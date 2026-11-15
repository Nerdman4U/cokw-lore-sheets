# Coding guidelines

Build a general-purpose, public Python command-line tool for auditing Google Sheets.

- Keep story, organization and user-specific content out of code, examples and tests.
- Use read-only Google Drive and Sheets operations. This version must not modify spreadsheets.
- Keep credentials, tokens, private configuration, snapshots and reports outside the repository.
- Use UTF-8 explicitly for text files and deterministic SHA-256 hashing of canonical JSON.
- Separate Google access, snapshot handling, checks and CLI code. Offline comparison and unit tests must not require Google packages or credentials.
- Preserve each cell's exact user-entered formula and value; store calculated results separately.
- Identify files and sheets by stable IDs. Do not interpret a rename as deletion and recreation.
- Report read errors and unmatched checks explicitly. Incomplete captures must not produce deletion claims.
- Test behavior using synthetic data, including failure cases. Run python -m unittest discover -s tests.
- Do not publish or push without an explicit user request.
