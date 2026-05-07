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
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 4 | 7.5s | 6m08s |
| mew implement_v2 | 0/1 | 20m32s | 38 model turns | 59 tool results | 3 writes/edits | 13.1s | turn 11 |

## Step Shape

Codex follows a compact frontier, even though this saved reference trace is not
a passing score artifact:

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

## 2026-05-08 Step Update

Latest valid mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-make-mips-interpreter-step-shape-10min-20260508-0223-visual-quality-gate-v2/make-mips-interpreter__vXPoMWc`

The prior invalid diagnostic
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-make-mips-interpreter-step-shape-10min-20260508-0206-visual-quality-gate`
did not preserve `selected_lane=implement_v2` because multiple
`--work-guidance` flags were passed. Do not use it as v2 step evidence.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0223` | 0/1 | 9m47s | 22 model turns | 39 tool calls | turn 7 | visual-oracle grounding |

The latest repair was directionally useful but incomplete:

- v2 no longer accepts only file existence, valid headers, boot stdout, or
  framebuffer logs as enough evidence for runtime visual artifact tasks.
- v2 now asks for visual quality evidence, but it can still accept
  model-authored/scaled visual-quality checks that are not grounded in the
  task's reference oracle.
- The external verifier passed VM execution and frame existence but failed
  reference similarity (`0.8065 < 0.95`).

Repair in progress remains generic: runtime visual artifact tasks must not
finish on self-proxy visual quality proof. The finish gate now requires
completed tool evidence grounded in a task-provided visual oracle: exact
task-provided dimensions/resolution, task-provided reference/golden/oracle
similarity or SSIM with pass semantics, or explicit expected-output markers.
The next live diagnostic is still required before speed/proof: run another
10min `make-mips-interpreter selected_lane=implement_v2` step-shape proof,
compare it against the Codex reference, and record the next generic blocker
before editing again.

## 2026-05-08 Current Pre-Speed Gate

Current-head pre-speed was started after the visual-oracle grounding patch and
the acceptance-architecture research request.

Focused checks:

- `uv run pytest --no-testmon tests/test_acceptance.py -k 'runtime_visual_artifact or visual or similarity or dimension' -q`
  passed: `11 passed`.
- `uv run pytest --no-testmon tests/test_implement_lane.py -k 'finish_gate or runtime_artifact or visual or source_grounding' -q`
  failed: `test_implement_v2_live_json_finish_gate_can_continue_then_complete`
  now observes `finish_gate_block_count == 1` where the test expected `2`.
- `uv run pytest --no-testmon tests/test_dogfood.py -k 'runtime_finish_gate_emulator or terminal_bench_replay' -q`
  passed: `7 passed`.
- Exact replay and terminal-bench replay dogfood for the `0223` artifact pass
  when asserting external reward `0.0`.
- `m6_24-runtime-finish-gate-emulator` dogfood passes.

Because the focused implement-lane gate is red, do not spend a new live 10min
step-shape diagnostic or `speed_1` yet. The pre-speed gate has correctly stopped
before live budget.

Important correction: the saved Codex trace is also an external-score miss. It
passes frame existence and reference similarity, but fails `test_vm_execution`
because the captured stdout does not contain the expected
`I_InitGraphics: DOOM screen size: w x h: 320 x 200` line before frame handoff.
The latest mew `0223` trace has the opposite shape: it passes VM execution and
frame existence, but fails reference similarity (`0.8065 < 0.95`).

So the step lesson is not "copy the saved Codex result as a pass." It is:

- Codex-like hot path is still valuable: cheap broad probes, one coherent patch,
  one small runtime-instruction repair, then verifier-shaped checks.
- The score gap is now finish/oracle state alignment: mew must carry typed
  oracle obligations and evidence through finish instead of relying on
  self-authored visual-quality prose.
- The acceptance research in
  `docs/REVIEW_2026-05-08_ACCEPTANCE_GATE_ARCHITECTURE.md` recommends freezing
  further string/regex growth and moving to `EvidenceEvent` / `OracleBundle` /
  cited-finish v0.

Next action: resolve the current focused test failure and choose the typed
evidence migration slice before running another live 10min step diagnostic.

## 2026-05-08 Typed-Evidence Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-make-mips-interpreter-step-shape-10min-20260508-0341-typed-evidence-prespeed/mew-m6-24-v2-make-mips-interpreter-step-shape-10min-20260508-0341-typed-evidence-prespeed/make-mips-interpreter__NJSSM9e`

