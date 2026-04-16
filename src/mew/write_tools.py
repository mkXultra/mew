import difflib
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
        try:
            roots.append(path.resolve(strict=True))
            continue
        except OSError:
            pass
        try:
            parent = path.parent.resolve(strict=True)
        except OSError:
            continue
        roots.append(parent / path.name)
    return roots


def resolve_allowed_write_path(path, allowed_roots, create=False):
    roots = normalize_allowed_write_roots(allowed_roots)
    if not roots:
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
        parent = candidate.parent.resolve(strict=True)
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


def _unified_diff(path, before, after, max_chars=DEFAULT_DIFF_MAX_CHARS):
    display_path = str(path).lstrip("/")
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{display_path}",
        tofile=f"b/{display_path}",
    )
    return clip_output("".join(lines), max_chars)


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
    if changed and not dry_run:
        _atomic_write_text(resolved, after)

    return {
        "operation": "write_file",
        "path": str(resolved),
        "created": not existed,
        "changed": changed,
        "dry_run": bool(dry_run),
        "written": bool(changed and not dry_run),
        "size": len(after),
        "diff": _unified_diff(resolved, before, after),
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

    resolved = resolve_allowed_write_path(path, allowed_roots, create=False)
    before = _read_text_if_exists(resolved)
    count = before.count(old)
    if count == 0:
        raise ValueError("old text was not found")
    if count > 1 and not replace_all:
        raise ValueError(f"old text matched {count} times; pass --replace-all to replace all matches")

    after = before.replace(old, new) if replace_all else before.replace(old, new, 1)
    if len(after) > max_chars:
        raise ValueError(f"edited content is too large: {len(after)} chars; max={max_chars}")
    started_at = now_iso()
    if before != after and not dry_run:
        _atomic_write_text(resolved, after)

    return {
        "operation": "edit_file",
        "path": str(resolved),
        "matched": count,
        "replaced": count if replace_all else 1,
        "changed": before != after,
        "dry_run": bool(dry_run),
        "written": bool(before != after and not dry_run),
        "diff": _unified_diff(resolved, before, after),
        "started_at": started_at,
        "finished_at": now_iso(),
    }


def summarize_write_result(result):
    lines = [
        f"{result.get('operation')} {result.get('path')}",
        f"changed: {result.get('changed')} dry_run: {result.get('dry_run')} written: {result.get('written')}",
    ]
    if result.get("created"):
        lines.append("created: True")
    if result.get("matched") is not None:
        lines.append(f"matched: {result.get('matched')} replaced: {result.get('replaced')}")
    if result.get("diff"):
        lines.extend(["diff:", result["diff"]])
    return "\n".join(lines)
