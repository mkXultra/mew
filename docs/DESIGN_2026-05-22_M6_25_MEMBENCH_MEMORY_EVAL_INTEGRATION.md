# Design 2026-05-22 - M6.25 MemBench Memory Eval Integration

Status: reviewed design candidate for a future implementation phase.

Scope: define how MemBench should be used as a source for curated
`memory_eval` fixtures after the committed M6.25 P0/P1 harness, without
turning `memory_eval` into a full agent answer benchmark.

This document authorizes no implementation changes and no fixture generation.

## Decision Summary

MemBench should be integrated into mew as a source corpus for curated
`memory_eval` fixtures, not as the primary scoring loop.

The first useful integration is a small P2/P3 fixture family that stresses
support-grounded compositional recall, scoped retrieval, budgeted context
assembly, noise robustness, and carefully validated update cases. Scoring
should remain deterministic and support-ID based before any answer artifact is
introduced.

The official MemBench multiple-choice loop should not be the primary
`memory_eval` score because it mixes at least four variables:

- memory ingestion and retrieval quality;
- memory context assembly quality;
- the answer model and prompt;
- the multiple-choice distractor distribution.

For mew, the primary question inside `memory_eval` remains:

```text
Did the memory adapter return the right active, in-scope support evidence,
with reproducible artifacts and no hidden gold leakage?
```

Whether an agent then answers the user-facing question correctly belongs to an
optional answer artifact or to `memory_behavior_bridge` plus `behavior_eval`,
where the external outcome is explicitly separated from memory-component
correctness.

## Sources Inspected

Local sources:

- `docs/another/mem_eval_fw.md`
- `docs/DESIGN_2026-05-21_M6_25_MEMORY_EVAL_HARNESS_IMPLEMENTATION_PLAN.md`
- `docs/DESIGN_2026-05-20_M6_25_MEMORY_CORE_AND_EVALUATION.md` read only
- `docs/REVIEW_2026-05-20_M6_25_MEMORY_SUBSYSTEM_LITERATURE.md`
- `src/mew/memory_eval/`
- `fixtures/memory_eval/p0`, `fixtures/memory_eval/p1`
- `tests/test_memory_eval_fixture_split.py`
- `tests/test_memory_eval_p1.py`

External sources:

- Tan et al., "MemBench: Towards More Comprehensive Evaluation on the Memory
  of LLM-based Agents", Findings of ACL 2025,
  https://aclanthology.org/2025.findings-acl.989/
- MemBench project README,
  https://github.com/import-myself/Membench
- MemBench benchmark code paths:
  `benchmark/env/Membenenv.py`, `benchmark/MembenchAgent.py`,
  `benchmark/load_test_data.py`

The inspected external sources confirm the high-level facts needed for this
design: MemBench has factual and reflective levels, participation and
observation scenarios, public data categories for first-agent and third-agent
settings, noise data, target step IDs for retrieval recall, and a
multiple-choice answer loop driven by an answer model over recalled memory
context.

## Existing Boundary To Preserve

The committed M6.25 P0/P1 harness owns deterministic memory-component
evaluation through a neutral adapter boundary:

```text
manifest
reset
ingest
mutate
retrieve
report_usage
```

The harness already separates:

- adapter-visible public fixture view;
- scorer-only gold view;
- opaque adapter IDs;
- support/provenance-lite mapping through `support_experience_ids`;
- deterministic request, operation prefix, result, public, gold, and full
  hashes;
- hard gates for scope, stale/conflict, forbidden retrieval, support mapping,
  budget, abstention, unsupported capability, and label leakage.

This MemBench integration must preserve the same ownership split:

| Layer | Owns | Must not own |
| --- | --- | --- |
| `memory_eval` | Memory adapter ingestion, mutation, retrieval, context artifact quality, support mapping, deterministic hashes, leakage checks, scope/freshness/budget gates. | Full agent success, official MemBench answer accuracy as a primary score, terminal task pass/fail. |
| `memory_behavior_bridge` | Links memory artifacts to external behavior runs and records memory-specific explanatory variables. | Source-of-record task success. |
| `behavior_eval` / terminal bench | User-facing or agent-facing task success, including official answer-loop style outcomes. | Memory adapter conformance or deterministic retrieval correctness. |

## MemBench Shape And Assumptions

MemBench is useful because it provides synthetic long-memory situations with
explicit support pointers. It is also risky because some of its metadata is
label-like and because official accuracy depends on an answer model.

### Published Benchmark Framing

The paper frames MemBench as evaluating memory in LLM-based agents across:

- factual memory and reflective memory;
- participation and observation scenarios;
- effectiveness, efficiency, and capacity dimensions.

The project README describes four main dataset groupings:

- Participation-Factual, represented as `FirstAgentLowLevel`;
- Participation-Reflective, represented as `FirstAgentHighLevel`;
- Observation-Factual, represented as `ThirdAgentLowLevel`;
- Observation-Reflective, represented as `ThirdAgentHighLevel`.

It also describes noise data and sampled data intended for 0-10k and 100k
conversation lengths.

### Raw Data Pattern

At a high level, each MemBench trajectory has:

- `tid`, a trajectory ID;
- `message_list`, the observations or conversation turns to feed to memory;
- `QA`, containing a question, time, choices, ground-truth option, answer text,
  and `target_step_id`.

Observed shapes include:

- Third-agent factual records where each message is a single observation with
  fields such as `message`, `time`, `place`, and label-like metadata such as
  `rel`, `attr`, and `value`.
- First-agent factual records where `message_list` can be nested sessions of
  user/assistant turns with `user_message` / `assistant_message` or
  `user` / `assistant` fields.
- Reflective high-level records where one logical trajectory can contain
  grouped message segments and `target_step_id` points to multiple support
  messages.
- Noise-augmented records where original target step IDs are relocated after
  injected noise.

