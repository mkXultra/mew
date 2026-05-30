# Design 2026-05-20 - M6.25 MemorySystem Tool Provider

Status: design only.

Scope: M6.25 memory subsystem boundaries for `implement_v2`, including the
`MemorySystem` injection boundary, `MemoryToolProvider`, `MemoryRegistry`,
ToolRegistry integration, recall v0 result shape, observability, safety gates,
and pre-implementation tests/static gates. This document does not authorize
implementation code changes.

This document's scope is ToolProvider integration only: how memory recall can
enter the model-visible tool surface without making ToolRegistry own memory
data behavior. The independent CLI/debug/scoring surface for MemorySystem core,
offline inspection, benchmark scoring, or operator-facing memory diagnostics is
out of scope and must be covered by a follow-up design document.

## Durable Decision

M6.25 introduces memory as an independent injectable subsystem. It does not put
memory storage, memory policy, prompt injection, chain recall, or memory
projection under `ToolRegistry`.

The first implementation target is deliberately small:

- `MemorySystem` is injectable and owns memory data behavior.
- `MemoryToolProvider` owns the provider-visible `recall` tool descriptor,
  JSON schema, handler, description, and schema hash.
- `ToolRegistry` remains the single source of truth for the final
  model-visible tool schema by accepting `MemoryToolProvider` as a tool
  provider input and including its descriptor only in the selected
  `ToolSurfaceSnapshot`.
- `MemoryRegistry` registers memory kinds, storage backends, graph indexes, and
  projection policies for `MemorySystem`; it never emits model-visible tool
  schema.
- `PromptSectionRegistry` is the separate surface for future memory prompt
  injection. v0 does not implement prompt injection.
- `recall` v0 is read-only, mock, and always returns an empty result.

No backward compatibility is required. The current task is design-only and must
not modify implementation code, tests, roadmap files, or unrelated docs.

## Architecture

```text
lane/runtime setup composition root
  - builds MemorySubsystemBundle through MemorySystemFactory
  - constructs MemoryToolProvider(memory_system=...)
  - passes provider inputs to ToolRegistry
  |
  v
provider request build
  |
  v
ToolRegistry
  - selects ToolSurfaceProfile
  - accepts registered ToolProvider inputs
  - builds the only model-visible tool schema snapshot
  - records descriptor/schema/route hashes
  |
  +--> codex_hot_path profile tools
  |      apply_patch, exec_command, write_stdin
  |      optional explicit list_dir
  |
  +--> MemoryToolProvider, only when explicitly enabled
         provider-visible tool: recall
         schema hash: memory_recall_tool_schema_v0 hash
         route: recall -> MemoryToolProvider.handle_recall

model emits recall tool call
  |
  v
ToolRegistry route validation
  - provider name must exist in current ToolSurfaceSnapshot
  - arguments must match recall schema
  - access class must be read
  |
  v
MemoryToolProvider.handle_recall(request)
  |
  v
MemorySystem.recall(request)
  - v0 implementation: EmptyMemorySystem
  - returns no candidates and no chain nodes
  - writes internal recall trace only
  |
  v
paired provider-visible recall output
  - candidates only
  - chain metadata only
  - dropped metadata only
  - no next_action / required_next / planner instruction
```

Separate non-tool data flow:

```text
raw provider request/response items
  -> native transcript / replay / provenance artifacts
  -> extraction + verification + approval
  -> short durable graph entry
  -> MemorySystem store / graph index
```

Raw API request/response item preservation is provenance and replay logging. It
is not durable memory. Durable memory is a short graph entry created only after
extraction, verification, and approval.

Future prompt injection has a separate route:

```text
MemorySystem projection
  -> PromptSectionRegistry
  -> bounded PromptSection entries
  -> provider request prompt sections
```

That route is not implemented in v0 and must not pass through `ToolRegistry`.

## Component Responsibilities

