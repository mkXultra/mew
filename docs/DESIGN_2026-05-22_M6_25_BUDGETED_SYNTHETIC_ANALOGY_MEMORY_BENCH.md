# Design 2026-05-22 - M6.25 Budgeted Synthetic Analogy Memory Bench

Status: reviewed design document only. No implementation authorization.

Scope: define a budgeted synthetic analogy / relation-induction benchmark for
mew `memory_eval` P3/P4 planning. The document is schema-draft-ready design
guidance, but it does not authorize fixture generation, tests, implementation
files, or committed harness changes.

The benchmark asks whether a memory system provides usable local semantic
representations under budget constraints. It uses synthetic local worlds and
word analogy / relation induction tasks so parametric model knowledge cannot
solve the tasks. Exact answer scoring must be possible without LLM judges.
Evidence IDs do not have to be the primary score, but hidden world graph,
relation, rule, and support IDs must exist for validation, fixture generation,
oracle construction, and failure analysis.

## Problem

P0/P1 memory retrieval fixtures can show whether a memory adapter returns the
right evidence IDs. They do not fully show whether memory has distilled a long
experience history into compact, reusable semantic structure that helps later
reasoning under budgets.

The core benchmark question is:

```text
Given only synthetic local experience, can the memory system preserve currently
valid relations, rules, updates, and scope constraints well enough that a fixed
solver can answer novel analogy or relation-induction questions within a fixed
budget?
```

A weak raw-evidence memory may solve some tasks by repeated retrieval and
solver turns over many snippets. A stronger memory should reduce turns, memory
calls, context tokens, and latency through better derived or structured memory
artifacts: typed summaries, relation claims, rule claims, stale/update markers,
support links, and scoped compact world-state projections.

## Long-term memory interpretation

This is not short-context analogy solving. It becomes a long-term memory
benchmark only across horizon profiles: increasing history length, session
count, elapsed time, distractor ratio, update/forget/supersede count, scope
count, and compaction pressure.

```text
As synthetic experience history grows and becomes stale, noisy, scoped,
updated, and budget-constrained, can the memory system preserve the currently
valid local semantic structure and expose it as a compact, supported memory
artifact?
```

Reports must group by horizon profile and include retention/degradation curves,
not only single-fixture accuracy.

## Non-goals

- Do not evaluate general model intelligence or world knowledge.
- Do not rely on LLM judges for primary answer correctness.
- Do not make `memory_eval` own full agent behavior or external task success.
- Do not require graph memory, vector search, typed-card storage, or mew-specific
  memory subsystem internals.
- Do not generate actual fixtures yet.
- Do not make raw transcript replay and derived memory quality look equivalent.
- Do not expose hidden gold, hidden IDs, trap labels, or answer keys to adapters
  or solver prompts.

## Boundary

| Layer | Owns | Does not own |
| --- | --- | --- |
| `memory_eval` core | P3-S memory artifact generation and deterministic artifact scoring. | Full agent behavior and external task success. |
| `synthetic_solver_probe` | Fixed solver consumption of frozen memory artifacts, exact answer scoring, budgeted utility diagnostics, and links to P3-S artifact hashes. | External behavior benchmark success, open-ended planning, arbitrary tool use, production agent runtime integration. |
| `memory_behavior_bridge` | Optional future linkage between memory artifacts and external behavior_eval runs. | Source-of-record behavior scoring. |

The benchmark has two internal tracks:

- P3-S rows evaluate memory artifacts directly: support coverage, pollution,
  freshness, scope isolation, compression, retention, and reproducibility.
- P4-S rows evaluate a frozen fixed-solver probe over already-built artifacts or
  oracle packets. P4-S is not a general behavior benchmark.

Future P4-B may connect memory artifacts to external behavior benchmarks, but
source-of-record task success remains outside this benchmark.

## Relationship To Prior P-Tier Naming

The existing memory eval plan used P3 for future model-judged support and
faithfulness. This benchmark keeps the user-facing P3/P4 split but makes the
synthetic deterministic tracks explicit:

- `P3-S`: synthetic memory artifact evaluation in `memory_eval` core. It uses
  hidden world graphs, normalized public claim payloads, support IDs, and exact
  scorer logic. It does not require an LLM judge.
- `P3-J`: future model-judged support/faithfulness evaluation for free-form
  memory artifacts. It is out of scope here.
- `P4-S` or `P4 synthetic solver probe`: benchmark-internal fixed-solver
  evaluation. The solver consumes frozen memory artifacts or oracle packets
  under strict budgets and produces exact normalized answers. This is not a
  general `behavior_eval` or terminal-bench task.
- `P4-B` or `external memory-behavior bridge`: optional future linkage to
  external behavior benchmarks. Source-of-record task success remains outside
  this benchmark.

