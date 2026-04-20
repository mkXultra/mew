# Mew Roadmap Status

Last updated: 2026-04-21

This file is the operational roadmap dashboard. It should stay short enough to
survive context compression and long-session reentry. Historical detail through
M5 was archived losslessly in
`docs/archive/ROADMAP_STATUS_through_M5_2026-04-20.md`.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | Native work sessions can inspect, edit, verify, resume, and expose an audit trail without delegating the whole loop. |
| 2. Interactive Parity | `done` | Cockpit/live/follow controls, approvals, compact output, interruption handling, and fresh-restart comparative evidence reached parity for the documented gate. |
| 3. Persistent Advantage | `done` | M3 close gate passed with strict reentry/comparator evidence plus half-hour, one-hour, four-hour, week-scale, and ten-day proof shapes. |
| 4. True Recovery | `done` | Crashed/interrupted runtime and work-session effects can be classified, safely retried/requeued when deterministic, or surfaced for durable review. |
| 5. Self-Improving Mew | `done` | Five consecutive no-rescue self-improvement loops passed with verification, audit, recovery evidence, and explicit user approval to close M5. |
| 5.1 Trust & Safety Close-Out | `done` | Post-M5 hardening added adversarial review and enforceable safety hooks without moving the M5 gate. |
| 6. Body: Daemon & Persistent Presence | `in_progress` | Core daemon body is implemented; enhanced multi-hour Docker proof is running. |
| 6.5. Self-Hosting Speed | `done` | Clean medium/compact resident rerun produced and verified a paired edit proposal with first THINK under 10s. |
| 6.6. Coding Competence: Codex CLI Parity | `foundation` | First slice is coding plan state plus path recall; mew is still naive compared with Codex CLI. |
| 7. Senses: Inbound Signals | `foundation` | Signal source gates, journaling, RSS/Atom parsing, and atom source-kind fetch support exist; deeper wiring is deferred until M6.6. |
| 8. Identity: Cross-Project Self | `not_started` | Add user-scope identity and memory across projects while preserving project boundaries. |
| 9. Legibility: Human-Readable Companion | `not_started` | Make mew's state understandable to humans without raw internal structures. |
| 10. Multi-Agent Residence | `not_started` | Let multiple model families inhabit the same mew with durable notes, review, and disagreement artifacts. |
| 11. Inner Life | `not_started` | Promote journal, dream, mood, and self-memory into a curated, auditable continuity of self. |

## Active Milestone Decision

Last assessed: 2026-04-20 21:25 JST.

Active work: **M6.6 Coding Competence: Codex CLI Parity** while the M6 enhanced
proof runs in parallel.

Reasoning:

- M1-M5 are closed. M5 closure was explicitly approved by the user on
  2026-04-20 after M3 and M4 were already closed.
- M5.1 closed as a bounded patch that makes future self-improvement safer
  without retroactively changing the M5 done gate.
- M6 core daemon work exists and the enhanced multi-hour Docker proof is
  running detached. Waiting for that proof should not block useful local work.
- M7 signal registry foundation exists. M6.5 was inserted before deeper M7
  work because feature expansion exposed a speed blocker in mew-as-implementer
  loops.
- The first #320-class self-hosting attempts produced no reviewable edit
  proposal: xhigh had roughly 132s first THINK latency, high then stalled
  beyond three minutes, and the repaired model turns recorded interruption
  without edits.
- After prompt-size instrumentation and approval-path cleanup, session #301 did
  produce and apply a reviewable paired src/tests patch, but its recorded
  model metrics still used `high`/`full`.
- Clean rerun session #306 proved the speed path: it used
  `medium`/`compact_memory`, reached first useful output in 14.7s, proposed a
  paired dry-run edit in the third model step, and verified the applied patch.
- That closes the speed blocker, but it also exposes the next blocker: native
  coding tasks are still too prompt-driven and naive compared with Codex CLI.
  Recent dogfood showed path confusion, repeated search/read churn, and a model
  turn that wanted to finish after identifying the next edit instead of
  proposing it.
- M6.6 is now the earliest unfinished enabling milestone. It should make coding
  work plan, edit, verify, repair, self-review, and summarize with explicit
  evidence, before M7 expands the resident's senses and creates more work for
  the native implementer.
- `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` identifies the structural
  cause: durable memory is currently used as prompt bulk instead of a fast
  pointer/index.
- `claude-ultra` was consulted in session
  `f220b253-51d5-435e-ab24-520190e3f97e` and recommended prompt caching,
  reasoning-effort auto-adjustment, and differential context before deeper M7
  feature work. Codex agrees.
- Broad polish and general refactor remain non-goals. M6.6 work should target
  coding-task structure, not cosmetic CLI refinements.

Current next action:

1. Use this dashboard as the active decision after context compression.
2. Let the enhanced M6 Docker proof finish, collect it, and run
   `./mew proof-summary proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910 --strict`.
3. Start M6.6 with the first native coding-loop slice: durable coding plan
   state plus anti-churn/path recall.
4. Before counting the three comparator tasks, run the M6.6 bootstrap
   integration gate: have mew implement one small reference-grounded
   coding-loop slice itself, with Codex only reviewing/approving. Any Codex
   rescue edit fails this bootstrap gate and is recorded as a blocker.
5. Compare each M6.6 dogfood task against Codex CLI standards: correctness,
   minimal edits, verifier choice, repair behavior, latency, and reviewability.
6. If the M6 proof passes while M6.6 is in progress, write the M6 close gate
   without dropping the M6.6 active focus.
7. Keep M5.1 as a closed safety baseline. Do not reopen it unless a future
   self-improvement loop violates the documented safety hooks.

Human-role transition rule:

- M5.1 dogfooded the first small slice with **mew as implementer** and Codex
  acting as the human reviewer/approver. The rescue was recorded honestly, so
  it did not count as autonomy credit.
- Treat rescue edits by Codex as a signal that mew is not ready to own that
  class of task yet. Record the blocker instead of silently fixing around it.
- Low- and medium-risk implementation can now use mew as primary implementer
  with Codex acting as human reviewer/approver. Rescue edits by Codex still
  disqualify the loop from autonomy credit and should be recorded as blockers.

## Milestone Evidence

### M1: Native Hands

Status: `done`.

Evidence:

- `mew work --ai` can run native read/search/glob/edit/write/shell/test tools
  inside a work session.
- Tool calls are journaled and resumable enough for later audit.

Missing proof:

- None for the documented M1 gate.

### M2: Interactive Parity

Status: `done`.

Evidence:

- Live/follow cockpit surfaces, streaming/compact model output, readable
  action/result panes, approval controls, rollback, verification summaries,
  interruption handling, and fresh-restart comparator artifacts were
  implemented and dogfooded.
- Final M2 comparative artifact recorded parity with mew continuity advantage
  for the documented focused task gate.

Missing proof:

- None for the documented M2 gate. Future cockpit feel work must map to M5.1
  safety, M6 daemon operation, or later milestones.

### M3: Persistent Advantage

Status: `done`.

Evidence:

- `docs/M3_CLOSE_GATE_2026-04-20.md` records the close decision.
- The final four-hour Docker resident-loop proof
  `proof-artifacts/mew-proof-real-4h-20260420-1312` passed strict summary:
  `processed=240`, `passive=239`, passive gaps within 60-61 seconds, and
  `8/8` checks passed.
- Reentry/comparator evidence includes fresh-restart, source/test reentry,
  week-scale synthetic, and ten-day virtual-time proof shapes.

Missing proof:

- None for the documented M3 gate. Real multi-day evidence can strengthen M6
  and later milestones but should not reopen M3.

### M4: True Recovery

Status: `done`.

Evidence:

- `docs/M4_CLOSE_GATE_2026-04-20.md` records the close decision.
- Runtime and work-session recovery classify effects, re-check world state, and
  choose resume/retry/abort/ask-user surfaces.
