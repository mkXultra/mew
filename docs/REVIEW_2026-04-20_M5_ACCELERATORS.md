# REVIEW 2026-04-20 — M5 Accelerators from References

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。M5 が active milestone になった今、rescue rate を下げる reference patterns の提案
**生成条件**: 2026-04-20 16:30 JST 以降、commit `a70d21e` 時点、1109 commits、M4 `done`、M5 active、最初の no-rescue candidate (`3174c85`) 記録済み

**関連**:
- `docs/ADOPT_FROM_REFERENCES.md`（全 S/A/B card、M5 前は判断保留）
- `docs/REVIEW_2026-04-20_M6_REFRAMING.md`（M6 reframing、並行候補）
- `ROADMAP.md` M5 Entry gate + Done-when + safety boundaries（`1bd45fe` で定義）
- `references/fresh-cli/{claude-code,codex,openclaw}/`

---

## 0. 動機

M4 が closed（`97236e4` at 13:10 JST）、M5 が正式 active。直近 3 時間で：
- Self-improve audit bundle 基盤構築
- Rescue vs no-rescue classification 導入
- **初の no-rescue candidate 記録**（`3174c85`）

M5 Done-when：
```
- at least 5 consecutive safe self-improvement loops
- no human rescue edits; human intervention is approval/rejection/redirection
- at least 1 loop exercises interruption or failure recovery
- every loop records product-goal rationale + audit bundle
```

**現在の課題**: 1 本目 no-rescue 達成、**5 本連続**が必要。  
`rescue` になる原因：実装が迷走、verification が甘く失敗見逃し、approval ceremony の肥大、etc.

Reference patterns の中に**rescue rate を structurally 下げる設計**が複数存在する。本 review はその map と採用順序を整理する。

---

## 1. Top 5 M5 Acceleration Patterns

### 1.1 Adversarial VerificationAgent（**最優先**）⭐

#### 出典
`references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts`（verified: 存在）

#### Core Prompt（verified 抜粋）
```
"You are a verification specialist. Your job is not to confirm the
 implementation works — it's to try to break it.

You have two documented failure patterns.
 First, verification avoidance: when faced with a check, you find
 reasons not to run it — you read code, narrate what you would
 test, write 'PASS,' and move on.
 Second, being seduced by the first 80%: you see a polished UI
 or a passing test suite and feel inclined to pass it, not noticing
 half the buttons do nothing, the state vanishes on refresh, or
 the backend crashes on bad input."
```

#### なぜ M5 に決定的か

Rescue pattern の大半は "**verifier が甘い**" から：
- Tests pass → "OK" と結論
- Model が "verified" と言う → 信じる
- Surface pass → deep fail 見逃し

Adversarial mindset は **"壊そうとする"** のでこれを直撃。

#### Mew 適用

新 skill file：

```
.codex/skills/mew-adversarial-verifier/SKILL.md
```

内容：
- verificationAgent.ts の prompt を mew context に翻訳
- mew M5 loop の verification phase で起動
- "tests pass" + "adversarial probe 1 つ通過" を no-rescue の条件に

実装規模: **~50-100 LOC（skill markdown 1 ファイル + hook コード少量）**

#### 期待効果

Rescue rate **30-50% 減**。5 連続 no-rescue 到達が現実的に。M5 Done-when 達成時期が 1 週間以上短縮。

---

### 1.2 Guardian Assessment + Approval Cache

#### 出典
`references/fresh-cli/codex/codex-rs/execpolicy/src/lib.rs`（verified）
`references/fresh-cli/codex/codex-rs/protocol/src/approvals.rs`（earlier report より verified）

#### 仕組み
2 段階承認：
1. **Execution policy**（static rules）がコマンド pattern を match
2. 分からなければ **Guardian**（LLM-based risk classifier）にエスカレーション
3. 結果を cache：`GuardianAssessmentEvent` + `GuardianRiskLevel`
4. 同じ pattern の次回は cached decision で自動処理

#### なぜ M5 に効くか

