# REVIEW 2026-04-20 — Mew Speed Leverage: Using Persistence to Beat Codex

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。**Mew self-hosting の速度問題を、mew が元から持つ persistence 優位で逆転する提案**
**生成条件**: 2026-04-20 18:30 JST 以降、commit `56ed357` 時点、M1-M5 closed、M6-M10 defined

**Trigger**: task #320 の mew 自己実装 dogfood で、xhigh 時 first THINK が 132 秒、high 時 3+ 分で中断（user 報告）。codex が mew を動かす時は 5-10 秒で first output を返せる。**mew が自分より遅い**という倒錯。

**関連**:
- `docs/ADOPT_FROM_REFERENCES.md` §5.1 Streaming Tool Executor（本 review と強く連動）
- `docs/REVIEW_2026-04-20_M5_ACCELERATORS.md`
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`

---

## 0. パラドックスの正体

### 観測

```
Codex (mew を動かす agent):
  context ≈ 2-5k tokens (coding task-focused)
  first tool output: 5-10 秒
  記憶: なし（毎回 fresh）

Mew (自己実装する agent):
  context ≈ 20-50k tokens (全 state 注入)
  first output: 30-130+ 秒
  記憶: durable、typed memory、snapshot、continuity
```

**記憶を持つ mew の方が遅い**。原理的には逆転しているべき。

### 直接原因

Mew は永続記憶を持ちながら、**それを "prompt 全部入れ"の方式で使っている**：

| Mew prompt に注入される内容（毎回） | 概算 token |
|---|---|
| Decision types 全列挙（boilerplate） | 2-4k |
| ROADMAP_STATUS 抜粋 | 3-5k |
| Typed memory（active_memory bundle） | 2-4k |
| Resume bundle | 3-5k |
| Session knowledge digest | 2-3k |
| World state (git status, file mtimes) | 1-2k |
| Task context + notes | 1-2k |
| Recent tool outputs | 3-5k |
| Recent model turns | 2-4k |
| **合計** | **20-34k tokens** |

Codex はこの全部を持たず、grep で必要分だけ読む → 2-5k tokens。

### パラドックスの教訓

**記憶を持つことと、それを使いこなすことは別**。  
Mew は記憶はあるが、**prompt 注入 layer が codex より素朴**。結果として記憶の利点を活かせていない。

---

## 1. Mew が持ち Codex が持たない 6 種の Leverage

### L1. **Durable State**
Mew は effects.jsonl、state.json、snapshot、typed memory を persistent に持つ。  
Codex はこれらを毎回ゼロから組み立てる。  
**→ Prompt caching で "不変部分を再処理しない"** が可能。

### L2. **常時起動（M6 Body 後）**
Mew は daemon として常駐できる（予定）。  
Codex は呼ばれて起動、終わったら消える。  
**→ 背景で index 維持、pre-warm** が可能。

### L3. **Typed Memory**
Project fact、user preference が structured に保存。  
Codex は毎回 README / source を grep。  
**→ "結論そのもの" を保存して即回答** が可能。

### L4. **Continuity Score**
前回状態との差分を認識できる。  
Codex は差分の概念なし。  
**→ "前回から変わった分" だけ prompt に** が可能。

### L5. **Project Snapshot**
ファイル構造、touched files、open risks が既に分かっている。  
Codex は grep / glob で毎回探索。  
**→ Pre-computed code index でゼロ grep** が可能。

### L6. **Event History**
過去の tool call、decision、effects が残る。  
Codex は履歴ゼロ。  
**→ 過去の観察を再利用**、重複探索回避。

これら 6 leverage を**使い切れば、mew は codex の 5-10 倍速い**はず。現状は**記憶を prompt に丸投げ** のせいで逆転している。

---

## 2. 7 つの具体改善案

### 改善 1: Anthropic Prompt Caching 🥇

#### 出典
Anthropic API が `cache_control: {"type": "ephemeral"}` marker で prompt prefix を cache 化できる：
- Cache hit: **input token 処理が 10-15 倍高速**
- Cost: **90% 割引**
- TTL: 5 分（hit があれば延長）

#### Mew 適用
現 prompt builder を 2 段構成に：

```
[STATIC PREFIX] ← cache_control
  - Decision types 列挙
  - 全 skill 定義
  - User preferences (changing infrequently)
  - Safety boundaries
  - ROADMAP_STATUS の安定 header 部

