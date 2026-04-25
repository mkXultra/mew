# M6.10 Close Gate Audit 2026-04-25

Status: close-ready.

## Scope

M6.10 asked whether mew-first implementation is reliable enough for ordinary
bounded coding tasks before returning to M6.9 durable-coding proof work.

## Done-When Check

| Criterion | Result | Evidence |
|---|---|---|
| Calibration D0 report summarizes latest attempts by success, drift, rescue, rejection, and verifier status | met | `mew metrics --mew-first` reports result classes, drift classes, rejected patch families, verifier status, gate successes, gate blockers, and blocker class counts. |
| Todo D1 lands with tests and one real bounded coding iteration | met | Task `#603` / session `#588`; `tests/test_work_todos.py`. |
| Todo D2 surfaces current Todo state in reviewer/operator views and prevents stale/duplicate churn | met | Task `#605` / session `#590`; `tests/test_brief.py`. |
| Structured rejection/frontier D1 lands and blocks at least one real/replayed drift before implementation | met | Task `#604` / session `#589`; `tests/test_work_rejection_frontier.py`. |
| Latest 10 bounded mew-first attempts after D0/D1 include at least 7 clean/practical successes, counted successes with `rescue_edits=0`, and every failure classified | met | `mew metrics --mew-first` shows `7/10 clean_or_practical threshold=7 passed=True`, successes `#606 #607 #608 #609 #610 #611 #612`, blockers `#600 #601 #602`, and all failures classified. |
| Explorer D1 lands only if D0/D1 evidence shows read-only exploration churn remains a measured blocker | deferred, not blocking | The gate passed without Explorer. Read-only churn still exists as friction, but it did not block M6.10 close after Todo, structured rejection, and calibration economics landed. |
| Scope fence holds across the proof run | met | Counted implementation patches stayed in bounded source/test scope; roadmap/status and close-audit updates remained reviewer-owned. No cross-session Todo persistence, write-capable Explorer, multi-Explorer fan-out, or accelerator-owned milestone edits were introduced. |

## Validation

Commands run at close:

```bash
./mew metrics --mew-first
./mew metrics --mew-first --json
uv run pytest -q tests/test_mew_first_calibration.py tests/test_metrics.py tests/test_work_todos.py tests/test_brief.py --no-testmon
uv run pytest -q tests/test_work_rejection_frontier.py --no-testmon
uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py
git diff --check
```

Observed close metrics:

```text
gate: 7/10 clean_or_practical threshold=7 success_gap=0 passed=True
gate_successes: #606 #607 #608 #609 #610 #611 #612
gate_blockers: #600 #601 #602
gate_blocker_classes: supervisor_owned=1 supervisor_owned_or_unknown=1 supervisor_rescue=1
```

## Decision

Close M6.10 and resume M6.9 at the already-recorded proof boundary.

M6.10 does not prove mew is ready for unattended self-hosting. It does prove
that, under reviewer-gated mew-first operation, recent bounded implementation
work can clear the reliability bar without hiding supervisor rescue edits.

