# M6.24 Dossier: Hard Runtime Artifact Frontier

Status: active improvement-phase dossier

Scope:

- primary tasks: `make-mips-interpreter`, `make-doom-for-mips`
- family: interpreter / emulator / game-runtime tasks that must produce a
  verifier-visible runtime artifact such as `/tmp/frame.bmp`
- selected gap classes:
  - `hard_task_implementation_strategy_contract_retention`
  - `runtime_visual_artifact_quality_contract`
  - `runtime_artifact_missing`
  - `external_expected_artifact_missing`

## Why This Dossier Exists

This family has more than two repair/rerun cycles and multiple historical
successes plus regressions. The next repair must not be selected from only the
latest live failure. Before adding hard-runtime prompt guidance, profile logic,
finish-gate logic, or runtime-artifact detectors, read this dossier and answer
the preflight in `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`.

## Chronology

| Date | Artifact / Doc | Result | Failure / movement | Implemented layer |
|---|---|---:|---|---|
| 2026-04-29 | `docs/M6_24_VISUAL_QUALITY_SPEED_RERUN_2026-04-29.md` | `make-mips-interpreter` `1/1` | Final verifier-shaped proof produced Doom stdout markers and fresh frame evidence; cleanup prevented stale handoff. | verifier/proof + runtime artifact contract |
| 2026-04-29 | `docs/M6_24_ARTIFACT_HANDOFF_SPEED_RERUN_2026-04-29.md` | `make-mips-interpreter` `1/1` | mew stayed in the hard runtime loop until a final MIPS `SPECIAL3` `EXT` / `INS` repair; external verifier passed. | hard-runtime repair loop + source/runtime edit |
| 2026-04-29 | `docs/M6_24_MAKE_MIPS_PROOF_5_2026-04-29.md` | `make-mips-interpreter` `1/5` | Remaining misses split into visual quality, exact stdout/fresh timing, and JSON robustness. | proof escalation evidence |
| 2026-04-29 onward | `make-doom-for-mips` rows in `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md` | repeated `0/1` | v2 reached source-backed runtime builds and VM runs, but repeatedly missed `/tmp/frame.bmp` after runtime/artifact failures. | runtime frontier and continuation gates |
| 2026-05-07 13:06 | `mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1306` | `0/1` | Tool-contract friction before provider error; `search_text` and no-contract diagnostic exec shape were too brittle. | tool/runtime |
| 2026-05-07 13:41 | `mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1341-tool-contract-repair` | `0/1` | stdout/stderr artifact targets normalized incorrectly; external verifier still expected `/tmp/frame.bmp`. | verifier/proof + acceptance normalization |
| 2026-05-07 14:09 | `mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1409-stream-contract` | `0/1` | Internal structured final verifier passed on `/app/frame000000.bmp` / `/app/frames/frame000000.bmp`, but hidden external verifier expected `/tmp/frame.bmp`; replay now extracts that feedback. | finish-gate projection + external feedback extraction |
| 2026-05-07 15:11 | `mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1511-external-artifact-feedback` | `0/1` | v2 moved into real runtime task-solving. It attempted syscall, WAD, and frame-path repairs, but stopped with `runtime_artifact_missing`: no `/app/frame0.bmp` or `/tmp/frame.bmp`; stdout shows Doom initialization then `-iwad not specified` / `Trying IWAD file:doom2.wad` / `vm_status=1`. Measurement caveat: Harbor omitted `timeout_seconds` / `{max_wall_seconds_option}`, so continuation gates were disabled. | current repair selection evidence |
| 2026-05-07 15:59 | `mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1559-runtime-producer-route` | `0/1` | Corrected Harbor timing moved v2 past producer-blocked runtime evidence. Internal final verifier-shaped commands repeatedly passed `/tmp/frame.bmp` and stdout, but external pytest still failed because `/tmp/frame.bmp` was absent and stdout stopped before `I_InitGraphics`. Replay now routes this to `runtime_artifact_latency_contract`: internal proof must match the external verifier's lifecycle/cwd/latency shape, and oneshot cleanup must scan implement_v2 proof manifests for stale `/tmp` runtime artifacts before verifier handoff. | external verifier lifecycle + cleanup projection |
| 2026-05-07 21:11 | `mew-m6-24-v2-make-mips-interpreter-step-shape-10min-20260507-2111` | `0/1` | Harness-shape invalid for the 10min gate because Harbor `{max_wall_seconds_option}` overrode `--max-wall-seconds 600` to `840s`. Product evidence is still useful: v2 reached real source-backed VM behavior and produced a valid `640x400` BMP, but the final structured proof accepted `/app/frame_000000.bmp` while runtime stdout advertised `/tmp/frame.bmp` and the external verifier expected `/tmp/frame.bmp`. | runtime-advertised artifact contract gate |
| 2026-05-08 14:23 | `mew-m6-24-runtime-heartbeat-make-mips-speed1-20260508-1423` | `0/1` | Timeout/heartbeat repairs worked and replay/dogfood are valid, but the same task family regressed from the `1109` external pass into a long fragmented runtime patch loop. v2 performed source/output probes before first write, then spent 35 turns on syscall/file-position/COP1/unaligned-memory repairs and still did not produce `/tmp/frame.bmp`. | runtime-frontier hot-path / prior-repair recall gap |

