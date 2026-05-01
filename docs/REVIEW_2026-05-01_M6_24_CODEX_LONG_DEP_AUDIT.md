# REVIEW 2026-05-01 - Codex Long Dependency Audit For M6.24

Scope: local read-only inspection of `references/fresh-cli/codex`, compared
against the active M6.24 long-dependency docs:

- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/ADOPT_FROM_REFERENCES.md`
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`

## Executive Conclusion

Mew is **highly diverged** from Codex for this gap, even though M6.24 has
already adopted several adjacent ideas.

The divergence is not that Codex has a better CompCert-specific strategy.
Codex does not appear to carry a long-dependency profile comparable to
`LongDependencyProfile`, nor a runtime-link rule stack comparable to
`RuntimeLinkProof`. Its advantage is lower in the stack: Codex treats command
execution, terminal output, patching, retries, compaction, and resume as durable
evented substrate. Long dependency builds can keep running, be polled, preserve
head/tail evidence, survive context pressure, and return structured completion
metadata.

Mew's M6.24 chain has moved in that direction with `acceptance_evidence`,
`finish_gate`, prompt sections, `RecoveryBudget`, `CompactRecovery`, and
resume blockers. But the current repair history is still dominated by
detector/profile accretion around one benchmark shape. That is the material
architectural gap.

## Codex Patterns Found

### Durable Architecture Concepts

1. **Interactive/background process execution is a first-class runtime.**

   Codex's unified exec layer explicitly manages long-lived process sessions,
   not just one-shot command calls:

   - `references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs`: module
     contract says unified exec manages interactive processes, output caps,
     centralized approval/sandbox/retry, and process handles.
   - `.../unified_exec/mod.rs:56-67`: clamps yield windows, defines a
     five-minute default background terminal timeout, 1 MiB output cap, and
     process-count limits.
   - `.../unified_exec/process_manager.rs:231-335`: starts a process, emits
     begin events, starts streaming output, and stores the live process before
     waiting for initial output so an interrupted turn does not drop the last
     handle.
   - `.../unified_exec/process_manager.rs:408-517`: `write_stdin` doubles as
     interactive input and polling; empty polls can wait longer than regular
     writes and return `process_id`, `exit_code`, wall time, and a chunk id.
   - `.../unified_exec/process_manager.rs:596-650`: process entries are stored,
     pruned, warned about, and watched for exit.
   - `.../unified_exec/process_manager.rs:859-963`: output collection drains
     chunks until a deadline, handles exit signals, and pauses deadlines during
     out-of-band elicitation.

   This is the strongest Codex pattern for M6.24. A long build is not forced to
   fit inside one model turn or one command response.

2. **Terminal output is streamed, bounded, and typed.**

   Codex represents command execution as typed events and bounded transcript
   snapshots:

   - `.../unified_exec/async_watcher.rs`: streams output deltas and emits a
     single command-end event after process exit and output drain.
   - `.../unified_exec/head_tail_buffer.rs`: preserves bounded head/tail output
     instead of relying on an arbitrary final log tail.
   - `.../tools/context.rs:375-476`: model-facing exec output includes
     `event_call_id`, `chunk_id`, wall time, optional `process_id`, optional
     `exit_code`, `original_token_count`, and truncated output.
   - `.../protocol/src/protocol.rs:3062-3157`: protocol types distinguish
     command begin, output delta, terminal interaction, and command end.
   - `.../protocol/src/exec_output.rs:16-46`: command output stores stdout,
     stderr, aggregated output, duration, and `timed_out`.
   - `.../protocol/src/exec_output.rs:62-139`: shell bytes are decoded with
     encoding detection before fallback.
   - `.../utils/output-truncation/src/lib.rs:12-19`: truncated output records
     total line count and middle-truncates under a budget.

   This makes build evidence durable and inspectable without requiring the
   model to infer state from a lossy prompt paragraph.

3. **Approval, sandbox selection, and retry live in one orchestrator.**

   Codex centralizes command retry mechanics:

   - `.../core/src/tools/orchestrator.rs:1-8`: module contract says it owns
     approval, sandbox selection, and retry semantics.
   - `.../core/src/tools/orchestrator.rs:122-180`: approval handling separates
     skipped, forbidden, needs approval, rejected, timed out, and aborted paths.
   - `.../core/src/tools/orchestrator.rs:260-350`: sandbox denial can retry
     without sandbox when policy allows, with a structured retry reason.
   - `.../core/src/tools/sandboxing.rs:70-115`: approval caching is scoped by
     approval keys.
   - `.../core/src/tools/sandboxing.rs:160-255`: `ExecApprovalRequirement`
     and first-attempt sandbox overrides are explicit types.

   The relevant M6.24 lesson is not "copy Codex sandboxing." It is that retry
   and permission recovery are not modeled as one-off resume blockers.

