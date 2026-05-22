from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mew.memory_typed_card_core import (
    MemoryMutation,
    MemoryRecallRequest,
    ModelRawMemoryExtractor,
    TypedMemoryCore,
    canonical_score,
    raw_memory_extraction_schema,
)
from mew.memory_typed_cards import (
    Applicability,
    Authority,
    AuthorityEvidenceEvent,
    CommandEvidenceState,
    CurrentEvidenceSnapshot,
    EvidenceLink,
    FileEvidenceState,
    GraphNode,
    GraphRefs,
    Invalidator,
    MemoryAuditFields,
    MemoryCard,
    MemoryRevision,
    MemoryTimestamps,
    PrivacyRules,
    ProvenanceProducer,
    RawMemoryIngestRequest,
    Scope,
    SymbolEvidenceState,
    TaskContractEvidence,
    VerifierEvidenceResult,
    stable_json,
)


CREATED = "2026-05-22T00:00:00Z"


class _Clock:
    def __init__(self) -> None:
        self._tick = 0

    def __call__(self) -> str:
        value = f"2026-05-22T00:{self._tick:02d}:00Z"
        self._tick += 1
        return value


def _scope(repo: str = "mew") -> Scope:
    return Scope(level="repo", namespace=f"repo:{repo}", repo_ref=repo)


def _branch_scope(branch: str, repo: str = "mew") -> Scope:
    return Scope(level="branch", namespace=f"repo:{repo}@branch:{branch}", repo_ref=repo, branch_ref=branch)


def _task_scope(task_ref: str, repo: str = "mew", branch: str | None = None) -> Scope:
    return Scope(level="task", namespace=f"task:{task_ref}", repo_ref=repo, branch_ref=branch, task_ref=task_ref)


def _task_family_scope(task_family: str, repo: str = "mew") -> Scope:
    return Scope(level="task_family", namespace=f"task_family:{task_family}", repo_ref=repo, task_family=task_family)


def _project_scope(project_id: str = "project-mew") -> Scope:
    return Scope(level="project", namespace=f"project:{project_id}", project_id=project_id)


def _user_scope(user_id: str = "user-1") -> Scope:
    return Scope(level="user", namespace=f"user:{user_id}", user_id=user_id)


def _candidate_payload(summary: str = "Use typed card lifecycle gates before durable memory recall.") -> dict:
    return {
        "decision": "candidate",
        "candidate": {
            "kind": "semantic_fact",
            "summary": summary,
            "details": "The model output is proposal material until explicit approval and commit.",
            "confidence": 0.86,
            "authority": {"source": "self", "strength": "hint"},
            "valence": {"polarity": "neutral", "effect": "use"},
            "applicability": {"applies_to": [_scope().scope_key(), "task_family:memory-subsystem"]},
            "proposed_by": "model",
        },
    }


def _core_with_payload(payload: dict) -> TypedMemoryCore:
    def extractor(request, provenance_event, scope):
        return payload

    return TypedMemoryCore(extractor=extractor, clock=_Clock())


def _ingest(core: TypedMemoryCore, *, raw_text: str = "Remember the typed lifecycle gate.", source_experience_id: str = "exp_001"):
    return core.ingest_raw(
        RawMemoryIngestRequest(raw_text),
        scope=_scope(),
        source_experience_id=source_experience_id,
    )


def _committed_core(
    summary: str = "Use typed card lifecycle gates before durable memory recall.",
    *,
    source_experience_id: str = "exp_001",
) -> tuple[TypedMemoryCore, MemoryCard]:
    core = _core_with_payload(_candidate_payload(summary))
    result = _ingest(core, raw_text=summary, source_experience_id=source_experience_id)
    assert result.proposal_card is not None
    _approved, committed = core.approve_and_commit_memory(result.proposal_card.card_id, actor="debug")
    return core, committed.card


def _replacement_ref(core: TypedMemoryCore, text: str, *, mutation_id: str = "mut_replacement", source_experience_id: str = "exp_replacement") -> str:
    event, _receipt, _audit = core.capture_raw_provenance(
        RawMemoryIngestRequest(text),
        scope=_scope(),
        actor=ProvenanceProducer.USER.value,
        source_experience_id=source_experience_id,
        source_mutation_id=mutation_id,
    )
    return event.event_id


def _node(node_type: str, canonical_ref: str):
    return GraphNode.build(
        node_type=node_type,
        scope=_scope(),
        canonical_ref=canonical_ref,
        display_name=canonical_ref,
        created_at=CREATED,
        updated_at=CREATED,
    )


def _replace_scope(card: MemoryCard, scope: Scope, *, kind: str | None = None) -> MemoryCard:
    return replace(
        card,
        kind=kind or card.kind,
        scope=scope,
        privacy=PrivacyRules(allowed_scope_ids=(scope.scope_key(),)),
        applicability=Applicability(applies_to=(scope.scope_key(),)),
    )


def test_ingest_raw_captures_provenance_and_stops_at_low_confidence_proposal() -> None:
    payload = _candidate_payload("Ambiguous note: maybe use direct-scan retrieval for Phase B.")
    payload["candidate"]["confidence"] = 0.91
    payload["candidate"]["ambiguous"] = True
    payload["candidate"]["approval_state"] = "committed"
    core = _core_with_payload(payload)

    result = _ingest(core, raw_text="Maybe remember that direct-scan retrieval is enough for now.")

    assert result.status == "low_confidence_proposal"
    assert result.provenance_event.event_kind == "raw_transcript"
    assert core.raw_payloads[result.provenance_event.event_id].startswith("Maybe remember")
    assert result.candidate is not None
    assert result.candidate.confidence == 0.49
    assert result.proposal_card is not None
    assert result.proposal_card.approval_state == "proposal"
    assert not [card for card in core.memory_cards.values() if card.approval_state == "committed"]
    assert [event.operation for event in result.audit_events] == [
        "capture_provenance",
        "extract_candidate",
        "propose",
    ]
    assert any(item.reason == "model_requested_commit" for item in result.dropped)


