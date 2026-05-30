from mew.implement_lane.execution_evidence import (
    ArtifactEvidence,
    ToolRunRecord,
    apply_finish_gate,
    build_oracle_bundle,
    classify_execution_failure,
    derive_verifier_evidence,
    normalize_execution_contract,
    semantic_exit_from_run,
)


def test_normalize_execution_contract_preserves_v2_fields_and_enums() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "compound",
            "stage": "command",
            "purpose": "verification",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "declared_target_refs": [{"kind": "artifact", "path": "/tmp/frame.bmp"}],
            "source_authority_requirement": {
                "mode": "inherits_task_contract",
                "required": True,
                "source_tree_ref": "source-tree:primary",
            },
            "resume_identity": {"idempotence_key": "sha256:abc"},
            "continuation_policy": {"mode": "managed", "resume_policy": "same_resume_identity"},
            "background_policy": {"mode": "foreground_yieldable", "allow_background": True},
            "expected_exit": {"mode": "any"},
            "substeps": [
                {
                    "id": "substep:runtime",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "requires_artifacts": ["binary"],
                    "produces_artifacts": ["frame"],
                }
            ],
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "path": "/tmp/frame.bmp",
                    "source": "model_declared",
                    "producer_substep_id": "substep:runtime",
                }
            ],
        }
    )

    as_dict = contract.as_dict()
    assert contract.proof_role == "verifier"
    assert contract.acceptance_kind == "external_verifier"
    assert as_dict["source_authority_requirement"]["source_tree_ref"] == "source-tree:primary"
    assert as_dict["resume_identity"]["idempotence_key"] == "sha256:abc"
    assert as_dict["continuation_policy"]["resume_policy"] == "same_resume_identity"
    assert as_dict["background_policy"]["allow_background"] is True
    assert contract.substeps[0].proof_role == "verifier"
    assert contract.substeps[0].requires_artifacts == ("binary",)


def test_normalize_execution_contract_accepts_stdout_target_and_check_aliases() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:stdout",
            "expected_artifacts": [
                {
                    "target": "stdout",
                    "checks": [
                        {"kind": "non_empty"},
                        {"kind": "text_contains", "value": "ELF"},
                    ],
                }
            ],
        }
    )

    artifact = contract.expected_artifacts[0]

    assert artifact.id == "stdout"
    assert artifact.kind == "stdout"
    assert artifact.target == {"type": "stream", "stream": "stdout"}
    assert artifact.path == ""
    assert artifact.checks[0]["type"] == "non_empty"
    assert artifact.checks[1]["type"] == "text_contains"
    assert artifact.checks[1]["text"] == "ELF"


def test_normalize_execution_contract_keeps_shorthand_check_values() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:file",
            "expected_artifacts": [
                {
                    "path": "vm.js",
                    "checks": [
                        {"text_contains": "class VM"},
                        {"regex": "function\\s+run"},
                    ],
                }
            ],
        }
    )

    artifact = contract.expected_artifacts[0]

    assert artifact.checks[0]["type"] == "text_contains"
    assert artifact.checks[0]["text"] == "class VM"
    assert artifact.checks[1]["type"] == "regex"
    assert artifact.checks[1]["pattern"] == "function\\s+run"


def test_normalize_execution_contract_treats_artifact_kind_values_as_kind_checks() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:file",
            "expected_artifacts": [
                {
                    "path": "frame.bmp",
                    "kind": "file",
                    "checks": [
                        {"kind": "file"},
                        {"kind": "non_empty"},
                    ],
                }
            ],
        }
    )

    artifact = contract.expected_artifacts[0]

    assert artifact.checks[0]["type"] == "kind"
    assert artifact.checks[0]["expected"] == "file"
    assert artifact.checks[1]["type"] == "non_empty"


def test_normalize_execution_contract_ignores_empty_shorthand_check_values() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:file",
            "expected_artifacts": [
                {
                    "path": "vm.js",
                    "checks": [
                        {"text_contains": None, "value": "class VM"},
                        {"regex": None, "expected": "function\\s+run"},
                        {"text_contains": True, "expected": "literal fallback"},
                    ],
                }
            ],
        }
    )

    artifact = contract.expected_artifacts[0]

    assert artifact.checks[0]["type"] == "text_contains"
    assert artifact.checks[0]["text"] == "class VM"
    assert artifact.checks[1]["type"] == "regex"
    assert artifact.checks[1]["pattern"] == "function\\s+run"
    assert artifact.checks[2]["type"] == "text_contains"
    assert artifact.checks[2]["text"] == "literal fallback"


