# Design 2026-05-20 - M6.25 Implement V2 Lane Substrate Cleanup

Status: design only, implementation-ready candidate.

Scope: clean up the M6.24 experimental structure and legacy runtime under
`src/mew/implement_lane` so the implement lane v2 native loop becomes a
lane-template-friendly substrate. This design is a precursor to reusing the
substrate for research lane and later lanes. It does not authorize changes to
runtime code, tests, roadmap files, or other documentation by itself.

## Decision

`implement_v2` production should keep exactly one live runtime family:

```text
implement_v2
  -> provider-native transcript loop
  -> selected ToolSurfaceProfile, default codex_hot_path
  -> provider loop and tool dispatch in a narrow native harness
  -> internal done-candidate closeout
  -> finish verifier planner component
  -> NativeFinishGate plus CompletionResolver sidecars
  -> native proof, replay, and observability artifacts
```

The old model-JSON runtime is not a production fallback. Because this is
pre-release, backward compatibility is not a constraint. Legacy code can be
deleted when unused, or retained only as explicitly named read-only diagnostics
under a legacy namespace that cannot be imported by production routes.

The provider-visible finish tool has already been removed from the intended
hot path. Any "finish gate" language in this design means internal closeout,
done-candidate gating, and completion resolution, not a model-visible finish
schema.

The future research lane must not copy `src/mew/implement_lane`. It should
compose a shared native substrate plus research-specific tools and completion
policy.

## Non-Goals

- No provider-visible finish tool, finish schema, `task_contract` JSON,
  WorkFrame contract, raw proof manifest, or resolver decision.
- No compatibility guarantee for historical model-JSON artifacts or old test
  fixtures.
- No copying `implement_lane` into `research_lane`.
- No new lane-specific controller hidden inside `ToolRegistry`.
- No regression in transcript pairing, proof manifest hashing, replay,
  sidecars, route observability, leak scans, write approval, command lifecycle,
  or final verifier freshness.
- No new Terminal-Bench proof spend as part of the cleanup itself. Existing
  benchmark evidence is preserved by replay/static gates first.

## Current Repo Facts

The current tree already has most of the native target:

- `src/mew/implement_lane/native_tool_harness.py` exposes
  `run_live_native_implement_v2()` and `run_native_implement_v2()`.
- `src/mew/implement_lane/tool_registry.py` defaults to
  `CODEX_HOT_PATH_PROFILE_ID` and records profile metadata.
- `src/mew/implement_lane/finish_verifier_planner_policy.py` default-enables
  the finish verifier planner through a central policy.
- `src/mew/implement_lane/native_finish_gate.py` and
  `src/mew/implement_lane/completion_resolver.py` already define sidecar-first
  finish decision boundaries.
- `src/mew/implement_lane/native_validation.py` already has static native-loop
  gates for default profile, planner default, native runtime identity, and some
  legacy model-JSON symbols.
- Model-JSON has partial quarantine via
  `src/mew/implement_lane/legacy_model_json_runtime.py` and
  `src/mew/implement_lane/legacy_model_json_provider.py`.

The cleanup problem is that production-adjacent imports and responsibilities
are still tangled:

- `native_tool_harness.py` owns provider loop, tool dispatch, transcript
  appends, artifact writes, done-candidate handling, final verifier closeout,
  planner request construction, planner safety checks, finish gate projection,
  NG resume policy, loop-control heuristics, and provider request rendering.
- `v2_runtime.py` still contains the legacy model-JSON live loop plus helper
  functions used by diagnostics.
- WorkFrame variant modules remain exported and production-readable:
  `workframe_variants.py`, `workframe_variant_transition_contract.py`,
  `workframe_variant_transcript_first.py`,
  `workframe_variant_transcript_tool_nav.py`, and
  `workframe_variant_minimal.py`.
- `finish_acceptance_helpers.py` and `execution_evidence.py` still bridge old
  finish/acceptance/typed-evidence concepts into live finish reasoning.
- Tool-lab and fastcheck diagnostics still rely on model-JSON helper imports.

## Target Architecture

The cleanup introduces a lane substrate boundary with this dependency shape:

```text
mew.lane_substrate
  native transcript
  provider adapter
  tool registry interfaces
  provider-visible result renderer interface
  artifact writer/proof manifest helpers
  observability records
  compact sidecar digest contract
  replay validators
      ^
      |
mew.implement_lane
  implement tool profile: codex_hot_path
  patch/write/edit/exec/read runtime bindings
  coding prompt contract
  final verifier planner policy
  coding completion policy
  Terminal-Bench/Harbor closeout adapters
      ^
      |
mew.research_lane, future lanes
  lane-specific tool profiles
  lane-specific prompt contract
  lane-specific completion policy
```

Shared substrate may know that tools exist, calls are paired, artifacts are
written, provider payloads are native, and proof records are hashable. It must
not know that a lane is solving a coding task, running Terminal-Bench, applying
patches, using Harbor closeout, or applying implement-specific finish
semantics. Finish gate policy, finish verifier planning, completion resolver
interpretation, Terminal-Bench/Harbor closeout, and coding completion semantics
belong to the lane implementation, not the substrate.

## Substrate API Boundary

The implementation should introduce a small shared package, tentatively
`src/mew/lane_substrate/`, with these conceptual APIs. Exact class names may
vary, but the dependency direction and artifact meaning are fixed.

```text
LaneRuntimeSpec
  lane_id
  runtime_id
  provider_adapter
  tool_surface_resolver
  tool_dispatcher
  transcript_store
  artifact_writer
  completion_policy
  observability_policy

NativeLoopRunner
  run(spec, lane_input, provider, artifact_root, max_turns) -> LaneRunResult

NativeTranscriptStore
  append_provider_items()
  append_tool_output()
  validate_pairing()
  write_response_transcript()

ProviderNativeAdapter
  build_request_descriptor()
  parse_response_items()
  apply_previous_response_delta()

ToolSurfaceResolver
  build_snapshot(lane_config, transcript_state, provider_capabilities)

ToolDispatcher
  dispatch(provider_call, runtime_context) -> ToolResultEnvelope

ToolResultRenderer
  render(profile_id, result) -> provider_visible_text

ArtifactWriter
  write_transcript()
  write_tool_results()
  write_provider_requests()
  write_route_records()
  write_proof_manifest()
  patch_manifest_sidecar_refs()

CompletionPolicyProtocol
  maybe_build_done_candidate()
  run_internal_closeout()
  resolve_completion()
  build_resume_signal()
```

`CompletionPolicyProtocol` is substrate-owned only as an interface. The
concrete implementation is lane-owned and passed through `LaneRuntimeSpec`.
`NativeLoopRunner` may call the protocol and persist the returned sidecar refs;
it must not inspect lane-specific completion meaning, construct finish gate
inputs, know Terminal-Bench/Harbor rules, choose coding verifier policy, or
interpret completion resolver blockers. For implement lane, that concrete
implementation lives under `mew.implement_lane` and can compose
`native_finish_gate.py`, `finish_verifier_planner.py`, and
`completion_resolver.py`. A future research lane provides its own completion
policy without importing implement completion modules.

Research lane acceptance gate:

- a minimal `research_lane` fixture can instantiate `LaneRuntimeSpec` using
  only `mew.lane_substrate` plus research-owned tool profile modules;
- the fixture has no import of `mew.implement_lane.native_tool_harness`,
  `mew.implement_lane.v2_runtime`, implement WorkFrame variants, or
  implement closeout helpers;
- shared replay validates transcript pairing and proof manifest hashing for
  the fixture.

## Native Harness Responsibility Boundary

`native_tool_harness.py` should become a thin implement-lane composition file
or be replaced by `implement_lane/native_runtime.py` that wires implement
components into `NativeLoopRunner`.

The ideal harness owns only:

- selecting the provider and calling the provider loop;
- asking the selected tool surface for provider-visible descriptors;
- dispatching model-issued tool calls to a dispatcher;
- appending exactly one paired output for each call;
- writing transcript, provider request, route, sidecar, and proof artifacts;
- returning `ImplementLaneResult` from substrate result fields.

The harness must not own:

- internal finish closeout policy;
- planner request construction, tool policy, safety validation, or retry logic;
- completion allow/block semantics;
- WorkFrame reducer selection;
- Terminal-Bench/Harbor acceptance rules;
- task-contract compiler interpretation;
- NG resume policy beyond invoking a completion policy component;
- legacy model-JSON replay compatibility.

