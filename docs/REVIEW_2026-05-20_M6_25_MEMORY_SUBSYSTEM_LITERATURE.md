# Review 2026-05-20 - M6.25 Memory Subsystem Literature

Status: research report.

Scope: 2025-2026 LLM agent memory / long-term memory subsystem trends for
M6.25 design. This report is design input only. It does not authorize
implementation changes.

Local context read:

- `ROADMAP.md`, especially M6.9 durable coding intelligence and M6.25
  Codex-plus resident advantage.
- `docs/DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md`.
- `docs/REVIEW_2026-05-10_LITERATURE_TOOL_RESULT_TO_NEXT_ACTION.md`.

Web/paper search was used on 2026-05-20. Primary sources are listed in the
source inventory.

## Executive Finding

2026 時点の主流は「長い context に全部入れる」でも「vector DB を一個足す」
でもない。実用的な memory subsystem は、ほぼ次の形に収束している。

```text
raw provenance
  -> memory candidate extraction
  -> verification / contradiction / scope checks
  -> approval or guarded write
  -> typed durable memory + indexes
  -> native recall or bounded projection
  -> rerank / chain expansion / freshness checks
  -> task action with cited memory refs
```

mew に入れるべき最初の判断は明確である。

- Raw transcript は provenance であって memory ではない。
- `MemorySystem.recall()` は native tool として始める。prompt injection
  形式の常時注入は v0/v1 では避ける。
- Durable memory は typed entry + provenance refs + scope + validity state を
  持つ。
- Graph memory は「主ストア」ではなく、retrieval seed を広げる bounded
  traversal index として使う。
- Write path は automatic append ではなく candidate queue + approval/write
  gate から始める。
- Scoring は LoCoMo/LongMemEval 系だけでは足りない。MemoryArena /
  LongMemEval-V2 / AMA-Bench / STATE-Bench 系の「記憶が後続行動を改善したか」
  を見る方向が mew に近い。ただし mew の主評価は Harbor-style coding
  fixtures で持つべき。

The practical design target is:

```text
small, typed, approved, cited, scoped, stale-aware memory
```

not:

```text
large, self-written, prompt-injected, universal memory
```

## Trend: Mainstream Architecture Patterns In 2026

### 1. Memory Is A Lifecycle, Not A Store

Recent surveys explicitly describe agent memory as a write/manage/read loop,
not as a passive database. Du's 2026 survey frames memory as
`write--manage--read` coupled to perception/action, and separates mechanisms
such as context-resident compression, retrieval stores, reflection,
hierarchical virtual context, and policy-learned management.

Sources:

- Pengfei Du, "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and
  Emerging Frontiers", arXiv:2603.07670, https://arxiv.org/abs/2603.07670
- Jinghao Luo et al., "From Storage to Experience: A Survey on the Evolution of
  LLM Agent Memory Mechanisms", arXiv:2605.06716,
  https://arxiv.org/abs/2605.06716
- Zeyu Zhang et al., "A Survey on the Memory Mechanism of Large Language Model
  based Agents", arXiv:2404.13501, https://arxiv.org/abs/2404.13501

Design implication for mew:

- `MemorySystem` must own lifecycle policy, not only storage adapters.
- `MemoryRegistry` should register memory kinds, backends, graph indexes, and
  projection policies.
- `ToolRegistry` should only expose callable tool schema. It should not become
  the memory policy owner.

This matches `DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md`.

### 2. Cognitive Taxonomies Are Useful, But Only After Product Scoping

The working / episodic / semantic / procedural taxonomy is now common because
it maps well to failure modes:

- working memory: current task state, plan, tool observations, pending action.
- episodic memory: what happened in a prior session or task episode.
- semantic memory: stable facts, preferences, project conventions, APIs.
- procedural memory: how to perform recurring workflows or repairs.

CoALA and later memory papers make this classification legible. MIRIX expands
it into Core, Episodic, Semantic, Procedural, Resource Memory, and Knowledge
Vault. Memp, ReMe, and Skill-Pro push specifically on procedural memory.

Sources:

- "Cognitive Architectures for Language Agents", arXiv:2309.02427,
  https://arxiv.org/abs/2309.02427
