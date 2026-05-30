import json
from pathlib import Path

import pytest

from mew.memory_core import (
    Contradiction,
    GraphEdge,
    InMemoryMemoryStore,
    JsonFileMemoryStore,
    MemoryAdaptRecallRequest,
    MemoryApprovalRequest,
    MemoryCompressionRequest,
    MemoryCandidateRequest,
    MemoryChainRequest,
    MemoryCommitRequest,
    MemoryEntry,
    MemoryInspectRequest,
    MemoryProjectRequest,
    MemoryProposalRequest,
    MemoryRecallBudget,
    MemoryRecallRequest,
    MemorySystem,
    MemoryTombstoneRequest,
    ProvenanceRef,
    Revision,
    Staleness,
)
from mew.memory_compression import compress_memory_with_model, memory_compression_prompt


FORBIDDEN_RECALL_FIELDS = {
    "next_action",
    "required_next",
    "planner",
    "policy",
    "tool_to_call",
    "should_edit",
    "finish_ready",
}


def _ref(ref_id="src-1", ref_kind="file_snapshot"):
    return ProvenanceRef(
        ref_id=ref_id,
        ref_kind=ref_kind,
        artifact_path_or_uri=f"mew://artifact/{ref_id}",
        content_hash=f"sha256:{ref_id}",
        excerpt_hash=f"sha256:{ref_id}:excerpt",
        timestamp="2026-05-20T00:00:00Z",
        producer="test",
    )


def _entry(**overrides):
    values = {
        "entry_id": "mem-1",
        "memory_kind": "project_convention",
        "scope": "repo:mew",
        "title": "Verifier ordering convention",
        "summary": "Run focused tests before broad verification when changing memory core.",
        "applicability": "mew memory subsystem implementation",
        "source_refs": (_ref("source-1"),),
        "proof_refs": (_ref("proof-1", "reviewer_approval"),),
        "created_at": "2026-05-20T00:00:00Z",
        "last_verified_at": "2026-05-20T01:00:00Z",
        "validity": "valid",
        "confidence": 0.9,
    }
    values.update(overrides)
    return MemoryEntry(**values)


def _assert_no_forbidden_fields(value):
    if isinstance(value, dict):
        assert FORBIDDEN_RECALL_FIELDS.isdisjoint(value.keys())
        for child in value.values():
            _assert_no_forbidden_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_fields(child)


def test_memory_core_schema_shapes_are_implementation_facing():
    stale = Staleness(
        state="maybe_stale",
        reasons=("file changed",),
        invalidators=(_ref("invalidate-1", "static_analysis"),),
        checked_at="2026-05-20T02:00:00Z",
    )
    contradiction = Contradiction(
        state="possible",
        contradicting_entry_ids=("mem-old",),
        contradicting_provenance_refs=(_ref("contra-1", "reviewer_comment"),),
        resolution="Prefer newer proof.",
    )
    edge = GraphEdge(
        edge_id="edge-1",
        source_entry_id="mem-1",
        target_entry_id="mem-2",
        edge_kind="supports",
        evidence_refs=(_ref("edge-proof"),),
        confidence=0.8,
    )
    entry = _entry(
        staleness=stale,
        contradiction=contradiction,
        revision=Revision(
            revision_id="rev-2",
            previous_entry_id="mem-old",
            supersedes_entry_ids=("mem-old",),
        ),
        graph_edges=(edge,),
        budgets={"max_chars": 400},
    )

    data = entry.to_dict()

    assert data["schema_version"] == 1
    assert data["memory_kind"] == "project_convention"
    assert data["staleness"]["state"] == "maybe_stale"
    assert data["contradiction"]["state"] == "possible"
    assert data["revision"]["previous_entry_id"] == "mem-old"
    assert data["graph_edges"][0]["edge_kind"] == "supports"
    assert data["source_refs"][0]["content_hash"] == "sha256:source-1"


def test_recall_is_direct_read_only_and_returns_evidence_context_only():
    system = MemorySystem.from_entries([_entry()])

    result = system.recall(
        MemoryRecallRequest(
            query="focused tests memory core",
            scope="repo:mew",
            memory_kinds=("project_convention",),
            limit=3,
            budget=MemoryRecallBudget(max_results=2, max_chars=1200),
        )
    )
    data = result.to_dict()

    assert len(result.candidates) == 1
    assert result.candidates[0].entry_id == "mem-1"
    assert result.candidates[0].evidence_refs[0].ref_id == "source-1"
    assert result.chains == ()
    _assert_no_forbidden_fields(data)
    assert data["trace"]["request_hash"]
    assert data["trace"]["result_hash"]
    assert data["trace"]["store_id"] == "memory:in-memory"
    assert data["trace"]["index_id"] == "memory:index:in-memory"
    assert data["budget_used"]["returned_results"] == 1
    assert system.traces[-1].trace_ref == result.trace_ref


