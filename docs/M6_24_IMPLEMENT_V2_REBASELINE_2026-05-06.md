# M6.24 Implement V2 Scoped Rebaseline

Date: 2026-05-06

Purpose: make M6.24 measure the lane that should become the normal coding
body. Historical `implement_v1` results remain useful repair evidence, but they
must not close M6.24 after `implement_v2` became runnable.

## Decision

M6.24 now runs an `implement_v2` scoped rebaseline before spending more
same-shape close proof budget.

The active scope is still the 25 Terminal-Bench 2.0 tasks from
`docs/M6_24_SOFTWARE_CODING_SCOPE_2026-05-03.md`.

For each scoped task:

1. Run one `speed_1` with `selected_lane=implement_v2`.
2. Record lane id, runtime id, artifact path, runner errors, reward, and replay
   status.
3. If the run misses, is harness-invalid, lacks replayable artifacts, or
   exposes a structural lane gap, stop broad measurement and repair that gap.
4. Reproduce any miss with `mew replay terminal-bench` and
   `mew dogfood --scenario m6_24-terminal-bench-replay` before code repair.
5. After repair, run focused UT, replay, dogfood, any matching emulator, then
   one same-shape `speed_1`.
6. Spend `proof_5` only for close candidates, variance-sensitive repairs, or
   when the controller is ready to resume measurement.

## Pre-Speed Gate

Before spending another live `speed_1` after any repair, run this gate in
order:

1. focused UT for the repaired behavior and nearby finish/replay/projection
   invariants;
2. `mew replay terminal-bench` against the latest relevant saved artifact with
   assertions matching the selected failure;
3. `mew dogfood --scenario m6_24-terminal-bench-replay` against the same saved
   artifact and assertion shape;
4. any matching same-shape emulator. If no generic emulator exists, add the
   smallest fixture that reproduces the failure class from saved artifacts;
5. one 10min step-shape proof for the target task with
   `selected_lane=implement_v2`, `--max-wall-seconds 600`, full artifact
   capture, and integration observation enabled when step comparison is the
   purpose.

The 10min step-shape proof is diagnostic, not scoring evidence. It asks whether
mew is entering the Codex-like active coding hot path before spending the full
speed budget:

- cheap source/binary/environment probes are front-loaded and preferably batched;
- first patch/edit appears early enough for the task class;
- the patch is coherent rather than many small whole-file rewrites;
- verification is external-verifier-shaped for path, cwd, lifecycle, and
  latency;
- prompt/projection weight is not dominating model turns;
- repeated same-frontier loops are visible and bounded.

If the 10min proof diverges from that shape, stop before live `speed_1`, record
the artifact and divergence, and repair the loop/hot-path first. Do not treat a
10min timeout or incomplete task as a score failure by itself.

Use `docs/DESIGN_2026-05-07_M6_24_INTEGRATION_OBSERVABILITY.md` as the repair
map after a step-shape miss. In particular, prefer the documented
post-observation tuning order: reduce model-visible proof/frontier weight,
strengthen cheap-probe -> coherent-patch -> verifier cadence, keep proof
objects in sidecars by default, and defer provider-native tools/cache until the
hot path is thinner.

This means `build-cython-ext` is currently a passing `speed_1` candidate, not a
reason to immediately rerun another `speed_1`. Its `proof_5` is deferred until
the rebaseline controller deliberately chooses close proof budget.

## Command Shape

Use the same Harbor wrapper as the passing `build-cython-ext` proof, with the
task-specific cwd from the task contract:

```text
harbor run -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/<task> -k 1 -n 1 -y \
  --agent-timeout-multiplier 2 \
  --job-name mew-m6-24-v2-rebaseline-<task>-speed1-<timestamp> \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-<task>-speed1-<timestamp> \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak command_cwd=<task-cwd> \
  --ak command_template='mew work --oneshot ... --work-guidance selected_lane=implement_v2 ...'
```

Do not count a run as v2 evidence unless the mew report/replay metadata records
`lane=implement_v2` (or the equivalent selected-lane action) and
`runtime_id=implement_v2_model_json_tool_loop`.

## Current V2 Rebaseline Table

