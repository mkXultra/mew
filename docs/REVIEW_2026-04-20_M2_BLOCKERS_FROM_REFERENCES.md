# REVIEW 2026-04-20 — M2 Blockers and Reference Patterns

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 強制ではなく**意見**。ROADMAP_STATUS の Milestone Gate rule に従い、**active M2 Done-when を閉じるための supporting implementation evidence** として提示
**生成条件**: 2026-04-20 00:00 JST、commit `10d01b8` 時点、914 commits 観測後
**関連**:
- `docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md`（観測された M2 blocker）
- `docs/ADOPT_FROM_REFERENCES.md`（§5.1 / §5.5 / §5.11 と関連）
- `docs/REVIEW_2026-04-19_STRUCTURAL_TIMING.md`（構造変更の timing）
- `docs/REVIEW_2026-04-19_REFACTOR_CADENCE.md`（complexity 管理）

---

## 0. 動機

2026-04-19 の comparative dogfood で mew は `fresh_cli_preferred` と記録された。M2 Done-when "would not prefer to restart in a fresh coding CLI" は未達。  
`ROADMAP_STATUS.md` の Milestone Gate rule に従い、次の implementation task は **"close one partial/unmet Done-when criterion for the active milestone"** であるべき。

本 review は、観測された M2 blocker に対して `references/fresh-cli/{claude-code, codex}` から**直接当てられる実装パターン**を 4 つ整理したもの。いずれも実在するコードを pinpoint 参照する。

ROADMAP_STATUS の優先順位を破らない。本 review の提案はすべて **active M2 Done-when を閉じるため**の候補。

---

## 1. 観測された M2 blocker（実測値）

`ROADMAP_STATUS.md` と `docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md` から抽出：

| # | Blocker | 実測値 / 証拠 |
|---|---|---|
| B1 | **paired source/test approval の rollback loop** | comparative dogfood #241: test 先を要求 → source 未存在で verify fail → rollback loop。mew 側で approval_confusions=2, verification_confusions=2, restart_or_recovery_steps=2 |
| B2 | **first_tool_latency が遅い** | `mew metrics --kind coding` p95 = **30.15s** |
| B3 | **observer/supervision overhead が fresh CLI より重い** | dogfood レポート: "for small localized changes, mew's persistent context is useful but the observer/supervision overhead remains higher than a fresh CLI" |
| B4 | **model_resume_wait が遅い** | `mew metrics --kind coding` p95 = **25.25s** |

Fresh CLI (codex-ultra) との comparative 結果：fresh CLI 側は approval_confusions=0, verification_confusions=1, dead_waits_over_30s=0, restart_or_recovery_steps=0。差は明確。

---

## 2. Blocker × Reference パターン マッピング

### B1 + B2: paired-test loop と first_tool_latency は **同じ根**

この 2 つは独立問題に見えるが、**どちらも "1 turn = 1 action" 構造に起因する**。

#### 根本原因
- mew は THINK → full response 受信 → 単一 action parse → 1 tool 実行、の直列
- そのため first tool が出るまで LLM 応答完了 + parse を待つ（30s の大半）
- そして **source edit と test edit を「同じ turn の別 action」として emit できない**ため、approval/verify の順序問題が発生

#### Reference パターン: **Streaming Tool Executor + Multi-Tool-per-Turn**

**Claude-code**: `src/services/tools/StreamingToolExecutor.ts`
- **Line 40** (verified): `export class StreamingToolExecutor`
- **Line 26, 84, 105-108, 119, 129, 144** (verified): `isConcurrencySafe: boolean` フィールドを全 tool call が持つ
- **Line 129**: `canExecuteTool(isConcurrencySafe)` — 並列安全ならすでに走っている tool とも共存
- **Line 144-148**: queue 処理で、concurrency_safe なら並列 spawn、そうでなければ排他待ち

