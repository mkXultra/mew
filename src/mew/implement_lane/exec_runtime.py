"""Managed exec tool execution for the default-off implement_v2 lane."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import posixpath
import re
import shlex
import time

from ..acceptance_evidence import split_unquoted_shell_command_segments
from ..read_tools import resolve_allowed_path
from ..toolbox import ManagedCommandRunner, is_resident_mew_loop_command, split_command_env
from .artifact_checks import capture_pre_run_artifact_stats, check_expected_artifacts
from .execution_evidence import (
    CommandRun,
    ExecutionContract,
    ExpectedArtifact,
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
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(/[A-Za-z0-9_./%+@:=~-]+)")
SHELL_COMMAND_NOT_FOUND_RE = re.compile(
    r"(?:^|\n)[^:\n]+:\d+:\s+command not found:\s*(?P<tool_zsh>[A-Za-z_][A-Za-z0-9_.+-]*)\b"
    r"|(?:^|\n)(?:[^:\n]+:\s*)?command not found:\s*(?P<tool_after>[A-Za-z_][A-Za-z0-9_.+-]*)\b"
    r"|(?:^|\n)(?:[^:\n]+:\s*)?(?:line\s+\d+:\s*)?(?P<tool>[A-Za-z_][A-Za-z0-9_.+-]*):\s+command not found\b"
    r"|(?:^|\n)(?:[^:\n]+:\s*)?(?:\d+:\s*)?(?P<tool_alt>[A-Za-z_][A-Za-z0-9_.+-]*):\s+not found\b"
    r"|\bexecutable not found:\s*(?P<tool_exec>[A-Za-z_][A-Za-z0-9_.+-]*)\b",
    re.IGNORECASE,
)
SOURCE_FRONTIER_PROBE_TOOLS = frozenset({"rg", "fd", "ag", "ack", "grep", "find", "readelf", "objdump", "file", "nm"})
ADVERTISED_ARTIFACT_BEFORE_RE = re.compile(
    r"(?:will\s+be\s+)?(?:saved|written|created|generated|produced|emitted|exported|dumped)"
    r"\s*(?:as|at|to|in|into|under|:)?\s*$"
    r"|(?:writes?|saves?|creates?|generates?|produces|emits|exports|dumps)"
    r"(?:\s+[A-Za-z0-9_.-]+){0,6}\s*(?:as|at|to|in|into|under|:)\s*$",
    re.IGNORECASE,
)
ADVERTISED_ARTIFACT_AFTER_RE = re.compile(
    r"^\s*(?:was\s+)?(?:saved|written|created|generated|produced|emitted|exported|dumped)\b",
    re.IGNORECASE,
)
ADVERTISED_ARTIFACT_SUFFIXES = frozenset(
    {
        ".bmp",
        ".bin",
        ".csv",
        ".db",
        ".gif",
        ".jpeg",
        ".jpg",
        ".json",
        ".log",
        ".out",
        ".png",
        ".ppm",
        ".report",
        ".txt",
        ".wasm",
    }
)
SOURCE_MUTATION_TRACKED_SUFFIXES = frozenset(
    {
        "",
        ".c",
        ".cc",
        ".cfg",
        ".conf",
        ".cpp",
        ".css",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".lock",
        ".lua",
        ".mjs",
        ".md",
        ".py",
        ".rs",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)
SOURCE_MUTATION_TRACKED_NAMES = frozenset({"makefile", "dockerfile", "cmakelists.txt", "configure"})
RUN_TESTS_SOURCE_MUTATION_NAMES = frozenset(
    {
        "makefile",
        "dockerfile",
        "cmakelists.txt",
        "configure",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
    }
)
RUN_TESTS_SOURCE_MUTATION_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cfg",
        ".conf",
        ".cpp",
        ".css",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".lock",
        ".lua",
        ".mjs",
        ".py",
        ".rs",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }
)
SOURCE_MUTATION_IGNORED_DIRS = frozenset(
    {".git", ".hg", ".mew", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "target", "dist", "build"}
)
SOURCE_MUTATION_SNAPSHOT_MAX_FILES = 500
SOURCE_MUTATION_HASH_MAX_BYTES = 1024 * 1024
SOURCE_MUTATION_CHANGED_PATH_LIMIT = 40


class ExecToolContractMisuse(ValueError):
    """Structured exec tool-contract misuse."""

    def __init__(self, payload: dict[str, object]):
        self.payload = dict(payload)
        super().__init__(str(self.payload.get("reason") or "exec tool-contract misuse"))


class RunTestsShellSurfaceMisuse(ExecToolContractMisuse):
    """Structured run_tests tool-contract misuse.

    `run_tests` remains a verifier path, not a source mutation path. This
    exception makes shell-shaped or mutation-shaped verifier attempts
    machine-readable so v2 can route/recover safe shell verifiers without
    widening the verifier contract into patch execution.
    """


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
        source_mutation_roots: tuple[str, ...] | list[str] | None = None,
    ):
        self.workspace = Path(str(workspace or ".")).expanduser().resolve(strict=False)
        self.allowed_roots = tuple(str(root) for root in (allowed_roots or (str(self.workspace),)))
        self.source_mutation_roots = tuple(str(root) for root in (source_mutation_roots or (str(self.workspace),)))
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
        except ExecToolContractMisuse as exc:
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

    def poll_active_commands(self, *, wait_seconds: float | None = None) -> tuple[dict[str, object], ...]:
        """Poll active commands without forcing terminal closeout.

        This is intentionally weaker than ``finalize_active_commands``: it may
        return a nonterminal ``yielded`` payload and leave the process active.
        The live lane uses it to avoid spending model turns on obvious
        verifier polling while preserving long-running command lifecycles.
        """

        if self.runner.active is None:
            return ()
        handle = self.runner.active
        try:
            wait = max(0.0, float(wait_seconds or 0.0))
        except (TypeError, ValueError):
            wait = 0.0
        payload = self.runner.poll(wait_seconds=wait, command_run_id=handle.command_run_id)
        if payload.get("status") == "running":
            payload["status"] = "yielded"
        payload.update(self.command_metadata.get(str(payload.get("command_run_id") or ""), {}))
        return (payload,)

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
            mutation_misuse = _run_tests_source_mutation_misuse(command, use_shell=use_shell)
            if mutation_misuse is not None:
                raise RunTestsShellSurfaceMisuse(mutation_misuse)
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
        timeout = _bounded_float(args.get("timeout"), default=300.0, minimum=1.0, maximum=3600.0)
        foreground_budget = _bounded_float(
            args.get("foreground_budget_seconds"),
            default=min(15.0, max(0.0, timeout - 1.0)),
            minimum=0.0,
            maximum=min(30.0, timeout),
        )
        command_intent = _command_intent(args)
        raw_contract = args.get("execution_contract") if isinstance(args.get("execution_contract"), dict) else {}
        compound_misuse = _run_command_source_mutation_verifier_compound_misuse(
            command,
            raw_contract=raw_contract,
            tool_name=call.tool_name,
        )
        if compound_misuse is not None:
            raise ExecToolContractMisuse(compound_misuse)
        patch_misuse = _run_command_source_patch_misuse(
            command,
            tool_name=call.tool_name,
        )
        if patch_misuse is not None:
            raise ExecToolContractMisuse(patch_misuse)
        exploration_misuse = _run_command_source_exploration_shell_surface_misuse(
            command,
            tool_name=call.tool_name,
        )
        if exploration_misuse is not None:
            exploration_misuse["cwd"] = str(args.get("cwd") or ".")
            raise ExecToolContractMisuse(exploration_misuse)
        cwd = _workspace_path(args.get("cwd") or ".", self.workspace)
        cwd = resolve_allowed_path(cwd, self.allowed_roots)
        if not cwd.is_dir():
            raise ValueError(f"{call.tool_name} cwd is not a directory: {cwd}")
        command_run_id = _command_run_id(call)
        output_ref = f"{call.lane_attempt_id}/{command_run_id}/output.log"
        output_path = _output_path(self.workspace, output_ref)
        normalized_contract = _normalize_runtime_contract(
            raw_contract,
            task_contract=self.task_contract,
            frontier_state=self.frontier_state,
            fallback_id=f"contract:{command_run_id}",
            command_intent=command_intent,
        )
        normalized_contract, unchecked_expected_artifacts = _drop_uncheckable_expected_artifacts(
            normalized_contract,
            workspace=self.workspace,
            allowed_roots=self.allowed_roots,
        )
        raw_contract_preserved = raw_contract if not _intent_downgrades_artifact_contract(command_intent) else {}
        pre_run_artifact_stats = {}
        if normalized_contract.expected_artifacts:
            pre_run_artifact_stats = capture_pre_run_artifact_stats(
                normalized_contract.expected_artifacts,
                workspace=self.workspace,
                allowed_roots=self.allowed_roots,
            )
        pre_run_source_tree_snapshot = {}
        if effective_tool_name == "run_command":
            pre_run_source_tree_snapshot = _capture_source_tree_snapshot(
                self.source_mutation_roots,
                workspace=self.workspace,
            )
        started_epoch = time.time()
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
            "command_intent": command_intent,
            "execution_contract_normalized": normalized_contract.as_dict(),
            "pre_run_artifact_stats": pre_run_artifact_stats,
            "pre_run_source_tree_snapshot": pre_run_source_tree_snapshot,
            "started_epoch": started_epoch,
            "tool_run_record_ids": [],
            **({"unchecked_expected_artifacts": list(unchecked_expected_artifacts)} if unchecked_expected_artifacts else {}),
            **({"execution_contract": dict(raw_contract_preserved)} if raw_contract_preserved else {}),
            **({"execution_contract_downgraded": True} if raw_contract and not raw_contract_preserved else {}),
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
        payload["command_intent"] = command_intent
        if unchecked_expected_artifacts:
            payload["unchecked_expected_artifacts"] = list(unchecked_expected_artifacts)
        if raw_contract_preserved:
            payload["execution_contract"] = dict(raw_contract_preserved)
        elif raw_contract:
            payload["execution_contract_downgraded"] = True
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
        if not self.runner.has_handle(command_run_id):
            raise ValueError(f"unknown command_run_id: {command_run_id}")
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
        component_warnings = _component_command_warnings(payload)
        if component_warnings:
            payload["component_warnings"] = component_warnings
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
        advertised_artifacts: tuple[ExpectedArtifact, ...] = ()
        if _is_terminal_record(record):
            advertised_artifacts = _runtime_advertised_expected_artifacts(
                contract,
                payload,
                allowed_roots=self.allowed_roots,
            )
            if advertised_artifacts:
                contract = replace(
                    contract,
                    expected_artifacts=(*contract.expected_artifacts, *advertised_artifacts),
                )
                payload["runtime_advertised_expected_artifacts"] = [
                    artifact.as_dict() for artifact in advertised_artifacts
                ]
        if _is_terminal_record(record) and contract.expected_artifacts:
            artifact_evidence = check_expected_artifacts(
                contract,
                command_run_id=command_run_id,
                tool_run_record_id=record.record_id,
                run_started_at=payload.get("started_epoch") or metadata.get("started_epoch") or payload.get("started_at") or command_run.started_at,
                workspace=self.workspace,
                allowed_roots=self.allowed_roots,
                pre_run_stats=metadata.get("pre_run_artifact_stats") if isinstance(metadata.get("pre_run_artifact_stats"), dict) else {},
                previous_evidence=(),
                stream_outputs=_stream_outputs_from_payload(payload, tool_run_record_id=record.record_id),
            )
        source_tree_mutations = ()
        if _is_terminal_record(record) and str(
            payload.get("effective_tool_name") or payload.get("tool_name") or tool_name
        ) == "run_command":
            source_tree_mutations = _source_tree_mutation_records(
                metadata.get("pre_run_source_tree_snapshot"),
                _capture_source_tree_snapshot(self.source_mutation_roots, workspace=self.workspace),
                command_run_id=command_run_id,
                provider_call_id=provider_call_id,
            )
        verifier = derive_verifier_evidence(contract, (record,), artifact_evidence)
        classification = classify_execution_failure(record, artifact_evidence, verifier, contract)
        finish_gate = apply_finish_gate(contract, verifier, (classification,))
        payload["execution_contract_normalized"] = contract.as_dict()
        payload["command_run"] = command_run.as_dict()
        payload["tool_run_record"] = record.as_dict()
        payload["artifact_evidence"] = [item.as_dict() for item in artifact_evidence]
        payload["source_tree_mutations"] = [dict(item) for item in source_tree_mutations]
        payload["verifier_evidence"] = verifier.as_dict()
        payload["failure_classification"] = classification.as_dict()
        payload["structured_finish_gate"] = finish_gate.as_dict()
        effects = (
            {"kind": "command_run", "record": command_run.as_dict()},
            {"kind": "tool_run_record", "record": record.as_dict()},
            *({"kind": "artifact_evidence", "record": item.as_dict()} for item in artifact_evidence),
            *({"kind": "source_tree_mutation", "record": dict(item)} for item in source_tree_mutations),
            {"kind": "verifier_evidence", "record": verifier.as_dict()},
            {"kind": "failure_classification", "record": classification.as_dict()},
            {"kind": "structured_finish_gate", "record": finish_gate.as_dict()},
        )
        if status in {"failed", "interrupted"} and bool(record.semantic_exit.get("ok")) and not finish_gate.blocked:
            return tuple(effects), payload, "completed"
        if status == "completed" and finish_gate.blocked and _contract_failure_blocks_tool_status(contract):
            payload["reason"] = "; ".join(finish_gate.reasons) or "structured execution evidence blocked completion"
            return tuple(effects), payload, "failed"
        return tuple(effects), payload, status


def _runtime_advertised_expected_artifacts(
    contract: ExecutionContract,
    payload: dict[str, object],
    *,
    allowed_roots: tuple[str, ...] | list[str],
) -> tuple[ExpectedArtifact, ...]:
    if not _contract_should_enforce_advertised_artifacts(contract):
        return ()
    known_paths = {_normalize_path_identity(artifact.path or artifact.target.get("path")) for artifact in contract.expected_artifacts}
    known_suffixes = {
        suffix
        for suffix in (
            Path(str(artifact.path or artifact.target.get("path") or "")).suffix.casefold()
            for artifact in contract.expected_artifacts
        )
        if suffix
    }
    artifacts: list[ExpectedArtifact] = []
    for path in _advertised_artifact_paths_from_payload(payload):
        identity = _normalize_path_identity(path)
        if not identity or identity in known_paths:
            continue
        if known_suffixes and Path(path).suffix.casefold() not in known_suffixes:
            continue
        if not _path_allowed_by_roots(path, allowed_roots):
            continue
        known_paths.add(identity)
        artifacts.append(
            ExpectedArtifact(
                id=path,
                kind="file",
                target={"type": "path", "path": path},
                path=path,
                required=True,
                source="runtime_inferred",
                confidence="medium",
                freshness="modified_after_run_start",
                checks=(
                    {"type": "exists", "severity": "blocking"},
                    {"type": "non_empty", "severity": "blocking"},
                    {"type": "mtime_after", "severity": "blocking"},
                ),
            )
        )
    return tuple(artifacts)


def _contract_should_enforce_advertised_artifacts(contract: ExecutionContract) -> bool:
    if contract.acceptance_kind != "external_verifier" and contract.proof_role != "verifier":
        return False
    return contract.role in {"runtime", "verify", "test", "compound"}


def _contract_failure_blocks_tool_status(contract: ExecutionContract) -> bool:
    """Return whether structured evidence failure should make the tool fail."""

    if (
        contract.role == "diagnostic"
        and contract.acceptance_kind in {"not_acceptance", "progress_only"}
        and contract.proof_role in {"none", "progress", "negative_diagnostic"}
    ):
        return False
    return True


def _advertised_artifact_paths_from_payload(payload: dict[str, object]) -> tuple[str, ...]:
    text = "\n".join(
        str(payload.get(key) or "")
        for key in ("stdout", "stdout_tail", "stderr", "stderr_tail")
        if payload.get(key)
    )
    if not text:
        return ()
    paths: list[str] = []
    for match in ABSOLUTE_PATH_RE.finditer(text):
        path = _strip_path_trailing_punctuation(match.group(1))
        if not _artifact_like_path(path):
            continue
        if not _has_runtime_artifact_producer_phrase(text, match.start(), match.end()):
            continue
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def _has_runtime_artifact_producer_phrase(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 96) : start]
    after = text[end : min(len(text), end + 48)]
    return ADVERTISED_ARTIFACT_BEFORE_RE.search(before) is not None or ADVERTISED_ARTIFACT_AFTER_RE.search(after) is not None


def _artifact_like_path(path: str) -> bool:
    if not path or path.endswith("/"):
        return False
    if "%" in path:
        return False
    normalized = path.casefold()
    if "/.mew/" in normalized or "/.git/" in normalized:
        return False
    suffix = Path(path).suffix.casefold()
    return suffix in ADVERTISED_ARTIFACT_SUFFIXES


def _strip_path_trailing_punctuation(path: str) -> str:
    return str(path or "").rstrip("`'\".,;:)]}")


def _normalize_path_identity(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve(strict=False)).casefold()


def _path_allowed_by_roots(path: str, allowed_roots: tuple[str, ...] | list[str]) -> bool:
    try:
        candidate = Path(path).expanduser().resolve(strict=False)
    except OSError:
        return False
    for root in allowed_roots:
        try:
            root_path = Path(str(root)).expanduser().resolve(strict=False)
        except OSError:
            continue
        if candidate == root_path or _is_relative_to(candidate, root_path):
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _capture_source_tree_snapshot(
    roots: tuple[str, ...] | list[str],
    *,
    workspace: Path,
) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    truncated = False
    for root in roots or (str(workspace),):
        root_path = Path(str(root or workspace)).expanduser()
        if not root_path.is_absolute():
            root_path = workspace / root_path
        root_path = root_path.resolve(strict=False)
        candidates = (root_path,) if root_path.is_file() else _iter_source_tree_candidates(root_path)
        for path in candidates:
            if len(files) >= SOURCE_MUTATION_SNAPSHOT_MAX_FILES:
                truncated = True
                break
            item = _source_tree_file_fingerprint(path)
            if not item:
                continue
            files[str(item["path"])] = item
        if truncated:
            break
    return {
        "schema_version": 1,
        "file_count": len(files),
        "truncated": truncated,
        "files": files,
    }


def _iter_source_tree_candidates(root: Path):
    if not root.exists() or not root.is_dir():
        return ()

    def walk():
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                entries = sorted(current.iterdir(), key=lambda item: item.name)
            except OSError:
                continue
            for path in entries:
                if path.name in SOURCE_MUTATION_IGNORED_DIRS:
                    continue
                try:
                    if path.is_dir() and not path.is_symlink():
                        stack.append(path)
                        continue
                except OSError:
                    continue
                yield path

    return walk()


def _source_tree_file_fingerprint(path: Path) -> dict[str, object]:
    try:
        if path.is_symlink() or not path.is_file() or not _should_track_source_mutation_path(path):
            return {}
        stat = path.stat()
    except OSError:
        return {}
    sha256 = ""
    if stat.st_size <= SOURCE_MUTATION_HASH_MAX_BYTES:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
        except OSError:
            sha256 = ""
    return {
        "path": str(path.resolve(strict=False)),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": sha256,
    }


def _should_track_source_mutation_path(path: Path) -> bool:
    name = path.name.casefold()
    if name in SOURCE_MUTATION_TRACKED_NAMES:
        return True
    return path.suffix.casefold() in SOURCE_MUTATION_TRACKED_SUFFIXES


def _source_tree_mutation_records(
    before_snapshot: object,
    after_snapshot: object,
    *,
    command_run_id: str,
    provider_call_id: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(before_snapshot, dict) or not isinstance(after_snapshot, dict):
        return ()
    before_files = before_snapshot.get("files")
    after_files = after_snapshot.get("files")
    if not isinstance(before_files, dict) or not isinstance(after_files, dict):
        return ()
    changes: list[dict[str, object]] = []
    for path in sorted(set(before_files) | set(after_files)):
        before = before_files.get(path)
        after = after_files.get(path)
        if before is None and isinstance(after, dict):
            changes.append(_source_tree_change(path, "created", after=after))
        elif after is None and isinstance(before, dict):
            changes.append(_source_tree_change(path, "deleted", before=before))
        elif isinstance(before, dict) and isinstance(after, dict) and _source_tree_fingerprint_changed(before, after):
            changes.append(_source_tree_change(path, "modified", before=before, after=after))
    if not changes:
        return ()
    return (
        {
            "schema_version": 1,
            "command_run_id": command_run_id,
            "provider_call_id": provider_call_id,
            "source": "bounded_source_tree_snapshot",
            "changed_count": len(changes),
            "changes": changes[:SOURCE_MUTATION_CHANGED_PATH_LIMIT],
            "truncated": bool(before_snapshot.get("truncated") or after_snapshot.get("truncated"))
            or len(changes) > SOURCE_MUTATION_CHANGED_PATH_LIMIT,
        },
    )


def _source_tree_fingerprint_changed(before: dict[str, object], after: dict[str, object]) -> bool:
    before_sha = str(before.get("sha256") or "")
    after_sha = str(after.get("sha256") or "")
    if before_sha and after_sha:
        return before_sha != after_sha
    return before.get("size") != after.get("size") or before.get("mtime_ns") != after.get("mtime_ns")


def _source_tree_change(
    path: str,
    change: str,
    *,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "path": path,
        "change": change,
        "before_sha256": str((before or {}).get("sha256") or ""),
        "after_sha256": str((after or {}).get("sha256") or ""),
        "before_size": (before or {}).get("size"),
        "after_size": (after or {}).get("size"),
    }


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
    command_intent: str = "",
):
    raw_value = value if isinstance(value, dict) else {}
    if _intent_downgrades_artifact_contract(command_intent):
        return normalize_execution_contract(
            {
                "id": str(raw_value.get("id") or fallback_id),
                "role": "diagnostic",
                "stage": "diagnostic",
                "purpose": "diagnostic",
                "proof_role": "negative_diagnostic" if command_intent == "diagnostic" else "none",
                "acceptance_kind": "not_acceptance",
                "expected_exit": {"mode": "any"},
                "expected_artifacts": [],
            },
            task_contract=None,
            frontier_state=None,
        )
    has_explicit_contract = bool(raw_value)
    frontier_for_inference = (
        frontier_state
        if has_explicit_contract or bool(frontier_state.get("_same_turn_model_declared_final_artifact"))
        else None
    )
    contract = normalize_execution_contract(
        value,
        task_contract=task_contract if has_explicit_contract else None,
        frontier_state=frontier_for_inference,
    )
    if contract.id == "contract:unknown":
        contract = normalize_execution_contract(
            {**contract.as_dict(), "id": fallback_id},
            task_contract=task_contract if has_explicit_contract else None,
            frontier_state=frontier_for_inference,
        )
    return contract


def _command_intent(args: dict[str, object]) -> str:
    value = str(args.get("command_intent") or "").strip().lower()
    if value in {"probe", "diagnostic", "build", "runtime", "verify", "finish_verifier"}:
        return value
    return ""


def _intent_downgrades_artifact_contract(command_intent: str) -> bool:
    return command_intent in {"probe", "diagnostic"}


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
    if isinstance(raw, dict):
        contract_input.update(raw)
    if isinstance(normalized, dict):
        contract_input.update(normalized)
    if contract_input:
        has_raw_contract = isinstance(raw, dict) and bool(raw)
        use_inference = has_raw_contract and not isinstance(normalized, dict)
        return normalize_execution_contract(
            contract_input,
            task_contract=task_contract if use_inference else None,
            frontier_state=frontier_state if use_inference else None,
        )
    return _normalize_runtime_contract(
        {},
        task_contract=task_contract,
        frontier_state=frontier_state,
        fallback_id=fallback_id,
    )


def _drop_uncheckable_expected_artifacts(
    contract: ExecutionContract,
    *,
    workspace: Path,
    allowed_roots: tuple[str, ...] | list[str],
) -> tuple[ExecutionContract, tuple[dict[str, object], ...]]:
    checkable: list[ExpectedArtifact] = []
    unchecked: list[dict[str, object]] = []
    for artifact in contract.expected_artifacts:
        reason = _uncheckable_artifact_reason(artifact, workspace=workspace, allowed_roots=allowed_roots)
        if reason:
            unchecked.append(
                {
                    "id": artifact.id,
                    "path": artifact.path or artifact.target.get("path") or "",
                    "kind": artifact.kind,
                    "source": artifact.source,
                    "reason": reason,
                    "required_next_action": (
                        "The command may still run, but mew cannot perform internal artifact checks for this path. "
                        "Use a shell-level verifier assertion or write/check an artifact inside the allowed roots."
                    ),
                }
            )
        else:
            checkable.append(artifact)
    if not unchecked:
        return contract, ()
    return replace(contract, expected_artifacts=tuple(checkable)), tuple(unchecked)


def _uncheckable_artifact_reason(
    artifact: ExpectedArtifact,
    *,
    workspace: Path,
    allowed_roots: tuple[str, ...] | list[str],
) -> str:
    target_type = str(artifact.target.get("type") or "")
    if not target_type and artifact.kind in {"stdout", "stderr"}:
        target_type = "stream"
    if target_type and target_type != "path":
        return ""
    raw_path = str(artifact.path or artifact.target.get("path") or "").strip()
    if not raw_path:
        return ""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    if _path_allowed_by_roots(str(candidate), allowed_roots):
        return ""
    allowed = ", ".join(str(Path(str(root)).expanduser().resolve(strict=False)) for root in allowed_roots)
    return f"artifact path is outside allowed roots: {candidate.resolve(strict=False)}; allowed={allowed}"


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


def _component_command_warnings(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return non-terminal warnings for component failures hidden by shell orchestration."""

    command = str(payload.get("command") or "")
    stderr_output = "\n".join(
        str(payload.get(key) or "")
        for key in ("stderr", "stderr_tail")
        if payload.get(key) not in (None, "")
    )
    stdout_output = "\n".join(
        str(payload.get(key) or "") for key in ("stdout", "stdout_tail") if payload.get(key) not in (None, "")
    )
    output = stderr_output
    if not output and "2>&1" in command:
        output = stdout_output
    if not output:
        return []
    masked_by_success = payload.get("exit_code") == 0
    warnings: list[dict[str, object]] = []
    seen: set[str] = set()
    for match in SHELL_COMMAND_NOT_FOUND_RE.finditer(output):
        tool = str(
            match.group("tool")
            or match.group("tool_zsh")
            or match.group("tool_after")
            or match.group("tool_alt")
            or match.group("tool_exec")
            or ""
        ).strip()
        if not tool or tool in seen:
            continue
        seen.add(tool)
        subclass = "source_frontier_probe_unavailable" if tool in SOURCE_FRONTIER_PROBE_TOOLS else "command_component_unavailable"
        recommendation = (
            "Treat the source frontier as incomplete; rerun the cheap probe with an available fallback "
            "such as glob/search_text, grep -R, find, Python, or a preflighted tool before editing."
            if subclass == "source_frontier_probe_unavailable"
            else "Retry with an available exact tool or report the unavailable executable as the blocker."
        )
        warnings.append(
            {
                "kind": "command_component_warning",
                "failure_class": "tool_availability_gap",
                "failure_subclass": subclass,
                "tool": tool,
                "masked_by_success_exit": masked_by_success,
                "command_had_shell_recovery": _has_shell_recovery_surface(command),
                "recommended_next_action": recommendation,
            }
        )
    return warnings


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
    elif kind == "source_tree_mutation":
        identifier = str(record.get("command_run_id") or record.get("provider_call_id") or "")
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
        argv = _normalize_argv_argument(raw_argv, argument_name="argv")
        if not argv:
            return "", "argv"
        return shlex.join(argv), "argv"
    command = args.get("command")
    command_source = "command"
    if command in (None, "") and args.get("cmd") not in (None, ""):
        command = args.get("cmd")
        command_source = "cmd"
    if isinstance(command, (list, tuple)):
        argv = _normalize_argv_argument(command, argument_name=command_source)
        if not argv:
            return "", f"{command_source}_argv"
        return shlex.join(argv), f"{command_source}_argv"
    return str(command or "").strip(), command_source


