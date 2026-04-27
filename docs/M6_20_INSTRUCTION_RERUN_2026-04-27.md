# M6.20 Instruction-Consuming Rerun

Date: 2026-04-27 JST

Status: instruction ingestion and report capture repaired; score optimization
not started.

## Runs

Initial instruction-consuming rerun:

- Job: `mew-smoke-instruction-entrypoint`
- Result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-instruction-entrypoint/result.json`
- Task artifact:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-instruction-entrypoint/make-mips-interpreter__GCUfzML/`
- Trials: 1
- Exceptions: 0
- Mean score: 0.0
- Finding: command transcript showed the full Terminal-Bench instruction was
  passed to `mew-smoke` and `exit_code=0`, but host-side `summary.json` reported
  fields as `unavailable` because `mew-report.json` was not visible in the host
  artifact directory.

Repaired stdout-fallback rerun:

- Job: `mew-smoke-stdout-report-fallback`
- Result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-stdout-report-fallback/result.json`
- Task artifact:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-stdout-report-fallback/make-mips-interpreter__6RPP6iX/`
- Trials: 1
- Exceptions: 0
- Mean score: 0.0
- Host report:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-stdout-report-fallback/make-mips-interpreter__6RPP6iX/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- Host summary:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-stdout-report-fallback/make-mips-interpreter__6RPP6iX/agent/terminal-bench-harbor-smoke/unknown-task/summary.json`

## Repair

`mew-smoke` now prints the same report JSON that it writes to `--report`.
`MewTerminalBenchAgent.populate_context_post_run` reads host-side
`mew-report.json` first, then falls back to parsing stdout JSON when the host
file is missing. If stdout recovery succeeds, it writes a host-side
`mew-report.json` and then produces `summary.json` from that recovered report.

This keeps the wrapper useful when the benchmark command writes files inside the
task container but only stdout is directly visible to the host wrapper.

## M6.18 Classification

- Harbor runner failure: not observed. Both instruction-consuming runs have
  `n_errors=0` and empty exception stats.
- Instruction ingestion failure: not observed. The first command transcript
  contains the full `make-mips-interpreter` instruction.
- Artifact/report capture failure: observed in the first rerun and repaired by
  stdout report fallback.
- Benchmark quality failure: still observed. The repaired rerun remains score
  `0.0` because `mew-smoke` is intentionally a capture-only smoke entrypoint.
- Task-solving failure: not yet measured for the real implementation lane. A
  capture-only smoke entrypoint cannot produce `/tmp/frame.bmp`, so the verifier
  failure is expected and should not be scored as mew's final coding ceiling.

Route: M6.20 can now move from harness/report capture into a real
instruction-consuming implementation attempt or a deliberately bounded
task-spec repair. Broad prompt/tool optimization is still premature until the
next run uses a real implementation lane rather than capture-only `mew-smoke`.

## Validation

Focused local validation:

```sh
uv run pytest -q tests/test_terminal_bench_smoke.py tests/test_harbor_terminal_bench_agent.py --no-testmon
uv run ruff check src/mew/terminal_bench_smoke.py tests/test_terminal_bench_smoke.py .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py
git diff --check
uv run mew-smoke --instruction 'diagnostic instruction' --report /tmp/mew-smoke-report.json --artifacts /tmp/mew-smoke-artifacts
```

Observed local result: focused pytest `9 passed`, ruff passed, diff check
passed, and `mew-smoke` printed parseable report JSON to stdout.