動作：
1. API から `tool_use` block が **stream 到着と同時に dispatch**
2. read 系は並列、write 系は排他
3. 1 つの model response に複数 `tool_use` があれば**並列実行**
4. 結果が出た順に UI / approval / verification へ

**Claude-code Tool.ts** の裏付け：
- **Line 402** (verified): `isConcurrencySafe(input): boolean` が tool method
- **Line 670** (verified): "Renders multiple parallel instances of this tool as a group"
- **Line 759** (verified): fail-closed default `isConcurrencySafe: (_input?: unknown) => false`

**Codex**: `codex-rs/protocol/src/protocol.rs`
- **Line 379** (verified): `pub enum Op` (Submission Queue)
- **Line 420, 429, 437** (verified): `UserTurn { approval_policy, sandbox_policy, ... }`
- SQ/EQ model で event stream に複数 tool call が乗る

#### mew への適用

B1 (paired-test loop) の解決経路：
```
現状: THINK → emit single action → approve → execute → verify → next THINK
      → test だけ先に出て、source がない → verify fail → rollback → loop

変更: THINK → emit MULTIPLE actions in same response
      → [edit_test, edit_source] が同一 turn で出る
      → approval は「この turn の action batch」として扱う
      → 両方 apply してから verify 走る
      → pair として verify 成功 OR rollback
```

B2 (first_tool_latency) の解決経路：
```
現状: 30s 中、model 応答完了待ち (~15-20s) + parse + approval prep (~5-10s)

変更: API stream 受信中に tool_use block を即 dispatch
      → read_file 等の concurrency_safe tool は model 応答継続中に走る
      → first tool output が 5-10s まで短縮可能
```

**実装規模**: 800-1,500 LOC

主要な変更点：
- `src/mew/plan_schema.py` を multi-action batch 対応に
- `src/mew/agent.py` / `step_loop.py` / `work_loop.py` を streaming 解釈に
- `src/mew/action_application.py` / approval 系を batch 単位に
- 各 work tool に `concurrency_safe` 属性を追加（read 系=True、write/shell=False）
- `asyncio` (stdlib) または `anyio` (dep 許容時) の採用判断

---

### B3: observer/supervision overhead — Permission Mode spectrum

#### Reference パターン: **claude-code の Permission Mode（5 段階）**

**Claude-code**: `src/types/permissions.ts`
- **Line 16-21** (verified):
  ```typescript
  export const EXTERNAL_PERMISSION_MODES = [
    'acceptEdits',
    'bypassPermissions',
    'default',
    'dontAsk',
    'plan',
  ]
  ```
- **Line 33-38** (verified): 内部 mode に `auto` 追加（feature-flagged）
- `src/utils/permissions/PermissionMode.ts` が 124 行で mode 間の遷移 / 表示 / schema を定義

各 mode の意味（推定、命名から）：
| Mode | 挙動 |
|---|---|
| `default` | 全 write / shell に approval prompt |
| `acceptEdits` | file edit は自動承認、shell は prompt |
| `bypassPermissions` | YOLO。すべて自動 |
| `plan` | 計画のみ、書き込まない |
| `dontAsk` | quiet default（UX-wise でロックしない） |
| `auto` | classifier でリスク判定 |

#### mew の現状

- `mew work --allow-read / --allow-write / --allow-verify / --allow-shell` の flag 組み合わせ
- **mode 概念は無い**。全 flag を明示しないと走らない
- 小さな低リスク変更でも同じ ceremony

#### mew への適用

```
--approval-mode {default, acceptEdits, bypass, plan}
```

実装：
- `src/mew/permissions.py`（新規 or 強化）に `PermissionMode` enum
- mode → concrete gate の mapping
- CLI flag として `--approval-mode` 追加
- default は既存挙動 backward-compat

**実装規模**: 300-500 LOC

ユーザーが明示的に `--approval-mode acceptEdits` or `bypass` を選んだ場合、小さい変更の ceremony が激減。comparative dogfood での **observer overhead が fresh CLI 並みに**。