- Opaque shell side-effect retry remains a deliberate non-goal.

Missing proof:

- None for the documented M4 gate.

### M5: Self-Improving Mew

Status: `done`.

Evidence:

- `docs/M5_CLOSE_REVIEW_2026-04-20.md` records `Status: passed`.
- `./mew self-improve --audit-sequence 307 308 309 310 311` reported
  `candidate_sequence_ready`, `verification=True`, `recovery=True`,
  `no_rescue_review=True`, and `candidate_credit=True`.
- The sequence includes a recovery event on task `#310`.
- The user explicitly approved closing M5 on 2026-04-20.

Missing proof:

- None for the documented M5 gate. Do not move the gate retroactively.

### M5.1: Trust & Safety Close-Out

Status: `done`.

Evidence:

- `docs/M5_1_CLOSE_GATE_2026-04-20.md` records `Status: passed`.
- Task `#319` / work session `#299` created
  `.codex/skills/mew-adversarial-verifier/SKILL.md` through a mew-native
  self-improvement loop. Codex acted as human reviewer/approver and did not
  directly edit the file.
- Verification passed with
  `rg -n 'product-goal drift|safety boundaries|evidence quality|missing verification|hidden rescue|approve|reject|revise' .codex/skills/mew-adversarial-verifier/SKILL.md`.
- This is useful M5.1 implementation evidence but not autonomy credit:
  `./mew self-improve --audit 319` reports
  `loop_credit_status: not_counted_due_to_rescue` because reviewer steer was
  needed for a missing new-file read, missing `create=true`, and an invalid
  shell-style verifier.
- `mew self-improve --audit` now includes an audit-only `safety_boundaries`
  report for permission-context drift, governance/policy-path edits, external
  visible side-effect commands, budget-exhaustion policy, and ambiguous-recovery
  policy. Current task `#319` surfaces `safety_boundaries: needs_review` because
  it touched `.codex/skills` and changed its permission context.
- Validation: `uv run pytest -q tests/test_self_improve.py --no-testmon`,
  `uv run ruff check src/mew/self_improve_audit.py tests/test_self_improve.py`,
  `git diff --check`, and `./mew self-improve --audit 319`.
- `accept-edits` auto-approval now refuses to auto-apply self-improvement
  governance/policy edits and leaves them as pending approvals requiring
  explicit `mew work --approve-tool`. A regression test covers
  `ROADMAP_STATUS.md`: auto-approval is `safety_blocked`, the file stays
  unchanged, and explicit approval still applies the edit.
- The `mew-adversarial-verifier` criteria were applied manually by Codex to
  review the audit visibility and auto-approval escalation slices; decision:
  approve. This proves the review shape is usable, but not yet as part of a
  mew-native self-improvement loop.
- Self-improvement `run_command` / `run_tests` actions now block known
  external-visible side-effect commands before execution. A regression test
  verifies a proposed `git push origin main` records `safety_blocked`, never
  reaches tool execution, and leaves a work-session note.
- `mew self-improve --audit` now includes safety-blocked work-session events as
  `safety_boundaries.blocked_events`, so a blocked external side-effect attempt
  is visible in the readable audit bundle.
- Validation: the targeted accept-edits work-session tests passed with
  `--no-testmon`.
- Deterministic dogfood scenario `m5-safety-hooks` now exercises both hook
  families through real `mew work --live` paths with mocked model output:
  governance edits are held as pending approval under `accept-edits`, and
  `git push origin main` is blocked before tool execution and surfaced in the
  self-improve audit bundle.
- Validation: `./mew dogfood --scenario m5-safety-hooks --json` passed, and
  `uv run pytest -q tests/test_dogfood.py --no-testmon` passed.
- `mew self-improve --audit` now surfaces budget-exhaustion notes and ambiguous
  recovery states as safety-boundary findings. Budget events produce
  `needs_review`; interrupted/unrecovered or indeterminate recovery states
  produce `blocked`.
- Validation: `uv run pytest -q tests/test_self_improve.py --no-testmon`
  passed.
- `claude-ultra` close-readiness review in ACM session
  `0a0a8006-0753-471d-a1e3-a8f257089e1d` asked for combined verifier+hook
  evidence, budget/recovery interpretation, and a close-gate document. Those
  artifacts are now recorded in the close-gate doc.
- The `mew-adversarial-verifier` criteria were applied to the
  `/tmp/mew-m5-safety-hooks-proof` audit bundles for task `#1` and task `#2`;
  decision: `approve`. The governance audit produced `needs_review`; the
  external side-effect audit produced `blocked`.

Missing proof:

- None for the documented M5.1 gate. Future self-improvement loops should use
  the verifier routinely, and later milestones can harden the command-risk
  marker list and budget/recovery policy actions.

Goal:

- Raise post-M5 safety and review quality without turning M5.1 into an
  open-ended polish milestone.

Done when:

- A `mew-adversarial-verifier` skill or equivalent verifier can review a
  proposed self-improvement loop against product-goal drift, safety boundaries,
  and evidence quality.
- Hook-based safety boundaries enforce the M5 rules mechanically for governance
  edits, permission/policy edits, external-visible side effects, budget
  exhaustion, and ambiguous recovery.
- The above work is dogfooded through at least one self-improvement loop or
  equivalent scenario, with a readable audit bundle.
- Any refactor is limited to the code paths needed by the verifier or safety
  hooks.

Next action:

- Move to M6 Body.

### M6: Body - Daemon & Persistent Presence

Status: `in_progress`.

Goal:

- Turn mew from a summonable CLI into a durable resident process.

Evidence:

- `mew daemon status|start|stop|logs` now provides a daemon-shaped control
  surface over the existing runtime.
- `mew daemon status --json` reports runtime state, pid, uptime, lock state,
  current cycle, last tick, watcher counts/items, safety/autonomy state, output
  path, and repair/start/stop/log controls.
- Validation: `uv run pytest -q tests/test_daemon.py --no-testmon`, targeted
  `ruff`, `./mew daemon status --json`, `./mew help daemon status`,
  `./mew daemon logs --lines 3`, and `git diff --check` passed.
- `mew run --watch-path <path>` now scans file/directory snapshots inside the
  runtime loop and queues `file_change` external events with provenance when a
  watched path changes.
- The watcher event uses the existing `external_event` runtime path, so the
  same THINK/ACT and audit machinery handles it before waiting for the next
  passive tick.
- Validation: targeted watcher/runtime pytest, targeted `ruff`,
  `./mew daemon status --json`, and `git diff --check` passed.
- Dogfood scenario `m6-daemon-watch` now starts a background daemon with
  `--watch-path`, observes active watcher status and uptime via
  `mew daemon status --json`, modifies the watched file, verifies a processed
  `file_change` event through the `external_event` runtime path, and stops the
  daemon with watcher state returning to idle.
- Validation: `m6-daemon-watch` dogfood passed in
  `/tmp/mew-m6-daemon-watch-proof`, along with the focused dogfood pytest.
- Dogfood scenario `m6-daemon-restart` now starts a daemon, baselines a watcher,
  stops cleanly, changes the watched file while stopped, starts again, and
  verifies the restarted daemon compares against the previous process snapshot
  and processes the file change through `external_event`.
- Validation: `m6-daemon-restart` dogfood passed in
  `/tmp/mew-m6-daemon-restart-proof`, along with the focused dogfood pytest.
- `mew daemon pause|resume|inspect|repair` now exposes daemon-specific control
  verbs. Pause/resume update the same autonomy gate used by the runtime, inspect
  reports the daemon status surface, and repair delegates to the existing repair
  path under the daemon namespace.
- Validation: `uv run pytest -q tests/test_daemon.py --no-testmon`, targeted
  `ruff`, and `./mew daemon inspect` passed.
