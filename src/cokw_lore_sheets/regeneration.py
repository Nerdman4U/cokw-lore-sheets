"""Explicit TMP writes, kept separate from read-only audit capture/check logic."""
import re

from .webapp import WebAppProvider


def validate_target(file_id, sheet_name):
    if not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
        raise ValueError("Invalid spreadsheet ID")
    if sheet_name is not None and (not isinstance(sheet_name, str) or not sheet_name.startswith("TMP_") or sheet_name.startswith("TMP_BACKUP_")):
        raise ValueError("Only assigned TMP_ sheets can be regenerated")


class RegenerationService:
    def __init__(self, provider):
        self.provider = provider

    def regenerate(self, file_id, sheet_name=None, dry_run=False):
        validate_target(file_id, sheet_name)
        request = {"file_id": file_id}
        if sheet_name is not None:
            request["sheet_name"] = sheet_name
        schema = self.provider.call("regenerationSchema", **request)
        if not isinstance(schema, dict) or not isinstance(schema.get("schema_revision"), str):
            raise ValueError("Invalid regeneration schema response")
        if dry_run:
            return {"status": "planned", **schema}
        result = self.provider.call("regenerate", **request, schema_revision=schema["schema_revision"])
        if not isinstance(result, dict) or result.get("status") not in ("regenerated", "regenerated_with_warnings", "regenerated_with_errors", "pending", "recovery_required"):
            raise ValueError("Invalid regeneration response")
        return result


def regenerate(file_id, sheet_name=None, *, web_app_url=None, dry_run=False):
    validate_target(file_id, sheet_name)
    return RegenerationService(WebAppProvider(web_app_url)).regenerate(file_id, sheet_name, dry_run)
