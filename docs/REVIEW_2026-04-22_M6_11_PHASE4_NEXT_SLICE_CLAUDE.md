# M6.11 Phase 4 Next Slice — Review (2026-04-22, claude)

## Context

HEAD: `5085ff0`. Tiny write-ready draft lane is now landed and, on live task
`#402` / session `#392`, the lane returns a stable blocker wait reason
(`write-ready tiny draft blocker: <code>`) instead of the previous raw model
timeout. Session continuity is 8/9. The one missing axis is
`next_action_runnable`.

Live inspection of `.mew/follow/session-392.json` confirms the gap concretely:

- `stop_reason`: `wait`
- `resume.phase`: `drafting`
- `resume.active_work_todo.status`: `drafting`
- `resume.active_work_todo.blocker`: `{}`
- `resume.next_action`: "draft one bounded patch from the cached paired windows
  or record one exact blocker"

Meanwhile the compiler replay bundle at
`.mew/replays/work-loop/2026-04-22/session-392/todo-todo-392-1/attempt-4/validator_result.json`
already contains a structured blocker:

```json
{
  "kind": "patch_blocker",
  "code": "insufficient_cached_context",
  "detail": "...",
  "recovery_action": "inspect_blocker",
  "todo_id": "todo-392-1"
}
```

So: the tiny lane has already classified the blocker and written it to disk.
The loop just never stores it back on `session["active_work_todo"]["blocker"]`
or flips the todo status. That single missing write is what keeps `#402`
stuck in a `drafting` + non-runnable next action loop.

## Proposed Slice (bounded Phase 4)

**Persist the tiny-lane patch blocker on the active `WorkTodo` so that
`session phase` derives to `blocked_on_patch` and resume surfaces a runnable
recovery next action.**

Concretely, when `_attempt_write_ready_tiny_draft_turn` returns
`status == "blocker"` in `src/mew/work_loop.py`, the caller must:

1. Write the blocker object into `session["active_work_todo"]["blocker"]`
   using the already-known `code`, `detail`, `path` (if any), and a pinned
   `recovery_action` from a small code→action map (see taxonomy below).
2. Set `session["active_work_todo"]["status"] = "blocked_on_patch"`.
3. Increment `session["active_work_todo"]["attempts"]["draft"]` exactly once
   per accepted tiny-lane blocker (not per prompt retry).
4. Update `session["active_work_todo"]["updated_at"]`.
5. On the next successful `patch_proposal` outcome, clear
   `blocker` back to `{}` and flip `status` back to `drafting` before the
   preview tool runs.

This reuses the existing normalizer `_normalize_active_work_todo` and the
existing `_observe_active_work_todo` path — no new storage, no new runtime
object, no schema change.

Because resume already derives:

- `phase = "blocked_on_patch"` when `active_work_todo.status == "blocked_on_patch"`
  (see `src/mew/work_session.py:5053`)
- `next_action = "inspect the active patch blocker and refresh the exact
  cached windows or todo source before retrying"` in that branch
  (`src/mew/work_session.py:5054`)

…just persisting the blocker automatically:

- flips live resume `phase` and `next_action` on `#402`,
- makes `next_action_runnable` pass (the string contains both `inspect` and
  `retry`, matching `_continuity_text_has_runnable_action`), raising
  continuity to 9/9,
- makes `follow-status` and `format_work_session_resume` surface the code on
  the todo (the formatter already prints
  `active_work_todo: id=... status=blocked_on_patch ... blocker.code=...`).

### Blocker → recovery-action map (pinned, read-only)

Introduce `WORK_TODO_BLOCKER_RECOVERY_ACTIONS` as a frozen dict matching the
design's Recovery Contract:

| code | recovery_action |
| --- | --- |
| `missing_exact_cached_window_texts` | `refresh_cached_window` |
| `cached_window_text_truncated` | `refresh_cached_window` |
| `stale_cached_window_text` | `refresh_cached_window` |
| `old_text_not_found` | `refresh_cached_window` |
| `ambiguous_old_text_match` | `narrow_old_text` |
| `overlapping_hunks` | `merge_or_split_hunks` |
| `no_material_change` | `revise_patch` |
| `unpaired_source_edit_blocked` | `add_paired_test_edit` |
| `write_policy_violation` | `revise_patch_scope` |
| `model_returned_non_schema` | `retry_with_schema` |
| `model_returned_refusal` | `inspect_refusal` |
| `review_rejected` | `revise_patch_from_review_findings` |

