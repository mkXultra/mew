# Design 2026-05-12 - M6.24 Native Tool Loop Responsibility Boundary

Status: design only.

Scope: `implement_v2` の provider-native tool/function calling loop における責務境界を定義する。対象は native transcript、request builder、harness、tool runtime、WorkFrame projection、finish completion、replay/fastcheck の境界であり、コード変更はこの文書だけでは承認しない。

この文書は `docs/EXPLAIN_2026-05-12_NATIVE_TOOL_LOOP_RESPONSIBILITY.ja.html` のレビュー済み方針を、実装フェーズと close gate に落とすための設計である。

## 決定

`NativeTranscript` を source of truth にする。provider から返った native `ResponseItem`、tool/function call、paired output、finish call/output、tool side effect refs、proof/replay metadata は transcript と sidecar artifact から再構成できる状態を正とする。

provider-visible な新しい `WorkFrame` object は導入しない。model が見る追加 context は既存 request surface の `compact_sidecar_digest` に入る bounded WorkFrame projection fields だけにする。通常 turn の provider input は次の三つに限定する。

- task/request instructions
- provider-native transcript window
- `compact_sidecar_digest`

`WorkFrame` は planner ではない。tool 実行、lane 完了、次 action の強制、provider transcript の構築を持たず、attention/evidence/finish risk を compact に示す projection である。

`finish_call` は transcript protocol と semantic lane completion を分離する。finish call/output は provider-native pairing として必ず記録されるが、lane status を `completed` にするかどうかは `CompletionResolver` が決める。

## 責務境界

### ProviderAdapter / RequestBuilder

持つ責務:

- provider-safe input item の構築
- tool schema lowering
- native `ResponseItem` / transcript item の変換
- request descriptor、prompt/cache metadata、reasoning/tool spec の組み立て
- `compact_sidecar_digest` を既存 request surface に入れること

持たない責務:

- task 完了判定
- model の次 action 決定
- WorkFrame reducer policy
- finish allow/block 判定
- `persisted_lane_state` 全体の provider-visible 展開

### Harness

持つ責務:

- provider-native call/output pairing の検証
- call id、arguments JSON、unknown tool、output kind の protocol validation
- tool routing
- read/write root、write approval、shell permission、timeout の safety boundary
- transcript artifact、proof artifact、sidecar refs の永続化
- verifier closeout を実行する場合の deterministic dispatch

持たない責務:

- task が本当に完了したかの semantic 判定
- external oracle 充足判定
- next action policy の provider-visible 命令化
- WorkFrame reducer
- `finish_call` 成功だけで lane を `completed` にすること

現行 harness にある semantic-ish control は移行対象として扱う。短期的には compatibility のため残してよいが、実装 close では責務ごとに `CompletionResolver` または WorkFrame projection へ移す。

### Tool Runtime

持つ責務:

- `read_file`、`search_text`、`write_file`、`apply_patch`、`run_command` などの実行
- managed command lifecycle、terminal status、output refs の保存
- execution contract、artifact evidence、verifier evidence、failure classification の typed evidence 化
- harness から明示的に要求された closeout verifier の実行

持たない責務:

- provider request の構築
- model plan の決定
- semantic finish allow/block の最終判断
- WorkFrame policy

`structured_finish_gate` / `apply_finish_gate()` は当面 tool/runtime 側で evidence を作るために残してよい。ただし最終的な lane completion authority は `CompletionResolver` に寄せる。

### WorkFrame Projection

持つ責務:

- transcript/tool result/typed evidence を compact に要約する
- goal、latest actionable、obligations、evidence refs、verifier freshness、finish readiness、step-shape metrics を示す
- `compact_sidecar_digest` 内の bounded fields として provider-visible にする
- replay/debug 用には full bundle を sidecar artifact に残す

持たない責務:

- tool 実行
- file edit
- provider API 呼び出し
- hard policy としての next action 強制
- raw transcript の代替

通常 repair の `required_next` は provider-visible projection から外す。必要な情報は次のように縮約する。

- `attention_hints`: model が気づくべき最新事実、missing obligation、repetition risk
- `tool_context`: 関連 tool result refs、path refs、verifier/artifact refs
- `finish_readiness`: finish の risk/blockers/missing evidence