- Yu Wang and Xi Chen, "MIRIX: Multi-Agent Memory System for LLM-Based Agents",
  arXiv:2507.07957, https://arxiv.org/abs/2507.07957
- Runnan Fang et al., "Memp: Exploring Agent Procedural Memory",
  arXiv:2508.06433, https://arxiv.org/abs/2508.06433
- Zouying Cao et al., "Remember Me, Refine Me: A Dynamic Procedural Memory
  Framework for Experience-Driven Agent Evolution", arXiv:2512.10696,
  https://arxiv.org/abs/2512.10696
- Qirui Mi et al., "Skill-Pro: Learning Reusable Skills from Experience via
  Non-Parametric PPO for LLM Agents", arXiv:2602.01869,
  https://arxiv.org/abs/2602.01869

Design implication for mew:

- Do not expose this taxonomy directly as user-facing complexity.
- Internally, use it to choose storage/gate/recall behavior.
- For M6.25, the most valuable split is not philosophical; it is:
  `working/reentry`, `episodic task episode`, `semantic project fact`,
  `procedural repair/runbook`, `preference/user memory`, and `failure-shield`.

### 3. Graph And Chain Recall Are Becoming Mainstream, But As A Second Step

A-MEM, Mem0 graph memory, MIRIX, Thought-Retriever, and EvolveMem all point in
the same direction: memory quality improves when retrieval can follow
relationships, not just nearest-neighbor chunks.

Important distinction: the successful pattern is not "dump a graph into the
prompt". It is:

```text
seed retrieval -> bounded graph/link expansion -> rerank -> compact projection
```

Sources:

- Wujiang Xu et al., "A-Mem: Agentic Memory for LLM Agents",
  arXiv:2502.12110, https://arxiv.org/abs/2502.12110
- Prateek Chhikara et al., "Mem0: Building Production-Ready AI Agents with
  Scalable Long-Term Memory", arXiv:2504.19413,
  https://arxiv.org/abs/2504.19413
- Tao Feng et al., "Thought-Retriever: Don't Just Retrieve Raw Data, Retrieve
  Thoughts for Memory-Augmented Agentic Systems", arXiv:2604.12231,
  https://arxiv.org/abs/2604.12231
- Jiaqi Liu et al., "EvolveMem: Self-Evolving Memory Architecture via
  AutoResearch for LLM Agents", arXiv:2605.13941,
  https://arxiv.org/abs/2605.13941

Design implication for mew:

- v1 can use simple exact/tag/path retrieval. v2 should add graph expansion.
- Graph edges should be typed and auditable:
  `derived_from`, `supersedes`, `contradicts`, `same_task_shape`,
  `failure_cluster`, `file_symbol`, `reviewer_correction`, `preference_scope`.
- Traversal must have depth/fanout/token budgets and return dropped metadata.
- Chain recall must never produce next-action policy. It returns evidence.

### 4. Hierarchical Online/Offline Consolidation Is A Strong Pattern

MemGPT introduced virtual context management with memory tiers. LightMem brings
that idea closer to a production shape: lightweight online filtering plus
offline "sleep-time" consolidation. MemoryBank uses reinforcement/forgetting
ideas. BEAM's LIGHT baseline also separates episodic, working, and scratchpad
memory.

Sources:

- Charles Packer et al., "MemGPT: Towards LLMs as Operating Systems",
  arXiv:2310.08560, https://arxiv.org/abs/2310.08560
- Jizhan Fang et al., "LightMem: Lightweight and Efficient
  Memory-Augmented Generation", arXiv:2510.18866,
  https://arxiv.org/abs/2510.18866
- Wanjun Zhong et al., "MemoryBank: Enhancing Large Language Models with
  Long-Term Memory", arXiv:2305.10250, https://arxiv.org/abs/2305.10250
- Mohammad Tavakoli et al., "Beyond a Million Tokens: Benchmarking and
  Enhancing Long-Term Memory in LLMs", arXiv:2510.27246,
  https://arxiv.org/abs/2510.27246

Design implication for mew:

- Online path should stay cheap and deterministic.
- Expensive extraction, consolidation, deduplication, and graph evolution
  should happen at session close, verifier boundary, or scheduled rehearsal.
- M6.25 should avoid every-turn LLM memory writes.

