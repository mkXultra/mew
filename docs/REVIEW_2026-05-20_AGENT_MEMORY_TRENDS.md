# 2026年時点の Agent Memory / Long-Term Memory Subsystem トレンド調査

Status: research note.  
作成日: 2026-05-20.  
範囲: agent memory / long-term memory / memory-augmented LLM agents / multi-session memory / memory benchmark / self-evolving memory。  
非範囲: mew 用の詳細設計、実装案、コード変更。

## 要約

2026年時点の主流は、単なる「vector DB に会話履歴を入れる」から、次の方向に移っている。

| 観測 | 2026時点の読み |
|---|---|
| 最も実用寄り | hybrid retrieval、typed memory、provenance、reranking、latency/token cost を含む評価 |
| 研究で伸びている | graph/temporal/causal memory、procedural memory、test-time learning、self-evolving memory |
| 評価の主戦場 | multi-session で、記憶が後続の行動・判断・手順成功に効いたか |
| hype が多い領域 | human-like memory、memory OS、latent/self-evolving memory、単一 benchmark SOTA 主張 |
| MemoryArena の位置づけ | LoCoMo/LongMemEval 型の「思い出せるか」から、「記憶を使って後続タスクを解けるか」へ寄せた 2026 型 benchmark |

一言でいうと、流行は次の式に寄っている。

```text
store everything
  -> retrieve relevant facts
  -> update / consolidate / forget
  -> use memory as task evidence
  -> evaluate downstream behavior, not recall alone
```

## 調査上の前提

「人気/主流」は厳密な citation ranking ではなく、2025-2026 の論文・benchmark・survey・OSS/実装論文で繰り返し現れる概念として判断した。

| 判断軸 | 見たもの |
|---|---|
| 年代 | 2025-2026 を優先。2023-2024 は基礎パターンのみ |
| 種別 | arXiv / ACL / ICLR 2026 / survey / benchmark / memory system paper |
| 主対象 | LLM agents の long-term / multi-session / external memory |
| 除外気味 | 単なる長文読解、一般 RAG、汎用 long-context model 評価 |

## 1. 流行っている memory subsystem パターン分類

### パターン早見表

| # | パターン | 主流度 | 実用度 | 代表キーワード | 代表例 |
|---|---|---:|---:|---|---|
| 1 | Retrieval-augmented persistent memory | 高 | 高 | vector store, BM25, hybrid retrieval, rerank, Recall@k | LongMemEval, Mem0, Zep |
| 2 | Typed cognitive memory | 高 | 中-高 | working / episodic / semantic / procedural, core memory | CoALA, MIRIX, MemoryAgentBench |
| 3 | Memory lifecycle / memory operations | 高 | 高 | write-manage-read, consolidation, update, forgetting, indexing | Rethinking Memory, Neuromem |
| 4 | Hierarchical / context OS / compression | 高 | 高 | virtual context, sleep-time consolidation, summary state | MemGPT, LightMem, ReSum, MemOS |
| 5 | Graph / temporal / causal memory | 高 | 中-高 | temporal KG, causality graph, linked notes, bounded graph expansion | Zep, A-MEM, Mem0 graph, GAM, AMA-Agent |
| 6 | Reflective / experiential / procedural memory | 中-高 | 高 for agents | reflection, lessons, workflows, skill libraries, runbooks | Reflexion, ExpeL, Voyager, AWM, Agent KB |
| 7 | Learned memory manager | 中 | 中 | RL memory policy, ADD/UPDATE/DELETE/NOOP, memory-as-action | Memory-R1, Fine-Mem, MEM1 |
| 8 | Self-evolving memory | 中 | 低-中 | test-time evolution, refine/prune, memory evolution, latent memory | Evo-Memory, EvoMemBench, MemGen |
| 9 | Multimodal / screen / environment memory | 中 | 中 | screenshots, UI state, environment gotchas, web trajectories | MIRIX, LongMemEval-V2 |
| 10 | Safety / governance of memory | 伸長中 | 高 | stale memory, contradiction, poisoning, privacy, misevolution | MemEvoBench, surveys |

### パターン別の見立て