def _normalize_argv_argument(value: object, *, argument_name: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{argument_name} must be a JSON array of command arguments")
    return [str(part) for part in value if str(part) != ""]


def _use_shell_for_call(
    tool_name: str,
    command: object,
    *,
    args: dict[str, object],
    command_source: str,
) -> bool:
    if tool_name != "run_command":
        return bool(args.get("use_shell"))
    if command_source in {"argv", "command_argv", "cmd_argv"}:
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


def _has_shell_recovery_surface(command: object) -> bool:
    features = _unquoted_run_tests_shell_surface_features(command)
    return "and_or" in features or "semicolon" in features or "pipe" in features


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


def _run_tests_source_mutation_misuse(command: object, *, use_shell: bool) -> dict[str, object] | None:
    paths = _source_like_mutation_paths(command)
    if not paths:
        return None
    features: list[str] = ["source_tree_mutation"]
    if use_shell:
        features.append("use_shell")
    features.extend(_unquoted_run_tests_shell_surface_features(command))
    unique_features = list(dict.fromkeys(features))
    return {
        "reason": (
            "run_tests must not mutate source-like files; apply the source change with "
            "write_file/edit_file/apply_patch, or use an explicit bounded run_command writer for "
            "large generated files, then run a separate verifier"
        ),
        "kind": "run_tests_source_mutation",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": "run_tests_source_mutation",
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": False,
        "terminal_failure_reaction_eligible": False,
        "features": unique_features,
        "preserved_command": str(command or ""),
        "suggested_tool": "write_file/edit_file/apply_patch",
        "suggested_use_shell": False,
        "mutation_paths": list(paths[:8]),
    }


def _run_command_source_mutation_verifier_compound_misuse(
    command: object,
    *,
    raw_contract: dict[str, object],
    tool_name: str,
) -> dict[str, object] | None:
    if tool_name != "run_command" or not _raw_execution_contract_is_verifier_like(raw_contract):
        return None
    paths = _source_like_mutation_paths(command)
    if not paths:
        return None
    return {
        "reason": (
            "run_command verifier commands must not also mutate source-like files; split this into "
            "a source mutation step with write_file/edit_file/apply_patch or an explicit bounded "
            "run_command writer, then run a separate verifier command"
        ),
        "kind": "run_command_source_mutation_verifier_compound",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": "run_command_source_mutation_verifier_compound",
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": False,
        "terminal_failure_reaction_eligible": False,
        "features": ["source_tree_mutation", "verifier_contract"],
        "preserved_command": str(command or ""),
        "suggested_tool": "write_file/edit_file/apply_patch",
        "suggested_use_shell": False,
        "mutation_paths": list(paths[:8]),
    }


def _run_command_source_patch_misuse(
    command: object,
    *,
    tool_name: str,
) -> dict[str, object] | None:
    if tool_name != "run_command":
        return None
    mutation_paths = _source_like_mutation_paths(command)
    if not mutation_paths:
        return None
    read_paths = _source_like_read_paths(command)
    if not read_paths:
        return None
    read_path_set = set(read_paths)
    common_paths = tuple(path for path in mutation_paths if path in read_path_set)
    if not common_paths:
        return None
    return {
        "reason": (
            "run_command must not patch an existing source-like file by reading and writing the "
            "same path; use write_file/edit_file/apply_patch for source patches, then run a "
            "separate verifier. Reserve bounded run_command writers for large generated files "
            "that are not patching an existing source path."
        ),
        "kind": "run_command_source_patch_shell_surface",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": "run_command_source_patch_shell_surface",
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": False,
        "terminal_failure_reaction_eligible": False,
        "features": ["source_tree_mutation", "source_tree_read", "same_path_patch"],
        "preserved_command": str(command or ""),
        "suggested_tool": "write_file/edit_file/apply_patch",
        "suggested_use_shell": False,
        "mutation_paths": list(mutation_paths[:8]),
        "read_paths": list(read_paths[:8]),
        "common_paths": list(common_paths[:8]),
    }


def _run_command_source_exploration_shell_surface_misuse(
    command: object,
    *,
    tool_name: str,
) -> dict[str, object] | None:
    if tool_name != "run_command":
        return None
    features = _source_exploration_shell_surface_features(command)
    if not features:
        return None
    return {
        "reason": (
            "run_command must not replace native source exploration with a broad shell/Python "
            "source scanner. Use glob/search_text/read_file for source discovery, or one bounded "
            "grep/rg/sed probe over a specific path, then make a source mutation with "
            "write_file/edit_file/apply_patch."
        ),
        "kind": "run_command_source_exploration_shell_surface",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": "run_command_source_exploration_shell_surface",
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": True,
        "terminal_failure_reaction_eligible": False,
        "features": features,
        "preserved_command": str(command or ""),
        "suggested_tool": "glob/search_text/read_file",
        "suggested_use_shell": False,
    }


def _source_exploration_shell_surface_features(command: object) -> list[str]:
    text = str(command or "")
    if not text.strip():
        return []
    lowered = text.casefold()
    features: list[str] = []

    def add(feature: str) -> None:
        if feature not in features:
            features.append(feature)

    python_command_re = (
        r"(?:^|[;&|]\s*)(?:(?:\S*/)?env\s+)?(?:\S*/)?python(?:\d+(?:\.\d+)?)?\s+(?:-|-[A-Za-z]*c\b)"
    )
    if re.search(python_command_re, text):
        add("python_shell_surface")
    if "<<" in text and re.search(
        r"(?:^|[;&|]\s*)(?:(?:\S*/)?env\s+)?(?:\S*/)?python(?:\d+(?:\.\d+)?)?\b", text
    ):
        add("python_heredoc")
    recursive_patterns = (
        r"\bos\.walk\s*\(",
        r"\bPath\s*\([^)]*\)\s*\.\s*rglob\s*\(",
        r"\bpathlib\.Path\s*\([^)]*\)\s*\.\s*rglob\s*\(",
        r"\bglob\.glob\s*\([^)]*recursive\s*=\s*True",
        r"\bfind\s+[^|;&]+(?:\s+-type\s+f|\s+-name\s+|\s+-regex\s+)",
    )
    if _text_matches_any(text, recursive_patterns):
        add("recursive_source_walk")
    source_walk_root = (
        r"(?:\.|\.\/|/app|/workspace|/workspaces/[^'\"]*|"
        r"(?:\.\/)?(?:src|source|tests?|include|lib|libs|app|apps|packages|doomgeneric)(?:\/[^'\"]*)?)"
    )
    workspace_recursive_patterns = (
        rf"\bos\.walk\s*\(\s*['\"]{source_walk_root}['\"]",
        rf"\bPath\s*\(\s*['\"]{source_walk_root}['\"]\s*\)\s*\.\s*rglob\s*\(",
        rf"\bpathlib\.Path\s*\(\s*['\"]{source_walk_root}['\"]\s*\)\s*\.\s*rglob\s*\(",
    )
    if _text_matches_any(text, workspace_recursive_patterns):
        add("workspace_recursive_walk")
    source_read_patterns = (
        r"\bopen\s*\([^)]*\)\s*\.\s*read\s*\(",
        r"\bopen\s*\([^)]*['\"]r",
        r"\bread_text\s*\(",
        r"\bread_bytes\s*\(",
        r"\breadlines\s*\(",
    )
    if _text_matches_any(text, source_read_patterns):
        add("source_read_loop")
    snippet_patterns = (
        r"\bprint\s*\(",
        r"\bsys\.stdout\.write\s*\(",
        r"\bjson\.dump",
    )
    if _text_matches_any(text, snippet_patterns):
        add("snippet_emission")
    source_suffix_hits = re.findall(
        r"\.(?:c|cc|cpp|cxx|h|hh|hpp|py|js|ts|tsx|jsx|rs|go|java|sh|mk|makefile)\b",
        lowered,
    )
    if source_suffix_hits:
        add("source_suffix_filter")
    if len(source_suffix_hits) >= 2:
        add("multiple_source_suffixes")
    if len(text) > 2000:
        add("large_inline_scanner")

    broad_python_scan = (
        ("python_shell_surface" in features or "python_heredoc" in features)
        and "recursive_source_walk" in features
        and (
            ("source_read_loop" in features and "source_suffix_filter" in features)
            or ("source_read_loop" in features and "workspace_recursive_walk" in features)
            or "multiple_source_suffixes" in features
        )
    )
    broad_find_scan = (
        "recursive_source_walk" in features
        and ("snippet_emission" in features or "multiple_source_suffixes" in features)
        and (" xargs " in f" {lowered} " or " -exec " in lowered)
    )
    if broad_python_scan or broad_find_scan:
        return features
    return []


def _raw_execution_contract_is_verifier_like(raw_contract: dict[str, object]) -> bool:
    if not isinstance(raw_contract, dict) or not raw_contract:
        return False
    contract = normalize_execution_contract(raw_contract, task_contract=None, frontier_state=None)
    return _execution_contract_is_verifier_like(contract) or any(
        _execution_substep_is_verifier_like(substep) for substep in contract.substeps
    )


def _execution_contract_is_verifier_like(contract: ExecutionContract) -> bool:
    return (
        contract.verifier_required
        or contract.role == "verify"
        or contract.stage in {"verification", "artifact_proof", "default_smoke", "custom_runtime_smoke"}
        or contract.purpose in {"verification", "artifact_proof", "smoke"}
        or contract.proof_role in {"verifier", "final_artifact", "default_smoke", "custom_runtime_smoke"}
        or contract.acceptance_kind
        in {"external_verifier", "candidate_final_proof", "candidate_runtime_smoke", "candidate_artifact_proof"}
    )


def _execution_substep_is_verifier_like(substep: object) -> bool:
    return (
        bool(getattr(substep, "verifier_required", False))
        or getattr(substep, "role", "") == "verify"
        or getattr(substep, "stage", "") in {"verification", "artifact_proof", "default_smoke", "custom_runtime_smoke"}
        or getattr(substep, "purpose", "") in {"verification", "artifact_proof", "smoke"}
        or getattr(substep, "proof_role", "") in {"verifier", "final_artifact", "default_smoke", "custom_runtime_smoke"}
        or getattr(substep, "acceptance_kind", "")
        in {"external_verifier", "candidate_final_proof", "candidate_runtime_smoke", "candidate_artifact_proof"}
    )


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


def _source_like_mutation_paths(command: object) -> tuple[str, ...]:
    text = str(command or "")
    if not text.strip():
        return ()
    paths: list[str] = []
    paths.extend(_shell_redirection_write_paths(text))
    if _text_matches_any(
        text,
        (
            r"\b(?:writefilesync|writeFileSync|write_text|write_bytes)\b",
            r"\bopen\s*\([^)]*,\s*['\"][^'\"]*[wax+]",
            r"\bopen\s*\([^)]*,[^)]*\bmode\s*=\s*['\"][^'\"]*[wax+]",
        ),
    ):
        paths.extend(_shell_write_api_paths(text))
    if _text_matches_any(text, (r"(?:^|[;&|()]\s*)(?:sed\s+-i|perl\s+-pi|cp|mv|install|touch)\b",)):
        paths.extend(_shell_token_paths(text))
    seen: set[str] = set()
    source_like: list[str] = []
    for path in paths:
        normalized = _normalize_source_path_identity(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _shell_path_is_source_like(normalized):
            source_like.append(normalized)
    return tuple(source_like)


def _source_like_read_paths(command: object) -> tuple[str, ...]:
    text = str(command or "")
    if not text.strip():
        return ()
    paths = list(_shell_read_api_paths(text))
    if _text_matches_any(text, (r"(?:^|[;&|()]\s*)(?:sed\s+-i|perl\s+-pi)\b",)):
        paths.extend(_shell_token_paths(text))
    seen: set[str] = set()
    source_like: list[str] = []
    for path in paths:
        normalized = _normalize_source_path_identity(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _shell_path_is_source_like(normalized):
            source_like.append(normalized)
    return tuple(source_like)


def _shell_redirection_write_paths(command: str) -> tuple[str, ...]:
    paths: list[str] = []
    index = 0
    while index < len(command):
        operator_index = _next_unquoted_redirection_index(command, start=index)
        if operator_index < 0:
            break
        next_index = operator_index + 1
        if next_index < len(command) and command[next_index] in {">", "|"}:
            next_index += 1
        while next_index < len(command) and command[next_index].isspace():
            next_index += 1
        word, end_index = _read_shell_word(command, next_index)
        if word:
            paths.append(word)
        index = max(end_index, operator_index + 1)
    for segment in split_unquoted_shell_command_segments(command):
        try:
            tee_tokens = shlex.split(segment)
        except ValueError:
            tee_tokens = re.split(r"\s+", segment)
        tee_index = _tee_command_index(tee_tokens)
        if tee_index < 0:
            continue
        paths.extend(token for token in tee_tokens[tee_index + 1 :] if token and not token.startswith("-"))
    return tuple(paths)


def _tee_command_index(tokens: list[str]) -> int:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" in token and not token.startswith("-") and token.split("=", 1)[0].replace("_", "A").isalnum():
            index += 1
            continue
        if token == "env":
            index += 1
            continue
        if token == "command":
            index += 1
            continue
        return index if token == "tee" else -1
    return -1


def _next_unquoted_redirection_index(text: str, *, start: int = 0) -> int:
    in_single = False
    in_double = False
    escaped = False
    index = max(0, int(start))
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
        if not in_single and not in_double and char == ">":
            return index
        index += 1
    return -1


def _read_shell_word(text: str, start: int) -> tuple[str, int]:
    chars: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    index = max(0, int(start))
    while index < len(text):
        char = text[index]
        if escaped:
            chars.append(char)
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
        if not in_single and not in_double and (char.isspace() or char in {";", "&", "|", "(", ")"}):
            break
        chars.append(char)
        index += 1
    return "".join(chars), index


def _shell_write_api_paths(command: str) -> tuple[str, ...]:
    paths: list[str] = [
        match.group(1)
        for match in re.finditer(
            r"(?:pathlib\.)?Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\.\s*write_(?:text|bytes)\s*\(",
            command,
            re.IGNORECASE,
        )
    ]
    string_vars = _shell_string_variable_assignments(command)
    for match in re.finditer(
        r"\b(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:pathlib\.)?Path\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)",
        command,
        re.IGNORECASE,
    ):
        variable = re.escape(match.group("var"))
        if re.search(rf"\b{variable}\s*\.\s*write_(?:text|bytes)\s*\(", command, re.IGNORECASE):
            paths.append(match.group("path"))
    for variable, variable_paths in string_vars.items():
        escaped = re.escape(variable)
        if re.search(
            rf"(?:writefilesync|writeFileSync)\s*\(\s*{escaped}\b",
            command,
            re.IGNORECASE,
        ):
            paths.extend(variable_paths)
    paths.extend(_python_open_variable_paths(command, string_vars, access="write"))
    paths.extend(
        match.group(1)
        for match in re.finditer(
            r"(?:writefilesync|writeFileSync)\s*\(\s*['\"]([^'\"]+)['\"]",
            command,
            re.IGNORECASE,
        )
    )
    paths.extend(
        match.group(1)
        for match in re.finditer(
            r"\bopen\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]*[wax+]",
            command,
            re.IGNORECASE,
        )
    )
    return tuple(paths)


def _shell_read_api_paths(command: str) -> tuple[str, ...]:
    paths: list[str] = [
        match.group(1)
        for match in re.finditer(
            r"(?:pathlib\.)?Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\.\s*read_(?:text|bytes)\s*\(",
            command,
            re.IGNORECASE,
        )
    ]
    string_vars = _shell_string_variable_assignments(command)
    for match in re.finditer(
        r"\b(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:pathlib\.)?Path\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)",
        command,
        re.IGNORECASE,
    ):
        variable = re.escape(match.group("var"))
        if re.search(rf"\b{variable}\s*\.\s*read_(?:text|bytes)\s*\(", command, re.IGNORECASE):
            paths.append(match.group("path"))
    for variable, variable_paths in string_vars.items():
        escaped = re.escape(variable)
        if re.search(
            rf"(?:readfilesync|readFileSync)\s*\(\s*{escaped}\b",
            command,
            re.IGNORECASE,
        ):
            paths.extend(variable_paths)
    paths.extend(_python_open_variable_paths(command, string_vars, access="read"))
    paths.extend(
        match.group(1)
        for match in re.finditer(
            r"(?:readfilesync|readFileSync)\s*\(\s*['\"]([^'\"]+)['\"]",
            command,
            re.IGNORECASE,
        )
    )
    paths.extend(
        match.group(1)
        for match in re.finditer(r"\bopen\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", command, re.IGNORECASE)
    )
    paths.extend(
        match.group(1)
        for match in re.finditer(
            r"\bopen\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]*r[^'\"]*['\"]",
            command,
            re.IGNORECASE,
        )
    )
    return tuple(paths)


def _shell_string_variable_assignments(command: str) -> dict[str, tuple[str, ...]]:
    assignments: dict[str, list[str]] = {}
    for match in re.finditer(
        r"\b(?:const|let|var)?\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*['\"](?P<path>[^'\"]+)['\"]",
        command,
        re.IGNORECASE,
    ):
        variable = match.group("var")
        path = match.group("path")
        variable_paths = assignments.setdefault(variable, [])
        if path not in variable_paths:
            variable_paths.append(path)
    return {variable: tuple(paths) for variable, paths in assignments.items()}


def _python_open_variable_paths(
    command: str,
    assignments: dict[str, tuple[str, ...]],
    *,
    access: str,
) -> tuple[str, ...]:
    paths: list[str] = []
    for variable, variable_paths in assignments.items():
        escaped = re.escape(variable)
        for match in re.finditer(rf"\bopen\s*\(\s*{escaped}\b(?P<rest>[^)]*)\)", command, re.IGNORECASE):
            mode = _python_open_mode_from_rest(match.group("rest"))
            if access == "write":
                if _python_open_mode_can_write(mode):
                    paths.extend(variable_paths)
            elif _python_open_mode_can_read(mode):
                paths.extend(variable_paths)
    return tuple(paths)


def _python_open_mode_from_rest(rest: str) -> str | None:
    text = str(rest or "").strip()
    if not text:
        return None
    if not text.startswith(","):
        return None
    text = text[1:].lstrip()
    positional = re.match(r"['\"](?P<mode>[^'\"]*)['\"]", text)
    if positional:
        return positional.group("mode")
    keyword = re.search(r"\bmode\s*=\s*['\"](?P<mode>[^'\"]*)['\"]", text)
    if keyword:
        return keyword.group("mode")
    return None


def _python_open_mode_can_read(mode: str | None) -> bool:
    if mode is None:
        return True
    lowered = mode.casefold()
    if "r" in lowered or "+" in lowered:
        return True
    return not any(char in lowered for char in ("w", "a", "x"))


def _python_open_mode_can_write(mode: str | None) -> bool:
    if mode is None:
        return False
    lowered = mode.casefold()
    return any(char in lowered for char in ("w", "a", "x", "+"))


def _shell_token_paths(command: str) -> tuple[str, ...]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = re.split(r"\s+", command)
    return tuple(token for token in tokens if token and not token.startswith("-"))


def _normalize_shell_path_token(path: object) -> str:
    return str(path or "").strip().strip("'\"")


def _normalize_source_path_identity(path: object) -> str:
    raw = _normalize_shell_path_token(path)
    if not raw:
        return ""
    if raw.startswith(("$", "-")):
        return raw
    normalized = posixpath.normpath(raw.replace("\\", "/"))
    return "" if normalized == "." else normalized


def _shell_path_is_source_like(path: object) -> bool:
    raw = _normalize_source_path_identity(path)
    if not raw or raw.startswith(("-", "$")) or raw.startswith(("/tmp/", "tmp/", "/var/tmp/")):
        return False
    name = Path(raw).name.casefold()
    if name in RUN_TESTS_SOURCE_MUTATION_NAMES:
        return True
    suffix = Path(name).suffix.casefold()
    return suffix in RUN_TESTS_SOURCE_MUTATION_SUFFIXES


def _text_matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


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
