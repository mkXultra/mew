# M6.9 Close-Gate Audit (2026-04-26)

Recommendation: NOT_CLOSE_READY_ONE_GAP.

Auditor task: close-gate aggregation and next-task selection only. This
document does not update source, tests, proof artifacts, or roadmap status by
itself.

Current HEAD: `cc12c89`
(`Add M6.9 phase2 comparator dogfood`).

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
  per-shape recall count `1`, and `reviewer_rescue_edits=0`.
- `./mew dogfood --scenario m6_9-symbol-index-hit --json`:
  `status=pass`, `index_hit=true`, `fresh_search_performed=false`.
- `./mew dogfood --scenario m6_9-reasoning-trace-recall --json`:
  `status=pass`, `recalled_count=2`, `shortened_deliberation_count=2`,
  `abstract_recall_count=1`.
- `./mew dogfood --scenario m6_9-phase2-regression --json`:
  `status=pass`, `budget_multiplier=1.0`,
  `b0_comparator_wall_seconds=4.0`, `median_wall_seconds=3.8`.
- `uv run pytest -q tests/test_dogfood.py --no-testmon`:
  `92 passed, 6 subtests passed`.
- `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`:
  all checks passed.
- `git diff --check`: clean.

## Done-When Checklist

1. On a predeclared set of 10 repeated task shapes, median wall time per task
   decreases over the first five repetitions with no increase in reviewer
   rescue edits.

   Status: PARTIAL.

   Evidence: `m6_9-repeated-task-recall` covers 10 task shapes and proves a
   first-to-second repetition improvement: fresh discovery records four
   deliberation search steps, durable recall records two, and
   `reviewer_rescue_edits=0` for all shapes. This is strong durable-recall
   signal, but the current scenario has only two repetitions and reports
   deliberation-step reduction rather than first-five median wall-time
   reduction. The formal gate should not be closed on this evidence alone.

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

M6.9 is very close, but should not close yet. Seven of eight criteria are
passing or pass-with-note; criterion 1 is the only formal gap. The gap is not a
new architecture problem. It is a proof-shape mismatch: the repeated-task
scenario proves 10-shape durable recall and no rescue edits, but not
first-five median wall-time reduction.

Next bounded task:

- Extend `m6_9-repeated-task-recall` or add a sibling close-gate dogfood
  scenario that records five repetitions for the 10 predeclared task shapes,
  emits per-shape first-five `wall_seconds` / `deliberation_step_count`
  evidence, asserts median improvement, and preserves `reviewer_rescue_edits=0`.

After that task lands and `dogfood --all`, focused tests, ruff, and
`git diff --check` are green, write a short close addendum or update this
audit to `CLOSE_READY` and close M6.9 in `ROADMAP_STATUS.md`.
