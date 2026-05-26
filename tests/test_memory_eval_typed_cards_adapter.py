from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from mew.memory_eval.adapters import TypedCardsMemoryEvalAdapter
from mew.memory_eval.runner import run_fixture
from mew.memory_typed_cards import EvidenceLink, GraphEdge, GraphNode, GraphRefs


ROOT = Path(__file__).resolve().parents[1]
P0_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p0"
P1_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p1"
GRAPH_FIXTURE = P1_FIXTURES / "graph_expansion_basic.json"
GRAPH_EDGE_FIXTURE = P1_FIXTURES / "graph_edge_expansion_basic.json"
GRAPH_CROSS_SCOPE_FIXTURE = P1_FIXTURES / "graph_cross_scope_no_leak_basic.json"
GRAPH_FORGET_FIXTURE = P1_FIXTURES / "graph_forget_no_leak_basic.json"
GRAPH_STALE_ENDPOINT_FIXTURE = P1_FIXTURES / "graph_stale_endpoint_no_leak_basic.json"
GRAPH_UNCANONICALIZED_ENDPOINT_FIXTURE = P1_FIXTURES / "graph_uncanonicalized_endpoint_no_leak_basic.json"
RELATION_NIECE_COMPANY_FIXTURE = P1_FIXTURES / "relation_sensitive_niece_company_basic.json"


PHASE_C_PASS_FIXTURES = [
    P0_FIXTURES / "dummy_happy_path.json",
    P1_FIXTURES / "memory_off_no_prior_memory_basic.json",
    P1_FIXTURES / "memory_on_happy_path_basic.json",
    P1_FIXTURES / "retrieval_ranking_basic.json",
    RELATION_NIECE_COMPANY_FIXTURE,
    P1_FIXTURES / "scope_isolation_basic.json",
    P1_FIXTURES / "stale_conflict_supersede_basic.json",
    P1_FIXTURES / "update_forget_basic.json",
    P1_FIXTURES / "abstention_no_memory_basic.json",
    P1_FIXTURES / "budget_limited_basic.json",
]


def _experience(
    experience_id: str = "ex_public",
    *,
    scope_id: str = "tenant_a/user_a",
    text: str = "Mira prefers green tea for planning breaks.",
) -> dict:
    return {
        "experience_id": experience_id,
        "scope_id": scope_id,
        "session_id": "session_test",
        "turn_id": "turn_001",
        "event_time": "2026-01-10T09:00:00Z",
        "ingest_order": 1,
        "actor_id": "user_a",
        "payload": {"mime_type": "text/plain", "text": text},
        "visibility": {"allowed_scope_ids": [scope_id], "retrievable": True},
    }


def _live_candidate_payload(summary: str = "Mira's planning-break drink preference is green tea.") -> dict:
    return {
        "decision": "candidate",
        "candidate": {
            "kind": "semantic_fact",
            "summary": summary,
            "details": "Fake live extractor output for adapter tests.",
            "confidence": 0.88,
            "authority": {"source": "self", "strength": "hint"},
            "valence": {"polarity": "neutral", "effect": "use"},
            "proposed_by": "model",
        },
    }


