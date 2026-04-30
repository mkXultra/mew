# M6.24 `compile-compcert` OAuth-Refresh Proof 5

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> proof-infra -> Codex OAuth refresh validation -> rerun long_dependency_timed_out_artifact_proof_calibration proof_5 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-oauth-refresh-compile-compcert-5attempts-seq-20260430-2256/result.json
```

## Summary

- requested shape: `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- frozen Codex target: `5/5`
- completed valid trials before stop: `2`
- score on valid completed trials: `1/2`
- cancelled trials: `1` operator cancellation after `5/5` became impossible
- Harbor root mean at stop: `0.333` because the cancelled trial is counted as an error
- close-gate result: missed

This rerun validates the proof-infrastructure repair: the previous
`HTTP 401 token_expired` failure did not recur. It does not close the
`compile-compcert` gap.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__B3St4K6` | `1.0` | Built `/tmp/CompCert/ccomp`, built and installed `runtime/libcompcert.a`, passed default smoke and external verifier. |
| `compile-compcert__zW8RbrX` | `0.0` | Built `/tmp/CompCert/ccomp`, then default smoke failed with `/usr/bin/ld: cannot find -lcompcert`; the session exhausted wall/model budget before the runtime-library recovery turn. |
| `compile-compcert__oQGB2eF` | n/a | Cancelled intentionally after the close target was impossible. |

## Failure Classification

This is not another OAuth or source-identity failure. It is also not clean
evidence for adding one more runtime-link prompt sentence: older v0.4, v0.6,
and v0.7 repairs already teach runtime link/default path/runtime install target
handling, and the passing contrast trial followed that route successfully.

The distinctive failure is budget:

```text
stop_reason: wall_timeout
elapsed_seconds: 1725.127
max_wall_seconds: 1740
remaining_seconds: 14.873
available_model_timeout_seconds: 2.437
```

The failed trial saw the recoverable linker error but had no meaningful model
turn left to run the same short runtime-library recovery used by the passing
contrast. `codex-ultra` review session `019ddee4-07a6-7e80-8ee8-038527eb88a4`
classified the next repair as tool/runtime:
`long_dependency_final_recovery_budget_after_failed_validation`.

## Repair

Implemented a generic long-build recovery-budget reserve for `mew work`
tool calls:

- long source-build/toolchain commands with long timeouts and final validation
  smoke now reserve `60s` of wall budget instead of only the normal `2s` tool
  reserve;
- the reserve is applied only when the task/command looks like a long
  dependency/toolchain build and the command includes both build and final
  validation markers;
- if a recent runtime-link/runtime-install blocker is already visible, the
  follow-up recovery command can spend the reserved budget instead of being
  re-reserved and blocked;
- regular short tool calls keep the old behavior.

Files:

- `src/mew/commands.py`
- `tests/test_work_session.py`

Focused validation:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --no-testmon tests/test_work_session.py -k 'wall_budget or wall_timeout or long_build_validation_command' -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/mew/commands.py tests/test_work_session.py
```

Result:

- focused tests: `8 passed`
- ruff: passed
- broader regression: `tests/test_work_session.py tests/test_codex_api.py
  tests/test_model_backends.py` passed (`858 passed`, one multiprocessing
  warning)
- `codex-ultra` review session `019ddeed-31bf-7373-a6f8-b417b0865203`:
  `APPROVE` after two required-change rounds covering recovery-command
  re-reservation risks

## Next

Run a one-trial same-shape `compile-compcert` speed proof with refreshable
`~/.codex/auth.json`.

Pass condition:

- external verifier passes; or
- the failure moves to a new blocker while preserving enough recovery budget.

Do not resume broad measurement before recording that same-shape rerun.
