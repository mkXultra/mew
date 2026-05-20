import json
from contextlib import redirect_stdout
from io import StringIO

from mew.cli import main
from mew.memory_core import Contradiction, GraphEdge, MemoryEntry, ProvenanceRef, Staleness
from mew.memory_debug import (
    chain_artifact,
    inspect_artifact,
    recall_artifact,
    score_fixture_artifact,
)
from mew.memory_arena import score_memory_arena_artifact, score_memory_arena_tool_artifact


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
        "entry_id": "golden-rule",
        "memory_kind": "project_convention",
        "scope": "repo:mew",
        "title": "Golden convention",
        "summary": "Use the golden convention when calculating delivery estimates.",
        "applicability": "Harbor resident-memory local fixture",
        "source_refs": (_ref("source-1"),),
        "proof_refs": (_ref("proof-1", "reviewer_approval"),),
        "created_at": "2026-05-20T00:00:00Z",
        "last_verified_at": "2026-05-20T01:00:00Z",
        "validity": "valid",
        "confidence": 0.9,
    }
    values.update(overrides)
    return MemoryEntry(**values)


def _write_store(path, entries):
    path.write_text(json.dumps({"entries": [entry.to_dict() for entry in entries]}), encoding="utf-8")


def _assert_no_forbidden_fields(value):
    if isinstance(value, dict):
        assert FORBIDDEN_RECALL_FIELDS.isdisjoint(value.keys())
        for child in value.values():
            _assert_no_forbidden_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_fields(child)


def test_recall_artifact_contains_trace_metrics_stale_and_contradiction_metadata(tmp_path):
    store = tmp_path / "memory.json"
    stale = _entry(
        entry_id="stale-rule",
        staleness=Staleness(state="stale", reasons=("fixture stale mode",)),
        contradiction=Contradiction(state="possible", contradicting_entry_ids=("golden-rule",)),
    )
    _write_store(store, [_entry(), stale])

    artifact = recall_artifact(
        store_path=str(store),
        query="golden convention delivery",
        include_stale=True,
    )
    result = artifact["result"]
    trace = result["trace"]

    assert artifact["operation"] == "recall"
    assert set(artifact["metrics"]["returned_entry_ids"]) == {"golden-rule", "stale-rule"}
    assert artifact["metrics"]["evidence_hits"] == []
    assert artifact["metrics"]["evidence_hit_count"] == 0
    assert artifact["metrics"]["stale_recall_count"] == 1
    assert artifact["metrics"]["contradiction_count"] == 1
    assert trace["request_hash"]
    assert trace["result_hash"]
    assert trace["store_id"].startswith("memory:json:")
    assert trace["index_id"].startswith("memory:index:json:")
    assert trace["timing_ms"] >= 0
    assert trace["budget_used"]["returned_chars"] > 0
    assert artifact["debug_trace"]["evidence_hits"] == artifact["metrics"]["evidence_hits"]
    assert artifact["debug_trace"]["stale_recall_count"] == 1
    assert artifact["debug_trace"]["contradiction_count"] == 1
    assert artifact["debug_trace"]["returned_chars"] > 0
    assert any(item["staleness"]["state"] == "stale" for item in result["candidates"])
    assert "memory recall:" in artifact["summary"]
    _assert_no_forbidden_fields(artifact)


def test_score_fixture_modes_are_explicit_and_artifact_visible(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "task_family": "harbor_resident_memory_local",
                "task_id": "golden-convention",
                "phase_or_session": "phase-b-recall",
                "query": "golden convention delivery",
                "expected_entry_ids": ["golden-rule"],
                "entries": [_entry().to_dict()],
                "stale_entries": [
                    _entry(
                        entry_id="stale-rule",
                        staleness=Staleness(state="stale", reasons=("layout changed",)),
                    ).to_dict()
                ],
            }
        ),
        encoding="utf-8",
    )

    off = score_fixture_artifact(fixture_path=str(fixture), mode="memory_off")
    on = score_fixture_artifact(fixture_path=str(fixture), mode="memory_on")
    stale = score_fixture_artifact(fixture_path=str(fixture), mode="stale")

    assert off["memory_mode"] == "memory_off"
    assert off["metrics"]["expected_hit_count"] == 0
    assert off["metrics"]["recall_at_k"] is False
    assert on["memory_mode"] == "memory_on"
    assert on["metrics"]["expected_hit_count"] == 1
    assert on["metrics"]["recall_at_k"] is True
    assert stale["memory_mode"] == "stale"
    assert stale["metrics"]["expected_hit_count"] == 0
    assert stale["metrics"]["dropped_reasons"]["stale_excluded"] == 1
    for artifact in (off, on, stale):
        assert artifact["memory_snapshot_hash"]
        assert artifact["recall_config_hash"]
        assert artifact["model_or_runner_config_hash"] == "direct-memory-core-no-model"
        assert artifact["store_id"].startswith("memory:fixture:")
        assert artifact["fixture_boundary"]["direct_memory_system"] is True
        assert artifact["fixture_boundary"]["model_used"] is False
        assert artifact["debug_trace"]["dropped_reasons"] == artifact["metrics"]["dropped_reasons"]