The implementation should remove giant local helper families from the harness
by moving them to named components before changing behavior. A function may
stay temporarily only if the phase close gate proves it is not imported by the
production loop after extraction.

## Finish Components

### NativeFinishGate

`src/mew/implement_lane/native_finish_gate.py` owns internal closeout decision
contracts:

- `FinishCloseoutCommand`
- `FinishCloseoutCommandValidation`
- `NativeFinishGatePolicy`
- `NativeFinishGateRequest`
- `NativeFinishCloseoutResult`
- `NativeFinishGateDecision`
- `select_closeout_command()`
- `validate_closeout_command()`
- `decide_native_finish_from_closeout()`
- `write_native_finish_gate_artifacts()`

It may read implement-specific closeout facts such as configured verifier,
auto-detected verifier, planner-selected verifier, allowed roots, command
budget, source mutation summary, and typed evidence refs. It must not call the
provider, execute tools directly, or scan arbitrary transcript history.

### FinishVerifierPlanner

Planner code should become a component, not a family of harness functions.
Create a module such as
`src/mew/implement_lane/finish_verifier_planner.py` with:

- `FinishVerifierPlannerLoopPolicy`
- `FinishVerifierPlannerLoopRequest`
- `FinishVerifierPlannerLoopResult`
- `FinishVerifierPlan`
- `FinishVerifierPlanCoercion`
- request builder from pre-extracted visible facts;
- planner prompt renderer;
- result coercion;
- command safety validation;
- decision/request artifact records.

The component may use a separate provider session to propose one verifier
command. It never accepts completion. It must not receive hidden benchmark
oracle details, raw `task_contract` JSON, resolver blockers, or proof oracle
constraints. It can see visible task text, visible tool results, candidate
paths, configured verifier command, workspace facts, and bounded budget facts.

Current harness symbols that should move into this component include:

- `FinishVerifierPlannerLoopPolicy`
- `FinishVerifierPlannerLoopRequest`
- `FinishVerifierPlannerLoopResult`
- `_NativeFinishVerifierPlan`
- `_NativeFinishVerifierPlanCoercion`
- `_FinishVerifierCommandSafetyResult`
- `_FinishVerifierPlannerEligibility`
- `_native_finish_verifier_planner_can_run`
- `_finish_verifier_planner_loop_request`
- `_run_finish_verifier_planner_loop`
- `_coerce_native_finish_verifier_plan*`
- `_finish_verifier_command_safety`
- `_finish_verifier_observable_requirements`
- `_finish_verifier_planner_request`
- `_finish_verifier_planner_prompt`
- `_record_finish_verifier_planner_*`
- `_write_finish_verifier_planner_artifacts`

### CompletionResolver

`src/mew/implement_lane/completion_resolver.py` stays sidecar-only and consumes
pre-extracted facts:

- done candidate id or legacy finish claim id;
- transcript hash;
- compact sidecar digest hash;
- closeout refs;
- fresh verifier refs;
- typed evidence refs;
- oracle obligation refs;
- blockers and missing obligations.

It must not execute tools, call providers, build provider messages, parse
arbitrary transcript items, or read raw command output. If fresh verifier
evidence is missing, it returns `blocked_continue` or `blocked_return`; it does
not run the verifier itself.

## Deletion And Isolation Map

The following map is normative for production imports. "Delete" means remove
if no isolated diagnostic still needs it. "Isolate" means keep under a
diagnostic or fixture namespace with static gates proving production cannot
import it.

