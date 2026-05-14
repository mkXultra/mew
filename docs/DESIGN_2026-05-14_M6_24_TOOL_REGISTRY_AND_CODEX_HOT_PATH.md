# Design 2026-05-14 - M6.24 ToolRegistry And Codex Hot Path

Status: Phase 0-5 implemented; default remains `mew_legacy` until the Phase 5
gate passes real fixed-set evidence.

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

The first concrete profile is `codex_hot_path`. It exposes the Codex-like coding
hot path plus a minimal native completion trigger:

```text
provider-visible coding tools:
  apply_patch
  exec_command
  write_stdin

provider-visible completion tool:
  finish

optional gated alias:
  list_dir
```

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
- No registry-owned WorkFrame reducer, CompletionResolver, finish policy,
  task semantic classifier, or "what should the model do next" decision.
- No task-specific MIPS, VM, Terminal-Bench, browser, mail, or calendar
  heuristic in the first profile.
- No source-code edit in this document.
- No deletion of transcript, sidecar proof, replay, typed evidence, source
  snapshots, finish gates, observer artifacts, or leak scans.

## ToolRegistry Responsibilities

`ToolRegistry` owns only the mechanical boundary from provider-visible tools to
internal kernels:

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
  entries: list[entry metadata]
```

The request descriptor and provider request inventory must record the
`ToolSurfaceSnapshot` identity, not just a flat `tool_spec_hash`.

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

Provider-visible completion name:

```text
finish
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

Internal mappings:

| Provider name | Internal kernel | Argument adapter | Renderer |
| --- | --- | --- | --- |
| `apply_patch` | `write.apply_patch` | freeform patch to current apply-patch args with `apply=true` | `codex_apply_patch_text_v1` |
| `exec_command` | `exec.run_command` | Codex unified exec args to managed exec args | `codex_terminal_text_v1` |
| `write_stdin` | `exec.poll_command` initially; `exec.write_stdin` only when implemented | Codex session args to managed command lifecycle args | `codex_terminal_text_v1` |
| `finish` | `finish.native_finish_call` | minimal finish args to current finish call args | `codex_finish_text_v1` |
| `list_dir` | `read.inspect_dir` | `dir_path` and implemented listing controls to bounded inspect args | `codex_list_dir_text_v1` |

Internal-only surfaces still run but are never provider-visible in this
profile:

- mew sidecar proof;
- typed source mutation evidence;
- source snapshots;
- execution contracts;
- artifact observers;
- transcript rebuild and replay;
- finish gates and `CompletionResolver`;
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

### `finish`

`codex_hot_path` keeps a minimal provider-visible `finish` tool because the
native harness completes through a `finish_call` plus `CompletionResolver`.
This is a completion trigger, not a planning tool.

Descriptor shape:

```text
name: finish
strict: false
required:
  summary
optional:
  evidence_refs
  final_status
```

Completion contract:

```text
model emits finish(summary, evidence_refs?, final_status?)
  -> registry maps to current native finish call args
  -> harness validates the finish call
  -> CompletionResolver decides allow, blocked_continue, or blocked_return
  -> transcript stores exactly one paired finish_output for the call_id
  -> resolver decision and evidence details stay in sidecars
```

Provider-visible `finish` output is concise:

```text
finish accepted: <bounded summary>
```

or:

```text
finish blocked: <bounded blocker summary>
```

Blocked finish behavior matches the existing native boundary: `blocked_continue`
keeps the blocked finish call/output in the transcript and lets the model
continue; `blocked_return` stores the pair and returns control to supervisor or
reentry. The registry does not decide either outcome.

Finish gates, verifier closeout details, resolver policy version, typed
evidence validation, and missing-obligation internals remain sidecar-only.

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
omitted output:

```text
Refs: output=<ref>
```

They should not dominate model-visible output. Evidence refs, source snapshot
refs, proof refs, route metadata, and finish-gate detail remain internal
sidecar artifacts unless a specific result cannot be understood without a
bounded factual ref.

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
  `exec_command`, `write_stdin`, `finish`, and no default
  `read_file`/`search_text`;
- optional `list_dir` appears only in an explicitly named fixture;
- `apply_patch` freeform descriptor uses the Codex short description;
- command descriptors are `strict=false`;
- `finish` descriptor is present and maps to native `finish_call` plus
  `CompletionResolver`;
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