def test_recall_why_relevant_lists_only_matched_terms():
    system = MemorySystem.from_entries(
        [
            _entry(
                entry_id="term-test",
                title="Alpha convention",
                summary="Alpha durable evidence.",
                applicability="Applies to alpha-only fixture.",
            )
        ]
    )

    result = system.recall(MemoryRecallRequest(query="alpha omega"))

    assert result.candidates[0].why_relevant == "Matched query terms: alpha"
    assert "omega" not in result.candidates[0].why_relevant


def test_recall_filters_unapproved_tombstoned_stale_and_mismatched_entries():
    entries = [
        _entry(entry_id="good", summary="Useful direct recall evidence."),
        _entry(entry_id="unapproved", approved=False),
        _entry(entry_id="tombstoned", revision=Revision(tombstoned=True)),
        _entry(entry_id="stale", staleness=Staleness(state="stale")),
        _entry(entry_id="other-kind", memory_kind="user_preference"),
        _entry(entry_id="query-miss", summary="Completely unrelated note."),
    ]
    system = MemorySystem(InMemoryMemoryStore(entries))

    result = system.recall(
        MemoryRecallRequest(
            query="useful direct recall evidence",
            memory_kinds=("project_convention",),
            limit=5,
        )
    )

    assert [item.entry_id for item in result.candidates] == ["good"]
    assert result.dropped["not_committed_approved_memory"] == 2
    assert result.dropped["stale_excluded"] == 1
    assert result.dropped["memory_kind_mismatch"] == 1
    assert result.dropped["query_mismatch"] == 1
    assert result.trace.dropped_reasons == result.dropped


def test_recall_drops_uncited_approved_committed_entries():
    entries = [
        _entry(entry_id="good", summary="Cited durable recall evidence."),
        _entry(entry_id="no-source", summary="Cited durable recall evidence.", source_refs=()),
        _entry(entry_id="no-proof", summary="Cited durable recall evidence.", proof_refs=()),
    ]
    system = MemorySystem(InMemoryMemoryStore(entries))

    result = system.recall(MemoryRecallRequest(query="cited durable recall evidence"))

    assert [item.entry_id for item in result.candidates] == ["good"]
    assert result.dropped["uncited_memory"] == 2
    assert result.trace.dropped_reasons["uncited_memory"] == 2


def test_inspect_entry_debug_read_returns_sanitized_entry_and_trace():
    system = MemorySystem.from_entries([_entry()])

    result = system.inspect_entry(MemoryInspectRequest(entry_id="mem-1"))
    missing = system.inspect_entry(MemoryInspectRequest(entry_id="missing"))

    assert result.entry is not None
    assert result.entry.entry_id == "mem-1"
    assert result.to_dict()["entry"]["proof_refs"][0]["ref_kind"] == "reviewer_approval"
    assert result.trace.event == "inspect_entry"
    assert missing.entry is None
    assert missing.dropped == {"not_found": 1}


def test_raw_provenance_refs_do_not_become_durable_memory_payloads():
    raw_ref = _ref("raw-1", "raw_transcript")
    entry = _entry(
        source_refs=(raw_ref,),
        summary="Only the extracted convention is durable.",
        applicability="Applies when testing raw provenance boundaries.",
    )
    system = MemorySystem.from_entries([entry])

    result = system.recall(MemoryRecallRequest(query="extracted convention"))
    candidate = result.to_dict()["candidates"][0]

    assert candidate["summary"] == "Only the extracted convention is durable."
    assert candidate["evidence_refs"][0]["ref_kind"] == "raw_transcript"
    assert set(candidate["evidence_refs"][0]) == {
        "ref_id",
        "ref_kind",
        "artifact_path_or_uri",
        "content_hash",
        "excerpt_hash",
        "timestamp",
        "producer",
    }
    assert "transcript" not in candidate
    with pytest.raises(ValueError, match="raw provenance kinds"):
        _entry(memory_kind="raw_transcript")


def test_json_file_store_loads_entries_without_write_api(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"entries": [_entry().to_dict()]}), encoding="utf-8")
    system = MemorySystem(JsonFileMemoryStore(path))

    result = system.recall(MemoryRecallRequest(query="verifier ordering"))

    assert result.candidates[0].title == "Verifier ordering convention"
    assert result.trace.store_id.startswith(f"memory:json:{path}")
    assert not hasattr(system.store, "write")


