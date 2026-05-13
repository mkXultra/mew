# Design 2026-05-13 - M6.24 Codex-Like Native Hot Path

Status: design only.

Scope: `implement_v2` live hot path after the native transcript rebuild and
native responsibility-boundary work. This document defines the next redesign
target before implementation. It does not authorize code changes by itself.

This design supersedes the parts of the WorkFrame / hot-path collapse designs
that made `WorkFrame`, `required_next`, `first_write_due`, or
`prewrite_probe_plateau` provider-visible live control. Those concepts may
remain as diagnostics, replay artifacts, sidecar projections, or supervisor
signals, but they must not steer the ordinary live model loop.

## Inputs

Reference investigations:

- ACM pid `50764`, codex-ultra session
  `019e205e-67e6-7db1-ae3d-2dbf09a14aeb`.
- ACM pid `51231`, codex-ultra session
  `019e205f-5d17-7151-b0a1-01094b753163`.

Local design context:

- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`
- `docs/DESIGN_2026-05-13_M6_24_COMMAND_EDIT_BOUNDARY_REDESIGN.md`
- `docs/REVIEW_2026-05-11_IMPLEMENT_V2_NATIVE_LOOP_DRIFT_PREVENTION.md`

Current source surfaces:

- `src/mew/implement_lane/native_tool_harness.py`
- `src/mew/implement_lane/native_transcript.py`
- `src/mew/implement_lane/native_sidecar_projection.py`
- `src/mew/implement_lane/native_workframe_projection.py`
- `src/mew/implement_lane/tool_policy.py`
- `src/mew/implement_lane/write_runtime.py`
- `src/mew/implement_lane/tool_harness_contract.py`
- `src/mew/implement_lane/completion_resolver.py`
- `src/mew/terminal_bench_replay.py`

Reference source surfaces:

- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs`
- `references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/router.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/context.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs`

## Durable Decision

The target architecture is:

```text
mew implement_v2 =
  Codex-like live hot path
  + mew-specific durable sidecar proof
```

The live loop should be as close as possible to:

```text
model emits provider-native tool_call
  -> runtime executes tool
  -> tool_output is appended with the same call_id
  -> next provider request receives the native transcript window
  -> model chooses the next action
```

Codex does not appear to have a production equivalent of "hard task: after N
probes force write". The replacement is not a hidden readiness heuristic. The
replacement is a provider-native transcript loop with a compact, usable tool
surface and execution-time safety.

Mew should keep its stronger resident-agent capabilities:

- transcript artifacts;
- proof manifest;
- replay;
- typed evidence;
- WorkFrame/debug sidecars;
- observer detail;
- CompletionResolver;
- terminal-bench trace normalization.

But those capabilities must be downstream of the transcript, not a second
live control protocol that competes with the model.

## Problem

The current native runtime has much of the right substrate, but the live
provider-visible path still leaks controller-derived steering:

- `compact_sidecar_digest` can contain `workframe_projection`;
- the projection can expose loop signals such as `first_write_due`;
- `prewrite_probe_plateau` can reject probe calls and force a source mutation;
- `required_next` and related fields can become an action card under another
  name;
- hard-runtime threshold tuning can become the main repair loop.

This is the wrong direction. It can make individual benchmark runs better, but
it moves `implement_v2` away from the reason v2 was created: native tool
calling where the model sees prior tool results and selects the next action.

The redesign goal is to remove live steering pressure while preserving the
observability that makes mew different from Codex.

## Non-Goals

- No new provider-visible planning object.
- No new WorkFrame variant as a live action protocol.
- No live `next_action` / `required_next` / `first_write_due` replacement
  under a new name.
- No broad Terminal-Bench measurement before the local gates in this design.
- No weakening of write safety, command lifecycle safety, approvals, or finish
  acceptance.
- No deletion of sidecar proof, replay, typed evidence, WorkFrame debug, or
  observer detail.
- No backward compatibility with old model-JSON `implement_v2` behavior.

