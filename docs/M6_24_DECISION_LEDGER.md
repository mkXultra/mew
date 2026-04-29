# M6.24 Decision Ledger

Purpose: keep the measure-vs-improve decisions for M6.24 in one compact,
append-friendly file so long sessions and context compression do not drift back
to stale next-batch execution.

## Controller Rule

After each batch or partial batch checkpoint, compare mew against the frozen
Codex target for the same measured trials.

Decision thresholds:

- `gap <= 10 percentage points`: classify any misses and continue broad
  measurement.
- `10 < gap <= 20 percentage points`: record gap classes and continue broad
  measurement unless the same class repeats across batches.
- `gap > 20 percentage points`: pause broad measurement and enter improvement
  phase.
- accepted structural blocker at any gap: pause M6.24, append/update
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, repair through M6.14, rerun the
  same failed shape, then resume M6.24.
- aggregate gap `> 20 percentage points` across three consecutive measured
  batches: enter improvement phase even if the latest batch alone is mixed.

Improvement phase requirements:

1. Choose exactly one generic gap class.
2. Name the failed task shape that will be rerun after repair.
3. Do not add Terminal-Bench-specific solvers.
4. Record before/after evidence.
5. Resume broad measurement only after the rerun is recorded or a written
   decision explains why the repair cannot be validated with the same shape.

## Decisions

| Date | Decision | Evidence | Next action | Status |
|---|---|---|---|---|
| 2026-04-29 | Enter M6.24 improvement phase; stop new broad measurement for now. | `docs/M6_24_GAP_BASELINE_2026-04-29.md`: measured subset is mew 92/210 = 43.8% vs Codex 156/210 = 74.3%, gap -30.5 pp; Batch 2, 3, 4, 5, and partial Batch 6 all exceed the `> 20 pp` improvement threshold. | Classify Batch 1-6 measured failures, pick one generic gap class, repair it, and rerun the same failed shape before continuing `gpt2-codegolf` or any new broad-measurement task. | active |

## Current Mode

`improvement_phase`

Do not run the next broad-measurement task merely because
`docs/M6_24_BATCH_6_MANIFEST_2026-04-29.md` lists `gpt2-codegolf` as pending.
That was the previous measurement-only next action. The current M6.24 controller
decision supersedes it.
