# M6.24 Batch 5 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-29 JST

Status: selected; runs pending.

## Purpose

Batch 5 continues broad Terminal-Bench parity measurement after Batch 4 full
measured tasks reached 11/35 against the frozen Codex target 25/35, excluding
the partial `train-fasttext` control run. It keeps the same rule as the earlier
batches: benchmark the generic mew work-session loop, not a
Terminal-Bench-specific solver path.

Frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_5.json`

## Selection Rule

- choose tasks not already measured in M6.20, M6.22, M6.24 Batch 1, Batch 2,
  Batch 3, or Batch 4;
- remaining unmeasured tasks are all frozen Codex 5/5 targets, so this batch
  takes the next alphabetical unmeasured high-target slice;
- include varied task shapes: Bayesian-network modification, circuit/math
  verification, compiler build, dataset counting, password/hash recovery,
  low-level memory debugging, search/distribution logic, and cryptanalysis;
- repair only generic recurring or high-leverage substrate failures through
  M6.14.

| Task | Codex target | Why selected |
|---|---:|---|
| `bn-fit-modify` | 5/5 | Bayesian-network/statistical code modification |
| `circuit-fibsqrt` | 5/5 | circuit/math correctness task |
| `compile-compcert` | 5/5 | compiler/toolchain build task |
| `count-dataset-tokens` | 5/5 | data-processing and token-counting task |
| `crack-7z-hash` | 5/5 | password/hash recovery task |
| `custom-memory-heap-crash` | 5/5 | low-level memory/debugging task |
| `distribution-search` | 5/5 | search/distribution implementation task |
| `feal-differential-cryptanalysis` | 5/5 | cryptanalysis implementation task |

Aggregate frozen Codex target: **40/40 successes, 100.0%**.

## Run Shape

Use the existing generic Harbor wrapper and normal `mew work --oneshot` command
shape:

```sh
env PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/<task-name> \
  -k 5 \
  -n 5 \
  -y \
  --agent-timeout-multiplier 2 \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command='apt-get update && apt-get install -y python3 python3-pip python3-venv && python3 -m pip install --break-system-packages -e /mew' \
  --ak command_cwd=/app \
  --ak container_repo_root=/mew \
  --ak timeout_seconds=1800 \
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-read /etc/apt --allow-write . --allow-write /usr/local/bin --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 {max_wall_seconds_option} --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

The `/etc/apt` read root and `/usr/local/bin` write root are generic
container-system task permissions for package-source inspection and requested
binary installation. They are not task solvers.

`--agent-timeout-multiplier 2` plus `timeout_seconds=1800` plus
`{max_wall_seconds_option}` is the current generic self-budgeting guard from
SR-014/SR-015.

## Next

Run Batch 5 task by task, starting with `bn-fit-modify`. After each result:

- record score, Harbor errors, runtime, artifact path, and any runner failure;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23;
- pause broad measurement only for accepted structural blockers, append them to
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, and repair through M6.14 before
  resuming the same task shape.