| パターン | 何を解くか | 2026時点の主流感 | 実用上の注意 |
|---|---|---|---|
| Retrieval memory | 過去会話・過去観測から必要情報を引く | まだ実装の中心。RAG 単体より hybrid + rerank + evidence 化が増加 | 類似検索だけだと因果・手順・更新に弱い |
| Typed cognitive memory | memory を用途別に分ける | working/episodic/semantic/procedural は共通語になった | 分類が UI/設計を複雑にしやすい |
| Lifecycle memory | 書き込み・更新・削除・圧縮まで扱う | survey/benchmark 側で主流化 | write path の品質が低いと retrieval 改善では救えない |
| Hierarchical memory | context budget と長期一貫性の両立 | 実用寄り。LightMem/ReSum 系は cost を強く見る | summary は loss を生む。原典参照が必要 |
| Graph memory | 関係・時間・矛盾・多段推論 | 2025以降かなり人気 | graph 化の抽出ミスが後で効く。bounded traversal が重要 |
| Procedural memory | 同じ失敗を繰り返さない、作業手順を再利用 | coding/web/enterprise agents ではかなり実用寄り | 事実記憶より評価が難しい |
| Learned manager | memory 操作を policy として学習 | 研究では増加 | 学習コスト、reward 設計、再現性が課題 |
| Self-evolving memory | deployment 中に記憶を整理・進化 | 2026 frontier | hype も多い。安全評価が追いついていない |

## 2. 代表論文・benchmark・キーワード

### Survey / taxonomy

| 論文 | 年 | ID / URL | 位置づけ | よく使う概念 |
|---|---:|---|---|---|
| A Survey on the Memory Mechanism of Large Language Model based Agents | 2024 | arXiv:2404.13501 https://arxiv.org/abs/2404.13501 | 初期の agent memory survey | memory source/form/operation |
| From Human Memory to AI Memory | 2025 | arXiv:2504.15965 https://arxiv.org/abs/2504.15965 | human memory との対応整理 | object/form/time, human-inspired memory |
| Rethinking Memory in LLM based Agents | 2025 | arXiv:2505.00675 https://arxiv.org/abs/2505.00675 | operations 中心の taxonomy | consolidation, updating, indexing, forgetting, retrieval, condensation |
| Memory for Autonomous LLM Agents | 2026 | arXiv:2603.07670 https://arxiv.org/abs/2603.07670 | 2026時点の agent memory survey | write-manage-read, temporal scope, substrate, control policy |
| From Storage to Experience | 2026 | arXiv:2605.06716 https://arxiv.org/abs/2605.06716 | storage -> reflection -> experience の流れ | trajectory preservation/refinement/abstraction |

### 基礎パターンを作った 2023-2024

| 論文 | 年 | ID / URL | 今も残っている概念 |
|---|---:|---|---|
| Reflexion | 2023 | arXiv:2303.11366 https://arxiv.org/abs/2303.11366 | verbal reflection, episodic memory buffer |
| Generative Agents | 2023 | arXiv:2304.03442 https://arxiv.org/abs/2304.03442 | memory stream, reflection, planning |
| MemoryBank | 2023 | arXiv:2305.10250 https://arxiv.org/abs/2305.10250 | long-term user memory, forgetting/reinforcement |
| Voyager | 2023 | arXiv:2305.16291 https://arxiv.org/abs/2305.16291 | skill library, executable procedural memory |
| ExpeL | 2023 | arXiv:2308.10144 https://arxiv.org/abs/2308.10144 | experience pool, lesson extraction |
| CoALA | 2023 | arXiv:2309.02427 https://arxiv.org/abs/2309.02427 | working/episodic/semantic/procedural memory |
| MemGPT | 2023 | arXiv:2310.08560 https://arxiv.org/abs/2310.08560 | virtual context management, memory tiers |
| Agent Workflow Memory | 2024 | arXiv:2409.07429 https://arxiv.org/abs/2409.07429 | reusable workflow memory |

### 2025-2026 の memory system 論文

