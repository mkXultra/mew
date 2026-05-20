# Review 2026-05-20 - MemoryArena Feasibility For M6.25

Status: feasibility report.

Scope: whether MemoryArena should be used to evaluate mew's future
`MemorySystem` core before it is connected to `implement_v2`.

Recommendation: use MemoryArena as an auxiliary generic benchmark for
`memory -> later action` behavior, but do not use it as the M6.25 acceptance
gate. The acceptance gate should remain Harbor resident-memory coding fixtures.

## Executive Finding

MemoryArena is relevant because it evaluates memory in multi-session
Memory-Agent-Environment loops instead of static recall QA. That matches the
M6.25 stance that memory must improve later work and should be scored before
being exposed through `implement_v2`.

It is not sufficient for mew because it is not a coding-agent benchmark. It
does not directly test repository conventions, verifier behavior, patch safety,
generated/protected file rules, reviewer rescue, WorkFrame/reentry, or
failure-shield behavior. Treat it as a subsystem sanity check, not proof of
resident coding advantage.

Practical feasibility is medium:

- The paper and Hugging Face dataset are available.
- The dataset can be loaded locally with Hugging Face `datasets`.
- The official project page's "Code" link currently points to generic
  `https://github.com`, not a specific repository, so exact official execution
  harness availability is unclear.
- A mew-owned adapter/harness is probably required for near-term use.

## What MemoryArena Evaluates

MemoryArena is a 2026 benchmark for interdependent multi-session agentic
tasks. The core question is whether an agent can learn from earlier
environment interactions, distill useful memory, retrieve it later, and use it
to solve dependent subtasks.

Task families:

| Family | What memory must preserve |
| --- | --- |
| Bundled web shopping | Earlier product attributes and compatibility constraints. |
| Progressive search | Accumulated search constraints across sessions. |
| Group travel planning | Previous travelers' preferences, plans, and relations. |
| Formal reasoning, math/physics | Prior definitions, lemmas, and intermediate derivation state. |

The paper reports task success rate and progress/process-style partial
completion measures, and compares long-context agents, external memory agents,
and RAG systems. The important signal for mew is not the leaderboard result;
it is the benchmark shape: dependent sessions where later success requires
preserved, relevant memory.

## Availability And Local Run Path

Known available resources:

- Paper: https://arxiv.org/abs/2602.16313
- Project page: https://memoryarena.github.io/
- Hugging Face paper page: https://huggingface.co/papers/2602.16313
- Dataset: https://huggingface.co/datasets/ZexueHe/memoryarena

Known dataset facts:

- Hugging Face repo id: `ZexueHe/memoryarena`
- Format: JSON/JSONL, CC-BY-4.0
- Configs shown on the project page and dataset card:
  `bundled_shopping`, `progressive_search`, `group_travel_planner`,
  `formal_reasoning_math`, `formal_reasoning_phys`
- Each row contains at least `id`, `questions`, `answers`, and sometimes
  `backgrounds` or task-specific fields.

Local dataset loading should work like:

```python
from datasets import load_dataset

for config in [
    "bundled_shopping",
    "progressive_search",
    "group_travel_planner",
    "formal_reasoning_math",
    "formal_reasoning_phys",
]:
    ds = load_dataset("ZexueHe/memoryarena", config, split="test")
    print(config, len(ds), ds.features)
```

Known unknowns:

- No specific official GitHub harness repo was found from primary sources. The
  project page has a "Code" button, but it currently links to generic GitHub.
- Exact official prompts, agent wrappers, environment simulators, scoring
  scripts, and baseline reproduction commands are therefore unclear.
- The paper and Hugging Face dataset counts may not be perfectly identical for
  every split/config; pin the HF dataset SHA before comparing results.

Implication for mew: start with a mew-owned lightweight harness over the HF
JSONL data. Do not wait for official code unless the next M6.25 step requires
leaderboard-compatible reproduction.

## Adapter Boundary For Mew

The adapter should evaluate `MemorySystem` directly, without `implement_v2`,
`ToolRegistry`, provider-visible `recall`, or production prompt injection.

Recommended boundary:

```text
MemoryArena row
  -> ArenaTaskAdapter
  -> MemorySystem seed/update/recall calls
  -> RecallTrace JSONL + optional BenchmarkMemoryEvidencePacket
  -> scorer
```

Minimum adapter responsibilities:

- Read one MemoryArena row and expose ordered subtasks as sessions.
- Reset memory per task id.
- Support explicit modes:
  `memory_off`, `memory_on`, `stale`.
- Convert current subtask query/background into `MemoryRecallRequest`.
- Seed approved durable entries from prior subtasks for read-side evaluation.
- Optionally test write path later by converting prior traces into
  candidate/proposal/approved/committed entries.
- Call only direct read-side APIs:
  `MemorySystem.recall()`, optional `adapt_recall()`, optional
  `expand_chain()`.
