# Design 2026-05-27 - M6.25 Synthetic Analogy Minimal Bench

Status: MVP design document only. No implementation changes are authorized by
this document.

Scope: `memory_eval` 向けに、最初に実装する最小の synthetic analogy
memory benchmark を定義する。目的は、少ない予算の中で memory が局所的な
意味構造を使える形で保持できるかを、厳密採点可能な小さなベンチで確認する
ことにある。

## 1. Purpose

この MVP は、memory が「長い振る舞い全体」を良くするかではなく、
`memory_eval` の部品レベルで、公開経験から局所的な意味構造を取り出して
固定 solver に渡せるかを測る。

中心の問いは次の 1 点に絞る。

```text
小さな synthetic local world から得た public experiences だけを使って、
memory は限られた budget 内で task を解くのに十分な局所的意味構造を
コンパクトに供給できるか。
```

MVP はまず単純な benchmark loop を成立させ、後から指標や難しい fixture
族を足す。最初から retention 曲線や forgetting-aware score まで入れない。

## 2. Non-goals

- terminal-bench や一般 agent behavior の評価はしない。
- LLM judge を主採点器にしない。
- retention AUC、長期 horizon 曲線、forgetting-aware metrics を入れない。
- rich provenance taxonomy や structured claim scoring を要求しない。
- raw vs derived の細かい品質分類を初期実装に入れない。
- stale/update/scope/forget/long-horizon の fixture を MVP に入れない。
- full design にある将来の広い設計を、この文書で置き換えたり破棄したりしない。

## 3. Relationship to full design doc

フル設計は
`docs/DESIGN_2026-05-22_M6_25_BUDGETED_SYNTHETIC_ANALOGY_MEMORY_BENCH.md`
に残す。この文書はその代替ではなく、最初に実装するための縮小版である。

整理すると次の役割分担にする。

- 2026-05-22 文書: 将来の広い方向性。条件分解、長期 profile、stale/update、
  richer metrics、bridge 先を含む。
- 2026-05-27 文書: まず実装する最小 loop。小 world、3 条件、厳密採点、
  budget 指標、簡単な report のみ。

したがって、MVP 実装はこの文書に従うが、将来拡張の方向は 2026-05-22 文書を
参照する。

## 4. MVP benchmark loop

MVP の実行単位は `world` と、その world から作られた複数 `task` である。

1. 1 個以上の小さな synthetic local world を生成する。
2. hidden world から public experiences を作る。
3. 同じ world/task 集合に対して `memory_off`、`memory_on`、
   `oracle_context` の 3 条件を走らせる。
4. 各条件は isolated memory state から開始する。MVP の既定は
   `reset_per_condition_world` であり、`memory_off` は `memory_on` が ingest
   した経験を見てはならない。
5. `memory_on` のみ public experiences を memory に ingest する。
6. `memory_on` では budget 内で 1 個の compact memory artifact
   または retrieval packet を構築・取得する。
7. 固定 solver に対して、条件に応じて次のいずれかを渡す。
   - `memory_off`: task prompt のみ
   - `memory_on`: task prompt + memory artifact
   - `oracle_context`: task prompt + scorer が作る minimal support context
8. solver の出力を正規化し、gold answer と厳密比較する。
9. 同時に memory call 数、split した context token 数、evidence item 数を記録する。
10. task 単位と条件単位の集計を出力する。

MVP では 1 task あたりの solver 実行は 1 回でよい。複数 turn の agent loop は
扱わない。

solver は MVP では memory を対話的に呼ばない。memory retrieval / artifact
build は solver 入力を作る前に runner 側で完了していなければならない。

## 5. Conditions and isolation

### Default state isolation

- 各条件は isolated memory state から走らせる。
- MVP の既定は `reset_per_condition_world` で、各 world ごとに条件開始前に reset
  する。
- task を完全独立に実行する runner は `reset_per_task` を使ってよい。
- `oracle_context` は memory ingest を必要としない。
- どの isolation policy を使ったかは report に
  `state_isolation: "reset_per_condition_world" | "reset_per_task"` として残す。

### `memory_off`

- solver は task prompt だけを見る。
- memory ingest はしない。
- `memory_calls_used = 0`。

### `memory_on`

- public experiences を memory に ingest する。
- task 解答前に、budget 内で 1 個の compact artifact か retrieval packet を
  用意する。
