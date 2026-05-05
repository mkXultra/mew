"""Implementation-lane transcript helpers."""

from __future__ import annotations

from .types import ImplementLaneTranscriptEvent, TranscriptEventKind


def lane_artifact_namespace(*, work_session_id: object, task_id: object, lane: object) -> str:
    """Return a stable artifact namespace for implementation-lane outputs."""

    safe_session = _safe_part(work_session_id, default="session")
    safe_task = _safe_part(task_id, default="task")
    safe_lane = _safe_part(lane, default="implement_v1")
    return f"implement-lane/{safe_lane}/{safe_session}/{safe_task}"


def build_transcript_event(
    *,
    kind: TranscriptEventKind,
    lane: object,
    turn_id: object,
    index: int,
    lane_attempt_id: object = "",
    payload: dict[str, object] | None = None,
) -> ImplementLaneTranscriptEvent:
    """Build a replayable lane-scoped transcript event."""

    safe_lane = _safe_part(lane, default="implement_v1")
    safe_turn = _safe_part(turn_id, default="turn")
    safe_attempt = _safe_part(lane_attempt_id, default="")
    event_id_prefix = f"{safe_lane}:{safe_attempt}:{safe_turn}" if safe_attempt else f"{safe_lane}:{safe_turn}"
    return ImplementLaneTranscriptEvent(
        kind=kind,
        lane=safe_lane,
        turn_id=safe_turn,
        event_id=f"{event_id_prefix}:{kind}:{max(0, int(index))}",
        payload=dict(payload or {}),
    )


def _safe_part(value: object, *, default: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return default
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or default


__all__ = ["build_transcript_event", "lane_artifact_namespace"]
