from pathlib import Path

import pytest

from mew.memory_typed_cards import (
    ActorKind,
    Applicability,
    ApplicabilityRef,
    Authority,
    AuthorityEvidenceEvent,
    CommandEvidenceState,
    CurrentEvidenceSnapshot,
    DroppedReason,
    EvidenceLink,
    FileEvidenceState,
    GraphEdge,
    GraphNode,
    GraphRefs,
    Invalidator,
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
    ProvenanceEvent,
    ProvenanceProducer,
    ProvenanceReceipt,
    ProvenanceRef,
    RawMemoryExtractorConfig,
    RawMemoryIngestRequest,
    Scope,
    SymbolEvidenceState,
    TaskContractEvidence,
    Valence,
    VerifierEvidenceResult,
    make_node_id_v1,
    migrate_legacy_memory_entry,
    migrate_retired_memory_card_payload,
    parse_node_id_v1,
    pseudonymous_actor_ref,
    stable_hash,
    stable_json,
)


CREATED = "2026-05-22T00:00:00Z"
UPDATED = "2026-05-22T00:01:00Z"


def _scope() -> Scope:
    return Scope(level="repo", namespace="repo:mew", repo_ref="mew")


def _support_link(ref_id: str = "prov_support_001") -> EvidenceLink:
    return EvidenceLink(
        ref_id=ref_id,
        role="current_support",
        active=True,
        added_by_mutation_id="mut_001",
        note="supports extracted claim",
    )


def _manual_invalidator() -> Invalidator:
    return Invalidator(
        kind="manual",
        trigger_policy="manual_only",
        manual_reason="Reviewer asked to retire this if the design changes.",
        metadata={"source": "phase-a-test"},
    )


def _card(**overrides) -> MemoryCard:
    scope = overrides.pop("scope", _scope())
    values = {
        "card_id": "mem_phase_a_001",
        "kind": "semantic_fact",
        "summary": "Typed memory cards store extracted claims, not raw transcript logs.",
        "details": "The durable card cites provenance and keeps raw material behind provenance events.",
        "confidence": 0.87654,
        "scope": scope,
        "lifecycle": Lifecycle(lifespan="project_durable"),
        "authority": Authority(source="reviewer", strength="should", source_refs=("prov_approval_001",)),
        "valence": Valence(polarity="neutral", effect="use"),
        "applicability": Applicability(
            applies_to=(f"scope:v1:{scope.level}:{scope.scope_key().split(':')[-1]}", "task_family:memory-subsystem"),
            prerequisites=("workflow:phase-a",),
        ),
        "evidence_links": (_support_link(), EvidenceLink(ref_id="prov_approval_001", role="approval")),
        "invalidators": (_manual_invalidator(),),
        "graph_refs": GraphRefs(),
        "privacy": PrivacyRules(sharing="project", allowed_scope_ids=(scope.scope_key(),)),
        "timestamps": MemoryTimestamps(created_at=CREATED, updated_at=UPDATED),
        "revision": MemoryRevision(version=1, supersedes=("legacy_entry_001",)),
        "audit": MemoryAuditFields(
            created_by="migration",
            write_reason="Phase A schema golden fixture",
            create_audit_id="audit_phase_a_001",
        ),
        "approval_state": "committed",
        "projection_mode": "debug_only",
        "metadata": {"schema_fixture": "phase_a"},
    }
    values.update(overrides)
    return MemoryCard(**values)


def _node(node_type: str, canonical_ref: str) -> GraphNode:
    return GraphNode.build(
        node_type=node_type,
        scope=_scope(),
        canonical_ref=canonical_ref,
        display_name=canonical_ref,
        created_at=CREATED,
        updated_at=UPDATED,
    )