[VARIABLE SUFFIX] ← 毎回変わる
  - Current task context
  - Recent effects（直近 5-10 件）
  - Current working memory
  - Last tool outputs
```

実装ポイント：
- `src/mew/anthropic_api.py` で cache_control 付与
- `src/mew/agent.py` の prompt builder を prefix/suffix 分離
- Cache 効いているか metric 追加（`cache_read_input_tokens` vs `cache_creation_input_tokens`）

#### 効果
- 1 回目: 普通（cache 作成）
- 2 回目以降: **132 秒 → 15-30 秒**
- Cost: **90% 減**

#### 実装規模
**100-200 LOC**。`anthropic_api.py`: ~50 LOC、prompt builder: ~100 LOC、metric: ~30 LOC。

#### 優先
**★★★★★ 最優先**。Implementation 単純、効果極大。

---

### 改善 2: Differential Context 🥈

#### 発想
Mew は自身の過去 state を知っている。**"今回の prompt に全 state を書く"** ではなく **"前回 prompt 以降何が変わったか"** を書く。

#### 現在 vs 改善後

**現在の prompt**:
```
ROADMAP_STATUS: [全 evidence list]
Recent effects: [全 20 件]
Active memory: [全 bundle]
Working memory: [全フィールド]
...
```

**改善後**:
```
[CACHED prefix: last-turn snapshot]

Since last THINK (turn 5):
  - 3 commits landed
  - tool calls executed: read_file tests/test_X.py, search_text "foo"
  - new observations: add_numbers is in src/mew/add.py
  - working_memory.next_step updated
  
Your task continues as:
  [current task]
  [current working_memory]
```

Codex は毎回全探索。Mew は**永続記憶で差分が取れる**のに、それを使っていない。

#### 実装構造
```python
# src/mew/prompt_differential.py (新規、~300-400 LOC)

@dataclass
class TurnDiff:
    previous_turn_id: str
    commits_landed: list[str]
    tool_calls_executed: list[ToolCall]
    memory_changes: list[MemoryChange]
    state_deltas: dict
    newly_relevant: list[str]

def compute_diff(current_turn_ctx, previous_snapshot) -> TurnDiff:
    ...

def render_differential_prompt(diff) -> str:
    # Concise, bullet-form
    # Only "what changed" since previous
    ...
```

#### 効果
Variable part が **5-10 倍小さい**。Model の reasoning も速い。  
**15-30 秒 → 5-10 秒** の見込み（改善 1 の上に乗せる）。

#### 実装規模
**300-500 LOC**

#### 優先
**★★★★** 改善 1 の直後。

---

### 改善 3: Memory as Conclusions, not Observations

#### 現 typed memory の弱点

```json
{
  "name": "pytest convention",
  "body": "This project uses pytest, tests live in tests/"
}
```

これは **"私が見たもの"** を記録したもの。Resident model はこれを読んで、**さらに** "じゃあテスト実行コマンドは何か" を推論する必要がある。

#### 改善後

```json
{
  "name": "pytest convention",
  "body": "...",
  "conclusions": {
    "test_command": "uv run pytest -q",
    "test_filter_by_module": "uv run pytest -q tests/test_<module>.py",
    "verification_command": "uv run pytest --testmon",
    "test_file_pattern": "tests/test_<module>.py"
  }
}
```

**Codex は "テスト実行方法は？" を毎回 grep で探す**。Mew は**答えを直接返す**。

#### Self-populate の mechanism

M5 self-improvement loop が**自分の結論を memory に書き戻す**：

```python
# 実行後に
def promote_conclusion(memory_id, key, value, evidence):
    # 結論として採用可能か audit
    # 採用なら memory.conclusions に append
    ...
