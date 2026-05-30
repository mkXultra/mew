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

## 2026-05-28 - Fresh deterministic MemBench backend rerun

Context:

- Commit under test: `4ca0334`.
- Commands:
  - `uv run python -m mew.memory_eval.membench profile membench-sample1000-typed --clean --typed-cards-summary-search-backend direct_scan_lexical --work-dir tmp/membench-rerun-20260528-direct --output tmp/membench-rerun-20260528-direct/report.json`
  - `uv run python -m mew.memory_eval.membench profile membench-sample1000-typed --clean --typed-cards-summary-search-backend bm25 --work-dir tmp/membench-rerun-20260528-bm25 --output tmp/membench-rerun-20260528-bm25/report.json`
- Note: both commands emitted an unauthenticated Hugging Face Hub warning only; the profile completed.

Results:

| Artifact | Backend | Status | Typed-card results | Avg `recall_at_k` | Avg `mrr_at_k` | Avg `ndcg_at_k` | Avg `precision_at_k` | Avg `support_recall_at_k` | Scope/stale failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `tmp/membench-rerun-20260528-direct/report.json` | `direct_scan_lexical` | passed | 10/10 passed | 1.000 | 0.933 | 0.950 | 0.200 | 1.000 | none observed |
| `tmp/membench-rerun-20260528-bm25/report.json` | `bm25` | passed | 10/10 passed | 1.000 | 0.933 | 0.950 | 0.200 | 1.000 | none observed |

Decision:

- The current deterministic MemBench sample1000 typed-card profile is green for both `direct_scan_lexical` and `bm25`.
- BM25 still does not outperform direct lexical on this profile; keep the default summary-search backend unchanged for now.
- Do not implement vector/embedding search solely to improve this profile. Keep vector/hybrid as an injectable backend to test when a larger profile or a failing relation/paraphrase fixture shows a need.
- Next memory work should move to the remaining graph/index validation slice or the Phase E/F read-only provider schema, while keeping MemBench reruns appended here.

## 2026-05-28 - Graph Expansion Value-Add Fixture

Context:

- New fixture: `fixtures/memory_eval/p1/graph_value_add_relation_basic.json`.
- Test command:
  - `uv run pytest --no-testmon -q tests/test_memory_eval_typed_cards_adapter.py::test_graph_value_add_fixture_compares_graph_off_and_graph_on_recall`

Result:

- Graph-off baseline request passed with `index_mode=direct_scan`, zero graph expansion counts, and no `exp_graph_value_related` support returned.
- Graph-on request passed with `index_mode=graph_index`, `graph_nodes_expanded >= 2`, `graph_edges_expanded >= 1`, and `graph_cards_expanded >= 1`.
- The same query returned the graph-only related support `exp_graph_value_related` only when `expand_graph=true`.

Decision:

- Memory eval now covers graph expansion value-add, not only correctness/safety.
- This fixture demonstrates that graph expansion can recover a related memory whose text does not directly match the query terms but shares a role-bearing graph edge with the seed memory.

## 2026-05-28 - Graph Budget Controls Fixture

Context:

- New fixture: `fixtures/memory_eval/p1/graph_budget_controls_basic.json`.
- Test command:
  - `uv run pytest --no-testmon -q tests/test_memory_eval_typed_cards_adapter.py::test_graph_budget_controls_fixture_passes_with_scorer_visible_limits`

Result:

- Fanout request passed with `index_mode=graph_index`, `graph_edges_expanded == 1`, `graph_cards_expanded <= 1`, and aggregate `graph_fanout_budget_exhausted` drops.
- Projection-char request passed with `projection_chars <= 240` and aggregate `projection_char_budget_exhausted` drops.
- Latency request passed with `graph_max_latency_ms=0`, direct-scan fallback usage, zero graph expansion counts, and aggregate `graph_latency_budget_exhausted` drops.

Decision:

- Memory eval now covers scorer-visible graph expansion budget limits, not only happy-path graph retrieval.
- `gold.expected_usage` supports both `min_*` and `max_*` count gates, so fixtures can catch over-expansion without exposing hidden budget expectations to the adapter.

## 2026-05-28 - Graph Redacted Edge-Support Fixture

Context:

- New fixture: `fixtures/memory_eval/p1/graph_redacted_edge_support_no_leak_basic.json`.
- Test command:
  - `uv run pytest --no-testmon -q tests/test_memory_eval_typed_cards_adapter.py::test_graph_negative_fixtures_do_not_leak_blocked_support`

Result:

- The fixture seeds a graph edge with a dedicated support experience, then forgets that support experience before recall.
- Recall passed with the related graph target absent, aggregate `missing_graph_edge_evidence` drops, and no caller-visible edge/provenance IDs.
- Derived graph index verification passed the scorer-only expectation for `ok=false` and `graph_edge_support_evidence_unavailable >= 1`.

Decision:

- Graph expansion now gates both normal edge traversal and seed-card edge-derived frontier construction on visible graph-edge support evidence.
- Memory eval covers redacted graph-edge support drift through derived verifier issue counts, not only through direct retrieval absence.
