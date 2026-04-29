# DESIGN 2026-04-29 - M6.24 Final Verifier State Transfer

Controller chain:

`M6.24 -> hard_task profile v0 -> hard_runtime_final_verifier_state_transfer -> speed-rerun make-doom-for-mips`

## Trigger

The runtime artifact freshness rerun in
`docs/M6_24_RUNTIME_FRESHNESS_RERUN_2026-04-29.md` stayed 0/5 after removing
the stale `/tmp/frame.bmp` short-circuit. All external verifiers waited for a
fresh frame and failed because no final `/tmp/frame.bmp` existed.

One trial also recorded an internal state like `last verification passed
exit=0: node vm.js`, while the external verifier still failed. This means
command success alone is not enough for hard runtime tasks. The deliverable
state must transfer to the external verifier's fresh command shape.

## Architecture Fit

Decision: `implementation_profile`.

Authoritative lane: `implementation/tiny`.

This is a finish/reentry guard inside the implementation lane. The task still
has one authoritative output: code/runtime state that the external verifier can
run. No new lane is introduced.

## v0 Repair

Implemented in:

- `src/mew/acceptance.py`
- `src/mew/work_session.py`
- `src/mew/work_loop.py`

Behavior:

- `acceptance_finish_blocker()` now blocks `task_done=true` for fresh-runtime
  tasks when a required `/tmp/...` artifact is not grounded by cited tool
  output
- command exit 0 is not enough when the task says the fresh runtime command
  writes an artifact such as `/tmp/frame.bmp`
- work-session resume now surfaces `final_verifier_state_transfer` when the
  latest successful runtime command did not prove the expected artifact
- THINK guidance says hard runtime/VM tasks must prove artifact creation by the
  final verifier-shaped command from the final cwd, or preserve the blocker
  instead of finishing

This repair is generic. It applies to frames, screenshots, logs, sockets, pid
files, and similar runtime artifacts created by final verifier-shaped commands.

## Validation

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or runtime_contract_gap' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `3 passed, 49 deselected`
- `4 passed, 768 deselected`
- `ruff`: all checks passed

## Speed-Rerun Gate

Next proof should be a one-trial speed-rerun, not `-k 5 -n 5`:

`terminal-bench/make-doom-for-mips`

Accept as directionally improved if one trial shows either:

- reward improvement
- external verifier reaches or exceeds the previous best 2/3 proximity without
  stale-artifact timing failure
- no false finish after command exit 0 without artifact proof, with a clearer
  `final_verifier_state_transfer` or runtime blocker in the final report

Escalate to `-k 5 -n 5` only if the speed-rerun shows material improvement,
contradictory variance, or the decision ledger is ready to resume broad
measurement.