Artifacts should include `p3_track: synthetic_deterministic` and
`p4_track: synthetic_solver_probe` where applicable.

## Benchmark Families And Classification

| Family | Example task shape | Primary phase | Secondary phase | Main question |
| --- | --- | --- | --- | --- |
| `relation_lookup` | In local world W, what is `glim` related to by relation `nava`? | P3-S | P4-S | Did memory retain scoped relation facts without distractors? |
| `analogy_completion` | `a : b :: c : ?` under an invented relation or rule. | P4-S | P3-S | Does memory expose enough structure for exact analogy solving? |
| `rule_induction` | Infer a local transformation rule from examples, then apply it to a held-out token. | P4-S | P3-S | Can derived memory compress reusable rules instead of replaying all examples? |
| `multi_hop_relation` | Follow two or three typed edges with temporal/scope filters. | P3-S | P4-S | Does memory support bounded chain expansion and stale filtering? |
| `update_supersede` | Earlier evidence says `dax -> mip`; later evidence supersedes it to `dax -> tovo`. | P3-S | P4-S | Does memory answer with the currently valid relation? |
| `scope_isolated_analogy` | Two scopes reuse invented tokens with different relation meanings. | P3-S | P4-S | Does memory isolate local worlds under reasoning pressure? |
| `ambiguous_or_noisy_support` | Evidence contains conflicts, hedges, partial observations, and distractors. | P3-S | P4-S | Does memory mark insufficiency or conflict rather than overclaim? |
| `budget_gradient` | Same hidden world under tight, medium, and loose budgets. | P3-S/P4-S | none | Does better memory reduce calls, context, turns, and latency? |

## Conditions

`memory_condition` is separate from fixture family and stressor tags.

Allowed `memory_condition` values:

| `memory_condition` | Adapter setup | Solver/probe input | Purpose |
| --- | --- | --- | --- |
| `memory_off` | No prior experiences ingested, or retrieval disabled. | Task prompt only. | Measures parametric/model guessing floor. |
| `raw_evidence_memory` | Public experiences ingested; adapter may retrieve raw evidence only. | Frozen raw evidence artifact. | Baseline for replay-heavy memory. |
| `compressed_or_derived_memory` | Same public experiences; adapter may emit summaries, cards, structured claims, or compact relation/rule artifacts. | Frozen derived artifact. | Tests whether structure improves budget efficiency. |
| `oracle_support_only` | Scorer supplies minimal valid world-state support. | Oracle support packet. | Upper bound for artifact usefulness without direct answer leakage. |
| `oracle_answer_packet` | Scorer supplies a packet that includes direct answer. | Debug-only oracle answer packet. | Debug upper bound only; excluded from normal aggregates. |

Fixture families and `stressor_tags` describe what is being stressed. They are
not memory conditions. Examples:

```text
stale_or_conflict
cross_scope_distractor
update_supersede
ambiguous_or_noisy_support
budget_gradient
multi_hop_relation
```

Artifact and aggregate rows should preserve this split:

```json
{
  "memory_condition": "compressed_or_derived_memory",
  "fixture_family": "scope_isolated_analogy",
  "stressor_tags": ["cross_scope_distractor", "budget_gradient"]
}
```

Stale, update, conflict, cross-scope, ambiguity, multi-hop, and budget-gradient
behavior may be scored by exact metrics and canonical failure types, but they
must appear as `fixture_family` / `stressor_tags`, not as `memory_condition`
rows.

Public setup operations may declare allowed derived artifacts, summaries, cards,
or adapter capabilities. They must not reveal gold-derived summaries, hidden
relation IDs, hidden rule IDs, fixture family labels, trap labels, required
support labels, answer keys, materialization targets, or whether a request is
stale-, scope-, ambiguity-, or update-focused.

For the first P3-S prototype, `raw_evidence_memory` and
`compressed_or_derived_memory` ingest the same public experiences. The condition
may change artifact budget and adapter-declared capabilities, but should not add
semantic setup data unless explicitly reviewed.

For direct raw-vs-derived comparisons, artifact build budgets must be paired and
identical unless the row is explicitly part of `budget_gradient`.

Allowed to differ:

- adapter-declared capability mode;
- artifact kind;
- whether structured claims are emitted.

Not allowed to differ in paired comparison:

- `max_artifact_build_memory_calls`;
- `max_artifact_build_context_tokens`;
- `max_artifact_build_evidence_items`;
- solver turn/context/output budget.

`raw_evidence_memory` obeys the same context-token, item, and call budgets as
other non-oracle conditions. If raw replay uses more context than the derived
condition, reports must show this explicitly and must not compare only answer
accuracy.

### Oracle packet levels

- `oracle_support_only`: minimal valid facts, rules, constraints, freshness,
  and scope information. It has no final answer unless the final answer is
  itself a valid world-state fact being tested.
