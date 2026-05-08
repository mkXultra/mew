# Design 2026-05-07 - M6.24 Integration Observability and Model Turn Extraction

Status: design only.

Scope: `implement_v2` instrumentation and internal model-turn boundary
extraction. This document does not authorize source behavior changes by itself.
The first implementation round must be behavior-preserving and must prove that
the same prompts, tool calls, tool results, finish decisions, lane result
status, and replay classification are produced before any hot-path tuning.

## Inputs Reviewed

- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/provider.py`
- `src/mew/implement_lane/prompt.py`
- `src/mew/implement_lane/types.py`
- `src/mew/implement_lane/replay.py`
- `docs/REVIEW_2026-05-07_CODEX_FLOW_VS_MEW_IMPLEMENT_V2.md`

## Problem

The 2026-05-07 Codex-vs-mew review concludes that `implement_v2` is not mainly
missing another strategy object. It is losing because the active coding loop is
too heavy and poorly integrated: model-JSON transport, proof concepts projected
too frequently, overlapping frontier/finish/recovery concepts, and source
mutation paths that are harder to audit than a first-class patch boundary.

Before changing behavior, mew needs one reliable observability layer around the
current model turn. The current runtime already has the ingredients:

- `run_live_json_implement_v2(...)` builds `_live_json_prompt(...)`, calls
  `model_json_callable(...)`, normalizes the payload, executes tools, appends
  full `history`, appends model-visible `prompt_history`, writes proof manifest
  metrics, and emits replay artifacts.
- `JsonModelProviderAdapter` explicitly records the current transport as
  `model_json`, not provider-native function calling.
- `prompt.py` builds provider-neutral prompt sections with cache metadata, but
  no provider-specific prompt-cache transport.
- `types.py` defines the lane input/result, tool envelopes, transcript events,
  and proof manifest boundary.
- `replay.py` validates call/result pairing and write safety, but it does not
  yet validate model-turn projections or observability records.

The missing piece is an explicit, replayable `ModelTurnInput -> ModelTurnOutput`
boundary and a sidecar `integration_observation` record that can explain what
the model saw, what mew retained, what mew hid or compacted, and where time and
tokens went.

## Goals

- Extract one model-turn boundary inside `implement_v2` without changing
  behavior.
- Emit behavior-preserving integration observations into the v2 proof manifest
  and artifact set.
- Audit model-visible projection separately from full history so future tuning
  can reduce prompt weight with evidence.
- Record enough metrics to compare the current loop against Codex-like hot-path
  properties: cheap probe latency, first edit latency, verifier cadence,
  repeated same-frontier loops, finish-gate blocks, and projection weight.
- Keep all records replayable, bounded, redacted where necessary, and safe for
  Terminal-Bench/dogfood reports.
- Defer provider-specific prompt-cache work until the model-turn boundary and
  projection audit prove which sections are actually stable, dynamic, and worth
  caching.

## Non-Goals

- No prompt text change in the behavior-preserving implementation round.
- No change to model output schema, tool schemas, tool policy, write policy,
  finish-gate behavior, reaction-turn budgeting, hard-runtime frontier logic, or
  acceptance gates.
- No default-route change for `implement_v1` or `implement_v2`.
- No provider-native function-calling implementation.
- No provider-specific prompt cache API integration.
- No new optimization heuristic, task-specific Terminal-Bench rule, or
  benchmark-tuned prompt.
- No large raw stdout/stderr duplication in proof manifest metrics.
- No recording of secrets, full environment dumps, auth material, or
  unbounded model prompts in normal proof manifests.

## Decision

Introduce a v2-local model-turn abstraction and observability record as a
sidecar around the existing `model_json_callable(...)` invocation.

The first implementation must be a mechanical extraction:

```text
existing loop state
  -> run_live_json_implement_v2 calls _live_json_prompt exactly where it does today
  -> ModelTurnInput(rendered_prompt plus audit metadata)
  -> call_model_turn(...)
       -> call exactly the same model_json_callable(...)
       -> time the call
       -> shape ModelBackendError exactly as today
       -> normalize exactly the same payload
       -> construct serializable observation descriptors
  -> ModelTurnOutput
  -> existing tool execution / finish / history / manifest behavior
