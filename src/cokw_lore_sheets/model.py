"""Sparse per-cell snapshots and deterministic, versioned hashing."""
from datetime import datetime, timezone
import hashlib
import json
import re

from .config import address, selected

FORMAT = "sheets-audit-snapshot-v1"
HASH_VERSION = "sha256-canonical-json-v1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hashes(book):
    inputs, results = [], []
    for sheet in sorted(book["sheets"], key=lambda s: s["properties"]["sheetId"]):
        inputs.append({"properties": sheet["properties"],
                       "cells": {a: c["input"] for a, c in sheet["cells"].items() if c["input"]}})
        results.append({"sheet_id": sheet["properties"]["sheetId"],
                        "cells": {a: c.get("result", {}) for a, c in sheet["cells"].items()
                                  if c.get("result")}})
    content = {"id": book["id"], "name": book["name"], "parents": book["parents"],
               "properties": book["properties"], "named_ranges": book["named_ranges"],
               "sheets": inputs}
    return {"content_sha256": digest(content), "results_sha256": digest(results)}


def normalize(metadata, spreadsheet, config):
    if spreadsheet.get("spreadsheetId") != metadata["id"]:
        raise ValueError("Spreadsheet ID differs from file ID")
    sheets, seen = [], set()
    for item in spreadsheet.get("sheets", []):
        props = item["properties"]
        sid = props["sheetId"]
        if sid in seen:
            raise ValueError("Duplicate sheet ID")
        seen.add(sid)
        gp = props.get("gridProperties", {})
        count = gp.get("rowCount", 0) * gp.get("columnCount", 0)
        if count > config["max_cells_per_sheet"]:
            raise ValueError("Sheet exceeds max_cells_per_sheet; narrow the file selection or increase the limit")
        cells = {}
        for data in item.get("data", []):
            for ri, row in enumerate(data.get("rowData", []), data.get("startRow", 0) + 1):
                for ci, cell in enumerate(row.get("values", []), data.get("startColumn", 0) + 1):
                    entered = cell.get("userEnteredValue", {})
                    result = cell.get("effectiveValue", {}) if config["include_results"] else {}
                    if entered or result:
                        if ri > gp.get("rowCount", 0) or ci > gp.get("columnCount", 0):
                            raise ValueError("Cell outside grid")
                        addr = address(ri, ci)
                        if addr in cells:
                            raise ValueError("Overlapping grid data")
                        cells[addr] = {"input": entered}
                        if config["include_results"]:
                            cells[addr]["result"] = result
        sheets.append({"properties": props, "cells": cells})
    book = {"id": metadata["id"], "name": metadata["name"],
            "parents": sorted(metadata.get("parents", [])),
            "drive_version": metadata.get("version"),
            "modified_time": metadata.get("modifiedTime"),
            "properties": spreadsheet.get("properties", {}),
            "named_ranges": sorted(spreadsheet.get("namedRanges", []),
                                   key=lambda r: r.get("namedRangeId", "")),
            "sheets": sorted(sheets, key=lambda s: s["properties"]["sheetId"])}
    book["hashes"] = hashes(book)
    return book


def capture(provider, config):
    start = utc_now()
    catalog = provider.list_files(config["files"])
    if len({f["id"] for f in catalog}) != len(catalog):
        raise ValueError("Duplicate file IDs in catalog")
    files, errors = [], []
    chosen = [f for f in catalog if selected(f, config["files"])]
    missing = set(config["files"]["file_ids"]) - {f["id"] for f in catalog}
    errors.extend({"file_id": fid, "error": "Configured file is not visible in the selected catalog"}
                  for fid in sorted(missing))
    for file in sorted(chosen, key=lambda f: f["id"]):
        try:
            meta, raw = provider.fetch(file, config)
            files.append(normalize(meta, raw, config))
        except Exception as exc:
            # Avoid dumping OAuth tokens or URLs from third-party exception messages.
            status = getattr(getattr(exc, "resp", None), "status", None)
            detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            errors.append({"file_id": file["id"], "name": file["name"],
                           "error": detail, "http_status": status})
    return {"format": FORMAT, "hash_version": HASH_VERSION, "created_at": utc_now(),
            "started_at": start, "account_id": provider.account_id,
            "selection": config["files"], "include_results": config["include_results"],
            "complete": not errors, "errors": errors, "files": files}


def validate_snapshot(snapshot, complete=True):
    if not isinstance(snapshot, dict) or snapshot.get("format") != FORMAT:
        raise ValueError("Unsupported snapshot format")
    if snapshot.get("hash_version") != HASH_VERSION:
        raise ValueError("Unsupported hash version")
    if not isinstance(snapshot.get("account_id"), str) or not snapshot["account_id"]:
        raise ValueError("Snapshot account identity is missing")
    if not isinstance(snapshot.get("selection"), dict) or type(snapshot.get("include_results")) is not bool:
        raise ValueError("Snapshot capture configuration is missing")
    if complete and (snapshot.get("complete") is not True or snapshot.get("errors")):
        raise ValueError("Incomplete snapshot: comparison would be misleading")
    if not isinstance(snapshot.get("files"), list):
        raise ValueError("Invalid snapshot files")
    seen = set()
    for file in snapshot["files"]:
        if file["id"] in seen:
            raise ValueError("Duplicate snapshot file ID")
        seen.add(file["id"])
        if file["hashes"] != hashes(file):
            raise ValueError(f"Snapshot hash mismatch for file {file['id']}")
        ids = [s["properties"]["sheetId"] for s in file["sheets"]]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate snapshot sheet ID")
        for sheet in file["sheets"]:
            if any(not re.fullmatch(r"[A-Z]+[1-9][0-9]*", a) for a in sheet["cells"]):
                raise ValueError("Invalid snapshot cell address")
    return snapshot
