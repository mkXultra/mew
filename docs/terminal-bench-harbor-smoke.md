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
  --ak command_template="mew-smoke --instruction {instruction_shell} --report {report_path} --artifacts {artifact_dir}" \
  --mounts-json "[{\"type\":\"bind\",\"source\":\"${MEW_REPO}\",\"target\":\"/mew\"}]"
```

`-l 1` bounds the selected Terminal-Bench task subset, and `-n 1` bounds trials, so the smoke cannot accidentally run the whole dataset. `-y` keeps the smoke non-interactive. Add `--include-task-name <name>` or `--task <name>` only when you want to pin the selected task. `--mounts-json` is a JSON array of Docker Compose service volumes; the example bind-mounts the local checkout at `/mew` so `install_command` can install the same code under test.

The initial M6.19 live smoke used `command_template="mew --help"` and produced `Exceptions=0`, transcript `exit_code=0`, and Harbor job output under `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-help-fixed-return-code/result.json`. M6.20 adds `mew-smoke`, a deliberately minimal installed entrypoint that accepts the Terminal-Bench instruction through `--instruction`, writes a report JSON at `--report`, records artifacts under `--artifacts`, and prints the same report JSON to stdout. This proves ingestion and artifact/report generation for the next bounded rerun; it is not a score-optimization run. The Harbor wrapper uses stdout JSON as a fallback report when the command wrote `mew-report.json` inside the benchmark container but the host artifact directory cannot see that file.

The agent class lives at `.harbor/mew_terminal_bench_agent.py` and follows Harbor's installed-agent shape:

- accepts Harbor factory construction as `MewTerminalBenchAgent(logs_dir=..., model_name=..., **kwargs)`;
- imports `BaseInstalledAgent` and `with_prompt_template` from `harbor.agents.installed.base` when Harbor is available;
- remains importable in local tests when Harbor is not installed;
- defines static `name()` plus async `install(environment)` and async `run(instruction, environment, context)`;
- can run an optional `install_command` with optional `install_env` before the task command;
- keeps `populate_context_post_run(context)` synchronous and writes through metadata-compatible context handling;
- executes the configured mew smoke command through a BaseInstalledAgent-compatible `exec_as_agent` helper seam.

## Artifact contract

For each Terminal-Bench task, the wrapper creates a task directory under Harbor `logs_dir/terminal-bench-harbor-smoke/` when Harbor supplies `logs_dir`. Outside Harbor, it falls back to local `artifacts/terminal-bench-harbor-smoke/`. Each task directory records:

- `instruction.json`: task id and instruction text;
- `command-transcript.json`: command, stdout, stderr, exit code, timeout flag, and timeout seconds;
- `mew-report.json`: optional report produced by the invoked mew smoke command;
- `summary.json`: comparable summary with work-session/report summary, verifier result, timeout status, and cost/token metadata when available.

If the mew report omits optional fields, `summary.json` records them as `"unavailable"` rather than inventing values.

## Scope

This harness is a compatibility and artifact-recording slice only. It is intentionally suitable for a small smoke subset before using M6.20 to improve scores, prompts, tools, or task-specific behavior.
