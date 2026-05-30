# Review 2026-05-20 - Memory Context Builder Literature

Status: paper-based research review. No code changes.

Scope: literature and system evidence for designing mew's memory subsystem and
RAG/context-construction path, especially `MemorySystem`,
`MemoryContextBuilder`, `MemoryToolProvider`, MemoryArena scoring, and
agent/lane integration.

Local context read: `docs/DESIGN_2026-05-20_M6_25_MEMORY_CORE_AND_EVALUATION.md`,
`docs/DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md`,
`docs/DESIGN_2026-05-20_M6_25_IMPLEMENT_V2_DURABLE_CODING_INTELLIGENCE.md`,
`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`,
`docs/REVIEW_2026-05-20_M6_25_MEMORY_SUBSYSTEM_LITERATURE.md`,
`docs/REVIEW_2026-05-20_MEMORY_ARENA_FEASIBILITY.md`, and current
`src/mew/memory_core.py` schema vocabulary.

## Executive Finding

The strongest evidence does not support a design where mew dumps prior
transcripts or vector-search chunks into the model prompt. It supports this
pipeline:

```text
raw provenance
  -> event-triggered candidate extraction
  -> typed, scoped, cited memory entry
  -> staleness / contradiction / approval gates
  -> seed retrieval
  -> task-aware rerank / read-side adaptation
  -> bounded graph or hierarchy expansion when needed
  -> compact evidence projection or read-only recall tool output
  -> traceable downstream action
```

For mew, the product-specific version is:

```text
small typed coding memories + proof refs + scope + stale/contradiction state
  -> direct MemorySystem recall first
  -> MemoryContextBuilder only builds bounded evidence context
  -> MemoryToolProvider stays a thin read-only adapter
  -> agent/lane decides when recall is useful
  -> Harbor decides coding-resident advantage; MemoryArena is auxiliary
```

## Interpreting Mew's 5+1 Dimensions

The repo does not currently use the exact phrase "5+1 memory dimensions" in
the active M6.25 docs. I interpret it as the older M6.9 five coding-memory
families, reconciled with the newer `MemorySystem` kinds, plus one
cross-cutting governance/evidence layer:

| Mew dimension | Current schema/kind relationship | Design meaning |
| --- | --- | --- |
| 1. Reviewer correction / steering | `reviewer_correction`, older `reviewer-steering` | durable corrections, reviewer rules, how/why guidance with approval |
| 2. Failure shield / negative evidence | `failure_shield` | approaches not to repeat; failed repairs, contradictions, obsolete tactics |
| 3. File/symbol structure | `file_symbol_edge`, older `file-pair/symbol-edge` | source/test/module/symbol relationships and structural locality |
| 4. Procedural repair / task template | `procedural_repair`, older `task-template` | reusable repair workflows, runbooks, skill-like procedures |
| 5. Episodic + semantic project memory | `episodic_task`, `project_convention`, `user_preference` | prior task episodes, stable repo conventions, explicitly scoped preferences |
| +1. Provenance/governance layer | `source_refs`, `proof_refs`, `scope`, `staleness`, `contradiction`, `confidence`, trace | not a memory kind; the audit, freshness, approval, and isolation substrate that makes the other five safe |

This review treats the "+1" as mandatory infrastructure, not as optional
observability. Without it, persistent memory becomes a long-lived prompt
injection and stale-context channel.

## Engineering Dimension Map

