# M6.24 Batch 6 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-29 JST

Status: selected; runs pending.

## Purpose

Batch 6 continues broad Terminal-Bench parity measurement after Batch 5
completed at 31/40 against the frozen Codex target 40/40. It keeps the same
rule as the earlier batches: benchmark the generic mew work-session loop, not a
Terminal-Bench-specific solver path.

Frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_6.json`

## Selection Rule

- choose tasks not already measured in M6.20, M6.22, M6.24 Batch 1, Batch 2,
  Batch 3, Batch 4, or Batch 5;
- remaining unmeasured tasks are all frozen Codex 5/5 targets, so this batch
  takes the next alphabetical unmeasured high-target slice;
- include varied task shapes: cryptanalysis, OCaml runtime repair, git branch
  coordination, code-golf/model implementation, terminal/headless workflow,
  model inference, numeric linear algebra, and batching/scheduling;
- repair only generic recurring or high-leverage substrate failures through
  M6.14.

| Task | Codex target | Why selected |
|---|---:|---|
| `feal-linear-cryptanalysis` | 5/5 | cryptanalysis task adjacent to Batch 5 FEAL coverage |
| `fix-ocaml-gc` | 5/5 | runtime/language implementation repair |
| `git-multibranch` | 5/5 | git branch coordination and repository state task |
| `gpt2-codegolf` | 5/5 | compact model/code-generation implementation task |
| `headless-terminal` | 5/5 | terminal/headless workflow task |
| `hf-model-inference` | 5/5 | Hugging Face/model inference task |
| `largest-eigenval` | 5/5 | numeric linear algebra task |
| `llm-inference-batching-scheduler` | 5/5 | batching/scheduling implementation task |

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
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-read /etc/apt --allow-read /tmp --allow-write . --allow-write /usr/local/bin --allow-write /tmp --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 {max_wall_seconds_option} --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

The `/etc/apt` read root, `/usr/local/bin` write root, and `/tmp` scratch
read/write root are generic container-system task permissions for package-source
inspection, requested binary installation, and task-declared scratch/build
locations. They are not task solvers.

`--agent-timeout-multiplier 2` plus `timeout_seconds=1800` plus
`{max_wall_seconds_option}` is the current generic self-budgeting guard from
SR-014/SR-015.

## Next

Run Batch 6 task by task, starting with `feal-linear-cryptanalysis`. After each
result:

- record score, Harbor errors, runtime, artifact path, and any runner failure;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23;
- pause broad measurement only for accepted structural blockers, append them to
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, and repair through M6.14 before
  resuming the same task shape.