def test_build_oracle_bundle_keeps_latest_completion_contract_for_same_artifact_target() -> None:
    bundle = build_oracle_bundle(
        task_contract={},
        execution_contracts=[
            {
                "id": "contract:first",
                "acceptance_kind": "external_verifier",
                "expected_artifacts": [{"id": "frame", "path": "frame.txt"}],
            },
            {
                "id": "contract:latest",
                "acceptance_kind": "external_verifier",
                "expected_artifacts": [{"id": "frame", "path": "frame.txt"}],
            },
        ],
    )

    assert bundle is not None
    ids = {obligation.id for obligation in bundle.obligations}
    assert "oracle:contract:latest:verifier_pass" in ids
    assert "oracle:contract:first:verifier_pass" not in ids


def test_normalize_execution_contract_accepts_stream_field_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:stream",
            "expected_artifacts": [
                {
                    "stream": "stderr",
                    "checks": [{"kind": "regex", "value": "error|warning"}],
                }
            ],
        }
    )

    artifact = contract.expected_artifacts[0]

    assert artifact.id == "stderr"
    assert artifact.kind == "stderr"
    assert artifact.target == {"type": "stream", "stream": "stderr"}
    assert artifact.checks[0]["type"] == "regex"
    assert artifact.checks[0]["pattern"] == "error|warning"


def test_semantic_exit_code_set_accepts_declared_nonzero_exit() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "expected_exit": {"mode": "code_set", "codes": [0, 4]},
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="failed",
        exit_code=4,
    )

    semantic_exit = semantic_exit_from_run(record, contract)

    assert semantic_exit == {
        "ok": True,
        "category": "ok",
        "source": "contract_override",
        "message": "exit code 4 accepted",
    }


def test_tool_record_identity_keeps_record_id_separate_from_command_run_id() -> None:
    record = ToolRunRecord(
        record_id="tool-run-record:poll2",
        command_run_id="command-run:1",
        provider_call_id="call-poll-2",
        status="completed",
        exit_code=0,
    )

    as_dict = record.as_dict()

    assert as_dict["record_id"] == "tool-run-record:poll2"
    assert as_dict["command_run_id"] == "command-run:1"
    assert as_dict["provider_call_id"] == "call-poll-2"


def test_runtime_missing_artifact_classifies_from_structured_evidence_without_markers() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "compound",
            "expected_exit": {"mode": "any"},
            "substeps": [
                {
                    "id": "substep:runtime",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "produces_artifacts": ["frame"],
                }
            ],
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "source": "model_declared",
                    "producer_substep_id": "substep:runtime",
                }
            ],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:poll2",
        command_run_id="command-run:1",
        status="failed",
        exit_code=4,
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:poll2",
        contract_id="contract:1",
        substep_id="substep:runtime",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert classification.failure_class == "runtime_artifact_missing"
    assert classification.phase == "runtime"
    assert classification.kind == "missing_artifact"
    assert classification.confidence == "high"
    assert classification.evidence_refs[-1] == {"kind": "artifact_evidence", "id": "artifact-evidence:frame"}


def test_model_near_miss_verifier_vocabulary_normalizes_to_runtime_artifact_gap() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:near-miss-verifier",
            "role": "generated_artifact",
            "stage": "verification",
            "purpose": "verification",
            "proof_role": "final_verifier",
            "acceptance_kind": "artifact_and_runtime_verification",
            "expected_exit": {"mode": "any"},
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "path": "/tmp/frame.bmp",
                    "freshness": "created_after_run_start",
                    "checks": [{"type": "exists", "severity": "blocking"}],
                }
            ],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:vm",
        command_run_id="command-run:vm",
        status="completed",
        exit_code=0,
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:vm",
        tool_run_record_id="tool-run-record:vm",
        contract_id="contract:near-miss-verifier",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert contract.role == "runtime"
    assert contract.proof_role == "verifier"
    assert contract.acceptance_kind == "external_verifier"
    assert classification.failure_class == "runtime_artifact_missing"
    assert classification.phase == "runtime"
    assert classification.kind == "missing_artifact"