- `oracle_answer_packet`: includes the direct answer. It is a debugging upper
  bound only and must not be mixed with `oracle_support_only` in aggregate
  reports.

Initial implementation should use `oracle_support_only` for oracle condition
rows.

For `oracle_support_only` and `oracle_answer_packet`, `memory_calls_to_answer`
defaults to 0 because no memory adapter retrieval/build operation is performed.
If oracle packet construction cost is reported, it must be reported separately
as oracle construction diagnostics and excluded from memory adapter efficiency
comparisons.

## Fixed Solver Budget Profile

P4-S synthetic solver probe rows must fix the solver and all budget knobs before
scoring. Frozen P4-S permits zero solver-time memory calls.

```json
{
  "solver_profile_id": "budgeted_synthetic_analogy_solver.v1",
  "model": "fixed model id, exact provider revision if available",
  "prompt_template_hash": "sha256:...",
  "temperature": 0,
  "top_p": 1,
  "seed": 1729,
  "decoding": {
    "max_output_tokens": 128,
    "stop_sequences": []
  },
  "artifact_build_budget_profile": {
    "max_artifact_build_memory_calls": 2,
    "max_artifact_build_context_tokens": 600,
    "max_artifact_build_evidence_items": 4
  },
  "turn_budget": {
    "max_solver_turns": 3,
    "max_solver_memory_calls": 0,
    "max_context_tokens_total": 1200,
    "max_context_tokens_per_solver_turn": 600,
    "timeout_ms": 30000
  },
  "answer_format": {
    "type": "exact_json",
    "schema": {
      "answer": "string | string[] | null",
      "abstain": "boolean"
    }
  },
  "memory_off_controls": {
    "max_memory_off_accuracy": 0.2,
    "on_exceed": "retire_bucket | diagnostic_only | regenerate_fixture",
    "min_bucket_size_for_retirement": 20
  }
}
```

P3-S retrieval/build operations are accounted for by
`artifact_build_budget_profile` and artifact `deterministic_usage`. P4-S runs
that exceed solver turns, solver context tokens, output tokens, timeout, or
`max_solver_memory_calls=0` fail the solver budget. P3-S artifact builds that
exceed artifact-build calls/items/context budgets fail before P4-S.

Only later P4-I may introduce interactive solver memory calls, after separate
profile, schema, leakage, and boundary review.

## Answer normalization rules

P4-S answer scoring uses exact normalized JSON:

- Solver output must conform to the declared exact JSON schema.
- `abstain=true` with a non-null answer is invalid unless explicitly allowed by
  the scoring profile.
- `abstain=false` with `answer=null`, an empty string, or an empty array is
  invalid.
- String answers are normalized to Unicode NFC before comparison.
- Case folding is applied only if the generator declares case-insensitive public
  tokens.
- Arrays are sets unless the request declares ordered answers.
- Duplicate values are removed for unordered sets and are a formatting failure
  if the scoring profile requires canonical arrays.
- Answers must use public surface tokens only.
- Hidden node IDs, relation IDs, rule IDs, support fact IDs, or answer-key
  handles in solver output are leakage failures.

## Synthetic World Generation

The generator creates local synthetic worlds that cannot be solved by
parametric knowledge.

Rules:

- Use invented tokens for entities, relations, attributes, classes, rules, and
  scopes. Tokens must not map to common words, real names, code APIs, brands, or
  geography.
- Include relation facts, rule examples, distractors, multi-hop relations,
  updates, supersedes, forget/delete operations, scope boundaries, temporal
  constraints, and ambiguous/noisy evidence.
- Include near-miss distractors with wrong relation direction, old validity,
  wrong scope, similar token spelling, or wrong relation type.
- Include anti-grep and anti-parametric-knowledge controls: regenerate token
  sets per seed, keep held-out seeds private, rotate templates, avoid answer
  tokens uniquely appearing in queries, and include memory-off baselines.
- Use `must_abstain=true` for insufficient or ambiguous worlds where no unique
  answer follows from public support.
- Keep hidden rule bodies, hidden relation IDs, hidden support labels, fixture
  family labels, and answer keys out of public adapter-visible inputs.

The hidden world graph should include nodes, relation edges, rule definitions,
validity windows, scope, support facts, supersedes/contradicts/forgets edges,
and answer-key derivations.

## Fixture And Gold Structure

Fixtures have public adapter-visible data, scorer/artifact-visible metadata,
and scorer-only gold.

Scorer/artifact-visible `horizon_profile` metadata:

```json
{
  "horizon_profile": {
    "history_item_count": 1000,
    "session_count": 20,
    "elapsed_days": 60,
    "distractor_ratio": 5.0,
    "scope_count": 4,
    "update_count": 8,
    "supersede_count": 3,
    "forget_count": 2,
    "ambiguous_evidence_rate": 0.15,
    "compaction_required": true,
    "raw_replay_budget_ratio": 0.05
  }
}
```

