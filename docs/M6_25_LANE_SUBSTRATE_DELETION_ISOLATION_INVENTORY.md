# M6.25 Lane Substrate Deletion And Isolation Inventory

Status: Phase 0/1 implementation-facing inventory for Run #1.

Scope: production import boundaries for `src/mew/commands.py`,
`src/mew/implement_lane/**`, and `src/mew/lane_substrate/**`.

This inventory freezes known cleanup debt without deleting or quarantining it
in Run #1. Later phases should remove entries from the native validation
allowlist as each row is completed.

## Production Import Boundary Snapshot

Run #1 freezes this import boundary:

| Root | Current production role | Boundary rule |
|---|---|---|
| `src/mew/commands.py` | CLI composition and implement_v2 route selection | may call native implement-lane entrypoints; must not route to model-json runtime |
| `src/mew/implement_lane/**` | implement_v2 lane-owned runtime, tools, prompt contracts, and completion policy | may own coding-specific semantics; known legacy symbols require explicit static-gate allowlist entries until later phases remove them |
| `src/mew/lane_substrate/**` | shared native runtime interfaces and lane-neutral contracts | must not import implement native harness, `v2_runtime`, WorkFrame variants, concrete finish gate/planner/resolver, Terminal-Bench, Harbor, or coding completion semantics |

No Run #1 code path imports `mew.lane_substrate` from production hot-path
runtime code yet; this is deliberate. The package is available as a stable
interface skeleton for later extraction without changing implement_v2 behavior.

| File or symbol | Current location | Action | Owner | Gate |
|---|---|---|---|---|
| `run_live_json_implement_v2` | `src/mew/implement_lane/v2_runtime.py`, `legacy_model_json_runtime.py` | delete or isolate | Phase 2 model-json quarantine | no production import, package export, CLI route, or proof manifest runtime id |
| `implement_v2_model_json_tool_loop` / `model_json_tool_loop` | `v2_runtime.py`, `native_transcript.py`, validation fixtures | delete or isolate compatibility | Phase 2 model-json quarantine | native validation rejects model-json runtime ids and compatibility leaves hot path |
| `JsonModelProviderAdapter` | `legacy_model_json_provider.py`, `v2_runtime.py` | isolate or delete | Phase 2 model-json quarantine | no production import from commands, registry, native harness, provider adapter, or package surface |
| `legacy_model_json_runtime.py` / `legacy_model_json_provider.py` / `legacy_model_json_tool_lab.py` | `src/mew/implement_lane/` | move under explicit legacy diagnostics or delete | Phase 2 model-json quarantine | static gate allowlist entry removed |
| `v2_runtime.py` | `src/mew/implement_lane/v2_runtime.py` | split useful helpers, then isolate or delete | Phase 2 model-json quarantine | no native production import; no package export; no model-json evidence accepted |
| `list_v2_base_tool_specs`, `list_v2_tool_specs_for_mode`, `list_v2_tool_specs_for_task` | `tool_profiles/mew_legacy.py`, `v2_runtime.py` | isolate or delete | Phase 2 tool profile quarantine | default tool surface remains `codex_hot_path`; legacy profile explicit diagnostics only |
| WorkFrame variant registry and selectors | `workframe_variants.py`, `workframe_variant*.py`, package exports | isolate or delete | Phase 4 WorkFrame retirement | production scan has no `workframe_variants`, `project_workframe_with_variant`, `reduce_workframe_with_variant`, `DEFAULT_WORKFRAME_VARIANT`, `CommonWorkFrameInputs`, or `list_workframe_variants` |
| WorkFrame variant users | `prompt.py`, `native_workframe_projection.py`, `hot_path_fastcheck.py`, `substrate_inventory.py` | replace or split diagnostics | Phase 4 WorkFrame retirement | provider-visible prompt and native projection consume canonical compact sidecar refs only |
| `task_contract_compiler*`, `legacy_task_contract`, `task_contract_legacy` | `commands.py`, `execution_evidence.py`, `finish_acceptance_helpers.py`, native harness string handling | rename into internal obligation compiler or remove | Phase 4 task-contract migration | commands no longer passes raw compiled contract into `LaneInput.task_contract`, provider payloads, prompt rendering, native loop, or planner prompt |
| `_finish_acceptance_action`, `_typed_acceptance_session_from_tool_results` | `finish_acceptance_helpers.py`, `native_tool_harness.py`, `v2_runtime.py` | split into internal closeout or isolate old bridge | Phase 3 completion extraction | native harness delegates completion through `CompletionPolicyProtocol` and does not call old acceptance bridge directly |
| Native harness planner helpers | `native_tool_harness.py` | move behind lane-owned completion component | Phase 3 completion extraction | static harness-boundary tests reject planner classes and giant helper definitions in harness |
| Native harness artifact and provider request helpers | `native_tool_harness.py` | move lane-neutral pieces into substrate writer/adapter | Phase 1/3 substrate extraction | response transcript, request/response inventories, route records, and proof manifest hashes are unchanged |
| `history_json:`, `frontier_state_update` legacy projection fields | `v2_runtime.py`, plus current guard/report/fastcheck modules that name the forbidden fields | remove from production-visible projection paths; keep only semantic guards or isolated diagnostics | Phase 2/4 model-json and projection cleanup | static gate fails unallowlisted occurrences and reports current temporary debt under `allowed_legacy_hits` |
| `substrate_inventory.py` M6.24 content | `src/mew/implement_lane/substrate_inventory.py` | rewrite or isolate | Phase 0/1 inventory refresh | M6.25 inventory describes shared substrate and cleanup gates, not retired experiment status |
| `mew.lane_substrate` interfaces | `src/mew/lane_substrate/` | keep interface/protocol/dataclass only | Phase 1 shared substrate skeleton | imports no native harness, `v2_runtime`, finish gate, planner, resolver, Terminal-Bench, Harbor, or coding completion semantics |

Run #1 static gate state:

- `validate_native_loop_gate()` recursively scans `src/mew/commands.py`,
  `src/mew/implement_lane/**/*.py`, and `src/mew/lane_substrate/**/*.py`.
- Known current debt is recorded as explicit path-pattern plus symbol
  allowlist entries in `native_validation.py`.
- Unallowlisted banned symbols fail the native validation gate.
- Allowed hits are reported separately as inventory data; they are not treated
  as production cleanup.