## Hot Path Contract

Production `implement_v2` provider-visible input is limited to:

1. stable task/system instructions;
2. provider-native transcript window;
3. compact factual tool-result digest.

The transcript is the source of truth. Sidecars are derived from transcript
items and tool side effects.

### Provider-Visible Allowed

Allowed in live provider input:

- native transcript items:
  - assistant text;
  - reasoning summaries when available;
  - provider-native tool calls;
  - paired tool outputs keyed by `call_id`;
- compact tool-result cards:
  - tool name;
  - status;
  - exit code or structured error code;
  - command/session id;
  - changed paths;
  - artifact refs;
  - bounded stdout/stderr tail;
  - concise human-readable output summary;
- safety constraints:
  - allowed roots;
  - write approval state;
  - active command lifecycle state;
  - finish evidence requirements.

Allowed only when factual and bounded:

- `compact_sidecar_digest` as a digest of transcript/tool-result facts.
- `WorkFrame`-derived fields only when they are facts or refs, not actions.
- `finish_readiness` when it describes missing evidence, not a next step.

### Provider-Visible Forbidden

Forbidden in ordinary live provider input:

- `next_action`;
- `next_action_policy`;
- ordinary repair `required_next`;
- `first_write_due`;
- `first_write_due_overrun`;
- `prewrite_probe_plateau`;
- `max_additional_probe_turns`;
- "perform source mutation now" style controller messages;
- full `WorkFrame` objects;
- full `persisted_lane_state`;
- old frontier/todo/proof JSON objects;
- full typed evidence objects;
- threshold values whose purpose is to steer model behavior;
- model-JSON response contracts such as top-level `tool_calls`, `finish`,
  `frontier_state_update`, or `history_json`.

Forbidden fields may still exist in:

- replay artifacts;
- observer detail;
- supervisor diagnostics;
- metrics;
- `mew context` summaries;
- `ROADMAP_STATUS.md` notes;
- sidecar JSON not sent to the provider.

## Internal Sidecar Contract

The internal sidecar system remains mandatory.

Keep:

- `response_transcript.json`;
- `response_items.jsonl`;
- `call_result_pairing.json`;
- `transcript_metrics.json`;
- `proof-manifest.json`;
- `tool_routes.jsonl`;
- provider request inventory;
- normalized trace;
- `mew-report.json`;
- typed evidence sidecars;
- resolver decisions;
- WorkFrame/debug bundles;
- terminal-bench replay artifacts.

Sidecars must satisfy:

- every sidecar cites transcript item ids or tool result refs;
- sidecars do not become provider input by default;
- replay can recompute sidecar-derived summaries from transcript plus tool
  artifacts;
- if provider-visible digest is generated, it is a lossy factual projection
  with hard byte/key caps;
- observer detail must make the live path inspectable without requiring a
  10 minute step-shape run for every bug.

## Tool Surface Contract

The live tool surface should make the right action natural.

Mutation tools:

- `apply_patch` is the primary source mutation path for multi-line source
  changes.
- `edit_file` / structured edit is acceptable for precise replacement or
  hunk-style edits.
- `write_file` is acceptable for small generated files or complete file
  creation, but should not be the natural path for large source rewrites in
  hard-runtime tasks.
- Shell-invoked `apply_patch` may be bridged only by an exact, narrow bridge
  that computes the same typed mutation evidence.

Execution tools:

- `run_command` / `run_tests` are process-runner routes.
- `poll_command`, `cancel_command`, and `read_command_output` are process
  lifecycle routes.
- Shell parsing is metadata only. It must not grow back into a source mutation
  classifier.

Read/probe tools:

- `read_file`, `search_text`, and command probes should return compact,
  directly useful evidence with refs.
- Tool output should make latest failure and relevant paths clear enough that
  the model can choose to patch without controller steering.

## Phase Plan

### Phase 0: Contract And Static Gates

Owner: main Codex only.

Purpose: freeze the provider-visible contract before parallel implementation.

