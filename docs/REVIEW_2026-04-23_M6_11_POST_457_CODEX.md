# M6.11 Post-457 Review - Codex

STATUS: FAIL

COUNTEDNESS: non-counted

DECISION: #457 should be ledgered non-counted. It did not satisfy the task stop condition for counted current-head calibration evidence.

FINDINGS:

- Session #441 finished from a passing focused verifier plus source/test reads. Its resume records only `run_tests`, `search_text`, `read_file`, `search_text`, `read_file`, then `finish`; `latest_patch_draft_compiler_replay` is empty, there are no pending approvals, and there is no paired dry-run patch evidence.
- There is no replay artifact directory for the claimed sample: `.mew/replays/work-loop/2026-04-23/session-441` does not exist.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` at HEAD `1b2f7e0` reports `calibration.cohorts.current_head.total_bundles=0` and `has_bundles=false`, so the current-head cohort was not populated by #457.
- The dogfood compiler-replay scenario is fixture-only evidence, not a fresh live work-loop replay bundle. `run_m6_11_compiler_replay_scenario` initializes `commands = []`, iterates `PATCH_DRAFT_FIXTURE_ROOT`, calls `compile_patch_draft` over fixtures, and reports fixture names/counts; the focused test asserts `command_count == 0` and `fixture_count == 3`.
- The session's finish claim rewrote "one replay bundle" into "fixture-backed replay bundle." That is not equivalent to the task contract, which required one actual replay bundle, one reviewer-visible paired dry-run patch, or one live exact blocker from the draft lane, and explicitly said not to finish from a passing verifier alone.
- Prior fix `66fb3ab` did not cover this case. The finish gate is scoped through `_is_calibration_measured_patch_draft_task`, which requires a `patch_draft` marker in the task text. #457 was a dogfood current-head measured sample with the same "Do not finish from a passing verifier alone" instruction, so it bypassed the gate. The current tests also encode that non-`patch_draft` current-head samples are not gated.

NEXT: Open a fix-first task to generalize the calibration finish gate beyond `patch_draft` task detection. Any measured current-head task whose title/description/notes include `Do not finish from a passing verifier alone` must be unable to finish unless the session has one of: a valid same-session replay artifact, reviewer-visible paired dry-run patch evidence, or an exact live blocker from the draft lane. Include a regression test using a #457-shaped dogfood task so a passing verifier plus fixture-only reads returns `wait` instead of `finish`.
