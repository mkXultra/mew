# Design 2026-05-10 - M6.24 Implement V2 WorkFrame Redesign

Status: design only.

Scope: `implement_v2` during M6.24 HOT_PATH_COLLAPSE only. This design does
not authorize code changes or live benchmark spending by itself.

No backward compatibility is required for old `implement_v2` model-visible
state, old model output fields, or unreleased internal lane projections. Saved
M6.24 proof artifacts remain validation evidence, but the live runtime should
prefer deletion and replacement over compatibility adapters.

## Decision

Redesign the `implement_v2` hot path around one model-visible state object:
`WorkFrame`.

Full detail stays in deterministic sidecars:

- typed evidence events and oracle obligations;
- managed exec records, command output refs, and normalized execution contracts;
- write/edit/apply_patch provenance and source mutation records;
- replay artifacts, proof manifests, prompt/render traces, and debug snapshots;
- finish-gate and verifier closeout records.

The model sees only static instructions, paired transcript/tool-result text, and
one current `WorkFrame` JSON object produced by a single pure reducer. No normal
turn should expose a second frontier, active todo card, repair-history card,
proof object, oracle object, execution-contract object, or model-authored
frontier update.

The reducer is the sole owner of:

- what the current task goal is;
- what phase the loop is in;
- what the latest actionable fact is;
- what action is required next;
- what actions are forbidden until evidence changes;
- which source files changed;
- whether verifier evidence is fresh;
- whether finish is ready;
- which sidecar evidence refs justify the frame.

If the reducer cannot justify a field from current sidecar inputs, the field is
empty or explicitly blocked. It must not carry stale planner state forward under
a new name.

## Trigger

The May 8 hot-path collapse design moved in the right direction, but the last
several hours of M6.24 repairs show the same pattern repeating across separate
boundaries:

- `2a70beb` added deterministic final verifier closeout after late source
  mutation.
- `c1245f9` clarified prewrite coverage projection.
- `e0b0f93` tightened typed finish recovery and raw evidence alias handling.
- `90d1a91` and `afbd58a` repaired latest-failure projection for killed/no-output
  verifier failures and generic runtime diagnostics.
- `cb142b5`, `cf343ee`, `2596b19`, `e16c3c4`, and nearby commits touched
  verifier artifact handling, frontier recovery, source mutation boundaries, and
  repeated verifier polling.

The roadmap now marks HOT_PATH_COLLAPSE as not closeable. The implemented slices
are useful, but the conceptual surface is still too wide: frontier state, active
work todo, execution contracts, typed evidence, finish recovery, prewrite gates,
and final verifier closeout are repaired as neighboring projections instead of
one deterministic model boundary.

This design replaces that boundary. It is not another patch to the current
frontier/todo layering.

## Non-Goals

- No task-specific MIPS, VM, DOOM, Terminal-Bench, or `make-mips-interpreter`
  solver heuristic.
- No provider-native tool-calling redesign.
- No broad M6.24 measurement plan.
- No new autonomous planner or helper lane.
- No preservation of old `frontier_state_update`, `active_work_todo`, or
  `lane_hard_runtime_frontier` as model-visible contracts.
- No weakening of finish safety. Typed evidence can replace legacy gates only
  when replay/dogfood/emulator coverage proves equivalent or stricter behavior.

## WorkFrame

`WorkFrame` is the only controller-authored dynamic state object rendered to the
model during ordinary `implement_v2` turns.

Example shape:

```json
{
  "schema_version": 1,
  "trace": {
    "attempt_id": "attempt-...",
    "turn_id": "turn-7",
    "workframe_id": "wf-...",
    "input_hash": "sha256:...",
    "output_hash": "sha256:..."
  },
  "goal": {
    "task_id": "terminal-bench:...",
    "objective": "Repair the workspace to satisfy the configured task verifier.",
    "success_contract_ref": "task-contract:...",
    "constraints": ["no_task_specific_solver", "use_workspace_tools"]
  },
  "current_phase": "repair_after_verifier_failure",
  "latest_actionable": {
    "family": "runtime_verifier_failure",
    "summary": "TypeError: this.check is not a function",
    "source_ref": "cmd:run-12",
    "evidence_refs": ["ev:verifier:run-12", "out:run-12:stderr-tail"]
  },
  "required_next": {
    "kind": "patch_or_edit",
    "reason": "latest strict verifier failed with an actionable runtime diagnostic",
    "target_paths": ["vm.js"],
    "after": "run_configured_verifier"
  },
  "forbidden_next": [
    {
      "kind": "finish",
      "reason": "strict verifier evidence is failing after the latest source mutation"
    },
    {
      "kind": "broad_rediscovery",
      "reason": "latest_actionable already identifies a concrete repair surface"
    }
  ],
  "changed_sources": {
    "paths": ["vm.js"],
    "latest_mutation_ref": "write:turn-6:call-2",
    "since_last_strict_verifier": true
  },
  "verifier_state": {
    "configured_verifier_ref": "task-contract:verify_command",
    "last_strict_verifier_ref": "cmd:run-12",
    "status": "failed",
    "fresh_after_latest_source_mutation": true,
    "budget_closeout_required": false
  },
  "finish_readiness": {
    "state": "not_ready",
    "blockers": ["verifier_failed"],
    "required_evidence_refs": ["ev:verifier:passing-after-latest-source-mutation"]
  },
  "evidence_refs": {
    "typed": ["ev:verifier:run-12"],
    "sidecar": ["sidecar:write-provenance:turn-6", "sidecar:exec:run-12"],
    "replay": ["replay:event:turn-7:workframe"]
  }
}
```

Required top-level fields:

