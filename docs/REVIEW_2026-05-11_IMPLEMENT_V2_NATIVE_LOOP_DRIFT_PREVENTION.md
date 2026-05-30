# Review 2026-05-11 - Implement V2 Native Loop Drift Prevention

Role: independent architecture reviewer.

Scope: prevent `implement_v2` from drifting away from provider-native
tool/function calling into model-JSON transport, prompt projections, or
WorkFrame-owned control.

Inputs reviewed:

- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
- `docs/DESIGN_2026-05-05_M6_23_2_IMPLEMENT_V2_NATIVE_TOOL_LOOP.md`
- `src/mew/implement_lane/registry.py`
- `src/mew/implement_lane/provider.py`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/codex_api.py`
- `src/mew/commands.py`

## Executive Finding

The primary architectural risk is not lack of implementation detail. The risk
is that `implement_v2` already has a plausible-looking tool loop that is not
provider-native. It asks the model to return a synthetic JSON object, projects
prior calls/results into `history_json`, normalizes model-authored
`tool_calls`, and labels the transport honestly as
`implement_v2_model_json_tool_loop`.

That path can keep improving forever while still missing the design goal. The
native rebuild should therefore be guarded by fail-closed invariants, negative
tests, progress metrics, and phase gates that make model-JSON impossible to
mistake for provider-native progress.

Recommended decision: approve the native transcript rebuild only if the project
adopts the anti-drift invariants below as close gates. Until those gates pass,
`implement_v2` evidence should be treated as model-JSON evidence, not native
tool-loop evidence.

## 1. Exact Previous Drift Mechanism

The drift mechanism was a sequence of individually reasonable substitutions:

1. Native tool-loop intent was registered as an explicit lane, but the actual
   runtime was made available with
   `runtime_id="implement_v2_model_json_tool_loop"`,
   `provider_native_tool_loop=False`, and `writes_allowed=True` in
   `src/mew/implement_lane/registry.py`.
2. The provider adapter boundary used `JsonModelProviderAdapter`, whose
   provider id is `model_json`, instead of an adapter that consumes native
   provider `ResponseItem` / `tool_use` / function-call items.
3. The live runtime called the existing model-JSON transport through
   `run_live_json_implement_v2`, `model_json_callable`, and `_call_model_turn`.
   The provider call returned assistant text, not native tool-call output
   items.
4. The prompt asked the model to "Return exactly one JSON object" with
   `summary`, `tool_calls`, and `finish`, plus a model-visible
   `history_json` projection.
5. `_normalize_live_json_payload` treated the model JSON as a transport
   protocol, accepting aliases such as `tools`, `calls`, and `action`, then
   converted those fields into provider-shaped local envelopes.
6. Runtime artifacts and command integration repeated the identity:
   `commands.py` records `implement_v2_model_json_tool_loop`, watches
   `model_json_*` progress phases, and calls `run_live_json_implement_v2`.
7. Observability then accumulated around the projection path:
   `history.json`, `history_projection`, hot-path projection metrics,
   WorkFrame bundles, frontier cards, prompt history compaction, parse repair,
   and `frontier_state_update` rejection.

This was not a single bug. It was architecture drift by compatibility pressure:
the system wanted native call/result pairing, but the available model call
surface only returned text. The runtime compensated by inventing a model-facing
JSON protocol and then building enough projection, repair, and observability
around it that it began to look like a native tool loop.

The exact forbidden pattern is:

```text
provider text response
  -> parse one model-authored JSON object
  -> normalize JSON fields into local tool-call envelopes
  -> execute tools
  -> serialize compacted tool results into prompt history_json
  -> ask for another JSON object
```

The required native pattern is:

```text
provider native response items
  -> append native assistant/reasoning/tool-call items to local transcript
  -> execute each provider call_id through the harness
  -> append exactly one native paired output item per call_id
  -> construct next provider input from transcript window plus compact sidecars
