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
| 6.8.5 Selector Intelligence and Curriculum Integration | `in_progress` | First read-only failure-cluster selector signal landed; preference/reviewer-history signals remain. |
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

Active work: **M6.8.5 Selector Intelligence and Curriculum Integration**.

Why M6.8.5 is active:

- M6.8 closed the safe reviewer-approved task handoff contract.
- M6.9 Phase 4 curriculum/habit/preference work was deliberately deferred
  until that contract existed, and now belongs here.
- The current resident capability gap is task quality: mew can chain safe
  bounded tasks, but selection is still shallow and mostly depends on prepared
  ready tasks.

Current M6.8.5 target:

- use the closed M6.8 selector ledger as the approval/scope substrate
- add read-only selector intelligence signals from failure clusters,
  preference evidence, and reviewer history
- keep reviewer approval mandatory before handoff execution
- keep selector-owned output away from roadmap-status, milestone-close, and
  governance files

Current M6.8.5 evidence:

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

## Next Milestone

Current scheduled milestone: **M6.8.5 Selector Intelligence and Curriculum
Integration**.

M6.8.5 absorbs M6.9 Phase 4. Do not reopen M6.9 just to implement these:

- failure-clustered curriculum
- preference-store retrieval from reviewer diffs
- habit compilation v0
- read-only M6.12/M6.14 selector evidence
- selector traces that explain why a task was chosen

M6.8.5 may now start because M6.8 core proved the safe chained approval loop.

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

`M6.8.5 -> selector intelligence -> read-only failure-cluster signal v0`

Acceptable near-term work:

- add the smallest read-only selector signal that helps mew choose better
  bounded tasks without changing the M6.8 approval contract
- start with failure-cluster evidence because it already exists in M6.12/M6.14
  surfaces and can be attached as `failure_cluster_reason`
- keep all selector execution reviewer-approved; no auto-dispatch

Non-goals for the next session:

- autonomous execution or auto-merge
- M6.13 deliberation lane
- full concurrent executor
- memory explore agentization
- provider-specific prompt caching
- M7 inbound-signal work
- broad refactors or polish not mapped to the M6.8.5 gate

## Latest Validation

Latest committed code baseline: `ab73636 Summarize selector proof streak`.

Current uncommitted change: M6.8 close-gate audit and roadmap-status focus
switch to M6.8.5. No source/test code changed after `ab73636`.

Observed in this cleanup session:

- `git diff --check` passed
- detailed pre-compression `ROADMAP_STATUS.md` was archived to
  `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Behavioral validation for the latest source/test change is listed above under
task `#638`; this closeout edit is documentation/status only.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action
  here.
- When a milestone closes, add or update a close-gate audit in `docs/` and
  summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions
  override the active milestone decision in this file.
