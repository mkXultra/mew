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
| 6.8 Task Chaining: Supervised Self-Selection | `done` | Close gate passed via `docs/M6_8_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.8.5 Selector Intelligence and Curriculum Integration | `done` | Close gate passed via `docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.9 Durable Coding Intelligence | `done` | Close gate passed via `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`; Phase 4 moved to M6.8.5. |
| 6.10 Execution Accelerators and Mew-First Reliability | `done` | Latest 10 attempts reached 7/10 clean-or-practical with classified failures. |
| 6.11 Loop Stabilization | `done` | Core and residual hardening are closed; use its surfaces as diagnostics only. |
| 6.12 Failure-Science Instrumentation | `done` | V0 read-only ledger/classifier/report surface is closed. |
| 6.13 High-Effort Deliberation Lane | `in_progress` | WorkTodo lane default, lane registry v0, mirror lane-scoped replay bundles, and deliberation preflight/budget primitives landed. |
| 6.14 Mew-First Failure Repair Gate | `done` | Repair ledger covers known mew-first substrate failures; future repairs append here. |
| 6.15 Verified Closeout Redraft Repair | `merged_into_6.14` | Historical episode folded into M6.14. |
| 6.16 Codex-Grade Implementation Lane | `not_started` | Future lane-hardening milestone after M6.13 telemetry identifies ordinary implementation-lane bottlenecks. |
| 6.17 Resident Meta Loop / Lane Chooser | `not_started` | Future supervisor milestone after lane telemetry, mirror/deliberation boundaries, and implementation-lane reliability are proven. |
| 7. Senses: Inbound Signals | `foundation` | Signal gates/journaling/RSS pieces exist; deeper work deferred. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.13 High-Effort Deliberation Lane**.

Why M6.13 is active:

- M6.8.5 closed the selector intelligence gate and the prior M6.13 deferral
  trigger has fired.
- M6.9 durable memory and M6.11 loop stabilization are usable, but hard
  work-loop blockers still need an explicit, bounded escalation lane.
- The next resident capability gap is controlled high-effort reasoning: mew
  should be able to ask for it, account for it, fall back safely, and
  internalize useful results without making it the default path.

Current M6.13 target:

- keep the existing tiny lane authoritative and backward compatible
- treat `implementation` as a display/conceptual name for the authoritative
  tiny lane; `tiny` remains the persisted canonical lane id in M6.13 v0
- add lane metadata and a lane registry without changing tiny behavior
- prove mirror-lane identity/bundles as non-authoritative before any
  deliberation write path
- emit lane-attempt telemetry needed for future calibration economics routing,
  while keeping M6.13 v0 routing rule-based
- defer broad refactoring until M6.16, except for narrow M6.14 repairs when
  the same reproducible mew-first failure class blocks M6.13 twice
- bind deliberation attempts to explicit model, effort, timeout, budget, and
  schema contracts
- allow deliberation only for reviewer-commanded or eligible semantic blockers,
  with fallback to tiny on refusal, timeout, budget, validation, or review
  failure
- convert useful deliberation output into reviewed M6.9 reasoning traces,
  never raw transcript storage

Current M6.13 chain:

`M6.13 -> additive lane foundation -> tiny compatibility plus mirror-lane proof`

Current M6.13 evidence:

- M6.13.2 decision memory saved at
  `.mew/memory/private/project/20260426T081045Z-decision-m6-13-2-side-project-dogfood-telemetry.md`.
  It records the side-project dogfood reporting flow: side-project task ->
  mew-first implementer -> Codex CLI/Codex reviewer/comparator/verifier ->
  tests/proof -> JSONL ledger append -> commit on success or M6.14 repair on
  structural failure. It also records the non-goals: no side-project
  implementation, EV routing, automatic Codex CLI integration, implementation
  lane refactor, or M6.13 close in this slice.
- M6.13.2 implementation landed a side-project dogfood ledger/report surface:
  `src/mew/side_project_dogfood.py`, `mew side-dogfood template`,
  `mew side-dogfood append`, and `mew side-dogfood report`. The default
  ledger path is `proof-artifacts/side_project_dogfood_ledger.jsonl`. This is
  ready for the first side-project dogfood task; side-project Codex CLI should
  normally be recorded as `operator` when it drives mew from the side-project
  directory. Direct Codex CLI implementation must be recorded via
  `codex_cli_used_as` as `implementer` or `fallback` and does not count as
  mew-first autonomy credit.

- Task `#647` / session `#634` landed the first additive WorkTodo lane field
  on `_normalize_active_work_todo`: missing or empty lane normalizes to
  `tiny`, while explicit strings such as `mirror` and unknown future lane names
  are preserved. Existing active-todo id/status/source/attempts/error behavior
  remains unchanged.
