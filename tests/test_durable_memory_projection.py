import json
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.durable_memory_projection import (
    MEMORY_PROJECTION_SECTION_ID,
    build_durable_memory_projection_dry_run,
)
from mew.typed_memory import FileMemoryBackend


def test_durable_projection_dry_run_projects_only_allowed_bounded_items():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src/foo.py").write_text("def foo(): return 1\n", encoding="utf-8")
        (root / "tests/test_foo.py").write_text("def test_foo(): pass\n", encoding="utf-8")
        backend = FileMemoryBackend(root)

        reviewer = backend.write(
            "Projection memory: keep edits scoped.",
            scope="private",
            memory_type="project",
            memory_kind="reviewer-steering",
            name="Projection scope rule",
            created_at="2026-05-20T00:00:01Z",
            approved=True,
            why="Projection reviewer correction repeated.",
            how_to_apply="Keep durable-memory edits scoped to the selected surface.",
        )
        shield = backend.write(
            "Projection memory: avoid stale proof reuse.",
            scope="private",
            memory_type="project",
            memory_kind="failure-shield",
            name="Projection stale proof shield",
            created_at="2026-05-20T00:00:02Z",
            approved=True,
            symptom="Projection reused stale proof",
            root_cause="Old artifact was accepted without current workspace verification.",
            fix="Verify the current workspace before accepting memory.",
            stop_rule="Do not trust stale projection evidence without a current check.",
        )
        pair = backend.write(
            "Projection memory: foo source pairs with foo test.",
            scope="private",
            memory_type="project",
            memory_kind="file-pair",
            name="Projection foo pair",
            created_at="2026-05-20T00:00:03Z",
            source_path="src/foo.py",
            test_path="tests/test_foo.py",
            structural_evidence="Projection same-session source/test review.",
            focused_test_green=True,
        )
        template = backend.write(
            "Projection memory: task template should stay sidecar-only.",
            scope="private",
            memory_type="project",
            memory_kind="task-template",
            name="Projection template",
            created_at="2026-05-20T00:00:04Z",
            approved=True,
            rationale="Projection templates can become live planners.",
        )
        trace = backend.write(
            "Projection memory: reasoning traces should not be projected.",
            scope="private",
            memory_type="project",
            memory_kind="reasoning-trace",
            name="Projection trace",
            created_at="2026-05-20T00:00:05Z",
            approved=True,
            situation="Projection thought retrieval",
            reasoning="Raw reasoning is not provider-visible memory.",
            verdict="Distill facts instead of injecting traces.",
            abstraction_level="shallow",
        )

        report = build_durable_memory_projection_dry_run(query="projection", base_dir=root)

    assert report["section_id"] == MEMORY_PROJECTION_SECTION_ID
    assert report["projection_allowed"] is False
    assert report["candidate_projection_chars"] <= 1200
    assert len(json.dumps(report["candidate_projection_items"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))) <= 1200
    assert report["provider_visible_forbidden_fields"]["status"] == "passed"
    assert set(report["projected_entry_ids"]).issubset({reviewer.id, shield.id, pair.id})
    assert report["projected_entry_ids"]
    dropped = {item["id"]: item["drop_reason"] for item in report["dropped_entry_ids_with_reason"]}
    assert dropped[template.id] == "hidden_answer_risk"
    assert dropped[trace.id] == "hidden_answer_risk"


def test_durable_projection_dry_run_rejects_missing_file_pair_path():
    with tempfile.TemporaryDirectory() as tmp:
        backend = FileMemoryBackend(tmp)
        entry = backend.write(
            "Projection missing file-pair memory.",
            scope="private",
            memory_type="project",
            memory_kind="file-pair",
            name="Missing projection pair",
            source_path="src/missing.py",
            test_path="tests/test_missing.py",
            structural_evidence="same-session source/test review",
            focused_test_green=True,
        )

        report = build_durable_memory_projection_dry_run(query="projection", base_dir=tmp)

    assert report["projected_entry_ids"] == []
    assert report["dropped_entry_ids_with_reason"] == [
        {
            "id": entry.id,
            "kind": "file-pair",
            "drop_reason": "precondition_miss",
        }
    ]


