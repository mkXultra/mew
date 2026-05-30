# Memory Eval Usage

Status: operational usage notes for the M6.25 memory evaluation surfaces.

This document is for running the local evaluation tools. Architecture and
design details remain in the design docs.

## Surfaces

| Surface | Use it for | Does not prove |
| --- | --- | --- |
| Generic P0/P1 fixture harness | Adapter conformance, fixture split, hashes, retrieval scoring, scope/stale/forget gates, graph-specific fixtures. | Full agent behavior or downstream task success. |
| MemBench profiles | External qrels-style retrieval checks and typed-card deterministic replay against sampled MemBench data. | Redistribution permission by itself, semantic world construction, or live-model stability. |
| Synthetic analogy minimal bench | Small deterministic semantic-structure probe with `memory_off`, `memory_on`, and `oracle_context`. | Long-term retention, structured claim scoring, terminal bench, or full agent behavior. |

## Generic Memory Eval Fixtures

The generic harness is primarily exercised through tests and fixture adapters.
Run the focused suite with:

```sh
uv run --group dev python -m pytest -q \
  tests/test_memory_eval_runner.py \
  tests/test_memory_eval_p1.py \
  tests/test_memory_eval_hashing.py \
  tests/test_memory_eval_fixture_split.py \
  tests/test_memory_eval_typed_cards_adapter.py \
  --override-ini=addopts=
```

Use this when changing adapter contracts, fixture loading, scorer behavior,
typed-card adapter behavior, or graph/index fixtures.

## MemBench Profiles

MemBench is a third-party dataset path. Read `docs/THIRD_PARTY_DATA.md` before
preparing or committing anything derived from MemBench.

The smallest local typed-card profile is:

```sh
uv run --group dev python -m mew.memory_eval.membench profile membench-smoke200-typed
```

The current deterministic sample profile is:

```sh
uv run --group dev python -m mew.memory_eval.membench profile membench-sample1000-typed
```

Larger registered profiles are:

```sh
uv run --group dev python -m mew.memory_eval.membench profile membench-full-qrels-oracle
uv run --group dev python -m mew.memory_eval.membench profile membench-sample5000-typed
uv run --group dev python -m mew.memory_eval.membench profile membench-full-typed
```

MemBench profile runs write local artifacts under `tmp/` by default. Treat
those artifacts as local evidence until summarized in `docs/M6_25_MEMORY_EVAL_LOG.md`.

## Synthetic Analogy Minimal Bench

Synthetic analogy is first-party and has no third-party data requirement. It is
a module-local manual profile command:

```sh
uv run --group dev python -m mew.memory_eval.synthetic_analogy --help
```

Run the smoke profile:

```sh
uv run --group dev python -m mew.memory_eval.synthetic_analogy \
  --profile synthetic-analogy-mvp-smoke \
  --output tmp/synthetic-analogy-smoke.json
```

Run the deterministic 20-task MVP-1 profile:

```sh
uv run --group dev python -m mew.memory_eval.synthetic_analogy \
  --profile synthetic-analogy-mvp-pack20 \
  --output tmp/synthetic-analogy-pack20.json
```

The command prints a concise human summary and writes a JSON artifact. The JSON
artifact is the source of record.

Current adapter status:

- The default profile command uses `DummyPassAdapter`.
- That confirms the benchmark harness, scoring, budget accounting, and report
  shape are usable.
- It does not prove the real typed-card memory subsystem passes this benchmark.
- Connecting `SyntheticAnalogy` to `TypedCardsMemoryEvalAdapter` is the next
  adapter-integration step.

## Reading Synthetic Analogy Output

Each profile compares the same task set across:

- `memory_off`: no memory artifact.
- `memory_on`: retrieved or harness-built memory artifact.
- `oracle_context`: scorer-supplied support context.

Key fields:

- `conditions`: aggregate accuracy, pass rate, budget metrics by condition.
- `condition_comparison`: display-only same-task-set comparison table.
- `comparisons.memory_lift`: `accuracy(memory_on) - accuracy(memory_off)`.
- `comparisons.oracle_gap`: `accuracy(oracle_context) - accuracy(memory_on)`.
- `known_limitations`: explicit non-goals for the run.

Interpretation:

- High `memory_lift` is a probe signal, not proof of memory correctness.
- `oracle_gap == 0` means the fixed solver did as well with the memory artifact
  as with oracle support for this small benchmark.
- The MVP does not evaluate long-term retention, update/forget correctness,
  structured claims, live model behavior, terminal-task success, or full agent
  behavior.

## What To Log

Append a dated entry to `docs/M6_25_MEMORY_EVAL_LOG.md` when a run informs an
M6.25 decision.

Include:

- command
- commit or working tree basis
- adapter/backend
- profile name
- output artifact path
- pass/fail summary
- key metrics
- decision supported