- Validation passed for the #647 source/test slice:
  `uv run pytest -q tests/test_work_session.py -k 'active_work_todo or lane' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`.
- The current mirror-lane replay slice keeps tiny on the legacy replay path
  while writing non-tiny lane bundles under
  `.mew/replays/work-loop/<date>/session-<id>/lane-<name>/todo-<id>/...`.
  Replay metadata now records additive lane reconstruction fields including
  `lane_decision`, `lane_authoritative`, `lane_layout`,
  `lane_write_capable`, and `lane_fallback_lane`.
- The write-ready shadow bridge now carries `active_work_todo.lane` into the
  patch-draft compiler replay environment, so a mirror-lane work todo can
  record a non-authoritative lane-scoped bundle while leaving the outer
  model-selected action unchanged. A replay-writer exception in the mirror
  path is captured as compiler observation data and does not replace or fail
  the outer action.
- The current deliberation preflight slice added `src/mew/deliberation.py` as
  pure M6.13 Phase 2 substrate: it normalizes requested/effective model
  bindings, classifies blocker-code escalation eligibility, reserves per-task
  attempt budget, builds cost/fallback events, appends deliberation attempts
  and cost events to session trace state, exposes those fields through
  `build_work_session_resume`, and validates the v1 `deliberation_result`
  contract before any raw model output can influence the tiny lane.
- Mirror-lane validation passed:
  `uv run pytest -q tests/test_work_replay.py -k "lane or path_shape" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "lane_metadata" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "m6_11_replay_lane_metadata_defaults_and_counts or m6_11_calibration" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "shadow_bridge_mirror_lane or shadow_bridge_records_validated_replay" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "patch_draft_compiler_shadow_bridge" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py tests/test_proof_summary.py --no-testmon`,
  and
  `uv run ruff check src/mew/work_loop.py src/mew/work_replay.py tests/test_work_session.py tests/test_work_replay.py tests/test_proof_summary.py`.
- Mew-first accounting: `product_progress_supervisor_rescue`, not autonomy
  credit. Mew reached the correct lane-normalization direction after reviewer
  steer, but stalled in partial-apply/rollback plus cached-window recovery
  before the final source repair. Treat another repeat as an M6.14 repair
  signal.
- Task `#648` / session `#635` landed the first data-only lane registry v0.
  `src/mew/work_lanes.py` now lists supported lanes `tiny`, `mirror`, and
  `deliberation`; `tiny` is authoritative/write-capable with legacy layout,
  `mirror` is non-authoritative lane-scoped mirror evidence, and
  `deliberation` is non-authoritative lane-scoped shadow evidence requiring
  explicit model binding. Missing or empty lane lookups fall back to `tiny`;
  unknown lane strings return an unsupported view while preserving the original
  WorkTodo lane value.
- #648 validation passed: work-session focused verifier
  `uv run pytest -q tests/test_work_lanes.py tests/test_work_session.py -k 'work_lane or active_work_todo_lane' --no-testmon`,
  `uv run python -m unittest tests.test_work_lanes`,
  `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py`, and
  `git diff --check`.
- #648 mew-first accounting: `success_mew_first_after_reviewer_rejection`.
  The reviewer rejected the first role-enum draft and steered the exact
  authoritative/mirror/shadow contract, but mew authored and verified the final
  source/test patch. No supervisor product rescue was used.
- Task `#649` / session `#636` landed the first data-only lane-attempt
  telemetry v0 helper. `build_lane_attempt_event()` emits the minimum
  `lane_attempt` event shape from the resident architecture design doc, maps
  the persisted `tiny` lane to display name `implementation`, keeps unknown
  lanes unsupported while preserving their string, and leaves routing,
  mirror execution, EV selection, and broad refactoring untouched. This was a
  mew-first implementation: after one transient model timeout and restarted
  live run, mew produced the paired source/test patch and the supervisor
  approved without rescue edits. Validation covered focused tests.
- #649 validation passed: work-session focused verifier
  `uv run pytest -q tests/test_work_lanes.py --no-testmon`,
  `uv run python -m unittest tests.test_work_lanes`,
  `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py`, and
  `git diff --check`.
- #649 same-surface audit found only `src/mew/work_lanes.py`,
  `tests/test_work_lanes.py`, and the architecture design doc referencing the
  new lane-attempt surface, so no production call sites need migration yet.
- Task `#650` / session `#637` exposed an M6.14 repair-class blocker before
  replay metadata could proceed: after `missing_required_terms`, mew produced
  rejected dry-run tools `#5890`/`#5891` that treated `required_terms` as
  product replay metadata and invented schema. Task `#651` records the bounded
  M6.14 repair episode for this `synthetic_schema_substitution` failure.
