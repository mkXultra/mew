from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import hashlib
import json
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MEMORY_SCHEMA_VERSION = 1

MEMORY_KINDS = (
    "project_convention",
    "episodic_task",
    "procedural_repair",
    "failure_shield",
    "reviewer_correction",
    "file_symbol_edge",
    "user_preference",
)

RAW_PROVENANCE_KINDS = (
    "raw_transcript",
    "provider_request",
    "provider_response",
    "native_transcript_item",
    "tool_result",
    "verifier_log",
    "reviewer_comment",
    "replay_bundle",
)

STALENESS_STATES = ("fresh", "maybe_stale", "stale", "superseded")
CONTRADICTION_STATES = ("none", "possible", "contradicted")
LIFECYCLE_STATES = ("committed", "tombstoned")
COMPRESSION_ACTIONS = ("candidate", "merge_existing", "drop")
COMPRESSION_SALIENCE_TERMS = (
    "approve",
    "approved",
    "bug",
    "commit",
    "decision",
    "error",
    "fail",
    "failed",
    "failure",
    "fix",
    "fixed",
    "must",
    "pass",
    "passed",
    "proof",
    "reject",
    "rejected",
    "repair",
    "review",
    "revert",
    "root cause",
    "should",
    "stale",
    "success",
    "test",
    "verify",
)


def _as_tuple(value: Optional[Iterable[Any]]) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _require_text(value: Any, name: str) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _stable_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return f"{prefix}-{_stable_json_hash(payload)[:16]}"


def _tokenize(value: str) -> Tuple[str, ...]:
    cleaned = []
    for char in value.casefold():
        cleaned.append(char if char.isalnum() or char in {"_", "-", "/"} else " ")
    return tuple(token for token in "".join(cleaned).split() if token)


def _text_similarity(left: str, right: str) -> float:
    left_terms = set(_tokenize(left))
    right_terms = set(_tokenize(right))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, len(left_terms | right_terms))


def _split_sentences(text: str) -> Tuple[str, ...]:
    normalized = _clean_text(text)
    if not normalized:
        return ()
    sentences: List[str] = []
    current: List[str] = []
    for char in normalized:
        current.append(char)
        if char in {".", "!", "?", "\n"}:
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return tuple(sentences) or (normalized,)


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = _clean_text(text)
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "..."


def _salience_terms(text: str) -> Tuple[str, ...]:
    lowered = f" {_clean_text(text).casefold()} "
    found = []
    for term in COMPRESSION_SALIENCE_TERMS:
        needle = f" {term.casefold()} "
        if needle in lowered or term.casefold() in lowered:
            found.append(term)
    return tuple(found)


def _compress_raw_text(text: str, max_chars: int) -> Tuple[str, Tuple[str, ...]]:
    sentences = _split_sentences(text)
    if not sentences:
        return "", ()
    salient = [sentence for sentence in sentences if _salience_terms(sentence)]
    selected = salient[:4] if salient else list(sentences[:3])
    summary = _truncate_text(" ".join(selected), max_chars)
    return summary, _salience_terms(summary)


def _matched_query_terms(entry: "MemoryEntry", query_terms: Iterable[str]) -> Tuple[str, ...]:
    terms = set(query_terms)
    if not terms:
        return ()
    haystack = set(_tokenize(entry.search_text()))
    return tuple(sorted(terms & haystack))


@dataclass(frozen=True)
class ProvenanceRef:
    ref_id: str
    ref_kind: str
    artifact_path_or_uri: str
    content_hash: str
    excerpt_hash: str = ""
    timestamp: str = ""
    producer: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _require_text(self.ref_id, "ref_id"))
        object.__setattr__(self, "ref_kind", _require_text(self.ref_kind, "ref_kind"))
        object.__setattr__(
            self,
            "artifact_path_or_uri",
            _require_text(self.artifact_path_or_uri, "artifact_path_or_uri"),
        )
        object.__setattr__(self, "content_hash", _require_text(self.content_hash, "content_hash"))
        object.__setattr__(self, "excerpt_hash", _clean_text(self.excerpt_hash))
        object.__setattr__(self, "timestamp", _clean_text(self.timestamp))
        object.__setattr__(self, "producer", _clean_text(self.producer))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "ref_kind": self.ref_kind,
            "artifact_path_or_uri": self.artifact_path_or_uri,
            "content_hash": self.content_hash,
            "excerpt_hash": self.excerpt_hash,
            "timestamp": self.timestamp,
            "producer": self.producer,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceRef":
        return cls(
            ref_id=str(data.get("ref_id", "")),
            ref_kind=str(data.get("ref_kind", "")),
            artifact_path_or_uri=str(data.get("artifact_path_or_uri", "")),
            content_hash=str(data.get("content_hash", "")),
            excerpt_hash=str(data.get("excerpt_hash", "")),
            timestamp=str(data.get("timestamp", "")),
            producer=str(data.get("producer", "")),
        )


@dataclass(frozen=True)
class Staleness:
    state: str = "fresh"
    reasons: Tuple[str, ...] = ()
    invalidators: Tuple[ProvenanceRef, ...] = ()
    checked_at: str = ""

    def __post_init__(self) -> None:
        state = _clean_text(self.state).casefold() or "fresh"
        if state not in STALENESS_STATES:
            raise ValueError(f"staleness state must be one of: {', '.join(STALENESS_STATES)}")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reasons", tuple(_clean_text(item) for item in self.reasons if _clean_text(item)))
        object.__setattr__(
            self,
            "invalidators",
            tuple(item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item) for item in self.invalidators),
        )
        object.__setattr__(self, "checked_at", _clean_text(self.checked_at))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "reasons": list(self.reasons),
            "invalidators": [item.to_dict() for item in self.invalidators],
            "checked_at": self.checked_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Staleness":
        return cls(
            state=str(data.get("state", "fresh")),
            reasons=tuple(data.get("reasons") or ()),
            invalidators=tuple(ProvenanceRef.from_dict(item) for item in data.get("invalidators") or ()),
            checked_at=str(data.get("checked_at", "")),
        )


@dataclass(frozen=True)
class Contradiction:
    state: str = "none"
    contradicting_entry_ids: Tuple[str, ...] = ()
    contradicting_provenance_refs: Tuple[ProvenanceRef, ...] = ()
    resolution: str = ""

    def __post_init__(self) -> None:
        state = _clean_text(self.state).casefold() or "none"
        if state not in CONTRADICTION_STATES:
            raise ValueError(
                f"contradiction state must be one of: {', '.join(CONTRADICTION_STATES)}"
            )
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "contradicting_entry_ids",
            tuple(_clean_text(item) for item in self.contradicting_entry_ids if _clean_text(item)),
        )
        object.__setattr__(
            self,
            "contradicting_provenance_refs",
            tuple(
                item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
                for item in self.contradicting_provenance_refs
            ),
        )
        object.__setattr__(self, "resolution", _clean_text(self.resolution))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "contradicting_entry_ids": list(self.contradicting_entry_ids),
            "contradicting_provenance_refs": [
                item.to_dict() for item in self.contradicting_provenance_refs
            ],
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Contradiction":
        return cls(
            state=str(data.get("state", "none")),
            contradicting_entry_ids=tuple(data.get("contradicting_entry_ids") or ()),
            contradicting_provenance_refs=tuple(
                ProvenanceRef.from_dict(item)
                for item in data.get("contradicting_provenance_refs") or ()
            ),
            resolution=str(data.get("resolution", "")),
        )


