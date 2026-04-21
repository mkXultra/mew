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
| 6. Body: Daemon & Persistent Presence | `done` | Collected 4-hour daemon proof now passes strict summary with 7/7 checks; the close gate records the retained-artifact false-negative caveat honestly. |
| 6.5. Self-Hosting Speed | `done` | Clean medium/compact resident rerun produced and verified a paired edit proposal with first THINK under 10s. |
| 6.6. Coding Competence: Codex CLI Parity | `done` | Bootstrap, three comparator slots, and the frozen Codex CLI side-by-side batch all passed with `rescue_edits=0`; closure caveats stay recorded, but the gate is closed. |
| 6.7. Supervised Self-Hosting Loop | `in_progress` | Two early bounded reviewer-gated iterations plus a fresh clean post-fix sixth iteration are recorded; dedicated governance scope fencing and stabilized live verification are in product, and the remaining gate is the supervised 8-hour proof. |
| 6.8. Task Chaining: Supervised Self-Selection | `not_started` | Remove per-iteration human-dispatch latency from the M6.7 loop by letting mew pick the next roadmap task itself under reviewer gating. |
| 6.9. Durable Coding Intelligence | `not_started` | Turn persistent state into a coding advantage so the Nth iteration on the same repo is measurably smarter than the 1st. Spec: `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`. |
| 7. Senses: Inbound Signals | `foundation` | Signal source gates, journaling, RSS/Atom parsing, and atom source-kind fetch support exist; deeper wiring stays deferred until the M6.7 supervised loop gate is proven. |
| 8. Identity: Cross-Project Self | `not_started` | Add user-scope identity and memory across projects while preserving project boundaries. |
| 9. Legibility: Human-Readable Companion | `not_started` | Make mew's state understandable to humans without raw internal structures. |
| 10. Multi-Agent Residence | `not_started` | Let multiple model families inhabit the same mew with durable notes, review, and disagreement artifacts. |
| 11. Inner Life | `not_started` | Promote journal, dream, mood, and self-memory into a curated, auditable continuity of self. |

## Active Milestone Decision

Last assessed: 2026-04-21 16:57 JST.

Active work: **M6.7 Supervised Self-Hosting Loop** while M5.1, M6, and M6.6
remain closed baselines and M7 stays deferred.

Reasoning:

- M1-M5 are closed. M5 closure was explicitly approved by the user on
  2026-04-20 after M3 and M4 were already closed.
- M5.1 closed as a bounded patch that makes future self-improvement safer
  without retroactively changing the M5 done gate.
- M6 is now closed. `docs/M6_CLOSE_GATE_2026-04-21.md` records the close gate,
  and the collected enhanced 4-hour Docker proof passes
  `./mew proof-summary ... --strict` with `ok=true`, `7/7` checks passed,
  `processed_events=241`, and `passive_events=239` against an expected minimum
  of `238`.
- The raw detached container still exited `1` and the original `report.json`
  still says `fail`, but that is now documented as a retention-based
  false negative in the close-out harness rather than missing daemon behavior.
- M6.5 is closed and M6.6 is now also closed: the bootstrap gate passed, all
  three predeclared comparator tasks passed with `rescue_edits=0`, the frozen
  detached Codex CLI comparator batch is recorded, and the first-edit blocker
  closed via task #363.
- M6.7 is now active. First supervised iteration proof is recorded in
  `docs/M6_7_FIRST_SUPERVISED_ITERATION_2026-04-21.md`: task `#364` /
  session `#352` stayed within the declared `src/mew/work_session.py` +
  `tests/test_work_session.py` scope, stopped for dry-run review, passed both
  focused and broader verification, and closed without reviewer rescue edits.
- The second supervised iteration is now also recorded in
  `docs/M6_7_SECOND_SUPERVISED_ITERATION_2026-04-21.md`: task `#365` /
  session `#353` landed a bounded `src/mew/commands.py` finish guard that
  keeps the session open while approvals, broader verification, or
  same-surface audit are incomplete, and it closed only after focused plus
  paired-source verification and a narrow commands.py same-surface audit.
- `docs/M6_7_SIXTH_SUPERVISED_ITERATION_2026-04-21.md` now records the fresh
  clean post-fix M6.7 proof: task `#374` / session `#362` stayed inside the
  declared `src/mew/brief.py` + `tests/test_brief.py` scope, ran the drift
  canary first, produced a reviewer-visible dry-run diff, passed the focused
  verifier plus `uv run python -m unittest tests.test_brief`, completed a
  same-surface audit, and finished with no reviewer rescue edits.
- M6.8 (Task Chaining) and M6.9 (Durable Coding Intelligence) are now
  registered as successors but neither is active. Ordering: M6.7 closes first,
  including the supervised 8-hour proof. Then M6.9 Phase 1-3 may begin under
  the M6.7 supervised-loop shape, while M6.8 may begin in parallel with those
  early M6.9 phases or before any M6.9 Phase 4 work that depends on chaining.
- This ordering keeps M6.7 as the stable supervised substrate while still
  registering the longer-horizon coding advantage. The M6.9 registration is
  meant to inform architectural choices made during remaining M6.7 work, not
  to reprioritize M6.7 implementation before its close gate is met.
- M7 signal registry foundation exists, but deeper signal work should not move
  ahead while M6.7 still lacks the supervised 8-hour proof.
- `claude-ultra` closure review `5974be96-8111-4918-abf4-4818d34ca635` agreed
  that M6.6 can be marked done honestly after the fresh B rerun and C
  comparator completed.
- Broad polish and general refactor remain non-goals. The next useful work is
  the supervised 8-hour proof, not more speculative coding-loop polish.

Current next action:

1. Use this dashboard as the active decision after context compression.
2. Treat M6.6 as a closed baseline. Reopen only if a future native coding loop
   regresses on rescue-edits, verifier choice, approval surfaces, or
   path-recall/anti-churn behavior.
3. Treat the first, second, and sixth bounded M6.7 iterations as the current
   supervised baseline: visible scope fence, proof-or-revert finish blocking,
   and clean post-fix reviewer-gated brief/focus behavior.
4. Treat task `#372` as strong bounded-loop evidence: the src/test diff itself
   landed with no reviewer code rescue, but broader live verification only
   closed after a direct verifier-runtime blocker patch outside the task scope.
5. Treat task `#374` as the clean fresh post-fix bounded proof on the now-
   stabilized live-verifier runtime.
6. The next gate is the supervised 8-hour M6.7 run with at least three real
   roadmap items, reviewer decisions recorded per iteration, zero
   proof-or-revert failures, and a green drift canary throughout.