M5 Done-when: "human intervention is mostly approval, redirection, or product judgment"。

「**毎回 approval を求める**」では達成できない。「**過去に approve された pattern は自動**」が要る。Guardian cache はそれ。

#### Mew 適用

```python
# src/mew/guardian.py (新規、~300-500 LOC)

@dataclass
class GuardianVerdict:
    risk_level: Literal["safe", "review", "block"]
    reason: str
    cached: bool
    feature_vector: dict

def assess_action(action: Action, context: Context) -> GuardianVerdict:
    # 1. Static policy → early return (known safe/bad)
    # 2. Cache lookup by feature vector
    # 3. Escalate to classifier (optional LLM)
    # 4. Record decision + outcome into .mew/trust_ledger.jsonl
    ...

def update_ledger(verdict, actual_outcome):
    # verification passed / rollback / failure → verdict の正誤記録
    # 誤判定が蓄積したら threshold 調整
    ...
```

合わせて `.mew/trust_ledger.jsonl`（私が前 REVIEW で提案した shadow ledger の実装版）。

#### 期待効果

Approval ceremony 激減 → loop が速く回る。M5 の "human mostly approval" が**単位時間あたり decision 密度を下げて**達成しやすい。

---

### 1.3 Hook-based Safety Boundaries

#### 出典
`references/fresh-cli/claude-code/src/utils/hooks/`（directory 存在、詳細 earlier report）

#### 仕組み
settings.json に declarative hook：
```json
{"event": "pre_tool_use", "tool": "edit_file",
 "if": "src/mew/**", "command": "check_paired_test.py"}
```

Tool 実行 / turn 終了 / error 等のタイミングで**data-driven に介入**。

#### なぜ M5 に効くか

M5 の safety boundaries（ROADMAP.md at `1bd45fe`）：
- no autonomous push / merge / PR
- no autonomous governance edits
- no bypass of gates

これらは**現状 prompt 文で表現**。Model が prompt を無視するリスク常にある。  
**Hook は code 直下で強制**するので迂回不可能。

#### Mew 適用

```toml
# .mew/m5_safety_hooks.toml
[[hook]]
event = "pre_tool_use"
tool = "run_command"
if_regex = "^git (push|merge|commit --amend|reset --hard)$"
behavior = "block"
reason = "M5 safety: no external side effects"

[[hook]]
event = "pre_edit"
path_glob = "ROADMAP*.md"
behavior = "require_human"
reason = "M5 safety: no autonomous governance edits"

[[hook]]
event = "pre_edit"
path_glob = ".codex/skills/mew-product-evaluator/*"
behavior = "require_human"
reason = "M5 safety: no self-modifying evaluator"
```

実装規模: 200-400 LOC（hook engine + 初期 config）。

#### 期待効果

M5 safety boundaries が**機械的強制**。prompt に頼らない。**M5 Done-when の safety-loop 条件が confident に満たせる**。

---

### 1.4 PlanAgent + Plan Mode

#### 出典
`references/fresh-cli/claude-code/src/tools/AgentTool/built-in/planAgent.ts`（verified）
`references/fresh-cli/claude-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts`（verified）

#### 仕組み
**Plan mode** = "書けるが execute しない" モード：
- Model が plan を出力（tool spec / steps / risk notes）
- Approval gate
- Approve → plan を execute phase で順次実行
- Reject → plan 書き直し

#### なぜ M5 に効くか

M5 の rescue の 2 番目の type：**implementer が迷走する**。

Plan mode だと：
1. Plan 段階で**全体像**が評価される（cheaper review）
2. Implementation は plan に**anchored**、迷走しにくい
3. Plan vs outcome の diff が audit material

#### Mew 適用