nullable/limited な `required_next` が残ってよいのは次だけである。

- finish-ready を示す場合
- verifier-closeout が必要な場合
- blocked 状態を supervisor/reentry に返す場合
- 明示的な `transition_contract` compatibility variant を選んだ場合

### Compact Sidecar Digest Provider Surface

`compact_sidecar_digest` は provider-visible な唯一の dynamic sidecar surface である。これは full WorkFrame ではなく、bounded projection でなければならない。

Normative shape:

| Field | Required | Shape | Bound |
| --- | --- | --- | --- |
| `schema_version` | yes | integer | scalar |
| `digest_kind` | yes | string literal | `native_transcript_compact_sidecar_digest` |
| `runtime_id` | yes | string | native runtime id |
| `transport_kind` | yes | string | `provider_native` |
| `provider_input_authority` | yes | string literal | `transcript_window_plus_compact_sidecar_digest` |
| `source_of_truth` | yes | string | `response_transcript.json` |
| `transcript_hash` | yes | string | sha256-style digest |
| `sidecar_hashes` | yes | object | refs only, no embedded sidecars |
| `counts` | yes | object | small integers only |
| `latest_tool_results` | optional | list of compact result cards | max 6 items, each summary max 240 chars |
| `latest_evidence_refs` | optional | list of refs | max 12 refs |
| `workframe_projection` | yes | object | max 8 keys; see below |
| `provider_request_note` | optional | string | max 200 chars |
| `digest_hash` / `digest_text` | yes | string | hash plus one-line summary |

`workframe_projection` の provider-visible keys は次に限定する。

- `current_phase`
- `attention_hints`: max 6 observational hints。命令文にしない。
- `tool_context`: refs/path refs/tool result refs only。max 12 refs。
- `finish_readiness`: state、blockers、missing evidence refs。
- `verifier_state`: fresh/stale/failing/missing の compact state。
- `loop_signals`: `first_write_due` / `verifier_repair_due` などの bounded booleans。
- `evidence_refs`: resolver/model が辿れる refs。max 12 refs。
- `required_next`: nullable。通常は absent/null。許容条件は Required Next Migration の limited cases のみ。

`workframe_projection.current_phase` は observational label であり、action prescription ではない。

Allowed values:

- `orient`
- `cheap_probe`
- `prewrite_blocked`
- `ready_to_patch`
- `repair_after_write_failure`
- `verify_after_mutation`
- `repair_after_verifier_failure`
- `finish_ready`
- `finish_blocked`
- `controller_closeout`
- `blocked`

Source of truth:

- native transcript window、tool result index、typed evidence sidecars、finish readiness、resolver/closeout sidecar refs から reducer/projection が決定する。
- model-authored text、previous prompt wording、full `persisted_lane_state`、old frontier/todo/proof object は source にしない。
- previous projection は churn/debug comparison にだけ使い、`current_phase` の authority にはしない。

Constraint:

- `current_phase` 単体では tool call、file path、finish、verifier 実行を命令しない。
- provider-visible text で `current_phase=repair_after_verifier_failure therefore edit/apply_patch/run_command ...` のような imperative prescription を作らない。
- finish allow/block は `current_phase` ではなく `CompletionResolver` が evidence refs と obligations で決める。

Size invariants:

- `compact_sidecar_digest` serialized JSON は target `<= 4096` bytes、hard red gate `<= 6144` bytes。
- provider-visible top-level keys は 16 個以下にする。
- `workframe_projection` は full reducer output、full sidecar、full `persisted_lane_state`、raw command output を含めない。
- hard gate 違反時は provider request を作らず、projection artifact に size/field-count failure を残す。

### CompletionResolver

持つ責務:

- `finish_call` の semantic completion を allow/block する
- finish claim、typed evidence、WorkFrame finish readiness、task/execution oracle obligations、fresh verifier/closeout evidence を読む
- lane status を `completed` / `blocked_continue` / `blocked_return` に決める
- resolver decision を sidecar/artifact に永続化する
- paired `finish_output` の content に allow/block result と blockers を渡す

持たない責務:

- tool を実行すること
- verifier を直接走らせること
- provider-native ResponseItem を新設すること
- request 全体の prompt rendering

`CompletionResolver` の入力は pre-extracted evidence に限定する。harness/tool runtime closeout が作った typed evidence refs、finish-time closeout item refs、oracle obligation refs、compact finish readiness を受け取る。resolver は arbitrary transcript scan をしない。直接参照してよい transcript item は、対象 `finish_call`、paired `finish_output` candidate、finish-time closeout call/output の refs に限定する。

fresh verifier が足りない場合、`CompletionResolver` は verifier を実行しない。既に harness/tool runtime closeout が実行した evidence を消費するか、`blocked_continue` の next action として verifier 実行を要求する。

Resolver decision artifact:

- location: native artifact root の `resolver_decisions.jsonl`
- manifest: `proof-manifest.json` に `resolver_decisions_ref` と hash を載せる
- cardinality: valid `finish_call` ごとに 1 record
- source authority: sidecar/proof artifact only。native `ResponseItem` ではない。

Record schema:

```json
{
  "schema_version": 1,
  "decision_id": "resolver:turn-4:call-finish-1",
  "policy_version": "native-finish-resolver-v1",
  "lane_attempt_id": "attempt-...",
  "turn_id": "turn-4",
  "finish_call_id": "call_...",
  "finish_output_call_id": "call_...",
  "transcript_hash_before_decision": "sha256:...",
  "compact_sidecar_digest_hash": "sha256:...",
  "lane_status": "completed | blocked_continue | blocked_return",
  "result": "allow | block",
  "blockers": ["verifier_evidence_missing"],
  "missing_obligations": ["external_artifact:/tmp/frame.bmp"],
  "evidence_refs": ["ev:strict-verifier:..."],
  "closeout_refs": ["native-call:final-verifier-closeout"],
  "reason": "bounded human-readable summary"
}
```

### Replay / Fastcheck

持つ責務:

- native transcript と proof artifact から projection を再計算する
- pairing、manifest hash、sidecar digest、WorkFrame projection、resolver decision を検証する
- step shape、finish mismatch、required evidence refs の欠落、provider-visible drift を検出する

持たない責務:

- live turn 中の tool 実行
- live lane status の source of truth
- provider-visible policy の追加

## Finish State Machine

`finish_call` の state machine は次で固定する。

```text
model emits finish_call
  |
  v
Harness validates finish_call args
  - call_id exists
  - arguments JSON parses
  - allowed finish schema only
  - paired output can be emitted
  |
  +-- invalid args
  |     paired finish_output = protocol_error result
  |     CompletionResolver is not invoked
  |     lane_status remains active/current
  |     next request keeps transcript pair and allows retry
  |
  v
Harness dispatches finish-time closeout when trigger preconditions hold
  |
  +-- closeout ran
  |     append closeout call/output + typed evidence refs
  |
  +-- closeout not runnable
  |     pass closeout_missing blocker to resolver input
  |
  v
CompletionResolver evaluates semantic completion
  |
  +-- allow
  |     paired finish_output = allow result
  |     lane_status = completed
  |     resolver_decision sidecar/artifact = completed
  |
  +-- block and continue
  |     paired finish_output = block result + blockers
  |     lane_status = blocked_continue
  |     resolver_decision sidecar/artifact = blocked_continue
  |     next provider request keeps the blocked finish_call/finish_output in the transcript window
  |     next provider request also receives compact_sidecar_digest blockers
  |
  +-- block and return
        paired finish_output = block result + blockers
        lane_status = blocked_return
        resolver_decision sidecar/artifact = blocked_return
        stored transcript preserves the blocked finish_call/finish_output pair
        control returns to supervisor/reentry
```

`resolver_decision` は native `ResponseItem` ではない。source of truth の transcript には provider-native `finish_call` と paired `finish_output` だけを置く。resolver の詳細理由、evidence refs、missing obligations、policy version は sidecar/proof artifact に mirror する。

`blocked_continue` と `blocked_return` は同じ `blocked` ではない。

- `blocked_continue`: 同じ lane attempt で model に修復継続させる。例: verifier evidence missing、external artifact obligation missing、finish claim が stale。
- `blocked_return`: harness/tool runtime が安全に続行できない、budget/permission/contract 上 supervisor 判断が必要。