Validation before/after the live run:

- focused runtime visual acceptance tests passed (`11 passed`);
- focused implement-lane finish/runtime/source tests passed (`20 passed`);
- focused dogfood replay/emulator tests passed (`7 passed`);
- exact replay of this `0341` artifact passed with external reward `0.0`;
- terminal-bench replay dogfood for this `0341` artifact passed with external
  reward `0.0`.

| Agent | Score | Wall | Model turns / messages | Tool calls | Prompt chars | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | n/a | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0341` | 0/1 | 10m00s inner / 11m21s Harbor | 16 model turns | 27 tool calls | 2,140,279 | turn 8 | blocked on `runtime_artifact_missing`; model request timed out |

Step delta:

1. Both Codex and mew start with cheap source/ELF inspection. Both encounter a
   missing `file(1)` style probe early and recover through source/symbol tools.
2. Codex keeps the source/ELF frontier compact and parallel: it reaches one
   coherent `vm.js` patch at `367.803s`, then applies one small `wsbh` repair
   and verifies frame files.
3. mew now has a better shape than `0223`: `model_turns` fell `22 -> 16`,
   `tool_calls` fell `39 -> 27`, and `prompt_chars_total` fell
   `3,608,027 -> 2,140,279`.
4. mew still serializes the frontier through seven model turns before the first
   write. The probes are sensible, but they are not compressed into a Codex-like
   "frontier complete -> coherent patch" transition.
5. After first write, mew patches toward the same runtime class, but repeated
   verifier failures end at a typed structured blocker:
   `runtime_artifact_missing` / `missing_artifact` for `/app/frame0000.bmp`.
6. The current blocker is no longer premature acceptance. The gate keeps the
   session blocked and replay can recompute the same structured failure. The
   remaining gap is turning typed runtime failure evidence into the next focused
   patch quickly enough before wall/model budget expires.

Current implication:

- Do not run `speed_1`, `proof_5`, or broad measurement from this state.
- Do not continue growing string/regex acceptance blockers for this family.
- The next generic repair should target the implement_v2 evidence-to-action
  path: compact typed runtime failure evidence into a model-visible next-patch
  frontier, so the model sees "producer/runtime artifact missing at command X,
  syscall/runtime tail Y, inspect/patch Z" without re-reading broad context.
- The typed evidence acceptance design in
  `docs/DESIGN_2026-05-08_M6_24_TYPED_EVIDENCE_ACCEPTANCE.md` has completed
  round-2 multi-model review with no needs-fix findings and is the intended
  direction for replacing further acceptance-gate string growth.

## 2026-05-08 Phase-6 Typed-Evidence Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-typed-evidence-phase6-make-mips-step-shape-10min-20260508-0512/make-mips-interpreter__S23sXhg`

Validation:

- commit `e832ce1` completed typed-evidence Phase 6 after codex-ultra approval;
- focused tests, exact replay, terminal-bench replay dogfood, and runtime
  finish-gate emulator were green before the live diagnostic;
- exact replay of the `0512` artifact passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured failure class
  `runtime_artifact_missing` and replay mismatch count `0`.

