"""Phase B deterministic core for typed memory cards.

This module intentionally stays behind the generic harness adapter boundary. It
implements a small in-memory source-of-truth core over the Phase A typed-card
schemas: raw provenance capture, candidate/proposal lifecycle, approval/commit
gates, direct-scan retrieval, mutations, audit, and usage records.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import math
import re
import time
from typing import Any

from .memory_typed_cards import (
    ApprovalState,
    Applicability,
    Authority,
    AuthorityEvidenceEvent,
    AuthoritySource,
    AuthorityStrength,
    CandidateProducer,
    ContradictionState,
    CurrentEvidenceSnapshot,
    DroppedReason,
    EvidenceLink,
    EvidenceRole,
    GraphEdge,
    GraphRefs,
    GraphNode,
    Invalidator,
    InvalidatorKind,
    Lifecycle,
    MemoryAuditEvent,
    MemoryAuditFields,
    MemoryCandidate,
    MemoryCard,
    MemoryCardKind,
    MemoryRevision,
    MemoryTimestamps,
    MemoryTraceEvent,
    PrivacyRules,
    ProjectionMode,
    ProvenanceEvent,
    ProvenanceProducer,
    ProvenanceReceipt,
    RawEventKind,
    RawMemoryExtractorConfig,
    RawMemoryIngestRequest,
    RedactionPolicy,
    RedactionState,
    RetentionState,
    Scope,
    ScopeLevel,
    StalenessState,
    TraceActor,
    Valence,
    stable_hash,
    stable_json,
    stable_short_hash,
)


ModelJsonCaller = Callable[[str, Mapping[str, Any], str, str, str, int], Any]
ModelStructuredJsonCaller = Callable[..., Any]
ModelAuthLoader = Callable[[str, str], Mapping[str, Any]]
RawExtractor = Callable[[RawMemoryIngestRequest, ProvenanceEvent, Scope], Mapping[str, Any]]

_SCORE_QUANTUM = Decimal("0.0001")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
_FORBIDDEN_SEED_KEYS = {
    "gold",
    "gold_label",
    "expected",
    "expected_answer",
    "expected_answer_ids",
    "trap",
    "trap_family",
    "fixture_mode",
    "scorer_view",
    "must_not_return_evidence_ids",
}
_FORBIDDEN_PATCH_PATHS = {
    "card_id",
    "schema_version",
    "kind",
    "scope",
    "scope.level",
    "scope.namespace",
    "authority",
    "authority.source",
    "authority.strength",
    "authority.source_refs",
    "evidence_links",
    "evidence_refs",
    "support_refs",
    "approval_state",
    "staleness_state",
    "contradiction_state",
    "revision",
    "timestamps.created_at",
    "audit",
    "graph_refs",
}
_ALLOWED_CLEAR_FIELDS = {"details", "lifecycle.expires_at", "privacy.redaction_policy"}
_AUTHORITY_RANK = {
    AuthorityStrength.OBSERVATION.value: Decimal("0.0000"),
    AuthorityStrength.HINT.value: Decimal("0.1000"),
    AuthorityStrength.SHOULD.value: Decimal("0.2000"),
    AuthorityStrength.MUST.value: Decimal("0.3000"),
}
_AUTHORITY_SOURCE_RANK = {
    AuthoritySource.SELF.value: Decimal("0.0000"),
    AuthoritySource.SCORING.value: Decimal("0.0500"),
    AuthoritySource.VERIFIER.value: Decimal("0.1000"),
    AuthoritySource.REVIEWER.value: Decimal("0.1200"),
    AuthoritySource.USER.value: Decimal("0.1400"),
    AuthoritySource.MAINTAINER.value: Decimal("0.1600"),
    AuthoritySource.SYSTEM.value: Decimal("0.1800"),
}
_NORMAL_COMMIT_ACTORS = {
    TraceActor.CORE.value,
    TraceActor.DEBUG.value,
    TraceActor.SCORING.value,
    TraceActor.MAINTAINER.value,
}
_NORMAL_APPROVE_ACTORS = {
    TraceActor.CORE.value,
    TraceActor.DEBUG.value,
    TraceActor.SCORING.value,
    TraceActor.USER.value,
    TraceActor.REVIEWER.value,
    TraceActor.VERIFIER.value,
    TraceActor.MAINTAINER.value,
}
_MUTATION_ACTORS = {
    TraceActor.CORE.value,
    TraceActor.DEBUG.value,
    TraceActor.SCORING.value,
    TraceActor.ADAPTER.value,
    TraceActor.USER.value,
    TraceActor.REVIEWER.value,
    TraceActor.MAINTAINER.value,
}
_SEMANTIC_PATCH_FIELDS = {"summary", "details", "applicability", "valence", "invalidators", "confidence"}
_LATENCY_SOURCE_PRECEDENCE = ("wall_clock", "replayed_artifact", "deterministic_mock")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_score(value: Any) -> str:
    """Return a CanonicalScore string using Decimal ROUND_HALF_UP."""

    try:
        if isinstance(value, Decimal):
            decimal = value
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise ValueError("score must be finite")
            decimal = Decimal(str(value))
        else:
            decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("score must be a finite decimal") from exc
    if decimal.is_nan() or decimal.is_infinite():
        raise ValueError("score must be finite")
    rounded = decimal.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    if rounded == Decimal("-0.0000"):
        rounded = Decimal("0.0000")
    return f"{rounded:.4f}"


def raw_memory_extraction_schema() -> dict[str, Any]:
    """Provider structured-output schema for raw memory extraction."""

    string_array = {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Canonical typed refs only. Use the provided default_scope_key when the "
            "claim applies to the current scope; use an empty array when unsure."
        ),
    }
    nullable_string = {"type": ["string", "null"]}
    nullable_scope_ref = {"type": ["string", "null"]}
    scope_schema = {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": [
            "level",
            "namespace",
            "user_id",
            "project_id",
            "repo_ref",
            "branch_ref",
            "task_ref",
            "task_family",
            "lane_id",
        ],
        "properties": {
            "level": {"type": "string", "enum": [item.value for item in ScopeLevel]},
            "namespace": {"type": "string"},
            "user_id": nullable_scope_ref,
            "project_id": nullable_scope_ref,
            "repo_ref": nullable_scope_ref,
            "branch_ref": nullable_scope_ref,
            "task_ref": nullable_scope_ref,
            "task_family": nullable_scope_ref,
            "lane_id": nullable_scope_ref,
        },
    }
    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "kind",
            "summary",
            "details",
            "confidence",
            "scope",
            "authority",
            "valence",
            "applicability",
            "evidence_links",
            "proposed_by",
            "write_reason",
            "ambiguous",
        ],
        "properties": {
            "kind": {"type": "string", "enum": [item.value for item in MemoryCardKind]},
            "summary": {
                "type": "string",
                "description": "Synthesized memory claim, not raw transcript text.",
            },
            "details": nullable_string,
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "scope": scope_schema,
            "authority": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "strength", "source_refs"],
                "properties": {
                    "source": {"type": "string", "enum": [item.value for item in AuthoritySource]},
                    "strength": {"type": "string", "enum": [item.value for item in AuthorityStrength]},
                    "source_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Use the provided provenance_event_id for self/hint extraction.",
                    },
                },
            },
            "valence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["polarity", "effect"],
                "properties": {
                    "polarity": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "effect": {"type": "string", "enum": ["use", "avoid", "verify", "ask", "ignore"]},
                },
            },
            "applicability": {
                "type": "object",
                "additionalProperties": False,
                "required": ["applies_to", "does_not_apply_to", "prerequisites", "counterexamples"],
                "properties": {
                    "applies_to": string_array,
                    "does_not_apply_to": string_array,
                    "prerequisites": string_array,
                    "counterexamples": string_array,
                },
            },
            "evidence_links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ref_id", "role", "active", "added_by_mutation_id", "note"],
                    "properties": {
                        "ref_id": {"type": "string"},
                        "role": {"type": "string", "enum": [item.value for item in EvidenceRole]},
                        "active": {"type": "boolean"},
                        "added_by_mutation_id": nullable_string,
                        "note": nullable_string,
                    },
                },
                "description": "If provided, cite the provenance_event_id as current_support.",
            },
            "proposed_by": {"type": "string", "enum": [item.value for item in CandidateProducer]},
            "write_reason": {"type": "string"},
            "ambiguous": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "candidate", "dropped"],
        "properties": {
            "decision": {"type": "string", "enum": ["candidate", "reject", "clarification_needed"]},
            "candidate": {
                **candidate_schema,
                "type": ["object", "null"],
                "description": "Null when decision is reject or clarification_needed.",
            },
            "dropped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["reason", "summary", "ref_id"],
                    "properties": {
                        "reason": {
                            "type": "string",
                            "enum": [
                                "ambiguous",
                                "raw_transcript",
                                "low_confidence",
                                "not_memory",
                                "unsupported",
                            ],
                        },
                        "summary": {"type": "string"},
                        "ref_id": nullable_string,
                    },
                },
            },
        },
    }


def raw_memory_extraction_prompt(request: RawMemoryIngestRequest, provenance_event: ProvenanceEvent, scope: Scope) -> str:
    payload = {
        "task": "Extract proposal-only typed memory candidates from raw text.",
        "schema": {
            "decision": "candidate | reject | clarification_needed",
            "candidate": {
                "kind": "reentry_snapshot | task_episode | semantic_fact | procedure | policy_or_preference",
                "summary": "synthesized memory claim, not raw transcript",
                "details": "optional synthesized details or null",
                "confidence": 0.0,
                "authority": {"source": "self", "strength": "hint", "source_refs": []},
                "valence": {"polarity": "neutral", "effect": "use"},
                "applicability": {"applies_to": [], "does_not_apply_to": [], "prerequisites": [], "counterexamples": []},
                "evidence_links": [],
                "proposed_by": "model",
                "write_reason": "raw ingest extractor proposal",
                "ambiguous": False,
                "scope": None,
            },
            "dropped": [{"reason": "ambiguous | raw_transcript | low_confidence", "summary": "short reason"}],
        },
        "rules": [
            "Return exactly one JSON object matching the schema.",
            "Do not mark anything committed or approved.",
            "Do not copy raw transcript into summary or details.",
            "When ambiguous, return clarification_needed, reject, or a low-confidence proposal.",
            "Every candidate must cite the provided provenance event through current_support evidence.",
            "Applicability fields must contain canonical typed refs only, never natural-language descriptions.",
            "For applies_to, use trusted_runtime_context.default_scope_key when the candidate applies to the current scope and no narrower canonical typed ref is known.",
            "Use empty applicability arrays when unsure; typed validation will reject invalid refs.",
            "Do not emit invalidators from raw extraction; they are assigned by later governance paths when needed.",
        ],
        "trusted_runtime_context": {
            "provenance_event_id": provenance_event.event_id,
            "default_scope": scope.to_dict(),
            "default_scope_key": scope.scope_key(),
        },
        "raw_text": request.raw_text,
    }
    return stable_json(payload)


class ModelRawMemoryExtractor:
    """Default production extractor binding through mew model_backends.

    Tests should inject ``call_json`` and ``load_auth`` or pass a fake extractor
    to ``TypedMemoryCore.ingest_raw`` so no live model call is made.
    """

    def __init__(
        self,
        *,
        config: RawMemoryExtractorConfig | None = None,
        model_auth: Mapping[str, Any] | None = None,
        base_url: str = "",
        timeout: int = 120,
        call_json: ModelJsonCaller | None = None,
        call_structured_json: ModelStructuredJsonCaller | None = None,
        load_auth: ModelAuthLoader | None = None,
    ) -> None:
        self.config = config or RawMemoryExtractorConfig()
        self.model_auth = model_auth
        self.base_url = base_url
        self.timeout = int(timeout or 120)
        self.call_json = call_json
        self.call_structured_json = call_structured_json
        self.load_auth = load_auth

    def __call__(
        self,
        request: RawMemoryIngestRequest,
        provenance_event: ProvenanceEvent,
        scope: Scope,
    ) -> Mapping[str, Any]:
        auth = self.model_auth
        if auth is None:
            loader = self.load_auth
            if loader is None:
                from .model_backends import load_model_auth

                loader = load_model_auth
            auth = loader(self.config.backend, self.config.auth_path)
        prompt = raw_memory_extraction_prompt(request, provenance_event, scope)
        if self.call_structured_json is not None:
            payload = self.call_structured_json(
                self.config.backend,
                auth,
                prompt,
                self.config.model,
                self.base_url,
                self.timeout,
                schema_name="raw_memory_extraction",
                json_schema=raw_memory_extraction_schema(),
                strict=True,
            )
        elif self.call_json is not None:
            payload = self.call_json(self.config.backend, auth, prompt, self.config.model, self.base_url, self.timeout)
        elif self.config.call_interface == "call_model_json":
            from .model_backends import call_model_json

            payload = call_model_json(self.config.backend, auth, prompt, self.config.model, self.base_url, self.timeout)
        else:
            from .model_backends import call_model_structured_json

            payload = call_model_structured_json(
                self.config.backend,
                auth,
                prompt,
                self.config.model,
                self.base_url,
                self.timeout,
                schema_name="raw_memory_extraction",
                json_schema=raw_memory_extraction_schema(),
                strict=True,
            )
        if not isinstance(payload, Mapping):
            raise ValueError("raw memory extractor must return a JSON object")
        return payload


@dataclass(frozen=True)
class RawIngestResult:
    status: str
    provenance_receipt: ProvenanceReceipt
    provenance_event: ProvenanceEvent
    candidate: MemoryCandidate | None
    proposal_card: MemoryCard | None
    dropped: tuple[DroppedReason, ...]
    audit_events: tuple[MemoryAuditEvent, ...]
    extractor_config: RawMemoryExtractorConfig
    request_hash: str
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provenance_receipt": self.provenance_receipt.to_dict(),
            "provenance_event": self.provenance_event.to_dict(),
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "proposal_card": self.proposal_card.to_dict() if self.proposal_card else None,
            "dropped": [item.to_dict() for item in self.dropped],
            "audit_events": [item.to_dict() for item in self.audit_events],
            "extractor_config": self.extractor_config.to_dict(),
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
        }


@dataclass(frozen=True)
class MemoryLifecycleResult:
    card: MemoryCard
    audit_event: MemoryAuditEvent


@dataclass(frozen=True)
class MemoryCommitResult:
    card: MemoryCard
    audit_event: MemoryAuditEvent
    bypass: str | None = None


@dataclass(frozen=True)
class MemoryMutation:
    mutation_id: str
    op: str
    target_card_id: str
    replacement_card: MemoryCard | None = None
    patch: Mapping[str, Any] | None = None
    reason: str = ""
    actor: str = TraceActor.DEBUG.value
    authority_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mutation_id", _required_text(self.mutation_id, "mutation_id"))
        op = _required_text(self.op, "mutation.op")
        if op not in {"update", "delete", "forget", "supersede", "tombstone"}:
            raise ValueError("mutation.op must be update, delete, forget, supersede, or tombstone")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "target_card_id", _required_text(self.target_card_id, "target_card_id"))
        actor = _required_text(self.actor, "mutation.actor")
        if actor not in _MUTATION_ACTORS:
            raise PermissionError(f"actor={actor} cannot mutate memory")
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "reason", _clean_text(self.reason) or op)
        object.__setattr__(self, "authority_refs", tuple(_required_text(item, "authority_refs") for item in self.authority_refs))
        if self.patch is not None and not isinstance(self.patch, Mapping):
            raise ValueError("mutation.patch must be an object")


@dataclass(frozen=True)
class MemoryMutationResult:
    mutation: MemoryMutation
    cards: tuple[MemoryCard, ...]
    audit_event: MemoryAuditEvent
    dropped: tuple[DroppedReason, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation": {
                "mutation_id": self.mutation.mutation_id,
                "op": self.mutation.op,
                "target_card_id": self.mutation.target_card_id,
                "reason": self.mutation.reason,
                "actor": self.mutation.actor,
                "authority_refs": list(self.mutation.authority_refs),
            },
            "cards": [card.to_dict() for card in self.cards],
            "audit_event": self.audit_event.to_dict(),
            "dropped": [item.to_dict() for item in self.dropped],
        }


@dataclass(frozen=True)
class MemoryRecallRequest:
    query: str
    scope: Scope
    authorization_scope: Scope | None = None
    applicability_refs: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    limit: int = 5
    include_maybe_stale: bool = False
    current_evidence: CurrentEvidenceSnapshot | None = None
    now: str | None = None
    latency_source: str = "deterministic_mock"
    request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _clean_text(self.query))
        scope = self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope)
        object.__setattr__(self, "scope", scope)
        if self.authorization_scope is None:
            object.__setattr__(self, "authorization_scope", scope)
        elif not isinstance(self.authorization_scope, Scope):
            object.__setattr__(self, "authorization_scope", Scope.from_dict(self.authorization_scope))
        object.__setattr__(self, "applicability_refs", tuple(_required_text(item, "applicability_refs") for item in self.applicability_refs))
        object.__setattr__(self, "kinds", tuple(MemoryCardKind(item).value for item in self.kinds))
        object.__setattr__(self, "limit", max(0, int(self.limit or 0)))
        if self.current_evidence is not None and not isinstance(self.current_evidence, CurrentEvidenceSnapshot):
            object.__setattr__(self, "current_evidence", CurrentEvidenceSnapshot(**self.current_evidence))
        object.__setattr__(self, "now", _clean_text(self.now) or None)
        if self.latency_source not in {"wall_clock", "deterministic_mock", "replayed_artifact"}:
            raise ValueError("latency_source must be wall_clock, deterministic_mock, or replayed_artifact")
        request_id = self.request_id or "req_" + stable_short_hash(self.to_request_payload(), length=16)
        object.__setattr__(self, "request_id", request_id)

    def to_request_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope.to_dict(),
            "authorization_scope": self.authorization_scope.to_dict() if self.authorization_scope else None,
            "applicability_refs": list(self.applicability_refs),
            "kinds": list(self.kinds),
            "limit": self.limit,
            "include_maybe_stale": self.include_maybe_stale,
            "current_evidence": self.current_evidence.to_dict() if self.current_evidence else None,
            "now": self.now,
            "latency_source": self.latency_source,
        }


@dataclass(frozen=True)
class MemoryUsage:
    latency_ms: float
    latency_source: str
    cards_scanned: int
    cards_ranked: int
    cards_returned: int
    cards_dropped: int
    graph_nodes_expanded: int = 0
    graph_edges_expanded: int = 0
    projection_chars: int = 0
    index_mode: str = "direct_scan"
    token_count: int | None = None
    cost_units: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "cards_scanned",
            "cards_ranked",
            "cards_returned",
            "cards_dropped",
            "graph_nodes_expanded",
            "graph_edges_expanded",
            "projection_chars",
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"usage.{name} must be non-negative")
            object.__setattr__(self, name, value)
        latency = float(self.latency_ms)
        if math.isnan(latency) or math.isinf(latency) or latency < 0:
            raise ValueError("usage.latency_ms must be a non-negative finite float")
        object.__setattr__(self, "latency_ms", latency)
        if self.latency_source not in {"wall_clock", "deterministic_mock", "replayed_artifact"}:
            raise ValueError("usage.latency_source is invalid")
        if self.index_mode not in {"direct_scan", "sync_lexical", "graph_index", "vector"}:
            raise ValueError("usage.index_mode is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_ms": self.latency_ms,
            "latency_source": self.latency_source,
            "cards_scanned": self.cards_scanned,
            "cards_ranked": self.cards_ranked,
            "cards_returned": self.cards_returned,
            "cards_dropped": self.cards_dropped,
            "graph_nodes_expanded": self.graph_nodes_expanded,
            "graph_edges_expanded": self.graph_edges_expanded,
            "projection_chars": self.projection_chars,
            "index_mode": self.index_mode,
            "token_count": self.token_count,
            "cost_units": self.cost_units,
        }


@dataclass(frozen=True)
class RankedMemoryEvidence:
    rank: int
    evidence_ref: str
    support_experience_ids: tuple[str, ...]
    source_experience_ids: tuple[str, ...]
    lineage_experience_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    source_mutation_ids: tuple[str, ...]
    mutation_refs: tuple[str, ...]
    score: str
    score_type: str
    score_components: Mapping[str, str | None]
    state: str
    scope_id: str
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "evidence_ref": self.evidence_ref,
            "support_experience_ids": list(self.support_experience_ids),
            "source_experience_ids": list(self.source_experience_ids),
            "lineage_experience_ids": list(self.lineage_experience_ids),
            "provenance_refs": list(self.provenance_refs),
            "source_mutation_ids": list(self.source_mutation_ids),
            "mutation_refs": list(self.mutation_refs),
            "score": self.score,
            "score_type": self.score_type,
            "score_components": dict(self.score_components),
            "state": self.state,
            "scope_id": self.scope_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CallerVisibleDroppedRecord:
    reason: str
    evidence_ref: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "evidence_ref": self.evidence_ref, "detail": self.detail}


@dataclass(frozen=True)
class MemoryRetrieveResult:
    ranked_evidence: tuple[RankedMemoryEvidence, ...]
    abstained: bool
    abstained_reason: str | None
    dropped: tuple[CallerVisibleDroppedRecord, ...]
    dropped_count_by_reason: Mapping[str, int]
    usage: MemoryUsage
    request_id: str
    request_hash: str
    result_hash: str
    audit_event: MemoryAuditEvent

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked_evidence": [item.to_dict() for item in self.ranked_evidence],
            "abstained": self.abstained,
            "abstained_reason": self.abstained_reason,
            "dropped": [item.to_dict() for item in self.dropped],
            "dropped_count_by_reason": dict(self.dropped_count_by_reason),
            "usage": self.usage.to_dict(),
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
        }


@dataclass(frozen=True)
class MemoryUsageReport:
    scope: Scope | None
    usage: MemoryUsage
    request_count: int
    window_start: str | None = None
    window_end: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.to_dict() if self.scope else None,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "request_count": self.request_count,
            "usage": self.usage.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TransientReentryRecord:
    record_id: str
    session_id: str
    scope: Scope
    summary: str
    created_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _required_text(self.record_id, "record_id"))
        object.__setattr__(self, "session_id", _required_text(self.session_id, "session_id"))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "created_at", _required_text(self.created_at, "created_at"))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "scope": self.scope.to_dict(),
            "summary": self.summary,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TransientReentryRecallResult:
    records: tuple[TransientReentryRecord, ...]
    request_hash: str
    result_hash: str
    audit_event: MemoryAuditEvent

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "audit_event": self.audit_event.to_dict(),
        }


class TypedMemoryCore:
    """Small deterministic Phase B memory core over typed-card value objects."""

    def __init__(
        self,
        *,
        extractor: RawExtractor | None = None,
        extractor_config: RawMemoryExtractorConfig | None = None,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.extractor = extractor
        self.extractor_config = extractor_config or RawMemoryExtractorConfig()
        self.clock = clock
        self.provenance_events: dict[str, ProvenanceEvent] = {}
        self.raw_payloads: dict[str, str] = {}
        self.candidates: dict[str, MemoryCandidate] = {}
        self.memory_cards: dict[str, MemoryCard] = {}
        self.graph_nodes: dict[str, GraphNode] = {}
        self.graph_edges: dict[str, GraphEdge] = {}
        self.memory_audit_log: list[MemoryAuditEvent] = []
        self.transient_reentry_records: dict[str, list[TransientReentryRecord]] = {}

    def ingest_raw(
        self,
        request: RawMemoryIngestRequest,
        *,
        scope: Scope,
        actor: str = ProvenanceProducer.USER.value,
        extractor: RawExtractor | None = None,
        source_experience_id: str | None = None,
        source_run_id: str | None = None,
        source_session_id: str | None = None,
        source_turn_id: str | None = None,
    ) -> RawIngestResult:
        request_hash = stable_hash(request.to_dict())
        provenance_event, receipt, capture_audit = self.capture_raw_provenance(
            request,
            scope=scope,
            actor=actor,
            source_experience_id=source_experience_id,
            source_run_id=source_run_id,
            source_session_id=source_session_id,
            source_turn_id=source_turn_id,
        )
        extractor_fn = extractor or self.extractor or ModelRawMemoryExtractor(config=self.extractor_config)
        try:
            payload = extractor_fn(request, provenance_event, scope)
            if not isinstance(payload, Mapping):
                raise ValueError("extractor output must be an object")
        except Exception as exc:
            dropped = (DroppedReason(reason="extractor_error", ref_id=provenance_event.event_id, detail=str(exc)),)
            audit = self._append_audit(
                operation="extract_candidate",
                actor=TraceActor.MODEL_PROPOSAL.value,
                request_hash=request_hash,
                result_payload={"status": "rejected", "reason": str(exc)},
                provenance_event_ids=(provenance_event.event_id,),
                dropped=dropped,
            )
            result = RawIngestResult(
                status="rejected",
                provenance_receipt=receipt,
                provenance_event=provenance_event,
                candidate=None,
                proposal_card=None,
                dropped=dropped,
                audit_events=(capture_audit, audit),
                extractor_config=self.extractor_config,
                request_hash=request_hash,
                result_hash=stable_hash({"status": "rejected", "provenance_event_id": provenance_event.event_id}),
            )
            return result

        candidate, status, dropped = self._candidate_from_extractor_payload(
            payload,
            request=request,
            provenance_event=provenance_event,
            default_scope=scope,
        )
        extract_audit = self._append_audit(
            operation="extract_candidate",
            actor=TraceActor.MODEL_PROPOSAL.value if candidate and candidate.proposed_by == CandidateProducer.MODEL.value else TraceActor.CORE.value,
            request_hash=request_hash,
            result_payload={"status": status, "candidate_id": candidate.candidate_id if candidate else None},
            provenance_event_ids=(provenance_event.event_id,),
            card_ids=(),
            dropped=dropped,
            metadata={
                "extractor_config_hash": stable_hash(self.extractor_config.to_dict()),
                "candidate_hash": candidate.stable_hash() if candidate else None,
            },
        )
        audit_events = [capture_audit, extract_audit]
        proposal_card: MemoryCard | None = None
        if candidate is not None:
            self.candidates[candidate.candidate_id] = candidate
            proposal_card, propose_audit = self.propose_memory(candidate, source_provenance_id=provenance_event.event_id)
            audit_events.append(propose_audit)
            if status == "candidate":
                status = "proposal"
            if Decimal(str(candidate.confidence)) < Decimal("0.50"):
                status = "low_confidence_proposal"
        result_payload = {
            "status": status,
            "provenance_event_id": provenance_event.event_id,
            "candidate_id": candidate.candidate_id if candidate else None,
            "proposal_card_id": proposal_card.card_id if proposal_card else None,
        }
        return RawIngestResult(
            status=status,
            provenance_receipt=receipt,
            provenance_event=provenance_event,
            candidate=candidate,
            proposal_card=proposal_card,
            dropped=dropped,
            audit_events=tuple(audit_events),
            extractor_config=self.extractor_config,
            request_hash=request_hash,
            result_hash=stable_hash(result_payload),
        )

    def capture_raw_provenance(
        self,
        request: RawMemoryIngestRequest,
        *,
        scope: Scope,
        actor: str = ProvenanceProducer.USER.value,
        source_experience_id: str | None = None,
        source_run_id: str | None = None,
        source_session_id: str | None = None,
        source_turn_id: str | None = None,
        source_mutation_id: str | None = None,
    ) -> tuple[ProvenanceEvent, ProvenanceReceipt, MemoryAuditEvent]:
        timestamp = self.clock()
        payload_hash = stable_hash({"raw_text": request.raw_text})
        event_id = self._unique_id(
            self.provenance_events,
            "prov",
            {
                "kind": RawEventKind.RAW_TRANSCRIPT.value,
                "payload_hash": payload_hash,
                "scope": scope.to_dict(),
                "source_experience_id": source_experience_id,
            },
        )
        excerpt = _bounded_excerpt(request.raw_text)
        event = ProvenanceEvent(
            event_id=event_id,
            event_kind=RawEventKind.RAW_TRANSCRIPT.value,
            actor=actor,
            scope=scope,
            payload_ref=f"raw_payloads:{event_id}",
            provenance_excerpt=excerpt,
            payload_hash=payload_hash,
            content_mime="text/plain",
            source_run_id=source_run_id,
            source_session_id=source_session_id,
            source_turn_id=source_turn_id,
            source_experience_id=source_experience_id,
            source_mutation_id=source_mutation_id,
            created_at=timestamp,
        )
        self.provenance_events[event.event_id] = event
        self.raw_payloads[event.event_id] = request.raw_text
        audit = self._append_audit(
            operation="capture_provenance",
            actor=TraceActor.CORE.value,
            request_hash=stable_hash(request.to_dict()),
            result_payload={"event_id": event.event_id, "payload_hash": event.payload_hash},
            provenance_event_ids=(event.event_id,),
            metadata={
                "payload_hash": payload_hash,
                "payload_ref": event.payload_ref,
                "excerpt_hash": stable_hash({"provenance_excerpt": excerpt}) if excerpt else None,
            },
        )
        receipt = ProvenanceReceipt(
            event_id=event.event_id,
            event_kind=event.event_kind,
            producer=event.actor,
            scope=event.scope,
            payload_hash=event.payload_hash,
            excerpt_hash=stable_hash({"provenance_excerpt": excerpt}) if excerpt else None,
            source_experience_id=event.source_experience_id,
            source_mutation_id=event.source_mutation_id,
            redaction_state=event.redaction_state,
            retention_state=event.retention_state,
            audit_id=audit.audit_id,
        )
        return event, receipt, audit

    def propose_memory(self, candidate: MemoryCandidate, *, source_provenance_id: str | None = None) -> tuple[MemoryCard, MemoryAuditEvent]:
        timestamp = self.clock()
        audit_id = "pending"
        created_by = TraceActor.MODEL_PROPOSAL.value if candidate.proposed_by == CandidateProducer.MODEL.value else TraceActor.CORE.value
        card_id = self._unique_id(
            self.memory_cards,
            "mem",
            {"candidate_id": candidate.candidate_id, "candidate_hash": candidate.stable_hash()},
        )
        metadata = {
            "candidate_id": candidate.candidate_id,
            "candidate_hash": candidate.stable_hash(),
            "source_provenance_id": source_provenance_id,
        }
        card = MemoryCard(
            card_id=card_id,
            kind=candidate.proposed_kind,
            summary=candidate.summary,
            details=candidate.details,
            confidence=candidate.confidence,
            scope=candidate.proposed_scope,
            lifecycle=Lifecycle(lifespan="project_durable"),
            authority=candidate.proposed_authority,
            valence=candidate.proposed_valence,
            applicability=candidate.proposed_applicability,
            evidence_links=candidate.evidence_links,
            invalidators=candidate.proposed_invalidators,
            staleness_state=StalenessState.FRESH.value,
            contradiction_state=ContradictionState.NONE.value,
            approval_state=ApprovalState.PROPOSAL.value,
            projection_mode=ProjectionMode.DEBUG_ONLY.value,
            graph_refs=GraphRefs(),
            privacy=PrivacyRules(allowed_scope_ids=(candidate.proposed_scope.scope_key(),)),
            timestamps=MemoryTimestamps(created_at=timestamp, updated_at=timestamp),
            revision=MemoryRevision(version=1),
            audit=MemoryAuditFields(created_by=created_by, write_reason=candidate.write_reason, create_audit_id=audit_id),
            metadata=metadata,
        )
        audit = self._append_audit(
            operation="propose",
            actor=created_by,
            request_hash=candidate.stable_hash(),
            result_payload={"card_id": card.card_id, "approval_state": card.approval_state},
            card_ids=(card.card_id,),
            provenance_event_ids=(source_provenance_id,) if source_provenance_id else (),
            metadata={"candidate_id": candidate.candidate_id},
        )
        card = replace(card, audit=replace(card.audit, create_audit_id=audit.audit_id))
        self.memory_cards[card.card_id] = card
        return card, audit

    def approve_memory(
        self,
        card_id: str,
        *,
        actor: str = TraceActor.DEBUG.value,
        approval_refs: Sequence[str] = (),
        reason: str = "approved",
    ) -> MemoryLifecycleResult:
        actor = _required_text(actor, "actor")
        if actor not in _NORMAL_APPROVE_ACTORS:
            raise PermissionError(f"actor={actor} cannot approve memory")
        card = self._card(card_id)
        self._assert_transition(card.approval_state, ApprovalState.APPROVED.value, actor=actor, operation="approve")
        if actor in {TraceActor.USER.value, TraceActor.REVIEWER.value, TraceActor.VERIFIER.value, TraceActor.MAINTAINER.value} and not approval_refs:
            raise PermissionError(f"actor={actor} approval requires approval provenance refs")
        for ref_id in approval_refs:
            self._require_provenance(ref_id)
        links = tuple(card.evidence_links) + tuple(
            EvidenceLink(ref_id=ref_id, role=EvidenceRole.APPROVAL.value, active=True, note=reason)
            for ref_id in approval_refs
        )
        audit = self._append_audit(
            operation="approve",
            actor=actor,
            request_hash=stable_hash({"card_id": card_id, "approval_refs": list(approval_refs), "reason": reason}),
            result_payload={"card_id": card.card_id, "approval_state": ApprovalState.APPROVED.value},
            card_ids=(card.card_id,),
            provenance_event_ids=tuple(approval_refs),
            metadata={"reason": reason},
        )
        updated = replace(
            card,
            approval_state=ApprovalState.APPROVED.value,
            evidence_links=links,
            timestamps=replace(card.timestamps, updated_at=self.clock()),
            audit=replace(card.audit, last_semantic_mutation_audit_id=audit.audit_id),
        )
        self.memory_cards[updated.card_id] = updated
        return MemoryLifecycleResult(card=updated, audit_event=audit)

    def reject_memory(
        self,
        card_id: str,
        *,
        actor: str = TraceActor.DEBUG.value,
        reason: str = "rejected",
    ) -> MemoryLifecycleResult:
        actor = _required_text(actor, "actor")
        if actor not in _NORMAL_APPROVE_ACTORS:
            raise PermissionError(f"actor={actor} cannot reject memory proposals")
        card = self._card(card_id)
        self._assert_transition(card.approval_state, ApprovalState.REJECTED.value, actor=actor, operation="approve")
        audit = self._append_audit(
            operation="approve",
            actor=actor,
            request_hash=stable_hash({"card_id": card_id, "reason": reason, "decision": "rejected"}),
            result_payload={"card_id": card.card_id, "approval_state": ApprovalState.REJECTED.value},
            card_ids=(card.card_id,),
            metadata={"reason": reason, "decision": "rejected"},
        )
        rejected = replace(
            card,
            approval_state=ApprovalState.REJECTED.value,
            timestamps=replace(card.timestamps, updated_at=self.clock()),
            audit=replace(card.audit, last_semantic_mutation_audit_id=audit.audit_id),
        )
        self.memory_cards[rejected.card_id] = rejected
        return MemoryLifecycleResult(card=rejected, audit_event=audit)

    def commit_memory(
        self,
        card_id: str,
        *,
        actor: str = TraceActor.CORE.value,
        reason: str = "committed",
    ) -> MemoryCommitResult:
        actor = _required_text(actor, "actor")
        if actor == TraceActor.MODEL_PROPOSAL.value:
            raise PermissionError("model proposals cannot commit durable memory")
        if actor not in _NORMAL_COMMIT_ACTORS:
            raise PermissionError(f"actor={actor} cannot commit memory")
        snapshot = self._snapshot_state()
        card = self._card(card_id)
        try:
            self._assert_transition(card.approval_state, ApprovalState.COMMITTED.value, actor=actor, operation="commit")
            pending = replace(card, approval_state=ApprovalState.COMMITTED.value)
            self._validate_commit_card(pending, actor=actor, operation="commit")
            audit = self._append_audit(
                operation="commit",
                actor=actor,
                request_hash=stable_hash({"card_id": card_id, "reason": reason}),
                result_payload={"card_id": card.card_id, "approval_state": ApprovalState.COMMITTED.value},
                card_ids=(card.card_id,),
                provenance_event_ids=tuple(link.ref_id for link in pending.evidence_links),
                metadata={"reason": reason},
            )
            committed = replace(
                pending,
                timestamps=replace(card.timestamps, updated_at=self.clock()),
                audit=replace(card.audit, last_semantic_mutation_audit_id=audit.audit_id),
            )
            self.memory_cards[committed.card_id] = committed
            return MemoryCommitResult(card=committed, audit_event=audit)
        except Exception:
            self._restore_state(snapshot)
            raise

    def approve_and_commit_memory(
        self,
        card_id: str,
        *,
        actor: str = TraceActor.DEBUG.value,
        approval_refs: Sequence[str] = (),
        reason: str = "approved and committed",
    ) -> tuple[MemoryLifecycleResult, MemoryCommitResult]:
        approved = self.approve_memory(card_id, actor=actor, approval_refs=approval_refs, reason=reason)
        commit_actor = actor if actor in _NORMAL_COMMIT_ACTORS else TraceActor.CORE.value
        committed = self.commit_memory(approved.card.card_id, actor=commit_actor, reason=reason)
        return approved, committed

    def seed_committed_card_for_eval(
        self,
        card: MemoryCard,
        *,
        actor: str = TraceActor.ADAPTER.value,
        public_operation_id: str = "seed_eval",
        source_experience_id: str | None = None,
    ) -> MemoryCommitResult:
        actor = _required_text(actor, "actor")
        if actor not in {TraceActor.ADAPTER.value, TraceActor.SCORING.value}:
            raise PermissionError("seed_eval bypass is restricted to adapter or scoring actors")
        _reject_forbidden_metadata(card.metadata, "seed_eval.metadata")
        snapshot = self._snapshot_state()
        try:
            seeded = replace(
                card,
                approval_state=ApprovalState.COMMITTED.value,
                audit=replace(card.audit, created_by=actor),
            )
            self._validate_commit_card(seeded, actor=actor, operation="seed_eval")
            audit = self._append_audit(
                operation="seed_eval",
                actor=actor,
                request_hash=stable_hash({"card": card.to_dict(), "public_operation_id": public_operation_id}),
                result_payload={"card_id": seeded.card_id, "approval_state": seeded.approval_state},
                card_ids=(seeded.card_id,),
                provenance_event_ids=tuple(link.ref_id for link in seeded.evidence_links),
                metadata={"public_operation_id": public_operation_id, "source_experience_id": source_experience_id},
            )
            seeded = replace(
                seeded,
                audit=replace(seeded.audit, create_audit_id=audit.audit_id, last_semantic_mutation_audit_id=audit.audit_id),
            )
            self.memory_cards[seeded.card_id] = seeded
            return MemoryCommitResult(card=seeded, audit_event=audit, bypass="seed_eval")
        except Exception:
            self._restore_state(snapshot)
            raise

    def import_migrated_card(self, card: MemoryCard, *, source_schema_version: str = "legacy") -> MemoryCommitResult:
        if card.audit.created_by != TraceActor.MIGRATION.value:
            raise PermissionError("migration bypass requires card.audit.created_by=migration")
        snapshot = self._snapshot_state()
        try:
            migrated = replace(card, approval_state=ApprovalState.COMMITTED.value)
            self._validate_commit_card(migrated, actor=TraceActor.MIGRATION.value, operation="migrate")
            audit = self._append_audit(
                operation="migrate",
                actor=TraceActor.MIGRATION.value,
                request_hash=stable_hash({"card": card.to_dict(), "source_schema_version": source_schema_version}),
                result_payload={"card_id": migrated.card_id, "approval_state": migrated.approval_state},
                card_ids=(migrated.card_id,),
                provenance_event_ids=tuple(link.ref_id for link in migrated.evidence_links),
                metadata={"source_schema_version": source_schema_version, "target_schema_version": migrated.schema_version},
            )
            migrated = replace(
                migrated,
                audit=replace(migrated.audit, create_audit_id=audit.audit_id, last_semantic_mutation_audit_id=audit.audit_id),
            )
            self.memory_cards[migrated.card_id] = migrated
            return MemoryCommitResult(card=migrated, audit_event=audit, bypass="migration")
        except Exception:
            self._restore_state(snapshot)
            raise

    def emergency_restore_new_revision(
        self,
        card: MemoryCard,
        *,
        source_card_id: str,
        actor: str = TraceActor.CORE.value,
        reason: str = "emergency restore",
    ) -> MemoryCommitResult:
        if card.card_id == source_card_id:
            raise ValueError("emergency restore must create a new card revision, not reverse the old card state")
        snapshot = self._snapshot_state()
        try:
            restored = replace(
                card,
                approval_state=ApprovalState.COMMITTED.value,
                revision=replace(card.revision, supersedes=tuple(sorted({*card.revision.supersedes, source_card_id}))),
            )
            self._validate_commit_card(restored, actor=actor, operation="rollback")
            audit = self._append_audit(
                operation="rollback",
                actor=actor,
                request_hash=stable_hash({"card": card.to_dict(), "source_card_id": source_card_id, "reason": reason}),
                result_payload={"card_id": restored.card_id, "source_card_id": source_card_id},
                card_ids=(restored.card_id, source_card_id),
                provenance_event_ids=tuple(link.ref_id for link in restored.evidence_links),
                metadata={"reason": reason},
            )
            restored = replace(
                restored,
                audit=replace(restored.audit, create_audit_id=audit.audit_id, last_semantic_mutation_audit_id=audit.audit_id),
            )
            self.memory_cards[restored.card_id] = restored
            return MemoryCommitResult(card=restored, audit_event=audit, bypass="emergency_restore")
        except Exception:
            self._restore_state(snapshot)
            raise

    def mutate_memory(self, mutation: MemoryMutation) -> MemoryMutationResult:
        snapshot = self._snapshot_state()
        try:
            target = self._card(mutation.target_card_id)
            if mutation.op == "update":
                cards = (self._mutate_update(target, mutation),)
            elif mutation.op == "delete":
                cards = (self._mutate_terminal(target, mutation, deleted=True),)
            elif mutation.op == "tombstone":
                cards = (self._mutate_terminal(target, mutation, tombstone=True),)
            elif mutation.op == "forget":
                cards = (self._mutate_forget(target, mutation),)
            elif mutation.op == "supersede":
                cards = self._mutate_supersede(target, mutation)
            else:  # pragma: no cover - dataclass validation keeps this unreachable.
                raise ValueError(f"unsupported mutation op: {mutation.op}")
            audit = self._append_audit(
                operation="mutate",
                actor=mutation.actor,
                request_hash=stable_hash(
                    {
                        "mutation_id": mutation.mutation_id,
                        "op": mutation.op,
                        "target_card_id": mutation.target_card_id,
                        "patch": _stable_patch_payload(mutation.patch),
                        "replacement_card": mutation.replacement_card.to_dict() if mutation.replacement_card else None,
                        "reason": mutation.reason,
                        "actor": mutation.actor,
                        "authority_refs": list(mutation.authority_refs),
                    }
                ),
                result_payload={"card_ids": [card.card_id for card in cards], "op": mutation.op},
                card_ids=tuple(card.card_id for card in cards),
                provenance_event_ids=tuple(mutation.authority_refs),
                mutation_ids=(mutation.mutation_id,),
                metadata={"reason": mutation.reason, "op": mutation.op},
            )
            updated_cards = []
            for card in cards:
                updated = replace(card, audit=replace(card.audit, last_semantic_mutation_audit_id=audit.audit_id))
                self.memory_cards[updated.card_id] = updated
                updated_cards.append(updated)
            return MemoryMutationResult(mutation=mutation, cards=tuple(updated_cards), audit_event=audit)
        except Exception:
            self._restore_state(snapshot)
            raise

    def retrieve(self, request: MemoryRecallRequest, *, actor: str = TraceActor.CORE.value) -> MemoryRetrieveResult:
        start = time.perf_counter()
        request_hash = stable_hash(request.to_request_payload())
        query_tokens = _tokens(request.query)
        dropped: list[CallerVisibleDroppedRecord] = []
        internal_dropped: list[DroppedReason] = []
        dropped_counts: dict[str, int] = {}
        scored: list[tuple[dict[str, str], MemoryCard, Decimal, bool]] = []
        scanned = 0
        now = request.now or self.clock()
        for card in sorted(self.memory_cards.values(), key=lambda item: item.card_id):
            scanned += 1
            reason = self._drop_reason(card, request, now=now)
            if reason is None:
                reason = self._invalidator_drop_reason(card, request.current_evidence)
            if reason is not None:
                _add_drop(reason, card, dropped, internal_dropped, dropped_counts)
                continue
            components, final_score, exact_scope = self._score_card(card, query_tokens, request)
            if query_tokens and Decimal(components["lexical_score"]) == Decimal("0.0000") and not request.applicability_refs:
                _add_drop("no_relevant_memory", card, dropped, internal_dropped, dropped_counts)
                continue
            scored.append((components, card, final_score, exact_scope))

        scored.sort(
            key=lambda item: (
                -item[2],
                not item[3],
                -_AUTHORITY_RANK[item[1].authority.strength],
                item[1].timestamps.last_verified_at is None,
                _reverse_iso(item[1].timestamps.last_verified_at),
                len(item[1].summary),
                item[1].card_id,
            )
        )
        ranked = []
        for index, (components, card, _final_score, _exact_scope) in enumerate(scored[: request.limit], start=1):
            ranked.append(self._ranked_evidence(index, card, components))
        latency_ms = 0.0
        if request.latency_source == "wall_clock":
            latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
        usage = MemoryUsage(
            latency_ms=latency_ms,
            latency_source=request.latency_source,
            cards_scanned=scanned,
            cards_ranked=len(scored),
            cards_returned=len(ranked),
            cards_dropped=sum(dropped_counts.values()),
            projection_chars=sum(len(item.metadata.get("summary", "")) for item in ranked),
            index_mode="direct_scan",
        )
        abstained = not ranked
        if not self.memory_cards:
            abstained_reason = "no_memory"
        elif abstained and dropped_counts and sum(dropped_counts.values()) == scanned:
            if set(dropped_counts) == {"privacy_block"}:
                abstained_reason = "privacy_block"
            elif "no_relevant_memory" in dropped_counts:
                abstained_reason = "no_relevant_memory"
            else:
                abstained_reason = "all_dropped"
        elif abstained:
            abstained_reason = "no_relevant_memory"
        else:
            abstained_reason = None
        result_payload = {
            "ranked_evidence": [item.to_dict() for item in ranked],
            "abstained": abstained,
            "abstained_reason": abstained_reason,
            "dropped_count_by_reason": dropped_counts,
            "usage": usage.to_dict(),
            "request_id": request.request_id,
            "request_hash": request_hash,
        }
        result_hash = stable_hash(result_payload)
        audit = self._append_audit(
            operation="retrieve",
            actor=actor,
            request_hash=request_hash,
            result_payload={"result_hash": result_hash, "cards_returned": len(ranked), "dropped": dropped_counts},
            card_ids=tuple(item.evidence_ref for item in ranked),
            dropped=tuple(internal_dropped),
            usage=usage.to_dict(),
            metadata={"request_id": request.request_id, "index_mode": usage.index_mode},
        )
        return MemoryRetrieveResult(
            ranked_evidence=tuple(ranked),
            abstained=abstained,
            abstained_reason=abstained_reason,
            dropped=tuple(dropped),
            dropped_count_by_reason=dropped_counts,
            usage=usage,
            request_id=request.request_id or "",
            request_hash=request_hash,
            result_hash=result_hash,
            audit_event=audit,
        )

    def report_usage(self, scope: Scope | None = None) -> MemoryUsageReport:
        retrieve_audits = [event for event in self.memory_audit_log if event.operation == "retrieve"]
        if scope is not None:
            scope_key = scope.scope_key()
            retrieve_audits = [
                event
                for event in retrieve_audits
                if any((self.memory_cards.get(card_id) and self.memory_cards[card_id].scope.scope_key() == scope_key) for card_id in event.card_ids)
            ]
        index_counts: dict[str, int] = {}
        latency_counts: dict[str, int] = {}
        token_missing = 0
        cost_missing = 0
        token_sum = 0
        cost_sum = Decimal("0")
        totals = {
            "latency_ms": 0.0,
            "cards_scanned": 0,
            "cards_ranked": 0,
            "cards_returned": 0,
            "cards_dropped": 0,
            "graph_nodes_expanded": 0,
            "graph_edges_expanded": 0,
            "projection_chars": 0,
        }
        for event in retrieve_audits:
            usage = event.usage
            for key in totals:
                totals[key] += usage.get(key, 0) or 0
            index = usage.get("index_mode") or "direct_scan"
            index_counts[index] = index_counts.get(index, 0) + 1
            latency_source = usage.get("latency_source") or "deterministic_mock"
            latency_counts[latency_source] = latency_counts.get(latency_source, 0) + 1
            if usage.get("token_count") is None:
                token_missing += 1
            else:
                token_sum += int(usage["token_count"])
            if usage.get("cost_units") is None:
                cost_missing += 1
            else:
                cost_sum += Decimal(str(usage["cost_units"]))
        index_mode = "direct_scan"
        for candidate in ("vector", "graph_index", "sync_lexical", "direct_scan"):
            if index_counts.get(candidate):
                index_mode = candidate
                break
        latency_source = "deterministic_mock"
        for candidate in _LATENCY_SOURCE_PRECEDENCE:
            if latency_counts.get(candidate):
                latency_source = candidate
                break
        usage = MemoryUsage(
            latency_ms=float(totals["latency_ms"]),
            latency_source=latency_source,
            cards_scanned=totals["cards_scanned"],
            cards_ranked=totals["cards_ranked"],
            cards_returned=totals["cards_returned"],
            cards_dropped=totals["cards_dropped"],
            graph_nodes_expanded=totals["graph_nodes_expanded"],
            graph_edges_expanded=totals["graph_edges_expanded"],
            projection_chars=totals["projection_chars"],
            index_mode=index_mode,
            token_count=None if token_missing else token_sum,
            cost_units=None if cost_missing else float(cost_sum),
        )
        return MemoryUsageReport(
            scope=scope,
            usage=usage,
            request_count=len(retrieve_audits),
            metadata={
                "index_mode_counts": index_counts,
                "latency_source_counts": latency_counts,
                "missing_token_count_requests": token_missing,
                "missing_cost_units_requests": cost_missing,
            },
        )

    def store_transient_reentry(
        self,
        *,
        session_id: str,
        scope: Scope,
        summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> TransientReentryRecord:
        record = TransientReentryRecord(
            record_id=self._unique_id(
                {record.record_id: record for records in self.transient_reentry_records.values() for record in records},
                "transient",
                {"session_id": session_id, "scope": scope.to_dict(), "summary": summary},
            ),
            session_id=session_id,
            scope=scope,
            summary=summary,
            created_at=self.clock(),
            metadata=metadata or {},
        )
        self.transient_reentry_records.setdefault(record.session_id, []).append(record)
        return record

    def retrieve_transient_reentry(
        self,
        *,
        session_id: str,
        scope: Scope,
        actor: str = TraceActor.CORE.value,
    ) -> TransientReentryRecallResult:
        session_id = _required_text(session_id, "session_id")
        scope = scope if isinstance(scope, Scope) else Scope.from_dict(scope)
        request_hash = stable_hash({"session_id": session_id, "scope": scope.to_dict()})
        records = tuple(
            record
            for record in self.transient_reentry_records.get(session_id, ())
            if record.scope.scope_key() == scope.scope_key()
        )
        result_payload = {"records": [record.to_dict() for record in records], "request_hash": request_hash}
        audit = self._append_audit(
            operation="retrieve_transient",
            actor=actor,
            request_hash=request_hash,
            result_payload=result_payload,
            metadata={"session_id": session_id, "record_count": len(records), "durable_support_ids": False},
        )
        return TransientReentryRecallResult(
            records=records,
            request_hash=request_hash,
            result_hash=stable_hash(result_payload),
            audit_event=audit,
        )

    def add_graph_node(self, node: GraphNode) -> None:
        self.graph_nodes[node.node_id] = node

    def add_graph_edge(self, edge: GraphEdge) -> None:
        self.graph_edges[edge.edge_id] = edge

    def _candidate_from_extractor_payload(
        self,
        payload: Mapping[str, Any],
        *,
        request: RawMemoryIngestRequest,
        provenance_event: ProvenanceEvent,
        default_scope: Scope,
    ) -> tuple[MemoryCandidate | None, str, tuple[DroppedReason, ...]]:
        decision = _clean_text(payload.get("decision") or payload.get("status") or "candidate").casefold()
        if decision not in {"candidate", "reject", "rejected", "clarification_needed"}:
            decision = "clarification_needed"
        dropped = []
        if _contains_forbidden_model_commit(payload):
            dropped.append(DroppedReason(reason="model_requested_commit", ref_id=provenance_event.event_id))
        if decision in {"reject", "rejected"}:
            return None, "rejected", tuple(dropped or (DroppedReason(reason="extractor_rejected", ref_id=provenance_event.event_id),))
        if decision == "clarification_needed":
            return None, "clarification_needed", tuple(dropped or (DroppedReason(reason="clarification_needed", ref_id=provenance_event.event_id),))
        raw_candidate = payload.get("candidate") if isinstance(payload.get("candidate"), Mapping) else payload
        if not isinstance(raw_candidate, Mapping):
            return None, "clarification_needed", (DroppedReason(reason="invalid_candidate", ref_id=provenance_event.event_id),)
        confidence = _bounded_confidence(raw_candidate.get("confidence", payload.get("confidence", 0.0)))
        ambiguous = bool(raw_candidate.get("ambiguous") or payload.get("ambiguous"))
        if ambiguous and confidence > 0.49:
            confidence = 0.49
        summary = _clean_text(raw_candidate.get("summary") or "")
        if not summary:
            return None, "clarification_needed", (DroppedReason(reason="missing_summary", ref_id=provenance_event.event_id),)
        if _looks_like_raw_copy(summary, request.raw_text):
            return None, "rejected", (DroppedReason(reason="raw_transcript_not_memory", ref_id=provenance_event.event_id),)
        details = _clean_text(raw_candidate.get("details") or "") or None
        if details and _looks_like_raw_copy(details, request.raw_text):
            return None, "rejected", (DroppedReason(reason="raw_transcript_not_memory", ref_id=provenance_event.event_id),)
        scope = default_scope
        if isinstance(raw_candidate.get("scope"), Mapping):
            scope = Scope.from_dict(raw_candidate["scope"])
        authority_payload = raw_candidate.get("authority") if isinstance(raw_candidate.get("authority"), Mapping) else {}
        source_refs = tuple(authority_payload.get("source_refs") or ())
        if not source_refs:
            source_refs = (provenance_event.event_id,)
        authority = Authority(
            source=authority_payload.get("source", AuthoritySource.SELF.value),
            strength=authority_payload.get("strength", AuthorityStrength.HINT.value),
            source_refs=source_refs,
        )
        valence = Valence.from_dict(raw_candidate.get("valence") or {})
        applicability_payload = raw_candidate.get("applicability") if isinstance(raw_candidate.get("applicability"), Mapping) else {}
        if not applicability_payload.get("applies_to"):
            applicability_payload = {**applicability_payload, "applies_to": (scope.scope_key(),)}
        applicability = Applicability.from_dict(applicability_payload)
        invalidators = tuple(Invalidator.from_dict(item) for item in raw_candidate.get("invalidators") or ())
        proposed_by = raw_candidate.get("proposed_by") or CandidateProducer.MODEL.value
        evidence_links = (
            EvidenceLink(
                ref_id=provenance_event.event_id,
                role=EvidenceRole.CURRENT_SUPPORT.value,
                active=True,
                note="raw ingest extracted support",
            ),
        )
        candidate_id = self._unique_id(
            self.candidates,
            "cand",
            {
                "provenance_event_id": provenance_event.event_id,
                "summary": summary,
                "kind": raw_candidate.get("kind", MemoryCardKind.SEMANTIC_FACT.value),
            },
        )
        candidate = MemoryCandidate(
            candidate_id=candidate_id,
            proposed_kind=raw_candidate.get("kind", MemoryCardKind.SEMANTIC_FACT.value),
            summary=summary,
            details=details,
            evidence_links=evidence_links,
            proposed_scope=scope,
            proposed_authority=authority,
            proposed_valence=valence,
            proposed_applicability=applicability,
            proposed_invalidators=invalidators,
            confidence=confidence,
            write_reason=_clean_text(raw_candidate.get("write_reason") or "raw ingest extractor proposal"),
            proposed_by=proposed_by,
        )
        if confidence < 0.5:
            dropped.append(DroppedReason(reason="low_confidence", ref_id=provenance_event.event_id))
        return candidate, "candidate", tuple(dropped)

    def _mutate_update(self, target: MemoryCard, mutation: MemoryMutation) -> MemoryCard:
        if target.approval_state != ApprovalState.COMMITTED.value:
            raise ValueError("update requires a committed target card")
        patch = _normalize_patch(mutation.patch or {})
        if not patch:
            raise ValueError("update requires at least one allowed patch field")
        evidence_links = self._replacement_evidence_links(
            target,
            mutation,
            requires_replacement_support=bool(_SEMANTIC_PATCH_FIELDS & set(patch)),
        )
        lifecycle = target.lifecycle
        if "lifecycle" in patch and "expires_at" in patch["lifecycle"]:
            lifecycle = replace(lifecycle, expires_at=patch["lifecycle"]["expires_at"])
        privacy = target.privacy
        if "privacy" in patch and "redaction_policy" in patch["privacy"]:
            privacy = replace(privacy, redaction_policy=patch["privacy"]["redaction_policy"] or RedactionPolicy.NONE.value)
        details = target.details
        if "details" in patch:
            details = patch["details"]
        invalidators = target.invalidators
        if "invalidators" in patch:
            invalidators = tuple(Invalidator.from_dict(item) if isinstance(item, Mapping) else item for item in patch["invalidators"])
        updated = replace(
            target,
            summary=patch.get("summary", target.summary),
            details=details,
            confidence=patch.get("confidence", target.confidence),
            applicability=Applicability.from_dict(patch["applicability"]) if "applicability" in patch else target.applicability,
            valence=Valence.from_dict(patch["valence"]) if "valence" in patch else target.valence,
            evidence_links=evidence_links,
            invalidators=invalidators,
            lifecycle=lifecycle,
            privacy=privacy,
            timestamps=replace(target.timestamps, updated_at=self.clock()),
            revision=replace(target.revision, version=target.revision.version + 1),
            metadata={**target.metadata, "last_mutation_op": "update", "last_mutation_id": mutation.mutation_id},
        )
        self._validate_commit_card(updated, actor=mutation.actor, operation="mutate")
        return updated

    def _mutate_terminal(
        self,
        target: MemoryCard,
        mutation: MemoryMutation,
        *,
        deleted: bool = False,
        tombstone: bool = False,
    ) -> MemoryCard:
        if target.approval_state not in {ApprovalState.COMMITTED.value, ApprovalState.SUPERSEDED.value}:
            raise ValueError(f"{mutation.op} requires an active or superseded target card")
        metadata = {**target.metadata, "last_mutation_op": mutation.op, "last_mutation_id": mutation.mutation_id}
        if deleted:
            metadata["phase_b_deleted"] = True
        if tombstone:
            metadata["phase_b_tombstoned"] = True
        return replace(
            target,
            approval_state=ApprovalState.TOMBSTONED.value,
            timestamps=replace(target.timestamps, updated_at=self.clock(), tombstoned_at=self.clock()),
            metadata=metadata,
        )

    def _mutate_forget(self, target: MemoryCard, mutation: MemoryMutation) -> MemoryCard:
        if target.approval_state not in {ApprovalState.COMMITTED.value, ApprovalState.SUPERSEDED.value, ApprovalState.TOMBSTONED.value}:
            raise ValueError("forget requires an existing durable target card")
        if not mutation.authority_refs and mutation.actor not in {TraceActor.USER.value, TraceActor.DEBUG.value, TraceActor.MAINTAINER.value}:
            raise PermissionError("forget requires privacy/security/user authority refs or a privileged actor")
        for link in target.evidence_links:
            event = self.provenance_events.get(link.ref_id)
            if event is None:
                continue
            redacted = replace(
                event,
                provenance_excerpt=None,
                payload_ref=None,
                redaction_state=RedactionState.RESTRICTED.value,
                retention_state=RetentionState.DELETED.value,
            )
            self.provenance_events[event.event_id] = redacted
            self.raw_payloads.pop(event.event_id, None)
        forgotten_links = tuple(replace(link, active=False, note="forgotten") for link in target.evidence_links)
        return replace(
            target,
            approval_state=ApprovalState.TOMBSTONED.value,
            evidence_links=forgotten_links,
            timestamps=replace(target.timestamps, updated_at=self.clock(), tombstoned_at=self.clock()),
            metadata={**target.metadata, "phase_b_forgotten": True, "last_mutation_op": "forget", "last_mutation_id": mutation.mutation_id},
        )

    def _mutate_supersede(self, target: MemoryCard, mutation: MemoryMutation) -> tuple[MemoryCard, MemoryCard]:
        if target.approval_state != ApprovalState.COMMITTED.value:
            raise ValueError("supersede requires a committed target card")
        if mutation.replacement_card is not None:
            replacement = mutation.replacement_card
            if replacement.card_id == target.card_id:
                raise ValueError("supersede replacement must use a new card_id")
            self._validate_replacement_card_support(target, replacement, mutation)
            replacement = replace(
                replacement,
                approval_state=ApprovalState.COMMITTED.value,
                revision=replace(
                    replacement.revision,
                    supersedes=tuple(sorted({*replacement.revision.supersedes, target.card_id})),
                ),
            )
        else:
            patch = _normalize_patch(mutation.patch or {})
            if "summary" not in patch:
                raise ValueError("supersede requires replacement summary when no replacement_card is supplied")
            evidence_links = self._replacement_evidence_links(
                target,
                mutation,
                requires_replacement_support=True,
            )
            new_id = self._unique_id(
                self.memory_cards,
                "mem",
                {"supersedes": target.card_id, "mutation_id": mutation.mutation_id, "summary": patch["summary"]},
            )
            replacement = replace(
                target,
                card_id=new_id,
                summary=patch["summary"],
                details=patch.get("details", target.details),
                evidence_links=evidence_links,
                approval_state=ApprovalState.COMMITTED.value,
                staleness_state=StalenessState.FRESH.value,
                contradiction_state=ContradictionState.NONE.value,
                timestamps=MemoryTimestamps(created_at=self.clock(), updated_at=self.clock()),
                revision=MemoryRevision(version=target.revision.version + 1, supersedes=(target.card_id,)),
                metadata={**target.metadata, "last_mutation_op": "supersede", "last_mutation_id": mutation.mutation_id},
            )
        self._validate_commit_card(replacement, actor=mutation.actor, operation="mutate")
        old = replace(
            target,
            approval_state=ApprovalState.SUPERSEDED.value,
            staleness_state=StalenessState.SUPERSEDED.value,
            timestamps=replace(target.timestamps, updated_at=self.clock(), superseded_at=self.clock()),
            revision=replace(target.revision, superseded_by=tuple(sorted({*target.revision.superseded_by, replacement.card_id}))),
            metadata={**target.metadata, "last_mutation_op": "supersede", "last_mutation_id": mutation.mutation_id},
        )
        return old, replacement

    def _replacement_evidence_links(
        self,
        target: MemoryCard,
        mutation: MemoryMutation,
        *,
        requires_replacement_support: bool,
    ) -> tuple[EvidenceLink, ...]:
        if not requires_replacement_support:
            return target.evidence_links
        if not mutation.authority_refs:
            raise ValueError("semantic update/supersede requires replacement provenance current_support refs")
        active_support_refs = {
            link.ref_id
            for link in target.evidence_links
            if link.active and link.role == EvidenceRole.CURRENT_SUPPORT.value
        }
        for ref_id in mutation.authority_refs:
            event = self._require_provenance(ref_id)
            if ref_id in active_support_refs:
                raise ValueError("replacement provenance must not reuse existing active current_support refs")
            if event.source_mutation_id != mutation.mutation_id:
                raise ValueError("replacement provenance must cite the current mutation as source_mutation_id")
        old_links = tuple(
            replace(link, active=False, note=f"replaced by {mutation.mutation_id}")
            if link.active and link.role == EvidenceRole.CURRENT_SUPPORT.value
            else link
            for link in target.evidence_links
        )
        new_links = tuple(
            EvidenceLink(
                ref_id=ref_id,
                role=EvidenceRole.CURRENT_SUPPORT.value,
                active=True,
                added_by_mutation_id=mutation.mutation_id,
                note="replacement support",
            )
            for ref_id in mutation.authority_refs
        )
        return old_links + new_links

    def _validate_replacement_card_support(self, target: MemoryCard, replacement: MemoryCard, mutation: MemoryMutation) -> None:
        active_target_support_refs = {
            link.ref_id
            for link in target.evidence_links
            if link.active and link.role in {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value}
        }
        active_replacement_support = tuple(
            link
            for link in replacement.evidence_links
            if link.active and link.role in {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value}
        )
        if not active_replacement_support:
            return
        for link in active_replacement_support:
            event = self._require_provenance(link.ref_id)
            if link.ref_id in active_target_support_refs:
                raise ValueError("replacement provenance must not reuse existing active current_support refs")
            if event.source_mutation_id != mutation.mutation_id:
                raise ValueError("replacement provenance must cite the current mutation as source_mutation_id")

    def _drop_reason(self, card: MemoryCard, request: MemoryRecallRequest, *, now: str) -> str | None:
        if not _privacy_allows(card, request.authorization_scope or request.scope, shared_policy_ids=()):
            return "privacy_block"
        if not _scope_allows(request.scope, card.scope, card_kind=card.kind):
            return "out_of_scope"
        if not _applicability_allows(card, request):
            return "out_of_scope"
        if card.approval_state != ApprovalState.COMMITTED.value:
            return _inactive_drop_reason(card)
        if request.kinds and card.kind not in request.kinds:
            return "kind_mismatch"
        if card.lifecycle.expires_at and _iso_lte(card.lifecycle.expires_at, now):
            return "stale"
        if card.staleness_state == StalenessState.MAYBE_STALE.value and not request.include_maybe_stale:
            return "stale"
        if card.staleness_state in {StalenessState.STALE.value, StalenessState.SUPERSEDED.value}:
            return card.staleness_state
        if card.contradiction_state in {ContradictionState.CONTRADICTED.value, ContradictionState.POSSIBLE.value}:
            return "contradicted"
        if not any(self._visible_support_link(link) for link in card.evidence_links if link.active):
            return "missing_evidence"
        return None

    def _invalidator_drop_reason(self, card: MemoryCard, current_evidence: CurrentEvidenceSnapshot | None) -> str | None:
        if not current_evidence:
            return None
        for invalidator in card.invalidators:
            if _invalidator_triggered(card, invalidator, current_evidence):
                return "invalidator_triggered"
        return None

    def _score_card(
        self,
        card: MemoryCard,
        query_tokens: set[str],
        request: MemoryRecallRequest,
    ) -> tuple[dict[str, str | None], Decimal, bool]:
        exact_scope = request.scope.scope_key() == card.scope.scope_key()
        structured = Decimal("1.0000")
        lexical = Decimal("0.0000")
        if query_tokens:
            card_tokens = _tokens(_card_search_text(card))
            lexical = Decimal(len(query_tokens & card_tokens)) / Decimal(max(1, len(query_tokens)))
        scope_modifier = Decimal("0.3000") if exact_scope else Decimal("0.1000")
        authority_modifier = _AUTHORITY_RANK[card.authority.strength] + _AUTHORITY_SOURCE_RANK[card.authority.source]
        freshness_modifier = Decimal("0.2000") if card.staleness_state == StalenessState.FRESH.value else Decimal("0.0000")
        contradiction_modifier = Decimal("0.0000") if card.contradiction_state == ContradictionState.NONE.value else Decimal("-0.2000")
        confidence_modifier = Decimal(str(card.confidence)) / Decimal("10")
        final = structured + (lexical * Decimal("2.0000")) + scope_modifier + authority_modifier + freshness_modifier + contradiction_modifier + confidence_modifier
        components = {
            "structured_match": canonical_score(structured),
            "lexical_score": canonical_score(lexical),
            "vector_score": None,
            "reranker_score": None,
            "scope_modifier": canonical_score(scope_modifier),
            "authority_modifier": canonical_score(authority_modifier),
            "freshness_modifier": canonical_score(freshness_modifier),
            "contradiction_modifier": canonical_score(contradiction_modifier),
            "confidence_modifier": canonical_score(confidence_modifier),
            "graph_modifier": canonical_score(Decimal("0")),
            "budget_modifier": canonical_score(Decimal("0")),
            "final_score": canonical_score(final),
        }
        return components, Decimal(components["final_score"]), exact_scope

    def _ranked_evidence(self, rank: int, card: MemoryCard, components: Mapping[str, str | None]) -> RankedMemoryEvidence:
        support_ref_ids = tuple(
            sorted(
                link.ref_id
                for link in card.evidence_links
                if link.active and link.role == EvidenceRole.CURRENT_SUPPORT.value and self._visible_support_link(link)
            )
        )
        source_ref_ids = tuple(
            sorted(
                link.ref_id
                for link in card.evidence_links
                if link.active and link.role in {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value} and self._visible_support_link(link)
            )
        )
        lineage_ref_ids = tuple(sorted(link.ref_id for link in card.evidence_links if link.role in {EvidenceRole.LINEAGE.value, EvidenceRole.SUPERSESSION.value}))
        refs_by_role: dict[str, list[str]] = {}
        for link in card.evidence_links:
            if link.active and self._visible_support_link(link):
                refs_by_role.setdefault(link.role, []).append(link.ref_id)
        support_experience_ids = _experience_ids(self.provenance_events, support_ref_ids)
        source_experience_ids = _experience_ids(self.provenance_events, source_ref_ids)
        lineage_experience_ids = _experience_ids(self.provenance_events, lineage_ref_ids)
        source_mutation_ids = tuple(
            sorted(
                {
                    event.source_mutation_id
                    for ref_id in source_ref_ids
                    if (event := self.provenance_events.get(ref_id)) is not None and event.source_mutation_id
                }
            )
        )
        mutation_refs = tuple(
            sorted(
                ref
                for ref in (
                    *(link.added_by_mutation_id for link in card.evidence_links if link.added_by_mutation_id),
                    card.metadata.get("last_mutation_id"),
                )
                if ref
            )
        )
        state = "maybe_stale" if card.staleness_state == StalenessState.MAYBE_STALE.value else "active"
        return RankedMemoryEvidence(
            rank=rank,
            evidence_ref=card.card_id,
            support_experience_ids=support_experience_ids,
            source_experience_ids=source_experience_ids,
            lineage_experience_ids=lineage_experience_ids,
            provenance_refs=support_ref_ids,
            source_mutation_ids=source_mutation_ids,
            mutation_refs=mutation_refs,
            score=components["final_score"] or "0.0000",
            score_type="deterministic_weighted_sum",
            score_components=dict(components),
            state=state,
            scope_id=card.scope.scope_key(),
            metadata={
                "card_id": card.card_id,
                "card_kind": card.kind,
                "summary": card.summary,
                "approval_state": card.approval_state,
                "staleness_state": card.staleness_state,
                "contradiction_state": card.contradiction_state,
                "authority": card.authority.to_dict(),
                "applicability": card.applicability.to_dict(),
                "provenance_refs_by_role": {key: sorted(value) for key, value in refs_by_role.items()},
            },
        )

    def _visible_support_link(self, link: EvidenceLink) -> bool:
        event = self.provenance_events.get(link.ref_id)
        if event is None:
            return True
        return event.redaction_state != RedactionState.RESTRICTED.value and event.retention_state == RetentionState.ACTIVE.value

    def _validate_commit_card(self, card: MemoryCard, *, actor: str, operation: str) -> None:
        if card.approval_state != ApprovalState.COMMITTED.value:
            raise ValueError("commit validation requires approval_state=committed")
        if not any(link.active and link.role in {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value} for link in card.evidence_links):
            raise ValueError("committed durable cards require active current_support or proof evidence")
        if not card.privacy.allowed_scope_ids:
            raise ValueError("committed durable cards require privacy.allowed_scope_ids")
        if card.scope.scope_key() not in card.privacy.allowed_scope_ids and not any(ref.startswith("shared_policy:v1:") for ref in card.privacy.allowed_scope_ids):
            raise ValueError("committed durable cards must include their canonical scope_key in privacy.allowed_scope_ids")
        for link in card.evidence_links:
            if link.ref_id in self.provenance_events:
                continue
            if link.role in {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value, EvidenceRole.APPROVAL.value}:
                raise ValueError(f"evidence link {link.ref_id} does not resolve to provenance")
        for node_id in card.graph_refs.node_ids:
            if node_id not in self.graph_nodes:
                raise ValueError(f"graph_refs.node_ids unresolved: {node_id}")
        for edge_id in card.graph_refs.edge_ids:
            if edge_id not in self.graph_edges:
                raise ValueError(f"graph_refs.edge_ids unresolved: {edge_id}")
        self._validate_authority(card, actor=actor, operation=operation)

    def _validate_authority(self, card: MemoryCard, *, actor: str, operation: str) -> None:
        source = card.authority.source
        if actor == TraceActor.MODEL_PROPOSAL.value:
            raise PermissionError("model proposal actor cannot authorize committed memory")
        if source == AuthoritySource.SCORING.value and operation != "seed_eval":
            raise PermissionError("authority.source=scoring is restricted to seed_eval paths")
        if card.authority.strength in {AuthorityStrength.SHOULD.value, AuthorityStrength.MUST.value} and not card.authority.source_refs:
            raise PermissionError("authority strength should/must requires source_refs")
        if source in {
            AuthoritySource.USER.value,
            AuthoritySource.REVIEWER.value,
            AuthoritySource.VERIFIER.value,
            AuthoritySource.MAINTAINER.value,
            AuthoritySource.SYSTEM.value,
        }:
            if not card.authority.source_refs:
                raise PermissionError(f"authority.source={source} requires matching provenance refs")
            if not any(self._provenance_matches_authority(ref_id, source) for ref_id in card.authority.source_refs):
                raise PermissionError(f"authority.source={source} requires matching provenance refs")
        if source == AuthoritySource.SELF.value and card.authority.strength not in {AuthorityStrength.OBSERVATION.value, AuthorityStrength.HINT.value}:
            raise PermissionError("self authority may only be observation or hint")

    def _provenance_matches_authority(self, ref_id: str, source: str) -> bool:
        event = self.provenance_events.get(ref_id)
        if event is None:
            return False
        if event.actor == source:
            return True
        if event.event_kind == RawEventKind.APPROVAL.value and source in {AuthoritySource.REVIEWER.value, AuthoritySource.USER.value, AuthoritySource.MAINTAINER.value, AuthoritySource.SYSTEM.value}:
            return True
        if source == AuthoritySource.VERIFIER.value and event.event_kind == RawEventKind.VERIFIER_OUTPUT.value:
            return True
        return False

    def _assert_transition(self, current: str, target: str, *, actor: str, operation: str) -> None:
        if current in {ApprovalState.REJECTED.value, ApprovalState.TOMBSTONED.value, ApprovalState.SUPERSEDED.value}:
            if target not in _allowed_transitions(current):
                raise ValueError(f"forbidden approval_state transition: {current} -> {target}")
        if target == ApprovalState.COMMITTED.value and current != ApprovalState.APPROVED.value:
            if operation not in {"seed_eval", "migrate", "rollback"}:
                raise ValueError("candidate/proposal -> committed bypass is restricted to seed_eval, migration, or emergency restore")
        if target not in _allowed_transitions(current):
            raise ValueError(f"forbidden approval_state transition: {current} -> {target}")
        if actor == TraceActor.MODEL_PROPOSAL.value and target == ApprovalState.COMMITTED.value:
            raise PermissionError("model proposals cannot commit durable memory")

    def _require_provenance(self, ref_id: str) -> ProvenanceEvent:
        event = self.provenance_events.get(ref_id)
        if event is None:
            raise ValueError(f"unknown provenance ref: {ref_id}")
        return event

    def _card(self, card_id: str) -> MemoryCard:
        try:
            return self.memory_cards[card_id]
        except KeyError as exc:
            raise KeyError(f"unknown memory card: {card_id}") from exc

    def _append_audit(
        self,
        *,
        operation: str,
        actor: str,
        request_hash: str,
        result_payload: Mapping[str, Any],
        card_ids: Sequence[str] = (),
        provenance_event_ids: Sequence[str | None] = (),
        mutation_ids: Sequence[str] = (),
        dropped: Sequence[DroppedReason] = (),
        usage: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryAuditEvent:
        result_hash = stable_hash(result_payload)
        audit_id = self._unique_id(
            {event.audit_id: event for event in self.memory_audit_log},
            "audit",
            {"operation": operation, "request_hash": request_hash, "result_hash": result_hash, "actor": actor},
        )
        trace = MemoryTraceEvent(
            operation=operation,
            request_hash=request_hash,
            result_hash=result_hash,
            actor=actor,
            card_ids=tuple(card_ids),
            provenance_event_ids=tuple(ref for ref in provenance_event_ids if ref),
            mutation_ids=tuple(mutation_ids),
            dropped=tuple(dropped),
            usage=usage or {},
            metadata=metadata or {},
        )
        audit = MemoryAuditEvent.from_trace(trace, audit_id=audit_id, created_at=self.clock())
        self.memory_audit_log.append(audit)
        return audit

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "memory_cards": dict(self.memory_cards),
            "provenance_events": dict(self.provenance_events),
            "raw_payloads": dict(self.raw_payloads),
            "graph_nodes": dict(self.graph_nodes),
            "graph_edges": dict(self.graph_edges),
            "memory_audit_log": list(self.memory_audit_log),
            "transient_reentry_records": {key: list(value) for key, value in self.transient_reentry_records.items()},
        }

    def _restore_state(self, snapshot: Mapping[str, Any]) -> None:
        self.memory_cards = dict(snapshot["memory_cards"])
        self.provenance_events = dict(snapshot["provenance_events"])
        self.raw_payloads = dict(snapshot["raw_payloads"])
        self.graph_nodes = dict(snapshot["graph_nodes"])
        self.graph_edges = dict(snapshot["graph_edges"])
        self.memory_audit_log = list(snapshot["memory_audit_log"])
        self.transient_reentry_records = {
            key: list(value)
            for key, value in snapshot["transient_reentry_records"].items()
        }

    def _unique_id(self, existing: Mapping[str, Any], prefix: str, payload: Mapping[str, Any]) -> str:
        base = f"{prefix}_{stable_short_hash(payload, length=16)}"
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"


def _allowed_transitions(current: str) -> set[str]:
    return {
        ApprovalState.CANDIDATE.value: {ApprovalState.PROPOSAL.value, ApprovalState.REJECTED.value},
        ApprovalState.PROPOSAL.value: {ApprovalState.APPROVED.value, ApprovalState.REJECTED.value},
        ApprovalState.APPROVED.value: {ApprovalState.COMMITTED.value, ApprovalState.REJECTED.value},
        ApprovalState.COMMITTED.value: {ApprovalState.SUPERSEDED.value, ApprovalState.TOMBSTONED.value},
        ApprovalState.SUPERSEDED.value: {ApprovalState.TOMBSTONED.value},
        ApprovalState.REJECTED.value: set(),
        ApprovalState.TOMBSTONED.value: set(),
    }[current]


def _bounded_excerpt(text: str) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= 240:
        return cleaned
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]
    return cleaned[:219].rstrip() + f" #sha256:{digest}"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _required_text(value: Any, field_name: str) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _bounded_confidence(value: Any) -> float:
    number = float(value or 0.0)
    if math.isnan(number) or math.isinf(number):
        raise ValueError("confidence must be finite")
    return max(0.0, min(1.0, number))


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text or "")}


def _card_search_text(card: MemoryCard) -> str:
    applicability = card.applicability.to_dict()
    parts = [
        card.summary,
        card.details or "",
        " ".join(applicability.get("applies_to") or ()),
        " ".join(applicability.get("prerequisites") or ()),
        " ".join(applicability.get("counterexamples") or ()),
    ]
    return " ".join(parts)


def _contains_forbidden_model_commit(payload: Mapping[str, Any]) -> bool:
    values = [payload.get("approval_state"), payload.get("state")]
    candidate = payload.get("candidate")
    if isinstance(candidate, Mapping):
        values.extend([candidate.get("approval_state"), candidate.get("state")])
    return any(_clean_text(value) == ApprovalState.COMMITTED.value for value in values)


def _looks_like_raw_copy(value: str, raw_text: str) -> bool:
    if not value:
        return False
    normalized_value = _clean_text(value).casefold()
    normalized_raw = _clean_text(raw_text).casefold()
    if len(normalized_value) > 240 and normalized_value in normalized_raw:
        return True
    speaker_lines = sum(1 for line in value.splitlines() if re.match(r"\s*(user|assistant|tool|system|developer)\s*:", line, re.I))
    return speaker_lines >= 2


def _reject_forbidden_metadata(metadata: Mapping[str, Any], path: str) -> None:
    for key, value in metadata.items():
        key_text = str(key)
        if key_text in _FORBIDDEN_SEED_KEYS:
            raise ValueError(f"{path} must not include fixture leakage key: {key_text}")
        if isinstance(value, Mapping):
            _reject_forbidden_metadata(value, f"{path}.{key_text}")


def _stable_patch_payload(patch: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if patch is None:
        return None
    return _normalize_patch(patch)


def _normalize_patch(patch: Mapping[str, Any]) -> dict[str, Any]:
    _reject_forbidden_patch_paths(patch)
    result: dict[str, Any] = {}
    clear_fields = tuple(sorted(str(item) for item in patch.get("clear_fields") or ()))
    for field_path in clear_fields:
        if field_path not in _ALLOWED_CLEAR_FIELDS:
            raise ValueError(f"clear_fields contains unsupported field: {field_path}")
    if "summary" in patch:
        if patch["summary"] is None:
            raise ValueError("summary cannot be null")
        result["summary"] = _required_text(patch["summary"], "summary")
    if "details" in patch:
        if patch["details"] is None and "details" not in clear_fields:
            raise ValueError("details=null requires clear_fields")
        result["details"] = None if patch["details"] is None else _clean_text(patch["details"])
    if "applicability" in patch:
        if patch["applicability"] is None:
            raise ValueError("applicability cannot be null")
        result["applicability"] = Applicability.from_dict(patch["applicability"]).to_dict()
    if "valence" in patch:
        if patch["valence"] is None:
            raise ValueError("valence cannot be null")
        result["valence"] = Valence.from_dict(patch["valence"]).to_dict()
    if "invalidators" in patch:
        if patch["invalidators"] is None:
            raise ValueError("invalidators cannot be null")
        result["invalidators"] = [Invalidator.from_dict(item).to_dict() if isinstance(item, Mapping) else item.to_dict() for item in patch["invalidators"]]
    if "confidence" in patch:
        if patch["confidence"] is None:
            raise ValueError("confidence cannot be null")
        result["confidence"] = _bounded_confidence(patch["confidence"])
    if "lifecycle" in patch:
        lifecycle = patch["lifecycle"] or {}
        if "expires_at" in lifecycle:
            if lifecycle["expires_at"] is None and "lifecycle.expires_at" not in clear_fields:
                raise ValueError("lifecycle.expires_at=null requires clear_fields")
            result["lifecycle"] = {"expires_at": _clean_text(lifecycle["expires_at"]) or None}
    if "privacy" in patch:
        privacy = patch["privacy"] or {}
        if "redaction_policy" in privacy:
            if privacy["redaction_policy"] is None and "privacy.redaction_policy" not in clear_fields:
                raise ValueError("privacy.redaction_policy=null requires clear_fields")
            result["privacy"] = {"redaction_policy": _clean_text(privacy["redaction_policy"]) or None}
    return result


def _reject_forbidden_patch_paths(value: Mapping[str, Any], prefix: str = "") -> None:
    for key, child in value.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text
        if path in _FORBIDDEN_PATCH_PATHS:
            raise ValueError(f"forbidden mutation patch field: {path}")
        if isinstance(child, Mapping):
            _reject_forbidden_patch_paths(child, path)


def _inactive_drop_reason(card: MemoryCard) -> str:
    if card.metadata.get("phase_b_forgotten"):
        return "forgotten"
    if card.metadata.get("phase_b_deleted"):
        return "deleted"
    if card.approval_state == ApprovalState.TOMBSTONED.value:
        return "tombstoned"
    if card.approval_state == ApprovalState.SUPERSEDED.value:
        return "superseded"
    return "not_committed"


def _add_drop(
    reason: str,
    card: MemoryCard,
    dropped: list[CallerVisibleDroppedRecord],
    internal_dropped: list[DroppedReason],
    counts: dict[str, int],
) -> None:
    counts[reason] = counts.get(reason, 0) + 1
    internal_dropped.append(DroppedReason(reason=reason, ref_id=card.card_id))
    if reason not in {"privacy_block", "forgotten", "out_of_scope"}:
        dropped.append(CallerVisibleDroppedRecord(reason=reason, evidence_ref=card.card_id))
    else:
        dropped.append(CallerVisibleDroppedRecord(reason=reason, evidence_ref=None))


def _privacy_allows(card: MemoryCard, authorization_scope: Scope, *, shared_policy_ids: Sequence[str]) -> bool:
    allowed = set(card.privacy.allowed_scope_ids)
    if not allowed:
        return False
    if authorization_scope.scope_key() in allowed:
        return True
    if card.scope.scope_key() in allowed and _scope_allows(authorization_scope, card.scope, card_kind=card.kind):
        return True
    if allowed & set(shared_policy_ids):
        return True
    return False


def _scope_allows(caller: Scope, card_scope: Scope, *, card_kind: str) -> bool:
    if caller.scope_key() == card_scope.scope_key():
        return True
    if card_scope.level == ScopeLevel.TASK.value:
        return bool(caller.task_ref and caller.task_ref == card_scope.task_ref and _same_repo_or_project(caller, card_scope))
    if card_scope.level == ScopeLevel.TASK_FAMILY.value:
        return bool(caller.task_family and caller.task_family == card_scope.task_family and _same_repo_or_project(caller, card_scope))
    if card_scope.level == ScopeLevel.BRANCH.value:
        return bool(caller.repo_ref and caller.repo_ref == card_scope.repo_ref and caller.branch_ref and caller.branch_ref == card_scope.branch_ref)
    if card_scope.level == ScopeLevel.REPO.value:
        return bool(caller.repo_ref and caller.repo_ref == card_scope.repo_ref and not card_scope.branch_ref)
    if card_scope.level == ScopeLevel.PROJECT.value:
        return bool(caller.project_id and caller.project_id == card_scope.project_id)
    if card_scope.level == ScopeLevel.USER.value:
        return bool(caller.user_id and caller.user_id == card_scope.user_id and card_kind == MemoryCardKind.POLICY_OR_PREFERENCE.value)
    if card_scope.level in {ScopeLevel.TEAM.value, ScopeLevel.SHARED.value}:
        return caller.namespace == card_scope.namespace
    return False


def _same_repo_or_project(left: Scope, right: Scope) -> bool:
    if (left.repo_ref or right.repo_ref) and left.repo_ref != right.repo_ref:
        return False
    if (left.project_id or right.project_id) and left.project_id != right.project_id:
        return False
    return True


def _applicability_allows(card: MemoryCard, request: MemoryRecallRequest) -> bool:
    request_refs = set(request.applicability_refs)
    request_refs.add(request.scope.scope_key())
    does_not = {item.value for item in (*card.applicability.does_not_apply_to, *card.applicability.counterexamples)}
    if request_refs & does_not:
        return False
    applies = {item.value for item in card.applicability.applies_to}
    if applies and not (request_refs & applies):
        return False
    return True


def _invalidator_triggered(card: MemoryCard, invalidator: Invalidator, evidence: CurrentEvidenceSnapshot) -> bool:
    if invalidator.kind == InvalidatorKind.FILE_HASH_CHANGED.value:
        for state in evidence.file_states:
            if _node_or_ref_matches(state.node_id, state.path, invalidator):
                return state.state == "missing" or bool(invalidator.baseline_hash and state.content_hash and invalidator.baseline_hash != state.content_hash)
    if invalidator.kind in {InvalidatorKind.SYMBOL_MOVED.value, InvalidatorKind.SYMBOL_REMOVED.value}:
        for state in evidence.symbol_states:
            if _node_or_ref_matches(state.node_id, state.canonical_ref, invalidator):
                if invalidator.kind == InvalidatorKind.SYMBOL_MOVED.value:
                    return state.state == "moved" or bool(invalidator.baseline_ref and state.canonical_ref and invalidator.baseline_ref != state.canonical_ref)
                return state.state == "missing"
    if invalidator.kind == InvalidatorKind.COMMAND_CHANGED.value:
        for state in evidence.command_states:
            if _node_or_ref_matches(state.node_id, state.normalized_command_ref, invalidator):
                return state.state == "changed" or bool(invalidator.baseline_hash and state.command_hash and invalidator.baseline_hash != state.command_hash)
    if invalidator.kind == InvalidatorKind.VERIFIER_CHANGED.value:
        for result in evidence.verifier_results:
            if invalidator.baseline_ref and result.verifier_ref != invalidator.baseline_ref:
                continue
            if invalidator.baseline_hash and result.result_hash and invalidator.baseline_hash != result.result_hash:
                return True
            if invalidator.baseline_value and result.result_value and invalidator.baseline_value != result.result_value:
                return True
    if invalidator.kind == InvalidatorKind.BRANCH_CHANGED.value:
        return bool(invalidator.baseline_value and evidence.branch_ref and invalidator.baseline_value != evidence.branch_ref)
    if invalidator.kind == InvalidatorKind.TASK_CONTRACT_CHANGED.value and evidence.task_contract:
        contract = evidence.task_contract
        if invalidator.baseline_ref and contract.ref != invalidator.baseline_ref:
            return True
        if invalidator.baseline_hash and contract.hash and contract.hash != invalidator.baseline_hash:
            return True
    if invalidator.kind in {
        InvalidatorKind.REVIEWER_VETOED.value,
        InvalidatorKind.USER_PREFERENCE_UPDATED.value,
        InvalidatorKind.POLICY_SUPERSEDED.value,
    }:
        return any(_authority_event_triggers(card, invalidator, event) for event in evidence.authority_events)
    if invalidator.kind == InvalidatorKind.PROCEDURE_FAILED_RECENTLY.value:
        targets = {item.value for item in card.applicability.applies_to}
        targets.update(ref for ref in (invalidator.target_node_id, invalidator.baseline_ref, invalidator.ref) if ref)
        for result in evidence.verifier_results:
            result_refs = {item.value for item in result.applicability_refs}
            result_refs.update(result.error_signature_refs)
            if result.task_ref:
                result_refs.add(result.task_ref)
            if invalidator.baseline_observed_at and not _iso_lt(invalidator.baseline_observed_at, result.observed_at):
                continue
            if result.result_value in {"fail", "error"} and targets & result_refs:
                return True
    return False


def _node_or_ref_matches(node_id: str, ref: str, invalidator: Invalidator) -> bool:
    return bool(
        (invalidator.target_node_id and node_id == invalidator.target_node_id)
        or (invalidator.baseline_ref and ref == invalidator.baseline_ref)
        or (invalidator.ref and ref == invalidator.ref)
    )


def _authority_event_triggers(card: MemoryCard, invalidator: Invalidator, event: AuthorityEvidenceEvent) -> bool:
    if invalidator.baseline_observed_at and not _iso_lt(invalidator.baseline_observed_at, event.observed_at):
        return False
    if not _scope_allows(card.scope, event.target_scope, card_kind=card.kind) and not _scope_allows(event.target_scope, card.scope, card_kind=card.kind):
        return False
    if invalidator.baseline_ref and invalidator.baseline_ref in event.supersedes_refs:
        return True
    return bool(invalidator.baseline_ref and event.ref == invalidator.baseline_ref)


def _experience_ids(events: Mapping[str, ProvenanceEvent], ref_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                event.source_experience_id
                for ref_id in ref_ids
                if (event := events.get(ref_id)) is not None
                and event.source_experience_id
                and event.redaction_state != RedactionState.RESTRICTED.value
                and event.retention_state == RetentionState.ACTIVE.value
            }
        )
    )


def _reverse_iso(value: str | None) -> str:
    return "" if value is None else "".join(chr(255 - ord(char)) for char in value)


def _iso_lte(left: str, right: str) -> bool:
    return left <= right


def _iso_lt(left: str, right: str) -> bool:
    return left < right