```

一度確立した結論は**後続の loop が再発見しなくていい**。

#### 実装規模
**400-600 LOC**

#### 優先
**★★★** 累積効果大。

---

### 改善 4: Pre-computed Code Index

#### 背景 index 維持

常時起動（M6 Body）が実現したら、daemon が背景で維持：

```json
// .mew/code_index.json (自動更新)
{
  "src/mew/commands.py": {
    "functions": ["cmd_focus", "cmd_work", "cmd_chat", ...],
    "imports": ["state", "tasks", "read_tools"],
    "exports": [...],
    "last_indexed": "2026-04-20T18:00:00Z",
    "git_hash": "abc123"
  },
  "src/mew/work_session.py": {
    ...
  }
}
```

File watcher（M6/M7）で**変更があったファイルだけ re-index**。

#### 効果

Resident model が "どこに何があるか" を **grep せず即答**可能：

Before:
```
Resident: "add_numbers はどこ？"
  → search_text "def add_numbers" (tool call, 2-5 秒)
  → read_file で該当箇所確認 (tool call, 1-3 秒)
  → 計 5-10 秒
```

After:
```
Resident: "add_numbers はどこ？"
  → mew context に既に "code_index: add_numbers in src/mew/add.py:42"
  → 即回答、tool call 不要
```

**tool call 数が半分以下**になる。

#### 実装規模
**500-800 LOC**（Python AST parser + watcher 統合 + incremental update）

#### 優先
**★★★** M6 daemon 稼働前提。

---

### 改善 5: Lazy Memory Loading（Pointer-Based Prompt）

#### 現在

```
Prompt = [全 active_memory block 注入]
```

#### 改善後

```
Prompt = [memory ID + description のみ]
  Available memories:
    M1 "pytest convention" (project, score 0.9)
    M2 "concise output preference" (feedback, score 0.7)
    M3 "resume-first workflow" (project, score 0.6)
  
  Use recall_memory(id=N) if detail needed.

Resident がの判断で必要な M# だけ expand：
  recall_memory(id=1) → [full content of M1]
```

#### 効果

- Initial prompt が**小さい**（memory IDs のみ）
- Model が **relevant な memory だけ展開**
- Unused memory の tokens 消費ゼロ

トレードオフ: recall_memory tool call 1-2 回増えるが、total tokens は**30-50% 減**。

#### 実装規模
**200-400 LOC**

#### 優先
**★★★** 改善 1 + 2 と相補的。

---

### 改善 6: Reasoning Effort 自動調整 🥉

#### 最も quick win

Task kind で reasoning effort を切り替え：

```python
REASONING_POLICY = {
    ("implementation", "small"): "medium",   # xhigh は過剰
    ("implementation", "medium"): "high",
    ("implementation", "large"): "high",
    ("planning", "any"): "high",
    ("triage", "any"): "low",
    ("exploration", "any"): "low",
    ("verification", "any"): "medium",
}

def choose_reasoning(task_kind, complexity):
    return REASONING_POLICY.get((task_kind, complexity), "medium")
