# Mew Roadmap Status

Last updated: 2026-04-27

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
| 6.13 High-Effort Deliberation Lane | `done` | Close gate passed via `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`; deterministic and live gpt-5.5 internalization proofs apply and verify the later tiny solve through the normal work path. |
| 6.14 Mew-First Failure Repair Gate | `done` | Repair ledger covers known mew-first substrate failures; future repairs append here. |
| 6.15 Verified Closeout Redraft Repair | `merged_into_6.14` | Historical episode folded into M6.14. |
| 6.16 Codex-Grade Implementation Lane | `done` | Close gate passed via `docs/M6_16_CLOSE_GATE_AUDIT_2026-04-27.md`; residual first-edit samples feed M6.17/M6.14 rather than keeping M6.16 open. |
| 6.17 Resident Meta Loop / Lane Chooser | `done` | Close gate passed via `docs/M6_17_CLOSE_GATE_AUDIT_2026-04-27.md`; v0 remains reviewer-gated. |
| 6.18 Implementation Failure Diagnosis Gate | `done` | Close gate passed via `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md`; M7+ dogfood now routes failures through diagnosis before M6.14 repair. |
| 6.19 Terminal-Bench Compatibility | `in_progress` | Active milestone: make mew runnable under Harbor / Terminal-Bench and produce comparable smoke-subset artifacts. |
| 6.20 Terminal-Bench Driven Implement-Lane Debugging | `not_started` | Use Terminal-Bench scores and failure cohorts to drive implementation-lane repair after M6.19 creates the harness. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision on 2026-04-27 while Terminal-Bench compatibility/debugging is added first; existing M7 signal work is preserved. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.19 Terminal-Bench Compatibility**.

Why M6.19 is active:

- User decision on 2026-04-27: pause M7 and add Terminal-Bench milestones
  before continuing the senses roadmap.
- The implementation lane needs an external, comparable benchmark. Internal
  mew-first dogfood is valuable but can overfit to mew's own repository and
  task style.
- Harbor is the official Terminal-Bench 2.0 harness and already supports
  existing reference agents such as Codex CLI and Claude Code, making it a
  suitable comparison surface for mew.
- M6.18 can now classify mew-first failures, so benchmark failures can become
  diagnosis data rather than free-form anecdotes.

Current M6.19 target:

- make mew runnable as a Harbor / Terminal-Bench custom agent
- run a small Terminal-Bench smoke subset through mew
- run the same subset with at least one reference agent such as Codex CLI or
  Claude Code
- store per-task artifacts with instruction, transcript/work-session summary,
  verifier result, timeout status, and available cost/token data
- keep score optimization out of M6.19; M6.20 owns debug/score improvement

Current M6.19 chain:

`M6.19 -> Harbor custom agent wrapper -> Terminal-Bench smoke artifacts -> comparable baseline`

M7 pending evidence preserved:

- M6.18 close audit `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md` adds the
  required diagnosis route for future M7 dogfood failures:
  polish -> same-task retry, structural -> M6.14 repair, invalid spec -> task
  correction, transient -> retry, ambiguous -> replay/proof collection.

- Existing signal gates, journaling, and RSS/feed surfaces provide foundation,
  but the M7 close proof is not yet present.
- Next work should define the smallest enabled inbound source and proof window,
  then produce or simulate one auditable passive observation.
- Selector proposal `#26` chose task `#682` as the first M7 bounded task with
  lane dispatch, calibration refs, failure cluster, and preference refs. This
  proves the closed M6.17 lane chooser can hand off into M7 without falling
  back to stale paused M6 work.
- Task `#682` completed the first M7 bounded slice. Mew session `#672`
  selected the existing signal source registry as the smallest deterministic
  proof-source surface and added `select_signal_proof_source(state,
  current_time=...)` in `src/mew/signals.py`. The helper is read-only: it
  inspects configured RSS/Atom sources, returns candidate blockers, proof
  metadata, reason-for-use, URL, and remaining budget, and does not fetch,
  record, queue, or save state. Reviewer follow-up fixed zero-budget and
  stale day-window edge cases, preserving source state while refreshing the
  returned budget view. Validation passed: `uv run python -m unittest
  tests.test_signals`, `uv run ruff check src/mew/signals.py
  tests/test_signals.py`, and `git diff --check`. Codex-ultra review
  `019dcc07-6515-71d0-afe0-d280a002c6a9` returned `STATUS: pass`.
- Task `#683` added the first explicit gated non-file signal fetch surface as
  product-progress supervisor rescue after mew session `#673` drifted into
  help/proof-source-only edits. `mew signals fetch <source> [--json]` now uses
  existing `fetch_signal_source` gates and budgets, saves state only after a
  recorded observation, and reports blocked sources without queueing or saving.
  `mew signals proof-source [--json]` exposes the read-only selector from task
  `#682`. Reviewer correction moved budget checking before network access and
  added proof that exhausted budgets do not call the opener. Validation passed:
  `uv run python -m unittest tests.test_signals tests.test_signal_fetch
  tests.test_commands`, `uv run ruff check src/mew/signals.py src/mew/cli.py
  src/mew/commands.py tests/test_signals.py tests/test_signal_fetch.py`, and
  `git diff --check`. Codex-ultra review
  `019dcc19-8fa5-72c3-b88c-7030398e3cc1` initially failed the pre-network
  budget gate, then passed after the fix.
