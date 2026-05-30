# Implementation Plan 2026-05-28 - M6.25 Synthetic Analogy Minimal Bench

## 0. 前提

- Source of truth は `docs/DESIGN_2026-05-27_M6_25_SYNTHETIC_ANALOGY_MINIMAL_BENCH.md`。
- `docs/DESIGN_2026-05-22_M6_25_BUDGETED_SYNTHETIC_ANALOGY_MEMORY_BENCH.md` は future/full design context として参照するだけにする。
- この計画は実装順序を決めるための小さい engineering plan であり、広い設計文書に戻さない。
- 対象は `memory_eval` の component-level benchmark。terminal bench、full agent behavior、live model 評価は扱わない。

## 1. 目的とスコープ

最初に MVP-0 smoke loop を作り、loop・split・scoring・report が壊れずに回ることを確認する。その後 MVP-1 minimal benchmark pack として、固定 seed の 20 task pack を追加する。

この MVP で確認することは、public experiences を ingest した memory が、budget 内の compact artifact / retrieval packet を通じて、固定 solver に局所的な意味構造を渡せるかである。`memory_lift` は probe metric であり、memory の正しさそのものの証明とは扱わない。

スコープ外:

- terminal bench / behavior_eval 連携
- multi-turn agent loop
- LLM judge
- P2 `build_context`
- structured claim scoring / rich provenance tree
- stale / update / scope / forget / long-horizon fixture
- generated fixture の無レビュー commit

## 2. 提案ファイルとモジュール

この計画ではファイルを提案するだけで、作成しない。

- `src/mew/memory_eval/synthetic_analogy.py`
  - MVP 固有の schema helper、view split、condition runner、artifact assembly、metric aggregation を置く候補。
  - 既存 `runner.py` に直接混ぜすぎず、P0/P1 retrieval harness と境界を保つ。
- `src/mew/memory_eval/scoring.py`
  - `normalize_answer`、exact JSON answer scoring、budget 判定を既存 scoring helper と揃えて追加する候補。
  - 既存 P0/P1 retrieval scoring と混線するなら `synthetic_analogy.py` 側に閉じる。
- `src/mew/memory_eval/hashing.py`
  - canonical JSON / `stable_hash` を再利用する。
  - MVP artifact hash helper は synthetic analogy 側に置き、hash payload field を明示する。
- `tests/test_memory_eval_synthetic_analogy.py`
  - normalization、view split leakage、budget、artifact hash、aggregation、smoke integration をまとめる候補。
- fixture 候補
  - MVP-0 の hand-authored `relation_lookup` は、初期実装では test 内 inline fixture か `.codex-artifacts` のレビュー用サンプルに置く。
  - commit するなら `fixtures/memory_eval/synthetic_analogy/mvp0_relation_lookup.json` などを別レビューで承認してからにする。
  - generated MVP-1 pack はレビュー完了まで commit しない。必要なら `tmp/` または `.codex-artifacts/` に手元生成するだけにする。
- profile / command 候補
  - まず `python -m mew.memory_eval.synthetic_analogy --profile synthetic-analogy-mvp-smoke` のような module-local entry を検討する。
  - 安定後に `src/mew/cli.py` へ薄い profile command を足す。

## 3. Phase Breakdown

### Phase 0: MVP-0 smoke loop

目的は benchmark quality ではなく、最小 loop の配線検証に置く。

- hand-authored `relation_lookup` fixture を 1 件だけ用意する。
- canonical authoring shape を固定する:
  - `world_id`
  - `hidden_world`
  - `public_experiences`
  - `tasks`
  - `task_id`, `family`, `prompt`, `gold_answer`, `oracle_context`
- 実行前に 3 view へ分割する:
  - `adapter_view`: public experiences、public task prompt、opaque IDs、budgets
  - `scorer_view`: hidden world、gold answer、oracle context、family label
  - `report_view`: condition、metrics、normalized answer、hashes
- `memory_off` / `memory_on` / `oracle_context` の 3 条件を同一 task で走らせる。
- state isolation は `reset_per_condition_world` を既定にする。
- `memory_on` は `artifact_provider=retrieve_packet` または `harness_baseline_packet` のどちらかから始める。
- solver stub は `{"answer":"..."}` 形式だけを返す。Phase 0 の score は smoke-test score と明示する。
- exact JSON answer scoring を通す。
- `token_counter=mvp_whitespace_v1` を使い、prompt / memory artifact / oracle context を分けて数える。
- MVP report shape を emit する。
- `hidden_world`、`gold_answer`、通常 `oracle_context` が `memory_on` adapter input や artifact generation input に入らない gate を入れる。