def _fixture_with_seed_lifecycle(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["fixture_id"] = f"{fixture['fixture_id']}_typed_lifecycle"
    setup_mutations = []
    rewritten_sequence = []
    for operation in fixture.get("operation_sequence") or []:
        rewritten_sequence.append(dict(operation))
        if operation.get("type") != "ingest":
            continue
        setup_op_id = f"setup_seed_{len(setup_mutations) + 1:06d}"
        setup_mutations.append(
            {
                "op_id": setup_op_id,
                "mutation_type": "seed_eval",
                "target_experience_id": operation["experience_id"],
                "effective_time": fixture["evaluation_time"],
                "reason": "phase c public setup",
            }
        )
        rewritten_sequence.append(
            {
                "type": "mutate",
                "op_id": setup_op_id,
                "ingest_order": operation.get("ingest_order", len(rewritten_sequence)),
            }
        )
    fixture["mutations"] = [*setup_mutations, *(fixture.get("mutations") or [])]
    fixture["operation_sequence"] = rewritten_sequence
    return fixture


@pytest.mark.parametrize("fixture_path", PHASE_C_PASS_FIXTURES, ids=lambda path: path.name)
def test_typed_cards_adapter_passes_p0_p1_fixtures_with_public_lifecycle_seed(fixture_path: Path) -> None:
    artifact = run_fixture(
        _fixture_with_seed_lifecycle(fixture_path),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["failures"] == []


def test_typed_cards_manifest_declares_mutate_lifecycle_setup_policy() -> None:
    manifest = TypedCardsMemoryEvalAdapter().manifest()

    assert manifest["capability_tier"] == "mutable_retrieval"
    assert manifest["setup_routing"] == "mutate_lifecycle"
    assert manifest["setup_policy"] == "explicit_mutate_lifecycle"
    assert manifest["extractor"]["live_llm"] is False
    assert manifest["extractor"]["mode"] == "deterministic_replay"
    assert manifest["extractor"]["external_model_ids"] == []
    assert manifest["external_model_ids"] == []
    assert manifest["capabilities"]["seed_eval"] is True
    assert manifest["capabilities"]["update"] is True
    assert manifest["capabilities"]["forget"] is True
    assert manifest["capabilities"]["derived_graph_index_verification"] is True


def test_live_model_manifest_declares_model_binding_without_token_material() -> None:
    adapter = TypedCardsMemoryEvalAdapter(
        extractor_mode="live_model",
        model_auth={"access_token": "super-secret-token", "refresh_token": "also-secret"},
    )
    manifest = adapter.manifest()
    manifest_text = json.dumps(manifest, sort_keys=True)

    assert manifest["extractor"]["mode"] == "live_model"
    assert manifest["extractor"]["live_llm"] is True
    assert manifest["extractor"]["backend"] == "codex"
    assert manifest["extractor"]["model"] == "gpt-5.5"
    assert manifest["extractor"]["auth_path"] == "auth.json"
    assert manifest["extractor"]["call_interface"] == "call_model_structured_json"
    assert manifest["extractor"]["external_model_ids"] == ["codex:gpt-5.5"]
    assert manifest["external_model_ids"] == ["codex:gpt-5.5"]
    assert "super-secret-token" not in manifest_text
    assert "also-secret" not in manifest_text
    assert "access_token" not in manifest_text
    assert "refresh_token" not in manifest_text


def test_live_model_mode_uses_model_raw_extractor_with_injected_callers() -> None:
    calls = []
    loads = []

    def fake_load_auth(backend, auth_path):
        loads.append((backend, auth_path))
        return {"path": auth_path, "access_token": "redacted-test-token"}

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
        return _live_candidate_payload()

    adapter = TypedCardsMemoryEvalAdapter.live_model(
        load_auth=fake_load_auth,
        call_json=fake_call_json,
        timeout=17,
    )
    adapter.reset({"fixture_id": "fx_live", "evaluation_time": "2026-05-21T00:00:00Z"})

    ingest = adapter.ingest([_experience()])[0]
    seed = adapter.mutate(
        [
            {
                "op_id": "seed_live",
                "lifecycle_type": "seed_eval",
                "target_experience_id": "ex_public",
            }
        ]
    )[0]

    assert ingest["status"] == "success"
    assert ingest["status_reason"] == "proposed"
    assert ingest["proposal_ids"]
    assert seed["status"] == "success"
    assert seed["card_ids"]
    assert loads == [("codex", "auth.json")]
    assert calls[0]["model_backend"] == "codex"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["model_auth"]["path"] == "auth.json"
    assert calls[0]["base_url"] == ""
    assert calls[0]["timeout"] == 17
    assert "Mira prefers green tea for planning breaks." in calls[0]["prompt"]


def test_live_model_mode_uses_structured_extractor_when_injected() -> None:
    calls = []

    def fake_load_auth(backend, auth_path):
        return {"path": auth_path, "access_token": "redacted-test-token"}

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
        return _live_candidate_payload()

    adapter = TypedCardsMemoryEvalAdapter.live_model(
        load_auth=fake_load_auth,
        call_structured_json=fake_call_structured_json,
        timeout=17,
    )
    adapter.reset({"fixture_id": "fx_live_structured", "evaluation_time": "2026-05-21T00:00:00Z"})

    ingest = adapter.ingest([_experience()])[0]

    assert ingest["status"] == "success"
    assert ingest["proposal_ids"]
    assert calls[0]["model_backend"] == "codex"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["schema_name"] == "raw_memory_extraction"
    assert calls[0]["json_schema"]["properties"]["decision"]["enum"] == [
        "candidate",
        "reject",
        "clarification_needed",
    ]
    assert "retrieval_terms" in calls[0]["json_schema"]["properties"]["candidate"]["required"]
    assert "graph_edges" in calls[0]["json_schema"]["properties"]["candidate"]["required"]
    assert calls[0]["strict"] is True
    assert "default_scope_key" in calls[0]["prompt"]
    assert "retrieval_terms" in calls[0]["prompt"]
    assert "graph_edges" in calls[0]["prompt"]


@pytest.mark.parametrize(
    "payload, expected_status_reason",
    [
        ({"decision": "clarification_needed"}, "clarification_needed"),
        ({"decision": "reject"}, "rejected"),
        ({"decision": "candidate", "candidate": {"kind": "semantic_fact", "confidence": 0.9}}, "clarification_needed"),
    ],
    ids=["clarification_needed", "rejected", "candidate_without_summary"],
)
def test_live_model_without_candidate_fails_lifecycle_seed_without_fallback(
    payload: dict,
    expected_status_reason: str,
) -> None:
    def fake_load_auth(backend, auth_path):
        return {"path": auth_path}

    def fake_call_json(model_backend, model_auth, prompt, model, base_url, timeout):
        return payload

    adapter = TypedCardsMemoryEvalAdapter(
        extractor_mode="live_model",
        load_auth=fake_load_auth,
        call_json=fake_call_json,
    )
    adapter.reset({"fixture_id": "fx_live_rejected", "evaluation_time": "2026-05-21T00:00:00Z"})

    ingest = adapter.ingest([_experience()])[0]
    seed = adapter.mutate(
        [
            {
                "op_id": "seed_rejected",
                "mutation_type": "seed_eval",
                "target_experience_id": "ex_public",
            }
        ]
    )[0]

    assert ingest["status"] == "success"
    assert ingest["status_reason"] == expected_status_reason
    assert ingest["proposal_ids"] == []
    assert seed["status"] == "failed"
    assert seed["status_reason"] == "proposal_not_found"
    assert adapter.core.candidates == {}
    assert adapter.core.memory_cards == {}
    assert not [event for event in adapter.core.memory_audit_log if event.operation == "propose"]


def test_plain_ingest_is_proposal_only_until_public_lifecycle_seed() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    receipt = adapter.ingest([_experience()])[0]

    assert receipt["status"] == "success"
    assert receipt["status_reason"] == "proposed"
    assert receipt["card_ids"] == []
    assert [event.operation for event in adapter.core.memory_audit_log] == [
        "capture_provenance",
        "extract_candidate",
        "propose",
    ]
    assert not [card for card in adapter.core.memory_cards.values() if card.approval_state == "committed"]

    result = adapter.retrieve(
        {
            "request_id": "rq_test",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "Which tea does Mira prefer for breaks?", "intent": "preference_lookup"},
            "k": 1,
            "filters": {"allowed_states": ["active"], "valid_at": "2026-03-01T12:00:00Z"},
            "budget": {"max_evidence_items": 1},
        }
    )
    assert result["ranked_evidence"] == []
    assert result["abstained"] is True


def test_lifecycle_seed_eval_round_trips_current_support_from_typed_provenance() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience()])
    seed = adapter.mutate(
        [
            {
                "op_id": "seed_public",
                "lifecycle_type": "seed_eval",
                "target_experience_id": "ex_public",
                "effective_time": "2026-05-21T00:00:00Z",
                "reason": "phase c public setup",
            }
        ]
    )[0]

    assert seed["status"] == "success"
    assert seed["lifecycle_type"] == "seed_eval"
    assert seed["card_ids"]
    assert [event.operation for event in adapter.core.memory_audit_log][-1] == "seed_eval"
    committed = adapter.core.memory_cards[seed["card_ids"][0]]
    assert {"Mira", "green", "tea", "planning", "breaks"}.issubset(set(committed.retrieval_terms))

    result = adapter.retrieve(
        {
            "request_id": "rq_test",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "Which tea does Mira prefer for breaks?", "intent": "preference_lookup"},
            "k": 1,
            "filters": {"allowed_states": ["active"], "valid_at": "2026-03-01T12:00:00Z"},
            "budget": {"max_evidence_items": 1},
        }
    )

    ranked = result["ranked_evidence"][0]
    assert ranked["support_experience_ids"] == ["ex_public"]
    assert ranked["source_experience_ids"] == ["ex_public"]
    assert ranked["provenance_refs"] == ranked["metadata"]["provenance_refs_by_role"]["current_support"]
    assert {"Mira", "green", "tea", "planning", "breaks"}.issubset(set(ranked["metadata"]["retrieval_terms"]))
    assert ranked["scope_id"] == "tenant_a/user_a"


