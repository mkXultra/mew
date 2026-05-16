"""Native finish-gate contracts for implement_v2.

This module is intentionally a boundary module first.  Phase 1 does not switch
live completion behavior; it freezes the public data shapes and pure helpers
that later phases will wire into the native harness.

The core design decision is pre-release and intentionally not backward
compatible with the legacy hot completion path: typed evidence, oracle
obligations, and resolver records are diagnostics/sidecars after a trusted final
verifier closeout exits 0.  They are not the hot completion authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import shlex
from typing import Literal, Mapping


NATIVE_FINISH_GATE_SCHEMA_VERSION = 1
NATIVE_FINISH_GATE_POLICY_VERSION = "native-finish-gate-v1"
NATIVE_FINISH_GATE_DECISIONS_FILE = "native_finish_gate_decisions.jsonl"

FinishVerifierSource = Literal[
    "configured_verifier",
    "auto_detected_verifier",
    "finish_verifier_planner",
]
FinishGateStatus = Literal["completed", "blocked_continue", "blocked_return"]
FinishGateResult = Literal["allow", "block"]
FinishCloseoutStatus = Literal[
    "not_run",
    "completed_zero",
    "completed_nonzero",
    "timed_out",
    "unsafe",
    "missing_command",
    "active_command_running",
    "budget_insufficient",
    "runtime_error",
]
TypedEvidenceProjectionStatus = Literal["not_attempted", "passed", "warning", "failed"]

DEFAULT_ALLOWED_SOURCES: tuple[FinishVerifierSource, ...] = (
    "configured_verifier",
    "finish_verifier_planner",
    "auto_detected_verifier",
)


@dataclass(frozen=True)
class NativeFinishGatePolicy:
    """Policy for native finish closeout.

    `typed_evidence_mode` and `oracle_obligation_mode` are fixed to
    `diagnostic_sidecar` on purpose.  A trusted final verifier closeout is the
    hot completion authority; resolver/evidence projections remain observable
    but lower authority.
    """

    policy_version: str = NATIVE_FINISH_GATE_POLICY_VERSION
    allowed_sources: tuple[FinishVerifierSource, ...] = DEFAULT_ALLOWED_SOURCES
    min_closeout_seconds: float = 5.0
    default_closeout_seconds: float = 60.0
    max_closeout_seconds: float = 3600.0
    allow_shell: bool = False
    require_no_unexpected_source_mutation: bool = True
    record_typed_evidence: bool = True
    typed_evidence_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"
    oracle_obligation_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "allowed_sources": list(self.allowed_sources),
            "min_closeout_seconds": self.min_closeout_seconds,
            "default_closeout_seconds": self.default_closeout_seconds,
            "max_closeout_seconds": self.max_closeout_seconds,
            "allow_shell": self.allow_shell,
            "require_no_unexpected_source_mutation": self.require_no_unexpected_source_mutation,
            "record_typed_evidence": self.record_typed_evidence,
            "typed_evidence_mode": self.typed_evidence_mode,
            "oracle_obligation_mode": self.oracle_obligation_mode,
        }


@dataclass(frozen=True)
class FinishCloseoutCommandValidation:
    """Validation result for a selected final-verifier command."""

    allowed: bool
    command: FinishCloseoutCommand | None = None
    blockers: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "allowed": self.allowed,
                "command": self.command.as_dict() if self.command else {},
                "blockers": list(self.blockers),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True)
class FinishCloseoutCommand:
    """One trusted final-verifier command candidate."""

    command: str
    cwd: str = "."
    source: FinishVerifierSource = "configured_verifier"
    source_ref: str = ""
    reason: str = ""
    confidence: str = ""
    raw: Mapping[str, object] = field(default_factory=dict)

    def normalized_command(self) -> str:
        return self.command.strip()

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "command": self.command,
                "cwd": self.cwd,
                "source": self.source,
                "source_ref": self.source_ref,
                "reason": self.reason,
                "confidence": self.confidence,
                "raw": dict(self.raw),
            }
        )


@dataclass(frozen=True)
class NativeFinishGateRequest:
    """Pre-extracted request facts for a native finish decision."""

    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    finish_arguments: Mapping[str, object]
    task_id: str = ""
    task_description: str = ""
    task_contract: Mapping[str, object] = field(default_factory=dict)
    lane_config: Mapping[str, object] = field(default_factory=dict)
    workspace: str = ""
    allowed_read_roots: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    latest_source_mutation: Mapping[str, object] = field(default_factory=dict)
    prior_tool_summary: tuple[Mapping[str, object], ...] = ()
    configured_command: FinishCloseoutCommand | None = None
    auto_detected_command: FinishCloseoutCommand | None = None
    planner_command: FinishCloseoutCommand | None = None
    remaining_wall_seconds: float | None = None


@dataclass(frozen=True)
class NativeFinishCloseoutResult:
    """Result of the final verifier closeout path.

    Phase 1 serializes opaque tool/transcript objects defensively.  Later phases
    will replace those objects with native transcript items from the harness.
    """

    command: FinishCloseoutCommand | None
    call_item: object | None
    output_item: object | None
    tool_result: object | None
    status: FinishCloseoutStatus
    exit_code: int | None = None
    timed_out: bool = False
    observed_unexpected_source_mutation: bool = False
    typed_evidence_projection_status: TypedEvidenceProjectionStatus = "not_attempted"
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "command": self.command.as_dict() if self.command else {},
                "call_item": _json_safe(self.call_item),
                "output_item": _json_safe(self.output_item),
                "tool_result": _json_safe(self.tool_result),
                "status": self.status,
                "exit_code": self.exit_code,
                "timed_out": self.timed_out,
                "observed_unexpected_source_mutation": self.observed_unexpected_source_mutation,
                "typed_evidence_projection_status": self.typed_evidence_projection_status,
                "evidence_refs": list(self.evidence_refs),
                "closeout_refs": list(self.closeout_refs),
                "observer_refs": list(self.observer_refs),
                "blockers": list(self.blockers),
                "warnings": list(self.warnings),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True)
class NativeFinishGateDecision:
    """Authoritative native finish-gate decision record."""

    decision_id: str
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    lane_status: FinishGateStatus
    result: FinishGateResult
    closeout: NativeFinishCloseoutResult
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    transcript_items_to_append: tuple[object, ...] = ()
    finish_output_payload: Mapping[str, object] = field(default_factory=dict)
    diagnostic_resolver_record: Mapping[str, object] = field(default_factory=dict)
    reason: str = ""
    policy_version: str = NATIVE_FINISH_GATE_POLICY_VERSION
    schema_version: int = NATIVE_FINISH_GATE_SCHEMA_VERSION

    def as_dict(self, *, include_finish_output_payload: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "policy_version": self.policy_version,
            "lane_attempt_id": self.lane_attempt_id,
            "turn_id": self.turn_id,
            "finish_call_id": self.finish_call_id,
            "lane_status": self.lane_status,
            "result": self.result,
            "closeout": self.closeout.as_dict(),
            "blockers": list(self.blockers),
            "missing_obligations": list(self.missing_obligations),
            "evidence_refs": list(self.evidence_refs),
            "closeout_refs": list(self.closeout_refs),
            "observer_refs": list(self.observer_refs),
            "transcript_hash_before_decision": self.transcript_hash_before_decision,
            "compact_sidecar_digest_hash": self.compact_sidecar_digest_hash,
            "transcript_items_to_append": [_json_safe(item) for item in self.transcript_items_to_append],
            "diagnostic_resolver_record": dict(self.diagnostic_resolver_record),
            "reason": self.reason,
        }
        if include_finish_output_payload:
            payload["finish_output_payload"] = finish_output_payload_for_decision(self)
        return _drop_empty(payload)


def select_closeout_command(
    request: NativeFinishGateRequest,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommand | None:
    """Select the highest-precedence allowed closeout command candidate."""

    active_policy = policy or NativeFinishGatePolicy()
    allowed = set(active_policy.allowed_sources)
    for command in (request.configured_command, request.planner_command, request.auto_detected_command):
        if command is None:
            continue
        if command.source not in allowed:
            continue
        if not command.normalized_command():
            continue
        return command
    return None


def validate_closeout_command(
    command: FinishCloseoutCommand | None,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommandValidation:
    """Validate a final-verifier command before dispatch.

    This validator is intentionally conservative.  Later phases may replace the
    string checks with parser metadata, but Phase 2 must already prevent obvious
    self-approval, mutation, privilege, network, and daemon-style commands from
    becoming the trusted hot closeout source.
    """

    active_policy = policy or NativeFinishGatePolicy()
    if command is None:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=None,
            blockers=("closeout_verifier_command_missing",),
            reason="no final verifier closeout command was selected",
        )
    normalized = command.normalized_command()
    if not normalized:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=("closeout_command_empty",),
            reason="final verifier closeout command is empty",
        )
    if command.source not in set(active_policy.allowed_sources):
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=("closeout_command_source_disallowed",),
            reason=f"command source {command.source!r} is not allowed by policy",
        )

    blockers = _unsafe_command_blockers(normalized, allow_shell=active_policy.allow_shell)
    if blockers:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=blockers,
            reason="final verifier closeout command failed safety validation",
        )
    return FinishCloseoutCommandValidation(
        allowed=True,
        command=command,
        reason="final verifier closeout command passed provenance validation",
    )


def select_and_validate_closeout_command(
    request: NativeFinishGateRequest,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommandValidation:
    """Select the highest-precedence command and validate it."""

    active_policy = policy or NativeFinishGatePolicy()
    return validate_closeout_command(select_closeout_command(request, active_policy), active_policy)


def finish_output_payload_for_decision(decision: NativeFinishGateDecision) -> dict[str, object]:
    """Build the bounded payload paired with the provider-native finish call."""

    if decision.finish_output_payload:
        return dict(decision.finish_output_payload)
    return _drop_empty(
        {
            "schema_version": decision.schema_version,
            "kind": "native_finish_gate_decision",
            "decision_id": decision.decision_id,
            "policy_version": decision.policy_version,
            "lane_status": decision.lane_status,
            "result": decision.result,
            "reason": decision.reason,
            "blockers": list(decision.blockers),
            "missing_obligations": list(decision.missing_obligations),
            "evidence_refs": list(decision.evidence_refs),
            "closeout_refs": list(decision.closeout_refs),
            "observer_refs": list(decision.observer_refs),
            "transcript_hash_before_decision": decision.transcript_hash_before_decision,
            "compact_sidecar_digest_hash": decision.compact_sidecar_digest_hash,
            "closeout_status": decision.closeout.status,
            "closeout_exit_code": decision.closeout.exit_code,
            "closeout_timed_out": decision.closeout.timed_out,
            "typed_evidence_projection_status": decision.closeout.typed_evidence_projection_status,
            "diagnostic_resolver_record": dict(decision.diagnostic_resolver_record),
        }
    )


def decide_native_finish_from_closeout(
    request: NativeFinishGateRequest,
    closeout: NativeFinishCloseoutResult,
    policy: NativeFinishGatePolicy | None = None,
) -> NativeFinishGateDecision:
    """Return the authoritative native finish decision for a closeout result.

    A trusted final verifier closeout that exits 0 is the hot completion
    authority.  Typed evidence and oracle projection warnings stay observable
    on the closeout result, but they do not become blockers here.
    """

    active_policy = policy or NativeFinishGatePolicy()
    decision_id = build_decision_id(
        lane_attempt_id=request.lane_attempt_id,
        turn_id=request.turn_id,
        finish_call_id=request.finish_call_id,
        policy_version=active_policy.policy_version,
    )
    blockers = tuple(dict.fromkeys(closeout.blockers))
    missing: tuple[str, ...] = ()
    lane_status: FinishGateStatus = "blocked_continue"
    result: FinishGateResult = "block"
    reason = closeout.reason or "final verifier closeout did not allow completion"

    if closeout.status == "completed_zero" and not closeout.timed_out:
        if active_policy.require_no_unexpected_source_mutation and closeout.observed_unexpected_source_mutation:
            blockers = tuple(dict.fromkeys((*blockers, "closeout_unexpected_source_mutation")))
            reason = "trusted final verifier passed but closeout mutated source unexpectedly"
        else:
            blockers = ()
            lane_status = "completed"
            result = "allow"
            reason = "trusted final verifier closeout exited 0"
    elif closeout.status == "missing_command":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_command_missing")))
        missing = ("final_verifier_closeout",)
        reason = closeout.reason or "final verifier closeout command is missing"
    elif closeout.status == "budget_insufficient":
        lane_status = "blocked_return"
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_budget_insufficient")))
        missing = ("final_verifier_closeout",)
        reason = closeout.reason or "insufficient budget for final verifier closeout"
    elif closeout.status == "timed_out" or closeout.timed_out:
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_timeout")))
        reason = closeout.reason or "final verifier closeout timed out"
    elif closeout.status == "active_command_running":
        blockers = tuple(dict.fromkeys((*blockers, "active_command_running")))
        reason = closeout.reason or "active command is still running before final verifier closeout"
    elif closeout.status == "unsafe":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_command_unsafe")))
        reason = closeout.reason or "final verifier closeout command was unsafe"
    elif closeout.status == "completed_nonzero":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_failed")))
        reason = closeout.reason or "final verifier closeout exited nonzero"
    elif closeout.status == "runtime_error":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_runtime_error")))
        reason = closeout.reason or "final verifier closeout runtime error"

    return NativeFinishGateDecision(
        decision_id=decision_id,
        policy_version=active_policy.policy_version,
        lane_attempt_id=request.lane_attempt_id,
        turn_id=request.turn_id,
        finish_call_id=request.finish_call_id,
        lane_status=lane_status,
        result=result,
        closeout=closeout,
        blockers=blockers,
        missing_obligations=missing,
        evidence_refs=closeout.evidence_refs,
        closeout_refs=closeout.closeout_refs,
        observer_refs=closeout.observer_refs,
        transcript_hash_before_decision=request.transcript_hash_before_decision,
        compact_sidecar_digest_hash=request.compact_sidecar_digest_hash,
        reason=reason,
    )


def write_native_finish_gate_artifacts(
    root: str | Path,
    decisions: tuple[NativeFinishGateDecision, ...] | list[NativeFinishGateDecision],
    *,
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write native finish-gate decisions and mirror their ref/hash into manifest."""

    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    decision_path = artifact_root / NATIVE_FINISH_GATE_DECISIONS_FILE
    records = [decision.as_dict(include_finish_output_payload=False) for decision in decisions]
    _write_jsonl(decision_path, records)
    digest = _file_sha256(decision_path)
    if proof_manifest_path is not None:
        _patch_proof_manifest(
            Path(proof_manifest_path),
            decision_path=decision_path,
            digest=digest,
            records=records,
        )
    return {"native_finish_gate_decisions": decision_path}