@dataclass(frozen=True)
class Revision:
    revision_id: str = "rev-1"
    previous_entry_id: str = ""
    supersedes_entry_ids: Tuple[str, ...] = ()
    tombstoned: bool = False
    tombstone_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _require_text(self.revision_id, "revision_id"))
        object.__setattr__(self, "previous_entry_id", _clean_text(self.previous_entry_id))
        object.__setattr__(
            self,
            "supersedes_entry_ids",
            tuple(_clean_text(item) for item in self.supersedes_entry_ids if _clean_text(item)),
        )
        object.__setattr__(self, "tombstoned", bool(self.tombstoned))
        object.__setattr__(self, "tombstone_reason", _clean_text(self.tombstone_reason))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "previous_entry_id": self.previous_entry_id,
            "supersedes_entry_ids": list(self.supersedes_entry_ids),
            "tombstoned": self.tombstoned,
            "tombstone_reason": self.tombstone_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Revision":
        return cls(
            revision_id=str(data.get("revision_id", "rev-1")),
            previous_entry_id=str(data.get("previous_entry_id", "")),
            supersedes_entry_ids=tuple(data.get("supersedes_entry_ids") or ()),
            tombstoned=bool(data.get("tombstoned", False)),
            tombstone_reason=str(data.get("tombstone_reason", "")),
        )


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source_entry_id: str
    target_entry_id: str
    edge_kind: str
    evidence_refs: Tuple[ProvenanceRef, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _require_text(self.edge_id, "edge_id"))
        object.__setattr__(self, "source_entry_id", _require_text(self.source_entry_id, "source_entry_id"))
        object.__setattr__(self, "target_entry_id", _require_text(self.target_entry_id, "target_entry_id"))
        object.__setattr__(self, "edge_kind", _require_text(self.edge_kind, "edge_kind"))
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(
                item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
                for item in self.evidence_refs
            ),
        )
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_entry_id": self.source_entry_id,
            "target_entry_id": self.target_entry_id,
            "edge_kind": self.edge_kind,
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphEdge":
        return cls(
            edge_id=str(data.get("edge_id", "")),
            source_entry_id=str(data.get("source_entry_id", "")),
            target_entry_id=str(data.get("target_entry_id", "")),
            edge_kind=str(data.get("edge_kind", "")),
            evidence_refs=tuple(ProvenanceRef.from_dict(item) for item in data.get("evidence_refs") or ()),
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    memory_kind: str
    scope: str
    title: str
    summary: str
    applicability: str
    source_refs: Tuple[ProvenanceRef, ...]
    proof_refs: Tuple[ProvenanceRef, ...]
    created_at: str
    last_verified_at: str
    validity: str
    confidence: float
    staleness: Staleness = field(default_factory=Staleness)
    contradiction: Contradiction = field(default_factory=Contradiction)
    revision: Revision = field(default_factory=Revision)
    graph_edges: Tuple[GraphEdge, ...] = ()
    budgets: Mapping[str, int] = field(default_factory=dict)
    schema_version: int = MEMORY_SCHEMA_VERSION
    approved: bool = True
    lifecycle_state: str = "committed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _require_text(self.entry_id, "entry_id"))
        memory_kind = _require_text(self.memory_kind, "memory_kind").casefold().replace("-", "_")
        if memory_kind in RAW_PROVENANCE_KINDS:
            raise ValueError("raw provenance kinds cannot be durable memory entries")
        if memory_kind not in MEMORY_KINDS:
            raise ValueError(f"memory_kind must be one of: {', '.join(MEMORY_KINDS)}")
        object.__setattr__(self, "memory_kind", memory_kind)
        object.__setattr__(self, "scope", _require_text(self.scope, "scope"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "applicability", _clean_text(self.applicability))
        object.__setattr__(
            self,
            "source_refs",
            tuple(
                item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
                for item in self.source_refs
            ),
        )
        object.__setattr__(
            self,
            "proof_refs",
            tuple(
                item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
                for item in self.proof_refs
            ),
        )
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        object.__setattr__(self, "last_verified_at", _clean_text(self.last_verified_at))
        object.__setattr__(self, "validity", _clean_text(self.validity) or "valid")
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))
        staleness = self.staleness if isinstance(self.staleness, Staleness) else Staleness.from_dict(self.staleness)
        contradiction = (
            self.contradiction
            if isinstance(self.contradiction, Contradiction)
            else Contradiction.from_dict(self.contradiction)
        )
        revision = self.revision if isinstance(self.revision, Revision) else Revision.from_dict(self.revision)
        object.__setattr__(self, "staleness", staleness)
        object.__setattr__(self, "contradiction", contradiction)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(
            self,
            "graph_edges",
            tuple(item if isinstance(item, GraphEdge) else GraphEdge.from_dict(item) for item in self.graph_edges),
        )
        object.__setattr__(self, "budgets", dict(self.budgets or {}))
        object.__setattr__(self, "schema_version", int(self.schema_version or MEMORY_SCHEMA_VERSION))
        object.__setattr__(self, "approved", bool(self.approved))
        lifecycle_state = _clean_text(self.lifecycle_state).casefold() or "committed"
        if lifecycle_state not in LIFECYCLE_STATES:
            raise ValueError(f"lifecycle_state must be one of: {', '.join(LIFECYCLE_STATES)}")
        object.__setattr__(self, "lifecycle_state", lifecycle_state)

    def is_recallable(self) -> bool:
        return self.is_committed_approved() and self.has_required_citations()

    def is_committed_approved(self) -> bool:
        return bool(self.approved) and self.lifecycle_state == "committed" and not self.revision.tombstoned

    def has_required_citations(self) -> bool:
        return bool(self.source_refs) and bool(self.proof_refs)

    def search_text(self) -> str:
        return " ".join(
            [
                self.entry_id,
                self.memory_kind,
                self.scope,
                self.title,
                self.summary,
                self.applicability,
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "schema_version": self.schema_version,
            "memory_kind": self.memory_kind,
            "scope": self.scope,
            "title": self.title,
            "summary": self.summary,
            "applicability": self.applicability,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "proof_refs": [item.to_dict() for item in self.proof_refs],
            "created_at": self.created_at,
            "last_verified_at": self.last_verified_at,
            "validity": self.validity,
            "confidence": self.confidence,
            "staleness": self.staleness.to_dict(),
            "contradiction": self.contradiction.to_dict(),
            "revision": self.revision.to_dict(),
            "graph_edges": [item.to_dict() for item in self.graph_edges],
            "budgets": dict(self.budgets),
            "approved": self.approved,
            "lifecycle_state": self.lifecycle_state,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryEntry":
        return cls(
            entry_id=str(data.get("entry_id", "")),
            schema_version=int(data.get("schema_version", MEMORY_SCHEMA_VERSION)),
            memory_kind=str(data.get("memory_kind", "")),
            scope=str(data.get("scope", "")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            applicability=str(data.get("applicability", "")),
            source_refs=tuple(ProvenanceRef.from_dict(item) for item in data.get("source_refs") or ()),
            proof_refs=tuple(ProvenanceRef.from_dict(item) for item in data.get("proof_refs") or ()),
            created_at=str(data.get("created_at", "")),
            last_verified_at=str(data.get("last_verified_at", "")),
            validity=str(data.get("validity", "valid")),
            confidence=float(data.get("confidence", 1.0)),
            staleness=Staleness.from_dict(data.get("staleness") or {}),
            contradiction=Contradiction.from_dict(data.get("contradiction") or {}),
            revision=Revision.from_dict(data.get("revision") or {}),
            graph_edges=tuple(GraphEdge.from_dict(item) for item in data.get("graph_edges") or ()),
            budgets=data.get("budgets") or {},
            approved=bool(data.get("approved", True)),
            lifecycle_state=str(data.get("lifecycle_state", "committed")),
        )


@dataclass(frozen=True)
class MemoryRecallBudget:
    max_results: int = 5
    max_chars: int = 4000

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_results", max(0, int(self.max_results or 0)))
        object.__setattr__(self, "max_chars", max(0, int(self.max_chars or 0)))

    def to_dict(self) -> Dict[str, Any]:
        return {"max_results": self.max_results, "max_chars": self.max_chars}


@dataclass(frozen=True)
class MemoryRecallRequest:
    query: str
    scope: str = ""
    memory_kinds: Tuple[str, ...] = ()
    evidence_filters: Mapping[str, str] = field(default_factory=dict)
    current_context_refs: Tuple[ProvenanceRef, ...] = ()
    limit: int = 5
    include_stale: bool = False
    chain_request: Mapping[str, Any] = field(default_factory=dict)
    budget: MemoryRecallBudget = field(default_factory=MemoryRecallBudget)

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _clean_text(self.query))
        object.__setattr__(self, "scope", _clean_text(self.scope))
        object.__setattr__(
            self,
            "memory_kinds",
            tuple(_clean_text(item).casefold().replace("-", "_") for item in self.memory_kinds if _clean_text(item)),
        )
        object.__setattr__(self, "evidence_filters", dict(self.evidence_filters or {}))
        object.__setattr__(
            self,
            "current_context_refs",
            tuple(
                item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
                for item in self.current_context_refs
            ),
        )
        object.__setattr__(self, "limit", max(0, int(self.limit or 0)))
        object.__setattr__(self, "include_stale", bool(self.include_stale))
        object.__setattr__(self, "chain_request", dict(self.chain_request or {}))
        budget = self.budget if isinstance(self.budget, MemoryRecallBudget) else MemoryRecallBudget(**self.budget)
        object.__setattr__(self, "budget", budget)

    def effective_limit(self) -> int:
        limits = [value for value in (self.limit, self.budget.max_results) if value > 0]
        return min(limits) if limits else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope,
            "memory_kinds": list(self.memory_kinds),
            "evidence_filters": dict(self.evidence_filters),
            "current_context_refs": [item.to_dict() for item in self.current_context_refs],
            "limit": self.limit,
            "include_stale": self.include_stale,
            "chain_request": dict(self.chain_request),
            "budget": self.budget.to_dict(),
        }


@dataclass(frozen=True)
class BudgetUse:
    returned_results: int = 0
    returned_chars: int = 0
    store_reads: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "returned_results": self.returned_results,
            "returned_chars": self.returned_chars,
            "store_reads": self.store_reads,
        }


