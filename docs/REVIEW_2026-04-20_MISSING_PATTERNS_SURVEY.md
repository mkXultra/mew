# REVIEW 2026-04-20 — Missing Patterns Survey (Post M1-M5)

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。**既存 ADOPT / M5 Accelerators / M6 Reframing 等 REVIEW の補完として、まだ扱っていない pattern を additive に追加提案**。統合方法は実装 agent の判断に委ねる
**生成条件**: 2026-04-20 18:00 JST 以降、commit `56ed357` 時点、M1-M5 closed、M6-M10 defined、1116 commits

**関連**:
- `docs/ADOPT_FROM_REFERENCES.md`（§5.1-5.18 既存 pattern 集）
- `docs/REVIEW_2026-04-20_M5_ACCELERATORS.md`（#1-5 + Explorer #6 想定）
- `docs/REVIEW_2026-04-20_M6_REFRAMING.md`（Human-Legible IF を M9 に）
- `docs/REVIEW_2026-04-20_M6_PROPOSAL.md`（Cross-Project を M8 に）
- `ROADMAP.md` M6-M10（`56ed357` で再構成済み）

---

## 0. 動機

M1-M5 完了。ROADMAP が M6-M10（Body / Senses / Identity / Legibility / Multi-Agent）に rebase された今、**claude-code と codex に存在し mew にまだ無い pattern** を体系的に整理する。

既存 REVIEW で扱った 22 pattern（ADOPT §5.1-5.18 + M5 Accelerator #1-5 + Explorer）**に加えて**、本 review では**新規 9 pattern** を扱う。

**対象外**（user 判断で除外）:
- Codex の Sandbox mode（seatbelt / landlock）: OS 依存、mew の軽さと相性悪い

**整理方針**: 各 pattern を M6-M10 のどこに紐づくか明示し、実装 agent が milestone-gate rule に沿って判断できるようにする。

---

## 1. Pattern Catalog

### Pattern A: Explorer（both references）

#### 出典
- claude-code: `src/tools/AgentTool/built-in/exploreAgent.ts`（verified: "You are a file search specialist... READ-ONLY exploration task..."）
- codex: `src/agent/role.rs:365-373` + `src/agent/builtins/explorer.toml`（verified）

#### Why
Implementation 前の codebase 探索が**両 reference に standard pattern**として存在。mew だけ missing。M5 rescue の 30-40% は「見ずに書いた」系で、Explorer で改善可能。

#### mew 適用
3 段階：
1. `.codex/skills/mew-explorer/SKILL.md`（軽量、1 時間、50-100 LOC）
2. Sub-agent spawning で parallel explorers（codex 流、500-800 LOC）
3. Explorer result の trust ledger cache（1,000-1,500 LOC）

#### 紐づく milestone
- **M5.1**（accelerator）: 軽量版でも rescue 減
- **M10 Multi-Agent**: parallel explorers として本格展開

#### Pinpoint references
```
claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:13+
codex/codex-rs/core/src/agent/role.rs:365-373
codex/codex-rs/core/src/agent/builtins/explorer.toml
```

---

### Pattern B: AskUserQuestion Tool（claude-code）

#### 出典
- claude-code: `src/tools/AskUserQuestionTool/AskUserQuestionTool.ts`（directory 存在確認済み）

#### What
Model が **構造化された multi-choice 質問** を user に投げる tool。Free-form chat ではなく、決まった選択肢から選ばせる。

```json
{
  "question": "Paired test approach?",
  "options": [
    {"id": "a", "label": "Write test first, then source"},
    {"id": "b", "label": "Write source first, defer test verification"},
    {"id": "c", "label": "Skip test for this change"}
  ]
}
```

#### Why
mew の approval flow は現在 yes/no + free text。**構造化選択肢**にすれば：
- Decision が deterministic（cache しやすい）
- User cognitive load 減（選ぶだけ）
- M5 self-improve loop で "approval, rejection, redirection" の redirection を形式化
- 将来的に Guardian cache の pattern key にできる

#### mew 適用
```python
# src/mew/ask_user.py (新規、~150-250 LOC)

@dataclass
class StructuredChoice:
    question: str
    options: list[ChoiceOption]
    context: dict  # task id, session id, etc.

def ask_user_structured(choice) -> ChoiceResponse:
    # 1. stdout に formatted prompt
    # 2. user が id で answer
    # 3. choice_ledger.jsonl に記録
    # 4. 同じ context で similar question は cache 参照
    ...
```

