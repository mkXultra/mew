# REVIEW 2026-04-20 — M3 Accelerated Proof Strategy

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。ROADMAP_STATUS の Milestone Gate rule を尊重、M3 active の下での**supporting implementation strategy**
**生成条件**: 2026-04-20 08:50 JST 以降、commit `314c997` 時点、1041 commits 観測後
**関連**:
- `docs/M3_RESIDENT_LOOP_30MIN_2026-04-20.md`（初の 30 分 cadence proof）
- `docs/REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md`（M2 pattern、今 M3 に応用）
- `ROADMAP.md` M3 Done-when / ROADMAP_STATUS "Missing proof:" section

---

## 0. 動機

M2 close 後、M3 が active milestone。M3 最大の壁は：

> ROADMAP_STATUS: "there is still no several-hour or multi-day cadence proof"

これを**暦時間そのまま**で proved にすると：
- 1 時間 cadence: 1 時間待機 × N 回
- 6 時間 cadence: 6 時間待機 × N 回
- 1 日 cadence: 24 時間 × N 回
- 1 週間 cadence: 168 時間 × N 回

**1 回の失敗で暦時間が倍増**する。実装時間は数時間で終わるのに、**実証で数日〜数週間失う**。これは velocity が落ちる典型的 bottleneck。

production システムの long-running testing では**時間を short-circuit するのが標準**。本 review は mew に同様の discipline を適用する提案。

---

## 1. 問題の分解

M3 が proved である必要があるもの（ROADMAP.md + ROADMAP_STATUS から）：

| 軸 | 何が proved される必要があるか | 時間依存度 |
|---|---|---|
| A. tick stability | passive tick が止まらず安定処理 | 低（1 時間で十分）|
| B. memory bloat 耐性 | thought journal が compact、working memory が stale 検出 | 中（24 時間相当の tick） |
| C. day-boundary rollover | journal / dream / mood の YYYY-MM-DD 切替 | **高**（日跨ぎが必須） |
| D. archive trigger | 古い session が archive される | 中（age-based eviction） |
| E. reentry fidelity | N 日後 resume で explain できる | **高**（実 N 日経過 or 合成）|
| F. memory recall after N days | 過去メモリが related 判定される | 中（関連度データ生成）|
| G. OS process stability | 実 OS で N 時間連続動作 | **高**（実時間必須）|
| H. external API TTL | Codex Web API セッション等 | **高**（実時間必須）|

**A, B, D, F は時間圧縮で十分**。C, E, G, H は一部実時間が必要だが、**大半は圧縮できる**。

---

## 2. 4 つの手法（コスパ順）

### 手法 1: **Time Dilation（時間拡張）** — 最推奨

`now_iso()` が返す時刻を実時間より速く進める。実時間 1 時間 = 論理時間 1 日、等。

**解決する軸**: A, B, C, D, F

#### 実装スケッチ

`src/mew/timeutil.py` を拡張（現在 20 LOC、+30-50 LOC で対応）：

```python
# src/mew/timeutil.py
import os
import time as _t
from datetime import datetime, timezone

_DILATION_MULTIPLIER = float(os.environ.get("MEW_TIME_DILATION", "1.0"))
_DILATION_START_REAL = _t.time()
_DILATION_START_LOGICAL = _t.time()

def enable_dilation(multiplier: float) -> None:
    """Called by dogfood at scenario start."""
    global _DILATION_MULTIPLIER, _DILATION_START_REAL, _DILATION_START_LOGICAL
    _DILATION_MULTIPLIER = multiplier
    _DILATION_START_REAL = _t.time()
    _DILATION_START_LOGICAL = _t.time()

def _now_seconds() -> float:
    if _DILATION_MULTIPLIER == 1.0:
        return _t.time()
    real_elapsed = _t.time() - _DILATION_START_REAL
    return _DILATION_START_LOGICAL + real_elapsed * _DILATION_MULTIPLIER

def now_iso() -> str:
    return datetime.fromtimestamp(_now_seconds(), tz=timezone.utc).isoformat()

def now_date_iso() -> str:
    """NEW: 日付系の直接呼び出しを置き換える用"""
    return datetime.fromtimestamp(_now_seconds(), tz=timezone.utc).date().isoformat()
```

#### CLI surface

```bash
mew dogfood --scenario resident-loop \
  --duration 3600 \          # 実時間 1 時間
  --interval 60 \            # 実時間 60s 毎に tick
  --time-dilation 24         # 論理時間は 24 倍速 = 1 日/時
```

