# M6.11 Post-Phase-4 Next Slice — Review (2026-04-22, claude)

## Context

HEAD: `8f48189` (Land M6.11 phase 4 blocker recovery bridge).

Post-commit facts on task `#402` / session `#392`:

- `./mew work 402 --session --resume --allow-read . --json` now reports
  `phase=blocked_on_patch`, populated `active_work_todo.blocker`, a
  `recovery_plan` with the tiny-lane blocker item, and `continuity=9/9`
  including `next_action_runnable`. Phase 4 blocker persistence is landed.
- `./mew work 402 --follow-status --json` still reports stale
  `phase=drafting`, empty `suggested_recovery`, and `latest_model_failure`
  pinned to the old `request_timed_out` turn. The snapshot at
  `.mew/follow/session-392.json` was written before the Phase 4 bridge
  landed and is never refreshed from the newer in-memory session.
- `_work_follow_status_from_snapshot` already detects this case
  (`session_state_newer=True` at `src/mew/commands.py:6705`) but only
  synthesizes a single `inspect_resume` fallback into `suggested_recovery`
  *if* `planned` from the snapshot resume was empty. Every other surface
  (`phase`, `next_action`, `active_work_todo`, `latest_model_failure`,
  `continuity`, `recovery_plan`) still reads straight from the stale
  snapshot file, so the live blocker/recovery state never shows up in
  follow-status output.
- Phase 2/3 calibration still fails the concentration gate with dominant
  `request_timed_out` share `0.5714` across 14 bundles (threshold `0.40`).
  That is a separate, larger, prompt/lane-shape problem.

## Proposed Slice (bounded follow-status newer-session bridge)

**When the current session is newer than the follow snapshot, derive
`phase`, `next_action`, `active_work_todo`, `suggested_recovery`,
`latest_model_failure`, and `continuity` in `work --follow-status` from a
freshly built `build_work_session_resume(session)` instead of the stale
snapshot resume, and surface the drafting-specific observability fields
(`active_work_todo`, `blocker_code`, `next_recovery_action`) the Phase 4
design requires.**

Concretely, in `_work_follow_status_from_snapshot`
(`src/mew/commands.py:6636`):

1. After computing `session_state_newer`, if `session is not None and
   session_state_newer`, call
   `build_work_session_resume(session, limit=8)` once and bind it as
   `live_resume`. Skip this call when `session_state_newer` is `False` so
   snapshot-only reads stay on the existing fast path.
2. Source `phase`, `next_action`, `recovery_plan`, `active_work_todo`,
   `verification_coverage_warning`, `verification_confidence`, and
   `continuity` from `live_resume` when it exists; otherwise keep the
   current snapshot-derived fallbacks. No snapshot mutation.
3. Pass `live_resume` into `work_follow_status_suggested_recovery` as the
   authoritative recovery-plan source so planned items produced by
   `_tiny_write_ready_draft_recovery_plan_item` surface. Current code
   reads only `snapshot_data["resume"]["recovery_plan"]`; extend it to
   prefer `live_resume["recovery_plan"]` when provided.
4. In `_work_follow_status_latest_model_failure`, break the "session wins
   on tie or newer id" shortcut when the snapshot failure belongs to a
   superseded turn. The simple rule that stays inside scope: when
   `session_state_newer` is `True`, prefer the session's
   `_latest_failed_model_turn` unconditionally (the snapshot turn is, by
   construction, older). Keep the existing merge rule unchanged when
   `session_state_newer` is `False`. This fixes the pinned-on-old-timeout
   bug without rewriting the merge.