- solver は task prompt とその artifact だけを見る。
- artifact は plain text summary、短い relation list、短い rule memo などでよく、
  structured claims は必須ではない。
- artifact 構築方法は MVP では profile-defined にする。profile は次の provider の
  いずれか 1 つを宣言する。
  - `retrieve_packet`: adapter の `retrieve` が ranked evidence snippets か memory
    items を返し、harness がそれを `artifact_text` に serialize する。
  - `adapter_compact_artifact`: adapter が MVP 用 compact artifact hook を公開する。
    optional だが、使うなら profile に明示する。
  - `harness_baseline_packet`: dummy / baseline adapter 用に、harness が返却 evidence
    text から簡単な packet を作る。
- `artifact_provider` ごとの `memory_calls_used` の既定は次のとおり。
  - `retrieve_packet`: `retrieve` 1 回ぶんとして `memory_calls_used = 1`。profile が
    明示的に override する場合だけ変更してよい。
  - `adapter_compact_artifact`: compact artifact build 1 回ぶんとして
    `memory_calls_used = 1`。profile が明示的に override する場合だけ変更してよい。
  - `harness_baseline_packet`: evidence を得るために使った retrieval call 数と同じ。
    harness 側の packet serialize 自体は memory call を 1 回増やさない。
- `memory_calls_used` は solver 入力準備のための retrieve / artifact-build call 数だけを
  数える。fixture setup、memory reset、experience ingest、scorer 側 oracle 構築は
  含めない。
- report には `artifact_provider` を必ず残す。
- MVP では full P2 `build_context` や rich provenance tree を要求しない。

### `oracle_context`

- scorer が、その task を解くのに必要な最小 support context を直接渡す。
- 通常の `oracle_context` には direct answer を含めない。
- ここで禁止するのは `{"answer":"..."}` のような答え専用 field や、
  `The answer is ...` のような明示答え文である。support fact 自体が答えを
  含意または内包することまでは禁じない。
- もし将来 debug 用に direct answer 付き oracle を追加する場合は別条件にし、
  MVP の通常集計には入れない。
- `memory_calls_used = 0`。

3 条件は同じ task 集合で比較し、solver prompt と budget ceiling も共通にする。

## 6. Fixture/task schema sketch and runtime split

MVP では hidden world と public view を明示的に分けるが、採点に必要な最小
情報だけ持てばよい。以下の schema sketch は canonical fixture authoring shape
であり、adapter がそのまま見る payload ではない。

```json
{
  "world_id": "world_001",
  "hidden_world": {
    "entities": ["dax", "wug", "zup"],
    "relations": [
      {"subject": "dax", "relation": "nava", "object": "wug"}
    ],
    "rules": [
      {"rule_id": "r1", "description": "token pair pattern used for task generation"}
    ]
  },
  "public_experiences": [
    {
      "experience_id": "exp_001",
      "text": "dax is nava-related to wug."
    }
  ],
  "tasks": [
    {
      "task_id": "task_001",
      "family": "relation_lookup",
      "prompt": "In this local world, what is dax related to by nava?",
      "gold_answer": "wug",
      "oracle_context": [
        "dax is nava-related to wug."
      ]
    }
  ]
}
```

MVP の fixture family は次の 3 つに限定する。

- `relation_lookup`
- `analogy_completion`
- `rule_application`

MVP の task answer はすべて単一 invented token に限定する。複数回答、
自由文理由、support citation 必須化は入れない。

実行前に runner はこの authoring shape を次の view に split する。

- `adapter_view`: public experiences、public request prompt、opaque IDs、budgets。
- `scorer_view`: `hidden_world`、`gold_answer`、`oracle_context`、fixture family labels。
- `report_view`: condition 名、metrics、`normalized_answer`、hashes。

`hidden_world`、`gold_answer`、`oracle_context` は `memory_on` の adapter input や
artifact generation input に serialize してはならない。

## 7. Solver and answer normalization

solver は固定 prompt、固定 decoding、固定 answer format を使う。MVP では
厳密採点を簡単にするため、solver 出力を単一 token answer に制約する。

Phase 0 の solver stub は runner plumbing 確認用であり、hand-authored fixture に
対して固定の事前設定 answer を返してよい。ただしその score は
benchmark-quality memory score ではなく smoke-test score として扱う。

