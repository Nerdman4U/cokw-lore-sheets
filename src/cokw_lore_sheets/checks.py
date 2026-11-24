"""Evaluate named, read-only cell checks; no Python eval in configuration."""
from .config import regex, bounds, address
from contextlib import contextmanager
from time import perf_counter
from .anomalies import audit
from .targets import match_targets


def scalar(value):
    if "errorValue" in value:
        return None
    for key in ("stringValue", "numberValue", "boolValue"):
        if key in value:
            return value[key]
    return None


def evaluate(snapshot, config, baseline=None):
    failures, tested = [], 0
    timings = {}
    @contextmanager
    def measured(file, sheet):
        started = perf_counter()
        try:
            yield
        finally:
            key = (file["id"], sheet["properties"]["sheetId"])
            timings[key] = timings.get(key, 0) + (perf_counter()-started)*1000

    prior = {f["id"]: f for f in baseline["files"]} if baseline else {}

    def fail(rule, reason, file=None, sheet=None, cell=None):
        failures.append({"check": rule["name"], "reason": reason,
                         "file_id": file["id"] if file else None,
                         "file_name": file["name"] if file else None,
                         "sheet_id": sheet["properties"]["sheetId"] if sheet else None,
                         "sheet_name": sheet["properties"]["title"] if sheet else None,
                         "cell": cell})

    for rule in config["checks"]:
        targets, reason = match_targets(snapshot, rule)
        if reason:
            fail(rule, reason)
        for file, sheet in targets:
            with measured(file, sheet):
                if rule["test"] == "sheet_name_matches":
                    tested += 1
                    if not regex(rule["pattern"]).search(sheet["properties"]["title"]):
                        fail(rule, "sheet_name_matches failed", file, sheet)
                    continue
                gp = sheet["properties"].get("gridProperties", {})
                try:
                    r1, c1, r2, c2 = bounds(rule["range"], gp.get("rowCount", 0), gp.get("columnCount", 0))
                    if (r2-r1+1)*(c2-c1+1) > config["max_check_cells"]:
                        raise ValueError("Range exceeds max_check_cells")
                except ValueError as exc:
                    fail(rule, str(exc), file, sheet)
                    continue
                previous = next((s for s in prior.get(file["id"], {}).get("sheets", [])
                                 if s["properties"]["sheetId"] == sheet["properties"]["sheetId"]), None)
                if rule["test"] == "unchanged" and previous is None:
                    fail(rule, "No baseline file/sheet for unchanged check", file, sheet)
                    continue
                for row in range(r1, r2+1):
                    for column in range(c1, c2+1):
                        addr = address(row, column)
                        cell = sheet["cells"].get(addr, {})
                        entered, result = cell.get("input", {}), cell.get("result", {})
                        test = rule["test"]
                        if test == "formula_matches":
                            formula = entered.get("formulaValue")
                            ok = isinstance(formula, str) and bool(regex(rule["pattern"]).search(formula))
                        elif test == "value_matches":
                            value = scalar(result)
                            ok = value is not None and bool(regex(rule["pattern"]).search(str(value)))
                        elif test == "not_empty":
                            ok = bool(entered) and entered.get("stringValue") != ""
                        elif test == "no_error":
                            ok = "errorValue" not in result
                            if snapshot["account_id"].startswith("builtin-values-v1:"):
                                ok = ok and result.get("stringValue") not in {
                                    "#ERROR!", "#REF!", "#DIV/0!", "#VALUE!", "#N/A",
                                    "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}
                        else:
                            basis = rule["basis"]
                            ok = cell.get(basis, {}) == previous["cells"].get(addr, {}).get(basis, {})
                        tested += 1
                        if not ok:
                            fail(rule, f"{test} failed", file, sheet, addr)
    footprint = audit(snapshot, config, timings)
    return {"tested_cells": tested, "failures": failures, "sheet_audit": footprint, "passed": not failures and not footprint["warnings"]}


def summary_lines(snapshot, config, report):
    """Group all configured checks by stable file/sheet IDs for concise output."""
    targets = {}
    for rule in config["checks"]:
        matched, reason = match_targets(snapshot, rule)
        if reason:
            pattern = rule["file_pattern"] if not matched and reason.startswith("No captured files") else rule["sheet_pattern"]
            targets[(None, None, rule["name"])] = (rule["name"], pattern, False)
        for file, sheet in matched:
            props = sheet["properties"]
            key = (file["id"], props["sheetId"], "")
            bad = any(f["file_id"] == file["id"] and f["sheet_id"] == props["sheetId"]
                      for f in report["failures"])
            targets[key] = (file["name"], props["title"], not bad)
    if not targets:
        return ["checks ERROR"]
    # Keep embedded line breaks from splitting one target into multiple status lines.
    def single_line(value):
        return value.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    audit_report = report.get("sheet_audit", {})
    by_sheet = {(s["file_id"], s["sheet_id"]): s for s in audit_report.get("sheets", [])}
    lines = []
    for key, item in by_sheet.items():
        if item["warning_count"]:
            targets.setdefault((*key, ""), (item["file_name"], item["sheet_name"], True))
    for key, (file, sheet, ok) in sorted(targets.items(), key=lambda kv: (kv[1][0].casefold(), kv[1][1].casefold())):
        entry = by_sheet.get(key[:2], {})
        if entry:
            load = "n/a" if entry["load_ms"] is None else str(entry["load_ms"])+"ms"
            detail = f" [load={load} check={entry['check_ms']}ms]"
            status = "ERROR" if not ok else "WARNING" if entry["warning_count"] else "OK"
        else:
            detail, status = "", "OK" if ok else "ERROR"
        lines.append(f"{single_line(file)}-{single_line(sheet)}{detail} {status}")
    for warning in audit_report.get("warnings", []):
        ranges = ",".join(warning.get("ranges", []))
        lines.append(f"WARNING {single_line(warning['file_name'])}-{single_line(warning['sheet_name'])}: {warning['kind']} {ranges}".rstrip())
    return lines
