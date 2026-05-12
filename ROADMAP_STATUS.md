# Mew Roadmap Status

Last updated: 2026-05-12

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
| 6.24 Software/Coding Terminal-Bench Parity Campaign | `in_progress` | Active controller is native step-shape diagnosis after partial transcript preservation. The latest step-check preserved paired native transcript evidence; current repair targets low remaining provider-turn budget and interrupted-verifier repair projection before another live proof. |
| 6.25 Codex-Plus Resident Advantage | `not_started` | Preserve parity while proving mew-native memory/reentry/repair and provider cache transport make it preferable to inhabit. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision while Terminal-Bench compatibility/debugging is active. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.24 Software/Coding Terminal-Bench Parity Campaign**.

Current controller mode: `m6_24_native_step_shape_diagnostic_repair`.

Current diagnostic mode: `m6_24_native_step_shape_gate`.

Phase 1 of
`docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md` is
green. Native v2 keeps `NativeTranscript` / provider-native paired tool outputs
as the source of truth, exposes only `native_transcript_window` plus bounded
`compact_sidecar_digest` as dynamic provider input, and keeps full
`persisted_lane_state`, ordinary repair `required_next`, and prescriptive
`native_loop_control` policy text out of the default provider-visible path.
The partial transcript preservation repair was committed as `d3605d9`. The next
bounded diagnostic,
`mew-make-mips-interpreter-step-check-10min-20260512-105949`, preserved paired
native transcript evidence (`72` native calls / `72` outputs, valid pairing, no
parse errors). It is still not clean solver evidence: the final provider turn
entered with only about `6.3s` active timeout and failed as `request timed out`,
and the compact digest returned to `orient` after an interrupted verifier plus
one diagnostic probe. Current repair is bounded and generic: block provider
turns before they start when remaining model budget is below the native minimum,
and keep interrupted/killed/timed-out verifier failures in repair projection
after one post-failure probe. Focused validation is green and codex-ultra review
session `019e1a0b-06bc-7612-941a-b7a6bd25dbe7` returned `STATUS: APPROVE`.
Do not run `speed_1`, `proof_5`, or broad measurement until this repair is
committed and followed by one bounded native step-shape diagnostic.

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
- `implement_v2` is being rebuilt as a provider-native transcript runtime. The
  old live `model_json` runtime is now explicit quarantine for legacy tests,
  replay compatibility, and dogfood emulators only; it is not the selected
  production v2 main path.
- Provider-specific live native tool-call execution is wired. Tiny live
  native-loop diagnostic
  `proof-artifacts/m6_24_native_loop_gate_20260511_live_portable/` completed
  through provider-native `inspect_dir -> write_file -> run_tests -> finish`,
  emitted authoritative native artifacts, and passed
  `scripts/check_implement_v2_native_gate.py`.
- M6.24 live proof work may resume with one bounded native step-shape
  diagnostic. The active proof lane is still `implement_v2`, and Phase 1
  boundary validation is green: focused native projection/harness tests,
  hot-path fastcheck, scoped ruff, `git diff --check`, and
  `scripts/check_native_tool_loop_boundary.py` passed; codex-ultra review
  session `019e198a-88e3-7962-886d-072a9b05d997` returned `STATUS: APPROVE`.
  Historical `implement_v1`, model-JSON `implement_v2`, pre-native WorkFrame
  results, and the tiny native-loop gate remain repair evidence but cannot
  replace the next bounded native diagnostic.