```

`call_model_turn(...)` owns only `model_json_callable(...)` invocation, timing,
`ModelBackendError` shaping, payload normalization, and observation descriptor
construction. It must not own tool execution, finish-gate policy,
terminal-failure reaction policy, prompt rendering, frontier state, or prompt
tuning in the first round. Phase 1 is explicitly render-then-call: prompt
rendering stays in `run_live_json_implement_v2(...)`. Moving prompt rendering
inside the model-turn boundary is later work after byte-parity tests exist.

## The 1-5 Plan

### 1. `ModelTurnInput` / `ModelTurnOutput` Dataclasses And Boundary

Add dataclasses in `src/mew/implement_lane/types.py` or a v2-local module if
reviewers prefer to keep public lane types small. Separate the in-memory call
objects from serializable observation objects. `ModelTurnInput` and
`ModelTurnOutput` are internal runtime objects: they may carry raw rendered
prompt text or raw provider payloads only in memory and must not expose
`as_dict()` methods that serialize those raw fields by default.

The recommended first in-memory shape is:

```python
@dataclass(frozen=True)
class ModelTurnInput:
    lane: str
    lane_attempt_id: str
    turn_id: str
    turn_index: int
    transport: str
    model_backend: str
    model: str
    rendered_prompt: str  # in memory only; never serialized by default
    current_projection_bytes: bytes  # already-compacted prompt_history bytes
    prompt_descriptor: dict[str, object]
    projection_descriptor: dict[str, object]
    timeout_seconds: float

@dataclass(frozen=True)
class ModelTurnOutput:
    payload: dict[str, object]  # in memory only; never serialized by default
    normalized_payload: dict[str, object]
    elapsed_seconds: float
    prompt_chars: int
    response_shape: dict[str, object]
    model_error: dict[str, object]
    observation: dict[str, object]  # serializable descriptor only
