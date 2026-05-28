# M6.25 Memory Eval Log

Status: append-only operational evaluation log for M6.25 typed-card memory.

Purpose: keep memory-eval observations, MemBench runs, backend comparisons, and live-model smoke results in one place so roadmap decisions do not drift from observed evidence.

Append rules:

- Add a new dated entry for each evaluation run or artifact backfill.
- Do not rewrite old entries except to add a clearly marked correction note.
- Each entry should include command or artifact path, backend/model, extractor mode, pass/fail summary, key retrieval metrics, and the decision it supports.
- Treat `tmp/` artifact paths as local evidence, not durable product proof, until copied or summarized into this log.
- Deterministic replay runs are gating candidates. Live model runs are opt-in diagnostics unless a later roadmap decision explicitly promotes them.

## 2026-05-27 - Backfill from existing local artifacts

Context:

- Current checked commit while writing this log: `e84fb73`.
- Relevant recent commits:
  - `09d5ed1` Add injectable memory summary search backend.
  - `54ede60` Allow MemBench typed-card backend selection.
  - `89294a0` Improve deterministic replay memory retrieval.
  - `dbff054` Add opt-in live MemBench typed-card eval.
  - `f1b8051` Register deferred MemBench validation profiles.
  - `8a65e10` Improve trace normalization and memory eval coverage.
- This entry summarizes existing artifacts and committed tests. It did not rerun the evaluations.

### Relation-sensitive niece/company fixture

Evidence:

- Fixture: `fixtures/memory_eval/p1/relation_sensitive_niece_company_basic.json`.
- Test: `tests/test_memory_eval_typed_cards_adapter.py::test_relation_sensitive_niece_company_fixture_asserts_top1_scope_and_support`.

Observed behavior:

- Top-1 request returns only `exp_niece_current_company`.
- `recall_at_k == 1.0`, `mrr_at_k == 1.0`, `precision_at_k == 1.0`.
- No cross-scope exposure.
- Superseded old company, forgotten raw match, unrelated company, and same-company other-scope distractors are not returned.

Decision:

- The relation-sensitive fixture requested after the MemBench rank-6 failure is present and committed.
- It covers top-1 precision, scope safety, stale/forget behavior, and active support correctness for the niece/company shape.

### Deterministic MemBench backend comparison

Evidence artifacts:

| Artifact | Backend | Status | Result summary |
| --- | --- | --- | --- |
| `tmp/membench-backend-smoke/direct/report.json` | `direct_scan_lexical` | passed | 1/1 typed-card smoke passed. |
| `tmp/membench-backend-smoke/bm25/report.json` | `bm25` | passed | 1/1 typed-card smoke passed. |
| `tmp/membench-backend-sample/direct/report.json` | `direct_scan_lexical` | failed | 2/10 passed before retrieval improvements. |
| `tmp/membench-backend-sample/bm25/report.json` | `bm25` | failed | 2/10 passed before retrieval improvements. |
| `tmp/membench-backend-sample/direct-after-hints/report.json` | `direct_scan_lexical` | failed | 9/10 passed after retrieval hint improvements. |
| `tmp/membench-backend-sample/direct-after-stopword/report.json` | `direct_scan_lexical` | passed | 10/10 passed; avg `recall_at_k=1.000`, `mrr_at_k=0.933`, `ndcg_at_k=0.950`, `support_recall_at_k=1.000`. |
| `tmp/membench-backend-sample/bm25-after-stopword/report.json` | `bm25` | passed | 10/10 passed; avg `recall_at_k=1.000`, `mrr_at_k=0.933`, `ndcg_at_k=0.950`, `support_recall_at_k=1.000`. |
| `tmp/membench-backend-sample/direct-after-summary/report.json` | `direct_scan_lexical` | failed | 5/10 passed in the alternate summary experiment. |
| `tmp/membench-backend-sample/bm25-after-summary/report.json` | `bm25` | failed | 5/10 passed in the alternate summary experiment. |

Decision:

- `direct_scan_lexical` and `bm25` both pass the current sample1000 typed-card deterministic profile after the stopword/retrieval changes.
- BM25 did not materially outperform direct lexical on these stored artifacts.
- Keep `SummarySearchBackend` injectable; do not switch the default purely because BM25 exists.
- A future vector/hybrid comparison should use the same profile and record backend identity, embedding model, and artifact hashes here.

### Live GPT-5.5 MemBench smoke

Evidence artifacts:

| Artifact | Model/backend | Summary |
| --- | --- | --- |
| `tmp/membench-live-50call-q10/summary.json` | `codex` / `gpt-5.5`, `direct_scan_lexical` | 10 fixtures, 0 failures, status counts `passed: 10`. |
| `tmp/membench-live-50doc/live_artifact.json` | `codex` / `gpt-5.5`, `direct_scan_lexical` | 1 request passed; `recall_at_k=1.0`, `mrr_at_k=1.0`, `support_recall_at_k=1.0`. |
| `tmp/membench-live-smoke/live_artifact.json` | `codex` / `gpt-5.5`, `direct_scan_lexical` | 1 request passed; `recall_at_k=1.0`, `mrr_at_k=1.0`, `support_recall_at_k=1.0`. |

Decision:

- Live GPT-5.5 extractor smoke is working as an opt-in diagnostic.
- Keep live model eval non-gating by default because cost, auth, latency, and model drift make it unsuitable for hermetic CI.
- Use live MemBench smoke to detect extractor drift after deterministic replay stays green.

### Current next evaluation target

- Append a fresh deterministic profile rerun under the current commit after the current docs/log changes are committed.
- If lexical and BM25 remain tied, defer embedding work until a failing fixture or larger MemBench profile demonstrates a clear need.
- If vector/hybrid is tested, prefer `ollama` + `qwen3-embedding:0.6b` first and record backend identity in this log.
