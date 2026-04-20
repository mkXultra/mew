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
| 6. Body: Daemon & Persistent Presence | `in_progress` | Make mew a resident process rather than a CLI that exists only when summoned. |
| 7. Senses: Inbound Signals | `not_started` | Let the resident notice audited external signals, not only its own state. |
| 8. Identity: Cross-Project Self | `not_started` | Add user-scope identity and memory across projects while preserving project boundaries. |
| 9. Legibility: Human-Readable Companion | `not_started` | Make mew's state understandable to humans without raw internal structures. |
| 10. Multi-Agent Residence | `not_started` | Let multiple model families inhabit the same mew with durable notes, review, and disagreement artifacts. |
| 11. Inner Life | `not_started` | Promote journal, dream, mood, and self-memory into a curated, auditable continuity of self. |

## Active Milestone Decision

Last assessed: 2026-04-20 18:49 JST.

Active work: **M6 Body**.

Reasoning:

- M1-M5 are closed. M5 closure was explicitly approved by the user on
  2026-04-20 after M3 and M4 were already closed.
- M5.1 closed as a bounded patch that makes future self-improvement safer
  without retroactively changing the M5 done gate.
- `claude-ultra` was consulted in session
  `831f34ca-4610-4c9b-9d10-b99f467d5f5f` and argued that the next real
  inhabitation milestone should be a persistent body: daemon, restart, and
  passive event handling. Codex agrees.
- Broad refactor work is not a milestone. Refactor only where it directly
  enables M6 daemon work or a directly observed blocker.

Current next action:

1. Use this dashboard as the active decision after context compression.
2. Start M6 Body in small slices: daemon status, resident tick supervision,
   durable pause/inspect/repair/resume controls, and one real watcher-triggered
   passive turn.
3. Keep M5.1 as a closed safety baseline. Do not reopen it unless a future
   self-improvement loop violates the documented safety hooks.

Human-role transition rule:

- M5.1 dogfooded the first small slice with **mew as implementer** and Codex
  acting as the human reviewer/approver. The rescue was recorded honestly, so
  it did not count as autonomy credit.
- Treat rescue edits by Codex as a signal that mew is not ready to own that
  class of task yet. Record the blocker instead of silently fixing around it.
- Low- and medium-risk implementation should now default to mew as primary
  implementer. Codex should increasingly act as requester, reviewer, approver,
  and product judge.
- Keep Codex as direct implementer for daemon, safety-hook, permission,
  recovery, roadmap/evaluator, and other high-risk architecture until M6 Body
  proves durable resident operation.

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

Missing proof:

- No long-duration daemon proof has shown the watcher and passive loop staying
  healthy beyond the short dogfood scenario.
- No daemon restart proof has shown reattachment without user rebrief.
- No multi-hour resident proof has run through the daemon path.
- Pause/inspect/repair/resume controls still reuse existing commands rather
  than a daemon-specific cockpit.

Done when:

- `mew daemon status` reports uptime and active watchers.
- A real file or git event triggers a passive turn end to end without manual
  polling.
- A restart after terminal close, process stop, or reboot reattaches without
  user rebrief.
- The daemon can be paused, inspected, repaired, and resumed from CLI/chat.

### M7: Senses - Inbound Signals

Status: `not_started`.

Goal:

- Give the resident audited read-only signals from the user's working world.

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

Active focus: **M6 Body**.

The next long session should not drift into broad polish or general refactor.
The acceptable near-term work is:

- daemon status and resident lifecycle controls;
- a supervised passive tick loop that survives ordinary CLI session boundaries;
- one real file or git watcher-triggered passive turn;
- pause, inspect, repair, and resume controls for the resident;
- roadmap/status maintenance that preserves the active decision across context
  compression.

Keep M5.1 as the closed safety baseline while M6 work begins.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Archive detailed milestone evidence at each milestone close.
- Keep `ROADMAP_STATUS.md` around 200-300 lines.
- Put long dogfood narratives in `docs/` or `docs/archive/`.
- If a long-session decision changes, update the Active Milestone Decision
  immediately and save a mew context checkpoint.
