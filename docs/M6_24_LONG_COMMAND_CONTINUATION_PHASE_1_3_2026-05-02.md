# M6.24 Long-Command Continuation Phase 1-3 Slice

Date: 2026-05-02

Status: implemented and reviewed.

## Scope

This slice implements the first generic substrate pieces from
`docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`.

Implemented:

- `LongCommandRun` schema helpers, output owner refs, bounded output snapshots,
  idempotence keys, env summaries, and yield/timeout invariant helpers.
- Strict command-evidence terminal acceptance guard:
  nonterminal or non-success statuses cannot prove artifacts even if a malformed
  stored record says `terminal_success=true`.
- Internal single-active `ManagedCommandRunner` with start, poll, finalize,
  timeout/process-group kill, and explicit cancel cleanup.
- `LongBuildState` reducer support for `long_command_runs`:
  running/yielded latest runs reduce to `in_progress` with
  `poll_long_command`; timed-out/killed latest runs reduce to `build_timeout`
  with `resume_idempotent_long_command`.

Not implemented yet:

- production-visible work-loop dispatch of managed long commands;
- compact recovery rendering for continuation actions;
- Harbor timeout-shape reporting;
- transfer fixtures and same-shape `compile-compcert` speed rerun.

## Review

codex-ultra reviewed this slice in session
`019de84b-b6f5-7f83-bc9e-bace82c79d20`.

Initial review requested changes for:

- raw `terminal_success` usage in reducer proof helpers;
- stale live `LongCommandRun` overriding a newer terminal timeout;
- missing managed-runner cleanup.

Those were fixed and the final review returned `STATUS: APPROVE`.

## Verification

Commands run:

```text
uv run pytest --no-testmon tests/test_long_build_substrate.py tests/test_toolbox.py -q
uv run pytest --no-testmon tests/test_work_session.py tests/test_acceptance.py tests/test_long_build_substrate.py tests/test_toolbox.py -q
uv run ruff check src/mew/long_build_substrate.py src/mew/toolbox.py src/mew/work_session.py tests/test_long_build_substrate.py tests/test_toolbox.py
uv run pytest --no-testmon -q
uv run ruff check .
git diff --check
```

Results:

- `267 passed`
- broader acceptance/work-session suite: `1267 passed`, `67 subtests passed`,
  one multiprocessing fork deprecation warning
- full suite: `2447 passed`, `93 subtests passed`, one multiprocessing fork
  deprecation warning
- ruff passed
- diff check passed

## Next Action

Continue with the remaining implementation phases from the continuation design:

1. Connect the managed runner to work-loop dispatch behind the documented
   feature gate.
2. Render continuation/budget state in compact recovery and work-loop outputs.
3. Add Harbor timeout-shape reporting.
4. Run non-CompCert transfer fixtures before spending another
   `compile-compcert` speed rerun.