def test_model_extractor_binds_to_codex_defaults_and_injected_callers() -> None:
    calls = []
    loads = []

    def fake_load_auth(backend, auth_path):
        loads.append((backend, auth_path))
        return {"path": auth_path, "access_token": "redacted"}

    def fake_call_json(model_backend, model_auth, prompt, model, base_url, timeout):
        calls.append(
            {
                "model_backend": model_backend,
                "model_auth": model_auth,
                "prompt": prompt,
                "model": model,
                "base_url": base_url,
                "timeout": timeout,
            }
        )
        return _candidate_payload()

    core = TypedMemoryCore(clock=_Clock())
    request = RawMemoryIngestRequest("Remember that tests inject extractor payloads.")
    provenance_event, _receipt, _audit = core.capture_raw_provenance(request, scope=_scope())
    extractor = ModelRawMemoryExtractor(load_auth=fake_load_auth, call_json=fake_call_json, timeout=17)

    payload = extractor(request, provenance_event, _scope())

    assert payload["decision"] == "candidate"
    assert loads == [("codex", "auth.json")]
    assert calls[0]["model_backend"] == "codex"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["model_auth"]["path"] == "auth.json"
    assert "Remember that tests inject extractor payloads." in calls[0]["prompt"]


def test_model_extractor_prefers_structured_json_and_passes_schema() -> None:
    calls = []

    def fake_call_structured_json(
        model_backend,
        model_auth,
        prompt,
        model,
        base_url,
        timeout,
        *,
        schema_name,
        json_schema,
        strict,
    ):
        calls.append(
            {
                "model_backend": model_backend,
                "model_auth": model_auth,
                "prompt": prompt,
                "model": model,
                "base_url": base_url,
                "timeout": timeout,
                "schema_name": schema_name,
                "json_schema": json_schema,
                "strict": strict,
            }
        )
        return _candidate_payload()

    core = TypedMemoryCore(clock=_Clock())
    request = RawMemoryIngestRequest("Remember that live extraction must use structured JSON.")
    provenance_event, _receipt, _audit = core.capture_raw_provenance(request, scope=_scope())
    extractor = ModelRawMemoryExtractor(
        model_auth={"path": "auth.json", "access_token": "redacted"},
        call_structured_json=fake_call_structured_json,
        timeout=17,
    )

    payload = extractor(request, provenance_event, _scope())

    assert payload["decision"] == "candidate"
    assert calls[0]["model_backend"] == "codex"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["schema_name"] == "raw_memory_extraction"
    assert calls[0]["json_schema"] == raw_memory_extraction_schema()
    assert "retrieval_terms" in calls[0]["json_schema"]["properties"]["candidate"]["required"]
    assert calls[0]["strict"] is True
    assert "default_scope_key" in calls[0]["prompt"]
    assert "retrieval_terms" in calls[0]["prompt"]


def test_approval_commit_separation_and_model_cannot_commit() -> None:
    core = _core_with_payload(_candidate_payload())
    result = _ingest(core)
    card_id = result.proposal_card.card_id

    with pytest.raises(PermissionError, match="model"):
        core.commit_memory(card_id, actor="model_proposal")
    with pytest.raises(ValueError, match="bypass"):
        core.commit_memory(card_id, actor="debug")

    _approved, committed = core.approve_and_commit_memory(card_id, actor="debug")

    assert committed.card.approval_state == "committed"
    audit_ops = [event.operation for event in core.memory_audit_log]
    assert "approve" in audit_ops
    assert "commit" in audit_ops
    assert audit_ops.index("approve") < audit_ops.index("commit")

    reject_core = _core_with_payload(_candidate_payload("Rejected proposals are terminal."))
    reject_result = _ingest(reject_core, raw_text="Rejected proposals are terminal.")
    rejected = reject_core.reject_memory(reject_result.proposal_card.card_id, actor="debug")
    assert rejected.card.approval_state == "rejected"
    with pytest.raises(ValueError, match="forbidden"):
        reject_core.commit_memory(rejected.card.card_id, actor="debug")


def test_seed_eval_bypass_is_restricted_and_audited() -> None:
    core = _core_with_payload(_candidate_payload("Seeded fixture card should rank like ordinary cards."))
    result = _ingest(core, raw_text="Seeded fixture card should rank like ordinary cards.")
    card = replace(
        result.proposal_card,
        authority=Authority(source="scoring", strength="hint", source_refs=(result.provenance_event.event_id,)),
    )

    with pytest.raises(PermissionError):
        core.seed_committed_card_for_eval(card, actor="debug")

    leaked = replace(card, metadata={"gold_label": "do-not-store"})
    with pytest.raises(ValueError, match="gold_label"):
        core.seed_committed_card_for_eval(leaked, actor="adapter")

    committed = core.seed_committed_card_for_eval(card, actor="adapter", public_operation_id="op_seed_001")

    assert committed.card.approval_state == "committed"
    assert committed.bypass == "seed_eval"
    assert committed.audit_event.operation == "seed_eval"
    assert committed.audit_event.metadata["public_operation_id"] == "op_seed_001"


def test_scoring_authority_is_seed_eval_only_not_normal_commit() -> None:
    payload = _candidate_payload("Scoring authority must stay fixture-only.")
    normal_core = _core_with_payload(payload)
    normal_result = _ingest(normal_core, raw_text="Scoring authority must stay fixture-only.")
    scoring_card = replace(
        normal_result.proposal_card,
        authority=Authority(source="scoring", strength="hint", source_refs=(normal_result.provenance_event.event_id,)),
    )
    normal_core.memory_cards[scoring_card.card_id] = scoring_card

    with pytest.raises(PermissionError, match="seed_eval"):
        normal_core.approve_and_commit_memory(scoring_card.card_id, actor="scoring")

    commit_core = _core_with_payload(payload)
    commit_result = _ingest(commit_core, raw_text="Scoring authority must stay fixture-only.")
    commit_card = replace(
        commit_result.proposal_card,
        authority=Authority(source="scoring", strength="hint", source_refs=(commit_result.provenance_event.event_id,)),
    )
    commit_core.memory_cards[commit_card.card_id] = commit_card
    approved = commit_core.approve_memory(commit_card.card_id, actor="scoring")
    with pytest.raises(PermissionError, match="seed_eval"):
        commit_core.commit_memory(approved.card.card_id, actor="scoring")

    seeded = commit_core.seed_committed_card_for_eval(commit_card, actor="scoring")

    assert seeded.card.approval_state == "committed"
    assert seeded.bypass == "seed_eval"


