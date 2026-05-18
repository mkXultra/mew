# Design 2026-05-17 - M6.24 Tool Profile Developer Message

Status: design only. No production code is authorized by this document.

Scope: `implement_v2` / `codex_hot_path` request construction for a
Codex CLI compliant provider-visible surface where one selected
`ToolSurfaceProfile` owns both the provider-visible tool schema and the
corresponding model-visible tool behavior contract. This is a pre-release
design; backward compatibility is not required.

## Decision

This is not merely adding more prompt text. For the OpenAI/Codex path, the
request input must include a `role=developer` message that carries the selected
profile's tool behavior contract. The existing `request_body.instructions`
field may still carry base instructions, but the `codex_hot_path` edit/command
contract must be a developer-role input item, not only text folded into
`instructions`.

`ToolSurfaceProfile` must own these as one unit:

- provider-visible tool names, descriptions, schemas, ordering, strict/custom
  lowering policy, and descriptor hashes;
- the `role=developer` tool behavior contract that explains how those exact
  tools are to be used;
- the profile metadata that proves both came from the same profile snapshot.

For `codex_hot_path`, the developer message must make at least these rules
model-visible:

- manual source edits use `apply_patch`;
- `exec_command` is for inspection, builds, tests, probes, package-manager
  setup, and verification;
- do not author source changes through shell heredoc, `cat`, `printf`, or
  equivalent shell text-generation/editing tricks;
- shell commands may create build outputs and run probes, but shell is not the
  manual source editing API.

If a provider cannot directly handle a `role=developer` input message, the only
fallback is to fold the same contract text into provider instructions and
record that fallback explicitly. The OpenAI/Codex implementation path must not
take that fallback.

`mew_legacy` remains a separate profile. It either keeps its existing behavior
or gets its own separate legacy developer contract. It must not reuse, merge,
or partially inherit the `codex_hot_path` contract.

The design preserves current observability, provider-native transcript
artifacts, one-output-per-tool-call pairing, and internalized finish gate
behavior. The change is the transport and ownership of profile tool behavior,
not a reintroduction of provider-visible `finish` or evidence bookkeeping.

## Context Checked

Required review/context files:

- `docs/REVIEW_2026-05-17_M6_24_PROMPT_COMPLETION_PRESSURE_COMPARE.md`
  records that the `make-doom-for-mips` failure path used `exec_command` with
  `cat > /app/doomgeneric_mips.c <<'EOF'`, used `apply_patch` zero times, and
  then completed through a provider-visible `finish` path. It also records the
  Codex reference trace using `apply_patch` 13 times and no `finish` tool.
- `docs/DESIGN_2026-05-14_M6_24_TOOL_REGISTRY_AND_CODEX_HOT_PATH.md`
  already defines `ToolRegistry` / `ToolSurfaceProfile`, the `codex_hot_path`
  tool list (`apply_patch`, `exec_command`, `write_stdin`, optional
  `list_dir`), profile-owned descriptors and prompt contracts, sidecar-only
  finish state, A/B observability, and Phase 6 profile ownership.
- `src/mew/implement_lane/tool_profiles/codex_hot_path.py` currently owns the
  `codex_hot_path` tool specs and prompt sections. Its current coding contract
  says to use `apply_patch` for source changes and `exec_command` for builds,
  tests, probes, package setup, and verification, but it is rendered as normal
  instructions rather than a `role=developer` input item.
- `src/mew/implement_lane/tool_registry.py` defines `ToolSurfaceProfile`,
  `ToolSurfaceSnapshot`, `provider_tool_names`, descriptor/route/render hashes,
  and profile selection between `mew_legacy` and `codex_hot_path`.
- `src/mew/implement_lane/tool_profiles/mew_legacy.py` owns the legacy tool
  specs and legacy prompt sections. It includes legacy names such as
  `run_command`, `run_tests`, read tools, and legacy finish behavior.
- `src/mew/implement_lane/tool_profiles/prompt_contracts.py` is the current
  narrow catalog from profile id and prompt contract id to prompt sections.
- `src/mew/implement_lane/prompt.py` assembles provider-neutral prompt
  sections from the selected tool surface and currently renders them through
  `render_prompt_sections()`.
