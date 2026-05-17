# Design 2026-05-14 - M6.24 ToolRegistry And Codex Hot Path

Status: Phase 0-5 implementation exists for registry selection, hot-path
descriptors/routes, rendering, A/B reporting, and the explicit default-switch
gate; default remains `mew_legacy` until the Phase 5 gate passes real fixed-set
evidence. Phase 6 is still required because profile ownership is incomplete:
`tool_policy.py` still owns canonical provider-visible tool descriptions/specs,
and `prompt.py` still assembles profile-sensitive tool/coding prompt text
through that policy layer instead of from profile-owned prompt contracts.

Scope: `implement_v2` native tool surface selection, provider-visible tool
descriptors, provider-visible tool result rendering, route observability, and
the first concrete Codex-like hot-path profile. This document does not
authorize source changes by itself.

## Context

This design follows:

- `docs/REVIEW_2026-05-14_M6_24_CODEX_TOOL_IF_GAP.md`
- `docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md`
- `docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_AFFORDANCE_COLLAPSE.md`
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`
- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`

Current source surfaces reviewed:

- `src/mew/implement_lane/tool_policy.py`
- `src/mew/implement_lane/native_tool_schema.py`
- `src/mew/implement_lane/native_tool_harness.py`
- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/write_runtime.py`
- `src/mew/implement_lane/read_runtime.py`
- `src/mew/implement_lane/types.py`

Codex references reviewed:

- `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs`
- `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs`

## Durable Decision

Introduce a durable `ToolRegistry` and `ToolSurfaceProfile` layer between the
native request builder and the existing read/write/exec/finish runtimes.

The target architecture is:

```text
explicit profile id
  -> ToolRegistry builds provider-visible descriptors and route map
  -> provider emits native tool call
  -> registry resolves provider-visible name to an internal kernel
  -> existing runtime executes the kernel
  -> profile renderer emits provider-visible output text
  -> transcript stores paired output by call_id
  -> sidecars store evidence, route, replay, observer, and finish details
```

The first concrete profile is `codex_hot_path`. It exposes only the Codex-like
coding hot path:

```text
provider-visible coding tools:
  apply_patch
  exec_command
  write_stdin

optional gated alias:
  list_dir
```

Native finish/closeout, completion resolution, proof, replay, and evidence stay
resident-internal for this profile. If a future profile wants to project a
provider-visible completion tool, that profile must own its descriptor, prompt
contract, renderer, and leak gates separately; it must not change
`codex_hot_path`.

`mew_legacy` remains runnable for A/B. It keeps the current mew tool names and
mew card-like result text until `codex_hot_path` proves better.

No backward compatibility is required before release. The only compatibility
requirement is operational: both `mew_legacy` and `codex_hot_path` must be
selectable by explicit profile id while the A/B gate is active.

## Problem

`implement_v2` already has the important native loop substrate:

- provider-native request descriptors;
- provider-native transcript items;
- exactly one paired output item per tool call id;
- freeform `apply_patch` lowering when supported;
- managed command execution;
- source mutation evidence;
- sidecar proof, replay, route, observer, and finish artifacts;
- provider-visible forbidden-field scans.

The remaining gap is that tool exposure is still a function-list policy, not a
durable profile. The default provider-visible names are mew-specific:
`run_command`, `run_tests`, `poll_command`, `read_command_output`,
`inspect_dir`, `search_text`, and `glob`. Tool output is also mew-card-like.
That surface is observable, but it does not match the action grammar that
Codex-conditioned coding models already know.

The registry should fix exposure and rendering without turning into another
controller.

## Non-Goals

- No full Codex CLI compatibility target.
- No new provider-visible planner.
- No provider-visible `next_action`, `required_next`, `first_write_due`,
  `prewrite_probe_plateau`, WorkFrame action card, or renamed equivalent.
- No provider-visible `finish` tool, task-specific finish pressure, evidence
  citation pressure, or sidecar/proof foregrounding in `codex_hot_path`.
- No registry-owned WorkFrame reducer, CompletionResolver, finish policy,
  task semantic classifier, or "what should the model do next" decision.
- No task-specific MIPS, VM, Terminal-Bench, browser, mail, or calendar
  heuristic in the first profile.
- No source-code edit in this document.
- No deletion of transcript, sidecar proof, replay, typed evidence, source
  snapshots, finish gates, observer artifacts, or leak scans.

## ToolRegistry Responsibilities

`ToolRegistry` is the complete injection boundary for provider-visible tool
surfaces. All provider-visible descriptor, route, renderer, and prompt-contract
material must enter the request through a selected `ToolSurfaceProfile` snapshot
that the registry builds. The registry owns only the mechanical boundary from
provider-visible tools to internal kernels:

1. Build ordered provider-visible descriptors for an explicit profile.
2. Record descriptor, route, and render-policy hashes.
3. Map provider-visible names to internal kernels.
4. Normalize provider-visible arguments into existing `ToolCallEnvelope`
   arguments.
5. Render `ToolResultEnvelope` into provider-visible output text according to
   the selected profile.
6. Emit route decision metadata for artifacts and debugging.
7. Enforce visibility classes: provider-visible, profile-hidden, and
   resident-only internal.

`ToolRegistry` may use these inputs:

- explicit `LaneConfig.tool_surface_profile_id`;
- explicit profile options such as `enable_list_dir`;
- permission mode such as read-only, exec, write, full;
- provider capabilities such as custom/freeform support and strict schema
  support;
- runtime capabilities such as shell availability and interactive stdin
  availability;
- command lifecycle facts needed to decide whether `write_stdin` can target an
  active session.

`ToolRegistry` must not use:

- `next_action`;
- `required_next`;
- first-write pressure;
- probe thresholds;
- WorkFrame current phase;
- finish readiness as an action selector;
- task-specific semantic guesses to choose a tool family.

The registry can say "this tool is unavailable in this permission mode" or
"this active session id exists". It cannot say "the next tool should be
`apply_patch`".

## Profile Selection And Plumbing

The profile id enters the native runtime through `LaneConfig`:

```text
lane_config.tool_surface_profile_id: string
  default: mew_legacy until the default-switch gate passes

lane_config.tool_surface_profile_options: object
  explicit booleans only, for example enable_list_dir
