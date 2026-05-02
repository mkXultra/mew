# M6.24 Compound Budget Speed Rerun - 2026-05-03

## Run

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compound-budget-compile-compcert-1attempt-20260503-0255`

Trial:

`compile-compcert__jRh8cm9`

Command shape:

`terminal-bench/compile-compcert`, `-k 1 -n 1`, same Harbor wrapper, same
`mew work --oneshot --defer-verify` command template, `gpt-5.5`, Codex auth
mounted from `~/.codex/auth.json`.

## Result

- Harbor reward: `0/1`
- runner exceptions: `0`
- total runtime: `9m58s`
- `mew-report.work_exit_code`: `1`
- `mew-report.work_report.stop_reason`: `long_command_budget_blocked`
- `timeout_shape.latest_long_command_run_id`: `work_session:1:long_command:1`
- `timeout_shape.latest_long_command_status`: `failed`
- external verifier: `/tmp/CompCert/ccomp` did not exist

## What Moved

The previous gap `compound_long_command_budget_not_attached` moved.

The live path now created a managed long-command run:

- `LongCommandRun.id`: `work_session:1:long_command:1`
- `status`: `failed`
- `stage`: `source_acquisition`
- `terminal.exit_code`: `22`
- `terminal.timed_out`: `false`

This means the approved compound budget repair reached production execution.
The failure is no longer "no managed budget was attached".

## New Gap

`non_timeout_source_acquisition_retry_blocked_as_same_timeout`

The failed managed command was a terminal non-timeout source-acquisition failure:
`curl` returned HTTP 404 while fetching source metadata.

The model then selected a corrected source channel, but the long-build reducer
treated the terminal failure like a timeout-style resume:

- `allowed_next_action.kind`: `resume_idempotent_long_command`
- prohibited action: `repeat_same_timeout_without_budget_change`
- resulting stop: `long_command_budget_blocked`

That policy is right for timed-out/killed long commands. It is wrong for a
terminal failed source acquisition with `timed_out=false`, where the next useful
action is a changed source channel or changed command.

codex-ultra classification:

- session `019de9de-820a-74c3-90bf-127e48a435b0`
- `primary_gap_class`: `non_timeout_source_acquisition_retry_blocked_as_same_timeout`
- `is_previous_gap_moved`: `yes`
- `repair_layer`: `detector/resume_state`

## Repair

Implemented in:

- `src/mew/long_build_substrate.py`
- `src/mew/commands.py`

Generic behavior:

- terminal `failed` long commands no longer reduce to timeout-style
  `resume_idempotent_long_command`;
- source-acquisition terminal failures are classified as
  `source_acquisition_failed`;
- failed non-timeout long commands now produce
  `repair_failed_long_command`;
- exact repeats of the failed idempotence key are still blocked as
  `repeat_identical_failed_command_without_new_evidence`;
- corrected commands with changed source channel or changed command are allowed
  under managed budget without requiring a larger timeout.

This is not a CompCert URL recipe.

## Validation

Focused:

`uv run pytest tests/test_long_build_substrate.py tests/test_work_session.py -q -k "failed_source_acquisition or same_timeout_resume or repaired_command_after_failed_source_acquisition or identical_failed_source_acquisition or timed_out_long_command"`

Result:

- `5 passed`

Broader M6.24 subset:

`uv run pytest tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py tests/test_toolbox.py tests/test_long_build_substrate.py -q -k "long_command or work_oneshot or harbor or timeout_shape or runtime_link or acceptance or source_authority or budget_stage or source_acquisition"`

Result:

- initial repair: `251 passed, 3 subtests passed`
- after review integration fix: `253 passed, 3 subtests passed`

Ruff:

`uv run ruff check src/mew/commands.py src/mew/long_build_substrate.py tests/test_long_build_substrate.py tests/test_work_session.py`

Result:

- passed

## Review Follow-Up

codex-ultra review session `019de9e6-a30b-7452-9e5f-ae8c2ca5914f`
returned `STATUS: REQUEST_CHANGES`.

Findings:

- `recover_long_command` was allowed by the budget policy but was not accepted
  by `_managed_long_command_budget()`, so changed corrective retries could fall
  back to normal shell execution instead of `ManagedCommandRunner`;
- killed managed command status could collapse to `failed`, weakening the
  timeout-style resume path for killed long commands.

Follow-up repair:

- `recover_long_command` is now a managed long-command action kind;
- killed and interrupted terminal managed command statuses are preserved when
  recording `LongCommandRun` state;
- integration tests now prove `recover_long_command` dispatches through the
  managed runner and killed managed commands keep timeout-style resume
  semantics.

Re-review:

- codex-ultra session `019de9e6-a30b-7452-9e5f-ae8c2ca5914f` returned
  `STATUS: APPROVE`;
- no remaining issues found in this repair slice;
- approved next action: exactly one same-shape `compile-compcert` speed_1.

## Next Action

Run exactly one same-shape `compile-compcert` speed_1.

Do not run `proof_5` or broad measurement before that same-shape rerun.