#### 既存 scenario への追加

`src/mew/dogfood.py:919` の `run_resident_loop_scenario()` signature に `time_dilation=1.0` を追加。scenario 開始時に `timeutil.enable_dilation()` 呼ぶ。

---

### 手法 2: **Synthetic Aged State（エージング合成）**

「N 日前から動いていた状態」を人工的に作って、そこから resume できるかテスト。

**解決する軸**: E, F

#### 設計

```bash
mew dogfood --scenario aged-reentry --pretend-age 7d
```

1. 新 workspace を作る
2. `.mew/state.json` に**過去 7 日分の history を injection**：
   - `thoughts`: 100 entries、`created_at` が 7 日前〜現在に分散
   - `work_sessions`: 30 closed、様々な touched files / working_memory
   - `tasks`: 5 active、うち 2 つは 3 日放置、3 つは 1 週間放置
   - `typed_memory`: 50 entries（user 10、project 30、reference 10）
   - `effects.jsonl`: 5000 行（passive ticks、tool calls、approval events）
3. 実 `mew focus`、`mew next`、`mew work --resume` 呼ぶ
4. 以下を verify：
   - focus 表示が崩れない（stale 10 task を優先順位付け）
   - memory recall が関連メモリを引く
   - resume bundle が意味を持つ（working_memory 復元）
   - archive/compaction が正しく動く

#### 実装規模

`src/mew/dogfood.py` に scenario 追加、state fixture generator で 150-250 LOC。

---

### 手法 3: **Tick Compression（interval 短縮）**

これは手法 1 の subset：interval を 60s → 0.1s に縮めて、数分で数百 tick を流す。

**解決する軸**: A, B（時間そのものではなく tick 数で）

#### CLI（既存の extension）

```bash
mew dogfood --scenario resident-loop --duration 60 --interval 0.1
# 600 tick を 60 秒で処理
```

#### 実装規模

**ほぼゼロ**。既存の `--duration` / `--interval` をそのまま使うだけ。

### 手法 4: **Staged Proof Pyramid（段階実証）**

「multi-day を一発 proof」ではなく「**段階別 proof の積み重ね**」。手法 1-3 を組み合わせて構築。

**pyramid**:

| 段階 | 実時間 | 論理時間 | 方式 | 証明内容 | 現状 |
|---|---|---|---|---|---|
| P0: tick stability | 1 分 | 10 分 | tick compression | loop 起動 / 停止 | ✅ existing |
| P1: 30 分 cadence | 30 分 | 30 分 | real | thought flood 回避 | ✅ done (today) |
| P2: 1 時間 cadence | 1 時間 | 1 時間 | real | compaction 発動 | 🔜 |
| P3: 6 時間 cadence | 6 時間 | 6 時間 | real | archive 発動 | 🔜 |
| P4: dilated 1 日 | **1 時間** | **1 日** | dilation 24× | day-boundary / date 切替 | 🔜 新規 |
| P5: dilated 7 日 | **7 時間** | **7 日** | dilation 24× | weekly / recall after week | 🔜 新規 |
| P6: aged 7 日 reentry | **30 秒** | — | synthetic age | reentry fidelity | 🔜 新規 |
| P7: 実 1 日 cadence | **24 時間** | 1 日 | real | OS stability | 🔜（任意）|
| P8: 実 7 日 cadence | **168 時間** | 7 日 | real | real multi-day | 🔜（任意）|

**M3 close に必要なのは P0-P6**。P7-P8 は保険（close 後に running proof として走らせて構わない）。

---

## 3. 推奨する組み合わせ

**MVP（1-2 時間実装）**:

1. `timeutil.py` に dilation 30-50 LOC
2. `resident-loop` scenario に `--time-dilation` option 20 LOC
3. テスト 50 LOC（dilated time が各所で一致することを確認）

→ **P4-P5 が今日中に dogfood 可能**に。1 週間分の cadence が 7 時間で proved。

**追加（もう半日）**:

4. `aged-reentry` scenario 200-300 LOC
5. state fixture generator

→ **P6 が proved**。N 日後 reentry が 30 秒で検証可能。

**合計 2-4 時間の実装**で、**P0-P6 の pyramid が揃う = 実質 M3 long-running cadence proved**。

---

## 4. 前準備：timeutil consolidation