### 5. Procedural Memory Is More Relevant To Coding Agents Than Persona Memory

Reflexion, ExpeL, Voyager, Memp, ReMe, and Skill-Pro all support the same
coding-agent intuition: durable value comes from not repeating bad repairs and
from reusing verified workflows.

Sources:

- Noah Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement
  Learning", arXiv:2303.11366, https://arxiv.org/abs/2303.11366
- Andrew Zhao et al., "ExpeL: LLM Agents Are Experiential Learners",
  arXiv:2308.10144, https://arxiv.org/abs/2308.10144
- Guanzhi Wang et al., "Voyager: An Open-Ended Embodied Agent with Large
  Language Models", arXiv:2305.16291, https://arxiv.org/abs/2305.16291
- Runnan Fang et al., "Memp: Exploring Agent Procedural Memory",
  arXiv:2508.06433, https://arxiv.org/abs/2508.06433
- Zouying Cao et al., "Remember Me, Refine Me", arXiv:2512.10696,
  https://arxiv.org/abs/2512.10696
- Qirui Mi et al., "Skill-Pro", arXiv:2602.01869,
  https://arxiv.org/abs/2602.01869

Design implication for mew:

- Do not prioritize a broad "remember user chats" subsystem for M6.25.
- Prioritize coding-domain memories:
  `failure-shield`, `verified repair procedure`, `reviewer correction`,
  `file/symbol edge`, `project convention`, `task-template`.
- Procedural memories need the strongest write gate because they can cause
  repeated side effects if wrong.

## Practical Memory Classification For Mew

The useful mew taxonomy is implementation-oriented:

| Kind | Purpose | Initial store | Write gate | Recall path |
| --- | --- | --- | --- | --- |
| Raw provenance | Replay, audit, extraction source. | Append-only transcript / tool / verifier logs. | None as memory; provenance capture only. | Not recallable as memory. |
| Working/reentry | Current task state and continuation. | WorkFrame / lane state / active todo. | Reducer-owned state transition. | Prompt section, not durable recall. |
| Episodic task memory | What happened in a prior task/session. | Short episode cards with proof refs. | Outcome + verifier/reviewer evidence. | `recall` by task shape, files, failure class. |
| Semantic project memory | Stable project facts and conventions. | Typed facts with source refs and scope. | Contradiction + freshness + approval. | `recall` by path/symbol/convention/query. |
| Procedural memory | Reusable repair/runbook/skill. | Versioned procedures with trigger/action/proof. | Strong approval; preferably verified successful use. | `recall` by trigger and current evidence. |
| Failure-shield memory | Approaches not to repeat. | Failed attempt summaries with evidence. | Failure classification + reviewer approval. | Inject as `do_not_repeat` evidence only. |
| Preference/user memory | User-level preferences. | Separate user scope. | Explicit user approval or manual edit. | Narrow scope projection; never project facts across projects. |
| Graph/symbol memory | Relation index over memories and code. | Typed edges, symbol/file keys. | Derived from approved entries or static analysis. | Bounded expansion after seed retrieval. |

This classification is more practical than exposing generic
working/episodic/semantic/procedural buckets because each row has different
write gates, staleness semantics, and recall budgets.

## Write Path Design

### Recommended Write Pipeline

```text
raw provider request/response
raw tool result
verifier/test/reviewer outcome
  -> provenance artifact with hashes
  -> candidate extractor
  -> memory candidate queue
  -> gate: scope, source, contradiction, freshness, utility, privacy
  -> approval: reviewer/user/policy depending on kind
  -> durable typed memory entry
  -> indexes and graph edges
```

Raw transcript preservation is necessary, but it should not be treated as
durable memory. It is too noisy, too large, and can contain untrusted
instructions. Generative Agents used a full experience record plus reflection,
but later work shifts toward extracted notes, consolidated facts, and
experience abstractions.

Source:

- Joon Sung Park et al., "Generative Agents: Interactive Simulacra of Human
  Behavior", arXiv:2304.03442, https://arxiv.org/abs/2304.03442
- Wujiang Xu et al., "A-Mem", arXiv:2502.12110,
  https://arxiv.org/abs/2502.12110
- Jizhan Fang et al., "LightMem", arXiv:2510.18866,
  https://arxiv.org/abs/2510.18866