7. Do not let mew self-author roadmap-status or milestone-close edits during
   M6.7; those remain reviewer-controlled until the supervised gate itself is
   proven.
8. Keep M5.1 as a closed safety baseline. Do not reopen it unless a future
   self-improvement loop violates the documented safety hooks.
9. Do not adopt `docs/PROPOSE_M6_7_UNSTICK_2026-04-21.md` into active M6.7 as
   written. The reconsideration trigger fired on fresh bounded item `#389`,
   but the exposed blocker was narrower than Explorer/Todo: write-ready diff
   generation. `work_loop.py` now carries the blocker-specific fix set
   instead: compact resume trimming, write-ready fast-path prompting with exact
   cached text, path normalization for cached windows, same-file-hunk guidance,
   and a write-ready timeout uplift. Those changes turned `#389` from repeated
   timeout stalls into a reviewer-visible paired dry-run/apply/verify/finish
   flow with no supervisor code rescue on the task itself. Keep Todo deferred
   as M6.8/M6.9 input and Explorer deferred post-M6.7; reconsider the broader
   proposal only if a new fresh bounded M6.7 item still stalls after these
   write-ready fast-path fixes.

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

Closure caveat and historical blocker trail:

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

Closure caveat and historical blocker trail:

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

Historical next action trail before closure:

- Move to M6 Body.

### M6: Body - Daemon & Persistent Presence

Status: `done`.

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
- `docs/M6_CLOSE_GATE_2026-04-21.md` records the final close decision.
- The collected enhanced multi-hour Docker proof
  `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910` now passes
  `./mew proof-summary ... --json --strict` with `ok=true`, `7/7` checks
  passed, `processed_events=241`, `passive_events=239`, `expected_min=238`,
  and passive gaps held to `60-61s` across the 4-hour run.
- The raw detached container exited `1` and the original `report.json` still
  records `status=fail`, but the close gate documents this as a
  retention-based false negative: the early watcher `external_event` aged out
  of the last-100 runtime-effect journal even though the processed
  `file_change` event remained present and auditable.

Missing proof:

- None for the documented M6 gate.

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

Historical next action trail before closure:

- Move active focus to M6.7 supervised self-hosting.

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

Historical next action trail before closure:

- Start M6.6 and treat the observed coding-loop naivete as the next blocker
  before deeper M7 work.

### M6.6: Coding Competence - Codex CLI Parity

Status: `done`.

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
- M6.6 task #351 / session #339 then retried a fresh broader
  `src/mew/work_session.py` continuity slice, but the native loop's first
  search used an invalid `pattern`, got zero matches, and immediately fell back
  to `read_file path=src/mew/work_session.py offset=0`, which disqualified the
  run before any edit attempt. The task was stopped and recorded as blocker
  evidence instead of spending more turns on a now-invalid proof attempt.
- A direct supervisor patch then added a code-level
  `broad_read_after_search_miss_guard` in `src/mew/work_session.py`, wired it
  into both work execution loops in `src/mew/commands.py`, and exposed the
  guard in model-visible tool-call context via `src/mew/work_loop.py`. The
  guard blocks `read_file` when the path is already a known target path, the
  latest same-path `search_text` returned zero matches, and the model tries to
  restart from the top of the file instead of reusing a targeted window or
  reformulating the search. Focused unit/integration pytest, `ruff`,
  `py_compile`, and `git diff --check` passed. This is blocker reduction and
  product progress; it still needs a fresh mew-side rerun on a broader
  `work_session.py` slice to count as no-rescue evidence.
- M6.6 task #352 / session #340 then turned that blocker reduction into a
  fresh broader no-rescue mew-side pass on `src/mew/work_session.py` and
  `tests/test_work_session.py`: mew found the exact continuity-repair and test
  surfaces, proposed a paired dry-run src/test edit batch, auto-applied both
  edits, passed `uv run python -m unittest tests.test_work_session`, completed
  the required same-surface audit natively, and finished the task without
  supervisor steer or rescue edits. There was still some small targeted churn:
  one repeated `working_memory_survived` search before the dry-run edit, and
  one zero-match same-surface search that then recovered to a narrow read of
  the known continuity window. Because the run stayed narrow and still closed
  natively, this counts as fresh mew-side implementation evidence for the
  frozen M6.6 set, not as a comparator slot.
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
  still needs a fresh unsatisfied rerun task to prove it. #351 then exposed one
  more broader-work_session failure mode: after a same-path search miss on a
  known target path, the native loop could discard that failure and restart
  with a top-of-file `read_file offset=0`. The new
  `broad_read_after_search_miss_guard` should reduce that fallback, but it
  still needed a fresh broader mew-side rerun to prove the native loop now
  reforms the search or reuses a targeted window instead of broad-reading.
  Task #352 provided that proof: after a same-surface search miss, the native
  loop recovered to a narrow `read_file` on the known continuity window and
  then finished the verified task natively. The remaining M6.6 missing proof is
  no longer this broad-read fallback. Task #353 then tightened the follow-up
  observation path on the same surface: when `search_text` matches are stored in
  string form, `redundant_search_observations` now extracts the concrete anchor
  line instead of degrading `suggested_next` to `line_start=None`. That
  blocker-reduction patch landed through a fresh no-steer mew-side paired
  src/test edit with native verification and same-surface audit. Task #354 then
  converted one broader durable path-recall carry-forward decision into a fresh
  no-rescue mew-side pass: `build_work_session_resume()` now surfaces
  `target_path_cached_window_observations` by pairing
  `working_memory.target_paths` with matching completed `read_file` windows, the
  paired tests prove that cached window survives through resume/context, and
  the native run closed with `uv run python -m unittest tests.test_work_session`
  plus a same-surface audit on `format_work_session_resume()`. Task #355 /
  session #343 then consumed that carried-forward signal in the next multi-file
  slice: `build_work_think_prompt()` now tells THINK to refresh a cached target
  path window from `target_path_cached_window_observations` before repeating
  same-surface `search_text` rediscovery, and the paired prompt-guidance test
  coverage now lives on the correct surface in `tests/test_work_session.py`.
  The native run passed `uv run python -m unittest tests.test_work_session
  tests.test_step_loop` and closed same-surface audit on
  `src/mew/work_loop.py`, but it needed one narrow steer to stop wasting time
  on the wrong test file (`tests/test_step_loop.py`) and switch to the real
  prompt-guidance surface. Count #355 as fresh multi-file implementation
  evidence for the frozen M6.6 set, but not as a clean no-steer proof. The
  remaining M6.6 missing proof is now narrower: broader multi-file normal-case
  autonomy and durable plan/path recall without supervisor steer, especially on
  slices that need correct paired source/test surfacing from the start. Task
  #356 then targeted exactly that missing surface-selection gap. Native mew
  work reached a reviewable paired dry-run batch, auto-applied it, and exposed
  the intended product patch, but the run drifted on the paired test anchor:
  it first inserted the new test before the existing `finally` block, then
  spent multiple repair turns rereading the same stale-test surface under high
  context pressure. The applied batch failed `uv run python -m unittest
  tests.test_work_session`, rolled back, and was stopped for supervisor
  takeover. A direct patch then landed the intended product change anyway:
  `_annotate_working_memory_with_latest_tool()` now carries a
  discovered-or-inferred `tests/**` partner when a stale latest-tool path
  points at `src/mew/**` and no test target is already present, and a focused
  resume test proves that stale src-path recall now keeps both the source and
  its paired test path. Count #356 as product progress plus a concrete blocker
  trace for repair-loop/test-anchor drift, not as no-rescue evidence.
