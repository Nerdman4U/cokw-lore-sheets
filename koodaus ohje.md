# Coding guidelines

Build a general-purpose, public Python command-line tool for auditing Google Sheets.

- Keep story, organization and user-specific content out of code, examples and tests.
- Audit commands use read-only Google Drive and Sheets operations. Explicit TMP regeneration is a separate writing subsystem and must preserve keyed inputs in a persistent recovery snapshot before changing target sheets.
- Keep credentials, tokens, private configuration, snapshots and reports outside the repository.
- Use UTF-8 explicitly for text files and deterministic SHA-256 hashing of canonical JSON.
- Separate Google access, snapshot handling, checks and CLI code. Offline comparison and unit tests must not require Google packages or credentials.
- Preserve each cell's exact user-entered formula and value; store calculated results separately.
- Identify files and sheets by stable IDs. Do not interpret a rename as deletion and recreation.
- Report read errors and unmatched checks explicitly. Incomplete captures must not produce deletion claims.
- Test behavior using synthetic data, including failure cases. Run python -m unittest discover -s tests.
- Do not publish or push without an explicit user request.

- Apps Script web app uses built-in DriveApp and SpreadsheetApp only; no UrlFetchApp or Advanced Services. Document built-in capture limitations and keep its baseline profile separate from exact API captures.
- Run node tests/webapp-script.test.cjs when changing the Apps Script adapter.

- TMP regeneration reads its private metadata workbook ID from LORE_SHEETS_META_SCHEMA_ID in Script properties. Keep target IDs out of public code. Test reorder preservation, preflight refusal, failed writes and pending retries with synthetic workbooks. Run node tests/regeneration-script.test.cjs.


- Formula footprint diagnostics count exact formula inputs, not spill result rows or allocated grid rows. Blank results are review evidence only; never automatically delete formulas based on them. Preserve suspicious cells in snapshots and repair confirmed defects at the source spreadsheet.
- Per-sheet load metrics are measured in the built-in WebApp. Workbook round-trip, local normalization and local checking times are separate. Missing per-sheet measurements remain null; never fabricate them from workbook totals. Timing metadata is excluded from hashes.
