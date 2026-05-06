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
    ):
        self.workspace = Path(str(workspace or ".")).expanduser().resolve(strict=False)
        self.allowed_roots = tuple(str(root) for root in (allowed_roots or (str(self.workspace),)))
        self.allow_shell = bool(allow_shell)
        self.run_command_available = bool(run_command_available)
        self.route_run_tests_shell_surface = bool(route_run_tests_shell_surface)
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
        status = _tool_result_status(payload)
        is_error = status in {"failed", "interrupted"}
        command_run_id = str(payload.get("command_run_id") or "")
        content_refs = ()
        if payload.get("output_ref"):
            content_refs = (f"implement-v2-exec://{call.lane_attempt_id}/{command_run_id}/output",)
        evidence_refs = ()
        if status == "completed" and call.tool_name in {"run_command", "run_tests", "poll_command"}:
            evidence_refs = (f"implement-v2-exec://{call.lane_attempt_id}/{command_run_id}/terminal",)
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
        )


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