| Task | Codex target | v2 speed_1 status | Evidence | Next |
|---|---:|---|---|---|
| `build-cython-ext` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-true-v2-build-cython-ext-speed1-20260506-0312-closeout` | proof_5 deferred until controller selects close proof |
| `circuit-fibsqrt` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-circuit-fibsqrt-speed1-20260506-0335` | proof_5 deferred until controller selects close proof |
| `cobol-modernization` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-cobol-modernization-speed1-20260506-0348` | proof_5 deferred until controller selects close proof |
| `distribution-search` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-distribution-search-speed1-20260506-0350` | proof_5 deferred until controller selects close proof |
| `feal-differential-cryptanalysis` | 5/5 | pass 1/1 after model-json repair | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair` | proof_5 deferred until controller selects close proof |
| `feal-linear-cryptanalysis` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426` | proof_5 deferred until controller selects close proof |
| `fix-git` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-fix-git-speed1-20260506-0435` | proof_5 deferred until controller selects close proof |
| `hf-model-inference` | 5/5 | pass 1/1 after Docker capacity retry | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-hf-model-inference-speed1-20260506-1030` | proof_5 deferred until controller selects close proof |
| `kv-store-grpc` | 4/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-kv-store-grpc-speed1-20260506-1050` | proof_5 deferred until controller selects close proof |
| `largest-eigenval` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-largest-eigenval-speed1-20260506-1053` | proof_5 deferred until controller selects close proof |
| `make-doom-for-mips` | 1/5 | recorded/deferred after 0/1 strategy-wall-budget frontier | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-finish-gate-prior-failure-make-doom-speed1-20260507-1217` | no same-shape rerun until a generic frontier-throttling or strategy design is selected and locally proven |
| `make-mips-interpreter` | 3/5 | blocked after 0/1 generic stdout/stderr expected-artifact contract gap | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1341-tool-contract-repair` | review/commit/pre-speed generic stream-contract repair, then rerun one same-shape v2 speed_1 |
| `merge-diff-arc-agi-task` | 5/5 | pending | none | run v2 speed_1 |
| `openssl-selfsigned-cert` | 5/5 | pending | none | run v2 speed_1 |
| `polyglot-c-py` | 5/5 | pending | none | run v2 speed_1 |
| `polyglot-rust-c` | 4/5 | pending | none | run v2 speed_1 |
| `prove-plus-comm` | 5/5 | pass 1/1 | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-true-implement-v2-prove-plus-comm-1attempt-20260506-0204` | proof_5 deferred until controller selects close proof |
| `pypi-server` | 5/5 | pending | none | run v2 speed_1 |
| `pytorch-model-cli` | 5/5 | pending | none | run v2 speed_1 |
| `pytorch-model-recovery` | 5/5 | pending | none | run v2 speed_1 |
| `raman-fitting` | 2/5 | pending | none | run v2 speed_1 |
| `regex-chess` | 5/5 | pending | none | run v2 speed_1 |
| `reshard-c4-data` | 5/5 | pending | none | run v2 speed_1 |
| `schemelike-metacircular-eval` | 5/5 | pending | none | run v2 speed_1 |
| `write-compressor` | 5/5 | pending | none | run v2 speed_1 |

## Repair Notes

- `feal-differential-cryptanalysis` first v2 attempt
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0359`
  scored `0.0` with runner errors `0` because `implement_v2` stopped on a
  first-turn `model_json_parse_error` and the saved report had no replayable
  v2 artifact. The generic repair makes JSON extraction accept the first valid
  object before trailing text, records model JSON failures as replayable v2
  lane failures, and lets terminal-bench replay/dogfood classify the historical
  miss as `repair model_json parse failure before another live speed run`.
  Focused UT, exact replay, and exact dogfood passed before the same-shape
  rerun.
- The same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-differential-cryptanalysis-speed1-20260506-0413-json-repair`
  scored reward `1.0` with runner errors `0`, total runtime `5m48s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=8`, `tool_calls=11`, `tool_results=11`,
  and external verifier `1/1` passing. Exact replay and matching
  terminal-bench replay dogfood passed.
- `feal-linear-cryptanalysis` live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-feal-linear-cryptanalysis-speed1-20260506-0426`
  scored reward `1.0` with runner errors `0`, total runtime `4m19s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=5`, `tool_calls=8`, `tool_results=8`,
  and external verifier `1/1` passing. Exact replay and matching
  terminal-bench replay dogfood passed.
- `fix-git` live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-fix-git-speed1-20260506-0435`
  scored reward `1.0` with runner errors `0`, total runtime `1m57s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=9`, `tool_calls=12`, `tool_results=12`,
  and external verifier `2/2` passing. Exact replay and matching
  terminal-bench replay dogfood passed.
- `hf-model-inference` first two v2 attempts were harness/infra-invalid before
  product scoring: Docker image extraction failed with `no space left on
  device`, first while pulling and then while registering the `libtriton.so`
  layer. After freeing host Docker capacity, the same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-hf-model-inference-speed1-20260506-1030`
  scored reward `1.0` with runner errors `0`, total runtime `5m25s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=7`, `tool_calls=7`, `tool_results=7`,
  and external verifier `4/4` passing. Exact replay and matching
  terminal-bench replay dogfood passed.
- `kv-store-grpc` live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-kv-store-grpc-speed1-20260506-1050`
  scored reward `1.0` with runner errors `0`, total runtime `2m27s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=4`, `tool_calls=11`, `tool_results=11`,
  and external verifier `7/7` passing. Exact replay and matching
  terminal-bench replay dogfood passed. The replay contains three recovered
  failed tool results before finish; they are not score blockers because final
  reward, replay, and dogfood are clean, but they remain efficiency evidence.
- `largest-eigenval` live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-largest-eigenval-speed1-20260506-1053`
  scored reward `1.0` with runner errors `0`, total runtime `7m11s`,
  `work_exit_code=0`, `stop_reason=finish`, `lane=implement_v2`,
  `runtime_id=implement_v2_model_json_tool_loop`, `provider=model_json`,
  `replay_valid=true`, `model_turns=10`, `tool_calls=20`,
  `tool_results=20`, and external verifier `27/27` passing. Exact replay and
  matching terminal-bench replay dogfood passed. The replay contains six
  recovered failed tool results before finish; they are not score blockers
  because final reward, replay, and dogfood are clean, but they remain
  efficiency evidence.
- `make-doom-for-mips` first live v2 speed_1
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1102`
  scored reward `0.0` with runner errors `0` because `implement_v2` falsely
  completed after generating a small self-smoke BMP artifact instead of
  satisfying the hidden stdout and frame-quality contract. The generic replay
  repair classifies `completed` plus external reward `0.0` as
  `debug implement_v2 divergence`, and terminal-bench replay dogfood can
  reproduce the saved artifact.
- The finish-gate repair made completed finish actions pass through
  `acceptance_done_gate_decision`, including finish-only turns, and grounds
  finish evidence refs without accepting ambiguous alpha or numeric provider
  ids. The same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1144-finish-gate`
  still scored reward `0.0`: the gate blocked three weak finishes but
  eventually allowed a valid-BMP/header-only proof. The external verifier
  expected the Doom screen stdout and a reference-similar `640x400` frame, but
  mew produced a synthetic `2x2` BMP. Exact replay and matching dogfood pass
  and classify this as finish-gate divergence.