Unknown codes (e.g. the `insufficient_cached_context` currently produced on
`#402` attempt-4) fall back to `refresh_cached_window`, which is the
conservative and also the most common case. Mapping unknown codes is a known
side gap — it is *not* fixed in this slice, only made visible.

## Why this slice, not an alternative

1. **It is the minimum wire that removes the 8/9 continuity gap.** Every
   downstream surface (resume phase, resume next_action, continuity axes,
   follow-status formatting, future recovery plan integration) already reads
   from `session["active_work_todo"]`. The only missing write is upstream of
   all of them. No other single change produces the same cascade.
2. **It directly satisfies the task constraint.** The task says optimize for
   "#402 produces a runnable next action or recovery path after a clean
   blocker." The clean blocker already exists; only persistence is missing.
3. **It stays inside Phase 4 scope.** Phase 4 is "drafting-specific recovery
   and follow-status" (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:836`).
   Persisting the blocker + pinning a recovery action is exactly that.
4. **It defers larger rework cleanly.** Alternatives considered:
   - *Replace draft-time `replan` in `build_work_recovery_plan`*: correct
     long-term goal, but the current recovery plan path only runs on
     `interrupted` turns and tool calls. The tiny-lane blocker is a *clean*
     wait, not an interrupt, so retrofitting recovery plan entries requires
     introducing a new synthetic item source. Larger scope, no additional
     immediate #402 win once this slice lands.
   - *Add a separate `latest_patch_blocker` top-level resume field plus
     follow-status line*: adds duplicate state; the todo already carries
     the blocker, and the existing `active_work_todo` formatter already
     prints blocker.code. Defer any new top-level field until there is a
     scenario the todo-derived surface cannot express.
   - *Rewire `latest_model_failure` so the tiny-lane blocker supersedes the
     older timeout*: this is a real bug (the user noted it), but it is in
     the `snapshot_turns` / `session_turns` merge in
     `src/mew/commands.py:6616` and is orthogonal to the continuity gap.
     Pulling it in widens the slice and still doesn't make #402 runnable by
     itself. Leave as a small follow-up slice.
   - *Bounded one-shot retry after blocker*: needs attempt policy, budget
     enforcement, and new tests; better after the blocker is durable.
5. **It is fully compatible with the canonical source-of-truth invariant.**
   `active_work_todo.status` remains canonical; resume phase keeps being
   derived from it (`src/mew/work_session.py:5009,5053`).

## Files to change

- `src/mew/work_loop.py`
  - In `_attempt_write_ready_tiny_draft_turn`, populate and return the
    classified blocker payload (code, detail, path if present,
    `recovery_action` from the pinned map) alongside the existing `action` /
    `action_plan`. Currently `_stable_write_ready_tiny_draft_blocker_reason`
    drops everything except the code into the `wait` action's reason string.
  - At the tiny-lane success branch in `_run_work_session_decision_step`
    (around `src/mew/work_loop.py:2776-2803`), when `tiny_result["status"]
    == "blocker"`, call a new helper that mutates
    `session["active_work_todo"]` to set `status = "blocked_on_patch"`,
    `blocker = {...}`, bump `attempts.draft`, and refresh `updated_at`. On
    tiny-lane `succeeded`, the same helper resets `blocker = {}` and
    `status = "drafting"`.
- `src/mew/work_session.py`
  - Add the frozen `WORK_TODO_BLOCKER_RECOVERY_ACTIONS` dict near the
    existing `WORK_TODO_STATUSES` / `WORK_TODO_PHASE_STATUSES` constants
    (around `src/mew/work_session.py:42-49`) and export a small pure
    `work_todo_recovery_action_for_code(code) -> str` used by the work_loop
    helper above. Keep it pure and importable from tests.
  - Teach `_normalize_active_work_todo` to preserve the new `recovery_action`
    and `detail` keys on `blocker` when present. No other change.
- `src/mew/patch_draft.py`
  - No code change required for this slice. (Validator already emits
    `code`/`detail`/`recovery_action`; the gap is downstream.) If the
    pinned map lives here instead of `work_session.py` for cohesion, that is
    also acceptable — pick one and keep it side-effect-free.

Do **not** change `src/mew/commands.py`, `write_tools.py`, prompt shape, or
validator semantics in this slice.

## Focused tests to add / adjust