- `src/mew/implement_lane/native_tool_harness.py` builds request descriptors in
  `_request_descriptor()`, currently calls `_native_instructions()` for the
  rendered profile prompt text, and builds input items through
  `_responses_input_items()`. For `codex_hot_path`, the first input item is
  currently the raw user task.
- `src/mew/implement_lane/native_provider_adapter.py` builds the Responses
  request body with `instructions`, `input`, `tools`, `tool_choice`,
  `parallel_tool_calls`, streaming, and local storage settings. It also
  implements `previous_response_id` delta mode.
- `src/mew/implement_lane/native_transcript.py`,
  `src/mew/implement_lane/tool_result_renderer.py`, and
  `src/mew/implement_lane/tool_routes.py` preserve native transcript pairing,
  profile rendering, and sidecar route records.
- `docs/DESIGN_2026-05-17_M6_24_INTERNAL_FINISH_GATE.md` defines the desired
  no-provider-visible-finish shape: normal assistant final response,
  controller-side done candidate, internal finish gate, and NG continue/return.

Codex CLI reference files checked:

- `references/fresh-cli/codex/codex-rs/config/src/config_toml.rs` defines
  `developer_instructions` as instructions inserted as a `developer` role
  message.
- `references/fresh-cli/codex/codex-rs/core/src/session/mod.rs`
  `build_initial_context()` aggregates permission, configured developer,
  memory, app, skill, plugin, realtime, and other developer sections, then
  emits them through `build_developer_update_item()`.
- `references/fresh-cli/codex/codex-rs/core/src/context_manager/updates.rs`
  `build_developer_update_item()` builds a message with role `developer`.
- `references/fresh-cli/codex/codex-rs/protocol/src/models.rs` defines
  `ResponseInputItem::Message { role, content }` and `BaseInstructions`, whose
  text corresponds to the Responses API `instructions` field.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs` builds a
  prompt from `input`, `router.model_visible_specs()`, and `base_instructions`.
- `references/fresh-cli/codex/codex-rs/core/src/client.rs` sends
  `prompt.base_instructions.text` as request `instructions`, formatted input
  as request `input`, and tool specs as request `tools`.
- `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs` defines
  provider-visible `exec_command` and `write_stdin` descriptors.
- `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs` defines
  the provider-visible freeform `apply_patch` descriptor.
- `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs`
  registers unified exec, `write_stdin`, `apply_patch`, and optional
  `list_dir` tool specs, but not a provider-visible finish tool for the normal
  Codex coding surface.

## Relationship To 2026-05-14 Design

This document extends, rather than replaces,
`docs/DESIGN_2026-05-14_M6_24_TOOL_REGISTRY_AND_CODEX_HOT_PATH.md`.

The 2026-05-14 design already made the selected `ToolSurfaceProfile` the owner
of provider-visible descriptors, renderer labels, route metadata, and prompt
contract sections. That remains correct. The missing piece is the transport
boundary: for OpenAI/Codex, the profile prompt contract must be emitted as a
`role=developer` input message, matching the Codex CLI reference shape, instead
of living only in `request_body.instructions`.

Treat this as a Phase 6D refinement before any default-switch evidence is
accepted:

```text
Phase 6D: Profile-Owned Developer Message Contract
  selected ToolSurfaceProfile
    -> provider-visible tool descriptors
    -> same-profile developer tool behavior contract
    -> OpenAI/Codex request input contains role=developer
```

The tool list, renderer policy, A/B design, resident-internal finish gate, and
`mew_legacy` A/B role from the 2026-05-14 design stay intact. The sub-phases
below are numbered `Phase 6D.0` through `Phase 6D.5` so they do not collide
with the existing 2026-05-14 Phase 0-5 plan. `Phase 6D.5` is an additional
developer-role recheck against the existing 2026-05-14 Phase 5 default-switch
gate; it does not replace or weaken that gate.

## Problem

The current profile-owned prompt work is only partial for Codex compatibility.
The selected profile owns text, but `native_tool_harness._native_instructions()`
renders that text into `request_body.instructions`. The OpenAI/Codex reference
has a distinct layering:

```text
base instructions
  -> Responses instructions field

developer instructions
  -> role=developer input message from build_initial_context()

tool schema
  -> Responses tools from router.model_visible_specs()
```

Mew currently has:

```text
profile prompt sections
  -> rendered into request_body.instructions

user task / transcript items
  -> request_body.input

tool schema
  -> request_body.tools from ToolSurfaceSnapshot.tool_specs