```

## 2. Anti-Drift Mechanisms

### Code

- Make the runtime id a hard contract:
  `implement_v2_native_transcript_loop` is the only production v2 runtime id
  after CLI integration. Any production v2 path that emits
  `implement_v2_model_json_tool_loop` fails tests.
- Split production native runtime modules from legacy model-JSON modules.
  If legacy replay support remains, it should live behind names containing
  `legacy_model_json` or `test_model_json`, not generic provider/runtime names.
- Remove `JsonModelProviderAdapter` from production imports. A static test
  should reject production imports of `JsonModelProviderAdapter`,
  `run_live_json_implement_v2`, `_live_json_prompt`,
  `_normalize_live_json_payload`, and `call_codex_json` from the v2 command
  path.
- Require provider adapters to expose native item capabilities, not just text:
  `supports_native_tool_calls=True`, tool spec lowering, streamed item parsing,
  function/custom call extraction, tool output item construction, request
  descriptors, and usage/event metadata.
- Make `provider_native_tool_loop` derived from runtime capability checks, not
  a manually set badge. The value should be true only when the selected runtime
  has native request lowering, native response item parsing, native transcript
  persistence, and paired output construction enabled.
- Fail closed when a provider lacks native tool support. Do not silently
  substitute model-JSON. Return `LaneResult.status=unavailable|blocked` with
  `fallback_lane=implement_v1`.
- Make `NativeTranscript` the input to proof, replay, tool result index,
  evidence sidecar, model turn index, WorkFrame debug bundle, and metrics.
  Sidecars may depend on the transcript; the transcript must not depend on
  sidecars.
- Treat `finish` as a native tool item. Completion by ordinary assistant prose
  or top-level JSON field should be impossible in native v2.

### Docs

- Put a short "Transport Non-Negotiables" section in the native design and
  implementation PR template:
  provider-native calls, native paired outputs, local native transcript source
  of truth, no model-JSON main path, no WorkFrame-owned control protocol.
- Keep a deletion/quarantine list in the roadmap status until Phase 7 closes:
  `run_live_json_implement_v2`, `JsonModelProviderAdapter`,
  `_live_json_prompt`, `_normalize_live_json_payload`,
  model-JSON parse retry, `frontier_state_update` handling,
  `history_json` prompt contract, and `implement_v2_model_json_tool_loop`.
- Document sidecar roles with allowed and forbidden examples. This matters
  because WorkFrame and frontier concepts are useful enough that they will
  otherwise re-enter as ordinary model-facing control state.
- Every phase note should state whether it changed runtime transport. "No
  transport change" must not count as native-loop progress.

### Tests

- Add registry tests asserting explicit v2 selection reports
  `runtime_id="implement_v2_native_transcript_loop"` and
  `provider_native_tool_loop is True` after Phase 5.
- Add static production-path tests rejecting model-JSON symbols in native v2:
  no `JsonModelProviderAdapter`, no `run_live_json_implement_v2`, no
  `call_codex_json`, no `_live_json_prompt`, no `history_json:` prompt section,
  no `frontier_state_update` response contract.
- Add golden request tests proving native Responses requests include `tools`,
  `tool_choice`, `stream`, `store=false`, no hidden `previous_response_id` in
  Phase 2, and stable tool spec/request/window/sidecar hashes.
- Add streamed response tests for function-call argument deltas, custom tool
  calls, output item completion, provider errors, usage, duplicate call ids,
  and interrupted streams.
- Add transcript invariant tests for every call/output pairing rule. These
  tests should run against fake provider fixtures, saved Codex traces, saved
  Claude traces, replay, dogfood, emulator, and fastcheck.
- Add negative tests where the model emits text that looks like JSON. Native v2
  must preserve it as assistant text and must not parse it as control.
- Add finish tests proving schema-invalid finish gets a paired output,
  acceptance-rejected finish gets a paired output and continuation, and accepted
  finish completes only after deterministic gates.

### Metrics

- Make `provider_native_tool_loop=true` a required metric for native v2
  completion credit.
- Add `transport_kind` with enum-like values:
  `provider_native`, `legacy_model_json`, `fake_native`, `imported_trace`.
  Native speed/proof metrics may include only `provider_native` and explicitly
  scoped `fake_native` phase tests.
- Add a `model_json_main_path_detected` boolean computed from runtime id,
  provider id, command progress phase names, prompt contract hashes, and
  imported symbols. It must be false for native v2.
- Track native event counts: provider requests, provider events, output items,
  function calls, custom calls, paired outputs, orphan outputs, duplicate ids,
  blocked finishes, accepted finishes, and transcript replay failures.
- Keep projection metrics but rename them as derived sidecar metrics. They must
  never be the denominator for tool-loop progress.

### Roadmap Gates

- Roadmap status should have a native-loop gate distinct from WorkFrame,
  evidence, and speed gates.
- M6.24 speed proof should not start until the native-loop gate is green:
  native runtime selected by CLI, native transcript artifacts emitted, no
  production model-JSON imports, pairing replay valid, and observability
  preserved.
- Any phase that improves WorkFrame, frontier, prompt history, parse repair, or
  hot-path projections without changing native transport should be marked as
  sidecar/projection work, not native-loop progress.
- If live native provider behavior is unstable, the allowed fallback is
  `implement_v1` as a separate attempt or fake-provider native tests. The
  forbidden fallback is reviving model-JSON as the v2 main path.

## 3. Hard Invariants That Must Fail Tests

These are binary invariants. A violation should fail unit tests, integration
tests, or the phase close gate.

### Runtime Identity

- For production native v2:
  `runtime_id == "implement_v2_native_transcript_loop"`.
- For production native v2:
  `provider_native_tool_loop is True`.
- Production native v2 metrics, proof manifest, command progress, and runtime
  registry must agree on the same runtime id.
- No completed native v2 result may have `provider in {"model_json"}` or
  `transport_kind == "legacy_model_json"`.
- `implement_v2_model_json_tool_loop` may appear only in legacy fixtures,
  migration docs, or quarantine tests after Phase 5.

### Transport

- The native v2 model-facing main path must not ask the model to return one
  synthetic JSON object containing `tool_calls`, `finish`, or
  `frontier_state_update`.
- Native v2 must not parse assistant text as the main control protocol.
- Native v2 must not call `call_codex_json` or `call_model_json_with_retries`
  for runtime turns.
- The provider adapter must parse native response items/tool-use blocks and
  construct provider-native tool output items.
- `finish` must be represented as a native tool call item, not top-level model
  JSON.

### Transcript Source Of Truth

- `response_transcript.json` and `response_items.jsonl` are authoritative for
  native v2. `history.json`, if emitted, is derived and marked as such.
- Every provider tool call item with a `call_id` has exactly one paired output
  item with the same `call_id`.
- No output item exists without a prior call item, except quarantined imported
  reference traces explicitly marked as imported.
- A `call_id` cannot be reused for a different side-effecting call.
- Pairing validation failure blocks completion credit and proof manifest
  success.
- Tool outputs visible to the next model turn must be the paired provider
  output items, not controller-only state.

### Side Effects And Acceptance

- Side-effecting tool calls execute only after native call identity,
  schema validation, approval/write gates, and allowed-root checks pass.
- Invalid arguments, unknown tools, denied approvals, interrupted tools, and
  provider stream interruptions produce model-visible paired results or a
  replayable blocked state before any next provider turn.
- Running/yielded command outputs cannot satisfy acceptance.
- Completed v2 requires deterministic acceptance evidence resolving to the
  same lane attempt or allowed shared work-session evidence.
- Same-attempt fallback to v1 is forbidden. A v1 retry is a separate lane
  attempt with separate artifacts and metrics.

## 4. Observability Invariants To Preserve

The native rebuild must not weaken current observability. It should preserve or
improve these properties:

- `proof-manifest.json` remains the primary proof entry point.
- Tool registry and policy artifacts remain emitted, with provider-native
  lowering hashes included.
- Tool results remain indexed by provider `call_id` and local mew tool id.
- Evidence sidecar and evidence ref index remain generated from tool outputs,
  not model claims.
- Natural transcript remains available as a derived reader-friendly export.
- Model/native turn index remains available for replay and debugging, but it is
  not control authority.
- WorkFrame debug bundles remain emitted with stable input/output hashes and
  invariant status, derived from transcript and evidence.
- Native request descriptors record bounded request metadata:
  request hash, transcript window hash, sidecar digest hash, tool spec hash,
  `store`, `previous_response_id`, stream mode, provider ids, safe headers,
  latency, and usage.
- Provider event logs preserve enough information to replay streaming assembly:
  event type counts, output indexes, call ids, item ids, response ids,
  argument-delta accumulation, completion/failure events, and usage.
- Metrics keep current operational values:
  model turn count, elapsed seconds, tool counts, command closeout, auto-poll,
  cleanup, first-write latency, first-verifier latency, finish-gate blocks,
  typed acceptance status, WorkFrame hashes, hot-path/projection byte counts,
  prompt/input bytes, and provider-visible tool output bytes.
- New native metrics are additive:
  response item counts by kind, native call/output pair counts, duplicate/orphan
  counts, custom/freeform call counts, native parse/stream failures, request
  descriptor hashes, and transcript replay validity.

Observability must not be preserved by keeping model-JSON alive as the runtime.
Compatibility exports are acceptable only when they are generated from the
native transcript and labeled as derived.

## 5. Lightweight Close-Gate Checklist By Phase

### Phase 0: Freeze Baseline And Artifact Contract

- Current model-JSON runtime and artifact contract are recorded as legacy
  baseline.
- Native artifact contract names `response_transcript.json`,
  `response_items.jsonl`, `provider_requests.jsonl`,
  `provider_events.jsonl`, `call_result_pairing.json`, and
  `transcript_metrics.json`.
- Expected runtime id `implement_v2_native_transcript_loop` is documented.
- Deletion/quarantine list is present.
- No runtime code behavior is changed.

### Phase 1: Typed Native Transcript Schema And Replay

- Native transcript schema exists with provider ids, local ids, item kinds,
  `call_id`, raw refs, bounded payloads, and metrics refs.
- Pairing validator rejects missing, duplicate, orphan, and mismatched calls.
- Fake native, Codex, and Claude trace fixtures normalize into the same schema.
- Proof manifest can be generated from native transcript fixtures.
- WorkFrame debug can be regenerated from transcript-derived sidecar events.

### Phase 2: Tool Schema Lowering And Codex Native Adapter

- Tool specs lower to provider-native Responses tools with strict schemas.
- Custom/freeform `apply_patch` grammar path exists where supported, with JSON
  fallback labeled as provider capability fallback rather than default design.
- Stream parser tests cover function-call deltas, custom calls, completed,
  failed, usage, and interrupted streams.
- Request descriptors prove `store=false`, no `previous_response_id` in this
  phase, stable tool spec hash, transcript window hash, and sidecar digest hash.
- No live side-effecting model execution is enabled yet.

### Phase 3: Native Tool Harness Loop With Fake Provider

- Fake native provider drives real read, exec, write, patch, poll/cancel,
  output-read, and finish harness paths in controlled fixtures.
- Invalid native calls return paired provider-visible outputs.
- Side effects are blocked before execution on invalid ids, schema failures,
  approval denials, or unsafe paths.
- Native transcript artifacts and proof manifest are emitted.
- Tool latency, first-write latency, first-verifier latency, and pairing
  metrics are present.

### Phase 4: Sidecars And WorkFrame As Derived Projections

- Evidence sidecar, result index, ref index, model turn index, and WorkFrame
  bundle consume native transcript input.
- Prompt inventory shows only transcript window plus compact sidecar digest as
  model-facing context; no ordinary frontier/todo/proof/evidence object acts as
  control protocol.
- Model-authored `frontier_state_update` is absent from native prompt contract.
- Typed acceptance and finish gate tests pass from native transcript evidence.
- WorkFrame hashes and invariant status remain stable as derived observability.

### Phase 5: CLI Integration And Model-JSON Quarantine

- Registry reports `implement_v2_native_transcript_loop` and
  `provider_native_tool_loop=True`.
- `commands.py` calls the native runtime and records native progress phases,
  not `model_json_*`.
- Production imports of `JsonModelProviderAdapter` and
  `run_live_json_implement_v2` are gone.
- No production command path references `implement_v2_model_json_tool_loop`.
- Model-JSON parser retry and `frontier_state_update` rejection are unreachable
  from native v2.
- v1 behavior and fallback semantics are unchanged.

### Phase 6: Validation Gates Before Live Speed Proof

- Replay validates pairing, write safety, typed evidence refs, finish outputs,
  and WorkFrame derived hashes.
- Dogfood, emulator, tool-lab, and fastcheck consume native artifacts or
  explicit native readers.
- Blocked finish receives a paired output and continues; accepted finish records
  output and completes with proof.
- Micro next-action tests work from latest native call/result pairs without old
  frontier/todo control state.
- Ten-minute diagnostic shows zero model-JSON parse failures, zero unpaired
  native calls, first-write latency recorded, verifier cadence recorded, and
  same-family repeats bounded by declared thresholds.
- Reference comparison computes first tool, first edit, commands, edits,
  verifiers, messages/turns, and tool-output visibility from normalized
  transcripts.

### Phase 7: Delete Old Main Path

- Full focused tests pass.
- No production code imports `JsonModelProviderAdapter`,
  `run_live_json_implement_v2`, `_live_json_prompt`, or
  `_normalize_live_json_payload`.
- Old model-JSON artifacts are migrated through a converter or explicitly
  marked as legacy fixtures.
- Docs and roadmap status name native transcript v2 as the only v2 main path.
- Any remaining model-JSON code is test-only, legacy-only, and impossible to
  select as production `implement_v2`.

## 6. Acceptable Sidecar Projections Vs Forbidden Control Protocols

### Acceptable Sidecars

Sidecars are acceptable when they are deterministic, derived from transcript
and tool-result artifacts, and explicitly non-authoritative for provider
control. Examples:

- WorkFrame debug bundles generated from transcript and evidence indexes.
- Compact sidecar digest in the provider request summarizing safety
  constraints, fresh evidence refs, current verifier status, and bounded
  navigation context.
- Evidence sidecar and evidence ref index generated from tool outputs.
- Model/native turn index for replay, plateau analysis, and observability.
- Frontier-like blocked-state or recovery card generated by the controller
  after rejected finish, command failure, or compaction.
- Compatibility `history.json` export generated from native transcript for a
  transition phase, labeled derived and excluded from authority.

Acceptable sidecars answer:

```text
What has happened?
What evidence refs are fresh?
What constraints must not be weakened?
What compact context helps the next native model turn?
```

They do not answer:

```text
Which tool did the model call?
Which call_id must receive a result?
Did finish complete?
What did the provider see as the call/result sequence?
```

### Forbidden Model-Facing Control Protocols

These are forbidden in native v2 main path:

- A prompt contract asking the model to return one JSON object with
  `tool_calls`, `finish`, `action`, `tools`, or `calls`.
- `history_json` as the model-visible transport for prior tool results.
- Parsing assistant prose or JSON-looking text as the primary control channel.
- Model-authored `frontier_state_update`, todo updates, proof objects, or
  WorkFrame updates that alter runtime state.
- WorkFrame as the primary model-facing control protocol.
- A second ordinary model-visible todo/proof/frontier object beside native
  transcript window plus compact sidecar digest.
- Model-JSON parse repair as a runtime concern.
- Treating a top-level JSON `finish` field as completion.
- Letting compatibility exports feed the next model turn as authority.

The dividing line is simple: the provider-native transcript owns calls, outputs,
finish, replay, and proof chronology. Sidecars may summarize and index that
truth; they may not define a parallel control language for the model.

## 7. Reviewer's Required Additional Gates

I would add three gates beyond the current design:

1. Static drift gate:
   a test scans production v2 imports, prompt strings, command integration, and
   runtime metrics for model-JSON symbols. The test has an allowlist for docs
   and legacy fixtures only.
2. Native transcript authority gate:
   a test deletes derived `history.json`, WorkFrame bundle, model-turn index,
   and evidence sidecar from a fixture copy, regenerates them from
   `response_transcript.json` / `response_items.jsonl`, and compares hashes.
3. Model text non-control gate:
   a fake/native provider emits assistant text containing a complete JSON
   object with `tool_calls` and `finish`. Native v2 must record it as assistant
   text only, execute no tool from it, and continue or block according to native
   stop/tool-call semantics.

These gates directly target the earlier failure mode: a convenient projection
or parser becoming the runtime protocol.

## Final Assessment

The May 11 native transcript rebuild design identifies the right correction:
make provider-native response items and paired outputs the source of truth, and
demote WorkFrame/evidence/frontier/todo to derived projections.

The implementation should be judged harshly on transport, not just behavior.
If `implement_v2` can still complete by asking for model JSON, parsing it, and
projecting `history_json` into the next prompt, then it has not become native
even if its tool harness, evidence sidecars, and WorkFrame observability are
excellent.

Native-loop closure requires all three at once:

- production v2 runtime identity and metrics say native;
- artifacts prove native call/result transcript authority;
- tests make the old model-JSON main path unreachable, except as explicit
  legacy replay material.