| Engineering dimension | Strong paper/system support | Mew design consequence |
| --- | --- | --- |
| 1. Compression / distillation before injection | RECOMP compresses retrieved docs and can emit empty augmentation when irrelevant; LLMLingua/LongLLMLingua and Selective Context show prompt/context compression tradeoffs; LightMem and Memp distill interaction history/trajectories before reuse. | `MemoryContextBuilder` must receive short approved summaries/procedures, not raw transcripts. Every projected item needs a budget, source refs, and a way to fetch provenance separately. |
| 2. Progressive / hierarchical expansion | RAPTOR retrieves from a summary tree; GraphRAG/LightRAG use graph/community or dual-level retrieval; IRCoT and FLARE show iterative retrieval during reasoning/generation; HippoRAG and A-MEM support graph-linked associative expansion. | `MemorySystem.recall()` should do seed retrieval first, then optional bounded `expand_chain()` with depth/fanout/char budgets and typed edges. No graph dump. |
| 3. Relevance modeling / reranking with task context | HyDE uses generated relevance pivots; RankRAG unifies ranking and generation; Self-RAG critiques whether retrieval is needed and whether passages are useful; CRAG evaluates retrieval quality before generation. | Prefer exact/path/symbol/tag retrieval first for coding, then rerank with current task, changed files, verifier failure, memory kind, recency, confidence, and scope. Record why an item survived. |
| 4. Decay, staleness, contradiction, negative evidence | MemoryBank models forgetting/reinforcement; LongMemEval/MemoryAgentBench test updates and selective forgetting; Astute RAG and ConflictRAG handle knowledge conflicts; Seven Failure Points highlights operational RAG failures; failure-memory work such as Reflexion/ExpeL/Voyager supports learning from bad outcomes. | Memory entries need invalidators: file hash, symbol move, verifier change, task-contract change, reviewer veto, user preference update. `failure_shield` should be first-class but never be allowed to block fresh evidence without proof. |
| 5. Information-space scoping / namespace isolation | CoALA separates memory types and actions; MemGPT/Letta separate context tiers; LangGraph/LangMem use namespaced stores; Mem0, Zep, and MIRIX separate users/sessions/agents and graph scopes. | Scope must be part of every request and entry: user/project/lane/task. Project memory must not leak through user memory into another repo. Cross-scope search must be explicit and logged. |
| 6. Retrieval timing / decision when to recall | ReAct and Toolformer establish tool-call timing as an agent decision; FLARE retrieves when low-confidence future text needs support; Self-RAG adaptively retrieves on demand; Adaptive-RAG chooses no/single/iterative retrieval by complexity; MemGPT lets the agent page memory tiers. | Start with a read-only `recall` tool and explicit lane-triggered recall points: task start, reentry, repeated failure, before broad search, before using a suspected convention, after contradictory evidence. Avoid always-on prompt memory in v0/v1. |
| 7. Retrieval auditing / confidence / rationale | RAGAS, ARES, RAGChecker, ALCE, Self-RAG, and RAGTruth all make evaluation/faithfulness/citations explicit. | Recall output must include `why_relevant`, score/confidence, source/proof refs, staleness/contradiction state, dropped counts/reasons, trace refs, request/result hashes. It must not include `next_action` or hidden rationale. |

## Evidence Inventory

### Mature or Foundational Evidence