補足：これは **ADOPT §5.5 PermissionContext Frozen** と直交する追加。Frozen Context は「ターン単位で政策を固める」、Permission Mode は「政策の shorthand を与える」。

---

### B4: model_resume_wait 25s — Snapshot resume

#### Reference パターン: **claude-code AgentMemorySnapshot + Codex session-scoped WebSocket**

**Claude-code**: `src/tools/AgentTool/agentMemorySnapshot.ts` (実在確認済み)
- `checkAgentMemorySnapshot`, `initializeFromSnapshot` が `loadAgentsDir.ts:51-53` から import されている
- 完了時に snapshot 保存、resume 時に history replay ではなく snapshot load

**Codex**: `codex-rs/core/src/client.rs`
- **Line 12-23** (verified): WebSocket prewarm、session-scoped connection reuse
- **Line 187, 200, 235** (verified): "WebSocket fallback is session-scoped... reuses it across multiple requests during that turn"

**Codex state persistence**: `codex-rs/state/src/runtime.rs`
- SQLite runtime + partition-based log eviction
- 接続再確立は state load → stream 再開、機械的

#### mew の現状

- `context_checkpoint` が直近に追加済み（`src/mew/context_checkpoint.py` +13 LOC、checkpoint API 拡張）
- しかし resume は**依然として bundle 再構築 + model 再読**依存
- model_resume_wait 25s の大半は「会話履歴を LLM に通して再構築」

#### mew への適用

既存の `context_checkpoint` を **full snapshot** に成長させる：

```python
# src/mew/snapshot.py (新規、ADOPT §5.11 参照)
@dataclass(frozen=True)
class WorkSessionSnapshot:
    schema_version: int
    session_id: str
    state_hash: str          # drift detection
    last_effect_id: int
    working_memory: dict
    touched_files: list[str]
    pending_approvals: list[dict]
    continuity_score: float | None
    active_memory_refs: list[str]
    unknown_fields: dict     # 未知フィールドを捨てず保持
```

Load 時は：
- schema_version check
- state_hash diff 確認
- diff 小 → snapshot usable、model に送る context は **snapshot summary + 直近 N turn のみ**
- diff 大 → partial resume、drift 報告

**実装規模**: 400-700 LOC

既存 `context_checkpoint.py` (13 LOC と推定) を足場に段階的に成長させれば、大 breaking 変更は不要。

---

## 3. 優先順位

comparative dogfood の blocker criticality と実装 ROI で ranking：

| 優先 | # | Blocker | 対応 | 実装 LOC | M2 score 影響 |
|---|---|---|---|---|---|
| **1** | B1 + B2 | paired-test loop + first_tool_latency | **Streaming Tool Executor + Multi-Tool-per-Turn** | 800-1,500 | **+8-10** |
| 2 | B3 | observer overhead | Permission Mode spectrum | 300-500 | **+3-5** |
| 3 | B4 | model_resume_wait | Snapshot resume（既存 context_checkpoint 拡張） | 400-700 | **+3-4** |

**合計**: 1,500-2,700 LOC で M2 score +14-19 ポイント見込み → 65 → ~80（M2 close 可能域）

**実測 velocity (~350 LOC/hour feature) で換算**:
- 優先 1: 4-5 時間（構造変更で ×0.5 係数なら 8-10 時間）
- 優先 2: 1-2 時間
- 優先 3: 1-2 時間

**合計 実装時間**: 10-14 時間。暦換算では 1-2 週間（dogfood cycle 込み）。

---

## 4. 最短経路の推奨

### Step 1: Streaming Tool Executor + Multi-Tool-per-Turn（優先 1）

B1 と B2 を同時に解決する唯一の手。以下の順で進める：

