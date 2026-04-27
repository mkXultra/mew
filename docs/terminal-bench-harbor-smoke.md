# Terminal-Bench Harbor smoke harness

M6.19 adds the smallest Harbor custom-agent surface needed to run a Terminal-Bench smoke subset with mew and collect comparable per-task artifacts. It does not try to optimize scores; M6.20 owns score-driven debugging.

## Custom agent import

Place `.harbor` on the Python import path used by Harbor. For a tiny compatibility smoke that mounts this checkout, installs it inside the task environment, runs one Terminal-Bench task, and invokes an existing mew command, run from the repository root:

```sh
MEW_REPO="$(pwd)"
PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -l 1 \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command="python -m pip install -e /mew" \
  --ak command_template="mew doctor --json" \
  --mounts-json "[{\"type\":\"bind\",\"source\":\"${MEW_REPO}\",\"target\":\"/mew\"}]"
```

`-l 1` keeps the smoke bounded. Add `--include-task-name <name>` or `--task <name>` only when you want to pin the selected task. `--mounts-json` is a JSON array of Docker Compose service volumes; the example bind-mounts the local checkout at `/mew` so `install_command` can install the same code under test.

The smoke command above intentionally uses `mew doctor --json`, which exists today and is enough to prove Harbor can instantiate the wrapper, mount/install mew, execute a command in the task environment, and record wrapper artifacts. A true instruction-consuming mew benchmark entrypoint remains the next M6.19 gap if `command_template` needs to solve Terminal-Bench tasks rather than run a compatibility smoke.

The agent class lives at `.harbor/mew_terminal_bench_agent.py` and follows Harbor's installed-agent shape:

- accepts Harbor factory construction as `MewTerminalBenchAgent(logs_dir=..., model_name=..., **kwargs)`;
- imports `BaseInstalledAgent` and `with_prompt_template` from `harbor.agents.installed.base` when Harbor is available;
- remains importable in local tests when Harbor is not installed;
- defines static `name()` plus async `install(environment)` and async `run(instruction, environment, context)`;
- can run an optional `install_command` with optional `install_env` before the task command;
- keeps `populate_context_post_run(context)` synchronous;
- executes the configured mew smoke command through a BaseInstalledAgent-compatible `exec_as_agent` helper seam.

## Artifact contract

For each Terminal-Bench task, the wrapper creates a task directory under `artifacts/terminal-bench-harbor-smoke/` by default and records:

- `instruction.json`: task id and instruction text;
- `command-transcript.json`: command, stdout, stderr, exit code, timeout flag, and timeout seconds;
- `mew-report.json`: optional report produced by the invoked mew smoke command;
- `summary.json`: comparable summary with work-session/report summary, verifier result, timeout status, and cost/token metadata when available.

If the mew report omits optional fields, `summary.json` records them as `"unavailable"` rather than inventing values.

## Scope

This harness is a compatibility and artifact-recording slice only. It is intentionally suitable for a small smoke subset before using M6.20 to improve scores, prompts, tools, or task-specific behavior.