def test_stale_score_requires_explicit_stale_entries(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "query": "golden convention delivery",
                "expected_entry_ids": ["golden-rule"],
                "entries": [_entry().to_dict()],
            }
        ),
        encoding="utf-8",
    )

    try:
        score_fixture_artifact(fixture_path=str(fixture), mode="stale")
    except ValueError as exc:
        assert "stale_entries" in str(exc)
    else:
        raise AssertionError("stale mode without stale_entries must fail fast")


def test_score_without_expected_entries_separates_returned_entries_from_hits(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "query": "golden convention delivery",
                "entries": [_entry().to_dict()],
            }
        ),
        encoding="utf-8",
    )

    artifact = score_fixture_artifact(fixture_path=str(fixture), mode="memory_on")

    assert artifact["metrics"]["returned_entry_ids"] == ["golden-rule"]
    assert artifact["metrics"]["candidate_entry_ids"] == ["golden-rule"]
    assert artifact["metrics"]["expected_entry_ids"] == []
    assert artifact["metrics"]["evidence_hits"] == []
    assert artifact["metrics"]["evidence_hit_count"] == 0
    assert artifact["metrics"]["expected_hit_count"] == 0
    assert artifact["metrics"]["recall_at_k"] is False
    assert artifact["debug_trace"]["evidence_hits"] == []


def test_chain_and_inspect_artifacts_use_direct_memory_system(tmp_path):
    store = tmp_path / "memory.json"
    edge = GraphEdge(
        edge_id="edge-1",
        source_entry_id="root",
        target_entry_id="child",
        edge_kind="supports",
        evidence_refs=(_ref("edge-proof"),),
    )
    _write_store(
        store,
        [
            _entry(entry_id="root", graph_edges=(edge,)),
            _entry(entry_id="child", memory_kind="procedural_repair", summary="Child chain evidence."),
        ],
    )

    chain = chain_artifact(store_path=str(store), entry_ids=("root",), max_depth=1)
    inspected = inspect_artifact(store_path=str(store), entry_id="child")

    assert chain["operation"] == "chain"
    assert chain["metrics"]["node_entry_ids"] == ["root", "child"]
    assert chain["metrics"]["edge_ids"] == ["edge-1"]
    assert "memory chain:" in chain["summary"]
    assert inspected["operation"] == "inspect"
    assert inspected["result"]["entry"]["entry_id"] == "child"
    assert "memory inspect:" in inspected["summary"]


def test_memory_core_cli_recall_prints_json_and_writes_artifact(tmp_path):
    store = tmp_path / "memory.json"
    artifact_path = tmp_path / "recall-artifact.json"
    _write_store(store, [_entry()])

    with redirect_stdout(StringIO()) as stdout:
        code = main(
            [
                "memory-core",
                "recall",
                "--store",
                str(store),
                "--query",
                "golden convention",
                "--json",
                "--artifact",
                str(artifact_path),
            ]
        )

    printed = json.loads(stdout.getvalue())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert code == 0
    assert printed["operation"] == "recall"
    assert printed["metrics"]["returned_entry_ids"] == ["golden-rule"]
    assert printed["metrics"]["evidence_hits"] == []
    assert printed["metrics"]["evidence_hit_count"] == 0
    assert artifact["result"]["trace"]["request_hash"] == printed["result"]["trace"]["request_hash"]


def test_memory_arena_score_compares_memory_modes_on_local_export(tmp_path):
    export = tmp_path / "memoryarena.jsonl"
    export.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "shopping-1",
                        "category": "bundled_shopping",
                        "background": "The user is planning a gluten free cake order.",
                        "questions": [
                            "Choose a cake mix.",
                            "Which cake mix should be used with the frosting bundle?",
                        ],
                        "answers": [
                            "Use almond gluten free cake mix.",
                            "Use almond gluten free cake mix with vanilla frosting.",
                        ],
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    off = score_memory_arena_artifact(input_path=str(export), mode="memory_off")
    on = score_memory_arena_artifact(input_path=str(export), mode="memory_on")
    stale = score_memory_arena_artifact(input_path=str(export), mode="stale")

    assert off["operation"] == "memory_arena_score"
    assert off["runner_boundary"]["implement_v2_used"] is False
    assert off["aggregate"]["expected_rows"] == 0
    assert on["rows_loaded"] == 1
    assert on["queries_scored"] == 1
    assert on["aggregate"]["expected_rows"] == 1
    assert on["aggregate"]["evidence_hit_rows"] == 1
    assert on["aggregate"]["recall_at_k"] == 1.0
    assert on["aggregate"]["hit_at_1"] == 1.0
    assert on["aggregate"]["mrr"] == 1.0
    assert stale["aggregate"]["expected_rows"] == 0
    assert stale["aggregate"]["stale_as_fresh_count"] == 0
    assert "memory arena score:" in on["summary"]