def test_write_path_preserves_candidate_proposal_approval_commit_separation():
    system = MemorySystem()

    candidate = system.write_candidate(
        MemoryCandidateRequest(
            memory_kind="project_convention",
            scope="repo:mew",
            title="Memory core citation rule",
            summary="Recallable memory entries must include source and proof refs.",
            applicability="Phase 1b write path",
            source_refs=(_ref("candidate-source"),),
            created_at="2026-05-20T03:00:00Z",
            confidence=0.8,
        )
    ).candidate
    assert system.recall(MemoryRecallRequest(query="citation rule")).candidates == ()

    proposal = system.propose_memory(
        MemoryProposalRequest(
            candidate_id=candidate.candidate_id,
            proof_refs=(_ref("proposal-proof", "verifier_log"),),
            proposed_at="2026-05-20T03:01:00Z",
            last_verified_at="2026-05-20T03:02:00Z",
            previous_entry_id="old-entry",
            supersedes_entry_ids=("old-entry",),
        )
    ).proposal
    assert system.recall(MemoryRecallRequest(query="citation rule")).candidates == ()
    with pytest.raises(ValueError, match="requires an approval"):
        system.commit_memory(MemoryCommitRequest(proposal_id=proposal.proposal_id, approval_id="missing"))

    approval = system.approve(
        MemoryApprovalRequest(
            proposal_id=proposal.proposal_id,
            approved_by="reviewer",
            approval_refs=(_ref("approval-proof", "reviewer_approval"),),
            approved_at="2026-05-20T03:03:00Z",
            reason="explicit review approval",
        )
    ).approval
    committed = system.commit_memory(
        MemoryCommitRequest(
            proposal_id=proposal.proposal_id,
            approval_id=approval.approval_id,
            entry_id="committed-memory",
            revision_id="rev-committed",
        )
    ).entry

    result = system.recall(MemoryRecallRequest(query="citation rule"))

    assert [item.entry_id for item in result.candidates] == ["committed-memory"]
    assert committed.approved is True
    assert committed.lifecycle_state == "committed"
    assert committed.revision.revision_id == "rev-committed"
    assert committed.revision.previous_entry_id == "old-entry"
    assert committed.revision.supersedes_entry_ids == ("old-entry",)
    assert [ref.ref_id for ref in committed.source_refs] == ["candidate-source"]
    assert [ref.ref_id for ref in committed.proof_refs] == ["proposal-proof", "approval-proof"]


def test_compress_memory_creates_small_candidate_without_raw_payload():
    system = MemorySystem()
    raw_text = "\n".join(
        [
            "The session inspected a large transcript and many routine reads.",
            "Reviewer decision: use apply_patch for source edits and avoid shell heredocs.",
            "The final proof passed after focused tests.",
            "Extra details " + "noise " * 80,
        ]
    )

    result = system.compress_memory(
        MemoryCompressionRequest(
            raw_text=raw_text,
            memory_kind="reviewer_correction",
            scope="repo:mew",
            title_hint="Source edit convention",
            applicability_hint="Use when planning source edits.",
            source_refs=(_ref("compression-source", "raw_transcript"),),
            created_at="2026-05-21T00:00:00Z",
            confidence=0.7,
            max_summary_chars=180,
        )
    )

    assert result.action == "candidate"
    assert result.candidate is not None
    assert result.candidate.entry_shape.title == "Source edit convention"
    assert result.candidate.entry_shape.memory_kind == "reviewer_correction"
    assert len(result.summary) <= 180
    assert "Reviewer decision" in result.summary
    assert "proof passed" in result.summary
    assert "noise noise noise noise noise noise" not in result.summary
    assert result.salience_terms
    assert result.trace.event == "compress_memory"
    assert system.recall(MemoryRecallRequest(query="apply_patch heredocs")).candidates == ()


