# M6.22 Close Gate Audit - Terminal-Bench Curated Subset Parity

Date: 2026-04-28 JST

## Verdict

M6.22 is closed.

The curated subset did not reach Codex aggregate parity: mew scored **17/35**
against the frozen Codex target **20/35**. The milestone is still closeable
because the Done-when allowed an explicit below-target gap table with M6.18
classifications and required at least one below-target task to be repaired and
rerun. That proof is now present.

## Done-When Evidence

- Curated manifest exists:
  `docs/M6_22_CURATED_SUBSET_MANIFEST_2026-04-27.md`.
- Local subset JSON exists:
  `docs/data/terminal_bench_m6_22_curated_subset.json`.
- Run ledger exists:
  `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`.
- Mew has 5-trial results for every selected task:
  - `filter-js-from-html`: 0/5, Codex target 0/5
  - `sanitize-git-repo`: 1/5, Codex target 1/5
  - `gcode-to-text`: 0/5, Codex target 2/5
  - `overfull-hbox`: baseline 1/5, Codex target 3/5
  - `extract-elf`: 5/5, Codex target 4/5
  - `cancel-async-tasks`: 5/5, Codex target 5/5
  - `fix-code-vulnerability`: 5/5, Codex target 5/5
- Below-target tasks were classified through M6.18:
  - `gcode-to-text`: structural,
    `missing_visual_decode_artifact_grounding`
  - `overfull-hbox`: structural,
    `insufficient_acceptance_constraint_model`
- Selected repair route was implemented and rerun:
  - `29335c9` added work acceptance checks.
  - First rerun regressed to 0/5 because repairable blockers terminated as
    `wait`.
  - `2d0b5c4` converted repairable waits to continuity notes while budget
    remains.
  - Second rerun reached 2/5, improving over the 1/5 baseline while leaving a
    residual below-target gap.

## Validation

- `uv run pytest tests/test_acceptance.py tests/test_work_session.py::WorkSessionTests::test_work_finish_block_keeps_session_open_for_proof_or_revert_gates tests/test_work_session.py::WorkSessionTests::test_work_finish_blocks_task_done_without_acceptance_checks tests/test_work_session.py::WorkSessionTests::test_repairable_wait_converts_to_remember_when_continuation_allowed tests/test_work_session.py::WorkSessionTests::test_repairable_wait_does_not_convert_on_final_step tests/test_work_session.py::WorkSessionTests::test_work_finish_allows_completed_same_surface_audit -q`
- `uv run ruff check src/mew/acceptance.py src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py`
- Harbor rerun:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-repairable-wait-20260428-0007/result.json`

## Caveats

- Mew is still below the curated Codex aggregate target by 3 successes.
- The acceptance-check repair improved `overfull-hbox` but did not fully solve
  it. Three failed rerun trials still self-reported verified edit-scope
  acceptance while the external verifier rejected `input.tex`.
- `gcode-to-text` remains below target and should not be repaired from one
  anecdote. It belongs in M6.23 failure-class ranking.

## Next

Move active focus to M6.23. The first M6.23 job is to rank failure classes from
the curated subset, including:

- `self_reported_acceptance_evidence_not_grounded_in_diff_validator`
- `missing_visual_decode_artifact_grounding`
- `agent_wall_timeout_without_report`
