"""Evaluate named, read-only cell checks; no Python eval in configuration."""
from .config import regex, bounds, address


def scalar(value):
    if "errorValue" in value:
        return None
    for key in ("stringValue", "numberValue", "boolValue"):
        if key in value:
            return value[key]
    return None


def evaluate(snapshot, config, baseline=None):
    failures, tested = [], 0
    prior = {f["id"]: f for f in baseline["files"]} if baseline else {}

    def fail(rule, reason, file=None, sheet=None, cell=None):
        failures.append({"check": rule["name"], "reason": reason,
                         "file_id": file["id"] if file else None,
                         "file_name": file["name"] if file else None,
                         "sheet_id": sheet["properties"]["sheetId"] if sheet else None,
                         "sheet_name": sheet["properties"]["title"] if sheet else None,
                         "cell": cell})

    for rule in config["checks"]:
        matches = [f for f in snapshot["files"] if regex(rule["file_pattern"]).search(f["name"])]
        if not matches:
            fail(rule, "No captured files matched the check")
        for file in matches:
            sheets = [s for s in file["sheets"] if regex(rule["sheet_pattern"]).search(s["properties"]["title"])]
            if not sheets:
                fail(rule, "No sheets matched the check", file)
            for sheet in sheets:
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
    return {"tested_cells": tested, "failures": failures, "passed": not failures}
