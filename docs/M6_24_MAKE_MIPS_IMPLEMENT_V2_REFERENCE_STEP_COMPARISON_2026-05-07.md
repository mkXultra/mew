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

## 2026-05-08 Transient-Retry Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-transient-retry-make-mips-step-shape-10min-20260508-0622/make-mips-interpreter__ipm3JtP`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0622` | 0/1 | 9m43s Harbor | 29 history turns | 40 tool calls | turn 8 | finish gate repeats `missing_typed_obligation` after internal verifier pass |

Step delta:

1. The transient backend failure did not recur; the retry repair succeeded for
   the observed transport class.
2. mew reached the runtime repair path, produced `/tmp/frame.bmp`, and the
   final grounded verifier command `call-verify-vm-js-frame-6-grounded` passed
   internally with `frame written: /tmp/frame.bmp`, `source_elf`, `source_tree`,
   dimensions, and color diversity evidence.
3. External reward is still `0.0` because Harbor verifier did not find
   `/tmp/frame.bmp` after mew exited; replay classifies that separately as a
   runtime artifact latency/cwd/lifecycle gap.
4. The immediate loop-level blocker before spending another live proof is
   finish evidence projection: the model supplied `finish.evidence_refs`, but
   they were incomplete/stale, so implement_v2 did not add the latest
   obligation-covering verifier/source refs and kept blocking on
   `missing_typed_obligation`.

Repair applied after this diagnostic:

- finish acceptance now merges obligation-driven typed refs into existing
  model-provided refs instead of only filling refs when none were supplied;
- required verifier/artifact/source refs are prioritized within the 16-ref
  finish window;
- existing model refs remain supplemental after required refs;
- supplemental fallback refs are not allowed to evict model refs when the model
  already supplied refs.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- If the finish-gate repeat is gone, the next generic blocker is likely the
  external-verifier-visible runtime artifact lifecycle for `/tmp/frame.bmp`.

## 2026-05-08 Finish-Ref-Merge Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-finish-ref-merge-make-mips-step-shape-10min-20260508-0646/make-mips-interpreter__E65uqpE`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0646` | 0/1 | 10m15s Harbor | 14 model turns | 23 tool calls | turn 6 | `apply_patch` rejected valid patch text with redundant matching `path`; later model timeout |

Step delta:

1. The finish-gate repeat disappeared:
   `finish_gate_block_count=0`, `typed_evidence_gate_block_count=0`, and
   `missing_typed_evidence_count=0`.
2. mew now reaches the same broad work class as Codex: cheap source/ELF probes,
   a `vm.js` write, runtime verification, and targeted runtime-instruction /
   syscall repair.
3. The remaining step shape is still inefficient: mew used 14 turns and
   2.17M prompt chars, while Codex used 8 messages. A yielded debug command
   still caused a model-mediated poll/cancel cycle.
4. The immediate local blocker is a generic write-surface issue, not a MIPS
   solver issue: the model emitted `apply_patch` with both a full patch body
   and `path: vm.js`. v2 rejected all `path` on `apply_patch`, even when the
   patch body contained the authoritative `*** Update File: vm.js` header.

Repair applied after this diagnostic:

- `apply_patch` now accepts a redundant `path` only when patch text is present
  and the path matches the patch update-file header;
- mismatched redundant paths are rejected;
- path/edits structured bypass without patch text remains rejected.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- If this blocker is gone, the next likely target is either model-mediated
  poll/cancel churn for long debug commands or external-verifier-visible
  `/tmp/frame.bmp` lifecycle alignment.

## 2026-05-08 Apply-Patch-Path Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-apply-patch-path-make-mips-step-shape-10min-20260508-0705/make-mips-interpreter__oM2KQTL`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0705` | 0/1 | 3m56s Harbor | 6 model turns | 12 tool calls | turn 4 | recoverable `model_json_parse_error` while emitting the next `apply_patch` repair |

Step delta:

1. The redundant `apply_patch.path` blocker disappeared.
2. mew now gets to a useful runtime-repair loop quickly: source/ELF probes,
   `vm.js` write, verifier-shaped execution, runtime failure classification,
   and one focused source read of `my_stdlib.c`.
3. The live lane stopped on transport shape rather than task reasoning:
   the model attempted the next patch as a JSON tool call, but the response was
   not one complete parseable JSON object.
4. This is generic to the current provider-neutral JSON transport. Large or
   partially streamed tool-call patches can fail before the write runtime sees
   them.

Repair applied after this diagnostic:

- recoverable `model_json_parse_error` now gets exactly one retry when the raw
  excerpt starts like a JSON object with `tool_calls` or `finish`;
- the retry prompt preserves the same immediate repair intent, demands one
  complete JSON object, and tells the model to avoid half-written large patch
  strings;
- arbitrary malformed prose is still not retried.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- If this blocker is gone, compare whether v2 can continue from
  `my_stdlib.c` evidence into the next runtime patch without restarting broad
  exploration.

## 2026-05-08 JSON-Parse-Retry Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-parse-retry-make-mips-step-shape-10min-20260508-0720/mew-m6-24-json-parse-retry-make-mips-step-shape-10min-20260508-0720/make-mips-interpreter__t4UwS6e`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0720` | 0/1 | 10m15s Harbor | 23 history turns | 38 tool calls | turn 4 | diagnostic stdout marker miss polluted hard-runtime frontier |

Step delta:

1. The recoverable JSON parse retry repair worked; the prior transport blocker
   did not recur.
2. mew continued through source/ELF probes, `vm.js` generation, runtime
   verifier failure, and syscall/runtime diagnostics.
3. The hard failure before the diagnostic was a real runtime verifier
   obligation: `/tmp/frame.bmp` was missing after the VM verifier command.
4. A later diagnostic stdout probe expected `TRACE syscall` and missed that
   stream marker. That diagnostic was useful evidence, but it is not an
   acceptance/verifier contract.
5. v2 incorrectly let that observational diagnostic failure replace the
   hard-runtime frontier/final artifact with `stdout` /
   `artifact_validation_failure`, hiding the actionable `/tmp/frame.bmp`
   runtime failure.

Repair applied after this diagnostic:

- observational diagnostic contracts can still record failed
  `artifact_evidence` and a blocked structured finish gate;
- those contracts no longer turn a completed diagnostic command into a failed
  tool result;
- those contracts no longer update the hard runtime frontier, final artifact,
  or latest runtime/build failure projection.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- The next diagnostic should show whether v2 now preserves the real latest
  runtime failure and converts it into the next patch, instead of chasing
  non-acceptance diagnostic stream markers.

## 2026-05-08 Diagnostic-Stream-Frontier Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-diagnostic-stream-frontier-make-mips-step-shape-10min-20260508-0748/make-mips-interpreter__E8upwvp`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing miss; frame existence/similarity pass |
| mew implement_v2 `0748` | 0/1 | 10m16s Harbor | 18 model turns | 37 tool calls | turn 8 | `runtime_artifact_missing` for required `/tmp/frame.bmp`; model timeout after several runtime-instruction patch clusters |

Step delta:

1. The observational diagnostic-stream repair worked: diagnostic stdout marker
   misses no longer replace the hard runtime frontier.
2. The latest structured failure is again the actionable runtime artifact
   failure: required `/tmp/frame.bmp` is missing after the fresh VM verifier.
3. mew now preserves typed runtime failure evidence, but still consumes too
   much model context while moving from latest runtime failure to the next
   focused patch.
4. The run used 18 turns and 3.02M prompt chars. Codex reached a comparable
   work shape with 8 messages and a more coherent patch/repair sequence.
5. codex-ultra classified the next gap as
   `implement_v2_hot_path_projection_weight /
   runtime_failure_to_next_patch_frontier_gap`, not as another MIPS-specific
   VM rule.

Repair selected after this diagnostic:

- keep full tool-call arguments in `history.json` and proof artifacts;
- compact next-turn provider history for large source mutation arguments on
  `write_file`, `edit_file`, and `apply_patch` into hash, size, and bounded
  excerpt projections;
- keep command strings visible but bounded;
- do not loosen acceptance, add MIPS/DOOM logic, or increase the turn budget.

Current implication:

- Do not run broad measurement yet.
- After review/commit, run one more 10min `make-mips-interpreter
  selected_lane=implement_v2` step-shape diagnostic before `speed_1` /
  `proof_5`.
- The next diagnostic should show whether smaller prompt/history projection
  improves latest-failure-to-next-patch focus without hiding the information
  needed for repair.

## 2026-05-08 Provider-History-Projection Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-provider-history-projection-make-mips-step-shape-10min-20260508-0819/make-mips-interpreter__tZdU9w7`

Validation:

- exact replay passes with external reward `0.0`;
- terminal-bench replay dogfood passes with structured replay mismatch count
  `0`;
- runtime finish-gate emulator passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing/marker miss; frame existence/similarity pass |
| mew implement_v2 `0819` | 0/1 | 9m47s Harbor | 20 model turns | 32 tool calls | turn 6 | external stdout marker miss; frame existence/similarity pass; final model turn timed out before finish |

Step delta:

1. This is a material improvement from `0748`: `/tmp/frame.bmp` is now
   produced, external frame existence passes, and external frame similarity
   passes.
2. The external verifier failure shape now matches the Codex reference: reward
   `0.0`, frame checks pass, stdout/timing marker fails.
3. v2 is still slower and chattier than Codex. Prompt volume dropped from
   `3,021,650` to `2,831,856` chars, but the loop still used `20` turns and
   timed out before the final model could emit `finish`.
4. The latest internal structured failure before the final successful verifier
   came from a model-declared `stdout` text_contains contract whose needles
   were projected as empty, producing `runtime_artifact_missing` for stdout
   even though the terminal output contained the markers. The next turn worked
   around it with command-internal `grep` checks and a simpler stdout contract.
5. codex-ultra classified the remaining external blocker as
   `external_verifier_artifact_stdout_timing_race`, and explicitly recommended
   no immediate local code repair because the external shape is now
   Codex-equivalent.

Current implication:

- Do not add MIPS/DOOM-specific stdout ordering hacks.
- Do not resume broad measurement from this artifact alone.
- It is acceptable to run the next controlled same-shape speed/proof step for
  `make-mips-interpreter`, then replay/dogfood and compare step shape again.
- If the next controlled run regresses to a mew-only structural miss, return to
  improvement mode. If it stays Codex-equivalent, this gap can stop blocking the
  broader M6.24 scoped queue.

## 2026-05-08 Controlled Provider-History Speed1

Latest controlled speed artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-provider-history-make-mips-speed1-20260508-1035/make-mips-interpreter__ivvSGpn`

Validation:

- exact replay passes with `work_exit_code=1` and external reward `0.0`;
- terminal-bench replay dogfood passes with external reward `0.0`;
- structured replay mismatch count is `0`.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing/marker miss; frame existence/similarity pass |
| mew implement_v2 `1035` | 0/1 | 17m14s Harbor | 38 model turns | 32 tool calls | turn 7 | stale `/tmp/frame.bmp` handoff caused external verifier early-stop race |

Step delta:

1. The early implementation path is still reasonable: source/output-path probes
   happen before `vm.js`, and the first write occurs at turn 7.
2. Internal verifier commands later produce `/tmp/frame.bmp` and the required
   Doom stdout markers.
3. External verifier failure is worse than the `0819` diagnostic, but the root
   is not a new VM-solving gap. A stale `/tmp/frame.bmp` from the internal
   verifier exists before external pytest launches `node vm.js`.
4. The external test sees the stale path immediately, while `vm.js` unlinks the
   stale file at startup. Pytest then terminates the process before a fresh
   frame and stdout marker are produced, so both stdout and frame tests fail.
5. This should have been handled by `--defer-verify` stale runtime artifact
   cleanup. The cleanup detector missed the implement_v2 proof manifest because
   raw `stage=final-verifier` was ignored after normalized contract projection
   became `stage=command` / `purpose=generic_command`.

Repair selected after this diagnostic:

- recognize raw and normalized implement_v2 contracts when detecting final
  verifier-shaped commands for oneshot cleanup;
- normalize hyphenated contract tokens such as `final-verifier`;
- allow verifier-shaped `stage=command` contracts with expected artifacts to
  trigger stale `/tmp` cleanup, still filtered by runtime-fresh context and
  passed artifact evidence;
- validate with focused oneshot cleanup tests, terminal-bench replay/dogfood
  slice, and ruff before another controlled speed rerun.

Current implication:

- Do not run broad measurement yet.
- Do not add MIPS/DOOM-specific VM fixes for this artifact.
- After review/commit, rerun the same controlled `speed_1` shape. A material
  improvement is either reward pass or movement back to the Codex-equivalent
  stdout timing class with frame existence/similarity passing.

## 2026-05-08 Runtime-Heartbeat Controlled Speed1

Latest controlled speed artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-heartbeat-make-mips-speed1-20260508-1423/make-mips-interpreter__jNFUALC`