Phase 1 以降の固定 solver は、`task prompt` と condition-specific context だけを
消費する。`gold_answer`、`hidden_world`、`oracle_context` は
`oracle_context` 条件以外で読んではならない。

推奨 answer format:

```json
{"answer":"wug"}
```

token 数の測定方法も solver profile に固定する。MVP report には次の field を残す。

```json
{
  "solver_profile": {
    "solver_id": "fixed_solver_v1",
    "answer_format": "json_single_token",
    "token_counter": "mvp_whitespace_v1 | model_tokenizer:<id>"
  }
}
```

MVP-0 では `mvp_whitespace_v1` を使ってよい。ただし token 数の数え方は再現可能で
なければならず、`task_prompt_tokens_used`、`memory_artifact_tokens_used`、
`oracle_context_tokens_used` の計測方法は report に記録された
`solver_profile.token_counter` で一意に分かる必要がある。

正規化関数 `normalize_answer(x)` は次を行う。

1. JSON から `answer` field を読む。読めない場合は失敗。
2. 文字列の前後空白を削除する。
3. ASCII 英字を小文字化する。
4. 連続空白を 1 個に潰す。

MVP では generator 側も invented token を ASCII lowercase に制限する。
正規化後の `normalized_answer` を `gold_answer` と完全一致で比較する。

不正 JSON、空 answer、複数 token answer、未知形式はすべて不正解として扱う。

## 8. Metrics and exact formulas

以下の式で `task_count >= 1` を前提にする。各集計は同一 condition・同一
benchmark slice の task 群に対して計算する。

各 task について:

- `per_task_success = 1 if normalized_answer == gold_answer else 0`
- `memory_calls_used`: solver 入力準備のために使った retrieve / artifact-build call 数
- `task_prompt_tokens_used`: task prompt token 数
- `memory_artifact_tokens_used`: `memory_on` で solver に渡した artifact token 数。
  他条件では 0
- `oracle_context_tokens_used`: `oracle_context` で solver に渡した support context
  token 数。他条件では 0
- `total_context_tokens_used = task_prompt_tokens_used + memory_artifact_tokens_used + oracle_context_tokens_used`
- `evidence_items_used`: solver に渡した evidence item 数。MVP の既定は
  `memory_off = 0`、`memory_on = len(artifact.evidence_ids)`、
  `oracle_context = len(task.oracle_context)` とする
- `budget_pass = memory_calls_used <= max_memory_calls and total_context_tokens_used <= max_total_context_tokens and evidence_items_used <= max_evidence_items`
- `task_pass = 1 if per_task_success == 1 and budget_pass == true else 0`

条件単位の集計:

- `accuracy = sum(per_task_success) / task_count`
- `pass_rate = sum(task_pass) / task_count`
- `avg_memory_calls = sum(memory_calls_used) / task_count`
- `avg_task_prompt_tokens = sum(task_prompt_tokens_used) / task_count`
- `avg_memory_artifact_tokens = sum(memory_artifact_tokens_used) / task_count`
- `avg_oracle_context_tokens = sum(oracle_context_tokens_used) / task_count`
- `avg_total_context_tokens = sum(total_context_tokens_used) / task_count`
- `avg_evidence_items = sum(evidence_items_used) / task_count`
- `budget_violation_rate = sum(1 if budget_pass == false else 0) / task_count`

条件差分:

- `memory_lift = accuracy(memory_on) - accuracy(memory_off)`
- `oracle_gap = accuracy(oracle_context) - accuracy(memory_on)`
- optional: `memory_pass_lift = pass_rate(memory_on) - pass_rate(memory_off)`
- optional: `oracle_pass_gap = pass_rate(oracle_context) - pass_rate(memory_on)`

補足:

- `memory_off` では `memory_calls_used = 0`。
- `oracle_context` でも `memory_calls_used = 0`。
- `memory_calls_used` に fixture setup、memory reset、experience ingest、scorer 側
  oracle construction は含めない。
- MVP solver は memory を interactive に呼ばないので、solver-time memory call は
  常に 0 である。
- `memory_lift` と `oracle_gap` は、同じ task 集合を同じ solver 設定で比較するとき
  だけ計算する。