**これが実は最大のコスト**。現状 mew コードベースには `datetime.now()` の直接呼び出しが 7 ファイルに散在：

```
src/mew/desk.py:39            return validate_date(datetime.now().date().isoformat())
src/mew/journal.py:26         return validate_date(datetime.now().date().isoformat())
src/mew/morning_paper.py:48   return validate_date(datetime.now().date().isoformat())
src/mew/dream.py:27           return validate_date(datetime.now().date().isoformat())
src/mew/mood.py:46            return validate_date(datetime.now().date().isoformat())
src/mew/self_memory.py:26     return validate_date(datetime.now().date().isoformat())
src/mew/passive_bundle.py:46  return validate_date(datetime.now().date().isoformat())
```

**これらが dilation を無視する**ので silent mismatch が出る。

**修正**: `timeutil.py` に `now_date_iso()` を追加し、7 ファイルの直接呼び出しを置き換える。

```python
# src/mew/timeutil.py
def now_date_iso() -> str:
    return datetime.fromtimestamp(_now_seconds(), tz=timezone.utc).date().isoformat()
```

各ファイル：
```python
# before
return validate_date(datetime.now().date().isoformat())

# after
from .timeutil import now_date_iso
return validate_date(now_date_iso())
```

**規模**: 7 ファイル × 1-2 行、合計 20-30 LOC。

### runtime.py の `time.time()` について

`src/mew/runtime.py:1413, 1452, 1782` で `time.time()` 直接使用あり。これは**tick scheduling の実時間**（monotonic wall-clock）。**dilation を適用すべきではない**。

判断：
- **実 wall-clock**（sleep / scheduling / monotonic）: `time.time()` のまま
- **論理時刻**（state/effect の `created_at` / `updated_at` / age 判定）: `timeutil.now()` 経由

この区別を文書化しておく必要がある。

---

## 5. 実装順序

### Phase 0（今すぐ、30 分）

1. `timeutil.py` に `now_date_iso()` と `enable_dilation()` を追加
2. 既存 7 ファイルの `datetime.now().date().isoformat()` を `now_date_iso()` 経由に統一
3. 境界文書: runtime.py の `time.time()` は scheduling 用途で dilation 対象外、と明記

### Phase 1（30 分）

4. `dogfood.py` の `run_resident_loop_scenario()` に `time_dilation=1.0` パラメータ追加
5. scenario 開始時に `timeutil.enable_dilation(time_dilation)` 呼ぶ
6. CLI (`--time-dilation N`) 足す
7. test：dilation 有効時、`now_iso()` が実時間より N 倍速く進むこと

### Phase 2（1-2 時間）

8. P4 (dilated 1 day) 実行：`--duration 3600 --interval 60 --time-dilation 24`
9. P5 (dilated 7 day) 実行：`--duration 25200 --interval 60 --time-dilation 24`
10. 結果を `docs/M3_DILATED_WEEK_2026-04-20.md` に記録

### Phase 3（2-3 時間）

11. `aged-reentry` scenario 実装
12. state fixture generator
13. P6 proof 実行

### Phase 4（1 日、保険）

14. P7（実 1 日 cadence）を走らせる。背景で放置。
15. 結果を `docs/M3_REAL_DAY_2026-04-20.md` に記録

---

## 6. 期待される時間節約

| 従来見積もり | Accelerated 見積もり | 節約 |
|---|---|---|
| **実 1 日 proof** | 24 時間 実 | **1 時間 実 + dilation 24×** | 23 時間 |
| **実 1 週間 proof** | 168 時間 実 | **7 時間 実 + dilation 24×** | 161 時間 |
| **N 日後 reentry** | 7 日 実 | **30 秒（aged state）** | ほぼ全部 |
| **M3 close まで** | 3-5 日 | **1-2 日** | 2-3 日 |

**実装コスト 2-4 時間** vs **節約される暦時間 2-3 日**。ROI は 10-15×。

---

## 7. 落とし穴 / リスク

### A. Silent mismatch from missed time source

新しく書かれる code が `datetime.now()` を使って dilation を bypass する可能性。**pre-commit hook か lint rule** で：

```python
# scripts/check_time_source.py
# src/mew/ 内で datetime.now() / time.time() の直接呼び出しを検出
# timeutil 経由への書き換えを要求
```

### B. Subprocess は dilation 知らない