invalid args は semantic block ではなく protocol error である。harness は provider-native pairing を壊さず protocol-error `finish_output` を返すが、`CompletionResolver` は呼ばない。lane status は直前の active/current state のままにし、次 turn で model が正しい finish args または別 tool call を出せる。

## Required Next Migration

現行 `required_next` は WorkFrame redesign 由来の prescriptive pressure を持つ。native loop では provider-native transcript と model の判断を主経路にするため、通常 repair 指示としての `required_next` を provider-visible projection から削る。

移行方針:

- `patch_or_edit`、`inspect_latest_failure`、`run_verifier` などの ordinary repair `required_next` は `attention_hints` / `tool_context` / `finish_readiness.blockers` に collapse する。
- `native_sidecar_projection` の todo digest は `required_next_kind` 由来の `needs_<kind>` status に依存しない形へ寄せる。
- `required_next_evidence_refs` は汎用 `evidence_refs` / `tool_context.refs` として残す。
- `forbidden_next` は safety/repetition guard に限定し、普通の planning policy には使わない。
- `transition_contract` variant は互換 baseline として残してよいが、off-by-default の明示 variant でだけ有効にする。default native projection の根拠にしない。

許容される limited `required_next`:

```text
finish-ready:
  required_next.kind = "finish"

verifier-closeout:
  required_next.kind = "run_verifier"
  reason = "fresh verifier/closeout evidence required before finish"

blocked:
  required_next.kind = "blocked"
  reason/evidence_refs = supervisor/reentry 用の具体 blocker

transition_contract compatibility:
  selected variant が明示されたテスト/比較/旧 artifact 再生のみ
```

default path gate:

- default native provider projection は `required_next_kind` を 0 件にする。
- `required_next_kind` が出てよい test は `workframe_variant=transition_contract` を明示する。
- fastcheck は default artifact で `required_next_kind` / `needs_<kind>` todo digest が provider-visible に出たら失敗する。

## Persisted Lane State

`persisted_lane_state` は provider-visible に展開しない。現行 request は `task_payload` に `persisted_lane_state` 全体を入れているため、native boundary としては移行対象である。

方針:

- provider input に full `persisted_lane_state` を出さない。
- `active_work_todo`、`lane_hard_runtime_frontier`、`repair_history` などの旧 state object を model-visible state として復活させない。
- 必要な最小 digest だけを `compact_sidecar_digest` に fold する。
- digest fields は `status`、`latest relevant refs`、`finish/verifier freshness`、`blocked reason` などに限定する。
- full state は sidecar artifact / replay / debug に残す。

## 移行または Audit が必要な現行 Control

以下は現時点で semantic-ish control として扱い、実装時に移行先または保持理由を明示する。

| 現行 control | 現在の問題 | Owner phase | 移行先 | 残す場合の compatibility 理由 |
| --- | --- | --- | --- | --- |
| `finish_call` result が `status == "completed"` のとき lane status を `completed` にする処理 | transcript pairing と semantic completion が混ざる | Phase 3 | `CompletionResolver` | Phase 0-2 では current control inventory としてだけ保持。Phase 3 以降は resolver decision を authority にする |
| `_native_final_verifier_closeout` | harness 内で verifier 実行と completion 上書きを行う。現行 non-finish/max-turn path も直接 completion し得る | Phase 3 | finish-time 実行 dispatch は harness/tool runtime、判定は `CompletionResolver`。non-finish/max-turn closeout は direct completion 禁止 | verifier dispatch path を壊さないため、resolver 導入まで call site を残す |
| `structured_finish_gate` / `apply_finish_gate()` | tool runtime の execution evidence と lane finish 判定が近すぎる | Phase 3 | typed evidence producer として残し、authority は `CompletionResolver` | typed evidence producer は残す。completion authority としては使わない |
| `native_loop_control.first_write_due` / `verifier_repair_due` | 有用な loop-shape signal だが policy と混ざっている | Phase 1 | `loop_signals` として `attention_hints` / `finish_readiness` に folded preserve | signal 自体は step-shape diagnostic に必要なので bounded booleans として保持 |
| `native_loop_control.next_action_policy` | provider-visible な prescriptive policy になっている | Phase 1 | 削除。必要な事実だけ `attention_hints` / metrics digest へ縮約 | なし。Phase 1 で provider-visible path から削除 |
| `native_loop_control` instruction text | model に next action を命令している | Phase 1 | bounded hint に変更し、hard policy 文を削る | なし。bounded hint と metrics へ移す |
| `native_sidecar_projection` todo digest の `required_next_kind` 依存 | ordinary repair required_next を復活させる | Phase 1-2 | digest status を finish/verifier/blocker/readiness 中心に変更 | transition_contract compatibility only。default native path では count 0 を close gate にする |
| `_prompt_visible_workframe.required_next` | WorkFrame が model-visible decision object として残る | Phase 1-2 | debug/sidecar projection に退避し、provider-visible digest は bounded fields だけにする | transition_contract compatibility only。default native path では provider-visible から外す |
| request `task_payload.persisted_lane_state` | 旧 frontier/todo/proof state を provider-visible に広げる | Phase 1 | 最小 digest fields のみ `compact_sidecar_digest` に fold | なし。debug artifacts / persisted runtime state と provider input を分離する |

