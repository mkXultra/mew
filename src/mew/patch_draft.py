import difflib
import hashlib
import json
from pathlib import Path

from .read_tools import _is_relative_to
from .test_discovery import convention_test_path_for_mew_source, normalize_work_path


PATCH_DRAFT_VALIDATOR_VERSION = 1
PATCH_BLOCKER_RECOVERY_ACTIONS = {
    "missing_exact_cached_window_texts": "refresh_cached_window",
    "cached_window_incomplete": "refresh_cached_window",
    "cached_window_text_truncated": "refresh_cached_window",
    "stale_cached_window_text": "refresh_cached_window",
    "old_text_not_found": "refresh_cached_window",
    "ambiguous_old_text_match": "narrow_old_text",
    "overlapping_hunks": "merge_or_split_hunks",
    "no_material_change": "revise_patch",
    "unpaired_source_edit_blocked": "add_paired_test_edit",
    "write_policy_violation": "revise_patch_scope",
    "model_returned_non_schema": "retry_with_schema",
    "model_returned_refusal": "inspect_refusal",
    "review_rejected": "revise_patch_from_review_findings",
    "task_goal_term_missing": "revise_patch_scope",
    "duplicated_adjacent_context": "narrow_old_text",
}


def sha1_text(text):
    return "sha1:" + hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_patch_blocker(todo_id, code, *, path="", line_start=None, line_end=None, detail=""):
    blocker = {
        "kind": "patch_blocker",
        "todo_id": str(todo_id or "").strip(),
        "code": str(code or "").strip(),
        "detail": str(detail or "").strip(),
        "recovery_action": PATCH_BLOCKER_RECOVERY_ACTIONS.get(str(code or "").strip(), "inspect_blocker"),
    }
    normalized_path = normalize_work_path(path)
    if normalized_path:
        blocker["path"] = normalized_path
    if isinstance(line_start, int) and line_start > 0:
        blocker["line_start"] = line_start
    if isinstance(line_end, int) and line_end > 0:
        blocker["line_end"] = line_end
    return blocker


def compile_patch_draft(*, todo, proposal, cached_windows, live_files, allowed_write_roots=None):
    todo = _normalize_todo(todo)
    todo_id = todo.get("id") or ""
    normalized = _normalize_proposal(proposal, todo_id=todo_id)
    if normalized.get("kind") == "patch_blocker":
        return normalized

    edited_paths = [item["path"] for item in normalized["files"]]
    goal_blocker = _validate_required_terms(todo, normalized)
    if goal_blocker:
        return goal_blocker
    pairing_blocker = _validate_pairing(
        todo,
        edited_paths,
        allowed_write_roots=allowed_write_roots,
    )
    if pairing_blocker:
        return pairing_blocker

    compiled_files = []
    diff_parts = []
    for proposal_file in normalized["files"]:
        compiled_file = _compile_file(
            todo=todo,
            proposal_file=proposal_file,
            cached_windows=cached_windows,
            live_files=live_files,
        )
        if compiled_file.get("kind") == "patch_blocker":
            return compiled_file
        compiled_files.append(compiled_file)
        diff_parts.append(compiled_file.pop("_unified_diff"))

    payload = {
        "todo_id": todo_id,
        "summary": normalized["summary"],
        "files": compiled_files,
    }
    draft_id = _stable_artifact_id("draft", payload)
    return {
        "kind": "patch_draft",
        "id": draft_id,
        "todo_id": todo_id,
        "status": "validated",
        "summary": normalized["summary"],
        "files": compiled_files,
        "unified_diff": "".join(part for part in diff_parts if part),
        "validator_version": PATCH_DRAFT_VALIDATOR_VERSION,
    }


