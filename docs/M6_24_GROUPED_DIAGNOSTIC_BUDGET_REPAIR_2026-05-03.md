# M6.24 Grouped Diagnostic Budget Repair - 2026-05-03

## Trigger

Same-shape `compile-compcert` speed rerun:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-typed-diagnostic-budget-compile-compcert-1attempt-20260503-1653/result.json`

Observed:

- Harbor reward `0.0`, runner errors `0`.
- `mew-report.work_exit_code=1`.
- External verifier failed because `/tmp/CompCert/ccomp` was missing.
- mew reached a real source tree and failed configure because distro Coq
  `8.18.0` is unsupported for CompCert `3.13.1`, and Menhir API location was
  not visible.
- The next raw model action was typed as read-only diagnostic, but the budget
  gate inherited the previous long-command stage (`configure`) and blocked the
  60s diagnostic behind a larger repair floor.

This is the same structural class as the prior typed read-only diagnostic
repair, but with a more realistic command shape: shell grouping,
`./configure -help`, pipelines, and `/dev/null` redirects.

## Reproduction

The exact saved artifact reproduces before repair:

```bash
./mew replay terminal-bench \
  --job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-typed-diagnostic-budget-compile-compcert-1attempt-20260503-1653 \
  --task compile-compcert \
  --assert-long-build-status blocked \
  --assert-current-failure long_command_failed \
  --assert-mew-exit-code 1 \
  --assert-external-reward 0 \
  --json
```

`mew dogfood --scenario m6_24-terminal-bench-replay` also reproduces the
artifact-level failure.

Most importantly, the new emulator catches the actual policy defect without
rerunning Harbor:

```bash
./mew dogfood \
  --scenario m6_24-compile-compcert-emulator \
  --terminal-bench-job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-typed-diagnostic-budget-compile-compcert-1attempt-20260503-1653 \
  --json
```

Before the repair, the emulator observed `diagnostic_budget=false`,
`minimum_timeout_seconds=600.0`, and `long_command_budget_blocked`.

## Repair

The read-only diagnostic predicate now accepts this shell-diagnostic surface:

- leading/trailing shell grouping syntax around an executable name, such as
  `(./configure ... )`;
- `./configure -help` as a help-only diagnostic when the typed execution
  contract says `purpose=diagnostic` and `risk_class=read_only`;
- simple read-only shell loop control (`for ... in ...`, `do <diagnostic>`,
  `done`) when the typed execution contract says the action is a read-only
  diagnostic;
- existing conservative guards still reject write-shaped redirects except
  `/dev/null` and do not trust arbitrary shell text as diagnostic.

This is still a narrow budget gate. It is not a broad shell classifier and not
a CompCert solver.

## Validation

Passed after repair:

- `uv run pytest --no-testmon -q tests/test_work_session.py -k 'compile_compcert_read_only_diagnostic or dependency_generation_diagnostic_after_build_failure or blocks_write_shaped_diagnostic'`
- `uv run ruff check src/mew/commands.py tests/test_work_session.py`
- `mew dogfood --scenario m6_24-compile-compcert-emulator --terminal-bench-job-dir <speed-job> --json`

The live-artifact emulator now observes `diagnostic_budget=true`,
`minimum_timeout_seconds=30.0`, and no wall/budget block for the raw diagnostic
action.

## Follow-up Speed Rerun

The first speed rerun after the initial grouped diagnostic fix was:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-grouped-diagnostic-budget-compile-compcert-1attempt-20260503-1714/result.json`

It scored `0/1` with runner errors `0`. Replay and terminal-bench dogfood
passed. The emulator caught the remaining defect before another Harbor run:
the next raw model action was still a typed read-only diagnostic, but it used
`for t in ...; do printf ...; command -v ...; done`, which the previous
allowlist treated as non-diagnostic shell text. The repair now accepts this
bounded shell-control shape.

The next same-shape speed proof did expose another read-only diagnostic parser
false negative:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-shell-loop-diagnostic-compile-compcert-1attempt-20260503-1731/result.json`

That triggered the stop rule. The follow-up repair is no longer a one-off
parser case. It normalizes shell-control prefixes for typed read-only
diagnostics (`if`, `then`, `else`, `elif`, `while`, `until`, `do`, plus
control-only terminators such as `fi`, `done`, `esac`) and recursively validates
the executable command inside the control branch. Side-effecting payloads such
as `if ...; then make ccomp; fi` still keep the long repair floor.

New stop rule: if the next same-shape speed proof exposes another read-only
diagnostic parser false negative after shell-control normalization, stop local
budget-gate work and open a separate diagnostic-contract redesign milestone.
At that point the narrow predicate is no longer the right abstraction.

## Next

Run the full pre-speed operation again:

1. focused UT / local validation
2. exact `mew replay terminal-bench`
3. exact `mew dogfood --scenario m6_24-terminal-bench-replay`
4. exact `mew dogfood --scenario m6_24-compile-compcert-emulator`

Only after all four pass, spend exactly one same-shape `compile-compcert`
speed_1. Do not run `proof_5` or broad measurement first.