def test_adapter_retrieve_accepts_graph_on_query_controls() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_graph_on", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest(
        [
            _experience("ex_seed", text="Apollo anchor belongs to the seed memory."),
            _experience("ex_related", text="Graph-only related regression coverage lives in typed adapter tests."),
        ]
    )
    seed = adapter.mutate([{"op_id": "seed_graph", "lifecycle_type": "seed_eval", "target_experience_id": "ex_seed"}])[0]
    related = adapter.mutate([{"op_id": "seed_related", "lifecycle_type": "seed_eval", "target_experience_id": "ex_related"}])[0]
    scope = adapter._scope_from_public("tenant_a/user_a")
    created = "2026-05-21T00:00:00Z"
    seed_node = GraphNode.build(
        node_type="file",
        scope=scope,
        canonical_ref="file:mew:main:src/mew/memory_typed_card_core.py",
        display_name="memory_typed_card_core.py",
        created_at=created,
        updated_at=created,
    )
    related_node = GraphNode.build(
        node_type="test",
        scope=scope,
        canonical_ref="test:mew:tests/test_memory_eval_typed_cards_adapter.py",
        display_name="test_memory_eval_typed_cards_adapter.py",
        created_at=created,
        updated_at=created,
    )
    adapter.core.add_graph_node(seed_node)
    adapter.core.add_graph_node(related_node)
    seed_card = adapter.core.memory_cards[seed["card_ids"][0]]
    related_card = adapter.core.memory_cards[related["card_ids"][0]]
    adapter.core.memory_cards[seed_card.card_id] = replace(seed_card, graph_refs=GraphRefs(node_ids=(seed_node.node_id,)))
    adapter.core.memory_cards[related_card.card_id] = replace(related_card, graph_refs=GraphRefs(node_ids=(related_node.node_id,)))
    edge = GraphEdge.build(
        from_node_id=seed_node.node_id,
        from_node_type="file",
        to_node_id=related_node.node_id,
        to_node_type="test",
        edge_type="related",
        scope=scope,
        evidence_links=(EvidenceLink(ref_id=seed_card.evidence_links[0].ref_id, role="current_support"),),
        created_at=created,
        updated_at=created,
    )
    adapter.core.add_graph_edge(edge)

    direct = adapter.retrieve(
        {
            "request_id": "rq_direct",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "Apollo anchor"},
            "k": 5,
            "budget": {"max_evidence_items": 5},
        }
    )
    graph_on = adapter.retrieve(
        {
            "request_id": "rq_graph",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "Apollo anchor"},
            "k": 5,
            "filters": {"expand_graph": True, "graph_max_items": 4},
            "budget": {"max_evidence_items": 5},
        }
    )

    assert [item["support_experience_ids"] for item in direct["ranked_evidence"]] == [["ex_seed"]]
    support_ids = [item["support_experience_ids"][0] for item in graph_on["ranked_evidence"]]
    assert "ex_seed" in support_ids
    assert "ex_related" in support_ids
    assert graph_on["usage"]["counts"]["index_mode"] == "graph_index"
    assert graph_on["usage"]["counts"]["graph_nodes_expanded"] == 2
    assert graph_on["usage"]["counts"]["graph_edges_expanded"] == 1
    assert graph_on["derived_graph_index_verification"]["ok"] is True
    assert graph_on["derived_graph_index_verification"]["issue_count"] == 0
    assert graph_on["derived_graph_index_verification"]["snapshot_hash"]


