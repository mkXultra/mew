# M6.24 Reference Trace Smoke: prove-plus-comm

Date: 2026-05-05 JST

Purpose: verify that reference-agent Harbor logs can be captured after task
completion and normalized without changing the Harbor execution path.

## Parser-Only Decision

Do not put `acm`, `ai-cli`, or a custom reference wrapper into the Harbor task
container for this proof. Harbor runs the built-in reference agents; mew only
parses completed artifacts after the task exits.

## Reusable Runner

Use the wrapper below for future reference-agent trace capture. Change only
`TASK_NAME` and `AGENT` (`codex` or `claude-code`) for the common case:

```sh
uv run python scripts/run_harbor_reference_trace.py TASK_NAME AGENT
```

Examples:

```sh
uv run python scripts/run_harbor_reference_trace.py prove-plus-comm codex
uv run python scripts/run_harbor_reference_trace.py prove-plus-comm claude-code
```

The wrapper:

- runs Harbor built-in reference agents;
- passes `.env.local` via Harbor `--env-file` when it exists;
- passes `CODEX_AUTH_JSON_PATH=~/.codex/auth.json` for Codex when it exists;
- normalizes every completed trial into `normalized-trace/agent_trace.jsonl`
  and `normalized-trace/summary.json`.
- prefers Harbor `agent/trajectory.json` when present, so normalized events keep
  `timestamp`, `elapsed_ms`, and phase-latency summary fields.

The normalized summary includes timeline fields:

- `start_timestamp` / `end_timestamp` / `total_seconds`
- `first_tool_seconds`
- `first_command_seconds`
- `first_edit_seconds`
- `first_verifier_seconds`
- `command_duration_seconds` and `command_duration_observed_count` when raw
  command duration can be extracted.

## Codex

Command:

```sh
env PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/prove-plus-comm \
  -k 1 \
  -n 1 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/reference-trace/codex-prove-plus-comm-20260505 \
  --agent codex \
  -m gpt-5.5 \
  --ak reasoning_effort=high \
  --ae CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json
```

Result:

- Job:
  `proof-artifacts/terminal-bench/reference-trace/codex-prove-plus-comm-20260505/2026-05-05__11-36-38/result.json`
- Trial: `prove-plus-comm__9UyWmbV`
- Reward: `1.0`
- Harbor exceptions: `0`
- Runtime: `2m 37s`
- Raw stream:
  `proof-artifacts/terminal-bench/reference-trace/codex-prove-plus-comm-20260505/2026-05-05__11-36-38/prove-plus-comm__9UyWmbV/agent/codex.txt`
- Harbor ATIF trajectory:
  `proof-artifacts/terminal-bench/reference-trace/codex-prove-plus-comm-20260505/2026-05-05__11-36-38/prove-plus-comm__9UyWmbV/agent/trajectory.json`

Normalization:

```sh
uv run python scripts/normalize_harbor_agent_trace.py \
  --agent codex \
  --task-dir proof-artifacts/terminal-bench/reference-trace/codex-prove-plus-comm-20260505/2026-05-05__11-36-38/prove-plus-comm__9UyWmbV \
  --json
```

Normalized summary:

```json
{
  "agent": "codex",
  "command_count": 6,
  "command_duration_observed_count": 6,
  "command_duration_seconds": 0.55,
  "command_event_count": 12,
  "edit_count": 1,
  "edit_event_count": 2,
  "event_count": 21,
  "first_command_seconds": 3.957,
  "first_edit_seconds": 13.967,
  "first_tool_seconds": 3.957,
  "first_verifier_seconds": 16.196,
  "message_count": 4,
  "parse_error_count": 0,
  "total_seconds": 22.389,
  "tool_call_completed_count": 7,
  "tool_call_count": 14,
  "tool_call_started_count": 7,
  "verifier_count": 1
}
```

## Claude Code

Command:

```sh
env PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/prove-plus-comm \
  -k 1 \
  -n 1 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/reference-trace/claude-prove-plus-comm-20260505 \
  --agent claude-code \
  -m sonnet \
  --ak reasoning_effort=high
```

Result:

- Job:
  `proof-artifacts/terminal-bench/reference-trace/claude-prove-plus-comm-20260505/2026-05-05__11-39-46/result.json`
- Trial: `prove-plus-comm__9ob7vWR`
- Reward: `0.0`
- Harbor exceptions: `1`
- Exception: `NonZeroAgentExitCodeError`
- Raw stream:
  `proof-artifacts/terminal-bench/reference-trace/claude-prove-plus-comm-20260505/2026-05-05__11-39-46/prove-plus-comm__9ob7vWR/agent/claude-code.txt`

Failure reason: Claude Code launched in the Harbor task container but was not
authenticated there:

```text
Not logged in - Please run /login
```

Normalization still worked on the failed raw stream:

```json
{
  "agent": "claude",
  "command_count": 0,
  "command_event_count": 0,
  "event_count": 5,
  "message_count": 1,
  "parse_error_count": 0,
  "tool_call_count": 0
}
```

## Outcome

- Post-task parser-only trace extraction works for Harbor built-in Codex.
- Post-task parser-only trace extraction also works for Claude Code auth-failure
  logs, so the parser path is usable once container auth is solved.
- Harbor built-in Codex writes `agent/codex.txt`, not `raw/stdout.jsonl`; the
  parser now auto-detects this path.
- Harbor built-in Claude Code writes `agent/claude-code.txt`; the parser now
  auto-detects this path.

After adding `CLAUDE_CODE_OAUTH_TOKEN` to ignored `.env.local`, Claude Code
also passed the same task:

- Job:
  `proof-artifacts/terminal-bench/reference-trace/claude-prove-plus-comm-20260505-retry-env/2026-05-05__11-53-48/result.json`
- Trial: `prove-plus-comm__W7SJ76h`
- Reward: `1.0`
- Harbor exceptions: `0`
- Runtime: `2m 21s`
- Normalized summary:

```json
{
  "agent": "claude",
  "command_count": 2,
  "command_event_count": 4,
  "edit_count": 1,
  "edit_event_count": 2,
  "event_count": 34,
  "message_count": 4,
  "parse_error_count": 0,
  "tool_call_completed_count": 5,
  "tool_call_count": 10,
  "tool_call_started_count": 5,
  "verifier_count": 1,
  "verifier_event_count": 2
}
```

The reusable runner produced a second authenticated Claude Code smoke:

```sh
uv run python scripts/run_harbor_reference_trace.py prove-plus-comm claude-code
```

Result:

- Job:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-prove-plus-comm-20260505-120526/2026-05-05__12-05-27/result.json`
- Trial: `prove-plus-comm__kgFJz2y`
- Reward: `1.0`
- Harbor exceptions: `0`
- Runtime: `3m 48s`
- Normalized summary:

```json
{
  "agent": "claude",
  "command_count": 3,
  "command_duration_observed_count": 0,
  "command_duration_seconds": null,
  "command_event_count": 6,
  "edit_count": 1,
  "edit_event_count": 2,
  "event_count": 20,
  "first_command_seconds": 32.982,
  "first_edit_seconds": 47.742,
  "first_tool_seconds": 4.336,
  "first_verifier_seconds": 50.473,
  "message_count": 7,
  "parse_error_count": 0,
  "total_seconds": 58.522,
  "tool_call_completed_count": 6,
  "tool_call_count": 12,
  "tool_call_started_count": 6,
  "verifier_count": 1
}
```
