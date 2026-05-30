# Design 2026-05-22 - M6.25 Memory Subsystem Typed Cards Plan

Status: target architecture design. Phase A-C implementation slices now exist; this document remains the normative architecture reference and must not treat current code as automatically authoritative.

Scope: define the intended mew memory subsystem architecture after the generic memory eval harness direction, using typed memory cards plus provenance, graph/index, governance, and bounded recall/projection.

Primary stance: the current mew memory subsystem implementation and any dirty diffs are non-authoritative for this document. This document defines the target architecture and acceptance shape. It must not rubber-stamp existing code.

Source docs consulted:

- `docs/another/REGENERATED_2026-05-21_M6_25_AGENT_MEMORY_ARCHITECTURE.md`
- `DESIGN_2026-05-21_M6_25_MEMORY_EVAL_HARNESS_IMPLEMENTATION_PLAN.md`
- `DESIGN_2026-05-20_M6_25_MEMORY_CORE_AND_EVALUATION.md`
- `DESIGN_2026-05-20_M6_25_MEMORY_SYSTEM_TOOL_PROVIDER.md`
- `DESIGN_2026-05-21_M6_25_MEMORY_CONTEXT_BUILDER.md`

---

## Table of contents

<!-- BEGIN AUTO-GENERATED TOC -->
- [1. Purpose and non-goals](#1-purpose-and-non-goals)
  - [Purpose](#purpose)
  - [Non-goals](#non-goals)
- [2. Relationship to eval harness](#2-relationship-to-eval-harness)
  - [Subsystem as System Under Test](#subsystem-as-system-under-test)
  - [Phase 0/1 harness comes first](#phase-01-harness-comes-first)
  - [Required evaluable behavior](#required-evaluable-behavior)
  - [No dependency on harness internals](#no-dependency-on-harness-internals)
- [3. Architecture overview](#3-architecture-overview)
  - [Layer responsibilities](#layer-responsibilities)
  - [End-to-end shape](#end-to-end-shape)
- [4. Minimal stores](#4-minimal-stores)
  - [Store summary](#store-summary)
  - [Minimal conceptual schemas](#minimal-conceptual-schemas)
- [5. Memory card kinds](#5-memory-card-kinds)
  - [Durable storage kinds](#durable-storage-kinds)
  - [Why the older eight buckets should not become a flat enum](#why-the-older-eight-buckets-should-not-become-a-flat-enum)
- [6. Transition and coexistence with existing memory implementation](#6-transition-and-coexistence-with-existing-memory-implementation)
  - [Existing surfaces are migration inputs, not target truth](#existing-surfaces-are-migration-inputs-not-target-truth)
  - [Field migration](#field-migration)
  - [Structured scope migration](#structured-scope-migration)
  - [Schema version migration](#schema-version-migration)
  - [Short-term memory and reentry snapshots](#short-term-memory-and-reentry-snapshots)
  - [Compression migration](#compression-migration)
  - [Method and surface mapping](#method-and-surface-mapping)
- [7. Typed Memory Card schema](#7-typed-memory-card-schema)
  - [Schema overview](#schema-overview)
  - [Field details](#field-details)
  - [Usage statistics boundary](#usage-statistics-boundary)
- [8. Provenance model](#8-provenance-model)
  - [Principle](#principle)
  - [Provenance sources](#provenance-sources)
  - [Required rules](#required-rules)
  - [Raw transcript extraction safeguards](#raw-transcript-extraction-safeguards)
  - [Provenance ref shape](#provenance-ref-shape)
  - [Provenance store API](#provenance-store-api)
- [9. Write path](#9-write-path)
  - [Strict v0/v1 rule](#strict-v0v1-rule)
  - [Write path phases](#write-path-phases)
  - [Conceptual API boundary](#conceptual-api-boundary)
  - [Candidate shape](#candidate-shape)
  - [Normal ingest and privileged eval seeding](#normal-ingest-and-privileged-eval-seeding)
  - [Approval actors and authority](#approval-actors-and-authority)
  - [Approval gate requirements](#approval-gate-requirements)
  - [Mutation semantics](#mutation-semantics)
- [10. Read path](#10-read-path)
  - [Read path overview](#read-path-overview)
  - [RecallRequest schema](#recallrequest-schema)
  - [Step 1: plan recall intent](#step-1-plan-recall-intent)
  - [Step 2: seed retrieval](#step-2-seed-retrieval)
  - [Short-term hybrid recall/search tooling boundary](#short-term-hybrid-recallsearch-tooling-boundary)
  - [Step 3: bounded graph expansion](#step-3-bounded-graph-expansion)
  - [Step 4: governance filtering](#step-4-governance-filtering)
  - [Step 5: ranking](#step-5-ranking)
  - [Step 6: evidence packet projection later](#step-6-evidence-packet-projection-later)
  - [Step 7: audit record](#step-7-audit-record)
- [11. Evaluation adapter requirements](#11-evaluation-adapter-requirements)
  - [Adapter placement](#adapter-placement)
  - [Initially supported adapter methods](#initially-supported-adapter-methods)
  - [Manifest routing contract](#manifest-routing-contract)
  - [Public operation wire forms](#public-operation-wire-forms)
  - [Mapping MemoryCard to harness evidence refs](#mapping-memorycard-to-harness-evidence-refs)
  - [Retrieve result contract](#retrieve-result-contract)
  - [Mapping mutations](#mapping-mutations)
  - [Exposing scope/staleness/contradiction](#exposing-scopestalenesscontradiction)
  - [Unsupported until later phases](#unsupported-until-later-phases)
- [12. Implementation phases](#12-implementation-phases)
  - [Phase A: typed card schema and provenance store only](#phase-a-typed-card-schema-and-provenance-store-only)
  - [Phase B: deterministic read/write core with manual/debug approval](#phase-b-deterministic-readwrite-core-with-manualdebug-approval)
  - [Phase C: adapter to generic memory eval harness](#phase-c-adapter-to-generic-memory-eval-harness)
  - [Phase D: graph/index seed retrieval and bounded expansion](#phase-d-graphindex-seed-retrieval-and-bounded-expansion)
  - [Phase E: MemoryContextBuilder / evidence packet](#phase-e-memorycontextbuilder-evidence-packet)
  - [Phase F: MemoryToolProvider / implement_v2 integration](#phase-f-memorytoolprovider-implement_v2-integration)
  - [Phase G: model-in-loop downstream utility](#phase-g-model-in-loop-downstream-utility)
  - [Short-term hybrid recall/tooling design-only next slice](#short-term-hybrid-recalltooling-design-only-next-slice)
  - [Phase summary](#phase-summary)
- [13. Import and dependency boundaries](#13-import-and-dependency-boundaries)
  - [Forbidden imports in memory subsystem core](#forbidden-imports-in-memory-subsystem-core)
  - [Allowed dependency direction](#allowed-dependency-direction)
  - [Boundary table](#boundary-table)
  - [Static import checks](#static-import-checks)
- [14. Close criteria](#14-close-criteria)
  - [Phase A close criteria: typed card schema and provenance store](#phase-a-close-criteria-typed-card-schema-and-provenance-store)
  - [Phase B close criteria: deterministic core](#phase-b-close-criteria-deterministic-core)
  - [Phase C close criteria: generic harness adapter](#phase-c-close-criteria-generic-harness-adapter)
  - [Phase D close criteria: graph/index expansion](#phase-d-close-criteria-graphindex-expansion)
  - [Phase E close criteria: context/evidence packet](#phase-e-close-criteria-contextevidence-packet)
  - [Phase F close criteria: tool/provider integration](#phase-f-close-criteria-toolprovider-integration)
  - [Phase G close criteria: model-in-loop utility](#phase-g-close-criteria-model-in-loop-utility)
  - [Required cross-phase tests](#required-cross-phase-tests)
- [15. Appendices and canonical detail locations](#15-appendices-and-canonical-detail-locations)
- [16. Risks and anti-patterns](#16-risks-and-anti-patterns)
- [17. Open questions](#17-open-questions)
- [Recommended next action](#recommended-next-action)
<!-- END AUTO-GENERATED TOC -->

## 1. Purpose and non-goals

### Purpose

この文書の目的は、generic memory eval harness の Phase 0/1 が優先される前提で、その背後に置かれる mew memory subsystem の実装方針を定義することである。

この subsystem は、次の性質を持つ System Under Test として設計する。

```text
typed memory cards
+ provenance-backed evidence
+ graph/index support
+ governance gates
+ bounded recall/projection
+ adapter-based evaluation surface
```

中心方針は以下である。

- durable memory は短く、typed で、scoped で、provenance を持つ `MemoryCard` として保存する。
- raw transcript、tool log、verifier output、reviewer comment、diff は durable memory ではなく provenance として扱う。
- graph は primary memory store ではなく、card と provenance / file / symbol / test / error を結ぶ index / expansion layer とする。
- recall は hidden instruction ではなく evidence retrieval として扱う。
- stale / contradicted / out-of-scope / weak-authority memory は projection 前に filter または downgrade する。
- subsystem 独自 benchmark を作らず、最終的には generic adapter-based memory eval harness で評価できる observable behavior を持たせる。

### Non-goals

この文書では次を実装対象にしない。

| Non-goal | 理由 |
| --- | --- |
| generic eval harness 自体の実装 | 別文書 `DESIGN_2026-05-21_M6_25_MEMORY_EVAL_HARNESS_IMPLEMENTATION_PLAN.md` の範囲。 |
| MemoryArena / model-in-loop downstream utility の実装 | generic harness P0/P1 と subsystem の deterministic boundary が安定した後に扱う。 |
| prompt injection by default | memory はまず recall/evidence として扱う。prompt section は後続設計で明示 gate を通す。 |
| model-controlled durable writes | model は candidate を提案できるが、durable commit は core/debug/scoring approval path が必要。 |
| adapter-based eval plan の置換 | subsystem は generic harness の背後に置かれる SUT であり、harness を subsystem 固有 benchmark に置き換えない。 |
| current code / dirty diffs の追認 | 既存実装は未検証であり、この文書の target architecture を満たすとは主張しない。 |
| raw transcript を memory として保存する設計 | raw material は provenance。MemoryCard は extracted / scoped / approved / cited claim。 |
| provider-visible write tool | `MemoryToolProvider(recall)` が来ても read-only recall から始める。 |

---

## 2. Relationship to eval harness

### Subsystem as System Under Test

mew memory subsystem は、generic memory eval harness の背後に置かれる **System Under Test** である。

```text
Generic memory eval harness
  -> MemoryEvalAdapter
       -> mew memory subsystem core
```

harness は fixture、public/gold split、operation sequence、metrics、hard gates、artifacts を所有する。memory subsystem core は harness internal schema に依存しない。adapter だけが harness contract と subsystem contract の変換を行う。

### Phase 0/1 harness comes first

現在の方向性は evaluation-harness-first である。

- Phase 0: adapter contract、fixture split、hash、dummy/broken adapter、conformance。
- Phase 1: deterministic retrieval evaluation。`memory_off`、`memory_on_happy_path`、`retrieval_ranking`、`scope_isolation`、`stale_conflict`、`update_forget`、`abstention`、`budget_limited` を ID-based metrics で評価する。

この subsystem plan は Phase 0/1 harness と競合してはならない。特に以下を守る。

- harness core に mew memory internals を import させない。
- memory core が fixture family、gold label、trap label、scoring profile などを読まない。
- adapter-visible input に gold / expected / mode / trap family が漏れない設計を邪魔しない。
- subsystem-specific benchmark を Phase 0/1 の代替にしない。

Concrete P0 readiness gate:

```text
stable adapter contract/schema
+ dummy adapter conformance passing
+ broken adapter gates still failing for the intended reasons
+ setup_method or mutate_lifecycle routing declared and tested
+ hidden reset-time seeding rejected
+ no core import of harness internals
```

Subsystem graph expansion is gated on this readiness. Graph/index schemas may be defined earlier, but executable graph expansion is Phase D and must not start until the generic adapter conformance path is passing against a dummy adapter and the subsystem adapter contract assumptions are stable.

### Required evaluable behavior

subsystem は、少なくとも adapter から以下の behavior を評価可能にする。

| Harness-facing behavior | Subsystem-side operation | 初期サポート方針 |
| --- | --- | --- |
| `ingest(items)` | provenance capture + normal candidate/proposal ingest | Phase C adapter で fixture experience を provenance/support refs に変換する。 |
| `setup(ops)` | public seed/approve/commit lifecycle setup | Phase C adapter で committed fixture memory を hash-covered public operations として作る。 |
| `mutate(ops)` | update/delete/forget/supersede/tombstone | Phase B で core mutation semantics を deterministic に定義する。 |
| `retrieve(query)` | recall pipeline | Phase B は structured filters + injectable summary-search backend、Phase D は graph expansion を追加。 |
| `report_usage(scope?)` | audit/log aggregation | Phase B から fixed `Usage` fields: latency source, card counts, graph counts, projection chars, and index mode を返す。 |
| later `build_context` | MemoryContextBuilder / evidence packet | Phase E 以降。P0/P1 hard gate にはしない。 |
| later `inspect_provenance` | provenance refs inspection | Phase E 以降。P0/P1 では support refs / role-bearing evidence links を最低限返す。 |

### No dependency on harness internals

memory subsystem core は以下に依存してはならない。

```text
memory_eval fixture family
scorer_view / gold labels
must_not_return_evidence_ids
expected_abstention
trap family
scoring_profile_id
request mode
hard gate names
```

必要な変換は adapter layer で行う。

```text
Experience / MemoryMutation / MemoryQuery
  <-> MemoryProvenanceEvent / MemoryCard seed / RecallRequest / MutationRequest
```

---

## 3. Architecture overview

採用する layered architecture は以下である。

```text
1. Provenance / Event Log
2. Typed Memory Cards
3. Graph / Index Layer
4. Governance Layer
5. Recall / Projection Pipeline
6. Evaluation / Audit Adapter
```

### Layer responsibilities

| Layer | Owns | Must not own |
| --- | --- | --- |
| Provenance / Event Log | raw evidence capture, stable refs, hashes, deletion/rollback support | durable memory semantics, prompt injection |
| Typed Memory Cards | approved scoped claims / episodes / procedures / policies | raw transcript dump, mixed-dimensional flat buckets |
| Graph / Index Layer | relations, retrieval keys, bounded expansion, invalidation edges | primary prose memory store, unbounded graph traversal |
| Governance Layer | scope, authority, lifecycle, approval, staleness, contradiction, privacy | agent planning, hidden instruction priority |
| Recall / Projection Pipeline | retrieve, expand, filter, rank, project bounded evidence, audit | durable write, next action, tool choice |
| Evaluation / Audit Adapter | generic harness adapter, evidence support mapping, usage report | harness core logic, gold labels, subsystem-specific benchmark |

### End-to-end shape

```text
Write side
----------
raw transcript / tool log / verifier output / reviewer comment / diff
  -> provenance event
  -> candidate extraction
  -> type assignment
  -> facet assignment
  -> deduplication
  -> contradiction/staleness checks
  -> approval gate
  -> commit / supersede / tombstone
  -> graph/index update
  -> audit log

Read side
---------
current task / query / scope / current repo evidence
  -> recall intent planning
  -> seed retrieval by structured filters + injected summary-search backend
  -> bounded graph expansion
  -> governance filtering
  -> ranking
  -> bounded evidence packet projection later
  -> audit record
  -> adapter result / tool result / context packet
```

Memory は evidence であり、hidden instruction ではない。fresh repository evidence、current verifier output、current task contract、current user instruction は、原則として memory より強い。

---

## 4. Minimal stores

M6.25 typed-card subsystem の最小 source-of-truth store は以下の 5 つに限定する。

```text
provenance_events
memory_cards
graph_nodes
graph_edges
memory_audit_log
```

### Store summary

| Store | Purpose | 初期実装の性質 |
| --- | --- | --- |
| `provenance_events` | raw evidence と stable refs を保存する。 | append-oriented。raw text は必要最小限と hash/ref を優先。 |
| `memory_cards` | durable typed cards を保存する。 | approved/committed だけが normal recall 対象。candidate/proposal は state で区別可能。 |
| `graph_nodes` | card, provenance, file, symbol, test, command, error, task, actor の canonical node identity を保存する。 | durable。virtual-only nodes は避け、canonicalization / staleness / invalidation の anchor にする。 |
| `graph_edges` | durable graph nodes 間の関係を保存する。 | bounded expansion と invalidation の補助。 |
| `memory_audit_log` | write/read/mutate/project/report_usage の trace を保存する。 | eval adapter と debug に使う。memory そのものではない。 |

`retrieval_index` is intentionally not in this list. BM25/lexical/vector indexes are derived, rebuildable, non-authoritative data structures. Phase B owns only simple direct scan or synchronously rebuilt in-memory/file-local lexical indexes over committed `memory_cards` text and canonical applicability refs. Phase D owns graph-aware/optimized derived indexes built from committed `memory_cards`, `graph_nodes`, and `graph_edges`, including async invalidation markers and rebuild verification. Indexes may be cached, snapshotted, or regenerated for performance, but they must never be the only source of a durable memory fact, state transition, provenance link, or audit decision.

### Minimal conceptual schemas

#### `provenance_events`

```text
provenance_event
  event_id: string
  event_kind: transcript_turn | tool_call | command_output | verifier_output | reviewer_comment | diff | file_snapshot | user_instruction | approval | memory_proposal | other
  scope: Scope
  actor: user | assistant | tool | verifier | reviewer | maintainer | system | adapter | scoring | migration
  event_time: datetime
  payload_ref: string | null
  provenance_excerpt: string | null
  payload_hash: string
  content_mime: string | null
  source_run_id: string | null
  source_session_id: string | null
  source_turn_id: string | null
  source_experience_id: string | null
  source_mutation_id: string | null
  redaction_state: none | redacted | restricted
  retention_state: active | pending_delete | deleted
  created_at: datetime
```

`provenance_excerpt` is the only canonical inline excerpt field. It is optional, redaction-controlled, and capped at 240 chars by default unless a stricter source-specific policy applies. Larger raw payloads live behind `payload_ref` plus `payload_hash`; they are inspected only through authorized provenance APIs.

#### `memory_cards`

```text
memory_card
  card_id: string
  schema_version: string
  kind: MemoryCardKind
  summary: string
  details: string | null
  retrieval_terms: list[string]
  scope: Scope
  lifecycle: Lifecycle
  authority: Authority
  valence: Valence
  evidence_links: list[EvidenceLink]
  invalidators: list[Invalidator]
  confidence: float
  applicability: Applicability
  projection_mode: ProjectionMode
  graph_refs: GraphRefs
  privacy: PrivacyRules
  audit fields...
```

#### `graph_nodes`

`NodeType` enum:

```text
memory_card | provenance_event | file | symbol | test | command | error_signature | task | task_family | workflow | scope | actor | user | reviewer | verifier
```

```text
graph_node
  node_id: string
  node_type: NodeType
  scope: Scope
  scope_key: string
  canonical_ref: string
  display_name: string
  content_hash: string | null
  metadata: object
  staleness_state: fresh | maybe_stale | stale | superseded
  created_at: datetime
  updated_at: datetime
```

Rules:

- `memory_card` node `canonical_ref` is `card.card_id`。
- `provenance_event` node `canonical_ref` is `provenance_event.event_id`。
- examples below are schematic display forms; actual serialized `node_id` applies the structured-key encoding rules below。
- file nodes use canonical repo-relative paths plus repo/branch scope, e.g. `file:<repo_ref>:<branch_ref>:src/mew/memory_core.py`。
- symbol nodes use repo/branch/file plus stable symbol path when available, e.g. `symbol:<repo_ref>:<branch_ref>:src/mew/memory_core.py::MemorySystem.recall`。
- test nodes use canonical test selector, e.g. `test:<repo_ref>:<branch_ref>:tests/test_memory_core.py::test_name`。
- command nodes use normalized command identity plus working directory/scope; command output remains provenance。
- error signature nodes use normalized error class/message frame hash, not full raw output。
- task_family nodes use `task_family:<stable-id>` and expand only by stable task family membership recorded in scope/task metadata。
- workflow nodes use `workflow:<stable-id>` and expand only by stable workflow ID; display names are metadata, not canonical identity。
- task/user/reviewer/verifier nodes use stable public IDs or scoped pseudonymous IDs; no raw private payload belongs in `canonical_ref`。
- actor-like nodes should use `node_type=actor` with `metadata.actor_kind = user | reviewer | verifier | maintainer | system | adapter | scoring | migration`。The older `user` / `reviewer` / `verifier` node types are compatibility aliases and must not be extended for new actor kinds。
- actor node `canonical_ref` is a stable public actor ID or scoped pseudonymous ID; actor display names are metadata only。
- canonical storage identity is the structured key `{node_type, scope_key, canonical_ref}`。`node_id` is a deterministic `NodeIdV1` display string derived from that structured key, not the primary identity parser。
- `scope_key` is stored on `graph_node` and derived from `Scope` as `scope:v1:<level>:<digest16>` where `<digest16>` is the first 16 lowercase hex chars of `sha256(canonical_scope_json)`。`canonical_scope_json` uses sorted keys, omits null fields, normalizes all strings to UTF-8 NFC before hashing, and includes `level`, `namespace`, `user_id`, `project_id`, `repo_ref`, `branch_ref`, `task_ref`, `task_family`, and `lane_id` when non-null。
- `NodeIdV1` serializes exactly as `node:v1:<node_type>:<encoded_scope_key>:<encoded_canonical_ref>`。The ordered fields and separators are fixed; parsers must reject missing fields, extra separators, unsupported versions, or empty `node_type` / `scope_key` / `canonical_ref`。
- `encoded_scope_key` and `encoded_canonical_ref` use UTF-8 NFC followed by percent-encoding of every byte outside the unreserved set `[A-Za-z0-9._~-]`。Hex digits in `%HH` escapes are uppercase。Raw `%` is not allowed except as a valid `%HH` escape, and non-canonical or double-encoded forms are rejected before lookup。
- `display_name` is never part of identity and may change without changing `node_id`。
- raw private payload must not appear in `node_id`, `scope_key`, or `canonical_ref`; use scoped pseudonymous IDs plus provenance refs/hashes when sensitive material is needed for inspection。
- `node_id` is globally unique across all node types through `NodeIdV1` serialization of `{node_type, scope_key, canonical_ref}`。Human-oriented type prefixes (`file:`, `symbol:`, `task_family:`, `workflow:`, `scope:`, `text:`) remain reserved for applicability refs and debug projections, not canonical graph node identity。
- `scope:` maps to a scope node or deterministic scope filter。`text:` is reserved only for non-expanding applicability refs and must never create a graph node。
- Phase D cannot close until these canonicalization conventions are implemented and tested for every node type used by graph expansion。

`graph_nodes` is what makes invalidation deterministic: file hash changes, symbol moves, verifier state changes, and command identity changes update or mark the node, then `graph_edges` identify affected cards. Virtual-only expansion nodes are allowed only as transient query planner artifacts and must not appear in durable audit, invalidation, or support mappings.

Graph endpoint policy:

- In Phase B, `graph_refs` are optional. If absent, the card remains retrievable by structured filters and lexical/direct-scan retrieval only。
- if Phase A/B committed cards include `graph_refs`, they may reference only canonical `graph_nodes` and durable `graph_edges`。If an endpoint cannot be canonicalized, commit rejects with a structured validation error。
- Phase D adds executable graph expansion requirements; Phase B does not require every committed card to have graph refs。
- candidate/proposal/migration paths may hold unresolved refs as non-expanding debug metadata with an audit warning; those refs cannot participate in graph expansion, invalidation, support mapping, or ranking。
- Phase D graph expansion must fail closed on unresolved endpoints: either canonicalize first or drop the edge with reason `uncanonicalized_graph_endpoint` and internal audit IDs only。
- no durable expanding edge may point at a virtual-only node。

#### `graph_edges`

```text
graph_edge
  edge_id: string
  from_node_id: string
  from_node_type: NodeType
  to_node_id: string
  to_node_type: NodeType
  edge_type: mentions | applies_to | does_not_apply_to | proved_by | contradicted_by | invalidated_by | supersedes | supports | avoids | fixes | fails_on | located_in | reviewed_by | approved_by | vetoed_by | seed_eval_by | migrated_by | related
  scope: Scope
  evidence_links: list[EvidenceLink]
  confidence: float
  staleness_state: fresh | maybe_stale | stale | superseded
  created_at: datetime
  updated_at: datetime
```

`confidence` uses the same `[0.0, 1.0]` semantics and 4-decimal canonical hash rounding as `MemoryCard.confidence`. It is relation-local confidence: it says how strongly this edge is supported, not whether the card itself is true.

Graph edge evidence rules:

- graph edges use role-bearing `EvidenceLink`, not bare provenance refs。
- `supports` / `proved_by` edges require active `current_support` or `proof` evidence links。
- `approved_by`, `reviewed_by`, `vetoed_by`, `seed_eval_by`, and `migrated_by` edges target `node_type=actor` nodes。Their target actor node must have `metadata.actor_kind` matching the approving/reviewing/vetoing/seeding/migrating actor。
- `approved_by`, `reviewed_by`, and `vetoed_by` edges use `approval` or `reviewer_context` links and do not become scored support IDs。
- `seed_eval_by` and `migrated_by` edges are audit/lineage edges only; normal recall does not expand through them unless the request intent is debug/audit/history。
- if an edge's evidence link is forgotten, deleted, or privacy-redacted, the edge is tombstoned or removed from expansion before recall; no graph expansion may expose the redacted provenance or adjacent edge ID to unauthorized callers。

#### `memory_audit_log`

```text
memory_audit_event
  audit_id: string
  operation: capture_provenance | extract_candidate | propose | approve | commit | mutate | retrieve | retrieve_transient | expand | project | report_usage | migrate | rollback | seed_eval
  request_hash: string
  result_hash: string
  actor: core | debug | scoring | adapter | model_proposal | user | reviewer | verifier | maintainer | migration | system
  card_ids: list[string]
  provenance_event_ids: list[string]
  mutation_ids: list[string]
  dropped: list[DroppedReason]
  usage: Usage
  metadata: object
  created_at: datetime
```

Audit payload boundary:

- `memory_audit_log` stores IDs, hashes, counts, reasons, actor/source labels, timestamps, and small structured metadata only。
- it must not store raw transcripts, raw command output, full diffs, full projected packets, or full context/evidence packets。
- large payloads belong in `provenance_events` with an explicit redaction/retention policy and are referenced from audit by ID/hash only。
- audit metadata intended for debug must be bounded and privacy-filtered before any caller-visible report。

Concrete audit size limits:

- `metadata` max serialized size is 8192 bytes after canonical JSON serialization。Overflow replaces it with a bounded metadata object containing `metadata_truncated=true`, `metadata_hash=sha256(full_metadata)`, and deterministic prefix fields; the replacement object, including flags and hashes, must be no larger than 8192 bytes。
- `dropped` may contain at most 100 detailed records. Overflow records are aggregated into `dropped_count_by_reason`; audit metadata records `dropped_overflow_count` and `dropped_overflow_hash=sha256(canonical_overflow_records)`。
- any free-form reason string in `dropped`, `metadata`, or audit receipts is capped at 256 Unicode scalar values. Longer values are represented as `prefix_236 + "#sha256:" + sha256(full_value)[0:12]` so the stored representation also fits the cap。
- ID lists (`card_ids`, `provenance_event_ids`, `mutation_ids`) may contain at most 500 entries each in one audit event; overflow uses the first 500 sorted IDs plus `<field>_overflow_count` and `<field>_overflow_hash` metadata。
- these truncation/hash policies are deterministic and must run before persistence and before caller-visible report generation。

---

## 5. Memory card kinds

### Durable storage kinds

Durable card kinds は以下の 5 つに限定する。

```text
reentry_snapshot
task_episode
semantic_fact
procedure
policy_or_preference
```

| Kind | Purpose | Default lifecycle | Default write gate |
| --- | --- | --- | --- |
| `reentry_snapshot` | 現在/直近タスクの再開に必要な state。 | `session` / `task_chain` | transient は low、durable promotion は high。 |
| `task_episode` | 過去 task の試行、成功、失敗、証拠、task shape。 | `task_chain` / `project_durable` | evidence links 必須。moderate。 |
| `semantic_fact` | project/repo/branch/task_family に関する安定した事実。 | `project_durable` | repo/doc/verifier/reviewer evidence 必須。moderate-high。 |
| `procedure` | repair recipe、runbook、診断/検証手順。 | `project_durable` / approved shared | verifier/reviewer/maintainer evidence 必須。high。 |
| `policy_or_preference` | user preference、review rule、maintainer decision、privacy/interaction constraint。 | `user_durable` / `project_durable` / `shared` | explicit authority 必須。high。 |

### Why the older eight buckets should not become a flat enum

旧 8 bucket は retrieval intent や fixture family としては有用だが、そのまま `memory_kind` enum にすると混合軸になる。

| Old bucket | 問題 | New representation |
| --- | --- | --- |
| `working/reentry` | storage kind としては妥当だが名称が広い。 | `kind=reentry_snapshot` |
| `episodic task` | storage kind としては妥当。 | `kind=task_episode` |
| `semantic project` | project 限定ではなく repo/branch/task_family も必要。 | `kind=semantic_fact` + `scope` |
| `procedural repair` | storage kind としては妥当だが gate が強い。 | `kind=procedure` + verifier/reviewer evidence |
| `failure shield` | kind ではなく negative evidence / behavioral effect。 | `valence.polarity=negative`, `valence.effect=avoid|verify` |
| `reviewer correction` | kind ではなく authority/source。 | `authority.source=reviewer`, `authority.strength=should|must` |
| `user preference` | user scope と authority の問題。内容は policy/fact/procedure になり得る。 | usually `kind=policy_or_preference`, `scope.level=user`, `authority.source=user` |
| `file/symbol graph` | memory item ではなく retrieval/index infrastructure。 | `graph_nodes` / `graph_edges` / index layer |

`memory_kind` は「何を記憶しているか」だけを表す。誰が言ったか、どの scope か、どれほど強いか、negative evidence か、どう検索されるかは facet として分離する。

---

## 6. Transition and coexistence with existing memory implementation

### Existing surfaces are migration inputs, not target truth

The existing implementation around `src/mew/memory_core.py` has useful behavior but is not the final schema:

```text
MemoryEntry
MEMORY_KINDS = project_convention | episodic_task | procedural_repair | failure_shield | reviewer_correction | file_symbol_edge | user_preference
MemorySystem.write_candidate()
MemorySystem.approve()
MemorySystem.commit_memory()
MemorySystem.recall()
MemorySystem.adapt_recall()
MemorySystem.expand_chain()
MemorySystem.compress_memory()
memory_arena.py
memory_debug.py
memory_compression.py
short_term_memory.py
CLI memory-core surfaces
tests/test_memory_core.py and tests/test_memory_debug.py
```

Phase A/B should wrap and port these surfaces; it should not hard-delete them before adapter conformance exists. Compatibility rule:

- existing stores remain readable through a migration adapter until a typed-card store passes Phase A/B/C close criteria。
- new writes after the typed-card implementation lands must use `MemoryCard`/`ProvenanceEvent`; legacy `MemoryEntry` writes are allowed only behind compatibility CLI/debug flags until deprecation。
- existing tests/CLI/debug/compression behavior should be ported to the typed-card APIs in the same phase that ports the underlying method; compatibility tests should prove legacy fixtures migrate deterministically。
- `memory_arena.py` remains an eval/benchmark integration surface, not a target storage model; it should use the generic adapter or a typed-card shim after Phase C。

### Field migration

| Existing `MemoryEntry` field | Target `MemoryCard` / store field | Rule |
| --- | --- | --- |
| `entry_id` | `card_id` plus `revision.legacy_entry_ids[]` metadata | Preserve if already stable and non-conflicting; otherwise create `mem_...` and record lineage/supersession。 |
| `memory_kind` | `kind`, `valence`, `authority`, `graph_nodes/graph_edges` | Use kind mapping table below; do not carry old enum into new storage。 |
| `scope: str` | structured `Scope` or quarantine | Parse known prefixes; unparseable strings enter fail-closed quarantine with `metadata.legacy_scope_string` and no normal recall/graph expansion。 |
| `title` | `summary` prefix or metadata `legacy_title` | Do not create a separate durable title unless UI/debug needs it。 |
| `summary` | `summary` / synthesized `details` | Revalidate raw transcript and length safeguards before commit。 |
| `applicability: str` | `Applicability.applies_to` and `prerequisites` | Split structured refs where possible; preserve raw string in metadata only if parsing is lossy。 |
| `source_refs` / `proof_refs` | `provenance_events` + role-bearing `evidence_links` | Create provenance events with source/proof metadata; committed cards cite event IDs with `current_support` or `proof` roles。 |
| `created_at`, `last_verified_at` | `timestamps` | Preserve exact values if valid datetimes。 |
| `validity` | `staleness_state`, `contradiction_state`, metadata | Map explicit stale/superseded terms to state; otherwise keep as metadata。 |
| `confidence` | `confidence` | Clamp to `[0.0, 1.0]`, round canonically for hashes。 |
| `staleness`, `contradiction` | target state + `invalidators` + audit | Preserve reasons/invalidators; do not silently resolve。 |
| `revision` | `revision` | Preserve supersedes/superseded/tombstone lineage; do not reuse a superseded card as committed active。 |
| `graph_edges` | `graph_nodes` + `graph_edges` | Create durable nodes before edges; reject edges whose endpoints cannot be canonicalized unless Phase D explicitly keeps them as non-expanding debug metadata。 |
| `approved`, `lifecycle_state` | `approval_state` | `approved=true,lifecycle_state=committed` maps to `committed`; tombstoned maps to `tombstoned`; do not silently upgrade unapproved entries。 |

Old kind mapping:

| Existing kind | Target representation |
| --- | --- |
| `project_convention` | Usually `semantic_fact`; if it is a normative rule or preference, `policy_or_preference` with maintainer/reviewer/user authority。 |
| `episodic_task` | `task_episode`。 |
| `procedural_repair` | `procedure` with prerequisites/applicability/invalidators。 |
| `failure_shield` | `procedure` or `task_episode` with `valence.polarity=negative`, `effect=avoid|verify`, and required applicability/counterexamples。 |
| `reviewer_correction` | Content kind based on claim; `authority.source=reviewer` and `source_refs` to reviewer provenance。 |
| `file_symbol_edge` | `graph_nodes` / `graph_edges`; if it contains a stable claim, also create a cited `semantic_fact`。 |
| `user_preference` | Usually `policy_or_preference` with `scope.level=user` and `authority.source=user`; project facts embedded in the preference must be split into separate scoped cards。 |

### Structured scope migration

Legacy flat scope strings are migrated conservatively:

```text
repo:mew                         -> level=repo, namespace=repo:mew, repo_ref=mew
repo:mew@branch:main             -> level=branch, namespace=repo:mew@branch:main, repo_ref=mew, branch_ref=main
task:<id>                        -> level=task, namespace=task:<id>, task_ref=<id>
memoryarena:<family>:<row_id>    -> level=task, namespace=memoryarena:<family>:<row_id>, task_family=<family>, task_ref=<row_id>
private/user:<id>                -> level=user, namespace=user:<id>, user_id=<id>
shared/team:<id>                 -> level=team|shared according to prefix, namespace=<legacy string>
unknown string                   -> quarantine, metadata.legacy_scope_string=<legacy string>, no normal recall
```

Migration must not broaden scope. If a flat string cannot be parsed safely, migration places the card in a fail-closed quarantine state: no normal recall, no graph expansion, no support mapping, and no projection. A maintainer/debug migration may later assign a structured scope with a new audit event; until then the card is inspectable only through authorized debug migration tooling.

### Schema version migration

Typed cards use semantic schema identifiers such as `memory_card.v1`. Migration rules:

- reject unknown major versions for `memory_cards`, `provenance_events`, `graph_nodes`, and `graph_edges`。
- allow optional minor fields when the major version is known and validation can supply safe defaults。
- preserve `card_id` lineage or record `supersedes` / `superseded_by`; never reuse an old ID for a materially different claim without revision metadata。
- do not silently change `approval_state` or `authority`; migration can lower recallability but cannot upgrade authority/approval without a new audit event。
- every migration writes `memory_audit_log` entries with request hash, result hash, actor, source store version, target schema version, migrated IDs, rejected IDs, and redaction decisions。
- migration failure is fail-closed: rejected cards remain in the legacy store for authorized debug inspection but are not normal recall candidates。

### Short-term memory and reentry snapshots

`ShortTermMemoryCard` and `ShortTermMemoryBuffer` stay as active session state. They are not deprecated by typed durable memory in Phase A/B. Relationship:

- transient short-term cards remain in `ShortTermMemoryBuffer`。
- transient reentry snapshots use a session-scoped reentry state record, initially backed by the active work/session state boundary rather than `memory_cards`。They may cite short-term card IDs, turn refs, and work-session refs, but they are not durable memory。
- only promoted snapshots become durable `memory_cards` with `kind=reentry_snapshot`, evidence links, scope, approval state, and lifecycle。
- normal durable recall reads only committed `MemoryCard` records。
- task-resume recall may read active session reentry state through a separate session gate, `retrieve_transient`, that records audit/trace separately from durable recall and cannot return durable `support_experience_ids`。
- Phase B covers the promotion gate and durable recall governance; transient session-state recall remains a separate session-state surface with minimal scope/privacy audit until a later context/session design expands it。
- short-term memory can be an input to candidate extraction, but it cannot become committed durable memory without the same provenance/proposal/approval/commit pipeline。

### Compression migration

`memory_compression.py`, `MemorySystem.compress_memory()`, and the CLI `memory-core compress` command become candidate/proposal producers, not commit paths:

```text
raw text / raw file
  -> capture_provenance(event_kind=transcript_turn|command_output|other)
  -> extract/compress candidate
  -> propose_memory
  -> approve_memory
  -> commit_memory
```

Compression results may return `candidate`, `merge_existing`, or `drop`, but `candidate` means proposal material only. The compressor must preserve `support_experience_ids` through provenance when invoked from fixtures, must enforce raw transcript safeguards, and must not include gold labels/trap families. Retire the legacy direct-compression-to-entry path after Phase B lifecycle tests and Phase C adapter conformance pass against the typed path.

### Method and surface mapping

| Existing surface | Target status | Target API |
| --- | --- | --- |
| `write_candidate` | port | `extract_candidate` / `propose_memory`; returns candidate/proposal state only。 |
| `approve` | port | `approve_memory`; enforces actor/kind matrix and state machine。 |
| `commit_memory` | port | `commit_memory`; transactional commit across card/node/edge/index/audit updates。 |
| `recall` | port | `recall`; returns deterministic typed retrieve result and appends audit only。 |
| `adapt_recall` | fold or keep as read-side adapter | If kept, it filters/ranks/projects recall output only; it cannot mutate durable memory。 |
| `expand_chain` | port in Phase D | Uses durable `graph_nodes`/`graph_edges`; cannot start before adapter conformance gate。 |
| `compress_memory` | change semantics | Candidate/proposal producer; no direct committed card creation。 |
| `memory_debug.py` inspect/artifacts | port | Reads typed cards/provenance/audit with authorization-aware redaction。 |
| CLI `memory-core recall/chain/inspect/score/compress/arena*` | port gradually | Compatibility flags may read legacy stores; typed recall/inspect/score/compress become default after Phase C; graph `chain` default waits for Phase D。 |
| tests | port/extend | Existing tests remain compatibility coverage; new tests enforce typed schema, state machine, adapter, redaction, migration。 |

---

## 7. Typed Memory Card schema

### Schema overview

実装時の class / dataclass / table 名は codebase に合わせてよい。ただし以下の field と enum の意味は保持する。

```yaml
MemoryCard:
  card_id: string
  schema_version: "memory_card.v1"
  kind: reentry_snapshot | task_episode | semantic_fact | procedure | policy_or_preference

  summary: string
  details: string | null
  retrieval_terms: list[string]
  confidence: float

  scope: Scope
  lifecycle: Lifecycle
  authority: Authority
  valence: Valence
  applicability: Applicability
  evidence_links: list[EvidenceLink]
  invalidators: list[Invalidator]
  staleness_state: fresh | maybe_stale | stale | superseded
  contradiction_state: none | possible | contradicted | resolved
  approval_state: candidate | proposal | approved | committed | rejected | superseded | tombstoned
  projection_mode: hidden | debug_only | recalled_tool_result | context_packet | prompt_section | always_on_core
  graph_refs: GraphRefs
  privacy: PrivacyRules

  timestamps:
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | null
    superseded_at: datetime | null
    tombstoned_at: datetime | null

  revision:
    version: int
    supersedes: list[string]
    superseded_by: list[string]
    contradicted_by: list[string]

  audit:
    created_by: core | debug | scoring | adapter | model_proposal | user | reviewer | maintainer | migration | system
    write_reason: string
    create_audit_id: string
    last_semantic_mutation_audit_id: string | null
```

### Field details

#### `card_id`

```text
card_id: mem_<stable id>
```

Rules:

- stable across recall calls。
- adapter may map it to `evidence_ref`。
- deterministic fixtures may seed known IDs。
- must not encode gold label, fixture mode, expected behavior, or trap family。

#### `kind`

```text
reentry_snapshot | task_episode | semantic_fact | procedure | policy_or_preference
```

Rules:

- required。
- small enum only。
- old eight buckets must not be added unless they answer the same storage-kind question。

#### `summary`

```text
summary: 1..512 chars
```

Rules:

- must be human-inspectable。
- must not contain raw transcript dumps or direct raw transcript copies。
- must be safe to project only after governance filtering。
- validation must reject committed cards whose summary exceeds 512 chars by default。

#### `details`

```text
details: synthesized explanation, 0..4096 chars by default
```

Rules:

- details are synthesized/extracted card prose, not a raw transcript payload。
- validation must reject committed cards whose details exceed 4096 chars by default unless an explicit debug/storage policy raises the limit。
- direct quote/excerpt material longer than 240 chars must live in `provenance_excerpt` on a `provenance_event`, not in `details`。
- `event_kind=transcript_turn` / `raw_transcript` provenance cannot be copied directly into `details` unless the extractor records an explicit `extractor_marker` in card metadata and cites the source event。
- extractor output should summarize decisions, facts, prerequisites, or failures; it must not preserve speaker-by-speaker transcript structure in durable card prose。

#### `retrieval_terms`

```text
retrieval_terms: 0..32 concise anchor strings, each <= 96 chars
```

Rules:

- `retrieval_terms` are search/ranking anchors, not projected user-facing prose。
- terms preserve raw identifying discriminators that make a card findable even when `summary` / `details` are synthesized or paraphrased。
- extractors should keep short raw-text anchors for subject, target context, condition, object, and value. Examples: names, colors, folder names, review types, product names, command names, file/symbol refs, and other discriminators。
- terms must be concise tokens or short phrases, not full sentences, transcript excerpts, speaker-role prefixes, raw URLs, or long path/blob payloads。
- duplicate terms are removed case-insensitively while preserving first occurrence order。
- `retrieval_terms` participate in stable serialization and card hash lineage. Adding or changing them is a semantic retrieval mutation and must be audit-visible。
- `retrieval_terms` inherit the card's `Scope` and `PrivacyRules`; they are never a separate cross-scope or lower-privacy search surface。
- derived lexical/vector indexes over `retrieval_terms` must be invalidated, redacted, or rebuilt when the card or supporting provenance is forgotten, deleted, privacy-blocked, redacted, or scope-changed。
- `retrieval_terms` must not include fixture gold labels, fixture modes, trap family names, or any scoring-only labels。
- `retrieval_terms` do not replace `applicability`: anchors answer "what terms should match this claim"; applicability answers "where this claim may be used"。
- every write path that can create or update searchable card prose must route `retrieval_terms` explicitly: candidates use `proposed_retrieval_terms`, seeded cards use `SeedCardSpec.retrieval_terms`, and mutation patches use `ReplacementContent.retrieval_terms`。
- clear/empty semantics are explicit. `retrieval_terms: []` replaces the term list with an empty list; `retrieval_terms: null` is accepted only when `clear_fields` contains `retrieval_terms` and canonicalizes to the same empty-list replacement。
- normal projection and context packets may omit `retrieval_terms`; debug/audit views may expose them after privacy filtering。

#### `confidence`

```text
confidence: float in [0.0, 1.0]
```

Rules:

- `0.0` means no trust beyond trace/debug visibility; `1.0` means maximum memory-local confidence after evidence and approval, not global truth。
- confidence is an input to ranking/governance, not a substitute for scope, evidence, authority, or freshness。
- JSON serialization for hashing must canonicalize confidence to a fixed precision, initially 4 decimal places, after clamping to `[0.0, 1.0]`。

#### `scope`

```yaml
Scope:
  level: user | project | repo | branch | task | task_family | team | shared
  namespace: string
  user_id: string | null
  project_id: string | null
  repo_ref: string | null
  branch_ref: string | null
  task_ref: string | null
  task_family: string | null
  lane_id: string | null
```

Rules:

- every card must have scope。
- `scope.level=user` must not be used to smuggle project facts across repos。
- retrieval must filter scope before projection and before caller-visible dropped IDs expose sensitive refs。

Scope match/overlap semantics:

`scope_allows(caller.authorization_scope, card.scope)` is evaluated after the privacy/sharing gate. Normal recall requires a deterministic match in this table; broader "maybe relevant" matching belongs in applicability or graph expansion after visibility succeeds.

| Card scope level | Normal match / containment rule |
| --- | --- |
| `task` | exact same `task_ref` only, with matching repo/project fields when present。 |
| `task_family` | same `task_family` and same repo or project containment; it does not match unrelated tasks that merely share words in a title。 |
| `branch` | same `repo_ref` + same `branch_ref`; descendant task scopes on that branch may see it。 |
| `repo` | same `repo_ref`; branch-specific recall is allowed only when card `branch_ref` is null, or when an explicit repo policy permits cross-branch recall。 |
| `project` | caller repo/task must be explicitly registered under `project_id`; no project inference from path/name similarity。 |
| `user` | same `user_id` and only user preferences/policies; user scope must not authorize project facts unless the card also has project/repo-scoped support through normal sharing rules。 |
| `team` | same team namespace plus `PrivacyRules.allowed_scope_ids` canonical `scope_key` match; team scope does not override user/project/repo isolation。 |
| `shared` | explicit canonical `scope_key` or resolved `shared_policy:v1:<stable-id>` match plus sharing policy approval; shared scope is not global by default。 |

Overlap rules:

- exact scope match outranks containment but does not bypass privacy。
- project contains only registered repos; repo contains branches only under the repo rule above; branch contains descendant tasks; task does not contain broader branch/repo memories。
- team/shared are audience scopes, not content scopes. They require both a sharing policy and an allowed content scope ID。

#### `lifecycle`

```yaml
Lifecycle:
  lifespan: turn | session | task_chain | project_durable | user_durable | shared
  expires_at: datetime | null
  consolidation_state: none
  retention_policy_id: string | null
```

Rules:

- lifecycle is not top-level architecture。
- stale handling is not just age; invalidators matter more。
- if `expires_at` is in the past, normal recall excludes the card as fresh and treats it as `maybe_stale` for historical/debug recall unless an explicit mutation changes state。
- expiry does not automatically tombstone, supersede, or delete a card。Those require explicit mutation and audit。
- `consolidation_state` is restricted to `none` until a future consolidation phase defines merge/summarization semantics。Inputs with `pending` or `consolidated` must be rejected rather than guessed。

#### `authority`

```yaml
Authority:
  source: self | verifier | reviewer | user | maintainer | system | scoring
  strength: observation | hint | should | must
  source_refs: list[string]
```

Rules:

- reviewer correction is represented here, not as kind。
- `must` requires strong source。
- self-generated memory without proof must remain `observation` or `hint`。
- `source=scoring` is allowed only for deterministic eval fixture setup and must not be used for production/user memory authority。
- canonical wire format is the object form above。Colon-joined strings such as `reviewer:should` are metadata/debug projections only and must not be parsed as authoritative storage。
- `source_refs` are `provenance_event.event_id` values unless a field explicitly says it accepts another ref type。
- actor and authority may diverge only when provenance makes the delegation explicit。Example: `actor=adapter` may write a fixture-approved card with `authority.source=scoring` only through `seed_committed_card_for_eval`; normal adapter ingest must not claim user/reviewer authority without matching provenance。
- `Authority.strength` is memory-local force inside the card's scope after governance filtering。It is not prompt hierarchy priority; `must` never becomes a system/developer instruction and never bypasses current user instruction, policy, privacy, scope, or freshness gates。

#### `valence/effect`

```yaml
Valence:
  polarity: positive | negative | neutral
  effect: use | avoid | verify | ask | ignore
```

Rules:

- failure shield is represented here, not as kind。
- negative memory should normally trigger `verify` or scoped `avoid`, not an unscoped permanent ban。

#### `applicability`

```yaml
Applicability:
  applies_to: list[ApplicabilityRef]
  does_not_apply_to: list[ApplicabilityRef]
  prerequisites: list[ApplicabilityRef]
  counterexamples: list[ApplicabilityRef]
```

Rules:

- applicability answers where the card can be applied。
- invalidators answer when the card may have become stale。
- `ApplicabilityRef` is a string in the same canonical graph node ID convention where possible: `file:...`, `symbol:...`, `test:...`, `cmd:...`, `err:...`, `task:...`, `task_family:...`, `workflow:...`, `scope:...`, `user:...`, `reviewer:...`, `verifier:...`。
- task-family refs use reserved `task_family:<stable-id>` and resolve/expand only by that stable task-family ID。
- workflow refs use reserved `workflow:<stable-id>` and resolve/expand only by that stable workflow ID; free-text workflow names are not canonical refs。
- scope-only refs use reserved `scope:<level>:<namespace-hash-or-stable-id>` and resolve to a scope node or deterministic scope filter。
- free-text fallback is allowed only as reserved `text:<sha256-12>:<short-slug>` with the full text stored in metadata; `text:` refs are non-expanding, never create graph nodes/edges, and do not satisfy Phase D graph canonicalization close criteria。
- `applies_to` should use concrete scope, file, symbol, command, error signature, task-family, or workflow refs where possible。
- `does_not_apply_to` and `counterexamples` are required for broad procedure / failure-shield-like negative memories unless the card is intentionally narrow by scope。
- procedure and negative-valence cards must use applicability to prevent over-application; a failure shield without a bounded `applies_to` or meaningful `does_not_apply_to` remains proposal/debug-only。

#### `evidence_links`

```yaml
EvidenceLink:
  ref_id: string
  role: current_support | proof | approval | lineage | supersession | invalidator | contradiction | reviewer_context | mutation_source | debug
  active: bool
  added_by_mutation_id: string | null
  note: string | null
```

Rules:

- durable committed cards should have at least one active `current_support` or `proof` link。
- `semantic_fact`, `procedure`, and `policy_or_preference` must have active support/proof links before commit。
- every committed card that may be returned as scorable P0/P1 ranked evidence must have at least one active `current_support` link。Proof-only committed cards may exist for debug/historical recall, but the adapter must abstain or mark them unscorable in deterministic P0/P1 unless governance aliases/duplicates a proof link as explicit `current_support`。
- approval provenance must use `role=approval`; it is not support unless it independently supports the claim content。
- stale, invalidator, lineage, reviewer context, and superseded provenance must not map to `support_experience_ids` unless a current returned card explicitly exposes it as active support after governance filtering。
- `evidence_refs` may exist only as a legacy/debug projection equal to the union of `EvidenceLink.ref_id`; storage and adapter scoring use role-bearing `evidence_links`。
- cards without evidence links can exist only as candidate/proposal or low-authority transient reentry。
- when multiple active `current_support` links remain after governance filtering, their `source_experience_id` values form a set. The adapter must preserve the set and must not choose, rank, or infer which support ID is the gold answer。

#### `invalidators`

```yaml
Invalidator:
  kind: file_hash_changed | symbol_moved | symbol_removed | command_changed | verifier_changed | branch_changed | task_contract_changed | reviewer_vetoed | user_preference_updated | policy_superseded | procedure_failed_recently | manual
  ref: string | null
  target_node_id: string | null
  target_node_type: NodeType | null
  baseline_hash: string | null
  baseline_ref: string | null
  baseline_value: string | null
  baseline_observed_at: datetime | null
  trigger_policy: hash_changed | ref_missing | ref_changed | value_changed | any_newer_authority | any_newer_failure | newer_evidence | manual_only
  manual_reason: string | null
  metadata: object
  checked_at: datetime | null
```

Rules:

- `ref` is a compatibility/debug alias. New invalidators must use `target_node_id`/`target_node_type` when the target is graph-addressable, or `baseline_ref` when it is an external verifier/task/policy ref。
- stored baseline data lives on the invalidator, not only in current request state。
- `baseline_hash` is used for file/symbol/command/verifier artifact comparisons。
- `baseline_value` is used for branch/task/user preference/policy values where a hash would hide the comparison needed for debugging。
- invalidator triggered => `staleness_state=maybe_stale|stale|superseded`。
- normal recall must not project stale memory as fresh。

Trigger policy validation:

| Invalidator kind | Required baseline / target | Default valid trigger_policy | Other allowed policies |
| --- | --- | --- | --- |
| `file_hash_changed` | `target_node_type=file`, `baseline_hash` | `hash_changed` | none |
| `symbol_moved` | `target_node_type=symbol`, `baseline_ref` | `ref_changed` | none |
| `symbol_removed` | `target_node_type=symbol`, `baseline_ref` | `ref_missing` | none |
| `command_changed` | `target_node_type=command`, `baseline_hash` or `baseline_ref`; compare to `command_states.command_hash/state` | `hash_changed` | `ref_changed` |
| `verifier_changed` | verifier ref/result `baseline_hash` or `baseline_value`; compare to `verifier_results.result_hash/result_value/observed_at` | `hash_changed` | `value_changed` |
| `branch_changed` | branch `baseline_value` | `value_changed` | none |
| `task_contract_changed` | task contract `baseline_ref` or `baseline_hash`; compare to `task_contract.ref/hash/value/observed_at` | `hash_changed` | `ref_changed` |
| `reviewer_vetoed` | reviewer/approval `baseline_observed_at`; newer `authority_events` with reviewer source, target scope, and supersession refs | `any_newer_authority` | none |
| `user_preference_updated` | user authority `baseline_observed_at`; newer `authority_events` with user source and matching target scope | `any_newer_authority` | none |
| `policy_superseded` | policy/authority `baseline_observed_at`; newer `authority_events` from maintainer/system/verifier with supersession refs | `any_newer_authority` | none |
| `procedure_failed_recently` | applicability/task/error target plus `baseline_observed_at`; newer `verifier_results` with `result_value=fail|error` and matching `applicability_refs`, `task_ref`, or `error_signature_refs` | `any_newer_failure` | `newer_evidence` |
| `manual` | `manual_reason` | `manual_only` | none |

Validation rejects mismatched combinations, such as `file_hash_changed` with `any_newer_authority`, missing baselines for hash/ref/value policies, authority policies without `baseline_observed_at`, `procedure_failed_recently` without `baseline_observed_at`, or `manual` without `manual_reason`。

#### `staleness_state`

```text
fresh | maybe_stale | stale | superseded
```

Rules:

- `stale` and `superseded` are blocked from normal projection。
- `maybe_stale` may be projected only with explicit caution and evidence。

#### `contradiction_state`

```text
none | possible | contradicted | resolved
```

Rules:

- `contradicted` is blocked from normal projection unless task asks for historical debugging。
- contradiction checks must compare against current repo evidence and existing cards。
- `possible -> resolved` requires either a superseding committed card, a manual/debug approval that records why the contradiction is no longer active, or new current evidence that invalidates the older contradictory claim。
- resolved cards may re-enter normal recall only when `approval_state=committed`, `staleness_state=fresh|maybe_stale`, and the resolution audit event cites the resolving evidence。Resolved history remains inspectable through audit/debug surfaces。

#### `approval_state`

```text
candidate | proposal | approved | committed | rejected | superseded | tombstoned
```

Rules:

- only `committed` cards are normal recall candidates。
- `approved` but not `committed` is not durable recallable memory。
- `tombstoned` cards remain audit-visible but not recallable as active evidence。

Legal state transitions:

```text
candidate -> proposal -> approved -> committed
candidate -> rejected
proposal -> rejected
approved -> rejected
committed -> superseded
committed -> tombstoned
superseded -> tombstoned
rejected -> terminal
tombstoned -> terminal
```

Forbidden normal transitions:

```text
rejected -> committed
tombstoned -> committed
superseded -> committed
candidate -> committed
```

`candidate -> committed` is forbidden for ordinary debug/manual/core operation. The only allowed direct bypasses are:

- `seed_eval` fixture setup by `actor=adapter|scoring`, with public operation input, fixture authority, support refs, and `memory_audit_log.operation=seed_eval`。
- schema migration by explicit `actor=migration`, with source schema version, target schema version, migrated IDs, rejected IDs, source refs, and `memory_audit_log.operation=migrate`。
- emergency restore that creates a new card revision/lineage entry, never a state reversal of the old card, with `memory_audit_log.operation=rollback|commit` and the restored source material cited。

Ordinary debug/manual approval must still record proposal -> approved -> committed audit events, even if a UI offers a single "approve and commit" command. The UI may collapse the command, but the durable lifecycle and audit log must not collapse the state transitions.

#### `projection_mode`

```text
ProjectionMode =
hidden | debug_only | recalled_tool_result | context_packet | prompt_section | always_on_core
```

Rules:

- default for durable cards should be `debug_only` or `recalled_tool_result` until later projection phases。
- `prompt_section` and `always_on_core` require separate prompt/projection gates。
- `projection: ProjectionPolicy` is retired terminology. Stored schema, hashes, and adapter artifacts use `projection_mode: ProjectionMode` only。

#### `graph_refs`

```yaml
GraphRefs:
  node_ids: list[string]
  edge_ids: list[string]
```

Rules:

- graph refs are index/expansion references。
- `graph_refs` may be empty in Phase B. Empty refs mean structured filters plus summary-search backend retrieval only, not an invalid card。
- when present, refs must resolve to canonical `graph_nodes` / `graph_edges`; unresolved expanding refs fail validation for committed cards。
- graph is never the only proof; role-bearing evidence links remain required for durable cards。

#### `privacy/sharing rules`

```yaml
PrivacyRules:
  sharing: private | project | team | shared
  allowed_scope_ids: list[string]
  redaction_policy: none | redact_payload | refs_only | restricted
  user_visible_editing: disabled | enabled_later
```

Rules:

- sharing defaults to narrow。
- user memory and project memory remain isolated unless explicit sharing exists。
- `sharing=team|shared` does not override `allowed_scope_ids`; it only widens the candidate audience inside the allowed scope set。
- `allowed_scope_ids` stores canonical `scope_key` values such as `scope:v1:<level>:<digest16>`, not `Scope.namespace`, display names, or graph scope node IDs。
- an entry may alternatively be an explicitly versioned shared-scope policy ID, `shared_policy:v1:<stable-id>`, only when the policy resolver maps it to concrete canonical scope keys before recall filtering。
- privacy matching compares deterministic scope keys derived from canonical `Scope` JSON; non-canonical or unresolvable entries fail closed。
- a matching memory `scope` never bypasses privacy. Recall must apply the privacy/sharing gate before caller authorization, scope matching, applicability, or ranking。

#### timestamps

```text
created_at
updated_at
last_verified_at
superseded_at
tombstoned_at
```

Rules:

- `updated_at` must not hide history; revisions/supersession must remain inspectable。
- tombstone and supersede are preferred over destructive deletion when audit is needed。

### Usage statistics boundary

Recall may append `memory_audit_log` events, but it must not alter semantic `memory_cards` fields. The fields `summary`, `details`, `scope`, `authority`, `valence`, `applicability`, `evidence_links`, `invalidators`, `staleness_state`, `contradiction_state`, `approval_state`, `projection_mode`, `privacy`, and revision data are semantic state and cannot change during retrieve.

Usage counters are derived from audit, or stored in a separate rebuildable aggregate:

```yaml
MemoryCardUsageStats:
  card_id: string
  last_recalled_at: datetime | null
  recall_count: int
  last_used_successfully_at: datetime | null
  last_misuse_at: datetime | null
  source_audit_event_ids: list[string]
```

`MemoryCardUsageStats` is not authoritative memory. If an implementation materializes it for speed, it must be rebuildable from `memory_audit_log` and excluded from semantic card hashes.

---

## 8. Provenance model

### Principle

Raw artifacts are evidence, not durable memory by default。

```text
raw transcript / tool log / verifier output / reviewer comment / diff
  -> provenance_events
  -> candidate/proposal
  -> approved MemoryCard
  -> committed MemoryCard
```

### Provenance sources

| Source | Stored as | Durable memory by default? |
| --- | --- | --- |
| conversation turn | `provenance_event` | No |
| tool call / command output | `provenance_event` | No |
| verifier output | `provenance_event` | No |
| reviewer comment | `provenance_event` | No |
| diff / patch | `provenance_event` | No |
| file snapshot/hash | `provenance_event` or graph node metadata | No |
| user approval | `provenance_event` + authority source | No, but can authorize card |
| memory proposal | `provenance_event` | No |
| adapter/scoring fixture setup | `provenance_event(actor=adapter|scoring)` / `ProvenanceRef.producer=adapter|scoring` | No, but can authorize `seed_eval` fixture cards when public setup ops allow it |
| schema migration receipt | `provenance_event(actor=migration)` / `ProvenanceRef.producer=migration` | No, but can support migration lineage/audit |

### Required rules

- Durable memory cards cite provenance via role-bearing `evidence_links`。
- No raw transcript injection into `summary` / `details` by default。
- Reviewer prose must not become unconditional instruction; it becomes evidence and possibly `authority.source=reviewer` after extraction and approval。
- Tool output must not become broad fact without validation and scope assignment。
- Provenance deletion/rollback must be possible; cards depending on removed provenance must be tombstoned, redacted, or downgraded。
- Audits must answer: which provenance created this card, who approved it, when it was last verified, and why it was projected or dropped。
- Fixture/public experience identity must be preserved: provenance from harness ingest records `source_experience_id` directly when provided, or derives it deterministically from `source_run_id` + `source_turn_id` only when the fixture schema explicitly allows that derivation。

### Raw transcript extraction safeguards

Raw transcript and similar raw event kinds are high-risk provenance, not durable card prose:

- `summary` max is 512 chars and `details` max is 4096 chars by default for committed cards。
- `details` must be synthesized by an extractor and must not be a direct transcript payload。
- direct quotes/excerpts longer than 240 chars require `provenance_excerpt` on the provenance event and an evidence link from the card。
- `event_kind=transcript_turn` / `raw_transcript` cannot be copied into `details` without an explicit extractor marker, extractor version, and cited event ID。
- validation must reject committed cards that preserve speaker labels, turn-by-turn logs, or raw tool dumps in `summary`/`details` instead of extracted claims。
- raw transcript leakage failures are schema/gate failures, not ranking issues。

### Provenance ref shape

```yaml
ProvenanceRef:
  ref_id: string
  event_kind: transcript_turn | tool_call | command_output | verifier_output | reviewer_comment | diff | file_snapshot | user_instruction | approval | memory_proposal | other
  artifact_path_or_uri: string | null
  content_hash: string
  excerpt_hash: string | null
  timestamp: datetime
  producer: user | assistant | tool | verifier | reviewer | maintainer | system | adapter | scoring | migration
  scope: Scope
  redaction_state: none | redacted | restricted
  source_experience_id: string | null
  source_mutation_id: string | null
```

### Provenance store API

Conceptual API:

```text
ingest_raw(request: RawMemoryIngestRequest) -> RawIngestResult
capture_provenance(request) -> ProvenanceReceipt
inspect_provenance(refs, actor, scope) -> ProvenanceInspectionResult
redact_provenance(refs, policy, actor) -> ProvenanceRedactionReceipt
delete_or_forget_provenance(refs, policy, actor) -> ProvenanceDeletionReceipt
rollback_provenance(refs, reason, actor) -> ProvenanceRollbackReceipt
```

Raw ingress is intentionally string-first:

```yaml
RawMemoryIngestRequest:
  raw_text: string
```

Rules:

- `RawMemoryIngestRequest` has no public `hint`, `event_kind`, `scope`, `actor`, `intent`, file list, command list, or authority field in v1。
- Callers may send ambiguous natural language. Usability is preferred at the raw ingress boundary; requiring rich hints would move extraction responsibility to the caller and create hallucination-prone pseudo-structure。
- The trusted runtime/session envelope may attach caller identity, current task/session IDs, default scope, source run/session/turn IDs, and auth context, but those are not user-supplied hints and are not treated as extracted memory facts。
- The LLM extractor may infer event kind, scope, actor, applicability, authority candidate, and candidate shape from `raw_text` plus trusted runtime context。All inferred fields are proposal material with confidence/provenance, not durable truth。
- The extractor-proposed scope may narrow a proposal inside the trusted runtime scope, add applicability annotations, or request clarification。It must not broaden scope, switch namespace, change `user_id`, change `repo_ref`, or create `team` / `shared` scope。
- When the trusted runtime/session envelope marks runtime scope as authoritative, any extracted scope mismatch becomes a proposal warning/audit drop reason and is not stored as the card scope。
- `ingest_raw` must not create committed cards directly。It may create provenance and candidate/proposal records; committed memory still requires the normal proposal/approval/commit path or explicit public `seed_eval` fixture setup。
- If extraction is ambiguous, the system should preserve the raw text as provenance and stop at low-confidence candidate/proposal, rejection, or clarification-needed state rather than inventing structured hints。

LLM extractor model binding:

- The default raw-memory extractor uses the existing mew model backend abstraction, not a new direct provider client。
- Default backend is `codex`; default extraction model is `gpt-5.5`, matching existing memory-compression / short-term-memory model defaults。
- Auth is loaded through the existing model auth path mechanism. The CLI/default path is `auth.json` with the existing fallback behavior owned by `load_model_auth`; the subsystem records only the auth path / config hash needed for audit, never token contents。
- The extractor call path should use the same `call_model_json` / injected `ModelJsonCaller` pattern used by existing mew model-backed memory utilities so retries, fake callers, replay, and tests do not drift。
- Harness/conformance tests must not depend on live `gpt-5.5` calls. They should inject deterministic extractor payloads or replay artifacts while still checking that production configuration defaults resolve to `codex` + `gpt-5.5` + `auth.json`-style auth loading。

`ProvenanceReceipt` maps directly to `provenance_events`:

```yaml
ProvenanceReceipt:
  event_id: string
  event_kind: string
  scope: Scope
  payload_hash: string
  excerpt_hash: string | null
  source_experience_id: string | null
  source_mutation_id: string | null
  redaction_state: none | redacted | restricted
  retention_state: active | pending_delete | deleted
  audit_id: string
```

Rules:

- provenance is append-oriented: normal redaction/deletion records tombstone/redaction events and changes authorized visibility; it does not silently rewrite historical audit。
- physical deletion is allowed only for privacy/security retention policy and must leave a redacted internal audit tombstone with non-sensitive hashes/IDs needed for rollback accounting。
- rollback means "this provenance should no longer support active memory"; it marks dependent cards `maybe_stale`, `tombstoned`, or `rejected` according to approval state and records affected card IDs in audit。
- inspect is authorization-aware; it may return hashes and redacted metadata without payload/excerpts。
- caller-visible provenance refs must never be exposed for privacy-blocked, forgotten, or out-of-scope cards。

---

## 9. Write path

### Strict v0/v1 rule

M6.25 v0/v1 の durable write rule は以下で固定する。

```text
model may propose memory candidates
model must not directly commit durable memory
durable commits require core/debug/scoring approval path
```

Provider-visible write tools are out of scope。

### Write path phases

| Step | Operation | Output | Gate |
| --- | --- | --- | --- |
| 1 | capture provenance | `provenance_event` | raw material stored as evidence only。 |
| 2 | extract candidate | `MemoryCandidate` | may be model-assisted or deterministic。not durable。 |
| 3 | type assignment | candidate.kind | one of 5 storage kinds。 |
| 4 | facet assignment | scope, lifecycle, authority, valence, evidence, invalidators | required fields present。 |
| 5 | deduplicate | merged/split candidate | no broad mixed claims。 |
| 6 | contradiction/staleness checks | state decision | compare current repo evidence, existing cards, invalidators。 |
| 7 | approval gate | approved/rejected proposal | core/debug/scoring/user/reviewer path。 |
| 8 | commit/supersede/tombstone | committed card / revision | auditable and reversible。 |
| 9 | graph/index update | conditional graph edges + retrieval index | graph writes only when graph material is present; bounded index only。 |
| 10 | audit log | write trace | request hash, result hash, actor, reasons。 |

Commit atomicity invariant:

```text
commit/supersede/tombstone transaction =
  memory_cards state change
  + conditional graph_nodes creation/update when graph_refs, graph-derived material, or explicit graph writes are present
  + conditional graph_edges creation/update when graph_refs, graph-derived material, or explicit graph writes are present
  + Phase B synchronous simple index rebuild/refresh when enabled
  + Phase D derived index refresh or invalidation marker when graph index is enabled
  + memory_audit_log event with result_hash
```

If any authoritative store write fails, the transaction rolls back or leaves a recoverable pending transaction record that normal recall treats as non-committed. In Phase B, absent `graph_refs` are a valid no-op for graph writes; lexical/direct-scan indexing and audit still remain transactional. If `graph_refs` are present, canonicalization and endpoint validation are required inside the transaction, and invalid graph refs reject the commit before the card becomes normal-recallable. In Phase B, any lexical/BM25 index is rebuilt synchronously or recomputed by direct scan. Asynchronous index invalidation is Phase D-only and is allowed only if the authoritative transaction records an index-invalid marker and recall either rebuilds/refreshes before use or ignores stale index entries by rechecking `memory_cards`.

### Conceptual API boundary

```text
MemorySystem.ingest_raw(request: RawMemoryIngestRequest) -> RawIngestResult
MemorySystem.capture_provenance(request) -> ProvenanceReceipt
MemorySystem.extract_candidate(request) -> CandidateResult
MemorySystem.propose_memory(request) -> ProposalResult
MemorySystem.approve_memory(request) -> ApprovalResult
MemorySystem.commit_memory(request) -> CommitResult
MemorySystem.mutate_memory(request) -> MutationResult
MemorySystem.recall(request) -> RecallResult
MemorySystem.expand_chain(request) -> ChainResult
MemorySystem.trace(event: MemoryTraceEvent) -> AuditReceipt
```

Exact method names may vary, but semantics must preserve candidate/proposal/approval/commit separation。

`MemorySystem.trace(event)` is not an extra memory-write channel. It accepts structured audit-only events:

```yaml
MemoryTraceEvent:
  operation: capture_provenance | extract_candidate | propose | approve | commit | mutate | retrieve | expand | project | report_usage | migrate | rollback | seed_eval | retrieve_transient
  request_hash: string
  result_hash: string
  actor: core | debug | scoring | adapter | model_proposal | user | reviewer | maintainer | verifier | migration | system
  card_ids: list[string]
  provenance_event_ids: list[string]
  mutation_ids: list[string]
  dropped: list[DroppedReason]
  usage: Usage
  metadata: object
```

It appends to `memory_audit_log`; it must not mutate `memory_cards`, `provenance_events`, `graph_nodes`, or `graph_edges` except through the named write APIs above.

`MemoryTraceEvent` follows the audit payload boundary: pass IDs/hashes/counts/reasons and bounded metadata only. Raw transcript chunks, raw command output, full diffs, full projected packets, or complete context packets must be captured as provenance and referenced by `provenance_event_ids` / hashes, not embedded in audit.

### Candidate shape

```yaml
MemoryCandidate:
  candidate_id: string
  proposed_kind: MemoryCardKind
  summary: string
  details: string | null
  proposed_retrieval_terms: list[string]
  evidence_links: list[EvidenceLink]
  proposed_scope: Scope
  proposed_authority: Authority
  proposed_valence: Valence
  proposed_applicability: Applicability
  proposed_invalidators: list[Invalidator]
  confidence: float
  write_reason: string
  proposed_by: model | deterministic_extractor | user | reviewer | debug | scoring | adapter
```

Candidate confidence uses the same `[0.0, 1.0]` range and 4-decimal canonical hash rounding as card and graph-edge confidence.

`proposed_retrieval_terms` uses the same validation and de-duplication rules as committed `MemoryCard.retrieval_terms`. Candidate extraction, deterministic replay fixtures, model proposals, public adapter ingest, and migration must preserve it through proposal/approval/commit or record an audit-visible reason for dropping/changing it.

### Normal ingest and privileged eval seeding

Normal ingest must not bypass governance:

```text
ingest_experience(experience)
  -> capture_provenance(source_experience_id=experience.id)
  -> extract_candidate/propose_memory
  -> optional approval decision
  -> commit only through normal approval/commit path
```

Rules:

- normal `ingest_experience` creates provenance and candidates/proposals; it does not directly create committed cards。
- fixture experiences become committed cards only when the public operation sequence contains an explicit `seed_eval`, `approve`, or `commit` operation, or when the normal approval path is exercised as part of the public operation sequence。
- stale/non-retrievable experiences are represented as provenance plus candidate/proposal, rejected/tombstoned cards, or committed cards with stale/superseded state according to the fixture operation; they are not silently dropped if scoring needs support lineage。
- `support_experience_ids` are preserved by `provenance_event.source_experience_id` and never inferred from card IDs。

Privileged eval seeding:

```text
seed_committed_card_for_eval(seed_request) -> CommitResult
```

Allowed only for deterministic fixture setup:

- actor must be `adapter` or `scoring`。
- authority source must be recorded as `scoring` or another explicit fixture-setup source, not user/reviewer unless the fixture includes public provenance for that authority。
- every call records `memory_audit_log.operation=seed_eval` with `source_experience_id`, public operation ID, request hash, result hash, and committed card IDs。
- seed input must not include gold labels, trap families, expected answers, scorer view, or hidden fixture mode。
- seeded committed cards still need provenance events, source experience IDs, approval state, authority, result hash, and audit entries。
- seeded cards must be audit-distinguishable from normally committed cards, but ranking-equivalent: core ranking and recall cannot use the fact that a card was seeded。
- ranking code must not read `memory_audit_log.operation=seed_eval` or any derived seeded/not-seeded flag。Ranking inputs are limited to committed card fields after governance filtering and derived retrieval scores; any use of seed-eval audit metadata in ranking is a conformance failure。
- hidden reset seeding is forbidden for P0/P1 scoring fixtures。If a fixture needs retrievable memory before a query, the seed/approve/commit operation must be public and included in public operation/prefix hashing。

### Approval actors and authority

Actors are who performs an operation. Authority is why the card is allowed to carry force. They usually match but are not identical:

- matching example: `actor=reviewer`, `authority.source=reviewer`, source ref is reviewer comment provenance。
- delegated example: `actor=adapter`, `authority.source=scoring`, source ref is fixture seed provenance, allowed only in `seed_committed_card_for_eval`。
- forbidden example: `actor=model_proposal`, `authority.source=user`, without a user provenance event。

Approver matrix:

| Kind / operation | Candidate/proposal actor | Approve actor | Commit actor | Authority requirements |
| --- | --- | --- | --- | --- |
| transient `reentry_snapshot` session state | core/session gate/model proposal | core/session gate | not a durable commit | session evidence; separate from `memory_cards`。 |
| promoted durable `reentry_snapshot` | core/session gate/debug | core/debug/scoring | core/debug/scoring | scoped provenance; no raw transcript payload。 |
| `task_episode` | model proposal/deterministic extractor/adapter | core/debug/scoring/reviewer | core/debug/scoring | public task evidence and success/failure status。 |
| `semantic_fact` | deterministic extractor/model proposal/adapter | debug/scoring/verifier/reviewer/maintainer | core/debug/scoring | repo/doc/verifier/reviewer/maintainer evidence and invalidators。 |
| `procedure` | deterministic extractor/model proposal/reviewer | debug/scoring/verifier/reviewer/maintainer | core/debug/scoring | successful use or verifier/reviewer/maintainer approval plus applicability/prerequisites。 |
| failure-shield-like negative content | deterministic extractor/model proposal/reviewer | debug/scoring/verifier/reviewer/maintainer | core/debug/scoring | negative valence, bounded applicability, counterexamples/invalidators。 |
| `policy_or_preference` | user/reviewer/maintainer/system/debug | user/reviewer/maintainer/debug | core/debug/scoring/maintainer | explicit authority provenance; user scope for user preference; project/team/shared requires maintainer/reviewer authority。 |

`must` authority requires user, maintainer, system, or explicit reviewer policy provenance. It still remains memory-local evidence after governance filtering and must not become a system/developer instruction.

### Approval gate requirements

| Kind | Required before commit |
| --- | --- |
| `reentry_snapshot` | transient: provenance refs and scope; durable: approval or deterministic gate。 |
| `task_episode` | evidence links; task shape; success/failure status; scope。 |
| `semantic_fact` | repo/doc/verifier/reviewer/maintainer evidence; invalidators。 |
| `procedure` | successful use or verifier/reviewer/maintainer approval; prerequisites; invalidators。 |
| `policy_or_preference` | explicit user/reviewer/maintainer/system source; scope; strength。 |

### Mutation semantics

| Mutation | Meaning | Evaluation mapping |
| --- | --- | --- |
| `update` | same card lineage, content/facet correction。 | maps to harness `update`。support refs must remain inspectable。 |
| `delete` | excluded from normal retrieval; provenance/audit remain; authorized internal inspection may see deleted card/provenance according to policy。 | maps to harness `delete`。 |
| `forget` | privacy/security/user-driven removal; no normal retrieval, support IDs, caller-visible provenance, or context projection; payload redacted/deleted; only redacted internal audit tombstone allowed。 | maps to harness `forget`。must not appear in support ids。 |
| `supersede` | old card becomes superseded; replacement becomes active。 | maps to harness `supersede`。old must not be fresh support。 |
| `tombstone` | no longer active; remains for audit/rollback/supersession history; not normal recall。 | internal op; adapter-visible only when fixture has explicit tombstone/supersede semantics, otherwise reported as delete/supersede result。 |

Mutation operation schema:

```yaml
MemoryMutation:
  mutation_id: string
  op: update | delete | forget | supersede | tombstone
  target_card_id: string
  replacement_card: MemoryCard | null
  patch: object | null
  reason: string
  actor: core | debug | scoring | adapter | user | reviewer | maintainer
  authority_refs: list[provenance_event_id]
```

`mutate_memory` dispatch accepts typed ops only. Adapter-visible ops are `update`, `delete`, `forget`, and `supersede`; `tombstone` is primarily internal unless a fixture explicitly models tombstone behavior. Unsupported typed ops return structured unsupported results and must not silently succeed.

Redaction cascade:

- deleting a card marks it non-recallable, removes or invalidates retrieval index entries, keeps provenance/audit visible only to authorized inspection, and records dropped reason `deleted` internally。
- tombstoning a card marks it non-active, preserves lineage edges, keeps audit/rollback metadata, removes it from normal retrieval, and blocks it as fresh support。
- forgetting provenance redacts/deletes payload and caller-visible provenance refs, removes dependent cards from normal retrieval, tombstones or forgets graph nodes/edges that would reveal the forgotten fact, invalidates retrieval indexes, and leaves only redacted internal audit tombstones。
- if a provenance event is forgotten, dependent cards cannot expose `support_experience_ids`, provenance refs, graph edges, snippets, or context projections derived from it。
- if a graph node is forgotten or privacy-blocked, graph expansion must not reveal the node ID, canonical ref, display name, or adjacent edge IDs to unauthorized callers。

---

## 10. Read path

### Read path overview

```text
RecallRequest
  -> plan recall intent
  -> seed retrieval
  -> bounded graph expansion
  -> governance filtering
  -> ranking
  -> evidence packet projection later
  -> audit record
```

### RecallRequest schema

```yaml
RecallRequest:
  query: string
  scope: Scope
  intent_tags: list[string]
  current_evidence: CurrentEvidenceSnapshot
  limits:
    k: int
    max_projection_chars: int
    max_latency_ms: int | null
  caller:
    actor: core | debug | scoring | adapter | tool_provider | user
    authorization_scope: Scope
```

`current_evidence` is not memory. It is the fresh observed world used to invalidate, downgrade, or override memory.

```yaml
CurrentEvidenceSnapshot:
  repo_ref: string | null
  branch_ref: string | null
  commit_ref: string | null
  file_states: list[FileEvidenceState]
  symbol_states: list[SymbolEvidenceState]
  command_states: list[CommandEvidenceState]
  verifier_results: list[VerifierEvidenceResult]
  task_contract: TaskContractEvidence | null
  authority_events: list[AuthorityEvidenceEvent]

FileEvidenceState:
  node_id: string
  path: string
  state: present | missing | unknown
  content_hash: string | null
  observed_at: datetime | null

SymbolEvidenceState:
  node_id: string
  canonical_ref: string
  state: present | moved | missing | unknown
  content_hash: string | null
  moved_to: string | null
  observed_at: datetime | null

CommandEvidenceState:
  node_id: string
  normalized_command_ref: string
  command_hash: string | null
  state: present | changed | unknown
  observed_at: datetime | null

VerifierEvidenceResult:
  verifier_ref: string
  result_hash: string | null
  result_value: pass | fail | error | unknown
  applicability_refs: list[ApplicabilityRef]
  task_ref: string | null
  error_signature_refs: list[string]
  observed_at: datetime
  provenance_ref: string | null

TaskContractEvidence:
  ref: string
  hash: string | null
  value: string | null
  observed_at: datetime

AuthorityEvidenceEvent:
  ref: string
  source: user | reviewer | maintainer | system | verifier
  strength: observation | hint | should | must
  target_scope: Scope
  observed_at: datetime
  supersedes_refs: list[string]
```

Rules:

- `node_id` values must use the same canonical graph node ID conventions as `graph_nodes`。
- `state=unknown` never proves freshness; it can only avoid a hard stale decision when the invalidator policy allows uncertainty。
- `observed_at` drives newer-authority and newer-failure invalidators; request construction must not substitute wall-clock time when no evidence was observed。
- `VerifierEvidenceResult.applicability_refs`, `task_ref`, and `error_signature_refs` are the deterministic target keys for `procedure_failed_recently`; a failure result without at least one target key cannot invalidate a procedure card。
- `authority_events` are current evidence for preference, reviewer, policy, and verifier authority changes. They are not durable authority unless separately captured as provenance and approved。
- `AuthorityEvidenceEvent.source` intentionally excludes `scoring`。Scoring authority is fixture setup authority only and is not valid current-world evidence. This does not conflict with `provenance_event.actor=scoring` / `ProvenanceRef.producer=scoring`, which are allowed only for seed/eval provenance and auditability。

### Step 1: plan recall intent

Recall intent should be internal and evidence-oriented, not a planner action。

```text
resume_task
find_project_fact
reuse_prior_episode
consider_procedure
avoid_repeated_failure
apply_policy_or_preference
locate_related_file_symbol_test_error
```

Intent tags are retrieval/ranking/audit tags only. Negative example: `avoid_repeated_failure` may raise negative-valence cards and procedures for consideration, but it must not tell the planner "do not edit this file" or "run this command next"。

### Step 2: seed retrieval

Initial retrieval should be deterministic or replayable, inspectable, and backend-injected.

Phase B seed retrieval uses structured filters plus a `SummarySearchBackend` over committed typed-card summary surfaces. The first implementation may use direct scan or a synchronously rebuilt simple lexical/BM25 backend as a deterministic baseline, but lexical/BM25 is not the architectural commitment. Vector or hybrid summary search can replace it after memory eval shows better recall/precision, provided the backend is artifacted and replayable for gated evaluation:

```text
structured filters:
  scope
  kind
  lifecycle
  approval_state=committed
  staleness_state allowed set
  contradiction_state allowed set
  authority minimum

summary search surfaces:
  summary
  details
  retrieval_terms
  applicability.applies_to
  applicability.prerequisites
  error_signature refs
  file/symbol refs
```

The backend boundary is narrow:

```yaml
SummarySearchBackend:
  input:
    query: string
    authorized_cards: list[MemoryCard]
    surface_config: RetrievalSurfaceConfig
    limit: int
  output:
    hits: list[SearchHit]

SearchHit:
  card_id: string
  backend_score: CanonicalScore
  score_components: map[string, CanonicalScore]
  matched_fields: list[string]
  backend_id: string
  backend_artifact: map[string, string]
```

Supported backend families:

- `direct_scan_lexical` / `bm25`: deterministic baseline and exact-anchor fallback。
- `vector`: summary embedding search over authorized typed-card surfaces。
- `hybrid`: vector summary search plus exact/lexical `retrieval_terms` anchors。
- `replay`: deterministic replay of a captured backend artifact for hermetic eval。

`SummarySearchBackend` owns only candidate scoring over already-authorized card surfaces. It does not own privacy, scope, support semantics, evidence-link promotion, forget/redaction policy, approval state, or final projection.

Memory eval should be able to run the same fixtures and recall requests against different summary-search backends. Backend selection is runtime/eval configuration, not hard-coded product behavior:

```text
summary_search_backend=direct_scan_lexical
summary_search_backend=bm25
summary_search_backend=vector
summary_search_backend=hybrid
summary_search_backend=replay
```

Score composition remains backend-independent:

```text
score = structured_match
      + summary_backend_score
      + optional_anchor_score
      + optional_reranker_score
      + authority/freshness/confidence modifiers
```

### Short-term hybrid recall/search tooling boundary

The next recall/tooling design slice is short-term memory recall, not long-term memory consolidation. It may read active session/reentry state and committed typed `MemoryCard` records through governed recall paths, but it does not introduce autonomous long-term writes, consolidation, or prompt injection.

Chosen direction:

```text
natural-language question
  -> memory_semantic_search over governed typed-card surfaces
  -> memory_context_grep over candidate transformed search docs for exact verification
  -> optional graph expansion from governed seeds / evidence packet after governance gates
```

This is not plain RAG, not pure GraphRAG, and not unbounded agentic grep. It is a bounded hybrid: deterministic/governed candidate generation over approved memory surfaces, plus optional agentic verification tools whose search space is candidate-limited by default and audit-visible.

Semantic recall/search rules:

- Phase B/D introduce internal candidate generation first: `memory_semantic_search_internal` is broad recall from Google-like natural-language text over governed typed-card surfaces. Adapter `retrieve(query)` may use this internal candidate generator before any LLM-visible tool exists.
- Phase F may expose `memory_semantic_search` as a provider-visible LLM tool, default-off, after core retrieval and adapter artifacts are already stable.
- `memory_semantic_search_internal` / `memory_semantic_search` use the injected `SummarySearchBackend`. The backend may be lexical/BM25, vector, hybrid, replay, reranking, or RAG-like candidate generation only over synthesized/typed `MemoryCard` surfaces.
- summary search method is intentionally swappable. Lexical/BM25 may be the first deterministic baseline; vector or hybrid may become the preferred/default backend if memory eval shows better top-k recall, top-1 precision, scope safety, and support correctness.
- Searchable card surfaces are `summary`, synthesized `details`, `retrieval_terms`, applicability refs, and graph refs/features when authorized and relevant. The exact included fields must be visible in score/debug artifacts.
- `retrieval_terms` remain useful even when vector summary search is primary: they provide exact anchors for names, IDs, paths, commands, errors, company names, and relation/value phrases that embedding search can miss. Any lexical/BM25 or hybrid backend must be `retrieval_terms`-aware, but weights must come from a hash-covered retrieval surface config rather than benchmark-specific phrase boosts.
- semantic search must not index or retrieve directly from raw transcript payloads, raw tool output, full diffs, raw reviewer comments, or unrestricted provenance payloads.
- `raw_text` / `provenance_events` remain the source of truth for support, audit, privacy, forget, and re-extraction. They are not public search surfaces.
- candidate generation must be authorization-prefiltered. Lexical/BM25/vector/semantic retrieval may score only cards that pass the first three recall visibility gates: privacy/sharing, caller `authorization_scope`, and coarse memory scope. Applicability and governance/staleness/contradiction still run later in the normal recall gate order before projection.
- unauthorized cards must not contribute candidate IDs, score components, hit counts, usage-visible dropped IDs, timing/debug explanations, or vector/semantic nearest-neighbor artifacts.
- if semantic retrieval uses vector embeddings, generated passages, BM25 fields, or reranker prompts, those derived artifacts are rebuildable indexes over the typed-card surface only and are never authoritative memory.

Implementation ticket boundary for authorization-prefiltered retrieval:

```yaml
coarse_visibility_filter:
  input:
    - committed MemoryCard ids
    - caller identity and authorization_scope
    - requested Scope
  gates:
    - privacy/sharing
    - caller authorization_scope
    - coarse memory scope
  output:
    - visible_card_ids

candidate_generation:
  input:
    - visible_card_ids
    - query
    - RetrievalSurfaceConfig
    - SummarySearchBackendIdentity
  rule: lexical/BM25/vector/semantic backends may score only visible_card_ids
  vector_rule: authorized shard or authorized candidate-set first; never global top-k then drop unauthorized hits

post_filter:
  gates:
    - applicability
    - staleness
    - contradiction
    - invalidators
    - budget
  output:
    - projected caller-visible results
    - privacy-safe dropped_count_by_reason
```

This split is an implementation requirement, not just a conceptual ordering. Vector indexes may be physically global for storage efficiency only if the query path applies an authorization-filtered shard, bitmap, allowlist, or equivalent candidate-set before nearest-neighbor scoring and before any debug/timing/hit-count artifact is produced.

Searchable surface identity:

```yaml
RetrievalSurfaceConfig:
  included_fields:
    - summary
    - details
    - retrieval_terms
    - applicability.applies_to
    - applicability.prerequisites
    - graph_refs.node_ids
    - graph_refs.edge_ids
  field_weights: map[string, CanonicalScore]
  tokenizer_id: string
  normalizer_id: string
  stopword_policy_id: string
  surface_config_hash: string
```

`RetrievalSurfaceConfig` is part of retrieval/index artifact identity. It separates "which card surface was indexed" from ranking-weight changes, so a regression can distinguish extraction/surface drift from scoring changes. `surface_config_hash` must be recorded with lexical/BM25/vector/reranker artifacts, retrieve result metadata, and replay fixtures.

Summary-search backend identity:

```yaml
SummarySearchBackendIdentity:
  backend_kind: direct_scan_lexical | bm25 | vector | hybrid | replay
  backend_version: string
  surface_config_hash: string
  backend_config_hash: string
  embedding_provider: ollama | openai | local_file | none
  embedding_model_id: string | null
  replay_artifact_id: string | null
```

Every retrieve artifact records `SummarySearchBackendIdentity`. Backend identity lets memory eval compare lexical/BM25, vector, hybrid, and replay modes without changing the governance, support, projection, or scoring artifact contract.

Optional vector/reranker identity:

```yaml
VectorIndexIdentity:
  embedding_provider: ollama | openai | local_file
  embedding_model_id: string
  embedding_config_hash: string
  index_snapshot_hash: string
  corpus_surface_hash: string

RerankerIdentity:
  reranker_model_id: string
  prompt_or_config_hash: string
  replay_artifact_id: string | null
  deterministic_mode: bool
```

Vector/reranker use is allowed only behind deterministic or replayable artifacts for P1-style scoring. A non-deterministic reranker may produce debug diagnostics or opt-in live smoke artifacts, but it must not be a direct hermetic CI gate for deterministic P1 scoring.

Initial local vector backend choice:

```yaml
summary_search_backend: vector
embedding_provider: ollama
embedding_model_id: qwen3-embedding:0.6b
```

`ollama` + `qwen3-embedding:0.6b` is the preferred first local vector candidate for Mac-class development because it is small enough for local iteration and gives multilingual/code-retrieval coverage. It is not a permanent product lock. Memory eval may still choose `direct_scan_lexical`, `bm25`, `hybrid`, `replay`, or a different embedding model if top-k recall, top-1 precision, scope safety, support correctness, latency, or reproducibility is better. Query embeddings and indexed card embeddings must use the same `embedding_provider`, `embedding_model_id`, and `embedding_config_hash`; changing any of them invalidates/rebuilds the vector index.

Exact verification rules:

- `memory_context_grep` provides exact verification after semantic recall proposes likely cards or docs. Its default mode is candidate-limited: it scans only `MemorySearchContextDoc` documents linked to candidate cards.
- global grep is allowed only by explicit request or failover policy, must be budgeted, must explain the fallback in audit, and still scans transformed search docs rather than raw payloads.
- grep must not scan raw text directly. It scans a redacted/normalized transformed document derived from raw material, for example:

```yaml
MemorySearchContextDoc:
  doc_id: string
  card_id: string
  source_provenance_refs: list[string]
  normalized_text: string
  line_index: list[LineIndexEntry]
  source_spans: list[SourceSpanRef]
  redaction_state: none | redacted | restricted
  scope: Scope
  privacy: PrivacyRules
  content_hash: string
  generated_at: datetime
```

`MemorySearchContextDoc` is derived, rebuildable, and governed. `normalized_text` is searchable only after redaction, scope filtering, and normalization; it is not a substitute for provenance. `source_spans`, support refs, line indexes, and `redaction_state` let exact matches be traced back to authorized evidence without exposing raw forgotten or restricted payloads. Forget/redaction of a source provenance event invalidates or regenerates every derived search-context doc that depends on it.

Grep support semantics are strict:

- a grep match is verification/localization evidence, not a support upgrade by itself.
- a grep match may be shown as verification only when the matched doc is linked to the candidate card, the candidate card has active `current_support`, the source span maps to authorized provenance, and that provenance is not forgotten, redacted, privacy-blocked, or out-of-scope.
- grep must not create new `support_experience_ids`, promote proof/debug provenance to current support, or rescue a card without active current-support evidence.
- grep can only confirm or localize support already reachable through the candidate card's active `current_support` links after governance filtering.

LLM-facing short-term tool interface shape:

```yaml
memory_semantic_search:
  purpose: broad semantic recall over governed card surfaces
  input:
    query: string
    scope: Scope
    k: int
    filters: object
  output:
    candidates: ranked MemoryCard summaries with card_id, why_recalled, score components, visible support refs, optional graph hints
    usage: Usage

memory_context_grep:
  purpose: exact verification over candidate MemorySearchContextDoc documents
  input:
    query_or_pattern: string
    candidate_card_ids: list[string]
    candidate_doc_ids: list[string]
    match_mode: literal | regex
    global_scan: bool  # default false; explicit/failover only
    max_matches: int
  output:
    matches: doc_id/card_id/line-range/redacted-snippet/source-span/support-ref records
    dropped_count_by_reason: map[string, int]
    usage: Usage

memory_report_usage:
  purpose: debug/eval-only usage report; not normal planning context
  input:
    scope: Scope | null
    window: object | null
  output:
    UsageReport
```

`memory_graph_expand` is optional future surface. Early phases may hide graph expansion behind `memory_semantic_search` result fields and score components instead of exposing a separate LLM tool. If exposed later, it must inherit Phase D graph bounds, governance filtering, and privacy-safe dropped counts.

Motivation from MemBench smoke:

- observed smoke failure: deterministic lexical ranking put the correct support at rank 6 for "What is the name of my niece's company?"
- the failure shows that budget-limited lexical ranking over card text can miss paraphrases and relationship bridges even when the correct support exists.
- the design response is to improve typed-card surface synthesis, retrieval anchors, semantic candidate generation, and exact governed verification. It must not add a narrow boost for "niece", "company", or any benchmark-specific phrase.
- evaluation must not stop at top-1 success. Relation-sensitive fixtures should include a positive support requiring niece + company + correct company name, plus distractors: niece but not company, company but unrelated to niece, same company name in a different user/scope, same name stale/superseded, and raw text match without active `current_support`.
- required evaluation dimensions are top-k recall, top-1 precision, scope safety, and support correctness using active `current_support` only.
- deterministic replay tests are the gating tests. Live `gpt-5.5` smoke is non-gating by default, runs only under `--allow-live-model-tests` or equivalent, and live failures open diagnostics without failing hermetic CI unless explicitly opted in.

### Step 3: bounded graph expansion

Graph expansion happens only after seed retrieval。

Current core request controls:

```text
expand_graph: false by default
summary_search_backend: default configured backend, e.g. direct_scan_lexical | bm25 | vector | hybrid | replay
graph_max_depth: 1 maximum in Phase D
graph_max_items: total node+edge expansion budget
graph_max_nodes: optional total expanded-node budget
graph_max_edges: optional total expanded-edge budget
graph_max_cards: optional graph-expanded card budget
graph_max_fanout: optional per-node edge fanout budget
graph_max_latency_ms: optional graph-expansion elapsed-time budget
max_projection_chars: optional returned evidence summary projection budget
```

The default summary-search backend may remain direct-scan/lexical for Phase C compatibility, but it is a configuration default rather than a design lock-in. Graph expansion is opt-in until graph fixtures, public adapter graph seeding, and derived index invalidation are complete.

Default initial limits:

```text
max_depth: 1 in Phase D
max_fanout_per_node: 8
max_total_nodes: 32
max_total_cards: 12
max_projection_chars: configured by caller
max_latency_ms: configured by caller/eval fixture
```

Useful expansion examples:

```text
error_signature -> task_episode -> procedure
file -> symbol -> test -> semantic_fact
reviewer correction authority -> policy_or_preference -> affected file family
procedure -> invalidator -> current verifier state
```

### Step 4: governance filtering

Filtering happens before projection。

Drop/downgrade reasons:

```text
out_of_scope
stale
contradicted
superseded
tombstoned
deleted
forgotten
missing_evidence
low_confidence
privacy_block
over_budget
authority_too_weak
invalidator_triggered
duplicate
raw_transcript_not_memory
```

Rules:

Recall visibility gate order is fixed:

1. privacy/sharing gate using `PrivacyRules.sharing` and `allowed_scope_ids`。
2. caller `authorization_scope` gate。
3. memory `scope` match。
4. `applicability` match。
5. governance/staleness/contradiction gate。
- stale/contradicted/out-of-scope memory is filtered before projection。
- internal audit may record dropped card IDs and provenance IDs。
- caller-visible results expose `dropped_count_by_reason` and may expose dropped IDs only for cards the caller is authorized to know exist。
- caller-visible results must never expose provenance refs for privacy-blocked, forgotten, or out-of-scope cards。
- `sharing=team|shared` does not widen `allowed_scope_ids`; the privacy gate compares canonical `scope_key` values, and a card whose memory scope matches the request still drops at the first gate if privacy blocks it。
- fresh repository evidence overrides memory。
- current user instruction overrides older user preference unless stronger policy applies。
- memory is evidence, not hidden instruction。

Invalidator evaluation protocol:

1. Build baseline refs/hashes from each card invalidator's stored `target_node_id`, `target_node_type`, `baseline_hash`, `baseline_ref`, `baseline_value`, and `baseline_observed_at`。
2. Build current refs/hashes/values from `RecallRequest.current_evidence: CurrentEvidenceSnapshot`。Every comparison uses canonical `node_id` or canonical ref identity; path/string fallbacks are allowed only when the invalidator was created before graph node canonicalization and must be audited as compatibility matching。
   Current evidence with `observed_at` older than `baseline_observed_at` cannot trigger newer-evidence or newer-authority policies; for direct hash/ref policies it downgrades to uncertainty unless the current state is a definitive `missing`/`moved` result。
3. Compare by invalidator kind:
   - `file_hash_changed`: find matching `file_states[].node_id` or path. `state=missing` triggers `ref_missing`; `state=present` with `baseline_hash != content_hash` triggers `hash_changed`; `state=unknown` records uncertainty and does not project as fresh unless another evidence source verifies freshness。
   - `symbol_moved` / `symbol_removed`: find matching `symbol_states[].node_id` or `canonical_ref`。`state=moved` triggers `symbol_moved` and records `moved_to`; `state=missing` triggers `symbol_removed`; changed `content_hash` may downgrade as maybe stale when policy allows `hash_changed`。
   - `command_changed`: find matching `command_states[].node_id` or `normalized_command_ref`。`state=changed` or `baseline_hash != command_hash` triggers `hash_changed`; changed normalized command ref triggers `ref_changed`。
   - `verifier_changed`: match `verifier_results[].verifier_ref` to `baseline_ref`。Different `result_hash` triggers `hash_changed`; different `result_value` triggers `value_changed` and may contradict prior pass/fail requirements。`observed_at` and `provenance_ref` are recorded in audit。
   - `branch_changed`: `baseline_value` branch differs from `current_evidence.branch_ref` unless card is repo/project scoped。
   - `task_contract_changed`: compare `task_contract.ref`, `task_contract.hash`, and `task_contract.value` to `baseline_ref`, `baseline_hash`, and `baseline_value`。A newer `task_contract.observed_at` with changed ref/hash/value triggers stale or out-of-scope according to the invalidator policy。
   - `reviewer_vetoed` / `user_preference_updated` / `policy_superseded`: scan `authority_events` where `observed_at > baseline_observed_at`, `target_scope` overlaps the card scope/applicability, source is authorized for the kind, and either `supersedes_refs` contains `baseline_ref` or the event targets the same policy/preference/reviewer authority ref。Matching events trigger `any_newer_authority`。
   - `procedure_failed_recently`: `trigger_policy=any_newer_failure` fires when newer `verifier_results` after `baseline_observed_at` have `result_value=fail|error` and at least one deterministic target matches the procedure card: overlap with the card's canonical applicability refs, matching `task_ref`, or matching `error_signature_refs`。Task-contract evidence can contribute only when `task_contract.ref` or `task_contract.value` maps to the same task/applicability target。`newer_evidence` may downgrade when newer relevant evidence exists but is pass/unknown rather than a failure。
4. Record internal dropped IDs and public counts by reason。
5. Prefer current repo/verifier/task/user evidence over memory whenever there is conflict。

Close tests must show fresh repo evidence, verifier output, task contract evidence, and current user instruction override older memory even when the older memory has high authority strength.

### Step 5: ranking

Recommended ranking signals:

| Signal | Description |
| --- | --- |
| task relevance | query/task text/file/error match。 |
| scope match | exact repo/branch/task/user match outranks broad shared。 |
| evidence strength | verifier/reviewer/user/maintainer evidence outranks self guess。 |
| freshness | fresh outranks maybe stale; stale blocked unless historical request。 |
| authority | `must` > `should` > `hint` > `observation`, subject to source。 |
| specificity | specific applies_to beats broad generic memory。 |
| prior success | successfully used procedure may rank higher。 |
| contradiction risk | possible contradiction lowers rank。 |
| compactness | shorter evidence packet preferred under budget。 |
| graph proximity | close graph relation after seed retrieval。 |
| retrieval anchors | concise `retrieval_terms` preserve raw discriminators omitted from synthesized prose。 |

Ranking must be deterministic. Final ordering tie-break:

```text
1. higher final_score
2. exact scope match over broader scope
3. higher authority strength after source validation
4. newer last_verified_at
5. shorter summary / lower projection cost
6. lexicographically smaller card_id
```

Ranking input boundary:

- ranking reads only governance-filtered committed card fields, graph/index features derived from authorized card/node/edge state, and request-local retrieval features。
- ranking may read `retrieval_terms` because they are committed card fields, but it must not read raw provenance payloads directly to rescue poor extraction。
- ranking must not read `memory_audit_log.operation=seed_eval`, setup route, fixture mode, gold/trap labels, or any audit-only seeded flag。
- seeded cards and normally committed cards with equivalent committed fields must rank equivalently。

Adapter/debug artifacts must expose score components:

```yaml
CanonicalScore: string  # decimal string matching -?(0|[1-9][0-9]*)\.[0-9]{4}; negative zero forbidden

score_components:
  structured_match: CanonicalScore
  lexical_score: CanonicalScore
  vector_score: CanonicalScore | null
  reranker_score: CanonicalScore | null
  scope_modifier: CanonicalScore
  authority_modifier: CanonicalScore
  freshness_modifier: CanonicalScore
  contradiction_modifier: CanonicalScore
  confidence_modifier: CanonicalScore
  graph_modifier: CanonicalScore
  budget_modifier: CanonicalScore
  final_score: CanonicalScore
score_type: deterministic_weighted_sum | lexical_only | structured_only | reranker
```

Scores are debug/eval signals; they must not replace hard governance filters.

Score canonicalization:

- every score component, item `score`, and `final_score` is serialized with fixed 4-decimal canonical rounding before `result_hash` calculation。
- non-null score fields must be finite。`NaN`, `Infinity`, and `-Infinity` are rejected before serialization and make the retrieve artifact invalid。
- canonicalization uses decimal arithmetic, not binary float stringification。Implementations should carry scores as decimal values or canonical decimal strings; if binary floats are used internally, they must be converted through a deterministic decimal path before artifact serialization。
- rounding mode is exactly `ROUND_HALF_UP` to four fractional digits, equivalent to quantizing by `0.0001` with half values rounded away from zero at the fourth decimal place。
- serialized score values are decimal strings with exactly four fractional digits, for example `0.0000`, `1.2300`, and `-0.1250`。Negative zero serializes as `0.0000`。
- this applies to ranked evidence artifacts, adapter retrieve result hashes, score debug artifacts, and golden artifact comparisons。
- numeric scores may be used internally, but adapter artifacts, result hashes, golden comparisons, and persisted/replayed reports must expose `CanonicalScore` strings rather than JSON numbers。
- implementations must compare canonicalized score strings for deterministic tests; raw floating-point intermediates are not artifact identity。

### Step 6: evidence packet projection later

Phase B retrieval result is not necessarily model-visible projection。Phase E introduces `MemoryContextBuilder` / evidence packet。

Projected evidence packet should include:

```text
memory_id
kind
summary
why_recalled
scope
authority
confidence
staleness_state
contradiction_state
evidence_links_by_role
applies_to
does_not_apply_to
prerequisites
counterexamples
recommended_effect: use | avoid | verify | ask | ignore
```

`recommended_effect` is evidence framing, not next action。

### Step 7: audit record

Every recall should log:

```text
request hash
scope
retrieval seed method
candidate card ids
expanded graph nodes/edges
dropped ids/counts/reasons
projected ids
usage: latency, item count, char count, read count
result hash
```

The audit record is not durable memory and must not be injected into prompts。

---

## 11. Evaluation adapter requirements

### Adapter placement

The generic memory eval adapter is the only layer that knows both harness schema and mew memory core schema。

```text
src/mew/memory_eval/adapters/memory_core.py or equivalent
  imports mew memory subsystem
  implements generic adapter contract

memory subsystem core
  does not import memory_eval harness
```

### Initially supported adapter methods

| Adapter method | Subsystem mapping | Notes |
| --- | --- | --- |
| `manifest()` | capability declaration | report support for retrieve, mutate ops, scope enforcement, usage。 |
| `reset(run)` | create clean fixture-scoped store/snapshot | use public fixture hash only; no gold。 |
| `ingest(items)` | create provenance events and candidates/proposals through normal ingest | fixture `Experience` maps to provenance support refs; no direct committed card creation。 |
| `setup(ops)` | apply public `ingest` / `seed_eval` / `approve` / `commit` setup operations | available only in `setup_method` routing mode; required before Phase C if P1 fixtures need committed memory before retrieve。 |
| `mutate(ops)` | update/delete/forget/supersede/tombstone | unsupported ops must be structured, not silent pass。 |
| `retrieve(query)` | call recall core | return ranked evidence refs with role-aware support mapping。 |
| `report_usage(scope?)` | aggregate audit usage | fixed latency/count/index fields below plus optional token/cost methodology。 |

`reset(run)` must not create hidden retrievable memory. Privileged fixture setup uses public operation-sequence items, not invisible reset side effects.

### Manifest routing contract

Adapter `manifest()` must include this top-level field:

```yaml
setup_routing: setup_method | mutate_lifecycle
```

Absence is a conformance failure unless a separately named legacy compatibility mode is explicitly defined by the generic harness. `setup_routing` participates in `capability_manifest_hash` / adapter config hash, not `public_fixture_hash`.

### Public operation wire forms

Lifecycle setup operation inputs use `LifecycleOp`. Execution outputs use `LifecycleReceipt`. These are separate wire records: `public_fixture_hash` includes only static adapter-visible fixture inputs, and operation/prefix hashes that cover lifecycle operations include `LifecycleOp` inputs only, never receipt-only IDs produced after execution.

```yaml
LifecycleOp:
  op_id: string
  lifecycle_type: ingest | seed_eval | approve | commit
  effective_time: datetime | null
  payload:
    experience_ids: list[string] | null
    seed_cards: list[SeedCardSpec] | null
    selectors: list[LifecycleSelector] | null
    approval_refs: list[string] | null
    reason: string | null

SeedCardSpec:
  kind: reentry_snapshot | task_episode | semantic_fact | procedure | policy_or_preference
  summary: string
  details: string | null
  retrieval_terms: list[string] | null
  scope: Scope
  applicability: Applicability
  current_support_experience_ids: list[string]
  authority: SeedAuthoritySpec
  confidence: float
  invalidators: list[Invalidator] | null
  valence: Valence | null

SeedAuthoritySpec:
  source: self | verifier | reviewer | user | maintainer | system | scoring
  strength: observation | hint | should | must
  public_source_experience_ids: list[string]
  public_approval_refs: list[string]

LifecycleSelector:
  source_op_id: string
  output_role: candidate | proposal | approved | committed_card | seeded_card
  index: int | null
  kind: MemoryCardKind | null
  source_experience_id: string | null

LifecycleReceipt:
  op_id: string
  lifecycle_type: ingest | seed_eval | approve | commit
  status: applied | unsupported | rejected
  status_reason: string | null
  audit_ids: list[string]
  result_hash: string
  provenance_event_ids: list[string]
  candidate_ids: list[string]
  proposal_ids: list[string]
  approved_ids: list[string]
  card_ids: list[string]
  mutation_ids: list[string]

RetrieveRequestEnvelope:
  request_id: string
  type: retrieve | request
  payload: RecallRequest-compatible public query
  request_hash: string
```

Rules:

- The old `AdapterOperation.type=mutate` envelope is retired for this design. Runtime mutations use `AdapterMutationOp` directly; lifecycle setup uses `LifecycleOp` input records。
- In `setup_method` mode, `setup(ops)` receives only `LifecycleOp` records。
- In `mutate_lifecycle` mode, `mutate(ops)` receives a union of `LifecycleOp | AdapterMutationOp` records。`AdapterMutationOp.mutation_type` remains limited to runtime mutations: `update | delete | forget | supersede | tombstone`。
- `setup(ops)` and `mutate(ops)` in `mutate_lifecycle` mode return ordered `LifecycleReceipt` records for lifecycle inputs; runtime `AdapterMutationOp` records return the normal mutation receipts/results。
- `LifecycleOp.lifecycle_type=ingest` is allowed only when the runner chooses to route ingest through the setup/lifecycle stream; otherwise public ingest continues to use `ingest(items)`。
- `seed_eval`, `approve`, and `commit` operation payloads are public fixture data and must be included in public operation/prefix hashes。
- `seed_eval` maps to `seed_committed_card_for_eval` and writes `memory_audit_log.operation=seed_eval`。
- `approve` maps to `approve_memory` and `memory_audit_log.operation=approve`。
- `commit` maps to `commit_memory` and `memory_audit_log.operation=commit`。
- unsupported lifecycle records return structured `LifecycleReceipt.status=unsupported` with `result_hash`; they must not silently pass。
- adapter conformance must define a single setup routing mode. Silent reset-time seeding is not allowed。
- `ingest` alone creates provenance/candidates/proposals. A P1 fixture that does only `reset -> ingest -> retrieve` should abstain or return only pre-existing public committed memory; it must not silently commit hidden memory。
- `approve` and `commit` are allowed public setup ops when a fixture wants to exercise the normal lifecycle rather than seed directly。
- setup payloads must not include scorer view, gold labels, expected answer IDs, trap family, or hidden mode。
- seeded cards are audit-distinguishable from normal commits but ranking-equivalent。
- `LifecycleReceipt` records are adapter outputs. They are stored in artifacts and audit verification, but are excluded from adapter inputs, `public_fixture_hash`, `operation_prefix_hash`, and retrieve `request_hash`。

`SeedCardSpec` rules:

- required fields are `kind`, `summary`, `scope`, `applicability`, non-empty `current_support_experience_ids`, `authority`, and `confidence`。
- optional fields are `details`, `retrieval_terms`, `invalidators`, and `valence`。If omitted, they use the same defaults as a committed `MemoryCard` candidate path。
- `retrieval_terms` is public fixture input when present and participates in public operation/prefix hashing. `null` / omitted means no explicit seed terms; any generated terms must be deterministic from public seed fields and audit-visible。
- `current_support_experience_ids` must name public experiences already present in the fixture or created by earlier public ingest/setup operations; proof-only refs are not enough for P1-scored retrieval。
- `SeedAuthoritySpec` is public input, not storage `Authority`。Its refs are public experience IDs / public approval refs because execution-generated `provenance_event.event_id` values do not exist yet。
- seed execution converts `SeedAuthoritySpec` to stored `Authority`: `source` and `strength` copy directly, `public_source_experience_ids` / `public_approval_refs` are resolved to generated or existing authorized `provenance_event.event_id` values, and those event IDs populate `Authority.source_refs` on the committed card。
- `LifecycleReceipt.provenance_event_ids` must include the provenance events used for this conversion so conformance can verify public input refs -> storage `Authority.source_refs` without requiring pre-execution private IDs。
Source-specific authority requirements:

| Seed authority source / strength | Required resolved storage refs |
| --- | --- |
| `source=scoring`, `strength=observation|hint` | May use fixture seed/support provenance generated during `seed_eval` with `provenance_event.actor=scoring` or `ProvenanceRef.producer=scoring`; empty refs are allowed only as low-authority fixture/debug evidence。 |
| `source=self`, `strength=observation|hint` | Empty refs are allowed only as low-authority self/fixture evidence。 |
| `source=user|reviewer|maintainer|system|verifier` | Must resolve at least one `public_source_experience_id` or `public_approval_ref` to provenance whose actor/producer matches the requested authority source。 |
| any `source`, `strength=should|must` | Must resolve at least one matching authority source ref with approval/authority role or explicit source provenance for that actor; support-only refs are weak for should/must and empty refs are rejected, including for scoring。 |

- if any public authority ref cannot be resolved, resolves to the wrong source, or fails the strength/source requirements, `seed_eval` returns `LifecycleReceipt.status=rejected` with `status_reason=authority_ref_unresolved|authority_source_mismatch|authority_refs_required`, and must not create a committed card。
- all `SeedCardSpec` and `SeedAuthoritySpec` fields participate in public operation/prefix hashing using the same canonical JSON and confidence rounding rules as `MemoryCard`。

Public selector binding:

- `approve` and `commit` inputs must not cite hidden candidate/proposal/card IDs. They cite public `LifecycleSelector` records instead。
- a selector binds to a prior public lifecycle operation by `source_op_id`, `output_role`, and optional `index`, `kind`, and `source_experience_id` filters over that prior operation's `LifecycleReceipt`。
- `output_role` maps to receipt fields deterministically: `candidate -> candidate_ids`, `proposal -> proposal_ids`, `approved -> approved_ids`, and `committed_card` / `seeded_card -> card_ids`。`seeded_card` is valid only for `seed_eval` receipts。`index` is zero-based after applying role, kind, and source-experience filters。
- if public ingest is routed through a dedicated `ingest(items)` method instead of `LifecycleOp.lifecycle_type=ingest`, the runner must emit an ingest-equivalent `LifecycleReceipt` keyed by the public ingest operation ID before `approve` / `commit` selectors can target it。Without that receipt, lifecycle selector setup is unsupported and fixtures should use `seed_eval`。
- selector resolution is deterministic over the ordered receipt output for the prior op. If a selector resolves to zero outputs or more than one output, the current operation returns `LifecycleReceipt.status=rejected` with a structured ambiguity reason and `result_hash`。
- `approve` accepts selectors with `output_role=candidate` or `proposal`。`commit` accepts selectors with `output_role=approved`, and may accept `output_role=proposal` only when the approval and commit happen inside one explicitly privileged debug/scoring operation recorded in audit。
- `seed_eval` may produce `output_role=seeded_card` / `committed_card` directly; P1 fixtures may use `seed_eval` without dynamic approve/commit binding when the fixture only needs deterministic setup。

Lifecycle payload requirements:

| lifecycle_type | Required payload fields | Source audit mapping |
| --- | --- | --- |
| `ingest` | `experience_ids` or public experience payload refs | `capture_provenance`, optional `extract_candidate` / `propose`。 |
| `seed_eval` | `seed_cards`; each card has a required `SeedCardSpec` and public current-support experience IDs | `seed_eval` plus provenance capture for each support experience。 |
| `approve` | `selectors`, `approval_refs`, `reason` | `approve`; approval refs become `EvidenceLink(role=approval)`。 |
| `commit` | `selectors`, `reason` | `commit`; result card IDs and result hash recorded in `LifecycleReceipt`。 |

Lifecycle receipts are part of adapter artifacts and audit verification. They are not inputs to ranking and are never projected to the adapter as future setup payloads; future lifecycle ops refer to prior outputs through public selectors.

Required generic harness contract change before Phase C:

```yaml
public_fixture_keys:
  fixture_id: string
  public_schema_version: string
  public_experiences: list[Experience]
  public_operation_sequence: list[LifecycleOp | AdapterMutationOp | RetrieveRequestEnvelope]
  public_fixture_hash: string
  capability_manifest_hash: string
  operation_prefix_hashes: map[op_id, string]
  request_hashes: map[request_id, string]
```

Canonicalization:

- public hashes use stable JSON: sorted object keys, UTF-8, no insignificant whitespace, normalized datetimes, and ordered operation arrays。
- `public_fixture_hash` includes only the static adapter-visible fixture view without gold: fixture ID, public schema version, public experiences, public scope/config knobs, and no operation prefix/query payloads。
- manifest capabilities, `setup_routing`, adapter version, and adapter config belong in `capability_manifest_hash` or adapter config hash, not in `public_fixture_hash`。
- each `operation_prefix_hash` includes `public_fixture_hash` plus every applied public setup/ingest/mutation operation input before the referenced operation boundary。
- for retrieve/query payloads, `operation_prefix_hash` excludes the current retrieve/query; the query payload has a separate `request_hash`。
- if setup receipt hashes are needed, they are named `setup_receipt_hash` / `lifecycle_receipt_hash` and are not folded into the operation prefix for prior requests。
- private scorer/gold fields, expected answer IDs, trap family, hidden mode, and scorer-only annotations are excluded from adapter input and rejected if they appear in any public setup/mutation payload。

Runner dispatch and routing:

```text
manifest.setup_routing = setup_method | mutate_lifecycle

setup lifecycle ops = ingest | seed_eval | approve | commit
runtime mutation ops = update | delete | forget | supersede | tombstone
```

- If `manifest.setup_routing=setup_method`, the adapter must expose `setup(ops)`; setup lifecycle ops go through `setup(ops)`, runtime mutation ops go through `mutate(ops)`, and lifecycle ops passed to `mutate(ops)` are rejected。
- If `manifest.setup_routing=mutate_lifecycle`, the adapter must not expose `setup(ops)`; both setup lifecycle ops and runtime mutation ops go through `mutate(ops)` with typed op records。
- If the current generic runner only supports operation types `ingest`, `mutate`, and `request`, Phase C must use `mutate_lifecycle`: encode `seed_eval` / `approve` / `commit` as public mutate lifecycle records, and treat `request` as `retrieve` for adapter dispatch。
- Mixed routing is a conformance failure。
- `reset(run)` only initializes an empty fixture-scoped store/snapshot and ID maps; it never seeds retrievable memory。

ID maps owned by the adapter/runner boundary:

```yaml
id_maps:
  experience_id_to_provenance_event_ids: map[string, list[string]]
  experience_id_to_active_card_ids: map[string, list[string]]
  op_id_to_mutation_ids: map[string, list[string]]
  op_id_to_card_ids: map[string, list[string]]
  card_id_to_source_experience_ids: map[string, list[string]]
```

These maps are derived from public operations and audit receipts. They are persisted in adapter artifacts for conformance/debug, but core ranking must not use them except through public provenance/card state.

Later optional:

| Adapter method | Subsystem mapping | Phase |
| --- | --- | --- |
| `build_context(request)` | MemoryContextBuilder / evidence packet | Phase E+ |
| `inspect_provenance(refs)` | provenance_events lookup with redaction | Phase E+ |

### Mapping MemoryCard to harness evidence refs

P1 deterministic scoring needs support IDs。

Recommended mapping:

```text
ranked_evidence[].evidence_ref = card.card_id
ranked_evidence[].support_experience_ids = active current-support evidence links -> provenance_event.source_experience_id
ranked_evidence[].source_experience_ids = same set as support_experience_ids in P0/P1 unless a later scorer defines a distinction
ranked_evidence[].lineage_experience_ids = lineage/proof/supersession evidence links that are visible and authorized, never scored as current support
ranked_evidence[].provenance_refs = authorized visible current_support evidence link refs only
ranked_evidence[].source_mutation_ids = source mutation IDs on active support/proof provenance or mutations that produced the current active card
ranked_evidence[].mutation_refs = public operation IDs that changed the returned card's current state
ranked_evidence[].state = card.staleness_state / active state as report-only
ranked_evidence[].scope_id = card.scope namespace as report-only
```

Important rules:

- P1 support IDs represent current-query support, not full historical lineage。
- for cards with multiple active `current_support` links, `support_experience_ids` is a de-duplicated set of acceptable support IDs. The harness owns exact matching semantics; the adapter must not infer gold logic, prefer one support ID, or drop secondary current support to improve scoring。
- stale lineage must not be included as support unless that stale item is actually exposed as evidence。
- if a card is derived/summarized, `support_experience_ids` must still identify the fixture experiences that justify the current claim。
- unscorable current-support evidence links should fail adapter conformance, not be hidden as low score。
- approval, reviewer-context, invalidator, contradiction, debug, stale, superseded, out-of-scope, or forgotten provenance never contributes to `support_experience_ids` by default。
- top-level `provenance_refs` is the union of authorized visible `current_support` refs only。All other roles are exposed, when authorized, only under `metadata.provenance_refs_by_role`。
- P0/P1 conformance requires every returned ranked evidence item to have either non-empty current support IDs or a structured abstention/unsupported reason; broad provenance refs are insufficient。

Adapter mapping algorithm:

```text
for each returned card:
  visible_links = governance-filtered card.evidence_links
  for each link in visible_links:
    load provenance_event
    if link.role == current_support and link.active and provenance_event.source_experience_id is present:
      add to support_experience_ids
      add provenance_event.source_experience_id to source_experience_ids
      add link.ref_id to provenance_refs
      add link.ref_id to metadata.provenance_refs_by_role.current_support
      add provenance_event.source_mutation_id to source_mutation_ids when present
    else if link.role in {lineage, proof, supersession} and caller is authorized:
      add provenance_event.source_experience_id to lineage_experience_ids when present
      add link.ref_id to metadata.provenance_refs_by_role[link.role]
    else if explicit fixture rule allows source_run_id/source_turn_id derivation:
      derive only for active current_support links
    else:
      keep the ref only in provenance_refs_by_role when caller is authorized
  if returned item has no support_experience_ids and request is deterministic P0/P1:
    mark evidence unscorable and fail conformance or abstain with structured reason
```

Round trip requirement: an experience ingested with `source_experience_id=exp_001` and later retrieved through a summarized card must return `support_experience_ids=["exp_001"]` unless the evidence was deleted/forgotten or no longer supports the visible result.

Phase C round-trip requirement: for every returned ranked item, top-level `provenance_refs` must exactly equal `metadata.provenance_refs_by_role.current_support` after authorization/redaction filtering.

### Retrieve result contract

Adapter `retrieve(query)` returns:

```yaml
RetrieveResult:
  ranked_evidence:
    - rank: int
      evidence_ref: string
      support_experience_ids: list[string]
      source_experience_ids: list[string]
      lineage_experience_ids: list[string]
      provenance_refs: list[string]
      source_mutation_ids: list[string]
      mutation_refs: list[string]
      score: CanonicalScore
      score_type: deterministic_weighted_sum | lexical_only | structured_only | reranker
      score_components:
        structured_match: CanonicalScore
        lexical_score: CanonicalScore
        vector_score: CanonicalScore | null
        reranker_score: CanonicalScore | null
        scope_modifier: CanonicalScore
        authority_modifier: CanonicalScore
        freshness_modifier: CanonicalScore
        contradiction_modifier: CanonicalScore
        confidence_modifier: CanonicalScore
        graph_modifier: CanonicalScore
        budget_modifier: CanonicalScore
        final_score: CanonicalScore
      state: active | maybe_stale | stale | superseded | deleted | tombstoned
      scope_id: string
      metadata:
        card_id: string
        card_kind: string
        approval_state: string
        staleness_state: string
        contradiction_state: string
        authority: Authority
        applicability: Applicability
        provenance_refs_by_role: map[string, list[string]]
  abstained: bool
  abstained_reason: no_memory | no_relevant_memory | all_dropped | over_budget | privacy_block | unsupported | null
  dropped: list[CallerVisibleDroppedRecord]
  dropped_count_by_reason: map[string, int]
  usage: Usage
  request_id: string
  request_hash: string
  result_hash: string
```

`rank` is 1-based after governance filtering and deterministic ranking. `dropped` is caller-visible only and must be privacy-safe; internal dropped IDs belong in `memory_audit_log`.

`Usage` is fixed enough for regression comparison:

```yaml
Usage:
  latency_ms: float
  latency_source: wall_clock | deterministic_mock | replayed_artifact
  cards_scanned: int
  cards_ranked: int
  cards_returned: int
  cards_dropped: int
  graph_nodes_expanded: int
  graph_edges_expanded: int
  projection_chars: int
  index_mode: direct_scan | sync_lexical | vector | hybrid | replay | graph_index
  token_count: int | null
  cost_units: float | null
```

Rules:

- all count fields are non-negative and count records after the visibility/privacy gate unless the field name explicitly says scanned。
- `cards_scanned` counts candidate memory cards considered by seed retrieval before ranking; `cards_ranked` counts cards that survive governance and enter deterministic ranking; `cards_returned` counts ranked evidence items returned; `cards_dropped` equals the sum of internal drop records for this request, even when caller-visible dropped IDs are suppressed。
- graph expansion counts are zero for `index_mode=direct_scan|sync_lexical|vector|hybrid|replay` unless Phase D expansion ran。
- `projection_chars` counts caller-visible projected text/chars, not hidden audit/provenance payload。
- P1 token/cost fields may remain null, but the fixed latency/count/index fields are required for `retrieve` and `report_usage` artifacts。

`report_usage(scope?)` returns the same fixed fields aggregated over the requested scope/window, plus `request_count` and the aggregation window when available:

```yaml
UsageReport:
  scope: Scope | null
  window_start: datetime | null
  window_end: datetime | null
  request_count: int
  aggregate: Usage
  metadata: object
```

Aggregate field rules:

- `latency_ms` is the arithmetic mean over included requests unless `metadata.percentiles` is also returned。
- `latency_source` is `wall_clock` if any included request used wall clock, else `replayed_artifact` if any used replay, else `deterministic_mock`; `metadata.latency_source_counts` records per-source counts。
- `cards_scanned`, `cards_ranked`, `cards_returned`, `cards_dropped`, `graph_nodes_expanded`, `graph_edges_expanded`, and `projection_chars` are sums。
- `index_mode` is `graph_index` if any request used graph index expansion, else `hybrid` if any request used hybrid summary search, else `vector` if any request used vector summary search, else `replay` if any request used replayed summary-search artifacts, else `sync_lexical` if any request used sync lexical, else `direct_scan`; `metadata.index_mode_counts` records per-mode counts。
- `token_count` is the sum only when every included request has non-null `token_count`; otherwise it is null and `metadata.missing_token_count_requests` records the missing count。
- `cost_units` is the sum only when every included request has non-null `cost_units`; otherwise it is null and `metadata.missing_cost_units_requests` records the missing count。
- unavailable fields must not be guessed. If a request lacks a required fixed field, conformance fails for P0/P1; for legacy debug aggregation, the field is excluded only when `metadata.legacy_missing_fields` records request IDs and field names。

`abstained_reason=unsupported` is reserved for capability/schema mismatch. Empty but supported retrieval uses `no_memory`, `no_relevant_memory`, `all_dropped`, or `privacy_block`.

### Mapping mutations

| Harness mutation | Memory core behavior | Required adapter behavior |
| --- | --- | --- |
| `update` | create new revision, preserve lineage | active card uses updated support; old revision not fresh support。 |
| `delete` | mark removed from normal retrieval | retrieve must not return as normal evidence。 |
| `forget` | strong non-exposure and non-support | support/provenance inspection must respect redaction/forget semantics。 |
| `supersede` | old card `superseded`; replacement `committed/fresh` | strict stale fixtures must not return old as fresh。 |

Harness-side mutation operation schema:

```yaml
AdapterMutationOp:
  op_id: string
  mutation_type: update | delete | forget | supersede | tombstone
  target_experience_id: string | null
  replacement_experience_id: string | null
  effective_time: datetime | null
  reason: string | null
  replacement:
    content: object | null
  metadata: object
```

Adapter dispatch maps this to typed `MemoryMutation`. `update/delete/forget/supersede` are adapter-visible. `tombstone` is accepted only when the fixture schema explicitly includes it; otherwise tombstone remains an internal representation for delete/supersede/rollback.

Translation rules:

- `target_experience_id` resolves to cards whose active current-support evidence links cite a provenance event with that `source_experience_id`。
- if zero active cards resolve, return structured unsupported/not_found for that op; do not silently pass。
- an experience is **P1 mutation-targetable** if any public `AdapterMutationOp` cites it as `target_experience_id`。This is a fixture-design validation rule, not a general runtime expectation。
- P1 mutation-targetable experiences must produce exactly one active targetable card at mutation time。If multiple active cards resolve, the fixture/operation is invalid for P1 and the adapter returns structured `ambiguous_target`。
- a future P2 extension may add hash-covered `target_card_id` or a structured selector to the public mutation schema; selector payloads must be included in public/prefix hashes and checked for leakage before dispatch。
- `replacement_experience_id` resolves to a provenance event from public ingest/setup with that source ID; if absent, replacement content may create only a candidate/proposal and cannot be committed without a public approve/commit/seed op。
- any provenance event created from a public mutation sets `source_mutation_id=op_id`。
- `source_mutation_ids` on resulting retrieve items include `op_id` when the public op produced the active card state or active support provenance。
- `mutation_refs` include `op_id` for every public operation that updated, deleted, forgot, superseded, or tombstoned the returned card lineage and is visible to the caller。
- `effective_time` is audit/order metadata; it must not let a mutation affect earlier prefix hashes or earlier public retrieval operations。

`replacement.content` and `MemoryMutation.patch` use one canonical nested wire representation, `ReplacementContent`. Dot-notation paths below are explanatory only and must not be the serialized form.

```yaml
ReplacementContent:
  clear_fields: list[details | retrieval_terms | lifecycle.expires_at | privacy.redaction_policy]
  summary?: string
  details?: string | null
  retrieval_terms?: list[string] | null
  applicability?: Applicability
  valence?: Valence
  invalidators?: list[Invalidator]
  confidence?: float
  lifecycle?:
    expires_at?: datetime | null
  privacy?:
    redaction_policy?: string | null

MemoryMutation.patch: ReplacementContent
```

Canonical hash/serialization rules:

```text
ReplacementContent is serialized as a nested object matching the MemoryCard facet shape.
Absent optional fields are omitted, not serialized as dotted keys.
Omitted fields mean unchanged.
`clear_fields` defaults to an empty list when absent.
Absent `clear_fields` and `clear_fields: []` canonicalize identically; non-empty entries are sorted lexicographically before hashing.
Explicit null is rejected unless the exact field path appears in `clear_fields` and the field is one of the allowed clearable paths.
Stable JSON hashing uses sorted keys and the same confidence rounding rules as MemoryCard.
`clear_fields` participates in canonical hashing and validation.
`retrieval_terms` uses MemoryCard term validation and de-duplication before hashing. A changed term list is a semantic retrieval mutation and is audit-visible.
```

Equivalent explanatory field paths:

```text
  clear_fields: list[details | retrieval_terms | lifecycle.expires_at | privacy.redaction_policy]
  summary?: string
  details?: string | null
  retrieval_terms?: list[string] | null
  applicability?: Applicability
  valence?: Valence
  invalidators?: list[Invalidator]
  confidence?: float
  lifecycle.expires_at?: datetime | null
  privacy.redaction_policy?: string | null
```

Tri-state patch semantics:

- omitted field: leave target card value unchanged。
- explicit value: replace that allowed field after normal schema validation。
- explicit null: clear only `details`, `retrieval_terms`, `lifecycle.expires_at`, or `privacy.redaction_policy`, and only when the field path is also listed in `clear_fields`。For `retrieval_terms`, clear means replace with `[]` because the stored field is a list, not nullable。Null for `summary`, `applicability`, `valence`, `invalidators`, `confidence`, `authority`, `scope`, or evidence links is rejected。
- empty `invalidators: []` means replace invalidators with an empty list if the actor/kind allows that patch; `invalidators: null` is rejected。

Replacement content by mutation type:

| Mutation type | Required replacement content | Auto-derived from target card | Provenance/authority requirements |
| --- | --- | --- | --- |
| `update` | at least one of `summary`, `details`, `retrieval_terms`, `applicability`, `valence`, `invalidators`, `confidence`, `lifecycle.expires_at`, `privacy.redaction_policy` | `kind`, `scope`, projection mode, existing lineage, and any unchanged content/facets | replacement provenance must cite `replacement_experience_id` or public mutation provenance as active `current_support`; authority stays unchanged unless public approve/commit supplies new authority。 |
| `supersede` | replacement `summary` plus active support provenance; `details` recommended when summary alone is ambiguous | `kind`, `scope`, lifecycle, privacy, and applicability unless provided | new card/revision gets active `current_support` link from replacement provenance and `authority.source=scoring` for fixture path unless public authority provenance is provided。 |
| `delete` | none; `replacement.content` must be null | not applicable | target lineage/audit only。 |
| `forget` | none; `replacement.content` must be null | not applicable | privacy/security/user-driven authority refs required by mutation request。 |
| `tombstone` | none; `replacement.content` must be null | not applicable | audit/rollback authority refs required。 |

Underspecified replacement content is rejected before core mutation:

- update/supersede without `replacement_experience_id` and without enough public `replacement.content` to build a typed candidate is invalid。
- replacement content cannot set forbidden fields listed below。
- replacement content cannot claim `authority.source=user|reviewer|maintainer` unless matching public provenance exists。
- replacement content cannot change scope identity; scope changes require supersede/new public commit with explicit structured scope and audit。

Allowed direct patch fields are content/facet fields that do not change provenance, authority, or scope identity. Forbidden patch fields:

```text
card_id
schema_version
kind
scope.level
scope.namespace
authority.source
authority.strength
authority.source_refs
evidence_links
evidence_refs
support_refs
approval_state
staleness_state
contradiction_state
revision
timestamps.created_at
audit
graph_refs
```

Changing forbidden fields requires `supersede` or a new public seed/approve/commit path that creates a new card/revision with new provenance and audit. A normal `update` patch re-enters proposal/approval unless the actor is the public adapter/scoring path applying a deterministic fixture mutation with public replacement provenance; that privileged fixture update is still audited as `mutate` plus resulting commit/supersede state. Adapter validation must reject forbidden-field patch attempts before calling core.

Allowed patch fields by actor/kind:

| Actor / kind | Allowed direct patch fields |
| --- | --- |
| `adapter`/`scoring` fixture update for any kind | `summary`, `details`, `retrieval_terms`, `applicability`, `valence`, `invalidators`, `confidence`, `lifecycle.expires_at`, `privacy.redaction_policy` when payload is public and hash-covered。 |
| `debug` for any kind | same as adapter/scoring, but commit still needs approval audit unless explicitly privileged。 |
| `user` on `policy_or_preference` | `summary`, `details`, `retrieval_terms`, `applicability`, `lifecycle.expires_at`, `privacy.redaction_policy`; authority changes require new approval/source provenance。 |
| `reviewer`/`maintainer` on `procedure` or `policy_or_preference` | `summary`, `details`, `retrieval_terms`, `applicability`, `valence`, `invalidators`, `confidence`; authority/scope changes require supersede/new commit。 |
| `model_proposal` any kind | no direct committed patch; creates proposal only。 |

### Exposing scope/staleness/contradiction

Adapter should report these as metadata, but harness scorer must not trust them as source of truth。

```json
{
  "evidence_ref": "mem_123",
  "support_experience_ids": ["exp_001"],
  "provenance_refs": ["prov_001"],
  "state": "active",
  "scope_id": "tenant_a/repo_x",
  "metadata": {
    "card_kind": "semantic_fact",
    "staleness_state": "fresh",
    "contradiction_state": "none",
    "approval_state": "committed",
    "authority": {
      "source": "reviewer",
      "strength": "should",
      "source_refs": ["prov_approval_001"]
    }
  }
}
```

### Unsupported until later phases

| Surface | Unsupported until | Reason |
| --- | --- | --- |
| semantic claim support judge | later model-judged phase | P1 is deterministic ID scoring。 |
| full context packet metrics | P2+ harness / Phase E subsystem | first prove retrieval correctness。 |
| full provenance traversal | Phase E | P1 uses support refs/provenance-lite。 |
| model-in-loop downstream utility | Phase G | after deterministic core and adapter are stable。 |
| production prompt projection | separate prompt section design | avoid ambient hidden memory。 |

---

## 12. Implementation phases

This plan is conservative and evaluation-harness-first。

### Phase A: typed card schema and provenance store only

Goal: define and implement data shapes without production recall exposure。

Deliverables:

- `MemoryCard` schema/dataclass。
- `ProvenanceEvent` schema/dataclass。
- `GraphNode` minimal schema。
- `GraphEdge` minimal schema。
- `MemoryAuditEvent` minimal schema。
- stable serialization and hash rules。
- no `implement_v2` dependency。
- no prompt projection。

Timing:

- should wait until, or run after, generic eval harness Phase 0 is usable enough to validate adapter-shape assumptions。
- may proceed in parallel only if no harness internals are imported into core。

### Phase B: deterministic read/write core with manual/debug approval

Goal: make core deterministic, inspectable, and evaluable。

Deliverables:

- provenance capture。
- candidate/proposal/approval/commit separation。
- manual/debug/scoring approval path。
- `retrieval_terms` carried through `MemoryCandidate`, committed `MemoryCard`, `SeedCardSpec`, and `ReplacementContent` mutation paths。
- structured filters plus injectable `SummarySearchBackend` seed retrieval over committed typed-card surfaces; direct-scan/lexical/BM25 is the deterministic baseline, while vector/hybrid/replay backends can be selected by eval/runtime config。
- Phase B/D internal `memory_semantic_search_internal` candidate generation over typed-card surfaces for adapter/core retrieval use。
- `RetrievalSurfaceConfig` and `SummarySearchBackendIdentity` artifact identity for included fields, field weights, tokenizer, normalizer, stopword policy, backend config, and surface hash。
- governance filters for scope, staleness, contradiction, approval state。
- update/delete/forget/supersede/tombstone semantics。
- optional `graph_refs` validation: absent refs are allowed; present refs must be canonical, but executable expansion waits for Phase D。
- usage/audit logs。

Rules:

- model may propose candidates。
- model cannot commit durable memory。
- `retrieve` is durable side-effect free。

### Phase C: adapter to generic memory eval harness

Goal: evaluate subsystem through generic adapter-based harness。

Deliverables:

- memory core adapter implementing either `manifest/reset/ingest/setup/mutate/retrieve/report_usage` with `setup_routing=setup_method`, or `manifest/reset/ingest/mutate/retrieve/report_usage` with `setup_routing=mutate_lifecycle`。
- support mapping from MemoryCard to `support_experience_ids`。
- mutation mapping。
- usage reporting。
- no harness core dependency inside memory core。

Timing:

- Phase C is a gate before executable graph expansion。If Phase B has retrieval/mutation semantics, Phase C connects to the harness immediately so design errors are found by P0/P1 fixtures。

P0 readiness close gate for this phase separates harness-level conformance coverage from the subsystem adapter requirement:

```text
generic harness conformance suite:
  adapter contract/schema stable
  + reference/dummy setup_method adapter smoke passing: manifest/reset/ingest/setup/mutate/retrieve/report_usage
  + reference/dummy mutate_lifecycle adapter smoke passing: manifest/reset/ingest/mutate/retrieve/report_usage with encoded seed_eval/approve/commit lifecycle ops exercised through mutate
  + hidden reset-time seeding rejected
  + setup/mutate routing exclusivity enforced

memory subsystem adapter close gate:
  declared setup_routing mode present in manifest
  + only the declared route's smoke test passing
  + hidden reset-time seeding rejected for that route
  + core forbidden-import checks passing
```

### Phase D: graph/index seed retrieval and bounded expansion

Goal: add graph/index as support layer, not primary memory。

Deliverables:

- graph node canonicalization。
- graph edge indexing。
- one-hop bounded expansion initially。
- file/symbol/test/error/task family links。
- expansion budget and dropped reasons。
- graph invalidation hooks。
- graph-aware/optimized retrieval index rebuild/invalidation logic with rebuild verifier。
- optional vector/reranker identity and replay artifacts if semantic candidate generation uses embeddings or reranking。

Rules:

- cannot start until Phase C adapter conformance gate passes。
- no unbounded graph traversal。
- expansion occurs after seed retrieval。
- governance filtering still happens before projection。

Normative Phase D requirements:

- expansion seeds only from cards that passed normal recall governance and direct relevance filtering。
- candidate cards found through graph expansion still pass privacy, authorization scope, memory scope, applicability, lifecycle, staleness, contradiction, invalidator, and visible-support gates before scoring。
- expansion uses fresh canonical `graph_nodes` and durable `graph_edges`; unresolved or stale endpoints are ignored for expansion。
- actor/lineage and negative governance edge types do not contribute scored retrieval support; only allowlisted retrieval edges such as `related`, `mentions`, `supports`, `proved_by`, `located_in`, and `fixes` expand。
- unresolved or stale graph endpoints are counted by reason in caller-visible aggregate drop counts, while node/edge IDs remain internal-audit only。
- graph-expanded cards receive an explicit deterministic `graph_modifier` score component, and usage records `index_mode=graph_index`, `graph_nodes_expanded`, and `graph_edges_expanded`。
- graph-generation fixtures may set scorer-only `gold.expected_usage` gates, so a fixture can require `index_mode=graph_index` and minimum/maximum graph expansion counts without exposing those expectations to the adapter。When graph fixtures are enabled as deterministic/replay tests, they must satisfy these usage gates。
- graph negative fixtures cover raw graph-edge cross-scope non-leak, forgotten-support non-leak, stale endpoints, and uncanonicalized endpoints; scorer-only dropped-count gates validate caller-visible reasons without exposing blocked card/provenance IDs。
- graph expansion treats `CurrentEvidenceSnapshot` file/symbol/command endpoint states as a freshness overlay: missing endpoints stop expansion as uncanonicalized, and changed/moved/unknown/hash-mismatched endpoints stop expansion as stale。
- derived graph index verification rebuilds a canonical snapshot/hash from `memory_cards`, `graph_nodes`, and `graph_edges`; it excludes forgotten/deleted cards from active card refs, reports missing/stale graph refs as drift issues, and exposes a safe aggregate verifier summary in memory-eval retrieval artifacts with scorer-only expected verification gates。
- `seed_graph` remains an explicit fixture/debug setup path for isolating recall expansion from extraction quality; it is not evidence that ingest generates graph material。

Current Phase D.1 implementation status, 2026-05-22:

- `MemoryRecallRequest.expand_graph` enables one-hop expansion in the typed-card core; default is off。
- the typed-card eval adapter accepts adapter-visible `filters.expand_graph` / `filters.graph_max_*` controls, and the live runner exposes `--expand-graph` for normal-suite no-regression scoring。
- graph expansion supports explicit node, edge, card, and per-node fanout budget controls through `graph_max_nodes`, `graph_max_edges`, `graph_max_cards`, and `graph_max_fanout`。
- graph expansion supports `graph_max_latency_ms`; when the budget is exhausted, traversal stops and caller-visible output receives aggregate `graph_latency_budget_exhausted` counts。
- recall supports `max_projection_chars`, which drops otherwise ranked evidence when returning its projected summary would exceed the caller/eval character budget。
- memory-eval scoring supports scorer-only `gold.expected_usage` maximum count gates such as `max_graph_edges_expanded` and `max_projection_chars`, so budget fixtures can fail adapters that over-expand while still keeping gold labels hidden from adapter-visible input。
- graph expansion rejects edges whose active support/proof provenance is missing, restricted, deleted, or otherwise not caller-safe; caller-visible output exposes only aggregate `missing_graph_edge_evidence` counts while internal audit may retain the edge ID。
- duplicate deterministic graph-edge additions merge evidence links instead of overwriting support, so one forgotten support source does not invalidate the edge when another active current-support/proof source remains。
- derived graph index verification records aggregate `graph_edge_support_evidence_unavailable` issues when an expansion edge still exists but all active support/proof provenance for that edge is redacted, deleted, or otherwise not visible。
- current-evidence graph invalidation has focused coverage for file hash changes, moved symbol endpoints, and changed command endpoints。
- graph value-add evaluation includes a graph-off / graph-on fixture where the same query retrieves only seed support without expansion and retrieves an additional graph-only related support when expansion is enabled。
- graph negative evaluation includes a redacted edge-support fixture where `seed_graph` uses a dedicated support experience, that support is forgotten, and graph expansion plus derived verifier gates confirm the related card is not returned。
- raw extraction can emit explicit `graph_nodes` and `graph_edges` from raw text; proposed graph refs are carried through proposal/commit and can be evaluated without `seed_graph` setup。
- raw extraction treats the caller-provided runtime scope as authoritative; LLM-emitted scope may narrow, annotate, or request clarification, but it cannot broaden scope, switch namespace, change `user_id`, change `repo_ref`, or create `team` / `shared` scope。Mismatches are proposal warnings / dropped scope overrides, not stored card scope。

Remaining Phase D work:

- broader graph-specific memory-eval fixtures。
- additional graph invalidation coverage, especially broader invalidation matrix fixtures beyond redacted graph-edge support。
- deeper graph-aware rebuild drift fixtures。

Observed Phase D.1 validation artifacts, non-normative and allowed to become stale:

- graph value-add fixture passed on 2026-05-28 (`fixtures/memory_eval/p1/graph_value_add_relation_basic.json`): graph-off baseline returned seed support only, while graph-on returned the graph-only related support with `index_mode=graph_index` and positive graph expansion counts。
- graph budget controls fixture passed on 2026-05-28 (`fixtures/memory_eval/p1/graph_budget_controls_basic.json`): fanout, projection-char, and latency budget requests satisfied scorer-only expected usage limits and caller-visible aggregate dropped-count gates without exposing internal graph node/edge IDs。
- graph redacted edge-support fixture passed on 2026-05-28 (`fixtures/memory_eval/p1/graph_redacted_edge_support_no_leak_basic.json`): a graph edge whose dedicated support experience was forgotten produced only aggregate `missing_graph_edge_evidence` retrieval drops and `graph_edge_support_evidence_unavailable` derived verifier issue counts。
- graph-on live normal suite passed on 2026-05-22 with `gpt-5.5` (`run_id=manual_suite_graph_on_20260522`, 9/9 passed); because current P0/P1 fixtures contain no graph seed material, all graph expansion counts were zero and this run is a no-regression check, not graph retrieval quality proof。
- graph-generation live fixture passed on 2026-05-22 with `gpt-5.5` (`run_id=manual_graph_generation_20260522_v3`): `raw_text -> LLM extractor graph_nodes -> proposal/commit -> graph-on recall` returned the graph-related support with `index_mode=graph_index` and `graph_nodes_expanded=1`。
- graph-generation live suite passed on 2026-05-23 with `gpt-5.5` (`run_id=manual_graph_edge_generation_20260523_scopefix`, 2/2 passed): both `graph_nodes` and `graph_edges` extraction paths satisfied scorer-only graph usage gates。
- these dated live results are observed validation notes only。Live tests are non-gating unless an explicit opt-in such as `--allow-live-model-tests` is enabled。
- if this section becomes stale or too long, move dated run IDs and pass counts to an external validation artifact and keep only a short artifact link/reference in this design。

### Phase E: MemoryContextBuilder / evidence packet

Goal: build bounded, auditable context packet after retrieval correctness is testable。

Deliverables:

- `MemoryContextRequest`。
- `MemoryContextCard`。
- `MemoryContextPacket`。
- negative-space and coverage-gap notes。
- provenance-lite projection。
- `build_context` optional adapter surface。

Rules:

- no raw transcript read by builder。
- packet is evidence, not prompt instruction。
- stale/contradicted/out-of-scope memory filtered before packet。

### Phase F: MemoryToolProvider / implement_v2 integration

Goal: expose read-only recall/tool surface only after core and adapter evaluation are usable。

Deliverables:

- thin `MemoryToolProvider(recall)` adapter。
- short-term `memory_semantic_search` tool over governed typed-card surfaces。
- short-term `memory_context_grep` tool over candidate `MemorySearchContextDoc` documents, candidate-limited by default。
- `memory_report_usage` debug/eval-only tool surface。
- optional future `memory_graph_expand` tool, or hidden graph expansion fields on semantic-search results in the early phase。
- explicit enablement only。
- provider-visible bounded recall result。
- no write tool。
- no default prompt injection。
- `ToolRegistry` remains final model-visible schema authority。

Rules:

- `MemoryToolProvider` must not own storage, graph, extraction, approval, or prompt registry。
- `ToolRegistry` must not import memory stores/backends/projection policies。
- provider-visible semantic search must not index or search raw provenance payloads directly。
- provider-visible grep must scan only governed `MemorySearchContextDoc` documents, not raw text。
- `memory_report_usage` is for debug/eval and must not be injected as normal planning memory。
- `memory_semantic_search` is the Phase F LLM-visible wrapper around already-evaluated core/adapter retrieval behavior; score-improvement work belongs first in Phase B/D internal retrieval and adapter artifacts。

Hot-path regression definition:

```text
memory_recall_enabled=false/default
  => ToolRegistry visible tool specs unchanged
  => implement_v2/Codex execution path does not call MemorySystem
  => prompts/context packets contain no memory section
  => existing non-memory tests and snapshots remain unchanged except for explicit opt-in fixtures
```

If the implementation does not already have a flag with this meaning, adding a narrow opt-in flag is part of Phase F. This replaces vague `codex_hot_path` language with a concrete disabled-by-default integration contract.

### Phase G: model-in-loop downstream utility

Goal: evaluate whether memory improves agent behavior, after deterministic retrieval and adapter evaluation are stable。

Deliverables:

- model-in-loop rows using generic harness extension or separate later phase。
- memory-off / memory-on / stale comparisons。
- no-regression and stale rejection metrics。
- resident advantage claims tied to artifacts, not model self-report。

Rules:

- does not replace generic adapter-based evaluation。
- no resident-advantage claim without memory-off/memory-on artifacts and stale handling。

### Short-term hybrid recall/tooling design-only next slice

Goal: close the design gap exposed by the MemBench rank-6 smoke failure before implementing new recall tools.

This slice is design-only. It should produce a reviewed interface/design delta, not code, tests, migrations, or provider registration.

Phase placement:

- semantic candidate generation belongs to Phase B/D retrieval/index work, but only over committed typed-card surfaces and governed active short-term state.
- `MemorySearchContextDoc` belongs beside Phase E evidence/provenance-lite projection because it is a transformed, redacted verification surface derived from provenance.
- LLM-visible tools belong to Phase F and remain default-off.
- graph expansion remains Phase D-governed; it may stay hidden behind semantic-search result metadata until a separate `memory_graph_expand` surface is justified.

Design-only close criteria:

- document the exact searchable `MemoryCard` fields for injectable summary-search backends and explicitly exclude raw provenance payloads from semantic search.
- document `SummarySearchBackend`, `RetrievalSurfaceConfig`, backend identity, and vector/reranker replay identity so backend choice, retrieval-surface changes, weighting changes, and non-deterministic model behavior can be evaluated separately.
- document `MemorySearchContextDoc` generation, source-span mapping, line indexing, redaction state, privacy/forget invalidation, and rebuild/hash behavior.
- document strict grep support semantics: grep matches verify/localize active support but do not create new `support_experience_ids`.
- document the LLM tool schemas for `memory_semantic_search`, `memory_context_grep`, and `memory_report_usage`, including budgets, candidate-limited grep defaults, global-scan failover rules, usage fields, and privacy-safe dropped counts.
- decide whether graph expansion is hidden behind semantic-search result fields in the first tool phase or exposed later as `memory_graph_expand`.
- add an eval follow-up target for the MemBench niece/company rank-6 failure that measures top-k recall, top-1 precision, scope safety, and active-current-support correctness against relation-sensitive positives/distractors, without phrase-specific boosts.
- state that deterministic replay tests are gating, while live `gpt-5.5` smoke is opt-in/non-gating by default.
- preserve the existing Phase D/E/F gates: no unbounded graph traversal, no raw transcript packet, no write tool, no default prompt injection, and no default hot-path behavior change.

Recommended implementation order for this slice:

1. route `retrieval_terms` through `MemoryCard`, `MemoryCandidate`, `SeedCardSpec`, and `ReplacementContent`.
2. add deterministic replay extractor fixtures that generate `retrieval_terms`.
3. add the `SummarySearchBackend` injection point and artifact identity, with direct-scan/lexical or BM25 as the first deterministic baseline backend.
4. add budget-limited fixtures with top-k, top-1, scope-safety, support-correctness, and distractor gates, then compare lexical/BM25, vector, and hybrid backends when vector artifacts are available.
5. add internal semantic candidate generation in the core retrieval path through the same backend interface.
6. add `MemorySearchContextDoc` / grep as a verification layer.
7. expose provider-visible tools in Phase F after core/adapter behavior is stable.

### Phase summary

| Phase | Name | Can start before harness P0? | Close dependency |
| --- | --- | --- | --- |
| A | schema + provenance | preferably after P0 usable; parallel only with no harness import | stable schema/tests |
| B | deterministic core | after A, preferably after P0 | write/read semantics tests |
| C | generic harness adapter | after B and P0 readiness | adapter conformance / P0-P1 fixture smoke |
| D | graph/index expansion | after C gate | bounded expansion/canonicalization tests |
| E | context/evidence packet | after retrieval correctness | optional context/provenance surfaces |
| F | tool/implement integration | after core + adapter confidence | explicit read-only tool gates |
| G | model-in-loop utility | after deterministic eval | downstream artifacts |

---

## 13. Import and dependency boundaries

### Forbidden imports in memory subsystem core

Memory subsystem core must not import:

```text
implement_v2
MemoryArena
ToolRegistry
PromptSectionRegistry
memory_eval harness runner/scoring/fixtures
provider-visible tool registry modules
```

### Allowed dependency direction

```text
memory subsystem core
  <- memory tool provider adapter
  <- memory eval adapter
  <- future prompt projection adapter
```

The core owns memory behavior. Adapters own integration with external surfaces。

### Boundary table

| Component | May import memory core? | Memory core may import it? | Notes |
| --- | --- | --- | --- |
| generic memory eval adapter | Yes | No | Adapter-only bridge。 |
| `MemoryToolProvider` | Yes | No | Thin read-only tool adapter。 |
| `ToolRegistry` | No concrete core imports | No | Registry may know provider protocol only。 |
| `PromptSectionRegistry` | Later projection adapter may call it | No | Prompt projection is later。 |
| `implement_v2` | Later via provider/tool surface | No | No hot-path pollution。 |
| MemoryArena/model-in-loop harness | Later eval layer may call adapter/core | No | Not core dependency。 |

### Static import checks

Add static checks when implementation begins:

```text
memory subsystem core files do not import implement_v2
memory subsystem core files do not import MemoryArena
memory subsystem core files do not import ToolRegistry
memory subsystem core files do not import PromptSectionRegistry
memory subsystem core files do not import memory_eval runner/scoring/fixture modules
ToolRegistry does not import concrete memory store/backends/projection/extraction/approval
MemoryToolProvider does not import prompt projection internals
```

---

## 14. Close criteria

### Phase A close criteria: typed card schema and provenance store

| Criterion | Test |
| --- | --- |
| `MemoryCard`, `ProvenanceEvent`, `GraphNode`, `GraphEdge`, `MemoryAuditEvent` schemas exist。 | schema/dataclass unit tests。 |
| `RawMemoryIngestRequest` is string-first with only `raw_text` as public input; rich hint fields are rejected in v1。 | raw ingress schema validation test。 |
| `provenance_event.actor` and `ProvenanceRef.producer` include `adapter`, `scoring`, and `migration` for fixture/migration provenance。 | provenance enum serialization test。 |
| `GraphNode` includes explicit `scope_key`, and `scope_key` derives deterministically from canonical `Scope` JSON。 | graph node scope-key golden test。 |
| `GraphNode(node_type=actor)` supports `metadata.actor_kind=user|reviewer|verifier|maintainer|system|adapter|scoring|migration` and stable pseudonymous actor refs。 | actor node schema/canonicalization test。 |
| `memory_audit_event` and `MemoryTraceEvent` serialize the same logical fields, including `mutation_ids`, `metadata`, and `actor=migration`, modulo persistence-only `audit_id`/`created_at`。 | audit/trace schema golden serialization test。 |
| stable JSON serialization exists。 | golden serialization/hash test。 |
| card kind enum is exactly the 5 durable kinds。 | enum test。 |
| old 7-kind implementation enum and older 8 bucket vocabulary are not flat storage enums。 | static/schema test。 |
| `EvidenceLink` schema exists with role enum, active flag, mutation lineage, and stable serialization/hash。 | schema/golden serialization test。 |
| `Applicability` / `ApplicabilityRef` schemas exist and validate canonical graph-node refs plus `task_family:`, `workflow:`, `scope:`, and `text:` fallback rules。 | schema validation test。 |
| `Invalidator` schema exists with target node, baseline, observed-at, trigger-policy, and `manual_reason` fields。 | schema/golden serialization test, including manual invalidator requirements。 |
| `CurrentEvidenceSnapshot` schema exists with file/symbol/command/verifier/task/authority evidence state fields, including verifier applicability/task/error target refs, and intentionally excludes scoring authority events。 | schema/golden serialization test。 |
| `MemoryCandidate` schema has golden serialization/hash including `proposed_retrieval_terms`, evidence links, applicability, invalidators, confidence, proposed authority, and `proposed_by=adapter`。 | candidate golden serialization/hash test。 |
| stored card schema uses canonical `projection_mode: ProjectionMode`; retired `projection: ProjectionPolicy` is rejected or migrated before hashing。 | schema/golden hash naming test。 |
| role-bearing `evidence_links` are required for committed durable cards。 | validation test。 |
| ambiguous `state: MemoryState` is absent from stored card schema。 | schema regression test。 |
| `provenance_excerpt` is the only inline provenance excerpt field and enforces size/redaction rules。 | provenance schema test。 |
| raw transcript cannot be stored as committed card summary/details by default, including max length and excerpt rules。 | validation/leak test。 |
| `source_experience_id` and `source_mutation_id` exist on provenance events。 | provenance schema test。 |
| schema migration rejects unknown major versions, accepts safe minor optional fields, preserves lineage, and does not upgrade approval/authority。 | migration validation tests。 |
| legacy `MemoryEntry` field/kind/scope migration is deterministic and unknown flat scopes quarantine without recall。 | migration mapping golden tests。 |
| core has no forbidden imports。 | static import test。 |

### Phase B close criteria: deterministic core

| Criterion | Test |
| --- | --- |
| candidate/proposal/approval/commit separation exists。 | write lifecycle unit tests。 |
| model proposal cannot directly commit durable memory。 | no model-controlled durable commit test。 |
| approval state transition machine is enforced。 | legal/forbidden transition tests, including terminal rejected/tombstoned states。 |
| `candidate -> committed` bypass is restricted to `seed_eval`, explicit migration actor, or emergency restore new revision; debug/manual still records proposal -> approved -> committed, and migrated cards preserve `created_by=migration`。 | privileged bypass audit tests。 |
| candidate/proposal not recallable; committed recallable。 | recallability unit tests。 |
| `retrieval_terms` survive candidate/proposal/approval/commit and seed/mutation paths, changes are semantic retrieval mutations, and clear-to-empty behavior is explicit。 | write-path serialization/audit tests for `MemoryCandidate`, `SeedCardSpec`, `ReplacementContent`, and committed cards。 |
| `retrieval_terms` inherit card scope/privacy, and derived indexes over them are invalidated/redacted on forget/delete/privacy block/redaction/scope change。 | retrieval-term privacy and index invalidation tests。 |
| actor/authority matrix is enforced per kind/operation。 | approval permission tests。 |
| active support/proof evidence links required for committed semantic/procedure/policy cards。 | validation tests。 |
| update/delete/forget/supersede/tombstone semantics exist。 | mutation tests。 |
| forbidden-field mutation patches are rejected before core mutation。 | patch validation tests。 |
| delete/tombstone/forget redaction behavior differs as specified。 | retrieval/support/provenance visibility tests。 |
| stale rejection works。 | stale card not returned as fresh。 |
| current evidence invalidators use `CurrentEvidenceSnapshot` stored baselines and override stale memory。 | per-invalidator baseline tests for file/symbol/command/verifier/task/authority/procedure-failure target kinds。 |
| invalidator `trigger_policy` is validated against `kind` and rejects mismatched combinations。 | invalidator policy matrix tests。 |
| lifecycle expiry excludes cards as fresh without auto-tombstone/supersede。 | expiry recall/mutation tests。 |
| `consolidation_state` rejects non-`none` until a future phase defines semantics。 | lifecycle validation test。 |
| scope isolation works。 | repo/user/project cross-scope tests。 |
| recall visibility gate order is privacy/sharing, caller authorization, memory scope, applicability, then governance/staleness/contradiction。 | privacy/scope/applicability ordering tests。 |
| `scope_allows` implements exact task, branch/repo/project/task_family/user/team/shared containment without broadening or leaking through shared scopes。 | scope overlap table tests。 |
| `PrivacyRules.allowed_scope_ids` compares canonical `scope_key` values or resolved versioned shared-policy IDs, never display namespaces。 | privacy scope-key gate tests。 |
| contradiction handling works。 | contradicted card blocked/downgraded。 |
| contradiction can resolve only through supersede or explicit debug/manual evidence。 | contradiction state tests。 |
| deterministic ranking tie-breaks and score components are present, and all artifact-visible scores are `CanonicalScore` strings with finite-number checks, decimal `ROUND_HALF_UP`, and exactly four fractional digits before result hashes/golden comparisons。 | ranking golden/hash tests including `x.xxx05` ties, non-finite rejection, and JSON-number score rejection。 |
| retrieve is durable-memory side-effect free。 | repeated retrieve does not create durable cards or alter semantic fields; usage stats derive from audit。 |
| audit logs record dropped reasons and usage。 | audit tests。 |
| normal ingest cannot create committed cards directly。 | ingest governance test。 |
| ambiguous `ingest_raw(raw_text)` creates provenance/candidate/proposal only and does not treat LLM-inferred structure as durable truth。 | raw ingest ambiguity/proposal tests。 |
| raw-memory LLM extraction defaults to existing mew `codex` backend, `gpt-5.5`, and `auth.json`-style `load_model_auth`/`call_model_json` plumbing, while tests can inject deterministic extractor outputs。 | extractor model-binding/replay tests。 |
| extractor-proposed scope cannot broaden, switch namespace, change `user_id`, change `repo_ref`, or create team/shared scope when runtime scope is authoritative; mismatches become proposal warnings, not stored scope。 | raw extraction scope-override tests。 |
| `SummarySearchBackend` is injectable, and retrieve artifacts record `SummarySearchBackendIdentity` with backend kind/version/config hash, surface hash, and optional replay artifact。 | backend injection and artifact identity tests。 |
| `RetrievalSurfaceConfig` exists and participates in retrieval/index artifacts with included fields, field weights, tokenizer, normalizer, stopword policy, and `surface_config_hash`。 | retrieval surface config hash/golden tests。 |
| lexical/BM25 or hybrid retrieval is `retrieval_terms`-aware without phrase-specific benchmark boosts, while vector backends may be evaluated/replayed through the same interface。 | deterministic retrieval-anchor and backend-comparison tests。 |
| internal `memory_semantic_search_internal` can be used by core/adapter retrieve over typed-card surfaces only, with deterministic/replayable artifacts。 | internal semantic candidate generation tests。 |
| semantic/vector/BM25 candidate generation is authorization-prefiltered before scoring and does not leak unauthorized candidate IDs, scores, hit counts, dropped IDs, timing/debug explanations, or nearest-neighbor artifacts。 | retrieval prefilter and leakage tests。 |
| public `seed_eval` records authority/source/result hash, cannot include gold/trap labels, and writes `memory_audit_log.operation=seed_eval`。 | eval seed leakage/audit tests。 |
| seeded cards are audit-distinguishable from normal commits but ranking-equivalent; ranking code never reads seed-eval audit metadata。 | ranking/audit comparison and forbidden-input test。 |
| `memory_audit_log` payloads stay bounded to IDs/hashes/counts/reasons/small metadata, enforce concrete truncation/hash limits, and never store raw transcripts/output/diffs/projected packets。 | audit payload boundary and overflow tests。 |
| transient reentry recall uses the session-state gate and does not enter normal durable recall/support IDs。 | transient recall/promotion tests。 |
| commit transaction is atomic across cards, conditional graph writes, index, and audit, or recoverably rolled back。 | partial-failure recovery test with and without graph writes。 |
| Phase B cards may omit `graph_refs`; commit without graph refs is valid and remains retrievable through structured filters plus the configured summary-search backend, while present invalid graph refs reject the commit。 | graph refs optionality/validation test。 |

### Phase C close criteria: generic harness adapter

| Criterion | Test |
| --- | --- |
| adapter implements the manifest-declared `setup_method` or `mutate_lifecycle` method set exactly。 | adapter conformance test。 |
| core does not import harness internals。 | static import test。 |
| generic harness conformance covers both routing modes with reference/dummy adapters; the memory subsystem adapter passes only its declared route's smoke gate。 | P0 conformance smoke。 |
| setup routing is exclusive: `setup_method` and `mutate_lifecycle` cannot be mixed。 | routing conformance test。 |
| `LifecycleOp` input and `LifecycleReceipt` output are separate; receipts are excluded from adapter input and public/prefix/request hashes。 | lifecycle hash/artifact test。 |
| `SeedCardSpec` and `SeedAuthoritySpec` are structured, fully hash-covered, convert public authority refs to storage `Authority.source_refs`, match scoring authority to scoring provenance producers, reject unbacked non-scoring/should/must authority, and require explicit current-support experience IDs。 | seed card schema/hash/conversion/rejection test。 |
| `approve`/`commit` use public `LifecycleSelector` bindings to prior operation outputs, not hidden internal IDs。 | lifecycle selector binding test。 |
| `mutate_lifecycle` encodes and dispatches `seed_eval`/`approve`/`commit` lifecycle ops through `mutate(ops)` with lifecycle receipts。 | mutate lifecycle wire test。 |
| `ingest` maps fixture experiences to provenance and candidates/proposals without direct committed cards。 | adapter fixture test。 |
| public setup op inputs are included in public operation/prefix hashes; hidden reset seeding is rejected。 | hash/leakage conformance test。 |
| manifest/config hashes are separate from `public_fixture_hash`; retrieve `request_hash` is separate from operation prefix hash。 | hash canonicalization test。 |
| `retrieve` returns scorable `support_experience_ids` only from active current-support evidence links。 | P1 scoring compatibility and round-trip test。 |
| multiple active current-support links map to a de-duplicated support ID set without adapter-side gold inference。 | multi-support mapping test。 |
| proof-only committed cards are rejected as scored P1 returns unless intentionally abstained or explicitly aliased as `current_support`。 | proof-only scoring test。 |
| top-level `provenance_refs` equals the current-support slice of `metadata.provenance_refs_by_role`。 | provenance role round-trip test。 |
| retrieve result contract includes rank, scores/components, abstention, dropped counts, usage, support/source/mutation IDs, and scoring metadata。 | adapter artifact schema test。 |
| public mutation schema translates `op_id/mutation_type/target_experience_id/replacement_experience_id/effective_time/reason` deterministically, with ambiguity handling。 | mutation conformance test。 |
| P1 mutation-targetable experiences resolve to exactly one active targetable card; multi-card target experiences fail closed。 | mutation target disambiguation test。 |
| replacement content converts deterministically to typed patch/replacement card, including `clear_fields` null-clearing semantics, or rejects underspecified payloads。 | replacement content conformance test。 |
| stale/superseded/forgotten IDs are not returned as fresh support。 | stale/update/forget fixtures。 |
| usage reporting includes fixed latency/count/index fields with non-negative counts, stable per-field aggregate semantics, and unavailable-field handling。 | artifact usage schema/regression test。 |
| graph-generation fixtures can hard-gate scorer-only expected usage such as `index_mode=graph_index` and minimum graph expansion counts。 | `gold.expected_usage` scoring gate regression test。 |
| graph negative fixtures can hard-gate caller-visible dropped reason counts without exposing blocked card/provenance IDs。 | `gold.expected_dropped_count_by_reason` scoring gate and graph negative fixture tests。 |
| graph drift fixtures can hard-gate derived graph verifier status and aggregate issue counts without exposing node/card/provenance IDs。 | `gold.expected_derived_graph_index_verification` scoring gate and graph drift fixture tests。 |
| raw extraction cannot move memory to an LLM-chosen scope when caller runtime scope is authoritative; extracted scope may narrow/annotate/request clarification but cannot broaden, switch namespace, change `user_id`, change `repo_ref`, or create team/shared scope。 | scope override warning/drop regression test。 |
| relation-sensitive retrieval fixtures cover niece + company + correct company name positives and distractors: niece-not-company, unrelated company, same company name different scope/user, stale/superseded same name, and raw text match without active current support。 | deterministic replay budget-limited fixtures measuring top-k recall, top-1 precision, scope safety, and active-current-support correctness。 |
| live raw-memory extraction smoke is opt-in and non-gating by default; live `gpt-5.5` failures create diagnostics but do not fail hermetic CI unless `--allow-live-model-tests` or equivalent explicitly opts in。 | live-test gating/config tests plus deterministic retrieval-anchor regression tests。 |
| adapter-visible payload does not leak gold/mode/trap labels。 | harness P0 leakage test。 |
| caller-visible dropped IDs do not leak unauthorized card/provenance existence。 | cross-scope dropped metadata gate。 |

### Phase D close criteria: graph/index expansion

| Criterion | Test |
| --- | --- |
| graph nodes canonicalize cards/provenance/files/symbols/tests/commands/errors/tasks/actors。 | graph node canonicalization tests。 |
| graph node IDs are globally unique across node types, round-trip through exact `NodeIdV1` serialization, derive deterministic `scope_key`, use NFC normalization and uppercase percent-encoding, and reject cross-type/double-encoded collisions。 | graph node encoding/collision test。 |
| graph edges link durable graph nodes and reject committed non-canonical endpoints while holding only candidate/migration debug refs。 | edge schema tests。 |
| actor edges `approved_by`/`reviewed_by`/`vetoed_by`/`seed_eval_by`/`migrated_by` target actor nodes with matching `metadata.actor_kind` and do not become scored support IDs。 | actor edge schema/governance test。 |
| graph edges use role-bearing evidence links and tombstone/drop expansion when edge evidence is forgotten/redacted。 | graph evidence redaction test。 |
| retrieval index is derived, rebuildable, not authoritative, and Phase B simple index behavior is distinct from Phase D graph-aware index behavior。 | derived graph snapshot/hash verifier and index rebuild/equality/phasing tests。 |
| vector indexes, when present, record embedding model/config, index snapshot hash, and corpus surface hash。 | vector replay identity tests。 |
| rerankers, when present, record reranker model/config, replay artifact, and deterministic mode; non-deterministic rerankers are not direct P1 hermetic gates。 | reranker replay/non-gating tests。 |
| expansion is bounded by depth/fanout/node/card/latency/char budgets。 | budget tests, including scorer-only `min_*` / `max_*` expected-usage gates and `graph_budget_controls_basic` fixture coverage。 |
| expansion happens after seed retrieval and after Phase C adapter gate。 | trace/gate test。 |
| expansion does not bypass governance。 | stale/scope/contradiction graph tests。 |
| graph invalidation uses node hashes/staleness and current evidence。 | invalidation tests。 |
| dropped expansion nodes are counted by reason without unauthorized ID exposure。 | audit/privacy tests。 |

### Phase E close criteria: context/evidence packet

| Criterion | Test |
| --- | --- |
| `MemoryContextRequest/Card/Packet` schema exists。 | serialization/hash tests。 |
| packet contains bounded cards, dropped reasons, negative space, coverage gaps。 | builder tests。 |
| stale/contradicted/out-of-scope memory is filtered before packet。 | governance packet tests。 |
| packet does not contain raw transcript dumps。 | leak tests。 |
| `MemorySearchContextDoc` is generated only from authorized provenance through redaction/normalization, preserves source spans/line indexes, and is invalidated on forget/redaction。 | search-context-doc generation and redaction cascade tests。 |
| `MemorySearchContextDoc` grep matches are verification/localization evidence only, require candidate active current support and authorized source-span provenance, and never create new `support_experience_ids`。 | grep support-semantics tests。 |
| packet is evidence, not next action。 | forbidden field tests。 |
| optional adapter `build_context` can expose packet later。 | optional adapter test。 |

### Phase F close criteria: tool/provider integration

| Criterion | Test |
| --- | --- |
| `MemoryToolProvider(recall)` is read-only and default off。 | provider snapshot tests。 |
| Phase F `memory_semantic_search` wraps already-evaluated core/adapter semantic retrieval, searches only governed typed-card surfaces, and exposes score/debug fields showing which surfaces contributed。 | provider schema and forbidden-raw-payload tests。 |
| `memory_context_grep` scans only governed `MemorySearchContextDoc` documents, is candidate-limited by default, and requires explicit/failover audit for global scans。 | grep-scope, redaction, and global-failover tests。 |
| `memory_report_usage` is debug/eval-only and never appears as normal model planning context。 | provider/tool context snapshot tests。 |
| recall appears only under explicit enablement。 | ToolRegistry snapshot tests。 |
| provider result contains candidates/chains/dropped or packet projection only。 | schema tests。 |
| no write tool is exposed。 | tool list tests。 |
| no prompt injection by default。 | prompt section absence tests。 |
| forbidden fields cannot appear: `next_action`, `required_next`, `planner_instruction`, `tool_to_call`, `should_edit`, `finish_ready`。 | output leak tests。 |
| default implement/Codex hot path behavior is byte-for-byte unchanged when memory recall flag is disabled。 | ToolRegistry/implement_v2 snapshot regression tests。 |

### Phase G close criteria: model-in-loop utility

| Criterion | Test / Artifact |
| --- | --- |
| memory-off baseline exists。 | artifact。 |
| memory-on result exists for same fixture set。 | artifact。 |
| stale/contradicted run exists or explicit diagnostic waiver。 | artifact。 |
| memory-on does not regress verifier/protected-file/reviewer-rescue floors。 | no-regression artifact。 |
| resident advantage claim uses artifacts, not model self-report。 | review checklist。 |
| generic adapter-based eval remains primary substrate。 | review checklist。 |

### Required cross-phase tests

These tests must exist before claiming subsystem readiness。

```text
stale rejection
scope isolation
contradiction handling
contradiction resolved through supersede/manual-debug evidence only
approval state enforcement
candidate->committed bypass restricted to seed_eval/migration/emergency-restore revision
actor/authority matrix enforcement
provenance actor/producer enums include adapter/scoring/migration
SeedAuthoritySpec converts public refs to storage Authority.source_refs
SeedAuthoritySpec rejects unbacked non-scoring authority and any unbacked should/must
MemoryCandidate proposed_by includes adapter
MemoryCandidate proposed_retrieval_terms survives candidate/proposal/commit
SeedCardSpec retrieval_terms are hash-covered public setup input
retrieval_terms inherit card scope/privacy and derived indexes invalidate/redact on forget/delete/privacy block/redaction/scope change
no model-controlled durable commit
projection_mode is canonical; ProjectionPolicy wording rejected/migrated
role-bearing evidence links required
support_experience_id round trip through active current-support provenance only
multi-support support_experience_ids treated as a set with no adapter gold inference
public seed_eval/setup op inputs included in public operation/prefix hashes
LifecycleOp inputs and LifecycleReceipt outputs stay hash-separated
setup_method vs mutate_lifecycle routing exclusivity
mutate_lifecycle lifecycle wire schema and receipts
public_fixture_hash excludes manifest/config and retrieve payloads
seeded cards audit-distinguishable but ranking-equivalent
proof-only committed cards not returned as scored P1 evidence
top-level provenance_refs equals current_support refs
P1 mutation target experiences resolve to one active targetable card
replacement.content deterministic conversion or rejection
replacement content canonical nested serialization
replacement clear_fields/null semantics including retrieval_terms clear-to-empty
replacement retrieval_terms changes are semantic retrieval mutations and audit-visible
public mutation schema translation and forbidden patch rejection
invalidator stored baseline comparison
CurrentEvidenceSnapshot drives command/task/authority/procedure invalidators
procedure_failed_recently uses verifier applicability/task/error target refs
AuthorityEvidenceEvent excludes scoring as current-world evidence
invalidator trigger_policy kind validation
manual invalidator requires manual_reason
privacy/sharing allowed_scope_ids gate precedes authorization/scope/applicability/governance
PrivacyRules.allowed_scope_ids use canonical scope_key or resolved shared_policy IDs
scope_allows containment table prevents repo/project/user/team/shared leaks
lifecycle expiry without auto tombstone/supersede
consolidation_state non-none rejected
raw transcript not stored as durable card
raw extraction cannot broaden/switch authoritative runtime scope, user_id, repo_ref, namespace, team scope, or shared scope
retrieve is durable-memory side-effect free
usage stats derived from audit or separate rebuildable aggregate
fresh repo evidence overrides memory
current verifier/task/user evidence overrides stale memory
user memory does not leak project facts
failure shield does not become permanent unscoped ban
deterministic ranking tie-breaks and score components
RetrievalSurfaceConfig included_fields/field_weights/tokenizer/normalizer/stopword policy hash
SummarySearchBackend injectable over typed card surfaces with backend identity artifacts
retrieval_terms-aware lexical/BM25 or hybrid exact-anchor support over typed card surfaces
semantic/vector/BM25 candidate generation authorization-prefiltered before scoring with no unauthorized debug/timing/nearest-neighbor leakage
memory eval can compare lexical/BM25, vector, hybrid, and replay summary-search backends on the same fixtures
relation-sensitive top-k/top-1/scope/support retrieval fixtures with niece/company distractors
deterministic replay tests gate retrieval quality; live gpt-5.5 smoke is opt-in/non-gating by default
score components/final_score canonicalize to 4 decimals before result_hash
artifact-visible scores are CanonicalScore strings, not JSON numbers
score canonicalizer rejects non-finite values and uses Decimal ROUND_HALF_UP
ranking code forbidden from reading seed_eval audit metadata
delete/tombstone/forget redaction cascade
caller-visible dropped IDs do not leak unauthorized existence
memory_audit_log payload boundary excludes raw transcripts/output/diffs/packets
audit payload overflow truncates deterministically with hashes
report_usage fixed latency/count/index field definitions
UsageReport aggregates every Usage field deterministically
graph_nodes canonicalization and invalidation
actor graph nodes and audit/lineage actor edges target actor_kind metadata
graph node structured key percent-encoding/NFC canonicalization
NodeIdV1 scope_key derivation and round-trip rejection for non-canonical forms
graph edge role-bearing evidence links and redaction/tombstone cascade
vector index identity includes embedding model/config, index snapshot hash, and corpus surface hash
reranker identity includes model/config/replay artifact/deterministic mode and excludes non-deterministic rerankers from direct P1 gates
graph node cross-type collision rejection
reserved scope/text applicability prefixes
reserved task_family/workflow applicability prefixes
applicability canonical ref resolution/free-text fallback behavior
schema version migration and legacy scope mapping
unknown legacy scope quarantine
normal ingest vs privileged eval seeding governance
transient reentry session-state gate and promotion
Phase B/Phase D retrieval index phasing
semantic search indexes typed MemoryCard surfaces only, never raw provenance payloads
internal memory_semantic_search_internal precedes Phase F LLM-visible memory_semantic_search
MemorySearchContextDoc grep scans transformed/redacted docs only, with candidate-limited default and audited global failover
MemorySearchContextDoc grep verifies/localizes active current support only and never creates support_experience_ids
memory_report_usage remains debug/eval-only and is not normal planning context
MemBench niece/company rank-6 follow-up uses general retrieval-surface/semantic behavior, not phrase-specific boosts
Phase B graph_refs optional but validated when present
commit without graph_refs performs no graph writes but remains index/audit atomic
transactional partial-failure recovery
forbidden imports absent
```

---

## 15. Appendices and canonical detail locations

The main normative design is sections 1-14: architecture, stores, `MemoryCard` schema, provenance, write/read path, adapter boundary, phase plan, and close criteria. Detailed contract material is treated as appendix content and has one canonical location to avoid duplicate drift:

| Appendix | Detail | Canonical location |
| --- | --- | --- |
| Appendix A | full `LifecycleOp` / `LifecycleReceipt` wire schema | Section 11, `Public operation wire forms`。 |
| Appendix B | invalidator policy matrix | Section 7, `invalidators` / `Trigger policy validation`。 |
| Appendix C | legacy migration mapping | Section 6, `Transition and coexistence with existing memory implementation`。 |
| Appendix D | replacement content / patch semantics | Section 11, `Mapping mutations` / `ReplacementContent`。 |
| Appendix E | full cross-phase test list | Section 14, `Required cross-phase tests`。 |

Rules:

- appendix content is normative even when physically located near the subsystem boundary it defines。
- future document splits must move these canonical blocks, not copy them into parallel definitions。
- implementation tickets should cite appendix label plus canonical section to avoid ambiguity, e.g. "Appendix A / Section 11"。

---

## 16. Risks and anti-patterns

| Risk / anti-pattern | Why it is dangerous | Required mitigation |
| --- | --- | --- |
| hidden prompt memory | bypasses evaluation, creates stale hidden policy。 | no prompt injection by default; use bounded evidence packets later。 |
| flat `memory_kind` enum with mixed dimensions | mixes kind/scope/authority/valence/index。 | keep 5 storage kinds + facets。 |
| graph as primary memory store | graph dump is hard to evaluate and easy to over-expand。 | graph is index/expansion layer only。 |
| raw transcript as memory | imports unverified text and prompt-like instructions。 | provenance only; extract typed cards。 |
| reviewer prose as unconditional instruction | authority inflation; stale correction may overrule current evidence。 | model as `authority.source=reviewer` with scope/strength/invalidators。 |
| stale failure shield becoming permanent ban | prevents valid future fixes after conditions change。 | negative valence with invalidators and `verify` effect。 |
| user memory leaking project facts | cross-repo/project privacy and correctness failure。 | separate `scope=user` from project facts; sharing explicit。 |
| memory overriding fresh repo evidence | creates wrong edits from old state。 | governance rule: fresh repo/verifier evidence wins。 |
| subsystem-specific eval replacing generic harness | prevents implementation-independent comparison。 | evaluate through generic adapter harness。 |
| model-controlled durable commit | false memories become permanent。 | model proposes only; core/debug/scoring approves/commits。 |
| retrieve mutates durable memory | P1 result semantics become non-deterministic。 | retrieve side-effect-free; audit only。 |
| caller-visible dropped IDs expose out-of-scope memory | privacy leak even when not returned as ranked evidence。 | dropped metadata count-only for unauthorized items。 |
| prompt projection before retrieval correctness | hides retrieval failures inside agent behavior。 | Phase E/F after Phase B/C confidence, and after Phase D when graph expansion is enabled。 |
| unsupported capability silently passes | false confidence in eval artifacts。 | structured unsupported and not_applicable / explicit failure。 |

---

## 17. Open questions

These decisions remain open and should not block Phase A/B unless the implementation cannot proceed without them。

| Question | Initial stance |
| --- | --- |
| exact storage backend | Start with simple file/SQLite-style boundary; keep schema portable。 |
| embedding/BM25 choice | Keep summary search backend-injected. Use `ollama` + `qwen3-embedding:0.6b` as the first local vector candidate, keep lexical/BM25 as deterministic baseline/fallback, and switch among vector/hybrid/lexical based on memory eval with backend identity and replay artifacts。 |
| approval UX | Begin with debug/scoring/manual approval; user-visible UX later。 |
| retention/garbage collection | Use lifecycle + tombstone/supersede first; destructive GC later with audit policy。 |
| user-visible memory editing | Defer; design card/tombstone refs so editing can be added。 |
| shared/team memory | Defer; requires explicit approval/revocation model。 |
| when to consolidate offline | Defer; consolidation should operate on provenance/candidates and preserve role-bearing evidence links。 |
| automatic invalidator watches | Start with explicit invalidator refs; add file/symbol/verifier watchers later。 |
| exact projection policy | Use recalled tool result/context packet first; prompt section later via separate design。 |

---

## Recommended next action

Recommended next action is **not** to implement the full memory subsystem immediately。

Proceed in this order:

1. Finish or make usable the generic memory eval harness Phase 0 enough to validate adapter contracts, fixture split, hashes, and dummy/broken conformance。
2. Start subsystem Phase A with schema/provenance/audit only, with forbidden-import static checks from the beginning。
3. Implement Phase B deterministic core in a small fixture-friendly way。
4. Add Phase C generic harness adapter early, before graph expansion or provider/tool integration。
5. Only after retrieval/mutation behavior is observable through the generic harness, continue to graph expansion, context packet, and read-only tool integration。

One-line plan:

```text
eval harness P0 -> typed card/provenance core -> deterministic recall/mutation -> generic adapter eval -> bounded graph/context/tool integration
```