def test_seed_graph_mutation_is_explicit_fixture_setup_for_recall_only() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_seed_graph", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest(
        [
            _experience("ex_seed", text="Rigel anchor belongs to the seed memory."),
            _experience("ex_related", text="Seeded graph setup can connect this related memory."),
        ]
    )
    adapter.mutate([{"op_id": "seed_graph_a", "lifecycle_type": "seed_eval", "target_experience_id": "ex_seed"}])
    adapter.mutate([{"op_id": "seed_graph_b", "lifecycle_type": "seed_eval", "target_experience_id": "ex_related"}])

    graph_receipt = adapter.mutate(
        [
            {
                "op_id": "graph_setup",
                "mutation_type": "seed_graph",
                "graph": {
                    "links": [
                        {
                            "from_experience_id": "ex_seed",
                            "to_experience_id": "ex_related",
                            "from_node": {
                                "node_type": "file",
                                "canonical_ref": "file:mew:main:src/mew/memory_typed_card_core.py",
                            },
                            "to_node": {
                                "node_type": "test",
                                "canonical_ref": "test:mew:tests/test_memory_eval_typed_cards_adapter.py",
                            },
                            "edge_type": "related",
                        }
                    ]
                },
            }
        ]
    )[0]
    graph_on = adapter.retrieve(
        {
            "request_id": "rq_seed_graph",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "Rigel anchor"},
            "k": 5,
            "filters": {"expand_graph": True, "graph_max_items": 4},
            "budget": {"max_evidence_items": 5},
        }
    )

    assert graph_receipt["status"] == "success"
    assert graph_receipt["graph_nodes_created"] == 2
    assert graph_receipt["graph_edges_created"] == 1
    assert graph_on["usage"]["counts"]["index_mode"] == "graph_index"
    assert [item["support_experience_ids"][0] for item in graph_on["ranked_evidence"]] == ["ex_seed", "ex_related"]


def test_deterministic_replay_retrieval_terms_skip_speaker_roles_and_overlong_tokens() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_replay_terms", "evaluation_time": "2026-05-21T00:00:00Z"})
    long_url = "https://example.test/" + ("x" * 110)
    adapter.ingest(
        [
            _experience(
                "ex_replay_terms",
                text=f"User: Mira stores launch notes near {long_url}",
            )
        ]
    )
    seed = adapter.mutate(
        [
            {
                "op_id": "seed_replay_terms",
                "lifecycle_type": "seed_eval",
                "target_experience_id": "ex_replay_terms",
            }
        ]
    )[0]

    assert seed["status"] == "success"
    committed = adapter.core.memory_cards[seed["card_ids"][0]]
    assert "User" not in committed.retrieval_terms
    assert "Mira" in committed.retrieval_terms
    assert "launch" in committed.retrieval_terms
    assert all(len(term) <= 96 for term in committed.retrieval_terms)
    assert all("x" * 40 not in term for term in committed.retrieval_terms)
    assert all("https" not in term.casefold() for term in committed.retrieval_terms)
    assert all("example" not in term.casefold() for term in committed.retrieval_terms)
    assert all("test/" not in term.casefold() for term in committed.retrieval_terms)


def test_deterministic_replay_synthesizes_short_transcript_summary() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_replay_short_transcript"})
    receipt = adapter.ingest(
        [
            _experience(
                "ex_short_transcript",
                text=(
                    "Data time: 09:05 AM\n\n"
                    "User: My boss runs a company called Golden State Freight Lines.; "
                    "Assistant: Noted."
                ),
            )
        ]
    )[0]

    assert receipt["status"] == "success"
    assert receipt["proposal_ids"]
    assert receipt["dropped"] == []
    proposal = adapter.core.memory_cards[receipt["proposal_ids"][0]]
    assert proposal.summary == (
        "Memory: My boss runs a company called Golden State Freight Lines."
    )
    assert "User:" not in proposal.summary
    assert "Assistant:" not in proposal.summary


