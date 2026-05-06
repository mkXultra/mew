"""Managed exec tool execution for the default-off implement_v2 lane."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shlex
import time

from ..acceptance_evidence import split_unquoted_shell_command_segments
from ..read_tools import resolve_allowed_path
from ..toolbox import ManagedCommandRunner, is_resident_mew_loop_command, split_command_env
from .artifact_checks import capture_pre_run_artifact_stats, check_expected_artifacts
from .execution_evidence import (
    CommandRun,
    ToolRunRecord,
    apply_finish_gate,
    classify_execution_failure,
    derive_verifier_evidence,
    normalize_execution_contract,
    semantic_exit_from_run,
)
from .read_runtime import DEFAULT_V2_READ_RESULT_MAX_CHARS
from .replay import build_invalid_tool_result
from .types import ToolCallEnvelope, ToolResultEnvelope

EXEC_TOOL_NAMES = frozenset({"run_command", "run_tests", "poll_command", "cancel_command", "read_command_output"})
TERMINAL_SUCCESS_STATUSES = frozenset({"completed"})
TERMINAL_FAILURE_STATUSES = frozenset({"failed", "timed_out", "killed", "orphaned"})
NONTERMINAL_STATUSES = frozenset({"running", "yielded"})
RESIDENT_MEW_LOOP_TEXT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\S*/)?mew\s+(?:attach|chat|do|run|session|work)\b"
    r"|(?<![A-Za-z0-9_])(?:\S*/)?python(?:\d+(?:\.\d+)?)?\s+-m\s+mew\s+"
    r"(?:attach|chat|do|run|session|work)\b"
)


class RunTestsShellSurfaceMisuse(ValueError):
    """Structured run_tests tool-contract misuse.

    `run_tests` remains argv-only. This exception makes shell-shaped verifier
    attempts machine-readable so v2 can later route or recover them without
    widening the run_tests contract.
    """

    def __init__(self, payload: dict[str, object]):
        self.payload = dict(payload)
        super().__init__(str(self.payload.get("reason") or "run_tests shell surface misuse"))


class ImplementV2ManagedExecRuntime:
    """Lane-local managed exec runtime for Phase 4 fake-provider tests."""

    def __init__(
        self,
        *,
        workspace: object,
        allowed_roots: tuple[str, ...] | list[str] | None = None,
        max_active: int = 1,
        allow_shell: bool = False,
        run_command_available: bool = False,
        route_run_tests_shell_surface: bool = True,
        task_contract: dict[str, object] | None = None,
        frontier_state: dict[str, object] | None = None,
    ):
        self.workspace = Path(str(workspace or ".")).expanduser().resolve(strict=False)
        self.allowed_roots = tuple(str(root) for root in (allowed_roots or (str(self.workspace),)))
        self.allow_shell = bool(allow_shell)
        self.run_command_available = bool(run_command_available)
        self.route_run_tests_shell_surface = bool(route_run_tests_shell_surface)
        self.task_contract = dict(task_contract or {})
        self.frontier_state = dict(frontier_state or {})
        self.runner = ManagedCommandRunner(max_active=max_active)
        self.output_paths: dict[str, str] = {}
        self.command_metadata: dict[str, dict[str, object]] = {}

    def execute(self, call: ToolCallEnvelope) -> ToolResultEnvelope:
        if call.tool_name not in EXEC_TOOL_NAMES:
            return build_invalid_tool_result(call, reason=f"unknown exec tool: {call.tool_name}")
        try:
            if call.tool_name in {"run_command", "run_tests"}:
                payload = self._run_command(call)
            elif call.tool_name == "poll_command":
                payload = self._poll_command(call)
            elif call.tool_name == "cancel_command":
                payload = self._cancel_command(call)
            else:
                payload = self._read_command_output(call)
        except RunTestsShellSurfaceMisuse as exc:
            return ToolResultEnvelope(
                lane_attempt_id=call.lane_attempt_id,
                provider_call_id=call.provider_call_id,
                mew_tool_call_id=call.mew_tool_call_id,
                tool_name=call.tool_name,
                status="failed",
                is_error=True,
                content=(dict(exc.payload),),
            )
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

    def cancel_active_commands(self, *, reason: str) -> tuple[dict[str, object], ...]:
        cancelled = []
        while self.runner.active is not None:
            payload = self.runner.cancel(reason=reason)
            payload.update(self.command_metadata.get(str(payload.get("command_run_id") or ""), {}))
            cancelled.append(payload)
        return tuple(cancelled)

    def finalize_active_commands(self, *, timeout_seconds: float | None = None) -> tuple[dict[str, object], ...]:
        finalized = []
        while self.runner.active is not None:
            handle = self.runner.active
            command_remaining = max(0.0, float(handle.timeout) - max(0.0, time.monotonic() - handle.started_monotonic))
            if timeout_seconds is None:
                effective_timeout = command_remaining
            else:
                effective_timeout = min(max(0.0, float(timeout_seconds)), command_remaining)
            payload = self.runner.finalize(timeout=effective_timeout)
            payload.update(self.command_metadata.get(str(payload.get("command_run_id") or ""), {}))
            finalized.append(payload)
        return tuple(finalized)

    def _run_command(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        command, command_source = _normalize_command_argument(args)
        if not command:
            raise ValueError(f"{call.tool_name} command is empty")
        _reject_resident_mew_loop_command(command, tool_name=call.tool_name)
        use_shell = _use_shell_for_call(call.tool_name, command, args=args, command_source=command_source)
        effective_tool_name = call.tool_name
        tool_contract_recovery: dict[str, object] | None = None
        if call.tool_name == "run_tests":
            misuse = _run_tests_shell_surface_misuse(command, use_shell=use_shell)
            if misuse is not None:
                misuse["cwd"] = str(args.get("cwd") or ".")
                if not self.allow_shell or not self.run_command_available or not self.route_run_tests_shell_surface:
                    raise RunTestsShellSurfaceMisuse(misuse)
                use_shell = True
                effective_tool_name = "run_command"
                tool_contract_recovery = {
                    "kind": "run_tests_shell_surface_routed_to_run_command",
                    "features": list(misuse.get("features") or ()),
                    "preserved_command_hash": _preserved_command_hash(command),
                    "suggested_use_shell": True,
                    "failure_class": misuse.get("failure_class"),
                    "failure_subclass": misuse.get("failure_subclass"),
                }
        cwd = _workspace_path(args.get("cwd") or ".", self.workspace)
        cwd = resolve_allowed_path(cwd, self.allowed_roots)
        if not cwd.is_dir():
            raise ValueError(f"{call.tool_name} cwd is not a directory: {cwd}")
        command_run_id = _command_run_id(call)
        output_ref = f"{call.lane_attempt_id}/{command_run_id}/output.log"
        output_path = _output_path(self.workspace, output_ref)
        timeout = _bounded_float(args.get("timeout"), default=300.0, minimum=1.0, maximum=3600.0)
        foreground_budget = _bounded_float(
            args.get("foreground_budget_seconds"),
            default=min(15.0, max(0.0, timeout - 1.0)),
            minimum=0.0,
            maximum=min(30.0, timeout),
        )
        raw_contract = args.get("execution_contract") if isinstance(args.get("execution_contract"), dict) else {}
        normalized_contract = _normalize_runtime_contract(
            raw_contract,
            task_contract=self.task_contract,
            frontier_state=self.frontier_state,
            fallback_id=f"contract:{command_run_id}",
        )
        pre_run_artifact_stats = {}
        if normalized_contract.expected_artifacts:
            pre_run_artifact_stats = capture_pre_run_artifact_stats(
                normalized_contract.expected_artifacts,
                workspace=self.workspace,
                allowed_roots=self.allowed_roots,
            )
        self.runner.start(
            command,
            cwd=str(cwd),
            timeout=timeout,
            use_shell=use_shell,
            kill_process_group=True,
            command_run_id=command_run_id,
            output_ref=output_ref,
            output_path=str(output_path),
        )
        self.output_paths[command_run_id] = str(output_path)
        self.command_metadata[command_run_id] = {
            "tool_name": call.tool_name,
            "effective_tool_name": effective_tool_name,
            "command_source": command_source,
            "execution_contract_normalized": normalized_contract.as_dict(),
            "pre_run_artifact_stats": pre_run_artifact_stats,
            "tool_run_record_ids": [],
            **({"execution_contract": dict(args["execution_contract"])} if isinstance(args.get("execution_contract"), dict) else {}),
            **({"tool_contract_recovery": dict(tool_contract_recovery)} if tool_contract_recovery is not None else {}),
        }
        payload = self.runner.poll(wait_seconds=foreground_budget, command_run_id=command_run_id)
        if payload.get("status") == "running":
            payload["status"] = "yielded"
        payload["command_run_id"] = command_run_id
        payload["output_ref"] = output_ref
        payload["output_path"] = str(output_path)
        payload["tool_name"] = call.tool_name
        payload["effective_tool_name"] = effective_tool_name
        payload["command_source"] = command_source
        if isinstance(args.get("execution_contract"), dict):
            payload["execution_contract"] = dict(args["execution_contract"])
        if tool_contract_recovery is not None:
            payload["tool_contract_recovery"] = tool_contract_recovery
        return payload

    def _poll_command(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        command_run_id = _required_command_run_id(args)
        payload = self.runner.poll(
            wait_seconds=_bounded_float(args.get("wait_seconds"), default=0.0, minimum=0.0, maximum=30.0),
            command_run_id=command_run_id,
        )
        payload.update(self.command_metadata.get(command_run_id, {}))
        if payload.get("status") == "running":
            payload["status"] = "yielded"
        payload["command_run_id"] = command_run_id
        return payload

    def _cancel_command(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        command_run_id = _required_command_run_id(args)
        payload = self.runner.cancel(
            reason=str(args.get("reason") or "cancelled"),
            command_run_id=command_run_id,
        )
        payload.update(self.command_metadata.get(command_run_id, {}))
        payload["command_run_id"] = command_run_id
        return payload

    def _read_command_output(self, call: ToolCallEnvelope) -> dict[str, object]:
        args = dict(call.arguments)
        command_run_id = _required_command_run_id(args)
        if command_run_id not in self.output_paths:
            raise ValueError(f"unknown command_run_id: {command_run_id}")
        output_path = Path(self.output_paths[command_run_id])
        text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
        max_chars = int(_bounded_float(args.get("max_chars"), default=DEFAULT_V2_READ_RESULT_MAX_CHARS, minimum=1, maximum=50_000))
        offset = int(_bounded_float(args.get("offset"), default=0, minimum=0, maximum=1_000_000))
        if bool(args.get("tail")):
            content = text[-max_chars:]
            offset = max(0, len(text) - len(content))
        else:
            content = text[offset : offset + max_chars]
        return {
            "command_run_id": command_run_id,
            "output_path": str(output_path),
            "offset": offset,
            "content": content,
            "chars": len(text),
            "truncated": len(content) < len(text),
            "status": "completed",
        }

    def _result_from_payload(self, call: ToolCallEnvelope, payload: dict[str, object]) -> ToolResultEnvelope:
        return self._result_from_payload_parts(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            payload=payload,
        )

    def project_result_payload(self, result: ToolResultEnvelope, payload: dict[str, object]) -> ToolResultEnvelope:
        """Rebuild a yielded command result after live closeout/final cleanup."""

        return self._result_from_payload_parts(
            lane_attempt_id=result.lane_attempt_id,
            provider_call_id=result.provider_call_id,
            mew_tool_call_id=result.mew_tool_call_id,
            tool_name=result.tool_name,
            payload=payload,
            prior_side_effects=result.side_effects,
        )

    def _result_from_payload_parts(
        self,
        *,
        lane_attempt_id: str,
        provider_call_id: str,
        mew_tool_call_id: str,
        tool_name: str,
        payload: dict[str, object],
        prior_side_effects: tuple[dict[str, object], ...] = (),
    ) -> ToolResultEnvelope:
        status = _tool_result_status(payload)
        is_error = status in {"failed", "interrupted"}
        command_run_id = str(payload.get("command_run_id") or "")
        content_refs = ()
        if payload.get("output_ref"):
            content_refs = (f"implement-v2-exec://{lane_attempt_id}/{command_run_id}/output",)
        evidence_refs = ()
        side_effects: tuple[dict[str, object], ...] = ()
        structured_payload = dict(payload)
        if command_run_id and tool_name in {"run_command", "run_tests", "poll_command", "cancel_command"}:
            side_effects, structured_payload, structured_status = self._structured_execution_evidence(
                lane_attempt_id=lane_attempt_id,
                provider_call_id=provider_call_id,
                tool_name=tool_name,
                payload=structured_payload,
                status=status,
            )
            side_effects = _merge_lifecycle_side_effects(prior_side_effects, side_effects)
            status = structured_status
            is_error = status in {"failed", "interrupted"}
        if status == "completed" and tool_name in {"run_command", "run_tests", "poll_command"}:
            evidence_refs = (f"implement-v2-exec://{lane_attempt_id}/{command_run_id}/terminal",)
        for effect in side_effects:
            ref = _execution_evidence_ref(lane_attempt_id=lane_attempt_id, effect=effect)
            if ref and ref not in evidence_refs:
                evidence_refs = (*evidence_refs, ref)
        return ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id=provider_call_id,
            mew_tool_call_id=mew_tool_call_id,
            tool_name=tool_name,
            status=status,
            is_error=is_error,
            content=(structured_payload,),
            content_refs=content_refs,
            evidence_refs=evidence_refs,
            side_effects=side_effects,
            started_at=str(structured_payload.get("started_at") or ""),
            finished_at=str(structured_payload.get("finished_at") or ""),
        )

    def _structured_execution_evidence(
        self,
        *,
        lane_attempt_id: str,
        provider_call_id: str,
        tool_name: str,
        payload: dict[str, object],
        status: str,
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object], str]:
        command_run_id = str(payload.get("command_run_id") or "")
        metadata = self.command_metadata.setdefault(command_run_id, {})
        contract = _contract_from_payload(
            payload,
            metadata=metadata,
            task_contract=self.task_contract,
            frontier_state=self.frontier_state,
            fallback_id=f"contract:{command_run_id}",
        )
        record_id = _tool_run_record_id(
            lane_attempt_id=lane_attempt_id,
            command_run_id=command_run_id,
            provider_call_id=provider_call_id,
            status=status,
            observation_index=_next_tool_observation_index(metadata),
        )
        record = ToolRunRecord(
            record_id=record_id,
            command_run_id=command_run_id,
            provider_call_id=provider_call_id,
            declared_tool_name=str(payload.get("tool_name") or tool_name),
            effective_tool_name=str(payload.get("effective_tool_name") or payload.get("tool_name") or tool_name),
            contract_id=contract.id,
            started_at=str(payload.get("started_at") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            duration_seconds=_optional_float(payload.get("duration_seconds")),
            status=_tool_run_record_status(payload, envelope_status=status),
            exit_code=_optional_int(payload.get("exit_code")),
            timed_out=bool(payload.get("timed_out")),
            interrupted=status == "interrupted",
            stdout_ref=(
                f"implement-v2-exec://{lane_attempt_id}/{command_run_id}/stdout"
                if payload.get("output_ref")
                else ""
            ),
            stderr_ref=(
                f"implement-v2-exec://{lane_attempt_id}/{command_run_id}/stderr"
                if payload.get("output_ref")
                else ""
            ),
            combined_output_ref=(
                f"implement-v2-exec://{lane_attempt_id}/{command_run_id}/output"
                if payload.get("output_ref")
                else ""
            ),
            stdout_preview=str(payload.get("stdout_tail") or payload.get("stdout") or ""),
            stderr_preview=str(payload.get("stderr_tail") or payload.get("stderr") or ""),
            output_truncated=bool(payload.get("output_truncated")),
            tool_contract_recovery=(
                dict(payload["tool_contract_recovery"]) if isinstance(payload.get("tool_contract_recovery"), dict) else None
            ),
            terminal_failure_reaction_eligible=not bool(
                isinstance(payload.get("tool_contract_recovery"), dict)
                and payload.get("tool_contract_recovery")
            ),
        )
        record = _record_with_semantic_exit(record, contract)
        record_ids = _append_record_id(metadata, record.record_id)
        command_run = CommandRun(
            command_run_id=command_run_id,
            contract_id=contract.id,
            started_at=str(payload.get("started_at") or metadata.get("started_at") or ""),
            status=record.status,
            record_ids=tuple(record_ids),
            terminal_record_id=record.record_id if _is_terminal_record(record) else "",
        )
        metadata["started_at"] = command_run.started_at
        artifact_evidence = ()
        if _is_terminal_record(record) and contract.expected_artifacts:
            artifact_evidence = check_expected_artifacts(
                contract,
                command_run_id=command_run_id,
                tool_run_record_id=record.record_id,
                run_started_at=payload.get("started_at") or command_run.started_at,
                workspace=self.workspace,
                allowed_roots=self.allowed_roots,
                pre_run_stats=metadata.get("pre_run_artifact_stats") if isinstance(metadata.get("pre_run_artifact_stats"), dict) else {},
                previous_evidence=(),
                stream_outputs=_stream_outputs_from_payload(payload, tool_run_record_id=record.record_id),
            )
        verifier = derive_verifier_evidence(contract, (record,), artifact_evidence)
        classification = classify_execution_failure(record, artifact_evidence, verifier, contract)
        finish_gate = apply_finish_gate(contract, verifier, (classification,))
        payload["execution_contract_normalized"] = contract.as_dict()
        payload["command_run"] = command_run.as_dict()
        payload["tool_run_record"] = record.as_dict()
        payload["artifact_evidence"] = [item.as_dict() for item in artifact_evidence]
        payload["verifier_evidence"] = verifier.as_dict()
        payload["failure_classification"] = classification.as_dict()
        payload["structured_finish_gate"] = finish_gate.as_dict()
        effects = (
            {"kind": "command_run", "record": command_run.as_dict()},
            {"kind": "tool_run_record", "record": record.as_dict()},
            *({"kind": "artifact_evidence", "record": item.as_dict()} for item in artifact_evidence),
            {"kind": "verifier_evidence", "record": verifier.as_dict()},
            {"kind": "failure_classification", "record": classification.as_dict()},
            {"kind": "structured_finish_gate", "record": finish_gate.as_dict()},
        )
        if status in {"failed", "interrupted"} and bool(record.semantic_exit.get("ok")) and not finish_gate.blocked:
            return tuple(effects), payload, "completed"
        if status == "completed" and finish_gate.blocked:
            payload["reason"] = "; ".join(finish_gate.reasons) or "structured execution evidence blocked completion"
            return tuple(effects), payload, "failed"
        return tuple(effects), payload, status


def _tool_result_status(payload: dict[str, object]) -> str:
    status = str(payload.get("status") or "")
    if status in NONTERMINAL_STATUSES:
        return "yielded"
    if status in TERMINAL_FAILURE_STATUSES:
        return "interrupted" if status == "killed" else "failed"
    if status in TERMINAL_SUCCESS_STATUSES:
        return "completed"
    if payload.get("exit_code") == 0:
        return "completed"
    if payload.get("exit_code") is not None or payload.get("timed_out"):
        return "failed"
    return "failed"


def _normalize_runtime_contract(
    value: object,
    *,
    task_contract: dict[str, object],
    frontier_state: dict[str, object],
    fallback_id: str,
):
    contract = normalize_execution_contract(value, task_contract=task_contract, frontier_state=frontier_state)
    if contract.id == "contract:unknown":
        contract = normalize_execution_contract(
            {**contract.as_dict(), "id": fallback_id},
            task_contract=task_contract,
            frontier_state=frontier_state,
        )
    return contract


def _contract_from_payload(
    payload: dict[str, object],
    *,
    metadata: dict[str, object],
    task_contract: dict[str, object],
    frontier_state: dict[str, object],
    fallback_id: str,
):
    normalized = payload.get("execution_contract_normalized") or metadata.get("execution_contract_normalized")
    raw = payload.get("execution_contract") or metadata.get("execution_contract")
    contract_input: dict[str, object] = {}
    if isinstance(normalized, dict):
        contract_input.update(normalized)
    if isinstance(raw, dict):
        contract_input.update(raw)
    if contract_input:
        return normalize_execution_contract(contract_input, task_contract=task_contract, frontier_state=frontier_state)
    return _normalize_runtime_contract(
        {},
        task_contract=task_contract,
        frontier_state=frontier_state,
        fallback_id=fallback_id,
    )


def _next_tool_observation_index(metadata: dict[str, object]) -> int:
    records = metadata.get("tool_run_record_ids")
    return len(records) + 1 if isinstance(records, list) else 1


def _append_record_id(metadata: dict[str, object], record_id: str) -> list[str]:
    records = metadata.setdefault("tool_run_record_ids", [])
    if not isinstance(records, list):
        records = []
        metadata["tool_run_record_ids"] = records
    records.append(record_id)
    return [str(item) for item in records if str(item)]


def _tool_run_record_id(
    *,
    lane_attempt_id: str,
    command_run_id: str,
    provider_call_id: str,
    status: str,
    observation_index: int,
) -> str:
    stable = _safe_id_part(provider_call_id, "provider-call")
    status_part = _safe_id_part(status, "status")
    digest = hashlib.sha256(
        f"{lane_attempt_id}:{command_run_id}:{provider_call_id}:{observation_index}:{status}".encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()
    return f"tool-run-record:{stable}:{observation_index}:{status_part}:{digest[:8]}"


def _tool_run_record_status(payload: dict[str, object], *, envelope_status: str):
    status = str(payload.get("status") or "")
    if status in {"running", "yielded", "completed", "failed", "timed_out", "killed", "orphaned"}:
        return status
    if envelope_status == "interrupted":
        return "interrupted"
    if envelope_status == "completed":
        return "completed"
    if envelope_status == "yielded":
        return "yielded"
    return "failed"


def _record_with_semantic_exit(record: ToolRunRecord, contract) -> ToolRunRecord:
    semantic_exit = semantic_exit_from_run(record, contract)
    return ToolRunRecord(
        record_id=record.record_id,
        command_run_id=record.command_run_id,
        provider_call_id=record.provider_call_id,
        declared_tool_name=record.declared_tool_name,
        effective_tool_name=record.effective_tool_name,
        contract_id=record.contract_id,
        substep_id=record.substep_id,
        started_at=record.started_at,
        finished_at=record.finished_at,
        duration_seconds=record.duration_seconds,
        status=record.status,
        exit_code=record.exit_code,
        timed_out=record.timed_out,
        interrupted=record.interrupted,
        semantic_exit=semantic_exit,
        stdout_ref=record.stdout_ref,
        stderr_ref=record.stderr_ref,
        combined_output_ref=record.combined_output_ref,
        stdout_preview=record.stdout_preview,
        stderr_preview=record.stderr_preview,
        output_truncated=record.output_truncated,
        tool_contract_recovery=record.tool_contract_recovery,
        terminal_failure_reaction_eligible=record.terminal_failure_reaction_eligible,
    )


def _is_terminal_record(record: ToolRunRecord) -> bool:
    return record.status in {"completed", "failed", "timed_out", "interrupted", "killed", "orphaned", "pre_spawn_error", "contract_rejected"}


def _stream_outputs_from_payload(payload: dict[str, object], *, tool_run_record_id: str) -> dict[str, object]:
    stdout = str(payload.get("stdout") or payload.get("stdout_tail") or "")
    stderr = str(payload.get("stderr") or payload.get("stderr_tail") or "")
    combined = "\n".join(item for item in (stdout, stderr) if item)
    return {
        "stdout": stdout,
        "stderr": stderr,
        "output": combined,
        tool_run_record_id: {
            "stdout": stdout,
            "stderr": stderr,
            "output": combined,
        },
    }


def _execution_evidence_ref(*, lane_attempt_id: str, effect: dict[str, object]) -> str:
    kind = str(effect.get("kind") or "")
    record = effect.get("record")
    if not isinstance(record, dict):
        return ""
    if kind == "command_run":
        identifier = str(record.get("command_run_id") or "")
    elif kind == "tool_run_record":
        identifier = str(record.get("record_id") or "")
    elif kind == "artifact_evidence":
        identifier = str(record.get("evidence_id") or "")
    elif kind == "verifier_evidence":
        identifier = str(record.get("verifier_id") or "")
    elif kind == "failure_classification":
        identifier = str(record.get("classification_id") or "")
    elif kind == "structured_finish_gate":
        identifier = "finish-gate"
    else:
        identifier = ""
    if not identifier:
        return ""
    return f"implement-v2-evidence://{lane_attempt_id}/{kind}/{_safe_id_part(identifier, kind)}"


def _merge_lifecycle_side_effects(
    prior_side_effects: tuple[dict[str, object], ...],
    current_side_effects: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    carried = []
    seen_tool_run_records: set[str] = set()
    for effect in (*prior_side_effects, *current_side_effects):
        if effect.get("kind") != "tool_run_record":
            continue
        record = effect.get("record")
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in seen_tool_run_records:
            continue
        seen_tool_run_records.add(record_id)
        carried.append(dict(effect))
    non_lifecycle_current = tuple(effect for effect in current_side_effects if effect.get("kind") != "tool_run_record")
    return (*carried, *non_lifecycle_current)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_command_argument(args: dict[str, object]) -> tuple[str, str]:
    """Return a managed-command string plus the provider argument source.

    v2 is provider-neutral, so the runtime accepts the common shapes emitted by
    coding agents instead of spending model turns on schema spelling repairs.
    The shell/argv safety policy is still enforced after normalization.
    """

    raw_argv = args.get("argv")
    if raw_argv not in (None, ""):
        if isinstance(raw_argv, (str, bytes)) or not isinstance(raw_argv, (list, tuple)):
            raise ValueError("argv must be a JSON array of command arguments")
        argv = [str(part) for part in raw_argv if str(part) != ""]
        if not argv:
            return "", "argv"
        return shlex.join(argv), "argv"
    command = args.get("command")
    command_source = "command"
    if command in (None, "") and args.get("cmd") not in (None, ""):
        command = args.get("cmd")
        command_source = "cmd"
    return str(command or "").strip(), command_source


def _use_shell_for_call(
    tool_name: str,
    command: object,
    *,
    args: dict[str, object],
    command_source: str,
) -> bool:
    if tool_name != "run_command":
        return bool(args.get("use_shell"))
    if command_source == "argv":
        return False
    if bool(args.get("use_shell")):
        return True
    return _has_unquoted_shell_surface(command)


def _workspace_path(path: object, workspace: Path) -> str:
    requested = Path(str(path or ".")).expanduser()
    if requested.is_absolute():
        return str(requested)
    return str((workspace / requested).resolve(strict=False))


def _reject_resident_mew_loop_command(command: object, *, tool_name: str) -> None:
    command_text = str(command or "")
    shell_scan_text = re.sub(r"[^A-Za-z0-9_./-]+", " ", command_text.replace("\\", "").replace("'", "").replace('"', ""))
    if is_resident_mew_loop_command(command_text) or RESIDENT_MEW_LOOP_TEXT_RE.search(shell_scan_text):
        raise ValueError(
            f"{tool_name} must not invoke resident mew loops; run bounded repository commands instead"
        )
    for segment in split_unquoted_shell_command_segments(command_text):
        if segment != command_text and is_resident_mew_loop_command(segment):
            raise ValueError(
                f"{tool_name} must not invoke resident mew loops; run bounded repository commands instead"
            )


def _reject_run_tests_shell_surface(command: object, *, use_shell: bool) -> None:
    misuse = _run_tests_shell_surface_misuse(command, use_shell=use_shell)
    if misuse is not None:
        raise RunTestsShellSurfaceMisuse(misuse)


def _preserved_command_hash(command: object) -> str:
    digest = hashlib.sha256(str(command or "").encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


def _has_unquoted_shell_surface(command: object) -> bool:
    return _has_unquoted_run_tests_shell_surface(command)


def _has_unquoted_run_tests_shell_surface(command: object) -> bool:
    return bool(_unquoted_run_tests_shell_surface_features(command))


def _run_tests_shell_surface_misuse(command: object, *, use_shell: bool) -> dict[str, object] | None:
    features: list[str] = []
    if use_shell:
        features.append("use_shell")
    features.extend(_unquoted_run_tests_shell_surface_features(command))
    if _has_explicit_shell_interpreter(command):
        features.append("explicit_shell_interpreter")
    if not features:
        return None
    unique_features = list(dict.fromkeys(features))
    return {
        "reason": "run_tests executes one argv command without a shell; use run_command for shell orchestration",
        "kind": "run_tests_shell_surface",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": "run_tests_shell_surface",
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": True,
        "terminal_failure_reaction_eligible": False,
        "features": unique_features,
        "preserved_command": str(command or ""),
        "suggested_tool": "run_command",
        "suggested_use_shell": True,
    }


def _unquoted_run_tests_shell_surface_features(command: object) -> list[str]:
    text = str(command or "")
    in_single = False
    in_double = False
    escaped = False
    index = 0
    features: list[str] = []

    def add(feature: str) -> None:
        if feature not in features:
            features.append(feature)

    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and not in_single:
            escaped = True
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if in_single or in_double:
            index += 1
            continue
        two_chars = text[index : index + 2]
        if char in {"\n", "\r"}:
            add("newline")
        elif two_chars in {"&&", "||"}:
            add("and_or")
            index += 1
        elif two_chars in {">>", "<<"}:
            add("redirect" if two_chars == ">>" else "heredoc")
            index += 1
        elif char == "|":
            add("pipe")
        elif char == ";":
            add("semicolon")
        elif char == "&":
            add("background")
        elif char in {"<", ">"}:
            add("redirect")
        index += 1
    return features


def _has_explicit_shell_interpreter(command: object) -> bool:
    try:
        parts, _env = split_command_env(command or "")
    except ValueError:
        return False
    parts = _unwrap_env_split_string(parts)
    for index, token in enumerate(parts[:-1]):
        executable = Path(str(token or "")).name
        if executable in {"bash", "sh", "zsh"} and parts[index + 1] in {"-c", "-lc", "-cl"}:
            return True
    return False


def _unwrap_env_split_string(parts: list[str]) -> list[str]:
    parts = list(parts or [])
    if not parts or Path(parts[0]).name != "env":
        return parts
    index = 1
    split_string_parts = None
    while index < len(parts):
        token = parts[index]
        if token == "--":
            index += 1
            break
        if token in {"-i", "--ignore-environment", "-0", "--null"}:
            index += 1
            continue
        if token in {"-u", "--unset", "-C", "--chdir"}:
            index += 2
            continue
        if token.startswith("-u") and token != "-u":
            index += 1
            continue
        if token.startswith("-C") and token != "-C":
            index += 1
            continue
        if token.startswith("--unset=") or token.startswith("--chdir="):
            index += 1
            continue
        if token in {"-S", "--split-string"} and index + 1 < len(parts):
            try:
                split_string_parts = shlex.split(parts[index + 1] or "")
            except ValueError:
                return parts
            index += 2
            break
        if token.startswith("-S") and token != "-S":
            try:
                split_string_parts = shlex.split(token[2:] or "")
            except ValueError:
                return parts
            index += 1
            break
        if token.startswith("--split-string="):
            try:
                split_string_parts = shlex.split(token.split("=", 1)[1] or "")
            except ValueError:
                return parts
            index += 1
            break
        if "=" in token and not token.startswith("-"):
            index += 1
            continue
        break
    if split_string_parts is not None:
        return split_string_parts + parts[index:]
    return parts[index:]


def _command_run_id(call: ToolCallEnvelope) -> str:
    stable = _safe_id_part(call.provider_call_id, "call")
    digest = hashlib.sha256(f"{call.lane_attempt_id}:{call.provider_call_id}".encode()).hexdigest()
    return f"{call.lane_attempt_id}:command:{stable}-{digest[:8]}"


def _output_path(workspace: Path, output_ref: str) -> Path:
    root = (workspace / ".mew" / "implement-v2").resolve(strict=False)
    path = (root / output_ref).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("managed exec output path escaped implement-v2 spool root") from exc
    return path


def _required_command_run_id(args: dict[str, object]) -> str:
    command_run_id = str(args.get("command_run_id") or "").strip()
    if not command_run_id:
        raise ValueError("command_run_id is required")
    return command_run_id


def _bounded_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _safe_id_part(value: object, default: str) -> str:
    text = str(value or "").strip() or default
    safe = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or default


__all__ = ["EXEC_TOOL_NAMES", "ImplementV2ManagedExecRuntime"]
