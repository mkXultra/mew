# M6.24 Phase 0 Substrate Inventory

Status: generated phase-0 inventory.

Purpose: record the current implement_v2 substrate before the tool-harness / WorkFrame-variant rearchitecture.

## Summary

- tool registry count: `15`
- tool registry hash: `sha256:757ebf1e31fe2570b0d278c41d4bc15663f65c199b9edbe0b7f4ab31cbb23976`
- WorkFrame default variant: `transition_contract`
- WorkFrame variant count: `4`
- WorkFrame variant hash: `sha256:6c4ed21f6dd3063cb524dd99edf55561c0c75cd9eab64671a0f15f57ea1a5828`
- proof root exists: `True`
- terminal-bench JSON artifact count: `14`
- missing offline-diagnosis surfaces: `17`

## Tool Surface

| tool | access | approval | transport | native |
|---|---|---:|---|---:|
| inspect_dir | read | false | json_arguments | true |
| read_file | read | false | json_arguments | true |
| search_text | read | false | json_arguments | true |
| glob | read | false | json_arguments | true |
| git_status | read | false | json_arguments | true |
| git_diff | read | false | json_arguments | true |
| run_command | execute | true | json_arguments | true |
| run_tests | execute | true | json_arguments | true |
| poll_command | execute | false | json_arguments | true |
| cancel_command | execute | false | json_arguments | true |
| read_command_output | execute | false | json_arguments | true |
| write_file | write | true | json_arguments | true |
| edit_file | write | true | json_arguments | true |
| apply_patch | write | true | json_line_array | true |
| finish | finish | false | json_arguments | true |

## WorkFrame Variants

| variant | description |
|---|---|
| `current` | Current M6.24 WorkFrame reducer behavior. |
| `minimal` | Thin WorkFrame reducer that preserves finish and verifier safety gates. |
| `transcript_first` | Prefers fresh paired transcript/tool evidence over stale prompt-projection fallback. |
| `transition_contract` | Adds a compact reducer-owned transition contract when fresh observations change state. |

## Shared Substrate Surfaces

| surface | phase | status | current source | notes |
|---|---:|---|---|---|
| paired_tool_call_result_contract | 1 | partial | `src/mew/implement_lane/v2_runtime.py` | ToolResultEnvelope pairing exists; Phase 1 still needs explicit invariant artifacts. |
| natural_transcript_tool_results | 1 | partial | `src/mew/implement_lane/v2_runtime.py` | Provider-visible tool result projection exists; shared transcript-first harness is not frozen. |
| typed_evidence_sidecars | 2 | partial | `src/mew/implement_lane/execution_evidence.py` | Typed acceptance/evidence records exist; hot-path index files are not yet canonical artifacts. |
| artifact_obligations | 2 | partial | `src/mew/implement_lane/hot_path_fastcheck.py` | Finish/obligation checks exist in fastcheck fixtures; shared obligation sidecar is not frozen. |
| verifier_freshness | 2 | partial | `src/mew/implement_lane/workframe.py` | WorkFrame verifier state exists; canonical sidecar/index split is still pending. |
| repair_loop_sidecars | 2 | legacy_present | `src/mew/implement_lane/prompt.py` | Prompt projection recovery exists; redesign should demote this to sidecar-derived state. |
| workframe_variant_projection | 3 | partial | `src/mew/implement_lane/workframe_variants.py` | Variant registry exists; CommonWorkFrameInputs wrapper and projection contract are pending. |
| transcript_tool_nav | 4 | missing | `-` | Target variant is design-only until Phase 4. |

## WorkFrameInputs Compatibility Fields

| field | type | default |
|---|---|---|
| `attempt_id` | `str` | `<required>` |
| `turn_id` | `str` | `<required>` |
| `task_id` | `str` | `<required>` |
| `objective` | `str` | `<required>` |
| `success_contract_ref` | `str` | `''` |
| `constraints` | `tuple[str, ...]` | `()` |
| `sidecar_events` | `tuple[dict[str, object], ...]` | `()` |
| `prompt_inventory` | `tuple[dict[str, object], ...]` | `()` |
| `baseline_metrics` | `dict[str, object]` | `<factory>` |
| `previous_workframe_hash` | `str` | `''` |
| `workspace_root` | `str` | `''` |
| `artifact_root` | `str` | `''` |
| `schema_version` | `int` | `1` |

## Missing For Offline Diagnosis

- `tool registry artifact` (`tool_registry.json`): required shared artifact is not present in current proof artifacts (phase 1)
- `tool policy artifact` (`tool_policy_index.json`): required shared artifact is not present in current proof artifacts (phase 1)
- `natural transcript log` (`natural_transcript.jsonl`): required shared artifact is not present in current proof artifacts (phase 1)
- `tool result log` (`tool_results.jsonl`): required shared artifact is not present in current proof artifacts (phase 1)
- `tool result index` (`tool_result_index.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `model turn index` (`model_turn_index.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `evidence ref index` (`evidence_ref_index.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `typed evidence delta` (`typed_evidence_delta.jsonl`): required shared artifact is not present in current proof artifacts (phase 2)
- `artifact obligation index` (`artifact_obligation_index.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `verifier freshness sidecar` (`verifier_freshness.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `repair loop state sidecar` (`repair_loop_state.json`): required shared artifact is not present in current proof artifacts (phase 2)
- `replay manifest` (`replay_manifest.json`): required shared artifact is not present in current proof artifacts (phase 6)
- `provider request inventory` (`provider_request_inventory.json`): required shared artifact is not present in current proof artifacts (phase 6)
- `provider response inventory` (`provider_response_inventory.json`): required shared artifact is not present in current proof artifacts (phase 6)
- `WorkFrame diff artifact` (`workframe_diff.json`): required shared artifact is not present in current proof artifacts (phase 6)
- `CommonWorkFrameInputs source type` (`src/mew/implement_lane/common_workframe_inputs.py`): current code still uses WorkFrameInputs directly; CommonWorkFrameInputs v1 wrapper is design-only (phase 3)
- `transcript_tool_nav variant` (`src/mew/implement_lane/workframe_variant_transcript_tool_nav.py`): target variant is design-only and not registered yet (phase 4)

## Migration Notes

- Current WorkFrameInputs remains the source compatibility surface for existing reducers.
- CommonWorkFrameInputs v1 should wrap current WorkFrameInputs plus tool registry, sidecars, indexes, and migration metadata.
- WorkFrame projection schema v3 is the target projection schema; it is distinct from CommonWorkFrameInputs schema v1.
- Variant projections must canonicalize CommonWorkFrameInputs before hashing or rendering.
- v1/v2 fixtures must be compared within their original schema or explicitly converted before v3 hash comparison.
