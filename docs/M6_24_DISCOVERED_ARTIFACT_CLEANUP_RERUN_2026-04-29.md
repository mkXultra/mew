# M6.24 Discovered Artifact Cleanup Speed Rerun

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_artifact_freshness_discovered_artifact -> speed_1 make-mips-interpreter`

## Run

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-discovered-artifact-make-mips-interpreter-1attempt-20260429-1620/result.json`

Command shape:

- task: `terminal-bench/make-mips-interpreter`
- trials: `-k 1 -n 1`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: 30
- result: `0/1`
- exceptions: 0
- total runtime: 29m 41s

## What Happened

The v0.1 discovered-artifact repair did not improve reward, but the transcript
showed the task was essentially solved before handoff:

- mew implemented `/app/vm.js`.
- The exact `node vm.js` command exited 0.
- stdout included `I_InitGraphics: DOOM screen size: w x h: 320 x 200`.
- stdout included `saved frame 1 to /tmp/frame.bmp`.
- stdout included `vm complete, /tmp/frame.bmp size=1024054`.
- The final successful tool was #30.

The run then hit `wall_timeout` before the model could produce a final `finish`
turn or cleanup command. The external verifier started with the stale
`/tmp/frame.bmp` still present, terminated the fresh `node vm.js` process too
early, and failed the stdout assertion while the frame existence and image
similarity checks still passed.

## Diagnosis

Gap class:

`deferred_verify_runtime_artifact_cleanup_on_timeout`

This is a generic one-shot handoff problem:

- `mew work --oneshot --defer-verify` delegates final verification to an
  external harness.
- A successful self-verifier can create a runtime artifact that the external
  verifier expects to observe freshly.
- If wall budget expires after the successful self-verifier but before a final
  model cleanup/finish turn, the stale artifact survives handoff.
- The external verifier can then short-circuit on the stale artifact and miss
  stdout or timing evidence from a fresh run.

## Repair

Implemented immediately after this speed rerun:

- `src/mew/commands.py`
  - after building the final one-shot resume, `--defer-verify` now removes
    `/tmp/...` artifacts listed in `stale_runtime_artifact_risk` before
    returning control to the external harness;
  - the final one-shot report records `post_run_cleanup`;
  - if every stale runtime artifact was removed, the final report clears the
    resume-visible stale risk.
- `src/mew/acceptance.py` and `src/mew/work_session.py`
  - runtime artifact creation markers now include `saved frame` and
    `created /tmp/`, so discovered frame output such as
    `saved frame 1 to /tmp/frame.bmp` is recognized.
- tests:
  - `tests/test_acceptance.py`
  - `tests/test_work_session.py`

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or oneshot_cleanup' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `6 passed, 769 deselected`
- `ruff`: all checks passed

## Next Rerun

Run a `speed_1` same-shape rerun for `make-mips-interpreter`.

Accept as improved if:

- `post_run_cleanup.kind` is `deferred_verify_runtime_artifact_cleanup` when a
  self-verifier leaves `/tmp/frame.bmp`;
- the external verifier no longer fails because the frame pre-existed before
  the fresh `node vm.js` process emitted the required stdout;
- reward improves, or the failure moves to a new concrete runtime/verification
  condition.

Do not escalate to `-k 5 -n 5` unless this speed rerun passes or shows material
improvement that needs stability proof.