| 論文 / system | 年 | ID / URL | パターン | 何が流行を示すか |
|---|---:|---|---|---|
| Zep: Temporal Knowledge Graph Architecture | 2025 | arXiv:2501.13956 https://arxiv.org/abs/2501.13956 | temporal graph memory | enterprise memory + temporal KG |
| A-MEM | 2025 | arXiv:2502.12110 https://arxiv.org/abs/2502.12110 | agentic linked memory | Zettelkasten, dynamic linking, memory evolution |
| Mem0 | 2025 | arXiv:2504.19413 https://arxiv.org/abs/2504.19413 | production memory layer | extraction/consolidation/retrieval, graph variant, latency/token cost |
| MEM1 | 2025 | arXiv:2506.15841 https://arxiv.org/abs/2506.15841 | learned compact memory | constant memory, RL, long-horizon agents |
| MemOS: A Memory OS for AI System | 2025 | arXiv:2507.03724 https://arxiv.org/abs/2507.03724 | memory OS | plaintext/activation/parameter memory, MemCube |
| MIRIX | 2025 | arXiv:2507.07957 https://arxiv.org/abs/2507.07957 | multi-agent typed memory | core/episodic/semantic/procedural/resource/vault, multimodal memory |
| Memory-R1 | 2025 | arXiv:2508.19828 https://arxiv.org/abs/2508.19828 | RL memory manager | ADD/UPDATE/DELETE/NOOP, answer agent |
| ReSum | 2025 | arXiv:2509.13313 https://arxiv.org/abs/2509.13313 | context summarization | indefinite web search via compact reasoning state |
| MemGen | 2025 | arXiv:2509.24704 https://arxiv.org/abs/2509.24704 | latent/self-evolving memory | memory trigger/weaver, machine-native latent memory |
| Memory as Action | 2025 | arXiv:2510.12635 https://arxiv.org/abs/2510.12635 | learnable context curation | memory editing as agent action |
| LightMem | 2025 | arXiv:2510.18866 https://arxiv.org/abs/2510.18866 | lightweight hierarchical memory | sensory/short-term/long-term, offline sleep-time update |
| Fine-Mem | 2026 | arXiv:2601.08435 https://arxiv.org/abs/2601.08435 | fine-grained reward for memory ops | credit assignment for memory operations |
| AgeMem | 2026 | arXiv:2601.01885 https://arxiv.org/abs/2601.01885 | unified STM/LTM policy | memory management inside agent policy |
| Neuromem | 2026 | arXiv:2602.13967 https://arxiv.org/abs/2602.13967 | streaming memory lifecycle testbed | insertion/retrieval interleaving, latency |
| GAM | 2026 | arXiv:2604.12285 https://arxiv.org/abs/2604.12285 | hierarchical graph memory | event progression graph + topic associative network |
| delta-mem | 2026 | arXiv:2605.12357 https://arxiv.org/abs/2605.12357 | compact online model-coupled memory | fixed-size associative memory state |

### 2024-2026 の主要 benchmark

| Benchmark | 年 | ID / URL | 何を測るか | 2026時点の位置づけ |
|---|---:|---|---|---|
| LoCoMo | 2024 | arXiv:2402.17753 https://arxiv.org/abs/2402.17753 | multi-session conversation memory、QA、summarization | いまだ基礎 benchmark。会話中心 |
| LongMemEval | 2024/2025 | arXiv:2410.10813 https://arxiv.org/abs/2410.10813 | extraction, multi-session reasoning, temporal reasoning, update, abstention | chat assistant memory の標準級 |
| MemoryAgentBench | 2025/2026 | arXiv:2507.05257 https://arxiv.org/abs/2507.05257 | accurate retrieval, test-time learning, long-range understanding, selective forgetting | 4能力を multi-turn 化した代表 benchmark |
| BEAM | 2025/2026 | arXiv:2510.27246 https://arxiv.org/abs/2510.27246 | 100K-10M token の long-term conversational memory | long-context だけで逃げにくい方向 |
| Evo-Memory | 2025/2026 | arXiv:2511.20857 https://arxiv.org/abs/2511.20857 | streaming task streams, test-time evolution | self-evolving memory 評価の代表 |
| MemoryArena | 2026 | arXiv:2602.16313 https://arxiv.org/abs/2602.16313 | interdependent multi-session agentic tasks | 「記憶で後続行動が改善するか」への転換点 |
| AMA-Bench | 2026 | arXiv:2602.22769 https://arxiv.org/abs/2602.22769 | real/synthetic agentic trajectories, causality/objective info | dialogue ではなく agent-environment trace へ |
| MemEvoBench | 2026 | arXiv:2604.15774 https://arxiv.org/abs/2604.15774 | memory misevolution safety | 汚染・偏り・noisy tool output による drift |
| LongMemEval-V2 | 2026 | arXiv:2605.12493 https://arxiv.org/abs/2605.12493 | web environment experience, workflow/gotchas | 「経験豊富な同僚」型評価 |
| EvoMemBench | 2026 | arXiv:2605.18421 https://arxiv.org/abs/2605.18421 | in/cross-episode x knowledge/execution memory | self-evolving 観点の横断 benchmark |
| STATE-Bench | 2026 | Microsoft OSS blog/GitHub https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/ | enterprise task completion, reliability, efficiency, UX | production で memory が agent を改善したかを見る |

