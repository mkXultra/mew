# REVIEW 2026-04-20 — M6 Reframing: Human-Legible Interface

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）および ROADMAP maintainer
**位置付け**: 意見。ROADMAP への追加提案（本 review は直接 ROADMAP.md を変更しない、採用は agent/user の判断）
**生成条件**: 2026-04-20 14:15 JST 以降、commit `9137d6f` 時点、1076 commits 観測後
**前提**: 先の `docs/REVIEW_2026-04-20_M6_PROPOSAL.md`（Cross-Project Inhabitation 提案）を**revise**し、Human-Legible Interface を新 M6、Cross-Project を M7 に再編する

**関連**:
- `docs/REVIEW_2026-04-20_M6_PROPOSAL.md`（前提 M6 提案、本提案で M7 に降格）
- `ROADMAP.md`（M1-M5）
- `docs/REVIEW_2026-04-19_STRUCTURAL_TIMING.md`（structural timing 原則）

---

## 0. 動機：実体験から判明した product gap

2026-04-20 午後、application 用 demo GIF を 2 回作成を試みた：

| 試行 | tool chain | 結果 |
|---|---|---|
| 1 回目（codex-ultra 生成）| `mew work --tool read_file ...` 系 CLI flag | user: 「意味不明」 |
| 2 回目（手作業 narrative 強化）| `mew chat` + `/focus` / `/show` / `/work-session resume` | user: 「何を操作しているかも不明」 |

2 回とも、**mew のコア value（durable state / continuity）が非 mew ユーザーに伝わらない**ことが判明した。

これは demo 設計の問題ではなく、**product の IF gap**：

- mew の output は `continuity: 9/9`、`working_memory`、`active_memory` 等の structured dense data
- mew ユーザーには宝物、非 mew ユーザーには「何かの data」
- **internal state が中心のツールを external に伝える手段がない**

Cursor / Claude Code の demo が成立するのは、code 変更が visible だから。mew の命は invisible。

---

## 1. 提案する milestone 再編

### Before（現 ROADMAP + 前回 review）
```
M1 Native Hands        done
M2 Interactive Parity  done
M3 Persistent Advantage in_progress
M4 True Recovery       in_progress
M5 Self-Improving      foundation
M6 Cross-Project       deferred（前 REVIEW 提案）
```

### After（本 review 提案）
```
M1 Native Hands            done
M2 Interactive Parity      done
M3 Persistent Advantage    in_progress
M4 True Recovery           in_progress
M5 Self-Improving          foundation
M6 Human-Legible Interface deferred（本 review 提案、新規）
M7 Cross-Project           deferred（前 M6 を降格）
```

Cross-Project は**依然必要**だが、**優先度では Human IF の下**。

---

## 2. M6: Human-Legible Interface とは

### Scope 定義

「**mew の internal state を non-mew-user にも legible な外部表現に変換する layer**」。

### 扱うもの
- Plain-English / Plain-Japanese narrative output
- Onboarding flow（`mew introduce` 的な）
- Share-able single-screen summary
- Human-readable error messages with actionable hints
- State diff visualization（before/after 中断）
- Demo-worthy reproducible scenarios
- Documentation structure が user journey を追う

### 扱わないもの
- multi-project（M7）
- daemon / OS integration（M7）
- 完全な GUI（別 deliverable）
- mobile apps（out of scope）
- voice UI（out of scope）

---

## 3. 提案する ROADMAP.md 追記テキスト

以下を `## Milestone 5: Self-Improving Mew` と `## Non-Negotiable Safety Requirements` の間に挿入：

