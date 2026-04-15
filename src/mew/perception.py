from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Protocol

from .read_tools import is_sensitive_path, normalize_allowed_roots
from .tasks import clip_output
from .toolbox import resolve_tool_cwd, run_command_record


MAX_GIT_STATUS_LINES = 50
MAX_GIT_STATUS_CHARS = 3000
MAX_RECENT_FILE_CHANGES = 12
MAX_RECENT_SCAN_ENTRIES = 1500
SKIP_DIR_NAMES = {
    ".git",
    ".mew",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


class Observer(Protocol):
    name: str

    def observe(self, cwd, roots):
        pass


OBSERVERS = []


def register_observer(observer):
    OBSERVERS.append(observer)
    return observer


def _is_relative_to(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_allowed(path, roots):
    return any(path == root or _is_relative_to(path, root) for root in roots)


def _safe_cwd(cwd):
    try:
        return resolve_tool_cwd(cwd)
    except ValueError:
        path = Path(cwd or ".").expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path


def git_status_observation(cwd):
    record = run_command_record("git status --short --branch", cwd=str(cwd), timeout=5)
    stdout = record.get("stdout") or ""
    stderr = record.get("stderr") or ""
    lines = stdout.splitlines()
    branch = ""
    changes = lines
    if lines and lines[0].startswith("## "):
        branch = lines[0][3:]
        changes = lines[1:]

    return {
        "type": "git_status",
        "status": "ok" if record.get("exit_code") == 0 else "unavailable",
        "cwd": record.get("cwd") or str(cwd),
        "exit_code": record.get("exit_code"),
        "branch": branch,
        "clean": record.get("exit_code") == 0 and not changes,
        "changes": changes[:MAX_GIT_STATUS_LINES],
        "truncated": len(changes) > MAX_GIT_STATUS_LINES,
        "stdout": clip_output(stdout, MAX_GIT_STATUS_CHARS),
        "stderr": clip_output(stderr, MAX_GIT_STATUS_CHARS),
    }


def _timestamp_iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def recent_file_changes_observation(roots, limit=MAX_RECENT_FILE_CHANGES):
    files = []
    scanned = 0
    truncated = False
    for root in roots:
        for current, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in SKIP_DIR_NAMES and not is_sensitive_path(Path(current) / dirname)
            ]
            for filename in filenames:
                scanned += 1
                path = Path(current) / filename
                if is_sensitive_path(path):
                    continue
                if scanned > MAX_RECENT_SCAN_ENTRIES:
                    truncated = True
                    break
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files.append(
                    {
                        "path": str(path),
                        "mtime": _timestamp_iso(stat.st_mtime),
                        "size": stat.st_size,
                    }
                )
            if truncated:
                break
        if truncated:
            break

    files.sort(key=lambda item: item["mtime"], reverse=True)
    return {
        "type": "recent_file_changes",
        "status": "ok",
        "roots": [str(root) for root in roots],
        "files": files[:limit],
        "scanned": scanned,
        "truncated": truncated or len(files) > limit,
    }


class GitStatusObserver:
    name = "git_status"

    def observe(self, cwd, roots):
        return [git_status_observation(cwd)]


class RecentFileChangesObserver:
    name = "recent_file_changes"

    def observe(self, cwd, roots):
        return [recent_file_changes_observation(roots)]


register_observer(GitStatusObserver())
register_observer(RecentFileChangesObserver())


def perceive_workspace(allowed_read_roots=None, cwd=None):
    resolved_cwd = _safe_cwd(cwd)
    roots = normalize_allowed_roots(allowed_read_roots)
    observations = [
        {
            "type": "workspace",
            "cwd": str(resolved_cwd),
            "allowed_read_roots": [str(root) for root in roots],
        }
    ]
    if not resolved_cwd.exists() or not resolved_cwd.is_dir():
        observations.append(
            {
                "type": "workspace_status",
                "status": "error",
                "reason": "cwd does not exist or is not a directory",
            }
        )
        return {"observations": observations}

    if not roots:
        observations.append(
            {
                "type": "read_scope",
                "status": "disabled",
                "reason": "no allowed_read_roots configured",
            }
        )
        return {"observations": observations}

    if not _path_allowed(resolved_cwd.resolve(), roots):
        observations.append(
            {
                "type": "read_scope",
                "status": "blocked",
                "reason": "cwd is outside allowed_read_roots",
            }
        )
        return {"observations": observations}

    observations.append({"type": "read_scope", "status": "allowed"})
    for observer in OBSERVERS:
        try:
            observations.extend(observer.observe(resolved_cwd, roots))
        except Exception as exc:
            observations.append(
                {
                    "type": getattr(observer, "name", "observer"),
                    "status": "error",
                    "error": str(exc),
                }
            )
    return {"observations": observations}


def format_perception(perception):
    observations = perception.get("observations", [])
    lines = []
    for observation in observations:
        kind = observation.get("type")
        if kind == "workspace":
            lines.append(f"cwd: {observation.get('cwd')}")
            roots = observation.get("allowed_read_roots") or []
            lines.append("allowed_read_roots: " + (", ".join(roots) if roots else "(none)"))
        elif kind == "workspace_status":
            text = f"workspace_status: {observation.get('status')}"
            if observation.get("reason"):
                text += f" ({observation.get('reason')})"
            lines.append(text)
        elif kind == "read_scope":
            text = f"read_scope: {observation.get('status')}"
            if observation.get("reason"):
                text += f" ({observation.get('reason')})"
            lines.append(text)
        elif kind == "git_status":
            lines.append(
                "git_status: "
                f"{observation.get('status')} exit_code={observation.get('exit_code')} "
                f"clean={observation.get('clean')}"
            )
            if observation.get("branch"):
                lines.append(f"branch: {observation.get('branch')}")
            changes = observation.get("changes") or []
            if changes:
                lines.append("changes:")
                lines.extend(changes)
            if observation.get("stderr"):
                lines.append("stderr:")
                lines.append(observation.get("stderr"))
        elif kind == "recent_file_changes":
            lines.append(
                "recent_file_changes: "
                f"{observation.get('status')} scanned={observation.get('scanned')} "
                f"truncated={observation.get('truncated')}"
            )
            for file_item in observation.get("files", []):
                lines.append(
                    f"- {file_item.get('mtime')} {file_item.get('size')} {file_item.get('path')}"
                )
        elif observation.get("status") == "error":
            lines.append(f"{kind}: error {observation.get('error')}")
    return "\n".join(lines) if lines else "No perception observations."