def test_compress_memory_points_similar_information_to_existing_entry():
    existing = _entry(
        entry_id="edit-convention",
        memory_kind="reviewer_correction",
        title="Source edit convention",
        summary="Reviewer decision: use apply_patch for source edits and avoid shell heredocs.",
        applicability="Use when planning source edits.",
    )
    system = MemorySystem.from_entries([existing])

    result = system.compress_memory(
        MemoryCompressionRequest(
            raw_text="Reviewer decision: use apply_patch for source edits and avoid shell heredocs.",
            memory_kind="reviewer_correction",
            scope="repo:mew",
            source_refs=(_ref("similar-source", "raw_transcript"),),
            created_at="2026-05-21T00:00:00Z",
            merge_similarity_threshold=0.5,
        )
    )

    assert result.action == "merge_existing"
    assert result.merge_target_entry_id == "edit-convention"
    assert result.candidate is None
    assert result.dropped == {"similar_existing_memory": 1}
    assert system.candidates == {}


def test_llm_memory_compression_uses_model_card_before_candidate_creation():
    system = MemorySystem()
    calls = []

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
        return {
            "title": "Patch edit discipline",
            "summary": "Use apply_patch for source edits and avoid shell heredocs.",
            "applicability": "Use when editing repository source files.",
            "confidence": 0.88,
        }

    request = MemoryCompressionRequest(
        raw_text="Huge raw transcript. Reviewer said source edits should use apply_patch, not shell heredocs.",
        memory_kind="reviewer_correction",
        scope="repo:mew",
        source_refs=(_ref("llm-source", "raw_transcript"),),
        created_at="2026-05-21T00:00:00Z",
    )
    result = compress_memory_with_model(
        system,
        request,
        model_auth={"path": "auth.json", "access_token": "redacted"},
        model_backend="codex",
        model="gpt-5.5",
        timeout=30,
        call_json=fake_call_json,
    )

    assert calls
    assert calls[0]["model_auth"]["path"] == "auth.json"
    assert "raw_text" in calls[0]["prompt"]
    assert result.action == "candidate"
    assert result.candidate is not None
    assert result.candidate.entry_shape.title == "Patch edit discipline"
    assert result.candidate.entry_shape.summary == "Use apply_patch for source edits and avoid shell heredocs."
    assert result.candidate.entry_shape.confidence == 0.88


def test_memory_compression_prompt_has_no_hidden_raw_storage_policy():
    request = MemoryCompressionRequest(
        raw_text="raw transcript with a useful reviewer decision",
        memory_kind="reviewer_correction",
        scope="repo:mew",
        source_refs=(_ref("prompt-source", "raw_transcript"),),
        created_at="2026-05-21T00:00:00Z",
    )

    prompt = memory_compression_prompt(request)

    assert "Do not copy raw transcript; compress it." in prompt
    assert "provenance refs already point to raw data" in prompt
    assert "reviewer_correction" in prompt


def test_commit_memory_rejects_second_commit_for_same_approved_proposal():
    system = MemorySystem()
    candidate = system.write_candidate(
        MemoryCandidateRequest(
            memory_kind="project_convention",
            scope="repo:mew",
            title="Single materialization rule",
            summary="One approved proposal commits to one durable memory entry.",
            applicability="Phase 1b write audit",
            source_refs=(_ref("single-source"),),
            created_at="2026-05-20T03:00:00Z",
            confidence=0.8,
        )
    ).candidate
    proposal = system.propose_memory(
        MemoryProposalRequest(
            candidate_id=candidate.candidate_id,
            proof_refs=(_ref("single-proof", "verifier_log"),),
            proposed_at="2026-05-20T03:01:00Z",
        )
    ).proposal
    approval = system.approve(
        MemoryApprovalRequest(
            proposal_id=proposal.proposal_id,
            approved_by="reviewer",
            approval_refs=(_ref("single-approval", "reviewer_approval"),),
            approved_at="2026-05-20T03:02:00Z",
            reason="explicit review approval",
        )
    ).approval

    system.commit_memory(
        MemoryCommitRequest(
            proposal_id=proposal.proposal_id,
            approval_id=approval.approval_id,
            entry_id="single-entry",
        )
    )
    with pytest.raises(ValueError, match="already committed"):
        system.commit_memory(
            MemoryCommitRequest(
                proposal_id=proposal.proposal_id,
                approval_id=approval.approval_id,
                entry_id="single-entry-2",
            )
        )


def test_write_path_rejects_raw_provenance_as_memory_candidate():
    with pytest.raises(ValueError, match="raw provenance kinds"):
        MemoryCandidateRequest(
            memory_kind="raw_transcript",
            scope="repo:mew",
            title="Raw transcript",
            summary="This must stay provenance only.",
            applicability="never durable",
            source_refs=(_ref("raw-source", "raw_transcript"),),
            created_at="2026-05-20T03:00:00Z",
        )


