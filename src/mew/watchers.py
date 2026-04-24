from pathlib import Path

from .state import add_event
from .timeutil import now_iso


def _snapshot_path(path):
    path = Path(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {
            "exists": False,
            "is_dir": False,
            "mtime_ns": None,
            "size": None,
        }
    return {
        "exists": True,
        "is_dir": path.is_dir(),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _change_kind(previous, current):
    if not previous:
        return "baseline"
    if not previous.get("exists") and current.get("exists"):
        return "created"
    if previous.get("exists") and not current.get("exists"):
        return "deleted"
    return "modified"


def _watch_key(path):
    return str(Path(path).expanduser().resolve(strict=False))


def _watch_label(path):
    return str(Path(path).expanduser())


def _watcher_item(items, path):
    key = _watch_key(path)
    for item in items:
        if item.get("key") == key:
            return item
    item = {
        "id": len(items) + 1,
        "key": key,
        "path": _watch_label(path),
        "absolute_path": key,
        "kind": "file",
        "status": "idle",
        "source": "daemon_watch",
        "snapshot": None,
        "last_checked_at": None,
        "last_changed_at": None,
        "last_event_id": None,
    }
    items.append(item)
    return item


def scan_watch_paths(state, paths, *, current_time=None, active=False, source="daemon_watch"):
    current_time = current_time or now_iso()
    watcher_state = state.setdefault("watchers", {})
    items = watcher_state.setdefault("items", [])
    requested = [_watch_key(path) for path in paths or []]
    requested_set = set(requested)
    events = []
    changed = False

    for path in paths or []:
        item = _watcher_item(items, path)
        status = "active" if active else "idle"
        if item.get("status") != status:
            item["status"] = status
            changed = True
        current = _snapshot_path(Path(path).expanduser())
        previous = item.get("snapshot")
        if previous is None:
            item["last_checked_at"] = current_time
            item["snapshot"] = current
            changed = True
            continue
        if previous == current:
            continue
        item["last_checked_at"] = current_time
        item["snapshot"] = current
        changed = True
        event = add_event(
            state,
            "file_change",
            source,
            {
                "path": item.get("path"),
                "absolute_path": item.get("absolute_path"),
                "change_kind": _change_kind(previous, current),
                "previous": previous,
                "current": current,
            },
        )
        item["last_changed_at"] = current_time
        item["last_event_id"] = event.get("id")
        events.append(event)

    retained_items = []
    removed = False
    for item in items:
        if item.get("kind") != "file" or item.get("key") in requested_set:
            retained_items.append(item)
            continue
        removed = True
    if removed:
        items[:] = retained_items
        changed = True

    watcher_state["updated_at"] = current_time
    watcher_state["active_count"] = len([item for item in items if item.get("status") == "active"])
    watcher_state["count"] = len(items)
    return {"events": events, "changed": changed}


def deactivate_watchers(state, *, current_time=None):
    current_time = current_time or now_iso()
    watcher_state = state.setdefault("watchers", {})
    items = watcher_state.setdefault("items", [])
    changed = False
    for item in items:
        if item.get("status") == "active":
            item["status"] = "idle"
            changed = True
    if changed:
        watcher_state["updated_at"] = current_time
        watcher_state["active_count"] = 0
        watcher_state["count"] = len(items)
    return changed
