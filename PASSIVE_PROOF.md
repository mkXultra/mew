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
717 passed, 6 subtests passed

./mew dogfood --scenario runtime-focus --cleanup --json
status: pass
```