def native_finish_gate_manifest_fields(path: str | Path) -> dict[str, object]:
    decision_path = Path(path)
    return {
        "native_finish_gate_decisions_ref": decision_path.name,
        "native_finish_gate_decisions_sha256": _file_sha256(decision_path),
    }


def build_decision_id(*, lane_attempt_id: str, turn_id: str, finish_call_id: str, policy_version: str) -> str:
    """Return a deterministic decision id for sidecar/replay records."""

    digest = hashlib.sha256(
        json.dumps(
            {
                "finish_call_id": finish_call_id,
                "lane_attempt_id": lane_attempt_id,
                "policy_version": policy_version,
                "turn_id": turn_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"native-finish-gate:{turn_id}:{finish_call_id}:{digest}"


_NOOP_COMMANDS = frozenset(
    {
        ":",
        "true",
        "/bin/true",
        "exit 0",
        "test 1 = 1",
        "test 1 == 1",
        "[ 1 = 1 ]",
        "[[ 1 == 1 ]]",
    }
)
_SHELL_TOKENS = frozenset({"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/bin/zsh"})
_SELF_ACCEPTANCE_TOKENS = frozenset({"echo", "printf"})
_WEAK_ASSERTION_TOKENS = frozenset({"test", "[", "[["})
_INLINE_EVALUATOR_TOKENS = frozenset({"node", "python", "python3", "ruby"})
_WRAPPER_TOKENS = frozenset({"command", "env"})
_SOURCE_MUTATION_TOKENS = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "install",
        "ln",
        "mkdir",
        "mv",
        "rm",
        "rsync",
        "sed",
        "tee",
        "touch",
        "truncate",
    }
)
_PACKAGE_INSTALL_TOKENS = frozenset({"apt", "apt-get", "brew", "dnf", "npm", "pip", "pip3", "pnpm", "yarn"})
_NETWORK_TOKENS = frozenset({"curl", "git", "hg", "scp", "ssh", "svn", "wget"})
_BACKGROUND_TOKENS = frozenset({"daemon", "nohup"})
_PRIVILEGED_TOKENS = frozenset({"doas", "sudo", "su"})
_SECRET_MARKERS = (
    "API_KEY",
    "AUTH_TOKEN",
    "BEARER",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


def _unsafe_command_blockers(command: str, *, allow_shell: bool) -> tuple[str, ...]:
    if "\n" in command or "\r" in command:
        return ("closeout_command_multiline",)
    normalized = " ".join(command.strip().split())
    blockers: list[str] = []
    if normalized in _NOOP_COMMANDS:
        blockers.append("closeout_command_noop_success")

    tokens = _split_command_tokens(normalized)
    semantic_tokens = _semantic_tokens(tokens)
    first = _basename(semantic_tokens[0]) if semantic_tokens else ""
    if first in _SELF_ACCEPTANCE_TOKENS:
        blockers.append("closeout_command_self_acceptance")
    if first in _WEAK_ASSERTION_TOKENS:
        blockers.append("closeout_command_weak_assertion")
    if first in _INLINE_EVALUATOR_TOKENS and any(token in {"-c", "-e"} for token in semantic_tokens):
        blockers.append("closeout_command_inline_program")
    if first in _SHELL_TOKENS and not allow_shell:
        blockers.append("closeout_command_shell_disallowed")
    semantic_basenames = {_basename(token) for token in semantic_tokens}
    if semantic_basenames & _SOURCE_MUTATION_TOKENS:
        blockers.append("closeout_command_source_mutation")
    if semantic_basenames & _PACKAGE_INSTALL_TOKENS and "install" in semantic_tokens:
        blockers.append("closeout_command_package_install")
    if semantic_basenames & _NETWORK_TOKENS:
        blockers.append("closeout_command_network")
    if semantic_basenames & _PRIVILEGED_TOKENS:
        blockers.append("closeout_command_privileged")
    if semantic_basenames & _BACKGROUND_TOKENS:
        blockers.append("closeout_command_background")

    if _contains_unquoted_control(command, (">", "<")):
        blockers.append("closeout_command_redirection")
    if _contains_chain_operator(command):
        blockers.append("closeout_command_chain")
    if _contains_background_operator(command):
        blockers.append("closeout_command_background")
    if any(marker in command.upper() for marker in _SECRET_MARKERS):
        blockers.append("closeout_command_secret")
    if _contains_self_pass_marker(command):
        blockers.append("closeout_command_self_acceptance")
    return tuple(dict.fromkeys(blockers))


def _split_command_tokens(command: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return ()


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1] if token else ""


def _semantic_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    remaining = list(tokens)
    while remaining:
        first = _basename(remaining[0])
        if first == "env":
            remaining.pop(0)
            while remaining and _looks_like_assignment(remaining[0]):
                remaining.pop(0)
            continue
        if first == "command":
            remaining.pop(0)
            continue
        if _looks_like_assignment(remaining[0]):
            remaining.pop(0)
            continue
        break
    return tuple(remaining)


def _looks_like_assignment(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name = token.split("=", 1)[0]
    return name.replace("_", "").isalnum()


def _contains_self_pass_marker(command: str) -> bool:
    normalized = command.lower().replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "acceptance:pass",
            "process.exit(0)",
            "sys.exit(0)",
            "exit(0)",
        )
    )


def _contains_chain_operator(command: str) -> bool:
    return any(marker in command for marker in ("&&", "||", ";", "|"))


def _contains_unquoted_control(command: str, controls: tuple[str, ...]) -> bool:
    in_single = False
    in_double = False
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if not in_single and not in_double and char in controls:
            return True
    return False


def _contains_background_operator(command: str) -> bool:
    if "&&" in command:
        command = command.replace("&&", "")
    return _contains_unquoted_control(command, ("&",))


def _drop_empty(payload: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in payload.items():
        if value in ("", None, (), [], {}):
            continue
        result[key] = value
    return result


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _json_safe(as_dict())
    return repr(value)


def _patch_proof_manifest(
    path: Path,
    *,
    decision_path: Path,
    digest: str,
    records: list[Mapping[str, object]],
) -> None:
    payload: dict[str, object] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload = loaded
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    summary = _decision_summary(records)
    payload["native_finish_gate_decisions_ref"] = decision_path.name
    payload["native_finish_gate_decisions_sha256"] = digest
    metrics["native_finish_gate_decisions"] = {
        "artifact_ref": decision_path.name,
        "artifact_sha256": digest,
        **summary,
    }
    payload["metrics"] = metrics
    _write_json(path, payload)


def _decision_summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    return {
        "decision_count": len(records),
        "allow_count": sum(1 for record in records if record.get("result") == "allow"),
        "block_count": sum(1 for record in records if record.get("result") == "block"),
        "completed_count": sum(1 for record in records if record.get("lane_status") == "completed"),
        "closeout_ref_count": sum(len(_strings(record.get("closeout_refs"))) for record in records),
        "observer_ref_count": sum(len(_strings(record.get("observer_refs"))) for record in records),
        "typed_evidence_warning_count": sum(
            1
            for record in records
            if _text(_mapping(record.get("closeout")).get("typed_evidence_projection_status")) == "warning"
        ),
        "unexpected_source_mutation_block_count": sum(
            1 for record in records if "closeout_unexpected_source_mutation" in _strings(record.get("blockers"))
        ),
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