def test_durable_projection_dry_run_budget_drop_has_single_revise_result():
    with tempfile.TemporaryDirectory() as tmp:
        backend = FileMemoryBackend(tmp)
        entry = backend.write(
            "Projection memory: keep reviewer rules compact.",
            scope="private",
            memory_type="project",
            memory_kind="reviewer-steering",
            name="Budgeted projection rule",
            approved=True,
            why="Projection budget test.",
            how_to_apply="Keep projected rules compact enough for the provider-visible budget.",
        )

        report = build_durable_memory_projection_dry_run(query="projection", base_dir=tmp, max_chars=10)

    assert report["projected_entry_ids"] == []
    assert report["dropped_entry_ids_with_reason"] == [
        {
            "id": entry.id,
            "kind": "reviewer-steering",
            "drop_reason": "projection_budget_exceeded",
        }
    ]
    assert [item["status"] for item in report["revise_gate_results"]] == ["dropped"]


def test_durable_projection_dry_run_enforces_hard_item_cap():
    with tempfile.TemporaryDirectory() as tmp:
        backend = FileMemoryBackend(tmp)
        ids = []
        for index in range(4):
            entry = backend.write(
                f"Projection memory {index}: keep reviewer rules compact.",
                scope="private",
                memory_type="project",
                memory_kind="reviewer-steering",
                name=f"Hard cap projection rule {index}",
                approved=True,
                why="Projection hard cap test.",
                how_to_apply=f"Keep projected rule {index} concise.",
            )
            ids.append(entry.id)

        report = build_durable_memory_projection_dry_run(
            query="projection",
            base_dir=tmp,
            max_items=4,
        )

    assert len(report["projected_entry_ids"]) <= 3
    assert len(report["projected_entry_ids"]) < 4
    assert set(report["projected_entry_ids"]).issubset(ids)
    assert {item["drop_reason"] for item in report["dropped_entry_ids_with_reason"]} == {
        "projection_budget_exceeded"
    }


def test_durable_projection_dry_run_forbidden_name_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        backend = FileMemoryBackend(tmp)
        entry = backend.write(
            "Projection memory: keep reviewer rules compact.",
            scope="private",
            memory_type="project",
            memory_kind="reviewer-steering",
            name="next_action projection rule",
            approved=True,
            why="Projection forbidden scan test.",
            how_to_apply="Keep projected rules concise.",
        )

        report = build_durable_memory_projection_dry_run(query="projection", base_dir=tmp)

    assert report["projected_entry_ids"] == []
    assert report["candidate_projection_items"] == []
    assert report["dropped_entry_ids_with_reason"] == [
        {
            "id": entry.id,
            "kind": "reviewer-steering",
            "drop_reason": "forbidden_content",
        }
    ]


def test_durable_projection_dry_run_reports_vetoed_entries_as_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        backend = FileMemoryBackend(tmp)
        entry = backend.write(
            "Projection memory: vetoed rule.",
            scope="private",
            memory_type="project",
            memory_kind="reviewer-steering",
            name="Veto projection rule",
            approved=True,
            why="Projection veto test.",
            how_to_apply="Do not project vetoed memory.",
        )
        backend.veto(entry.id, reason="obsolete")

        report = build_durable_memory_projection_dry_run(query="projection", base_dir=tmp)

    assert report["projected_entry_ids"] == []
    assert report["dropped_entry_ids_with_reason"] == [
        {
            "id": entry.id,
            "kind": "reviewer-steering",
            "drop_reason": "vetoed",
        }
    ]


def test_cli_memory_projection_dry_run_json():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            backend = FileMemoryBackend(".")
            entry = backend.write(
                "Projection memory: keep CLI output small.",
                scope="private",
                memory_type="project",
                memory_kind="reviewer-steering",
                name="CLI projection rule",
                approved=True,
                why="Projection CLI output must be reviewable.",
                how_to_apply="Keep projected memory output concise.",
            )

            with redirect_stdout(StringIO()) as stdout:
                assert main(["memory", "--projection-dry-run", "projection", "--json"]) == 0

            payload = json.loads(stdout.getvalue())
            assert payload["projected_entry_ids"] == [entry.id]
            assert payload["projection_allowed"] is False
        finally:
            os.chdir(old_cwd)