5. Add three top-level follow-status fields per the Phase 4 design
   observability section (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`
   lines 729-740):
   - `active_work_todo` (copied from the resolved resume)
   - `blocker_code` (`active_work_todo.blocker.code` if present, else `""`)
   - `next_recovery_action`
     (`active_work_todo.blocker.recovery_action`, else the
     `recovery_plan`'s first item `recovery_action`, else `""`)
6. In `format_work_follow_status`, print one `active_work_todo:` line
   summarizing `status`, `blocker.code`, `blocker.recovery_action`, and
   `attempts.draft` (mirrors the `format_work_session_resume` formatter);
   print a `next_recovery_action:` line when set. Keep all other lines
   unchanged to avoid churning operator muscle memory.

This is purely a read-path change inside `commands.py`. It adds no new
storage, no snapshot writer, no runtime state, and no new resume field.
It reuses the already-landed Phase 4 persistence: the session's
`active_work_todo` and resume `recovery_plan` are already authoritative.

## Why this slice, not an alternative

1. **It closes the exact three gaps the user flagged in one surface.**
   The `--follow-status --json` command is the single consumer that still
   shows pre-Phase-4 state. Every downstream resume consumer already
   reads the fresh session resume. Pointing follow-status at the same
   source retires the inconsistency without touching writers.

2. **The Phase 4 review explicitly deferred it.**
   `docs/REVIEW_2026-04-22_M6_11_PHASE4_NEXT_SLICE_CLAUDE.md` Risks #4
   and Non-goals call out
   `_work_follow_status_latest_model_failure` stale-timeout merge and the
   missing observability fields as "explicit follow-up slice, not
   silently deferred and forgotten." This is that slice.

3. **It completes Phase 4 in the design's own terms.** The design's
   Phase 4 "Add drafting-specific recovery and follow-status"
   (`LOOP_STABILIZATION_DESIGN_2026-04-22.md:836`) requires surfacing
   `phase`, `todo_id`, `blocker_code`, and `next_recovery_action` in
   `work --follow-status`. Only persistence and resume side have landed;
   the follow-status side has not. Landing this slice lets the milestone
   finally claim Phase 4 closed by contract, not just by resume coverage.

4. **Rejected alternatives and why:**
   - *Refresh the follow snapshot eagerly from the session writer (Phase
     6 terminal-record territory).* Correct long-term shape, but it
     requires touching the snapshot writer path plus producer lifecycle,
     blowing the blast radius and colliding with the deferred Phase 6
     executor work. Not bounded.
   - *Fix the calibration concentration gate (reduce timeout share
     below 0.40 across 20 bundles).* Root cause is the tiny-lane prompt
     producing `request_timed_out` at ~57% — needs live runs, prompt
     tuning, and possibly timeout-uplift inside a frozen prompt envelope.
     That work is unbounded from a single review, requires live model
     proof, and would mix Phase 3 prompt churn with Phase 4 surface
     tightening. Keep it as the next-next slice after follow-status is
     authoritative so its measurement surface is trustworthy.
   - *Add a new `latest_patch_blocker` top-level resume field mirroring
     follow-status observability.* The Phase 4 review already rejected
     this: `active_work_todo` already carries the blocker and is already
     the canonical source of truth. Duplicating it widens state without
     closing any gap.
   - *Persist calibrated blocker-code → recovery-action mapping
     expansion, e.g. register `insufficient_cached_context`.* Mildly
     useful, but today it already falls through to
     `refresh_cached_window`, so the user-visible `--follow-status`
     output is unchanged. Pure taxonomy cleanup belongs on a separate
     bounded slice once follow-status is authoritative.
   - *Bounded one-shot retry after a tiny-lane blocker.* Needs attempt
     budget policy plus new tests; Phase 5 territory per the design and
     per the prior review.

5. **It leaves the frozen surfaces frozen.** No edits to
   `write_tools.py`, prompt shape, `patch_draft.py` validator,
   blocker taxonomy, or `commands.py` approval/apply surfaces. Only the
   read-side of follow-status changes.

## Files to change

- `src/mew/commands.py`
  - Import `build_work_session_resume` if not already in this module's
    import list.
  - Extend `_work_follow_status_from_snapshot` (~`src/mew/commands.py:6636`)
    to build `live_resume` when `session_state_newer` and `session` is
    present, and prefer it for `phase`, `next_action`, `continuity`,
    `verification_coverage_warning`, `verification_confidence`, and the
    `recovery_plan` handed to `work_follow_status_suggested_recovery`.
  - Extend `work_follow_status_suggested_recovery`
    (`src/mew/commands.py:6508`) to accept an optional `resume_override`
    argument (or read a `live_resume` key from `snapshot_data` it adds
    locally) and use its `recovery_plan` when the snapshot's is empty.
  - Extend `_work_follow_status_latest_model_failure`
    (`src/mew/commands.py:6616`) to accept a `prefer_session` flag; when
    `True`, return the session failure if any, else the snapshot failure.
    Pass `prefer_session=session_state_newer` from the caller.
  - Add `active_work_todo`, `blocker_code`, and `next_recovery_action`
    keys to the return dict of `_work_follow_status_from_snapshot`.
  - Extend `format_work_follow_status`
    (`src/mew/commands.py:6770`) to emit one `active_work_todo:` line
    (status, `blocker.code`, `blocker.recovery_action`,
    `attempts.draft`) and one `next_recovery_action:` line when set.
    Reuse the existing `active_work_todo` formatting pattern from
    `format_work_session_resume` so both surfaces read identically.

- `tests/test_commands.py`
  - Add `test_work_follow_status_prefers_live_session_when_newer`:
    build a state with a snapshot that has `resume.phase=drafting`,
    empty `recovery_plan`, and an old failed model turn, and a session
    where `active_work_todo.status=blocked_on_patch`, a persisted
    `blocker` with `recovery_action`, `updated_at` > snapshot
    `session_updated_at`, and a newer failed model turn. Assert the
    follow-status JSON reports `phase=blocked_on_patch`,
    `blocker_code=<persisted>`, non-empty `suggested_recovery` with
    `kind` matching the tiny-lane recovery plan item,
    `latest_model_failure.source="session"` with the newer turn id,
    and a non-empty `active_work_todo` block.
  - Add `test_work_follow_status_keeps_snapshot_when_session_older`:
    inverse case — snapshot is the newer write, session is older. Assert
    the existing snapshot-driven output is preserved (no regression for
    the common live-follow path).
  - Add `test_work_follow_status_exposes_next_recovery_action`: sanity
    check that `next_recovery_action` is populated from
    `active_work_todo.blocker.recovery_action` when present and falls
    back to `recovery_plan[0].recovery_action` otherwise, and is `""`
    when neither exists.
  - Adjust any existing follow-status JSON-shape assertion (currently
    around `test_work_follow_status_*`) to tolerate the three new keys.
    Existing assertions that key off `phase` or `latest_model_failure`
    should remain green; none of them construct an explicit
    `session_state_newer` scenario today.

No changes to `src/mew/work_session.py`, `src/mew/work_loop.py`,
`src/mew/patch_draft.py`, `src/mew/write_tools.py`, or any prompt/lane
module in this slice.

## Focused tests to run

- `uv run pytest tests/test_commands.py -q -k follow_status`
- `uv run pytest tests/test_work_session.py -q` (full file, unchanged,
  to prove no regression in the Phase 4 persistence + resume tests)
- `uv run ruff check src/mew/commands.py tests/test_commands.py`

## Risks

1. **Performance: `build_work_session_resume` inside follow-status.**
   The resume builder is non-trivial. Mitigation: only build when
   `session_state_newer` is `True`. The common hot-follow path
   (snapshot fresher than session) keeps the current zero-cost branch.
2. **Subtle continuity drift.** If `live_resume["continuity"]` differs
   from the snapshot's, existing continuity assertions elsewhere may
   observe two values from one task across surfaces. Mitigation: prefer
   live continuity only when `session_state_newer` and document the
   swap inline. Every downstream consumer already trusts the live
   resume; this aligns follow-status with them, not the other way.
3. **latest_model_failure merge regression.** The current merge chooses
   session when ids are unresolvable. Under `prefer_session=True`, that
   path keeps the same outcome; under `prefer_session=False` (the
   common case when the snapshot is newer), the existing "session wins
   on tie" default is preserved. Covered by the two new directional
   tests.
4. **Inspect-resume command string.** `_work_follow_status_inspect_command`
   already emits `--session --resume --auto-recover-safe`, which matches
   the user's existing invocation. No change to that command is
   needed; the suggested_recovery kind will now reliably match a
   tiny-lane `inspect_blocker`-style plan item instead of falling back
   to the generic `inspect_resume` string.
5. **Snapshot-write-side divergence remains.** This slice does not
   rewrite the snapshot writer to always reflect post-Phase-4 state.
   A future slice (likely inside Phase 6 executor lifecycle) can do
   that; until then, the *read* side of follow-status is
   authoritatively reconciled by this change, which is what the
   user-visible gap demands.

## Non-goals

- No changes to `build_work_recovery_plan` or to the `replan`
  model-turn recovery item.
- No change to `_attempt_write_ready_tiny_draft_turn`, tiny-lane prompt
  envelope, or write-ready fast-path prompt.
- No new resume fields (`latest_patch_blocker`,
  `draft_prompt_contract_version` surfacing beyond what Phase 4
  already added, etc.).
- No fix to the Phase 2/3 calibration concentration gate (dominant
  `request_timed_out` share `0.5714`). That is the logical next-next
  slice, intentionally left outside this one.
- No retry-after-blocker automation (Phase 5).
- No review lane (Phase 5), no executor lifecycle tightening (Phase 6).
- No snapshot writer changes; follow snapshots keep their existing
  write cadence.
- No taxonomy expansion of
  `WORK_TODO_BLOCKER_RECOVERY_ACTIONS`; unknown codes keep falling back
  to `refresh_cached_window` as defined in the Phase 4 slice.

## Success criteria for this slice

1. `./mew work 402 --follow-status --json` against the existing
   `.mew/follow/session-392.json` plus the current in-memory session
   reports:
   - `phase == "blocked_on_patch"`
   - non-empty `active_work_todo` with the persisted `blocker.code` and
     `blocker.recovery_action`
   - non-empty `suggested_recovery` matching the tiny-lane recovery plan
     item (not an `inspect_resume` fallback)
   - `latest_model_failure.source == "session"` with the newer failed
     model turn id
   - `blocker_code` and `next_recovery_action` populated
   - `continuity` reports 9/9
2. `./mew work 402 --follow-status` (human format) prints one
   `active_work_todo:` line and one `next_recovery_action:` line
   alongside the existing output.
3. All new and existing `tests/test_commands.py` follow-status tests
   pass under `uv run pytest tests/test_commands.py -q -k follow_status`.
4. `uv run pytest tests/test_work_session.py -q` remains green.
5. `uv run ruff check src/mew/commands.py tests/test_commands.py`
   passes.
