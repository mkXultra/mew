# Design 2026-05-20 - M6.25 Memory Core And Evaluation

Status: pre-implementation design only.

Scope: define the M6.25 MemorySystem core, direct debug/scoring boundary,
MemoryArena and Harbor resident-memory evaluation plan, and the phase ordering
that must close before memory is wired into `implement_v2` through a thin
`MemoryToolProvider(recall)` adapter.

This document does not authorize implementation code changes. It is the design
successor for the part that
`docs/DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md` explicitly left
out: the independent MemorySystem core, offline/debug/scoring surface, and
evaluation gates.

## Problem And Design Stance

The current M6.25 problem is not "add a recall tool to the model". The recall
tool is only useful after mew has a memory core worth calling.

The resident-advantage goal requires a small, typed, cited, stale-aware memory
subsystem that can prove it improves later work without polluting the ordinary
`implement_v2` hot path. A premature prompt projection or provider-visible
tool can make the product look smarter for one run while hiding unverified
memory, stale facts, or raw transcript instructions in the model context.

The design stance is therefore:

```text
MemorySystem core first
  -> direct debug/scoring/benchmark recall
  -> MemoryArena + Harbor resident evaluation
  -> thin MemoryToolProvider(recall)
  -> read-only implement_v2 connection
```

`MemoryToolProvider(recall)` is Phase 4+ adapter work. It is not the main actor
for MemorySystem core v0/v1.

Prompt injection is a non-goal for this stage. v0/v1 must not constantly inject
memory into prompts. If future work injects memory into provider requests, it
must go through `PromptSectionRegistry` with explicit section ids, hashes,
budgets, and gates.

## Relationship To MemorySystem Tool Provider Design

`docs/DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md` defines how a
provider-visible `recall` tool can enter the `ToolRegistry` surface without
making `ToolRegistry` own memory behavior.

This document defines what must exist before that adapter is worth exposing:

- durable memory entry schema;
- provenance references;
- candidate/proposal/approval/commit write path;
- direct read-only recall API;
- chain expansion API;
- staleness and contradiction metadata;
- CLI/debug/scoring boundary callable without `implement_v2`;
- MemoryArena and Harbor resident-memory evaluation gates.

The two documents have different centers of gravity:

| Document | Main actor | Scope |
| --- | --- | --- |
| `MEMORY_SYSTEM_TOOL_PROVIDER` | `MemoryToolProvider` plus `ToolRegistry` | Provider-visible `recall` descriptor, schema, route, hash, and explicit tool-surface enablement. |
| This document | `MemorySystem` | Durable memory lifecycle, direct recall/evaluation APIs, scoring/debug boundary, and close gates before tool exposure. |

Both documents preserve the same invariants:

- `ToolRegistry` remains the source of truth for model-visible tool schema.
- `MemorySystem` owns memory data behavior.
- raw transcript/provenance is not durable memory.
- recall output is evidence/context only.
- prompt projection is future work through `PromptSectionRegistry`, not through
  `ToolRegistry`.

### API Naming And Phase Reconciliation

The companion ToolProvider design uses the names `propose_memory()` and
`commit_memory()` for the MemorySystem write side. This document's four-state
write path is the same boundary with the internal gate made explicit:

| Core state in this document | ToolProvider-design method relationship | Rule |
| --- | --- | --- |
| candidate | before `propose_memory()` | Extracted or deterministic possible memory. Not durable and not recallable. |
| proposal | result of `propose_memory()` | Typed proposed entry with source/proof refs, scope, validity, staleness, and contradiction metadata. Still not committed. |
| approved proposal | internal approval gate before `commit_memory()` | Approval is a MemorySystem/core gate. It may be user, reviewer, or policy approval depending on memory kind. |
| committed entry | result of `commit_memory()` | Durable approved entry persisted to store/index and eligible for recall. |

`propose_memory()` and `commit_memory()` are not model-visible tools in M6.25
v0/v1. They are MemorySystem methods. `MemoryToolProvider(recall)` in Phase 4
must not expose write authority.

`adapt_recall()` belongs to the MemorySystem read side. It is allowed in Phase
1 as a core fit/drop/rerank operation after seed recall and before a result is
returned to debug/scoring callers. It must not create, approve, or persist
memory.