- A direct supervisor patch then turned that #356 blocker into an explicit
  resume/prompt surface: `build_work_session_resume()` now emits
  `repair_anchor_observations`, a deduplicated list of source/test `read_file`
  anchors built from the latest failed write plus any still-relevant
  `working_memory.target_paths`, and `build_work_think_prompt()` now tells
  native mew to prefer those anchors before new same-surface `search_text` or
  broader rereads. Focused regressions, broader `uv run python -m unittest
  tests.test_work_session`, `ruff`, `py_compile`, and `git diff --check`
  passed. This is product progress aimed at the #356 repair-loop/test-anchor
  blocker, not yet fresh no-rescue evidence.
- M6.6 task #357 / session #345 then turned that landed
  `repair_anchor_observations` surface into fresh no-steer mew-side evidence.
  Native mew reused the cached repair anchors to recover the exact
  `src/mew/commands.py` and `tests/test_work_session.py` windows, proposed a
  paired dry-run src/test batch, auto-applied it, passed
  `uv run python -m unittest tests.test_work_session`, then chose and passed
  the broader inferred verifier `uv run python -m unittest tests.test_commands`
  before finish. The same session completed the required same-surface audit in
  `src/mew/commands.py` and closed with `rescue_edits=0`. The landed patch now
  makes `work --follow-status` prefer the first resume
  `repair_anchor_observations` entry for dead/stale snapshots and emit
  `recovery_path`, `recovery_line_start`, and `recovery_line_count` in text
  output while preserving the no-anchor `inspect_resume` fallback. This is
  implementation evidence for the frozen M6.6 set, not an extra comparator
  slot. The remaining M6.6 missing proof is no longer repair-anchor reuse
  after failure recovery; it stays broader multi-file normal-case autonomy and
  durable plan/path recall on slices that need the right paired surfaces from
  the start.
- M6.6 task #358 / session #346 then turned that broader durable-plan target
  into a fresh multi-file no-steer mew-side pass. Native mew stayed on the
  intended `src/mew/work_session.py`, `src/mew/work_loop.py`, and
  `tests/test_work_session.py` surfaces from the start, recovered the exact
  windows needed for all three files, noticed the same-file write-batch
  constraint and returned `wait` once instead of emitting an unsafe partial
  batch, then proposed and auto-applied a paired `edit_file_hunks` +
  `edit_file` src/test batch. It passed `uv run python -m unittest
  tests.test_work_session`, preserved a concise `remember` replan when the
  step budget exhausted, completed the required same-surface audit on the two
  touched `src/mew` surfaces, and finished with `rescue_edits=0`. The landed
  patch now makes `build_work_session_resume()` emit
  `plan_item_observations`, extends the paired resume/context assertions in
  `tests/test_work_session.py`, and teaches `build_work_think_prompt()` to
  prefer `work_session.resume.plan_item_observations` before broader
  rediscovery while pruning completed `working_memory.plan_items`. Count this
  as fresh implementation evidence for the frozen M6.6 set, not an extra
  comparator slot. The remaining M6.6 missing proof is now narrower: broader
  multi-file normal-case autonomy still shows adjacent same-file reread creep
  before first edit under medium/high context pressure, even when the correct
  paired surfaces are chosen from the start.
- M6.6 task #359 / session #347 then targeted that narrower first-edit
  efficiency gap directly: make the first `plan_item_observations` entry carry
  multi-path `cached_windows`, emit `edit_ready` only when every paired target
  path is cached and untruncated, and demote same-path adjacent reread signals
  once the batch is edit-ready. The native loop recovered the correct
  source/test repair anchors after one old-text mismatch, but it exhausted the
  remaining step budget on `remember` before it reached a fresh dry-run edit
  batch. The landed direct patch now makes
  `build_work_session_resume()` attach `cached_windows` and `edit_ready` to
  the first `plan_item_observations` entry, moves same-path
  `adjacent_read_observations` into a demoted bucket when that batch is ready,
  and teaches `build_work_think_prompt()` to prefer one paired dry-run edit
  over another same-path reread when `edit_ready` is true. Focused targeted
  pytest, module-level `uv run python -m unittest tests.test_work_session`,
  `ruff`, `py_compile`, and `git diff --check` passed. This is product
  progress aimed at the remaining first-edit-efficiency blocker, not fresh
  no-rescue mew-side evidence.
- M6.6 task #360 / session #348 then used that new `edit_ready` surface on a
  fresh `format_work_session_resume()` audit slice. Native mew reached
  `edit_ready=true` with paired cached source/test windows, but it still spent
  more turns on source rediscovery and never produced the reviewable paired
  dry-run edit batch. Inspecting the product surface showed the missing link:
  the human-facing formatter text still did not render
  `plan_item_observations`, `target_path_cached_window_observations`, or
  `demoted_adjacent_read_observations`, so the edit-ready audit signal was not
  visible in the rendered resume body. The direct blocker-reduction patch now
  makes `format_work_session_resume()` print those sections with exact cached
  window lines, `edit_ready` state, and demoted reread hints, and the focused
  formatter/prompt regression tests passed with `ruff`, `py_compile`, and
  `git diff --check`. This is product progress for the same first-edit
  efficiency blocker, not fresh no-rescue evidence.