For original MemBench trajectory conversion, `target_step_id` is the valuable
qrel source. For MTEB/Hugging Face qrels conversion, the dataset-provided
`qrels` are the valuable support mapping. Fields such as `rel`, `attr`,
`value`, `answer`, `ground_truth`, `choices`, and the raw category name are
scorer-only unless a later answer-artifact phase explicitly needs choices
outside the memory adapter boundary.

### Official Runtime Pattern

The official environment feeds messages in sequence, then emits a QA object
with a question, time, choices, ground truth, and target step IDs. The agent
stores each message in a memory module. At question time, it recalls memory
context, sends that context plus the question and choices to an answer LLM, and
returns an option. The agent may also return `memory_index`; the environment
can compute recall by comparing that index to `target_step_id`.

That split is exactly why mew should not use official multiple-choice accuracy
as the primary `memory_eval` score. The retrieval target is a memory-component
signal. The selected answer letter is a model-in-loop behavior signal.

## Integration Stance

Use MemBench-derived fixtures to ask whether a memory component can find the
right support evidence under composition, noise, and selected update pressure.

Do not use MemBench-derived fixtures to ask whether a full agent can reason,
choose the right multiple-choice option, or complete an end-user task. Those
belong outside `memory_eval` core.

### Appropriate For P2/P3

The following categories are appropriate after curation and validation:

| MemBench source | Use in mew | Phase fit |
| --- | --- | --- |
| Observation-Factual / `ThirdAgentLowLevel` simple factual items | Single-support and few-support retrieval, ranking, scope, and noise tests. | Early P2 deterministic support retrieval and context artifact fixtures. |
| Participation-Factual / `FirstAgentLowLevel` conversation turns | Conversation-turn support retrieval and session-aware support mapping. | Early P2 after flattening nested sessions deterministically. |
| Aggregative, comparative, and conditional factual questions | Multi-support compositional recall where the scorer checks support-set coverage, not answer reasoning. | P2 deterministic support-set scoring. |
| Observation-Reflective and Participation-Reflective high-level examples | Support-grounded reflective recall where the expected evidence is multiple mentions. | Dry-run or P3 judged-memory-artifact candidates by default; P2 only after reviewer confirmation that support IDs are necessary and sufficient. |
| Noise-augmented examples | Distractor and budget stress, with target relocation verified from source. | P2 after deterministic source hash and seed provenance are pinned. |
| Update-like or contradiction-like examples discovered in pinned source files | Supersede/update/stale pressure when old and new support can be unambiguously mapped. | Late P2 or P3 only after manual stale/fresh validation. |

The first deterministic fixture pack should focus on Observation-Factual and
Participation-Factual examples. Reflective examples are excluded by default
unless a reviewer explicitly confirms that the gold support set is necessary
and sufficient for the expected memory artifact. Reflective examples requiring
abstraction, summarization, or semantic judgment beyond support retrieval
remain dry-run candidates or P3 judged memory-artifact candidates.

Update fixtures must be discovery-based, not category-name dependent. The
converter should discover update-like or contradiction-like examples from
pinned source files, then require manual mapping to old/stale support IDs,
fresh/active support IDs, an explicit `update` or `supersede` operation, and a
query time after the mutation effective time. If old/fresh support cannot be
mapped unambiguously, defer the example.

### Exclude Or Defer

The following should not be part of the first MemBench fixture pack:

| Source or behavior | Reason |
| --- | --- |
| Official MemBench multiple-choice accuracy as the main score | It mixes retrieval, context, answer model, prompt, and distractors. |
| Official answer LLM prompts inside `memory_eval` core | They make deterministic memory-component scoring model-dependent. |
| 100k or full capacity sets | Scale stress should come after small fixtures make failures diagnosable. |
| Uncurated reflective examples | Some require abstraction beyond deterministic support retrieval; use only after support sufficiency is reviewed. |
| Category-name-only update selection | Upstream category names may not be stable; update-like examples must be discovered from pinned source content and manually mapped to `supersede`, `update`, or deferred. |
| Public benchmark leaderboard claims | Curated mew fixtures are internal harness material, not a comparable MemBench leaderboard result. |
| Any fixture whose adapter-visible experience text, request fields, metadata, or IDs leak `rel`, `attr`, `value`, `answer`, `ground_truth`, `target_step_id`, category, mode, or trap labels | Leakage invalidates the fixture. |

## Fixture Conversion Model

Each selected MemBench trajectory should become one or more
`memory_eval_fixture.v1` fixtures. A converter can be introduced later, but it
must emit the same public/scorer split as the existing P0/P1 fixtures.

### Source Locator

The converter should first normalize every MemBench message into an internal
source locator:

```json
{
  "dataset": "membench",
  "upstream_commit": "git sha",
  "source_path": "MemData/ThirdAgent/simple.json",
  "category": "roles",
  "trajectory_tid": 0,
  "message_locator": {
    "outer_index": 0,
    "inner_index": null,
    "mid": 10,
    "sid": null
  }
}
```

This source locator is not adapter-visible. It exists to make qrel conversion,
duplicate diagnosis, source hashing, and reviewer review deterministic.

Source locator visibility rules:

| Surface | Allowed source detail |
| --- | --- |
| `adapter_view` | No raw source path, category, `target_step_id`, source qrel, source locator, or benchmark-specific label. |
| Public run artifact | May include `source_benchmark_id` and source hash summaries only. |
| Scorer artifact | May include source locator hashes and qrel hashes. |
| Reviewer/debug artifact | May include raw source locator details only when explicitly scorer-only or debug-only. |

Raw source paths, categories, qrel locators, and `target_step_id` must never be
adapter-visible.

In particular, `source_benchmark.source_path` is scorer-only and must be
excluded from `adapter_view` and from public run artifacts. Public artifacts
may include only source hash summaries.

### Adapter-Visible Experience Payload

Adapter-visible `Experience` records should contain only externally observable
memory input. Generated public `Experience.experience_id` values use the
`exp_src_*` namespace. Source locators are separate and are never used directly
as evidence IDs.