- The follow-up visual-quality repair treats task contracts that require
  artifacts to be printed or written "appropriately" as requiring grounded
  runtime visual/stdout quality evidence, not just file existence or image
  header validity. Focused acceptance, implement-lane, and terminal-bench
  replay tests passed; scoped ruff and `git diff --check` passed; codex-ultra
  reviewer session `019dfb1a-5815-7f62-9669-cff64ea61fbc` approved.
- The post-repair rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1158-visual-quality-gate`
  is inconclusive product evidence. It scored reward `0.0` with runner errors
  `0`, but `mew_exit_code=1`, `stop_reason=implement_v2_blocked`, and
  `finish.outcome=failed` because the Codex Web API returned
  `IncompleteRead(101768 bytes read)` after three model turns. Exact replay
  passes and matching terminal-bench replay dogfood passes with next action
  `inspect model backend failure before another live speed run`. Since no
  false completion occurred and the model backend failed before a finish
  attempt, rerun exactly one same-shape `make-doom-for-mips` v2 `speed_1`
  before classifying the remaining product gap.
- The post-commit same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1214-post-commit`
  scored reward `0.0` with runner errors `0` and total runtime `8m21s`, but
  `implement_v2` ended `blocked` with `completion_credit=false` and
  `finish_gate_block_count=3`. The gate no longer grants false completion.
  The remaining issue is a hard-runtime strategy/profile gap: v2 inspected the
  provided Doom/VM source, then generated a handcrafted MIPS ELF and synthetic
  frame producer instead of preserving the source-provided implementation
  path. The next repair is a generic cacheable `implement_v2_hard_runtime_profile`
  prompt section for provided-source plus VM/emulator/binary/runtime-artifact
  tasks. Focused tests, replay/dogfood on the 1214 artifact, scoped ruff,
  JSONL validation, and codex-ultra review session
  `019dfb51-9ee5-7400-b46f-e07737e056a3` passed. Commit the profile repair,
  then run exactly one same-shape live speed_1.
- The hard-runtime-profile rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1231-hard-runtime-profile`
  scored reward `0.0` with runner errors `0` and total runtime `3m42s`. The
  prompt metrics confirm `implement_v2_hard_runtime_profile` was present. The
  prior handcrafted surrogate path did not recur; v2 inspected the source,
  checked and installed MIPS cross compilers, then stopped on
  `model_backend_error: response did not contain assistant text` before a final
  artifact. Replay and dogfood pass and classify the artifact as model backend
  failure. Since `recoverable_work_model_error` already treats this marker as
  recoverable but `agent.call_model_json_with_retries` did not, the next repair
  is to add empty assistant-text markers to the shared transient model retry
  detector and rerun one same-shape speed_1 after focused validation. Focused
  retry tests, replay/dogfood on the 1231 artifact, scoped ruff, JSONL
  validation, and codex-ultra review session
  `019dfb5d-dc7f-7a52-989b-c440fe6fc27c` passed.
- The empty-assistant-retry rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1243-empty-assistant-retry`
  scored reward `0.0` with runner errors `0` and total runtime `15m47s`.
  This is progress, not a provider-error repeat: the run preserved the
  provided source path, reached `model_turns=24`, `tool_calls=36`,
  `tool_results=36`, attempted the MIPS build, and blocked after the latest
  terminal command failed with `m_misc.c:82:25: error: 'EISDIR' undeclared`.
  Replay previously misclassified the top-level
  `implement_v2 reached max_turns before finish` as `model_backend_error`,
  which hid the actionable terminal frontier. The current measurement repair
  classifies it as `max_turns_before_finish` / `ImplementV2LoopLimit`,
  preserves active-command closeout as a more specific diagnosis, and makes the
  next action point to the latest failed terminal result rather than a later
  non-terminal tool failure.
- The follow-up bounded reaction-turn repair lets `implement_v2` spend a small
  extra turn only when the configured turn budget is exhausted on a latest
  terminal tool failure and wall budget remains. It also closes out yielded
  terminal commands at the budget boundary before reaction classification,
  preserves accumulated closeout metrics, keeps deterministic finish-gate
  evaluation on pre-closeout provider-visible results, and prevents
  `finish.completed` from bypassing a final terminal failure. Validation
  passed: full `tests/test_implement_lane.py` (`88 passed`), focused
  terminal-bench replay/dogfood suite (`18 passed, 108 deselected`), exact
  replay/dogfood on the 1243 artifact, scoped ruff, and `git diff --check`.
  codex-ultra reviewer session `019dfb88-3c9e-7261-bc6a-01b8e993a874`
  requested the closeout/finish edge-case regressions and then approved. After
  commit, `m6_24-implement-v2-terminal-failure-reaction-emulator` was added as
  the selected gap emulator. It reproduces the final yielded command closeout
  failure plus one bounded reaction turn without Harbor. Scoped ruff, focused
  dogfood tests, the real emulator scenario, and codex-ultra review session
  `019dfb9a-6778-7532-9a21-109841f65c28` passed. After committing the emulator
  support, spend exactly one same-shape `implement_v2` speed_1.
