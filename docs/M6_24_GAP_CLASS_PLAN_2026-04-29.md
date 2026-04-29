# M6.24 Gap Class Plan - 2026-04-29

Purpose: classify the current measured M6.24 gap into repairable classes and
select the first improvement target under `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`.

## Source Evidence

- `docs/M6_24_GAP_BASELINE_2026-04-29.md`: mew 92/210 = 43.8% vs Codex
  156/210 = 74.3%, aggregate gap -30.5 percentage points.
- `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` through
  `docs/M6_24_BATCH_6_RUNS_2026-04-29.md`.
- `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`: already accepted structural
  substrate repairs SR-001 through SR-017.
- `docs/ADOPT_FROM_REFERENCES.md` and
  `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` for reference-derived
  implementation-lane architecture.

## Current Classification

| Gap class | Classification | Evidence | Status |
|---|---|---|---|
| Hard-task implementation strategy / contract retention | structural at implementation-lane level | `make-doom-for-mips`, `make-mips-interpreter`, `video-processing`, `mcmc-sampling-stan`, `compile-compcert`, `crack-7z-hash`, `count-dataset-tokens`, `custom-memory-heap-crash`, `fix-ocaml-gc`, `git-multibranch` | selected first |
| Long dependency / wall-budget observability | structural substrate, mostly repaired | SR-001, SR-012, SR-014, SR-015; residual task-solving remains on `financial-document-processor`, `protein-assembly`, `adaptive-rejection-sampler`, `compile-compcert` | watch after selected class |
| Artifact / visual / document observation | structural substrate, partially repaired | SR-003 fixed `extract-moves-from-video` proof; `code-from-image` reached 5/5 after `read_image`; PDF/document observation still appears in `financial-document-processor` | defer unless repeated after strategy work |
| Runner / harness configuration | structural or external runner debt | `/tmp` permission SR-016, Harbor timeout mapping SR-012, `torch-pipeline-parallelism` disk/temp exhaustion, `git-multibranch` setup error | repair only when repeated or blocking measurement |
| Local numeric / precision polish | local/polish | `count-dataset-tokens` 4/5, `custom-memory-heap-crash` 4/5, `fix-ocaml-gc` 4/5 | defer until broader strategy class is addressed |
| Measurement missing / partial | measurement_missing | `train-fasttext` partial low-target control, `git-multibranch` 1 setup error and 4 completed trials | add data only when these shapes are selected |

## Selected First Gap Class

Selected gap:

`hard_task_implementation_strategy_contract_retention`

One-line chain:

```text
M6.24 -> hard_task_implementation_strategy_contract_retention -> reference-backed implementation-lane design/repair -> rerun one same-shape hard task where Codex target is high and mew currently fails
```

Rationale:

- It explains the largest unrepaired portion of the measured gap better than
  another permission or timeout slice.
- Many major misses are now recorded as "task-solving" after lower-level
  substrate blockers were repaired. That does not mean they are purely model
  capability failures. It means the current mew work loop does not yet force
  enough task decomposition, source grounding, patch lifecycle discipline, and
  verifier-driven repair for hard terminal tasks.
- Codex and Claude Code reference patterns are directly relevant here:
  task/todo tracking, patch/review/apply loops, context contract windows,
  structured approval/rejection, and fail-closed tool policy.

Non-goal:

- Do not build a task-specific solver for any Terminal-Bench task.
- Do not run a new broad benchmark task until the selected class has either a
  repair and same-shape rerun, or a decision-ledger entry rejecting the repair.

## Rerun Candidate

Preferred same-shape rerun after the repair:

1. `make-doom-for-mips` or `make-mips-interpreter`
   - Reason: repeated surrogate/stub strategy against a concrete external
     verifier; no major runner error after existing substrate repairs.
   - Expected improvement signal: fewer surrogate finishes, stronger source-use
     and exact verifier evidence, increased reward or more actionable failure.

Fallback candidates:

2. `video-processing`
   - Reason: hidden generalization and artifact reasoning; useful if the repair
     targets validation generalization.
3. `compile-compcert`
   - Reason: long-build strategy after `/tmp` permission repair; useful if the
     repair targets source/build planning and partial progress.

## Next Action

Before writing implementation code, produce a small reference-backed design for
the selected class:

1. Inspect the mew failure evidence above.
2. Inspect Codex source patterns under `references/fresh-cli/codex` that govern
   task decomposition, patch lifecycle, context windows, verification, and
   review/apply loops.
3. Cross-check `docs/ADOPT_FROM_REFERENCES.md` and
   `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`.
4. Translate only the smallest generic concept into mew's existing work-session
   loop.
5. Implement and rerun the selected same-shape task.

If this design cannot name a concrete generic mechanism, reclassify the gap as
`ambiguous` and add more instrumentation rather than patching prompts.