| Source | Authors | Year | Link | Supports |
| --- | --- | ---: | --- | --- |
| Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | Patrick Lewis et al. | 2020 | https://arxiv.org/abs/2005.11401 | parametric + non-parametric memory, provenance/updating motivation |
| REALM: Retrieval-Augmented Language Model Pre-Training | Kelvin Guu et al. | 2020 | https://arxiv.org/abs/2002.08909 | learned retrieval as part of language modeling |
| ReAct: Synergizing Reasoning and Acting in Language Models | Shunyu Yao et al. | 2022/2023 | https://arxiv.org/abs/2210.03629 | agent decides when to act/search/retrieve |
| Toolformer: Language Models Can Teach Themselves to Use Tools | Timo Schick et al. | 2023 | https://arxiv.org/abs/2302.04761 | learned API/tool invocation timing |
| Reflexion: Language Agents with Verbal Reinforcement Learning | Noah Shinn et al. | 2023 | https://arxiv.org/abs/2303.11366 | episodic reflection, failure-derived memory |
| Generative Agents: Interactive Simulacra of Human Behavior | Joon Sung Park et al. | 2023 | https://arxiv.org/abs/2304.03442 | memory stream, reflection, recency/importance/relevance retrieval |
| Voyager: An Open-Ended Embodied Agent with Large Language Models | Guanzhi Wang et al. | 2023 | https://arxiv.org/abs/2305.16291 | verified procedural skill library |
| MemoryBank: Enhancing Large Language Models with Long-Term Memory | Wanjun Zhong et al. | 2023 | https://arxiv.org/abs/2305.10250 | forgetting/reinforcement over long-term user memory |
| ExpeL: LLM Agents Are Experiential Learners | Andrew Zhao et al. | 2023 | https://arxiv.org/abs/2308.10144 | experience pool and lesson extraction |
| Cognitive Architectures for Language Agents | Theodore R. Sumers et al. | 2023 | https://arxiv.org/abs/2309.02427 | working/episodic/semantic/procedural split; internal memory actions |
| MemGPT: Towards LLMs as Operating Systems | Charles Packer et al. | 2023 | https://arxiv.org/abs/2310.08560 | virtual context management, memory tiers, agent-managed paging |
| Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection | Akari Asai et al. | 2023 | https://arxiv.org/abs/2310.11511 | retrieval on demand, relevance/support critique, citation accuracy |
| RECOMP: Improving Retrieval-Augmented LMs with Compression and Selective Augmentation | Fangyuan Xu, Weijia Shi, Eunsol Choi | 2023 | https://arxiv.org/abs/2310.04408 | retrieved-context compression and selective non-injection |
| Lost in the Middle: How Language Models Use Long Contexts | Nelson F. Liu et al. | 2023 | https://arxiv.org/abs/2307.03172 | why bounded context construction beats indiscriminate stuffing |
| Active Retrieval Augmented Generation / FLARE | Zhengbao Jiang et al. | 2023 | https://arxiv.org/abs/2305.06983 | iterative retrieval triggered by low confidence |
| IRCoT: Interleaving Retrieval with Chain-of-Thought Reasoning | Harsh Trivedi et al. | 2023 | https://arxiv.org/abs/2212.10509 | multi-hop retrieval where later queries depend on prior derivations |
| RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval | Parth Sarthi et al. | 2024 | https://arxiv.org/abs/2401.18059 | hierarchical compression and retrieval at multiple abstraction levels |
| Corrective Retrieval Augmented Generation | Shi-Qi Yan et al. | 2024 | https://arxiv.org/abs/2401.15884 | retrieval evaluator, confidence-triggered correction/search |
| Seven Failure Points When Engineering a RAG System | Scott Barnett et al. | 2024 | https://arxiv.org/abs/2401.05856 | operational RAG failure taxonomy and validation during operation |
| Adaptive-RAG | Soyeong Jeong et al. | 2024 | https://arxiv.org/abs/2403.14403 | choose no/single/iterative retrieval by query complexity |
| GraphRAG: From Local to Global | Darren Edge et al. | 2024/2025 | https://arxiv.org/abs/2404.16130 | graph/community summaries for corpus-level questions |
| LightRAG: Simple and Fast RAG | Zirui Guo et al. | 2024/2025 | https://arxiv.org/abs/2410.05779 | graph-structured dual-level retrieval |
| Astute RAG | Fei Wang et al. | 2024/2025 | https://arxiv.org/abs/2410.07176 | source-aware conflict handling between retrieved and internal knowledge |
| RAGAS | Shahul Es et al. | 2023/2024 | https://arxiv.org/abs/2309.15217 | context precision/recall and faithfulness-style evaluation |
| ARES | Jon Saad-Falcon et al. | 2023/2024 | https://arxiv.org/abs/2311.09476 | automated context relevance, answer faithfulness, answer relevance |
| RAGChecker | Dongyu Ru et al. | 2024 | https://arxiv.org/abs/2408.08067 | fine-grained retrieval/generation diagnostics |
| ALCE: Enabling LMs to Generate Text with Citations | Tianyu Gao et al. | 2023 | https://arxiv.org/abs/2305.14627 | citation/evidence-aware answer generation |
| RAGTruth | Ziyang Niu et al. | 2024 | https://aclanthology.org/2024.acl-long.585/ | hallucination corpus for trustworthy RAG |

