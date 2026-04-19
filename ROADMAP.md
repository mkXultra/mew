# Mew Roadmap

## Goal

Make mew the task/coding execution shell that frontier models would prefer to inhabit over Claude Code or Codex CLI.

This does not mean copying those tools. Claude Code and Codex CLI are strong reactive coding CLIs. mew should become a resident AI shell: persistent, passive, recoverable, self-observing, and safe enough to keep running while the user is away.

## Shared Values

This roadmap aligns the current Codex view with the claude-ultra review.

- A model should remember what it was doing after time passes, restarts, or context compression.
- Tasks, questions, decisions, effects, failures, and recoveries should be durable.
- Passive operation should be calm: notice, decide, act, wait, and report without noisy repetition.
- The coding loop must be tight enough that a model does not wish it were back in Claude Code or Codex CLI.
- Every meaningful action should leave a human-readable audit trail.
- Autonomy must be gated. Silence is not permission.
- Recovery is a product feature, not only an implementation detail.
- The long-term advantage is persistence plus native execution, not orchestration alone.

## Current Position

mew already has the beginning of a resident brain:

- durable state
- task and question tracking
- passive runtime ticks
- THINK / ACT separation
- Codex Web API backend
- `mew chat`
- runtime effect journal
- `doctor` / `repair`
- dogfood scenarios
- self-improvement workflow entry points

The largest gap is hands.

Claude Code and Codex CLI are still much better at direct coding work because the model can read, edit, run commands, see output, and iterate inside a tight interactive loop. mew currently has strong state and autonomy, but too much real coding work still depends on dispatching external agents or coarse action cycles.

## Milestone 1: Native Hands

Build the smallest native tool-use loop that lets a resident model directly work on code.

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

- a model can inspect, edit, test, and fix a small task without delegating to an external coding agent
- the session can be interrupted and resumed with enough state to know what happened
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
- chat cockpit commands for work state, effects, tests, files touched, and next action

Done when:

- using mew for one focused coding task feels close to Claude Code / Codex CLI
- the model does not lose momentum while waiting for tool feedback

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
- continuity scoring for interrupted work:
  - working memory survived
  - risks preserved
  - runnable next action
  - approvals visible
  - recovery path visible
  - verifier confidence kept
  - bundle within budget
  - prior decisions preserved
- project memory search that affects model behavior
- user preference memory
- daily passive bundle for reentry across journal, mood, research, dream, and self-memory artifacts
- first-class journal generation that preserves daily reentry hints without a model call
- first-class mood scoring that tells the model and human whether mew is steady, concerned, or watchful
- static-feed morning paper ranking that can later grow into passive research collection
- first-class self-memory generation for traits, learnings, and continuity cues
- first-class dream generation for overnight-style reflection and reentry
- desktop-pet view model for passive state without coupling UI to raw state
- file watcher or git watcher for passive observation
- passive tick updates that refine the next action without spamming the user

Done when:

- returning to mew after interruption, context compression, terminal close, or a day away is faster than starting a new Claude Code or Codex CLI session
- the model can explain what it was doing, what changed, what is risky, and what it should do next

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

- a crashed runtime can restart and make a safe next move without manual reconstruction
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

Done when:

- mew can run multiple safe self-improvement loops with a clear audit trail
- human intervention is mostly approval, redirection, or product judgment

## Non-Negotiable Safety Requirements

- All state transitions must be atomic.
- Every tool action must be journaled before execution and completed with status, outcome, and errors.
- Write actions must support rollback or a clearly recorded reason why rollback is impossible.
- Shell/network/destructive actions need explicit gates.
- Passive autonomy needs per-cycle budgets to prevent runaway loops.
- Recovery must re-check the world before retrying stale plans.
- The audit trail must stay readable without special tooling.
- The user must be able to pause, inspect, repair, and resume from `mew chat`.

## First Build Target

Build the first native work loop.

Proposed first slice:

1. Add a `work_session` state concept for one task.
2. Add a minimal native tool dispatcher with read-only tools first: `read_file`, `search_text`, `glob`.
3. Add `run_command` behind an explicit `--allow-shell` gate.
4. Feed tool results back into the same work loop.
5. Journal every tool call as an effect.
6. Add chat commands to inspect the current work session.
7. Dogfood on a small mew bugfix task.

This is the point where mew starts changing from a passive task manager into a shell a model can actually inhabit.
