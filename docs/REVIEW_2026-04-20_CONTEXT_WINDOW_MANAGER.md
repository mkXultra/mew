# REVIEW 2026-04-20 — Context Window Manager

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。**Claude-code と codex が持つ context window management subsystem が mew に欠けていることを指摘し、M6 Body 前 / M5.1 accelerator として phase 分け実装を提案**
**生成条件**: 2026-04-20 18:45 JST 以降、commit `56ed357` 時点、M1-M5 closed

**Trigger**: `REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` 書いたあと、`MISSING_PATTERNS_SURVEY.md` に**Context Window Manager が漏れていた**ことに気づいた。Claude-code は `src/services/compact/` に**10+ ファイルの dedicated subsystem**を持ち、codex は core 統合済み。mew は `compact_recent_items()` 1 関数のみ。

**関連**:
- `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md`（改善 1/2 と補完関係）
- `docs/ADOPT_FROM_REFERENCES.md` §5.15 Pre/Post Compact Hooks（本 review が拡張）
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`（漏れていた pattern）
- `ROADMAP.md` M6 Body（daemon 化）

---

## 0. 動機

### Context window は全 agent の sharp edge

大きい context を model に送ると：
- Input token 処理時間が増える
- API cost 増
- Model の reasoning quality が劣化（dilution）
- Model limit に達するとエラー

**Agent を長時間動かす = context 管理を避けて通れない**。Claude-code と codex はこの問題に**dedicated subsystem**で応える。Mew は現状、単純 truncation だけ。

### Mew の固有症状

- task #320 で 132 秒の遅延（速度 review で分析）
- session が長くなると **growth unbounded**（各 item 数上限はあるが、section 数が多い）
- M6 Body（daemon で常駐）になると**数時間〜数日の context が累積**、現設計では破綻する

---

## 1. Claude-code の Context Window Manager

### 1.1 Subsystem 構成

`src/services/compact/` に**11 ファイル**の dedicated subsystem：

| ファイル | 役割 |
|---|---|
| `compact.ts` | Main compaction orchestrator |
| `autoCompact.ts` | 閾値で自動発動 |
| `apiMicrocompact.ts` | 各 API call 直前の micro-compact |
| `microCompact.ts` | Small incremental compactions |
| `sessionMemoryCompact.ts` | Session memory 専用 |
| `postCompactCleanup.ts` | Compact 後の cleanup |
| `compactWarningHook.ts` | 事前警告 hook |
| `compactWarningState.ts` | Warning state 管理 |
| `timeBasedMCConfig.ts` | 時間 based micro-compact 設定 |
| `grouping.ts` | Message grouping for compaction |
| `prompt.ts` | Compaction 用 prompt |

さらに関連：
- `src/utils/contextAnalysis.ts` — token stats 計算
- `src/utils/context.ts` — `COMPACT_MAX_OUTPUT_TOKENS` 等の constants
- `src/utils/forkedAgent.ts` — compaction 用 cheap agent fork
- `src/utils/attachments.ts` — stub 化された attachment

### 1.2 Auto-compact（verified 抜粋）

`autoCompact.ts:40-120`:

```typescript
const autoCompactWindow = process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW
// 環境変数で override 可能

const autoCompactThreshold = getAutoCompactThreshold(model)
const threshold = isAutoCompactEnabled() ? autoCompactThreshold : ...

const warningThreshold = threshold - WARNING_THRESHOLD_BUFFER_TOKENS
const errorThreshold = threshold - ERROR_THRESHOLD_BUFFER_TOKENS

