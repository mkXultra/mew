# M6.24 Codex Long-Dependency Audit

Date: 2026-05-01 JST

Scope: `references/fresh-cli/codex`, inspected only for transferable architecture
patterns relevant to mew M6.24 long dependency/toolchain build reliability. This
is not a `compile-compcert` task-solver audit.

## Inspected Files

Codex reference files:

- `references/fresh-cli/codex/AGENTS.md`
- `references/fresh-cli/codex/codex-rs/core/gpt_5_codex_prompt.md`
- `references/fresh-cli/codex/codex-rs/core/gpt-5.2-codex_prompt.md`
- `references/fresh-cli/codex/codex-rs/core/prompt_with_apply_patch_instructions.md`
- `references/fresh-cli/codex/codex-rs/core/review_prompt.md`
- `references/fresh-cli/codex/codex-rs/core/src/tasks/mod.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tasks/regular.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tasks/compact.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tasks/review.rs`
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs`
- `references/fresh-cli/codex/codex-rs/core/src/session/review.rs`
- `references/fresh-cli/codex/codex-rs/core/src/session/rollout_reconstruction.rs`
- `references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/router.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/registry.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/events.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/shell.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/shell.rs`
- `references/fresh-cli/codex/codex-rs/core/src/exec.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/unified_exec.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs`
- `references/fresh-cli/codex/codex-rs/core/src/apply_patch.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/apply_patch.rs`
- `references/fresh-cli/codex/codex-rs/core/src/safety.rs`
- `references/fresh-cli/codex/codex-rs/core/src/compact.rs`
- `references/fresh-cli/codex/codex-rs/core/src/compact_remote.rs`
- `references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs`
- `references/fresh-cli/codex/codex-rs/exec/src/cli.rs`
- `references/fresh-cli/codex/codex-rs/exec/src/event_processor_with_human_output.rs`
- `references/fresh-cli/codex/codex-rs/exec/src/event_processor_with_jsonl_output.rs`

Mew grounding files inspected only to map implications:

- `src/mew/work_loop.py`
- `ROADMAP_STATUS.md`
- `docs/REVIEW_2026-05-01_ACCEPTANCE_PATTERNS_MEW_GAP.md`
- `docs/M6_24_EXTERNAL_BRANCH_HELP_PROBE_COMPILE_COMPCERT_SPEED_RERUN_2026-05-01.md`

## Reference Patterns

Codex does not appear to encode a domain-specific "long dependency build"
profile. Its reliability comes from a layered execution architecture:

- Prompt guidance gives general working rules: plan, inspect before editing,
  keep going through verification, prefer `rg`, use scoped tests, and be patient
  with known slow repo commands. The repo-local `AGENTS.md` has a Rust-specific
  patience rule, but that is project guidance, not executor policy.
- `SessionTask` separates regular work, compaction, review, shell-command, and
  undo tasks. A turn records active state, cancellation, telemetry, token usage,
  last agent message, and completion or abort events.
- `run_turn` loops model sampling and tool follow-up until there is no pending
  tool result. Tool calls are recorded as model-visible history items before and
  after execution.
- Tool execution is typed and centralized: model output becomes `ToolCall`
  through `ToolRouter`, is dispatched through `ToolRegistry`, and goes through a
  shared `ToolOrchestrator` for approvals, sandbox choice, permission hooks,
  network rules, and sandbox-denial retry.
- Shell failure is not hidden. Nonzero exits, timeouts, and sandbox denials
  become structured tool events plus model-visible output so the model can
  recover from real command evidence.
- Classic shell execution has a short default timeout. The transferable
  long-build architecture is instead `unified_exec`: start a PTY-backed process,
  return an output snapshot after a bounded yield, keep a `process_id`, allow
  later polling or stdin writes, retain capped output, and emit an eventual final
  `ExecCommandEnd` from an exit watcher.
- `unified_exec` treats long work as a live process, not as one oversized tool
  call. It has process caps, output caps, bounded poll windows, background
  timeout defaults, begin/delta/end events, and head/tail buffering so early
  configure failures and late link errors both remain visible.
- Patch application is its own grammar-backed tool. Codex intercepts attempts to
  run `apply_patch` through shell and reroutes them to the patch runtime, where
  patch safety, diffs, sandboxing, and events are handled consistently.
- Review is a distinct task mode. It spawns a constrained review conversation
  with review prompts, disabled web/collab tools, structured review output, and
  explicit enter/exit review events.
- Context compaction is a task and a checkpoint, not just a summary paragraph.
  Compaction records replacement history, token metrics, begin/completed events,
  remote/local compaction traces, and rollout reconstruction logic.
- Final validation in Codex is mostly prompt and process discipline plus typed
  evidence. Codex does not have mew-style acceptance finish blockers. The CLI
  event processors collect the final message and stream typed command, patch,
  compaction, and item events for external consumers.

## Where Reliability Is Represented

Tool execution is represented in `tools/router.rs`, `tools/registry.rs`,
`tools/orchestrator.rs`, tool handlers, tool runtimes, and protocol events.

Patch/apply/review is represented as separate tool/task surfaces:
`apply_patch_tool.rs`, `tools/handlers/apply_patch.rs`,
`tools/runtimes/apply_patch.rs`, `tasks/review.rs`, `session/review.rs`, and
`review_prompt.md`.

Context compaction is represented in `compact.rs`, `compact_remote.rs`,
`tasks/compact.rs`, `rollout_reconstruction.rs`, and protocol `CompactedItem`
and `ContextCompacted` events.

Timeouts and retries are distributed by failure layer:

- provider stream retries and fallback transport live in turn sampling;
- classic shell timeout and process-group termination live in `exec.rs`;
- long process yield/poll/background timeout behavior lives in `unified_exec`;
- sandbox retry is in `ToolOrchestrator`;
- cancellation/abort is in task/session control.

Final validation is not a hard executor gate. It is mainly prompt guidance,
review mode, final message collection, and the event/protocol evidence left
behind by commands and patches.

## Long-Build Encoding

Codex encodes long-build behavior as a combination of:

- prompt guidance for patience and validation;
- executor policy for timeouts, cancellation, sandbox retry, process retention,
  and output caps;
- task/turn state machines for sampling, tool follow-up, aborts, review, and
  compaction;
- typed event/log evidence for command begin/output/end, patch begin/update/end,
  turn completion, token usage, and compaction.

It does not encode "long dependency build" as a semantic detector taxonomy like
`LongDependencyProfile`, `RuntimeLinkProof`, or `RecoveryBudget`. Build recovery
is primarily model reasoning over preserved command output. The executor knows
how to keep long commands observable and resumable; it does not know that
CompCert runtime linking requires `libcompcert.a`.

## Mew Implications

Mew's current long-dependency surface is more domain-aware than Codex's, but too
much of that awareness is accumulating as prompt sections and narrow blockers.
The Codex pattern suggests moving authority into a generic evidence and process
substrate:

- Treat long dependency builds as resumable process attempts with stable ids,
  wall budget, command/cwd/env/sandbox metadata, yield chunks, exit status,
  duration, and retained head/tail output.
- Make `RuntimeLinkProof` a typed validation artifact attached to a build
  ledger, not only prompt text. The artifact should record the default
  invocation, compile/link smoke command, runtime-library location, install or
  default search path evidence, and final verifier result.
- Make `RecoveryBudget` executor-enforced attempt state: remaining wall budget,
  allowed recovery actions by class, and a mandatory reserve before final
  verifier or default-link proof. It should not rely only on the model
  remembering a prompt reserve.
- Replace repeated detector accretion with a small failure-state machine:
  `start -> running -> evidence_snapshot -> failure_class -> recovery_action ->
  validation_gate -> done/blocked`. Failure classes can be generic
  `timeout`, `sandbox_denied`, `dependency_version_mismatch`,
  `source_provenance_unverified`, `artifact_missing`, `runtime_link_failed`,
  `command_surface_invalid`, and `model_format_error`.
- Keep mew's stronger acceptance finish blockers, but feed them from the same
  typed build ledger used by resume state. Codex's evidence-first event model is
  the import; Codex's weak final gate is not.
- Put the "cheap compatibility branch before expensive alternate toolchain"
  ordering into recovery policy over the attempt ledger, not another
  `compile-compcert` prompt paragraph.
- Stop treating every new `compile-compcert` miss as proof that another prompt
  detector is needed. First ask which generic ledger field was absent or which
  recovery transition lacked enforcement.

## Divergence Risks

- Codex can rely on human-facing approval, interruption, and review flows. Mew's
  Terminal-Bench lane needs autonomous, noninteractive decisions with explicit
  wall-clock accounting.
- Codex's classic shell default timeout is not a long-build answer. Copying that
  surface would worsen M6.24. The relevant pattern is unified exec.
- Codex does not solve semantic dependency/toolchain diagnosis. Importing its
  architecture will make evidence better, but mew still needs generic build
  proof and recovery policy.
- Codex's final validation boundary is weaker than mew's current acceptance
  blocker system. Do not trade mew's finish authority for Codex-style final
  message discipline.
- Codex's full protocol/UI/event architecture is broad. Copying it wholesale
  would add complexity unrelated to the M6.24 reliability gap.
- Review subagents are useful as an optional audit mode, but M6.24 should not
  accidentally create a new authoritative helper lane after prior roadmap
  decisions kept the implementation lane narrow.

## Import Candidates

High:

- Unified exec process model: background process ids, bounded initial yield,
  poll/write continuation, exit watcher, process caps, output caps, and typed
  begin/delta/end events.
- Shared build-attempt ledger: command, cwd, env summary, sandbox/network mode,
  wall budget, process id, chunks, exit status, duration, artifacts, validation
  proofs, and recovery decisions.
- Central tool orchestration: one place for sandbox/permission/network/retry
  policy and one typed result shape for all shell-like tools.
- Executor-enforced recovery budget: reserve wall time for final default
  runtime-link proof and verifier, and block expensive recovery branches when
  budget is below threshold.
- Compaction checkpoint model: replacement history plus event-log trace so
  compact recovery resumes from durable evidence rather than prompt memory.

Medium:

- Patch grammar/interception pattern for tool-action hygiene.
- Review mode as a separate constrained task for post-change bug finding, kept
  non-authoritative for M6.24 scoring.
- Provider stream retry/backoff and model-visible stream error events.
- Head/tail output buffering for long build logs, with explicit omitted-middle
  accounting.
- Repo/project prompt layer for stable build patience and test guidance, used
  only after executor evidence and policy exist.

Low:

- Human approval and guardian flows.
- WebSocket/HTTPS transport fallback specifics.
- Full Codex app-server protocol taxonomy.
- Codex's exact final-answer and CLI rendering behavior.

## Avoid Copying

- Do not copy prompt accretion as architecture. Prompt sections are useful
  steering, but they should not be the source of truth for build state,
  recovery budgets, or runtime-link proof.
- Do not copy classic shell defaults for long builds. A short timeout plus a
  giant retry loop is the wrong shape.
- Do not generalize Codex's sandbox-denial heuristics into build diagnosis.
  Keyword heuristics are acceptable for sandbox denial, not for toolchain proof.
- Do not copy Codex's weak final validation boundary. Mew should keep hard finish
  blockers, but drive them from typed evidence.
- Do not import a full Codex-sized protocol stack when M6.24 needs a smaller
  build/process/evidence substrate.
- Do not add Terminal-Bench or `compile-compcert` special solvers. The import
  should be generic long-build process reliability and proof accounting.