`native_loop_control` の hard policy と bounded hint は次の基準で分ける。

- hard policy: specific tool、file/path、action を imperative に処方する文。例: "must repair with edit/write/apply_patch"、"patch `vm.js`"、"do not continue broad exploration"。
- bounded hint: transcript/evidence から観測された事実。例: "`first_write_due=true` because probes exceeded threshold without source mutation"、"`verifier_repair_due=true` because latest strict verifier failed and no post-failure write exists"。
- close gate: provider-visible instruction text に imperative action verbs が specific tools/path targets と同時に出たら失敗する。
- preserve gate: `first_write_due` と `verifier_repair_due` は削除せず、`loop_signals` booleans と short observational `attention_hints` として残す。

## 実装フェーズ

### Phase 0: Docs / Static Audit

作業:

- この設計を基準に `native_tool_harness.py`、`native_sidecar_projection.py`、`native_workframe_projection.py`、`exec_runtime.py`、`execution_evidence.py` の current controls を棚卸しする。
- audit code を追加または更新する場合は、変更範囲を static audit 本体、CLI wrapper、focused tests、この設計書に限定する。
- code change を伴わない docs/artifacts-only 変更の場合だけ `git diff --check` と changed-file scope check を必須確認にする。
- migration table の各 item に owner phase、移行先、残す場合の compatibility 理由を付ける。

Close gate:

- semantic-ish controls の migration table が実装 issue または design checklist として追跡できる。
- audit-code change なら changed files が `src/mew/implement_lane/native_boundary_audit.py`、`scripts/check_native_tool_loop_boundary.py`、`tests/test_native_boundary_audit.py`、この設計書に限定される。
- docs-only change なら changed files が `docs/` と `.codex-artifacts/` だけである。
- audit 対象の runtime source (`native_tool_harness.py`、`native_sidecar_projection.py`、`native_workframe_projection.py`、`exec_runtime.py`、`execution_evidence.py`) を変更していないことを `git status --short --untracked-files=all` または同等の scope check で確認する。

Tests:

- `git diff --check`
- changed-file scope check: docs/artifacts-only or audit-code-only
- migration table checklist audit
- focused audit tests

### Phase 1: Compact Sidecar Digest Boundary

作業:

- `compact_sidecar_digest` に bounded WorkFrame projection fields を追加する。
- provider-visible な full `WorkFrame` object、full `persisted_lane_state`、旧 todo/frontier/proof object を出さない。
- ordinary repair `required_next` を `attention_hints` / `tool_context` に collapse する。
- `native_loop_control.first_write_due` / `verifier_repair_due` を `loop_signals` と observational hints として preserve する。
- `next_action_policy` と imperative instruction text を provider-visible path から落とす。

Close gate:

- provider request inventory が `native_transcript_window` + `compact_sidecar_digest` だけを dynamic state として報告する。
- `persisted_lane_state` 全体が provider input に出ない。
- `transition_contract` compatibility 以外で ordinary repair `required_next.kind` が provider-visible digest に出ない。
- default native projection の `required_next_kind` count が 0 である。
- `compact_sidecar_digest` は serialized JSON `<= 6144` bytes、top-level keys `<= 16`、`workframe_projection` keys `<= 8`。
- provider-visible hint text に specific tool/path target 付き imperative action prescription が出ない。
- `workframe_projection.current_phase` は allowed enum のみで、observational label としてだけ使われる。

Tests:

- `tests/test_native_workframe_projection.py`
- `tests/test_native_sidecar_projection.py`
- provider input inventory の新規 fixture test
- default-path fixture: `required_next_kind` entries are zero
- compact digest size/field-count static test
- native loop signal preservation test for `first_write_due` / `verifier_repair_due`
- current_phase enum/source/observational-only projection test

### Phase 2: CompletionResolver Skeleton

作業:

- `CompletionResolver` を harness 外に定義する。
- 入力 schema を finish claim、typed evidence refs、finish readiness、oracle obligations、latest verifier/closeout evidence に限定する。
- 出力 schema を `completed` / `blocked_continue` / `blocked_return` にする。
- resolver decision artifact を追加する。

Close gate:

- resolver は tool runtime を import しない。
- resolver は command/verifier を実行しない。
- resolver は pre-extracted typed evidence refs と finish-time closeout refs だけを読む。
- resolver decision は native ResponseItem ではなく `resolver_decisions.jsonl` と proof manifest ref にだけ保存される。

Tests:

- resolver unit tests: allow, missing verifier -> `blocked_continue`, unsafe/budget blocker -> `blocked_return`
- import-boundary test: resolver から tool runtime execution path を呼べない
- artifact schema test for `resolver_decisions.jsonl`
- resolver input fixture that rejects arbitrary transcript scan dependencies

### Phase 3: Finish Call Integration

作業:

- harness の finish handling を state machine に合わせる。
- args validation 後に resolver を呼ぶ。
- paired `finish_output` は allow/block result を含める。
- lane status は resolver output で決める。
- invalid args では protocol-error `finish_output` を pair し、resolver は呼ばない。

Close gate:

- `finish_call` が valid なら allow/block に関係なく paired `finish_output` が残る。
- missing oracle/verifier obligation では transcript は paired、lane は `completed` にならない。
- `blocked_continue` は blocked finish pair を次 transcript window に残し、blockers を digest 経由で渡す。
- `blocked_return` は stored transcript に blocked finish pair を残すが、next provider request は発行しない。
- invalid args は lane status を変えず、次 turn retry を許す。

Tests:

- native transcript pairing tests
- finish args validation tests
- blocked finish continuation fixture
- invalid finish args protocol-error fixture
- replay が resolver decision artifact と paired finish output の整合を検証する test

### Phase 4: Verifier Closeout Boundary

作業:

- `_native_final_verifier_closeout` を「実行 dispatch」と「completion 判定」に分離する。
- closeout verifier 実行は harness/tool runtime に残す。
- closeout 結果の completion 判定は resolver が evidence として消費する。
- closeout dispatch trigger を固定する。

Closeout trigger semantics:

- trigger: valid `finish_call` の args validation 後、resolver invocation 前。
- precondition: latest source mutation または artifact-producing command の後に fresh strict verifier evidence がない。
- precondition: task/execution contract に configured verifier または closeout verifier command がある。
- precondition: remaining wall budget が configured minimum 以上で、permission/root policy が verifier 実行を許す。
- output: harness/tool runtime は closeout call/output と typed evidence refs を transcript/sidecar に追加する。
- no-run case: budget/permission/command missing の場合、harness は tool を実行せず closeout_missing reason を resolver input に渡す。

Non-finish / max-turn closeout migration:

- current risk: existing harness closeout can run after the model loop without a valid `finish_call` and can set lane status directly.
- target invariant: no lane may become `completed` without a valid `finish_call` that reaches `CompletionResolver` and receives an allow decision.
- retained option: non-finish/max-turn closeout may run only to produce evidence/status for supervisor/reentry, or to seed a later valid finish resolver path. It returns `blocked_return`, `needs_reentry`, or equivalent non-completed status with closeout evidence refs.
- removal option: delete the non-finish/max-turn closeout path entirely, with a test proving max-turn or no-finish attempts cannot complete from closeout evidence alone.
- forbidden behavior: synthesize a `finish_call`, synthesize resolver allow, or set `lane_status=completed` from closeout pass without model finish.