Aggregate `group_by` keys:

```text
fixture_family
memory_condition
stressor_tags
horizon_bucket
history_item_count_bucket
session_count_bucket
elapsed_days_bucket
distractor_ratio_bucket
update_count_bucket
compaction_required
```

### Public Adapter-Visible View

```json
{
  "schema_version": "memory_eval_synthetic_world_public.v1",
  "fixture_public_id": "opaque_fx_000123",
  "public_generation_id": "opaque_pubgen_44121",
  "scopes": [
    {
      "scope_id": "scope_a",
      "visibility": {"allowed_scope_ids": ["scope_a"]}
    }
  ],
  "experiences": [
    {
      "experience_id": "exp_001",
      "scope_id": "scope_a",
      "event_time": "2026-01-10T10:00:00Z",
      "ingest_order": 1,
      "payload": {
        "mime_type": "text/plain",
        "text": "In the zafik notes, lomep holds nava toward brisol."
      },
      "visibility": {"retrievable": true}
    }
  ],
  "operations": [
    {
      "op_id": "op_004",
      "type": "supersede",
      "target_experience_ids": ["exp_002"],
      "replacement_experience_id": "exp_009",
      "effective_time": "2026-01-15T00:00:00Z"
    }
  ],
  "requests": [
    {
      "request_id": "rq_001",
      "scope_id": "scope_a",
      "query_time": "2026-01-20T00:00:00Z",
      "query_text": "In zafik, lomep : brisol :: darven : ?",
      "budget": {
        "max_evidence_items": 4,
        "max_context_tokens": 600,
        "max_artifact_build_memory_calls": 2
      }
    }
  ]
}
```

The public view may include relation-looking text because that is what memory
must ingest. It must not include hidden relation IDs, hidden rule IDs, hidden
support fact IDs, answer keys, fixture family labels, trap labels, required
support labels, or expected answers.

`public_generation_id` is opaque and must not be the generator seed for hidden
token tables, graphs, answers, family, or traps. The true generator seed belongs
only in scorer/gold view and contributes to `fixture_gold_hash`, not
`fixture_public_hash` or adapter-visible inputs. If a legacy fixture contains a
public seed-like field, treat it only as an opaque public generation identifier
and prefer `public_generation_id` going forward.

If a legacy public field is named `max_memory_calls`, the scoring profile must
interpret it as a P3-S artifact-build budget or reject the fixture as ambiguous.
It is never a solver-time memory-call budget for frozen P4-S.

### Scorer-Only Gold View

```json
{
  "schema_version": "memory_eval_synthetic_world_gold.v1",
  "fixture_id": "synthetic_analogy_000123",
  "generator": {
    "generator_id": "synthetic_world_generator.v1",
    "generator_version": "git-or-package-id",
    "seed": 981772
  },
  "hidden_world_graph": {
    "world_graph_id": "wg_000123",
    "nodes": [
      {"node_id": "ent_lomep", "kind": "entity", "scope_id": "scope_a"}
    ],
    "relations": [
      {
        "relation_id": "rel_017",
        "relation_type_id": "rtype_nava_scope_a",
        "source_node_id": "ent_lomep",
        "target_node_id": "ent_brisol",
        "valid_from": "2026-01-10T00:00:00Z",
        "valid_until": null,
        "support_fact_ids": ["sf_001"]
      }
    ],
    "rules": [
      {
        "rule_id": "rule_003",
        "rule_kind": "analogy_mapping",
        "scope_id": "scope_a",
        "rule_body": {
          "body_schema": "synthetic_rule_body.v1",
          "mapping_pairs": [
            {"from_node_id": "ent_lomep", "to_node_id": "ent_brisol"},
            {"from_node_id": "ent_darven", "to_node_id": "ent_tavik"}
          ],
          "constraints": {
            "same_scope_required": true,
            "exclude_superseded": true
          }
        },
        "support_fact_ids": ["sf_001", "sf_002", "sf_003"]
      }
    ],
    "support_facts": [
      {
        "support_fact_id": "sf_001",
        "experience_id": "exp_001",
        "span_ref": "span_001",
        "role": "premise"
      }
    ]
  },
  "answer_key": [
    {
      "request_id": "rq_001",
      "answer": ["tavik"],
      "answer_node_ids": ["ent_tavik"],
      "required_relation_ids": ["rel_017", "rel_021"],
      "required_rule_ids": ["rule_003"],
      "required_support_fact_ids": ["sf_001", "sf_002"],
      "forbidden_support_fact_ids": ["sf_009"],
      "must_abstain": false
    }
  ]
}
```

Hidden `world_graph`, relation IDs, rule IDs, `rule_body`, support fact IDs, and
answer keys live only in scorer/gold view.

