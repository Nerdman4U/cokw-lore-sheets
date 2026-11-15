"""Private local files; never overwrite a previous dump."""
from pathlib import Path
import json
import os


def data_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "cokw-lore-sheets"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {value}")))


def private_path(path):
    path = Path(path).expanduser().resolve()
    if any((p / ".git").exists() for p in (path.parent, *path.parents)):
        raise ValueError("Keep private snapshots, reports and tokens outside Git repositories")
    return path


def write_json(path, value):
    path = private_path(path)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def save_token(path, text):
    """Replace a refreshable token atomically, using a private sibling file."""
    import secrets
    path = private_path(path)
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        write_json(temp, json.loads(text))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
