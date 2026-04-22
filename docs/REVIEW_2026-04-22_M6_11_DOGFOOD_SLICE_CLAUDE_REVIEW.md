# M6.11 Dogfood Scenario Slice Review (2026-04-22, claude)

Scope: working-tree diff for `src/mew/dogfood.py` + `tests/test_dogfood.py`
plus the new fixture `tests/fixtures/work_loop/recovery/402_timeout_before_draft/`.
Focus: correctness, milestone semantics, close-gate-evidence honesty,
implemented-vs-not_implemented separation.

## Verdict

**Revise.**

The registration shape and not_implemented handling are honest: the five
`m6_11-*` names are added to `DOGFOOD_SCENARIOS`, the aggregate status at
`src/mew/dogfood.py:10591` correctly fails when any scenario reports
`not_implemented`, the three deferred scenarios surface an explicit
`scenario_implementation_status=false` check, and `test_run_dogfood_m6_11_not_implemented_scenarios`
pins the failing-aggregate contract. `m6_11-compiler-replay` is solid
offline evidence for `#399`-shaped buckets.

But `m6_11-draft-timeout` as written is misleading close-gate evidence
for `#401`. That is the one class of failure this slice was told to
avoid, so it blocks approve.

## Findings

### 1. HIGH — `m6_11-draft-timeout` does not exercise a `#401` draft timeout; it re-replays a `#399`-shaped compiler blocker

- **file:line** `src/mew/dogfood.py:520-607`, fixture `tests/fixtures/work_loop/recovery/402_timeout_before_draft/scenario.json:25-86`
- **issue** The fixture's session trace is a *completed* tiny-lane model
  turn whose `action_plan` already carries
  `blocker.code=stale_cached_window_text` and whose compiler artifact
  kind is `patch_blocker`. There is no timeout signal
  (`tiny_write_ready_draft_fallback_reason=timeout`, an interrupted
  turn, a `request timed out` trace, etc.) — it is simply a compiler
  blocker surfaced through the resume view. Despite that, the scenario
  is named `m6_11-draft-timeout`, the fixture is named
  `402_timeout_before_draft`, and the scenario is the one the ROADMAP
  and the strengthen proposal both tie to `#401` coverage
  (`ROADMAP.md:618-619`, `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:90-93`).
- **why it matters** The Done-when line for `#401` is explicit:
  "recovery preserves the same drafting frontier via
  `resume_draft_from_cached_windows` instead of generic `replan`"
  (`ROADMAP.md:618-619`). `resume_draft_from_cached_windows` does not
  exist in source (`rg 'resume_draft_from_cached_windows' src/ tests/`
  returns nothing — it is referenced only in design docs). A future
  close-gate reader who sees `m6_11-draft-timeout: pass` will treat
  that Done-when bullet as satisfied when the scenario never
  exercises a draft-timeout path at all, and the action it asserts
  (`refresh_cached_window`) is the `#399` recovery vocabulary, not the
  `#401` one. This is exactly the "replayable, not rarer" close-gate
  dishonesty the slice is meant to guard against.
- **concrete fix** Pick one:
  - Mark `m6_11-draft-timeout` `not_implemented` (same shape as
    `m6_11-drafting-recovery`) with reason
    `"#401 timeout-before-draft recovery awaits resume_draft_from_cached_windows landing"`,
    and either rename the fixture + scenario pair that is actually
    landing (`m6_11-compiler-blocker-resume` or fold it into
    `m6_11-compiler-replay` as a resume-surface sub-check), or
  - Regenerate the fixture so the session trace models a genuine
    pre-draft timeout (e.g. an interrupted turn with
    `tiny_write_ready_draft_fallback_reason=timeout`, no
    `patch_blocker` artifact yet, `active_work_todo` still in
    `drafting`), and defer the recovery-vocabulary assertion until
    `resume_draft_from_cached_windows` lands per Phase 4 §8 of
    `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`.

### 2. MEDIUM — recovery-plan assertion is too weak to detect regression toward the `#401` close gate

- **file:line** `src/mew/dogfood.py:572-591`
- **issue** The check `m6_11_draft_timeout_recovery_plan_first_item_not_replan`
  passes when the first item's action is anything other than
  `"replan"`. Today that means `"needs_user_review"` satisfies it.
  The paired check `m6_11_draft_timeout_canonical_action_refresh_cached_window`
  then pins the blocker-level vocabulary to `refresh_cached_window`.
  Neither check is the positive assertion the ROADMAP requires
  (`resume_draft_from_cached_windows` at the recovery-plan level).