def compile_patch_draft_previews(patch_draft, *, allowed_write_roots=None):
    """
    Convert a validated PatchDraft into dry-run write action specs for the existing
    write-action execution path (edit_file/edit_file_hunks payload shape), not
    write_tool result objects.
    """
    patch_draft = patch_draft if isinstance(patch_draft, dict) else {}
    if not patch_draft:
        return build_patch_blocker(
            "",
            "model_returned_non_schema",
            detail="patch_draft must be a patch artifact object",
        )

    kind = str(patch_draft.get("kind") or "").strip()
    todo_id = str(patch_draft.get("todo_id") or patch_draft.get("id") or "").strip()
    if kind == "patch_blocker":
        return patch_draft
    if kind != "patch_draft":
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="patch_draft.kind must be patch_draft or patch_blocker",
        )
    if patch_draft.get("status") != "validated":
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="patch_draft must be validated before preview translation",
        )

    files = patch_draft.get("files")
    if not isinstance(files, list) or not files:
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="patch_draft.files must be a non-empty array",
        )
    if not allowed_write_roots:
        return build_patch_blocker(
            todo_id,
            "write_policy_violation",
            detail="allowed_write_roots is required for preview translation",
        )

    previews = []
    seen_paths = set()
    for file_item in files:
        if not isinstance(file_item, dict):
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail="patch_draft.files entry must be an object",
            )
        path = normalize_work_path(file_item.get("path"))
        if not path:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail="patch_draft.files item missing path",
            )
        if path in seen_paths:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"patch_draft.files has duplicate path: {path}",
                path=path,
            )
        if not _path_under_allowed_roots(path, allowed_write_roots):
            return build_patch_blocker(
                todo_id,
                "write_policy_violation",
                path=path,
                detail="preview path is outside allowed_write_roots",
            )

        file_kind = str(file_item.get("kind") or "").strip()
        if file_kind not in {"edit_file", "edit_file_hunks"}:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"patch_draft.files[{path}] kind must be edit_file or edit_file_hunks",
            )

        raw_edits = file_item.get("edits")
        if not isinstance(raw_edits, list) or not raw_edits:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"patch_draft.files[{path}] edits must be a non-empty array",
                path=path,
            )

        edits = []
        for edit in raw_edits:
            if not isinstance(edit, dict):
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"patch_draft.files[{path}] edit must be an object",
                    path=path,
                )
            old = edit.get("old")
            new = edit.get("new")
            if not isinstance(old, str) or old == "":
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"patch_draft.files[{path}] edit old must be a non-empty string",
                    path=path,
                )
            if not isinstance(new, str):
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"patch_draft.files[{path}] edit new must be a string",
                    path=path,
                )
            edits.append({"old": old, "new": new})

        if file_kind == "edit_file" and len(edits) != 1:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
            detail=f"patch_draft.files[{path}] edit_file must contain exactly one edit",
                path=path,
            )
        seen_paths.add(path)

        preview = {
            "type": file_kind,
            "path": path,
            "apply": False,
            "dry_run": True,
        }
        if file_kind == "edit_file":
            preview["old"] = edits[0]["old"]
            preview["new"] = edits[0]["new"]
        else:
            preview["edits"] = edits
        previews.append(preview)

    return previews


def review_patch_draft_previews(patch_draft, review, *, allowed_write_roots=None):
    previews = compile_patch_draft_previews(
        patch_draft,
        allowed_write_roots=allowed_write_roots,
    )
    if isinstance(previews, dict) and previews.get("kind") == "patch_blocker":
        return previews

    patch_draft = patch_draft if isinstance(patch_draft, dict) else {}
    todo_id = str(patch_draft.get("todo_id") or patch_draft.get("id") or "").strip()
    review = review if isinstance(review, dict) else {}
    status = str(review.get("status") or "").strip().casefold().replace("-", "_").replace(" ", "_")
    summary = str(review.get("summary") or review.get("reason") or "").strip()
    findings = _normalize_review_findings(review.get("findings"))

    if not status:
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="review.status must be accepted or rejected",
        )

    if status in {"rejected", "reject", "request_changes", "changes_requested"}:
        detail = summary or "patch draft review rejected"
        blocker = build_patch_blocker(todo_id, "review_rejected", detail=detail)
        blocker["patch_draft_id"] = str(patch_draft.get("id") or "").strip()
        blocker["findings"] = findings
        blocker["review"] = {
            "status": status,
            "summary": summary,
        }
        return blocker

    if status and status not in {"accepted", "accept", "approved", "approve", "pass", "no_findings"}:
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="review.status must be accepted or rejected",
        )

    return previews


