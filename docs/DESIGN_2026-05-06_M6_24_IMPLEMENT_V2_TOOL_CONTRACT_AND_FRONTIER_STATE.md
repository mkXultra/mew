# Design 2026-05-06 - M6.24 Implement V2 Tool Contract and Frontier State

Status: design only.

Scope: `implement_v2` only. This document does not authorize source changes by
itself and does not propose changes to `implement_v1`, other lanes,
Terminal-Bench-only wrappers, or global CLI behavior except for replay/dogfood
classification surfaces that consume `implement_v2` artifacts.

## Inputs Reviewed

- `docs/M6_24_REFERENCE_TRACE_MAKE_DOOM_FOR_MIPS_2026-05-06.md`
- `docs/REVIEW_2026-05-06_M6_24_CODEX_MAKE_DOOM_STEP_DESIGN.md`
- `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`
- `docs/DESIGN_2026-05-05_M6_23_2_IMPLEMENT_V2_NATIVE_TOOL_LOOP.md`
- `docs/DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md`
- `docs/DESIGN_2026-05-03_M6_24_GENERIC_MANAGED_EXEC.md`
- Current `implement_v2` source around:
  - `src/mew/implement_lane/exec_runtime.py`
  - `src/mew/implement_lane/prompt.py`
  - `src/mew/implement_lane/tool_policy.py`
  - `src/mew/implement_lane/types.py`
  - `src/mew/implement_lane/v2_runtime.py`
  - `src/mew/terminal_bench_replay.py`
  - `src/mew/dogfood.py`
  - `tests/test_implement_lane.py`

The make-doom trace and Codex step-design report are reference evidence, not a
task-specific recipe. The import target is the generic step shape: cheap
source/runtime preflight, toolchain probe before heavy edits, source-preserving
repair, tight build/run/failure-inspect/patch loop, exact final artifact proof,
and wrong-tool recovery.

## Problem

The current `implement_v2` run reached the source-backed MIPS build/link
frontier, then spent the final useful verifier action on a tool-contract error:
the model sent a multi-line shell verifier to argv-only `run_tests`.
`run_tests` correctly rejected it with:

```text
run_tests executes one argv command without a shell; use run_command for shell orchestration
```

The rejection protects the tool contract, but near a timed hard-runtime
frontier it should not discard a high-confidence final verifier command whose
intended execution surface is clear and safe.

A secondary gap is repeated rediscovery. Once `implement_v2` has identified the
provided source, runtime harness, build target, final verifier artifact, and
latest build/runtime failure, that compact frontier should be carried in v2
state instead of being re-learned from broad searches and long terminal tails.

## Decision

Add two v2-local mechanisms:

1. Deterministic `run_tests` shell-surface recovery:
   - If `run_tests` receives a shell-shaped command and `run_command` is allowed
     for this v2 attempt, route the same command through managed `run_command`
     with shell execution.
   - If routing is not allowed, return a structured tool-contract failure that
     preserves the exact command and suggested retry surface.

2. Compact hard-runtime frontier state:
   - Persist and project a bounded `lane_hard_runtime_frontier` object through
     `implement_v2` dynamic lane state.
   - Treat it as reentry/prompt state only. It is never acceptance proof unless
     its evidence refs resolve through the existing deterministic gates.

Add one bounded final verifier recovery turn only when the sole final blocker is
this specific tool-contract misuse and routing did not already execute it.

## Phase Plan

### Phase 1: Typed `run_tests` Shell-Surface Misuse

Files likely to change:

- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/types.py` if a small typed dict/dataclass is useful
- `tests/test_implement_lane.py`

Add a v2-local detector that returns a structured decision, not only a
`ValueError` string:

```json
{
  "kind": "run_tests_shell_surface",
  "recoverable": true,
  "features": ["newline", "pipe", "redirect", "explicit_shell_interpreter"],
  "preserved_command": "...",
  "suggested_tool": "run_command",
  "suggested_use_shell": true
}
```

Inputs:

- normalized `command`/`cmd`/`argv`;
- `cwd`;
- timeout and foreground budget;
- `execution_contract`;
- current lane permission bits, especially `allow_shell` and `allow_verify`.

The existing detection is a good starting point:

- unquoted newlines and shell operators in `_has_unquoted_run_tests_shell_surface`;
- explicit shell interpreter detection in `_has_explicit_shell_interpreter`;
- resident mew loop rejection before execution.

Required behavior:

- Simple argv-shaped `run_tests` keeps using argv-style execution.
- Quoted shell metacharacters inside a single argv argument must not route.
- `argv` arrays that explicitly invoke `bash -c`, `sh -c`, or equivalent are
  still shell orchestration and must not run as `run_tests`.
- Resident mew loop commands stay rejected; routing must not bypass that guard.
- The result payload must include a machine-readable failure class or recovery
  marker, not only prose.

New focused tests:

- simple `run_tests` command remains `run_tests`;
- `run_tests` with newline, pipe, redirection, background, heredoc, `&&`, `||`,
  or explicit shell interpreter is classified as shell surface;
- shell-like tokens inside quotes do not route;
- resident mew loop command is still rejected before any route;
- `argv=["bash", "-lc", "..."]` is classified as shell orchestration.

### Phase 2: Deterministic Route to `run_command`

Files likely to change:

- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/tool_policy.py`
- `tests/test_implement_lane.py`

When the detector identifies recoverable shell surface and this v2 attempt has
`allow_shell=true`, execute the exact preserved command through the existing
managed exec path as `run_command` with `use_shell=true`.

Pairing invariant:

- The provider emitted one `run_tests` call, so the provider receives one paired
  result for that same provider call id.
- The proof manifest should preserve both surfaces:
  - declared/provider tool: `run_tests`;
  - effective execution tool: `run_command`;
  - recovery kind: `run_tests_shell_surface_routed_to_run_command`.

Payload sketch:

```json
{
  "tool_name": "run_tests",
  "effective_tool_name": "run_command",
  "tool_contract_recovery": {
    "kind": "run_tests_shell_surface_routed_to_run_command",
    "features": ["newline", "redirect"],
    "preserved_command_hash": "sha256:...",
    "suggested_use_shell": true
  },
  "command_run_id": "...",
  "output_ref": "...",
  "status": "completed|failed|yielded",
  "exit_code": 0
}
```

Execution invariants:

- Preserve `cwd`, `timeout`, `foreground_budget_seconds`,
  `execution_contract`, expected artifacts, and declared target refs.
- Do not create a second provider-visible tool call.
- Do not bypass approval, allowed roots, command timeout, managed lifecycle, or
  active-command concurrency limits.
- Do not route if `allow_shell` is false.
- Do not route if `run_command` would be unavailable for the lane mode.
- Do not route if the resident-loop guard or existing safety checks reject the
  command.
- Routed terminal success is still only candidate evidence; the existing done
  gate decides completion.

New tests:

- shell-shaped `run_tests` routes to managed `run_command` when `allow_shell`
  is true and records recovery metadata;
- routed verifier completion creates terminal evidence refs;
- routed verifier failure stays a terminal failure with stdout/stderr tails;
- yielded routed verifier can be polled/read with the same managed command id;
- provider pairing validation still passes with one call and one result.

### Phase 3: Exclusive Final Tool-Contract Recovery Turn

Files likely to change:

- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/exec_runtime.py`
- `tests/test_implement_lane.py`

If routing did not execute the command, add one bounded recovery turn through a
dedicated tool-contract path, not through the generic terminal-failure reaction
path.

The failed tool result must carry an explicit marker:

```json
{
  "failure_class": "tool_contract_misuse",
  "failure_subclass": "run_tests_shell_surface",
  "recoverable_tool_contract_misuse": true,
  "tool_contract_recovery_eligible": true,
  "terminal_failure_reaction_eligible": false,
  "preserved_command": "...",
  "suggested_tool": "run_command",
  "suggested_use_shell": true
}
```

The existing generic terminal-failure reaction selector must skip any terminal
or tool result whose payload has `failure_class=tool_contract_misuse` or
`terminal_failure_reaction_eligible=false`. This makes the two recovery
families mutually exclusive:

- real terminal build/runtime/verifier failures can use the existing
  `terminal_failure_reaction_turns_used` budget;
- argv-only `run_tests` shell-surface misuse can use only the new
  `tool_contract_recovery_turns_used` budget;
- one failure cannot consume both budgets or receive both prompts.

Add lane metrics:

```json
{
  "tool_contract_recovery_turn_limit": 1,
  "tool_contract_recovery_turns_used": 0,
  "terminal_failure_reaction_turns_used": 0
}
```

The tool-contract recovery counter is separate from, and does not decrement,
`terminal_failure_reaction_turn_limit`.

Spend the one tool-contract recovery turn only when all conditions are true:

- The current turn is at the base turn budget or final finish gate boundary.
- The latest failed terminal/tool result is a `run_tests` tool-contract misuse
  with a preserved command and `suggested_tool=run_command`.
- No later real build/runtime/verifier failure exists.
- No successful final verifier evidence already exists after that failure.
- `allow_shell=true`, wall budget remains above the existing configurable
  reaction minimum, and `run_command` is available.
- No prior tool-contract recovery turn was spent in this attempt.

The recovery prompt must be narrower than the existing terminal-failure
reaction prompt and must not include broad failure-repair language:

```text
The last action failed only because run_tests is argv-only. Re-run the exact
preserved command with run_command/use_shell=true from the same cwd and keep the
same execution_contract. Do not broaden source investigation or invent a new
surrogate. If it cannot be run safely, finish blocked with the exact blocker.
```

This is a fallback for conservative no-route cases, not a second chance after a
real verifier/build failure.

New tests:

- final `run_tests` shell-contract failure extends exactly one
  tool-contract-recovery turn and then completes after a corrected
  `run_command`;
- the same shell-contract failure does not increment
  `terminal_failure_reaction_turns_used`;
- the generic terminal-failure reaction selector skips results marked
  `failure_class=tool_contract_misuse`;
- the second prompt contains the narrow correction text and does not contain the
  broader terminal-failure reaction wording;
- no recovery turn is added when the latest failure is an actual compiler,
  runtime, timeout, or artifact assertion failure;
- no recovery turn is added when `allow_shell=false`;
- repeated misuse does not loop beyond one extra turn;
- finish-gate blocked completion plus sole tool-contract misuse uses the same
  recovery path.

### Phase 4: Hard-Runtime Frontier State

Files likely to change:

- `src/mew/implement_lane/types.py`
- `src/mew/implement_lane/prompt.py`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/terminal_bench_replay.py`
- `tests/test_implement_lane.py`
- `tests/test_terminal_bench_replay.py`

Add a compact dynamic state object under `updated_lane_state` and projected
`persisted_lane_state`:

```json
{
  "lane_hard_runtime_frontier": {
    "schema_version": 1,
    "status": "active|blocked|resolved",
    "objective": "short task objective",
    "source_roles": [
      {
        "path": "doomgeneric_img.c",
        "role": "primary_source|runtime_harness|build_file|generated_artifact|test_harness|toolchain_probe",
        "state": "hypothesis|grounded",
        "evidence_refs": ["..."]
      }
    ],
    "harness_runtime_source": [
      {"path": "vm.js", "role": "runtime_harness", "evidence_refs": ["..."]}
    ],
    "build_target": {
      "cwd": "/app",
      "target": "shortest known target",
      "command": "make ...",
      "artifact_path": "path/to/binary",
      "evidence_refs": ["..."]
    },
    "final_artifact": {
      "path": "/tmp/frame.bmp",
      "kind": "file|image|binary|log|socket|pid|executable",
      "freshness": "must be created by final verifier-shaped command",
      "evidence_refs": []
    },
    "prohibited_surrogates": [
      "handcrafted stubs",
      "synthetic final artifacts",
      "nearby tools not named by the task"
    ],
    "latest_build_failure": {
      "command_run_id": "...",
      "exit_code": 2,
      "stderr_tail": "...",
      "failure_summary": "short"
    },
    "latest_runtime_failure": {
      "command_run_id": "...",
      "exit_code": 1,
      "stdout_tail": "...",
      "stderr_tail": "...",
      "failure_summary": "short"
    },
    "next_verifier_shaped_command": {
      "tool": "run_command",
      "cwd": "/app",
      "command": "node vm.js ... && test -s /tmp/frame.bmp",
      "use_shell": true,
      "execution_contract": {
        "purpose": "verification",
        "stage": "verification",
        "proof_role": "verifier",
        "acceptance_kind": "candidate_final_proof"
      }
    }
  }
}
```

Population rules:

- The model may return a small `frontier_state_update` object in the v2 JSON
  response contract.