## Recurring Patterns

- Artifact path evidence alone is not enough. The final proof must be
  verifier-shaped: fresh process, expected stdout markers, expected frame path,
  and image/size/quality checks when available.
- Hard-runtime tasks can be near-solved while still failing the external
  verifier. Treat `node vm.js` local success, frame existence, and stdout
  snippets as partial evidence unless the expected external contract is covered.
- The same runtime artifact can fail at different layers: instruction
  semantics, syscall ABI, runtime CLI/IWAD setup, output path handoff, visual
  quality, or verifier timing.
- The latest v2 run shows a memory/strategy weakness: prior same-task evidence
  included a successful `SPECIAL3` `EXT` / `INS` repair, but v2 active memory
  was empty and the run re-explored syscall/WAD/frame-path hypotheses instead
  of first checking prior same-task repair history.

## Explicitly Avoid Duplicate Fixes

- Do not add another task-specific sentence that says "write `/tmp/frame.bmp`".
  The external expected-artifact feedback path already detects that.
- Do not loosen finish acceptance to pass on internal frame paths. The 14:09
  run proved that is unsafe.
- Do not expand max steps as the first repair. The latest run used 32 history
  turns and stopped on structured runtime evidence; more turns without better
  prior-repair recall is likely to repeat local runtime patches.
- Do not add a broad shell/string classifier. Use structured execution,
  verifier evidence, replay, and emulator fixtures.
- If a final verifier-shaped runtime command stdout/stderr advertises an
  artifact path that matches the contract's artifact shape, the structured
  contract must verify that exact verifier-visible path or explicitly repair the
  producer. A separate internal artifact path is not enough.

## Current Preflight Answer

1. This failure is a narrower version of the historical hard-runtime artifact
   frontier, not a brand-new gap.
2. Previous repairs already addressed path handoff, visual proof quality,
   expected-artifact extraction, terminal evidence, and hard-runtime
   continuation. They did not make `implement_v2` recall same-task repair
   history.
3. The immediate repair should preserve the distinction between an external
   artifact path mismatch and a producer-blocked runtime. The 15:11 artifact is
   the latter: the runtime progressed, emitted domain stdout, then exited before
   producing the expected frame.
4. If the same shape repeats after a corrected timed Harbor command, the likely
   next durable layer is bounded task/gap repair-history input to
   `implement_v2`, exposed as a cited prompt section or read-only provider.
5. The 2026-05-08 14:23 controlled rerun repeats that conclusion after timeout
   containment: the lane did not fail because of model transport, cleanup, or
   finish closeout. It failed because it re-solved a hard-runtime interpreter
   frontier from scratch and fragmented the runtime patch sequence instead of
   using same-task repair history or a compact latest-failure-to-next-patch
   frontier.

## Next Same-Shape Rerun Condition

Before another live `make-mips-interpreter selected_lane=implement_v2` speed:

1. replay the 15:11 artifact and assert `external_reward=0`;
2. dogfood the same artifact through `m6_24-terminal-bench-replay`;
3. add or update an emulator that routes runtime-progress-plus-missing-frame
   evidence to the runtime producer/resource/syscall frontier before path
   alignment or another live speed;
4. validate focused UT plus scoped ruff;
5. run the live speed only with the documented `timeout_seconds` plus
   `{max_wall_seconds_option}` command shape;
6. only then spend one same-shape live speed.

## 2026-05-07 15:59 Repair Gate

Before another live `make-mips-interpreter selected_lane=implement_v2` speed
after the runtime-artifact-latency repair:

1. replay the exact `15:59` artifact and assert `external_reward=0` plus
   `next_action_contains=runtime_artifact_latency_contract`;
2. dogfood the same artifact through `m6_24-terminal-bench-replay` with the
   same next-action assertion;
3. run `m6_24-runtime-artifact-latency-emulator`;
4. prove `mew work --oneshot --defer-verify` cleanup can derive stale `/tmp`
   runtime artifacts from `implement_v2/proof-manifest.json`;
5. validate focused UT plus scoped ruff;
6. then spend at most one same-shape live speed and classify the next gap.
