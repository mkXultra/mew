# M6.24 Validated Archive Source Signal Review - 2026-05-02

Reviewer: `codex-ultra`
Session: `019de5fe-2059-7bd2-8853-4184e3e1f472`
Status: `APPROVE`

## Scope

Reviewed the validated archive-loop source signal repair in:

- `src/mew/long_build_substrate.py`
- `tests/test_long_build_substrate.py`
- `docs/M6_24_VALIDATED_ARCHIVE_SOURCE_SIGNAL_REPAIR_2026-05-02.md`

## Review Loop

The reviewer initially requested hardening for shell false positives and one
valid-loop false negative:

- standard same-line `for url in ...; do` archive loops were not accepted
- direct fetches inside unexecuted `if false` branches were counted
- direct/candidate fetches inside unexecuted `while` / `until` bodies were
  counted
- split-line `if ...` / `then` and `while ...` / `do` block openers were not
  tracked
- control openers after another command on the same physical line, such as
  `:; if false; then`, were not tracked

All requested blockers were fixed with generic source-authority guardrails and
tests. The final reviewer response was:

```text
STATUS: APPROVE
```

Residual non-blocking risk: shell parsing remains heuristic rather than a full
shell AST. The repair is intentionally conservative around shell functions and
nested control flow, which is acceptable for this source-authority signal.

## Validation

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'source_authority'`: `111 passed`, `74 deselected`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`: `185 passed`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`: `1180 passed`, `1 warning`, `67 subtests`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`: passed
- `git diff --check`: passed
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl`: passed

## Next Gate

Commit the repair, then run one live same-shape `compile-compcert` speed rerun.
Do not run proof_5 or broad measurement until that live rerun records:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`