1. **RFC を書く** (`docs/RFC_streaming_tool_executor.md`、1-2 時間)
   - 既存 THINK/ACT/tool の構造をどう保つか
   - asyncio / anyio / sync + thread pool の trade-off
   - multi-action batch の schema（`plan_schema.py` の拡張）
   - approval が batch 単位になることの UX 影響

2. **Batch schema を先に**
   - `plan_schema.py` に `Actions: list[Action]` を許容
   - 既存 single action はそのまま動く backward compat

3. **Streaming 解釈**
   - `agent.py` / `step_loop.py` で API stream から tool_use を順次取り出す
   - `action_application.py` で concurrency_safe の並列実行
   - 既存 tool に `concurrency_safe` 属性を注入（`read_file` 等は True）

4. **Approval を batch 単位に**
   - `work_session.py` の pending_approvals 構造を batch 対応に
   - `--approve-all` は既にあるので、それが batch を一撃 approve に使える

5. **comparative dogfood を再走行**
   - 同じ task (paired source/test edit) で mew vs fresh CLI
   - approval_confusions、first_tool_latency、restart_or_recovery_steps の改善を測定

**成功基準**: comparative dogfood で `mew_preferred` または `equivalent`、first_tool_latency p95 < 10s。

### Step 2: Permission Mode（優先 2、並行可）

Step 1 の streaming 実装と独立。以下は並行可能：

1. `src/mew/permissions.py` に enum 追加
2. `--approval-mode` flag を CLI に
3. 各 tool の risk 分類を既存の verification_confidence / same_surface_audit と整合
4. dogfood で mode 別の ceremony time を測定

**成功基準**: `--approval-mode acceptEdits` で小変更の dogfood が fresh CLI 並みのテンポで走る。

### Step 3: Snapshot resume（優先 3）

Step 1 完了後に着手推奨（async 化が先に収まった方が、snapshot 設計が clean）。

1. 既存 `context_checkpoint.py` を `snapshot.py` に拡張
2. `schema_version`, `state_hash`, `unknown_fields` を追加
3. Load 時の usable/partial/unusable 判定
4. resume path を model 再読から snapshot load に差し替え

**成功基準**: `model_resume_wait` p95 < 8s。

---

## 5. 検証済み pinpoint 参照 index

本 review で引用するもの全て：

### claude-code
```
src/Tool.ts:402                          isConcurrencySafe(input): boolean
src/Tool.ts:670                          Renders multiple parallel instances
src/Tool.ts:709                          isConcurrencySafe in ToolDefaults
src/Tool.ts:759                          fail-closed default: false
src/services/tools/StreamingToolExecutor.ts:40     class StreamingToolExecutor
src/services/tools/StreamingToolExecutor.ts:26     isConcurrencySafe field
src/services/tools/StreamingToolExecutor.ts:84,105-108,119     concurrency-safe detection
src/services/tools/StreamingToolExecutor.ts:129    canExecuteTool logic
src/services/tools/StreamingToolExecutor.ts:144-148 queue dispatch
src/types/permissions.ts:16-21           EXTERNAL_PERMISSION_MODES = [acceptEdits, bypassPermissions, default, dontAsk, plan]
src/types/permissions.ts:33-38           INTERNAL_PERMISSION_MODES (adds 'auto')
src/utils/permissions/PermissionMode.ts  full mode machinery
src/tools/AgentTool/agentMemorySnapshot.ts  snapshot save/load/init
src/tools/AgentTool/loadAgentsDir.ts:51-53  snapshot import usage
```

### codex
```
codex-rs/protocol/src/protocol.rs:379    pub enum Op (SQ)
codex-rs/protocol/src/protocol.rs:420    pub struct UserTurn
codex-rs/protocol/src/protocol.rs:429    approval_policy
codex-rs/protocol/src/protocol.rs:437    sandbox_policy
codex-rs/protocol/src/protocol.rs:1557   EventMsg::TurnAborted
codex-rs/core/src/client.rs:12-23        WebSocket prewarm, session-scoped
codex-rs/core/src/client.rs:187,200,235  session-scoped WebSocket reuse
codex-rs/state/src/runtime.rs            StateRuntime + SQLite partition eviction
```