- The provider-history-compaction rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1420-history-compaction`
  scored reward `0.0` with runner errors `0` and total runtime `12m16s`. This
  is valid product evidence, not a backend transport miss: v2 ran
  `model_turns=27`, `tool_calls=52`, and `tool_results=52`, preserved the
  source-backed MIPS build path, and stopped with
  `max_turns_before_finish` after a final terminal failure. Replay and
  terminal-bench dogfood pass, but the replay could not expose the actionable
  compiler/linker tail because managed command terminal results only populated
  `stdout_tail` / `stderr_tail` on timeout. The generic repair makes managed
  command results preserve stdout/stderr tails for all terminal outcomes, so
  future replay/dogfood can classify failed build frontiers without another
  live proof. Focused implement-lane and terminal-bench replay tests passed.
- The terminal-tail evidence rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-1453-terminal-tail`
  scored reward `0.0` with runner errors `0` and total runtime `8m14s`.
  Replay/dogfood now exposes the latest failed terminal result
  (`/bin/bash: line 6: file: command not found`), confirming the terminal-tail
  repair worked. The remaining blocker is another `Codex Web API error:
  IncompleteRead(3132767 bytes read)` after only `model_turns=7`,
  `tool_calls=21`, and `prompt_chars_total=379894`. The generic repair projects
  terminal `run_command`/`run_tests`/`poll_command`/`cancel_command` results in
  next-turn provider history to lifecycle metadata, bounded tails, and
  `output_ref`; full stdout/stderr remain in proof artifacts and can be
  intentionally fetched with `read_command_output`. codex-ultra initially
  requested preserving non-output diagnostics such as `reason` / `error` /
  `failure_class`; the fix added those fields and a regression, then
  codex-ultra review session `019dfbe8-f49c-7341-b9bc-1e0c04975c19`
  approved. This is a generic provider-history projection repair, not a
  Doom/MIPS solver.
- The reference-compare rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare`
  scored reward `0.0` with runner errors `0` and total runtime `11m34s`.
  It used true `implement_v2` (`runtime_id=implement_v2_model_json_tool_loop`),
  preserved the source-backed MIPS/Doom path, and reached build/link repairs.
  The final blocker was generic tool-contract selection: the model sent a
  multi-line shell verifier to `run_tests`, but `run_tests` is argv-only and
  instructed it to use `run_command` for shell orchestration. Codex and
  Claude Code reference traces for the same task are captured in
  `docs/M6_24_REFERENCE_TRACE_MAKE_DOOM_FOR_MIPS_2026-05-06.md`.
- The tool-contract replay repair makes current-head replay classify both
  structured and legacy reason-only `run_tests` shell-surface failures as the
  same recoverable tool-contract gap. It also fixed the hard-runtime frontier
  compactor's numeric type check so the tool-contract recovery emulator runs
  under the current Python runtime. Focused UT, exact replay with a
  `recover run_tests shell-surface verifier through run_command` assertion,
  terminal-bench replay dogfood, both selected emulators, scoped ruff,
  `git diff --check`, and codex-ultra review session
  `019dfc7a-2c56-7d91-a1f4-0562b4ad801d` passed. After this commit, run one
  same-shape `make-doom-for-mips` `implement_v2` speed_1.
- The first post-repair speed
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-175436-tool-contract-recovery`
  scored reward `0.0` with runner errors `0`, but this was classified as a
  provider/backend miss: the lane stopped after `model_turns=2` because the
  Codex response did not contain assistant text. Replay exposed
  `model_backend_error`, so this was not counted as product/lane evidence and
  one same-shape rerun was allowed without source changes.
- The provider rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-175853-provider-rerun`
  scored reward `0.0` with runner errors `0` and total runtime `29m04s`.
  This is valid product evidence. The v2 lane reached a source-backed MIPS ELF
  at `/app/doomgeneric_mips`, but `node vm.js` failed with
  `Execution error at PC=0x4002e8: Unknown opcode: 0x10` and no
  `/tmp/frame.bmp`. The generic failure shape is runtime artifact contract
  mismatch: the generated binary/runtime artifact and the VM/emulator loader
  contract were not reconciled before another build/finish. The repair is not a
  Doom/MIPS recipe. It classifies `Unknown opcode` / illegal-instruction style
  VM failures with ELF/ABI/endianness/loader evidence as
  `runtime_artifact_contract_mismatch`, adds a hard-runtime profile reminder to
  compare artifact ABI/ISA/endianness/entrypoint against the runtime loader
  contract, and routes replay/dogfood to the required next probe. Focused
  implement-lane tests, terminal-bench replay tests, exact replay on the
  provider-rerun artifact with `artifact ABI/ISA/endianness/entrypoint`,
  terminal-bench replay dogfood, scoped ruff, and `git diff --check` passed.
  codex-ultra review session `019dfceb-60ea-7572-b469-4f063dcbe111`
  first requested compaction, stale-failure, and command-text-only negative
  regressions; after those were added, it approved.
  After this repair, run one same-shape `make-doom-for-mips` `implement_v2`
  speed_1.
- The same-shape post-repair speed
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-200527-runtime-artifact-contract`
  scored reward `0.0` with runner errors `0` and total runtime `19m45s`.
  Replay and terminal-bench dogfood pass. The lane no longer stops at the
  previous ABI/endianness mismatch: it built a source-backed MIPS ELF, patched
  `vm.js` through JALR decode, and reached a later VM execution gap. The latest
  failed terminal result is `node vm.js` timing out with `VM_RC=124` and no
  `/tmp/frame.bmp`; the external verifier also failed frame existence and
  similarity. A replay instrumentation bug initially routed this to `model
  backend failure` because the product summary contained the words "timed out".
  The repair is generic: only explicit backend/parse/loop-limit markers are
  treated as model errors, and hard-runtime replay routes product terminal
  failures to the latest failed terminal result. Focused replay tests, exact
  replay with `latest failed run_command result`, terminal-bench replay
  dogfood, scoped ruff, `git diff --check`, and codex-ultra review session
  `019dfd0d-23ca-7d20-a92f-489e1c2a0a25` passed. Next repair should use the
  latest terminal failure as product evidence, not rerun live speed or chase
  provider transport.
