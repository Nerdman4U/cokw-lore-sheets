# cokw-lore-sheets

A general-purpose, read-only Google Sheets auditing CLI. Capture an evening snapshot, capture another in the morning, and compare them offline. Code, tests and examples contain no user-specific file IDs, credentials or application-specific data.

## First version

- Catalog Google Sheets files with stable file IDs, names and parent folder IDs.
- List every selected file's sheets with stable sheet IDs, names, order and grid dimensions.
- Save each populated cell's exact user-entered value or formula, separately from its calculated value or error.
- Compute a versioned SHA-256 content hash per file and a separate calculated-results hash.
- Run configurable regex-based checks over file names, sheet names and A1 ranges.
- Compare files, sheets and individual cells by stable IDs. Renames are metadata changes.
- Write timestamped private JSON snapshots without overwriting previous captures.
- Report failed reads explicitly; refuse to compare incomplete captures.

Sparse storage means absent cells are empty; they are still tested when included in a check range. Row-relative formulas are stored exactly, not normalized into one shared formula template.

This is an audit tool, not a repair or restoration tool. It does not modify Google files. A hash detects changes; it does not prove a spreadsheet is correct or authenticate a snapshot's author.

## Install

Python 3.11 or newer:

~~~text
python -m venv .venv
~~~

Activate the virtual environment, then:

~~~text
python -m pip install -e .
cokw-lore-sheets --help
~~~

From a checkout, **python sheets.py ...** also works. On Windows, add the repository's **bin** directory to PATH to use its .cmd launcher. Offline commands and tests need only the Python standard library. The default Apps Script transport needs only the standard library. The optional **google** extra supports direct OAuth access.

## Apps Script web app (default)

1. Create your own Apps Script project. Copy **apps-script/Code.gs** into it.
2. In project settings, show the manifest and copy **apps-script/appsscript.json** into it.
3. In Script properties, add **LORE_SHEETS_API_KEY** with a long random secret of your own. Do not put it in source code.
4. The default Apps Script project uses built-in **DriveApp** and **SpreadsheetApp**; no Advanced Services or separate REST API activation is needed. A manually associated standard Cloud project may require Drive API enablement under Google's project rules.
5. Run **authorize** in the editor and approve the requested permissions.
6. Deploy as **Web app**, execute as **Me**, access **Anyone**. Copy the deployed **/exec** URL.
7. Set **LORE_SHEETS_WEB_APP_URL** and **LORE_SHEETS_API_KEY** in your local environment. Use the same key value as the Script property. Open a new terminal after persistent environment changes.
8. Copy examples/config.example.json outside the repository, adjust it, and run:

~~~text
cokw-lore-sheets dump --config /private/config.json
~~~

No local Google OAuth client or token is needed. The web app executes with its publisher's granted permissions. Each request is authenticated with the key in a JSON POST body; POST is only the transport and does not modify spreadsheets. Each file is captured in a separate request and file listings are paginated. The snapshot structure stays the same, but built-in captures use a separate account/profile identifier and cannot be compared with direct API captures.

Use **--web-app-url URL** to override the environment URL. The secret is read only from the environment. Public deployment does not mean unauthenticated access to the audit data: every action requires the key. Do not reuse the engine's key. Keep the web app URL and key out of public examples and shell history. Update the deployment to a new version after changing script code.

Large spreadsheets can exceed Apps Script execution or response limits. Such failures produce incomplete captures, never a successful empty capture; narrow the file selection or use the optional direct OAuth transport for these cases. Offline compare/check commands are unchanged.