```json
{
  "experience_id": "exp_src_000001",
  "scope_id": "tenant_mb/user_000001",
  "session_id": "session_000001",
  "turn_id": "turn_000001",
  "event_time": "2024-10-01T08:00:00Z",
  "ingest_order": 1,
  "actor_id": "user_000001",
  "payload": {
    "mime_type": "text/plain",
    "text": "My subordinate has an Associate Degree. (place: Boston, MA; time: 2024-10-06 10:34 Tuesday)"
  },
  "visibility": {
    "allowed_scope_ids": ["tenant_mb/user_000001"],
    "retrievable": true
  },
  "metadata": {
    "source_kind": "synthetic_memory_observation"
  }
}
```

For first-agent user/assistant turns, the payload may include both sides of the
observed turn because the official memory flow stores both. A stable format is
enough:

```text
user: ...
assistant: ...
time: ...
place: ...
```

Adapter-visible `Experience.payload.text` must be derived from externally
observed message text or the official observation text used in the benchmark
runtime. The converter must not synthesize public experience text from
scorer-only labels such as `rel`, `attr`, `value`, `answer`, `ground_truth`,
or `target_step_id` unless source audit confirms the same text was part of the
externally observed message stream. Rendering private labels into natural
language is label leakage.

The adapter-visible payload must not include:

- raw `rel`, `attr`, or `value` keys;
- normalized answer values from labels;
- `qid`, `answer`, `ground_truth`, `choices`, or `target_step_id`;
- benchmark category names such as `FirstAgentLowLevel`,
  `ThirdAgentHighLevel`, `simple`, `roles`, or update-like category labels
  when those names are not needed for retrieval;
- source file names, source paths, or fixture family names;
- descriptive IDs that encode expected behavior.

If the natural message text itself contains the fact being tested, that is not
leakage; the point of memory retrieval is to find that fact-bearing message.
Leakage is exposing the private label or qrel metadata that tells the adapter
which message is the answer.

### Scorer-Only Gold Mapping

Qrel source handling differs by source mode:

- Original MemBench trajectory mode: use `QA.target_step_id` as the
  scorer-only qrel source and map it through normalized source locators.
- MTEB/Hugging Face qrels mode: use dataset-provided `qrels` as the
  scorer-only support mapping. Do not assume `QA.target_step_id` exists. The
  converter must map qrel document IDs to generated
  `Experience.experience_id` values through the corpus manifest.

Both modes must produce the same `memory_eval` `scorer_view` shape:
`relevant_evidence_ids`, optional `acceptable_support_sets`, source locator
hashes, and support coverage policy.

In original MemBench trajectory mode, `QA.target_step_id` should convert to
scorer-only support IDs:

```json
{
  "request_id": "req_membench_internal_000001",
  "mode": "membench_support_retrieval",
  "requires_capabilities": ["retrieve"],
  "on_unsupported": "hard_failure",
  "gold": {
    "relevant_evidence_ids": ["exp_src_000010"],
    "expected_abstention": false,
    "source_qrels": [
      {
        "target_step_id": 10,
        "experience_id": "exp_src_000010",
        "source_locator_hash": "sha256:..."
      }
    ]
  }
}
```

The `mode` field in this example is a scorer-only request label. It may be
stored in the source fixture request block and in `scorer_view`, but it must be
stripped from the adapter-visible request passed to `retrieve()`.

For nested or high-level examples, normalize target locators before mapping:

- Integer `target_step_id` maps to the corresponding flat message step.
- Pair-like target IDs map to a source locator, not blindly to a numeric list
  position. The converter must know whether the pair means
  `[message_index, group_index]`, `[turn_index, session_index]`, or another
  MemBench-specific shape for that source file.
- Multiple target IDs become a support set. The scorer should be able to
  distinguish "any one of these supports is sufficient" from "all of these
  supports are required for a compositional memory artifact."

### Request Mapping

Adapter-visible retrieval requests should contain only retrieval-relevant
question information:

```json
{
  "request_id": "rq_000001",
  "scope_id": "tenant_mb/user_000001",
  "query_time": "2024-10-12T13:33:00Z",
  "query": {
    "text": "What is the education level of the subordinate?",
    "intent": "memory_lookup"
  },
  "k": 5,
  "filters": {
    "valid_at": "2024-10-12T13:33:00Z",
    "allowed_states": ["active"]
  },
  "budget": {
    "max_evidence_items": 5,
    "max_latency_ms": 500,
    "max_cost_units": null
  }
}
```

Choices should not be passed to the memory adapter for the primary retrieval
score. They are answer-task inputs, not memory-retrieval inputs. If a later
exact multiple-choice answer artifact is added, choices must be in the
answer-artifact input block, not in `retrieve()`.

`request_hash` must be computed over this stripped adapter-visible query. It
therefore excludes the scorer-side `mode`, descriptive request ID, qrels,
choices, answer metadata, and source benchmark labels.

Query time derivation:

- If `QA.time` is parseable, normalize it to RFC3339 and use it as
  `query_time`.
- If `QA.time` is absent or not parseable, use a deterministic synthetic query
  time after the last applied message, and preserve raw time only in
  scorer/debug metadata.
- The query checkpoint must be after all target support messages for ordinary
  retrieval fixtures. Otherwise reject the fixture as future support.

## Fixture Schema Extensions

The existing `memory_eval_fixture.v1` schema can carry the first MemBench
fixtures with minor scorer-only extensions. Avoid changing adapter-visible
public keys unless a concrete P2 context artifact requires it.

Recommended scorer-only additions:

The following example shows the full schema shape. For the first generated
fixture pack, `answer_artifact_gold` must be omitted even though the schema
allows it.