def test_generated_artifact_build_contract_normalizes_to_build_gap() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:near-miss-build",
            "role": "generated_artifact",
            "stage": "build",
            "purpose": "build",
            "proof_role": "target_build",
            "acceptance_kind": "candidate_artifact_proof",
            "expected_artifacts": [{"id": "binary", "kind": "executable", "path": "build/app"}],
        }
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:binary",
        artifact_id="binary",
        command_run_id="command-run:build",
        tool_run_record_id="tool-run-record:build",
        contract_id="contract:near-miss-build",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(None, [artifact], None, contract)

    assert contract.role == "build"
    assert classification.failure_class == "build_artifact_missing"
    assert classification.phase == "build"


def test_builder_near_miss_proof_role_does_not_create_invalid_acceptance_pair() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:builder-near-miss",
            "stage": "build",
            "purpose": "build",
            "proof_role": "builder",
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:build",
        command_run_id="command-run:build",
        status="completed",
        exit_code=0,
    )

    verifier = derive_verifier_evidence(contract, [record], [])
    gate = apply_finish_gate(contract, verifier, [])

    assert contract.proof_role == "none"
    assert contract.acceptance_kind == "not_acceptance"
    assert verifier.verdict != "fail"
    assert gate.blocked is False


def test_build_missing_artifact_does_not_classify_as_runtime() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "build",
            "expected_artifacts": [
                {
                    "id": "binary",
                    "kind": "executable",
                    "source": "model_declared",
                    "producer_substep_id": "substep:build",
                }
            ],
            "substeps": [
                {
                    "id": "substep:build",
                    "role": "build",
                    "stage": "build",
                    "proof_role": "target_build",
                    "acceptance_kind": "candidate_artifact_proof",
                    "produces_artifacts": ["binary"],
                }
            ],
        }
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:binary",
        artifact_id="binary",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        contract_id="contract:1",
        substep_id="substep:build",
        kind="executable",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(None, [artifact], None, contract)

    assert classification.failure_class == "build_artifact_missing"
    assert classification.phase == "build"


def test_runtime_inferred_artifact_caps_confidence_at_medium() -> None:
    contract = normalize_execution_contract(
        {},
        task_contract={
            "expected_artifacts": [
                {
                    "id": "frame",
                    "path": "/tmp/frame.bmp",
                    "kind": "file",
                }
            ]
        },
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        source="runtime_inferred",
        confidence="high",
        status="failed",
        blocking=True,
    )

    assert contract.expected_artifacts[0].source == "runtime_inferred"
    assert contract.expected_artifacts[0].confidence == "medium"
    classification = classify_execution_failure(None, [artifact], None, contract)
    assert classification.confidence == "medium"


def test_partial_verifier_blocks_finish_for_nonterminal_run() -> None:
    contract = normalize_execution_contract({"id": "contract:1", "verifier_required": True})
    record = ToolRunRecord(
        record_id="tool-run-record:start",
        command_run_id="command-run:1",
        status="yielded",
    )

    verifier = derive_verifier_evidence(contract, [record], [])
    gate = apply_finish_gate(contract, verifier, [])

    assert verifier.verdict == "partial"
    assert gate.blocked is True
    assert "verifier_partial" in gate.reasons


def test_missing_required_verifier_evidence_is_partial_without_runs() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "verifier_required": True,
            "expected_artifacts": [{"id": "frame", "required": True}],
        }
    )

    verifier = derive_verifier_evidence(contract, [], [])
    gate = apply_finish_gate(contract, verifier, [])

    assert verifier.verdict == "partial"
    assert {"kind": "artifact_evidence", "artifact_id": "frame"} in verifier.missing_evidence
    assert gate.blocked is True