if (isAutoCompactEnabled() && tokenUsage >= autoCompactThreshold) {
  // compact を発動
}
```

**3 段階 threshold**：
1. 正常: threshold まで（通常通り）
2. Warning: `warningThreshold` 超えたら表示
3. Error: `errorThreshold` 近いと force compact

### 1.3 Multiple strategies

| Strategy | Trigger | 方法 |
|---|---|---|
| **Micro-compact** | 各 API call 直前 | 重複 stub 化、recent duplicate 除去 |
| **Auto-compact** | Token threshold | Forked agent で summary 生成 |
| **Session memory** | Session close | Memory に compress して persist |
| **Time-based** | 古い messages | 時間経過で自動要約 |

### 1.4 Forked agent で summarize

`runForkedAgent` で**cheap model が compaction を実行**：
- Main context に summary だけ返される
- 原文は破棄（or stub 化）
- Main model は summary を読んで context を continue

### 1.5 Stub markers

Compact 時に**placeholder**を挿入：
```
FILE_UNCHANGED_STUB: "このファイルは N 回前に read 済み、変更なし。"
```

Re-expand が必要になれば tool call で取得。**"可逆圧縮"**。

### 1.6 Pre/Post hooks

`executePreCompactHooks` / `executePostCompactHooks`（`utils/hooks.ts`）:
- Compact 前に artifact extract
- Compact 後に invariant check
- ADOPT §5.15 で既提案

---

## 2. Codex の Context Window Manager

### 2.1 構成

```
codex-rs/core/src/
  compact.rs              ← main compaction
  tasks/compact.rs        ← task-level compact
  thread_manager_tests.rs ← tests
  tasks/regular.rs        ← regular turn での compact 統合
  client.rs               ← API call で compact 呼ぶ
```

### 2.2 Integration スタイル

Claude-code は **services/ 独立 subsystem**。  
Codex は **core runtime と deep に統合**（タスク実行の一部）。

```rust
// task の一部として compact 発動
match task_type {
    Compact => run_compact_task(...),
    Regular => run_regular_turn(...),
    ...
}
```

Compact が**独立した task type**として 1 級市民。Agent が `/compact` スラッシュで**明示起動**もできる。

### 2.3 codex 固有の特徴

- State はすでに SQLite 永続化（compact の前提として state が durable）
- Turn 間での context 継承が明示的
- Thread manager が compaction 実行後の cleanup を管理

---

## 3. Mew の現状

### 3.1 実装

`src/mew/context.py:48`:

```python
def compact_recent_items(items, limit):
    # items を直近 N 件に truncate
    return items[-limit:]
```

### 3.2 使用箇所（11 箇所）

```
memory.py:
  shallow recent → compact_recent_items(limit)
  deep.preferences → compact_recent_items(limit)
  deep.project → compact_recent_items(limit)
  deep.decisions → compact_recent_items(limit)

context.py:
  verification_runs → compact_recent_items(limit=10)
  write_runs → compact_recent_items(limit=10)
  effects → compact_recent_items(...)
  step_runs → compact_recent_items(MAX_CONTEXT_STEP_RUNS)

他:
  desk.py, step_loop.py, thoughts.py, work_session.py
```

**全て "直近 N 件だけ残す" truncation**。Sophisticated ではない。

### 3.3 問題点

1. **Item 数で切るが、各 item の token 数は考慮せず**
   - 1 item が 100 tokens の日も、10,000 tokens の日もある
   - Total token budget に無関心
   
2. **Section 数が増えると total 爆発**
   - `verification_runs` (10) + `write_runs` (10) + `effects` (N) + `preferences` (M) + ... = 累積
   - 各 section は bounded、全体は unbounded
   
3. **Threshold 機構なし**
   - API が "context too large" エラー返すまで compact 発動しない
   - Warning もない
   
4. **Summary なし**
   - "最古の item を捨てる"だけ
   - 要約して content を保持する機能なし
   - **決定的に codex/claude-code より貧弱**
   
5. **Forked agent 不在**
   - Main model が compaction を担う → context 既に満杯の状況で余計な work
   
6. **Pre/Post hooks 未実装**
   - ADOPT §5.15 で提案したが未採用

---

## 4. 欠けている 6 機能（詳細）

### F1. Token 数 awareness

**現状**: item 数のみ  
**必要**: 各 item の token count を知る  
**実装**: tokenizer で計算 + cache

### F2. Auto-trigger at threshold

**現状**: なし（API error まで何もしない）  
**必要**: `token_usage > threshold` で自動 compact  
**実装**: 3 段階（warning / error / force）

### F3. Warning 事前通知

**現状**: なし  
**必要**: user / agent に "context が重いよ" と伝える  
**実装**: `mew status` 等に token usage 表示

### F4. Forked agent summarization

**現状**: なし  
**必要**: cheap model が summary 生成、main model に summary のみ渡す  
**実装**: Claude haiku or gpt-mini で summary、main model に insert

### F5. Multiple strategies

**現状**: truncate のみ  
**必要**: micro / session / time-based 等の複数戦略  
**実装**: strategy selector + 各 strategy の implementation

### F6. Pre/Post compact hooks

**現状**: なし  
**必要**: hook で artifact extract / invariant check（ADOPT §5.15）  
**実装**: hook-as-data（ADOPT §5.10 と共通）

---

## 5. Phase 分け実装提案

全体規模: **~800-1,200 LOC**、3-5 日実装。

### Phase 1: Token Counting Foundation（~200 LOC、半日）

**Goal**: 現在の context 消費量を**測れる**状態に。

```python
# src/mew/context_budget.py (新規)