def test_raw_ingress_is_raw_text_only_and_rejects_public_rich_hints():
    request = RawMemoryIngestRequest.from_dict({"raw_text": "Remember that Phase A is schema only."})
    extractor_config = RawMemoryExtractorConfig()

    assert request.to_dict() == {"raw_text": "Remember that Phase A is schema only."}
    assert extractor_config.to_dict() == {
        "backend": "codex",
        "model": "gpt-5.5",
        "auth_path": "auth.json",
        "call_interface": "call_model_structured_json",
        "injectable_caller": True,
    }

    for forbidden in ("hint", "event_kind", "scope", "actor", "intent", "authority", "files", "commands"):
        with pytest.raises(ValueError, match="raw_text"):
            RawMemoryIngestRequest.from_dict({"raw_text": "content", forbidden: "rich hint"})

    with pytest.raises(ValueError, match="token"):
        RawMemoryExtractorConfig.from_dict({"token": "never-store-this"})


def test_card_kind_enum_is_exact_and_old_flat_kinds_are_rejected():
    assert tuple(item.value for item in MemoryCardKind) == (
        "reentry_snapshot",
        "task_episode",
        "semantic_fact",
        "procedure",
        "policy_or_preference",
    )

    for old_kind in (
        "project_convention",
        "episodic_task",
        "procedural_repair",
        "failure_shield",
        "reviewer_correction",
        "file_symbol_edge",
        "user_preference",
    ):
        with pytest.raises(ValueError):
            _card(kind=old_kind)


def test_scope_key_and_node_id_v1_canonicalization_golden():
    scope = _scope()
    canonical_ref = "file:mew:main:src/mew/memory_core.py"
    node_id = make_node_id_v1("file", scope.scope_key(), canonical_ref)

    assert scope.canonical_json() == '{"level":"repo","namespace":"repo:mew","repo_ref":"mew"}'
    assert scope.scope_key() == "scope:v1:repo:6e65353668c4eff4"
    assert (
        node_id
        == "node:v1:file:scope%3Av1%3Arepo%3A6e65353668c4eff4:"
        "file%3Amew%3Amain%3Asrc%2Fmew%2Fmemory_core.py"
    )
    assert parse_node_id_v1(node_id).canonical_ref == canonical_ref

    graph_node = _node("file", canonical_ref)
    assert graph_node.scope_key == scope.scope_key()
    assert graph_node.node_id == node_id

    with pytest.raises(ValueError, match="uppercase"):
        parse_node_id_v1(node_id.replace("%3A", "%3a", 1))
    with pytest.raises(ValueError, match="double-encoded"):
        parse_node_id_v1("node:v1:file:scope%253Av1:file")
    with pytest.raises(ValueError):
        parse_node_id_v1("node:v1:file:raw:scope:file")


def test_actor_graph_node_supports_required_actor_kinds_and_stable_pseudonymous_refs():
    scope = _scope()
    for actor_kind in (item.value for item in ActorKind):
        actor_ref = pseudonymous_actor_ref(actor_kind, "private raw actor id", scope_key=scope.scope_key())
        actor_node = GraphNode.build(
            node_type="actor",
            scope=scope,
            canonical_ref=actor_ref,
            display_name="debug label",
            metadata={"actor_kind": actor_kind},
            created_at=CREATED,
            updated_at=UPDATED,
        )
        assert actor_node.metadata["actor_kind"] == actor_kind
        assert actor_node.canonical_ref == actor_ref
        assert "private raw actor id" not in actor_node.node_id

    assert pseudonymous_actor_ref("adapter", "same", scope_key=scope.scope_key()) == pseudonymous_actor_ref(
        "adapter", "same", scope_key=scope.scope_key()
    )


