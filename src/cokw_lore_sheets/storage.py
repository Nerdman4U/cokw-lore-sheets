"""Private local files; never overwrite a previous dump."""
from pathlib import Path
import json
import os
import subprocess


def data_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "cokw-lore-sheets"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {value}")))


def private_path(path, allow_ignored=False):
    path = Path(path).expanduser().resolve()
    if any((p / ".git").exists() for p in (path.parent, *path.parents)):
        ignored = False
        if allow_ignored:
            try:
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", "--", str(path)],
                    cwd=path.parent if path.parent.is_dir() else next(p for p in path.parents if p.is_dir()),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
                ).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not ignored:
            raise ValueError("Keep private snapshots and reports outside Git or in an explicitly ignored directory; tokens must stay outside Git")
    return path


def write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    return write_text(path, text)


def write_text(path, text):
    """Save UTF-8 text with the same privacy and no-overwrite rules as snapshots."""
    path = private_path(path, allow_ignored=True)
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