def test_tombstone_makes_committed_entry_non_recallable_with_revision_metadata():
    system = MemorySystem.from_entries([_entry(entry_id="to-remove", summary="Retired memory note.")])

    tombstoned = system.tombstone_entry(
        MemoryTombstoneRequest(
            entry_id="to-remove",
            reason="superseded by newer convention",
            tombstone_ref=_ref("tombstone-proof", "reviewer_approval"),
            revision_id="rev-tombstone",
        )
    ).entry
    result = system.recall(MemoryRecallRequest(query="retired memory note"))

    assert result.candidates == ()
    assert result.dropped["not_committed_approved_memory"] == 1
    assert tombstoned.lifecycle_state == "tombstoned"
    assert tombstoned.revision.tombstoned is True
    assert tombstoned.revision.tombstone_reason == "superseded by newer convention"
    assert tombstoned.revision.previous_entry_id == "rev-1"
    assert tombstoned.proof_refs[-1].ref_id == "tombstone-proof"


def test_adapt_recall_is_read_side_fit_drop_with_trace():
    system = MemorySystem.from_entries(
        [
            _entry(entry_id="keep", summary="Reusable focused memory guidance.", confidence=0.9),
            _entry(entry_id="low", summary="Reusable focused memory guidance.", confidence=0.2),
            _entry(
                entry_id="stale",
                summary="Reusable focused memory guidance.",
                staleness=Staleness(state="stale"),
            ),
            _entry(
                entry_id="wrong-kind",
                memory_kind="user_preference",
                summary="Reusable focused memory guidance.",
            ),
        ]
    )
    recall = system.recall(MemoryRecallRequest(query="reusable focused memory", include_stale=True))

    adapted = system.adapt_recall(
        MemoryAdaptRecallRequest(
            recall_result=recall,
            min_confidence=0.5,
            allowed_kinds=("project_convention",),
            include_stale=False,
        )
    )

    assert [item.entry_id for item in adapted.candidates] == ["keep"]
    assert adapted.dropped["low_confidence"] == 1
    assert adapted.dropped["stale_excluded"] == 1
    assert adapted.dropped["memory_kind_mismatch"] == 1
    assert adapted.trace.event == "adapt_recall"
    assert system.store.get_entry("keep").lifecycle_state == "committed"


def test_expand_chain_is_bounded_and_returns_evidence_nodes_only():
    edge_ab = GraphEdge(
        edge_id="edge-ab",
        source_entry_id="a",
        target_entry_id="b",
        edge_kind="supports",
        evidence_refs=(_ref("edge-ab-proof"),),
    )
    edge_ac = GraphEdge(
        edge_id="edge-ac",
        source_entry_id="a",
        target_entry_id="c",
        edge_kind="supports",
        evidence_refs=(_ref("edge-ac-proof"),),
    )
    system = MemorySystem.from_entries(
        [
            _entry(entry_id="a", summary="Root chain memory.", graph_edges=(edge_ab, edge_ac)),
            _entry(entry_id="b", memory_kind="procedural_repair", summary="Supported chain memory."),
            _entry(entry_id="c", memory_kind="failure_shield", summary="Dropped by fanout."),
        ]
    )

    chain = system.expand_chain(
        MemoryChainRequest(start_entry_ids=("a",), max_depth=1, max_fanout=1, max_nodes=5)
    )
    data = chain.to_dict()

    assert [node.entry_id for node in chain.nodes] == ["a", "b"]
    assert [edge.edge_id for edge in chain.edges] == ["edge-ab"]
    assert chain.dropped["budget_fanout_limit"] == 1
    assert data["nodes"][0]["evidence_refs"][0]["ref_id"] == "source-1"
    _assert_no_forbidden_fields(data)


def test_project_is_dormant_interface_only_with_no_projection_content():
    system = MemorySystem.from_entries([_entry()])

    result = system.project(MemoryProjectRequest())
    data = result.to_dict()

    assert result.enabled is False
    assert "deferred" in result.deferred_reason
    assert "candidates" not in data
    assert "projection" not in data
    assert result.trace.event == "project"


def test_phase_1b_does_not_wire_memory_into_forbidden_surfaces():
    root = Path(__file__).resolve().parents[1]
    forbidden_paths = [
        root / "src" / "mew" / "implement_lane" / "tool_registry.py",
        root / "src" / "mew" / "implement_lane" / "prompt.py",
        root / "src" / "mew" / "implement_lane" / "native_tool_harness.py",
    ]

    for path in forbidden_paths:
        text = path.read_text(encoding="utf-8")
        assert "MemoryToolProvider" not in text
        assert "memory_core" not in text