`acm run codex-ultra` 等の外部 CLI は実時間で動く。dilation を enable した dogfood 中に外部 CLI を呼ぶと：
- 外部側は real 60 秒で処理
- mew 側は logical 24 分と記録
- state の `elapsed_time` が歪む

**対処**:
- dilation 中は外部 CLI 呼び出しを避ける（dogfood scenario で explicit に）
- もしくは外部 CLI 呼び出し時だけ dilation 一時停止

### C. filesystem mtime は実時間

`.mew/` のファイルの mtime は OS 管轄で実時間。file-watcher と組み合わせたとき、dilated time と mtime が乖離する。

**対処**:
- file-watcher 系の test は dilation 非使用
- mtime 比較は `st_mtime` （real）と `now_iso()` （dilated）を分けて扱う

### D. False confidence

dilated で proved でも、実時間で動作すると silent bug が出る可能性（特に外部 API TTL、real sleep 挙動）。

**対処**:
- Pyramid P7（実 1 日）を最後に保険として必ず走らせる
- close 後も running proof として背景で continuous に走らせる（trust ledger に記録）

### E. 既存 state との互換性

state.json の `created_at` / `updated_at` が dilated なまま残ると、後続の real run で「未来の日付」として扱われ、age 判定が壊れる。

**対処**:
- dilation 有効な dogfood は **別 workspace**（`/tmp/...`）で実行
- production state に dilated timestamp が混入しない

---

## 8. 参考パターン

この種の time-manipulation test は production システムで標準：

- **claude-code**: test は vitest の `vi.useFakeTimers()` / `vi.advanceTimersByTime(ms)`
- **codex**: Rust の `tokio::time::pause()` + `tokio::time::advance()`
- **Python ecosystem**: `freezegun`, `time_machine`, `pytest-freezer`

mew は stdlib のみで実装可能（上記の簡易 dilation で十分、full freezing は不要）。

---

## 9. 検証済み事実

本 review で引用する状況：

- `src/mew/timeutil.py` 実在、20 LOC、`now_iso()` / `parse_time()` / `elapsed_hours()` 持つ
- 25 モジュールが `from .timeutil import` 経由で時刻を取得
- **7 モジュールが `datetime.now().date().isoformat()` を直接呼ぶ**（統一が必要）
- `src/mew/runtime.py:1413, 1452, 1782` が `time.time()` を scheduling に直接使用（これは意図的）
- `run_resident_loop_scenario(workspace, env=None, duration=6.0, interval=2.0, poll_interval=0.1)` at `dogfood.py:919` 既に parametrized
- Pyramid P1（30 分 cadence proof）は **既に pass**（`docs/M3_RESIDENT_LOOP_30MIN_2026-04-20.md`）

---

## 10. 私が間違っている可能性

1. **dilation 実装の細部**: 実装 agent が `timeutil.py` の実地を読んだほうが最適解が分かる。特に既存の `parse_time()` との相互作用
2. **Subprocess への影響範囲**: `acm run` / `codex-ultra` 呼び出しがどの dogfood scenario で起きるか、実地で確認が必要
3. **filesystem mtime の用途**: mew コードベースで mtime に依存している箇所がどれだけあるか未調査
4. **Phase 4 の必要性**: 実 1 日 proof を本当にやるべきか、pyramid P0-P6 で十分かは judgment
5. **Phase の時間見積もり**: 30 分 / 1-2 時間は conservative、agent の実測 velocity（350-490 LOC/hour）なら 15-60 分でも可

これらは実装 agent が現場判断で優先。本 review は方向のみ。

---

## 11. TL;DR

```
M3 multi-day cadence proof を 3-5 日 → 1-2 日 に圧縮する。

手法:
  1. Time Dilation       (timeutil.py 拡張)  ← 最推奨
  2. Synthetic Aged State (新 scenario)
  3. Tick Compression    (既存 interval)
  4. Staged Pyramid      (1-4 組合せ)

MVP: 2-4 時間実装で Pyramid P0-P6 が proved
節約: 2-3 日の暦時間 (ROI 10-15×)

実装順序:
  Phase 0: timeutil consolidation (30分)
  Phase 1: dilation 実装 (30分)
  Phase 2: P4-P5 dogfood 走行 (1-2時間 実時間)
  Phase 3: aged-reentry (2-3時間)
  Phase 4: 実 1 日保険 (1日 背景)
```

