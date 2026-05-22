# Design 2026-05-21 - M6.25 Memory Eval Harness Implementation Plan

Status: implementation plan for M6.25 v0/v1.

Primary source: `docs/another/mem_eval_fw.md`.

Related inputs:

- `docs/another/ai_agent_mem_eval.md`
- `docs/another/REGENERATED_2026-05-21_M6_25_AGENT_MEMORY_ARCHITECTURE.md`
- `docs/REVIEW_2026-05-21_IMPLEMENTATION_INDEPENDENT_MEMORY_EVAL.md`
- `docs/REVIEW_2026-05-21_M6_25_MEMORY_TAXONOMY.md`

## 1. 目的

M6.25 で作るものは、mew の特定の記憶実装に依存しない、決定的な memory evaluation harness の v0/v1 である。

この harness は、Memory System Under Test を adapter 越しの black box として扱い、fixture、実行順、gold 分離、scoring、artifact、再現性 hash、hard gate を harness 側で所有する。adapter は実装固有 API と harness の中立 schema を変換する薄い境界であり、harness 本体は vector store、graph memory、summary store、long-context replay、MemorySystem、MemoryContextBuilder、MemoryArena のどれも前提にしない。

M6.25 の中心問いは次の 4 つに絞る。

1. 同じ fixture と adapter config から同じ run artifact を再現できるか。
2. adapter が gold を見ずに、scope、time、mutation、budget を尊重して evidence を返せるか。
3. deterministic ID scoring だけで recall、ranking、staleness、conflict、scope leak、forbidden retrieval、abstention、usage を判定できるか。
4. dummy adapter は通り、意図的に壊した adapter は予測可能に落ちるか。

## 2. 非目的

M6.25 v0/v1 では次を実装しない。

- model judge による semantic faithfulness、claim support、summary quality 判定。
- MemoryArena、Harbor、implement_v2 などの downstream agent utility 評価。
- `MemoryContextBuilder` への直接依存、または context packet builder の acceptance gate 化。
- mew memory subsystem の architecture rewrite。
- model が durable memory を直接 commit する write path。
- full leaderboard、single aggregate score、stress/longitudinal benchmark。
- raw transcript、tool log、reviewer prose を durable memory として評価対象にする設計。

これらは memory が実際の agent 行動に効くかを測るうえで重要だが、M6.25 v0/v1 の deterministic harness substrate が安定する前に入れると、memory retrieval の失敗、agent planning の失敗、judge variance、prompt leakage、実装依存 interface が混ざる。

## 3. `mem_eval_fw.md` との関係

`docs/another/mem_eval_fw.md` はこの領域の source of truth である。本書はそれを置き換えない。役割は、同 report の抽象設計から M6.25 v0/v1 だけを切り出し、後続 builder が実装できる粒度に落とすことである。

採用するもの:

- Memory Adapter による implementation-independent boundary。
- adapter に gold、expected、metric labels、anti-leak lists を渡さない原則。
- fixture、request、artifact、hash、failure object の分離。
- deterministic metric backbone: recall@k、precision@k、MRR/NDCG、stale/conflict、scope leak、forbidden retrieval、abstention、cost/latency。
- Phase 0: spec、schema、hash、golden fixtures、adapter conformance。
- Phase 1: deterministic retrieval evaluation。

M6.25 向けに狭めるもの:

- v0/v1 の required adapter contract は `manifest`、`reset`、`ingest`、`mutate`、`retrieve`、`report_usage` だけにする。
- `build_context` と `inspect_provenance` は adapter manifest で宣言できるが、M6.25 hard gate にはしない。
- adapter-visible reset に渡す hash は public fixture view の hash に限定する。artifact 側には scorer-only gold hash も記録する。
- context packet metrics と downstream utility は P2 以降へ明示的に延期する。

関連 report の扱い:

- `IMPLEMENTATION_INDEPENDENT_MEMORY_EVAL` は、mew memory subsystem は generic harness の背後の adapter の 1 つである、という boundary を補強する。
- `M6_25_MEMORY_TAXONOMY` と regenerated architecture は、fixture family と risk checklist の語彙を補助する。memory kind や architecture schema は harness 本体の必須 schema にはしない。
- `ai_agent_mem_eval` は downstream utility の重要性を補助するが、M6.25 v0/v1 の acceptance には使わない。

## 4. v0/v1 phase boundary

M6.25 が扱うのは P0 と P1 のみである。

### P0: specification and golden fixtures

目的:

- harness package の最小境界を作る。
- fixture schema と artifact schema を固定する。
- canonical JSON hash と public/gold 分離を実装する。
- dummy adapter と broken adapter で conformance test を作る。

P0 close shape:

- fixture loader が `adapter_view` と `scorer_view` を分ける。
- fixture hash、request hash、operation prefix hash、adapter config hash、scoring profile hash が安定する。
- dummy happy-path fixture が pass する。
- broken adapters がそれぞれ期待された hard gate で fail する。
- artifact に run、request、metrics、failures、hard gate result が残る。

### P1: deterministic retrieval evaluation

目的:

- adapter の `retrieve` 結果を ID-based metrics で scoring する。
- staleness、conflict、scope isolation、update/forget、abstention、budget/latency を fixture family として持つ。
- model judge、context packet、downstream agent を使わずに、memory retrieval の correctness を落とせる。

P1 close shape:

- `memory_off`、`memory_on_happy_path`、`retrieval_ranking`、`scope_isolation`、`stale_conflict`、`update_forget`、`abstention`、`budget_limited` の fixtures がある。
- aggregate artifact が metric family 別に出る。
- hard gate が pass/fail を決め、single opaque score にしない。
- unsupported capability は pass 扱いされず、`not_applicable` または explicit failure として artifact に出る。

`memory_off` は downstream utility の勝敗を測るためではなく、P1 では deterministic negative-space baseline として扱う。runner は prior experiences を ingest しない、または fixture が指定した空 state に reset し、同じ query に対して adapter が evidence を返さないこと、または abstain することを確認する。`memory_off` の metric は `memory_on` と別 bucket で artifact に出し、success delta は P4 まで計算しない。

`memory_on_happy_path` は P1 の normal memory-on baseline であり、1 scope の明白な relevant evidence を返せるかだけを見る。`retrieval_ranking`、`scope_isolation`、`stale_conflict`、`update_forget`、`abstention`、`budget_limited` は `memory_on` 系の concrete fixture families だが、fixture family 名としては上記の explicit names を使う。

### P2-P5 は延期

| Phase | 内容 | M6.25 v0/v1 で延期する理由 |
| --- | --- | --- |
| P2 | deterministic context-packet evaluation: `build_context`、context budget、redaction、raw evidence leak、provenance coverage | `build_context` の実装差が大きく、retrieval correctness と context assembly を先に分離する必要がある。raw span alignment や redaction tokenization も追加設計が必要。 |
| P3 | model-judged claim support / faithfulness | judge model、prompt、temperature、calibration、disagreement handling が必要で、M6.25 の deterministic acceptance を不安定にする。 |
| P4 | model-in-loop downstream utility、MemoryArena、agent task success | memory retrieval、agent planning、tool use、prompting、model variance が絡む。generic harness substrate が安定した後の別 acceptance layer にする。 |
| P5 | stress、robustness、longitudinal、large history、多数 user/tenant、high mutation | P1 の小さい hand-verifiable fixtures が通ってから scale する。初手で入れると failure diagnosis が粗くなる。 |

## 5. Minimal adapter contract

M6.25 v0 の required surface は次の 6 method である。実装言語や class 名は後続 builder が codebase に合わせて決めてよいが、method name と入出力の意味は固定する。

```text
manifest() -> AdapterManifest
reset(run: EvalRunSpec) -> ResetResult
ingest(items: Experience[]) -> WriteReceipt[]
mutate(ops: MemoryMutation[]) -> MutationReceipt[]
retrieve(query: MemoryQuery) -> RetrievalResult
report_usage(scope?: UsageScope) -> UsageReport
```

Optional/deferred:

```text
build_context(request: ContextBuildRequest) -> ContextPacket
inspect_provenance(refs: EvidenceRef[]) -> ProvenanceRecord[]
```

