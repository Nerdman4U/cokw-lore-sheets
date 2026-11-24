"""Offline differences by stable file/sheet IDs and exact cell addresses."""
from .model import validate_snapshot


def compatible(before, after):
    validate_snapshot(before); validate_snapshot(after)
    for key in ("account_id", "selection", "include_results"):
        if before.get(key) != after.get(key):
            raise ValueError(f"Snapshot {key} differs; use the same account and capture configuration")


def compare(before, after, include_results=False, config=None):
    compatible(before, after)
    if include_results and not after["include_results"]:
        raise ValueError("Results were not captured")
    changes, result_hash_changes = [], []

    def change(kind, file, **details):
        changes.append({"kind": kind, "file_id": file["id"], "file_name": file["name"], **details})

    old = {f["id"]: f for f in before["files"]}
    new = {f["id"]: f for f in after["files"]}
    for fid in sorted(old.keys() - new.keys()):
        change("file_removed", old[fid])
    for fid in sorted(new.keys() - old.keys()):
        change("file_added", new[fid], hashes=new[fid]["hashes"])
    for fid in sorted(old.keys() & new.keys()):
        a, b = old[fid], new[fid]
        for key in ("name", "parents", "properties", "named_ranges"):
            if a[key] != b[key]:
                change("file_metadata_changed", b, field=key, before=a[key], after=b[key])
        if a["hashes"]["content_sha256"] != b["hashes"]["content_sha256"]:
            change("content_hash_changed", b, before=a["hashes"]["content_sha256"],
                   after=b["hashes"]["content_sha256"])
        if a["hashes"]["results_sha256"] != b["hashes"]["results_sha256"]:
            result_hash_changes.append({"file_id": fid, "file_name": b["name"],
                                        "before": a["hashes"]["results_sha256"],
                                        "after": b["hashes"]["results_sha256"]})
        sa = {s["properties"]["sheetId"]: s for s in a["sheets"]}
        sb = {s["properties"]["sheetId"]: s for s in b["sheets"]}
        for sid in sorted(sa.keys() - sb.keys()):
            change("sheet_removed", b, sheet_id=sid, sheet_name=sa[sid]["properties"]["title"])
        for sid in sorted(sb.keys() - sa.keys()):
            change("sheet_added", b, sheet_id=sid, sheet_name=sb[sid]["properties"]["title"])
        for sid in sorted(sa.keys() & sb.keys()):
            x, y = sa[sid], sb[sid]
            if x["properties"] != y["properties"]:
                change("sheet_metadata_changed", b, sheet_id=sid,
                       before=x["properties"], after=y["properties"])
            for addr in sorted(x["cells"].keys() | y["cells"].keys()):
                for key in (("input", "result") if include_results else ("input",)):
                    prior = x["cells"].get(addr, {}).get(key, {})
                    current = y["cells"].get(addr, {}).get(key, {})
                    if prior != current:
                        change("cell_"+key+"_changed", b, sheet_id=sid,
                               sheet_name=y["properties"]["title"], cell=addr,
                               before=prior, after=current)
    from .anomalies import audit
    sheet_audit = audit(after, config or {})
    return {"sheet_audit": sheet_audit, "format": "sheets-audit-comparison-v1", "before": before["created_at"],
            "after": after["created_at"], "has_changes": bool(changes), "changes": changes,
            "result_hash_changes": result_hash_changes,
            "results_included_in_changes": include_results}