- Emit artifacted traces with request hash, store snapshot hash, recall config,
  returned ids, dropped reasons, timing, and result size.

Core-only evaluation can score whether expected proof-bearing memory is
returned for later subtasks. Downstream evaluation can then pass a bounded
`BenchmarkMemoryEvidencePacket` to a task solver, but that packet must remain
benchmark-only evidence, not an `implement_v2` integration path.

## Metrics To Extract

Every row should declare:

```text
task_family
task_id
subtask_index
memory_mode: off | on | stale
memory_snapshot_hash
recall_config_hash
runner_config_hash
```

Required memory metrics:

| Metric | Use |
| --- | --- |
| Memory off/on/stale comparison | Confirms memory benefit and stale-memory safety separately. |
| Evidence hit rate | Did recall return the expected proof-bearing memory? |
| Recall@k / MRR | Retrieval quality for rows with known expected memory. |
| Stale-as-fresh count | Must be zero for seeded stale entries in accepted rows. |
| Contradiction rate | Measures whether contradictory memory is labeled or dropped. |
| Dropped count by reason | Explains filtering, budget, staleness, contradiction, scope misses. |
| Latency p50/p95 | Keeps recall usable before tool exposure. |
| Returned item count and character/token size | Prevents context flooding. |
| Useful-recall ratio | Returned useful evidence divided by returned memory. |

Required downstream metrics if a task solver is run:

- task success rate;
- progress/process score or subtask completion fraction;
- repeated exploration/read/search reduction;
- first useful action latency, if measurable;
- memory-on no-regression against memory-off;
- stale-mode success only when stale memory is rejected, downgraded, or
  verified against current evidence.

## What Not To Evaluate With MemoryArena

Keep these in Harbor resident/coding fixture work:

- repository-specific coding conventions;
- verifier/test pass and failure modes;
- protected or generated file safety;
- patch correctness and diff quality;
- reviewer correction and reviewer-rescue count;
- repeated failed approach blocking through `failure_shield` memory;
- file/symbol/path staleness tied to real repo changes;
- WorkFrame/reentry behavior;
- `implement_v2` tool-loop behavior;
- `MemoryToolProvider(recall)` schema exposure;
- production prompt projection through `PromptSectionRegistry`;
- whether memory changes ordinary coding-agent behavior safely.

MemoryArena should not be allowed to prove "mew has resident coding advantage."
It can only support "the generic MemorySystem core can retrieve and apply
cross-session memory under non-coding task pressure."

## Recommended Next Steps

1. Pin the HF dataset revision and record exact config counts.
2. Build a small read-only `ArenaTaskAdapter` outside `implement_v2`.
3. Start with direct recall scoring only:
   `memory_off`, `memory_on`, and synthetic `stale`.
4. Use gold/fixture-seeded approved entries first; test autonomous writes only
   after the candidate/proposal/approval/commit path exists.
5. Set default pass expectations before running:
   evidence hit threshold, stale-as-fresh zero, p95 recall budget, result-size
   budget, and memory-on no-regression.
6. Add optional downstream task-solver rows only after direct recall artifacts
   are stable.
7. Run Harbor resident-memory rows in parallel and make Harbor the Phase 3
   close gate.

## Main Risks

| Risk | Mitigation |
| --- | --- |
| Official execution harness unavailable or unclear. | Use HF JSONL with a mew-owned harness; do not claim official leaderboard compatibility. |
| Benchmark mismatch with coding-agent memory. | Treat MemoryArena as auxiliary; Harbor decides M6.25 readiness. |
| Gold-answer leakage when seeding memory. | Seed only reusable evidence entries with source/proof refs; do not seed final answers for the same subtask. |
| Measuring solver/model skill instead of memory core. | Separate direct recall scoring from downstream action scoring. |
| Stale mode is synthetic, not native to the dataset. | Make stale fixtures explicit and artifacted; count them separately. |
| Context flooding from memory evidence. | Enforce result-size and item-count budgets before downstream use. |
| Overfitting to non-coding tasks. | Require Harbor no-regression and resident-advantage metrics before any Phase 4 exposure. |

## Sources

- Zexue He et al., "MemoryArena: Benchmarking Agent Memory in Interdependent
  Multi-Session Agentic Tasks", arXiv:2602.16313,
  https://arxiv.org/abs/2602.16313
- MemoryArena project page, https://memoryarena.github.io/
- Hugging Face paper page for arXiv:2602.16313,
  https://huggingface.co/papers/2602.16313
- Hugging Face dataset `ZexueHe/memoryarena`,
  https://huggingface.co/datasets/ZexueHe/memoryarena
- Local M6.25 design input:
  `docs/DESIGN_2026-05-20_M6_25_MEMORY_CORE_AND_EVALUATION.md`
- Local literature input:
  `docs/REVIEW_2026-05-20_M6_25_MEMORY_SUBSYSTEM_LITERATURE.md`
  and `docs/REVIEW_2026-05-20_AGENT_MEMORY_TRENDS.md`