- Dogfood scenario `m6-daemon-loop` now starts a background daemon, lets it run
  repeated passive ticks, processes a real watched file change through
  `external_event`, exercises `pause`, `inspect`, and `resume` against the
  running daemon, stops cleanly, checks applied passive effects and daemon
  output logs, and verifies `mew focus` can reenter the stopped daemon state.
- Validation: `m6-daemon-loop` passed in `/tmp/mew-m6-daemon-loop-proof` with
  `duration=6`, `interval=2`, `processed_events=4`, `passive_events=3`, and
  passive gaps `[2.0, 2.0]`; the focused dogfood pytest also passed.
- Docker proof tooling now supports `m6-daemon-loop` duration/interval args and
  writes `/proof/artifacts/report.json`. `mew proof-summary` prefers that
  report, surfaces the source path, and rejects weak long proofs whose passive
  event count is far below the requested cadence.
- Validation: `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py::DogfoodTests::test_run_dogfood_m6_daemon_loop_scenario --no-testmon`,
  targeted `ruff`, `bash -n scripts/run_proof_docker.sh`, `git diff --check`,
  and short Docker smoke
  `proof-artifacts/mew-proof-m6-daemon-loop-smoke-20260420-1913` all passed.
- Enhanced multi-hour Docker proof is running detached:
  `mew-proof-m6-daemon-loop-enhanced-20260420-1910`, scenario
  `m6-daemon-loop`, duration `14400`, interval `60`, poll interval `0.2`.
  On completion, collect with
  `scripts/collect_proof_docker.sh mew-proof-m6-daemon-loop-enhanced-20260420-1910`.

Missing proof:

- The enhanced multi-hour resident proof is running but not complete yet.
- M6 should not close until the collected Docker artifacts pass
  `./mew proof-summary proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910 --strict`
  with actual passive counts near the requested 4h/60s cadence.

Done when:

- `mew daemon status` reports uptime, active watchers, last tick, last event,
  current task, and safety state.
- A real file or git event triggers a passive turn end to end without manual
  polling.
- A restart after terminal close, process stop, or reboot reattaches without
  user rebrief.
- A multi-hour resident proof runs through the daemon path, not only a direct
  foreground loop.
- The daemon can be paused, inspected, repaired, and resumed from CLI/chat.

### M6.5: Self-Hosting Speed

Status: `done`.

Goal:

- Make mew fast enough that a resident model can implement small mew changes
  inside mew instead of falling back to a fresh external coding CLI.

Evidence:

- `ROADMAP.md` now defines M6.5 as the gate between a durable body and deeper
  M7 feature expansion.
- `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` diagnosed the current speed
  blocker: prompt construction and persistent memory injection are too heavy
  for small implementation loops.
- The final committed default Codex reasoning effort is `high` in `84a2a99`,
  after `xhigh` proved too slow for the self-hosting path.
- The #320-class mew self-implementation attempt recorded the right failure:
  no reviewable edit proposal, model turns repaired after interruption, and no
  silent Codex rescue edits counted as autonomy.
- `claude-ultra` session `f220b253-51d5-435e-ab24-520190e3f97e` agreed that
  prompt pipeline speed work should precede further M7 collectors.
- Work model turns now persist `model_metrics` with context size, injected
  active-memory size/count, THINK prompt chars, THINK latency, ACT prompt chars,
  ACT latency, and total model seconds.
- `mew metrics` now prints and returns a `self_hosting` section with first
  THINK latency, first dry-run edit proposal latency, context chars,
  active-memory chars/count, prompt chars, and total model seconds.
- Work turns now select and record a reasoning policy: read-only exploration
  defaults to `low`, small implementation/verification to `medium`, and
  roadmap/recovery/safety/daemon/auth/policy work to `high`, with
  `MEW_CODEX_REASONING_EFFORT` as an explicit override.
- Non-high-risk work turns now use a compact prompt context for active memory:
  memory bodies are omitted from THINK/ACT prompts and replaced by
  id/path/name/description pointers, while full resume output remains available
  to humans.
- Compact prompt context now also uses tighter tool-call, model-turn, task,
  goal, and resume limits. On the active #320 session this reduced measured
  context from about `95k` chars to about `28k` chars, and THINK prompt from
  about `129k` chars to about `43k` chars before another real Codex rerun.
- `mew metrics` now summarizes prompt context modes so self-hosting reports can
  prove whether a task used full or compact resident memory injection.
- `mew metrics` now breaks down self-hosting prompt size into work-session,
  resume, tool-context, and model-turn context chars so future reruns can show
  which part still dominates.
- Running work model turns now save preflight prompt-size metrics before the
  THINK API call completes, so interrupted or timed-out self-hosting attempts
  can still report context size and chosen reasoning policy.
- The reasoning-effort policy now ignores historical task-description sections
  such as completed commits when matching high-risk terms, preventing a small
  #320-class M7 implementation task from being escalated to `high` and full
  prompt mode just because its history mentions M6/daemon work.
- The #320 dogfood patch reached the normal work-session approval surface and
  was applied through approvals #2120, #2121, and #2122, producing completed
  write tool calls #2123, #2124, and #2125 without manual rescue edits to the
  source/test files before approval. Focused verification passed:
  `uv run pytest -q tests/test_signal_fetch.py tests/test_signals.py --no-testmon`.
- The applied #320 slice added a minimal RSS/Atom feed parser and `rss`
  source-config fetch helper in `src/mew/signals.py`, plus mocked-fetch tests
  in `tests/test_signal_fetch.py`. CLI `signals fetch` wiring remained a
  deferred M7 follow-up, not part of the M6.5 speed gate.