@dataclass
class TokenStats:
    system_prompt: int
    memory_bundle: int
    recent_effects: int
    current_turn: int
    task_context: int
    total: int
    
    def fraction_of(self, budget: int) -> float:
        return self.total / budget

def count_tokens(text: str, model: str) -> int:
    # anthropic / tiktoken で count
    # 5 分 cache で同じ text 再計算しない
    ...

def analyze_context(context_dict) -> TokenStats:
    # 各 section の token を集計
    ...
```

**Dogfood**: `mew metrics` に token stats を出す。**測定できる = 改善の土台**。

### Phase 2: Warning Thresholds（~150 LOC、半日）

**Goal**: Agent / user が "重くなってる" を **知れる** 状態に。

```python
@dataclass
class ContextBudget:
    total_limit: int          # e.g., 200k for Claude
    warning_threshold: int    # 140k (70%)
    error_threshold: int      # 170k (85%)
    auto_compact_threshold: int  # 160k (80%)

def assess_context(stats, budget) -> ContextAssessment:
    if stats.total > budget.error_threshold:
        return ContextAssessment(level="error", recommend="compact_now")
    elif stats.total > budget.warning_threshold:
        return ContextAssessment(level="warning", recommend="consider_compact")
    return ContextAssessment(level="ok", recommend=None)
```

**Dogfood**: `mew focus` が warning を表示。まだ compact はしない、**見える化**のみ。

### Phase 3: Micro-Compact（~250 LOC、1 日）

**Goal**: 各 API call 直前に**軽量 cleanup**を実施。

戦略：
- 同一ファイルの repeated read → 最新だけ残して他を stub 化
- 重複 tool output → deduplicate
- 古い thought_journal → 数行要約に

```python
def micro_compact(context) -> CompactedContext:
    # 可逆性のある cleanup
    # stub 化、dedup、軽量要約
    # ~20-30% tokens 削減見込み
    ...
```

**Dogfood**: 1 つの work session で micro_compact を複数回実行し、token stats が線形増加でなく**安定**することを確認。

### Phase 4: Forked Agent Summarization（~300 LOC、1-2 日）

**Goal**: **深い圧縮** を cheap model で実行。

```python
def deep_compact(context, keep_recent_turns=5) -> CompactedContext:
    # 古い turns を cheap model (haiku / gpt-mini) で summarize
    # summary を 1 つの SystemCompactBoundaryMessage として insert
    # recent turns はそのまま保持
    ...

def spawn_summarizer_agent(context_chunk, target_tokens):
    # Small model を subprocess で呼んで summary 取得
    # API cost は main model の 1/10 程度
    ...