def test_compound_failed_input_artifact_takes_precedence_over_later_runtime_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "compound",
            "substeps": [
                {
                    "id": "substep:build",
                    "role": "build",
                    "stage": "build",
                    "proof_role": "target_build",
                    "acceptance_kind": "candidate_artifact_proof",
                    "produces_artifacts": ["binary"],
                },
                {
                    "id": "substep:runtime",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "requires_artifacts": ["binary"],
                    "produces_artifacts": ["frame"],
                },
            ],
            "expected_artifacts": [
                {"id": "binary", "producer_substep_id": "substep:build"},
                {"id": "frame", "producer_substep_id": "substep:runtime"},
            ],
        }
    )
    runtime_artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        substep_id="substep:runtime",
        status="failed",
        blocking=True,
    )
    build_artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:binary",
        artifact_id="binary",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        substep_id="substep:build",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(None, [runtime_artifact, build_artifact], None, contract)

    assert classification.failure_class == "build_artifact_missing"
    assert classification.phase == "build"
    assert classification.kind == "missing_artifact"
    assert classification.evidence_refs[-1] == {"kind": "artifact_evidence", "id": "artifact-evidence:binary"}


def test_missing_input_evidence_prevents_later_runtime_artifact_from_becoming_primary() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "compound",
            "substeps": [
                {
                    "id": "substep:build",
                    "role": "build",
                    "stage": "build",
                    "proof_role": "target_build",
                    "acceptance_kind": "candidate_artifact_proof",
                    "produces_artifacts": ["binary"],
                },
                {
                    "id": "substep:runtime",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "requires_artifacts": ["binary"],
                    "produces_artifacts": ["frame"],
                },
            ],
            "expected_artifacts": [
                {"id": "binary", "producer_substep_id": "substep:build"},
                {"id": "frame", "producer_substep_id": "substep:runtime"},
            ],
        }
    )
    runtime_artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        substep_id="substep:runtime",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(None, [runtime_artifact], None, contract)

    assert classification.failure_class == "build_artifact_missing"
    assert classification.kind == "partial_evidence"
    assert classification.secondary_classes == ("runtime_artifact_missing",)


def test_partial_input_artifact_keeps_partial_kind_before_later_runtime_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "compound",
            "substeps": [
                {
                    "id": "substep:build",
                    "role": "build",
                    "stage": "build",
                    "proof_role": "target_build",
                    "acceptance_kind": "candidate_artifact_proof",
                    "produces_artifacts": ["binary"],
                },
                {
                    "id": "substep:runtime",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "requires_artifacts": ["binary"],
                    "produces_artifacts": ["frame"],
                },
            ],
            "expected_artifacts": [
                {"id": "binary", "producer_substep_id": "substep:build"},
                {"id": "frame", "producer_substep_id": "substep:runtime"},
            ],
        }
    )
    runtime_artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        substep_id="substep:runtime",
        status="failed",
        blocking=True,
    )
    build_artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:binary",
        artifact_id="binary",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        substep_id="substep:build",
        status="partial",
        blocking=True,
    )

    classification = classify_execution_failure(None, [runtime_artifact, build_artifact], None, contract)

    assert classification.failure_class == "build_artifact_missing"
    assert classification.kind == "partial_evidence"
    assert classification.evidence_refs[-1] == {"kind": "artifact_evidence", "id": "artifact-evidence:binary"}


def test_contract_required_artifact_cannot_be_weakened_by_evidence_required_false() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "verifier_required": True,
            "expected_artifacts": [{"id": "frame", "required": True}],
        }
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        required=False,
        status="failed",
        blocking=False,
    )

    verifier = derive_verifier_evidence(contract, [], [artifact])
    classification = classify_execution_failure(None, [artifact], verifier, contract)

    assert verifier.verdict == "fail"
    assert classification.failure_class == "artifact_validation_failure"
    assert classification.kind == "missing_artifact"


def test_partial_artifact_evidence_classifies_as_partial_not_missing() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_artifacts": [{"id": "frame", "required": True}],
        }
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="partial",
        blocking=True,
    )

    classification = classify_execution_failure(None, [artifact], None, contract)

    assert classification.failure_class == "artifact_validation_failure"
    assert classification.kind == "partial_evidence"


def test_runtime_inferred_confidence_uses_matching_expected_artifact_source() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_artifacts": [{"id": "frame", "source": "runtime_inferred"}],
        }
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(None, [artifact], None, contract)

    assert classification.confidence == "medium"