| File or symbol | Action | Target owner | Production rule |
|---|---|---|---|
| `run_live_json_implement_v2` | delete from production, optionally isolate | `legacy_experiments/model_json_runtime.py` or delete | no production import, no CLI route, no package export |
| `model_json_tool_loop` / `implement_v2_model_json_tool_loop` runtime id | delete from production | legacy diagnostics only | rejected by native validation and proof gates |
| `JsonModelProviderAdapter` family | isolate or delete | `legacy_experiments/model_json_provider.py` | no import from `commands.py`, native harness, provider adapter, registry, package surface |
| `src/mew/implement_lane/v2_runtime.py` | reduce to legacy diagnostics or delete | split helpers first | no production native import |
| `_live_json_prompt`, `_normalize_live_json_payload`, `call_model_json_with_retries` | delete | none | static banned symbols |
| `_render_prompt_history_json` | move if still needed | `lane_substrate/transcript_rendering.py` or diagnostic helper | no import from legacy runtime |
| `_source_output_contract_from_tool_results`, `_frontier_evidence_registry` | move if still needed | implement diagnostics or proof helper | no dependency on model-JSON loop |
| `run_fake_exec_implement_v2`, fake read/write JSON runtimes | isolate | fixtures or `legacy_model_json_tool_lab.py` | not package-exported |
| `legacy_model_json_runtime.py` | keep only as read-only diagnostic facade or delete | legacy diagnostics | no production imports |
| `legacy_model_json_provider.py` | keep only as diagnostic facade or delete | legacy diagnostics | no production imports |
| `provider.py` `FakeProviderAdapter` and `FakeProviderToolCall` | move to test fixture if only tests use it | tests/fixtures or substrate fake provider | not package-exported from production package |
| `tool_profiles/mew_legacy.py` | isolate, then delete after diagnostic A/B artifacts stop needing it | `legacy_experiments/tool_profiles/mew_legacy.py` | `build_tool_surface_snapshot({})` never selects it; explicit diagnostic only |
| `list_v2_base_tool_specs`, `list_v2_tool_specs_for_mode`, `list_v2_tool_specs_for_task` | delete or isolate | active `ToolSurfaceResolver` replacement | banned from production imports and package exports |
| `workframe_variants.py` registry | isolate | `legacy_experiments/workframe_variants/` | production digest uses one canonical projection, not variant dispatch |
| `workframe_variant_transition_contract.py` | isolate or delete | legacy experiment | no production imports |
| `workframe_variant_transcript_first.py` | isolate or delete | legacy experiment | no production imports |
| `workframe_variant_transcript_tool_nav.py` | isolate or delete | legacy experiment | no production imports |
| `workframe_variant_minimal.py` | isolate or delete | legacy experiment | no production imports |
| `workframe_variants`, `project_workframe_with_variant`, `reduce_workframe_with_variant`, `DEFAULT_WORKFRAME_VARIANT`, `CommonWorkFrameInputs` | delete from production imports/exports | legacy WorkFrame diagnostics only | banned across all production scan files, including `prompt.py` and `native_workframe_projection.py` |
| `WorkFrameInputs`, `WorkFrame`, raw WorkFrame prompt projection | diagnostics only | compact sidecar digest component | not provider-visible and not production completion authority |
| `prompt.py` WorkFrame/task-contract projection | replace | implement prompt contract using substrate sidecar refs | no import of WorkFrame variants; no raw compiler JSON in provider-visible prompt |
| `native_workframe_projection.py` | replace or isolate | compact sidecar digest/projection module | if retained in production, it cannot import variant registry or expose variant selector |
| `task_contract_compiler` live-path handling | replace, not merely ban | `commands.py` migration plus `native_finish_gate`/`proof_obligations.py` | no provider-visible projection; no direct harness interpretation |
| `commands.py` `task_contract_compiler*` work-guidance config | delete from live lane config or rename into internal obligation compiler | `CompletionObligationIndex` sidecar writer | `commands.py` must not pass raw compiled contract into `LaneInput.task_contract`, provider payloads, prompt rendering, native loop, or planner prompt |
| `finish_acceptance_helpers.py` old bridge | split | internal closeout helpers or legacy diagnostics | harness consumes typed refs, not old acceptance sessions |
| `_finish_acceptance_action`, `_typed_acceptance_session_from_tool_results` | isolate unless still internal-only | `legacy_acceptance_bridge.py` or proof helper | not called by provider loop |
| `execution_evidence.resolve_typed_finish` if tied to old finish | keep only as diagnostic resolver | proof diagnostics | CompletionResolver remains authority |
| `native_tool_harness.py` planner helpers | move | `finish_verifier_planner.py` | harness calls component interface only |
| `native_tool_harness.py` closeout decision helpers | move | `native_finish_gate.py`/`completion_resolver.py` | harness calls component interface only |
| `native_tool_harness.py` artifact helpers | move | substrate `artifact_writer.py` | harness delegates writes |
| `native_tool_harness.py` provider request helpers | move | substrate provider adapter or implement prompt profile | harness delegates request building |
| `substrate_inventory.py` M6.24 WorkFrame inventory | isolate or rewrite | M6.25 substrate inventory | should describe shared substrate, not retired experiments |
| `tool_lab.py` legacy-backed imports | split | native tool lab plus legacy tool lab | native tool lab cannot import `v2_runtime.py` |
| `hot_path_fastcheck.py` model-JSON replay support | split | native replay/fastcheck plus legacy diagnostics | native fastcheck cannot import legacy runtime |

