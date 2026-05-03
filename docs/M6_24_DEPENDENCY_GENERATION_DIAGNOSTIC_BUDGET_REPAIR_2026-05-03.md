# M6.24 Dependency-Generation Diagnostic Budget Repair - 2026-05-03

## Trigger

Same-shape `compile-compcert` speed rerun:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-failed-long-command-repair-budget-compile-compcert-1attempt-20260503-1229`

Result:

- Harbor reward: `0.0`
- runner errors: `0`
- `mew work` exit: `1`
- external verifier: `/tmp/CompCert/ccomp` missing

The previous failed-long-command repair moved the gate. The run reached source
acquisition, configuration, dependency installation, and a real `make ccomp`
attempt. The latest failure was a missing generated/dependency file shape:

```text
Error: Can't find file ./Heaps.v
```

mew correctly selected `repair_failed_long_command`, but a read-only diagnostic
probe (`find`, `sed`, `make -n depend`) was blocked because the generic build
repair floor stayed at `600s`.

## Classification

`dependency_generation_diagnostic_budget_floor_overconstrained` in
`tool_runtime_budget`.

This is not a Terminal-Bench solver and not a CompCert-specific build rule. It
is a budget routing defect: after a terminal failed long command, read-only
diagnostics must be allowed to run with a short diagnostic floor, while
side-effecting dependency/build repair attempts must keep the long repair
floor.

codex-ultra classification session:

`019debf2-726f-7552-8ced-5130e69683bc`

Reviewer recommendation:

- repair generic failed-long-command budget routing so read-only diagnostics
  after dependency-generation failures use diagnostic budget
- preserve the `600s` floor for true build continuations and identical failed
  retries
- do not add a CompCert or Terminal-Bench specific solver

## Repair

`src/mew/commands.py` now distinguishes a short read-only diagnostic from a
side-effecting repair when calculating the failed-long-command repair minimum.
The predicate is segment/token based rather than substring based:

- every shell segment must be a known read-only diagnostic segment
- comments are stripped before `make -n` detection, so `make depend # -n`
  stays blocked
- unknown or wrapper segments such as `env make ...`, `ninja ...`, and
  `python -m build` stay blocked even if a later segment is read-only
- diagnostic commands include `find`, `grep`, `sed`, `cat`, `ls`, `pwd`,
  `test`, `wc`, `sha256sum`, list-only `tar`, and dry-run `make`
- side-effecting shapes such as package installs, extraction, configure,
  writes, and non-dry-run `make` stay on the true build repair floor
- write-shaped diagnostic-looking commands such as `find -delete` and
  `sed -i` stay on the true build repair floor
- no-whitespace file redirections such as `Makefile>/tmp/out`, `>>/tmp/out`,
  and `2>/tmp/err` stay on the true build repair floor; fd duplication such as
  `2>&1` remains allowed for read-only diagnostics
- typed execution contracts with diagnostic/read-only proof roles cannot force
  the diagnostic floor unless the actual command segments pass the read-only
  predicate

`src/mew/long_build_substrate.py` keeps the stage minima narrow:

- `diagnostic`: `30s`
- `source_acquisition`: `60s`
- `source_authority`: `60s`
- `configure`: `120s`

There is intentionally no blanket `dependency_generation` short floor. The
short floor is for read-only diagnostics, not for `make depend` or other
state-changing dependency-generation work.

## Validation

Reproduced the exact saved failure before repair selection:

- `./mew replay terminal-bench ... --assert-long-build-status blocked --assert-current-failure long_command_failed --assert-recovery-action repair_failed_long_command --assert-blocker dependency_generation_order_issue --assert-mew-exit-code 1 --assert-external-reward 0 --json`
- `./mew dogfood --scenario m6_24-terminal-bench-replay ...` with the same
  assertion shape

Focused validation on the repair:

- `uv run pytest --no-testmon -q tests/test_work_session.py -k 'long_command_budget_policy_allows_short_dependency_generation_diagnostic_after_build_failure or long_command_budget_policy_blocks_short_side_effecting_dependency_repair_after_build_failure or long_command_budget_policy_blocks_write_shaped_diagnostic_commands_after_build_failure or long_command_budget_policy_keeps_long_floor_for_failed_build_repair or long_command_budget_policy_allows_short_source_acquisition_probe_after_terminal_failure'`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py -k 'long_command_failed or repair_failed_long_command or source_acquisition or long_command_budget_policy or minimum_repair_seconds or dependency_generation_diagnostic'`
- `uv run ruff check src/mew/commands.py src/mew/long_build_substrate.py tests/test_work_session.py`

After codex-ultra's first two review rounds, adversarial regressions were added
for `make depend # -n`, wrapper/unknown mixed commands, write-shaped
diagnostics, typed diagnostic contracts on side-effecting build commands, and
no-whitespace stdout/stderr write redirections. The focused budget tests pass
with `7 passed` plus `9 subtests`; the broader long-command subset passes with
`16 passed` plus `12 subtests`.

## Next

codex-ultra review session `019debfe-47ae-71c0-b778-744d4aa70d99` approved
after two request-change rounds that tightened segment/token parsing and
no-whitespace redirection handling.

Run the pre-speed operation on current head, then exactly one same-shape
`compile-compcert` speed_1. Do not run `proof_5` or broad measurement first.
