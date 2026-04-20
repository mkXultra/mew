import difflib
import hashlib
import os
from pathlib import Path
import tempfile

from .read_tools import _is_relative_to, ensure_not_sensitive
from .tasks import clip_output
from .timeutil import now_iso


DEFAULT_WRITE_MAX_CHARS = 100000
DEFAULT_DIFF_MAX_CHARS = 12000


def normalize_allowed_write_roots(allowed_roots):
    roots = []
    for root in allowed_roots or []:
        path = Path(root).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        roots.append(path.resolve(strict=False))
    return roots


def resolve_allowed_write_path(path, allowed_roots, create=False):
    roots = normalize_allowed_write_roots(allowed_roots)
    if not roots:
        if allowed_roots:
            raise ValueError(
                "no allowed write roots could be resolved; create the parent directory or pass an existing directory"
            )
        raise ValueError("write is disabled; pass --allow-write PATH")

    candidate = Path(path or "").expanduser()
    if not str(candidate):
        raise ValueError("write path is empty")
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    if candidate.exists():
        resolved = candidate.resolve(strict=True)
        if resolved.is_dir():
            raise ValueError(f"path is a directory: {resolved}")
        ensure_not_sensitive(resolved, verb="write")
        for root in roots:
            if resolved == root or _is_relative_to(resolved, root):
                return resolved
    else:
        if not create:
            raise ValueError(f"path does not exist: {candidate}; pass --create to create it")
        parent = candidate.parent.resolve(strict=False)
        resolved = parent / candidate.name
        ensure_not_sensitive(resolved, verb="write")
        for root in roots:
            if parent == root or _is_relative_to(parent, root):
                return resolved
            if resolved == root:
                return resolved

    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"path is outside allowed write roots: {candidate}; allowed={allowed}")


def _read_text_if_exists(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sha256_file(path):
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_diff_line_counts(before, after):
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    added = 0
    removed = 0
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed += before_end - before_start
        added += after_end - after_start
    return {"added": added, "removed": removed}


def _unified_diff_text(path, before, after):
    display_path = str(path).lstrip("/")
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{display_path}",
        tofile=f"b/{display_path}",
    )
    return "".join(lines)

def _atomic_write_text(path, content):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(content)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _atomic_write_temp_paths(path):
    if not path.parent.exists():
        return []
    return sorted(str(candidate) for candidate in path.parent.glob(f".{path.name}.*.tmp"))


def _planned_write_after_text(tool, parameters, before):
    parameters = parameters or {}
    if tool == "write_file":
        content = parameters.get("content", "")
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        return content
    if tool == "edit_file":
        old = parameters.get("old")
        new = parameters.get("new")
        if not isinstance(old, str) or old == "":
            raise ValueError("old text must be a non-empty string")
        if not isinstance(new, str):
            raise ValueError("new text must be a string")
        count = before.count(old)
        if count == 0:
            raise ValueError(
                "old text was not found; confirm the exact existing text before retrying; "
                "use read_file on the latest target window first"
            )
        if count > 1 and not parameters.get("replace_all"):
            raise ValueError(
                f"old text matched {count} times; pass --replace-all to replace all matches "
                "or include surrounding context to narrow the match"
            )
        return before.replace(old, new) if parameters.get("replace_all") else before.replace(old, new, 1)
    if tool == "edit_file_hunks":
        edits = parameters.get("edits")
        return _apply_edit_hunks(before, edits)
    raise ValueError(f"unsupported write tool: {tool}")


def _normalize_edit_hunk(index, edit):
    if not isinstance(edit, dict):
        raise ValueError(f"edit hunk #{index + 1} must be an object with old/new strings")
    old = edit.get("old")
    new = edit.get("new")
    if not isinstance(old, str) or old == "":
        raise ValueError(f"edit hunk #{index + 1} old text must be a non-empty string")
    if not isinstance(new, str):
        raise ValueError(f"edit hunk #{index + 1} new text must be a string")
    return {"old": old, "new": new}


def _apply_edit_hunks(before, edits):
    edits = edits if isinstance(edits, list) else []
    if not edits:
        raise ValueError("edit_file_hunks requires a non-empty edits list")

    placements = []
    for index, raw_edit in enumerate(edits):
        edit = _normalize_edit_hunk(index, raw_edit)
        old = edit["old"]
        count = before.count(old)
        if count == 0:
            raise ValueError(
                f"edit hunk #{index + 1} old text was not found; confirm the exact existing text before retrying; "
                "use read_file on the latest target window first"
            )
        if count > 1:
            raise ValueError(
                f"edit hunk #{index + 1} old text matched {count} times; include more surrounding context to narrow the match"
            )
        start = before.find(old)
        placements.append(
            {
                "index": index,
                "old": old,
                "new": edit["new"],
                "start": start,
                "end": start + len(old),
            }
        )

    placements.sort(key=lambda item: (item["start"], item["end"], item["index"]))
    for previous, current in zip(placements, placements[1:]):
        if current["start"] < previous["end"]:
            raise ValueError(
                "edit hunks overlap in the target file; merge them into one hunk or use surrounding context that makes them disjoint"
            )

    pieces = []
    cursor = 0
    for placement in placements:
        pieces.append(before[cursor : placement["start"]])
        pieces.append(placement["new"])
        cursor = placement["end"]
    pieces.append(before[cursor:])
    return "".join(pieces)