### Candidate Extraction

Candidate extraction should be event-triggered, not every turn:

- session close / compact boundary
- verifier pass or fail
- reviewer correction
- user correction
- repeated same-shape failure
- explicit "remember this" user action
- static project scan producing file/symbol edges

Candidate fields should include:

- `candidate_id`
- `memory_kind`
- `scope`: user / project / task / lane
- `source_refs`: transcript id, tool result id, verifier id, commit/hash
- `claim` or `procedure`
- `trigger_conditions`
- `validity`: provisional / approved / stale / superseded / rejected
- `confidence`
- `utility_score`
- `privacy_class`
- `created_at`, `last_verified_at`, `valid_from`, `valid_until`
- `supersedes`, `contradicts`, `derived_from`

### Approval / Write Gates

The write gate should be stricter by kind:

- User preference: explicit user approval or manual edit.
- Project convention: source evidence plus no contradiction; reviewer approval
  for broad conventions.
- Episodic task: verifier/reviewer outcome evidence.
- Failure-shield: failed outcome plus cause classification; reviewer approval
  before it can block future action.
- Procedural memory: successful verifier proof and explicit approval; for v2,
  prefer two successful uses or one reviewer-approved procedure.
- Graph edge: only from approved entries or deterministic/static analysis.

Do not overwrite memory in place. Use revision lineage:

```text
old entry -> superseded_by -> new entry
old entry -> contradicted_by -> evidence entry
entry -> stale_due_to -> file hash / commit / verifier change
```

### Revise Gates

`MemorySystem.revise()` should not be a model-visible "edit memory" shortcut.
It should consume approved candidate updates and invalidation events. A revise
operation should be one of a small set:

- add approved entry
- supersede entry
- mark stale
- mark contradicted
- merge duplicate entries
- promote or demote scope
- add graph edge derived from approved evidence
- reject candidate with reason

Required revise gate fields:

- source candidate or invalidation event
- old memory id if modifying existing memory
- reviewer/user/policy approval ref
- contradiction scan result
- freshness scan result
- scope decision
- before/after diff
- rollback/tombstone metadata

This keeps revision auditable and prevents old model prose from silently
rewriting durable memory.

### Staleness Handling

For coding memory, staleness is not only time-based. It is caused by:

- file changed since memory proof
- symbol moved/renamed
- verifier command changed
- task contract changed
- user preference changed
- reviewer later rejected the pattern
- model/provider/tool surface changed

Mew should store `proof_context` and `invalidators`, not just `timestamp`.

## Recall Path Design

### Native Tool First

`recall` should be a native read-only tool before memory is injected into every
prompt. The native tool path has three advantages:

- It gives an auditable trace: query, scope, candidates, dropped candidates,
  chain nodes, rerank reason.
- It avoids prompt bloat and "lost in the middle" failures.
- It treats memory as evidence requested for a task, not as ambient policy.

Prompt projection can come later for a tiny set of high-confidence,
high-frequency memories, but it should route through `PromptSectionRegistry`,
not `ToolRegistry`.

### Retrieval Stages

Recommended recall path:

```text
request validation
  -> scope filter
  -> kind filter
  -> exact/path/symbol/tag search
  -> optional vector retrieval
  -> optional graph expansion
  -> contradiction/staleness filter
  -> rerank
  -> bounded projection
  -> result with evidence refs and dropped metadata
```

Recall result should include:

- `memory_id`
- `kind`
- `scope`
- `summary`
- `why_relevant`
- `source_refs`
- `proof_refs`
- `validity`
- `confidence`
- `staleness`
- `related_ids`
- `dropped_count_by_reason`

It should not include:

- model instructions
- next-action commands
- hidden chain-of-thought
- raw transcript dumps
- unbounded graph neighborhoods

### Chain / Graph Recall

Graph traversal should be edge-typed and bounded:

- seed by exact/path/symbol/failure-class retrieval first
- expand only along allowed edge types for the memory kind
- cap depth and fanout
- rerank after expansion
- include why each edge was followed
- drop stale/superseded nodes unless the query asks for history

For mew, useful chain examples:

- current failing test -> previous failure cluster -> approved repair memory
- current file path -> symbol edge -> reviewer correction -> project convention
- current task shape -> old failed attempt -> failure-shield -> verified
  alternative