`project()` belongs to the future prompt-projection layer. Phase 1 may freeze
its conceptual shape so the core is not painted into a corner, but Phase 1-3
do not use it for production prompt injection. Any future production prompt
projection must route through `PromptSectionRegistry`; `ToolRegistry` and
`MemoryToolProvider(recall)` must not become prompt-injection paths.

## Definitions And Boundaries

### Raw Provenance Is Not Durable Memory

Raw provider requests, provider responses, native transcript items, tool
results, verifier logs, reviewer comments, and replay bundles are provenance.
They are necessary for audit, replay, candidate extraction, and evidence refs.
They are not memory entries by themselves.

Durable memory is a short typed entry created only after extraction, validation,
scope decision, contradiction/freshness checks, and approval. It keeps links
back to provenance, but it does not copy unbounded transcript text into the
memory store.

```text
raw transcript / tool output / verifier result
  -> provenance artifact with stable refs and hashes
  -> extracted candidate
  -> gate and approval
  -> durable memory entry
```

### Memory Entry

A memory entry is an approved durable record that can be recalled as evidence.
It must be small, scoped, typed, versioned, and cited.

Initial memory kinds should stay coding-agent oriented:

- `project_convention`
- `episodic_task`
- `procedural_repair`
- `failure_shield`
- `reviewer_correction`
- `file_symbol_edge`
- `user_preference`

The exact enum can be finalized during implementation, but the schema must not
collapse every kind into generic prose. Different kinds have different write
gates, staleness rules, and recall budgets.

### Candidate / Proposal / Approval / Commit

The write path is not automatic append.

Use separate states:

| State | Meaning |
| --- | --- |
| candidate | Extracted possible memory from provenance or deterministic analysis. Not durable. Not recallable as approved memory. |
| proposal | Candidate normalized into a typed entry shape with refs, scope, and gate evidence. Still not committed. |
| approved proposal | Proposal accepted by user, reviewer, or explicit policy gate appropriate to its kind. |
| committed entry | Durable memory entry persisted to store/index and eligible for read-only recall. |

No v0/v1 path should silently convert model prose or tool output into durable
memory without this candidate/proposal/approval/commit separation.

### Recall Is Evidence, Not Policy

`MemorySystem.recall()` returns evidence/context:

- candidate summaries;
- source/proof refs;
- relevance and confidence metadata;
- staleness/contradiction state;
- chain nodes and typed edges when requested;
- dropped metadata.

It must not return:

- `next_action`;
- `required_next`;
- planner instruction;
- `tool_to_call`;
- `should_edit`;
- `finish_ready`;
- hidden chain-of-thought;
- raw transcript dumps;
- unapproved candidates.

The caller remains responsible for deciding what to do after reading evidence.

### Chain Expansion

Chain expansion is bounded traversal after seed recall. It is not graph dump
and not a second planner.

Useful edge kinds for M6.25 include:

- `derived_from`
- `supersedes`
- `contradicts`
- `same_task_shape`
- `failure_cluster`
- `file_symbol`
- `reviewer_correction`
- `supports`

Traversal must have explicit depth, fanout, node, character/token, and latency
budgets. Dropped nodes must be counted by reason.

## Phase 1 - Build MemorySystem Core

Goal: create the independent MemorySystem core boundary that can be used by
debug/scoring CLI and benchmark fixtures without `implement_v2` or
`ToolRegistry`.

This phase is about interfaces, stores, validation rules, and observability. It
does not expose a provider-visible recall tool and does not inject memory into
prompts.

Phase 1 is intentionally split so the first implementation does not become a
large memory product in one step:

- Phase 1a: schema, store boundary, read-only recall, inspect, and trace.
- Phase 1b: candidate, proposal, approval, commit, and revision/tombstone
  write path.
- `project()` remains dormant/interface-only or explicitly deferred until a
  separate PromptSectionRegistry design authorizes production prompt
  projection.

### Required Data Model

Conceptual durable entry shape:

```text
MemoryEntry
  entry_id
  schema_version
  memory_kind
  scope
  title
  summary
  applicability
  source_refs
  proof_refs
  created_at
  last_verified_at
  validity
  confidence
  staleness
  contradiction
  revision
  graph_edges
  budgets
```

Required provenance ref shape:

```text
ProvenanceRef
  ref_id
  ref_kind
  artifact_path_or_uri
  content_hash
  excerpt_hash
  timestamp
  producer
```

`source_refs` identify where the candidate came from. `proof_refs` identify
why the entry is trusted, for example verifier output, reviewer approval, user
approval, commit hash, or static analysis proof.

Required staleness/contradiction metadata:

```text
Staleness
  state: fresh | maybe_stale | stale | superseded
  reasons
  invalidators
  checked_at

Contradiction
  state: none | possible | contradicted
  contradicting_entry_ids
  contradicting_provenance_refs
  resolution
```

For coding memory, staleness is not only age. It can be caused by file changes,
symbol moves, verifier changes, task contract changes, user preference changes,
reviewer vetoes, or model/tool-surface changes.

### Required APIs

The implementation may choose exact Python names and module placement, but the
boundary must preserve these operations:

```text
MemorySystem.write_candidate(request) -> candidate result
MemorySystem.propose_memory(request) -> proposal result
MemorySystem.approve(request) -> approval result
MemorySystem.commit_memory(request) -> commit result
MemorySystem.recall(request) -> recall result
MemorySystem.adapt_recall(request) -> adapted recall result
MemorySystem.expand_chain(request) -> chain result
MemorySystem.project(request) -> projection result for future PromptSectionRegistry use
MemorySystem.inspect_entry(request) -> entry/debug result
MemorySystem.trace(event) -> no provider-visible output
```

Required constraints:

- `recall` and `expand_chain` are read-only.
- `recall` reads only committed approved durable entries.
- `recall` must not read raw native transcript items as memory.
- write APIs must preserve candidate/proposal/approval/commit separation.
- `commit_memory` must require an approved proposal and must be auditable and
  reversible by later revision/tombstone metadata.
- `adapt_recall` is read-side only. It may filter, rank, deduplicate, or drop
  candidates for the current context, but it must not mutate memory.
- `project` is dormant for Phase 1-3 production paths. It may be defined as a
  future PromptSectionRegistry-facing boundary, but it must not be called by
  `ToolRegistry` or `MemoryToolProvider(recall)`.
- all APIs must be callable directly from debug/scoring contexts without a
  model-visible native tool.

### Recall Request And Result Contract

Core recall request, conceptual:

```text
MemoryRecallRequest
  query
  scope
  memory_kinds
  evidence_filters
  current_context_refs
  limit
  include_stale
  chain_request
  budget
```

Core recall result, conceptual:

```text
MemoryRecallResult
  candidates
  chains
  dropped
  trace_ref
  timing
  budget_used
```

Candidate result fields:

```text
candidate
  entry_id
  memory_kind
  scope
  title
  summary
  why_relevant
  evidence_refs
  proof_refs
  validity
  confidence
  staleness
  contradiction
  score
```

The core result may include debug-only trace refs and timing. Provider-visible
Phase 4 output must be stricter and narrower, as defined by the tool-provider
design.

### Phase 1a Close Gate

Phase 1a closes only when:

- durable entry, provenance ref, staleness, contradiction, revision, and graph
  edge shapes are specified in implementation-facing schema or dataclass form;
- direct read-only `recall` API exists;
- direct `inspect_entry` or equivalent debug-read API exists;
- trace output records request hash, result hash, store/index ids, timing,
  budget use, and dropped reasons;
- recall output contains evidence/context only and no next-action or planner
  fields;
- raw transcript/provenance cannot be returned as durable memory;
- core read APIs can be called without constructing `implement_v2`,
  `ToolRegistry`, or `MemoryToolProvider`;
- no prompt injection or provider-visible recall tool is required to use the
  core.

### Phase 1b Close Gate

Phase 1b closes only when:

- Phase 1a is closed;
- candidate/proposal/approval/commit write separation exists;
- `propose_memory` and `commit_memory` names are aligned with the companion
  ToolProvider design, with approval explicitly required before commit;
