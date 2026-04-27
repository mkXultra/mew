# Terminal-Bench Harbor smoke harness

M6.19 adds the smallest Harbor custom-agent surface needed to run a Terminal-Bench smoke subset with mew and collect comparable per-task artifacts. It does not try to optimize scores; M6.20 owns score-driven debugging.

## Custom agent import

Place `.harbor` on the Python import path used by Harbor, then run the custom agent with:

```sh
harbor run -d terminal-bench/terminal-bench-2 --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent
```

The agent class lives at `.harbor/mew_terminal_bench_agent.py` and follows Harbor's installed-agent shape:

- imports `BaseInstalledAgent` and `with_prompt_template` from `harbor.agents.installed.base` when Harbor is available;
- remains importable in local tests when Harbor is not installed;
- defines async `install(environment)` and async `run(instruction, environment, context)`;
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
