# REVIEW 2026-04-23 - M6.11 Finish Gate Replay Evidence

Reviewer: codex-ultra
Session: `019db9c8-2d8b-73b3-89ea-607e4cc627f2`

## Scope

Reviewed the M6.11 finish-gate patch touching:

- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `tests/test_work_session.py`

Intent: allow calibration-measured patch_draft tasks to finish when a valid
patch_draft compiler replay artifact exists from a previous completed model turn
in the same session, while blocking stale or wrong replay evidence.

## Result

STATUS: PASS

No findings in the current diff for the requested scope.

The patch addresses the stale replay and incomplete metadata gaps from the first
review:

- prior replay evidence is validated against schema, session, todo, and payload
  file presence
- older replay evidence is dropped when a later completed write action has no
  replay

Focused review verification observed the relevant `WorkSessionTests` around:

- prior replay allowed
- missing/stale path blocked
- later write blocked
- wrong todo blocked
- failed turn ignored
- current-turn replay allowed
- no-replay finish blocked