```python
# src/mew/plan_mode.py (新規、~400-600 LOC)

@dataclass
class ImplementationPlan:
    task_id: str
    steps: list[PlanStep]
    risk_notes: list[str]
    expected_verification: str
    estimated_tool_calls: int

def enter_plan_mode(task) -> ImplementationPlan:
    # M5 evaluator が pick した task に対し、plan のみ生成
    # 全 tool は read-only、write は deferred
    ...

def review_plan(plan, auto_approve_threshold=...) -> PlanVerdict:
    # Guardian 経由で risk assess
    # auto-approve or human review
    ...

def execute_plan(plan, verdict) -> ExecutionOutcome:
    # Approved plan を順次実行
    # 途中で plan 逸脱したら escalate
    ...
```

#### 期待効果

M5 loop の筋が通る。途中 rescue 減。**plan vs outcome diff が M5 audit の核**になる。

---

### 1.5 Sub-Agent Spawning（Agent Tool）

#### 出典
`references/fresh-cli/claude-code/src/tools/AgentTool/`（directory 全体、verified）
- `loadAgentsDir.ts` — agent frontmatter 解釈
- `agentMemorySnapshot.ts` — state 継承
- `agentColorManager.ts`、`agentDisplay.ts` — 識別

#### 仕組み
Meta-agent が**別 context / 権限 / memory の sub-agent を spawn**：
- Isolation（独立 context）
- Fresh-eye review（bias 回避）
- Parallel execution 可能

#### なぜ M5 に効くか

現状の M5 loop は**同一 session** で evaluator → implementer → verifier が流れる。context が染まると自己正当化 bias が出る。

Sub-agent spawning なら：
```
Controller
  ├─ [evaluator] independently picks task
  ├─ [planner]   independently writes plan
  ├─ [implementer] executes plan
  └─ [adversarial verifier] independently tries to break
```

Verifier が「implementer と同じ context」でないので**不都合な結論**を出しやすい。

#### Mew 適用

```python
# src/mew/subagent.py (新規、~500-800 LOC)

@dataclass
class SubAgentHandle:
    id: str
    role: Literal["evaluator", "planner", "implementer", "verifier"]
    permission_context: PermissionContext   # frozen copy
    memory_scope: MemoryScope               # isolated slice
    inbox: Mailbox

def spawn(role, parent_ctx, memory_refs) -> SubAgentHandle: ...
def collect(handle) -> SubAgentResult: ...
```

実装規模大。M5 stabilized 後 or M6 並行推奨。

#### 期待効果

Self-justification bias 除去。**M5 audit が objective** になる。rescue 判定の信頼度 up。

---

## 2. 優先順位と timing

| 順 | Pattern | LOC | Timing | M5 impact |
|---|---|---|---|---|
| **1** | **Adversarial Verifier** | **50-100** | **今週** | **極大** |
| 2 | Guardian + Approval Cache | 300-500 | 来週（M5 active 中）| 大 |
| 3 | Hook-based Safety | 200-400 | 来週（並行可）| 大 |
| 4 | Plan Mode | 400-600 | M5 active 後半 | 中-大 |
| 5 | Sub-Agent Spawning | 500-800 | M5 stabilized 後 or M6 並行 | 中 |

## 3. Pattern 1 の即時実装案（今日〜明日）

**最速 landing 可能**なので詳細：

### 3.1 Skill ファイル

`.codex/skills/mew-adversarial-verifier/SKILL.md`（新規、50-80 行）：

