STATUS: FAIL

COUNTEDNESS: rejected

DECISION: Do not accept task #462 / session #446 as M6.11 evidence. The run reached useful source/test reads, then the initial live turn timed out and later same-session bursts continued reading/searching and saved a `remember` note, but the session produced none of the required stop artifacts: no same-session replay bundle, no reviewer-visible paired dry-run patch, no source/test diff, no exact native draft-lane blocker, and no verifier run.

Evidence:

- HEAD is exactly `b74770081c532d2f25a943648ebcbc30c9650b76`.
- `find .mew/replays/work-loop/2026-04-23/session-446 -maxdepth 4 -type f` returns `No such file or directory`.
- `PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop/2026-04-23 --m6_11-phase2-calibration --json` reports `calibration.cohorts.current_head.total_bundles=0`.
- `git diff -- src/mew/work_loop.py tests/test_work_session.py` is empty.
- `.mew/follow/session-446.json` records `draft_attempts=0`, `latest_verifier_closeout={}`, `latest_patch_draft_compiler_replay={}`, an initial `model turn failed: request timed out`, and final `stop_reason=remember`.
- `.mew/state.json` still has task #462 status `ready`; work session #446 remains `active`.

Ledger disposition: append one non-counted rejected row so the no-artifact timeout/read-size failure is visible in calibration accounting, but do not increment current-head replay incidence.

Recommended fields:

```json
{"counted":false,"countedness":"rejected_no_artifact_timeout","reviewer_decision":"rejected_as_no_artifact_timeout_read_loop","non_counted_reason":"Task #462/session #446 timed out after scoped source/test reads and later same-session resume bursts only performed more reads/searches plus one remember action; it emitted no same-session replay bundle, no reviewer-visible paired dry-run patch, no source/test diff, no exact native draft-lane blocker, and no verifier run, so it cannot be accepted as M6.11 evidence.","blocker_code":null,"replay_bundle_path":null,"notes":"Frozen HEAD b747700. Scope was src/mew/work_loop.py + tests/test_work_session.py. Relevant windows were read, including src/mew/work_loop.py tiny-draft context/prompt regions and tests/test_work_session.py tiny write-ready draft tests, but the session stopped with no qualifying artifact. Task #462 remains ready/open; session #446 remains active. Treat as no-artifact timeout/read-size-control evidence, not counted or partial replay evidence."}
```

Next action: implement a narrow substrate fix before continuing normal sampling. Specifically, make model-timeout/no-assistant-text failures in an edit-ready or nearly edit-ready tiny-draft lane persist a reviewer-visible failure artifact, and reduce the work-loop tiny-draft context/read budget so this path can reach one patch/blocker decision inside the timeout. After that, rerun a fresh #462-style sample on `src/mew/work_loop.py` + `tests/test_work_session.py`; do not close #462 as successfully sampled, and do not keep spending live bursts on the same active session without a capture fix.

This does expose an M6.11 gap. The current loop can consume the full timeout after reading enough context to be in the target lane, yet leave no replay directory and no native blocker for reviewers to classify. The adjacent gap is context/read-size control: session #446 repeatedly expanded around large `work_loop.py` and `test_work_session.py` windows instead of converging to one paired draft or exact blocker. That combination makes failures disappear from current-head bundle accounting unless reviewers manually add rejected ledger rows.