`build_context` と `inspect_provenance` は manifest に存在を宣言してよい。ただし M6.25 P0/P1 の required tests は呼ばない。adapter が提供していても scoring は retrieval artifact 中の evidence IDs と reported metadata に限定する。

### `manifest`

最低限の fields:

```json
{
  "schema_version": "memory_eval_adapter_manifest.v1",
  "adapter_id": "string",
  "adapter_version": "string",
  "memory_implementation_id": "string",
  "memory_implementation_version": "string",
  "capability_tier": "v0_surface | retrieval_only | mutable_retrieval | context_optional | auditable_optional",
  "capabilities": {
    "ingest": true,
    "mutate": true,
    "update": false,
    "delete": false,
    "forget": false,
    "supersede": false,
    "retrieve": true,
    "report_usage": true,
    "build_context": false,
    "inspect_provenance": false,
    "scope_enforcement": true,
    "latency_reporting": true,
    "cost_reporting": false,
    "deterministic_seed": true
  },
  "limits": {
    "max_payload_bytes": null,
    "max_k": null,
    "max_fixture_items": null
  }
}
```

Unsupported capability は manifest で `false` にし、method call 時にも structured result で返す。黙って近似しない。

例:

```json
{
  "op_id": "mut_003",
  "status": "unsupported",
  "unsupported_capability": "forget",
  "effective_state": {},
  "failures": [
    {
      "type": "unsupported_capability",
      "message": "Adapter does not support strong forget semantics."
    }
  ]
}
```

### `reset`

`reset` は fixture 単位の clean state を作る。fixture 間の記憶持ち越しは禁止であり、persistent cross-run を測る fixture は M6.25 v0/v1 では扱わない。

adapter-visible input:

```json
{
  "run_id": "uuid",
  "fixture_id": "fx_000001",
  "fixture_public_hash": "sha256:...",
  "seed": 12345,
  "evaluation_time": "2026-05-21T00:00:00Z"
}
```

adapter-visible `fixture_id` は harness が生成する opaque ID である。descriptive file name、fixture family、mode、trap family、expected behavior、gold labels から作ってはならない。real `scoring_profile_id`、`fixture_full_hash`、`fixture_gold_hash` は scorer artifact にだけ記録し、adapter には渡さない。adapter に profile-like token が本当に必要な場合も、`public_eval_profile_id` のような opaque value にし、`m6_25_p1_retrieval_v1` のような intent-bearing ID は渡さない。

opaque `adapter_fixture_id` / `adapter_request_id` は、deterministic hash に含めるなら同じ `fixture_public_hash`、`operation_sequence` position、seed から常に同じ値を生成する。許容例は `fx_{fixture_ordinal:06d}`、`rq_{request_ordinal:06d}`、または `rq_<sha256(fixture_public_hash + request_ordinal + seed)[:12]>`。random opaque ID を使う実装では、その ID を `request_hash`、`operation_prefix_hash`、`deterministic_result_hash` などの deterministic hashes から除外する。

### `ingest`

adapter に渡す `Experience` は externally observable experience だけである。`experience_id` は scoring のために許可されるが、`gold` labels は含めない。

adapter-visible fields:

```json
{
  "experience_id": "exp_001",
  "scope_id": "tenant_a/user_17",
  "session_id": "session_001",
  "turn_id": "turn_003",
  "event_time": "2026-01-10T09:00:00Z",
  "ingest_order": 1,
  "actor_id": "user_17",
  "payload": {
    "mime_type": "text/plain",
    "text": "User prefers meetings after 10 AM."
  },
  "visibility": {
    "allowed_scope_ids": ["tenant_a/user_17"],
    "retrievable": true
  },
  "metadata": {
    "source_kind": "conversation"
  }
}
```

adapter-hidden fields:

- relevant / irrelevant / stale / conflicting labels。
- expected answer。
- must-not-return IDs。
- forbidden evidence IDs。
- fixture family labels that identify the trap。

### `mutate`

`mutate` method は v0 surface として必須だが、個別 op の support は manifest で宣言する。

required op vocabulary:

- `update`: evidence lineage を保った修正。
- `delete`: normal retrieval から外す。
- `forget`: 評価上、retrieve、expose、summarize、support use を禁止する強い忘却。
- `supersede`: old evidence を stale/superseded にし、replacement を active にする。

P1 の replacement handling は 1 つに固定する。replacement experiences は通常の `Experience` record として mutation op より前に `operation_sequence` で ingest する。mutation op は `replacement_experience_id` を参照するだけで、`mutate` call が追加の duplicate replacement item を作ってはならない。nested replacement creation は P2 以降に延期し、P1 に持ち込む場合は runner が事前に canonical expansion してから adapter に渡す。

P1 の `stale_conflict` と `update_forget` fixture は必要 capability を持つ adapter だけが pass 対象になる。capability がない adapter では、runner は fixture result を `not_applicable` にするか、conformance fixture なら expected failure とする。unsupported を successful pass として集計してはならない。

### `retrieve`

`retrieve` は final answer ではなく ranked evidence refs を返す。

adapter-visible input:

```json
{
  "request_id": "rq_000001",
  "scope_id": "tenant_a/user_17",
  "query_time": "2026-03-01T12:00:00Z",
  "query": {
    "text": "When should I schedule a meeting with the user?",
    "intent": "preference_lookup"
  },
  "k": 5,
  "filters": {
    "valid_at": "2026-03-01T12:00:00Z",
    "allowed_states": ["active"]
  },
  "budget": {
    "max_evidence_items": 5,
    "max_latency_ms": 200,
    "max_cost_units": null
  }
}
```

`request_id` も opaque ID であり、descriptive fixture file name、mode name、trap family、expected behavior、gold labels から作らない。`mode` はこの adapter-visible request には含めない。`stale_conflict`、`scope_isolation`、`update_forget`、`abstention`、`budget_limited` などは trap family label として scorer/artifact 側だけに置く。adapter が test family 名で分岐できる状態は gold leakage と同じ扱いにする。

required output:

```json
{
  "request_id": "rq_000001",
  "ranked_evidence": [
    {
      "evidence_ref": "mem_77",
      "evidence_id": null,
      "rank": 1,
      "score": null,
      "score_type": "none",
      "support_experience_ids": ["exp_012"],
      "source_mutation_ids": ["mut_001"],
      "state": "active",
      "scope_id": "tenant_a/user_17",
      "provenance_refs": ["prov_012"]
    }
  ],
  "abstained": false,
  "abstained_reason": null,
  "dropped": [
    {
      "count": 1,
      "reason": "out_of_scope"
    }
  ],
  "usage": {
    "latency_ms": {
      "retrieve": 34.1,
      "total": 34.1,
      "source": "harness_measured"
    },
    "tokens": {
      "adapter_internal_input_tokens": null,
      "adapter_internal_output_tokens": null,
      "methodology": "not_reported"
    },
    "cost": {
      "cost_units": null,
      "currency": null,
      "methodology": "not_reported"
    }
  },
  "failures": []
}
```

`rank` は required である。`score` は optional/nullable で、native score がない adapter は `{ "score": null, "score_type": "none" }` を返してよい。P1 metrics は native score に依存せず、rank と support IDs だけを使う。

P1 は raw evidence store だけでなく、derived/summarized memory も scoring できる。adapter が `mem_77` のような derived ref を返す場合、`support_experience_ids` を provenance-lite scoring input として返す。P1 adapter は `support_experience_ids` を emit するべきで、`source_experience_ids` は legacy alias としてだけ受け付ける。`support_experience_ids` がある場合、`source_experience_ids` は原則 omit する。両方が non-empty で存在する場合は canonical set normalization 後に同一でなければならず、不一致は `failure.type=support_source_mismatch`、`gate_id=support_source_consistency` で hard fail にする。

P1 で `source_experience_ids` を使う場合も、意味は current-query support source に限定する。これは historical lineage ではない。stale historical lineage は、その stale item を current query で expose/use する場合以外、P1 support IDs に含めない。`lineage_experience_ids` は report-only/P2 provenance であり、P1 scoring には使わない。full `inspect_provenance` は P2 以降に延期する。

P0/P1 の `retrieve` は durable-memory side-effect free でなければならない。検索履歴、query summary、last accessed marker などを durable memory として書いたり、将来の retrieval result semantics を変えたりしてはならない。ephemeral cache は、returned evidence semantics に影響せず、memory evidence として露出しない場合だけ許可する。

