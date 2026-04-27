# M6.20 Codex Reference Timing

Date: 2026-04-27 JST

Purpose: record a fresh Harbor timing sample for the same fixed Terminal-Bench
task used by M6.20 before comparing mew wall-budget behavior.

Important correction: Harbor's `-n` flag is concurrency (`--n-concurrent`), not
trial count. A leaderboard-shaped score run must use `--n-attempts 5` / `-k 5`
and may add `-n 5` only to run those attempts concurrently. This document now
records both the original one-attempt timing sample and the corrected
`-k 5 -n 5` run.

## Corrected Five-Attempt Parallel Run

Command:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -k 5 \
  -n 5 \
  -y \
  --job-name codex-reference-make-mips-5attempts-20260427-2017-auth \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

Artifacts:

- job result:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-make-mips-5attempts-20260427-2017-auth/result.json`
- per-trial results:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-make-mips-5attempts-20260427-2017-auth/make-mips-interpreter__*/result.json`

Observed result:

| Metric | Value |
| --- | ---: |
| Harbor total runtime | 20m 40s |
| Started -> finished | 2026-04-27 20:17:12 -> 20:37:52 JST |
| Attempts | 5 |
| Concurrent attempts | 5 |
| Harbor errors | 0 |
| Mean score | 0.0 |
| Pass@5 | 0.0 |
| Reward distribution | `0.0: 5` |
| Codex version | 0.125.0 |

Per-trial summary:

| Trial | Agent execution | Verifier | Verifier tests | Reward | Main failure |
| --- | ---: | ---: | ---: | ---: | --- |
| `2skyunR` | 10m38s | 18s | 2/3 | 0.0 | missing expected stdout |
| `BpPwTjS` | 7m09s | 27s | 2/3 | 0.0 | missing expected stdout |
| `V4fg6gL` | 6m53s | 25s | 2/3 | 0.0 | missing expected stdout |
| `VYENLEV` | 9m55s | 21s | 2/3 | 0.0 | missing expected stdout |
| `WzKMSvj` | 18m52s | 16s | 0/3 | 0.0 | no verifier-visible stdout/frame |

Interpretation:

- The corrected command shape worked: 5 attempts ran concurrently, with no
  Harbor exceptions.
- The fresh local result did **not** reproduce the frozen leaderboard target
  for Codex `0.121.0` / `gpt-5.5@openai`, which records 3/5 successes
  (60.0%) for this task.
- This run used Codex CLI `0.125.0`, installed by Harbor as `@openai/codex`
  latest, so it is a fresh local reference run rather than the exact frozen
  leaderboard environment.
- Four attempts were near misses: they produced `frame.bmp` and passed the
  image checks, but failed `test_vm_execution` because stdout did not contain
  `I_InitGraphics: DOOM screen size: w x h: 320 x 200` before the verifier
  terminated the process.
- One attempt internally reached a successful-looking local run during agent
  execution, but failed all verifier tests afterward. Treat that as a Codex
  attempt failure, not as a Harbor harness error.

M6.20 implication:

- User decision after this run: do not use `make-mips-interpreter` as the first
  M6.20 terminal gate. It is a useful stretch task, but too noisy for the first
  implementation-lane calibration because a fresh local Codex CLI 0.125.0
  reference run also scored 0/5.
- The M6.20 terminal gate moved to two Codex-frozen 5/5 implementation tasks:
  `fix-code-vulnerability` and `cancel-async-tasks`.
- Use this fresh 0/5 Codex run as local timing/failure evidence only. It shows
  that `make-mips-interpreter` is a hard benchmark with useful partial-failure
  structure, not that the task setup is invalid.
- For mew, the immediate comparison should include partial-credit diagnostics
  such as verifier test counts and failure class, not only the binary reward.

## Valid Single-Attempt Timing Sample

Command:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -n 1 \
  -y \
  --job-name codex-reference-make-mips-20260427-2003-auth \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

Artifacts:

- job result:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-make-mips-20260427-2003-auth/result.json`
- trial result:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-make-mips-20260427-2003-auth/make-mips-interpreter__Wsu3zcL/result.json`

Observed result:

| Metric | Value |
| --- | ---: |
| Harbor total runtime | 9m 51s |
| Result JSON started -> finished | 591.7s |
| Environment setup | 35.2s |
| Agent setup | 29.3s |
| Agent execution | 496.2s |
| Verifier | 17.5s |
| Attempts | 1 |
| Harbor errors | 0 |
| Mean score | 0.0 |
| Exception stats | `{}` |
| Codex version | 0.125.0 |
| Input tokens | 2426303 |
| Cached input tokens | 2332672 |
| Output tokens | 21147 |

Interpretation:

- A single Codex Harbor attempt for `make-mips-interpreter` takes roughly
  9-10 minutes end-to-end on this machine.
- The actual agent execution took roughly 8 minutes 16 seconds. This is the
  useful comparison point for mew's implementation-lane wall budget.
- Score remained 0.0 for this one attempt. This does not contradict the frozen
  leaderboard registry: `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`
  records `make-mips-interpreter` at 3/5 successes, 60.0%.
- The trial nearly solved the task but failed the verifier. It created
  `/app/vm.js`, generated `/tmp/frame.bmp`, and passed 1/3 verifier tests. The
  failures were missing expected stdout text in the verifier-captured run and
  frame similarity `0.8065 < 0.95`.

## Excluded Failed Run

An earlier refresh attempt omitted `CODEX_AUTH_JSON_PATH`:

- job:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-make-mips-20260427-1959/result.json`
- runtime: 2m 5s
- error: `NonZeroAgentExitCodeError`
- cause: Codex used an empty `OPENAI_API_KEY` fallback and returned 401.

This run is excluded from timing and score comparison except as an
auth-configuration guardrail.

## Historical Make-MIPS Comparable Shape

For a future stretch score comparison against the frozen Codex target for
`make-mips-interpreter`, use the same task with five attempts:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -k 5 \
  -n 1 \
  -y \
  --job-name codex-reference-make-mips-5attempts \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

Use `-n 5` only when intentionally running those attempts concurrently.

## Active M6.20 Gate Shape

For the active M6.20 terminal gate, run the two Codex-frozen 5/5 implementation
tasks rather than `make-mips-interpreter`:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/fix-code-vulnerability \
  -k 5 \
  -n 5 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high

CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/cancel-async-tasks \
  -k 5 \
  -n 5 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

## Fresh Local Codex Check For Active Gate Tasks

After the gate moved to the two Codex-frozen 5/5 tasks, both were rerun through
the same Harbor shape with local Codex CLI `0.125.0` and `gpt-5.5`.

### `fix-code-vulnerability`

Artifacts:

- job result:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-fix-code-vulnerability-5attempts-20260427-2052-auth/result.json`
- per-trial results:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-fix-code-vulnerability-5attempts-20260427-2052-auth/fix-code-vulnerability__*/result.json`

Observed result:

| Metric | Value |
| --- | ---: |
| Harbor total runtime | 3m 1s |
| Started -> finished | 2026-04-27 20:52:13 -> 20:55:14 JST |
| Attempts | 5 |
| Concurrent attempts | 5 |
| Harbor errors | 0 |
| Mean score | 1.0 |
| Pass@5 | 1.0 |
| Reward distribution | `1.0: 5` |

Interpretation: the fresh local Codex run reproduced the strict 5/5 target for
this task.

### `cancel-async-tasks`

Artifacts:

- job result:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-cancel-async-tasks-5attempts-20260427-2055-auth/result.json`
- per-trial results:
  `proof-artifacts/terminal-bench/harbor-smoke/codex-reference-cancel-async-tasks-5attempts-20260427-2055-auth/cancel-async-tasks__*/result.json`

Observed result:

| Metric | Value |
| --- | ---: |
| Harbor total runtime | 2m 35s |
| Started -> finished | 2026-04-27 20:55:27 -> 20:58:03 JST |
| Attempts | 5 |
| Concurrent attempts | 5 |
| Harbor errors | 0 |
| Mean score | 0.8 |
| Pass@5 | 1.0 |
| Reward distribution | `1.0: 4`, `0.0: 1` |

Failed trial:

- `cancel-async-tasks__qteAkPq`: verifier passed 5/6 tests and failed
  `test_tasks_cancel_below_max_concurrent` because captured stdout contained
  zero `Task started.` lines before SIGINT.

Interpretation:

- The task is still valid as a benchmark target: local Codex solved it in at
  least one attempt and achieved `pass@5 = 1.0`.
- The fresh local Codex run did **not** reproduce the frozen leaderboard's
  strict 5/5 result for Codex `0.121.0` / `gpt-5.5@openai`.
- Until the user changes the gate, keep M6.20's stated parity target tied to
  the frozen registry, not this fresh local Codex `0.125.0` sample. Treat this
  sample as variance evidence and as a warning that strict 5/5 may be harsher
  than the local reference run.

## Next Comparison

Run the mew `mew work --oneshot` Harbor proof on
`fix-code-vulnerability` and `cancel-async-tasks` with `--max-wall-seconds` set
below Harbor's 900 second agent timeout. The intended outcome is a complete mew
report instead of a Harbor timeout exception, followed by M6.18 failure
classification when any attempt fails. Score claims should be based on
5-attempt runs, not one-attempt timing samples.
