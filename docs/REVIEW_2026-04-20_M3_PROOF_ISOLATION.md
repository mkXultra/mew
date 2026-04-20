# REVIEW 2026-04-20 — M3 Proof Isolation: Separate Environment Strategy

**Written by**: Claude Opus 4.7（外部レビュー、Claude Code 経由）
**対象読者**: mew を実装中の別 Opus 4.7（effort: max）
**位置付け**: 意見。ROADMAP_STATUS の M3 active milestone を前提、**long-running proof の infrastructure strategy** として提示
**生成条件**: 2026-04-20 10:00 JST 以降、commit `fb37cf5` 時点、1043 commits 観測後
**関連**:
- `docs/REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md`（時間圧縮手法、本提案と相補）
- `docs/M3_RESIDENT_LOOP_30MIN_2026-04-20.md`（既存 30 分 cadence proof）
- `docs/M3_REENTRY_BURDEN_COMPARISON_2026-04-20.md`（初の mew_preferred）

---

## 0. 動機

M3 Done-when の "long-running resident cadence" は real-time の proof が必要。`docs/REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md` の time dilation で 24× 加速しても：

1. **実 OS stability proof** は real time でしか確認できない
2. **実 24 時間 cadence** は削れない最低値
3. **実 1 週間 proof** があれば M3 `done` 宣言の defensibility が段違い

**問題**: これを local Mac で走らせると：
- Mac が sleep → proof 中断
- user が Ctrl-C → proof 崩壊
- agent が並行して state を触る → regression で proof invalid
- **Mac を 1 日〜1 週間 占有**する
- local dev と proof の compute が competing

**解決案**: **別環境での proof 実行**。mew 本体開発と proof を物理的に分離する。

---

## 1. 別環境が解決する問題

| 問題 | 同一 PC | 別環境 |
|---|---|---|
| PC sleep / reboot で proof 中断 | リスク高 | ✅ 解消 |
| Accidental Ctrl-C / 誤操作 | リスク高 | ✅ 解消 |
| Agent M4 並列実装での regression | 高（state 共有）| ✅ 完全分離 |
| Mac リソース占有 | 24h-168h | ✅ 0 |
| Dev work と proof compute の competing | あり | ✅ 解消 |
| OS-level 安定性（memory leak, FD leak）検証 | dev ノイズ混じり | ✅ 純粋環境 |
| Linux / production-like 環境での動作確認 | Mac 限定 | ✅ 可能（VPS）|

特に **"agent が並列で M4 を触って proof が壊れる"** のリスクは本質的。`docs/REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md` の選択肢 C（並列実装）を安全に実行する**唯一の方法**でもある。

---

## 2. 選択肢の比較

コスト低い順に：

### Option A: Docker container (local Mac)

**最推奨** for short/medium proof。

- セットアップ: 5 分
- コスト: 無料
- 分離レベル: filesystem / process 分離（OS は共有）
- Mac sleep 影響: あり（`caffeinate` で回避可）
- 向き: 数時間〜1 日の proof

### Option B: 別ユーザーアカウント + tmux

最軽量。

- セットアップ: 1 分
- コスト: 無料
- 分離レベル: filesystem のみ（user space）
- Mac sleep 影響: あり
- 向き: agent regression 回避だけ欲しい場合

### Option C: 小型 VPS (Hetzner / DigitalOcean)

本格的な分離と 24/7 稼働。

- セットアップ: 15 分
- コスト: $1-5（1 週間）
- 分離レベル: 完全別 machine、Linux 環境
- Sleep 影響: なし
- 向き: 実 1 日〜1 週間の proof、**M3 の本番 evidence**

### Option D: Raspberry Pi / 既存旧 PC

手元に余り機がある場合。

- セットアップ: 30 分
- コスト: 0（電気代のみ）
- ARM だと uv wheel に注意
- 向き: 常時稼働環境が欲しい user

### Option E: 別 Mac mini / dedicated HW

Overkill だが最強。

- コスト: $数百〜
- 推奨しない（VPS で事足りる）

---

## 3. 推奨 configuration

### 基本方針: **Docker で short proof、VPS で long proof**

```
┌────────────────────┬─────────────────────────────────┐
│ Proof 種類          │ 推奨環境                         │
├────────────────────┼─────────────────────────────────┤
│ 1h dilated 1week    │ Docker (local)                  │
│ 1h cadence          │ Docker (local)                  │
│ 6h cadence          │ Docker (local, caffeinate 有)   │
│ 実 24h cadence      │ VPS                             │
│ 実 1 week cadence   │ VPS                             │
│ Comparative dogfood │ Docker or local（attention 要） │
└────────────────────┴─────────────────────────────────┘
```

---

## 4. Docker setup（今日すぐ作れる）

### 4.1 Dockerfile（30 行、repo に追加）