def test_provenance_shapes_cover_adapter_scoring_migration_and_excerpt_rules():
    scope = _scope()
    for producer in ("adapter", "scoring", "migration"):
        event = ProvenanceEvent(
            event_id=f"prov_{producer}",
            event_kind="memory_proposal",
            actor=producer,
            scope=scope,
            payload_hash=f"sha256:{producer}",
            provenance_excerpt="bounded excerpt",
            source_experience_id="exp_001",
            source_mutation_id="mut_001",
            created_at=CREATED,
        )
        ref = ProvenanceRef(
            ref_id=event.event_id,
            event_kind=event.event_kind,
            artifact_path_or_uri=None,
            content_hash=event.payload_hash,
            excerpt_hash="sha256:excerpt",
            timestamp=event.created_at,
            producer=producer,
            scope=scope,
            source_experience_id=event.source_experience_id,
            source_mutation_id=event.source_mutation_id,
        )
        receipt = ProvenanceReceipt(
            event_id=event.event_id,
            event_kind=event.event_kind,
            producer=producer,
            scope=scope,
            payload_hash=event.payload_hash,
            excerpt_hash=ref.excerpt_hash,
            source_experience_id=event.source_experience_id,
            source_mutation_id=event.source_mutation_id,
            redaction_state="none",
            retention_state="active",
            audit_id=f"audit_{producer}",
        )
        assert event.actor == producer
        assert ref.producer == producer
        assert receipt.producer == producer
        assert receipt.to_dict()["producer"] == producer
        assert receipt.source_experience_id == "exp_001"
        assert receipt.source_mutation_id == "mut_001"

    assert {"adapter", "scoring", "migration"}.issubset({item.value for item in ProvenanceProducer})
    with pytest.raises(ValueError, match="producer"):
        ProvenanceReceipt(
            event_id="prov_bad_producer",
            event_kind="memory_proposal",
            producer="model",
            scope=scope,
            payload_hash="sha256:bad",
            excerpt_hash=None,
            source_experience_id=None,
            source_mutation_id=None,
            redaction_state="none",
            retention_state="active",
            audit_id="audit_bad_producer",
        )
    with pytest.raises(ValueError, match="provenance_excerpt"):
        ProvenanceEvent(
            event_id="prov_long_excerpt",
            event_kind="raw_transcript",
            actor="adapter",
            scope=scope,
            payload_hash="sha256:raw",
            provenance_excerpt="x" * 241,
            created_at=CREATED,
        )


def test_memory_card_golden_serialization_hash_and_retired_schema_names():
    card = _card()
    card_json = stable_json(card.to_dict())

    assert "projection_mode" in card.to_dict()
    assert "projection" not in card.to_dict()
    assert "state" not in card.to_dict()
    assert card_json == (
        '{"applicability":{"applies_to":["scope:v1:repo:6e65353668c4eff4",'
        '"task_family:memory-subsystem"],"counterexamples":[],"does_not_apply_to":[],'
        '"prerequisites":["workflow:phase-a"]},"approval_state":"committed",'
        '"audit":{"create_audit_id":"audit_phase_a_001","created_by":"migration",'
        '"last_semantic_mutation_audit_id":null,"write_reason":"Phase A schema golden fixture"},'
        '"authority":{"source":"reviewer","source_refs":["prov_approval_001"],"strength":"should"},'
        '"card_id":"mem_phase_a_001","confidence":0.8765,"contradiction_state":"none",'
        '"details":"The durable card cites provenance and keeps raw material behind provenance events.",'
        '"evidence_links":[{"active":true,"added_by_mutation_id":"mut_001",'
        '"note":"supports extracted claim","ref_id":"prov_support_001","role":"current_support"},'
        '{"active":true,"added_by_mutation_id":null,"note":null,"ref_id":"prov_approval_001",'
        '"role":"approval"}],"graph_refs":{"edge_ids":[],"node_ids":[]},"invalidators":[{'
        '"baseline_hash":null,"baseline_observed_at":null,"baseline_ref":null,"baseline_value":null,'
        '"checked_at":null,"kind":"manual","manual_reason":"Reviewer asked to retire this if the design changes.",'
        '"metadata":{"source":"phase-a-test"},"ref":null,"target_node_id":null,"target_node_type":null,'
        '"trigger_policy":"manual_only"}],"kind":"semantic_fact","lifecycle":{"consolidation_state":"none",'
        '"expires_at":null,"lifespan":"project_durable","retention_policy_id":null},'
        '"metadata":{"schema_fixture":"phase_a"},"privacy":{"allowed_scope_ids":["scope:v1:repo:6e65353668c4eff4"],'
        '"redaction_policy":"none","sharing":"project","user_visible_editing":"disabled"},'
        '"projection_mode":"debug_only","retrieval_terms":[],"revision":{"contradicted_by":[],"superseded_by":[],'
        '"supersedes":["legacy_entry_001"],"version":1},"schema_version":"memory_card.v1",'
        '"scope":{"branch_ref":null,"lane_id":null,"level":"repo","namespace":"repo:mew",'
        '"project_id":null,"repo_ref":"mew","task_family":null,"task_ref":null,"user_id":null},'
        '"staleness_state":"fresh","summary":"Typed memory cards store extracted claims, not raw transcript logs.",'
        '"timestamps":{"created_at":"2026-05-22T00:00:00Z","last_verified_at":null,'
        '"superseded_at":null,"tombstoned_at":null,"updated_at":"2026-05-22T00:01:00Z"},'
        '"valence":{"effect":"use","polarity":"neutral"}}'
    )
    assert card.stable_hash() == "sha256:81efbbaee31c356ecd9a8c4ae17bc4e78d00288d3dbe09c3d2e518ed0a492ffb"

    retired = card.to_dict()
    retired["projection"] = retired.pop("projection_mode")
    with pytest.raises(ValueError, match="retired projection"):
        MemoryCard.from_dict(retired)
    migrated = migrate_retired_memory_card_payload(retired)
    assert migrated["projection_mode"] == "debug_only"
    assert "projection" not in migrated

    bad_state = card.to_dict()
    bad_state["state"] = "committed"
    with pytest.raises(ValueError, match="MemoryState"):
        MemoryCard.from_dict(bad_state)

    minor = card.to_dict()
    minor["schema_version"] = "memory_card.v1.1"
    minor["x_optional_minor_field"] = {"ignored": True}
    assert MemoryCard.from_dict(minor).schema_version == "memory_card.v1.1"

    unknown_major = card.to_dict()
    unknown_major["schema_version"] = "memory_card.v2"
    with pytest.raises(ValueError, match="unknown"):
        MemoryCard.from_dict(unknown_major)


