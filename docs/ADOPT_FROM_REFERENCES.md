# ADOPT_FROM_REFERENCES

`references/fresh-cli/{claude-code, codex, openclaw}` から mew に取り込む価値のある**設計パターン**を、実装判断に使える密度でまとめたもの。

---

## 0. このドキュメントの使い方

- 読み手：mew を実装中の別 Opus 4.7（effort: max）
- 位置付け：**意思決定支援**。prescriptive ではなく、採否とタイミングの判断を最小コストで行えるように書いている
- 使い方：
  1. §1 の decision tree で関係する card に飛ぶ
  2. §2 の drama ranking で優先度を把握
  3. §3 の M2/M3 integration plan で現在の sprint との接続点を確認
  4. §5 の実装カードで詳細（現状／差分／pinpoint 参照／概算 LOC／前提／落とし穴／スケッチ）
- **信頼性**：ファイル位置と行番号は 2026-04-19 時点で検証済み（§8 参照）。参照コミットは参照リポの HEAD。ただし reference リポ更新で行が drift する前提で、**引用行は再確認してから採用する**こと。
- **mew 側パス** (`src/mew/*.py`) は構造把握の起点。行番号は書いていない（すぐ陳腐化するため）。コードを開いて該当構造を探すこと。

### 0.1 2026-04-19 inhabitation adoption decision

Codex + claude-ultra の相談後の採用判断：

- **「AI が入りたい program」として最適化するなら、次に採る 1 枚は 5.12 Memory Scope × Type。**
- 理由：mew は continuity/resume 表示が育ってきたが、記憶がまだ flat で、user preference / project fact / feedback / reference を future resident が迷わず思い出せない。Streaming は操作感を上げるが、Memory Scope は住める場所を作る。
- 5.11 AgentMemorySnapshot は重要だが、state schema がまだ動いている間は早い。5.12 で typed memory API を置いた後、schema が落ち着いたタイミングで採る。
- 5.1 Streaming Tool Executor は、実際の痛みが「cockpit が Codex CLI / Claude Code より遅い」になった時の M2 最優先。現時点では inhabitation 目的の最初の 1 枚ではない。
- 5.8 Agent Frontmatter / 5.9 Skill Manifest は M5 まで待つ。拡張性より先に、記憶・再開・受動実行の芯を固める。
- 2026-04-19 実装メモ：5.12 の MVP は `mew memory --add --type ... --scope ...` と file-backed recall として入り始めた。`work_session.resume.active_memory` として resident THINK prompt にも渡るようになり、`mew memory --active --task-id ...` で注入内容を確認できる。実 Codex Web API dogfood でも active project memory を理由に `README.md` を読む行動が選ばれた。

---

## 1. 一言 decision tree

症状ベースで該当 card に飛ぶ：

| 症状 / 求めるもの | 行くべき card |
|---|---|
| cockpit が Codex CLI より一拍遅く感じる | **5.1 Streaming Tool Executor** |
| ツール実行中にユーザーが打てない／打つと cancel になる | **5.2 MessageQueue** |
| Ctrl-C の挙動がツールによって違うべきなのに一律 | **5.4 Interrupt Behavior per Tool** |
| interrupt/resume が構造として grafted に感じる | **5.3 SQ/EQ Op Enum** |
| 同一セッション内で権限が暗黙に変化する／子 session と混ざる | **5.5 PermissionContext Frozen** |
| タスクごとに allow policy が違うのに CLI flag がセッション全体に残る | **5.6 Per-Turn Policy on Op** |
| 新ツール追加時にセキュリティ属性を忘れる | **5.7 Tool Factory + fail-closed** |
| resident が同じ種類のミスを繰り返す (prompt 修正では消えない) | **5.8 Agent Frontmatter** + **5.9 Skill Manifest** |
| M2 cockpit の介入点 (hook) がコードに散らばっている | **5.10 Hooks as Data** |
| resume が「会話の再生」で遅い／context compression 後に失う | **5.11 AgentMemorySnapshot** |
| メモリが flat で user preference / project context が混ざる | **5.12 Memory Scope × Type** |
| passive tick が polling 形で day-scale が不安定 | **5.13 Mailbox + trigger_turn** |
| 再開時に過去コンテキストの自動想起がない | **5.14 Active Memory Recall** |
| 圧縮時に work memory / verification tail が消える | **5.15 Pre/Post Compact Hooks** |
| ツール実行中の approval が crash でロストする | **5.16 Durable Elicitation** |
| `mew focus` / `mew status` の起動が重くなってきた | **5.17 Cold/Hot Split** |
| 境界違反（例：tool が state 内部に直接 reach）が PR で滑り込む | **5.18 Invariant Tests** |

---

## 2. Drama Ranking (S/A/B とは別軸)

影響軸別。`極大/大/中/小/-` は mew の該当マイルストーン実装後のユーザー/resident 体感での期待差。

| # | 項目 | M2 cockpit feel | M3 continuity | M5 self-improve | Hygiene | 概算 LOC (mew 実装) | 前提 |
|---|---|---|---|---|---|---|---|
| 5.1 | Streaming Tool Executor | **極大** | 中 | - | - | 400-600 | asyncio + 5.3 |
| 5.2 | MessageQueue | **大** | - | - | - | 150-250 | 5.3 |
| 5.3 | SQ/EQ Op Enum | 中 (enabler) | 小 | - | 中 | 200-400 | - |
| 5.4 | Interrupt Behavior per Tool | 中 | - | - | 小 | 80-150 | 5.3 |
| 5.5 | PermissionContext Frozen | 中 | 中 | - | **大** | 200-400 | - |
| 5.6 | Per-Turn Policy on Op | 小 | 中 | - | **大** | 100-200 | 5.5 |
| 5.7 | Tool Factory + fail-closed | - | - | - | 中 | 80-150 | - |
| 5.8 | Agent Frontmatter (.md) | - | - | **大** | 中 | 200-350 | - |
| 5.9 | Skill Manifest (.toml) | - | 中 | **大** | 中 | 300-500 | - |
| 5.10 | Hooks as Data | 中 | - | 中 | 大 | 200-400 | - |
| 5.11 | AgentMemorySnapshot | - | **極大** | - | - | 200-400 | state shape 安定 |
| 5.12 | Memory Scope × Type | - | **大** | 中 | 中 | 150-300 | - |
| 5.13 | Mailbox + trigger_turn | - | **大** | - | - | 150-300 | 5.3 preferred |
| 5.14 | Active Memory Recall | - | 中 | - | - | 100-200 | 5.12 |
| 5.15 | Pre/Post Compact Hooks | - | 中 | - | 小 | 80-150 | 5.10 |
| 5.16 | Durable Elicitation | 小 | 中 | - | **大** | 150-250 | - |
| 5.17 | Cold/Hot Split | 中 (起動) | - | - | 中 | 200-400 (段階的) | - |
| 5.18 | Invariant Tests | - | - | - | 中 | 150-250 | - |