## 3. Hype と実用寄りの切り分け

### 実用寄り

| 領域 | なぜ実用寄りか | 代表 |
|---|---|---|
| Hybrid retrieval + rerank + evidence | 既存 stack に入れやすく、latency/cost を測れる | Mem0, Zep, LongMemEval 系 |
| Typed memory + provenance | 誤記憶、矛盾、削除、監査に必要 | Rethinking Memory, MIRIX, surveys |
| Offline consolidation | online latency を抑えつつ memory quality を上げる | LightMem, ReSum |
| Procedural / runbook memory | coding/web/enterprise agent の同じ失敗を減らしやすい | Voyager, AWM, Agent KB, LongMemEval-V2 |
| Agentic benchmark | recall ではなく task success/reliability を測る | MemoryArena, AMA-Bench, STATE-Bench |
| Safety/gov metrics | persistent memory には必須 | MemEvoBench |

### Hype が強い

| 領域 | Hype 理由 | 実用化する条件 |
|---|---|---|
| Human-like memory / brain metaphor | 用語が大きく、評価が recall に落ちがち | provenance、更新規則、失敗時の削除/訂正 |
| Universal memory OS | 抽象は魅力的だが subsystem 境界が広すぎる | small API、明確な memory type、実測 latency/cost |
| Self-evolving memory | benchmark は出始めたが安全・再現性が弱い | memory drift / poisoning / stale update の評価 |
| Latent memory / model-coupled memory | 閉じたモデルや汎用 agent stack に入れにくい | adapter 化、ablation、運用 observability |
| Graph everything | graph 抽出が誤ると強く壊れる | bounded traversal、typed edge、原典 evidence |
| 単一 benchmark SOTA | LoCoMo/LongMemEval は benchmark leakage や context window 問題が出やすい | 複数 benchmark、task success、cost、safety を併記 |

## 4. MemoryArena の位置づけ

MemoryArena は 2026 年型の agent memory benchmark の中でかなり重要な位置にある。理由は、既存 benchmark の弱点をかなり明示的に突いているため。

### MemoryArena が置かれる地図

| 世代 | Benchmark | 中心問い | MemoryArena との差 |
|---|---|---|---|
| 会話 recall | LoCoMo, LongMemEval | 過去会話の事実・時間・更新を答えられるか | MemoryArena は会話 QA ではなく agentic task で見る |
| 長大 context stress | BEAM | 10M token 級でも覚えられるか | MemoryArena は長さより interdependent tasks |
| memory 能力分解 | MemoryAgentBench | retrieval / TTL / LRU / forgetting を測る | MemoryArena は能力単体でなく行動ループ |
| agent trace memory | AMA-Bench | machine-generated agent-environment trace を扱えるか | MemoryArena は multi-session task dependency を重視 |
| experience colleague | LongMemEval-V2 | web環境の workflow/gotcha を覚えるか | MemoryArena はより汎用的な agentic environment gym |
| production task reliability | STATE-Bench | memory が enterprise task success/reliability を上げるか | MemoryArena は研究 benchmark 寄り |

### MemoryArena の特徴

| 項目 | 内容 |
|---|---|
| 論文 | MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks |
| 年 / ID | 2026, arXiv:2602.16313 |
| URL | https://arxiv.org/abs/2602.16313 |
| 問い | agent が前 session の行動・feedback を memory に蒸留し、後続 session のタスク解決に使えるか |
| タスク領域 | web navigation、preference-constrained planning、progressive information search、sequential formal reasoning |
| 重要な主張 | LoCoMo などで高性能な agent でも agentic setting では弱いことを示す |
| 位置づけ | recall benchmark と action benchmark の間をつなぐ、2026 の frontier benchmark |

### MemoryArena をどう読むべきか

| 読み | コメント |
|---|---|
| 強い点 | 「記憶を持っている」ではなく「記憶が行動に効く」を測る |
| 弱い点 | 実 product の memory governance、編集、所有権、削除、privacy までは主対象でない |
| LoCoMo/LongMemEval との関係 | 代替というより上位補完。conversation recall ができても agentic memory とは限らない |
| mew への軽い含意 | coding agent memory を見るなら、recall accuracy だけでなく「次の tool choice / repair / verification が改善したか」を測る必要がある |

