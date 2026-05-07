"""Approval-gated write tool execution for the default-off implement_v2 lane."""

from __future__ import annotations

from pathlib import Path

from ..write_tools import edit_file, edit_file_hunks, write_file
from .replay import build_invalid_tool_result
from .types import ToolCallEnvelope, ToolResultEnvelope

WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})
PROTECTED_WRITE_PATHS = frozenset({"ROADMAP.md", "ROADMAP_STATUS.md", "SIDE_PROJECT_ROADMAP_STATUS.md"})
PROTECTED_WRITE_PREFIXES = (".codex/skills/", ".github/workflows/")


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
            return ToolResultEnvelope(
                lane_attempt_id=call.lane_attempt_id,
                provider_call_id=call.provider_call_id,
                mew_tool_call_id=call.mew_tool_call_id,
                tool_name=call.tool_name,
                status="failed",
                is_error=True,
                content=({"reason": str(exc)},),
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
        result = write_file(
            path,
            args.get("content", ""),
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
        result = edit_file(
            path,
            old_text,
            new_text,
            self.allowed_write_roots,
            replace_all=bool(args.get("replace_all")),
            dry_run=not apply,
        )
        return _write_payload(call, result, apply=apply, approval=approval)

    def _apply_patch(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        apply = _apply_requested(args)
        approval = self._approval_for_call(call) if apply else None
        denied = _denied_payload(call, approval=approval) if apply and not _approval_granted(approval) else None
        if denied is not None:
            return denied
        patch_args = _patch_edit_arguments(args)
        self._raise_for_governance_path(str(_workspace_path(patch_args["path"], self.workspace)))
        result = edit_file_hunks(
            str(_workspace_path(patch_args["path"], self.workspace)),
            patch_args["edits"],
            self.allowed_write_roots,
            dry_run=not apply,
        )
        result["operation"] = "apply_patch"
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


def _apply_requested(args: dict[str, object]) -> bool:
    return bool(args.get("apply")) or args.get("dry_run") is False


def _first_present(args: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in args and args.get(key) is not None:
            return args.get(key)
    return ""


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
        if stripped.startswith("*** Add File:") or stripped.startswith("*** Delete File:"):
            raise ValueError("minimal apply_patch v0 supports update-file patches only")
        if stripped.startswith("*** Update File:"):
            if path:
                raise ValueError("minimal apply_patch v0 supports exactly one file")
            path = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("@@"):
            flush_edit()
            continue
        if not path:
            if stripped:
                raise ValueError("apply_patch update file header is required before hunks")
            continue
        marker = raw_line[:1]
        text = raw_line[1:] if marker in {" ", "-", "+"} else raw_line
        if marker == "-":
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
        raise ValueError("apply_patch update file header is required")
    if not saw_change:
        raise ValueError("apply_patch contains no changes")
    if not edits:
        raise ValueError("apply_patch contains no exact anchored edit hunks")
    return {
        "path": path,
        "edits": edits,
        "format": "exact_update_patch_v0",
    }


__all__ = ["ImplementV2WriteRuntime", "WRITE_TOOL_NAMES"]