```markdown
## Milestone 6: Human-Legible Interface

Make mew's durable state legible to people who have never used mew.

Target:

- plain-language narrative output:
  - `mew next` returns a sentence, not a dense structure
    (e.g., "You were fixing add_numbers for negatives. Last touched
    tests/test_add_numbers.py. Try handling negative inputs next.")
  - every top-level command offers a `--narrative` or default-narrative
    mode that reads like a note to your future self
  - dense structured output stays available via `--json` or `--raw`
- onboarding surface:
  - `mew introduce` or an equivalent first-run explanation that finishes
    in under 30 seconds
  - a default `mew focus` that is understandable without prior docs
- shareable single-screen summary:
  - a command that produces a screenshot-worthy 20-30 line summary of
    the current resident state, suitable for pasting in a chat or blog
  - the summary is self-contained: it does not require external context
- actionable error messages:
  - every mew error explains what happened and offers at least one
    concrete next command to try
  - "silent no-op" states are visible
- state-diff visualization:
  - `mew diff <hours|sessions>` or similar surface that shows what
    changed between two points in time in mew's perspective
- demo-worthy scenarios:
  - at least two reproducible demo scenarios that are self-explanatory
    in a 30-60 second terminal capture without voice-over
- documentation structure:
  - README leads with the user journey, not with implementation
  - getting-started path lands a new user on a working mew in under
    5 minutes

Entry gate:

- Milestone 3 is done so there is rich durable state worth surfacing
- Milestone 4 is substantially progressing so legibility is not built
  on shaky recovery
- Milestone 5 can run in parallel because self-improvement produces
  the audit material that Human-Legible Interface surfaces

Done when:

- a person who has never used mew can say, after 30 seconds of watching
  a recorded demo, what mew is doing and why it is different from
  other CLIs
- the self-test passes: a demo GIF of 30-60 seconds, recorded from a
  single tape script, is self-explanatory to a non-mew-user on the
  first viewing without narration
- the README shows a new user the "why now" value in under 2 minutes
- at least 80% of user-visible error messages include at least one
  concrete next command
- shareable single-screen summaries exist for focus, brief, resume,
  and work-session close

M6-specific safety boundaries:

- narrative output must never fabricate facts. if working memory is
  missing, narrative says so rather than inventing
- marketing-style language is not allowed. plain, specific, and honest
- onboarding must not lower any safety gate for the user's convenience
```

---

## 4. 提案する ROADMAP_STATUS.md 追記テキスト

```markdown
## Milestone 6: Human-Legible Interface

Status: `deferred`（M5 の entry gate 側と並行整理、Primary active は M5 後）

Evidence:

- `docs/REVIEW_2026-04-20_M6_REFRAMING.md` motivates this milestone. The
  2026-04-20 demo-GIF failure (two attempts, both reported illegible by
  non-mew reviewer) is the concrete trigger.
- Existing surfaces that already lean "legible": `mew focus`, `mew brief`,
  `mew daily`, mood/journal/dream artifacts. These are partial M6 material
  but not yet pass the 30-second-legibility self-test.
- Existing surfaces that are dense / mew-user-only: `/work-session resume`,
  `mew memory --active --json`, full effect journal, raw state bundles.

Missing proof:

- No demo GIF of 30-60 seconds has yet survived review from a non-mew
  reader on the first viewing.
- No `--narrative` mode exists as a uniform convention.
- No `mew introduce` / onboarding command exists.
- No screenshot-worthy single-screen summary convention exists.
- README leads with implementation detail, not user journey.

Next action:

- Do not start M6 implementation until M5 entry gate is met. Active milestone
  selection rule continues to govern.
- Before opening M6 as active, add a `dogfood --scenario m6-legibility`
  that runs a recorded demo-scenario tape and compares a generated GIF
  against a rubric of "would a non-mew-user understand this?".
```

---

## 5. M7: Cross-Project Inhabitation（前 M6 を降格）

前回 review（`docs/REVIEW_2026-04-20_M6_PROPOSAL.md`）で提案した Cross-Project 関連すべてを **M7 として再配置**。内容は変更せず番号のみ update。

### 降格の理由

| 観点 | Human IF (新 M6) | Cross-Project (新 M7) |
|---|---|---|
| 対象 user | **全員**（潜在 adopter 含む）| power user |
| Adoption への影響 | **絶大**（最初の 30 秒で判断）| 中（multi-repo user のみ）|
| Grant 審査への影響 | **絶大**（pitch 可視化）| 小 |
| M5 closure への依存度 | 低（並行可）| 中（自己改善の audit が必要）|
| 実装規模 | 500-800 LOC（narrative 層、docs）| 1,850-2,850 LOC |
| 完成の "見える" さ | 明確（self-test がある）| 漠然 |

**Human IF は adoption の gate**。これが無いと multi-project は user がいない world で作ることになる。

---

## 6. M6 の self-test（literal）

**Done-when の検証法**：

```
1. 実装完了後、demo tape を 1 回で書く
2. `vhs demo.tape` で GIF 生成
3. mew を知らない人（友人、家族、X のフォロワー）に見せる
4. "何をしていますか" と問う
5. 30 秒以内に「継続する AI」「覚えている」等の core を答えられるか

→ 答えられれば M6 pass
→ 答えられなければ M6 unmet
```

**今日 (2026-04-20) の GIF は literally この test に unmet**。これが milestone の存在理由。

## 7. 実装の候補アプローチ

### 7.1 Narrative mode convention