- Task `#684` added the first deterministic passive surface for queued inbound
  signal evidence. A `signal_observed` event now produces one unread
  reviewer-visible `send_message` that says mew noticed but did not act,
  includes source, summary, `reason_for_use`, and an explicit
  `./mew signals disable <source>` command, and does not mutate tasks or
  roadmap state. Mew session `#674` first drifted into reflex-observation
  metadata, then produced the core signal path after reviewer steer; supervisor
  cleanup removed residual wrong-target reflex changes. Count as mixed/product
  progress after steer, not clean autonomy credit. Validation passed:
  `uv run python -m unittest tests.test_commands tests.test_autonomy
  tests.test_signals tests.test_signal_fetch`, `uv run ruff check
  src/mew/agent.py tests/test_autonomy.py`, and `git diff --check`.
  Codex-ultra review `019dcc36-658f-72b0-8371-f24eae6a863e` returned
  `STATUS: pass`.
- Runtime proof `2026-04-27 09:00 JST`: enabled gated non-file RSS source
  `hn` with daily budget `1`, selected it through `mew signals proof-source`,
  fetched one HN RSS item through `mew signals fetch hn --json`, and processed
  the queued event with `mew run --once --echo-outbox`. The runtime produced
  outbox `#156`: `signal-observed noticed, not acted`, with source `hn`,
  fetched summary, `reason_for_use`, and disable command
  `./mew signals disable hn`. This proves the immediate end-to-end M7 path, but
  the real-day useful-observation gate remains open until the observation
  survives an intended passive proof window without spam.
- Task `#685` added the first M7 no-spam guard. `record_signal_observation`
  now suppresses duplicates in the current budget window before budget
  consumption and before queueing `signal_observed`: same source/kind/summary
  duplicates and same payload URL duplicates are blocked with
  `duplicate_suppressed`, with payload URL suppression working across sources.
  Mew session `#675` hit `task_goal_term_missing` once, then produced the core
  source/test patch after explicit reviewer steer. Supervisor fixed a
  codex-ultra finding that URL suppression was accidentally source-scoped.
  Validation passed: `uv run python -m unittest tests.test_signals
  tests.test_signal_fetch tests.test_commands`, `uv run ruff check
  src/mew/signals.py tests/test_signals.py`, and `git diff --check`.
  Codex-ultra review `019dcc4b-c380-77e3-acf5-26cd146e7935` failed initially;
  re-review `019dcc4f-1032-7f22-9a6f-d4610bd92e9a` returned `STATUS: pass`.

M6.17 close evidence:

- Task `#679` landed the first reviewer-visible lane-dispatch proposal slice as
  mixed mew-first plus supervisor review-fix evidence. Mew sessions `#668` and
  `#669` produced the initial `lane_dispatch` schema, human formatter exposure,
  and paired tests, but codex-ultra review
  `019dcbbe-33bb-7313-80bd-9ef159edd697` found two acceptance gaps:
  missing `repair_route` and missing `lane_dispatch` on no-candidate selector
  responses. The supervisor applied only those review fixes after the mew work
  session exhausted its failure budget, so this is product progress but not
  clean mew-first autonomy credit. Validation passed:
  `uv run python -m unittest tests.test_tasks tests.test_commands`,
  `uv run ruff check src/mew/tasks.py src/mew/commands.py tests/test_tasks.py tests/test_commands.py`,
  and `git diff --check`. Codex-ultra re-review
  `019dcbc5-974b-7fc3-955b-b2bc869c74c3` returned `STATUS: pass`.
- Task `#680` fixed a reentry drift path where `mew next --kind coding` could
  prefer a stale paused older milestone work session over the active M6.17
  roadmap gate. Mew session `#670` attempted the task first, but produced three
  failing or too-broad drafts, so the final patch is supervisor rescue with no
  mew autonomy credit. The fix parses `Active work: **M6.17 ...**.` from
  `ROADMAP_STATUS.md`, keeps current/non-milestone paused sessions paused, and
  routes older `M6.x` paused sessions to the active native self-improve focus.
  Validation passed: `uv run python -m unittest tests.test_brief`,
  `uv run ruff check src/mew/brief.py tests/test_brief.py`, and
  `git diff --check`. Codex-ultra review
  `019dcbd8-e9bb-7880-9009-7efb152bc3eb` returned `STATUS: pass` after the
  punctuation/current-milestone test gaps were fixed.
- Task `#681` added `next_action` to no-candidate selector proposals so a
  reviewer still sees the active native self-improve path when no safe bounded
  task candidate exists. Mew session `#671` authored the source/test patch and
  verification passed; the supervisor applied a tiny formatter follow-up so
  normal candidate proposals do not show `next_action: null`. After M7 became
  active, `./mew task propose-next 681 --json` returns a blocked no-candidate
  proposal with `lane_dispatch` plus `next_action: ./mew self-improve
  --start-session --focus 'Advance M7 Senses: Inbound Signals'`. Validation
  passed: `uv run python -m unittest
  tests.test_commands`, `uv run ruff check src/mew/commands.py
  tests/test_commands.py`, and `git diff --check`. Codex-ultra review
  `019dcbe9-aae6-75d1-a17d-fb613f1ef4c3` returned `STATUS: pass`.

M6.16 close evidence:

- Task `#656` produced the first M6.16 baseline slice as supervisor-owned
  rescue after failed mew-first attempts. Sessions `#642` and `#643` did not
  land product code: the first draft was label-only, the second helper-only
  draft missed the real metrics shape and CLI surface, the fresh retry hit
  `task_goal_term_missing`, and the final retry drifted into a wrong-target
  calibration parser patch. Count this as `product_progress_supervisor_rescue`
  with no autonomy credit, and as implementation-lane evidence for
  task-goal/substitution fragility after rejection feedback.
- The supervisor-owned baseline surface adds `mew metrics --implementation-lane`
  plus `src/mew/implementation_lane_baseline.py`. It combines
  `summarize_mew_first_calibration`, `build_observation_metrics(kind="coding")`,
  and `summarize_side_project_dogfood`. Current output reports
  `attempts_total=12`, `clean_or_practical_successes=3`,
  `rescue_partial_count=9`, `approval.rejected=13/18`,
  `verifier.failed=0/75`, `first_edit_latency.p95=890.0`, empty
  side-project dogfood rows, and failure classes including
  `task_goal_substitution` and `synthetic_schema_substitution`; after task
  `#659`, the current output reports `attempts_total=15`,
  `clean_or_practical_successes=3`, `rescue_partial_count=12`,
  `approval.rejected=17/22`, `verifier.failed=0/74`, and still recommends
  `mew_first_rescue_partial` as the first bottleneck. Validation passed:
  `uv run pytest -q tests/test_implementation_lane_baseline.py tests/test_mew_first_calibration.py tests/test_metrics.py tests/test_side_project_dogfood.py --no-testmon`,
  `uv run ruff check src/mew/implementation_lane_baseline.py src/mew/commands.py src/mew/cli.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
- Task `#657` landed the first M6.16 bottleneck-reduction slice against
  closeout correctness: `same_surface_audit.status=noted` should not keep a
  work session blocked at finish after the required sibling-surface audit has
  been recorded. This is a supervisor-owned substrate fix, not mew-first
  autonomy credit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'finish_block or same_surface_audit' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_commands.py -k 'finish or same_surface_audit or work_finish' --no-testmon`,
  `uv run ruff check src/mew/commands.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#658` attempted the side-project issue `#2` closeout-completeness
  prompt slice mew-first. Session `#644` produced two rejected paired dry-run
  attempts: the first edited the write-ready tiny draft prompt with
  side-project-specific wording, and the retry still substituted
  side-pj/internal-plumbing anti-schema wording instead of finish/closeout
  evidence. Count this as `product_progress_supervisor_rescue` with no
  autonomy credit. The supervisor-owned bounded patch adds normal
  `build_work_think_prompt` guidance requiring user-facing implementation
  tasks to account for acceptance criteria, README/usage docs, CLI
  stdout/output-file behavior, tests run, and unverified modes before finish.
  Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_commands.py -k 'work_think_prompt or finish or same_surface_audit or work_finish' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#659` is a supervisor-owned M6.16/M6.14 repair slice from the `#658`
  failure evidence. Rejection-frontier classification now preserves explicit
  `task_goal_substitution` before it can be downgraded to
  `missing_focused_verifier` or pairing recovery, and write-ready
  `task_goal.required_terms` filters evidence-source/scope labels such as
  `side-pj`, `side-project`, `implementation-lane`, `prompt-only`, and
  `test-only` while retaining real task anchors such as `user-facing` and
  `output-file`. This is loop-substrate/product progress, not mew-first
  autonomy credit. Focused proof:
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'rejection_frontier or write_ready or work_think_prompt' --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py tests/test_metrics.py -k 'task_goal or implementation_lane or metrics' --no-testmon`,
  `uv run ruff check src/mew/commands.py src/mew/work_loop.py tests/test_work_session.py tests/test_work_rejection_frontier.py`,
  and `git diff --check`.
- Task `#661` is a follow-on supervisor-owned M6.16/M6.14 repair from task
  `#660` / session `#645`: after switching `mew work` to
  `~/.codex/auth.json`, the model got past the expired `auth.pro.json` token
  but write-ready tiny draft blocked on `task_goal_term_missing` for
  `ROADMAP_STATUS`. The repair adds `roadmap_status` to the evidence-source
  required-term stopwords and extends the focused evidence-source test so
  document names do not become mandatory patch anchors. This is substrate
  progress only; retry `#660` mew-first after commit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k evidence_source_scope_terms --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#662` is the next same-family supervisor-owned M6.16/M6.14 repair:
  the retry after `#661` then blocked on verifier command flag `no-testmon`
  as a required task-goal term. The repair adds `no-testmon` to the
  evidence/command stopwords and extends the same focused test. Retry `#660`
  mew-first after commit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k evidence_source_scope_terms --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#660` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#661` and `#662` blocker fixes and
  switching live work to `~/.codex/auth.json`. It deduplicates
  `mew_first.gate_blocking_task_ids` in `mew metrics --implementation-lane`
  while preserving first-seen order, with paired coverage in
  `tests/test_implementation_lane_baseline.py`. Count this as
  `success_after_substrate_fix`: the fresh mew-first session drafted the
  paired source/test patch and the supervisor approved without product rescue
  edits; a reviewer steer was needed only to replace an invalid task verifier
  (`-k "gate_blocking"` selected no tests and exited 5). Valid proof passed:
  `uv run pytest -q tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run pytest -q tests/test_implementation_lane_baseline.py tests/test_metrics.py -k 'implementation_lane or gate_blocking or metrics' --no-testmon`,
  `uv run ruff check src/mew/implementation_lane_baseline.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --mew-first --limit 100 --json`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
  Codex-ultra re-review reported no findings after confirming `#660` is in
  the mew-first attempt window and counted as a practical success.
