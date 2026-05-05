# M6.24 Failed Long-Command Repair Budget Repair - 2026-05-03

## Trigger

Same-shape `compile-compcert` speed rerun:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-execution-contract-compile-compcert-1attempt-20260503-1155/result.json`

Observed:

- Harbor reward `0.0`, runner errors `0`.
- `mew-report.work_exit_code=1`.
- External verifier failed because `/tmp/CompCert/ccomp` was missing.
- The managed source-acquisition command failed terminally with curl exit `22`
  for a missing release URL.
- mew proposed a changed bounded source-authority probe, but
  `long_command_budget_blocked` rejected its `120s` timeout because
  `repair_failed_long_command` inherited `minimum_repair_seconds=600`.

codex-ultra classified the gap as
`failed_long_command_repair_timeout_floor_overconstrained` in
`tool_runtime_budget` and recommended repairing now.

## Reproduction

The exact saved artifact was reproduced before code repair:

```bash
./mew replay terminal-bench \
  --job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-execution-contract-compile-compcert-1attempt-20260503-1155 \
  --task compile-compcert \
  --assert-long-build-status blocked \
  --assert-current-failure long_command_failed \
  --assert-recovery-action repair_failed_long_command \
  --assert-mew-exit-code 1 \
  --assert-external-reward 0 \
  --json
```

The replay passed.

`mew dogfood --scenario m6_24-terminal-bench-replay` initially failed because
the scenario still expected the older fixed
`compatibility_override_probe_missing` blocker. The scenario now accepts
explicit `--terminal-bench-assert-*` flags for existing Harbor artifacts. With
those assertions, the exact artifact dogfood reproduction passed.

## Repair

`repair_failed_long_command` keeps the generic long-build floor for actual
build repairs, but allows bounded changed repair probes for early non-build
stages:

- `diagnostic`: `30s`
- `source_acquisition`: `60s`
- `source_authority`: `60s`
- `configure`: `120s`

The 600s floor remains for build/runtime/artifact work, and identical failed
idempotence keys remain blocked.

## Validation

Passed:

- `uv run pytest --no-testmon -q tests/test_work_session.py -k 'long_command_budget_policy_allows_short_source_acquisition_probe_after_terminal_failure or long_command_budget_policy_keeps_long_floor_for_failed_build_repair or long_command_budget_policy_blocks_identical_failed_source_acquisition_repeat or long_command_budget_policy_allows_repaired_command_after_failed_source_acquisition'`
- `uv run pytest --no-testmon -q tests/test_dogfood.py -k 'terminal_bench_replay or terminal_bench_replay_assertions'`
- `./mew replay terminal-bench ...` on the exact failed artifact.
- `./mew dogfood --scenario m6_24-terminal-bench-replay ...` on the exact
  failed artifact.
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py -k 'long_command_failed or repair_failed_long_command or source_acquisition or long_command_budget_policy or minimum_repair_seconds'`
- `uv run ruff check src/mew/cli.py src/mew/dogfood.py src/mew/commands.py src/mew/long_build_substrate.py tests/test_dogfood.py tests/test_work_session.py`
- codex-ultra review session `019debd8-a8c8-7d91-8fcf-27f147c89eb4`
  requested one post-cap minimum enforcement fix, then approved the repaired
  diff with `RISK_LEVEL: low`.

## Next

Run the normal pre-speed operation and then exactly one same-shape
`compile-compcert` speed_1.
