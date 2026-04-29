# DESIGN 2026-04-29 - M6.24 Hard-Runtime Verifier Strategy

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> hard-runtime verifier strategy repair -> rerun make-doom-for-mips same shape`

## Trigger

The hard-task contract capsule rerun kept the task contract and avoided false
stub completion, but `make-doom-for-mips` stayed 0/5. codex-ultra review in
`docs/REVIEW_2026-04-29_M6_24_HARD_CONTRACT_RERUN_NEXT.md` selected
`VM-strategy` as the next primary blocker:

- real source-built artifacts appeared
- exact `node vm.js` failed with PC/opcode/startup signatures
- `/tmp/frame.bmp` stayed missing
- reports preserved `task_done=false`

The next useful substrate behavior is not another broad run. It is to preserve
runtime failure signatures in reentry so the model maps the artifact and
runtime source before another rebuild.

## v0 Repair

Implemented in:

- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/reasoning_policy.py`

Behavior:

- failed `run_command` / `run_tests` verifier output can now produce
  `verifier_failure_repair_agenda.runtime_contract_gap`
- runtime gaps classify into:
  - `loader_entry`
  - `unsupported_opcode_instruction_set`
  - `syscall_runtime`
  - `expected_artifact`
- the agenda preserves:
  - command and cwd
  - exit code
  - PC
  - opcode or special function
  - expected `/tmp/...` artifacts
  - compact failure lines
  - recommended artifact-mapping tools: `readelf`, `nm`, `objdump`,
    `addr2line`
- `format_work_session_resume()` surfaces the runtime gap and signature
- the work-loop prompt tells the model to preserve the runtime signature and
  inspect runtime source plus artifact mapping before another rebuild
- reasoning policy now treats MIPS/ELF/toolchain/provided-source/VM-style
  implementation tasks as `high` effort rather than small implementation

This is generic arbitrary-workspace behavior. It does not encode Doom,
Terminal-Bench, or `vm.js` special solvers.

## Validation

Focused validation:

```sh
uv run pytest tests/test_work_session.py -k 'runtime_contract_gap or verifier_failure_repair_agenda or hard_task_implementation_contract' --no-testmon -q
uv run pytest tests/test_reasoning_policy.py --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py src/mew/reasoning_policy.py tests/test_work_session.py tests/test_reasoning_policy.py
```

Observed:

- `3 passed, 766 deselected`
- `20 passed`
- `ruff`: all checks passed

## Same-Shape Rerun Gate

Next proof should rerun:

`terminal-bench/make-doom-for-mips`

Accept as improved only if:

- `runtime_contract_gap` appears in failed VM/runtime reentry when applicable
- no surrogate/stub completion returns
- no ordinary package/toolchain permission wait dominates the run
- at least one trial gets past the current VM startup/opcode blocker, writes
  `/tmp/frame.bmp`, or improves reward

If the rerun remains 0/5 with the same signatures, keep M6.24 in improvement
phase and choose the next generic blocker from the recorded evidence.