```

Request construction reads this value once per request and asks the registry to
build a `ToolSurfaceSnapshot`. Missing or unknown profile ids fail closed before
the provider request is sent, unless a caller explicitly requests
`mew_legacy` fallback for diagnostic replay.

The selected profile must be recorded in:

- request descriptor;
- provider request inventory;
- `provider_requests.jsonl`;
- `tool_routes.jsonl`;
- descriptor golden artifact;
- transcript metrics;
- proof manifest or its registry/profile sidecar ref;
- A/B report rows.

Required profile fields in those artifacts:

```text
profile_id
profile_version
profile_hash
descriptor_hash
route_table_hash
render_policy_hash
prompt_contract_id
parallel_tool_calls_requested
parallel_tool_calls_effective
interactive_stdin
profile_options
ab_pair_id, when present
```

`prompt_contract_id` is an immutable profile-level label. It may select a
static prompt contract such as `mew_legacy_prompt_v1` or
`codex_hot_path_prompt_v1`, but it cannot vary by turn, probe count, WorkFrame
phase, verifier status, first-write latency, task semantic state, or any other
runtime observation.

`default_parallel_tool_calls` is also static profile metadata. Provider
capability checks may only downgrade it, for example from requested `true` to
effective `false` when the provider does not support parallel tool calls. The
registry must not toggle it based on transcript shape, open loops, probe
counts, WorkFrame state, or whether a verifier recently failed.

## Visibility Classes

Every registry entry has exactly one visibility class:

- `provider_visible`: descriptor is sent to the provider for the selected
  profile. Calls can be emitted by the model.
- `profile_hidden`: kernel may exist and may be exposed by another profile, but
  this profile does not send its descriptor. Calls using the hidden provider
  name in this profile receive a paired unknown-tool output.
- `resident_internal`: kernel is never sent to the provider in any ordinary
  profile. It can run only from harness, supervisor, closeout, replay, cleanup,
  or observer code. Examples include proof projection, source snapshots,
  finish-gate internals, replay rebuild, source observers, and resident cleanup.

Leak tests must prove that `resident_internal` entries never appear in
provider-visible descriptors, prompt text, compact digest, rendered tool
outputs, or provider request inventory. Route artifacts may mention them only
with `provider_visible=false`.

## Core Types

The implementation should introduce these conceptual records. Exact Python
names may vary, but the fields and artifact meaning should not.

```text
ToolSurfaceProfile
  profile_id: string
  profile_version: integer
  description: string
  descriptor_order: list[provider_tool_name]
  result_renderer_id: string
  tool_entries: list[ToolRegistryEntry]
  default_parallel_tool_calls: boolean
  prompt_contract_id: string
  prompt_sections: list[ProfilePromptSection]
  hidden_internal_families: list[string]
  profile_hash: sha256

ToolRegistryEntry
  provider_name: string
  kernel_id: string
  family: read | write | execute | lifecycle | finish | web | data |
          browser | connector | repo | internal
  access: read | write | execute | approval | finish | internal
  visibility: provider_visible | profile_hidden | resident_internal
  descriptor_factory_id: string
  argument_adapter_id: string
  result_renderer_id: string
  supports_parallel: boolean
  availability_class: always | permission_mode | provider_capability |
                      runtime_capability | active_session |
                      explicit_profile_option
  route_hash: sha256

ToolSurfaceSnapshot
  profile_id: string
  profile_version: integer
  profile_hash: sha256
  descriptor_hash: sha256
  route_table_hash: sha256
  render_policy_hash: sha256
  prompt_contract_id: string
  parallel_tool_calls_requested: boolean
  parallel_tool_calls_effective: boolean
  interactive_stdin: boolean
  provider_tool_names: list[string]
  provider_tool_specs: list[object]
  prompt_sections: list[ProfilePromptSection]
  entries: list[entry metadata]
```

The request descriptor and provider request inventory must record the
`ToolSurfaceSnapshot` identity, not just a flat `tool_spec_hash`.

Provider-visible descriptor text and profile-specific prompt text are part of
the profile contract. For `codex_hot_path`, `mew_legacy`, and any later profile,
the profile module owns:

- provider-visible names, descriptions, schemas, strict/custom/freeform flags,
  and descriptor ordering;
- descriptor factory id, argument adapter id, result renderer id, and renderer
  policy label for each exposed provider-visible tool;
- profile prompt contract id and the tool/coding prompt sections that explain
  the exposed surface to the provider;
- profile renderer ids and provider-visible renderer policy labels;
- golden fixtures that lock descriptor and prompt-contract text.

Profile-owned modules/catalogs are the durable home for tool details. The first
catalog entries are `codex_hot_path` and `mew_legacy`; later entries such as
`web_search`, `python_task`, browser, repo-native, or connector profiles must
follow the same ownership rule instead of extending a central tool policy.

`tool_policy.py` must not be the source of provider-visible descriptions or
canonical provider tool specs once Phase 6 closes. It should be deleted if the
profile modules and registry fully replace it. If deletion is too disruptive in
one step, it may remain only as an internal migration shim or internal contract
module with no provider-visible descriptions, no provider-visible schemas, and
no profile-specific prompt text.

`availability_class` is declarative metadata, not a predicate hook. Allowed
classes are:

| Class | Allowed inputs |
| --- | --- |
| `always` | selected profile id and profile version only |
| `permission_mode` | lane permission mode and write/exec/read authorization |
| `provider_capability` | provider support for custom tools, strict schemas, parallel calls, encrypted reasoning, or equivalent provider features |
| `runtime_capability` | shell available, managed exec available, interactive stdin available, write approval available |
| `active_session` | existence and status of a profile-visible command session id |
| `explicit_profile_option` | explicit static option such as `enable_list_dir=true` |

Forbidden availability inputs:

- WorkFrame and WorkFrame projections;
- `next_action`, `required_next`, first-write pressure, or probe thresholds;
- task semantic classification;
- first-write latency, probe count, verifier count, or cadence metrics;
- finish readiness;
- previous failed verifier state, except as ordinary sidecar metrics outside
  registry selection.

## Profile Catalog

### `mew_legacy`

Purpose: preserve the current implementation-lane surface for A/B and
diagnostics.

Provider-visible names:

```text
apply_patch
edit_file
write_file
run_command
run_tests
poll_command
cancel_command
read_command_output
read_file
search_text
glob
inspect_dir
git_status
git_diff
finish
```

Descriptor and result behavior:

- Provider-visible descriptor JSON must be byte-for-byte stable against the
  pre-registry `mew_legacy` descriptor fixture. Ordering, names, descriptions,
  schemas, strict flags, and custom/freeform payloads are unchanged.
- Keep current mew card-like `ToolResultEnvelope.natural_result_text()`
  rendering.
- Keep existing sidecar refs in the current compact style.
- New profile metadata is allowed only in sidecar/request inventory snapshots,
  not inside the provider-visible descriptor JSON.

If schema/runtime drift is fixed as an independent correctness repair, the
fixture must be intentionally updated before the registry wire-in and the
registry phase must then preserve that updated fixture byte-for-byte.

This profile is not the future default target. It exists so the same tasks can
be compared against `codex_hot_path`.

### `codex_hot_path`

Purpose: make the ordinary coding loop look like Codex at the provider-visible
boundary while preserving mew's resident proof and replay substrate.

Provider-visible default coding names:

```text
apply_patch
exec_command
write_stdin
```

Optional alias:

```text
list_dir
```

`list_dir` is allowed only behind an explicit profile option such as
`enable_list_dir=true` or in a read-only diagnostic profile variant. It is
justified because Codex has an experimental `list_dir` tool and because it can
give the model a cheap directory listing when shell execution is disabled. It
must not be enabled by default for full coding A/B until traces show it does
not revive read/probe-heavy behavior.

`read_file` is not part of `codex_hot_path` v1. In this profile the model can
use `exec_command` with familiar commands such as `rg`, `sed`, `nl`, `cat`, and
`git diff`. A future `read_file` alias may be added only if A/B traces show
terminal reads are worse and the alias does not increase prewrite probe count.

No provider-visible completion tool is part of `codex_hot_path`. Native
finish/closeout state, `CompletionResolver`, and verifier evidence remain
resident-internal. The profile prompt contract must not tell the model to call a
finish tool, cite evidence refs, satisfy task-specific closeout pressure, or
surface proof/sidecar details. A separate profile may expose a completion tool
only if that profile owns the descriptor and prompt contract explicitly.

Internal mappings for provider-visible tools:

| Provider name | Internal kernel | Argument adapter | Renderer |
| --- | --- | --- | --- |
| `apply_patch` | `write.apply_patch` | freeform patch to current apply-patch args with `apply=true` | `codex_apply_patch_text_v1` |
| `exec_command` | `exec.run_command` | Codex unified exec args to managed exec args | `codex_terminal_text_v1` |
| `write_stdin` | `exec.poll_command` initially; `exec.write_stdin` only when implemented | Codex session args to managed command lifecycle args | `codex_terminal_text_v1` |
| `list_dir` | `read.inspect_dir` | `dir_path` and implemented listing controls to bounded inspect args | `codex_list_dir_text_v1` |

Internal-only surfaces still run but are never provider-visible in this
profile:

- mew sidecar proof;
- typed source mutation evidence;
- source snapshots;
- execution contracts;
- artifact observers;
- transcript rebuild and replay;
- native finish/closeout, finish gates, and `CompletionResolver`;
- provider request inventories;
- forbidden-field scans;
- route decision artifacts;
- source observer artifacts;
- resident-only cleanup and supervisor hooks.

## `codex_hot_path` Descriptor Details

### `apply_patch`

Use the custom/freeform tool when the provider supports it:

```text
name: apply_patch
type: custom
description: Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON.
format: lark grammar matching existing APPLY_PATCH_LARK_GRAMMAR
```

When custom/freeform is unavailable, use a JSON fallback named `apply_patch`
with `strict=false` and one required `input` string. The fallback reason must be
recorded in the descriptor metadata.

### `exec_command`

Expose a non-strict Codex-like function descriptor:

```text
name: exec_command
strict: false
required: cmd
optional:
  workdir
  shell
  tty
  yield_time_ms
  max_output_tokens
  login
