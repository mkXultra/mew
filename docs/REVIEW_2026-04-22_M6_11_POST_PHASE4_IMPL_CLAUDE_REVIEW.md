# M6.11 Post-Phase-4 Follow-Status Parity — Implementation Review (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `8f48189`:

- `src/mew/commands.py` (+146 / -25): introduces
  `_work_follow_status_session_state_equal`,
  `_work_follow_status_continuity_score`,
  `_work_follow_status_todo_has_blocker`,
  `_work_follow_status_resume_is_richer`,
  `_work_follow_status_session_task`. Threads a live
  `build_work_session_resume(session, ...)` result through
  `_work_follow_status_from_snapshot` and selects an "effective resume"
  either from the snapshot or from a fresh live overlay. Adds
  `resume_source`, `active_work_todo`, `blocker_code`, and
  `next_recovery_action` to the returned dict and the human-readable
  format. `_work_follow_status_latest_model_failure` grows a
  `prefer_session` flag.
- `tests/test_work_session.py` (+335 / -20): five new tests for the
  overlay path plus two assertion shifts on the existing
  `test_work_follow_status_marks_session_state_newer_than_snapshot`
  test (`pending_approval_count` 1 → 0; `suggested_recovery` goes from
  the old `replannable` command to `inspect_resume` / `--session
  --resume --allow-read . --auto-recover-safe`).

## Findings

No blocker-severity findings.

### 1. LOW — `session_state_newer` is computed twice

`_work_follow_status_from_snapshot` assigns `session_state_newer` at
`src/mew/commands.py:6767` and again at
`src/mew/commands.py:6800`, with identical arguments. The value is not
consumed between the two assignments. Redundant but harmless. Remove
one of them. Tidiness only.

### 2. LOW / OPEN QUESTION — Stale snapshot `latest_model_failure` can still survive an overlay-on path

`_work_follow_status_latest_model_failure` with `prefer_session=True`
returns the session failure *only when one exists*
(`src/mew/commands.py:6675-6700`):

```python
if not session_failure:
    snapshot_failure["source"] = "snapshot"
    return snapshot_failure
```

This is the path the live `#402` scenario actually takes: the tiny
lane produced a clean blocker (a `wait` action, not a failed model
turn). There is no new `failed` turn on the live side, so
`session_failure` is `None` and the old snapshot timeout is returned
with `source="snapshot"`. `format_work_follow_status` then still emits
`latest_model_failure: turn=… status=failed summary=request timed out`.

If the brief's "prefer live latest_model_failure when overlay is
chosen" is meant to also suppress a stale snapshot failure when the
live state has no active failure at all, this implementation does not
cover that case. If the brief only means "prefer live *when present*",
this is working as designed.

Recommendation: clarify the intent. If the former, either null out
`latest_model_failure` when `use_session_overlay` is True and
`session_failure` is `None`, or add a sibling field like
`latest_model_failure_stale` that the formatter annotates. Either is a
small follow-up. Not a blocker for landing this slice, which already
delivers parity on `phase`, `active_work_todo`, `blocker_code`,
`next_recovery_action`, `continuity`, `pending_approval_count`, and
`suggested_recovery`.

### 3. LOW — `build_work_session_resume` invocation has mutation side effects on the in-memory session

`_work_follow_status_from_snapshot` now calls
`build_work_session_resume(session, task=session_task, state=state)`
(`src/mew/commands.py:6766`). That function invokes
`_observe_active_work_todo`, which mutates `session["active_work_todo"]`
(stamping `status=blocked_on_patch`, minting todo ids,
incrementing/merging attempts) and bumps
`session["last_work_todo_ordinal"]`.

`cmd_work_follow_status` does not `save_state` afterward, so the
mutations are discarded when the command exits. Inside the same call,
however, the mutated `session` is passed onward to
`_work_follow_status_latest_model_failure`,
`work_follow_status_suggested_recovery`, and the `pending_approvals`
count read. The mutations align the in-memory `session` with the
overlay view, which is the desired behaviour for the report, but it is
worth noting that `_work_follow_status_from_snapshot` is no longer a
pure read over `session`. A future refactor could pass a copy or have
`build_work_session_resume` return an unmutated snapshot, but this is
not required for Phase 4 parity.

There is also a small per-call cost: `build_work_session_resume` is now
executed on every `--follow-status` invocation with a live session.
For a long-running session this is not a hot path, but the added work
is non-trivial.