See [Google's web app deployment guide](https://developers.google.com/apps-script/guides/web).

### Built-in capture limits

Built-in **getFormulas/getValues** preserve explicit formulas and typed non-formula values, including numbers, booleans and dates (converted to spreadsheet-local serial values). They cannot distinguish array/spill outputs from manually entered values, or distinguish a formula error from identical text. Formula-result changes in spill cells can therefore affect the input hash. Empty strings and empty cells are also indistinguishable. **no_error** checks conservatively treat recognized error strings as failures, including literal error text. Use direct OAuth capture when exact user-entered cell provenance or structured errors are required.

Built-in reads use before/after modification timestamps and metadata instead of Drive revision numbers. This is a weaker concurrent-edit check, not a transactional snapshot. Shared-drive support depends on DriveApp availability; direct OAuth remains the adapter for full shared-drive support. Unsupported non-grid sheets fail explicitly. Named ranges use their names as keys rather than API range IDs. The account/profile prefix prevents comparison against snapshots captured with the previous REST implementation. Start a new baseline after this update.

The built-in manifest requests **drive.readonly**, **spreadsheets**, and **userinfo.email**. SpreadsheetApp.openById requires the full spreadsheets scope even for reads; the implementation uses no write methods. The optional direct OAuth adapter retains its read-only scopes. The effective user's email is hashed for stable audit identity and is not returned in clear text. No spreadsheet or Drive write operations are used. After updating from the REST version, run **authorize** again to grant the changed scopes.

## Optional direct OAuth transport

Install **python -m pip install -e ".[google]"** and pass **--transport oauth** to dump to use the original direct Google API adapter.

## Private configuration and authorization

1. Create your own Google Cloud project and enable the **Google Drive API** and **Google Sheets API**.
2. Configure OAuth consent for your use and create an **OAuth Desktop app** client. Download its client JSON outside this repository.
3. Copy examples/config.example.json to a private location outside the repository. Edit the selection and checks.
4. Authorize interactively once:

~~~text
cokw-lore-sheets auth --client-secrets /private/path/client.json
~~~

Only **drive.metadata.readonly** and **spreadsheets.readonly** are requested. The token is saved outside the repository, by default:

- Windows: %LOCALAPPDATA%\cokw-lore-sheets\token.json
- Linux: $XDG_DATA_HOME/cokw-lore-sheets/token.json, falling back to ~/.local/share/cokw-lore-sheets/token.json.
- Other platforms: the same XDG/home fallback.

Use **--token PATH** on auth and dump for another private token. Refresh tokens are used without opening a browser during ordinary dumps. If authorization expires or is revoked, run auth again. OAuth testing/consent and verification requirements depend on your Google Cloud configuration. Publishing this source does not supply a shared OAuth client.

The tool refuses to write tokens, snapshots or reports inside a Git working tree. The ignore file also excludes common credentials, local config and capture names. Keep your downloaded client JSON and private config outside Git too. Snapshots can contain confidential spreadsheet contents.

Google references:

- [Python authorization setup](https://developers.google.com/workspace/sheets/api/quickstart/python)
- [Drive file listing](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list)
- [Sheets grid reads and field selection](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get)
- [User-entered and effective cell values](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells)

## Evening and morning

~~~text
cokw-lore-sheets dump --config /private/config.json --output /private/evening.snapshot.json
cokw-lore-sheets dump --config /private/config.json --output /private/morning.snapshot.json
cokw-lore-sheets compare /private/evening.snapshot.json /private/morning.snapshot.json --output /private/comparison.report.json
~~~

Omit **--output** on dump to save a timestamped snapshot in the application's private snapshots directory. Existing output files are never replaced.

By default, comparisons report input/formula and structure changes. They summarize calculated-results hashes separately. Add **compare --results** to include per-cell result differences in the change list and exit status. Volatile formulas, imports and recalculation can change results while the formula remains unchanged.

| Exit code | Meaning |
| --- | --- |
| 0 | Successful dump/check with passing rules, or comparison with no relevant changes |
| 1 | Failed check, or differences found by compare |
| 2 | Configuration/authentication/read error, incomplete capture or invalid comparison |

An incomplete dump is saved with complete=false and errors when individual files fail. Enumeration/authentication failures stop the command without creating a successful-looking dump. A missing file means it left the selected, visible catalog; it does not prove the physical file was deleted.

Use the same account, selection and include_results setting for both snapshots. The comparison rejects differing scopes to avoid misleading deletion claims. A failed rule is separate from capture completeness.

## Configuration

~~~json
{
  "version": 1,
  "files": {
    "name_pattern": ".*",
    "owned_only": true,
    "folder_ids": [],
    "file_ids": []
  },
  "include_results": true,
  "max_cells_per_sheet": 5000000,
  "max_check_cells": 100000,
  "checks": [
    {
      "name": "Imports",
      "file_pattern": ".*",
      "sheet_pattern": "^IMP_",
      "range": "A1",
      "test": "formula_matches",
      "pattern": "(?i)^=IMPORTRANGE\\s*\\("
    }
  ]
}
~~~

All patterns use Python regular expression **search**, case-sensitive unless a flag such as (?i) is supplied. files.name_pattern controls capture selection; a check's file_pattern only selects from captured files.

For IMP_ **file names**, set file_pattern to ^IMP_ and sheet_pattern to .*. The supplied example checks IMP_ **sheet names**.

**owned_only** defaults to true. Set it false to include accessible shared files. **folder_ids** selects direct children of any listed folder, **not recursive descendants**. **file_ids** further narrows the selection. All selection filters are combined. An explicitly listed file missing from the catalog makes the capture incomplete.

Supported areas: A1, B2:D20, A:A, 1:3, B2:B. Specify sheet filtering separately; sheet-qualified or named ranges are not accepted for checks in v1. Out-of-grid ranges and rules that match no files or no sheets are failures, not silently skipped. max_check_cells applies to each matched check/sheet.

| Test | Meaning |
| --- | --- |
| formula_matches | Exact stored formula matches pattern by regex search |
| value_matches | Calculated scalar value matches pattern; an error or absent result fails |
| not_empty | A nonempty user-entered value/formula exists; zero and false are valid |
| no_error | The cell has no effective Google Sheets error |
| unchanged | Each cell equals the same cell in --baseline; basis is input (default) or result |

The **no_error** test detects a calculation error, not its cause. A matching IMPORTRANGE formula and a successful import are two distinct checks; the example config runs both. Ranges are checked cell by cell, including empty cells. No user-supplied Python code is executed.

Run checks later without contacting Google:

~~~text
cokw-lore-sheets check /private/morning.snapshot.json --config /private/config.json --baseline /private/evening.snapshot.json
~~~

## Hash coverage and limits

SHA-256 is computed over UTF-8 canonical JSON, identified as **sha256-canonical-json-v1**. File IDs, names, parent IDs, captured spreadsheet properties, named ranges, sheet properties and each cell's exact input/formula contribute to the content hash. Effective values and errors contribute to the separate results hash. Capture timestamps, Drive modification time and Drive version do not contribute.

Only fields explicitly requested by this tool are captured. Formatting, notes, comments, charts, protections, validations, permissions, linked documents and complete revision history are **not** covered by v1. A result-only spill cell is covered by the results hash, not the input hash. Hashes are recalculated when loading a snapshot for checks/comparisons.

Each file is read with a Drive version check before and after; a concurrent edit causes a retry, up to three captures. This is not an atomic snapshot of the entire Drive, and calculated values can recalculate independently.

Large spreadsheets require time, memory and API quota. The allocated grid limit is checked before fetching cell data. Partial field masks reduce payloads, but v1 fetches a selected workbook's captured grid data in one request; finer-grained paging can be added later.

## Offline demonstration and tests

The fixture contains only synthetic IDs and invented spreadsheet contents:

~~~text
python sheets.py dump --config examples/config.example.json --fixture examples/fixture.example.json --output /private/demo.snapshot.json
python -m unittest discover -s tests -v
~~~

No scheduling is installed automatically. An OS scheduler can invoke dump nightly and invoke a morning dump followed by compare. Automatic baseline selection and a built-in scheduler are outside v1.