```

#### 効果

xhigh で 132 秒 → medium で **20-40 秒** の見込み（reasoning time 自体が減る）。

Small implementation task に xhigh は overkill。

#### 実装規模
**50-100 LOC**（policy table + selector）

#### 優先
**★★★★★** 即効、低リスク。

---

### 改善 7: Daemon Pre-warming（M6 後）

#### M6 Body で解禁

常時起動で背景に：
- API session の warm-up（empty ping で cold start 除去）
- 頻用 prompt の **pre-computed** cache
- Code index の背景 update
- Incremental state snapshot

#### 効果

All operations が **warm から始まる**：
- First API call latency: 2-5 秒 → **< 1 秒**
- 改善 1-6 の accumulated effect の上に**更に加速**

#### 実装規模
M6 本体 + **400-600 LOC**

#### 優先
**★★★** M6 完了後のみ有効、長期投資。

---

## 3. 組み合わせ効果の見積

現状 latency 132 秒から、各改善の累積：

| Phase | 改善内容 | Latency 予測 | 累積倍率 |
|---|---|---|---|
| 現状 | なし | **132s** (xhigh) | 1× |
| +6 | Reasoning auto | 50-70s | ~2× |
| +1 | Prompt caching | 15-25s | ~6× |
| +2 | Differential context | 5-10s | ~20× |
| +3 + 5 | Memory conclusions + lazy | 3-6s | ~30× |
| +4 (M6) | Code index | 2-4s | ~50× |
| +7 (M6) | Daemon pre-warm | 1-2s | **~100×** |

**ゴール: mew を codex より速くする（5-10 秒 → 1-5 秒）**。

---

## 4. 思想的転換：**"記憶を prompt に注入"から"記憶を index 化"へ**

### 現状の mew mental model

```
Mew = "すべてを暗記して毎回口頭で言う受験生"
  prompt → 全暗記 → 口頭発表
  ↓
  発表前の暗記時間（THINK）が長い
```

### あるべき mental model

```
Mew = "索引付きノートを開いて答える実務家"
  prompt → 索引で必要箇所 locate → 即答
  ↓
  THINK time 劇的に短い
```

### Codex との対比

```
Codex:
  毎回ノートを一から作る（grep / glob / read）
  作るのに時間がかかるが、必要な部分だけで済む
  
Mew 現状:
  ノートを作る作業は終わっている
  でも読み方が「全部音読」
  
Mew 理想:
  ノートを作る作業は終わっている
  読み方は「索引を引いて関連部分だけ」
  結果: Codex より早い
```

---

## 5. 実装順序の推奨

### 🔥 今週（quick wins、2 日で数十倍速）

```
Day 1 (3-5 時間):
  改善 6 Reasoning auto-adjust    (50-100 LOC)
  改善 1 Prompt Caching           (100-200 LOC)
  Dogfood で 132s → 20-30s 確認

Day 2 (4-6 時間):
  改善 2 Differential Context     (300-500 LOC)
  Dogfood で 20-30s → 5-10s 確認
```

**約 1 日の実装で 132s → 5-10s（約 20×）**。

### 📅 次週（深い改善、3-5 日）

```
Day 3-4:
  改善 3 Memory as conclusions (400-600 LOC)
  改善 5 Lazy memory loading (200-400 LOC)
  Dogfood で 5-10s → 3-5s

Day 5:
  Metric instrumentation (cache hit rate 等)
  Regression test