- The first `#663` retry exposed a new M6.16/M6.14 substrate blocker before
  product editing: after a same-path positive `search_text` on
  `src/mew/mew_first_calibration.py`, a later same-path zero-match
  `search_text` caused the broad-read guard to hard-fail a top-of-file
  `read_file` instead of reusing the positive search anchor. Task `#664`
  repairs that path: broad-read-after-search-miss now produces a narrow
  `read_file` replacement from the latest positive same-path search anchor
  when no cached read window exists. This is supervisor-owned loop-substrate
  progress, not mew-first autonomy credit; retry `#663` after commit.
  Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'broad_read_after_search_miss' --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings.
- Task `#663` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#664` blocker fix. It ignores narrative
  metric/status bullets that merely mention a task id, while preserving real
  attempt-entry prefixes such as `- Task #...`, `- follow-up #...`, and
  `- #639 mew-first note`. Count this as `success_after_substrate_fix`: the
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without product rescue edits after rejecting two
  wrong-target drafts. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py -k "narrative or attempt_window or substrate or success_after" --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_metrics.py -k 'narrative or attempt_window or substrate or success_after or mew_first or metrics' --no-testmon`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `./mew metrics --mew-first --limit 100 --json`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
  The failed `uv run python -m unittest tests.test_mew_first_calibration`
  command was an invalid inferred verifier because this module contains pytest
  tests, not a product regression. Codex-ultra re-review reported no findings
  after adding explicit `follow-up #...` prefix coverage.
- Task `#665` is a supervisor-owned M6.16/M6.14 repair from the invalid
  inferred verifier observed during `#663`: `suggested_verify_command_for_call_path`
  now prefers `uv run pytest -q <test_path> --no-testmon` for pytest-style
  test files while preserving `uv run python -m unittest <module>` for
  `unittest.TestCase` modules. Count this as loop-substrate/product progress,
  not mew-first autonomy credit: mew hit repeated `task_goal_term_missing`
  before drafting the patch. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k "suggested_verify_command or pytest_style or paired_source_verifier" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "verify_command or verifier" --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings after adding
  explicit pytest import/class-style coverage.
- Task `#666` is a supervisor-owned M6.16/M6.14 repair from GitHub issue `#10`:
  stale pending dry-run approvals are now suppressed once a later completed,
  non-rolled-back same-path write is followed by a passing verifier. Rolled
  back failed writes do not suppress the original pending approval. Count this
  as loop-substrate/product progress, not mew-first autonomy credit: mew spent
  the attempt budget reading anchors and then timed out before drafting. Valid
  proof passed:
  `uv run pytest -q tests/test_work_session.py -k "superseded or pending_approval or finish_blocked or rolled_back" --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings after the
  rolled-back-write regression was added.
- Task `#667` landed the GitHub issue `#3` same-file write-batch ergonomics
  slice as practical mew-first evidence. The work loop now collapses duplicate
  same-path `edit_file` actions into one `edit_file_hunks` action before
  enforcing the five-tool write-batch cap, while preserving rejection for
  unsafe `write_file` duplicates and `replace_all=True` edit semantics. Count
  this as practical mew-first without rescue edits: mew authored the source
  and test patch, Codex-ultra first found two correctness issues, and reviewer
  steer was needed for mew to repair both in the same session with no
  supervisor product-code rescue. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k "same_path_write_edits or edit_file_hunks or paired_write_batch" --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The broad `uv run python -m unittest tests.test_work_session`
  attempts are not counted as product regressions: inside the mew run they
  inherited `MEW_CODEX_REASONING_EFFORT=high` and failed existing reasoning
  expectation tests, and the manual env-cleared rerun hit an unrelated 0.21s
  timing flake. Codex-ultra re-review session
  `019dca8b-7797-7760-b628-100e80455aa5` reported no findings after the
  reviewer fixes.
- Task `#668` landed the GitHub issue `#9` behavior-verifier prompt slice as
  practical mew-first evidence. The work think prompt now tells tests and
  verifier commands to prefer behavior, contract, output, state, or
  docs-visible assertions over exact source text phrase assertions unless the
  task explicitly requires a literal public string or security-sensitive marker.
  Count this as practical mew-first without rescue edits: mew authored the
  paired source/test patch, codex-ultra review session
  `019dcab7-b73d-7bf2-b4a5-994e8c940a62` found the missing write-ready and
  tiny-draft prompt surfaces, and mew session `#651` repaired them without
  supervisor product-code rescue. The supervisor only corrected an invalid
  pytest `-k` verifier expression in the task invocation. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or behavior' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The invalid original verifier
  `work_think_prompt or source_literal or behavior verifier` was a task-spec
  operator error, not a product regression. Codex-ultra re-review reported no
  findings after the write-ready and tiny-draft repair.
