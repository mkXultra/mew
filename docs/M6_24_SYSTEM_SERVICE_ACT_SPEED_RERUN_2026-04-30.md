# M6.24 System Service ACT Speed Rerun - 2026-04-30

Task: `git-multibranch`

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-system-service-act-git-multibranch-1attempt-20260430-0255/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `1/1`
- runtime: `6m 8s`

## Observed Behavior

The v0.1 ACT capability-boundary repair worked on the same failed shape.

mew preserved the shell-authorized system-service `run_command` instead of
converting it to `wait` because `/git`, `/etc`, `/var`, and `/run` were outside
native write roots. The run configured:

- `git@localhost:/git/project` with password SSH;
- a bare Git repository and post-receive deployment hook;
- Nginx HTTPS on `localhost:8443` with a self-signed certificate;
- main and dev branch deployment paths.

The work session then ran a final self-check against the same external
interfaces and finished. The external verifier passed.

## Decision

The selected repair is materially validated by a one-trial same-shape speed
proof.

Next action:

Run a five-trial same-shape proof for `git-multibranch`. If it reaches the
frozen Codex target `5/5` without a new repeated structural blocker, close the
selected `system_service_state_permission_contract` repair and recheck the
M6.24 aggregate/current-batch gap before resuming broad measurement.