全 top-level command に `--narrative` flag：

```bash
$ mew next
{
  "active_task": {"id": 1, "title": "Fix add_numbers for negatives"},
  "last_touched": "tests/test_add_numbers.py",
  "next_step": "handle negative inputs",
  "continuity_score": "9/9"
}

$ mew next --narrative
You were fixing add_numbers for negatives. Last touched
tests/test_add_numbers.py. Try handling negative inputs next.
(continuity 9/9, 3 active memories)
```

**規則**: `--narrative` is default if no `--json` / `--raw` 指定。dense は opt-in に。

### 7.2 Onboarding surface

```bash
$ mew introduce
mew is a place where an AI remembers across sessions.

Right now mew knows:
  - 1 active coding task
  - 3 typed memories (2 project facts, 1 your preference)
  - 1 paused work session with 9/9 continuity

Try:
  mew next        ← what to work on
  mew focus       ← current state
  mew chat        ← open a conversation
```

### 7.3 Share-able summary

```bash
$ mew share
┌──────────────────────────────────────────┐
│ mew, 2026-04-20 14:30 JST                │
│                                           │
│ Active: Fix add_numbers for negatives     │
│   - Reading tests/test_add_numbers.py     │
│   - Next: handle negative inputs          │
│                                           │
│ Remembers:                                │
│   - "Prefer concise output"               │
│   - "This project uses pytest"            │
│                                           │
│ Continuity: 9/9 strong                    │
└──────────────────────────────────────────┘
Paste this in a chat, a blog, or anywhere.
```

screenshot-able 20 行以内 summary。

### 7.4 Actionable error

```bash
# Bad (現状想定)
Error: ApprovalRequired for edit_file

# Good (M6 後)
Error: This edit needs approval first.
  To approve: mew work 1 --approve-tool 12
  To reject:  mew work 1 --reject-tool 12
  To inspect: mew work 1 --session --diffs
```

### 7.5 State diff

```bash
$ mew diff --since 1h
Between 13:30 and 14:30:
  + 2 tool calls (read_file, search_text)
  + 1 session note added
  - 0 files changed
  continuity: was 7/9, now 9/9 (improved)
```

---

## 8. 参考 reference

既に存在する CLI で human-legible に成功している例：

- **Stripe CLI**: `stripe customers list --limit 3 --pretty`
- **gh CLI**: `gh pr status` (narrative output)
- **1Password CLI**: plain description + concrete actions
- **Cargo**: "Compiling X v0.1.0" は technical だが understandable

逆に mew が回避すべき anti-pattern:
- AWS CLI（raw JSON only、不親切）
- kubectl（技術者専用）
- Git の "error: Your local changes..."（何すればいいか不明）

---

## 9. M6 を M5 と並走させるべきか

**Yes, 部分並走可能**：

### M5 active 期間中に M6 prep 可能な subset
- narrative mode の convention 設計（docs only）
- `mew introduce` の skeleton
- README rewrite の outline

### M5 が終わってから着手すべき subset
- state diff（snapshot 主経路化が前提）
- demo scenario curation（M5 self-improvement で得た fail pattern を反映）
- actionable error の全面改修（recovery logic が stable であることが前提）

### 推奨 timing

```
M5 foundation (今)
  ↓ entry gate が埋まる
M5 active work
  ↓ 並行で M6 prep (docs, outlines)
M5 closed
  ↓
M6 active work (full implementation)
  ↓ self-test pass
M6 closed
  ↓
M7 Cross-Project active
```

**Total 2-3 ヶ月**で M5 → M6 → M7 chain 完了の見込み（現 velocity 前提）。

---

## 10. 実装規模の推定

### 新 M6 Human IF

| 項目 | 概算 LOC |
|---|---|
| Narrative mode convention + 各 command 対応 | 300-500 |
| `mew introduce` | 100-150 |
| Share-able summary format | 100-200 |
| Actionable error messages 全面改修 | 200-400 |
| State diff | 300-500 |
| Onboarding docs rewrite | docs only, ~300 lines markdown |
| Demo scenario curation + self-test | 200-300 |
| **合計** | **~1,200-2,050 LOC** |

純実装時間（現 velocity）: **5-7 時間**、dogfood 込み **1-2 日**。

---

## 11. Risk / Caveat

### A. Narrative の fabrication リスク
M6 で plain-English 生成する時、mew が「持っていない情報を補完」してしまう可能性。  
**対策**: narrative 生成は**機械的 template**（LLM 呼ばない）で実装。状態が空なら空と言う。

