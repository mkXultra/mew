# M6.24 Compound Long-Command Budget Repair - 2026-05-03

## Context

The same-shape `compile-compcert` speed_1 after
`docs/M6_24_NONTERMINAL_LONG_COMMAND_HANDOFF_REPAIR_2026-05-03.md` no longer
returned `wait` as a successful verifier handoff. It ran for `30m37s` and
failed nonzero.

Run:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-nonterminal-handoff-compile-compcert-1attempt-20260503-0120`

Observed:

- Harbor score: `0/1`
- `work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`
- `work_report.steps`: `8`
- `latest_long_command_run_id`: `null`
- step 8 was a compound OPAM / configure / build / final-smoke command
- step 8 requested `timeout=2400` but was capped to `899.53`
- step 8 had no `long_command_budget`
- final artifact `/tmp/CompCert/ccomp` remained missing

codex-ultra classification:

- session `019de99a-761c-7ee3-94f0-d18c0953eecd`
- `primary_gap_class`: `compound_long_command_budget_not_attached`

## Classification

`compound_long_command_budget_not_attached`

The previous repair worked for its target failure: oneshot no longer handed off
successfully on `wait` while a managed command was running. The new failure is
that a compound long-build continuation was treated as a normal shell command
and killed by the generic wall-clock ceiling instead of being launched through
the managed long-command runner.

This is generic implementation-lane behavior, not a CompCert recipe.

## Repair

Implemented in:

- `src/mew/long_build_substrate.py`
- `src/mew/commands.py`

Changes:

- add `planned_long_build_command_budget_stage`
- keep the recorded attempt stage logic intact
- add a budget-specific promotion layer for planned commands
- if a command is initially classified as `configure`, `source_acquisition`, or
  `command` but contains build/dependency/final-proof work for the required
  artifact, classify it as a managed-budget-eligible stage
- guard against pure source-fetch false positives where `curl -L` looks like a
  runtime `-L` flag; source acquisition without build work in non-fetch shell
  segments remains non-managed-budget work, even if the URL contains build
  words such as `make`
- treat a non-fetch shell segment as build work only when it actually invokes a
  build/install command such as `make`, `ninja`, `cargo build`, `go build`,
  `npm run build`, `python -m build`, `opam install`, or `pip install`; path
  readbacks such as `test -s /tmp/make.tar.gz`, `sha256sum /tmp/make.tar.gz`,
  and `printf 'archive=/tmp/make.tar.gz\n'` do not qualify
- use that budget stage in `work_tool_long_command_budget_policy`

Focused regressions:

- `tests/test_long_build_substrate.py::test_planned_long_build_command_budget_stage_promotes_compound_configure_build_smoke`
- `tests/test_long_build_substrate.py::test_planned_long_build_command_budget_stage_does_not_promote_pure_curl_source_fetch`
- `tests/test_long_build_substrate.py::test_planned_long_build_command_budget_stage_does_not_promote_source_fetch_readback`
- `tests/test_work_session.py::WorkSessionTests::test_long_command_budget_policy_attaches_to_compound_configure_build_smoke`
- `tests/test_work_session.py::WorkSessionTests::test_long_command_budget_policy_does_not_attach_to_pure_source_fetch`
- `tests/test_work_session.py::WorkSessionTests::test_long_command_budget_policy_does_not_attach_to_source_fetch_readback`

Validation so far:

`uv run pytest tests/test_long_build_substrate.py tests/test_work_session.py -q -k "pure_curl_source_fetch or source_fetch_readback or pure_source_fetch or compound_configure_build_smoke"`

Result:

- `8 passed, 3 subtests passed`

`uv run pytest tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py tests/test_toolbox.py tests/test_long_build_substrate.py -q -k "long_command or work_oneshot or harbor or timeout_shape or runtime_link or acceptance or source_authority or budget_stage"`

Result:

- superseded by the stricter rerun below

`uv run pytest tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py tests/test_toolbox.py tests/test_long_build_substrate.py -q -k "long_command or work_oneshot or harbor or timeout_shape or runtime_link or acceptance or source_authority or budget_stage or pure_source_fetch or pure_curl or source_fetch_readback"`

Result:

- `248 passed, 3 subtests passed`

`uv run ruff check src/mew/commands.py src/mew/long_build_substrate.py tests/test_work_session.py tests/test_long_build_substrate.py`

Result:

- passed

## Next Action

codex-ultra re-review session `019de9ac-023e-7011-b73e-d0c47bdcc5fc`
returned `STATUS: APPROVE`.

Run exactly one same-shape `compile-compcert` speed_1.

Do not run proof_5 or broad measurement before that same-shape rerun.
