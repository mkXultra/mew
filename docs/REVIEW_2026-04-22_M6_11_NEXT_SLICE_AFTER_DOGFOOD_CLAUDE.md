# M6.11 Next Slice After Dogfood Registration — Recommendation (2026-04-22, claude)

Prior slice: `8303098 Start M6.11 dogfood close-gate scenarios`.
Outcome of prior slice: `m6_11-*` scenario enum registered with an
honest `1 implemented + 4 not_implemented` split
(`m6_11-compiler-replay` passes; `m6_11-draft-timeout`,
`m6_11-refusal-separation`, `m6_11-drafting-recovery`,
`m6_11-phase4-regression` are explicit `not_implemented`). Both
claude-ultra and codex-ultra approved that honesty contract.

## Verdict

**Option B: implement `m6_11-drafting-recovery` as the next
deterministic scenario.**

Not A (refusal separation) and not C (incidence instrumentation).

## Reasoning

### Why B is the highest-value next slice

1. **It is the only close-gate scenario that directly validates the
   two most-recent structural landings.** `9787166 Land M6.11 phase 4
   follow-status parity` and `8f48189 Land M6.11 phase 4 blocker
   recovery bridge` together deliver the invariant that resume and
   follow-status emit the same canonical `blocker_code` and
   `next_recovery_action` for the same `WorkTodo`. That invariant
   currently has no dogfood gate — it is proven only by eyeballing
   `./mew work 402 --follow-status` (see
   `docs/REVIEW_2026-04-22_M6_11_POST_PHASE4_NEXT_STEP_CLAUDE.md:16-33`
   and `...CODEX.md:13-27`).

2. **It fills a gap the prior-slice review explicitly flagged.** From
   `docs/REVIEW_2026-04-22_M6_11_DOGFOOD_SLICE_CLAUDE_REVIEW.md:125-132`:
   > "no scenario in this slice yet asserts the same `blocker_code`
   > + `next_recovery_action` across resume and follow-status for the
   > same `WorkTodo`, which is the Done-when bullet at
   > `ROADMAP.md:622-623`. Close-gate evidence for that bullet must
   > not be claimed from this slice alone."

3. **Codex named it as first-mandatory before the honesty compromise.**
   `docs/REVIEW_2026-04-22_M6_11_POST_PHASE4_NEXT_STEP_CODEX.md:42,54`
   calls `m6_11-drafting-recovery` "the first mandatory executable
   scenario in the slice" — the registration-first compromise was
   adopted to avoid misleading `#401` claims, not because the parity
   scenario itself was deprioritised.

4. **It flips coverage from 1/5 to 2/5 implemented** on the same
   close-gate register, using existing infrastructure
   (`build_work_session_resume` at `src/mew/work_session.py:4846` and
   the follow-status render path already exercise the parity logic
   end-to-end on live `#402`). No new substrate is required.

5. **It is deterministic and bounded.** A fixture derived from the
   existing `.mew/replays/work-loop/2026-04-22/session-392/` state
   shape drives both surfaces offline. Matches the proposal's
   "≤ 5 min wall time each, deterministic, JSON-reportable" contract
   (`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:107-110`).

### Why not A (refusal separation)

- Refusal is the least-frequent bucket. Current live calibration
  (`proof-summary --m6_11-phase2-calibration`) shows
  `dominant_bundle_type=work-loop-model-failure.request_timed_out`
  at `dominant_bundle_share≈0.5714`, not refusal. The refusal_rate
  ceiling is already 0.03 and live bundles have not tripped it.
- Phase 0 refusal-separation source work already landed
  (`model_returned_refusal` vs `model_returned_non_schema` are
  distinct codes in `src/mew/work_loop.py`). Unit tests already
  cover it. A dogfood wrapper is nice-to-have but does not move
  any actual close blocker.
- A can follow B as a small subsequent slice once the parity scenario
  is in place; it is not order-sensitive.

### Why not C (incidence instrumentation)

- **Premature**. The 20-slice `#399 + #401` incidence batch
  (strengthen proposal §3.2) requires implemented scenarios *and*
  bounded live slices to feed it. Building batch-analysis
  instrumentation before any slices exist risks designing against
  guessed-at data shapes.
- The measurement surface that matters **today** is the calibration
  checkpoint — already instrumented in
  `src/mew/proof_summary.py:272-305` and already red. The extra
  incidence instrumentation (strengthen proposal §7 "Iter-B") is
  explicitly scheduled "during or after Phase 3," after scenarios
  land.
- Iter-C (calibration checkpoint evaluator) is already implemented
  per `ROADMAP_STATUS.md:152-155`
  (`mew proof-summary --m6_11-phase2-calibration`). There is no
  gap C is filling that is actually blocking close *today* — the
  gap is evidence, not instrumentation.

## Exact bounded scope

**Implement `m6_11-drafting-recovery` as a deterministic
offline parity scenario. No other scenario in this slice.**

### Files to touch

