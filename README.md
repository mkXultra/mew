# mew

`mew` is a local passive AI task agent prototype.

It keeps task state in `.mew/state.json`, wakes on a timer, remembers context, asks questions, and can run a guarded programmer loop through `ai-cli`.

## Quick Start

```sh
uv run mew doctor --auth auth.json
uv run mew task add "Improve mew" --description "Pick one small useful improvement"
uv run mew run --autonomous --autonomy-level propose --echo-outbox
```

In another shell:

```sh
uv run mew attach -m "今日のタスクは何？"
uv run mew brief
uv run mew next
```

## Programmer Loop

Manual flow:

```sh
uv run mew task plan <task-id>
uv run mew task dispatch <task-id>
uv run mew agent result <run-id>
uv run mew agent review <run-id>
uv run mew agent followup <review-run-id>
uv run mew agent retry <failed-run-id>
uv run mew agent sweep
```

Autonomous dispatch is intentionally gated:

```sh
uv run mew task update <task-id> --status ready --auto-execute
uv run mew run --autonomous --autonomy-level act --allow-agent-run --echo-outbox
```

Local shell command execution is a separate gate:

```sh
uv run mew task update <task-id> --command "python -m pytest" --status ready --auto-execute
uv run mew run --execute-tasks
```

## Useful Commands

```sh
uv run mew status
uv run mew brief
uv run mew next
uv run mew self-improve --focus "Make one small mew improvement"
uv run mew outbox
uv run mew ack --all
uv run mew questions
uv run mew reply <question-id> "answer"
uv run mew attention
uv run mew attention --resolve-all
uv run mew memory --compact
```

## Safe Tools

`mew tool` gives AI-facing read-only workspace tools and bounded verification:

```sh
uv run mew tool status
uv run mew tool list src/mew
uv run mew tool read src/mew/cli.py --max-chars 4000
uv run mew tool search "self-improve" src
uv run mew tool test --command "UV_CACHE_DIR=.uv-cache uv run python -m unittest"
uv run mew tool git diff
```

Sensitive files such as `auth.json`, `.env`, and private keys are refused by the
read command. Tool commands do not provide file-writing operations.
Programmer-loop implementation prompts also point agents at these commands so
self-improvement runs can inspect and verify work through the safe layer.

## Self-Improvement

Create a planned self-improvement task without starting an agent:

```sh
uv run mew self-improve --focus "Improve stale agent-run handling"
```

Create a dry-run implementation record:

```sh
uv run mew self-improve --focus "Improve docs" --ready --auto-execute --dispatch --dry-run
```

When reusing an open self-improvement task, mew creates a fresh plan if the
latest plan was already dispatched or no longer matches the current focus.

Run one supervised implementation plus review cycle:

```sh
uv run mew self-improve --cycle --focus "Make one small safe improvement"
```

The cycle waits for implementation, starts a review, processes follow-up, and
stops unless the review returns `STATUS: pass`. Use `--cycles N` to repeat that
guarded loop.

Add a supervisor-owned verification gate before review:

```sh
uv run mew self-improve --cycle --verify-command "UV_CACHE_DIR=.uv-cache uv run python -m unittest"
```

Let passive mode dispatch ready self-improvement tasks:

```sh
uv run mew run --autonomous --autonomy-level act --allow-agent-run --echo-outbox
```

## State Files

- `.mew/state.json`: durable state.
- `.mew/runtime.md`: runtime log.
- `.mew/guidance.md`: human-written think-phase priority.
- `.mew/policy.md`: local safety policy.
- `.mew/self.md`: mew identity and behavior.
- `.mew/desires.md`: autonomous work preferences.

`auth.json` and `.mew/` are ignored by git.