- M6.6 task #361 / session #349 then retried the same first-edit-efficiency
  slice after that rendered-resume patch. Native mew stayed on the correct
  `src/mew/work_session.py` and `tests/test_work_session.py` surfaces from the
  start and reached `edit_ready=true`, but it still issued another chain of
  adjacent test-file rereads instead of proposing the paired dry-run edit
  batch. That narrowed the blocker again: the cached-window recall path was
  still exposing only the latest narrow same-path `read_file` window instead
  of the already available merged adjacent span. The direct blocker-reduction
  patch now propagates `context_truncated` through
  `build_adjacent_read_observations()`, reuses that merged same-path span when
  populating `cached_window_by_path`, and therefore widens
  `target_path_cached_window_observations`, `plan_item_observations.cached_window`,
  and `cached_windows` from the shared source of truth. Focused targeted
  pytest, module-level `uv run python -m unittest tests.test_work_session`,
  `ruff`, `py_compile`, and `git diff --check` passed. This is product
  progress for the same first-edit-efficiency blocker, not fresh no-rescue
  evidence.
- M6.6 task #362 / session #350 then retried the fresh proof on top of
  `a74ee69`, but it failed immediately for a different reason: the model tried
  to `read_file` a `.mew/memory/private/...` decision file surfaced through
  active memory and hit the tool's sensitive-path guard before it ever touched
  the src/test slice. That is not the milestone blocker itself, but it is
  avoidable friction in the coding loop. The direct blocker-reduction patch
  now tells `build_work_think_prompt()` not to call `read_file` on
  `.mew/memory/private` paths surfaced in active memory because the relevant
  excerpt is already present in prompt context. Focused prompt tests,
  module-level `uv run python -m unittest tests.test_work_session`, `ruff`,
  `py_compile`, and `git diff --check` passed. This is prompt hygiene for the
  same M6.6 first-edit proof path, not fresh no-rescue evidence.
- M6.6 task #363 / session #351 then provided the fresh no-rescue proof that
  the first-edit-efficiency blocker is closed. Native mew did one initial
  source/test anchor search, one redundant source search that was then
  converted into the suggested narrow `read_file`, and after `edit_ready=true`
  it went straight to a paired dry-run src/test edit without another same-path
  reread before the edit batch. It applied the paired source/test change,
  passed `uv run python -m unittest tests.test_work_session`, performed the
  required same-surface audit on the adjacent `edit_ready` / cached-window /
  adjacent-read-demotion branch, and finished with the proof summary recorded
  in task #363. The concrete wording-only src/test diff from that run was not
  kept, because it merely restated the proof condition in user-visible text;
  the run itself is the evidence. This is fresh mew-side implementation
  evidence for the frozen M6.6 set.
- The frozen detached comparator batch then completed on 2026-04-21. M6.6-B
  was rerun cleanly in `/tmp/mew-m66b-codex-rerun-20260421-1223`, removing the
  earlier environment caveat, and M6.6-C passed in
  `/tmp/mew-m66c-codex-20260421-1223` with both focused and broader verifier
  passes. `docs/M6_6_CODEX_PARITY_COMPARE.md` now records side-by-side
  evidence for all three predeclared comparator slots.

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
- Record task #354 / session #342 as fresh mew-side durable path-recall
  evidence for the frozen M6.6 implementation set: cached exact `read_file`
  windows can now be paired back to `working_memory.target_paths` without
  supervisor hints, native verification passed, and same-surface audit closed.
- Record task #355 / session #343 as fresh multi-file implementation evidence
  for the frozen M6.6 set: mew carried `target_path_cached_window_observations`
  from resume into `build_work_think_prompt()` and landed the paired
  `src/mew/work_loop.py` + `tests/test_work_session.py` change with native
  verification and same-surface audit, but the run still needed one narrow
  steer to abandon the wrong test surface before the edit.
- Carry the landed #356 paired-test-path recall patch as product progress, but
  do not count it as no-rescue evidence: native mew reached a reviewable
  paired dry-run/apply attempt, but repeated test-anchor drift on
  `tests/test_work_session.py` forced supervisor takeover before the final
  passing patch was landed.
- Record task #357 / session #345 as fresh mew-side repair-anchor recovery
  evidence for the frozen M6.6 set: native mew reused
  `repair_anchor_observations` to return to the correct paired source/test
  surfaces, landed the `work --follow-status` recovery patch, passed both
  `tests.test_work_session` and the inferred broader verifier
  `tests.test_commands`, and closed same-surface audit with `rescue_edits=0`.
- Record task #358 / session #346 as fresh multi-file durable-plan evidence
  for the frozen M6.6 set: native mew surfaced `plan_item_observations` in
  `build_work_session_resume()`, wired the matching prompt rule in
  `build_work_think_prompt()`, passed `tests.test_work_session`, and closed the
  required same-surface audit with `rescue_edits=0`.
- Carry the landed #359 `edit_ready` / multi-path cached-window patch as
  product progress, but do not count it as no-rescue evidence: native mew
  recovered the right repair anchors and left a correct reentry note, yet the
  session exhausted its step budget before it reached the fresh paired dry-run
  edit batch.
- Carry the landed #360 resume-text audit patch as product progress, but do
  not count it as no-rescue evidence: native mew proved the remaining blocker
  by reaching `edit_ready=true` and then still failing to produce a paired
  dry-run edit; the landed formatter patch now makes that audit state visible
  in the rendered resume body for the next fresh proof task.
- Carry the landed #361 merged-cached-window patch as product progress, but do
  not count it as no-rescue evidence: native mew reached the correct paired
  surfaces and `edit_ready=true`, yet still kept rereading because cached
  window recall was anchored to the last narrow same-path span instead of the
  merged adjacent span.
- Carry the landed #362 active-memory private-path guard as product progress,
  but do not count it as no-rescue evidence: the fresh proof task failed
  before touching src/test because it tried to inspect a sensitive
  `.mew/memory/private` path already represented in active memory.
- Record task #363 / session #351 as fresh mew-side first-edit-efficiency
  proof for the frozen M6.6 set: after the recent blocker-reduction patches,
  native mew reached a paired dry-run src/test edit once `edit_ready=true`,
  passed the configured unittest verifier, and closed same-surface audit
  without rescue edits.
- Keep M6.6 on the mew-side critical path. The next task should move from
  blocker reduction to milestone closure work: freeze the current M6.6
  implementation set and run the deferred Codex CLI comparator batch in
  parallel detached worktrees, or surface any remaining honest gap that still
  prevents that freeze.
- Defer the remaining/final Codex CLI comparator runs until the M6.6
  implementation set is frozen, then run them in parallel detached worktrees.
- Continue to treat read-window / prompt-truncation fixes and other
  mew-as-implementer readiness work as M6.6 first-slice sub-tasks, then
  continue with the next M6.6 coding-loop slice instead of per-slice
  comparator work.