- `goal`: compact task objective, success contract ref, and active constraints.
- `current_phase`: a small enum describing the loop state.
- `latest_actionable`: the newest fact that should change the next action.
- `required_next`: the one reducer-justified next action, or `null`.
- `forbidden_next`: actions that would be unsafe or wasteful until evidence
  changes.
- `changed_sources`: source mutation provenance and whether verification is
  stale.
- `verifier_state`: configured verifier, latest verifier evidence, freshness,
  and closeout need.
- `finish_readiness`: whether finish can be accepted, plus missing obligations.
- `evidence_refs`: refs into typed evidence, sidecar records, and replay logs.

`WorkFrame` is bounded. A normal frame should target `<= 4096` bytes, with a red
gate above `6144` bytes unless reviewers accept a measured trade. Large output,
proof objects, history, oracle bundles, and raw typed evidence are not embedded;
they are referenced.

## Reducer Contract

Introduce one reducer, conceptually:

```text
WorkFrameInputs
  -> reduce_workframe(inputs)
  -> WorkFrame + WorkFrameTrace + WorkFrameInvariantReport
```

Reducer inputs are canonical sidecar facts, not previous prompt text:

- task contract digest and selected lane config;
- current attempt, turn, budget, and provider-call identity;
- full tool calls/results and provider-visible history;
- managed exec lifecycle records and output refs;
- write provenance, source mutation roots, and changed file refs;
- normalized execution contracts and command intent tiers;
- typed evidence events, oracle obligations, and finish-gate decisions;
- final verifier closeout records;
- replay manifest metadata and prior `WorkFrame` hash for diffing only.

The previous `WorkFrame` may be used to emit a diff and detect churn. It is not
authoritative input for `required_next`, `finish_readiness`, verifier freshness,
or source mutation status. Recomputing from the same sidecar event log must
produce the same frame hash.

### Reducer Input Canonicalization

Reducer determinism depends on byte-stable inputs. `WorkFrameInputs` are
canonicalized before hashing and before `reduce_workframe()` runs.

Event ordering:

- Sidecar events are ordered by a monotonic `event_sequence` assigned at write
  time.
- If a legacy fixture lacks `event_sequence`, the conversion step must assign a
  deterministic sequence from provider turn, tool index, provider_call_id,
  command_run_id, and original artifact order, then write that sequence into the
  fixture input.
- Events with the same sequence are invalid unless they are byte-identical
  duplicates.
- The reducer does not sort by wall-clock timestamp, filesystem mtime, process
  id, or provider arrival timing.

Fields excluded from the reducer input hash:

- raw wall-clock timestamps, mtimes, pids, hostnames, local username, and
  provider latency;
- absolute artifact root prefixes, replaced by stable artifact-relative paths;
- absolute workspace root prefixes, replaced by `$WORKSPACE`;
- raw token accounting and provider billing metadata;
- dict insertion order, platform path separators, and raw CRLF line endings;
- debug-only comments or reviewer annotations in fixture files.

Fields included in normalized form:

- reducer schema version, WorkFrame schema version, canonicalizer version, and
  fixture conversion version;
- semantic budget facts used by the reducer, such as remaining model-turn class,
  wall-budget class, and closeout eligibility, rounded or bucketed by the
  runtime before canonicalization;
- provider_call_id, command_run_id, write_provenance_id, typed_evidence_id, and
  replay event ids;
- normalized relative paths and output refs;
- normalized stdout/stderr tails after line-ending conversion.

Canonical serialization:

- JSON is UTF-8, `sort_keys=true`, compact separators, no NaN/Infinity, and a
  trailing newline.
- Text fields use LF line endings. CRLF and bare CR normalize to LF before
  hashing.
- Numeric values are serialized as integers when exact, otherwise as fixed
  decimal strings chosen by the producer.
- Binary outputs are never embedded in the hash input. The input contains a
  content hash and ref metadata.
- The hash preimage starts with an explicit envelope:

  ```json
  {
    "reducer_schema_version": 1,
    "workframe_schema_version": 1,
    "canonicalizer_version": 1,
    "payload": {}
  }
  ```

Fastcheck must recompute canonical input hashes from saved fixtures on the
current machine and fail if the stored hash cannot be reproduced. A cross-machine
fixture recomputation mismatch is `reducer_nondeterministic`, not a prompt or
model failure.

Reducer order:

1. Normalize sidecar events into small facts: latest tool result, latest source
   mutation, latest strict verifier, latest finish gate, active budget, and
   typed evidence obligations.
2. Compute `changed_sources` from write provenance and diff side effects.
3. Compute `verifier_state`, including whether the latest strict verifier is
   after the latest source mutation.
4. Compute `finish_readiness` from typed evidence and legacy safety gates.
5. Compute `latest_actionable` from the latest unresolved failure family, not
   from retained frontier prose.
6. Compute `current_phase` from mutation/verifier/finish state.
7. Compute `required_next` and `forbidden_next` from the same facts.
8. Attach evidence refs and trace ids.
9. Run invariants before rendering the prompt.

If multiple next actions look plausible, the reducer should either choose the
least risky one with cited evidence or set `required_next=null` and include a
bounded `latest_actionable` summary. It should not invent a persistent todo.

## Phase Enum

Initial `current_phase` enum:

- `orient`: no meaningful task/source evidence yet.
- `cheap_probe`: the next needed action is bounded read/search/environment
  inspection.
- `prewrite_blocked`: source mutation is forbidden until required generic
  coverage exists.
- `ready_to_patch`: enough evidence exists for first coherent mutation.
- `repair_after_write_failure`: write/edit/apply_patch failed and stale-code
  verification is forbidden.
