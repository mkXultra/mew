# mew

`mew` is a local passive AI task agent prototype.

It keeps task state in `.mew/state.json`, wakes on a timer, remembers context, asks questions, and can run a guarded programmer loop through `ai-cli`.

## Quick Start

```sh
uv run mew doctor --auth auth.json
uv run mew task add "Improve mew" --kind coding --ready --description "Pick one small useful improvement"
uv run mew run --autonomous --autonomy-level propose --echo-effects --echo-outbox
uv run mew run --ai --model-backend codex --auth auth.json --echo-outbox
# or run it in the background:
uv run mew start -- --autonomous --autonomy-level propose
```

In another shell:

```sh
uv run mew chat
uv run mew attach -m "今日のタスクは何？"
uv run mew -m "今日のタスクは何？" --wait
uv run mew message "今日のタスクは何？" --wait
uv run mew event github_webhook --source local --payload '{"ref":"main"}' --wait
printf '{"id":"1","type":"status"}\n{"id":"2","type":"stop"}\n' | uv run mew session
uv run mew focus
uv run mew focus --kind coding
uv run mew daily
uv run mew journal --write
uv run mew morning-paper feed.json --interest ai --write
uv run mew self-memory --write
uv run mew dream --write
uv run mew bundle --show
uv run mew bundle --generate-core --morning-feed feed.json --interest ai --show
uv run mew desk --json
uv run mew mood --write
uv run mew digest
uv run mew brief
uv run mew next
uv run mew next --kind coding
```

`focus` and `daily` are the quiet daily views: they show the current next move,
open questions, and the top tasks without the full operational brief. Tasks can
be tagged with `--kind coding|research|personal|admin|unknown`; only coding
tasks are routed into the programmer plan queue by `mew next` and autonomous
propose mode. Use `mew next --kind coding` or `mew focus --kind coding` when
older research/personal questions should not hide the next coding-shell move;
when there are no coding tasks, that view suggests a native self-improvement
session instead of going silent.
`digest` summarizes activity since the last user interaction without entering
the chat REPL.
`journal` writes a morning/evening `.mew/journal/YYYY-MM-DD.md` from tasks,
questions, active work sessions, and runtime effects.
`morning-paper` ranks a static feed JSON against interest tags and writes
`.mew/morning-paper/YYYY-MM-DD.md`; collection from the web is still outside the
core command.
`self-memory` writes `.mew/self/learned-YYYY-MM-DD.md` with durable traits,
recent learnings, and continuity cues.
`dream` writes `.mew/dreams/YYYY-MM-DD.md` from active tasks, active work
sessions, and recent learnings.
`bundle` composes already-generated daily report markdown files into one
`.mew/passive-bundle/YYYY-MM-DD.md` reentry artifact. It does not generate the
source reports; use it after `mew journal --write`, `mew mood --write`,
`mew self-memory --write`, `mew dream --write`, or `mew morning-paper ... --write`.
Use `mew bundle --generate-core` to generate journal, mood, dream, and
self-memory before composing; add `--morning-feed feed.json --interest TAG` to
include the static morning paper in the same command. Generated source reports
are written under `--reports-root`; pass the same path to `--reports-root` and
`--output-dir` when you want sources and bundle under a separate root. If
generated reports would overwrite different existing content, mew writes a
sibling `.bak` first.
`desk` prints a small desktop-pet view model with `sleeping`, `thinking`,
`typing`, or `alerting` state plus a compact focus summary, primary action,
counts, and shallow detail lists for questions, active work sessions, tasks,
and attention. Use `mew desk --json` for a future tray/window process, or
`mew desk --write` to write `.mew/desk` artifacts.
`mood` scores current state across `energy`, `worry`, and `joy`, then can write
`.mew/mood/YYYY-MM-DD.md` for `mew bundle`.
When an active work session has working memory, `focus` includes the current
hypothesis and memory next step so reentry context is visible before opening the
full resume. If a later tool or model turn made that memory stale, `focus` marks
it stale and suppresses the old memory next step.
The same view uses the active session's saved model, permission, approval, and
verification defaults for its `continue` and `follow` commands, so quiet reentry
does not lose the cockpit setup.
Use `run --echo-effects` when observing passive runtime behavior: it prints the
runtime effect id, status, event reason, action types, summary, and outcome for
each processed cycle even when no user-facing outbox message was created.

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
uv run mew task list --kind coding --json
uv run mew task add "Implement the next small fix" --kind coding --json
uv run mew task show <task-id> --json
uv run mew task update <task-id> --status ready --json
uv run mew task done <task-id> --summary "verified" --json
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

