# M6.24 `compile-compcert` Recovery-Budget Proof 5

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> tool/runtime -> long_dependency_final_recovery_budget_after_failed_validation proof_5 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-5attempts-seq-20260501-0055/result.json
```

## Summary

- requested shape: sequential `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- frozen Codex target: `5/5`
- completed valid trials before stop: `3`
- score on valid completed trials: `2/3`
- cancelled trials: `1` operator cancellation after `5/5` became impossible
- Harbor root mean at stop: `0.500` because the cancelled trial is counted as an error
- close-gate result: missed

The v1.0 recovery-budget speed proof did not regress, and two valid completed
trials passed. The miss was not a runtime-link or source-build ordering
recurrence. The failed valid trial stopped before doing work because the first
model turn returned malformed structured JSON and one-shot treated that parse
failure as terminal.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__ueFgWiJ` | `1.0` | Built `/tmp/CompCert/ccomp`, installed default runtime support, and external verifier passed. |
| `compile-compcert__qHktk5b` | `1.0` | Built `/tmp/CompCert/ccomp`, installed default runtime support, and external verifier passed. |
| `compile-compcert__thmeNZo` | `0.0` | `mew work` stopped at step 1 with `stop_reason=model_error`: `failed to parse JSON plan: Expecting ',' delimiter...`; no task work ran. |
| `compile-compcert__jTsuLdn` | n/a | Cancelled intentionally after the close target was impossible. |

## Failure Classification

This is a loop-recovery miss:

```text
gap_reason: work_oneshot_malformed_json_plan_recovery_missing
layer: loop_recovery
```

The existing one-shot recovery path already continued after transient backend
failures such as timeouts, incomplete reads, 5xx responses, and `response did
not contain assistant text`. The same transient behavior can occur when the
provider returns a truncated or malformed JSON plan. Generic invalid JSON
messages remain non-recoverable; the bounded repair recognizes the specific
`failed to parse JSON plan` structured-plan parser failure emitted by the model
backend.

## Repair

Implemented a bounded one-shot recovery extension:

- `recoverable_work_model_error()` now treats `failed to parse JSON plan` as a
  recoverable transient model error;
- generic `model returned invalid JSON` remains non-recoverable;
- one-shot sessions with `continue_after_remember` continue to the next model
  turn instead of failing the whole trial on the first malformed structured
  plan.

Files:

- `src/mew/commands.py`
- `tests/test_work_session.py`

Focused validation:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --no-testmon tests/test_work_session.py -k 'recoverable_work_model_error or continues_after_recoverable_model_error or does_not_continue_after_recoverable_model_error' -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/mew/commands.py tests/test_work_session.py
```

Result:

- focused tests: `3 passed`
- ruff: passed
- broader work-session regression: `826 passed`, one multiprocessing warning,
  `67 subtests passed`
- `codex-ultra` review session `019ddf49-e29d-7140-bd17-24c9d889c0a8`:
  `APPROVE`

## Next

Run a one-trial same-shape `compile-compcert` speed proof with refreshable
`~/.codex/auth.json`. Do not resume broad measurement. If the speed proof
passes, return to resource-normalized proof_5. If it misses, read
`docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` before another repair.
