# M6.19 Terminal-Bench Compatibility Close Audit

Status: closed.

M6.19 is closed because Harbor can run mew as a custom agent without patching
Harbor source, a bounded Terminal-Bench smoke subset now produces mew artifacts,
and the same bounded task was run with the built-in Codex reference agent for
side-by-side comparison.

## Evidence

Mew custom-agent smoke:

```sh
PYTHONPATH=.harbor harbor run -d terminal-bench/terminal-bench-2 -l 1 -n 1 -y \
  --job-name mew-smoke-help-fixed-return-code \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command="python -m pip install -e /mew" \
  --ak command_template="mew --help" \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"}]'
```

Result:

- result: `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-help-fixed-return-code/result.json`
- task: `terminal-bench/make-mips-interpreter`
- exceptions: `0`
- score: `0.0`
- transcript: `command-transcript.json` recorded `exit_code: 0`
- artifact root: Harbor `logs_dir/terminal-bench-harbor-smoke`

Codex reference-agent smoke:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -l 1 \
  -n 1 \
  -y \
  --job-name codex-smoke-make-mips \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

Result:

- result: `proof-artifacts/terminal-bench/harbor-smoke/codex-smoke-make-mips/result.json`
- task: `terminal-bench/make-mips-interpreter`
- exceptions: `0`
- score: `0.0`
- agent version: Codex `0.125.0`
- token metadata present in Harbor result: input `2707381`, cached `2577024`,
  output `18253`, cost `null`

Focused wrapper validation:

```sh
uv run pytest -q tests/test_harbor_terminal_bench_agent.py --no-testmon
uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py
git diff --check
```

All passed during the close session.

## Done-When Review

- Harbor can invoke mew as a custom agent without patching Harbor source: yes.
- A Terminal-Bench smoke subset runs through mew and produces per-task results:
  yes.
- The same subset can be run for at least one reference agent: yes, Codex.
- Mew stores per-task artifacts with instruction, command transcript, summary,
  verifier/timeout metadata, and token/cost metadata when available: yes for the
  compatibility smoke. The smoke command itself does not produce model token
  usage, so mew records those optional fields as unavailable.
- Artifacts are stable enough to route failures into M6.18/M6.14: yes. The
  artifact paths and Harbor result JSON are deterministic enough for M6.20
  failure-science work.

## Caveats

This close does not claim task-solving quality. Both mew and Codex scored `0.0`
on the selected smoke task. M6.19 only proves compatibility and comparable
artifact collection. M6.20 owns scored debugging, task selection, score targets,
and any instruction-consuming mew benchmark entrypoint work.
