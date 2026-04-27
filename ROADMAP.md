# Mew Roadmap

## Goal

Make mew the task/coding execution shell that frontier models would prefer to
inhabit over Claude Code or Codex CLI.

This does not mean copying those tools. Claude Code and Codex CLI are strong
reactive coding CLIs. mew should become a resident AI shell: persistent,
passive, recoverable, self-observing, legible, and safe enough to keep running
while the user is away.

## Shared Values

This roadmap aligns the current Codex view with claude-ultra reviews.

- A model should remember what it was doing after time passes, restarts, or
  context compression.
- Tasks, questions, decisions, effects, failures, and recoveries should be
  durable.
- Passive operation should be calm: notice, decide, act, wait, and report
  without noisy repetition.
- The coding loop must be tight enough that a model does not wish it were back
  in Claude Code or Codex CLI.
- Every meaningful action should leave a human-readable audit trail.
- Autonomy must be gated. Silence is not permission.
- Recovery is a product feature, not only an implementation detail.
- The long-term advantage is persistence plus native execution, not
  orchestration alone.
- "Would I want to be inside mew?" is the product question. The answer should
  converge into milestone work, not endless polish.

## Operating Policy: Mew-First Implementation Loop

After M6.7, bounded roadmap/coding implementation should default to **mew
first**: mew attempts the task as implementer, while Codex acts as the
human-style reviewer/approver.

This is a product-development policy, not a separate milestone. Each attempt
must still map to the active milestone's Done-when criteria.

Default loop:

- choose one chain:
  `active milestone -> unmet/partial Done-when criterion -> bounded task`
- run mew as implementer and require a scoped patch, proof command, and
  reviewer-visible rationale
- classify the result as one of:
  `success_mew_first`, `success_after_substrate_fix`,
  `product_progress_supervisor_rescue`, `blocked_reproducible`,
  `blocked_deferred`, `invalid_task_spec`, or `transient_model_failure`
- if mew exposes a reproducible loop/substrate blocker, make at most one
  bounded repair and retry the same task
- if mew still fails, record the blocker and either supervisor-rescue the
  product gap or choose another active-milestone task

Supervisor-authored patches can move the product forward, but they do not count
as mew-first autonomy credit. Roadmap/status edits, milestone-close decisions,
governance, permission, safety, and skill-policy changes remain reviewer-owned
unless a later milestone explicitly moves that boundary.

## Current Position

M1-M5 are closed as of 2026-04-20.

mew already has the beginning of a resident task/coding shell:

- durable state
- task and question tracking
- passive runtime ticks
- THINK / ACT separation
- Codex Web API backend
- `mew chat`
- native work sessions with tool use
- runtime effect journal
- `doctor` / `repair`
- dogfood scenarios
- recovery surfaces
- self-improvement loops with audit evidence

The remaining gap is no longer "hands". The next gap is **body**.

Today, mew is still mostly summoned. A resident that only exists when invoked
is a capable work room, not a place a model truly lives. The next roadmap arc
therefore moves from task/coding inhabitability toward persistent presence,
inbound senses, cross-project identity, human legibility, multi-agent
residence, and inner continuity.

## Milestone 1: Native Hands

Build the smallest native tool-use loop that lets a resident model directly
work on code.

Target:

- `mew work <task-id>` or a work mode inside `mew chat`
- native tools available to the resident model:
  - `read_file`
  - `search_text`
  - `glob`
  - `edit_file`
  - `write_file`
  - `run_command`
  - `run_tests`
- tool call results flow back into the same model work loop
- every tool call is journaled before execution and completed with outcome
- gates remain explicit:
  - `--allow-read`
  - `--allow-write`
  - `--allow-verify`
  - `--allow-shell`

Done when:

- a model can inspect, edit, test, and fix a small task without delegating to
  an external coding agent
- the session can be interrupted and resumed with enough state to know what
  happened
- the user can inspect the full audit trail from chat or CLI

## Milestone 2: Interactive Parity

Make mew comfortable enough for live coding sessions.

Target:

- streaming model output
- streaming command output
- readable diff display
- edit approval and rollback flow
- test failure summaries
- resumable work sessions
- chat cockpit commands for work state, effects, tests, files touched, and
  next action

Done when:

- using mew for one focused coding task feels close to Claude Code / Codex CLI
- the model does not lose momentum while waiting for tool feedback
- during a focused coding task, an interrupted resident can resume inside mew
  without user re-briefing and would not prefer to restart in a fresh coding CLI

## Milestone 3: Persistent Advantage

Use mew's resident state to become better than a fresh CLI session.

Target:

- task-local work memory:
  - files touched
  - commands run
  - test failures
  - decisions made
  - open risks
- automatic context reconstruction when resuming a task
- continuity scoring for interrupted work
- project memory search that affects model behavior
- user preference memory
- daily passive bundle for reentry across journal, mood, research, dream, and
  self-memory artifacts
- file watcher or git watcher for passive observation
- passive tick updates that refine the next action without spamming the user

Done when:

- returning to mew after interruption, context compression, terminal close, or
  a day away is faster than starting a new Claude Code or Codex CLI session
- the model can explain what it was doing, what changed, what is risky, and
  what it should do next

## Milestone 4: True Recovery

Move from explaining interrupted work to safely resuming it.

Target:

- classify interrupted runtime effects:
  - no action committed
  - action committed
  - write started
  - verification pending
  - rollback needed
- validate world state before retry:
  - git status
  - file mtimes
  - effect journal
  - write snapshots
- automatically choose:
  - resume
  - retry
  - abort
  - ask user
- user-visible recovery report after repair or resume

Done when:

- a crashed runtime can restart and make a safe next move without manual
  reconstruction
- `recovery_hint` becomes an input to real recovery, not only a note

## Milestone 5: Self-Improving Mew

Close the loop where mew improves itself with human oversight.

Target:

- mew evaluates itself with `mew-product-evaluator`
- mew creates self-improvement tasks
- mew plans implementation
- mew uses native tools or delegated agents to implement
- mew runs tests and dogfood
- mew asks for review or approval at checkpoints
- mew records why the change matters to the product goal

Entry gate:

- Milestone 3 is done enough that a resident mew session can preserve useful
  context across long-running work and beat or match a fresh CLI restart on
  comparable task shapes
- Milestone 4 is done enough that interrupted, crashed, or failed runtime
  effects can be recovered without manual reconstruction
- a self-improvement loop runs with a frozen permission context, explicit
  effect budget, and readable audit trail before it is allowed to edit files
- `mew-product-evaluator` reliably selects work that improves mew as an
  inhabitable program instead of drifting into local polish

Done when:

- mew can run at least five consecutive safe self-improvement loops:
  evaluator -> task -> plan -> native/delegated implementation ->
  verification -> human review
