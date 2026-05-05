# M6.23.2 Phase 3 Read-Only Proof - 2026-05-05

## Scope

This proof covers the Phase 3 `implement_v2` read/search spike from
`docs/DESIGN_2026-05-05_M6_23_2_IMPLEMENT_V2_NATIVE_TOOL_LOOP.md`.

`implement_v2` remains default-off. The proof only covers the fake-provider
read-only runtime and does not grant write-capable implementation completion.

## Commit

- Commit: `d0c3ca7 Add implement v2 read-only spike`
- Review: `codex-ultra` session `019df861-1878-7963-96ef-bfb5433c6e4d`
- Review result: `STATUS: PASS`, `FINDINGS: none`

## Validation

```text
uv run pytest --no-testmon tests/test_implement_lane.py tests/test_work_lanes.py -q
=> 40 passed, 2 subtests passed

uv run ruff check src/mew/implement_lane tests/test_implement_lane.py tests/test_work_lanes.py
=> All checks passed

git diff --check
=> pass
```

## Proved Behavior

- v1 remains default and authoritative.
- Explicit `implement_v2` stays visible but default-off and non-authoritative.
- Fake provider read-only calls produce paired `ToolResultEnvelope` results.
- Replay manifest validation stays green for successful and failed/denied calls.
- Read-only `analysis_ready` is never counted as implementation completion.
- `task_complete`/`completed` finish claims are blocked in read-only mode.
- Path traversal and read-only write/execute attempts are rejected without
  mutating the workspace.
- Large read results are clipped and receive content refs.
- Git read tools are constrained to allowed repo roots, force diffstat, disable
  external diff/textconv/pager/fsmonitor/untracked cache, convert nonzero exits
  and timeouts into paired failed results, and redact sensitive git path output.

## Next

M6.23.2 should now record an explicit resume decision before M6.24 continues:

1. Keep `implement_v1` as the production lane for M6.24 proofs.
2. Treat `implement_v2` Phase 3 as a shadow/read-only diagnostic lane only.
3. Resume M6.24 only when the next proof artifact explicitly names the
   producing lane.