### Recent Agent-Memory Systems and Benchmarks

| Source | Authors | Year | Link | Supports |
| --- | --- | ---: | --- | --- |
| Zep: A Temporal Knowledge Graph Architecture for Agent Memory | Preston Rasmussen et al. | 2025 | https://arxiv.org/abs/2501.13956 | temporal graph memory and enterprise temporal reasoning |
| A-MEM: Agentic Memory for LLM Agents | Wujiang Xu et al. | 2025 | https://arxiv.org/abs/2502.12110 | dynamically linked/Zettelkasten-style agent memory |
| Mem0: Production-Ready Long-Term Memory | Prateek Chhikara et al. | 2025 | https://arxiv.org/abs/2504.19413 | extraction, consolidation, graph memory variant, latency/token savings |
| MIRIX: Multi-Agent Memory System | Yu Wang, Xi Chen | 2025 | https://arxiv.org/abs/2507.07957 | modular memory types and multi-agent memory management |
| Memp: Exploring Agent Procedural Memory | Runnan Fang et al. | 2025 | https://arxiv.org/abs/2508.06433 | trajectory-to-procedure distillation, update/deprecation |
| LightMem: Lightweight and Efficient Memory-Augmented Generation | Jizhan Fang et al. | 2025/2026 | https://arxiv.org/abs/2510.18866 | lightweight compression, topic memory, offline consolidation |
| ReMe: Remember Me, Refine Me | Zouying Cao et al. | 2025 | https://arxiv.org/abs/2512.10696 | procedural memory with distillation, context-adaptive reuse, pruning |
| MemoryAgentBench | Yuanzhe Hu et al. | 2025 | https://arxiv.org/abs/2507.05257 | retrieval, test-time learning, long-range understanding, selective forgetting |
| MemoryArena | Zexue He et al. | 2026 | https://arxiv.org/abs/2602.16313 | interdependent multi-session agentic tasks |
| AMA-Bench | Yujie Zhao et al. | 2026 | https://arxiv.org/abs/2602.22769 | agent-environment trajectories, causality graph, tool-augmented retrieval |
| LongMemEval-V2 | Di Wu et al. | 2026 | https://arxiv.org/abs/2605.12493 | web-agent experience: state, workflows, gotchas, premise awareness |
| ConflictRAG | Chenyu Wang et al. | 2026 | https://arxiv.org/abs/2605.17301 | conflict detection/classification/resolution before answer generation |
| Thought-Retriever | Tao Feng et al. | 2026 | https://arxiv.org/abs/2604.12231 | retrieving distilled intermediate thoughts rather than raw chunks |

### System Documentation, Useful But Not Paper Evidence

These are implementation references, not peer-reviewed evidence:

| Source | Link | Useful idea | Evidence caveat |
| --- | --- | --- | --- |
| LangGraph memory docs | https://docs.langchain.com/oss/javascript/langgraph/memory | short-term thread state vs long-term namespace store | official project docs, not independent evidence |
| LangMem namespace docs | https://langchain-ai.github.io/langmem/guides/dynamically_configure_namespaces/ | templated namespaces for user/agent isolation | product docs |
| Letta/MemGPT docs | https://docs.letta.com/ | core/archival/recall memory hierarchy | system docs tied to MemGPT lineage |
| Mem0 docs | https://docs.mem0.ai/ | user/session/agent memory, graph memory | product docs; paper provides stronger evidence |
| STATE-Bench blog | https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/ | production-style memory benchmark claims | official blog; useful to monitor, not enough for mew close gates |

## Mature vs Speculative Claims

Treat as mature enough for M6.25 design:

- RAG should provide provenance and updateable external knowledge, but raw
  retrieval is not enough.