| Component | Owns | Must not own |
| --- | --- | --- |
| Lane/runtime setup composition root | Build `MemorySubsystemBundle`, choose `MemorySystemFactory`, wire `MemoryToolProvider(memory_system=...)`, pass provider inputs into ToolRegistry. | Provider-visible schema generation, memory recall policy, prompt injection, concrete tool routing after ToolRegistry snapshot creation. |
| `MemorySystem` | Store access, graph index, chain recall, read-side recall adaptation, projection generation, memory proposal/commit over extracted/verified/approved facts, memory trace facts. | Provider-visible tool schema, ToolRegistry profile selection, prompt-section injection, model next-action policy. |
| `MemoryToolProvider` | `recall` tool name, description, input schema, output schema, handler adapter, schema hash, route metadata, read-only access declaration. | Memory storage internals, graph policy registration, prompt injection, profile selection, tool-surface source of truth. |
| `ToolRegistry` | Final model-visible tool schema snapshot, provider-visible ordering, route table, descriptor hash, route hash, enabled tool snapshot, provider-visible tool list. | Memory store/index/projection, MemoryRegistry policy, raw memory extraction, prompt injection, planner instructions. |
| `MemoryRegistry` | Memory kind registry, backend registry, graph-index registry, projection policy registry, validation of memory-kind/backend compatibility. | Model-visible tool schema, provider-visible descriptions, ToolRegistry route entries, prompt section text. |
| `PromptSectionRegistry` | Future memory prompt-section registration, section ids, section hashes, stability/cache policy, prompt-injection gates. | Tool descriptors, callable tool handlers, ToolRegistry route decisions. |
| Native transcript/replay log | Complete raw API request/response preservation, replay, provenance, request/response item hashes. | Durable memory semantics, approved memory graph entries, model-visible memory content. |
| Extraction/verification/approval pipeline | Convert raw provenance into short approved graph entries. | Provider-visible recall schema, direct transcript injection into prompt/tool output. |

## MemorySystem Interface

The implementation may choose exact Python module names, but the boundary must
preserve this shape:

```python
class MemorySystem:
    system_id: str
    registry: MemoryRegistry

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        """Read-only recall over approved durable memory entries."""

    def adapt_recall(self, request: MemoryRecallAdaptRequest) -> MemoryRecallAdaptResult:
        """Read-side fit/drop step for recalled candidates in the current context."""

    def project(self, request: MemoryProjectionRequest) -> MemoryProjectionResult:
        """Build bounded projection data for PromptSectionRegistry, not ToolRegistry."""

    def propose_memory(self, request: MemoryProposalRequest) -> MemoryProposalResult:
        """Create proposed graph entries from extracted and verified facts."""

    def commit_memory(self, request: MemoryCommitRequest) -> MemoryCommitResult:
        """Persist approved proposed graph entries to the durable store/index."""

    def trace(self, event: MemoryTraceEvent) -> None:
        """Record internal observability for recall/adapt/propose/commit/project."""
```

Ownership rules:

- `MemorySystem.recall()` MUST be read-only.
- `MemorySystem.recall()` MUST read only approved durable memory entries.
- `MemorySystem.recall()` MUST NOT read raw native transcript items as memory.
- `MemorySystem.adapt_recall()` is the read-side "retrieve -> adapt ->
  bounded projection" step. It may filter, rank, deduplicate, or drop recalled
  candidates for the current request, but it MUST NOT create, update, approve,
  or persist memory entries.
- `MemorySystem.project()` MUST NOT be called by `ToolRegistry`.
- `MemorySystem.project()` MAY feed `PromptSectionRegistry` in a future phase.
- `MemorySystem.propose_memory()` and `MemorySystem.commit_memory()` are the
  write side. They MUST require extracted, verified facts and explicit approval
  before durable graph entries are committed.
- v0 MUST bind `MemorySystem` to an `EmptyMemorySystem` or equivalent mock that
  returns no candidates and performs no store/index lookup.

Conceptual owned internals:

```text
MemorySystem
  store: approved durable memory entries
  graph_index: nodes, typed edges, revision lineage
  chain_recall: bounded recall traversal
  recall_adaptation: read-side fit/drop over recalled candidates
  propose_memory: extracted/verified fact to proposed graph entry
  commit_memory: approved proposal to durable graph entry
  projection: bounded prompt-section projection producer
```

