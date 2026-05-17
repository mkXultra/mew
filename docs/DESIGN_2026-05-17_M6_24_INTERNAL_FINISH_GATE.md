# Design 2026-05-17 - M6.24 Internal Finish Gate

Status: design only.

Scope: remove the provider-visible `finish` tool from the `implement_v2`
main-model agentic loop and run a mew-internal finish gate after the main model
produces a normal final response. This document does not authorize code changes
by itself.

## Decision

`implement_v2` should stop making the main model call a provider-visible
`finish` tool. The Codex-like hot path is:

```text
main model agent loop
  -> provider-native tool calls / edits / tests
  -> model emits normal final response
  -> controller records a done candidate
  -> mew-internal finish gate runs
  -> OK: lane completed
  -> NG continue: agentic loop resumes with an abstract failure signal
  -> NG return: lane stops blocked for supervisor/budget/safety
```

The main model must not learn mew's finish schema, `task_contract` gate shape,
`evidence_refs` bookkeeping, `NativeFinishGateDecision`, or resolver JSON. It
should only see ordinary coding instructions, ordinary provider-native tools,
ordinary tool results, and, on NG continue, a bounded repair signal whose
transport is intentionally abstract.

No backward compatibility requirement applies. This is pre-release and may be a
flag-day migration for production `implement_v2`.

## Current Repo Facts

Relevant existing docs:

- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
  defines `response_transcript.json` as source of truth for the provider-native
  loop.
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`
  separates provider-native finish protocol from semantic lane completion and
  assigns completion authority to resolver/gate sidecars.
- `docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_AFFORDANCE_COLLAPSE.md` defines the
  hot-path rule: provider-visible state is limited and WorkFrame/proof/evidence
  stay sidecar-first.
- `docs/DESIGN_2026-05-15_M6_24_HOT_PATH_OBSERVABILITY.md` keeps hot-path
  measurement artifact-only and forbids observability code from changing live
  behavior.
- `docs/DESIGN_2026-05-15_M6_24_FINISH_VERIFIER_PLANNER.md` defines a separate
  finish-time verifier planner that selects a verifier command but never
  accepts completion.
- This design amends and supersedes the finish-trigger/keying parts of
  `docs/DESIGN_2026-05-15_M6_24_FINISH_VERIFIER_PLANNER.md` and any 2026-05-16
  planner follow-up that keys planner launch or records by `finish_call_id`.
  New production planner trigger/keying is `done_candidate_id`; `finish_call_id`
  is legacy replay/quarantine vocabulary only.

Relevant implementation files discovered by inspection:

- Native runtime entry and harness: `src/mew/implement_lane/native_tool_harness.py`
  exposes `run_live_native_implement_v2()` and `run_native_implement_v2()`.
- Production command route: `src/mew/commands.py` imports and calls
  `run_live_native_implement_v2`.
- Native transcript source of truth:
  `src/mew/implement_lane/native_transcript.py`; runtime id is
  `IMPLEMENT_V2_NATIVE_RUNTIME_ID = "implement_v2_native_transcript_loop"`.
- Provider request and stream adapter:
  `src/mew/implement_lane/native_provider_adapter.py`.
- Provider-visible tool surface:
  `src/mew/implement_lane/tool_policy.py` still includes `finish` in
  `V2_BASE_TOOL_SPECS`.
- Codex-like tool-surface assembly:
  `src/mew/implement_lane/tool_registry.py` currently routes finish access and
  includes `legacy_by_name["finish"]`; `src/mew/implement_lane/tool_routes.py`
  has a canonical `"finish"` route; `src/mew/implement_lane/tool_result_renderer.py`
  has `CODEX_FINISH_RENDERER_ID` and `_render_codex_finish()`.
- Responses schema lowering:
  `src/mew/implement_lane/native_tool_schema.py` still defines a strict
  `finish` schema with `summary`, `evidence_refs`, and `final_status`.
- Native finish gate contracts:
  `src/mew/implement_lane/native_finish_gate.py`; existing decision file is
  `native_finish_gate_decisions.jsonl`.
- Semantic resolver:
  `src/mew/implement_lane/completion_resolver.py`; existing decision file is
  `resolver_decisions.jsonl`.
- Finish verifier planner and native closeout wiring:
  `src/mew/implement_lane/native_tool_harness.py`, especially the
  `_run_native_finish_time_closeouts()` and planner-decision artifact paths.
- Hot-path replay checks:
  `src/mew/implement_lane/hot_path_fastcheck.py`.
- Artifact-only step-shape analyzer:
  `src/mew/implement_lane/hot_path_step_diff.py`.
- Native boundary audit:
  `src/mew/implement_lane/native_boundary_audit.py` still has finish-call keyed
  anchors such as `finish_call_resolver_completion`.
- Compact sidecar projection:
  `src/mew/implement_lane/native_sidecar_projection.py` currently derives
  `finish_status`, `finish_readiness_state`, and
  `finish_required_evidence_refs` from finish calls / WorkFrame readiness.
- Legacy model-JSON path:
  `src/mew/implement_lane/v2_runtime.py` still has `run_live_json_implement_v2()`
  and a model-authored `finish` object. This is not the selected native command
  route, but it is a migration and test surface.

Ambiguity: `native_tool_harness.py` currently contains both protocol handling
for provider-native `finish_call` and internal controller final-verifier
closeout behavior. A later implementation should split "provider-visible
finish tool" from "internal done-candidate finish gate" rather than renaming
the existing functions wholesale.

## Non-Goals

- No new model-visible finish schema.
- No model-visible `task_contract`, finish-gate decision JSON, resolver input,
  raw WorkFrame, raw proof manifest, or raw typed-evidence graph.
- No requirement to preserve legacy provider-visible `finish` behavior.
- No weakening of write approval, command lifecycle, verifier freshness, proof
  manifest hashing, replay, or hot-path observability.
- No final choice of NG resume transport. It may later be a user-role natural
  language message, a provider tool-result-like item, or another internal input
  item. This design only defines the insertion point and abstract interface.

## Provider-Visible Finish Removal

Production native `implement_v2` should remove `finish` from the model-visible
tool surface:

- Delete or production-gate the `finish` entry in
  `src/mew/implement_lane/tool_policy.py`.
- Remove `finish` from `list_v2_tool_specs_for_mode()` results for all
  production native modes.
- Remove `ToolAccess="finish"` from production surface assembly. If the type
  literal remains, it is for legacy replay/quarantine only and must not be
  accepted by production `build_tool_surface_snapshot()`.
- Remove finish from Codex hot-path tool registry, route table, and provider
  output rendering in `tool_registry.py`, `tool_routes.py`, and
  `tool_result_renderer.py`. Any finish route/renderer that remains must be
  unreachable from production native request construction and explicitly named
  legacy/replay.
- Delete or quarantine the provider-visible strict schema in
  `src/mew/implement_lane/native_tool_schema.py`.
- Stop treating provider stream items named `finish` as production completion
  protocol in `src/mew/implement_lane/native_provider_adapter.py`.
- Keep historical `finish_call` / `finish_output` support only where needed for
  old artifact replay, explicit quarantine tests, or migration fixtures.

Internal downgrade is allowed. The names `NativeFinishGateDecision`,
`native_finish_gate_decisions.jsonl`, and `finish_verifier_planner_decisions.jsonl`
may remain as internal artifact vocabulary. They must not appear in the
provider request body, provider-visible tool list, tool descriptions, or hot
path compact sidecar digest.

## Done Candidate Detection

A done candidate is a controller-side state, not a provider tool call.

The detector runs after a provider response is fully parsed and all model-issued
tool calls from that response have either received paired outputs or been
synthetically cancelled by protocol rules.

Minimum conditions:

- provider response status is terminal for the turn;
- response contains no executable call items after normalization;
- response contains at least one assistant message suitable to expose as the
  model's final response;
- no managed command remains active without a closeout/poll/cancel decision;
- no write approval or tool protocol error is pending in a state that requires
  supervisor return;
- model-turn and wall-clock budgets leave enough time for the internal finish
  gate, or the candidate becomes `blocked_return` for budget.

The detector must not parse a JSON `finish` object from assistant text. A final
answer that mentions tests, evidence, or "done" is still plain assistant text.
If the detector cannot decide whether assistant text is final or accidental
mid-loop prose, the conservative behavior is one ordinary continuation request
with no finish-gate schema. The cap is exactly one ambiguous no-tool
continuation per lane attempt. If the immediately following provider turn again
returns no executable call and assistant prose, record a `no_tool_repeat` done
candidate and run the internal gate; do not issue a second generic
continuation.

Suggested sidecar record:

```json
{
  "schema_version": 1,
  "done_candidate_id": "done-candidate:turn-7:response-...",
  "lane_attempt_id": "...",
  "turn_id": "turn-7",
  "assistant_message_item_ids": ["item-..."],
  "final_response_text_ref": "native-output://.../assistant-final",
  "transcript_hash_before_gate": "sha256:...",
  "compact_sidecar_digest_hash": "sha256:...",
  "detector_version": "native-done-candidate-v1"
}
```

The canonical done-candidate sidecar is `done_candidates.jsonl`. Each production
done candidate must have one row in that file, and `proof-manifest.json` must
record `done_candidates_ref`, `done_candidates_sha256`, and
`metrics.done_candidates`.

## Internal Finish Gate Launch Conditions

The internal finish gate launches exactly after a done candidate is recorded.
It is not launched while the model is still issuing tool calls.

Inputs:

- done candidate id and final response text ref;
- `response_transcript.json` hash and bounded transcript indexes;
- latest tool-result/evidence sidecars;
- latest source/artifact mutation summary;
- active command closeout status;
- configured verifier, auto-detected verifier, and finish verifier planner
  eligibility;
- internal task information, including `task_contract`, allowed roots, and
  acceptance constraints.

The internal gate may read `task_contract`; the main model must not. Any
projection from `task_contract` into a resume signal must be plain task-repair
language, not raw contract JSON or field names.

Gate-only inputs and planner-visible inputs are separate. The internal gate may
use hidden verifier/oracle state to decide OK/NG, but the
`finish_verifier_planner` must not receive hidden oracle knowledge as a shortcut.

Planner-visible inputs are limited to:

- raw user task text as originally provided to the main model;
- a configured verifier command only when it was explicitly supplied by the
  task/user/lane config, not inferred from hidden benchmark metadata;
- model-visible tool results and artifact refs, including bounded output text
  already available through normal tool rendering;
- transcript summaries that could be reconstructed from model-visible turns;
- safe internal runtime facts such as workspace root, allowed roots, remaining
  timeout budget, available command surface, latest visible mutation summary,
  and active command lifecycle state.

Planner-forbidden inputs:

- hidden external verifier failure details;
- hidden acceptance constraints or benchmark-only expected outputs;
- raw `task_contract` JSON;
- proof oracle constraints or unresolved oracle obligation records;
- private resolver/gate blocker JSON;
- any expected artifact/output that was not visible in the original user task,
  normal tool results, or model-visible artifacts.

If hidden external verifier state exists, the gate may use it internally to
block or return, but the planner request must carry only a generic visible
repair question. Example: "the visible verifier is not sufficient" may be
allowed as a controller-side NG reason; "hidden test expected output X" is not.

The gate should reuse or evolve existing contracts from
`src/mew/implement_lane/native_finish_gate.py`, but production request and
decision rows are keyed by `done_candidate_id`, not `finish_call_id`.
`native_finish_gate_decisions.jsonl` may keep its filename to reduce artifact
churn, but its production schema must have `done_candidate_id` as the primary
key. If the file is renamed, use `internal_finish_gate_decisions.jsonl` and
mirror the new ref/hash names in `proof-manifest.json`. `finish_call_id` may
appear only in legacy replay/quarantine rows.

## Finish Verifier Planner Connection

The finish verifier planner remains a separate command-selection helper.

Verifier precedence inside the internal finish gate:

1. Close or observe active managed commands.
2. `configured_verifier` is first authority when explicitly supplied and safe.
   If it proves the candidate, do not launch the planner for completion
   authority.
3. `finish_verifier_planner` is second authority when enabled and no configured
   verifier proves the candidate. Build its request only from the
   planner-visible input set above.
4. `auto_detected_verifier` is diagnostic-only by default. It may not silently
   become completion authority and may not silently replace a rejected planner
   command.
5. Auto-detected completion authority is allowed only behind an explicit named
   policy such as `allow_auto_detected_finish_verifier_fallback_v1`. When that
   policy is off, auto-detected commands may run only as diagnostic evidence and
   cannot convert NG to OK.

Planner execution order when selected:

1. Build the planner request from planner-visible facts only.
2. Run the planner in its separate session.
3. Validate the proposed command with the existing safety policy.
4. Execute the accepted command through normal `run_command` / `run_tests`
   runtime, producing ordinary typed evidence and transcript-linked refs.
5. Feed the closeout result into the internal gate decision.

If an auto-detected fallback policy is explicitly enabled, every fallback row
must record:

- policy name and version;
- reason fallback was considered;
- auto-detected source and source evidence;
- strength/confidence classification;
- whether the planner was unavailable, declined, or rejected;
- why fallback is allowed despite planner state;
- final fallback decision: diagnostic-only, executed-non-authoritative, or
  completion-authority.

An auto-detected verifier must never replace a rejected planner command without
that explicit policy and sidecar record. A planner rejection with no authorized
auto fallback remains NG/continue or NG/return.

Planner request, response, rejection, fallback, command dispatch, and command
result remain sidecar artifacts:

- `finish_verifier_planner_requests.jsonl`
- `finish_verifier_planner_decisions.jsonl`
- `native_finish_gate_decisions.jsonl` or successor
- `proof-manifest.json` hashes and metrics

Planner rows must use `done_candidate_id` as the production correlation key.
Legacy planner fields named `finish_call_id` may remain only when reading old
artifacts or quarantined fixtures; fastcheck must fail if a new production
planner row lacks `done_candidate_id`.

The main model never sees planner prompts, planner rationale, verifier command
selection reasons, or planner-specific blocker codes.

## Compact Digest Migration

`compact_sidecar_digest` keeps a small completion-state projection, but it must
not expose finish-tool or internal-gate schema.

Replacement fields:

- `done_candidate_status`: `none`, `candidate_recorded`, `gate_ok`,
  `gate_ng_continue`, `gate_ng_return`, or `repeat_plateau`.
- `done_candidate_ref`: a bounded ref to the `done_candidates.jsonl` row, not
  raw assistant text or gate JSON.
- `internal_gate_status`: `not_run`, `running`, `ok`, `ng_continue`,
  `ng_return`, or `skipped_budget`.
- `resume_signal_status`: `none`, `queued`, `delivered`, or `suppressed`.

Deprecated provider-visible fields:

- `finish_status` must be removed or rewritten to `done_candidate_status`.
- `finish_readiness_state` must be removed from provider-visible digest output.
  Internal readiness may remain in sidecars.
- `finish_required_evidence_refs` must be removed. If a repair needs a visible
  hint, expose only safe path/command refs through `observable_refs` on the NG
  resume signal.

Forbidden compact-digest keys include all historical finish-tool schema and
gate/resolver keys: `finish`, `finish_status`, `finish_readiness`,
`finish_readiness_state`, `finish_required_evidence_refs`, `task_done`,
`summary`, `final_status`, `evidence_refs`, `closeout_refs`,
`missing_obligations`, `unsafe_blockers`, `budget_blockers`,
`native_finish_gate_decision`, `resolver_decision`, and `task_contract`.

## OK / NG State Transitions

Internal gate outcomes:

- `OK`: gate result `allow`; lane status becomes `completed`; the final user
  response is the model's done-candidate assistant message, with optional
  controller metadata only in sidecars.
- `NG_CONTINUE`: gate result `block` with recoverable blockers; append an
  abstract resume signal to the next model input and continue the same agentic
  loop.
- `NG_RETURN`: gate result `block` with safety, permission, budget, or
  supervisor blockers; stop the lane as blocked and return a user/supervisor
  summary.

State machine:

```text
RUNNING
  -> DONE_CANDIDATE
  -> INTERNAL_GATE_RUNNING
  -> COMPLETED
  -> BLOCKED_RETURN
  -> RESUME_SIGNAL_ENQUEUED
  -> RUNNING