- The runtime merges it with deterministic facts from terminal tool results and
  command `execution_contract` fields.
- Latest terminal failure is derived from actual tool results, not model prose.
- Expected artifacts and declared targets are derived from `execution_contract`
  when present.
- Evidence refs must point to current attempt tool results or durable artifact
  refs. Ungrounded state remains `hypothesis`.
- State is capped by size: short strings, bounded arrays, no raw logs.
- State is not acceptance evidence and must not bypass the deterministic finish
  gate.

Allowed evidence ref shapes:

All stored frontier refs should be normalized to object refs. The runtime may
accept legacy strings only when they parse to one of these shapes and resolve
against the current registries.

```json
{"kind": "tool_call", "id": 1}
{"kind": "provider_call", "id": "compile-closeout-fail"}
{"kind": "command_run", "id": "command-1"}
{"kind": "command_output", "ref": "implement_v2/.../output.log"}
{"kind": "content_ref", "ref": "implement-v2-exec://.../output"}
{"kind": "evidence_ref", "ref": "implement-v2-exec://.../terminal"}
{"kind": "proof_artifact", "path": ".../implement_v2/proof-manifest.json"}
```

Runtime resolution rules:

- Build a per-attempt registry from actual `ToolResultEnvelope` values before
  merging model-provided frontier state.
- `tool_call` ids resolve by the manifest's 1-based tool result order.
- `provider_call` ids resolve against provider call ids from the current
  attempt only.
- `command_run` ids resolve from terminal tool result content, not from model
  prose.
- `command_output` refs resolve only if they match a managed command result's
  `output_ref`.
- `content_ref` and `evidence_ref` values resolve only if they are present in a
  current tool result's `content_refs` or `evidence_refs`.
- `proof_artifact` paths resolve only if they are under this v2 attempt's
  artifact directory or manifest output paths.
- Unresolved refs are dropped from the stored state.
- If an entry has no resolved refs after filtering, its `state` is forced to
  `hypothesis` even if the model claimed `grounded`.
- Runtime-derived terminal evidence overrides model-claimed latest failures:
  the newest failed/interrupted `run_command`, `run_tests`, or `poll_command`
  result supplies `latest_build_failure` or `latest_runtime_failure` tails and
  command ids. Model-provided latest-failure fields may only fill short
  hypothesis notes when no runtime terminal failure is available.

Prompt interaction:

- Keep the cacheable hard-runtime profile generic.
- Add the compact frontier only in dynamic `implement_v2_lane_state` or a new
  dynamic `implement_v2_hard_runtime_frontier_state` section.
- The prompt should say: use this state before broad rediscovery; update it when
  a newer build/runtime result supersedes it; do not finish from it alone.

New tests:

- prompt metrics include the dynamic frontier section only when state exists or
  the hard-runtime profile is active;
- memory filtering still excludes unrelated memory summaries;
- frontier state is size-capped and serializable;
- fabricated `evidence_refs` are dropped and the entry remains `hypothesis`;
- mixed valid and invalid refs keep only resolved refs;
- legacy string refs are accepted only when they resolve to current
  content/evidence refs;
- latest failed terminal result updates latest build/runtime failure tails;
- runtime-derived terminal failure overwrites a model-claimed latest failure
  with fabricated refs;
- routed tool-contract recovery updates `next_verifier_shaped_command`;
- finish acceptance ignores frontier state without terminal evidence refs.

### Phase 5: Replay, Dogfood, and Emulator Surfaces

Files likely to change:

- `src/mew/terminal_bench_replay.py`
- `src/mew/dogfood.py`
- `tests/test_terminal_bench_replay.py`
- `tests/test_dogfood.py`

Replay should identify this as a structural v2 tool-contract gap rather than a
generic failed verifier:

```text
debug implement_v2 divergence: recover run_tests shell-surface verifier through
run_command before another live speed run
```

Add or extend a dogfood emulator for the exact generic shape:

- fake model spends its last base turn on shell-shaped `run_tests`;
- either the runtime auto-routes it to `run_command`, or the loop spends one
  final correction turn;
