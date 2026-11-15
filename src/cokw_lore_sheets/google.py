"""Read-only Google Drive / Sheets adapter. Imported only for live commands."""
from pathlib import Path

from .storage import private_path, save_token

SCOPES = (
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
)
FILE_FIELDS = "id,name,parents,ownedByMe,version,modifiedTime"
PROPERTIES = ("spreadsheetId,properties(title,locale,timeZone,autoRecalc),"
              "namedRanges(namedRangeId,name,range),"
              "sheets(properties(sheetId,title,index,sheetType,"
              "gridProperties(rowCount,columnCount,frozenRowCount,frozenColumnCount,hideGridlines)))")


def dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ValueError('Live Google access needs: python -m pip install -e ".[google]"') from None
    return Request, Credentials, InstalledAppFlow, build


def authorize(client_secrets, token):
    _, _, Flow, _ = dependencies()
    private_path(client_secrets)
    private_path(token)
    flow = Flow.from_client_secrets_file(str(Path(client_secrets).expanduser()), scopes=SCOPES)
    creds = flow.run_local_server(port=0)
    if not creds.has_scopes(SCOPES):
        raise ValueError("The requested read-only scopes were not granted")
    save_token(token, creds.to_json())


def credentials(token):
    Request, Credentials, _, _ = dependencies()
    path = private_path(token)
    if not path.is_file():
        raise ValueError("No token found. Run auth --client-secrets PATH first")
    creds = Credentials.from_authorized_user_file(str(path), scopes=SCOPES)
    if not creds.has_scopes(SCOPES):
        raise ValueError("Token lacks the read-only scopes; run auth again")
    if not creds.valid:
        if not creds.refresh_token:
            raise ValueError("Token cannot be refreshed; run auth again")
        try:
            creds.refresh(Request())
        except Exception:
            raise ValueError("Google token refresh failed; run auth again") from None
        save_token(path, creds.to_json())
    return creds


class GoogleProvider:
    def __init__(self, token):
        _, _, _, build = dependencies()
        creds = credentials(token)
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        user = self.drive.about().get(fields="user(permissionId)").execute(num_retries=3)
        self.account_id = user["user"]["permissionId"]

    def list_files(self, selection):
        clauses = ["mimeType='application/vnd.google-apps.spreadsheet'", "trashed=false"]
        if selection["owned_only"]:
            clauses.append("'me' in owners")
        if selection["folder_ids"]:
            clauses.append("(" + " or ".join(f"'{fid}' in parents" for fid in selection["folder_ids"]) + ")")
        token, seen, files = None, set(), []
        while True:
            response = self.drive.files().list(
                q=" and ".join(clauses), pageSize=1000, pageToken=token,
                spaces="drive", supportsAllDrives=True, includeItemsFromAllDrives=True,
                fields=f"nextPageToken,incompleteSearch,files({FILE_FIELDS})"
            ).execute(num_retries=3)
            if response.get("incompleteSearch"):
                raise ValueError("Drive returned an incomplete search; narrow the selection")
            files.extend(response.get("files", []))
            token = response.get("nextPageToken")
            if not token:
                return files
            if token in seen:
                raise ValueError("Drive returned a repeated page token")
            seen.add(token)

    def fetch(self, file, config):
        # Optimistic consistency check per spreadsheet; no account-wide transaction is claimed.
        for _ in range(3):
            before = self.drive.files().get(fileId=file["id"], fields=FILE_FIELDS,
                                            supportsAllDrives=True).execute(num_retries=3)
            meta = self.sheets.spreadsheets().get(
                spreadsheetId=file["id"], fields=PROPERTIES
            ).execute(num_retries=3)
            for sheet in meta.get("sheets", []):
                gp = sheet["properties"].get("gridProperties", {})
                if gp.get("rowCount", 0) * gp.get("columnCount", 0) > config["max_cells_per_sheet"]:
                    raise ValueError("Sheet exceeds max_cells_per_sheet")
            cell_fields = "userEnteredValue,effectiveValue" if config["include_results"] else "userEnteredValue"
            raw = self.sheets.spreadsheets().get(
                spreadsheetId=file["id"],
                fields=PROPERTIES[:-1] + f",data(startRow,startColumn,rowData(values({cell_fields}))))"
            ).execute(num_retries=3)
            after = self.drive.files().get(fileId=file["id"], fields=FILE_FIELDS,
                                           supportsAllDrives=True).execute(num_retries=3)
            if not before.get("version") or not after.get("version"):
                raise ValueError("Drive did not return a file version; cannot verify a stable read")
            if before["version"] == after["version"]:
                return after, raw
        raise ValueError("Spreadsheet changed during all three read attempts")
