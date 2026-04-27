# M6.24 Batch 1 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-28 JST

Status: selected; runs pending.

## Purpose

M6.24 moves from curated subset debugging into the broad parity campaign. Batch
1 is the first measured slice from the frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

This is still a generic mew work-session benchmark. Do not add
Terminal-Bench-specific solvers to core.

## Batch

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_1.json`

Selection rule:

- choose tasks not already measured in M6.20/M6.22;
- cover Codex success bands 0/1/2/3/4/5;
- include multiple 5/5 controls with different task shapes;
- keep the batch small enough to classify and repair before expanding.

| Band | Task | Codex target | Why selected |
|---:|---|---:|---|
| 0/5 | `configure-git-webserver` | 0/5 | low-target setup/server task; should not drive repair unless mew unexpectedly outperforms or runner errors appear |
| 1/5 | `db-wal-recovery` | 1/5 | low-target data recovery task with file/state reasoning |
| 2/5 | `raman-fitting` | 2/5 | numerical/data-fitting task; probes scientific scripting without using prior `gcode-to-text` evidence |
| 3/5 | `chess-best-move` | 3/5 | bounded reasoning/tooling task at the same target band as `overfull-hbox` |
| 4/5 | `kv-store-grpc` | 4/5 | implementation/server task close to Codex parity |
| 5/5 | `build-cython-ext` | 5/5 | build/packaging control |
| 5/5 | `code-from-image` | 5/5 | artifact/vision-like input shape; likely to exercise readback/grounding weaknesses |
| 5/5 | `fix-git` | 5/5 | git-state repair control |

Aggregate frozen Codex target: **25/40 successes, 62.5%**.

## Run Shape

Use the existing generic Harbor wrapper and `mew work --oneshot` command shape:

```sh
env PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/<task-name> \
  -k 5 \
  -n 5 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command='apt-get update && apt-get install -y python3 python3-pip python3-venv && python3 -m pip install --break-system-packages -e /mew' \
  --ak command_cwd=/app \
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

## Next

Run Batch 1 task by task. After each result:

- record artifact path, score, errors, runtime, and cost/token data when
  available;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23 before
  selecting repairs.

