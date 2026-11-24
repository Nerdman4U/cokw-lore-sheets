"""Read-only, sparse formula-footprint auditing; never treat spills as formulas."""
from time import perf_counter
import re

DEFAULTS = {"enabled": True, "max_formula_row": 500, "max_formula_rows": 500,
            "min_blank_tail_rows": 100, "rules": []}


def settings(raw):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
        raise ValueError("Invalid anomalies configuration")
    result = {**DEFAULTS, **raw}
    if type(result["enabled"]) is not bool:
        raise ValueError("anomalies.enabled must be boolean")
    for k in ("max_formula_row", "max_formula_rows", "min_blank_tail_rows"):
        if type(result[k]) is not int or result[k] < 1:
            raise ValueError(f"anomalies.{k} must be a positive integer")
    if not isinstance(result["rules"], list):
        raise ValueError("anomalies.rules must be a list")
    for rule in result["rules"]:
        allowed = {"file_pattern", "sheet_pattern", "max_formula_row", "max_formula_rows", "min_blank_tail_rows"}
        if not isinstance(rule, dict) or set(rule) - allowed:
            raise ValueError("Invalid anomaly rule")
        for key in ("file_pattern", "sheet_pattern"):
            if not isinstance(rule.get(key, ".*"), str):
                raise ValueError("Anomaly patterns must be strings")
            try:
                re.compile(rule.get(key, ".*"))
            except re.error:
                raise ValueError("Invalid anomaly pattern") from None
        for key in allowed - {"file_pattern", "sheet_pattern"}:
            if key in rule and (type(rule[key]) is not int or rule[key] < 1):
                raise ValueError("Anomaly thresholds must be positive integers")
    return result


def audit(snapshot, config, check_times=None):
    policy = settings(config.get("anomalies"))
    reports, warnings = [], []
    for file in snapshot["files"]:
        for sheet in file["sheets"]:
            started = perf_counter()
            props = sheet["properties"]
            limits = dict(policy)
            for rule in policy["rules"]:
                if re.search(rule.get("file_pattern", ".*"), file["name"]) and re.search(rule.get("sheet_pattern", ".*"), props["title"]):
                    limits.update(rule)
            formulas, literal_rows, result_rows = {}, set(), set()
            for addr, cell in sheet.get("cells", {}).items():
                row = int(re.search(r"[1-9][0-9]*$", addr)[0])
                entered = cell.get("input", {})
                if "formulaValue" in entered:
                    formulas[addr] = (row, cell)
                elif entered and entered.get("stringValue") != "":
                    literal_rows.add(row)
                result = cell.get("result", {})
                if result and result.get("stringValue") != "":
                    result_rows.add(row)
            formula_rows = {row for row, _ in formulas.values()}
            last_formula = max(formula_rows, default=0)
            last_literal = max(literal_rows, default=0)
            local = []
            if limits["enabled"]:
                if last_formula > limits["max_formula_row"]:
                    local.append({"kind": "formula_extent", "last_formula_row": last_formula,
                                  "limit": limits["max_formula_row"]})
                if len(formula_rows) > limits["max_formula_rows"]:
                    local.append({"kind": "many_formula_rows", "formula_rows": len(formula_rows),
                                  "limit": limits["max_formula_rows"]})
                # Blank output is only supporting evidence, never proof a formula is useless.
                tail = {addr: row for addr, (row, cell) in formulas.items()
                        if row > last_literal and "result" in cell and
                        (not cell["result"] or cell["result"] == {"stringValue": ""})}
                if len(set(tail.values())) >= limits["min_blank_tail_rows"]:
                    spans = {}
                    for addr, row in tail.items():
                        spans.setdefault(re.match(r"[A-Z]+", addr)[0], []).append(row)
                    ranges = []
                    for column, numbers in sorted(spans.items()):
                        numbers.sort(); start = end = numbers[0]
                        for row in numbers[1:]:
                            if row != end + 1:
                                ranges.append(f"{column}{start}:{column}{end}"); start = row
                            end = row
                        ranges.append(f"{column}{start}:{column}{end}")
                    local.append({"kind": "blank_formula_tail", "formula_rows": len(set(tail.values())),
                                  "ranges": ranges, "action": "Review dependencies and intended row bounds, then remove confirmed surplus formulas in the spreadsheet; do not merely hide them in the snapshot"})
            ident = {"file_id": file["id"], "file_name": file["name"],
                     "sheet_id": props["sheetId"], "sheet_name": props["title"]}
            warnings.extend({**ident, **w, "automatic_deletion_safe": False} for w in local)
            timing = sheet.get("timings", {})
            reports.append({**ident, "formula_cells": len(formulas), "formula_rows": len(formula_rows),
                            "last_formula_row": last_formula, "last_literal_row": last_literal,
                            "last_result_row": max(result_rows, default=0),
                            "grid_rows": props.get("gridProperties", {}).get("rowCount"),
                            "load_ms": timing.get("load_ms"),
                            "load_measurement": timing.get("load_measurement", "not recorded; workbook transfer time is not a per-sheet measurement"),
                            "normalize_ms": timing.get("normalize_ms"),
                            "check_ms": round((perf_counter()-started)*1000 + (check_times or {}).get((file["id"], props["sheetId"]), 0), 3),
                            "workbook_transfer_ms": file.get("timings", {}).get("transfer_ms"),
                            "warning_count": len(local)})
    return {"source_complete": bool(snapshot.get("complete")), "sheets": reports,
            "warnings": warnings, "warning_count": len(warnings)}