```

`NG_CONTINUE` consumes an additional model turn budget and has an absolute cap:
at most two consecutive `NG_CONTINUE` resumes per lane attempt, and at most
three total internal-gate NG decisions per lane attempt. A later implementation
may lower these limits but must not leave them unbounded.

The plateau signature is:

```text
gate_policy_version
+ normalized blocker codes
+ normalized missing-obligation classes
+ latest source mutation hash
+ latest artifact mutation hash
+ latest verifier evidence ref set
+ latest terminal command status/exit class
```

Tool progress after an NG means at least one of:

- a new paired tool output sequence after the previous NG;
- a changed source/artifact mutation hash;
- a new typed evidence ref;
- a new verifier command result with a distinct command-run id or exit class.

If the same plateau signature recurs without tool progress, the next state is
`NG_RETURN` with `repeat_plateau`, even if the model-turn budget has not been
exhausted.

## Abstract NG Resume Interface

The resume signal is intentionally abstract:

```text
FinishGateResumeSignal
  done_candidate_id
  decision_id
  lane_status = blocked_continue
  concise_reason
  repair_focus
  observable_refs
  prohibited_leak_keys
  sidecar_ref
```

Allowed model-visible content:

- one or two sentences explaining what was not yet verified or what failed;
- concrete path/line refs or command-result refs already safe for normal tool
  result rendering;
- a repair focus such as "run the failing verifier and fix the failure" or
  "produce the expected artifact";
- no raw decision JSON.

Forbidden model-visible content:

- keys named `task_contract`, `finish_gate`, `native_finish_gate_decision`,
  `resolver_decision`, `evidence_refs`, `missing_obligations`,
  `oracle_obligation_refs`, `finish_status`, `finish_readiness_state`,
  `finish_required_evidence_refs`, or `task_done`;
- full `proof-manifest.json`;
- full WorkFrame/proof/frontier objects;
- planner prompt/rationale;
- hidden acceptance constraints not already present in the user task.

Insertion point:

- The resume signal is added after the done-candidate assistant message and
  after the internal gate decision.
- It becomes the first input to the next main-model turn.
- Its transport can later be chosen as user-role text, a provider input item,
  or a tool-result-like payload. Tests should assert only the abstract content
  contract and leak policy, not the final transport.

Replay-canonical record:

- The transport-agnostic sidecar row is canonical for replay. Use
  `ng_resume_signals.jsonl` if kept separate, or a `resume_signal` object inside
  `native_finish_gate_decisions.jsonl` / `internal_finish_gate_decisions.jsonl`.
- `response_transcript.json` records the concrete transport selected by that
  run. Replay compares abstract sidecar content across transports and compares
  transcript hashes only within the same transport choice.

Leak scanning:

- Scan the rendered controller-authored resume signal, not arbitrary model
  prose.
- Use structural JSON-key matching when the signal is structured and
  whole-token or quoted-key matching for prose.
- Production fails closed on leak-scan uncertainty. Tests may include an
  allowlist only for ordinary words in user task text, never for controller
  schema keys.

## Hot-Path Non-Leakage Policy

The production provider request for the main model may contain only:

- static coding instructions;
- provider-native transcript window;
- normal provider-visible tool specs, excluding `finish`;
- normal compact sidecar digest fields already allowed by the hot-path collapse
  design;
- NG resume signal text after a failed internal gate.

It must not contain:

- raw `task_contract`;
- provider-visible `finish` tool or finish schema;
- any historical finish-tool schema field name, including `summary`,
  `evidence_refs`, `final_status`, `task_done`, `closeout_refs`,
  `missing_obligations`, `unsafe_blockers`, and `budget_blockers`;
- `native_finish_gate_decisions`, `resolver_decisions`, or planner decision
  records;
- `FinishVerifierPlannerLoopRequest`;
- `CompletionResolverInput`;
- `NativeFinishGateRequest`;
- `required_next` or finish-pressure fields except where already allowed by the
  compact digest policy, and never as finish schema.

Provider request artifacts in `native-provider-requests.json` must be scanned
for those forbidden keys. The scan should be structural where JSON is available
and phrase-based for rendered text.

## Proof / Replay / Observability

The source of truth remains `response_transcript.json`. The done candidate and
internal gate are sidecar decisions derived from it and from tool-result
artifacts.

Required artifacts:

- `response_transcript.json`
- `response_items.jsonl`
- `proof-manifest.json`
- `native-provider-requests.json`
- `tool_results.jsonl` / existing tool result sidecars
- `done_candidates.jsonl`
- `native_finish_gate_decisions.jsonl` or successor internal-gate sidecar
- `ng_resume_signals.jsonl` if resume signals are not embedded in gate rows
- `finish_verifier_planner_requests.jsonl` when planner runs
- `finish_verifier_planner_decisions.jsonl` when planner runs
- `resolver_decisions.jsonl` only if resolver remains distinct from the
  internal gate

Manifest requirements:

- hash every new sidecar;
- count `done_candidate_count`, `internal_finish_gate_decision_count`,
  `internal_finish_gate_ok_count`, `internal_finish_gate_ng_continue_count`,
  `internal_finish_gate_ng_return_count`, and planner request/decision counts;
- expose `ng_resume_signal_count`, `ng_continue_consecutive_max`, and
  `repeat_plateau_count`;
- record prompt/request leak-scan status;
- record whether any provider-visible finish tool appeared.

Observability additions:

- `src/mew/implement_lane/hot_path_fastcheck.py` should check that native
  artifacts with done candidates have matching internal gate decisions and no
  provider-visible `finish` tool.
- `src/mew/implement_lane/hot_path_step_diff.py` should classify done-candidate
  turns separately from tool turns and gate turns. Required classifications:
  `model_tool_turn`, `done_candidate`, `internal_gate`, `ng_resume`, and
  `blocked_return`. Summaries must expose `done_candidate_turn_count`,
  `internal_gate_turn_count`, `ng_resume_turn_count`, and
  `completed_after_internal_gate_count`.
- `src/mew/implement_lane/native_boundary_audit.py` should replace
  finish-call anchors with done-candidate anchors: `done_candidate_detected`,
  `internal_finish_gate_launched`, `ng_resume_signal_appended`, and
  `provider_visible_finish_absent`.
- `docs/DESIGN_2026-05-15_M6_24_HOT_PATH_OBSERVABILITY.md` remains the rule:
  analyzers read artifacts; they do not alter live behavior.

Completion resolver disposition:

- The internal finish gate is the canonical OK/NG authority.
- `completion_resolver.py` may remain as a subordinate pure evaluator if it
  produces diagnostic sub-decisions consumed by the gate.
- If both resolver and internal-gate rows exist, the lane outcome is determined
  only by the internal-gate row keyed by `done_candidate_id`; resolver rows are
  evidence/diagnostic refs and must not contradict or override the gate.
- If the resolver is absorbed, preserve its current pre-extracted-input guard:
  no raw transcript, raw tool results, or provider request body as resolver
  authority.

## Impact Scope

Likely production code impact:

- `src/mew/implement_lane/tool_policy.py`: remove or production-gate `finish`
  from `V2_BASE_TOOL_SPECS`.
- `src/mew/implement_lane/tool_registry.py`: remove finish from production
  Codex hot-path profile assembly, route tables, route hashes, and
  `ToolAccess` handling; retain only legacy/replay entries if needed.
- `src/mew/implement_lane/tool_routes.py`: remove production `"finish"` route
  classification; legacy route records must be isolated from production
  provider-visible route artifacts.
- `src/mew/implement_lane/tool_result_renderer.py`: remove production
  `CODEX_FINISH_RENDERER_ID` / `_render_codex_finish()` rendering path from
  provider-visible output; any retained renderer is legacy/replay-only.
- `src/mew/implement_lane/native_tool_schema.py`: remove provider-visible
  `finish` schema from production lowering.
- `src/mew/implement_lane/native_provider_adapter.py`: stop production parsing
  of `finish` as a model-visible function-call protocol; keep historical
  replay support only if needed.
- `src/mew/implement_lane/native_tool_harness.py`: replace in-loop
  `finish_call` handling with done-candidate detection, internal gate launch,
  OK/NG transition handling, and resume-signal insertion.
- `src/mew/implement_lane/native_finish_gate.py`: evolve request/decision
  shapes from `finish_call_id` authority to `done_candidate_id` authority.
- `src/mew/implement_lane/completion_resolver.py`: either absorb into the new
  internal gate or rename inputs from `FinishClaim` to done-candidate facts.
- `src/mew/implement_lane/native_transcript.py`: preserve assistant-message
  final response as transcript source; add derived done-candidate metrics.
- `src/mew/implement_lane/native_sidecar_projection.py` and
  `src/mew/implement_lane/native_workframe_projection.py`: ensure compact
  digest uses `done_candidate_status` / `internal_gate_status` and never
  projects internal finish-gate schema or legacy finish-readiness fields.
- `src/mew/implement_lane/native_boundary_audit.py`: redesign anchors from
  finish-call completion to done-candidate detection, internal gate launch, NG
  resume append, and provider-visible finish absence.
- `src/mew/implement_lane/hot_path_fastcheck.py`: add no-finish-tool and
  done-candidate/internal-gate replay checks.
- `src/mew/implement_lane/hot_path_step_diff.py`: add done-candidate and
  internal-gate classifications.
- `src/mew/commands.py`: ensure selected production command route still calls
  the native runner and reports the new metrics.

Legacy or ambiguous impact:

- `src/mew/implement_lane/v2_runtime.py` still has model-JSON `finish`
  handling. Because production native routing now uses `run_live_native_implement_v2`,
  it must be quarantined behind an explicit `legacy_test_only` / replay-only
  route before close. `run_live_json_implement_v2()` must not be callable from
  production command routing, native validation, or Codex hot-path profiles.
- Existing tests under `tests/test_implement_lane.py` heavily exercise
  `run_live_json_implement_v2()`; keep them only under quarantined legacy test
  markers or move them to legacy fixtures. New production tests must use
  `run_live_native_implement_v2()` / `run_native_implement_v2()`.

Likely test impact:

- `tests/test_native_tool_schema.py`
- `tests/test_native_tool_harness.py`
- `tests/test_native_provider_adapter.py`
- `tests/test_native_boundary_audit.py`
- `tests/test_hot_path_fastcheck.py`
- `tests/test_hot_path_step_diff.py`
- new or existing tests covering `tool_registry.py`, `tool_routes.py`, and
  `tool_result_renderer.py` production profiles
- `tests/test_native_finish_gate.py`
- `tests/test_native_transcript.py`
- `tests/test_implement_lane.py` for legacy quarantine only

Likely script/check impact:

- `scripts/check_implement_v2_hot_path.py`
- `scripts/check_implement_v2_native_gate.py`
- `scripts/analyze_hot_path_step_diff.py`

## Phases

### Phase 0 - Static Contract And Leak Gate

- Add a canonical "no provider-visible finish" forbidden-surface gate.
- Add fixture coverage that provider request descriptors contain no `finish`
  tool descriptor and no finish schema fields.
- Add production profile checks for `tool_registry.py`, `tool_routes.py`, and
  `tool_result_renderer.py` so finish cannot leak through route/render metadata
  after removal from `tool_policy.py`.
- Add `native_boundary_audit.py` design/source anchors for
  `done_candidate_detected`, `internal_finish_gate_launched`,
  `ng_resume_signal_appended`, and `provider_visible_finish_absent`.
- Add done-candidate sidecar schema tests.
- Do not change live behavior until this gate exists.

### Phase 1 - Tool Surface Removal

- Remove provider-visible `finish` from production native tool policy and
  schema lowering.
- Remove production finish access/route/render entries from tool registry,
  route metadata, and Codex result rendering. Retained finish machinery must be
  under legacy/replay names and unreachable from production request assembly.
- Replace provider-visible compact digest completion fields with
  `done_candidate_status`, `done_candidate_ref`, `internal_gate_status`, and
  `resume_signal_status`.
- Update native provider adapter tests so assistant final text is not parsed as
  control JSON.
- Keep old `finish_call` fixtures in an explicit legacy/replay namespace if
  needed.

### Phase 2 - Done Candidate Detector

- In `native_tool_harness.py`, treat no-call assistant final responses as done
  candidates after pairing/cancelling all calls and closing active commands.
- Persist `done_candidates.jsonl` and manifest hashes.
- Enforce the one-continuation cap for ambiguous no-tool prose and the
  `no_tool_repeat` done-candidate fallback.

### Phase 3 - Internal Finish Gate

- Launch internal gate after each done candidate.
- Reuse final-verifier closeout, planner, resolver, and artifact writers with a
  done-candidate request shape.
- Rekey gate and planner rows to `done_candidate_id`; keep `finish_call_id`
  only in legacy artifact readers.
- Enforce planner-visible input filtering before any finish verifier planner
  call.
- Enforce verifier precedence: configured verifier first, planner second, and
  auto-detected verifier diagnostic-only unless a named fallback policy is on.
- Produce OK/NG decisions without appending provider-visible `finish_output`.

### Phase 4 - NG Resume Signal

- Add the abstract resume signal insertion point.
- Keep transport swappable; tests pin content and non-leakage, not user-role vs
  tool-result-like implementation.
- Persist transport-agnostic resume signal content in a sidecar and record the
  concrete transport in `response_transcript.json`.
- Add the hard cap, plateau signature, and tool-progress definition for NG
  resumes.

### Phase 5 - Observability And Replay Closure

- Update hot-path fastcheck, step-diff, and native gate scripts.
- Require manifest hashes for done candidate, internal gate, and planner
  artifacts.
- Add step-diff classification counts for `done_candidate`, `internal_gate`,
  and `ng_resume`.
- Add sidecar replay tests for OK, NG continue, NG return, planner accepted,
  planner rejected/fallback, hidden planner-input leak rejection, auto fallback
  policy rejection, and hash drift.

### Phase 6 - Legacy Quarantine

- Remove production references to provider-visible finish tool.
- Quarantine or delete model-JSON finish behavior where it is not needed for
  legacy fixtures.
- Mark `run_live_json_implement_v2()` as `legacy_test_only` or equivalent and
  move existing `tests/test_implement_lane.py` finish coverage under explicit
  legacy markers.
- Fail native boundary audit if production native route can expose `finish`.

## Close Gate

The migration is closed only when all are true:

- Production native provider requests contain no `finish` tool descriptor.
- Production native provider requests contain no finish argument schema fields:
  `summary`, `task_done`, `final_status`, `evidence_refs`, `closeout_refs`,
  `missing_obligations`, `unsafe_blockers`, `budget_blockers`.
- Main-model input contains no raw `task_contract`, finish-gate decision JSON,
  resolver JSON, planner prompt/rationale, or proof manifest body.
- Planner request artifacts contain only planner-visible inputs: raw user task,
  explicitly supplied configured verifier command, model-visible tool
  results/artifacts, transcript summaries, and safe internal runtime facts.
- Planner request artifacts contain no hidden external verifier failure detail,
  hidden acceptance constraint, raw `task_contract` JSON, proof oracle
  constraint, unresolved oracle obligation, or benchmark-only expected output
  unless that information was visible in the original task or normal tool
  results.
- Verifier precedence is visible in sidecars: configured verifier first,
  finish verifier planner second, and auto-detected verifier diagnostic-only
  unless a named fallback policy is explicitly enabled.
- Auto-detected verifier never silently replaces a rejected planner command.
  Any authorized auto fallback records policy, reason, source, strength,
  planner state, and fallback decision.
- A no-tool assistant final response produces exactly one done candidate.
- Every done candidate has exactly one internal finish-gate decision.
- Production gate and planner rows are keyed by `done_candidate_id`; any
  `finish_call_id` row is legacy/quarantine-only.
- OK decisions mark the lane completed and preserve the model's final response.
- NG continue resumes the agentic loop through the abstract signal and does not
  leak internal schema.
- Consecutive NG continue behavior respects the hard cap and repeat plateau
  rule.
- NG return stops blocked with a supervisor-safe summary.
- Finish verifier planner decisions remain sidecar-only and are manifest-hashed.
- Compact sidecar digest uses done-candidate/internal-gate fields and contains
  no legacy finish-readiness fields.
- `response_transcript.json`, sidecars, and `proof-manifest.json` replay the
  same completion outcome deterministically.
- Hot-path step-diff can distinguish model work turns, done-candidate turn,
  internal gate work, and NG resume turns.

## Testing Strategy

Unit tests:

- provider tool list excludes `finish`;
- native schema lowering has no `finish` schema in production mode;
- Codex hot-path tool registry, route metadata, and tool-result renderer expose
  no production finish route/renderer;
- compact sidecar digest emits `done_candidate_status` and
  `internal_gate_status`, not `finish_status`, `finish_readiness_state`, or
  `finish_required_evidence_refs`;
- assistant text containing JSON-like `{"finish": ...}` is recorded as text;
- done candidate detection fires on no-call final response;
- ambiguous no-tool prose receives one continuation only, then
  `no_tool_repeat` becomes a done candidate;
- active command or pending approval prevents OK and becomes NG/return;
- internal gate OK/NG transitions are deterministic;
- NG continue hard cap and plateau signature force `NG_RETURN` when no tool
  progress occurs;
- NG resume signal omits forbidden keys and raw gate JSON;
- planner request builder rejects hidden external verifier failures, hidden
  acceptance constraints, raw `task_contract`, proof oracle constraints, and
  benchmark-only expected outputs not visible to the model;
- configured verifier precedence suppresses planner completion authority when
  configured verifier proves the candidate;
- planner-enabled cases do not use auto-detected verifier as silent fallback
  after planner rejection;
- named auto fallback policy, when enabled in a fixture, records reason, source,
  strength, planner state, and fallback decision in sidecars;
- planner accepted/rejected/fallback cases remain sidecar-only.

Replay/fixture tests:

- native artifact with OK internal gate passes fastcheck;
- native artifact with missing internal gate decision fails fastcheck;
- sidecar hash drift fails fastcheck;
- trusted closeout pass without matching done candidate fails;
- planner request sidecar containing hidden verifier/acceptance/oracle fields
  fails fastcheck or boundary leak checks;
- auto-detected verifier completion authority without named fallback policy
  fails fastcheck;
- rejected planner plus silent auto-detected replacement fails fastcheck;
- NG continue followed by repair and second done candidate passes;
- repeated NG without tool progress hits plateau.
- the same abstract NG resume sidecar content replays across two transport
  choices, while transcript hashes are compared only inside a single transport
  choice.

Boundary tests:

- `tests/test_native_boundary_audit.py` rejects production native code paths that
  include provider-visible `finish` and requires the new done-candidate/gate
  anchors;
- `tests/test_hot_path_fastcheck.py` scans `native-provider-requests.json` for
  forbidden finish/task-contract fields;
- planner request leak checks scan `finish_verifier_planner_requests.jsonl` for
  hidden external verifier details, hidden acceptance constraints, raw
  `task_contract`, proof oracle constraints, and benchmark-only expected
  outputs;
- verifier precedence tests prove configured > planner > diagnostic-only auto,
  and prove auto fallback needs a named policy and explicit sidecar record;
- legacy model-JSON `finish` tests are explicitly labeled legacy/quarantine and
  cannot satisfy production native close gates.

Suggested local verification:

```text
uv run pytest --no-testmon -q tests/test_native_tool_schema.py tests/test_native_provider_adapter.py tests/test_native_tool_harness.py tests/test_native_finish_gate.py tests/test_hot_path_fastcheck.py tests/test_native_boundary_audit.py
```

## Migration Plan

This can be a flag-day migration because there is no backward compatibility
requirement.

1. Land the static leak gate and production-mode fixture first.
2. Remove `finish` from production native tool surface, registry, routes, and
   result rendering.
3. Replace compact digest finish fields with done-candidate/internal-gate fields.
4. Add done-candidate sidecar generation while still allowing historical
   finish replay fixtures.
5. Move final-verifier closeout and planner launch behind the internal gate,
   rekey gate/planner artifacts to `done_candidate_id`, and add planner-visible
   input filtering.
6. Add explicit verifier precedence and keep auto-detected verifier
   diagnostic-only unless a named fallback policy is enabled and recorded.
7. Add NG resume signal insertion, replay-canonical sidecar content, hard cap,
   and repeat-plateau logic.
8. Update fastcheck, step-diff, and native boundary audit.
9. Quarantine or delete legacy model-JSON finish routes from production checks.
10. Run a bounded native gate artifact proof before any broad speed/proof run.

Rollback rule: if the internal gate regresses completion accuracy, restore only
the previous internal resolver/gate behavior behind done-candidate detection.
Do not reintroduce provider-visible finish schema to the main model hot path.