## M6.24 Experimental Retirement

Production `implement_v2` should retire experimental toggles rather than keep
them as hidden defaults.

### WorkFrame Variants

Retire `workframe_variant` as a production selector. Keep one native compact
sidecar digest path derived from the authoritative native transcript, tool
result index, evidence sidecars, and closeout state. If variant comparisons
remain useful, move them under legacy diagnostics and require explicit fixture
input. Production must not import the variant registry or render variant names
into provider request inventory.

The static gate must catch WorkFrame variant usage anywhere in the production
scan root, not just obvious runtime files. In particular, `prompt.py` and
`native_workframe_projection.py` cannot be treated as harmless projection
helpers while they import `workframe_variants`,
`project_workframe_with_variant`, `reduce_workframe_with_variant`,
`DEFAULT_WORKFRAME_VARIANT`, or `CommonWorkFrameInputs`. If those modules remain
production modules, they must render from the canonical compact sidecar digest
and substrate refs only. If they still need variant comparisons, move those
functions under legacy diagnostics before enabling the production gate.

### Transition Contract And Transcript-First Variants

`transition_contract` and `transcript_first` were useful M6.24 experiments.
For M6.25 they become diagnostics only. Any useful invariant should be copied
into one of these shared, non-variant components:

- transcript pairing validation;
- compact sidecar digest;
- replay validators;
- completion blocker refs;
- route/observability records.

Do not preserve the variants as "just in case" live selectors.

### Task Contract Compiler Mixing

`task_contract_compiler` should not be interpreted in the live provider loop,
WorkFrame projection, provider-visible prompt, or planner-visible prompt.
Current `commands.py` work guidance can start the compiler and pass compiler
state through the lane input; M6.25 must remove that ambiguity before a broad
static ban is enabled.

M6.25 chooses the conversion path, not a lingering production exception:

- delete `task_contract_compiler*`, `legacy_task_contract`, and
  `task_contract_legacy` as live work-guidance/lane-config knobs in
  `commands.py`;
- if model-assisted obligation extraction is still needed, replace the old
  path with an internal `CompletionObligationIndex` compiler that writes
  sidecar refs for closeout only;
- do not store raw compiled contract JSON in `LaneInput.task_contract`,
  provider request payloads, compact sidecar provider-visible fields, prompt
  inventory, native harness state, or finish verifier planner prompts;
- allow metrics only as non-authoritative route/report fields, with no raw
  compiler payload and no effect on the native loop.

If implement closeout still needs compiled obligations, introduce a bounded
internal obligation compiler that writes proof sidecars:

```text
task_contract -> CompletionObligationIndex -> finish gate input refs
```

The provider request, compact sidecar digest, planner-visible prompt, and live
provider loop must not include raw compiler JSON or hidden acceptance details.

### Acceptance And Typed-Evidence Bridge

Old finish acceptance helpers should stop being a live bridge between model
finish claims and lane completion. Production completion consumes typed
evidence refs and closeout refs. Legacy helpers can be retained only for
diagnostic replay of old artifacts.

## Proof, Replay, And Observability Preservation

Cleanup is not allowed to weaken the artifact trail. The following artifacts
or equivalent substrate-owned records remain required for native production
runs:

- `response_transcript.json`
- `proof-manifest.json`
- `provider_requests.jsonl`
- provider request inventory sidecar
- provider response inventory sidecar
- tool result index
- evidence ref index
- route records with tool surface metadata
- rendered tool output sidecars
- native finish gate decisions
- completion resolver decisions, when resolver runs
- done candidates
- NG resume signals, when applicable
- finish verifier planner requests and decisions, when planner runs
- manifest hashes for every sidecar referenced by completion/proof decisions

