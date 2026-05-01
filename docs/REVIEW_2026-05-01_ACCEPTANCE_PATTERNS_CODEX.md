# REVIEW 2026-05-01 - Codex Acceptance Patterns For Mew

Scope: local read-only inspection of `/Users/mk/dev/tech_check/codex`. This note is limited to acceptance, done-gate, evidence, approval, patch/review loop, and test patterns that can improve mew's implementation lane.

## Recommendation

Import Codex's **shape** of completion governance, not Codex's status semantics. The most useful slice for mew is a typed done gate between a model's finish proposal and the session's completed state:

- deterministic acceptance checks over task constraints, fresh verifier evidence, write evidence, and pending approvals
- structured evidence references in the final answer contract
- hook-style block/continue feedback when the finish candidate is not yet acceptable
- typed approval/rejection outcomes, not booleans
- exact tests that prove failed patches, stale verification, and missing evidence cannot produce a successful finish

Codex itself does not treat `TurnComplete` as semantic acceptance. Mew should not copy that. Mew should make the final transition stronger than Codex's transport completion.

## Files And Lines Inspected

### Completion Boundary And Stop Gates

- `codex-rs/core/src/codex.rs:6320-6415`: regular turn setup stores `last_agent_message`, creates the turn diff tracker, and enters the sampling loop.
- `codex-rs/core/src/codex.rs:6423-6460`: after each sampling request Codex decides whether the model needs follow-up or there is pending user input.
- `codex-rs/core/src/codex.rs:6479-6560`: if there is no follow-up, Codex runs stop hooks with the last assistant message before allowing the turn to end; hook output can inject a continuation prompt and keep the turn alive.
- `codex-rs/core/src/codex.rs:7895-7916`: output items update tool futures, `last_agent_message`, and the follow-up flag.
- `codex-rs/core/src/codex.rs:7997-8016`: a Responses `Completed` event flushes stream segments and breaks the sampling request; it is protocol completion, not proof that the task is accepted.
- `codex-rs/core/src/codex.rs:8097-8122`: Codex drains in-flight tool futures and emits turn diffs only after the response stream has closed.
- `codex-rs/core/src/tasks/mod.rs:295-324`: task execution calls `on_task_finished` only when not cancelled, then notifies completion.
- `codex-rs/core/src/tasks/mod.rs:400-544`: `on_task_finished` drains pending input, computes metrics, and emits `EventMsg::TurnComplete` with `last_agent_message`.
- `codex-rs/protocol/src/protocol.rs:1396-1433` and `2048-2059`: protocol-level `TurnCompleteEvent` carries turn id, last agent message, completion time, and duration.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:3861-3882` and `4176-4184`: v2 exposes `Turn` and `TurnStatus` as `Completed`, `Interrupted`, `Failed`, or `InProgress`.
- `codex-rs/app-server/src/bespoke_event_handling.rs:217-232`, `1975-2008`, and `2194-2222`: app-server maps core completion into v2 completion; if a last error exists it marks the turn failed, otherwise completed.
- `codex-rs/app-server-protocol/src/protocol/thread_history.rs:895-943`: thread history marks an in-progress turn completed when it receives turn completion.
- `codex-rs/hooks/src/events/stop.rs:23-42`, `66-122`, `133-210`, and `268-299`: stop hooks receive the last assistant message and can allow stop, block with a reason, or return continuation fragments.
- `codex-rs/protocol/src/items.rs:46-57` and `231-271`: hook prompt fragments are represented as typed items and fed back as a user message.
- `codex-rs/core/src/contextual_user_message_tests.rs:68-99`: tests verify hook prompt round-trip and escaping.

### Acceptance Criteria And Structured Output

- `codex-rs/protocol/src/protocol.rs:403-463`: `UserInput` and `UserTurn` can carry an optional `final_output_json_schema`.
- `codex-rs/core/src/client_common.rs:25-45`: model prompts carry an optional `output_schema`.
- `codex-rs/core/src/codex.rs:6940-6961`: each turn passes `final_output_json_schema` into the prompt as `output_schema`.
- `codex-rs/exec/tests/suite/output_schema.rs:8-62`: exec tests assert the request sends a strict JSON schema under `/text/format`.
- `codex-rs/app-server/tests/suite/v2/output_schema.rs:21-100` and `103-209`: v2 tests show an output schema applies to the requested turn and does not leak into the next turn.
- `codex-rs/core/review_prompt.md:1-87`: review mode defines acceptance for a patch as bug-oriented review findings plus an overall correctness verdict, with a strict JSON output format.
- `codex-rs/core/src/review_prompts.rs:15-18`, `28-29`, and `56-95`: review targets are converted into concrete prompts for uncommitted changes, base branches, commits, and custom prompts.
- `codex-rs/core/src/review_prompts.rs:132-185`: tests cover the generated review prompts.
- `codex-rs/core/src/guardian/prompt.rs:505-564`: guardian review has a strict JSON schema and a matching prompt fragment for risk, authorization, outcome, and rationale.

### Evidence Ledger And Final Answer Handling

- `codex-rs/core/src/codex.rs:2955-2960`: every event is persisted to rollout before delivery.
- `codex-rs/core/src/codex.rs:2972-2998`: item started/completed events carry `turn_id` and item payloads.
- `codex-rs/core/src/codex.rs:7340-7378` and `7402-7417`: plan and assistant message items are emitted as typed turn items.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:4510-4588`: v2 `ThreadItem` variants include user messages, hook prompts, agent messages, plans, reasoning, command executions, file changes, and MCP tool calls.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:5105-5128` and `5153-5180`: command executions and file changes have explicit status, exit code, duration, diff/change shape, and patch apply status.
- `codex-rs/app-server/src/bespoke_event_handling.rs:1510-1530`: core turn items become app-server item start/completion notifications.
- `codex-rs/exec/src/event_processor_with_jsonl_output.rs:359-390` and `467-548`: exec reconciles unfinished items at completion, picks a final message from completed turn items, and clears stale final messages on failed/interrupted turns.
- `codex-rs/exec/src/event_processor_with_human_output.rs:299-331`: human output has the same final-message recovery and stale-message clearing behavior.
- `codex-rs/exec/src/event_processor_with_human_output_tests.rs:92-232`: tests prove final message recovery from turn items and latest-agent-message selection.

### Patch, Review, Apply, And Retry Loops

- `codex-rs/core/src/tools/orchestrator.rs:1-8`: the orchestrator owns approval, sandbox selection, and retry semantics.
- `codex-rs/core/src/tools/orchestrator.rs:122-180`: approval handling distinguishes skipped, forbidden, needs approval, rejected, timed out, and aborted paths.
- `codex-rs/core/src/tools/orchestrator.rs:182-205`, `260-345`, and `360-379`: sandbox denial can produce an escalated retry request with a structured reason and separate approval.
- `codex-rs/core/src/tools/runtimes/apply_patch.rs:39-47`: patch requests carry action, file paths, changes, approval requirement, and permissions.
- `codex-rs/core/src/tools/runtimes/apply_patch.rs:112-168`: patch approval is cached per key, can route through guardian, and can be bypassed by preapproved permissions.
- `codex-rs/core/src/tools/runtimes/apply_patch.rs:180-236`: patch runtime applies verified patches, emits output deltas and exit code, and maps sandbox denial to a retryable tool error.
- `codex-rs/apply-patch/src/parser.rs:126-178`: parser has strict and lenient paths, including model-produced heredoc-wrapped patches.
- `codex-rs/apply-patch/tests/fixtures/scenarios/README.md:1-7`: scenario fixtures are `input/`, `patch.txt`, and `expected/`.
- `codex-rs/apply-patch/tests/suite/scenarios.rs:10-60`: tests apply every fixture patch and compare the resulting filesystem to `expected/`.
- `codex-rs/core/tests/suite/apply_patch_cli.rs:332-390`, `1000-1020`, and `1023-1100`: tests cover no turn diff for pure moves, event/diff emission after successful patch, and no turn diff plus unchanged file after failed patch.
- `codex-rs/core/src/tasks/review.rs:50-88`: review tasks run a child review conversation and do not let the review task's own turn completion carry the review text as normal assistant output.
- `codex-rs/core/src/tasks/review.rs:95-138`: review child config is locked down: no web search, no collab, approval policy never, and review instructions as base prompt.
- `codex-rs/core/src/tasks/review.rs:140-188`: review event processing suppresses streaming assistant output and parses the review result only on child turn completion.
- `codex-rs/core/src/tasks/review.rs:190-210`: review output parser accepts strict JSON, then first JSON object substring, then structured fallback.
- `codex-rs/core/src/tasks/review.rs:212-283`: exiting review mode records the reviewer prompt and assistant review result back into the parent rollout.
- `codex-rs/core/src/review_format.rs:16-81`: review findings are rendered into a stable text block.
- `codex-rs/core/tests/suite/review.rs:36-303`: tests cover lifecycle, rollout recording, plain-text fallback, and suppression of child assistant events.

### Structured Approvals, Rejections, And Guardian Evidence

- `codex-rs/protocol/src/protocol.rs:3515-3570`: `ReviewDecision` distinguishes approved, approved for session, exec policy amendment, network policy amendment, denied, timed out, and abort.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:1054-1097`: v2 command approval decisions distinguish accept, accept for session, accept with policy amendment, network amendment, decline, and cancel.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:1249-1261`: file change approvals distinguish accept, accept for session, decline, and cancel.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:5753-5843`: approval requests carry thread id, turn id, item id, approval id, reason, command/file context, proposed amendments, available decisions, and typed responses.
- `codex-rs/core/src/codex.rs:3170-3249` and `3553-3570`: command approval requests are keyed and pending before emission; missing pending approval resolves to abort.
- `codex-rs/app-server/src/bespoke_event_handling.rs:2310-2405`: malformed or failed approval responses default to denied.
- `codex-rs/core/src/tools/sandboxing.rs:64-115`: cached approval is scoped by keys and records typed decision telemetry.
- `codex-rs/app-server-protocol/src/protocol/common.rs:1298-1315`: wire tests assert approval response serialization.
- `codex-rs/app-server/tests/suite/v2/request_permissions.rs:23-130`: permission approval round-trip asserts requested write paths, granted scope, and server request resolution before turn completion.
- `codex-rs/core/src/guardian/review.rs:92-120`, `164-213`, `235-295`, and `338-351`: guardian review fails closed on errors/timeouts, emits assessment events, and runs in a locked-down read-only session.
- `codex-rs/core/src/guardian/prompt.rs:74-95`: guardian prompt treats transcript, tool results, retry reason, and planned action JSON as untrusted evidence with explicit boundaries.
- `codex-rs/protocol/src/approvals.rs:85-197`: guardian assessment events carry risk, authorization, status, decision source, rationale, target item, turn id, and canonical action.
- `codex-rs/app-server-protocol/src/protocol/v2.rs:4688-4771` and `5496-5521`: v2 exposes guardian review status and notifications.
- `codex-rs/app-server/src/bespoke_event_handling.rs:299-333`: app-server maps guardian denied/aborted to declined command execution and timed out to failed.
- `codex-rs/core/src/guardian/tests.rs:690-708` and `1268-1284`: tests cover cancelled guardian approval returning abort and review errors returning denied.