- Task `#669` landed the GitHub issue `#5` scoped-verifier-repair slice as
  supervisor-owned M6.16/M6.14 repair evidence after a partial mew-first
  attempt. The normal, write-ready, and tiny-draft work prompts now tell the
  implementation lane to keep one compact in-session repair when a rollback
  verifier failure has one small clear localized cause and a clean worktree,
  centering that repair on the failed assertion/output and target path before
  switching to remember, checkpoint, or stop due pressure. Count this as
  loop-substrate/product progress, not mew-first autonomy credit: mew session
  `#652` authored the first normal-prompt patch, codex-ultra review session
  `019dcace-ebe2-7422-98d9-553dc259e1b2` found missing write-ready/tiny
  coverage, mew session `#653` added model-specific wording and then hit
  `old_text_not_found`, and the supervisor repaired the final generic
  three-surface prompt/test shape. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'verifier_failure or failed_patch_repair or work_think_prompt or write_ready_tiny_draft or write_ready' --no-testmon`,
  `env -u MEW_CODEX_REASONING_EFFORT uv run python -m unittest tests.test_work_session.WorkSessionTests.test_work_ai_compact_live_forces_compact_prompt_context_on_high_risk_task tests.test_work_session.WorkSessionTests.test_work_session_steer_is_consumed_by_next_model_step`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The broader `uv run python -m unittest tests.test_work_session`
  failure inside the mew run inherited `MEW_CODEX_REASONING_EFFORT=high` and is
  not counted as a product regression. Codex-ultra re-review reported no
  findings after the generic three-surface repair.
- Task `#670` landed the GitHub issue `#4` rejected/rolled-back retry-context
  compaction slice as supervisor-owned M6.16/M6.14 repair evidence after a
  mew-first attempt failed to produce a patch. Session `#654` spent ten steps
  on targeted inspection and write-ready cached-window refresh, then reached
  `max_steps` without drafting. The supervisor-owned repair adds
  `resume.retry_context` for rejected and rolled-back writes, omits raw
  `old`/`new`/`content`/`edits` and `diff` bodies from resolved rejected or
  rolled-back write tool calls in model prompts, propagates the compact
  retry context into write-ready and deliberation focused contexts, and drops
  stale retry context after a newer changed write supersedes it. Count this as
  loop-substrate/product progress, not mew-first autonomy credit. Valid proof
  passed:
  `uv run pytest -q tests/test_work_session.py -k 'rejected or rolled_back or retry_context or patch_body or pending_approval or work_session_resume' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'write_ready or failed_patch_repair or rejection_frontier or retry_context' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcaf1-2534-7a12-8812-e6927b62d586` first found stale supersession and
  empty-diff-key issues, then re-review reported no findings after both
  regressions were covered.
- Task `#671` landed the GitHub issue `#11` side-dogfood append-validation
  slice as practical mew-first evidence. `mew side-dogfood validate --input
  ... [--json]` now validates one local side-project dogfood report against the
  canonical append schema without mutating the ledger, so side-project
  closeout can catch descriptive/non-appendable reports before finish. Count
  this as practical mew-first without rescue edits: session `#655` authored
  the source/CLI/test patch, codex-ultra review session
  `019dcb09-266b-7a22-8db7-9eead609e51b` found a missing-input `OSError`
  path, and mew session `#656` repaired it with a focused regression. Valid
  proof passed:
  `uv run pytest -q tests/test_side_project_dogfood.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run python -m unittest tests.test_commands tests.test_work_deliberation_cli`,
  `uv run ruff check src/mew/cli.py src/mew/commands.py tests/test_side_project_dogfood.py`,
  and `git diff --check`. Codex-ultra re-review reported no findings after
  the missing-input regression.
- Task `#672` landed the GitHub issue `#12` watch/continuous-mode verifier
  guidance slice as practical mew-first evidence. The normal, write-ready,
  and tiny-draft work prompts now tell the implementation lane that tasks
  involving watch, continuous, polling, listen, or other repeated modes must
  include bounded-loop or repeated-observation proof of external behavior, plus
  interval/interrupt handling or output-rewrite evidence where relevant, and
  must not accept internal mode flags alone. Count this as practical
  mew-first without rescue edits: session `#657` authored the paired
  source/test patch, hit one stale `old_text_not_found` draft, then repaired
  the same proposal after reviewer steer to retry exact anchors. Valid proof
  passed:
  `uv run pytest -q tests/test_work_session.py -k 'watch or continuous or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or write_ready or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcb20-3fec-7043-b508-a3ec5e8ceac4` reported no findings.
- Task `#673` landed the GitHub issue `#7` contract/docs-heading proof
  guidance slice as practical mew-first evidence. The normal, write-ready,
  and tiny-draft work prompts now tell the implementation lane that
  contract/docs-heavy slices must compare documented headings/surfaces against
  actual renderer or CLI output instead of treating file creation as proof.
  Count this as practical mew-first without rescue edits: session `#658`
  authored the paired source/test patch. The mew-run broad unittest verifier
  initially failed two unrelated reasoning-effort tests, but the same full
  module passed immediately when re-run outside the failed follow snapshot.
  Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'contract or heading or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or write_ready or contract or heading or behavior or verifier' --no-testmon`,
  `uv run python -m unittest tests.test_work_session`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcb2f-dcd3-79e1-b069-4919e7e21c6d` reported no findings.
- Task `#674` landed the GitHub issue `#6` side-dogfood ledger-semantics
  slice as practical mew-first evidence. `mew side-dogfood report` now states
  that `rescue_edits` is a numeric Codex product-code rescue count and excludes
  operator steering, reviewer rejection, verifier follow-up, and generic
  repair. The implementation-lane baseline text labels the side-project
  aggregate as `codex_product_code_rescue_edits`, while JSON keeps the
  backward-compatible `rescue_edits_total` key and adds the same semantic alias.
  Count this as practical mew-first without supervisor product-code rescue:
  session `#659` authored the initial paired source/test patch and sibling
  digest label; codex-ultra review session
  `019dcb3e-a3f6-7423-ac91-981e1396c86c` found a non-integral float truncation
  bug and missing machine-readable alias; session `#660` repaired both. Valid
  proof passed:
  `uv run pytest -q tests/test_side_project_dogfood.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/side_project_dogfood.py src/mew/implementation_lane_baseline.py tests/test_side_project_dogfood.py tests/test_implementation_lane_baseline.py`,
  and `git diff --check`. Codex-ultra re-review reported no findings.
