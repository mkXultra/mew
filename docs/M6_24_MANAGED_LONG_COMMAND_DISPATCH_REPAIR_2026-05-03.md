# M6.24 Managed Long-Command Dispatch Repair

Date: 2026-05-03 JST

Selected chain:

```text
M6.24 -> long_dependency/toolchain gap -> long-command continuation dispatch not engaged -> managed dispatch repair -> same-shape speed_1
```

## Trigger

The source-authority path-correlation speed rerun moved the prior reducer
blocker, but the continuation substrate was still not exercised in production:

- `source_authority=satisfied`
- `/tmp/CompCert/ccomp` existed and was executable
- external verifier failed default runtime linking with `cannot find -lcompcert`
- `long_command_runs=[]`
- `timeout_shape.latest_long_command_run_id=null`

codex-ultra classified this as `long_command_continuation_dispatch_not_engaged`
in `docs/REVIEW_2026-05-03_M6_24_SOURCE_AUTHORITY_RERUN_CLASSIFICATION_CODEX.md`.

## Change

- `run_command` and `run_tests` now dispatch through `ManagedCommandRunner`
  when `long_command_budget.action_kind` is `start_long_command`,
  `resume_idempotent_long_command`, or `poll_long_command`.
- Running/yielded managed command snapshots keep nonterminal
  `CommandEvidence.status` (`running` / `yielded`) with `finish_order=0`, while
  the work-loop tool call can still complete non-failingly and continue the
  model loop.
- Terminal poll/finalize snapshots create separate terminal evidence and update
  the same `LongCommandRun`.
- Managed command polling now enforces the command timeout instead of allowing a
  background process to exceed its effective timeout between polls.
- Long-build budget policy now preserves reserve for `dependency_generation`
  compound commands, which covers commands that do `configure`, `make depend`,
  final target build, and smoke proof in one step.

## Validation

- `uv run pytest -q tests/test_work_session.py -k 'managed_long_command' --no-testmon`
  -> `4 passed`
- `uv run pytest -q tests/test_toolbox.py tests/test_long_build_substrate.py tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py tests/test_acceptance.py --no-testmon`
  -> `1311 passed`, `1 warning`, `67 subtests passed`
- `uv run ruff check .` -> passed
- `git diff --check` -> passed
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl` -> passed

## Review

codex-ultra session `019de952-1bf3-7513-820a-ecb5eada4139` initially requested
changes because running snapshots were recorded as completed command evidence.
After fixing that invariant and adding `run_tests`, nonterminal/terminal
evidence, and timeout-enforcement coverage, codex-ultra returned:

```text
STATUS: APPROVE
```

The same review stated that one same-shape `compile-compcert` speed_1 is the
next correct action.

## Next

Run exactly one same-shape `compile-compcert` speed_1 before `proof_5` or broad
measurement.