```json
{
  "source_benchmark": {
    "benchmark_id": "membench",
    "paper": "Tan et al. Findings ACL 2025",
    "project_url": "https://github.com/import-myself/Membench",
    "upstream_commit": "git sha",
    "source_file_sha256": "sha256:...",
    "source_path": "MemData/ThirdAgent/simple.json",
    "converter_id": "mew_membench_converter",
    "converter_version": "0.1.0",
    "conversion_manifest_hash": "sha256:..."
  },
  "requests": [
    {
      "request_id": "req_membench_internal_000001",
      "mode": "membench_support_retrieval",
      "gold": {
        "relevant_evidence_ids": ["exp_src_000010"],
        "acceptable_support_sets": [["exp_src_000010"]],
        "support_coverage_policy": "all_required",
        "source_qrels": []
      },
      "answer_artifact_gold": {
        "enabled": false,
        "question": "What is the education level of the subordinate?",
        "choices": {
          "A": "Bachelor's Degree",
          "B": "Associate Degree",
          "C": "High School Diploma",
          "D": "Master's Degree"
        },
        "ground_truth": "B",
        "answer_text": "Associate Degree"
      }
    }
  ]
}
```

Notes:

- `source_benchmark` is artifact/scorer-only. It must not appear in
  `adapter_view`.
- `source_benchmark.source_path` is scorer-only. It must not appear in
  `adapter_view` or public run artifacts; public artifacts may expose only
  source hash summaries.
- If `answer_artifact_gold` is introduced in a later phase, `enabled=false`
  should be the default until answer-artifact scoring is implemented and
  leakage-tested.
- `answer_artifact_gold` is schema-allowed but omitted from the first
  generated fixture pack. A dry-run report may include answer metadata counts
  and hashes for reviewer inspection, but committed P2 fixtures should not
  include `answer_artifact_gold` until answer-artifact scoring is implemented
  and leakage-tested. When this changes, `answer_artifact_gold` must affect
  `fixture_gold_hash` and must not affect `fixture_public_hash`.
- `acceptable_support_sets` is already anticipated by the implementation plan;
  if not implemented at the time of conversion, keep it scorer-only and do not
  let it affect scoring until the scorer supports it.
- `support_coverage_policy` should be one of `any_relevant`,
  `all_required`, or `min_count`.

Implementation-readiness note: generated MemBench fixtures must not rely on
these scorer-only fields until the future implementation extends
`split_fixture`, `scorer_view`, and hash tests for them. In particular,
`source_benchmark`, `source_qrels`, `acceptable_support_sets`,
`support_coverage_policy`, and `answer_artifact_gold` must be absent from
`adapter_view`, present in `scorer_view` when supplied, included in
`fixture_gold_hash`, and covered by tests that prove changing those fields does
not alter `fixture_public_hash`.

MemBench-derived fixtures using `acceptable_support_sets` or
`support_coverage_policy` require scorer support before they affect metrics.
Until implemented, these fields remain scorer-only metadata and must not
silently change P1 scoring behavior. Tests must prove they are absent from
`adapter_view`, present in `scorer_view`, included in `fixture_gold_hash`, and
excluded from `fixture_public_hash`.

## Support Coverage Policy Semantics

Support coverage policy controls how multi-support MemBench qrels turn into
deterministic support scoring:

| Policy | Required coverage |
| --- | --- |
| `any_relevant` | At least one relevant support ID from the gold support set must be covered. |
| `all_required` | Every evidence ID in at least one acceptable support set must be covered. |
| `min_count` | At least `N` unique relevant support IDs must be covered, where `N` is declared in scorer-only gold metadata. |

For `min_count`, the gold metadata must name the count explicitly:

```json
{
  "gold": {
    "support_coverage_policy": "min_count",
    "support_min_count": 2,
    "acceptable_support_sets": [
      ["exp_src_000010", "exp_src_000011", "exp_src_000012"]
    ]
  }
}
```

If `acceptable_support_sets` is present, the scorer must either derive
`relevant_evidence_ids` from the union of those sets or validate that
`union(acceptable_support_sets)` is a subset of `relevant_evidence_ids`.
Fixtures with inconsistent support sets, missing `support_min_count` values,
unknown evidence IDs, or support policies that the scorer does not implement
must fail validation rather than falling back to ordinary P1 behavior. If
`support_coverage_policy = min_count`, `support_min_count` must be present,
positive, and less than or equal to the number of unique relevant evidence IDs.

## Scoring Modes

### Mode 1: Deterministic Support Retrieval

This is the primary mode.

Inputs:

- public experiences from MemBench messages;
- public retrieval query with question and time;
- scorer-only support qrels from the selected source mode.

Adapter output:

- ranked evidence with `support_experience_ids` or a derived `evidence_ref`
  mapped to `support_experience_ids`;
- abstention when expected;
- usage and visible dropped records.

Metrics and gates:

- `support_recall_at_k`, `precision_at_k`, `support_precision_at_k`,
  `mrr_at_k`, `ndcg_at_k`;
- support-set coverage for compositional examples;
- no unknown or future support references;
- no duplicate support signature inflation;
- no cross-scope leak or exposure;
- no stale-as-fresh or contradiction-as-fresh when update fixtures are used;
- budget and usage gates;
- label leakage gate.

For MemBench-derived multi-support examples, `precision_at_k` remains
item-level, following M6.25 P1 scoring. A returned item is relevant if its
`scorable_support_ids` intersects the gold relevant evidence set. Do not define
`precision_at_k` as `|covered_support_ids ∩ relevant_support_ids| / k`,
because one returned derived item may cover multiple support IDs and could make
precision exceed 1.0. Use `support_precision_at_k` separately for support-ID
coverage precision.

This mode can start with ordinary `retrieve()` only. It should not require
`build_context` or an answer model.

Noise-derived and budget-stress fixtures must declare explicit `k`,
`max_evidence_items`, and, when context is scored, a context budget. Returning
all history must not be rewarded. Low precision under distractors, duplicate
support signatures, irrelevant context pollution, budget violations, and raw
history dumps that exceed item or token budgets must be penalized.

### Mode 2: Deterministic Context Artifact

This is a P2 extension for adapters that declare `build_context`.

Inputs:

- same support qrels as Mode 1;
- adapter retrieval result or context-build request;
- explicit token/item budget.

Scoring:

- required support coverage in the context packet;
- irrelevant or stale support pollution;
- raw label leakage;
- redaction of fields that must not be exposed;
- context budget compliance;
- provenance-lite coverage through support IDs.