### 未検証で本 review で引用したもの（採用前に確認）
- claude-code `FileEditTool` の multi-edit サポートの有無（types.ts 見た範囲では single-edit）
- Permission Mode 各値の具体的挙動（名前から推測）

これらは実装 agent が採用前に実地 verify することを推奨。

---

## 6. 私が間違っている可能性

実装 agent の local context がより正確である領域：

1. **Streaming 化の async runtime 選択**: `asyncio` vs `anyio` vs `trio` vs sync+thread の trade-off は実装 agent の方が判断材料を多く持つ

2. **Multi-action batch の UX 影響**: 既存 `mew focus` / `mew next` / cockpit 表示が「1 action = 1 line」前提になっている可能性。batch 化で表示が崩れないか要検証

3. **approval_mode の default**: `default` のままで backward compat は守れるが、dogfood で最も体感差が出るのは `acceptEdits`。どの mode を default にするか、dogfood 実験が必要

4. **Snapshot vs context_checkpoint の境界**: 既存 `context_checkpoint.py` がどこまで snapshot に成長可能か、agent が現コードを見て判断すべき

5. **implementation order**: Step 1/2/3 を並行にするか直列にするかは、active dogfood focus 次第。Step 1 は構造変更なので**他の feature work を一時止めて集中する**ほうが筋が良い可能性

6. **LOC estimate**: 過去の実測 velocity ~350 LOC/hour は additive 作業。**構造変更で 50% に落ちる**可能性は織り込んだが、30% まで落ちる可能性も残る

これらは実装 agent が **「違う」と判断したら本 review を優先しなくていい**。

---

## 7. 本 review の扱いについて

`ROADMAP_STATUS.md` の Milestone Gate rule は：
> "Evaluate only that milestone's Done-when criteria. Mark each criterion as met, partial, or unmet with concrete evidence."
> "The next task must do one of: close one partial/unmet Done-when criterion, reduce a measured blocker, collect specific dogfood evidence."

本 review は **3 つ目「specific dogfood evidence の解釈と、それに対する implementation option の提示」** に相当する。

`docs/ADOPT_FROM_REFERENCES.md` §0.1 が defining する load-bearing 判断は維持する。本 review は ADOPT §5.1 (Streaming Tool Executor) と §5.11 (AgentMemorySnapshot) について、**現在の blocker に対して採用判断を前倒しする根拠**を提供するもの。

---

## 8. TL;DR

```
B1 paired-test loop     ┐
                        ├── Streaming Tool Executor + Multi-Tool-per-Turn
B2 first_tool_latency   ┘   (claude-code StreamingToolExecutor.ts:40)
                            800-1,500 LOC

B3 observer overhead    ── Permission Mode spectrum
                            (claude-code types/permissions.ts:16-21)
                            300-500 LOC

B4 model_resume_wait    ── Snapshot resume
                            (claude-code AgentMemorySnapshot)
                            400-700 LOC
```

**推奨順**: 優先 1 (B1+B2 同時解決) → 優先 2 (B3) → 優先 3 (B4)。

**期待**: M2 score 65 → 80（close 可能域）。実装時間 10-14 時間。暦で 1-2 週間。

優先 1 が M2 close の最大レバー。優先 1 単体でも comparative dogfood が `fresh_cli_preferred` → `equivalent` または `mew_preferred` に転じる可能性が高い。

---

## 9. Addendum 2026-04-20 — New Blocker From Task Shape Dogfood

### 9.1 観測された新しい evidence

- commits: `be23dd5 Add M2 task shape dogfood option` (00:14)、`74e8afe Record M2 task shape comparison` (00:16)
- task: #254（m2-task-shape option を dogfood.py に追加する task）
- mew sessions: #247, #248
- fresh CLI: `/tmp/mew-fresh-task-shape` worktree
- 結果: `comparison_result.status=inconclusive`、`resident_preference.choice=inconclusive`

