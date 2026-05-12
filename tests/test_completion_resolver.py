import ast
import subprocess
import sys
import json
from pathlib import Path

from mew.implement_lane.completion_resolver import (
    COMPLETION_RESOLVER_POLICY_VERSION,
    CompletionResolver,
    CompletionResolverInput,
    FinishClaim,
    write_completion_resolver_artifacts,
)


def _finish_claim() -> FinishClaim:
    return FinishClaim(
        lane_attempt_id="attempt-1",
        turn_id="turn-4",
        finish_call_id="finish-1",
        finish_output_call_id="finish-1",
        outcome="completed",
        summary="done",
    )


def test_completion_resolver_allows_finish_with_fresh_evidence() -> None:
    decision = CompletionResolver().resolve(
        CompletionResolverInput(
            finish_claim=_finish_claim(),
            transcript_hash_before_decision="sha256:transcript",
            compact_sidecar_digest_hash="sha256:sidecar",
            typed_evidence_refs=("ev:artifact:frame",),
            fresh_verifier_refs=("ev:strict-verifier:pass",),
            verifier_required=True,
        )
    )

    assert decision.result == "allow"
    assert decision.lane_status == "completed"
    assert decision.policy_version == COMPLETION_RESOLVER_POLICY_VERSION
    assert decision.evidence_refs == ("ev:artifact:frame", "ev:strict-verifier:pass")
    assert decision.as_dict()["decision_id"] == "resolver:turn-4:finish-1"


def test_completion_resolver_missing_required_verifier_blocks_continue() -> None:
    decision = CompletionResolver().resolve(
        CompletionResolverInput(
            finish_claim=_finish_claim(),
            verifier_required=True,
            oracle_obligation_refs=("external_artifact:/tmp/frame.bmp",),
        )
    )

    assert decision.result == "block"
    assert decision.lane_status == "blocked_continue"
    assert "verifier_evidence_missing" in decision.blockers
    assert "strict_verifier_evidence" in decision.missing_obligations


def test_completion_resolver_unsafe_or_budget_blocker_blocks_return() -> None:
    decision = CompletionResolver().resolve(
        CompletionResolverInput(
            finish_claim=_finish_claim(),
            unsafe_blockers=("write_outside_allowed_root",),
            budget_blockers=("wall_budget_exhausted",),
        )
    )

    assert decision.result == "block"
    assert decision.lane_status == "blocked_return"
    assert decision.blockers == ("write_outside_allowed_root", "wall_budget_exhausted")


def test_completion_resolver_rejects_raw_transcript_or_tool_payload_inputs() -> None:
    payload = {"finish_claim": _finish_claim().as_dict(), "transcript_items": [{"kind": "finish_call"}]}

    try:
        CompletionResolverInput.from_mapping(payload)
    except ValueError as exc:
        assert "transcript_items" in str(exc)
    else:
        raise AssertionError("expected raw transcript input rejection")


def test_completion_resolver_rejects_unsupported_or_nested_raw_inputs() -> None:
    unsupported = {"finish_claim": _finish_claim().as_dict(), "messages": []}
    nested = {
        "finish_claim": {
            **_finish_claim().as_dict(),
            "arguments": {"tool_results": [{"status": "completed"}]},
        },
    }
    readiness = {
        "finish_claim": _finish_claim().as_dict(),
        "finish_readiness": {"raw_transcript": [{"kind": "finish_call"}]},
    }

    for payload, expected in (
        (unsupported, "unsupported keys: messages"),
        (nested, "finish_claim.arguments.tool_results"),
        (readiness, "finish_readiness.raw_transcript"),
    ):
        try:
            CompletionResolverInput.from_mapping(payload)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"expected resolver input rejection for {expected}")


def test_completion_resolver_writes_jsonl_and_manifest_ref(tmp_path: Path) -> None:
    manifest = tmp_path / "proof-manifest.json"
    manifest.write_text('{"schema_version":1}\n', encoding="utf-8")
    decision = CompletionResolver().resolve(
        CompletionResolverInput(
            finish_claim=_finish_claim(),
            typed_evidence_refs=("ev:artifact:frame",),
        )
    )

    paths = write_completion_resolver_artifacts(tmp_path, [decision], proof_manifest_path=manifest)

    decision_path = paths["resolver_decisions"]
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [decision.as_dict()]
    updated_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert updated_manifest["resolver_decisions_ref"] == "resolver_decisions.jsonl"
    assert str(updated_manifest["resolver_decisions_sha256"]).startswith("sha256:")


def test_completion_resolver_has_no_tool_runtime_import_boundary() -> None:
    source = Path("src/mew/implement_lane/completion_resolver.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")

    forbidden = {
        "mew.implement_lane.exec_runtime",
        "mew.implement_lane.native_tool_harness",
        "mew.implement_lane.read_runtime",
        "mew.implement_lane.write_runtime",
        "src.mew.implement_lane.exec_runtime",
        "src.mew.implement_lane.native_tool_harness",
        "src.mew.implement_lane.read_runtime",
        "src.mew.implement_lane.write_runtime",
    }
    assert imported_modules.isdisjoint(forbidden)


def test_completion_resolver_package_import_does_not_initialize_harness_or_runtime() -> None:
    code = """
import json
import sys
import mew.implement_lane.completion_resolver
forbidden = [
    'mew.implement_lane.exec_runtime',
    'mew.implement_lane.native_tool_harness',
    'mew.implement_lane.read_runtime',
    'mew.implement_lane.write_runtime',
]
print(json.dumps({name: name in sys.modules for name in forbidden}, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    loaded = json.loads(result.stdout)
    assert loaded == {
        "mew.implement_lane.exec_runtime": False,
        "mew.implement_lane.native_tool_harness": False,
        "mew.implement_lane.read_runtime": False,
        "mew.implement_lane.write_runtime": False,
    }