This still does not score final answer correctness.

### Mode 3: Optional Exact Multiple-Choice Answer Artifact

This is explicitly secondary.

If added, it should produce a separate artifact block:

```json
{
  "answer_artifact": {
    "enabled": true,
    "source_of_record": "memory_eval_secondary_artifact",
    "answerer_id": "fixed_exact_or_model_id",
    "answerer_prompt_hash": "sha256:...",
    "input_context_hash": "sha256:...",
    "choices_hash": "sha256:...",
    "predicted_choice": "B",
    "ground_truth": "B",
    "exact_choice_correct": true,
    "excluded_from_primary_memory_score": true
  }
}
```

Hard rules:

- The answer artifact must not change `result_status` for primary
  memory-component scoring.
- Mode 3 must not affect primary request `result_status`, primary memory
  metrics, or memory adapter correctness gates.
- If a model is used, the model ID, prompt, temperature, seed, and response
  schema must be hashed and recorded.
- The answer artifact must never be used to excuse missing support retrieval.
  A guessed correct answer with no support remains a memory failure.

### Mode 4: Bridge-Linked External Outcome

The official MemBench loop, or any model-in-loop replay of it, belongs here:

```json
{
  "memory_behavior_bridge": {
    "external_benchmark_id": "membench_official_like_replay",
    "external_run_id": "run_...",
    "memory_artifact_hash": "sha256:...",
    "source_of_record": "behavior_eval",
    "excluded_from_memory_eval_core_score": true
  }
}
```

Official MemBench answer-loop replay belongs only to
`memory_behavior_bridge` / `behavior_eval`. `memory_eval` may link to the
external run and record artifact hashes, required support coverage, and
pollution flags, but it must not own official-loop success. Mode 4 must not
affect primary request `result_status`, primary memory metrics, or memory
adapter correctness gates.

## Import And Conversion Phases

### External-source / no-vendor mode

The preferred first integration mode is to use MemBench through a pinned
external source, not to commit raw source data or generated fixtures. This
keeps early validation useful while avoiding a premature vendor copy of
benchmark data.

Supported source paths:

- Hugging Face dataset `mteb/MemBench` for MTEB-style `corpus`, `queries`,
  `qrels`, and `top_ranked` subsets.
- Upstream GitHub or original data sources only after a separate source audit.

The manifest values below are illustrative; implementation must populate them
from the pinned source audit, not hard-code them. The source manifest should
include:

```yaml
source_mode: external_huggingface
source_dataset: mteb/MemBench
source_revision: pinned
source_subset: single_hop | multi_hop | comparative | aggregative | knowledge_updating | ...
declared_license: "<value from pinned dataset card or source audit>"
license_source: Hugging Face dataset card
citation_required: true
citation_targets:
  - mteb/MemBench dataset card
  - MTEB
  - LMEB/MMTEB processing if indicated by the dataset card
raw_file_hashes: required
local_cache_only: true
generated_fixture_commit_policy: no_vendor_by_default
redistribution_status: private_only | commit_allowed | blocked
redistribution_review:
  approved: true
  reviewer: "<reviewer name or handle>"
  reviewed_at: "calendar-valid YYYY-MM-DD"
  decision_basis: "<non-placeholder summary of the review basis>"
  scope: generated_fixtures_only
notice_file_required_if_committed: true
```

When MemBench-derived data is used, citation should appear in `README.md`,
`docs/THIRD_PARTY_DATA.md` or an equivalent notice location, the source audit
note, the conversion manifest, and evaluation reports. README citation alone
is not sufficient if generated fixtures are committed; committed derived
fixtures require source audit, notice/attribution, and reviewer-approved
`commit_allowed` status.

External-source mode can be used for local or CI evaluation with no raw or
generated data committed, but it still requires a pinned revision, raw hashes,
declared license and citation metadata, and clear local cache handling. Do not
overstate legal certainty: the Hugging Face dataset card currently shows MIT
and citation expectations, but source audit and revision/hash pinning remain
mandatory.

Phase 4a implementation note: source manifests now carry
`redistribution_status` with allowed values `private_only`, `commit_allowed`,
and `blocked`, plus notice/citation/provenance fields used by
`validate-source-manifest` to report Phase C fixture-commit readiness.
`private_only` remains the default and disallows committed generated fixtures.
`commit_allowed` is not sufficient by name alone; the source manifest must also
validate with an immutable pinned revision, full `sha256:` raw-file hashes,
non-placeholder source dataset/host/license fields, absolute non-placeholder
source and license-source URLs, declared license source, citation targets,
`generated_fixture_commit_policy: no_vendor_by_default`, and complete
`docs/THIRD_PARTY_DATA.md` notice metadata present. `blocked` and invalid
source-audit states refuse MTEB qrels dry-run conversion.

Phase 4b implementation note: `commit_allowed` also requires explicit
`redistribution_review` metadata before
`phase_c_commit_preconditions.status` can become `commit_allowed_ready`.
The review block must have `approved: true`, non-placeholder `reviewer`,
`reviewed_at` as a calendar-valid `YYYY-MM-DD` date, non-placeholder
`decision_basis`, and `scope: generated_fixtures_only`. This approval covers
only generated fixture commit readiness. It never changes
`raw_source_commit_allowed: false` and is not legal advice.

Phase 4c implementation note: local Hugging Face MTEB export preparation is a
separate raw-source preparation step. The command
`python -m mew.memory_eval.membench prepare-hf-mteb-qrels <output-dir>
--dataset mteb/MemBench --subset single_hop --revision <40-char commit sha>`
loads configs named `<subset>-corpus`, `<subset>-queries`, and
`<subset>-qrels`; `--include-top-ranked` also loads
`<subset>-top_ranked`. It writes only local raw-source JSONL files and
`source_manifest.json` under the chosen output directory, never under
`fixtures/memory_eval`, and never creates a generated fixture pack. The helper
uses the `datasets` development dependency; runtime installs still do not need
`datasets`, and missing `datasets` should fail clearly. The default loader uses
a local-files-only download configuration so a cache miss fails rather than
fetching raw MemBench during this preparation step. Older `datasets` versions
that cannot provide `DownloadConfig(local_files_only=True)` must fail clearly
instead of falling back to network access. The pinned `--revision` remains
required before any Hugging Face load is attempted, and the generated manifest
defaults to `local_cache_only: true`,
`generated_fixture_commit_policy: no_vendor_by_default`, and
`redistribution_status: private_only`.

