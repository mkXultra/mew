import hashlib
import json

from .config import MODEL_TRACE_FILE


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def _prompt_digest(prompt):
    text = prompt or ""
    return {
        "prompt_chars": len(text),
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
    }


def append_model_trace(
    *,
    at,
    phase,
    event,
    backend,
    model,
    status,
    prompt="",
    plan=None,
    reason="",
    error="",
    include_prompt=True,
):
    MODEL_TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": at,
        "phase": phase,
        "event_id": event.get("id") if isinstance(event, dict) else None,
        "event_type": event.get("type") if isinstance(event, dict) else "",
        "backend": backend,
        "model": model,
        "status": status,
        **_prompt_digest(prompt),
    }
    if include_prompt and prompt:
        record["prompt"] = prompt
    if plan is not None:
        record["plan"] = _jsonable(plan)
    if reason:
        record["reason"] = str(reason)
    if error:
        record["error"] = str(error)

    with MODEL_TRACE_FILE.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return record


def read_model_traces(limit=20, include_prompt=False):
    if limit <= 0 or not MODEL_TRACE_FILE.exists():
        return []
    try:
        lines = MODEL_TRACE_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                record = {"status": "corrupt", "raw": line}
        except json.JSONDecodeError:
            record = {"status": "corrupt", "raw": line}
        if not include_prompt:
            record.pop("prompt", None)
        records.append(record)
    return records[-limit:]
