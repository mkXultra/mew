from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

def elapsed_hours(since, until):
    start = parse_time(since)
    end = parse_time(until)
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)
