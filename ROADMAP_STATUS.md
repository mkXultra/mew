# Mew Roadmap Status

Last updated: 2026-05-20

This file is the compact operational roadmap dashboard for context reentry.
Detailed history is intentionally archived instead of kept here.

Detailed archives:

- `docs/archive/ROADMAP_STATUS_through_M5_2026-04-20.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-05-03.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-05-20.md`

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
| 6.23.2 Lane Isolation Substrate | `done` | Close gate passed via `docs/M6_23_2_PHASE6_M6_24_REENTRY_AB_GATE_PROOF_2026-05-05.md`; M6.24 resumes with explicit lane attribution. |
| 6.24 Software/Coding Terminal-Bench Parity Campaign | `done` | Staged close passed via `docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md`: 25/25 scoped tasks have evidence, 22/25 clean speed_1 passes, `make-mips-interpreter` proof_5 exceeded target, and remaining below-target rows are classified/deferred. |
| 6.25 Codex-Plus Resident Advantage | `in_progress` | Active focus: preserve the M6.24 baseline while proving mew-native persistence, reentry, memory, diagnosis, repair reuse, and provider-cache ergonomics. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision while Terminal-Bench compatibility/debugging is active. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.25 Codex-Plus Resident Advantage**.

Current controller mode:
`m6_25_resident_advantage_after_m6_24_staged_close`.

Current diagnostic mode:
`m6_24_proof5_deferred_m6_25_planning`.

Current reentry decision:
2026-05-20 update: M6.24 is staged-closed by
`docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md`. Do not run the previously
selected `reshard-c4-data` proof_5 next; the user explicitly rejected that spend
as too time-expensive for the current decision. M6.25 is now active. The next
work is to plan and execute Codex-plus resident advantage evidence while
preserving the M6.24 baseline.

2026-05-20 M6.25 plan: `docs/M6_25_RESIDENT_ADVANTAGE_PLAN_2026-05-20.md`
defines the active phase order. Phase 0 is baseline/guard plus experiment
ledger (`proof-artifacts/m6_25_resident_advantage_ledger.jsonl`). Phase 1 is a
memory-light cold-vs-resident reentry comparison, starting with
`reshard-c4-data` repair-reuse evidence. Do not run proof_5 as that experiment.

## M6.24 Close Summary

M6.24 is staged-closed via `docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md`.

Key evidence:

- `25/25` scoped Terminal-Bench software/coding tasks have `implement_v2` evidence.
- `22/25` clean `speed_1` rows passed.
- `make-mips-interpreter` proof_5 reached `4/5`, above frozen Codex target `3/5`.
- Below-target rows are classified and deferred: `make-doom-for-mips` and `raman-fitting`.
- No unexplained Harbor runner error remains in the final selected rows.
- No accepted active structural blocker remains open.

Do not resume `reshard-c4-data` proof_5. That prior next-action was superseded by the staged-close decision because proof_5 is too time-expensive for the current decision.

Detailed M6.24 history is archived in `docs/archive/ROADMAP_STATUS_detailed_2026-05-20.md` and the task table remains in `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`.

## M6.25 Reentry Guard

Governing plan: `docs/M6_25_RESIDENT_ADVANTAGE_PLAN_2026-05-20.md`.

M6.25 proves Codex-plus resident advantage while preserving the M6.24 baseline. The active work is not another Terminal-Bench proof sweep.

Phase order:

1. Baseline and guard: keep M6.24 closed, use `proof-artifacts/m6_25_resident_advantage_ledger.jsonl`, and define cold-vs-resident evidence axes.
2. Memory-light reentry advantage: compare cold vs resident recovery on a small repair-reuse shape.
3. Bounded read-only memory summary: add only if bounded, inspectable, and measurable.
4. Read-only `MemoryExploreProvider` boundary.
5. Provider cache transport behind default-off flags.
6. Resident advantage report.

Current next action: define the first M6.25 cold-vs-resident comparison shape. Use `reshard-c4-data` repair-reuse as the candidate only as a memory/reentry experiment, not as proof_5.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action here.
- When a milestone closes, add or update a close-gate audit in `docs/` and summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions override the active milestone decision in this file.