## Memory Artifact Schema

P3-S artifacts can be raw evidence packets, context packets, or derived
world-state artifacts.

```json
{
  "schema_version": "memory_eval_synthetic_artifact.v1",
  "artifact_id": "ma_000123_rq_001",
  "memory_condition": "compressed_or_derived_memory",
  "fixture_family": "scope_isolated_analogy",
  "stressor_tags": ["cross_scope_distractor", "budget_gradient"],
  "request_id": "rq_001",
  "operation_prefix_hash": "sha256:...",
  "adapter_request_hash": "sha256:...",
  "claim_scoring_applicability": {
    "structured_claims_required": false,
    "structured_claims_present": true,
    "evidence_level_support_scoring": true,
    "free_text_summary_diagnostic_only": true
  },
  "memory_output": {
    "kind": "retrieval_result | context_packet | derived_world_state",
    "items": [
      {
        "item_id": "adapter_item_01",
        "public_evidence_ids": ["exp_001", "exp_002"],
        "summary": "Within scope_a, nava maps lomep to brisol and darven to tavik.",
        "structured_claims": [
          {
            "claim_id": "claim_01",
            "claim_kind": "relation_fact",
            "scope_id": "scope_a",
            "valid_at": "2026-01-20T00:00:00Z",
            "relation_fact": {
              "relation_surface": "nava",
              "source_surface": "lomep",
              "target_surface": "brisol",
              "direction": "forward"
            },
            "support_public_ids": ["exp_001"]
          },
          {
            "claim_id": "claim_02",
            "claim_kind": "rule",
            "scope_id": "scope_a",
            "valid_at": "2026-01-20T00:00:00Z",
            "rule": {
              "rule_kind": "analogy_mapping",
              "public_relation_tokens": ["nava"],
              "constraints": {"same_scope_required": true}
            },
            "support_public_ids": ["exp_001", "exp_002", "exp_003"]
          }
        ],
        "rank": 1,
        "tokens": 42
      }
    ],
    "abstention": {"abstained": false, "reason": null}
  },
  "deterministic_usage": {
    "memory_calls": 1,
    "context_tokens": 148,
    "retrieved_item_count": 1,
    "structured_claim_count": 2
  },
  "environmental_usage": {
    "latency_ms": 23.4,
    "latency_source": "wall_clock",
    "cost_estimate": null
  },
  "memory_artifact_hash": "sha256:..."
}
```

Structured claims are required only for P3-S structured-claim scoring. Adapters
that do not emit normalized structured claims are not automatically failed.
Instead:

- `structured_claim_score`: `not_applicable`.
- `evidence_level_support_score`: applicable if public evidence/support IDs are
  returned.
- `frozen_solver_probe`: applicable if artifact can be consumed by fixed solver.
- `free_text_summary_quality`: diagnostic only unless judged profile enabled.

A scoring profile must declare whether structured claims are required,
optional, or not applicable. Free-text summaries are diagnostic/report-only for
deterministic P3-S unless a judged profile is explicitly enabled.

`support_public_ids` are generated public `Experience.experience_id` values,
not hidden support fact IDs or raw source locators. Initial schemas may use
`support_public_ids`; span-level scoring may later extend this to
`support_public_refs`:

```json
{
  "support_public_refs": [
    {
      "experience_id": "exp_001",
      "span_ref": "span_001"
    }
  ]
}
```

## P3-S canonical failure types

| Failure type | Meaning |
| --- | --- |
| `structured_claim_overclaim` | Structured claim asserts relation/rule/update semantics stronger than public support/gold allows. |
| `unsupported_structured_claim` | Normalized claim has no support IDs or support IDs do not support it. |
| `insufficient_support_ids` | Answer or claim may be correct but misses required support IDs for artifact validation. |
| `ambiguous_public_claim` | Public payload could map to multiple hidden candidates and is not disambiguated by support/constraints. |
| `wrong_scope_claim` | Claim uses support or semantics from another scope. |
| `stale_claim_as_active` | Superseded/expired claim is presented as current. |
| `forgotten_claim_used` | Support that should be forgotten/deleted is used. |
| `forbidden_support_claim` | Artifact uses support explicitly forbidden by gold. |
| `hidden_id_leakage` | Hidden relation/rule/support IDs appear in adapter-visible artifact. |
| `answer_key_leakage` | Final answer or answer key appears in adapter-visible setup/prompt where it should not. |
| `oracle_answer_leak` | `oracle_answer_packet` content is mixed into support-only or non-oracle conditions. |
| `artifact_budget_violation` | Artifact exceeds item/token/claim budget. |
| `raw_replay_budget_violation` | `raw_evidence_memory` exceeds configured raw replay, item, call, or context budget, regardless of whether the answer is correct. |
| `solver_budget_failure` | P4-S solver exceeds turns/output/context/time budget. |
| `seed_nondeterminism` | Generated fixture or run cannot be reproduced from declared non-secret seeds/hashes. |
| `memory_off_too_high` | Memory-off accuracy exceeds scoring profile threshold. |

