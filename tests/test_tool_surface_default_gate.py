from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID
from mew.implement_lane.tool_surface_default_gate import evaluate_tool_surface_default_switch_gate


def _row(profile_id: str, **overrides: object) -> dict[str, object]:
    row = {
        "profile_id": profile_id,
        "lane_status": "completed",
        "accepted_finish_status": "accepted",
        "provider_visible_forbidden_scan_ok": True,
        "hidden_steering_markers": [],
        "render_leak_ok": True,
        "every_call_has_exactly_one_output": True,
        "verifier_evidence_preserved": True,
        "argument_adapter_failure_count": 0,
        "unsupported_capability_count": 0,
        "mutation_count": 1,
        "first_write_turn": 2,
        "probe_count_before_first_write": 1,
        "failed_verifier_to_next_edit_latency": {"latency_turns": 1},
        "provider_visible_output_bytes": 400,
        "provider_visible_schema_bytes": 200,
        "provider_request_inventory_bytes": 200,
        "proof_replay_status": {
            "proof_manifest_present": True,
            "transcript_hash_matches_manifest": True,
            "evidence_observation_present": True,
        },
    }
    row.update(overrides)
    return row


def _report(
    *,
    baseline: dict[str, object] | None = None,
    candidate: dict[str, object] | None = None,
    comparable: bool = True,
) -> dict[str, object]:
    baseline_row = baseline or _row(
        MEW_LEGACY_PROFILE_ID,
        first_write_turn=3,
        probe_count_before_first_write=2,
        provider_visible_output_bytes=500,
        provider_visible_schema_bytes=300,
        provider_request_inventory_bytes=300,
    )
    candidate_row = candidate or _row(CODEX_HOT_PATH_PROFILE_ID)
    return {
        "schema_version": 1,
        "report_kind": "tool_surface_profile_ab_report",
        "ab_pair_id": "ab-gate-unit",
        "ab_comparable": comparable,
        "default_switch_evidence_included": comparable,
        "rows": [baseline_row, candidate_row],
    }


def test_default_switch_gate_ready_when_candidate_not_worse_and_reviewer_accepted() -> None:
    result = evaluate_tool_surface_default_switch_gate(
        [_report()],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )

    payload = result.as_dict()
    assert payload["status"] == "ready"
    assert payload["can_switch_default"] is True
    assert payload["reasons"] == []
    assert payload["metrics"]["candidate_success_rate"] == 1.0


def test_default_switch_gate_blocks_without_reviewer_or_fixed_set() -> None:
    result = evaluate_tool_surface_default_switch_gate([_report()])

    assert result.can_switch_default is False
    assert "reviewer_acceptance_required" in result.reasons
    assert "fixed_ab_set_id_required" in result.reasons


def test_default_switch_gate_blocks_candidate_provider_visible_leak() -> None:
    result = evaluate_tool_surface_default_switch_gate(
        [
            _report(
                candidate=_row(
                    CODEX_HOT_PATH_PROFILE_ID,
                    provider_visible_forbidden_scan_ok=False,
                    hidden_steering_markers=["first_write_due"],
                )
            )
        ],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )

    assert result.can_switch_default is False
    assert "candidate_provider_visible_forbidden_scan_failed" in result.reasons
    assert "candidate_hidden_steering_markers_present" in result.reasons


def test_default_switch_gate_requires_visible_byte_safety_reason_when_candidate_larger() -> None:
    report = _report(
        candidate=_row(
            CODEX_HOT_PATH_PROFILE_ID,
            provider_visible_output_bytes=2000,
            provider_visible_schema_bytes=2000,
            provider_request_inventory_bytes=2000,
        )
    )

    blocked = evaluate_tool_surface_default_switch_gate(
        [report],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )
    allowed = evaluate_tool_surface_default_switch_gate(
        [report],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
        visible_bytes_safety_reason="candidate carries terminal tails needed for replay comparison",
    )

    assert blocked.can_switch_default is False
    assert "candidate_visible_bytes_higher_without_safety_reason" in blocked.reasons
    assert allowed.can_switch_default is True


def test_default_switch_gate_blocks_missing_candidate_first_write_evidence() -> None:
    result = evaluate_tool_surface_default_switch_gate(
        [
            _report(
                candidate=_row(
                    CODEX_HOT_PATH_PROFILE_ID,
                    first_write_turn=None,
                    mutation_count=0,
                )
            )
        ],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )

    assert result.can_switch_default is False
    assert "candidate_first_write_evidence_missing" in result.reasons


def test_default_switch_gate_blocks_one_missing_first_write_in_multi_pair_set() -> None:
    good = _report()
    missing = _report(
        candidate=_row(
            CODEX_HOT_PATH_PROFILE_ID,
            first_write_turn=None,
            mutation_count=0,
        )
    )

    result = evaluate_tool_surface_default_switch_gate(
        [good, missing],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )

    assert result.can_switch_default is False
    assert "candidate_first_write_evidence_missing" in result.reasons


def test_default_switch_gate_blocks_failed_verifier_without_next_edit() -> None:
    result = evaluate_tool_surface_default_switch_gate(
        [
            _report(
                candidate=_row(
                    CODEX_HOT_PATH_PROFILE_ID,
                    failed_verifier_to_next_edit_latency={
                        "failed_verifier_call_id": "verify-1",
                        "next_edit_call_id": "",
                        "latency_turns": None,
                    },
                )
            )
        ],
        reviewer_accepted=True,
        fixed_ab_set_id="fixed-unit-set",
    )

    assert result.can_switch_default is False
    assert "candidate_failed_verifier_without_next_edit" in result.reasons