**優先トップ5（もし今週中に 1 つずつ着手するなら）**:
1. **5.1 Streaming Tool Executor** — M2 の体感速度を直撃
2. **5.11 AgentMemorySnapshot** — M3 continuity を「説明」から「load」に上げる
3. **5.2 MessageQueue** — M2 「calm cockpit」の体感を完成
4. **5.12 Memory Scope × Type** — ROADMAP 未着手の「project memory / user preference memory」を成立させる
5. **5.5 PermissionContext Frozen** — M2/M4 の hardening の基盤

---

## 3. M2 / M3 Integration Plan

ROADMAP_STATUS (2026-04-19) の現状に対する織り込み点。

### M2: Interactive Parity (active focus)

> Current gap: "calmer continuous coding cockpit with a more stable reasoning/status pane, less repeated reentry material during long sessions"

| Sprint slot | 採る item | 期待効果 |
|---|---|---|
| 直近 | **5.1 Streaming Tool Executor** | THINK → ACT → tool の直列を、ブロック到着ごとの並行へ。cockpit の burst 感が消える |
| 直近 | **5.2 MessageQueue** | ツール実行中の入力が queue に入り、次ターンで処理される |
| 中期 | **5.3 SQ/EQ** | 5.1 + 5.2 の土台。grafted にならない interrupt 構造 |
| 中期 | **5.4 Interrupt Behavior per Tool** | `run_tests: block` / `read_file: cancel` を tool 宣言に |
| 中期 | **5.5 PermissionContext Frozen** | persisted gates の hardening。子 session が親を汚染しない |
| 継続 | **5.10 Hooks as Data** | cockpit の介入点を settings.json に畳む |
| 低優先 | **5.7 Tool Factory** | 新ツール追加時の hygiene |

### M3: Persistent Advantage (in_progress, 未証明)

> Current gap: "long-running resident cadence is still unproven"

| Sprint slot | 採る item | 期待効果 |
|---|---|---|
| 直近 | **5.11 AgentMemorySnapshot** | continuity score を「復元可能性」の実装に繋げる。resume = load |
| 直近 | **5.12 Memory Scope × Type** | ROADMAP の「project memory search / user preference memory」を実装形に |
| 中期 | **5.13 Mailbox + trigger_turn** | passive tick を polling → event-driven へ。day-scale cadence の基盤 |
| 中期 | **5.14 Active Memory Recall** | ターン冒頭での memory 再呼び出し |
| 低優先 | **5.15 Compact Hooks** | 圧縮境界で work memory を journal に抽出 |

### M4: True Recovery (ongoing)

| Sprint slot | 採る item | 期待効果 |
|---|---|---|
| 折り込み | **5.6 Per-Turn Policy on Op** | 効果 journal に policy が残る。recovery 判断の材料増 |
| 折り込み | **5.16 Durable Elicitation** | crash をまたいで approval が再開可能 |

### M5: Self-Improving (foundation)

| Sprint slot | 採る item | 期待効果 |
|---|---|---|
| M2/M3 安定後 | **5.8 Agent Frontmatter** | resident が新しい agent を宣言的に足せる |
| M2/M3 安定後 | **5.9 Skill Manifest** | 手順知識を prompt ではなく skill ファイルに外出し |

### 継続的 hygiene (並行で)

| Sprint slot | 採る item | 期待効果 |
|---|---|---|
| 都度 | **5.17 Cold/Hot Split** | 起動コストが実害になる前に予防 |
| 都度 | **5.18 Invariant Tests** | 境界違反を PR で止める |

---

## 4. Dependency Graph

```
5.3 SQ/EQ Op Enum ───┬── 5.1 Streaming Tool Executor
                     ├── 5.2 MessageQueue
                     ├── 5.4 Interrupt Behavior per Tool
                     └── 5.13 Mailbox (preferred, not strict)

5.5 PermissionContext Frozen ── 5.6 Per-Turn Policy on Op

5.12 Memory Scope × Type ── 5.14 Active Memory Recall

5.10 Hooks as Data ── 5.15 Pre/Post Compact Hooks

5.11 AgentMemorySnapshot ── depends on stable snapshot shape of state.py
                            (do not adopt while state schema is actively churning)
```

**独立** (他に依存しない): 5.3 / 5.5 / 5.7 / 5.8 / 5.9 / 5.10 / 5.11 / 5.12 / 5.16 / 5.17 / 5.18

---

## 5. Implementation Cards

各 card の構造：

- **Drama**：どの軸に効くか
- **Mew 現状**：`src/mew/*.py` で関連する構造
- **差分**：before → after
- **Pinpoint 参照**：検証済みファイル:行
- **概算 LOC**：mew 側実装の粗見積もり
- **前提**：他 card / 基盤技術
- **落とし穴**：実装時に気を付けるべきもの
- **スケッチ**：pseudo-code または型シグネチャ

---

### 5.1 Streaming Tool Executor

**Drama**: M2 cockpit feel **極大**。単一項目での体感差は最大。

**Mew 現状**: `src/mew/step_loop.py` と `src/mew/work_session.py` の中で、`agent.plan_event()` → `apply_event_plans()` → tool 実行、というモデル応答**完全受信後**の直列ループ。`work_loop.py` は work-session の tool 呼び出しを個別実行するが、model 側が streaming でも tool は全 plan を parse してから走る。

**差分**:
- before: model THINK 全文取得 → JSON parse → tool 配列 → 1 個ずつ実行
- after: SSE delta から `tool_use` ブロックを検出 → **到着順に即 dispatch** → concurrency-safe な tool は並列、safe でないものは排他 → 結果が出た順に UI へ

**Pinpoint 参照**: `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:40` (class 定義), `:35` (doc comment: "Executes tools as they stream in with concurrency control"), `:127` ("Check if a tool can execute based on current concurrency state"), `:138` ("Process the queue, starting tools when concurrency conditions allow")

**概算 LOC**: 400-600（asyncio 採用前提。採らないなら thread + Queue で 500-800）

**前提**: 5.3 SQ/EQ 形を決めてから。純 sync 下で書くと後で捨てることになる。依存許容時は `anyio` を強く推奨。

**落とし穴**:
1. `concurrency_safe` 属性を誤って全 tool に True にすると、write と verify が競合する。**read 系のみ True** がデフォルト。
2. 結果が out-of-order で到着したとき、UI 上の「timeline」との整合（現状 `/work-session timeline` ）を壊さないよう、**表示順序は dispatch order**、実行順序とは分離する。
3. streaming model 側の JSON が不完全で tool block が壊れる場合、現状の「malformed JSON を retryable model error として扱う」挙動 (`agent.py` 近辺) を壊さないこと。

