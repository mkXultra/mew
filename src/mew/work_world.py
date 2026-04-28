from pathlib import Path

from .read_tools import is_sensitive_path, resolve_allowed_path
from .tasks import clip_output
from .toolbox import run_git_tool


DEFAULT_WORLD_STATE_FILE_LIMIT = 8
WORLD_STATE_SNAPSHOT_SKIP_NAMES = {
    ".git",
    ".mew",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


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
    if not cwds:
        try:
            cwd = Path(".").resolve()
            if cwd not in cwds:
                cwds.append(cwd)
        except OSError:
            pass
    return cwds


def _world_base(cwd=None):
    path = Path(cwd or ".").expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _world_path_for_cwd(path, base):
    candidate = Path(path or ".").expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((base / candidate).resolve(strict=False))


def _world_roots_for_cwd(allowed_read_roots, cwd=None):
    base = _world_base(cwd)
    roots = []
    for root in allowed_read_roots or []:
        raw = str(root or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
        text = str(path.resolve(strict=False))
        if text not in roots:
            roots.append(text)
    return roots


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


def _display_world_path(path, cwd=None):
    base = _world_base(cwd)
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
    except OSError:
        return str(path)


def _world_file_record(path, display_path, source):
    record = {"path": display_path, "source": source}
    try:
        stat = path.stat()
        record.update(
            {
                "exists": True,
                "type": "directory" if path.is_dir() else "file",
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    except OSError as exc:
        record.update({"exists": False, "error": str(exc)})
    return record


def _allowed_missing_path(path, allowed_read_roots, cwd=None):
    requested = str(path or "").strip()
    if not requested:
        raise ValueError("path is required")
    base = _world_base(cwd)
    candidate = Path(requested).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    if is_sensitive_path(resolved):
        raise ValueError(f"refusing to inspect sensitive path: {requested}")
    for root in allowed_read_roots or []:
        try:
            allowed_root = Path(root).expanduser()
            if not allowed_root.is_absolute():
                allowed_root = base / allowed_root
            allowed_root = allowed_root.resolve(strict=False)
        except OSError:
            continue
        if allowed_root.exists() and allowed_root.is_file():
            allowed_root = allowed_root.parent
        try:
            resolved.relative_to(allowed_root)
            return resolved
        except ValueError:
            continue
    raise ValueError(f"path is not under an allowed read root: {requested}")


def _resume_target_path_records(resume):
    paths = []

    def add_path(value):
        path = str(value or "").strip()
        if path and path not in paths:
            paths.append(path)

    working_memory = (resume or {}).get("working_memory")
    if isinstance(working_memory, dict):
        for path in working_memory.get("target_paths") or []:
            add_path(path)
    active_todo = (resume or {}).get("active_work_todo")
    if isinstance(active_todo, dict):
        source = active_todo.get("source") if isinstance(active_todo.get("source"), dict) else {}
        for path in source.get("target_paths") or []:
            add_path(path)
    return [(path, "target_path") for path in paths]


def _resume_world_path_records(resume):
    touched = [(path, "touched") for path in (resume or {}).get("files_touched") or []]
    if touched:
        return touched
    return _resume_target_path_records(resume)


def _workspace_snapshot_records(allowed_read_roots, file_limit, cwd=None):
    records = []
    count = max(0, int(file_limit))
    if count == 0:
        return records
    for root in allowed_read_roots or []:
        if len(records) >= count:
            break
        try:
            path = Path(root).expanduser().resolve()
        except OSError:
            continue
        if not path.exists():
            continue
        if path.is_file():
            records.append(
                _world_file_record(path, _display_world_path(path, cwd=cwd), "workspace_snapshot")
            )
            continue
        try:
            children = sorted(
                path.iterdir(),
                key=lambda item: (item.is_file(), item.name.casefold()),
            )
        except OSError:
            continue
        for child in children:
            if len(records) >= count:
                break
            if child.name in WORLD_STATE_SNAPSHOT_SKIP_NAMES:
                continue
            records.append(
                _world_file_record(child, _display_world_path(child, cwd=cwd), "workspace_snapshot")
            )
    return records


def build_work_world_state(resume, allowed_read_roots, file_limit=None, cwd=None):
    if not allowed_read_roots:
        return {}

    base = _world_base(cwd)
    allowed_read_roots = _world_roots_for_cwd(allowed_read_roots, cwd=base)
    world = {"files": []}
    git_status = _world_git_status(allowed_read_roots)
    world["git_status"] = {
        "exit_code": git_status.get("exit_code"),
        "cwd": git_status.get("cwd") or ".",
        "stdout": clip_output(filter_internal_git_status(git_status.get("stdout") or ""), 2000),
        "stderr": clip_output(git_status.get("stderr") or "", 1000),
    }

    snapshot_limit = DEFAULT_WORLD_STATE_FILE_LIMIT if file_limit is None else max(0, int(file_limit))
    paths = _resume_world_path_records(resume)
    if file_limit is not None:
        paths = paths[:snapshot_limit]
    for path, source in paths:
        record = {"path": path}
        try:
            resolved = resolve_allowed_path(_world_path_for_cwd(path, base), allowed_read_roots)
            if is_sensitive_path(resolved):
                raise ValueError(f"refusing to inspect sensitive path: {path}")
            record.update(_world_file_record(resolved, path, source))
        except OSError as exc:
            record.update({"exists": False, "error": str(exc)})
        except ValueError as exc:
            if "path does not exist" in str(exc):
                try:
                    resolved = _allowed_missing_path(path, allowed_read_roots, cwd=base)
                    record.update(_world_file_record(resolved, path, source))
                except ValueError as missing_exc:
                    record.update({"exists": None, "error": str(missing_exc)})
            else:
                record.update({"exists": None, "error": str(exc)})
        world["files"].append(record)
    if not world["files"]:
        world["files"] = _workspace_snapshot_records(allowed_read_roots, snapshot_limit, cwd=base)
    return world
