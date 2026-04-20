# REVIEW 2026-04-20 — M6 Proposal: Cross-Project Inhabitation

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）および ROADMAP maintainer
**位置付け**: **意見**。ROADMAP.md への追加提案（本 review は直接 ROADMAP.md を変更しない、agent/user の判断で採用）
**生成条件**: 2026-04-20 11:00 JST 以降、commit `6348948` 時点、1060 commits 観測後
**関連**:
- `ROADMAP.md`（M1-M5 を拡張する提案）
- `docs/REVIEW_2026-04-19_STRUCTURAL_TIMING.md`（structural timing 原則と整合）
- `docs/REVIEW_2026-04-19_REFACTOR_CADENCE.md`（complexity control と整合）

---

## 0. 動機

本日の対話で発見された ROADMAP の構造的 gap：

- **Multi-project 対応**：`ROADMAP.md` に一切記述なし（"user preference memory" の hint のみ）
- **Daemon mode**：`ROADMAP.md` に一切記述なし（"file watcher" の hint のみ）

どちらも Level 3 Self-Hosting leverage（先日の対話で分析）に必要な要素だが、**公式 milestone に存在しない**ため、evaluator skill の discipline（"exactly one active milestone"）が厳密に機能する限り**自律的には実装されない**。

### なぜ今**新 milestone として分離**するか

user 指摘の通り、**M1-M5 は「単一プロジェクト内での inhabitation」の coherent arc**。ここに multi-project / daemon を**混ぜると複雑度が制御不能**になる：

- M3 target が既に 14+ 項目で最大。ここに multi-project を足すと M3 が重くなり closure 困難
- M5（self-improving）に載せると self-improvement と cross-project 両方が曖昧に進む
- 複数の **関心軸**（persistence vs spanning）を同一 milestone で扱うと dogfood 評価が困難

**分離された M6 として扱えば**：
- M1-M5 の coherent arc を崩さず完了できる
- evaluator skill が M6 を独立 active milestone として切り替えられる
- complexity 債 が milestone 境界で明示される

これは complexity control の観点で**明確に優れた構造**。

---

## 1. M6 の scope 定義

### M6 で扱うもの
- User-scoped memory（`~/.mew/` が project-local `.mew/` と並存）
- Scope 3 軸 taxonomy（user / project / local、claude-code 互換）
- Daemon mode（OS 統合：systemd / launchd / background process）
- Cross-project file watcher / git watcher
- Unified mew identity across projects（同一 user の mew は 1 人の住人）
- Project 切替の fast-path

### M6 で扱わない（明示的除外）
- **Multi-user / team scope**: 別 concern、M7 以降 or 別系統
- **Cloud sync / remote state**: local-first 維持
- **Mobile apps / GUI**: 別 deliverable（mew-desk 拡張と混同しない）
- **Agent hierarchy（manager-of-managers）**: M5 の延長線上ではない

### M3 との境界（重要）

現行 M3 target "file watcher or git watcher for passive observation" は：
- **M3 のまま**：**in-project** の file watcher（`.mew/` のあるプロジェクト内の監視）
- **M6 が拡張**：**cross-project** の file watcher（daemon が複数プロジェクトを同時に見る）

M3 の file watcher が入れば、M6 での拡張は「**daemon が複数の watcher を hold する**」という薄い上乗せで済む。

## 2. 提案する ROADMAP.md への追記テキスト

以下を `ROADMAP.md` の `## Milestone 5: Self-Improving Mew` と `## Non-Negotiable Safety Requirements` の間に挿入する：

```markdown
## Milestone 6: Cross-Project Inhabitation

Let a single resident mew span multiple projects without losing identity.

Target:

- user-scoped memory at `~/.mew/` alongside project-scoped `.mew/`:
  - user preferences
  - user self-memory (traits, style, communication cues)
  - user feedback rules learned across projects
- scope taxonomy in recall and resume:
  - `user` scope (always relevant)
  - `project` scope (current workspace)
  - `local` scope (ephemeral, per-session)
- daemon mode:
  - `mew daemon start` / `mew daemon stop` / `mew daemon status`
  - OS integration (systemd user service on Linux, launchd on macOS)
  - survives terminal close, sleep, and reboot
- cross-project passive observation:
  - daemon watches multiple registered projects
  - file watcher / git watcher per project
  - user-visible switching without context loss
- unified identity:
  - same user's mew in project A and project B knows the same preferences,
    self-memory, and traits
  - project-specific facts stay in project scope
- project registry:
  - `mew project add <path>` / `mew project list` / `mew project focus <name>`
  - daemon knows which projects to observe

Done when:

- a user preference stated in project A is recalled correctly when working in
  project B, without manual re-teaching
- mew survives terminal close, OS sleep, and reboot, and reattaches without
  losing active work
- switching between registered projects is faster than explaining context to
  a fresh coding CLI in each project
- a comparative dogfood proves cross-project mew preferred over fresh CLI in
  a realistic multi-project task sequence
```

## 3. 提案する ROADMAP_STATUS.md への追記テキスト

M5 section の後ろに以下を追加：