Validation:

- exact replay passes with `work_exit_code=1` and external reward `0.0`;
- terminal-bench replay dogfood passes with external reward `0.0`;
- structured replay mismatch count is `0`;
- codex-ultra read-only classifier session
  `019e0626-2849-7922-8380-16b22c92a4c8` classified the run as a normal
  hard-runtime task-solving miss, not a transport, stale-cleanup, or close-out
  regression.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing/marker miss; frame existence/similarity pass |
| mew implement_v2 `1423` | 0/1 | 26m57s Harbor | 35 model turns | 49 tool calls | turn 8 | no `/tmp/frame.bmp`; fragmented runtime patch loop exhausted before frame production |

Step delta:

1. Timeout containment and heartbeat instrumentation worked. This was not the
   previous no-tool-call transport stall: the run completed with replayable
   implement_v2 artifacts, no model error, and paired tool calls/results.
2. The cleanup/close-out repairs are not the blocker here. There was no
   internally passing final verifier handoff; the verifier timed out waiting
   for `/tmp/frame.bmp`, and the artifact was missing.
3. The early shape remains directionally correct: source/output-path probes
   happen before editing, and the first `vm.js` write occurs at turn 8.
4. The runtime repair path is still too fragmented. The model iteratively
   patched syscall returns, COP1 fallback, file positioning, and unaligned
   memory transfers, then ended with a verifier-shaped `runtime_artifact_missing`
   / `artifact_validation_failure` for `/tmp/frame.bmp`.
5. Compared to the previous `1109` external pass, this artifact confirms that
   the lane can still regress stochastically on the same task family when it
   does not reuse same-task repair history or converge to one coherent runtime
   patch sequence.

Current implication:

- Do not run broad measurement or another unchanged same-shape speed from this
  artifact.
- Do not add MIPS/DOOM-specific VM rules.
- The next generic repair should target runtime-frontier hot-path conversion:
  latest structured runtime failure and prior same-task repair evidence should
  become a compact next-patch frontier, so v2 moves from failure evidence to a
  focused patch without broad rediscovery or many small model-mediated runtime
  edits.

## 2026-05-08 Repair-History Pre-Speed Diagnostic

