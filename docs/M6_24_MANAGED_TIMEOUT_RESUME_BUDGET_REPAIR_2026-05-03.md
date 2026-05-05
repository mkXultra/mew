# M6.24 Managed Timeout Resume-Budget Repair

Date: 2026-05-03

## Input

Previous repair: `docs/M6_24_MANAGED_POLL_RESERVE_REPAIR_2026-05-03.md`

Live same-shape speed rerun:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416`
- Trial: `compile-compcert__znzCSRf`
- Result: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416/result.json`
- Agent report: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416/compile-compcert__znzCSRf/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- Verifier stdout: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416/compile-compcert__znzCSRf/verifier/test-stdout.txt`

Outcome:

- Harbor reward: `0.0`
- Runner errors: `0`
- `mew work` stopped with `wall_timeout`
- `resume.long_build_state.status`: `blocked`
- `current_failure.failure_class`: `build_timeout`
- `current_failure.stage`: `runtime_build`
- `allowed_next_action.kind`: `resume_idempotent_long_command`
- Required artifact still missing: `/tmp/CompCert/ccomp`

The previous poll-reserve blocker moved. The run reached a real managed
`make -j10 ccomp` build, made visible Coq build progress, and then timed out
before the required compiler artifact existed.

## Reproduction

Exact replay:

```bash
./mew replay terminal-bench \
  --job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416 \
  --task compile-compcert \
  --assert-long-build-status blocked \
  --assert-current-failure build_timeout \
  --assert-recovery-action resume_idempotent_long_command \
  --assert-external-reward 0 \
  --json
```

Status: pass.

Exact dogfood replay:

```bash
./mew dogfood --scenario m6_24-terminal-bench-replay \
  --terminal-bench-job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-managed-poll-reserve-compile-compcert-1attempt-20260503-1416 \
  --terminal-bench-assert-long-build-status blocked \
  --terminal-bench-assert-current-failure build_timeout \
  --terminal-bench-assert-recovery-action resume_idempotent_long_command \
  --terminal-bench-assert-external-reward 0 \
  --json
```

Status: pass.

## Classification

codex-ultra session: `019dec63-b7ff-7a31-9d54-661b13a6062c`

```text
GAP_CLASS: structural_tool_runtime_budget
GAP_REASON: timed_out_managed_long_command_resume_budget_not_preserved
DECISION: REPAIR_NOW
```

This is still a narrow long-build substrate issue. It is not yet a trigger for
the all-command generic managed-exec design slice because managed dispatch and
polling attached correctly; the remaining problem is timeout/resume budget
handling for an active long build.

## Repair Target

Implement a generic managed long-command timeout/resume-budget repair:

- When a managed long command times out after real progress and required
  artifacts are still missing, preserve and report truthful remaining wall
  budget.
- Do not spend repeated low-wall model turns after the system already knows the
  only useful action is a same-idempotence resume.
- Advertise `resume_idempotent_long_command` only when enough actual
  wall/model budget exists for a meaningful resume slice.
- If there is not enough budget, stop cleanly with typed
  `build_timeout` / resume-budget-exhausted evidence.

Do not add a CompCert-specific solver, a Terminal-Bench-specific parser, or
another broad shell classifier.

## Next Validation

Before another live speed rerun:

1. focused unit tests for timeout/resume-budget handling,
2. exact artifact replay above,
3. exact dogfood replay above,
4. scoped ruff and diff check,
5. codex-ultra implementation review.

Only after those pass, run exactly one same-shape `compile-compcert` speed_1.

## Validation

Local validation after the repair:

- `tests/test_long_build_substrate.py -k 'resume_budget_exhausted or timed_out_long_command_to_build_timeout_resume_decision'`: `2 passed`
- `tests/test_work_session.py -k 'timed_out_managed_long_command_caps_resume_budget_to_prior_wall_slice or long_command_budget_policy_blocks_resume_budget_exhausted_action or long_command_budget_policy_blocks_same_timeout_resume or managed_poll_preserves_logical_final_proof_reserve_for_later_repair'`: `4 passed`
- exact artifact replay with repaired assertion `resume_budget_exhausted`: pass
- exact dogfood replay with repaired assertion `resume_budget_exhausted`: pass
- `uv run ruff check src/mew/commands.py src/mew/long_build_substrate.py src/mew/work_session.py tests/test_long_build_substrate.py tests/test_work_session.py`: pass
- `tests/test_long_build_substrate.py`: `366 passed`
- `tests/test_work_session.py -k 'long_command or wall_timeout or managed or dependency_generation_diagnostic_budget'`: `38 passed`, `12 subtests passed`
- `tests/test_terminal_bench_replay.py tests/test_dogfood.py -k 'terminal_bench_replay'`: `5 passed`
- `jq empty proof-artifacts/m6_24_gap_ledger.jsonl`: pass
- `git diff --check`: pass

Review status: codex-ultra session `019dec74-191f-75b1-97f0-da6e0ed306fe`
returned `STATUS: APPROVE`. The only minor note was to add a direct policy
test for `resume_budget_exhausted`; that test was added and passed.

Next action: commit this repair, then run the pre-speed operation and exactly
one same-shape `compile-compcert` speed_1. Do not run `proof_5` or broad
measurement first.