Replay must be able to reconstruct:

- native transcript pairing;
- provider-visible request body hash;
- tool descriptor/profile hash;
- route table hash;
- compact sidecar digest hash;
- proof manifest sidecar refs;
- finish closeout and resolver decision refs.

Legacy artifact replay is optional. If retained, it must be a read-only
diagnostic command and must not be counted as native production evidence.

## Static Gates And Tests

The cleanup is done only when deterministic gates prove the new boundary.

### Legacy Import Absence

Extend `src/mew/implement_lane/native_validation.py` or add an equivalent
static gate that scans production paths for banned imports and symbols.

Production paths:

```text
src/mew/commands.py
src/mew/implement_lane/**
src/mew/lane_substrate/**
```

The default rule is that every Python file under `src/mew/implement_lane/**`
is production-scanned. Diagnostics are not exempt because they are "near"
production; they are exempt only after being moved to an explicit legacy or
diagnostic allowlist path. This prevents projection modules such as `prompt.py`,
`native_workframe_projection.py`, `native_sidecar_projection.py`, and
`tool_result_renderer.py` from carrying WorkFrame or raw task-contract paths
that the old narrow scan would miss.

Banned in production:

```text
run_live_json_implement_v2
JsonModelProviderAdapter
model_json_tool_loop
implement_v2_model_json_tool_loop
from .v2_runtime import
from mew.implement_lane.v2_runtime import
legacy_model_json_runtime
legacy_model_json_provider
list_v2_base_tool_specs
list_v2_tool_specs_for_mode
list_v2_tool_specs_for_task
workframe_variants
from .workframe_variants import
from mew.implement_lane.workframe_variants import
project_workframe_with_variant
reduce_workframe_with_variant
DEFAULT_WORKFRAME_VARIANT
CommonWorkFrameInputs
list_workframe_variants
workframe_variant_transition_contract
workframe_variant_transcript_first
workframe_variant_transcript_tool_nav
task_contract_compiler
task_contract_compiler_mode
task_contract_compiler_model
task_contract_compiler_timeout_seconds
task_contract_compiler_required
legacy_task_contract
task_contract_legacy
_finish_acceptance_action
_typed_acceptance_session_from_tool_results
```

Allowlist only explicit legacy diagnostic paths:

```text
src/mew/implement_lane/legacy_experiments/**
src/mew/implement_lane/legacy_model_json_*.py, until deleted
src/mew/implement_lane/legacy_model_json_tool_lab.py, until deleted
tests/fixtures/**
tests/**legacy**
scripts/**legacy**
```

The gate should scan tokens or AST where practical, not only imports, because
the dangerous state can appear as lazy package exports, string-selected
variants, work-guidance keys, or projection helper calls. `commands.py` may keep
temporary migration code only until Phase 4 closes; the Phase 4 close gate
requires zero live `task_contract_compiler*` configuration in `commands.py`
unless the code has been renamed into the internal obligation compiler and
proven not to affect provider-visible state.

### Default Native Path

Tests must prove the default `implement_v2` path uses:

- `IMPLEMENT_V2_NATIVE_RUNTIME_ID`;
- provider-native transcript and pairing;
- `tool_surface_profile_id == "codex_hot_path"`;
- `profile_default == true`;
- no provider-visible `finish`;
- internal done candidate for no-tool final assistant response;
- `native_finish_gate_decisions.jsonl` or equivalent closeout sidecar;
- `finish_verifier_planner_policy({}).enabled is True`;
- proof manifest reports `model_json_main_path_detected == False`.

### Harness Boundary

Static tests should fail if `native_tool_harness.py` defines planner or finish
giant helpers after extraction. Suggested checks:

- no class names starting with `FinishVerifierPlanner` in harness;
- no functions matching `_finish_verifier_planner_*` in harness except a single
  delegating call;
- no `_coerce_native_finish_verifier_plan*` in harness;
- no `CompletionResolverInput` construction outside a completion component;
- no old provider-visible finish handling except legacy diagnostics.