- `budget_pass` は精度と別に持ち、正答でも budget 超過なら `task_pass = 0` にする。
- budget 判定は `total_context_tokens_used` を使うが、memory 効率の読み取りでは
  `memory_artifact_tokens_used` を別に見る。
- `task_prompt_tokens_used`、`memory_artifact_tokens_used`、
  `oracle_context_tokens_used` は、必ず `solver_profile.token_counter` に記録した同一
  method で数える。
- `memory_lift` は MVP の probe metric であり、memory artifact correctness の証明
  ではない。`memory_off` accuracy、`oracle_gap`、budget 使用量と併せて解釈し、
  より厳密な support / pollution 系の読みは full design の後続指標に委ねる。

## 9. Artifact/report shape

MVP report は、task 単位行と condition 単位 summary を持てば十分である。
複雑な provenance 木や claim graph は不要。

```json
{
  "benchmark_id": "synthetic_analogy_minimal.v1",
  "state_isolation": "reset_per_condition_world",
  "budget_profile": {
    "max_memory_calls": 1,
    "max_total_context_tokens": 600,
    "max_evidence_items": 8
  },
  "solver_profile": {
    "solver_id": "fixed_solver_v1",
    "answer_format": "json_single_token",
    "token_counter": "mvp_whitespace_v1"
  },
  "conditions": {
    "memory_off": {
      "task_count": 20,
      "accuracy": 0.10,
      "pass_rate": 0.10,
      "avg_memory_calls": 0.0,
      "avg_task_prompt_tokens": 120.0,
      "avg_memory_artifact_tokens": 0.0,
      "avg_oracle_context_tokens": 0.0,
      "avg_total_context_tokens": 120.0,
      "avg_evidence_items": 0.0,
      "budget_violation_rate": 0.0
    },
    "memory_on": {
      "task_count": 20,
      "accuracy": 0.65,
      "pass_rate": 0.60,
      "avg_memory_calls": 1.0,
      "avg_task_prompt_tokens": 120.0,
      "avg_memory_artifact_tokens": 100.0,
      "avg_oracle_context_tokens": 0.0,
      "avg_total_context_tokens": 220.0,
      "avg_evidence_items": 4.0,
      "budget_violation_rate": 0.05
    },
    "oracle_context": {
      "task_count": 20,
      "accuracy": 0.95,
      "pass_rate": 0.95,
      "avg_memory_calls": 0.0,
      "avg_task_prompt_tokens": 120.0,
      "avg_memory_artifact_tokens": 0.0,
      "avg_oracle_context_tokens": 60.0,
      "avg_total_context_tokens": 180.0,
      "avg_evidence_items": 3.0,
      "budget_violation_rate": 0.0
    }
  },
  "comparisons": {
    "memory_lift": 0.55,
    "oracle_gap": 0.30,
    "memory_pass_lift": 0.50,
    "oracle_pass_gap": 0.35
  },
  "per_task_rows": [
    {
      "task_id": "task_001",
      "condition": "memory_on",
      "normalized_answer": "wug",
      "per_task_success": 1,
      "artifact_id": "artifact_world_001_task_001_memory_on",
      "artifact_hash": "sha256:abcd",
      "artifact_provider": "retrieve_packet",
      "memory_calls_used": 1,
      "task_prompt_tokens_used": 120,
      "memory_artifact_tokens_used": 90,
      "oracle_context_tokens_used": 0,
      "total_context_tokens_used": 210,
      "evidence_items_used": 3,
      "budget_pass": true,
      "task_pass": 1
    }
  ]
}
```

artifact 自体の最小 shape は次で十分である。

```json
{
  "artifact_id": "artifact_world_001_task_001_memory_on",
  "task_id": "task_001",
  "world_id": "world_001",
  "condition": "memory_on",
  "artifact_hash": "sha256:abcd",
  "artifact_provider": "retrieve_packet",
  "memory_calls_used": 1,
  "memory_artifact_tokens_used": 90,
  "artifact_text": "compact memory packet text",
  "evidence_ids": ["exp_001", "exp_004"]
}
```

full provenance tree は不要だが、`artifact_hash` と `artifact_provider` は残す。

### MVP artifact hash

MVP の `artifact_hash` は、artifact 最小 payload から作る canonical JSON を UTF-8
bytes にして計算する。canonicalization の条件は次の 3 つだけに絞る。