def build_write_intent(tool, parameters):
    """Build a small pre-execution write intent for crash recovery."""
    parameters = parameters or {}
    path = parameters.get("path") or ""
    resolved = resolve_allowed_write_path(
        path,
        parameters.get("allowed_write_roots") or [],
        create=tool == "write_file" and bool(parameters.get("create")),
    )
    existed = resolved.exists()
    before = _read_text_if_exists(resolved) if existed else ""
    after = _planned_write_after_text(tool, parameters, before)
    return {
        "schema_version": 1,
        "kind": "file_write",
        "operation": tool,
        "path": str(resolved),
        "apply_requested": bool(parameters.get("apply")),
        "create": tool == "write_file" and bool(parameters.get("create")),
        "before_existed": existed,
        "before_sha256": _sha256_text(before),
        "before_size": len(before),
        "expected_sha256": _sha256_text(after),
        "expected_size": len(after),
        "verify_expected": bool(parameters.get("verify_command")),
        "verify_command": parameters.get("verify_command") or "",
        "verify_cwd": parameters.get("verify_cwd") or parameters.get("cwd") or ".",
        "prepared_at": now_iso(),
    }


def classify_write_intent_world_state(intent):
    intent = intent or {}
    path = Path(intent.get("path") or "")
    if not path.is_absolute():
        return {
            "state": "unknown",
            "reason": "write intent path is missing or not absolute",
        }
    exists = path.exists()
    current_sha = _sha256_file(path) if exists else None
    temp_paths = _atomic_write_temp_paths(path)
    before_existed = bool(intent.get("before_existed"))
    before_sha = intent.get("before_sha256")
    expected_sha = intent.get("expected_sha256")
    if exists and current_sha == expected_sha:
        state = "completed_externally"
        reason = "target already matches the intended post-write content"
    elif not exists and not before_existed and not temp_paths:
        state = "not_started"
        reason = "target still does not exist and no atomic temp file remains"
    elif exists and current_sha == before_sha and not temp_paths:
        state = "not_started"
        reason = "target still matches the pre-write hash"
    elif temp_paths:
        state = "partial"
        reason = "atomic write temp file remains near the target"
    else:
        state = "target_diverged"
        reason = "target no longer matches the pre-write or intended post-write hash"
    return {
        "state": state,
        "path": str(path),
        "exists": exists,
        "current_sha256": current_sha,
        "before_sha256": before_sha,
        "expected_sha256": expected_sha,
        "temp_paths": temp_paths,
        "reason": reason,
    }


def snapshot_write_path(path, allowed_roots, create=False):
    resolved = resolve_allowed_write_path(path, allowed_roots, create=create)
    existed = resolved.exists()
    return {
        "path": str(resolved),
        "existed": existed,
        "content": _read_text_if_exists(resolved) if existed else "",
        "created_at": now_iso(),
    }


def restore_write_snapshot(snapshot):
    path = Path(snapshot.get("path") or "")
    if not path.is_absolute():
        raise ValueError("rollback snapshot path must be absolute")

    existed = bool(snapshot.get("existed"))
    if existed:
        _atomic_write_text(path, snapshot.get("content") or "")
        removed = False
    else:
        path.unlink(missing_ok=True)
        removed = True

    return {
        "path": str(path),
        "restored": True,
        "removed_created_file": removed,
        "restored_at": now_iso(),
    }


def write_file(path, content, allowed_roots, create=False, dry_run=False, max_chars=DEFAULT_WRITE_MAX_CHARS):
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    if len(content) > max_chars:
        raise ValueError(f"content is too large: {len(content)} chars; max={max_chars}")

    resolved = resolve_allowed_write_path(path, allowed_roots, create=create)
    existed = resolved.exists()
    before = _read_text_if_exists(resolved)
    after = content
    changed = before != after
    started_at = now_iso()
    diff = _unified_diff_text(resolved, before, after)
    if changed and not dry_run:
        if create:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(resolved, after)

    return {
        "operation": "write_file",
        "path": str(resolved),
        "created": not existed,
        "changed": changed,
        "dry_run": bool(dry_run),
        "written": bool(changed and not dry_run),
        "size": len(after),
        "diff": clip_output(diff, DEFAULT_DIFF_MAX_CHARS),
        "diff_stats": _text_diff_line_counts(before, after),
        "started_at": started_at,
        "finished_at": now_iso(),
    }