Terminology rule: do not use a single `revise()` method for both meanings.
Read-side recall adaptation is `adapt_recall()` or an equivalent
`revise_recall()` name. Write-side durable memory changes are
`propose_memory()` plus `commit_memory()` or equivalent separated proposal and
commit names.

## Composition Root And Injection

`MemorySystem` construction is owned by lane/runtime setup, not by
`ToolRegistry`.

Conceptual composition:

```python
class MemorySubsystemBundle:
    memory_system: MemorySystem
    memory_registry: MemoryRegistry
    memory_tool_provider: MemoryToolProvider


class MemorySystemFactory:
    def build(self, config: MemorySubsystemConfig) -> MemorySubsystemBundle:
        """Build memory registry, empty/real system, and provider wiring."""
```

Required wiring flow:

1. Lane/runtime setup reads explicit memory config/profile options.
2. `MemorySystemFactory` builds `MemoryRegistry` and the selected
   `MemorySystem` implementation. v0 selects `EmptyMemorySystem`.
3. Lane/runtime setup constructs
   `MemoryToolProvider(memory_system=bundle.memory_system, ...)`.
4. Lane/runtime setup passes `bundle.memory_tool_provider` as a provider input
   to `ToolRegistry` snapshot construction.
5. `ToolRegistry` sees only the provider protocol, provider id, descriptors,
   route entries, and schema hashes. It does not import concrete memory stores,
   graph indexes, factories, or backend config.

Composition close gate:

- `ToolRegistry` MUST NOT construct `MemorySystem`.
- `ToolRegistry` MUST NOT import `MemorySystemFactory`, concrete memory
  backends, graph indexes, extraction code, approval code, or projection code.
- `MemoryToolProvider` receives an already-built `MemorySystem`.
- v0 wiring MUST be satisfiable with an `EmptyMemorySystem` and no durable
  memory backend.

## MemoryToolProvider Interface

`MemoryToolProvider` is the only owner of the provider-visible recall tool
contract before it enters `ToolRegistry`.

Conceptual interface:

```python
class MemoryToolProvider:
    provider_id = "memory_tool_provider_v0"

    def __init__(self, memory_system: MemorySystem):
        """Receive an injected MemorySystem from lane/runtime setup."""

    def tool_specs(self, context: ToolProviderContext) -> tuple[ImplementLaneToolSpec, ...]:
        """Return recall spec only when memory recall is explicitly enabled."""

    def tool_schema_hash(self, tool_name: str) -> str:
        """Return stable hash for the recall descriptor and JSON schema."""

    def route_entries(self, context: ToolProviderContext) -> tuple[ToolRegistryEntry, ...]:
        """Return recall route metadata for ToolRegistry snapshot construction."""

    def handle_recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        """Validate request and delegate read-only recall to MemorySystem."""
```

Required `recall` descriptor facts:

```text
name: recall
access: read
description owner: MemoryToolProvider
input schema owner: MemoryToolProvider
result schema owner: MemoryToolProvider
handler owner: MemoryToolProvider
schema hash owner: MemoryToolProvider
internal dependency: MemorySystem
```

`MemoryToolProvider` MUST NOT register prompt text. It may expose a concise tool
description through `ToolRegistry`; that description is part of the
model-visible tool schema and is covered by the schema hash. It must not add
memory content to prompt sections.

## Provider Protocol

Memory tool integration uses a conceptual `ToolProviderProtocol`. This is a
registry input protocol, not a second registry and not a model-visible schema
path.

Conceptual protocol:

```python
class ToolProviderProtocol:
    provider_id: str

    def tool_specs(self, context: ToolProviderContext) -> tuple[ImplementLaneToolSpec, ...]:
        """Return provider-owned specs to merge into ToolSurfaceSnapshot."""

    def route_entries(self, context: ToolProviderContext) -> tuple[ToolRegistryEntry, ...]:
        """Return provider-owned route entries for the same visible specs."""

    def tool_schema_hash(self, tool_name: str) -> str:
        """Return a stable hash for the provider-owned descriptor/schema."""
```

`tool_schema_hash()` is required for every provider-visible tool returned by
`tool_specs()`. A provider may also expose a batch form such as
`schema_hashes(context)`, but the registry artifact must still contain a stable
per-tool hash.