Phase 4d implementation note: MemBench dry-run validation uses a
qrels-oracle reference adapter for converter/scorer sanity checks. This
reference target replays scorer-only qrels through opaque public evidence IDs;
it is not a memory-quality baseline. Real memory adapter quality is measured by
separate targets such as `TypedCardsMemoryEvalAdapter`. MemBench external
fixtures also use converter-specific adapter-view leakage checks instead of the
generic synthetic P0/P1 blocked-token scan, because natural corpus text may
legitimately contain words such as `family` or `stale`. Scorer-only keys,
source locators, qrels, target IDs, answers, and label-rendered values remain
forbidden in adapter-visible payloads.

Phase 4e implementation note: dry-run conversion supports deterministic corpus
sampling so full and smoke runs can share the same converter. Use
`--corpus-sample-policy full` for stress/full-corpus runs. Use
`--corpus-sample-policy qrel_plus_prefix --max-corpus-docs N` for smoke runs
that always include the gold qrel documents plus the first prefix distractors.
Use `qrel_plus_random` for seed-stable random distractors. Sampling changes the
fixture's effective corpus and hashes, so reports must include the sampling
policy, seed, full corpus size, effective corpus size, and whether all qrel
documents were included. Sampling is for local dry-run and adapter smoke
validation; it does not create a committed fixture pack or change source-audit
redistribution status.

Phase 4f implementation note: MemBench profiles are operator-facing wrappers
for local validation runs. They perform prepare/source-gate/dry-run/validation
in one command, but the profile report keeps those phases separate:

```text
setup.prepare
setup.source_gate
setup.dry_run
run.validation
```

Available initial profiles:

| Profile | Purpose | Shape |
| --- | --- | --- |
| `membench-smoke200-typed` | Small wiring check. | `single_hop`, `max_queries=1`, `qrel_plus_prefix`, `max_corpus_docs=200`, TypedCards validation. |
| `membench-sample1000-typed` | Intermediate local validation before a full profile. | `single_hop`, `max_queries=10`, `qrel_plus_prefix`, `max_corpus_docs=1000`, TypedCards validation. |

The wrapper writes local artifacts under `tmp/membench-profiles` by default. By
default it pins Hugging Face
`mteb/MemBench` to dataset commit
`1dd519e4d91573e2818d850eb4405fb290663ac2`; that revision is an upstream data
snapshot pin for reproducibility, not a mew code version. The wrapper is
intended for local diagnosis and must not be treated as permission to commit
raw source data or generated fixtures.

### Phase A: Source Audit

Generated MemBench-derived fixtures MUST NOT be committed until:

- the MemBench upstream repository commit is pinned;
- raw source file hashes are recorded;
- code license and data license are reviewed separately;
- redistribution permission for generated fixtures is classified as
  `commit_allowed`, `private_only`, or `blocked`;
- a reviewer explicitly approves generated fixture commit readiness in
  `redistribution_review` when `redistribution_status` is `commit_allowed`.

Before any fixture generation, also verify whether data is available through
the GitHub repository, Git LFS, Google Drive, Baidu, or another source, and
inspect whether selected examples contain synthetic personal-like emails,
phone numbers, or addresses that should be sanitized.

Output: source audit note and conversion manifest. No fixtures yet.

### Phase B: Converter Dry Run

Build a converter that emits a dry-run report before writing fixtures:

- selected source files and categories;
- number of candidate trajectories;
- qrel mapping success rate;
- skipped examples and reasons;
- detected duplicate IDs or ambiguous `target_step_id` shapes;
- label-like keys found in source and removed from adapter-visible output;
- adapter-view key scan results;
- adapter-view string value scan results;
- scorer-only field list removed from adapter view;
- public/gold/full hash preview;
- confirmation that changing qrels, choices, answers, target IDs, or source
  benchmark metadata changes only gold/full hashes, not public hash;
- rejected leakage examples and exact rejection reasons;
- category distribution;
- estimated token and item budgets.

Dry-run artifacts that contain raw source text, raw source paths, categories,
target IDs, or label-like metadata must not be committed unless the source
audit status is `commit_allowed`. Otherwise they are local-only reviewer
artifacts.

Output: dry-run JSON/Markdown artifact. Still no committed fixtures.

## Converter Test Matrix

The converter test matrix must cover:

- single integer `target_step_id`;
- multiple integer `target_step_id`;
- pair-like high-level `target_step_id`;
- MTEB/Hugging Face qrel document ID mapping through the corpus manifest;
- nested first-agent session target IDs;
- noise-relocated target IDs;
- ambiguous target ID rejection;
- duplicate source locator disambiguation;
- target support after request checkpoint rejection;
- source qrel mapped to missing message rejection;
- answer choices absent from adapter-visible `retrieve()` input;
- `source_benchmark`, `source_qrels`, `target_step_id`, `answer`,
  `ground_truth`, and `choices` absent from `adapter_view`.

### Phase B.5: Adapter Validation Targets

Before generating committed fixtures, validate the converted dry-run fixtures
against two adapter classes:

- `ReferenceP1Adapter` is the converter/scorer oracle sanity target. It should
  pass fixtures whose qrels, support coverage policy, budget, and
  public/scorer split are internally consistent.
- Broken reference adapters remain the negative-control targets. They should
  fail expected gates for missing support, future support, cross-scope
  exposure, stale-as-fresh support, duplicate support signatures, budget
  violations, and unscorable evidence.
