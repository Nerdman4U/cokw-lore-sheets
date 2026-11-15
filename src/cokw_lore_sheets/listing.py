"""Offline inspection of cells targeted by configured checks; no evaluation."""
import csv
import io
import json
from .config import bounds, address
from .targets import match_targets


def list_cells(snapshot, config):
    rows, issues = [], []
    if not snapshot["complete"]:
        issues.append({"reason": "Source snapshot is incomplete", "errors": snapshot.get("errors", [])})
    if not config["checks"]:
        issues.append({"reason": "No checks configured"})
    for rule in config["checks"]:
        targets, reason = match_targets(snapshot, rule)
        if reason:
            issues.append({"check": rule["name"], "reason": reason})
        for file, sheet in targets:
            props = sheet["properties"]
            if rule["test"] == "sheet_name_matches":
                rows.append({"check": rule["name"], "test": rule["test"],
                             "file_id": file["id"], "file_name": file["name"],
                             "sheet_id": props["sheetId"], "sheet_name": props["title"],
                             "cell": None, "target": "sheet_name",
                             "input": {"stringValue": props["title"]}, "result": None})
                continue
            grid = props.get("gridProperties", {})
            try:
                r1, c1, r2, c2 = bounds(rule["range"], grid.get("rowCount", 0), grid.get("columnCount", 0))
                if (r2-r1+1)*(c2-c1+1) > config["max_check_cells"]:
                    raise ValueError("Range exceeds max_check_cells")
            except ValueError as exc:
                issues.append({"check": rule["name"], "file_id": file["id"],
                               "sheet_id": props["sheetId"], "reason": str(exc)})
                continue
            for ri in range(r1, r2+1):
                for ci in range(c1, c2+1):
                    cell_address = address(ri, ci)
                    cell = sheet["cells"].get(cell_address, {})
                    rows.append({"check": rule["name"], "test": rule["test"],
                                 "file_id": file["id"], "file_name": file["name"],
                                 "sheet_id": props["sheetId"], "sheet_name": props["title"],
                                 "cell": cell_address, "input": cell.get("input", {}),
                                 "result": cell.get("result", {}) if snapshot["include_results"] else None})
    return {"source_complete": snapshot["complete"], "rows": rows, "issues": issues}


def render(report, output_format):
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    text = io.StringIO(newline="")
    writer = csv.writer(text, delimiter="\t", lineterminator="\n")
    writer.writerow(["Check", "File", "File ID", "Sheet", "Sheet ID", "Cell", "Formula", "Input", "Result"])
    for row in report["rows"]:
        entered = row["input"]
        writer.writerow([row["check"], row["file_name"], row["file_id"], row["sheet_name"],
                         row["sheet_id"], row["cell"], entered.get("formulaValue", ""),
                         json.dumps(entered, ensure_ascii=False),
                         json.dumps(row["result"], ensure_ascii=False)])
    return text.getvalue()