## 5. Agent memory の評価指標としてよく使われるもの

### 指標カテゴリ

| カテゴリ | 指標例 | 使われる benchmark / 論文 | 何が見えるか | 限界 |
|---|---|---|---|---|
| Retrieval quality | Recall@k, precision@k, MRR, evidence recall | LongMemEval, RAG baselines, Neuromem | 必要 memory を引けるか | 引けても使えるとは限らない |
| QA accuracy | Exact Match, F1, LLM-as-judge score | LoCoMo, LongMemEval, BEAM | 過去情報で答えられるか | judge 品質、context stuffing に弱い |
| Temporal reasoning | temporal QA accuracy, latest-fact accuracy | LongMemEval, Zep, LoCoMo | 更新・時系列に強いか | 実作業手順は測りにくい |
| Multi-hop reasoning | multi-hop F1/accuracy | LoCoMo, A-MEM, GAM | 複数 memory を結べるか | graph 抽出品質と混ざる |
| Update / forgetting | selective forgetting, conflict resolution, abstention | MemoryAgentBench, LongMemEval | 古い事実を上書き/無視できるか | 「忘れるべきか」の ground truth が難しい |
| Test-time learning | new rule/label/task adaptation accuracy | MemoryAgentBench, Evo-Memory | deployment 中に学べるか | training/eval leakage に注意 |
| Downstream task success | success rate, pass@1, pass^n, completion rate | MemoryArena, STATE-Bench, AMA-Bench | memory が行動に効くか | 原因が memory か planning か分離しにくい |
| Reliability | pass^5, variance across runs | STATE-Bench | 一回当たりでなく安定して成功するか | 実行コストが高い |
| Efficiency | latency, token cost, API calls, storage size | Mem0, LightMem, Neuromem, STATE-Bench | production viability | 精度と tradeoff |
| Streaming degradation | accuracy over rounds, insertion/retrieval latency | Neuromem, Evo-Memory | memory が増えるほど壊れないか | 長期実験が重い |
| Safety / drift | misevolution rate, biased memory impact, poisoning robustness | MemEvoBench | persistent memory の安全性 | 新しい領域で標準化途中 |
| UX / interaction | user experience score, user effort, consent | STATE-Bench | enterprise agent の実用性 | LLM judge 依存 |

### Benchmark ごとの評価能力

| Benchmark | Recall | Reasoning | Update/forget | Agent action | Cost/latency | Safety | コメント |
|---|---:|---:|---:|---:|---:|---:|---|
| LoCoMo | 高 | 中-高 | 中 | 低 | 低 | 低 | 会話 memory の基礎 |
| LongMemEval | 高 | 高 | 高 | 低 | 中 | 低 | chat assistant memory 標準 |
| BEAM | 高 | 高 | 中 | 低 | 中 | 低 | long-context stuffing 対策寄り |
| MemoryAgentBench | 高 | 高 | 高 | 中 | 中 | 低 | 4能力の切り分け |
| MemoryArena | 中 | 高 | 中 | 高 | 中 | 低 | agentic memory への橋渡し |
| AMA-Bench | 中 | 高 | 中 | 高 | 中 | 低 | agent-environment trace と causality |
| Evo-Memory | 中 | 高 | 高 | 中-高 | 中 | 低 | self-evolving/test-time learning |
| LongMemEval-V2 | 中 | 高 | 中 | 高 | 高 | 低 | web workflow/gotcha/experience |
| STATE-Bench | 低 | 中 | 中 | 高 | 高 | 中 | production reliability 寄り |
| MemEvoBench | 中 | 中 | 高 | 中 | 中 | 高 | memory safety frontier |

## 6. 2026時点の「主流キーワード」

| キーワード | 意味 | 重要度 |
|---|---|---:|
| write-manage-read loop | memory を storage でなく lifecycle として見る | 高 |
| consolidation | raw event を durable memory に変換・統合 | 高 |
| selective forgetting | 古い/不要/危険な memory を抑制・削除 | 高 |
| conflict resolution | 矛盾や更新の扱い | 高 |
| temporal knowledge graph | 時間つき entity/relation memory | 高 |
| causality graph | 類似ではなく因果で agent trace を引く | 中-高 |
| procedural memory | 手順・失敗回避・skill/runbook の記憶 | 高 |
| test-time learning | deployment 中に経験から改善 | 中-高 |
| memory-as-action | memory 編集を agent action として扱う | 中 |
| sleep-time update | online path 外で整理・圧縮 | 中-高 |
| context gathering | memory system が compact evidence を返す評価形式 | 中-高 |
| pass^n / reliability | 同じ task を複数回安定して解けるか | 高 |
| memory misevolution | 汚染された memory による drift | 伸長中 |