**推奨**: Phase 0-2 を今日中に landing、P4-P5 dogfood を今日の夜間に走らせる。明日朝には **dilated 1 week cadence proved** の状態。

---

## 12. Addendum 2026-04-20 09:40 — Snapshot landed + mew_preferred achieved

本 review を書いた 40 分後（2026-04-20 09:23-09:32 JST）に、agent が独立に以下を landing させた。**骨格はそのまま有効**だが、いくつかの前提が更新されたので追記する。

### 12.1 観測された新 evidence

#### `9:23 57ff355 Strengthen M3 reentry comparator`
新 doc: `docs/M3_REENTRY_BURDEN_COMPARISON_2026-04-20.md`。M3 reentry gate の measurement が richer 化：
- `reconstruction_burden` (repository-only steps / verifier read before correct action 等)
- `persistent_advantage_signal` (mew_saved_reconstruction / mew_prevented_wrong_first_action 等)

**結果**: `comparison choice: mew_preferred`（**M3 で初めて mew が fresh CLI を超えた**）。

#### `9:32 fb37cf5 Add work session snapshots`
`src/mew/snapshot.py` 199 LOC 新規。構造：
```python
@dataclass(frozen=True)
class WorkSessionSnapshot:
    schema_version: int              # = 1
    session_id: str
    task_id: str
    state_hash: str                  # drift 検出
    last_effect_id: int
    closed_at: str | None
    saved_at: str                    # ← dilation の影響を受ける
    working_memory: dict
    touched_files: list[str]
    pending_approvals: list[dict]
    continuity_score: str | None
    continuity_status: str | None
    continuity_recommendation: dict | None
    active_memory_refs: list[str]
    unknown_fields: dict             # evolution-safe
```

保存先: `.mew/sessions/<session_id>/snapshot.json`。`mew work --close-session` と `/work-session close` が snapshot を保存。**resume 主経路はまだ差し替えていない**（Phase 2 は signal 待ち）。

### 12.2 本 proposal の妥当性

| 項目 | Status |
|---|---|
| Time Dilation（手法 1）| **依然必要**。未 landing |
| Synthetic Aged State（手法 2）| **依然必要**。ただし実装方式を更新（下記 12.3）|
| Tick Compression（手法 3）| 変更なし |
| Staged Proof Pyramid | 変更なし、むしろ P6 が snapshot で明確化 |
| timeutil consolidation | **依然 critical**。snapshot の `saved_at` も now_iso 経由なので dilation 整合が必要 |

**骨格は有効**。破壊的な rewrite 不要。

### 12.3 §2 手法 2 "Synthetic Aged State" の更新

**更新前**: state.json を人工合成して resume テスト。

**更新後**: snapshot.json を人工合成して `load_snapshot()` の drift 検出を exercise。

```python
# 新しい aged-reentry 設計
def build_aged_snapshot(days_ago: int) -> WorkSessionSnapshot:
    return WorkSessionSnapshot(
        schema_version=1,
        session_id="aged-test",
        task_id="0",
        state_hash="deliberately_stale_hash",  # drift を起こす
        last_effect_id=100,
        closed_at=(now - days_ago).isoformat(),
        saved_at=(now - days_ago).isoformat(),
        working_memory={...},  # N 日前の plausible content
        touched_files=[...],
        pending_approvals=[...],
        continuity_score="7/9 usable",  # 古い snapshot 想定
        continuity_status="usable",
        continuity_recommendation=None,
        active_memory_refs=["typed:project:stale-fact"],
        unknown_fields={},
    )

# dogfood
1. synthetic snapshot を書く
2. mew で load_snapshot() 呼ぶ
3. SnapshotLoadResult.usable / drift_notes / partial_reasons が意味を持つか verify
4. resume 主経路との整合を測定（まだ主経路ではないので diff 検証）
```

これは snapshot.py の drift 検出を**実証する第一歩**にもなる。

### 12.4 §4 前準備の更新

timeutil consolidation に加えて：

**新規注意点**: `snapshot.py` の `saved_at` は `timeutil.now_iso()` 経由（確認済み：`from .timeutil import now_iso`）。

**これは desired な挙動**：
- Dilation 有効な dogfood で snapshot を保存 → `saved_at` は dilated time
- その snapshot を load すると N 日後として扱われる → **aged reentry の natural な実現**
- **手法 1（dilation）と手法 2（aged state）が統合される**

