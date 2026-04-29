# M6.24 Hard-Task Profile Speed Rerun: make-mips-interpreter

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> profile generality sample -> speed_1 make-mips-interpreter`

## Run

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-profile-make-mips-interpreter-1attempt-20260429-1555/result.json`

Command shape:

- task: `terminal-bench/make-mips-interpreter`
- trials: `-k 1 -n 1`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: 30
- result: `0/1`
- exceptions: 0
- total runtime: 18m 0s

## What Improved

This is a stronger result than the earlier 0/5 batch score for this task:

- mew implemented `/app/vm.js`.
- The exact `node vm.js` command booted Doom.
- A fresh self-check removed `/tmp/frame.bmp`, ran `node vm.js`, and validated
  a recreated 640x400 32-bit top-down BMP.
- The external verifier passed:
  - `test_frame_bmp_exists`
  - `test_frame_bmp_similar_to_reference`

The remaining external verifier failure was:

```text
Expected text not found in output
assert b'I_InitGraphics: DOOM screen size: w x h: 320 x 200' in stdout_content
```

The captured stdout stopped before the expected `I_InitGraphics` line because
`/tmp/frame.bmp` already existed from mew's self-check. The verifier's wait loop
observed that stale file immediately, slept one second, and terminated the fresh
`node vm.js` process before enough stdout was emitted.

## Diagnosis

Gap class:

`runtime_artifact_freshness_discovered_artifact`

This is a generic implementation-lane failure, not a Terminal-Bench-specific
solver issue:

- the task text described generated frames but did not name `/tmp/frame.bmp`;
- mew discovered `/tmp/frame.bmp` from source and verifier evidence;
- the existing stale artifact freshness guard only recognized `/tmp/...`
  artifacts explicitly named in the task text;
- therefore finish did not block after self-verification left the discovered
  runtime artifact in place.

## Repair

Implemented immediately after this speed rerun:

- `src/mew/acceptance.py`
  - runtime artifact freshness and final-state gates now infer `/tmp/...`
    artifacts from verified checks and completed tool output when the task text
    contains a fresh runtime / generated-artifact shape.
- `src/mew/work_session.py`
  - `stale_runtime_artifact_risk` and `final_verifier_state_transfer` now infer
    discovered `/tmp/...` artifacts from completed runtime self-check output.
- tests:
  - `tests/test_acceptance.py`
  - `tests/test_work_session.py`

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `4 passed, 769 deselected`
- `ruff`: all checks passed

## Next Rerun

Run a `speed_1` same-shape rerun for `make-mips-interpreter`.

Accept as improved if:

- mew does not finish while leaving a discovered fresh-runtime artifact stale;
- if it self-checks `/tmp/frame.bmp`, it preserves evidence and cleans the
  stale artifact before finish;
- the external verifier no longer fails due early stdout termination from a
  pre-existing frame.

Do not escalate to `-k 5 -n 5` unless this speed rerun passes or shows a
material improvement that needs stability proof.