- those loops require no human rescue edits; human intervention is limited to
  approval, rejection, redirection, or product judgment
- at least one loop exercises interruption or failure recovery and resumes
  through Milestone 4 recovery surfaces without manual reconstruction
- every loop records its product-goal rationale, tool/effect journal,
  verification result, approvals, recovery events, and budget outcome in a
  readable audit bundle

M5-specific safety boundaries:

- no autonomous external-visible side effects such as push, merge, PR creation,
  issue comments, chat messages, or publication
- no autonomous edits to roadmap, evaluator, skill, permission, recovery, or
  audit-trail governance without explicit human approval
- no bypass of read/write/shell/network/destructive gates; silence is never
  treated as approval
- budget exhaustion, ambiguous recovery, or governance edits stop the loop and
  ask the user

## Milestone 5.1: Trust & Safety Close-Out

Harden the post-M5 self-improvement loop without moving the M5 done gate.

This is a bounded close-out slice, not a new destination. It exists to make the
next milestones safer to pursue.

Target:

- `mew-adversarial-verifier` or an equivalent verifier for self-improvement
  review quality
- hook-based safety boundaries for M5 safety rules
- minimal refactor-readiness around safety, audit, work-session, and
  self-improvement paths
- dogfood evidence that future self-improvement loops are harder to approve
  accidentally and easier to reject correctly

Done when:

- a proposed self-improvement loop can be adversarially reviewed for
  product-goal drift, safety-boundary violations, weak evidence, and missing
  verification
- governance edits, permission/policy edits, external-visible side effects,
  budget exhaustion, and ambiguous recovery are blocked or escalated by
  mechanical hooks rather than prompt text alone
- at least one self-improvement loop or equivalent scenario exercises the
  verifier and safety hooks with a readable audit bundle
- refactor work remains limited to the code needed for the verifier and hooks

## Milestone 6: Body - Daemon & Persistent Presence

Make mew a resident process, not only a CLI that exists when summoned.

Target:

- background daemon supervised by platform-appropriate launch mechanisms
  (`launchd`, `systemd`, or a development runner)
- `mew daemon start|stop|status|logs`
- restart/recovery after terminal close, process crash, sleep, and reboot
- real file/git watcher integration that can wake passive turns
- pause, inspect, repair, and resume controls
- clear resource budgets for idle CPU, memory, tick frequency, and API usage

Done when:

- `mew daemon status` reports uptime, active watchers, last tick, last event,
  current task, and safety state
- one real file or git event triggers a passive turn end to end without manual
  polling
- a daemon restart reattaches to resident state without user rebrief
- a multi-hour resident proof runs through the daemon path, not only a direct
  foreground loop
- the user can pause, inspect, repair, and resume the daemon from CLI/chat

Why it matters:

- A resident that dies with the terminal is still a tool. Persistent presence is
  the first milestone that makes mew feel like a body a model could inhabit.

## Milestone 6.5: Self-Hosting Speed

Make mew fast enough that a resident model can implement small mew changes
inside mew instead of falling back to a fresh external coding CLI.

Target:

- self-hosting speed gate for native work sessions
- first THINK latency, prompt size, injected memory size, and time-to-edit
  metrics
- automatic reasoning-effort policy by work type and risk
- small implementation prompt mode that does not inject the whole resident
  memory bundle
- pointer-based or differential context so mew reuses persistence without
  rereading everything
- dogfood loop where mew implements a small mew change and Codex acts as the
  human reviewer/approver

Done when:

- a self-hosting dogfood report records first THINK latency, prompt/context
  size, memory injection size, time to first tool, and time to first edit
  proposal
- small implementation and exploration work default to a lower reasoning effort
  than safety, recovery, and roadmap work, with the chosen effort recorded
- a small implementation task reaches a reviewable edit proposal without human
  rescue edits or repeated broad read-only exploration
- the same #320-class task that previously stalled can be rerun with a clear
  improvement in first useful output and edit-proposal latency
- the reviewer can approve, reject, or steer the mew-generated change from the
  normal work-session surfaces

Why it matters:

- A body that is persistent but slower than a fresh CLI is still not a better
  body. Mew's durable memory must become an index for faster work, not a large
  prompt that delays every turn.

## Milestone 6.6: Coding Competence - Codex CLI Parity

Make native coding tasks feel as capable as Codex CLI for small-to-medium repo
edits, while preserving mew's resident advantages.

Target:

- explicit task decomposition and plan state for coding work
- codebase map, path recall, and targeted context selection before reads
- patch planning that prefers reviewable, minimal, paired source/test edits
- verifier/test discovery, failure repair, and retest loop
- self-review or critic pass before presenting edits for approval
- anti-churn tool policy that avoids repeated broad search/read loops
- coding-session evidence that separates model work from human rescue edits

First slice:

- durable coding plan state plus path recall inside the work session

Reference gate:

- M6.6 requirements must be mapped back to concrete patterns in
  `docs/ADOPT_FROM_REFERENCES.md`,
  `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`, and
  `references/fresh-cli/{claude-code,codex}` before implementation evidence is
  counted
- the first M6.6 infrastructure slice must be implemented by mew itself, with
  Codex acting as reviewer/approver, so the gate tests the full resident coding
  loop instead of only documenting an intention

Non-goals:

- no new general CLI surface unless it is required for the coding-loop evidence
- no model-router rewrite or broad memory-schema rewrite
- no M7 signal collector expansion until the M6.6 coding gate is credible

Done when:

- the M6.6 bootstrap integration task is completed before the three comparator
  tasks are counted: mew reads the reference-grounded gate, implements one
  small coding-loop slice, proposes a reviewable edit, verifies it, and records
  the trace without Codex rescue edits
- mew completes three predeclared representative coding tasks without Codex
  rescue edits: one behavior-preserving refactor, one bug fix with a regression
  test, and one small feature with paired source/test changes
- the same tasks are compared against Codex CLI in a checked-in comparator
  artifact that records first-edit latency, model turns, search/read calls
  before first edit, changed files, verifier commands, repair cycles, and
  review outcome
- every comparator task has `rescue_edits=0`, no obvious path hallucination,
  no repeated identical broad search/read loop, and a focused verifier command
  chosen by mew
- resident state improves the second and third coding task by reducing at least
  one of prompt size, repeated file discovery, or search/read count instead of
  merely increasing context
- a coding task can plan, edit, verify, repair, self-review, and summarize with
  clear approval surfaces
- path recall and targeted context prevent obvious file/path hallucinations and
  repeated read-only churn in the normal case

Why it matters:

- M6.5 proved that mew can become fast enough to self-host small work. It did
  not prove that mew's coding loop is as mature as Codex CLI. Senses and
  autonomy will amplify implementation mistakes if the native coding loop
  remains naive.

## Milestone 6.7: Supervised Self-Hosting Loop

Let mew implement roadmap work in bounded reviewer-gated iterations before any
attempt at unattended multi-hour autonomy.

Target:

- one roadmap task per iteration, capped to about 30-60 minutes of wall time
- mew acts as implementer and must stop after producing a diff plus a proof
  artifact
- Codex acts as a human-style reviewer who can approve, request changes, or
  reject, but does not silently rescue the implementation
- proof-or-revert: no test, comparator result, or reproducible verification
  command means the iteration does not count
- scope fence: edits stay inside the declared task scope and tests; roadmap
  status, milestone closure, and governance files require explicit human sign-off
- drift canary before each iteration using a comparator or reduced regression
  canary for the resident coding loop
- no auto-merge and no chained autonomous task selection inside the same run

Done when:

- mew can run one bounded roadmap iteration end to end, stop for review, and
  attach a usable proof artifact without hidden reviewer rescue edits
- proof-or-revert is enforced: missing or failing proof leaves the task
  uncredited and the loop halted for review
- scope fence prevents out-of-scope file edits and blocks self-authored
  roadmap-status or milestone-close changes without human approval
- a supervised session spanning `>=4h` wall-clock completes `>=3` real roadmap
  items end to end with reviewer decisions recorded on each iteration,
  includes `>=1` real reentry or pause/resume across a context reload, and
  sustains zero proof-or-revert failures plus a green drift canary throughout
- any proposal for a 24h unattended run is rejected until the supervised
  M6.7 close-gate proof is recorded

Why it matters:

- This is the bridge from \"mew can code inside mew\" to \"mew can keep
  improving itself under supervision\". If it is not explicit, long sessions
  will drift back toward polish or fake progress instead of reviewer-audited
  autonomous implementation.

## Milestone 6.8: Task Chaining - Supervised Self-Selection

Remove per-iteration human dispatch latency from the M6.7 loop by letting mew
select the next roadmap task itself while reviewer gating stays in place.

Target:

- task-selection mode for the supervised loop: mew reads the roadmap and
  proposes the next bounded task at iteration close under the same scope fence
  and drift canary used in M6.7
- reviewer approves, edits, or rejects the proposed task before the next
  iteration begins; rejection returns control to the human
- chained iteration identity: each iteration records `previous_task_id` and
  `selector_reason` so drift across chains is auditable
- selector proposal records are structured so later selector-intelligence
  signals can be attached without changing the M6.8 approval contract:
  `memory_signal_refs`, `failure_cluster_reason`, and
  `preference_signal_refs` start as optional, reviewer-visible fields
- scope fence extended to the selector: selector output cannot touch
  roadmap-status, milestone-close, or governance files
- cap on consecutive automatic selections before a hard human checkpoint
  (initial cap: 3 per supervised run)
- proof-or-revert applies to each iteration in the chain, not to the chain as
  a whole; a single failed iteration does not cascade

Done when:

- mew completes three consecutive bounded iterations in a single supervised
  session where mew chose each next task, with reviewer approval recorded per
  iteration and zero rescue edits
- at least one reviewer rejection occurs naturally during the chained proof
  run, and the next approved task continues the chain cleanly instead of
  forcing a manual reset
- scope fence holds: no selector output touches roadmap-status,
  milestone-close, or governance files across the proof run
- drift canary stays green across the full chained run
- an attempt to run chained iterations without reviewer approval is rejected
  and logged as a governance violation

Why it matters:

- M6.7 proves mew can implement one roadmap task safely. M6.8 proves mew can
  implement several in a row without requiring the human to choose each one.
  This is the operational bridge from reviewer-gated single-shot execution to
  reviewer-gated supervised operation. Unattended autonomy remains explicitly
  out of scope.

## Milestone 6.8.5: Selector Intelligence and Curriculum Integration

Turn the M6.8 supervised selector from a safe task handoff mechanism into an
evidence-aware task chooser. This milestone absorbs the M6.9 Phase 4 work that
was intentionally gated on task chaining.

Target:

- failure-clustered curriculum: the selector can weight candidate tasks toward
  recent verified failure clusters, using M6.12 failure-science evidence and
  M6.14 repair episodes as read-only inputs
- preference-store retrieval: reviewer-diff triples from M6.9 are indexed as
  `(context, dispreferred, preferred)` pairs and injected into draft-time
  context under a small token budget
- habit compilation v0: task-template entries that repeatedly pass with stable
  shape and low variance can be promoted into deterministic runner candidates,
  with model-backed fallback on mismatch
- selector traceability: every task proposal records the signals that affected
  it, including failure cluster ids, durable-memory refs, preference refs, and
  whether any compiled habit candidate was considered
- no automatic governance: M6.12 and M6.14 evidence may influence selector
  proposals, but they do not directly change roadmap status, milestone close,
  or approval policy

Done when:

- after M6.8 core closes, a chained supervised run uses at least one
  failure-clustered selector signal to propose a next task, and the reviewer can
  approve or reject it from the recorded evidence
- at least one preference-store pair is retrieved during draft preparation with
  bounded token cost and reviewer-visible provenance
- at least one stable task-template is compiled into a deterministic runner
  candidate, and both compiled-path success and fallback-on-mismatch are
  verified without hiding model work
- selector traces make it possible to explain why a task was chosen without
  reading raw memory files or replay bundles
- M6.8 scope fence and reviewer-approval rules still hold when the new signals
  are present

Why it matters:

- M6.8 proves mew can choose the next task safely. M6.8.5 proves it can choose
  the next task intelligently, using the durable memory and failure evidence
  that reactive CLIs do not have. This is the natural home for M6.9 Phase 4:
  curriculum, habit compilation, and preference conditioning only become useful
  once task chaining exists.

## Milestone 6.9: Durable Coding Intelligence

Turn mew's persistent state into a coding advantage so the Nth iteration on the
same repository is measurably smarter than the 1st. This is the first
coding-track milestone whose goal is not parity with Codex CLI but a capability
Codex CLI cannot structurally have.

Target:

- five coding-domain memory types layered on existing typed memory:
  reviewer-steering, failure-shield, file-pair/symbol-edge, task-template, and
  reasoning-trace
- outcome-gated write gates per type, and a Revise step on the reuse path
- symbol/call-graph-aware durable index keyed to `(module, symbol_kind,
  symbol_name)`, with file paths as secondary keys, so refactors do not
  invalidate memory
- reviewer-diff capture of approved `(ai_draft, reviewer_approved, ai_final)`
  triples as raw material for a later preference store
- hindsight harvester that relabels failed trajectories into candidate cases,
  routed through reviewer approval before entering durable memory
