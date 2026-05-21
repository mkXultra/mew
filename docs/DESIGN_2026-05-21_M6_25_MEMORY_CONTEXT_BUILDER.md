# Design 2026-05-21 - M6.25 Memory Context Builder

Status: proposed design.

Scope: redesign the next M6.25 memory step around a real memory subsystem,
not around MemoryArena-specific scoring. This document converts the literature
review in `docs/REVIEW_2026-05-20_MEMORY_CONTEXT_BUILDER_LITERATURE.md` and
the product discussion into an implementation plan.

Non-goals:

- Do not add ambient prompt injection.
- Do not use MemoryArena as the primary close gate.
- Do not make `recall()` a planner or next-action generator.
- Do not store raw transcripts as durable memory entries.
- Do not treat token-overlap recall as the finished memory architecture.

## Problem

Current `MemorySystem.recall()` is useful as a substrate, but the search path is
simple:

```text
query
  -> tokenize
  -> scan MemoryEntry.search_text()
  -> token overlap score
  -> scope/kind/stale/citation filters
  -> top-k candidates
```

That is not enough to prove that mew has a useful resident memory system.

The missing product capability is not just better retrieval. It is a bounded,
auditable path from messy experience to safe model-visible memory context:

```text
raw session / proof / review / verifier evidence
  -> compressed durable memory
  -> scoped recall
  -> relevance and freshness analysis
  -> progressive expansion when needed
  -> compact context packet
  -> agent/lane uses or ignores it
  -> trace proves what happened
```

## Memory Engineering Dimensions

M6.25 memory work should be evaluated across these dimensions.

| # | Dimension | Meaning | Current state |
|---:|---|---|---|
| 1 | Information compression | Distill raw session/review/proof into short durable memory. | Mostly missing. |
| 2 | Progressive expansion | Start from summary, then expand to detail/provenance/raw evidence only when needed. | Schema has refs and graph edges, but builder behavior is missing. |
| 3 | Relevance | Decide which memory is useful for the current task/context. | Token overlap only. |
| 4 | Decay / contradiction | Detect stale, superseded, contradicted, or negative evidence. | Metadata and filters exist; invalidation policy is missing. |
| 5 | Information-space scoping | Prevent memory leaking across user/project/lane/task spaces. | Scope and kind filters exist; namespace policy is still thin. |
| 6 | Retrieval timing | Decide when the agent should recall. | Not integrated. |
| 7 | Retrieval audit | Record why a memory was retrieved, used, dropped, or expanded. | Basic traces exist; context-builder audit is missing. |

## Literature-Supported Direction

The review points to a practical direction:

- Compression before injection: RECOMP, LLMLingua/LongLLMLingua, LightMem,
  Memp, Mem0.
- Progressive expansion: RAPTOR, GraphRAG, LightRAG, HippoRAG, A-MEM.
- Adaptive retrieval timing: ReAct, Toolformer, Self-RAG, FLARE, Adaptive-RAG,
  MemGPT.
- Relevance and critique: Self-RAG, CRAG, RankRAG, HyDE.
- Conflict/staleness handling: Astute RAG, ConflictRAG, MemoryBank,
  LongMemEval-V2, MemoryAgentBench.
- Auditing/evaluation: RAGAS, ARES, RAGChecker, ALCE, RAGTruth.

The design implication is clear: raw recall candidates should not be dumped
into the prompt. A `MemoryContextBuilder` should analyze, compress, bound, and
audit the memory packet before any agent sees it.

## Proposed Architecture

```text
                 write side
                 ---------

raw artifacts
  provider transcript / tool result / verifier log / reviewer note
        |
        v
MemoryCandidateExtractor
  - meaning-boundary compression
  - memory kind classification
  - source/proof refs
  - confidence / applicability
        |
        v
proposal -> approval -> committed MemoryEntry


                 read side
                 --------

task context / lane context / current failure / scope
        |
        v
MemorySystem.recall()
  - cheap seed retrieval
  - scope/kind/stale/citation filters
        |
        v
MemoryContextBuilder
  - task-aware relevance
  - negative-space summary
  - stale/contradiction handling
  - optional bounded expand_chain()
  - compression and budget enforcement
  - audit artifact
        |
        v
MemoryContextPacket
  - compact cards
  - dropped reasons
  - coverage gaps
  - provenance refs
        |
        v
MemoryToolProvider / future PromptSectionRegistry
```

## Core Types

### MemoryContextRequest

Input to the builder.