```dockerfile
# Dockerfile.proof (repo root に新規)
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /mew
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
# README.md を pyproject.toml が require している場合に備え

RUN uv sync --no-dev || uv sync

# Proof workspace（volume mount される）
RUN mkdir -p /proof/workspace /proof/artifacts

ENV PYTHONUNBUFFERED=1
ENV MEW_PROOF_MODE=1

# Default: 1 week resident-loop
CMD ["uv", "run", "mew", "dogfood", \
     "--scenario", "resident-loop", \
     "--duration", "604800", \
     "--interval", "60", \
     "--workspace", "/proof/workspace", \
     "--json"]
```

### 4.2 起動コマンド

```bash
# Build
docker build -f Dockerfile.proof -t mew-proof:latest .

# Run (1 day cadence)
docker run -d --name mew-proof-1day \
  -v $(pwd)/proof-artifacts:/proof/artifacts \
  -v $(pwd)/proof-workspace:/proof/workspace \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  mew-proof:latest \
  uv run mew dogfood --scenario resident-loop \
    --duration 86400 --interval 60 \
    --workspace /proof/workspace --json

# 結果取得
docker logs mew-proof-1day > /tmp/mew-proof-1day.log
ls proof-workspace/.mew/
```

### 4.3 Mac が sleep しないように

```bash
# proof 中は caffeinate で sleep 防止
caffeinate -i -w $(docker inspect mew-proof-1day --format '{{.State.Pid}}')
```

### 4.4 実装負荷

- `Dockerfile.proof` 新規 30 行
- `.dockerignore` 追加（`references/`, `.git/`, `.mew/` 等を除外）10 行
- README に "Running proof" セクション追加（任意）

**合計**: ~40 行、15-30 分の作業。

---

## 5. VPS setup（1 週間 proof 用）

### 5.1 VPS 選定

推奨: **Hetzner CX11**（€3.79/月、1 vCPU / 2GB RAM / 20GB SSD）

代替: DigitalOcean Basic Droplet（$5/月）、Linode Nanode（$5/月）

### 5.2 セットアップスクリプト

```bash
# init.sh（VPS 上で一度実行）
#!/bin/bash
set -euo pipefail

apt-get update
apt-get install -y python3 python3-pip git curl tmux
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

git clone https://github.com/<user>/mew.git /opt/mew
cd /opt/mew
uv sync

# Proof user
useradd -m -s /bin/bash mewproof
cp -r /opt/mew /home/mewproof/mew
chown -R mewproof:mewproof /home/mewproof/mew

# Systemd service（任意）: sleep 時も自動再起動不要、単に tmux で十分
```

### 5.3 Proof 起動

```bash
# VPS で
ssh mewproof@<vps-ip>
tmux new-session -s m3-proof -d
tmux send-keys -t m3-proof "cd ~/mew && export ANTHROPIC_API_KEY='...' && uv run mew dogfood --scenario resident-loop --duration 604800 --interval 60 --workspace /home/mewproof/proof-1week --json > /home/mewproof/proof-1week.log 2>&1" C-m

# detach して放置
```

### 5.4 結果回収（週末に）

```bash
# local から
rsync -av mewproof@<vps-ip>:/home/mewproof/proof-1week/ ./local-proof-artifacts/
scp mewproof@<vps-ip>:/home/mewproof/proof-1week.log ./local-proof-artifacts/
```

### 5.5 セキュリティ

- API key は環境変数のみ、`.env` にも置かない（shell 履歴に注意）
- SSH key only, password login 無効化
- Hetzner の firewall で必要 port のみ open（本 proof は inbound 不要）

### 5.6 実装負荷

- `scripts/provision_proof_vps.sh` 新規 50 行
- `scripts/start_proof.sh` 新規 20 行
- README に "VPS proof" セクション追加（任意）

**合計**: 70 行、VPS 契約込みで 30 分の作業。

---

## 6. Proof scenario 3 種

### 6.1 Passive cadence (API key 不要)

```bash
uv run mew dogfood --scenario resident-loop \
  --duration 604800 \          # 1 週間
  --interval 60 \
  --workspace /proof/cadence-1w
```

これは **passive tick のみ**、external API 呼び出しなし。API key 不要。

**検証項目**:
- passive_events count の線形増加
- thought journal の compaction
- state.json サイズの bounded growth
- effects.jsonl の rotation

### 6.2 Actual resident with synthetic load

```bash
uv run mew start --interval 300 --autonomy-level propose &
MEW_PID=$!

# 1 時間おきに模擬タスク投入
while true; do
  uv run mew task add "Synthetic task $(date +%s)" --kind research
  sleep 3600
done &
```

API key **必要**（propose autonomy が LLM 呼ぶ場合）。

**検証項目**:
- multi-task 処理での state 安定性
- actual API TTL との整合（Codex Web API セッション切れ等）
- long-running での memory leak