- Task `#651` landed the substrate repair: write-ready prompts now define
  `task_goal.required_terms` as semantic anchors, not fields or metadata keys
  to persist, and instruct the draft lane to return `task_goal_term_missing`
  rather than inventing schema when anchors cannot fit naturally. This is loop
  substrate surgery, not mew-first product autonomy credit. Retry target remains
  task `#650`.
- #651 validation passed:
  `uv run pytest -q tests/test_work_session.py -k "required_terms or tiny_write_ready_draft_prompt" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "write_ready" --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- While retrying `#650`, verifier baseline exposed one more M6.14 substrate
  repair: generic `fast-path` wording in the replay-harness task description
  was extracted as a required term and made the clean replay compiler fixture
  return `patch_blocker`. Task `#652` added `fast-path` to the generic
  required-term stopword set and covered this with a focused work-session test.
  This was direct Codex substrate repair, not mew-first autonomy credit.
- Task `#650` / session `#638` then completed the replay metadata slice
  mew-first after repair. Replay bundle metadata now derives lane provenance
  via `get_work_todo_lane_view()` and records `lane`, `lane_role`,
  `lane_schema_version=1`, and `lane_attempt_id`; missing/empty lanes resolve
  to `tiny` with authoritative role, while explicit lanes use registry roles.
  The reviewer steer was needed: the reviewer rejected the first lane-only
  draft, repaired the verifier substrate, then approved the mew-authored
  source/test patch without rescue edits. Validation covered focused tests.
- #650/#652 validation passed:
  `uv run pytest -q tests/test_work_replay.py --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "write_ready or required_terms" --no-testmon`,
  `uv run ruff check src/mew/work_replay.py src/mew/work_loop.py tests/test_work_replay.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#653` / session `#639` exposed another bounded M6.14 repair-class
  blocker while attempting the proof-summary read/report lane slice: after
  complete cached windows existed, the model requested a broad `read_file` on a
  path whose latest same-path `search_text` had zero matches, and the
  broad-read guard failed the step instead of coercing to the known cached
  line-window. Task `#654` repaired that loop substrate by attaching safe
  replacement parameters to the broad-read guard and executing the narrowed
  cached-window read when available. This is direct Codex substrate repair, not
  mew-first autonomy credit; retry target remains task `#653`.
- #654 validation passed:
  `uv run pytest -q tests/test_work_session.py -k "broad_read_after_search_miss_guard or write_ready" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "broad_read_after_search_miss_guard_reuses_latest_same_path_window or work_session_runs_read_only_tools_and_journals_results" --no-testmon`,
  `uv run ruff check src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`, and
  `git diff --check`.
- While retrying `#653`, required-term validation exposed one more bounded
  M6.14 repair: natural-language task wording used `proof-summary`, while the
  scoped Python source and tests naturally use `proof_summary`. Task `#655`
  repaired required-term validation to accept hyphen/underscore spelling
  variants without weakening genuinely missing anchors. This is direct Codex
  substrate repair, not mew-first autonomy credit; retry target remains
  task `#653`.
- #655 validation passed:
  `uv run pytest -q tests/test_patch_draft.py -k "required_term or task_goal_terms" --no-testmon`,
  `uv run pytest -q tests/test_patch_draft.py --no-testmon`,
  `uv run ruff check src/mew/patch_draft.py tests/test_patch_draft.py`, and
  `git diff --check`.
- Task `#653` / session `#641` then completed the proof-summary read/report
  lane slice mew-first after the bounded M6.14 fixes. Replay bundle summaries
  now expose lane metadata via `get_work_lane_view()`; legacy missing/empty
  lanes default to `tiny` with authoritative role; explicit `mirror` lanes
  report mirror metadata; and M6.11 replay calibration top-level/cohort
  summaries now include additive `lane_counts` without changing bundle type
  counts, thresholds, or classification. The reviewer steer was needed after
  the restart, but the final source/test patch landed without rescue edits:
  mew authored the source/test patch and Codex only hydrated
  cached windows, approved the dry-run patch, and verified it. Verification
  passed for the work-session pytest and ruff commands below.
- #653 validation passed:
  work-session verifier `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run ruff check src/mew/proof_summary.py tests/test_proof_summary.py`, and
  `git diff --check`.
- Resident architecture framing was recorded in
  `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`. Claude Ultra and
  Codex Ultra both reviewed the direction as `approve_with_changes`; the
  accepted constraints are that M6.13 keeps its current close gate, `tiny`
  remains the persisted canonical lane id, `implementation` is display
  terminology only, calibration economics starts as telemetry, EV routing is
  future work, and the meta loop is deferred.

Current M6.8.5 close evidence:

