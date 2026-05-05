# M6.24 Managed Poll Reserve Repair - 2026-05-03

## Evidence

Latest same-shape `compile-compcert` speed_1 after the dependency-generation
diagnostic budget repair:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-dependency-diagnostic-budget-compile-compcert-1attempt-20260503-1320`
- Trial: `compile-compcert__852quo8`
- Runner errors: `0`
- Harbor reward: `0.0`
- `mew-report.work_exit_code`: `1`
- `mew-report.work_report.stop_reason`: `long_command_budget_blocked`
- Verifier miss: `/tmp/CompCert/ccomp` missing

The previous repair moved the gate. mew reached a real managed CompCert build:
source acquisition recovered, MenhirLib was installed, configure/dependency
generation progressed, and `make -j"$(nproc)" ccomp` was still running under a
managed command.

## Reproduction

Exact artifact replay passed:

```bash
./mew replay terminal-bench \
  --job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-dependency-diagnostic-budget-compile-compcert-1attempt-20260503-1320 \
  --task compile-compcert \
  --assert-long-build-status in_progress \
  --assert-recovery-action poll_long_command \
  --assert-mew-exit-code 1 \
  --assert-external-reward 0 \
  --json
```

Exact dogfood passed with the same assertions:

```bash
./mew dogfood \
  --scenario m6_24-terminal-bench-replay \
  --terminal-bench-job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-dependency-diagnostic-budget-compile-compcert-1attempt-20260503-1320 \
  --terminal-bench-assert-long-build-status in_progress \
  --terminal-bench-assert-recovery-action poll_long_command \
  --terminal-bench-assert-mew-exit-code 1 \
  --terminal-bench-assert-external-reward 0 \
  --json
```

## Classification

codex-ultra classification session:
`019dec30-429e-77d2-a75d-a233bdeb3af7`.

- Gap class: `structural`
- Stable reason: `managed_long_command_poll_blocked_by_final_proof_reserve`
- Layer: `tool_runtime_budget`
- Repair: `REPAIR_NOW`

The final live step had an active `poll_long_command` recovery action, but the
work wall guard blocked it because about `40s` remained and the generic
long-build final-proof reserve was still `60s`. That reserve is correct for
starting, resuming, or repairing long commands, but it is too strict for polling
an already running managed command. Polling is the only path that can finalize
the command evidence; blocking it turns a recoverable nonterminal build into a
hard benchmark miss.

## Repair Route

Implement a narrow generic rule:

- For `poll_long_command` only, allow the poll to spend the long-build
  final-proof reserve.
- Keep the small tool guard.
- Keep `minimum_poll_seconds`.
- Keep the reserve for `start_long_command`, `resume_idempotent_long_command`,
  `recover_long_command`, and arbitrary new commands.
- Do not let nonterminal poll evidence satisfy artifact proof.
- Do not add Terminal-Bench or CompCert-specific logic.

## Validation Before Next Speed Run

1. Focused unit tests for poll reserve spending and non-poll reserve blocking.
2. Broader long-command budget/recovery subset.
3. Exact artifact replay and dogfood against the `20260503-1320` job with the
   assertions above.
4. Scoped ruff and JSONL/diff checks.
5. codex-ultra review.

Only after those pass, run exactly one same-shape `compile-compcert` speed_1.
Do not run `proof_5` or broad measurement first.

## Validation Result

- Focused regression:
  `6 passed, 910 deselected`
- Broader long-command/wall-timeout/managed/dependency-generation subset:
  `37 passed, 879 deselected, 12 subtests passed`
- Exact artifact replay: passed
- Exact artifact dogfood: passed
- Scoped ruff: passed
- `git diff --check`: passed
- codex-ultra review session `019dec39-7f1d-7901-af16-e2d1950b0a3e`:
  `STATUS: approve`, `SPEED_PROOF_NEXT: yes`