```

That means `codex_hot_path` can expose Codex-like tool names while the behavior
contract is not represented at the same provider role as Codex CLI developer
instructions. It also means the request artifacts cannot prove that the tool
schema and behavior contract came from the same profile snapshot.

The observed `make-doom-for-mips` failure makes this concrete. The model used
`exec_command` as a source authoring API via shell heredoc and generated a
synthetic source/artifact path. The fix must bind the shell/edit boundary to
the same profile that exposes `apply_patch` and `exec_command`; otherwise the
tool surface and behavior contract can drift independently.

## Codex CLI To Mew Mapping

| Codex CLI reference concept | Reference location | Mew concept / target |
| --- | --- | --- |
| `BaseInstructions` text | `protocol/src/models.rs`, `core/src/session/mod.rs`, `core/src/client.rs` | `request_body.instructions`; after this design, it must not be the only carrier of `codex_hot_path` tool behavior on OpenAI/Codex. |
| `developer_instructions` config | `config/src/config_toml.rs` | `DeveloperToolBehaviorContract` selected by `ToolSurfaceProfile`, not a central prompt string. |
| `build_initial_context()` | `core/src/session/mod.rs` | mew request context assembly in `native_tool_harness._request_descriptor()` / `_responses_input_items()`. |
| `build_developer_update_item()` | `core/src/context_manager/updates.rs` | proposed `build_profile_developer_input_item()` or equivalent helper producing `{"role": "developer", "content": ...}`. |
| contextual user/environment items | `core/src/session/mod.rs` | existing `role=user` task input and future safe context refresh items. `codex_hot_path` keeps raw task first after the developer item and avoids raw `task_contract`. |
| `router.model_visible_specs()` | `core/src/session/turn.rs` | `ToolSurfaceSnapshot.tool_specs` selected by `tool_registry.py`. |
| `create_tools_json_for_responses_api()` | `tools/src/tool_spec.rs` | `native_tool_schema.lower_implement_lane_tool_specs()` and `provider_tool_specs()`. |
| `create_apply_patch_freeform_tool()` | `tools/src/apply_patch_tool.rs` | `codex_hot_path.py` `apply_patch` spec and provider-native freeform lowering. |
| `create_exec_command_tool()` / `create_write_stdin_tool()` | `tools/src/local_tool.rs` | `codex_hot_path.py` `exec_command` / `write_stdin` specs and adapters to managed exec. |
| normal Codex completion | absence of provider-visible finish in tool registry and traces | mew internal finish gate over normal assistant final response; no `finish` descriptor in `codex_hot_path`. |
| Responses request `input`, `instructions`, `tools` | `core/src/client.rs`, `codex-api/src/common.rs` | `native_provider_adapter.build_responses_request_descriptor()` with `role=developer` in `input`, base instructions in `instructions`, and same-profile tools in `tools`. |

## Proposed Mew-Side Types

Exact Python names may vary, but the implementation should introduce these
mew-side concepts.

```text
ToolSurfaceProfile
  profile_id
  profile_version
  provider_tool_specs
  provider_tool_names
  prompt_contract_id
  developer_contract_id
  developer_contract_version
  developer_contract_sections
  developer_contract_hash
  developer_contract_transport_policy
  render_policy_id
  default_parallel_tool_calls
  interactive_stdin
  profile_hash
```

```text
DeveloperToolBehaviorContract
  profile_id
  profile_version
  contract_id
  contract_version
  role: developer
  provider_tool_names
  content_sections
  rendered_text
  content_hash
  transport_policy:
    preferred: role_developer_input
    fallback: instructions_folded_only_when_provider_lacks_developer_role
  forbidden_provider_visible_terms
  required_provider_visible_phrases
```

```text
ToolSurfaceSnapshot additions
  developer_contract_id
  developer_contract_version
  developer_contract_hash
  developer_contract_transport_policy
  developer_contract_provider_tool_names
  developer_contract_wire_visible
  developer_contract_transport
  developer_contract_fallback_reason