- The initial #320 dogfood did not close M6.5: `mew metrics --kind coding
  --limit 8` still recorded the completed #320 model turns as
  `reasoning_efforts: high=2` and
  `prompt_context_modes: full=2`, with first THINK latency `128.209s` and
  first tool output for session #301 at `140.0s`.
- The root cause of the unexpected `high`/`full` rerun was task notes: the
  previous policy ignored historical sections in the task description but still
  matched high-risk terms from historical dogfood notes. The policy now ignores
  historical note prefixes such as `Dogfood note:`, `Long session checkpoint:`,
  and `Context save ` when selecting reasoning effort. A live policy check for
  task #320 now returns `medium` / `small_implementation`.
- The policy also stopped treating milestone numbers such as `M6.5` as
  inherently high risk. Real risk is now carried by terms such as daemon,
  safety, recovery, policy, auth, and permission instead of numeric milestone
  labels alone.
- Work prompt guidance now says implementation tasks with write roots should
  not finish merely because the next edit is clear; if exact old/new text or
  file content is available, the model should propose a dry-run edit/write
  action instead. This fixed the observed session #303 behavior where mew
  stopped after planning the next edit.
- Clean rerun session #306 closed the M6.5 gate. It used
  `reasoning_effort=medium` and `prompt_context_mode=compact_memory` for all
  three model turns. Metrics for the first turn were `context_chars=12182`,
  `think.prompt_chars=24819`, `active_memory_chars=2693`, and
  `think.elapsed_seconds=9.61`; first useful output arrived in 14.7s.
- The edit-proposal turn in #306 had `context_chars=24051`,
  `work_session_chars=22998`, `resume_chars=9540`, `tool_context_chars=7471`,
  `active_memory_entries=3`, `think.prompt_chars=37412`, and
  `think.elapsed_seconds=11.679`. It produced paired dry-run edits #2142/#2143
  without manual file rescue, then approval applied #2144/#2145 and focused
  verification passed.
- Compared with the failed #320 baseline (`high`/`full`, first THINK
  `128.209s`, `context_chars` about `104k`, THINK prompt about `138k`, first
  tool output `140.0s`, and no fast edit proposal), #306 is a clear speed
  improvement and reaches the normal reviewer approval surface.
- Validation: `tests/test_work_session.py`, `tests/test_metrics.py`,
  `tests/test_reasoning_policy.py`,
  `tests/test_commands.py::CommandTests::test_metrics_command_prints_observation_metrics`,
  targeted `ruff`, `uv run python -m py_compile`, and `git diff --check` passed.

Closed proof:

- A clean post-policy resident rerun populated `medium` / `compact_memory`
  self-hosting metrics and reached a verified paired edit through the normal
  work-session approval path.
- Residual speed work remains, but it is no longer the active blocker. If
  future resident loops regress, add Codex prompt caching or stronger
  tool-choice guidance as a targeted follow-up.

Done when:

- A self-hosting dogfood report records first THINK latency, prompt/context
  size, memory injection size, time to first tool, and time to first edit
  proposal.
- Small implementation and exploration work default to a lower reasoning effort
  than safety, recovery, and roadmap work, with the chosen effort recorded.
- A small implementation task reaches a reviewable edit proposal without human
  rescue edits or repeated broad read-only exploration.
- The same #320-class task that previously stalled can be rerun with a clear
  improvement in first useful output and edit-proposal latency.
- The reviewer can approve, reject, or steer the mew-generated change from the
  normal work-session surfaces.

Next action:

- Start M6.6 and treat the observed coding-loop naivete as the next blocker
  before deeper M7 work.

### M6.6: Coding Competence - Codex CLI Parity

Status: `foundation`.

Goal:

- Make native coding tasks feel as capable as Codex CLI for small-to-medium
  repo edits, while preserving mew's resident state and approval surfaces.

Evidence:

- M6.5 clean rerun proved that mew can reach a reviewable edit quickly enough
  for self-hosting: session #306 used `medium` / `compact_memory`, produced
  paired dry-run edits, and verified the applied patch.
- The same dogfood sequence also exposed coding competence gaps that speed work
  alone does not solve: path confusion in earlier attempts, repeated broad
  search/read exploration, and a finish decision after the next edit was clear.
- Current work-session prompts now discourage finishing merely because the next
  edit is clear, and reasoning policy no longer escalates milestone numbers
  alone to high-risk mode. These are useful guards, not a Codex CLI-level
  coding architecture.
- `docs/ADOPT_FROM_REFERENCES.md`,
  `docs/REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md`, and
  `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` remain the reference material
  for adopting mature CLI patterns without losing mew's resident shape.
- `claude-ultra` session `2923749a-f605-47fa-aa2a-ba01b38cfd0a` reviewed the
  proposed M6.6 gate and returned "qualified yes": M6.6 should exist before M7,
  but it must use a narrow first slice and measurable comparator evidence to
  avoid becoming a grab-bag.
- `docs/M6_6_CODEX_PARITY_COMPARE.md` now defines the M6.6 comparator template
  and the three predeclared task shapes required for close-gate evidence.
- The comparator now has a reference-grounded gate. M6.6 evidence must map each
  implementation slice back to `docs/ADOPT_FROM_REFERENCES.md`,
  `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`, and concrete
  `references/fresh-cli/{claude-code,codex}` files such as TodoWriteTool,
  exploreAgent, verificationAgent, StreamingToolExecutor, agentMemorySnapshot,
  and Codex patch/review prompts.
- `claude-ultra` session `2a605115-1a2f-4114-9a41-2062ddbcc4e2` reviewed the
  new gates and agreed they are conceptually correct. It recommended making the
  bootstrap a prerequisite, treating any Codex rescue edit as a failed
  bootstrap blocker, and adding a dedicated bootstrap record section.
- Bootstrap task #322 / session #307 ran with mew as implementer and Codex only
  steering/reviewing. It did not produce edits and exposed the exact
  `read_file` old-string retention blocker. Retry #323 after `ca9ba94` then
  succeeded for one small coding-loop slice: mew authored dry-run edits for
  `src/mew/work_loop.py` (#2182) and `tests/test_work_session.py` (#2183),
  Codex only reviewed/approved/applied them (#2184/#2185), focused pytest
  passed with 2 tests, and `rescue_edits=0`. Reviewer steering and one
  read-root permission repair were still needed. This is recorded in
  `docs/M6_6_CODEX_PARITY_COMPARE.md` as bootstrap evidence for a small slice,
  not full M6.6 closure.
- M6.6-B mew-side comparator task #324 / session #310 passed as a bugfix with
  regression test: mew authored dry-run edits #2207/#2208, Codex
  reviewed/approved/applied them as #2209/#2210, focused pytest passed, and
  `rescue_edits=0`.
- M6.6-A mew-side comparator task #325 / session #311 passed as a
  behavior-preserving refactor: after narrow source/test reads and one reviewer
  steer to stop source rereads, mew produced a paired dry-run batch
  (#2221/#2222), Codex approved/applied it as #2223/#2224, focused pytest
  passed on apply, reviewer same-surface audit found the literal only in
  `src/mew/work_loop.py` and `tests/test_work_session.py`, and broader
  `uv run python -m unittest tests.test_work_session` passed. `rescue_edits=0`.
- The matching Codex CLI comparator for M6.6-A ran in
  `/tmp/mew-m66a-codex-20260420-2316` against commit `3ea02ea`, converged on
  the same source refactor with a slightly smaller test delta, and passed the
  preferred focused verifier
  `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch --no-testmon`
  with `1 passed in 0.47s`. The run used one narrow search, four narrow reads,
  and `rescue_edits=0`; `uv` created a local `.venv` in the detached worktree,
  so this comparator completed without the environment caveat seen in M6.6-B.
- The matching Codex CLI comparator ran in
  `/tmp/mew-m66b-codex-20260420-2218` against commit `ac8b7d6`, produced a
  comparable source/test patch, and passed the focused regression via an
  existing pytest environment. Normal `uv run` verification hit sandbox/cache
  dependency limits, so the comparator is recorded with an environment caveat.
- Budget-based work-context compaction now preserves `recent_read_file_windows`
  in full prompt mode, so high-effort or large-session turns still retain exact
  recent line-window reads for edit preparation instead of dropping that
  surface when the recent tool/model window is reduced. Focused and broader
  context tests passed after the change.
- M6.6-C task #326 tested a small-feature comparator slice for suggested
  verifier fallback, but sessions #312 and #313 did not reach a dry-run edit.
  The runs repeated targeted read/search recovery and one live planning turn
  hung before edit proposal, so this attempt is recorded as blocker evidence
  only and does not count toward M6.6 closure.
- A direct supervisor patch then added the fallback: when `run_tests` is chosen
  without an explicit command and no configured `verify_command` exists, the
  loop now prefers
  `work_session.resume.suggested_verify_command.command`. Focused and broader
  validation passed, but this patch is not comparator evidence because mew did
  not author a reviewable dry-run edit in #326.
- M6.6-C task #327 / session #314 then replaced the blocked #326 evidence path
  with a fresh mew-side run: after a few repeated narrow searches and two
  reviewer steers, mew used one exact src window read, proposed a paired
  dry-run edit batch, focused pytest passed on apply, and reviewer broader
  `uv run python -m unittest tests.test_work_session` passed. The resulting
  patch in `src/mew/work_loop.py` and `tests/test_work_session.py` tells the
  model to reuse an exact `recent_read_file_windows` entry instead of issuing
  another same-span `read_file` during edit preparation. `rescue_edits=0`.
- M6.6 task #328 / session #315 advanced built-in verifier discovery: mew
  added prompt guidance telling THINK to prefer `run_tests` with the broader
  `suggested_verify_command` before finish when
  `verification_confidence.status` is `narrow` after source edits, then
  validated the paired change with both the focused selector and the broader
  inferred module verifier. The mew-side run proposed a reviewable dry-run
  batch, applied it, ran the narrow verifier, chose the broader verifier on the
  next turn, and only then finished. `rescue_edits=0`.
- M6.6 task #329 / session #316 advanced repair-loop behavior: mew added
  prompt guidance telling THINK to prefer one narrow repair step using failing
  output or `suggested_safe_reobserve` after the latest verification or
  write/apply failure when the failure is not obviously
  permission/environment-related. The mew-side run proposed a paired dry-run
  batch, applied it, ran the focused verifier, then chose the broader
  suggested verifier before finish. `rescue_edits=0`.
- M6.6 task #330 / session #317 advanced same-surface self-review behavior:
  after two reviewer steers corrected repeated search churn and one bad
  line-window guess, mew read exact source/test windows, proposed a reviewable
  paired dry-run batch, applied it, and passed broad `uv run pytest -q`
  verification. On the next turn, mew obeyed the new prompt rule by performing
  one narrow same-surface audit read on the nearby `ACT`/control surface in
  `src/mew/work_loop.py` before finishing, then recorded why that sibling
  surface was covered/out of scope for the THINK-only reminder. `rescue_edits=0`.
- M6.6 task #331 / session #318 targeted durable path recall, but the mew-side
  run stalled in an exact-old-string reread loop after narrow source/test
  reads; bundle pressure rose to `high` before any dry-run edit was proposed.
  A direct supervisor patch then added machine-readable
  `working_memory.target_paths`, surfaced it in the resume/text bundle, and
  taught `build_work_think_prompt` to prefer `working_memory.target_paths`
  before broader project search. Focused working-memory/prompt tests, `ruff`,
  `py_compile`, and `git diff --check` passed. This is product progress, not
  mew-side comparator evidence.
- M6.6 task #332 / session #319 then turned that `working_memory.target_paths`
  surface into fresh mew-side anti-churn evidence: after one steer away from a
  repeated same-symbol `search_text`, mew stayed on the known src/test paths,
  proposed a paired dry-run edit batch (#2345/#2346), Codex only
  approved/applied it as #2347/#2348, chose
  `uv run python -m unittest tests.test_work_session` as the focused verifier,
  passed it with `396 tests`, performed one narrow same-surface audit read, and
  finished cleanly. The resulting prompt change in `src/mew/work_loop.py` and
  `tests/test_work_session.py` tells THINK to issue a direct `read_file` on a
  known `working_memory.target_paths` entry before repeating same-surface
  `search_text`. `rescue_edits=0`.
- M6.6 task #333 / session #320 attempted to widen durable plan state with a
  three-file `plan_items` checklist slice, but under high context pressure the
  native loop could not safely reconstruct the full
  `work_session.py`/`work_loop.py`/test batch after one old-text mismatch in
  `src/mew/work_session.py`. The task was recorded as blocked evidence for
  multi-file exact-old-text retention, not as a passed mew-side slice.
- M6.6 task #334 / session #321 then retried the narrower persistence half in
  `src/mew/work_session.py` and `tests/test_work_session.py`. Mew reached a
  partial dry-run, but the accepted patch landed directly afterward for product
  progress rather than autonomy credit: `working_memory.plan_items` now seeds in
  startup memory, normalizes and caps to 3 items, surfaces in resume text, and
  appears in model context. Focused `uv run python -m unittest
  tests.test_work_session`, `ruff`, `py_compile`, and `git diff --check`
  passed. This is product progress, not no-rescue mew-side evidence.
- M6.6 task #335 / session #322 then attempted the next narrower checklist
  evidence slice: surface `working_memory.plan_items` in `recent_decisions` and
  `compressed_prior_think` summaries inside `src/mew/work_session.py` with a
  paired test update. Even after multiple reviewer steers to stop redundant
  search and pin exact spans, the native loop repeatedly reread the same exact
  builder/formatter windows, exhausted the step budget at `pressure=high`, and
  finished without proposing a dry-run edit. The feature then landed directly
  as product progress: `recent_decisions` and `compressed_prior_think` now both
  carry clipped `plan_items`, and `format_work_session_resume()` renders those
  items in the Recent decisions / Compressed prior think blocks. Focused `uv
  run python -m unittest tests.test_work_session`, `ruff`, `py_compile`, and
  `git diff --check` passed. This is blocker evidence plus product progress,
  not no-rescue mew-side evidence.
- M6.6 task #336 / session #323 then attacked that measured blocker directly in
  `src/mew/work_loop.py` and `tests/test_work_session.py`: after two narrow
  reviewer steers, mew searched the existing `recent_read_file_windows`
  surfaces, read one exact source window and one nearby test window, proposed a
  paired dry-run edit batch, applied it, passed `uv run python -m unittest
  tests.test_work_session`, performed one narrow same-surface audit read, and
  finished cleanly. The resulting patch now exposes
  `work_session.recent_read_file_windows` in normal/full work-session context,
  not only after compaction, while leaving `context_compaction` itself gated to
  compacted modes. `rescue_edits=0`.
- M6.6 task #337 / session #324 then retried a fresh same-file multi-span
  `src/mew/work_session.py` slice using the landed #336 surface: add
  `working_memory.target_paths` to `recent_decisions` and
  `compressed_prior_think` summaries with paired test updates. The native loop
  read the exact src/test windows but still repeated the same `work_session.py`
  exact-span rereads instead of reaching a dry-run edit batch. The feature then
  landed directly as product progress: `recent_decisions` and
  `compressed_prior_think` now both carry `target_paths`, and
  `format_work_session_resume()` renders them in the summary blocks. Focused
  `uv run python -m unittest tests.test_work_session`, `ruff`, `py_compile`,
  and `git diff --check` passed. This is blocker evidence plus product
  progress, not no-rescue mew-side evidence.
- A direct supervisor patch then widened
  `WORK_RECENT_READ_FILE_WINDOW_LIMIT` from `2` to `5` in
  `src/mew/work_loop.py`, with a focused regression in
  `tests/test_work_session.py` proving that five recent exact read windows
  survive in full context for same-file multi-span edit preparation. Focused
  `uv run python -m unittest tests.test_work_session`, `ruff`, `py_compile`,
  and `git diff --check` passed. This is product progress aimed at the #337
  blocker, not mew-side evidence.
- M6.6 task #338 / session #325 then retried the next fresh
  `src/mew/work_session.py` same-file multi-span slice for
  `working_memory.open_questions`. The native loop reached a paired dry-run
  edit proposal, but that batch covered only the `recent_decisions` path and
  missed the matching `compressed_prior_think` changes, so it was correctly
  rejected. The follow-up turns then kept rereading overlapping and adjacent
  `src/mew/work_session.py` exact spans instead of reusing already-known
  context, which showed that the remaining blocker was not only window count:
  same-path overlapping/adjacent recent read windows were displacing each
  other. This is blocker evidence, not no-rescue mew-side evidence.
- A direct supervisor patch then changed `build_recent_read_file_windows()` to
  merge same-path overlapping or adjacent line windows instead of spending
  separate slots on each repair reread, with a focused regression in
  `tests/test_work_session.py` proving that the merged windows retain the full
  `4350-4417` and `3859-3881` exact spans while still preserving the paired
  test windows and the older `3217-3248` source window under the five-window
  cap. Focused `uv run python -m unittest tests.test_work_session`, `ruff`,
  `py_compile`, and `git diff --check` passed. This is product progress aimed
  at the #338 blocker, not mew-side evidence.
- M6.6 task #339 / session #326 then retried the fresh
  `working_memory.open_questions` summary-recall slice after the merged-window
  patch. This time the native loop no longer fell into the same-file reread
  churn seen in #337/#338: it reached the intended narrow pattern of
  `search_text -> exact read_file windows -> paired dry-run edit batch`.
  However, the first dry-run batch still missed one required source surface,
  and the repair attempt then failed with `old text was not found` on the
  final source edit. That shifts the remaining blocker from recent-window
  eviction to stable multi-edit batch assembly and exact old-text matching
  under medium context pressure. The feature then landed directly as product
  progress: `recent_decisions` now carries `open_questions`, and
  `format_work_session_resume()` renders `open_questions` in both the Recent
  decisions and Compressed prior think blocks, with paired test coverage.
  Focused assertions plus `uv run python -m unittest tests.test_work_session`,
  `ruff`, `py_compile`, and `git diff --check` passed. This is blocker
  evidence plus product progress, not no-rescue mew-side evidence.
- A direct supervisor patch then tightened write-batch normalization for M6.6:
  if a code write batch would exceed the five-tool limit, mew now returns
  `wait` instead of truncating the batch and silently dropping required sibling
  edits. The THINK prompt now also says not to propose a partial batch when the
  full required write set exceeds five tools, and the tests cover both the
  prompt text and the new refusal behavior. `uv run python -m unittest
  tests.test_work_session`, `ruff`, `py_compile`, and `git diff --check`
  passed. This is product progress aimed at the #339 blocker, not mew-side
  evidence.
- A direct supervisor patch then tightened batch-failure cleanup for M6.6:
  when a write batch hits a later sibling-tool failure after earlier dry-run
  edits have already been previewed, mew now marks those earlier dry-run
  approvals `indeterminate` and removes them from `resume.pending_approvals`
  instead of leaving a misleading partial-approval surface behind. The tests
  now cover the failing batch case directly, and `uv run python -m unittest
  tests.test_work_session`, `ruff`, `py_compile`, and `git diff --check`
  passed. This is product progress aimed at the #339 blocker, not mew-side
  evidence.
- A direct supervisor patch then tightened same-file write-batch planning for
  M6.6: code write batches may now contain at most one write/edit per file
  path, and the THINK prompt now tells mew to collapse multiple hunks for the
  same file into one `edit_file` or `write_file` against the most recent exact
  window for that path. Focused prompt/normalization tests plus `uv run python
  -m unittest tests.test_work_session`, `ruff`, `py_compile`, and `git diff
  --check` passed. This is product progress aimed at the #339 blocker, not
  mew-side evidence.
- M6.6 task #340 / session #327 then tested that same-path rule with a fresh
  `src/mew/work_session.py` paired source/test slice. The native loop obeyed
  the rule: it moved from batched narrow searches to exact line-window reads,
  realized the source change needed one consolidated `src/mew/work_session.py`
  edit rather than duplicate same-file writes, and after one interrupt steer
  chose a no-change finish instead of proposing an unsafe batch. That is
  blocker evidence, not no-rescue credit: the bridging source window
  `3862-4414` spans about 27.9k chars, so with the current 12k `read_file`
  default and 12k/6k full-prompt/recent-window context caps the exact old text
  remained prompt-truncated even after the correct single-file plan was found.
- A direct supervisor patch then targeted that new #340 blocker: explicit
  `read_file` line-window requests now auto-scale `max_chars` from `line_count`
  when the model does not provide one, and full-prompt work context now keeps
  the larger line-window result visible in `tool_calls` instead of clipping it
  back to the old 12k display cap. The THINK prompt now tells mew that
  line-window reads auto-scale `max_chars` for edit preparation. Focused
  read-parameter/context tests plus `uv run python -m unittest
  tests.test_work_session`, `ruff`, `py_compile`, and `git diff --check`
  passed. This is product progress aimed at the #340 blocker, not mew-side
  evidence.
- M6.6 task #341 / session #328 then retried the same `last_verified_state`
  slice after commit `ad55c17`. The native loop improved further: it moved
  from batched searches to one bridged source read (`tool_call #2503` with
  `max_chars=50000`, `result.truncated=False`, `result_text_len=26421`) plus a
  cached paired test window, and it no longer claimed the bridge was missing at
  the tool layer. But the run still closed as blocker evidence, not no-rescue
  credit: after one interrupt steer, mew said the exact bridged old text was
  present in `tool_calls[#2503]` yet still not reusable because
  `recent_read_file_windows` kept only a truncated cache for that same span, so
  it treated the single-file edit boundary as unresolved and chose a no-change
  finish.
