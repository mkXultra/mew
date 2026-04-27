# M6.16 Close Gate Audit 2026-04-27

Verdict: `CLOSE_WITH_RESIDUALS`

M6.16 should close. The implementation lane is not "finished" in the absolute
sense, but the milestone's gate has been met: recent mew-first work is
materially more reliable than the baseline, rescues are classified instead of
hidden, verifier failures are controlled, and the first-edit latency issue has
both measurement and a first reducer in place.

## Evidence

- Baseline at M6.16 start: `attempts_total=12`,
  `clean_or_practical_successes=3`, `rescue_partial_count=9`,
  approval rejection `13/18`, verifier failure `0/75`, and first-edit latency
  p95 around `890s`.
- Current `./mew metrics --mew-first --limit 10`: latest window
  `#678 #677 #676 #675 #674 #673 #672 #671 #670 #669`, gate passes at `8/10`.
- Current `./mew metrics --implementation-lane --limit 20`:
  `clean_or_practical_successes=12/20`, `rescue_partial_rate=0.4`,
  `approval.rejection_rate=0.143`, `verifier.failure_rate=0.0`,
  first-edit latency `median=285.5s`, `p95=536.55s`, `max=704.0s`.
- Current `./mew metrics --implementation-lane --limit 10`:
  `clean_or_practical_successes=8/10`, `rescue_partial_rate=0.2`,
  approval rejection `0.0`, verifier failure `0.0`,
  first-edit latency `median=187.0s`, `p95=599.15s`, `max=704.0s`.
- Task `#678` is clean mew-first evidence on current head. Session `#667`
  reached its first write in about `176s`, passed focused and full
  work-session verification, and codex-ultra review
  `019dcb9d-ddf7-7f30-8605-7b603f048ba8` reported `NO FINDINGS`.

## Done-When Check

- Recent bounded mew-first cohort improved reliability: `met`.
- Supervisor-authored rescue is rare and classified: `met_with_note`.
  The latest-10 window still contains two older supervisor-owned tasks, but
  `#671` through `#678` are clean or practical mew-first.
- Approval rejections are reduced or produce successful retries: `met`.
- Verifier failures have explicit retry or repair paths: `met`.
- First-edit latency feels usable enough to proceed: `met_with_residual`.
  Historical slow samples remain, but #678 gives current-head evidence below
  three minutes and the prompt now has a budget rule against rediscovery loops.
- Refactors are tied to measured bottlenecks: `met`.
- Structural failures enter M6.14 instead of hidden rescue: `met`.

## Residuals

- First-edit p95 is still inflated by older slow sessions `#665`, `#652`, and
  `#649`. Do not reopen M6.16 for these alone; use them as M6.17 lane-choice
  and repair-priority inputs.
- Side-project dogfood ledger rows are still `0`. User controls side-project
  launch, so this is not an M6.16 blocker.
- Future ordinary coding failures should route to M6.14 when structural, or to
  M6.17 meta-loop evidence when the issue is task/lane dispatch.

## Next

Start M6.17 Resident Meta Loop / Lane Chooser. Its first slice should be
read-only or reviewer-gated and should use M6.16 metrics as dispatch evidence,
not bypass the implementation lane's remaining guardrails.
