# M6.24 Implement V2 Scoped Rebaseline

Date: 2026-05-06

Purpose: make M6.24 measure the lane that should become the normal coding
body. Historical `implement_v1` results remain useful repair evidence, but they
must not close M6.24 after `implement_v2` became runnable.

## Decision

M6.24 now runs an `implement_v2` scoped rebaseline before spending more
same-shape close proof budget.

The active scope is still the 25 Terminal-Bench 2.0 tasks from
`docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`.

For each scoped task:

1. Run one `speed_1` with `selected_lane=implement_v2`.
2. Record lane id, runtime id, artifact path, runner errors, reward, and replay
   status.
3. If the run misses, is harness-invalid, lacks replayable artifacts, or
   exposes a structural lane gap, stop broad measurement and repair that gap.
4. Reproduce any miss with `mew replay terminal-bench` and
   `mew dogfood --scenario m6_24-terminal-bench-replay` before code repair.
5. After repair, run focused UT, replay, dogfood, any matching emulator, then
   one same-shape `speed_1`.
6. Spend `proof_5` only for close candidates, variance-sensitive repairs, or
   when the controller is ready to resume measurement.

This means `build-cython-ext` is currently a passing `speed_1` candidate, not a
reason to immediately rerun another `speed_1`. Its `proof_5` is deferred until
the rebaseline controller deliberately chooses close proof budget.

## Command Shape

Use the same Harbor wrapper as the passing `build-cython-ext` proof, with the
task-specific cwd from the task contract:

```text
harbor run -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/<task> -k 1 -n 1 -y \
  --agent-timeout-multiplier 2 \
  --job-name mew-m6-24-v2-rebaseline-<task>-speed1-<timestamp> \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-<task>-speed1-<timestamp> \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak command_cwd=<task-cwd> \
  --ak command_template='mew work --oneshot ... --work-guidance selected_lane=implement_v2 ...'
```

Do not count a run as v2 evidence unless the mew report/replay metadata records
`lane=implement_v2` (or the equivalent selected-lane action) and
`runtime_id=implement_v2_model_json_tool_loop`.

## Current V2 Rebaseline Table

| Task | Codex target | v2 speed_1 status | Evidence | Next |
|---|---:|---|---|---|
| `build-cython-ext` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0312-closeout` | proof_5 deferred until controller selects close proof |
| `circuit-fibsqrt` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-circuit-fibsqrt-speed1-20260506-0335` | proof_5 deferred until controller selects close proof |
| `cobol-modernization` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-cobol-modernization-speed1-20260506-0348` | proof_5 deferred until controller selects close proof |
| `distribution-search` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-distribution-search-speed1-20260506-0350` | proof_5 deferred until controller selects close proof |
| `feal-differential-cryptanalysis` | 5/5 | pass 1/1 after model-json repair | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair` | proof_5 deferred until controller selects close proof |
| `feal-linear-cryptanalysis` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426` | proof_5 deferred until controller selects close proof |
| `fix-git` | 5/5 | pending | none | run v2 speed_1 |
| `hf-model-inference` | 5/5 | pending | none | run v2 speed_1 |
| `kv-store-grpc` | 4/5 | pending | none | run v2 speed_1 |
| `largest-eigenval` | 5/5 | pending | none | run v2 speed_1 |
| `make-doom-for-mips` | 1/5 | pending | none | run v2 speed_1 |
| `make-mips-interpreter` | 3/5 | pending | none | run v2 speed_1 |
| `merge-diff-arc-agi-task` | 5/5 | pending | none | run v2 speed_1 |
| `openssl-selfsigned-cert` | 5/5 | pending | none | run v2 speed_1 |
| `polyglot-c-py` | 5/5 | pending | none | run v2 speed_1 |
| `polyglot-rust-c` | 4/5 | pending | none | run v2 speed_1 |
| `prove-plus-comm` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-true-implement-v2-prove-plus-comm-1attempt-20260506-0204` | proof_5 deferred until controller selects close proof |
| `pypi-server` | 5/5 | pending | none | run v2 speed_1 |
| `pytorch-model-cli` | 5/5 | pending | none | run v2 speed_1 |
| `pytorch-model-recovery` | 5/5 | pending | none | run v2 speed_1 |
| `raman-fitting` | 2/5 | pending | none | run v2 speed_1 |
| `regex-chess` | 5/5 | pending | none | run v2 speed_1 |
| `reshard-c4-data` | 5/5 | pending | none | run v2 speed_1 |
| `schemelike-metacircular-eval` | 5/5 | pending | none | run v2 speed_1 |
| `write-compressor` | 5/5 | pending | none | run v2 speed_1 |

## Repair Notes

- `feal-differential-cryptanalysis` first v2 attempt
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0359`
  scored `0.0` with runner errors `0` because `implement_v2` stopped on a
  first-turn `model_json_parse_error` and the saved report had no replayable
  v2 artifact. The generic repair makes JSON extraction accept the first valid
  object before trailing text, records model JSON failures as replayable v2
  lane failures, and lets terminal-bench replay/dogfood classify the historical
  miss as `repair model_json parse failure before another live speed run`.
  Focused UT, exact replay, and exact dogfood passed before the same-shape
  rerun.
- The same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair`
  scored reward `1.0` with runner errors `0`, total runtime `5m48s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=8`, `tool_calls=11`, `tool_results=11`,
  and external verifier `1/1` passing. Exact replay and matching
  terminal-bench replay dogfood passed.
- `feal-linear-cryptanalysis` live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426`
  scored reward `1.0` with runner errors `0`, total runtime `4m19s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=5`, `tool_calls=8`, `tool_results=8`,
  and external verifier `1/1` passing. Exact replay and matching
  terminal-bench replay dogfood passed.

## Repair Trigger

Pause the rebaseline and repair immediately when any of these happens:

- `speed_1` reward is `0.0` on a task where the harness launched mew correctly.
- Harbor runner error is nonzero or the mew report is missing.
- The task is harness-invalid and the invalidity is in mew's wrapper,
  task-cwd selection, auth mount, or artifact layout.
- Replay or dogfood cannot express the failure shape.
- The run exposes an implementation-lane structural gap, such as tool surface,
  managed exec lifecycle, finish gate, acceptance evidence, context/reentry, or
  repair-loop behavior.

Do not continue measuring unrelated tasks through a known structural lane gap.
That would collect more low-quality evidence instead of improving mew.

## Close Rule

A task is "v2 rebaseline measured" after a clean `speed_1` with replayable
artifacts. A task is "v2 close-candidate passed" only after the relevant
`proof_5` or documented lower-cost close gate.

M6.24 as a milestone can only close when:

- all 25 scoped tasks have `implement_v2` evidence,
- below-target tasks have classified repair routes or explicit deferrals,
- close candidates are validated against the frozen Codex target shape, and
- no accepted structural lane blocker remains open.
