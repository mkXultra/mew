# M6.12 Calibration Input From Externals

Date: 2026-04-23
Status: design input, not a commitment

## Purpose

Capture the external lessons from `Hermes`, `OpenClaw`, `Codex`, and
`Vellum Assistant` that should inform `M6.12 Calibration ergonomics`, without
importing their architecture or turning external project shape into a mew
roadmap commitment.

This memo is intentionally narrow:

- source of truth remains mew's own replay bundles, calibration ledger, and
  counted/non-counted cohort data
- external systems contribute priors, failure archetypes, and evaluation
  heuristics
- this document does not propose adopting Hermes/OpenClaw/Codex/Vellum loop
  architecture
- this document does not authorize widening the M6.11 canonical ledger schema
  while M6.11 is still open

## Short Conclusion

The strongest shared lesson from `Hermes`, `OpenClaw`, `Codex`, and
`Vellum Assistant` is that the hardest part of agent-loop stabilization is
usually not the visible outer loop. The hardest part is preserving correct
state under pressure and across lifecycle boundaries:

- context compression / compaction
- session continuity
- tool-call normalization and replay integrity
- fallback / retry classification
- queue / drain / recovery around detached or delayed work
- interrupt / shutdown / overloaded-boundary behavior
- drift across task frontier, context, replay, approval, and UI surfaces
- calibration feedback loops and token-estimate drift
- pressure cascades across compaction, tool results, media, and memory injection

For `M6.12`, this implies that calibration ergonomics should optimize for
finding:

1. which subsystem keeps reappearing across slices
2. which subsystem accumulates multiple distinct failure classes
3. which subsystem remains central enough that many surfaces fail when it drifts

The best proxy for "hardness" is therefore not raw commit count, PR count, or
test count. It is:

`recurrence across slices/releases x failure-class diversity x architectural centrality`

## External Findings

### Hermes

Hermes appears to have spent repeated stabilization effort on:

- context compression + prompt caching + session continuity
- streaming / tool-call / response-normalization integrity
- gateway runtime state, especially approval routing, stuck sessions, cached
  agent hygiene, and timeout/activity tracking

The strongest signal is not simply volume. It is that the same areas continue
to reappear across multiple release waves, including releases that already call
themselves hardening or resilience passes.

Relevant evidence:

- `v0.2.0` already includes compression/retry/tool-call repair and blocking
  post-compression re-read/search loops
  [RELEASE_v0.2.0.md](/tmp/hermes-agent/RELEASE_v0.2.0.md:52)
- `v0.5.0` still has compression, streaming, retry, and cross-loop deadlock
  work
  [RELEASE_v0.5.0.md](/tmp/hermes-agent/RELEASE_v0.5.0.md:65)
  [RELEASE_v0.5.0.md](/tmp/hermes-agent/RELEASE_v0.5.0.md:88)
- `v0.7.0` explicitly calls out `Gateway Hardening` and a `compression death
  spiral`
  [RELEASE_v0.7.0.md](/tmp/hermes-agent/RELEASE_v0.7.0.md:23)
  [RELEASE_v0.7.0.md](/tmp/hermes-agent/RELEASE_v0.7.0.md:57)
- `v0.8.0` and `v0.9.0` still need inactivity timeouts, tool-use guidance,
  empty-response acceptance, stream repair, and turn-exit diagnostics
  [RELEASE_v0.8.0.md](/tmp/hermes-agent/RELEASE_v0.8.0.md:17)
  [RELEASE_v0.8.0.md](/tmp/hermes-agent/RELEASE_v0.8.0.md:21)
  [RELEASE_v0.8.0.md](/tmp/hermes-agent/RELEASE_v0.8.0.md:69)
  [RELEASE_v0.9.0.md](/tmp/hermes-agent/RELEASE_v0.9.0.md:74)

Drift-specific evidence:

- compression summaries are explicitly marked as `REFERENCE ONLY`, name an
  `Active Task`, and tell the model not to treat summarized questions as
  current instructions
  [agent/context_compressor.py](/tmp/hermes-agent/agent/context_compressor.py:38)
