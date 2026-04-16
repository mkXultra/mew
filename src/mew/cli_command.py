import os
from pathlib import Path
import shlex


def mew_executable():
    local = Path.cwd() / "mew"
    if local.is_file() and os.access(local, os.X_OK):
        return "./mew"
    return "mew"


def mew_command(*parts):
    return shlex.join([mew_executable(), *(str(part) for part in parts)])
