"""Semantic finish resolver for the implement_v2 native tool loop.

The resolver is deliberately outside the native harness.  It consumes only
pre-extracted finish/evidence facts and produces a sidecar decision.  It must
not execute tools, inspect arbitrary transcripts, or build provider messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Literal, Mapping


COMPLETION_RESOLVER_SCHEMA_VERSION = 1
COMPLETION_RESOLVER_POLICY_VERSION = "native-finish-resolver-v1"
COMPLETION_RESOLVER_DECISIONS_FILE = "resolver_decisions.jsonl"

CompletionResolverLaneStatus = Literal["completed", "blocked_continue", "blocked_return"]
CompletionResolverResult = Literal["allow", "block"]

_FORBIDDEN_RAW_INPUT_KEYS = frozenset(
    {
        "commands",
        "history",
        "messages",
        "native_transcript",
        "persisted_lane_state",
        "prompt_history",
        "raw_transcript",
        "response_items",
        "tool_outputs",
        "tool_results",
        "transcript",
        "transcript_items",
    }
)
_ALLOWED_INPUT_KEYS = frozenset(
    {
        "blockers",
        "budget_blockers",
        "closeout_refs",
        "compact_sidecar_digest_hash",
        "finish_claim",
        "finish_readiness",
        "fresh_verifier_refs",
        "missing_obligations",
        "oracle_obligation_refs",
        "transcript_hash_before_decision",
        "typed_evidence_refs",
        "unsafe_blockers",
        "verifier_required",
    }
)


@dataclass(frozen=True)
class FinishClaim:
    """One provider-native finish claim after protocol-level validation."""

    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    finish_output_call_id: str = ""
    outcome: str = ""
    summary: str = ""
    arguments: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "lane_attempt_id": self.lane_attempt_id,
                "turn_id": self.turn_id,
                "finish_call_id": self.finish_call_id,
                "finish_output_call_id": self.finish_output_call_id,
                "outcome": self.outcome,
                "summary": self.summary,
                "arguments": dict(self.arguments),
            }
        )


@dataclass(frozen=True)
class CompletionResolverInput:
    """Pre-extracted facts allowed to influence semantic finish resolution."""

    finish_claim: FinishClaim
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    finish_readiness: dict[str, object] = field(default_factory=dict)
    typed_evidence_refs: tuple[str, ...] = ()
    oracle_obligation_refs: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    fresh_verifier_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    unsafe_blockers: tuple[str, ...] = ()
    budget_blockers: tuple[str, ...] = ()
    verifier_required: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CompletionResolverInput":
        """Build resolver input while rejecting raw transcript/tool payloads."""

        unknown = sorted(key for key in value if key not in _ALLOWED_INPUT_KEYS)
        if unknown:
            raise ValueError("completion resolver input contains unsupported keys: " + ", ".join(unknown))
        forbidden = sorted(key for key in value if key in _FORBIDDEN_RAW_INPUT_KEYS)
        if forbidden:
            raise ValueError("completion resolver input must be pre-extracted; forbidden keys: " + ", ".join(forbidden))
        finish_claim_raw = value.get("finish_claim")
        if not isinstance(finish_claim_raw, Mapping):
            raise ValueError("completion resolver input requires finish_claim mapping")
        finish_claim = FinishClaim(
            lane_attempt_id=_text(finish_claim_raw.get("lane_attempt_id")),
            turn_id=_text(finish_claim_raw.get("turn_id")),
            finish_call_id=_text(finish_claim_raw.get("finish_call_id")),
            finish_output_call_id=_text(finish_claim_raw.get("finish_output_call_id")),
            outcome=_text(finish_claim_raw.get("outcome")),
            summary=_text(finish_claim_raw.get("summary")),
            arguments=dict(finish_claim_raw.get("arguments") or {})
            if isinstance(finish_claim_raw.get("arguments"), Mapping)
            else {},
        )
        _reject_forbidden_nested(finish_claim.arguments, path="finish_claim.arguments")
        finish_readiness = (
            dict(value.get("finish_readiness") or {}) if isinstance(value.get("finish_readiness"), Mapping) else {}
        )
        _reject_forbidden_nested(finish_readiness, path="finish_readiness")
        return cls(
            finish_claim=finish_claim,
            transcript_hash_before_decision=_text(value.get("transcript_hash_before_decision")),
            compact_sidecar_digest_hash=_text(value.get("compact_sidecar_digest_hash")),
            finish_readiness=finish_readiness,
            typed_evidence_refs=_texts(value.get("typed_evidence_refs")),
            oracle_obligation_refs=_texts(value.get("oracle_obligation_refs")),
            missing_obligations=_texts(value.get("missing_obligations")),
            fresh_verifier_refs=_texts(value.get("fresh_verifier_refs")),
            closeout_refs=_texts(value.get("closeout_refs")),
            blockers=_texts(value.get("blockers")),
            unsafe_blockers=_texts(value.get("unsafe_blockers")),
            budget_blockers=_texts(value.get("budget_blockers")),
            verifier_required=bool(value.get("verifier_required")),
        )


@dataclass(frozen=True)
class CompletionResolverDecision:
    """Sidecar-only semantic finish decision."""

    decision_id: str
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    finish_output_call_id: str
    lane_status: CompletionResolverLaneStatus
    result: CompletionResolverResult
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    reason: str = ""
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    policy_version: str = COMPLETION_RESOLVER_POLICY_VERSION
    schema_version: int = COMPLETION_RESOLVER_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "policy_version": self.policy_version,
            "lane_attempt_id": self.lane_attempt_id,
            "turn_id": self.turn_id,
            "finish_call_id": self.finish_call_id,
            "finish_output_call_id": self.finish_output_call_id,
            "transcript_hash_before_decision": self.transcript_hash_before_decision,
            "compact_sidecar_digest_hash": self.compact_sidecar_digest_hash,
            "lane_status": self.lane_status,
            "result": self.result,
            "blockers": list(self.blockers),
            "missing_obligations": list(self.missing_obligations),
            "evidence_refs": list(self.evidence_refs),
            "closeout_refs": list(self.closeout_refs),
            "reason": self.reason,
        }


class CompletionResolver:
    """Resolve a valid finish claim from pre-extracted evidence only."""

    policy_version = COMPLETION_RESOLVER_POLICY_VERSION

    def resolve(self, resolver_input: CompletionResolverInput) -> CompletionResolverDecision:
        finish = resolver_input.finish_claim
        blockers = list(dict.fromkeys((*resolver_input.blockers, *_finish_readiness_blockers(resolver_input))))
        missing = list(dict.fromkeys((*resolver_input.missing_obligations, *_finish_readiness_missing(resolver_input))))
        if resolver_input.verifier_required and not resolver_input.fresh_verifier_refs and not resolver_input.closeout_refs:
            blockers.append("verifier_evidence_missing")
            missing.append("strict_verifier_evidence")

        if resolver_input.unsafe_blockers or resolver_input.budget_blockers:
            blockers.extend(resolver_input.unsafe_blockers)
            blockers.extend(resolver_input.budget_blockers)
            lane_status: CompletionResolverLaneStatus = "blocked_return"
            result: CompletionResolverResult = "block"
            reason = "finish blocked for supervisor return: " + ", ".join(dict.fromkeys(blockers))
        elif blockers or missing:
            lane_status = "blocked_continue"
            result = "block"
            reason = "finish blocked; more evidence or repair is required"
        else:
            lane_status = "completed"
            result = "allow"
            reason = finish.summary or "finish allowed by resolver evidence"

        return CompletionResolverDecision(
            decision_id=f"resolver:{finish.turn_id}:{finish.finish_call_id}",
            lane_attempt_id=finish.lane_attempt_id,
            turn_id=finish.turn_id,
            finish_call_id=finish.finish_call_id,
            finish_output_call_id=finish.finish_output_call_id,
            lane_status=lane_status,
            result=result,
            blockers=tuple(dict.fromkeys(blockers)),
            missing_obligations=tuple(dict.fromkeys(missing)),
            evidence_refs=tuple(
                dict.fromkeys((*resolver_input.typed_evidence_refs, *resolver_input.fresh_verifier_refs))
            ),
            closeout_refs=resolver_input.closeout_refs,
            reason=reason,
            transcript_hash_before_decision=resolver_input.transcript_hash_before_decision,
            compact_sidecar_digest_hash=resolver_input.compact_sidecar_digest_hash,
        )


def write_completion_resolver_artifacts(
    root: str | Path,
    decisions: tuple[CompletionResolverDecision, ...] | list[CompletionResolverDecision],
    *,
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write resolver decisions and optionally mirror their ref/hash into a manifest."""

    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    decision_path = artifact_root / COMPLETION_RESOLVER_DECISIONS_FILE
    records = [decision.as_dict() for decision in decisions]
    _write_jsonl(decision_path, records)
    digest = _file_sha256(decision_path)
    if proof_manifest_path is not None:
        _patch_proof_manifest(Path(proof_manifest_path), decision_path=decision_path, digest=digest)
    return {"resolver_decisions": decision_path}