### Mew Import Targets Noted

- `src/mew/acceptance.py:2351-2408`: current `acceptance_finish_blocker()` already blocks some `task_done=true` finishes without acceptance checks.
- `src/mew/validation.py:265-333` and `349-380`: state validation already checks write-run to verification-run links and runtime-effect links.
- `src/mew/state.py:104-105`, `167-168`, `322-367`, and `1163-1178`: state already has `verification_runs`, `write_runs`, next ids, and verification run append logic.
- `src/mew/work_loop.py:6191-6199`: implementation-contract and acceptance-check instructions already exist in prompt text.
- `src/mew/work_session.py:6600-6687` and `9200-9271`: pending write approvals already carry pairing state, approval controls, and defer-verification hints.

## Transferable Concepts

1. **Separate protocol completion from accepted completion.**
   Codex cleanly separates response-stream completion, tool draining, stop hooks, and turn completion. Mew should go one step further: model finish proposal -> deterministic done gate -> completed state. A final `task_done=true` action should be only a candidate, not the state transition.

2. **Make stop hooks into a finish blocker with continuation.**
   Codex stop hooks can block the turn and feed continuation fragments back as user input. Mew can use the same pattern for acceptance: when a finish candidate lacks proof, append a structured "finish blocked" continuation prompt into the same implementation lane instead of marking the task failed or waiting for a human.