```text
request_id
scope
lane_id
task_kind
task_text_hash
current_files
current_symbols
recent_failure_family
query
allowed_memory_kinds
max_items
max_chars
allow_chain_expansion
include_stale
```

Important: this is not a prompt. It is a construction request.

### MemoryContextPacket

Output from the builder.

```text
packet_id
packet_hash
scope
query_hash
cards[]
dropped{}
coverage_gaps[]
negative_space[]
conflicts[]
stale_items[]
budget_used
trace_ref
```

The model-visible projection, if any, is derived from this packet. The packet
itself is also stored as an artifact for replay/debugging.

### MemoryContextCard

One bounded, model-safe memory item.

```text
memory_id
memory_kind
summary
why_relevant
how_to_use
limits
confidence
staleness
contradiction
source_refs
proof_refs
expanded_from[]
score_breakdown
```

`how_to_use` is not `next_action`. It is a constrained applicability note, for
example "use when editing generated-file guards" or "avoid repeating this
failed toolchain path".

### Negative Space

A short statement of what the memory packet does not establish.

Examples:

- "No recalled memory proves the current verifier command."
- "No memory confirms this source path still exists."
- "Recalled repair history predates the native tool loop rebuild."

This is meant to reduce hallucinated confidence from partial memory.

## MemorySystem Core Responsibilities

Keep `MemorySystem` deterministic and inspectable.

It should own:

- entry schema;
- candidate/proposal/approval/commit lifecycle;
- tombstone/revision/supersession;
- scope/kind/stale/citation filtering;
- cheap seed recall;
- graph edge traversal through `expand_chain`;
- trace hashes and budget accounting.

It should not own:

- prompt projection;
- agent/lane policy;
- when to recall;
- next actions;
- hidden raw transcript injection;
- LLM-based interpretation.

Future search improvements can be added behind observable score components:

```text
score = exact/path/symbol score
      + lexical score
      + optional embedding score
      + optional reranker score
      + confidence/freshness modifiers
```

Every score component must be artifacted before it affects close gates.

## MemoryContextBuilder Responsibilities

The builder is the main new component.

It should:

- take recall candidates and task context;
- filter by scope, kind, freshness, contradiction, and budget;
- rerank with task context;
- optionally call `expand_chain()` with strict depth/fanout limits;
- compress each result into a bounded memory card;
- produce negative-space and coverage-gap notes;
- record dropped reasons and score breakdowns;
- return a `MemoryContextPacket`.

It should not:

- read arbitrary raw transcripts directly;
- invent memory not backed by `source_refs` and `proof_refs`;
- tell the agent what tool to call next;
- silently include stale memory as fresh;
- allow cross-project memory without explicit request/audit.

## MemoryToolProvider Responsibilities

The tool provider should stay thin.

It owns:

- provider-visible `recall` tool schema;
- input validation;
- read-only declaration;
- conversion from tool call to `MemoryContextRequest`;
- conversion from `MemoryContextPacket` to compact tool output.

It does not own:

- storage;
- candidate extraction;
- approval;
- prompt registry;
- memory writeback;
- lane policy.

This keeps memory tools injectable without making tool registry responsible for
memory architecture.

## Agent And Lane Integration

The agent/lane should decide when memory is worth reading.

Initial recall trigger points:

- task start when the task resembles a known project convention;
- after context reentry;
- after repeated verifier failure;
- before broad filesystem search;
- before relying on a remembered convention;
- when fresh evidence contradicts a remembered rule;
- before reviewer-rescue style repair.

Memory is weaker than:

- user instruction;
- system/developer policy;
- fresh repository evidence;
- current verifier output;
- current task contract.

M6.25 should not add always-on memory prompt injection. Start with a native
read-only recall tool plus explicit artifacts proving when it was called.

## Evaluation Plan

Primary evaluation should be a mew memory contract eval, not MemoryArena.

### Contract Fixtures

Create small fixture families:

1. `compression`
   - raw session is long;
   - expected durable memory is short;
   - raw transcript must not be injected.
2. `progressive_expansion`
   - top card is enough for simple task;
   - detailed proof is fetched only when requested.
3. `relevance`
   - multiple plausible memories exist;
   - only task-relevant one should appear in top-k.
4. `decay`
   - stale/superseded memory exists;
   - fresh memory should win or stale should be labeled/dropped.
5. `scope`
   - same query across two projects;
   - cross-scope leakage must be zero.
6. `negative_space`
   - partial memory exists;
   - packet must state what is not established.
7. `agent_timing`
   - read-only model loop has recall available;
   - artifact shows whether recall was used at the right time.

