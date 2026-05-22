"""Phase A typed-card schema foundations for the durable memory subsystem.

This module intentionally owns only value objects, validation, stable
serialization, canonical graph identifiers, and narrow migration helpers. It
does not implement durable recall, extraction, approval, commit, projection, or
tool/provider integration behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


MAX_SUMMARY_CHARS = 512
MAX_DETAILS_CHARS = 4096
MAX_RETRIEVAL_TERMS = 32
MAX_RETRIEVAL_TERM_CHARS = 96
MAX_PROVENANCE_EXCERPT_CHARS = 240
CONFIDENCE_HASH_DIGITS = 4

MEMORY_CARD_SCHEMA_VERSION = "memory_card.v1"
PROVENANCE_EVENT_SCHEMA_VERSION = "provenance_event.v1"
GRAPH_NODE_SCHEMA_VERSION = "graph_node.v1"
GRAPH_EDGE_SCHEMA_VERSION = "graph_edge.v1"

_UNRESERVED_BYTES = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-")
_HEX_UPPER = set("0123456789ABCDEF")
_EDGE_ID_RE = re.compile(r"^edge:v1:[0-9a-f]{16}$")
_SCOPE_KEY_RE = re.compile(
    r"^scope:v1:(user|project|repo|branch|task|task_family|team|shared):[0-9a-f]{16}$"
)
_SHARED_POLICY_ID_RE = re.compile(r"^shared_policy:v1:[A-Za-z0-9._~-]+$")


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class RawEventKind(_StrEnum):
    TRANSCRIPT_TURN = "transcript_turn"
    RAW_TRANSCRIPT = "raw_transcript"
    TOOL_CALL = "tool_call"
    COMMAND_OUTPUT = "command_output"
    VERIFIER_OUTPUT = "verifier_output"
    REVIEWER_COMMENT = "reviewer_comment"
    DIFF = "diff"
    FILE_SNAPSHOT = "file_snapshot"
    USER_INSTRUCTION = "user_instruction"
    APPROVAL = "approval"
    MEMORY_PROPOSAL = "memory_proposal"
    OTHER = "other"


class ProvenanceProducer(_StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"
    MAINTAINER = "maintainer"
    SYSTEM = "system"
    ADAPTER = "adapter"
    SCORING = "scoring"
    MIGRATION = "migration"


class RedactionState(_StrEnum):
    NONE = "none"
    REDACTED = "redacted"
    RESTRICTED = "restricted"


class RetentionState(_StrEnum):
    ACTIVE = "active"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class MemoryCardKind(_StrEnum):
    REENTRY_SNAPSHOT = "reentry_snapshot"
    TASK_EPISODE = "task_episode"
    SEMANTIC_FACT = "semantic_fact"
    PROCEDURE = "procedure"
    POLICY_OR_PREFERENCE = "policy_or_preference"


MEMORY_CARD_KINDS = tuple(item.value for item in MemoryCardKind)


class ScopeLevel(_StrEnum):
    USER = "user"
    PROJECT = "project"
    REPO = "repo"
    BRANCH = "branch"
    TASK = "task"
    TASK_FAMILY = "task_family"
    TEAM = "team"
    SHARED = "shared"


class LifecycleLifespan(_StrEnum):
    TURN = "turn"
    SESSION = "session"
    TASK_CHAIN = "task_chain"
    PROJECT_DURABLE = "project_durable"
    USER_DURABLE = "user_durable"
    SHARED = "shared"


class ConsolidationState(_StrEnum):
    NONE = "none"


class AuthoritySource(_StrEnum):
    SELF = "self"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"
    USER = "user"
    MAINTAINER = "maintainer"
    SYSTEM = "system"
    SCORING = "scoring"


class AuthorityStrength(_StrEnum):
    OBSERVATION = "observation"
    HINT = "hint"
    SHOULD = "should"
    MUST = "must"


class ValencePolarity(_StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ValenceEffect(_StrEnum):
    USE = "use"
    AVOID = "avoid"
    VERIFY = "verify"
    ASK = "ask"
    IGNORE = "ignore"


class EvidenceRole(_StrEnum):
    CURRENT_SUPPORT = "current_support"
    PROOF = "proof"
    APPROVAL = "approval"
    LINEAGE = "lineage"
    SUPERSESSION = "supersession"
    INVALIDATOR = "invalidator"
    CONTRADICTION = "contradiction"
    REVIEWER_CONTEXT = "reviewer_context"
    MUTATION_SOURCE = "mutation_source"
    DEBUG = "debug"


class NodeType(_StrEnum):
    MEMORY_CARD = "memory_card"
    PROVENANCE_EVENT = "provenance_event"
    FILE = "file"
    SYMBOL = "symbol"
    TEST = "test"
    COMMAND = "command"
    ERROR_SIGNATURE = "error_signature"
    TASK = "task"
    TASK_FAMILY = "task_family"
    WORKFLOW = "workflow"
    SCOPE = "scope"
    ACTOR = "actor"
    USER = "user"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"


class ActorKind(_StrEnum):
    USER = "user"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"
    MAINTAINER = "maintainer"
    SYSTEM = "system"
    ADAPTER = "adapter"
    SCORING = "scoring"
    MIGRATION = "migration"


class StalenessState(_StrEnum):
    FRESH = "fresh"
    MAYBE_STALE = "maybe_stale"
    STALE = "stale"
    SUPERSEDED = "superseded"


class ContradictionState(_StrEnum):
    NONE = "none"
    POSSIBLE = "possible"
    CONTRADICTED = "contradicted"
    RESOLVED = "resolved"


class ApprovalState(_StrEnum):
    CANDIDATE = "candidate"
    PROPOSAL = "proposal"
    APPROVED = "approved"
    COMMITTED = "committed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"


class ProjectionMode(_StrEnum):
    HIDDEN = "hidden"
    DEBUG_ONLY = "debug_only"
    RECALLED_TOOL_RESULT = "recalled_tool_result"
    CONTEXT_PACKET = "context_packet"
    PROMPT_SECTION = "prompt_section"
    ALWAYS_ON_CORE = "always_on_core"


class PrivacySharing(_StrEnum):
    PRIVATE = "private"
    PROJECT = "project"
    TEAM = "team"
    SHARED = "shared"


class RedactionPolicy(_StrEnum):
    NONE = "none"
    REDACT_PAYLOAD = "redact_payload"
    REFS_ONLY = "refs_only"
    RESTRICTED = "restricted"


class UserVisibleEditing(_StrEnum):
    DISABLED = "disabled"
    ENABLED_LATER = "enabled_later"


class InvalidatorKind(_StrEnum):
    FILE_HASH_CHANGED = "file_hash_changed"
    SYMBOL_MOVED = "symbol_moved"
    SYMBOL_REMOVED = "symbol_removed"
    COMMAND_CHANGED = "command_changed"
    VERIFIER_CHANGED = "verifier_changed"
    BRANCH_CHANGED = "branch_changed"
    TASK_CONTRACT_CHANGED = "task_contract_changed"
    REVIEWER_VETOED = "reviewer_vetoed"
    USER_PREFERENCE_UPDATED = "user_preference_updated"
    POLICY_SUPERSEDED = "policy_superseded"
    PROCEDURE_FAILED_RECENTLY = "procedure_failed_recently"
    MANUAL = "manual"


class TriggerPolicy(_StrEnum):
    HASH_CHANGED = "hash_changed"
    REF_MISSING = "ref_missing"
    REF_CHANGED = "ref_changed"
    VALUE_CHANGED = "value_changed"
    ANY_NEWER_AUTHORITY = "any_newer_authority"
    ANY_NEWER_FAILURE = "any_newer_failure"
    NEWER_EVIDENCE = "newer_evidence"
    MANUAL_ONLY = "manual_only"


class GraphEdgeType(_StrEnum):
    MENTIONS = "mentions"
    APPLIES_TO = "applies_to"
    DOES_NOT_APPLY_TO = "does_not_apply_to"
    PROVED_BY = "proved_by"
    CONTRADICTED_BY = "contradicted_by"
    INVALIDATED_BY = "invalidated_by"
    SUPERSEDES = "supersedes"
    SUPPORTS = "supports"
    AVOIDS = "avoids"
    FIXES = "fixes"
    FAILS_ON = "fails_on"
    LOCATED_IN = "located_in"
    REVIEWED_BY = "reviewed_by"
    APPROVED_BY = "approved_by"
    VETOED_BY = "vetoed_by"
    SEED_EVAL_BY = "seed_eval_by"
    MIGRATED_BY = "migrated_by"
    RELATED = "related"


class MemoryTraceOperation(_StrEnum):
    CAPTURE_PROVENANCE = "capture_provenance"
    EXTRACT_CANDIDATE = "extract_candidate"
    PROPOSE = "propose"
    APPROVE = "approve"
    COMMIT = "commit"
    MUTATE = "mutate"
    RETRIEVE = "retrieve"
    RETRIEVE_TRANSIENT = "retrieve_transient"
    EXPAND = "expand"
    PROJECT = "project"
    REPORT_USAGE = "report_usage"
    MIGRATE = "migrate"
    ROLLBACK = "rollback"
    SEED_EVAL = "seed_eval"


class TraceActor(_StrEnum):
    CORE = "core"
    DEBUG = "debug"
    SCORING = "scoring"
    ADAPTER = "adapter"
    MODEL_PROPOSAL = "model_proposal"
    USER = "user"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"
    MAINTAINER = "maintainer"
    MIGRATION = "migration"
    SYSTEM = "system"


class CandidateProducer(_StrEnum):
    MODEL = "model"
    DETERMINISTIC_EXTRACTOR = "deterministic_extractor"
    USER = "user"
    REVIEWER = "reviewer"
    DEBUG = "debug"
    SCORING = "scoring"
    ADAPTER = "adapter"


class EvidencePresenceState(_StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNKNOWN = "unknown"


class SymbolPresenceState(_StrEnum):
    PRESENT = "present"
    MOVED = "moved"
    MISSING = "missing"
    UNKNOWN = "unknown"


class CommandPresenceState(_StrEnum):
    PRESENT = "present"
    CHANGED = "changed"
    UNKNOWN = "unknown"


class VerifierResultValue(_StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNKNOWN = "unknown"


class CurrentAuthoritySource(_StrEnum):
    USER = "user"
    REVIEWER = "reviewer"
    MAINTAINER = "maintainer"
    SYSTEM = "system"
    VERIFIER = "verifier"


_DEFAULT_INVALIDATOR_POLICY = {
    InvalidatorKind.FILE_HASH_CHANGED.value: TriggerPolicy.HASH_CHANGED.value,
    InvalidatorKind.SYMBOL_MOVED.value: TriggerPolicy.REF_CHANGED.value,
    InvalidatorKind.SYMBOL_REMOVED.value: TriggerPolicy.REF_MISSING.value,
    InvalidatorKind.COMMAND_CHANGED.value: TriggerPolicy.HASH_CHANGED.value,
    InvalidatorKind.VERIFIER_CHANGED.value: TriggerPolicy.HASH_CHANGED.value,
    InvalidatorKind.BRANCH_CHANGED.value: TriggerPolicy.VALUE_CHANGED.value,
    InvalidatorKind.TASK_CONTRACT_CHANGED.value: TriggerPolicy.HASH_CHANGED.value,
    InvalidatorKind.REVIEWER_VETOED.value: TriggerPolicy.ANY_NEWER_AUTHORITY.value,
    InvalidatorKind.USER_PREFERENCE_UPDATED.value: TriggerPolicy.ANY_NEWER_AUTHORITY.value,
    InvalidatorKind.POLICY_SUPERSEDED.value: TriggerPolicy.ANY_NEWER_AUTHORITY.value,
    InvalidatorKind.PROCEDURE_FAILED_RECENTLY.value: TriggerPolicy.ANY_NEWER_FAILURE.value,
    InvalidatorKind.MANUAL.value: TriggerPolicy.MANUAL_ONLY.value,
}


def _nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


def _text(value: Any, *, allow_empty: bool = True, field_name: str = "value") -> str:
    if value is None:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name} must not be empty")
    text = _nfc(value).strip()
    if not text and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _nfc(value).strip()
    return text if text else None


def _enum_value(enum_class: type[_StrEnum], value: Any, field_name: str) -> str:
    if isinstance(value, enum_class):
        return value.value
    text = _text(value, allow_empty=False, field_name=field_name)
    try:
        return enum_class(text).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_class)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _tuple_text(values: Any, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence")
    return tuple(_text(item, allow_empty=False, field_name=field_name) for item in values)


def _retrieval_terms(values: Any, field_name: str = "retrieval_terms") -> tuple[str, ...]:
    terms = _tuple_text(values, field_name)
    normalized: list[str] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = " ".join(term.split())
        if not cleaned:
            continue
        if len(cleaned) > MAX_RETRIEVAL_TERM_CHARS:
            raise ValueError(f"{field_name} items must be <= {MAX_RETRIEVAL_TERM_CHARS} chars")
        if _has_long_direct_quote(cleaned) or re.search(r"\b(User|Assistant|System|Tool):", cleaned):
            raise ValueError(f"{field_name} must contain concise anchor terms, not transcript excerpts")
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    if len(normalized) > MAX_RETRIEVAL_TERMS:
        raise ValueError(f"{field_name} must contain <= {MAX_RETRIEVAL_TERMS} items")
    return tuple(normalized)


def _tuple_of(cls: type[Any], values: Any, field_name: str) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence")
    result = []
    for item in values:
        if isinstance(item, cls):
            result.append(item)
        elif hasattr(cls, "from_dict") and isinstance(item, Mapping):
            result.append(cls.from_dict(item))
        else:
            result.append(cls(item))
    return tuple(result)


def _validate_confidence(value: Any, field_name: str = "confidence") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite float in [0.0, 1.0]") from exc
    if math.isnan(number) or math.isinf(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"{field_name} must be a finite float in [0.0, 1.0]")
    return number


def _plain(value: Any, *, omit_none: bool = False) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name), omit_none=omit_none)
            for item in fields(value)
            if not (omit_none and getattr(value, item.name) is None)
        }
    if isinstance(value, Mapping):
        return {
            _nfc(key): _plain(child, omit_none=omit_none)
            for key, child in sorted(value.items(), key=lambda item: _nfc(item[0]))
            if not (omit_none and child is None)
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item, omit_none=omit_none) for item in value]
    if isinstance(value, set):
        normalized = [_plain(item, omit_none=omit_none) for item in value]
        return sorted(normalized, key=lambda item: stable_json(item, omit_none=omit_none))
    if isinstance(value, str):
        return _nfc(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("non-finite floats are not stable JSON")
        return round(value, CONFIDENCE_HASH_DIGITS)
    return value


def stable_json(value: Any, *, omit_none: bool = False) -> str:
    """Return canonical JSON with sorted keys and NFC-normalized strings."""

    return json.dumps(
        _plain(value, omit_none=omit_none),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_hash(value: Any, *, omit_none: bool = False) -> str:
    payload = stable_json(value, omit_none=omit_none).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def stable_short_hash(value: Any, *, length: int = 16, omit_none: bool = False) -> str:
    return stable_hash(value, omit_none=omit_none).removeprefix("sha256:")[:length]


def _validate_schema_version(version: Any, prefix: str) -> str:
    text = _text(version, allow_empty=False, field_name="schema_version")
    match = re.fullmatch(rf"{re.escape(prefix)}\.v([0-9]+)(?:\.([0-9]+))?", text)
    if not match:
        raise ValueError(f"schema_version must be {prefix}.v<known-major>")
    if match.group(1) != "1":
        raise ValueError(f"unknown {prefix} schema major version: v{match.group(1)}")
    return text


@dataclass(frozen=True)
class RawMemoryIngestRequest:
    raw_text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_text", _text(self.raw_text, allow_empty=False, field_name="raw_text"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawMemoryIngestRequest":
        extra = set(data) - {"raw_text"}
        if extra:
            raise ValueError(
                "RawMemoryIngestRequest v1 accepts only raw_text; rich hint fields are rejected"
            )
        return cls(raw_text=data.get("raw_text"))

    def to_dict(self) -> dict[str, Any]:
        return {"raw_text": self.raw_text}


@dataclass(frozen=True)
class RawMemoryExtractorConfig:
    """Schema-only extractor binding defaults; never performs model calls."""

    backend: str = "codex"
    model: str = "gpt-5.5"
    auth_path: str = "auth.json"
    call_interface: str = "call_model_structured_json"
    injectable_caller: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend", _text(self.backend, allow_empty=False, field_name="extractor.backend"))
        object.__setattr__(self, "model", _text(self.model, allow_empty=False, field_name="extractor.model"))
        object.__setattr__(self, "auth_path", _text(self.auth_path, allow_empty=False, field_name="extractor.auth_path"))
        object.__setattr__(
            self,
            "call_interface",
            _text(self.call_interface, allow_empty=False, field_name="extractor.call_interface"),
        )
        if self.call_interface not in {"call_model_json", "call_model_structured_json"}:
            raise ValueError("raw-memory extractor config must bind through call_model_json or call_model_structured_json")
        object.__setattr__(self, "injectable_caller", bool(self.injectable_caller))

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "auth_path": self.auth_path,
            "call_interface": self.call_interface,
            "injectable_caller": self.injectable_caller,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawMemoryExtractorConfig":
        forbidden = {"api_key", "token", "secret", "auth_token"} & set(data)
        if forbidden:
            raise ValueError("extractor config schema must not store token material")
        return cls(
            backend=data.get("backend", "codex"),
            model=data.get("model", "gpt-5.5"),
            auth_path=data.get("auth_path", "auth.json"),
            call_interface=data.get("call_interface", "call_model_structured_json"),
            injectable_caller=data.get("injectable_caller", True),
        )


@dataclass(frozen=True)
class Scope:
    level: str
    namespace: str
    user_id: str | None = None
    project_id: str | None = None
    repo_ref: str | None = None
    branch_ref: str | None = None
    task_ref: str | None = None
    task_family: str | None = None
    lane_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _enum_value(ScopeLevel, self.level, "scope.level"))
        object.__setattr__(self, "namespace", _text(self.namespace, allow_empty=False, field_name="scope.namespace"))
        for name in (
            "user_id",
            "project_id",
            "repo_ref",
            "branch_ref",
            "task_ref",
            "task_family",
            "lane_id",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))

    def identity_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "repo_ref": self.repo_ref,
            "branch_ref": self.branch_ref,
            "task_ref": self.task_ref,
            "task_family": self.task_family,
            "lane_id": self.lane_id,
        }

    def canonical_json(self) -> str:
        return stable_json(self.identity_dict(), omit_none=True)

    def scope_key(self) -> str:
        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]
        return f"scope:v1:{self.level}:{digest}"

    def to_dict(self) -> dict[str, Any]:
        return self.identity_dict()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scope":
        return cls(
            level=data.get("level"),
            namespace=data.get("namespace"),
            user_id=data.get("user_id"),
            project_id=data.get("project_id"),
            repo_ref=data.get("repo_ref"),
            branch_ref=data.get("branch_ref"),
            task_ref=data.get("task_ref"),
            task_family=data.get("task_family"),
            lane_id=data.get("lane_id"),
        )


@dataclass(frozen=True)
class Lifecycle:
    lifespan: str
    expires_at: str | None = None
    consolidation_state: str = ConsolidationState.NONE.value
    retention_policy_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "lifespan", _enum_value(LifecycleLifespan, self.lifespan, "lifecycle.lifespan"))
        object.__setattr__(
            self,
            "consolidation_state",
            _enum_value(ConsolidationState, self.consolidation_state, "lifecycle.consolidation_state"),
        )
        object.__setattr__(self, "expires_at", _optional_text(self.expires_at))
        object.__setattr__(self, "retention_policy_id", _optional_text(self.retention_policy_id))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Lifecycle":
        return cls(
            lifespan=data.get("lifespan"),
            expires_at=data.get("expires_at"),
            consolidation_state=data.get("consolidation_state", ConsolidationState.NONE.value),
            retention_policy_id=data.get("retention_policy_id"),
        )


@dataclass(frozen=True)
class Authority:
    source: str
    strength: str
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        source = _enum_value(AuthoritySource, self.source, "authority.source")
        strength = _enum_value(AuthorityStrength, self.strength, "authority.strength")
        if strength == AuthorityStrength.MUST.value and source in {
            AuthoritySource.SELF.value,
            AuthoritySource.SCORING.value,
        }:
            raise ValueError("authority.strength=must requires explicit user/reviewer/verifier/maintainer/system authority")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "source_refs", _tuple_text(self.source_refs, "authority.source_refs"))

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "strength": self.strength, "source_refs": list(self.source_refs)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Authority":
        return cls(
            source=data.get("source"),
            strength=data.get("strength"),
            source_refs=tuple(data.get("source_refs") or ()),
        )


@dataclass(frozen=True)
class Valence:
    polarity: str = ValencePolarity.NEUTRAL.value
    effect: str = ValenceEffect.USE.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "polarity", _enum_value(ValencePolarity, self.polarity, "valence.polarity"))
        object.__setattr__(self, "effect", _enum_value(ValenceEffect, self.effect, "valence.effect"))

    def to_dict(self) -> dict[str, Any]:
        return {"polarity": self.polarity, "effect": self.effect}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Valence":
        return cls(polarity=data.get("polarity", ValencePolarity.NEUTRAL.value), effect=data.get("effect", ValenceEffect.USE.value))


@dataclass(frozen=True)
class EvidenceLink:
    ref_id: str
    role: str
    active: bool = True
    added_by_mutation_id: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _text(self.ref_id, allow_empty=False, field_name="evidence_link.ref_id"))
        object.__setattr__(self, "role", _enum_value(EvidenceRole, self.role, "evidence_link.role"))
        object.__setattr__(self, "active", bool(self.active))
        object.__setattr__(self, "added_by_mutation_id", _optional_text(self.added_by_mutation_id))
        object.__setattr__(self, "note", _optional_text(self.note))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceLink":
        return cls(
            ref_id=data.get("ref_id"),
            role=data.get("role"),
            active=data.get("active", True),
            added_by_mutation_id=data.get("added_by_mutation_id"),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class NodeIdV1:
    node_type: str
    scope_key: str
    canonical_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_type", _enum_value(NodeType, self.node_type, "node_type"))
        object.__setattr__(self, "scope_key", _text(self.scope_key, allow_empty=False, field_name="scope_key"))
        object.__setattr__(self, "canonical_ref", _text(self.canonical_ref, allow_empty=False, field_name="canonical_ref"))

    def serialize(self) -> str:
        return make_node_id_v1(self.node_type, self.scope_key, self.canonical_ref)

    @classmethod
    def parse(cls, node_id: str) -> "NodeIdV1":
        return parse_node_id_v1(node_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "scope_key": self.scope_key,
            "canonical_ref": self.canonical_ref,
            "node_id": self.serialize(),
        }


def _percent_encode_component(value: str) -> str:
    encoded = []
    for byte in _nfc(value).encode("utf-8"):
        if byte in _UNRESERVED_BYTES:
            encoded.append(chr(byte))
        else:
            encoded.append(f"%{byte:02X}")
    return "".join(encoded)


def _percent_decode_component(value: str) -> str:
    raw = _text(value, allow_empty=False, field_name="encoded component")
    output = bytearray()
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "%":
            if index + 2 >= len(raw):
                raise ValueError("percent escape must include two uppercase hex digits")
            hi = raw[index + 1]
            lo = raw[index + 2]
            if hi not in _HEX_UPPER or lo not in _HEX_UPPER:
                raise ValueError("percent escapes must use uppercase hex digits")
            output.append(int(raw[index + 1 : index + 3], 16))
            index += 3
            continue
        byte = ord(char)
        if byte > 127 or byte not in _UNRESERVED_BYTES:
            raise ValueError("unreserved characters only may appear unescaped")
        output.append(byte)
        index += 1
    decoded = output.decode("utf-8")
    normalized = _nfc(decoded)
    if _percent_encode_component(normalized) != raw:
        raise ValueError("non-canonical percent encoding")
    if re.search(r"%[0-9A-Fa-f]{2}", normalized):
        raise ValueError("double-encoded node id component")
    return normalized


def make_node_id_v1(node_type: str, scope_key: str, canonical_ref: str) -> str:
    node_type_value = _enum_value(NodeType, node_type, "node_type")
    scope_key_text = _text(scope_key, allow_empty=False, field_name="scope_key")
    canonical_ref_text = _text(canonical_ref, allow_empty=False, field_name="canonical_ref")
    return (
        "node:v1:"
        + node_type_value
        + ":"
        + _percent_encode_component(scope_key_text)
        + ":"
        + _percent_encode_component(canonical_ref_text)
    )


def parse_node_id_v1(node_id: str) -> NodeIdV1:
    text = _text(node_id, allow_empty=False, field_name="node_id")
    parts = text.split(":")
    if len(parts) != 5 or parts[0] != "node" or parts[1] != "v1":
        raise ValueError("NodeIdV1 must serialize as node:v1:<node_type>:<scope_key>:<canonical_ref>")
    return NodeIdV1(
        node_type=_enum_value(NodeType, parts[2], "node_type"),
        scope_key=_percent_decode_component(parts[3]),
        canonical_ref=_percent_decode_component(parts[4]),
    )


_APPLICABILITY_PREFIXES = {
    "file",
    "symbol",
    "test",
    "cmd",
    "err",
    "task",
    "task_family",
    "workflow",
    "scope",
    "user",
    "reviewer",
    "verifier",
}


@dataclass(frozen=True)
class ApplicabilityRef:
    value: str

    def __post_init__(self) -> None:
        value = _text(self.value, allow_empty=False, field_name="applicability_ref")
        _validate_applicability_ref(value)
        object.__setattr__(self, "value", value)

    def to_dict(self) -> str:
        return self.value

    @classmethod
    def from_dict(cls, data: Any) -> "ApplicabilityRef":
        return cls(str(data))


def _validate_applicability_ref(value: str) -> None:
    if value.startswith("node:v1:"):
        parse_node_id_v1(value)
        return
    if "\n" in value or "\r" in value:
        raise ValueError("applicability refs must be single-line")
    if value.startswith("text:"):
        if not re.fullmatch(r"text:[0-9a-f]{12}:[a-z0-9][a-z0-9._-]{0,63}", value):
            raise ValueError("text applicability refs must be text:<sha256-12>:<short-slug>")
        return
    prefix, separator, rest = value.partition(":")
    if not separator or prefix not in _APPLICABILITY_PREFIXES or not rest:
        raise ValueError("applicability ref must be a canonical node id or reserved typed ref")
    if prefix in {"task_family", "workflow"} and not re.fullmatch(r"[A-Za-z0-9._~-]+", rest):
        raise ValueError(f"{prefix} refs require a stable id")
    if prefix == "scope":
        if value.startswith("scope:v1:"):
            pieces = value.split(":")
            if len(pieces) != 4 or not pieces[2] or not re.fullmatch(r"[0-9a-f]{16}", pieces[3]):
                raise ValueError("scope_key refs must be scope:v1:<level>:<digest16>")
        elif len(value.split(":")) < 3:
            raise ValueError("scope refs must include a level and stable id")


@dataclass(frozen=True)
class Applicability:
    applies_to: tuple[ApplicabilityRef, ...] = ()
    does_not_apply_to: tuple[ApplicabilityRef, ...] = ()
    prerequisites: tuple[ApplicabilityRef, ...] = ()
    counterexamples: tuple[ApplicabilityRef, ...] = ()

    def __post_init__(self) -> None:
        for name in ("applies_to", "does_not_apply_to", "prerequisites", "counterexamples"):
            object.__setattr__(self, name, _tuple_of(ApplicabilityRef, getattr(self, name), name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "applies_to": [item.to_dict() for item in self.applies_to],
            "does_not_apply_to": [item.to_dict() for item in self.does_not_apply_to],
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "counterexamples": [item.to_dict() for item in self.counterexamples],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Applicability":
        return cls(
            applies_to=tuple(data.get("applies_to") or ()),
            does_not_apply_to=tuple(data.get("does_not_apply_to") or ()),
            prerequisites=tuple(data.get("prerequisites") or ()),
            counterexamples=tuple(data.get("counterexamples") or ()),
        )


@dataclass(frozen=True)
class Invalidator:
    kind: str
    ref: str | None = None
    target_node_id: str | None = None
    target_node_type: str | None = None
    baseline_hash: str | None = None
    baseline_ref: str | None = None
    baseline_value: str | None = None
    baseline_observed_at: str | None = None
    trigger_policy: str | None = None
    manual_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    checked_at: str | None = None

    def __post_init__(self) -> None:
        kind = _enum_value(InvalidatorKind, self.kind, "invalidator.kind")
        policy = self.trigger_policy or _DEFAULT_INVALIDATOR_POLICY[kind]
        policy = _enum_value(TriggerPolicy, policy, "invalidator.trigger_policy")
        target_node_type = (
            _enum_value(NodeType, self.target_node_type, "invalidator.target_node_type")
            if self.target_node_type is not None
            else None
        )
        target_node_id = _optional_text(self.target_node_id)
        if target_node_id:
            parsed = parse_node_id_v1(target_node_id)
            if target_node_type is not None and parsed.node_type != target_node_type:
                raise ValueError("invalidator.target_node_id type must match target_node_type")
            target_node_type = target_node_type or parsed.node_type

        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "trigger_policy", policy)
        object.__setattr__(self, "target_node_id", target_node_id)
        object.__setattr__(self, "target_node_type", target_node_type)
        for name in (
            "ref",
            "baseline_hash",
            "baseline_ref",
            "baseline_value",
            "baseline_observed_at",
            "manual_reason",
            "checked_at",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        object.__setattr__(self, "metadata", _plain(self.metadata))
        self._validate_policy_combo()

    def _validate_policy_combo(self) -> None:
        if self.kind == InvalidatorKind.FILE_HASH_CHANGED.value:
            self._require_target(NodeType.FILE.value)
            self._require(self.baseline_hash, "file_hash_changed requires baseline_hash")
            self._require_policy({TriggerPolicy.HASH_CHANGED.value})
        elif self.kind == InvalidatorKind.SYMBOL_MOVED.value:
            self._require_target(NodeType.SYMBOL.value)
            self._require(self.baseline_ref, "symbol_moved requires baseline_ref")
            self._require_policy({TriggerPolicy.REF_CHANGED.value})
        elif self.kind == InvalidatorKind.SYMBOL_REMOVED.value:
            self._require_target(NodeType.SYMBOL.value)
            self._require(self.baseline_ref, "symbol_removed requires baseline_ref")
            self._require_policy({TriggerPolicy.REF_MISSING.value})
        elif self.kind == InvalidatorKind.COMMAND_CHANGED.value:
            self._require_target(NodeType.COMMAND.value)
            self._require(self.baseline_hash or self.baseline_ref, "command_changed requires baseline_hash or baseline_ref")
            self._require_policy({TriggerPolicy.HASH_CHANGED.value, TriggerPolicy.REF_CHANGED.value})
        elif self.kind == InvalidatorKind.VERIFIER_CHANGED.value:
            self._require(self.baseline_hash or self.baseline_value, "verifier_changed requires baseline_hash or baseline_value")
            self._require_policy({TriggerPolicy.HASH_CHANGED.value, TriggerPolicy.VALUE_CHANGED.value})
        elif self.kind == InvalidatorKind.BRANCH_CHANGED.value:
            self._require(self.baseline_value, "branch_changed requires baseline_value")
            self._require_policy({TriggerPolicy.VALUE_CHANGED.value})
        elif self.kind == InvalidatorKind.TASK_CONTRACT_CHANGED.value:
            self._require(
                self.baseline_ref or self.baseline_hash,
                "task_contract_changed requires baseline_ref or baseline_hash",
            )
            self._require_policy({TriggerPolicy.HASH_CHANGED.value, TriggerPolicy.REF_CHANGED.value})
        elif self.kind in {
            InvalidatorKind.REVIEWER_VETOED.value,
            InvalidatorKind.USER_PREFERENCE_UPDATED.value,
            InvalidatorKind.POLICY_SUPERSEDED.value,
        }:
            self._require(self.baseline_observed_at, f"{self.kind} requires baseline_observed_at")
            self._require_policy({TriggerPolicy.ANY_NEWER_AUTHORITY.value})
        elif self.kind == InvalidatorKind.PROCEDURE_FAILED_RECENTLY.value:
            self._require(self.baseline_observed_at, "procedure_failed_recently requires baseline_observed_at")
            self._require(
                self.target_node_id or self.baseline_ref or self.ref,
                "procedure_failed_recently requires an applicability/task/error target ref",
            )
            self._require_policy({TriggerPolicy.ANY_NEWER_FAILURE.value, TriggerPolicy.NEWER_EVIDENCE.value})
        elif self.kind == InvalidatorKind.MANUAL.value:
            self._require(self.manual_reason, "manual invalidator requires manual_reason")
            self._require_policy({TriggerPolicy.MANUAL_ONLY.value})

    def _require(self, condition: Any, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def _require_policy(self, allowed: set[str]) -> None:
        if self.trigger_policy not in allowed:
            raise ValueError(f"{self.kind} does not allow trigger_policy={self.trigger_policy}")

    def _require_target(self, node_type: str) -> None:
        if self.target_node_type != node_type:
            raise ValueError(f"{self.kind} requires target_node_type={node_type}")

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Invalidator":
        return cls(
            kind=data.get("kind"),
            ref=data.get("ref"),
            target_node_id=data.get("target_node_id"),
            target_node_type=data.get("target_node_type"),
            baseline_hash=data.get("baseline_hash"),
            baseline_ref=data.get("baseline_ref"),
            baseline_value=data.get("baseline_value"),
            baseline_observed_at=data.get("baseline_observed_at"),
            trigger_policy=data.get("trigger_policy"),
            manual_reason=data.get("manual_reason"),
            metadata=data.get("metadata") or {},
            checked_at=data.get("checked_at"),
        )


def _validate_edge_id(edge_id: str) -> str:
    text = _text(edge_id, allow_empty=False, field_name="graph_refs.edge_ids")
    if not _EDGE_ID_RE.fullmatch(text):
        raise ValueError("graph edge refs must be canonical edge:v1:<16-lower-hex> ids")
    return text


def _validate_allowed_scope_id(scope_id: str) -> str:
    text = _text(scope_id, allow_empty=False, field_name="privacy.allowed_scope_ids")
    if _SCOPE_KEY_RE.fullmatch(text) or _SHARED_POLICY_ID_RE.fullmatch(text):
        return text
    raise ValueError(
        "privacy.allowed_scope_ids must contain canonical scope:v1:<level>:<16-lower-hex> "
        "or shared_policy:v1:<stable-id> ids"
    )


@dataclass(frozen=True)
class GraphRefs:
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        node_ids = _tuple_text(self.node_ids, "graph_refs.node_ids")
        for node_id in node_ids:
            parse_node_id_v1(node_id)
        object.__setattr__(self, "node_ids", node_ids)
        edge_ids = _tuple_text(self.edge_ids, "graph_refs.edge_ids")
        for edge_id in edge_ids:
            _validate_edge_id(edge_id)
        object.__setattr__(self, "edge_ids", edge_ids)

    def to_dict(self) -> dict[str, Any]:
        return {"node_ids": list(self.node_ids), "edge_ids": list(self.edge_ids)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphRefs":
        return cls(node_ids=tuple(data.get("node_ids") or ()), edge_ids=tuple(data.get("edge_ids") or ()))


@dataclass(frozen=True)
class PrivacyRules:
    sharing: str = PrivacySharing.PRIVATE.value
    allowed_scope_ids: tuple[str, ...] = ()
    redaction_policy: str = RedactionPolicy.NONE.value
    user_visible_editing: str = UserVisibleEditing.DISABLED.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "sharing", _enum_value(PrivacySharing, self.sharing, "privacy.sharing"))
        object.__setattr__(
            self,
            "redaction_policy",
            _enum_value(RedactionPolicy, self.redaction_policy, "privacy.redaction_policy"),
        )
        object.__setattr__(
            self,
            "user_visible_editing",
            _enum_value(UserVisibleEditing, self.user_visible_editing, "privacy.user_visible_editing"),
        )
        allowed = _tuple_text(self.allowed_scope_ids, "privacy.allowed_scope_ids")
        for scope_id in allowed:
            _validate_allowed_scope_id(scope_id)
        object.__setattr__(self, "allowed_scope_ids", allowed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sharing": self.sharing,
            "allowed_scope_ids": list(self.allowed_scope_ids),
            "redaction_policy": self.redaction_policy,
            "user_visible_editing": self.user_visible_editing,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PrivacyRules":
        return cls(
            sharing=data.get("sharing", PrivacySharing.PRIVATE.value),
            allowed_scope_ids=tuple(data.get("allowed_scope_ids") or ()),
            redaction_policy=data.get("redaction_policy", RedactionPolicy.NONE.value),
            user_visible_editing=data.get("user_visible_editing", UserVisibleEditing.DISABLED.value),
        )


@dataclass(frozen=True)
class MemoryTimestamps:
    created_at: str
    updated_at: str
    last_verified_at: str | None = None
    superseded_at: str | None = None
    tombstoned_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _text(self.created_at, allow_empty=False, field_name="timestamps.created_at"))
        object.__setattr__(self, "updated_at", _text(self.updated_at, allow_empty=False, field_name="timestamps.updated_at"))
        for name in ("last_verified_at", "superseded_at", "tombstoned_at"):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryTimestamps":
        return cls(
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            last_verified_at=data.get("last_verified_at"),
            superseded_at=data.get("superseded_at"),
            tombstoned_at=data.get("tombstoned_at"),
        )


@dataclass(frozen=True)
class MemoryRevision:
    version: int = 1
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    contradicted_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        version = int(self.version)
        if version < 1:
            raise ValueError("revision.version must be >= 1")
        object.__setattr__(self, "version", version)
        for name in ("supersedes", "superseded_by", "contradicted_by"):
            object.__setattr__(self, name, _tuple_text(getattr(self, name), f"revision.{name}"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "supersedes": list(self.supersedes),
            "superseded_by": list(self.superseded_by),
            "contradicted_by": list(self.contradicted_by),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryRevision":
        return cls(
            version=data.get("version", 1),
            supersedes=tuple(data.get("supersedes") or ()),
            superseded_by=tuple(data.get("superseded_by") or ()),
            contradicted_by=tuple(data.get("contradicted_by") or ()),
        )


@dataclass(frozen=True)
class MemoryAuditFields:
    created_by: str
    write_reason: str
    create_audit_id: str
    last_semantic_mutation_audit_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_by", _enum_value(TraceActor, self.created_by, "audit.created_by"))
        object.__setattr__(self, "write_reason", _text(self.write_reason, allow_empty=False, field_name="audit.write_reason"))
        object.__setattr__(self, "create_audit_id", _text(self.create_audit_id, allow_empty=False, field_name="audit.create_audit_id"))
        object.__setattr__(
            self,
            "last_semantic_mutation_audit_id",
            _optional_text(self.last_semantic_mutation_audit_id),
        )

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryAuditFields":
        return cls(
            created_by=data.get("created_by"),
            write_reason=data.get("write_reason"),
            create_audit_id=data.get("create_audit_id"),
            last_semantic_mutation_audit_id=data.get("last_semantic_mutation_audit_id"),
        )


def _validate_card_text(summary: str, details: str | None, approval_state: str) -> None:
    if not summary or len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError(f"summary must be 1..{MAX_SUMMARY_CHARS} chars")
    if details is not None and len(details) > MAX_DETAILS_CHARS:
        raise ValueError(f"details must be <= {MAX_DETAILS_CHARS} chars")
    if approval_state != ApprovalState.COMMITTED.value:
        return
    combined = "\n".join(item for item in (summary, details or "") if item)
    if _looks_like_raw_transcript(combined):
        raise ValueError("committed card prose must not store raw transcript or raw tool dumps")
    if details and _has_long_direct_quote(details):
        raise ValueError("direct quote/excerpt material over 240 chars belongs in provenance_excerpt")


_SPEAKER_LINE = re.compile(
    r"^\s*(user|assistant|system|developer|tool|verifier|reviewer|maintainer|model|agent)\s*:",
    re.IGNORECASE,
)


def _looks_like_raw_transcript(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    speaker_lines = sum(1 for line in lines if _SPEAKER_LINE.search(line))
    if speaker_lines >= 2:
        return True
    raw_markers = (
        "raw_transcript",
        "transcript_turn",
        "tool output:",
        "command output:",
        "stdout:",
        "stderr:",
        "traceback (most recent call last):",
    )
    lowered = text.casefold()
    return len(text) > MAX_PROVENANCE_EXCERPT_CHARS and any(marker in lowered for marker in raw_markers)


def _has_long_direct_quote(text: str) -> bool:
    if any(line.strip().startswith(">") and len(line.strip()) > MAX_PROVENANCE_EXCERPT_CHARS for line in text.splitlines()):
        return True
    return bool(re.search(r'"[^"]{241,}"', text, re.DOTALL))


@dataclass(frozen=True)
class MemoryCard:
    card_id: str
    kind: str
    summary: str
    scope: Scope
    lifecycle: Lifecycle
    authority: Authority
    valence: Valence
    applicability: Applicability
    evidence_links: tuple[EvidenceLink, ...]
    invalidators: tuple[Invalidator, ...]
    graph_refs: GraphRefs
    privacy: PrivacyRules
    timestamps: MemoryTimestamps
    revision: MemoryRevision
    audit: MemoryAuditFields
    schema_version: str = MEMORY_CARD_SCHEMA_VERSION
    details: str | None = None
    confidence: float = 1.0
    staleness_state: str = StalenessState.FRESH.value
    contradiction_state: str = ContradictionState.NONE.value
    approval_state: str = ApprovalState.PROPOSAL.value
    projection_mode: str = ProjectionMode.DEBUG_ONLY.value
    retrieval_terms: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _validate_schema_version(self.schema_version, "memory_card"))
        object.__setattr__(self, "card_id", _text(self.card_id, allow_empty=False, field_name="card_id"))
        object.__setattr__(self, "kind", _enum_value(MemoryCardKind, self.kind, "kind"))
        object.__setattr__(self, "summary", _text(self.summary, allow_empty=False, field_name="summary"))
        object.__setattr__(self, "details", _optional_text(self.details))
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(
            self,
            "lifecycle",
            self.lifecycle if isinstance(self.lifecycle, Lifecycle) else Lifecycle.from_dict(self.lifecycle),
        )
        object.__setattr__(
            self,
            "authority",
            self.authority if isinstance(self.authority, Authority) else Authority.from_dict(self.authority),
        )
        object.__setattr__(self, "valence", self.valence if isinstance(self.valence, Valence) else Valence.from_dict(self.valence))
        object.__setattr__(
            self,
            "applicability",
            self.applicability if isinstance(self.applicability, Applicability) else Applicability.from_dict(self.applicability),
        )
        object.__setattr__(self, "evidence_links", _tuple_of(EvidenceLink, self.evidence_links, "evidence_links"))
        object.__setattr__(self, "invalidators", _tuple_of(Invalidator, self.invalidators, "invalidators"))
        object.__setattr__(self, "graph_refs", self.graph_refs if isinstance(self.graph_refs, GraphRefs) else GraphRefs.from_dict(self.graph_refs))
        object.__setattr__(self, "privacy", self.privacy if isinstance(self.privacy, PrivacyRules) else PrivacyRules.from_dict(self.privacy))
        object.__setattr__(
            self,
            "timestamps",
            self.timestamps if isinstance(self.timestamps, MemoryTimestamps) else MemoryTimestamps.from_dict(self.timestamps),
        )
        object.__setattr__(self, "revision", self.revision if isinstance(self.revision, MemoryRevision) else MemoryRevision.from_dict(self.revision))
        object.__setattr__(self, "audit", self.audit if isinstance(self.audit, MemoryAuditFields) else MemoryAuditFields.from_dict(self.audit))
        object.__setattr__(
            self,
            "staleness_state",
            _enum_value(StalenessState, self.staleness_state, "staleness_state"),
        )
        object.__setattr__(
            self,
            "contradiction_state",
            _enum_value(ContradictionState, self.contradiction_state, "contradiction_state"),
        )
        object.__setattr__(self, "approval_state", _enum_value(ApprovalState, self.approval_state, "approval_state"))
        object.__setattr__(self, "projection_mode", _enum_value(ProjectionMode, self.projection_mode, "projection_mode"))
        object.__setattr__(self, "retrieval_terms", _retrieval_terms(self.retrieval_terms))
        object.__setattr__(self, "metadata", _plain(self.metadata))
        _validate_card_text(self.summary, self.details, self.approval_state)
        if self.approval_state == ApprovalState.COMMITTED.value:
            support_roles = {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value}
            if not any(link.active and link.role in support_roles for link in self.evidence_links):
                raise ValueError("committed durable cards require active role-bearing evidence_links")

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "schema_version": self.schema_version,
            "kind": self.kind,
            "summary": self.summary,
            "details": self.details,
            "confidence": self.confidence,
            "scope": self.scope.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "authority": self.authority.to_dict(),
            "valence": self.valence.to_dict(),
            "applicability": self.applicability.to_dict(),
            "evidence_links": [item.to_dict() for item in self.evidence_links],
            "invalidators": [item.to_dict() for item in self.invalidators],
            "staleness_state": self.staleness_state,
            "contradiction_state": self.contradiction_state,
            "approval_state": self.approval_state,
            "projection_mode": self.projection_mode,
            "retrieval_terms": list(self.retrieval_terms),
            "graph_refs": self.graph_refs.to_dict(),
            "privacy": self.privacy.to_dict(),
            "timestamps": self.timestamps.to_dict(),
            "revision": self.revision.to_dict(),
            "audit": self.audit.to_dict(),
            "metadata": _plain(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryCard":
        payload = _normalize_memory_card_payload(data, migrate_retired_projection=False)
        return cls(
            card_id=payload.get("card_id"),
            schema_version=payload.get("schema_version", MEMORY_CARD_SCHEMA_VERSION),
            kind=payload.get("kind"),
            summary=payload.get("summary"),
            details=payload.get("details"),
            confidence=payload.get("confidence", 1.0),
            scope=Scope.from_dict(payload.get("scope") or {}),
            lifecycle=Lifecycle.from_dict(payload.get("lifecycle") or {}),
            authority=Authority.from_dict(payload.get("authority") or {}),
            valence=Valence.from_dict(payload.get("valence") or {}),
            applicability=Applicability.from_dict(payload.get("applicability") or {}),
            evidence_links=tuple(EvidenceLink.from_dict(item) for item in payload.get("evidence_links") or ()),
            invalidators=tuple(Invalidator.from_dict(item) for item in payload.get("invalidators") or ()),
            staleness_state=payload.get("staleness_state", StalenessState.FRESH.value),
            contradiction_state=payload.get("contradiction_state", ContradictionState.NONE.value),
            approval_state=payload.get("approval_state", ApprovalState.PROPOSAL.value),
            projection_mode=payload.get("projection_mode", ProjectionMode.DEBUG_ONLY.value),
            retrieval_terms=tuple(payload.get("retrieval_terms") or ()),
            graph_refs=GraphRefs.from_dict(payload.get("graph_refs") or {}),
            privacy=PrivacyRules.from_dict(payload.get("privacy") or {}),
            timestamps=MemoryTimestamps.from_dict(payload.get("timestamps") or {}),
            revision=MemoryRevision.from_dict(payload.get("revision") or {}),
            audit=MemoryAuditFields.from_dict(payload.get("audit") or {}),
            metadata=payload.get("metadata") or {},
        )

    def canonical_json(self) -> str:
        return stable_json(self.to_dict())

    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


def _normalize_memory_card_payload(
    data: Mapping[str, Any], *, migrate_retired_projection: bool
) -> dict[str, Any]:
    payload = dict(data)
    _validate_schema_version(payload.get("schema_version", MEMORY_CARD_SCHEMA_VERSION), "memory_card")
    if "state" in payload:
        raise ValueError("stored MemoryCard schema must not include ambiguous state/MemoryState")
    if "projection" in payload:
        if not migrate_retired_projection:
            raise ValueError("retired projection/ProjectionPolicy must be migrated before hashing")
        if "projection_mode" in payload and payload["projection_mode"] != payload["projection"]:
            raise ValueError("cannot migrate conflicting projection and projection_mode values")
        payload["projection_mode"] = payload.pop("projection")
    return payload


def migrate_retired_memory_card_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a payload with retired projection naming migrated before hashing."""

    return _normalize_memory_card_payload(data, migrate_retired_projection=True)