- **`src/mew/dogfood.py`**
  - Replace the `run_m6_11_drafting_recovery_scenario` stub
    (`src/mew/dogfood.py:709-714`) with a deterministic
    implementation.
  - Load a new fixture directory
    `tests/fixtures/work_loop/drafting_recovery/blocker_code_parity/`
    containing a minimal `scenario.json` with: (a) a `WorkTodo` in
    `blocked_on_patch` with a populated `blocker_code` from the
    frozen `PATCH_BLOCKER_RECOVERY_ACTIONS` taxonomy, (b) the
    session/state shape required by `build_work_session_resume`,
    (c) the inputs needed by the follow-status render path.
  - Drive both surfaces on the same loaded state:
    - resume surface via `build_work_session_resume(...)` at
      `src/mew/work_session.py:4846`
    - follow-status surface via the existing follow-status JSON
      render used by `./mew work <id> --follow-status --json`
  - Emit `_scenario_check`s asserting:
    - `resume.blocker_code == follow_status.blocker_code`
    - `resume.next_recovery_action == follow_status.next_recovery_action`
    - both values equal
      `PATCH_BLOCKER_RECOVERY_ACTIONS[blocker_code]`
    - `resume.active_work_todo.id == follow_status.active_work_todo.id`
    - `follow_status.resume_source == "session_overlay"` (documents
      that the overlay path is the one being measured)
  - Report artifacts include the matched `blocker_code`,
    `next_recovery_action`, and `todo_id` so the close-gate artifact
    can cite concrete values.
- **`tests/fixtures/work_loop/drafting_recovery/blocker_code_parity/scenario.json`**
  (new) — minimum state to exercise both surfaces. Strip to the
  smallest field set both paths actually read; do not copy session
  noise. Name the directory for what it proves
  (`blocker_code_parity`), not for the live session it was derived
  from (lesson from the `402_timeout_before_draft` mislabel flagged
  in the prior review).
- **`tests/test_dogfood.py`**
  - Remove `"m6_11-drafting-recovery"` from the
    `test_run_dogfood_m6_11_not_implemented_scenarios` list
    (`tests/test_dogfood.py:548-573`).
  - Add `test_run_dogfood_m6_11_drafting_recovery_scenario` pinning
    `status=="pass"` and the four parity checks above.
  - Update `test_run_dogfood_m6_11_all_subset_aggregate_reflects_not_implemented`
    so the expected implemented set is
    `{m6_11-compiler-replay, m6_11-drafting-recovery}` and the
    expected `not_implemented` set is
    `{m6_11-draft-timeout, m6_11-refusal-separation, m6_11-phase4-regression}`.
    The aggregate still honestly fails (3 `not_implemented` remain).

### Out of scope (explicit non-goals)

- Do **not** implement `m6_11-refusal-separation`,
  `m6_11-draft-timeout`, or `m6_11-phase4-regression`. Each is its
  own subsequent bounded slice.
- Do **not** add incidence-measurement instrumentation or
  20-slice batch-analysis support. That is a later slice and
  requires more scenarios + live slices first.
- Do **not** modify `build_work_session_resume`, the follow-status
  render path, `PATCH_BLOCKER_RECOVERY_ACTIONS`, or any source
  outside `src/mew/dogfood.py`. The scenario is a reader, not a
  mutator.
- Do **not** change `latest_model_failure` suppression semantics
  (the deferred open question from
  `REVIEW_2026-04-22_M6_11_POST_PHASE4_IMPL_CLAUDE_REVIEW_4.md`
  Finding 3 remains deferred).
- Do **not** run the 20-slice incidence batch.

## Suggested validations

- `uv run pytest tests/test_dogfood.py -q -k m6_11` — the new
  parity test passes; the aggregate subset test reflects 2
  implemented / 3 not_implemented.
- `./mew dogfood m6_11-drafting-recovery --json` — exits 0,
  `status=pass`, artifacts payload includes the matched
  `blocker_code`, `next_recovery_action`, `todo_id`.
- `./mew dogfood all --json` — aggregate still `fail` (3
  `not_implemented` scenarios remain), but
  `m6_11-compiler-replay` and `m6_11-drafting-recovery` both
  report `pass`.
- `./mew proof-summary --strict` — counts 5 registered `m6_11-*`
  scenarios with a 2 pass / 3 not_implemented split.
- **Fixture-vs-live parity spot-check**: diff the `blocker_code` /
  `next_recovery_action` / `active_work_todo.id` values the
  fixture-backed scenario emits against what
  `./mew work 402 --follow-status --json` emits live today.
  Values should match exactly; if they diverge, the fixture has
  drifted from reality and needs to be regenerated rather than
  patched.
- Unchanged regressions: `uv run pytest tests/test_dogfood.py -q`
  (full dogfood suite) stays green;
  `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  shape is unchanged (this slice does not address calibration
  concentration — that is its own non-goal).

## Risks

1. **Fixture drift vs live overlay logic.** If
   `build_work_session_resume` changes shape, the fixture must be
   regenerated. Mitigation: strip the fixture to the minimum fields
   both surfaces actually read; re-run the parity spot-check when
   `build_work_session_resume` is touched.
2. **Scenario proves parity but not rarity.** Correct — that is B's
   scope. The rarity question belongs to the 20-slice incidence
   gate (the eventual C-shaped work), not to this parity scenario.
3. **Calibration concentration stays red.** True and out of scope.
   This slice targets the ROADMAP `#622-623` parity Done-when, not
   the calibration checkpoint. The calibration checkpoint needs
   more diverse replay bundles, which come from running more
   bounded live slices, which depends on the scenario harness
   being trustworthy — which this slice moves forward.