def test_committed_card_validation_rejects_missing_evidence_and_raw_transcript_leaks():
    with pytest.raises(ValueError, match="evidence_links"):
        _card(evidence_links=())

    with pytest.raises(ValueError, match="raw transcript"):
        _card(details="User: please remember this\nAssistant: I will store the whole chat")

    with pytest.raises(ValueError, match="provenance_excerpt"):
        _card(details='"' + ("quoted raw material " * 20) + '"')

    with pytest.raises(ValueError, match="summary"):
        _card(summary="x" * 513)


def test_evidence_applicability_invalidators_and_current_evidence_snapshot():
    file_node = _node("file", "file:mew:main:src/mew/memory_typed_cards.py")
    symbol_node = _node("symbol", "symbol:mew:main:src/mew/memory_typed_cards.py::MemoryCard")
    command_node = _node("command", "cmd:pytest tests/test_memory_typed_cards_phase_a.py")
    file_invalidator = Invalidator(
        kind="file_hash_changed",
        target_node_id=file_node.node_id,
        target_node_type="file",
        baseline_hash="sha256:old-file",
    )
    applicability = Applicability(
        applies_to=(file_node.node_id, "task_family:memory-subsystem", "workflow:phase-a"),
        prerequisites=("scope:v1:repo:6e65353668c4eff4",),
        counterexamples=("text:0123456789ab:not-for-runtime",),
    )
    snapshot = CurrentEvidenceSnapshot(
        repo_ref="mew",
        branch_ref="main",
        commit_ref="abc123",
        file_states=(
            FileEvidenceState(
                node_id=file_node.node_id,
                path="src/mew/memory_typed_cards.py",
                state="present",
                content_hash="sha256:new-file",
                observed_at=UPDATED,
            ),
        ),
        symbol_states=(
            SymbolEvidenceState(
                node_id=symbol_node.node_id,
                canonical_ref=symbol_node.canonical_ref,
                state="present",
                content_hash="sha256:symbol",
                observed_at=UPDATED,
            ),
        ),
        command_states=(
            CommandEvidenceState(
                node_id=command_node.node_id,
                normalized_command_ref=command_node.canonical_ref,
                command_hash="sha256:cmd",
                state="changed",
                observed_at=UPDATED,
            ),
        ),
        verifier_results=(
            VerifierEvidenceResult(
                verifier_ref="pytest-phase-a",
                result_hash="sha256:pytest",
                result_value="fail",
                applicability_refs=applicability.applies_to,
                task_ref="task:phase-a",
                error_signature_refs=("err:typed-card-validation",),
                observed_at=UPDATED,
                provenance_ref="prov_pytest",
            ),
        ),
        task_contract=TaskContractEvidence(ref="task:phase-a", hash="sha256:contract", value="Phase A only", observed_at=UPDATED),
        authority_events=(
            AuthorityEvidenceEvent(
                ref="auth_user_pref",
                source="user",
                strength="should",
                target_scope=_scope(),
                observed_at=UPDATED,
                supersedes_refs=("auth_old",),
            ),
        ),
    )

    assert file_invalidator.trigger_policy == "hash_changed"
    assert file_invalidator.target_node_type == "file"
    assert snapshot.verifier_results[0].applicability_refs[0].value == file_node.node_id
    assert snapshot.verifier_results[0].task_ref == "task:phase-a"
    assert snapshot.verifier_results[0].error_signature_refs == ("err:typed-card-validation",)
    assert "scoring" not in {event.source for event in snapshot.authority_events}
    assert stable_hash(file_invalidator.to_dict()) == "sha256:55c3d1ecb88812e78c603baa34b9d10c94ea7be7cfc5d598472cddc7361ccdcb"

    with pytest.raises(ValueError):
        AuthorityEvidenceEvent(
            ref="score-not-current-world-authority",
            source="scoring",
            strength="should",
            target_scope=_scope(),
            observed_at=UPDATED,
        )
    with pytest.raises(ValueError):
        ApplicabilityRef("free text is not a canonical ref")


