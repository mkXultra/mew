# M6.24 Gap Baseline - 2026-04-29

Purpose: freeze the current measured Codex gap before M6.24 switches from
broad measurement to the measurement / improvement loop. This prevents context
compression from drifting back to "just run the next batch" when the measured
evidence says improvement is higher value.

Scope:

- Source ledgers: `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` through
  `docs/M6_24_BATCH_6_RUNS_2026-04-29.md`
- Count policy: use latest recorded task results in the batch ledgers. Runner
  and setup errors count as failures unless a ledger explicitly excludes a
  partial/control run.
- Batch 6 is partial: it includes `feal-linear-cryptanalysis`,
  `fix-ocaml-gc`, and `git-multibranch` only.

## Aggregate

| Scope | mew successes | Codex target successes | mew rate | Codex rate | absolute gap | relative success |
|---|---:|---:|---:|---:|---:|---:|
| Batches 1-6 measured subset | 92/210 | 156/210 | 43.8% | 74.3% | -30.5 pp | 59.0% |

Interpretation:

- mew has 64 fewer successes than Codex on the measured subset.
- mew currently achieves about 59.0% of Codex's measured successes.
- The gap is large enough that additional broad measurement has lower value
  than closing the dominant generic gap classes.

## Batch Breakdown

| Batch | mew | Codex target | absolute gap | relative success | decision |
|---|---:|---:|---:|---:|---|
| Batch 1 | 22/40 = 55.0% | 25/40 = 62.5% | -7.5 pp | 88.0% | continue/classify |
| Batch 2 | 16/40 = 40.0% | 27/40 = 67.5% | -27.5 pp | 59.3% | improvement signal |
| Batch 3 | 2/40 = 5.0% | 24/40 = 60.0% | -55.0 pp | 8.3% | improvement signal |
| Batch 4 | 11/35 = 31.4% | 25/35 = 71.4% | -40.0 pp | 44.0% | improvement signal |
| Batch 5 | 31/40 = 77.5% | 40/40 = 100.0% | -22.5 pp | 77.5% | improvement signal |
| Batch 6 partial | 10/15 = 66.7% | 15/15 = 100.0% | -33.3 pp | 66.7% | improvement signal |

## Controller Decision

M6.24 should enter improvement phase now.

Reason:

- Aggregate gap is -30.5 percentage points.
- Four completed/partial batches exceed the `> 20 pp` improvement threshold.
- Continuing with new broad measurement would mostly increase confidence that
  mew is behind Codex, not close the gap.

Next action:

1. Stop spending new broad-measurement budget on the next Batch 6 task.
2. Build/update `docs/M6_24_DECISION_LEDGER.md` with this decision.
3. Classify measured failures into gap classes.
4. Select one generic repair target.
5. Rerun the same failed task shape after the repair.
6. Resume broad measurement only after the rerun result is recorded.

Non-goal:

- Do not add Terminal-Bench-specific solvers. Repairs must improve the generic
  arbitrary-workspace work-session path.
