# M6.24 Command/Edit Boundary Deletion Map - 2026-05-13

Purpose: Phase 0 anti-drift artifact for
`docs/DESIGN_2026-05-13_M6_24_COMMAND_EDIT_BOUNDARY_REDESIGN.md`.

This map freezes the old broad shell mutation classifier surface so later
phases delete, quarantine, or narrow it instead of polishing it further. It is
not a runtime behavior change.

## Baseline

- Active controller: `m6_24_command_edit_boundary_redesign_phase_0_1`
- Baseline status: broad regex/shlex source mutation inference still exists in
  live code and must not receive new polish work.
- Replacement direction:
  - execute-route tools are process runners;
  - source mutation uses typed write/edit/patch tools;
  - parser metadata is conservative helper data only;
  - process side effects are observed through source snapshot/diff refs.

## Deletion / Quarantine Map

| Current entry point | Current risk | Phase 6 action | Replacement | Test gate |
| --- | --- | --- | --- | --- |
| `src/mew/implement_lane/exec_runtime.py::_run_tests_source_mutation_misuse` | `run_tests` infers source writes from shell text | quarantine/delete from live native route | `invalid_tool_contract` for explicit verifier/source-write contract misuse plus typed mutation tools | live route test proves `run_tests` no longer calls this helper |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_mutation_verifier_compound_misuse` | `run_command` verifier path infers shell source writes | quarantine/delete from live native route | process-runner route plus observer finish block | verifier command with source side effect is handled by observer refs, not shell text inference |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_patch_misuse` | classifies shell text as source patch | replace | bridge registry miss or exact `shell_invoked_apply_patch` bridge | shell-invoked apply_patch is the only bootstrap bridge |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_creation_shell_surface_misuse` | broad source creation detection in `run_command` | quarantine/delete from live native route | narrow `invalid_tool_contract` only for declared/edit-shaped execute misuse | unrecognized shell writes remain process-runner side effects observed after execution |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_exploration_shell_surface_misuse` | shell surface can become a read/write classifier | narrow/delete | read/search/list display metadata only | tests prove read/search/list hints do not bypass approval or sandbox |
| `src/mew/implement_lane/exec_runtime.py::_source_like_mutation_paths` and shell write-path helpers | broad regex/shlex source mutation classifier | quarantine/delete from live native route except exact bridge internals | source snapshot/diff observer and bridge registry | tests fail if live routes call deleted helpers |
| `src/mew/implement_lane/v2_runtime.py::_is_deep_runtime_prewrite_source_mutation_attempt` | prewrite behavior tied to inferred shell source mutation | delete/quarantine from live native route | typed mutation route metrics and route decisions | live native route test proves no call |
| `src/mew/implement_lane/v2_runtime.py::_shell_command_may_mutate_source_tree` and shell write-path helpers | duplicate broad shell mutation classifier | delete/quarantine from live native route | parser metadata plus observer | live native route test proves no call |
| `src/mew/implement_lane/v2_runtime.py::_source_patch_shell_repair_from_result` | repair loop can preserve shell-as-edit semantics | replace | narrow `invalid_tool_contract` recovery hint or bridge registry result | recovery cards cite typed mutation tools, not inferred shell edit |
| `src/mew/implement_lane/v2_runtime.py::_unaccounted_source_tree_mutation_block` | blocker may depend on shell text inference | keep only as observer consumer | terminal source side-effect refs from Phase 4 | tests prove it consumes artifact refs, not shell text |

## Prompt / Tool Spec Surfaces To Watch

- `src/mew/implement_lane/tool_policy.py`
  - `run_command` and `run_tests` descriptions must stay process-runner oriented.
  - `write_file`, `edit_file`, and `apply_patch` must remain the source
    mutation route.
- `src/mew/implement_lane/prompt.py`
  - implementation-lane prompts must not recommend shell writes as a normal
    source mutation path.
- `src/mew/tool_kernel.py`
  - shared tool execution should emit route metadata without turning route
    metadata into a shell mutation classifier.

## Phase 0 Close Gate

- This document names the old classifier entry points and their replacements.
- Baseline classifier-dependent areas are explicit and searchable.
- Later Phase 6 work must update this document or a successor closeout note
  with the final action for each row.
- No runtime behavior changes are authorized by this document alone.