- Follow-up frontier repair: the same artifact showed the final compound
  command's observed `VM_RC=124` timeout was stored as `latest_build_failure`
  because the command text included rebuild steps. Current-head classification
  now treats observed VM/emulator timeout markers such as `VM_RC=124` as
  `latest_runtime_failure` with `failure_class=runtime_execution_timeout`, even
  when the compound command also contains build/link text. This keeps the next
  model turn on runtime progress and artifact production rather than another
  generic rebuild loop. Focused implement-lane tests, scoped ruff, and
  `git diff --check` passed; codex-ultra review session
  `019dfd13-6160-72b3-871e-fae47d4c99bb` approved.
- The VM-timeout-frontier rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-204057-vm-timeout-frontier`
  scored reward `0.0` with runner errors `0` and total runtime `14m23s`.
  Replay and terminal-bench dogfood pass. The lane reached a source-backed
  MIPS ELF, repaired past the previous VM timeout, and executed a final fresh
  verifier, but `node vm.js` terminated at `PC=0x0` after `9` instructions and
  did not create `/tmp/frame.bmp`. The run then spent its final base turn on a
  successful diagnostic command and stopped at `max_turns_before_finish` with
  `terminal_failure_reaction_turns_used=0`. The generic gap is not Doom/MIPS:
  `implement_v2` only extended reaction turns when the final base turn itself
  produced a terminal failure, not when an unresolved prior terminal failure
  was followed by final diagnostic evidence. The bounded repair lets the lane
  spend one terminal-failure reaction turn from accumulated tool evidence when
  the base budget expires with a prior terminal failure still actionable.
  Focused implement-lane tests, focused dogfood tests, exact replay on the
  artifact, matching terminal-bench dogfood, the new
  `m6_24-implement-v2-prior-terminal-failure-diagnostic-emulator`, scoped
  ruff, and `git diff --check` must pass before the next same-shape live
  speed_1.
- The post-reaction-rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-2109-prior-terminal-reaction`
  scored reward `0.0` with runner errors `0` and total runtime `21m59s`.
  This confirms the prior repair changed behavior: the lane used all three
  bounded terminal-failure reaction turns (`turn_budget_limit=27`,
  `terminal_failure_reaction_turns_used=3`) instead of stopping at the base
  `24` turns. The new blocker is replay integrity, not the same reaction gap:
  the model reused `provider_call_id=read-img-backend` on turn `20` after an
  earlier turn `2` read, so the artifact recorded
  `replay_valid=false` with `duplicate_provider_call_id` /
  `duplicate_result_for_provider_call_id`. The generic repair keeps provider-id
  reuse side-effect safe by rejecting the tool call as invalid, but assigns a
  deterministic internal provider id to the rejected call so future proof
  manifests remain pairable and replay/dogfood can classify the subsequent
  terminal failure. This is a provider-tool-loop robustness repair, not a
  Doom/MIPS rule.
- The provider-id-replay rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-2143-provider-id-replay`
  scored reward `0.0` with runner errors `0` and total runtime `19m09s`.
  Replay and terminal-bench dogfood pass; `replay_valid=true` and the bounded
  terminal-failure reaction path used all three extra turns. The new gap is
  frontier classification: the final compound command rebuilt and linked, then
  executed the VM verifier, but the VM returned `vm_rc=0`, terminated at
  `PC=0x0` after `9` instructions, and produced `NO_FRAME`. Because the
  command also contained build/link text and warnings, the frontier stored this
  as `latest_build_failure`. Current-head classification treats observed
  VM/emulator runtime termination evidence plus missing-output-artifact markers
  as `latest_runtime_failure` with
  `failure_class=runtime_artifact_missing`, even when build/link output is
  present. This is a generic observed-evidence repair: the next model turn
  should inspect runtime progress and artifact production, not repeat a broad
  rebuild loop. Focused frontier tests, the negative build-artifact-missing
  boundary, exact replay/dogfood on the artifact, full implement/replay/dogfood
  suite, scoped ruff, `git diff --check`, and codex-ultra review session
  `019dfd67-ebb8-7f22-8f08-93c6ce5f9130` passed.
- The expected-artifact contract repair Phase 1-6 was implemented and reviewed
  through codex-ultra session `019dfe1f-c6e2-79b1-85ed-faff0d3b08bc`. Phase 7
  pre-speed passed: focused schema/classifier/checker UT (`300 passed, 6
  subtests passed`), exact replay on the latest replayable `make-doom-for-mips`
  artifact (`2143-provider-id-replay`), matching terminal-bench replay dogfood,
  the new `m6_24-expected-artifact-contract-emulator`, scoped ruff, and
  `git diff --check`.
- The Phase 7 same-shape live speed
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-expected-artifact-contract-make-doom-speed1-20260507-013823`
  scored reward `0.0` with runner errors `0` and total runtime `13m11s`.
  This is valid product evidence, not a harness/provider miss:
  `selected_lane=implement_v2`, `runtime_id=implement_v2_model_json_tool_loop`,
  `mew_exit_code=1`, `stop_reason=implement_v2_blocked`, `model_turns=26`,
  `tool_calls=57`, `tool_results=57`, and
  `terminal_failure_reaction_turns_used=2`. Replay and terminal-bench dogfood
  pass, and the structured replay recomputes `26` classification records with
  `mismatch_count=0`.
- The new failure is no longer "missing evidence". The final structured command
  declared `/tmp/frame.bmp`, checked it after a source-backed MIPS build plus
  fresh `node vm.js`, and correctly recorded missing artifact evidence:
  `VM_RC=0`, `Program terminated at PC=0x0`, `Executed 34 instructions`,
  `BMP_MISSING`, and `VM_STDOUT_MARKER_MISSING`. The immediate product gap is
  actual runtime/artifact production in the task-solving strategy.
