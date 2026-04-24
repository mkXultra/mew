# M6.11 Close-Gate Gap Rationale (2026-04-24)

Status: not close-ready.

- reviewer: `codex-ultra`
- session: `019dbe35-f1d5-7821-a70b-7d80d61ccfb3`
- reviewer decision: `STATUS NEEDS_WORK`
- CLOSE_READY: `no`

## Audit commands and results

- `./mew dogfood --all --json`  
  result: all five `m6_11-*` scenarios pass
- `uv run pytest -q tests/test_dogfood.py -k 'm6_11' --no-testmon`  
  result: `6 passed`, `75 deselected`
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`  
  result: `ok=true`
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --strict --json`  
  result: `ok=true`

## Evidence accepted this audit

- patch-draft path proof: task `#521` (`m6_11` patch-draft completion)  
  (task reached paired patch and was reviewer approved)
- verifier-backed no-change proofs: tasks `#522`, `#523`
- prior counted incidence evidence on the 20-slice trajectory is preserved in
  history and remains part of the running concentration calculation

## Remaining gap / risk

- no literal 20-slice batch run was executed in this audit; this is a smaller
  reduction run instead
- current HEAD now has `cohort[current_head]: total=0` in proof-summary view after
  closeout commits, so fresh measurement remains inherited by cohort carry-over
- strict and non-strict calibrations pass, but `cohort[unknown]` concentration
  behavior is still a risk signal to track
- #522 and #523 are valid `current_head_positive_verifier_backed_no_change` outcomes
  but do not provide patch-draft replay evidence for that gate lane

## Next action

Keep M6.11 open and continue with a reviewer-approved smaller-reduction path.
For future close-gate clearance attempts, re-run a documented 20-slice batch or
obtain an explicit reviewer waiver for the same reduction shape.
