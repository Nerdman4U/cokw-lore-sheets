"""Read-only Apps Script transport; no local Google OAuth dependencies."""
import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError


class WebAppProvider:
    def __init__(self, url=None):
        self.url = url or os.environ.get("LORE_SHEETS_WEB_APP_URL", "")
        self.key = os.environ.get("LORE_SHEETS_API_KEY", "")
        if not re.fullmatch(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", self.url):
            raise ValueError("Set LORE_SHEETS_WEB_APP_URL to the deployed https://script.google.com/macros/s/.../exec URL")
        if not self.key:
            raise ValueError("Set LORE_SHEETS_API_KEY to the web app's Script property value")
        self.account_id = self.call("about")["account_id"]

    def call(self, action, **params):
        body = json.dumps({"api_key": self.key, "action": action, **params}).encode("utf-8")
        request = Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=360) as response:
                result = json.load(response)
        except (URLError, TimeoutError, ValueError):
            raise ValueError("Web app request failed. Check deployment access, URL and connectivity") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            code = result.get("error") if isinstance(result, dict) else None
            allowed = {"UNAUTHORIZED", "INVALID_REQUEST", "GOOGLE_READ_FAILED", "UNSTABLE_READ", "SHEET_TOO_LARGE", "API_DISABLED", "PERMISSION_DENIED", "GOOGLE_UNAUTHORIZED", "ACCOUNT_UNAVAILABLE", "UNSUPPORTED_SHEET"}
            raise ValueError("Web app error: " + (code if isinstance(code, str) and code in allowed else "INVALID_RESPONSE"))
        return result["data"]

    def list_files(self, selection):
        files, page, seen = [], None, set()
        while True:
            result = self.call("list", selection=selection, page_token=page)
            files.extend(result.get("files", []))
            page = result.get("nextPageToken")
            if not page:
                return files
            if page in seen:
                raise ValueError("Web app returned a repeated page token")
            seen.add(page)

    def list_folders(self, parent_id):
        folders, page, seen = [], None, set()
        while True:
            result = self.call("folders", parent_id=parent_id, page_token=page)
            folders.extend(result.get("folders", []))
            page = result.get("nextPageToken")
            if not page:
                return folders
            if page in seen:
                raise ValueError("Web app returned a repeated folder page token")
            seen.add(page)

    def fetch(self, file, config):
        result = self.call("fetch", file_id=file["id"],
                           include_results=config["include_results"],
                           max_cells_per_sheet=config["max_cells_per_sheet"])
        return result["metadata"], result["spreadsheet"]