@dataclass(frozen=True)
class ProvenanceRef:
    ref_id: str
    event_kind: str
    artifact_path_or_uri: str | None
    content_hash: str
    excerpt_hash: str | None
    timestamp: str
    producer: str
    scope: Scope
    redaction_state: str = RedactionState.NONE.value
    source_experience_id: str | None = None
    source_mutation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _text(self.ref_id, allow_empty=False, field_name="provenance_ref.ref_id"))
        object.__setattr__(self, "event_kind", _enum_value(RawEventKind, self.event_kind, "provenance_ref.event_kind"))
        object.__setattr__(self, "artifact_path_or_uri", _optional_text(self.artifact_path_or_uri))
        object.__setattr__(self, "content_hash", _text(self.content_hash, allow_empty=False, field_name="provenance_ref.content_hash"))
        object.__setattr__(self, "excerpt_hash", _optional_text(self.excerpt_hash))
        object.__setattr__(self, "timestamp", _text(self.timestamp, allow_empty=False, field_name="provenance_ref.timestamp"))
        object.__setattr__(self, "producer", _enum_value(ProvenanceProducer, self.producer, "provenance_ref.producer"))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(self, "redaction_state", _enum_value(RedactionState, self.redaction_state, "provenance_ref.redaction_state"))
        object.__setattr__(self, "source_experience_id", _optional_text(self.source_experience_id))
        object.__setattr__(self, "source_mutation_id", _optional_text(self.source_mutation_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "event_kind": self.event_kind,
            "artifact_path_or_uri": self.artifact_path_or_uri,
            "content_hash": self.content_hash,
            "excerpt_hash": self.excerpt_hash,
            "timestamp": self.timestamp,
            "producer": self.producer,
            "scope": self.scope.to_dict(),
            "redaction_state": self.redaction_state,
            "source_experience_id": self.source_experience_id,
            "source_mutation_id": self.source_mutation_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceRef":
        return cls(
            ref_id=data.get("ref_id"),
            event_kind=data.get("event_kind"),
            artifact_path_or_uri=data.get("artifact_path_or_uri"),
            content_hash=data.get("content_hash"),
            excerpt_hash=data.get("excerpt_hash"),
            timestamp=data.get("timestamp"),
            producer=data.get("producer"),
            scope=Scope.from_dict(data.get("scope") or {}),
            redaction_state=data.get("redaction_state", RedactionState.NONE.value),
            source_experience_id=data.get("source_experience_id"),
            source_mutation_id=data.get("source_mutation_id"),
        )


@dataclass(frozen=True)
class ProvenanceEvent:
    event_id: str
    event_kind: str
    actor: str
    scope: Scope
    payload_hash: str
    created_at: str
    schema_version: str = PROVENANCE_EVENT_SCHEMA_VERSION
    payload_ref: str | None = None
    provenance_excerpt: str | None = None
    content_mime: str | None = None
    source_run_id: str | None = None
    source_session_id: str | None = None
    source_turn_id: str | None = None
    source_experience_id: str | None = None
    source_mutation_id: str | None = None
    redaction_state: str = RedactionState.NONE.value
    retention_state: str = RetentionState.ACTIVE.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _validate_schema_version(self.schema_version, "provenance_event"))
        object.__setattr__(self, "event_id", _text(self.event_id, allow_empty=False, field_name="event_id"))
        object.__setattr__(self, "event_kind", _enum_value(RawEventKind, self.event_kind, "event_kind"))
        object.__setattr__(self, "actor", _enum_value(ProvenanceProducer, self.actor, "provenance_event.actor"))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(self, "payload_hash", _text(self.payload_hash, allow_empty=False, field_name="payload_hash"))
        object.__setattr__(self, "created_at", _text(self.created_at, allow_empty=False, field_name="created_at"))
        for name in (
            "payload_ref",
            "provenance_excerpt",
            "content_mime",
            "source_run_id",
            "source_session_id",
            "source_turn_id",
            "source_experience_id",
            "source_mutation_id",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        redaction_state = _enum_value(RedactionState, self.redaction_state, "redaction_state")
        if self.provenance_excerpt and len(self.provenance_excerpt) > MAX_PROVENANCE_EXCERPT_CHARS:
            raise ValueError(f"provenance_excerpt must be <= {MAX_PROVENANCE_EXCERPT_CHARS} chars")
        if redaction_state == RedactionState.RESTRICTED.value and self.provenance_excerpt:
            raise ValueError("restricted provenance events must not inline provenance_excerpt")
        object.__setattr__(self, "redaction_state", redaction_state)
        object.__setattr__(self, "retention_state", _enum_value(RetentionState, self.retention_state, "retention_state"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "event_kind": self.event_kind,
            "actor": self.actor,
            "scope": self.scope.to_dict(),
            "payload_ref": self.payload_ref,
            "provenance_excerpt": self.provenance_excerpt,
            "payload_hash": self.payload_hash,
            "content_mime": self.content_mime,
            "source_run_id": self.source_run_id,
            "source_session_id": self.source_session_id,
            "source_turn_id": self.source_turn_id,
            "source_experience_id": self.source_experience_id,
            "source_mutation_id": self.source_mutation_id,
            "redaction_state": self.redaction_state,
            "retention_state": self.retention_state,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceEvent":
        return cls(
            event_id=data.get("event_id"),
            schema_version=data.get("schema_version", PROVENANCE_EVENT_SCHEMA_VERSION),
            event_kind=data.get("event_kind"),
            actor=data.get("actor"),
            scope=Scope.from_dict(data.get("scope") or {}),
            payload_ref=data.get("payload_ref"),
            provenance_excerpt=data.get("provenance_excerpt"),
            payload_hash=data.get("payload_hash"),
            content_mime=data.get("content_mime"),
            source_run_id=data.get("source_run_id"),
            source_session_id=data.get("source_session_id"),
            source_turn_id=data.get("source_turn_id"),
            source_experience_id=data.get("source_experience_id"),
            source_mutation_id=data.get("source_mutation_id"),
            redaction_state=data.get("redaction_state", RedactionState.NONE.value),
            retention_state=data.get("retention_state", RetentionState.ACTIVE.value),
            created_at=data.get("created_at"),
        )


@dataclass(frozen=True)
class ProvenanceReceipt:
    event_id: str
    event_kind: str
    producer: str
    scope: Scope
    payload_hash: str
    excerpt_hash: str | None
    source_experience_id: str | None
    source_mutation_id: str | None
    redaction_state: str
    retention_state: str
    audit_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text(self.event_id, allow_empty=False, field_name="receipt.event_id"))
        object.__setattr__(self, "event_kind", _enum_value(RawEventKind, self.event_kind, "receipt.event_kind"))
        object.__setattr__(self, "producer", _enum_value(ProvenanceProducer, self.producer, "receipt.producer"))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(self, "payload_hash", _text(self.payload_hash, allow_empty=False, field_name="receipt.payload_hash"))
        object.__setattr__(self, "excerpt_hash", _optional_text(self.excerpt_hash))
        object.__setattr__(self, "source_experience_id", _optional_text(self.source_experience_id))
        object.__setattr__(self, "source_mutation_id", _optional_text(self.source_mutation_id))
        object.__setattr__(self, "redaction_state", _enum_value(RedactionState, self.redaction_state, "receipt.redaction_state"))
        object.__setattr__(self, "retention_state", _enum_value(RetentionState, self.retention_state, "receipt.retention_state"))
        object.__setattr__(self, "audit_id", _text(self.audit_id, allow_empty=False, field_name="receipt.audit_id"))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    scope: Scope
    scope_key: str
    canonical_ref: str
    display_name: str
    content_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    staleness_state: str = StalenessState.FRESH.value
    created_at: str = ""
    updated_at: str = ""
    schema_version: str = GRAPH_NODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _validate_schema_version(self.schema_version, "graph_node"))
        node_type = _enum_value(NodeType, self.node_type, "graph_node.node_type")
        scope = self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope)
        scope_key = _text(self.scope_key, allow_empty=False, field_name="graph_node.scope_key")
        canonical_ref = _text(self.canonical_ref, allow_empty=False, field_name="graph_node.canonical_ref")
        expected_scope_key = scope.scope_key()
        if scope_key != expected_scope_key:
            raise ValueError("graph_node.scope_key must derive from canonical Scope JSON")
        expected_node_id = make_node_id_v1(node_type, scope_key, canonical_ref)
        node_id = _text(self.node_id, allow_empty=False, field_name="graph_node.node_id")
        if node_id != expected_node_id:
            raise ValueError("graph_node.node_id must match NodeIdV1 canonicalization")
        parsed = parse_node_id_v1(node_id)
        if parsed.node_type != node_type or parsed.scope_key != scope_key or parsed.canonical_ref != canonical_ref:
            raise ValueError("graph_node.node_id does not match structured identity")
        metadata = _plain(self.metadata)
        if node_type == NodeType.ACTOR.value:
            actor_kind = metadata.get("actor_kind")
            metadata["actor_kind"] = _enum_value(ActorKind, actor_kind, "graph_node.metadata.actor_kind")
        object.__setattr__(self, "node_type", node_type)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "scope_key", scope_key)
        object.__setattr__(self, "canonical_ref", canonical_ref)
        object.__setattr__(self, "display_name", _text(self.display_name, allow_empty=True, field_name="graph_node.display_name"))
        object.__setattr__(self, "content_hash", _optional_text(self.content_hash))
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "staleness_state", _enum_value(StalenessState, self.staleness_state, "graph_node.staleness_state"))
        object.__setattr__(self, "created_at", _text(self.created_at, allow_empty=False, field_name="graph_node.created_at"))
        object.__setattr__(self, "updated_at", _text(self.updated_at, allow_empty=False, field_name="graph_node.updated_at"))

    @classmethod
    def build(
        cls,
        *,
        node_type: str,
        scope: Scope,
        canonical_ref: str,
        display_name: str = "",
        content_hash: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        staleness_state: str = StalenessState.FRESH.value,
        created_at: str,
        updated_at: str,
    ) -> "GraphNode":
        scope_key = scope.scope_key()
        node_type_value = _enum_value(NodeType, node_type, "graph_node.node_type")
        canonical_ref_text = _text(canonical_ref, allow_empty=False, field_name="graph_node.canonical_ref")
        return cls(
            node_id=make_node_id_v1(node_type_value, scope_key, canonical_ref_text),
            node_type=node_type_value,
            scope=scope,
            scope_key=scope_key,
            canonical_ref=canonical_ref_text,
            display_name=display_name,
            content_hash=content_hash,
            metadata=metadata or {},
            staleness_state=staleness_state,
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "schema_version": self.schema_version,
            "node_type": self.node_type,
            "scope": self.scope.to_dict(),
            "scope_key": self.scope_key,
            "canonical_ref": self.canonical_ref,
            "display_name": self.display_name,
            "content_hash": self.content_hash,
            "metadata": _plain(self.metadata),
            "staleness_state": self.staleness_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphNode":
        return cls(
            node_id=data.get("node_id"),
            schema_version=data.get("schema_version", GRAPH_NODE_SCHEMA_VERSION),
            node_type=data.get("node_type"),
            scope=Scope.from_dict(data.get("scope") or {}),
            scope_key=data.get("scope_key"),
            canonical_ref=data.get("canonical_ref"),
            display_name=data.get("display_name", ""),
            content_hash=data.get("content_hash"),
            metadata=data.get("metadata") or {},
            staleness_state=data.get("staleness_state", StalenessState.FRESH.value),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


def pseudonymous_actor_ref(actor_kind: str, source_identifier: str, *, scope_key: str | None = None) -> str:
    kind = _enum_value(ActorKind, actor_kind, "actor_kind")
    source = _text(source_identifier, allow_empty=False, field_name="source_identifier")
    scope_text = _optional_text(scope_key) or ""
    digest = hashlib.sha256(stable_json({"actor_kind": kind, "scope_key": scope_text, "source": source}).encode("utf-8")).hexdigest()[:16]
    return f"actor:{kind}:{digest}"


_ACTOR_LINEAGE_EDGE_ROLES = {
    GraphEdgeType.APPROVED_BY.value: {EvidenceRole.APPROVAL.value, EvidenceRole.REVIEWER_CONTEXT.value},
    GraphEdgeType.REVIEWED_BY.value: {EvidenceRole.APPROVAL.value, EvidenceRole.REVIEWER_CONTEXT.value},
    GraphEdgeType.VETOED_BY.value: {EvidenceRole.APPROVAL.value, EvidenceRole.REVIEWER_CONTEXT.value},
    GraphEdgeType.SEED_EVAL_BY.value: {EvidenceRole.LINEAGE.value, EvidenceRole.DEBUG.value},
    GraphEdgeType.MIGRATED_BY.value: {EvidenceRole.LINEAGE.value, EvidenceRole.DEBUG.value},
}
_SUPPORT_EDGE_ROLES = {
    GraphEdgeType.SUPPORTS.value: {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value},
    GraphEdgeType.PROVED_BY.value: {EvidenceRole.CURRENT_SUPPORT.value, EvidenceRole.PROOF.value},
}


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    from_node_id: str
    from_node_type: str
    to_node_id: str
    to_node_type: str
    edge_type: str
    scope: Scope
    evidence_links: tuple[EvidenceLink, ...]
    confidence: float = 1.0
    staleness_state: str = StalenessState.FRESH.value
    created_at: str = ""
    updated_at: str = ""
    schema_version: str = GRAPH_EDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _validate_schema_version(self.schema_version, "graph_edge"))
        from_type = _enum_value(NodeType, self.from_node_type, "graph_edge.from_node_type")
        to_type = _enum_value(NodeType, self.to_node_type, "graph_edge.to_node_type")
        from_node = parse_node_id_v1(self.from_node_id)
        to_node = parse_node_id_v1(self.to_node_id)
        if from_node.node_type != from_type:
            raise ValueError("from_node_id type must match from_node_type")
        if to_node.node_type != to_type:
            raise ValueError("to_node_id type must match to_node_type")
        object.__setattr__(self, "from_node_type", from_type)
        object.__setattr__(self, "to_node_type", to_type)
        object.__setattr__(self, "edge_type", _enum_value(GraphEdgeType, self.edge_type, "graph_edge.edge_type"))
        object.__setattr__(self, "scope", self.scope if isinstance(self.scope, Scope) else Scope.from_dict(self.scope))
        object.__setattr__(self, "evidence_links", _tuple_of(EvidenceLink, self.evidence_links, "graph_edge.evidence_links"))
        self._validate_edge_type_rules()
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence, "graph_edge.confidence"))
        object.__setattr__(self, "staleness_state", _enum_value(StalenessState, self.staleness_state, "graph_edge.staleness_state"))
        object.__setattr__(self, "created_at", _text(self.created_at, allow_empty=False, field_name="graph_edge.created_at"))
        object.__setattr__(self, "updated_at", _text(self.updated_at, allow_empty=False, field_name="graph_edge.updated_at"))
        expected_edge_id = graph_edge_id(
            from_node_id=self.from_node_id,
            to_node_id=self.to_node_id,
            edge_type=self.edge_type,
            scope_key=self.scope.scope_key(),
        )
        object.__setattr__(self, "edge_id", _text(self.edge_id, allow_empty=False, field_name="graph_edge.edge_id"))
        if self.edge_id != expected_edge_id:
            raise ValueError("graph_edge.edge_id must be deterministic from endpoints, type, and scope")

    def _validate_edge_type_rules(self) -> None:
        if self.edge_type in _ACTOR_LINEAGE_EDGE_ROLES:
            if self.to_node_type != NodeType.ACTOR.value:
                raise ValueError(f"{self.edge_type} graph edges must target node_type=actor")
            self._require_active_evidence_role(_ACTOR_LINEAGE_EDGE_ROLES[self.edge_type])
        if self.edge_type in _SUPPORT_EDGE_ROLES:
            self._require_active_evidence_role(_SUPPORT_EDGE_ROLES[self.edge_type])

    def _require_active_evidence_role(self, allowed_roles: set[str]) -> None:
        if not any(link.active and link.role in allowed_roles for link in self.evidence_links):
            allowed = ", ".join(sorted(allowed_roles))
            raise ValueError(f"{self.edge_type} graph edges require active evidence link role: {allowed}")

    @classmethod
    def build(
        cls,
        *,
        from_node_id: str,
        from_node_type: str,
        to_node_id: str,
        to_node_type: str,
        edge_type: str,
        scope: Scope,
        evidence_links: Sequence[EvidenceLink | Mapping[str, Any]],
        confidence: float = 1.0,
        staleness_state: str = StalenessState.FRESH.value,
        created_at: str,
        updated_at: str,
    ) -> "GraphEdge":
        edge_type_value = _enum_value(GraphEdgeType, edge_type, "graph_edge.edge_type")
        return cls(
            edge_id=graph_edge_id(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                edge_type=edge_type_value,
                scope_key=scope.scope_key(),
            ),
            from_node_id=from_node_id,
            from_node_type=from_node_type,
            to_node_id=to_node_id,
            to_node_type=to_node_type,
            edge_type=edge_type_value,
            scope=scope,
            evidence_links=tuple(evidence_links),
            confidence=confidence,
            staleness_state=staleness_state,
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "schema_version": self.schema_version,
            "from_node_id": self.from_node_id,
            "from_node_type": self.from_node_type,
            "to_node_id": self.to_node_id,
            "to_node_type": self.to_node_type,
            "edge_type": self.edge_type,
            "scope": self.scope.to_dict(),
            "evidence_links": [item.to_dict() for item in self.evidence_links],
            "confidence": self.confidence,
            "staleness_state": self.staleness_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def graph_edge_id(*, from_node_id: str, to_node_id: str, edge_type: str, scope_key: str) -> str:
    payload = {
        "from_node_id": _text(from_node_id, allow_empty=False, field_name="from_node_id"),
        "to_node_id": _text(to_node_id, allow_empty=False, field_name="to_node_id"),
        "edge_type": _enum_value(GraphEdgeType, edge_type, "edge_type"),
        "scope_key": _text(scope_key, allow_empty=False, field_name="scope_key"),
    }
    return f"edge:v1:{stable_short_hash(payload, length=16)}"


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    proposed_kind: str
    summary: str
    details: str | None
    evidence_links: tuple[EvidenceLink, ...]
    proposed_scope: Scope
    proposed_authority: Authority
    proposed_valence: Valence
    proposed_applicability: Applicability
    proposed_invalidators: tuple[Invalidator, ...]
    confidence: float
    write_reason: str
    proposed_by: str
    retrieval_terms: tuple[str, ...] = ()
    proposed_graph_refs: GraphRefs = field(default_factory=GraphRefs)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, allow_empty=False, field_name="candidate_id"))
        object.__setattr__(self, "proposed_kind", _enum_value(MemoryCardKind, self.proposed_kind, "proposed_kind"))
        object.__setattr__(self, "summary", _text(self.summary, allow_empty=False, field_name="summary"))
        object.__setattr__(self, "details", _optional_text(self.details))
        if len(self.summary) > MAX_SUMMARY_CHARS:
            raise ValueError(f"candidate summary must be <= {MAX_SUMMARY_CHARS} chars")
        if self.details and len(self.details) > MAX_DETAILS_CHARS:
            raise ValueError(f"candidate details must be <= {MAX_DETAILS_CHARS} chars")
        object.__setattr__(self, "evidence_links", _tuple_of(EvidenceLink, self.evidence_links, "candidate.evidence_links"))
        object.__setattr__(
            self,
            "proposed_scope",
            self.proposed_scope if isinstance(self.proposed_scope, Scope) else Scope.from_dict(self.proposed_scope),
        )
        object.__setattr__(
            self,
            "proposed_authority",
            self.proposed_authority
            if isinstance(self.proposed_authority, Authority)
            else Authority.from_dict(self.proposed_authority),
        )
        object.__setattr__(
            self,
            "proposed_valence",
            self.proposed_valence if isinstance(self.proposed_valence, Valence) else Valence.from_dict(self.proposed_valence),
        )
        object.__setattr__(
            self,
            "proposed_applicability",
            self.proposed_applicability
            if isinstance(self.proposed_applicability, Applicability)
            else Applicability.from_dict(self.proposed_applicability),
        )
        object.__setattr__(
            self,
            "proposed_invalidators",
            _tuple_of(Invalidator, self.proposed_invalidators, "candidate.proposed_invalidators"),
        )
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        object.__setattr__(self, "write_reason", _text(self.write_reason, allow_empty=False, field_name="write_reason"))
        object.__setattr__(self, "proposed_by", _enum_value(CandidateProducer, self.proposed_by, "proposed_by"))
        object.__setattr__(self, "retrieval_terms", _retrieval_terms(self.retrieval_terms))
        object.__setattr__(
            self,
            "proposed_graph_refs",
            self.proposed_graph_refs
            if isinstance(self.proposed_graph_refs, GraphRefs)
            else GraphRefs.from_dict(self.proposed_graph_refs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "proposed_kind": self.proposed_kind,
            "summary": self.summary,
            "details": self.details,
            "evidence_links": [item.to_dict() for item in self.evidence_links],
            "proposed_scope": self.proposed_scope.to_dict(),
            "proposed_authority": self.proposed_authority.to_dict(),
            "proposed_valence": self.proposed_valence.to_dict(),
            "proposed_applicability": self.proposed_applicability.to_dict(),
            "proposed_invalidators": [item.to_dict() for item in self.proposed_invalidators],
            "confidence": self.confidence,
            "write_reason": self.write_reason,
            "proposed_by": self.proposed_by,
            "retrieval_terms": list(self.retrieval_terms),
            "proposed_graph_refs": self.proposed_graph_refs.to_dict(),
        }

    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class FileEvidenceState:
    node_id: str
    path: str
    state: str
    content_hash: str | None = None
    observed_at: str | None = None

    def __post_init__(self) -> None:
        parsed = parse_node_id_v1(self.node_id)
        if parsed.node_type != NodeType.FILE.value:
            raise ValueError("FileEvidenceState.node_id must identify a file node")
        object.__setattr__(self, "path", _text(self.path, allow_empty=False, field_name="file.path"))
        object.__setattr__(self, "state", _enum_value(EvidencePresenceState, self.state, "file.state"))
        object.__setattr__(self, "content_hash", _optional_text(self.content_hash))
        object.__setattr__(self, "observed_at", _optional_text(self.observed_at))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FileEvidenceState":
        return cls(
            node_id=data.get("node_id"),
            path=data.get("path"),
            state=data.get("state"),
            content_hash=data.get("content_hash"),
            observed_at=data.get("observed_at"),
        )


@dataclass(frozen=True)
class SymbolEvidenceState:
    node_id: str
    canonical_ref: str
    state: str
    content_hash: str | None = None
    moved_to: str | None = None
    observed_at: str | None = None

    def __post_init__(self) -> None:
        parsed = parse_node_id_v1(self.node_id)
        if parsed.node_type != NodeType.SYMBOL.value:
            raise ValueError("SymbolEvidenceState.node_id must identify a symbol node")
        object.__setattr__(self, "canonical_ref", _text(self.canonical_ref, allow_empty=False, field_name="symbol.canonical_ref"))
        object.__setattr__(self, "state", _enum_value(SymbolPresenceState, self.state, "symbol.state"))
        object.__setattr__(self, "content_hash", _optional_text(self.content_hash))
        object.__setattr__(self, "moved_to", _optional_text(self.moved_to))
        object.__setattr__(self, "observed_at", _optional_text(self.observed_at))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SymbolEvidenceState":
        return cls(
            node_id=data.get("node_id"),
            canonical_ref=data.get("canonical_ref"),
            state=data.get("state"),
            content_hash=data.get("content_hash"),
            moved_to=data.get("moved_to"),
            observed_at=data.get("observed_at"),
        )


@dataclass(frozen=True)
class CommandEvidenceState:
    node_id: str
    normalized_command_ref: str
    state: str
    command_hash: str | None = None
    observed_at: str | None = None

    def __post_init__(self) -> None:
        parsed = parse_node_id_v1(self.node_id)
        if parsed.node_type != NodeType.COMMAND.value:
            raise ValueError("CommandEvidenceState.node_id must identify a command node")
        object.__setattr__(
            self,
            "normalized_command_ref",
            _text(self.normalized_command_ref, allow_empty=False, field_name="command.normalized_command_ref"),
        )
        object.__setattr__(self, "state", _enum_value(CommandPresenceState, self.state, "command.state"))
        object.__setattr__(self, "command_hash", _optional_text(self.command_hash))
        object.__setattr__(self, "observed_at", _optional_text(self.observed_at))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandEvidenceState":
        return cls(
            node_id=data.get("node_id"),
            normalized_command_ref=data.get("normalized_command_ref"),
            command_hash=data.get("command_hash"),
            state=data.get("state"),
            observed_at=data.get("observed_at"),
        )


@dataclass(frozen=True)
class VerifierEvidenceResult:
    verifier_ref: str
    result_value: str
    observed_at: str
    result_hash: str | None = None
    applicability_refs: tuple[ApplicabilityRef, ...] = ()
    task_ref: str | None = None
    error_signature_refs: tuple[str, ...] = ()
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "verifier_ref", _text(self.verifier_ref, allow_empty=False, field_name="verifier_ref"))
        object.__setattr__(self, "result_value", _enum_value(VerifierResultValue, self.result_value, "verifier.result_value"))
        object.__setattr__(self, "observed_at", _text(self.observed_at, allow_empty=False, field_name="verifier.observed_at"))
        object.__setattr__(self, "result_hash", _optional_text(self.result_hash))
        object.__setattr__(self, "applicability_refs", _tuple_of(ApplicabilityRef, self.applicability_refs, "verifier.applicability_refs"))
        object.__setattr__(self, "task_ref", _optional_text(self.task_ref))
        object.__setattr__(self, "error_signature_refs", _tuple_text(self.error_signature_refs, "verifier.error_signature_refs"))
        object.__setattr__(self, "provenance_ref", _optional_text(self.provenance_ref))

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier_ref": self.verifier_ref,
            "result_hash": self.result_hash,
            "result_value": self.result_value,
            "applicability_refs": [item.to_dict() for item in self.applicability_refs],
            "task_ref": self.task_ref,
            "error_signature_refs": list(self.error_signature_refs),
            "observed_at": self.observed_at,
            "provenance_ref": self.provenance_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerifierEvidenceResult":
        return cls(
            verifier_ref=data.get("verifier_ref"),
            result_hash=data.get("result_hash"),
            result_value=data.get("result_value"),
            applicability_refs=tuple(data.get("applicability_refs") or ()),
            task_ref=data.get("task_ref"),
            error_signature_refs=tuple(data.get("error_signature_refs") or ()),
            observed_at=data.get("observed_at"),
            provenance_ref=data.get("provenance_ref"),
        )