Close gate:

- closeout pass/fail が harness 内で直接 lane status を上書きしない。
- closeout evidence が resolver input に入る。
- fresh verifier がない場合、resolver は tool 実行せず `blocked_continue` を返せる。
- harness と resolver が同じ freshness definition を使う。
- no valid `finish_call` の max-turn/non-finish closeout は `completed` を返さない。

Tests:

- closeout pass -> resolver completed
- closeout fail -> resolver blocked_continue または blocked_return
- no budget/no permission -> blocked_return
- closeout trigger fixture: pending mutation without later verifier runs closeout before resolver
- closeout no-run fixture: missing command/budget produces resolver blocker without tool execution
- non-finish/max-turn closeout pass fixture: no `finish_call` means no lane completion
- removal-path fixture, if chosen: max-turn no-finish attempts have no closeout completion path

### Phase 5: Replay / Fastcheck

作業:

- native transcript、compact digest、resolver decision artifact を replay で再検証する。
- old `required_next_kind` todo digest 依存を fastcheck で検出する。
- provider-visible state が増えていないことを static/drift gate 化する。
- compact digest size/field-count と imperative-instruction drift を static gate 化する。

Close gate:

- saved native artifact から deterministic に same digest/resolver decision が再計算できる。
- `raw transcript + compact_sidecar_digest` が provider input authority として維持される。
- old model-JSON / full WorkFrame / full persisted lane state drift が検出される。
- default native artifact で `required_next_kind` / `needs_<kind>` todo digest が 0 件である。
- `transition_contract` required_next は explicit off-by-default variant artifact でだけ許可される。

Tests:

- `tests/test_hot_path_fastcheck.py`
- native artifact replay fixture
- static drift test for provider-visible sections
- compact digest size/field-count replay gate
- default-vs-transition_contract required_next compatibility gate

## 非ゴール

- provider-native transcript を置き換える新しい model-visible state object の導入。
- WorkFrame を planner、tool router、completion authority にすること。
- task-specific MIPS/DOOM/Terminal-Bench solver heuristic。
- `persisted_lane_state`、frontier、todo、proof object の provider-visible 復活。
- `CompletionResolver` に verifier/tool 実行責務を持たせること。
- `finish_call` を拒否して transcript pairing を壊すこと。
- non-finish/max-turn closeout pass を lane completion として扱うこと。
- docs-only design を実装完了扱いすること。

## Drift Traps

- `compact_sidecar_digest` の中身が full WorkFrame になり、実質的に新 object になる。serialized JSON `> 6144` bytes、top-level keys `> 16`、`workframe_projection` keys `> 8` は static gate failure。
- ordinary repair `required_next` が名前だけ変えて `next_action_policy` や instruction text として復活する。
- `blocked_continue` を単なる `blocked` として扱い、継続可能な修復が supervisor return になる。
- resolver decision を native `ResponseItem` として transcript に混ぜる。
- closeout verifier を resolver が直接実行し、completion 判定と tool runtime が再結合する。
- no-finish/max-turn closeout が passing verifier を理由に `lane_status=completed` を返す。
- `current_phase` が enum label ではなく、tool/path/action を命令する hidden policy になる。
- `persisted_lane_state` の便利さに戻り、old frontier/todo/proof が provider-visible に漏れる。
- replay/fastcheck が sidecar artifact を source of truth と誤解し、native transcript より強い authority を持つ。

## Reviewer Checklist

- provider-native transcript が source of truth として残っているか。
- provider-visible state が `compact_sidecar_digest` に bounded されているか。
- WorkFrame projection が planner 化していないか。
- `finish_call` pairing と lane completion が分離されているか。
- verifier 実行責務が harness/tool runtime に残り、resolver は evidence consumer だけになっているか。
- ordinary repair `required_next` が provider-visible default path から消えているか。
- `persisted_lane_state` が full provider input になっていないか。