def test_memory_core_cli_memory_arena_score_writes_artifact(tmp_path):
    export = tmp_path / "memoryarena.json"
    artifact_path = tmp_path / "arena-artifact.json"
    export.write_text(
        json.dumps(
            [
                {
                    "id": "formal-1",
                    "questions": ["Remember lemma alpha.", "Which lemma helps the proof?"],
                    "answers": ["Lemma alpha rewrites x + 0 to x.", "Use lemma alpha."],
                }
            ]
        ),
        encoding="utf-8",
    )

    with redirect_stdout(StringIO()) as stdout:
        code = main(
            [
                "memory-core",
                "memory-arena-score",
                "--input",
                str(export),
                "--mode",
                "memory_on",
                "--artifact",
                str(artifact_path),
                "--json",
            ]
        )

    printed = json.loads(stdout.getvalue())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert code == 0
    assert printed["operation"] == "memory_arena_score"
    assert printed["aggregate"]["recall_at_k"] == 1.0
    assert artifact["runner_config_hash"] == printed["runner_config_hash"]


def test_memory_core_cli_memory_arena_tool_score_writes_artifact(tmp_path):
    export = tmp_path / "memoryarena.json"
    artifact_path = tmp_path / "arena-tool-artifact.json"
    export.write_text(
        json.dumps(
            [
                {
                    "id": "formal-2",
                    "questions": ["Remember lemma beta.", "Which lemma helps now?"],
                    "answers": ["Lemma beta rewrites 0 + x to x.", "Use lemma beta."],
                }
            ]
        ),
        encoding="utf-8",
    )

    with redirect_stdout(StringIO()) as stdout:
        code = main(
            [
                "memory-core",
                "memory-arena-tool-score",
                "--input",
                str(export),
                "--mode",
                "memory_on",
                "--artifact",
                str(artifact_path),
                "--json",
            ]
        )

    printed = json.loads(stdout.getvalue())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert code == 0
    assert printed["operation"] == "memory_arena_tool_score"
    assert printed["tool_call_counts"]["memory_save:saved"] == 2
    assert printed["tool_call_counts"]["memory_recall"] == 1
    assert artifact["runner_config_hash"] == printed["runner_config_hash"]


def test_memory_arena_tool_score_uses_save_then_recall_surface(tmp_path):
    export = tmp_path / "memoryarena.json"
    export.write_text(
        json.dumps(
            [
                {
                    "id": "travel-1",
                    "backgrounds": [
                        "Alice starts in Kyoto.",
                        "Bob joins Alice after the first leg.",
                    ],
                    "questions": [
                        "Plan Alice's first train.",
                        "Which city should Bob join from?",
                        "Which earlier plan should be reused?",
                    ],
                    "answers": [
                        "Alice takes the train from Kyoto to Osaka.",
                        "Bob should join from Osaka.",
                        "Reuse the Kyoto to Osaka leg.",
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    off = score_memory_arena_tool_artifact(input_path=str(export), mode="memory_off")
    on = score_memory_arena_tool_artifact(input_path=str(export), mode="memory_on")
    stale = score_memory_arena_tool_artifact(input_path=str(export), mode="stale")

    assert off["operation"] == "memory_arena_tool_score"
    assert off["runner_boundary"]["native_memory_tool_harness"] is True
    assert off["aggregate"]["expected_rows"] == 0
    assert off["tool_call_counts"]["memory_save:skipped_memory_off"] == 3

    assert on["aggregate"]["expected_rows"] == 2
    assert on["aggregate"]["recall_at_k"] == 1.0
    assert on["aggregate"]["hit_at_1"] == 1.0
    assert on["tool_call_counts"]["memory_save:saved"] == 3
    assert on["tool_call_counts"]["memory_recall"] == 2
    assert on["row_results"][0]["query"].startswith("Bob joins Alice")

    assert stale["aggregate"]["expected_rows"] == 0
    assert stale["aggregate"]["stale_as_fresh_count"] == 0
    assert stale["tool_call_counts"]["memory_save:saved"] == 3