- The prior scoped rebaseline controller
  (`docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`) remains suspended until
  the next bounded same-shape native diagnostic is examined.
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
- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
- `docs/M6_23_2_PHASE3_READ_ONLY_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE4_MANAGED_EXEC_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE5_WRITE_APPROVAL_PROOF_2026-05-05.md`
- `docs/M6_23_2_PHASE6_M6_24_REENTRY_AB_GATE_PROOF_2026-05-05.md`
- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`

M6.24 reentry decision:

```text
selected_lane=implement_v2 is still the active M6.24 lane; native responsibility-boundary Phase 1 is green, so run exactly one bounded native step-shape diagnostic next. Keep NativeTranscript/provider-native paired outputs as source of truth, keep full persisted_lane_state and ordinary repair required_next out of the default provider-visible path, and do not jump directly to speed_1/proof_5/broad measurement before analyzing that diagnostic.
```

Latest update: selected `build-cython-ext`, `circuit-fibsqrt`,
`cobol-modernization`, `distribution-search`,
`feal-differential-cryptanalysis`, `feal-linear-cryptanalysis`, `fix-git`,
`hf-model-inference`, `kv-store-grpc`, and `largest-eigenval` v2 speed_1 runs
passed with exact replay and terminal-bench replay dogfood. This is historical
pre-WorkFrame measurement evidence. The current decision is no longer
"build-cython proof_5 now" or "continue the implement_v2 scoped rebaseline";
the current decision is the native responsibility-boundary Phase 1 above.

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
- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_GAP_BASELINE_2026-04-29.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`

Current native-boundary-gated next action:

```text
M6.24 -> native responsibility-boundary Phase 1 green -> run one bounded native step-shape diagnostic -> compare step shape and provider-visible request inventory -> then decide repair vs speed_1/proof_5/broad measurement
```

Older scoped-rebaseline, WorkFrame, diagnostic-runner, and native-loop rows
remain historical evidence. They do not supersede the next bounded native
diagnostic.

The 2026-05-07 same-shape `make-doom-for-mips` rerun after the finish-gate
prior-failure repair is replayable and classified, but codex-ultra marked it
`RECORD_AND_DEFER`: task strategy plus wall-budget limited runtime-artifact
frontier, not a local loop-boundary bug. Do not spend another same-shape
make-doom speed run without a generic frontier-throttling or strategy design.

Historical pre-WorkFrame `make-mips-interpreter` note: the first v2 speed run
exposed generic tool-contract friction and that repair was committed. The
same-shape rerun at `20260507-1341-tool-contract-repair` moved past that bug
but exposed a second generic expected-artifact contract normalization gap:
stdout/stderr artifacts declared as `target: "stdout"` or `stream: "stdout"`
were treated as path artifacts with no path, and model-facing check aliases
were projected as default `exists` checks. That evidence helped motivate the
WorkFrame proof gate; it is not an active instruction to resume the old repair
or spend scoped measurement before the WorkFrame gate.

The active repair target does not stay on `build-cython-ext`: its passing v2
artifact `mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0312-closeout`
still replays and dogfoods green on current head with `mew_exit_code=0` and
external reward `1.0`. Do not rerun the same speed_1 shape blindly; any future
`build-cython-ext` proof spend must be an explicit close-proof decision.

Do not spend new M6.24 live proof budget on out-of-scope tasks. If the next
action says to run a new `compile-compcert` speed proof, treat that as drift and
re-read the scope doc plus decision ledger first.

## M6.24 Close Gate

Done when:

- the `implement_v2` native transcript rebuild has a green native-loop gate:
  selected production v2 uses `implement_v2_native_transcript_loop`, provider
  native tool calls and paired outputs are authoritative transcript artifacts,
  legacy model-JSON v2 is limited to explicit quarantine tests/replay/emulators,
  and proof metrics reject `model_json_main_path_detected=true`;
- the `implement_v2` HOT_PATH_COLLAPSE design has explicit Phase 0-6 evidence:
  before any same-shape 10 minute diagnostic, the HOT_PATH fastcheck passes.
  Legacy WorkFrame artifacts must pass focused UT, saved-artifact replay,
  prompt leak checks, sidecar/projection checks, latest-actionable-failure
  shape checks, and a required hash-bound micro next-action check. Native
  transcript artifacts must pass transcript/response-items/manifest consistency,
  native trace summary, and native loop-control replay without requiring
  legacy `history.json`;
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

### M6.24 Native Boundary Status