- `TypedCardsMemoryEvalAdapter` is the first real mew memory-core validation
  target. It checks whether the current typed-card memory subsystem can ingest
  MemBench-derived public experiences and return scorer-compatible support
  mappings through the neutral memory_eval adapter boundary.

Initial MemBench runs against `TypedCardsMemoryEvalAdapter` should keep
deterministic replay extractor mode as the hermetic gating path. Live model
extraction is now allowed only as an explicit local smoke/diagnostic path:
`--typed-cards-extractor-mode live_model --allow-live-model-tests`. Live runs
use the configured typed-card extractor backend, defaulting to codex
`gpt-5.5`, write local artifacts, and are non-gating by default. A live failure
should create diagnostics for extractor drift; it must not fail hermetic CI
unless the operator explicitly opts into live-model gating.

Adapter validation should not change fixture commit policy. Source audit,
license/citation review, hash pinning, leakage checks, and reviewer approval
remain required before any generated MemBench-derived fixtures are committed.

### Phase C: Small Curated Fixture Pack

Phase C fixture generation is blocked unless Phase A marks selected source
files as `commit_allowed` or explicitly `private_only` for local-only
evaluation. A generated fixture pack may be committed only when the selected
source audit status is `commit_allowed` and the manifest includes complete
`redistribution_review` approval metadata scoped to
`generated_fixtures_only`; `private_only` permits local-only evaluation
artifacts but not committed fixtures.

Create a first reviewed pack only after Phase A and B pass:

- 5 to 10 single-support factual examples;
- 5 to 10 multi-support compositional examples;
- 3 to 5 noise/distractor examples;
- 2 to 3 manually validated update/supersede examples, or defer update if
  mapping is not unambiguous.

The first pack should focus on Observation-Factual and Participation-Factual
examples where the support messages are human-verifiable and where target IDs
map cleanly. Do not chase category coverage at the cost of unclear gold.

First generated fixture pack acceptance gate:

- source audit status is `commit_allowed` for committed fixtures;
- `redistribution_review.approved` is exactly `true`, with non-placeholder
  reviewer, review date, decision basis, and `scope: generated_fixtures_only`;
- converter dry-run report has been reviewed;
- every qrel maps to exactly known source messages;
- every target support is applied before request time;
- `adapter_view` contains no scorer-only keys or values;
- changing scorer-only qrels changes `fixture_gold_hash` but not
  `fixture_public_hash`;
- reference adapter passes;
- intentionally broken adapters fail expected gates;
- reviewer manually verifies every selected example's support sufficiency.

Scope-isolation MemBench-derived fixtures may require synthetic wrapping. The
converter may place similar trajectories or paraphrased facts into neighboring
synthetic scopes, but adapter-visible scope IDs must remain opaque and must not
encode source category, expected behavior, or qrel labels.

### Phase D: Validation And Harness Run

Run the same validation style as P0/P1:

- adapter view contains no scorer-only keys or values;
- public/gold/full hashes are stable;
- adapter-visible IDs are opaque and deterministic;
- every qrel maps to an applied experience before request time;
- no qrel points to a future or missing support item;
- duplicate source locators are disambiguated;
- reference adapter passes;
- intentionally broken adapters fail expected gates.

### Phase E: Expansion And Holdout

Only after the small pack is useful:

- add held-out private fixture splits for regression protection;
- add longer noise variants with pinned sample seeds;
- add larger stress sets if diagnostic artifacts remain readable;
- consider bridge-linked official-loop comparisons outside primary
  `memory_eval`.

## Validation Checks

The converter and fixture loader should reject a MemBench-derived fixture when
either of these adapter-visible surfaces leaks scorer-only material:

- Experience text leakage: `Experience.payload.text` includes source label
  renderings such as `rel=...`, `attr=...`, `value=...`, qrels, target step
  IDs, answer keys, or other text that was not part of the externally observed
  message.
- Adapter-view structure leakage: any adapter-visible key or structured field
  is named `rel`, `attr`, `value`, `answer`, `ground_truth`, `choices`,
  `target_step_id`, `qid`, `memory_index`, `mode`, `gold`, `relevant`,
  `must_not`, `expected`, `stale`, `conflict`, or a fixture family label.

It should also reject a fixture when:

- adapter-visible IDs encode source category, answer, fixture family, mode, or
  expected behavior;
- in original MemBench trajectory mode, `target_step_id` cannot be mapped to
  exactly known source messages;
- target supports occur after the request checkpoint;
- answer choices are visible to `retrieve()` in the primary scoring mode;
- a reflective example's gold support set is not necessary and sufficient for
  the expected memory artifact or support-grounded retrieval target;
- an update-like or contradiction-like example cannot be mapped to explicit
  active/stale support, a `supersede` or `update` operation, and a query time
  after mutation effective time;
- the source data has duplicate message IDs that would collapse distinct
  experiences without source-locator disambiguation;
- category names or source file names appear in adapter-visible metadata;
- source audit status is unresolved, `blocked`, or incompatible with the
  intended commit/local-only use.

## Artifact And Hash Requirements

MemBench-derived runs should preserve all current memory_eval hash behavior.

Required fixture/artifact fields:

- `fixture_public_hash`: adapter-visible fixture view only;
- `fixture_gold_hash`: qrels, support sets, answer metadata, source benchmark
  metadata, and private labels;
- `fixture_full_hash`: full source fixture identity;
- `request_hash`: stripped adapter-visible query only, excluding scorer-only
  `mode`, scorer IDs, qrels, choices, answer metadata, and source benchmark
  labels;
- `operation_prefix_hash`: public ingest/mutate prefix before request;
- `retrieval_result_hash`: returned evidence order, support IDs, abstention,
  visible dropped records, visible provenance-derived IDs, and stable usage
  methodology labels;
- `deterministic_result_hash`: volatile fields stripped;
- `volatile_run_hash` and `volatile_usage_hash`: run identity and measured
  usage only.

Additional MemBench-specific hashes:

- upstream repository commit hash;
- raw source file SHA-256;
- conversion manifest hash;
- selected trajectory manifest hash;
- converter version hash;
- optional source audit artifact hash.

