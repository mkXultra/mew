import os
from pathlib import Path
import shlex
import sys


def _argv_mew_executable():
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return ""
    path = Path(argv0)
    if path.name != "mew":
        return ""
    if not path.is_absolute() and path.parent == Path("."):
        return ""
    candidate = path if path.is_absolute() else (Path.cwd() / path).resolve(strict=False)
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return ""


def mew_executable():
    override = os.environ.get("MEW_EXECUTABLE")
    if override:
        return override
    launched = _argv_mew_executable()
    if launched:
        return launched
    local = Path.cwd() / "mew"
    if local.is_file() and os.access(local, os.X_OK):
        return "./mew"
    return "mew"


def mew_command(*parts):
    return shlex.join([mew_executable(), *(str(part) for part in parts)])