#### 紐づく milestone
- **M9 Legibility**: structured human interaction は legibility の核
- **M5.1 (accelerator)**: approval を structured にして cache 可能化

---

### Pattern C: CLAUDE.md / AGENTS.md 慣習（both）

#### 出典
- claude-code: `src/memdir/memoryTypes.ts`（CLAUDE.md frontmatter 処理あり、verified）
- codex: `AGENTS.md` convention（codex-rs の test fixtures に頻出）

#### What
プロジェクトルートに **agent が自動的に最初に読む** ドキュメント：
- Build/test command
- Convention
- Project-specific quirks
- Permission defaults

Agent は session 開始時 or task 開始時に CLAUDE.md / AGENTS.md を自動 prepend する。

#### Why
**Implicit knowledge を explicit 化**。新 session / 新 agent が即 onboard できる。mew の ROADMAP.md は一部これを果たしているが、**agent の自動読み込み慣習ではない**。

#### mew 適用
新規 file：
```
/project/MEW_AGENTS.md   # このプロジェクトで mew を使う時のガイド

## Build / test
uv run pytest
uv run ruff check

## Conventions
- Paired tests: tests/test_<module>.py
- Memory scope: feedback → private, project fact → project

## Safety
- No autonomous push
- ROADMAP.md は human 承認必須
```

mew の resident model は、session 開始時に MEW_AGENTS.md を自動読み込んで active_memory に注入。

実装 ~100-200 LOC。

#### 紐づく milestone
- **M9 Legibility**: 非 mew user onboarding に直撃
- **M8 Identity**: project-scoped fact の第一級 surface

---

### Pattern D: Todo 管理 tool（claude-code）

#### 出典
- claude-code: `src/tools/TodoWriteTool/TodoWriteTool.ts`（verified）

#### What
**Model が自身の ephemeral な TODO リスト**を管理：
```
[x] Read tests/test_add_numbers.py
[-] Understand add_numbers function signature
[ ] Write failing test for negative input
[ ] Update implementation
[ ] Run verification
```

session 内の一時的な作業分解で、mew の task とは別層。**現在進行中の "今やってる事"** を可視化。

#### Why
mew の `tasks` は persistent で formal。しかし**短期的な作業分解**（今の session で do すべき 5-10 items）を表現する layer がない。Todo ephemeral list があれば：
- Agent の思考を**ステップ化**できる
- **途中で止めても TODO で resume**
- M5 audit に current progress visible
- Human reviewer が "今どこ" をすぐ把握

#### mew 適用
```python
# src/mew/todo.py (新規、~200-300 LOC)

@dataclass
class Todo:
    id: int
    title: str
    status: Literal["pending", "in_progress", "done", "blocked"]
    session_id: str  # ephemeral to session

def todo_write(todos) -> None:
    # .mew/session_todos/<session_id>.json
    # session close で自動 archive
    ...

def todo_list(session_id) -> list[Todo]: ...
```

#### 紐づく milestone
- **M5.1 Self-Improve loop の可視化**: audit bundle に todo state 含める
- **M9 Legibility**: "今何してる" の most legible surface

---

### Pattern E: MCP Integration（both）

#### 出典
- claude-code: `src/services/mcp/`（directory 全体、verified earlier）
- codex: `codex-rs/codex-mcp/`（directory、前 exploration で verified）

#### What
MCP (Model Context Protocol) server を subprocess として起動し、その tool set を mew's native tool と同列に扱う。外部 ecosystem への bridge。

#### Why
**mew を閉鎖系から ecosystem 接続系に変える**：
- 他 tool の知見を import（Slack、Notion、Google Drive 等）
- M7 Senses の外部 signal が来る経路
- Plugin ecosystem の入口

#### mew 適用
```python
# src/mew/mcp_bridge.py (新規、~500-800 LOC)

@dataclass
class MCPServer:
    name: str
    command: list[str]
    tool_prefix: str

def start_mcp_server(config) -> MCPProcess:
    # stdio-based JSON-RPC subprocess
    # fetch tool manifest at startup
    # wrap each tool in mew-native interface
    ...

def route_tool_call(name, args):
    if name.startswith("mcp:"):
        return mcp_dispatch(name, args)
    else:
        return native_dispatch(name, args)
```

#### 紐づく milestone
- **M7 Senses**: 外部 signal の正式 ingress
- **M10 Multi-Agent**: 他 model family が MCP 経由で相互接続