Status as of 2026-05-12: **in progress**. The native transcript rebuild design
`docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md` gave
mew a provider-native runtime. The active design is now
`docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`,
which prevents WorkFrame/todo/evidence sidecars from becoming a second
model-visible control plane.

Phase 0 boundary inventory/static audit is complete and committed as
`3059cca`. It audits the current semantic-ish controls across
`native_tool_harness.py`, `native_sidecar_projection.py`,
`native_workframe_projection.py`, `exec_runtime.py`, and
`execution_evidence.py`.

Native-loop gate evidence:

- artifact root:
  `proof-artifacts/m6_24_native_loop_gate_20260511_live_portable/`
- work exit: `0`, stop reason: `finish`
- runtime: `implement_v2_native_transcript_loop`
- transport: `provider_native`, provider: `openai`, model: `gpt-5.5`
- step shape: `inspect_dir -> write_file -> run_tests -> finish`
- pairing: valid, `call_count=4`, `output_count=4`, `errors=[]`
- first write: turn 2, about 26.3s
- first verifier: turn 3, about 36.1s
- native gate:
  `uv run python scripts/check_implement_v2_native_gate.py --artifact proof-artifacts/m6_24_native_loop_gate_20260511_live_portable --json`
  returned `ok=true`

Remaining active gap: do not classify the latest bounded 10min native
step-shape diagnostic as a solver failure. Provider request inventory now
survives, but partial native transcript artifacts are still lost when a later
provider turn times out. The repair is reviewed and ready to commit; after that,
rerun and analyze one bounded native step-shape diagnostic.

### M6.24 HOT_PATH_COLLAPSE Phase Status

Status as of 2026-05-10: **implementation complete, proof gate pending**. The
WorkFrame Phase 0-6 code path has been implemented, reviewed phase-by-phase,
and committed through `3787e83`. HOT_PATH_COLLAPSE is still not closeable until
the WorkFrame-native fastcheck/dogfood/emulator gate and one same-shape
`step-check-10min` are recorded. Treat any reentry that jumps to `speed_1`,
`proof_5`, or broad measurement before that gate as drift.

Redesign note: after many same-shape polish commits across frontier/todo/
evidence/contract/finish/closeout boundaries, a reviewed no-backward-
compatibility WorkFrame redesign now exists at
`docs/DESIGN_2026-05-10_M6_24_IMPLEMENT_V2_WORKFRAME_REDESIGN.md`, with
paper-grounded support in
`docs/REVIEW_2026-05-10_M6_24_WORKFRAME_LITERATURE_REVIEW.md`. The review loop
resolved round-1 findings and round 2 returned no remaining `needs_fix`
findings. Phases 0-6 were then implemented in small reviewed commits:
`42a8012`, `6548669`, `57e7aff`, `c3ccfa9`, `3d28412`, `1fff2ab`, and
`3787e83`. This supersedes older same-shape `step-check-10min` / `speed_1` /
`proof_5` rows that predate the WorkFrame boundary.

| Phase | Status | Current evidence / remaining gap |
|---|---|---|
| Phase 0 baseline/metrics | implemented/reviewed | `42a8012` introduced the WorkFrame schema, canonical reducer, invariant report, baseline fields, and fixture tests. |
| Phase 1 prompt collapse | implemented/reviewed | `6548669` cut the ordinary prompt over to a single dynamic `implement_v2_workframe` section and removed normal prompt dependence on model-authored frontier state. |
| Phase 2 latest actionable failure | implemented/reviewed | `57e7aff` routes latest failures through reducer-owned generic categories and `required_next`/`forbidden_next` rather than parallel frontier/todo prompt cards. |
| Phase 3 sidecar-inferred execution contracts | implemented/reviewed | `c3ccfa9` keeps execution contracts, typed evidence, and oracle details sidecar-only while WorkFrame carries compact refs and obligations. |
| Phase 4 patch/edit as mutation boundary | implemented/reviewed | `3d28412` makes source mutation and verifier freshness reducer-owned WorkFrame facts. |
| Phase 5 finish cited evidence | implemented/reviewed | `1fff2ab` routes finish readiness and final verifier closeout deterministically through WorkFrame/sidecars instead of finish-continuation proof dumps. |
| Phase 6 replay/dogfood/emulator/step-shape gate | implemented/reviewed; proof gate superseded | `3787e83` extends HOT_PATH fastcheck with WorkFrame replay, invariant, ref-policy, reentry, prompt-leak, hard-reject, and hash-bound micro checks. Focused validation passed (`454 passed`), scoped ruff passed, `git diff --check` passed, and codex-ultra reviewer session `019e0f86-d16a-7da3-ac92-2a39cb825ca6` returned `STATUS: APPROVE`. The WorkFrame proof-gate next action is superseded by the 2026-05-12 native responsibility-boundary Phase 1 gate. |