- Task `#639` / session `#627` landed the first read-only selector
  intelligence signal after bounded M6.14 substrate repair. Non-blocked
  `mew task propose-next` proposals now attach `failure_cluster_reason` from
  `summarize_calibration_ledger("proof-artifacts/m6_11_calibration_ledger.jsonl")`
  when the existing M6.12 calibration ledger has non-positive archetype counts.
  Missing-ledger and blocked proposal paths leave the existing field empty; the
  M6.8 approval/no-dispatch/governance contract is unchanged.
- #639 mew-first note: sessions `#625`/`#626` first failed with rejected
  synthetic-schema/hard-coded metadata patches. M6.14 repair task `#640`
  landed `synthetic_schema_substitution` rejection-frontier classification in
  commit `9c2c1d1`, then #627 retried #639 and produced the accepted source/test
  patch. Count this as `success_after_substrate_fix`; Codex reviewer correction
  was limited to rejecting bad drafts and steering the `CalibrationSummary.counts`
  API, not authoring the product patch.
- #639 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py
  tests/test_work_session.py`, and `git diff --check`.
- #639 dogfood evidence: `mew task propose-next 639 --candidate-task-id 641
  --record --json` produced `failure_cluster_reason:
  preflight_gap:9 from proof-artifacts/m6_11_calibration_ledger.jsonl` while
  keeping `approval_required=true`, `blocked=false`, and no auto-dispatch.
- Task `#641` / session `#629` added the second read-only selector
  intelligence signal. Non-blocked `mew task propose-next` proposals now attach
  bounded `preference_signal_refs` from existing selector reviewer history
  (`reviewer_decision` + `reviewer_reason`) so the next reviewer sees compact
  preference evidence without opening raw state.
- #641 mew-first note: session `#628` first drifted toward the previous
  `failure_cluster_reason` target, and #629 needed reviewer steering for a
  stale `src/mew/task_selector.py` path plus one rejected non-ASCII truncation
  draft. The final paired source/test patch was authored by mew and applied
  after reviewer approval; count this as `success_mew_first_with_reviewer_revisions`.
- #641 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- #641 dogfood evidence: `mew task propose-next 641 --candidate-task-id 642
  --record --json` produced both `failure_cluster_reason` and three
  `preference_signal_refs`; proposal `#18` was approved and executed to
  supervised handoff `#9` for task `#642`. A first candidate title containing a
  forbidden governance surface word was correctly blocked before retitling.
- Task `#642` / session `#630` added the third read-only selector intelligence
  signal. Non-blocked `mew task propose-next` proposals now attach bounded
  calibration/evaluator evidence rows as `memory_signal_refs` from the real
  `summarize_calibration_ledger("proof-artifacts/m6_11_calibration_ledger.jsonl")`
  output. Missing evidence leaves `memory_signal_refs` empty; blocked proposals
  still skip signal attachment.
- #642 mew-first note: #630 initially spent too many read turns and needed a
  reviewer steer to draft from cached anchors, but the final paired source/test
  patch was authored by mew and applied after approval. Count this as
  `success_mew_first_with_reviewer_steer`; no supervisor product edit.
- #642 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- #642 dogfood evidence: `mew task propose-next 642 --candidate-task-id 643
  --record --json` produced `memory_signal_refs`, `failure_cluster_reason`, and
  `preference_signal_refs`; proposal `#19` was approved and executed to
  supervised handoff `#10` for task `#643`.
- Task `#643` / session `#631` added the fourth read-only selector intelligence
  signal. Non-blocked `mew task propose-next` proposals now attach bounded
  `selector_habit_template` entries into existing `memory_signal_refs` from
  real `selector_proposals`, `selector_execution_attempts`, and tasks, for both
  non-record and `--record` output. Missing repeated evidence leaves
  `memory_signal_refs` empty; no new top-level proposal field was added.
- #643 mew-first note: #631 first drifted into a rejected
  `selector_governance_tags` synthetic schema, then produced a close but
  record-only habit patch. M6.14 repair task `#644` landed write-ready recovery
  cues in commit `161180b`, so explicit `read_file` / `first read` /
  `exact source text` recovery guidance triggered the needed exact read instead
  of another wait. The retried paired source/test patch was authored by mew and
  applied after reviewer approval. Count this as `success_after_substrate_fix`;
  no supervisor product patch.
- #643 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#645` / session `#632` implemented the M6.8.5 habit compilation v0
  proof slice. Selector habit evidence now emits a reviewer-visible
  `compiled_habit_runner_candidate` entry in existing `memory_signal_refs` only
  when a repeated task template has approved handoff evidence and the historical
  `next_command` matches the deterministic runner command shape for that source
  task. Command mismatches fall back to the normal selector proposal with no
  compiled candidate ref; approval-required/no-dispatch behavior is unchanged.