Next action after closure:

- Keep M6.6 closed. Use it as the resident coding baseline, not as the active
  milestone.
- Reopen M6.6 only if a future native coding loop regresses on rescue-edits,
  verifier choice, reviewable approval surfaces, or path-recall/anti-churn
  behavior.
- Shift active focus to M6 close-out: collect the running enhanced Docker proof
  and write the M6 close gate if the proof passes.
- After M6 closes, start M6.7 with a reviewer-gated bounded loop rather than
  any unattended multi-hour self-hosting run.
- Keep deeper M7 signal work deferred until M6 is closed or a specific M7 task
  is explicitly chosen.

### M6.7: Supervised Self-Hosting Loop

Status: `in_progress`.

Goal:

- Let mew implement roadmap work in bounded reviewer-gated iterations before
  any attempt at unattended multi-hour autonomy.

Evidence:

- M6.6 now provides the closed coding baseline needed for supervised
  self-hosting: bootstrap passed, three comparator slots passed with
  `rescue_edits=0`, and the frozen Codex CLI comparator batch is recorded.
- `claude-ultra` session `9b90d99e-3bb5-4b65-aafd-5f5985bcd952` recommended
  a short bounded loop as the first honest shape: one roadmap item per
  iteration, proof artifact required, reviewer decision after each run, no
  chained tasks, and no auto-merge.
- The guardrails are now explicit in `ROADMAP.md`: proof-or-revert, scope
  fencing, and a drift canary before each iteration.
- `docs/M6_7_FIRST_SUPERVISED_ITERATION_2026-04-21.md` records the first
  bounded supervised iteration. Task `#364` / session `#352` used a reviewer
  scope limited to `src/mew/work_session.py` and `tests/test_work_session.py`,
  stopped on a paired dry-run diff, required explicit reviewer approval,
  passed the focused verifier
  `uv run pytest -q tests/test_work_session.py -k 'declared_write_scope' --no-testmon`,
  then passed the broader verifier
  `uv run python -m unittest tests.test_work_session`, completed same-surface
  audit, and finished with no reviewer rescue edits.
- `docs/M6_7_SECOND_SUPERVISED_ITERATION_2026-04-21.md` records the second
  bounded supervised iteration. Task `#365` / session `#353` stayed inside the
  declared `src/mew/commands.py` + `src/mew/work_session.py` +
  `tests/test_work_session.py` scope, stopped on paired dry-run diffs, then
  required both the focused verifier
  `uv run pytest -q tests/test_work_session.py -k 'finish_block' --no-testmon`
  and the paired-source verifier
  `uv run python -m unittest tests.test_commands` before finish. The landed
  `src/mew/commands.py` guard keeps the session open while pending approvals,
  non-finish-ready verification, or same-surface audit still block proof, and
  the iteration closed after a narrow same-surface commands.py audit with no
  reviewer rescue edits.
- Task `#366` / session `#354` targeted the remaining dedicated scope-fence
  gap: block `approve-all` when the pending dry-run batch contains a
  governance/policy edit such as `ROADMAP_STATUS.md`. The native run reached a
  correct bounded 3-file dry-run batch, but after the bad first regression
  shape was repaired it closed itself under high pressure instead of preserving
  a reviewable approval surface. The product patch then landed directly in
  `src/mew/work_session.py`, `src/mew/commands.py`, and
  `tests/test_work_session.py`: resume now prints
  `approve all blocked: approve-all is blocked for pending governance/policy dry-run edits ...`,
  `work --approve-all` returns an error for pending governance/policy dry-run
  edits, and the new regression proves both behaviors. Focused
  `uv run pytest -q tests/test_work_session.py -k 'approve_all or governance_edit' --no-testmon`,
  broader `uv run python -m unittest tests.test_work_session tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed in the same update
  session. This is product progress, not a no-rescue supervised-iteration
  proof.
- Task `#367` / session `#355` then targeted the next secondary-surface gap:
  reply-file / CLI approval surfaces still treated governance-blocked
  `approve-all` like the older hidden-unpaired-source case, so they could emit
  the wrong wording and the reply-file path could bypass the new governance
  block entirely. The native run found the right bounded source/test surfaces
  and refreshed the exact windows, but two codex model turns stalled in
  planning before they surfaced a reviewable dry-run diff. The product patch
  then landed directly in `src/mew/commands.py` and
  `tests/test_work_session.py`: CLI approval controls now distinguish
  hidden-unpaired-source blocks from governance blocks, reply-file guidance now
  tells the reviewer to inspect resume and approve per-tool for
  governance/policy edits, and `work --reply-file` now rejects `approve_all`
  when the pending batch contains governance/policy dry-run edits instead of
  bypassing the block. Focused
  `uv run pytest -q tests/test_work_session.py -k 'reply_file and approve_all or governance_blocks_approve_all' --no-testmon`,
  broader `uv run python -m unittest tests.test_work_session tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed in the same update
  session. This is product progress, not a no-rescue supervised-iteration
  proof.
- Task `#368` / session `#356` then targeted the last contextual reply
  secondary-surface gap in the same fence family: `build_work_reply_schema()`
  still advertised the generic `approve_all` action in
  `schema["supported_actions"]` even when hidden-unpaired-source or
  governance/policy blockers meant the reviewer should steer or approve
  per-tool instead. The native run anchored the correct
  `_work_reply_supported_actions()` / `build_work_reply_schema()` source
  surfaces and the reply-template regressions, but again spent its bounded
  steps in planning without surfacing a reviewable dry-run diff. The product
  patch then landed directly in `src/mew/commands.py` and
  `tests/test_work_session.py`: `build_work_reply_schema(session, resume=...)`
  now passes `resume` into `_work_reply_supported_actions()`, and the generic
  `approve_all` action is omitted from `schema["supported_actions"]` whenever
  `approve_all_blocked_reason` is present. The hidden-unpaired-source and
  governance reply-template regressions now assert that omission directly.
  Focused named pytest coverage, broader
  `uv run python -m unittest tests.test_work_session tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed in the same update
  session. This is product progress, not a no-rescue supervised-iteration
  proof.
- Task `#369` / session `#357` then targeted the next bounded proof slice on
  the same surface: expose machine-readable blocked `approve_all` context from
  the existing resume fields, so external reviewers do not have to infer the
  blocked reason only from `reply_template` text or the omitted
  `supported_actions` entry. The native run recovered from one transient Codex
  transport failure, then stayed inside the declared `src/mew/commands.py` +
  `tests/test_work_session.py` scope, searched exact anchors, read exact
  source/test windows, and advanced to a bounded batch decision that would
  reuse the existing blocked-context fields. The producer then died before the
  dry-run diff surfaced, so the same minimal patch landed directly in
  `src/mew/commands.py` and `tests/test_work_session.py` instead:
  `build_work_reply_schema()` now returns `approve_all_blocked_reason`,
  `blocked_approve_all_hint`, and `override_approve_all_hint`, and the hidden-
  unpaired-source plus governance blocked tests assert those schema fields
  directly against the resume state. Focused named pytest coverage, broader
  `uv run python -m unittest tests.test_work_session tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed in the same update
  session. This is product progress, not a no-rescue supervised-iteration
  proof.
- Task `#370` / session `#358` then shifted M6.7 from adjacent reply-surface
  scope-fence hardening into blocker reduction. The native loop had already
  searched exact anchors, read exact src/test windows, and reached a bounded
  batch decision for `src/mew/work_session.py` +
  `tests/test_work_session.py`, but the formatted resume still lost the
  proposed write when the producer stopped before the dry-run tool call
  finished. The minimal direct patch landed in those same two files instead:
  `format_work_action(batch)` now appends an indented `Diff preview` block for
  dry-run `write_file`, `edit_file`, and `edit_file_hunks` subtools using a
  minimal planned unified diff built from tool parameters, and a new
  batch-formatting regression proves the preview is visible before execution.
  Focused pytest on batch formatting + diff preview, broader
  `uv run python -m unittest tests.test_work_session tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed. This is blocker
  reduction plus product progress, not a no-rescue supervised-iteration proof.
- Task `#371` / session `#359` then used that hardened paired src/test review
  surface for the next fresh bounded proof attempt in the same two files. The
  native loop stayed inside scope without reviewer code rescue: it ran the
  drift canary, searched exact anchors, read exact windows, proposed a paired
  dry-run diff, and stopped on reviewer-visible approvals for
  `src/mew/work_session.py` + `tests/test_work_session.py`. The landed change
  adds truncated-batch visibility to `format_work_action(batch)`: when
  `truncated_tools > 0`, the `tools:` line now renders `(+N truncated)`, and
  the nearby batch-format regression asserts that output directly. Focused
  batch-formatting pytest, `ruff`, `py_compile`, and `git diff --check`
  passed. But the iteration still does not count as fresh no-rescue proof:
  after approval the native loop chose the correct broader verifier target
  (`uv run python -m unittest tests.test_work_session`), yet the live
  `run_tests` path timed out twice under session capture even though the same
  unittest module passed directly outside the live loop (`Ran 421 tests in
  23.681s`). Carry #371 as blocker evidence plus product progress, not as
  supervised-iteration credit.