- A direct supervisor patch then aligned the cache with that #341 evidence:
  `build_recent_read_file_windows()` now preserves full text for explicit
  line-window reads when the source result is untruncated and the effective
  `max_chars` ceiling allows it, while keeping the older 6k cap for normal
  offset reads and oversized results. The THINK prompt now explicitly says that
  if `recent_read_file_windows` is truncated, mew may fall back to the matching
  `tool_calls[*].result.text` before declaring old text unrecoverable. Focused
  recent-window/context tests plus `ruff`, `py_compile`, and broader
  `uv run python -m unittest tests.test_work_session` passed. This is product
  progress aimed at the #341 blocker, not mew-side evidence.
- A direct supervisor patch then refined that same-file retention policy for
  large overlapping explicit line-window reads: when
  `build_recent_read_file_windows()` merges adjacent or overlapping same-path
  windows, it now uses the larger effective text budget from those explicit
  line-window reads instead of refusing the merge once one window exceeds the
  default 6k cap. Focused prompt-window regressions, `ruff`, `py_compile`, and
  `git diff --check` passed. This is product progress aimed at the #343
  blocker, not mew-side evidence.
- M6.6 task #343 / session #331 then turned that direct patch into fresh
  mew-side same-file multi-span evidence on the long-blocked
  `last_verified_state` slice. The native loop recovered the formatter anchor,
  read the exact formatter and builder windows, proposed one paired dry-run
  batch with `edit_file` for `tests/test_work_session.py` and
  `edit_file_hunks` for `src/mew/work_session.py`, auto-applied both writes,
  passed `uv run python -m unittest tests.test_work_session` with `407 tests`,
  completed the required same-surface audit inside `src/mew/work_session.py`,
  and finished cleanly with `rescue_edits=0`. The landed feature now carries
  `working_memory.last_verified_state` through `recent_decisions` and renders
  that field in the Recent decisions block. This is implementation evidence
  for the frozen M6.6 set, not an extra comparator slot.