- Task `#675` landed an M6.16 measurement-quality slice as practical
  mew-first evidence. The mew-first calibration now treats reviewer-mediated
  mew-first repairs with no supervisor product-code rescue as
  `practical_mew_first`, while preserving clean credit for no-review
  `without rescue edits` entries. Sessions `#661`, `#662`, and `#663`
  authored the paired source/test patch and repaired two codex-ultra review
  findings plus the live `#671` wording gap. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `git diff --check`,
  `./mew metrics --mew-first --limit 100 --json`,
  and `./mew metrics --implementation-lane --json`. Metrics now classify
  tasks `#671` and `#674` as practical, keep clean/practical successes at
  `11`, and reduce the measured rescue/partial count from `29` to `28`.
  Codex-ultra review session `019dcb59-5c67-7e12-9169-500867c5e80c` ended with
  `NO FINDINGS`.
- Task `#676` landed an M6.16 measurement-window slice as practical
  mew-first evidence. `extract_mew_first_attempts(limit=N)` now sorts attempt
  records by descending task id before applying the limit, so recent cohort
  metrics select the newest task ids instead of the oldest tail of
  `ROADMAP_STATUS.md`; M6.16 headings are also recognized by the default
  attempt-section list for fixture/doc compatibility. Session `#664` authored
  the paired source/test patch. It hit one expected shell-permission stop while
  trying to run `./mew metrics` from inside the work session, but no
  supervisor product-code rescue was needed. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `git diff --check`,
  `./mew metrics --mew-first --limit 10 --json`,
  and `./mew metrics --implementation-lane --limit 20 --json`. Current
  `--limit 10` now reports task window `#676 #675 #674 #673 #672 #671 #670
  #669 #668 #667` and passes the gate at `8/10`; `--limit 20` reduces the
  measured rescue/partial rate to `0.5`. Codex-ultra review session
  `019dcb76-a4a1-7803-b29c-d9a888edae14` reported `NO FINDINGS`.
- Task `#677` landed an M6.16 first-edit-latency instrumentation slice as
  practical mew-first evidence. Metrics diagnostics now expose
  `slow_first_edit_proposals` samples with session/task fields, first-edit
  seconds, first write tool id/tool/path, start time, and first model-turn
  summary; the implementation-lane baseline carries those samples under
  `first_edit_latency.samples` and prints them in the text report. Session
  `#665` authored the read-only telemetry/reporting patch, and session `#666`
  repaired the codex-ultra threshold finding so exactly-at-threshold `30.0s`
  samples are not treated as slow. Valid proof passed:
  `uv run pytest -q tests/test_metrics.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/metrics.py src/mew/implementation_lane_baseline.py tests/test_metrics.py tests/test_implementation_lane_baseline.py`,
  `git diff --check`,
  `./mew metrics --implementation-lane --limit 20 --json`,
  and `./mew metrics --implementation-lane --limit 20`. Current samples name
  concrete first-edit latency targets including sessions `#665`, `#652`, and
  `#649`. Codex-ultra review session
  `019dcb8a-8e66-71b3-b488-203fb4f5eb4f` ended with `NO FINDINGS`. No
  supervisor product-code rescue occurred.
- Task `#678` landed an M6.16 first-edit-latency reduction slice as clean
  mew-first evidence. The normal THINK prompt now treats first-edit latency as
  an operational budget: when scoped source/test cached windows already contain
  first-edit old text, mew should avoid another same-surface rediscovery turn
  and prefer the bounded paired edit path while preserving exact-old-text,
  pairing, scope, and verifier gates. Session `#667` authored the patch,
  produced a patch-draft replay on the write-ready surface, and passed both
  the focused prompt verifier and the full work-session unittest module:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or first_edit_latency' --no-testmon`
  and `uv run python -m unittest tests.test_work_session`. Additional local
  checks passed: `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`
  and `git diff --check`. Codex-ultra review session
  `019dcb9d-ddf7-7f30-8605-7b603f048ba8` reported `STATUS: pass` with
  `NO FINDINGS`; this was mew-first without rescue edits. After the `#677`
  and `#678` evidence-classification notes, `./mew metrics --mew-first --limit 10 --json`
  passes at `8/10`; `./mew metrics --implementation-lane --limit 20 --json`
  reports `clean_or_practical_successes=12/20`, `rescue_partial_rate=0.4`,
  `approval.rejection_rate=0.143`, `verifier.failure_rate=0.0`, and
  first-edit latency `median=285.5s`, `p95=536.55s`, `max=704.0s`.
- M6.13 close gate passed via
  `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`. The proof records
  reviewer-approved deliberation internalization, M6.9 ranked recall, normal
  tiny batch preview, normal approval apply, and a real unittest verifier with
  `close_evidence=true` and no close blockers.
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
- The current work-loop call-boundary slice wires those deliberation primitives
  into `plan_work_model_turn` as a read-only lane attempt. Eligible blockers
  can make one explicitly bound high-effort call; validated results stop as
  reviewer-visible `result_ready` waits, while timeout, non-schema, validation,
  budget, or state-limit cases record fallback trace data and leave tiny
  available. `cmd_work_ai` now persists the returned session trace patch
  through `apply_work_session_trace_patch`.