- There is one measurement follow-up before another live speed: the model
  declared `role=generated_artifact` / `proof_role=final_verifier`, but the
  normalizer projected this to `role=unknown`, `proof_role=none`, and
  `acceptance_kind=not_acceptance`. As a result the latest structured class is
  `artifact_validation_failure` with `phase=unknown` instead of a more precise
  runtime-artifact class. Do not add task-specific Doom logic; repair or record
  this as a generic contract-role vocabulary/normalization gap if the next
  repair depends on phase-specific routing.
- Post-repair update on 2026-05-07 JST: the vocabulary normalization gap is
  repaired generically. `execution_contract` now tolerates near-miss model
  vocabulary such as `generated_artifact`, `final_verifier`, and
  `artifact_and_runtime_verification` by projecting it back to the v3 contract
  vocabulary without expanding the enum set. Replay also prefers raw contract
  fields over stale stored normalized fields when recomputing historical
  artifacts. The same historical job now replays as latest
  `runtime_artifact_missing` / `phase=runtime` with an expected
  `structured_replay_mismatch_count=7` because old stored classifications were
  less specific. This is a replay semantics repair, not a new live proof.
- Post-repair update on 2026-05-07 JST: hard-runtime frontier state now follows
  the same structured blocking-artifact evidence. For verifier-like execution
  contracts with multiple expected artifacts, `lane_hard_runtime_frontier` no
  longer chooses the first expected artifact such as a log file; it prefers the
  failed/blocking `artifact_evidence` that caused the terminal verdict. On the
  Phase 7 `make-doom-for-mips` artifact, the frontier therefore points at
  `/tmp/frame.bmp` and drops stale broad build failure state when the latest
  terminal failure is runtime-artifact missing. This is a generic reentry/state
  repair so the next model turn investigates runtime artifact production
  instead of another broad rebuild or log-proof path.
- Pre-speed instrumentation update on 2026-05-07 JST: terminal-bench replay
  dogfood now accepts the same structured replay assertions as the replay CLI:
  latest structured failure class and expected structured mismatch count. This
  lets dogfood validate historical artifacts after intentional classifier or
  normalizer upgrades without requiring old stored classifications to match the
  current recomputation exactly. On the Phase 7 artifact, the dogfood command
  passes with `runtime_artifact_missing` and `structured_replay_mismatch_count=7`.
- The runtime-frontier blocking-artifact repair rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-frontier-make-doom-speed1-20260507-0838`
  is harness-valid and scored reward `0.0` with runner errors `0`, total
  runtime `15m22s`, `work_exit_code=1`, `stop_reason=implement_v2_blocked`,
  `selected_lane=implement_v2`, `runtime_id=implement_v2_model_json_tool_loop`,
  `model_turns=27`, `tool_calls=53`, `tool_results=53`, and
  `terminal_failure_reaction_turns_used=3`. It is progress but still not a
  pass: v2 preserved the source-backed build path, produced
  `/app/doomgeneric_mips`, then the final VM verifier stopped at `PC=0x0`,
  executed 8 instructions, and did not produce `/tmp/frame.bmp`. Exact replay
  and matching terminal-bench dogfood pass after fixing a host Python 3.9 replay
  compatibility bug in `normalize_execution_contract`. The latest structured
  failure is `runtime_artifact_missing` with mismatch count `0`; no another
  live speed should be spent until the next generic repair has local
  UT/replay/dogfood/emulator coverage.
- Post-classification repair on 2026-05-07 JST: `implement_v2` now treats
  hard-runtime/frontier tasks as a bounded continuation gate instead of using
  the normal small terminal-failure reaction budget. The default expansion is
  generic and capped: it requires hard-runtime task markers or persisted
  active/blocked `lane_hard_runtime_frontier`, sufficient wall budget, and still
  excludes tool-contract misuse. The prompt now explicitly tells reaction turns
  to continue from `lane_hard_runtime_frontier`, inspect the producing
  substep/artifact path, make the smallest source/runtime repair, and then run a
  verifier-shaped command. Local validation passed with focused UT, the
  hard-runtime reaction-budget emulator, exact replay dogfood on the `0838`
  artifact, scoped ruff, and `git diff --check`. Next action is current-head
  pre-speed, then exactly one same-shape `make-doom-for-mips`
  `selected_lane=implement_v2` speed_1 if green.
- Same-shape speed update on 2026-05-07 JST: the post-continuation-gate rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-runtime-continuation-make-doom-speed1-20260507-0948`
  scored reward `0.0` with runner errors `0` and total runtime `18m57s`.
  This was not a regression: v2 advanced from the previous `PC=0x0` / 8
  instruction frontier to a source-backed Doom runtime that reached
  `PC=0x40c848` after `4,634,462` instructions, but still failed to produce
  `/tmp/frame.bmp`. Exact replay and terminal-bench replay dogfood pass with
  latest structured failure `runtime_artifact_missing` and mismatch count `0`.
  The next repair is a generic progress-sensitive continuation credit: after
  the normal hard-runtime reaction budget is exhausted, grant a small bounded
  extra credit only when the frontier signature has demonstrably changed
  (for example a new runtime artifact failure signature with fresh runtime
  stdout/stderr evidence) and wall budget remains. It must not globally raise
  max turns or add Doom/MIPS rules.
- Progress-continuation repair on 2026-05-07 JST: `implement_v2` now tracks
  hard-runtime frontier progress signatures and can grant up to four additional
  configured/default continuation credits only after the base hard-runtime
  reaction budget is exhausted and a new actionable runtime frontier signature
  appears. Identical runtime-artifact misses are not eligible. Local validation
  passed with focused UT, full `tests/test_implement_lane.py` +
  `tests/test_dogfood.py`, the new
  `m6_24-implement-v2-hard-runtime-progress-continuation-emulator`, exact
  `0948` replay, exact `0948` terminal-bench replay dogfood, scoped ruff, and
  `git diff --check`. codex-ultra review session
  `019e000e-15b5-71c0-b3bb-fb0861076cec` approved with no findings. Next
  action after commit is current-head pre-speed, then exactly one same-shape
  `make-doom-for-mips selected_lane=implement_v2` speed_1 if green.