- M6.6 task #344 / session #332 then targeted the first-slice durable plan
  state gap in `src/mew/work_loop.py` and `tests/test_work_session.py`: make
  THINK explicitly expose `working_memory.plan_items` in the schema text and
  instruct the model to keep up to 3 short checklist items when more than one
  concrete step remains. The native loop did eventually land and verify the
  paired patch with `edit_file_hunks` on both files, but only after repeated
  explicit steers, three zero-match test searches, a temporary wait/replan, and
  a mid-task stop request. Validation passed (`uv run python -m unittest
  tests.test_work_session`, focused pytest, `ruff`, `py_compile`, and
  `git diff --check`), but this should be carried as product progress rather
  than no-rescue mew-side evidence.
- A direct supervisor prompt patch then addressed the fresh #344 drift:
  `build_work_think_prompt()` now says that when guidance, recent windows, or a
  recent failure already identify an exact `line_start`/`line_count` window,
  THINK should refresh that same targeted window instead of falling back to an
  offset `read_file` from the top of the file. Focused prompt tests, `ruff`,
  `py_compile`, and `git diff --check` passed. This is product progress aimed
  at the #344 targeted-context blocker, not mew-side evidence.
- M6.6 task #345 / session #333 then tested the next prompt-hygiene slice in
  `src/mew/work_loop.py` and `tests/test_work_session.py`: add one THINK prompt
  sentence telling mew to keep `working_memory.open_questions` limited to
  unanswered items and drop resolved questions once answered. The native loop
  eventually proposed the paired dry-run `edit_file` batch, auto-applied it,
  passed `uv run python -m unittest tests.test_work_session` with `407 tests`,
  and finished cleanly. But it still needed one exact-window
  `interrupt_submit` steer to stop drifting off the prompt/test surfaces and
  pin the correct line windows first, so carry #345 as product progress rather
  than fresh no-rescue mew-side evidence.