完了条件:

- `relation_lookup` 1 fixture x 3 conditions の smoke test が通り、JSON report が 1 件 emit される。
- report に `state_isolation`、`solver_profile.token_counter=mvp_whitespace_v1`、condition 別 token split、exact JSON scoring 結果が残る。
- leakage gate が `hidden_world` / `gold_answer` / 通常 `oracle_context` の adapter/artifact 混入を失敗扱いにする。
- solver stub の結果は smoke-only と表示され、MVP-1 benchmark scoring に流用されない。
- Phase 0 の provider は `retrieve_packet` または `harness_baseline_packet` に限定し、`adapter_compact_artifact` は optional/future のままにする。

### Phase 1: runner + metrics hardening

Phase 0 の loop を、MVP-1 に耐える集計へ固める。

- task 単位:
  - `per_task_success`
  - `memory_calls_used`
  - `task_prompt_tokens_used`
  - `memory_artifact_tokens_used`
  - `oracle_context_tokens_used`
  - `total_context_tokens_used`
  - `evidence_items_used`
  - `budget_pass`
  - `task_pass`
- condition 集計:
  - `accuracy`
  - `pass_rate`
  - `avg_memory_calls`
  - `avg_task_prompt_tokens`
  - `avg_memory_artifact_tokens`
  - `avg_oracle_context_tokens`
  - `avg_total_context_tokens`
  - `avg_evidence_items`
  - `budget_violation_rate`
- condition 差分:
  - `memory_lift = accuracy(memory_on) - accuracy(memory_off)`
  - `oracle_gap = accuracy(oracle_context) - accuracy(memory_on)`
  - optional `memory_pass_lift`
  - optional `oracle_pass_gap`
- `evidence_items_used` default:
  - `memory_off = 0`
  - `memory_on = len(artifact.evidence_ids)`
  - `oracle_context = len(task.oracle_context)`
- `memory_calls_used` default:
  - `retrieve_packet = 1`
  - `adapter_compact_artifact = 1`
  - `harness_baseline_packet = retrieval call 数`
  - setup、reset、ingest、scorer oracle construction は含めない。
- artifact hash:
  - sorted-key canonical JSON、UTF-8、deterministic array order。
  - hash payload は MVP doc の最小 field に限定する。
  - solver answer、score、timestamps、run id、environment は除外する。
  - MVP では `artifact_id` を含める方針で始め、review で再確認する。
- no gold leakage gates:
  - adapter-visible payload に `gold_answer`、`hidden_world`、通常 oracle support、family label、answer token 用 label が混ざらないことを検査する。

完了条件:

- normalization、budget、token split、artifact hash、metrics aggregation の unit tests が通る。
- report の task row と condition summary に `per_task_success`、`budget_pass`、`task_pass`、`accuracy`、`pass_rate`、`memory_lift`、`oracle_gap` が出る。
- `memory_calls_used` は実装済み provider の default に従い、setup / reset / ingest / oracle construction を数えないことが test で確認される。`adapter_compact_artifact` は実装された場合だけ対象にする。
- `oracle_context` の `evidence_items_used=len(task.oracle_context)` は、oracle context が support item list として表現されている場合にだけ使う。単一 text blob の場合は list 化するか、count 不明として失敗させる。
- artifact hash は canonical JSON で安定し、score / answer / timestamp / run id が hash に入らないことが確認される。

### Phase 2: deterministic generator and MVP-1 pack

MVP-1 は小さく固定する。広い full design の horizon / stale / update には進まない。

- fixed seed を 1 つ選び、同じ入力から常に同じ 20 tasks を作る。
- family は 3 つだけ:
  - `relation_lookup`
  - `analogy_completion`
  - `rule_application`
- invented token は ASCII lowercase の単一 token に限定する。
- answer は単一 token のみ。複数回答、自由文理由、citation 必須化は入れない。
- generator は answer-token leakage を避ける:
  - 原則として task prompt に gold answer token を置かない。
  - family 上どうしても候補表示が必要な場合は、その task を明示的に diagnostic 扱いにする。
- `memory_off` floor は diagnostic として記録するが、hard threshold は review まで置かない。
- generated pack の commit は別レビュー後に判断する。初回は runtime generation または artifact 出力で十分にする。

完了条件:

- fixed seed から 20 tasks が deterministic に生成され、再実行で task IDs / prompts / gold / oracle support の hash が一致する。
- 20 tasks は `relation_lookup` / `analogy_completion` / `rule_application` の 3 family だけを含む。
- answer-token leakage check が通り、疑わしい task は normal aggregate から外すか diagnostic として明示される。
- pack20 run の report に 3 conditions、budget metrics、`memory_lift`、`oracle_gap`、`memory_off` floor diagnostic が残る。
- generated fixture pack は commit されず、レビュー用 artifact または runtime generation に留まる。

### Phase 3: profile command / manual gate

安定するまで CI default には入れない。

- profile 名:
  - `synthetic-analogy-mvp-smoke`
  - `synthetic-analogy-mvp-pack20`
- local/manual gate:
  - smoke profile は開発者が手元で短時間に回せること。
  - pack20 profile は deterministic report を出すこと。
  - CI 追加は report/hash が安定し、false failure が少ないと確認してからにする。
- CLI integration は薄く保つ:
  - profile を選ぶ。
  - output path を受け取る。
  - JSON artifact と human summary を出す。

完了条件:

- `synthetic-analogy-mvp-smoke` profile が Phase 0 smoke report を出す。
- `synthetic-analogy-mvp-pack20` profile が Phase 2 pack20 report を出す。
- manual gate の証跡として、実行 command、JSON report path、human summary の短い抜粋を記録できる。
- profile は local/manual 既定で、CI default には入れない。CI 追加は別レビューに分ける。
- command integration は thin wrapper に留まり、terminal bench / behavior_eval に接続しない。

### Phase 4: report ergonomics

レビューしやすさを上げるだけで、評価軸を広げない。

- JSON artifact を source of record にする。
- concise human summary を併出する:
  - condition ごとの `accuracy` / `pass_rate`
  - budget 使用量
  - `memory_lift`
  - `oracle_gap`
- `memory_off` / `memory_on` / `oracle_context` を同じ task set で横比較できる形にする。
- known limitations を report に残す:
  - smoke score is not benchmark-quality
  - no long-term retention
  - no structured claim scoring
  - no terminal / agent behavior

完了条件:

- JSON artifact が source of record として、task rows、condition summaries、comparisons、known limitations を含む。
- human summary が `memory_off` / `memory_on` / `oracle_context` の `accuracy`、`pass_rate`、budget 使用量、`memory_lift`、`oracle_gap` を同じ task set で比較する。
- summary は smoke score と MVP-1 score を混同せず、Phase 0 solver stub の結果を benchmark-quality と呼ばない。
- report に MVP の非対象が残る: long-term retention、structured claim scoring、terminal / full agent behavior は未評価。
- report schema の追加は表示・比較の改善に限定し、新しい fixture family や full design metric を増やさない。

## 4. Data / Schema Details

### Authoring fixture と runtime views

authoring fixture は人間が読むための canonical shape にする。runtime では必ず split し、adapter には public 情報だけ渡す。

- authoring fixture:
  - hidden world と public experiences を同じファイル内に持てる。
  - gold answer と oracle context を task に持てる。
- `adapter_view`:
  - public experiences
  - public request prompt
  - opaque IDs
  - budget
  - hidden IDs、gold、oracle、family label は含めない。
- `scorer_view`:
  - hidden world
  - gold answer
  - oracle context
  - family labels
  - leakage gate 用 metadata
- `report_view`:
  - task / condition result
  - normalized answer
  - artifact id/hash/provider
  - metrics

### Oracle context

通常の `oracle_context` は direct answer を含めない。禁止するのは `{"answer":"..."}` のような answer field と、`The answer is ...` のような明示答え文である。support fact が答えを含意することまでは禁止しない。

direct answer 付き oracle が必要になった場合は debug-only の別条件にし、MVP normal aggregate には入れない。

### Artifact providers

MVP の provider は次から始める。

- `retrieve_packet`
  - adapter `retrieve` の ranked evidence / memory items を harness が `artifact_text` に serialize する。
  - default `memory_calls_used = 1`
- `harness_baseline_packet`
  - dummy / reference adapter 用に harness が retrieval evidence text から packet を作る。
  - packet serialize 自体は memory call に数えない。
- `adapter_compact_artifact`
  - optional。adapter hook が必要になるまで入れない。

artifact minimum fields:

- `artifact_id`
- `task_id`
- `world_id`
- `condition`
- `artifact_hash`
- `artifact_provider`
- `memory_calls_used`
- `memory_artifact_tokens_used`
- `artifact_text`
- `evidence_ids`