- transcript offset tests cover losing new messages or replaying all prior
  messages when raw gateway history diverges from filtered model-visible
  history
  [test_transcript_offset.py](/tmp/hermes-agent/tests/gateway/test_transcript_offset.py:1)
  [test_transcript_offset.py](/tmp/hermes-agent/tests/gateway/test_transcript_offset.py:122)
- retry replacement tests ensure `/retry` replays the original user text and
  replaces the prior turn instead of appending duplicate state
  [test_retry_replacement.py](/tmp/hermes-agent/tests/gateway/test_retry_replacement.py:13)
- approval isolation tests prevent approvals or callbacks from drifting across
  concurrent sessions
  [test_approval_isolation.py](/tmp/hermes-agent/tests/acp/test_approval_isolation.py:1)

### OpenClaw

OpenClaw appears to have concentrated hardest on:

- compaction + transcript/tool-result integrity + overflow recovery
- failover / fallback classification
- background-task / subagent / queue-drain runtime correctness

Again, the strongest signal is recurrence under different failure shapes:

- the same compaction and transcript integrity surface keeps returning
- the same fallback classification surface keeps needing provider-specific
  expansion
- detached work plumbing repeatedly reappears as a mixed signal: some of it is
  correctness hardening, and some of it is product/runtime expansion

Relevant evidence:

- `2026.1.8` explicitly says `Agent loop: compaction, pruning, streaming, and
  error handling hardened`
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6323)
- the same release also names `Agent loop + compaction` fixes
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6331)
- `2026.1.9` and `2026.1.10` continue with `Agents/Runtime`, transcript,
  reasoning-on-tool-only-turns, auto-compaction overflow recovery, single-writer
  session locks, and duplicate tool-result repair
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6289)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6302)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6121)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6139)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6194)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:6249)
- later releases still add timeout-recovery compaction, tool-result guard
  overflow recovery, queue/drain reliability, and background task control plane
  work
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:1544)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:1996)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:1997)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:1233)
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:3356)

Drift-specific evidence:

- OpenClaw documents a stable system-prompt prefix and volatile suffix so
  per-turn metadata does not drift or invalidate the stable prompt/cache
  boundary
  [prompt-caching.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/docs/reference/prompt-caching.md:166)
- fallback retries preserve the original prompt body so the retrying model keeps
  the active task instead of seeing only a generic continuation
  [appcast.xml](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/appcast.xml:91)
- orphaned active-turn user text is carried into the next prompt before
  transcript repair so mid-run follow-ups are not silently dropped
  [CHANGELOG.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/CHANGELOG.md:331)
- approval-backed execution freezes a canonical `systemRunPlan` and rejects
  later command/cwd/session mutation as an approval mismatch
  [exec-approvals.md](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/docs/tools/exec-approvals.md:402)
- UI tests and gateway code guard against stale history responses and reloads
  during active runs so rendered chat does not drift from the selected session
  [app-gateway.ts](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/ui/src/ui/app-gateway.ts:448)
  [chat.test.ts](/Users/mk/dev/personal-pj/mew_inspect/references/fresh-cli/openclaw/ui/src/ui/controllers/chat.test.ts:779)

### Codex

Codex appears to concentrate hardest on:

- queue pressure, drain behavior, and backpressure semantics
- explicit lifecycle boundaries for thread/turn/item, interrupt, and shutdown
- replay/resume/fork/compaction correctness around persisted conversation state

The important signal here is slightly different from Hermes/OpenClaw. Codex
shows that even when the outer agent loop is not the dominant abstraction,
stability work still piles up at the same boundaries:

- how pressure is measured
- how overload is surfaced
- how lifecycle states are named
- how interruption and graceful shutdown preserve invariants

Relevant evidence:

- the TUI chunking design explicitly optimizes for queue pressure, stable
  ordering, hysteresis, and traceable mode transitions rather than only raw
  streaming speed
  [docs/tui-stream-chunking-review.md](/Users/mk/dev/tech_check/codex/docs/tui-stream-chunking-review.md:12)
  [docs/tui-stream-chunking-review.md](/Users/mk/dev/tech_check/codex/docs/tui-stream-chunking-review.md:54)
- the chunking validation process treats queue depth, queued age, transition
  count, and rapid re-entry as first-class metrics
  [docs/tui-stream-chunking-validation.md](/Users/mk/dev/tech_check/codex/docs/tui-stream-chunking-validation.md:29)
  [docs/tui-stream-chunking-validation.md](/Users/mk/dev/tech_check/codex/docs/tui-stream-chunking-validation.md:44)
