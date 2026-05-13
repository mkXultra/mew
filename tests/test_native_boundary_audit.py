from pathlib import Path

from mew.implement_lane.native_boundary_audit import run_native_boundary_audit


def test_native_boundary_audit_passes_current_repo() -> None:
    report = run_native_boundary_audit(Path(__file__).resolve().parents[1])

    assert report.ok, report.as_dict()
    assert any(check.name == "design_tracks_codex_like_live_hot_path" for check in report.checks)
    assert any(check.name == "source_inventory_native_loop_control_policy_state" for check in report.checks)


def test_native_boundary_audit_reports_missing_required_design_marker(tmp_path: Path) -> None:
    _write_complete_fixture(tmp_path)
    design = tmp_path / "docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md"
    design.write_text("incomplete design\n", encoding="utf-8")

    report = run_native_boundary_audit(tmp_path)

    assert not report.ok
    failed = {check.name for check in report.checks if not check.passed}
    assert "design_tracks_codex_like_live_hot_path" in failed
    assert "source_inventory_native_loop_control_policy_state" not in failed


def test_native_boundary_audit_reports_missing_source_marker_in_anchor_window(tmp_path: Path) -> None:
    _write_complete_fixture(tmp_path)
    harness = tmp_path / "src/mew/implement_lane/native_tool_harness.py"
    harness.write_text(
        harness.read_text(encoding="utf-8").replace('    "compact_sidecar_digest": dict(compact_sidecar_digest),\n', ""),
        encoding="utf-8",
    )

    report = run_native_boundary_audit(tmp_path)

    assert not report.ok
    failed = {check.name for check in report.checks if not check.passed}
    assert "source_inventory_persisted_lane_state_provider_payload" in failed


def test_native_boundary_audit_reports_missing_source_file(tmp_path: Path) -> None:
    _write_complete_fixture(tmp_path)
    (tmp_path / "src/mew/implement_lane/execution_evidence.py").unlink()

    report = run_native_boundary_audit(tmp_path)

    assert not report.ok
    failed = {check.name for check in report.checks if not check.passed}
    assert "source_inventory_execution_evidence_finish_gate_producer" in failed


def _write_complete_fixture(root: Path) -> None:
    design = root / "docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md"
    design.parent.mkdir(parents=True)
    design.write_text(
        "Codex-like live hot path native transcript window compact factual tool-result digest mew-specific durable sidecar proof\n"
        "Provider-Visible Forbidden next_action first_write_due prewrite_probe_plateau WorkFrame\n"
        "Internal Sidecar Contract response_transcript.json provider request inventory typed evidence sidecars\n"
        "Tool Surface Contract apply_patch edit_file write_file\n"
        "Phase 1A: Transcript/Input Collapse Phase 1B: Tool Surface And Mutation Path Main Codex responsibilities\n",
        encoding="utf-8",
    )
    impl = root / "src/mew/implement_lane"
    impl.mkdir(parents=True)
    (impl / "native_tool_harness.py").write_text(
        'if call.kind == "finish_call" and result.status == "completed" and not result.is_error:\n'
        "    accepted_finish = call\n"
        '    status = "completed"\n'
        "closeout = _native_final_verifier_closeout(\n"
        "    provider=provider,\n"
        "    tool_calls=tuple(tool_calls),\n"
        ")\n"
        "def _responses_input_items():\n"
        "    compact_sidecar_digest = {}\n"
        "task_payload = {\n"
        '    "compact_sidecar_digest": dict(compact_sidecar_digest),\n'
        "}\n"
        "def _native_loop_control_state():\n"
        "    first_write_due = True\n"
        "    verifier_repair_due = True\n"
        "    return {\n"
        '        "surface": "native_loop_signals",\n'
        "    }\n",
        encoding="utf-8",
    )
    (impl / "exec_runtime.py").write_text(
        "finish_gate = apply_finish_gate(contract, verifier, (classification,))\n"
        'payload["structured_finish_gate"] = finish_gate.as_dict()\n'
        "_contract_failure_blocks_tool_status(contract)\n",
        encoding="utf-8",
    )
    (impl / "execution_evidence.py").write_text(
        "def apply_finish_gate(contract, verifier_evidence, classifications) -> FinishGateResult:\n"
        "    reasons = []\n"
        "    evidence_refs = []\n",
        encoding="utf-8",
    )
    (impl / "native_sidecar_projection.py").write_text(
        "def build_compact_native_sidecar_digest(transcript):\n"
        '    "provider_input_authority": "transcript_window_plus_compact_sidecar_digest"\n'
        '    "latest_tool_results"\n'
        '    "latest_evidence_refs"\n'
        '    "sidecar_hashes"\n'
        "def _workframe_digest(workframe_bundle):\n"
        "    required_next = {}\n"
        '    "required_next_kind"\n'
        '    "required_next_evidence_refs"\n'
        "def _derived_active_work_todo():\n"
        "    required_next_kind = ''\n"
        '    "first_write_readiness"\n'
        '    "required_next"\n',
        encoding="utf-8",
    )
    (impl / "native_workframe_projection.py").write_text(
        '"prompt_visible_workframe": _prompt_visible_workframe(workframe.as_dict()),\n'
        '"reducer_output": workframe.as_dict(),\n'
        '"prompt_render_inventory"\n'
        "def build_native_prompt_input_inventory(compact_sidecar_digest):\n"
        '    "diagnostic_only_fields_report"\n'
        '    "provider_visible": False\n'
        '    "provider_visible_forbidden_fields"\n'
        '    "native_loop_signals"\n'
        "def _prompt_visible_workframe(workframe):\n"
        '    "provider_visible": False\n'
        '    "native_workframe_sidecar_debug_ref"\n'
        '    "missing_evidence_refs"\n',
        encoding="utf-8",
    )
