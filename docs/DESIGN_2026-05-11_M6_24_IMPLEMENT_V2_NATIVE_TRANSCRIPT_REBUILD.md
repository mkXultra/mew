# Design 2026-05-11 - M6.24 Implement V2 Native Transcript Rebuild

Status: implementation in progress.

Implementation checkpoint 2026-05-11:

- Phase 0-1 native transcript schema and artifact gates are committed.
- Phase 2-4 native provider/tool/sidecar scaffolds are committed.
- Phase 5-6 CLI selection and native validation gates are committed.
- Phase 7 quarantine slice is committed at `150db0b`: the
  `mew.implement_lane` public package surface no longer exports legacy
  model-JSON v2 runners or provider adapters, and the native gate rejects those
  symbols in production native paths.
- Live provider-native execution slice is implemented: CLI-selected
  `implement_v2` now calls the native Responses runtime, emits provider-native
  transcript artifacts when an artifact root is supplied, and keeps the old
  unavailable native stub out of the selected command route.
- The legacy model-JSON runtime still exists only as explicit quarantine for
  old unit tests, replay compatibility, and dogfood emulators. It is not the
  selected production v2 main path.
- Native v2 speed/proof evidence may now start only after the native-loop gate
  stays green and the next bounded diagnostic run emits authoritative
  `response_transcript.json`, `response_items.jsonl`, and `proof-manifest.json`
  from the live provider-native path.
- Tiny live native-loop gate is green:
  `proof-artifacts/m6_24_native_loop_gate_20260511_live_portable/` completed
  with `work_exit_code=0`, runtime `implement_v2_native_transcript_loop`,
  transport `provider_native`, paired `inspect_dir -> write_file -> run_tests
  -> finish`, valid pairing (`4/4`, no errors), first write at turn 2, first
  verifier at turn 3, and
  `scripts/check_implement_v2_native_gate.py --artifact ... --json` returned
  `ok=true`.
- Native HOT_PATH fastcheck now accepts native transcript artifacts directly:
  it reads authoritative `response_transcript.json`, verifies
  `response_items.jsonl`, manifest hash/pairing, normalized trace parse
  cleanliness, native loop-control replay, and positive `search_text` outputs
  carrying compact model-visible `path:line` anchors without requiring legacy
  `history.json`. The next proof step is not a bare 10min diagnostic. It is
  the pre-speed gate in this order: focused UT/local checks -> native
  `scripts/check_implement_v2_hot_path.py --artifact <native-artifact>
  --no-baseline` -> replay/dogfood/emulator where applicable -> exactly one
  10min native step-shape diagnostic -> reference-step comparison. Broad
  `speed_1` / `proof_5` measurement remains blocked until that gate is green.

Scope: no-backward-compatibility redesign of `implement_v2` as a provider-native
tool/function calling loop. This document does not authorize code changes by
itself.

## Inputs Reviewed

Existing designs and diagnostics:

- `docs/DESIGN_2026-05-05_M6_23_2_IMPLEMENT_V2_NATIVE_TOOL_LOOP.md`
- `docs/DESIGN_2026-05-07_M6_24_INTEGRATION_OBSERVABILITY.md`
- `docs/DESIGN_2026-05-08_M6_24_TYPED_EVIDENCE_ACCEPTANCE.md`
- `docs/DESIGN_2026-05-08_M6_24_IMPLEMENT_V2_HOT_PATH_COLLAPSE.md`
- `docs/DESIGN_2026-05-10_M6_24_IMPLEMENT_V2_WORKFRAME_REDESIGN.md`
- `docs/DESIGN_2026-05-11_M6_24_TOOL_HARNESS_WORKFRAME_VARIANTS.md`
- `docs/DESIGN_2026-05-11_M6_24_TRANSITION_CONTRACT_RUNTIME_REPAIR_REDESIGN.md`
- `docs/M6_24_STEP_CAUSE_BREAKDOWN_2026-05-11.md`
- `docs/REVIEW_2026-05-11_IMPLEMENT_V2_NATIVE_LOOP_DRIFT_PREVENTION.md`

Current implementation surfaces:

- `src/mew/implement_lane/registry.py`
- `src/mew/implement_lane/provider.py`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/transcript.py`
- `src/mew/implement_lane/workframe.py`
- `src/mew/implement_lane/prompt.py`
- `src/mew/implement_lane/tool_policy.py`
- `src/mew/implement_lane/tool_harness_contract.py`
- `src/mew/commands.py`
- `src/mew/codex_api.py`

Reference and API shape:

- `references/fresh-cli/codex/codex-rs/protocol/src/models.rs`
- `references/fresh-cli/codex/codex-rs/core/src/client.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/tool_spec.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/responses_api.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`
- OpenAI Responses function-calling documentation, checked 2026-05-11:
  `https://developers.openai.com/api/docs/guides/function-calling`

## Problem

`implement_v2` was intended to be a Codex-like provider-native tool loop. The
current runtime is not that. The registry explicitly names
`runtime_id="implement_v2_model_json_tool_loop"` and
`provider_native_tool_loop=False`; the command path and result metrics repeat
the same runtime identity. The active runtime builds a full prompt, asks the
model to return one JSON object containing `summary`, `tool_calls`, optional
`finish`, and legacy `frontier_state_update`, then normalizes that model JSON
into provider-shaped envelopes.

That transport now distorts the architecture:

- native provider `ResponseItem` / tool-call items are not the saved source of
  truth;
- tool calls are model-authored JSON fields rather than provider output items;
- `history.json` is a prompt projection, not an authoritative conversation log;
- parse repair, patch-line JSON pressure, and model-authored frontier rejection
  are runtime concerns that native tool calling should avoid;
- WorkFrame/frontier/todo/evidence projections have become compensating
  structures for a weak model-facing transport.

The current observability work is valuable and must survive. The mistake would
be to keep polishing WorkFrame and model-JSON transport until it resembles a
native loop. The correct move is to rebuild `implement_v2` around a typed native
transcript and make WorkFrame/evidence/frontier artifacts projections over that
transcript.

## Decision

Rebuild `implement_v2` around a local, typed transcript of provider-native
response items. The transcript is the source of truth for model turns, native
tool calls, paired tool outputs, finish calls, metrics, replay, and derived
sidecars.

