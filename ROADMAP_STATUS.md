# Mew Roadmap Status

Last updated: 2026-05-06

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
| 6.23.2 Lane Isolation Substrate | `done` | Close gate passed via `docs/M6_23_2_PHASE6_M6_24_REENTRY_AB_GATE_PROOF_2026-05-05.md`; M6.24 resumes with explicit lane attribution. |
| 6.24 Software/Coding Terminal-Bench Parity Campaign | `in_progress` | Active controller is now implement_v2 scoped rebaseline: remeasure the 25 software/coding tasks with v2 and repair any miss before unrelated measurement continues. |
| 6.25 Codex-Plus Resident Advantage | `not_started` | Preserve parity while proving mew-native memory/reentry/repair and provider cache transport make it preferable to inhabit. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision while Terminal-Bench compatibility/debugging is active. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.24 Software/Coding Terminal-Bench Parity Campaign**.

Current controller mode: `m6_24_implement_v2_scoped_rebaseline`.

Scope:

- M6.23.2 is closed. The full sequence passed:
  Phase 1 lane isolation substrate, Phase 2 native tool-loop v0, Phase 3
  read/search spike, Phase 4 managed exec, Phase 5 write/edit/apply_patch, and
  Phase 6 M6.24 reentry A/B gate.
- Phase 1 and Phase 2 are implemented. Phase 3 read/search v2 spike is
  implemented, reviewed, and proved in
  `docs/M6_23_2_PHASE3_READ_ONLY_PROOF_2026-05-05.md`.
- Phase 4 managed exec v2 spike is implemented, reviewed, and proved in
  `docs/M6_23_2_PHASE4_MANAGED_EXEC_PROOF_2026-05-05.md`.
- Phase 5 write/edit/apply_patch v2 spike is implemented, reviewed, and proved
  in `docs/M6_23_2_PHASE5_WRITE_APPROVAL_PROOF_2026-05-05.md`.
- Phase 6 M6.24 reentry A/B gate is implemented, reviewed, and proved in
  `docs/M6_23_2_PHASE6_M6_24_REENTRY_AB_GATE_PROOF_2026-05-05.md`.
- `implement_v1` remains the compatibility/default lane, but it was not the
  selected lane for the latest `build-cython-ext` same-shape speed/debug
  attempt.
- `implement_v2` now has a live `model_json` runtime that bypasses the v1
  THINK/ACT planner, emits v2 transcript/proof artifacts, and can write/verify
  through the v2 substrates. It remains explicit-selection only.
- Provider-specific native tool-call transport is still future work; current
  v2 proof must be described as `model_json`, not provider-native.
- M6.24 live proof work resumes only with explicit lane metadata. The active
  measurement lane is now `implement_v2`; historical `implement_v1` results
  remain repair evidence but cannot close the current M6.24 gate.
- The active controller is
  `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`: run one `speed_1` per
  scoped software/coding task with `selected_lane=implement_v2`, and pause to
  repair if a task misses, is harness-invalid, lacks replayable artifacts, or
  exposes a structural lane gap.
- The first true-v2 `build-cython-ext` speed attempt
  `mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0215` is excluded from
  product evidence: Docker failed before `mew` launched because the harness
  used missing cwd `/workspace`. The task was rerun with `/app`.
- The first task-correct `/app` true-v2 `build-cython-ext` run
  `mew-m6-24-true-v2-build-cython-ext-speed1-20260506-10min-appcwd` completed
  in `4m43s` with runner errors `0`, but scored `0.0`. It is valid divergence
  evidence, not a pass: v2 spent turns on tool-surface mismatches (`cmd`,
  `argv`, compound shell strings, and edit aliases), then fixed Python files
  but missed the sibling Cython `*.pyx`/`*.pxd` NumPy-alias frontier. Live
  speed spending was stopped until that generic v2 I/F/frontier gap was
  repaired and covered by focused UT plus replay/dogfood/emulator checks.
- Current repair status: v2 tool-surface mismatch is repaired, true-v2
  artifacts replay through `implement_v2/history.json` and
  `proof-manifest.json`, and generic compiled/native Python compatibility
  frontier guidance is present. The follow-up `/app` true-v2 run
  `mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0245-appcwd` moved the
  gap: v2 applied the broad Python/Cython NumPy alias repair, then killed the
  final rebuild/install/smoke command when `max_turns` closed the attempt.
  The generic active-command closeout repair now drains a running managed
  command within remaining wall budget on normal close and records terminal
  evidence instead of immediately cancelling it. The current-head pre-speed
  gate was run before the post-repair live proof; old v1 replay-only gates are
  not enough for v2.