`answer_key_leakage` applies only when the answer appears because scorer-only
gold, `oracle_answer_packet`, hidden answer keys, or debug metadata leaked into
adapter-visible inputs, memory artifacts, or solver prompts.

A memory artifact may contain the final public answer token if it was derived
from public experiences under the evaluated `memory_condition` and is supported
by valid public evidence. In that case, score it through support coverage and
pollution metrics, not as leakage.

## Hash And Reproducibility Rules

| Hash | Includes | Excludes |
| --- | --- | --- |
| `fixture_public_hash` | Adapter-visible scopes, experiences, operations, requests, public budgets. | Hidden graph, answer key, support labels, fixture family/trap labels. |
| `fixture_gold_hash` | Hidden world graph, rule IDs, relation IDs, rule bodies, support facts, answer key, true generator seed. | Adapter outputs and solver outputs. |
| `operation_prefix_hash` | Public fixture hash plus public setup/ingest/mutation operation inputs before request. | Operation receipts, hidden gold, current query. |
| `adapter_request_hash` | Adapter-visible query text, scope, query time, valid-at filters, public budget, deterministic opaque request ID if included. | `memory_condition`, fixture family, difficulty bucket, trap labels, expected answer, relevant IDs, hidden graph fields. |
| `scorer_request_hash` | `adapter_request_hash` plus scorer/artifact-visible `memory_condition`, fixture family, stressor tags, difficulty bucket, horizon bucket, scoring metadata. | Hidden answer key unless explicitly part of scorer/gold hash. |
| `memory_artifact_hash` | Canonical memory output, ordering, redactions, structured claims, `adapter_request_hash`, deterministic usage fields. | Solver answer, latency, cost, wall-clock timestamps, provider environment fields, `scorer_request_hash`. |
| `solver_profile_hash` | Model, prompt, decoding, seed, turn/context/time budgets, answer schema. | Fixture gold. |
| `scoring_profile_hash` | Metric definitions, thresholds, aggregation rules. | Adapter internals. |

Run artifacts and aggregate artifacts include `scorer_request_hash`. Adapter
artifacts include `adapter_request_hash` and must not learn scorer-only request
metadata through hash names or payloads.

Canonicalization uses sorted JSON keys, UTF-8, normalized datetimes, stable
array ordering where order is semantic, and deterministic decimal formatting for
scores that affect artifact identity. Latency and cost are environmental usage
and excluded from `memory_artifact_hash`.

## Exact Scoring And Aggregation

Primary answer scoring is exact and judge-free.

In metric formulas, `condition` means `memory_condition`; fixture families and
stressor tags are independent grouping dimensions.

| Metric | Definition | Layer |
| --- | --- | --- |
| `accuracy_at_budget` | 1 if exact normalized answer set matches gold before budgets expire; abstention must match `must_abstain`. | P4-S |
| `turns_to_answer` | Solver turns before first exact valid answer. | P4-S |
| `memory_calls_to_answer` | P3-S retrieval/build operations already accounted for by the frozen artifact; not solver-time calls. | P4-S/P3-S |
| `context_tokens_to_answer` | Frozen artifact/oracle context tokens consumed before exact answer. | P4-S |
| `latency_to_answer_ms` | Replayed or measured artifact plus solver latency, with source recorded. | Diagnostic |
| `accuracy_oracle_gap` | `accuracy_at_budget(oracle_support_only) - accuracy_at_budget(condition)`. | P4-S |
| `turns_oracle_gap` | `turns_to_answer(condition) - turns_to_answer(oracle_support_only)`. | P4-S |
| `memory_calls_oracle_gap` | `memory_calls_to_answer(condition) - memory_calls_to_answer(oracle_support_only)`. | P4-S |
| `context_tokens_oracle_gap` | `context_tokens_to_answer(condition) - context_tokens_to_answer(oracle_support_only)`. | P4-S |
| `accuracy_memory_off_delta` | `accuracy_at_budget(condition) - accuracy_at_budget(memory_off)`. | P4-S |
| `context_tokens_memory_off_delta` | `context_tokens_to_answer(memory_off) - context_tokens_to_answer(condition)`. | P4-S |
| `artifact_support_recall` | Required support fact/relation/rule IDs represented by public evidence or structured claims. | P3-S |
| `artifact_pollution_rate` | Stale, wrong-scope, forbidden, forgotten, or irrelevant support divided by support-mappable returned support. | P3-S |
| `stale_update_success` | 1 if current valid relation/rule is used and superseded support is excluded or marked stale. | P3-S/P4-S |
| `scope_isolation_under_reasoning` | 1 if wrong-scope support does not affect artifact or answer. | P3-S/P4-S |