Tasks:

- Add tests or static gates that production provider input does not contain:
  `next_action`, ordinary `required_next`, `first_write_due`,
  `prewrite_probe_plateau`, full `WorkFrame`, full persisted lane state,
  model-JSON response contracts, or `history_json`.
- Add a provider inventory gate that records exactly which dynamic sections
  were sent to the model.
- Add a digest shape gate for compact factual tool-result cards.
- Add a sidecar-only allowlist for diagnostic loop signals.
- Update M6.24 status to name this design as the active next action.

Close gate:

- focused unit tests for provider input inventory pass;
- static forbidden-field gate fails on a fixture containing steering fields;
- no implementation worker starts before this phase is committed.

### Phase 1A: Transcript/Input Collapse

Owner: `$orchestrate-build-review` controller A after Phase 0 is committed.

Write scope:

- `src/mew/implement_lane/native_tool_harness.py`
  - request/input construction only;
  - no tool runtime changes;
- `src/mew/implement_lane/native_sidecar_projection.py`
  - compact factual digest;
  - diagnostic fields moved to sidecar-only artifacts;
- `src/mew/implement_lane/native_workframe_projection.py`
  - provider-visible projection shrink;
  - WorkFrame remains derived sidecar/debug output;
- focused tests for provider input inventory and digest shape.

Do not edit:

- mutation runtime;
- write runtime;
- tool policy for mutation tools;
- completion resolver except for read-only adaptation.

Close gate:

- provider input contains native transcript window plus compact factual digest;
- forbidden live steering fields are absent;
- observer/detail artifacts still contain diagnostic fields for debugging;
- replay can still find transcript and sidecar hashes.

### Phase 1B: Tool Surface And Mutation Path

Owner: `$orchestrate-build-review` controller B after Phase 0 is committed.

Write scope:

- `src/mew/implement_lane/tool_policy.py`
  - task-aware but non-steering tool surface;
  - hard-runtime large-source tasks prefer patch/edit surface;
  - `write_file` availability is constrained structurally when appropriate;
- `src/mew/implement_lane/write_runtime.py`
  - mutation evidence output remains typed and concise;
- `src/mew/implement_lane/tool_harness_contract.py`
  - output contract updates for concise tool results;
- `src/mew/implement_lane/native_tool_schema.py`
  - if schema shape needs changing;
- focused tests for tool list and mutation output cards.

Do not edit:

- provider input builder;
- WorkFrame projection;
- native transcript schema;
- main harness loop wiring except through exported policy functions.

Close gate:

- `apply_patch` / edit tools are the natural source mutation path;
- hard-runtime surface no longer invites huge `write_file` source rewrites;
- tool outputs stay concise but carry refs needed by replay/finish resolver;
- no shell mutation classifier reappears.

### Phase 2: Main Integration

Owner: main Codex.

Purpose: integrate Lane A and Lane B without merging their responsibilities.

Tasks:

- wire Lane A input collapse and Lane B tool surface into the native harness;
- resolve file conflicts manually;
- preserve exactly one paired tool output per provider call id;
- ensure `CompletionResolver` remains the completion authority;
- ensure observer/detail and provider request inventory still emit artifacts.

Close gate:

- full focused unit set for native harness, tool policy, replay, and
  terminal-bench replay passes;
- integration reviewer confirms no provider-visible steering objects remain;
- no model-JSON path is selected for production `implement_v2`.

### Phase 3: Validation Before Speed

Owner: main Codex.

Validation order:

1. focused unit tests;
2. native fastcheck;
3. replay/dogfood/emulator where applicable;
4. one 10 minute step-shape diagnostic;
5. reference-step comparison;
6. speed proof only after the above is green or explicitly yellow with a
   documented non-hot-path reason.

Close gate:

- 10 minute diagnostic shows the model sees prior tool outputs naturally and
  does not require controller rejection to leave probe loops;
