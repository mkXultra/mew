# M6.24 System Service State Contract

Date: 2026-04-30 JST

## Context

After the `gpt2-codegolf` repair reached the frozen Codex target, M6.24 stayed
in `improvement_phase` because the aggregate/current measured gaps remain above
the controller threshold.

Next selected evidence:

- `docs/M6_24_BATCH_6_RUNS_2026-04-29.md`
- `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__10-59-27/result.json`
- failed `git-multibranch` transcripts under
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__10-59-27/`

`git-multibranch` scored `1/4` completed trials with one setup error against a
frozen Codex target of `5/5`. Two completed failures stopped immediately after
inventory because the model treated writes to `/git`, `/srv`, `/etc`, `/run`,
and account/service state as forbidden by `allowed_write_roots`, even though
the task was explicitly a system service setup task and `allow_shell` was
enabled in an ephemeral benchmark workspace. Another trial tried an
allowed-root alternative but remained sensitive to exact external interface
behavior.

## Gap

Gap class:

`system_service_state_permission_contract`

This is not a request to make mew globally unsafe. The issue is narrower:

- native `write_file` / `edit_file` tools are correctly constrained by
  `allowed_write_roots`;
- shell commands are already separately gated by `allow_shell`;
- for tasks whose acceptance criteria explicitly require localhost daemons,
  system users, ports, package/service config, or exact paths such as `/git`,
  `/srv`, `/var`, `/run`, and `/etc`, the model must not wait solely because
  native write roots exclude those paths;
- if the environment is an isolated/containerized work context and shell is
  allowed, the implementation lane should use a bounded `run_command` that
  sets up the exact external interface and verifies it.

## Architecture Fit

Decision: `implementation_profile`, no new lane.

Rationale:

- output authority is still the implementation lane;
- no helper agent or deliberation lane is needed;
- the repair is a policy/profile clarification for `run_command` under
  `allow_shell`, not a new executor or permission model;
- calibration unit remains the same failed task shape.

## v0 Repair

Change `build_work_think_prompt()` to make the capability boundary explicit:

- `allowed_write_roots` constrain native write/edit tools, not shell-side
  service setup by itself;
- when `allow_shell` is true and the task explicitly requires system service
  state, prefer a bounded shell setup plus verifier-shaped check over a wait
  for more write roots;
- avoid touching host secrets or sensitive paths;
- do not substitute `/tmp`-only implementations when the verifier requires an
  exact external path/interface such as `git@localhost:/git/project`.

This is generic arbitrary-workspace work-loop behavior, not a Terminal-Bench
solver.

## Same-Shape Rerun

After v0, run a 1-trial same-shape speed rerun for `git-multibranch`.

Success signal:

- the run does not stop after inventory with a write-root wait;
- mew attempts exact externally visible service state or an exact-interface
  equivalent;
- reward improves or the next failure moves to a concrete verifier/service
  issue.

Do not escalate to a five-trial proof unless the speed rerun passes, materially
improves, or gives variance-sensitive evidence.