- Same-shape speed update on 2026-05-07 JST: the post-progress-continuation
  run
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-runtime-progress-continuation-make-doom-speed1-20260507-1040`
  scored reward `0.0` with runner errors `0` and total runtime `30m09s`.
  This remains valid product evidence: v2 preserved the source-backed MIPS
  path, built `/app/doomgeneric_mips`, reached repeated runtime/artifact
  failures, and made source repairs. It then stopped at `model_turns=32` with
  `terminal_failure_reaction_turns_used=8/8` and
  `hard_runtime_progress_continuation_turns_used=0/4`. Replay and dogfood
  reproduce the artifact with latest failure `artifact_validation_failure` /
  `missing_artifact` / `phase=unknown`: a structured verifier-like command
  declared blocking final artifacts, but the progress signature gate only
  accepted runtime-named failure classes. The repair is generic: structured
  artifact-validation failures for blocking failed hard-runtime final artifacts
  now count as actionable frontier progress. It does not add a Doom/MIPS rule,
  and build-phase, partial, stale, or nonblocking artifact-validation failures
  still do not qualify. codex-ultra review session
  `019e003c-a93d-73d1-bab0-84d74dbd1940` requested the narrower boundary and
  then approved the updated predicate, tests, and docs.
- Same-shape speed update on 2026-05-07 JST: the post-artifact-validation
  progress-signature rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-validation-progress-make-doom-speed1-20260507-1136`
  scored reward `0.0` with runner errors `0` and total runtime `17m41s`.
  Exact replay and terminal-bench replay dogfood pass with latest structured
  failure `runtime_artifact_missing`, mismatch count `0`, and next action
  containing `expected runtime artifact`. The run spent one terminal-reaction
  turn and reached a verifier-like command that produced `/tmp/frame.bmp`, but
  the frame was `320x200` and externally failed the reference `640x400`
  visual contract. The lane then attempted to finish after a read-only source
  grounding step; the deterministic finish gate correctly blocked completion,
  but because the current turn was read-only it did not spend an available
  reaction turn on the unresolved prior runtime failure. The next repair is
  generic: when finish gate blocks completion at the turn boundary and the
  current turn has no terminal failure, allow the existing terminal-failure
  reaction path to consider unresolved prior terminal/runtime failures. This
  is not a Doom/MIPS solver and does not change acceptance requirements.
- Review follow-up on 2026-05-07 JST: the same bounded prior-failure reaction
  must cover finish-only / no-tool-call completion attempts as well as
  read-only-current-turn attempts. When a finish-gate block grants an extra
  reaction turn, the runtime must append finish-gate history before continuing
  so the next prompt sees the deterministic blocker that caused the turn.
  Focused UT, full `tests/test_implement_lane.py`, exact replay/dogfood,
  scoped ruff, JSONL validation, and `git diff --check` passed; codex-ultra
  review session `019e0064-c09c-79d3-9009-aa771e495048` approved with no
  findings. Next action is current-head pre-speed and then exactly one
  same-shape `make-doom-for-mips selected_lane=implement_v2` speed_1.
- Same-shape speed update on 2026-05-07 JST: the post-finish-gate-prior-failure
  rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-finish-gate-prior-failure-make-doom-speed1-20260507-1217`
  scored reward `0.0` with runner errors `0` and total runtime `30m46s`.
  Replay and dogfood reproduce the miss with latest failure
  `artifact_validation_failure` / `missing_artifact` for `/tmp/frame.bmp`,
  `model_turns=30`, and `max_turns_before_finish`. codex-ultra classified this
  as `RECORD_AND_DEFER`: a task-strategy + wall-budget limited runtime-artifact
  frontier, not a local loop-boundary bug. Do not run another same-shape
  make-doom speed proof until a generic frontier-throttling or strategy design
  is selected and proven with local replay/dogfood/emulator first.
- `make-mips-interpreter` true-v2 scoped rebaseline attempt on 2026-05-07 JST:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1306`
  scored reward `0.0` with runner errors `0`, total runtime `9m06s`,
  `work_exit_code=1`, `stop_reason=implement_v2_blocked`,
  `lane=implement_v2`, and `runtime_id=implement_v2_model_json_tool_loop`.
  The external verifier failed all three checks because `/tmp/frame.bmp` was
  missing. Replay and terminal-bench replay dogfood reproduce the artifact and
  show the generic blocker before the backend error:
  `search_text` used a lone `pattern` argument as the search term and failed,
  then no-contract diagnostic `run_command` calls inherited final-artifact
  checks and failed with `artifact artifact has no path target`; the run later
  stopped on `Codex Web API error: IncompleteRead(756949 bytes read)`.
  The repair is generic to the implement_v2 tool loop: read-only search treats
  a lone `pattern` as the query, no-contract diagnostic exec calls no longer
  inherit task final-artifact checks, and same-turn final-artifact inference is
  still preserved when one no-contract exec/verifier is accompanied by
  read-only evidence. Focused UT, full `tests/test_implement_lane.py`, exact
  replay, terminal-bench replay dogfood, both matching dogfood emulators,
  scoped ruff, and codex-ultra review session
  `019e00ae-d36c-7ff1-b485-3e79f875a0da` passed. After commit, run
  current-head pre-speed and then exactly one same-shape
  `make-mips-interpreter selected_lane=implement_v2` speed_1 if green.