### B. "dumbing down" リスク
Narrative 化の誘惑で、**power user 向けの精密 output を失う**可能性。  
**対策**: `--json` / `--raw` の dense output を**完全維持**。narrative は layer on top、置き換えではない。

### C. Marketing drift
M6 で自己肯定的な narrative を生成しだすと**sleek な mew marketing 言語**になり、honest な technical content から遠ざかる。  
**対策**: safety boundary に "marketing-style language is not allowed" を明記。

### D. M5 self-improvement との conflict
M5 evaluator が「polish drift 検出」する rule が、M6 narrative 改善を「polish」と誤認する可能性。  
**対策**: M6 work は明示的に "non-polish"、self-test（30 秒 legibility）で pass/fail が明確、drift にはならない。

---

## 12. 私が間違っている可能性

1. **"Cross-Project より Human IF が先" の優先順**: 実は multi-project こそが adopter にとっての killer feature の可能性。user 判断が正確。
2. **Narrative mode の convention**: `--narrative` flag 付与は全 command を touch する。M5 stability と conflict するかも。
3. **Self-test の rigor**: 「非 mew ユーザーが 30 秒で分かる」は主観。test を objective にする必要がある。
4. **実装規模**: 1,200-2,050 LOC は optimistic。error message 全面改修が深い dependency を持つと膨らむ可能性。
5. **M5 との並行度**: narrative layer が self-improvement loop と干渉する可能性（evaluator が narrative を更に評価し始める等）。

これらは実装 agent の現場判断で優先。本 review は方向のみ。

---

## 13. 採用判断

本 review を採用するなら：

### Step 1: ROADMAP.md を 2 箇所 update
- §3 の M6 section を新 M6 (Human IF) で挿入
- 前 M6 提案の Cross-Project を M7 に renumber

### Step 2: ROADMAP_STATUS.md に M6 = `deferred` を記録
- 同時に M7 を書き換え（前 M6 file の参照を M7 に）

### Step 3: `docs/REVIEW_2026-04-20_M6_PROPOSAL.md` の status を update
- 「本 doc の milestone 番号は M7 に変更された」旨を先頭に追記

どれも commit 2-3 本、30 分の作業。M5 close まで実装は**しない**。

---

## 14. TL;DR

```
現 ROADMAP (M1-M5 + 前 M6 提案):
  - M1-M5 は single-user single-project の AI habitat
  - 前 M6 (Cross-Project) は multi-repo 対応

問題:
  - 2026-04-20 demo GIF 作成が 2 回失敗
  - 原因: mew の internal state を外部に伝える IF が弱い
  - これは adoption / grant / OSS 広がりの gate

提案: Milestone 再編
  M6 = Human-Legible Interface (新)
  M7 = Cross-Project (前 M6 を降格)

理由:
  - 使える → 分かる → 広がる → multi-project の順
  - Human IF なしでは adopter がゼロ
  - demo 作れない = pitch が弱い = grant 通らない

核 feature:
  - narrative mode convention
  - mew introduce (onboarding)
  - share-able summary
  - actionable errors
  - state diff
  - demo-worthy reproducible scenarios

Self-test:
  - 30 秒の demo GIF を非 mew ユーザーに見せて 
    "何してる？" と聞く → 正答できれば M6 pass

規模: 1,200-2,050 LOC, 純実装 5-7h, dogfood 込み 1-2 日
timing: M5 active 期間中に partial prep, M5 close 後に full active
```

---

## 15. この review の位置付け

- 本 review は**今日の demo 失敗から派生**した実体験ベースの gap detection
- 「M5 達成まで先送り」という現 milestone gate は**尊重**する
- 本 review は agent 採用を強制せず、**M5 close のタイミングに参照される候補**として docs/ に残る

もし agent がこの reframing を妥当と判断すれば、ROADMAP の 2 箇所 update で正式化される。妥当でないと判断すれば、docs/ に candidate として残るだけ。どちらも mew の現在作業に干渉しない。

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 14:15 JST
**Context**: commit `9137d6f`, 1076 commits observed, M2 done, M3 in_progress ~85%, M4 in_progress ~65%, M5 foundation (entry gate defined at commit `1bd45fe`)
**Trigger**: 2026-04-20 demo GIF creation failed twice, revealing product IF gap
**Related**: `docs/REVIEW_2026-04-20_M6_PROPOSAL.md` (Cross-Project, now M7), `ROADMAP.md`, `ROADMAP_STATUS.md` M5 section
**Conversation trace**: Claude Code session (single session, no memory between runs)