- `verify_after_mutation`: source changed and no strict verifier is fresh.
- `repair_after_verifier_failure`: latest strict verifier failed with an
  actionable failure.
- `finish_ready`: finish is allowed if cited evidence refs are used.
- `finish_blocked`: finish was attempted or considered but obligations are
  missing.
- `controller_closeout`: deterministic closeout, such as final verifier closeout,
  is running or just ran.
- `blocked`: no safe next action remains under current budget or evidence.

These phases describe generic coding-loop state. They must not encode
task-specific runtime names.

## Prompt and Response Shape

Ordinary prompt shape:

1. Static cacheable instructions for the small coding rhythm and tool surface.
2. Task contract or a stable task-contract digest where possible.
3. Paired transcript/tool-result window.
4. Exactly one dynamic `implement_v2_workframe` section containing `WorkFrame`.

Delete ordinary dynamic sections that currently project parallel state:

- `implement_v2_active_work_todo`;
- `implement_v2_hard_runtime_frontier_state`;
- `implement_v2_repair_history`;
- ordinary prompt fragments that expose proof manifests, oracle bundles, full
  typed evidence objects, or detailed execution-contract ontology.

The model response contract allows:

- tool calls;
- `finish` with `outcome`, short `summary`, and `evidence_refs`;
- no `frontier_state_update`;
- no model-authored todo update;
- no model-authored proof object;
- no model-authored verifier closeout state.

Legacy-field policy is staged and deterministic:

- Phases 1-5: ignore deleted model-authored state fields, execute valid tool
  calls if present, and write a debug event classified as
  `legacy_projection_field_ignored`. The ignored field is never merged into
  sidecar state and never affects `WorkFrame`.
- Phase 6 close and later: hard-reject deleted model-authored state fields as an
  invalid model payload before tool execution. The failure is classified as
  `legacy_projection_field_rejected`.
- At all phases, prompt rendering must not ask for those fields. Seeing them is
  a model-output compatibility observation, not a supported contract.

## Collapse Map

| Existing surface | New treatment |
|---|---|
| `frontier_state_update` model output | Delete from prompt and response schema. The model does not author frontier. Legacy appearances become debug failures, not state. |
| `lane_hard_runtime_frontier` | Replace live model-visible use with reducer-derived `latest_actionable`, `required_next`, `forbidden_next`, `changed_sources`, and `verifier_state`. Keep only event-level sidecar facts needed for replay/debug. |
| `active_work_todo` | Delete from `implement_v2` model prompt and live next-action authority. Replace with `current_phase` and `required_next`. Human/work-session resume may render a sidecar summary, but it is not the model hot path. |
| first-write/prewrite readiness | Sidecar fact feeding `changed_sources`, `current_phase=prewrite_blocked`, `required_next`, and `forbidden_next`. No separate prompt card. |
| write repair lock | Sidecar gate feeding `current_phase=repair_after_write_failure` and `forbidden_next`. The model sees only the current failed write fact and required repair class. |
| typed evidence | Canonical sidecar source of truth. `WorkFrame` includes ids and missing obligations only. Full typed events stay in evidence artifacts. |
| oracle bundle | Sidecar only. `finish_readiness.required_evidence_refs` may name oracle obligation ids. |
| execution contract | Normalized sidecar only for command evidence and verifier safety. Cheap probes use command intent; verifier/finish commands may be referenced by compact ids. |
| latest failure projection | Reducer-owned `latest_actionable`. Historical same-family failures are replaced unless still independently unresolved. |
| final verifier closeout | Deterministic controller sidecar action. `WorkFrame.verifier_state` and `required_next` can request it; the model does not author closeout state. |
| finish gate continuation prompt | Replace with `WorkFrame.finish_readiness` and `current_phase=finish_blocked`. One blocked obligation summary, no proof object dump. |
| repair history | Sidecar/debug only. The reducer may surface one current no-repeat warning through `forbidden_next` when justified by current evidence. |

## Evidence Ref Dereferencing

`evidence_refs` are compact handles, not hidden prompt expansion.

Each ref in `evidence_ref_index.json` has:

- `id`;
- `kind`: `typed_evidence`, `command_output`, `write_provenance`,
  `execution_contract`, `oracle_obligation`, `finish_gate`, `replay_event`, or
  `debug_trace`;
- `visibility`: `model_visible_summary`, `model_fetchable`, or `replay_only`;
- `summary`: bounded text already counted in `WorkFrame` when model-visible;
- `fetch_tool`: optional existing tool name, such as `read_command_output`;
- `max_fetch_bytes`;
- `sidecar_path` or replay artifact path for debug/replay use.

Model contract:

- The model may cite any `evidence_refs` id in `finish.evidence_refs`.
- The model may fetch only refs marked `model_fetchable`, and only through the
  listed existing tool. No new generic evidence-ref fetch tool is introduced by
  this design.
- `command_output` refs may be model-fetchable through `read_command_output`
  when the reducer says more output is the required or allowed next action.
- Typed evidence, oracle, proof-manifest, finish-gate, and debug-trace refs are
  normally `replay_only`. The reducer must expose the small obligation summary
  needed for the next model action inside `WorkFrame`.
- Automatic prompt expansion is limited to the bounded `summary` already inside
  `WorkFrame`. Full dereferenced payloads are never auto-expanded into the
  ordinary prompt.

Size and growth alignment:

- The count and bounded summaries of model-visible refs count against the
  WorkFrame byte cap.
- Fetchable output bytes count against provider-visible tool-result metrics.
- Replay-only sidecar payloads count against sidecar size/growth metrics.
- If the model needs hidden replay-only detail to make progress, the reducer is
  under-specified; the fix is a better bounded WorkFrame summary or an explicit
  `model_fetchable` command-output ref, not prompt-dumping the sidecar.

