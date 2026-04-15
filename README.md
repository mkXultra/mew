# mew

`mew` is a local passive AI task agent prototype.

It keeps task state in `.mew/state.json`, wakes on a timer, remembers context, asks questions, and can run a guarded programmer loop through `ai-cli`.

## Quick Start

```sh
uv run mew doctor --auth auth.json
uv run mew task add "Improve mew" --kind coding --ready --description "Pick one small useful improvement"
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
uv run mew event github_webhook --source local --payload '{"ref":"main"}' --wait
printf '{"id":"1","type":"status"}\n{"id":"2","type":"stop"}\n' | uv run mew session
uv run mew focus
uv run mew daily
uv run mew brief
uv run mew next
```

`focus` and `daily` are the quiet daily views: they show the current next move,
open questions, and the top tasks without the full operational brief. Tasks can
be tagged with `--kind coding|research|personal|admin|unknown`; only coding
tasks are routed into the programmer plan queue by `mew next` and autonomous
propose mode.

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

Programmer plans and direct task agent runs are intentionally limited to tasks classified as `coding`.
For a misclassified implementation task, run `uv run mew task update <id> --kind coding`
or `/kind <id> coding` in chat first.

`mew buddy` is the safer single-task wrapper around that manual flow. By
default it only creates or reuses a plan; add `--dispatch --dry-run` to preview
the implementation run command before starting anything:

```sh
uv run mew task classify --mismatches
uv run mew task classify <task-id> --apply
uv run mew buddy --task <task-id>
uv run mew buddy --task <task-id> --dispatch --dry-run
uv run mew buddy --task <task-id> --dispatch
uv run mew agent wait <run-id>
uv run mew buddy --task <task-id> --review --dry-run
```

Autonomous dispatch is intentionally gated:

```sh
uv run mew task add "Implement the next small fix" --kind coding --ready --auto-execute
# or:
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
uv run mew repair --force
uv run mew effects
uv run mew effects --json
uv run mew start -- --autonomous --autonomy-level propose
uv run mew stop
uv run mew message "今日のタスクは何？" --wait
uv run mew chat
uv run mew session
uv run mew focus
uv run mew focus --json
uv run mew daily
uv run mew brief
uv run mew brief --json
uv run mew activity
uv run mew context
uv run mew step --dry-run
uv run mew step --ai --auth auth.json --allow-read . --max-steps 3
uv run mew step --ai --auth auth.json --allow-read . --focus "Review the current mew implementation work"
uv run mew snapshot --allow-read .
uv run mew dogfood --ai --duration 60
uv run mew dogfood --source-workspace . --ai --duration 60
uv run mew dogfood --source-workspace . --pre-snapshot --ai --duration 60
uv run mew dogfood --source-workspace . --cycles 3 --duration 30
uv run mew dogfood --source-workspace . --cycles 3 --report .mew/dogfood-latest.json
uv run mew perceive --allow-read .
uv run mew next
uv run mew next --json
uv run mew task list --kind coding
uv run mew verification
uv run mew writes
uv run mew event file_change --payload '{"path":"src/mew/runtime.py"}'
uv run mew event github_webhook --source github --payload '{"ref":"main"}' --wait
MEW_WEBHOOK_TOKEN=secret uv run mew webhook --host 127.0.0.1 --port 8765
uv run mew run --notify-command "scripts/notify-mew" --notify-bell
uv run mew thoughts --details
uv run mew self-improve --focus "Make one small mew improvement"
uv run mew outbox
uv run mew ack --all
uv run mew questions
uv run mew questions --defer <question-id> --reason "not now"
uv run mew questions --reopen <question-id>
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
Runtime cycles select and persist the next event under `.mew/state.lock`, then
release the lock while the resident model runs THINK/ACT. The runtime reacquires
the lock only to commit the resulting action plan, so `mew chat`, `mew message`,
and `mew status` can keep working during slow model calls.
This is an optimistic snapshot design: messages queued while a model call is in
flight are preserved and handled by a later cycle, but the in-flight plan does
not see them. Before commit, the runtime rechecks that the selected event is
still unprocessed; if another command has already handled it, the stale plan is
discarded without emitting messages or effects.
The same pending-event check runs before read-only verification is precomputed
outside the lock, so stale events do not start a verification command.
Resident prompts include a bounded raw conversation history from recent
`user_message` events and human-facing outbox replies/questions, so follow-up
turns can see the human's wording and mew's last replies instead of relying
only on summaries.

External systems can wake the same event loop without waiting for the passive
interval. `mew event <type> --payload '{"key":"value"}'` queues a non-reserved
external event, and `--wait` waits for outbox linked to that event. `mew
webhook` exposes the same ingress over HTTP: `POST /event/<type>` with a JSON
object body. Non-loopback webhook binds require `--token` or
`MEW_WEBHOOK_TOKEN`; tokenless non-loopback serving must be explicitly enabled
with `--allow-unauthenticated`. Runtime notifications are opt-in:
`--notify-command` runs once per new outbox message with `MEW_OUTBOX_*`
environment variables, and `--notify-bell` emits a terminal bell.

`mew step` is a bounded manual feedback loop. It plans one small passive step,
filters out writes, task execution, and agent dispatch, applies only safe
read/memory/question/task-proposal actions, then records the actions, skipped
actions, and visible effects so the next step can see the feedback. Autonomous
read-only actions are also guarded against short-term repeats, so mew should
synthesize or choose a different inspection target instead of reading the same
file over and over. Routine autonomous read progress is kept in outbox for
history and live attach streams, but marked read so the user's unread queue
stays focused on actual replies, questions, and warnings.
After repeated inspection produces a concrete direction, the resident model can
use `refine_task` to turn a self-proposed generic task into a specific coding
task and refresh its programmer plan.
Use `--focus` to steer a short step loop toward the current development session
without rewriting persistent guidance.

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
/focus
/brief
/next
/perception
/tasks
/questions
/add "調査する" | "対象を小さく確認する"
/show 4
/note 4 次はここを見る
/kind 4 research
/classify 4 apply
/defer 3 later
/reopen 3
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
/buddy 4 dispatch dry-run
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

`mew session` is the JSON Lines control surface for scripts and future richer
frontends. It reads one JSON object per line and writes one JSON object per
line. Supported request types include `status`, `brief`, `focus`, `daily`, `activity`,
`questions`, `attention`, `outbox`, `ack`, `message`, `reply`, `next`, and
`defer_question`, `reopen_question`, `wait_outbox`, and `stop`. `message`
requests may also pass `"wait": true`. `stop` exits the JSONL session;
it does not stop the background runtime. `focus` responses contain a `focus`
payload; `daily` responses contain the same shape under `daily`:

```sh
printf '{"id":"m1","type":"message","text":"今日のタスクは何？"}\n{"id":"s1","type":"status"}\n{"type":"stop"}\n' | uv run mew session
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
- `.codex/skills/mew-product-evaluator/SKILL.md`: project skill for evaluating
  whether mew is becoming a shell an AI would want to inhabit.

`auth.json` and `.mew/` are ignored by git.