```markdown
## Milestone 6: Cross-Project Inhabitation

Status: `deferred`（M5 close まで未着手）

Evidence:

- `src/mew/config.py:5` defines `STATE_DIR = Path(".mew")` as cwd-relative,
  so every project gets an independent `.mew/`.
- `src/mew/typed_memory.py` has `--scope` field but currently only handles
  `private` / `team`; no `user` / `project` / `local` split yet.
- `mew start` exists as a foreground wrapper over `mew run`; there is no
  daemon mode, systemd / launchd integration, or background-persisting
  runtime.
- `docs/REVIEW_2026-04-20_M6_PROPOSAL.md` motivates this milestone and
  describes the scope boundary with M3 / M5.

Missing proof:

- No user-scope memory surface.
- No daemon or OS-integrated background runtime.
- No cross-project file watcher.
- No project registry or project-switching command.

Next action:

- Do not start M6 implementation until M5 is either closed or explicitly
  deferred. Active milestone selection rule continues to govern.
- Before opening M6 as active, add a `dogfood --scenario m6-cross-project`
  that paired-runs mew with two registered projects and records cross-project
  preference recall as evidence.
```

## 4. 依存関係と順序

```
M1 done
  ↓
M2 done
  ↓
M3 in_progress
  (required: snapshot, continuity, typed memory, in-project file watcher)
  ↓
M4 in_progress
  (required: recovery, rollback — needed for daemon stability)
  ↓
M5 foundation
  (required: self-improvement — user preferences come from learned behavior)
  ↓
M6 deferred（本提案）
```

**M6 は M5 close 後**が自然。理由：
- User preference memory は自動生成（M5）で育つのが自然。手動入力だけだと scope の意味が薄い
- Daemon は M4 recovery が固まってから。crash-loop daemon は害
- file watcher は M3 (in-project) が先に動いて、daemon が束ねる形

ただし **M6 の部分採用は可能**：
- 「**user-scope memory だけ先行**」は M3 の延長として許される
- 「**daemon だけ先行**」は M4 の延長として許される
- ただし **M6 として bundle すると discipline が保たれる**

## 5. Scope 拡張の claude-code 互換性

claude-code の AgentJsonSchema (`loadAgentsDir.ts:86`) は：
```typescript
memory: z.enum(['user', 'project', 'local']).optional()
```

この 3 軸は**そのまま mew に transportable**。M6 で scope resolver を入れる際：
- `user` → `~/.mew/memory/user/*`
- `project` → `./.mew/memory/project/*`
- `local` → in-memory or per-session（将来）

claude-code の実証された命名を使う利点：
- **他 AI tool との memory interchange** が将来できる（user preference を claude-code から import 等）
- Convention collision がない

## 6. Complexity control の観点

### M6 が単独 milestone であるべき理由

**Option A**: M3 に multi-project を足す → M3 target が 17+ 項目、Done-when が 4+ 個に肥大

**Option B**: M5 に混ぜる → self-improvement と cross-project が絡んで dogfood 評価が困難

**Option C**（推奨）: M6 として分離 → **scope 明確、Done-when 精緻、dogfood 専用 scenario**

### Complexity budget

M6 の推定実装規模（ADOPT の類似 skeleton を元に）：

| 項目 | 概算 LOC |
|---|---|
| `~/.mew/` state resolver | 200-300 |
| Scope taxonomy in typed_memory | 150-250 |
| Daemon mode (launchd / systemd / raw) | 400-600 |
| Project registry | 200-300 |
| Cross-project file watcher | 300-500 |
| Scope-aware recall | 200-300 |
| M6 dogfood scenarios | 400-600 |
| **合計** | **~1,850-2,850 LOC** |

**実装時間**: 現 velocity (~350 LOC/hour feature) で純実装 **5-8 時間**。dogfood 込みで **2-3 日**。

---

## 7. M5 との関係

M5（Self-Improving）で user preference memory が自動生成される想定：

- Resident が feedback ("stop summarizing", "prefer diffs") を**自動で user scope に昇格**
- Cross-project で使える preference は **user scope に書き込まれる**
- Project-specific fact は **project scope に留まる**

**M5 が動いていないと M6 の user preference に入れる material が乏しい**。これは M6 を M5 後に置く実質的理由。

## 8. 初期 dogfood scenario の提案

M6 を active にする前に、**dogfood scenario を先行実装**することを推奨（M2 で m2-comparative を先に作った pattern）：

```python
# src/mew/dogfood.py に追加
def run_m6_cross_project_scenario(...):
    """
    Two workspaces: /tmp/mew-m6-project-A, /tmp/mew-m6-project-B
    
    1. In A: mew memory --add --scope user --type feedback
       "don't summarize at end of responses"
    2. Start daemon observing both A and B
    3. Switch to B: mew focus in /tmp/.../B
    4. In B: mew work with a small task
    5. Verify: resident prompt contains the user feedback from A
    6. Verify: project facts of A don't leak into B
    """
```

これが pass する状態 = M6 の最初の proof。

## 9. 実施 timing の推奨