- direct read-only `adapt_recall` API exists or is explicitly folded into
  `recall` with equivalent fit/drop trace fields;
- direct bounded `expand_chain` API exists;
- `project` is either defined as a dormant future PromptSectionRegistry-facing
  API or explicitly deferred with no production caller;
- write APIs can be called from debug/scoring contexts without constructing
  `implement_v2`, `ToolRegistry`, or `MemoryToolProvider`;
- committed entries are auditable and reversible by later revision/tombstone
  metadata.

## Phase 2 - Make CLI And Benchmarks Call Memory Directly

Goal: let scoring, debug, MemoryArena harnesses, and Harbor resident fixtures
call `MemorySystem.recall()` and `MemorySystem.expand_chain()` directly.

This phase intentionally avoids the implement lane. It proves that memory core
can be inspected and scored as a subsystem before asking the model to call it
as a native tool.

### Direct Boundary

The direct boundary should support:

- query by text, path, symbol, task shape, memory kind, and scope;
- seed fixture memory stores from explicit approved entries;
- run memory-off and memory-on comparisons with the same task fixture;
- emit machine-readable recall traces;
- print human-readable debug summaries;
- inspect why candidates were dropped;
- inspect chain expansion and truncation;
- measure latency and result size.

Conceptual commands or callable harness operations:

```text
memory recall --store ... --query ... --kind ... --scope ... --json
memory chain --store ... --entry ... --max-hops ... --json
memory inspect --store ... --entry ...
memory score --fixture ... --mode memory_off|memory_on|stale
```

These are boundary sketches, not implementation commands. Exact CLI names may
follow existing repo conventions.

### Required Fixture Use

MemoryArena and Harbor fixtures must be able to call memory directly:

- not through `implement_v2`;
- not through a provider-visible model tool;
- not through prompt injection;
- not by asking the model whether it used memory.

For Harbor resident-memory fixtures, the memory condition should be represented
as fixture/campaign data:

- `memory_off`: empty store or disabled recall;
- `memory_on`: approved entries seeded from prior step/campaign state;
- `stale`: approved but stale/misleading entries plus current evidence that
  should cause rejection or downgrade.

### Close Gate

Phase 2 closes only when:

- debug/scoring code can call memory core APIs directly;
- direct calls produce both JSON artifacts and readable summaries;
- MemoryArena-style task harnesses can seed and query approved memory without
  `implement_v2`;
- Harbor resident-memory fixtures can seed and query approved memory without
  `implement_v2`;
- memory-off, memory-on, and stale modes are explicit and artifact-visible;
- recall traces include evidence hits, dropped reasons, stale/contradiction
  metadata, latency, and size;
- no model prompt is modified by enabling direct scoring/debug recall.

## Phase 3 - Evaluate Memory Core

Goal: prove that the core improves downstream task behavior and remains safe
enough to expose as a native read-only recall surface later.

This phase has two evaluation anchors:

- generic agentic memory evaluation through MemoryArena-style tasks;
- mew-specific coding resident evaluation through Harbor resident-memory
  fixtures.

MemoryArena is useful because it measures whether memory helps later action in
interdependent multi-session tasks. Harbor is required because mew's product
claim is coding-resident advantage.

### Evaluation Modes

Every accepted evaluation row should declare:

```text
memory_mode: off | on | stale
task_family
task_id
phase_or_session
store_id
memory_snapshot_hash
recall_config_hash
model_or_runner_config_hash
```

Required comparisons:

- memory off baseline;
- memory on;
- stale or contradictory memory;
- optional chain expansion off/on when chain recall lands.

### Required Metrics

Generic memory metrics:

- recall evidence hit rate;
- Recall@k or equivalent fixture-specific hit metric;
- stale recall rate;
- contradiction rate;
- dropped count by reason;
- abstention or no-hit correctness when no approved memory should apply;
- recall latency;
- chain expansion latency;
- returned character/token size;
- store/index read count;
- useful-recall ratio.

Downstream task metrics:

- task success;
- verifier pass/fail;
- first useful action latency when measurable;
- time to first edit when applicable;
- number of repeated searches or reads;
- number of repeated failed approaches;
- reviewer rescue required;
- pass@1 or repeated-run consistency where practical;
- token overhead or prompt overhead, if any future prompt projection is tested.