For memory efficiency metrics, `context_tokens_to_answer` should be split into:

- `task_prompt_tokens`;
- `memory_artifact_tokens`;
- `solver_output_tokens`.

`context_tokens_memory_off_delta` must specify whether it compares total solver
context tokens or memory-artifact-only tokens. The default should report both
when available.

`budget_efficiency_family` includes:

```text
success_at_budget
turns_to_answer
memory_calls_to_answer
context_tokens_to_answer
latency_to_answer_ms
accuracy_oracle_gap
turns_oracle_gap
memory_calls_oracle_gap
context_tokens_oracle_gap
accuracy_memory_off_delta
context_tokens_memory_off_delta
```

Do not collapse `budget_efficiency_family` into one leaderboard score.

### Retention and degradation curves

```text
artifact_quality(h) = artifact_support_recall(h) * (1 - artifact_pollution_rate(h)) * stale_update_success(h) * scope_isolation_under_reasoning(h)

retention_auc = area_under_curve(artifact_quality over ordered horizon buckets)
```

Each factor must declare applicability. If a factor is not applicable for a
fixture family, it is excluded from the product for that fixture and the
artifact must record `metric_applicability`. Do not silently treat
non-applicable factors as pass unless the scoring profile explicitly declares
neutral defaults.

```json
{
  "metric_applicability": {
    "stale_update_success": false,
    "scope_isolation_under_reasoning": true,
    "artifact_pollution_rate": true
  }
}
```

Horizon buckets can be history item count, session count, elapsed days,
update/forget pressure, distractor ratio, and compaction pressure.
`retention_auc` is diagnostic and must not hide hard failures.

### Forgetting-aware artifact score

```text
forgetting_aware_artifact_score = valid_current_support_recall * (1 - obsolete_support_usage_rate) * (1 - forgotten_support_usage_rate) * (1 - contradiction_as_current_rate)
```

Terms:

- `valid_current_support_recall`: fraction of required currently valid support
  facts/rules/relations covered by the artifact.
- `obsolete_support_usage_rate`: fraction of artifact support that is
  superseded, expired, or stale but presented as active.
- `forgotten_support_usage_rate`: fraction of artifact support that should be
  forgotten, deleted, tombstoned, or unavailable for use.
- `contradiction_as_current_rate`: fraction of contradicted claims/support
  presented as current rather than conflicted or insufficient.

Report `forgetting_aware_artifact_score` separately from raw answer accuracy.

### Compression efficiency

```text
support_per_1k_context_tokens = required_support_fact_ids_covered / max(1, context_tokens / 1000)

clean_support_per_1k_context_tokens = valid_required_support_fact_ids_covered / max(1, (context_tokens + pollution_tokens) / 1000)

compression_gain_over_raw = clean_support_per_1k_context_tokens(compressed_or_derived_memory) - clean_support_per_1k_context_tokens(raw_evidence_memory)
```

### P4 result memory-quality attribution

```json
{
  "memory_quality_attribution": {
    "status": "supported | unsupported | contradicted | inconclusive",
    "p3_artifact_hash": "sha256:...",
    "required_support_covered": true,
    "pollution_detected": false,
    "stale_or_forbidden_support_used": false,
    "memory_off_bucket_accuracy": 0.05,
    "oracle_support_only_success": true
  }
}
```

Correct P4-S answers without P3-S support coverage are solver successes, not
memory-quality successes.

## P4-S execution modes

Initial P4-S must use frozen-artifact mode:

- P3-S generates the artifact first.
- Solver receives a fixed artifact or oracle packet.
- Solver cannot call the memory adapter interactively.
- `memory_calls_to_answer` means P3-S retrieval/build operations already
  accounted for by the artifact.
- Solver output is exact normalized JSON.

Interactive memory calls are later `P4-I` and need separate profile, schema,
leakage, and boundary review.

## Anti-Grep And Anti-Parametric Controls

- Use invented token sets and private held-out generator seeds.
- Rotate paraphrase templates and relation grammars.
- Reject tokens that collide with common language, known benchmarks, APIs, real
  names, brands, or geography.
- Include distractors with surface overlap, wrong scope, stale validity, and
  wrong relation direction.
- Include `memory_off` rows for every P4-S bucket; retire, mark diagnostic, or
  regenerate buckets where memory-off accuracy exceeds profile threshold.
- Keep hidden IDs, trap labels, support labels, and answer keys out of adapter
  payloads and solver prompts.
- Add canaries for hidden ID leakage, answer key leakage, and oracle answer
  leakage.

## Difference From MemBench And LoCoMo-Style Recall