@dataclass(frozen=True)
class MemoryRecallCandidate:
    entry_id: str
    memory_kind: str
    scope: str
    title: str
    summary: str
    why_relevant: str
    evidence_refs: Tuple[ProvenanceRef, ...]
    proof_refs: Tuple[ProvenanceRef, ...]
    validity: str
    confidence: float
    staleness: Staleness
    contradiction: Contradiction
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "memory_kind": self.memory_kind,
            "scope": self.scope,
            "title": self.title,
            "summary": self.summary,
            "why_relevant": self.why_relevant,
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "proof_refs": [item.to_dict() for item in self.proof_refs],
            "validity": self.validity,
            "confidence": self.confidence,
            "staleness": self.staleness.to_dict(),
            "contradiction": self.contradiction.to_dict(),
            "score": self.score,
        }


@dataclass(frozen=True)
class MemoryTrace:
    trace_ref: str
    event: str
    request_hash: str
    result_hash: str
    store_id: str
    index_id: str
    timing_ms: float
    budget_used: BudgetUse
    dropped_reasons: Mapping[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_ref": self.trace_ref,
            "event": self.event,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "store_id": self.store_id,
            "index_id": self.index_id,
            "timing_ms": self.timing_ms,
            "budget_used": self.budget_used.to_dict(),
            "dropped_reasons": dict(self.dropped_reasons),
        }


@dataclass(frozen=True)
class MemoryRecallResult:
    candidates: Tuple[MemoryRecallCandidate, ...]
    chains: Tuple[Any, ...]
    dropped: Mapping[str, int]
    trace_ref: str
    timing_ms: float
    budget_used: BudgetUse
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "chains": list(self.chains),
            "dropped": dict(self.dropped),
            "trace_ref": self.trace_ref,
            "timing_ms": self.timing_ms,
            "budget_used": self.budget_used.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryInspectRequest:
    entry_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"entry_id": self.entry_id}


@dataclass(frozen=True)
class MemoryInspectResult:
    entry: Optional[MemoryEntry]
    dropped: Mapping[str, int]
    trace_ref: str
    timing_ms: float
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.to_dict() if self.entry else None,
            "dropped": dict(self.dropped),
            "trace_ref": self.trace_ref,
            "timing_ms": self.timing_ms,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryCandidateRequest:
    memory_kind: str
    scope: str
    title: str
    summary: str
    applicability: str
    source_refs: Tuple[ProvenanceRef, ...]
    created_at: str
    validity: str = "valid"
    confidence: float = 0.5
    staleness: Staleness = field(default_factory=Staleness)
    contradiction: Contradiction = field(default_factory=Contradiction)
    graph_edges: Tuple[GraphEdge, ...] = ()
    budgets: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        memory_kind = _require_text(self.memory_kind, "memory_kind").casefold().replace("-", "_")
        if memory_kind in RAW_PROVENANCE_KINDS:
            raise ValueError("raw provenance kinds cannot be memory candidates")
        if memory_kind not in MEMORY_KINDS:
            raise ValueError(f"memory_kind must be one of: {', '.join(MEMORY_KINDS)}")
        object.__setattr__(self, "memory_kind", memory_kind)
        object.__setattr__(self, "scope", _require_text(self.scope, "scope"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "applicability", _clean_text(self.applicability))
        source_refs = tuple(
            item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
            for item in self.source_refs
        )
        if not source_refs:
            raise ValueError("memory candidates require source_refs")
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        object.__setattr__(self, "validity", _clean_text(self.validity) or "valid")
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))
        staleness = self.staleness if isinstance(self.staleness, Staleness) else Staleness.from_dict(self.staleness)
        contradiction = (
            self.contradiction
            if isinstance(self.contradiction, Contradiction)
            else Contradiction.from_dict(self.contradiction)
        )
        object.__setattr__(self, "staleness", staleness)
        object.__setattr__(self, "contradiction", contradiction)
        object.__setattr__(
            self,
            "graph_edges",
            tuple(item if isinstance(item, GraphEdge) else GraphEdge.from_dict(item) for item in self.graph_edges),
        )
        object.__setattr__(self, "budgets", dict(self.budgets or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_kind": self.memory_kind,
            "scope": self.scope,
            "title": self.title,
            "summary": self.summary,
            "applicability": self.applicability,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "created_at": self.created_at,
            "validity": self.validity,
            "confidence": self.confidence,
            "staleness": self.staleness.to_dict(),
            "contradiction": self.contradiction.to_dict(),
            "graph_edges": [item.to_dict() for item in self.graph_edges],
            "budgets": dict(self.budgets),
        }


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    request_hash: str
    entry_shape: MemoryCandidateRequest
    state: str = "candidate"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "request_hash": self.request_hash,
            "entry_shape": self.entry_shape.to_dict(),
            "state": self.state,
        }