- The current deliberation control slice adds explicit work-loop controls for
  the live proof: `--deliberate` requests a reviewer-commanded deliberation
  attempt, and `--no-auto-deliberation` disables automatic escalation for the
  run without blocking explicit reviewer commands. This makes the next proof
  commands observable instead of relying only on free-text guidance markers.
  Command-boundary tests now prove that `cmd_work_ai` persists reviewer
  commanded traces, automatic eligible traces, and no-auto fallback traces
  while still calling the tiny lane after the fallback.
- The current Phase 3 internalization slice extends approved
  `reasoning-trace` memory with additive lane provenance
  (`source_lane`, lane attempt id, blocker code, bundle ref, same-shape key,
  and reviewer decision ref). Existing M6.9 reasoning traces remain valid, but
  `source_lane=deliberation` now requires the provenance needed to reconstruct
  the internalization proof. Approved reasoning traces also append to
  `.mew/durable/memory/reasoning_trace.jsonl`, preserving the M6.9/M6.13
  durable ledger slot. A deterministic dogfood scenario records a hard
  deliberation-assisted task, writes the reviewed trace, proves a later
  same-shape task recalls it through provenance-aware active memory, and
  runs the tiny write-ready planning path with a deterministic fake model that
  receives the trace provenance in prompt context and emits a validated paired
  patch draft with `deliberation_invoked=false`. The same scenario now supports
  `--ai --auth <path>` live tiny-provider mode: it loads the configured model
  auth and replaces both the deliberation result call and the tiny draft call
  with a live provider. Validation passed with
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model gpt-5.5 --model-timeout 180 --json`,
  producing `evidence_class=live_provider_internalization_contract`,
  `deliberation_provider_mode=live_provider`, `tiny_provider_mode=live_provider`,
  and a validated paired patch draft. A later close slice replaced the
  previous not-close readiness state with normal work-path apply/verify proof.
- The M6.13 close slice records the full Phase 3 proof: active memory emits
  M6.9 ranked recall metadata with recency, importance, relevance,
  symbol-overlap, and task-shape components; the dogfood trace records
  `contract_cycle_proven=true`; deterministic and live `gpt-5.5` proofs pass;
  the later tiny task previews through `run_work_batch_action`, applies via
  `_apply_work_approval_batch`, and runs a real unittest verifier with
  `verification_test_count>=1`; and `close_evidence=true` has no close
  blockers. The close audit is
  `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`.
- GitHub issue `#1` from side-project dogfood exposed a bounded M6.14 repair
  class: write-batch normalization/execution assumed every code batch must be
  a mew-core `src/mew/**` plus root `tests/**` pair, which blocked declared
  non-core product roots such as `experiments/mew-companion-log`. The repair
  keeps the strict mew-core paired-test rule for `src/mew/**` writes, but lets
  non-core write batches proceed when every write is inside
  `allowed_write_roots`; prompts now describe the same distinction. This is
  substrate repair from side-project evidence, not side-project implementation
  progress.
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

Current scheduled milestone: **M6.20 Terminal-Bench Driven Implement-Lane Debugging**.

M6.20 starts after M6.19 proves that Harbor / Terminal-Bench can execute mew
and at least one reference agent on the same smoke subset. M6.20 should not
begin from model opinion alone; it needs benchmark artifacts from M6.19.

First M6.20 slice:

- choose a fixed smoke/selected subset and write the score target before
  optimizing
- compute mew baseline and reference-agent baseline on the same subset
- classify failed mew tasks through M6.18
- route only cited structural failures into M6.14 repair episodes
- rerun the same subset and record whether the repair improved, regressed, or
  did not affect the score

Planned future milestones:

- **M7 Senses: Inbound Signals**: resume after M6.19/M6.20 give the
  implementation lane an external benchmark and failure-debug loop.
- **M8 Identity: Cross-Project Self**: user-scope identity and cross-project
  memory remain future work after M7.

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
- Reopen M6.16 only if a fresh bounded implementation-lane cohort regresses
  below the recorded close gate, or if first-edit latency remains high on
  current-head samples after M6.17 has used it as lane-choice evidence.
- Reopen M6.18 only if mew-first failure diagnosis stops emitting routeable
  failure scopes or sends structural repairs to M6.14 without cited signals.
- M6.14 remains the default home for future mew-first substrate repair
  episodes.

## Current Roadmap Focus

The next implementation task should map to this chain:

`M6.19 -> Harbor custom agent wrapper -> Terminal-Bench smoke artifacts -> comparable baseline`

Acceptable near-term work:

- run the new Harbor custom-agent wrapper against a tiny Terminal-Bench smoke
  subset and keep the transcript/artifact output
- add a mew headless benchmark entrypoint only if the current CLI surface is
  insufficient for the live Harbor smoke run
- record benchmark artifacts in a stable path with per-task outcome,
  transcript/work-session summary, verifier result, timeout, and cost/token
  data when available
- run or document the same smoke subset against at least one reference agent
  such as Codex CLI or Claude Code

Non-goals for the next session:

- M6.20 score optimization before the M6.19 harness is trustworthy
- broad prompt tuning for Terminal-Bench before baseline artifacts exist
- resuming M7 inbound signal work before the Terminal-Bench milestones are
  addressed or explicitly reprioritized
