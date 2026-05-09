"""Approval-gated write tool execution for the default-off implement_v2 lane."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from ..write_tools import delete_file, edit_file, edit_file_hunks, write_file
from .replay import build_invalid_tool_result
from .types import ToolCallEnvelope, ToolResultEnvelope

WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})
PROTECTED_WRITE_PATHS = frozenset({"ROADMAP.md", "ROADMAP_STATUS.md", "SIDE_PROJECT_ROADMAP_STATUS.md"})
PROTECTED_WRITE_PREFIXES = (".codex/skills/", ".github/workflows/")
_EDIT_RECOVERY_FILE_CHAR_CAP = 1_000_000
_EDIT_RECOVERY_OLD_TEXT_CHAR_CAP = 4096
_SOURCE_MUTATION_LINE_GUARD_MIN_CHARS = 4000
_SOURCE_MUTATION_MAX_LINE_CHARS = 2400
_SOURCE_MUTATION_EXTENSIONS = frozenset(
    {
        ".bash",
        ".c",
        ".cc",
        ".cjs",
        ".cpp",
        ".cs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".lua",
        ".mjs",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".swift",
        ".ts",
        ".tsx",
        ".zsh",
    }
)


class ImplementV2WriteRuntime:
    """Lane-local write runtime for Phase 5 fake-provider tests."""

    def __init__(
        self,
        *,
        workspace: object,
        allowed_write_roots: tuple[str, ...] | list[str] | None = None,
        approved_write_calls: tuple[object, ...] | list[object] | None = None,
        allow_governance_writes: bool = False,
    ):
        self.workspace = Path(str(workspace or ".")).expanduser().resolve(strict=False)
        self.allowed_write_roots = tuple(
            str(_workspace_path(root, self.workspace)) for root in (allowed_write_roots or ())
        )
        self.approved_write_calls = tuple(approved_write_calls or ())
        self.allow_governance_writes = bool(allow_governance_writes)

    def execute(self, call: ToolCallEnvelope) -> ToolResultEnvelope:
        if call.tool_name not in WRITE_TOOL_NAMES:
            return build_invalid_tool_result(call, reason=f"unknown write tool: {call.tool_name}")
        try:
            if call.tool_name == "write_file":
                payload = self._write_file(call)
            elif call.tool_name == "edit_file":
                payload = self._edit_file(call)
            else:
                payload = self._apply_patch(call)
        except (OSError, RuntimeError, ValueError) as exc:
            content = {"reason": str(exc)}
            if call.tool_name == "edit_file":
                content.update(self._edit_file_recovery_payload(call, reason=str(exc)))
            elif call.tool_name == "apply_patch":
                content.update(self._apply_patch_recovery_payload(call, reason=str(exc)))
            return ToolResultEnvelope(
                lane_attempt_id=call.lane_attempt_id,
                provider_call_id=call.provider_call_id,
                mew_tool_call_id=call.mew_tool_call_id,
                tool_name=call.tool_name,
                status="failed",
                is_error=True,
                content=(content,),
            )
        return self._result_from_payload(call, payload)

    def _write_file(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        apply = _apply_requested(args)
        path = str(_workspace_path(args.get("path") or "", self.workspace))
        self._raise_for_governance_path(path)
        approval = self._approval_for_call(call) if apply else None
        denied = _denied_payload(call, approval=approval) if apply and not _approval_granted(approval) else None
        if denied is not None:
            return denied
        content = _content_text(args)
        quality_failure = _source_mutation_quality_failure_payload(
            path,
            content,
            operation="write_file",
            apply=apply,
            approval=approval,
        )
        if quality_failure is not None:
            return quality_failure
        result = write_file(
            path,
            content,
            self.allowed_write_roots,
            create=bool(args.get("create")),
            dry_run=not apply,
        )
        return _write_payload(call, result, apply=apply, approval=approval)

    def _edit_file(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        apply = _apply_requested(args)
        path = str(_workspace_path(args.get("path") or "", self.workspace))
        self._raise_for_governance_path(path)
        approval = self._approval_for_call(call) if apply else None
        denied = _denied_payload(call, approval=approval) if apply and not _approval_granted(approval) else None
        if denied is not None:
            return denied
        old_text = _first_present(args, "old", "old_string", "old_text")
        new_text = _first_present(args, "new", "new_string", "new_text")
        quality_failure = _source_mutation_quality_failure_payload(
            path,
            _changed_new_text_for_line_guard(old_text, new_text),
            operation="edit_file",
            apply=apply,
            approval=approval,
        )
        if quality_failure is not None:
            return quality_failure
        result = edit_file(
            path,
            old_text,
            new_text,
            self.allowed_write_roots,
            replace_all=bool(args.get("replace_all")),
            dry_run=not apply,
        )
        return _write_payload(call, result, apply=apply, approval=approval)

    def _edit_file_recovery_payload(self, call: ToolCallEnvelope, *, reason: str) -> dict[str, object]:
        if "old text was not found" not in reason:
            return {}
        args = dict(call.arguments)
        path = _workspace_path(args.get("path") or "", self.workspace)
        old_text = str(_first_present(args, "old", "old_string", "old_text") or "")
        payload: dict[str, object] = {
            "failure_class": "edit_exact_match_miss",
            "failure_subclass": "edit_exact_match_miss",
            "recoverable": True,
            "path": str(path),
            "suggested_tool": "read_file/edit_file/apply_patch",
            "suggested_next_action": "retry with an exact old string from nearest_existing_windows or read the target window",
        }
        if old_text:
            payload["old_string_preview"] = _clip_text(old_text, 240)
        try:
            current = _read_text_prefix(path, _EDIT_RECOVERY_FILE_CHAR_CAP)
        except OSError:
            return payload
        windows = _nearest_existing_windows(current, old_text)
        if windows:
            payload["nearest_existing_windows"] = windows
        return payload

    def _apply_patch_recovery_payload(self, call: ToolCallEnvelope, *, reason: str) -> dict[str, object]:
        anchor_missing = "old text was not found" in reason
        anchor_ambiguous = "old text matched" in reason
        if not anchor_missing and not anchor_ambiguous:
            return {}
        try:
            patch_args = _patch_edit_arguments(dict(call.arguments))
        except ValueError:
            return {}
        if str(patch_args.get("operation") or "") != "update_file":
            return {}
        path = _workspace_path(patch_args.get("path") or "", self.workspace)
        edits = patch_args.get("edits") if isinstance(patch_args.get("edits"), list) else []
        hunk_index = _hunk_index_from_reason(reason)
        selected_edits = (
            [edits[hunk_index - 1]]
            if hunk_index is not None and 0 < hunk_index <= len(edits)
            else [edit for edit in edits if isinstance(edit, dict)]
        )
        failure_subclass = "patch_ambiguous_anchor" if anchor_ambiguous else "patch_exact_match_miss"
        payload: dict[str, object] = {
            "failure_class": "patch_anchor_mismatch",
            "failure_subclass": failure_subclass,
            "recoverable": True,
            "path": str(path),
            "suggested_tool": "read_file/apply_patch/edit_file",
            "suggested_next_action": (
                "retry with exact current source context from patch_anchor_windows "
                "or read the target window before the next patch"
            ),
        }
        try:
            current = _read_text_prefix(path, _EDIT_RECOVERY_FILE_CHAR_CAP)
        except OSError:
            return payload
        windows: list[dict[str, object]] = []
        for offset, edit in enumerate(selected_edits):
            if not isinstance(edit, dict):
                continue
            old_text = str(edit.get("old") or "")
            if not old_text:
                continue
            index = hunk_index if hunk_index is not None else offset + 1
            item: dict[str, object] = {
                "hunk_index": index,
                "old_string_preview": _clip_text(old_text, 240),
            }
            if anchor_ambiguous:
                item["matching_existing_windows"] = _matching_existing_windows(current, old_text)
            else:
                item["nearest_existing_windows"] = _nearest_existing_windows(current, old_text)
            windows.append(item)
            if len(windows) >= 3:
                break
        if windows:
            payload["patch_anchor_windows"] = windows
        return payload

    def _apply_patch(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        apply = _apply_requested(args)
        approval = self._approval_for_call(call) if apply else None
        denied = _denied_payload(call, approval=approval) if apply and not _approval_granted(approval) else None
        if denied is not None:
            return denied
        patch_args = _patch_edit_arguments(args)
        self._raise_for_governance_path(str(_workspace_path(patch_args["path"], self.workspace)))
        patch_path = str(_workspace_path(patch_args["path"], self.workspace))
        patch_lexical_path = str(_workspace_lexical_path(patch_args["path"], self.workspace))
        patch_operation = str(patch_args.get("operation") or "update_file")
        quality_failure = _patch_source_mutation_quality_failure_payload(
            patch_path,
            patch_args,
            operation="apply_patch",
            apply=apply,
            approval=approval,
        )
        if quality_failure is not None:
            return quality_failure
        if patch_operation == "add_file":
            if Path(patch_lexical_path).exists() or Path(patch_lexical_path).is_symlink():
                raise ValueError(f"apply_patch add file target already exists: {patch_args['path']}")
            result = write_file(
                patch_lexical_path,
                patch_args.get("content", ""),
                self.allowed_write_roots,
                create=True,
                dry_run=not apply,
            )
        elif patch_operation == "delete_file":
            result = delete_file(
                patch_lexical_path,
                self.allowed_write_roots,
                dry_run=not apply,
            )
        else:
            result = edit_file_hunks(
                patch_path,
                patch_args["edits"],
                self.allowed_write_roots,
                dry_run=not apply,
            )
        result["operation"] = "apply_patch"
        result["patch_operation"] = patch_operation
        result["patch_format"] = patch_args["format"]
        return _write_payload(call, result, apply=apply, approval=approval)

    def _approval_for_call(self, call: ToolCallEnvelope) -> dict[str, object]:
        for raw_approval in self.approved_write_calls:
            approval = _normalize_approval_record(raw_approval)
            if approval.get("status") != "approved":
                continue
            provider_call_id = str(approval.get("provider_call_id") or "")
            mew_tool_call_id = str(approval.get("mew_tool_call_id") or "")
            if provider_call_id and provider_call_id == call.provider_call_id:
                return approval
            if mew_tool_call_id and mew_tool_call_id == call.mew_tool_call_id:
                return approval
        return {}

    def _raise_for_governance_path(self, path: str) -> None:
        if self.allow_governance_writes:
            return
        resolved = Path(path).expanduser().resolve(strict=False)
        try:
            relative = resolved.relative_to(self.workspace).as_posix()
        except ValueError:
            relative = resolved.name
        if relative in PROTECTED_WRITE_PATHS or any(relative.startswith(prefix) for prefix in PROTECTED_WRITE_PREFIXES):
            raise ValueError(
                f"governance write path is protected in implement_v2 write mode: {relative}; "
                "route roadmap, skill, workflow, or policy edits through an explicit governance lane"
            )

    def _result_from_payload(self, call: ToolCallEnvelope, payload: dict[str, object]) -> ToolResultEnvelope:
        status = str(payload.get("mew_status") or "completed")
        is_error = status in {"failed", "denied", "invalid", "interrupted"}
        content_refs = ()
        if payload.get("diff"):
            content_refs = (f"implement-v2-write://{call.lane_attempt_id}/{call.provider_call_id}/diff",)
        evidence_refs = ()
        side_effects = ()
        if payload.get("written") and payload.get("dry_run") is False:
            evidence_refs = (f"implement-v2-write://{call.lane_attempt_id}/{call.provider_call_id}/mutation",)
            side_effects = (
                {
                    "kind": "file_write",
                    "operation": payload.get("operation") or call.tool_name,
                    "path": payload.get("path") or "",
                    "approval_status": payload.get("approval_status") or "",
                    "approval_source": payload.get("approval_source") or "",
                    "approval_id": payload.get("approval_id") or "",
                    "dry_run": payload.get("dry_run"),
                    "written": payload.get("written"),
                },
            )
        return ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status=status,
            is_error=is_error,
            content=(dict(payload),),
            content_refs=content_refs,
            evidence_refs=evidence_refs,
            side_effects=side_effects,
        )


def _workspace_path(path: object, workspace: Path) -> Path:
    requested = Path(str(path or "")).expanduser()
    if requested.is_absolute():
        return requested.resolve(strict=False)
    return (workspace / requested).resolve(strict=False)


def _workspace_lexical_path(path: object, workspace: Path) -> Path:
    requested = Path(str(path or "")).expanduser()
    if requested.is_absolute():
        return requested
    return workspace / requested


def _apply_requested(args: dict[str, object]) -> bool:
    return bool(args.get("apply")) or args.get("dry_run") is False


def _first_present(args: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in args and args.get(key) is not None:
            return args.get(key)
    return ""


def _content_text(args: dict[str, object], *, key: str = "content") -> str:
    if key in args and args.get(key) is not None:
        return str(args.get(key) or "")
    lines = args.get(f"{key}_lines")
    if isinstance(lines, list):
        text = "\n".join(str(line) for line in lines)
        if bool(args.get("trailing_newline", True)):
            text += "\n"
        return text
    return ""


def _clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _nearest_existing_windows(current: str, old_text: str) -> list[dict[str, object]]:
    if not current or not old_text:
        return []
    old_text = old_text[:_EDIT_RECOVERY_OLD_TEXT_CHAR_CAP]
    current = current[:_EDIT_RECOVERY_FILE_CHAR_CAP]
    window_size = max(160, min(640, len(old_text) * 6))
    starts: set[int] = set()
    for anchor in _edit_mismatch_anchors(old_text):
        search_from = 0
        matches_for_anchor = 0
        while matches_for_anchor < 16 and len(starts) < 160:
            index = current.find(anchor, search_from)
            if index < 0:
                break
            starts.add(max(0, index - window_size // 2))
            search_from = index + max(1, len(anchor))
            matches_for_anchor += 1
    if not starts:
        return []
    ranked: list[tuple[float, int, int, str]] = []
    for start in starts:
        end = min(len(current), start + window_size)
        snippet = current[start:end]
        score = difflib.SequenceMatcher(None, old_text, snippet).ratio()
        ranked.append((score, start, end, snippet))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    windows: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for score, start, end, snippet in ranked:
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        windows.append(
            {
                "start": start,
                "end": end,
                "similarity": round(score, 3),
                "text": _clip_text(snippet, 700),
            }
        )
        if len(windows) >= 3:
            break
    return windows


def _matching_existing_windows(current: str, old_text: str) -> list[dict[str, object]]:
    if not current or not old_text:
        return []
    old_text = old_text[:_EDIT_RECOVERY_OLD_TEXT_CHAR_CAP]
    current = current[:_EDIT_RECOVERY_FILE_CHAR_CAP]
    window_size = max(160, min(640, len(old_text) * 4))
    windows: list[dict[str, object]] = []
    search_from = 0
    while len(windows) < 3:
        index = current.find(old_text, search_from)
        if index < 0:
            break
        start = max(0, index - window_size // 2)
        end = min(len(current), index + len(old_text) + window_size // 2)
        windows.append(
            {
                "start": start,
                "end": end,
                "text": _clip_text(current[start:end], 700),
            }
        )
        search_from = index + max(1, len(old_text))
    return windows


def _hunk_index_from_reason(reason: str) -> int | None:
    match = re.search(r"edit hunk #(\d+)", reason)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _edit_mismatch_anchors(old_text: str) -> list[str]:
    raw_tokens = re.findall(
        r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+"
        r"|0x[0-9A-Fa-f]+"
        r"|[A-Za-z_$][A-Za-z0-9_$]*"
        r"|>>>|<<|&&|\|\||==|!=|<=|>=|[0-9]+",
        old_text,
    )
    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) < 3 and not token.isdigit():
            continue
        if token not in tokens:
            tokens.append(token)
    tokens.sort(key=lambda item: (-len(item), item))
    return tokens[:12]


def _read_text_prefix(path: Path, char_limit: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(char_limit)


def _normalize_approval_record(raw_approval: object) -> dict[str, object]:
    if isinstance(raw_approval, str):
        return {
            "provider_call_id": raw_approval,
            "status": "approved",
            "source": "lane_config.approved_write_calls",
            "approval_id": raw_approval,
        }
    if not isinstance(raw_approval, dict):
        return {}
    status = str(raw_approval.get("status") or "").strip()
    return {
        "provider_call_id": str(raw_approval.get("provider_call_id") or "").strip(),
        "mew_tool_call_id": str(raw_approval.get("mew_tool_call_id") or "").strip(),
        "status": status,
        "source": str(raw_approval.get("source") or "external_write_approval").strip(),
        "approval_id": str(
            raw_approval.get("approval_id")
            or raw_approval.get("id")
            or raw_approval.get("provider_call_id")
            or raw_approval.get("mew_tool_call_id")
            or ""
        ).strip(),
    }


def _approval_granted(approval: dict[str, object]) -> bool:
    return str(approval.get("status") or "") == "approved" and bool(approval.get("approval_id"))


def _denied_payload(call: ToolCallEnvelope, *, approval: dict[str, object]) -> dict[str, object]:
    status = str(approval.get("status") or "") or "missing"
    return {
        "operation": call.tool_name,
        "mew_status": "denied",
        "dry_run": True,
        "written": False,
        "changed": False,
        "approval_status": status,
        "approval_source": str(approval.get("source") or ""),
        "approval_id": str(approval.get("approval_id") or ""),
        "reason": (
            f"{call.tool_name} apply requested without independent approved write approval; "
            "provider-supplied approval arguments are ignored"
        ),
    }


def _source_mutation_quality_failure_payload(
    path: object,
    content: object,
    *,
    operation: str,
    apply: bool,
    approval: dict[str, object] | None,
) -> dict[str, object] | None:
    text = str(content or "")
    path_text = str(path or "")
    if not _source_path_needs_line_guard(path_text, text):
        return None
    lines = text.splitlines() or [text]
    line_number, longest_line = max(enumerate(lines, start=1), key=lambda item: len(item[1]))
    if len(longest_line) <= _SOURCE_MUTATION_MAX_LINE_CHARS:
        return None
    return {
        "operation": operation,
        "mew_status": "failed",
        "dry_run": True,
        "written": False,
        "changed": False,
        "apply_requested": bool(apply),
        "approval_status": str((approval or {}).get("status") or ("approved" if apply else "not_required_for_dry_run")),
        "approval_source": str((approval or {}).get("source") or ("external_write_approval" if apply else "")),
        "approval_id": str((approval or {}).get("approval_id") or ""),
        "failure_class": "source_mutation_unreadable_long_line",
        "failure_subclass": "source_mutation_single_line_diagnostic_risk",
        "recoverable": True,
        "path": path_text,
        "reason": (
            f"{operation} would create a {len(longest_line)} character line in source file {path_text}; "
            "rewrite the source mutation as readable multi-line code before verification"
        ),
        "line_number": line_number,
        "line_chars": len(longest_line),
        "max_line_chars": _SOURCE_MUTATION_MAX_LINE_CHARS,
        "content_chars": len(text),
        "suggested_tool": "write_file/edit_file/apply_patch",
        "suggested_next_action": (
            "rewrite source mutations as readable multi-line code before verification; "
            "single-line generated source causes poor diagnostics and fragile follow-up edits"
        ),
    }


def _changed_new_text_for_line_guard(old_text: object, new_text: object) -> str:
    old_lines = str(old_text or "").splitlines()
    new_lines = str(new_text or "").splitlines()
    if not old_lines:
        return str(new_text or "")
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    changed_lines: list[str] = []
    for tag, _old_start, _old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_lines.extend(new_lines[new_start:new_end])
    return "\n".join(changed_lines)


def _patch_source_mutation_quality_failure_payload(
    path: object,
    patch_args: dict[str, object],
    *,
    operation: str,
    apply: bool,
    approval: dict[str, object] | None,
) -> dict[str, object] | None:
    patch_operation = str(patch_args.get("operation") or "")
    if patch_operation == "delete_file":
        return None
    if patch_operation == "add_file":
        return _source_mutation_quality_failure_payload(
            path,
            patch_args.get("content", ""),
            operation=operation,
            apply=apply,
            approval=approval,
        )
    edits = patch_args.get("edits") if isinstance(patch_args.get("edits"), list) else []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        failure = _source_mutation_quality_failure_payload(
            path,
            _changed_new_text_for_line_guard(edit.get("old", ""), edit.get("new", "")),
            operation=operation,
            apply=apply,
            approval=approval,
        )
        if failure is not None:
            return failure
    return None


def _source_path_needs_line_guard(path: str, text: str) -> bool:
    if len(text) < _SOURCE_MUTATION_LINE_GUARD_MIN_CHARS:
        return False
    suffix = Path(path).suffix.lower()
    return suffix in _SOURCE_MUTATION_EXTENSIONS


def _write_payload(
    call: ToolCallEnvelope,
    result: dict[str, object],
    *,
    apply: bool,
    approval: dict[str, object] | None,
) -> dict[str, object]:
    payload = dict(result)
    payload.setdefault("operation", call.tool_name)
    payload["mew_status"] = "completed"
    payload["approval_status"] = str((approval or {}).get("status") or ("approved" if apply else "not_required_for_dry_run"))
    payload["approval_source"] = str((approval or {}).get("source") or ("external_write_approval" if apply else ""))
    payload["approval_id"] = str((approval or {}).get("approval_id") or "")
    payload["apply_requested"] = bool(apply)
    return payload


def _patch_edit_arguments(args: dict[str, object]) -> dict[str, object]:
    patch_text = str(args.get("patch") or args.get("input") or "")
    if args.get("edits") or ((args.get("path") or args.get("edits")) and not patch_text):
        raise ValueError("apply_patch requires patch text; path/edits structured bypass is not accepted in implement_v2")
    parsed = _parse_minimal_apply_patch(patch_text)
    explicit_path = str(args.get("path") or "").strip()
    if explicit_path and explicit_path != str(parsed.get("path") or "").strip():
        raise ValueError("apply_patch path argument must match patch update file")
    return parsed


def _parse_minimal_apply_patch(patch_text: str) -> dict[str, object]:
    lines = patch_text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "*** Begin Patch":
        raise ValueError("apply_patch input must start with *** Begin Patch")
    if not lines[-1].strip() == "*** End Patch":
        raise ValueError("apply_patch input must end with *** End Patch")
    path = ""
    operation = ""
    add_parts: list[str] = []
    old_parts: list[str] = []
    new_parts: list[str] = []
    edits: list[dict[str, str]] = []
    saw_change = False

    def flush_edit() -> None:
        if not old_parts and not new_parts:
            return
        if old_parts == new_parts:
            old_parts.clear()
            new_parts.clear()
            return
        if not old_parts:
            raise ValueError("apply_patch hunk must include old/context lines for exact anchoring")
        edits.append({"old": "".join(old_parts), "new": "".join(new_parts)})
        old_parts.clear()
        new_parts.clear()

    for raw_line in lines[1:-1]:
        stripped = raw_line.strip()
        if stripped.startswith("*** Add File:"):
            if path:
                raise ValueError("minimal apply_patch v0 supports exactly one file")
            path = stripped.split(":", 1)[1].strip()
            operation = "add_file"
            continue
        if stripped.startswith("*** Delete File:"):
            if path:
                raise ValueError("minimal apply_patch v0 supports exactly one file")
            path = stripped.split(":", 1)[1].strip()
            operation = "delete_file"
            saw_change = True
            continue
        if stripped.startswith("*** Update File:"):
            if path:
                raise ValueError("minimal apply_patch v0 supports exactly one file")
            path = stripped.split(":", 1)[1].strip()
            operation = "update_file"
            continue
        if stripped.startswith("@@"):
            if operation != "update_file":
                raise ValueError("apply_patch @@ hunks are only valid for update-file patches")
            flush_edit()
            continue
        if not path:
            if stripped:
                raise ValueError("apply_patch file header is required before patch body")
            continue
        marker = raw_line[:1]
        text = raw_line[1:] if marker in {" ", "-", "+"} else raw_line
        if operation == "add_file":
            if marker != "+":
                raise ValueError("apply_patch add-file body lines must start with +")
            add_parts.append(text)
            saw_change = True
        elif operation == "delete_file":
            if stripped:
                raise ValueError("apply_patch delete-file patch must not include body lines")
        elif marker == "-":
            old_parts.append(text)
            saw_change = True
        elif marker == "+":
            new_parts.append(text)
            saw_change = True
        elif marker == " ":
            old_parts.append(text)
            new_parts.append(text)
        elif stripped:
            raise ValueError(f"unsupported apply_patch hunk line: {stripped}")
    flush_edit()
    if not path:
        raise ValueError("apply_patch file header is required")
    if not saw_change:
        raise ValueError("apply_patch contains no changes")
    if operation == "add_file":
        return {
            "path": path,
            "operation": operation,
            "content": "".join(add_parts),
            "format": "add_file_patch_v0",
        }
    if operation == "delete_file":
        return {
            "path": path,
            "operation": operation,
            "format": "delete_file_patch_v0",
        }
    if not edits:
        raise ValueError("apply_patch contains no exact anchored edit hunks")
    return {
        "path": path,
        "operation": operation or "update_file",
        "edits": edits,
        "format": "exact_update_patch_v0",
    }


__all__ = ["ImplementV2WriteRuntime", "WRITE_TOOL_NAMES"]