def test_commit_without_graph_refs_is_valid_but_unresolved_graph_refs_fail() -> None:
    core, committed = _committed_core("Graph refs may be absent in Phase B.")

    recall = core.retrieve(MemoryRecallRequest(query="graph refs absent", scope=_scope()))

    assert recall.ranked_evidence[0].evidence_ref == committed.card_id

    result = _ingest(core, raw_text="Graph-backed proposal.")
    node = GraphNode.build(
        node_type="file",
        scope=_scope(),
        canonical_ref="file:mew:main:src/mew/memory_typed_card_core.py",
        display_name="memory_typed_card_core.py",
        created_at=CREATED,
        updated_at=CREATED,
    )
    core.memory_cards[result.proposal_card.card_id] = replace(
        result.proposal_card,
        graph_refs=GraphRefs(node_ids=(node.node_id,)),
    )
    approved = core.approve_memory(result.proposal_card.card_id, actor="debug")
    with pytest.raises(ValueError, match="unresolved"):
        core.commit_memory(approved.card.card_id, actor="debug")

    core.add_graph_node(node)
    committed_with_graph = core.commit_memory(approved.card.card_id, actor="debug")

    assert committed_with_graph.card.graph_refs.node_ids == (node.node_id,)


def test_retrieve_filters_lifecycle_state_scope_and_is_card_side_effect_free() -> None:
    core, committed = _committed_core("Direct scan retrieval returns approved committed cards.")
    before = stable_json({card_id: card.to_dict() for card_id, card in core.memory_cards.items()})

    result = core.retrieve(MemoryRecallRequest(query="direct scan committed", scope=_scope(), limit=5))
    second = core.retrieve(MemoryRecallRequest(query="direct scan committed", scope=_scope(), limit=5))
    after = stable_json({card_id: card.to_dict() for card_id, card in core.memory_cards.items()})

    assert before == after
    assert [item.evidence_ref for item in result.ranked_evidence] == [committed.card_id]
    assert result.ranked_evidence[0].support_experience_ids == ("exp_001",)
    assert result.ranked_evidence[0].score == result.ranked_evidence[0].score_components["final_score"]
    assert result.usage.index_mode == "direct_scan"
    assert second.audit_event.operation == "retrieve"

    other_scope = core.retrieve(MemoryRecallRequest(query="direct scan committed", scope=_scope("other")))
    assert other_scope.abstained is True
    assert other_scope.dropped_count_by_reason["privacy_block"] == 1

    core.memory_cards[committed.card_id] = replace(committed, staleness_state="stale")
    stale = core.retrieve(MemoryRecallRequest(query="direct scan committed", scope=_scope()))
    assert stale.abstained is True
    assert stale.dropped_count_by_reason["stale"] == 1


def test_retrieval_terms_preserve_discriminators_for_ranking_when_summary_is_generic() -> None:
    def extractor(request, provenance_event, scope):
        is_launch = "cobalt" in request.raw_text
        return {
            "decision": "candidate",
            "candidate": {
                "kind": "semantic_fact",
                "summary": "Mira has a badge color preference for reviews.",
                "details": None,
                "retrieval_terms": [
                    "Mira",
                    "badge color",
                    "cobalt" if is_launch else "silver",
                    "launch reviews" if is_launch else "archive reviews",
                ],
                "confidence": 0.9,
                "authority": {"source": "self", "strength": "hint"},
                "valence": {"polarity": "neutral", "effect": "use"},
                "applicability": {"applies_to": [_scope().scope_key()]},
                "proposed_by": "model",
            },
        }

    core = TypedMemoryCore(extractor=extractor, clock=_Clock())
    primary = _ingest(
        core,
        raw_text="Mira uses badge color cobalt for launch reviews.",
        source_experience_id="exp_primary_badge",
    )
    secondary = _ingest(
        core,
        raw_text="Mira uses badge color silver for archive reviews.",
        source_experience_id="exp_secondary_badge",
    )
    assert primary.proposal_card is not None
    assert secondary.proposal_card is not None
    assert "launch reviews" in primary.proposal_card.retrieval_terms

    core.approve_and_commit_memory(primary.proposal_card.card_id, actor="debug")
    core.approve_and_commit_memory(secondary.proposal_card.card_id, actor="debug")

    result = core.retrieve(
        MemoryRecallRequest(
            query="Which badge color does Mira use for launch reviews?",
            scope=_scope(),
            limit=1,
        )
    )

    assert result.ranked_evidence[0].support_experience_ids == ("exp_primary_badge",)
    assert "launch reviews" in result.ranked_evidence[0].metadata["retrieval_terms"]
    assert "cobalt" in result.ranked_evidence[0].metadata["retrieval_terms"]


def test_raw_retrieval_anchor_fallback_sanitizes_unbounded_tokens() -> None:
    payload = _candidate_payload("Store the short durable claim without crashing on raw anchor tokens.")
    core = _core_with_payload(payload)
    long_url = "https://example.test/" + ("very-long-path-segment/" * 12)

    result = _ingest(
        core,
        raw_text=f"Remember this link for later: {long_url}",
        source_experience_id="exp_long_url",
    )

    assert result.proposal_card is not None
    assert all(len(term) <= 96 for term in result.proposal_card.retrieval_terms)
    assert all("very-long-path-segment" not in term for term in result.proposal_card.retrieval_terms)


def test_raw_retrieval_anchor_fallback_skips_single_line_speaker_role_tokens() -> None:
    payload = _candidate_payload("Mira uses badge color cobalt for launch reviews.")
    core = _core_with_payload(payload)

    result = _ingest(
        core,
        raw_text="User: Mira uses badge color cobalt for launch reviews.",
        source_experience_id="exp_speaker_prefix",
    )

    assert result.proposal_card is not None
    assert "User:" not in result.proposal_card.retrieval_terms
    assert "Mira" in result.proposal_card.retrieval_terms


def test_multi_token_query_abstains_on_single_weak_overlap() -> None:
    core, _committed = _committed_core(
        "Mira stores receipts in drawer seven.",
        source_experience_id="exp_unrelated",
    )

    result = core.retrieve(
        MemoryRecallRequest(
            query="Which tea does Mira prefer for breaks?",
            scope=_scope(),
            limit=3,
        )
    )

    assert result.abstained is True
    assert result.dropped_count_by_reason["no_relevant_memory"] == 1