```

### 🏗️ M6 完了後（structural 改善）

```
改善 4 Code index (500-800 LOC)
改善 7 Daemon pre-warm (400-600 LOC)
```

**最終状態: 1-2s first output**。Codex を超える。

---

## 6. Risks / Caveats

### A. Prompt cache の設計ミス

Cache prefix に**頻繁に変わるもの**を入れると cache miss。

**対策**: 明確に "static" と "variable" を分離。用語・構造レベルで強制（`PromptPrefix` と `PromptSuffix` を別型）。

### B. Differential Context の "差分見失い"

前回 turn を正しく再構築できないと差分が計算できない → full fallback。

**対策**: 
- Turn ID で anchor
- Fallback 時は explicit に "full context (diff unavailable)" と記録
- Cache で recent full snapshots を保持

### C. Memory conclusions の rot

結論が古くなり不正確に。

**対策**:
- 各 conclusion に `derived_at`、`evidence_refs` を付ける
- M5 self-improvement の一部として**古い conclusion を refresh**
- 整合性破れたら drop

### D. Reasoning effort too low で quality 落ちる

Medium で実装が雑に。

**対策**:
- Dogfood で rescue rate 監視
- rescue 増 → auto policy を re-calibrate

### E. Code index の staleness

File watch 遅延で index が stale。

**対策**:
- Git hash を index entry に付ける
- Read time に hash 照合、stale なら re-index
- File watcher + explicit refresh command

---

## 7. 私が間違っている可能性

1. **Prompt cache の効果 10-15×**: Anthropic の実測値。mew 固有状況で differ 可能性
2. **Differential context の LOC**: 300-500 は optimistic。初回は 500-700 かも
3. **Memory conclusion の self-populate**: M5 内で自動 populate が安全か要検討。誤結論の promotion risk
4. **Code index の精度**: Python AST で大半は取れるが、動的生成 / metaclass 等で欠落あり
5. **Daemon pre-warm の効果測定**: 実効 latency 改善が見込み通りかは実装後検証
6. **改善 3, 4, 5 の相互作用**: 同時に landing すると互いに優先順位で悩む可能性

実装 agent が現場判断で優先。本 review は方向のみ。

---

## 8. 既存 REVIEW との関係

| 既存 doc | 本 review との関係 |
|---|---|
| `ADOPT_FROM_REFERENCES.md` §5.1 Streaming Tool Executor | 改善 1 + 2 は streaming executor の**代替**ではなく**補完**。Streaming は "first tool 早く"、本 review は "first THINK 早く"。両方必要 |
| `REVIEW_2026-04-20_M5_ACCELERATORS.md` | M5 loop の rescue 減らす（#1-5）と並んで、M5 loop の**実行速度を 20× にする**補完 |
| `REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` | 改善 5 は Lazy loading パターン。他 patterns とは別軸 |
| `REVIEW_2026-04-20_M6_REFRAMING.md` (M9 Legibility) | 改善 6 の reasoning auto は M9 の "legible output" と連動（user が何を見ているか選択的） |

---

## 9. TL;DR

```
Problem: mew 自己実装が 132 秒 (xhigh)、codex が mew を動かすと 5-10 秒
         → 記憶を持つ mew の方が遅いという倒錯

Root cause: mew は永続記憶を "prompt 全量注入" で使っている
            Codex は記憶なしで "grep で必要分だけ" 探す

Mew の leverage (6 種):
  L1 Durable state        → Prompt caching
  L2 常時起動 (M6)         → Background pre-warm
  L3 Typed memory         → Memory as conclusions
  L4 Continuity           → Differential context
  L5 Project snapshot     → Pre-computed code index
  L6 Event history        → Turn diff

7 improvements (impact 順):
  1. Anthropic Prompt Caching    (100-200 LOC, 今夜)
  2. Differential Context        (300-500 LOC, 明日)
  3. Memory as Conclusions       (400-600 LOC, 来週)
  4. Pre-computed Code Index     (500-800 LOC, M6 後)
  5. Lazy Memory Loading         (200-400 LOC, 来週)
  6. Reasoning Auto-adjust       (50-100 LOC, 即効)
  7. Daemon Pre-warm             (400-600 LOC, M6 後)

Latency roadmap:
  現状: 132s
  今週末: 5-10s (20× 改善)
  来週末: 3-5s (30× 改善)
  M6 後: 1-2s (100× 改善, codex より速い)

思想的転換:
  "memory を prompt に注入"→"memory を index 化"
```

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 18:30 JST
**Context**: commit `56ed357`, 1116 commits observed, M1-M5 closed, task #320 self-hosting dogfood が 132s で blocked
**Trigger**: user 報告 — "mew の方が実装記憶あるから原理的に早くなるはず、常時起動だし"
**Related**: `docs/ADOPT_FROM_REFERENCES.md` §5.1, `docs/REVIEW_2026-04-20_M5_ACCELERATORS.md`, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
**Conversation trace**: Claude Code session (single session, no memory between runs)
