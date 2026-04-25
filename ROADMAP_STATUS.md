# Mew Roadmap Status

Last updated: 2026-04-26

This file is the compact operational roadmap dashboard. It is intentionally
short enough to survive context compression and long-session reentry.

Detailed historical evidence through the current compression point is archived
losslessly in:

- `docs/archive/ROADMAP_STATUS_through_M5_2026-04-20.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Status vocabulary:

- `not_started`: no meaningful implementation yet
- `foundation`: supporting pieces exist, but the milestone's core user value is
  not usable
- `in_progress`: core implementation exists or is the active focus
- `pending`: meaningful implementation exists, but the milestone is
  intentionally paused by a higher-priority active milestone
- `done`: the recorded close gate passed
- `merged_into_*`: historical milestone folded into another milestone

Important interpretation: `done` means the recorded close gate passed. It does
not mean every idea in every design note has shipped. Deferred post-close work
is tracked below.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| 1. Native Hands | `done` | Native work sessions can inspect, edit, verify, resume, and expose audit trails. |
| 2. Interactive Parity | `done` | Cockpit/live/follow controls, approvals, compact output, interruption handling, and comparator evidence reached the gate. |
| 3. Persistent Advantage | `done` | Reentry/comparator evidence plus long-gap proof shapes closed the gate. |
| 4. True Recovery | `done` | Runtime/work-session effects can be classified and safely retried/requeued or surfaced for review. |
| 5. Self-Improving Mew | `done` | Five consecutive no-rescue self-improvement loops passed with review and verification. |
| 5.1 Trust & Safety Close-Out | `done` | Post-M5 hardening added adversarial review and safety hooks without changing the M5 gate. |
| 6. Body: Daemon & Persistent Presence | `done` | 4-hour daemon proof passed strict summary; retained-artifact false-negative caveat is archived. |
| 6.5 Self-Hosting Speed | `done` | Compact resident rerun produced a verified paired edit proposal with first THINK under 10s. |
| 6.6 Coding Competence: Codex CLI Parity | `done` | Bootstrap, comparator slots, and frozen Codex CLI side-by-side batch passed with recorded caveats. |
| 6.7 Supervised Self-Hosting Loop | `done` | Reviewer-gated supervised iterations, reentry, and detached close-watch satisfied the gate. |
| 6.8 Task Chaining: Supervised Self-Selection | `in_progress` | Active. Build safe reviewer-approved chained task selection. |
| 6.8.5 Selector Intelligence and Curriculum Integration | `not_started` | Planned immediately after M6.8 core; formal home for M6.9 Phase 4. |
| 6.9 Durable Coding Intelligence | `done` | Close gate passed via `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`; Phase 4 moved to M6.8.5. |
| 6.10 Execution Accelerators and Mew-First Reliability | `done` | Latest 10 attempts reached 7/10 clean-or-practical with classified failures. |
| 6.11 Loop Stabilization | `done` | Core and residual hardening are closed; use its surfaces as diagnostics only. |
| 6.12 Failure-Science Instrumentation | `done` | V0 read-only ledger/classifier/report surface is closed. |
| 6.13 High-Effort Deliberation Lane | `not_started` | Deferred until M6.8.5 or direct hard-blocker evidence shows it would shorten work. |
| 6.14 Mew-First Failure Repair Gate | `done` | Repair ledger covers known mew-first substrate failures; future repairs append here. |
| 6.15 Verified Closeout Redraft Repair | `merged_into_6.14` | Historical episode folded into M6.14. |
| 7. Senses: Inbound Signals | `foundation` | Signal gates/journaling/RSS pieces exist; deeper work deferred. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.8 Task Chaining: Supervised Self-Selection**.

Why M6.8 is active:

- M6.9 is closed, but its Phase 4 curriculum/habit/preference work depends on
  task chaining and is now scheduled as M6.8.5.
- The current resident capability gap is task selection: mew still needs the
  human/Codex supervisor to choose each next bounded roadmap task.
- The next step toward a resident execution shell is not more memory or more
  polish. It is safe chained task proposal under reviewer approval.

Current M6.8 target:

- mew proposes the next bounded roadmap task at iteration close
- reviewer approval is required before execution
- the proposal records `previous_task_id` and `selector_reason`
- the proposal reserves optional future fields for M6.8.5:
  `memory_signal_refs`, `failure_cluster_reason`, and `preference_signal_refs`
- selector-owned output cannot touch roadmap-status, milestone-close, or
  governance files
- drift canary and proof-or-revert discipline remain active across the chain

Current M6.8 evidence:

- Task `#628` / session `#612` landed the first mew-first selector-contract
  slice: `build_task_selector_proposal()` in `src/mew/tasks.py` produces a
  reviewer-gated proposal with `previous_task_id`, proposed task identity,
  `selector_reason`, `approval_required=true`, optional M6.8.5 signal refs, and
  governance/status blocking fields.
- The first #628 patch was correctly rejected as a shallow
  `task_kind_report` passthrough. After reviewer steering, mew retried the same
  task and produced the accepted helper/test patch without supervisor product
  rescue.
- Validation passed: `uv run pytest -q tests/test_tasks.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/tasks.py tests/test_tasks.py`, and
  `git diff --check`.

M6.8 is done when:

- mew completes three consecutive bounded iterations in one supervised session
  where mew chose each next task, reviewer approval was recorded per iteration,
  and rescue edits stayed at zero
- at least one reviewer rejection happens during the chained proof run, and the
  next approved task continues the chain without manual reset