### `report_usage`

`report_usage` は run または fixture の aggregate usage を返す。per-request `usage` と同じ source/methodology vocabulary を使う。cost が `null` の場合は unknown であり、`methodology=zero_cost` のときだけ zero と解釈する。latency reporting は `adapter_reported` と `harness_measured` の両方を許可し、hidden model calls の診断のために source を artifact に残す。latency reporting capability が true の adapter で latency が欠けたら hard failure にする。

## 6. Capability tiers

M6.25 の比較では tier を artifact に明示し、異なる tier を同一 leaderboard のように比較しない。

| Tier | Required surface | Scored fixtures |
| --- | --- | --- |
| `v0_surface` | 6 required methods が存在する。個別 mutation op は unsupported でも structured に返る。 | P0 conformance only。 |
| `retrieval_only` | `reset`、`ingest`、`retrieve`、`report_usage` が実質動作する。`mutate` は method として存在し unsupported を返せる。 | happy path、ranking、scope isolation、abstention、budget。 |
| `mutable_retrieval` | `update`、`delete`、`forget`、`supersede` のうち fixture が要求する op を実装する。 | stale/conflict、update/forget。 |
| `context_optional` | `build_context` を持つ。 | P2 以降。M6.25 P0/P1 では report-only。 |
| `auditable_optional` | `inspect_provenance` と redaction lineage を持つ。 | P2 以降。M6.25 P0/P1 では report-only。 |

unsupported representation:

- manifest capability は `false`。
- method result は `status=unsupported` または request-level failure。
- runner は `requires_capabilities` を fixture/scoring profile から読み、unsupported fixture を `not_applicable`、`expected_failure`、`hard_failure` のいずれかに分類する。
- unsupported が空 result や low score として隠れる状態は anti-pattern として fail する。

Capability requirement shape:

```json
{
  "requires_capabilities": ["retrieve", "scope_enforcement", "supersede"],
  "on_unsupported": "not_applicable"
}
```

`requires_capabilities` は fixture request または scoring profile のどちらにも置ける。request-level definition が profile-level default を上書きする。`on_unsupported` の値は次の 3 つだけにする。

| Value | Runner behavior |
| --- | --- |
| `not_applicable` | adapter manifest が required capability を欠く場合、その request は score denominator から外し、artifact に `not_applicable` result と failure object を残す。 |
| `expected_failure` | broken adapter conformance 用。unsupported が返れば expected result として扱うが、pass score には混ぜない。 |
| `hard_failure` | capability が必須の acceptance fixture。unsupported、無視、または unsupported-as-success は hard fail。 |

## 7. Fixture model: public/private separation

Fixture は 1 つの canonical file に public と scorer-only information を持てる。ただし adapter call の直前に必ず分離する。

```text
canonical fixture
  -> adapter_view: reset/ingest/mutate/retrieve に渡す public data
  -> scorer_view: gold、must-not、stale/conflict labels、hard gates
  -> artifact_view: public hash、gold hash、run result、metrics
```

### Operation sequence

Fixture は experiences、mutations、requests を単に並列 arrays として持つだけではなく、runner が適用する canonical timeline を持つ。

```json
{
  "operation_sequence": [
    {"type": "ingest", "experience_id": "exp_001", "ingest_order": 1},
    {"type": "ingest", "experience_id": "exp_012", "ingest_order": 12},
    {"type": "mutate", "op_id": "mut_001", "ingest_order": 13},
    {"type": "request", "request_id": "req_stale_conflict_001", "after_ingest_order": 13}
  ]
}
```

runner はこの sequence を source of truth とし、request に到達するまでの ingest/mutate prefix を adapter に適用してから `retrieve` を呼ぶ。`operation_prefix_hash` は、その request より前に適用済みの public operations を ordered canonical form で hash する。P1 の `stale_conflict` と `update_forget` は、event time、ingest order、mutation effective time、query time の全てを fixture に明示し、scorer はこれらを scorer_view から計算する。

### Adapter-visible data

adapter に見せてよいもの:

- opaque/sanitized `fixture_id`、`fixture_version`。
- public scopes と allowed scope IDs。
- experiences の `experience_id`、scope、time、actor、payload、source kind。
- mutations の op type、target IDs、`replacement_experience_id`、effective time、reason。
- request の opaque/sanitized `request_id`、scope、query time、query text/intent、k、filters、budget。
- adapter config、seed、evaluation time。

Adapter-visible `fixture_id` と `request_id` は、runner が fixture load 時に生成する opaque ID にする。deterministic hash に含める ID は deterministic opaque ID にし、random opaque ID は deterministic hashes から除外する。例は `fx_{fixture_ordinal:06d}`、`rq_{request_ordinal:06d}`、または `rq_<sha256(fixture_public_hash + request_ordinal + seed)[:12]>` である。禁止する ID source は次の通り。

- descriptive fixture file name: `stale_conflict_supersede_basic.json` など。
- fixture family metadata: `scope_isolation`、`budget_limited` など。
- request `mode`。
- trap family: `trap`、`leak`、`forbidden`、`stale`、`conflict` など。
- expected behavior: `should_abstain`、`must_fail`、`expected_recall` など。
- gold label: `relevant`、`must_not_return`、`fresh_ids`、`stale_ids` など。

Scorer/artifact は canonical fixture ID、descriptive file path、fixture family、mode と opaque adapter IDs の mapping を持てる。ただし adapter call payload に入るのは opaque IDs だけである。

### Scorer-only `gold`

adapter に見せてはいけないもの:

- `relevant_evidence_ids`。
- `acceptable_support_sets`。
- `must_not_return_evidence_ids`。
- `must_not_context_evidence_ids`。
- `stale_evidence_ids`。
- `forgotten_evidence_ids`。
- `conflict_sets`。
- `expected_abstention`。
- `graded_gains`。
- `hard_gates`。
- request `mode`。
- trap family labels such as `scope_leak_trap`。
- forbidden raw spans, if present for future P2。

Request-level scorer metadata can define capability requirements and unsupported behavior:

```json
{
  "request_id": "req_003",
  "mode": "stale_conflict",
  "requires_capabilities": ["retrieve", "supersede"],
  "on_unsupported": "hard_failure",
  "gold": {
    "relevant_evidence_ids": ["exp_fresh"],
    "stale_evidence_ids": ["exp_old"],
    "expected_abstention": false
  }
}
```

この block は scorer view にだけ存在する。adapter view に入る request は対応する opaque `request_id`、例えば `rq_000003` を持つが、scorer-side descriptive `request_id`、`mode`、`requires_capabilities`、`on_unsupported`、`gold` を含まない。

### Leakage prevention checks

P0 で次の tests を必須にする。

- adapter view serialization に `gold` key が含まれない。
- adapter view serialization に `mode`、`trap`、`family`、`relevant`、`must_not`、`expected`、`stale_evidence_ids`、`conflict_sets` などの scorer-only key が含まれない。
- adapter view serialization の全 string values を scan し、blocked tokens が含まれないことを確認する。これは keys だけでなく、`fixture_id`、`request_id`、file path、query intent、metadata、payload text など、adapter に渡す input values も対象にする。
- blocked tokens for P0/P1: `memory_off`、`memory_on`、`scope_isolation`、`stale_conflict`、`update_forget`、`abstention`、`budget_limited`、`trap`、`leak`、`forbidden`、`stale`、`conflict`。
- value scan は lowercase 化し、hyphen、slash、dot、space を underscore 相当に正規化した文字列にも適用する。例: `scope-isolation`、`scope/isolation`、`scope isolation` も `scope_isolation` と同じ leak として扱う。
- P0/P1 conformance fixtures は public text 内でも blocked tokens を避ける。どうしても domain text に必要な場合は、M6.25 v0/v1 では fixture を採用せず、後続 phase で explicit allowlist と reviewer approval を追加してから扱う。
- `semantic_annotations` を public に出す場合でも、`later_superseded`、`expected_current`、`trap` のような scoring label は除去する。
- adapter reset に full/gold hash を渡さない。
- request ID や fixture ID に answer、mode、fixture family、trap family、expected behavior、gold label を埋め込まない naming convention を fixture authoring rule にする。

