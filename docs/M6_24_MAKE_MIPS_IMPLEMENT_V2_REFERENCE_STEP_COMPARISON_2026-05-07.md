# M6.24 make-mips-interpreter implement_v2 Reference-Step Comparison

Date: 2026-05-07 JST

## Compared Runs

- Codex reference:
  `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq`
- mew implement_v2:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-make-mips-interpreter-speed1-20260507-2017-integration-observation/make-mips-interpreter__AyhHmxB`

## Outcome

| Agent | Score | Wall | Model turns / messages | Tool calls | Edits | First tool | First patch |
|---|---:|---:|---:|---:|---:|---:|---:|
| Codex reference | pass | 6m56s | 8 messages | 34 completed tool calls | 4 | 7.5s | 6m08s |
| mew implement_v2 | 0/1 | 20m32s | 38 model turns | 59 tool results | 3 writes/edits | 13.1s | turn 11 |

## Step Shape

Codex follows a compact frontier:

1. Parallel cheap source/ELF inspection: `rg`, `rg --files`, `file/readelf`.
2. Focused ABI/source narrowing: `readelf`, map file, symbol search, source `rg`.
3. Instruction/runtime surface sampling: `objdump`, source slices, opcode scans.
4. One large coherent `vm.js` patch.
5. Run `node vm.js`, patch one missing instruction (`wsbh`), rerun.
6. Verify `/tmp/frame.bmp` and `/tmp/frame_000001.bmp` headers, size, and nonzero pixels.

mew implement_v2 did useful work, but the frontier was too fragmented:

1. It inspected the same source/ELF surfaces, but in many model turns.
2. It generated `vm.js` through repeated whole-file writes instead of one coherent patch.
3. It spent many turns polling a long verifier command after producing a frame.
4. It accepted an internal proof that took about 86s to create `/tmp/frame.bmp`; the external verifier waits about 30s.
5. It then hit a finish-gate source-grounding projection gap and exhausted turns.

## Repair Applied Here

The source-grounding projection gap was generic and fixed in code:

- `acceptance.py` now exposes `implementation_source_ref_matches_text()`.
- `implement_v2` finish synthesis appends verified source/binary grounding checks from prior completed `read_file`, `search_text`, `glob`, or `run_command` results.
- This prevents losing earlier source evidence when the latest structured final verifier is the only model-visible acceptance check.

Validation:

- `uv run pytest --no-testmon tests/test_implement_lane.py -q -k 'finish_gate or source_grounding or runtime_artifact'`
- `uv run ruff check src/mew/acceptance.py src/mew/implement_lane/v2_runtime.py tests/test_implement_lane.py`
- exact `2017` terminal-bench replay
- exact `2017` terminal-bench replay dogfood
- runtime-artifact-latency emulator dogfood

## Remaining Divergence

The source-grounding fix only removes a late false blocker. It does not make
mew Codex-shaped yet.

Next high-value repair is not another task-specific MIPS rule. It should make
implement_v2 prefer the Codex hot path:

- cheap parallel source/ELF probes first,
- one coherent patch once the compatibility surface is known,
- external-verifier-shaped runtime proof with the same path and latency budget,
- proof/evidence sidecars retained, but not inflated into every model prompt.

Do not run broad measurement from this state. Run a bounded same-shape rerun
only after the runtime-latency contract or hot-path tuning is implemented and
pre-speed checks pass.
