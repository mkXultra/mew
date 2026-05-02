# M6.24 Long-Command Continuation Phase 4-5 Slice

Date: 2026-05-02

Status: implemented and reviewed.

## Scope

This slice continues
`docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md` after the approved
Phase 1-3 substrate.

Implemented:

- Phase 4 work-loop budget rendering:
  - long-command budget policy now records start/poll/resume intent;
  - wall-budget blocks for long commands use typed stop reason
    `long_command_budget_blocked`;
  - `yield_after_seconds < effective_timeout_seconds` is recorded after timeout
    capping;
  - compact recovery renders `continuation_action` and latest long-command
    identity instead of stale `suggested_next` prose;
  - work-session resume text surfaces latest long-command status/output ref and
    continuation counts.
- Phase 5 Harbor timeout-shape reporting:
  - `command-transcript.json`, `summary.json`, and `mew-report.json` now
    include `timeout_shape`;
  - timeout shape records Harbor outer timeout, mew inner wall timeout, reserve,
    matched outer/inner flag, diagnostic flag, and latest long-command id/status
    when present in the mew report;
  - missing-report outer timeout paths synthesize non-success report metadata so
    the timeout shape is still preserved.

Not implemented yet:

- production-visible managed long-command dispatch;
- transfer fixture closeout doc and same-shape `compile-compcert` speed rerun.

## Verification

Commands run:

```text
uv run pytest --no-testmon tests/test_work_session.py -q -k 'compact_recovery_context_surfaces_long_command_continuation_action or wall_timeout_ceiling_records_long_command_start_budget or wall_timeout_ceiling_uses_typed_stop_reason or long_build_recovery_command_can_spend_reserved_budget_after_linker_failure or unrelated_long_command_preserves_reserve_after_linker_failure or budget_reserve_violation_preserves_reserve_for_non_build_long_command or compact_recovery_context_hard_caps_long_build_payloads'
uv run pytest --no-testmon tests/test_harbor_terminal_bench_agent.py -q
uv run pytest --no-testmon tests/test_long_build_substrate.py -q -k 'WidgetCLI or BarVM or non_compcert or default_runtime or masked_or_spoofed or invalid_target or runtime_repair'
uv run pytest --no-testmon tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py -q -k 'long_command or wall_timeout_ceiling or compact_recovery_context or harbor or timeout_shape or recovery_budget'
uv run ruff check src/mew/commands.py src/mew/work_loop.py src/mew/work_session.py tests/test_work_session.py
uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py
python3 -c 'import json,pathlib; p=pathlib.Path("proof-artifacts/m6_24_gap_ledger.jsonl"); lines=[l for l in p.read_text().splitlines() if l.strip()]; [json.loads(l) for l in lines]; print(len(lines))'
git diff --check
```

Results:

- focused Phase 4 work-session tests: `7 passed`
- Harbor wrapper tests: `17 passed`
- non-CompCert transfer fixture subset: `29 passed`
- combined Phase 4/5 subset after review fixes: `28 passed`
- scoped ruff passed
- gap-ledger JSONL parse passed: `151` records
- diff check passed
- codex-ultra review session `019de86a-2a44-7c10-84e8-d384c1c3f61f`
  returned `STATUS: APPROVE` after two request-change rounds.

## Next Action

Run the broader work-session, long-build, acceptance, Harbor, and ruff suites,
then proceed to Phase 6 transfer closeout before spending another
`compile-compcert` same-shape speed rerun.
