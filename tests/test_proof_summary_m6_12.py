import hashlib
import json
from types import SimpleNamespace

from mew.calibration_report import ARCHETYPE_PRIORITY, CLASSIFIER_VERSION
from mew.cli import build_parser
from mew.commands import cmd_proof_summary
from mew.proof_summary import format_m6_12_report, summarize_m6_12_report


def _row(
    line_id,
    *,
    replay_bundle_path="",
    counted=True,
    blocker_code="cached_window_incomplete",
    countedness="canonical",
    reviewer_decision="accepted",
    head="",
):
    row = {
        "task_id": line_id,
        "counted": counted,
        "countedness": countedness,
        "blocker_code": blocker_code,
        "reviewer_decision": reviewer_decision,
        "replay_bundle_path": replay_bundle_path,
    }
    if head:
        row["head"] = head
    return row


def _write_ledger(path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_bundle(root, relative_path, text="bundle\n"):
    bundle = root / relative_path
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(text, encoding="utf-8")
    return bundle


def _write_compiler_bundle(root, relative_dir):
    bundle_dir = root / relative_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)
    metadata = bundle_dir / "replay_metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "bundle": "patch_draft_compiler",
                "files": {"validator_result": "validator_result.json"},
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "validator_result.json").write_text(
        json.dumps({"kind": "patch_draft", "status": "validated"}),
        encoding="utf-8",
    )
    return metadata


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_m6_12_report_json_has_contract_layers_and_classifier_trace(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    replay_path = ".mew/replays/work-loop/run/replay_metadata.json"
    _write_ledger(
        ledger,
        [
            _row(572, replay_bundle_path=replay_path),
            _row(
                573,
                counted=False,
                blocker_code="",
                countedness="partial_gate_validation_only",
                reviewer_decision="rejected",
            ),
        ],
    )
    _write_compiler_bundle(tmp_path, "run")
    _write_compiler_bundle(tmp_path, "outside-ledger")

    summary = summarize_m6_12_report(tmp_path, ledger=ledger)

    assert summary["ok"] is True
    assert summary["kind"] == "m6_12_report"
    assert summary["subcommand_mode"] == "m6_12_report"
    assert summary["classifier_version"] == CLASSIFIER_VERSION
    assert summary["canonical"]["mode"] == "pre_closeout"
    assert summary["canonical"]["ledger_path"] == str(ledger)
    assert summary["canonical"]["ledger_rows"] == 2
    assert summary["canonical"]["cohorts"]["all"]["counted_rows"] == 1
    assert summary["canonical"]["bundles"] == {
        "referenced": 1,
        "resolved": 1,
        "missing": 0,
    }
    assert summary["canonical"]["bundle_provenance"] == {
        "mode": "pre_closeout",
        "root": str(tmp_path),
        "closeout_index": None,
        "referenced": 1,
        "resolved": 1,
        "missing": 0,
        "missing_row_refs": [],
    }
    assert summary["derived"]["classifier_priority"] == list(ARCHETYPE_PRIORITY)
    assert summary["derived"]["archetype_counts"]["cached_window_integrity"] == 1
    assert summary["derived"]["calibration_rates"]["source"] == "resolved_ledger_replay_bundles"
    assert summary["derived"]["calibration_rates"]["total_bundles"] == 1
    cached_window = next(
        item
        for item in summary["derived"]["archetypes_active"]
        if item["label"] == "cached_window_integrity"
    )
    assert cached_window["counted"] == 1
    assert cached_window["evidence_priority"] == 2
    assert cached_window["row_refs"] == ["ledger:#1"]
    assert cached_window["bundle_refs"] == [replay_path]
    assert summary["derived"]["drift_axes"][0]["reserved"] is True


def test_m6_12_report_text_includes_contract_sections(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    replay_path = ".mew/replays/work-loop/run/replay_metadata.json"
    _write_ledger(
        ledger,
        [
            _row(572, replay_bundle_path=replay_path),
            _row(
                573,
                replay_bundle_path="",
                counted=False,
                blocker_code="",
                countedness="partial_gate_validation_only",
            ),
        ],
    )
    _write_compiler_bundle(tmp_path, "run")

    text = format_m6_12_report(summarize_m6_12_report(tmp_path, ledger=ledger))

    assert "M6.12 proof summary" in text
    assert "subcommand_mode: m6_12_report" in text
    assert f"classifier_version: {CLASSIFIER_VERSION}" in text
    assert "mode: pre_closeout" in text
    assert "bundle_provenance: mode=pre_closeout" in text
    assert "referenced=1 resolved=1 missing=0" in text
    assert "summary:" in text
    assert "all counted=1 non_counted=1" in text
    assert "subsystem_heatmap:" in text
    assert "unknown counted=1 top=cached_window_integrity(1) rows=ledger:#1" in text
    assert "recurrence:" in text
    assert "drift:" in text
    assert "calibration_rates (bundle-derived):" in text
    assert "non_counted_concentration:" in text
    assert "reason unspecified x1 rows=ledger:#2" in text
    assert "countedness partial_gate_validation_only x1 rows=ledger:#2" in text
    assert "classifier_priority: " + ", ".join(ARCHETYPE_PRIORITY) in text
    assert "hardest_archetype: cached_window_integrity" in text
    assert "archetypes_active: cached_window_integrity=1" in text


def test_m6_12_report_defaults_to_proof_artifacts_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proof_artifacts = tmp_path / "proof-artifacts"
    proof_artifacts.mkdir()
    ledger = proof_artifacts / "m6_11_calibration_ledger.jsonl"
    _write_ledger(ledger, [_row(1, replay_bundle_path="")])

    summary = summarize_m6_12_report(tmp_path / "artifact-root")

    assert summary["canonical"]["ledger_path"] == "proof-artifacts/m6_11_calibration_ledger.jsonl"
    assert summary["ok"] is True


def test_m6_12_precloseout_missing_bundle_records_reason(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    _write_ledger(
        ledger,
        [_row(572, replay_bundle_path=".mew/replays/work-loop/missing/replay_metadata.json")],
    )

    summary = summarize_m6_12_report(tmp_path, ledger=ledger)

    provenance = summary["canonical"]["bundle_provenance"]
    assert summary["ok"] is False
    assert provenance["referenced"] == 1
    assert provenance["resolved"] == 0
    assert provenance["missing"] == 1
    assert provenance["missing_row_refs"] == [
        {"row_ref": "ledger:#1", "reason": "precloseout_missing"}
    ]
    assert summary["derived"]["calibration_rates"] is None


def test_m6_12_report_respects_measurement_head_cohort(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    _write_ledger(
        ledger,
        [
            _row(1, replay_bundle_path="", head="HEAD-MEASURE"),
            _row(2, replay_bundle_path="", head="OTHER"),
        ],
    )

    summary = summarize_m6_12_report(tmp_path, ledger=ledger, measurement_head="HEAD-MEASURE")

    assert summary["canonical"]["cohorts"]["measurement_head"] == {
        "ledger_rows": 1,
        "counted_rows": 1,
        "non_counted_rows": 0,
    }


def test_m6_12_report_warns_for_unclassified_rows(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    _write_ledger(
        ledger,
        [
            _row(
                1,
                replay_bundle_path="",
                blocker_code="",
                countedness="unknown_new_shape",
                reviewer_decision="unknown",
            )
        ],
    )

    summary = summarize_m6_12_report(tmp_path, ledger=ledger)

    assert summary["derived"]["archetype_counts"]["unclassified_v0"] == 1
    assert "unclassified_v0 ledger:#1" in summary["warnings"]


def test_m6_12_postcloseout_resolver_records_all_missing_reasons(tmp_path):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    paths = {
        "not-indexed": ".mew/replays/work-loop/not-indexed/replay_metadata.json",
        "missing": ".mew/replays/work-loop/missing/replay_metadata.json",
        "sha-mismatch": ".mew/replays/work-loop/sha-mismatch/replay_metadata.json",
        "ok": ".mew/replays/work-loop/ok/replay_metadata.json",
    }
    _write_ledger(
        ledger,
        [
            _row(1, replay_bundle_path=paths["not-indexed"]),
            _row(2, replay_bundle_path=paths["missing"]),
            _row(3, replay_bundle_path=paths["sha-mismatch"]),
            _row(4, replay_bundle_path=paths["ok"]),
        ],
    )
    mismatch_bundle = _write_bundle(tmp_path, "sha-mismatch/replay_metadata.json", "actual\n")
    ok_bundle = _write_bundle(tmp_path, "ok/replay_metadata.json", "ok\n")
    index = tmp_path / "closeout-index.json"
    index.write_text(
        json.dumps(
            [
                {
                    "original_path": paths["missing"],
                    "export_path": "missing/replay_metadata.json",
                    "sha256": "",
                    "size_bytes": 0,
                    "exported_at": "2026-04-25T00:00:00Z",
                },
                {
                    "original_path": paths["sha-mismatch"],
                    "export_path": "sha-mismatch/replay_metadata.json",
                    "sha256": "0" * 64,
                    "size_bytes": mismatch_bundle.stat().st_size,
                    "exported_at": "2026-04-25T00:00:00Z",
                },
                {
                    "original_path": paths["ok"],
                    "export_path": "ok/replay_metadata.json",
                    "sha256": _sha256(ok_bundle),
                    "size_bytes": ok_bundle.stat().st_size,
                    "exported_at": "2026-04-25T00:00:00Z",
                },
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_m6_12_report(tmp_path, ledger=ledger, closeout_index=index)

    provenance = summary["canonical"]["bundle_provenance"]
    assert summary["canonical"]["mode"] == "post_closeout"
    assert provenance["closeout_index"] == str(index)
    assert provenance["referenced"] == 4
    assert provenance["resolved"] == 1
    assert provenance["missing"] == 3
    assert provenance["missing_row_refs"] == [
        {"row_ref": "ledger:#1", "reason": "closeout_index_miss"},
        {"row_ref": "ledger:#2", "reason": "closeout_export_missing"},
        {"row_ref": "ledger:#3", "reason": "closeout_export_sha_mismatch"},
    ]


def test_proof_summary_parser_accepts_m6_12_flags():
    parser = build_parser()

    args = parser.parse_args(
        [
            "proof-summary",
            "artifacts",
            "--m6_12-report",
            "--ledger",
            "ledger.jsonl",
            "--closeout-index",
            "index.json",
        ]
    )

    assert args.m6_12_report is True
    assert args.ledger == "ledger.jsonl"
    assert args.closeout_index == "index.json"


def test_cmd_proof_summary_rejects_conflicting_m6_11_and_m6_12_flags(capsys):
    args = SimpleNamespace(
        artifact_dir="artifacts",
        json=True,
        strict=False,
        m6_11_phase2_calibration=True,
        m6_12_report=True,
        ledger=None,
        closeout_index=None,
        measurement_head=None,
    )

    assert cmd_proof_summary(args) == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_cmd_proof_summary_rejects_closeout_index_without_m6_12(capsys):
    args = SimpleNamespace(
        artifact_dir="artifacts",
        json=True,
        strict=False,
        m6_11_phase2_calibration=False,
        m6_12_report=False,
        ledger=None,
        closeout_index="index.json",
        measurement_head=None,
    )

    assert cmd_proof_summary(args) == 2
    assert "valid only with --m6_12-report" in capsys.readouterr().err


def test_cmd_proof_summary_m6_12_json_output(tmp_path, capsys):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    replay_path = ".mew/replays/work-loop/run/replay_metadata.json"
    _write_ledger(ledger, [_row(572, replay_bundle_path=replay_path)])
    _write_compiler_bundle(tmp_path, "run")
    args = SimpleNamespace(
        artifact_dir=str(tmp_path),
        json=True,
        strict=False,
        m6_11_phase2_calibration=False,
        m6_12_report=True,
        ledger=str(ledger),
        closeout_index=None,
        measurement_head=None,
    )

    assert cmd_proof_summary(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "m6_12_report"
    assert payload["subcommand_mode"] == "m6_12_report"
    assert payload["classifier_version"] == CLASSIFIER_VERSION
    assert payload["canonical"]["mode"] == "pre_closeout"


def test_cmd_proof_summary_m6_12_strict_missing_bundle_fails(tmp_path, capsys):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    _write_ledger(
        ledger,
        [_row(572, replay_bundle_path=".mew/replays/work-loop/missing/replay_metadata.json")],
    )
    args = SimpleNamespace(
        artifact_dir=str(tmp_path),
        json=True,
        strict=True,
        m6_11_phase2_calibration=False,
        m6_12_report=True,
        ledger=str(ledger),
        closeout_index=None,
        measurement_head=None,
    )

    assert cmd_proof_summary(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["canonical"]["bundle_provenance"]["missing"] == 1


def test_cmd_proof_summary_m6_12_non_strict_missing_bundle_exits_zero(tmp_path, capsys):
    ledger = tmp_path / "m6_11_calibration_ledger.jsonl"
    _write_ledger(
        ledger,
        [_row(572, replay_bundle_path=".mew/replays/work-loop/missing/replay_metadata.json")],
    )
    args = SimpleNamespace(
        artifact_dir=str(tmp_path),
        json=True,
        strict=False,
        m6_11_phase2_calibration=False,
        m6_12_report=True,
        ledger=str(ledger),
        closeout_index=None,
        measurement_head=None,
    )

    assert cmd_proof_summary(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