- reasoning-trace harvester that distills `(situation, reasoning, verdict)`
  triples at shallow and deep abstraction levels
- scheduled rehearsal passes and novel-task injection as a memory-coverage
  metric, to prevent alignment decay and over-reliance on memory
- drift controls: reviewer veto with edge-propagating invalidation, confidence
  decay, growth budgets per type, and comparator rerun against M6.6 slots
- design spec: see
  `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` for the canonical
  schema, phase split, and proof protocol

Done when:

- on a predeclared set of 10 repeated task shapes, median wall time per task
  decreases over the first five repetitions with no increase in reviewer rescue
  edits
- at least three reviewer corrections from past iterations fire as durable
  rules in later iterations, and at least one would have caused a rescue edit
  if not caught
- at least two previously reverted approaches are blocked pre-implementation by
  durable failure-shield memory in a later iteration
- at least 80% of first-read file lookups in a post-Phase-1 iteration are
  served by the durable symbol/pair index rather than fresh search
- drift canary stays green across five consecutive iterations while memory
  accumulates, and at least one novel-task injection forces exploration
  without silent memory reliance
- after a deliberate 48-hour gap or a simulated alignment-decay pass, mew
  recovers prior convention usage within one iteration via a rehearsal pass,
  without reviewer steering
- at least two iterations explicitly recall a past reasoning trace and a
  reviewer confirms the recall shortened deliberation; at least one of those
  recalls lands on an abstract task, not a mechanical edit
- the M6.6 comparator is rerun with durable recall active and shows measurable
  gain over the M6.6 baseline attributable to the new memory

Why it matters:

- M6.5 through M6.8 track parity and operational autonomy. None of them use
  the one thing mew has that reactive CLI agents cannot have: durable state
  across sessions. Without M6.9, mew is a slower, safer Codex CLI with a
  daemon. With M6.9, mew's Nth visit to the same repo is structurally better
  than the 1st, which is the only long-term basis for a resident that a
  frontier model would prefer to inhabit over Claude Code or Codex CLI.

## Milestone 6.10: Execution Accelerators and Mew-First Reliability

Make mew-first implementation economical enough to use in place of Codex CLI
for ordinary bounded coding tasks. The milestone uses short-horizon Todo,
bounded exploration, structured rejection, and M6.12-style calibration
economics to reduce drift, rescue edits, and repeated read-only churn without
widening governance.

Target:

- session-scoped Todo state for the current resident coding loop, separate
  from persistent roadmap tasks and durable coding memory
- minimum Todo tools to write, update, and list 5-10 bounded items inside one
  session, with explicit status and duplicate-state guards
- `mew focus`, `mew brief`, or the equivalent reviewer-facing coding surfaces
  can show the current Todo state without silently promoting it into durable
  memory
- a mew-first calibration economics report that classifies the latest
  implementation attempts by success class, drift class, supervisor rescue
  cost, rejected patch family, and verifier/proof status using M6.12 evidence
  surfaces rather than a new instrumentation framework
- structured rejection/frontier state that turns reviewer rejection into a
  durable next action for the same task, including explicit stop rules for
  existing-scenario artifact tweaks, unpaired edits, missing focused
  verifiers, and generic cleanup substitutions
- a bounded Explorer helper for read-only repository exploration that can
  gather cited findings for the main session but cannot edit files, run shell,
  or mutate mew state
- Todo and structured rejection land before Explorer; Explorer may depend on
  Todo state, but not vice versa
- explicit non-goals for this milestone: no cross-session Todo persistence, no
  write-capable Explorer, no multi-Explorer concurrency, and no governance or
  milestone-close edits through these accelerators

Done when:

- Calibration D0 lands as a repeatable report or command that summarizes the
  latest 10 mew-first implementation attempts with clean/practical/partial/
  supervisor-rescue counts, drift classes, rescue edits, rejected patch
  families, and verifier/proof status
- Todo D1 lands with passing tests and is used in at least one real bounded
  coding iteration to keep short-horizon work decomposition visible without
  replacing persistent tasks
- Todo D2 surfaces the current Todo state in reviewer/operator views and
  prevents obvious duplicate `in_progress` or stale-item churn inside a
  session
- structured rejection/frontier D1 lands with passing tests and blocks at
  least one real or replayed abstract-task drift into existing-surface polish,
  generic cleanup, unpaired edits, or missing-verifier patches before
  implementation
- the latest 10 bounded mew-first implementation attempts after D0/D1 include
  at least 7 clean or practical mew-first successes, with `rescue_edits=0` for
  counted successes and every failure classified through the calibration
  economics surface
- Explorer D1 lands only if D0/D1 evidence shows read-only exploration churn
  remains a measured blocker; otherwise it is explicitly deferred without
  blocking M6.10 close
- the scope fence holds across the proof run: no cross-session Todo writes, no
  write or shell capability in Explorer, no multi-Explorer fan-out, and no
  milestone or roadmap-status edits through accelerator surfaces

Why it matters:

- M6.9 makes mew smarter across sessions, but its proof is polluted if mew
  cannot reliably implement bounded tasks without supervisor rescue. M6.10
  makes one session trustworthy and economical enough to use as the default
  implementation body, then M6.9 can resume durable-memory proof with cleaner
  autonomy evidence.

## Milestone 6.11: Loop Stabilization

Stabilize the agent loop structurally so mew can turn exact cached windows into
reviewer-visible dry-run patches and recover from drafting failures without
falling back into generic replanning.

Target:

- canonical `WorkTodo` drafting frontier persisted in session state, with
  session phase derived from it rather than competing with it
- deterministic `PatchDraftCompiler` that turns a tiny drafting proposal into
  either a validated patch artifact or one exact blocker
- replay bundles and offline fixtures for the known loop failure buckets,
  especially `#399` and `#401`
- a tiny drafting contract in write-ready mode that emits `patch_proposal` or
  `patch_blocker`, instead of a generic next-action tool plan
- drafting-specific recovery actions such as
  `resume_draft_from_cached_windows`, `refresh_cached_window`, and
  `revise_patch_from_review_findings`
- refusal separation at the API boundary so `model_returned_refusal` is a
  reachable blocker code rather than an opaque parse/backend failure
- design spec: see `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` and
  `docs/REVIEW_2026-04-22_LOOP_STABILIZATION_DESIGN_REVIEW.md`
- phase split:
  - core close-gate phases: 0-4
  - residual hardening phases: Phase 5 isolated review lane, Phase 6 executor
    lifecycle tightening, provisional read-only `MemoryExploreProvider`, and
    prompt/cache-aware drafting contract boundaries

Done when:

- Phase 0-4 of `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` are landed and
  validated; this closed the original M6.11 core gate