def _normalize_todo(todo):
    todo = todo if isinstance(todo, dict) else {}
    source = todo.get("source") if isinstance(todo.get("source"), dict) else {}
    return {
        "id": str(todo.get("id") or "").strip(),
        "source": {
            "target_paths": [
                normalize_work_path(path)
                for path in (source.get("target_paths") or [])
                if normalize_work_path(path)
            ],
            "required_terms": _normalize_required_terms(source.get("required_terms") or []),
        },
    }


def _normalize_required_terms(terms):
    normalized = []
    seen = set()
    for term in terms or []:
        value = str(term or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _proposal_search_text(proposal):
    pieces = [str(proposal.get("summary") or "")]
    for file_item in proposal.get("files") or []:
        if not isinstance(file_item, dict):
            continue
        pieces.append(str(file_item.get("path") or ""))
        for edit in file_item.get("edits") or []:
            if not isinstance(edit, dict):
                continue
            pieces.append(str(edit.get("old") or ""))
            pieces.append(str(edit.get("new") or ""))
    return "\n".join(pieces).casefold()


def _required_term_variants(term):
    normalized = str(term or "").strip().casefold()
    if not normalized:
        return []
    variants = {normalized}
    if "-" in normalized or "_" in normalized:
        variants.add(normalized.replace("-", "_"))
        variants.add(normalized.replace("_", "-"))
    return sorted(variants)


def _validate_required_terms(todo, proposal):
    required_terms = list(((todo.get("source") or {}).get("required_terms") or []))
    if not required_terms:
        return {}
    proposal_text = _proposal_search_text(proposal)
    missing = [
        term
        for term in required_terms
        if str(term or "").strip()
        and not any(variant in proposal_text for variant in _required_term_variants(term))
    ]
    if not missing:
        return {}
    blocker = build_patch_blocker(
        todo.get("id") or "",
        "task_goal_term_missing",
        detail="patch proposal is missing required task-goal term(s): " + ", ".join(missing),
    )
    blocker["missing_terms"] = missing
    return blocker


def _normalize_review_findings(raw_findings):
    if raw_findings is None:
        return []
    if not isinstance(raw_findings, list):
        raw_findings = [raw_findings]
    findings = []
    for item in raw_findings:
        if isinstance(item, dict):
            normalized = {}
            for key in ("path", "line", "severity", "message", "detail", "reason", "suggested_fix", "rule"):
                if item.get(key) is not None:
                    normalized[key] = item.get(key)
            if normalized:
                findings.append(normalized)
            continue
        text = str(item or "").strip()
        if text:
            findings.append({"message": text})
    return findings


def _normalize_proposal(proposal, *, todo_id):
    if not isinstance(proposal, dict):
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="proposal must be an object",
        )

    kind = str(proposal.get("kind") or "").strip()
    if kind == "patch_blocker":
        return _normalize_blocker_proposal(proposal, todo_id=todo_id)
    if kind != "patch_proposal":
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="proposal.kind must be patch_proposal or patch_blocker",
        )

    files = proposal.get("files")
    if not isinstance(files, list) or not files:
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="patch_proposal.files must be a non-empty array",
        )

    normalized_files = []
    seen_paths = set()
    for file_index, file_item in enumerate(files, start=1):
        if not isinstance(file_item, dict):
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"files[{file_index}] must be an object",
            )
        path = normalize_work_path(file_item.get("path"))
        if not path:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"files[{file_index}].path must be a non-empty string",
            )
        if path in seen_paths:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"duplicate files entry for path: {path}",
            )
        seen_paths.add(path)

        edits = file_item.get("edits")
        if not isinstance(edits, list) or not edits:
            return build_patch_blocker(
                todo_id,
                "model_returned_non_schema",
                detail=f"files[{file_index}].edits must be a non-empty array",
            )
        normalized_edits = []
        for edit_index, edit in enumerate(edits, start=1):
            if not isinstance(edit, dict):
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"files[{file_index}].edits[{edit_index}] must be an object",
                )
            old = edit.get("old")
            new = edit.get("new")
            if not isinstance(old, str) or not old:
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"files[{file_index}].edits[{edit_index}].old must be a non-empty string",
                )
            if not isinstance(new, str):
                return build_patch_blocker(
                    todo_id,
                    "model_returned_non_schema",
                    detail=f"files[{file_index}].edits[{edit_index}].new must be a string",
                )
            normalized_edits.append({"old": old, "new": new})
        normalized_files.append({"path": path, "edits": normalized_edits})

    return {
        "kind": "patch_proposal",
        "summary": str(proposal.get("summary") or "").strip(),
        "files": normalized_files,
    }