- selector scope fence holds across the proof run
- drift canary stays green across the full chained run
- attempting chained execution without reviewer approval is rejected and logged
  as a governance violation

## Next Milestone

Next scheduled milestone after M6.8: **M6.8.5 Selector Intelligence and
Curriculum Integration**.

M6.8.5 absorbs M6.9 Phase 4. Do not reopen M6.9 just to implement these:

- failure-clustered curriculum
- preference-store retrieval from reviewer diffs
- habit compilation v0
- read-only M6.12/M6.14 selector evidence
- selector traces that explain why a task was chosen

M6.8.5 should not start until M6.8 core proves the safe chained approval loop.

## Post-Close Deferred Ledger

| Origin | Deferred Item | Trigger / Timing | Recommended Home | Blocks Current? |
|---|---|---|---|---|
| M6.9 Phase 4 | Failure-clustered curriculum | After M6.8 core selector can propose, approve, reject, and continue a chain | M6.8.5 Phase 1 | Not M6.8 core; yes for intelligent chaining |
| M6.9 Phase 4 | Preference-store retrieval from reviewer diffs | After selector traces can carry `preference_signal_refs` and draft preparation has a bounded injection point | M6.8.5 Phase 2 | No |
| M6.9 Phase 4 | Habit compilation v0 | After repeated task-template evidence identifies stable candidates with low variance | M6.8.5 Phase 3 | No |
| M6.10 | Explorer D1 / read-only exploration reducer | Only if M6.8 or M6.8.5 evidence shows read-only exploration churn is a measured blocker again | M6.10 follow-up or M6.8.5 helper slice | No |
| M6.11 | Full concurrent / streaming executor | After selector/curriculum proof shows measured idle or concurrency pain while loop attribution is stable | Later execution milestone | No |
| M6.11 | MemoryExplore protocol full freeze/replay and agentization | Keep read-only provider for now; full agentization waits until a second planner will not obscure loop failures | M10 or later memory/explorer milestone | No |
| M6.11 | Provider-specific prompt caching | Only when provider telemetry shows cache/latency as a direct blocker | M6.13 or later acceleration slice | No |
| M6.12 | Governance/evaluator/adversarial wiring | First use M6.12 as read-only selector input in M6.8.5; automatic governance wiring needs a later explicit safety milestone | M6.8.5 read-only, later governance milestone | No |

## Mew-First Operating Rule

From M6.9 onward, bounded roadmap/coding implementation belongs to mew first.
Codex acts as reviewer/supervisor.

Allowed direct Codex work:

- roadmap/status/audit bookkeeping
- governance, permission, safety, and skill-policy changes
- loop-substrate repairs after a classified mew-first failure

Not allowed as autonomy credit:

- supervisor-authored product rescue disguised as mew-owned implementation
- milestone-close or roadmap-status changes authored by selector output
- unattended auto-merge

If a mew-owned task fails structurally:

1. classify the failure
2. pause the active product milestone
3. append or activate a bounded M6.14 repair episode
4. fix the substrate or task spec
5. retry the same task

## Closed Baseline Caveats

These caveats are preserved; they do not reopen the milestones by default.

- M6 daemon: original retained-artifact report had a false-negative shape, but
  strict summary proof passed and the caveat is archived.
- M6.6: comparator proof contains environment/caveat notes, but the gate is
  closed.
- M6.9: some wall-time and comparator evidence is deterministic fixture
  evidence rather than fresh external CLI reruns; the close audit records this.
- M6.10: Explorer D1 is deferred because the reliability gate passed without
  it.
- M6.11: residual hardening includes mixed autonomy outcomes; acceptable
  because the residual gate was loop-substrate hardening.
- M6.12: closeout export tree and governance wiring are deferred by design.

## Reopen Rules

- Reopen M6.6 only if a future native coding loop regresses on rescue edits,
  first-edit efficiency, or comparator parity.
- Reopen M6.8 only if chained task selection violates approval, scope fence, or
  drift-canary discipline after close.
- Reopen M6.9 only if M6.8/M6.8.5 selector proof exposes a real
  durable-memory regression against `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`.
- Reopen M6.11 only if a fresh loop regression cannot be classified or repaired
  using the closed residual surfaces.
- Reopen M6.12 only if the read-only report stops parsing the canonical ledger
  or gives incorrect missing-bundle/citation results.
- M6.14 remains the default home for future mew-first substrate repair
  episodes.

## Current Roadmap Focus

The next implementation task should map to this chain:

`M6.8 -> supervised selector contract -> bounded task proposal with reviewer approval`

Acceptable near-term work:

- create the first M6.8 bounded task for selector proposal output
- implement the smallest safe selector proposal surface
- preserve optional signal refs for M6.8.5, but do not implement
  curriculum/habit/preference selector policy in M6.8 core
- add tests that reject selector-owned roadmap-status, milestone-close, or
  governance edits
- prove reviewer approval is required before chained execution

Non-goals for the next session:

- M6.8.5 curriculum/habit/preference policy before M6.8 core closes
- M6.13 deliberation lane
- full concurrent executor
- memory explore agentization
- provider-specific prompt caching
- M7 inbound-signal work
- broad refactors or polish not mapped to the M6.8 gate

## Latest Validation

Current change is docs/status only.

Observed in this cleanup session:

- `git diff --check` passed
- detailed pre-compression `ROADMAP_STATUS.md` was archived to
  `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Behavioral validation was not rerun because no source/test code changed.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action
  here.
- When a milestone closes, add or update a close-gate audit in `docs/` and
  summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions
  override the active milestone decision in this file.