- the exit/shutdown design uses explicit terms and explicit state boundaries
  for `Exit`, `Shutdown`, `Interrupt`, and `ShutdownComplete`
  [docs/exit-confirmation-prompt-design.md](/Users/mk/dev/tech_check/codex/docs/exit-confirmation-prompt-design.md:8)
  [docs/exit-confirmation-prompt-design.md](/Users/mk/dev/tech_check/codex/docs/exit-confirmation-prompt-design.md:16)
  [docs/exit-confirmation-prompt-design.md](/Users/mk/dev/tech_check/codex/docs/exit-confirmation-prompt-design.md:57)
- the app-server interface defines bounded queues, retryable overload
  semantics, and explicit `Thread` / `Turn` / `Item` lifecycle primitives
  instead of leaving those boundaries implicit
  [codex-rs/app-server/README.md](/Users/mk/dev/tech_check/codex/codex-rs/app-server/README.md:45)
  [codex-rs/app-server/README.md](/Users/mk/dev/tech_check/codex/codex-rs/app-server/README.md:64)
  [codex-rs/app-server/README.md](/Users/mk/dev/tech_check/codex/codex-rs/app-server/README.md:77)

Drift-specific evidence:

- compact/resume/fork tests assert that model-visible history matches the
  expected sequence after compaction, rollback, resume, and fork
  [compact_resume_fork.rs](/Users/mk/dev/tech_check/codex/codex-rs/core/tests/suite/compact_resume_fork.rs:8)
- compaction summaries are explicitly designed to help the next LLM continue
  the same work rather than restart or duplicate it
  [prompt.md](/Users/mk/dev/tech_check/codex/codex-rs/core/templates/compact/prompt.md:9)
- steered user input must stay pending through compaction and only appear after
  the correct post-compaction continuation
  [pending_input.rs](/Users/mk/dev/tech_check/codex/codex-rs/core/tests/suite/pending_input.rs:560)
- `turn/steer` requires an `expectedTurnId`, and review or manual compaction
  turns reject same-turn steering
  [codex-rs/app-server/README.md](/Users/mk/dev/tech_check/codex/codex-rs/app-server/README.md:680)
- pending approvals and input prompts are replayed only while unresolved, so
  resolved prompts do not reappear after thread switches
  [pending_interactive_replay.rs](/Users/mk/dev/tech_check/codex/codex-rs/tui/src/app/pending_interactive_replay.rs:731)
- reviewer prompts pin findings to bugs that the original author would fix,
  reducing review drift away from intended patch correctness
  [review_prompt.md](/Users/mk/dev/tech_check/codex/codex-rs/core/review_prompt.md:5)

### Vellum Assistant

`Vellum Assistant` is closer to mew at the primitive layer than at the product
category layer. It has memory, identity files, proactive wake paths, scheduler
ticks, watchers, task queues, an engineered tool loop, compaction, overflow
recovery, and calibration hooks. But its center of gravity is a user-facing
personal assistant, not an AI habitat that recursively implements its own
runtime.

For `M6.12`, the useful import is therefore failure science, not product shape.
Vellum gives strong examples of:

- calibration drift: token-estimate calibration must not learn from its own
  corrected estimate
- context-pressure cascade: overflow is not one error; it can propagate through
  compaction, tool-result truncation, media stubbing, injection downgrade, and
  latest-turn compression
- mid-loop overflow: a turn can pass preflight and still exceed budget after
  tools add history
- tool-result bloat: AX trees, screenshots, and large tool outputs need
  type-specific retention rules
- parallel-tool cancellation mismatch: every provider-visible `tool_use` still
  needs a matching `tool_result` after abort or cancellation
- empty-response and tool-error loops: silent model endings and repeated tool
  errors need bounded loop outcomes instead of generic backend failure labels
- proactive wake misfire: heartbeat, scheduler, watcher, and opportunity wakes
  need single-flight, cooldown, and routing semantics so background agency does
  not drift into the wrong session or wrong user-facing channel

Relevant evidence:

- simplified memory separates brief state from archive recall, with
  `time_contexts`, `open_loops`, observations, chunks, and episodes
  [memory.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/memory.md:1)
  [memory.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/memory.md:52)
