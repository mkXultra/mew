# M6.11 Calibration-Counted Compiler Replay Fix Review — Codex

Date: 2026-04-23  
HEAD: `739c527341833af38b3c88de2b092073b5ca4f4d`

## Findings

No blocking issues found in the current working-tree slice.

The change set fixes the two substrate problems that mattered for session-405:

- `src/mew/proof_summary.py:275-330` no longer misclassifies a valid
  `{"kind":"patch_draft","status":"validated"}` validator payload as malformed
  just because it has no `code`. Those bundles now land in
  `patch_draft_compiler.other`, which matches the actual compiler artifact shape.
- `src/mew/work_replay.py:337-390`, `src/mew/work_session.py:1512-1519`, and
  `src/mew/commands.py:5722-5734` add the missing coupling from reviewer
  rejection to replay metadata, so a rejected pending write can flip the replay
  bundle to `calibration_counted=false` with an exclusion reason.
- `src/mew/proof_summary.py:394-450` then excludes those non-counted bundles
  from `relevant_bundles`, `compiler_bundles`, `total_bundles`, and
  `malformed_relevant_bundle_count` while still surfacing them in a diagnostic
  bucket.

## Verification

- `PYTHONPATH=src python3 -m unittest tests.test_work_replay tests.test_work_session tests.test_proof_summary`
  passed: `Ran 527 tests ... OK`.
- Live replay verification against the current workspace:
  `PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  now reports:
  - `errors=[]`
  - `calibration.malformed_relevant_bundle_count=0`
  - `calibration.non_counted_bundle_count=2`
  - `calibration.cohorts.current_head.total_bundles=1`
  - `calibration.cohorts.current_head.non_counted_bundle_count=2`
- The session-405 replay metadata currently present at
  `.mew/replays/work-loop/2026-04-22/session-405/todo-todo-405-1/attempt-{1,2}/replay_metadata.json`
  is already marked with `calibration_counted=false` and
  `calibration_exclusion_reason="reviewer rejected"`, so the old pollution is
  excluded under the new summary logic.

## Residual Risk

The code fix only auto-protects future rejected samples. Older rejected replay
bundles still need their own `replay_metadata.json` backfilled to
`calibration_counted=false` or they will remain counted by default for backward
compatibility. In this workspace, session-405 is already backfilled, so the
specific session-405 malformed-bundle pollution issue is resolved locally.