Implementation status: explicit `codex_hot_path` selection now exposes
`apply_patch`, `exec_command`, `write_stdin`, and `finish` by default.
`list_dir` is available only behind an explicit boolean profile option.
`exec_command` routes to managed exec, `write_stdin` is poll-only when chars
are empty, and route records preserve provider-visible declared names plus the
internal effective kernel.

Implementation slice:

- implement `codex_hot_path` profile selection;
- implement `apply_patch`, `exec_command`, and `write_stdin` descriptors;
- implement argument adapters to `write.apply_patch`, `exec.run_command`, and
  command lifecycle kernels;
- implement minimal `finish` descriptor and adapter to native finish calls;
- implement the internal verifier classification bridge for `exec_command`;
- add optional `list_dir` profile variant if chosen;
- ensure unknown mew legacy names are unavailable in this profile.

Close gate:

- provider request with `profile_id=codex_hot_path` exposes only the expected
  tools;
- `exec_command` maps to managed exec without exposing `run_command`;
- an `exec_command` matching the configured verifier command produces the same
  verifier evidence class that `run_tests` produced under `mew_legacy`;
- yielded command output exposes a session id usable by `write_stdin`;
- `write_stdin` empty chars polls a yielded session;
- non-empty `write_stdin` is either implemented or records
  `interactive_stdin=false`, `write_stdin_mode=poll_only`, and returns the
  terminal-shaped adapter failure defined above;
- `finish` calls produce paired finish outputs and route through
  `CompletionResolver`;
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
- `finish` allow, blocked_continue, and blocked_return tests;
- optional `list_dir` route tests;
- unknown legacy tool rejection tests for `codex_hot_path`.

### Phase 3: Profile-Specific Result Rendering

Intent: make the transcript output look like Codex on the hot path while
keeping mew cards in `mew_legacy`.

Implementation status: implemented in `tool_result_renderer.py` and wired into
the native harness. `mew_legacy` preserves `natural_result_text()` output.
`codex_hot_path` renders command-family results with terminal-shaped output,
`apply_patch` with changed-path output, and `finish` with concise
accepted/blocked output. Render metrics and leak-scan records are written to
`tool_render_outputs.jsonl`.

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
- `finish` accepted/blocked outputs are concise and do not expose resolver
  internals;
- sidecar refs do not dominate provider-visible output;
- renderer outputs contain no forbidden steering fields.

Suggested tests:

- command success/failure/yield renderer fixtures;
- adapter-failure fixtures for empty `cmd`, unknown `session_id`, unsupported
  `tty`, unsupported `login`, non-empty stdin in poll-only mode, and malformed
  `apply_patch`;
- apply-patch success/failure renderer fixtures;
- finish accepted/blocked renderer fixtures;
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
- provider request inventories for both profiles pass forbidden-field scans;
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
be comparable default-switch evidence.

Close gate:

- `codex_hot_path` has zero canonical provider-visible steering leaks across
  the fixed A/B set;
- pairing, replay, proof manifest, resolver decisions, and source snapshot
  checks pass;
- success/acceptance rate is not worse than `mew_legacy`;
- accepted completion under `codex_hot_path` always passes through native
  `finish_call` plus `CompletionResolver`, with blocked finish continuation
  preserved in transcript artifacts;
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
- reviewer accepts the A/B report.
- paired live A/B evidence comes from a single-task wrapper run with explicit
  real workspace/task identity; synthetic hashes, failed child diagnostics, and
  missing or non-passing external rewards are not accepted as default-switch
  evidence.

Only after this gate may `codex_hot_path` become the default. `mew_legacy` can
remain available as an explicit diagnostic/A-B profile until release cleanup.

## Risks

- The registry may gradually become a planner. Mitigation: fail tests if it
  imports WorkFrame reducers, consumes `required_next`, or emits action
  pressure.
- Availability, prompt, or parallel-call metadata may become covert runtime
  steering. Mitigation: constrain them to static profile metadata plus explicit
  provider/runtime capability downgrades.
- Hiding `run_tests` may weaken verifier classification. Mitigation: require
  the internal-only `exec_command` verifier bridge and A/B evidence before
  default switching.
- Adding a provider-visible `finish` tool may look like an extra hot-path tool.
  Mitigation: classify it as completion-only, route it through the existing
  resolver, and keep finish gates internal.
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
- `codex_hot_path` exposes only `apply_patch`, `exec_command`,
  `write_stdin`, completion-only `finish`, plus explicitly gated `list_dir` if
  enabled.
- `finish` uses native `finish_call` plus `CompletionResolver`; finish gates
  and resolver internals stay sidecar-only.
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