```markdown
---
name: mew-adversarial-verifier
type: skill
---

## Purpose

You are NOT verifying that the implementation works.
You are trying to BREAK or embarrass it.

If all your checks are 'tests pass' or 'returns 200', you have
confirmed the happy path, not verified correctness. Go back and
try to break something.

## Two documented failure patterns

1. Verification avoidance: you find reasons not to run it — you
   read code, narrate what you would test, write 'PASS,' and move on.
   Recognize this urge. Run the command.

2. Being seduced by the first 80%: test suite passes, UI looks clean.
   But half the buttons may do nothing, state may vanish on refresh,
   errors may crash on bad input. The last 20% is where your value is.

## Required checks for mew self-improve loops

- The paired-test relationship: did src/** edit have a corresponding
  tests/** edit, and did both pass verification together?
- The recovery path: is the change reversible if mid-execution failure
  occurs? Check for snapshot/rollback coverage.
- The audit trail: is every effect journaled with outcome?
- Adversarial probes (pick 1+ that fits the change):
  - boundary values (0, -1, empty, huge inputs)
  - idempotency (run the change twice, is the second a no-op?)
  - orphan state (what if an earlier turn left a partial state?)
  - interrupt during write (does snapshot path work?)
  - concurrency (if two sessions update, does last-write-win avoid corruption?)

## Before issuing PASS

Your report must include at least one adversarial probe you ran
and its result — even if the result was "handled correctly."

## Before issuing FAIL

Check you haven't missed why it's actually fine:
- Already handled elsewhere (defensive code upstream)?
- Intentional (ROADMAP / notes explain)?
- Not actionable (real but unfixable)?

## Output shape

```json
{
  "status": "pass" | "fail",
  "adversarial_probes_run": [...],
  "missed_risks": [...],
  "recommendation": "..."
}
```
```

### 3.2 M5 loop への組み込み

現在の M5 audit 生成 (`6aeaf88 Seed M5 self-improve audit bundles`) の verification phase で：

```python
# src/mew/self_improve.py (既存拡張想定) or new m5_verify.py
def verify_loop_outcome(loop_id, implementation_artifacts):
    # 既存: tests pass check
    basic_check = run_verification_command(...)
    
    # NEW: adversarial verifier を起動
    adv_result = invoke_skill("mew-adversarial-verifier", 
                              context=implementation_artifacts)
    
    if basic_check.passed and adv_result.status == "pass":
        return LoopClassification.NO_RESCUE
    elif basic_check.passed and adv_result.status == "fail":
        return LoopClassification.RESCUE_NEEDED_FOR_DEEP_BUG
    # ...
```

### 3.3 No-rescue 条件の更新

`rescue vs no-rescue` 判定で「**adversarial verifier も pass**」を要件に追加：

```
no-rescue = 
  basic tests pass
  AND adversarial probes pass (≥1 実施)
  AND no human edits during the loop
  AND approved tool calls only
```

### 3.4 実装時間

- Skill ファイル 作成: 15-20 分
- Loop 組み込み: 30-45 分
- 初回 dogfood test: 15-30 分
- **合計: 1-2 時間で landing**

---

## 4. 段階的採用 roadmap

### Stage A（今日〜明日）: Pattern #1 のみ
- Adversarial Verifier skill + loop 組み込み
- 1-2 時間実装、即 dogfood
- **M5 5-loop 連続達成の確率 +30-50%**

### Stage B（来週、M5 active 中）: Pattern #2 + #3
- Guardian + Approval Cache
- Hook-based Safety
- 合計 500-900 LOC、1-2 日実装
- **M5 safety confident、approval ceremony 激減**

### Stage C（M5 active 後半）: Pattern #4
- Plan Mode
- 400-600 LOC
- M5 loop の筋が通る

### Stage D（M5 stabilized 後）: Pattern #5
- Sub-Agent Spawning
- 500-800 LOC
- Bias 除去、objective audit

---

## 5. Risk / Caveat

### A. Adversarial verifier が厳しすぎる

"何でも破ろうとする" verifier は**false positive**（実は問題ない）を出す可能性。

**対策**:
- "Before issuing FAIL" セクション（既に prompt に含む）で fine-grained 判定
- M5 audit で false positive も記録、パラメータ調整材料に

### B. Guardian の classifier 精度

LLM-based classifier が誤判定する可能性。

**対策**:
- Static policy を前に置く（明らかに safe / bad は LLM 呼ばない）
- Cache 運用で精度を累積的に改善
- 誤判定 outcome を明示記録、後日 rule へ昇格

### C. Hook の combinatorial explosion

Hook が増えすぎると conflict や deadlock。

**対策**:
- hook 優先順位を明示（block > require_human > command > log）
- conflict detector を付ける

### D. Plan mode の overhead

毎 loop 毎に plan phase を挟むと遅くなる。

**対策**:
- Plan mode は「複数 step task」のみに適用、1 action task は skip
- Auto-approve threshold を設定

