# M6.24 Batch 4 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-29 JST

Status: selected; runs pending.

## Purpose

Batch 4 continues broad Terminal-Bench parity measurement after Batch 3
completed at 2/40 against the frozen Codex target 24/40. It keeps the same
rule as the earlier batches: benchmark the generic mew work-session loop, not
a Terminal-Bench-specific solver path.

Frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_4.json`

## Selection Rule

- choose tasks not already measured in M6.20, M6.22, M6.24 Batch 1, Batch 2,
  or Batch 3;
- cover the remaining available Codex success bands. Unmeasured 1/5 and 2/5
  bands are exhausted, so this batch covers 0/5, 3/5, 4/5, and 5/5;
- include varied task shapes: image/data segmentation, training workflow,
  systems implementation, distributed ML, bioinformatics, statistical coding,
  legacy modernization, and optimization/scheduling;
- repair only generic recurring or high-leverage substrate failures through
  M6.14.

| Band | Task | Codex target | Why selected |
|---:|---|---:|---|
| 0/5 | `sam-cell-seg` | 0/5 | low-target image/data segmentation control after visual artifact repairs |
| 0/5 | `train-fasttext` | 0/5 | low-target model-training/package workflow control |
| 3/5 | `make-mips-interpreter` | 3/5 | medium-target systems/interpreter task distinct from prior MIPS build tasks |
| 3/5 | `torch-pipeline-parallelism` | 3/5 | medium-target distributed ML task distinct from simple scripting |
| 4/5 | `protein-assembly` | 4/5 | high-medium bioinformatics/algorithmic task |
| 5/5 | `adaptive-rejection-sampler` | 5/5 | high-target statistical/numeric implementation control |
| 5/5 | `cobol-modernization` | 5/5 | high-target legacy code modernization control |
| 5/5 | `constraints-scheduling` | 5/5 | high-target optimization/scheduling implementation control |

Aggregate frozen Codex target: **25/40 successes, 62.5%**.

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
  --ak container_repo_root=/mew \
  --ak timeout_seconds=1800 \
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-read /etc/apt --allow-write . --allow-write /usr/local/bin --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 {max_wall_seconds_option} --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

The `/etc/apt` read root and `/usr/local/bin` write root are generic
container-system task permissions for package-source inspection and requested
binary installation. They are not task solvers.

`timeout_seconds=1800` plus `{max_wall_seconds_option}` is a generic
self-budgeting guard: the wrapper still records command timeout transcripts,
while `mew work --oneshot` gets an inner wall budget and can write a final
`wall_timeout` report before Harbor raises `AgentTimeoutError`.

## Next

Run Batch 4 task by task, starting with `sam-cell-seg`. After each result:

- record score, Harbor errors, runtime, artifact path, and any runner failure;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23;
- pause broad measurement only for accepted structural blockers, append them to
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, and repair through M6.14 before
  resuming the same task shape.
