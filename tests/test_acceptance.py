from mew.acceptance import (
    acceptance_done_gate_decision,
    acceptance_finish_blocker,
    coerce_acceptance_checks,
    exact_command_example_requirements,
    extract_acceptance_constraints,
    finish_continuation_prompt,
    implementation_contract_source_requirements,
    is_long_dependency_toolchain_build_task,
    is_model_inference_output_task,
    is_numeric_artifact_task,
    is_query_only_hidden_model_task,
    is_runtime_visual_artifact_task,
    long_dependency_final_artifacts,
    runtime_component_finish_gate_decision,
)
from mew.acceptance_evidence import long_dependency_artifact_proven_by_call
from mew.implement_lane.execution_evidence import (
    DoneDecision,
    EvidenceEvent,
    FinishClaim,
    OracleBundle,
    OracleObligation,
    recommend_finish_evidence_refs,
    resolve_typed_finish,
)


def test_resolve_typed_finish_returns_neutral_without_oracle_bundle():
    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:artifact:frame"},)),
        None,
        (EvidenceEvent(id="ev:artifact:frame", kind="artifact_check", status="passed", observed={"path": "frame.bmp"}),),
    )

    assert isinstance(decision, DoneDecision)
    assert decision.decision == "no_typed_decision"
    assert decision.gate_source == "none"


def test_resolve_typed_finish_blocks_completed_finish_without_refs():
    bundle = OracleBundle(
        id="oracle:bundle:frame",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"exists": True},
                source="test",
            ),
        ),
    )

    decision = resolve_typed_finish(FinishClaim(outcome="completed"), bundle, ())

    assert decision.decision == "block_continue"
    assert decision.gate_source == "typed_evidence"
    assert decision.missing_obligations
    assert "typed evidence" in decision.continuation_prompt


def test_resolve_typed_finish_allows_cited_passing_artifact_event():
    bundle = OracleBundle(
        id="oracle:bundle:frame",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"exists": True},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.bmp", "status": "passed"},
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:artifact:frame"},)),
        bundle,
        (event,),
    )

    assert decision.decision == "allow_complete"
    assert decision.gate_source == "typed_evidence"


def test_resolve_typed_finish_does_not_cross_satisfy_source_grounding():
    bundle = OracleBundle(
        id="oracle:bundle:source",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:source:b",
                kind="source_grounding",
                subject={"path": "src/b.py"},
                expected={"grounded": True},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:source:a",
        kind="source_grounding",
        status="passed",
        observed={"path": "src/a.py", "grounded": True},
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:source:a"},)),
        bundle,
        (event,),
    )

    assert decision.decision == "block_continue"
    assert decision.missing_obligations


def test_resolve_typed_finish_does_not_cross_satisfy_verifier_contracts():
    bundle = OracleBundle(
        id="oracle:bundle:verifier",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:verifier:b",
                kind="verifier_pass",
                subject={"contract_id": "contract:b"},
                expected={"verdict": "pass"},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:verifier:a",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass", "contract_id": "contract:a"},
        contract_id="contract:a",
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:verifier:a"},)),
        bundle,
        (event,),
    )

    assert decision.decision == "block_continue"
    assert decision.missing_obligations


def test_resolve_typed_finish_rejects_visual_similarity_without_oracle_measurement():
    bundle = OracleBundle(
        id="oracle:bundle:visual",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
                expected={"exists": True},
                source="test",
            ),
            OracleObligation(
                id="oracle:frame:visual_similarity",
                kind="visual_similarity",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"missing_reference": True},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:oracle:frame",
        kind="oracle_check",
        status="passed",
        observed={"kind": "visual_similarity", "artifact_id": "frame", "candidate_path": "frame.bmp"},
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:oracle:frame"},)),
        bundle,
        (event,),
    )

    assert decision.decision == "block_continue"
    assert decision.missing_obligations


def test_resolve_typed_finish_rejects_candidate_derived_visual_similarity():
    bundle = OracleBundle(
        id="oracle:bundle:visual",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:visual_similarity",
                kind="visual_similarity",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"reference_path": "/tmp/target.png", "threshold": 0.95, "comparator": ">="},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:oracle:frame",
        kind="oracle_check",
        status="passed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.99,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "model_authored"},
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:oracle:frame"},)),
        bundle,
        (event,),
    )

    assert decision.decision == "block_continue"
    assert decision.missing_obligations


def test_resolve_typed_finish_rejects_candidate_visual_pass_after_visual_failure():
    bundle = OracleBundle(
        id="oracle:bundle:visual",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:visual_similarity",
                kind="visual_similarity",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"reference_path": "/tmp/target.png", "threshold": 0.95, "comparator": ">="},
                source="test",
            ),
        ),
    )
    trusted_pass = EvidenceEvent(
        id="ev:oracle:trusted",
        kind="oracle_check",
        status="passed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.99,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "verifier_evidence"},
    )
    failed_oracle = EvidenceEvent(
        id="ev:oracle:failed",
        kind="oracle_check",
        status="failed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.5,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "verifier_evidence"},
    )
    candidate_pass = EvidenceEvent(
        id="ev:oracle:candidate",
        kind="oracle_check",
        status="passed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.99,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "model_authored"},
    )

    decision = resolve_typed_finish(
        FinishClaim(
            outcome="completed",
            evidence_refs=(
                {"kind": "evidence_event", "id": "ev:oracle:trusted"},
                {"kind": "evidence_event", "id": "ev:oracle:candidate"},
            ),
        ),
        bundle,
        (trusted_pass, failed_oracle, candidate_pass),
    )

    assert decision.decision == "block_continue"
    assert decision.failed_evidence_refs


def test_resolve_typed_finish_ignores_superseding_failure_for_other_verifier_contract():
    bundle = OracleBundle(
        id="oracle:bundle:verifier",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:verifier:a",
                kind="verifier_pass",
                subject={"contract_id": "contract:a"},
                expected={"verdict": "pass"},
                source="test",
            ),
        ),
    )
    pass_event = EvidenceEvent(
        id="ev:verifier:a:pass",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass", "contract_id": "contract:a"},
        contract_id="contract:a",
    )
    other_failure = EvidenceEvent(
        id="ev:verifier:b:fail",
        kind="verifier_result",
        status="failed",
        observed={"verdict": "fail", "contract_id": "contract:b"},
        contract_id="contract:b",
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:verifier:a:pass"},)),
        bundle,
        (pass_event, other_failure),
    )

    assert decision.decision == "allow_complete"


def test_resolve_typed_finish_rejects_artifact_pass_superseded_by_same_contract_verifier_failure():
    bundle = OracleBundle(
        id="oracle:bundle:artifact",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.txt"},
                expected={"exists": True},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
        ),
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.txt"},
        contract_id="contract:verify",
    )
    failed_verifier = EvidenceEvent(
        id="ev:verifier:verify",
        kind="verifier_result",
        status="failed",
        observed={"verdict": "fail"},
        contract_id="contract:verify",
    )

    decision = resolve_typed_finish(
        FinishClaim(outcome="completed", evidence_refs=({"kind": "evidence_event", "id": "ev:artifact:frame"},)),
        bundle,
        (artifact_event, failed_verifier),
    )

    assert decision.decision == "block_continue"
    assert decision.failed_evidence_refs


def test_resolve_typed_finish_uses_latest_artifact_cover_after_same_contract_retry():
    bundle = OracleBundle(
        id="oracle:bundle:artifact",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.txt"},
                expected={"exists": True},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
        ),
    )
    first_artifact = EvidenceEvent(
        id="ev:artifact:first",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.txt"},
        contract_id="contract:verify",
    )
    failed_verifier = EvidenceEvent(
        id="ev:verifier:first",
        kind="verifier_result",
        status="failed",
        observed={"verdict": "fail"},
        contract_id="contract:verify",
    )
    latest_artifact = EvidenceEvent(
        id="ev:artifact:latest",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.txt"},
        contract_id="contract:verify",
    )
    latest_verifier = EvidenceEvent(
        id="ev:verifier:latest",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass"},
        contract_id="contract:verify",
    )

    decision = resolve_typed_finish(
        FinishClaim(
            outcome="completed",
            evidence_refs=(
                {"kind": "evidence_event", "id": "ev:artifact:first"},
                {"kind": "evidence_event", "id": "ev:artifact:latest"},
                {"kind": "evidence_event", "id": "ev:verifier:latest"},
            ),
        ),
        bundle,
        (first_artifact, failed_verifier, latest_artifact, latest_verifier),
    )

    assert decision.decision == "allow_complete"


def test_recommend_finish_evidence_refs_selects_late_covering_events():
    bundle = OracleBundle(
        id="oracle:bundle:late-artifact",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"exists": True},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
            OracleObligation(
                id="oracle:contract:verify:verifier_pass",
                kind="verifier_pass",
                subject={"contract_id": "contract:verify"},
                expected={"verdict": "pass"},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
        ),
    )
    early_events = tuple(
        EvidenceEvent(
            id=f"ev:artifact:early:{index}",
            kind="artifact_check",
            status="passed",
            observed={"artifact_id": f"early-{index}", "path": f"early-{index}.txt"},
            contract_id=f"contract:early:{index}",
        )
        for index in range(20)
    )
    latest_artifact = EvidenceEvent(
        id="ev:artifact:late-frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.bmp"},
        contract_id="contract:verify",
    )
    latest_verifier = EvidenceEvent(
        id="ev:verifier:late-pass",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass", "contract_id": "contract:verify"},
        contract_id="contract:verify",
    )

    refs = recommend_finish_evidence_refs(bundle, (*early_events, latest_artifact, latest_verifier), limit=16)

    assert {"kind": "evidence_event", "id": "ev:artifact:late-frame"} in refs
    assert {"kind": "evidence_event", "id": "ev:verifier:late-pass"} in refs
    assert len(refs) <= 16
    decision = resolve_typed_finish(FinishClaim(outcome="completed", evidence_refs=refs), bundle, (*early_events, latest_artifact, latest_verifier))
    assert decision.decision == "allow_complete"


def test_resolve_typed_finish_accepts_string_evidence_refs():
    bundle = OracleBundle(
        id="oracle:bundle:artifact",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.txt"},
                expected={"exists": True},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
        ),
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.txt"},
        contract_id="contract:verify",
    )

    decision = resolve_typed_finish(
        {"outcome": "completed", "evidence_refs": ["ev:artifact:frame"]},
        bundle,
        (artifact_event,),
    )

    assert decision.decision == "allow_complete"


def test_resolve_typed_finish_accepts_command_run_id_alias_for_covering_events():
    bundle = OracleBundle(
        id="oracle:bundle:runtime-frame",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.bmp"},
                expected={"exists": True},
                source="execution_contract",
            ),
            OracleObligation(
                id="oracle:contract:verify:verifier_pass",
                kind="verifier_pass",
                subject={"contract_id": "contract:verify"},
                expected={"verdict": "pass"},
                source="execution_contract",
            ),
        ),
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.bmp"},
        refs=({"kind": "command_run", "id": "cmd:final-verifier"},),
        contract_id="contract:verify",
        command_run_id="cmd:final-verifier",
    )
    verifier_event = EvidenceEvent(
        id="ev:verifier:final",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass", "contract_id": "contract:verify"},
        refs=({"kind": "command_run", "id": "cmd:final-verifier"},),
        contract_id="contract:verify",
        command_run_id="cmd:final-verifier",
    )

    decision = resolve_typed_finish(
        FinishClaim(
            outcome="completed",
            evidence_refs=({"kind": "command_run", "id": "cmd:final-verifier"},),
        ),
        bundle,
        (artifact_event, verifier_event),
    )

    assert decision.decision == "allow_complete"