### E. Sub-agent の context duplication cost

Spawn するたびに context を load すると API cost 増大。

**対策**:
- Stateless sub-agent にして context reuse
- Snapshot-based fork（claude-code の `agentMemorySnapshot.ts` パターン）

---

## 6. 私が間違っている可能性

1. **Adversarial verifier が 1 番目は本当か**: Guardian + cache が先かもしれない（approval ceremony 減が M5 Done-when に直撃）。user 判断で入れ替え可
2. **VerificationAgent の prompt を skill に翻訳した時の loss**: 原文は claude-code の特定 tool set 前提。mew context 用に書き直す際、本質を失わない確認が要る
3. **現 mew self-improve の verification layer との重複**: 既に何らかの verification はあるはず。重複/競合の確認が要る
4. **Implementation 規模 50-100 LOC の楽観度**: skill ファイル + loop hook 少量で可能と書いたが、実地で 200-300 LOC 要るかもしれない
5. **5 パターンの依存関係**: Plan Mode と Sub-Agent Spawning は互いに相乗効果が大きい。片方だけだと効果薄の可能性
6. **M5 Done-when との整合**: 私の解釈が ROADMAP の文言と微妙にズレる可能性あり。実装 agent が ROADMAP.md を一次とする

これらは実装 agent が現場判断で優先。本 review は方向のみ。

---

## 7. Integration with current M5 work

現 M5 audit infrastructure（直近 commits）との接続：

| 既存 artifact | 本 review の拡張 |
|---|---|
| `6aeaf88 Seed M5 self-improve audit bundles` | audit bundle に `adversarial_verifier_result` field 追加 |
| `7bf7d9b Classify rescued self-improve loops` | 分類に "rescued_by_adversarial_verifier" を追加 |
| `3174c85 Record first M5 no-rescue candidate` | 同じ no-rescue 判定に adversarial probe を要件化 |
| `a70d21e Aggregate M5 audit across task sessions` | 集計で adversarial pass rate を時系列追跡 |

**既存作業を壊さず、各 commit の延長として各 pattern を織り込める**。

---

## 8. TL;DR

```
M5 が active、初の no-rescue candidate 記録済み。
5 連続 no-rescue 達成には rescue rate を構造的に下げる要あり。

Reference patterns 5 つ:
  1. Adversarial VerificationAgent (claude-code)       ← 今週実装推奨
     50-100 LOC、rescue rate -30-50%
  2. Guardian + Approval Cache (codex)                 ← 来週
     300-500 LOC、approval ceremony 削減
  3. Hook-based Safety (claude-code)                   ← 来週
     200-400 LOC、safety boundary 機械強制
  4. Plan Mode + PlanAgent (claude-code)               ← M5 active 後半
     400-600 LOC、implementation 筋通し
  5. Sub-Agent Spawning (claude-code)                  ← M5 stabilized 後
     500-800 LOC、bias 除去

最速 impact: #1 Adversarial Verifier
  - 1 skill ファイル + small loop 組み込み
  - 1-2 時間で landing
  - M5 5-loop no-rescue 達成確率 +30-50%
  - 今日中 or 明日実装推奨
```

**今すぐ着手するなら**: `.codex/skills/mew-adversarial-verifier/SKILL.md` を書いて、次の M5 audit loop でそれを呼ぶ hook を足す。この 1 commit で M5 Done-when 達成時期が大きく早まる見込み。

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 16:30 JST
**Context**: commit `a70d21e`, 1109 commits observed, M4 done at `97236e4`, M5 active, first no-rescue candidate at `3174c85`
**Trigger**: M5 active 化 + rescue rate 下げる需要の特定
**Related**: `docs/ADOPT_FROM_REFERENCES.md` (5.4 interrupt behavior, 5.10 hooks, 5.11 snapshot と部分重複), `docs/REVIEW_2026-04-20_M6_REFRAMING.md` (Human IF との並行)
**Conversation trace**: Claude Code session (single session, no memory between runs)