4. **Patch application has structured lifecycle evidence.**

   Codex does not treat patches as plain shell text:

   - `.../core/src/tools/handlers/apply_patch.rs:39-100`: streaming tool-input
     deltas are parsed into patch progress events.
   - `.../core/src/tools/handlers/apply_patch.rs:378-437`: patch input is
     re-parsed, verified, permission-scoped, run through the orchestrator, and
     emitted with begin/end events.
   - `.../core/src/tools/handlers/apply_patch.rs:469-544`: shell-shaped
     `apply_patch` calls are intercepted and routed through the same patch
     runtime.
   - `.../core/src/tools/runtimes/apply_patch.rs:180-236`: runtime emits stdout
     and stderr deltas, exit code, duration, and retryable sandbox denial.
   - `.../apply-patch/src/parser.rs:126-178`: patch parsing has strict,
     lenient, and streaming modes; streaming parse is explicitly for progress,
     not application.
   - `.../apply-patch/src/invocation.rs:134-206`: verified patch parsing
     resolves paths and reads existing file content before producing changes.
   - `.../core/src/tools/events.rs:170-210` and `:450-535`: begin/end patch
     events and turn diffs are emitted only from the structured patch path.

   The durable concept is a normalized write/evidence lifecycle. The local
   prompt heuristic is merely "use apply_patch."

5. **Context budget and resume are system services, not prompt reminders.**

   Codex has pre-turn and mid-turn compaction plus rollout reconstruction:

   - `.../core/src/session/turn.rs:154-167`: pre-sampling compaction can run
     before regular context updates are recorded.
   - `.../core/src/session/turn.rs:445-503`: after each sampling request,
     Codex checks token usage, pending input, and model follow-up; if context
     is at the auto-compact limit and work must continue, it runs mid-turn
     compaction and continues.
   - `.../core/src/session/turn.rs:963-1095`: sampling requests retry stream
     errors with backoff and can switch transport after retry exhaustion.
   - `.../core/src/compact.rs:65-84`: auto compaction can be run inline.
   - `.../core/src/compact.rs:170-243`: compaction uses a retry budget and
     trims oldest history items on context-window overflow.
   - `.../core/src/compact.rs:258-278`: replacement history is installed,
     optional initial context is re-injected, and token usage is recomputed.
   - `.../core/src/compact.rs:412-492`: compacted history preserves recent
     user messages under a token limit and inserts canonical initial context at
     a known boundary.
   - `.../core/src/session/mod.rs:1142-1230`: resume/fork reconstructs initial
     history from rollout items.
   - `.../core/src/session/mod.rs:2452-2470`: compacted replacement history is
     persisted.
   - `.../core/src/session/mod.rs:2747-2776`: `TurnContextItem` is persisted so
     resume/lazy replay can recover the durable context baseline.
   - `.../core/src/session/rollout_reconstruction.rs`: rollout replay handles
     replacement-history checkpoints and context baselines.
   - `.../protocol/src/protocol.rs:2825-2863`: `TurnContextItem` persists cwd,
     policy, model, and other turn context.

   Mew's `CompactRecovery` is directionally aligned, but Codex's mechanism is
   event/history reconstruction rather than a low-wall prompt variant alone.

6. **Provider, stream, and auth recovery are handled below the task loop.**

   Codex retries or recovers transport/auth failures without turning them into
   task-specific long-dependency rules:

   - `.../core/src/session/turn.rs:1052-1095`: stream failures are retried with
     provider retry limits and "Reconnecting..." feedback.
   - `.../core/src/client.rs:1188` and `:1301`: unauthorized responses can go
     through auth recovery.
   - `.../core/src/client.rs:1563-1571`: WebSocket transport can fall back to
     HTTP at session scope.
   - `.../core/src/compact.rs:170-243`: compaction has its own retry behavior.

