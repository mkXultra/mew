# Terminal-Bench Harbor smoke harness

M6.19 adds the smallest Harbor custom-agent surface needed to run a Terminal-Bench smoke subset with mew and collect comparable per-task artifacts. It does not try to optimize scores; M6.20 owns score-driven debugging.

## Custom agent import

Place `.harbor` on the Python import path used by Harbor. For a tiny compatibility smoke that mounts this checkout, installs it inside the task environment, runs one Terminal-Bench task, and invokes the installed instruction-consuming smoke entrypoint, run from the repository root:

```sh
MEW_REPO="$(pwd)"
PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -l 1 \
  -n 1 \
  -y \
  --job-name mew-smoke-instruction-entrypoint \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command="python -m pip install -e /mew" \
  --ak container_repo_root="/mew" \
  --ak command_template="mew-smoke --instruction {instruction_shell} --report {report_path} --artifacts {artifact_dir}" \
  --mounts-json "[{\"type\":\"bind\",\"source\":\"${MEW_REPO}\",\"target\":\"/mew\"}]"
```

`-l 1` bounds the selected Terminal-Bench task subset, and `-n 1` bounds trials, so the smoke cannot accidentally run the whole dataset. `-y` keeps the smoke non-interactive. Add `--include-task-name <name>` or `--task <name>` only when you want to pin the selected task. `--mounts-json` is a JSON array of Docker Compose service volumes; the example bind-mounts the local checkout at `/mew` so `install_command` can install the same code under test.

The initial M6.19 live smoke used `command_template="mew --help"` and produced `Exceptions=0`, transcript `exit_code=0`, and Harbor job output under `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-help-fixed-return-code/result.json`. M6.20 adds `mew-smoke`, a deliberately minimal installed entrypoint that accepts the Terminal-Bench instruction through `--instruction`, writes a report JSON at `--report`, records artifacts under `--artifacts`, and prints the same report JSON to stdout. This proves ingestion and artifact/report generation for the next bounded rerun; it is not a score-optimization run. The Harbor wrapper uses stdout JSON as a fallback report when the command wrote `mew-report.json` inside the benchmark container but the host artifact directory cannot see that file.

For M6.20 implementation-lane debugging, keep the same wrapper but swap the
command template to the generic `mew work --oneshot` path instead of adding a
benchmark-specific solver:

```sh
MEW_REPO="$(pwd)"
PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -n 1 \
  -y \
  --agent-timeout-multiplier 2 \
  --job-name mew-work-oneshot-make-mips \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command="python -m pip install -e /mew" \
  --ak command_cwd="/app" \
  --ak container_repo_root="/mew" \
  --ak timeout_seconds=1800 \
  --ak command_template="mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-read /etc/apt --allow-read /tmp --allow-write . --allow-write /usr/local/bin --allow-write /tmp --allow-shell --allow-verify --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 {max_wall_seconds_option} --max-steps 30 --work-guidance 'selected_lane=implement_v2 write_integration_observation_detail=true' --report {report_path} --artifacts {artifact_dir} --json" \
  --mounts-json "[{\"type\":\"bind\",\"source\":\"${MEW_REPO}\",\"target\":\"/mew\"},{\"type\":\"bind\",\"source\":\"/Users/mk/.codex/auth.json\",\"target\":\"/codex-auth/auth.json\"}]"
```

This is still a generic work-session run: Terminal-Bench only provides the
workspace cwd, instruction, artifact path, and verifier harness.
For M6.24 speed/proof runs, keep `timeout_seconds` plus
`{max_wall_seconds_option}` in the command template. Without that, mew cannot
compute an inner wall budget, and hard-runtime continuation gates are disabled.

For repeatable implementation-lane diagnostics, prefer the checked-in runner
instead of hand-building Harbor commands:

```sh
uv run python scripts/run_harbor_mew_diagnostic.py make-mips-interpreter
```

The runner fixes the default diagnostic shape:

- `selected_lane=implement_v2 write_integration_observation_detail=true` in a
  single `--work-guidance` string;
- local checkout mounted at `/mew` and `~/.codex/auth.json` mounted at
  `/codex-auth/auth.json`;
- no assumed `/tests` read surface; the 2026-05-12 diagnostic showed that path
  is absent inside this Harbor agent environment;
- `timeout_seconds=660` and `timeout_reserve_seconds=60`, which makes
  `{max_wall_seconds_option}` expand to a 600 second mew wall budget;
- post-run summary that reports whether integration-observation detail was
  enabled, written, and host-visible.

This avoids context-compression or copy/paste drift where a manual diagnostic
forgets observer detail, passes duplicate `--work-guidance`, or lets Harbor
template formatting consume JSON braces.

Use explicit modes to keep diagnostics and proof runs separate:

```sh
# 10 minute step-shape check. Diagnostic only; not score proof.
uv run python scripts/run_harbor_mew_diagnostic.py make-mips-interpreter \
  --mode step-check-10min

# One-trial speed proof after local/replay/dogfood/emulator are green.
uv run python scripts/run_harbor_mew_diagnostic.py make-mips-interpreter \
  --mode speed-proof

# Five-trial proof after the speed proof is accepted.
uv run python scripts/run_harbor_mew_diagnostic.py make-mips-interpreter \
  --mode proof-5
```

`step-check-10min` uses `-k 1 -n 1`, `timeout_seconds=660`, and a 600 second
mew wall budget. `speed-proof` uses one trial with the normal 1800 second
wrapper budget. `proof-5` uses `-k 5 -n 1` with the same 1800 second budget.
All modes keep observer detail on by default so a failed run is debuggable;
use `--allow-missing-observer-detail` only for harness debugging, not for
M6.24 evidence.

The agent class lives at `.harbor/mew_terminal_bench_agent.py` and follows Harbor's installed-agent shape:

- accepts Harbor factory construction as `MewTerminalBenchAgent(logs_dir=..., model_name=..., **kwargs)`;
- imports `BaseInstalledAgent` and `with_prompt_template` from `harbor.agents.installed.base` when Harbor is available;
- remains importable in local tests when Harbor is not installed;
- defines static `name()` plus async `install(environment)` and async `run(instruction, environment, context)`;
- can run an optional `install_command` with optional `install_env` before the task command;
- can run the task command from optional `command_cwd` and exposes
  `{command_cwd}` / `{command_cwd_shell}` template placeholders;
- can map host artifact placeholders to a container-visible repo mount with
  `container_repo_root=/mew`, so running partial reports survive command
  timeouts;
- does not impose an inner command timeout by default; Harbor's task
  `agent.timeout_sec` remains the authoritative wall clock unless
  `timeout_seconds=...` is passed explicitly;
- keeps `populate_context_post_run(context)` synchronous and writes through metadata-compatible context handling;
- executes the configured command through a BaseInstalledAgent-compatible `exec_as_agent` helper seam.

## Artifact contract

For each Terminal-Bench task, the wrapper creates a task directory under Harbor `logs_dir/terminal-bench-harbor-smoke/` when Harbor supplies `logs_dir`. Outside Harbor, it falls back to local `artifacts/terminal-bench-harbor-smoke/`. Each task directory records:

- `instruction.json`: task id and instruction text;
- `command-transcript.json`: command, cwd, stdout, stderr, exit code, timeout flag, and timeout seconds;
- `mew-report.json`: optional report produced by the invoked mew smoke command;
- `summary.json`: comparable summary with work-session/report summary, verifier result, timeout status, and cost/token metadata when available.

If the mew report omits optional fields, `summary.json` records them as `"unavailable"` rather than inventing values.

## Scope

This harness is a compatibility and artifact-recording slice only. It is intentionally suitable for a small smoke subset before using M6.20 to improve scores, prompts, tools, or task-specific behavior.