Invalid or stale refs block finish through `finish_readiness` and the typed
evidence gate.

## Context Compression And Reentry

Context compression, wall timeout, interruption, and blocked-finish resume must
not reintroduce a second recovery card. Reentry uses the same reducer and renders
exactly one resumed `WorkFrame`.

Durable sidecar inputs:

- `workframe_cursor.json`: attempt id, latest durable `event_sequence`,
  previous_workframe_hash, reducer schema version, canonicalizer version,
  evidence_ref_index hash, and sidecar manifest path;
- sidecar event log up to the cursor sequence;
- provider transcript/tool-result cursor for the bounded resumed transcript
  tail;
- command/run cursor for any active, yielded, interrupted, or closeout command;
- write provenance cursor for latest source mutation and changed paths;
- typed evidence/oracle cursor for current obligations and known evidence ids;
- finish gate cursor for last blocked or allowed decision;
- budget cursor with normalized semantic budget class;
- optional debug-only prior WorkFrame for diff display, never as reducer
  authority.

Resumed prompt shape:

1. Static instructions.
2. Bounded transcript/tool-result tail selected by cursor.
3. Exactly one `implement_v2_workframe` section produced from sidecar events.

No separate recovery card, frontier summary, active todo, or finish-continuation
prompt is rendered on reentry. If recovery facts matter, they appear as
`current_phase`, `latest_actionable`, `required_next`, `forbidden_next`,
`verifier_state`, and `finish_readiness` fields in the resumed WorkFrame.

Reentry invariants:

- With no new semantic sidecar event after compression, resumed
  `required_next`, `forbidden_next`, `latest_actionable`, `changed_sources`,
  `verifier_state`, and `finish_readiness` match the pre-compression WorkFrame
  exactly.
- A pure resume marker, prompt compaction marker, or debug note is not semantic
  evidence and cannot change `required_next` or `forbidden_next`.
- A budget-class change, command terminalization, user interruption, or new tool
  result may change the WorkFrame, but `workframe_diff.json` must cite that new
  event.
- Evidence refs in the resumed WorkFrame resolve through the resumed
  `evidence_ref_index.json`.
- The resumed prompt still has exactly one dynamic state object.
- If the pre-compression frame forbade finish, the resumed frame forbids finish
  until a later passing verifier/evidence event changes that fact.

Fastchecks:

- compression fixture recomputes pre- and post-compression WorkFrame hashes;
- resume fixture asserts `required_next` and `forbidden_next` preservation when
  no semantic event changed;
- interruption fixture asserts active command state becomes
  `latest_actionable` or `blocked`, not a frontier card;
- blocked-finish fixture asserts `finish_readiness` and missing obligations
  survive resume;
- prompt leak check runs on resumed prompt;
- micro next-action check runs against at least one resumed WorkFrame fixture.

Replay tests:

- context compression with no new events;
- wall timeout before next model turn;
- yielded/interrupted command resume;
- blocked finish after invalid evidence refs;
- low-budget final verifier closeout after latest source mutation.

## Observability

Precise debugging is a mandatory part of the redesign. A failed WorkFrame turn
must be diagnosable without spending another 10 minute Harbor run.

Each turn writes a debug bundle under the attempt artifact directory:

```text
implement_v2/workframes/
  turn-0007/
    reducer_inputs.json
    reducer_output.workframe.json
    reducer_trace.jsonl
    invariant_report.json
    prompt_render_inventory.json
    prompt_visible_workframe.json
    workframe_diff.json
    evidence_ref_index.json
    workframe_cursor.json
    failure_taxonomy.json
```

Required trace ids:

- `attempt_trace_id`;
- `turn_id`;
- `workframe_id`;
- `reducer_trace_id`;
- `provider_call_id` for each model/tool call;
- `command_run_id` for exec evidence;
- `write_provenance_id` for source mutations;
- `typed_evidence_id` for finish/verifier facts;
- `input_hash`;
- `output_hash`;
- `previous_workframe_hash`;
- `prompt_render_hash`.

Required debug metrics:

- frame byte size;
- full normal prompt bytes;
- provider-visible tool-result bytes;
- sidecar total bytes and per-turn growth;
- number of evidence refs in frame;
- number of forbidden actions;
- latest-actionable family;
- whether `required_next` changed from the previous frame;
- whether the model followed the prior `required_next` category;
- whether any legacy prompt/output key leaked;
- whether this turn is fresh, compressed, resumed, interrupted, or closeout.

Per-turn diffing:

- `workframe_diff.json` records added/removed/changed fields against the previous
  frame.
- Diff is for observability only; the reducer must be deterministic without
  reading the diff.
- Repeated flip-flop of `current_phase`, `required_next.kind`, or
  `finish_readiness.state` without new sidecar evidence is a red invariant.

Replay determinism:

- Replay recomputes every `WorkFrame` from saved sidecar events.
- `reducer_inputs.json` and `reducer_output.workframe.json` hashes must match.
- A deterministic replay mismatch fails fastcheck before live diagnostics.
- New artifacts are WorkFrame-native. Old artifacts can be one-time converted
  into fixture sidecar facts for tests, but the live runtime should not carry a
  legacy projection adapter.

## Invariants

Hard invariants:

- Ordinary prompt has exactly one `implement_v2_workframe` dynamic state section.
- Ordinary prompt contains no `frontier_state_update`, `active_work_todo`,
  `lane_hard_runtime_frontier`, full proof manifest, full oracle bundle, or full
  typed evidence object.
- Model output containing `frontier_state_update` is not consumed as state.
- Every `evidence_refs` id resolves to a typed evidence event, sidecar record, or
  replay record.