**スケッチ**:
```python
# src/mew/streaming_exec.py (新規)
class StreamingToolExecutor:
    def __init__(self, gate: PermissionContext):
        self._gate = gate
        self._queue: asyncio.Queue[ToolCall] = asyncio.Queue()
        self._exclusive_lock = asyncio.Lock()
        self._results: dict[str, ToolResult] = {}

    async def submit(self, call: ToolCall) -> None:
        await self._queue.put(call)

    async def run(self) -> AsyncIterator[ToolResult]:
        in_flight: set[asyncio.Task] = set()
        while True:
            call = await self._queue.get()
            if call.sentinel_end: break
            if call.concurrency_safe:
                t = asyncio.create_task(self._run_safe(call))
            else:
                t = asyncio.create_task(self._run_exclusive(call))
            in_flight.add(t)
            # yield completed tasks in completion order, preserve dispatch order in UI separately
            ...
```

---

### 5.2 MessageQueue (input-while-busy)

**Drama**: M2 cockpit feel **大**。体感「常に聞いてくれている」を与える。

**Mew 現状**: `mew chat` は REPL ベース。tool 実行中の入力は**受け付けない**か、Ctrl-C で強制中断のどちらか。`/work-session` コマンドは sync。

**差分**:
- before: tool 実行中に user が打つ → 何も起きない or 割り込まれる
- after: tool 実行中に user が打つ → **input queue に追加** → 次のターン冒頭で model 側に提示 → "interrupting message" として plan で参照可能

**Pinpoint 参照**: claude-code は AppState 経由で input buffer を持つ。`src/state/AppState.ts` 周辺（verified: directory 存在、詳細は parallel exploration agent の earlier 報告参照）。

**概算 LOC**: 150-250（5.3 SQ/EQ が先にあれば簡単に乗る）

**前提**: 5.3 (SQ/EQ Op) 推奨。`Op::UserTurn` とは別に `Op::QueuedUserMessage` を足せば自然。

**落とし穴**:
1. queue が溢れた場合の policy を明示（drop newest / drop oldest / block）。**drop oldest** を推奨、drop 通知は audit に残す。
2. quiet chat (`mew chat --quiet`) との干渉：queue 状態の可視化を compact mode で抑制する設計を最初から入れる。
3. model の context に queued message を入れる位置：**ユーザー turn の末尾に追加**が正解。先頭に入れると時系列が歪む。

**スケッチ**:
```python
# 概念レベル
class Submission(Enum):
    USER_TURN = ...
    QUEUED_USER_MESSAGE = ...  # input-while-busy
    INTERRUPT = ...

async def chat_loop():
    async for sub in submission_queue:
        if sub.type == QUEUED_USER_MESSAGE and current_turn_active():
            current_turn.append_queued(sub.text)
        elif sub.type == INTERRUPT:
            await current_turn.abort("user_interrupt")
        ...
```

---

### 5.3 SQ/EQ Op Enum (Submission / Event Queue)

**Drama**: M2 enabler (中)。**5.1/5.2/5.4 の前提として effect が出る**。単体では体感変化は小。

**Mew 現状**: `commands.py` (13k LOC) が CLI → 直接 state 変更、`runtime.py` が tick ベースの event loop。interrupt は POSIX signal でグローバルに捕捉。User 入力と system event が混ざった構造。

**差分**:
- before: interrupt は signal、user 入力は stdin、tick は timer、それぞれ別路線
- after: すべて `Op` (Submission) として queue に入り、処理結果は `Event` として queue に出る。interrupt も `Op::Interrupt` の一種

**Pinpoint 参照**:
- `references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs:379` (`pub enum Op`)
- `:420` (`UserTurn` struct with `approval_policy:429`, `sandbox_policy:437`)
- `:1557` (`TurnAborted(TurnAbortedEvent)`)
- `:3598` (`pub struct TurnAbortedEvent` — cancelled list を含む)

**概算 LOC**: 200-400（Python dataclass + asyncio.Queue で十分）

**前提**: なし。ただし asyncio (または anyio) を入れる判断と一緒に決めるべき。

**落とし穴**:
1. 既存の `commands.py` 直接実行路を**一気に置換しない**。新しい `Op` 経路を追加し、既存 CLI は shim として Op を submit する形で段階移行。
2. `Op` と `Event` のスキーマを最初に固める。後から足すのは易しいが、変えるのは高い。
3. interrupt の粒度：turn-level？ tool-level？ 両方が必要（前者が一般、後者が 5.4 の実装に要る）

**スケッチ**:
```python
# src/mew/protocol.py (新規)
@dataclass(frozen=True)
class UserTurn:
    prompt: str
    approval_policy: ApprovalPolicy
    sandbox_policy: SandboxPolicy
    cwd: Path
    model: str | None = None
    reasoning_effort: str | None = None

@dataclass(frozen=True)
class Interrupt:
    reason: str

Op = UserTurn | Interrupt | QueuedUserMessage | ...

@dataclass(frozen=True)
class TurnAborted:
    turn_id: str
    reason: str
    cancelled_tool_calls: list[str]  # tool call ids

Event = TurnStarted | ToolCallStarted | ToolCallCompleted | TurnAborted | ...
```

---

### 5.4 Interrupt Behavior per Tool

**Drama**: M2 cockpit feel 中。正しい Ctrl-C の感触を与える。

**Mew 現状**: `work_session.py` に `WORK_TOOLS` set があるが、interrupt 時の挙動は全 tool 一律（直近コミットで Ctrl-C capture を改善中）。

**差分**:
- before: Ctrl-C は global、全 tool で cancel
- after: tool 宣言に `interrupt_behavior: "cancel" | "block"`。`run_tests: block`（テストを最後まで走らせる、Ctrl-C は queue に積む）/ `read_file: cancel`（即中止、次の input に進む）

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/Tool.ts:416` (`interruptBehavior?(): 'cancel' | 'block'`)
- codex 側: `protocol.rs:3598` TurnAbortedEvent の `cancelled` リスト (verified @:3598)

**概算 LOC**: 80-150

**前提**: 5.3 SQ/EQ 推奨（Interrupt を Op として扱えると実装が素直）。5.7 Tool Factory があれば default 値 (`cancel`) の注入が自然。

**落とし穴**:
1. `block` 扱いの tool が無限ループしたら？ **すべての block tool にタイムアウト必須**。`run_tests` なら既存の `--timeout` を利用。
2. user の期待と実挙動が乖離しないよう、cockpit で「このツール中の Ctrl-C は queue 動作」を表示する。

**スケッチ**:
```python
@dataclass(frozen=True)
class ToolDef:
    name: str
    interrupt_behavior: Literal["cancel", "block"] = "cancel"  # fail-safe default
    timeout_seconds: float | None = None
    concurrency_safe: bool = False  # also for 5.1
    is_readonly: bool = True  # fail-safe default