#### mew 側 gate evidence（`docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md` 末尾から）
- `changed_or_pending_work=true`
- `risk_or_interruption_preserved=true`
- `runnable_next_action=true`
- `continuity_usable=true` (**9/9 continuity score**)
- `verification_after_resume_candidate=false`
- `interruption_resume_gate.mew.status=not_proved`

**観察**: mew は interruption 後の resume が**非常に強い**（9/9 continuity、世界状態 / active project memory / 失敗ステップ / pending steer 全部保持）。しかし**実装を完了できなかった**ため `not_proved`。

#### 具体的な詰まり方（dogfood レポートから引用）

> "the model correctly narrowed from `src/mew/dogfood.py` to `src/mew/cli.py` after an interrupt-submit steer, then hit paired-test steering and **attempted to inspect `tests/test_cli.py`, which does not exist**. It stopped with no passing verification candidate."

実際には `tests/test_dogfood.py` に cli parser の coverage があるが、**convention 依存の steering が `tests/test_cli.py` を探しに行って失敗**した。

### 9.2 B5: Paired-test file discovery fails on convention mismatch

#### 根本原因

`src/mew/work_session.py` の paired-test steering が **`src/mew/{name}.py` → `tests/test_{name}.py`** の convention を前提としている：
- `:1771-1873` 付近: `_same_surface_audit_*` / `build_same_surface_audit_checkpoint`
- `:2262`: "latest verifier passed, but does not appear to cover every inferred paired test"

mew の現状の test layout は：
```
src/mew/cli.py         → テストは tests/test_dogfood.py の parser test にある
src/mew/commands.py    → 多くのテストが tests/test_commands.py だが一部は test_dogfood.py
src/mew/dogfood.py     → tests/test_dogfood.py（convention 一致）
```

つまり、**実際のテスト構成は convention に半分しか従っていない**。mew のテストは feature 単位で組織されていて、1 test file が複数の src file をカバーする。

steering の default 仮定が壊れた時、model は：
1. 指定された `tests/test_cli.py` を開こうとする
2. 存在しない
3. **fallback 経路が steering に無い** → 停止

この blocker は B1 (paired-test approval loop) と関係するが**別物**。B1 は「approval 順序」、B5 は「test 発見の失敗」。

### 9.3 Reference パターン

#### Claude-code: **No hardcoded convention, model-driven discovery**

`references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:43` (verified):

> "**Read the project's CLAUDE.md / README for build/test commands and conventions.** Check package.json / Makefile / pyproject.toml for script names. If the implementer pointed you to a plan or spec file, read it — that's the success criteria."

つまり claude-code の verification subagent は：
1. **CLAUDE.md / README を先に読む**
2. `pyproject.toml` / `Makefile` の script 名を調べる
3. **GrepTool + GlobTool で実際のテストファイルを探す**
4. 固定 convention に従わない

道具：
- `src/tools/GrepTool/GrepTool.ts`（file 内容検索）
- `src/tools/GlobTool/GlobTool.ts`（file path 検索）
- `src/tools/AgentTool/built-in/verificationAgent.ts`（モデル駆動の verification）

#### testmon はすでに mew の dep である

`pyproject.toml:12`:
```toml
"pytest-testmon>=2.1"
```

testmon は**実行されたテストと触れられたソースの coverage DB** を持っている。`.testmondata` に：
- どのテストがどのソース行を触ったか
- source 変更時に影響するテストの計算

これは **「`src/mew/cli.py` を変更した時、どのテストが走るべきか」** の問いに**データで答える**。

### 9.4 B5 の解決策

3 つの直交する対処。**最小変更で最大効果は (a)**。

#### (a) Test coverage DB-backed discovery（**最推奨、軽量**）

paired-test steering に入る前、**テストカバレッジの事実を injection**：