- M6.6 task #346 / session #334 then retried the same prompt surface with a
  fresh no-steer `target_paths` hygiene slice. The native loop found the
  correct `build_work_think_prompt` test block and eventually read the exact
  `src/mew/work_loop.py` target-path guidance window without supervisor hints,
  but it still repeated the same `search_text src/mew/work_loop.py
  query=target_paths` once before first edit, so the run does not count as
  no-rescue evidence. A direct supervisor prompt patch then taught
  `build_work_think_prompt()` not to rerun the same `search_text` when the
  latest result already provides the needed line anchor, and to switch to a
  narrow `read_file` instead. Focused pytest, `ruff`, `py_compile`, and
  `git diff --check` passed. This is blocker evidence plus product progress,
  not mew-side evidence.
- M6.6 task #347 / session #335 then reran the prompt surface immediately
  after that patch with a fresh `target_paths` stale-path pruning slice. The
  native loop improved again: it found the correct `build_work_think_prompt`
  function anchor in `src/mew/work_loop.py`, found the correct
  `build_work_think_prompt` test block in `tests/test_work_session.py`, and
  refreshed the exact test window without supervisor hints. But before first
  edit it still repeated the same anchored `search_text
  src/mew/work_loop.py query=build_work_think_prompt`, so the no-steer proof is
  still not complete. A direct supervisor patch then added structured
  `redundant_search_observations` to `src/mew/work_session.py` resume data,
  rendered those observations in the formatted resume, and taught
  `build_work_think_prompt()` to use the signal's concrete `read_file`
  replacement instead of rerunning the same successful search. Focused pytest,
  `ruff`, `py_compile`, and `git diff --check` passed. This is blocker evidence
  plus product progress, not mew-side evidence.
- M6.6 task #348 / session #336 then turned that direct patch into fresh
  no-steer mew-side evidence on the same prompt surface. The native loop did
  not rerun the same anchored search again: it used the anchored result to move
  into narrow `read_file` observations on `src/mew/work_loop.py` and
  `tests/test_work_session.py`, proposed a paired dry-run edit batch, auto-
  applied it, passed `uv run python -m unittest tests.test_work_session` with
  `408 tests`, and finished cleanly with same-surface audit covered.
  `rescue_edits=0`. The landed feature now tells THINK to drop stale
  `working_memory.target_paths` entries once they are no longer needed, and the
  new `redundant_search_observations` signal proved strong enough to convert
  repeated anchored search into the intended read-before-edit behavior. This is
  implementation evidence for the frozen M6.6 set, not an extra comparator
  slot.
- M6.6 task #349 / session #337 then returned to the broader
  `src/mew/work_session.py` continuity surface: `memory_ok` now counts
  `plan_items`, `target_paths`, and `open_questions` as durable working-memory
  evidence, and the paired test now asserts that broader continuity reason. The
  native loop found the correct src/test surfaces without supervisor hints,
  eventually proposed a paired dry-run edit, auto-applied it, and passed `uv
  run python -m unittest tests.test_work_session` with `409 tests`. But it
  used a long adjacent-window reread chain before first edit, and same-surface
  audit then found one stale continuity-axis reason string that needed a direct
  paired follow-up patch. Focused continuity pytest, the full unittest,
  `ruff`, `py_compile`, and `git diff --check` passed. This is blocker
  evidence plus product progress, not fresh no-rescue mew-side evidence.