def test_invalid_proof_acceptance_pair_fails_verifier_and_blocks_finish() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "proof_role": "none",
            "acceptance_kind": "external_verifier",
            "verifier_required": True,
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="completed",
        exit_code=0,
    )

    verifier = derive_verifier_evidence(contract, [record], [])
    gate = apply_finish_gate(contract, verifier, [])

    assert verifier.verdict == "fail"
    assert verifier.checks[0]["observed"]["invalid_pairs"][0]["proof_role"] == "none"
    assert gate.blocked is True


def test_v2_dependency_strategy_and_diagnostic_final_artifact_pairs_are_valid() -> None:
    dependency_contract = normalize_execution_contract(
        {
            "id": "contract:dependency",
            "proof_role": "dependency_strategy",
            "acceptance_kind": "not_acceptance",
            "verifier_required": True,
        }
    )
    diagnostic_contract = normalize_execution_contract(
        {
            "id": "contract:diagnostic",
            "purpose": "diagnostic",
            "proof_role": "final_artifact",
            "acceptance_kind": "not_acceptance",
            "verifier_required": True,
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="completed",
        exit_code=0,
    )

    assert derive_verifier_evidence(dependency_contract, [record], []).verdict == "pass"
    assert derive_verifier_evidence(diagnostic_contract, [record], []).verdict == "pass"


def test_mapping_normalization_does_not_collapse_record_id_into_command_run_id() -> None:
    classification = classify_execution_failure(
        {
            "record_id": "tool-run-record:poll2",
            "status": "failed",
            "exit_code": 1,
        },
        [],
        None,
        {"id": "contract:1", "role": "runtime", "expected_exit": {"mode": "zero"}},
    )

    assert {"kind": "tool_run_record", "id": "tool-run-record:poll2"} in classification.evidence_refs
    assert {"kind": "command_run", "id": ""} in classification.evidence_refs
    assert {"kind": "command_run", "id": "tool-run-record:poll2"} not in classification.evidence_refs


def test_artifact_primary_keeps_semantic_exit_as_secondary_kind() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_exit": {"mode": "zero"},
            "expected_artifacts": [{"id": "frame", "source": "model_declared"}],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="failed",
        exit_code=4,
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert classification.failure_class == "runtime_artifact_missing"
    assert classification.secondary_classes == ("runtime_failure",)
    assert classification.secondary_kinds == ("nonzero_exit",)


def test_silent_terminal_runtime_failure_defers_to_failed_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_exit": {"mode": "zero"},
            "expected_artifacts": [{"id": "frame", "path": "/tmp/frame.bmp", "source": "model_declared"}],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="interrupted",
        interrupted=True,
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert classification.failure_class == "runtime_artifact_missing"
    assert classification.kind == "missing_artifact"
    assert classification.secondary_classes == ("runtime_failure",)
    assert classification.secondary_kinds == ("interrupted",)
    assert "producing substep" in classification.required_next_probe


def test_terminal_runtime_failure_with_output_stays_primary_over_failed_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_exit": {"mode": "zero"},
            "expected_artifacts": [{"id": "frame", "path": "/tmp/frame.bmp", "source": "model_declared"}],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="interrupted",
        interrupted=True,
        stderr_preview="unsupported opcode 0x1f",
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert classification.failure_class == "runtime_failure"
    assert classification.kind == "interrupted"
    assert classification.summary == "tool run tool-run-record:1 ended with interrupted"
    assert classification.required_next_probe == ""


def test_terminal_failed_runtime_failure_with_output_stays_primary_over_failed_artifact() -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "role": "runtime",
            "expected_exit": {"mode": "zero"},
            "expected_artifacts": [{"id": "frame", "path": "/tmp/frame.bmp", "source": "model_declared"}],
        }
    )
    record = ToolRunRecord(
        record_id="tool-run-record:1",
        command_run_id="command-run:1",
        status="failed",
        exit_code=1,
        stderr_preview="segv read32 0x00000000",
    )
    artifact = ArtifactEvidence(
        evidence_id="artifact-evidence:frame",
        artifact_id="frame",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        status="failed",
        blocking=True,
    )

    classification = classify_execution_failure(record, [artifact], None, contract)

    assert classification.failure_class == "runtime_failure"
    assert classification.kind == "nonzero_exit"
    assert classification.summary == "exit code 1"
    assert classification.secondary_classes == ("runtime_artifact_missing",)
    assert classification.secondary_kinds == ("missing_artifact",)
    assert classification.required_next_probe == ""