def test_graph_refs_and_privacy_refs_require_canonical_ids():
    scope = _scope()
    canonical_edge_id = "edge:v1:b7db3b46894d4bc1"

    assert GraphRefs(edge_ids=(canonical_edge_id,)).edge_ids == (canonical_edge_id,)
    assert PrivacyRules(allowed_scope_ids=(scope.scope_key(), "shared_policy:v1:team-policy_1")).allowed_scope_ids == (
        "scope:v1:repo:6e65353668c4eff4",
        "shared_policy:v1:team-policy_1",
    )

    for bad_edge_id in ("edge-1", "edge:v1:B7DB3B46894D4BC1", "edge:v1:123"):
        with pytest.raises(ValueError, match="edge:v1"):
            GraphRefs(edge_ids=(bad_edge_id,))

    for bad_scope_id in (
        "scope:v1:repo:nothex",
        "scope:v1:unknown:6e65353668c4eff4",
        "scope:repo:6e65353668c4eff4",
        "shared_policy:v1:bad id",
    ):
        with pytest.raises(ValueError, match="allowed_scope_ids"):
            PrivacyRules(allowed_scope_ids=(bad_scope_id,))


def test_memory_candidate_golden_serialization_hash():
    scope = _scope()
    candidate = MemoryCandidate(
        candidate_id="cand_phase_a_001",
        proposed_kind="procedure",
        summary="Use typed-card schema tests before adding recall behavior.",
        details="This is proposal material only and cannot commit durable memory.",
        evidence_links=(_support_link("prov_candidate_support"),),
        proposed_scope=scope,
        proposed_authority=Authority(source="scoring", strength="hint", source_refs=("prov_candidate_support",)),
        proposed_valence=Valence(polarity="positive", effect="verify"),
        proposed_applicability=Applicability(applies_to=("workflow:phase-a", "task_family:memory-subsystem")),
        proposed_invalidators=(_manual_invalidator(),),
        confidence=0.81234,
        write_reason="schema-only proposal fixture",
        proposed_by="adapter",
    )

    assert stable_json(candidate.to_dict()) == (
        '{"candidate_id":"cand_phase_a_001","confidence":0.8123,'
        '"details":"This is proposal material only and cannot commit durable memory.",'
        '"evidence_links":[{"active":true,"added_by_mutation_id":"mut_001",'
        '"note":"supports extracted claim","ref_id":"prov_candidate_support","role":"current_support"}],'
        '"proposed_applicability":{"applies_to":["workflow:phase-a","task_family:memory-subsystem"],'
        '"counterexamples":[],"does_not_apply_to":[],"prerequisites":[]},'
        '"proposed_authority":{"source":"scoring","source_refs":["prov_candidate_support"],"strength":"hint"},'
        '"proposed_by":"adapter","proposed_invalidators":[{"baseline_hash":null,'
        '"baseline_observed_at":null,"baseline_ref":null,"baseline_value":null,"checked_at":null,'
        '"kind":"manual","manual_reason":"Reviewer asked to retire this if the design changes.",'
        '"metadata":{"source":"phase-a-test"},"ref":null,"target_node_id":null,'
        '"target_node_type":null,"trigger_policy":"manual_only"}],"proposed_kind":"procedure",'
        '"proposed_scope":{"branch_ref":null,"lane_id":null,"level":"repo","namespace":"repo:mew",'
        '"project_id":null,"repo_ref":"mew","task_family":null,"task_ref":null,"user_id":null},'
        '"proposed_valence":{"effect":"verify","polarity":"positive"},'
        '"retrieval_terms":[],'
        '"summary":"Use typed-card schema tests before adding recall behavior.",'
        '"write_reason":"schema-only proposal fixture"}'
    )
    assert candidate.stable_hash() == "sha256:36874c5860ea8c5f25de744d2a55e01515bd65c49f1a4139f6d21d8fc2d364a4"