- the memory reducer is a delayed provider-backed background process whose
  result is applied transactionally, which makes reducer output a distinct
  failure boundary
  [memory.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/memory.md:58)
- raw token estimates are recorded separately from corrected estimates so the
  calibrator does not learn a feedback loop against its own correction
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:478)
- usage events carry `estimatedInputTokens`, allowing provider ground truth and
  the pre-send estimate to be compared in one event plane
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:608)
- tool calls are emitted together and executed with `Promise.all`, while abort
  handling preserves provider-visible tool/result pairing
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:809)
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:1052)
- oversized tool results are truncated through a dedicated
  `toolResultTruncate` pipeline before downstream persistence observes them
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:894)
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:945)
- AX trees and old image blocks have explicit history-retention logic rather
  than relying on generic compaction
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:1119)
  [loop.ts](/tmp/vellum-assistant-20260424/assistant/src/agent/loop.ts:1180)
- compaction failures feed a `circuitBreaker` pipeline keyed by conversation,
  instead of retrying compaction forever
  [conversation-agent-loop.ts](/tmp/vellum-assistant-20260424/assistant/src/daemon/conversation-agent-loop.ts:204)
  [conversation-agent-loop.ts](/tmp/vellum-assistant-20260424/assistant/src/daemon/conversation-agent-loop.ts:271)
- overflow recovery is explicitly tiered: forced compaction, tool-result
  truncation, media/file stubbing, injection downgrade, and latest-turn
  compression
  [ARCHITECTURE.md](/tmp/vellum-assistant-20260424/ARCHITECTURE.md:46)
  [memory.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/memory.md:247)
- mid-loop budget checks can yield out of the agent loop, compact, and then
  re-enter instead of waiting for provider-side context failure
  [conversation-agent-loop.ts](/tmp/vellum-assistant-20260424/assistant/src/daemon/conversation-agent-loop.ts:1654)
  [conversation-agent-loop.ts](/tmp/vellum-assistant-20260424/assistant/src/daemon/conversation-agent-loop.ts:1697)
- opportunity wakes inject a non-persistent `[opportunity:<source>]` message
  and serialize wake handling per conversation
  [agent-wake.ts](/tmp/vellum-assistant-20260424/assistant/src/runtime/agent-wake.ts:4)
  [agent-wake.ts](/tmp/vellum-assistant-20260424/assistant/src/runtime/agent-wake.ts:192)
  [agent-wake.ts](/tmp/vellum-assistant-20260424/assistant/src/runtime/agent-wake.ts:337)
- recurring scheduler, watchers, and task queues are distinct lifecycle
  surfaces rather than one generic background loop
  [scheduling.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/scheduling.md:41)
  [scheduling.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/scheduling.md:128)
  [scheduling.md](/tmp/vellum-assistant-20260424/assistant/docs/architecture/scheduling.md:191)

Vellum-specific failure names worth carrying into a mew-derived classifier:

- `calibration_feedback_drift`
- `context_pressure_cascade`
- `mid_loop_overflow`
- `tool_result_bloat`
- `parallel_tool_abort_pairing`
- `empty_response_after_tool`
- `tool_error_retry_spiral`
- `proactive_wake_misroute`
- `memory_injection_scope_leak`
- `stale_identity_or_now_context`

## What M6.12 Should Import

`M6.12` should import analysis primitives, not implementation patterns.

### 1. Hardness Is A Recurrence Problem

Calibration ergonomics should make it easy to ask:

- which subsystem keeps reopening?
- which subsystem has the highest failure-class diversity?
- which subsystem still reopens after a supposed hardening pass?

This is more useful than:

- "which file changed most?"
- "which area has the most tests?"
- "which slice had the most commits?"

### 2. State-Continuity Surfaces Need Derived Bucketing

`M6.12` will likely need a derived bucketing layer for state-continuity
failures, but the exact labels should follow a mew-native mapping pass, not be
imported directly from Hermes/OpenClaw/Vellum.

The likely families to watch are still:

- compaction or compression pressure
- transcript or replay integrity
- session state or resume continuity
- tool-call or tool-result shape normalization
- retry or failure classification
- queue/drain or detached-work recovery