- The post-repair same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1341-tool-contract-repair`
  scored reward `0.0` with runner errors `0` and total runtime `4m41s`.
  This run moved past the prior no-contract diagnostic inheritance bug, but
  exposed another generic expected-artifact contract normalization gap:
  explicit `target: "stdout"` / `stream: "stdout"` model-declared artifacts
  were previously treated as path artifacts with no path, and check aliases
  such as `{"kind": "text_contains", "value": "ELF"}` were projected as
  default `exists` checks. The repair normalizes stdout/stderr artifact targets
  to stream targets, preserves path artifacts, and maps `kind`/`value` check
  aliases to the `artifact_checks` schema. Focused UT, full related
  implement-lane/execution-evidence/artifact-check/replay tests, exact 1341
  replay, exact 1341 terminal-bench replay dogfood, the updated
  expected-artifact emulator with a stdout stream proof, scoped ruff, and JSONL
  validation passed. codex-ultra review session
  `019e00cb-238f-74f0-ad24-df9053cadac4` approved with no blocking findings;
  the non-blocking `stream: "stdout"` checker suggestion was added. After
  commit, run current-head pre-speed and then exactly one same-shape
  `make-mips-interpreter selected_lane=implement_v2` speed_1 if green.
- The next same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1409-stream-contract`
  scored reward `0.0` with runner errors `0` and total runtime `17m40s`.
  It moved past the stdout stream-contract friction and reached a fresh final
  structured verifier that passed internally, but the model then repeated
  finish attempts without explicit `acceptance_evidence`. The external
  verifier still failed because hidden tests expected `/tmp/frame.bmp` while
  internal proof had produced `/app/frame000000.bmp` and
  `/app/frames/frame000000.bmp`. The repair is generic: preserve structured
  `artifact_evidence` / `verifier_evidence` in the finish-gate projection,
  synthesize a finish acceptance check from the latest passed structured final
  verifier when the model omits evidence, do not promote verifier scratch
  transcripts such as `/tmp/vmout.txt` to runtime output obligations, and make
  replay extract `/tmp/...` expected artifact paths from external verifier
  stdout/CTRf. Exact `1409` replay and terminal-bench replay dogfood now pass
  with `next_action` containing `/tmp/frame.bmp`; the new
  `m6_24-external-artifact-mismatch-emulator` dogfood scenario covers the
  hidden-path feedback shape. codex-ultra review session
  `019e0101-7b3f-7ff1-bff2-c95451f77478` requested tightening empty
  `acceptance_checks`, final-verifier contract shape, and failed-result
  artifact suppression; after those follow-ups it approved with no findings.
  After commit, run current-head pre-speed and then exactly one same-shape
  `make-mips-interpreter selected_lane=implement_v2` speed_1 if green.
- The post-repair same-shape rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-mips-interpreter-speed1-20260507-1511-external-artifact-feedback`
  scored reward `0.0` with runner errors `0` and total runtime `21m18s`.
  This is valid product evidence, not a harness miss. Replay and terminal-bench
  replay dogfood both pass. The run moved past the previous internal/external
  artifact projection mismatch and into real runtime task-solving: v2 wrote and
  edited `vm.js`, probed syscall behavior, tried WAD/frame-path repairs, and
  stopped blocked on structured `runtime_artifact_missing`. The latest failed
  verifier-shaped command required `/app/frame0.bmp`, exited nonzero, and stdout
  shows Doom initialization followed by `-iwad not specified`, `Trying IWAD
  file:doom2.wad`, and `vm_status=1`. The external verifier still expected
  `/tmp/frame.bmp` and failed `3/3` tests. Measurement caveat: the Harbor run
  omitted `--ak timeout_seconds=1800` and command-template
  `{max_wall_seconds_option}`, so `mew_max_wall_seconds=null` and the
  hard-runtime continuation gate was disabled. Treat the runtime-producer
  classification as product evidence, but do not use this run to judge
  continuation budgeting. This exposes a higher-level hard-runtime
  repair-history gap: prior M6.24 evidence for this same task had a successful
  MIPS `SPECIAL3` `EXT` / `INS` repair, but this v2 run had empty active memory
  and re-explored syscall/WAD/frame-path hypotheses. Active dossier:
  `docs/M6_24_DOSSIER_HARD_RUNTIME_ARTIFACT.md`. Do not spend another
  same-shape speed until the latest artifact is replayed/dogfooded and the next
  generic repair has UT/replay/dogfood/emulator proof. Any same-shape rerun must
  use the documented `timeout_seconds` plus `{max_wall_seconds_option}` command
  shape.

## Repair Trigger

Pause the rebaseline and repair immediately when any of these happens:

- `speed_1` reward is `0.0` on a task where the harness launched mew correctly.
- Harbor runner error is nonzero or the mew report is missing.
- The task is harness-invalid and the invalidity is in mew's wrapper,
  task-cwd selection, auth mount, or artifact layout.
- Replay or dogfood cannot express the failure shape.
- The run exposes an implementation-lane structural gap, such as tool surface,
  managed exec lifecycle, finish gate, acceptance evidence, context/reentry, or
  repair-loop behavior.

Do not continue measuring unrelated tasks through a known structural lane gap.
That would collect more low-quality evidence instead of improving mew.

## Close Rule

A task is "v2 rebaseline measured" after a clean `speed_1` with replayable
artifacts. A task is "v2 close-candidate passed" only after the relevant
`proof_5` or documented lower-cost close gate.

M6.24 as a milestone can only close when:

- all 25 scoped tasks have `implement_v2` evidence,
- below-target tasks have classified repair routes or explicit deferrals,
- close candidates are validated against the frozen Codex target shape, and
- no accepted structural lane blocker remains open.