def test_finish_continuation_prompt_points_visual_quality_to_task_verifiers():
    prompt = finish_continuation_prompt(
        [
            "runtime visual artifact quality evidence ungrounded: artifact existence, "
            "nonzero pixels, valid headers, or self-consistent dimensions are not enough"
        ]
    )

    assert "task-provided verifier/test/reference artifacts" in prompt
    assert "expected-output markers" in prompt
    assert "Do not rely on artifact existence" in prompt


def test_resolve_typed_finish_allows_latest_same_contract_verifier_pass_after_failure():
    bundle = OracleBundle(
        id="oracle:bundle:artifact",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:contract:verify:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "frame.txt"},
                expected={"exists": True},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": "contract:verify"},),
            ),
        ),
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "frame.txt"},
        contract_id="contract:verify",
    )
    failed_verifier = EvidenceEvent(
        id="ev:verifier:first",
        kind="verifier_result",
        status="failed",
        observed={"verdict": "fail"},
        contract_id="contract:verify",
    )
    latest_verifier = EvidenceEvent(
        id="ev:verifier:latest",
        kind="verifier_result",
        status="passed",
        observed={"verdict": "pass"},
        contract_id="contract:verify",
    )

    decision = resolve_typed_finish(
        FinishClaim(
            outcome="completed",
            evidence_refs=(
                {"kind": "evidence_event", "id": "ev:artifact:frame"},
                {"kind": "evidence_event", "id": "ev:verifier:latest"},
            ),
        ),
        bundle,
        (artifact_event, failed_verifier, latest_verifier),
    )

    assert decision.decision == "allow_complete"


def test_acceptance_done_gate_allows_typed_retired_runtime_visual_family():
    bundle = OracleBundle(
        id="oracle:bundle:visual",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:visual_similarity",
                kind="visual_similarity",
                subject={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
                expected={"reference_path": "/tmp/target.png", "threshold": 0.95, "comparator": ">="},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:oracle:frame",
        kind="oracle_check",
        status="passed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "/tmp/frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.99,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "verifier_evidence"},
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
        obligation_id="oracle:frame:exists",
        refs=({"kind": "tool_call", "id": "verify-frame"},),
        provenance={"source": "verifier_evidence"},
    )
    decision = acceptance_done_gate_decision(
        (
            "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
            "I will check that the first rendered frame is correct."
        ),
        {
            "type": "finish",
            "task_done": True,
            "evidence_refs": [
                {"kind": "evidence_event", "id": "ev:artifact:frame"},
                {"kind": "evidence_event", "id": "ev:oracle:frame"},
            ],
        },
        session={
            "typed_acceptance": {
                "oracle_bundle": bundle.as_dict(),
                "evidence_events": [artifact_event.as_dict(), event.as_dict()],
                "retired_legacy_blockers": [
                    "runtime_final_verifier_artifact_evidence",
                    "runtime_visual_artifact_quality_evidence",
                ],
            }
        },
    )

    assert decision["decision"] == "allow_complete"
    assert decision["gate_source"] == "typed_evidence"
    assert decision["legacy_warnings"]


def test_acceptance_done_gate_keeps_legacy_block_when_typed_family_not_retired():
    bundle = OracleBundle(
        id="oracle:bundle:visual",
        source="test",
        obligations=(
            OracleObligation(
                id="oracle:frame:exists",
                kind="artifact_exists",
                subject={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
                expected={"exists": True},
                source="test",
            ),
            OracleObligation(
                id="oracle:frame:visual_similarity",
                kind="visual_similarity",
                subject={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
                expected={"reference_path": "/tmp/target.png", "threshold": 0.95, "comparator": ">="},
                source="test",
            ),
        ),
    )
    event = EvidenceEvent(
        id="ev:oracle:frame",
        kind="oracle_check",
        status="passed",
        observed={
            "kind": "visual_similarity",
            "artifact_id": "frame",
            "candidate_path": "/tmp/frame.bmp",
            "reference_path": "/tmp/target.png",
            "score": 0.99,
            "threshold": 0.95,
        },
        obligation_id="oracle:frame:visual_similarity",
        oracle_id="oracle:frame:visual_similarity",
        provenance={"source": "verifier_evidence"},
    )
    artifact_event = EvidenceEvent(
        id="ev:artifact:frame",
        kind="artifact_check",
        status="passed",
        observed={"artifact_id": "frame", "path": "/tmp/frame.bmp"},
        obligation_id="oracle:frame:exists",
        refs=({"kind": "tool_call", "id": "verify-frame"},),
        provenance={"source": "verifier_evidence"},
    )

    decision = acceptance_done_gate_decision(
        (
            "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
            "I will check that the first rendered frame is correct."
        ),
        {
            "type": "finish",
            "task_done": True,
            "evidence_refs": [
                {"kind": "evidence_event", "id": "ev:artifact:frame"},
                {"kind": "evidence_event", "id": "ev:oracle:frame"},
            ],
        },
        session={
            "typed_acceptance": {
                "oracle_bundle": bundle.as_dict(),
                "evidence_events": [artifact_event.as_dict(), event.as_dict()],
            }
        },
    )

    assert decision["decision"] == "block_continue"
    assert decision["gate_source"] == "legacy_string_safety"
    assert decision["blockers"][0]["code"] == "runtime_final_verifier_artifact_evidence"


def test_extract_acceptance_constraints_keeps_output_and_edit_scope_rules():
    text = (
        'Ensure that the LaTeX document main.tex compiles successfully with no "overfull hbox" warnings. '
        "In doing so, the only edits you may make are to replace words in input.tex with their specified "
        "synonyms in synonyms.txt. Do not edit main.tex or synonyms.txt."
    )

    constraints = extract_acceptance_constraints(text)

    assert any("no \"overfull hbox\" warnings" in item for item in constraints)
    assert any("only edits" in item and "synonyms.txt" in item for item in constraints)
    assert any("Do not edit main.tex or synonyms.txt" in item for item in constraints)


def test_acceptance_finish_blocker_requires_verified_checks_for_task_done():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True})

    assert "acceptance constraints unchecked" in blocker


def test_acceptance_finish_blocker_accepts_complete_verified_checks():
    text = "Ensure the output file exists. Do not edit config.json."
    constraints = extract_acceptance_constraints(text)
    checks = [
        {"constraint": constraint, "status": "verified", "evidence": "tool #3 output confirmed it"}
        for constraint in constraints
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""
    assert coerce_acceptance_checks(checks) == checks


def test_acceptance_finish_blocker_rejects_stateful_output_relabel_only():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed; asserted the live desk label appears in the speech bubble.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": "PASS: asserted live desk label appears in the speech bubble.",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_runtime_component_import_only_proof():
    text = (
        "The compiled extensions (chelpers, ccomplexity, and cinvariants) "
        "should work in their original context from Python side."
    )
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Compiled extensions chelpers, ccomplexity, and cinvariants should work",
                "status": "verified",
                "evidence": (
                    "Command evidence #13 imported chelpers, ccomplexity, and cinvariants "
                    "and printed their installed .so module paths."
                ),
                "evidence_refs": [{"kind": "command_evidence", "id": 13}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 13,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": (
                    "from pyknotid.spacecurves import chelpers, ccomplexity; "
                    "from pyknotid import cinvariants; print(chelpers.__file__, ccomplexity.__file__)"
                ),
                "output_tail": "pyknotid.spacecurves.ccomplexity /usr/local/lib/.../ccomplexity.so\n",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, action, session=session)

    assert "runtime component behavior evidence import-only" in blocker


def test_acceptance_finish_blocker_accepts_runtime_component_behavior_proof():
    text = "The compiled extensions should work in their original context from Python side."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Compiled extensions should work",
                "status": "verified",
                "evidence": "Command evidence #13 invoked exported function behavior.",
                "evidence_refs": [{"kind": "command_evidence", "id": 13}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 13,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python - <<'PY'\nimport native_ext; print(native_ext.exported_function())\nPY",
                "output_tail": "compiled extension exported function returned 0.0\n",
            }
        ]
    }

    assert acceptance_finish_blocker(text, action, session=session) == ""


def test_runtime_component_finish_gate_accepts_targeted_component_test_ref():
    text = "The native module should work in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Behavior proof",
                "status": "verified",
                "evidence": "Command evidence #21 ran the targeted component test.",
                "evidence_refs": [{"kind": "command_evidence", "id": 21}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 21,
                "tool": "run_tests",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "pytest tests/test_runtime_component.py::test_component_behavior",
                "output_tail": "repository-test-tail targeted component test passed\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "allow_complete"


def test_runtime_component_finish_gate_rejects_attribute_access_only():
    text = "The native module should work in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Native module behavior proof",
                "status": "verified",
                "evidence": "Command evidence #22 checked the module has the behavior attribute.",
                "evidence_refs": [{"kind": "command_evidence", "id": 22}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 22,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module; print(hasattr(native_module, \"behavior\"))'",
                "output_tail": "True\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_rejects_import_only_run_tests():
    text = "The native module should run in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Native module runtime behavior proof",
                "status": "verified",
                "evidence": "Command evidence #23 ran an import test.",
                "evidence_refs": [{"kind": "command_evidence", "id": 23}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 23,
                "tool": "run_tests",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "pytest tests/test_runtime_component.py::test_import_runtime_component",
                "output_tail": "test_import_runtime_component passed; imported module path /tmp/native_module.so\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_rejects_verifier_labeled_path_probe():
    text = "The native module should execute in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Native module runtime behavior proof",
                "status": "verified",
                "evidence": "Command evidence #24 ran the verifier-labeled command.",
                "evidence_refs": [{"kind": "command_evidence", "id": 24}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 24,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module; print(native_module.__file__)'",
                "execution_contract": {"acceptance_kind": "external_verifier", "proof_role": "verifier"},
                "output_tail": "external verifier path proof passed: /tmp/native_module.so\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_rejects_verifier_labeled_hasattr_probe():
    text = "The native module should execute in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Native module runtime behavior proof",
                "status": "verified",
                "evidence": "Command evidence #25 ran the verifier-labeled command.",
                "evidence_refs": [{"kind": "command_evidence", "id": 25}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 25,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module; print(hasattr(native_module, \"behavior\"))'",
                "execution_contract": {"acceptance_kind": "external_verifier", "proof_role": "verifier"},
                "output_tail": "external verifier behavior attribute exists: True\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_blocks_generated_executable_path_until_execution_smoke():
    text = "The generated executable should run from the repository runtime context."
    path_only_action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Generated executable runs.",
                "status": "verified",
                "evidence": "Command evidence #26 proved the executable path exists.",
                "evidence_refs": [{"kind": "command_evidence", "id": 26}],
            }
        ],
    }
    smoke_action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Generated executable runs.",
                "status": "verified",
                "evidence": "Command evidence #27 executed the smoke path.",
                "evidence_refs": [{"kind": "command_evidence", "id": 27}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 26,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "test -x dist/tool && echo executable path exists",
                "output_tail": "executable path exists\n",
            },
            {
                "id": 27,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "./dist/tool --smoke",
                "output_tail": "execution smoke passed\n",
            },
        ]
    }

    blocked = runtime_component_finish_gate_decision(text, path_only_action, session=session)
    allowed = runtime_component_finish_gate_decision(text, smoke_action, session=session)

    assert blocked["decision"] == "block_continue"
    assert blocked["blockers"][0]["code"] == "runtime_component_behavior_evidence"
    assert allowed["decision"] == "allow_complete"


def test_runtime_component_finish_gate_blocks_non_behavior_entrypoint_shapes():
    text = "The generated executable should run from the repository runtime context."
    blocked_commands = [
        ("python setup.py build", "build completed\n"),
        ("python -m build", "wheel built\n"),
        ("python -m pip install .", "installed package\n"),
        ("node build.js", "build script completed\n"),
        ("./configure", "configured successfully\n"),
        ("./dist/tool --help", "usage: tool [OPTIONS]\n"),
        ("./dist/tool --version", "tool 1.2.3\n"),
        ("python readback.py", "readback matched expected path\n"),
        ("node list.js", "listing generated files\n"),
        ("./dist/noop", "no-op completed\n"),
    ]
    session = {"command_evidence": []}
    for offset, (command, output_tail) in enumerate(blocked_commands, start=40):
        session["command_evidence"].append(
            {
                "id": offset,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": command,
                "output_tail": output_tail,
            }
        )

    for offset, (command, _output_tail) in enumerate(blocked_commands, start=40):
        action = {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Generated executable runs.",
                    "status": "verified",
                    "evidence": f"Command evidence #{offset} ran {command}.",
                    "evidence_refs": [{"kind": "command_evidence", "id": offset}],
                }
            ],
        }
        decision = runtime_component_finish_gate_decision(text, action, session=session)
        assert decision["decision"] == "block_continue", command
        assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_accepts_explicit_callable_with_neutral_output():
    text = "The native module should run in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Native module runtime behavior proof.",
                "status": "verified",
                "evidence": "Command evidence #60 invoked native_module.run().",
                "evidence_refs": [{"kind": "command_evidence", "id": 60}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 60,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module; print(native_module.run())'",
                "output_tail": "ok\n",
            }
        ]
    }

    decision = runtime_component_finish_gate_decision(text, action, session=session)

    assert decision["decision"] == "allow_complete"