def test_applicability_applies_to_is_required_even_without_explicit_request_refs() -> None:
    core, committed = _committed_core("Procedure applies only to memory subsystem task families.")
    task_family_only = replace(
        committed,
        kind="procedure",
        applicability=Applicability(applies_to=("task_family:memory-subsystem",)),
    )
    core.memory_cards[task_family_only.card_id] = task_family_only

    missing_ref = core.retrieve(MemoryRecallRequest(query="procedure applies", scope=_scope()))
    explicit_ref = core.retrieve(
        MemoryRecallRequest(
            query="procedure applies",
            scope=_scope(),
            applicability_refs=("task_family:memory-subsystem",),
        )
    )
    scope_applicable = replace(task_family_only, applicability=Applicability(applies_to=(_scope().scope_key(),)))
    core.memory_cards[scope_applicable.card_id] = scope_applicable
    scope_ref = core.retrieve(MemoryRecallRequest(query="procedure applies", scope=_scope()))

    assert missing_ref.abstained is True
    assert missing_ref.dropped_count_by_reason["out_of_scope"] == 1
    assert explicit_ref.ranked_evidence[0].evidence_ref == committed.card_id
    assert scope_ref.ranked_evidence[0].evidence_ref == committed.card_id


def test_retrieve_applies_kind_filter_and_does_not_leak_cross_scope_inactive_ids() -> None:
    core, fact_card = _committed_core("Semantic facts should be hidden by procedure filters.")
    proc_core, proc_card = _committed_core("Procedure card should satisfy procedure filters.")
    procedure = replace(proc_card, kind="procedure")
    core.provenance_events.update(proc_core.provenance_events)
    core.raw_payloads.update(proc_core.raw_payloads)
    core.memory_cards[procedure.card_id] = procedure

    result = core.retrieve(MemoryRecallRequest(query="procedure filters", scope=_scope(), kinds=("procedure",)))

    assert [item.evidence_ref for item in result.ranked_evidence] == [procedure.card_id]
    assert result.dropped_count_by_reason["kind_mismatch"] == 1
    assert fact_card.card_id not in [item.evidence_ref for item in result.ranked_evidence]

    hidden_core = _core_with_payload(_candidate_payload("Private proposal should not leak across scopes."))
    proposal = _ingest(hidden_core, raw_text="Private proposal should not leak across scopes.").proposal_card
    assert proposal is not None
    proposal = replace(proposal, scope=_scope(), privacy=PrivacyRules(allowed_scope_ids=(_scope().scope_key(),)))
    hidden_core.memory_cards[proposal.card_id] = proposal
    leaked = hidden_core.retrieve(MemoryRecallRequest(query="private proposal", scope=_scope("other")))

    assert leaked.dropped_count_by_reason["privacy_block"] == 1
    assert all(item.evidence_ref is None for item in leaked.dropped)
    assert proposal.card_id not in stable_json(leaked.to_dict())

    _deleted_core, deleted_card = _committed_core("Deleted private card should not leak.", source_experience_id="exp_deleted")
    _deleted_core.mutate_memory(
        MemoryMutation(mutation_id="mut_delete_private", op="delete", target_card_id=deleted_card.card_id, actor="debug")
    )
    deleted_cross_scope = _deleted_core.retrieve(MemoryRecallRequest(query="deleted private", scope=_scope("other")))
    assert deleted_cross_scope.dropped_count_by_reason["privacy_block"] == 1
    assert all(item.evidence_ref is None for item in deleted_cross_scope.dropped)
    assert deleted_card.card_id not in stable_json(deleted_cross_scope.to_dict())


def test_canonical_score_rounding_and_nonfinite_rejection() -> None:
    assert canonical_score("1.23495") == "1.2350"
    assert canonical_score("-0.00001") == "0.0000"

    with pytest.raises(ValueError):
        canonical_score(float("nan"))
    with pytest.raises(ValueError):
        canonical_score("Infinity")


def test_last_verified_tie_breaker_orders_newer_then_older_then_missing() -> None:
    core, newer = _committed_core("Shared rank newer card.", source_experience_id="exp_rank_newer")
    older_core, older = _committed_core("Shared rank older card.", source_experience_id="exp_rank_older")
    missing_core, missing = _committed_core("Shared rank empty card.", source_experience_id="exp_rank_missing")
    core.provenance_events.update(older_core.provenance_events)
    core.provenance_events.update(missing_core.provenance_events)
    core.raw_payloads.update(older_core.raw_payloads)
    core.raw_payloads.update(missing_core.raw_payloads)
    core.memory_cards[older.card_id] = older
    core.memory_cards[missing.card_id] = missing
    newer = replace(newer, timestamps=replace(newer.timestamps, last_verified_at="2026-05-22T00:00:00Z"))
    older = replace(older, timestamps=replace(older.timestamps, last_verified_at="2025-05-22T00:00:00Z"))
    missing = replace(missing, timestamps=replace(missing.timestamps, last_verified_at=None))
    core.memory_cards[newer.card_id] = newer
    core.memory_cards[older.card_id] = older
    core.memory_cards[missing.card_id] = missing

    result = core.retrieve(MemoryRecallRequest(query="shared", scope=_scope(), limit=3))

    assert [item.evidence_ref for item in result.ranked_evidence] == [
        newer.card_id,
        older.card_id,
        missing.card_id,
    ]