## 8. Artifact schema and reproducibility hashes

P0/P1 artifact は JSON を主形式にする。Markdown summary は任意だが source of record ではない。

P0/P1 が要求する再現性は、artifact 全体の bitwise reproducibility ではない。`run_id`、`created_at`、latency、cost、environment などは run ごとに変わる。hash conformance は deterministic content hashes、特に `fixture_public_hash`、`fixture_gold_hash`、`request_hash`、`operation_prefix_hash`、`scoring_profile_hash`、`retrieval_result_hash` の安定性を対象にする。

### Run artifact

```json
{
  "schema_version": "memory_eval_artifact.v1",
  "run_id": "run_2026_05_21_001",
  "created_at": "2026-05-21T10:00:00Z",
  "phase": "P0 | P1",
  "harness": {
    "harness_id": "mew-memory-eval",
    "harness_version": "0.1.0",
    "scoring_profile_id": "m6_25_p1_retrieval_v1",
    "scoring_profile_hash": "sha256:..."
  },
  "fixture": {
    "fixture_id": "stale_conflict_supersede_basic",
    "adapter_fixture_id": "fx_000001",
    "fixture_version": "1.0.0",
    "fixture_public_hash": "sha256:...",
    "fixture_gold_hash": "sha256:...",
    "fixture_full_hash": "sha256:..."
  },
  "adapter": {
    "adapter_id": "string",
    "adapter_version": "string",
    "memory_implementation_id": "string",
    "memory_implementation_version": "string",
    "adapter_config_hash": "sha256:...",
    "capability_manifest_hash": "sha256:...",
    "capability_tier": "retrieval_only"
  },
  "environment": {
    "python_version": "optional",
    "platform": "optional",
    "external_model_ids": [],
    "seed": 12345
  },
  "artifact_hashes": {
    "deterministic_result_hash": "sha256:...",
    "retrieval_result_hash": "sha256:...",
    "volatile_run_hash": "sha256:...",
    "volatile_usage_hash": "sha256:..."
  },
  "volatile_fields": [
    "run_id",
    "created_at",
    "usage.latency_ms",
    "usage.cost",
    "usage.tokens.adapter_internal_input_tokens",
    "usage.tokens.adapter_internal_output_tokens",
    "environment"
  ],
  "requests": [],
  "aggregate_metrics": {},
  "hard_gates": [],
  "failures": []
}
```

### Per-request artifact

```json
{
  "request_id": "req_stale_conflict_001",
  "adapter_request_id": "rq_000001",
  "result_status": "passed",
  "score_denominator_included": true,
  "gate_denominator_included": true,
  "unsupported_capabilities": [],
  "status_reason": null,
  "request_hash": "sha256:...",
  "operation_prefix_hash": "sha256:...",
  "retrieval_result_hash": "sha256:...",
  "mode": "stale_conflict",
  "scope_id_hash": "sha256:...",
  "input_summary": {
    "k": 5,
    "max_evidence_items": 5,
    "max_latency_ms": 200
  },
  "retrieval": {
    "returned_evidence_order": [
      {
        "evidence_ref": "mem_77",
        "evidence_id": null,
        "rank": 1,
        "score": null,
        "score_type": "none",
        "support_experience_ids": ["exp_012"],
        "source_mutation_ids": ["mut_001"],
        "scorable_support_ids": ["exp_012"],
        "state_reported_by_adapter": "active",
        "scope_id_hash": "sha256:..."
      }
    ],
    "abstained": false,
    "abstained_reason": null,
    "visible_dropped": [
      {
        "count": 1,
        "reason": "out_of_scope"
      }
    ],
    "visible_provenance_derived_evidence_ids": [],
    "hash_usage_fields": {
      "latency_source": "harness_measured",
      "cost_methodology": "not_reported",
      "token_methodology": "not_reported"
    }
  },
  "usage": {
    "latency_ms": {
      "retrieve": 34.1,
      "total": 34.1,
      "source": "harness_measured"
    },
    "tokens": {
      "adapter_internal_input_tokens": null,
      "adapter_internal_output_tokens": null,
      "methodology": "not_reported"
    },
    "cost": {
      "cost_units": null,
      "currency": null,
      "methodology": "not_reported"
    }
  },
  "metrics": {
    "recall_at_5": 1.0,
    "precision_at_5": 0.2,
    "mrr_at_5": 1.0,
    "ndcg_at_5": 1.0,
    "stale_as_fresh": 0.0,
    "contradiction_as_fresh": 0.0,
    "cross_scope_leak_rate": 0.0,
    "cross_scope_exposure_rate": 0.0,
    "forbidden_retrieval_rate": 0.0,
    "abstention_correct": 1.0,
    "budget_violation": 0
  },
  "hard_gates": [
    {
      "gate_id": "no_cross_scope_leak",
      "passed": true,
      "reason": "No returned evidence was outside authorized scope."
    }
  ],
  "failures": []
}
```

`result_status` vocabulary:

| Status | Meaning |
| --- | --- |
| `passed` | Request was applicable and all hard gates passed. Included in score/gate denominators. |
| `failed` | Request was applicable and at least one hard gate failed. Included in denominators. |
| `not_applicable` | Adapter lacks declared required capability and `on_unsupported=not_applicable`. This is not a failure and is excluded from score/gate denominators. |
| `expected_failure` | Broken-adapter conformance expected the failure. Excluded from normal pass denominators. |
| `skipped` | Runner did not execute the request for an explicit harness reason. Excluded from denominators and must include `status_reason`. |

`retrieval_result_hash` は deterministic scoring/exposure hash である。含めるもの:

- returned evidence order: `rank`, `evidence_ref`, `evidence_id`。
- `support_experience_ids` / `source_experience_ids`、`source_mutation_ids`。
- derived `scorable_support_ids` used by P1 metrics。
- abstention fields: `abstained`、`abstained_reason`。
- caller-visible dropped records such as count-only out-of-scope drops。
- caller-visible provenance-derived evidence IDs, if any。
- stable usage labels only, if included: latency source, cost methodology, token methodology。

含めないもの: measured latency、measured cost、token counts、`run_id`、`created_at`、environment。measured usage values は `retrieval_result_hash` ではなく、`volatile_run_hash` または `volatile_usage_hash` に入れる。

P1 では `context` と `provenance` blocks は必須にしない。将来の P2 で追加する場合も、schema_version を上げるか optional block として扱う。

### Failure object

`failures` は run artifact、per-request artifact、adapter operation result、hard gate result のどこからでも同じ object shape で参照する。これにより failure hash と reviewer diagnosis を安定させる。

Required fields:

```json
{
  "failure_id": "fail_req_001_no_cross_scope_leak",
  "stage": "reset | ingest | mutate | retrieve | scoring | hashing | artifact",
  "severity": "error | warning | info",
  "type": "cross_scope_leak",
  "message": "Returned evidence exp_other_user is outside requested scope.",
  "request_id": "req_001",
  "operation_id": null,
  "evidence_id": "exp_other_user",
  "gate_id": "no_cross_scope_leak",
  "metric_id": "cross_scope_leak_rate",
  "expected": 0,
  "actual": 1,
  "adapter_status": "success",
  "retry_count": 0,
  "hash": "sha256:..."
}
```

Attachment rules:

- adapter method failure は該当 operation result の `failures` と per-request artifact の `failures` に入れる。
- hard gate failure は `hard_gates[]` の `gate_id` と同じ `gate_id` を持つ failure object を作る。
- run-wide failure は run artifact の `failures` に入れ、request が特定できる場合は `request_id` も埋める。
- `hash` は failure object 自体を canonicalized した hash で、`hash` field は計算対象から除外する。

Canonical failure types:

| Type | Example gate/linkage |
| --- | --- |
| `unsupported_capability` | `requires_capabilities` mismatch。`gate_id=required_capability_supported`。 |
| `hash_mismatch` | fixture/request/result hash が再計算値と違う。`stage=hashing`。 |
| `metric_hard_gate` | metric threshold failure。`metric_id` と `gate_id` を必須にする。 |
| `invalid_ranking` | duplicate `returned_item_identity`、rank gap、rank starts other than 1、returned count > k。 |
| `invalid_support_reference` | `scorable_support_ids(e)` に入る experience ref、または source/support mutation ref が malformed、または request prefix と照合できない。 |
| `unknown_evidence_reference` | `support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id`、source/support mutation ID が fixture public operations に存在しない。 |
| `future_evidence_reference` | `support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id`、source/support mutation ID が request 時点の `operation_sequence` prefix にまだ適用されていない。 |
| `support_source_mismatch` | `support_experience_ids` と P1 legacy `source_experience_ids` が両方 non-empty で、canonical set normalization 後に一致しない。`gate_id=support_source_consistency`。 |
| `duplicate_support_reference` | 複数 returned items が同じ non-empty `support_signature` を持つ。`gate_id=no_duplicate_support_reference`。 |
| `unscorable_evidence` | returned item が `evidence_ref` を持つが、`support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id` のいずれもなく、`scorable_support_ids(e)` が空。`gate_id=required_support_mapping_present`。 |
| `label_leakage` | adapter view の keys または string values に `gold`、`mode`、trap label、blocked token、must-not IDs、descriptive fixture family などが入った。 |
| `cross_scope_leak` | unauthorized scope evidence returned。 |
| `forbidden_retrieval` | `must_not_return_evidence_ids` が returned evidence に含まれる。 |
| `stale_as_fresh` | strict stale fixture で stale/superseded/forgotten evidence が fresh として返る。 |
| `contradiction_as_fresh` | conflict set の stale/fresh evidence が同時に fresh 扱いで返る。 |
| `abstention_mismatch` | expected abstention と actual abstention が一致しない。 |
| `budget_violation` | k/max_evidence_items/declared latency/cost hard budget violation。 |
| `missing_usage` | manifest が usage reporting を宣言しているのに latency/cost/token field が欠ける。 |

Example: unsupported capability。

```json
{
  "failure_id": "fail_req_004_forget_unsupported",
  "stage": "mutate",
  "severity": "error",
  "type": "unsupported_capability",
  "message": "Fixture requires forget but adapter manifest has forget=false.",
  "request_id": "req_004",
  "operation_id": "mut_009",
  "evidence_id": null,
  "gate_id": "required_capability_supported",
  "metric_id": null,
  "expected": "forget=true",
  "actual": "forget=false",
  "adapter_status": "unsupported",
  "retry_count": 0,
  "hash": "sha256:..."
}
```

Example: hard gate failure。

```json
{
  "failure_id": "fail_req_002_strict_stale",
  "stage": "scoring",
  "severity": "error",
  "type": "stale_as_fresh",
  "message": "Strict stale fixture returned exp_001 as active.",
  "request_id": "req_002",
  "operation_id": null,
  "evidence_id": "exp_001",
  "gate_id": "no_stale_as_fresh",
  "metric_id": "stale_as_fresh",
  "expected": 0,
  "actual": 1,
  "adapter_status": "success",
  "retry_count": 0,
  "hash": "sha256:..."
}
```

### Scoring profile schema

Scoring profile は metric cutoff、hard gate、capability requirement、aggregation を固定し、`scoring_profile_hash` の入力になる。fixture request が同じ field を持つ場合、request-level value が profile default を上書きする。

```json
{
  "schema_version": "memory_eval_scoring_profile.v1",
  "profile_id": "m6_25_p1_retrieval_v1",
  "phase": "P1",
  "metric_cutoffs": {
    "dummy_happy_path": {
      "recall_at_k_min": 1.0,
      "mrr_at_k_min": 1.0
    },
    "retrieval_ranking": {
      "recall_at_k_min": 1.0,
      "mrr_at_k_min": 0.5,
      "ndcg_at_k_min": 0.75
    }
  },
  "hard_gates": [
    "no_cross_scope_leak",
    "no_cross_scope_exposure",
    "no_forbidden_retrieval",
    "no_stale_as_fresh_when_strict",
    "no_contradiction_as_fresh_when_strict",
    "abstention_matches_expected",
    "item_budget_respected",
    "required_usage_present",
    "valid_rank_ordering",
    "no_unknown_or_future_support_refs",
    "required_support_mapping_present",
    "support_source_consistency",
    "no_duplicate_support_reference",
    "required_capability_supported",
    "no_label_leakage"
  ],
  "requires_capabilities": ["retrieve"],
  "on_unsupported": "hard_failure",
  "hard_latency_budget": false,
  "hard_cost_budget": false,
  "aggregation": {
    "group_by": ["mode", "fixture_family", "capability_tier"],
    "single_score": false,
    "include_not_applicable_in_denominator": false
  }
}
```

### Hashing rules

canonicalization:

- JSON object keys sorted。
- UTF-8。
- Unicode NFC。
- insignificant whitespace removed。
- timestamp は RFC3339 で normalized。
- arrays whose order is semantic keep order。
- sets are sorted before hashing。

required hashes:

| Hash | Include |
| --- | --- |
| `fixture_public_hash` | adapter-visible fixture view。gold と hard gates は含めない。adapter reset に渡してよい。 |
| `fixture_gold_hash` | scorer-only `gold`、hard gate definitions、private labels。adapter には渡さない。 |
| `fixture_full_hash` | public + gold を canonical に合わせた fixture source identity。artifact only。 |
| `request_hash` | adapter-visible request: scope、query time、query、filters、k、budget。`mode` と scorer-side descriptive `request_id` は含めない。opaque `adapter_request_id` を含める場合は deterministic に生成されたものだけにする。random opaque ID は除外する。 |
| `operation_prefix_hash` | request 前に `operation_sequence` で適用済みの public ingests と mutations の ordered prefix。 |
| `adapter_config_hash` | adapter config、model IDs、retrieval limits、seeds、feature flags。 |
| `capability_manifest_hash` | normalized manifest。 |
| `scoring_profile_hash` | metric definitions、cutoffs、hard gates、aggregation rules。M6.25 v0/v1 では judge prompt は存在しない。 |
| `retrieval_result_hash` | deterministic scoring/exposure hash: returned evidence order, `evidence_ref`/`evidence_id`, `support_experience_ids` or P1 support-only `source_experience_ids`, `source_mutation_ids`, derived `scorable_support_ids`, abstention fields, visible dropped records, visible provenance-derived evidence IDs, and optional stable usage source/methodology labels. Excludes measured latency, measured cost, token counts, `run_id`, `created_at`, and environment. |
| `deterministic_result_hash` | volatile fields を除いた request results、metrics、gate outcomes、deterministic hashes。 |
| `volatile_run_hash` | run_id、created_at、usage latency/cost、environment など volatile fields を含む run identity。比較用途では補助情報。 |
| `volatile_usage_hash` | measured latency/cost/token counts を含む optional usage hash。deterministic scoring comparison には使わない。 |

hash mismatch は reproducibility failure として artifact に残す。

## 9. Deterministic metrics and hard gates

P1 の metric は scorer_view の source-of-truth IDs と request gold だけで計算する。text similarity や model judge は使わない。

Adapter-reported `state` と `scope` は diagnostics only である。scorer MUST compute freshness and scope from scorer_view / fixture source of truth. Adapter-reported state and scope MUST NOT be trusted for hard gate decisions.

Let:

- `R(q)`: gold relevant evidence IDs。
- `M(q)`: must-not-return evidence IDs。
- `S(q)`: stale、superseded、expired、forgotten evidence IDs。
- `L(q)`: requested scope から unauthorized な evidence IDs。
- `E_k(q)`: adapter が返した top-k evidence refs。
- `support(e)`: scorer が evidence ref `e` に対応付ける source support IDs。
- `H_k(q)`: `union(scorable_support_ids(e) for e in E_k(q))`。
- `rank(e)`: `E_k(q)` における evidence `e` の 1-based rank。

P1 support mapping:

```text
scorable_support_ids(e) =
  if support_experience_ids exists and is non-empty then support_experience_ids
  else if source_experience_ids exists and is non-empty then source_experience_ids
  else if evidence_id exists then [evidence_id]
  else []
```

`support_experience_ids` は current query で returned item の evidence として使われる support sources である。P1 で `source_experience_ids` を使う場合も同じ意味に限定する。all historical lineage を入れてはならない。`lineage_experience_ids` は artifact-only diagnostics または P2 `inspect_provenance` の対象であり、P1 scoring には使わない。