Memory quality metrics:

- write precision: approved committed entries divided by proposed entries;
- important-event miss rate for candidates expected by fixtures;
- stale invalidation latency;
- contradiction resolution rate;
- rollback/tombstone correctness.

### MemoryArena Plan

Use MemoryArena-style evaluation to test the core outside mew-specific coding
assumptions.

Minimum MemoryArena-oriented questions:

- Does direct recall return the memory evidence needed for the later session?
- Does chain expansion improve evidence hits without excessive stale or
  irrelevant expansion?
- Does stale or contradictory memory get dropped or labeled instead of treated
  as fresh?
- Does memory-on improve task success or reduce repeated exploration compared
  with memory-off?
- Does memory-on stay within latency and result-size budgets?

MemoryArena rows do not replace Harbor rows. They are a generic subsystem
sanity check.

Initial Phase 3 implementation command:

```bash
./mew memory-core memory-arena-score \
  --input path/to/memoryarena-export.jsonl \
  --mode memory_on \
  --limit-rows 20 \
  --artifact proof-artifacts/memory/memoryarena-memory-on.json \
  --json
```

The command also supports `--mode memory_off` and `--mode stale`. It accepts a
local JSON/JSONL export by default so the scoring loop stays deterministic in
unit tests and offline debugging. Optional Hugging Face loading is exposed with
`--hf-config`, `--hf-split`, and `--hf-revision`, but it intentionally depends
on an environment that has the optional `datasets` package installed; the core
mew package does not add that dependency yet.

V0 scoring is a direct `MemorySystem` benchmark. It does not call a model, does
not touch `implement_v2`, and does not use production prompt injection. The
artifact records `runner_boundary`, `runner_config_hash`, row-level recall
traces, and aggregate recall/staleness/latency metrics.

### Harbor Resident-Memory Plan

Use the `resident-golden-convention-recall` style task as the mew-specific
resident coding evaluation anchor.

2026-05-20 decision update: keep this as a future evaluation anchor, but do
not implement an external Harbor resident campaign runner as the next step.
Running memory-on/off through an outside runner is not a strong enough proof
until `implement_v2` has a real memory surface. The next active work is to
connect memory to the implement lane in a bounded, inspectable way; Harbor
resident evaluation resumes after that integration exists.

The Harbor fixture should remain independently solvable by ordinary inspection.
Memory is expected to improve speed, reliability, or stale-memory rejection,
not to reveal hidden verifier answers.

Required Harbor comparisons:

- Step A seed run with memory off, producing provenance and candidate material.
- Step B recall run with memory off baseline.
- Step B recall run with memory on, seeded only with approved durable memory.
- Step C stale run with stale or misleading memory present.

### Deferred Harbor Benchmark Evidence Delivery Channel

Status: deferred until implement-lane memory integration exists.

Phase 3 has two separate activities:

1. direct MemorySystem scoring, where the harness calls `recall`,
   `adapt_recall`, and optional `expand_chain` and scores the returned evidence
   without giving it to a coding agent;
2. downstream Harbor evaluation, where a coding agent must be able to observe
   bounded memory evidence so memory-on can affect behavior.

The downstream Harbor activity uses a benchmark-only evidence channel:

```text
MemorySystem.recall/adapt_recall
  -> BenchmarkMemoryEvidencePacket
  -> resident campaign runner benchmark_memory_evidence section or read-only fixture artifact
  -> Harbor task agent
```

`BenchmarkMemoryEvidencePacket` is not production prompt injection. It is a
campaign artifact used only for Phase 3 evaluation rows. It must be:

- generated from approved committed memory through direct MemorySystem APIs;
- artifacted with packet hash, memory snapshot hash, recall config hash,
  source memory ids, and dropped reasons;
- bounded to at most 3 memory items and 1200 UTF-8 characters by default;
- labeled as memory evidence, not instructions;
- forbidden from containing `next_action`, planner policy, raw transcript,
  hidden verifier answers, or unapproved candidates;
