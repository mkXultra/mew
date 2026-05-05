# Design 2026-05-05 - M6.23.2 Implement V2 Native Tool Loop

Status: design proposal for review

Scope: define `implement_v2` as a default-off provider-native tool-loop lane
under M6.23.2 Lane Isolation Substrate. This document is a design only. It does
not authorize source edits by itself.

## Inputs Reviewed

Controller and roadmap context:

- `docs/DESIGN_2026-05-05_M6_23_2_LANE_ISOLATION_SUBSTRATE.md`
- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`
- `ROADMAP.md`
- `ROADMAP_STATUS.md`

Reference adoption and survey context:

- `docs/ADOPT_FROM_REFERENCES.md`
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
- `docs/REVIEW_2026-05-01_M6_24_CLAUDE_CODE_LONG_DEP_AUDIT.md`
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`
- `docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md`
- `docs/DESIGN_2026-05-03_M6_24_GENERIC_MANAGED_EXEC.md`

Reference source sampled for transferable patterns:

- `references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs`
- `references/fresh-cli/codex/codex-rs/protocol/src/dynamic_tools.rs`
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/*`
- `references/fresh-cli/codex/codex-rs/core/src/apply_patch.rs`
- `references/fresh-cli/claude-code/src/query.ts`
- `references/fresh-cli/claude-code/src/Tool.ts`
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts`
- `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts`
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts`
- `references/fresh-cli/claude-code/src/tools/BashTool/*`
- `references/fresh-cli/claude-code/src/tools/TaskOutputTool/*`
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/*`
- `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts`
- `references/fresh-cli/claude-code/src/constants/prompts.ts`

Current mew source sampled only to understand integration boundaries:

- `src/mew/work_lanes.py`
- `src/mew/work_replay.py`
- `src/mew/prompt_sections.py`
- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `src/mew/long_build_substrate.py`
- `src/mew/acceptance.py`

## Decision

Build `implement_v2` as a separate lane runtime that speaks provider-native
tool calls and returns paired provider-native tool results. Do not retrofit this
loop into the existing implement lane.

`implement_v1` remains the default implementation lane and keeps its existing
JSON THINK/ACT behavior. `implement_v2` is default-off, lane-scoped, and
runtime-unavailable until the phase gates below pass. M6.24 proof work should
resume only with an explicit lane selection recorded in the artifact metadata.

The core shape is:

```text
LaneInput
  -> prompt section assembly
  -> provider request with native tool schemas
  -> provider tool_call/tool_use events
  -> mew tool validation, approval, execution
  -> paired provider tool_result messages
  -> same provider conversation continues
  -> finish candidate
  -> deterministic acceptance / proof artifacts / metrics
  -> LaneResult
```

The provider adapters translate message and tool-call wire formats. The lane
runtime owns the loop, tool policy, transcript, artifacts, and metrics. Shared
mew services own filesystem operations, managed exec, approvals, acceptance,
prompt sections, and replay storage.

## Goals

- Add a coding lane that feels like a native shell for a frontier coding model:
  read, search, run, edit, verify, and recover through one model/tool/result
  loop.
- Keep v1 behavior stable while v2 is built beside it.
- Make v1 and v2 artifacts comparable without forcing v1 to adopt v2 internals.
- Preserve deterministic proof boundaries: final acceptance is based on mew
  evidence, not on a model final message.
- Keep prompt-section and cache metadata provider-neutral so cache transport can
  be added later without rewriting lane semantics.
- Record enough metrics to decide whether v2 improves M6.24-style software and
  coding work before making any default-route decision.

## Non-Goals

- No change to `implement_v1` behavior.
- No default switch to `implement_v2`.
- No Terminal-Bench task-specific behavior, classifiers, prompts, fixtures, or
  benchmark recipes.
- No provider-specific prompt-cache transport implementation.
- No full clone of Codex unified exec, Claude Code Bash permissions, subagents,
  MCP search, task/todo framework, or UI.
- No new autonomous supervisor or second write-capable authoritative lane.
- No write/edit/apply-patch support before read-only and managed-exec phase
  gates pass.
- No acceptance based on nonterminal command progress, output tails that look
  close, or model self-report.
- No app/plugin connector tool surface in the first v2 runtime. External app
  tools can be considered after the core coding lane proves safe.

## Coexistence With `implement_v1`

`implement_v1` is the compatibility boundary. It should be wrapped by the lane
dispatcher but not rewritten into the v2 loop.

Required invariants:

- Missing or empty lane values continue to resolve to the existing default lane.
- Existing v1 work sessions, work todo normalization, THINK/ACT schema, cached
  window behavior, tiny draft path, managed command behavior, acceptance gates,
  and replay bundle shape remain behaviorally unchanged.
- The v1 adapter may add lane metadata around artifacts, but it must not change
  v1 prompts, tool policy, command routing, finish semantics, or recovery
  decisions.
- v2 cannot reuse v1 artifact paths without a lane namespace.
- v2 cannot mutate v1 persisted state except through shared services that are
  already designed to be lane-neutral, such as command evidence, acceptance
  records, and work-session journal events with lane ids.
- Any v2 failure must fall back by returning a v2 `LaneResult` with status
  `blocked`, `failed`, or `deferred`; it must not silently reroute the same
  attempt through v1 and count as v2 success.
- `fallback_lane=implement_v1` is operator-visible reentry guidance after a
  finalized v2 `LaneResult`. It is not automatic same-attempt execution.
- Any v1 retry after a v2 result must be a separate `implement_v1` lane attempt
  with its own lane attempt id, artifact namespace, transcript, metrics, and
  proof attribution.
- V2 success metrics must never include fallback execution. If a v2 attempt
  returns `blocked` and the operator starts v1, the v2 metrics remain blocked
  and the v1 metrics belong only to the new v1 attempt.

The registry state should remain conceptually:

```text
tiny / implement_v1
  authoritative=true
  write_capable=true
  runtime_available=true
  default=true

implement_v2
  authoritative=false until write gates pass
  write_capable=false until write gates pass
  runtime_available=false until phase gates pass
  default=false
  fallback_lane=implement_v1
```

After v2 write gates pass, it may become `authoritative=true` only for an
explicitly selected run. It still must not become default during M6.23.2.

### Fallback Semantics

Fallback has three separate meanings and they must not be conflated:

| Field or action | Meaning | Metrics owner |
|---|---|---|
| `fallback_lane` on a runtime view | Static operator guidance for what lane can be tried next if this lane is unavailable or blocked. | None by itself. |
| v2 `LaneResult.status=blocked|failed|deferred|unavailable` with `next_reentry_hint.fallback_lane=implement_v1` | Finalized v2 attempt says the operator may retry in v1. | The v2 attempt remains blocked/failed/deferred/unavailable. |
| Later v1 retry | A new explicit `implement_v1` attempt started by operator or caller. | The v1 attempt only. |

The runtime must not do this:

```text
start implement_v2 -> fail internally -> run implement_v1 in same attempt
-> return completed lane=implement_v2
```

That would contaminate v2 metrics and M6.24 proof attribution. A fallback retry
must look like this instead:

```text
attempt A: lane=implement_v2 status=blocked fallback_lane=implement_v1
attempt B: lane=implement_v1 status=completed|blocked|failed
```

Attempt A and attempt B have separate artifact namespaces, transcript replay,
tool metrics, command evidence ownership, approval records, and proof summary
entries.

## V1/Shared-Substrate Reuse Inventory

V2 should reuse proven shared substrate where the behavior is lane-neutral. It
should not copy v1's JSON loop or accumulated repair heuristics.

### Reuse From V1 Or Shared Substrate

| Surface | Reuse decision | Boundary |
|---|---|---|
| Lane registry and lane attempt telemetry | Reuse and extend. | Keep v1 default and record v2 as explicit lane attempts. |
| Read/search helpers | Reuse shared filesystem/search services. | Expose through provider-native schemas and v2 envelopes, not v1 action JSON. |
| Write/edit/patch helpers | Reuse shared mutation primitives and validators. | Put v2 dry-run, approval, and provider-result pairing around them. |
| Managed exec | Reuse generic managed execution for all v2 run/test tools. | Preserve terminal/nonterminal proof semantics. |
| Approval and durable elicitation surfaces | Reuse shared approval policy and artifacts. | Freeze per-turn permission context and record v2 tool ids. |
| Acceptance and verifier gates | Reuse deterministic acceptance. | V2 `completed` means acceptance passed; finish text alone is not enough. |
| Prompt section registry | Reuse `PromptSection` metadata and metrics. | Add v2 section ids; do not mutate v1 prompt sections. |
| Work replay/proof artifacts | Reuse lane-scoped replay conventions. | Ensure v2 has its own namespace and pairing validation. |
| Metrics/proof summary | Reuse lane attempt and proof summary aggregation. | Add v2-specific tool-loop metrics without counting fallback execution. |
| Existing tests and fixtures | Reuse shared safety/acceptance/managed-exec fixtures. | Add provider-native fake-provider tests for v2 semantics. |
| Failure logs and command evidence | Reuse as evidence sources. | Do not parse them with v1 reducer heuristics to drive v2 loop state. |

### Do Not Copy From V1

| V1 surface | Why v2 should not copy it |
|---|---|
| JSON THINK/ACT loop | V2's purpose is provider-native tool calls and paired tool results. |
| V1 action schema and action projection | It encodes v1 loop assumptions and broad action normalization. |
| V1 action reducer/recovery reducer | It mixes historical repair heuristics with v1 action semantics. |
| Tiny write-ready cached-window fast path | Useful v1 behavior, but it would import v1-specific cached-window assumptions into v2. |
| Terminal-Bench/M6.24 task-family repair logic | V2 must stay generic and avoid benchmark-task-specific behavior. |
| Long prompt/profile accretion | V2 should keep behavior in tool/runtime contracts and prompt sections with hash metrics. |
| V1 context JSON layout as authority | V2 should define its own lane input and context suffix. |
| Hidden fallback/rescue execution | V2 success must not include v1 fallback or supervisor rescue edits. |
| Text parsing of finish claims | V2 finish must be a provider-native tool call validated against evidence refs. |
| Acceptance shortcuts from tool output prose | V2 must cite deterministic evidence refs and pass shared gates. |

## Current Scaffold Reconciliation

The current `src/mew/implement_lane` scaffold should be treated as the starting
shape for the implementation phases, not as a competing design. Ignore
`__pycache__` files; they are generated artifacts and should not be part of the
design.

| Current file | Round-2 design disposition |
|---|---|
| `src/mew/implement_lane/__init__.py` | Keep as package export shim. Expand exports only as stable v2 types/runtime pieces land. |
| `src/mew/implement_lane/registry.py` | Expand in place. Keep v1 default and v2 default-off; update selection semantics so v2 unavailability returns a v2 result with operator-visible fallback guidance instead of same-attempt v1 execution. |
| `src/mew/implement_lane/types.py` | Expand in place. Add canonical mode enum, `LaneResult` statuses, tool call/result envelopes, finish tool payload/result types, and metrics types. |
| `src/mew/implement_lane/transcript.py` | Expand in place. Keep `lane_artifact_namespace()` as a compatibility helper, but make future manifest/replay paths lane-scoped and pairing-validating. |
| `src/mew/implement_lane/tool_policy.py` | Expand in place. Split current provider-neutral specs into full tool definitions with schemas, risk classes, dry-run support, approval requirements, concurrency, and finish tool schema. |
| `src/mew/implement_lane/v1_adapter.py` | Keep as a compatibility shim. It should describe/wrap v1 without moving or changing the legacy runtime. |
| `src/mew/implement_lane/v2_runtime.py` | Replace the unavailable stub incrementally with the real v2 runtime across phases. Preserve `describe_implement_v2_runtime()` for operator/status introspection. |

The existing `tests/test_implement_lane.py` shape should expand with each phase:
registry/default-off tests remain, then fake-provider pairing tests, read-only
analysis-result tests, managed-exec tests, finish validation tests, and replay
manifest tests are added.

## Lane Runtime Contract

Every lane should satisfy the M6.23.2 lane contract without sharing internal
loop assumptions.

### LaneInput

Minimum fields:

```json
{
  "schema_version": 1,
  "work_session_id": "session id",
  "lane": "implement_v2",
  "lane_attempt_id": "stable lane-scoped attempt id",
  "task_contract": {
    "task_id": "task id",
    "task_kind": "coding",
    "objective": "user-visible goal",
    "acceptance_constraints": [],
    "allowed_roots": {},
    "prohibited_effects": []
  },
  "workspace": {
    "root": "/workspace",
    "cwd": "/workspace"
  },
  "model_config": {
    "provider": "provider id",
    "model": "model slug",
    "effort": "optional effort"
  },
  "lane_config": {
    "mode": "read_only|plan|exec|write",
    "approval_policy": "never|on_request|always",
    "dry_run_default": true,
    "max_turns": 0,
    "max_tool_calls": 0,
    "max_wall_seconds": 0
  },
  "persisted_lane_state": {}
}
```

`task_contract` is authority. Model memory, prior transcripts, prompt text, or
provider state may add hypotheses but cannot weaken task constraints, allowed
roots, proof requirements, or safety gates.

### Canonical Mode Enum

Use one canonical mode enum across `lane_config.mode` and `PermissionContext`.
Do not create separate `exec_enabled` or `write_enabled` booleans as a second
permission system.

| Canonical mode | Read tools | Run tools | Write/edit/apply_patch tools | Finish behavior |
|---|---|---|---|---|
| `read_only` | Allowed by readable roots. | Not available except `read_command_output` for existing refs. | Not available. | May return `analysis_ready`, never `completed`. |
| `plan` | Allowed by readable roots. | Not available. | Dry-run planning only if a later phase explicitly adds non-mutating diff preview. | May return `analysis_ready` or `blocked`. |
| `exec` | Allowed. | Available through managed exec and approval policy. | Not available. | May complete only if task requires no writes and acceptance evidence passes. |
| `write` | Allowed. | Available through managed exec and approval policy. | Available behind dry-run, approval, and allowed-root gates. | May complete only after acceptance evidence passes. |
| `bypass` | Reserved for future explicit policy. | Reserved. | Reserved. | Out of M6.23.2 scope. |

If older callers still pass `exec_enabled`, map it to `exec`; if they pass
`write_enabled`, map it to `write`; if they pass empty or unknown values, fail
closed to `read_only` for v2 and record a validation warning. V1 compatibility
shims may continue to interpret old flags for v1 only.

### LaneResult

Minimum fields:

```json
{
  "schema_version": 1,
  "lane": "implement_v2",
  "lane_attempt_id": "stable lane-scoped attempt id",
  "status": "completed|analysis_ready|blocked|failed|interrupted|deferred|unavailable",
  "user_visible_summary": "",
  "proof_artifacts": [],
  "next_reentry_hint": {},
  "updated_lane_state": {},
  "metrics": {}
}
```

`completed` means the lane reached a finish candidate and deterministic mew
acceptance/verifier gates accepted it. A model final answer without accepted
evidence is `blocked` or `failed`, not `completed`.

`analysis_ready` is the Phase 3 read-only success convention. It means v2
completed a replay-valid read/search provider-native loop and produced a
structured diagnosis or plan without claiming task completion or mutating the
workspace. It is useful product evidence for the read-only spike, but it is not
counted as implementation success and cannot satisfy M6.24 proof closure.

### Runtime Lifecycle

The runtime lifecycle is explicit:

1. `created`: lane attempt id, lane input, frozen permission context, and
   artifact namespace are allocated.
2. `prompt_ready`: prompt sections and provider-neutral tool specs are rendered
   and hashed.
3. `provider_turn_started`: provider adapter submits the request with native
   tool schemas.
4. `tool_call_received`: provider-native calls are captured with stable ids.
5. `tool_call_validated`: arguments are schema-validated and policy-classified.
6. `approval_pending`: only for gated tools when policy requires user decision.
7. `tool_started`: shared service starts the tool execution.
8. `tool_result_ready`: one result envelope is produced for every tool call.
9. `provider_continued`: provider adapter feeds tool results back into the same
   conversation.
10. `finish_candidate`: model calls the provider-native `finish` tool with
    outcome and acceptance refs.
11. `acceptance_checked`: deterministic gates accept or reject the candidate.
12. `finalized`: lane result, metrics, replay index, and proof artifact manifest
    are written.

Crash/reentry must resume from durable lane state. If the runtime cannot prove
where to resume, it should mark the lane attempt `blocked` with a replayable
reason instead of reconstructing hidden state.

## Provider-Native Tool Calls

The v2 loop uses provider-native tool calls when the provider supports them.
The provider-specific wire shape stays in an adapter. The core lane sees only a
provider-neutral envelope.

### Provider Adapter Responsibilities

Each adapter owns:

- converting prompt sections and native tool schemas into a provider request;
- streaming or collecting provider responses;
- extracting assistant text, reasoning summaries if available, and tool calls;
- preserving provider call ids;
- building provider-native tool result messages;
- translating provider finish/stop reasons into lane events;
- reporting token usage and cache usage when available;
- refusing runtime start when the provider lacks native tool-call support.

Adapters do not own:

- approval policy;
- filesystem safety;
- command execution;
- output retention;
- acceptance;
- replay redaction;
- prompt-section metadata semantics;
- provider-specific cache transport in this milestone.

### ToolCallEnvelope

Every provider tool call is normalized:

```json
{
  "schema_version": 1,
  "lane_attempt_id": "lane-implement_v2-session-todo-attempt",
  "provider": "openai|anthropic|other",
  "provider_message_id": "assistant message id when available",
  "provider_call_id": "native tool call id",
  "mew_tool_call_id": "lane-scoped monotonic id",
  "turn_index": 1,
  "sequence_index": 1,
  "tool_name": "read_file",
  "arguments": {},
  "raw_arguments_ref": "optional artifact ref",
  "received_at": "iso8601",
  "status": "received|validated|rejected|executing|completed"
}
```

`provider_call_id` is the pairing authority for the next provider message.
`mew_tool_call_id` is the mew audit/replay id. Both are persisted.

### ToolResultEnvelope

Every call gets exactly one paired result:

```json
{
  "schema_version": 1,
  "lane_attempt_id": "lane-implement_v2-session-todo-attempt",
  "provider_call_id": "native tool call id",
  "mew_tool_call_id": "lane-scoped monotonic id",
  "tool_name": "read_file",
  "status": "completed|failed|denied|invalid|interrupted|running|yielded",
  "is_error": false,
  "content": [],
  "content_refs": [],
  "evidence_refs": [],
  "side_effects": [],
  "started_at": "iso8601",
  "finished_at": "iso8601-or-null"
}
```

For providers that distinguish error tool results, `is_error=true` is used for
unknown tools, schema validation failures, denied approvals, execution
exceptions, interrupted tools, and synthetic fallback results. Nonterminal
managed command results use `status=running|yielded` and are not acceptance
evidence even when `is_error=false`.

`status` is mew-internal metadata. Provider APIs generally treat a tool result
as a completed message payload for a prior call id. Therefore `running` and
`yielded` are serialized inside ordinary provider-visible `tool_result` content,
not as provider protocol states. The provider-visible result is still the one
required paired result for that call id, with `is_error=false`, no acceptance
evidence refs, and content that tells the model which command run is still live
and which follow-up tools can poll or inspect it.

### Pairing Invariants

The transcript must satisfy these invariants:

- Every provider tool call produces exactly one provider-visible tool result.
- Tool results carry the same provider call id the model emitted.
- A provider call id is never reused for a different mew tool call.
- A mew tool call id is never reused inside a lane attempt.
- Unknown tool names produce a model-visible error result, not a broken turn.
- Invalid arguments produce a model-visible error result that includes the
  validation problem and schema version.
- Approval denial produces a model-visible denial result and an approval event.
- Interrupted or cancelled tools produce synthetic paired results before the
  next provider turn.
- Streaming fallback or provider retry must discard orphaned results and
  synthesize error results for any calls that the provider already emitted.
- The lane must never send ordinary user text between required tool results
  when the provider requires a contiguous tool-result sequence.

These invariants are the main reason v2 is a separate lane. They are awkward to
retrofit into v1's JSON action loop without changing v1 behavior.

### Finish Tool Wire Shape

V2 uses a provider-native `finish` tool. Completion is not parsed from ordinary
assistant text. The model must call `finish` when it wants to end the lane
attempt, report a read-only diagnosis, or declare that it is blocked.

Provider-neutral tool spec:

```json
{
  "name": "finish",
  "description": "Finalize the lane attempt with acceptance evidence or a structured non-completion result.",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["summary", "outcome", "acceptance_evidence_refs"],
    "properties": {
      "summary": {"type": "string"},
      "outcome": {
        "type": "string",
        "enum": ["task_complete", "analysis_ready", "blocked", "failed", "deferred"]
      },
      "acceptance_evidence_refs": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["kind", "id"],
          "additionalProperties": true,
          "properties": {
            "kind": {
              "type": "string",
              "enum": ["command_evidence", "tool_result", "file_diff", "approval", "replay_manifest"]
            },
            "id": {"type": ["string", "integer"]},
            "lane_attempt_id": {"type": "string"}
          }
        }
      },
      "acceptance_checks": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["constraint", "status", "evidence_refs"],
          "additionalProperties": false,
          "properties": {
            "constraint": {"type": "string"},
            "status": {"type": "string", "enum": ["verified", "blocked", "unknown"]},
            "evidence_refs": {"type": "array", "items": {"type": "object"}}
          }
        }
      },
      "files_changed": {"type": "array", "items": {"type": "string"}},
      "commands_run": {"type": "array", "items": {"type": "string"}},
      "remaining_risks": {"type": "array", "items": {"type": "string"}},
      "next_action_hint": {"type": "string"},
      "fallback_lane": {"type": "string"}
    }
  }
}
```

Validation rules:

- `outcome=task_complete` requires at least one acceptance check, every
  acceptance check must be `verified`, and each check must cite deterministic
  evidence refs that resolve inside the same lane attempt or shared
  work-session evidence.
- Command refs used for completion must resolve to terminal successful command
  evidence. Running/yielded command metadata is rejected.
- File-diff or mutation refs must be fresh after the latest relevant write.
- Approval refs prove permission only; they do not prove task acceptance by
  themselves.
- `outcome=analysis_ready` is allowed only in read-only/plan phases with no
  file mutations and no claim that the task is done.
- `outcome=blocked|failed|deferred` may include empty
  `acceptance_evidence_refs`, but must include a summary and next action hint.
- `fallback_lane` in a finish payload is advisory only and must match the
  finalized `LaneResult.next_reentry_hint`; it must not trigger execution.

Rejected finish behavior:

- Schema-invalid finish calls return a paired provider-visible tool result with
  `is_error=true`, validation details, and a request to call `finish` again or
  continue tool use.
- Schema-valid but acceptance-rejected finish calls return a paired
  provider-visible tool result with `is_error=false`, content
  `finish_accepted=false`, rejected evidence refs, acceptance blockers, and the
  next allowed action. The provider conversation continues.
- If the model repeats rejected finish calls without new evidence, the lane may
  finalize as `blocked` with a replayable reason instead of looping forever.

## Tool Schema Boundaries

The v2 tool surface is small and fail-closed. Tool definitions are structured
data with name, description, JSON schema, capability class, risk class, approval
requirements, concurrency behavior, interrupt behavior, dry-run support, and
result-size policy.

The tool factory default should be conservative:

- `read_only=false` unless explicitly true;
- `concurrency_safe=false` unless explicitly true;
- `requires_approval=true` for writes, edits, patches, destructive commands,
  network writes, and unknown risk;
- `dry_run_supported=false` unless implemented;
- `interrupt_behavior=cancel` for quick read/search operations;
- long run/test commands are block/yield managed by the command runtime, not
  killed by a generic turn abort without cleanup;
- unknown tools are rejected with paired tool results.

### Read Tools

Representative tools:

- `read_file`
- `list_dir` or `inspect_dir`
- `git_status`
- `git_diff`
- `read_command_output`

Boundary:

- read-only;
- concurrency-safe when the implementation does not mutate shared state;
- allowed only under configured readable roots or explicitly allowed artifact
  refs;
- accepts path, optional line range, and max chars;
- returns bounded content plus content refs for larger data;
- refuses path traversal, symlink escapes if the shared file service cannot
  prove the resolved path is allowed, binary reads unless explicitly requested,
  and unbounded full-repo reads.

`git_diff` is read-only but may expose large data. It must default to stat or
bounded output and require an explicit cap for full diff content.

### Search Tools

Representative tools:

- `search_text`
- `glob`

Boundary:

- read-only;
- concurrency-safe;
- implemented through structured search APIs or bounded `rg`/glob helpers, not
  arbitrary shell strings;
- accepts literal query or explicit regex mode, path/glob filters, max results,
  and max output chars;
- skips ignored/cache/virtualenv/build directories according to shared mew
  policy unless explicitly overridden by the task contract;
- returns file, line, and bounded preview refs;
- never writes search indexes or caches inside the workspace without an
  explicit shared-service contract.

### Run Tools

Representative tools:

- `run_command`
- `run_tests`
- `poll_command`
- `cancel_command`
- `read_command_output`

Boundary:

- all work-mode command execution goes through the generic managed execution
  service, including short commands;
- command lifecycle routing is separate from safety/approval classification;
- every run has command id, cwd, timeout, foreground budget, output ref,
  command evidence, and lane/tool ids;
- every result includes terminal or nonterminal status;
- nonterminal `running` or `yielded` status is planning evidence only;
- only terminal command evidence can satisfy acceptance;
- one side-effecting command per work session is allowed by default;
- read-only commands may run concurrently only when the command policy can prove
  they do not conflict with a yielded side-effecting command;
- stdin, PTY, interactive prompts, persistent shells, and multiple live
  side-effecting processes are deferred.

`run_command` accepts either argv or shell form. Shell form has higher risk and
must pass command policy and approval gates. The schema should include:

- command or argv;
- cwd;
- timeout seconds;
- foreground budget seconds;
- execution contract;
- env overlay with secret-free summary;
- risk class;
- expected output cap;
- optional reason for approval.

The existing nested resident loop guard remains required. Commands that invoke
`mew work`, another resident loop, destructive workspace reset, publication, or
external-visible side effects must be blocked or approval-gated according to the
shared safety policy.

### Write Tools

Representative tool:

- `write_file`

Boundary:

- approval-gated;
- dry-run preview required before apply unless the lane is in an explicitly
  approved noninteractive policy that still records the approval source;
- allowed only under writable roots;
- create/overwrite flags are explicit;
- result records before/after hash, path, bytes, and diff/stat refs;
- refuses symlink escapes, directory writes, binary writes unless explicitly
  allowed, generated proof artifact overwrites outside the lane namespace, and
  writes to governance/roadmap/safety surfaces unless task contract and approval
  allow them.

### Edit Tools

Representative tools:

- `edit_file`
- `edit_file_hunks`

Boundary:

- approval-gated;
- dry-run preview required before apply;
- exact old text or structured hunk match required;
- optional expected old hash or mtime should be supported for stale-window
  detection;
- ambiguous matches fail closed unless `replace_all=true` is explicit and
  approved;
- result records matched ranges, before/after hash, diff ref, and whether the
  edit was applied;
- failed dry-runs return paired model-visible results and do not mutate files.

### Apply Patch Tool

Representative tool:

- `apply_patch`

Boundary:

- approval-gated;
- patch grammar validation before any filesystem mutation;
- dry-run diff/stat preview before apply;
- allowed roots checked for every touched path and move target;
- add/delete/update/move are classified separately for risk;
- destructive deletes and broad generated-file rewrites require explicit
  approval;
- result records parsed patch summary, before/after hashes where available,
  changed paths, and diff/proof refs;
- provider-native patch calls must not bypass mew's shared patch parser,
  approval, and write service.

`apply_patch` should be the preferred write primitive for multi-file changes
only after v2 has passed single-file write/edit gates.

## Approval, Dry-Run, And Safety Gates

V2 freezes a permission context at lane-attempt start and records a policy
snapshot for each provider turn. Policy changes are events, not mutable ambient
state.

### PermissionContext

Minimum fields:

- mode: `read_only`, `plan`, `exec`, `write`, or `bypass` if later supported;
- readable roots;
- writable roots;
- shell/network/destructive permissions;
- approval policy;
- prompt avoidance flag for background/noninteractive runs;
- allowed/denied/ask rules by source;
- task-contract overrides;
- lane id and lane attempt id.

Priority should be explicit:

```text
explicit user turn approval
  > task contract
  > local project/session settings
  > persisted work-session defaults
  > global defaults
```

Silence is never approval.

### Approval Events

Approval requests are durable artifacts:

```json
{
  "schema_version": 1,
  "approval_id": "approval id",
  "lane_attempt_id": "lane attempt",
  "mew_tool_call_id": "tool id",
  "tool_name": "edit_file",
  "risk_class": "write|destructive|shell|network|unknown",
  "summary": "",
  "diff_ref": "optional diff preview",
  "command": "optional command",
  "cwd": "optional cwd",
  "decision": "pending|approved|denied|expired",
  "decided_by": "user|policy|hook",
  "decided_at": "iso8601"
}
```

If the process exits while approval is pending, reentry resumes the durable
approval or marks it stale. A background lane that cannot prompt should return
`blocked_for_approval` instead of auto-approving.

### Dry-Run Rules

- Writes, edits, and patches default to dry-run preview in v2 until the write
  phase gate passes.
- Dry-run output is a tool result and a proof artifact, not a mutation.
- Applying a dry-run proposal requires either a follow-up approved apply call or
  a policy mode that explicitly authorizes apply.
- Rejected dry-runs remain replayable and can be repaired by the model.
- Dry-run diffs must be bounded in provider-visible results, with full refs
  stored as artifacts.

### Safety Gates

Safety is enforced before execution and again before acceptance:

- tool schema validation;
- allowed root resolution;
- symlink/path traversal checks;
- command risk classification;
- nested resident-loop rejection;
- destructive command/write denial or approval;
- one-side-effecting-command concurrency limit;
- command timeout and output caps;
- nonterminal command proof rejection;
- post-edit acceptance freshness checks;
- lane namespace checks for artifacts;
- provider-result pairing checks.

If a tool's safety class is unknown, v2 treats it as side-effecting,
non-concurrency-safe, approval-gated, and non-acceptance until proven otherwise.

## Managed Exec Integration

V2 should consume the existing generic managed execution substrate rather than
creating a new command runner.

### Command Lifecycle

The lane-visible lifecycle is:

```text
start -> completed
start -> failed
start -> yielded/running -> poll -> completed
start -> yielded/running -> poll -> still running
start -> yielded/running -> cancel -> interrupted/killed
start -> timeout -> timed_out
start -> process lost -> orphaned
```

Every command run has:

- command run id;
- lane attempt id;
- provider call id;
- mew tool call id;
- command/argv and cwd;
- start/end timestamps;
- timeout and foreground budget;
- process status;
- output ref;
- bounded head/tail;
- terminal command evidence ref if finalized;
- nonterminal command evidence ref if yielded.

### Provider Result Semantics

For a quick terminal command, the provider receives one tool result with
terminal status, exit code, bounded output, output ref, and evidence refs.

For a long command that yields, the provider receives one paired tool result
with `status=yielded` or `status=running`, the command run id, output ref,
current output tail, and suggested available tools such as `poll_command` and
`read_command_output`. This result does not prove the task. It tells the model
that the command is alive and the lane can continue useful work or poll later.
The provider-visible wire value is still an ordinary `tool_result` payload for
the original call id:

```json
{
  "tool_result": {
    "tool_use_id": "provider-call-id",
    "is_error": false,
    "content": {
      "mew_status": "yielded",
      "acceptance_evidence": false,
      "command_run_id": "work_session:1:command_run:4",
      "output_ref": "work-session/1/commands/4/output.log",
      "stdout_tail": ["bounded tail"],
      "available_followups": [
        {"tool": "poll_command", "command_run_id": "work_session:1:command_run:4"},
        {"tool": "read_command_output", "command_run_id": "work_session:1:command_run:4"}
      ]
    }
  }
}
```

`mew_status=running|yielded` is metadata inside the content object. It is not a
provider protocol state, not an error, and not acceptance evidence.

For `poll_command`, a terminal poll produces a new terminal evidence ref. A
still-running poll returns a paired nonterminal result. Polling must not create
acceptance proof until the command finalizes.

### Long And Nonterminal Rules

- Running/yielded command evidence has `finish_order=0` or equivalent
  nonterminal marker.
- Acceptance rejects running, yielded, interrupted, killed, timed-out,
  orphaned, nonzero, contradictory, masked, spoofed, and stale command evidence.
- A live side-effecting command blocks additional side-effecting tools by
  default.
- Read-only tools may continue while a command is yielded if they do not
  inspect unstable generated outputs as proof.
- Reentry must validate live-process ownership before polling. Bare pid reuse
  is not authority.
- If ownership cannot be validated after restart, mark the command orphaned and
  decide through recovery policy, not hidden process assumptions.
- Output refs stay under the work-session or lane artifact root.

This is the core compatibility point with current M6.24 substrate work. V2 gets
a native tool loop, but it must not weaken the proof boundary that managed exec
already established.

## Transcript Replay And Proof Artifacts

V2 needs replay that can reconstruct why the model chose each next action and
prove that the runtime did not hide rescue edits or unpaired tool calls.

### Artifact Namespace

Recommended namespace:

```text
proof-artifacts/work-sessions/<session-id>/lane-implement_v2/<lane-attempt-id>/
  transcript.jsonl
  provider-messages.jsonl
  prompt-sections.json
  tool-calls.jsonl
  tool-results.jsonl
  approvals.jsonl
  command-runs.jsonl
  file-mutations.jsonl
  diffs/
  outputs/
  metrics.json
  result.json
  manifest.json
```

The exact path can follow existing `work_replay.py` conventions, but the lane id
must be in the path or metadata for every v2 replay/proof artifact. V2 must not
write into v1 legacy replay locations except through a compatibility index that
points to lane-scoped artifacts.

### Transcript Events

Minimum event types:

- `lane_attempt_started`
- `prompt_sections_rendered`
- `provider_request_started`
- `provider_response_delta` or bounded response summary
- `provider_message_completed`
- `tool_call_received`
- `tool_call_validated`
- `tool_call_rejected`
- `approval_requested`
- `approval_decided`
- `tool_started`
- `tool_progress`
- `tool_result_completed`
- `managed_exec_started`
- `managed_exec_yielded`
- `managed_exec_finalized`
- `file_dry_run_created`
- `file_mutation_applied`
- `finish_candidate`
- `acceptance_checked`
- `lane_attempt_finalized`

Events must include lane attempt id, turn index, sequence index, and stable
refs. Large content should be stored as artifact refs with bounded previews in
the transcript.

### Replay Checks

Replay should validate:

- every tool call has exactly one result;
- every result references a known call;
- result order is valid for the provider adapter;
- every applied mutation has approval or policy proof;
- every file change is inside allowed roots;
- every command output ref is under the allowed artifact root;
- finish acceptance refs resolve to terminal proof;
- no hidden supervisor rescue edits appear outside v2 tool events;
- prompt-section hashes match the rendered prompt;
- lane metadata and artifact paths agree.

### Proof Manifest

`manifest.json` should summarize:

- lane id and lane attempt id;
- task id and work session id;
- model/provider/effort;
- prompt section metrics;
- provider turn count;
- tool counts by class and status;
- file mutation refs;
- command evidence refs;
- approval refs;
- finish tool result and acceptance decision;
- fallback lane hint if present, with no fallback execution counted;
- verifier/acceptance result;
- final lane status;
- replay validation status.

Reviewers should be able to inspect the manifest first, then drill into
transcript, tool results, diffs, outputs, and command evidence.

## Prompt Section Registry Integration

V2 must assemble prompts through the existing prompt section registry contract.
Do not grow one large inline prompt.

Current registry metadata already records:

- section id;
- version;
- title;
- content hash;
- stability;
- cache policy;
- cache hint;
- char counts;
- cacheable prefix chars.

V2 should add lane-specific sections rather than mutating v1 section ids.

### Proposed V2 Sections

Stable/cacheable prefix:

- `implement_v2_lane_base`: invariant lane role, one-authoritative-lane rule,
  finish contract, proof boundary.
- `implement_v2_tool_contract`: provider-native tool loop rules, result
  pairing, invalid/denied/synthetic result handling.
- `implement_v2_tool_schema_read_search`: read/search schema summaries.
- `implement_v2_tool_schema_run`: managed exec and command evidence contract.
- `implement_v2_tool_schema_write`: write/edit/apply-patch dry-run and approval
  contract, included only in write-capable phases.
- `implement_v2_safety_policy`: safety and approval invariants.

Session-specific sections:

- `implement_v2_task_contract`: task objective, acceptance constraints, allowed
  roots, explicit non-goals.
- `implement_v2_active_memory`: scoped memory and reentry hints.
- `implement_v2_lane_state`: compact lane-local state needed for resume.

Dynamic sections:

- `implement_v2_dynamic_evidence`: recent tool results, command state, failure
  evidence, and verifier feedback.
- `implement_v2_context_json`: final structured context suffix.

### Cache-Neutral Metadata

"Cache-neutral" means the registry records facts that a future provider adapter
can use, but this milestone does not implement provider-specific cache-control
transport.

Rules:

- Keep section ids and versions stable.
- Keep cacheable sections before session/dynamic sections.
- Track section hash churn and char deltas.
- Mark dynamic sections dynamic instead of trying to cache them.
- Keep provider-specific cache headers, cache scopes, and cache-editing APIs out
  of M6.23.2.
- If a provider reports cached token usage, store it as provider-reported
  metrics. Do not make lane behavior depend on that report.

The v2 provider adapter may map prompt sections into provider request blocks,
but it must preserve the registry metrics and artifact hashes. Future cache
transport work can use those artifacts without changing lane semantics.

## Metrics For V1/V2 Comparison And M6.24 Reentry

Metrics should be comparable across v1 and v2 while allowing v2-specific tool
loop analysis.

### Lane Attempt Metrics

- lane id;
- lane attempt id;
- task id and task kind;
- model backend, provider, model, effort;
- default-off or explicit selected flag;
- wall-clock start/end/duration;
- first assistant output latency;
- first tool call latency;
- first tool result latency;
- first edit latency;
- total provider turns;
- total tool calls;
- outcome: completed, analysis_ready, blocked, failed, interrupted, deferred,
  or unavailable;
- fallback recommended;
- fallback execution counted: always false for v2;
- rescue edit used;
- reviewer decision;
- verifier/acceptance result;
- replay bundle path;
- later reuse value.

This extends the existing `lane_attempt` calibration shape rather than replacing
it.

### Tool Loop Metrics

- tool counts by tool name, class, and status;
- provider tool-call ids paired vs unpaired;
- synthetic tool result count and reason;
- schema validation failure count;
- unknown tool count;
- approval prompts, approvals, denials, expirations;
- dry-run count, apply count, dry-run-to-apply ratio;
- file mutation count and changed path count;
- command run count by status;
- nonterminal command yield/poll/finalize counts;
- command output bytes and truncation count;
- command terminal evidence refs cited in finish;
- acceptance refs resolved vs rejected;
- interrupt/cancel count.

### Prompt Metrics

- prompt section count;
- total chars;
- static/semi-static/dynamic chars;
- cacheable chars;
- cacheable prefix chars;
- section hashes;
- section hash churn across attempts;
- provider-reported input/output/reasoning tokens when available;
- provider-reported cached input tokens when available.

### M6.24 Resume Metrics

For later M6.24 proof work, every proof artifact should record:

- explicit lane id and lane attempt id;
- whether the lane was v1 or v2;
- task cohort/scoped proof id without task-specific behavior in the lane;
- runner errors or external harness errors as external evidence;
- terminal acceptance result;
- replay validation status;
- v1/v2 aggregate success, failure class, wall time, tool count, and verifier
  failure rates.

The comparison question is not "did v2 pass one benchmark task?" It is whether
v2 improves generic software/coding execution quality while preserving proof
discipline and v1 baseline behavior.

## Phased Implementation Plan

Each phase is default-off unless explicitly stated. No phase changes v1
behavior.

### Phase 0 - Design Acceptance And Drift Guard

Deliverables:

- this design reviewed and accepted or revised;
- explicit decision that v2 remains default-off;
- M6.24 remains paused behind lane isolation until lane identity is recorded.

Gate:

- reviewers agree the design covers provider-native calls, pairing, managed
  exec, approvals, prompt sections, metrics, replay, non-goals, and rollback.

Tests:

- none beyond artifact/document review.

### Phase 1 - Lane Boundary And V1 Baseline Lock

Deliverables:

- lane registry keeps v1/tiny default behavior;
- v1 adapter wraps existing runtime without prompt/tool behavior change;
- lane-scoped artifact metadata exists for v1 and placeholder v2;
- placeholder v2 remains runtime-unavailable and non-authoritative.

Gate:

- focused v1 regression passes;
- missing lane still defaults to legacy behavior;
- explicit `implement_v1` resolves to v1 behavior;
- placeholder v2 cannot be selected as a write-capable runtime;
- v1 and v2 placeholder artifacts cannot collide.

Tests:

- lane registry tests;
- v1 adapter no-behavior-change snapshot or focused fixtures;
- replay path namespace tests;
- unsupported lane fallback/defer tests.

### Phase 2 - Provider-Neutral Types And Transcript Skeleton

Deliverables:

- `LaneInput`, `LaneResult`, `ToolCallEnvelope`, `ToolResultEnvelope`,
  transcript events, proof manifest, and metrics schemas;
- provider adapter interface with at least fake/test provider;
- replay validator for pairing invariants.

Gate:

- fake provider can emit text, tool calls, invalid tool calls, and finish
  events into a lane transcript;
- every synthetic/invalid/unknown call gets a paired result;
- replay validator rejects unpaired calls and orphan results;
- no filesystem or command side effects are available yet.

Tests:

- transcript serialization tests;
- provider adapter fake event tests;
- pairing invariant tests;
- prompt-section metric artifact tests;
- lane namespace tests.

### Phase 3 - Read/Search V2 Spike

Deliverables:

- default-off v2 read-only runtime;
- provider-native schemas for read/search/glob/git status/diff bounded reads;
- prompt sections for v2 base, tool contract, read/search tools, safety, task
  contract, dynamic evidence, and context JSON;
- read-only replay/proof artifacts.

Gate:

- v2 can inspect a fixture workspace through provider-native tool calls and
  produce a diagnosis or plan;
- successful read-only diagnosis/plan finalizes as
  `LaneResult.status=analysis_ready`, with `updated_lane_state.read_only_result`
  carrying `kind=diagnosis|plan`, inspected paths, open questions, and proposed
  next actions;
- `analysis_ready` is counted as a read-only spike success metric, not an
  implementation completion metric;
- read/search tools cannot mutate workspace state;
- tool results are paired and replay-valid;
- v1 remains default and focused regression still passes.

Tests:

- fake provider read/search loop;
- read-only finish tool produces `analysis_ready`;
- read-only finish cannot produce `completed`;
- allowed-root/path traversal rejection;
- result-size clipping and content-ref tests;
- concurrent read/search ordering tests if concurrency is enabled;
- prompt section id/hash/cache policy tests.

### Phase 4 - Managed Exec Tools

Deliverables:

- v2 `run_command`, `run_tests`, `poll_command`, `cancel_command`, and
  `read_command_output` tools using shared managed exec;
- terminal and nonterminal command results in provider-native paired tool
  results;
- command evidence refs and output refs in proof artifacts;
- command safety/approval policy separated from lifecycle.

Gate:

- short command finalizes in one tool result;
- long command yields, can be polled, and finalizes with terminal evidence;
- nonterminal command results cannot satisfy acceptance;
- one side-effecting command concurrency limit is enforced;
- orphan/lost process states are non-success evidence.

Tests:

- command completes zero/nonzero;
- command yields then completes;
- command timeout/killed/interrupted/orphaned;
- poll/read output refs;
- acceptance rejects nonterminal command evidence;
- concurrent side-effecting command rejection;
- v1 command behavior unchanged under v1 lane.

### Phase 5 - Write/Edit/Apply Patch Behind Approval

Deliverables:

- write/edit/apply-patch tool schemas;
- dry-run previews and diff artifacts;
- durable approval events;
- approved apply path through shared file mutation services;
- post-write proof and acceptance freshness events.

Gate:

- v2 can propose a dry-run edit without mutation;
- v2 can apply an approved small edit in a fixture workspace;
- denied approval produces paired model-visible result and no mutation;
- stale/ambiguous edit attempts fail closed;
- replay proves every mutation has approval/policy evidence.

Tests:

- write allowed root and denied root;
- edit exact match, no match, ambiguous match;
- apply_patch parse failure, dry run, approved apply, denied apply;
- symlink/path traversal rejection;
- governance/safety surface approval guard;
- replay no-hidden-mutation check.

### Phase 6 - Acceptance, Replay, And Metrics Close

Deliverables:

- finish candidate format for v2;
- deterministic acceptance integration;
- proof manifest and replay validation report;
- v1/v2 comparable metrics;
- failure classification for v2 runtime issues.

Gate:

- completed v2 means acceptance passed;
- rejected finish returns model-visible next action or blocked result;
- replay manifest validates all finished attempts;
- metrics are sufficient to compare v1 and v2 on the same fixture task shapes.

Tests:

- finish with valid terminal evidence;
- finish without evidence rejected;
- finish with stale/nonterminal evidence rejected;
- metrics schema tests;
- proof manifest tests;
- replay validation failure tests.

### Phase 7 - A/B Gate Before M6.24 Resume

Deliverables:

- explicit operator command/config to select `implement_v1` or `implement_v2`;
- small non-benchmark fixture suite run with both lanes where possible;
- documented M6.24 reentry decision naming selected lane.

Gate:

- v1 baseline remains valid;
- v2 artifacts are separate and replay-valid;
- no artifact collision or v1 behavior change;
- M6.24 proof artifacts can record lane id and lane attempt id.

Tests:

- same fixture v1/v2 comparison where v2 supports the needed tools;
- proof summary lane counts;
- resume/reentry from v2 artifact;
- v1 default route regression.

Only after this gate should any M6.24 proof run use v2, and only by explicit
lane selection.

## Rollback And Defer Conditions

### Immediate Rollback Conditions

Disable v2 runtime availability and fall back to explicit v1 use if any of
these occur:

- v1 focused regression changes behavior;
- missing lane no longer defaults to v1/tiny behavior;
- v1 and v2 artifact paths collide;
- replay validator finds unpaired provider tool calls in a completed attempt;
- write/edit/apply-patch mutates without approval or allowed-root proof;
- command nonterminal evidence is accepted as completion;
- provider adapter loses call ids or cannot synthesize required error results;
- prompt section rendering mutates v1 section ids or hashes unexpectedly;
- metrics cannot identify which lane produced a proof artifact.

Rollback mechanism:

- set `implement_v2.runtime_available=false`;
- keep `implement_v2.default=false`;
- keep persisted v2 artifacts for review;
- record rollback reason in lane attempt metrics and roadmap/status notes when
  the rollback affects milestone progress;
- do not delete or rewrite v1 artifacts.

### Defer Conditions

Defer write capability if:

- read-only provider loop is unstable;
- provider pairing semantics differ enough that the adapter cannot guarantee one
  result per call;
- durable approval artifacts are not ready;
- dry-run preview cannot be replayed;
- allowed-root checks are incomplete.

Defer managed exec capability if:

- command output refs are not durable;
- yielded commands cannot be safely polled/finalized;
- live process ownership cannot be validated;
- nonterminal proof rejection has gaps;
- command safety classification is mixed with lifecycle routing.

Defer M6.24 resume if:

- lane identity is not present in proof artifacts;
- v1 baseline has not been rechecked after lane boundary changes;
- v2 metrics are incomplete and v2 is selected;
- reviewers find accepted must-fix findings in lane isolation, pairing, safety,
  or replay.

## Open Questions

- Should v2's first provider adapter target one provider only, or should Phase 2
  require two fake adapters that exercise different call/result ordering rules?
- Should v2 store provider raw messages fully by default, or store bounded
  previews plus raw refs to reduce artifact size?
- Which current v1 write/edit helpers can be reused safely without carrying
  v1-specific cached-window assumptions into v2?
- Should `run_tests` be classified as side-effecting by default even when test
  commands are read-like in many repositories?
- What is the smallest shared approval UX that works for CLI, chat, and
  background/noninteractive modes without adding a full new permission UI?

These questions should not block Phase 1 or Phase 2. They should be resolved
before write-capable v2 runs.

## Done When

This design is ready to drive implementation when reviewers agree that it:

- preserves v1 as default with no behavior change;
- defines a lane runtime contract and lifecycle;
- specifies provider-native tool calls and tool result pairing;
- bounds read/search/run/write/edit/apply-patch schemas;
- gates approval, dry-run, and safety;
- reuses managed exec without weakening nonterminal proof rules;
- defines transcript replay and proof artifacts;
- integrates prompt section registry metadata without cache transport work;
- defines metrics for v1/v2 comparison and M6.24 reentry;
- lays out phase gates and tests;
- names non-goals, rollback, and defer conditions.
