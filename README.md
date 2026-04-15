# mew

`mew` is a local passive AI task agent prototype.

It keeps task state in `.mew/state.json`, wakes on a timer, remembers context, asks questions, and can run a guarded programmer loop through `ai-cli`.

## Quick Start

```sh
uv run mew doctor --auth auth.json
uv run mew task add "Improve mew" --description "Pick one small useful improvement"
uv run mew run --autonomous --autonomy-level propose --echo-outbox
uv run mew run --ai --model-backend codex --auth auth.json --echo-outbox
# or run it in the background:
uv run mew start -- --autonomous --autonomy-level propose
```

In another shell:

```sh
uv run mew chat
uv run mew attach -m "今日のタスクは何？"
uv run mew message "今日のタスクは何？" --wait
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
uv run mew agent followup <review-run-id> --ack --note "handled elsewhere"
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

Passive verification is a narrower gate for letting the runtime check the repo
without executing arbitrary task commands:

```sh
uv run mew run --autonomous --autonomy-level act \
  --allow-verify \
  --allow-write . \
  --verify-command "UV_CACHE_DIR=.uv-cache uv run python -m unittest" \
  --verify-interval-minutes 60
```

When autonomous mode sees an open verification failure attention item, it can
propose a high-priority repair task instead of letting the failure sit as a
passive alert.

## Useful Commands

```sh
uv run mew status
uv run mew status --json
uv run mew doctor
uv run mew doctor --json
uv run mew repair
uv run mew repair --json
uv run mew effects
uv run mew effects --json
uv run mew start -- --autonomous --autonomy-level propose
uv run mew stop
uv run mew message "今日のタスクは何？" --wait
uv run mew chat
uv run mew brief
uv run mew brief --json
uv run mew activity
uv run mew context
uv run mew snapshot --allow-read .
uv run mew dogfood --ai --duration 60
uv run mew dogfood --source-workspace . --ai --duration 60
uv run mew dogfood --source-workspace . --pre-snapshot --ai --duration 60
uv run mew dogfood --source-workspace . --cycles 3 --duration 30
uv run mew dogfood --source-workspace . --cycles 3 --report .mew/dogfood-latest.json
uv run mew perceive --allow-read .
uv run mew next
uv run mew next --json
uv run mew verification
uv run mew writes
uv run mew thoughts --details
uv run mew self-improve --focus "Make one small mew improvement"
uv run mew outbox
uv run mew ack --all
uv run mew questions
uv run mew reply <question-id> "answer"
uv run mew attention
uv run mew attention --resolve-all
uv run mew archive
uv run mew archive --apply
uv run mew run --auto-archive
uv run mew run --ai --model-backend codex --auth auth.json
uv run mew memory --compact
```

Read-only inspections also maintain a compact `project_snapshot` under deep
memory, so dogfood runs and resident prompts can reuse repository shape without
re-reading every file.
Run `mew snapshot --allow-read .` to refresh that map deterministically.
`mew dogfood --report <path>` stores the structured report for later inspection,
including model phase counts, cycle summaries, active dropped-thread warnings,
and the final project snapshot.
Every state save is validated, reconciles `next_ids`, and appends a compact
checkpoint to `.mew/effects.jsonl`; `mew doctor` reports validation issues and
the latest checkpoint hash.

## Resident Model

`mew run --ai` routes `think` and `act` through a resident model backend. The
available backends are `codex` and `claude`. `codex` calls the Codex Web API
directly with OAuth credentials from `auth.json` or `~/.codex/auth.json`.
`claude` calls the Claude Messages API with `ANTHROPIC_API_KEY` or a key file
passed with `--auth`.

```sh
uv run mew run --ai --model-backend codex --auth auth.json
ANTHROPIC_API_KEY=... uv run mew run --ai --model-backend claude
```

The runtime still validates every action locally. The model chooses plans; mew's
local code decides which effects are allowed.

`mew thoughts --details` shows the resident mind's carried threads. If a thread
was open in one cycle and disappears without being carried or resolved, mew
records it as a dropped thread and injects a warning into the next model context.
Dogfood loop reports distinguish historical dropped threads from active dropped
thread warnings, so resolved continuity hiccups do not look like current
blockers.

## Chat

`mew chat` is the human-facing REPL for a running runtime. Non-slash input is
sent to mew as a user message, and slash commands let you inspect or update
state without leaving the session:

```text
/brief
/next
/perception
/tasks
/questions
/add "調査する" | "対象を小さく確認する"
/show 4
/note 4 次はここを見る
/reply 3 それで進めて
/attention
/resolve all
/agents
/result 12
/wait 12 60
/review 12 dry-run
/followup 13
/retry 12 dry-run
/sweep dry-run
/verification
/verify UV_CACHE_DIR=.uv-cache uv run python -m unittest
/writes
/why
/thoughts details
/digest
/approve 4
/ready 4
/plan 4 prompt
/dispatch 4 dry-run
/self dry-run prompt improve chat loop
/done 4
/block 4
/pause
/resume
/mode act
/ack all
/activity off
/exit
```

## Safe Tools

`mew perceive` shows the small passive workspace observations that are injected
into the model context when a read root is allowed. Current observers include
git status and recent file changes:

```sh
uv run mew perceive --allow-read .
uv run mew perceive --allow-read . --json
```

`mew tool` gives AI-facing workspace tools with bounded read, write-preview,
verification, and read-only git helpers:

```sh
uv run mew tool status
uv run mew tool list src/mew
uv run mew tool read src/mew/cli.py --max-chars 4000
uv run mew tool search "self-improve" src
uv run mew tool write notes.md --content "hello" --create --dry-run
uv run mew tool edit notes.md --old "hello" --new "hello mew" --dry-run
uv run mew tool test --command "UV_CACHE_DIR=.uv-cache uv run python -m unittest"
uv run mew tool git diff
uv run mew tool git diff --staged --stat
uv run mew tool git diff --base main --stat
```

Sensitive files such as `auth.json`, `.env`, and private keys are refused by the
read and write commands. Runtime write actions require `--allow-write` and
non-dry-run runtime writes also require `--allow-verify --verify-command`.
Runtime write actions default to dry-run unless the action explicitly sets
`dry_run=false`. If verification fails after a runtime write, mew restores the
previous file content or removes the newly created file and records the rollback
in `mew writes`.
Direct `mew tool write` and `mew tool edit` commands can apply changes, so use
`--dry-run` first when an AI is operating through the tool layer.
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
- `.mew/runtime.out`: background runtime output when started with `mew start`.
- `.mew/archive/`: archived processed inbox, read outbox, completed agent runs, and old verification/write records.
- `mew run --auto-archive` writes old inactive records to `.mew/archive/`.
- `.mew/guidance.md`: human-written think-phase priority.
- `.mew/policy.md`: local safety policy.
- `.mew/self.md`: mew identity and behavior.
- `.mew/desires.md`: autonomous work preferences.

`auth.json` and `.mew/` are ignored by git.