- Post-closeout proof status: the current-head `/app` true-v2 run
  `mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0312-closeout` passed
  with reward `1.0`, runner errors `0`, runtime `4m52s`, `work_exit_code=0`,
  `stop_reason=finish`, `selected_lane=implement_v2`, and external verifier
  `11/11` passing. Exact replay and dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not as the whole M6.24 close
  proof. Do not rerun the same speed_1 shape blindly.
- `circuit-fibsqrt` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-circuit-fibsqrt-speed1-20260506-0335/mew-m6-24-v2-rebaseline-circuit-fibsqrt-speed1-20260506-0335/result.json`
  scored `1.0` with runner errors `0`, runtime `5m59s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `3/3` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `cobol-modernization` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-cobol-modernization-speed1-20260506-0348/mew-m6-24-v2-rebaseline-cobol-modernization-speed1-20260506-0348/result.json`
  scored `1.0` with runner errors `0`, runtime `3m06s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `3/3` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `distribution-search` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-distribution-search-speed1-20260506-0350/mew-m6-24-v2-rebaseline-distribution-search-speed1-20260506-0350/result.json`
  scored `1.0` with runner errors `0`, runtime `6m52s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `4/4` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `feal-differential-cryptanalysis` true-v2 scoped rebaseline evidence:
  the first v2 attempt
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0359`
  missed because `model_json_parse_error` was not replayable. The generic
  repair now makes JSON extraction tolerate a valid leading object with
  trailing text and records no-tool-call v2 model errors as replayable lane
  failures. The same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair/result.json`
  scored `1.0` with runner errors `0`, runtime `5m48s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `1/1` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `feal-linear-cryptanalysis` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426/result.json`
  scored `1.0` with runner errors `0`, runtime `4m19s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `1/1` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `fix-git` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-fix-git-speed1-20260506-0435/mew-m6-24-v2-rebaseline-fix-git-speed1-20260506-0435/result.json`
  scored `1.0` with runner errors `0`, runtime `1m57s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `2/2` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `hf-model-inference` true-v2 scoped rebaseline evidence:
  the first two attempts were harness/infra-invalid before mew product scoring
  because Docker image extraction failed with `no space left on device`. After
  host Docker capacity was freed, the same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-hf-model-inference-speed1-20260506-1030/mew-m6-24-v2-rebaseline-hf-model-inference-speed1-20260506-1030/result.json`
  scored `1.0` with runner errors `0`, runtime `5m25s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `4/4` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `kv-store-grpc` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-kv-store-grpc-speed1-20260506-1050/mew-m6-24-v2-rebaseline-kv-store-grpc-speed1-20260506-1050/result.json`
  scored `1.0` with runner errors `0`, runtime `2m27s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `7/7` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- `largest-eigenval` true-v2 scoped rebaseline evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-largest-eigenval-speed1-20260506-1053/mew-m6-24-v2-rebaseline-largest-eigenval-speed1-20260506-1053/result.json`
  scored `1.0` with runner errors `0`, runtime `7m11s`, `work_exit_code=0`,
  `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, and external verifier `27/27` passing. Exact replay and
  matching terminal-bench replay dogfood on the passing artifact also pass.
  This counts as v2 rebaseline `speed_1` evidence, not close proof.
- True-v2 canary evidence:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-true-implement-v2-prove-plus-comm-1attempt-20260506-0204/mew-m6-24-true-implement-v2-prove-plus-comm-1attempt-20260506-0204/result.json`
  scored `1.0` with runner errors `0`; the mew report recorded
  `selected_lane=implement_v2`, `runtime_id=implement_v2_model_json_tool_loop`,
  `lane_status=completed`, `work_exit_code=0`, replay-valid proof artifacts,
  and no v1 planner call path.

Controller docs:

- `docs/DESIGN_2026-05-05_M6_23_2_LANE_ISOLATION_SUBSTRATE.md`
- `docs/DESIGN_2026-05-05_M6_23_2_IMPLEMENT_V2_NATIVE_TOOL_LOOP.md`
- `docs/M6_23_2_PHASE3_READ_ONLY_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE4_MANAGED_EXEC_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE5_WRITE_APPROVAL_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE6_M6_24_REENTRY_AB_GATE_PROOF_2026-05-05.md`
- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`

M6.24 reentry decision:

```text
selected_lane=implement_v2 is now the active M6.24 measurement lane; remeasure scoped software/coding tasks with v2 speed_1; if a run misses or exposes a structural lane gap, reproduce through replay/dogfood/emulator and repair before unrelated measurement continues
```

Latest update: selected `build-cython-ext`, `circuit-fibsqrt`,
`cobol-modernization`, `distribution-search`,
`feal-differential-cryptanalysis`, `feal-linear-cryptanalysis`, `fix-git`,
`hf-model-inference`, `kv-store-grpc`, and `largest-eigenval` v2 speed_1 runs
passed with exact replay and terminal-bench replay dogfood. The
current decision is no longer
"build-cython proof_5 now"; it is "continue the implement_v2 scoped rebaseline,
while preserving immediate repair on any miss or structural lane gap."

## Active M6.24 Context

- M6.24 focuses only on the 25 Terminal-Bench 2.0 tasks returned by the
  `software-engineering,coding` filters.
- The authoritative scoped task list is
  `docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`.
- The scoped rebaseline is
  `docs/M6_24_SOFTWARE_CODING_REBASELINE_2026-05-03.md`.
- The active repeated-gap dossier is
  `docs/M6_24_DOSSIER_BUILD_CYTHON_EXT_2026-05-03.md`.
- Fresh Codex/Claude Code reference traces for the same active gap are recorded
  in `docs/M6_24_REFERENCE_TRACE_BUILD_CYTHON_EXT_2026-05-05.md`.
- The current-head remeasurement artifact is
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-rebaseline-build-cython-ext-1attempt-20260503-1936/result.json`.
- Previous all-registry and `compile-compcert` records are historical repair
  evidence. They are not the active M6.24 close gate unless a later milestone
  explicitly promotes a BuildOrchestrationLane benchmark.

Controller docs:

- `docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`
- `docs/M6_24_SOFTWARE_CODING_REBASELINE_2026-05-03.md`
- `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`
- `docs/M6_24_DOSSIER_BUILD_CYTHON_EXT_2026-05-03.md`
- `docs/M6_24_REFERENCE_TRACE_BUILD_CYTHON_EXT_2026-05-05.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_GAP_BASELINE_2026-04-29.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`

Next action:

```text
M6.24 -> implement_v2 scoped rebaseline -> make-doom-for-mips is recorded_deferred as task_strategy_wall_budget_limited_runtime_artifact_frontier -> return to selected build-cython-ext gap -> replay/dogfood/emulator classification -> generic repository-test-tail frontier repair or record/defer -> exactly one build-cython-ext speed_1 only after local proof
```

The 2026-05-07 same-shape `make-doom-for-mips` rerun after the finish-gate
prior-failure repair is replayable and classified, but codex-ultra marked it
`RECORD_AND_DEFER`: task strategy plus wall-budget limited runtime-artifact
frontier, not a local loop-boundary bug. Do not spend another same-shape
make-doom speed run without a generic frontier-throttling or strategy design.

The active repair target returns to `build-cython-ext`. The 2026-05-05
Codex/Claude Code reference traces both pass `build-cython-ext` and confirm
that the next repair should make same-family verifier/runtime failures a
compact active repair frontier before another broad build/test/finish cycle.

Do not spend new M6.24 live proof budget on out-of-scope tasks. If the next
action says to run a new `compile-compcert` speed proof, treat that as drift and
re-read the scope doc plus decision ledger first.

## M6.24 Close Gate

Done when:

- all 25 scoped `software-engineering,coding` tasks have mew results with
  `implement_v2` results, complete artifacts, and no unexplained Harbor runner
  errors;
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

1. Continue the `implement_v2` scoped rebaseline from
   `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`; `make-doom-for-mips` is
   recorded/deferred and should not pull the session into another same-shape
   proof loop.
2. Work the selected `build-cython-ext` gap from
   `docs/M6_24_SOFTWARE_CODING_REBASELINE_2026-05-03.md`: read the dossier and
   latest artifact, reproduce with replay/dogfood/emulator, then implement only
   a generic repository-test-tail/frontier repair if the evidence supports it.
3. If any run misses, is harness-invalid, lacks replayable artifacts, or exposes
   a structural lane gap, stop measuring unrelated tasks and repair via
   replay/dogfood/emulator before rerunning the same shape.
4. Keep M6.25 and M7+ pending until M6.24 reaches the scoped close gate or the
   user explicitly changes the priority.