P1 default profile では unscorable returned item を許可しない。すべての returned item は non-empty `scorable_support_ids(e)` を持たなければならない。`evidence_ref` があるのに `support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id` がなく `scorable_support_ids(e)` が空になる場合、`failure.type=unscorable_evidence`、`gate_id=required_support_mapping_present` で hard fail にする。この制約は P2 で `inspect_provenance` が deterministic に provenance traversal できるようになった後にだけ緩和できる。

`support_experience_ids` と `source_experience_ids` が両方 non-empty の場合、canonical set normalization 後に同一でなければならない。異なる場合は `failure.type=support_source_mismatch`、`gate_id=support_source_consistency` で hard fail にし、片方だけを信じて scoring してはならない。

Support reference validity is a hard gate:

```text
scorable_support_ids(e) ⊆ public_experience_ids_applied_before(q)
source_mutation_ids(e) ⊆ public_mutation_ids_applied_before(q)
```

The first rule validates every experience ID that can enter `scorable_support_ids(e)`: `support_experience_ids`, P1 support-only legacy `source_experience_ids`, and fallback `evidence_id`. Unknown IDs, malformed IDs, future evidence IDs, future mutation IDs, and not-yet-ingested replacement IDs fail `no_unknown_or_future_support_refs`. If a future P1-compatible adapter emits `support_mutation_ids`, the same mutation-prefix rule applies to that field. This prevents future evidence or not-yet-applied mutations from matching gold by accident.

Returned item identity and duplicate support rules:

```text
returned_item_identity(e) =
  evidence_ref if evidence_ref is non-empty,
  else evidence_id
```

Duplicate `returned_item_identity` は `invalid_ranking` として hard fail にする。

```text
support_signature(e) = sorted(scorable_support_ids(e))
```

P1 default profile では、2 つ以上の returned items が同じ non-empty `support_signature` を持ってはならない。後続 item を non-relevant duplicate として扱う選択肢は P2 以降の大規模/曖昧 fixture 向けであり、小さい deterministic P1 fixtures では `failure.type=duplicate_support_reference`、`gate_id=no_duplicate_support_reference` で hard fail にする。

```text
item_relevant(e, q) =
  1 if scorable_support_ids(e) ∩ R(q) is non-empty,
  else 0
```

### Retrieval metrics

```text
support_recall@k(q) = |H_k(q) ∩ R(q)| / |R(q)|
```

P1 の `recall@k` は `support_recall@k` を primary recall として report してよい。実装では `E_k(q)` をそのまま fixture IDs と比較せず、`H_k(q)` と `R(q)` を比較する。

`|R(q)| = 0` の fixture では使わず、abstention / negative-space を見る。

P1 `precision@k` は item-level で定義する。support ID 数で割る定義は、derived memory item が複数 relevant support IDs を持つと 1.0 を超える可能性があるため使わない。

```text
precision@k(q) =
  sum(item_relevant(e, q) for e in E_k(q)) / k
```

adapter が k 未満しか返さない場合、default scoring では未返却 rank を non-relevant item と数える。

Optional support precision:

```text
support_precision@k(q) = |H_k(q) ∩ R(q)| / max(1, |H_k(q)|)
```

```text
MRR@k(q) = 1 / rank(first relevant evidence in E_k(q))
```

ここで relevant evidence とは `item_relevant(e, q)=1` の returned evidence ref を指す。top-k に relevant item がなければ 0。

```text
DCG@k(q) = Σ_i=1..k gain_i / log2(i + 1)
NDCG@k(q) = DCG@k(q) / IDCG@k(q)
```

P1 は item-level binary gain を default にする。

```text
gain_i = 1 if scorable_support_ids(E_i) ∩ R(q) is non-empty else 0
```

fixture が `graded_gains` を持つ場合のみ graded NDCG を有効にする。graded gains は scorer-only。

### Freshness and conflict

```text
stale_as_fresh(q) =
  |{id in H_k(q): id in S(q)}| / max(1, |H_k(q)|)
```

strict stale fixture では、stale evidence を返すだけでも fail にできる。historical query fixture は future work で別 profile にする。

```text
contradiction_as_fresh(q) =
  1 if any conflict_set has stale_ids and fresh_ids both present in H_k(q)
       for a strict current-state query,
  else 0
```

freshness preference:

```text
freshness_preference_accuracy(q) =
  1 if highest-ranked evidence from the conflict family is fresh,
  else 0
```

### Isolation and forbidden retrieval

```text
cross_scope_leak_rate(q) =
  |{id in H_k(q): scope_from_scorer_view(id) not authorized for q}| /
  max(1, |H_k(q)|)
```

```text
any_cross_scope_leak(q) = 1 if cross_scope_leak_rate(q) > 0 else 0
```

All caller-visible exposure surfaces are gated, not just ranked evidence. Define:

```text
exposed_evidence_ids(q) =
  H_k(q)
  union visible_dropped_evidence_ids
  union visible_provenance_derived_evidence_ids
```

```text
cross_scope_exposure_rate(q) =
  |{id in exposed_evidence_ids(q): scope_from_scorer_view(id) not authorized for q}| /
  max(1, |exposed_evidence_ids(q)|)
```

`dropped` in caller-visible P1 adapter output must not list unauthorized evidence IDs. For out-of-scope drops, use count-only records such as `{ "count": 3, "reason": "out_of_scope" }`. If harness internals need exact dropped IDs for diagnostics, keep them artifact-only after scoring and never expose them to the adapter caller.

```text
forbidden_retrieval_rate(q) =
  |H_k(q) ∩ M(q)| / max(1, |H_k(q)|)
```

### Abstention and negative space

```text
abstention_correct(q) =
  1 if expected_abstention(q) == actual_abstention(q),
  else 0
```

```text
negative_space_correct(q) =
  1 if R(q) = empty and adapter abstains or returns no supporting memory,
  else 0
```

false abstention と missed abstention を分けて aggregate する。

```text
false_abstention_rate =
  answerable_requests_abstained / max(1, answerable_requests)
```

```text
missed_abstention_rate =
  unanswerable_requests_not_abstained / max(1, unanswerable_requests)
```

### Budget, latency, cost

P1 required reporting:

- returned item count。
- retrieve latency。
- total run latency。
- cost units or explicit `null` with reporting methodology。
- token usage with `not_reported | tokenizer_estimated | provider_reported` methodology。

```text
budget_violation(q) =
  1 if returned_items > min(k, max_evidence_items), else 0
```

```text
latency_violation(q) =
  1 if fixture declares max_latency_ms and retrieve_latency_ms > max_latency_ms,
  else 0
```

```text
cost_violation(q) =
  1 if fixture declares max_cost_units and adapter cost_units > max_cost_units,
  else 0
```

latency/cost は environment variance があるため、default profile では report-first にする。ただし fixture または scoring profile が `hard_latency_budget=true` / `hard_cost_budget=true` を宣言した場合は hard gate にする。

### Hard gate examples

以下は P1 の default hard gates とする。

- `cross_scope_leak_rate > 0` or `cross_scope_exposure_rate > 0`: hard fail。
- `forbidden_retrieval_rate > 0`: hard fail。
- strict stale fixture で `stale_as_fresh > 0`: hard fail。
- strict conflict fixture で `contradiction_as_fresh > 0`: hard fail。
- abstention fixture で `expected_abstention=true` かつ returned evidence がある: hard fail。
- answerable fixture で adapter が abstain し、fixture が false abstention を許可していない: hard fail。
- returned item count が `k` または `max_evidence_items` を超える: hard fail。
- manifest で latency reporting true なのに retrieve latency が欠ける: hard fail。
- required capability fixture に対して unsupported を success として返す: hard fail。
- returned item が `evidence_ref` を持つが `scorable_support_ids(e)` が空: hard fail。
- non-empty `support_experience_ids` と non-empty `source_experience_ids` が canonical set normalization 後に一致しない: hard fail。
- `scorable_support_ids(e)` に入る `support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id`、または source/support mutation IDs が unknown または request prefix より未来: hard fail。
- duplicate `returned_item_identity`、duplicate non-empty `support_signature`、or invalid rank ordering: hard fail。

Threshold gates:

- dummy happy path: `recall@k = 1.0`、`MRR@k = 1.0`。
- ranking fixture: `MRR@k >= configured_threshold` and `NDCG@k >= configured_threshold`。
- budget fixture: relevant evidence が budget 内 top-k に入ること。

## 10. Initial fixture families for P0/P1

P0 fixtures:

| Family | Purpose | Expected result |
| --- | --- | --- |
| `dummy_happy_path` | 1 scope、2 experiences、1 obvious query。dummy adapter が exact ID を返す。 | pass: recall@1=1、precision@1=1、MRR=1。 |
| `broken_adapter_expected_failures` | leak、wrong rank、forbidden ID、missing usage、unsupported-as-success などを個別に返す adapters。表の file names は illustrative だが、close criteria では default hard gate ごとに最低 1 つの broken fixture を要求する。 | each fixture fails with the intended hard gate。 |
| `schema_hash_conformance` | canonical JSON ordering、public/gold split、hash stability。 | hash values are stable; adapter view has no gold keys。 |

P1 fixtures:

| Family | Purpose | Required capability | Hard gates |
| --- | --- | --- | --- |
| `memory_off` | prior experiences を ingest しない deterministic baseline。adapter は mode を見ず、空 state に対して abstain または empty evidence を返す。 | reset + retrieve | evidence returned when `expected_abstention=true` で fail。memory_on との downstream delta は計算しない。 |
| `memory_on_happy_path` | ordinary memory-on の最小成功例。1 scope、明白な relevant support、no distractor。 | ingest + retrieve | recall@k=1、MRR@k=1、no forbidden/scope exposure。 |
| `retrieval_ranking` | distractors がある中で relevant evidence を top-k 上位に置けるか。 | retrieve | recall@k threshold、MRR/NDCG threshold。 |
| `scope_isolation` | adjacent user/project/tenant に似た事実を置き、requested scope だけを返せるか。 | scope enforcement | cross-scope leak > 0 で fail。 |
| `stale_conflict` | old fact と new fact が conflict する。fresh を優先し、old を fresh 扱いしないか。 | supersede or equivalent | stale-as-fresh > 0、contradiction-as-fresh > 0 で fail。 |
| `update_forget` | update/delete/forget semantics を区別できるか。forget 後の evidence を support として返さないか。 | required mutation op | forgotten ID returned で fail。unsupported は not_applicable or expected_failure。 |
| `abstention` | relevant memory がない、または scope/policy 上使えない場合に出さないか。 | retrieve | expected abstention mismatch で fail。 |
| `budget_limited` | k、max_evidence_items、latency/cost budget 下で ranking と usage reporting が崩れないか。 | retrieve + usage reporting | item budget violation、required usage missing で fail。latency/cost は profile 次第で hard/report。 |

Fixture authoring rules:

- 小さい synthetic fixture から始め、手で expected result を検算できるサイズにする。
- public fixture と private holdout の両方を置ける layout にするが、M6.25 P0/P1 は public conformance fixtures だけでよい。
- scorer/artifact 用の descriptive file name、fixture family、mode metadata は許可するが、adapter-visible ID や payload には出さない。
- adapter-visible request ID / fixture ID / text に gold ID、mode name、fixture family、trap family、expected behavior を埋め込まない。
- stale/conflict fixture は event time、ingest order、mutation effective time、query time を明示する。
- scope fixture は tenant/user/project など複数軸を持たせるが、P1 では 1 つの clear unauthorized leak を測れればよい。

## 11. Suggested file layout

これは実装案であり、最終 class 名は既存 codebase に合わせてよい。ただし harness core は mew memory internals を import しない。

```text
src/mew/memory_eval/
  __init__.py
  adapter_contract.py        # protocol/types or dataclass boundary; no mew memory internals
  fixtures.py                # canonical fixture loading, validation, public/gold split
  hashing.py                 # canonical JSON and reproducibility hashes
  runner.py                  # reset -> ingest/mutate sequence -> retrieve -> score
  scoring.py                 # deterministic metrics and hard gates
  artifacts.py               # run/request/failure artifact writer
  adapters/
    dummy.py                 # pass adapter for P0/P1 happy path
    broken.py                # controlled failure adapters
    memory_core.py           # optional later adapter; only adapter module may import memory_core

fixtures/memory_eval/
  p0/
    dummy_happy_path.json
    broken_cross_scope_leak.json
    broken_forbidden_retrieval.json
    broken_stale_as_fresh.json
    broken_contradiction_as_fresh.json
    broken_abstention_mismatch.json
    broken_invalid_ranking.json
    broken_budget_violation.json
    broken_missing_usage.json
    broken_unsupported_as_success.json
    broken_label_leakage_mode.json
    broken_support_source_mismatch.json
    broken_duplicate_support_reference.json
    broken_unscorable_evidence.json
  p1/
    memory_off_no_prior_memory_basic.json
    memory_on_happy_path_basic.json
    retrieval_ranking_basic.json
    scope_isolation_basic.json
    stale_conflict_supersede_basic.json
    update_forget_basic.json
    abstention_no_memory_basic.json
    budget_limited_basic.json

tests/
  test_memory_eval_fixture_split.py
  test_memory_eval_hashing.py
  test_memory_eval_scoring.py
  test_memory_eval_runner_dummy.py
  test_memory_eval_runner_broken.py
```

この file layout の descriptive filenames は scorer/artifact storage のためだけに使う。runner は file path や file stem から adapter-visible `fixture_id` / `request_id` を作ってはならない。adapter call の直前に opaque ID mapping を作り、adapter view value scan を通した payload だけを渡す。

CLI は後続 builder が必要と判断した場合だけ追加する。追加するなら `mew memory-eval run --fixture ... --adapter dummy --artifact ...` のような thin wrapper にとどめ、CLI が scoring logic を持たない。

Import boundary:

- `src/mew/memory_eval/fixtures.py`、`scoring.py`、`runner.py` は `src/mew/memory_core.py`、`memory_arena.py`、`memory_debug.py`、`MemoryContextBuilder` を import しない。
- mew の実 memory subsystem を測る場合は adapter module だけが実装固有 import を持つ。
- tests は import boundary を確認する。

## 12. Later builder close criteria

後続 implementation builder は次を満たしたら M6.25 memory eval harness v0/v1 を close できる。

P0:

- `src/mew/memory_eval/` 相当の small package が存在する。
- fixture loader が public/gold split を実施し、adapter call payload に gold key が入らないことを test している。
- adapter-visible `fixture_id` / `request_id` が opaque で、descriptive filename、fixture family、mode、trap family、expected behavior、gold label から生成されていないことを test している。
- opaque adapter IDs が deterministic hash に含まれる場合は同じ `fixture_public_hash`、operation position、seed から deterministic に生成され、random opaque ID は deterministic hashes から除外されることを test している。
- adapter view string values 全体に対する blocked-token scan があり、blocked token を含む fixture は label leakage failure になる。
- canonical deterministic hashes が安定し、key order 変更で `fixture_public_hash`、`fixture_gold_hash`、`request_hash`、`operation_prefix_hash`、`scoring_profile_hash`、`retrieval_result_hash` が変わらない。whole artifact の bitwise equality は要求しない。
- `retrieval_result_hash` が measured latency/cost/token counts を含まず、returned order、support IDs、derived `scorable_support_ids`、abstention、visible dropped records、visible provenance-derived IDs を含む。
- artifact schema が run/request/failure/hard gate を出す。
- dummy adapter が `dummy_happy_path` を pass する。
- broken adapters が default hard gate ごとに最低 1 fixture で intended gate fail を起こす。上の file layout の broken fixtures は最小例であり、hard gate を追加したら対応する broken fixture も追加する。

P1:

- retrieval metrics: support_recall@k、item-level precision@k、support_precision@k、MRR、item-level binary NDCG が unit-tested。
- derived/summarized memory の `evidence_ref` + `support_experience_ids` が `scorable_support_ids` で score される。legacy adapter の `source_experience_ids` を受ける場合も current-query support としてだけ扱う。
- `support_experience_ids` / P1 `source_experience_ids` が current-query support だけを表し、historical lineage を scoring に混ぜない。
- `support_experience_ids` と P1 legacy `source_experience_ids` が両方 non-empty の場合、canonical set normalization 後の不一致が `support_source_mismatch` / `support_source_consistency` で hard fail になる。
- すべての returned items が non-empty `scorable_support_ids(e)` を持ち、unscorable derived `evidence_ref` が `unscorable_evidence` / `required_support_mapping_present` で hard fail になる。
- duplicate `returned_item_identity` が `invalid_ranking` になり、duplicate non-empty `support_signature` が `duplicate_support_reference` / `no_duplicate_support_reference` で hard fail になる。
- `scorable_support_ids(e)` に入る `support_experience_ids`、P1 support-only `source_experience_ids`、fallback `evidence_id` と、source/support mutation IDs が `operation_sequence` request prefix 内に存在することを hard gate で検証する。
- `retrieve` が durable-memory side-effect free で、future retrieval semantics を変えない。
- stale/conflict metrics: stale-as-fresh、contradiction-as-fresh、freshness preference が unit-tested。
- scorer が freshness/scope を scorer_view から計算し、adapter-reported state/scope を hard gate に使わない。
- isolation metrics: cross-scope leak、cross-scope exposure、forbidden retrieval が hard fail になる。
- abstention metrics: expected abstention、false abstention、missed abstention が分かれて artifact に出る。
- budget/latency/cost: item budget は hard gate、latency/cost は configured hard/report mode を持つ。
- per-request artifact が `result_status`、denominator inclusion、unsupported capabilities、status reason を持つ。
- usage artifact が latency source、cost methodology、token methodology を持つ。
- fixture runner が `operation_sequence` を適用し、各 request の `operation_prefix_hash` を sequence prefix から作る。
- initial P1 fixture families が最低 1 つずつある。
- unsupported capability が pass として集計されない。
- `memory_off` baseline があり、adapter-visible request に mode を渡さず、artifact では `memory_on` と separate bucket に出る。
- harness core が mew memory subsystem internals に依存しない。

Verification:

- targeted pytest for memory_eval passes。
- source reports under `docs/another/` are not edited by implementation。
- generated artifacts are stable enough to compare in review。

## 13. Future orchestrated implementation review checklist

Reviewers should check:

- M6.25 scope が P0/P1 だけに保たれているか。
- `build_context`、`inspect_provenance`、MemoryArena、downstream agent task が acceptance gate に混ざっていないか。
- harness core が `MemorySystem`、`MemoryContextBuilder`、`memory_arena`、`implement_v2` を import していないか。
- adapter-visible payload に `mode`、trap family label、`gold`、expected、relevant IDs、must-not IDs、stale/conflict labels が漏れていないか。
- `fixture_public_hash` と `fixture_gold_hash` が分離され、adapter reset に gold/full hash が渡っていないか。
- adapter-visible `fixture_id` / `request_id` が opaque で、file path、descriptive fixture name、mode、fixture family、trap family、expected behavior、gold label を encode していないか。
- opaque adapter IDs が deterministic hashes に入る場合は deterministic に生成され、random opaque IDs が deterministic hashes から除外されているか。
- leakage prevention が adapter-view keys だけでなく string values も scan しているか。
- unsupported capability が visible な artifact result になっているか。
- `not_applicable` が failure ではなく score/gate denominators から除外されているか。
- whole artifact bitwise equality ではなく deterministic content hashes の安定性を見ているか。
- `retrieval_result_hash` が deterministic scoring/exposure hash であり、volatile measured usage を含んでいないか。
- `retrieval_result_hash` に support/exposure inputs: `support_experience_ids`、P1 support-only `source_experience_ids`、`source_mutation_ids`、`scorable_support_ids`、visible dropped records、visible provenance-derived IDs が入っているか。
- precision@k と NDCG が item-level relevance を使い、support IDs の数で 1.0 を超えないか。
- derived/summarized memory が current-query support IDs で score され、lineage IDs を scoring に使っていないか。
- `support_experience_ids` と P1 legacy `source_experience_ids` が両方ある場合の不一致が `support_source_mismatch` hard fail になるか。
- unscorable returned items が non-relevant 扱いで隠れず、`required_support_mapping_present` hard gate で落ちるか。
- duplicate `returned_item_identity` と duplicate non-empty `support_signature` が item-level precision/NDCG を膨らませない hard gate になっているか。
- `scorable_support_ids(e)` に入る `support_experience_ids`、P1 support-only legacy `source_experience_ids`、fallback `evidence_id` と source/support mutation refs が request prefix 内の known/applied public operations に限定されているか。
- replacement experiences が mutation 前に normal Experience として ingest され、mutate が duplicate replacement を作らないか。
- `retrieve` が durable-memory side-effect free か。
- native score が nullable で、P1 metrics が native score に依存していないか。
- `dropped` や visible provenance-derived IDs が scope exposure surface として gate 対象になっているか。
- scorer が adapter-reported state/scope を信用せず、scorer_view から freshness/scope を計算しているか。
- `operation_sequence` と request checkpoint が stale/update/forget scoring の source of truth になっているか。
- adapter-visible reset に real `scoring_profile_id` が渡っていないか。
- hard gates が metric を report するだけで終わらず pass/fail に効いているか。
- cross-scope leak、forbidden retrieval、strict stale-as-fresh、strict contradiction-as-fresh が zero tolerance か。
- dummy pass と broken fail の両方があるか。
- latency/cost が hidden model calls を隠さない形で artifact に残るか。
- single aggregate score で privacy/staleness failure を覆っていないか。
- fixture naming、adapter-visible IDs、request text が answer/gold/mode/trap family を暗示していないか。descriptive filenames は scorer/artifact-only か。

## 14. Risks and anti-patterns

- Harness 本体を mew memory internals に結びつけること。adapter の中だけに閉じ込める。
- `MemoryContextBuilder` を v0/v1 の required path にすること。P2 までは deferred。
- MemoryArena や downstream success を memory retrieval correctness の証明として扱うこと。
- model judge で deterministic fact を判定すること。
- adapter に `gold`、expected、anti-leak lists、private hash を渡すこと。
- unsupported capability を空の retrieval や low score として隠すこと。
- stale、supersede、delete、forget を同じ operation として扱うこと。
- scope filter を retrieval 後の display filter として扱い、artifact/log/provenance に unauthorized evidence を出すこと。
- caller-visible `dropped` に unauthorized evidence IDs を出すこと。
- adapter-reported state/scope を scorer の source of truth として使うこと。
- `retrieve` で検索履歴、query summary、last accessed marker などを durable memory に書き、future retrieval semantics を変えること。
- `support_experience_ids` だけで scoring し、異なる `source_experience_ids` に stale/out-of-scope IDs が残ることを見逃すこと。
- duplicate derived memory refs or duplicate support signatures で item-level precision/NDCG を膨らませること。
- unscorable `evidence_ref` を単なる non-relevant item として処理し、deterministic ID scoring の穴を隠すこと。
- volatile run fields を含む artifact 全体の bitwise equality を P0 reproducibility gate にすること。
- random opaque adapter IDs を deterministic hashes に含め、hash conformance を run ごとに不安定にすること。
- `scoring_profile_id` のような intent-bearing profile ID を adapter-visible reset に渡すこと。
- high recall のために raw history dump を報酬すること。
- privacy/staleness hard fail を single aggregate score で薄めること。
- public fixture だけに過学習すること。P0/P1 では conformance が主目的だが、将来比較には holdout が必要。
- adapter-visible request ID、fixture ID、text template に answer、mode、fixture family、trap family、expected behavior、gold label を埋め込むこと。
- descriptive fixture filename や fixture family metadata から adapter-visible ID を生成すること。
- cost/latency/model calls を adapter の中で隠すこと。
- architecture taxonomy を harness schema に直結しすぎること。memory kind は fixture metadata として有用だが、harness core の storage assumption ではない。

## 15. Implementation order

後続 builder は次の順に進める。

1. package skeleton、fixture dataclasses/types、canonical JSON hash。
2. fixture loader と public/gold split。
3. adapter contract と dummy/broken adapters。
4. scoring functions and hard gates。
5. runner and artifact writer。
6. P0 fixtures and tests。
7. P1 fixture families and tests。
8. optional CLI wrapper only if useful。

この順序なら、MemoryContextBuilder、MemoryArena、mew memory subsystem rewrite に入らず、M6.25 の deterministic harness substrate を単独で閉じられる。