- A direct blocker-reduction patch then targeted the root cause exposed by
  #371: `run_command_record_streaming()` in `src/mew/toolbox.py` now drains
  `stdout`/`stderr` with fixed-size `read()` chunks instead of newline-bound
  `readline()`, so commands that emit long progress streams without trailing
  newlines cannot fill the pipe and stall the live verifier path. The new
  `tests/test_toolbox.py` regression drives `200000` newline-free `stderr`
  characters through the streaming helper and asserts the command completes
  without timing out while `on_output` still receives streamed data. Focused
  `pytest`, `uv run python -m unittest tests.test_toolbox`, `ruff`,
  `py_compile`, and `git diff --check` passed. This is blocker reduction plus
  product progress; a fresh bounded M6.7 proof rerun is still required.
- A second direct blocker-reduction patch then fixed the remaining broader
  live-verifier hang exposed while rerunning task `#372`: tool subprocesses in
  `src/mew/toolbox.py` now launch with `stdin=subprocess.DEVNULL`, and the new
  `tests/test_toolbox.py` regression asserts that the streaming helper passes
  `DEVNULL` stdin into `subprocess.Popen`. This prevents verifier subprocesses
  from inheriting reviewer stdin and stalling on approval-prompt tests that
  expect EOF in non-interactive runs. Focused `pytest`, `ruff`, `py_compile`,
  and `git diff --check` passed. This is blocker reduction plus product
  progress.
- Task `#372` / session `#360` then reran the fresh bounded
  `src/mew/work_session.py` + `tests/test_work_session.py` review-surface
  slice. The native loop ran the drift canary, searched exact anchors, read
  exact src/test windows, proposed a paired dry-run diff, stopped for explicit
  reviewer approval, passed the focused verifier, then resumed to pass the
  broader verifier `uv run python -m unittest tests.test_work_session`,
  completed the required same-surface audit, and finished cleanly. The landed
  change makes single dry-run `write_file` / `edit_file` /
  `edit_file_hunks` actions surface the planned diff preview instead of only
  size counts, with direct regression coverage in
  `tests/test_work_session.py`. Count this as strong supervised-loop evidence
  plus product progress, but not yet as the clean post-fix milestone-closing
  proof because the live-verifier runtime changed mid-iteration.
- Task `#373` / session `#361` then tried to turn the now-saved M6.7 context
  checkpoint into a better coding reentry fallback for `mew focus` /
  `mew brief`: prefer `./mew context --load --limit 1` over native
  self-improve only while the user is actively waiting for agent work. The
  bounded source/test intent was sound, but the run needed multiple reviewer
  steers and eventually a direct reviewer takeover after verification noise, so
  it does not count as supervised-loop proof. The landed direct patch stays
  inside the same scope: `src/mew/brief.py` now prefers checkpoint recovery
  only when `user_status.mode == waiting_for_agent` and the latest checkpoint
  `created_at` is same-day, while `tests/test_brief.py` now covers both the
  waiting/current-checkpoint path and the stale-checkpoint fallback, and fixes
  brittle self-improve/continuity expectations so the suite is deterministic
  again. Focused `uv run pytest -q tests/test_brief.py -k "next_move or focus
  or brief" --no-testmon`, broader `uv run python -m unittest tests.test_brief`,
  `ruff`, `py_compile`, and `git diff --check` all passed. This is product
  progress, not a fresh no-rescue supervised-iteration proof.