3. **Persist evidence as typed items before final answer handling.**
   Codex persists event items before delivery and exposes command/file/tool items with status and ids. Mew already has `verification_runs` and `write_runs`; the missing bridge is requiring final answers to cite those ids and requiring the ids to be terminal, fresh, and relevant.

4. **Use per-turn final schemas for finish candidates.**
   Codex's `final_output_json_schema` proves that output contracts can be scoped to one turn and tested for non-leakage. Mew should require finish candidates to produce a schema such as:
   - `task_done`
   - `summary`
   - `acceptance_checks[]`
   - `evidence_refs[]`
   - `residual_risks[]`
   - `next_action_if_blocked`

5. **Represent approval as a typed decision family.**
   Codex distinguishes accept once, accept for session, policy amendment, decline, cancel, timeout, and abort. Mew should not treat approval as `approved=true/false`; decline should mean "continue without this effect", while cancel should interrupt the turn.

6. **Treat failed patch application as first-class evidence.**
   Codex tests prove a failed patch produces diagnostics and does not emit a success diff. Mew should record failed writes as evidence of attempted work, but must not let them satisfy acceptance or verifier freshness.

7. **Use locked-down review as evidence, not as normal assistant prose.**
   Codex review mode suppresses child assistant deltas, parses structured output, and records the result back into the parent rollout. Mew can use a read-only reviewer lane for high-risk finish candidates, but its output should be stored as `review_run` evidence and consumed by the done gate.