- the verifier command writes/proves a small generic artifact;
- report checks assert:
  - one provider call gets one paired result;
  - recovery metadata is present;
  - exactly one tool-contract recovery turn is spent;
  - `terminal_failure_reaction_turns_used` remains unchanged for this failure;
  - the correction prompt is the narrow run-command retry prompt;
  - no v1 fallback occurred;
  - frontier state contains final artifact and next verifier-shaped command
    only with resolved refs or `hypothesis` state;
  - fabricated frontier refs are dropped by the emulator fixture;
  - completion only happens after terminal evidence.

The existing
`m6_24-implement-v2-terminal-failure-reaction-emulator` remains useful for real
terminal failure reaction. The new emulator should focus on tool-contract
misuse, not compiler/runtime repair.

## Interaction With Existing Designs

### Execution Contract

`execution_contract` remains the semantic owner of command purpose, stage,
proof role, expected artifacts, declared target refs, continuation policy, and
acceptance kind.

The new route changes only execution transport:

- declared provider tool: `run_tests`;
- effective execution surface: `run_command` shell;
- same semantic `execution_contract`;
- same expected artifacts and target refs.

Reducers and finish gates should consume the typed contract and terminal
evidence, not shell-string heuristics. Shell-surface detection is only a tool
contract validator/recovery mechanism.

### Generic Managed Exec

No new process lifecycle is introduced. Routed commands still go through the
existing `ManagedCommandRunner` path, output refs, terminal/yielded statuses,
poll/cancel/read-output surfaces, foreground budget, timeout, and active command
limits.

The route must not create a parallel executor or special Terminal-Bench command
path. A routed command is just a managed command whose effective tool is
`run_command`.

### Prompt Section Registry

The stable cacheable sections should stay stable:

- `implement_v2_lane_base`
- `implement_v2_tool_contract`
- `implement_v2_tool_surface`
- `implement_v2_compatibility_frontier`
- `implement_v2_hard_runtime_profile`

Only dynamic lane state should carry frontier details. This keeps prompt-cache
semantics predictable and avoids turning one benchmark trace into permanent
task-specific prompt text.

### Implement V2 Native Tool Loop

The native loop invariants remain:

- every provider tool call has exactly one paired tool result;
- invalid/recovered calls are visible to the model;
- finish is deterministic and acceptance-gated;
- v2 failures remain v2 results and never silently fall back to v1.

Wrong-tool recovery follows the Codex pattern identified in the step-design
report: high-confidence misroutes can be recovered at the runtime boundary when
the semantics are clear. It does not import Codex architecture wholesale.

## Exact Invariants

- `implement_v1` behavior, prompts, reducers, and fallback semantics are
  unchanged.
- `run_tests` remains argv-only. It does not gain shell semantics.
- `run_command` remains the only v2 shell orchestration surface.
- Shell-shaped `run_tests` either routes to `run_command` under explicit v2
  shell permission or returns a structured recoverable tool-contract failure.
- Routing preserves command, cwd, timeout, foreground budget,
  `execution_contract`, expected artifacts, and declared target refs.
- Routing never bypasses resident mew loop rejection, allowed-root checks,
  approval requirements, managed lifecycle, or active-command limits.
- Provider pairing stays one call to one result. The manifest records both
  declared and effective tool surfaces.
- A final tool-contract recovery turn is spent at most once per v2 attempt and
  is counted separately from terminal-failure reaction turns.
- Generic terminal-failure reaction must skip tool results marked
  `failure_class=tool_contract_misuse` or
  `terminal_failure_reaction_eligible=false`.
- A final tool-contract recovery turn is not spent after a real build/runtime
  failure, timeout, unsafe command, or missing shell permission.
- Frontier state is prompt/reentry state only. It cannot prove completion.
- Frontier entries may be marked `grounded` only after all retained
  `evidence_refs` resolve against the current v2 attempt registry or durable
  v2 artifact refs.
- Unresolved frontier refs are dropped. Entries without any resolved refs are
  forced to `hypothesis`.
- Runtime-derived terminal evidence wins over model-claimed latest build/runtime
  failure fields.
- Final artifact proof must cite terminal/read evidence for the verifier-visible
  path, not the frontier state's path string alone.
- Prohibited surrogate notes persist until superseded by grounded evidence.
- No Doom-specific strings, build targets, or artifact dimensions are hardcoded.

## Failure Modes To Guard

- False route: legitimate argv `run_tests` containing quoted operators is
  misclassified as shell. Guard with quote-aware tests.