READ_FILE = ToolDef(name="read_file", is_readonly=True, concurrency_safe=True)
RUN_TESTS = ToolDef(name="run_tests", interrupt_behavior="block", timeout_seconds=600, is_readonly=False)
```

---

### 5.5 PermissionContext Frozen per-Turn

**Drama**: M2 中、Hygiene **大**、M4 recovery 中。

**Mew 現状**: `work_session.py` の persisted gates + `commands.py` の CLI flag (`--allow-read/write/verify/shell`) + `--approve-tool`/`--reject-tool`。**子 work session の派生時に親の gate を mutate する余地**があり、同一プロセス内で複数セッションが並ぶと混ざる。

**差分**:
- before: gate は state 上の mutable dict / CLI flag から random 時点で読む
- after: **turn 開始時に `PermissionContext` を frozen dataclass に固める**。子 session は親の context を `replace()` で fork。親は絶対に mutate されない

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/Tool.ts:123` (`ToolPermissionContext = DeepImmutable<{...}>`)
- `:140` (`getEmptyToolPermissionContext`)
- `:390` (tool 呼び出し時の `toolPermissionContext: ToolPermissionContext`)

**概算 LOC**: 200-400

**前提**: なし。ただし `state.py` の permission 表現を immutable に寄せる前提作業が要る。

**落とし穴**:
1. **mew のペルミッションは複数ソース混在** (CLI flag + persisted session gate + hook 的な `.mew/settings.json`)。凍結時点で**どこから読むかの優先順位**を明示する（推奨：CLI > local settings > session default > global default）。
2. 子 session を fork した後、親に approve 情報を「伝えたい」場合がある。これは context 経由ではなく **Event** として伝える（5.3 の Event queue 経由）。context 自体は不変。
3. plan mode (`mew code --plan`?) などのモード遷移時に context が切り替わる → `pre_plan_mode` を context 内に保持しておき戻せるように。

**スケッチ**:
```python
# src/mew/permissions.py (新規または強化)
@dataclass(frozen=True)
class PermissionContext:
    mode: Literal["default", "plan", "bypass"]
    allow_read_roots: frozenset[Path]
    allow_write_roots: frozenset[Path]
    allow_shell: bool
    allow_verify: bool
    approval_policy: Literal["never", "on_request", "always"]
    avoid_prompts: bool  # for background runs
    pre_plan_mode: PermissionContext | None = None

def fork(parent: PermissionContext, *, mode: str | None = None, **overrides) -> PermissionContext:
    return replace(parent, mode=mode or parent.mode, **overrides)
```

---

### 5.6 Per-Turn Policy on Op

**Drama**: M3 continuity 中、M4 recovery **大** (policy が audit に残る)、Hygiene **大**。

**Mew 現状**: ポリシーはセッション level（work_session の gate）とプロセス level（CLI flag）に分散。**タスクや turn 単位**では表現されていない。

**差分**:
- before: "このセッションは `--allow-write` で始まった" という session level fact
- after: "turn #42 は policy P で走った" という turn level fact。effects.jsonl に policy も残る → M4 で「この効果はこの policy 下で許されたものか」判定可能

**Pinpoint 参照**:
- `codex/codex-rs/protocol/src/protocol.rs:420` (`UserTurn { approval_policy, sandbox_policy, cwd, model, ... }`)
- `:429`, `:437` (policy フィールド定義)

**概算 LOC**: 100-200（5.5 に乗せる）

**前提**: 5.5 (PermissionContext Frozen) 先。

**落とし穴**:
1. **backward compat**: 既存 CLI flag は従来通り動かす。Op の policy は**新規コード経路のみで解釈**する二段構え。
2. policy diff の表示：task 間で policy が違うと user が混乱するので、`mew status` で visible にする。

**スケッチ**:
```python
@dataclass(frozen=True)
class UserTurn:
    prompt: str
    permission_context: PermissionContext  # 5.5 の frozen
    cwd: Path
    model: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    task_id: str | None = None
```

---

### 5.7 Tool Factory + fail-closed default

**Drama**: Hygiene 中。新ツール追加時の安全網。

**Mew 現状**: `work_session.py:WORK_TOOLS` は **set of strings**。各 tool のメタ情報 (read-only, concurrency, interrupt) は**コード内の分岐**で表現。

**差分**:
- before: 新ツール追加時に read/write set、concurrency、interrupt を**別々の場所で更新**。どこかを忘れるとセキュリティ regression
- after: `build_tool()` factory で宣言。未指定属性は**安全側デフォルト**が自動注入

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/Tool.ts:704` (doc: "Methods that `buildTool` supplies a default for")
- `:757` (`const TOOL_DEFAULTS`)
- `:783` (`export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D>`)

**概算 LOC**: 80-150

**前提**: なし。5.4/5.5 と合わせて入れるのが自然。

**落とし穴**:
1. `WORK_TOOLS`、`READ_ONLY_WORK_TOOLS`、`COMMAND_WORK_TOOLS`、`WRITE_WORK_TOOLS` 等の既存 set を factory 経由で**導出**するように段階移行（set を即消すと他の参照が壊れる）。
2. fail-closed default は「**書き込み許可はデフォルト False**」「**concurrency_safe はデフォルト False**」「**interrupt_behavior はデフォルト cancel**」。保守的側に倒す。

**スケッチ**:
```python
TOOL_DEFAULTS = dict(
    is_readonly=True,         # 書くなら明示
    concurrency_safe=False,   # 並列安全なら明示
    interrupt_behavior="cancel",  # block は明示
    requires_approval=False,
    timeout_seconds=None,
)

def build_tool(**spec) -> ToolDef:
    return ToolDef(**{**TOOL_DEFAULTS, **spec})

# 使用例
EDIT_FILE = build_tool(name="edit_file", is_readonly=False, requires_approval=True)
READ_FILE = build_tool(name="read_file", concurrency_safe=True)
RUN_TESTS = build_tool(name="run_tests", is_readonly=False, interrupt_behavior="block", timeout_seconds=600)
```

そこから `WORK_TOOLS = frozenset(t.name for t in ALL_TOOLS)` など既存 set を導出。

---

### 5.8 Agent Frontmatter (.md with YAML)

**Drama**: M5 **大**、Hygiene 中。

**Mew 現状**: エージェントに相当する概念は `self_improve.py`、`programmer.py` に hardcode。外部 agent への dispatch は `agent_runs.py` 経由だが、各 agent の設定は static。

**差分**:
- before: 新 agent を追加するには code を書く
- after: `.mew/agents/reviewer.md` を置くだけで追加できる。frontmatter に tools / prompt / memory_scope / mcp_servers / hooks / maxTurns

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/tools/AgentTool/loadAgentsDir.ts:73-98` (`AgentJsonSchema` で frontmatter schema 定義)
  - フィールド確認済み：`description`, `tools`, `disallowedTools`, `prompt`, `model`, `effort`, `permissionMode`, `mcpServers`, `hooks`, `maxTurns`, `skills`, `memory: 'user'|'project'|'local'`, `background`