### Option 1: M5 close 直後
M5 が formal close 後、自然な順序で M6 を active に。

**見込み**: 今の pace なら **1-2 週間後**。

### Option 2: M5 が長引きそうなら部分先行
M5 closure が見えにくい場合：
- `~/.mew/` user scope を M3 拡張として先行（M5 待たず）
- daemon は M4 closure 後に先行
- 完全な M6 active は M5 後
- 本番宣言は M5 close に合わせる

### Option 3: 凍結（M5 close まで完全に触らない）
最も disciplined。M6 文書は残すが実装はしない。evaluator skill は M3-M5 に集中。

**推奨: Option 1**。evaluator skill が milestone gate を厳守しているので、自然な順序で進めるのが一番リスク低い。

## 10. Risks / considerations

### A. Project registry の security
複数プロジェクトを daemon が見る = 各プロジェクトへの file system access が 1 点に集中。セキュリティ境界を明確に。

### B. user-scope memory の staleness
A で学んだ preference が B で古い可能性（1 年前の好みが今と違う）。age-aware decay が必要かも。M5 と相互作用。

### C. Daemon crash recovery
Daemon が crash したら複数プロジェクトの state が不整合に。M4 recovery の extension が必要。

### D. scope collision
`user` と `project` の scope で同じ key（例：`editor_preference`）があった時の優先順位。推奨：**project override user**。

### E. Cross-platform
systemd (Linux) vs launchd (macOS) vs Windows。mew は macOS 中心で開発、Linux は Docker で確認、Windows は未対応。M6 で初めて WSL 対応を真剣に考える必要あり。

---

## 11. 既存 review との integration

| Review | M6 との関係 |
|---|---|
| `REVIEW_2026-04-19_STRUCTURAL_TIMING.md` | structural items の timing 原則に整合。M6 も「準備は早めに、実装は signal 待ち」 |
| `REVIEW_2026-04-19_REFACTOR_CADENCE.md` | M6 実装中も refactor cadence は有効。commands.py の爆発防止 |
| `REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md` | M2 は close、参照のみ |
| `REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md` | M6 の multi-day proof でも dilation 活用可能 |
| `REVIEW_2026-04-20_M3_PROOF_ISOLATION.md` | M6 の daemon proof は Docker / VPS で長時間走らせるのが自然 |

**M6 は既存 proposal を無効化しない**。むしろ daemon の long-running proof は REVIEW 3 つの総合応用になる。

---

## 12. 私が間違っている可能性

1. **scope taxonomy の 3 軸**: `user / project / local` が claude-code 互換だが、mew 独自の語彙（例：`resident / workspace / transient`）の方が良い可能性
2. **Daemon 実装の OS 選択**: launchd / systemd を先に、Docker で Linux も covered。Windows 優先度は低いが、user 次第
3. **M5 依存の強さ**: user preference が M5 自動生成に依存と書いたが、手動 add だけでも M6 は機能し得る。依存を弱めて M5 と並行可能かもしれない
4. **Implementation 順序**: M6 target の中で何を先にやるかの細部は agent の現場判断
5. **M6 の timing**: M5 close まで deferred が保守的か、M3-M5 が安定した瞬間に部分先行すべきか
6. **Done-when の具体性**: "faster than fresh CLI" を定量化する axes を先に定義する必要（M2/M3 と同じ discipline）

これらは実装 agent と user が現場判断で優先。本 review は方向のみ。

---

## 13. 採用判断

本 review を採用するなら、以下 2 step：

### Step 1: ROADMAP.md に M6 section を追加
§2 のテキストをそのまま挿入。これで evaluator skill が M6 を認識するようになる。

### Step 2: ROADMAP_STATUS.md に M6 status = `deferred` を記録
§3 のテキストを追加。active milestone ではないことを明示。

これで M5 close まで M6 は**触られない**が、**認識されている**状態になる。M5 close 時に自然に active に昇格。

---

## 14. TL;DR

```
現 ROADMAP (M1-M5):
  - Single-project inhabitation の coherent arc
  - Multi-project / daemon の計画なし
  
提案: M6 Cross-Project Inhabitation を追加
  - ~/.mew/ user scope
  - daemon mode (systemd / launchd)
  - cross-project file watcher
  - unified identity
  
理由:
  - M3 に混ぜると target 肥大
  - M5 に混ぜると self-improvement と絡む
  - 独立 milestone で complexity 境界明確
  
順序: M5 close 直後に active 化（1-2 週間後）
規模: 1,850-2,850 LOC、実装 5-8h、dogfood 込み 2-3 日

採用方法:
  1. ROADMAP.md に §2 のテキストを挿入
  2. ROADMAP_STATUS.md に §3 のテキストを追加
  3. M5 close まで deferred のまま放置
```

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 11:00 JST
**Context**: commit `6348948`, 1060 commits observed, M2 done, M3 in_progress ~80, M4 in_progress, M5 foundation
**Related**: `ROADMAP.md` M5 末尾に追加想定、全 M1-M5 を拡張する new milestone 提案
**Conversation trace**: Claude Code session (single session, no memory between runs)