But these should remain provisional descriptors until they are grounded in
mew-native blocker codes and replay bundle shapes.

### 3. Drift Calibration Needs Its Own Axis

`Drift` should be treated as a first-class calibration family, not folded into
generic runtime failure.

The external systems point to five useful drift axes:

- `task_frontier_drift`: the active objective or current edit frontier changes
  without an explicit boundary
- `context_session_drift`: compression, prompt cache, memory, model config, or
  session restore changes what the model believes the task is
- `replay_tool_drift`: retry, replay, resume, fork, or tool-result repair
  duplicates, drops, reorders, or mutates model-visible state
- `approval_review_drift`: a reviewer or approval path judges one object and
  applies another
- `ui_channel_drift`: the operator-visible state no longer matches the active
  session, selected task, or in-flight run

The mew-native calibration questions are:

- did the current `WorkTodo` or task frontier remain the same after
  compression/retry/resume?
- did any user follow-up, approval, or steer attach to the wrong task/session?
- did replay/resume preserve model-visible state, or did it duplicate/drop
  evidence?
- did the review or approval object stay byte-identical to what was applied?
- did the UI/follow-status surface show stale or hidden state?

This should remain a derived calibration layer. The canonical ledger should not
gain external drift labels while M6.11 is still open.

### 4. Queue Pressure And Lifecycle Boundaries Need First-Class Measurement

`Codex` suggests that `M6.12` should not only classify failures after the
fact. It should make pressure and lifecycle boundaries visible while the system
is running.

The likely mew-native questions are:

- when did queue or backlog pressure first become visible?
- when did a recovery path actually reduce pressure versus merely delay it?
- did an interrupt, cancel, or shutdown preserve the expected terminal record?
- did a replay/resume path stay idempotent, or did it duplicate/lose work?

This does not imply adopting Codex's thread/turn/item architecture. It does
suggest that operator surfaces should expose:

- backlog or queue concentration when relevant
- explicit lifecycle state transitions
- retryable overload versus fatal drift
- resume/replay/idempotence failures as a distinct family

### 5. Countedness And Reviewer Disposition Matter

`M6.11` has already taught the key lesson: calibration ergonomics are only
honest if counted/non-counted status and reviewer disposition live in the same
artifact plane as the replay bundle and ledger.

That should remain central in `M6.12`.

Relevant mew evidence:

- the roadmap explicitly says reviewer-rejected and measured calibration samples
  should append to one canonical ledger so `M6.12` can consume it directly
  [ROADMAP.md](/Users/mk/dev/personal-pj/mew_inspect/ROADMAP.md:639)
- the loop stabilization design treats the replay-bundle checkpoint as a gating
  surface, not a loose reporting add-on
  [docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md](/Users/mk/dev/personal-pj/mew_inspect/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:906)

### 6. "Hardening Pass" Should Be Measurable

`M6.12` should expose whether a supposed stabilization slice actually changed
the recurrence pattern:

- did the dominant failure class move?
- did one subsystem stop reopening?
- did the same subsystem stay dominant but change failure shape?
- did a fix only convert one visible failure into a different hidden one?

This suggests explicit before/after cohort comparison against the canonical
ledger rather than anecdotal interpretation from scattered sessions.

### 7. Calibration Drift And Pressure Cascades Need First-Class Buckets

`Vellum Assistant` adds a useful failure-science warning: calibration and
context pressure can become self-reinforcing if they are treated as generic
runtime noise.

The mew-native questions are:

- did a token estimate compare raw estimate against provider ground truth, or
  did it learn from an already-corrected value?
- did a pressure failure begin before the model call, after tool results, or
  only after compaction/reduction changed the visible context?
- did a recovery step reduce pressure, or merely hide pressure by dropping the
  latest task-critical evidence?
- did type-specific history such as stdout, screenshots, cached windows, or
  tool observations need its own retention rule?
- did a background wake attach to the intended task/session/channel, or did it
  create a plausible but wrong continuation?

This suggests M6.12 should include derived buckets for:

- estimate/calibration drift
- preflight context pressure
- mid-loop context pressure
- reducer/compaction pressure
- tool-result/media bloat
- background wake misrouting

These buckets should remain derived labels. They should not become canonical
ledger fields while M6.11 is still open.

