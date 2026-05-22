"""Typed-card adapter for memory-eval conformance fixtures."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from ..adapter_contract import adapter_manifest, default_capabilities, default_usage
from ...memory_typed_card_core import (
    MemoryMutation,
    MemoryRecallRequest,
    ModelAuthLoader,
    ModelJsonCaller,
    ModelRawMemoryExtractor,
    ModelStructuredJsonCaller,
    TypedMemoryCore,
)
from ...memory_typed_cards import (
    ApprovalState,
    CandidateProducer,
    ProvenanceEvent,
    ProvenanceProducer,
    RawMemoryExtractorConfig,
    RawMemoryIngestRequest,
    Scope,
    ScopeLevel,
    TraceActor,
)


SETUP_POLICY = "explicit_mutate_lifecycle"
LIFECYCLE_TYPES = {"seed_eval", "approve", "commit"}
TERMINAL_MUTATIONS = {"delete", "forget", "tombstone"}
ExtractorMode = Literal["deterministic_replay", "live_model"]
EXTRACTOR_MODE_DETERMINISTIC_REPLAY = "deterministic_replay"
EXTRACTOR_MODE_LIVE_MODEL = "live_model"
SUPPORTED_EXTRACTOR_MODES = {
    EXTRACTOR_MODE_DETERMINISTIC_REPLAY,
    EXTRACTOR_MODE_LIVE_MODEL,
}
RawExtractorLike = Callable[[RawMemoryIngestRequest, ProvenanceEvent, Scope], Mapping[str, Any]]


class TypedCardsMemoryEvalAdapter:
    """Memory-eval adapter backed by the typed-card Phase B core."""

    def __init__(
        self,
        *,
        extractor_mode: ExtractorMode = EXTRACTOR_MODE_DETERMINISTIC_REPLAY,
        extractor_config: RawMemoryExtractorConfig | Mapping[str, Any] | None = None,
        model_auth: Mapping[str, Any] | None = None,
        load_auth: ModelAuthLoader | None = None,
        call_json: ModelJsonCaller | None = None,
        call_structured_json: ModelStructuredJsonCaller | None = None,
        timeout: int = 120,
    ) -> None:
        if extractor_mode not in SUPPORTED_EXTRACTOR_MODES:
            raise ValueError(f"unsupported typed-card extractor_mode: {extractor_mode}")
        self.extractor_mode = extractor_mode
        self.extractor_config = _coerce_extractor_config(extractor_config)
        self.model_auth = model_auth
        self.load_auth = load_auth
        self.call_json = call_json
        self.call_structured_json = call_structured_json
        self.timeout = int(timeout or 120)
        self.evaluation_time = "2026-05-21T00:00:00Z"
        self.core = self._new_core()
        self.experiences: dict[str, dict[str, Any]] = {}
        self.provenance_by_experience: dict[str, list[str]] = {}
        self.proposals_by_experience: dict[str, list[str]] = {}

    @classmethod
    def live_model(
        cls,
        *,
        extractor_config: RawMemoryExtractorConfig | Mapping[str, Any] | None = None,
        model_auth: Mapping[str, Any] | None = None,
        load_auth: ModelAuthLoader | None = None,
        call_json: ModelJsonCaller | None = None,
        call_structured_json: ModelStructuredJsonCaller | None = None,
        timeout: int = 120,
    ) -> "TypedCardsMemoryEvalAdapter":
        return cls(
            extractor_mode=EXTRACTOR_MODE_LIVE_MODEL,
            extractor_config=extractor_config,
            model_auth=model_auth,
            load_auth=load_auth,
            call_json=call_json,
            call_structured_json=call_structured_json,
            timeout=timeout,
        )

    def manifest(self) -> dict[str, Any]:
        manifest = adapter_manifest(
            adapter_id="mew_typed_cards_memory_eval",
            adapter_version="0.3.1",
            memory_implementation_id="mew_typed_cards_phase_b",
            capability_tier="mutable_retrieval",
            capabilities=default_capabilities(
                update=True,
                delete=True,
                forget=True,
                supersede=True,
                scope_enforcement=True,
                latency_reporting=True,
            ),
        )
        manifest["setup_routing"] = "mutate_lifecycle"
        manifest["setup_policy"] = SETUP_POLICY
        manifest["extractor"] = self._extractor_manifest()
        manifest["external_model_ids"] = list(manifest["extractor"]["external_model_ids"])
        manifest["capabilities"]["seed_eval"] = True
        return manifest

    def reset(self, run: Mapping[str, Any]) -> dict[str, Any]:
        self.evaluation_time = _normalize_effective_time(run.get("evaluation_time")) or self.evaluation_time
        self.core = self._new_core()
        self.experiences = {}
        self.provenance_by_experience = {}
        self.proposals_by_experience = {}
        return {
            "status": "success",
            "fixture_id": run.get("fixture_id"),
            "seeded_during_reset": False,
            "failures": [],
        }

    def ingest(self, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [self._ingest_one(item) for item in items]

    def mutate(self, ops: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for op in ops:
            lifecycle_type = _lifecycle_type(op)
            if lifecycle_type:
                receipts.append(self._mutate_lifecycle(op, lifecycle_type))
            else:
                receipts.append(self._mutate_runtime(op))
        return receipts

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        scope = self._scope_from_public(str(query.get("scope_id") or ""))
        budget = query.get("budget") if isinstance(query.get("budget"), Mapping) else {}
        limit = int(query.get("k") or 5)
        if budget.get("max_evidence_items") is not None:
            limit = min(limit, int(budget.get("max_evidence_items")))
        result = self.core.retrieve(
            MemoryRecallRequest(
                query=_query_text(query),
                scope=scope,
                limit=limit,
                now=_optional_str((query.get("filters") or {}).get("valid_at") if isinstance(query.get("filters"), Mapping) else None),
                latency_source="deterministic_mock",
                request_id=_optional_str(query.get("request_id")),
            )
        )
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": [
                self._ranked_item_to_harness(item.to_dict()) for item in result.ranked_evidence
            ],
            "abstained": result.abstained,
            "abstained_reason": result.abstained_reason,
            "dropped": [item.to_dict() for item in result.dropped],
            "usage": _usage_to_harness(result.usage.to_dict()),
            "failures": [],
        }

    def report_usage(self, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _usage_to_harness(self.core.report_usage().usage.to_dict())

    def _new_core(self) -> TypedMemoryCore:
        return TypedMemoryCore(
            extractor=self._extractor(),
            extractor_config=self.extractor_config,
            clock=_DeterministicClock(self.evaluation_time),
        )

    def _extractor(self) -> RawExtractorLike:
        if self.extractor_mode == EXTRACTOR_MODE_LIVE_MODEL:
            return ModelRawMemoryExtractor(
                config=self.extractor_config,
                model_auth=self.model_auth,
                timeout=self.timeout,
                call_json=self.call_json,
                call_structured_json=self.call_structured_json,
                load_auth=self.load_auth,
            )
        return _deterministic_replay_extractor

    def _extractor_manifest(self) -> dict[str, Any]:
        live = self.extractor_mode == EXTRACTOR_MODE_LIVE_MODEL
        return {
            "mode": self.extractor_mode,
            "live_llm": live,
            "backend": self.extractor_config.backend,
            "model": self.extractor_config.model,
            "auth_path": self.extractor_config.auth_path,
            "call_interface": self.extractor_config.call_interface,
            "external_model_ids": [f"{self.extractor_config.backend}:{self.extractor_config.model}"] if live else [],
        }

    def _ingest_one(self, item: Mapping[str, Any]) -> dict[str, Any]:
        experience_id = str(item.get("experience_id") or "")
        self.experiences[experience_id] = dict(item)
        scope = self._scope_from_public(str(item.get("scope_id") or ""))
        try:
            result = self.core.ingest_raw(
                RawMemoryIngestRequest(_experience_text(item)),
                scope=scope,
                actor=ProvenanceProducer.USER.value,
                source_experience_id=experience_id,
                source_session_id=_optional_str(item.get("session_id")),
                source_turn_id=_optional_str(item.get("turn_id")),
            )
        except Exception as exc:
            return _receipt(
                status="failed",
                status_reason="ingest_failed",
                experience_id=experience_id,
                failures=[{"message": str(exc)}],
            )
        self._remember_provenance(result.provenance_event)
        if result.proposal_card is not None:
            self._remember_proposal(experience_id, result.proposal_card)
        status_reason = {
            "proposal": "proposed",
            "candidate": "proposed",
            "low_confidence_proposal": "low_confidence_proposal",
            "rejected": "rejected",
            "clarification_needed": "clarification_needed",
        }.get(result.status, result.status)
        return _receipt(
            status="success",
            status_reason=status_reason,
            experience_id=experience_id,
            provenance_event_ids=[result.provenance_event.event_id],
            proposal_ids=[result.proposal_card.card_id] if result.proposal_card else [],
            card_ids=[],
            audit_ids=[event.audit_id for event in result.audit_events],
            dropped=[item.to_dict() for item in result.dropped],
        )

    def _mutate_lifecycle(self, op: Mapping[str, Any], lifecycle_type: str) -> dict[str, Any]:
        experience_ids = _target_experience_ids(op)
        if not experience_ids:
            return _receipt(status="failed", status_reason="missing_lifecycle_experience_id")
        effective_time = _normalize_effective_time(op.get("effective_time"))
        if op.get("effective_time") and effective_time is None:
            return _receipt(status="failed", status_reason="invalid_effective_time")
        snapshot = self.core._snapshot_state()
        try:
            if lifecycle_type == "seed_eval":
                cards = self._proposal_cards(experience_ids)
                results = [
                    self.core.seed_committed_card_for_eval(
                        card,
                        actor=TraceActor.ADAPTER.value,
                        public_operation_id=str(op.get("op_id") or "seed_eval"),
                        source_experience_id=experience_id,
                    )
                    for card, experience_id in zip(cards, experience_ids, strict=True)
                ]
            elif lifecycle_type == "approve":
                cards = self._proposal_cards(experience_ids)
                results = [
                    self.core.approve_memory(card.card_id, actor=TraceActor.DEBUG.value, reason=str(op.get("reason") or "approved"))
                    for card in cards
                ]
            else:
                cards = self._approved_cards(experience_ids)
                results = [
                    self.core.commit_memory(card.card_id, actor=TraceActor.DEBUG.value, reason=str(op.get("reason") or "committed"))
                    for card in cards
                ]
        except LookupError as exc:
            self.core._restore_state(snapshot)
            return _receipt(status="failed", status_reason=str(exc))
        except Exception as exc:
            self.core._restore_state(snapshot)
            return _receipt(status="failed", status_reason=_status_reason(exc), failures=[{"message": str(exc)}])
        card_ids = [result.card.card_id for result in results]
        return _receipt(
            status="success",
            status_reason="applied",
            lifecycle_type=lifecycle_type,
            card_ids=card_ids,
            audit_ids=[result.audit_event.audit_id for result in results],
            provenance_event_ids=[
                ref
                for result in results
                for ref in result.audit_event.provenance_event_ids
            ],
            effective_time=effective_time,
        )

    def _mutate_runtime(self, op: Mapping[str, Any]) -> dict[str, Any]:
        mutation_type = str(op.get("mutation_type") or op.get("lifecycle_type") or op.get("type") or "").strip()
        if mutation_type in LIFECYCLE_TYPES:
            return self._mutate_lifecycle(op, mutation_type)
        if mutation_type not in {"update", "delete", "forget", "supersede", "tombstone"}:
            return _receipt(status="failed", status_reason="unsupported_mutation")
        effective_time = _normalize_effective_time(op.get("effective_time"))
        if op.get("effective_time") and effective_time is None:
            return _receipt(status="failed", status_reason="invalid_effective_time")
        if mutation_type in TERMINAL_MUTATIONS and _has_replacement_content(op):
            return _receipt(status="failed", status_reason="terminal_mutation_replacement_not_allowed")
        target_experience_id = str(op.get("target_experience_id") or "")
        target_card = self._active_card_for_experience(target_experience_id)
        if target_card is None:
            return _receipt(status="failed", status_reason="target_not_found")
        if isinstance(target_card, list):
            return _receipt(status="failed", status_reason="ambiguous_target")
        snapshot = self.core._snapshot_state()
        try:
            authority_refs = self._mutation_authority_refs(op, mutation_type)
            patch = _mutation_patch(op)
            replacement_id = _optional_str(op.get("replacement_experience_id"))
            if replacement_id:
                replacement_card = self._latest_card_for_experience(replacement_id)
                if replacement_card is None:
                    raise LookupError("replacement_not_found")
                patch = {
                    **patch,
                    "summary": replacement_card.summary,
                    "retrieval_terms": list(replacement_card.retrieval_terms),
                    "applicability": replacement_card.applicability.to_dict(),
                    "valence": replacement_card.valence.to_dict(),
                    "confidence": replacement_card.confidence,
                }
                if "details" not in patch and replacement_card.details is not None:
                    patch["details"] = replacement_card.details
            result = self.core.mutate_memory(
                MemoryMutation(
                    mutation_id=str(op.get("op_id") or f"mut_{mutation_type}"),
                    op=mutation_type,
                    target_card_id=target_card.card_id,
                    patch=patch,
                    reason=str(op.get("reason") or mutation_type),
                    actor=TraceActor.USER.value,
                    authority_refs=tuple(authority_refs),
                )
            )
            if replacement_id:
                self._retire_replacement_standalone(replacement_id, {card.card_id for card in result.cards})
            if effective_time:
                self._record_public_effective_time(result.audit_event.audit_id, effective_time)
        except Exception as exc:
            self.core._restore_state(snapshot)
            return _receipt(status="failed", status_reason=_status_reason(exc), failures=[{"message": str(exc)}])
        return _receipt(
            status="success",
            status_reason="applied",
            mutation_type=mutation_type,
            card_ids=[card.card_id for card in result.cards],
            audit_ids=[result.audit_event.audit_id],
            provenance_event_ids=list(result.audit_event.provenance_event_ids),
            effective_time=effective_time,
        )

    def _mutation_authority_refs(self, op: Mapping[str, Any], mutation_type: str) -> list[str]:
        op_id = str(op.get("op_id") or f"mut_{mutation_type}")
        replacement_id = _optional_str(op.get("replacement_experience_id"))
        if replacement_id and replacement_id in self.experiences:
            text = _experience_text(self.experiences[replacement_id])
        else:
            text = str(op.get("reason") or mutation_type)
        event, _receipt_obj, _audit = self.core.capture_raw_provenance(
            RawMemoryIngestRequest(text),
            scope=self._scope_from_public(str(op.get("scope_id") or self.experiences.get(str(op.get("target_experience_id") or ""), {}).get("scope_id") or "mutation")),
            actor=ProvenanceProducer.USER.value,
            source_experience_id=replacement_id,
            source_mutation_id=op_id,
        )
        self._remember_provenance(event)
        return [event.event_id]

    def _proposal_cards(self, experience_ids: Sequence[str]):
        cards = []
        for experience_id in experience_ids:
            proposal_ids = self.proposals_by_experience.get(experience_id) or []
            proposal = next(
                (
                    self.core.memory_cards[card_id]
                    for card_id in reversed(proposal_ids)
                    if card_id in self.core.memory_cards
                    and self.core.memory_cards[card_id].approval_state == ApprovalState.PROPOSAL.value
                ),
                None,
            )
            if proposal is None:
                raise LookupError("proposal_not_found")
            cards.append(proposal)
        return cards

    def _approved_cards(self, experience_ids: Sequence[str]):
        cards = []
        for experience_id in experience_ids:
            card = self._latest_card_for_experience(experience_id, states={ApprovalState.APPROVED.value})
            if card is None:
                raise LookupError("approved_not_found")
            cards.append(card)
        return cards

    def _latest_card_for_experience(self, experience_id: str, *, states: set[str] | None = None):
        refs = set(self.provenance_by_experience.get(experience_id) or [])
        matched = [
            card
            for card in self.core.memory_cards.values()
            if (states is None or card.approval_state in states)
            and any(link.ref_id in refs for link in card.evidence_links)
        ]
        if not matched:
            return None
        return sorted(matched, key=lambda item: (item.timestamps.updated_at, item.card_id))[-1]

    def _active_card_for_experience(self, experience_id: str):
        refs = set(self.provenance_by_experience.get(experience_id) or [])
        matched = [
            card
            for card in self.core.memory_cards.values()
            if card.approval_state == ApprovalState.COMMITTED.value
            and not card.metadata.get("phase_b_deleted")
            and not card.metadata.get("phase_b_forgotten")
            and any(link.ref_id in refs for link in card.evidence_links if link.active)
        ]
        if len(matched) > 1:
            return matched
        return matched[0] if matched else None

    def _remember_provenance(self, event: ProvenanceEvent) -> None:
        if event.source_experience_id:
            self.provenance_by_experience.setdefault(event.source_experience_id, []).append(event.event_id)

    def _remember_proposal(self, experience_id: str, card) -> None:
        self.proposals_by_experience.setdefault(experience_id, []).append(card.card_id)

    def _retire_replacement_standalone(self, experience_id: str, keep_card_ids: set[str]) -> None:
        refs = set(self.provenance_by_experience.get(experience_id) or [])
        for card in list(self.core.memory_cards.values()):
            if card.card_id in keep_card_ids:
                continue
            if card.approval_state != ApprovalState.COMMITTED.value:
                continue
            if not any(link.active and link.ref_id in refs for link in card.evidence_links):
                continue
            self.core.memory_cards[card.card_id] = replace(
                card,
                approval_state=ApprovalState.TOMBSTONED.value,
                metadata={**card.metadata, "memory_eval_retired_replacement": True},
            )

    def _record_public_effective_time(self, audit_id: str, effective_time: str) -> None:
        for index, event in enumerate(self.core.memory_audit_log):
            if event.audit_id != audit_id:
                continue
            self.core.memory_audit_log[index] = replace(
                event,
                metadata={**event.metadata, "public_effective_time": effective_time},
            )
            return

    def _ranked_item_to_harness(self, item: Mapping[str, Any]) -> dict[str, Any]:
        support_ids = list(item.get("support_experience_ids") or [])
        return {
            "rank": item.get("rank"),
            "evidence_ref": item.get("evidence_ref"),
            "evidence_id": item.get("evidence_ref"),
            "score": item.get("score"),
            "score_type": item.get("score_type"),
            "score_components": item.get("score_components") or {},
            "support_experience_ids": support_ids,
            "source_experience_ids": list(item.get("source_experience_ids") or []),
            "lineage_experience_ids": list(item.get("lineage_experience_ids") or []),
            "source_mutation_ids": list(item.get("source_mutation_ids") or []),
            "support_mutation_ids": list(item.get("mutation_refs") or []),
            "provenance_refs": list(item.get("provenance_refs") or []),
            "state": item.get("state"),
            "scope_id": _public_scope_for_support(self.experiences, support_ids) or item.get("scope_id"),
            "metadata": dict(item.get("metadata") or {}),
        }

    def _scope_from_public(self, scope_id: str) -> Scope:
        scope_id = str(scope_id or "default").strip() or "default"
        return Scope(level=ScopeLevel.SHARED.value, namespace=scope_id)


class _DeterministicClock:
    def __init__(self, current: str) -> None:
        self.current = _normalize_effective_time(current) or "2026-05-21T00:00:00Z"

    def __call__(self) -> str:
        value = self.current
        self.current = _add_second(value)
        return value


def _deterministic_replay_extractor(
    request: RawMemoryIngestRequest,
    provenance_event: ProvenanceEvent,
    scope: Scope,
) -> Mapping[str, Any]:
    return {
        "decision": "candidate",
        "candidate": {
            "kind": "semantic_fact",
            "summary": _clean_summary(request.raw_text),
            "details": None,
            "retrieval_terms": _replay_retrieval_terms(request.raw_text),
            "confidence": 0.9,
            "authority": {
                "source": "self",
                "strength": "hint",
                "source_refs": [provenance_event.event_id],
            },
            "valence": {"polarity": "neutral", "effect": "use"},
            "applicability": {
                "applies_to": [scope.scope_key()],
                "does_not_apply_to": [],
                "prerequisites": [],
                "counterexamples": [],
            },
            "evidence_links": [
                {
                    "ref_id": provenance_event.event_id,
                    "role": "current_support",
                    "active": True,
                    "added_by_mutation_id": None,
                    "note": "deterministic replay support",
                }
            ],
            "proposed_by": CandidateProducer.MODEL.value,
            "write_reason": "deterministic memory-eval replay",
            "ambiguous": False,
        },
    }


def _coerce_extractor_config(value: RawMemoryExtractorConfig | Mapping[str, Any] | None) -> RawMemoryExtractorConfig:
    if value is None:
        return RawMemoryExtractorConfig()
    if isinstance(value, RawMemoryExtractorConfig):
        return value
    return RawMemoryExtractorConfig.from_dict(value)


def _receipt(**kwargs: Any) -> dict[str, Any]:
    receipt = {
        "status": kwargs.pop("status", "success"),
        "status_reason": kwargs.pop("status_reason", ""),
        "experience_id": kwargs.pop("experience_id", None),
        "lifecycle_type": kwargs.pop("lifecycle_type", None),
        "mutation_type": kwargs.pop("mutation_type", None),
        "card_ids": kwargs.pop("card_ids", []),
        "proposal_ids": kwargs.pop("proposal_ids", []),
        "provenance_event_ids": kwargs.pop("provenance_event_ids", []),
        "audit_ids": kwargs.pop("audit_ids", []),
        "effective_time": kwargs.pop("effective_time", None),
        "dropped": kwargs.pop("dropped", []),
        "failures": kwargs.pop("failures", []),
    }
    receipt.update(kwargs)
    return receipt


def _experience_text(item: Mapping[str, Any]) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), Mapping) else {}
    text = payload.get("text") if isinstance(payload, Mapping) else None
    return str(text or item.get("text") or "")


def _query_text(query: Mapping[str, Any]) -> str:
    raw = query.get("query")
    if isinstance(raw, Mapping):
        return str(raw.get("text") or raw.get("intent") or "")
    return str(raw or query.get("text") or "")


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _lifecycle_type(op: Mapping[str, Any]) -> str:
    value = str(op.get("lifecycle_type") or op.get("mutation_type") or "").strip()
    return value if value in LIFECYCLE_TYPES else ""


def _target_experience_ids(op: Mapping[str, Any]) -> list[str]:
    payload = op.get("payload") if isinstance(op.get("payload"), Mapping) else {}
    values = []
    if op.get("target_experience_id"):
        values.append(str(op.get("target_experience_id")))
    values.extend(str(item) for item in payload.get("experience_ids") or [])
    return [item for item in values if item]


def _normalize_effective_time(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _add_second(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_summary(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[:512] or "Memory extracted from public experience."


def _replay_retrieval_terms(text: str) -> list[str]:
    terms = []
    seen = set()
    for raw in str(text or "").split():
        term = raw.strip(",:;!?()[]{}\"'")
        if len(term) < 2:
            continue
        key = term.casefold()
        if key in {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "of", "on", "or", "that", "the", "to", "use", "uses", "with"}:
            continue
        if key in {"user", "assistant", "system", "tool", "developer"}:
            continue
        if len(term) > 96:
            continue
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
        if len(terms) >= 32:
            break
    return terms


def _mutation_patch(op: Mapping[str, Any]) -> dict[str, Any]:
    replacement = op.get("replacement") if isinstance(op.get("replacement"), Mapping) else {}
    content = replacement.get("content") if isinstance(replacement.get("content"), Mapping) else {}
    return dict(content)


def _has_replacement_content(op: Mapping[str, Any]) -> bool:
    if op.get("replacement_experience_id"):
        return True
    replacement = op.get("replacement")
    if replacement is None:
        return False
    if not isinstance(replacement, Mapping):
        return True
    return bool(replacement.get("content"))


def _public_scope_for_support(experiences: Mapping[str, Mapping[str, Any]], support_ids: Sequence[str]) -> str | None:
    for support_id in support_ids:
        experience = experiences.get(str(support_id))
        if experience and experience.get("scope_id"):
            return str(experience["scope_id"])
    return None


def _status_reason(exc: Exception) -> str:
    text = str(exc)
    if text in {"proposal_not_found", "approved_not_found", "replacement_not_found"}:
        return text
    if "ambiguous" in text:
        return "ambiguous_target"
    if "replacement" in text and "terminal" in text:
        return "terminal_mutation_replacement_not_allowed"
    return "mutation_failed"


def _usage_to_harness(usage: Mapping[str, Any]) -> dict[str, Any]:
    base = default_usage(latency_ms=float(usage.get("latency_ms") or 0.0))
    base["latency_ms"]["source"] = usage.get("latency_source") or "deterministic_mock"
    base["counts"] = {
        "cards_scanned": usage.get("cards_scanned", 0),
        "cards_ranked": usage.get("cards_ranked", 0),
        "cards_returned": usage.get("cards_returned", 0),
        "cards_dropped": usage.get("cards_dropped", 0),
        "graph_nodes_expanded": usage.get("graph_nodes_expanded", 0),
        "graph_edges_expanded": usage.get("graph_edges_expanded", 0),
        "projection_chars": usage.get("projection_chars", 0),
        "index_mode": usage.get("index_mode", "direct_scan"),
    }
    return base