MemBench and LoCoMo-style memory benchmarks are useful for support-grounded
recall, conversational memory, temporal questions, and multi-session QA. This
benchmark is narrower and synthetic:

- It uses local invented worlds so parametric knowledge cannot solve tasks.
- It emphasizes relation induction and analogy transfer, not only recalling a
  support span.
- It treats turns, retrieval/build calls, context tokens, latency, memory-off
  deltas, oracle gaps, retention, forgetting, and compression as first-class
  outcomes.
- It separates raw evidence replay from compressed or derived memory artifacts.

Track relationship:

- Track A: synthetic deterministic memory-artifact scoring.
- Track B: naturalistic conversational memory diagnostics.
- Track C: agentic trajectory memory diagnostics.

Full task success remains owned by `behavior_eval` / terminal bench. Optional
future P4-B may link memory artifacts to external behavior runs, but this
benchmark does not own source-of-record external task success.

## Risks And Mitigations

| Risk | Failure mode | Mitigation |
| --- | --- | --- |
| Solver contamination | Solver learns fixture grammar or answer patterns. | Held-out seeds, fixed profile hashes, memory-off monitoring, no gold in prompts. |
| Benchmark becomes model reasoning eval | Memory-off performs nearly as well as memory-on. | `memory_off_controls`, bucket retirement, regenerate weak fixtures. |
| Overfitting synthetic grammar | Systems tune to generator quirks. | Multiple grammar families, private held-out sets, horizon slices. |
| Hidden leakage | Relation/rule/support IDs or answers leak into public view. | Public/gold split, leakage canaries, hash audits, reviewer checklist. |
| Unstable bridge scoring | Provider nondeterminism changes exact answers. | Temperature 0, fixed seed where available, exact JSON, variance diagnostic only. |
| Conflating answer success with memory quality | Solver guesses around bad memory. | P3-S support metrics, memory-quality attribution, memory-off/oracle gaps. |
| Raw replay wins by budget loophole | Raw evidence uses more context than derived artifacts. | Same non-oracle budgets, raw replay ratio, compression metrics. |
| Stale/forgotten support used | Obsolete support produces right answer accidentally. | Forgetting-aware score and canonical failure types. |
| Ambiguity penalizes honest abstention | Public evidence lacks a unique answer. | Manual ambiguity review and `must_abstain=true`. |

## Phased Rollout

### Phase A: Design review

- Review P3-S/P4-S/P4-B boundaries.
- Confirm no implementation or fixture generation is authorized.
- Confirm horizon profile and long-term-memory interpretation are accepted.

### Phase B: Schema-only draft

- Draft public/gold/artifact schemas.
- Draft hash canonicalization examples.
- Draft answer normalization and scoring profile schema.

### Phase C: Generator prototype outside acceptance

- Prototype a tiny private generator sample.
- Manually inspect leakage, answerability, and ambiguity.
- Do not commit generated fixtures yet.

### Phase D: Deterministic P3-S artifact scoring

- Score support recall, pollution, stale/forget handling, scope isolation,
  budget compliance, structured-claim applicability, and retention curves.

### Phase E: Frozen P4-S synthetic solver probe

- Use frozen-artifact mode only.
- Run `memory_off`, `raw_evidence_memory`, `compressed_or_derived_memory`, and
  `oracle_support_only`.
- Report exact accuracy and budget metric families with P3-S artifact hashes.

### Phase F: Held-out review gate

- Add private held-out seeds and grammar variants.
- Retire or regenerate buckets with high memory-off accuracy.
- Ambiguity fixtures require manual review before release: reviewer must
  confirm sufficient public support for unique answer, or `must_abstain=true`;
  otherwise the fixture cannot enter acceptance sets.
- Publish only after leakage, reproducibility, and hash review.

## Review Checklist

- Does the target design file exist at the exact path?
- Does the design separate `memory_eval`, `synthetic_solver_probe`, and
  `memory_behavior_bridge`?
- Are P3-S, P4-S, P4-B, and deferred P4-I clearly distinguished?
- Does frozen P4-S set `max_solver_memory_calls: 0` and separate
  artifact-build budgets?
- Are conditions defined without gold-hint setup operations?
- Are `oracle_support_only` and `oracle_answer_packet` separated?
- Are structured claims capability/applicability gated?
- Are hidden `world_graph`, relation IDs, rule IDs, support fact IDs, rule
  bodies, and answer keys scorer-only?
- Are `adapter_request_hash` and `scorer_request_hash` split?
- Is `public_generation_id` opaque and non-generative?
- Are exact answer normalization rules complete?
- Are retention AUC, forgetting-aware score, compression metrics, and
  `budget_efficiency_family` diagnostic families rather than one score?
- Are canonical failure types complete enough for debugging?
- Are anti-grep and anti-parametric controls present?
- Are ambiguity fixtures manually reviewed before acceptance?