```

The `profile_hash` must cover both descriptor/spec identity and developer
contract identity. A profile hash that changes for tool descriptors but not for
developer contract, or vice versa, is incomplete.

The developer contract must list the provider tool names it describes. For
`codex_hot_path`, that list must match `ToolSurfaceSnapshot.provider_tool_names`
after explicit options such as `enable_list_dir` are applied.

## Request Construction

For OpenAI/Codex providers, the request body must have this shape:

```json
{
  "instructions": "<base instructions only, or profile-independent lane base>",
  "input": [
    {
      "role": "developer",
      "content": [
        {
          "type": "input_text",
          "text": "<rendered codex_hot_path developer contract>"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "<raw task text for codex_hot_path>"
        }
      ]
    }
  ],
  "tools": ["<lowered tools from the same ToolSurfaceSnapshot>"]
}
```

Implementation impact:

- `src/mew/implement_lane/tool_profiles/codex_hot_path.py` should expose a
  profile-owned developer contract builder alongside `codex_hot_path_tool_specs()`.
- `src/mew/implement_lane/tool_profiles/mew_legacy.py` should not import or
  reuse the `codex_hot_path` contract. If legacy keeps its current behavior, it
  can continue to render its legacy prompt through existing mechanisms until a
  separate legacy contract is designed.
- `src/mew/implement_lane/tool_profiles/prompt_contracts.py` should become, or
  be paired with, a profile contract catalog that returns both prompt/base
  sections and developer contract sections from the selected profile id and
  contract id.
- `src/mew/implement_lane/tool_registry.py` should include developer contract
  identity in `ToolSurfaceProfile` and `ToolSurfaceSnapshot`.
- `src/mew/implement_lane/prompt.py` should stop being the place where
  `codex_hot_path` tool behavior is converted only into request instructions.
  It may keep profile-independent lane base rendering, but profile-specific
  tool behavior must come from the selected profile as a developer contract.
- `src/mew/implement_lane/native_tool_harness.py` should build profile
  developer input items before task input items. For `codex_hot_path`, the raw
  task remains a user message and no raw `task_contract` appears in the hot
  path input.
- `src/mew/implement_lane/native_provider_adapter.py` should accept the
  already-assembled input items and record whether the developer contract was
  wire-visible as a `role=developer` message or folded into instructions.
- `previous_response_id` developer refresh is explicitly **deferred** for this
  implementation slice. Today, when the websocket / previous-response path is
  lost, mew does not have a full retry / full replay fallback that can continue
  the same loop. Because neither continuation path is ready, developer refresh
  is not a current close-gate requirement. The current requirement is only that
  every full or normal OpenAI/Codex `codex_hot_path` request includes the
  profile developer contract as a `role=developer` input item.

Future continuation rule:

- If `previous_response_id` delta mode is made reliable later, the continuation
  request must keep the current profile developer contract wire-visible as
  `role=developer` whenever the provider request would otherwise hide it in a
  matched prefix.
- If a full retry / full replay fallback is added later, the reconstructed full
  request must include the same `role=developer` contract before the raw task and
  transcript/tool-output context.
- A future refresh item must not be `role=user`, hash-only, contract-id-only, or
  a terse "same as before" pointer. It must restate the normative tool behavior
  rules, including the `apply_patch` manual-edit rule and shell non-authoring
  boundary.
- Future inventory fields may include `previous_response_developer_refresh`,
  `previous_response_developer_refresh_reason`,
  `developer_contract_refresh_hash`, and `developer_contract_refresh_text_kind`,
  but these fields are out of scope for the current M6.24 implementation.

Provider capability handling:

```text
supports_developer_role_input=true and provider=openai/codex
  -> request_body.input includes role=developer
  -> developer_contract_transport=role_developer_input

supports_developer_role_input=false
  -> fold same rendered contract into request_body.instructions
  -> developer_contract_transport=instructions_folded
  -> developer_contract_fallback_reason=provider_lacks_developer_role
```

No other fallback is allowed. Do not split the contract across both locations
for the same request unless a transition fixture explicitly proves that the
provider requires duplication; duplication is not the default design.

## `codex_hot_path` Developer Contract

The `codex_hot_path` profile developer message should be short and operational.
It should not mention WorkFrame, proof manifests, finish gates, evidence refs,
or task-specific closeout pressure.

Minimum content:

```text
You are working through the codex_hot_path tool surface.

Use apply_patch for manual source edits.

Use exec_command for inspection, builds, tests, probes, package-manager setup,
and verification.

Do not create or edit source files with shell heredocs, cat, printf, sed -i,
perl -pi, Python file-writing scripts, or equivalent shell text-generation
shortcuts. Shell commands may create build outputs, run tools, install packages
when permitted, and inspect files, but shell is not the manual source editing
API.