Conceptual context:

```text
ToolProviderContext
  profile_id: string
  profile_version: string
  prompt_contract_id: string
  render_policy_id: string
  mode: string
  profile_options: mapping
  available_provider_tool_names: optional list[string]
  provider_supports_parallel_tool_calls: boolean
  memory_recall_enabled: boolean
  memory_system_id: optional string
  memory_registry_hash: optional string
```

`ToolProviderContext` is a new dataclass/protocol wrapper built by
`ToolRegistry` during snapshot construction. It is not just raw
`tool_surface_profile_options`. `profile_options` is one field inside the
context; derived booleans such as `memory_recall_enabled` must be computed by
the registry from explicit profile/profile-option input before providers see
the context. Providers may read the context, but they must not mutate it.

Provider constraints:

- Providers MUST return descriptors/routes only for tools they own.
- Providers MUST NOT return prompt sections, memory content, planner guidance,
  or raw transcript material.
- Providers MUST NOT decide the selected profile.
- Providers MUST NOT write to `ToolSurfaceSnapshot` directly.
- Providers MUST return no specs and no routes when their explicit enablement
  flag is false.

`ToolRegistry` calls providers inside the existing
`build_tool_surface_snapshot(...)` flow, after selecting the profile and
normalizing profile options, and before descriptor/route/render hashes are
computed. It merges provider specs into the same ordered `tool_specs`,
`provider_tool_names`, `entries`, descriptor hash, route table hash, render
policy hash, and request metadata used by existing profile tools. A provider
descriptor that is not merged into this `ToolSurfaceSnapshot` does not exist for
the model.

## ToolRegistry Integration Contract

`ToolRegistry` remains the unified source of truth for model-visible tool
schema. Provider ownership does not create a second source of truth; it creates
an input that the registry snapshots.

Required integration contract:

1. `MemoryToolProvider` is registered as a provider input to `ToolRegistry`.
2. `ToolRegistry` asks registered providers for descriptors during snapshot
   construction.
3. `ToolRegistry` includes `recall` in `ToolSurfaceSnapshot.tool_specs`,
   `provider_tool_names`, descriptor hash, route table hash, render policy hash,
   and request metadata only when explicitly enabled.
4. `ToolRegistry` routes a provider-visible `recall` call only when the current
   snapshot contains `recall`.
5. Unknown or disabled `recall` calls receive the normal paired unknown-tool
   output; they must not bypass registry routing.
6. The enabled tool snapshot is the only authority for what the model can see.
7. The default `codex_hot_path` tool list MUST remain:
   `apply_patch`, `exec_command`, `write_stdin`.
8. `list_dir` remains explicitly gated as already designed.
9. `recall` MUST be explicitly gated separately, for example by a future
   `tool_surface_profile_options.enable_memory_recall_v0 == true` or a future
   profile/extension with equivalent explicit selection.
10. Enabling memory recall MUST NOT change codex hot-path developer-contract
    behavior for source edits, command execution, or completion.

The registry may import a provider protocol. It MUST NOT import concrete memory
stores, graph indexes, `MemorySystemFactory`, extraction logic, approval logic,
projection logic, or prompt-injection policy.

Minimum snapshot metadata when `recall` is enabled:

```json
{
  "provider_tool_names": ["apply_patch", "exec_command", "write_stdin", "recall"],
  "tool_provider_ids": ["codex_hot_path_profile_v1", "memory_tool_provider_v0"],
  "memory_recall_schema_hash": "sha256:...",
  "descriptor_hash": "sha256:...",
  "route_table_hash": "sha256:...",
  "provider_visible_tool_list_hash": "sha256:..."
}
```

Exact field placement may follow existing `ToolSurfaceSnapshot` conventions,
but the facts must be present in request metadata and registry artifacts.

## MemoryRegistry Responsibility

`MemoryRegistry` is configuration and validation for memory data behavior.

Required registry records:

```text
MemoryKindRegistration
  memory_kind: string
  schema_version: string
  allowed_scopes: list[string]
  backend_id: string
  graph_index_id: string
  projection_policy_id: string
  retention_policy_id: string
  approval_policy_id: string

MemoryBackendRegistration
  backend_id: string
  backend_kind: file | sqlite | other
  read_capabilities: list[string]
  write_capabilities: list[string]

MemoryProjectionPolicyRegistration
  projection_policy_id: string
  target_surface: prompt_section
  max_entries: integer
  max_chars: integer
  allowed_fields: list[string]
```

`MemoryRegistry` MUST NOT:

- emit provider-visible tool descriptors;
- choose provider-visible tool names;
- compute ToolRegistry descriptor hashes;
- register prompt sections directly into a provider request;
- encode next-action or planner policy.

## Recall Request Shape

Provider-visible `recall` input schema v0:

```json
{
  "schema_version": 1,
  "query": "string, required, 1..512 chars",
  "memory_kinds": ["optional list of registered memory_kind strings, max 8"],
  "limit": "optional integer, 0..20, default 5",
  "chain": {
    "max_hops": "optional integer, v0 must be 0",
    "include_dropped": "optional boolean, default true"
  }
}
```

Normative constraints:

- `query` is search text, not an instruction.
- `memory_kinds` filters approved durable memory kinds only.
- `limit` caps candidates, not chain hops.
- `chain.max_hops` MUST be accepted only as `0` in v0.
- Any unsupported field MUST fail schema validation or be ignored according to
  the existing provider schema strictness mode, but it must not affect recall.
- Request fields MUST NOT include `next_action`, `required_next`,
  `planner_instruction`, `goal_override`, or equivalent steering fields.

Example v0 call:

```json
{
  "schema_version": 1,
  "query": "ToolRegistry memory provider boundary",
  "memory_kinds": ["design-decision"],
  "limit": 5,
  "chain": {
    "max_hops": 0,
    "include_dropped": true
  }
}
```

## Recall Result Shape

Provider-visible `recall` result schema v0:

```json
{
  "schema_version": 1,
  "result_kind": "memory_recall_result",
  "candidates": [],
  "chains": [],
  "dropped": []
}
```

Future-compatible candidate shape:

```json
{
  "id": "mem_...",
  "memory_kind": "design-decision",
  "title": "short title",
  "summary": "short approved memory summary",
  "evidence": {
    "source": "approved_memory_entry",
    "provenance_ref": "prov_..."
  },
  "score": 0.0,
  "revision": {
    "entry_version": 1,
    "supersedes": []
  }
}
```

Future-compatible chain shape:

```json
{
  "chain_id": "chain_...",
  "root_candidate_id": "mem_...",
  "nodes": ["mem_..."],
  "edges": [
    {
      "from": "mem_...",
      "to": "mem_...",
      "edge_kind": "supports | revises | supersedes | related",
      "score": 0.0
    }
  ],
  "truncated": false
}
```

Future-compatible dropped shape:

```json
{
  "reason": "duplicate | policy_denied | stale_revision | chain_limit | unsupported_kind | raw_transcript_not_memory",
  "count": 0
}
```

Provider-visible recall results MUST NOT contain:

- `next_action`;
- `required_next`;
- `planner_instruction`;
- `should_edit`;
- `should_run`;
- `finish_ready`;
- `tool_to_call`;
- imperative instructions telling the model what to do next;
- raw transcript items;
- complete provider API request/response items;
- unapproved memory candidates.

The internal recall trace may record request hash, result hash, backend ids,
drop reasons, timing, and store/index calls. The provider-visible result should
remain only candidates, chain metadata, and dropped metadata.

## Chain Recall Evolution

v0:

- `recall` tool may be visible only under explicit enablement.
- Handler is read-only.
- Handler is mock/empty.
- `chain.max_hops` must be `0`.
- Result always has empty `candidates`, empty `chains`, and empty `dropped`.
- No store read, graph-index traversal, prompt injection, or memory projection.

v1:

- Enable approved store reads for exact/lexical recall.
- Return bounded candidate summaries from approved durable memory entries.
- Preserve v0 output envelope.
- `chain.max_hops` may remain `0`.
- Dropped reasons become meaningful for policy-denied, duplicate, stale, and
  unsupported-kind candidates.

v1.5:

- Enable one-hop graph traversal behind `chain.max_hops == 1`.
- Return chain nodes and typed edges.
- Enforce bounded chain count, node count, and summary chars.
- Still no prompt injection unless the separate PromptSectionRegistry feature
  is explicitly implemented and gated.

v2:

- Add projection policies that can feed PromptSectionRegistry.
- Add optional `MemoryExploreProvider` integration as a separate provider or
  explore subsystem extension.
- Keep tool recall, prompt projection, and memory exploration as separate
  surfaces with separate gates and observability.

## Mock Recall V0 Close Gate

M6.25 v0 may close only when all of the following are true:

1. `MemorySystem` exists as an injectable subsystem boundary or equivalent
   design-approved interface.
2. `MemoryToolProvider` owns the `recall` descriptor, schema, handler, and
   schema hash.
3. `ToolRegistry` is the only source of the final provider-visible tool schema.
4. Default `codex_hot_path` remains exactly `apply_patch`, `exec_command`,
   `write_stdin`.
5. `recall` appears only under explicit memory-recall enablement.
6. A `recall` call returns exactly the v0 empty envelope:
   `candidates=[]`, `chains=[]`, `dropped=[]`.
7. v0 recall performs no write and no durable memory read.
8. v0 recall emits an internal trace record with schema hash, request hash,
   result hash, enabled tool snapshot hash, and dropped-reason summary.
9. Provider-visible recall output contains no `next_action`, `required_next`,
   planner instruction, raw transcript item, or complete API request/response
   item.
10. No prompt section includes memory content in v0.
11. No implementation change pollutes `implement_v2` codex hot-path behavior,
    developer contract, result rendering, finish handling, or command lifecycle.

## Observability

Required observability facts:

- `memory_recall_schema_hash`: stable hash of the `recall` description and JSON
  schema owned by `MemoryToolProvider`.
- `enabled_tool_snapshot`: provider-visible tool names, provider ids, descriptor
  hash, route table hash, render policy hash, and profile id for the request.
- `provider_visible_tool_list`: ordered list of tool names sent to the provider.
- `provider_visible_tool_list_hash`: stable hash of that ordered list.
- `recall_trace`: internal JSONL artifact for each recall call.
- `dropped_reasons`: structured counts by reason in internal trace; provider
  result includes only bounded dropped metadata.
- `memory_system_id`: identifies mock/empty v0 versus future real systems.
- `memory_registry_hash`: hash of memory kind/backend/projection registrations
  used by the MemorySystem for the run.

Conceptual internal trace record:

```json
{
  "schema_version": 1,
  "trace_kind": "memory_recall_trace",
  "tool_call_id": "call_...",
  "memory_system_id": "empty_memory_system_v0",
  "memory_tool_provider_id": "memory_tool_provider_v0",
  "memory_recall_schema_hash": "sha256:...",
  "enabled_tool_snapshot_hash": "sha256:...",
  "request_hash": "sha256:...",
  "result_hash": "sha256:...",
  "candidate_count": 0,
  "chain_count": 0,
  "dropped_reasons": {},
  "store_reads": 0,
  "store_writes": 0,
  "prompt_projection_emitted": false
}
```

The trace is an internal artifact. It is not itself memory and must not be
injected into the model as recalled content.

## Safety Requirements

Read-only guarantee:

- `recall` access class MUST be `read`.
- v0 handler MUST NOT call `adapt_recall()` unless it is adapting the empty v0
  result in-memory, and MUST NOT call `propose_memory()`, `commit_memory()`,
  approval, extraction, backend write, or projection code.
- v0 handler MUST NOT mutate store, graph index, lane state, transcript, or
  prompt sections except for normal paired tool output and internal trace.

Prompt injection separation:

- v0 MUST NOT inject memory into any prompt section.
- Future prompt injection MUST enter through `PromptSectionRegistry`, with
  section ids, hashes, stability, cache policy, char bounds, and leak gates.
- ToolRegistry MUST NOT be used as a prompt-injection path.

Raw transcript safety:

- Raw native transcript items and complete provider API request/response items
  are provenance/replay logs, not durable memory.
- Durable memory entries MUST be short graph entries after
  extraction/verification/approval.