---

### Pattern F: StatusLine（claude-code）

#### 出典
- claude-code: `src/tools/AgentTool/built-in/statuslineSetup.ts`（verified）

#### What
Shell の status line に **mew の現在状態を動的表示**：
```
[mew·task#1·9/9·3mem·recover]$ 
```

常にユーザーの視野にある **ambient awareness**。

#### Why
現在 mew の状態を見るには `mew focus` を打つ必要。StatusLine あれば**打たずに見える**：
- 今の task
- continuity score
- active memory 数
- recovery pending 等

**Inhabitability の体感**を劇的に変える。"mew が居る" を常に感じる。

#### mew 適用
```bash
# user の .bashrc / .zshrc
export PS1='$(mew status --line) $ '

# mew status --line が毎プロンプトで呼ばれる
# .mew/status.cache で 5 秒 cache、subprocess cost 抑制
```

実装 ~200-300 LOC。

#### 紐づく milestone
- **M9 Legibility**: 最も legible な ambient surface
- **M6 Body**: daemon 稼働中の visible presence

---

### Pattern G: SleepTool（claude-code）

#### 出典
- claude-code: `src/tools/SleepTool/`（directory 存在確認）

#### What
Model が明示的に **"X 秒 sleep してください"** と言える tool。待機的な work（e.g., CI build 完了待ち、rate limit 回避）で使う。

#### Why
mew には passive tick（周期処理）あるが、**model が意図して一時停止**する手段がない：
- 外部 CI 待ち
- Rate limit 対応
- Poll 間隔の明示

#### mew 適用
```python
# src/mew/tools/sleep_tool.py (新規、~50 LOC)

def sleep_tool(duration_seconds, reason):
    # runtime の次 cycle に awake を schedule
    # effect journal に sleep event 記録
    ...
```

軽量追加。

#### 紐づく milestone
- **M7 Senses**: 外部 signal 待ちの自然な表現
- **M6 Body**: daemon の polling pattern と統合

---

### Pattern H: ScheduleCronTool（claude-code）

#### 出典
- claude-code: `src/tools/ScheduleCronTool/`（directory 存在確認）

#### What
Model が **cron-scheduled task を自分で登録**：
- "1 時間後に test を再実行"
- "毎日 9:00 に morning paper 更新"
- "3 日後に review task を作成"

**未来の自己にメッセージを送る**。

#### Why
mew の passive tick は polling 的。Cron scheduling は：
- 決まった時刻の action が可能に
- Long-term plan を実装機構に落とせる
- **time-aware AI resident**の前提

#### mew 適用
```python
# src/mew/cron.py (新規、~200-300 LOC)

@dataclass
class CronEntry:
    id: str
    expression: str  # cron format
    action: Action
    created_by: str  # session id
    next_fire_at: datetime

def schedule_cron(entry) -> str: ...
def list_crons() -> list[CronEntry]: ...
def fire_due_crons(now) -> list[CronFired]: ...
```

runtime tick と統合。

#### 紐づく milestone
- **M7 Senses**: 時間 signal
- **M6 Body**: daemon-required feature（schedule を実行する process が要る）

---

### Pattern I: Worker + Awaiter roles（codex）

#### 出典
- codex: `src/agent/builtins/worker.toml`、`builtins/awaiter.toml`（verified）

Awaiter 定義（verified 抜粋）：
```
"You are an awaiter. Your role is to await the completion of a
 specific command or task and report its status only when it is
 finished.
 
 Behavior rules:
 1. When given a command/task identifier, execute or await it
 2. Do not modify the task
 3. Use repeated tool calls if necessary
 4. Use long timeouts; increase exponentially
 5. Return current status on request, resume awaiting
 6. Terminate only on completion / failure / explicit stop"
```

Worker は codex の main implementer role（explorer と対）。

#### What
Codex は**role-based agent taxonomy**を持つ：
- **worker**: implement
- **explorer**: read-only 調査
- **awaiter**: 非同期待機

それぞれ専用 prompt / config / tool set。

#### Why
mew の resident model は**role なし**の単一 model。同じ model が task picker / implementer / verifier を全部やる。これは：
- Context pollution（implementer の bias が verifier に染みる）
- Model tuning 不能（全部同じ model）
- Parallel delegation 不能

Role-based なら：
- Explorer は read-only model（安い model でも OK）
- Worker は implementer（高 reasoning）
- Awaiter は長時間 polling（軽量 model）

