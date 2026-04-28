# M6.24 Batch 3 Manifest - Broad Terminal-Bench Parity

Date: 2026-04-28 JST

Status: selected; runs pending.

## Purpose

Batch 3 resumes broad Terminal-Bench parity measurement after Batch 2 and the
selected M6.14 structural repairs. It expands coverage across unseen registry
tasks while preserving the core rule: this is a generic mew work-session
benchmark, not a Terminal-Bench-specific implementation track.

Frozen Codex registry:

`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`

Local batch JSON:

`docs/data/terminal_bench_m6_24_batch_3.json`

## Selection Rule

- choose tasks not already measured in M6.20, M6.22, M6.24 Batch 1, or M6.24
  Batch 2;
- cover Codex success bands 0/1/2/3/4/5;
- include varied task shapes: OS/emulation setup, cross-compile/build,
  statistical scripting, video/artifact processing, numeric/ML extraction,
  polyglot implementation, HTML editing, and source build;
- repair only generic recurring or high-leverage substrate failures through
  M6.14.

| Band | Task | Codex target | Why selected |
|---:|---|---:|---|
| 0/5 | `install-windows-3.11` | 0/5 | low-target OS/emulation setup control; useful for runner and permission behavior |
| 1/5 | `make-doom-for-mips` | 1/5 | low-target cross-compile/build task distinct from `make-mips-interpreter` |
| 2/5 | `mcmc-sampling-stan` | 2/5 | statistical scripting task; probes data/modeling workflow without prior repair bias |
| 3/5 | `video-processing` | 3/5 | video/artifact task after SR-003, but not the same `extract-moves-from-video` shape |
| 4/5 | `model-extraction-relu-logits` | 4/5 | numeric/ML extraction task close to Codex parity |
| 4/5 | `polyglot-rust-c` | 4/5 | multi-language implementation/build task |
| 5/5 | `break-filter-js-from-html` | 5/5 | high-target HTML/editing control related to, but distinct from, `filter-js-from-html` |
| 5/5 | `build-pov-ray` | 5/5 | high-target source build control distinct from previous build tasks |

Aggregate frozen Codex target: **24/40 successes, 60.0%**.

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
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-read /etc/apt --allow-write . --allow-write /usr/local/bin --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

The `/etc/apt` read root and `/usr/local/bin` write root are generic
container-system task permissions for package-source inspection and requested
binary installation. They are not task solvers.

## Next

Run Batch 3 task by task. After each result:

- record score, Harbor errors, runtime, artifact path, and any runner failure;
- compare against the frozen Codex target;
- classify below-target or runner-error shapes through M6.18/M6.23;
- pause broad measurement only for accepted structural blockers, append them to
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, and repair through M6.14 before
  resuming the same task shape.