def test_runtime_component_finish_gate_rejects_claim_text_only_entrypoint_behavior_signal():
    text = "The generated executable should run from the repository runtime context."
    session = {
        "command_evidence": [
            {
                "id": 70,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "./dist/tool",
                "output_tail": "hello world\n",
            },
            {
                "id": 71,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python script.py",
                "output_tail": "42\n",
            },
            {
                "id": 72,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "./dist/tool --smoke",
                "output_tail": "execution smoke passed\n",
            },
        ]
    }

    spoofed_tool_action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Generated executable runs.",
                "status": "verified",
                "evidence": "Command evidence #70 ran the runtime component to verify behavior.",
                "evidence_refs": [{"kind": "command_evidence", "id": 70}],
            }
        ],
    }
    spoofed_script_action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Generated executable runs.",
                "status": "verified",
                "evidence": "Command evidence #71 ran successfully; behavior executed; runtime smoke passed.",
                "evidence_refs": [{"kind": "command_evidence", "id": 71}],
            }
        ],
    }
    objective_smoke_action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Generated executable runs.",
                "status": "verified",
                "evidence": "Command evidence #72 completed.",
                "evidence_refs": [{"kind": "command_evidence", "id": 72}],
            }
        ],
    }

    blocked_tool = runtime_component_finish_gate_decision(text, spoofed_tool_action, session=session)
    blocked_script = runtime_component_finish_gate_decision(text, spoofed_script_action, session=session)
    allowed_smoke = runtime_component_finish_gate_decision(text, objective_smoke_action, session=session)

    assert blocked_tool["decision"] == "block_continue"
    assert blocked_tool["blockers"][0]["code"] == "runtime_component_behavior_evidence"
    assert blocked_script["decision"] == "block_continue"
    assert blocked_script["blockers"][0]["code"] == "runtime_component_behavior_evidence"
    assert allowed_smoke["decision"] == "allow_complete"


def test_runtime_component_finish_gate_rejects_loader_api_calls_as_behavior():
    text = "The shared library runtime component should run in its original runtime context."
    blocked_commands = [
        "python -c 'import ctypes; ctypes.CDLL(\"libx.so\")'",
        "python -c 'import ctypes; ctypes.cdll.LoadLibrary(\"libx.so\")'",
        "python -c 'ffi.dlopen(\"libx.so\")'",
        "python -c 'import importlib; importlib.import_module(\"native_module\")'",
        "python -c 'loader.load_library(\"libx\", \".\")'",
    ]
    session = {"command_evidence": []}
    for offset, command in enumerate(blocked_commands, start=80):
        session["command_evidence"].append(
            {
                "id": offset,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": command,
                "output_tail": "loaded\n",
            }
        )

    for offset, command in enumerate(blocked_commands, start=80):
        action = {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Shared library runtime behavior proof.",
                    "status": "verified",
                    "evidence": f"Command evidence #{offset} loaded and invoked {command}.",
                    "evidence_refs": [{"kind": "command_evidence", "id": offset}],
                }
            ],
        }
        decision = runtime_component_finish_gate_decision(text, action, session=session)
        assert decision["decision"] == "block_continue", command
        assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"


def test_runtime_component_finish_gate_allows_pure_documentation_task():
    decision = runtime_component_finish_gate_decision(
        "Document how the runtime component interpreter works in README.md.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "README explains the interpreter.",
                    "status": "verified",
                    "evidence": "Read the updated README.",
                }
            ],
        },
        session={},
    )

    assert decision["decision"] == "allow_complete"


def test_runtime_component_finish_gate_allows_no_change_investigation_task():
    decision = runtime_component_finish_gate_decision(
        "Investigate why the native module does not work; report findings only and do not modify source.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Investigation findings are reported.",
                    "status": "verified",
                    "evidence": "Summarized the observed failure family.",
                }
            ],
        },
        session={},
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_finish_blocker_rejects_runtime_component_behavior_claim_without_tool_proof():
    text = "The native module should work from Python side."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "The native module should work",
                "status": "verified",
                "evidence": "Command evidence #8 invoked exported function behavior.",
                "evidence_refs": [{"kind": "command_evidence", "id": 8}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 8,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "wget https://example.invalid/archive.tar.gz",
                "output_tail": "wget returned 0\n",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, action, session=session)

    assert "runtime component behavior evidence import-only" in blocker


def test_acceptance_finish_blocker_allows_runtime_component_import_only_task():
    text = "Ensure the native extension imports without errors."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Ensure the native extension imports without errors.",
                "status": "verified",
                "evidence": "Command evidence #4 imported the native extension successfully.",
                "evidence_refs": [{"kind": "command_evidence", "id": 4}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 4,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module'",
                "output_tail": "",
            }
        ]
    }

    assert acceptance_finish_blocker(text, action, session=session) == ""


def test_acceptance_finish_blocker_rejects_shared_library_load_only_proof():
    text = "The native module and shared library should work from the Python side."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "The native module and shared library should work",
                "status": "verified",
                "evidence": "Command evidence #3 loaded the native module and printed the shared library path.",
                "evidence_refs": [{"kind": "command_evidence", "id": 3}],
            }
        ],
    }
    session = {
        "command_evidence": [
            {
                "id": 3,
                "tool": "run_command",
                "terminal_success": True,
                "status": "completed",
                "exit_code": 0,
                "command": "python -c 'import native_module; print(native_module.__file__)'",
                "output_tail": "/usr/local/lib/native_module.so\n",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, action, session=session)

    assert "runtime component behavior evidence import-only" in blocker


def test_acceptance_done_gate_prechecks_runtime_component_before_evidence_ref_validation():
    text = "The loadable runtime component should work in its original runtime context."
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Behavior proof",
                "status": "verified",
                "evidence": "Checked the import path only.",
            }
        ],
    }

    decision = acceptance_done_gate_decision(text, action, session={"tool_calls": []})

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "runtime_component_behavior_evidence"
    assert decision["blockers"][1]["code"] == "acceptance_evidence_refs_missing"