```

The serializable observation object is a different shape. It contains only
hashes, counts, response shape, tool counts/names, failure classes, bounded
descriptors, and artifact refs. Raw rendered prompts, raw
`model_visible_history` entries, raw provider payloads, `model_auth`, and
provider request/response metadata are not serialized by default.

The boundary is inside `run_live_json_implement_v2(...)`, at the point where the
runtime currently invokes `model_json_callable(...)`. In Phase 1,
`run_live_json_implement_v2(...)` still builds `_live_json_prompt(...)` exactly
where it does today and passes the rendered prompt into `ModelTurnInput`.

### 2. Move Existing `model_json_callable(...)` Invocation Into `call_model_turn(...)`

Move the current invocation, timing, `ModelBackendError` conversion, payload
normalization, prompt char counting, and progress messages into
`call_model_turn(...)` or an equivalent v2-local helper.

Required first-round invariants:

- Same callable signature to `model_json_callable(...)`.
- Same `log_prefix`.
- Same timeout/base URL/model/auth arguments.
- Same `ModelBackendError` failure class mapping through the existing
  `_live_json_model_error(...)`.
- Same `_normalize_live_json_payload(...)` result for every payload.
- Same transcript, history, prompt history, finish arguments, and tool execution
  decisions after control returns to the main loop.

The helper returns data; it does not execute tools and does not mutate the
runtime state except through explicit return values. It also does not own,
mutate, filter, or interpret `hard_runtime_frontier_state`. It may return the
same normalized payload shape as today for main-loop compatibility, including a
`frontier_state_update` value, but frontier extraction, merge policy, and state
updates remain in `run_live_json_implement_v2(...)`.

### 3. Behavior-Preserving `integration_observation` Emission Into Proof Manifest

Add an `integration_observation` field under the existing
`ImplementLaneProofManifest.metrics` dictionary. This avoids a schema-version
bump in the first round because manifest consumers already treat `metrics` as a
mapping. The manifest field must stay small because `manifest.as_dict()` is also
placed in `ImplementLaneResult.updated_lane_state`. Full per-turn observation
must not persist through `updated_lane_state` or later `persisted_lane_state`.

By default, the manifest includes a summary plus an optional artifact ref:

```json
{
  "integration_observation": {
    "schema_version": 1,
    "runtime_id": "implement_v2_model_json_tool_loop",
    "transport": "model_json",
    "detail_policy": "summary",
    "artifact_ref": "",
    "summary": {
      "model_turns": 1,
      "prompt_chars": 12345,
      "model_elapsed_seconds": 1.234,
      "tool_call_count": 2,
      "turns_with_projection_truncation": 0,
      "turns_with_model_error": 0,
      "current_projection_chars_total": 2400,
      "future_projection_chars_total": 2400,
      "projection_savings_chars": 0,
      "projection_savings_ratio": 0.0
    }
  }
}
```

Full per-turn serializable observation belongs in
`integration-observation.json` only when detail is explicitly requested through
`lane_config["write_integration_observation_detail"] == true`. The default is
`false`: write only the small manifest summary and no sidecar. When the sidecar
is written, `integration_observation.artifact_ref` points to it, and the sidecar
path is returned from `_write_live_json_artifacts(...)` so it appears in
`ImplementLaneResult.proof_artifacts`.

The observation must be sidecar evidence. It cannot affect status,
`completion_credit`, replay validity, reaction-turn extension, finish-gate
decisions, or model-visible text in the behavior-preserving round.

### 4. Shadow Record Current Projection And Future Compact Projection

Record two projections for each model turn:

- `current_projection`: the exact current model-visible history projection that
  `_live_json_prompt(...)` receives today through `prompt_history`.
- `future_compact_projection`: a proposed smaller projection generated in
  shadow mode only.

The current projection hash source must be exact: compute bytes from the
already-compacted `prompt_history` object that `_live_json_prompt(...)` sends to
the model, with the same slicing and serialization:

```python
current_projection_json = json.dumps(
    list(prompt_history)[-8:],
    ensure_ascii=False,
    indent=2,
)
current_projection_bytes = current_projection_json.encode("utf-8")
```

The implementation should introduce a helper or render result, such as
`_render_prompt_history_json(prompt_history)`, and use that same result both in
`_live_json_prompt(...)` and in the projection audit. Hashing raw tool results,
full `history`, or a byte-different reserialization is not acceptable.

The future projection should be stored as an audit candidate, not sent to the
model. Its goal is to measure savings and semantic risk before tuning.

The future compact projection can start as a deterministic clone of the current
projection plus one of these no-op modes:

- `mode="identity"` in the first implementation, proving the audit plumbing.
- `mode="candidate_v0"` behind an explicit shadow-only flag after identity
  parity passes.

Candidate compaction should focus on exactly the pain described in the review:
keep latest command lifecycle, exit status, bounded stdout/stderr tails,
artifact miss if relevant, and one deterministic blocker class; keep full
stdout/stderr and proof objects in artifacts, not next-turn history.

Identity mode must prove byte parity:

- `future_projection_sha256 == current_projection_sha256`;
- `future_projection_chars == current_projection_chars`;
- `diff_summary == {}` or an equivalent empty diff shape;
- `projection_savings_chars == 0`;
- `projection_savings_ratio == 0.0`.

### 5. Replay/Dogfood Checks Proving Behavior Unchanged Before Tuning

Before enabling any candidate projection or prompt hot-path tuning, add checks
that prove behavior did not change:

- Unit tests with fake `model_json_callable` responses asserting identical
  prompts before and after extraction.
- Unit tests asserting identical normalized payloads, model error mapping,
  progress-visible turn count, proof manifest call/result pairing, and lane
  result status.
- Artifact tests asserting `history.json`, `transcript.json`, and
  `proof-manifest.json` remain compatible with current replay consumers.
- Replay tests in `src/mew/implement_lane/replay.py` or existing replay
  consumers that tolerate and summarize `integration_observation`.
- Terminal-Bench dogfood/replay checks on existing `implement_v2` fixture
  classes, proving next-action classification is unchanged.
- A shadow projection report that flags savings and semantic-risk indicators
  without changing the model prompt.

Only after parity is proven should mew tune the model-visible projection.

## Observability Schema

`integration_observation` is a manifest-side, schema-versioned summary object.
It should be append-only for v1 compatibility and should avoid changing the
existing top-level manifest schema until consumers need first-class validation.
It is not the full per-turn record.

Recommended manifest metrics schema:

```json
{
  "schema_version": 1,
  "runtime_id": "implement_v2_model_json_tool_loop",
  "transport": "model_json",
  "lane_attempt_id": "...",
  "artifact_namespace": "...",
  "detail_policy": "summary",
  "artifact_ref": "",
  "summary": {
    "model_turns": 0,
    "prompt_chars": 0,
    "model_elapsed_seconds": 0.0,
    "tool_call_count": 0,
    "finish_count": 0,
    "turns_with_projection_truncation": 0,
    "turns_with_model_error": 0,
    "current_projection_chars_total": 0,
    "future_projection_chars_total": 0,
    "projection_savings_chars": 0,
    "projection_savings_ratio": 0.0,
    "detail_written": false
  }
}
```

When `lane_config["write_integration_observation_detail"] == true`, write a
sidecar named `integration-observation.json` beside `proof-manifest.json`,
`transcript.json`, and `history.json`. The sidecar contains bounded per-turn
serializable observations:

```json
{
  "schema_version": 1,
  "runtime_id": "implement_v2_model_json_tool_loop",
  "transport": "model_json",
  "lane_attempt_id": "...",
  "artifact_namespace": "...",
  "turns": [
    {
      "turn_id": "turn-1",
      "turn_index": 1,
      "phase": "model_call",
      "prompt": {
        "chars": 0,
        "sha256": "sha256:...",
        "history_turns_included": 0,
        "sections": {"section_count": 0, "total_chars": 0, "by_id": {}}
      },
      "history_projection": {
        "current_projection_schema": "provider_history_projection_v0",
        "current_projection_sha256": "sha256:...",
        "current_projection_chars": 0,
        "future_projection_schema": "provider_history_projection_candidate_v0",
        "future_projection_sha256": "sha256:...",
        "future_projection_chars": 0,
        "future_projection_mode": "identity",
        "diff_summary": {}
      },
      "response": {
        "elapsed_seconds": 0.0,
        "payload_kind": "object",
        "summary_chars": 0,
        "tool_call_count": 0,
        "tool_names": [],
        "has_finish": false,
        "finish_outcome": "",
        "frontier_update_keys": []
      },
      "error": {
        "failure_class": "",
        "error_type": "",
        "message_sha256": "",
        "raw_excerpt_chars": 0
      }
    }
  ]
}
```

Fields that might contain sensitive or large model content should be represented
by byte/character counts, hashes, bounded excerpts, and artifact refs rather
than raw bodies.

## Model-Visible Projection Audit

The audit has three questions:

1. What did the model actually see this turn?
2. What full evidence did mew retain outside the prompt?
3. What smaller projection could the model have seen without losing actionable
   next-step information?

For the current behavior, the model-visible projection is produced by
`_provider_visible_tool_result_for_history(...)`,
`_project_terminal_result_for_provider_history(...)`, and
`_compact_provider_visible_content_for_history(...)`, then included in
`history_json` by `_live_json_prompt(...)`.

The audit should record:

- prompt history turn count and serialized character count;
- per-turn `tool_names`, statuses, `is_error`, and provider call ids;
- whether terminal payloads used `provider_history_projection=terminal_result_v0`;
- stdout/stderr chars retained, omitted, and referred to by `output_ref`;
- structured execution summary keys projected into prompt history;
- content refs and evidence refs preserved;
- list truncation and text truncation markers;
- finish-gate continuation entries projected into history;
- hash of the exact current projection sent to the model.

The audit must never replace replay artifacts. Full `history.json`,
`transcript.json`, and `proof-manifest.json` remain the source of record.

## Metrics

The first-round metrics should explain current integration behavior, not score
new heuristics:

- `model_turns`, `model_elapsed_seconds`, and `prompt_chars_total`.
- Per-turn prompt chars and prompt section chars.
- Per-turn current projection chars and future projection chars.
- `projection_savings_chars` and `projection_savings_ratio` for shadow
  candidates.
- `tool_call_count`, `tool_result_count`, and tool names per turn.
- `terminal_result_turns`, `write_result_turns`, and `finish_gate_turns`.
- `turns_with_model_error`, with failure classes only.
- `turns_with_history_compaction` and truncation counts.
- Hot-path timings derived without behavior changes:
  - first read/search/inspect turn;
  - first terminal command turn;
  - first write/edit/apply_patch turn;
  - first verifier-shaped command turn;
  - repeated same-frontier runtime loop count when existing evidence can
    identify it.

These metrics support future tuning by showing where weight and latency live.
They should not determine model-visible behavior until a later accepted design
or implementation round.

## Replay Semantics

Replay must treat `integration_observation` as optional audit data.

Required replay rules:

- Existing manifests without `integration_observation` stay valid.
- Summary-only observations stay valid when no sidecar is written.
- When `artifact_ref` is present, replay may read `integration-observation.json`
  from `proof_artifacts`; missing or malformed sidecar detail is reported as an
  observability defect, not a pairing failure.
- Pairing validation remains based on `tool_calls` and `tool_results`.
- Write safety validation remains based on write tool results and side effects.
- Observation validation checks only self-consistency:
  - schema version known;
  - turn count matches or is less than manifest/runtime model turn count when
    interrupted;
  - prompt/history projection hashes are well-formed;
  - char counts are nonnegative;
  - no raw auth fields are present;
  - totals equal per-turn sums where applicable.
- Observation validation failure should be reported as an observability defect,
  not as tool pairing failure, unless future implementation explicitly promotes
  it.

Dogfood and Terminal-Bench replay reports should summarize the observation as:

- current projection weight;
- shadow candidate savings;
- model-error classes;
- first edit/verifier timings;
- any observability validation defects.

Next-action routing must be unchanged in the first implementation.

## Privacy And Size Limits

The observation layer must be bounded because model prompts and command outputs
can contain secrets, credentials, proprietary source, or very large logs.

Rules:

- Store hashes and counts for full prompts by default.
- Treat raw `ModelTurnInput` and `ModelTurnOutput` as in-memory only. Do not
  serialize raw rendered prompts, raw `model_visible_history` entries, raw
  provider payloads, `model_auth`, provider request metadata, provider response
  metadata, access tokens, or API keys by default.
- Do not store full environment dumps or filesystem-wide metadata snapshots.
- Do not duplicate full stdout/stderr in `integration_observation`; use
  existing `content_refs`, `output_ref`, `history.json`, and manifest tool
  result payloads.
- Keep bounded excerpts only when they are already model-visible in current
  prompt history, and cap them with the same or smaller limits as current
  provider-history projection.
- Cap per-turn observation payload size. Suggested default: 16 KiB per turn,
  with overflow summarized by hashes/counts and `observation_truncated=true`.
- Cap the proof-manifest observation summary tightly. Suggested default: 8 KiB
  per lane attempt. Cap optional sidecar detail separately, with a suggested
  default of 256 KiB per lane attempt.
- Hash large string fields with `sha256:` prefixes and deterministic JSON
  serialization.
- Preserve refs (`content_refs`, `evidence_refs`, `output_ref`, artifact paths)
  so replay can locate full evidence without embedding it in the manifest
  metrics.
- Prevent full per-turn observation from entering `updated_lane_state` or later
  `persisted_lane_state`. Add a size test that fails if the manifest copy placed
  in `updated_lane_state["proof_manifest"]` contains sidecar `turns` or exceeds
  the agreed summary budget.

## File Integration

### `src/mew/implement_lane/v2_runtime.py`

Owns the extraction point and keeps prompt rendering in place for Phase 1. The
main loop should call `_live_json_prompt(...)` exactly where it does today,
construct `ModelTurnInput` from the rendered prompt plus audit metadata, call
`call_model_turn(...)`, then continue with the same normalized payload handling,
frontier update handling, tool execution, finish-gate logic, histories,
transcript events, and manifest construction. `_write_live_json_artifacts(...)`
should write `integration-observation.json` only when
`lane_config["write_integration_observation_detail"] == true`; when written,
that path is returned and appears in `ImplementLaneResult.proof_artifacts`.

### `src/mew/implement_lane/provider.py`

Provides the transport label and provider adapter context. In the first round,
`JsonModelProviderAdapter.provider == "model_json"` should remain the transport
recorded in observations. Do not add provider-native function calling or
provider-specific prompt cache calls here as part of this work.

### `src/mew/implement_lane/prompt.py`

Keeps prompt sections provider-neutral. Phase 1 may collect
`implement_v2_prompt_section_metrics(...)` or equivalent section metrics for
observation, but must not alter section content, order, cache policy, or
rendering. If prompt-history rendering is factored into a helper for hashing
parity, that helper should preserve the current bytes exactly:
`json.dumps(list(prompt_history)[-8:], ensure_ascii=False, indent=2)`. In the
current `_live_json_prompt(...)` signature, this is the already-compacted
history argument passed from `prompt_history`.

### `src/mew/implement_lane/types.py`

Likely home for `ModelTurnInput`, `ModelTurnOutput`, and possibly
`IntegrationObservation` dataclasses if reviewers want shared serializable
types. Keep the raw call objects internal and non-serializing; keep only the
observation summary/detail objects JSON-shaped. If reviewers prefer less public
surface, define them in a new v2-local module and export only after tests prove
stability.

### `src/mew/implement_lane/replay.py`

Adds optional observation validation helpers after the first manifest emission
exists. These helpers must be separate from pairing and write-safety validation
so an observability defect does not masquerade as a provider tool-call defect.
Replay should discover detail through
`metrics.integration_observation.artifact_ref` or the returned
`proof_artifacts` path, and must tolerate summary-only manifests.

### `docs/REVIEW_2026-05-07_CODEX_FLOW_VS_MEW_IMPLEMENT_V2.md`

This design operationalizes the review's recommendation to simplify the hot
path with evidence. It does not immediately remove frontier/execution-contract
machinery. Instead, it measures exactly how much model-visible weight those
concepts add and where projection can be reduced safely.

## Tests

Initial implementation tests should be focused and parity-oriented:

- Fake model response test proving `call_model_turn(...)` passes the exact same
  prompt and callable arguments as the current inline call.
- Render-then-call test proving `_live_json_prompt(...)` is still called by
  `run_live_json_implement_v2(...)` at the existing point, and
  `call_model_turn(...)` receives the rendered prompt instead of building it.
- Model error test proving parse/backend/timeout errors produce the same
  `model_error`, transcript event shape, history entry, status, and replayable
  failure.
- Frontier ownership test proving `call_model_turn(...)` does not mutate,
  filter, interpret, or persist `hard_runtime_frontier_state`.
- Manifest test proving summary-only `integration_observation` appears under
  metrics and existing `replay_valid` remains unchanged.
- State-size test proving `updated_lane_state["proof_manifest"]` contains only
  the small observation summary plus optional `artifact_ref`, not sidecar
  `turns` or raw prompt/payload/history data.
- Projection audit unit test proving current projection hash/chars are computed
  from bytes produced by the same helper/render result used for
  `_live_json_prompt(...)`: `json.dumps(list(prompt_history)[-8:],
  ensure_ascii=False, indent=2).encode("utf-8")`.
- Shadow projection identity test proving `future_compact_projection` is
  explicitly `mode=identity`, `future_projection_sha256` equals
  `current_projection_sha256`, chars are equal, diff summary is empty,
  `projection_savings_chars == 0`, and `projection_savings_ratio == 0.0`.
- Sidecar discovery test proving `integration-observation.json` is written only
  when `lane_config["write_integration_observation_detail"] == true`, is
  returned by `_write_live_json_artifacts(...)`, and appears in
  `ImplementLaneResult.proof_artifacts`.
- Artifact compatibility test proving existing `history.json`,
  `transcript.json`, and `proof-manifest.json` paths and JSON shapes remain
  consumable.
- Replay test proving manifests with and without `integration_observation` are
  accepted and summarized correctly.
- Privacy/size test proving large stdout/stderr and large prompts are hashed,
  counted, or ref-backed rather than duplicated into manifest metrics.
- Dogfood replay regression test proving Terminal-Bench next-action
  classification is unchanged when the observation is present.

Recommended command set for the implementation round:

```text
uv run pytest --no-testmon tests/test_implement_lane.py tests/test_terminal_bench_replay.py -q
uv run ruff check src/mew/implement_lane tests/test_implement_lane.py tests/test_terminal_bench_replay.py
```

The exact command can be narrowed if the implementation remains fully local to
`implement_lane`, but at least one replay consumer test should run.

## Future Hot-Path Tuning

This design supports Codex-like tuning by separating measurement from behavior.
Once parity is proven, mew can safely ask:

- Which prompt sections dominate first-turn and repeated-turn cost?
- Which execution evidence fields help the next model action, and which are
  proof-only?
- How often does the model need full artifact/verifier objects versus the latest
  command, exit code, bounded tails, and refs?
- How much would a compact projection save before first patch and before final
  verifier?
- Where do repeated same-frontier loops occur, and what exact model-visible
  observations preceded them?

That evidence enables later changes such as:

- thinner model-visible history for cheap probes;
- sidecar proof classification rather than prompt-heavy proof objects;
- smaller normal-turn response contract;
- model-visible frontier only when preventing rediscovery or false completion;
- stricter patch/verifier cadence metrics.

### Post-Observation Tuning Backlog

Do not stop at observation. The next intended product move after this design is
to make `implement_v2` behave more like the Codex active coding hot path, using
the new observations to choose the smallest safe change.

Trigger for this backlog:

- model-turn extraction and `integration_observation` are implemented;
- parity/replay/dogfood checks prove behavior did not change;
- at least one target task has a mew trace with integration observations and a
  Codex reference trace for step comparison.

When triggered, prefer this order:

1. Reduce model-visible proof/frontier/execution-contract weight.
   Keep proof, frontier, execution evidence, and finish gates as sidecar/replay
   evidence by default. Project them into the model only when they prevent
   rediscovery or false completion.
2. Strengthen the active coding rhythm:
   cheap probe -> coherent patch -> verifier -> latest-failure repair.
   Measure first cheap probe, first patch/edit, first verifier, verifier repair
   cadence, and repeated same-frontier loops before and after changes.
3. Move proof/evidence classification behind deterministic sidecars.
   The model should usually see the latest command, exit code, bounded tails,
   artifact miss if relevant, refs, and one concise blocker class; full proof
   objects remain in artifacts.
4. Make source mutation prefer patch/edit paths.
   `run_command` should not silently become the normal source-mutation path.
   Either route source changes through write/edit/apply_patch, intercept obvious
   shell patch attempts, or record diff-level side effects.
5. Defer provider-native tool calling and provider-specific prompt cache until
   the observed hot path is thinner.
   These are likely necessary later, but implementing them before reducing
   prompt/projection weight risks optimizing the wrong shape.

If observations show a different dominant gap, update this backlog with that
evidence before tuning. Do not add a large StrategyPlan object as the default
answer; the current reference evidence says Codex wins through a smaller,
transcript-driven, patch/verifier-oriented loop rather than a larger explicit
planning ontology.

The design deliberately avoids provider-specific prompt-cache work now. Prompt
cache APIs should come after this boundary proves which sections are stable,
which dynamic fields churn, and which model-visible projections should remain.
Otherwise mew risks caching a prompt shape that is already known to be too heavy
for the active coding hot path.

### Evidence Contract V0 Trigger

The acceptance gate is a temporary safety boundary, not the intended long-term
center of the coding loop. Codex-like behavior means the model naturally uses
tool results, verifier failures, and artifact evidence to choose the next patch
or finish point, while deterministic gates become last-mile assertions rather
than frequent correction mechanisms.

This section is a trigger rule for evidence/acceptance-mismatch repairs, not the
current M6.24 active next action. The active next action is always the newest
row in `docs/M6_24_DECISION_LEDGER.md`; as of 2026-05-08, model-transport
timeout guard repair takes precedence over further evidence-contract work.

Use this sequence only when the active ledger row classifies the current miss as
an evidence/projection/acceptance mismatch:

1. Commit the current repair only after review and focused validation pass.
2. Run one 10min `make-mips-interpreter selected_lane=implement_v2`
   step-shape diagnostic before any live `speed_1`, `proof_5`, or broad
   measurement.
3. Compare the new trace against the Codex reference. The diagnostic question
   is not score first; it is whether the loop moved toward:
   cheap probe -> coherent patch -> verifier -> latest-failure repair.
4. If the next miss is again caused by finish/projection/acceptance evidence
   mismatch, stop adding narrow acceptance heuristics and implement an
   `EvidenceEvent` / `oracle bundle` / cited-finish contract v0.
5. If the miss is not an evidence mismatch, classify the observed hot-path gap
   and choose the smallest generic repair from this design's tuning backlog.

`EvidenceEvent` / `oracle bundle` / cited-finish v0 should make the following
objects first-class in `implement_v2`:

- task oracle bundle: expected paths, expected outputs, verifier command shape,
  task-provided dimensions/resolution, task-provided reference/golden/oracle
  artifacts, and explicit acceptance markers;
- evidence events: command id, tool/result id, exit code, artifact path,
  stdout/stderr refs, structured artifact checks, oracle pass/fail, and failure
  class;
- cited finish: completion may reference evidence ids and oracle ids, but
  free-form model claims alone do not satisfy runtime/artifact/model-output
  tasks.

The model-visible projection should stay small: latest command, exit code,
bounded tails, artifact miss or oracle verdict, refs, and one concise blocker
class. Full proof objects, verifier transcripts, and historical evidence stay
in sidecars/replay artifacts by default.

Do not treat a more complex acceptance gate as progress by itself. A healthy
post-repair trace is one where the gate rarely blocks because the work loop has
already gathered and cited verifier-shaped evidence that matches the external
truth. If the gate keeps discovering missing/ungrounded evidence, the next
repair belongs in the tool-result -> evidence -> next-action -> cited-finish
structure, not another task-family-specific gate patch.

## Acceptance For This Design

The design is acceptable when reviewers agree that:

- it is design-only and does not change source behavior;
- the five-step plan is behavior-preserving before tuning;
- the observability schema is bounded, replayable, and optional for old
  manifests;
- the projection audit records both current and future compact views without
  sending the future view to the model;
- tests prove behavior unchanged before any prompt, projection, provider, or
  cache optimization.