No adapter call should receive:

- `fixture_gold_hash`;
- `fixture_full_hash`;
- raw source file path;
- category or fixture family labels;
- real `scoring_profile_id`;
- answer keys or target step IDs.

## Reproducibility Requirements

The implementation phase should be reproducible without live network access:

- download or locate MemBench source data outside test execution;
- pin the exact upstream commit and raw file hashes;
- store only a conversion manifest and reviewed fixture outputs in repo, if
  license permits;
- use deterministic sampling with explicit seeds;
- sort source paths, categories, trajectories, and support IDs before hashing
  unless order is semantically part of the fixture;
- normalize times to RFC3339 when parseable and preserve raw time only in
  scorer metadata or sanitized public payload text;
- record skipped examples so future reruns explain why the fixture count did
  not change.
- prepare Hugging Face MTEB source dirs with the optional
  `prepare-hf-mteb-qrels` command only after choosing a pinned dataset
  revision; the command prepares local raw source files plus a source manifest,
  not committed fixtures or legal permission to commit fixtures.

## Risks

| Risk | Mitigation |
| --- | --- |
| License or redistribution ambiguity | Treat as a hard blocker before committing derived fixtures; classify redistribution as `commit_allowed`, `private_only`, or `blocked` and require explicit `redistribution_review` approval for generated fixtures only. |
| Synthetic data quality | Start with manually reviewed small packs; document skipped examples and known artifacts. |
| Public benchmark leakage | Do not claim MemBench leaderboard comparability; keep held-out mew splits for regression. |
| Answer-model contamination | Keep answer artifacts secondary and exclude them from primary `memory_eval` scores. |
| Metadata leakage from `rel` / `attr` / `value` | Strip label-like fields from adapter view and add converter-specific leak checks. |
| Category ambiguity | Keep category labels scorer-only and manually review reflective examples. |
| Stale/update semantics mismatch | Use only discovery-based update-like examples that map cleanly to `update` or `supersede`; otherwise defer. |
| Duplicate message IDs or nested target IDs | Use source locators, not raw `mid` or `sid` alone, as the conversion source of truth. |
| Noise generation nondeterminism | Prefer already materialized sampled data with hashes, or pin generator seed and manifest. |
| PII-like synthetic strings | Sanitize or exclude examples with phone/email/address content if repository policy requires it. |
| Raw-history reward | Keep budgets and support-scoring gates so dumping all history is penalized. |
| Scope leakage | Use synthetic scopes and run existing cross-scope exposure gates on MemBench fixtures. |

## Review Checklist

Reviewers should verify:

- The design keeps MemBench official answer accuracy out of primary
  `memory_eval` scoring.
- License and redistribution status are explicit, separately reviewing code
  and data licenses, with `commit_allowed` gated by complete
  `redistribution_review` metadata for generated fixtures only.
- Converter tests cover integer target IDs, multiple target IDs, high-level
  pair-like IDs, nested first-agent sessions, noise relocation, ambiguous
  rejection, duplicate source locator disambiguation, missing-message qrels,
  answer choices absent from adapter input, and scorer-only fields absent from
  `adapter_view`.
- Experience payload text and adapter-visible request/fixture structure are
  checked separately for leakage of `rel`, `attr`, `value`, answers, choices,
  ground truth, qrels, target IDs, category names, mode labels, and source
  paths.
- Adapter-visible experience text is not synthesized from private labels.
- `QA.target_step_id` maps only to scorer-only support IDs.
- Nested first-agent and reflective target IDs are mapped through source
  locators, not guessed from raw numeric position alone.
- Multiple-support examples have explicit support coverage policy, and
  `support_coverage_policy` is either implemented in the scorer or kept as
  scorer-only metadata.
- Reflective examples are excluded from the first deterministic pack unless
  manually verified for necessary and sufficient support.
- Update-like examples are discovered from pinned sources and deferred unless
  old/fresh support maps cleanly to `update` or `supersede`.
- Retrieval scoring stays support-ID based before context or answer artifacts.
- `answer_artifact_gold` is omitted from first generated fixtures, or later
  leakage-tested before inclusion.
- Optional multiple-choice answer artifacts are secondary and hash all model
  or exact-answer inputs.
- Source locator details are hidden from `adapter_view` and raw source
  locators appear only in scorer-only or debug-only artifacts.
- `memory_behavior_bridge` is the only place where official-loop style
  external outcome can be linked, and official-loop outcomes are excluded from
  primary `memory_eval` score, metrics, and gates.
- Public/gold/full hashes and deterministic result hashes follow existing
  P0/P1 behavior.
- Fixture generation is blocked until license, source hashes, and conversion
  manifest are reviewed.
- First fixture pack acceptance requires reviewed dry-run output, exact qrel
  mapping, request-prefix support validity, clean adapter view, gold-only hash
  sensitivity for scorer-only data, reference adapter pass, broken adapter
  expected failures, and manual support-sufficiency review.
- No implementation files, committed fixtures, or P0/P1 harness files are
  required for this design-doc task.

## Implementation-Phase Recommendation

Approve a separate implementation phase only after design review. The first
implementation should be a converter dry run and validator, not a large fixture
drop.

Recommended first implementation target:

1. Add a MemBench source-audit and converter-dry-run command that reads a
   local MemBench checkout or data directory and writes only dry-run artifacts.
2. Add converter leak checks for MemBench-specific private fields.
3. Produce a reviewed conversion manifest with pinned source hashes.
4. Run the dry-run conversion through `ReferenceP1Adapter` and the existing
   broken adapters to prove scorer behavior before exercising the real memory
   subsystem.
5. Run the same dry-run fixture set through `TypedCardsMemoryEvalAdapter` in
   deterministic replay mode as the first real mew memory-core validation
   target.
6. In a later PR, generate a tiny P2 fixture pack from manually selected
   examples after source audit and redistribution gates are satisfied.

Do not wire in the official MemBench answer loop until deterministic support
retrieval and context artifact scoring are stable.
