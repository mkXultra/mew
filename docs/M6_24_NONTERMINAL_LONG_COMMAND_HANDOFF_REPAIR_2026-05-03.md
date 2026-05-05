# M6.24 Nonterminal Long-Command Handoff Repair - 2026-05-03

## Context

The same-shape `compile-compcert` speed_1 rerun after
`docs/M6_24_MANAGED_LONG_COMMAND_DISPATCH_REPAIR_2026-05-03.md` proved that
managed dispatch now works, but exposed a narrower handoff bug.

Run:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-dispatch-compile-compcert-1attempt-20260503-0045`

Observed:

- Harbor score: `0/1`
- `work_exit_code`: `0`
- `work_report.stop_reason`: `wait`
- `work_report.steps`: `6`
- `timeout_shape.latest_long_command_run_id`: `work_session:1:long_command:1`
- `timeout_shape.latest_long_command_status`: `running`
- `resume.long_build_state.recovery_decision.allowed_next_action.kind`: `poll_long_command`
- `terminal_command_evidence_ref`: `null`
- verifier failure: `/tmp/CompCert/ccomp does not exist`

## Classification

`nonterminal_managed_command_handoff`

The prior repair moved the system forward: a real managed command was launched,
persisted as `long_command_runs[0]`, and exposed `poll_long_command` as the next
valid recovery action.

The new failure is that `mew work --oneshot` treated a model `wait` action as a
successful external handoff even though the managed command was still
nonterminal. Harbor then ran the verifier while the build was still in progress.

This is generic one-shot semantics, not a CompCert-specific build recipe.

## Repair

Implemented in `src/mew/commands.py`:

- mark `cmd_work_oneshot` internal runs with `oneshot_mode`
- when a oneshot model emits `wait` while resume state has an active
  `running` / `yielded` managed long command whose allowed next action is
  `poll_long_command`, convert that wait to a synthetic `run_command` poll
- use a bounded 60s poll action so the managed runner can reach terminal
  evidence inside the same one-shot process
- if max steps are exhausted while an active managed long command remains
  nonterminal, return typed nonzero stop `long_command_incomplete` instead of
  handing off as success

Focused regression:

- `tests/test_work_session.py::WorkSessionTests::test_work_oneshot_converts_wait_to_active_long_command_poll`
- `tests/test_work_session.py::WorkSessionTests::test_work_oneshot_returns_nonzero_when_long_command_remains_nonterminal_at_max_steps`

Validation so far:

`uv run pytest tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py tests/test_toolbox.py tests/test_long_build_substrate.py -q -k "long_command or work_oneshot or harbor or timeout_shape or runtime_link or acceptance or source_authority"`

Result:

- `240 passed`

Review:

- codex-ultra session `019de975-e11d-72f3-905b-2eaeb52e376a`
- `STATUS: APPROVE`

## Next Action

Have codex-ultra review this generic handoff repair. If approved, run exactly
one same-shape `compile-compcert` speed_1.

Do not run proof_5 or broad measurement before that same-shape rerun.