| Agent | Score | Wall | Model turns / messages | Tool calls | Prompt chars | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | n/a | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0512` | 0/1 | 10m16s Harbor | 21 model turns | 33 tool calls | 3,293,792 | turn 7 | source-declared artifact path missed, then `runtime_artifact_missing` / model timeout |

Step delta:

1. Codex finds the source-declared output path before writing: it searches the
   source tree and sees `doomgeneric_img.c` print/save `/tmp/frame.bmp`.
2. mew performs useful cheap probes, but the source frontier is too shallow:
   it inspects `/app/doomgeneric`, later tries the wrong
   `/app/doomgeneric/doomgeneric.c`, and does not discover the nested
   `doomgeneric/doomgeneric/doomgeneric_img.c` path before first write.
3. Because the source-declared path was missed, mew writes a `vm.js` that tries
   to prove `/app/first_frame.png` / `/app/frames/frame000001.png`; the hidden
   external verifier expects `/tmp/frame.bmp`.
4. The typed gate behaves correctly: it blocks instead of falsely completing.
   The remaining gap is earlier than acceptance. The model needs a
   source-first artifact-path frontier before the first coherent patch.

Current implication:

- Do not run `speed_1`, `proof_5`, or broad measurement from this state.
- Do not repair this by teaching a `make-mips-interpreter` path.
- The next generic repair is a hard-runtime source frontier rule: before the
  first write/edit on runtime-generated artifact tasks, do one recursive source
  pass for output paths/stdout markers and treat source-declared paths as
  authoritative execution-contract targets.

## 2026-05-08 Source-Frontier Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-frontier-make-mips-step-shape-10min-20260508-0535/make-mips-interpreter__u3R5nZ7`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes after the follow-up typed ref-selection
  repair.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0535` | 0/1 | 9m47s Harbor | 27 history turns | 33 tool calls | turn 12 | finish-gate typed evidence ref loop, then model timeout |

Step delta:

1. The source-frontier repair worked. Turn 1 now performs a recursive
   source/output-path pass before editing. `rg` is absent in the Harbor
   container, but the model recovers on turn 2 with shell/source probes instead
   of skipping the frontier entirely.
2. mew eventually reaches the correct source-declared `/tmp/frame.bmp` path and
   the external verifier passes frame existence plus reference similarity.
3. The remaining external score miss is the same class as the saved Codex
   reference: stdout does not contain the expected
   `I_InitGraphics: DOOM screen size: w x h: 320 x 200` marker before frame
   handoff.
4. The new mew-only inefficiency is after internal verifier success: finish
   synthesis auto-selected early typed evidence refs, so late final
   verifier/artifact evidence did not cover required oracle obligations. The
   gate repeated `missing_typed_obligation` until model timeout.

Repair applied after this diagnostic:

- `recommend_finish_evidence_refs(...)` now selects evidence refs by required
  oracle obligation coverage instead of first-N passing events.
- finish parsing accepts string evidence-ref ids as shorthand for
  `{"kind": "evidence_event", "id": ...}`.
- implement_v2 still preserves source-grounding refs when adding recommended
  typed finish refs.
- response contract now names `finish.evidence_refs` explicitly, while
  `acceptance_evidence` is only an optional human-readable summary.

Current implication:

- Do not run broad measurement yet.
- Run one more 10min step-shape diagnostic before `speed_1` / `proof_5`.
- The next diagnostic should answer whether the finish-gate dead loop is gone.
  If it is gone, the next generic gap is stdout/runtime behavior alignment, not
  artifact existence or typed acceptance.

## 2026-05-08 Typed-Ref Selection Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-typed-ref-selection-make-mips-step-shape-10min-20260508-0608/make-mips-interpreter__eaxj8GH`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0608` | 0/1 | 5m51s Harbor | 12 history turns | 24 tool calls | turn 8 | runtime artifact missing, then transient model backend error |

Step delta:

1. The typed-finish `missing_typed_obligation` loop did not recur. The repair
   succeeded for the observed failure class.
2. mew now reaches a coherent `vm.js` write at turn 8 and follows a compact
   runtime-repair path until `node vm.js` fails with
   `unimplemented SPECIAL fn=52` before `/tmp/frame.bmp` exists.
3. Replay classifies the latest concrete runtime failure as
   `runtime_artifact_missing` with `required_next_probe=Inspect the producing
   substep and artifact path before another rebuild.`
4. The live run then stopped on `Codex Web API error:
   IncompleteRead(5188 bytes read)` before the next patch. This is not a
   make-mips acceptance blocker; it exposes a generic implement_v2 transport
   gap where transient backend errors were converted into lane failure instead
   of being retried inside the same model turn.

Repair applied after this diagnostic:

- `_call_model_turn(...)` now retries one transient `model_backend_error` such
  as `IncompleteRead`, connection resets, rate limits, overloads, and 5xx
  backend failures.
- `model_timeout` and `model_json_parse_error` remain replayable lane failures
  and are not retried by this patch.
- retry count is recorded in the model response shape and observation when a
  transient retry happens.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- The next diagnostic should distinguish a true runtime-special-instruction
  repair gap from transient backend noise.