def _normalize_blocker_proposal(proposal, *, todo_id):
    code = str(proposal.get("code") or "").strip()
    if not code:
        return build_patch_blocker(
            todo_id,
            "model_returned_non_schema",
            detail="patch_blocker.code must be a non-empty string",
        )
    return build_patch_blocker(
        todo_id,
        code,
        path=proposal.get("path") or "",
        detail=proposal.get("detail") or proposal.get("summary") or "",
    )


def _validate_pairing(todo, edited_paths, *, allowed_write_roots=None):
    ordered_target_paths = list(todo.get("source", {}).get("target_paths") or [])
    target_paths = set(ordered_target_paths)
    edited_path_set = set(edited_paths)
    target_test_paths = [path for path in ordered_target_paths if _patch_draft_path_is_test(path)]
    edited_target_test_paths = [
        path for path in edited_paths if path in target_paths and _patch_draft_path_is_test(path)
    ]

    if not allowed_write_roots:
        return build_patch_blocker(
            todo.get("id") or "",
            "write_policy_violation",
            detail="allowed_write_roots is required for validation",
        )

    for path in edited_paths:
        if not _path_under_allowed_roots(path, allowed_write_roots):
            return build_patch_blocker(
                todo.get("id") or "",
                "write_policy_violation",
                path=path,
                detail="proposal path is outside allowed_write_roots",
            )

    for path in edited_paths:
        if path not in target_paths:
            return build_patch_blocker(
                todo.get("id") or "",
                "write_policy_violation",
                path=path,
                detail="proposal path is outside the active WorkTodo target_paths",
            )

    for path in edited_paths:
        if not path.startswith("src/mew/"):
            continue
        paired_test_path = convention_test_path_for_mew_source(path)
        if not paired_test_path:
            continue
        if paired_test_path in target_paths:
            if paired_test_path not in edited_path_set:
                return build_patch_blocker(
                    todo.get("id") or "",
                    "unpaired_source_edit_blocked",
                    path=path,
                    detail=f"missing paired test edit for {paired_test_path}",
                )
            continue
        if target_test_paths:
            if edited_target_test_paths:
                continue
            return build_patch_blocker(
                todo.get("id") or "",
                "unpaired_source_edit_blocked",
                path=path,
                detail=f"missing paired test edit for {target_test_paths[0]}",
            )
        return build_patch_blocker(
            todo.get("id") or "",
            "write_policy_violation",
            path=paired_test_path,
            detail="paired test path is outside the active WorkTodo target_paths",
        )
    return {}


def _patch_draft_path_is_test(path):
    normalized = normalize_work_path(path)
    return normalized.startswith("tests/") or "/tests/" in normalized