## M6.11 Lock And Sequencing

While `M6.11` is still open, the current ledger shape should stay canonical and
stable.

Relevant evidence:

- `ROADMAP.md` already fixes the intended seed shape for `M6.12` consumption:
  head, scope, verifier, counted/non-counted status, blocker code, replay
  bundle path, and reviewer decision
  [ROADMAP.md](/Users/mk/dev/personal-pj/mew_inspect/ROADMAP.md:639)
- the current reviewer guidance already says the new calibration ledger is good
  enough as the M6.12 seed shape and should not widen while M6.11 is still open
  [docs/REVIEW_2026-04-23_M6_11_POST_425_NEXT_CODEX.md](/Users/mk/dev/personal-pj/mew_inspect/docs/REVIEW_2026-04-23_M6_11_POST_425_NEXT_CODEX.md:7)

This means any external-inspired classification layer should be:

- read-time only during M6.11, or
- stored in a separate derived view after M6.11 closes

It should not rewrite or widen canonical evidence while the milestone is still
using that evidence to close honestly.

## Current Mew-Native Seed Shape

Before any external prior is imported, `M6.12` should start from what mew
already records today.

The current ledger already carries:

- `head`
- `task_id`
- `session_id`
- `attempt`
- `scope_files`
- `verifier`
- `counted`
- `non_counted_reason`
- `blocker_code`
- `reviewer_decision`
- `replay_bundle_path`
- `review_doc`
- `notes`

Representative live examples exist in:

- [proof-artifacts/m6_11_calibration_ledger.jsonl](/Users/mk/dev/personal-pj/mew_inspect/proof-artifacts/m6_11_calibration_ledger.jsonl:1)

The current mew-native blocker/replay surface is therefore closer to:

- counted vs non-counted
- current-head vs legacy vs unknown cohorts
- bundle type / bundle-type concentration
- blocker code breakdown

than to any externally inspired subsystem taxonomy.

That is a feature, not a gap. `M6.12` should treat this mew-native shape as the
primary evidence plane and only layer derived classification on top of it.

## External Classifiers Must Be Derived, Not Canonical

The external lesson is not "adopt these six archetype strings." The external
lesson is "you probably need a derived classification layer at all."

So the correct import is:

- mew-native evidence stays canonical
- any external-inspired labels are derived at read time or in a separate view
- no external-inspired label becomes source-of-truth by default

### Mapping Must Start From Mew Blocker Codes

If `M6.12` later introduces archetype labels, the first step should be an
explicit mapping from current mew-native evidence, for example:

- `blocker_code`
- replay bundle type
- counted/non-counted disposition
- cohort
- prompt/contract version when relevant

The first mapping question is therefore not
"Which Hermes/OpenClaw/Vellum categories do we want?"
but
"Which mew blocker/replay families are already visible, and which derived
clusters would actually help the operator reason about them?"

Example current-head signals already visible in the ledger/reviews include:

- `no_concrete_draftable_change`
- `insufficient_cached_window_context`
- `insufficient_cached_context`
- `model_returned_refusal`

Relevant evidence:

- [proof-artifacts/m6_11_calibration_ledger.jsonl](/Users/mk/dev/personal-pj/mew_inspect/proof-artifacts/m6_11_calibration_ledger.jsonl:2)
- [docs/REVIEW_2026-04-23_M6_11_POST_425_NEXT_CODEX.md](/Users/mk/dev/personal-pj/mew_inspect/docs/REVIEW_2026-04-23_M6_11_POST_425_NEXT_CODEX.md:16)

Until that mapping exists, any external-inspired archetype vocabulary should be
treated as provisional.

## Cohort And Sample-Size Discipline

Recurrence analysis only makes sense if the comparison boundary is honest.

`M6.12` should therefore keep comparison rules explicit:

- do not mix `current_head`, `legacy`, and `unknown` into one operator claim
- do not silently mix prompt-contract or schema versions when those versions are
  known to affect bundle shape
- do not present "hardest subsystem" claims without a declared minimum-N for the
  relevant counted cohort

Current mew evidence already has cohort-aware calibration surfaces:

- [src/mew/proof_summary.py](/Users/mk/dev/personal-pj/mew_inspect/src/mew/proof_summary.py:392)
- [tests/test_proof_summary.py](/Users/mk/dev/personal-pj/mew_inspect/tests/test_proof_summary.py:558)