8. **Fail closed for parse errors and timeouts at safety/acceptance boundaries.**
   Codex guardian review defaults malformed responses and errors to denial, while preserving the specific reason. Mew should block completion on verifier/reviewer/done-gate parse failure or timeout, but record `timeout` separately from `denied` so repair prompts stay accurate.

9. **Test gates with event-order and freshness properties.**
   Codex tests exercise turn-item reconciliation, stale final-message clearing, approval round trips, and patch failure behavior. Mew's acceptance tests should assert ordering: no completion while tools are in flight, no completion with verification older than the last write, and no completion when evidence ids are missing.

## What Not To Copy

- Do not copy Codex's `TurnStatus::Completed` as a semantic done signal. In Codex it mostly means the turn ended without a recorded error; it is not acceptance proof.
- Do not copy final-message recovery as acceptance evidence. Codex can fall back from agent message to plan text for CLI output. Mew should never treat "latest assistant message" or a plan as proof.
- Do not rely on prompt-only JSON instructions for gating. Codex review has prompt-level structure plus parser fallback; mew's done gate should enforce a schema and make fallback output non-gating.
- Do not copy broad rollout reconstruction or event stream machinery wholesale. Mew already has state, calls, `verification_runs`, `write_runs`, pending approvals, and runtime effects. Add a compact evidence index rather than replacing the state model.
- Do not copy per-path approval caching as sufficient write authorization. For mew, cached write approval should include affected path, action kind, patch hash or content fingerprint, and session scope.
- Do not copy platform-variable approval outcomes. Codex has tests that tolerate declined command turns completing or interrupting in some shell-fork cases. Mew should define one contract for decline vs cancel.
- Do not copy lenient patch parsing into the done gate. Leniency belongs at patch ingestion; acceptance should consume normalized write evidence and verifier evidence only.
- Do not copy guardian/approval terminology directly into user-facing mew concepts. The transferable idea is a typed, fail-closed assessor with canonical action evidence.