The main runtime path becomes:

```text
local native transcript + current sidecar digests
  -> provider request with native tool specs
  -> streamed provider ResponseItems
  -> append assistant/message/reasoning/tool-call items to local transcript
  -> execute each native tool call through mew's tool harness
  -> append exactly one paired tool-output item per call_id
  -> continue with transcript-derived input
  -> finish tool call
  -> deterministic acceptance
  -> proof, replay, WorkFrame/debug, metrics from transcript
```

Do not preserve model-JSON as the main path. Once native v2 closes its gates,
delete or quarantine `implement_v2_model_json_tool_loop` behind test-only or
artifact-replay names. No live production route should continue to ask the model
for a synthetic JSON object that wraps tool calls.

`implement_v1` remains the fallback lane. Fallback is a separate attempt, not a
same-attempt silent reroute. No compatibility promise is made for old
`implement_v2` prompt contracts, model-output fields, WorkFrame variants, or
model-JSON artifacts.

## Non-Goals

- No code implementation in this design document.
- No preservation of model-JSON transport as a live v2 runtime.
- No default switch of all implementation work to v2 before gates pass.
- No weakening of deterministic acceptance, write safety, command lifecycle,
  or verifier freshness.
- No WorkFrame-owned fork of tool execution, provider request parsing,
  evidence schema, benchmark harness, replay, or dogfood semantics.
- No task-specific MIPS, VM, Terminal-Bench, or benchmark-solver heuristic.
- No counting WorkFrame, frontier, prompt projection, parse repair, or
  observability-only work as native-loop implementation progress unless the
  phase also changes the provider-native transport boundary.

## Transport Non-Negotiables

The prior drift happened through individually reasonable substitutions:
provider-shaped local envelopes, a model-authored JSON response contract,
`history_json` prompt projection, and observability built around that projection
path. The native rebuild must fail closed against the same drift.

Hard invariants:

- Production native v2 runtime id is
  `implement_v2_native_transcript_loop`.
- Production native v2 reports `provider_native_tool_loop=True`.
- Native v2 completion credit requires
  `transport_kind="provider_native"` and
  `model_json_main_path_detected=false`.
- Native v2 must not call `call_codex_json`,
  `call_model_json_with_retries`, `run_live_json_implement_v2`, or any other
  model-JSON runtime turn path.
- Native v2 must not ask the model to return one synthetic JSON object with
  `tool_calls`, `finish`, `action`, `tools`, `calls`, or
  `frontier_state_update`.
- Assistant text that looks like JSON is assistant text. It is never parsed as
  the native v2 control protocol.
- Provider adapters expose native item capabilities: tool spec lowering,
  streamed item parsing, function/custom call extraction, paired output item
  construction, request descriptors, usage/event metadata, and
  `supports_native_tool_calls=True`.
- `provider_native_tool_loop` should be derived from runtime capability checks,
  not a manually asserted badge.
- If a provider lacks native tool support, native v2 returns
  `unavailable` or `blocked` with `fallback_lane=implement_v1`; it must not
  silently substitute model JSON.

Static drift gates:

- Production v2 imports and command paths reject `JsonModelProviderAdapter`,
  `run_live_json_implement_v2`, `_live_json_prompt`,
  `_normalize_live_json_payload`, `call_codex_json`, and
  `call_model_json_with_retries`.
- Production prompt strings reject `history_json:` as a transport section and
  reject a response contract that asks for JSON `tool_calls` or
  `frontier_state_update`.
- Production metrics, registry, proof manifest, command progress, dogfood, and
  replay scripts must agree on the native runtime id. Old
  `implement_v2_model_json_tool_loop` literals are allowed only in migration
  docs, legacy fixtures, or explicit quarantine tests.
- A "model text non-control" fixture emits assistant text containing a complete
  JSON object with `tool_calls` and `finish`; native v2 must record it as text
  and execute no tool from it.

These gates are part of native-loop closure. A phase that improves WorkFrame,
frontier, prompt history, parse repair, or hot-path projection without changing
native transport is sidecar/projection progress, not native-loop progress.

## Transcript Source Of Truth

Introduce a provider-neutral native transcript, conceptually:

```text
NativeTranscript
  schema_version
  lane_attempt_id
  provider
  model
  turns[]
  items[]
  indexes
```

Each item has a stable local id, monotonic sequence, provider ids when present,
raw provider type, normalized kind, and bounded/redacted payload:

```text
NativeTranscriptItem
  sequence
  turn_id
  response_id
  provider_item_id
  output_index
  kind:
    input_message
    assistant_message
    reasoning
    function_call
    custom_tool_call
    function_call_output
    custom_tool_call_output
    finish_call
    finish_output
  call_id
  tool_name
  arguments_json_text
  custom_input_text
  output_text_or_ref
  status
  raw_ref
  encrypted_reasoning_ref
  metrics_ref
```

Rules:

- The transcript, not WorkFrame, is authoritative for what the model saw and
  what it asked to do.
- Every provider tool call item with `call_id` must have exactly one paired
  output item with the same `call_id`.
- Pairing is per transcript sequence and per provider `call_id`; duplicated or
  missing ids produce synthetic error outputs before any side effect.
- Synthetic errors are represented as ordinary `function_call_output` or
  `custom_tool_call_output` items with the same `call_id` as the originating
  call and `status="synthetic_error"` or `is_error=true`. They are not a
  separate transcript kind because that would weaken the one-call-one-output
  invariant.
- Tool outputs are ordinary next-turn model input, not controller-only state.
- Large outputs are represented by bounded natural text plus `content_refs`.
  Full stdout/stderr, patch bodies, and raw artifacts stay in sidecar files.
- Finish is a native tool call, not a top-level model JSON field. A blocked
  finish receives a paired output and the loop continues. An accepted finish
  records the paired output and completes the lane without requiring another
  model turn.
- Reasoning items, assistant messages, provider request ids, response ids,
  token usage, and streaming event counters are transcript metadata. They are
  not used as deterministic evidence unless explicitly converted into typed
  evidence by a sidecar reducer.
- Encrypted reasoning blobs are referenced by `encrypted_reasoning_ref` and
  stored in `reasoning_sidecar.json`; the blob bytes are excluded from transcript
  hash preimages. The transcript hash includes the sidecar ref, provider item
  id, content length, and blob hash, not the encrypted blob itself.