Native work is a separate resident-model path. `--allow-native-work` lets a
passive tick create a task-linked `mew work` session; `--allow-native-advance`
lets later passive ticks advance a runtime-owned session by one bounded live
step. The runtime will not advance human-started sessions, sessions waiting on a
write approval, or sessions with an already-running model/tool turn.

```sh
uv run mew run --ai --auth auth.json \
  --autonomous --autonomy-level act \
  --allow-read . \
  --allow-native-work \
  --allow-native-advance \
  --echo-outbox
```

Local shell command execution is a separate gate:

```sh
uv run mew task update <task-id> --command "python -m pytest" --status ready --auto-execute
uv run mew run --execute-tasks
```

Native work-session `run_command` calls are parsed with `shlex` and executed
without an interactive shell. Avoid shell operators such as pipes, redirection,
`&&`, `||`, and `;`; wrap complex probes in an interpreter command such as
`python -c` when needed. A nonzero `run_command` exit does not stop the resident
loop as a tool crash, but it is surfaced in the work-session failure summary and
phase so the cockpit does not miss it.

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
uv run mew effects 10
uv run mew effects --json
uv run mew runtime-effects 10
uv run mew start -- --autonomous --autonomy-level propose
uv run mew run --once --autonomous --autonomy-level act --focus "Take one small verified step"
uv run mew run --once --passive-now --autonomous --autonomy-level propose --allow-read . --echo-effects --focus "Check one passive tick"
uv run mew stop
uv run mew -m "今日のタスクは何？" --wait
uv run mew message "今日のタスクは何？" --wait
uv run mew chat
uv run mew session
uv run mew focus
uv run mew focus --json
uv run mew focus --kind coding
uv run mew daily
uv run mew journal --date 2026-04-17 --write
uv run mew journal --show
uv run mew morning-paper feed.json --interest ai --write
uv run mew morning-paper feed.json --show
uv run mew self-memory --date 2026-04-17 --write
uv run mew dream --date 2026-04-17 --write
uv run mew bundle --date 2026-04-17 --show
uv run mew bundle --date 2026-04-17 --generate-core --morning-feed feed.json --interest ai --show
uv run mew desk --json
uv run mew desk --write
uv run mew mood --date 2026-04-17 --write
uv run mew mood --json
uv run mew brief
uv run mew brief --json
uv run mew activity
uv run mew activity --kind coding
uv run mew metrics --kind coding --limit 20
uv run mew metrics --kind coding --limit 20 --json
uv run mew context
uv run mew context --save "current intent; next action; validation; blockers"
uv run mew context --load
uv run mew step --dry-run
uv run mew step --ai --auth auth.json --allow-read . --max-steps 3
uv run mew step --ai --auth auth.json --allow-read . --max-reflex-rounds 1 --focus "Read README.md, then decide"
uv run mew step --ai --auth auth.json --allow-read . --focus "Review the current mew implementation work"
uv run mew step --ai --auth auth.json --allow-read . --allow-write . --allow-verify --verify-command "uv run pytest -q" --focus "Make one small verified change"
uv run mew snapshot --allow-read .
uv run mew dogfood --ai --duration 60
uv run mew dogfood --all
uv run mew dogfood --source-workspace . --ai --duration 60
uv run mew dogfood --source-workspace . --pre-snapshot --ai --duration 60
uv run mew dogfood --source-workspace . --cycles 3 --duration 30
uv run mew dogfood --source-workspace . --cycles 3 --report .mew/dogfood-latest.json
uv run mew perceive --allow-read .
uv run mew next
uv run mew next --kind coding
uv run mew next --json
uv run mew work
uv run mew task list --kind coding
uv run mew verification
uv run mew writes
uv run mew event file_change --payload '{"path":"src/mew/runtime.py"}'
uv run mew event github_webhook --source github --payload '{"ref":"main"}' --wait
MEW_WEBHOOK_TOKEN=secret uv run mew webhook --host 127.0.0.1 --port 8765
uv run mew run --notify-command "scripts/notify-mew" --notify-bell
uv run mew thoughts --details
uv run mew self-improve --focus "Make one small mew improvement"
uv run mew self-improve --native --focus "Make one small native work improvement"
uv run mew self-improve --start-session --focus "Start a native self-improvement session"
uv run mew outbox
uv run mew outbox --json
uv run mew ack --routine
uv run mew ack --all
uv run mew questions
uv run mew questions --json
uv run mew questions --defer <question-id> --reason "not now"
uv run mew questions --reopen <question-id>
uv run mew reply <question-id> "answer"
uv run mew attention
uv run mew attention --json
uv run mew attention --resolve-all
uv run mew archive
uv run mew archive --apply
uv run mew run --auto-archive
uv run mew run --ai --model-backend codex --auth auth.json
uv run mew memory --compact
uv run mew memory --search "project summary"
uv run mew trace --json
```

Read-only inspections also maintain a compact `project_snapshot` under deep
memory, so dogfood runs and resident prompts can reuse repository shape without
re-reading every file.
Run `mew snapshot --allow-read .` to refresh that map deterministically.
`mew metrics` summarizes work-session reliability, approval/verification
friction, and latency percentiles, then surfaces compact bottleneck signals for
the selected task kind. `mew context --save` writes a reentry checkpoint to
typed project memory, and `mew context --load` reads the latest checkpoints after
context compression or interruption.
`mew dogfood --report <path>` stores the structured report for later inspection,
including model phase counts, cycle summaries, active dropped-thread warnings,
and the final project snapshot.
Every state save is validated, reconciles `next_ids`, and appends a compact
checkpoint to `.mew/effects.jsonl`; `mew doctor` reports validation issues and
the latest checkpoint hash. `mew archive --apply` also compacts old effect log
entries into `.mew/archive/`.
Runtime cycles also append a bounded `runtime_effects` journal in state. Each
entry records the selected event, lifecycle status, action types, user-visible
outcome, and linked verification/write runs. Use `mew runtime-effects` or
`mew runtime-effects 10` for the recent journal; `mew doctor` flags unfinished
effects and `mew repair` can mark them interrupted after a crashed runtime with
a recovery hint for the next cycle.
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
file over and over. Routine startup/passive `info` messages are kept in outbox
history, but they start as read and are skipped by live echo, notification,
listen, attach, and chat streams so the user's unread queue stays focused on
actual replies, questions, and warnings. Use `mew ack --routine` to clear older
routine unread `info` messages without acknowledging questions or warnings.
Add `--max-reflex-rounds 1` when the resident model should do a narrow
read-only observation, immediately rethink with that observation, and only then
emit ACT actions. Step reports and model traces show the reflex read so the
reasoning path is inspectable without opening prompts by default.
After repeated inspection produces a concrete direction, the resident model can
use `refine_task` to turn a self-proposed generic task into a specific coding
task and refresh its programmer plan.
Use `--focus` to steer a short step loop toward the current development session
without rewriting persistent guidance.
Use `mew work [task-id]` as a read-only resume surface for one coding task: it
shows the current plan, recent agent runs, verification, writes, open questions,
and exactly one recommended next action. For coding tasks that do not already
have a running implementation path, the next action starts or continues a native
work session so the resident model can work from inside mew instead of forcing
the older external-agent planner path first.
`mew next` and passive next-move messages use the same native work-session
entry point for unplanned coding tasks.
Native work sessions are the first Milestone 1 path toward giving the resident
model its own hands. Start one with `mew work <task-id> --start-session`, inspect
it with `mew work --session` or `/work-session` in chat, and run tools with
explicit gates. Write tools default to dry-run. Applied writes require
`--allow-verify` and `--verify-command`; failed verification rolls the change
back and records the failed tool result. Nonzero `run_tests` exits are treated
as failed tool calls and summarized in `mew work --session --details`.
When `mew run --allow-native-advance` is enabled, runtime-started sessions are
also resumable by passive ticks. Each tick runs at most one live step, preserves
the session's auth/model/read/write/verify defaults, disables inline approval
prompts, and records the outcome in the session notes and dogfood metrics.
When no work session is active, `mew work --session` and
`mew work --session --resume` list recent sessions with resume commands instead
of leaving reentry discovery to memory.
`/work-session` in chat uses the same recent-session fallback, so a user can
reenter from the REPL without remembering the last task id.
The same recent-session summaries are available in `mew work --session --json`
for scripts and model-facing tools.
When a session is active, both `mew work --session` and `/work-session` include
the next controls for continuing, stopping, resuming, or opening chat.
The default session view keeps read-tool entries compact, so a large
`read_file` result does not flood reentry with file contents.
`mew work --session --resume` and `/work-session resume` include the same
controls after the compact resume bundle.
Active `mew work --session --json` and `--resume --json` also include
`next_cli_controls`, so machine readers get the same reentry commands.
Recent commands in the resume include short stdout/stderr previews, so common
test or shell output can be scanned without opening the focused commands pane.
Truncated previews start at a line boundary to avoid partial-line fragments.
The resume bundle also carries a compact `working_memory` section when resident
THINK output or recent session evidence can provide it: current hypothesis,
next intended step, open questions, and latest verification state. That same
digest is injected into future work-model context, so reentry starts from a
short contract instead of reconstructing intent from raw logs. Observed
verification results override model-written verification claims, and older
working memory is marked stale when later model turns did not refresh it.
The same memory also records the latest tool observation and is marked stale
when the selected tool ran after that memory was written, so a resume does not
quietly treat a pre-tool `next_step` as current; stale resume text is labeled
`stale_next_step`.
World-state git summaries hide mew's own `.mew/` state noise, keeping the
reentry signal focused on project files.
`mew chat` prints active-session controls on startup even when `--no-brief` is
used, so quiet chat still preserves the reentry affordance.
When a live work command uses read/write/verify/model/approval options, the active
session remembers those defaults and reuses them in later CLI and chat controls.
Starting a session with those options also seeds the same defaults before the
first live step. Later partial commands add explicit new options without
forgetting earlier read/write/verify/model gates. Starting a new session for a
task that only has closed sessions clones the latest closed session defaults, so
closed-session reentry does not forget its cockpit setup.
For CLI live runs that pass explicit tool gates, the printed next controls follow
that current permission posture, so a read-only continue does not suggest stale
write, shell, or verify flags from earlier broader runs.
Controls include both a one-step continue and a bounded `--max-steps 3`
continue, so short autonomous runs are discoverable without hiding the safer
single-step path. Multi-step work stops at pending dry-run write approvals
instead of continuing past a human review boundary. Add `--prompt-approval` to a
live run when you want mew to ask inline before applying or rejecting a dry-run
write.
`mew work --live` prints the selected action before execution, a compact result
pane after each step, and a resume after each completed tool step. The thinking
pane includes `step/max`, session, task id, phase, and elapsed time, so a longer
live run has a stable progress anchor. The result pane separates outcome, tools,
and session state, includes tool duration when start/finish timestamps are
available, and places command cwd/stdout/stderr directly under the tool result.
Read results stay summarized in the result pane and final step report so large
files do not flood the cockpit. Add `--compact-live`
when you want only thinking/action/result panes during a longer run and will
open `mew work --session --resume` separately if you need the full reentry
bundle; compact mode also keeps the final step report to command/cwd/exit
summaries instead of replaying stdout/stderr after the result pane.
`search_text` live results include short context snippets around matches, so a
compact run can show what was found without opening the full session details or
making the model infer too much from a single matched line.
`mew work --follow` uses compact live mode and renders plan-shaped model streams
as readable `summary_delta`, `reason_delta`, and `action_delta` lines when the
backend supports deltas, so a bounded autonomous run is observable while it is
thinking instead of only after each step completes. Follow mode now also prints
the active running model/tool cell before completion, then prints compact
completed cells with durable ids and a `mew work <task-id> --cells` hint for
details. Its planning summary is a short `plan: <action>` line plus model-stream
metrics. Use `--quiet` when you want the stdout cell stream without default
`mew work ai:` progress lines on stderr; pass `--progress` to force those lines
back on.
If a follow run or multi-step live run reaches `--max-steps`, mew records a
system work-session note with the last action/result and the reentry command
hint, so the next session can tell the loop hit its bound rather than silently
stopping.
When the model finishes, the work session is closed
and the final note is appended to the task so `mew work <task-id> --session --resume`
can still show the closed session. A `finish` action can explicitly set
`task_done: true` to mark the task done; otherwise it only closes the work
session. Work-mode `send_message` writes to outbox;
`ask_user` creates a normal question. The model can also choose a read-only
`batch` action to run up to five inspection tools in one work turn; writes and
shell commands remain outside batch mode. In `mew chat`, live work steps print
compact `Next controls` after execution: primary continue/follow commands plus
resume/help, while full controls stay available from startup and `/work-session`.
`/continue` remembers the previous live-step options for the chat session, and a
fresh chat can recover the active work session's stored defaults, so
`/continue <guidance>` can steer the next step without retyping gates such as
`--allow-read .`. A long work loop can be asked
to pause at the next model/tool boundary with `mew work --stop-session` or
`/work-session stop`. Work steps are journaled before THINK/ACT starts, and stop
requests are checked again after planning before any selected tool is started.
CLI live runs end with `Next CLI controls` so the next continue, follow, steer,
queue-followup, stop, resume, or chat command is visible. Work-mode `remember` records
durable session notes that appear in the resume bundle and future model context;
humans can add the same kind of note with `mew work --session-note` or
`/work-session note`. With an explicit task id, `mew work <task-id>
--session-note ...` can also annotate the latest closed task session after
review. For mid-loop steering that should not become permanent memory, use
`mew work --steer "..."` or `/work-session steer ...`; mew queues that text for
the next live/follow step, records the consumed steer as a note, and then clears
it. Session, resume, and live result panes show the queued steer while it is
still pending; model/API failures preserve it for the next real step instead of
silently dropping it. If more than one work session is active, `--steer` asks
for an explicit task id before queuing. For follow-up input that should wait in
FIFO order instead of replacing the next steer, use
`mew work --queue-followup "..."` or `/work-session queue ...`; the next
live/follow step consumes one queued follow-up only when no pending steer is
waiting. To stop the current step at the next model/tool boundary and submit
new guidance immediately afterward, use `mew work --interrupt-submit "..."`
or `/work-session interrupt ...`; if the current loop still has remaining
steps, it continues with that submitted guidance. Approving a dry-run write can reuse the
latest session
verification command, so `--verify-command` does not need to be repeated when a
recent `run_tests` or task command already defines it. A successful `run_tests`
or write verification refreshes the session's default verification command, so
future controls do not keep recommending a stale failing command.
Interrupted read-only tools can be retried with `mew work --recover-session
--allow-read .`. A resume can also opt into safe automatic retry with
`mew work --session --resume --allow-read . --auto-recover-safe`; this only
retries interrupted read/git inspection after explicit read gates, and its
recovery report includes the live world state checked before the retry. Write,
shell, and verification interruptions still require human review, and
interrupted resumes include a `Recovery plan` that classifies retryable reads,
replannable model turns, and side-effecting work that needs review. Older tool calls that
fall out of the full recent context window
are carried forward as compact `session_knowledge` digests instead of raw file
contents, and recent `read_file` results are clipped in model context with a
resume offset so the model can request the next page when needed. If the
work-session context still exceeds the budget, mew shrinks the recent
tool/turn windows and leaves a `context_compaction` note for the model. Passing
`--allow-read` to `mew work --session --resume` adds a live world-state check
with current git status and touched-file stats. Before any file has been
touched, non-git workspaces still show a shallow snapshot of the allowed read
root instead of `(no files)`. The same bounded summary is included in future
work-model context when read access is allowed.
Model-selected `read_file` calls default to a smaller page than manual reads,
and model-selected `git_diff` defaults to diffstat, so broad read-only batches
do not immediately bloat a resident session. One-shot `--work-guidance` and
`/continue <guidance>` text is treated as the current instruction for that turn
and retained as a historical guidance snapshot on model turns so resume,
timeline, and details views can show why the resident model chose the next
action without making that old guidance current again. THINK prompts ask the
resident model to write a compact `working_memory` object for future reentry;
older sessions fall back to the latest turn summary and verification state, and
stale memory is marked when newer turns omit the digest or when a tool result
landed after the memory was written; human-facing resumes label that old plan as
`stale_next_step`.

```sh
uv run mew work 1 --start-session
uv run mew work --session
uv run mew work --session --details
uv run mew work --session --timeline
uv run mew work --cells
uv run mew work --session --resume
uv run mew work --session --resume --allow-read .
uv run mew work --session-note "prefer small verified steps"
uv run mew work --steer "inspect README before editing"
uv run mew work 1 --recover-session --allow-read .
uv run mew work 1 --session --resume --allow-read . --auto-recover-safe
uv run mew work --stop-session --stop-reason "pause after this step"
uv run mew work 1 --tool read_file --path README.md --allow-read .
uv run mew work 1 --tool read_file --path src/mew/commands.py --allow-read . --offset 50000 --max-chars 12000
uv run mew work 1 --tool search_text --query "work session" --path . --allow-read . --context-lines 3
uv run mew work 1 --tool glob --pattern "*.py" --path src --allow-read .
uv run mew work 1 --tool git_status --allow-read .
uv run mew work 1 --tool git_diff --allow-read .
uv run mew work 1 --tool run_tests --command "uv run pytest -q tests/test_work_session.py" --allow-verify
uv run mew work 1 --tool run_tests --command "uv run pytest -q tests/test_work_session.py" --allow-verify --progress --json
uv run mew work 1 --tool write_file --path notes.md --content "hello" --create --allow-write .
uv run mew work 1 --tool edit_file --path README.md --old "old" --new "new" --allow-write .
uv run mew work 1 --approve-tool 7 --allow-write . --allow-verify --verify-command "uv run pytest -q"
uv run mew work 1 --approve-all --allow-write . --allow-verify --verify-command "uv run pytest -q"
uv run mew work 1 --reject-tool 7 --reject-reason "not the right change"
uv run mew work 1 --tool edit_file --path README.md --old "old" --new "new" --allow-write . --apply --allow-verify --verify-command "uv run pytest -q"
uv run mew work 1 --ai --auth auth.json --allow-read . --allow-write . --allow-verify --verify-command "uv run pytest -q" --max-steps 3
uv run mew code 1
uv run mew code 1 --read-only --no-verify
uv run mew code 1 --quiet --timeout 0
uv run mew do 1 --work-guidance "make the smallest verified fix"
uv run mew do 1 --no-prompt-approval --work-guidance "leave write approvals in the resume bundle"
uv run mew work 1 --live --auth auth.json --allow-read . --act-mode deterministic --max-steps 1
uv run mew work 1 --live --auth auth.json --allow-read . --allow-write . --allow-verify --verify-command "uv run pytest -q" --max-steps 3
uv run mew work 1 --follow --auth auth.json --allow-read .
uv run mew work 1 --follow --quiet --auth auth.json --allow-read . --max-steps 3
uv run mew work 1 --live --stream-model --auth auth.json --allow-read . --max-steps 1
uv run mew work 1 --ai --auth auth.json --allow-read . --act-mode deterministic --max-steps 1
```

`mew code [task-id]` is the quiet coding cockpit. With a task id, it starts or
reuses that task's native work session, scopes chat to `coding`, enables
work-mode, and keeps startup controls short: `/c`, `/follow`, and
`/continue <guidance>`. It hides unread outbox by default so old passive chatter
does not flood a coding session; use `--show-unread` when you want to review it.
Runtime activity is also hidden by default; use `--activity` when you want the
background runtime log in the cockpit.
Its startup brief is a compact status and next-action line rather than the full
general chat brief.
Use `--quiet` for scripted checks or attach-style probes where the chat banner,
scope line, work-mode line, brief, unread messages, and startup controls should
all stay silent.
Use `--read-only --no-verify` to enter without inheriting older write, shell, or
verification gates from a previous session. `mew next` and `mew focus` point
coding work back to this cockpit, whether the task is fresh or already active,
instead of printing a flag-heavy live command as the primary next action.

`mew do <task-id>` is the compact supervised coding path. It runs the resident
work loop live with deterministic ACT, `--allow-read .`, `--allow-write .`, and
an auto-detected verification command such as `uv run pytest -q` when available.
It uses the normal auth fallback (`./auth.json`, then `~/.codex/auth.json`)
unless `--auth` is explicitly supplied. In an interactive terminal, `mew do`
and `mew work --live` prompt inline before applying dry-run writes; use
`--prompt-approval` to force that behavior in non-TTY runs, or
`--no-prompt-approval` to leave approvals in the resume bundle. Use
`--read-only` / `--no-verify` to remove the default write and verification gates.
Live runs print a compact `thinking` pane before each action, so the selected
step is visible before any tool runs.
They also print a compact `result` pane after each step, combining action
status, key tool output, phase, context pressure, pending approvals, and the
next action before the full resume block.
`mew work --follow` also emits active and completed stable cockpit cells. Cells
give model turns, tools, commands, tests, diffs, and pending approvals durable
ids such as `s1:model_turn:2` or `s1:test:7`, so a human or future UI can point
at the same work item instead of reconstructing it from raw logs. The follow
stream keeps completed cells compact; use `mew work --cells` or
`/work-session cells` to inspect the full cell view later.
Live and follow runs also write `.mew/follow/latest.json` plus
`.mew/follow/session-<id>.json`, containing the latest step, resume, cells, and
next controls for another model or UI to observe without scraping terminal text.
That observer can write a JSON reply file and apply it with
`mew work --reply-file reply.json`; supported safe actions are `steer`,
`followup`, `interrupt_submit`, `note`, `stop`, `reject`, `approve`, and
`approve_all`. Follow snapshots include `supported_actions`, top-level
`pending_approvals`, and a context-aware `reply_template` so observers can
resolve pending dry-run writes without scraping terminal text. See
`docs/FOLLOW_REPLY_SCHEMA.md` for the snapshot and reply contract, including
the stale-snapshot guard and `mew work <task-id> --follow-status --json`, or run
`mew work <task-id> --reply-schema --json` to print a session-specific template.
When a pending write touches `src/mew/**`, the approval entry may also include
an advisory `pairing_status`; `missing_test_edit` means the same work session
has not yet produced a paired changed write/edit under `tests/**`.
Approving that source edit is blocked by default until a paired test write/edit
exists; use `--allow-unpaired-source-edit` only for an explicit audited override.
Blocked source approvals leave plain approve hints empty and steer observers
toward adding tests or using the explicit override path.
Inline approval prompts show the clipped diff preview and the verification
command that will run on approval.

Inside `mew chat`, use `/work-session details`, `/work-session diffs`,
`/work-session tests`, `/work-session commands`, `/work-session cells`,
`/work-session timeline`,
`/work-session resume --allow-read .`,
`/work-session resume --allow-read . --auto-recover-safe`,
`/work-session live 1 --allow-read . --max-steps 1`,
`/work-session live --allow-read . --allow-write . --allow-verify --verify-command "uv run pytest -q"`,
`/continue --allow-read .` to advance the active work session by one live step,
`/c --allow-read .` as the short alias,
`/follow --allow-read .` for a compact bounded live loop with model progress,
`/continue focus on README.md` to reuse the previous or persisted live options with new guidance,
`/work-mode on` or `mew chat --work-mode` to make text act as `/continue <guidance>` and let blank lines repeat after one work step,
`/work-session note prefer small verified steps`,
`/work-session steer inspect README before editing`,
`/work-session stop pause after this step`,
`/work-session ai 1 --allow-read . --max-steps 1`,
`/work-session approve 7 --allow-write . --verify-command "uv run pytest -q"`,
`/work-session approve all --allow-write . --verify-command "uv run pytest -q"`, or
`/work-session reject 7 not the right change`.

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

`mew chat` is the human-facing REPL for a running runtime. `mew chat --help`
prints the startup options plus the slash-command reference. Non-slash input is
sent to mew as a user message, and slash commands let you inspect or update
state without leaving the session. Chat inputs are also appended to
`.mew/chat.jsonl`; inspect the recent transcript with `mew chat-log` or
`/transcript` without mixing it into the runtime activity log:

```text
/help work
/focus
/focus coding
/brief
/next
/next coding
/doctor
/repair
/perception
/tasks
/questions
/add "調査する" | "対象を小さく確認する"
/show 4
/work
/work-session details
/work-session resume
/continue --allow-read .
/continue focus on the current failure
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
/runtime-effects
/why
/thoughts details
/digest
/transcript
/approve 4
/ready 4
/plan 4 prompt
/dispatch 4 dry-run
/buddy 4 dispatch dry-run
/self dry-run prompt improve chat loop
/self native improve the native work loop
/self start improve the native work loop
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
it does not stop the background runtime. `status`, `brief`, `focus`, `daily`,
and `activity` accept `"kind": "coding"` style scopes. `focus` responses contain
a `focus` payload; `daily` responses contain the same shape under `daily`:

```sh
printf '{"id":"m1","type":"message","text":"今日のタスクは何？"}\n{"id":"s1","type":"status"}\n{"type":"stop"}\n' | uv run mew session
```

## Safe Tools

`mew perceive` (or the `mew observe` alias) shows the small passive workspace
observations that are injected into the model context when a read root is
allowed. Current observers include git status and recent file changes:

```sh
uv run mew perceive --allow-read .
uv run mew perceive --allow-read . --json
uv run mew observe --allow-read . --json
```

`mew tool` gives AI-facing workspace tools with bounded read, write-preview,
verification, and read-only git helpers:

```sh
uv run mew tool status
uv run mew tool list src/mew
uv run mew tool read src/mew/cli.py --max-chars 4000
uv run mew tool search "self-improve" src
uv run mew tool glob "*.py" src/mew
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

Turn an idea into a native self-improvement work session:

```sh
uv run mew self-improve --start-session --focus "Make the coding cockpit calmer"
uv run mew work <task-id> --follow --quiet --allow-read . --compact-live --max-steps 10
uv run mew work <task-id> --follow-status --json
```

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
- `.mew/archive/`: archived processed inbox, read outbox, completed agent runs, old verification/write records, and old effect log entries.
- `mew run --auto-archive` writes old inactive records and effect log entries to `.mew/archive/`.
- `.mew/guidance.md`: human-written think-phase priority.
- `.mew/policy.md`: local safety policy.
- `.mew/self.md`: mew identity and behavior.
- `.mew/desires.md`: autonomous work preferences.
- `.codex/skills/mew-product-evaluator/SKILL.md`: project skill for evaluating
  whether mew is becoming a shell an AI would want to inhabit.

`auth.json` and `.mew/` are ignored by git.