def test_acceptance_finish_blocker_rejects_stateful_output_without_checks():
    text = "Connect the speech bubble copy to live current state."

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True})

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_accepts_stateful_output_contrast_evidence():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": (
                        "PASS positive injected state payload: adapter returned current state "
                        "status=busy and the speech message changed to Busy.\n"
                        "PASS negative fixture path: fixture output says local terminal and "
                        "does not claim live state."
                    ),
                },
            }
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_claim_without_tool_output():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": "PASS: asserted the live desk label appears in the speech bubble.",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_from_edit_summary():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "edit_file",
                "status": "completed",
                "summary": "positive injected state and negative fixture assertions were added",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_from_command_parameter_only():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "pytest -k 'positive injected state or negative fixture'"},
                "result": {"exit_code": 0, "stdout": "1 passed"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_does_not_escalate_plain_current_copy_replacement():
    text = "Replace the current copy from Start to Begin. Ensure the output text updates."
    checks = [
        {
            "constraint": "Replace the current copy from Start to Begin.",
            "status": "verified",
            "evidence": "tool #2 read the output text and found Begin.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the output text and found Begin.",
        }
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_does_not_escalate_literal_current_status_title_copy():
    text = 'Use "Current Status" as the title text in the UI. Ensure the output text updates.'
    checks = [
        {
            "constraint": 'Use "Current Status" as the title text in the UI.',
            "status": "verified",
            "evidence": "tool #2 read the title text and found Current Status.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the title text and found Current Status.",
        },
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_does_not_escalate_literal_state_title_copy():
    text = 'Use "State" as the title text in the UI. Ensure the output text updates.'
    checks = [
        {
            "constraint": 'Use "State" as the title text in the UI.',
            "status": "verified",
            "evidence": "tool #2 read the title text and found State.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the title text and found State.",
        },
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_rejects_stale_runtime_artifact_before_fresh_verifier():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "frame written by node vm.js",
            "status": "verified",
            "evidence": "Tool #7 verified /tmp/frame.bmp with bmp_header_ok=True.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "path=/tmp/frame.bmp\nframe_bytes=1024054\nbmp_header_ok=True\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime artifact freshness unchecked" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_rejects_discovered_stale_runtime_artifact_before_fresh_verifier():
    text = (
        "Implement a MIPS interpreter called vm.js so I can run `node vm.js`. "
        "Running this file should result in saving the frames as they are rendered."
    )
    checks = [
        {
            "constraint": "first frame was saved",
            "status": "verified",
            "evidence": "Tool #30 ran `rm -f /tmp/frame.bmp && node vm.js` and validated /tmp/frame.bmp.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 30,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp && node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "rm -f /tmp/frame.bmp && node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "frame bmp validation ok\n",
                    "stderr": "saved frame 1 to /tmp/frame.bmp after 30670791 instructions\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime artifact freshness unchecked" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_allows_stale_runtime_artifact_after_cleanup():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "frame written by node vm.js",
            "status": "verified",
            "evidence": "Tool #7 verified /tmp/frame.bmp and tool #8 removed the stale frame for the fresh verifier.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "path=/tmp/frame.bmp\nframe_bytes=1024054\nbmp_header_ok=True\n",
                },
            },
            {
                "id": 8,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "cleaned /tmp/frame.bmp\n"},
            },
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_acceptance_finish_blocker_rejects_runtime_command_pass_without_artifact_proof():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "node vm.js exits successfully",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js with exit_code=0.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0, "stdout": "Program exited cleanly\n"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime final verifier artifact evidence missing" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_accepts_runtime_artifact_command_evidence_ref():
    text = "A fresh VM run will write /tmp/frame.bmp during execution."
    checks = [
        {
            "constraint": "fresh VM run created /tmp/frame.bmp",
            "status": "verified",
            "evidence": "Command evidence #4 created /tmp/frame.bmp.",
            "evidence_refs": [{"kind": "command_evidence", "id": 4}],
        }
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 4,
                "ref": {"kind": "command_evidence", "id": 4},
                "source": "native_command",
                "tool": "run_command",
                "command": "node vm.js && test -s /tmp/frame.bmp",
                "cwd": ".",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "created /tmp/frame.bmp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert blocker == ""


def test_acceptance_finish_blocker_rejects_wrong_runtime_artifact_path():
    text = (
        "Implement a MIPS interpreter called vm.js so I can run `node vm.js`. "
        "Running this file should result in saving the frames as they are rendered."
    )
    checks = [
        {
            "constraint": "first rendered frame was saved",
            "status": "verified",
            "evidence": "Tool #22 saved frames/frame000001.bmp and tool #23 verified the root frame copy.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 22,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {
                    "command": "node vm.js",
                    "exit_code": 0,
                    "stdout": (
                        "DoomGeneric initialized. Frames will be saved to /tmp/frame.bmp\n"
                        "saved frames/frame000001.bmp\n"
                    ),
                },
            },
            {
                "id": 23,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "python3 inspect_frames.py"},
                "result": {
                    "command": "python3 inspect_frames.py",
                    "exit_code": 0,
                    "stdout": (
                        "path frames/frame000001.bmp exists True size 1024054\n"
                        "path frame000001.bmp exists True size 1024054\n"
                        "tmp_frame_before_cleanup False -1\n"
                    ),
                },
            },
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime final verifier artifact evidence missing" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_rejects_runtime_visual_artifact_format_only_evidence():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames to /tmp/frame.bmp. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 validated /tmp/frame.bmp as a valid/non-uniform BMP, "
                "and tool #20 removed the stale frame."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": (
                        "artifact validation passed: both outputs were identical "
                        "320x200x32 BMPs\npath=/tmp/frame.bmp\n"
                    ),
                    "stderr": "saved frame 1 to /tmp/frame.bmp\n",
                },
            },
            {
                "id": 20,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "removed /tmp/frame.bmp\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime visual artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_runtime_visual_artifact_loose_quality_aliases():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames to /tmp/frame.bmp. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 reported exact stdout, expected size, reference, and failed-l2 aliases for /tmp/frame.bmp."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 weak_frame_claims.py"},
                "result": {
                    "command": "node vm.js && python3 weak_frame_claims.py",
                    "exit_code": 0,
                    "stdout": (
                        "exact stdout I_InitGraphics\n"
                        "expected size 768054\n"
                        "reference file exists\n"
                        "similarity failed l2=999.0\n"
                        "saved /tmp/frame.bmp\n"
                    ),
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime visual artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_appropriate_visual_artifact_without_quality_evidence():
    text = (
        "I have provided /app/doomgeneric/, the source code to doom. "
        "I have provided vm.js that will expect a file called doomgeneric_mips and will run it. "
        "Please build the doomgeneric_mips ELF for me, so that I can run `node vm.js`. "
        "After running `node vm.js` I expect that stdout will be printed appropriately, "
        "and frames will be written to /tmp/frame.bmp."
    )
    checks = [
        {
            "constraint": "provided source tree is grounded",
            "status": "verified",
            "evidence": "Tool #23 listed /app/doomgeneric/ and confirmed doomgeneric_img.c exists.",
        },
        {
            "constraint": "node vm.js writes a frame",
            "status": "verified",
            "evidence": (
                "Tool #24 removed /tmp/frame.bmp, ran node vm.js, and proved a valid BMP was created /tmp/frame.bmp; "
                "tool #25 removed the stale frame."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 23,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "find /app/doomgeneric -maxdepth 2 -type f | head"},
                "result": {
                    "command": "find /app/doomgeneric -maxdepth 2 -type f | head",
                    "exit_code": 0,
                    "stdout": "/app/doomgeneric/doomgeneric/doomgeneric_img.c\n",
                },
            },
            {
                "id": 24,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp && node vm.js && python3 inspect_frame.py"},
                "result": {
                    "command": "rm -f /tmp/frame.bmp && node vm.js && python3 inspect_frame.py",
                    "exit_code": 0,
                    "stdout": (
                        "doomgeneric_mips: drawing one frame to /tmp/frame.bmp\n"
                        "created /tmp/frame.bmp by node vm.js: BMP bytes 70 header 424d\n"
                    ),
                },
            },
            {
                "id": 25,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "removed /tmp/frame.bmp\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime visual artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_runtime_visual_artifact_quality_evidence():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames to /tmp/frame.bmp. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 confirmed exact stdout I_InitGraphics, expected dimensions 640x400, "
                "and reference similarity for /tmp/frame.bmp; tool #20 removed the stale frame."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": (
                        "I_InitGraphics: DOOM screen size: w x h: 320 x 200\n"
                        "framebuffer expected dimensions 640x400\n"
                        "reference similarity passed l2=0.01\n"
                        "saved /tmp/frame.bmp\n"
                    ),
                },
            },
            {
                "id": 20,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "removed /tmp/frame.bmp\n"},
            },
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_acceptance_finish_blocker_does_not_promote_verifier_scratch_transcript_to_runtime_artifact():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 confirmed exact stdout I_InitGraphics, expected dimensions 640x400, "
                "reference similarity, and saved frame000000.bmp."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "rm -f /tmp/vmout.txt frame000000.bmp; node vm.js | tee /tmp/vmout.txt"
                },
                "result": {
                    "command": "rm -f /tmp/vmout.txt frame000000.bmp; node vm.js | tee /tmp/vmout.txt",
                    "exit_code": 0,
                    "stdout": (
                        "I_InitGraphics: framebuffer: x_res: 640, y_res: 400\n"
                        "saved frame000000.bmp\n"
                        "FRAME_QUALITY_OK 640x400 reference similarity passed\n"
                        "grep saved frame000000.bmp /tmp/vmout.txt succeeded\n"
                    ),
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert blocker == ""


def test_runtime_visual_artifact_task_classifier_requires_quality_language():
    assert is_runtime_visual_artifact_task(
        "Run node vm.js; it should save rendered frames and I will check the first frame is correct."
    )
    assert not is_runtime_visual_artifact_task(
        "Run node vm.js; it will write /tmp/frame.bmp during the fresh VM run."
    )


def test_implementation_contract_source_requirements_extract_provided_source_refs():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement vm.js so I can run `node vm.js`."
    )

    requirements = implementation_contract_source_requirements(text)

    assert [item["path"] for item in requirements] == ["/app/doomgeneric_mips", "doomgeneric/"]