### Metrics

Minimum metrics:

- Hit@1/3/5 and MRR for expected memory cards;
- stale-as-fresh count;
- contradiction-as-fresh count;
- cross-scope leak count;
- negative-space presence rate;
- p50/p95 recall and builder latency;
- returned char budget p95;
- dropped counts by reason;
- useful-recall ratio;
- downstream success and no-regression only after lane integration.

### MemoryArena Role

MemoryArena remains auxiliary.

It can test:

- generic multi-session recall;
- stale and irrelevant memory handling;
- memory-off vs memory-on generic behavior;
- tool-call timing in a model-in-loop evaluator later.

It cannot close M6.25 by itself because it does not prove:

- coding-resident advantage;
- source/test/verifier convention reuse;
- reviewer-correction reuse;
- protected/generated file safety;
- implement lane integration quality.

## Phase Plan

### Phase A - Freeze The Contract

Deliverables:

- `MemoryContextRequest`
- `MemoryContextCard`
- `MemoryContextPacket`
- stable JSON serialization
- trace/ref/hash rules
- fixture schema for contract eval

Close gate:

- unit tests prove packet serialization is stable;
- empty/no-memory packet records negative space and dropped reasons;
- no prompt injection or implement-lane dependency.

### Phase B - Builder V0

Deliverables:

- builder consumes `MemoryRecallResult`;
- filters stale/contradiction/scope;
- emits bounded cards;
- emits negative-space and coverage-gap notes;
- records score breakdown and dropped reasons.

Close gate:

- contract fixtures cover relevance, decay, scope, and budget;
- all fixture metrics are artifacted;
- no model calls required.

### Phase C - Progressive Expansion V0

Deliverables:

- bounded one-hop `expand_chain()` integration;
- graph depth/fanout/char budgets;
- expanded cards show source entry ids.

Close gate:

- expansion improves fixture hit metrics where expected;
- expansion does not increase stale-as-fresh or scope leakage;
- budget drops are visible.

### Phase D - MemoryToolProvider V0

Deliverables:

- read-only native `recall` tool;
- tool output is a compact `MemoryContextPacket` projection;
- no writeback;
- no ambient prompt injection.

Close gate:

- native tool call produces the same packet as direct builder call;
- provider-visible output is bounded;
- artifacts include request hash, packet hash, and dropped reasons.

### Phase E - Model-In-Loop Timing Spike

Deliverables:

- small eval where model has recall tool available;
- compare memory_off / memory_on / stale;
- measure if model calls recall at useful times.

Close gate:

- not a production gate;
- result reports recall timing, task outcome, and memory usefulness;
- failures are classified as memory quality, tool usability, or model behavior.

### Phase F - Implement Lane Integration Decision

Deliverables:

- decide whether to expose recall to implement_v2;
- if yes, expose through tool registry/profile only;
- no prompt injection unless a separate prompt-section design is approved.

Close gate:

- Harbor resident-memory task or equivalent coding fixture shows no regression;
- memory-on has a predeclared advantage metric;
- stale-memory fixture rejects blind reuse.

## Drift Guards

- If a change adds memory to the prompt without a `MemoryContextPacket`, stop.
- If a change uses raw transcript as durable memory summary, stop.
- If a change lets stale memory appear as fresh, stop.
- If a change makes `recall()` emit `next_action`, stop.
- If a change optimizes only MemoryArena score without improving contract
  fixtures, mark it auxiliary and do not count it toward M6.25 close.
- If a change adds vector search before score components and artifacts are
  defined, defer it.

## Immediate Next Task

Implementation starts with a narrower short-term memory v0 before the full
context builder. This intentionally avoids medium-term indexes, long-term
durable memory promotion, graph retrieval, and production prompt injection.

Short-term memory v0:

- compress recent transcript/tool/reviewer evidence with an LLM into a small
  schema;
- keep the result session-local;
- recall only compact cards;
- expire cards by turn count or task end;
- use it to learn the schema through Harbor/MemoryArena-style fixtures before
  designing medium/long-term memory.

The v0 schema is allowed to evolve while MemoryArena and Harbor experiments
teach us which fields matter. It should remain small:

```text
kind: fact | decision | blocker | constraint | next_step | warning
summary
why_it_matters
source_refs[]
expires: turns:N | task_end | manual
confidence
```

Implement Phase A-short-term before adding any model-in-loop MemoryArena agent
or implement-lane memory injection.

One-line chain:

```text
M6.25 -> short-term memory correctness -> LLM compression schema + session-local recall fixtures
```
