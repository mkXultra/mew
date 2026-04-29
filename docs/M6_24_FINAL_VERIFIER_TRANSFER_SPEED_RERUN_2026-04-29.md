# M6.24 Final-Verifier Transfer Speed-Rerun - 2026-04-29

Controller chain:

`M6.24 -> hard_task profile v0 -> final verifier state transfer v0 -> speed-rerun make-doom-for-mips`

## Run

Task:

`terminal-bench/make-doom-for-mips`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-final-verifier-transfer-make-doom-1attempt-20260429-1518/result.json`

Run shape:

- model: `gpt-5.5`
- trials: `-k 1 -n 1`
- runtime: 30m 17s
- same task, permissions, timeout shape, and work-session path as the prior
  same-shape reruns
- smaller trial count by M6.24 rerun budget rule

Result:

- `n_trials`: 1
- `n_errors`: 0
- `mean`: 0.000
- reward `0.0`: `make-doom-for-mips__o8gh2TN`

## Delta

The score stayed 0/1, but the selected repair moved the failure mode.

Positive movement:

- `final_verifier_state_transfer` appeared in resume:
  `/tmp/frame.bmp` was missing after a successful `node vm.js` command
- the agent did not finish after command exit 0 without artifact proof
- the model explicitly named the acceptance gap:
  "stdout was verified, but /tmp/frame.bmp creation must be proven fresh from
  the final runtime command"
- after that, it reran a fresh artifact check, proved `/tmp/frame.bmp` was
  still missing, mapped the runtime failure, and made one source repair
- the task progressed to a new concrete runtime blocker:
  `W_GetNumForName: STCFN33 not found`
- working memory preserved a useful hypothesis:
  Doom likely expects `STCFN033`, but the shim formatter emitted `STCFN33`

Remaining miss:

- reward stayed 0
- the external verifier still failed 3/3 tests because `/tmp/frame.bmp` was
  absent
- the session hit `wall_timeout` after the model had a concrete next repair
  candidate

## Classification

Status: `directionally_improved_score_unchanged`.

The final-verifier state-transfer guard is doing the intended generic work:
it prevents command-success-without-artifact finish and keeps the next runtime
blocker visible. This is enough for the diagnostic speed-rerun tier.

Do not escalate to `-k 5 -n 5` from this result. A five-trial proof would spend
more tokens on a still-failing shape. Escalation should wait until a speed-rerun
shows reward/proximity improvement or the controller is ready for close/resume
proof.

## Next Action

Keep M6.24 in improvement phase.

Recommended next step:

- do not run another `make-doom-for-mips` proof immediately
- decide the next highest-leverage gap from the ledger
- if continuing hard-task work, avoid another broad prompt-only repair; pick
  either:
  - a different hard-task speed sample to check whether the profile generalizes
  - or a concrete generic budget/reentry repair only if multiple samples show
    "concrete next source repair identified but model/wall timeout before edit"

This result should not be counted as a reward improvement, but it should count
as a successful diagnostic repair of the selected false-finish shape.