### 6.3 Periodic comparative dogfood (API key 必要、両側)

```bash
# 6 時間おきに comparative を走らせる
0 */6 * * * cd /proof && uv run mew dogfood --scenario m3-reentry-gate \
  --workspace /proof/comparative/$(date +%Y%m%d-%H) --json
```

これは **毎回 codex-ultra を外部呼び出し**するので API credit 消費。1 日 4 回 × 7 日 = 28 回。

**検証項目**:
- mew_preferred の再現性（何 % の回で mew_preferred か）
- burden metric の分布
- task shape 別の advantage profile

---

## 7. Artifact retrieval 戦略

長時間 proof の結果を local に戻す方法：

### 7.1 Docker: volume mount

```bash
# -v で local directory に直接書き出し
-v $(pwd)/proof-artifacts:/proof/artifacts
```

proof 中でも local から `ls proof-artifacts/` で途中経過が見える。

### 7.2 VPS: 自動 push

```bash
# cron で 1 時間おきに git push（proof 結果 repo）
0 * * * * cd /proof/artifacts && git add . && git commit -m "proof snapshot $(date)" && git push
```

local で `git pull` すれば progress が見える。

### 7.3 VPS: rsync pull

```bash
# local から毎朝 rsync
0 7 * * * rsync -av mewproof@<vps-ip>:/proof/ /local/proof-backup/
```

### 7.4 完了通知

proof 終了時に notification：

```bash
# proof command の末尾
curl -X POST https://ntfy.sh/<私用 topic> -d "M3 proof finished at $(date)"
```

---

## 8. 他の proposal との integration

### 8.1 `REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md` との関係

Accelerated proof は**計算圧縮**、本 proposal は**実行分離**。補完関係。

| Acceleration | Isolation | 組み合わせ |
|---|---|---|
| Dilation のみ | local | 簡易、7h 連続占有 |
| Dilation のみ | Docker | 7h 背景 run、Mac 解放 |
| Dilation + real | Docker + VPS | 最強、同時進行 |

**推奨の combo**:
- **Local Docker**: dilated 1 week proof（7 時間）
- **VPS**: 実 1 week proof（168 時間）
- **両方を並行**: proof のクロス検証、dilation と real の差分観察

### 8.2 M4 並列実装（前チャットの話題）との関係

前回話した「M3 proof 中に M4 並列実装したい」は、**本 proposal で安全に実現可能**：

- M3 proof は VPS で走る（local と完全分離）
- local agent は自由に M4 実装してよい
- M4 commits が proof PC に届くのは user が `git push` した時のみ
- proof 用 repo は **tag ベース**で pin（例: `v-m3-proof-2026-04-20`）、HEAD を追わない

これで **evaluator skill の "one active milestone" 規律を破らずに**、計算的には並列化できる。

---

## 9. Risks / Caveats

### 9.1 API key セキュリティ
VPS や Docker に key を置く：
- Environment 変数のみ、ファイルに書かない
- 使用後は key をローテーション
- Hetzner 等の VPS ログに key が残らないよう注意

### 9.2 Platform 差異
mew は macOS 中心で開発。VPS (Linux) で走らせると：
- **副作用** macOS 限定の問題が露呈する可能性（path 区切り、permission、launchd 等）
- これは **bonus**（production-like の検証）でもあり**リスク**（proof 以前に動かない）でもある
- 先に Docker で Linux 互換を確認してから VPS 移行が安全

### 9.3 外部 API TTL / rate limit
- 1 週間 proof 中に Codex Web API セッションが切れる可能性
- 再認証が必要な場合、proof が自動継続できない
- 対策: passive cadence（scenario 6.1）を基本に、comparative (6.3) は低頻度に

### 9.4 Proof repo の HEAD 汚染
local agent が proof 中の repo を触らないよう：
- proof 用 git tag を切って push
- VPS は tag を checkout（`git checkout v-m3-proof-2026-04-20`）
- local で M4 実装が進んでも VPS は影響受けない

### 9.5 Artifact が grows too large
- effects.jsonl が 1 週間で数 MB になる可能性
- Git push ベースの retrieval だと repo が膨らむ
- **対策**: artifact repo を別に切る、もしくは rsync pull のみ

### 9.6 Proof 失敗時の debug 困難
別環境だと debugger 取れない：
- mew doctor を定期実行して状態保存
- 失敗時に state.json の snapshot を保持
- `tmux` セッションなら後から attach して状況確認可能

---

## 10. 期待される effect

### 時間短縮
| 項目 | Local のみ | 別環境利用 | 節約 |
|---|---|---|---|
| Mac 占有時間 | 24-168h | **0-7h** | ~95% |
| User 作業 blocked 時間 | 多 | **ほぼ 0** | ~全部 |
| agent の M4 並列可能性 | × | **○** | M4 着手が数日早まる |
| OS stability 検証 | Mac のみ | **Mac + Linux** | 1 production check |

