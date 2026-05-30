import json
from pathlib import Path

from mew.memory_eval.fixtures import find_label_leakage, load_fixture, reset_payload, split_fixture
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.runner import run_fixture
from mew.memory_eval.adapters import DummyPassAdapter


ROOT = Path(__file__).resolve().parents[1]
P0_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p0"


def test_fixture_split_hides_scorer_data_and_uses_opaque_ids():
    views = split_fixture(load_fixture(P0_FIXTURES / "dummy_happy_path.json"), fixture_ordinal=7)

    serialized = canonical_json(views.adapter_view)

    assert views.adapter_fixture_id == "fx_000007"
    assert views.adapter_view["requests"][0]["request_id"] == "rq_000001"
    assert views.adapter_view["experiences"][0]["experience_id"] == "ex_000001"
    assert views.id_maps["experience_id_to_adapter"]["exp_alpha"] == "ex_000001"
    assert views.id_maps["adapter_experience_id_to_scorer"]["ex_000001"] == "exp_alpha"
    assert "req_dummy_primary" not in serialized
    assert "exp_alpha" not in serialized
    assert "dummy_happy_path" not in serialized
    assert "gold" not in serialized
    assert "mode" not in serialized
    assert "relevant_evidence_ids" not in serialized
    assert "must_not_return_evidence_ids" not in serialized
    assert find_label_leakage(views.adapter_view) == []

    reset = reset_payload(views, run_id="run_fixed", seed=12345)
    assert reset["fixture_id"] == "fx_000007"
    assert reset["fixture_public_hash"] == views.fixture_public_hash
    assert "fixture_gold_hash" not in reset
    assert "fixture_full_hash" not in reset


def test_fixture_split_remaps_experience_and_mutation_refs_from_adapter_view():
    views = split_fixture(load_fixture(P0_FIXTURES / "broken_stale_as_fresh.json"))
    serialized = canonical_json(views.adapter_view)

    assert views.adapter_view["experiences"][0]["experience_id"] == "ex_000001"
    assert views.adapter_view["experiences"][1]["experience_id"] == "ex_000002"
    assert views.adapter_view["mutations"][0]["op_id"] == "mu_000001"
    assert views.adapter_view["mutations"][0]["target_experience_id"] == "ex_000001"
    assert views.adapter_view["mutations"][0]["replacement_experience_id"] == "ex_000002"
    assert views.adapter_view["operation_sequence"][0]["experience_id"] == "ex_000001"
    assert views.adapter_view["operation_sequence"][2]["op_id"] == "mu_000001"
    assert "exp_old" not in serialized
    assert "exp_new" not in serialized
    assert "mut_supersede" not in serialized
    assert find_label_leakage(views.adapter_view) == []


def test_adapter_view_value_scan_detects_blocked_public_tokens():
    views = split_fixture(load_fixture(P0_FIXTURES / "broken_label_leakage_public_token.json"))

    failures = find_label_leakage(views.adapter_view)

    assert failures
    assert {failure["type"] for failure in failures} == {"label_leakage"}
    assert any(failure["gate_id"] == "no_label_leakage" for failure in failures)


def test_runner_turns_label_leakage_into_failed_artifact_without_adapter_gold_exposure():
    artifact = run_fixture(
        P0_FIXTURES / "broken_label_leakage_public_token.json",
        DummyPassAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )

    assert artifact["requests"][0]["result_status"] == "failed"
    assert artifact["requests"][0]["hard_gates"][0]["gate_id"] == "no_label_leakage"
    assert artifact["requests"][0]["hard_gates"][0]["passed"] is False
    assert {failure["type"] for failure in artifact["failures"]} == {"label_leakage"}


def test_memory_eval_core_does_not_import_mew_memory_internals():
    source_root = ROOT / "src" / "mew" / "memory_eval"
    blocked = [
        "memory" + "_core",
        "memory" + "_arena",
        "Memory" + "ContextBuilder",
        "Memory" + "Arena",
        "implement" + "_v2",
        "Tool" + "Registry",
        "PromptSection" + "Registry",
    ]
    offenders = []
    for path in source_root.rglob("*.py"):
        if "adapters" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for token in blocked:
            if token in text:
                offenders.append((path.name, token))

    assert offenders == []


def test_fixture_public_hash_is_independent_from_json_key_order():
    fixture = load_fixture(P0_FIXTURES / "dummy_happy_path.json")
    reordered = json.loads(json.dumps(fixture, sort_keys=True))

    views_a = split_fixture(fixture)
    views_b = split_fixture(reordered)

    assert views_a.fixture_public_hash == views_b.fixture_public_hash
    assert views_a.fixture_gold_hash == views_b.fixture_gold_hash
