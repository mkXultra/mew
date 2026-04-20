from pathlib import Path

from .cli_command import mew_command
from .config import STATE_DIR
from .timeutil import now_iso, parse_time


RUNTIME_OUTPUT_FILE = STATE_DIR / "runtime.out"


def _runtime_lock_state(lock, pid_alive_func):
    if not lock:
        return {"state": "none", "pid": None, "started_at": None}
    pid = lock.get("pid")
    return {
        "state": "active" if pid_alive_func(pid) else "stale",
        "pid": pid,
        "started_at": lock.get("started_at"),
    }


def _elapsed_seconds(since, until):
    start = parse_time(since)
    end = parse_time(until)
    if not start or not end:
        return None
    return max(0.0, round((end - start).total_seconds(), 3))


def _watcher_items(state):
    runtime = state.get("runtime_status") or {}
    configured = runtime.get("watchers")
    if configured is None:
        configured = state.get("watchers")
    if not configured:
        return []
    if isinstance(configured, dict):
        configured = configured.get("items") or configured.get("active") or []
    if not isinstance(configured, list):
        return []

    watchers = []
    for index, item in enumerate(configured, start=1):
        if isinstance(item, dict):
            watcher = dict(item)
        else:
            watcher = {"name": str(item)}
        watcher.setdefault("id", index)
        watcher.setdefault("status", "unknown")
        watcher.setdefault("kind", watcher.get("type") or "unknown")
        watchers.append(watcher)
    return watchers


def build_daemon_status(state, lock, pid_alive_func, *, current_time=None):
    current_time = current_time or now_iso()
    runtime = state.get("runtime_status") or {}
    autonomy = state.get("autonomy") or {}
    lock_state = _runtime_lock_state(lock, pid_alive_func)
    active = lock_state["state"] == "active"
    started_at = lock_state.get("started_at") or runtime.get("started_at")
    pid = lock_state.get("pid") if lock_state.get("pid") is not None else runtime.get("pid")
    watchers = _watcher_items(state)
    active_watchers = [watcher for watcher in watchers if watcher.get("status") in ("active", "running", "watching")]
    last_tick_at = runtime.get("last_woke_at") or runtime.get("last_evaluated_at")

    state_name = runtime.get("state") or "unknown"
    if active:
        state_name = "running"
    elif lock_state["state"] == "stale":
        state_name = "stale"

    return {
        "state": state_name,
        "pid": pid,
        "started_at": started_at,
        "uptime_seconds": _elapsed_seconds(started_at, current_time) if active else None,
        "lock": lock_state,
        "current": {
            "reason": runtime.get("current_reason") or "",
            "phase": runtime.get("current_phase") or "",
            "event_id": runtime.get("current_event_id"),
            "effect_id": runtime.get("current_effect_id"),
            "cycle_started_at": runtime.get("cycle_started_at"),
        },
        "last_tick": {
            "at": last_tick_at,
            "reason": runtime.get("last_cycle_reason") or "",
            "processed_count": runtime.get("last_processed_count"),
            "duration_seconds": runtime.get("last_cycle_duration_seconds"),
            "age_seconds": _elapsed_seconds(last_tick_at, current_time),
        },
        "watchers": {
            "count": len(watchers),
            "active_count": len(active_watchers),
            "items": watchers,
        },
        "safety": {
            "autonomy_enabled": bool(autonomy.get("enabled")),
            "autonomy_level": autonomy.get("level") or "off",
            "autonomy_paused": bool(autonomy.get("paused")),
            "allow_agent_run": bool(autonomy.get("allow_agent_run")),
            "allow_native_work": bool(autonomy.get("allow_native_work")),
            "allow_write": bool(autonomy.get("allow_write")),
            "allow_verify": bool(autonomy.get("allow_verify")),
        },
        "output_path": str(RUNTIME_OUTPUT_FILE),
        "controls": {
            "start": mew_command("daemon", "start", "--", "--autonomous"),
            "stop": mew_command("daemon", "stop"),
            "pause": mew_command("daemon", "pause", "maintenance"),
            "resume": mew_command("daemon", "resume"),
            "inspect": mew_command("daemon", "inspect"),
            "logs": mew_command("daemon", "logs"),
            "repair": mew_command("daemon", "repair"),
        },
    }


def format_daemon_status(data):
    current = data.get("current") or {}
    last_tick = data.get("last_tick") or {}
    watchers = data.get("watchers") or {}
    safety = data.get("safety") or {}
    lines = [
        f"daemon_state: {data.get('state')}",
        f"pid: {data.get('pid') or ''}",
        f"uptime_seconds: {data.get('uptime_seconds')}",
        f"lock: {(data.get('lock') or {}).get('state')}",
        f"started_at: {data.get('started_at') or ''}",
        f"current_reason: {current.get('reason') or ''}",
        f"current_phase: {current.get('phase') or ''}",
        f"last_tick_at: {last_tick.get('at') or ''}",
        f"last_tick_reason: {last_tick.get('reason') or ''}",
        f"last_tick_age_seconds: {last_tick.get('age_seconds')}",
        f"last_tick_processed_count: {last_tick.get('processed_count')}",
        f"watchers_active: {watchers.get('active_count', 0)}",
        f"watchers_total: {watchers.get('count', 0)}",
        f"autonomy_enabled: {safety.get('autonomy_enabled')}",
        f"autonomy_level: {safety.get('autonomy_level')}",
        f"autonomy_paused: {safety.get('autonomy_paused')}",
        f"output: {data.get('output_path')}",
        f"start: {(data.get('controls') or {}).get('start')}",
        f"stop: {(data.get('controls') or {}).get('stop')}",
        f"pause: {(data.get('controls') or {}).get('pause')}",
        f"resume: {(data.get('controls') or {}).get('resume')}",
        f"inspect: {(data.get('controls') or {}).get('inspect')}",
        f"logs: {(data.get('controls') or {}).get('logs')}",
        f"repair: {(data.get('controls') or {}).get('repair')}",
    ]
    for watcher in watchers.get("items") or []:
        lines.append(
            "watcher: "
            f"#{watcher.get('id')} {watcher.get('kind')} {watcher.get('name', '')} "
            f"status={watcher.get('status')}"
        )
    return "\n".join(lines)


def tail_daemon_log(path=None, *, lines=40):
    path = Path(path or RUNTIME_OUTPUT_FILE)
    if not path.exists():
        return {"path": str(path), "exists": False, "lines": []}
    text = path.read_text(encoding="utf-8", errors="replace")
    limit = max(0, int(lines))
    output_lines = [] if limit == 0 else text.splitlines()[-limit:]
    return {"path": str(path), "exists": True, "lines": output_lines}


def format_daemon_log(data):
    if not data.get("exists"):
        return f"daemon log not found: {data.get('path')}"
    body = "\n".join(data.get("lines") or [])
    if body:
        return body
    return f"daemon log is empty: {data.get('path')}"
