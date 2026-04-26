# M6.13 Close-Readiness Audit (2026-04-26)

Recommendation: NOT_CLOSE_READY.

This audit records the current M6.13 Phase 3 internalization state after the
live-provider dogfood proof was strengthened. It is intentionally not a close
gate.

## Evidence Now Available

- `m6_13-deliberation-internalization` records a deliberation-assisted hard
  task, a distilled `source_lane=deliberation` reasoning trace, and a later
  same-shape tiny-lane planning attempt.
- The scenario now emits a reviewer decision artifact reference under
  `.mew/durable/review/`.
- `mew memory --active --task-id` emits observable scored recall metadata:
  ranker name, score, rank, score components, matched terms, and top entry
  ids.
- The M6.13 dogfood trace records `contract_cycle_proven=true` when the
  deliberation result, trace write, scored recall, and tiny patch-draft reuse
  contract all pass.
- The deterministic proof and live `gpt-5.5` proof both pass.

## Why This Is Not Close Evidence Yet

M6.13's close gate requires a full internalization cycle:

1. deliberation solves or materially advances a hard task
2. reviewer approval writes a `source_lane=deliberation` reasoning trace
3. a later same-shape task retrieves the trace through M6.9 ranked recall
4. the later task is solved by tiny without re-invoking deliberation
5. reviewer evidence confirms the trace shortened or avoided deliberation

The current artifact proves the contract shape, but it still records
`close_evidence=false` for three reasons:

- M6.9 ranked recall with recency, importance, symbol overlap, and task-shape
  components is not the recall source yet. The current event is scored active
  recall, not the final M6.9 ranked recall scorer.
- Reviewer approval is represented by a scenario artifact, not an independent
  reviewer decision consumed from outside the scenario.
- The later same-shape task proves validated tiny patch planning, not an
  applied and verified tiny-only solve.

## Reviewer Check

Codex-ultra reviewed the first `close_evidence=true` attempt and rejected it
as overclaimed. After revision, the same reviewer approved the current shape:

- `close_evidence=false`
- `contract_cycle_proven=true`
- `scored_recall_event` instead of M6.9 ranked-recall close proof
- explicit `close_blockers`

Reviewer session: `019dc96d-a73d-7762-baa4-6af2430c61b9`.

## Accepted Validation

- `uv run pytest -q tests/test_dogfood.py -k 'm6_13_deliberation_internalization or m6_13_live_provider or scenario_choices' --no-testmon`
- `uv run pytest -q tests/test_memory.py -k 'memory_active or reasoning_trace' --no-testmon`
- `uv run pytest -q tests/test_work_session.py -k 'active_memory or write_ready_tiny or compact_active_memory_preserves_reasoning_trace_provenance' --no-testmon`
- `uv run pytest -q tests/test_dogfood.py --no-testmon`
- `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --json`
- `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model gpt-5.5 --model-timeout 180 --json`
- `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --model gpt-5.5 --model-timeout 180 --json`
- `uv run ruff check src/mew/work_session.py src/mew/dogfood.py tests/test_dogfood.py tests/test_memory.py`
- `git diff --check`

## Next Close Tasks

The next M6.13 work should close one of the recorded blockers, in this order:

1. Route the later-task recall proof through the real M6.9 ranked recall
   scorer, or explicitly add that scorer before claiming M6.13 close.
2. Consume an independent reviewer decision artifact instead of synthesizing
   approval inside the scenario.
3. Extend the later same-shape proof from validated tiny patch planning to an
   applied and verified tiny-only solve.

Do not mark M6.13 done until all three are resolved or the close gate is
explicitly rewritten.