### 4. LOW — Test coverage is one-sided for `resume_source`

All five new tests and the two assertion shifts exercise the
`resume_source == "session_overlay"` branch
(`tests/test_work_session.py:24737, 24816, 24871, 24943`). There is no
new test that explicitly asserts `resume_source == "snapshot"` when the
snapshot is fresher, when the session is absent, or when the timestamps
are equal but the session is *not* richer. The existing tests that
don't touch `resume_source` still pass the non-overlay path implicitly,
but a regression to "always overlay" would not be caught by any new
assertion.

One short negative test — e.g. snapshot with
`session_updated_at="2026-04-18T00:10:00Z"`, session with
`updated_at="2026-04-18T00:00:00Z"`, assert
`resume_source == "snapshot"` and assert `active_work_todo == {}` — would
close the loop. Not a blocker.

### 5. LOW — `phase` construction is redundant

The returned `phase` key at `src/mew/commands.py:6828-6832` hardcodes
`blocked_on_patch` when the overlay is on and the active todo status is
`blocked_on_patch`:

```python
"phase": (
    "blocked_on_patch"
    if use_session_overlay and str((active_work_todo or {}).get("status") or "") == "blocked_on_patch"
    else effective_resume.get("phase") or resume.get("phase") or data.get("phase") or ""
),
```

`build_work_session_resume` already derives `resume["phase"]` from
`active_work_todo.status` (`src/mew/work_session.py:5053` onwards), so
this override duplicates the design doc's canonical-source rule in a
second location. If `effective_resume.phase` ever disagrees with the
todo status, the discrepancy would be hidden. Safer to either (a) drop
the override and trust `effective_resume.phase`, or (b) factor the
status-to-phase derivation into one helper used by both sites.
Cosmetic / maintenance concern, not a correctness bug today.

### 6. LOW — Heuristic priority in `_work_follow_status_resume_is_richer`

`_work_follow_status_resume_is_richer`
(`src/mew/commands.py:6595-6620`) applies four heuristics in sequence:
blocked_on_patch promotion, todo-blocker-present, recovery-plan-items,
continuity-score. The ordering is sensible and matches the slice's
intent ("surface richer blocker state"), but it is ad-hoc and will
need revisiting once the Phase 5 review lane introduces new todo
statuses (`awaiting_review`, `awaiting_approval`, `applying`,
`verifying`). Worth a note in the design doc when that work lands so
the heuristic does not silently become wrong. Not an action for this
slice.

## Residual non-blocking follow-ups

1. Resolve the Finding 2 intent question: should an overlay-on path
   suppress a stale snapshot `latest_model_failure` when the live side
   has no active failure?
2. Add a `resume_source == "snapshot"` negative test (Finding 4).
3. Consider a single source of truth for `phase` derivation
   (Finding 5).
4. Deduplicate the `session_state_newer` computation
   (Finding 1).

## Bounding check

- Files touched: 2 (`src/mew/commands.py` and
  `tests/test_work_session.py`). ✓
- No change to `work_session.py`, `work_loop.py`, `patch_draft.py`, or
  write/apply/verify flow. ✓
- No new top-level resume schema field in `build_work_session_resume`;
  the new `active_work_todo`, `blocker_code`, and `next_recovery_action`
  keys only appear in `_work_follow_status_from_snapshot`'s return
  dict. ✓
- Stays inside the stated post-Phase-4 follow-status parity slice. No
  scope creep into Phase 5/6. ✓

## Verdict

**Approve.**

The slice closes the deferred follow-status parity gap that the prior
Phase 4 review explicitly left as a follow-up: `#402`-style sessions
whose live state has advanced to `blocked_on_patch` with a populated
blocker and non-empty recovery plan will now report those fields (plus
`resume_source=session_overlay`) in `mew work <id> --follow-status`,
even when the follow snapshot lags behind with a stale timeout. The
overlay trigger (`session_state_newer` OR
`session_state_equal` + `resume_is_richer`) is conservative and the
overlay-on path consistently uses the live resume for `phase`,
`next_action`, `continuity`, `active_work_todo`, `recovery_plan`,
`pending_approval_count`, and `verification_*`.

Residual items are low-severity: one open-question on
`latest_model_failure` semantics (Finding 2), a missing negative-path
test (Finding 4), a duplicated `session_state_newer` computation
(Finding 1), a redundant `phase` override (Finding 5), and a heuristic
that will need revisiting in Phase 5 (Finding 6). None of these block
landing.