7. **Tool dispatch is parallel-safe and cancellation-aware.**

   - `.../core/src/tools/parallel.rs:43-109`: tool calls route through a shared
     runtime; tools that support parallelism take a read lock, others take a
     write lock.
   - `.../core/src/tools/parallel.rs:110-183`: aborted shell/unified-exec tools
     return a model-visible wall-time message instead of disappearing.
   - `.../core/src/session/turn.rs:1775-1803` and `:1809-2235`: in-flight tool
     futures are drained before turn diff emission and final sampling result.

### Prompt Heuristics And Local Habits

These are not the reason Codex is more robust on long builds:

- base instructions such as prefer fast search, persist with tests, or use
  `apply_patch`
- the textual `apply_patch` grammar given to the model
- AGENTS.md-style repository guidance
- prompt-level review/final-answer formatting instructions
- any model habit to "run a verifier" after editing

They help only because the runtime below them can preserve process state,
typed output, write evidence, and context continuity. Importing the prompt text
without the substrate would mostly reproduce M6.24's current profile accretion
pattern.

## Comparison To Current M6.24 Approach

### `LongDependencyProfile`

Codex has no equivalent domain-specific long-dependency profile. It relies on a
generic command/session substrate that lets the model observe long work,
continue after partial output, poll the same process, and inspect exact
completion metadata.

Mew should treat `LongDependencyProfile` as a temporary steering layer. Its
content should shrink as generic exec/evidence/resume substrate becomes real.

### `RuntimeLinkProof`

Codex does not encode a CompCert-like runtime-link proof policy. It stores
terminal command evidence, exit codes, patch/write events, and final output.

Mew's `RuntimeLinkProof` is valid as a product-specific acceptance contract,
but repeated additions such as default path, install target, subdir target, and
link recovery are a sign that the generic artifact-proof substrate is still too
weak. The proof should be backed by typed terminal evidence refs, not by
ever-growing textual examples.

### `RecoveryBudget`

Mew's `RecoveryBudget` reserves wall clock after validation failures. Codex's
more durable mechanism is different: long-running commands can outlive the
initial yield and be resumed or polled by `write_stdin`. That turns "reserve
time for another command" into "do not force the current command to be a
one-shot."

Mew should keep `RecoveryBudget` short term, but the stronger import is a
background command session with pollable state and bounded transcript
snapshots.

### Resume Blockers

Codex persists evented history and reconstructs context baselines. It does not
need a growing taxonomy of resume blockers to recover what happened.

Mew's blockers are useful diagnostics, but too many now encode task-order
strategy. Once command events and evidence refs exist, several blocker classes
should collapse into generic categories:

- final artifact unproven
- terminal command timed out
- proof command failed
- post-proof mutation occurred
- long command still running
- command output truncated but head/tail retained
- verification older than latest write

### `acceptance_evidence`

This is the most Codex-aligned M6.24 substrate so far. The 2026-05-01 decision
ledger already rejected benchmark-semantic parsing and moved toward terminal
tool evidence, `evidence_refs`, strict final-artifact proof, finish blockers,
and post-proof mutation guards.

The remaining gap is to make those refs point at durable command/patch events
with event ids, exit code, duration, timeout status, cwd, command surface, and
bounded output. That would look much closer to Codex's
`ExecCommandEndEvent`/`PatchApplyEndEvent` model.

### `work_session`

Mew's `work_session` currently carries much of the long-dependency intelligence
in resume state and suggested next actions. Codex's equivalent reliability is
more distributed:

- process manager owns command lifetime
- protocol owns command/patch events
- context manager owns truncation and token state
- compact/rollout reconstruction owns resume continuity
- orchestrator owns retry/sandbox decisions
- turn loop owns follow-up and in-flight tool draining

Mew should avoid making `work_session` the permanent home for every long-build
repair.

## What Mew Should Adopt Now

1. **A minimal unified exec equivalent.**

   Implement the smallest local form of Codex's process-session contract:

   - command returns a `process_id` when still running after an initial yield
   - poll/write action can resume the same process
   - command output has `chunk_id`, wall time, `exit_code`, `timed_out`,
     `original_token_count`, and bounded head/tail transcript
   - process exit emits a durable terminal event
   - long build commands no longer have to fit in one tool response

2. **Typed terminal evidence as the source of artifact proof.**

   Extend `acceptance_evidence` so final-artifact proof resolves against typed
   command events, not just tool-output text. Include command, cwd, status,
   exit code, timeout flag, duration, and output excerpts.