## 7. まとめ: 2026 の流行だけを圧縮すると

| 問い | 答え |
|---|---|
| 何が一番主流か | retrieval + typed/lifecycle memory + cost-aware evaluation |
| 何が研究 frontier か | graph/causal/procedural/self-evolving/learned memory manager |
| 何が hype か | human-like universal memory、memory OS、self-evolving claims、単一 benchmark SOTA |
| 何が実用寄りか | provenance つき memory、bounded retrieval、offline consolidation、procedural/runbook memory、task-success 評価 |
| MemoryArena は何か | agent memory を「後続行動に効くか」で測る 2026 型 benchmark |
| 評価指標の主流 | Recall/F1/accuracy から、task success、pass^n、latency/token cost、update/forget、安全性へ拡張中 |

## mew への軽い含意

mew の memory subsystem 設計前に見るべき流行は、巨大な自律的記憶ではなく、まず「小さく、typed で、根拠を持ち、後続行動を改善する memory」である。特に coding agent としては、ユーザー嗜好より先に、procedural memory、failure memory、project convention、reviewer correction、environment gotcha を評価対象にする方が 2026 の実用トレンドに近い。

## Source inventory

| Source | URL |
|---|---|
| A Survey on the Memory Mechanism of Large Language Model based Agents | https://arxiv.org/abs/2404.13501 |
| From Human Memory to AI Memory | https://arxiv.org/abs/2504.15965 |
| Rethinking Memory in LLM based Agents | https://arxiv.org/abs/2505.00675 |
| Memory for Autonomous LLM Agents | https://arxiv.org/abs/2603.07670 |
| From Storage to Experience | https://arxiv.org/abs/2605.06716 |
| Reflexion | https://arxiv.org/abs/2303.11366 |
| Generative Agents | https://arxiv.org/abs/2304.03442 |
| MemoryBank | https://arxiv.org/abs/2305.10250 |
| Voyager | https://arxiv.org/abs/2305.16291 |
| ExpeL | https://arxiv.org/abs/2308.10144 |
| CoALA | https://arxiv.org/abs/2309.02427 |
| MemGPT | https://arxiv.org/abs/2310.08560 |
| Agent Workflow Memory | https://arxiv.org/abs/2409.07429 |
| Zep | https://arxiv.org/abs/2501.13956 |
| A-MEM | https://arxiv.org/abs/2502.12110 |
| Mem0 | https://arxiv.org/abs/2504.19413 |
| MEM1 | https://arxiv.org/abs/2506.15841 |
| MemOS | https://arxiv.org/abs/2507.03724 |
| MIRIX | https://arxiv.org/abs/2507.07957 |
| Memory-R1 | https://arxiv.org/abs/2508.19828 |
| ReSum | https://arxiv.org/abs/2509.13313 |
| MemGen | https://arxiv.org/abs/2509.24704 |
| Memory as Action | https://arxiv.org/abs/2510.12635 |
| LightMem | https://arxiv.org/abs/2510.18866 |
| Fine-Mem | https://arxiv.org/abs/2601.08435 |
| AgeMem | https://arxiv.org/abs/2601.01885 |
| Neuromem | https://arxiv.org/abs/2602.13967 |
| GAM | https://arxiv.org/abs/2604.12285 |
| delta-mem | https://arxiv.org/abs/2605.12357 |
| LoCoMo | https://arxiv.org/abs/2402.17753 |
| LongMemEval | https://arxiv.org/abs/2410.10813 |
| MemoryAgentBench | https://arxiv.org/abs/2507.05257 |
| BEAM | https://arxiv.org/abs/2510.27246 |
| Evo-Memory | https://arxiv.org/abs/2511.20857 |
| MemoryArena | https://arxiv.org/abs/2602.16313 |
| AMA-Bench | https://arxiv.org/abs/2602.22769 |
| MemEvoBench | https://arxiv.org/abs/2604.15774 |
| LongMemEval-V2 | https://arxiv.org/abs/2605.12493 |
| EvoMemBench | https://arxiv.org/abs/2605.18421 |
| STATE-Bench | https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/ |