- disabled for ordinary `implement_v2` requests;
- independent from `ToolRegistry` and `MemoryToolProvider(recall)`;
- replaced by a separate `PromptSectionRegistry` design before any production
  prompt projection is allowed.

Required anti-leak gates:

- ordinary `implement_v2` provider requests MUST NOT contain
  `BenchmarkMemoryEvidencePacket`, `benchmark_memory_evidence`, or equivalent
  benchmark-memory payloads;
- only the resident campaign runner or an explicitly named Phase 3 benchmark
  harness may emit `BenchmarkMemoryEvidencePacket`;
- any artifact that contains `BenchmarkMemoryEvidencePacket` must also record
  the fixture id, memory snapshot hash, recall config hash, and
  `benchmark_only=true`;
- production `PromptSectionRegistry` integration cannot reuse this packet
  format without a separate design and close gate.

If the resident campaign runner uses `prompt_section` language for Harbor
rows, that name refers only to this benchmark artifact format. It does not
mean the production `PromptSectionRegistry` path has shipped. Future
production prompt sections must re-specify section ids, hashes, cache policy,
budgets, leak gates, and provider transport separately.

Harbor-specific metrics:

- verifier success;
- protected/generated files not modified;
- first edit latency when available;
- read/search/tool counts;
- correct source/verifier convention evidence hit;
- stale memory rejected or downgraded;
- reviewer rescue required;
- memory items returned;
- memory items used by downstream evidence, measured by artifacts rather than
  model self-report.

### Phase 3 Acceptance Rules

Reporting the metrics is not enough. Phase 3 acceptance requires prespecified
expectations before the run starts.

Default no-regression floors:

- Harbor `memory_on` must not reduce verifier pass/fail outcome compared with
  the paired `memory_off` baseline for the same step and fixture version.
- Harbor `memory_on` must not reduce protected/generated-file safety compared
  with `memory_off`; a row that modifies protected generated output cannot
  count as a memory win.
- Harbor `memory_on` must not increase reviewer-rescue count compared with
  `memory_off`.
- MemoryArena-style `memory_on` must not reduce the primary task-success
  metric compared with `memory_off`, unless a documented waiver marks the row
  as diagnostic-only and excludes it from Phase 4 exposure evidence.

Recall evidence expectations:

- Each fixture row with an expected memory must declare expected evidence ids,
  source refs, or proof refs before the run.
- Harbor Step B memory-on must return the expected project convention or
  workflow/gotcha evidence in the accepted recall set. Default expectation is
  top 3 unless the implementation design predeclares a different `k`.
- MemoryArena-style task sets must meet a predeclared evidence-hit threshold.
  Default expectation is at least 0.80 Recall@5 across rows with expected
  memory and no required row missing its only proof-bearing memory.
- Rows with no applicable approved memory must show correct abstention or an
  empty/dropped result instead of irrelevant confident recall.

Stale and contradiction acceptance:

- A seeded stale entry in a stale row must not be returned as fresh. The
  stale-as-fresh count for seeded stale entries must be zero.
- Stale or contradictory entries may be returned only if labeled/downgraded
  with staleness or contradiction metadata, or counted under `dropped`.
- Harbor Step C must reward verification against the current fixture layout
  and reject blind use of obsolete paths or obsolete verifier locations.
- A stale row that passes only because the stale memory happened to be harmless
  does not count unless the artifact shows explicit downgrade, rejection, or
  current-evidence verification.

Latency and result-size budgets:

- Default direct recall budget: p95 <= 1 second on the local fixture store.
- Default chain expansion budget, when enabled: p95 <= 2 seconds on the local
  fixture store.
- Default benchmark evidence packet budget: <= 3 items and <= 1200 UTF-8
  characters after normalization.
- Default downstream overhead floor: memory-on must not add more than 10%
  median wall-time overhead against memory-off unless the predeclared primary
  success metric improves.
- A budget waiver must be written before accepting the row. It must name the
  exceeded budget, explain the environment or fixture reason, set a replacement
  budget, and mark whether the row can count for Phase 4. Missing measurement
  is not a waiver.

Prespecified downstream success rule:

- Before each Phase 3 run set, choose one primary downstream rule: verifier
  pass improvement, pass-rate preservation with at least 10% improvement on a
  named efficiency metric, one fewer repeated failed approach, stale-memory
  rejection, or another named artifact-measured rule.
- A resident-advantage claim requires that rule to pass and all no-regression
  floors to remain green.
- If memory-on is neutral but safe, the row may support subsystem readiness,
  but it must not be cited as resident advantage.

### Phase 3 Close Gate

Phase 3 closes only when:

- memory-off baseline exists for at least one MemoryArena-style task set;
- memory-on result exists for the same task set;
- stale/contradictory result exists or a documented reason explains why the
  task set does not support it;
- memory-off baseline exists for the Harbor resident-memory task;
- memory-on result exists for the same Harbor task;
- stale-memory Harbor row exists and rewards verification over blind reuse;
- recall evidence hit rate is reported;
- prespecified recall evidence-hit expectations pass or have an explicit
  diagnostic-only waiver;
- stale/contradiction rate is reported;
- seeded stale entries are never counted as fresh in accepted rows;
- latency and result-size overhead are reported;
- latency and result-size budgets pass or have an explicit waiver that says
  whether the row can count for Phase 4;
- downstream task success is reported;
- the prespecified downstream success rule passes for any row used to claim
  resident advantage;
- no-regression floors for verifier success, protected/generated-file safety,
  reviewer rescue count, and primary task success pass for rows used as Phase 4
  exposure evidence;
- any Harbor memory-on downstream row uses only the benchmark-only evidence
  channel, not `implement_v2`, provider-visible recall, or production prompt
  injection;
- no accepted row depends on production prompt injection, ordinary
  `implement_v2` prompt modification, or provider-visible recall;
- static or artifact gates prove ordinary `implement_v2` provider requests do
  not contain `BenchmarkMemoryEvidencePacket`, `benchmark_memory_evidence`, or
  equivalent benchmark-memory payloads;
- every `BenchmarkMemoryEvidencePacket` artifact is labeled
  `benchmark_only=true` and names its fixture id, memory snapshot hash, and
  recall config hash;
- no accepted row treats raw transcript as durable memory;
- any claimed resident advantage is tied to artifacts, not model self-report.

## Phase 4 - Add Thin MemoryToolProvider(recall)

Goal: expose read-only recall through `ToolRegistry` only after the core and
evaluation gates make the behavior inspectable.

This phase consumes the existing ToolProvider design. It should not redesign
the core and should not move memory policy into `ToolRegistry`.

### Adapter Contract

`MemoryToolProvider(recall)` is a thin adapter:

```text
provider-visible recall request
  -> validate provider schema
  -> adapt to MemorySystem.recall request
  -> call read-only MemorySystem.recall
  -> adapt core result to provider-visible envelope
  -> return evidence/context only
```

The provider-visible schema appears here first. It is not the core API. The
core API may expose richer debug metadata; the provider result must stay small
and must obey the forbidden-field rules from the ToolProvider design.

### ToolRegistry Connection

Phase 4 must preserve:

- `ToolRegistry` as the only source of final model-visible tool schema;
- explicit memory recall enablement;
- stable descriptor/schema/route hashes;
- read-only access class;
- normal unknown/disabled tool handling;
- no prompt section registration by `MemoryToolProvider`;
- no memory store/index imports inside `ToolRegistry`.

### Implement Lane Connection

The first implement-lane connection starts with read-only recall only:

- default off;
- explicit profile/config enablement;
- no write tool;
- no automatic prompt memory section;
- no planner or next-action fields;
- no raw transcript return;
- trace every call with schema hash, request hash, result hash, timing, and
  dropped reasons.

Prompt projection remains later work. If it is added, the path is:

```text
MemorySystem projection
  -> PromptSectionRegistry
  -> bounded PromptSection entries
  -> provider request prompt sections
```

It does not route through `MemoryToolProvider` or `ToolRegistry`.

### Phase 4 Close Gate

Phase 4 closes only when:

- Phase 1a, Phase 1b, and Phase 2 close gates have closed with no waiver;
- Phase 3 close gates have closed, or any Phase 3 waiver is explicitly marked
  diagnostic-only and cannot be used to claim resident advantage or justify
  broad production exposure;