## Suggested Mew Design And Import Plan

### 1. Add A `DoneGate` Around Finish

Implement this as a small module, either `src/mew/done_gate.py` or a narrow extension around `acceptance_finish_blocker()` in `src/mew/acceptance.py`.

Core data shapes:

- `FinishCandidate`: parsed finish action plus final answer text and `acceptance_checks`.
- `EvidenceRef`: `{kind, id, status, created_at_or_sequence, summary}` where kind starts with `verification_run`, `write_run`, `tool_call`, `approval`, and later `review_run`.
- `AcceptanceCheck`: `{constraint, status, evidence_refs, freshness}`.
- `DoneGateDecision`: `{decision, reason, missing_checks, invalid_evidence_refs, continuation_prompt}` where decision is one of `allow_complete`, `block_continue`, `stop_blocked`, or `fail_closed`.
- `CompletionRecord`: persisted only on `allow_complete`, with final answer, accepted timestamp, acceptance checks, evidence refs, latest write id, latest verification id, and reviewer ids if any.

### 2. Gate Completion Deterministically Before Any Reviewer

The first pass should be deterministic and should block if any of these are true:

- `task_done=true` has no `acceptance_checks`.
- an acceptance check has no evidence refs
- a referenced evidence id does not exist
- a referenced evidence item is non-terminal, failed, stale, dry-run-only, or older than the latest relevant write
- there is a pending approval or unresolved rejected/failed write effect for the same scope
- the task required an exact command, artifact, stdout marker, fixture, or do-not-edit rule and the final checks do not cite direct evidence for it
- the final answer cites user-reported or prompt-only claims as verification evidence

This should turn today's prompt instruction in `work_loop.py:6191-6199` into runtime behavior.

### 3. Feed Blocks Back Into The Same Lane

When the gate returns `block_continue`, append a hook-style continuation prompt:

- name the blocked finish candidate
- list missing checks and stale evidence
- list the exact next verifier/read/diff action needed
- preserve current pending approvals and recovery state

Do not mark the session failed. Do not ask for human approval unless the only remaining action is genuinely reviewer/user authorization.

### 4. Build A Compact Evidence Index From Existing State

Reuse current state instead of adding a large event bus:

- `verification_runs`: command, cwd, exit code, output excerpt, status, sequence/time, linked write ids
- `write_runs`: paths, dry-run/applied status, diff hash, linked verification id, approval status
- tool calls: read/search/run/apply status and output excerpts
- approvals: request scope, available decisions, selected decision, affected paths, patch hash
- runtime effects: existing verification/write links from `validation.py`

The done gate can build this index at finish time. A later iteration can persist it as `completion_record.evidence_snapshot`.

### 5. Normalize Approval Decisions

Add a typed approval decision enum in mew's work-session layer:

- `accept_once`
- `accept_for_session`
- `decline_continue`
- `cancel_turn`
- `timeout`
- `failed_closed`

Map existing statuses into this enum at the boundary. Use `decline_continue` to leave the lane active with rejection evidence. Use `cancel_turn` to stop the current turn and block completion.

### 6. Add Optional Read-Only Review Runs For High-Risk Finishes

Only after deterministic checks pass or nearly pass, run an optional reviewer for high-risk implementation tasks:

- read-only tools only
- no writes, no approval prompts, no web unless task explicitly needs it
- input is the finish candidate, evidence index, diff summary, and acceptance constraints
- output must be structured: blocking findings, nonblocking findings, verdict, evidence refs
- plain text fallback may be recorded, but cannot satisfy "review passed"

Store this as `review_run` evidence. The done gate blocks on blocking findings unless they are addressed or explicitly waived with evidence.

### 7. Make Patch Application Produce Scenario-Testable Evidence

For mew's write path:

- create a pre-apply file-change record with planned paths and patch hash
- create a post-apply record with applied/failed status, diff hash, diagnostics, and affected paths
- never let a failed apply create successful write evidence
- never let a dry-run write satisfy completion
- tie verification freshness to the latest successful write for the affected scope

This mirrors Codex's useful patch evidence behavior without importing its patch grammar.

## Tests Mew Should Add

1. `test_done_gate_blocks_task_done_without_verification_evidence`
   A finish action with `task_done=true` and a plausible summary but no verification evidence returns `block_continue`.

2. `test_done_gate_accepts_only_fresh_verification_after_last_write`
   Verification before the latest write does not count; verification after the latest applied write with exit code 0 does.

3. `test_final_answer_must_cite_existing_evidence_ids`
   Missing, misspelled, or wrong-kind evidence refs block completion.

4. `test_acceptance_check_requires_direct_evidence_for_each_constraint`
   A compile/test command cannot satisfy a do-not-edit, exact stdout, artifact existence, or source-read constraint unless direct evidence is cited.

5. `test_failed_patch_does_not_emit_success_write_evidence`
   Failed apply leaves write status failed, preserves diagnostics, and cannot satisfy acceptance.

6. `test_dry_run_write_cannot_satisfy_completion`
   A dry-run diff may support review, but completion requires applied write evidence or a no-change task path.

7. `test_patch_scenario_runner_compares_expected_filesystem`
   Add fixture-style tests with `input/`, `patch`, and `expected/` to prove apply behavior exactly.

8. `test_review_sub_lane_records_structured_findings_and_blocks_p1`
   A structured reviewer output with a blocking finding prevents completion until addressed.

9. `test_review_plain_text_is_recorded_but_non_gating`
   Plain text reviewer fallback is stored as evidence but cannot satisfy a required review-pass gate.

10. `test_approval_decline_continue_vs_cancel_turn`
    Decline records rejected evidence and keeps work active; cancel interrupts and prevents completion.

11. `test_accept_for_session_scope_requires_matching_fingerprint`
    Cached approval for one path/patch hash or command family does not approve a different write or command.

12. `test_done_gate_timeout_fails_closed_with_timeout_reason`
    Verifier, reviewer, or done-gate timeout blocks completion and records `timeout`, not generic denial.

13. `test_stop_gate_block_feedback_reenters_same_lane`
    A blocked finish appends a continuation prompt and leaves the task in progress.

14. `test_transport_completion_does_not_mark_task_complete_when_gate_blocks`
    Model response completion plus final text does not set completed state if the done gate blocks.

15. `test_finish_output_schema_is_per_turn`
    A finish schema applies to the finish proposal only and does not leak into later repair/work turns.

16. `test_tool_evidence_ordering_requires_terminal_items`
    Completion is blocked while referenced writes, commands, approvals, or review runs are still pending.

## Implementation Order

1. Add the deterministic `DoneGate` and evidence-ref validation on top of existing `verification_runs`, `write_runs`, tool calls, and pending approvals.
2. Persist `completion_record` only after `allow_complete`.
3. Convert finish blockers into hook-style continuation prompts when blocked.
4. Add patch/write evidence status tests and stale-verification tests.
5. Normalize approval decisions and add decline-vs-cancel tests.
6. Add optional read-only review runs only after the deterministic gate is reliable.

The smallest useful first PR is steps 1, 2, and the first four tests. That would close the most important false-green path: the implementation lane saying it is done without fresh, linked, terminal evidence.
