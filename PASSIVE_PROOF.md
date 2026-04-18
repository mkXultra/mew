# Mew Passive Proof Log

This file records real passive-runtime checks. The goal is to preserve evidence
about whether mew can run without fresh user input, notice state, and propose
safe next steps.

## 2026-04-17 Short Passive Loop

Start time: 2026-04-17 21:33 JST session window.

### Setup

Before the true passive check, three stale unprocessed `user_message` inbox
events from earlier dogfood runs were still present. `mew run --once` prioritized
those as `reason=user_input`, so they were drained by normal runtime processing
rather than edited manually.

After draining:

```bash
jq '[.inbox[]?|select(.processed_at==null)] | length' .mew/state.json
```

Result:

```text
0
```

### Command

```bash
./mew run \
  --ai \
  --autonomous \
  --autonomy-level propose \
  --allow-read . \
  --auth auth.json \
  --echo-outbox \
  --max-reflex-rounds 1 \
  --interval 2 \
  --poll-interval 0.2 \
  --focus "Short passive loop proof: no user input. On passive ticks, observe current coding/project state and propose safe next steps without writing files."
```

Stopped with:

```bash
./mew stop
```

### Observed Output

```text
mew runtime started pid=25493 state=.mew/state.json
Codex Web API enabled auth=auth.json model=gpt-5.4 base_url=https://chatgpt.com/backend-api/codex
guidance loaded path=.mew/guidance.md
runtime focus: Short passive loop proof: no user input. On passive ticks, observe current coding/project state and propose safe next steps without writing files.
policy loaded path=.mew/policy.md
self loaded path=.mew/self.md
desires loaded path=.mew/desires.md
autonomous mode enabled level=propose
read-only inspection allowed under:
- .
processed 1 event(s) reason=startup
processed 1 event(s) reason=passive_tick
processed 1 event(s) reason=passive_tick
processed 1 event(s) reason=passive_tick
processed 1 event(s) reason=passive_tick
processed 1 event(s) reason=passive_tick
mew runtime stopped
```

### Runtime State Evidence

During the loop, `mew status --kind coding` showed:

```text
runtime_status: running
current_reason: passive_tick
current_phase: planning
agent_mode: reviewing_tasks
agent_focus: safe next-step proposal for mew-bond
autonomy_enabled: True
autonomy_level: propose
user_mode: idle
open_tasks: 0
latest_summary: kept the waiting thread stable and continued a small proposal to review mew-bond README
```

After stopping, `mew doctor` showed:

```text
runtime_lock: none
runtime: stopped pid=None phase= effect= incomplete_cycle=False
runtime_effects: total=13 incomplete=0 latest=#13 status=applied event=#391 reason=passive_tick actions=update_memory,self_review
```

### What Worked

- With no unprocessed inbox items, mew reached real `passive_tick` cycles.
- The runtime stayed within `autonomy-level propose`.
- Read-only gates were explicit.
- No repository files were changed by the passive runtime.
- Status showed task review/planning around the current side-project context.

### Friction

- `mew run --once` always processed `startup` and exited, so it did not reach
  passive ticks. A short loop was required.
- Stale unprocessed `user_message` events can hide passive behavior until they
  are drained.
- Passive proposals were visible in runtime status summaries, but no new outbox
  message was emitted during the true passive loop.

### Product Judgment

This is a small but real proof that passive ticks work after startup and inbox
drain. It is not yet proof of useful autonomous work. The next proof should run
longer with a controlled open coding task and should preserve a structured
cycle report for every passive tick.

## 2026-04-17 Follow-Up: `--passive-now`

The short loop exposed that `mew run --once` was not a convenient passive proof
entrypoint because it processed `startup` and exited. A small CLI option was
added:

```bash
./mew run --once --passive-now
```

Behavior:

- Pending user or external events still take priority.
- If no such event is pending, the first internal cycle is `passive_tick`
  instead of `startup`.
- This makes one-shot passive proof and regression checks possible without
  starting a multi-cycle runtime loop.

Live verification:

```bash
./mew run --once --passive-now --ai --autonomous --autonomy-level propose --allow-read . --auth auth.json --echo-outbox --max-reflex-rounds 1 --focus "Test --passive-now: process exactly one passive tick without waiting for startup. Do not write files."
```

Result:

```text
processed 1 event(s) reason=passive_tick
```

Validation:

```text
uv run pytest -q
718 passed, 6 subtests passed

./mew dogfood --scenario runtime-focus --cleanup --json
status: pass, including runtime_passive_now_processes_passive_tick

./mew dogfood --scenario all --cleanup --json
status: pass
```

