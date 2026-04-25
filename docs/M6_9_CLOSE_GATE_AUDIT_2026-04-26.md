# M6.9 Close-Gate Audit (2026-04-26)

Recommendation: CLOSE_READY.

Auditor task: close-gate aggregation and next-task selection only. This
document does not update source, tests, proof artifacts, or roadmap status by
itself.

Current HEAD: working tree after task `#627`
(`M6.9 repeated-task five-repetition close-gate proof`).

Inputs inspected:

- `ROADMAP.md` M6.9 Done-when criteria.
- `ROADMAP_STATUS.md` M6.9 / M6.14 evidence.
- `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`.
- `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md`.
- M6.9 dogfood scenarios in `src/mew/dogfood.py`.
- Task/session evidence for `#598`, `#599`, `#600`, `#601`, `#602`,
  `#613`, `#615`, `#617`, `#619`, and M6.14 repair tasks `#614`, `#616`,
  `#618`, `#626`.

Recent validation accepted for this audit:

- `./mew dogfood --all --json`: `status=pass`.
- `./mew dogfood --scenario m6_9-repeated-task-recall --json`:
  `status=pass`, `shape_count=10`, `recalled_file_pair_count=10`,
  five `first_five_wall_seconds`, five
  `first_five_deliberation_step_counts`, all
  `per_shape_median_improvement` entries true, and
  `reviewer_rescue_edits=0`.
- `./mew dogfood --scenario m6_9-symbol-index-hit --json`:
  `status=pass`, `index_hit=true`, `fresh_search_performed=false`.
- `./mew dogfood --scenario m6_9-reasoning-trace-recall --json`:
  `status=pass`, `recalled_count=2`, `shortened_deliberation_count=2`,
  `abstract_recall_count=1`.
- `./mew dogfood --scenario m6_9-phase2-regression --json`:
  `status=pass`, `budget_multiplier=1.0`,
  `b0_comparator_wall_seconds=4.0`, `median_wall_seconds=3.8`.
- `uv run pytest -q tests/test_dogfood.py -k 'm6_9_repeated_task_recall or scenario_choices' --no-testmon`:
  `2 passed, 90 deselected`.
- `uv run pytest -q tests/test_dogfood.py --no-testmon`:
  `92 passed, 6 subtests passed`.
- `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`:
  all checks passed.
- `git diff --check`: clean.

## Done-When Checklist

1. On a predeclared set of 10 repeated task shapes, median wall time per task
   decreases over the first five repetitions with no increase in reviewer
   rescue edits.

   Status: PASS.

   Evidence: task `#627` extended `m6_9-repeated-task-recall` to emit five
   repetitions for all 10 predeclared task shapes. The scenario records
   `first_five_wall_seconds`, `first_five_deliberation_step_counts`,
   per-shape `median_wall_seconds_improved=true`,
   `median_deliberation_step_count_improved=true`, and
   `reviewer_rescue_edits=0`. The focused selector and full dogfood test
   module both pass.

2. At least three reviewer corrections from past iterations fire as durable
   rules in later iterations, and at least one would have caused a rescue edit
   if not caught.

   Status: PASS.

   Evidence: `m6_9-reviewer-steering-reuse` now records three durable rules
   for existing-scenario artifact tweaks, unpaired source edits, and missing
   focused verifiers. The scenario records
   `simulated_rescue_edit_prevented_count=3` and passes through the dogfood
   suite.

3. At least two previously reverted approaches are blocked pre-implementation
   by durable failure-shield memory in a later iteration.

   Status: PASS.

   Evidence: `m6_9-failure-shield-reuse` blocks two previously reverted
   approaches before implementation: stale cached-window retry and generic
   cleanup substitution.

4. At least 80% of first-read file lookups in a post-Phase-1 iteration are
   served by the durable symbol/pair index rather than fresh search.

   Status: PASS_WITH_NOTE.

   Evidence: `m6_9-symbol-index-hit` proves `index_hit=true` and
   `fresh_search_performed=false` for the direct first-read source lookup.
   `m6_9-repeated-task-recall` separately proves 10/10 post-first-repetition
   task shapes resolve source/test pairs from durable recall. The remaining
   caveat is that the 10-shape aggregate uses deterministic dogfood trace
   evidence rather than a live arbitrary work-session sample.

5. Drift canary stays green across five consecutive iterations while memory
   accumulates, and at least one novel-task injection forces exploration
   without silent memory reliance.

   Status: PASS.

   Evidence: `m6_9-drift-canary` records five green iterations with
   accumulated memory and a novel-task injection that forces source/test
   exploration while recording `no_silent_memory_reliance=true`.

6. After a deliberate 48-hour gap or a simulated alignment-decay pass, mew
   recovers prior convention usage within one iteration via a rehearsal pass,
   without reviewer steering.

   Status: PASS.

   Evidence: `m6_9-alignment-decay-rehearsal` records
   `simulated_gap_or_decay=true`, `rehearsal_pass_ran=true`,
   `recovered_within_iterations=1`, and `reviewer_steering_required=false`.

7. At least two iterations explicitly recall a past reasoning trace and a
   reviewer confirms the recall shortened deliberation; at least one recall
   lands on an abstract task.

   Status: PASS.

   Evidence: `m6_9-reasoning-trace-recall` records two recalled traces, two
   reviewer-confirmed shortened deliberations, and one abstract deep recall
   for anti-polish drift.

8. The M6.6 comparator is rerun with durable recall active and shows measurable
   gain over the M6.6 baseline attributable to the new memory.

   Status: PASS_WITH_NOTE.

   Evidence: `m6_9-phase1-regression` and `m6_9-phase2-regression` reuse the
   frozen M6.6 comparator fixture with durable recall active. Phase 2 applies
   the neutral budget (`budget_multiplier=1.0`) and reports
   `median_wall_seconds=3.8` against `B0.comparator=4.0`, a measured 5%
   improvement in the deterministic fixture. The caveat is that no live
   external fresh-CLI comparator rerun has been attempted for this post-split
   close gate.

## Closure Decision

M6.9 is close-ready. All eight formal Done-when criteria are backed by
deterministic dogfood evidence, focused tests, broad dogfood tests, and the
M6.14 mew-first repair ledger for honesty around substrate repairs.

Caveats to preserve:

- Some wall-time and comparator evidence is deterministic fixture evidence,
  not a fresh external CLI rerun. This is acceptable for the M6.9 close gate
  because the phase-regression scenarios preserve the M6.6 comparator baseline
  and the audit records the evidence source explicitly.
- Several earlier M6.9 slices were supervisor-owned product progress rather
  than autonomy credit. The final M6.14 retry sequence proves mew can recover
  from substrate blockers and land later M6.9 proof slices mew-first without
  hidden product rescue.

Recommended roadmap update:

- Mark M6.9 `done`.
- Move active focus to M6.8 Task Chaining, because M6.9 Phase 4 remains gated
  on M6.8 and the next resident capability gap is supervised self-selection of
  the next bounded task.