@dataclass(frozen=True)
class MemoryCandidateResult:
    candidate: MemoryCandidate
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryCompressionRequest:
    raw_text: str
    memory_kind: str
    scope: str
    source_refs: Tuple[ProvenanceRef, ...]
    created_at: str
    title_hint: str = ""
    applicability_hint: str = ""
    validity: str = "valid"
    confidence: float = 0.5
    max_summary_chars: int = 600
    merge_similarity_threshold: float = 0.72

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_text", _require_text(self.raw_text, "raw_text"))
        memory_kind = _require_text(self.memory_kind, "memory_kind").casefold().replace("-", "_")
        if memory_kind in RAW_PROVENANCE_KINDS:
            raise ValueError("raw provenance kinds cannot be memory compression targets")
        if memory_kind not in MEMORY_KINDS:
            raise ValueError(f"memory_kind must be one of: {', '.join(MEMORY_KINDS)}")
        object.__setattr__(self, "memory_kind", memory_kind)
        object.__setattr__(self, "scope", _require_text(self.scope, "scope"))
        source_refs = tuple(
            item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
            for item in self.source_refs
        )
        if not source_refs:
            raise ValueError("memory compression requires source_refs")
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        object.__setattr__(self, "title_hint", _clean_text(self.title_hint))
        object.__setattr__(self, "applicability_hint", _clean_text(self.applicability_hint))
        object.__setattr__(self, "validity", _clean_text(self.validity) or "valid")
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))
        object.__setattr__(self, "max_summary_chars", max(80, int(self.max_summary_chars or 0)))
        object.__setattr__(
            self,
            "merge_similarity_threshold",
            max(0.0, min(1.0, float(self.merge_similarity_threshold))),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text_hash": _stable_json_hash({"raw_text": self.raw_text}),
            "raw_text_chars": len(self.raw_text),
            "memory_kind": self.memory_kind,
            "scope": self.scope,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "created_at": self.created_at,
            "title_hint": self.title_hint,
            "applicability_hint": self.applicability_hint,
            "validity": self.validity,
            "confidence": self.confidence,
            "max_summary_chars": self.max_summary_chars,
            "merge_similarity_threshold": self.merge_similarity_threshold,
        }


@dataclass(frozen=True)
class MemoryCompressionResult:
    action: str
    summary: str
    title: str
    salience_terms: Tuple[str, ...]
    novelty_score: float
    merge_target_entry_id: str
    candidate: Optional[MemoryCandidate]
    dropped: Mapping[str, int]
    trace_ref: str
    trace: MemoryTrace

    def __post_init__(self) -> None:
        action = _require_text(self.action, "action")
        if action not in COMPRESSION_ACTIONS:
            raise ValueError(f"compression action must be one of: {', '.join(COMPRESSION_ACTIONS)}")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "summary", _clean_text(self.summary))
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "salience_terms", tuple(_clean_text(item) for item in self.salience_terms if _clean_text(item)))
        object.__setattr__(self, "novelty_score", max(0.0, min(1.0, float(self.novelty_score))))
        object.__setattr__(self, "merge_target_entry_id", _clean_text(self.merge_target_entry_id))
        object.__setattr__(self, "dropped", dict(self.dropped or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "summary": self.summary,
            "title": self.title,
            "salience_terms": list(self.salience_terms),
            "novelty_score": self.novelty_score,
            "merge_target_entry_id": self.merge_target_entry_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "dropped": dict(self.dropped),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryProposalRequest:
    candidate_id: str
    proof_refs: Tuple[ProvenanceRef, ...]
    proposed_at: str
    proposal_id: str = ""
    last_verified_at: str = ""
    previous_entry_id: str = ""
    supersedes_entry_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _require_text(self.candidate_id, "candidate_id"))
        proof_refs = tuple(
            item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
            for item in self.proof_refs
        )
        if not proof_refs:
            raise ValueError("memory proposals require proof_refs")
        object.__setattr__(self, "proof_refs", proof_refs)
        object.__setattr__(self, "proposed_at", _require_text(self.proposed_at, "proposed_at"))
        object.__setattr__(self, "proposal_id", _clean_text(self.proposal_id))
        object.__setattr__(self, "last_verified_at", _clean_text(self.last_verified_at))
        object.__setattr__(self, "previous_entry_id", _clean_text(self.previous_entry_id))
        object.__setattr__(
            self,
            "supersedes_entry_ids",
            tuple(_clean_text(item) for item in self.supersedes_entry_ids if _clean_text(item)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "proof_refs": [item.to_dict() for item in self.proof_refs],
            "proposed_at": self.proposed_at,
            "proposal_id": self.proposal_id,
            "last_verified_at": self.last_verified_at,
            "previous_entry_id": self.previous_entry_id,
            "supersedes_entry_ids": list(self.supersedes_entry_ids),
        }


@dataclass(frozen=True)
class MemoryProposal:
    proposal_id: str
    candidate: MemoryCandidate
    proof_refs: Tuple[ProvenanceRef, ...]
    proposed_at: str
    last_verified_at: str = ""
    previous_entry_id: str = ""
    supersedes_entry_ids: Tuple[str, ...] = ()
    state: str = "proposal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "candidate": self.candidate.to_dict(),
            "proof_refs": [item.to_dict() for item in self.proof_refs],
            "proposed_at": self.proposed_at,
            "last_verified_at": self.last_verified_at,
            "previous_entry_id": self.previous_entry_id,
            "supersedes_entry_ids": list(self.supersedes_entry_ids),
            "state": self.state,
        }


@dataclass(frozen=True)
class MemoryProposalResult:
    proposal: MemoryProposal
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryApprovalRequest:
    proposal_id: str
    approved_by: str
    approval_refs: Tuple[ProvenanceRef, ...]
    approved_at: str
    reason: str = ""
    approval_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _require_text(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "approved_by", _require_text(self.approved_by, "approved_by"))
        approval_refs = tuple(
            item if isinstance(item, ProvenanceRef) else ProvenanceRef.from_dict(item)
            for item in self.approval_refs
        )
        if not approval_refs:
            raise ValueError("memory approvals require approval_refs")
        object.__setattr__(self, "approval_refs", approval_refs)
        object.__setattr__(self, "approved_at", _require_text(self.approved_at, "approved_at"))
        object.__setattr__(self, "reason", _clean_text(self.reason))
        object.__setattr__(self, "approval_id", _clean_text(self.approval_id))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "approved_by": self.approved_by,
            "approval_refs": [item.to_dict() for item in self.approval_refs],
            "approved_at": self.approved_at,
            "reason": self.reason,
            "approval_id": self.approval_id,
        }


@dataclass(frozen=True)
class MemoryApproval:
    approval_id: str
    proposal_id: str
    approved_by: str
    approval_refs: Tuple[ProvenanceRef, ...]
    approved_at: str
    reason: str = ""
    state: str = "approved"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "approved_by": self.approved_by,
            "approval_refs": [item.to_dict() for item in self.approval_refs],
            "approved_at": self.approved_at,
            "reason": self.reason,
            "state": self.state,
        }


@dataclass(frozen=True)
class MemoryApprovalResult:
    approval: MemoryApproval
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval": self.approval.to_dict(),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryCommitRequest:
    proposal_id: str
    approval_id: str
    entry_id: str = ""
    revision_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _require_text(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "approval_id", _require_text(self.approval_id, "approval_id"))
        object.__setattr__(self, "entry_id", _clean_text(self.entry_id))
        object.__setattr__(self, "revision_id", _clean_text(self.revision_id))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "approval_id": self.approval_id,
            "entry_id": self.entry_id,
            "revision_id": self.revision_id,
        }


@dataclass(frozen=True)
class MemoryCommitResult:
    entry: MemoryEntry
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryTombstoneRequest:
    entry_id: str
    reason: str
    tombstone_ref: ProvenanceRef
    revision_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _require_text(self.entry_id, "entry_id"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))
        ref = self.tombstone_ref
        object.__setattr__(
            self,
            "tombstone_ref",
            ref if isinstance(ref, ProvenanceRef) else ProvenanceRef.from_dict(ref),
        )
        object.__setattr__(self, "revision_id", _clean_text(self.revision_id))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "reason": self.reason,
            "tombstone_ref": self.tombstone_ref.to_dict(),
            "revision_id": self.revision_id,
        }