```

Argument mapping:

- `cmd` -> internal `command`.
- `workdir` -> internal `cwd`, resolved under allowed roots.
- `yield_time_ms` -> foreground poll budget, bounded by existing command
  timeout policy.
- `max_output_tokens` -> provider-visible output budget, converted to a
  bounded character budget with a documented ratio and existing hard cap.
- `shell`, `tty`, and `login` are capability-sensitive. Unsupported values
  produce a paired tool output with a concrete unsupported-capability message,
  not a registry-level planning hint.

The registry must allocate a profile-visible session id for yielded commands.
The session id should be an opaque stable value that maps to internal
`command_run_id`. If numeric ids are practical, prefer numeric ids for Codex
compatibility. If string ids are used, the schema must accept both string and
number under `strict=false`, and the route artifact must record the mapping.

#### Internal verifier classification bridge

Hiding provider-visible `run_tests` must not remove verifier evidence. The
`exec_command` adapter therefore feeds an internal-only verifier classification
bridge after argument normalization and before execution evidence is finalized.

Allowed bridge inputs:

- normalized command string and cwd;
- configured task verifier command and acceptance constraints;
- command metadata from the existing shell metadata parser;
- internal lane configuration for verifier/closeout commands;
- existing execution evidence and artifact expectation schemas.

Forbidden bridge outputs:

- provider-visible `command_intent`;
- provider-visible `execution_contract`;
- provider-visible "run tests next" text;
- registry availability changes;
- WorkFrame or next-action state.

Bridge outputs are sidecar/runtime metadata only:

```text
effective_tool_name: run_tests, when the command is classified as verifier-like
command_intent: verify, internal only
execution_contract_normalized: verifier-like contract, internal only
verifier_evidence refs, when execution result satisfies verifier evidence rules
tool_route_decision.effective_tool: run_tests, sidecar only
```

Verifier-like classification may be derived from exact normalized match against
the configured verifier command, explicit lane verifier config, or existing
execution evidence contract metadata. Heuristic "looks like a test" command
classification may be recorded as diagnostic metadata, but it must not be the
sole authority for finish acceptance until reviewers approve that rule.

Phase 2 must prove that a task whose verifier previously used provider-visible
`run_tests` still produces verifier evidence when the model calls
`exec_command` with the same command under `codex_hot_path`.

### `write_stdin`

Expose a non-strict Codex-like function descriptor:

```text
name: write_stdin
strict: false
required: session_id
optional:
  chars
  yield_time_ms
  max_output_tokens
```

Argument mapping:

- `session_id` -> profile-visible session id -> internal `command_run_id`.
- empty or missing `chars` -> poll the command.
- non-empty `chars` -> write to stdin only when
  `interactive_stdin=true` for the profile/runtime snapshot.
- `yield_time_ms` and `max_output_tokens` follow `exec_command` budgeting.

Round-2 decision: the initial `codex_hot_path` implementation may be
poll-only. If the managed command runner still starts commands with stdin
unavailable, the profile snapshot must record:

```text
interactive_stdin=false
write_stdin_mode=poll_only
```

In `poll_only` mode, empty `chars` remains valid polling. Non-empty `chars`
returns a paired terminal-shaped adapter failure and does not write to the
process:

```text
Chunk ID: <chunk_id>
Wall time: 0.000s
Process exited with code 1
Output:
write_stdin adapter error: interactive stdin is unavailable for this session
```

`codex_hot_path` should not become the default until either non-empty stdin is
implemented or the A/B report shows no successful hot-path trace requires
interactive stdin.

### Finish And Closeout Stay Internal

`codex_hot_path` must not expose a provider-visible `finish` descriptor. The
native harness may still use `finish_call`, `CompletionResolver`, verifier
closeout checks, and blocked-return/blocked-continue state internally, but those
mechanisms are resident-internal for this profile.

Profile contract:

```text
provider-visible descriptors:
  apply_patch
  exec_command
  write_stdin
  list_dir only when enable_list_dir=true

provider-visible prompt sections:
  no finish-tool instruction
  no evidence-ref citation pressure
  no task-specific closeout pressure
  no WorkFrame, proof, sidecar, or next-action steering
```

If the runtime needs an internal closeout attempt after the model's natural
final response, that attempt is recorded in resolver/sidecar artifacts, not as
a provider-native tool descriptor or provider-visible tool output in
`codex_hot_path`. If a future profile exposes a completion tool, it must be a
separate selectable profile with its own profile-owned descriptor, argument
adapter, renderer, prompt contract, and golden fixtures.

### `list_dir`

If enabled, expose a Codex-like `list_dir` descriptor:

```text
name: list_dir
strict: false
required: dir_path
optional:
  limit
