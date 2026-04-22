# M6.11 Post-Phase-4 Next Step — Recommendation (2026-04-22, claude)

## Verdict

**Option (A): start close-gate evidence collection, beginning with
dogfood scenario registration.**

Do *not* cut another operator-surface slice for `latest_model_failure`
yet. The roadmap's stated trigger for option (B) is "stale-timeout
`latest_model_failure` obscuring blocker-backed recovery despite
`resume_source=session_overlay`." Live `#402` evidence shows the
trigger does not fire.

## Grounding evidence

Current live `./mew work 402 --follow-status` output (HEAD `9787166`):

```
resume_source: session_overlay
phase: blocked_on_patch
latest_model_failure: turn=1826 status=failed source=session
  summary=model turn failed: request timed out
latest_model_failure_metrics: ... draft_attempts=10 ...
next_action: inspect the active patch blocker and refresh the exact
  cached windows or todo source before retrying
active_work_todo: id=todo-392-1 status=blocked_on_patch draft_attempts=13
next_recovery_action: refresh_cached_window
recovery: needs_human_review
recovery_command: ./mew work 402 --session --resume --allow-read .
  --auto-recover-safe
continuity: 9/9 status=strong
```

Key facts:

1. `latest_model_failure.source == "session"`, not `"snapshot"`.
   Turn 1826 is a real tiny-lane turn that actually timed out inside
   the live session. This is not a stale snapshot remnant the overlay
   fix is meant to supersede — it is a current, truthful fact about
   the session's history. Suppressing it would hide genuine signal.
2. Every blocker-backed recovery field is populated and operator-
   actionable: `phase`, `active_work_todo`, `next_action`,
   `next_recovery_action`, `recovery_command`, `continuity`. Follow-
   status is authoritative.
3. The trigger condition for a second operator-surface slice is
   "obscuring blocker-backed recovery." That obscuration does not
   occur here: the failure line is one line among many, and the
   actionable state (blocked_on_patch + refresh_cached_window +
   recovery_command) is fully visible.

Calibration status: concentration gate still failing at `0.5714`
across 14 bundles (dominant `work-loop-model-failure.request_timed_out`
> the 40% ceiling). This is the real blocker for close-gate proof,
not operator surface polish.

Missing close-gate artifacts (from
`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` and
`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:903-907`):

- None of the required five `m6_11-*` scenarios is registered in
  `src/mew/dogfood.py` (`DOGFOOD_SCENARIOS` at line 44 only lists
  `m2-*`, `m3-*`, `m4-*`, `m5-*`, `m6-*` names through
  `m6-daemon-loop`).
- The 20-slice `#399 + #401` incidence batch has not been run.
- No `docs/M6_11_CLOSE_GATE_*.md` artifact yet.

## Reasoning

The Phase 4 work delivered its intended invariant: when tiny-lane
persists a clean blocker, resume and follow-status both surface the
canonical `blocker_code` and `next_recovery_action` derived from the
frozen `PATCH_BLOCKER_RECOVERY_ACTIONS` taxonomy. The remaining gap
is measurement, not surface.

Option (B) would be premature because:

- The visible `latest_model_failure` line reflects a real live failure
  (turn 1826), not the `source="snapshot"` staleness the overlay fix
  was designed to fix. Either suppressing or de-emphasising it hides
  a real data point that operators need when 13 draft attempts have
  already accumulated without landing an apply.
- Any adjustment would be cosmetic. It would not move the concentration
  gate (`0.5714 → ≤0.40`), the off-schema rate, or the incidence rate —
  all of which are what actually blocks close.
- Pulling forward another surface slice delays the moment the
  calibration gate can be re-measured against the new Phase 4 drafting
  path.

Option (A) directly exercises the new Phase 4 surface and produces
the artifacts close-gate requires.

## Proposed bounded slice

**Register the five `m6_11-*` dogfood scenarios in
`src/mew/dogfood.py`, land handler stubs for all five, and implement
the two fully-offline scenarios (`m6_11-compiler-replay`,
`m6_11-draft-timeout`) against existing fixtures.** Leave the other
three scenarios as stubs that return a `"not_implemented"` JSON
report so `./mew dogfood m6_11-<name>` does not 404, but no
regression suite depends on them yet.

Why this cut and not something larger:

- Registration and two offline scenarios fit the "≤5 min wall time
  each, deterministic, JSON-reportable" discipline the proposal
  requires.
- `m6_11-compiler-replay` can reuse the three fixtures that already
  exist under `tests/fixtures/work_loop/patch_draft/`
  (`paired_src_test_happy`, `ambiguous_old_text_match`,
  `stale_cached_window_text`). No new fixtures required.
- `m6_11-draft-timeout` can reuse the existing `#402` replay bundles
  under `.mew/replays/work-loop/2026-04-22/session-392/` as a
  data-driven fixture, asserting that the `WorkTodo` survives and
  that `next_recovery_action` is `refresh_cached_window`.