```

**Effect**: 50k tokens の history → 2-3k tokens の summary に圧縮。**>90% tokens 削減**。

**Dogfood**: 2-3 時間の resident 稼働で、context が auto-compact trigger を何度か通過しても runtime は安定、continuity score が落ちない。

### Phase 5: Pre/Post Compact Hooks（~100 LOC、半日）

**Goal**: ADOPT §5.15 実装。Compact 前後で extract / verify。

```python
# settings.json
{
  "hooks": [
    {"event": "pre_compact", "command": "extract_working_memory.py"},
    {"event": "post_compact", "command": "verify_continuity_score.py"}
  ]
}
```

Compact の境界で hook 発火。ADOPT §5.10 Hook System と統合。

### Phase 6: Session Memory Compact（~200 LOC、1 日）

**Goal**: Session close 時に **memory に compress して persist**。

Session 内の work session bundle を、session 終了時：
1. Key decisions だけ extract → typed_memory に昇格
2. Original work session は archive（full detail）
3. Next session 開始時は summary を active_memory で
4. 必要時に archive を retrieve（tool call）

**Effect**: Session 間の context transfer が **graceful**。M6 Body 常駐時の **数日 running** が現実的に。

---

## 6. 各 Phase の dependency

```
Phase 1 (Token counting)
  ↓
Phase 2 (Warnings) — user visibility
  ↓
Phase 3 (Micro-compact) — everyday savings
  ↓
Phase 4 (Forked summarizer) — deep compression
  ├→ Phase 5 (Hooks)
  └→ Phase 6 (Session memory)
```

Phase 1-3 は独立、Phase 4-6 は相互依存 + Phase 3 を前提。

---

## 7. Integration との関係

### 7.1 Speed Leverage review との連動

`REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md` との相補性：

| 改善 | 焦点 |
|---|---|
| Prompt Caching (改善 1) | **Static prefix を再処理させない** |
| Differential Context (改善 2) | **差分だけ send** |
| Context Window Manager (本 review) | **古い history を圧縮/summarize** |

3 つ全部で**context の"インプット side"最適化 trifecta**。

### 7.2 ADOPT §5.15 の拡張

§5.15 は Pre/Post Compact Hooks だけ → 本 review は**full manager**。

§5.15 は本 review の **Phase 5** に相当。Phase 1-4, 6 は新規追加。

### 7.3 M6 Body との関連

M6 daemon 化すると：
- 常駐 → 数日 context 累積
- Context manager なし → 破綻
- **M6 Done-when に context manager を前提条件として入れるべき**

本 review の **Phase 1-3 は M6 着手前 mandatory**、Phase 4-6 は M6 と並行。

### 7.4 M5.1 Accelerator としての位置付け

Context が重いと：
- Self-improve loop が遅い（132 秒問題）
- Rescue rate が上がる（context 多すぎて model が focus 外す）

**Context manager は M5.1 accelerator の隠れた最重要 patch**。

---

## 8. 予想効果

### Latency

Speed Leverage の数字を context manager で補強：

| Phase 組み合わせ | Latency (xhigh small task) |
|---|---|
| 現状 | 132s |
| + Speed Leverage Phase 1 (Reasoning auto) | 50-70s |
| + Speed Leverage Phase 2 (Prompt caching) | 15-25s |
| + Speed Leverage Phase 3 (Differential) | 5-10s |
| + **Context Manager Phase 3 (Micro-compact)** | **3-7s** |
| + Context Manager Phase 4 (Forked summarizer) | 2-5s |

Speed Leverage と併用で **40-60× 改善**が可能。

### Long-running stability

- 現状: 2-3 時間 running で "context too large" error 可能性
- Phase 3 後: 1 日安定 running 可能
- Phase 4 後: 1 週間 running 可能
- Phase 6 後: 1 ヶ月以上の "identity 継続" 可能

**M6 Body + 本 review Phase 4-6 = 住人 mew の前提**。

### Cost

Prompt caching (Speed Leverage 1) と合わせて：
- 現状 token usage: 高い
- Phase 3 (micro): -20-30%
- Phase 4 (forked summary): -50-70%
- **合計: -60-80% cost** の見込み

---

## 9. Risks / Caveats

### A. Compaction による情報欠損

Summary で詳細が落ちる。後で "そのコード具体的にどうだっけ" 質問できない。

**対策**:
- Compacted 部分は archive に残す（可逆）
- 必要時 retrieve tool で full content 取得
- Stub markers で "N 件前の X に関する詳細は archive#Y" とポインタ

### B. Forked agent の cost + latency

Summary 生成に cheap model でも 1-3 秒かかる。Compact 発動が頻繁だと遅延増。

**対策**:
- Auto-compact は threshold 超えた時のみ（頻繁ではない）
- Micro-compact は tokenization + rule-based（model 呼ばない）
- Deep compact は session boundary / time-based でスケジューリング

### C. Summary quality の悪化

Cheap model の summary が雑だと next session の context が薄い。

**対策**:
- Summary の quality metric を計測（tokens before/after ratio、keyword 保存率）
- Rescue rate 上がったら summarizer 調整
- 重要項目（decisions, risks）は summary から抜かない rule

### D. Hook の failure

Pre-compact hook が落ちたら compact できない。

**対策**:
- Hook failure は warning、compact は実行
- Hook は optional（missing でも OK）
- Error は journal 記録

### E. Mew の既存 truncation との conflict

`compact_recent_items` が既に使われている。新 manager との整合。

**対策**:
- Phase 1-3 は互換（並存）
- Phase 4 以降で既存 truncation を徐々に置換
- Migration path を明示

### F. Tokenizer dependency

Token count に `tiktoken` / `anthropic` tokenizer 必要。Mew の zero-dep 哲学と矛盾?

**対策**:
- dev extras として install（zero-dep core は維持）
- Fallback: 文字数 × 0.25 の近似（粗いが dep 不要）
- Production では正確 tokenizer、dev では近似でも OK

---

## 10. 私が間違っている可能性

1. **Phase 分けの粒度**: 6 phase は細分化しすぎかも。3-4 phase にまとめても意味通る
2. **Token thresholds の値**: 私が書いた 140k/170k/160k は推測。モデル固有、dogfood で調整
3. **Forked agent の cost 見積もり**: cheap model でも累積コストあり。実測必要
4. **既存 `compact_recent_items` の migration**: 互換性の難しさは実装まで見えない
5. **Summary quality**: Quality evaluation 自体が研究課題。simple metric では不十分かも
6. **M6 との順序**: 本 review の Phase 1-3 を M6 前、Phase 4-6 を並行 と提案したが、全 phase を M6 並行にする案もあり

実装 agent が現場判断で優先。本 review は方向のみ。

---

## 11. TL;DR

```
Mew は context window manager が弱い（truncate-to-N のみ）
Claude-code は services/compact/ に 11 ファイルの subsystem
Codex は core に deep 統合