```python
# src/mew/test_discovery.py (新規、~150-200 LOC)
import subprocess
from pathlib import Path

def find_tests_covering(source_path: Path) -> list[Path]:
    """
    優先順位:
    1. pytest-testmon coverage DB (`.testmondata`) から引く
    2. 引けなければ grep で "from mew.{name}" / "import {name}" を
       tests/ 以下で検索
    3. それも引けなければ convention `tests/test_{name}.py` fallback
    4. convention file も無ければ empty を返す（steering に "no tests found" と伝える）
    """
    # 1. testmon lookup
    if _testmon_available():
        return _testmon_query(source_path)
    # 2. grep fallback
    module_name = source_path.stem
    refs = _grep_imports_of(module_name, in_dir=Path("tests"))
    if refs:
        return refs
    # 3. convention fallback
    conv_path = Path("tests") / f"test_{module_name}.py"
    if conv_path.exists():
        return [conv_path]
    return []
```

`work_session.py` の paired-test steering を `find_tests_covering()` 呼び出しに置き換える：
- 現在: `tests/test_{name}.py` をハードコード
- 変更後: `find_tests_covering(source_path)` が返したリストを model に **「既存の関連テスト: X, Y, Z. これらを更新するか、新規作成の正当化を示してください」** として提示

**実装規模**: 150-250 LOC（`test_discovery.py` + work_session 統合 + tests）

#### (b) Model-driven fallback（**中規模、robust**）

steering 文言を**固定コマンドから model 指示に変更**：

- 現在: "Inspect `tests/test_{name}.py` first"
- 変更後: "Find existing tests that cover `{source_path}`. Use `search_text` to look for imports of this module under `tests/`. If none exist, propose creating new tests OR justify why this source change needs no test."

これは **claude-code の verificationAgent prompt スタイル**。model に search_text / glob を使わせる。prompt の 1 行変更でできるが、**既存の paired-test audit logic を緩める必要**がある。

**実装規模**: 30-100 LOC（prompt 文言 + audit logic の relax）

#### (c) Multi-tool-per-turn が構造的に解く（**B1 と同じ fix**）

model が 1 turn で source edit と test edit を**同時に emit**できるようになれば：
- test 探索も source 編集も**並行に走る**
- "test file がない → source edit を止める" という sequential 依存が消える
- 「source 先に、test 後から」の選択も可能（model が batch を組み立てる時に決める）

これは B1 と**完全に同じ fix**（Streaming Tool Executor + Multi-Tool-per-Turn）。B5 の根本解決は B1 の副産物として得られる。

### 9.5 実装順序の推奨

| Phase | 内容 | LOC | 効果 |
|---|---|---|---|
| **今すぐ (small)** | **(a) testmon-backed test_discovery.py** | 150-250 | B5 を直接緩和、dogfood blocker 即時解消 |
| 並行 (small) | (b) steering 文言 relax | 30-100 | model に search を許可 |
| 優先 1 と一緒 | (c) Multi-tool-per-turn | （B1 内） | B5 の根本解決 |

**(a) + (b) を先に入れる**ことで、**B1 の大きな構造変更を待たずに M2 comparative dogfood の次 round で interruption_resume_gate を proved にできる可能性**がある。interruption_resume_gate が proved になれば、M2 Done-when の 1 項目が met に進む。

### 9.6 B5 を入れた場合の M2 score 影響

| Phase | M2 score 影響 |
|---|---|
| B5 (a) 単体 | **+2-3**（paired-test steering の blocker 解消、dogfood #254 が完走可能に）|
| B5 (a) + (b) | +3-4 |
| B1 (Multi-tool-per-turn) | +8-10（B1+B2+B5 同時解決）|

### 9.7 Procedural note: comparative dogfood の次 round について

現 dogfood レポート末尾：

> "Follow-up: the next M2 comparison should be a **true interrupted-resume trial on both sides**, or mew should reduce the paired-test steering failure where it suggested a non-existent `tests/test_cli.py` instead of finding the existing `tests/test_dogfood.py` parser coverage."