This suggests that `M6.12` should treat boundary rules as part of the product,
not as an implementation detail.

## What M6.12 Should Not Import

### 1. Do Not Import Their Architecture

Do not import:

- Hermes gateway/session/runtime architecture
- OpenClaw compaction engine or background-task runtime shape
- Codex app-server, thread/turn/item, or TUI transport architecture
- Vellum's personal-assistant gateway, client, channel, CES, or managed-service
  architecture
- their queue, cron, or approval abstractions as direct design goals

Those systems are useful evidence because they show where stabilization effort
accumulates, not because mew should converge on the same loop architecture.

### 2. Do Not Import Their Thresholds

Do not treat external PR counts, commit counts, release durations, or test
counts as mew targets.

Those are useful only as "this class of problem is usually deeper than a
one-pass cleanup" evidence.

### 3. Do Not Pollute The Canonical Ledger

External evidence should not be merged into mew's own calibration ledger or
counted bundle math.

The canonical M6.12 input should remain:

- mew replay bundles
- mew counted/non-counted metadata
- mew reviewer decisions
- mew current-head and related cohorts

External systems should remain explanatory priors and naming aids.

### 4. Do Not Import Their Constants Or Surface Area

Do not import:

- Codex chunking thresholds, hold windows, or queue constants as mew defaults
- Hermes/OpenClaw release cadence as a target pace
- Vellum heartbeat intervals, context thresholds, tool-retry counts, or
  assistant-product surface area as mew defaults
- Codex app-server or realtime surface area unless mew actually needs it
- OpenClaw Active Memory/Dreaming recall architecture as part of M6.12 drift
  calibration

The transferable lesson is that these systems expose pressure and lifecycle
boundaries explicitly, not that mew should copy their numeric tuning or
product breadth.

### 5. Do Not Hide Drift Behind Automatic Recovery

Do not silently auto-compress, auto-retry, auto-resume, or auto-repair without
recording the before/after state boundary.

For M6.12, a visible interruption is better than invisible drift.

## Recommended M6.12 Outputs

If this memo is adopted, `M6.12 Calibration ergonomics` should likely produce
at least:

- a subsystem heatmap derived from mew-native ledger rows
- a recurrence view grouped by failure archetype and subsystem
- a drift view grouped by task-frontier, context/session, replay/tool,
  approval/review, and UI/channel drift
- a calibration/estimate view that distinguishes raw estimate, corrected
  estimate, provider ground truth, and call-site/provider namespace
- a context-pressure view that distinguishes preflight pressure, mid-loop
  pressure, reducer pressure, and tool-result/media bloat
- a before/after comparison for bounded stabilization slices
- an operator-visible distinction between:
  - high-frequency single-class failure
  - low-frequency but high-diversity subsystem drift
  - reviewer-rejected but informative non-counted samples
- an explicit answer to:
  - "what is hardest right now?"
  - "what changed after the last hardening slice?"
  - "which next slice is most likely to reduce recurrence rather than only move it?"

## Suggested Translation To M6.12 Scope

If `M6.12` is later created, this memo suggests the following design boundary:

- `source_of_truth`: mew replay bundles + canonical calibration ledger
- `classifier_layer`: derived read-time labels grounded in mew-native evidence
- `operator_surface`: recurrence, concentration, drift, pressure, and
  post-hardening comparison

This preserves mew-native evidence while still benefiting from the failure
science that Hermes, OpenClaw, Codex, and Vellum have already paid for.

## Delivery Surface

This memo does not choose the final operator surface. That should remain a
future `M6.12` design decision.

The likely options are:

- extending `mew proof-summary`
- adding a companion calibration-oriented command
- or producing a separate reviewer/operator report surface

The important point is not the CLI name. The important point is that any
surface must preserve:

- canonical evidence
- explicit cohort boundaries
- explicit derived-vs-canonical separation

## Bottom Line

The right external import for `M6.12` is not architecture. It is:

- what to watch
- how to bucket it
- how to detect objective/context/replay drift
- where lifecycle boundaries need explicit visibility
- how to tell "hard" from merely "busy"

In one line:

`Import failure analysis, not loop structure.`
