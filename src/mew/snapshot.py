from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re

from .config import STATE_DIR, STATE_FILE
from .state import default_state, merge_defaults, migrate_state, reconcile_next_ids, state_digest
from .tasks import find_task
from .timeutil import now_iso
from .work_session import build_work_session_resume, find_work_session


SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_ROOT = STATE_DIR / "sessions"
_SNAPSHOT_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class WorkSessionSnapshot:
    schema_version: int
    session_id: str
    task_id: str
    state_hash: str
    last_effect_id: int
    closed_at: str | None
    saved_at: str
    working_memory: dict
    touched_files: list[str]
    pending_approvals: list[dict]
    continuity_score: str | None
    continuity_status: str | None
    continuity_recommendation: dict | None
    active_memory_refs: list[str]
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self):
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        known = {field_name for field_name in cls.__dataclass_fields__ if field_name != "unknown_fields"}
        unknown = {key: value for key, value in data.items() if key not in known}
        return cls(
            schema_version=int(data.get("schema_version") or 0),
            session_id=str(data.get("session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            state_hash=str(data.get("state_hash") or ""),
            last_effect_id=int(data.get("last_effect_id") or 0),
            closed_at=data.get("closed_at"),
            saved_at=str(data.get("saved_at") or ""),
            working_memory=dict(data.get("working_memory") or {}),
            touched_files=list(data.get("touched_files") or []),
            pending_approvals=list(data.get("pending_approvals") or []),
            continuity_score=data.get("continuity_score"),
            continuity_status=data.get("continuity_status"),
            continuity_recommendation=(
                dict(data.get("continuity_recommendation") or {})
                if data.get("continuity_recommendation") is not None
                else None
            ),
            active_memory_refs=list(data.get("active_memory_refs") or []),
            unknown_fields=unknown,
        )


@dataclass(frozen=True)
class SnapshotLoadResult:
    snapshot: WorkSessionSnapshot
    usable: bool
    drift_notes: list[str]
    partial_reasons: list[str]
    path: str


def _base_dir_path(base_dir):
    return Path(base_dir).expanduser().resolve()


def _snapshot_session_dir(session_id, *, base_dir="."):
    safe_id = _SNAPSHOT_ID_RE.sub("_", str(session_id or "")).strip("._") or "unknown"
    return _base_dir_path(base_dir) / SNAPSHOT_ROOT / safe_id


def snapshot_path(session_id, *, base_dir="."):
    return _snapshot_session_dir(session_id, base_dir=base_dir) / "snapshot.json"


def _load_state(base_dir="."):
    path = _base_dir_path(base_dir) / STATE_FILE
    if not path.exists():
        return default_state()
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    return reconcile_next_ids(merge_defaults(migrate_state(state), default_state()))


def _last_effect_id(state):
    latest = 0
    for effect in state.get("runtime_effects") or []:
        if not isinstance(effect, dict):
            continue
        try:
            latest = max(latest, int(effect.get("id") or 0))
        except (TypeError, ValueError):
            continue
    return latest


def _active_memory_refs(active_memory):
    refs = []
    for item in (active_memory or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        ref = item.get("id") or item.get("path") or item.get("name") or item.get("key")
        if ref:
            refs.append(str(ref))
    return refs


def take_snapshot(session_id, *, state=None, base_dir=".", current_time=None):
    state = reconcile_next_ids(merge_defaults(migrate_state(state or _load_state(base_dir)), default_state()))
    session = find_work_session(state, session_id)
    if not session:
        raise ValueError(f"work session not found: {session_id}")
    task = find_task(state, session.get("task_id"))
    resume = build_work_session_resume(session, task=task, state=state, current_time=current_time) or {}
    continuity = resume.get("continuity") or {}
    return WorkSessionSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        session_id=str(session.get("id") or ""),
        task_id=str(session.get("task_id") or ""),
        state_hash=state_digest(state),
        last_effect_id=_last_effect_id(state),
        closed_at=session.get("updated_at") if session.get("status") == "closed" else None,
        saved_at=current_time or now_iso(),
        working_memory=dict(resume.get("working_memory") or {}),
        touched_files=list(resume.get("files_touched") or []),
        pending_approvals=list(resume.get("pending_approvals") or []),
        continuity_score=continuity.get("score"),
        continuity_status=continuity.get("status"),
        continuity_recommendation=continuity.get("recommendation") or None,
        active_memory_refs=_active_memory_refs(resume.get("active_memory") or {}),
    )


def save_snapshot(snapshot, *, base_dir="."):
    path = snapshot_path(snapshot.session_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp_file.open("w", encoding="utf-8") as handle:
        json.dump(snapshot.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_file, path)
    return path


def load_snapshot(session_id, *, base_dir=".", state=None):
    path = snapshot_path(session_id, base_dir=base_dir)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        snapshot = WorkSessionSnapshot.from_dict(json.load(handle))

    usable = True
    drift_notes = []
    partial_reasons = []
    if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
        usable = False
        partial_reasons.append(
            f"snapshot schema {snapshot.schema_version} is not current {SNAPSHOT_SCHEMA_VERSION}"
        )

    current_state = reconcile_next_ids(merge_defaults(migrate_state(state or _load_state(base_dir)), default_state()))
    current_hash = state_digest(current_state)
    if snapshot.state_hash and current_hash != snapshot.state_hash:
        usable = False
        drift_notes.append("state_hash differs from current state")
        partial_reasons.append("snapshot may still be useful, but current state changed after it was saved")

    return SnapshotLoadResult(
        snapshot=snapshot,
        usable=usable,
        drift_notes=drift_notes,
        partial_reasons=partial_reasons,
        path=str(path),
    )


def upgrade_snapshot(snapshot, target=SNAPSHOT_SCHEMA_VERSION):
    if snapshot.schema_version == target:
        return snapshot
    raise ValueError(f"cannot upgrade snapshot schema {snapshot.schema_version} to {target}")