The old `history.json` should become either:

- `response_transcript.json` plus `response_items.jsonl`; or
- a compatibility export generated from the native transcript for one transition
  phase only.

It must not remain the primary runtime log.

Authoritative versus derived files:

- `response_transcript.json` and `response_items.jsonl` are authoritative.
  They are the only persisted source of truth for native provider chronology,
  call ids, item ids, tool calls, paired outputs, finish calls, and replay
  chronology.
- `transcript_window.jsonl`, `request_descriptor.json`, `provider_requests.jsonl`,
  derived `history.json`, WorkFrame bundles, evidence indexes, and prompt/input
  inventories are rebuilt from the authoritative transcript plus sidecars. They
  are never edited or treated as authority directly.
- If a derived window cannot be reproduced from transcript plus sidecars, replay
  fails with `derived_window_mismatch` and completion credit is blocked.

## Native Provider Request Shape

For Codex/OpenAI Responses, the first native adapter should target the Responses
API shape used by the current `codex_api.py` and the fresh Codex reference, but
with tools enabled.

The client-side typed transcript owns request construction. Each provider
request is a derived window over `response_transcript.json` /
`response_items.jsonl` plus compact sidecar digests; no provider request, prompt
projection, or server conversation id is authority over the local transcript.

Baseline request:

```json
{
  "model": "<selected model>",
  "instructions": "<static implement_v2 instructions>",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "<task contract and current compact sidecar digest>"
        }
      ]
    }
  ],
  "tools": [
    {
      "type": "function",
      "name": "read_file",
      "description": "...",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Workspace-relative path to read."
          },
          "max_chars": {
            "type": "integer",
            "description": "Maximum characters to return."
          }
        },
        "required": ["path", "max_chars"],
        "additionalProperties": false
      },
      "strict": true
    },
    {
      "type": "custom",
      "name": "apply_patch",
      "description": "...",
      "format": {
        "type": "grammar",
        "syntax": "lark",
        "definition": "<apply_patch grammar>"
      }
    }
  ],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "stream": true,
  "store": false,
  "include": ["reasoning.encrypted_content"],
  "prompt_cache_key": "<lane/session cache key>"
}
```

`include: ["reasoning.encrypted_content"]` is present only when the selected
model and reasoning configuration can emit encrypted reasoning. Non-reasoning
requests omit it. For strict function tools, every property in `properties`
must appear in `required` and `additionalProperties` must be `false`; otherwise
the lowering layer must set `strict=false` and record the reason in the request
descriptor. Phase 2 must add offline schema validation for every lowered tool.

Tool-call output for a JSON function tool:

```json
{
  "type": "function_call_output",
  "call_id": "call_...",
  "output": "read_file result: completed; path=src/example.py; output_refs=..."
}
```

Tool-call output for a custom/freeform tool:

```json
{
  "type": "custom_tool_call_output",
  "call_id": "call_...",
  "name": "apply_patch",
  "output": "apply_patch result: completed; changed_paths=src/example.py; evidence_refs=..."
}
```

Use function tools for structured JSON arguments:

- `inspect_dir`
- `read_file`
- `search_text`
- `glob`
- `git_status`
- `git_diff`
- `run_command`
- `run_tests`
- `poll_command`
- `cancel_command`
- `read_command_output`
- `write_file`
- `edit_file`
- `finish`

Use a custom/freeform tool for `apply_patch` on models that support it. The
grammar-backed custom tool is the desired main path. A JSON `apply_patch` tool
may exist only as an explicit provider capability fallback, not as the default
design.

`previous_response_id` and server-side `store` are avoided in the first native
v2 implementation:

- `store=false` keeps correctness anchored in mew's local transcript and
  matches the current local privacy posture.
- `previous_response_id` is not needed for correctness because each request is
  constructed from the locally persisted transcript window plus sidecar digests.
- Avoiding `previous_response_id` makes replay deterministic, avoids hidden
  server conversation state, and lets saved artifacts reconstruct the exact
  model input.
- If reasoning models require retained reasoning context while `store=false`,
  persist provider-returned encrypted reasoning items in `reasoning_sidecar.json`
  and include the provider-required encrypted reasoning items in the next
  request according to the provider's documented stateless flow.
- A later optimization may add `previous_response_id` for transport efficiency
  only after replay proves byte-equivalent local transcript reconstruction. It
  cannot become the source of truth.

This intentionally diverges from Codex-style server-state optimization. The
tradeoff is that mew pays more local transcript-window construction cost in
exchange for deterministic replay and local proof authority. Request descriptors
must make this divergence auditable by recording `store`,
`previous_response_id`, transcript window hash, sidecar digest hash,
reasoning sidecar refs used, and whether a request used local stateless
reasoning carry-forward.

### Reasoning Sidecar

`reasoning_sidecar.json` stores encrypted reasoning material separately from
the transcript:

```text
reasoning_sidecar.json
  schema_version
  lane_attempt_id
  provider
  items[]
    ref
    response_id
    provider_item_id
    turn_id
    encrypted_content_sha256
    encrypted_content_bytes
    include_in_next_request
```

The sidecar is not evidence and not model-facing prose. It exists only to
support stateless provider continuation when `store=false`. Replay validates
that transcript items reference existing sidecar entries, that hash metadata
matches, and that request descriptors cite the sidecar refs re-included in each
future request.

## Runtime Ownership Boundaries

### Provider Adapter

The provider adapter owns wire translation:

- lower `ImplementLaneToolSpec` to provider tool specs;
- send Responses requests and consume streaming events;
- accumulate `function_call` argument deltas by `output_index`;
- normalize `ResponseItem::FunctionCall` and `ResponseItem::CustomToolCall`;
- build `function_call_output` and `custom_tool_call_output` input items;
- record provider ids, request ids, response ids, usage, and latency.

The adapter must not execute tools, decide finish acceptance, derive WorkFrame,
or hide provider items from the transcript.

Streaming event inventory:

| Provider event family | Native transcript handling |
|---|---|
| `response.created` | Start response-turn metadata with response id and request descriptor ref. |
| `response.output_item.added` | Reserve item slot by output index and provider item id. |
| `response.output_item.done` | Finalize assistant, reasoning, function call, custom call, web/search, or other item. |
| `response.content_part.added` / `response.content_part.done` | Attach message content-part metadata and bounded refs. |
| `response.output_text.delta` / `response.output_text.done` | Accumulate assistant text content only; never parse as control. |
| `response.function_call_arguments.delta` / `response.function_call_arguments.done` | Accumulate raw JSON argument text for the matching function-call item. |
| `response.custom_tool_call_input.delta` / done-equivalent event | Accumulate freeform custom input text for the matching custom tool-call item. |
| `response.completed` | Seal response-turn metadata, usage, and final output item count. |
| `response.failed` | Record provider failure and block before any unpaired side effect. |
| `response.incomplete` | Record incomplete reason; pair only fully emitted calls, then block or continue by deterministic policy. |
| usage/metadata events | Record safe usage, latency, request id, response id, and provider metadata refs. |

If the provider adds unknown events, the adapter records them in
`provider_events.jsonl` and fails closed unless they are explicitly marked
observability-only.

### Transcript Runtime

The native runtime owns loop control:

- build the initial transcript from task input and static instructions;
- select transcript window and sidecar digests for each provider request;
- append provider output items to the transcript;
- dispatch tool calls to the shared tool harness;
- append paired output items;
- stop only on accepted finish, fatal provider error, replay-invalid state,
  wall budget, turn budget, or deterministic blocked condition.

Same-response dispatch ordering:

- Provider output items are ordered by provider `output_index`, then stream
  sequence, then local transcript sequence.
- Non-tool items in the same response, such as assistant messages and reasoning
  items, are appended to the authoritative transcript in provider output order.
  They require no execution and no paired output item.
- Pure read tools may execute concurrently when their schemas validate and
  there is no earlier unpaired write, finish, approval, or provider error.
- Execute tools may run concurrently only when the tool policy marks the call
  non-mutating and no earlier same-response write or finish is pending.
- Write tools, `apply_patch`, approval-sensitive calls, and any call whose
  mutability is unknown execute serially in provider output order.
- Paired output items are appended to the transcript in stable provider output
  order, even if safe reads complete out of order.
- `finish` is evaluated only after all earlier sibling calls have paired
  outputs. Earlier assistant or reasoning siblings are context only and do not
  block finish; they have already been appended as transcript items. Later
  executable siblings are not dispatched until finish is resolved.
- If finish is accepted, later sibling calls receive paired synthetic-error
  outputs with their original `call_id`, `status="synthetic_error"`, and reason
  `cancelled_after_accepted_finish`; the lane then completes.
- If finish is blocked, its paired output is appended and later siblings remain
  undispatched for the next provider turn unless deterministic policy says they
  are still safe to execute.

The runtime treats parse failures differently from model JSON:

- malformed function-call arguments become paired tool outputs explaining the
  schema error;
- unavailable tools become paired synthetic error outputs;
- provider streaming interruption becomes a turn-level provider error with no
  unpaired side effects;
- patch grammar failures become `apply_patch` output, not a model-response JSON
  parse error.

### Tool Harness

The existing tool kernel remains valuable. The redesign should keep one shared
harness for read, write, exec, poll, cancel, output reads, and finish.

The harness owns:

- argument validation;
- approval and write gates;
- managed exec lifecycle;
- command closeout and orphan cleanup;
- bounded natural result text;
- output refs and evidence refs;
- source mutation provenance;
- exactly one transcript output per call.

The harness must be provider-agnostic. It receives normalized native calls and
returns `ToolResultEnvelope` plus a provider-output item.

### Updated Lane State

`updated_lane_state` is a derived runtime output, not a WorkFrame/todo control
protocol. The native runtime emits it from the authoritative transcript plus
evidence, verifier, and WorkFrame sidecars after the turn is complete.

Allowed fields are compatibility state that existing `commands.py` consumers
need, such as `lane_attempt_id`, finish status, proof manifest refs, artifact
paths, and derived `active_work_todo` readiness summaries. Any emitted
`active_work_todo` or frontier-like value must cite transcript/evidence refs and
must be rebuildable from artifacts. Phase 4 must prove the native
`updated_lane_state` round-trips through
`_merge_work_session_active_work_todo_readiness` without changing that command
integration schema.

### Acceptance And Finish

`finish` becomes a native tool. Its arguments are:

```json
{
  "outcome": "completed | blocked | failed",
  "summary": "short stop reason",
  "evidence_refs": [{"kind": "evidence_event", "id": "ev:..."}]
}
```

The model supplies evidence refs only. Typed acceptance may resolve those refs
against typed obligations or verifier facts in sidecars, but the finish schema
does not expose a second task-specific acceptance channel.

The finish handler runs typed acceptance first when typed session data exists,
then legacy safety asserts while they remain in migration. Outcomes:

- `allow_complete`: append `finish_output` with acceptance summary and complete
  the lane.
- `block_continue`: append `finish_output` with blockers and continue if budget
  remains.
- `failed` or replay invalid: append output, stop blocked/failed.

The model cannot complete by emitting final prose without a finish tool call.
Assistant text without tool calls and without finish is a blocked or continue
condition, depending on budget and provider stop reason.

Assistant or reasoning items that appear in the same provider response as a
finish call remain transcript context only. They do not require paired outputs
and do not delay finish evaluation beyond the requirement that earlier
executable tool-call siblings are paired.

## WorkFrame, Evidence, Frontier, And Todo

WorkFrame, typed evidence, frontier state, and active todo may remain, but only
as sidecars/analyzers/projections derived from the transcript and tool result
sidecars.

Allowed roles:

- WorkFrame debug bundle generated from transcript and evidence indexes.
- Compact WorkFrame or navigation card in the prompt when it summarizes current
  safety constraints, searchable refs, or verifier freshness.
- Evidence sidecar generated from tool outputs.
- Frontier-like recovery card generated for compaction, resume, or blocked
  finish.
- Debug-only model-turn index for plateau/replay analysis.

Disallowed roles:

- WorkFrame as the primary model-facing control protocol.
- Model-authored `frontier_state_update`.
- A second ordinary model-visible todo/proof/frontier object beside the native
  transcript and compact sidecar digest.
- Variant-specific tool execution, evidence schemas, replay semantics, or
  benchmark behavior.