Context isolation + cost optimization。

#### mew 適用
```
.codex/skills/
  mew-explorer/SKILL.md    # 既提案
  mew-worker/SKILL.md      # 実装特化
  mew-awaiter/SKILL.md     # 非同期待機
  mew-verifier/SKILL.md    # 破壊的検証（M5 Acc #1）
```

各 skill が**独立 session / 独立 context**で走る想定。

#### 紐づく milestone
- **M10 Multi-Agent**: まさにこれが multi-role の第一歩
- **M5.1 Accelerator**: role 分離で rescue 減

---

### Pattern J: Config Layering（codex）

#### 出典
- codex: `src/agent/role.rs` の ConfigLayerStack（earlier exploration より）
- `src/config_loader/state.rs` に layer 実装

#### What
Config を**6 層の stack** で解決：
```
1. Built-in defaults
2. Global ~/.codex/config.toml
3. Project-local .codex/config.toml
4. Profile (e.g., [profile.work])
5. Session flags
6. Role layer (per-agent)
```

各層は**non-destructive に上書き**。下層設定を失わない。

#### Why
mew の現設定は：
- `config.py` で hardcoded defaults
- `STATE_DIR = Path(".mew")` のみで project scope
- CLI flag で session scope
- Role 概念なし

これは**flat**。以下の問題：
- Profile 切替困難（work / personal mix）
- User-scope config 不在（`~/.mew/` 未定義、M8 の話）
- Role 別 override 不能

Layered なら：
- "Global で conservative、personal project で bypass" 等が可能
- User identity (M8) の受け皿
- Role-based model/budget の切替（Pattern I と連動）

#### mew 適用
```python
# src/mew/config_stack.py (新規、~300-400 LOC)

@dataclass
class ConfigLayer:
    name: str
    source: Path | str
    settings: dict
    precedence: int

def resolve_config(layers: list[ConfigLayer]) -> ResolvedConfig:
    # precedence 順に merge、上位が下位を override（destructive ではなく record も残す）
    ...

def explain_config(key) -> list[tuple[ConfigLayer, any]]:
    # ある設定値が どの layer で決まったか を説明
    ...
```

#### 紐づく milestone
- **M8 Identity**: user-scope config の受け皿
- **M6 Body**: daemon 設定と session 設定の分離

---

## 2. Priority Matrix

各 pattern の推定 impact × 実装規模：

| Pattern | Impact | LOC | Milestone fit | 優先 |
|---|---|---|---|---|
| **A Explorer** | 極大（rescue 30-40% 減） | 50-100（軽量版）| M5.1 + M10 | **1** |
| **E MCP Integration** | 極大（ecosystem）| 500-800 | M7 Senses | 2 |
| **I Worker/Awaiter roles** | 大（multi-agent 基盤）| 300-500 | M10 | 3 |
| **B AskUserQuestion** | 大（structured approval）| 150-250 | M9 + M5.1 | 4 |
| **F StatusLine** | 大（ambient presence）| 200-300 | M9 | 5 |
| **D Todo management** | 中-大（audit 可視化）| 200-300 | M5.1 + M9 | 6 |
| **C CLAUDE.md 慣習** | 中（onboarding）| 100-200 | M9 | 7 |
| **J Config Layering** | 中（hygiene）| 300-400 | M8 | 8 |
| **H ScheduleCronTool** | 中 | 200-300 | M6 + M7 | 9 |
| **G SleepTool** | 小（代替手段あり）| 30-50 | M7 | 10 |

**合計 ~2,100-3,400 LOC**（9 pattern 全部なら）。実装 ~10-20 時間。

---

## 3. Milestone 別 mapping

### M5.1 (Accelerator)
- **A Explorer**（rescue 直撃）
- **B AskUserQuestion**（approval structure）
- **D Todo management**（audit 可視化）

### M6 Body
- **H ScheduleCronTool**（daemon 要件）
- **G SleepTool**（runtime integration）

### M7 Senses
- **E MCP Integration**（外部 signal の正式 ingress）
- **H ScheduleCronTool**（時間 signal）
- **G SleepTool**（signal 待ち）

### M8 Identity
- **J Config Layering**（user scope の受け皿）

### M9 Legibility
- **F StatusLine**（ambient surface）
- **C CLAUDE.md 慣習**（onboarding）
- **B AskUserQuestion**（structured interaction）
- **D Todo management**（progress visibility）