def test_current_evidence_invalidators_cover_phase_b_target_kinds() -> None:
    file_node = _node("file", "file:mew:main:src/mew/memory_typed_card_core.py")
    symbol_node = _node("symbol", "symbol:mew:main:src/mew/memory_typed_card_core.py::TypedMemoryCore")
    command_node = _node("command", "cmd:pytest tests/test_memory_typed_cards_phase_b.py")

    cases = [
        (
            Invalidator(
                kind="file_hash_changed",
                target_node_id=file_node.node_id,
                target_node_type="file",
                baseline_hash="sha256:old-file",
            ),
            CurrentEvidenceSnapshot(
                file_states=(
                    FileEvidenceState(
                        node_id=file_node.node_id,
                        path="src/mew/memory_typed_card_core.py",
                        state="present",
                        content_hash="sha256:new-file",
                    ),
                )
            ),
        ),
        (
            Invalidator(
                kind="symbol_moved",
                target_node_id=symbol_node.node_id,
                target_node_type="symbol",
                baseline_ref="symbol:old",
            ),
            CurrentEvidenceSnapshot(
                symbol_states=(
                    SymbolEvidenceState(
                        node_id=symbol_node.node_id,
                        canonical_ref="symbol:new",
                        state="moved",
                    ),
                )
            ),
        ),
        (
            Invalidator(
                kind="command_changed",
                target_node_id=command_node.node_id,
                target_node_type="command",
                baseline_hash="sha256:old-command",
            ),
            CurrentEvidenceSnapshot(
                command_states=(
                    CommandEvidenceState(
                        node_id=command_node.node_id,
                        normalized_command_ref="cmd:pytest tests/test_memory_typed_cards_phase_b.py",
                        state="changed",
                        command_hash="sha256:new-command",
                    ),
                )
            ),
        ),
        (
            Invalidator(
                kind="verifier_changed",
                baseline_ref="pytest-phase-b",
                baseline_value="pass",
                trigger_policy="value_changed",
            ),
            CurrentEvidenceSnapshot(
                verifier_results=(
                    VerifierEvidenceResult(
                        verifier_ref="pytest-phase-b",
                        result_value="fail",
                        observed_at="2026-05-22T00:10:00Z",
                    ),
                )
            ),
        ),
        (
            Invalidator(
                kind="task_contract_changed",
                baseline_ref="task:memory-phase-b",
                baseline_hash="sha256:old-contract",
            ),
            CurrentEvidenceSnapshot(
                task_contract=TaskContractEvidence(
                    ref="task:memory-phase-b",
                    hash="sha256:new-contract",
                    observed_at="2026-05-22T00:10:00Z",
                )
            ),
        ),
        (
            Invalidator(
                kind="user_preference_updated",
                baseline_ref="pref:memory-policy",
                baseline_observed_at="2026-05-22T00:00:00Z",
            ),
            CurrentEvidenceSnapshot(
                authority_events=(
                    AuthorityEvidenceEvent(
                        ref="pref:memory-policy",
                        source="user",
                        strength="should",
                        target_scope=_scope(),
                        observed_at="2026-05-22T00:10:00Z",
                    ),
                )
            ),
        ),
    ]

    for invalidator, current_evidence in cases:
        core, card = _committed_core(f"Invalidator case {invalidator.kind}", source_experience_id=f"exp_{invalidator.kind}")
        card = replace(card, invalidators=(invalidator,))
        core.memory_cards[card.card_id] = card
        result = core.retrieve(
            MemoryRecallRequest(
                query="invalidator case",
                scope=_scope(),
                current_evidence=current_evidence,
            )
        )
        assert result.dropped_count_by_reason["invalidator_triggered"] == 1


def test_procedure_failure_invalidator_requires_newer_observation() -> None:
    invalidator = Invalidator(
        kind="procedure_failed_recently",
        baseline_ref="task:procedure",
        baseline_observed_at="2026-05-22T00:10:00Z",
    )
    core, card = _committed_core("Procedure failure recency should be checked.", source_experience_id="exp_proc")
    procedure = replace(
        card,
        kind="procedure",
        applicability=Applicability(applies_to=("task:procedure",)),
        invalidators=(invalidator,),
    )
    core.memory_cards[procedure.card_id] = procedure

    def recall_at(observed_at: str):
            return core.retrieve(
                MemoryRecallRequest(
                    query="procedure failure recency",
                    scope=_scope(),
                    applicability_refs=("task:procedure",),
                    current_evidence=CurrentEvidenceSnapshot(
                        verifier_results=(
                            VerifierEvidenceResult(
                            verifier_ref="pytest-phase-b",
                            result_value="fail",
                            applicability_refs=("task:procedure",),
                            observed_at=observed_at,
                        ),
                    )
                ),
            )
        )

    assert recall_at("2026-05-22T00:09:00Z").ranked_evidence[0].evidence_ref == procedure.card_id
    assert recall_at("2026-05-22T00:10:00Z").ranked_evidence[0].evidence_ref == procedure.card_id
    newer = recall_at("2026-05-22T00:11:00Z")
    assert newer.abstained is True
    assert newer.dropped_count_by_reason["invalidator_triggered"] == 1


