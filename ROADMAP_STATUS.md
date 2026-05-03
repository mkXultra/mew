# Mew Roadmap Status

Last updated: 2026-05-03

This file is the compact operational roadmap dashboard for context reentry.
Detailed history is intentionally archived instead of kept here.

Detailed archives:

- `docs/archive/ROADMAP_STATUS_through_M5_2026-04-20.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-05-03.md`

Status vocabulary:

- `not_started`: no meaningful implementation yet
- `foundation`: supporting pieces exist, but the milestone's core user value is
  not usable
- `in_progress`: core implementation exists or is the active focus
- `pending`: meaningful implementation exists, but the milestone is paused by a
  higher-priority active milestone
- `done`: the recorded close gate passed
- `merged_into_*`: historical milestone folded into another milestone

Important interpretation: `done` means the recorded close gate passed. It does
not mean every idea in every design note has shipped.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| 1. Native Hands | `done` | Native work sessions can inspect, edit, verify, resume, and expose audit trails. |
| 2. Interactive Parity | `done` | Cockpit/live/follow controls, approvals, compact output, interruption handling, and comparator evidence reached the gate. |
| 3. Persistent Advantage | `done` | Reentry/comparator evidence plus long-gap proof shapes closed the gate. |
| 4. True Recovery | `done` | Runtime/work-session effects can be classified and safely retried/requeued or surfaced for review. |
| 5. Self-Improving Mew | `done` | Five consecutive no-rescue self-improvement loops passed with review and verification. |
| 5.1 Trust & Safety Close-Out | `done` | Post-M5 hardening added adversarial review and safety hooks. |
| 6. Body: Daemon & Persistent Presence | `done` | 4-hour daemon proof passed strict summary. |
| 6.5 Self-Hosting Speed | `done` | Compact resident rerun produced a verified paired edit proposal with first THINK under 10s. |
| 6.6 Coding Competence: Codex CLI Parity | `done` | Bootstrap, comparator slots, and frozen Codex CLI side-by-side batch passed with caveats. |
| 6.7 Supervised Self-Hosting Loop | `done` | Reviewer-gated supervised iterations, reentry, and detached close-watch satisfied the gate. |
| 6.8 Task Chaining: Supervised Self-Selection | `done` | Close gate passed via `docs/M6_8_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.8.5 Selector Intelligence and Curriculum Integration | `done` | Close gate passed via `docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.9 Durable Coding Intelligence | `done` | Close gate passed via `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`; Phase 4 moved to M6.8.5. |
| 6.10 Execution Accelerators and Mew-First Reliability | `done` | Latest 10 attempts reached 7/10 clean-or-practical with classified failures. |
| 6.11 Loop Stabilization | `done` | Core and residual hardening are closed; use its surfaces as diagnostics only. |
| 6.12 Failure-Science Instrumentation | `done` | V0 read-only ledger/classifier/report surface is closed. |
| 6.13 High-Effort Deliberation Lane | `done` | Close gate passed via `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.14 Mew-First Failure Repair Gate | `done` | Follow-on SR-017 side-project write-batch normalizer repair is recorded. |
| 6.15 Verified Closeout Redraft Repair | `merged_into_6.14` | Historical episode folded into M6.14. |
| 6.16 Codex-Grade Implementation Lane | `done` | Close gate passed via `docs/M6_16_CLOSE_GATE_AUDIT_2026-04-27.md`. |
| 6.17 Resident Meta Loop / Lane Chooser | `done` | Close gate passed via `docs/M6_17_CLOSE_GATE_AUDIT_2026-04-27.md`; v0 remains reviewer-gated. |
| 6.18 Implementation Failure Diagnosis Gate | `done` | Close gate passed via `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md`. |
| 6.19 Terminal-Bench Compatibility | `done` | mew and Codex both run bounded Harbor smoke with comparable artifacts. |
| 6.20 Terminal-Bench Driven Implement-Lane Debugging | `done` | Fixed two-task terminal gate closed on current head: both selected tasks reached 5/5 with Harbor errors 0. |
| 6.21 Terminal-Bench Codex Target Registry | `done` | Codex `0.121.0` / `gpt-5.5@openai` Terminal-Bench 2.0 leaderboard was frozen as JSON. |
| 6.22 Terminal-Bench Curated Subset Parity | `done` | Close gate passed via `docs/M6_22_CLOSE_GATE_AUDIT_2026-04-28.md`. |
| 6.23 Terminal-Bench Failure-Class Coverage | `done` | Close gate passed via `docs/M6_23_CLOSE_GATE_AUDIT_2026-04-28.md`. |
| 6.24 Software/Coding Terminal-Bench Parity Campaign | `in_progress` | Scope changed on 2026-05-03 to the 25 Terminal-Bench 2.0 `software-engineering,coding` tasks; scoped rebaseline pending. |
| 6.25 Codex-Plus Resident Advantage | `not_started` | Preserve parity while proving mew-native memory/reentry/repair and provider cache transport make it preferable to inhabit. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision while Terminal-Bench compatibility/debugging is active. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.24 Software/Coding Terminal-Bench Parity Campaign**.

Current controller mode: `improvement_phase` with
`scope_rebaseline_pending`.

Scope:

- M6.24 now focuses only on the 25 Terminal-Bench 2.0 tasks returned by the
  `software-engineering,coding` filters.
- The authoritative scoped task list is
  `docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`.
- Previous all-registry and `compile-compcert` records are historical repair
  evidence. They are not the active M6.24 close gate unless a later milestone
  explicitly promotes a BuildOrchestrationLane benchmark.

Controller docs:

- `docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_GAP_BASELINE_2026-04-29.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`

Next action:

```text
M6.24 -> software/coding cohort scope -> build scoped cohort rebaseline -> select first below-target in-scope gap -> UT/replay/dogfood/emulator -> speed_1
```

Do not spend new M6.24 live proof budget on out-of-scope tasks. If the next
action says to run a new `compile-compcert` speed proof, treat that as drift and
re-read the scope doc plus decision ledger first.

## M6.24 Close Gate

Done when:

- all 25 scoped `software-engineering,coding` tasks have mew results with
  complete artifacts and no unexplained Harbor runner errors;
- mew aggregate successes on the scoped 25-task cohort match or exceed the
  frozen Codex target for the same tasks and trial counts, or an explicit staged
  close gate is written after the scoped aggregate gap drops below the agreed
  near-parity threshold;
- every scoped task where mew is below Codex has a recorded classification and
  either a selected repair route or a written decision to defer it;
- every improvement-phase process change records current pain, expected benefit,
  one-run trial boundary, rollback condition, and adopted/rejected decision;
- no accepted structural blocker remains unaddressed while scoped measurement
  continues.

## Historical Evidence

The long `compile-compcert` repair sequence, Long-Build Substrate work, Long
Command Continuation work, and generic managed-exec decision remain valuable
build-orchestration evidence. They are archived and linked from the controller
docs, but they should not pull M6.24 back into an out-of-scope proof loop.

Useful historical files:

- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`
- `docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md`
- `docs/REVIEW_2026-05-03_CODEX_LONG_BUILD_BUDGET_PLANNING.md`
- `docs/REVIEW_2026-05-03_CLAUDE_CODE_LONG_BUILD_BUDGET_PLANNING.md`
- `docs/REVIEW_2026-05-03_FORGECODE_LONG_BUILD_BUDGET_PLANNING.md`

## Current Roadmap Focus

1. Rebaseline the scoped 25-task software/coding cohort against the frozen Codex
   target registry and local mew artifacts.
2. Select the first below-target in-scope gap using the M6.24 controller.
3. Before any live `speed_1`, run focused UT, replay, dogfood, and a same-shape
   emulator. If no emulator exists, build the smallest emulator fixture first.
4. If the selected gap is local/polish, fix it and rerun the same scoped shape.
5. If the selected gap is structural, pause M6.24 behind M6.14, repair the
   generic substrate, rerun the same scoped shape, then resume M6.24.
6. Keep M6.25 and M7+ pending until M6.24 reaches the scoped close gate or the
   user explicitly changes the priority.
