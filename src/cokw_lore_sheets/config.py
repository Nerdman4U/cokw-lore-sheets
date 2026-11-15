"""Small, validated JSON configuration; no executable code in rules."""
import re

TESTS = {"formula_matches", "value_matches", "not_empty", "no_error", "unchanged"}


def regex(pattern):
    if not isinstance(pattern, str):
        raise ValueError("Regex patterns must be strings")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from None


def bounds(area, rows, columns):
    """Resolve bounded A1 ranges, open ranges, whole columns and whole rows."""
    if not isinstance(area, str) or "!" in area or not area:
        raise ValueError("Use an A1 cell/range without a sheet name")
    parts = area.upper().split(":")
    if len(parts) > 2:
        raise ValueError(f"Invalid A1 range: {area}")

    def parse(part):
        m = re.fullmatch(r"([A-Z]*)([1-9][0-9]*)?", part)
        if not m or not any(m.groups()):
            raise ValueError(f"Invalid A1 range: {area}")
        col = 0
        for letter in m[1]:
            col = col * 26 + ord(letter) - 64
        return (int(m[2]) if m[2] else None), (col or None)

    first = parse(parts[0])
    if len(parts) == 1:
        if None in first:
            raise ValueError("Use A:A or 1:1 for a whole column/row")
        last = first
    else:
        last = parse(parts[1])
    r1, c1 = first[0] or 1, first[1] or 1
    r2, c2 = last[0] or rows, last[1] or columns
    if not (1 <= r1 <= r2 <= rows and 1 <= c1 <= c2 <= columns):
        raise ValueError(f"Range {area} is outside the sheet grid")
    return r1, c1, r2, c2


def address(row, column):
    letters = ""
    while column:
        column, rem = divmod(column - 1, 26)
        letters = chr(65 + rem) + letters
    return letters + str(row)


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a JSON object")
    unknown = set(raw) - {"version", "files", "checks", "include_results",
                          "max_cells_per_sheet", "max_check_cells"}
    if unknown:
        raise ValueError("Unknown config fields: " + ", ".join(sorted(unknown)))
    if type(raw.get("version", 1)) is not int or raw.get("version", 1) != 1:
        raise ValueError("Unsupported configuration version")
    files = raw.get("files", {})
    if not isinstance(files, dict) or set(files) - {
        "name_pattern", "owned_only", "folder_ids", "file_ids"
    }:
        raise ValueError("Invalid files configuration")
    files = {"name_pattern": ".*", "owned_only": True,
             "folder_ids": [], "file_ids": [], **files}
    regex(files["name_pattern"])
    if type(files["owned_only"]) is not bool:
        raise ValueError("owned_only must be a boolean")
    for key in ("folder_ids", "file_ids"):
        if not isinstance(files[key], list) or any(
            not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", v)
            for v in files[key]
        ):
            raise ValueError(f"{key} must contain Drive IDs")
        files[key] = sorted(set(files[key]))
    results = raw.get("include_results", True)
    if type(results) is not bool:
        raise ValueError("include_results must be a boolean")
    checks = raw.get("checks", [])
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    rules, names = [], set()
    for item in checks:
        if not isinstance(item, dict) or set(item) - {
            "name", "file_pattern", "sheet_pattern", "range", "test", "pattern", "basis"
        }:
            raise ValueError("Invalid check fields")
        rule = {"file_pattern": ".*", "sheet_pattern": ".*", "range": "A1",
                "basis": "input", **item}
        name = rule.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Each check needs a nonempty, unique name")
        names.add(name)
        if rule.get("test") not in TESTS:
            raise ValueError(f"Unknown test in check {name}")
        regex(rule["file_pattern"]); regex(rule["sheet_pattern"])
        # Validate syntax before any API request, without imposing actual grid limits.
        bounds(rule["range"], 10_000_000, 18_278)
        if rule["test"].endswith("_matches"):
            if "pattern" not in rule:
                raise ValueError(f"Check {name} needs pattern")
            regex(rule["pattern"])
        if rule["basis"] not in {"input", "result"}:
            raise ValueError("unchanged basis must be input or result")
        if not results and (rule["test"] in {"value_matches", "no_error"}
                            or (rule["test"] == "unchanged" and rule["basis"] == "result")):
            raise ValueError(f"Check {name} requires include_results=true")
        rules.append(rule)
    limits = {}
    for key, default in (("max_cells_per_sheet", 5_000_000), ("max_check_cells", 100_000)):
        value = raw.get(key, default)
        if type(value) is not int or value < 1:
            raise ValueError(f"{key} must be a positive integer")
        limits[key] = value
    return {"version": 1, "files": files, "checks": rules,
            "include_results": results, **limits}


def selected(file, config):
    return bool(
        regex(config["name_pattern"]).search(file["name"])
        and (not config["owned_only"] or file.get("ownedByMe", False))
        and (not config["folder_ids"] or set(file.get("parents", [])) & set(config["folder_ids"]))
        and (not config["file_ids"] or file["id"] in config["file_ids"])
    )