- `#399` becomes replayable offline and resolves to either a validated
  patch-draft path or one exact blocker without same-surface reread regression
- `#401` becomes replayable offline and recovery preserves the same drafting
  frontier via `resume_draft_from_cached_windows` instead of generic `replan`
- live draft failures emit replay bundles early enough to reproduce the first
  post-rewrite failures locally
- `WorkTodo.status` is the canonical source of truth for drafting state, and
  follow-status/resume expose the same blocker code and next recovery action
- refusal-shaped model output is classified distinctly from generic parse or
  transport failure at the work-loop boundary
- at least one bounded mew-first implementation slice completes through the new
  drafting path with reviewer-visible dry-run preview, approval/apply/verify,
  and no rescue edits attributable to the old drafting failure buckets
- `m6_11-*` dogfood scenarios for compiler replay, draft timeout, refusal
  separation, drafting recovery, and phase-4 regression are registered and pass
  under `proof-summary --strict` during M6.11 validation
- a 20-slice bounded iteration batch shows at least a 50% combined reduction in
  `#399` + `#401` incidence versus the documented pre-M6.11 baseline, or a
  reviewer-signed documented reason explains a smaller reduction
- a Phase 2/3 calibration checkpoint passes before Phase 3 starts, or an
  explicit Phase 2.5 calibration slice lands first; the checkpoint uses replay
  bundles to measure off-schema/refusal rates and prevent an unstable Phase 3
  rollout
- while M6.11 is open, measured and reviewer-rejected calibration samples are
  appended to `proof-artifacts/m6_11_calibration_ledger.jsonl` with head,
  scope, verifier, counted/non-counted status, blocker code, replay bundle
  path, and reviewer decision, so M6.12 can consume one canonical ledger
  instead of reconstructing method and evidence from scattered review notes

Residual hardening is done when:

- a validated patch artifact can pass through an isolated review lane before
  approval/apply, and review findings attach to the active `WorkTodo` rather
  than only to the exploratory transcript
- executor lifecycle states distinguish `queued`, `executing`, `completed`,
  `cancelled`, and `yielded`, and interrupted/fallback work leaves terminal
  records instead of orphaned in-flight state
- a read-only `MemoryExploreProvider` v0 can feed typed/durable memory and
  symbol/file-pair hits into the same explore handoff shape as filesystem
  exploration, without adding a second autonomous planner
- drafting prompt/cache metrics make stable contract text and dynamic payload
  boundaries observable, so cache-sensitive prompt changes are deliberate
- after the residual hardening, the next M6.9 bounded slice can run mew-first
  with clearer failure classification across review, executor lifecycle,
  memory explore, and task-spec causes

Why it matters:

- M6.9 assumes mew can turn durable recall into action. Without a stable agent
  loop, more memory only makes failures harder to debug. M6.11 hardens the
  drafting nerve path first so later durable memory, accelerators, and
  resident-operation work build on a replayable, contract-driven execution
  core rather than prompt luck.

## Milestone 6.12: Failure-Science Instrumentation

Turn the M6.11 calibration ledger and replay bundles into a small
operator-facing failure-science surface before resuming broad M6.9 durable
memory work.

Target:

- a read-only calibration ledger parser for
  `proof-artifacts/m6_11_calibration_ledger.jsonl`
- a derived classifier that maps each ledger row into reproducible v0
  archetypes without mutating the canonical ledger
- a single CLI surface:
  `mew proof-summary <artifact_dir> --m6_12-report`
- bundle-provenance accounting that separates ledger-only claims from
  bundle-derived rates and fails closed under `--strict` when referenced
  bundles are missing
- drift axes rendered explicitly even when all are still reserved with
  `count=0`
- no downstream governance wiring in v0; the report is an operator/reviewer
  reading surface only
- design spec:
  `docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md`

Done when:

- every row in the closed 127-row M6.11 calibration ledger is classified into
  exactly one v0 archetype or `unclassified_v0` with a row-ref warning, and the
  emitted counts match the design's post-priority totals
- every derived label traces back to a ledger row and, where applicable, a
  replay bundle reference
- text output fits the single-screen cockpit discipline while still showing
  reserved drift axes
- `--json` separates `canonical` from `derived`, includes
  `bundle_provenance`, and exposes `derived.classifier_priority`
- pre-closeout and post-closeout resolver modes are both tested, including
  strict-mode failures for missing bundles and closeout-index errors
- existing `proof-summary` default and `--m6_11-phase2-calibration` strict
  behavior remains unchanged
- no canonical ledger field is renamed, widened, or retroactively rewritten

Why it matters:

- M6.11 produced the evidence plane needed to debug mew's agent loop, but raw
  ledger rows are too hard to use during future long sessions. M6.12 turns that
  evidence into a compact instrument so M6.9 and later resident-coding work can
  choose the next hardening slice from recurrence data instead of scattered
  review notes.

## Milestone 6.13: High-Effort Deliberation Lane

Add a bounded escalation lane for hard supervised work-loop blockers without
making high-effort reasoning the default path.

Target:

- additive `WorkTodo.lane` state with `tiny` as the backward-compatible
  default
- a small lane registry for `tiny`, `mirror`, and `deliberation`, where only
  the existing tiny path remains write-capable in v0
- additive lane metadata in replay bundles, with legacy bundles interpreted as
  `lane=tiny`
- a mirror lane that proves non-authoritative lane identity and lane-scoped
  bundles without changing tiny-lane behavior
- M6.13.2 side-project implementation dogfood telemetry v0: a structured
  JSONL/report surface that records side-project mew-first implementation
  attempts before the side-project lane starts, so M6.16 can polish the
  implementation lane from comparable evidence instead of reply transcripts
- explicit deliberation model binding with requested/effective backend, model,
  effort, timeout, schema contract, and budget telemetry
- blocker-code escalation rules that refresh stale state instead of escalating,
  block policy-limit cases, and allow only eligible semantic blockers or
  reviewer-commanded attempts under budget
- fallback to tiny on missing binding, budget exhaustion, timeout, refusal,
  non-schema output, validation failure, or reviewer rejection
- reviewer-approved conversion of useful deliberation output into M6.9-style
  reasoning traces, never raw transcript storage
- design spec:
  `docs/DESIGN_2026-04-25_M6_13_DELIBERATION_LANE.md`
- resident architecture framing reference:
  `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`

Done when:

- old sessions with no lane normalize to `tiny`, existing active-todo fields
  keep their meanings, and tiny remains the default lane
- existing M6.11 replay bundles parse without migration, new lane metadata is
  additive, and non-tiny lane bundles can use a lane-scoped layout without
  breaking the legacy resolver