```

Mapping:

- `dir_path` -> internal `inspect_dir.path`.
- `limit` -> internal bounded directory listing limit.
- `offset` and `depth` must not be exposed until they are implemented honestly.

If reviewers require exact Codex experimental `list_dir` shape with `offset`
and `depth`, Phase 2 must implement both before exposing the alias:

- `offset` skips that many entries from a deterministic sorted listing.
- `depth` controls recursive traversal depth with explicit hard caps.
- rendered output states applied offset, limit, and depth.

No no-op `offset` or `depth` fields are allowed in a provider-visible
descriptor.

This alias must be treated as experimental in A/B reporting.

## Provider-Visible Result Rendering

Rendering is profile-owned. Tool execution still returns `ToolResultEnvelope`;
the selected `ToolSurfaceProfile` decides which string goes into the provider
tool-output item.

### `mew_legacy`

Keep current mew card text:

```text
run_command result: failed; exit_code=2; ...
latest_failure: ...
output_tail:
...
refs: ...
```

### `codex_hot_path`

Use Codex-like terminal text for command-family results. The string should make
the terminal result immediate and should not foreground mew evidence refs.
Only provider-visible `apply_patch`, `exec_command`, `write_stdin`, and
explicitly enabled `list_dir` calls are rendered into provider-native tool
outputs in this profile. Internal finish/closeout, proof, replay, route, and
evidence artifacts remain sidecar-only unless a different selected profile
explicitly projects them.

Terminal completed shape:

```text
Chunk ID: <chunk_id>
Wall time: <seconds>s
Process exited with code <exit_code>
Original token count: <count>
Output:
<bounded terminal output>
```

Terminal running/yielded shape:

```text
Chunk ID: <chunk_id>
Wall time: <seconds>s
Process running with session ID <session_id>
Output:
<bounded terminal output>
```

Terminal failure still uses the same shape with a non-zero exit code or a
clear failed status. The newest stderr/stdout failure text should appear before
generic tails when the payload contains both.

Adapter failures also return paired provider-native outputs and use the
terminal shape when the failed call belongs to the command family. They are not
silent registry errors and they do not trigger a planner hint.

Examples:

```text
Chunk ID: <chunk_id>
Wall time: 0.000s
Process exited with code 1
Output:
exec_command adapter error: cmd is required
```

```text
Chunk ID: <chunk_id>
Wall time: 0.000s
Process exited with code 1
Output:
write_stdin adapter error: unknown session_id <session_id>
```

Unsupported `tty`, unsupported `login`, unknown session id, empty `cmd`,
invalid `workdir`, non-empty stdin in `poll_only` mode, and output-budget parse
failures must each have renderer fixtures.

`apply_patch` success shape:

```text
Success. Updated files:
M src/example.py
```

For add/delete/rename, use stable one-letter operation prefixes when known:
`A`, `M`, `D`, `R`. Include a compact diffstat line only if it is short enough
to fit the live output cap.

`apply_patch` failure shape:

```text
apply_patch failed: <bounded reason>
```

Malformed freeform input, grammar failure, unsupported patch operation,
approval denial, and adapter normalization errors use the same
`apply_patch failed:` prefix. If the malformed input cannot be parsed into a
file operation, the output must include only a bounded reason and no guessed
next action.

Anchor recovery details may include short path/line snippets if they are
already factual and bounded. They must not include `suggested_next_action`,
`required_next`, or action-card language.

Sidecar refs may appear as a single short footer only when needed to recover
omitted raw terminal output:

```text
Refs: output=<ref>
```

They should not dominate model-visible output. Evidence refs, source snapshot
refs, proof refs, route metadata, finish-gate detail, and task-specific closeout
pressure remain internal sidecar artifacts. `codex_hot_path` provider-visible
output stays raw task context plus native transcript plus compact tool output.

## Future Tool Family Injection

The registry must be generic enough to inject future tool families without
turning the default coding profile into a broad tool menu.

Future families:

- `web_search`: externally backed search tools with citation/result rendering.
  Not enabled in `codex_hot_path` by default.
- `python_data`: Python, notebook, dataframe, and local data-analysis tools.
  Outputs render as REPL/terminal text plus artifact refs.
- `browser`: browser open/click/type/screenshot tools. Outputs render as
  compact DOM/text/screenshot refs.
- `mail_calendar`: connector-backed Gmail/Calendar tools. These require
  explicit user/account authorization boundaries, redaction policy, and a
  non-coding profile.
- `repo_native`: repository-aware tools such as git, PR, issue, workspace
  index, or language-server operations. These are not automatically exposed
  just because the task is coding.
- `resident_internal`: mew-only tools for proof, replay, sidecar projection,
  source observers, finish gates, cleanup, and supervisor/reentry.

Each injected family must define:

- provider-visible names;
- internal kernel ids;
- visibility class;
- argument adapters;
- renderer;
- provider capability requirements;
- byte caps and redaction rules;
- route artifact schema additions;
- profile-specific leak scans.

Families are selected by explicit profile or explicit user/product capability,
not by the registry inferring a plan from the task.

## Observability

No observability is removed. The registry adds profile-aware observability.

Required artifacts and fields:

- descriptor golden artifacts for `mew_legacy` and `codex_hot_path`;
- descriptor hash, route-table hash, render-policy hash, and profile hash;
- `profile_id`, `profile_version`, and `profile_hash` in every request
  inventory record;
- ordered provider-visible tool names and per-tool descriptor hashes;
- route decision artifacts recording provider-visible name, internal kernel id,
  argument adapter id, renderer id, effective tool, profile id, and profile
  hash;
- per-tool provider-visible byte counts, split by tool name and renderer id;
- per-turn visible output bytes, tool schema bytes, dynamic input bytes, and
  compact digest bytes;
- first-write latency, first-write turn, probe count before first write,
  command count before first write, and read/list alias count before first
  write;
- edit/verify/repair cadence: mutation count, first verifier latency, failed
  verifier to next edit latency, post-edit verifier freshness, and accepted
  finish evidence;
- unknown tool, argument-adapter failure, unsupported capability, and synthetic
  error counts by profile;
- legacy vs `codex_hot_path` A/B report over the same task set;
- leak scans for canonical forbidden steering fields across instructions,
  task payload, compact digest, tool descriptors, tool outputs, provider
  request inventory, and rendered result text.

Descriptor golden artifacts should be checked in as deterministic fixtures. A
reviewer should be able to diff `codex_hot_path` and see only the intended
provider-visible tools.

Route decision artifacts must stay sidecar-only. They explain what happened;
they are not provider-visible instructions.

## A/B Mechanic

The A/B comparison is a paired-run mechanism, not an informal metric
comparison.

For each A/B item:

1. Create a fixed `ab_pair_id`.
2. Capture a workspace snapshot id or source tree hash before either run.
3. Run the same task contract, model, effort, wall budget, turn budget,
   permission mode, and provider capability configuration.
4. Run one lane attempt with `profile_id=mew_legacy`.
5. Run one lane attempt with `profile_id=codex_hot_path`.
6. Use a deterministic provider seed when available. If no seed is available,
   record `provider_seed_supported=false`.
7. Store separate artifact roots and transcripts for each profile.
8. Write one A/B report row keyed by `ab_pair_id` and profile id.

Required A/B tags:

```text
ab_pair_id
ab_role: baseline | candidate
profile_id
profile_hash
descriptor_hash
workspace_snapshot_id
task_contract_hash
model
effort
budget_profile
provider_seed or provider_seed_supported=false
```

The report compares:

- lane status and accepted finish status;
- first-write latency and first-write turn;
- probe/read/list count before first write;
- mutation count and first verifier latency;
- failed verifier to next edit latency;
- verifier evidence production under `codex_hot_path` `exec_command`;
- provider-visible bytes by section and by tool;
- unknown tool and adapter-failure counts;
- replay/proof/finish/observer artifact validity;
- forbidden provider-visible field scan results.

If the workspace cannot be restored to the same snapshot for both runs, the row
is invalid for default-switch evidence and must be marked
`ab_comparable=false`.

## Phase Plan

### Phase 0: Contract Fixtures And Static Gates

Intent: freeze profile semantics before wiring the registry into live requests.

Implementation status: `mew_legacy` registry schema, profile metadata, hashes,
visibility/availability metadata, and focused invariants are implemented.
`codex_hot_path` golden descriptor fixtures remain Phase 2 work.

Implementation slice:

- add profile contract fixtures for `mew_legacy` and `codex_hot_path`;
- define the registry dataclasses or equivalent schema;
- add descriptor golden artifacts;
- add provider-visible leak fixtures for profile descriptors and rendered
  outputs;
- document the exact `exec_command` and `write_stdin` argument adapters.
- document visibility classes, availability classes, static prompt contract
  labels, and static parallel-tool-call metadata.

Close gate:

- `codex_hot_path` golden descriptor contains only `apply_patch`,
  `exec_command`, `write_stdin`, plus explicitly gated `list_dir`; it contains
  no default `read_file`, `search_text`, `run_tests`, `finish`, or legacy
  mew-specific tool;
- optional `list_dir` appears only in an explicitly named fixture;
- `apply_patch` freeform descriptor uses the Codex short description;
- command descriptors are `strict=false`;
- native finish/closeout and `CompletionResolver` are represented only as
  resident-internal runtime/sidecar contracts for `codex_hot_path`;
- every registry entry has one visibility class and one availability class;
- `prompt_contract_id` and `default_parallel_tool_calls` are static profile
  metadata in fixtures;
- no forbidden steering field appears in descriptors or renderer fixtures;
- docs/artifacts-only scope is respected if no code is intended in the phase.

Suggested tests:

- descriptor golden tests;
- profile hash stability tests;
- visibility and availability class tests;
- forbidden-field descriptor scan tests;
- renderer fixture leak tests.

### Phase 1: Registry Wire-In With `mew_legacy`

Intent: make the live path ask a registry for the current surface without
changing behavior.

Implementation status: live native request construction now routes
`mew_legacy` through `ToolRegistry`, records profile metadata in request
descriptor/inventory artifacts, and stamps turn-matched profile metadata on
`tool_routes.jsonl`. Provider-visible tool names and descriptors remain
unchanged for `mew_legacy`.

Implementation slice:

- route current `list_v2_tool_specs_for_task` behavior through
  `ToolRegistry.build_surface(profile_id="mew_legacy")`;
- add profile id/hash to request descriptors and request inventory;
- add route-table metadata to `tool_routes.jsonl`;
- keep existing tool names, schemas, and mew renderer.

Close gate:

- current focused tests remain green;
- `mew_legacy` provider-visible descriptor JSON is byte-for-byte identical to
  the pre-registry fixture;
- new profile metadata appears only in request inventory, descriptor artifacts,
  route artifacts, or sidecars, not in provider-visible descriptor JSON;
- live request inventory records `profile_id=mew_legacy`;
- route artifacts record profile id/hash;
- no source behavior changes are introduced.

Suggested tests:

- `tests/test_native_provider_adapter.py` request descriptor tests;
- `tests/test_native_tool_harness.py` provider request inventory tests;
- `tests/test_tool_harness_contract.py` route artifact tests;
- native fastcheck on an existing saved artifact.

### Phase 2: `codex_hot_path` Descriptors And Routes

Intent: expose the Codex-like tool names and map them to existing kernels.

Implementation status: explicit `codex_hot_path` selection already exposes only
`apply_patch`, `exec_command`, and `write_stdin` by default, with `list_dir`
available only behind an explicit boolean profile option. No provider-visible
`finish` descriptor belongs to this profile; native finish/closeout and
`CompletionResolver` stay resident-internal. Phase 6 is about moving ownership
of provider-visible descriptions/specs and prompt sections into profile modules,
not about removing `finish` from the current selected surface.

Implementation slice:

- implement `codex_hot_path` profile selection;
- implement `apply_patch`, `exec_command`, and `write_stdin` descriptors;
- implement argument adapters to `write.apply_patch`, `exec.run_command`, and
  command lifecycle kernels;
- keep native finish/closeout, `CompletionResolver`, and blocked-finish state
  resident-internal for this profile;
- implement the internal verifier classification bridge for `exec_command`;
- add optional `list_dir` profile variant if chosen;
- ensure unknown mew legacy names are unavailable in this profile.

Close gate:

- provider request with `profile_id=codex_hot_path` exposes exactly
  `apply_patch`, `exec_command`, and `write_stdin` by default, and only adds
  `list_dir` when the explicit profile option enables it;
- no provider request with `profile_id=codex_hot_path` exposes `finish`,
  `run_command`, `run_tests`, `read_file`, `search_text`, `glob`,
  `inspect_dir`, WorkFrame steering tools, or evidence/proof projection tools;
- `exec_command` maps to managed exec without exposing `run_command`;
- an `exec_command` matching the configured verifier command produces the same
  verifier evidence class that `run_tests` produced under `mew_legacy`;
- yielded command output exposes a session id usable by `write_stdin`;
- `write_stdin` empty chars polls a yielded session;
- non-empty `write_stdin` is either implemented or records
  `interactive_stdin=false`, `write_stdin_mode=poll_only`, and returns the
  terminal-shaped adapter failure defined above;
- internal closeout/`CompletionResolver` artifacts remain present but are not
  provider-visible descriptors or provider-native tool outputs in
  `codex_hot_path`;
- optional `list_dir` exposes no `offset` or `depth` fields unless both are
  implemented honestly;
- `mew_legacy` still runs unchanged.

Suggested tests:

- fake-native tool-call route tests;
- descriptor hash tests;
- session id mapping tests;
- `write_stdin` poll tests;
- `write_stdin` non-empty poll-only adapter-failure test;
- verifier evidence tests for `exec_command` verifier commands;
- internal closeout/blocked-finish tests proving sidecar-only behavior;
- optional `list_dir` route tests;
- unknown legacy tool rejection tests for `codex_hot_path`.

### Phase 3: Profile-Specific Result Rendering

Intent: make the transcript output look like Codex on the hot path while
keeping mew cards in `mew_legacy`.

Implementation status: implemented in `tool_result_renderer.py` and wired into
the native harness. `mew_legacy` preserves `natural_result_text()` output.
`codex_hot_path` renders command-family results with terminal-shaped output,
and `apply_patch` with changed-path output. Any finish/closeout rendering is
internal or belongs to a non-hot profile; `codex_hot_path` must not add a
provider-visible finish-output shape. Render metrics and leak-scan records are
written to `tool_render_outputs.jsonl`.

Implementation slice:

- add renderer registry keyed by profile and tool family;
- implement `codex_terminal_text_v1`;
- implement `codex_apply_patch_text_v1`;
- keep current `natural_result_text()` for `mew_legacy`;
- record per-renderer byte counts and leak scans.

Close gate:

- `exec_command` and `write_stdin` outputs use the terminal shape;
- yielded commands show `Process running with session ID`;
- completed commands show `Process exited with code`;
- command output byte caps and refs are preserved;
- `apply_patch` output is concise and changed-path focused;
- adapter failures are paired outputs and use the profile renderer, not
  unpaired registry exceptions;
- no `codex_hot_path` renderer emits provider-visible finish, evidence-pressure,
  proof, WorkFrame, or next-action text;
- sidecar refs do not dominate provider-visible output;
- renderer outputs contain no forbidden steering fields.

Suggested tests:

- command success/failure/yield renderer fixtures;
- adapter-failure fixtures for empty `cmd`, unknown `session_id`, unsupported
  `tty`, unsupported `login`, non-empty stdin in poll-only mode, and malformed
  `apply_patch`;
- apply-patch success/failure renderer fixtures;
- internal closeout fixtures proving no provider-visible finish output under
  `codex_hot_path`;
- output byte count tests;
- leak scan tests over rendered output;
- replay test proving internal refs still recover omitted details.

### Phase 4: Profile-Aware Observability And A/B Report

Intent: make profile comparison reliable before any default switch.

Implementation status: implemented by
`src/mew/implement_lane/tool_surface_ab_report.py` and
`scripts/build_tool_surface_ab_report.py`. The report reads native
implement_v2 artifact roots, compares `mew_legacy` and `codex_hot_path` rows,
marks mismatched workspace snapshots as `ab_comparable=false`, preserves
provider request / route / render / proof / evidence sidecars, and keeps
diagnostic-only loop signals out of provider-visible leak decisions.

Implementation slice:

- add A/B report generation for `mew_legacy` vs `codex_hot_path`;
- include first-write latency, probe counts, edit/verify/repair cadence,
  output bytes, schema bytes, success/finish status, and proof/replay status;
- tag every paired run with `ab_pair_id`, `ab_role`, profile id/hash,
  descriptor hash, workspace snapshot id, task contract hash, model, effort,
  budget profile, and provider seed support;
- add saved artifacts for at least one small fake-native task and one
  M6.24-style hard-runtime diagnostic;
- ensure profiler output cites profile id/hash and descriptor hash.

Close gate:

- A/B report can compare both profiles on the same task contract and workspace
  snapshot;
- report rows with different workspace snapshots are marked
  `ab_comparable=false` and excluded from default-switch evidence;
- provider request inventories for `codex_hot_path` pass forbidden-field scans;
  legacy baseline rows may carry old provider-visible markers such as `proof`
  and still be comparable when pairing, replay, evidence, render, and sidecar
  integrity are intact;
- every call has exactly one paired output;
- sidecar proof, replay, finish, and observer artifacts remain present;
- verifier evidence is preserved for verifier commands hidden behind
  `exec_command`;
- no `codex_hot_path` run depends on hidden first-write pressure.

Suggested tests:

- A/B report fixture tests;
- native fastcheck for both profiles;
- artifact scope tests for sidecar preservation;
- provider inventory profile/hash tests.

### Phase 5: Default-Switch Gate

Intent: switch the default profile only after evidence says the new surface is
better.

Implementation status: implemented as an explicit blocker gate, not a default
switch. `src/mew/implement_lane/tool_surface_default_gate.py` and
`scripts/check_tool_surface_default_switch_gate.py` consume Phase 4 A/B report
artifacts, require a fixed A/B set and reviewer acceptance, and block default
switching when comparability, forbidden-field scans, pairing/proof/evidence,
success/acceptance, first-write/probe cadence, verifier repair latency,
visible-byte safety, or `write_stdin`/adapter limitations regress.
`scripts/run_tool_surface_ab_smoke.py` generates a reusable fake-native
`mew_legacy` vs `codex_hot_path` smoke artifact set and writes both the Phase 4
report and Phase 5 gate result. Live/pre-speed A/B can now select the same
profile surface through `mew work --oneshot --work-guidance
tool_surface_profile_id=<profile>`; `scripts/run_harbor_mew_diagnostic.py`
also exposes `--tool-surface-profile-id` and includes it in the generated
jobs-dir name. `scripts/run_tool_surface_ab_diagnostic.py` wraps one paired
`mew_legacy` / `codex_hot_path` live diagnostic item, then writes the Phase 4
A/B report and Phase 5 gate artifacts. The wrapper is deliberately conservative:
it rejects multi-trial/proof-5 runs, blocks the default-switch gate if either
child diagnostic fails or lacks a passing external reward, and requires explicit
real `workspace_snapshot_id` / `task_contract_hash` inputs before the report can
be comparable default-switch evidence. It also forwards the resolved task cwd to
the child Harbor diagnostics. The cwd comes from a task map by default
(`prove-plus-comm` uses `/workspace`; unknown tasks fall back to `/app`), with
`--command-cwd` available only as an explicit override.

Internal closeout acceptance is required for default switching unless an
explicit reviewer-visible external-reward override is supplied. This keeps
externally passing Terminal-Bench traces usable as caveated A/B evidence without
silently treating blocked mew closeout / evidence-citation behavior as a clean
default switch signal. That acceptance requirement must not be implemented by
projecting a provider-visible `finish` tool or evidence-citation instruction in
`codex_hot_path`.

Close gate:

- `codex_hot_path` has zero canonical provider-visible steering leaks across
  the fixed A/B set;
- pairing, replay, proof manifest, resolver decisions, and source snapshot
  checks pass;
- success/acceptance rate is not worse than `mew_legacy`;
- if any `codex_hot_path` internal closeout remains blocked, the gate blocks
  unless `external_reward_override_reason` explicitly records reviewer-accepted
  external verifier evidence;
- accepted completion under `codex_hot_path` records native closeout /
  `CompletionResolver` state in internal artifacts without exposing a
  provider-visible `finish` descriptor, finish tool output, or evidence-pressure
  prompt text;
- verifier evidence production is not worse after provider-visible `run_tests`
  is hidden behind `exec_command`;
- zero-write timeout rate is lower than or equal to `mew_legacy`, and lower on
  the M6.24 target diagnostic that motivated this work;
- first-write median and p95 are not worse than `mew_legacy`;
- probe/read/list count before first write is lower or justified by a higher
  success rate;
- failed verifier to next edit latency is not worse;
- visible prompt/tool-output bytes are lower or have a documented safety reason;
- `write_stdin` limitations do not appear in successful hot-path traces, or
  interactive stdin support is implemented;
- reviewer accepts the A/B report;
- paired live A/B evidence comes from a single-task wrapper run with explicit
  real workspace/task identity; synthetic hashes, failed child diagnostics, and
  missing or non-passing external rewards are not accepted as default-switch
  evidence.

Only after this gate may `codex_hot_path` become the default. `mew_legacy` can
remain available as an explicit diagnostic/A-B profile until release cleanup.

### Phase 6: Profile-Owned Tool Surface And Prompt Contract

Intent: restore the full meaning of tool injection. A selected
`ToolSurfaceProfile` must define the provider-visible tool surface end to end:
names, descriptions, schemas, descriptor ordering, argument adapters, route
metadata, renderer policy labels, and the prompt contract that describes the
tool/coding surface to the model. The registry may select and snapshot that
profile, but profile-specific tool text must not live in a central policy
module.

Current implementation reality: `src/mew/implement_lane/tool_registry.py`
selects `mew_legacy` or `codex_hot_path`, but it still imports
`tool_policy.py` for canonical specs and provider-visible descriptions.
`src/mew/implement_lane/prompt.py` also imports `tool_policy.py` to assemble
the tool section and coding contract, then branches on the selected profile.
Provider-visible behavior is therefore scattered across `tool_policy.py`,
`tool_registry.py`, and `prompt.py`. This makes injection partial: the profile
affects route selection and some metadata, but the profile does not yet own all
provider-visible descriptions or prompt steering.

Implementation status: not implemented. Phase 0-5 route/render/A-B/gate
plumbing exists, and `codex_hot_path` has no provider-visible `finish`, but
provider-visible descriptor/spec ownership and profile prompt-contract
ownership are still incomplete.

Target module boundary:

- `codex_hot_path` provider-visible descriptions/specs live only in the
  `codex_hot_path` profile module.
- `mew_legacy` provider-visible descriptions/specs live only in the
  `mew_legacy` profile module.
- each later profile, for example `web_search` or `python_task`, owns its own
  descriptor, argument-adapter, renderer, and prompt-contract module/catalog
  entry.
- `tool_registry.py` imports profile definitions or receives them through a
  profile catalog; it is the complete provider-visible injection boundary and
  does not import provider-visible text from `tool_policy.py`.
- `prompt.py` accepts a `ToolSurfaceSnapshot` or equivalent profile prompt
  contract object and injects profile-defined prompt sections selected by
  `ToolSurfaceSnapshot.prompt_contract_id`.
- `prompt.py` does not directly inspect `tool_policy.py`, concrete profile
  internals, profile module constants beyond the snapshot/contract interface,
  or raw tool-name lists such as `if "apply_patch" in tool_names` to construct
  coding/tool guidance.
- `tool_policy.py` is deleted, or shrunk to an internal-only migration shim
  with no provider-visible descriptions, canonical provider specs, or
  profile-specific prompt text.
- `codex_hot_path` provider-visible descriptors are exactly `apply_patch`,
  `exec_command`, and `write_stdin` by default, with `list_dir` only under an
  explicit profile option; no `finish`, proof, evidence, WorkFrame, or
  next-action projection is included.

Phase 6 is not closed until these grep/testable gates pass:

- provider-visible tool descriptions live only in profile-owned
  modules/catalogs and descriptor golden fixtures, never in `tool_policy.py`;
- `rg "tool_policy" src/mew/implement_lane tests` has no live
  provider-visible or prompt dependency, or only a clearly named compatibility
  shim with a deletion plan and a failing test if provider-visible text is
  added there;
- `prompt.py` receives tool/prompt sections through
  `ToolSurfaceSnapshot.prompt_contract_id` or an explicit profile-owned prompt
  contract object, has no direct `tool_policy.py` import, and does not infer
  coding guidance by inspecting concrete tool names;
- `codex_hot_path` golden descriptor proves thin Codex-like descriptions and
  the exact provider-visible tool list: `apply_patch`, `exec_command`,
  `write_stdin`, plus optional `list_dir` only in the explicitly enabled
  fixture;
- `mew_legacy` golden descriptor proves legacy profile stability, or records an
  explicit reviewed migration with a new legacy fixture;
- profile modules/catalogs own descriptor, argument adapter, renderer, prompt
  contract id, and prompt sections where applicable;
- tests prove descriptors and prompt sections can change by selected profile
  without changing runtime kernel contracts;
- provider-visible `codex_hot_path` stays raw task plus native transcript plus
  compact tool output; sidecar/proof/evidence/finish detail remains internal
  unless the selected non-hot profile explicitly projects it;
- forbidden-field scans fail on provider-visible `next_action`, `first_write`,
  WorkFrame steering, task-specific finish pressure, evidence citation
  pressure, proof foregrounding, or sidecar control text in `codex_hot_path`.

#### Phase 6A: Move Descriptors Into Profile Modules

Intent: make provider-visible descriptor ownership local to each profile before
changing prompt assembly. The full repository-wide
`rg "tool_policy" src/mew/implement_lane tests` zero-or-compatibility-shim gate
belongs to the final Phase 6 / Phase 6C end-state, not to this slice.

Implementation status: not implemented. `tool_registry.py` still reaches
`tool_policy.py` for canonical provider-visible specs/descriptions; Phase 6A
ends when descriptor/spec ownership is profile-local even if `prompt.py` still
has temporary Phase 6B dependencies and other modules still carry tracked
non-provider-visible contract/type imports scheduled for Phase 6C cleanup.

Implementation slice:

- introduce profile modules for `mew_legacy` and `codex_hot_path`, or expand
  existing profile modules if they already exist;
- move all provider-visible names, descriptions, schemas, strict flags,
  custom/freeform descriptors, descriptor ordering, descriptor ids, argument
  adapter ids, renderer ids, renderer policy labels, and prompt contract ids
  into the profile modules;
- make `tool_registry.py` build `ToolSurfaceSnapshot` from selected profile
  definitions instead of from `tool_policy.py` canonical specs;
- allow existing `tool_policy.py` imports outside the registry/profile
  descriptor path to remain only when they are non-provider-visible
  contract/type imports or explicitly Phase 6B prompt dependencies, and record
  them as Phase 6B/6C follow-up inventory;
- keep route maps and internal kernel ids in registry/profile metadata, not in
  prompt assembly;
- preserve the current Phase 0-5 behavior and descriptor hashes unless a
  fixture is intentionally updated with a reviewer-visible reason.

Close gate:

- `tool_registry.py` no longer imports `tool_policy.py` for provider-visible
  descriptors, canonical specs, names, schemas, or descriptions;
- profile descriptor/spec modules do not depend on `tool_policy.py` for
  provider-visible text or schemas;
- any remaining `tool_policy.py` imports in `src/mew/implement_lane` or tests
  are explicitly inventoried as non-provider-visible contract/type dependencies
  or Phase 6B prompt-migration dependencies, with no provider-visible
  descriptor/spec/ordering ownership and with removal or shim containment
  assigned to Phase 6B/6C;
- provider-visible descriptions exist only in profile modules and their golden
  fixtures;
- `codex_hot_path` descriptor golden tests lock Codex-like thin descriptions
  and the exact list `apply_patch`, `exec_command`, `write_stdin`, with
  optional gated `list_dir` only in the explicit option fixture;
- `mew_legacy` descriptor is fixed in the legacy profile module and remains
  byte-for-byte stable against its legacy golden fixture;
- route tests still prove `exec_command`, `write_stdin`, `apply_patch`, and
  optional `list_dir` map to the intended internal kernels without exposing
  legacy names; native finish/closeout remains resident-internal.

Suggested tests:

- descriptor golden tests per profile module;
- provider-visible description location test or static grep test;
- `tool_registry.py` import-boundary test;
- Phase 6A import-inventory test or fixture proving remaining `tool_policy.py`
  imports are outside provider-visible descriptor/spec/ordering construction;
- profile hash stability tests;
- cross-profile injection test showing a descriptor/prompt change in one
  profile does not require changing runtime kernel contracts;
- unknown-tool rejection tests for `codex_hot_path`.

#### Phase 6B: Move Prompt Tool/Coding Contract Into Profiles

Intent: make prompt injection consume profile-owned prompt contracts rather
than reconstructing profile semantics from a central tool policy.

Implementation status: not implemented. `prompt.py` still imports
`tool_policy.py`, branches on concrete profile/tool details, and assembles
profile-sensitive tool/coding prompt text directly.

Implementation slice:

- define a profile prompt contract record keyed by
  `ToolSurfaceSnapshot.prompt_contract_id`;
- move the provider-visible tool section, coding contract text, tool-use
  affordance text, and profile-specific warnings into profile-owned prompt
  sections;
- make `prompt.py` receive the selected snapshot/contract and inject those
  sections through a narrow interface;
- keep generic, profile-independent prompt scaffolding in `prompt.py`;
- remove profile-specific branching in `prompt.py` except for selecting already
  materialized sections from the snapshot/contract interface;
- remove tool-name-inspection prompt assembly from `prompt.py`; it must not
  build coding guidance by checking whether names such as `apply_patch`,
  `exec_command`, `run_tests`, or `write_file` are present;
- preserve the Codex-like hot path: `codex_hot_path` prompt text must stay
  thin and must not drift into mew-heavy proof, WorkFrame, sidecar, or steering
  language, and must not mention provider-visible finish or evidence-citation
  pressure.

Close gate:

- prompt tool/coding sections are injected from profile prompt contracts
  selected by `ToolSurfaceSnapshot.prompt_contract_id`;
- `prompt.py` does not import or inspect `tool_policy.py`;
- `prompt.py` does not import concrete `codex_hot_path` or `mew_legacy`
  internals;
- `prompt.py` does not construct profile-specific tool/coding guidance by
  inspecting provider-visible tool names directly;
- `codex_hot_path` prompt golden tests lock thin Codex-like wording and fail on
  mew-heavy descriptions, WorkFrame steering, proof/sidecar foregrounding, or
  hidden next-action, first-write, finish, or evidence pressure;
- `mew_legacy` prompt contract remains fixed in the legacy profile module and
  keeps the legacy provider-visible expectations;
- descriptor and prompt-contract hashes both appear in request inventory or
  equivalent profile artifacts.

Suggested tests:

- prompt golden tests for `codex_hot_path_prompt_v1` and
  `mew_legacy_prompt_v1`;
- forbidden-field scans over prompt text;
- import-boundary tests for `prompt.py`;
- tool-name-inspection static test for `prompt.py`;
- request inventory tests for prompt contract id/hash;
- A/B smoke fixture proving the same selected profile controls descriptors and
  prompt contract.

#### Phase 6C: Delete Or Contain `tool_policy.py`

Intent: finish the migration so future profiles cannot accidentally inherit
central provider-visible text.

Implementation status: not implemented. `tool_policy.py` remains a live module
for provider-visible specs/descriptions and prompt-policy dependencies; Phase
6C closes only after those dependencies are deleted or contained in an
internal-only shim.

Implementation slice:

- delete `tool_policy.py` after all imports are removed; or, if one release
  needs a migration shim, shrink it to internal-only adapters with an explicit
  removal issue/date;
- move any remaining non-provider-visible helpers to appropriately named
  internal modules;
- update `__init__.py`, native provider adapter, harness contract, schema,
  substrate inventory, workframe navigation, and runtime imports to consume
  profile/registry/internal-contract APIs instead of `tool_policy.py`;
- update artifact names only if needed, keeping old artifact readers tolerant
  through internal migration code rather than provider-visible policy text.

Close gate:

- `rg "tool_policy" src/mew/implement_lane tests` is zero; or the only match
  is a documented migration shim with zero provider-visible description/spec
  dependency and a failing test if provider-visible text is added there;
- provider-visible descriptions/specs are discoverable only in profile modules
  and descriptor golden fixtures;
- `codex_hot_path` descriptor and prompt-contract golden tests still pass and
  prove thin Codex-like wording and the exact hot-path tool list;
- `mew_legacy` descriptor and prompt-contract golden tests still pass from the
  legacy profile module;
- `prompt.py` has no direct dependency on tool policy or concrete profile
  internals and no profile-specific tool-name inspection;
- registry, prompt, provider adapter, native harness, replay/fastcheck, and A/B
  report tests pass on saved fixtures;
- reviewer can verify that the profile-selected surface includes
  provider-visible descriptions and prompt contract, not only route selection.

## Risks

- The registry may gradually become a planner. Mitigation: fail tests if it
  imports WorkFrame reducers, consumes `required_next`, or emits action
  pressure.
- Central provider-visible tool text may survive under another name and keep
  profile injection partial. Mitigation: require profile-owned descriptor and
  prompt-contract golden tests plus static import/grep gates for
  `tool_policy.py`.
- The Codex-like hot path may drift into mew-heavy descriptions or prompt
  steering while preserving the same tool names. Mitigation: lock
  `codex_hot_path` descriptor and prompt-contract text in profile-owned golden
  tests and scan for WorkFrame/proof/sidecar/next-action steering terms.
- Availability, prompt, or parallel-call metadata may become covert runtime
  steering. Mitigation: constrain them to static profile metadata plus explicit
  provider/runtime capability downgrades.
- Hiding `run_tests` may weaken verifier classification. Mitigation: require
  the internal-only `exec_command` verifier bridge and A/B evidence before
  default switching.
- Reintroducing a provider-visible `finish` tool into `codex_hot_path` would
  violate the Codex-thin surface and reintroduce task-specific closeout/evidence
  pressure. Mitigation: keep finish/closeout resident-internal for
  `codex_hot_path`; if a provider-visible completion tool is needed, expose it
  only through a separate selectable profile with its own golden descriptor and
  prompt contract.
- `write_stdin` may not map cleanly to the current managed runner. Mitigation:
  make interactive stdin capability explicit and block default switch until
  traces prove it is acceptable.
- Hiding read/search tools may force awkward shell reads. Mitigation: compare
  A/B traces and add only the smallest justified alias, starting with
  `list_dir`.
- Terminal-shaped output may hide important mew evidence. Mitigation: keep refs
  in sidecars, include a short ref footer only when needed, and require replay
  to recover omitted details.
- Descriptor differences may be too small to change model behavior. Mitigation:
  measure behavior, not just descriptor hash.
- Profile explosion may make debugging harder. Mitigation: require explicit
  profile ids, stable profile hashes, and golden descriptors for each profile.
- Mail/calendar/browser/data tools have privacy and authorization concerns.
  Mitigation: keep them out of `codex_hot_path` and require family-specific
  redaction and authorization design before exposure.

## Reviewer Checklist

Reviewers should reject an implementation if any item is false:

- `ToolRegistry` exposes tools and maps calls; it does not choose next actions.
- the selected `ToolSurfaceProfile` owns provider-visible descriptions, specs,
  descriptor ordering, renderer policy labels, and prompt contract sections.
- `tool_policy.py` is deleted, or contains only internal migration/contract
  code with no provider-visible descriptions, no canonical provider specs, and
  no profile-specific prompt text.
- `rg "tool_policy" src/mew/implement_lane tests` is zero except for the
  documented internal shim case above.
- provider-visible descriptions exist only in profile modules and descriptor
  golden fixtures.
- prompt tool/coding sections are injected from the selected profile prompt
  contract through `ToolSurfaceSnapshot.prompt_contract_id`.
- `prompt.py` does not directly depend on `tool_policy.py` or concrete profile
  internals.
- `codex_hot_path` descriptor and prompt-contract golden tests lock thin
  Codex-like wording and fail on mew-heavy prompt steering.
- `codex_hot_path` exposes only `apply_patch`, `exec_command`,
  `write_stdin`, plus explicitly gated `list_dir` if enabled; no
  provider-visible `finish` tool is exposed.
- native finish/closeout uses internal `finish_call` / `CompletionResolver`
  artifacts only; finish gates and resolver internals stay sidecar-only.
- verifier classification is preserved when verifier commands arrive through
  `exec_command` instead of provider-visible `run_tests`.
- `mew_legacy` remains selectable for A/B.
- `mew_legacy` provider-visible descriptors are byte-for-byte stable against
  the pre-registry fixture.
- every registry entry has a defined visibility class and declarative
  availability class.
- mew sidecar proof, evidence, transcript artifacts, source snapshots, replay,
  finish gates, and observer artifacts remain internal.
- command result rendering for `codex_hot_path` is terminal-shaped.
- adapter failures render as paired profile-shaped outputs.
- mew card rendering remains available for `mew_legacy`.
- provider-visible output does not foreground sidecar/proof refs.
- provider-visible hot path stays raw task plus native transcript plus compact
  tool output; sidecar/proof/evidence remains internal unless the selected
  profile explicitly projects it.
- profile id/hash appears in request inventory and route artifacts.
- `LaneConfig.tool_surface_profile_id` is the profile plumbing entry point.
- per-tool visible byte counts and edit/verify/repair metrics are recorded.
- A/B runs use paired lane attempts with the same task contract and workspace
  snapshot, tagged by `ab_pair_id`.
- optional `list_dir` does not expose `offset` or `depth` until implemented.
- forbidden steering fields are scanned across descriptors, input, inventory,
  and rendered tool outputs.
- default switching is blocked until the A/B report satisfies the measurement
  gate.