- Long contexts do not remove the need for selection and ordering.
- Compression/distillation before injection reduces cost and noise but must
  keep source refs.
- Retrieval should be adaptive: no retrieval, single retrieval, iterative
  retrieval, or graph expansion depending on task need.
- RAG systems need operational evaluation, not only static accuracy.
- Agent memory needs typed storage, lifecycle management, and explicit
  update/forget/invalidate operations.
- Multi-session benchmarks should test downstream action, not only recall QA.

Treat as promising but not yet mature enough to drive first implementation:

- Self-evolving memory systems that autonomously reorganize durable memory.
- Thought-memory retrieval from prior reasoning traces. For mew this must be
  distilled fact/decision/invariant memory only; no hidden rationale recall.
- Universal memory OS claims that cover every memory form in one abstraction.
- Blog/product benchmark claims without stable harnesses or peer-reviewed
  methodology.
- Conflict-aware RAG papers published days/weeks ago. Use their schemas as
  inspiration, not as proof of reliability.

## Read First: 10 Sources

1. **CoALA** - gives the cleanest agent architecture taxonomy:
   https://arxiv.org/abs/2309.02427
2. **MemGPT** - the strongest context-tier / memory-paging architecture:
   https://arxiv.org/abs/2310.08560
3. **Self-RAG** - retrieval timing, relevance/support critique, citations:
   https://arxiv.org/abs/2310.11511
4. **RAPTOR** - hierarchical distillation and retrieval at abstraction levels:
   https://arxiv.org/abs/2401.18059
5. **CRAG** - lightweight retrieval quality evaluator and corrective path:
   https://arxiv.org/abs/2401.15884
6. **Astute RAG** - source-aware conflict handling under imperfect retrieval:
   https://arxiv.org/abs/2410.07176
7. **A-MEM** - agentic graph/link organization for evolving memories:
   https://arxiv.org/abs/2502.12110
8. **Mem0** - production-oriented extraction/consolidation/retrieval tradeoffs:
   https://arxiv.org/abs/2504.19413
9. **MemoryArena** - generic benchmark for memory improving later action:
   https://arxiv.org/abs/2602.16313
10. **LongMemEval-V2 or AMA-Bench** - experienced-colleague / agent-trajectory
    evaluation pressure: https://arxiv.org/abs/2605.12493 and
    https://arxiv.org/abs/2602.22769

For mew specifically, read `Reflexion`, `ExpeL`, `Voyager`, `Memp`, and `ReMe`
next because procedural/failure memory is more valuable for coding agents than
generic chat preference memory.

## Concrete Design Implications For Mew

### MemorySystem Core

Implement the durable lifecycle, not just search:

- Store only approved `MemoryEntry` objects, never raw transcript as memory.
- Preserve `source_refs` and `proof_refs` with content/excerpt hashes.
- Keep candidate/proposal/approval/commit separated.
- Support revision lineage: `supersedes`, `contradicts`, `derived_from`,
  tombstone/veto metadata.
- Make staleness invalidators structural for coding: file hash, symbol move,
  verifier command, task contract, user preference, reviewer veto, tool-surface
  or provider behavior changes.
- Provide read APIs: `recall`, `adapt_recall`, `expand_chain`,
  `inspect_entry`, and trace.
- Prefer deterministic exact/path/symbol/tag retrieval first; add vector and
  graph retrieval only behind observable score components.
- Keep `recall` evidence-only: no `next_action`, `tool_to_call`,
  `should_edit`, or planner policy.

### MemoryContextBuilder

This should be the bounded construction layer between raw recall and any model
context:

- Input: task context, lane id, scope, current files/symbols, verifier state,
  recent failure class, and `MemoryRecallResult`.
- Steps: filter by scope/kind, drop stale/contradicted entries unless asked for
  history, rerank with task context, optionally expand graph, compress to
  short evidence cards, then enforce item/char/token budgets.
- Output: a structured evidence packet or future prompt section with
  `memory_id`, `kind`, `summary`, `why_relevant`, `source/proof refs`,
  `confidence`, `staleness`, `contradiction`, and dropped reasons.