- current user preference query -> user-scope preference -> project override

### Prompt Injection Risk

Memory content must be treated as untrusted data. The risk is not only classic
web prompt injection. Raw transcripts, old tool outputs, and old model prose can
contain commands that were never meant to become durable policy.

Rules for mew:

- Memory entries are evidence, not instructions.
- A memory entry must not override system/developer policy, tool access, task
  contract, verifier output, or fresh repository evidence.
- Raw transcript content is never directly injected as a prompt section.
- Memory projection must label content as memory evidence and preserve source
  refs.
- User-scope preferences must not import project facts across projects.
- Project memory must not leak into another project unless explicitly promoted.
- Recall output should quote or summarize bounded content and keep original
  refs fetchable for audit.

This directly supports the existing M6.25 choice: read-only `recall` provider
first, prompt injection later and separately.

## Scoring And Benchmarking

### Benchmark Landscape

Older memory benchmarks mostly test whether a system can recall facts from long
conversations. Newer benchmarks test whether memory improves future action,
workflow knowledge, state tracking, or experience reuse.

| Benchmark | Source | What it tests | Mew relevance |
| --- | --- | --- | --- |
| LoCoMo | arXiv:2402.17753 | Very long multi-session conversation QA, summarization, multimodal dialogue. | Useful baseline only; too conversation-centric. |
| LongMemEval | arXiv:2410.10813 | Information extraction, multi-session reasoning, temporal reasoning, updates, abstention. | Good for retrieval/indexing sanity. |
| MemBench | ACL Findings 2025 | Factual and reflective memory, participation vs observation, efficiency/capacity. | Good for factual/reflective scoring, not coding action. |
| MemoryAgentBench | arXiv:2507.05257 | Accurate retrieval, test-time learning, long-range understanding, selective forgetting. | Good generic memory lifecycle benchmark. |
| BEAM | arXiv:2510.27246 | 100K-10M token long-term conversation memory. | Stress test for scale; not primary for mew. |
| StructMemEval | arXiv:2602.11243 | Whether memory systems organize state into useful structures. | Relevant to graph/structured memory decisions. |
| MemoryArena | arXiv:2602.16313 | Interdependent multi-session Memory-Agent-Environment loops. | Strongest generic fit for mew because memory must guide later action. |
| AMA-Bench | arXiv:2602.22769 | Agent logs, causal state transitions, long-horizon agentic applications. | Relevant to tool/action provenance and causal memory. |
| LongMemEval-V2 | arXiv:2605.12493 | Environment-specific experience: state, workflows, gotchas, premise awareness. | Highly relevant for "experienced colleague" behavior. |
| STATE-Bench | Microsoft Open Source Blog, 2026-05-19 | Whether memory improves realistic enterprise task success and consistency. | Worth monitoring; not yet a peer-reviewed anchor. |

Sources:

- Adyasha Maharana et al., "Evaluating Very Long-Term Conversational Memory of
  LLM Agents", arXiv:2402.17753, https://arxiv.org/abs/2402.17753
- Di Wu et al., "LongMemEval: Benchmarking Chat Assistants on Long-Term
  Interactive Memory", arXiv:2410.10813, https://arxiv.org/abs/2410.10813
- Haoran Tan et al., "MemBench: Towards More Comprehensive Evaluation on the
  Memory of LLM-based Agents", Findings of ACL 2025, DOI:10.18653/v1/2025.findings-acl.989,
  https://aclanthology.org/2025.findings-acl.989/
- Yuanzhe Hu et al., "Evaluating Memory in LLM Agents via Incremental
  Multi-Turn Interactions", arXiv:2507.05257,
  https://arxiv.org/abs/2507.05257
- Mohammad Tavakoli et al., "Beyond a Million Tokens", arXiv:2510.27246,
  https://arxiv.org/abs/2510.27246
- Alina Shutova et al., "Evaluating Memory Structure in LLM Agents",
  arXiv:2602.11243, https://arxiv.org/abs/2602.11243
- Zexue He et al., "MemoryArena: Benchmarking Agent Memory in Interdependent
  Multi-Session Agentic Tasks", arXiv:2602.16313,
  https://arxiv.org/abs/2602.16313
