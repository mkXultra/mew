from pathlib import Path

from .read_tools import resolve_allowed_path
from .tasks import clip_output
from .toolbox import run_git_tool


DEFAULT_WORLD_STATE_FILE_LIMIT = 8


def filter_internal_git_status(stdout):
    lines = []
    for line in (stdout or "").splitlines():
        path = line[3:] if len(line) > 3 else line
        if path == ".mew" or path.startswith(".mew/"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _world_git_status_cwds(allowed_read_roots):
    cwds = []
    for root in allowed_read_roots or []:
        try:
            path = Path(root).expanduser().resolve()
        except OSError:
            continue
        if path.is_file():
            path = path.parent
        if path.exists() and path not in cwds:
            cwds.append(path)
    try:
        cwd = Path(".").resolve()
        if cwd not in cwds:
            cwds.append(cwd)
    except OSError:
        pass
    return cwds


def _world_git_status(allowed_read_roots):
    first = None
    for cwd in _world_git_status_cwds(allowed_read_roots):
        result = run_git_tool("status", cwd=str(cwd))
        result["cwd"] = str(cwd)
        if first is None:
            first = result
        if result.get("exit_code") == 0:
            return result
    return first or run_git_tool("status", cwd=".")


def build_work_world_state(resume, allowed_read_roots, file_limit=None):
    if not allowed_read_roots:
        return {}

    world = {"files": []}
    git_status = _world_git_status(allowed_read_roots)
    world["git_status"] = {
        "exit_code": git_status.get("exit_code"),
        "cwd": git_status.get("cwd") or ".",
        "stdout": clip_output(filter_internal_git_status(git_status.get("stdout") or ""), 2000),
        "stderr": clip_output(git_status.get("stderr") or "", 1000),
    }

    paths = list((resume or {}).get("files_touched") or [])
    if file_limit is not None:
        paths = paths[: max(0, int(file_limit))]
    for path in paths:
        record = {"path": path}
        try:
            resolved = resolve_allowed_path(path, allowed_read_roots)
            stat = resolved.stat()
            record.update(
                {
                    "exists": True,
                    "type": "directory" if resolved.is_dir() else "file",
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        except OSError as exc:
            record.update({"exists": False, "error": str(exc)})
        except ValueError as exc:
            record.update({"exists": None, "error": str(exc)})
        world["files"].append(record)
    return world