@dataclass(frozen=True)
class MemoryTombstoneResult:
    entry: MemoryEntry
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryAdaptRecallRequest:
    recall_result: MemoryRecallResult
    min_confidence: float = 0.0
    allowed_kinds: Tuple[str, ...] = ()
    include_stale: bool = False
    limit: int = 0
    budget: MemoryRecallBudget = field(default_factory=MemoryRecallBudget)

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_confidence", max(0.0, min(1.0, float(self.min_confidence))))
        object.__setattr__(
            self,
            "allowed_kinds",
            tuple(_clean_text(item).casefold().replace("-", "_") for item in self.allowed_kinds if _clean_text(item)),
        )
        object.__setattr__(self, "include_stale", bool(self.include_stale))
        object.__setattr__(self, "limit", max(0, int(self.limit or 0)))
        budget = self.budget if isinstance(self.budget, MemoryRecallBudget) else MemoryRecallBudget(**self.budget)
        object.__setattr__(self, "budget", budget)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recall_trace_ref": self.recall_result.trace_ref,
            "min_confidence": self.min_confidence,
            "allowed_kinds": list(self.allowed_kinds),
            "include_stale": self.include_stale,
            "limit": self.limit,
            "budget": self.budget.to_dict(),
        }


@dataclass(frozen=True)
class MemoryAdaptRecallResult:
    candidates: Tuple[MemoryRecallCandidate, ...]
    dropped: Mapping[str, int]
    trace_ref: str
    timing_ms: float
    budget_used: BudgetUse
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "dropped": dict(self.dropped),
            "trace_ref": self.trace_ref,
            "timing_ms": self.timing_ms,
            "budget_used": self.budget_used.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryChainRequest:
    start_entry_ids: Tuple[str, ...]
    max_depth: int = 1
    max_fanout: int = 5
    max_nodes: int = 20
    max_chars: int = 4000
    edge_kinds: Tuple[str, ...] = ()
    include_stale: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "start_entry_ids",
            tuple(_clean_text(item) for item in self.start_entry_ids if _clean_text(item)),
        )
        object.__setattr__(self, "max_depth", max(0, int(self.max_depth or 0)))
        object.__setattr__(self, "max_fanout", max(0, int(self.max_fanout or 0)))
        object.__setattr__(self, "max_nodes", max(0, int(self.max_nodes or 0)))
        object.__setattr__(self, "max_chars", max(0, int(self.max_chars or 0)))
        object.__setattr__(
            self,
            "edge_kinds",
            tuple(_clean_text(item) for item in self.edge_kinds if _clean_text(item)),
        )
        object.__setattr__(self, "include_stale", bool(self.include_stale))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_entry_ids": list(self.start_entry_ids),
            "max_depth": self.max_depth,
            "max_fanout": self.max_fanout,
            "max_nodes": self.max_nodes,
            "max_chars": self.max_chars,
            "edge_kinds": list(self.edge_kinds),
            "include_stale": self.include_stale,
        }


@dataclass(frozen=True)
class MemoryChainNode:
    entry_id: str
    memory_kind: str
    scope: str
    title: str
    summary: str
    evidence_refs: Tuple[ProvenanceRef, ...]
    proof_refs: Tuple[ProvenanceRef, ...]
    staleness: Staleness
    contradiction: Contradiction
    depth: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "memory_kind": self.memory_kind,
            "scope": self.scope,
            "title": self.title,
            "summary": self.summary,
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "proof_refs": [item.to_dict() for item in self.proof_refs],
            "staleness": self.staleness.to_dict(),
            "contradiction": self.contradiction.to_dict(),
            "depth": self.depth,
        }


@dataclass(frozen=True)
class MemoryChainResult:
    nodes: Tuple[MemoryChainNode, ...]
    edges: Tuple[GraphEdge, ...]
    dropped: Mapping[str, int]
    trace_ref: str
    timing_ms: float
    budget_used: BudgetUse
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "dropped": dict(self.dropped),
            "trace_ref": self.trace_ref,
            "timing_ms": self.timing_ms,
            "budget_used": self.budget_used.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class MemoryProjectRequest:
    purpose: str = "future_prompt_projection"

    def to_dict(self) -> Dict[str, Any]:
        return {"purpose": _clean_text(self.purpose)}


@dataclass(frozen=True)
class MemoryProjectResult:
    enabled: bool
    deferred_reason: str
    trace_ref: str
    trace: MemoryTrace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "deferred_reason": self.deferred_reason,
            "trace_ref": self.trace_ref,
            "trace": self.trace.to_dict(),
        }


class MemoryReadStore:
    store_id = "memory-read-store"
    index_id = "memory-read-index"

    def iter_entries(self) -> Iterable[MemoryEntry]:
        raise NotImplementedError

    def get_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        wanted = _clean_text(entry_id)
        if not wanted:
            return None
        for entry in self.iter_entries():
            if entry.entry_id == wanted:
                return entry
        return None

    def commit_entry(self, entry: MemoryEntry) -> MemoryEntry:
        raise NotImplementedError("memory store is read-only")

    def replace_entry(self, entry: MemoryEntry) -> MemoryEntry:
        raise NotImplementedError("memory store is read-only")


class InMemoryMemoryStore(MemoryReadStore):
    def __init__(
        self,
        entries: Sequence[MemoryEntry] = (),
        *,
        store_id: str = "memory:in-memory",
        index_id: str = "memory:index:in-memory",
    ) -> None:
        self._entries = list(entries)
        self.store_id = store_id
        self.index_id = index_id

    def iter_entries(self) -> Iterable[MemoryEntry]:
        return iter(tuple(self._entries))

    def commit_entry(self, entry: MemoryEntry) -> MemoryEntry:
        if self.get_entry(entry.entry_id):
            raise ValueError(f"memory entry already exists: {entry.entry_id}")
        self._entries.append(entry)
        return entry

    def replace_entry(self, entry: MemoryEntry) -> MemoryEntry:
        for index, existing in enumerate(self._entries):
            if existing.entry_id == entry.entry_id:
                self._entries[index] = entry
                return entry
        raise ValueError(f"memory entry not found: {entry.entry_id}")


class JsonFileMemoryStore(MemoryReadStore):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.store_id = f"memory:json:{self.path}"
        self.index_id = f"memory:index:json:{self._content_hash()[:16]}"

    def _content_hash(self) -> str:
        if not self.path.exists():
            return "missing"
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def iter_entries(self) -> Iterable[MemoryEntry]:
        if not self.path.exists():
            return iter(())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        raw_entries = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(raw_entries, list):
            return iter(())
        return iter(MemoryEntry.from_dict(item) for item in raw_entries if isinstance(item, dict))