def test_mutations_update_delete_forget_tombstone_and_supersede() -> None:
    core, update_card = _committed_core("Old summary for typed memory update.", source_experience_id="exp_update")

    with pytest.raises(ValueError, match="forbidden"):
        core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_forbidden",
                op="update",
                target_card_id=update_card.card_id,
                patch={"approval_state": "committed"},
                actor="debug",
            )
        )

    with pytest.raises(ValueError, match="replacement provenance"):
        core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_update_missing_support",
                op="update",
                target_card_id=update_card.card_id,
                patch={"summary": "Unsupported summary change."},
                actor="debug",
            )
        )

    with pytest.raises(ValueError, match="must not reuse"):
        core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_update_old_support",
                op="update",
                target_card_id=update_card.card_id,
                patch={"summary": "Old support must not justify new content."},
                actor="debug",
                authority_refs=(update_card.evidence_links[0].ref_id,),
            )
        )

    stale_ref, _receipt, _audit = core.capture_raw_provenance(
        RawMemoryIngestRequest("Replacement-looking evidence without mutation id."),
        scope=_scope(),
        actor=ProvenanceProducer.USER.value,
        source_experience_id="exp_no_mutation_marker",
    )
    with pytest.raises(ValueError, match="source_mutation_id"):
        core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_update_unmarked_support",
                op="update",
                target_card_id=update_card.card_id,
                patch={"summary": "Unmarked support must not justify new content."},
                actor="debug",
                authority_refs=(stale_ref.event_id,),
            )
        )

    update_ref = _replacement_ref(
        core,
        "Updated summary for typed memory retrieval.",
        mutation_id="mut_update",
        source_experience_id="exp_update_replacement",
    )
    update = core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_update",
            op="update",
            target_card_id=update_card.card_id,
            patch={"summary": "Updated summary for typed memory retrieval."},
            actor="debug",
            authority_refs=(update_ref,),
        )
    )
    assert update.cards[0].card_id == update_card.card_id
    assert update.cards[0].revision.version == update_card.revision.version + 1
    update_recall = core.retrieve(MemoryRecallRequest(query="updated summary retrieval", scope=_scope()))
    assert update_recall.ranked_evidence[0].evidence_ref == update_card.card_id
    assert update_recall.ranked_evidence[0].support_experience_ids == ("exp_update_replacement",)

    _delete_core, delete_card = _committed_core("Delete removes a card from normal retrieval.", source_experience_id="exp_delete")
    delete_event_id = delete_card.evidence_links[0].ref_id
    delete = _delete_core.mutate_memory(
        MemoryMutation(mutation_id="mut_delete", op="delete", target_card_id=delete_card.card_id, actor="debug")
    )
    assert delete.cards[0].metadata["phase_b_deleted"] is True
    assert _delete_core.provenance_events[delete_event_id].retention_state == "active"
    assert _delete_core.retrieve(MemoryRecallRequest(query="delete retrieval", scope=_scope())).dropped_count_by_reason["deleted"] == 1

    _forget_core, forget_card = _committed_core("Forget redacts caller-visible support.", source_experience_id="exp_forget")
    forget_event_id = forget_card.evidence_links[0].ref_id
    forget = _forget_core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_forget",
            op="forget",
            target_card_id=forget_card.card_id,
            actor="user",
            authority_refs=(forget_event_id,),
        )
    )
    assert forget.cards[0].metadata["phase_b_forgotten"] is True
    assert _forget_core.provenance_events[forget_event_id].retention_state == "deleted"
    assert forget_event_id not in _forget_core.raw_payloads
    assert _forget_core.retrieve(MemoryRecallRequest(query="forget support", scope=_scope())).dropped_count_by_reason["forgotten"] == 1

    _tomb_core, tomb_card = _committed_core("Tombstone keeps audit-visible lineage.", source_experience_id="exp_tomb")
    tombstone = _tomb_core.mutate_memory(
        MemoryMutation(mutation_id="mut_tomb", op="tombstone", target_card_id=tomb_card.card_id, actor="debug")
    )
    assert tombstone.cards[0].metadata["phase_b_tombstoned"] is True
    assert _tomb_core.retrieve(MemoryRecallRequest(query="tombstone lineage", scope=_scope())).dropped_count_by_reason["tombstoned"] == 1

    _super_core, old_card = _committed_core("Old superseded retrieval behavior.", source_experience_id="exp_old")
    super_ref = _replacement_ref(
        _super_core,
        "New superseding retrieval behavior.",
        mutation_id="mut_super",
        source_experience_id="exp_new",
    )
    supersede = _super_core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_super",
            op="supersede",
            target_card_id=old_card.card_id,
            patch={"summary": "New superseding retrieval behavior."},
            actor="debug",
            authority_refs=(super_ref,),
        )
    )
    old, new = supersede.cards
    assert old.approval_state == "superseded"
    assert new.approval_state == "committed"
    ranked = _super_core.retrieve(MemoryRecallRequest(query="superseding retrieval", scope=_scope())).ranked_evidence
    assert [item.evidence_ref for item in ranked] == [new.card_id]
    assert ranked[0].support_experience_ids == ("exp_new",)

    card_core, card_target = _committed_core("Old replacement-card support.", source_experience_id="exp_card_old")
    bad_replacement = replace(
        card_target,
        card_id="mem_bad_replacement_card",
        summary="New replacement-card content cannot reuse old support.",
        revision=MemoryRevision(version=card_target.revision.version + 1, supersedes=(card_target.card_id,)),
    )
    with pytest.raises(ValueError, match="must not reuse"):
        card_core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_super_card_bad",
                op="supersede",
                target_card_id=card_target.card_id,
                replacement_card=bad_replacement,
                actor="debug",
            )
        )

    unmarked_ref, _receipt, _audit = card_core.capture_raw_provenance(
        RawMemoryIngestRequest("Unmarked replacement-card support."),
        scope=_scope(),
        actor=ProvenanceProducer.USER.value,
        source_experience_id="exp_card_unmarked",
    )
    unmarked_replacement = replace(
        card_target,
        card_id="mem_unmarked_replacement_card",
        summary="New replacement-card content needs mutation-marked support.",
        evidence_links=(
            EvidenceLink(
                ref_id=unmarked_ref.event_id,
                role="current_support",
                active=True,
                added_by_mutation_id="mut_super_card_unmarked",
            ),
        ),
        revision=MemoryRevision(version=card_target.revision.version + 1, supersedes=(card_target.card_id,)),
    )
    with pytest.raises(ValueError, match="source_mutation_id"):
        card_core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_super_card_unmarked",
                op="supersede",
                target_card_id=card_target.card_id,
                replacement_card=unmarked_replacement,
                actor="debug",
            )
        )

    card_ref = _replacement_ref(
        card_core,
        "Supported replacement-card content.",
        mutation_id="mut_super_card_good",
        source_experience_id="exp_card_new",
    )
    good_replacement = replace(
        card_target,
        card_id="mem_good_replacement_card",
        summary="Supported replacement-card content.",
        evidence_links=(
            EvidenceLink(
                ref_id=card_ref,
                role="current_support",
                active=True,
                added_by_mutation_id="mut_super_card_good",
            ),
        ),
        revision=MemoryRevision(version=card_target.revision.version + 1, supersedes=(card_target.card_id,)),
    )
    card_supersede = card_core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_super_card_good",
            op="supersede",
            target_card_id=card_target.card_id,
            replacement_card=good_replacement,
            actor="debug",
        )
    )
    _old_card, new_card = card_supersede.cards
    assert new_card.card_id == "mem_good_replacement_card"
    card_ranked = card_core.retrieve(MemoryRecallRequest(query="replacement-card content", scope=_scope())).ranked_evidence
    assert [item.evidence_ref for item in card_ranked] == ["mem_good_replacement_card"]
    assert card_ranked[0].support_experience_ids == ("exp_card_new",)