- The three remaining scenarios (`m6_11-refusal-separation`,
  `m6_11-drafting-recovery`, `m6_11-phase4-regression`) need fresh
  fixtures or live infrastructure and should each be their own
  subsequent slice. Registering them as `not_implemented` now still
  delivers the "dogfood scenario enum coverage" signal that downstream
  tooling (e.g. `proof-summary`) can count.

### Files to touch

- `src/mew/dogfood.py`
  - Append five names to `DOGFOOD_SCENARIOS` (line 44): `m6_11-compiler-replay`,
    `m6_11-draft-timeout`, `m6_11-refusal-separation`,
    `m6_11-drafting-recovery`, `m6_11-phase4-regression`.
  - Add five handler functions, e.g. `dogfood_m6_11_compiler_replay`,
    each returning a dict matching the existing scenario shape used
    by `format_dogfood_scenario_report` / `summarize_dogfood_scenario_json`.
  - Extend the dispatch block at `run_dogfood_scenario` (line 10177)
    with five new `elif name == "m6_11-…"` branches.
  - Implement `dogfood_m6_11_compiler_replay` by iterating the
    fixtures under `tests/fixtures/work_loop/patch_draft/` and
    driving `PatchDraftCompiler` against each. Assert blocker code
    matches the fixture's `expected_blocker.json` (or happy-path
    validated artifact) and that no same-surface reread is emitted.
  - Implement `dogfood_m6_11_draft_timeout` by loading a saved live
    `#402` tiny-lane-timeout bundle from `.mew/replays/work-loop/…`,
    running it through `build_work_session_resume`, and asserting
    `active_work_todo.status == "blocked_on_patch"`,
    `next_recovery_action == "refresh_cached_window"`, and
    `recovery_plan.items[0].action` is not `replan`.
  - The other three handlers return
    `{"status": "not_implemented", "reason": "pending implementation slice"}`
    with `exit_code=0` when `--allow-unimplemented` is passed, else
    `exit_code=2`. Default is strict.
- `tests/test_dogfood.py` (or whichever test file currently locks in
  `DOGFOOD_SCENARIOS` membership) — extend the "all scenarios
  registered" assertion to include the five new names.

No changes to `src/mew/commands.py`, `src/mew/work_session.py`,
`src/mew/work_loop.py`, `src/mew/patch_draft.py`, or
`src/mew/proof_summary.py`.

### Focused validation

- `uv run pytest tests/test_dogfood.py -q` — new registration
  assertions pass.
- `./mew dogfood m6_11-compiler-replay --json` — exits 0 with a JSON
  report that includes `scenario=m6_11-compiler-replay`, per-fixture
  results, and `status=pass`.
- `./mew dogfood m6_11-draft-timeout --json` — exits 0 with a JSON
  report asserting the blocker-backed surface invariants named
  above.
- `./mew dogfood m6_11-refusal-separation --json`,
  `m6_11-drafting-recovery --json`, `m6_11-phase4-regression --json`
  — each exits 2 by default (`not_implemented`), exits 0 with
  `--allow-unimplemented`. JSON report carries the scenario name so
  `proof-summary` can enumerate coverage.
- `./mew proof-summary --strict` — counts 5 `m6_11-*` scenarios
  registered and surfaces the 2 pass / 3 not_implemented split.

### Non-goals

- Do not change `latest_model_failure` rendering or suppression logic
  (this is the explicitly deferred open question from
  `REVIEW_2026-04-22_M6_11_POST_PHASE4_IMPL_CLAUDE_REVIEW_4.md`
  Finding 3; it is not the bottleneck).
- Do not implement `m6_11-refusal-separation`,
  `m6_11-drafting-recovery`, or `m6_11-phase4-regression` in this
  slice. Register + stub only.
- Do not run the 20-slice `#399/#401` incidence batch yet. That
  depends on the scenario harness landing first.
- Do not touch the write/apply/verify flow or the tiny-lane prompt.

## Risks

1. **Scenario surface drift.** Implementing two deterministic
   scenarios uses fixtures whose shape might shift if later Phase
   4 tightening alters the compiler output. Mitigation: pin fixture
   hashes in the handler and re-generate if the validator_version
   bumps.
2. **Replay bundle reuse.** `dogfood_m6_11_draft_timeout` leans on
   `.mew/replays/work-loop/2026-04-22/session-392/` — those bundles
   are under `.mew/` and currently ignored by the repo. For
   determinism the scenario should copy the minimum bundle fields
   into `tests/fixtures/work_loop/recovery/402_timeout_before_draft/`
   rather than reading from a session-local replay root. Small
   additional file touch but keeps the scenario reproducible off a
   fresh clone.
3. **Calibration expectations.** Registration alone will not lower
   the concentration gate. That requires subsequent bounded live
   slicing. The 20-slice batch is a separate follow-up slice; this
   one only delivers the harness.

## Open question (noted but not blocking)

`latest_model_failure` semantics when overlay fires but the live
session has no new failure remains as a future tiny follow-up slice
— but only if close-gate evidence collection later demonstrates the
line actually misleads operators in the wild. Deferring it is the
right call now; revisit after the first 20-slice batch if the
output still looks confusing.