- `MemoryToolProvider` owns the provider-visible recall descriptor, input
  schema, result schema, handler adapter, and schema hash;
- provider-visible `recall` is read-only and default off;
- `ToolRegistry` snapshots include recall only under explicit enablement;
- provider-visible recall result contains candidates, chains, and dropped
  metadata only;
- forbidden fields such as `next_action`, `required_next`, and planner
  instructions cannot appear;
- default `codex_hot_path` behavior remains unchanged when memory recall is
  disabled;
- no prompt memory injection is introduced.

## Debug And Scoring CLI Boundary

The debug/scoring boundary is a first-class part of MemorySystem core. It is
not a convenience wrapper around the future native tool.

Required capabilities:

- load a memory snapshot or fixture store;
- list entries by kind, scope, staleness, and validity;
- inspect an entry with source/proof refs;
- run recall for a query with machine-readable output;
- run chain expansion with visible truncation and dropped reasons;
- compare memory-off, memory-on, and stale modes;
- emit per-call trace artifacts for scoring;
- support fixture-level evidence hit calculation;
- support latency/result-size measurement.

This boundary is allowed to expose debug metadata that would be too large or
too internal for provider-visible recall. It must still avoid exposing raw
transcript as if it were durable memory.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Memory becomes ambient prompt policy before it is evaluated. | v0/v1 use direct recall and benchmark calls only. Phase 3 Harbor may use the benchmark-only evidence packet, but production prompt injection is a non-goal. Future production injection must use `PromptSectionRegistry`. |
| Raw transcript gets mistaken for durable memory. | Separate provenance refs from approved entries; recall reads committed entries only. |
| Automatic writes create false or dangerous memories. | Candidate/proposal/approval/commit path; no automatic append. |
| Recall turns into a planner. | Recall result schema forbids next-action and policy fields. |
| Graph recall floods context or amplifies stale edges. | Bounded traversal, typed edges, stale/contradiction filtering, dropped metadata. |
| Evaluation overfits to generic memory benchmarks. | Use MemoryArena for generic action-memory sanity and Harbor resident tasks for mew coding advantage. |
| Memory-on wins by leaking answers. | Harbor tasks must remain independently solvable; memory entries are reusable conventions/gotchas, not hidden answers. |
| Provider adapter hides core failures. | Core is evaluated through direct debug/scoring calls before provider-visible tool exposure. |
| Latency/token overhead erases benefits. | Phase 3 requires latency and result-size reporting before Phase 4. |

## Implementation Readiness Checklist

Before implementation begins, the next implementation prompt should be able to
answer yes to every item:

- Target implementation phase is named: Phase 1, 2, 3, or 4.
- The task does not edit roadmap files unless explicitly requested.
- The task does not wire memory into ordinary `implement_v2` prompts.
- The task does not implement production prompt injection.
- Durable entry schema includes kind, scope, source refs, proof refs,
  staleness, contradiction, and revision metadata.
- Write path separates candidate, proposal, approval, and commit.
- Recall reads only approved committed entries.
- Recall result is evidence/context only.
- Chain expansion is bounded and typed.
- Debug/scoring calls do not require `ToolRegistry` or `MemoryToolProvider`.
- MemoryArena and Harbor evaluation modes can distinguish memory off, memory
  on, and stale memory.
- Evaluation reports evidence hit rate, stale/contradiction rate, latency,
  result size, and downstream task success.
- `MemoryToolProvider(recall)` is not implemented until core and evaluation
  gates are closed or waived.

## Non-Goals

- No implementation code in this design step.
- No test changes in this design step.
- No roadmap or roadmap-status edits in this design step.
- No production prompt injection for v0/v1.
- No automatic append of transcript/tool output into durable memory.
- No model-visible write-memory tool.
- No recall output that contains next-action, planner, or policy directives.
- No raw transcript dump as recall output.
- No broad user-persona or cross-project identity memory in M6.25 core v0/v1.
- No `ToolRegistry` ownership of memory stores, indexes, projection policies,
  extraction, approval, or chain traversal.
- No claim of resident advantage without memory-off and memory-on artifacts.