### Research Lane Substrate

Add a small test fixture that constructs a research-like lane runtime using
the shared substrate:

```text
LaneRuntimeSpec(lane_id="research_fixture", ...)
```

The fixture should expose only research-owned read/search/summarize tools and
run a fake provider transcript through pairing and proof artifact writes. The
test fails if importing the fixture imports `mew.implement_lane.native_tool_harness`,
`v2_runtime`, WorkFrame variants, or implement closeout modules.

### Replay And Observability

Replay tests must verify:

- native artifact replay still validates pairing and manifest hashes;
- route metadata includes profile, descriptor, route table, and renderer hashes;
- compact sidecar digest remains bounded and has no forbidden provider-visible
  fields;
- legacy diagnostics, if kept, are labeled `legacy_model_json` and cannot pass
  native production evidence gates.

## Phase Breakdown

### Phase 0 - Inventory And Freeze

Actions:

- run the current native validation gate;
- record production import graph for `src/mew/commands.py`,
  `src/mew/implement_lane/**`, and planned `src/mew/lane_substrate/**`;
- classify every reference to `v2_runtime.py`, `mew_legacy.py`, WorkFrame
  variants, `task_contract_compiler`, and old acceptance helpers;
- decide which legacy diagnostics are worth retaining.

Close gate:

- deletion/isolation issue list exists with file, symbol, action, owner, and
  gate;
- no code movement begins until the static gate allowlist is explicit.

### Phase 1 - Shared Substrate Skeleton

Actions:

- introduce `mew.lane_substrate` package with interfaces for native transcript,
  provider adapter, tool surface, renderer, artifact writer, observability,
  replay validation, and completion policy protocol hooks;
- move helpers that are already lane-neutral, keeping behavior equivalent;
- keep implement-specific tool specs, prompt contracts, write runtimes, and
  closeout policy in `implement_lane`.

Close gate:

- `implement_v2` still passes native validation;
- moved helpers have no import of `mew.implement_lane.v2_runtime`;
- substrate package has no import of `mew.implement_lane.native_tool_harness`.
- substrate has no concrete finish gate, planner, resolver, Terminal-Bench,
  Harbor, or coding completion semantics.

### Phase 2 - Model-JSON Deletion Or Quarantine

Actions:

- remove `run_live_json_implement_v2` from production routes and package
  exports;
- move useful helper functions out of `v2_runtime.py`;
- delete `v2_runtime.py` if possible, otherwise rename or isolate it as legacy
  diagnostics;
- isolate or delete `JsonModelProviderAdapter` and model-JSON artifact replay;
- split tool-lab and fastcheck so native diagnostics do not import legacy code.

Close gate:

- static gate finds zero model-JSON symbols in production paths;
- old model-JSON artifacts cannot pass native proof validation;
- any retained legacy command prints or records `legacy_model_json` explicitly.

### Phase 3 - Harness Responsibility Split

Actions:

- extract finish verifier planner into a component module;
- extract artifact writing into substrate artifact writer;
- extract provider request construction into provider adapter plus profile
  prompt contract;
- extract done-candidate closeout and NG resume into an implement-owned
  completion policy that implements the substrate protocol;
- leave harness as composition and loop mechanics only.

Close gate:

- harness owns provider loop, dispatch, append, and write delegation only;
- planner artifacts are byte-for-byte compatible or intentionally versioned;
- no regression in done-candidate, closeout, resolver, and NG resume sidecars.

### Phase 4 - M6.24 Experiment Retirement

Actions:

- remove production `workframe_variant` selector;
- isolate WorkFrame variant modules as legacy experiments or delete them;
- remove WorkFrame variant imports and lazy exports from `prompt.py`,
  `native_workframe_projection.py`, `hot_path_fastcheck.py`,
  `substrate_inventory.py`, and `__init__.py` before they are included in the
  broad production gate;
- move useful invariant checks into compact sidecar/replay/static gates;
- remove `transition_contract`, `transcript_first`, and
  `transcript_tool_nav` imports from production paths;
- delete live `task_contract_compiler*` work-guidance config in `commands.py`;
- replace any still-needed compiler behavior with an internal
  `CompletionObligationIndex` sidecar compiler, or delete the path if no longer
  needed.