- Replay-only evidence refs are not model-fetchable, and fetchable refs name an
  existing tool plus byte cap.
- `required_next` must cite a reducer reason and at least one source fact.
- `required_next` cannot persist unchanged across turns unless no new sidecar
  fact has arrived or the previous action was blocked before execution.
- Compression or resume cannot change `required_next` or `forbidden_next`
  without a new semantic sidecar event.
- `finish_readiness.state=ready` requires passing required obligations after
  the latest source mutation.
- If `changed_sources.since_last_strict_verifier=true`, `finish` is in
  `forbidden_next` unless the task is explicitly no-change/investigation-only.
- If a write failed, later same-turn verifier calls are skipped or marked
  invalid, and the next frame is `repair_after_write_failure`.
- Cheap probe failures are not promoted to artifact proof failures.
- A missing configured final verifier after latest source mutation produces
  `verifier_state.budget_closeout_required=true` or `required_next.kind=run_verifier`.
- `WorkFrame` size and sidecar growth remain inside phase caps.
- Same input hash produces same output hash.

Soft invariants:

- Latest actionable summary should contain a concrete diagnostic when available,
  not only `exit code 1`, `killed`, or `failed`.
- `forbidden_next` should block broad rediscovery after a concrete verifier
  failure unless new evidence invalidates the target.
- `current_phase` should advance toward patch/edit, verifier, or finish within
  two successful model turns after a concrete latest-actionable failure.

## Failure Taxonomy

Fastchecks, replay, and artifacts classify WorkFrame failures into these generic
families:

- `prompt_legacy_projection_leak`: old frontier/todo/evidence state reached the
  ordinary prompt.
- `legacy_projection_field_ignored`: early-phase model output contained a
  deleted state field that was ignored with debug evidence.
- `legacy_projection_field_rejected`: Phase 6 or later model output contained a
  deleted state field and was hard-rejected.
- `reducer_input_missing`: required sidecar input is absent or corrupt.
- `reducer_nondeterministic`: same inputs do not reproduce the same frame hash.
- `canonical_fixture_hash_mismatch`: saved fixture does not recompute to the
  stored canonical input hash.
- `evidence_ref_unresolved`: frame references missing sidecar/typed evidence.
- `evidence_ref_stale`: frame uses evidence before the latest source mutation as
  fresh proof.
- `evidence_ref_not_model_fetchable`: model attempted to fetch a replay-only
  ref.
- `evidence_ref_overexpanded`: prompt auto-expanded ref payload beyond the
  bounded WorkFrame summary.
- `reentry_required_next_drift`: resume changed required_next without a new
  semantic sidecar event.
- `reentry_forbidden_next_drift`: resume changed forbidden_next without a new
  semantic sidecar event.
- `latest_actionable_generic`: latest failure is only a generic status despite
  actionable output being available.
- `required_next_unjustified`: required action has no cited sidecar basis.
- `required_next_stale`: required action persists after contradictory new
  evidence.
- `forbidden_next_missing`: finish, broad rediscovery, stale verifier, or
  source mutation should have been blocked but was not.
- `finish_false_positive`: frame says finish-ready but legacy or typed safety
  gates would block.
- `finish_false_negative`: frame blocks finish despite all required evidence
  being fresh and passing.
- `verifier_stale_after_mutation`: changed source lacks a later strict verifier.
- `closeout_not_scheduled`: low budget plus stale verifier did not produce a
  controller closeout or required verifier action.
- `workframe_size_over_cap`: model-visible frame exceeds cap.
- `sidecar_growth_red`: prompt shrank by hiding unbounded sidecar complexity.
- `micro_next_action_invalid`: model category response does not follow the
  frame.
- `task_specific_heuristic`: reducer or prompt encodes a task-specific solver.

Each taxonomy record includes the trace ids, reducer input hashes, the invariant
that failed, and the first suggested local detector to update.

## Phase 0 Baseline Bands

Phase 0 records the baseline values used by calibration and close gates. Where
the May 8 HOT_PATH_COLLAPSE design already defined a band, this redesign
inherits it exactly. Where WorkFrame introduces a new metric, this document
defines the band here.

Required Phase 0 baseline fields:

- `B_prompt_normal_total`;
- `B_prompt_dynamic_hot_path`;
- `B_tool_result_p95`;
- `B_sidecar_total`;
- `B_sidecar_per_turn_growth`;
- `B_first_edit_turn`;
- `B_first_edit_seconds`;
- `B_first_verifier_turn`;
- `B_first_verifier_seconds`;
- `B_model_turns_10m`;
- `B_tool_calls_10m`;
- `B_same_family_repeats_10m`;
- `B_required_next_adherence`;
- `B_workframe_bytes`.

Bands:

| Metric | Green | Yellow | Red |
|---|---:|---:|---:|
| Normal full prompt bytes | `<= 70% * B_prompt_normal_total` | `> 70%` and `<= 80%` | `> 80%` |
| Dynamic hot-path prompt bytes | `<= 45% * B_prompt_dynamic_hot_path` | `> 45%` and `<= 60%` | `> 60%` |
| Provider-visible tool-result p95 bytes | `<= 40% * B_tool_result_p95` | `> 40%` and `<= 55%` | `> 55%` |
| Sidecar total bytes | `<= 110% * B_sidecar_total` | `> 110%` and `<= 125%` | `> 125%` |
| Sidecar per-turn growth | `<= 110% * B_sidecar_per_turn_growth` | `> 110%` and `<= 150%` | `> 150%` |
| First edit turn | `<= 75% * B_first_edit_turn` | `> 75%` and `<= 100%` | `> 100%` |
| First edit seconds | `<= 75% * B_first_edit_seconds` | `> 75%` and `<= 100%` | `> 100%` |
| First strict verifier turn | `<= 90% * B_first_verifier_turn` | `> 90%` and `<= 110%` | `> 110%` |
| First strict verifier seconds | `<= 90% * B_first_verifier_seconds` | `> 90%` and `<= 110%` | `> 110%` |
| Model turns in 10 minute diagnostic | `<= 90% * B_model_turns_10m` | `> 90%` and `<= 100%` | `> 100%` |
| Tool calls in 10 minute diagnostic | `<= 100% * B_tool_calls_10m` | `> 100%` and `<= 115%` | `> 115%` |
| Repeated same-family failures | `<= 50% * B_same_family_repeats_10m` and `<= 1` unresolved repeat per family | `<= B_same_family_repeats_10m` and `<= 2` only with new evidence between repeats | `> B_same_family_repeats_10m` or `>= 3` unresolved repeats |
| Required-next adherence | `>= 90%` of model next-action categories follow `required_next` or an allowed equivalent, with no forbidden action | `>= 75%` and `< 90%`, with no forbidden action | `< 75%` or any forbidden action |
| WorkFrame bytes | `<= 4096` | `> 4096` and `<= 6144` | `> 6144` |

Close-gate rule:

- A red band blocks close.
- Yellow requires a written tradeoff and must not involve prompt leaks, safety
  regressions, nondeterminism, stale evidence, or task-specific heuristics.
- Missing Phase 0 baseline values block same-shape calibration. Do not silently
  substitute a default except for the absolute WorkFrame byte cap above.

## Phase Plan

### Phase 0: Baseline And WorkFrame Schema

Implementation target:

- define `WorkFrame`, `WorkFrameInputs`, `WorkFrameTrace`, and invariant report
  schema;
- add fixture-only reducer over saved sidecar facts;
- add prompt inventory checks proving the current legacy projections are still
  present before cutover.

Close gate:

- schema reviewed;
- reducer fixture deterministic;
- debug bundle format documented;
- baseline metrics recorded for prompt bytes, tool-result bytes, sidecar bytes,
  first edit, first verifier, model turns, tool calls, same-family repeats, and
  WorkFrame size;
- every calibration metric has a green/yellow/red band from the Phase 0
  Baseline Bands table or explicitly blocks progression until one is added;
- canonical fixture recomputation passes on current head;
- no live benchmark.

### Phase 1: Prompt Cutover To One Dynamic State Object

Implementation target:

- replace ordinary dynamic cards with `implement_v2_workframe`;
- delete `frontier_state_update` from ordinary response schema;
- remove model-visible `active_work_todo`, hard-runtime frontier, and repair
  history sections from `implement_v2`;
- preserve static tool rhythm and paired tool-result protocol.

Close gate:

- prompt leak tests pass;
- fake-provider tests prove legacy model fields are not consumed;
- deleted legacy state fields are ignored with `legacy_projection_field_ignored`
  debug events during this early phase and do not affect WorkFrame;
- normal prompt has exactly one dynamic state object;
- old projection tests are rewritten to WorkFrame invariants, not compatibility.

### Phase 2: Reducer-Owned Latest Actionable And Next Action

Implementation target:

- move latest-failure projection into the WorkFrame reducer;
- compute `required_next` and `forbidden_next` from latest tool result,
  write/verifier provenance, typed evidence obligations, and budgets;
- replace historical same-family failure accumulation with current unresolved
  family state.

Close gate:

- command-not-found, generic nonzero, killed/no-output, runtime diagnostic,
  artifact miss, write failure, and verifier pass fixtures all reduce to the
  expected generic category;
- `latest_actionable_generic` fastcheck catches bad summaries;
- micro next-action fixtures pass category checks.

### Phase 3: Sidecar Evidence And Execution Contracts

Implementation target:

- keep normalized execution contracts and typed evidence as sidecar records;
- reduce model-visible evidence to refs and missing obligations;
- infer cheap probe versus diagnostic/build/runtime/verify/finish-verifier
  intent in the sidecar;
- reject model-authored proof obligations for cheap probes.

Close gate:

- typed evidence resolver tests pass;
- cheap probes cannot satisfy finish proof;
- strict verifier commands still produce typed evidence and finish-gate facts;
- no full execution-contract object appears in normal prompt.

### Phase 4: Mutation And Verifier Boundary

Implementation target:

- make write/edit/apply_patch provenance the source mutation boundary;
- record shell-source side effects as sidecar facts when detected;
- compute `changed_sources` and verifier freshness in the reducer;
- block stale verifier/finish behavior through `forbidden_next`.

Close gate:

- failed writes project `repair_after_write_failure`;
- source mutation without later strict verifier projects
  `verify_after_mutation`;
- variable-indirected shell source patch fixtures are represented as sidecar
  mutation facts or blocked by policy;
- no stale-code verifier/finish acceptance.

### Phase 5: Finish And Deterministic Closeout

Implementation target:

- collapse finish-gate continuation into `finish_readiness`;
- keep final verifier closeout as deterministic controller action;
- represent closeout need in `verifier_state` and `required_next`;
- require finish to cite `evidence_refs`.

Close gate:

- finish-ready requires passing fresh typed or legacy-equivalent evidence;
- finish-blocked frame names only missing obligations and refs;
- low-budget latest-source-mutation fixtures schedule closeout or require
  configured verifier;
- no proof/oracle object dump in prompt.

### Phase 6: Replay, Dogfood, Fastcheck, And Same-Shape Calibration

Implementation target:

- extend `scripts/check_implement_v2_hot_path.py` or equivalent to validate
  WorkFrame-native artifacts;
- replay saved artifacts through the reducer;
- run dogfood/emulator coverage for the affected generic failure shape;
- run one same-shape step diagnostic only after fastchecks pass.

Close gate:

- focused UT pass;
- exact saved-artifact replay passes WorkFrame hash checks;
- prompt leak, sidecar growth, latest-actionable, invariant, and micro
  next-action checks pass;
- deleted legacy state fields are now hard-rejected as
  `legacy_projection_field_rejected`;
- reentry fixtures preserve `required_next` and `forbidden_next` across
  compression/resume when no semantic event changed;
- dogfood and relevant emulator pass;
- one same-shape `step-check-10min` is green or yellow against Phase 0 bands and
  shows the intended loop shape.

## Fastcheck Requirements

The fast inner loop must run before any same-shape 10 minute diagnostic:

1. Focused unit tests for touched reducer/prompt/evidence/exec/write surface.
2. Saved-artifact replay through the WorkFrame reducer.
3. Prompt leak check:
   - exactly one `implement_v2_workframe` dynamic state section;
   - no normal prompt `frontier_state_update`;
   - no normal prompt `active_work_todo`;
   - no full proof/oracle/typed-evidence/execution-contract object.
4. Canonical input recomputation check:
   - stored reducer input hash matches canonicalized fixture input;
   - schema versions are present in the hash envelope;
   - line endings and path roots normalize identically on the current machine.
5. Reducer invariant check.
6. Sidecar growth and frame-size check.
7. Evidence-ref dereference policy check:
   - replay-only refs are not fetchable by the model;
   - fetchable refs name an existing tool and byte cap;
   - prompt auto-expansion stays inside the WorkFrame summary cap.
8. Reentry check when a compression/resume fixture exists:
   - resumed prompt has one WorkFrame section;
   - `required_next` and `forbidden_next` are preserved when no semantic event
     changed.
9. Latest-actionable shape check.
10. Hash-bound micro next-action check.

Micro next-action check:

- uses a saved intermediate WorkFrame fixture and transcript/tool-result tail;
- hashes prompt, WorkFrame, projection, and expected category set;
- asks the model only for the next action category;
- valid categories are `cheap_probe`, `inspect_latest_failure`, `patch/edit`,
  `run_verifier`, `finish_with_evidence`, `blocked`, and `invalid`;
- asserts category, not exact command text;
- refreshes with one bounded live `auth.json` call only when the fixture is
  missing or stale;
- fails if the expected category encodes a task-specific exact path, opcode,
  syscall, or verifier command not present in the task contract or sidecar
  evidence.

## Same-Shape Calibration Plan

Calibration remains same-shape and generic:

1. Recompute WorkFrame sequences for saved `make-mips-interpreter` artifacts
   from the active M6.24 rows, including the recent prewrite, runtime
   diagnostic, killed/no-output, finish-alias, and final-verifier-closeout
   shapes.
2. Recompute WorkFrame sequences for the passing `build-cython-ext` v2 artifact
   to verify the redesign does not regress a known good coding task shape.
3. Compare against Phase 0 bands:
   - normal prompt bytes;
   - provider-visible tool-result bytes;
   - sidecar bytes and growth;
   - first edit turn/seconds;
   - first strict verifier turn/seconds;
   - model turns and tool calls;
   - repeated same-family failures;
   - required-next adherence.
4. Run micro next-action checks on at least:
   - before first source mutation;
   - after first source mutation before verifier;
   - after concrete verifier failure;
   - after finish-blocked evidence;
   - low-budget closeout after latest mutation.
5. Only after all fastchecks pass, run exactly one same-shape
   `make-mips-interpreter` `step-check-10min`.
6. Classify step shape before any `speed_1` or `proof_5`:
   - green: smaller prompt/tool-result surface, no repeated same-family loop,
     earlier or equal patch/verifier, and no safety regression;
   - yellow: safety intact and no legacy projection leak, but one metric is
     neutral or slightly worse with written reason;
   - red: prompt leak, nondeterminism, stale verifier, repeated frontier-like
     loops, delayed first edit/verifier, or task-specific behavior.

The calibration may use `make-mips-interpreter` as the current same-shape
artifact family because M6.24 is already using it for hot-path evidence. The
reducer and checks must remain task-family generic.

## Migration Plan

No backward compatibility constraints apply to live `implement_v2` projections.

Delete:

- normal prompt `implement_v2_active_work_todo`;
- normal prompt `implement_v2_hard_runtime_frontier_state`;
- normal prompt `implement_v2_repair_history`;
- normal response `frontier_state_update`, with Phases 1-5 ignoring old
  model-authored fields only as debug-observed no-ops and Phase 6 hard-rejecting
  them;
- model-visible proof/oracle/typed-evidence object dumps;
- detailed execution-contract instructions for cheap probes;
- live `implement_v2` authority that reads old active todo/frontier fields.

Keep as sidecar:

- full transcript and provider call/result pairing;
- managed exec records and output refs;
- normalized execution contracts;
- typed evidence and oracle obligations;
- write provenance and source mutation records;
- final verifier closeout records;
- proof manifests and replay history;
- human/debug summaries outside ordinary model prompt.

Replace:

- `active_work_todo` with `WorkFrame.current_phase`, `required_next`, and
  `forbidden_next`;
- hard-runtime frontier prompt with reducer facts inside `latest_actionable`,
  `changed_sources`, and `verifier_state`;
- finish continuation prose with `finish_readiness`;
- scattered prompt metrics with WorkFrame-specific prompt/render/reducer
  metrics;
- legacy fastcheck prompt-leak checks with one-WorkFrame invariants.

Saved legacy artifacts:

- may be converted into WorkFrame fixture inputs for regression tests;
- should not force the live runtime to preserve old projection schemas;
- remain useful as evidence only if replay records the conversion hash and the
  resulting WorkFrame sequence.

## Why This Is Not Another Frontier

A frontier is durable planning state. The current system has accumulated several
frontier-like surfaces: model-authored frontier updates, active todos, repair
cards, hard-runtime frontier summaries, finish continuation prompts, and
execution-contract proof objects. Each can disagree with the others.

`WorkFrame` is a reducer output, not a new planner:

- it is recomputed from canonical sidecar events every turn;
- it is discarded and replayed by hash;
- the model cannot edit it;
- it has a closed schema;
- it replaces old dynamic projections instead of being added beside them;
- it carries refs, not full proof state;
- it owns both required and forbidden next actions so safety and next-step
  guidance cannot split across different cards.

This reduces conceptual surface because debugging moves from "which projection
lied?" to "which reducer input or invariant produced this WorkFrame field?"

## Tests

Unit tests:

- WorkFrame schema and serialization caps;
- canonical input serialization, schema-version hash envelope, volatile-field
  exclusion, path normalization, and line-ending normalization;
- reducer determinism and hash stability;
- reducer input normalization for tool calls/results, writes, exec records,
  typed evidence, finish gate, and final verifier closeout;
- current phase transitions;
- latest actionable family selection;
- required/forbidden next derivation;
- evidence ref resolution;
- evidence ref dereference policy for `model_visible_summary`,
  `model_fetchable`, and `replay_only`;
- prompt has exactly one dynamic state object;
- legacy prompt/output fields are absent or classified as invalid;
- staged legacy-field policy ignores with debug events before close and
  hard-rejects at Phase 6 close;
- cheap probe failures stay non-proof;
- stale verifier after source mutation blocks finish;
- finish-ready cannot bypass legacy safety gates;
- WorkFrame diff and invariant reports are written.

Replay tests:

- saved `make-mips-interpreter` failed shapes from recent M6.24 rows;
- saved passing `build-cython-ext` v2 artifact;
- write failure and same-turn skipped verifier fixture;
- final verifier closeout fixture;
- finish-blocked typed evidence alias fixture.
- context compression, wall timeout, interruption, and blocked-finish resume
  fixtures preserving `required_next` and `forbidden_next` when no semantic
  event changed.

Fastcheck tests:

- prompt leak;
- canonical fixture recomputation across machines;
- sidecar growth;
- frame size;
- evidence ref dereference policy and over-expansion rejection;
- context compression/reentry preservation;
- latest actionable generic-summary rejection;
- unresolved evidence ref rejection;
- nondeterminism rejection;
- micro next-action fixture reuse and stale-fixture refresh path.

Dogfood/emulator:

- `m6_24-terminal-bench-replay` with explicit WorkFrame assertions;
- runtime finish-gate emulator;
- hard-runtime/source-mutation emulator only when the generic failure shape needs
  it;
- no emulator may encode a task-specific MIPS/VM solution.

## Overall Close Gate

The WorkFrame redesign is closeable only when:

1. Ordinary `implement_v2` prompt has exactly one dynamic state object:
   `WorkFrame`.
2. Model output cannot update frontier/todo/proof state.
3. Full detail remains in typed evidence, sidecars, and replay artifacts.
4. Reducer inputs, outputs, trace ids, invariant reports, and diffs are written
   for every turn.
5. Canonical reducer input hashes recompute from fixtures across machines.
6. Replay recomputes WorkFrame hashes deterministically.
7. Context compression and reentry render one resumed WorkFrame and preserve
   `required_next`/`forbidden_next` when no semantic event changed.
8. Evidence refs have explicit dereference policy and never auto-expand beyond
   WorkFrame caps.
9. Phase 6 hard-rejects deleted legacy state fields instead of consuming them.
10. Fastcheck catches prompt leaks, stale evidence refs, generic latest failures,
   sidecar growth, and bad micro next-action categories before Harbor.
11. Finish safety is equivalent or stricter than current gates.
12. Same-shape calibration is green or accepted yellow.
13. The design has not introduced MIPS/VM/task-specific solver rules.
14. `ROADMAP_STATUS.md` can mark the HOT_PATH_COLLAPSE phase as closed with
    links to WorkFrame-native evidence, not just a benchmark score.

Do not close if:

- any old frontier/todo/evidence projection remains in the ordinary prompt;
- a new dynamic model-visible state object appears beside `WorkFrame`;
- required-next state persists without current sidecar justification;
- final verifier freshness can be stale after source mutation;
- WorkFrame replay is nondeterministic;
- context compression or resume changes required/forbidden next without a new
  semantic sidecar event;
- the model needs replay-only evidence details that are not summarized or
  fetchable by contract;
- a bug is first diagnosable only by rerunning a 10 minute Harbor job.

## Reviewer Acceptance Criteria

Reviewers should accept this design if they agree that:

- no backward compatibility is needed for old `implement_v2` model-visible
  projections;
- the only ordinary dynamic model state should be one reducer-produced
  `WorkFrame`;
- typed evidence, execution contracts, proof manifests, and verifier closeout
  remain sidecar/replay facts;
- observability is sufficient to debug a bad next action from reducer artifacts;
- context compression and reentry preserve WorkFrame state without adding a
  second recovery surface;
- reducer input canonicalization and evidence-ref dereferencing are deterministic
  enough for replay;
- the phase and fastcheck gates can prevent another loop of frontier/todo/
  evidence/contract boundary repairs;
- the proposal is generic to coding-loop substrate and explicitly avoids
  task-specific MIPS/VM heuristics.