class MemorySystem:
    def __init__(self, store: Optional[MemoryReadStore] = None) -> None:
        self.store = store or InMemoryMemoryStore()
        self.traces: List[MemoryTrace] = []
        self.candidates: Dict[str, MemoryCandidate] = {}
        self.proposals: Dict[str, MemoryProposal] = {}
        self.approvals: Dict[str, MemoryApproval] = {}
        self.committed_proposals: Dict[str, str] = {}

    @classmethod
    def from_entries(cls, entries: Sequence[MemoryEntry]) -> "MemorySystem":
        return cls(InMemoryMemoryStore(entries))

    def compress_memory(self, request: MemoryCompressionRequest) -> MemoryCompressionResult:
        """Turn raw provenance text into a compact candidate or merge hint.

        This is the hippocampal-MVP write entrance: keep the compressed memory
        data small, keep raw data in provenance refs, and avoid creating a new
        durable item when a near-duplicate committed memory already exists.
        """
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        summary, salience_terms = _compress_raw_text(request.raw_text, request.max_summary_chars)
        dropped: Dict[str, int] = {}
        candidate: Optional[MemoryCandidate] = None
        merge_target_entry_id = ""
        action = "candidate"
        title = self._compression_title(request, summary)
        novelty_score = 1.0

        if not summary:
            action = "drop"
            dropped["empty_compressed_summary"] = 1
        else:
            match, similarity = self._best_compression_match(
                summary=summary,
                memory_kind=request.memory_kind,
                scope=request.scope,
            )
            novelty_score = round(1.0 - similarity, 6)
            if match is not None and similarity >= request.merge_similarity_threshold:
                action = "merge_existing"
                merge_target_entry_id = match.entry_id
                dropped["similar_existing_memory"] = 1
            else:
                candidate = self.write_candidate(
                    MemoryCandidateRequest(
                        memory_kind=request.memory_kind,
                        scope=request.scope,
                        title=title,
                        summary=summary,
                        applicability=self._compression_applicability(request, salience_terms),
                        source_refs=request.source_refs,
                        created_at=request.created_at,
                        validity=request.validity,
                        confidence=request.confidence,
                        budgets={"max_summary_chars": request.max_summary_chars},
                    )
                ).candidate

        result_payload = {
            "action": action,
            "summary": summary,
            "title": title,
            "salience_terms": list(salience_terms),
            "novelty_score": novelty_score,
            "merge_target_entry_id": merge_target_entry_id,
            "candidate_id": candidate.candidate_id if candidate else "",
            "dropped": dropped,
        }
        trace = self.trace(
            event="compress_memory",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(
                returned_results=1 if candidate or merge_target_entry_id else 0,
                returned_chars=len(summary),
                store_reads=sum(1 for _ in self.store.iter_entries()),
            ),
            dropped_reasons=dropped,
        )
        return MemoryCompressionResult(
            action=action,
            summary=summary,
            title=title,
            salience_terms=salience_terms,
            novelty_score=novelty_score,
            merge_target_entry_id=merge_target_entry_id,
            candidate=candidate,
            dropped=dropped,
            trace_ref=trace.trace_ref,
            trace=trace,
        )

    def write_candidate(self, request: MemoryCandidateRequest) -> MemoryCandidateResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        candidate_id = _stable_id("candidate", request.to_dict())
        candidate = MemoryCandidate(
            candidate_id=candidate_id,
            request_hash=request_hash,
            entry_shape=request,
        )
        self.candidates[candidate_id] = candidate
        result_payload = {"candidate": candidate.to_dict()}
        trace = self.trace(
            event="write_candidate",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(returned_results=1),
            dropped_reasons={},
        )
        return MemoryCandidateResult(candidate=candidate, trace_ref=trace.trace_ref, trace=trace)

    def propose_memory(self, request: MemoryProposalRequest) -> MemoryProposalResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        candidate = self.candidates.get(request.candidate_id)
        if not candidate:
            raise ValueError(f"memory candidate not found: {request.candidate_id}")
        proposal_id = request.proposal_id or _stable_id("proposal", request.to_dict())
        proposal = MemoryProposal(
            proposal_id=proposal_id,
            candidate=candidate,
            proof_refs=request.proof_refs,
            proposed_at=request.proposed_at,
            last_verified_at=request.last_verified_at,
            previous_entry_id=request.previous_entry_id,
            supersedes_entry_ids=request.supersedes_entry_ids,
        )
        self.proposals[proposal_id] = proposal
        result_payload = {"proposal": proposal.to_dict()}
        trace = self.trace(
            event="propose_memory",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(returned_results=1),
            dropped_reasons={},
        )
        return MemoryProposalResult(proposal=proposal, trace_ref=trace.trace_ref, trace=trace)

    def approve(self, request: MemoryApprovalRequest) -> MemoryApprovalResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        if request.proposal_id not in self.proposals:
            raise ValueError(f"memory proposal not found: {request.proposal_id}")
        approval_id = request.approval_id or _stable_id("approval", request.to_dict())
        approval = MemoryApproval(
            approval_id=approval_id,
            proposal_id=request.proposal_id,
            approved_by=request.approved_by,
            approval_refs=request.approval_refs,
            approved_at=request.approved_at,
            reason=request.reason,
        )
        self.approvals[approval_id] = approval
        result_payload = {"approval": approval.to_dict()}
        trace = self.trace(
            event="approve",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(returned_results=1),
            dropped_reasons={},
        )
        return MemoryApprovalResult(approval=approval, trace_ref=trace.trace_ref, trace=trace)

    def commit_memory(self, request: MemoryCommitRequest) -> MemoryCommitResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        proposal = self.proposals.get(request.proposal_id)
        if not proposal:
            raise ValueError(f"memory proposal not found: {request.proposal_id}")
        if proposal.proposal_id in self.committed_proposals:
            raise ValueError(
                "memory proposal is already committed: "
                f"{proposal.proposal_id} -> {self.committed_proposals[proposal.proposal_id]}"
            )
        approval = self.approvals.get(request.approval_id)
        if not approval or approval.proposal_id != proposal.proposal_id:
            raise ValueError("commit_memory requires an approval for the proposal")
        shape = proposal.candidate.entry_shape
        approval_refs = tuple(approval.approval_refs)
        proof_refs = proposal.proof_refs + tuple(
            ref for ref in approval_refs if ref.ref_id not in {item.ref_id for item in proposal.proof_refs}
        )
        entry_id = request.entry_id or _stable_id(
            "entry",
            {
                "proposal_id": proposal.proposal_id,
                "approval_id": approval.approval_id,
                "title": shape.title,
            },
        )
        revision_id = request.revision_id or _stable_id("rev", request.to_dict())
        entry = MemoryEntry(
            entry_id=entry_id,
            memory_kind=shape.memory_kind,
            scope=shape.scope,
            title=shape.title,
            summary=shape.summary,
            applicability=shape.applicability,
            source_refs=shape.source_refs,
            proof_refs=proof_refs,
            created_at=shape.created_at,
            last_verified_at=proposal.last_verified_at or approval.approved_at,
            validity=shape.validity,
            confidence=shape.confidence,
            staleness=shape.staleness,
            contradiction=shape.contradiction,
            revision=Revision(
                revision_id=revision_id,
                previous_entry_id=proposal.previous_entry_id,
                supersedes_entry_ids=proposal.supersedes_entry_ids,
            ),
            graph_edges=shape.graph_edges,
            budgets=shape.budgets,
            approved=True,
            lifecycle_state="committed",
        )
        committed = self.store.commit_entry(entry)
        self.committed_proposals[proposal.proposal_id] = committed.entry_id
        result_payload = {"entry": committed.to_dict()}
        trace = self.trace(
            event="commit_memory",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(returned_results=1, returned_chars=len(committed.summary)),
            dropped_reasons={},
        )
        return MemoryCommitResult(entry=committed, trace_ref=trace.trace_ref, trace=trace)

    def tombstone_entry(self, request: MemoryTombstoneRequest) -> MemoryTombstoneResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        entry = self.store.get_entry(request.entry_id)
        if not entry:
            raise ValueError(f"memory entry not found: {request.entry_id}")
        revision = Revision(
            revision_id=request.revision_id or _stable_id("tombstone", request.to_dict()),
            previous_entry_id=entry.revision.revision_id,
            supersedes_entry_ids=(entry.entry_id,),
            tombstoned=True,
            tombstone_reason=request.reason,
        )
        tombstoned = replace(
            entry,
            proof_refs=entry.proof_refs + (request.tombstone_ref,),
            revision=revision,
            lifecycle_state="tombstoned",
        )
        replaced = self.store.replace_entry(tombstoned)
        result_payload = {"entry": replaced.to_dict()}
        trace = self.trace(
            event="tombstone_entry",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(returned_results=1, returned_chars=len(replaced.summary)),
            dropped_reasons={},
        )
        return MemoryTombstoneResult(entry=replaced, trace_ref=trace.trace_ref, trace=trace)

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        dropped: Dict[str, int] = {}
        store_reads = 0
        scored: List[MemoryRecallCandidate] = []
        query_terms = set(_tokenize(request.query))
        limit = request.effective_limit()

        for entry in self.store.iter_entries():
            store_reads += 1
            drop_reason = self._recall_drop_reason(entry, request)
            if drop_reason:
                dropped[drop_reason] = dropped.get(drop_reason, 0) + 1
                continue
            score = self._score_entry(entry, query_terms)
            if query_terms and score <= 0.0:
                dropped["query_mismatch"] = dropped.get("query_mismatch", 0) + 1
                continue
            scored.append(self._candidate_from_entry(entry, score, query_terms))

        scored.sort(key=lambda item: (item.score, item.confidence, item.entry_id), reverse=True)
        candidates: List[MemoryRecallCandidate] = []
        returned_chars = 0
        for candidate in scored:
            if len(candidates) >= limit:
                dropped["budget_result_limit"] = dropped.get("budget_result_limit", 0) + 1
                continue
            candidate_chars = len(candidate.title) + len(candidate.summary) + len(candidate.why_relevant)
            if request.budget.max_chars and returned_chars + candidate_chars > request.budget.max_chars:
                dropped["budget_char_limit"] = dropped.get("budget_char_limit", 0) + 1
                continue
            candidates.append(candidate)
            returned_chars += candidate_chars

        timing_ms = (time.perf_counter() - started) * 1000.0
        budget_used = BudgetUse(
            returned_results=len(candidates),
            returned_chars=returned_chars,
            store_reads=store_reads,
        )
        result_payload = {
            "candidates": [item.to_dict() for item in candidates],
            "chains": [],
            "dropped": dict(dropped),
            "timing_ms": round(timing_ms, 3),
            "budget_used": budget_used.to_dict(),
        }
        trace = self.trace(
            event="recall",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=timing_ms,
            budget_used=budget_used,
            dropped_reasons=dropped,
        )
        return MemoryRecallResult(
            candidates=tuple(candidates),
            chains=(),
            dropped=dropped,
            trace_ref=trace.trace_ref,
            timing_ms=timing_ms,
            budget_used=budget_used,
            trace=trace,
        )

    def adapt_recall(self, request: MemoryAdaptRecallRequest) -> MemoryAdaptRecallResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        dropped: Dict[str, int] = {}
        kept: List[MemoryRecallCandidate] = []
        limit = request.limit or request.budget.max_results
        returned_chars = 0

        for candidate in request.recall_result.candidates:
            if request.allowed_kinds and candidate.memory_kind not in request.allowed_kinds:
                dropped["memory_kind_mismatch"] = dropped.get("memory_kind_mismatch", 0) + 1
                continue
            if candidate.confidence < request.min_confidence:
                dropped["low_confidence"] = dropped.get("low_confidence", 0) + 1
                continue
            if not request.include_stale and candidate.staleness.state in {"stale", "superseded"}:
                dropped["stale_excluded"] = dropped.get("stale_excluded", 0) + 1
                continue
            candidate_chars = len(candidate.title) + len(candidate.summary) + len(candidate.why_relevant)
            if limit and len(kept) >= limit:
                dropped["budget_result_limit"] = dropped.get("budget_result_limit", 0) + 1
                continue
            if request.budget.max_chars and returned_chars + candidate_chars > request.budget.max_chars:
                dropped["budget_char_limit"] = dropped.get("budget_char_limit", 0) + 1
                continue
            kept.append(candidate)
            returned_chars += candidate_chars

        kept.sort(key=lambda item: (item.score, item.confidence, item.entry_id), reverse=True)
        timing_ms = (time.perf_counter() - started) * 1000.0
        budget_used = BudgetUse(returned_results=len(kept), returned_chars=returned_chars)
        result_payload = {
            "candidates": [item.to_dict() for item in kept],
            "dropped": dropped,
            "timing_ms": round(timing_ms, 3),
            "budget_used": budget_used.to_dict(),
        }
        trace = self.trace(
            event="adapt_recall",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=timing_ms,
            budget_used=budget_used,
            dropped_reasons=dropped,
        )
        return MemoryAdaptRecallResult(
            candidates=tuple(kept),
            dropped=dropped,
            trace_ref=trace.trace_ref,
            timing_ms=timing_ms,
            budget_used=budget_used,
            trace=trace,
        )

    def expand_chain(self, request: MemoryChainRequest) -> MemoryChainResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        entries = {entry.entry_id: entry for entry in self.store.iter_entries()}
        dropped: Dict[str, int] = {}
        nodes: List[MemoryChainNode] = []
        edges: List[GraphEdge] = []
        queue: List[Tuple[str, int, Optional[GraphEdge]]] = [
            (entry_id, 0, None) for entry_id in request.start_entry_ids
        ]
        visited = set()
        returned_chars = 0

        while queue:
            entry_id, depth, incoming_edge = queue.pop(0)
            if entry_id in visited:
                dropped["duplicate_node"] = dropped.get("duplicate_node", 0) + 1
                continue
            if len(nodes) >= request.max_nodes:
                dropped["budget_node_limit"] = dropped.get("budget_node_limit", 0) + 1
                continue
            entry = entries.get(entry_id)
            if not entry:
                dropped["missing_entry"] = dropped.get("missing_entry", 0) + 1
                continue
            drop_reason = self._recall_drop_reason(
                entry,
                MemoryRecallRequest(query="", include_stale=request.include_stale),
            )
            if drop_reason:
                dropped[drop_reason] = dropped.get(drop_reason, 0) + 1
                continue
            node_chars = len(entry.title) + len(entry.summary)
            if returned_chars + node_chars > request.max_chars:
                dropped["budget_char_limit"] = dropped.get("budget_char_limit", 0) + 1
                continue

            visited.add(entry_id)
            returned_chars += node_chars
            nodes.append(self._chain_node_from_entry(entry, depth))
            if incoming_edge is not None:
                edges.append(incoming_edge)
            if depth >= request.max_depth:
                continue

            fanout = 0
            for edge in entry.graph_edges:
                if request.edge_kinds and edge.edge_kind not in request.edge_kinds:
                    dropped["edge_kind_filtered"] = dropped.get("edge_kind_filtered", 0) + 1
                    continue
                if fanout >= request.max_fanout:
                    dropped["budget_fanout_limit"] = dropped.get("budget_fanout_limit", 0) + 1
                    continue
                fanout += 1
                queue.append((edge.target_entry_id, depth + 1, edge))

        timing_ms = (time.perf_counter() - started) * 1000.0
        budget_used = BudgetUse(
            returned_results=len(nodes),
            returned_chars=returned_chars,
            store_reads=len(entries),
        )
        result_payload = {
            "nodes": [item.to_dict() for item in nodes],
            "edges": [item.to_dict() for item in edges],
            "dropped": dropped,
            "timing_ms": round(timing_ms, 3),
            "budget_used": budget_used.to_dict(),
        }
        trace = self.trace(
            event="expand_chain",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=timing_ms,
            budget_used=budget_used,
            dropped_reasons=dropped,
        )
        return MemoryChainResult(
            nodes=tuple(nodes),
            edges=tuple(edges),
            dropped=dropped,
            trace_ref=trace.trace_ref,
            timing_ms=timing_ms,
            budget_used=budget_used,
            trace=trace,
        )

    def project(self, request: MemoryProjectRequest) -> MemoryProjectResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        result_payload = {
            "enabled": False,
            "deferred_reason": "projection is deferred for Phase 1b and has no production caller",
        }
        trace = self.trace(
            event="project",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=(time.perf_counter() - started) * 1000.0,
            budget_used=BudgetUse(),
            dropped_reasons={"deferred": 1},
        )
        return MemoryProjectResult(
            enabled=False,
            deferred_reason=result_payload["deferred_reason"],
            trace_ref=trace.trace_ref,
            trace=trace,
        )

    def inspect_entry(self, request: MemoryInspectRequest) -> MemoryInspectResult:
        started = time.perf_counter()
        request_hash = _stable_json_hash(request.to_dict())
        entry = self.store.get_entry(request.entry_id)
        dropped: Dict[str, int] = {}
        if entry is None:
            dropped["not_found"] = 1
        elif not entry.is_committed_approved():
            dropped["not_committed_approved_memory"] = 1
            entry = None
        elif not entry.has_required_citations():
            dropped["uncited_memory"] = 1
            entry = None

        timing_ms = (time.perf_counter() - started) * 1000.0
        result_payload = {
            "entry": entry.to_dict() if entry else None,
            "dropped": dropped,
            "timing_ms": round(timing_ms, 3),
        }
        trace = self.trace(
            event="inspect_entry",
            request_hash=request_hash,
            result_hash=_stable_json_hash(result_payload),
            timing_ms=timing_ms,
            budget_used=BudgetUse(returned_results=1 if entry else 0, returned_chars=0, store_reads=1),
            dropped_reasons=dropped,
        )
        return MemoryInspectResult(
            entry=entry,
            dropped=dropped,
            trace_ref=trace.trace_ref,
            timing_ms=timing_ms,
            trace=trace,
        )

    def trace(
        self,
        *,
        event: str,
        request_hash: str,
        result_hash: str,
        timing_ms: float,
        budget_used: BudgetUse,
        dropped_reasons: Mapping[str, int],
    ) -> MemoryTrace:
        trace_ref = f"memory-trace:{request_hash[:12]}:{result_hash[:12]}"
        trace = MemoryTrace(
            trace_ref=trace_ref,
            event=event,
            request_hash=request_hash,
            result_hash=result_hash,
            store_id=self.store.store_id,
            index_id=self.store.index_id,
            timing_ms=timing_ms,
            budget_used=budget_used,
            dropped_reasons=dict(dropped_reasons),
        )
        self.traces.append(trace)
        return trace

    def _recall_drop_reason(self, entry: MemoryEntry, request: MemoryRecallRequest) -> str:
        if not entry.is_committed_approved():
            return "not_committed_approved_memory"
        if not entry.has_required_citations():
            return "uncited_memory"
        if request.scope and entry.scope != request.scope:
            return "scope_mismatch"
        if request.memory_kinds and entry.memory_kind not in request.memory_kinds:
            return "memory_kind_mismatch"
        if not request.include_stale and entry.staleness.state in {"stale", "superseded"}:
            return "stale_excluded"
        return ""

    def _best_compression_match(
        self,
        *,
        summary: str,
        memory_kind: str,
        scope: str,
    ) -> Tuple[Optional[MemoryEntry], float]:
        best_entry: Optional[MemoryEntry] = None
        best_score = 0.0
        for entry in self.store.iter_entries():
            if not entry.is_recallable():
                continue
            if entry.memory_kind != memory_kind or entry.scope != scope:
                continue
            score = _text_similarity(summary, entry.search_text())
            if score > best_score:
                best_score = score
                best_entry = entry
        return best_entry, best_score

    def _compression_title(self, request: MemoryCompressionRequest, summary: str) -> str:
        if request.title_hint:
            return _truncate_text(request.title_hint, 100)
        first_sentence = _split_sentences(summary)[0] if summary else ""
        if first_sentence:
            return _truncate_text(first_sentence, 100)
        return f"Compressed {request.memory_kind.replace('_', ' ')} memory"

    def _compression_applicability(
        self,
        request: MemoryCompressionRequest,
        salience_terms: Sequence[str],
    ) -> str:
        if request.applicability_hint:
            return request.applicability_hint
        if salience_terms:
            cues = ", ".join(salience_terms[:5])
            return f"Use in {request.scope} when these cues recur: {cues}."
        return f"Use in {request.scope} when this compressed experience becomes relevant."

    def _score_entry(self, entry: MemoryEntry, query_terms: Iterable[str]) -> float:
        terms = set(query_terms)
        if not terms:
            return entry.confidence
        overlap = len(_matched_query_terms(entry, terms))
        if overlap <= 0:
            return 0.0
        return round((overlap / max(1, len(terms))) * entry.confidence, 6)

    def _candidate_from_entry(
        self,
        entry: MemoryEntry,
        score: float,
        query_terms: Iterable[str],
    ) -> MemoryRecallCandidate:
        terms = _matched_query_terms(entry, query_terms)
        if terms:
            why = f"Matched query terms: {', '.join(terms)}"
        else:
            why = "Returned by committed durable memory listing."
        return MemoryRecallCandidate(
            entry_id=entry.entry_id,
            memory_kind=entry.memory_kind,
            scope=entry.scope,
            title=entry.title,
            summary=entry.summary,
            why_relevant=why,
            evidence_refs=entry.source_refs,
            proof_refs=entry.proof_refs,
            validity=entry.validity,
            confidence=entry.confidence,
            staleness=entry.staleness,
            contradiction=entry.contradiction,
            score=score,
        )

    def _chain_node_from_entry(self, entry: MemoryEntry, depth: int) -> MemoryChainNode:
        return MemoryChainNode(
            entry_id=entry.entry_id,
            memory_kind=entry.memory_kind,
            scope=entry.scope,
            title=entry.title,
            summary=entry.summary,
            evidence_refs=entry.source_refs,
            proof_refs=entry.proof_refs,
            staleness=entry.staleness,
            contradiction=entry.contradiction,
            depth=depth,
        )


__all__ = [
    "BudgetUse",
    "Contradiction",
    "GraphEdge",
    "InMemoryMemoryStore",
    "JsonFileMemoryStore",
    "MemoryAdaptRecallRequest",
    "MemoryAdaptRecallResult",
    "MemoryApproval",
    "MemoryApprovalRequest",
    "MemoryApprovalResult",
    "MemoryCandidate",
    "MemoryCandidateRequest",
    "MemoryCandidateResult",
    "MemoryChainNode",
    "MemoryChainRequest",
    "MemoryChainResult",
    "MemoryCommitRequest",
    "MemoryCommitResult",
    "MemoryEntry",
    "MemoryInspectRequest",
    "MemoryInspectResult",
    "MemoryProjectRequest",
    "MemoryProjectResult",
    "MemoryProposal",
    "MemoryProposalRequest",
    "MemoryProposalResult",
    "MemoryReadStore",
    "MemoryRecallBudget",
    "MemoryRecallCandidate",
    "MemoryRecallRequest",
    "MemoryRecallResult",
    "MemorySystem",
    "MemoryTombstoneRequest",
    "MemoryTombstoneResult",
    "MemoryTrace",
    "ProvenanceRef",
    "Revision",
    "Staleness",
]