- Phase 1 proves tiny-lane behavior is unchanged: prompt, effort override,
  compiler path, and fallback semantics stay authoritative, and mirror-lane
  failure cannot fail a tiny run
- the mirror lane records a non-authoritative bundle that a reader can
  reconstruct separately from the authoritative tiny result
- at least one reviewer-command deliberation attempt and one automatic eligible
  blocker attempt run under explicit model binding and budget accounting
- at least one ineligible blocker is blocked from escalation, and at least one
  deliberation failure falls back to tiny without breaking the work loop
- cost events record budget checks, reservations, spend or estimates, blocks,
  and fallback
- lane attempts emit comparable telemetry for future calibration economics
  routing; M6.13 records the evidence needed for expected-value routing but
  does not require EV-based automatic routing in v0
- side-project dogfood can record a mew-first implementation attempt with
  task/session id, side project, worktree or branch, Codex CLI role
  (`operator`, `reviewer`, `comparator`, `verifier`, `fallback`, or
  `implementer`),
  first-edit latency, read turns before edit, files changed, tests run,
  reviewer rejections, verifier failures, rescue edits, outcome, failure
  class, repair requirement, proof artifacts, and commit
- one full internalization cycle is proven: deliberation solves or materially
  advances a hard task, reviewer approval writes a `source_lane=deliberation`
  reasoning trace, and a later same-shape task retrieves that trace through
  M6.9 ranked recall and is solved by tiny without re-invoking deliberation
- M6.9, M6.11, and M6.12 close gates remain unchanged

Why it matters:

- M6.9 gives mew durable memory and M6.11 stabilizes the drafting loop, but
  some blockers are genuinely too hard for a tiny lane. M6.13 gives mew a
  controlled way to ask for expensive reasoning, keep budgets and fallback
  visible, and then internalize the useful result so later tiny-lane work gets
  smarter instead of merely calling a stronger model again.

Architecture boundary:

- M6.13 keeps `tiny` as the canonical persisted lane id. `implementation` is a
  display/conceptual name for the authoritative tiny lane, not a v0 storage
  migration.
- M6.13 does not implement the future resident meta loop. It leaves lane
  decision, result, replay, and calibration contracts that a later supervisor
  can use.
- M6.13 does not broaden non-coding lanes (`research`, `routine`, `planning`)
  into active implementation scope. Those remain architectural direction until
  the coding lane substrate has proven itself.
- M6.13 does not start broad refactoring. Refactors are allowed only when they
  are required for the lane slice itself, or when the same reproducible
  mew-first failure class has blocked at least two attempts and the repair fits
  the M6.14 repair ledger.
- M6.13.2 does not build the side project, choose EV routing, auto-integrate
  Codex CLI, or harden the implementation lane. It only installs the
  measurement contract. Side-project implementation remains mew-first, while
  Codex CLI/Codex is recorded separately as operator, reviewer, comparator,
  verifier, fallback, or implementer.

## Milestone 6.14: Mew-First Failure Repair Ledger

Make M6.9+ implementation genuinely mew-owned by treating mew implementation
failures as first-class substrate blockers instead of letting Codex silently
rescue the product patch.

Target:

- the `mew-first-implementation-loop` skill is the operating contract for
  M6.9+ bounded roadmap/coding tasks
- when mew fails a bounded implementation task, Codex first classifies the
  failure and repairs the mew loop substrate if the failure is reproducible,
  rather than filling the product gap by hand
- active product milestones move to `pending` while their mew-first blocker is
  under repair, then resume at the same failed task after repair
- repair incidents are normally recorded as repair episodes under M6.14, not
  minted as M6.15/M6.16 just because another incident happened
- known M6.14 episode families include implementation-drift, wrong-target,
  scope, task-goal, patch-selection, verified-closeout, and stale-redraft
  failures
- every repair episode names the failed task/session, blocker class,
  replay/evidence source, focused fix, verifier, and retry target
- new repair milestones are exceptional and only for genuinely new product or
  architecture axes that do not fit M6.14
- direct Codex edits remain allowed for governance, roadmap/status, permission,
  safety, skill policy, and loop substrate surgery; they never count as
  mew-first autonomy credit

Done when:

- the skill and roadmap/status documents state that M6.9+ bounded
  roadmap/coding implementation is mew-first by default
- a real failed mew-first task is recorded with task/session id, rejected patch
  family, reviewer decision, and no hidden supervisor product rescue
- the active product milestone is paused as `pending` while the structural
  repair episode is active
- the identified substrate blocker is fixed with focused tests or replay
  evidence, and the same failed task is retried mew-first
- the retry either lands with `success_after_substrate_fix` and
  `rescue_edits=0`, or produces a new classified blocker that remains inside
  the active repair episode/ledger instead of drifting back to product rescue

Why it matters:

- M6.9's durable-memory proof only matters if mew can use that memory to
  implement. If Codex keeps rescuing failed implementation slices, mew may look
  more complete while its body remains unable to act. M6.14 turns each
  implementation failure into a repair loop for the body itself, which is the
  path toward mew surpassing reactive coding CLIs rather than being wrapped by
  one.

## Milestone 6.16: Codex-Grade Implementation Lane

Use the lane telemetry collected during M6.13 and later mew-first work to make
the authoritative implementation lane reliably usable for ordinary bounded
coding tasks.

Target:

- treat the persisted `tiny` lane as the authoritative implementation lane,
  while keeping compatibility with M6.13 lane metadata
- analyze recent mew-first lane attempts by rescue rate, approval rejection,
  verifier failure, first-edit latency, retry path, and failure class
- consume the M6.13.2 side-project dogfood ledger as a primary evidence source
  for implementation-lane bottlenecks; reply/chat logs are auxiliary evidence
- reduce measured implementation-lane friction without adding new write
  authority or hiding failures behind deliberation
- perform targeted refactor hardening only when a measured bottleneck or
  recurring failure class is named
- keep M6.14 as the repair path for structural mew-first failures
- preserve M6.11 patch-draft compiler, exact cached-window, scope-fence, and
  verifier discipline

Refactor policy:

- no aesthetic refactor
- no broad `work_loop.py` / `work_session.py` split without a named recurring
  failure class
- each refactor must record the baseline symptom, expected improvement,
  focused verifier or replay proof, and after evidence
- if the same failure class blocks M6.13 mew-first work twice before M6.16,
  handle it as a bounded M6.14 repair episode rather than waiting for M6.16

Start when:

- M6.13 has enough lane-attempt telemetry to identify the main implementation
  lane failure modes, or implementation-lane regression reopens the
  M6.6/M6.10 bar

Done when:

- a recent bounded mew-first coding cohort shows improved implementation-lane
  reliability against the prior measured baseline