- built-in examples: `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/{claudeCodeGuideAgent,exploreAgent,generalPurposeAgent,planAgent,verificationAgent,statuslineSetup}.ts`

**概算 LOC**: 200-350（YAML/TOML 片側 + validation）

**前提**: なし。ただし 5.5 (PermissionContext) があれば `permissionMode` を agent 宣言で制御できる。

**落とし穴**:
1. YAML parsing は stdlib に無い (Python 3.11+ の `tomllib` は TOML のみ)。**frontmatter は TOML で統一**するか、最小 YAML parser を同梱する判断が要る。推奨：**frontmatter を `+++` で囲む TOML**（MkDocs の `rich_yaml` 形式を真似しない）。
2. built-in agent の書き換えは**最後に**。既存の hardcode agent は残し、新規宣言型 agent を並列で動かしてから移行。
3. frontmatter の未知フィールドは warning で残す（schema 拡張の痛点を可視化）。

**スケッチ**:
```
# .mew/agents/reviewer.md
+++
description = "Review work session diffs and flag risky changes"
tools = ["read_file", "search_text", "git_diff", "git_log"]
model = "inherit"
effort = "high"
permission_mode = "default"
memory_scope = "project"
max_turns = 8
+++

You are a code reviewer. Inspect the latest diffs and flag anything that:
- Breaks an established invariant
- Mixes implementation-only with paired tests
...
```

---

### 5.9 Skill Manifest (.toml)

**Drama**: M5 **大**、M3 中、Hygiene 中。

**Mew 現状**: 手順知識は `prompt` / `context.py` の組み立てに埋め込み。「daily-report を書く手順」のような反復的な手順は**変更するたびに code を触る**。

**差分**:
- before: 手順知識は prompt 生成ロジックに埋没
- after: `.mew/skills/daily-report/manifest.toml` + `impl.py` で skill 単位にカプセル化。中のモデル自身が skill を追加/改訂できる

**Pinpoint 参照**:
- `references/fresh-cli/openclaw/extensions/*/openclaw.plugin.json` (検証済み：extensions に `.plugin.json` が多数あり。例：`extensions/memory-lancedb/openclaw.plugin.json`)
- `references/fresh-cli/openclaw/skills/` ディレクトリ実在（例：`1password`, `apple-notes`, `camsnap`, `canvas`, `clawhub` ...）
- `references/fresh-cli/openclaw/.agents/skills/` に agent-skill が実在（例：`openclaw-ghsa-maintainer`, `openclaw-qa-testing`, `parallels-discord-roundtrip`, `security-triage`）

**概算 LOC**: 300-500（manifest parser + skill registry + impl loader + 最初の 1 つ skill の dogfood 実装）

**前提**: 5.17 (Cold/Hot Split) を先に考えておくと、manifest は cold path・impl は hot path で自然に分けられる。

**落とし穴**:
1. skill の execution 境界を最初に決める：**resident model が skill impl を直接実行する** のか、**skill は prompt 生成のヘルパに徹する** のか。前者は powerful だが sandbox が要る。推奨：**初期は prompt helper のみ**、徐々に executor へ。
2. skill の versioning：manifest に `api_version` を必須に（後で schema を変えるための escape hatch）。
3. mew の既存 `morning_paper.py`, `dream.py`, `journal.py` 等は**実質 skill**。これらを skill ディレクトリに寄せる refactor を並走するのが綺麗だが、M2/M3 の中では避ける。

**スケッチ**:
```toml
# .mew/skills/daily-report/manifest.toml
api_version = "1"
id = "daily-report"
description = "Generate a daily reentry report from journal, mood, dream, self-memory"
trigger_commands = ["mew daily"]
reads = ["journal", "mood", "dream", "self_memory"]
provides_tools = []
defer_impl_load = true
```

```python
# .mew/skills/daily-report/impl.py
def run(ctx: SkillContext) -> SkillResult:
    ...
```

---

### 5.10 Hooks as Data (settings.json)

**Drama**: M2 cockpit feel 中、Hygiene **大**。

**Mew 現状**: cockpit 制御の `--no-verify`、`--approve-all`、`--reject-tool`、`/work-session approve`... と flag/コマンドが増え続けている。拡張点は code の中に散らばる。

**差分**:
- before: 新しい介入点を足すたびに CLI/chat command を足す
- after: `settings.json` に `{ hooks: [{event, tool, if, behavior/command}] }` を書くだけで介入できる。**code 改修不要**

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/utils/hooks/` ディレクトリ（directory 存在は既出報告で確認、具体ファイル名は要再検）
- settings での hook 表現は `loadAgentsDir.ts:88` で `hooks: HooksSchema().optional()` として参照されている（確認済み）

**概算 LOC**: 200-400

**前提**: なし。ただし 5.7 (Tool Factory) があると hook の matcher (`tool: "bash", if: "git *"`) を tool declaration 側とリンクしやすい。

**落とし穴**:
1. hook が shell command の場合、**sandbox と timeout を明示**。mew の allow policy と整合させる。
2. hook が複数マッチした時の優先順位を決める：**block > ask > allow > command**。
3. hook failure を silent にしない。cockpit に「hook X failed」を表示する仕組みが要る。

**スケッチ**:
```jsonc
// .mew/settings.json
{
  "hooks": [
    { "event": "pre_tool_use", "tool": "run_command", "if": "rm -rf *", "behavior": "block" },
    { "event": "pre_tool_use", "tool": "edit_file", "if": "src/mew/**", "command": ["python", "scripts/check_paired_test.py", "${tool.input.path}"] },
    { "event": "post_turn", "command": ["python", "scripts/update_journal.py", "${turn.id}"] }
  ]
}
```

---

### 5.11 AgentMemorySnapshot

**Drama**: M3 continuity **極大**。

**Mew 現状**: `work_session.py` が resume bundle を生成、continuity score あり。ただし resume は「状態の語り（explanation）」寄りで、**state の機械的な load** ではない。context compression 後の resume は特に弱い（再構築が要る）。

**差分**:
- before: resume = 最新 state + 会話履歴再生 + 推測
- after: 完了（または中断）時点で**構造化スナップショット**を保存。resume = snapshot load + 差分確認

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/tools/AgentTool/agentMemorySnapshot.ts` (実在確認済み)
- `loadAgentsDir.ts:51` で `checkAgentMemorySnapshot, initializeFromSnapshot` が import されている（実在裏付け）

**概算 LOC**: 200-400

**前提**: state schema の安定。**現在 M2 cockpit 側で state が活発に変わっている間は避ける**。continuity score が落ち着いた（直近コミット群）タイミングで着手するのが良い。

