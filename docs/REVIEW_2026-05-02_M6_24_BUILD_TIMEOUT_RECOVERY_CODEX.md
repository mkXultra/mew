# Review 2026-05-02: M6.24 Build-Timeout Recovery Decision Repair

Reviewer: codex-ultra

Session: `019de7d9-b0b1-7a03-9fa4-657915260995`

## Round 1

Status: `REQUEST_CHANGES`

Findings:

- `src/mew/long_build_substrate.py` let `build_timeout` bypass all active
  blockers in `current_failure`, not only the same-evidence unreached install
  blocker. This could demote real source-provenance or budget blockers and
  route recovery incorrectly.
- `_blocker_masked_by_latest_build_timeout` masked any same-tool-call
  `untargeted_full_project_build_for_specific_artifact` blocker. It needed to
  distinguish unreached later `make install` from real overbroad builds such as
  `make all`.

Required tests:

- same-call timeout from overbroad `make all` keeps the overbroad blocker active
- build timeout plus unrelated source-authority blocker keeps the unrelated
  blocker as `current_failure`

## Round 2

Status: `REQUEST_CHANGES`

Findings:

- The code and tests were acceptable, but the durable repair docs still used
  broad wording saying latest `build_timeout` wins over older or same-command
  blockers.

Required docs:

- Narrow the repair record to same-evidence unreached `make install` blockers.
- State that unrelated blockers and real overbroad builds remain active.

## Final

Status: `APPROVE`

Findings: none.

Missing tests: none blocking.

Residual risk:

- The repair uses an intentional `install`-excerpt heuristic instead of true
  shell segment reachability. The current code, docs, and tests are consistent:
  unrelated blockers and real overbroad builds remain active, while the
  same-evidence unreached `make install` case is suppressed.
