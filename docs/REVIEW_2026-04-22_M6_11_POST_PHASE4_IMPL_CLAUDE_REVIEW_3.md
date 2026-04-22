# M6.11 Post-Phase-4 Follow-Status Parity — Final Review (2026-04-22, claude)

## Scope re-reviewed

Uncommitted diff against HEAD `8f48189`:

- `src/mew/commands.py` (+165 / -25, +1 code line since REVIEW_2)
- `tests/test_work_session.py` (+456 / -20, +65 lines since REVIEW_2)

## Delta since REVIEW_2

### 1. Pending-approval count now reads from the effective resume

At `src/mew/commands.py:6816`:

```python
pending_approvals = (effective_resume or {}).get("pending_approvals") or []
```

And at `src/mew/commands.py:6867-6869`:

```python
"pending_approval_count": len(pending_approvals)
if use_session_overlay
else len(data.get("pending_approvals") or []),
```

The previous iteration read
`len((session or {}).get("pending_approvals") or [])` on the overlay
path. That was silently always `0`, because `session` never stores
`pending_approvals` as a field — the only producer of
`pending_approvals` is `build_work_session_resume` itself
(`src/mew/work_session.py:5388`), which iterates tool calls with
`status == "approval_requested"` and builds the view at resume time.
The fix changes the source to `effective_resume["pending_approvals"]`,
which is the resume-builder-computed view of actually-pending
approvals when overlay is on. This is a genuine correctness
improvement: under the previous code, follow-status would have
reported `pending_approval_count: 0` even on a live session with real
pending approvals as long as the overlay path was taken.

### 2. New targeted test

`test_work_follow_status_overlay_uses_effective_resume_pending_approval_count`
(`tests/test_work_session.py:234-298`) stubs `build_work_session_resume`
to return a `pending_approvals: [2 approvals]` view, forces overlay via
an equal timestamp + richer blocker, and asserts
`data["pending_approval_count"] == 2` and
`resume_source == "session_overlay"`. This locks the fix in.

Existing `test_work_follow_status_marks_session_state_newer_than_snapshot`
still asserts `pending_approval_count == 0` — which is now correct for
the right reason: the fresh `build_work_session_resume(session)` call
on a session whose tool_calls have no `approval_requested` entries
produces an empty `pending_approvals` list, so the overlay count is
truly 0.

## Findings

No blocker-severity findings.

### 1. LOW (unchanged) — `session_state_newer` still computed twice

`src/mew/commands.py:6787` and `6819` both assign `session_state_newer`
with identical arguments. Redundant but harmless.

### 2. LOW / OPEN QUESTION (unchanged) — Stale snapshot `latest_model_failure` persists when the live side has no new failure

`_work_follow_status_latest_model_failure(..., prefer_session=True)` at
`src/mew/commands.py:6703-6708` only returns the session failure when
one exists. For the `#402` tiny-lane-wait scenario, `session_failure`
is `None` and the snapshot's stale timeout is returned with
`source="snapshot"`. Whether this is intended ("prefer live *when it
exists*") or a gap ("suppress stale snapshot failure whenever overlay
is on") is still unresolved. Not a blocker for landing this slice, but
it leaves the user-visible `latest_model_failure:` line still showing
the stale timeout on `#402`-like snapshots.

### 3. LOW (unchanged) — `build_work_session_resume` in-call side effects and per-call cost

`_work_follow_status_from_snapshot` now invokes
`build_work_session_resume(session, ...)` at
`src/mew/commands.py:6785`. The call mutates `session` (via
`_observe_active_work_todo`). Mutations are discarded on exit
(`cmd_work_follow_status` does not `save_state`) but propagate to
other readers of `session` inside the same call. Additional per-call
cost. No correctness regression.

### 4. LOW (unchanged) — `phase` hardcoded override duplicates canonical-source derivation

`src/mew/commands.py:6848-6852` hardcodes `"blocked_on_patch"` when
overlay is on and the active todo says so, duplicating the derivation
already done by `build_work_session_resume` at
`src/mew/work_session.py:5281`. Cosmetic maintenance concern only.

### 5. LOW (unchanged) — Continuity-score comparison uses only the numerator

`_work_follow_status_resume_is_richer` compares the parsed integer
score without the denominator. Stable today with 9 axes; brittle if
axis count changes between snapshot and session versions. Low impact.

### 6. LOW (unchanged) — `working_memory_stale` is not overlayed

`working_memory_stale` is computed from `resume` (the snapshot's
resume) at `src/mew/commands.py:6778-6780`, before the overlay
decision. Every other resume-derived field switches to the live resume
when overlay fires, except this one. Parity gap for this single
field; small fix (recompute after overlay decision).

### 7. LOW (unchanged) — Dead `except` branch in `_work_follow_status_continuity_score`

The `try / except` at `src/mew/commands.py:6600-6604` wraps
`int(value)` for `float` inputs, which cannot raise for normal floats.
Unreachable `except`. Tidy-only.

## Residual non-blocking follow-ups

1. Resolve the intent question on `latest_model_failure` (Finding 2).
2. Deduplicate `session_state_newer` (Finding 1).
3. Factor `phase` derivation to a single helper (Finding 4).
4. Parse/compare the full `passed/total` ratio or document the stable
   denominator assumption (Finding 5).
5. Overlay `working_memory_stale` consistently (Finding 6).
6. Drop the unreachable `float` branch (Finding 7).

## Bounding check

- Files touched: 2 (`src/mew/commands.py`, `tests/test_work_session.py`). ✓
- No change to `work_session.py`, `work_loop.py`, `patch_draft.py`, or
  write/apply/verify flow. ✓
- No new top-level fields on `build_work_session_resume`. The only new
  public-ish keys (`resume_source`, `active_work_todo`, `blocker_code`,
  `next_recovery_action`) live on `_work_follow_status_from_snapshot`'s
  return dict and the follow-status formatter. ✓
- Stays inside the post-Phase-4 follow-status parity slice. ✓

## Verdict

**Approve.**

The pending-approval fix closes a real correctness gap left by the
prior iteration: previously the overlay path would have always read
`pending_approval_count: 0` regardless of what the live session held,
because `session["pending_approvals"]` is not a stored field. The new
code sources the count from `effective_resume["pending_approvals"]`,
which is the resume-builder-computed live view, and the new test
`test_work_follow_status_overlay_uses_effective_resume_pending_approval_count`
pins this behaviour.

Across the series (REVIEW → REVIEW_2 → REVIEW_3) the slice has:

- introduced the `session_state_newer OR (session_state_equal AND
  resume_is_richer)` overlay trigger;
- wired live `active_work_todo`, `blocker_code`,
  `next_recovery_action`, `continuity`, `phase`, `next_action`,
  `verification_*`, and `suggested_recovery` through
  `_work_follow_status_from_snapshot`;
- surfaced `resume_source` in JSON and human output;
- fixed the continuity-score parser to handle the real `"X/Y"` string
  form;
- added a snapshot-fresher negative test that asserts
  `resume_source == "snapshot"`;
- and now sourced `pending_approval_count` from the effective resume
  rather than a non-existent session field.

All remaining findings are LOW-severity (duplicate computation,
open-question on stale-failure semantics, redundant phase override,
unparsed-denominator in continuity compare, un-overlayed
`working_memory_stale`, one unreachable branch, resume builder
side-effects / cost). None of them block landing the slice.
