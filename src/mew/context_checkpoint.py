import subprocess

from .typed_memory import FileMemoryBackend, entry_to_dict, memory_entry_matches


CONTEXT_CHECKPOINT_QUERY = "Context save next safe action context compression long session"


def _parse_git_status_short(status_text):
    status_text = (status_text or "").rstrip("\n")
    tracked_dirty_paths = []
    untracked_paths = []
    dirty_paths = []
    for line in status_text.splitlines():
        if len(line) <= 2:
            continue
        path = line[3:] if len(line) > 3 and line[2] == " " else line[2:].lstrip()
        dirty_paths.append(path)
        if line.startswith("??"):
            untracked_paths.append(path)
        else:
            tracked_dirty_paths.append(path)
    if not dirty_paths:
        status = "clean"
    elif tracked_dirty_paths:
        status = "dirty"
    else:
        status = "untracked_only"
    return {
        "status_short": status_text,
        "status": status,
        "dirty_paths": dirty_paths,
        "tracked_dirty_paths": tracked_dirty_paths,
        "untracked_paths": untracked_paths,
    }


def current_git_reentry_state():
    data = {
        "head": "",
        "status": "unknown",
        "status_short": "",
        "dirty_paths": [],
        "tracked_dirty_paths": [],
        "untracked_paths": [],
    }
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if head.returncode == 0:
            data["head"] = (head.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if status.returncode == 0:
            data.update(_parse_git_status_short(status.stdout or ""))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return data


def context_load_current_state():
    git = current_git_reentry_state()
    return {
        "git_head": git.get("head") or "",
        "git_status": git.get("status") or "unknown",
        "git_status_short": git.get("status_short") or "",
        "dirty_paths": git.get("dirty_paths") or [],
        "tracked_dirty_paths": git.get("tracked_dirty_paths") or [],
        "untracked_paths": git.get("untracked_paths") or [],
    }


def extract_context_save_note(text):
    for line in str(text or "").splitlines():
        if line.startswith("Note:"):
            return line.removeprefix("Note:").strip()
    return ""


def matching_context_checkpoints(query=CONTEXT_CHECKPOINT_QUERY, *, base_dir="."):
    entries = [
        entry
        for entry in FileMemoryBackend(base_dir).entries()
        if entry.memory_type == "project" and memory_entry_matches(entry, query)
    ]
    entries.sort(key=lambda entry: (entry.created_at or "", entry.id), reverse=True)
    return entries


def context_checkpoint_to_dict(entry, *, recommended=False):
    item = entry_to_dict(entry)
    item["recommended"] = bool(recommended)
    item["reentry_note"] = extract_context_save_note(item.get("text"))
    item["diagnostics_are_historical"] = True
    return item


def compact_context_checkpoint(checkpoint):
    if not isinstance(checkpoint, dict):
        return {}
    return {
        "name": checkpoint.get("name") or checkpoint.get("key") or "",
        "created_at": checkpoint.get("created_at") or "",
        "description": checkpoint.get("description") or "",
        "path": checkpoint.get("path") or "",
        "reentry_note": checkpoint.get("reentry_note") or "",
        "diagnostics_are_historical": bool(checkpoint.get("diagnostics_are_historical")),
    }


def latest_context_checkpoint(query=CONTEXT_CHECKPOINT_QUERY, *, base_dir="."):
    entries = matching_context_checkpoints(query, base_dir=base_dir)
    if not entries:
        return {}
    return context_checkpoint_to_dict(entries[0], recommended=True)


def load_context_checkpoints(query=CONTEXT_CHECKPOINT_QUERY, limit=3, *, base_dir="."):
    limit = max(0, int(limit or 0))
    entries = matching_context_checkpoints(query, base_dir=base_dir)
    return [
        context_checkpoint_to_dict(entry, recommended=index == 0)
        for index, entry in enumerate(entries[:limit])
    ]
