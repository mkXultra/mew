# M6.24 WorkFrame Variant Comparison - 2026-05-11

Purpose: compare WorkFrame reducer variants on the same `make-mips-interpreter`
10 minute diagnostic before deciding whether to flip the default WorkFrame.

## Command

```bash
uv run python scripts/run_workframe_variant_step_checks.py make-mips-interpreter \
  --comparison-plan m6-24-tool-harness \
  --mode step-check-10min \
  --max-parallel 3 \
  --output proof-artifacts/terminal-bench/harbor-smoke/workframe-variant-comparison-make-mips-interpreter-20260511-131738.json
```

The initial summary reader missed Terminal-Bench v2 rewards because Harbor now
stores them at `verifier_result.rewards.reward`. Commit `3a9c940` fixed the
runner and resummarized the existing artifacts into:

`proof-artifacts/terminal-bench/harbor-smoke/workframe-variant-comparison-make-mips-interpreter-20260511-131738-resummarized.json`

## Results

All variants failed the external task (`reward=0.0`, `work_exit_code=1`). This
comparison still produced a useful default decision because the variants failed
with different step shape and diagnostic quality.

| variant | reward | work exit | stop | fastcheck | turns | tool calls | first edit | first verifier | prompt chars | WorkFrame bytes | decision |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| `transition_contract` | 0.0 | 1 | `implement_v2_blocked` | pass | 11 | 18 | 211s | 227s | 500,651 | 4,718 | keep as default |
| `minimal` | 0.0 | 1 | `implement_v2_failed` | pass | 16 | 30 | 275s | 275s | 795,144 | 2,714 | keep as comparator |
| `transcript_tool_nav` | 0.0 | 1 | `implement_v2_failed` | fail | 25 | 46 | none | none | 1,161,879 | 10,989 | do not promote |

## Failure Families

`transition_contract`:

- `patch_anchor_mismatch:patch_exact_match_miss:path:/app/vm.js`
- `runtime_failure:nonzero_exit:artifact:/app/frame000000.ppm:/app/frame000000.ppm`

`minimal`:

- `runtime_artifact_missing:missing_artifact:artifact:/tmp/frame.bmp:/tmp/frame.bmp`
- `runtime_failure:nonzero_exit:artifact:/tmp/frame.bmp:/tmp/frame.bmp`
- `model_timeout:unknown:summary:provider returned no valid model turn`

`transcript_tool_nav`:

- `tool_availability_gap:source_frontier_probe_unavailable:summary:file`
- `model_timeout:unknown:summary:provider returned no valid model turn`

## Decision

Keep `transition_contract` as the default WorkFrame variant.

Do not flip to `transcript_tool_nav`. It exposed too much navigational state,
exceeded the WorkFrame cap (`10,989 > 6,144` bytes), never reached edit or
verifier calls in the diagnostic, and spent the most prompt budget.

Do not promote `minimal` yet. It has a clean small WorkFrame and a useful
artifact-oriented failure, but it was slower than `transition_contract` and
timed out near the step-check boundary.

## Next Repair

The next repair should not add a new WorkFrame variant or another
frontier/todo/evidence projection. Repair the generic `transition_contract`
hot path:

1. Convert patch-anchor mismatch into a direct re-anchor or bounded rewrite
   action instead of a blocker loop.
2. Preserve the exact runtime artifact obligation from the latest verifier
   result without confusing internal WorkFrame artifacts with the external
   Terminal-Bench target. In this run, WorkFrame cited internal
   `/app/frame000000.ppm`, while the external verifier failure is the missing
   `/tmp/frame.bmp`; the repair should carry both roles distinctly and should
   not promote the internal surrogate path as the external acceptance target.
3. Re-run focused UT/fastcheck/micro checks first.
4. Run one same-shape `transition_contract` 10 minute diagnostic.
5. Compare against the Codex reference step shape before any `speed_1` or
   `proof_5`.

Phase 7 state: comparison substrate is usable and the default decision is clear,
but task success is still red. The WorkFrame proof gate remains open.