def edit_file(
    path,
    old,
    new,
    allowed_roots,
    replace_all=False,
    dry_run=False,
    max_chars=DEFAULT_WRITE_MAX_CHARS,
):
    if not isinstance(old, str) or old == "":
        raise ValueError("old text must be a non-empty string")
    if not isinstance(new, str):
        raise ValueError("new text must be a string")

    try:
        resolved = resolve_allowed_write_path(path, allowed_roots, create=False)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("path does not exist:"):
            missing_path = message.split("path does not exist:", 1)[1].split(";", 1)[0].strip()
            raise ValueError(
                f"path does not exist: {missing_path}; use write_file with --create/create=True to create new files"
            ) from exc
        raise
    before = _read_text_if_exists(resolved)
    count = before.count(old)
    if count == 0:
        raise ValueError(
            "old text was not found; confirm the exact existing text before retrying; "
            "use read_file on the latest target window first"
        )
    if count > 1 and not replace_all:
        raise ValueError(
            f"old text matched {count} times; pass --replace-all to replace all matches "
            "or include surrounding context to narrow the match"
        )

    after = before.replace(old, new) if replace_all else before.replace(old, new, 1)
    changed = before != after
    no_op_reason = ""
    if not changed:
        no_op_reason = "old and new text are identical" if old == new else "replacement produced no file changes"
    edit_size = max(len(new), abs(len(after) - len(before)))
    if edit_size > max_chars:
        raise ValueError(f"edited content is too large: {edit_size} chars; max={max_chars}")
    started_at = now_iso()
    diff = _unified_diff_text(resolved, before, after)
    if changed and not dry_run:
        _atomic_write_text(resolved, after)

    result = {
        "operation": "edit_file",
        "path": str(resolved),
        "matched": count,
        "replaced": count if replace_all else 1,
        "changed": changed,
        "no_op": not changed,
        "dry_run": bool(dry_run),
        "written": bool(changed and not dry_run),
        "diff": clip_output(diff, DEFAULT_DIFF_MAX_CHARS),
        "diff_stats": _text_diff_line_counts(before, after),
        "started_at": started_at,
        "finished_at": now_iso(),
    }
    if no_op_reason:
        result["no_op_reason"] = no_op_reason
    return result


def edit_file_hunks(path, edits, allowed_roots, dry_run=False, max_chars=DEFAULT_WRITE_MAX_CHARS):
    try:
        resolved = resolve_allowed_write_path(path, allowed_roots, create=False)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("path does not exist:"):
            missing_path = message.split("path does not exist:", 1)[1].split(";", 1)[0].strip()
            raise ValueError(
                f"path does not exist: {missing_path}; use write_file with --create/create=True to create new files"
            ) from exc
        raise

    before = _read_text_if_exists(resolved)
    after = _apply_edit_hunks(before, edits)
    changed = before != after
    no_op_reason = ""
    if not changed:
        no_op_reason = "all hunk replacements produced no file changes"
    edit_size = max(len(after) - len(before), *(len(edit.get("new") or "") for edit in (edits or [])), 0)
    if edit_size > max_chars:
        raise ValueError(f"edited content is too large: {edit_size} chars; max={max_chars}")
    started_at = now_iso()
    diff = _unified_diff_text(resolved, before, after)
    if changed and not dry_run:
        _atomic_write_text(resolved, after)

    result = {
        "operation": "edit_file_hunks",
        "path": str(resolved),
        "hunk_count": len(edits or []),
        "changed": changed,
        "no_op": not changed,
        "dry_run": bool(dry_run),
        "written": bool(changed and not dry_run),
        "diff": clip_output(diff, DEFAULT_DIFF_MAX_CHARS),
        "diff_stats": _text_diff_line_counts(before, after),
        "started_at": started_at,
        "finished_at": now_iso(),
    }
    if no_op_reason:
        result["no_op_reason"] = no_op_reason
    return result


def summarize_write_result(result):
    lines = [
        f"{result.get('operation')} {result.get('path')}",
        f"changed: {result.get('changed')} dry_run: {result.get('dry_run')} written: {result.get('written')}",
    ]
    if result.get("created"):
        lines.append("created: True")
    if result.get("matched") is not None:
        lines.append(f"matched: {result.get('matched')} replaced: {result.get('replaced')}")
    if result.get("hunk_count") is not None:
        lines.append(f"hunks: {result.get('hunk_count')}")
    if result.get("no_op"):
        no_op_reason = result.get('no_op_reason') or 'replacement produced no file changes'
        if no_op_reason == 'old and new text are identical':
            no_op_reason = 'old and new text are identical; file content is unchanged'
        lines.append(f"no_op: {no_op_reason}")
        lines.append("next: re-read the target window and retry with an edit that changes file content")
    if result.get("diff"):
        lines.extend(["diff:", result["diff"]])
    return "\n".join(lines)