- if it fails, the failure is classified as one of:
  - bad tool output shape;
  - missing mutation affordance;
  - lost transcript evidence;
  - finish resolver issue;
  - model/tool capability limitation.
- broad measurement is blocked until the failure is not a provider-visible
  steering regression.

## Parallel Implementation Rules

Parallel implementation is allowed only after Phase 0 is committed.

Use `$orchestrate-build-review` controllers for parallel implementation
phases. The main Codex is not one of the Lane A/B builders; it only peeks,
checks ownership, and integrates results.

Required controller setup:

- Controller A receives only Lane A scope and file ownership.
- Controller B receives only Lane B scope and file ownership.
- Each controller must run its own build/review loop.
- Each controller must include codex-ultra review.
- Difficult contract changes may add claude-ultra review.
- Controllers must stop if they need files outside their ownership.

Main Codex responsibilities:

- Phase 0 implementation and commit;
- controller launch prompts;
- periodic `peek` to verify the controller is not drifting;
- final merge/integration;
- conflict resolution;
- final validation and commits.

Forbidden parallel pattern:

- two workers editing `native_tool_harness.py` in overlapping regions;
- a worker changing both provider input and mutation tool policy;
- a worker adding new live action protocol fields to "help" the model;
- a worker changing proof/replay artifacts without preserving transcript refs.

## Observability Requirements

No implementation phase may reduce observability.

Required artifacts after integration:

- provider request inventory including dynamic section names and hashes;
- native response transcript;
- response item jsonl;
- call/output pairing report;
- tool route decisions;
- tool result refs and output paths;
- compact digest hash and byte size;
- sidecar hashes;
- WorkFrame/debug projection as sidecar;
- typed evidence refs;
- resolver decision records;
- native replay result;
- terminal-bench normalized trace;
- first-write latency / probe count / verifier count metrics.

New observation needed:

- `provider_visible_forbidden_fields` report:
  - absent fields list;
  - any detected forbidden fields;
  - source section names;
  - pass/fail.
- `diagnostic_only_fields` report:
  - confirms `first_write_due`, `prewrite_probe_plateau`, and similar fields
    are stored only in sidecar/observer artifacts when present.

## Review Checklist

Reviewers should reject an implementation if any item is false:

- provider-native transcript remains the source of truth;
- live provider input is transcript window plus compact factual digest;
- ordinary `next_action` / `required_next` is not provider-visible;
- `first_write_due` and `prewrite_probe_plateau` are not live steering;
- WorkFrame is not a planner or action card;
- tool output is concise and model-usable;
- `apply_patch` / edit are first-class mutation paths;
- shell remains process execution plus metadata, not mutation inference;
- completion remains `finish_call` plus `CompletionResolver`;
- proof/replay/observer artifacts remain available;
- no model-JSON production path is revived.

## Redesign Trigger After This Work

Do not keep polishing threshold controls after this design lands. If the
10 minute diagnostic still fails after Phase 1A/1B/2, decide from evidence:

- If the model cannot see useful prior tool output, fix transcript/tool-output
  shape.
- If the model lacks a natural mutation affordance, fix tool surface.
- If sidecars are needed for debugging but not visible, improve observer and
  replay, not live steering.
- If the same failure repeats after two focused polish iterations, consider a
  smaller collapse redesign that removes provider-visible sidecar fields
  further. Do not add another frontier/action-card layer.

## Close Criteria

This design is implemented when:

1. Phase 0 static gates are committed.
2. Lane A and Lane B are implemented through isolated build/review workflows.
3. Main Codex integrates both lanes without ownership leakage.
4. Focused unit tests pass.
5. Native fastcheck passes.
6. Replay/dogfood/emulator checks pass for relevant saved artifacts.
7. One 10 minute step-shape diagnostic passes or produces only a documented
   non-hot-path issue.
8. Provider request inventory proves no live steering fields are sent.
9. Observer/detail artifacts prove the diagnostic fields are still available
   internally.
10. M6.24 may resume speed proof only after these gates are met.