This differs from the current WorkFrame polish path. WorkFrame polish keeps
repairing what the model sees because the model does not have a natural native
tool transcript. The native rebuild gives the model the actual latest
call/result pair in provider-native form. That reduces the need for
`required_next`, frontier, todo, and evidence objects to compensate for stale or
over-projected history. The transcript carries short-horizon action authority;
sidecars gate safety and explain decisions.

## Observability Contract

Do not lose current observability. The native runtime should preserve or
improve these artifacts and metrics.

### Artifacts

Keep or replace:

| Current artifact | Native replacement |
|---|---|
| `history.json` | `response_transcript.json` and `response_items.jsonl`; optional derived `history.json` during transition |
| `transcript.json` | native transcript items with provider ids and normalized item kinds |
| `natural_transcript.jsonl` | derived natural transcript from call/output pairs |
| `proof-manifest.json` | keep filename, regenerate from native transcript and sidecars |
| `tool_registry.json` | keep, now provider-native schema lowering is included |
| `tool_policy_index.json` | keep |
| `tool_results.jsonl` | keep, emitted from paired output items |
| `tool_result_index.json` | keep, keyed by `call_id` and local tool refs |
| `evidence_sidecar.json` | keep, generated from tool outputs |
| `evidence_ref_index.json` | keep |
| `model_turn_index.json` | keep as debug/recovery index only |
| `integration-observation.json` | replace with `native-turn-observation.json` or bump schema |
| `workframes/turn-*/...` | keep as derived debug bundle |

New recommended artifacts:

```text
implement_v2/
  response_transcript.json
  response_items.jsonl
  transcript_window.jsonl
  request_descriptor.json
  provider_requests.jsonl
  provider_events.jsonl
  reasoning_sidecar.json
  native_turn_observation.json
  call_result_pairing.json
  transcript_metrics.json
```

`provider_requests.jsonl` stores bounded request descriptors, not raw secrets.
It should include request hashes, tool spec hash, transcript window hash,
sidecar digest hash, `store`, `previous_response_id`, stream mode, and provider
headers that are safe to expose.

### Pairing

Pairing validation becomes stricter:

- every native call item has one output item;
- no output item exists without a known prior call, except quarantined imported
  reference traces;
- the same `call_id` cannot be reused for two side-effecting calls;
- a failed validation produces a proof manifest failure and no completion
  credit;
- pairing is checked in replay, dogfood, emulator, tool-lab, and fastcheck.
- synthetic validation, schema, permission, unknown-tool, cancellation, and
  accepted-finish sibling errors are still paired output items with the original
  provider `call_id`.

### Metrics

Preserve current metrics and add native ones:

- model turn count;
- model elapsed seconds per turn and total;
- provider request latency, stream first-event latency, stream completion
  latency;
- response id, request id, output item count, item type counts;
- tool call count and tool result count;
- per-tool latency: queued, started, first output, finished;
- first-write latency in turns and wall seconds;
- first verifier latency in turns and wall seconds;
- command closeout count, auto-poll count, cleanup count;
- prompt/input item bytes, transcript window bytes, provider-visible tool
  output bytes;
- token usage when provider returns it;
- step-shape metrics: probe count, edit count, verifier count, same-family
  repeat count, model turns per 10 minutes, prompt/input bytes per turn;
- finish gate block count and typed acceptance decision;
- WorkFrame input/output hashes and invariant status as derived metrics.
- `transport_kind`, with values such as `provider_native`,
  `legacy_model_json`, `fake_native`, and `imported_trace`;
- `provider_native_tool_loop`, required true for native v2 completion credit;
- `model_json_main_path_detected`, computed from runtime id, provider id,
  command progress phase names, prompt contract hashes, request descriptors,
  and imported symbols;
- native event counts: provider requests, provider events, output items,
  function calls, custom calls, paired outputs, orphan outputs, duplicate ids,
  blocked finishes, accepted finishes, and transcript replay failures.

## Reference Trace Normalization

The transcript schema must normalize both native mew traces and reference CLI
traces.

Codex normalization:

- `ResponseItem::Message` -> `assistant_message` or `input_message`;
- `ResponseItem::Reasoning` -> `reasoning`;
- `ResponseItem::FunctionCall` -> `function_call`;
- `ResponseItem::CustomToolCall` -> `custom_tool_call`;
- `ResponseItem::FunctionCallOutput` -> `function_call_output`;
- `ResponseItem::CustomToolCallOutput` -> `custom_tool_call_output`;
- `call_id`, `name`, `arguments`, `input`, and output payloads are preserved.

Claude normalization:

- `tool_use` -> native call item with provider namespace `claude`;
- `tool_result` -> paired output item;
- Claude message ids and content block ids map to provider ids;
- normalized `call_id` is the tool-use id;
- raw content blocks are kept behind refs when large.

The normalizer should output the same native transcript schema so step-shape
comparisons can compare mew, Codex, and Claude on tool order, first edit,
verifier cadence, output visibility, and pair validity without pretending the
providers have identical wire formats.

## Files Likely Touched

Primary runtime and provider:

- `src/mew/implement_lane/registry.py`
- `src/mew/implement_lane/provider.py`
- `src/mew/implement_lane/v2_runtime.py`
- new `src/mew/implement_lane/native_runtime.py`
- new `src/mew/implement_lane/native_provider.py`
- new `src/mew/implement_lane/native_transcript.py`
- `src/mew/implement_lane/transcript.py`
- `src/mew/implement_lane/types.py`
- `src/mew/codex_api.py`
- `src/mew/model_backends.py`
- `src/mew/commands.py`

Tool schema and harness:

- `src/mew/implement_lane/tool_policy.py`
- `src/mew/implement_lane/tool_harness_contract.py`
- `src/mew/tool_kernel.py`
- `src/mew/implement_lane/read_runtime.py`
- `src/mew/implement_lane/write_runtime.py`
- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/replay.py`

Sidecars, WorkFrame, and validation:

- `src/mew/implement_lane/prompt.py`
- `src/mew/implement_lane/workframe.py`
- `src/mew/implement_lane/workframe_variants.py`
- `src/mew/implement_lane/hot_path_fastcheck.py`
- `src/mew/implement_lane/tool_lab.py`
- `src/mew/dogfood.py`
- `src/mew/terminal_bench_replay.py`
- reference-trace normalization modules if present or new.

Tests and fixtures:

- `tests/test_implement_lane.py`
- `tests/test_acceptance.py`
- `tests/test_dogfood.py`
- `tests/test_codex_api.py` or equivalent new provider tests
- fixtures under `tests/fixtures/implement_v2/`

Documentation:

- this design;
- follow-up implementation phase notes;
- updated artifact contract docs once Phase 1 lands.

## Artifacts Preserved, Changed, And Deleted

Preserved:

- `proof-manifest.json` as the main proof entry point;
- tool registry, policy index, result index, evidence sidecar, evidence ref
  index, model-turn index, natural transcript, WorkFrame debug bundles;
- replay, tool-lab, dogfood, emulator, fastcheck, and Terminal-Bench artifact
  roots.

Changed:

- `history.json` is derived, not authoritative;
- provider-visible history projection is replaced by `transcript_window.jsonl`,
  a derived provider input window rebuilt from the authoritative transcript
  plus sidecars;
- `request_descriptor.json` records the exact native request shape, hashes,
  `store`, `previous_response_id`, reasoning sidecar refs, and provider
  capability decisions for each turn;
- model-turn observations become native response-turn observations;
- proof manifest metrics use `runtime_id="implement_v2_native_transcript_loop"`
  plus `provider_native_tool_loop=true`,
  `transport_kind="provider_native"`, and
  `model_json_main_path_detected=false`;
- tool ids are provider `call_id` first, with local ids as secondary refs;
- WorkFrame bundles cite transcript and evidence sidecar hashes, not old prompt
  projection refs.

Deleted or quarantined after gates pass:

- `run_live_json_implement_v2` as the live path;
- `JsonModelProviderAdapter` as a production adapter;
- `_live_json_prompt`, `_normalize_live_json_payload`, model JSON parse retry,
  and model-authored `frontier_state_update` handling;
- `implement_v2_model_json_tool_loop` runtime selection;
- production hardcoded `implement_v2_model_json_tool_loop` literals in
  `commands.py`, `dogfood.py`, replay scripts, proof readers, progress
  summaries, and runtime metrics;
- `history_json` response contract instructions in the model prompt.

## Phase Plan

Each phase should be reviewed and committed separately. A phase is not closed by
partial code plus a promise to test later.

Each phase review must state whether the phase changed runtime transport.
`transport_change=no` phases may be necessary scaffolding, but they do not count
as native-loop progress. A phase may count as native-loop progress only when its
close gates prove provider-native request lowering, native response item
parsing, transcript authority, paired output construction, runtime selection,
or native validation behavior.

### Phase 0: Freeze Baseline And Artifact Contract

Implementation:

- Add no runtime behavior yet.
- Mark the phase `transport_change=no`; it is artifact and gate preparation,
  not native-loop progress.
- Record the exact current model-JSON artifact and metrics contract.
- Add the native artifact contract document or schema fixture.
- Add expected new runtime id:
  `implement_v2_native_transcript_loop`.
- Add the anti-drift checklist to roadmap/status tracking: runtime identity,
  static model-JSON rejects, transcript authority, sidecar boundaries,
  transport metrics, and deletion/quarantine scope.

Close gates:

- `git status` shows only design/schema/test fixture changes intended for the
  phase.
- Current model-JSON replay/fastcheck still passes.
- Review accepts the artifact migration table and no-compat deletion list.
- Review explicitly agrees that WorkFrame, frontier, parse repair, prompt
  projection, or observability-only changes are sidecar work unless paired with
  transport-changing native gates.

Commit after review.

### Phase 1: Typed Native Transcript Schema And Replay

Implementation:

- Mark the phase `transport_change=partial`: native transcript authority and
  replay are added, but no live provider transport is selected.
- Add transcript dataclasses and JSON/JSONL writers.
- Add native pairing validator.
- Add import normalizers for Codex ResponseItems and Claude tool-use/tool-result
  traces.
- Add fake native provider fixtures for function calls, custom calls, outputs,
  duplicate ids, missing outputs, and finish calls.
- Add transcript hashing rules that include item metadata, sidecar refs, and
  encrypted-reasoning hashes but exclude encrypted blob bytes.
- Add paired synthetic-error output fixtures for schema failures, unknown
  tools, denied calls, duplicate ids, accepted-finish sibling cancellation, and
  interrupted streams.
- Do not call a live model.

Close gates:

- Unit tests prove call/output pairing, duplicate rejection, orphan quarantine,
  transcript hash stability, and derived proof manifest generation.
- Synthetic errors are serialized as paired function/custom output items with
  the original `call_id`, never as a separate transcript kind.
- Saved Codex and Claude traces normalize into the same transcript schema.
- Existing WorkFrame/debug bundle can be regenerated from transcript-derived
  sidecar events.
- Native transcript authority gate passes: deleting derived history,
  WorkFrame, turn index, and evidence sidecars from a fixture copy and
  regenerating them from `response_transcript.json` / `response_items.jsonl`
  yields stable hashes.

Commit after review.

### Phase 2: Tool Schema Lowering And Codex Native Adapter

Implementation:

- Mark the phase `transport_change=yes`: the provider adapter must emit native
  Responses requests and parse native streamed response items.
- Lower `ImplementLaneToolSpec` to provider-native Responses tool specs.
- Add strict JSON schemas for structured tools.
- Add custom/freeform `apply_patch` grammar tool where supported.
- Add request descriptor artifacts with `store=false` and no
  `previous_response_id`.
- Add `include: ["reasoning.encrypted_content"]` when the selected model uses
  reasoning and the provider supports encrypted reasoning.
- Add `reasoning_sidecar.json` persistence and request-descriptor refs for
  encrypted reasoning carry-forward.
- Add streaming parser coverage for `response.created`,
  `response.output_item.added`, `response.output_item.done`,
  `response.content_part.added`, `response.content_part.done`,
  `response.output_text.delta`, `response.output_text.done`,
  `response.function_call_arguments.delta`,
  `response.function_call_arguments.done`, custom tool input deltas/done
  equivalents, `response.completed`, `response.failed`,
  `response.incomplete`, usage, and metadata events.
- Do not execute side-effecting tools against a live model in this phase.

Close gates:

- Golden tests for tool schema JSON, including offline validation that strict
  schemas require every property and reject additional properties, or else are
  deliberately lowered with `strict=false` and a recorded reason.
- Golden tests for streamed function-call accumulation.
- Golden tests for function and custom tool output input items.
- Request descriptor proves `store=false`, no `previous_response_id`, and stable
  tool spec hashes.
- Request descriptor records `store`, `previous_response_id`, transcript window
  hash, sidecar digest hash, reasoning sidecar refs used, stream mode, provider
  request id, safe headers, tool spec hash, and provider-native capability
  decisions.
- Reasoning sidecar round-trip proves transcript refs resolve to sidecar
  entries, encrypted blob hashes match, encrypted blob bytes are excluded from
  transcript hashes, and carried-forward refs appear in the next descriptor.
- A model-text non-control fixture emits assistant text containing a complete
  JSON object with `tool_calls` and `finish`; the adapter records it as text and
  produces no control action from it.

Commit after review.

### Phase 3: Native Tool Harness Loop With Fake Provider

Implementation:

- Mark the phase `transport_change=yes`: fake provider items must enter the
  same native transcript and paired-output path the live adapter will use.
- Add `run_native_implement_v2` or equivalent native runtime entry point.
- Feed fake provider native calls through the real tool harness.
- Execute read, exec, write, apply_patch, poll/cancel, read output, and finish
  in controlled fixtures.
- Implement deterministic same-response dispatch ordering: safe reads may run
  concurrently, writes and unknown-mutability calls serialize by provider
  `output_index`, paired outputs append in provider order, and finish waits for
  all earlier sibling outputs.
- Emit native transcript artifacts and proof manifest from the fake runs.

Close gates:

- Read-only, exec, write, and finish fixtures pass.
- Invalid arguments produce paired tool outputs.
- Side-effecting calls are blocked before execution when ids or approvals are
  invalid.
- Finish-with-siblings fixtures prove accepted finish cancels later siblings by
  paired synthetic-error outputs and blocked finish appends a paired output
  without completing.
- Finish-with-non-tool-siblings fixtures prove assistant/reasoning items are
  appended in provider order as transcript context, require no pairing, and do
  not block finish evaluation.
- Tool latency and first-write latency metrics are present.
- Replay validates the native proof manifest.

Commit after review.

### Phase 4: Sidecars And WorkFrame As Derived Projections

Implementation:

- Mark the phase `transport_change=sidecar-only`: this phase may change compact
  provider context, but it does not count as native-loop progress unless Phases
  2 and 3 native transport gates are already green.
- Convert evidence sidecar, tool result index, evidence ref index, model turn
  index, and WorkFrame debug bundle generation to consume native transcript.
- Keep WorkFrame variants only as projection/policy analyzers.
- Remove model-authored frontier/todo/proof fields from the native prompt.
- Add compact sidecar digest input to provider requests.
- Emit `updated_lane_state` as a derived runtime output from transcript,
  evidence, verifier, and WorkFrame sidecars.

Close gates:

- WorkFrame replay tests pass from transcript input.
- Prompt/input inventory shows no ordinary model-visible frontier, todo, proof,
  or evidence object beside transcript window plus compact sidecar digest.
- WorkFrame bundle files are still emitted with stable input/output hashes.
- Typed acceptance and finish gate tests pass.
- Native `updated_lane_state` round-trips through
  `_merge_work_session_active_work_todo_readiness` without command integration
  schema changes.
- Deleting WorkFrame, model-turn index, derived history, and evidence sidecar
  artifacts from a fixture copy and regenerating them from the authoritative
  native transcript produces stable derived hashes.

Commit after review.

### Phase 5: CLI Integration And Model-JSON Quarantine

Implementation:

- Mark the phase `transport_change=yes`: selected production v2 must route to
  the native runtime, not the model-JSON runtime.
- Change registry v2 runtime to
  `runtime_id="implement_v2_native_transcript_loop"` and
  derived `provider_native_tool_loop=True` from native capability checks.
- Wire `commands.py` selected-lane path to the native runtime.
- Update progress phases from `model_json_*` to native response phases.
- Replace production hardcoded `implement_v2_model_json_tool_loop` literals in
  `commands.py`, `dogfood.py`, replay scripts, proof readers, progress
  summaries, and runtime metrics.
- Quarantine model-JSON runtime under explicit test-only names or delete it if
  no longer needed by tests.
- Update metrics, proof summary, tool-lab, and dogfood readers for native
  artifacts, including `transport_kind` and
  `model_json_main_path_detected`.

Close gates:

- Unit tests that select v2 observe native runtime id and
  `provider_native_tool_loop=true`.
- No production command path references
  `implement_v2_model_json_tool_loop`.
- Static drift gate rejects production v2 imports, prompt strings, command
  integration, and runtime metrics containing `JsonModelProviderAdapter`,
  `run_live_json_implement_v2`, `_live_json_prompt`,
  `_normalize_live_json_payload`, `call_codex_json`,
  `call_model_json_with_retries`, `history_json:` transport sections, or a
  JSON response contract with `tool_calls`, `finish`, or
  `frontier_state_update`.
- Static grep test proves old runtime ids and `model_json` symbols are absent
  from production v2 paths, with an allowlist only for docs, legacy fixtures,
  and explicit quarantine tests.
- Model-JSON-specific parser retry and `frontier_state_update` rejection are
  unreachable from native v2.
- Proof manifest, command progress, dogfood, replay, and metrics agree on
  `runtime_id="implement_v2_native_transcript_loop"`,
  `transport_kind="provider_native"`,
  `provider_native_tool_loop=true`, and
  `model_json_main_path_detected=false`.
- Existing v1 behavior is unchanged.

Commit after review.

### Phase 6: Validation Gates Before Live Speed Proof

Implementation:

- Mark the phase `transport_change=validation`: it validates the selected
  native runtime and must not count legacy model-JSON or projection-only runs as
  native speed/proof evidence.
- Run saved replay gates.
- Run dogfood and emulator gates against native artifacts.
- Run the native HOT_PATH fastcheck against the latest current-head native
  artifact. The fastcheck must accept native transcript artifacts without
  `history.json`, validate transcript/response-items/manifest consistency, and
  replay native loop-control state.
- Run micro next-action gates only for legacy WorkFrame/history artifacts or
  explicitly designed native micro fixtures. Native transcript mode must not
  recreate `history.json` only to satisfy old micro checks.
- Run one 10 minute step-shape diagnostic before any speed proof.
- Compare reference trace normalized shape against Codex and Claude.

Close gates:

- Replay: native transcript pairing valid, write safety valid, typed evidence
  refs valid, WorkFrame derived hashes stable.
- Dogfood: native artifact bundle is accepted by existing reports or explicit
  native replacements.
- Emulator: blocked finish receives a paired output and continues; accepted
  finish completes with proof.
- Micro next-action: latest native tool result maps to the intended next inspect,
  patch, verifier, or blocked action without requiring old frontier/todo state.
- Native fastcheck: `scripts/check_implement_v2_hot_path.py` passes on the
  latest native artifact and reports `history_path=""`, `transcript_path`,
  `native_manifest_contract`, `native_pairing`,
  `native_response_items_match`, `native_trace_summary`, and
  `native_loop_control_replay`. If a completed `search_text` reports positive
  matches, `native_search_text_anchor_projection` must confirm that the model
  saw compact `path:line` anchors rather than only match counts plus refs.
- Native closeout: if a latest source mutation has no later terminal configured
  verifier, the native loop runs one deterministic configured final verifier at
  closeout. A passing closeout may complete without another model turn; a
  failing closeout downgrades even a previously completed finish; a verifier
  that yielded and later completed through `poll_command` counts as the later
  verifier and must not trigger duplicate closeout.
- 10 minute step shape: parse error count is zero, no model-JSON failures exist,
  first write latency is recorded, verifier count and same-family repeats are
  bounded by the phase's declared thresholds, and no unpaired tool calls appear.
- Native-loop gate is green before any speed proof starts: CLI-selected v2 uses
  native runtime, native transcript artifacts are emitted, no production
  model-JSON imports are reachable, pairing replay is valid, and observability
  artifacts are present or replaced by native equivalents.
- Metrics used for proof or speed exclude `legacy_model_json` transport and
  reject `model_json_main_path_detected=true`.
- Reference normalization: Codex/Claude/mew comparison report can compute first
  tool, first edit, commands, edits, verifiers, messages/model turns, and
  tool-output visibility from normalized transcripts.

Commit after review.

### Phase 7: Delete Old Main Path

Implementation:

- Mark the phase `transport_change=yes`: after this phase native transcript v2
  is the only production v2 main path.
- Delete or quarantine remaining model-JSON runtime code.
- Remove old model-JSON artifact writers if they are not needed for replay
  fixtures.
- Update docs and status files to name native transcript v2 as the only v2 main
  path.

Close gates:

- Full focused test suite passes.
- No production code imports `JsonModelProviderAdapter` or
  `run_live_json_implement_v2`.
- No production code imports or calls `_live_json_prompt`,
  `_normalize_live_json_payload`, `call_codex_json`,
  `call_model_json_with_retries`, model-JSON parser retry helpers, or
  model-authored `frontier_state_update` handlers from native v2.
- No production code contains hardcoded `implement_v2_model_json_tool_loop`
  literals, except explicit legacy fixture or quarantine-test allowlist entries.
- Old fixtures either migrate through a converter or are explicitly marked
  legacy model-JSON fixtures.
- Docs, roadmap status, registry, command progress, proof manifests, dogfood,
  replay, and metrics name native transcript v2 as the only v2 main path.

Commit after review.

## Risks

- Provider API drift: Responses tool and custom tool wire shapes can change.
  Mitigation: isolate provider lowering/parsing in one adapter and keep golden
  request/stream fixtures.
- Reasoning context loss with `store=false`: some models may need encrypted
  reasoning items carried forward. Mitigation: persist and replay reasoning
  items locally before enabling long native runs.
- Prompt growth from local transcript replay: resending transcript windows can
  grow. Mitigation: transcript windowing plus compact sidecar digests, measured
  in provider request descriptors.
- Parallel calls with write side effects: provider may emit multiple calls.
  Mitigation: allow parallel read/exec where safe; serialize or block unsafe
  write sequences through harness policy.
- Finish-as-tool semantics may need one provider turn less than normal
  call/output cycles. Mitigation: still append paired finish output locally; only
  skip sending it back when the deterministic gate accepts completion.
- Artifact reader churn: tool-lab, dogfood, and proof summary expect old paths.
  Mitigation: keep filenames where valuable and add native replacement readers
  before deleting old exports.
- Hidden coupling to WorkFrame variants: current tests may assume WorkFrame is
  the active control protocol. Mitigation: port tests to transcript-source
  fixtures and keep WorkFrame checks as derived invariant tests.
- False native success: an implementation could improve sidecars, prompt
  projection, or parser repair and report native progress without changing
  transport. Mitigation: phase reviews must record `transport_change`, and
  completion credit requires native runtime id, native request/response
  artifacts, static model-JSON rejects, and `transport_kind="provider_native"`.
- Strict schema mismatch: provider strict-schema rules can reject tools that
  local validation accepts. Mitigation: offline provider-shape validation,
  golden request fixtures, and deliberate `strict=false` lowering only when the
  descriptor records the reason.

## Rollback And De-Risk Path

No backward compatibility is required for old v2, but de-risking still matters.

- Phase commits are independently revertible.
- `implement_v1` remains the operator fallback lane.
- Native v2 should remain explicitly selected until Phase 6 passes.
- If Phase 5 integration fails, revert the registry/commands commit and keep
  the transcript/provider code as inactive scaffolding.
- If live native provider behavior is unstable, keep fake-provider and replay
  fixtures while fixing the provider adapter; do not revive model-JSON as the
  v2 main path.
- If artifact readers lag, temporarily emit derived compatibility exports from
  the native transcript. These exports are adapters, not runtime truth.

## Approval Target

Approve this redesign only if reviewers agree that:

- the native `ResponseItem` transcript is the source of truth;
- provider-native tool calls and paired outputs are the only v2 main runtime
  transport;
- WorkFrame/evidence/frontier/todo are derived sidecars or compact projections;
- observability is preserved or improved;
- anti-drift gates prevent model-JSON/projection work from being counted as
  native-loop progress;
- model-JSON can be deleted or quarantined after native gates close;
- each implementation phase has measurable close gates and review/commit
  boundaries.
