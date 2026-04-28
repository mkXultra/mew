# M6.24 Batch 2 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-28 JST

Status: selected; runs pending.

## Purpose

Batch 2 continues the broad Terminal-Bench parity campaign after Batch 1 showed
that repeated single-task repair loops can consume time without closing the
milestone. This batch expands measurement coverage across unseen registry tasks
and reserves repair work for generic failure classes that recur or are small
and high-leverage.

Frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_2.json`

## Selection Rule

- choose tasks not already measured in M6.20, M6.22, or M6.24 Batch 1;
- include low, medium, and high Codex success bands;
- include varied task shapes: build, ML/runtime, sequence/data, video/artifact,
  document extraction, git recovery, and large text editing;
- do not add Terminal-Bench-specific solvers to core.

| Band | Task | Codex target | Why selected |
|---:|---|---:|---|
| 0/5 | `caffe-cifar-10` | 0/5 | low-target ML/runtime task; useful runner and observation control |
| 2/5 | `extract-moves-from-video` | 2/5 | video/artifact task; probes whether visual tooling needs a generic video/frame observation surface |
| 3/5 | `dna-assembly` | 3/5 | medium-band sequence/data reasoning task |
| 3/5 | `dna-insert` | 3/5 | second sequence/edit task to separate one-off biology failures from reusable substrate issues |
| 4/5 | `financial-document-processor` | 4/5 | document/data extraction task close to Codex parity |
| 5/5 | `build-pmars` | 5/5 | build/control task distinct from `build-cython-ext` |
| 5/5 | `git-leak-recovery` | 5/5 | git-state control distinct from `fix-git` |
| 5/5 | `large-scale-text-editing` | 5/5 | large edit/control task for implementation-lane edit reliability |

Aggregate frozen Codex target: **27/40 successes, 67.5%**.

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
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command='apt-get update && apt-get install -y python3 python3-pip python3-venv && python3 -m pip install --break-system-packages -e /mew' \
  --ak command_cwd=/app \
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

## Next

Run Batch 2 task by task. After each result:

- record score, Harbor errors, runtime, artifact path, and any runner failure;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23;
- repair only when the failure is generic, repeated, or very small and
  high-leverage.
