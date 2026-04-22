# M6.11 Post-Phase-4 Follow-Status Parity — Implementation Re-Review (2026-04-22, claude)

## Scope re-reviewed

Uncommitted diff against HEAD `8f48189`:

- `src/mew/commands.py` (+164 / -25, +18 since the prior review)
- `tests/test_work_session.py` (+391 / -20, +56 since the prior review)

The delta since the prior review:

1. `_work_follow_status_continuity_score`
   (`src/mew/commands.py:6580-6605`) is now a full type-dispatching
   parser that handles `int`, `float`, plain numeric `str` (e.g. `"9"`),
   and fractional `str` (e.g. `"9/9"`). The prior version would have
   silently returned `None` for the fractional form that
   `build_work_session_resume` actually produces (see
   `src/mew/work_session.py:3965`, `"score": f"{passed}/{total}"`),
   making the continuity-score branch of the richness heuristic
   effectively dead. That dead branch is now live.

2. New negative test
   `test_work_follow_status_keeps_snapshot_when_fresher_than_live_session`
   (`tests/test_work_session.py:234-290`) exercises the opposite of the
   overlay path: snapshot is newer, session has a richer in-memory
   `active_work_todo` with a populated blocker, and the test asserts
   `resume_source == "snapshot"`, `phase == "drafting"`,
   `blocker_code == ""`, and the live blocker code does not leak into
   `active_work_todo`. This closes the one-sided coverage gap flagged
   in the prior review.

3. `test_work_follow_status_overlay_prefers_live_continuity`
   (`tests/test_work_session.py:180-232`) now uses the real string form
   `"score": "9/9"` / `"1/9"` instead of the bare integer form it used
   before, directly exercising the parser fix.

## Findings

No blocker-severity findings.

### 1. LOW (unchanged) — `session_state_newer` still computed twice

Lines `src/mew/commands.py:6787` and `6804` both assign
`session_state_newer` with identical arguments. The second assignment
is a no-op. Tidiness only; not a correctness issue.

### 2. LOW / OPEN QUESTION (unchanged) — Stale snapshot `latest_model_failure` still survives an overlay-on path when the live side has no active failure

`_work_follow_status_latest_model_failure(..., prefer_session=True)`
at `src/mew/commands.py:6693-6715` returns the session failure only when
`_latest_failed_model_turn(session_turns)` is non-empty. For a
`#402`-shape session where the tiny lane returned a clean blocker
(a `wait` action, not a failed model turn), `session_failure` is
`None` and the old snapshot timeout is returned with
`source="snapshot"`. The formatter then still prints the stale
`latest_model_failure:` line. Whether this is intended ("prefer live
*when* a live failure exists") or a gap ("suppress stale failure
whenever overlay is chosen") depends on the slice's intended semantics;
still worth clarifying before treating the follow-status parity work as
closed.

### 3. LOW (unchanged) — `build_work_session_resume` side effects and per-call cost

`_work_follow_status_from_snapshot` calls
`build_work_session_resume(session, task=session_task, state=state)`
at `src/mew/commands.py:6776`. That call mutates `session`
(`_observe_active_work_todo` stamps `active_work_todo.status`, mints
todo ids, bumps `last_work_todo_ordinal`). `cmd_work_follow_status`
does not `save_state`, so the mutations are discarded on exit, but
they still flow into `_work_follow_status_latest_model_failure`,
`work_follow_status_suggested_recovery`, and the `pending_approvals`
count within the same call. Per-call cost also increases because the
resume builder is non-trivial. Neither issue is a correctness
regression; noting for future tightening.

### 4. RESOLVED — Snapshot-fresher negative test coverage

`test_work_follow_status_keeps_snapshot_when_fresher_than_live_session`
locks in `resume_source == "snapshot"` when the snapshot is newer and
the session has a richer in-memory todo. Coverage gap closed.

### 5. LOW (unchanged) — `phase` key still hardcodes `"blocked_on_patch"` override

The return-dict `phase` at `src/mew/commands.py:6848-6852`
duplicates the canonical-source derivation that
`build_work_session_resume` already performs. Safer to trust
`effective_resume.phase` (already derived from
`active_work_todo.status` in `src/mew/work_session.py:5053`). Cosmetic
/ maintenance concern only.

### 6. LOW — `_work_follow_status_continuity_score` compares numerator only

`_work_follow_status_resume_is_richer` compares the parsed integer
score (`9` vs `1`) without considering the denominator. Today
continuity always has 9 axes so the denominator is stable, but if a
future axis is added or removed between snapshot and session versions
the comparison could mislead. Low impact; worth a comment, or parse
the whole ratio.

### 7. LOW — `working_memory_stale` is not overlayed

`working_memory_stale` is computed from `resume` (the snapshot's
resume) at `src/mew/commands.py:6778-6780`, before the overlay
decision is made. When overlay fires, every other resume-derived
field switches to the live resume except this one. Parity is
incomplete for working-memory stale tracking. In practice this is
rarely material for the `#402` scenario, but it is an asymmetry worth
flagging. Small fix: recompute `working_memory_stale` from
`effective_resume.working_memory` after the overlay decision.

### 8. LOW — Dead branch in `_work_follow_status_continuity_score`

The `try / except` at `src/mew/commands.py:6600-6604` wraps only
`int(value)` for `float` inputs, which cannot raise for normal floats
(inf/nan are not meaningful here anyway). The `except` branch is
unreachable. Tidy-only.

## Residual non-blocking follow-ups

1. Resolve the intent question on `latest_model_failure` (Finding 2).
2. Deduplicate `session_state_newer` (Finding 1).
3. Factor out the `phase` derivation to a single helper (Finding 5).
4. Parse/compare the full `passed/total` ratio or document the stable
   denominator assumption (Finding 6).
5. Overlay `working_memory_stale` consistently (Finding 7).
6. Drop the unreachable `float` try/except branch (Finding 8).

## Bounding check

- Files touched: 2 (`src/mew/commands.py`, `tests/test_work_session.py`). ✓
- No change to `work_session.py`, `work_loop.py`, `patch_draft.py`, or
  the write/apply/verify flow. ✓
- No new top-level fields on `build_work_session_resume`; the new
  `active_work_todo`, `blocker_code`, and `next_recovery_action` keys
  only exist on `_work_follow_status_from_snapshot`'s return dict. ✓
- Stays inside the stated post-Phase-4 follow-status parity slice. No
  scope creep into Phase 5/6. ✓

## Verdict

**Approve.**

The continuity-score fix turns a previously dead branch into a working
one (the parser now correctly extracts `9` from `"9/9"`), and the new
snapshot-fresher negative test closes the coverage gap from the prior
review. The overlay path now:

- fires on the intended conditions
  (`session_state_newer` OR `session_state_equal + richer`),
- cleanly prefers live values for `phase`, `next_action`,
  `active_work_todo`, `blocker_code`, `next_recovery_action`,
  `continuity`, `pending_approval_count`,
  `verification_coverage_warning`, and `verification_confidence`, and
- surfaces `resume_source` in both JSON and human output.

Residual findings are all low-severity: one open-question
(`latest_model_failure` semantics — finding 2), two unchanged
tidiness items from the prior review (findings 1 and 5), and three
small new observations (findings 6, 7, 8). None block landing.