- #645 mew-first note: #632 was mew-authored and needed no supervisor product
  rescue. The reviewer approved one paired source/test dry-run patch and then
  asked mew to finish after verification. Count this as `success_mew_first`.
- #645 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#646` / session `#633` closed the preference draft-preparation proof
  slice. Work-session resume and THINK prompt context now surface bounded
  `preference_signal_refs` from the approved selector proposal that selected the
  current task, with `approved_selector_proposal` provenance and selector
  proposal/task ids. Missing preference refs, unapproved selector records, or
  wrong-task records produce an empty field; `memory_signal_refs` are not used
  as a fallback.
- #646 mew-first note: #633 first produced a close source/test dry-run that
  incorrectly fell back to `memory_signal_refs`. The reviewer rejected it, and
  mew retried with a paired source/test patch that removed the fallback and
  added a THINK-prompt assertion. Count this as
  `success_mew_first_with_reviewer_revision`; no supervisor product patch.
- #646 validation passed: focused
  `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt' --no-testmon`,
  exact-timeout rerun
  `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt or hard_timeout_without_retries' --no-testmon`,
  full `uv run pytest -q tests/test_work_session.py --no-testmon` on rerun,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. The first full work-session run had one transient
  hard-timeout assertion failure; the exact failing test and full suite passed
  immediately on rerun.

Closed M6.8 evidence:

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
- Task `#629` / session `#614` exposed the proposal helper as the read-only
  `mew task propose-next` CLI. It supports JSON and human output, keeps
  `approval_required=true`, reports governance-blocked candidates, and does not
  dispatch or mutate agent runs.
- #629 mew-first note: the first implementation verifier failed on a test
  expectation case mismatch (`roadmap` vs `ROADMAP_STATUS.md`). Reviewer steered
  mew to preserve product behavior and repair the test; mew re-applied the CLI
  parser and the paired test repair with no supervisor product edit.
- #629 validation passed: `uv run pytest -q tests/test_commands.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/commands.py src/mew/cli.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#630` / session `#615` repaired a selector scope-fence
  false-positive found by dogfooding: M6.8 implementation tasks that merely
  describe governance/status guardrails were being blocked as if they targeted
  those surfaces. Selector target checks now inspect task title and explicit
  `scope.target_paths`, not description/notes. Explicit forbidden titles and
  target paths still block.
- #630 validation passed: `uv run pytest -q tests/test_tasks.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/tasks.py tests/test_tasks.py`, and
  `git diff --check`.
- Starting task `#631` exposed a loop-substrate false negative rather than a
  product-code failure: sessions `#616`/`#617` repeatedly stopped with
  `cached_window_incomplete` because write-ready structural preflight could not
  narrow a complete indented `build_parser()` parser-registration fragment in
  `src/mew/cli.py`. This was repaired as M6.14 substrate work, not counted as
  #631 autonomy credit. The structural gate now accepts complete indented
  simple-statement sequences such as argparse registration blocks while still
  rejecting one-line orphaned body fragments; the observed `cli.py:1707-1995`
  window narrows to `1707-1960`.
- #631 substrate repair validation passed: `uv run pytest -q
  tests/test_work_session.py -k 'write_ready' --no-testmon`, `uv run pytest -q
  tests/test_work_session.py tests/test_commands.py --no-testmon`, `uv run
  ruff check src/mew/work_loop.py tests/test_work_session.py`, and `git diff
  --check`.
- Task `#631` / session `#617` then landed the durable selector-proposal
  ledger slice mew-first after one reviewer rejection. `mew task propose-next
  --record` now persists `selector_proposals` records without dispatching:
  `id`, `previous_task_id`, `proposed_task_id`, original `proposal`, `status`
  (`proposed` or `blocked`), `created_at`, and `updated_at`. The slice
  intentionally does not add approve/reject commands or chained execution.
- #631 mew-first note: the first proposed patch only added a cosmetic
  `selector-proposal` output label and was rejected. After reviewer steer and
  one model-timeout retry, mew produced the accepted source/CLI/test batch; no
  supervisor product edit was used.
- #631 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_commands.py tests/test_tasks.py
  tests/test_work_session.py -k 'task_propose_next or write_ready'
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Dogfooding `mew task propose-next 631 --record --json` immediately after
  #631 recorded a blocked proposal for stale governance task `#388`, proving
  the scope fence but also exposing that automatic selection could get stuck on
  the first blocked ready candidate.
- Task `#632` / session `#618` repaired that selector behavior mew-first.
  Automatic `task propose-next` now scans ready/todo coding tasks, builds each
  proposal, skips governance-blocked proposals, and returns the first unblocked
  candidate; explicit `--candidate-task-id` still returns and records blocked
  proposals for reviewer visibility.
