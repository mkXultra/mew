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
| `make-doom-for-mips` | 1/5 | current-head miss after reference compare | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare` | repair generic final tool-contract selection gap, then replay/dogfood/emulator before one same-shape v2 speed_1 |
| `make-mips-interpreter` | 3/5 | pending | none | run v2 speed_1 |
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