- object key は sorted order にする。
- text encoding は UTF-8 に固定する。
- array は出力時の deterministic な順序をそのまま使う。MVP では stable array
  ordering を runner / provider 側で保証する。

hash payload に含める field は次だけである。

- `artifact_id`
- `task_id`
- `world_id`
- `condition`
- `artifact_provider`
- `artifact_text`
- `evidence_ids`
- `memory_calls_used`
- `memory_artifact_tokens_used`

hash payload から除外するもの:

- solver answer
- `normalized_answer`
- `per_task_success`
- `budget_pass`
- `task_pass`
- latency
- wall-clock timestamps
- `run_id`
- environment-specific fields
- `artifact_hash` 自身

MVP では単純化のため `artifact_id` を hash に含めてよい。content-only 比較が必要に
なった場合は将来 `artifact_content_hash` を追加してもよいが、この MVP では導入しない。

## 10. What this MVP can and cannot measure

この MVP が測れるもの:

- public experiences を ingest した memory が、小さな local world の relation /
  analogy / rule 情報を budgeted artifact として solver に渡せるか。
- `memory_off` / `memory_on` / `oracle_context` の比較から、artifact が task 成功に
  どれだけ寄与し、理想 support context までどの程度差があるか。

この MVP では測れないもの:

- long-term retention
- forgetting correctness
- stale / update / scope isolation
- strict raw-vs-derived quality difference
- structured claim support
- provenance fidelity
- full agent behavior

これらは 2026-05-22 の full design に future direction として残す。

## 11. Implementation phases and acceptance levels

### Phase 0 / MVP-0 smoke loop

- world / experience / task の最小 schema を固定する。
- 単一 token JSON answer を返す solver stub を作る。
- `relation_lookup` の hand-authored fixture を 1 つ作る。
- `memory_off` / `memory_on` / `oracle_context` の 3 条件を通せるようにする。
- exact JSON answer scoring を通す。
- report shape を emit する。
- この段階の score は smoke-test score であり、benchmark-quality memory score ではない。

### Phase 1 / MVP-1 minimal benchmark pack

- invented token の小 world generator を追加する。
- `relation_lookup`、`analogy_completion`、`rule_application` の 3 family を生成する。
- seed 固定で 20 task の deterministic pack を作る。
- `memory_on` で public experiences を ingest し、profile-defined artifact provider
  から compact artifact を 1 個返せるようにする。
- 3 条件 `memory_off` / `memory_on` / `oracle_context` が同一 task 集合で走る。
- `memory_lift` と `oracle_gap` を report に載せる。
- generator は、family が candidate choices を明示的に使う場合を除き、gold answer
  token を task prompt に置かない。保証できない task は、Phase 3 の anti-grep
  checks が入るまで `diagnostic` 扱いにする。
- Phase 1 以降の固定 solver は task prompt と condition-specific context だけを読み、
  hidden gold を見ない。

MVP の acceptance は「memory が十分高性能であること」ではなく、
「最小 benchmark loop が厳密に回ること」に置く。

### Later hardening phases

- Phase 2: profile command と adapter integration の磨き込み。
- Phase 3: anti-grep distractors と `memory_off` floor checks を導入する。
- Phase 4: budget 比較と report polish を追加する。

## 12. Future extensions explicitly deferred

以下は将来拡張であり、この文書の MVP には入れない。

- stale / update / scope / forget / long-horizon fixture
- retention curve と retention AUC
- forgetting-aware metrics
- raw vs derived の厳密分離スコア
- structured claim scoring
- rich provenance taxonomy
- model-judge scoring
- terminal bench や full agent behavior との bridge
- P4 bridge / terminal bench behavior scoring

これらは full design の将来方向として保持する。

## 13. Reviewer checklist

- この文書が 2026-05-22 の full design より明確に小さく、単純になっているか。
- benchmark loop が 3 条件と 3 family に限定され、すぐ実装できる粒度か。
- 数式が曖昧でなく、`task_count`、budget、condition 差分、split token 指標の定義が
  明確か。
- `memory_eval` の component-level benchmark に留まり、terminal bench に
  逸脱していないか。
- `oracle_context` が通常 scoring で direct answer を漏らしていないか。
- hidden/public split が authoring shape と runtime view の両方で明確か。
- structured claims や provenance-heavy scoring なしでも MVP 実装できるか。
- full design が future direction として残ることが明記されているか。