### M10 Multi-Agent
- **I Worker/Awaiter roles**（role taxonomy の核）
- **A Explorer**（parallel delegation）

---

## 4. 除外した pattern（参考）

user 指示で除外：
- **Codex Sandbox mode**（seatbelt / landlock）: OS 依存 + mew の軽さと相性悪いため、本 review では扱わない

他に考えられたが除外：
- NotebookEdit tool（.ipynb 専用、mew の scope 外）
- REPL tool（動的 code 実行、mew の write path と齟齬）
- Embedded search (bfs/ugrep)（mew は grep/ripgrep で足りる）
- Profile overrides（Config Layering J と同じ）

---

## 5. 統合方法の候補（実装 agent が選択）

本 review の 9 pattern の mew への取り込み方の選択肢：

### Approach 1: ADOPT §5.19-5.27 として追記
`docs/ADOPT_FROM_REFERENCES.md` の延長。既存 22 pattern と統一形式。  
**利点**: 一覧性、既存 agent の参照経路と整合  
**欠点**: ADOPT が膨大化（現 892 行 → 1,400 行超）

### Approach 2: 各 Milestone の設計 doc に分散
M7 設計時に E + G + H を参照、M9 設計時に B + C + F + D を参照、等。  
**利点**: 必要な時に必要な pattern のみ見る  
**欠点**: 全体像を失う

### Approach 3: 本 doc を master reference として保持
`REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` をそのまま reference 元に。各 pattern を採用するとき本 doc を 参照 + implementation doc を 新規作成。  
**利点**: 本 doc が変わらず安定  
**欠点**: 新 patterns が出た時は別 review が要る

### Approach 4: 選択的 extract
本 doc から高 impact 3-5 pattern を選んで個別 REVIEW doc に書き直し、残りは本 doc のまま残す。  
**利点**: 重要な物は深掘り、残りは reference  
**欠点**: どれを extract するか判断必要

**私の推奨**: **Approach 3**（本 doc をそのまま reference）。実装 agent が milestone active 時に参照 + 必要なら個別 implementation doc 作成。

---

## 6. 私が間違っている可能性

1. **Priority matrix**: impact 推定は私の主観。実 dogfood で優先順位が変わる可能性
2. **LOC 見積もり**: 概算、特に MCP integration は 500-800 LOC より重い可能性（SDK 依存）
3. **Milestone fit**: 私の解釈。agent は別の配置が優れている判断可
4. **Pattern 網羅性**: 本 survey で**全てをカバーした保証なし**。継続的に新 pattern 発見される
5. **依存関係**: 例えば Worker/Awaiter (I) は Sub-Agent Spawning (ADOPT §5.5 / M5 Acc #5) に依存。先後関係を丁寧に検討必要

実装 agent が現場判断で優先。本 review は方向のみ。

---

## 7. TL;DR

```
M1-M5 completed.
ROADMAP rebased to M6-M10.

既存 REVIEW (22 patterns, ADOPT + M5 Accelerators) に加えて、
本 review は新 9 pattern を additive に提案:

  A Explorer          M5.1 + M10    (rescue 直撃、最優先)
  B AskUserQuestion   M9 + M5.1     (structured approval)
  C CLAUDE.md 慣習    M9             (onboarding)
  D Todo management   M5.1 + M9     (audit 可視化)
  E MCP Integration   M7            (ecosystem 接続)
  F StatusLine        M9            (ambient presence)
  G SleepTool         M7            (軽量、待機)
  H ScheduleCronTool  M6 + M7       (time-aware)
  I Worker/Awaiter    M10           (multi-role)
  J Config Layering   M8            (user scope 受皿)

除外:
  - Codex Sandbox mode (user 判断)

合計規模: ~2,100-3,400 LOC, 実装 ~10-20 時間
(全部一度にではなく、M6-M10 それぞれで必要な分だけ)
```

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 18:00 JST
**Context**: commit `56ed357`, 1116 commits observed, M1-M5 closed, M6-M10 defined
**Related**: `docs/ADOPT_FROM_REFERENCES.md`, `docs/REVIEW_2026-04-20_M5_ACCELERATORS.md`, `docs/REVIEW_2026-04-20_M6_REFRAMING.md`, `docs/REVIEW_2026-04-20_M6_PROPOSAL.md`
**Conversation trace**: Claude Code session (single session, no memory between runs)