- `tests/test_work_session.py`
  - **Add** `test_tiny_write_ready_blocker_persists_on_active_work_todo`:
    construct a `session` with an `edit_ready` plan-item observation and
    paired cached windows, simulate a tiny-lane blocker result (stub
    `_attempt_write_ready_tiny_draft_turn` or call the new persistence
    helper directly) with `code="missing_exact_cached_window_texts"`,
    assert that `session["active_work_todo"]["status"] == "blocked_on_patch"`,
    `blocker.code` is set, `blocker.recovery_action ==
    "refresh_cached_window"`, and `attempts.draft` incremented by one.
  - **Add** `test_tiny_write_ready_blocker_flips_resume_to_runnable`:
    run `build_work_session_resume(session)` after the persistence above,
    assert `resume["phase"] == "blocked_on_patch"`, `resume["next_action"]`
    is the inspect-and-retry string, and
    `build_work_continuity_score(resume)` has all axes met including
    `next_action_runnable`.
  - **Add** `test_tiny_write_ready_success_clears_blocker`: after a blocker
    is persisted, run a tiny-lane `succeeded` path (or helper) and assert
    `blocker == {}` and `status == "drafting"`.
  - **Add** `test_work_todo_recovery_action_for_code_defaults_unknown_codes`:
    pure mapping test covering each known code plus
    `"insufficient_cached_context"` falling back to
    `refresh_cached_window`.
  - **Adjust** `test_build_work_session_resume_prefers_persisted_active_work_todo`
    if it currently asserts a blocker shape that does not carry
    `recovery_action` — extend to include the new key. (Existing test at
    `tests/test_work_session.py:8112` will need a one-line additional
    assertion.)

No changes required to `tests/test_commands.py` or follow-status formatters
in this slice; the existing `active_work_todo` formatter already exposes
`status`, `blocker.code`, and `attempts.draft`.

## Risks

1. **Blocker-clear regression on success path.** If the success branch
   forgets to reset `blocker`/`status`, the todo stays `blocked_on_patch`
   even after a validated draft. Mitigated by the dedicated clearing test.
2. **Attempts.draft double-count.** `_observe_active_work_todo` already
   reads `draft_attempts` from model turn metrics via
   `_write_ready_draft_metrics`. The persistence helper must increment only
   when metrics don't already account for the turn, or must use
   `max(existing, candidate)` semantics like the current frontier update at
   `src/mew/work_session.py:4516-4522`. Chosen approach: bump in the
   persistence helper, then let `_observe_active_work_todo` keep using the
   `max` merge it already uses, so re-observation is idempotent.
3. **Unknown blocker codes mask real problems.** Falling back to
   `refresh_cached_window` is benign but hides taxonomy drift. Mitigation:
   the test matrix explicitly covers the unknown-code fallback so any new
   unmapped code shows up in review instead of silently being swept to a
   single recovery.
4. **`latest_model_failure` stays stale.** The follow-status gap the user
   flagged (older timeout still shown while resume shows newer blocker) is
   not fixed here. It is a separate small slice; calling it out so it is
   not silently deferred and forgotten.
5. **Race on persistence vs. resume snapshot.** The existing snapshot path
   already rehydrates `active_work_todo` from session state. As long as the
   persistence write happens before the snapshot write in the same step
   loop iteration, this slice is safe.

## Non-goals

- No changes to `build_work_recovery_plan` or to the `replan` model-turn
  recovery item.
- No retry-after-blocker automation (Phase 5 territory).
- No review lane (Phase 5).
- No executor lifecycle state additions (Phase 6).
- No new top-level resume fields (`latest_patch_blocker`,
  `next_recovery_action`) — the existing `active_work_todo` surface is
  sufficient for the runnable-next-action goal.
- No changes to the tiny-lane prompt contract, `patch_draft.py` validator,
  or blocker taxonomy vocabulary.
- No fix to `_work_follow_status_latest_model_failure` stale-timeout merge
  (explicit follow-up slice).
- No widening of the pinned blocker→recovery map beyond the design doc's
  frozen taxonomy; unmapped codes fall back to `refresh_cached_window`.

## Success criteria for this slice

1. Rerunning #402 to the same point produces
   `follow/session-392.json` with `resume.active_work_todo.status ==
   "blocked_on_patch"`, a non-empty `blocker.code`, `blocker.recovery_action`
   set from the pinned map, and `resume.next_action` containing `inspect`
   and `retry`.
2. `build_work_continuity_score(resume)` reports 9/9 with
   `next_action_runnable` met.
3. All four new tests and the adjusted existing test pass under
   `uv run pytest tests/test_work_session.py -q`.
4. No change to `tests/test_commands.py` outcomes.