**落とし穴**:
1. snapshot が stale になった時の検出：`state_version_hash` を snapshot に埋める。load 時に version 差分があれば「partial resume」扱い。
2. snapshot と effect journal の関係：**snapshot は effect journal の投影**であるべき。snapshot が独立に mutate されると integrity が崩れる。
3. snapshot のサイズ管理：**session 毎に 1 ファイル**（`.mew/sessions/{session_id}/snapshot.json`）にし、archive 時に圧縮。

**スケッチ**:
```python
@dataclass
class WorkSessionSnapshot:
    session_id: str
    task_id: str
    state_schema_version: str
    closed_at: str | None
    last_effect_id: int
    working_memory: dict
    touched_files: list[str]
    pending_approvals: list[dict]
    continuity_score: float
    continuity_recommendation: dict | None

def save_snapshot(session_id: str) -> Path: ...
def load_snapshot(session_id: str) -> WorkSessionSnapshot | None: ...
def resume_from_snapshot(snapshot: WorkSessionSnapshot) -> ResumeContext:
    # validate schema version, check effect journal tail == last_effect_id,
    # if drift: return partial resume with drift notes
    ...
```

---

### 5.12 Memory Scope × Type Taxonomy

**Drama**: M3 **大**。ROADMAP の "project memory search / user preference memory" を直接成立させる。

**Mew 現状**: `memory.py`, `self_memory.py`, `journal.py`, `dream.py`, `mood.py` — 記録はあるが分類は **by-file**。"user profile" と "project state" と "feedback rule" と "reference link" が同じ layer に混ざる。

**差分**:
- before: `.mew/memory/*.md` は flat
- after: `.mew/memory/{private|team}/{user|feedback|project|reference}/*.md` で scope × type 分類。recall 時に type で絞れる

**Pinpoint 参照**:
- `references/fresh-cli/claude-code/src/memdir/memoryTypes.ts:14` (検証済み: `MEMORY_TYPES = ['user', 'feedback', 'project', 'reference']`)
- `:37` (`TYPES_SECTION_COMBINED` — scope は `private | team` の二値、type と直交)
- `:28` (`parseMemoryType` — frontmatter から type を読む、不明は undefined に degrade)

**概算 LOC**: 150-300

**前提**: なし。mew の既存 journal/dream/mood も**type 付きメモリとして読み替える**のが綺麗。

**落とし穴**:
1. 既存メモリの migration：**無理に一括変更しない**。新規メモリを frontmatter 付きで書き、旧 flat は `type: unknown` で扱う。
2. recall API の signature を最初に固定する：`recall(scope=..., type=..., query=..., k=5)`。後で変えると plugin が全滅する。
3. team scope は**現状 mew に team concept がない**。`team` は "shareable" の意味で用意しておく（ROADMAP に team が出たとき使える）。

**スケッチ**:
```python
class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"
    UNKNOWN = "unknown"  # for legacy

class MemoryScope(str, Enum):
    PRIVATE = "private"
    TEAM = "team"

@dataclass
class MemoryEntry:
    id: str
    scope: MemoryScope
    type: MemoryType
    name: str
    description: str  # 1-line hook for recall
    body: str
    created_at: str

def recall(*, scope: MemoryScope | None = None, type: MemoryType | None = None,
           query: str, k: int = 5) -> list[MemoryEntry]: ...
```

---

### 5.13 Mailbox + trigger_turn

**Drama**: M3 **大** ("long-running resident cadence" を実装形に)。

**Mew 現状**: passive tick は timer-based (`runtime.py`)。子 task からの「親を起こす」signal は無く、必要な時は親が poll。

**差分**:
- before: passive tick は**時刻ベース**。子の完了を親が気付くのは次の tick
- after: 子タスクが `Mail { from, to, trigger_turn: bool }` を親に送ると、`trigger_turn: true` の場合**親が即座に wake**

**Pinpoint 参照**:
- `references/fresh-cli/codex/codex-rs/core/src/agent/mailbox.rs:11` (`pub(crate) struct Mailbox`)
- `:17` (`MailboxReceiver`)
- `:43` (`pub(crate) fn send(&self, communication: InterAgentCommunication) -> u64`)
- `:63` (`pub(crate) fn has_pending_trigger_turn(&mut self) -> bool`)
- `:83` (`trigger_turn: bool`)

**概算 LOC**: 150-300

**前提**: 5.3 (SQ/EQ Op) があると `Op::MailArrived` として自然に合流。なくても動くが後で継ぎ接ぎになる。

**落とし穴**:
1. mailbox が詰まった時の挙動（bounded vs unbounded）：**unbounded + 低優先度 trigger は drop**。最重要は trigger_turn: true。
2. 循環：A → B → A の ping-pong を prevent するため、**turn あたり最大 N mail 処理**のガードを入れる。
3. passive tick との合流：mailbox の trigger_turn と timer tick が同時に来た時は **mail を優先**、tick は skip。

**スケッチ**:
```python
@dataclass(frozen=True)
class InterAgentMail:
    seq: int
    from_id: str
    to_id: str
    payload: dict
    trigger_turn: bool
    sent_at: str

class Mailbox:
    def __init__(self): self._q: list[InterAgentMail] = []
    def send(self, mail: InterAgentMail) -> int: ...
    def drain(self, max_n: int = 100) -> list[InterAgentMail]: ...
    def has_pending_trigger(self) -> bool:
        return any(m.trigger_turn for m in self._q)

# runtime.py 側
def passive_loop():
    while running:
        if mailbox.has_pending_trigger():
            handle_mails()
        elif time_for_tick():
            tick()
        else:
            wait_for_mail_or_tick(timeout=tick_interval)
```

---

### 5.14 Active Memory Recall

**Drama**: M3 中。ターン冒頭の自動想起。

**Mew 現状**: `context.py` が resume bundle 等を prepend するが、**semantic recall はしていない**。過去メモリはモデルが自発的に要求しないと入らない。

**差分**:
- before: model がターン開始時に「関連メモリを見せて」と tool 呼びする必要あり
- after: **ターン開始前の blocking sub-step** で現在の入力と working memory から recall を実施、関連メモリを context に prepend

**Pinpoint 参照**:
- `references/fresh-cli/openclaw/extensions/active-memory/` ディレクトリ実在確認済み（`openclaw.plugin.json` あり）

**概算 LOC**: 100-200

**前提**: 5.12 (Memory Scope × Type) があるべき。無いと recall の signal が弱い。

**落とし穴**:
1. **recall を遅くしない**。file-scan full-text で 100ms 超えたら resident の応答性が劣化。最初は**トップレベル description (1-line hook) だけを scan**、必要になってから body を fetch。
2. recall 結果が多すぎると context 爆発。**k=5 を上限**とし、score threshold を設定。
3. 将来 vector DB に差し替える想定で、recall backend を Protocol に：