- A direct supervisor patch then added `adjacent_read_observations` to
  `src/mew/work_session.py`, rendered that signal in the formatted resume, and
  taught `build_work_think_prompt()` to use the signal's merged `read_file`
  suggestion instead of inching through overlapping or near-adjacent
  same-path windows. Focused pytest, `ruff`, `py_compile`, and `git diff
  --check` passed. A follow-up rerun task (#350) showed the new signal did
  change behavior, but that attempted rerun overlapped with the already-landed
  continuity diff in the working tree, so it does not count as fresh evidence.
- Decision 2026-04-21: stop running Codex CLI comparators on every M6.6 slice.
  Finish the mew-side M6.6 implementation set first, freeze a commit, then run
  the remaining comparator tasks in parallel detached worktrees as gate
  evidence. Comparator work is evidence collection, not the implementation
  critical path.
- On 2026-04-20, a proposed split to add `M6.5.2` as a separate
  "mew can implement mew sanely enough" milestone was considered and rejected.
  The current roadmap already assigns that role transition to the M6.6 first
  slice and bootstrap gate, so splitting it out would blur the closed M6.5
  speed gate and weaken the M6.6 evidence path.

Missing proof:

- Plan state and path recall: the #323 retry shows one small bootstrap slice,
  #332 proves one normal-case anti-churn/path-recall behavior for
  `working_memory.target_paths`, and #336 proves one blocker-reduction slice
  for exact recent window reuse in normal/full context. `working_memory.plan_items`
  and `working_memory.target_paths` now both exist as product behavior for
  persistence/surfacing across working memory, recent decisions, and compressed
  prior-think summaries, but broader durable checklist/path-recall behavior is
  still not proven by a no-rescue mew-side task across multi-file normal coding
  work or resume after context compression.
- Coding loop: built-in verifier discovery, prompt-level repair-loop guidance,
  and prompt-level same-surface self-review are now improved, but there is
  still no broader work-session self-review phase beyond the `src/mew`
  same-surface audit path.
- Comparator: M6.6-A and M6.6-B have checked-in side-by-side evidence, and
  M6.6-C now has a mew-side run, but the frozen-commit parallel comparator
  batch for the final M6.6 implementation set has not been run yet.
- M6.6-B comparator: side-by-side evidence exists with a Codex CLI environment
  caveat.
- Robustness: the successful retries still needed reviewer steering, one
  read-root permission repair, in #330 one incorrect line-window guess, in
  #331 an exact-old-string reread loop under high context pressure, and in
  #332 one steer to stop repeated same-symbol search before the exact read. The
  blocked #333, direct-patch #334, and blocked/direct-patch #335 follow-ups
  show where exact old-text retention failed before #336. The #336 blocker
  reduction improves same-session exact window reuse, but #337 and blocked
  #338 showed that same-file multi-span exact-old-text reuse inside
  `src/mew/work_session.py` still was not proven under medium context pressure:
  overlapping/adjacent same-path repairs displaced each other even after the
  five-window limit patch. #339 then showed the merged-window patch did remove
  the earlier reread churn and let the native loop reach a paired dry-run edit
  batch, but the next failure mode is still unresolved: stable multi-edit
  assembly and exact old-text matching across the full same-file source/test
  surface. The partial-write-batch refusal patch should reduce one source of
  that failure by stopping incomplete dry-run batches before approval, and the
  batch-failure cleanup patch now prevents stale pending approvals from hiding
  the real recovery path after a sibling-tool failure. A further direct patch
  now rejects duplicate same-path writes inside a code batch and tells THINK to
  collapse same-file hunks into one file-level edit, which should reduce the
  `old text was not found` failure mode observed in #339. #340 then showed the
  next blocker more precisely: once mew obeyed the one-file rule, it still
  could not form the consolidated src edit because the needed bridging
  line-window text was clipped by the 12k default read budget and prompt
  display cap. A direct follow-up patch now auto-scales explicit line-window
  reads and preserves those larger windows in full prompt context. #341 then
  showed one more contradiction: the full bridged text was visible in
  `tool_calls[#2503]`, but `recent_read_file_windows` still stored only a
  truncated cache for the overlapping formatter repair window under the five
  slot cap. The follow-up merge-budget patch fixed that retention policy for
  large explicit line windows, and #343 / session #331 converted it into a
  no-rescue mew-side pass for the same-file multi-hunk `edit_file_hunks`
  feature slice. That removes this exact retention blocker for
  `last_verified_state`, but broader normal-case autonomy is still not proven:
  #343 still used some exploratory search/read steps before the final batch,
  and durable plan/path recall across broader multi-file coding work remains
  open. #345 showed the landed targeted-reread guidance can be converted into a
  successful paired edit/verify/finish run once the exact source/test windows
  are pinned, but normal-case exact-surface selection for prompt/test slices is
  still not proven without supervisor hints. #346 improved that diagnosis:
  exact prompt/test surface discovery now works without steer, but search
  results are still not always converted into the anchored `read_file` step on
  the first try. #347 confirmed the remaining gap more precisely: even after a
  prompt-level warning, the native loop can still repeat the same successful
  anchor search before first edit. #348 then converted the structured
  `redundant_search_observations` signal into a fresh no-steer pass on the
  prompt surface, so that exact search-to-read conversion blocker is now
  reduced. The remaining missing proof is broader durable plan/path recall and
  multi-file normal-case autonomy, not this prompt-surface search loop. #349
  sharpened that remaining gap: on a broader `work_session.py` slice, mew can
  reach paired edit/verify, but adjacent source rereads before first edit and a
  same-surface audit follow-up still block no-rescue credit. The new
  `adjacent_read_observations` signal should reduce that reread creep, but it
  still needs a fresh unsatisfied rerun task to prove it.

Done when:

- The #323 bootstrap retry remains documented as the no-rescue baseline, and
  mew completes three predeclared representative coding tasks without Codex
  rescue edits: one behavior-preserving refactor, one bug fix with a regression
  test, and one small feature with paired source/test changes.
- The final frozen M6.6 implementation set is compared against Codex CLI in a
  checked-in comparator artifact that records first-edit latency, model turns,
  search/read calls before first edit, changed files, verifier commands,
  repair cycles, and review outcome.
- Every comparator task has `rescue_edits=0`, no obvious path hallucination, no
  repeated identical broad search/read loop, and a focused verifier command
  chosen by mew.
- Resident state improves the second and third coding task by reducing at least
  one of prompt size, repeated file discovery, or search/read count instead of
  merely increasing context.
- A coding task can plan, edit, verify, repair, self-review, and summarize with
  clear approval surfaces.
- Path recall and targeted context prevent obvious file/path hallucinations and
  repeated read-only churn in the normal case.

Next action:

- Keep M6.6 active; do not introduce `M6.5.2`.
- Carry the landed suggested-verifier fallback as product progress, but do not
  count task #326 as comparator evidence; use task #327 as the M6.6-C mew-side
  replacement run.
- Record task #332 / session #319 as fresh mew-side path-recall/anti-churn
  proof for the frozen M6.6 implementation set, but not as one of the three
  comparator slots.
- Carry the landed `plan_items` persistence half from #334 as product progress,
  but do not count it as no-rescue evidence.
- Carry the landed #335 summary surfacing patch as product progress, but do not
  count it as no-rescue evidence.
- Record task #336 / session #323 as fresh blocker-reduction evidence for
  `recent_read_file_windows` reuse in full context.
- Carry the landed #337 target-path summary patch as product progress, but do
  not count it as no-rescue evidence.
- Carry the landed recent-read-window limit expansion as product progress, but
  do not count it as no-rescue evidence.
- Carry the landed #345 `open_questions` hygiene patch as product progress, but
  do not count it as no-rescue evidence because the run needed an exact-window
  interrupt steer.
- Keep M6.6 on the mew-side critical path. The next task should be a fresh
  native no-steer proof task on a broader `src/mew/work_session.py` +
  `tests/test_work_session.py` slice that exercises durable plan/path recall in
  normal coding work rather than another prompt-only edit. Prefer a slice that
  needs exact remembered src/test windows plus one concrete plan_items /
  target_paths / open_questions carry-forward decision before the edit is
  proposed, but avoid the adjacent-window reread creep seen in #349 and require
  same-surface audit to close natively. Choose a fresh task whose premise is
  not already satisfied by the current worktree, so the next rerun can count as
  evidence. Do not return to comparator work until the mew-side implementation
  set is frozen.
- Defer the remaining/final Codex CLI comparator runs until the M6.6
  implementation set is frozen, then run them in parallel detached worktrees.
- Continue to treat read-window / prompt-truncation fixes and other
  mew-as-implementer readiness work as M6.6 first-slice sub-tasks, then
  continue with the next M6.6 coding-loop slice instead of per-slice
  comparator work.

### M7: Senses - Inbound Signals

Status: `foundation`.

Goal:

- Give the resident audited read-only signals from the user's working world.

Evidence:

- `mew signals enable|disable|sources|record|journal` now provides an explicit
  gate and journal for inbound signal sources. A source has a kind, reason,
  daily budget, enabled/disabled state, config, and durable journal entries.
- `mew signals record` refuses unknown, disabled, or budget-exhausted sources.
  Successful observations can queue a `signal_observed` runtime event with
  provenance, while `--no-queue` records without waking the runtime.
- `src/mew/signals.py` now has minimal RSS/Atom parsing and a gated feed-fetch
  helper, with mocked tests in `tests/test_signal_fetch.py`.
- Atom source-kind fetch support was dogfooded in the M6.5 clean rerun and
  verified with focused signal tests.
- Validation: `uv run pytest -q tests/test_signals.py --no-testmon`,
  targeted `ruff`, `./mew help signals record`, and `git diff --check` passed.

Missing proof:

- No CLI or daemon path fetches an enabled source on a resident schedule yet.
- No real-day unsolicited observation has been collected from signal evidence.
- Further M7 collector work is paused until M6.6 makes self-hosted coding work
  closer to Codex CLI level.

Done when:

- At least one non-file-system source can be enabled behind an explicit gate.
- Signals are journaled with provenance, budget, and suppression logic.
- Over a real day, mew produces at least one useful unsolicited observation
  without fabrication or spam.

### M8: Identity - Cross-Project Self

Status: `not_started`.

Goal:

- Add a user-scope identity across projects while preserving project-local
  facts.

Done when:

- A preference learned in one project is recalled in another without rebrief.
- Project facts do not leak into unrelated repos unless explicitly promoted.
- A comparator shows project switching is faster than briefing a fresh CLI.

### M9: Legibility - Human-Readable Companion

Status: `not_started`.

Goal:

- Make mew understandable as a resident to humans, not only as internal state.

Done when:

- A 30-60 second recorded demo is self-explanatory to a non-mew user without
  narration.
- `mew introduce`, `mew next`, focus/brief/resume summaries, actionable
  errors, and state diff surfaces have narrative defaults with `--json` or
  `--raw` escape hatches.
- Narrative output refuses to invent missing facts.

### M10: Multi-Agent Residence

Status: `not_started`.

Goal:

- Let multiple model families work inside the same mew without losing each
  other's notes, approvals, or disagreements.

Done when:

- Two different resident models complete a review-and-fix loop with durable
  cross-agent notes.
- Each resident can restart once and still recover the shared state.
- Disagreements become first-class auditable artifacts, not chat residue.

### M11: Inner Life

Status: `not_started`.

Goal:

- Give the resident a curated, auditable continuity of self across time.

Done when:

- After 30 days of real uptime, journal, dream, mood, and self-memory produce
  a resident-owned self-description that changes over time.
- The changes are auditable, reversible, and clearly separated from user-authored
  instructions.

## Current Roadmap Focus

Active focus: **M6.6 Coding Competence: Codex CLI Parity**.

The next long session should not drift into broad polish or general refactor.
The acceptable near-term work is:

- collecting the running M6 enhanced Docker proof when it finishes;
- adding explicit coding plan state, path recall, and anti-churn behavior to
  native work sessions;
- dogfooding representative coding tasks with mew as implementer and Codex as
  reviewer/approver;
- comparing mew traces against Codex CLI expectations for correctness, tool
  churn, latency, verification, repair, and reviewability;
- roadmap/status maintenance that preserves the active decision across context
  compression.

Keep M5.1 as the closed safety baseline and M6 as proof-pending while M6.6
removes the coding-competence blocker before deeper M7 signal work.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Archive detailed milestone evidence at each milestone close.
- Keep `ROADMAP_STATUS.md` around 200-300 lines.
- Put long dogfood narratives in `docs/` or `docs/archive/`.
- If a long-session decision changes, update the Active Milestone Decision
  immediately and save a mew context checkpoint.