def test_deterministic_replay_preserves_semantic_retrieval_hints_before_raw_tokens() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_replay_semantic_hints"})
    metadata_words = " ".join(f"metadata{i}" for i in range(40))
    receipt = adapter.ingest(
        [
            _experience(
                "ex_hobby_hint",
                text=(
                    f"Data time: {metadata_words}\n\n"
                    "User: My niece loves cooking and makes pasta every weekend.; "
                    "Assistant: That sounds creative."
                ),
            )
        ]
    )[0]

    assert receipt["status"] == "success"
    proposal = adapter.core.memory_cards[receipt["proposal_ids"][0]]
    assert {"hobby", "enjoy", "niece", "cooking"}.issubset(
        set(proposal.retrieval_terms)
    )
    assert len(proposal.retrieval_terms) <= 32


def test_deterministic_replay_ranks_hobby_relation_over_auxiliary_have_matches() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_replay_hobby_relation"})
    adapter.ingest(
        [
            _experience(
                "ex_boss_hobby",
                text="User: My boss is really into sports; it's a big part of their life.",
            ),
            _experience(
                "ex_boss_context",
                text="User: Working with Maya is inspiring; it is nice to have a boss.",
            ),
            _experience(
                "ex_hobby_context",
                text="User: Clara would love to have me join her pottery hobby.",
            ),
        ]
    )
    adapter.mutate(
        [
            {
                "op_id": f"seed_{experience_id}",
                "lifecycle_type": "seed_eval",
                "target_experience_id": experience_id,
            }
            for experience_id in (
                "ex_boss_hobby",
                "ex_boss_context",
                "ex_hobby_context",
            )
        ]
    )

    result = adapter.retrieve(
        {
            "request_id": "rq_boss_hobby",
            "scope_id": "tenant_a/user_a",
            "query": {"text": "What hobby does the boss have?"},
            "k": 3,
            "budget": {"max_evidence_items": 3},
        }
    )

    assert result["ranked_evidence"][0]["support_experience_ids"] == [
        "ex_boss_hobby"
    ]