- `docs/M6_7_SIXTH_SUPERVISED_ITERATION_2026-04-21.md` now records the fresh
  clean post-fix bounded proof that the earlier M6.7 section still lacked.
  Task `#374` / session `#362` stayed inside the declared `src/mew/brief.py`
  + `tests/test_brief.py` scope, ran the drift canary first, anchored exact
  `build_focus_data()` / `build_brief_data()` and nearby brief regressions,
  surfaced a paired dry-run diff, stopped for explicit reviewer approval,
  passed the focused verifier
  `uv run pytest -q tests/test_brief.py -k "focus or brief or active_work_session" --no-testmon`,
  then passed the broader verifier
  `uv run python -m unittest tests.test_brief`, completed a same-surface audit,
  and finished with no reviewer rescue edits. The landed change makes
  `active_work_session_items()` skip non-actionable tasks, and the new
  regression proves `mew focus --kind coding` no longer treats a stale blocked
  work session as active work that should suppress the next useful move.
- The refreshed 8-hour proof queue has now been exercised further. Task `#380`
  / sessions `#368` and `#369` soft-stopped Candidate N-A after the focused
  verifier shape was repaired: the run stayed inside
  `src/mew/proof_summary.py` + `tests/test_proof_summary.py`, but two fresh
  attempts stalled before a reviewable paired dry-run diff surfaced. Carry
  this as non-converging proof evidence, not closure credit.
- Task `#381` / session `#370` soft-stopped Candidate N-B. The initial work
  drifted toward focus-only `active_work_session_items()` edits, while the real
  target is `brief` / `next` / JSON output. Keep the stored repair guidance in
  task notes, but do not count this as M6.7 proof credit.
- Task `#382` / session `#371` closed Candidate N-C as reviewer no-change.
  Existing `active_work_session_items()` gates already filter non-actionable
  work through `session.status != active`, missing-task, `task.status == done`,
  and blocked-task checks, and the existing `tests/test_brief.py` coverage for
  stale blocked and done-task branches already pins that behavior. No product
  patch landed.
- Task `#383` / session `#372` then targeted Candidate N-E. mew anchored the
  correct `src/mew/toolbox.py` + `tests/test_toolbox.py` scope and read both
  files, but the edit-planning model turns stalled twice. The direct supervisor
  patch then landed additive structured timeout diagnostics in
  `src/mew/toolbox.py` (`kill_status`, `stdout_tail`, `stderr_tail`,
  `timeout_seconds`) plus a focused timeout regression in
  `tests/test_toolbox.py`. Focused
  `uv run pytest -q tests/test_toolbox.py -k 'timeout or streaming_kill' --no-testmon`,
  broader `uv run python -m unittest tests.test_toolbox`, `ruff`,
  `py_compile`, and `git diff --check` all passed. This is product progress,
  not supervised-proof credit.
- Task `#384` / session `#373` then targeted Candidate N-H. mew anchored the
  correct `src/mew/mood.py` + `tests/test_mood.py` scope and read the exact
  formatter/test windows, but repeated live retries stalled in edit planning
  before a reviewable paired dry-run diff surfaced. The direct supervisor patch
  then landed the bounded text-surface gap: `format_mood_view()` in
  `src/mew/mood.py` now appends a `signals:` section that renders
  `view_model["signals"]` or an explicit no-signals line, and
  `tests/test_mood.py` now asserts the plain-text formatter carries the same
  signal content as the existing markdown/JSON surface. Focused
  `uv run pytest -q tests/test_mood.py -k 'mood_command or format_mood or signals' --no-testmon`,
  broader `uv run python -m unittest tests.test_mood`, `ruff`, `py_compile`,
  and `git diff --check` all passed. This is product progress, not
  supervised-proof credit.
- A direct M6.7 substrate patch then addressed the newly explicit soft-stop
  blocker itself: `--compact-live` now forces the live THINK prompt to use
  `compact_memory` context even for high-risk tasks, instead of only compacting
  CLI rendering while the model still received a full prompt. The fix landed in
  `src/mew/work_loop.py` and `src/mew/commands.py`, and
  `tests/test_work_session.py` now proves both that
  `work_prompt_context_mode(..., compact_live=True)` returns
  `compact_memory` and that a high-risk `work --ai --compact-live` turn records
  `prompt_context_mode=compact_memory` in model metrics. Focused named pytest,
  broader `uv run python -m unittest tests.test_work_session`, `ruff`,
  `py_compile`, and `git diff --check` all passed. Treat this as blocker
  reduction plus product progress; the next honest step is a fresh proof rerun,
  not another direct candidate patch.
- Task `#385` / session `#374` then reopened Candidate N-F after the
  compact-live substrate fix. mew surfaced the intended `src/mew/sweep.py` +
  `tests/test_sweep.py` JSON-report patch, but the broader verifier
  `uv run python -m unittest tests.test_commands` exposed a real product
  blocker: `cmd_agent_sweep()` used `args.json` while the `agent sweep` CLI
  parser did not define `--json`. The live rerun stayed bounded and re-anchored
  the exact `src/mew/cli.py`, `src/mew/commands.py`, and
  `tests/test_commands.py` windows, but still stopped before a new
  reviewer-visible dry-run diff surfaced. The direct supervisor blocker fix
  then landed: `src/mew/cli.py` now defines `agent sweep --json`,
  `src/mew/commands.py` uses `getattr(args, "json", False)` defensively, and
  `tests/test_commands.py` covers the JSON path while preserving timeout
  passthrough. Focused
  `uv run pytest -q tests/test_sweep.py tests/test_commands.py -k 'agent_sweep or sweep_report_json' --no-testmon`,
  broader `uv run python -m unittest tests.test_sweep tests.test_commands`,
  `ruff`, `py_compile`, and `git diff --check` all passed. Treat this as
  blocker reduction plus product progress, not M6.7 supervised-proof credit.
- Task `#386` / session `#375` then converted Candidate N-G into real
  supervised-proof evidence. mew stayed within
  `src/mew/commands.py` + `tests/test_journal.py`, surfaced reviewer-visible
  dry-run diffs, applied the approved changes, repaired two stale exact test
  expectations through same-surface repair turns without supervisor code
  edits, reran the targeted journal pytest, passed broader
  `uv run python -m unittest tests.test_journal`, then selected and passed the
  paired commands verifier `uv run python -m unittest tests.test_commands`
  before closing with same-surface audit reasoning. Focused
  `uv run pytest -q tests/test_journal.py -k 'journal_command or json' --no-testmon`,
  broader journal/commands unittests, `ruff`, and `py_compile` all passed.
  Count this as M6.7 supervised-proof credit.