def test_acceptance_finish_blocker_rejects_hard_task_without_provided_source_evidence():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement a MIPS interpreter called vm.js "
        "so that I can run `node vm.js`."
    )
    checks = [
        {
            "constraint": "node vm.js runs",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js and produced a frame.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 1,
                "tool": "write_file",
                "status": "completed",
                "parameters": {"path": "vm.js", "content": "console.log('DoomGeneric initialized')"},
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0, "stdout": "DoomGeneric initialized\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "implementation contract source evidence ungrounded" in blocker
    assert "/app/doomgeneric_mips" in blocker


def test_acceptance_finish_blocker_accepts_hard_task_with_provided_source_evidence():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement a MIPS interpreter called vm.js "
        "so that I can run `node vm.js`."
    )
    checks = [
        {
            "constraint": "provided binary inspected",
            "status": "verified",
            "evidence": "Tool #1 inspected /app/doomgeneric_mips.",
        },
        {
            "constraint": "provided source inspected",
            "status": "verified",
            "evidence": "Tool #2 listed doomgeneric/ source files.",
        },
        {
            "constraint": "node vm.js runs",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 1,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "file /app/doomgeneric_mips"},
                "result": {"command": "file /app/doomgeneric_mips", "exit_code": 0},
            },
            {
                "id": 2,
                "tool": "glob",
                "status": "completed",
                "parameters": {"pattern": "doomgeneric/**"},
                "result": {"text": "doomgeneric/doomgeneric_img.c\ndoomgeneric/i_system.c"},
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0},
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_edit_scope_write_history_after_write():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )
    checks = [
        {"constraint": "Ensure the output file exists.", "status": "verified", "evidence": "tool #3 passed"},
        {
            "constraint": "The only edits you may make are specified replacements.",
            "status": "verified",
            "evidence": "Applied edit_file tool #2 with replacements from earlier read history.",
        },
        {
            "constraint": "Do not edit config.json.",
            "status": "verified",
            "evidence": "Write history shows no write action for config.json.",
        },
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "edit-scope acceptance evidence ungrounded" in blocker


def test_acceptance_finish_blocker_requires_explicit_edit_scope_check_after_write():
    text = "Ensure output exists. The only edits you may make are specified replacements."
    checks = [
        {"constraint": "Ensure output exists.", "status": "verified", "evidence": "tool #3 passed"},
        {"constraint": "Task complete.", "status": "verified", "evidence": "tool #4 passed"},
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
            {"id": 4, "tool": "run_command", "status": "completed"},
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "edit-scope acceptance evidence missing" in blocker


def test_acceptance_finish_blocker_accepts_post_write_edit_scope_validator():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )
    checks = [
        {"constraint": "Ensure the output file exists.", "status": "verified", "evidence": "tool #3 passed"},
        {
            "constraint": "The only edits you may make are specified replacements.",
            "status": "verified",
            "evidence": "Tool #4 run_command compared the final file against the allowed replacements and printed OK.",
        },
        {
            "constraint": "Do not edit config.json.",
            "status": "verified",
            "evidence": "Tool #4 run_command confirmed config.json was unchanged.",
        },
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
            {"id": 4, "tool": "run_command", "status": "completed"},
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_numeric_single_fit_residual_only():
    text = (
        "Fit the G and 2D Peak of the spectrum and return the x0, gamma, "
        "amplitude and offset of the peaks."
    )
    checks = [
        {
            "constraint": "Verify numeric plausibility against the input data.",
            "status": "verified",
            "evidence": "Tool #4 residual checks and finite parameter assertions passed.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "rmse=0.05 rel_rmse=0.02 finite parameters"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "numeric artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_numeric_independent_cross_check():
    text = (
        "Fit the G and 2D Peak of the spectrum and return the x0, gamma, "
        "amplitude and offset of the peaks."
    )
    checks = [
        {
            "constraint": "Verify numeric plausibility against the input data.",
            "status": "verified",
            "evidence": "Tool #4 independent cross-check recomputed fit stability with an alternative method.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "independent cross-check: alternative grid fit compared against "
                        "nonlinear fit; residual rmse and parameter stability within bounds"
                    )
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_ignores_blocked_numeric_checks():
    text = "Compute metrics from the dataset and write output.json."
    checks = [
        {
            "constraint": "Verify numeric metric quality against the input data.",
            "status": "blocked",
            "evidence": "Tool #4 independent cross-check recomputed metrics with an alternative method.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "independent cross-check: alternative computation compared metrics; "
                        "residual error within bounds"
                    )
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "numeric artifact quality evidence missing" in blocker


def test_numeric_artifact_task_classifier_covers_rank_and_metrics_without_ui_false_positive():
    assert is_numeric_artifact_task("Rank rows by numeric score.")
    assert is_numeric_artifact_task("Compute metrics from the dataset.")
    assert not is_numeric_artifact_task("Fix offset pagination regression where the text does not fit.")
    assert not is_numeric_artifact_task("Update metrics reporting docs.")
    assert not is_numeric_artifact_task("Keep the prompt cache boundary empty without draft metrics.")


def test_model_inference_output_task_classifier_covers_checkpoint_sampling():
    text = (
        "I have downloaded model weights stored as a TF .ckpt. Write a dependency-free "
        "C file that samples from the model with arg-max sampling and continues the "
        "output for the next 20 tokens using vocab.bpe."
    )

    assert is_model_inference_output_task(text)
    assert is_model_inference_output_task(
        "Run inference from checkpoint weights and print the generated token continuation."
    )
    assert is_model_inference_output_task("Load a GPT model from model.bin and sample the next token.")
    assert is_model_inference_output_task(
        "Given a model checkpoint, perform greedy decoding and print the next tokens."
    )
    assert not is_model_inference_output_task("Count dataset tokens from a CSV file.")
    assert not is_model_inference_output_task("Update docs about model selection.")
    assert not is_model_inference_output_task("Read token weights from weights.csv and generate output.json.")


def test_long_dependency_toolchain_build_classifier_extracts_final_artifact():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp. "
        "Keep the dependency/toolchain branch coherent and prove it is executable/invokable."
    )

    assert is_long_dependency_toolchain_build_task(text)
    assert long_dependency_final_artifacts(text) == ["/tmp/CompCert/ccomp"]
    assert not is_long_dependency_toolchain_build_task("Update docs about compiler options.")


def test_acceptance_finish_blocker_rejects_long_dependency_partial_build_progress():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert build prerequisites and dependency generation completed.",
            "status": "verified",
            "evidence": "Tool #7 installed opam Coq 8.16.1 and ran make depend.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "coqc 8.16.1\nmake depend completed\nmake ccomp timed out\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker
    assert "/tmp/CompCert/ccomp" in blocker


def test_acceptance_finish_blocker_accepts_long_dependency_final_artifact_evidence():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Tool #9 built from source and ran /tmp/CompCert/ccomp -version; SMOKE_OK.",
        },
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Tool #9: ls -l /tmp/CompCert/ccomp; /tmp/CompCert/ccomp -version; SMOKE_OK.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "ls -l /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version"},
                "result": {
                    "exit_code": 0,
                    "stdout": "-rwxr-xr-x /tmp/CompCert/ccomp\nCompCert version 3.13\nSMOKE_OK\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_accepts_long_dependency_artifact_proof_in_command_with_clean_stdout():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Tool #9 completed the build and ran /tmp/CompCert/ccomp -version successfully.",
        },
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Tool #9 ran /tmp/CompCert/ccomp -version successfully.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version"},
                "result": {
                    "exit_code": 0,
                    "stdout": "CompCert C compiler, version 3.13.1\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_accepts_long_dependency_artifact_section_label_before_real_probe():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact and smoke.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "printf '== required artifact /tmp/CompCert/ccomp ==\\n'\n"
                    "test -x /tmp/CompCert/ccomp\n"
                    "ls -l /tmp/CompCert/ccomp\n"
                    "/tmp/CompCert/ccomp -version\n"
                ),
                "cwd": "/app",
                "status": "completed",
                "start_order": 1,
                "finish_order": 2,
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": (
                    "== required artifact /tmp/CompCert/ccomp ==\n"
                    "-rwxr-xr-x 1 root root 10836768 /tmp/CompCert/ccomp\n"
                    "The CompCert C verified compiler, version 3.13\n"
                ),
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_accepts_long_dependency_unrelated_missing_warning_after_artifact_probe():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact and default-link smoke.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e\n"
                    "test -x /tmp/CompCert/ccomp\n"
                    "ls -l /tmp/CompCert/ccomp\n"
                    "/tmp/CompCert/ccomp -o /tmp/smoke /tmp/smoke.c\n"
                ),
                "cwd": "/app",
                "status": "completed",
                "start_order": 1,
                "finish_order": 2,
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": (
                    "-rwxr-xr-x 1 root root 10836768 /tmp/CompCert/ccomp\n"
                    "smoke-ok\n"
                ),
                "stderr_tail": (
                    "/usr/bin/ld: warning: /tmp/compcert000283.o: "
                    "missing .note.GNU-stack section implies executable stack\n"
                ),
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_rejects_masked_probe_plus_echoed_reverse_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": "test -x /tmp/CompCert/ccomp || true; printf '/tmp/CompCert/ccomp exists=true\\n'",
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_masked_probe_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "test -x /tmp/CompCert/ccomp || true; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_semicolon_masked_probe_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "test -x /tmp/CompCert/ccomp; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_probe_before_late_errexit_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "test -x /tmp/CompCert/ccomp; "
                    "set -e; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_probe_after_errexit_disabled_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e; "
                    "set +e; "
                    "test -x /tmp/CompCert/ccomp; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_quoted_probe_before_errexit_disabled_spoof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e; "
                    "printf 'test -x /tmp/CompCert/ccomp\\n'; "
                    "set +e; "
                    "test -x /tmp/CompCert/ccomp; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": (
                    "test -x /tmp/CompCert/ccomp\n"
                    "/tmp/CompCert/ccomp exists=true\n"
                ),
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_and_skipped_probe_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e; "
                    "false && test -x /tmp/CompCert/ccomp; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_and_chain_skipped_probe_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e; "
                    "false && test -x /tmp/CompCert/ccomp && true; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_and_lhs_probe_failure_plus_variable_echoed_exists_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Command evidence #12 proved /tmp/CompCert/ccomp exists and is invokable.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Command evidence #12 proved final artifact.",
            "evidence_refs": [{"kind": "command_evidence", "id": 12}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 12,
                "ref": {"kind": "command_evidence", "id": 12},
                "source": "native_command",
                "tool": "run_command",
                "command": (
                    "set -e; "
                    "test -x /tmp/CompCert/ccomp && true; "
                    "p=/tmp/CompCert/ccomp; "
                    "printf '%s exists=true\\n' \"$p\""
                ),
                "cwd": "/app",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "/tmp/CompCert/ccomp exists=true\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_timed_out_long_dependency_artifact_probe():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Tool #9 ran test -x /tmp/CompCert/ccomp and /tmp/CompCert/ccomp -version.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version"},
                "result": {
                    "exit_code": 0,
                    "timed_out": True,
                    "stdout": "command timed out before final artifact proof\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_long_dependency_structured_evidence_ref_only():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Final artifact proof completed.",
            "evidence_refs": [{"kind": "tool_call", "id": 9}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Final artifact proof completed.",
            "evidence_refs": [{"kind": "tool_call", "id": 9}],
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version"},
                "result": {
                    "exit_code": 0,
                    "stdout": "CompCert C compiler, version 3.13.1\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_accepts_long_dependency_command_evidence_ref_only():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Final artifact proof completed.",
            "evidence_refs": [{"kind": "command_evidence", "id": 9}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": "Final artifact proof completed.",
            "evidence_refs": [{"kind": "command_evidence", "id": 9}],
        },
    ]
    session = {
        "command_evidence": [
            {
                "schema_version": 1,
                "id": 9,
                "ref": {"kind": "command_evidence", "id": 9},
                "source": "native_command",
                "tool": "run_command",
                "command": "test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version",
                "cwd": "/tmp/CompCert",
                "status": "completed",
                "start_order": 1,
                "finish_order": 2,
                "exit_code": 0,
                "timed_out": False,
                "terminal_success": True,
                "stdout_tail": "CompCert C compiler, version 3.13.1\n",
                "stderr_tail": "",
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""


def test_acceptance_finish_blocker_preserves_structured_evidence_ref_before_long_evidence_clip():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    long_text = " ".join(f"detail{i}" for i in range(80))
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": long_text,
            "evidence_refs": [{"kind": "tool_call", "id": 9}],
        },
        {
            "constraint": "Build the CompCert C verified compiler from source.",
            "status": "verified",
            "evidence": long_text,
            "evidence_refs": [{"kind": "tool_call", "id": 9}],
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version"},
                "result": {"exit_code": 0, "stdout": "CompCert C compiler, version 3.13.1\n"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert blocker == ""
    coerced = coerce_acceptance_checks(checks)
    assert "tool #9" in coerced[0]["evidence"]


def test_acceptance_done_gate_blocks_invalid_evidence_ref():
    text = "Ensure output exists."
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "test -s output.txt"},
                "result": {"exit_code": 1, "stdout": "missing output.txt\n"},
            }
        ]
    }
    action = {
        "type": "finish",
        "task_done": True,
        "acceptance_checks": [
            {
                "constraint": "Ensure output exists.",
                "status": "verified",
                "evidence": "Tool #4 checked output.txt.",
                "evidence_refs": [{"kind": "tool_call", "id": 4}],
            }
        ],
    }

    decision = acceptance_done_gate_decision(text, action, session=session)

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "acceptance_evidence_refs_invalid"
    assert "tool_call#4 not terminal-success" in decision["reason"]
    assert decision["invalid_evidence_refs"] == [
        {
            "kind": "tool_call",
            "id": 4,
            "reason": "not_terminal_success",
            "status": "completed",
            "exit_code": 1,
            "timed_out": False,
        }
    ]
    assert "deterministic done gate" in decision["continuation_prompt"]


def test_acceptance_done_gate_blocks_missing_evidence_ref_for_verified_check():
    decision = acceptance_done_gate_decision(
        "Ensure output exists.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Ensure output exists.",
                    "status": "verified",
                    "evidence": "Checked the file.",
                }
            ],
        },
        session={"tool_calls": []},
    )

    assert decision["decision"] == "block_continue"
    assert decision["blockers"][0]["code"] == "acceptance_evidence_refs_missing"