def _compile_file(*, todo, proposal_file, cached_windows, live_files):
    path = proposal_file["path"]
    window_bundle = _normalize_cached_window_bundle(cached_windows, path)
    if not window_bundle["windows"]:
        return build_patch_blocker(
            todo.get("id") or "",
            "missing_exact_cached_window_texts",
            path=path,
            detail="missing cached window text for target path",
        )
    if any(window.get("context_truncated") for window in window_bundle["windows"]):
        window = window_bundle["windows"][0]
        return build_patch_blocker(
            todo.get("id") or "",
            "cached_window_text_truncated",
            path=path,
            line_start=window.get("line_start"),
            line_end=window.get("line_end"),
            detail="cached window text is truncated",
        )

    first_window = window_bundle["windows"][0] if window_bundle["windows"] else {}
    live_file = _normalize_live_file(
        live_files,
        path,
        todo_id=todo.get("id") or "",
        line_start=first_window.get("line_start"),
        line_end=first_window.get("line_end"),
    )
    if live_file.get("kind") == "patch_blocker":
        return live_file

    stale_blocker = _validate_live_file_against_cached_window(path, window_bundle, live_file, todo_id=todo.get("id") or "")
    if stale_blocker:
        return stale_blocker

    before_text = live_file["text"]
    placements = []
    for index, edit in enumerate(proposal_file["edits"], start=1):
        if edit["old"] not in window_bundle["text"]:
            window = _first_window_containing(window_bundle["windows"], edit["old"]) or window_bundle["windows"][0]
            return build_patch_blocker(
                todo.get("id") or "",
                "old_text_not_found",
                path=path,
                line_start=window.get("line_start"),
                line_end=window.get("line_end"),
                detail=f"edit hunk #{index} old text was not found in cached window text",
            )
        count = before_text.count(edit["old"])
        if count == 0:
            window = _first_window_containing(window_bundle["windows"], edit["old"]) or window_bundle["windows"][0]
            return build_patch_blocker(
                todo.get("id") or "",
                "old_text_not_found",
                path=path,
                line_start=window.get("line_start"),
                line_end=window.get("line_end"),
                detail=f"edit hunk #{index} old text was not found in live file text",
            )
        if count > 1:
            return build_patch_blocker(
                todo.get("id") or "",
                "ambiguous_old_text_match",
                path=path,
                detail=f"edit hunk #{index} old text matched {count} times in the live file",
            )
        start = before_text.find(edit["old"])
        placements.append(
            {
                "index": index,
                "old": edit["old"],
                "new": edit["new"],
                "start": start,
                "end": start + len(edit["old"]),
            }
        )
        duplicate_blocker = _duplicated_adjacent_context_blocker(
            todo_id=todo.get("id") or "",
            path=path,
            before_text=before_text,
            old=edit["old"],
            new=edit["new"],
            start=start,
            end=start + len(edit["old"]),
            index=index,
        )
        if duplicate_blocker:
            return duplicate_blocker

    placements.sort(key=lambda item: (item["start"], item["end"], item["index"]))
    for previous, current in zip(placements, placements[1:]):
        if current["start"] < previous["end"]:
            return build_patch_blocker(
                todo.get("id") or "",
                "overlapping_hunks",
                path=path,
                detail="same-path edit hunks overlap in the live file",
            )

    after_text = _apply_placements(before_text, placements)
    if after_text == before_text:
        return build_patch_blocker(
            todo.get("id") or "",
            "no_material_change",
            path=path,
            detail="compiled patch does not change the file",
        )

    return {
        "path": path,
        "kind": "edit_file" if len(proposal_file["edits"]) == 1 else "edit_file_hunks",
        "edits": proposal_file["edits"],
        "window_sha256s": window_bundle["window_sha256s"],
        "pre_file_sha256": sha256_text(before_text),
        "post_file_sha256": sha256_text(after_text),
        "_unified_diff": _unified_diff_text(path, before_text, after_text),
    }


def _duplicated_adjacent_context_blocker(*, todo_id, path, before_text, old, new, start, end, index):
    if new.startswith(old):
        inserted = new[len(old) :]
        following = before_text[end:]
        prefix = _meaningful_edge_text(inserted, from_start=True)
        if prefix and following.startswith(prefix):
            return build_patch_blocker(
                todo_id,
                "duplicated_adjacent_context",
                path=path,
                detail=(
                    f"edit hunk #{index} repeats text already adjacent after the old text; "
                    "include the complete old block or narrow the insertion anchor"
                ),
            )
    if new.endswith(old):
        inserted = new[: -len(old)]
        preceding = before_text[:start]
        suffix = _meaningful_edge_text(inserted, from_start=False)
        if suffix and preceding.endswith(suffix):
            return build_patch_blocker(
                todo_id,
                "duplicated_adjacent_context",
                path=path,
                detail=(
                    f"edit hunk #{index} repeats text already adjacent before the old text; "
                    "include the complete old block or narrow the insertion anchor"
                ),
            )
    return {}


def _meaningful_edge_text(text, *, from_start):
    lines = text.splitlines(keepends=True)
    if not from_start:
        lines = list(reversed(lines))
    selected = []
    non_blank = 0
    char_count = 0
    for line in lines:
        if not selected and not line.strip():
            continue
        selected.append(line)
        char_count += len(line)
        if line.strip():
            non_blank += 1
        if non_blank >= 2 or char_count >= 160:
            break
    if not selected or non_blank == 0:
        return ""
    if not from_start:
        selected = list(reversed(selected))
    return "".join(selected)