- #632 mew-first note: the first patch only added comments/assertions around
  existing explicit-candidate behavior and was rejected. After reviewer steer,
  mew produced the accepted source/test patch with no supervisor product edit.
- #632 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_commands.py
  tests/test_work_session.py -k 'task_propose_next or write_ready'
  --no-testmon`, `uv run ruff check src/mew/commands.py
  tests/test_commands.py`, and `git diff --check`.
- Post-#632 dogfood `mew task propose-next 632 --record --json` skipped stale
  governance task `#388` and returned `no safe selector candidate found`
  instead of proposing the blocked task.
- Task `#633` / session `#619` landed reviewer-visible selector approval and
  rejection recording mew-first. `mew task approve-proposal <id>` and `mew task
  reject-proposal <id>` update existing `selector_proposals` records with
  `reviewer_decision`, `reviewer_reason`, `reviewed_at`, `updated_at`, and a
  terminal `status` without dispatching the proposed task or mutating tasks.
- #633 mew-first note: two proposed patches were rejected before approval. The
  first bypassed the CLI by calling command helpers directly from tests. The
  second added CLI wiring but allowed approving blocked governance proposals,
  which would weaken the M6.8 scope fence. After reviewer steer, mew produced
  the accepted CLI/source/test patch with no supervisor product edit.
- #633 scope-fence dogfood: `mew task approve-proposal 4 --reason ... --json`
  recorded reviewer approval for the safe `#632 -> #633` proposal, `mew task
  approve-proposal 1 --reason ... --json` rejected approval of the blocked
  governance proposal, and `mew task reject-proposal 1 --reason ... --json`
  recorded the reviewer rejection for the blocked candidate.
- #633 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#634` / session `#620` landed the first guarded execution attempt
  slice mew-first. `mew task execute-proposal <id>` now rejects missing,
  unapproved, and blocked selector proposals, persists
  `selector_execution_attempts` audit records with `proposal_id`,
  `proposed_task_id`, `status=rejected`, `blocked_reason`,
  `governance_violation=true`, and `timestamp`, and does not mutate tasks or
  dispatch agent runs.
- #634 dogfood: `mew task execute-proposal 5 --json` rejected/logged blocked
  proposal execution, `mew task propose-next 634 --candidate-task-id 635
  --record --json` created proposal `#7`, `mew task execute-proposal 7 --json`
  rejected/logged the unapproved execution attempt, and after reviewer approval
  `mew task execute-proposal 7 --json` returned the safe v0 message that
  approved execution handoff is not implemented and no task was dispatched.
- #634 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#635` / session `#621` landed the approved selector handoff slice
  mew-first. Approved `mew task execute-proposal <id>` now persists a
  `selector_execution_attempts` record with `status=handoff_ready`,
  `proposal_id`, `proposed_task_id`, reviewer approval metadata,
  `next_command`, and `auto_run=false`; it prints the reviewer-visible
  `./mew work <task-id> --start-session` handoff command and still does not
  dispatch model work or mutate tasks.
- #635 mew-first note: one patch was rejected for omitting the required
  `next_command` handoff evidence, and a later edit attempt hit the known
  duplicated-adjacent-context guard. After reviewer steer, mew produced the
  accepted source/test pair with no supervisor product edit.
- #635 dogfood: `mew task execute-proposal 7 --json` recorded
  `status=handoff_ready`, `proposed_task_id=635`, the original reviewer
  approval metadata, `next_command="./mew work 635 --start-session"`, and
  `auto_run=false`.
- #635 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#636` / session `#622` continued the approved handoff chain from
  proposal `#9`. The reviewer approved `#635 -> #636`, `execute-proposal`
  recorded `handoff_ready`, and mew implemented the read-only
  `mew task selector-status` CLI as the next bounded task.
- #636 adds a selector proof status summary for close-gate review without
  dispatching work or mutating state: counts for `selector_proposals`,
  `selector_execution_attempts`, `approved_handoffs`, `rejected_attempts`, and
  `blocked_proposals`, plus the latest proposal and execution attempt.
- #636 dogfood: `mew task selector-status --json` reported the live M6.8 chain
  state, including `approved_handoffs=2`, `rejected_attempts=2`, and latest
  handoff attempt `#4` for proposal `#9 -> task #636`.
- #636 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#637` / session `#623` continued the auto-selected handoff chain from
  proposal `#11`. The reviewer approved `#636 -> #637`, `execute-proposal`
  recorded `handoff_ready`, and mew extended `mew task selector-status` with a
  joined `recent_handoffs` list for close-gate auditing.
- #637 exposes each recent approved handoff with `proposal_id`,
  `previous_task_id`, `proposed_task_id`, `selector_reason`, reviewer metadata,
  `next_command`, and timestamp. This keeps proof evidence read-only and avoids
  M6.8.5 selector intelligence or dispatch behavior.