- full concurrent executor
- memory explore agentization
- provider-specific prompt caching
- broad work-loop or work-session refactors without a recorded structural
  signal
- treating diagnosis output as automatic permission to perform structural
  repair without reviewer-visible evidence

## Latest Validation

Latest roadmap/status validation:

- M6.19 task `#687` added `.harbor/mew_terminal_bench_agent.py`,
  `docs/terminal-bench-harbor-smoke.md`, and
  `tests/test_harbor_terminal_bench_agent.py`.
- Focused validation for `#687` passed:
  `uv run pytest -q tests/test_harbor_terminal_bench_agent.py --no-testmon`,
  `uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py`,
  and `git diff --check`.
- Autonomy accounting: mew produced the wrapper/docs/tests and repaired the
  await-time timeout fallback test; Codex applied a one-line supervisor lint
  cleanup after mew marked the task done without running ruff. Count the slice
  as product progress with a small reviewer cleanup, not a fully clean
  mew-first close.
- Remaining M6.19 gap: live Harbor execution against a Terminal-Bench smoke
  subset and a comparable reference-agent run are not yet complete.
- M7 task `#686` pending dry-run tools `#6644/#6645` were rejected without
  applying because M7 is now pending behind Terminal-Bench milestones.
- Earlier roadmap-only M6.19/M6.20 setup remains historical; current M6.19
  validation includes the focused wrapper tests and ruff checks listed above.

Latest M6.18 source/test validation:

- Close audit: `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md`.
- Failure diagnosis slice:
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run ruff check src/mew/mew_first_calibration.py src/mew/implementation_lane_baseline.py tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --mew-first --limit 10 --json`, and
  `./mew metrics --implementation-lane --limit 10` passed.

Latest M6.17 source/test validation:

- Task `#679` lane-dispatch proposal slice:
  `uv run python -m unittest tests.test_tasks tests.test_commands`,
  `uv run ruff check src/mew/tasks.py src/mew/commands.py tests/test_tasks.py tests/test_commands.py`,
  and `git diff --check` passed.
- Task `#680` active roadmap gate slice:
  `uv run python -m unittest tests.test_brief`,
  `uv run ruff check src/mew/brief.py tests/test_brief.py`, and
  `git diff --check` passed.
- Task `#681` no-candidate next-action fallback slice:
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/commands.py tests/test_commands.py`, and
  `git diff --check` passed.

Earlier M6.16 source/test validation:

- Task `#678` first-edit latency budget slice:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or first_edit_latency' --no-testmon`,
  `uv run python -m unittest tests.test_work_session`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check` passed. Codex-ultra review session
  `019dcb9d-ddf7-7f30-8605-7b603f048ba8` reported `STATUS: pass` with
  `NO FINDINGS`.
- M6.13 deliberation work-loop call-boundary slice:
  `uv run pytest -q tests/test_work_deliberation_loop.py --no-testmon`,
  `uv run pytest -q tests/test_deliberation.py tests/test_work_deliberation_loop.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'deliberation or active_work_todo or lane' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'plan_work_model_turn' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_deliberation_loop.py`,
  and `git diff --check` passed.
- M6.13 deliberation live-control slice:
  `uv run pytest -q tests/test_deliberation.py tests/test_work_deliberation_loop.py tests/test_work_deliberation_cli.py --no-testmon`,
  `uv run ruff check src/mew/deliberation.py src/mew/work_loop.py src/mew/commands.py src/mew/cli.py tests/test_deliberation.py tests/test_work_deliberation_loop.py tests/test_work_deliberation_cli.py`,
  and `git diff --check` passed.
- M6.13 Phase 3 internalization proof slice:
  `uv run pytest -q tests/test_dogfood.py -k 'm6_13' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py tests/test_work_session.py -k 'm6_13 or approve_all or paired' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'approve_all or paired' --no-testmon`,
  `./mew dogfood --scenario m6_13-deliberation-internalization --workspace /tmp/mew-m6-13-proof-cli-3 --json --report /tmp/mew-m6-13-proof-cli-3-report.json`,
  `./mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model-backend codex --model gpt-5.5 --model-timeout 120 --workspace /tmp/mew-m6-13-live-gpt55-2 --json --report /tmp/mew-m6-13-live-gpt55-2-report.json`,
  `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`,
  and `git diff --check` passed for the final normal work-path close proof.
  Earlier supporting validation:
  `uv run pytest -q tests/test_memory.py -k 'reasoning_trace' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py -k 'm6_13_deliberation_internalization or m6_13_live_provider or scenario_choices' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'compact_active_memory_preserves_reasoning_trace_provenance' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'write_ready_tiny or write_ready_fast_path or compact_active_memory_preserves_reasoning_trace_provenance' --no-testmon`,
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --json`,
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model gpt-5.5 --model-timeout 180 --json`,
  `uv run ruff check src/mew/typed_memory.py src/mew/work_session.py src/mew/work_loop.py src/mew/commands.py src/mew/cli.py src/mew/dogfood.py tests/test_memory.py tests/test_dogfood.py tests/test_work_session.py`,
  and `git diff --check` passed.
- M6.14 side-project write-scope repair from GitHub issue `#1`:
  `uv run pytest -q tests/test_work_write_scope.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'plan_work_model_turn or paired or write_batch' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py src/mew/commands.py tests/test_work_write_scope.py`,
  and `git diff --check` passed.
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
