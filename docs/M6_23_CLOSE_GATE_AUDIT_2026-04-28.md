# M6.23 Close Gate Audit - Terminal-Bench Failure-Class Coverage

Date: 2026-04-28 JST

## Verdict

M6.23 is closed.

The milestone converted M6.22 curated-subset failures into ranked repair
classes, implemented the top-ranked generic repair, and reran the same evidence
shape. The selected repair improved `overfull-hbox` from 2/5 to 3/5 and reached
the frozen Codex target for that task.

## Done-When Evidence

- Every failed task in the curated subset has an M6.18 classification with
  cited artifacts in:
  `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`.
- At least one task from each observed failure class has a replayable evidence
  bundle or a recorded reason why it is not worth repairing yet.
- Repair candidates are ranked by expected benchmark leverage and risk.
- The top repair, grounded edit-scope acceptance evidence, was implemented in
  commit `47a3393`.
- `overfull-hbox` was rerun against the same 5-trial evidence shape:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-23-overfull-hbox-5attempts-edit-scope-grounding-20260428-0032/result.json`
- Rerun verdict: **improved**.

## Repair Delta

| Run | Result | Notes |
|---|---:|---|
| M6.22 baseline | 1/5 | `insufficient_acceptance_constraint_model` |
| M6.22 repaired wait rerun | 2/5 | all reports finished, but some acceptance evidence remained self-reported |
| M6.23 grounded edit-scope rerun | 3/5 | matches frozen Codex target for `overfull-hbox` |

M6.23 rerun details:

- trials: 5
- Harbor errors: 1 `AgentTimeoutError`
- mean: 0.600
- pass@5: 1.000
- reward `1.0`: `overfull-hbox__oKJ3xQW`,
  `overfull-hbox__qw5xNKm`, `overfull-hbox__bM36EYw`
- reward `0.0`: `overfull-hbox__g3D3Kxf`,
  `overfull-hbox__KpuMvNa`

## Validation

- `uv run pytest tests/test_acceptance.py tests/test_work_session.py::WorkSessionTests::test_work_finish_blocks_task_done_without_acceptance_checks tests/test_work_session.py::WorkSessionTests::test_work_finish_blocks_ungrounded_edit_scope_acceptance_after_write tests/test_work_session.py::WorkSessionTests::test_repairable_wait_converts_to_remember_when_continuation_allowed tests/test_work_session.py::WorkSessionTests::test_repairable_wait_does_not_convert_on_final_step -q`
- `uv run ruff check src/mew/acceptance.py src/mew/work_loop.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py`
- Harbor rerun:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-23-overfull-hbox-5attempts-edit-scope-grounding-20260428-0032/result.json`

## Caveats

- The selected repair improved the task-level score but did not eliminate all
  edit-scope failures. Two failed trials still failed `test_input_file_matches`.
- One successful-verifier trial also reported `AgentTimeoutError`. Timeout
  reporting remains a ranked follow-up class.
- M6.23 proves the repair-economy loop on one class; it does not claim broad
  Terminal-Bench parity.

## Next

Move active focus to M6.24: broad Terminal-Bench parity campaign.

