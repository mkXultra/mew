# M6.23 Failure-Class Coverage

Date: 2026-04-28 JST

## Scope

This document converts the M6.22 curated-subset failures into repair classes.
It is not a task-solver plan. Any repair selected here must improve the generic
`mew work --oneshot` / work-session implementation lane for arbitrary
workspace roots.

Primary evidence:

- `docs/M6_22_CURATED_SUBSET_MANIFEST_2026-04-27.md`
- `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`
- `docs/M6_22_CLOSE_GATE_AUDIT_2026-04-28.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-repairable-wait-20260428-0007/result.json`

## Observed Failure Classes

| Class | M6.18 class | Evidence | Leverage | Risk | Status |
|---|---|---|---:|---:|---|
| `self_reported_acceptance_evidence_not_grounded_in_diff_validator` | structural | `overfull-hbox` repair rerun reached 2/5, but three failed trials self-reported verified edit-scope acceptance while the external verifier rejected `input.tex`. | high | medium | selected first |
| `missing_visual_decode_artifact_grounding` | structural | `gcode-to-text` scored 0/5 vs Codex target 2/5. The agent lacked a reliable artifact-readback path for visual/G-code output. | medium-high | high | deferred |
| `agent_wall_timeout_without_report` | structural secondary | One `gcode-to-text` trial ended in `AgentTimeoutError` without a useful terminal report. | medium | medium | deferred |
| `repairable_constraint_blocker_terminal_wait` | structural | First `overfull-hbox` acceptance-check rerun regressed to 0/5 because repairable constraint blockers stopped as `wait`. | medium | low | repaired by `2d0b5c4` |
| `verifier_timeout_no_edit` | transient/verifier | `filter-js-from-html` had 5 `VerifierTimeoutError` results, but Codex target is also 0/5. | low | medium | classify only |
| `shell_quoting_multiline_command` | polish | `sanitize-git-repo` failed trials included malformed shell quoting, but mew matched the 1/5 Codex target. | low-medium | low | defer until repeated |

## Replay Evidence Bundles

| Class | Replayability | Bundle |
|---|---|---|
| `self_reported_acceptance_evidence_not_grounded_in_diff_validator` | replayable | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-repairable-wait-20260428-0007/` |
| `missing_visual_decode_artifact_grounding` | replayable | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json` |
| `agent_wall_timeout_without_report` | replayable as part of the same `gcode-to-text` run | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json` |
| `repairable_constraint_blocker_terminal_wait` | replayable; already repaired | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-acceptance-checks-20260427-2349/result.json` |
| `verifier_timeout_no_edit` | replayable, but not useful for a mew-core repair yet | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json` |
| `shell_quoting_multiline_command` | replayable | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-sanitize-git-repo-5attempts-20260427-2245/result.json` |

## Ranked Repair Candidates

1. **Grounded edit-scope acceptance validator**

   Require edit-scope acceptance claims to cite grounded evidence from a
   validator-style command or final-file/diff inspection, not only the agent's
   write history. This targets the remaining `overfull-hbox` gap without adding
   a benchmark-specific solver.

2. **Artifact readback confidence gate**

   Add a generic readback path for tasks whose correctness depends on generated
   binary, visual, or encoded artifacts. This targets `gcode-to-text`, but risk
   is higher because the correct generic shape is less clear.

3. **Timeout report flushing**

   Ensure long-running work writes a useful partial report before wall-time
   expiry. This is cross-cutting, but the current evidence is secondary rather
   than the dominant failure.

4. **Multiline shell quoting guard**

   Detect high-risk inline multiline shell fragments and encourage file-backed
   scripts or safer command construction. Defer until it repeats on below-target
   tasks.

5. **Verifier-timeout classification only**

   Keep `filter-js-from-html` in the evidence set but do not spend core repair
   budget while Codex target is also 0/5.

## Selected First Repair

M6.23 selects **grounded edit-scope acceptance validator** as the first repair.

Rationale:

- It attacks the largest known residual gap after the M6.22 repair.
- It is generic: normal coding tasks also contain "only edit X", "do not touch
  Y", "must preserve Z", and similar constraints.
- It improves the implementation lane's ability to distinguish "I believe my
  edit followed the rule" from "I have grounded evidence that the final state
  follows the rule".
- It is less speculative than visual-artifact readback.

Done for this repair when:

- the work-session finish blocker or prompt contract rejects edit-scope
  acceptance checks that rely only on self-reported write history;
- tests cover the stricter rule without affecting non-edit-scope constraints;
- `overfull-hbox` is rerun against the same evidence and marked improved,
  unchanged, or regressed.

## Repair Result

Implemented by commit `47a3393`.

Local validation:

- `uv run pytest tests/test_acceptance.py tests/test_work_session.py::WorkSessionTests::test_work_finish_blocks_task_done_without_acceptance_checks tests/test_work_session.py::WorkSessionTests::test_work_finish_blocks_ungrounded_edit_scope_acceptance_after_write tests/test_work_session.py::WorkSessionTests::test_repairable_wait_converts_to_remember_when_continuation_allowed tests/test_work_session.py::WorkSessionTests::test_repairable_wait_does_not_convert_on_final_step -q`
- `uv run ruff check src/mew/acceptance.py src/mew/work_loop.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py`

Rerun artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-23-overfull-hbox-5attempts-edit-scope-grounding-20260428-0032/result.json`

Rerun result:

- trials: 5
- Harbor errors: 1 `AgentTimeoutError`
- mean: 0.600
- pass@5: 1.000
- reward `1.0`: `overfull-hbox__oKJ3xQW`,
  `overfull-hbox__qw5xNKm`, `overfull-hbox__bM36EYw`
- reward `0.0`: `overfull-hbox__g3D3Kxf`,
  `overfull-hbox__KpuMvNa`

Verdict: **improved**.

Comparison:

- M6.22 baseline: 1/5
- M6.22 acceptance-check repair after repairable wait fix: 2/5
- M6.23 grounded edit-scope evidence repair: 3/5
- frozen Codex target for `overfull-hbox`: 3/5

Caveat:

- The run still has one `AgentTimeoutError`, even though that trial's external
  verifier passed. Keep timeout reporting as a later repair class rather than
  treating this repair as a complete loop-stability fix.
- Two failed trials still failed `test_input_file_matches`; the edit-scope
  grounding repair improved the aggregate but did not eliminate the class.