### Proof 品質
- **実 1 週間 proof** が現実的に行える（local では user が耐えられない）
- **複数 cadence 並列** で信頼度 up（dilated local + real VPS のクロス検証）
- **M3 `done` 宣言の defensibility** が段違い（"we ran it for a week and here's the log"）

---

## 11. 推奨実施順序

### Phase 0（今日、15-30 分）
1. `Dockerfile.proof` を書く
2. `.dockerignore` 調整
3. local で `docker build` してイメージ化
4. 短時間 run（30 分 cadence）で起動確認

### Phase 1（今夜、自動）
5. Docker で dilated 1 week cadence proof（7h 実）を夜間 run
6. 並行で Docker で real 1 day cadence を 24h run

### Phase 2（明日、20-40 分）
7. VPS を契約（Hetzner CX11 等）
8. init.sh で provisioning
9. **実 1 week cadence** を VPS で start（7 日放置）

### Phase 3（1 週間後）
10. VPS の artifact を回収
11. M3 Done-when checklist の **multi-day evidence** を填める
12. M3 `done` 宣言 or 追加 proof 判断

### Phase 4（継続的、M3 close 後）
13. VPS を **production-like running proof** として継続
14. trust ledger / running uptime ledger を蓄積

---

## 12. 実装 agent への具体的指示

もし本 proposal を採用するなら、agent が今日できる 1 commit:

```
commit: Add proof Dockerfile and start script

- Dockerfile.proof に 30 行
- .dockerignore に除外パス追加
- scripts/run_proof_docker.sh に起動 helper
- README.md に "Running long-running proof" セクション追加
```

これだけで **local Docker での proof が動く**。VPS は user の判断（VPS 契約を agent に任せるのは不適切）。

---

## 13. 検証済み事実

- `Dockerfile` は repo に**存在しない**（新規作成対象）
- `ANTHROPIC_API_KEY` が `src/mew/anthropic_api.py:38` で `os.environ.get` 読み
- `resident-loop` scenario は `dogfood.py` の `run_resident_loop_scenario(workspace, env=None, duration=6.0, interval=2.0, poll_interval=0.1)`
- `requires-python = ">=3.9"` (pyproject.toml) — Python 3.11 slim で動く
- 既存 dependencies: `pytest>=8.0, pytest-testmon>=2.1, ruff>=0.11`（production は zero dep）

---

## 14. 私が間違っている可能性

1. **VPS 選定**: Hetzner は欧州中心、JP user なら遠い。ConoHa / Sakura VPS 等の方が低 latency かも
2. **Docker build の Python バージョン**: 3.11 slim を提案したが、mew が Python 3.9+ ならもっと軽い Alpine でも動く可能性
3. **caffeinate の必要性**: agent が `MEW_PROOF_MODE` 環境変数で sleep 挙動変えるならそれが正解
4. **Git push-based artifact retrieval**: agent が既に別の retrieval 仕組みを持ってる可能性
5. **M3 `done` 判定に「実 1 週間 proof」が必須か**: 私は「あれば defensibility 最強」と書いたが、evaluator skill が「6 時間 cadence で十分」と判定するかもしれない

これらは実装 agent が現場判断で優先。本 proposal は方向のみ。

---

## 15. TL;DR

```
M3 long-running proof を local から分離:
  - Local Docker: dilated 1 week proof (7h), 実 1 day proof (24h)
  - VPS: 実 1 week proof (168h, 背景放置)

コスト:
  - Docker: 無料、30 分セットアップ
  - VPS: $1-5/週、30 分セットアップ

効果:
  - Mac 占有 24-168h → 0-7h
  - agent が M4 並列実装可能（別環境なので安全）
  - 実 1 week proof が現実的に可能

推奨:
  - 今日: Dockerfile 作成、dilated + 実 1 day を local Docker で run
  - 明日: VPS 契約、実 1 week を VPS で放置
  - 1 週間後: artifact 回収、M3 done 宣言
```

**最小 commit**: `Dockerfile.proof` + `.dockerignore` + `scripts/run_proof_docker.sh` = **~50 LOC、30 分**。

これで M3 proof の time-bound 制約から local 環境を解放、agent の attention を M4 prep か M3 robustness 強化に回せます。

---

**Reviewer**: Claude Opus 4.7 (外部)
**Generated**: 2026-04-20 10:00 JST
**Context**: commit `fb37cf5`, 1043 commits observed, snapshot.py just landed, M3 active
**Related**: `docs/REVIEW_2026-04-20_M3_ACCELERATED_PROOF.md`, `docs/REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md`, `docs/REVIEW_2026-04-19_STRUCTURAL_TIMING.md`
**Conversation trace**: Claude Code session (single session, no memory between runs)