Use write_stdin only to poll or interact with an existing exec_command session
according to the profile's interactive-stdin capability.
```

If optional `list_dir` is enabled, the same contract may add one sentence:

```text
Use list_dir only for bounded directory listings; use exec_command for normal
terminal inspection when shell access is available.
```

The contract must not include:

- `finish`, `final_status`, `summary`, `evidence_refs`, `task_done`, or
  acceptance schema language;
- `run_tests`, `run_command`, `read_file`, `search_text`, `glob`, or
  `inspect_dir` as available hot-path commands unless that exact tool is
  provider-visible in the selected profile;
- WorkFrame, `next_action`, `required_next`, first-write pressure, proof
  projection, or hidden sidecar state;
- benchmark-specific MIPS, Doom, VM, `/tmp/frame.bmp`, or Terminal-Bench
  instructions.

## `mew_legacy` Separation

`mew_legacy` is a different profile with different provider-visible tools and
different behavior. It keeps existing behavior unless a later explicit legacy
design gives it its own developer-role contract.

Close rules:

- A `mew_legacy` request must not include `codex_hot_path_developer_contract_v1`.
- A `codex_hot_path` request must not include legacy tool behavior text such as
  "use run_command or run_tests" unless those provider-visible names are
  intentionally added to that profile, which this design does not do.
- Profile hashes and request inventory must make it impossible to combine
  `mew_legacy` tools with a `codex_hot_path` developer contract without failing
  tests.

## Observability And Artifacts

Current artifacts stay. The new fields are additive and profile-aware.

Required additions:

- `native-provider-requests.json` and `provider_request_inventory.json` record
  `developer_contract_id`, `developer_contract_hash`,
  `developer_contract_transport`, `developer_contract_wire_visible`,
  and `developer_contract_fallback_reason`.
- `provider_request_inventory.model_visible_sections` distinguishes
  `profile_developer_contract`, `raw_task`, `native_transcript_delta`, and
  any `task_context_refresh`.
- `tool_surface` metadata includes the developer contract fields next to
  `profile_id`, `descriptor_hash`, `route_table_hash`, `render_policy_hash`,
  and `prompt_contract_id`.
- The forbidden-field scan includes the developer message text. For
  `codex_hot_path`, scans must fail on provider-visible finish/evidence,
  WorkFrame, proof, next-action, first-write, or sidecar-control text.
- `tool_routes.jsonl` continues to record declared tool, internal kernel,
  profile id/hash, descriptor hash, and route table hash. It does not receive
  developer contract text.
- `tool_render_outputs.jsonl` and renderer metrics stay unchanged except for
  profile hashes if the profile hash now covers developer contract identity.
- `response_transcript.json` remains the source of truth for provider outputs
  and tool-call/tool-output pairing. The profile developer message is request
  context, not a tool call and not a transcript pairing participant.
- Internal finish gate artifacts, done candidates, `CompletionResolver`
  diagnostics, verifier closeout, proof manifests, source snapshots, and replay
  artifacts remain sidecar-only.

The provider-visible request body is the primary acceptance artifact for this
design: reviewers must be able to inspect it and see a `role=developer` item
for OpenAI/Codex `codex_hot_path`.

## Make-Doom-For-Mips Synthetic Artifact Mitigation

This design is a general tool-boundary repair, not a task-specific
`make-doom-for-mips` heuristic. The mitigation is to make the edit boundary
provider-visible at developer-role strength and then watch whether the model
stops using shell as a source authoring API.

Watch these observability indicators in `make-doom-for-mips` and the fixed A/B
set:

- `native-provider-requests.json`: `codex_hot_path` request contains
  `role=developer`, `developer_contract_transport=role_developer_input`, and
  no provider-visible `finish` or `evidence_refs` schema.
- `request_body.tools`: only `apply_patch`, `exec_command`, `write_stdin`,
  plus optional explicit `list_dir`.
- `response_items.jsonl`: `apply_patch` call count is greater than zero on
  source-changing attempts; no `finish` call appears in `codex_hot_path`.
- `tool_routes.jsonl`: source mutation routes come from `apply_patch`; shell
  commands that look like `cat > *.c`, heredoc, `printf > source`, `sed -i`,
  or Python write scripts are flagged as command-edit-boundary violations.
- source mutation evidence: source changes have typed mutation refs from the
  write runtime, not only an executable artifact created by shell.
- first-write metrics: first write occurs through `apply_patch`, with reduced
  probe count before first source mutation compared with legacy.
- edit/verify/repair cadence: failed verifier output is followed by another
  `apply_patch` when source changes are needed, not by overwriting a generated
  standalone file through shell.
- artifact/source consistency: `/app/doomgeneric_mips` and `/tmp/frame.bmp`
  existence are not accepted as sufficient if no source mutation evidence
  ties the artifact back to provided source or an allowed patch.
- renderer metrics: terminal output remains compact and does not foreground
  evidence refs or proof sidecars as model-visible completion objectives.
- internal finish gate: OK/NG decisions remain keyed to done-candidate/internal
  gate artifacts, not provider-visible finish arguments.

If a trace still uses `exec_command` to author source, the failure should be
classified as a command-edit-boundary violation in the A/B report even if the
external reward happens to pass.

## Phase Split

### Phase 6D.0 - Static Contract Fixture

Add profile-owned developer contract fixtures without changing live behavior.

Close gate:

- `codex_hot_path` fixture contains the required apply-patch and shell-boundary
  sentences.
- fixture contains no finish, evidence-ref, WorkFrame, proof, next-action, or
  task-specific benchmark text.
- fixture tool names match the `codex_hot_path` descriptor fixture.
- `mew_legacy` has no dependency on the `codex_hot_path` fixture.

### Phase 6D.1 - Profile Snapshot Ownership

Extend `ToolSurfaceProfile` / `ToolSurfaceSnapshot` with developer contract
identity, hashes, transport policy, and contract tool names.

Close gate:

- profile hash changes when the developer contract changes;
- descriptor hash remains descriptor-only;
- developer contract hash is recorded in request inventory;
- tests prove the same selected profile produces both `provider_tool_names` and
  developer contract tool names.

### Phase 6D.2 - OpenAI/Codex Role Transport

Move `codex_hot_path` tool behavior from instructions-only rendering into a
`role=developer` input item on OpenAI/Codex requests.

Close gate:

- first provider request JSON for `codex_hot_path` has
  `request_body.input[0].role == "developer"`;
- that developer item includes the required edit/command boundary text;
- the user task remains a `role=user` item after the developer item;
- `request_body.instructions` does not become the only carrier of
  `codex_hot_path` tool behavior on OpenAI/Codex;
- provider request inventory records `developer_contract_transport` as
  `role_developer_input`.

### Phase 6D.3 - Deferred Continuation Handling

Do not implement previous-response developer refresh in this slice. The current
system does not yet have a reliable `previous_response_id` continuation after a
websocket break, and it does not yet have full retry / full replay fallback.
Therefore there is no active continuation path for developer refresh to protect.

Keep only the non-OpenAI provider fallback in the current scope. Record the
future continuation rule so later retry/delta work does not drop the developer
contract.

Close gate:

- current OpenAI/Codex fixtures do not require
  `previous_response_developer_refresh` and do not block on continuation refresh
  behavior;
- current full/normal OpenAI/Codex requests always include the developer
  contract as a `role=developer` input item;
- a provider fixture with `supports_developer_role_input=false` folds the exact
  same contract into instructions and records
  `developer_contract_fallback_reason=provider_lacks_developer_role`;
- OpenAI/Codex fixtures never use the fallback;
- future `previous_response_id` or full retry work must preserve/reconstruct the
  same developer contract as `role=developer` before it is allowed to become a
  completion path.

### Phase 6D.4 - Legacy Separation And Leak Gates

Prove profile separation and forbidden-surface behavior.

Close gate:

- `mew_legacy` request fixtures do not contain `codex_hot_path` contract ids or
  required codex shell-boundary phrases unless legacy explicitly defines its
  own separate equivalent contract;
- `codex_hot_path` fixtures do not expose `finish`, `run_tests`,
  `run_command`, `read_file`, `search_text`, `glob`, or `inspect_dir` by
  default;
- forbidden-field scans include developer messages;
- a forbidden-token fixture injects forbidden developer-message text and proves
  the scan fails for finish/evidence tokens, WorkFrame tokens, next-action /
  required-next / first-write tokens, legacy tool names, sidecar/proof control
  text, and benchmark-specific task text;
- no internal finish gate, resolver, WorkFrame, proof, or evidence schema leaks
  into `codex_hot_path` developer text.

### Phase 6D.5 - Behavioral A/B Recheck

Run the fixed tool-surface A/B set and at least the motivating
`make-doom-for-mips` diagnostic with the developer-role profile contract. This
phase rechecks the existing 2026-05-14 Phase 5 default-switch gate with the
new developer-role evidence. It is not a replacement gate and does not allow
`codex_hot_path` to become default unless the existing Phase 5 gate also passes.

Close gate:

- provider request JSON, tool list, route records, render records, transcript
  pairing, proof manifest, source snapshots, and internal finish gate artifacts
  are all present;
- `codex_hot_path` has zero command-edit-boundary source-authoring violations
  on accepted traces, or every violation blocks default-switch evidence;
- first source mutation route is `apply_patch` on source-changing tasks;
- no provider-visible finish or evidence-ref completion pressure is present;
- `mew_legacy` remains separately runnable for comparison;
- the existing 2026-05-14 Phase 5 default-switch gate is rerun or re-evaluated
  with developer-role metadata, developer-message leak scans, and
  command-edit-boundary violations included in its evidence set;
- reviewer accepts that any remaining external reward pass did not rely on a
  synthetic replacement artifact.

## Test Design

Provider request JSON contains `role=developer`:

- Update `tests/test_native_tool_harness.py` live descriptor coverage for
  `codex_hot_path` to assert `request_body["input"][0]["role"] == "developer"`.
- Assert the developer item text contains `Use apply_patch for manual source
  edits`, `Use exec_command for inspection, builds, tests, probes`,
  `Do not create or edit source files with shell heredocs`, and `shell is not
  the manual source editing API`.
- Assert OpenAI/Codex request inventory has
  `developer_contract_transport == "role_developer_input"` and
  `developer_contract_wire_visible is True`.
- Do not add previous-response developer-refresh tests in this implementation
  slice. They belong to the future continuation/retry work described in Phase
  6D.3. Current tests should cover full/normal request construction only.
- Add a provider capability test for `supports_developer_role_input=false`
  proving the only fallback is exact-text instruction folding with an explicit
  fallback reason.

Tools and developer contract originate from the same profile:

- Add a unit test over `build_tool_surface_snapshot()` proving
  `snapshot.developer_contract_provider_tool_names == snapshot.provider_tool_names`
  for default `codex_hot_path` and the explicit `enable_list_dir` variant.
- Add a hash test proving `snapshot.profile_hash` changes when developer
  contract text changes.
- Add a static/import-boundary test proving `codex_hot_path` developer contract
  content lives in `src/mew/implement_lane/tool_profiles/codex_hot_path.py` or
  the profile-owned catalog, not in `prompt.py` or a central policy module.
- Add a request descriptor test proving the lowered provider tools and
  developer contract id are recorded under the same `tool_surface.profile_id`.

`mew_legacy` does not mix with `codex_hot_path`:

- Add a legacy request fixture proving no
  `codex_hot_path_developer_contract_v1` id appears in `mew_legacy`.
- Add a `codex_hot_path` fixture proving no legacy default tool names are
  exposed and no legacy prompt contract id is used.
- Add a negative test that attempts to pair `mew_legacy` tool names with a
  `codex_hot_path` developer contract and fails before the provider request is
  sent.

Developer-message forbidden-token scan tests:

- Add a unit fixture that injects forbidden text into the
  `codex_hot_path` developer contract and proves
  `build_provider_visible_forbidden_fields_report()` or the equivalent
  provider-visible scanner fails on the `profile_developer_contract` surface.
- The fixture must cover finish/evidence tokens such as `finish`,
  `evidence_refs`, `final_status`, and `task_done`.
- It must cover WorkFrame/action-pressure tokens such as `WorkFrame`,
  `next_action`, `required_next`, and `first_write`.
- It must cover legacy tool names that are not provider-visible in default
  `codex_hot_path`: `run_tests`, `run_command`, `read_file`, `search_text`,
  `glob`, and `inspect_dir`.
- It must cover sidecar/proof control text such as `sidecar`, `proof_manifest`,
  and `native_finish_gate`.
- It must cover benchmark-specific task text such as `make-doom-for-mips`,
  `doomgeneric_mips`, `/tmp/frame.bmp`, and Terminal-Bench-specific success
  wording.
- The test should assert both that the forbidden fields are reported and that a
  clean `codex_hot_path` developer contract fixture passes the same scan.

Preservation tests:

- Existing native transcript pairing tests remain green: every model tool call
  receives exactly one paired output.
- Existing `tool_routes.jsonl`, `tool_render_outputs.jsonl`, provider request
  inventory, replay, proof manifest, and native finish gate artifact tests
  remain green with added developer contract metadata.
- Existing internal finish gate tests continue to use no-tool assistant final
  response / done candidate / internal OK-NG authority. No test should require
  a provider-visible `finish` tool in `codex_hot_path`.

Synthetic artifact tests:

- Add a fixture or analyzer case where `exec_command` contains a shell heredoc
  or `cat > source.c`; the A/B or boundary report must flag it as a
  command-edit-boundary violation.
- Add a fixture where artifact existence is present but source mutation
  evidence is absent; the internal finish/default-switch gate must not treat it
  as clean default-switch evidence.

## Current Related Files And Impact Scope

Likely production code impact when implemented:

- `src/mew/implement_lane/tool_profiles/codex_hot_path.py`: add the
  profile-owned developer contract and required shell/edit boundary text.
- `src/mew/implement_lane/tool_profiles/mew_legacy.py`: keep legacy separate,
  or add a separate legacy developer contract without importing the hot-path
  contract.
- `src/mew/implement_lane/tool_profiles/prompt_contracts.py`: expand the
  catalog from prompt sections to profile contract bundles.
- `src/mew/implement_lane/tool_registry.py`: add developer contract metadata to
  `ToolSurfaceProfile`, `ToolSurfaceSnapshot`, hashes, and request metadata.
- `src/mew/implement_lane/prompt.py`: stop being the instructions-only carrier
  for `codex_hot_path` tool behavior.
- `src/mew/implement_lane/native_tool_harness.py`: insert profile developer
  input items before user task input and include them in forbidden-field scans.
- `src/mew/implement_lane/native_provider_adapter.py`: record developer
  contract transport and handle the no-developer-role provider fallback. Do not
  implement previous-response developer refresh in this slice.
- `src/mew/implement_lane/native_workframe_projection.py`: include developer
  message text in provider-visible forbidden scans and inventory sections.
- `src/mew/implement_lane/tool_surface_ab_report.py`: report developer
  contract transport/hash and command-edit-boundary violations.
- `src/mew/implement_lane/hot_path_fastcheck.py`,
  `src/mew/implement_lane/hot_path_step_diff.py`, and
  `src/mew/implement_lane/native_boundary_audit.py`: add checks for developer
  role presence, same-profile ownership, and shell source-authoring flags.
- `tests/test_native_tool_harness.py` and profile/registry tests: add request
  JSON, same-profile, fallback, and legacy separation coverage. Previous-
  response developer-refresh coverage is deferred.

No impact intended:

- no provider-visible `finish` reintroduction;
- no change to internal finish gate authority;
- no change to one-output-per-tool-call pairing;
- no removal of proof, replay, source snapshots, sidecars, or renderer
  observability;
- no default switch to `codex_hot_path` without the existing A/B gates plus the
  developer-role gates above.

## Reviewer Close Gate

Reviewers should reject implementation if any item is false:

- OpenAI/Codex `codex_hot_path` provider request JSON contains a
  `role=developer` input item with the profile tool behavior contract.
- That developer message and the provider-visible tools come from the same
  `ToolSurfaceProfile` snapshot and share a profile hash.
- `codex_hot_path` developer text contains the required `apply_patch` and
  `exec_command` boundary rules.
- `codex_hot_path` developer text contains no provider-visible finish,
  evidence-ref, WorkFrame, proof, sidecar-control, next-action, first-write, or
  task-specific benchmark language.
- The only no-developer-role provider fallback is exact contract folding into
  instructions with an explicit fallback reason.
- `mew_legacy` remains separate and does not mix legacy tools with the
  `codex_hot_path` developer contract.
- Existing provider-native transcript, tool pairing, tool rendering, route
  records, proof/replay artifacts, source snapshots, and internal finish gate
  artifacts are preserved.
- A `make-doom-for-mips` style shell-authored synthetic source artifact is
  observable as a command-edit-boundary violation and cannot be clean
  default-switch evidence.