## 2026-04-17 Follow-Up: `--echo-effects`

The passive loop was still hard to observe when a cycle updated memory or self
review without sending a user-facing outbox message. A second small CLI option
was added:

```bash
./mew run --echo-effects
```

For every processed cycle, it prints the applied runtime effect summary after
the normal `processed ... reason=...` line.

Live verification:

```bash
./mew run --once --passive-now --autonomous --autonomy-level propose --allow-read . --echo-effects --focus "Check one passive tick effect summary without model."
```

Result excerpt:

```text
processed 1 event(s) reason=passive_tick
effect #15 [applied] event=#393 reason=passive_tick actions=record_memory,wait_for_user,ask_user,wait_for_user summary=3 open task(s) ... outcome=Question #3 is still unanswered.
```

Product impact:

- `--echo-outbox` remains for user-facing messages.
- `--echo-effects` exposes quiet passive cycles that only update memory,
  review state, or wait.
- Together with `--passive-now`, this gives a one-command passive runtime proof
  that does not require waiting for a multi-cycle resident loop.

Regression coverage:

```text
uv run pytest -q tests/test_runtime.py tests/test_dogfood.py tests/test_commands.py
200 passed, 4 subtests passed

./mew dogfood --scenario runtime-focus --cleanup --json
status: pass, including runtime_passive_now_echoes_effect_summary

./mew dogfood --scenario all --cleanup --json
status: pass
```

## 2026-04-18 Review: Next Passive Proof

After the observer JSON/recovery work and the isolated terminal `mew-desk`
prototype, `claude-ultra` reviewed the direction and judged mew more plausible
as a passive AI shell because the observer contract now has machine-readable
perception and gated actuation:

- `mew observe --json`
- `mew task add/list/show/update/done --json`
- `.mew/follow/latest.json`
- `mew work --follow-status --json`
- `producer_health` and `suggested_recovery`
- reply-file actions such as approve, reject, steer, followup, interrupt, and
  note

The next proof should not be another side project. It should record a complete
observer-driven `mew code` or `mew work --follow` cycle that uses the JSON
contract rather than human text scraping:

1. Start a small coding task with a dry-run write.
2. Read `.mew/follow/latest.json` or `mew work <task-id> --follow-status --json`.
3. Generate a reply file from the published schema.
4. Approve or steer via `mew work --reply-file`.
5. Wait for the next snapshot and preserve the trace.

Open blocker before more passive-AI decoration:

- The true passive loop can update memory/self-review and print
  `--echo-effects`, but it still needs one concrete `autonomy-level=propose`
  path that reaches a user-visible outbox message without fresh user input.
  Until that proof exists, passive autonomy is observable but not yet clearly
  proactive.

## 2026-04-18 Deterministic Observer Reply-File Proof

Workspace:

```text
/tmp/mew-observer-proof.9p4cDM
```

This proof used no model call. It exercised the observer contract as a
machine-readable control path:

1. Created ready coding task `#1`.
2. Started work session `#1` with write root `.` and verifier
   `python3 -m py_compile proof.py`.
3. Ran a dry-run `write_file` for `proof.py`.
4. Refreshed `.mew/follow/session-1.json` with
   `mew work 1 --follow --max-steps 0 --quiet --json`.
5. Read `mew work 1 --reply-schema --json` and wrote a reply file containing
   an `approve` action for tool call `#1`.
6. Applied it with `mew work 1 --reply-file .mew/follow/reply.json --json`.
7. Refreshed the follow snapshot again and checked follow status.

Result excerpt:

```text
"type": "approve"
"tool_call_id": 1
"applied_tool_call_id": 2
"status": "completed"
"verification_exit_code": 0
"rolled_back": false
```

Final follow status:

```text
status: fresh
pending_approval_count: 0
producer_health.state: fresh
suggested_recovery: {}
```

Learning:

- A non-human observer can now drive the approval lane from JSON snapshot to
  reply file to verified write application without scraping human text.
- The first two attempts also proved rollback behavior for bad verification:
  `python` missing and invalid Python content both failed closed and did not
  leave the file applied.
- This closes the smallest observer-contract proof. The remaining passive-AI
  proof is still user-visible proactive output from a true passive tick.

## 2026-04-18 Final 6h Passive Check

Command:

```bash
./mew run --once --passive-now --autonomous --autonomy-level propose --allow-read . --echo-effects --echo-outbox --focus "Final 6h passive check: observe current state and surface a safe user-visible next step only if useful."
```

Observed result:

```text
processed 1 event(s) reason=passive_tick
effect #19 [applied] event=#398 reason=passive_tick actions=record_memory,wait_for_user,wait_for_user,wait_for_user,self_review
outcome=Question #3 is still unanswered.
```

No outbox message was printed by `--echo-outbox`.

Judgment:

- Passive processing is alive and records effects.
- The current state is dominated by existing unanswered questions, so the
  runtime chose `wait_for_user` rather than sending a new proactive message.
- This reinforces the remaining proof gap: mew needs one controlled no-input
  scenario where `autonomy-level=propose` creates a user-visible outbox proposal.

## 2026-04-18 Controlled Passive Outbox Proof

Workspace:

```text
/tmp/mew-passive-outbox-proof.tgg0Oo
```

Setup:

- One ready coding task.
- No stale inbox messages.
- No open questions before the passive tick.

Command:

```bash
mew run --once --passive-now --autonomous --autonomy-level propose --allow-read . --echo-effects --echo-outbox --focus "Controlled passive outbox proof: no user input and one ready coding task. If useful, create a concise user-visible proposal."
```

Observed result:

```text
processed 1 event(s) reason=passive_tick
effect #1 [applied] event=#1 reason=passive_tick actions=record_memory,ask_user,self_review,plan_task
outcome=Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?
outbox #1 [question]: Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?
```

Note: this proof captured the older coding-task question wording. The current
wording routes ready coding tasks to `./mew code <task-id>` instead of the
older agent/command/backend prompt.

Judgment:

- A clean no-input passive tick can create a user-visible outbox proposal under
  `autonomy-level=propose`.
- The production repo's final check did not emit a new outbox message because
  existing unanswered questions caused the runtime to wait for user input.
- The remaining product work is not "can passive output happen at all"; it is
  prioritization and cadence when older unanswered questions are already open.

Likely implementation hook:

- `src/mew/agent.py` `append_passive_decisions` checks
  `pending_question_for_task` before asking a task question. In the real repo
  state, every open task had an unanswered question, so the passive tick emitted
  only `wait_for_user` decisions. The next slice should decide when a stale
  unanswered question should be summarized, deferred, or superseded instead of
  permanently suppressing new passive output.

## 2026-04-18 Stale Question Refresh Proof

Change:

- `append_passive_decisions` now treats a task-bound open question older than
  24 hours as stale during autonomous `propose`/`act` passive ticks.
- It refreshes at most one stale task question per cycle.
- The old question is marked `deferred` with a readable reason before the new
  question is created, so the history is journaled rather than silently dropped.

Real repo command:

```bash
./mew run --once --passive-now --autonomous --autonomy-level propose --allow-read . --echo-effects --echo-outbox --focus "Passive refresh proof after stale-question cadence fix: if an old unanswered task question is blocking, refresh exactly one user-visible prompt."
```

Observed result:

```text
processed 1 event(s) reason=passive_tick
effect #20 [applied] event=#399 reason=passive_tick actions=record_memory,ask_user,wait_for_user,wait_for_user,self_review
outcome=Task #20 is ready research work. Should I assign it to an agent, add research criteria, or block it?
outbox #141 [question]: Task #20 is ready research work. Should I assign it to an agent, add research criteria, or block it?
```

Question state after the run:

```text
question #3: deferred, task #20
defer_reason: Question #3 was unanswered for 61.0h; refreshing one passive prompt instead of waiting forever.
question #5: open, task #20
```

Regression coverage:

```text
uv run pytest -q tests/test_autonomy.py
90 passed

./mew dogfood --scenario runtime-focus --cleanup --json
status: pass, including runtime_passive_refreshes_stale_question_once

./mew dogfood --scenario resident-loop --cleanup --json
status: pass, including resident_loop_processes_multiple_events and resident_loop_compacts_repeated_wait_thoughts

./mew dogfood --scenario native-work --cleanup --json
status: pass, including native_work_session_created_for_ready_coding_task,
native_work_records_start_action, and native_work_does_not_start_external_agent_run
```

Human-facing visibility:

```text
mew questions / mew focus now show old open questions with waiting=...
mew questions --all shows deferred stale questions with defer_reason=...
```

Judgment:

- The previous real-repo silence is fixed for stale task-bound questions.
- mew still respects a fresh unanswered question and waits instead of spamming.
- With explicit `--allow-native-work`, act-level passive runtime can now start
  a native `mew code` work session for ready coding tasks without delegating to
  external agents.
- Remaining cadence work: decide whether global/non-task questions should also
  age into a summary/reminder path, and tune the 24-hour threshold after longer
  dogfood.