def test_acceptance_done_gate_allows_structured_terminal_evidence_ref():
    decision = acceptance_done_gate_decision(
        "Ensure output exists.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Ensure output exists.",
                    "status": "verified",
                    "evidence": "Tool checked output.txt.",
                    "evidence_refs": [{"kind": "tool_call", "id": 4}],
                }
            ],
        },
        session={
            "tool_calls": [
                {
                    "id": 4,
                    "tool": "run_command",
                    "status": "completed",
                    "parameters": {"command": "test -s output.txt"},
                    "result": {"exit_code": 0, "stdout": "ok\n"},
                }
            ]
        },
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_done_gate_allows_structured_command_evidence_ref():
    decision = acceptance_done_gate_decision(
        "Ensure output exists.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Ensure output exists.",
                    "status": "verified",
                    "evidence": "Command evidence checked output.txt.",
                    "evidence_refs": [{"kind": "command_evidence", "id": 4}],
                }
            ],
        },
        session={
            "command_evidence": [
                {
                    "schema_version": 1,
                    "id": 4,
                    "ref": {"kind": "command_evidence", "id": 4},
                    "source": "native_command",
                    "tool": "run_command",
                    "command": "test -s output.txt",
                    "cwd": ".",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "terminal_success": True,
                    "stdout_tail": "ok\n",
                    "stderr_tail": "",
                }
            ]
        },
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_done_gate_allows_external_ground_truth_command_evidence_ref():
    decision = acceptance_done_gate_decision(
        "Use the ground truth command `validator --threshold 50 --format json` to verify output.txt.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Run validator ground truth command.",
                    "status": "verified",
                    "evidence": "Command evidence #1 ran validator with the required flags.",
                    "evidence_refs": [{"kind": "command_evidence", "id": 1}],
                }
            ],
        },
        session={
            "command_evidence": [
                {
                    "schema_version": 1,
                    "id": 1,
                    "ref": {"kind": "command_evidence", "id": 1},
                    "source": "native_command",
                    "tool": "run_command",
                    "command": "validator --threshold 50 --format json output.txt",
                    "cwd": ".",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "terminal_success": True,
                    "stdout_tail": "validator ok\n",
                    "stderr_tail": "",
                }
            ]
        },
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_done_gate_allows_exact_command_example_command_evidence_ref():
    decision = acceptance_done_gate_decision(
        "After writing output.txt, the user can run `validator --strict output.txt` from the task cwd.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Advertised validator command works.",
                    "status": "verified",
                    "evidence": "Command evidence #2 ran the exact advertised command.",
                    "evidence_refs": [{"kind": "command_evidence", "id": 2}],
                }
            ],
        },
        session={
            "command_evidence": [
                {
                    "schema_version": 1,
                    "id": 2,
                    "ref": {"kind": "command_evidence", "id": 2},
                    "source": "native_command",
                    "tool": "run_command",
                    "command": "validator --strict output.txt",
                    "cwd": ".",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "terminal_success": True,
                    "stdout_tail": "ok\n",
                    "stderr_tail": "",
                }
            ]
        },
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_done_gate_blocks_non_terminal_command_evidence_ref():
    decision = acceptance_done_gate_decision(
        "Ensure output exists.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Ensure output exists.",
                    "status": "verified",
                    "evidence": "Command evidence checked output.txt.",
                    "evidence_refs": [{"kind": "command_evidence", "id": 4}],
                }
            ],
        },
        session={
            "command_evidence": [
                {
                    "schema_version": 1,
                    "id": 4,
                    "ref": {"kind": "command_evidence", "id": 4},
                    "source": "native_command",
                    "tool": "run_command",
                    "command": "test -s output.txt",
                    "cwd": ".",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "terminal_success": False,
                    "stdout_tail": "ok\n",
                    "stderr_tail": "",
                }
            ]
        },
    )

    assert decision["decision"] == "block_continue"
    assert decision["invalid_evidence_refs"] == [
        {
            "kind": "command_evidence",
            "id": 4,
            "reason": "not_terminal_success",
            "status": "completed",
            "exit_code": 0,
            "timed_out": False,
        }
    ]


def test_acceptance_done_gate_allows_extra_failed_refs_when_success_ref_present():
    decision = acceptance_done_gate_decision(
        "Ensure output exists.",
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Ensure output exists.",
                    "status": "verified",
                    "evidence": "Tool #4 tried an earlier probe; tool #5 checked output.txt.",
                    "evidence_refs": [{"kind": "tool_call", "id": 4}, {"kind": "tool_call", "id": 5}],
                }
            ],
        },
        session={
            "tool_calls": [
                {
                    "id": 4,
                    "tool": "run_command",
                    "status": "completed",
                    "parameters": {"command": "test -s output.txt"},
                    "result": {"exit_code": 1, "stdout": "missing output.txt\n"},
                },
                {
                    "id": 5,
                    "tool": "run_command",
                    "status": "completed",
                    "parameters": {"command": "test -s output.txt"},
                    "result": {"exit_code": 0, "stdout": "ok\n"},
                },
            ]
        },
    )

    assert decision["decision"] == "allow_complete"


def test_acceptance_done_gate_blocks_missing_or_unsupported_refs_even_with_success_ref():
    for extra_ref in ({"kind": "tool_call", "id": 999}, {"kind": "file", "id": 5}):
        decision = acceptance_done_gate_decision(
            "Ensure output exists.",
            {
                "type": "finish",
                "task_done": True,
                "acceptance_checks": [
                    {
                        "constraint": "Ensure output exists.",
                        "status": "verified",
                        "evidence": "Tool #5 checked output.txt.",
                        "evidence_refs": [{"kind": "tool_call", "id": 5}, extra_ref],
                    }
                ],
            },
            session={
                "tool_calls": [
                    {
                        "id": 5,
                        "tool": "run_command",
                        "status": "completed",
                        "parameters": {"command": "test -s output.txt"},
                        "result": {"exit_code": 0, "stdout": "ok\n"},
                    },
                ]
            },
        )

        assert decision["decision"] == "block_continue"
        assert decision["blockers"][0]["code"] == "acceptance_evidence_refs_invalid"


def test_acceptance_done_gate_allows_multiline_long_dependency_final_proof_with_extra_failed_refs():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp. "
        "CompCert must be freshly built from source and fully functional."
    )
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "make ccomp"},
                "result": {"exit_code": 2, "stdout": "partial build failed\n"},
            },
            {
                "id": 12,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "set -euxo pipefail\n"
                        "make runtime/libcompcert.a\n"
                        "make install\n"
                        "/tmp/CompCert/ccomp /tmp/compcert_smoke.c -o /tmp/compcert_smoke | tee /tmp/log\n"
                        "ls -l /tmp/CompCert/ccomp\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": (
                        "Functional default compile/link smoke after runtime install:\n"
                        "smoke:120\n"
                        "Final artifact proof:\n"
                        "ls -l /tmp/CompCert/ccomp\n"
                        "-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n"
                    ),
                },
            },
        ]
    }

    decision = acceptance_done_gate_decision(
        text,
        {
            "type": "finish",
            "task_done": True,
            "acceptance_checks": [
                {
                    "constraint": "Build the CompCert C verified compiler from source.",
                    "status": "verified",
                    "evidence": "Tool #4 was an earlier failure; tool #12 completed final artifact proof.",
                    "evidence_refs": [{"kind": "tool_call", "id": 4}, {"kind": "tool_call", "id": 12}],
                },
                {
                    "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
                    "status": "verified",
                    "evidence": "Tool #12 proved /tmp/CompCert/ccomp is executable.",
                    "evidence_refs": [{"kind": "tool_call", "id": 12}],
                },
                {
                    "constraint": "CompCert must be freshly built from source and fully functional.",
                    "status": "verified",
                    "evidence": "Tool #12 ran a default compile/link smoke and produced smoke:120.",
                    "evidence_refs": [{"kind": "tool_call", "id": 12}],
                },
            ],
        },
        session=session,
    )

    assert decision["decision"] == "allow_complete"


def test_long_dependency_final_artifact_proof_is_generic_not_task_semantic():
    assert long_dependency_artifact_proven_by_call(
        {
            "tool": "run_command",
            "status": "completed",
            "parameters": {"command": "make install\nls -l /opt/widget/bin/widget"},
            "result": {
                "exit_code": 0,
                "stdout": "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\n",
            },
        },
        "/opt/widget/bin/widget",
    )
    assert long_dependency_artifact_proven_by_call(
        {
            "tool": "run_command",
            "status": "completed",
            "parameters": {"command": "make install\nfile /opt/widget/bin/widget"},
            "result": {
                "exit_code": 0,
                "stdout": "/opt/widget/bin/widget: ELF 64-bit LSB executable\n",
            },
        },
        "/opt/widget/bin/widget",
    )


def test_long_dependency_final_artifact_proof_rejects_suppressed_probe_plus_faked_output():
    assert not long_dependency_artifact_proven_by_call(
        {
            "tool": "run_command",
            "status": "completed",
            "parameters": {
                "command": (
                    "ls -l /opt/widget/bin/widget >/dev/null; "
                    "printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\\n'"
                )
            },
            "result": {
                "exit_code": 0,
                "stdout": "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\n",
            },
        },
        "/opt/widget/bin/widget",
    )


def test_long_dependency_final_artifact_proof_rejects_relative_basename_echo_spoof():
    for command, stdout in (
        ("printf 'exists=true widget\\n'", "exists=true widget\n"),
        ("echo 'regular file widget'", "regular file widget\n"),
        ("printf 'exists=true ./widget\\n'", "exists=true ./widget\n"),
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"cwd": "/opt/widget/bin", "command": command},
                "result": {"cwd": "/opt/widget/bin", "exit_code": 0, "stdout": stdout},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_generated_marker_output_without_real_probe():
    for command, stdout in (
        (
            "awk 'BEGIN{print \"exists=true /opt/widget/bin/widget\"}'",
            "exists=true /opt/widget/bin/widget\n",
        ),
        (
            "python -c 'print(\"exists=true widget\")'",
            "exists=true widget\n",
        ),
        (
            "sh -c 'printf \"regular file ./widget\\n\"'",
            "regular file ./widget\n",
        ),
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"cwd": "/opt/widget/bin", "command": command},
                "result": {"cwd": "/opt/widget/bin", "exit_code": 0, "stdout": stdout},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_parent_glob_mutation_after_probe():
    for command, cwd in (
        ("ls -l /opt/widget/bin/widget && rm /opt/widget/bin/*", None),
        ("ls -l /opt/widget/bin/widget && truncate -s 0 /opt/widget/bin/*", None),
        ("ls -l widget && rm *", "/opt/widget/bin"),
    ):
        parameters = {"command": command}
        result = {
            "exit_code": 0,
            "stdout": "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\n",
        }
        if cwd:
            parameters["cwd"] = cwd
            result["cwd"] = cwd
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": parameters,
                "result": result,
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_nested_interpreter_mutation_after_probe():
    for command in (
        "ls -l /opt/widget/bin/widget && sh -c 'rm /opt/widget/bin/widget'",
        "ls -l /opt/widget/bin/widget && python -c 'import os; os.remove(\"/opt/widget/bin/widget\")'",
        "ls -l /opt/widget/bin/widget && perl -e 'unlink \"/opt/widget/bin/widget\"'",
        "ls -l /opt/widget/bin/widget && sh -c 'rm /opt/widget/bin/*'",
        (
            "ls -l /opt/widget/bin/widget && "
            "python -c 'from pathlib import Path; Path(\"/opt/widget/bin/widget\").unlink()'"
        ),
        "ls -l /opt/widget/bin/widget && python -c 'import os; os.rename(\"/opt/widget/bin/widget\", \"/tmp/widget\")'",
        "ls -l /opt/widget/bin/widget && python -c 'open(\"/opt/widget/bin/widget\", \"w\").close()'",
        "ls -l /opt/widget/bin/widget && uv run python -c 'open(\"/opt/widget/bin/widget\", \"w\").close()'",
        "ls -l /opt/widget/bin/widget && sudo python -c 'open(\"/opt/widget/bin/widget\", \"w\").close()'",
        "ls -l /opt/widget/bin/widget && python3.12 -c 'open(\"/opt/widget/bin/widget\", \"w\").close()'",
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": command},
                "result": {
                    "exit_code": 0,
                    "stdout": "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\n",
                },
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_path_prefix_match():
    for command, stdout in (
        (
            "ls -l /opt/widget/bin/widget.old",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget.old\n",
        ),
        (
            "file /opt/widget/bin/widget.old",
            "/opt/widget/bin/widget.old: ELF 64-bit LSB executable\n",
        ),
        (
            "stat -c '%F %n' /opt/widget/bin/widget.old",
            "regular file /opt/widget/bin/widget.old\n",
        ),
        (
            "test -x /opt/widget/bin/widget.old",
            "exists=true /opt/widget/bin/widget.old\n",
        ),
        (
            "mv /opt/widget/bin/widget /opt/widget/bin/widget.old && file /opt/widget/bin/widget.old",
            "/opt/widget/bin/widget.old: ELF 64-bit LSB executable\n",
        ),
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": command},
                "result": {"exit_code": 0, "stdout": stdout},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_unrelated_absolute_basename_match():
    for command, stdout in (
        ("file /tmp/widget", "/tmp/widget: ELF 64-bit LSB executable\n"),
        ("stat -c '%F %n' /tmp/widget", "regular file /tmp/widget\n"),
        ("test -x /tmp/widget", "exists=true /tmp/widget\n"),
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"cwd": "/opt/widget/bin", "command": command},
                "result": {"cwd": "/opt/widget/bin", "exit_code": 0, "stdout": stdout},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_allows_relative_basename_from_artifact_cwd():
    for command, stdout in (
        ("file ./widget", "./widget: ELF 64-bit LSB executable\n"),
        ("stat -c '%F %n' widget", "regular file widget\n"),
        ("test -x widget", ""),
        ("[ -x ./widget ]", ""),
    ):
        assert long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"cwd": "/opt/widget/bin", "command": command},
                "result": {"cwd": "/opt/widget/bin", "exit_code": 0, "stdout": stdout},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_rejects_test_x_extra_operands():
    for command in (
        "test -x /opt/widget/bin/widget -o 1 = 1",
        "test -x widget -o 1 = 1",
        "[ -x widget -o 1 = 1 ]",
    ):
        assert not long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"cwd": "/opt/widget/bin", "command": command},
                "result": {"cwd": "/opt/widget/bin", "exit_code": 0, "stdout": ""},
            },
            "/opt/widget/bin/widget",
        )