def test_graph_edge_schema_uses_canonical_actor_edges_and_evidence_links():
    card_node = _node("memory_card", "mem_phase_a_001")
    file_node = _node("file", "file:mew:main:src/mew/memory_typed_cards.py")
    actor_node = GraphNode.build(
        node_type="actor",
        scope=_scope(),
        canonical_ref=pseudonymous_actor_ref("reviewer", "reviewer-1", scope_key=_scope().scope_key()),
        display_name="reviewer",
        metadata={"actor_kind": "reviewer"},
        created_at=CREATED,
        updated_at=UPDATED,
    )
    edge = GraphEdge.build(
        from_node_id=card_node.node_id,
        from_node_type="memory_card",
        to_node_id=actor_node.node_id,
        to_node_type="actor",
        edge_type="approved_by",
        scope=_scope(),
        evidence_links=(EvidenceLink(ref_id="prov_approval_001", role="approval"),),
        confidence=0.75,
        created_at=CREATED,
        updated_at=UPDATED,
    )

    assert edge.edge_id == "edge:v1:b7db3b46894d4bc1"
    assert edge.evidence_links[0].role == "approval"
    assert edge.to_node_type == "actor"

    support_edge = GraphEdge.build(
        from_node_id=card_node.node_id,
        from_node_type="memory_card",
        to_node_id=file_node.node_id,
        to_node_type="file",
        edge_type="supports",
        scope=_scope(),
        evidence_links=(EvidenceLink(ref_id="prov_support_001", role="current_support"),),
        confidence=0.75,
        created_at=CREATED,
        updated_at=UPDATED,
    )
    assert support_edge.edge_type == "supports"

    with pytest.raises(ValueError, match="node_type=actor"):
        GraphEdge.build(
            from_node_id=card_node.node_id,
            from_node_type="memory_card",
            to_node_id=file_node.node_id,
            to_node_type="file",
            edge_type="approved_by",
            scope=_scope(),
            evidence_links=(EvidenceLink(ref_id="prov_approval_001", role="approval"),),
            created_at=CREATED,
            updated_at=UPDATED,
        )

    with pytest.raises(ValueError, match="active evidence"):
        GraphEdge.build(
            from_node_id=card_node.node_id,
            from_node_type="memory_card",
            to_node_id=file_node.node_id,
            to_node_type="file",
            edge_type="supports",
            scope=_scope(),
            evidence_links=(EvidenceLink(ref_id="prov_approval_001", role="approval"),),
            created_at=CREATED,
            updated_at=UPDATED,
        )

    with pytest.raises(ValueError, match="active evidence"):
        GraphEdge.build(
            from_node_id=card_node.node_id,
            from_node_type="memory_card",
            to_node_id=file_node.node_id,
            to_node_type="file",
            edge_type="proved_by",
            scope=_scope(),
            evidence_links=(EvidenceLink(ref_id="prov_support_001", role="current_support", active=False),),
            created_at=CREATED,
            updated_at=UPDATED,
        )

    with pytest.raises(ValueError, match="active evidence"):
        GraphEdge.build(
            from_node_id=card_node.node_id,
            from_node_type="memory_card",
            to_node_id=actor_node.node_id,
            to_node_type="actor",
            edge_type="migrated_by",
            scope=_scope(),
            evidence_links=(EvidenceLink(ref_id="prov_approval_001", role="approval"),),
            created_at=CREATED,
            updated_at=UPDATED,
        )


