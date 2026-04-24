import os
import time
from datetime import datetime, timezone


def _initial_dilation_multiplier():
    raw = os.environ.get("MEW_TIME_DILATION")
    if not raw:
        return 1.0
    try:
        multiplier = float(raw)
    except ValueError:
        return 1.0
    return multiplier if multiplier > 0 else 1.0


_DILATION_MULTIPLIER = _initial_dilation_multiplier()
_DILATION_START_REAL = time.time()
_DILATION_START_LOGICAL = _DILATION_START_REAL


def enable_dilation(multiplier, *, start_real=None, start_logical=None):
    multiplier = float(multiplier)
    if multiplier <= 0:
        raise ValueError("dilation multiplier must be positive")
    real = time.time() if start_real is None else float(start_real)
    logical = real if start_logical is None else float(start_logical)

    global _DILATION_MULTIPLIER, _DILATION_START_REAL, _DILATION_START_LOGICAL
    _DILATION_MULTIPLIER = multiplier
    _DILATION_START_REAL = real
    _DILATION_START_LOGICAL = logical


def reset_dilation():
    enable_dilation(1.0)


def dilation_multiplier():
    return _DILATION_MULTIPLIER


def _now_seconds():
    current = time.time()
    if _DILATION_MULTIPLIER == 1.0:
        return current
    return _DILATION_START_LOGICAL + ((current - _DILATION_START_REAL) * _DILATION_MULTIPLIER)


def now_iso():
    return datetime.fromtimestamp(_now_seconds(), timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_date_iso():
    return datetime.fromtimestamp(_now_seconds(), timezone.utc).date().isoformat()

def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed

def elapsed_hours(since, until):
    start = parse_time(since)
    end = parse_time(until)
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)