def test_authority_source_requires_matching_provenance_before_commit() -> None:
    payload = _candidate_payload("Reviewer authority cannot be invented by the model.")
    payload["candidate"]["authority"] = {"source": "reviewer", "strength": "should"}
    core = _core_with_payload(payload)
    result = _ingest(core, raw_text="The model says a reviewer required this.")
    approved = core.approve_memory(result.proposal_card.card_id, actor="debug")

    with pytest.raises(PermissionError, match="reviewer"):
        core.commit_memory(approved.card.card_id, actor="debug")

    reviewer_core = _core_with_payload(payload)
    reviewer_result = reviewer_core.ingest_raw(
        RawMemoryIngestRequest("Reviewer: use typed cards for durable memory."),
        scope=_scope(),
        actor=ProvenanceProducer.REVIEWER.value,
    )
    reviewer_core.approve_memory(
        reviewer_result.proposal_card.card_id,
        actor="reviewer",
        approval_refs=(reviewer_result.provenance_event.event_id,),
    )
    committed = reviewer_core.commit_memory(reviewer_result.proposal_card.card_id, actor="debug")

    assert committed.card.authority.source == "reviewer"


def test_contradicted_cards_are_blocked_and_supersede_restores_active_memory() -> None:
    core, card = _committed_core("Old contradicted memory should not project.", source_experience_id="exp_contra_old")
    contradicted = replace(card, contradiction_state="contradicted")
    core.memory_cards[card.card_id] = contradicted
    blocked = core.retrieve(MemoryRecallRequest(query="contradicted memory", scope=_scope()))
    assert blocked.abstained is True
    assert blocked.dropped_count_by_reason["contradicted"] == 1

    replacement_ref = _replacement_ref(
        core,
        "Resolved replacement memory should project.",
        mutation_id="mut_contra_super",
        source_experience_id="exp_contra_new",
    )
    supersede = core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_contra_super",
            op="supersede",
            target_card_id=card.card_id,
            patch={"summary": "Resolved replacement memory should project."},
            actor="debug",
            authority_refs=(replacement_ref,),
        )
    )
    _old, new = supersede.cards
    recalled = core.retrieve(MemoryRecallRequest(query="resolved replacement", scope=_scope()))
    assert [item.evidence_ref for item in recalled.ranked_evidence] == [new.card_id]

    debug_core, debug_card = _committed_core("Possible contradiction can be resolved by debug evidence.")
    possible = replace(debug_card, contradiction_state="possible")
    debug_core.memory_cards[possible.card_id] = possible
    assert debug_core.retrieve(MemoryRecallRequest(query="possible contradiction", scope=_scope())).dropped_count_by_reason["contradicted"] == 1
    debug_evidence = _replacement_ref(debug_core, "Debug evidence resolved the contradiction.", mutation_id="mut_resolve")
    debug_core.mutate_memory(
        MemoryMutation(
            mutation_id="mut_resolve",
            op="update",
            target_card_id=possible.card_id,
            patch={"details": "Debug evidence resolved the contradiction."},
            actor="debug",
            authority_refs=(debug_evidence,),
        )
    )
    resolved = replace(debug_core.memory_cards[possible.card_id], contradiction_state="resolved")
    debug_core.memory_cards[resolved.card_id] = resolved
    assert debug_core.retrieve(MemoryRecallRequest(query="debug evidence resolved", scope=_scope())).ranked_evidence[0].evidence_ref == resolved.card_id


def test_scope_overlap_table_and_cross_scope_drop_non_leakage() -> None:
    core, repo_card = _committed_core("Repo scope is visible to same repo branch callers.")
    branch_request = core.retrieve(
        MemoryRecallRequest(
            query="repo scope visible",
            scope=_branch_scope("main"),
            applicability_refs=(repo_card.scope.scope_key(),),
        )
    )
    assert branch_request.ranked_evidence[0].evidence_ref == repo_card.card_id

    branch_card = _replace_scope(repo_card, _branch_scope("feature"))
    core.memory_cards[branch_card.card_id] = branch_card
    other_branch = core.retrieve(MemoryRecallRequest(query="repo scope visible", scope=_branch_scope("other")))
    assert other_branch.abstained is True
    assert all(item.evidence_ref is None for item in other_branch.dropped)

    task_card = _replace_scope(repo_card, _task_scope("task-1"))
    core.memory_cards[task_card.card_id] = task_card
    exact_task = core.retrieve(MemoryRecallRequest(query="repo scope visible", scope=_task_scope("task-1")))
    wrong_task = core.retrieve(MemoryRecallRequest(query="repo scope visible", scope=_task_scope("task-2")))
    assert exact_task.ranked_evidence[0].evidence_ref == task_card.card_id
    assert wrong_task.abstained is True
    missing_task_container = core.retrieve(
        MemoryRecallRequest(
            query="repo scope visible",
            scope=Scope(level="task", namespace="task:task-1", task_ref="task-1"),
        )
    )
    mismatched_task_container = core.retrieve(
        MemoryRecallRequest(query="repo scope visible", scope=_task_scope("task-1", repo="other"))
    )
    assert missing_task_container.abstained is True
    assert mismatched_task_container.abstained is True
    assert all(item.evidence_ref is None for item in missing_task_container.dropped)
    assert all(item.evidence_ref is None for item in mismatched_task_container.dropped)

    family_card = _replace_scope(repo_card, _task_family_scope("memory-subsystem"))
    core.memory_cards[family_card.card_id] = family_card
    family_request = core.retrieve(
        MemoryRecallRequest(query="repo scope visible", scope=_task_family_scope("memory-subsystem"))
    )
    assert family_request.ranked_evidence[0].evidence_ref == family_card.card_id
    missing_family_container = core.retrieve(
        MemoryRecallRequest(
            query="repo scope visible",
            scope=Scope(
                level="task_family",
                namespace="task_family:memory-subsystem",
                task_family="memory-subsystem",
            ),
        )
    )
    mismatched_family_container = core.retrieve(
        MemoryRecallRequest(query="repo scope visible", scope=_task_family_scope("memory-subsystem", repo="other"))
    )
    assert missing_family_container.abstained is True
    assert mismatched_family_container.abstained is True
    assert all(item.evidence_ref is None for item in missing_family_container.dropped)
    assert all(item.evidence_ref is None for item in mismatched_family_container.dropped)

    project_card = _replace_scope(repo_card, _project_scope("project-mew"))
    core.memory_cards[project_card.card_id] = project_card
    project_request = core.retrieve(MemoryRecallRequest(query="repo scope visible", scope=_project_scope("project-mew")))
    assert project_request.ranked_evidence[0].evidence_ref == project_card.card_id

    user_core, user_card = _committed_core("User preference remains user-scoped.")
    policy_card = _replace_scope(user_card, _user_scope("user-1"), kind="policy_or_preference")
    user_core.memory_cards[policy_card.card_id] = policy_card
    same_user = user_core.retrieve(MemoryRecallRequest(query="user preference", scope=_user_scope("user-1")))
    other_user = user_core.retrieve(MemoryRecallRequest(query="user preference", scope=_user_scope("user-2")))
    assert same_user.ranked_evidence[0].evidence_ref == policy_card.card_id
    assert other_user.abstained is True
    assert all(item.evidence_ref is None for item in other_user.dropped)


