from .read_tools import resolve_allowed_path
from .tasks import clip_output
from .toolbox import run_git_tool


DEFAULT_WORLD_STATE_FILE_LIMIT = 8


def build_work_world_state(resume, allowed_read_roots, file_limit=None):
    if not allowed_read_roots:
        return {}

    world = {"files": []}
    git_status = run_git_tool("status", cwd=".")
    world["git_status"] = {
        "exit_code": git_status.get("exit_code"),
        "stdout": clip_output(git_status.get("stdout") or "", 2000),
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
