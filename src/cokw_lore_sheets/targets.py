"""Two-stage check targeting shared by evaluation, listing and summaries."""
from .config import regex


def match_targets(snapshot, rule):
    file_pattern, sheet_pattern = regex(rule["file_pattern"]), regex(rule["sheet_pattern"])
    files = sorted((file for file in snapshot["files"] if file_pattern.search(file["name"])),
                   key=lambda file: (file["name"].casefold(), file["id"]))
    targets = [(file, sheet) for file in files
               for sheet in sorted(file["sheets"],
                   key=lambda sheet: (sheet["properties"]["title"].casefold(), sheet["properties"]["sheetId"]))
               if sheet_pattern.search(sheet["properties"]["title"])]
    reason = None
    if not files:
        reason = "No captured files matched the check"
    elif not targets:
        reason = "No sheets matched the check in any matching file"
    return targets, reason