- #637 dogfood: `mew task selector-status --json` reported
  `approved_handoffs=3`, `rejected_attempts=2`, and recent handoffs for
  proposal `#11` (`#636 -> #637`), proposal `#9` (`#635 -> #636`), and
  proposal `#7` (`#634 -> #635`).
- #637 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#638` / session `#624` added the close-gate proof summary after the
  reviewer-approved `#637 -> #638` auto-selected handoff. `mew task
  selector-status --json` now derives `proof_summary` from `recent_handoffs`:
  total recent handoffs, contiguous chain length, latest task id, oldest task
  id, and `has_three_consecutive_handoffs`.
- #638 dogfood: live `selector-status --json` reported
  `approved_handoffs=4`, `rejected_attempts=2`, `blocked_proposals=6`,
  `proof_summary.contiguous_chain_length=4`, and
  `has_three_consecutive_handoffs=true`. The latest three auto-selected links
  are `#635 -> #636`, `#636 -> #637`, and `#637 -> #638`.
- #638 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.

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

M6.8 close result: **done**. The recorded audit is
`docs/M6_8_CLOSE_GATE_AUDIT_2026-04-26.md`.

M6.8.5 close result: **done**. The recorded audit is
`docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`.

## Next Milestone

Current scheduled milestone: **M6.13 High-Effort Deliberation Lane**.

M6.13 starts now because the M6.8.5 deferral trigger has fired. The first slice
should be additive and low-risk:

- introduce lane state/registry with `tiny` as the legacy default
- prove old sessions and replay bundles normalize to tiny without migration
- prove a mirror lane can record non-authoritative lane identity/bundles
  without changing tiny-lane behavior
- add lane-attempt telemetry fields that future M6.16/M6.17 work can use for
  calibration economics, without claiming EV routing in M6.13 v0
- add M6.13.2 side-project implementation dogfood telemetry before launching
  the side-project dogfood lane, so the first external implementation attempts
  produce structured M6.16 evidence instead of only reply/chat history
  (**landed in M6.13.2 v0**)

Planned future milestones:

- **M6.16 Codex-Grade Implementation Lane**: use M6.13 lane-attempt telemetry
  and the M6.13.2 side-project dogfood ledger to harden the authoritative
  implementation lane. Broad refactoring belongs here only when a measured
  bottleneck or recurring failure class is named with before/after proof.
- **M6.17 Resident Meta Loop / Lane Chooser**: add a reviewer-gated resident
  supervisor after implementation-lane reliability and lane boundaries are
  proven.

## Post-Close Deferred Ledger

| Origin | Deferred Item | Trigger / Timing | Recommended Home | Blocks Current? |
|---|---|---|---|---|
| M6.9 Phase 4 | Failure-clustered curriculum | Closed by M6.8.5 task `#639` | M6.8.5 done | No |
| M6.9 Phase 4 | Preference-store retrieval from reviewer diffs | Closed by M6.8.5 tasks `#641` and `#646` | M6.8.5 done | No |
| M6.9 Phase 4 | Habit compilation v0 | Closed by M6.8.5 tasks `#643` and `#645` | M6.8.5 done | No |
| M6.10 | Explorer D1 / read-only exploration reducer | Only if M6.8 or M6.8.5 evidence shows read-only exploration churn is a measured blocker again | M6.10 follow-up or M6.8.5 helper slice | No |
| M6.11 | Full concurrent / streaming executor | After selector/curriculum proof shows measured idle or concurrency pain while loop attribution is stable | Later execution milestone | No |
| M6.11 | MemoryExplore protocol full freeze/replay and agentization | Keep read-only provider for now; full agentization waits until a second planner will not obscure loop failures | M10 or later memory/explorer milestone | No |
| M6.11 | Provider-specific prompt caching | Only when provider telemetry shows cache/latency as a direct blocker | M6.13 or later acceleration slice | No |
| M6.12 | Governance/evaluator/adversarial wiring | First use M6.12 as read-only selector input in M6.8.5; automatic governance wiring needs a later explicit safety milestone | M6.8.5 read-only, later governance milestone | No |
| Resident architecture | Codex-grade implementation lane hardening | After M6.13 emits enough lane-attempt telemetry to identify implementation-lane bottlenecks | M6.16 | No |
| Resident architecture | Resident meta loop / lane chooser | After M6.13 lane boundaries and M6.16 implementation-lane reliability are proven | M6.17 | No |
| Refactor policy | Broad work-loop/work-session refactoring | Defer until M6.16 unless the same reproducible failure class blocks M6.13 mew-first work twice and fits M6.14 repair | M6.16 or M6.14 repair | No |

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

