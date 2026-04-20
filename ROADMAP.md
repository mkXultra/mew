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