欠けている 6 機能:
  F1 Token counting
  F2 Auto-trigger threshold
  F3 Warning notification
  F4 Forked agent summarization
  F5 Multiple strategies
  F6 Pre/Post hooks (= ADOPT §5.15)

Phase 分け実装 (800-1,200 LOC, 3-5 日):
  Phase 1 Token counting         (200 LOC, 半日)  ← M6 前必須
  Phase 2 Warnings               (150 LOC, 半日)  ← M6 前必須
  Phase 3 Micro-compact          (250 LOC, 1 日)  ← M6 前推奨
  Phase 4 Forked summarizer      (300 LOC, 1-2 日) ← M6 並行
  Phase 5 Hooks (§5.15)          (100 LOC, 半日)  ← M6 並行
  Phase 6 Session memory         (200 LOC, 1 日)  ← M6 後

効果:
  - Latency: Speed Leverage と併用で 40-60× 改善
  - Long-running: 2-3h → 1 週間安定
  - Cost: -60-80%

Integration:
  - Speed Leverage と相補 (caching / diff / compact の trifecta)
  - ADOPT §5.15 の拡張
  - M6 Body の前提条件
  - M5.1 Accelerator としての隠れた最重要 patch
```

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 18:45 JST
**Context**: commit `56ed357`, 1116 commits observed, M1-M5 closed
**Trigger**: MISSING_PATTERNS_SURVEY から context window manager が漏れていた発見
**Related**: `docs/REVIEW_2026-04-20_MEW_SPEED_LEVERAGE.md`, `docs/ADOPT_FROM_REFERENCES.md` §5.15, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
**Conversation trace**: Claude Code session (single session, no memory between runs)