- Task `#387` / session `#376` then converted Candidate N-I into additional
  supervised-proof evidence. mew stayed within
  `src/mew/signals.py` + `tests/test_signals.py`, surfaced reviewer-visible
  dry-run diffs, applied the approved source/test edits, passed focused
  `uv run pytest -q tests/test_signals.py -k 'cli or journal or reason_for_use' --no-testmon`,
  passed broader `uv run python -m unittest tests.test_signals`, and closed
  with same-surface audit reasoning that only `format_signal_journal()` text
  output changed while JSON behavior remained unchanged. `ruff`,
  `py_compile`, and `git diff --check` all passed. Count this as M6.7
  supervised-proof credit.
- Task `#389` / session `#380` then converted Candidate N-J into additional
  supervised-proof evidence after the narrow write-ready blocker fix set
  landed in `src/mew/work_loop.py` and `tests/test_work_session.py`. mew first
  exposed exact blockers instead of timing out: cached src tail missing,
  missing model-turn schema, then same-file-hunk batch shaping. After the
  write-ready fast-path prompt, exact cached text injection, path
  normalization, same-file-hunk guidance, and write-ready timeout uplift
  landed, mew stayed within `src/mew/commands.py` +
  `tests/test_work_session.py`, surfaced reviewer-visible paired dry-run
  diffs with `edit_file_hunks`, applied the approved source/test edits with no
  supervisor code rescue on the task itself, passed `uv run python -m unittest
  tests.test_commands` on apply, passed focused `uv run python -m unittest
  tests.test_work_session.WorkSessionTests.test_work_follow_status_marks_planning_producer_overdue_after_model_timeout`,
  completed a same-surface audit on `src/mew/commands.py`, and finished with a
  summary tied to the new `latest_model_failure` JSON field. Focused pytest
  for the touched substrate tests, broader `unittest` on
  `tests.test_commands` plus the edited follow-status case, `ruff`,
  `py_compile`, and `git diff --check` all passed. Count this as M6.7
  supervised-proof credit.

Missing proof:

- The current supervised run now has three real roadmap items (`N-G`, `N-I`,
  `N-J`), but the 8-hour wall-clock proof window has not completed yet.
- Any 24h unattended run is still disallowed until the supervised 8-hour proof
  is recorded.
- If any supervised 8-hour proof item fails or soft-stops, M6.7 must classify
  it as proof-or-revert failure, product-only progress, or substrate evidence,
  then fix the exposed blocker before consuming more bounded proof items.
- Task `#388` is now explicitly marked as a paused debug target via the
  existing work-session stop request, with `brief`, `focus`, and `desk`
  updated to surface that paused state honestly instead of recommending it as
  the default next move. Treat it as a stored fallback/debug target, not as
  the next proof item to grind.

Done when:

- mew can run one bounded roadmap iteration end to end, stop for review, and
  attach a usable proof artifact without hidden reviewer rescue edits
- proof-or-revert is enforced when proof is missing or failing
- scope fence blocks out-of-scope edits and self-authored roadmap/milestone
  closure changes without human approval
- a supervised 8-hour run completes at least three real roadmap items end to
  end with reviewer decisions recorded on each iteration, zero
  proof-or-revert failures, and a green drift canary throughout

Next action:

- Stop treating direct supervisor fixes as progress toward the 8-hour proof
  when the same unresolved blocker is still open. If one proof item fails or
  soft-stops, return to the exposed blocker, land the substrate fix, verify
  it, and only then go back to the supervised proof queue.
- Once the blocker fix is verified, rerun a fresh bounded proof item from the
  remaining live queue (`N-F`, `N-G`, `N-I`, then `N-D`) instead of consuming
  more candidates under the same unresolved blocker.
- Do not spend more proof items right now. Keep the current supervised run
  alive, record `N-J` with the blocker-fix chain that enabled it, and wait for
  the 8-hour wall-clock criterion before deciding whether another bounded item
  is actually required.
- Preserve the new operator/debug stance: `#388` stays paused unless a real
  invalidation forces resume, and `brief` / `focus` / `desk` should keep
  reflecting that paused state during the wall-clock wait.
- Plan and run the supervised 8-hour M6.7 proof only on bounded items that are
  still live product gaps and can plausibly produce reviewer-gated dry-run
  diffs.
- Keep the per-iteration drift canary, proof-or-revert discipline, and
  reviewer-gated dry-run approvals intact throughout the run.
- Keep roadmap-status and milestone-close edits under reviewer control.

### M6.8: Task Chaining - Supervised Self-Selection

Status: `not_started`.

Goal:

- remove the per-iteration human-dispatch latency from the M6.7 loop while
  preserving reviewer gating and the scope fence

Entry gate:

- M6.7 must be closed, including its supervised 8-hour proof
- reviewer approval must be logged before the first chained run begins

Missing proof:

- no chained supervised run exists yet
- selector governance, rejection recovery, and chained drift-canary behavior
  have not been exercised

Next action:

- finish M6.7 first; do not start M6.8 implementation while the M6.7 close
  gate is still open

### M6.9: Durable Coding Intelligence

Status: `not_started`.

Goal:

- turn persistent state into a coding advantage so repeated work in the same
  repository becomes measurably smarter over time

Entry gate:

- M6.7 must be closed
- the delta/spec work derived from
  `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` must be approved
  before any `src/mew` implementation lands
- M6.9 Phase 4 stays gated on M6.8

Missing proof:

- no M6.9 implementation or comparator rerun exists yet
- no durable-coding-memory types are registered in product behavior yet

Next action:

- keep this as the next coding-track dream-goal, but defer all implementation
  until M6.7 closes and the Phase 1-3 delta plan is reviewer-approved

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

Active focus: **M6.7 Supervised Self-Hosting Loop**.

The next long session should not drift into broad polish, open-ended
infrastructure, or unattended autonomy. The acceptable near-term work is:

- planning and running the supervised 8-hour M6.7 proof with bounded roadmap
  items and recorded reviewer decisions;
- roadmap registration and status maintenance for M6.8 / M6.9 only when it
  clarifies post-M6.7 ordering without changing the active milestone;
- keeping M6.6 as a closed regression baseline for resident coding work;
- keeping M6 milestone close and proof harness fixes as closed baseline work;
- reviewer-owned roadmap/status updates and checkpointing around M6.7 runs;
- roadmap/status maintenance that preserves the active decision across context
  compression.

Keep M5.1, M6, and M6.6 as closed baselines while M6.7 proves supervised
self-hosting before deeper M7 signal work or any unattended self-hosting.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Archive detailed milestone evidence at each milestone close.
- Keep `ROADMAP_STATUS.md` around 200-300 lines.
- Put long dogfood narratives in `docs/` or `docs/archive/`.
- If a long-session decision changes, update the Active Milestone Decision
  immediately and save a mew context checkpoint.