def test_long_dependency_final_artifact_proof_allows_mutation_before_final_probe():
    for command in (
        "install build/widget /opt/widget/bin/widget && ls -l /opt/widget/bin/widget",
        "cp build/widget /opt/widget/bin/widget && stat -c '%F %n' /opt/widget/bin/widget",
        "chmod +x /opt/widget/bin/widget && file /opt/widget/bin/widget",
    ):
        assert long_dependency_artifact_proven_by_call(
            {
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": command},
                "result": {
                    "exit_code": 0,
                    "stdout": "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /opt/widget/bin/widget\n",
                },
            },
            "/opt/widget/bin/widget",
        )


def test_acceptance_finish_blocker_rejects_header_only_or_masked_long_dependency_output_proof():
    text = (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )
    checks = [
        {
            "constraint": "CompCert can be invoked through /tmp/CompCert/ccomp.",
            "status": "verified",
            "evidence": "Tool #9 completed final artifact proof for /tmp/CompCert/ccomp.",
            "evidence_refs": [{"kind": "tool_call", "id": 9}],
        }
    ]
    cases = [
        (
            "set -x; test -x /tmp/CompCert/ccomp || true; echo 'functional smoke'",
            "+ test -x /tmp/CompCert/ccomp\nfunctional smoke\n",
        ),
        (
            "printf 'Final artifact proof:\\nls -l /tmp/CompCert/ccomp\\n'",
            "Final artifact proof:\nls -l /tmp/CompCert/ccomp\n",
        ),
        (
            "printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\\n'",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\\n' && true",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "true && printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\\n'",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 /tmp/'\"CompCert\"'/ccomp\\n'",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "p=/tmp/CompCert/ccomp; printf 'Final artifact proof:\\n-rwxr-xr-x 1 root root 123 %s\\n' \"$p\"",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && rm -f /tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "stat -c '%F %n' /tmp/CompCert/ccomp && mv /tmp/CompCert/ccomp /tmp/CompCert/ccomp.old",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && chmod -x /tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && : > /tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && cp /tmp/other /tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && install /tmp/other /tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
        (
            "ls -l /tmp/CompCert/ccomp && dd if=/tmp/other of=/tmp/CompCert/ccomp",
            "Final artifact proof:\n-rwxr-xr-x 1 root root 123 /tmp/CompCert/ccomp\n",
        ),
    ]

    for command, stdout in cases:
        blocker = acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session={
                "tool_calls": [
                    {
                        "id": 9,
                        "tool": "run_command",
                        "status": "completed",
                        "parameters": {"command": command},
                        "result": {"exit_code": 0, "stdout": stdout},
                    }
                ]
            },
        )

        assert "long dependency/toolchain final artifact evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_smoke_only_output():
    text = (
        "I have downloaded the gpt-2 weights stored as a TF .ckpt. Write me a dependency-free C file "
        "that samples from the model with arg-max sampling. Call your program /app/gpt2.c, I will "
        "compile with gcc -O3 -lm. It should read the .ckpt and the .bpe file. Your c program must "
        "be <5000 bytes. I will run it /app/a.out gpt2-124M.ckpt vocab.bpe \"[input string here]\" "
        "and you should continue the output under whatever GPT-2 would print for the next 20 tokens."
    )
    checks = [
        {
            "constraint": "Call your program /app/gpt2.c, I will compile with gcc -O3 -lm.",
            "status": "verified",
            "evidence": "Tool #4 compiled with gcc successfully.",
        },
        {
            "constraint": "It should read the .ckpt and the .bpe file.",
            "status": "verified",
            "evidence": "Tool #4 ran with gpt2-124M.ckpt and vocab.bpe.",
        },
        {
            "constraint": "Your c program must be <5000 bytes.",
            "status": "verified",
            "evidence": "Tool #4: 2821 gpt2.c.",
        },
        {
            "constraint": "Continue output under whatever GPT-2 would print for the next 20 tokens.",
            "status": "verified",
            "evidence": "Tool #4 exited 0 and printed 20 generated tokens.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "compiled ok\n2821 gpt2.c\nprogram output: prompt Damien Damien Damien\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference output quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_model_inference_reference_output_evidence():
    text = (
        "I have downloaded model weights stored as a TF .ckpt. Write a compact C sampler "
        "that uses vocab.bpe and continues the output for the next 20 tokens."
    )
    checks = [
        {
            "constraint": "The C sampler compiles and reads the checkpoint plus vocab.bpe.",
            "status": "verified",
            "evidence": "Tool #5 compile/read checks passed.",
        },
        {
            "constraint": "Continue the output under the model's argmax tokens.",
            "status": "verified",
            "evidence": "Tool #5 python reference top-1 token ids match for 20/20 generated tokens.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "python reference implementation top-1 token ids match 20/20; expected continuation passed\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_model_inference_candidate_reference_flag_when_independent():
    text = (
        "I have downloaded model weights stored as a TF .ckpt. Write a compact C sampler "
        "that uses vocab.bpe and continues the output for the next 20 tokens."
    )
    checks = [
        {
            "constraint": "Continue the output under the model's argmax tokens.",
            "status": "verified",
            "evidence": "Tool #5 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "python3 /tests/reference_check.py /app/a.out"},
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_model_inference_candidate_derived_reference():
    text = (
        "I have downloaded model weights stored as a TF .ckpt. Write a compact C sampler "
        "that uses vocab.bpe and continues the output for the next 20 tokens."
    )
    checks = [
        {
            "constraint": "Continue the output under the model's argmax tokens.",
            "status": "verified",
            "evidence": "Tool #16 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 16,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 - <<'PY'\n"
                        "s=open('sampler.c').read()\n"
                        "open('/tmp/sampler_ref.c','w').write(s[:100] + s[100:])\n"
                        "PY\n"
                        "gcc /tmp/sampler_ref.c -o /tmp/ref\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker
    assert "not independent" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_candidate_copied_reference():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #9 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 9,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "cp sampler.c /tmp/sampler_ref.c && gcc /tmp/sampler_ref.c -o /tmp/ref"
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_candidate_copied_golden_reference():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the golden model.",
            "status": "verified",
            "evidence": "Tool #11 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 11,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "cat sampler.c > /tmp/golden_model.c"},
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_tmp_generated_oracle_source():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches an argmax oracle.",
            "status": "verified",
            "evidence": (
                "Tool #20 TOP1_TOKEN_ID_ORACLE count=20; "
                "TOKEN_ID_DECODE_MATCH_CANDIDATE True; "
                "top-1 token ids match 20/20, 0 mismatches; "
                "FINAL_TOKEN_ID_EQUIVALENCE_OK prompts=4 independent_oracle_ids=20."
            ),
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 20,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "cat > /tmp/oracle_gpt2.c <<'C'\n"
                        "/* model-written oracle source */\n"
                        "C\n"
                        "gcc /tmp/oracle_gpt2.c -o /tmp/oracle_gpt2\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": (
                        "TOP1_TOKEN_ID_ORACLE count=20\n"
                        "TOKEN_ID_DECODE_MATCH_CANDIDATE True\n"
                        "top-1 token ids match 20/20, 0 mismatches\n"
                        "FINAL_TOKEN_ID_EQUIVALENCE_OK prompts=4 independent_oracle_ids=20\n"
                    ),
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker
    assert "generated in the current work session" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_tmp_oracle_reuse():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches an argmax oracle.",
            "status": "verified",
            "evidence": "Tool #21 top-1 token ids match 20/20, 0 mismatches.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 21,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "gcc /tmp/oracle_gpt2.c -o /tmp/oracle && /tmp/oracle model.bin vocab.bpe"
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "top-1 token ids match 20/20, 0 mismatches\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_mixed_tests_and_tmp_oracle():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #22 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 22,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 /tests/reference_check.py /app/a.out\n"
                        "cat > /tmp/oracle_gpt2.c <<'C'\n"
                        "/* unrelated model-written oracle */\n"
                        "C\n"
                        "gcc /tmp/oracle_gpt2.c -o /tmp/oracle_gpt2\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_overwritten_tests_copy_destination():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #25 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 25,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "s=open('/tests/reference_model.c').read()\n"
                        "open('/tmp/reference_model.c','w').write(s)\n"
                        "open('/tmp/reference_model.c','w').write('/* generated replacement */')\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_cwd_generated_oracle_heredoc():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches an argmax oracle.",
            "status": "verified",
            "evidence": "Tool #23 top-1 token ids match 20/20, 0 mismatches.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 23,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "cat <<'C' > oracle_gpt2.c\n"
                        "/* model-written oracle source */\n"
                        "C\n"
                        "gcc oracle_gpt2.c -o oracle_gpt2\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "top-1 token ids match 20/20, 0 mismatches\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_cwd_generated_oracle_pipe_tee():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches an argmax oracle.",
            "status": "verified",
            "evidence": "Tool #26 top-1 token ids match 20/20, 0 mismatches.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 26,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "cat <<'C' | tee oracle_gpt2.c\n/* model-written oracle source */\nC\n"
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "top-1 token ids match 20/20, 0 mismatches\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_cwd_generated_oracle_tee():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches an argmax oracle.",
            "status": "verified",
            "evidence": "Tool #24 top-1 token ids match 20/20, 0 mismatches.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 24,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "tee oracle_gpt2.c <<'C'\n/* model-written oracle source */\nC\n"
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "top-1 token ids match 20/20, 0 mismatches\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_self_derived_evidence_text():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": (
                "Tool #12 standard-libm reference candidate_equals_reference True "
                "and expected_continuation passed."
            ),
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 12,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference oracle provenance ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_model_inference_task_provided_reference_source():
    text = (
        "Load checkpoint model.bin and tokenizer vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #10 candidate_equals_reference True and expected_continuation passed.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 10,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 - <<'PY'\n"
                        "s=open('/tests/reference_model.c').read()\n"
                        "open('/tmp/reference_model.c','w').write(s)\n"
                        "PY\n"
                        "gcc /tmp/reference_model.c -o /tmp/ref\n"
                    )
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference True\nexpected_continuation passed\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_model_inference_weak_or_failed_reference_text():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #7 reference model loaded ok and top-1 token ids match: false.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "reference model loaded ok\ntop-1 token ids match: false\nmatched 0/20\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference output quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_failed_boolean_oracle_text():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #8 candidate_equals_reference 0 and top-1 token ids match: 0.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 8,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "candidate_equals_reference: no\ntop-1 token ids match: 0\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference output quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_model_inference_reference_no_match_text():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #15 matches reference: no.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 15,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "reference comparison: no match\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference output quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_model_inference_success_with_zero_mismatches():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #13 top-1 token ids match 20/20, 0 mismatches.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 13,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "top-1 token ids match 20/20, 0 mismatches\nexpected continuation passed\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_model_inference_success_with_zero_failures():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #14 all matched, 0 failures.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 14,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "all matched, no failures\nexpected continuation passed\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_model_inference_reference_with_no_differences():
    text = (
        "Load a GPT model from model.bin and vocab.bpe, then sample the next token "
        "and print the generated continuation."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #16 reference comparison: 0 differences.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 16,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "exit_code": 0,
                    "stdout": "reference comparison: no differences\nreference comparison: no errors\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_model_inference_oracle_marker_from_command_parameter_only():
    text = (
        "Run inference from checkpoint weights and vocab.bpe, then print the generated "
        "token continuation from the model."
    )
    checks = [
        {
            "constraint": "Generated token continuation matches the reference model.",
            "status": "verified",
            "evidence": "Tool #6 reference implementation top-1 token ids match.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 6,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "echo 'reference implementation top-1 token ids match'"},
                "result": {"exit_code": 0, "stdout": "printed 20 generated tokens\n"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "model inference output quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_does_not_escalate_plain_token_output_task():
    text = "Write a CLI that prints exactly 20 tokens from stdin."
    checks = [
        {
            "constraint": "Print exactly 20 tokens.",
            "status": "verified",
            "evidence": "Tool #3 counted exactly 20 tokens.",
        }
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_query_only_hidden_model_classifier_covers_forward_extraction():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. Save the matrix "
        "to `/app/stolen_A1.npy`."
    )

    assert is_query_only_hidden_model_task(text)
    assert is_query_only_hidden_model_task(
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1."
    )
    assert not is_query_only_hidden_model_task("Call forward(x) in this ordinary helper test.")


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_from_write_file():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 checked source and output.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nimport forward as target\nnp.save('/app/stolen_A1.npy', target.A1)\n",
                },
            },
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "exists True\nmatches_A1 True\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_from_edit_hunks():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 checked source and output.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "edit_file_hunks",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "edits": [
                        {
                            "old": "return recover()",
                            "new": "import forward as target\nreturn target.A1",
                        }
                    ],
                },
            },
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "exists True\nmatches_A1 True\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_alias():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import forward as f\nanswer = f.A1\n",
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_dynamic_reads():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    forbidden_sources = [
        "import forward\nanswer = forward.__dict__['A1']\n",
        "import forward\nanswer = vars(forward)['A1']\n",
        "import importlib\nm = importlib.import_module('forward')\nanswer = m.A1\n",
        "m = __import__('forward')\nanswer = m.__dict__['A1']\n",
        "import importlib\nanswer = importlib.import_module('forward').A1\n",
        "from pathlib import Path\nsrc = Path('forward.py').read_text()\n",
    ]
    for source in forbidden_sources:
        session = {
            "tool_calls": [
                {
                    "id": 2,
                    "tool": "write_file",
                    "status": "completed",
                    "parameters": {"path": "steal.py", "content": source},
                },
                {
                    "id": 3,
                    "tool": "run_tests",
                    "status": "completed",
                    "result": {"stdout": "synthetic randomized holdout pass true\n"},
                },
            ]
        }

        blocker = acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )

        assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_allows_dynamic_import_for_forward_calls_only():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": (
                        "import importlib\n"
                        "m = importlib.import_module('forward')\n"
                        "def f(x):\n"
                        "    return m.forward(x)\n"
                    ),
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_star_import():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "from forward import *\nanswer = A1\n",
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_fixture_only_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #4 query_only_source_check True.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 visible fixture min_best_abs_cos_rows 0.999999 and pass True.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #4 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "exists True\nstolen_shape (20, 10)\ntarget_shape (20, 10)\n"
                        "query_only_source_check True\npass True\n"
                    )
                },
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_failed_holdout_plus_visible_passed():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 synthetic holdout failed; visible fixture passed.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "synthetic holdout failed\nvisible fixture passed\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_skipped_holdout_plus_visible_passed():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 visible fixture passed. synthetic holdout skipped.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "visible fixture passed. synthetic holdout skipped.\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_hidden_ok_without_holdout():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 hidden ok.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "hidden ok\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_query_only_holdout_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 source check passed and synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 synthetic randomized holdout pass true; all matched on generated 30-row model.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 exists True and synthetic pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": (
                        "source check passed\nsynthetic randomized hidden holdout pass true\n"
                        "generated 30-row model all matched\n"
                    )
                },
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_query_only_all_matched_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "randomized synthetic validation all_matched true\n"},
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_query_only_all_matched_false():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched=0.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "randomized synthetic validation all_matched=0\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_allows_synthetic_validator_object_fields():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 source check passed and synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 exists True and synthetic randomized holdout pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": (
                        "from forward import forward\n"
                        "class Synthetic:\n"
                        "    def __init__(self):\n"
                        "        self.A1 = None\n"
                        "synthetic = Synthetic()\n"
                        "synthetic.A1 = 'holdout ground truth only'\n"
                    ),
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_does_not_treat_ui_fit_or_offset_as_numeric():
    text = "Fix offset pagination regression where the text does not fit in the card. Ensure output file exists."
    checks = [
        {"constraint": constraint, "status": "verified", "evidence": "tool #2 output confirmed it"}
        for constraint in extract_acceptance_constraints(text)
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "ui pagination regression verified"},
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_does_not_escalate_non_edit_scope_checks():
    text = "Ensure the output file exists."
    checks = [{"constraint": text, "status": "verified", "evidence": "tool #2 wrote the file"}]
    session = {"tool_calls": [{"id": 2, "tool": "write_file", "status": "completed"}]}

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_exact_command_example_requirements_extract_backticked_run_shapes():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )

    commands = [item["command"] for item in exact_command_example_requirements(text)]

    assert commands == [
        "rustc /app/polyglot/main.rs && /app/polyglot/main N",
        "g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N",
    ]


