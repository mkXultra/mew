# M6.25 Typed Memory Phase C Close Report - 2026-05-22

Status: Phase C implementation slice closed for typed-card adapter, deterministic P0/P1 retrieval fixtures, and opt-in live raw-memory extractor smoke.

Primary design:

- `docs/DESIGN_2026-05-22_M6_25_MEMORY_SUBSYSTEM_TYPED_CARDS_PLAN.md`

Related implementation commits:

- `5bb09c2 Implement M6.25 typed memory cards`
- `9bca59e Add live typed-card memory eval runner`
- `cb3dbdb Add retrieval anchors for typed memory cards`

## Scope Closed

This close report covers the implementation-independent memory-eval adapter path for the typed-card memory subsystem:

- typed `MemoryCard` / `MemoryCandidate` schema and provenance-backed ingest;
- proposal-only raw ingest with explicit lifecycle commit paths;
- deterministic direct-scan recall/ranking over committed cards;
- adapter bridge to the generic memory-eval harness using public mutate lifecycle setup;
- opt-in live LLM extraction through `mew.memory_eval_live_runner`;
- retrieval anchors via `retrieval_terms`, so raw identifying terms remain searchable even when summary/details are synthesized.

This does not close Phase D graph/index expansion, Phase E `MemoryContextBuilder`, read-only tool/provider integration, or downstream model-in-loop utility evaluation.

## Key Decision

`retrieval_terms` are committed card fields, not hidden prompt text and not raw transcript storage.

They exist because live LLM extraction may paraphrase `summary` / `details` and drop discriminators needed for deterministic retrieval. The failure that triggered this was:

```text
raw primary:   Mira uses badge color cobalt for launch reviews.
raw secondary: Mira uses badge color silver for archive reviews.
query:         Which badge color does Mira use for launch reviews?
```

Without retrieval anchors, live extraction could rank the archive-review memory above the launch-review memory. The fix preserves concise anchors such as `Mira`, `badge`, `color`, `cobalt`, `launch`, and `reviews` as search inputs while keeping raw transcript payloads in provenance.

## Verification

Deterministic targeted tests:

```bash
uv run pytest -o addopts= \
  tests/test_memory_typed_cards_phase_a.py \
  tests/test_memory_typed_cards_phase_b.py \
  tests/test_memory_eval_typed_cards_adapter.py \
  tests/test_memory_eval_live_runner.py -q
```

Result:

```text
86 passed
```

Lint:

```bash
uv run ruff check \
  src/mew/memory_typed_cards.py \
  src/mew/memory_typed_card_core.py \
  src/mew/memory_eval/adapters/typed_cards.py \
  tests/test_memory_typed_cards_phase_a.py \
  tests/test_memory_typed_cards_phase_b.py \
  tests/test_memory_eval_typed_cards_adapter.py \
  tests/test_memory_eval_live_runner.py
```

Result:

```text
All checks passed
```

Live LLM normal fixture smoke:

```bash
uv run python -m mew.memory_eval_live_runner \
  fixtures/memory_eval/p1/budget_limited_basic.json \
  --auth-json /Users/mk/.codex/auth.json
```

Observed result:

```text
status_counts: {"passed": 1}
top_1_support: ["exp_primary_badge"]
```

Full normal 9-fixture live smoke was rerun with `gpt-5.5` and explicit `/Users/mk/.codex/auth.json`.

Artifacts:

- `.codex-artifacts/memory-eval-live/manual-normal-9-20260522-rerun/`

Observed result:

```text
FAILED_COUNT 0
```

The prior failing fixture now returns:

```text
budget_limited_basic.json
status_counts: {"passed": 1}
top_support: ["exp_primary_badge"]
```

Multi-review controller result:

- artifact root: `.codex-artifacts/orchestrate-build-review/typed-card-live-extractor/`
- final round: reviewer slots `codex`, `glm5.1`, and `claude` returned `findings: []`.

## Close-Criteria Mapping

| Criterion | Evidence |
| --- | --- |
| Core does not import harness internals. | Existing typed-card adapter tests and static structure keep harness imports in `src/mew/memory_eval/adapters/typed_cards.py`, not core. |
| `ingest` creates provenance and candidate/proposal only. | Adapter and core tests cover proposal-only ingest and explicit `seed_eval` lifecycle commit. |
| Public `seed_eval` setup is explicit and audit-visible. | Typed adapter tests cover public mutate lifecycle setup and seeded-card ranking equivalence. |
| Retrieve returns scorable support IDs from active current-support links. | P1 fixture smoke and typed adapter tests pass. |
| Mutations preserve update/delete/forget/supersede semantics. | P1 `update_forget_basic` and `stale_conflict_supersede_basic` pass in deterministic and live smoke paths. |
| Usage reporting includes fixed counts and index mode. | Adapter artifacts include latency/count/projection/index-mode usage blocks. |
| Live raw-memory extraction works through `gpt-5.5` without entering CI. | `mew.memory_eval_live_runner` is opt-in and was run manually with explicit auth. |
| Retrieval anchors preserve discriminators for budget-limited ranking. | `budget_limited_basic` live smoke now passes with `exp_primary_badge` top-1. |

## Residual Risks

- Stored-card stable hashes change when `retrieval_terms` are populated; this is acceptable for the current pre-migration slice but must be handled explicitly by any durable migration.
- Direct-scan lexical scoring is still a Phase B implementation. It is inspectable and deterministic, but not yet a graph-aware or optimized index.
- `retrieval_terms` improve recall but do not replace applicability, invalidators, privacy gates, or provenance inspection.
- Live LLM extraction remains non-deterministic and should stay out of default CI. It is a smoke check, not a golden deterministic gate.
- Existing unrelated dirty files in the working tree were not part of this close report.

## Next Work

Recommended next step before Phase D:

1. Add a small CLI/report command or documented script for running the normal 9-fixture live smoke without ad hoc Python snippets.
2. Decide whether `retrieval_terms` should be surfaced in debug/inspect output, and under which privacy gate.
3. Only then start Phase D graph/index expansion, keeping indexes derived and rebuildable.

