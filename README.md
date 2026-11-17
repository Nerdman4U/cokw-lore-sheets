# cokw-lore-sheets

| Project | Details |
| --- | --- |
| Implementation | OpenAI Codex / ChatGPT |
| Model | GPT-6.1 Sol Light (as reported by the user's interface) |
| Design and development | In collaboration with the project maintainer |
| Version | 0.1.0 (initial release) |
| Updated | 2026-11-15 |
| Runtime | Python 3.11+; Google Apps Script V8 for the web app |
| Purpose | Google Sheets audit snapshots, configurable checks and offline comparisons |

A general-purpose Google Sheets auditing CLI with a separate, explicit TMP regeneration command. Capture an evening snapshot, capture another in the morning, and compare them offline. Code, tests and examples contain no user-specific file IDs, credentials or application-specific data.

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

Audit commands do not modify Google files. The separate **regenerate** command intentionally rebuilds registered TMP_ sheets and preserves keyed inputs. A hash detects changes; it does not prove a spreadsheet is correct or authenticate a snapshot's author.

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

Tokens must stay outside Git. Snapshots and reports may be written inside a Git working tree only when git check-ignore confirms the destination is ignored (for example audit/); tracked files are never exempted. The ignore file also excludes common credentials, local config and capture names. Keep your downloaded client JSON and private config outside Git too. Snapshots can contain confidential spreadsheet contents.

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

## Recursive folder selection

Set **files.folder_ids** to one or more Drive folder IDs and **files.recursive** to **true** to capture spreadsheets directly in those folders and all descendant folders. The default is false (direct children only). Roots remain in the snapshot selection; newly discovered descendants do not change the comparison scope. Overlapping roots and repeated folders are visited once. Folder-read failures abort catalog discovery rather than implying deletions. Folder shortcuts are not followed. Other file filters still apply: set **owned_only: false** to include accessible spreadsheets owned by others within the selected tree. With no folder IDs, recursive has no effect.

~~~json
{"version":1,"files":{"folder_ids":["YOUR_FOLDER_ID"],"recursive":true,"owned_only":false},"checks":[]}
~~~

The web app must be updated to the version that supports the **folders** action. No new Google scopes are required. A previously unrestricted dump and a folder-scoped dump have different selections and cannot be compared; capture a fresh baseline with the new configuration.

## List configured check targets (offline)

Use **list** to inspect the cells selected by the **checks** array without evaluating the rules or contacting Google:

~~~text
cokw-lore-sheets list /private/evening.snapshot.json --config /private/config.json
cokw-lore-sheets list /private/evening.snapshot.json --config /private/config.json --output /private/imports.tsv
cokw-lore-sheets list /private/evening.snapshot.json --config /private/config.json --format json --output /private/imports.json
~~~

The default TSV shows the check name, file name/ID, sheet name/ID, address, formula, typed input and result. JSON also includes the test name and an issues array. Output files use UTF-8 and are never overwritten. Blank targeted cells are included; multiple checks targeting the same cell produce separate rows identified by check name. Values are displayed even if they fail the check: listing does not mean validation passed. An **unchanged** check can be listed without a baseline.

For listing, **checks** and **max_check_cells** select cells from the already captured snapshot. The config's capture selection (**files**, **include_results**) does not recapture or filter the source; this permits inspecting an older snapshot with a new check configuration. Missing results are JSON null when results were not captured. The stored capture selection is unchanged.

A rule with no matching files or no matching sheets anywhere is reported explicitly, as are invalid or oversized ranges. Files with no matching sheets are skipped; **list**, **check** and summaries share this two-stage targeting behavior. An empty checks array is also reported. Exit codes: 0 = listing complete, 1 = target-selection issues, 2 = incomplete source or input/output error. Incomplete dumps may be inspected but are clearly reported and never count as a successful complete listing. Snapshot hashes are validated before listing.

A generic rule to list import cells, including wrapped formulas such as IF(...IMPORTRANGE(...)), is:

~~~json
{"name":"Import formula in A1","file_pattern":".*","sheet_pattern":"^IMP_","range":"A1","test":"formula_matches","pattern":"(?i)\\bIMPORTRANGE\\s*\\("}
~~~

This regex is a configurable text check, not a formula parser. **list** shows all matched cells, **check** evaluates the rule, and **compare** compares two captures.

## Concise check status

~~~text
cokw-lore-sheets check /private/evening.snapshot.json --config /private/config.json --format summary
cokw-lore-sheets check /private/evening.snapshot.json --config /private/config.json --format summary --output /private/status.txt
~~~

Summary output is one **file-sheet OK** or **file-sheet ERROR** line per targeted file/sheet pair. Checks are grouped by stable IDs: any failed check or checked cell makes that target ERROR. A rule with no matching files or no matching sheets anywhere produces an ERROR row using the unmatched pattern. Files without targeted sheets are skipped. Empty checks produce **checks ERROR**. Exit code 0 means all configured checks passed, 1 means check/target failures, 2 means an input/output error. Use the default **--format json** for detailed failure reasons. Summary output is UTF-8 and never overwrites an existing report.

Offline **check**, like **list**, applies the checks to the existing snapshot; the config's **files** capture selection does not filter or recapture it. The captured **include_results** setting must still match for check evaluation. Baseline comparisons continue to require compatible capture selections. This lets you inspect an existing evening snapshot after changing the next dump's folder configuration.

Check targeting has two stages: **file_pattern** limits candidate files, then **sheet_pattern** selects target sheets within them. Only files with at least one target sheet take part in that rule. Finally, every cell in the configured range on each selected sheet is evaluated against the test/pattern. Selecting **^IMP_** never requires every candidate file to contain an import sheet. A rule matching no sheets in the entire capture still reports an error instead of silently passing.

## Check sheet names

**sheet_name_matches** validates the name itself once per selected sheet, without reading a cell or using **range**. Selection and validation remain separate: **file_pattern** selects candidate files, **sheet_pattern** selects sheets, and **pattern** defines the requirement for each selected name. All patterns use regex search; use ^ and $ for a whole-name requirement.

~~~json
{
  "name": "Import sheet naming convention",
  "file_pattern": ".*",
  "sheet_pattern": "^IMP_",
  "test": "sheet_name_matches",
  "pattern": "^IMP_[A-Za-z0-9_.]+$"
}
~~~

**list** displays one row per selected name with a blank Cell column, the name as typed Input, and no calculated Result. JSON marks the row **target: sheet_name** and **cell: null**. **check --format summary** groups name and cell checks on the same file/sheet: any failed requirement makes that line ERROR. Name checks work even when a sheet has no grid/cells or results were not captured. Missing **pattern** or an invalid regex is rejected before evaluation.


## Regenerate schema-driven TMP sheets

```powershell
cokw-lore-sheets regenerate <spreadsheet-id>
cokw-lore-sheets regenerate <spreadsheet-id> TMP_Example
cokw-lore-sheets regenerate <spreadsheet-id> TMP_Example --dry-run
```

This is a separate writing subsystem (`regeneration.py` and `apps-script/Regeneration.gs`).
No capture, list, check or compare command invokes it. The same web app URL and API key are used.
Configure the Apps Script property **LORE_SHEETS_META_SCHEMA_ID** once with the private metadata
workbook ID, then publish both Apps Script files together. No spreadsheet IDs belong in this repository.
Existing spreadsheet permissions already include the required write scope; Drive remains read-only.

The CLI first POSTs **regenerationSchema** to read/validate the metadata and target, then POSTs
**regenerate** with that exact schema revision. `--dry-run` only performs the first request.
An omitted sheet name selects all schemas explicitly assigned to the given workbook.
Only registered `TMP_` targets are accepted. Model workbooks also need explicit assignments;
the program does not infer assignments from other workbooks using a model.

The metadata workbook has four sheets (row 1 contains headers):

| Sheet | Required columns |
| --- | --- |
| Skeemat | Nimi, Otsikko, Järjestys, LahdeVälilehti, Kaava, Kaavarivit, Riviavain, Format |
| Mallit | MalliID |
| Tiedostot | TiedostoID, MalliID |
| TiedostojenSkeemat | TiedostoID, Skeema |

`Nimi` identifies a TMP sheet; `Otsikko` is its column header; unique positive integer `Järjestys`
values order columns. Exactly one column per schema has `Riviavain=TRUE`; the others are FALSE.
Blank `Kaava` means user input, including zero, false and dates. Header matching is exact after
trimming whitespace. `LähdeOtsikko` and `EsimerkkiKaava` may provide descriptive information;
the Kaava field controls executable formulas. `Format` is passed to Sheets unchanged.

Formulas may contain any native Sheets expression. Only these reserved placeholders are expanded:

| Placeholder | Expansion |
| --- | --- |
| `{SRC:Header}` | Current column under Header on LahdeVälilehti, row 2 through its open-ended column |
| `{COL_30}` | TMP column whose Järjestys is 30 |
| `{R}`, `{R-1}`, `{R+1}` | Target row, previous row, next row |

`Kaavarivit` specifies `2`, `2:14`, or `2:MAX`. MAX is the existing grid's last row; a new
TMP sheet starts with 1,000 rows. A spill formula is written once when the metadata specifies `2`.
No function-name heuristics or custom spreadsheet formula interpreter are used.
Missing/duplicate source headers, duplicate keys, input rows without keys and bad assignments
are rejected before any target is cleared. Native formula syntax is evaluated by Sheets after writing.

Before changing any target, a hidden **TMP_BACKUP_<id>** sheet stores a versioned JSON recovery
snapshot, including old cell values/formulas and the keyed input mapping. Existing TMP sheet IDs
are preserved. Headers, formats and calculated columns are rebuilt; inputs return to the matching
key, even if row order changes. New keys have blank inputs. Removed keys and removed columns
remain in the backup and are reported as orphaned/unmapped. Key names must remain stable;
a renamed key cannot be automatically identified as its old name.

`flush()` plus bounded polling waits for error-free, stable key reads before restoration.
An import still loading produces **pending**; a write/readback error produces
**recovery_required**. Both return the backup sheet name/ID and CLI exit code 1. Rerun the exact
same command with unchanged metadata to resume from the persisted original input snapshot.
Do not change the selected schema set or schema metadata while recovery is pending.
After restoring inputs, native calculation errors are reported as **regenerated_with_errors**
and orphaned inputs/unmapped columns as **regenerated_with_warnings**, both with exit code 1.
Calculation errors in other columns do not prevent restoring inputs first.
The backup stays in the workbook even after success; cleanup is manual.

If old row keys are already broken before the first regeneration, the tool stops rather than
guessing where input belongs. Recover those keys from a prior backup/source before proceeding.
Do not edit the target manually during regeneration. ScriptLock serializes this application's
writes, but cannot lock out human edits or make multiple spreadsheet operations atomic.
The pre-write recheck detects changes during preparation. If source changes have already
replaced old key results with different values, their previous meaning cannot be inferred from
the new results. Keep source changes and regeneration coordinated; prior backups remain the
recovery source, and unmatched inputs are reported rather than silently discarded. Polling observes calculated values;
it is not a transactional guarantee that every external import has permanently stabilized.

Schema/input grids are bounded to prevent oversized Apps Script requests (250,000 target cells;
5,000 metadata rows). Exit code 0 means regenerated/planned, 1 means warnings, calculation errors or pending/recovery required,
and 2 means invalid setup, preflight failure or transport failure. A timeout must not be treated
as proof that no write happened: rerun to use the server-side pending recovery record.