- Recall results MUST NOT include raw transcript text, complete request JSON, or
  complete response JSON.

No memory-driven planner:

- Recall output MUST NOT prescribe the next tool call.
- Recall output MUST NOT contain `next_action`, `required_next`, or renamed
  equivalents.
- Memory candidates are evidence/context only. The model remains responsible
  for deciding how to use them under the normal task/tool contract.

## Tests And Static Gates Before Implementation

Required static gates:

- Scan `src/mew/implement_lane/tool_registry.py` and registry-adjacent modules
  for forbidden concrete memory imports: store, graph index, extraction,
  projection, prompt-injection policy, `MemorySystemFactory`, and concrete
  backend config.
- Scan `ToolRegistry` and provider protocol code for direct construction of
  `MemorySystem`; none allowed.
- Scan `MemorySystem` interface for an ambiguous single `revise()` method; none
  allowed. Read-side adaptation and write-side proposal/commit must remain
  separately named.
- Scan `MemoryRegistry` implementation for provider-visible schema generation
  calls; none allowed.
- Scan `MemoryToolProvider` result schema and render output for forbidden
  fields: `next_action`, `required_next`, `planner_instruction`,
  `tool_to_call`, `should_edit`, `should_run`.
- Scan prompt section builders for v0 memory content injection; none allowed.
- Assert default `codex_hot_path` provider-visible names remain exactly
  `["apply_patch", "exec_command", "write_stdin"]`.
- Assert `recall` is absent from default `codex_hot_path`.
- Assert `recall` is present only when explicit memory recall enablement is set.

Required unit/contract gates:

- Golden JSON schema test for `recall` request and result.
- Golden schema hash test for `memory_recall_tool_schema_v0`.
- ToolRegistry snapshot test proving descriptor hash and route table hash change
  only under explicit recall enablement.
- Route test proving disabled `recall` gets the normal unknown-tool paired
  output.
- Handler test proving v0 returns empty candidates/chains/dropped for any valid
  request.
- Handler test proving `chain.max_hops > 0` is rejected or normalized to v0
  failure according to strictness mode.
- Side-effect test proving v0 has `store_reads=0` and `store_writes=0`.
- Trace test proving internal recall trace records schema hash, enabled tool
  snapshot hash, request hash, result hash, dropped reasons, and provider list.
- Leak test proving provider-visible recall output contains no raw transcript,
  complete API request/response item, prompt text, or planner fields.
- Prompt test proving no memory prompt section is emitted in v0.

Required integration gates:

- Build a provider request with default `codex_hot_path`; assert no recall.
- Build a provider request with explicit memory recall v0 enabled; assert
  `recall` appears in the enabled tool snapshot and request descriptor.
- Execute a mock `recall` tool call; assert exactly one paired tool output is
  appended.
- Verify replay/provenance logs preserve raw API items separately from memory
  artifacts.
- Verify implement-lane hot-path tests do not need update when memory recall is
  disabled.
- Verify lane/runtime setup can construct a v0 `MemorySubsystemBundle` with an
  `EmptyMemorySystem`, inject it into `MemoryToolProvider`, and pass only the
  provider input to ToolRegistry.

## Explicit Non-Goals

- No implementation code change in this task.
- No CLI/debug/scoring adapter design in this document; that belongs in the
  follow-up MemorySystem core plus CLI/debug/scoring design.
- No real memory retrieval in v0.
- No embedding index in v0.
- No graph traversal in v0.
- No prompt injection in v0.
- No raw transcript injection as memory.
- No complete API request/response item as durable memory.
- No provider-visible planner, next-action tool, or required-next memory field.
- No backward compatibility requirement.
- No change to default `codex_hot_path` tool names.
- No change to finish handling, CompletionResolver, WorkFrame projection,
  command lifecycle, or tool result rendering.
- No migration of existing `MemoryExploreProvider` behavior into
  `ToolRegistry`.
- No `MemoryRegistry` authority over model-visible tool schema.
- No `ToolRegistry` authority over memory store/index/projection policy.
- No `ToolRegistry` construction of `MemorySystem`, `MemorySystemFactory`, or
  concrete memory backends.
