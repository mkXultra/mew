import json

from .config import ARCHIVE_DIR
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

    archive_payload = {
        "created_at": current_time,
        "counts": {
            "inbox": len(inbox_archived),
            "outbox": len(outbox_archived),
        },
        "inbox": inbox_archived,
        "outbox": outbox_archived,
    }
    total = len(inbox_archived) + len(outbox_archived)
    archive_path = str(_archive_filename(current_time)) if total else ""

    if not dry_run and total:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        with _archive_filename(current_time).open("w", encoding="utf-8") as handle:
            json.dump(archive_payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        state["inbox"] = inbox_remaining
        state["outbox"] = outbox_remaining

    return {
        "dry_run": bool(dry_run),
        "archive_path": archive_path,
        "archived": archive_payload["counts"],
        "remaining": {
            "inbox": len(inbox_remaining),
            "outbox": len(outbox_remaining),
        },
        "total_archived": total,
    }


def format_archive_result(result):
    lines = [
        f"dry_run: {result.get('dry_run')}",
        f"archived_inbox: {result.get('archived', {}).get('inbox', 0)}",
        f"archived_outbox: {result.get('archived', {}).get('outbox', 0)}",
        f"remaining_inbox: {result.get('remaining', {}).get('inbox', 0)}",
        f"remaining_outbox: {result.get('remaining', {}).get('outbox', 0)}",
    ]
    if result.get("archive_path"):
        lines.append(f"archive_path: {result['archive_path']}")
    return "\n".join(lines)