def test_update_forget_fixture_uses_current_support_and_does_not_leak_forgotten_ids() -> None:
    artifact = run_fixture(
        _fixture_with_seed_lifecycle(P1_FIXTURES / "update_forget_basic.json"),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    returned = request["retrieval"]["returned_evidence_order"]
    assert returned[0]["support_experience_ids"] == ["exp_active_folder"]
    assert {"Mira", "travel", "notes", "Orion"}.issubset(
        set(returned[0]["debug_metadata"]["retrieval_terms"])
    )
    assert "exp_removed_folder" not in str(request["retrieval"])
    assert returned[0]["source_mutation_ids"] == ["mut_update_folder"]


def test_relation_sensitive_niece_company_fixture_asserts_top1_scope_and_support() -> None:
    artifact = run_fixture(
        _fixture_with_seed_lifecycle(RELATION_NIECE_COMPANY_FIXTURE),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["metrics"]["recall_at_k"] == 1.0
    assert request["metrics"]["mrr_at_k"] == 1.0
    assert request["metrics"]["precision_at_k"] == 1.0
    assert request["metrics"]["cross_scope_leak_rate"] == 0
    assert request["metrics"]["cross_scope_exposure_rate"] == 0
    assert request["metrics"]["stale_as_fresh"] == 0

    returned = request["retrieval"]["returned_evidence_order"]
    assert len(returned) == 1
    assert returned[0]["support_experience_ids"] == ["exp_niece_current_company"]
    assert returned[0]["source_experience_ids"] == ["exp_niece_current_company"]
    assert returned[0]["source_mutation_ids"] == ["mut_niece_company_current"]
    assert {"niece", "Elena", "Northstar", "Robotics"}.issubset(
        set(returned[0]["debug_metadata"]["retrieval_terms"])
    )
    assert "exp_niece_old_company" not in str(request["retrieval"])
    assert "exp_other_scope_same_company" not in str(request["retrieval"])
    assert "exp_raw_match_removed" not in str(request["retrieval"])
    assert request["retrieval"]["dropped_count_by_reason"]["superseded"] >= 1
    assert request["retrieval"]["dropped_count_by_reason"]["forgotten"] >= 1
    assert request["retrieval"]["dropped_count_by_reason"]["privacy_block"] >= 1


def test_scope_isolation_fixture_passes_without_cross_scope_support() -> None:
    artifact = run_fixture(
        _fixture_with_seed_lifecycle(P1_FIXTURES / "scope_isolation_basic.json"),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["metrics"]["cross_scope_leak_rate"] == 0
    assert request["metrics"]["cross_scope_exposure_rate"] == 0


def test_graph_expansion_fixture_passes_with_graph_usage_counts() -> None:
    artifact = run_fixture(
        json.loads(GRAPH_FIXTURE.read_text(encoding="utf-8")),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_graph",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    returned = request["retrieval"]["returned_evidence_order"]
    support_ids = [support_id for item in returned for support_id in item["support_experience_ids"]]
    assert "exp_related_note" in support_ids
    assert request["usage"]["counts"]["index_mode"] == "graph_index"
    assert request["usage"]["counts"]["graph_nodes_expanded"] == 1
    assert request["usage"]["counts"]["graph_edges_expanded"] == 0
    assert request["metrics"]["expected_usage_satisfied"] == 1.0
    assert "expected_usage_satisfied" in {
        gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is True
    }


def test_graph_edge_expansion_fixture_passes_with_graph_usage_counts() -> None:
    artifact = run_fixture(
        json.loads(GRAPH_EDGE_FIXTURE.read_text(encoding="utf-8")),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_graph_edge",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    returned = request["retrieval"]["returned_evidence_order"]
    support_ids = [support_id for item in returned for support_id in item["support_experience_ids"]]
    assert "exp_edge_related_note" in support_ids
    assert request["usage"]["counts"]["index_mode"] == "graph_index"
    assert request["usage"]["counts"]["graph_nodes_expanded"] == 2
    assert request["usage"]["counts"]["graph_edges_expanded"] == 1
    assert request["metrics"]["expected_usage_satisfied"] == 1.0
    assert request["retrieval"]["derived_graph_index_verification"]["ok"] is True
    assert request["retrieval"]["derived_graph_index_verification"]["issue_count"] == 0


@pytest.mark.parametrize(
    "fixture_path, forbidden_id, dropped_reason",
    [
        (GRAPH_CROSS_SCOPE_FIXTURE, "exp_graph_scope_foreign", "privacy_block"),
        (GRAPH_FORGET_FIXTURE, "exp_graph_forget_related", "forgotten"),
        (GRAPH_STALE_ENDPOINT_FIXTURE, "exp_graph_stale_related", "stale_graph_node"),
        (GRAPH_UNCANONICALIZED_ENDPOINT_FIXTURE, "exp_graph_missing_related", "uncanonicalized_graph_endpoint"),
    ],
    ids=["cross_scope", "forgotten", "stale_endpoint", "uncanonicalized_endpoint"],
)
def test_graph_negative_fixtures_do_not_leak_blocked_support(
    fixture_path: Path,
    forbidden_id: str,
    dropped_reason: str,
) -> None:
    artifact = run_fixture(
        json.loads(fixture_path.read_text(encoding="utf-8")),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_graph_negative",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    returned = request["retrieval"]["returned_evidence_order"]
    support_ids = [support_id for item in returned for support_id in item["support_experience_ids"]]

    assert request["result_status"] == "passed"
    assert forbidden_id not in support_ids
    assert forbidden_id not in str(request["retrieval"]["visible_dropped"])
    assert request["usage"]["counts"]["index_mode"] == "graph_index"
    assert request["metrics"]["expected_usage_satisfied"] == 1.0
    assert request["metrics"]["expected_dropped_counts_satisfied"] == 1.0
    assert request["retrieval"]["dropped_count_by_reason"][dropped_reason] == 1
    if dropped_reason == "uncanonicalized_graph_endpoint":
        verification = request["retrieval"]["derived_graph_index_verification"]
        assert request["metrics"]["expected_derived_graph_index_verification_satisfied"] == 1.0
        assert verification["ok"] is False
        assert verification["issue_count_by_type"]["graph_edge_to_node_missing"] >= 1


def test_harness_scope_strings_map_to_non_user_typed_scope_for_semantic_facts() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience()])
    adapter.mutate([{"op_id": "seed_public", "mutation_type": "seed_eval", "target_experience_id": "ex_public"}])

    committed = next(card for card in adapter.core.memory_cards.values() if card.approval_state == "committed")
    assert committed.kind == "semantic_fact"
    assert committed.scope.level == "shared"
    assert committed.scope.user_id is None


def test_reset_does_not_seed_memory_and_missing_lifecycle_seed_fails_without_side_effects() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    receipt = adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})

    assert receipt["seeded_during_reset"] is False
    assert adapter.core.memory_cards == {}
    assert adapter.core.memory_audit_log == []

    lifecycle_receipt = adapter.mutate(
        [
            {
                "op_id": "setup_seed",
                "lifecycle_type": "seed_eval",
                "target_experience_id": "missing",
            }
        ]
    )[0]
    assert lifecycle_receipt["status"] == "failed"
    assert lifecycle_receipt["status_reason"] == "proposal_not_found"
    assert adapter.core.memory_cards == {}


@pytest.mark.parametrize("lifecycle_type", ["seed_eval", "approve", "commit"])
def test_lifecycle_empty_target_list_fails_closed(lifecycle_type: str) -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})

    receipt = adapter.mutate([{"op_id": f"{lifecycle_type}_empty", "lifecycle_type": lifecycle_type}])[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "missing_lifecycle_experience_id"
    assert adapter.core.memory_cards == {}
    assert adapter.core.memory_audit_log == []


def test_lifecycle_seed_eval_mixed_targets_is_transactional() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_a", text="Mira keeps meeting notes in folder Fern.")])

    receipt = adapter.mutate(
        [
            {
                "op_id": "seed_mixed",
                "lifecycle_type": "seed_eval",
                "payload": {"experience_ids": ["ex_a", "missing"]},
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "proposal_not_found"
    assert not [card for card in adapter.core.memory_cards.values() if card.approval_state == "committed"]
    assert not [event for event in adapter.core.memory_audit_log if event.operation == "seed_eval"]


def test_lifecycle_approve_mixed_targets_is_transactional() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_a", text="Mira keeps meeting notes in folder Fern.")])

    receipt = adapter.mutate(
        [
            {
                "op_id": "approve_mixed",
                "lifecycle_type": "approve",
                "payload": {"experience_ids": ["ex_a", "missing"]},
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "proposal_not_found"
    assert [card.approval_state for card in adapter.core.memory_cards.values()] == ["proposal"]
    assert not [event for event in adapter.core.memory_audit_log if event.operation == "approve"]


def test_lifecycle_commit_mixed_targets_is_transactional() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_a", text="Mira keeps meeting notes in folder Fern.")])
    approve = adapter.mutate(
        [{"op_id": "approve_ex_a", "lifecycle_type": "approve", "target_experience_id": "ex_a"}]
    )[0]
    assert approve["status"] == "success"

    receipt = adapter.mutate(
        [
            {
                "op_id": "commit_mixed",
                "lifecycle_type": "commit",
                "payload": {"experience_ids": ["ex_a", "missing"]},
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "approved_not_found"
    assert [card.approval_state for card in adapter.core.memory_cards.values()] == ["approved"]
    assert not [event for event in adapter.core.memory_audit_log if event.operation == "commit"]


def test_malformed_lifecycle_effective_time_returns_failed_receipt_without_state_change() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_public")])
    before_audits = list(adapter.core.memory_audit_log)
    before_cards = dict(adapter.core.memory_cards)

    receipt = adapter.mutate(
        [
            {
                "op_id": "seed_bad_time",
                "lifecycle_type": "seed_eval",
                "target_experience_id": "ex_public",
                "effective_time": "not-a-date",
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "invalid_effective_time"
    assert adapter.core.memory_audit_log == before_audits
    assert adapter.core.memory_cards == before_cards


def test_malformed_runtime_effective_time_returns_failed_receipt_without_state_change() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_delete")])
    adapter.mutate([{"op_id": "seed_delete", "mutation_type": "seed_eval", "target_experience_id": "ex_delete"}])
    before_audits = list(adapter.core.memory_audit_log)
    before_cards = dict(adapter.core.memory_cards)

    receipt = adapter.mutate(
        [
            {
                "op_id": "delete_bad_time",
                "mutation_type": "delete",
                "target_experience_id": "ex_delete",
                "effective_time": "not-a-date",
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "invalid_effective_time"
    assert adapter.core.memory_audit_log == before_audits
    assert adapter.core.memory_cards == before_cards


def test_terminal_mutations_reject_replacement_content() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_delete")])
    adapter.mutate([{"op_id": "seed_delete", "mutation_type": "seed_eval", "target_experience_id": "ex_delete"}])

    for op in (
        {
            "op_id": "delete_bad_replacement_id",
            "mutation_type": "delete",
            "target_experience_id": "ex_delete",
            "replacement_experience_id": "ex_other",
        },
        {
            "op_id": "forget_bad_replacement_content",
            "mutation_type": "forget",
            "target_experience_id": "ex_delete",
            "replacement": {"content": {"summary": "not allowed"}},
        },
        {
            "op_id": "delete_bad_scalar_replacement",
            "mutation_type": "delete",
            "target_experience_id": "ex_delete",
            "replacement": "not allowed",
        },
        {
            "op_id": "tombstone_bad_scalar_replacement_content",
            "mutation_type": "tombstone",
            "target_experience_id": "ex_delete",
            "replacement": {"content": "not allowed"},
        },
    ):
        receipt = adapter.mutate([op])[0]
        assert receipt["status"] == "failed"
        assert receipt["status_reason"] == "terminal_mutation_replacement_not_allowed"


def test_replacement_content_preserves_clear_fields_and_nested_nulls() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest(
        [
            _experience("ex_old", text="Mira keeps typed-card notes in folder Cedar."),
            _experience("ex_set", text="Mira sets lifecycle and privacy metadata for typed-card notes."),
            _experience("ex_clear", text="Mira clears lifecycle and privacy metadata for typed-card notes."),
        ]
    )
    adapter.mutate([{"op_id": "seed_old", "mutation_type": "seed_eval", "target_experience_id": "ex_old"}])

    set_receipt = adapter.mutate(
        [
            {
                "op_id": "mu_set_nested",
                "mutation_type": "update",
                "target_experience_id": "ex_old",
                "replacement_experience_id": "ex_set",
                "replacement": {
                    "content": {
                        "details": "Temporary details.",
                        "lifecycle": {"expires_at": "2026-12-31T00:00:00Z"},
                        "privacy": {"redaction_policy": "refs_only"},
                    }
                },
            }
        ]
    )[0]
    assert set_receipt["status"] == "success"
    card = adapter.core.memory_cards[set_receipt["card_ids"][0]]
    assert card.details == "Temporary details."
    assert card.lifecycle.expires_at == "2026-12-31T00:00:00Z"
    assert card.privacy.redaction_policy == "refs_only"

    clear_receipt = adapter.mutate(
        [
            {
                "op_id": "mu_clear_nested",
                "mutation_type": "update",
                "target_experience_id": "ex_set",
                "replacement_experience_id": "ex_clear",
                "replacement": {
                    "content": {
                        "details": None,
                        "lifecycle": {"expires_at": None},
                        "privacy": {"redaction_policy": None},
                        "clear_fields": ["details", "lifecycle.expires_at", "privacy.redaction_policy"],
                    }
                },
            }
        ]
    )[0]
    assert clear_receipt["status"] == "success"
    cleared = adapter.core.memory_cards[clear_receipt["card_ids"][0]]
    assert cleared.details is None
    assert cleared.lifecycle.expires_at is None
    assert cleared.privacy.redaction_policy == "none"


def test_effective_time_is_preserved_in_runtime_receipt_and_audit_metadata() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest(
        [
            _experience("ex_old", text="Mira first kept travel notes in folder Cedar."),
            _experience("ex_new", text="Mira updates the travel notes home to folder Orion."),
        ]
    )
    adapter.mutate([{"op_id": "seed_old", "mutation_type": "seed_eval", "target_experience_id": "ex_old"}])
    adapter.mutate([{"op_id": "seed_new", "mutation_type": "seed_eval", "target_experience_id": "ex_new"}])

    receipt = adapter.mutate(
        [
            {
                "op_id": "mu_update",
                "mutation_type": "update",
                "target_experience_id": "ex_old",
                "replacement_experience_id": "ex_new",
                "effective_time": "2026-01-16T09:06:00Z",
                "reason": "newer travel home",
            }
        ]
    )[0]

    assert receipt["status"] == "success"
    assert receipt["effective_time"] == "2026-01-16T09:06:00Z"
    audit = next(event for event in adapter.core.memory_audit_log if "mu_update" in event.mutation_ids)
    assert audit.metadata["public_effective_time"] == "2026-01-16T09:06:00Z"


def test_forget_uses_explicit_authority_provenance_not_target_support() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience("ex_forget", text="Mira used folder Birch for temporary travel notes staging.")])
    adapter.mutate([{"op_id": "seed_forget", "mutation_type": "seed_eval", "target_experience_id": "ex_forget"}])
    target = next(card for card in adapter.core.memory_cards.values() if card.approval_state == "committed")
    target_support_refs = {
        link.ref_id for link in target.evidence_links if link.active and link.role == "current_support"
    }

    receipt = adapter.mutate(
        [
            {
                "op_id": "mu_forget",
                "mutation_type": "forget",
                "target_experience_id": "ex_forget",
                "effective_time": "2026-01-16T09:11:00Z",
                "reason": "remove temporary folder note",
            }
        ]
    )[0]

    assert receipt["status"] == "success"
    authority_refs = set(receipt["provenance_event_ids"])
    assert authority_refs
    assert authority_refs.isdisjoint(target_support_refs)
    authority_event = adapter.core.provenance_events[next(iter(authority_refs))]
    assert authority_event.actor == "user"
    assert authority_event.source_mutation_id == "mu_forget"
    audit = next(event for event in adapter.core.memory_audit_log if "mu_forget" in event.mutation_ids)
    assert set(audit.provenance_event_ids) == authority_refs


def test_mutation_target_ambiguity_fails_closed() -> None:
    adapter = TypedCardsMemoryEvalAdapter()
    adapter.reset({"fixture_id": "fx_test", "evaluation_time": "2026-05-21T00:00:00Z"})
    adapter.ingest([_experience()])
    adapter.mutate([{"op_id": "seed_public", "mutation_type": "seed_eval", "target_experience_id": "ex_public"}])
    committed = next(card for card in adapter.core.memory_cards.values() if card.approval_state == "committed")
    duplicate = replace(committed, card_id=f"{committed.card_id}_duplicate")
    adapter.core.seed_committed_card_for_eval(
        duplicate,
        actor="adapter",
        public_operation_id="test_duplicate",
        source_experience_id="ex_public",
    )

    receipt = adapter.mutate(
        [
            {
                "op_id": "mu_ambiguous",
                "mutation_type": "delete",
                "target_experience_id": "ex_public",
                "reason": "test ambiguous target",
            }
        ]
    )[0]

    assert receipt["status"] == "failed"
    assert receipt["status_reason"] == "ambiguous_target"


@pytest.mark.parametrize(
    "fixture_path",
    [
        P1_FIXTURES / "stale_conflict_supersede_basic.json",
        P1_FIXTURES / "update_forget_basic.json",
    ],
    ids=lambda path: path.name,
)
def test_synthetic_retire_mutation_ids_do_not_leak_to_retrieval_or_usage(fixture_path: Path) -> None:
    artifact = run_fixture(
        _fixture_with_seed_lifecycle(fixture_path),
        TypedCardsMemoryEvalAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert ":retire_seed:" not in json.dumps(request["retrieval"], sort_keys=True)
    assert ":retire_seed:" not in json.dumps(request["usage"], sort_keys=True)


def test_typed_memory_core_files_do_not_import_memory_eval() -> None:
    offenders = []
    for relative in ("src/mew/memory_typed_card_core.py", "src/mew/memory_typed_cards.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if "memory_eval" in text:
            offenders.append(relative)

    assert offenders == []