- supervisor-authored product rescue is rare and every rescue is classified
  instead of hidden
- approval rejections are either reduced or produce fast, successful retries
  with recorded failure classes
- verifier failures have an explicit retry or repair path
- first-edit latency improves enough that ordinary source/test tasks feel
  usable compared with a fresh coding CLI
- any refactor used for the milestone names the measured bottleneck it reduced
  and records before/after evidence
- failures that are structural enter M6.14 repair episodes rather than being
  papered over by direct Codex edits

Why it matters:

- Lane composition only helps if the authoritative implementation lane has
  competent hands. M6.16 converts M6.13's lane telemetry into focused
  implementation-lane hardening instead of letting deliberation become a
  workaround for weak ordinary coding.

## Milestone 6.17: Resident Meta Loop / Lane Chooser

Add a resident supervisor that can propose task and lane dispatch decisions
from roadmap state, work-session state, memory, and calibration economics.

Target:

- a read-only or reviewer-gated meta loop that observes current roadmap focus,
  tasks, active sessions, metrics, memory, and user constraints
- task-selection and lane-dispatch proposals that explain their evidence and
  expected-value assumptions
- integration with existing M6.8.5 selector evidence instead of creating a
  second competing planner
- respect for M6.14 repair episodes when implementation-lane failures are
  structural
- no unattended automatic dispatch or milestone-close mutation in v0

Start when:

- implementation-lane telemetry is stable enough for lane-choice reasoning
- M6.13 has proven mirror/deliberation/internalization boundaries
- M6.16 has reduced ordinary implementation-lane friction enough that a
  supervisor would not simply orchestrate unreliable hands

Done when:

- the meta loop can produce a reviewer-visible next-task and lane-dispatch
  proposal with evidence from roadmap status, memory, and calibration metrics
- the proposal names the authoritative lane, any helper lanes, fallback,
  verifier, budget, and expected-value rationale
- reviewer approval is required before dispatch in v0
- after a completed work item, the meta loop can propose the next action or
  repair path without losing the active milestone gate
- no task status, roadmap status, or durable memory write is mutated without
  the appropriate lane/reviewer/policy gate

Why it matters:

- A resident AI is more than a work loop. It needs a supervisor that can decide
  what to work on, which body to use, when to ask, when to repair itself, and
  how to feed outcomes back into memory without drifting from the roadmap.

## Milestone 6.18: Implementation Failure Diagnosis Gate

Make mew-first implementation failures route through evidence-based diagnosis
before either same-task polish retry or M6.14 substrate repair.

Target:

- classify bounded mew-first implementation failures with a reviewer-visible
  `failure_scope`: `polish`, `structural`, `invalid_task_spec`,
  `transient_model`, or `ambiguous`
- record the evidence behind that scope: signals, confidence, recommended
  route, and a `structural_reason` when applicable
- treat diagnosis as triage, not omniscience: v0 recommends a route and keeps
  reviewer approval in the loop
- route `polish` to same-task retry, `structural` to a bounded M6.14 repair
  episode, `invalid_task_spec` to task/spec correction, `transient_model` to
  retry, and `ambiguous` to replay/proof collection before structural claims
- use `docs/ADOPT_FROM_REFERENCES.md`,
  `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`, and related reference
  reviews as evidence for structural repair candidates, not as automatic
  authority to perform broad architecture work
- keep larger structural changes such as structured approval/rejection,
  WorkTodo/patch lifecycle hardening, task-contract context bundles, and tool
  factory/per-turn policy behind named structural signals unless the change is
  needed to build the diagnosis surface itself

Start when:

- recent mew-first implementation attempts mix product progress, reviewer
  steering, supervisor rescue, and high rejection rates enough that ordinary
  polish and substrate failure are hard to distinguish
- M7 or later product work would otherwise keep generating implementation-lane
  evidence without a durable route decision

Done when:

- the mew-first attempt evidence model can record `failure_scope`,
  `confidence`, `signals`, `recommended_route`, and optional
  `structural_reason`
- implementation-lane metrics or reports expose polish/structural/ambiguous
  counts for recent attempts
- the `mew-first-implementation-loop` operating contract states the route:
  polish -> same-task retry, structural -> M6.14 repair, invalid spec -> task
  correction, transient -> retry, ambiguous -> collect replay/proof
- at least one recent mew-first failure is reclassified through the new
  diagnosis surface with cited evidence and a reviewer-visible route
- no structural repair is launched solely from model opinion; it must cite at
  least one recorded signal such as wrong target, task-goal miss, missing patch
  artifact, lost retry frontier, cached-window failure, policy/scope ambiguity,
  first-edit latency, or supervisor product rescue

Why it matters:

- M6.14 repairs are valuable only when the failure really belongs to the body.
  M6.18 prevents mew from treating every rejection as architecture work and
  every architecture smell as prompt polish. It is the gate that lets future
  M7+ dogfood produce either product progress or actionable implementation-lane
  repair data.

## Milestone 6.19: Terminal-Bench Compatibility

Make mew runnable as a Harbor / Terminal-Bench agent so implementation-lane
quality can be measured against established terminal-agent baselines.

Target:

- provide a headless mew entrypoint suitable for Harbor custom-agent execution
- add or document a Harbor agent wrapper that can run mew against
  Terminal-Bench tasks
- preserve mew's reviewer-gated work-session audit trail while running inside
  benchmark containers
- export enough benchmark artifacts to compare mew, Codex CLI, Claude Code,
  and other agent CLIs on the same task subset
- keep the first slice small: smoke subset first, full benchmark later
- avoid optimizing prompts or implementation-lane behavior before the
  measurement harness is trustworthy

Done when:

- Harbor can invoke mew as a custom agent without patching Harbor source
- a Terminal-Bench smoke subset runs through mew and produces per-task results
- the same subset can be run for at least one reference agent such as Codex CLI
  or Claude Code for side-by-side comparison
- mew stores per-task artifacts with instruction, command transcript,
  work-session/tool-call summary, verifier result, timeout status, and cost or
  token data when available
- the artifacts are stable enough that failures can be replayed or routed into
  M6.18/M6.14 diagnosis instead of becoming free-form anecdotes

Why it matters:

- Internal dogfood proves mew can improve itself, but it can overfit to mew's
  own repository and task style. Terminal-Bench gives the implementation lane a
  shared external yardstick against Codex CLI, Claude Code, and other terminal
  agents.

## Milestone 6.20: Terminal-Bench Driven Implement-Lane Debugging

Use Terminal-Bench results to improve mew's implementation lane with measured
failure classes and score targets instead of local anecdotes.

Target:

- establish a mew Terminal-Bench baseline on a fixed smoke or selected subset
- compare mew against Codex CLI and Claude Code on the same subset
- route failed tasks through the M6.18 diagnosis taxonomy:
  `polish`, `structural`, `invalid_task_spec`, `transient_model`, or
  `ambiguous`
- connect structural failures to bounded M6.14 repair episodes with before /
  after benchmark evidence
- track success rate, timeout rate, verification failure rate, first-edit
  latency, tool count, cost, and rescue/approval outcomes
- set an explicit score target before broad optimization

Done when:

- a baseline report exists with mew score, reference-agent score, task list,
  command lines, environment notes, and artifact paths
- at least one scored failure cohort is classified through M6.18 with cited
  benchmark evidence
- at least one implementation-lane repair or task-spec repair is chosen from
  benchmark evidence and rerun against the same task subset
- the score target is written in ROADMAP_STATUS before optimization, starting
  with a small target such as smoke-subset pass rate or a percentage of the
  reference Codex CLI score
- reruns show whether the repair improved, regressed, or did not affect the
  benchmark score

Why it matters:

- mew should become a coding body that frontier models would actually choose
  over standard agent CLIs. Terminal-Bench-driven debugging turns that goal into
  a scoreboard and a failure-science loop.

## Milestone 7: Senses - Inbound Signals

Let mew notice the user's working world through explicit, audited, read-only
signals.

Target:

- inbound signal registry with per-source gates and budgets
- file/git activity as the first-class source
- optional future sources such as calendar, mail digest, issue tracker, chat
  digest, browser/read-it-later, or RSS
- signal provenance in the audit trail
- suppression logic so observations do not become spam
- passive turns that distinguish "noticed" from "acted"

Done when:

- at least one non-file-system source can be enabled behind an explicit gate
- signals are journaled with source, timestamp, budget, and reason-for-use
- over a real day, mew produces at least one useful unsolicited observation
  from inbound signal evidence without fabrication or spam
- the user can see why mew noticed something and disable that source

Why it matters:

- A resident that only rereads its own state cannot be meaningfully passive.
  Senses give mew a controlled way to notice the world.

## Milestone 8: Identity - Cross-Project Self

Give mew a user-scope self that persists across projects while preserving
project-local boundaries.

Target:

- `~/.mew/` user scope alongside project `.mew/`
- user preferences, tone, durable decisions, model feedback, and identity cues
  stored at user scope
- project facts, codebase memories, work sessions, and audit bundles stored at
  project scope
- explicit promotion/demotion between scopes
- project routing when the user asks a global mew a project-specific question
- comparator proof against briefing a fresh CLI after project switch

Done when:

- a preference taught in project A is recalled in project B without re-teaching
- a project fact from A does not leak into project B unless explicitly promoted
- a resident can switch projects faster than a fresh CLI can be briefed, with a
  recorded comparator artifact
- the user can inspect and edit user-scope memory independently from
  project-scope memory

Why it matters:

- A resident should have continuity of self, not only continuity of a single
  repository.

## Milestone 9: Legibility - Human-Readable Companion

Make mew's durable state understandable to humans without requiring them to
read internal structures.

This absorbs the useful parts of
`docs/REVIEW_2026-04-20_M6_REFRAMING.md`. The earlier cross-project M6 proposal
is now covered by Milestone 8.

Target:

- narrative defaults for top-level commands with `--json` or `--raw` escape
  hatches
- `mew introduce` for first-run explanation
- `mew next` for a direct next-action sentence
- shareable single-screen summaries for focus, brief, resume, and work-session
  close
- actionable error messages with at least one concrete next command
- state diff surfaces that explain what changed between two moments
- reproducible demo scenarios that are self-explanatory without narration

Done when:

- a person who has never used mew can watch a 30-60 second recording and answer
  what mew is doing and why it is different from ordinary coding CLIs
- README and first-run flows get a new user to a working resident in under five
  minutes
- at least 80% of user-visible errors include a concrete next command
- narrative output refuses to invent missing facts

Why it matters:

- Invisible state gets turned off. Legibility makes the resident trustworthy
  enough for the user to keep it running.

## Milestone 10: Multi-Agent Residence

Let multiple model families inhabit the same mew without losing each other's
notes, permissions, or disagreements.

Target:

- durable sub-agent or peer-resident sessions with frozen permission context
- isolated memory scope for each resident plus shared project notes
- review/fix/verifier loops where different model families can participate
- disagreement artifacts with evidence, resolution, and residual risk
- restart-safe mailbox or handoff protocol between residents

Done when:

- two different model families complete a review-and-fix loop inside mew
- both residents survive at least one restart/reentry without losing the shared
  state
- disagreements become first-class auditable artifacts, not chat residue
- permission and memory boundaries remain inspectable

Why it matters:

- A single resident can become biased or stale. A shared habitat lets mew use
  multiple model strengths without dissolving into external orchestration.

## Milestone 11: Inner Life

Promote mood, journal, dream, and self-memory from generated hints into a
curated continuity of self that the resident owns.

Target:

- resident-owned self-description with audit history
- curated reading pile and codebase opinions
- journal/dream/mood/self-memory feedback loop
- user-visible but not user-authored identity evolution
- reversible edits and safety boundaries for self-description changes
- long-horizon resident review that separates real learning from narrative
  drift

Done when:

- after 30 days of real uptime, mew has a self-description that changed in
  response to work, feedback, failures, and recoveries
- those changes are auditable, reversible, and not fabricated
- the resident can explain how its current self-description affects its next
  action
- the user can reset, pin, or reject identity changes

Why it matters:

- This is where mew stops being only a durable process and starts feeling like a
  resident the model would want to return to.

## Non-Negotiable Safety Requirements

- All state transitions must be atomic.
- Every tool action must be journaled before execution and completed with
  status, outcome, and errors.
- Write actions must support rollback or a clearly recorded reason why rollback
  is impossible.
- Shell/network/destructive actions need explicit gates.
- Passive autonomy needs per-cycle budgets to prevent runaway loops.
- Recovery must re-check the world before retrying stale plans.
- The audit trail must stay readable without special tooling.
- The user must be able to pause, inspect, repair, and resume from `mew chat`.
- Daemon, signal, identity, multi-agent, and inner-life features must be
  explicitly inspectable and disableable.

## Roadmap Maintenance

`ROADMAP.md` defines the product path. `ROADMAP_STATUS.md` is the operational
dashboard.

- Keep `ROADMAP_STATUS.md` compact enough for context compression.
- Archive detailed evidence at milestone close.
- Do not promote polish, refactor, or side projects into active work unless
  they close a documented Done-when criterion.
- If a milestone feels wrong, rewrite the milestone gate explicitly instead of
  drifting around it.
- `mew-product-evaluator` should always answer the product question first:
  would a frontier model want to be inside mew after this milestone?