Historical WorkFrame action: close the WorkFrame proof gate by repairing
`transition_contract` hot-path patch-anchor/runtime-artifact-obligation handling
and rerunning focused checks plus one same-shape diagnostic. This is not the
current next action while `native_boundary_phase1_active` is open. Do not resume
this WorkFrame action until the native boundary row in
`docs/M6_24_DECISION_LEDGER.md` is closed or explicitly superseded.

WorkFrame variant benchmark note (2026-05-10): after Codex, Claude Code, and
2025-2026 literature reviews of `tool result -> evidence/state -> next action`,
the historical WorkFrame proof-gate strategy was to measure WorkFrame reducer
variants before another long polish sequence. That strategy is superseded while
`native_boundary_phase1_active` is open. The retained lesson is architectural:
if WorkFrame variants are revisited later, keep variant implementations isolated
from tool runtime/provider loop/verifier changes and compare them with the same
fastcheck, same diagnostic, and same analyzer.

WorkFrame variant comparison result (2026-05-11): the same-shape
`make-mips-interpreter` comparison is recorded in
`docs/M6_24_WORKFRAME_VARIANT_COMPARISON_2026-05-11.md`. The initial comparison
summary missed Terminal-Bench v2 rewards; commit `3a9c940` fixed reward and
work-exit classification. Corrected result: all variants remain task-red
(`reward=0.0`, `work_exit_code=1`), but `transition_contract` is the best
default candidate and remains selected. `minimal` stays a comparator.
`transcript_tool_nav` must not be promoted because it exceeded the WorkFrame
size cap, never edited or verified, and used the largest prompt budget. Next
repair is generic `transition_contract` hot-path work: turn patch-anchor
mismatch into direct re-anchor or bounded rewrite action, preserve exact runtime
artifact obligations from the latest verifier result while keeping internal
WorkFrame artifact paths distinct from the external Terminal-Bench target, then
run focused UT/fastcheck/micro checks followed by exactly one same-shape
`transition_contract` 10 minute diagnostic and reference-step comparison.

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

1. The active M6.24 focus is native responsibility-boundary Phase 1 from
   `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`.
2. Use `docs/M6_24_DECISION_LEDGER.md` and the native boundary section above as
   the reentry guard. They supersede older HOT_PATH polish, WorkFrame,
   diagnostic-runner, or scoped-rebaseline rows that point directly to
   `step-check-10min`, `speed_1`, `proof_5`, or broad measurement.
3. Required next order: implement compact sidecar digest boundary, remove full
   `persisted_lane_state` and ordinary repair `required_next` from default
   provider-visible input, preserve loop signals as bounded observational
   booleans/hints, run focused projection/harness tests plus
   `scripts/check_native_tool_loop_boundary.py`, then run exactly one bounded
   same-shape diagnostic.
4. If the gate is red, repair the native boundary/projection failure first. Do
   not add another model-visible frontier/todo/evidence projection as a shortcut.
5. Keep M6.25 and M7+ pending until M6.24 reaches the scoped close gate or the
   user explicitly changes the priority.