- Never project raw transcript, old tool output, hidden rationale, full
  reviewer diffs, proof JSON bodies, or future-step answers.
- Keep ordering stable and auditable. If compression is lossy, expose a ref
  back to the exact provenance.

### MemoryToolProvider

Keep this boring:

- Own only the provider-visible `recall` descriptor, input/output schema,
  schema hash, handler adapter, and read-only access declaration.
- Delegate to an injected `MemorySystem`.
- Return candidates/chains/dropped metadata only.
- Do not own storage, graph policy, prompt sections, write APIs, or memory
  injection.
- Require explicit enablement in the selected tool surface. Unknown/disabled
  recall calls should go through ordinary unknown-tool handling.

### Agent And Lane Integration

Retrieval timing should be explicit and measured:

- Agent may call recall at task start, after reentry, before broad search, when
  a task resembles a known shape, after repeated verifier failure, before
  relying on a remembered convention, and when fresh evidence contradicts
  memory.
- Lane/runtime should provide scope and memory-kind hints; the model supplies a
  query, not storage policy.
- Harbor campaign rows should record `memory_off`, `memory_on`, and `stale`
  modes with memory snapshot hashes and recall config hashes.
- Memory must remain weaker than fresh repo evidence, verifier output, task
  contract, system/developer policy, and explicit user instruction.

## MemoryArena: What It Can And Cannot Evaluate

MemoryArena can evaluate:

- whether prior session evidence is retrievable for a later dependent subtask;
- whether memory improves task success or process progress in generic
  multi-session agent loops;
- recall@k/MRR/evidence-hit style metrics on fixture-seeded memory;
- stale-memory rejection in synthetic variants;
- chain expansion and result-size/latency budgets in non-coding tasks.

MemoryArena cannot evaluate, by itself:

- mew's coding-resident advantage over cold Codex-like runs;
- source/test/verifier conventions in a real repo;
- patch correctness, protected/generated file safety, or diff quality;
- WorkFrame/reentry behavior and native tool-loop integration;
- reviewer-correction reuse, reviewer rescue reduction, or failure-shield
  blocking in coding tasks;
- `ToolRegistry` and `MemoryToolProvider` schema exposure safety;
- production prompt projection through `PromptSectionRegistry`;
- whether memory changes ordinary coding-agent behavior safely.

Use MemoryArena as an auxiliary `MemorySystem` sanity benchmark. Use Harbor
resident-memory fixtures as the M6.25 acceptance gate.

## Practical Close-Gate Recommendations

- V0: direct `MemorySystem` scoring and empty/thin read-only recall adapter
  only. No prompt memory injection.
- V1: approved seeded entries, exact/path/symbol/tag recall, stale filtering,
  trace artifacts, Harbor `memory_off/on/stale`.
- V1.5: bounded one-hop graph expansion with typed edges and dropped reasons.
- V2: event-triggered candidate extraction and kind-specific approval gates.
- Late V2: tiny `PromptSectionRegistry` projection only for high-confidence
  active conventions/preferences after recall usefulness is proven.

Minimum metrics:

- evidence hit rate, Recall@k/MRR, stale-as-fresh count, contradiction count;
- dropped count by reason, useful-recall ratio, latency p50/p95, result size;
- write precision/recall for candidate extraction;
- downstream verifier pass, pass^N, first useful action latency, first edit
  latency, repeated failed approach count, reviewer rescue count;
- memory-attributable win rate against paired cold runs.

## Caveats

- This is a literature review, not an implementation authorization.
- Web search and primary arXiv/ACL/project pages were used on 2026-05-20.
- Several 2026 papers are very recent preprints; use them as design signals,
  not as mature engineering proof.
- Product documentation and blog posts are separated above from paper evidence.
- The "5+1" mapping is an interpretation from local mew docs and current
  schema vocabulary because no active local document used that exact phrase.