def test_acceptance_finish_blocker_rejects_cd_wrapped_exact_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "rustc /app/polyglot/main.rs && /app/polyglot/main N",
            "status": "verified",
            "evidence": "tool #4 ran the exact command shape.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'cd /app/polyglot; "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": "bash -lc 'cd /app/polyglot; rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_exact_command_example_from_task_cwd():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "rustc /app/polyglot/main.rs && /app/polyglot/main N",
            "status": "verified",
            "evidence": "tool #4 ran rustc /app/polyglot/main.rs && /app/polyglot/main 20.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                    "stdout": "10946\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_command_example_from_tool_not_check_text():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes should print Fibonacci values.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                    "stdout": "10946\n",
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_command_example_verifier_loop_as_surrogate():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes should print Fibonacci values.",
            "status": "verified",
            "evidence": "Tool call 4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "for n in 0 1 2 7; do /app/polyglot/main \"$n\"; done'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "for n in 0 1 2 7; do /app/polyglot/main \"$n\"; done'"
                    ),
                    "exit_code": 0,
                    "stdout": "1\n1\n2\n21\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_output_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs -o /app/polyglot/main "
                        "&& /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs -o /app/polyglot/main "
                        "&& /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_output_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs','-o','/app/polyglot/main']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs','-o','/app/polyglot/main']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_semicolon_for_and_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs; /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs; /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_subshell_cd_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc '(cd /app/polyglot && rustc /app/polyglot/main.rs && /app/polyglot/main 20)'"
                },
                "result": {
                    "command": "bash -lc '(cd /app/polyglot && rustc /app/polyglot/main.rs && /app/polyglot/main 20)'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_setup_copy_between_command_example_terms():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "cp /app/main /app/polyglot/main && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "cp /app/main /app/polyglot/main && /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_setup_copy_before_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'cp /app/main /app/polyglot/main && "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'cp /app/main /app/polyglot/main && "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_out_dir_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs --out-dir /app/polyglot "
                        "&& /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs --out-dir /app/polyglot "
                        "&& /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_cwd_wrapper_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs'], cwd='/app/polyglot'); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs'], cwd='/app/polyglot'); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_chdir_wrapper_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import os, subprocess; os.chdir('/app/polyglot'); "
                        "subprocess.run(['rustc','/app/polyglot/main.rs']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import os, subprocess; os.chdir('/app/polyglot'); "
                        "subprocess.run(['rustc','/app/polyglot/main.rs']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_failed_command_example_result():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=1 attempted advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 1,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_requires_each_advertised_command_example():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )
    checks = [
        {
            "constraint": "Advertised Rust command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the Rust advertised command shape.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_both_advertised_command_examples():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes work.",
            "status": "verified",
            "evidence": "Tool #4 and Tool call 5 verified both advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain "
                        "&& /app/polyglot/cmain 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain "
                        "&& /app/polyglot/cmain 20'"
                    ),
                    "exit_code": 0,
                },
            },
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_python_command_example_itself():
    text = "You can run `python3 /app/check.py N` to validate the answer."
    checks = [
        {
            "constraint": "Advertised Python command works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the advertised Python command.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "python3 /app/check.py 1"},
                "result": {"command": "python3 /app/check.py 1", "exit_code": 0},
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_accepts_cat_command_example_itself():
    text = "You can run `cat /app/out.txt` to inspect the answer."
    checks = [
        {
            "constraint": "Advertised cat command works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the advertised cat command.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "cat /app/out.txt"},
                "result": {"command": "cat /app/out.txt", "exit_code": 0},
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )
