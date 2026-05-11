# Design 2026-05-08 - M6.24 Implement V2 Hot-Path Collapse

Status: design only.

Scope: redesign the `implement_v2` active coding path so the model sees a
small Codex-like loop while mew keeps its resident-agent guarantees as sidecar
state, replay evidence, and deterministic finish safety. This document does not
authorize code changes or live benchmark spending by itself.

## Decision

Collapse the model-visible `implement_v2` hot path around this loop:

```text
latest transcript/tool result
  -> cheap probe if needed
  -> patch/edit
  -> run/verify
  -> latest actionable failure only
  -> finish with cited evidence or block precisely
```

Do not remove the resident substrate. Keep context compression, replay, dogfood
proof, typed evidence, finish gate, managed exec, durable state, and recovery
state. Move those surfaces behind deterministic sidecars and compact digests so
they audit and gate the loop rather than becoming the loop.

This is not a full rewrite. The current runtime already has usable primitives:
provider call/result pairing, managed exec lifecycle, write safety, prompt
section metadata, typed evidence, final verifier closeout, and replay artifacts.
The redesign changes ownership and projection: less model-authored state, less
proof-object prompt text, and more deterministic sidecar reduction.

## Trigger

The redesign is triggered now because the latest `first_write_readiness` and
write-repair polish partly worked, but the repair trajectory is drifting toward
more frontiers, more todo projection, and more evidence/proof objects in the
normal prompt. The 2026-05-08 decision ledger records the desired step shape:
after hot-path tuning, compare whether mew moves toward "cheap probe -> coherent
patch -> verifier -> latest-failure repair" and avoid task-specific MIPS/VM
logic (`docs/M6_24_DECISION_LEDGER.md:84-91`). The same ledger shows recent
repairs improving first-write behavior while still selecting another generic
projection repair rather than another solver (`docs/M6_24_DECISION_LEDGER.md:117-120`).

The direct Codex comparison already named the core issue: Codex wins through a
smaller, transcript-driven hot path, not a richer explicit planning ontology
(`docs/REVIEW_2026-05-07_CODEX_FLOW_VS_MEW_IMPLEMENT_V2.md:7-18`,
`:139-150`). The current mew loop has the right components, but too many of
them are projected into every model turn.

## Source Anchors

Current mew:

- `src/mew/implement_lane/v2_runtime.py:205-223` describes the live JSON loop as
  the first production v2 runtime, still using `model_json` transport rather
  than provider-native tool calls.
- `src/mew/implement_lane/v2_runtime.py:417-431` renders a full prompt each
  turn; `:516-523` accepts `finish`, `frontier_state_update`, and `tool_calls`
  in the same model payload; `:760-771` stores full history plus provider-visible
  prompt history.
- `src/mew/implement_lane/v2_runtime.py:785-859` interleaves finish-gate,
  tool-contract recovery, and terminal-failure reaction policy with normal loop
  control.
- `src/mew/implement_lane/v2_runtime.py:979-1055` writes proof manifest metrics,
  finish gate state, `active_work_todo`, and `lane_hard_runtime_frontier` into
  lane result state.
- `src/mew/implement_lane/prompt.py:30-138` defines the static prompt sections,
  including active coding rhythm, execution artifact contract, tool surface, and
  compatibility frontier. `:143-169` projects `active_work_todo`; `:170-207`
  projects the hard-runtime profile; `:230-251` projects hard-runtime frontier
  state.
- `src/mew/implement_lane/tool_policy.py:33-120` already exposes the needed tool
  surface: read/search/git, run/poll/cancel/read output, write/edit/apply_patch,
  and finish.
- `src/mew/implement_lane/exec_runtime.py:199-288` starts managed commands with
  normalized execution contracts. `:338-540` expands terminal results into
  command run, tool run record, artifact evidence, verifier evidence, failure
  classification, and structured finish gate.
- `src/mew/implement_lane/write_runtime.py:56-112` owns write/edit/apply_patch
  application and write provenance.
- `src/mew/implement_lane/replay.py:33-94` validates one paired tool result per
  provider call; `:107-153` validates write safety.

Reference CLI behavior:

- Codex builds each sampling request from conversation history
  (`references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:429-455`).
  Tool calls are recorded, queued, and force follow-up
  (`references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs:228-254`;
  `turn.rs:1961-1975`). `end_turn=false` also forces follow-up, and in-flight
  tool results are drained before the turn returns (`turn.rs:2084-2105`,
  `turn.rs:2213`).
- Codex surfaces non-fatal tool errors as model-visible tool outputs rather than
  controller states (`references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs:63-77`;
  `stream_events_utils.rs:289-338`).
- Codex's shell result shape is compact: chunk/session identity, wall time,
  exit code or session id, original token count, and truncated output
  (`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:397-479`).
- Codex exposes small exec/stdin tools
  (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:19-134`) and a
  grammar-backed first-class `apply_patch` tool
  (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:10-99`).
  `exec_command` is parallel-capable, `write_stdin` is not, and `apply_patch` is
  registered as non-parallel (`references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:156-171`,
  `:322-341`). Codex also intercepts `apply_patch` attempts sent through shell
  and routes them through the patch path (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:469-565`).
- Claude Code separates cached and dynamic prompt sections. Normal sections are
  memoized until clear/compact, while explicitly dangerous uncached sections
  need a reason (`references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:16-38`,
  `:43-57`). Its prompt builder puts static cacheable content before a dynamic
  boundary and registry-managed dynamic sections
  (`references/fresh-cli/claude-code/src/constants/prompts.ts:491-576`).
- Claude Code assembles system prompt layers separately from user/system context
  (`references/fresh-cli/claude-code/src/QueryEngine.ts:284-325`;
  `references/fresh-cli/claude-code/src/utils/queryContext.ts:30-43`) and appends
  dynamic system context at query time (`references/fresh-cli/claude-code/src/query.ts:449-451`).
- Claude Code keeps tool use as the loop-exit signal, not `stop_reason`
  (`references/fresh-cli/claude-code/src/query.ts:551-558`, `:826-835`), executes
  tool results, then recurses with messages plus tool results
  (`query.ts:1380-1400`, `:1714-1727`).
- Claude Code provides a read-only exploration phase through plan mode
  (`references/fresh-cli/claude-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts:71-118`)
  and a separate verifier nudge after todo completion
  (`references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:104-108`).
  This design borrows the separation, not another autonomous planner/lane.

## Three Surfaces

### 1. Model-Visible Hot Path

The model sees only the active coding state needed for the next action:

- static instructions for the small coding rhythm;
- task objective and current local constraints;
- latest transcript window;
- latest tool result summary, including direct failure/output details;
- latest actionable failure, if any;
- `required_next_action`, if deterministic sidecar reduction can name one;
- patch/edit/run/verify tools.

The model should not normally author `frontier_state_update`, full proof
objects, detailed execution contracts, or expanded todo/repair state. It should
act through tools and finish with cited evidence.

`required_next_action` is not retained planner state under a new name. It is
re-derived for each turn from the latest tool result, the latest actionable
failure family, and write/verifier provenance. If those inputs do not imply one
safe action, the field is omitted rather than preserved from an older turn.

Normal next-turn terminal result projection should be closer to:

```json
{
  "tool": "run_command",
  "status": "failed",
  "exit_code": 127,
  "command_excerpt": "file /app/mips",
  "stdout_tail": "",
  "stderr_tail": "file: command not found",
  "artifact_miss": null,
  "latest_failure": {
    "class": "probe_tool_unavailable",
    "next_action": "retry with an available probe such as readelf, find, grep, or Python"
  },
  "refs": {
    "command_run_id": "cmd-...",
    "output_ref": "..."
  }
}
```

### 2. Sidecar Resident Substrate

Mew keeps the resident machinery, but it owns it deterministically:

- full tool calls/results, transcripts, `history.json`, proof manifest, and
  replay artifacts;
- managed exec records, artifact evidence, verifier evidence, failure
  classification, and structured finish gate;
- typed evidence events, oracle bundle, finish claim resolver, and compact
  evidence digest;
- context compression and integration observation;
- durable lane state for recovery after compaction/resume;
- dogfood and emulator proof.

The sidecar substrate may compute frontier-like state, latest failure, and
repair readiness. It should not require the model to maintain a parallel
frontier JSON object during ordinary turns. Sidecar state is also budgeted: the
collapse is not allowed to move unbounded prompt complexity into resident JSON.

### 3. Finish, Replay, And Recovery Surfaces

Finish/replay/recovery are separate from the normal hot path:

- Finish: model emits `finish` only with `outcome`, short summary, and
  `evidence_refs`/`oracle_refs` when available. The deterministic gate decides.
- Replay: saved artifacts are the source of record. Replay validates tool
  pairing, write safety, typed evidence ids, finish gate decisions, and compact
  projection invariants.
- Recovery: after compaction, wall timeout, blocked finish, or interrupted
  command, the model sees one compact recovery card: objective, latest actionable
  failure, last successful mutation/verifier, minimal `frontier_summary`, and
  next safe action. `frontier_summary` is sidecar-derived and capped to the
  latest passed checkpoint or current blocked checkpoint plus refs. Full
  frontier and proof objects remain in sidecars.

## Hide From The Normal Prompt

Remove or hide these from ordinary model turns:

1. `frontier_state_update` in the default response contract. Keep any frontier
   state sidecar-derived. Surface it only during explicit recovery/reentry when
   it prevents rediscovery or false completion. If a default-mode model emits a
   `frontier_state_update`, the runtime should ignore it and record a debug
   note; only explicit debug/recovery mode may consume it.
2. Detailed `execution_contract` requirements for cheap probes. Cheap source,
   environment, ABI, and tool-availability probes should not have to declare
   `role`, `stage`, `proof_role`, `acceptance_kind`, and expected artifacts.
3. Full typed evidence, verifier, proof, oracle, and structured finish-gate
   objects. Project only compact ids/statuses/verdicts and one blocker summary.
4. Excessive `active_work_todo`, `first_write_readiness`, and `write_repair`
   projection. Replace with a single current step and one required next action.
5. Historical same-family repair lists unless the model is about to repeat a
   known failed edit. Store full history for replay and resident memory.

## Keep Visible

Keep these visible because they directly improve the next model action:

- direct tool failure or output summary;
- exit code, timeout/interruption state, command id, output ref, bounded tails;
- latest actionable failure only;
- concrete artifact miss or verifier verdict when relevant;
- `required_next_action` derived from the latest result/failure/provenance
  reducer;
- read/search/git/read-output, patch/edit/write, run/poll/cancel, and finish;
- a compact typed-evidence digest only when finish or verifier action needs ids.

## Phase Plan

### Phase 0: Freeze The Baseline And Name The Split

Target files:

- `docs/M6_24_DECISION_LEDGER.md`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/prompt.py`
- focused tests only

Implementation:

1. Add no hot-path behavior yet.
2. Add constants or internal names for the three surfaces:
   `hot_path_projection`, `resident_sidecar_state`, and
   `finish_replay_recovery`.
3. Add prompt metrics for total normal full-mode model-visible inventory, not
   just dynamic suffix bytes:
   `normal_full_prompt_bytes`, `normal_section_inventory`,
   `normal_static_cacheable_bytes`, `normal_dynamic_hot_path_bytes`,
   `normal_dynamic_recovery_bytes`, and `provider_visible_tool_result_bytes`.
   The inventory records section id, mode, bytes, and whether it is ordinary,
   recovery/reentry-only, or sidecar-only.
4. Add sidecar state-size metrics and caps:
   `resident_sidecar_total_bytes`, `resident_sidecar_per_turn_growth_bytes`,
   and per-family bytes/item counts for transcript/history, managed exec,
   typed evidence, oracle bundle, proof manifest, frontier/todo/recovery cards,
   and compression snapshots.
5. Record Phase 0 baselines used by later gates:
   `B_prompt_normal_total`, `B_prompt_dynamic_hot_path`,
   `B_tool_result_p95`, `B_sidecar_total`, `B_sidecar_per_turn_growth`,
   `B_first_edit_turn`, `B_first_verifier_turn`, `B_model_turns_10m`,
   `B_tool_calls_10m`, and `B_same_family_repeats_10m`.
6. Define initial cap bands. Sidecar state is green at `<= 110%` of the Phase 0
   baseline, yellow at `> 110%` and `<= 125%`, and red above `125%`, unless the
   implementation explicitly deletes an equal or larger model-visible section
   and reviewers accept the trade. Per-turn sidecar growth is red above `150%`
   of `B_sidecar_per_turn_growth`.
7. Add a no-op assertion that the normal prompt still contains existing sections
   before collapse starts.

Done when:

- focused unit tests prove no prompt/render/status/replay behavior changed;
- metrics can report total normal full-mode model-visible section inventory,
  dynamic hot-path weight, provider-visible tool-result bytes, and sidecar state
  size/growth separately;
- baseline values are written in one stable artifact or fixture for Phase 1,
  Phase 2, and Phase 6 gates;
- the decision ledger still says broad measurement is paused.

Validation:

- focused `tests/test_implement_lane.py` prompt/metrics tests;
- focused state-size metric tests proving sidecar-only proof/frontier/todo data
  is counted even when hidden from the prompt;
- `git diff --check`;
- no live benchmark, no broad tests.

### Phase 1: Collapse Prompt Sections Into Cacheable Static Plus Dynamic Hot Path

Target files:

- `src/mew/implement_lane/prompt.py`
- `src/mew/implement_lane/v2_runtime.py`
- `tests/test_implement_lane.py`

Implementation:

1. Keep the base tool loop and tool surface instructions cacheable.
2. Move runtime-hardening prose into either static guidance or recovery-only
   projection. The normal dynamic suffix should contain only current task,
   latest transcript window, latest failure, next action, and compact evidence
   digest. Measure the full normal full-mode prompt, including cacheable static
   sections and provider-visible history/tool-result text; do not judge the
   phase only by dynamic suffix shrinkage.
3. Remove `frontier_state_update` from the ordinary response contract in
   `_live_json_prompt()`. If retained temporarily, mark it deprecated and hidden
   behind an explicit `lane_config["debug_model_frontier_update"]`. Default-mode
   parsing ignores model-authored `frontier_state_update` and records only a
   sidecar debug/recovery note.
4. Replace normal `active_work_todo` projection with a compact hot-path card:

   ```json
   {
     "current_step": "patch vm.js frame output path",
     "target_paths": ["vm.js"],
     "latest_failure": "runtime_artifact_missing:/tmp/frame.bmp",
     "required_next_action": "edit target path, then run final verifier"
   }
   ```

   `required_next_action` is produced by the current-turn reducer from latest
   tool result, latest actionable failure family, and write/verifier provenance.
   It is not persisted as planner state and may be absent.

5. Follow the Claude Code prompt-section pattern: cacheable/static sections first,
   dynamic current-turn sections last, and volatile/cache-breaking content only
   with an explicit reason.
6. Make heavy ordinary-turn sections absent or capped: detailed
   execution-contract prose, hard-runtime profile/frontier JSON, expanded todo
   lists, proof/oracle objects, and typed evidence objects are recovery/reentry
   only or sidecar-only. In ordinary turns, their combined model-visible summary
   budget is `<= 1536` bytes, and full frontier/proof/oracle JSON objects are
   `0` bytes.

Done when:

- default prompt no longer asks the model to author frontier updates;
- default runtime ignores model-authored `frontier_state_update` unless explicit
  debug/recovery mode is enabled;
- total normal full-mode model-visible bytes are green at `<= 70%` of
  `B_prompt_normal_total`, yellow at `> 70%` and `<= 80%`, and red above `80%`;
- normal dynamic hot-path bytes are green at `<= 45%` of
  `B_prompt_dynamic_hot_path`, yellow at `> 45%` and `<= 60%`, and red above
  `60%`;
- heavy execution-contract, hard-runtime/frontier/todo/proof content is absent,
  recovery/reentry-only, or within the `1536` byte ordinary-turn cap;
- sidecar totals remain green or yellow under the Phase 0 sidecar bands; red
  sidecar growth fails the phase even if prompt bytes improve;
- cacheable/static prompt ordering is stable;
- existing read/write/exec fake-provider tests still pass.

Validation:

- unit tests for section ids/order/cache policies;
- prompt snapshot tests for normal full mode and recovery/reentry mode;
- default-runtime fake-provider test where the model emits
  `frontier_state_update` and the runtime ignores it; paired debug/recovery-mode
  test may prove the explicit opt-in path still works;
- prompt budget test that reports full normal prompt inventory and fails if
  heavy sections appear uncapped in ordinary turns;
- replay fixture proving old artifacts still summarize, even if old internal
  lane state is not reused.

### Phase 2: Collapse Tool-Result Projection To Latest Actionable Failure

Target files:

- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/execution_evidence.py`
- focused tests

Implementation:

1. Keep full structured execution evidence in `ToolResultEnvelope`, proof
   manifest, and side effects.
2. Change provider-visible terminal projection to one compact result plus
   `latest_failure`:
   command/run id, status, semantic exit, exit code, timed out, bounded tails,
   artifact miss/verifier verdict, blocker class, and next action.
   `next_action` is computed from the same reducer inputs as Phase 1:
   latest tool result, latest actionable failure family, and write/verifier
   provenance.
3. Cheap probe failures must remain cheap probe failures. A missing local tool
   such as `file: command not found` must not appear to the model as an artifact
   proof failure.
4. Collapse historical failures by replacement, not accumulation. The next prompt
   carries the latest actionable failure for each family only when still
   unresolved.
5. Preserve `read_command_output`/content refs for deliberate expansion.

Done when:

- normal prompt history omits full artifact/verifier/proof objects;
- latest failure projection is deterministic from tool results;
- provider-visible tool-result projection p95 is green at `<= 40%` of
  `B_tool_result_p95`, yellow at `> 40%` and `<= 55%`, and red above `55%`;
- the normal prompt carries at most one unresolved `latest_failure` per family
  and no retained historical same-family repair list;
- repeated same-family failure projection in prompt history is green at
  `<= 1` per family, yellow at `2` only with an explicit new tool result between
  repeats, and red at `>= 3`;
- sidecar totals remain below the Phase 0 red cap after full structured evidence
  is hidden from the prompt;
- command-not-found and diagnostic nonzero cases project as probe/tool failures;
- verifier/runtime failures still include artifact or verifier facts needed for
  the next patch.

Validation:

- unit tests for cheap probe, build failure, runtime artifact miss, timeout,
  interrupted command, and final verifier pass;
- projection budget tests for p95 terminal-result bytes and latest-failure
  replacement;
- exact replay of a saved `make-mips-interpreter` miss showing same final status
  but smaller provider history;
- no weakening of replay pairing/write-safety validation.

### Phase 3: Make Execution Contracts Sidecar-Inferred For Cheap Probes

Target files:

- `src/mew/implement_lane/exec_runtime.py`
- `src/mew/implement_lane/execution_evidence.py`
- `src/mew/implement_lane/prompt.py`
- focused tests

Implementation:

1. Introduce command intent tiers:
   `probe`, `diagnostic`, `build`, `runtime`, `verify`, `finish_verifier`.
2. For `probe` and `diagnostic`, the model supplies only command/cwd/timeout and
   maybe a short purpose. The runtime assigns a non-acceptance contract.
3. For `verify` and `finish_verifier`, allow a compact `verify` object or typed
   evidence refs instead of the full execution-contract ontology in prompt text.
4. Preserve the full `ExecutionContract` dataclass and normalized sidecar
   evidence. The sidecar can still derive expected artifacts from task contract,
   verifier evidence, and runtime-advertised paths.
5. Reject or downgrade model-authored artifact expectations on cheap probes.

Done when:

- cheap probes no longer require detailed execution contracts;
- verifier-shaped commands still produce typed evidence and finish-gate facts;
- existing acceptance safety asserts still block false completion;
- no new task-specific rule is introduced.

Validation:

- unit tests for contract inference and downgrade behavior;
- typed evidence tests from `docs/DESIGN_2026-05-08_M6_24_TYPED_EVIDENCE_ACCEPTANCE.md:656-718`;
- runtime finish-gate emulator for visual/artifact tasks.

### Phase 4: Privilege Patch/Edit As The Source Mutation Boundary

Target files:

- `src/mew/implement_lane/write_runtime.py`
- `src/mew/implement_lane/tool_policy.py`
- `src/mew/implement_lane/v2_runtime.py`
- focused tests

Implementation:

1. Make `apply_patch` the preferred mutation path for coherent changes,
   including add/update/delete and multi-hunk edits if implementation scope
   allows. Codex's grammar-backed patch tool is the reference shape.
2. Keep `write_file` for generated files and whole-file replacement.
3. Keep `edit_file` for exact current-text replacement.
4. Stage shell mutation policy instead of hard-blocking immediately:
   - Phase 4A records diff-level side effects around `run_command` for source
     mutations, attaches that provenance to sidecar state, and makes finish fail
     unless the mutated diff is accounted for by write/verifier evidence.
   - Phase 4B may hard-block, route, or intercept obvious shell patch/write
     commands only after replay and dogfood evidence show Phase 4A catches the
     relevant escapes without excessive false positives.
5. After failed write/edit/apply_patch, skip later same-turn verifier calls and
   project the write failure as the latest failure, not as a reason to test stale
   code.

Done when:

- in Phase 4A, shell source mutations cannot silently escape finish-time gating,
  even if they are not blocked at command time;
- hard-blocking or shell-to-patch routing is enabled only after Phase 4A replay
  and dogfood evidence supports it;
- a failed exact edit leads to current-text repair or patch, not another verifier;
- write evidence and approval invariants remain intact.

Validation:

- unit tests for add/update/delete patch cases or explicit non-support if kept
  narrow;
- unit tests for diff-level shell mutation side-effect recording and finish-time
  block;
- later Phase 4B tests for hard block or shell-to-patch routing only if that
  escalation is implemented;
- replay of the stale exact-edit/write-repair saved artifact;
- `git diff --check`.

### Phase 5: Collapse Finish To Cited Evidence And Recovery Cards

Target files:

- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/execution_evidence.py`
- `src/mew/acceptance.py`
- `src/mew/dogfood.py`
- focused tests

Implementation:

1. Keep typed evidence and oracle bundle as sidecar state, following the typed
   evidence design migration (`docs/DESIGN_2026-05-08_M6_24_TYPED_EVIDENCE_ACCEPTANCE.md:637-654`).
2. The model-visible finish prompt asks for `finish.evidence_refs` and
   `finish.oracle_refs`, not prose acceptance claims.
3. Normal prompt gets a compact evidence digest only when refs are needed.
4. If finish gate blocks, project one recovery card:

   ```json
   {
     "finish_blocked": true,
     "missing": ["oracle:task:frame_similarity"],
     "passed": ["ev:artifact:frame_exists"],
     "frontier_summary": {
       "blocked_checkpoint": "final visual similarity verifier",
       "refs": ["cmd:verify-frame", "oracle:task:frame_similarity"]
     },
     "next_action": "run one verifier-shaped comparison and finish with its evidence id"
   }
   ```

   `frontier_summary` is optional and capped. It names either the latest passed
   checkpoint or current blocked checkpoint plus refs; it never expands into the
   full frontier, proof manifest, oracle bundle, or typed evidence object.

5. Do not retire legacy safety asserts until typed replay/dogfood covers the same
   false-completion family.

Done when:

- focused finish tests pass with cited ids;
- typed allow does not bypass a valid legacy safety block unless that family has
  been retired by replay/dogfood evidence;
- finish-gate blocks are phrased as missing typed obligations or invalid ids.

Validation:

- `tests/test_acceptance.py` typed resolver cases;
- `tests/test_implement_lane.py` cited finish and digest projection;
- `tests/test_dogfood.py` runtime finish-gate emulator and terminal-bench replay
  dogfood cases.

### Fast Inner Loop: Phase Contract Before Live Step-Shape

`step-check-10min` is an integration gate, not the default implementation
feedback loop. Each HOT_PATH_COLLAPSE phase must have a fast contract check that
can fail before Harbor, Terminal-Bench, or a long live LLM run is used.

Target files:

- `scripts/check_implement_v2_hot_path.py` or an equivalent `poe` task;
- focused tests in `tests/test_implement_lane.py`, `tests/test_acceptance.py`,
  and replay/dogfood test modules;
- saved proof-artifact fixtures for the current failure family.

Fastcheck order:

1. Run the focused unit-test subset for the touched surface.
2. Run `scripts/check_implement_v2_hot_path.py` on the latest current-head
   artifact for the changed surface.
   - For legacy WorkFrame/history artifacts, this includes WorkFrame replay,
     prompt leak, sidecar/projection, latest-actionable-failure, and
     hash-bound micro next-action checks.
   - For provider-native artifacts, this includes native transcript read,
     manifest/transcript hash, call/output pairing, `response_items.jsonl`
     equality, normalized trace parse cleanliness, and native loop-control
     replay. It must not require or regenerate legacy `history.json`.
3. Replay the latest saved artifact for the relevant failure family.
4. Run prompt leak checks:
   - no normal prompt `frontier_state_update`;
   - no full proof/oracle/typed-evidence object in the normal prompt;
   - active todo is projected as a compact card only.
5. Run sidecar/projection checks:
   - `hot_path_projection` and `resident_sidecar_state` metrics are present;
   - sidecar total and per-turn growth are within the current phase cap;
   - latest actionable failure is projected once per family.
6. Run a required micro next-action check when the artifact mode provides a
   history/WorkFrame micro fixture:
   - use a saved intermediate history from `make-mips-interpreter`,
     `build-cython-ext`, or another measured coding task;
   - ask the model for the next tool call category only;
   - classify the answer as `patch/edit`, `run_verifier`,
    `inspect_latest_failure`, `cheap_probe`, or `invalid`;
   - do not run Harbor for this check.
   Native transcript artifacts may skip the legacy micro fixture only when the
   native fastcheck has direct transcript/trace/loop-control checks for the same
   repair class. Do not add `history.json` back solely to satisfy this step.

Micro LLM checks are required because they are cheaper than a live Harbor
diagnostic and catch prompt/projection mistakes that pure unit tests cannot
observe. They must be fixture-backed, hash-bound, and category-based; they must
not assert a task-specific exact command as the only passing answer. A saved
micro fixture is acceptable for the fast inner loop only when its prompt,
projection, and model-context hashes still match. If the fixture is missing,
stale, or explicitly refreshed, the fastcheck makes one bounded live LLM API
call using `auth.json` and saves the response as the next fixture. The gate must
fail if no current micro next-action evidence is available.

Done when:

- a single command can run the fast contract check for HOT_PATH_COLLAPSE;
- the command prints the artifact paths it used and the metrics file it wrote;
- a phase implementation cannot proceed to `step-check-10min` while focused UT,
  replay, prompt leak, sidecar/projection, or required micro LLM checks are red;
- failures explain which phase contract failed, not only that the benchmark
  failed.

Validation:

- the fastcheck itself is covered by a small smoke test or documented fixture;
- at least one saved failing artifact is caught by fastcheck before a live
  10 minute diagnostic is run;
- fastcheck reuses saved micro evidence without network access when hashes
  match, but missing or stale evidence must trigger a bounded live micro LLM
  refresh via `auth.json`; the refreshed response is saved as fixture evidence.

### Phase 6: Replay, Dogfood, Emulator, And Step-Shape Gate

Target files:

- replay/dogfood surfaces touched by prior phases;
- no benchmark runner changes unless an emulator cannot express the gap.

Gate order:

1. HOT_PATH_COLLAPSE fastcheck for the changed phase.
2. Focused unit tests for any surface not covered by fastcheck.
3. Exact replay of the latest relevant saved Harbor artifact.
4. `mew dogfood --scenario m6_24-terminal-bench-replay` with explicit
   terminal-bench assertions for the artifact being validated.
5. Runtime finish-gate emulator.
6. Selected hard-runtime/source-frontier emulator, such as
   `m6_24-implement-v2-hard-runtime-progress-continuation-emulator` when the
   change affects runtime frontier projection.
7. For native v2, verify the native artifact fastcheck result is green and
   records `history_path=""`, `transcript_path`, and native loop-control replay.
8. One same-shape 10 minute `make-mips-interpreter` step-shape diagnostic.
9. Reference-step comparison against Codex and Claude Code traces.

Done when:

- the 10 minute diagnostic is green or yellow against Phase 0 baselines:
  - first edit turn is green at `<= 75%` of `B_first_edit_turn`, yellow at
    `> 75%` and `<= 100%`, and red above baseline;
  - first verifier turn is green at `<= 90%` of `B_first_verifier_turn`, yellow
    at `> 90%` and `<= 110%`, and red above `110%`;
  - total model turns are green at `<= 90%` of `B_model_turns_10m`, yellow at
    `> 90%` and `<= 100%`, and red above baseline;
  - tool calls are green at `<= 100%` of `B_tool_calls_10m`, yellow at `> 100%`
    and `<= 115%`, and red above `115%`;
  - prompt p95 normal full-mode bytes are green at `<= 70%` of
    `B_prompt_normal_total`, yellow at `> 70%` and `<= 80%`, and red above
    `80%`;
  - repeated same-family loops are green at `<= 50%` of
    `B_same_family_repeats_10m` and `<= 1` unresolved repeat per family, yellow
    at `<= baseline`, and red above baseline;
  - sidecar total and per-turn growth stay below the Phase 0 red caps after the
    same-shape diagnostic;
- the qualitative shape matches cheap probe -> coherent patch -> verifier ->
  latest-failure repair, with no task-specific solver;
- external score is classified after step shape, not used as the only signal.

Validation:

- no broad measurement, `speed_1`, or `proof_5` until fastcheck and the above
  Phase 6 gate pass;
- update `docs/M6_24_DECISION_LEDGER.md` only after implementation evidence
  exists.

## Close Gate

HOT_PATH_COLLAPSE is not closed by a single green benchmark. It is closed only
when the implementation can repeatedly prove that the model-visible coding loop
is smaller and the resident guarantees still live in deterministic sidecars.

Close prerequisites:

1. Phase 0 through Phase 6 are explicitly marked implemented in
   `ROADMAP_STATUS.md` or the current milestone status document, with links to
   the commits and artifacts used for each phase.
2. The fast inner loop command is the default pre-step-shape check for this
   milestone and is documented in the milestone status.
3. Normal prompts do not ask the model to author `frontier_state_update`.
4. Normal prompts do not expose full proof manifests, oracle bundles, typed
   evidence objects, or unbounded active todo/frontier state.
5. `required_next_action` is re-derived from latest reducer inputs each turn; it
   is not persisted hidden planner state.
6. Sidecar metrics are green or explicitly accepted yellow, never red.
7. Typed evidence finish safety is at least as strict as the legacy string
   gates for covered false-completion families.
8. Replay, dogfood, emulator, and micro next-action checks all pass for the
   current target failure families.
9. Native transcript artifacts pass the native HOT_PATH fastcheck without
   legacy `history.json` fallback.
10. The 10 minute step-shape diagnostic is green or yellow and does not regress
   first edit turn, first verifier turn, prompt bytes, or repeated same-family
   loops against the Phase 0 baseline.
11. Any remaining failure is recorded as either:
    - implementation polish inside this design;
    - a measured provider/tool-transport gap for a later milestone;
    - or an explicit stop condition requiring redesign.

Do not close if:

- the latest repair added another normal-prompt frontier/todo/evidence object;
- `step-check-10min` is the first detector for a bug that should be caught by
  fastcheck, replay, dogfood, emulator, or micro next-action checks;
- the phase status is inferred from benchmark score without contract evidence;
- context compression would leave the next implementer unsure whether to add a
  new structure or collapse an existing one.

## Test Plan

Unit tests:

- prompt section split, total normal full-mode model-visible section inventory,
  dynamic section byte budget, heavy-section ordinary-turn cap, and response
  contract without default `frontier_state_update`;
- default-mode ignore of model-authored `frontier_state_update`, with explicit
  debug/recovery-mode opt-in if retained;
- sidecar state-size budget/cap metrics so hidden proof/frontier/todo state is
  counted outside the prompt;
- latest-failure projection for command-not-found, nonzero diagnostic, build
  failure, runtime timeout, missing artifact, stale artifact, verifier fail, and
  verifier pass;
- `required_next_action` re-derivation from latest tool result, latest failure
  family, and write/verifier provenance, including omission when no safe action
  is implied;
- cheap-probe contract inference and verifier contract preservation;
- compact typed digest and cited finish ids;
- write/edit/apply_patch provenance, failed write repair, and shell mutation
  detection/recording;
- finish safety counters and state-size limits.

Replay:

- exact saved `make-mips-interpreter` artifacts for the latest hot-path miss;
- saved write-repair/stale exact-edit artifact;
- saved final-verifier closeout pass artifact;
- manifests before this design remain readable for replay reports, but old
  unreleased internal lane state is not a live compatibility contract.

Dogfood:

- `m6_24-terminal-bench-replay` with explicit assertions;
- runtime finish-gate emulator;
- hard-runtime progress/frontier continuation emulator;
- any narrower source-frontier emulator created for the selected failure shape.

Step shape:

- one 10 minute same-shape diagnostic before `speed_1` or `proof_5`;
- compare against Codex reference traces for `make-mips-interpreter` and
  `build-cython-ext`, including first command/edit/verifier, model turns, tool
  calls, prompt chars, repeated same-frontier loops, and whether the next action
  follows the latest failure;
- classify green/yellow/red with the Phase 6 numeric bands before deciding
  whether any live measurement is allowed;
- use Claude Code as a structural reference for prompt layering, read-only
  exploration, verifier separation, compact tool result projection, and
  concurrent-safe tool execution, not as a reason to add a new autonomous lane.

## Regression Gates

- No new frontier unless the design explicitly justifies why existing sidecar
  state cannot represent the needed recovery fact.
- No new task-specific MIPS, VM, emulator, DOOM, or Terminal-Bench solver.
- No weakening finish safety. Typed evidence can replace legacy string gates only
  after replay/dogfood proves equivalent coverage for that false-completion
  family.
- No full proof/verifier/oracle objects in normal prompt history.
- No unbounded sidecar growth. Prompt reduction must preserve or improve
  Phase 0 sidecar cap bands unless reviewers approve a measured trade.
- No retained planner state renamed as `required_next_action`; it must be
  re-derived from current reducer inputs each turn.
- No broad measurement from red focused tests.
- No provider-native tool-calling or provider-specific prompt-cache work in this
  redesign. Those are later optimizations after the hot path is thinner.
- No new autonomous planner/lane. Claude Code plan mode and verifier separation
  are references for phase separation only.
- No hidden supervisor rescue edits in validation evidence.

If Phase 6 plateaus after these collapse gates, the next likely gap is
provider-native tool transport and prompt-cache mechanics, not another layer of
projection scaffolding.

## Ownership Recommendation

This should be Codex-supervisor implemented, not mew-first.

Reason: this is loop substrate surgery. It changes prompt ownership, recovery
projection, finish evidence, write provenance, and replay/dogfood contracts.
Those are the guarantees mew relies on to judge itself. A mew-first attempt here
would make the system under test modify its own scoring and recovery substrate
while the failure class is already "hot-path projection drift." Mew-first can be
used later for bounded application tasks after the collapse is reviewed and
validated.

## Migration Plan

There is no external compatibility requirement for unreleased internal lane
state. Migration should prefer simpler live state:

1. Introduce a new internal projection schema version for hot-path prompt
   history and recovery cards.
2. Ignore or compact old `active_work_todo`, `write_repair`, and
   `lane_hard_runtime_frontier` live state into the new recovery card shape.
3. Keep saved proof manifests readable for replay reports, because they are
   validation evidence, not public API.
4. Do not preserve old model output fields such as `frontier_state_update` as a
   normal compatibility contract. During staging, accept them but do not require
   or prompt them.
5. Migrate fake-provider tests and replay fixtures phase by phase. Delete old
   fixture expectations only after the new replay/dogfood gate covers the same
   safety case.

## Risks

- The prompt may hide too much and cause rediscovery. Mitigation: recovery cards
  and replay compare repeated same-frontier loops before live speed/proof.
- Finish safety may accidentally depend on prose again. Mitigation: typed ids,
  legacy safety asserts, and typed coverage-gap metrics.
- Sidecar state may grow while prompt text shrinks, creating new complexity.
  Mitigation: Phase 0 sidecar baselines, `110%`/`125%` cap bands, per-turn
  growth limits, no new frontier by default, and state-size tests.
- `required_next_action` may become hidden planner state. Mitigation: recompute
  it each turn from latest result/failure/provenance inputs and omit it when the
  reducer cannot justify one action.
- Shell mutation detection may create false positives. Mitigation: start with
  recording diff side effects before hard blocking broad command shapes.
- Model-visible evidence digests may still be too large. Mitigation: cap digest
  size and stop if prompt weight exceeds the Phase 0 red band.
- A 10 minute diagnostic can improve shape without improving score. Mitigation:
  classify step shape first, then decide whether same-shape `speed_1` is allowed.

## Stop Conditions

Stop and revise before more code if:

- the implementation adds another frontier/todo/evidence object to the normal
  prompt instead of hiding or collapsing one;
- sidecar state crosses the Phase 0 red cap without an accepted measured trade;
- default prompts still ask the model to author `frontier_state_update`;
- default runtime consumes model-authored `frontier_state_update` outside
  explicit debug/recovery mode;
- cheap probe failures are still projected as artifact/verifier proof failures;
- `required_next_action` persists across turns without being re-derived from the
  latest result/failure/provenance inputs;
- a finish accepted by the new path would be blocked by a valid current safety
  assert;
- focused UT, replay, dogfood, or emulator gates are red;
- step-shape analysis shows more model turns, more prompt chars, delayed first
  edit, or repeated same-frontier loops after the collapse;
- the proposed repair becomes task-specific to MIPS/VM/Terminal-Bench rather than
  generic coding-loop substrate.

## Acceptance For This Design

Reviewers should accept this design if they agree that:

- the active model loop should become transcript/tool-result driven;
- proof, frontier, typed evidence, context compression, and durable state remain
  resident sidecars with measured size caps;
- full-mode prompt reduction is judged by total model-visible section inventory,
  not only dynamic suffix bytes;
- finish safety is preserved or strengthened;
- implementation must be Codex-supervisor owned;
- validation uses focused UT, exact replay, dogfood, emulator, 10 minute
  step-shape diagnostic with numeric Phase 0 bands, and reference-step comparison
  before any speed/proof.
