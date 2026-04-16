import json

from .config import ARCHIVE_DIR, EFFECT_LOG_FILE
from .timeutil import now_iso


def _archive_filename(current_time):
    safe_time = current_time.replace(":", "").replace("-", "").replace(".", "")
    return ARCHIVE_DIR / f"state-{safe_time}.json"


def _split_archivable(records, should_archive, keep_recent):
    candidates = [record for record in records if should_archive(record)]
    keep_ids = {id(record) for record in candidates[-keep_recent:]} if keep_recent > 0 else set()
    remaining = []
    archived = []
    for record in records:
        if should_archive(record) and id(record) not in keep_ids:
            archived.append(record)
        else:
            remaining.append(record)
    return remaining, archived


def _reviewed_implementation_ids(agent_runs):
    reviewed = set()
    for run in agent_runs:
        if (
            run.get("purpose") == "review"
            and run.get("review_of_run_id") is not None
            and run.get("followup_processed_at")
        ):
            reviewed.add(str(run.get("review_of_run_id")))
    return reviewed


def _retried_run_ids(agent_runs):
    retried = set()
    for run in agent_runs:
        if run.get("parent_run_id") is not None:
            retried.add(str(run.get("parent_run_id")))
    return retried


def _decode_effect_line(line):
    if not line.strip():
        return {"type": "blank_effect_record", "raw": line}
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return {"type": "corrupt_effect_record", "raw": line}
    if not isinstance(record, dict):
        return {"type": "corrupt_effect_record", "raw": line}
    return record


def _split_effect_log(keep_recent):
    if not EFFECT_LOG_FILE.exists():
        return [], [], 0
    try:
        lines = EFFECT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], [], 0
    if keep_recent > 0:
        archived_lines = lines[:-keep_recent]
        remaining_lines = lines[-keep_recent:]
    else:
        archived_lines = lines
        remaining_lines = []
    archived_records = [_decode_effect_line(line) for line in archived_lines]
    return remaining_lines, archived_records, len(lines)


def _agent_run_archivable(run, reviewed_implementation_ids, retried_run_ids):
    status = run.get("status")
    if status not in ("completed", "failed", "dry_run"):
        return False
    purpose = run.get("purpose") or "implementation"
    if purpose == "implementation":
        if status == "completed":
            return str(run.get("id")) in reviewed_implementation_ids
        if status == "failed":
            return str(run.get("id")) in retried_run_ids
        return status == "dry_run"
    if purpose == "review":
        return bool(run.get("followup_processed_at"))
    return True


def archive_state_records(state, keep_recent=100, dry_run=True, current_time=None):
    current_time = current_time or now_iso()
    keep_recent = max(0, int(keep_recent))

    inbox_remaining, inbox_archived = _split_archivable(
        list(state.get("inbox", [])),
        lambda event: bool(event.get("processed_at")),
        keep_recent,
    )
    outbox_remaining, outbox_archived = _split_archivable(
        list(state.get("outbox", [])),
        lambda message: bool(message.get("read_at")),
        keep_recent,
    )
    agent_runs = list(state.get("agent_runs", []))
    reviewed_implementation_ids = _reviewed_implementation_ids(agent_runs)
    retried_run_ids = _retried_run_ids(agent_runs)
    agent_run_remaining, agent_run_archived = _split_archivable(
        agent_runs,
        lambda run: _agent_run_archivable(run, reviewed_implementation_ids, retried_run_ids),
        keep_recent,
    )
    verification_remaining, verification_archived = _split_archivable(
        list(state.get("verification_runs", [])),
        lambda run: True,
        keep_recent,
    )
    write_remaining, write_archived = _split_archivable(
        list(state.get("write_runs", [])),
        lambda run: True,
        keep_recent,
    )
    work_session_remaining, work_session_archived = _split_archivable(
        list(state.get("work_sessions", [])),
        lambda session: session.get("status") == "closed",
        keep_recent,
    )
    effect_remaining_lines, effect_archived, _effect_total = _split_effect_log(keep_recent)

    archive_payload = {
        "created_at": current_time,
        "counts": {
            "inbox": len(inbox_archived),
            "outbox": len(outbox_archived),
            "agent_runs": len(agent_run_archived),
            "verification_runs": len(verification_archived),
            "write_runs": len(write_archived),
            "work_sessions": len(work_session_archived),
            "effects": len(effect_archived),
        },
        "inbox": inbox_archived,
        "outbox": outbox_archived,
        "agent_runs": agent_run_archived,
        "verification_runs": verification_archived,
        "write_runs": write_archived,
        "work_sessions": work_session_archived,
        "effects": effect_archived,
    }
    total = sum(archive_payload["counts"].values())
    archive_path = str(_archive_filename(current_time)) if total else ""

    if not dry_run and total:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        with _archive_filename(current_time).open("w", encoding="utf-8") as handle:
            json.dump(archive_payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        state["inbox"] = inbox_remaining
        state["outbox"] = outbox_remaining
        state["agent_runs"] = agent_run_remaining
        state["verification_runs"] = verification_remaining
        state["write_runs"] = write_remaining
        state["work_sessions"] = work_session_remaining
        if effect_archived:
            EFFECT_LOG_FILE.write_text(
                ("\n".join(effect_remaining_lines) + "\n") if effect_remaining_lines else "",
                encoding="utf-8",
            )

    return {
        "dry_run": bool(dry_run),
        "archive_path": archive_path,
        "archived": archive_payload["counts"],
        "remaining": {
            "inbox": len(inbox_remaining),
            "outbox": len(outbox_remaining),
            "agent_runs": len(agent_run_remaining),
            "verification_runs": len(verification_remaining),
            "write_runs": len(write_remaining),
            "work_sessions": len(work_session_remaining),
            "effects": len(effect_remaining_lines),
        },
        "total_archived": total,
    }


def format_archive_result(result):
    sections = ("inbox", "outbox", "agent_runs", "verification_runs", "write_runs", "work_sessions", "effects")
    lines = [f"dry_run: {result.get('dry_run')}"]
    for section in sections:
        lines.append(f"archived_{section}: {result.get('archived', {}).get(section, 0)}")
    for section in sections:
        lines.append(f"remaining_{section}: {result.get('remaining', {}).get(section, 0)}")
    if result.get("archive_path"):
        lines.append(f"archive_path: {result['archive_path']}")
    return "\n".join(lines)
