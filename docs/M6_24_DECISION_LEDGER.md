# M6.24 Decision Ledger

Purpose: keep the measure-vs-improve decisions for M6.24 in one compact,
append-friendly file so long sessions and context compression do not drift back
to stale next-batch execution.

Companion controller and data files:

- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`
- `docs/M6_24_GAP_BASELINE_2026-04-29.md`

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
6. Record classification and repair state in
   `proof-artifacts/m6_24_gap_ledger.jsonl`.

Allowed next actions during improvement phase:

- classify a measured failure into the gap ledger
- add missing instrumentation for a selected gap and speed-rerun the same shape
- make a bounded local/polish repair for a selected gap
- open/complete a reference-backed structural repair for a selected gap
- rerun the same failed shape after repair
- update this decision ledger to resume broad measurement with evidence

Anything else is drift unless the user's newest explicit instruction changes
direction.

## Decisions

| Date | Decision | Evidence | Next action | Status |
|---|---|---|---|---|
| 2026-04-29 | Enter M6.24 improvement phase; stop new broad measurement for now. | `docs/M6_24_GAP_BASELINE_2026-04-29.md`: measured subset is mew 92/210 = 43.8% vs Codex 156/210 = 74.3%, gap -30.5 pp; Batch 2, 3, 4, 5, and partial Batch 6 all exceed the `> 20 pp` improvement threshold. | Classify Batch 1-6 measured failures, pick one generic gap class, repair it, and rerun the same failed shape before continuing `gpt2-codegolf` or any new broad-measurement task. | active |
| 2026-04-29 | Select first gap class: `hard_task_implementation_strategy_contract_retention`. | `docs/M6_24_GAP_CLASS_PLAN_2026-04-29.md` and `proof-artifacts/m6_24_gap_ledger.jsonl`: many major losses remain after lower-level timeout, permission, artifact, and verifier-grounding repairs; repeated failures look like weak task decomposition, contract retention, source grounding, and verifier-driven repair on hard implementation tasks. | Produce a reference-backed design by inspecting mew evidence plus `references/fresh-cli/codex`, `docs/ADOPT_FROM_REFERENCES.md`, and `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`; implement the smallest generic work-session repair; rerun `make-doom-for-mips` or `make-mips-interpreter` same shape. | active |
| 2026-04-29 | Implement v0 hard-task contract capsule. | `docs/REVIEW_2026-04-29_M6_24_CODEX_IMPLEMENTATION_LANE_PATTERNS.md` and `docs/DESIGN_2026-04-29_M6_24_HARD_TASK_CONTRACT_CAPSULE.md`: Codex-style persistent objective/source grounding was translated into `working_memory.implementation_contract` plus a pre-finish source proof blocker. Focused validation passed for acceptance and work-session surfaces. | Rerun one same-shape hard task, preferably `make-doom-for-mips` or `make-mips-interpreter`, and record whether source grounding, surrogate/stub finishes, and reward improve. | rerun_recorded |
| 2026-04-29 | Same-shape rerun improved behavior but not reward. | `docs/M6_24_HARD_TASK_CONTRACT_RERUN_2026-04-29.md` and codex-ultra review `docs/REVIEW_2026-04-29_M6_24_HARD_CONTRACT_RERUN_NEXT.md`: `make-doom-for-mips` remained 0/5, but the failure shape changed from surrogate/stub completions to real source-build and VM-loader/runtime repair attempts; no false complete state was observed. Two trials still stopped on system package/read-write permission boundaries, and three reached real ELF/VM work before missing `/tmp/frame.bmp`. | Continue improvement phase. Do not run new broad measurement. Next bounded repair is generic hard-runtime verifier strategy: classify VM/emulator/interpreter failure signatures, preserve PC/opcode/artifact evidence, steer runtime-source plus readelf/nm/objdump/addr2line mapping, then rerun `make-doom-for-mips` same shape again. | active |
| 2026-04-29 | Implement v0 hard-runtime verifier strategy. | `docs/DESIGN_2026-04-29_M6_24_HARD_RUNTIME_VERIFIER_STRATEGY.md`: failed VM/emulator/interpreter verifier output now becomes `verifier_failure_repair_agenda.runtime_contract_gap` with kind, PC/opcode/artifact signature, recommended mapping tools, and resume-visible next action. Reasoning policy also promotes MIPS/ELF/toolchain/provided-source/VM-style implementation tasks to high effort. Focused work-session and reasoning-policy validation passed. | Rerun `make-doom-for-mips` same shape and record whether the runtime gap appears in reentry, permission waits are reduced/absent, and at least one trial passes the current VM startup/opcode blocker or writes `/tmp/frame.bmp`. | rerun_pending |

## Current Mode

`improvement_phase`

Do not run the next broad-measurement task merely because
`docs/M6_24_BATCH_6_MANIFEST_2026-04-29.md` lists `gpt2-codegolf` as pending.
That was the previous measurement-only next action. The current M6.24 controller
decision supersedes it.

Current selected next action:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> hard-runtime verifier strategy repair implemented -> rerun make-doom-for-mips same shape`