Latest current-head mew artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-repair-history-make-mips-step-shape-10min-20260508-1520/make-mips-interpreter__Mf9NJoB`

Validation:

- the first `1517` attempt is harness-invalid: Harbor command-template
  formatting interpreted unescaped JSON guidance braces as placeholders;
- exact replay of the valid `1520` artifact passes with `work_exit_code=1` and
  external reward `0.0`;
- terminal-bench replay dogfood passes with external reward `0.0`;
- `m6_24-implement-v2-hard-runtime-progress-continuation-emulator` passes.

| Agent | Score | Wall | Model turns / messages | Tool calls | First patch/write | Latest blocker |
|---|---:|---:|---:|---:|---:|---|
| Codex reference | 0/1 | 6m56s | 8 messages | 34 completed tool calls | 6m08s | stdout timing/marker miss; frame existence/similarity pass |
| mew implement_v2 `1423` | 0/1 | 26m57s Harbor | 35 model turns | 49 tool calls | turn 8 | no `/tmp/frame.bmp`; fragmented runtime patch loop exhausted before frame production |
| mew implement_v2 `1520` | 0/1 | 11m16s Harbor / 600.033s mew wall | 15 model turns | 24 tool calls | turn 5 | wall budget exhausted; final closeout hides earlier actionable runtime/artifact frontier |

Step delta:

1. The bounded repair-history/context capsule section was injected as
   `implement_v2_repair_history` with `945` dynamic chars and no raw
   duplication in task-contract guidance.
2. The hot path improved materially from `1423`: model turns dropped `35 -> 15`,
   tool calls dropped `49 -> 24`, prompt chars dropped `5,576,901 ->
   1,680,301`, and first write moved from turn `8` to turn `5`.
3. The early shape now matches the intended sequence more closely: T1-T4 do
   source/runtime frontier probes, T5 writes `vm.js`, then the lane runs focused
   verifier/patch iterations instead of broad rediscovery.
4. It still does not match Codex. Codex reaches its external failure shape in
   `8` messages and about `416s`; mew spends the whole 600s lane wall budget
   and still exits blocked.
5. The latest closeout is wall-budget exhaustion, but earlier turns contained
   actionable runtime/artifact frontier failures such as missing `/tmp/frame.bmp`.
   The final killed/empty active-command state should not replace that prior
   actionable frontier as the main reentry signal.

Current implication:

- Do not run broad measurement or another unchanged same-shape speed from this
  artifact.
- Do not add MIPS/DOOM-specific VM rules.
- Next generic repair:
  `wall_budget_closeout_prior_runtime_frontier_projection`.
- The repair should preserve the latest actionable runtime/artifact frontier
  when wall budget prevents another turn, so reentry sees the useful failure
  rather than a generic wall timeout or killed verifier closeout.
- After the repair, run focused UT/local replay/dogfood/emulator, review, and
  one more 10 minute step-shape diagnostic before `speed_1` / `proof_5`.

## 2026-05-08 Wall-Budget Closeout Projection Repair

Repair implemented:

- `implement_v2` runtime state preserves an earlier actionable
  `runtime_artifact_missing` / artifact frontier when the final result is only
  a low-signal active-command closeout;
- replay mirrors the same projection for `current.implement_v2.latest_failure`
  and `current.next_action`;
- closeout-only and mixed closeout-only artifacts still route to active-command
  closeout recovery instead of being hidden.

Validation:

- focused closeout tests: `5 passed`;
- `tests/test_terminal_bench_replay.py`: `32 passed`;
- `tests/test_implement_lane.py`: `203 passed`;
- scoped ruff: pass;
- exact `1520` replay: pass;
- exact `1520` terminal-bench replay dogfood: pass;
- `m6_24-implement-v2-hard-runtime-progress-continuation-emulator`: pass;
- codex-ultra review session `019e065a-716d-7121-b01a-92266beb9196`:
  `APPROVE`.

Current exact replay projection for `1520`:

- `current.implement_v2.latest_failure.provider_call_id`:
  `call-verify-vm-10b`;
- `failure_class`: `runtime_artifact_missing`;
- `failure_kind`: `missing_artifact`;
- `failure_phase`: `runtime`;
- `active_command_closeout_failed`: `false`;
- `next_action`: runtime producer/resource/syscall frontier blocked before
  `/tmp/frame.bmp`.

Next operation:

- commit this repair;
- run one same-shape 10 minute `make-mips-interpreter` step-shape diagnostic;
- compare against the Codex reference before any `speed_1` / `proof_5`.