def test_report_usage_aggregates_latency_source_precedence() -> None:
    core, _card = _committed_core("Usage report should aggregate latency sources.")
    core.retrieve(MemoryRecallRequest(query="usage report", scope=_scope(), latency_source="deterministic_mock"))
    core.retrieve(MemoryRecallRequest(query="usage report", scope=_scope(), latency_source="replayed_artifact"))
    core.retrieve(MemoryRecallRequest(query="usage report", scope=_scope(), latency_source="wall_clock"))

    report = core.report_usage()

    assert report.request_count == 3
    assert report.usage.latency_source == "wall_clock"
    assert report.metadata["latency_source_counts"] == {
        "deterministic_mock": 1,
        "replayed_artifact": 1,
        "wall_clock": 1,
    }


def test_commit_and_mutation_roll_back_on_partial_failure() -> None:
    core = _core_with_payload(_candidate_payload("Rollback commit should leave proposal approved."))
    result = _ingest(core, raw_text="Rollback commit should leave proposal approved.")
    node = _node("file", "file:mew:main:rollback.py")
    core.add_graph_node(node)
    core.memory_cards[result.proposal_card.card_id] = replace(
        result.proposal_card,
        graph_refs=GraphRefs(node_ids=(node.node_id,)),
    )
    approved = core.approve_memory(result.proposal_card.card_id, actor="debug")
    original_append = core._append_audit

    def fail_commit_audit(**kwargs):
        if kwargs.get("operation") == "commit":
            raise RuntimeError("audit write failed")
        return original_append(**kwargs)

    core._append_audit = fail_commit_audit
    with pytest.raises(RuntimeError, match="audit write failed"):
        core.commit_memory(approved.card.card_id, actor="debug")
    assert core.memory_cards[approved.card.card_id].approval_state == "approved"
    assert core.memory_cards[approved.card.card_id].graph_refs.node_ids == (node.node_id,)

    mutate_core, forget_card = _committed_core("Rollback forget should restore raw provenance.", source_experience_id="exp_rollback")
    forget_event_id = forget_card.evidence_links[0].ref_id
    before_raw = dict(mutate_core.raw_payloads)
    original_mutate_append = mutate_core._append_audit

    def fail_mutate_audit(**kwargs):
        if kwargs.get("operation") == "mutate":
            raise RuntimeError("mutate audit failed")
        return original_mutate_append(**kwargs)

    mutate_core._append_audit = fail_mutate_audit
    with pytest.raises(RuntimeError, match="mutate audit failed"):
        mutate_core.mutate_memory(
            MemoryMutation(
                mutation_id="mut_forget_rollback",
                op="forget",
                target_card_id=forget_card.card_id,
                actor="user",
                authority_refs=(forget_event_id,),
            )
        )
    assert mutate_core.memory_cards[forget_card.card_id].approval_state == "committed"
    assert mutate_core.provenance_events[forget_event_id].retention_state == "active"
    assert mutate_core.raw_payloads == before_raw


def test_transient_reentry_recall_stays_out_of_durable_recall_and_support_ids() -> None:
    core = TypedMemoryCore(clock=_Clock())
    transient = core.store_transient_reentry(
        session_id="session-1",
        scope=_scope(),
        summary="Transient reentry note for current session only.",
    )

    durable = core.retrieve(MemoryRecallRequest(query="transient reentry", scope=_scope()))
    transient_result = core.retrieve_transient_reentry(session_id="session-1", scope=_scope())

    assert durable.abstained is True
    assert durable.abstained_reason == "no_memory"
    assert core.memory_cards == {}
    assert transient_result.records == (transient,)
    assert transient_result.audit_event.operation == "retrieve_transient"
    assert "support_experience_ids" not in stable_json(transient_result.to_dict())


def test_migration_and_emergency_restore_bypass_audits() -> None:
    migration_core, migration_card = _committed_core("Migration bypass should be explicit.", source_experience_id="exp_migrate")
    migration_candidate = replace(
        migration_card,
        card_id="mem_migration_round2",
        audit=MemoryAuditFields(
            created_by="migration",
            write_reason="round 2 migration audit test",
            create_audit_id="audit_pending_migration",
        ),
    )
    migration = migration_core.import_migrated_card(migration_candidate, source_schema_version="legacy.v0")

    assert migration.bypass == "migration"
    assert migration.audit_event.operation == "migrate"
    assert migration.card.audit.created_by == "migration"

    restore_core, old_card = _committed_core("Emergency restore source.", source_experience_id="exp_restore_old")
    restore_ref = _replacement_ref(
        restore_core,
        "Emergency restored memory revision.",
        mutation_id="mut_restore",
        source_experience_id="exp_restore_new",
    )
    restored_candidate = replace(
        old_card,
        card_id="mem_emergency_restore_round2",
        summary="Emergency restored memory revision.",
        evidence_links=(
            EvidenceLink(
                ref_id=restore_ref,
                role="current_support",
                added_by_mutation_id="mut_restore",
            ),
        ),
        revision=MemoryRevision(version=old_card.revision.version + 1),
        timestamps=MemoryTimestamps(created_at=CREATED, updated_at=CREATED),
    )
    restored = restore_core.emergency_restore_new_revision(
        restored_candidate,
        source_card_id=old_card.card_id,
        actor="core",
    )

    assert restored.bypass == "emergency_restore"
    assert restored.audit_event.operation == "rollback"
    assert old_card.card_id in restored.card.revision.supersedes


def test_phase_b_core_has_no_forbidden_imports() -> None:
    source = Path("src/mew/memory_typed_card_core.py").read_text(encoding="utf-8")
    forbidden = (
        "implement_v2",
        "MemoryArena",
        "ToolRegistry",
        "PromptSectionRegistry",
        "memory_eval.runner",
        "memory_eval.scoring",
        "memory_eval.fixtures",
    )

    for item in forbidden:
        assert item not in source