`M6.13 -> deliberation Phase 2 -> work-loop call wiring with explicit binding/budget/fallback`

Acceptable near-term work:

- add mirror-lane recording as non-authoritative evidence only after tiny
  compatibility is proven
- wire the deliberation preflight primitives into the work loop only after the
  model-call boundary can preserve tiny fallback on timeout/refusal/non-schema
- prove old sessions and existing replay bundles with absent lane metadata keep
  tiny-compatible behavior at their read/report boundary
- wire the minimal lane-attempt telemetry helper into future lane attempts only
  when that slice already needs a lane attempt record; do not add EV routing

Non-goals for the next session:

- autonomous execution or auto-merge
- full concurrent executor
- memory explore agentization
- provider-specific prompt caching
- side-project dogfood; it is user-controlled and outside the current mainline
  M6.13 task selection unless a reproducible core blocker is reported
- M7 inbound-signal work
- raw deliberation transcript storage
- broad refactors not tied to lane telemetry or a repeated M6.14 repair-class
  failure
- broad refactors or polish not mapped to the M6.13 gate

## Latest Validation

Latest M6.13 source/test validation:

- M6.13 deliberation preflight/budget primitive slice:
  `uv run pytest -q tests/test_deliberation.py --no-testmon`,
  `uv run pytest -q tests/test_deliberation.py tests/test_work_session.py -k "deliberation" --no-testmon`,
  `uv run pytest -q tests/test_deliberation.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "deliberation or active_work_todo or lane" --no-testmon`,
  and
  `uv run ruff check src/mew/deliberation.py src/mew/work_session.py tests/test_deliberation.py tests/test_work_session.py`
  passed.
- M6.13 mirror lane-scoped replay bundle slice:
  `uv run pytest -q tests/test_work_replay.py -k "lane or path_shape" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "lane_metadata" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "shadow_bridge_mirror_lane or shadow_bridge_records_validated_replay" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "patch_draft_compiler_shadow_bridge" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py tests/test_proof_summary.py --no-testmon`,
  and
  `uv run ruff check src/mew/work_loop.py src/mew/work_replay.py tests/test_work_session.py tests/test_work_replay.py tests/test_proof_summary.py`
  passed.
- M6.13.2 side-project dogfood telemetry v0:
  `uv run pytest -q tests/test_side_project_dogfood.py --no-testmon` passed,
  `uv run ruff check src/mew/side_project_dogfood.py src/mew/commands.py src/mew/cli.py tests/test_side_project_dogfood.py`
  passed, `./mew side-dogfood template` printed the appendable schema, and
  `./mew side-dogfood report --json` returned an empty valid report for the
  default ledger.
- task `#650` / session `#638`: replay metadata lane provenance/defaulting
- task `#652`: M6.14 fast-path required-term stopword repair
- `uv run pytest -q tests/test_work_replay.py --no-testmon` passed
- `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py -k "write_ready or required_terms" --no-testmon`
  passed
- `uv run ruff check src/mew/work_replay.py src/mew/work_loop.py tests/test_work_replay.py tests/test_work_session.py`
  passed
- `git diff --check` passed
- task `#651`: M6.14 repair for #650 required-terms synthetic schema
- `uv run pytest -q tests/test_work_session.py -k "required_terms or tiny_write_ready_draft_prompt" --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py -k "write_ready" --no-testmon`
  passed
- `uv run ruff check src/mew/work_loop.py tests/test_work_session.py` passed
- `git diff --check` passed
- task `#649` / session `#636`: data-only lane-attempt telemetry v0
- `uv run pytest -q tests/test_work_lanes.py --no-testmon` passed
- `uv run python -m unittest tests.test_work_lanes` passed
- `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py` passed
- `git diff --check` passed
- task `#648` / session `#635`: data-only lane registry v0
- `uv run pytest -q tests/test_work_lanes.py tests/test_work_session.py -k 'work_lane or active_work_todo_lane' --no-testmon`
  passed
- `uv run python -m unittest tests.test_work_lanes` passed
- `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py` passed
- `git diff --check` passed
- task `#647` / session `#634`: additive WorkTodo lane normalization
- `uv run pytest -q tests/test_work_session.py -k 'active_work_todo or lane' --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py --no-testmon` passed
- `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
  passed
- `git diff --check` passed

Latest milestone-close validation:

- M6.8.5 close audit passed via `docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`
- detailed pre-compression `ROADMAP_STATUS.md` was archived to
  `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Behavioral validation for the latest source/test changes is listed above under
tasks `#639` through `#646`; this closeout edit is documentation/status only.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action
  here.
- When a milestone closes, add or update a close-gate audit in `docs/` and
  summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions
  override the active milestone decision in this file.
