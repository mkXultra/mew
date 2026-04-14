from pathlib import Path

from .read_tools import normalize_allowed_roots
from .tasks import clip_output
from .toolbox import resolve_tool_cwd, run_command_record


MAX_GIT_STATUS_LINES = 50
MAX_GIT_STATUS_CHARS = 3000


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
    observations.append(git_status_observation(resolved_cwd))
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
    return "\n".join(lines) if lines else "No perception observations."