- "AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications",
  arXiv:2602.22769, https://arxiv.org/abs/2602.22769
- Di Wu et al., "LongMemEval-V2: Evaluating Long-Term Agent Memory Toward
  Experienced Colleagues", arXiv:2605.12493,
  https://arxiv.org/abs/2605.12493
- Lewis Liu and Nishant Yadav, "Introducing STATE-Bench: A benchmark for AI
  agent memory", Microsoft Open Source Blog, 2026-05-19,
  https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/

### What To Score In Mew

Mew needs two scoring layers.

Generic memory quality:

- retrieval Recall@k and MRR against known evidence
- evidence hit rate: did recall return the proof-bearing memory?
- stale recall rate
- contradiction rate
- abstention accuracy
- token/latency/API-call overhead
- write precision: accepted durable writes / proposed candidates
- write recall: important events missed by extractor
- invalidation latency after file or preference changes

Mew-specific downstream quality:

- repeated same-shape task improvement over first run
- verifier pass rate with memory on vs memory off
- first useful action latency
- time to first edit
- number of repeated failed approaches blocked by failure-shield memory
- reviewer rescue edits per task
- pass@1 and pass^N consistency across reruns
- memory-attributable win rate against fresh Codex/Codex-like briefing
- no-regression on novel-task canaries
- prompt size and memory projection size
- recall tool call count and useful-recall ratio

### MemoryArena vs Harbor Fixtures

MemoryArena is useful because it evaluates interdependent multi-session tasks
where memory must guide later action. It is closer to mew than LoCoMo because
it tests `memory -> decision -> environment result`, not only `memory -> QA`.

But MemoryArena should not replace Harbor fixtures.

Harbor-style fixtures should remain the primary M6.25 proof because mew's
product claim is coding-resident advantage:

- repeated coding task shapes
- repository-specific conventions
- verifier/test outcomes
- patch attempts
- reviewer corrections
- tool-loop and reentry behavior
- failure clusters and repair history

Recommended role split:

- LongMemEval / MemBench / MemoryAgentBench: sanity-check generic memory
  retrieval and lifecycle behavior.
- MemoryArena / LongMemEval-V2 / AMA-Bench / STATE-Bench: compare whether
  memory improves future action in non-coding environments.
- Harbor fixtures: accept/reject M6.25 because they directly test mew's coding
  advantage.

## Source Inventory

Foundational and taxonomy sources:

- Joon Sung Park et al., "Generative Agents: Interactive Simulacra of Human
  Behavior", arXiv:2304.03442, https://arxiv.org/abs/2304.03442
- Noah Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement
  Learning", arXiv:2303.11366, https://arxiv.org/abs/2303.11366
- Wanjun Zhong et al., "MemoryBank: Enhancing Large Language Models with
  Long-Term Memory", arXiv:2305.10250, https://arxiv.org/abs/2305.10250
- Guanzhi Wang et al., "Voyager: An Open-Ended Embodied Agent with Large
  Language Models", arXiv:2305.16291, https://arxiv.org/abs/2305.16291
- Andrew Zhao et al., "ExpeL: LLM Agents Are Experiential Learners",
  arXiv:2308.10144, https://arxiv.org/abs/2308.10144
- "Cognitive Architectures for Language Agents", arXiv:2309.02427,
  https://arxiv.org/abs/2309.02427
- Charles Packer et al., "MemGPT: Towards LLMs as Operating Systems",
  arXiv:2310.08560, https://arxiv.org/abs/2310.08560
- Zeyu Zhang et al., "A Survey on the Memory Mechanism of Large Language Model
  based Agents", arXiv:2404.13501, https://arxiv.org/abs/2404.13501
- Mathis Pink et al., "Position: Episodic Memory is the Missing Piece for
  Long-Term LLM Agents", arXiv:2502.06975,
  https://arxiv.org/abs/2502.06975
- Pengfei Du, "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and
  Emerging Frontiers", arXiv:2603.07670, https://arxiv.org/abs/2603.07670
- Jinghao Luo et al., "From Storage to Experience", arXiv:2605.06716,
  https://arxiv.org/abs/2605.06716

2025-2026 memory systems:

- Wujiang Xu et al., "A-Mem: Agentic Memory for LLM Agents",
  arXiv:2502.12110, https://arxiv.org/abs/2502.12110
- Rana Salama et al., "MemInsight: Autonomous Memory Augmentation for LLM
  Agents", arXiv:2503.21760, https://arxiv.org/abs/2503.21760
- Prateek Chhikara et al., "Mem0: Building Production-Ready AI Agents with
  Scalable Long-Term Memory", arXiv:2504.19413,
  https://arxiv.org/abs/2504.19413
- Hongli Yu et al., "MemAgent: Reshaping Long-Context LLM with Multi-Conv
  RL-based Memory Agent", arXiv:2507.02259,
  https://arxiv.org/abs/2507.02259
- Yu Wang and Xi Chen, "MIRIX: Multi-Agent Memory System for LLM-Based Agents",
  arXiv:2507.07957, https://arxiv.org/abs/2507.07957
- Runnan Fang et al., "Memp: Exploring Agent Procedural Memory",
  arXiv:2508.06433, https://arxiv.org/abs/2508.06433
- Jizhan Fang et al., "LightMem: Lightweight and Efficient
  Memory-Augmented Generation", arXiv:2510.18866,
  https://arxiv.org/abs/2510.18866
- Zouying Cao et al., "Remember Me, Refine Me", arXiv:2512.10696,
  https://arxiv.org/abs/2512.10696
- Qirui Mi et al., "Skill-Pro", arXiv:2602.01869,
  https://arxiv.org/abs/2602.01869
- Tao Feng et al., "Thought-Retriever", arXiv:2604.12231,
  https://arxiv.org/abs/2604.12231
- Jiaqi Liu et al., "EvolveMem", arXiv:2605.13941,
  https://arxiv.org/abs/2605.13941

Benchmarks:

- Adyasha Maharana et al., "Evaluating Very Long-Term Conversational Memory of
  LLM Agents", arXiv:2402.17753, https://arxiv.org/abs/2402.17753
- Di Wu et al., "LongMemEval", arXiv:2410.10813,
  https://arxiv.org/abs/2410.10813
- Haoran Tan et al., "MemBench", Findings of ACL 2025,
  DOI:10.18653/v1/2025.findings-acl.989,
  https://aclanthology.org/2025.findings-acl.989/
- Yuanzhe Hu et al., "Evaluating Memory in LLM Agents via Incremental
  Multi-Turn Interactions", arXiv:2507.05257,
  https://arxiv.org/abs/2507.05257
- Mohammad Tavakoli et al., "Beyond a Million Tokens", arXiv:2510.27246,
  https://arxiv.org/abs/2510.27246
- Alina Shutova et al., "Evaluating Memory Structure in LLM Agents",
  arXiv:2602.11243, https://arxiv.org/abs/2602.11243
- Zexue He et al., "MemoryArena", arXiv:2602.16313,
  https://arxiv.org/abs/2602.16313
- "AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications",
  arXiv:2602.22769, https://arxiv.org/abs/2602.22769
- Di Wu et al., "LongMemEval-V2", arXiv:2605.12493,
  https://arxiv.org/abs/2605.12493
- Lewis Liu and Nishant Yadav, "Introducing STATE-Bench: A benchmark for AI
  agent memory", Microsoft Open Source Blog, 2026-05-19,
  https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/

## Recommended V0 / V1 / V2 Scope

### V0: Interface And Trace Skeleton

Goal: make the memory boundary real without making memory behavior matter yet.

Include:

- `MemorySystem` injectable interface.
- `MemoryToolProvider` exposing read-only `recall` only when explicitly
  enabled.
- `EmptyMemorySystem` or equivalent returning no candidates.
- stable recall input/output schema and schema hash.
- memory trace events for request, result, dropped reasons, latency.
- raw provenance remains separate from durable memory.
- no prompt injection.
- no model-writable memory.
- no graph traversal.

Done when:

- enabling/disabling recall changes only the tool surface snapshot as expected.
- recall result is paired, empty, read-only, and auditable.
- no implementation path can read raw transcript items as memory.

### V1: Approved Read-Only Project Memory

Goal: prove bounded recall can help without introducing autonomous writes.

Include:

- project-scoped approved durable memory entries.
- manual/reviewer-approved seed memories from existing artifacts.
- memory kinds: `episodic_task`, `project_fact`, `failure_shield`,
  `reviewer_correction`.
- exact/path/symbol/tag search first; optional vector search only behind a
  feature flag.
- stale/superseded filtering.
- bounded recall result with source/proof refs.
- Harbor fixtures with memory-on/memory-off comparison.

Do not include yet:

- automatic durable writes.
- prompt-section memory projection.
- self-evolving retrieval configuration.
- unbounded graph recall.

### V2: Candidate Writes, Graph Expansion, Procedural Repair Memory

Goal: start turning repeated mew work into approved durable advantage.

Include:

- candidate extraction at session close, verifier boundary, reviewer/user
  correction, and repeated failure.
- candidate queue with kind-specific approval gates.
- typed graph edges for `derived_from`, `supersedes`, `contradicts`,
  `same_task_shape`, `failure_cluster`, `file_symbol`, `reviewer_correction`.
- bounded chain recall after seed retrieval.
- procedural repair memory with strong proof requirements.
- stale handling tied to file hash, verifier command, task contract, and
  reviewer veto.
- scoring dashboard or JSONL metrics for write precision, stale recall,
  memory-attributable wins, and repeated failure blocking.

Optional late-v2:

- tiny prompt projection for high-confidence preferences or active project
  conventions through `PromptSectionRegistry`.
- offline consolidation/rehearsal pass.

## Recommended Mew Architecture

```text
Native transcript / replay / verifier artifacts
  - append-only
  - content-addressed
  - not directly recallable as memory

Candidate extraction
  - event-triggered
  - produces typed candidates
  - binds source refs and proof refs

Approval / write gates
  - scope check
  - contradiction check
  - freshness check
  - privacy check
  - utility score
  - reviewer/user/policy approval by memory kind

Durable MemoryStore
  - typed entries
  - revision lineage
  - validity state
  - proof context
  - invalidators

Indexes
  - exact/path/symbol/tag
  - optional vector
  - typed graph edges
  - failure cluster index

MemorySystem
  - recall: read-only evidence retrieval
  - revise: consumes approved candidates, not raw model prose
  - project: bounded prompt projection for future phases
  - trace: observability and scoring

MemoryToolProvider
  - owns provider-visible `recall` schema
  - delegates to MemorySystem
  - never owns memory policy

PromptSectionRegistry
  - future bounded projection only
  - separate from ToolRegistry
```

Recommended memory entry shape:

```text
memory_id
kind
scope
summary
claim_or_procedure
trigger_conditions
source_refs
proof_refs
validity_state
confidence
utility_score
created_at
last_verified_at
invalidators
supersedes
contradicts
related_edges
```

Recommended recall request shape:

```text
query
scope
allowed_kinds
target_paths
symbols
failure_classes
max_candidates
max_chain_depth
freshness_policy
include_superseded
```

Recommended recall result shape:

```text
candidates[]
chain_nodes[]
dropped_by_reason
scope_used
index_versions
latency_ms
trace_id
```

The important product decision: memory must shorten or improve work while
remaining inspectable. If a memory cannot cite evidence and cannot be
invalidated, it should not affect `implement_v2`.

## Do Not Do Yet

- Do not auto-write durable memory from every model turn.
- Do not inject raw transcripts, old tool outputs, or old model prose into the
  prompt as memory.
- Do not make memory a second planner or next-action authority.
- Do not let `ToolRegistry` own memory storage, graph policy, or prompt
  projection.
- Do not create a single global vector store for user, project, task, and
  procedural memory.
- Do not let project facts leak across projects through user-scope memory.
- Do not promote user preferences without explicit user approval or manual
  edit.
- Do not promote procedural memories from failed or speculative trajectories
  without verifier/reviewer proof.
- Do not enable graph traversal without depth/fanout/staleness limits and
  dropped-candidate telemetry.
- Do not optimize retrieval configuration with EvolveMem-style self-evolution
  before v1/v2 observability and regression gates exist.
- Do not score M6.25 only on LoCoMo or LongMemEval. They are useful sanity
  checks, not proof of resident coding advantage.
- Do not use prompt projection until native recall traces prove which memories
  are actually useful.