- **why it matters** "Not `replan`" is the weakest shape of the
  requirement. A regression that swapped `needs_user_review` for, say,
  `resume_with_stale_window` would still pass both checks, while a
  correct future landing of `resume_draft_from_cached_windows` would
  flip the canonical-action check to red because it is pinned to the
  pre-Phase-4 vocabulary. The scenario is currently set up to red when
  the milestone actually ships, and green while the real gap persists.
- **concrete fix** Pair with finding #1. If the scenario stays, assert
  the positive action name the milestone is supposed to deliver
  (`first_recovery_item_action == "resume_draft_from_cached_windows"`)
  and let it stay red until that action exists; if the scenario is
  downgraded to `not_implemented`, drop these two checks.

### 3. LOW — `scenario_loaded` check's observed value contradicts its predicate

- **file:line** `src/mew/dogfood.py:484-490`
- **issue** The check passes on
  `bool(scenario.get("todo")) and bool(scenario.get("model_output"))`
  but reports `observed=bool(scenario.get("name") == fixture_dir.name)`.
  A fixture whose `name` field matches the directory but lacks `todo`
  or `model_output` would fail the check while reporting
  `observed=True`, which inverts what a debugger should see.
- **why it matters** Not load-bearing for this slice (all three
  fixtures load fine), but this is scaffolding for future `m6_11-*`
  fixtures; the first time the check fails it will actively mislead
  the person triaging.
- **concrete fix**
  `observed={"has_todo": bool(scenario.get("todo")), "has_model_output": bool(scenario.get("model_output"))}`.

### 4. LOW — fixture directory name overstates what the fixture models

- **file:line** `tests/fixtures/work_loop/recovery/402_timeout_before_draft/scenario.json:1-3`
- **issue** `402_timeout_before_draft` reads as "a timeout that fired
  before the draft completed," but the JSON describes a
  post-compilation `patch_blocker` state. This is the same root concern
  as finding #1, surfaced at the fixture level so it is flagged even
  if the scenario wiring changes.
- **why it matters** Fixture directories are the nouns someone
  grepping for `#401` evidence will land on. A mislabeled fixture
  plants a tripwire for later reviewers and for the close artifact.
- **concrete fix** Rename to describe what the fixture actually
  contains (e.g. `402_blocked_on_patch_stale_window_resume/`) and
  reserve `*_timeout_before_draft` for a fixture that models that
  shape.

## Residual risks

- Once finding #1 is addressed, the slice still leaves
  `m6_11-drafting-recovery` (the parity scenario Codex flagged as the
  first-mandatory one) as `not_implemented`. That is consistent with
  the scoped-slice framing and with the aggregate failing; it is not a
  defect in this diff, but it does mean **no scenario in this slice
  yet asserts the same `blocker_code` + `next_recovery_action` across
  resume and follow-status for the same `WorkTodo`**, which is the
  Done-when bullet at `ROADMAP.md:622-623`. Close-gate evidence for
  that bullet must not be claimed from this slice alone.
- `m6_11-compiler-replay` is honest for `#399`-shaped recovery but
  only exercises three fixtures all from
  `tests/fixtures/work_loop/patch_draft/`. If a new fixture is added
  there for a different deliverable, it will be silently folded into
  `m6_11-compiler-replay` with no scenario-side opt-in. Acceptable for
  now, but worth an allow-list if more buckets get added.
- The compiler-replay scenario's per-fixture checks tolerate missing
  `file_count` / `file_kinds` / `diff_contains` / `detail_contains`
  / `path` keys (wrapped in `if "…" in expected`). If a future fixture
  omits all optional keys, the scenario passes on `kind` alone. Same
  note as above — acceptable now, but consider requiring at least one
  shape assertion per fixture.

## Suggested validation additions

- Add a dogfood-level test that runs `run_dogfood_scenario` with
  `scenario="all"` across just the `m6_11-*` names and asserts the
  aggregate `report["status"]` is `"fail"` while the two implemented
  scenarios' sub-reports are `"pass"`. The current per-scenario tests
  cover each name in isolation, but the all-run is the shape the
  close-gate artifact will cite, and it should be pinned explicitly.
- Once finding #1 is resolved, add a negative test that swaps the
  fixture's `blocker.code` to something `resume_draft_from_cached_windows`
  does not map to (or swaps `recovery_action` away from the expected
  value) and asserts the scenario reports `fail`. This prevents the
  "weak assertion" regression from recurring.
- Consider a smoke test that fails if any string in
  `DOGFOOD_SCENARIOS` starting with `m6_11-` lacks a dispatch arm in
  `run_dogfood_scenario`; currently adding a name without a handler
  raises `ValueError` only at runtime for that specific scenario.