def _normalize_cached_window_bundle(cached_windows, path):
    windows = []
    if isinstance(cached_windows, dict):
        raw_windows = cached_windows.get(path)
    else:
        raw_windows = cached_windows
    if isinstance(raw_windows, dict):
        raw_windows = [raw_windows]

    for raw_window in raw_windows or []:
        if not isinstance(raw_window, dict):
            continue
        window_path = normalize_work_path(raw_window.get("path") or path)
        if window_path != path:
            continue
        text = raw_window.get("text")
        if not isinstance(text, str):
            continue
        line_start = raw_window.get("line_start")
        line_end = raw_window.get("line_end")
        try:
            line_start = int(line_start) if line_start is not None else None
            line_end = int(line_end) if line_end is not None else None
        except (TypeError, ValueError):
            line_start = None
            line_end = None
        windows.append(
            {
                "path": window_path,
                "text": text,
                "line_start": line_start,
                "line_end": line_end,
                "context_truncated": bool(raw_window.get("context_truncated")),
                "window_sha256": str(raw_window.get("window_sha256") or sha256_text(text)),
                "file_sha256": str(raw_window.get("file_sha256") or "").strip(),
            }
        )

    windows.sort(key=lambda item: ((item.get("line_start") or 0), (item.get("line_end") or 0)))
    return {
        "windows": windows,
        "text": "\n".join(window["text"] for window in windows),
        "window_sha256s": [window["window_sha256"] for window in windows],
    }


def _normalize_live_file(live_files, path, *, todo_id, line_start=None, line_end=None):
    raw_live = live_files.get(path) if isinstance(live_files, dict) else None
    if not isinstance(raw_live, dict):
        return build_patch_blocker(
            todo_id,
            "stale_cached_window_text",
            path=path,
            line_start=line_start,
            line_end=line_end,
            detail="missing live file payload",
        )
    text = raw_live.get("text")
    if not isinstance(text, str):
        return build_patch_blocker(
            todo_id,
            "stale_cached_window_text",
            path=path,
            line_start=line_start,
            line_end=line_end,
            detail="missing live file text",
        )
    sha256 = str(raw_live.get("sha256") or "").strip()
    if not sha256:
        return build_patch_blocker(
            todo_id,
            "stale_cached_window_text",
            path=path,
            line_start=line_start,
            line_end=line_end,
            detail="missing live file sha256",
        )
    return {"text": text, "sha256": sha256}


def _validate_live_file_against_cached_window(path, window_bundle, live_file, *, todo_id):
    computed_live_sha = sha256_text(live_file["text"])
    if live_file["sha256"] != computed_live_sha:
        window = window_bundle["windows"][0]
        return build_patch_blocker(
            todo_id,
            "stale_cached_window_text",
            path=path,
            line_start=window.get("line_start"),
            line_end=window.get("line_end"),
            detail="provided live file text/hash mismatch",
        )

    for window in window_bundle["windows"]:
        expected_sha = str(window.get("file_sha256") or "").strip()
        if expected_sha and expected_sha != live_file["sha256"]:
            return build_patch_blocker(
                todo_id,
                "stale_cached_window_text",
                path=path,
                line_start=window.get("line_start"),
                line_end=window.get("line_end"),
                detail="live file hash differs from cached window hash",
            )
    return {}


def _first_window_containing(windows, text):
    for window in windows or []:
        if text in (window.get("text") or ""):
            return window
    return {}


def _apply_placements(before_text, placements):
    pieces = []
    cursor = 0
    for placement in placements:
        pieces.append(before_text[cursor : placement["start"]])
        pieces.append(placement["new"])
        cursor = placement["end"]
    pieces.append(before_text[cursor:])
    return "".join(pieces)


def _unified_diff_text(path, before_text, after_text):
    return "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _path_under_allowed_roots(path, allowed_roots):
    resolved_path = _resolve_workspace_path(path)
    if not resolved_path:
        return False

    for allowed_root in allowed_roots or []:
        resolved_root = _resolve_workspace_path(allowed_root)
        if not resolved_root:
            continue
        if resolved_path == resolved_root or _is_relative_to(resolved_path, resolved_root):
            return True
    return False


def _resolve_workspace_path(path):
    raw_path = str(path or "").strip().replace("\\", "/")
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


def _stable_artifact_id(prefix, payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"
