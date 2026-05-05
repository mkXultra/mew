# M6.24 Software/Coding Rebaseline

Date: 2026-05-03

Scope: the 25 Terminal-Bench 2.0 tasks listed in
`docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`.

Frozen target: Codex `0.121.0` / `gpt-5.5@openai` from
`docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`.

## Status

| Status | Count | Tasks |
|---|---:|---|
| Target met | 8 | `circuit-fibsqrt`, `cobol-modernization`, `distribution-search`, `feal-differential-cryptanalysis`, `feal-linear-cryptanalysis`, `fix-git`, `kv-store-grpc`, `make-mips-interpreter` |
| Measured below target | 4 | `build-cython-ext`, `make-doom-for-mips`, `polyglot-rust-c`, `raman-fitting` |
| Unmeasured in scoped cohort | 13 | `hf-model-inference`, `largest-eigenval`, `merge-diff-arc-agi-task`, `openssl-selfsigned-cert`, `polyglot-c-py`, `prove-plus-comm`, `pypi-server`, `pytorch-model-cli`, `pytorch-model-recovery`, `regex-chess`, `reshard-c4-data`, `schemelike-metacircular-eval`, `write-compressor` |

Measured aggregate on the 12 measured scoped tasks:

- Mew best observed: `34/60`
- Frozen Codex target: `44/60`
- Gap: `-16.7 percentage points`

This aggregate is within the controller's `10 < gap <= 20 percentage points`
band, but M6.24 is already in improvement phase and `build-cython-ext` remains
a large repeated in-scope gap with many repair cycles. The controller should
classify and repair one selected gap before broad scoped measurement resumes.

## Current-Head Recheck

After the execution-contract and prompt-section architecture changed, the next
step was remeasurement rather than repairing from the older dossier alone.

Current-head live recheck:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-rebaseline-build-cython-ext-1attempt-20260503-1936/result.json`
- Trial: `build-cython-ext__MQPEBk8`
- Result: `0/1`
- Runtime: `29m30s`
- Harbor runner errors: `0`
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`

The old selected gap is not stale enough to discard: current-head mew still
misses `build-cython-ext`. The failure shape did move materially. The run fixed
or passed the earlier source/build/import smoke path, including extension
imports and the README example, and external verifier output shows `10/11`
Harbor tests passed. The remaining failure is the original repository test tail:
`test_pyknotid_repository_tests` fails because the cloned upstream tests still
have one failing `tests/test_spacecurve.py::test_reconstructed_space_curve`.

This refines the active gap from a broad historical sibling-frontier hypothesis
to a current-head shape:

```text
verified_sibling_repair_frontier_not_exhausted
  -> repository-test-tail repair frontier not exhausted before wall timeout
```

Do not use the older `build-cython-ext` artifacts as the sole repair basis. The
latest saved artifact above is now the first replay/dogfood/emulator input.

## Per-Task Rebaseline

| Task | Codex target | Mew best/current | State | Evidence |
|---|---:|---:|---|---|
| `build-cython-ext` | 5/5 | best 1/5, latest 0/1 current-head recheck | below target | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-rebaseline-build-cython-ext-1attempt-20260503-1936/result.json` |
| `circuit-fibsqrt` | 5/5 | 5/5 | target met | scoped historical artifact set |
| `cobol-modernization` | 5/5 | 5/5 | target met | scoped historical artifact set |
| `distribution-search` | 5/5 | 5/5 | target met | scoped historical artifact set |
| `feal-differential-cryptanalysis` | 5/5 | 5/5 | target met | scoped historical artifact set |
| `feal-linear-cryptanalysis` | 5/5 | 5/5 | target met | scoped historical artifact set |
| `fix-git` | 5/5 | 5/5 | target met | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` |
| `hf-model-inference` | 5/5 | unmeasured | pending measurement | none |
| `kv-store-grpc` | 4/5 | 5/5 | target met | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` |
| `largest-eigenval` | 5/5 | unmeasured | pending measurement | none |
| `make-doom-for-mips` | 1/5 | 0/5 | below target | M6.24 hard-runtime artifacts |
| `make-mips-interpreter` | 3/5 | 3/5 | target met | M6.24 hard-runtime artifacts |
| `merge-diff-arc-agi-task` | 5/5 | unmeasured | pending measurement | none |
| `openssl-selfsigned-cert` | 5/5 | unmeasured | pending measurement | none |
| `polyglot-c-py` | 5/5 | unmeasured | pending measurement | none |
| `polyglot-rust-c` | 4/5 | 0/5 | below target | M6.24 batch artifacts |
| `prove-plus-comm` | 5/5 | unmeasured | pending measurement | none |
| `pypi-server` | 5/5 | unmeasured | pending measurement | none |
| `pytorch-model-cli` | 5/5 | unmeasured | pending measurement | none |
| `pytorch-model-recovery` | 5/5 | unmeasured | pending measurement | none |
| `raman-fitting` | 2/5 | 0/5 | below target | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` |
| `regex-chess` | 5/5 | unmeasured | pending measurement | none |
| `reshard-c4-data` | 5/5 | unmeasured | pending measurement | none |
| `schemelike-metacircular-eval` | 5/5 | unmeasured | pending measurement | none |
| `write-compressor` | 5/5 | unmeasured | pending measurement | none |

## Selected Next Gap

Selected next task shape: `build-cython-ext`.

Reason:

- It is the largest repeated in-scope deficit: best `1/5` vs Codex `5/5`.
- It exercises normal developer work: native extension build, packaging,
  source compatibility repair, reinstall, and verifier-driven iteration.
- The best passing trial proves the task is solvable without a task-specific
  solver.
- Failed trials preserve enough same-family verifier evidence to build replay,
  dogfood, and emulator checks before live Harbor budget.

Selected generic gap class:
`verified_sibling_repair_frontier_not_exhausted`.

Current-head subtype:
`repository_test_tail_frontier_not_exhausted_before_wall_timeout`.

One-line controller chain:

```text
M6.24 -> verified_sibling_repair_frontier_not_exhausted -> current-head build-cython-ext artifact -> replay/dogfood/emulator classification -> generic repository-test-tail frontier repair -> focused UT/replay/dogfood/emulator -> exactly one build-cython-ext speed_1
```

Do not add `pyknotid`, NumPy, Cython, or Terminal-Bench specific solvers. Any
repair must generalize to verifier-driven source compatibility loops where the
same failure family appears in several source locations.