**スケッチ**:
```python
class MemoryBackend(Protocol):
    def recall(self, *, query: str, scope: MemoryScope | None,
               type: MemoryType | None, k: int) -> list[MemoryEntry]: ...

class FileMemoryBackend:
    """grep-based. 依存ゼロ。"""
    def recall(self, *, query, scope, type, k):
        # 1-line hook search, then body fetch for top-k
        ...

# 起動時に swap 可能
MEMORY_BACKEND: MemoryBackend = FileMemoryBackend()

# 各ターン冒頭
def on_turn_start(turn: UserTurn) -> list[MemoryEntry]:
    recalled = MEMORY_BACKEND.recall(query=turn.prompt, scope=None, type=None, k=5)
    return recalled  # prepend to context
```

---

### 5.15 Pre/Post Compact Hooks

**Drama**: M3 中。圧縮境界で情報を救う。

**Mew 現状**: context compression は model backend 側（Codex Web API）の挙動。mew 側で「圧縮前に X を救う」仕組みは無い。`compressed_prior_think` で古い turn を見せる工夫はあるが、hook ポイントではない。

**差分**:
- before: 圧縮は黒箱。失うものは復元不能
- after: pre-compact hook で「work memory / verification tail / touched file list」を journal に書き出す → 圧縮後も load 可能

**Pinpoint 参照**: claude-code の `src/services/compact/compact.ts` 付近（earlier exploration agent 報告。直接 verify 未実施、**採用前に要実地確認**）。

**概算 LOC**: 80-150

**前提**: 5.10 (Hooks as Data) 先。hook フレームワーク無しに専用 hook を足すのは非推奨。

**落とし穴**:
1. 圧縮 trigger の検出：mew 側で token 数を厳密に見ていない可能性。**API からの hint 取得 or heuristic (turn count)** で近似する設計。
2. pre-compact が重いと圧縮遅延が長くなる。hook は 100ms 以内で済ます設計。

---

### 5.16 Durable Elicitation

**Drama**: M4 recovery **大**、Hygiene **大**。

**Mew 現状**: `mew work --prompt-approval` でインタラクティブ承認があるが、プロセスが落ちると承認待ちが**失われる**。

**差分**:
- before: 承認待ち中に crash → user が再入力、mew は承認要求を覚えていない
- after: 承認要求は `.mew/elicitations/{id}.json` に書かれ、crash 後も ID 経由で再開

**Pinpoint 参照**: claude-code の `src/types/hooks.ts:135-139` (Elicitation hook)、`src/services/mcp/elicitationHandler.ts`（earlier report から。**採用前に要実地確認**）

**概算 LOC**: 150-250

**前提**: なし。ただし 5.5 (PermissionContext) と合わせると「approve 時の context」も残せる。

**落とし穴**:
1. elicitation が古くなった時の扱い（TTL）：**24h 以上古い elicitation は stale 扱い**、user に再提示。
2. elicitation の UI：chat、CLI flag、HTTP webhook の複数経路で応答可能にする。単一経路にすると backup が無い。

---

### 5.17 Cold/Hot Split (preventive)

**Drama**: Hygiene 中。将来の起動コスト対策。

**Mew 現状**: `mew/__main__.py` → `cli.py` → `commands.py` (13k LOC) が起動時にほぼすべて import される。skill が増えると効く。

**差分**:
- before: すべての command が startup import
- after: `mew focus`, `mew status` 等の cold command は**メタデータのみ** import。`mew work`, `mew code` が初めて tool runtime を lazy-import

**Pinpoint 参照**:
- openclaw `src/channels/plugins/types.plugin.ts` vs `*.runtime-api.ts` 等の pattern（earlier report）。**pattern そのものは Python で容易に実装可能**

**概算 LOC**: 200-400（段階的）

**前提**: なし。5.9 (Skill Manifest) を採用した時点で自然に起きる。

**落とし穴**:
1. 過剰分離で可読性が落ちる。**hot-path 上の 1-2 個の module のみ分離**。全部は不要。
2. import 副作用（global state 登録等）を持つ module は要注意。lazy import で副作用が起きないこと。

---

### 5.18 Invariant Tests (AST-based)

**Drama**: Hygiene 中。境界違反の早期検出。

**Mew 現状**: pytest がカバーしてるが、**「tool が state 内部に直接 import で触っていないか」**等の構造不変量は手動レビュー依存。

**差分**:
- before: 構造違反は PR レビュアーが気付く
- after: `scripts/check_tool_boundaries.py` が AST で import グラフを検査、既知例外は `test/fixtures/baseline_violations.json`

**Pinpoint 参照**:
- openclaw `scripts/check-extension-plugin-sdk-boundary.mjs` (earlier report)

**概算 LOC**: 150-250

**前提**: なし。

**落とし穴**:
1. baseline drift を放置すると**意味が腐る**。月次レビューで baseline を減らす運用を決めてから入れる。
2. false positive 率が高いと devx 劣化。**最初は 1-2 ルールだけ**（例：`src/mew/tools/**` は `src/mew/state.py` を直接 import 不可）。

**スケッチ**:
```python
# scripts/check_tool_boundaries.py
import ast, json, pathlib

BAD_IMPORT_RULES = [
    # (importing_glob, must_not_import_module)
    ("src/mew/read_tools.py", "src.mew.state"),
    # ...
]

def check() -> list[dict]:
    violations = []
    for glob, bad in BAD_IMPORT_RULES:
        for path in pathlib.Path(".").glob(glob):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == bad:
                    violations.append({"file": str(path), "line": node.lineno, "rule": f"must_not_import {bad}"})
    baseline = json.loads(pathlib.Path("test/fixtures/baseline_violations.json").read_text())
    new = [v for v in violations if v not in baseline]
    return new
```

---

## 6. 依存トレードオフ（再掲 + 具体化）

### 劇的に効く採用候補

| dep | 何が書ける | 関係する card |
|---|---|---|
| `anyio` (または `trio`) | 構造化並行性・キャンセル伝播 | 5.1 / 5.2 / 5.3 / 5.4 |
| `watchdog` | ファイル監視 | M3 passive observation, 5.13 と合流 |
| `httpx` | 非同期 HTTP + SSE | streaming backend、webhook |
| `pydantic` or `msgspec` | 型付き state / Op / Event | 5.3 / 5.5 / 5.11 |
| `rich` | 段組・live 表示 | M2 cockpit 全般 |
| `mcp` (公式 SDK) | MCP bridge | 外部ツール口（新 card 候補） |

### 条件付き

| dep | 条件 |
|---|---|
| `anthropic` / `openai` SDK | 手組み HTTP の維持コストが実害に達したら |
| `lancedb` / `chromadb` | 5.14 active recall が file backend で遅いと判明してから |
| `textual` | TUI を本気で作ると決めてから |

### 拒否

- `langchain` / `autogen` / `crewai`: エージェント性を他人の語彙で書き直す。mew の芯を上書きする。

### 判断基準