### Solver profile と token counter

MVP-0 は次の固定 profile でよい。

- `solver_id = fixed_solver_v1`
- `answer_format = json_single_token`
- `token_counter = mvp_whitespace_v1`

`mvp_whitespace_v1` は再現可能な単純 whitespace counter として定義する。将来 model tokenizer を使う場合も、report の `solver_profile.token_counter` だけで解釈できるようにする。

### Report schema outline

JSON artifact は次の top-level を持てば十分。

- `benchmark_id`
- `state_isolation`
- `budget_profile`
- `solver_profile`
- `conditions`
- `comparisons`
- `per_task_rows`
- `known_limitations`

`conditions` は 3 条件の aggregate を持つ。`per_task_rows` は condition ごとの task result を持つ。provenance tree や claim graph は入れない。

## 5. Test Strategy

live model test は入れない。unit と deterministic smoke integration に限定する。

- `normalize_answer`
  - valid JSON
  - invalid JSON
  - missing answer
  - empty answer
  - uppercase ASCII
  - extra whitespace
  - multiple token rejection
- budget / token counting
  - `mvp_whitespace_v1`
  - split token totals
  - `budget_pass`
  - `task_pass`
- split leakage
  - `adapter_view` に `hidden_world`、`gold_answer`、oracle、family label がない。
  - `memory_on` artifact generation input に scorer-only field がない。
- artifact hash
  - key order independent
  - stable array order
  - excluded fields が hash に影響しない。
  - `artifact_id` を含める現行 MVP policy の確認。
- metrics aggregation
  - accuracy / pass_rate
  - memory_lift / oracle_gap
  - optional pass lift/gap
  - task_count が 1 以上であること。
- smoke integration
  - dummy/reference memory adapter で 1 fixture x 3 conditions を回す。
  - report が emit される。
  - no live model, no network, no generated fixture commit。

## 6. Acceptance Criteria

### MVP-0

- hand-authored `relation_lookup` fixture 1 件で loop が通る。
- `memory_off` / `memory_on` / `oracle_context` の 3 条件が同一 task で走る。
- 各条件が isolated state から始まる。
- exact JSON answer scoring が機能する。
- `mvp_whitespace_v1` で token split が記録される。
- MVP report が JSON として emit される。
- `memory_on` adapter/artifact input に hidden gold / oracle / direct answer が漏れない。
- Phase 0 score が benchmark-quality ではなく smoke-test score と明示される。

### MVP-1

- fixed seed から 20 deterministic tasks が作れる。
- family は `relation_lookup` / `analogy_completion` / `rule_application` の 3 つだけ。
- 3 条件が同じ 20 tasks で走る。
- `accuracy`、`pass_rate`、budget metrics が report される。
- `memory_lift` と `oracle_gap` が存在する。
- answer-token leakage avoidance が実装され、疑わしい task は diagnostic 扱いになる。
- generated fixture pack はレビューなしに commit されない。

## 7. Risks and Guardrails

- design bloat:
  - 2026-05-22 full design の horizon、stale/update、scope、retention、structured claim scoring を MVP に戻さない。
- hidden/gold leakage:
  - authoring shape から runtime view への split を唯一の入口にする。
  - adapter/artifact-visible payload の serialized scan を gate にする。
- solver guessing:
  - `memory_off` floor を常に出す。
  - high memory_off accuracy は diagnostic として扱う。
- metric overclaim:
  - `memory_lift` は probe metric。support correctness の証明とは書かない。
- implementation dependency:
  - P2 `build_context` や structured claims を要求しない。
  - `retrieve_packet` / `harness_baseline_packet` から始める。
- fixture policy:
  - hand-authored smoke fixture は最小にする。
  - generated samples / pack は review まで commit しない。
  - tmp data や raw datasets を source of record にしない。

## 8. Open Questions

- final numeric budget defaults:
  - `max_memory_calls`
  - `max_total_context_tokens`
  - `max_evidence_items`
- `mvp_whitespace_v1` から model tokenizer へ移る場合の exact behavior:
  - tokenizer id
  - normalization
  - whitespace / punctuation の扱い
  - report compatibility
- `memory_off` floor threshold:
  - MVP-1 では diagnostic のままにするか。
  - hard threshold を置くなら bucket size と action をどうするか。
- `artifact_id` を MVP artifact hash に含め続けるか:
  - 2026-05-27 MVP doc は含めてよい方針。
  - content-only comparison が必要なら将来 `artifact_content_hash` を追加する。