def test_audit_trace_shape_alignment_and_audit_payload_safeguards():
    trace = MemoryTraceEvent(
        operation="migrate",
        request_hash="sha256:req",
        result_hash="sha256:res",
        actor="migration",
        card_ids=("mem_b", "mem_a"),
        provenance_event_ids=("prov_a",),
        mutation_ids=("mut_b", "mut_a"),
        dropped=(DroppedReason(reason="quarantined", ref_id="legacy_bad", detail="unknown scope"),),
        usage={"counts": {"migrated": 1}},
        metadata={"source_store_version": "legacy", "target_schema_version": "memory_card.v1"},
    )
    audit = MemoryAuditEvent.from_trace(trace, audit_id="audit_migrate_001", created_at=CREATED)

    assert audit.logical_payload() == trace.to_dict()
    assert audit.to_dict()["audit_id"] == "audit_migrate_001"
    assert audit.to_dict()["created_at"] == CREATED
    assert audit.actor == "migration"
    assert audit.mutation_ids == ("mut_a", "mut_b")

    with pytest.raises(ValueError, match="provenance"):
        MemoryTraceEvent(
            operation="retrieve",
            request_hash="sha256:req",
            result_hash="sha256:res",
            actor="core",
            metadata={"raw_text": "User: " + ("raw transcript " * 30)},
        )


def test_legacy_memory_entry_migration_is_deterministic_and_quarantines_unknown_scope():
    legacy = {
        "entry_id": "legacy-1",
        "memory_kind": "project_convention",
        "scope": "repo:mew",
        "summary": "Run focused schema tests for typed memory changes.",
        "body": "A short extracted legacy body.",
        "applicability": "typed memory phase a",
        "source_refs": [{"ref_id": "legacy-source"}],
        "proof_refs": [{"ref_id": "legacy-proof"}],
        "approved": True,
        "created_at": CREATED,
        "last_verified_at": UPDATED,
        "confidence": 0.91,
    }

    first = migrate_legacy_memory_entry(legacy)
    second = migrate_legacy_memory_entry(dict(reversed(list(legacy.items()))))

    assert first.to_dict() == second.to_dict()
    assert first.quarantined is False
    assert first.recallable is True
    assert first.card is not None
    assert first.card.kind == "semantic_fact"
    assert first.card.approval_state == "committed"
    assert first.card.revision.supersedes == ("legacy-1",)

    unknown_scope = migrate_legacy_memory_entry({**legacy, "scope": "global-ish free text"})
    assert unknown_scope.quarantined is True
    assert unknown_scope.recallable is False
    assert unknown_scope.card is None

    unknown_kind = migrate_legacy_memory_entry({**legacy, "memory_kind": "working/reentry"})
    assert unknown_kind.quarantined is True
    assert unknown_kind.target_kind is None


def test_typed_memory_phase_a_core_has_no_forbidden_imports():
    source = Path("src/mew/memory_typed_cards.py").read_text(encoding="utf-8")
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
