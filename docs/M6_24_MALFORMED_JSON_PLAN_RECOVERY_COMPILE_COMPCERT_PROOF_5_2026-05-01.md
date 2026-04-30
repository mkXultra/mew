# M6.24 `compile-compcert` Malformed-JSON Recovery Proof 5

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> loop_recovery -> work_oneshot_malformed_json_plan_recovery proof_5 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-5attempts-seq-20260501-0220/result.json
```

## Summary

- requested shape: sequential `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- frozen Codex target: `5/5`
- completed valid trials before stop: `2`
- score on valid completed trials: `1/2`
- cancelled trials: `1` operator cancellation after `5/5` became impossible
- Harbor root mean at stop: `0.333` because the cancelled trial is counted as an error
- close-gate result: missed

The malformed-JSON recovery speed proof did not regress, and the first valid
completed proof trial passed. The failed valid trial did not show another
malformed structured-plan parse error. It reached the known
long-dependency/runtime recovery path, built `/tmp/CompCert/ccomp`, then failed
the default runtime link smoke with:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
```

The session then read `/tmp/CompCert/runtime/Makefile`, but the next four model
planning turns timed out under shrinking wall-clock ceilings while still using
full prompt context. The failed turn sequence had effective THINK timeouts of
approximately `43s`, `21s`, `10s`, and `5s`, with prompt sizes around `193k` to
`197k` chars. The session stopped on wall timeout before executing the obvious
runtime-library build/install recovery command.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__JgBZWVW` | `1.0` | Built `/tmp/CompCert/ccomp`; external verifier passed. |
| `compile-compcert__gHMYo7H` | `0.0` | Reached runtime-link recovery, but low-wall planning used full context and repeatedly timed out before recovery action. |
| `compile-compcert__m64NowY` | n/a | Cancelled intentionally after the close target was impossible. |

## Failure Classification

This is not another runtime-link prompt rule. The known blocker was already
visible in `long_dependency_build_state` as
`runtime_install_before_runtime_library_build`, and the previous policy already
said to build the shortest runtime-library target before retrying install and
default-link smoke.

The failure class is:

```text
gap_reason: work_timeout_ceiling_full_context_recovery_prompt
layer: model_context_budgeting
```

When wall-clock pressure forces a reduced model timeout, full-context planning
can be self-defeating: the model spends the remaining recovery budget reading a
large prompt and timing out rather than choosing the bounded continuation.

## Repair

Implemented a generic timeout-ceiling context repair:

- when `plan_work_model_turn()` is called with `timeout_ceiling=True`, a
  default `full` prompt context is converted to `compact_recovery`;
- compact recovery keeps the latest recovery state and decisions while trimming
  large historical tool/model context;
- the change is not task-specific and does not inspect Terminal-Bench,
  CompCert, command text, or verifier output.

Files:

- `src/mew/work_loop.py`
- `tests/test_work_session.py`

Focused validation:

```text
uv run pytest --no-testmon tests/test_work_session.py -k 'compact_recovery_under_wall_timeout_ceiling or compact_recovery_after_timeout_with_pending_steer' -q
uv run ruff check src/mew/work_loop.py tests/test_work_session.py
```

Result:

- focused tests: `2 passed`
- ruff: passed
- `codex-ultra` review session `019ddfa4-889a-7d72-a789-239af7ce2a2b`:
  `APPROVE`

## Next

Run a one-trial same-shape `compile-compcert` speed proof with refreshable
`~/.codex/auth.json`. Do not resume broad measurement. If the speed proof
passes, return to resource-normalized proof_5. If it misses, read
`docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` before another repair.