現 round で `inconclusive` になった理由の 1 つは、**fresh_cli 側が実際には中断されなかった**こと。次 round では：

1. Fresh CLI session を task 途中で明示的に interrupt（Ctrl-C）
2. 新しい codex-ultra session でその context を resume させる
3. **両サイドで interruption → resume → completion を踏む**
4. そのうえで `interruption_resume_gate` を両サイドで proved に

これは**コード変更ではなく dogfood protocol の変更**。`mew dogfood --scenario m2-comparative --force-interrupt-both` のような option を足すことも検討可能。

### 9.8 更新された B5 込みの優先順位表

§3 の表を更新：

| 優先 | # | Blocker | 対応 | 実装 LOC | M2 score 影響 |
|---|---|---|---|---|---|
| **0** (今すぐ) | **B5 (a)** | **paired-test file discovery** | **testmon-backed test_discovery.py** | **150-250** | **+2-3** |
| 1 | B1 + B2 | paired-test loop + first_tool_latency | Streaming Tool Executor + Multi-Tool-per-Turn | 800-1,500 | +8-10 |
| 2 | B3 | observer overhead | Permission Mode spectrum | 300-500 | +3-5 |
| 3 | B4 | model_resume_wait | Snapshot resume | 400-700 | +3-4 |

**新しい優先 0 (B5) の位置付け**：
- **最小コストで即座に M2 dogfood を前進させる**
- B1 の大規模構造変更を待たない
- testmon が既に mew の dep なので**追加依存ゼロ**
- 150-250 LOC = **実測 velocity で 0.5-1 時間**

### 9.9 検証済み追加 pinpoint 参照

```
references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:43
  → "Read the project's CLAUDE.md / README for build/test commands and conventions"
references/fresh-cli/claude-code/src/tools/AgentTool/prompt.ts:130
  → sample dialogue showing test discovery via grep
references/fresh-cli/claude-code/src/tools/GrepTool/GrepTool.ts  (実在確認済み)
references/fresh-cli/claude-code/src/tools/GlobTool/GlobTool.ts  (実在確認済み)
```

mew 側：
```
src/mew/work_session.py:1771-1873  _same_surface_audit_* 群
src/mew/work_session.py:2262       paired-test coverage check message
pyproject.toml:12                  pytest-testmon>=2.1（既存）
```

### 9.10 TL;DR (Addendum)

新 blocker **B5: paired-test file discovery** 発見。対応として：

1. **今すぐ**: `test_discovery.py` を testmon + grep fallback で実装（150-250 LOC、0.5-1 時間）
2. **並行**: paired-test steering の文言を model-driven に緩和
3. **構造的解決**: 優先 1 の Multi-tool-per-turn で最終的に解消

この addendum で**M2 close の最短経路が更新**された：

- **Phase 0 (B5)**: 小さく即時、30 分〜1 時間の実装で dogfood #254 が完走可能に
- **Phase 1 (B1+B2)**: 構造変更、L2 unlock の本命
- **Phase 2 (B3)**: Permission Mode、ceremony 削減
- **Phase 3 (B4)**: Snapshot、resume 高速化

**M2 score 65 → 68 (Phase 0) → 78-80 (Phase 1 後) → 82+ (Phase 2-3 後)** の推移が defensible。

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 00:00 JST, addendum appended 2026-04-20 00:30 JST
**Context**: initial commit `10d01b8` (914 commits); addendum at `74e8afe` (916 commits) after task shape dogfood result
**Related**: `docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md`, `docs/ADOPT_FROM_REFERENCES.md`, `docs/REVIEW_2026-04-19_STRUCTURAL_TIMING.md`, `docs/REVIEW_2026-04-19_REFACTOR_CADENCE.md`
**Conversation trace**: Claude Code session (single session, no memory between runs)