- Unsafe route: shell routing bypasses resident-loop or permission checks. Run
  the existing guards before route and preserve allow-shell gating.
- Pairing drift: internal `run_command` execution creates an extra provider
  result. Preserve provider call id and wrap the effective tool in payload.
- Acceptance drift: routed command success is accepted without final artifact or
  stdout/artifact quality proof. Keep finish gate unchanged.
- Recovery loop: repeated bad `run_tests` calls consume extra turns. Allow one
  final correction turn only, through the dedicated tool-contract counter.
- Double recovery: one shell-surface `run_tests` failure matches both
  tool-contract recovery and generic terminal-failure reaction. Require the
  dedicated marker to make generic terminal reaction ineligible.
- Wrong latest failure: tool-contract recovery fires when a later compiler or
  runtime failure exists. Select from ordered tool results and prefer latest
  real terminal failure.
- State hallucination: model-provided source roles become trusted facts. Mark
  ungrounded entries as hypotheses and require evidence refs for grounded
  state.
- Ref forgery: model-provided frontier refs point at nonexistent tool calls,
  command ids, output refs, or artifact paths. Normalize refs through the
  current attempt registry, drop unresolved refs, and force hypothesis state.
- Latest-failure forgery: model claims a latest build/runtime failure that is
  not present in terminal results. Use runtime-derived terminal evidence as the
  authoritative latest failure.
- Stale frontier: old build target or artifact path survives after a newer
  command changes the frontier. Merge by latest evidence order and allow
  explicit supersession.
- Prompt bloat: frontier stores raw logs or many files. Cap entries and keep
  logs in output refs.
- Replay blindness: replay reports only "failed run_tests" and hides the
  recoverable tool-contract class. Add explicit replay classification.

## Validation Plan Before Live Speed Proof

1. Focused unit tests:

```sh
uv run pytest --no-testmon -q tests/test_implement_lane.py -k 'run_tests and (shell or contract or route or recovery)'
uv run pytest --no-testmon -q tests/test_implement_lane.py -k 'tool_contract_recovery and terminal_failure_reaction'
uv run pytest --no-testmon -q tests/test_implement_lane.py -k 'hard_runtime or frontier or evidence_ref'
uv run pytest --no-testmon -q tests/test_terminal_bench_replay.py -k 'implement_v2 or tool_contract'
uv run pytest --no-testmon -q tests/test_dogfood.py -k 'implement_v2_tool_contract or terminal_failure_reaction'
```

2. Exact replay and dogfood on the reference-compare miss:

```sh
./mew replay terminal-bench \
  --job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare \
  --task make-doom-for-mips

./mew dogfood --scenario m6_24-terminal-bench-replay \
  --terminal-bench-job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare \
  --terminal-bench-task make-doom-for-mips \
  --json
```

3. Emulator:

```sh
./mew dogfood --scenario m6_24-implement-v2-tool-contract-recovery-emulator --json
./mew dogfood --scenario m6_24-implement-v2-terminal-failure-reaction-emulator --json
```

If the exact replay cannot expose the final shell-shaped `run_tests` misuse,
update replay extraction or the new emulator before any live proof.

4. Hygiene:

```sh
uv run ruff check src/mew/implement_lane src/mew/terminal_bench_replay.py src/mew/dogfood.py tests/test_implement_lane.py tests/test_terminal_bench_replay.py tests/test_dogfood.py
git diff --check
```

5. One same-shape speed proof only after the above is green:

```text
harbor run -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-doom-for-mips -k 1 -n 1 -y \
  --agent-timeout-multiplier 2 \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak command_cwd=/app \
  --ak container_repo_root=/mew \
  --ak timeout_seconds=1800 \
  --ak command_template='mew work --oneshot ... --work-guidance selected_lane=implement_v2 ...'
```

Do not resume broad scoped measurement until that same-shape run is classified.

## Non-Goals

- No Doom-specific prompt patch, target name, MIPS recipe, VM patch, or artifact
  quality shortcut.
- No change to `implement_v1`.
- No changes to other lanes.
- No broad global shell classifier.
- No Terminal-Bench-only wrapper behavior.
- No full Codex architecture import.
- No provider-native tool transport rewrite in this slice.
- No acceptance based on frontier state, model self-report, output tail shape,
  or artifact existence alone.
