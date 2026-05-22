from copy import deepcopy
from pathlib import Path

from mew.memory_eval.adapters import DummyPassAdapter
from mew.memory_eval.hashing import canonical_json, stable_hash
from mew.memory_eval.runner import run_fixture
from mew.memory_eval.scoring import retrieval_result_hash_input_hash


ROOT = Path(__file__).resolve().parents[1]
P0_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p0"


def test_canonical_json_hash_ignores_object_key_order():
    left = {"b": [2, {"d": "x", "c": "y"}], "a": 1}
    right = {"a": 1, "b": [2, {"c": "y", "d": "x"}]}

    assert canonical_json(left) == canonical_json(right)
    assert stable_hash(left) == stable_hash(right)


def test_retrieval_result_hash_excludes_measured_usage_values():
    artifact = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        DummyPassAdapter(),
        run_id="run_one",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    retrieval = deepcopy(request["retrieval"])

    baseline = request["retrieval_result_hash"]
    request["usage"]["latency_ms"]["retrieve"] = 9999
    request["usage"]["cost"]["cost_units"] = 42
    request["usage"]["tokens"]["adapter_internal_input_tokens"] = 12345

    assert retrieval_result_hash_input_hash(retrieval) == baseline

    changed = deepcopy(retrieval)
    changed["returned_evidence_order"][0]["support_experience_ids"] = ["exp_beta"]
    changed["returned_evidence_order"][0]["scorable_support_ids"] = ["exp_beta"]
    assert retrieval_result_hash_input_hash(changed) != baseline


def test_deterministic_result_hash_is_stable_across_run_ids_and_created_at():
    first = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        DummyPassAdapter(),
        run_id="run_one",
        created_at="2026-05-21T00:00:00Z",
    )
    second = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        DummyPassAdapter(),
        run_id="run_two",
        created_at="2026-05-21T00:00:01Z",
    )

    assert first["artifact_hashes"]["deterministic_result_hash"] == second["artifact_hashes"][
        "deterministic_result_hash"
    ]
    assert first["artifact_hashes"]["volatile_run_hash"] != second["artifact_hashes"]["volatile_run_hash"]
    assert first["requests"][0]["request_hash"] == second["requests"][0]["request_hash"]
    assert first["requests"][0]["operation_prefix_hash"] == second["requests"][0]["operation_prefix_hash"]
