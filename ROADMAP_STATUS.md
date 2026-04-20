# Mew Roadmap Status

Last updated: 2026-04-20

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
| 6.5. Self-Hosting Speed | `foundation` | New gate: make mew fast enough to implement small mew changes inside mew before resuming feature expansion. |
| 7. Senses: Inbound Signals | `foundation` | Signal source gates and journaling have started, but further source work is paused until M6.5 removes the self-hosting speed blocker. |
| 8. Identity: Cross-Project Self | `not_started` | Add user-scope identity and memory across projects while preserving project boundaries. |
| 9. Legibility: Human-Readable Companion | `not_started` | Make mew's state understandable to humans without raw internal structures. |
| 10. Multi-Agent Residence | `not_started` | Let multiple model families inhabit the same mew with durable notes, review, and disagreement artifacts. |
| 11. Inner Life | `not_started` | Promote journal, dream, mood, and self-memory into a curated, auditable continuity of self. |

## Active Milestone Decision

Last assessed: 2026-04-20 20:11 JST.

Active work: **M6.5 Self-Hosting Speed** while the M6 enhanced proof runs in
parallel.

Reasoning:

- M1-M5 are closed. M5 closure was explicitly approved by the user on
  2026-04-20 after M3 and M4 were already closed.
- M5.1 closed as a bounded patch that makes future self-improvement safer
  without retroactively changing the M5 done gate.
- M6 core daemon work exists and the enhanced multi-hour Docker proof is
  running detached. Waiting for that proof should not block useful local work.
- M7 signal registry foundation exists, but feature expansion exposed a more
  important blocker: mew is still too slow to act as its own implementer.
- The #320-class self-hosting attempt produced no reviewable edit proposal:
  xhigh had roughly 132s first THINK latency, high then stalled beyond three
  minutes, and the repaired model turns recorded interruption without edits.
- `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` identifies the structural
  cause: durable memory is currently used as prompt bulk instead of a fast
  pointer/index.
- `claude-ultra` was consulted in session
  `f220b253-51d5-435e-ab24-520190e3f97e` and recommended prompt caching,
  reasoning-effort auto-adjustment, and differential context before deeper M7
  feature work. Codex agrees.
- Broad polish and general refactor remain non-goals. M6.5 work must be
  measured against self-hosting latency and edit-proposal outcomes.

Current next action:

1. Use this dashboard as the active decision after context compression.
2. Let the enhanced M6 Docker proof finish, collect it, and run
   `./mew proof-summary proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910 --strict`.
3. Rerun a #320-class self-hosting task and compare first useful output,
   selected reasoning effort, prompt/context size, and edit-proposal latency
   against the failed attempt.
4. If the rerun still stalls, reduce context further before adding new M7
   features.
5. If the M6 proof passes while M6.5 is in progress, write the M6 close gate
   without dropping the M6.5 active focus.
6. Keep M5.1 as a closed safety baseline. Do not reopen it unless a future
   self-improvement loop violates the documented safety hooks.

Human-role transition rule:

- M5.1 dogfooded the first small slice with **mew as implementer** and Codex
  acting as the human reviewer/approver. The rescue was recorded honestly, so
  it did not count as autonomy credit.
- Treat rescue edits by Codex as a signal that mew is not ready to own that
  class of task yet. Record the blocker instead of silently fixing around it.
- Low- and medium-risk implementation should move toward mew as primary
  implementer only after M6.5 produces a reviewable edit proposal without
  rescue edits.
- Until then, Codex may implement the M6.5 infrastructure directly, but every
  change should be aimed at making the next mew-as-implementer dogfood attempt
  faster and more legible.

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

Status: `foundation`.

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
- Validation: `tests/test_work_session.py`, `tests/test_metrics.py`,
  `tests/test_reasoning_policy.py`,
  `tests/test_commands.py::CommandTests::test_metrics_command_prints_observation_metrics`,
  targeted `ruff`, `uv run python -m py_compile`, and `git diff --check` passed.

Missing proof:

- No post-instrumentation real Codex work session has populated the new
  `self_hosting` metrics yet.
- The #320-class task has not yet been rerun successfully after speed changes.

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

- Rerun a #320-class self-hosting task and compare first useful output,
  edit-proposal latency, and the new `self_hosting` prompt-size breakdown
  against the failed attempt.

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
- Validation: `uv run pytest -q tests/test_signals.py --no-testmon`,
  targeted `ruff`, `./mew help signals record`, and `git diff --check` passed.

Missing proof:

- No real non-file-system source fetcher exists yet. RSS/calendar/mail/etc. can
  now plug into the registry, but one source still needs an actual collector.
- No real-day unsolicited observation has been collected from signal evidence.
- Further M7 collector work is paused until M6.5 makes self-hosting fast enough
  to produce reviewable edit proposals.

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

Active focus: **M6.5 Self-Hosting Speed**.

The next long session should not drift into broad polish or general refactor.
The acceptable near-term work is:

- collecting the running M6 enhanced Docker proof when it finishes;
- self-hosting speed metrics for native work sessions;
- rerunning a #320-class mew-as-implementer dogfood task and comparing latency
  to the failed attempt;
- roadmap/status maintenance that preserves the active decision across context
  compression.

Keep M5.1 as the closed safety baseline and M6 as proof-pending while M6.5
removes the self-hosting speed blocker.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Archive detailed milestone evidence at each milestone close.
- Keep `ROADMAP_STATUS.md` around 200-300 lines.
- Put long dogfood narratives in `docs/` or `docs/archive/`.
- If a long-session decision changes, update the Active Milestone Decision
  immediately and save a mew context checkpoint.