3. **Patch/write lifecycle events.**

   Mew does not need Codex's exact Rust patch parser, but it should persist
   write attempts as begin/end evidence with affected paths, success/failure,
   diff hash or patch hash, and terminal stdout/stderr. Failed writes must be
   visible but non-gating for acceptance.

4. **Event-backed resume reconstruction.**

   Add a compact event/evidence index that `work_session` can summarize after
   compression or interruption. This is the mew-sized analogue of Codex
   rollout reconstruction and `TurnContextItem`, not a wholesale architecture
   replacement.

5. **Centralize retry/error recovery below the benchmark strategy.**

   Auth refresh already moved in this direction. The next substrate should make
   model-stream retry, malformed/empty model response recovery, transport
   fallback, and command timeout status generic runtime facts, not individual
   long-dependency blockers.

6. **Install an anti-accretion gate.**

   Before adding another `LongDependencyProfile` or resume-blocker clause, the
   controller should classify the failure as either:

   - missing typed execution/evidence substrate
   - missing context/resume substrate
   - missing generic artifact-proof rule
   - truly new domain strategy

   Only the last category should add profile text.

## What To Defer

- Do not import Codex's sandbox implementation wholesale. `docs/ADOPT_FROM_REFERENCES.md`
  and the missing-pattern survey already treat full sandbox import as
  platform-heavy for mew's current shape. Adopt the orchestrator concept, not
  the full OS policy stack.
- Do not copy Codex `TurnStatus::Completed` as semantic task acceptance.
  Existing M6.24 acceptance work correctly makes mew's done gate stronger than
  Codex's protocol completion.
- Do not copy Codex prompt instructions as a standalone fix.
- Do not build Codex's remote exec-server/app-server split before a local
  process-session MVP exists.
- Do not add multi-agent/review machinery for this gap unless a later M6.24
  decision selects it explicitly.

## Risks Of Continuing Detector And Profile Accretion

- **Benchmark overfit.** The repair sequence is increasingly centered on
  `compile-compcert` pathologies: compatibility overrides, runtime install,
  default runtime path, vendored dependency patching, branch probes, and
  subdir targets.
- **Prompt budget waste.** `LongDependencyProfile`, `RuntimeLinkProof`,
  `RecoveryBudget`, `CompactRecovery`, `DynamicFailureEvidence`, and context
  JSON all compete for the same model budget.
- **Conflicting blockers.** As blocker count grows, stale suppression and
  ordering rules become their own failure class.
- **Weak transfer.** A new long dependency task can fail in a novel way because
  the underlying process/evidence/resume substrate still lacks generic
  continuation.
- **Authority drift.** If `acceptance.py`, `work_session.py`, and prompt
  guidance each carry their own proof rules, they can disagree about whether an
  artifact is proven.
- **Hidden rescue edits.** Repeated narrow repairs can mask the fact that mew
  still lacks a robust way to keep a long build alive, poll it, and preserve
  exact evidence across context compression.

## Concrete Next Investigation And Design Questions

1. What is the smallest mew `exec_command`/`poll_process` contract that can
   preserve a real long build across model turns?
2. Can `acceptance_evidence` cite durable command event ids instead of parsed
   `tool #N` text while keeping backward compatibility?
3. What head/tail byte and token limits preserve build failure diagnostics
   without bloating prompt context?
4. Which existing long-dependency blockers become redundant once terminal
   events include command, cwd, exit code, timeout, duration, and output
   excerpts?
5. How should `work_session` reconstruct after context compression from an
   event/evidence index rather than a prose resume bundle?
6. Where should post-proof mutation guards live once patch/write events are
   first-class?
7. Can `RecoveryBudget` be redefined as "reserve budget for recovery planning
   and process polling" rather than "reserve time to run another one-shot
   command"?
8. What controller rule stops new profile clauses unless the failure is proven
   not to be substrate-shaped?

## Bottom Line

Codex's transferable advantage for M6.24 is not a better long-dependency
prompt. It is a durable execution and evidence architecture. Mew should keep
the current same-shape `compile-compcert` repair loop disciplined, but the next
structural investment should be an evented, pollable command substrate tied to
typed acceptance evidence. That is the cleanest way to reduce future
detector/profile accretion while preserving the M6.24 no-benchmark-specific-
solver boundary.