@dataclass(frozen=True)
class TaskContractEvidence:
    ref: str
    observed_at: str
    hash: str | None = None
    value: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _text(self.ref, allow_empty=False, field_name="task_contract.ref"))
        object.__setattr__(self, "observed_at", _text(self.observed_at, allow_empty=False, field_name="task_contract.observed_at"))
        object.__setattr__(self, "hash", _optional_text(self.hash))
        object.__setattr__(self, "value", _optional_text(self.value))

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskContractEvidence":
        return cls(ref=data.get("ref"), hash=data.get("hash"), value=data.get("value"), observed_at=data.get("observed_at"))


@dataclass(frozen=True)
class AuthorityEvidenceEvent:
    ref: str
    source: str
    strength: str
    target_scope: Scope
    observed_at: str
    supersedes_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _text(self.ref, allow_empty=False, field_name="authority_event.ref"))
        object.__setattr__(self, "source", _enum_value(CurrentAuthoritySource, self.source, "authority_event.source"))
        object.__setattr__(self, "strength", _enum_value(AuthorityStrength, self.strength, "authority_event.strength"))
        object.__setattr__(
            self,
            "target_scope",
            self.target_scope if isinstance(self.target_scope, Scope) else Scope.from_dict(self.target_scope),
        )
        object.__setattr__(self, "observed_at", _text(self.observed_at, allow_empty=False, field_name="authority_event.observed_at"))
        object.__setattr__(self, "supersedes_refs", _tuple_text(self.supersedes_refs, "authority_event.supersedes_refs"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "source": self.source,
            "strength": self.strength,
            "target_scope": self.target_scope.to_dict(),
            "observed_at": self.observed_at,
            "supersedes_refs": list(self.supersedes_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorityEvidenceEvent":
        return cls(
            ref=data.get("ref"),
            source=data.get("source"),
            strength=data.get("strength"),
            target_scope=Scope.from_dict(data.get("target_scope") or {}),
            observed_at=data.get("observed_at"),
            supersedes_refs=tuple(data.get("supersedes_refs") or ()),
        )


@dataclass(frozen=True)
class CurrentEvidenceSnapshot:
    repo_ref: str | None = None
    branch_ref: str | None = None
    commit_ref: str | None = None
    file_states: tuple[FileEvidenceState, ...] = ()
    symbol_states: tuple[SymbolEvidenceState, ...] = ()
    command_states: tuple[CommandEvidenceState, ...] = ()
    verifier_results: tuple[VerifierEvidenceResult, ...] = ()
    task_contract: TaskContractEvidence | None = None
    authority_events: tuple[AuthorityEvidenceEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_ref", _optional_text(self.repo_ref))
        object.__setattr__(self, "branch_ref", _optional_text(self.branch_ref))
        object.__setattr__(self, "commit_ref", _optional_text(self.commit_ref))
        object.__setattr__(self, "file_states", _tuple_of(FileEvidenceState, self.file_states, "file_states"))
        object.__setattr__(self, "symbol_states", _tuple_of(SymbolEvidenceState, self.symbol_states, "symbol_states"))
        object.__setattr__(self, "command_states", _tuple_of(CommandEvidenceState, self.command_states, "command_states"))
        object.__setattr__(self, "verifier_results", _tuple_of(VerifierEvidenceResult, self.verifier_results, "verifier_results"))
        if self.task_contract is not None and not isinstance(self.task_contract, TaskContractEvidence):
            object.__setattr__(self, "task_contract", TaskContractEvidence.from_dict(self.task_contract))
        object.__setattr__(self, "authority_events", _tuple_of(AuthorityEvidenceEvent, self.authority_events, "authority_events"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_ref": self.repo_ref,
            "branch_ref": self.branch_ref,
            "commit_ref": self.commit_ref,
            "file_states": [item.to_dict() for item in self.file_states],
            "symbol_states": [item.to_dict() for item in self.symbol_states],
            "command_states": [item.to_dict() for item in self.command_states],
            "verifier_results": [item.to_dict() for item in self.verifier_results],
            "task_contract": self.task_contract.to_dict() if self.task_contract else None,
            "authority_events": [item.to_dict() for item in self.authority_events],
        }


@dataclass(frozen=True)
class DroppedReason:
    reason: str
    ref_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _text(self.reason, allow_empty=False, field_name="dropped.reason"))
        object.__setattr__(self, "ref_id", _optional_text(self.ref_id))
        detail = _optional_text(self.detail)
        if detail and len(detail) > 256:
            digest = hashlib.sha256(detail.encode("utf-8")).hexdigest()[:12]
            detail = detail[:236] + "#sha256:" + digest
        object.__setattr__(self, "detail", detail)

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "ref_id": self.ref_id, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DroppedReason":
        return cls(reason=data.get("reason"), ref_id=data.get("ref_id"), detail=data.get("detail"))


_RAW_AUDIT_METADATA_KEYS = {
    "raw_text",
    "raw_transcript",
    "command_output",
    "tool_output",
    "full_diff",
    "full_context_packet",
    "projected_packet",
}


def _bounded_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _plain(value)
    _reject_raw_audit_metadata(normalized)
    encoded = stable_json(normalized).encode("utf-8")
    if len(encoded) <= 8192:
        return normalized
    digest = hashlib.sha256(encoded).hexdigest()
    return {
        "metadata_truncated": True,
        "metadata_hash": "sha256:" + digest,
        "metadata_prefix": stable_json(normalized)[:512],
    }


def _reject_raw_audit_metadata(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = _nfc(key)
            if key_text in _RAW_AUDIT_METADATA_KEYS and isinstance(child, str) and len(child) > MAX_PROVENANCE_EXCERPT_CHARS:
                raise ValueError("audit metadata must reference raw payloads by provenance id/hash, not inline them")
            _reject_raw_audit_metadata(child)
    elif isinstance(value, list):
        for item in value:
            _reject_raw_audit_metadata(item)


@dataclass(frozen=True)
class MemoryTraceEvent:
    operation: str
    request_hash: str
    result_hash: str
    actor: str
    card_ids: tuple[str, ...] = ()
    provenance_event_ids: tuple[str, ...] = ()
    mutation_ids: tuple[str, ...] = ()
    dropped: tuple[DroppedReason, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", _enum_value(MemoryTraceOperation, self.operation, "trace.operation"))
        object.__setattr__(self, "request_hash", _text(self.request_hash, allow_empty=False, field_name="trace.request_hash"))
        object.__setattr__(self, "result_hash", _text(self.result_hash, allow_empty=False, field_name="trace.result_hash"))
        object.__setattr__(self, "actor", _enum_value(TraceActor, self.actor, "trace.actor"))
        object.__setattr__(self, "card_ids", tuple(sorted(_tuple_text(self.card_ids, "trace.card_ids"))))
        object.__setattr__(
            self,
            "provenance_event_ids",
            tuple(sorted(_tuple_text(self.provenance_event_ids, "trace.provenance_event_ids"))),
        )
        object.__setattr__(self, "mutation_ids", tuple(sorted(_tuple_text(self.mutation_ids, "trace.mutation_ids"))))
        object.__setattr__(self, "dropped", _tuple_of(DroppedReason, self.dropped, "trace.dropped"))
        object.__setattr__(self, "usage", _plain(self.usage))
        object.__setattr__(self, "metadata", _bounded_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "actor": self.actor,
            "card_ids": list(self.card_ids),
            "provenance_event_ids": list(self.provenance_event_ids),
            "mutation_ids": list(self.mutation_ids),
            "dropped": [item.to_dict() for item in self.dropped],
            "usage": _plain(self.usage),
            "metadata": _plain(self.metadata),
        }


@dataclass(frozen=True)
class MemoryAuditEvent:
    audit_id: str
    created_at: str
    operation: str
    request_hash: str
    result_hash: str
    actor: str
    card_ids: tuple[str, ...] = ()
    provenance_event_ids: tuple[str, ...] = ()
    mutation_ids: tuple[str, ...] = ()
    dropped: tuple[DroppedReason, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit_id", _text(self.audit_id, allow_empty=False, field_name="audit_id"))
        object.__setattr__(self, "created_at", _text(self.created_at, allow_empty=False, field_name="created_at"))
        trace = MemoryTraceEvent(
            operation=self.operation,
            request_hash=self.request_hash,
            result_hash=self.result_hash,
            actor=self.actor,
            card_ids=self.card_ids,
            provenance_event_ids=self.provenance_event_ids,
            mutation_ids=self.mutation_ids,
            dropped=self.dropped,
            usage=self.usage,
            metadata=self.metadata,
        )
        for name, value in trace.to_dict().items():
            if name in {"dropped", "usage", "metadata"}:
                continue
            object.__setattr__(self, name, tuple(value) if name.endswith("_ids") else value)
        object.__setattr__(self, "dropped", trace.dropped)
        object.__setattr__(self, "usage", trace.usage)
        object.__setattr__(self, "metadata", trace.metadata)

    @classmethod
    def from_trace(cls, trace: MemoryTraceEvent, *, audit_id: str, created_at: str) -> "MemoryAuditEvent":
        return cls(audit_id=audit_id, created_at=created_at, **trace.to_dict())

    def logical_payload(self) -> dict[str, Any]:
        return MemoryTraceEvent(
            operation=self.operation,
            request_hash=self.request_hash,
            result_hash=self.result_hash,
            actor=self.actor,
            card_ids=self.card_ids,
            provenance_event_ids=self.provenance_event_ids,
            mutation_ids=self.mutation_ids,
            dropped=self.dropped,
            usage=self.usage,
            metadata=self.metadata,
        ).to_dict()

    def to_dict(self) -> dict[str, Any]:
        payload = self.logical_payload()
        payload.update({"audit_id": self.audit_id, "created_at": self.created_at})
        return payload


@dataclass(frozen=True)
class LegacyMemoryEntryMigration:
    legacy_entry_id: str
    source_kind: str
    target_kind: str | None
    quarantined: bool
    recallable: bool
    reason: str
    card: MemoryCard | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacy_entry_id": self.legacy_entry_id,
            "source_kind": self.source_kind,
            "target_kind": self.target_kind,
            "quarantined": self.quarantined,
            "recallable": self.recallable,
            "reason": self.reason,
            "card": self.card.to_dict() if self.card else None,
        }


_LEGACY_KIND_MAP = {
    "project_convention": MemoryCardKind.SEMANTIC_FACT.value,
    "episodic_task": MemoryCardKind.TASK_EPISODE.value,
    "procedural_repair": MemoryCardKind.PROCEDURE.value,
    "failure_shield": MemoryCardKind.PROCEDURE.value,
    "reviewer_correction": MemoryCardKind.SEMANTIC_FACT.value,
    "file_symbol_edge": MemoryCardKind.SEMANTIC_FACT.value,
    "user_preference": MemoryCardKind.POLICY_OR_PREFERENCE.value,
}


def migrate_legacy_memory_entry(data: Mapping[str, Any]) -> LegacyMemoryEntryMigration:
    legacy_id = _text(data.get("entry_id") or data.get("id"), allow_empty=False, field_name="legacy.entry_id")
    source_kind = _text(data.get("memory_kind") or data.get("kind"), allow_empty=False, field_name="legacy.memory_kind")
    target_kind = _LEGACY_KIND_MAP.get(source_kind)
    if target_kind is None:
        return LegacyMemoryEntryMigration(
            legacy_entry_id=legacy_id,
            source_kind=source_kind,
            target_kind=None,
            quarantined=True,
            recallable=False,
            reason="unknown legacy memory_kind",
        )
    scope_result = _migrate_legacy_scope(data.get("scope"))
    if scope_result is None:
        return LegacyMemoryEntryMigration(
            legacy_entry_id=legacy_id,
            source_kind=source_kind,
            target_kind=target_kind,
            quarantined=True,
            recallable=False,
            reason="unknown legacy scope quarantined without normal recall",
        )

    evidence_links = _legacy_evidence_links(data)
    approved = bool(data.get("approved", False)) or data.get("lifecycle_state") == ApprovalState.COMMITTED.value
    approval_state = ApprovalState.COMMITTED.value if approved and evidence_links else ApprovalState.PROPOSAL.value
    card_id = legacy_id if legacy_id.startswith("mem_") else "mem_" + stable_short_hash({"legacy_entry_id": legacy_id}, length=16)
    summary = _text(data.get("summary") or data.get("title") or data.get("name"), allow_empty=False, field_name="legacy.summary")
    details = _optional_text(data.get("details") or data.get("body"))
    created_at = _text(data.get("created_at") or "1970-01-01T00:00:00Z", allow_empty=False, field_name="legacy.created_at")
    valence = Valence(
        polarity=ValencePolarity.NEGATIVE.value if source_kind == "failure_shield" else ValencePolarity.NEUTRAL.value,
        effect=ValenceEffect.VERIFY.value if source_kind == "failure_shield" else ValenceEffect.USE.value,
    )
    authority_source = AuthoritySource.SELF.value
    authority_strength = AuthorityStrength.OBSERVATION.value
    if source_kind == "reviewer_correction":
        authority_source = AuthoritySource.REVIEWER.value
        authority_strength = AuthorityStrength.SHOULD.value
    elif source_kind == "user_preference":
        authority_source = AuthoritySource.USER.value
        authority_strength = AuthorityStrength.SHOULD.value

    applicability = _legacy_applicability(data.get("applicability"), scope_result)
    card = MemoryCard(
        card_id=card_id,
        kind=target_kind,
        summary=summary,
        details=details,
        confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
        scope=scope_result,
        lifecycle=Lifecycle(lifespan=LifecycleLifespan.PROJECT_DURABLE.value),
        authority=Authority(source=authority_source, strength=authority_strength),
        valence=valence,
        applicability=applicability,
        evidence_links=evidence_links,
        invalidators=(),
        staleness_state=StalenessState.FRESH.value,
        contradiction_state=ContradictionState.NONE.value,
        approval_state=approval_state,
        projection_mode=ProjectionMode.DEBUG_ONLY.value,
        graph_refs=GraphRefs(),
        privacy=PrivacyRules(allowed_scope_ids=(scope_result.scope_key(),)),
        timestamps=MemoryTimestamps(created_at=created_at, updated_at=created_at, last_verified_at=data.get("last_verified_at")),
        revision=MemoryRevision(supersedes=(legacy_id,) if card_id != legacy_id else ()),
        audit=MemoryAuditFields(
            created_by=TraceActor.MIGRATION.value,
            write_reason="legacy MemoryEntry deterministic migration",
            create_audit_id="audit_" + stable_short_hash({"legacy_entry_id": legacy_id, "operation": "migrate"}, length=16),
        ),
        metadata={"legacy_entry_id": legacy_id, "legacy_memory_kind": source_kind},
    )
    return LegacyMemoryEntryMigration(
        legacy_entry_id=legacy_id,
        source_kind=source_kind,
        target_kind=target_kind,
        quarantined=False,
        recallable=card.approval_state == ApprovalState.COMMITTED.value,
        reason="migrated",
        card=card,
    )


def _migrate_legacy_scope(value: Any) -> Scope | None:
    text = _optional_text(value)
    if not text:
        return None
    branch_match = re.fullmatch(r"repo:([^@]+)@branch:(.+)", text)
    if branch_match:
        repo_ref = branch_match.group(1)
        branch_ref = branch_match.group(2)
        return Scope(level=ScopeLevel.BRANCH.value, namespace=text, repo_ref=repo_ref, branch_ref=branch_ref)
    repo_match = re.fullmatch(r"repo:(.+)", text)
    if repo_match:
        return Scope(level=ScopeLevel.REPO.value, namespace=text, repo_ref=repo_match.group(1))
    task_match = re.fullmatch(r"task:(.+)", text)
    if task_match:
        return Scope(level=ScopeLevel.TASK.value, namespace=text, task_ref=task_match.group(1))
    arena_match = re.fullmatch(r"memoryarena:([^:]+):(.+)", text)
    if arena_match:
        return Scope(
            level=ScopeLevel.TASK.value,
            namespace=text,
            task_family=arena_match.group(1),
            task_ref=arena_match.group(2),
        )
    user_match = re.fullmatch(r"private/user:(.+)", text)
    if user_match:
        return Scope(level=ScopeLevel.USER.value, namespace=f"user:{user_match.group(1)}", user_id=user_match.group(1))
    team_match = re.fullmatch(r"shared/team:(.+)", text)
    if team_match:
        return Scope(level=ScopeLevel.TEAM.value, namespace=text)
    return None


def _legacy_evidence_links(data: Mapping[str, Any]) -> tuple[EvidenceLink, ...]:
    links: list[EvidenceLink] = []
    for item in data.get("source_refs") or ():
        ref_id = _legacy_ref_id(item)
        if ref_id:
            links.append(EvidenceLink(ref_id=ref_id, role=EvidenceRole.CURRENT_SUPPORT.value))
    for item in data.get("proof_refs") or ():
        ref_id = _legacy_ref_id(item)
        if ref_id:
            links.append(EvidenceLink(ref_id=ref_id, role=EvidenceRole.PROOF.value))
    return tuple(links)


def _legacy_ref_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _optional_text(value.get("ref_id"))
    return _optional_text(getattr(value, "ref_id", None))


def _legacy_applicability(value: Any, scope: Scope) -> Applicability:
    text = _optional_text(value)
    refs = [f"scope:v1:{scope.level}:{scope.scope_key().split(':')[-1]}"]
    if text:
        digest = hashlib.sha256(_nfc(text).encode("utf-8")).hexdigest()[:12]
        slug = re.sub(r"[^a-z0-9._-]+", "-", text.casefold()).strip("-")[:32] or "legacy"
        refs.append(f"text:{digest}:{slug}")
    return Applicability(applies_to=tuple(refs))