def completion_resolver_manifest_fields(path: str | Path) -> dict[str, object]:
    decision_path = Path(path)
    return {
        "resolver_decisions_ref": decision_path.name,
        "resolver_decisions_sha256": _file_sha256(decision_path),
    }


def _finish_readiness_blockers(resolver_input: CompletionResolverInput) -> tuple[str, ...]:
    readiness = resolver_input.finish_readiness
    blockers = readiness.get("blockers")
    return _texts(blockers)


def _finish_readiness_missing(resolver_input: CompletionResolverInput) -> tuple[str, ...]:
    readiness = resolver_input.finish_readiness
    missing = readiness.get("missing_obligations") or readiness.get("required_evidence_refs")
    return _texts(missing)


def _patch_proof_manifest(path: Path, *, decision_path: Path, digest: str) -> None:
    payload: dict[str, object] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            payload = data
    payload["resolver_decisions_ref"] = decision_path.name
    payload["resolver_decisions_sha256"] = digest
    _write_json(path, payload)


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


def _texts(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(text for item in value if (text := _text(item)))


def _reject_forbidden_nested(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = _text(key)
            child_path = f"{path}.{key_text}" if key_text else path
            if key_text in _FORBIDDEN_RAW_INPUT_KEYS:
                raise ValueError(f"completion resolver input contains raw payload key: {child_path}")
            _reject_forbidden_nested(item, path=child_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_forbidden_nested(item, path=f"{path}[{index}]")


def _text(value: object) -> str:
    return str(value or "").strip()


def _drop_empty(payload: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value not in ("", [], {}, None)}


__all__ = [
    "COMPLETION_RESOLVER_DECISIONS_FILE",
    "COMPLETION_RESOLVER_POLICY_VERSION",
    "COMPLETION_RESOLVER_SCHEMA_VERSION",
    "CompletionResolver",
    "CompletionResolverDecision",
    "CompletionResolverInput",
    "CompletionResolverLaneStatus",
    "CompletionResolverResult",
    "FinishClaim",
    "completion_resolver_manifest_fields",
    "write_completion_resolver_artifacts",
]