Close gate:

- default production request does not mention WorkFrame variant names;
- production scan over `src/mew/implement_lane/**` catches zero
  `workframe_variants`, `project_workframe_with_variant`,
  `reduce_workframe_with_variant`, `DEFAULT_WORKFRAME_VARIANT`, and
  `CommonWorkFrameInputs` hits outside allowlisted legacy diagnostics;
- `commands.py` no longer passes raw `task_contract_compiler*` config or
  compiled task-contract JSON into `LaneInput`, provider-visible prompts,
  planner prompts, or native loop state;
- compact sidecar digest remains bounded and replayable;
- production completion decisions cite sidecar refs, not old WorkFrame or
  acceptance bridge state.

### Phase 5 - Lane Template Proof

Actions:

- create a research-lane fixture that uses the shared substrate without
  implement-lane imports;
- prove the fixture can build a native request, dispatch fake tools, write
  transcript/proof artifacts, and replay pairing;
- document the minimal API future lanes must implement.

Close gate:

- import gate proves `research_fixture` depends on `mew.lane_substrate` only;
- fixture proof artifacts pass shared replay;
- no copy of `native_tool_harness.py` or implement WorkFrame modules exists in
  research code.

### Phase 6 - Cleanup Lock

Actions:

- delete now-unused legacy files;
- update native validation production scan root, banned-symbol list, and
  explicit legacy allowlist;
- update package exports to expose only native/substrate production surfaces;
- archive retained diagnostics behind explicit command names.

Close gate:

- static gates pass;
- unit tests covering native default, proof, replay, observability, planner,
  finish gate, completion resolver, and research fixture pass;
- M6.24 benchmark baseline artifacts remain readable as historical artifacts,
  but only native artifacts count as production evidence.

## Implementation Readiness Checklist

- [ ] Inventory all imports of `v2_runtime.py`, model-JSON provider classes,
  `list_v2_*` symbols, WorkFrame variant modules/symbols, live
  `task_contract_compiler*` config, and old acceptance helpers.
- [ ] Add production import/token gates over `src/mew/commands.py`,
  `src/mew/implement_lane/**`, and `src/mew/lane_substrate/**` before deleting
  code.
- [ ] Define the exact `mew.lane_substrate` package API and forbid implement
  imports from it.
- [ ] Keep `CompletionPolicy` as a substrate protocol only; implement lane owns
  the concrete finish gate/planner/resolver semantics.
- [ ] Move lane-neutral transcript/provider/artifact helpers first.
- [ ] Move planner classes and helpers out of `native_tool_harness.py`.
- [ ] Move closeout decision construction into `native_finish_gate.py` or a
  dedicated implement completion policy.
- [ ] Split native diagnostics from legacy model-JSON diagnostics.
- [ ] Remove production `workframe_variant` selection and all production uses
  of `workframe_variants`, `project_workframe_with_variant`,
  `reduce_workframe_with_variant`, `DEFAULT_WORKFRAME_VARIANT`, and
  `CommonWorkFrameInputs`.
- [ ] Delete live `commands.py` `task_contract_compiler*` work-guidance config
  or replace it with an internal `CompletionObligationIndex` sidecar compiler
  that never reaches provider-visible or planner-visible state.
- [ ] Prove default implement_v2 uses native transcript, `codex_hot_path`, and
  internal closeout.
- [ ] Prove retained legacy artifacts are explicitly labeled diagnostics and
  fail production evidence gates.
- [ ] Add research-lane substrate fixture without implement-lane imports.
- [ ] Verify proof manifest, replay, route observability, planner artifacts,
  finish gate artifacts, resolver artifacts, and compact sidecar digest hashes.

## Expected End State

After M6.25 cleanup, `implement_v2` is still the coding lane, but its native
loop substrate is reusable. Implement-specific behavior lives in implement
components: patch/write/edit tools, Codex hot-path profile, coding prompt
contract, verifier selection, completion policy, and Terminal-Bench/Harbor
closeout. Shared substrate owns the native loop mechanics and proof trail.

Research lane can then be created by providing research tools, research prompt
contract, and research completion policy to the substrate. It should not fork
or copy the implement harness.