つまり dilation を活用すれば：
```bash
# 1 時間で 1 週間 snapshot を生成
MEW_TIME_DILATION=168 mew dogfood --scenario resident-loop --duration 3600
# → saved_at は 1 週間後の timestamp
# → そのまま load して aged reentry test になる
```

**これは手法 1 + 手法 2 の merger**。別々に実装する必要が減る。実装時間が 2-3 時間さらに短縮される可能性。

### 12.5 更新された Phase ordering

**Phase 0**（30 分）: timeutil consolidation（7 ファイル統一）— 依然必要

**Phase 1**（30 分）: dilation 実装 + CLI — 依然必要

**Phase 2**（1-2 時間）: **dilated snapshot proof**
- `MEW_TIME_DILATION=168` で 1 時間 dogfood
- snapshot.json の `saved_at` が 1 週間後
- その snapshot を load → drift 検出
- **P4-P6 が同時に proved**

**Phase 3**（削除可能）: 独立 aged-reentry scenario — dilation で十分実現できるので、separate scenario は optional

**Phase 4**（1 日、保険）: 実 1 日 cadence — 依然必要（OS-level stability）

**合計実装時間**: 元 proposal の 2-4 時間 → **1-2 時間に短縮**可能（Phase 3 が吸収される）

### 12.6 M3 Done-when #1 の現状更新

元 proposal 時点："parity"（限定的）。
現時点：**"mew_preferred" 初達成**（tiny synthetic README task）。

次のステップは proposal の意図と変わらない：
1. **規模の大きい task での mew_preferred 再現**
2. **long-running cadence での mew_preferred**
3. **context compression 跨ぎでの mew_preferred**

dilation + snapshot combo がこれらを accelerate する。

### 12.7 追加 pinpoint 参照

```
src/mew/snapshot.py                       (新規 199 LOC)
  :14   SNAPSHOT_SCHEMA_VERSION = 1
  :22   class WorkSessionSnapshot
  :37   unknown_fields: dict (evolution-safe)
  :74   class SnapshotLoadResult
  :127  def take_snapshot
  :139  state_hash via state_digest

docs/M3_REENTRY_BURDEN_COMPARISON_2026-04-20.md  (新規 84 LOC)
  → 初の M3 mew_preferred 記録
```

### 12.8 推奨の再整理

元の「**Phase 0-2 を今日中に landing、P4-P5 dogfood を今日の夜間に走らせる**」は以下に更新：

**更新後の推奨**:
1. **Phase 0**（30 分）: timeutil consolidation
2. **Phase 1**（30 分）: dilation 実装
3. **Phase 2**（1 時間）: `MEW_TIME_DILATION=168 resident-loop 3600s` で**1 週間分 snapshot を 1 時間生成**
4. **Phase 2.5**（30 分）: 生成された snapshot を load → drift 検出 verify → aged reentry gate proved
5. **Phase 4**（背景、1 日）: 実 1 日 cadence を並行放置

**今日中の目標**: Phase 0-2.5 完了 = **dilated 1 week cadence + aged reentry both proved**。
**明日朝の状態**: P0-P6 の pyramid は proved、P7（実 1 日）を背景で待つのみ。

---

## 13. Updated TL;DR

```
Snapshot は 09:32 に landed (ADOPT §5.11 minimal skeleton)。
M3 mew_preferred は 09:23 に初達成 (小 synthetic task)。

残るのは:
  - Time Dilation (未 landing)
  - Dilation を活用した aged reentry proof (合成不要、snapshot の saved_at で実現)
  - multi-day cadence proof (dilation で圧縮)

骨格は有効。実装時間 2-4h → 1-2h に短縮。

推奨: Phase 0-2.5 を今日中、Phase 4 を背景放置。
明日朝に M3 long-running cadence proof の pyramid 完成。
```

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 08:50 JST, addendum 09:40 JST after observing snapshot landing
**Context**: initial commit `314c997` (1041 commits); addendum at `fb37cf5` (1043 commits) after snapshot.py landed and M3 mew_preferred achieved
**Related**: `docs/M3_RESIDENT_LOOP_30MIN_2026-04-20.md`, `docs/M3_REENTRY_BURDEN_COMPARISON_2026-04-20.md`, `docs/REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md`, `ROADMAP.md`, `ROADMAP_STATUS.md` M3 "Missing proof:" section, `src/mew/snapshot.py` (landed 09:32)
**Conversation trace**: Claude Code session (single session, no memory between runs)