1. **IO/センサー系** (watchdog, httpx, anyio)：採る
2. **データ/スキーマ系** (pydantic, rich)：採る
3. **エージェント性を持つもの**：採らない
4. **ベンダーロック**：代替の維持コストが実害化してから

---

## 7. 取り込まないもの

- Codex の Bazel / Landlock / Seatbelt：OS 依存、mew の軽さを壊す
- Openclaw の plugin marketplace / 107-extensions monorepo：スケール問題はまだ無い
- Claude-code の TUI 細部（Ink, vim mode, keybindings）：CLI の哲学が違う
- モバイル / multi-channel bridge：mew の「ターミナル一点集中」を崩す
- 重量フレームワーク（§6 拒否リスト参照）

---

## 8. 検証ノート（2026-04-19）

### 実地検証済み（ファイルと行番号を本文で使用）

- claude-code: `src/Tool.ts:123, 140, 390, 416, 704, 757, 783`（PermissionContext, interruptBehavior, buildTool, TOOL_DEFAULTS）
- claude-code: `src/services/tools/StreamingToolExecutor.ts:35, 40, 127, 138`
- claude-code: `src/tools/AgentTool/loadAgentsDir.ts:51, 73-98`（AgentJsonSchema + MemorySnapshot import）
- claude-code: `src/tools/AgentTool/agentMemorySnapshot.ts`（ファイル実在）
- claude-code: `src/memdir/memoryTypes.ts:14, 28, 37`（MEMORY_TYPES, parseMemoryType, TYPES_SECTION_COMBINED）
- claude-code: `src/tools/AgentTool/built-in/*.ts`（built-in agents が code-defined として実在）
- codex: `codex-rs/protocol/src/protocol.rs:379, 420, 429, 437, 1557, 3598`（Op enum, UserTurn, TurnAborted）
- codex: `codex-rs/core/src/agent/mailbox.rs:11, 17, 43, 63, 83`（Mailbox, trigger_turn）
- openclaw: `AGENTS.md` (root) — 実在
- openclaw: `skills/` ディレクトリ — 実在（1password, apple-notes, camsnap, canvas, clawhub, ...）
- openclaw: `.agents/skills/` — 実在（openclaw-ghsa-maintainer, parallels-discord-roundtrip, ...）
- openclaw: `extensions/*/openclaw.plugin.json` — 実在（memory-lancedb, moonshot, lmstudio, ...）

### 未検証（採用前に実地確認を）

- claude-code `src/utils/hooks/` 配下の具体ファイル（5.10）
- claude-code `src/services/compact/compact.ts`（5.15）
- claude-code `src/services/mcp/elicitationHandler.ts`（5.16）
- openclaw `scripts/check-extension-plugin-sdk-boundary.mjs`（5.18）
- openclaw `src/plugins/` の manifest-first pattern の詳細

### 取り消した（前版にあった誤り）

- **openclaw の scoped AGENTS.md 分散配置は未検証/実在せず**。前版で `src/plugin-sdk/AGENTS.md`, `src/channels/AGENTS.md` 等を引用していたが、実地検証で見つかったのは**ルート `openclaw/AGENTS.md` のみ**。scoped AGENTS.md パターン自体は有用だが、openclaw を出典とするのは不正確。**claude-code 自身が built-in agent を `src/tools/AgentTool/built-in/` に scoped に持つ pattern**の方が正確な出典。

---

## 9. Pinpoint Reference Index

検証済み参照のみ。`references/fresh-cli/` からの相対パス。

### claude-code
```
src/Tool.ts:123                ToolPermissionContext (DeepImmutable)
src/Tool.ts:140                getEmptyToolPermissionContext
src/Tool.ts:390                tool call with toolPermissionContext
src/Tool.ts:416                interruptBehavior(): 'cancel' | 'block'
src/Tool.ts:704-792            TOOL_DEFAULTS + buildTool factory
src/services/tools/StreamingToolExecutor.ts:40   class StreamingToolExecutor
src/tools/AgentTool/loadAgentsDir.ts:73-98      AgentJsonSchema (frontmatter shape)
src/tools/AgentTool/agentMemorySnapshot.ts      (checkAgentMemorySnapshot, initializeFromSnapshot)
src/tools/AgentTool/built-in/                   built-in agents (exploreAgent, planAgent, ...)
src/memdir/memoryTypes.ts:14                    MEMORY_TYPES = ['user','feedback','project','reference']
src/memdir/memoryTypes.ts:28                    parseMemoryType
```

### codex
```
codex-rs/protocol/src/protocol.rs:379           pub enum Op
codex-rs/protocol/src/protocol.rs:420           pub struct UserTurn
codex-rs/protocol/src/protocol.rs:429           approval_policy: AskForApproval
codex-rs/protocol/src/protocol.rs:437           sandbox_policy: SandboxPolicy
codex-rs/protocol/src/protocol.rs:1557          TurnAborted(TurnAbortedEvent)
codex-rs/protocol/src/protocol.rs:3598          pub struct TurnAbortedEvent
codex-rs/core/src/agent/mailbox.rs:11           pub(crate) struct Mailbox
codex-rs/core/src/agent/mailbox.rs:43           fn send(...)
codex-rs/core/src/agent/mailbox.rs:63           fn has_pending_trigger_turn()
codex-rs/core/src/agent/mailbox.rs:83           trigger_turn: bool
codex-rs/core/src/agent/{control,registry,role}.rs   agent tree primitives
codex-rs/state/src/runtime.rs                   StateRuntime + SQLite partitioning
```

### openclaw
```
AGENTS.md                                        root (only; no scoped sub-AGENTS.md)
.agents/skills/{openclaw-qa-testing,...}         agent-bound skills
skills/{1password, apple-notes, canvas, ...}     tool-like skills (dir-per-skill)
extensions/*/openclaw.plugin.json                plugin manifests (e.g. memory-lancedb, moonshot)
src/plugins/                                     plugin discovery/registry code
```

---

## 10. 最後に — 実装判断の短い推奨

**今のスプリントで 1 つだけ採るなら**: **5.1 Streaming Tool Executor**。ROADMAP_STATUS が明示する M2 のギャップ「Codex CLI より遅く感じないか」に直撃する唯一の項目。依存許容なら `anyio` を同時に入れる。

**今のスプリントで 2 つ採れるなら**: **5.1 + 5.11 AgentMemorySnapshot**。M2 の体感と M3 の continuity を同時に進める。ただし 5.11 は state schema の揺れが収まったタイミングに入れる。

**3 つ以上は同時着手しない**。各 item が要する dogfood サイクルを考えると、並走させるほど信号が弱くなる。

**何もしない選択肢**：直近 commit 群（continuity 関連）のレビュー循環が健全に回っている間は、**何も取り込まず M2 の現スライスを締めるのが最適**。各 card は「M2 の次スライスを決める時に読む」使い方が正しい。
