# Mew Roadmap Status

Last updated: 2026-05-27

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
| 6.25 Codex-Plus Resident Advantage | `in_progress` | Active focus: preserve the M6.24 baseline while proving typed-card memory, eval-backed recall, reentry, diagnosis, repair reuse, and provider-cache ergonomics. |
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

2026-05-20 M6.25 implementation update: commits `f392111`, `f3ef986`, and
`71748e2` fixed implement_v2 native defaults, added the
`resident-golden-convention-recall` Harbor fixture, and captured an initial
durable-coding memory design. Commit `dfc5a9b` reverted the premature
sidecar-only durable-memory projection dry-run implementation because the
memory cycle, injection point, and campaign evidence contract require
redesign. The next work is to keep the Harbor fixture, redesign durable memory
mechanics, and only then reintroduce implementation behind explicit gates.

2026-05-20 decision update: commit `f108aa0` added direct MemoryArena scoring
for the memory core. Do not build an external Harbor resident campaign runner
as the next step. It is not a useful resident-agent proof until memory is wired
into `implement_v2` itself. Keep the Harbor fixture as a future benchmark, but
defer Harbor memory-on/off campaign execution until the implement lane has a
real, bounded, inspectable memory surface.

2026-05-21 decision update: MemoryArena remains auxiliary, not the primary
M6.25 memory close gate. Current memory recall is mostly token-overlap over
structured entries, so the next valuable work is `MemoryContextBuilder`
contract and V0 fixtures: compression, progressive expansion, relevance,
decay/contradiction, scope isolation, retrieval timing, and retrieval audit.
Use `docs/REVIEW_2026-05-20_MEMORY_CONTEXT_BUILDER_LITERATURE.md` as the
literature basis and `docs/DESIGN_2026-05-21_M6_25_MEMORY_CONTEXT_BUILDER.md`
as the implementation authority.

2026-05-27 memory-eval update: the active memory design authority is now
`docs/DESIGN_2026-05-22_M6_25_MEMORY_SUBSYSTEM_TYPED_CARDS_PLAN.md`.
Append memory-eval observations to `docs/M6_25_MEMORY_EVAL_LOG.md` whenever
MemBench, live extractor smoke, backend comparison, graph-on recall, or
provider-memory validation is run. The log currently records committed
relation-sensitive niece/company coverage, deterministic MemBench backend
artifacts, and opt-in live GPT-5.5 MemBench smoke artifacts. Treat `tmp/`
artifacts as local evidence until summarized in that log.

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
Typed-card memory design: `docs/DESIGN_2026-05-22_M6_25_MEMORY_SUBSYSTEM_TYPED_CARDS_PLAN.md`.
Memory eval log: `docs/M6_25_MEMORY_EVAL_LOG.md`.

M6.25 proves Codex-plus resident advantage while preserving the M6.24 baseline. The active work is not another Terminal-Bench proof sweep.

Phase order:

1. Baseline and guard: keep M6.24 closed, use `proof-artifacts/m6_25_resident_advantage_ledger.jsonl`, and define cold-vs-resident evidence axes.
2. Durable memory redesign: define memory kinds, write cycle, retrieval cycle,
   revise gate, injection point, and experiment gates before adding code.
3. Implement-lane memory integration design: connect memory to `implement_v2`
   only as a bounded, inspectable surface, not as ambient prompt policy.
4. Bounded read-only memory summary or recall surface: add only if measurable
   and if ordinary `implement_v2` requests can prove what memory was exposed.
5. Resident campaign/ledger: run paired cold/resident/stale evidence on the
   committed Harbor fixture only after the implement lane can actually use the
   memory surface being evaluated.
6. Read-only `MemoryExploreProvider` boundary.
7. Provider cache transport behind default-off flags.
8. Resident advantage report.

Current next action: continue M6.25 typed-card memory work by appending a fresh
deterministic MemBench/backend rerun to `docs/M6_25_MEMORY_EVAL_LOG.md`, then
close the next memory slice from
`docs/DESIGN_2026-05-22_M6_25_MEMORY_SUBSYSTEM_TYPED_CARDS_PLAN.md`.
Prioritize remaining graph/index validation and the Phase E/F read-only
provider schema only after the core/adapter eval path stays green. Do not
implement a MemoryArena model-in-loop agent or Harbor resident campaign runner
yet. Do not treat
`docs/DESIGN_2026-05-20_M6_25_IMPLEMENT_V2_DURABLE_CODING_INTELLIGENCE.md` or
the reverted `016e102` implementation as active implementation authority. Do
not inject memory into ordinary `implement_v2` requests until the Phase F
provider surface is explicit, default-off, and covered by provider snapshot and
leak tests.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action here.
- When a milestone closes, add or update a close-gate audit in `docs/` and summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions override the active milestone decision in this file.
