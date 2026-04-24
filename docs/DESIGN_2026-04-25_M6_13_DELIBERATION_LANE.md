# M6.13 High-Effort Deliberation Lane Design (v0)

Date: 2026-04-25
Status: draft design; no implementation in this document
Owner: M6.13 design surface
Depends on: M6.11 Loop Stabilization runtime contracts
Related: M6.12 failure-science instrumentation, M6.9 durable coding
intelligence, M6.13 Phase 0 high-effort model tuning reference
Scope boundary: `M6.13` is one milestone with three phases.
The lane framework, deliberation lane, and memory internalization proof
must not be split into separate milestones.

## 1. Purpose And Non-Goals

### 1.1 Purpose

`M6.13 High-Effort Deliberation Lane` adds a bounded escalation path to
mew's supervised work loop.
The milestone is not about making the default loop more expensive.
It is about giving mew a narrow way to notice a hard blocker, ask for
deliberation under explicit budget controls, and turn the result into
durable reasoning memory that a later tiny lane can reuse.
The Phase 0 research reference frames M6.13 as a "deliberation lane":
a bounded path that escalates harder tasks to higher-effort reasoning
models or higher test-time-compute settings
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:11-18`).
That same reference warns against judging the work by whether mew can
call a powerful model.
The differentiator is blocker-aware durable reuse: typed blockers,
replay bundles, explicit internalization, and later recall across
sessions (`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:460-481`).
This design accepts that boundary.
The milestone contains exactly three phases:
1. Phase 1: Lane Framework.
2. Phase 2: Deliberation Lane.
3. Phase 3: Memory Internalization.
Those phases are ordered, but they are one coherent milestone.
The lane framework without deliberation is only routing.
Deliberation without memory internalization is only a wrapper around a
stronger model.
M6.13 closes only when all three phases have landed and one complete
internalization cycle is proven.
The required proof is:
1. A hard task reaches an eligible blocker or hard-shape state.
2. The deliberation lane solves or materially advances that task.
3. The useful reasoning is distilled into a reviewer-approved
   reasoning-trace entry.
4. A later same-shape task is solved by the tiny lane using that trace.
If step 4 is missing, M6.13 is blocked.
That is the codex-beyond gate for this milestone.

### 1.2 Non-Goals

`M6.13` is explicitly not supposed to:
- execute the `M6.11` closeout refresh or reopen the `M6.11` close gate
- rewrite `M6.11` replay bundles, ledger rows, or closeout evidence
- rename any existing `M6.11` replay bundle field or directory segment
- change tiny-lane behavior during Phase 1
- weaken the exact cached-window discipline from `M6.11`
- replace `PatchDraftCompiler` validation with model judgement
- change the blocker taxonomy as a prerequisite for Phase 1
- silently drop the additive `cached_window_incomplete` code that now
  exists in source
- execute `M6.9` Phase 2, Phase 3, or Phase 4 as part of this milestone
- redefine `M6.9` ranked recall, hindsight harvesting, rehearsal, or
  curriculum work
- bypass the `M6.9` durable-memory write gate
- store raw deliberation transcript as durable memory
- auto-accept deliberation-derived reasoning traces without reviewer
  approval
- implement `M6.12` reading surfaces
- ship the `M6.12` cockpit or classifier
- change the `M6.12` close gate or the `M6.12` success criteria
- modify `ROADMAP.md` or `ROADMAP_STATUS.md`
- choose a permanent provider or permanent high-effort model family
- choose final numeric cost caps in this design document
- fine-tune, train, or weight-update any model
- introduce a broad autonomous subagent architecture
- make the deliberation lane write-capable in v0
- make high effort the default for all work-loop turns
- collapse schema failures into "use a smarter model"
- treat external benchmark gains as direct mew close evidence
- introduce new paper citations not already present in the Phase 0
  M6.13 research reference
- remove reviewer judgement from escalation, internalization, or close
  proof
- hide escalation failure behind a generic tiny-lane retry
- create a second independent task planner
- let budget overruns fail the whole loop when tiny fallback is
  available
- promise that all eligible blockers should escalate automatically
- ship a milestone that can only be described as a codex-cli wrapper

### 1.3 Shape Of The Product

M6.13 is a small lane system plus one real lane.
The lane system names which execution path owns a `WorkTodo` attempt.
The first real non-tiny lane is `deliberation`.
The first proof-only non-tiny lane is `mirror`.
The `mirror` lane exists to prove the framework can carry non-tiny lane
identity without changing behavior.
The `deliberation` lane exists to make one bounded model call under an
explicit model binding and an explicit budget.
The memory internalization phase exists to turn useful deliberation into
durable coding intelligence.
Every lane claim must be reconstructable from plain files:
- `active_work_todo`
- replay bundle metadata
- session trace cost events
- reviewer decision artifacts
- durable `reasoning_trace.jsonl` entries
This follows the external observability principle from M6.9, which
requires durable artifacts to be reconstructable from `.mew/durable/`
and session traces without reading source code
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:338-353`).

### 1.4 Close-Gate Shape

The M6.13 close gate belongs to M6.13 only.
It does not alter the M6.9, M6.11, or M6.12 gates.
The close gate is intentionally stronger than the MVP.
The MVP may be Phase 1 only.
The milestone is not closed by the MVP.
The v0 success criteria in section 16 span all three phases.

## 2. Inputs

### 2.1 Canonical Artifacts Consumed

The primary research input is:
- `docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md`
That file provides the Phase 0 literature and model-surface survey.
It is the source for the "why not codex-cli as-is" philosophy.
It explicitly separates effort controls from a complete mew escalation
policy: Codex and Claude Code expose typed effort surfaces, but neither
source tree showed a broad automatic hard-task router
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:195-197`,
`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:245-252`).
It also states that high-effort lanes add failure surface: schema drift,
capability mismatch, refusal behavior, latency, and overthinking
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:273-293`).
The design therefore treats high effort as a controlled escalation, not
as a default work-loop policy.

### 2.2 Shape References

The first shape reference is:
- `docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md`
M6.12 is a design for a reading surface on top of closed M6.11 evidence.
Its non-goals explicitly defer multi-lane infrastructure to M6.13
(`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:47-51`).
Its CLI design keeps one mode flag under `mew proof-summary` and
separates canonical from derived output
(`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:623-651`,
`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:717-787`).
Its v0 success criteria are nine concrete items followed by an explicit
"not done if any criterion fails" rule
(`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:1575-1632`,
`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:1648`).
M6.13 matches that discipline in section 16.
The second shape reference is:
- `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`
M6.11 defines the runtime state model that M6.13 extends.
It makes `active_work_todo.status` the source of session phase after a
draft frontier exists
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:321-351`).
It lists the original 12 blocker codes
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:483-500`).
It splits implementation into phases with a clear "scope" and "what
this phase proves" pattern
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:769-861`).
M6.13 uses the same phase discipline.

### 2.3 M6.9 Memory Inputs

The durable coding intelligence design is:
- `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`
M6.9 defines reasoning-trace reuse as a formal success condition:
at least two iterations must recall a past reasoning trace, and a
reviewer must confirm that recall shortened deliberation
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:59-63`).
M6.9 defines reasoning traces as distilled `(situation, reasoning,
verdict)` triples, not raw transcripts
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:228-247`).
M6.9 also requires outcome-gated retention and a reuse-gate adaptation
step before memory is applied
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:257-266`).
M6.13 Phase 3 reuses those principles.
The scientific expected-values reference is:
- `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md`
It classifies evidence as Direct, Translated, or Directional and says
to widen the class when uncertain
(`docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md:68-120`).
It treats reasoning-trace gains as a Translated-class expectation,
measured on abstract tasks after reasoning trace becomes available
(`docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md:357-380`).
M6.13 applies that conservative adaptation philosophy to any claim that
deliberation improved later tiny-lane behavior.

### 2.4 Source Inputs

The current executable blocker map lives in:
- `src/mew/patch_draft.py:11-24`
The source map has 13 keys, not the 12-code list in the M6.11 design.
The additive key is `cached_window_incomplete`.
M6.13 treats the executable map as canonical for implementation, while
preserving the 12-code design list as historical M6.11 context.
`WorkTodo` normalization currently accepts `id`, `status`, `source`,
`cached_window_refs`, `attempts`, `patch_draft_id`, `blocker`,
`created_at`, and `updated_at`
(`src/mew/work_session.py:4868-4918`).
`work_session_phase()` currently derives the phase from
`active_work_todo.status` when that status is a work-todo phase
(`src/mew/work_session.py:4213-4238`).
The current tiny write-ready lane builds focused context from cached
windows and active todo source fields
(`src/mew/work_loop.py:4592-4657`).
Its prompt returns only `patch_proposal` or `patch_blocker`
(`src/mew/work_loop.py:4786-4808`).
It binds the tiny draft reasoning effort and records tiny metrics
(`src/mew/work_loop.py:4100-4151`).
It uses `codex_reasoning_effort_scope()` around the model call
(`src/mew/work_loop.py:4165-4176`).
The existing shadow compiler is
`_shadow_compile_patch_draft_for_write_ready_turn()`
(`src/mew/work_loop.py:3797-3820`).
The common compiler adapter is
`_compile_write_ready_patch_draft_proposal()`
(`src/mew/work_loop.py:4035-4097`).
Replay bundles are currently written under `.mew/replays/work-loop` and
use `todo-<id>/attempt-<n>` for patch-draft compiler bundles
(`src/mew/work_replay.py:477-573`).
Model-failure bundles use `todo-<id>/turn-<id>/attempt-<n>`
(`src/mew/work_replay.py:403-474`).
The proof-summary calibration reader walks `replay_metadata.json` and
`report.json`, classifies compiler bundles by blocker code, and reports
off-schema/refusal/bundle rates
(`src/mew/proof_summary.py:238-330`,
`src/mew/proof_summary.py:414-489`,
`src/mew/proof_summary.py:569-626`).
The model backend abstraction already routes JSON calls through backend,
model, base URL, auth, and timeout fields
(`src/mew/model_backends.py:14-25`,
`src/mew/model_backends.py:118-129`).
The Codex web API wrapper attaches `reasoning.effort` from
`MEW_CODEX_REASONING_EFFORT`
(`src/mew/codex_api.py:248-273`).
The current reasoning policy validates `low`, `medium`, `high`, and
`xhigh`, supports an environment override, and exposes
`codex_reasoning_effort_scope()`
(`src/mew/reasoning_policy.py:5-6`,
`src/mew/reasoning_policy.py:49-51`,
`src/mew/reasoning_policy.py:104-147`,
`src/mew/reasoning_policy.py:150-165`).

## 3. Data Model Additions

### 3.1 Design Rule

Every M6.13 data change is additive.
Existing M6.11 bundles remain valid.
Existing sessions without lane fields normalize as tiny-lane sessions.
Existing readers that ignore lane fields keep their current behavior.
New readers may filter by lane.
No existing field is renamed.
No existing blocker code is removed.
No existing `attempt` counter is reinterpreted.

### 3.2 `WorkTodo.lane`

Add `lane` to `WorkTodo`.
Shape:

```json
{
  "lane": "tiny"
}
```

Rules:
- type: string
- default: `"tiny"`
- empty string: normalize to `"tiny"`
- missing field: normalize to `"tiny"`
- unknown value: preserve as a string but mark unsupported in derived
  views
- v0 supported lanes: `tiny`, `mirror`, `deliberation`
- value is a lane identifier, not a model name
- value is persisted on the todo, not inferred only from metrics
The default is required for backward compatibility because current
`_normalize_active_work_todo()` has no lane field
(`src/mew/work_session.py:4868-4918`).
The lane belongs to the active attempt frontier.
If a later implementation chooses to record attempt-level lane history,
`WorkTodo.lane` still represents the currently authoritative lane for
the todo.

### 3.3 Lane Registry

M6.13 introduces a lane registry as data, not as a broad plugin system.
Minimum fields:

```json
{
  "name": "tiny",
  "role": "authoritative|shadow|mirror",
  "write_capable": false,
  "model_binding_required": false,
  "fallback_lane": "tiny",
  "bundle_layout": "legacy|lane_scoped"
}
```

`tiny` is authoritative and write-capable only through the existing
dry-run approval flow.
`mirror` is non-authoritative in Phase 1.
`deliberation` is read-only in v0.
No lane owns direct writes in M6.13 except the existing tiny path through
existing approval and apply machinery.

### 3.4 Replay Bundle Schema Additions

Additive fields for `replay_metadata.json` and `report.json`:

```json
{
  "lane": "tiny",
  "lane_role": "authoritative|shadow|mirror",
  "lane_schema_version": 1,
  "lane_attempt_id": "lane-tiny-todo-17-attempt-1",
  "lane_parent_attempt_id": "",
  "lane_decision": "authoritative|shadow_only|fallback|budget_blocked",
  "requested_model": "",
  "requested_effort": "",
  "effective_model": "",
  "effective_effort": "",
  "budget_snapshot": {}
}
```

Missing `lane` means `tiny`.
Missing model fields mean no non-tiny model binding was involved.
Missing budget fields mean the bundle predates M6.13.
The current `patch_draft_compiler` metadata has
`schema_version`, `bundle`, `calibration_counted`,
`calibration_exclusion_reason`, `git_head`, `bucket_tag`, `session_id`,
`todo_id`, `blocker_code`, `attempt`, `captured_at`, and `files`
(`src/mew/work_replay.py:548-570`).
M6.13 appends to that object.
It does not replace it.

### 3.5 Lane-Scoped Directory Layout

The legacy layout stays valid:

```text
.mew/replays/work-loop/<date>/session-<id>/todo-<id>/attempt-<n>/
```

The lane-scoped layout is reserved for new non-tiny bundles:

```text
.mew/replays/work-loop/<date>/session-<id>/lane-<name>/todo-<id>/attempt-<n>/
```

Model-failure bundles may add the turn segment:

```text
.mew/replays/work-loop/<date>/session-<id>/lane-<name>/todo-<id>/turn-<turn>/attempt-<n>/
```

Readers must support both layouts.
The legacy layout has implicit `lane=tiny`.
The lane-scoped layout has explicit `lane=<name>` and still records the
same field in metadata.
Phase 1 should not move tiny bundles into the lane-scoped layout.
That keeps tiny-lane behavior and paths stable while proving the
non-tiny layout through `mirror`.

### 3.6 Deliberation Trace Fields

Add session-trace fields, not durable-memory fields:

```json
{
  "deliberation_attempts": [],
  "deliberation_cost_events": [],
  "latest_deliberation_result": {},
  "latest_deliberation_bundle": ""
}
```

`deliberation_attempts` records requests and outcomes.
`deliberation_cost_events` records reservation, spend, budget block,
fallback, and refund-like accounting if a provider exposes actual usage.
`latest_deliberation_result` is transient session state.
Durable memory receives only reviewer-approved distilled traces.

### 3.7 Reasoning Trace Provenance

Extend `reasoning_trace.jsonl` entries with lane provenance.
Shape:

```json
{
  "source_lane": "deliberation",
  "source_lane_attempt_id": "lane-deliberation-todo-17-attempt-1",
  "source_blocker_code": "review_rejected",
  "source_bundle_ref": ".mew/replays/work-loop/...",
  "deliberation_result_id": "delib-...",
  "internalization_review_id": "review-...",
  "same_shape_key": "shape-..."
}
```

This extends the reserved M6.9 `reasoning_trace.jsonl` slot under
`.mew/durable/memory/`
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:489-497`).
M6.13 does not change the raw entry type from reasoning trace to a new
sixth durable memory type.

### 3.8 Internalization Proof Artifact

Phase 3 writes a proof artifact only after the full cycle succeeds.
Suggested shape:

```json
{
  "schema_version": 1,
  "milestone": "M6.13",
  "hard_task_ref": "...",
  "deliberation_bundle_ref": "...",
  "reasoning_trace_entry_id": "...",
  "reuse_task_ref": "...",
  "tiny_lane_reuse_bundle_ref": "...",
  "reviewer_decision": "approved",
  "proof_summary": "..."
}
```

This artifact is evidence for M6.13 only.
It does not back-propagate into M6.9 success criteria.

## 4. Lane Framework Design (Phase 1)

### 4.1 Phase 1 Goal

Phase 1 proves that lane identity can exist without disrupting the tiny
lane.
It adds:
- `WorkTodo.lane`
- lane registry
- lane-aware replay metadata
- lane-scoped bundle resolver
- reusable shadow-vs-authoritative bridge
- empty `mirror` lane
- lane filter contract for the planned M6.12 report
It does not add high-effort model calls.
It does not change tiny-lane prompt content.
It does not change tiny-lane model effort.
It does not change tiny-lane fallback behavior.

### 4.2 WorkTodo Defaulting

All current active todos normalize to lane `tiny`.
The normalization rule must be near the existing active-todo normalizer,
because that is where the current persisted shape is constrained
(`src/mew/work_session.py:4868-4918`).
The new field is not optional in normalized output.
It may be optional on disk for old sessions.
The normalized todo returned to resume/follow-status should carry
`lane: "tiny"` even when the source JSON omitted it.
This makes lane filtering deterministic for old data.

### 4.3 Lane Registry Behavior

The registry is intentionally small.
`tiny` is the existing lane.
`mirror` is registered but behaviorally identical to tiny.
`deliberation` is reserved but disabled until Phase 2.
Phase 1 must be able to answer:
- which lanes exist
- which lane owns the current todo
- which bundle layout applies to a lane
- whether the lane can be authoritative
- what fallback lane applies
It must not answer:
- which provider is best
- how much high effort costs
- whether memory internalization succeeded
Those belong to later phases.

### 4.4 Empty Mirror Lane

The mirror lane is a proof instrument.
It should receive the same focused context as tiny.
It should compile through the same patch-draft contract.
It should not become authoritative by default.
It should write lane-scoped metadata so reviewers can prove that
non-tiny lane bundles exist.
It should be safe to disable without changing user-visible output.
A Phase 1 mirror-lane proof is successful when:
1. tiny produces the same authoritative result as before
2. mirror records a non-authoritative bundle
3. the bundle has `lane=mirror`
4. the planned M6.12 lane filter can include or exclude it
5. no existing tiny replay reader breaks

### 4.5 Shadow-Bridge Generalization

M6.11 already has a shadow compiler:
`_shadow_compile_patch_draft_for_write_ready_turn()`
(`src/mew/work_loop.py:3797-3820`).
That function adapts a normal action into a patch-draft proposal and
then calls the common compiler adapter.
The common compiler adapter validates the proposal, translates validated
drafts into previews, and writes replay metadata
(`src/mew/work_loop.py:4035-4097`).
M6.13 should extract the reusable primitive:

```json
{
  "input_artifact": {},
  "authoritative_lane": "tiny",
  "candidate_lane": "mirror|deliberation",
  "mode": "shadow|authoritative",
  "compiler_contract": "patch_draft_v1",
  "result_policy": "record_only|can_replace_if_valid"
}
```

The primitive decides what is recorded.
It does not decide whether escalation is allowed.
Escalation policy belongs to Phase 2.

### 4.6 Shadow vs Authoritative Invariants

The bridge must enforce:
1. Exactly one lane is authoritative for a work-loop action.
2. A shadow lane may write replay metadata but not apply edits.
3. A shadow lane result may not silently replace an authoritative result.
4. Replacement requires an explicit lane decision event.
5. Replacement is forbidden in Phase 1.
6. Tiny remains authoritative by default.
7. A failed mirror attempt cannot fail the work loop.
8. A malformed mirror bundle is a mirror bug, not a tiny-lane blocker.
These invariants prevent Phase 1 from changing the tiny lane while still
making lane plumbing observable.

### 4.7 Bundle Resolver Rules

Lane-aware readers must search both old and new layouts.
Order:
1. explicit metadata path
2. legacy layout
3. lane-scoped layout
4. closeout export index, when M6.12 post-closeout mode exists
The resolver must not rewrite paths.
The resolver must not infer that a missing bundle has lane
`deliberation`.
The resolver may infer `tiny` only when the metadata lacks a lane field
or the legacy path is used.
This preserves current calibration behavior, where proof-summary walks
`replay_metadata.json` and `report.json` under a replay root
(`src/mew/proof_summary.py:414-489`).

### 4.8 Lane-Aware Calibration Contract

M6.12 plans one report mode:

```text
mew proof-summary <artifact_dir> --m6_12-report ...
```

That mode is described in the M6.12 design
(`docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md:640-651`).
M6.13 adds an input contract for that planned report:

```text
--lane <name>
```

Rules:
- absent: include all lanes
- `--lane tiny`: include legacy bundles and explicit tiny bundles
- `--lane mirror`: include only mirror bundles
- `--lane deliberation`: include only deliberation bundles
- unknown lane: argument error
- missing lane metadata: treated as tiny
M6.13 does not implement the M6.12 reader.
It only defines the lane metadata and filter semantics that M6.12 should
consume.

### 4.9 Phase 1 Acceptance

Phase 1 is acceptable when:
- old M6.11 bundles still parse
- old sessions normalize to `lane=tiny`
- tiny prompt and model behavior are unchanged
- mirror lane can produce a lane-scoped shadow bundle
- M6.12 lane filter semantics are documented and fixture-tested
- no close gate outside M6.13 changes
Phase 1 alone is an MVP.
Phase 1 alone is not M6.13 close.

## 5. Deliberation Lane Design (Phase 2)

### 5.1 Phase 2 Goal

Phase 2 turns the framework into a real bounded lane.
It adds:
- configured model binding
- blocker-code escalation mapping
- reviewer opt-in escalation
- automatic escalation default rules
- per-session, per-iteration, and per-task budget caps
- fallback to tiny
- cost telemetry
- deliberation replay bundles
It does not add durable memory writes.
It does not make deliberation write-capable.
It does not replace the tiny lane.

### 5.2 Model Binding Abstraction

The binding should be compatible with the current backend model:

```json
{
  "backend": "codex|claude|...",
  "model": "configured-model",
  "base_url": "",
  "auth_ref": "",
  "requested_effort": "high",
  "timeout_seconds": 0,
  "schema_contract": "deliberation_result_v1"
}
```

The current model backend protocol takes auth, prompt, model, base URL,
timeout, and optional text delta sink
(`src/mew/model_backends.py:14-25`).
`call_model_json()` dispatches those values through the backend
(`src/mew/model_backends.py:118-129`).
For Codex-compatible bindings, effort can be scoped by
`MEW_CODEX_REASONING_EFFORT`
(`src/mew/codex_api.py:248-273`,
`src/mew/reasoning_policy.py:150-165`).
The binding must log both requested and effective values:
- `requested_backend`
- `requested_model`
- `requested_effort`
- `effective_backend`
- `effective_model`
- `effective_effort`
- `effort_resolution_reason`
This is required because the research reference warns that effort labels
are not equivalent across providers and wrappers may remap unsupported
effort values
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:135-147`,
`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:380-385`).

### 5.3 Deliberation Result Contract

The lane returns a structured artifact.
It does not return raw prose.
Minimum shape:

```json
{
  "kind": "deliberation_result",
  "schema_version": 1,
  "todo_id": "todo-17",
  "lane": "deliberation",
  "blocker_code": "review_rejected",
  "decision": "propose_patch_strategy|decline_escalation|needs_state_refresh",
  "situation": "short task and blocker summary",
  "reasoning_summary": "distilled reasoning, no raw hidden transcript",
  "recommended_next": "retry_tiny|refresh_state|ask_reviewer|finish_blocked",
  "expected_trace_candidate": true,
  "confidence": "low|medium|high"
}
```

If the result cannot fit this shape, it is a deliberation failure.
The tiny lane remains available.

### 5.4 Explicit Design Decisions

Escalation trigger in v0:
- recommendation: support both reviewer opt-in and automatic triggering
- default: automatic only after an eligible blocker and budget pass
- reviewer command: allowed to request deliberation, but cannot override
  budget exhaustion, write-policy blockers, or stale-state blockers
Lane selection scope:
- recommendation: per-`WorkTodo`
- reason: bundle paths, budget accounting, and internalization proof all
  need a durable todo-level identity
- attempt-level history may record multiple lanes, but `WorkTodo.lane`
  names the currently authoritative lane
Retry effort shape:
- recommendation: do not add a generic low-effort deliberation retry
- reason: tiny already covers the cheap narrow attempt
- exception: schema-wrapper failures may retry the wrapper once before
  high-effort escalation, because those are contract failures
- configured deliberation should go directly to the configured binding for
  eligible semantic blockers
Non-effort alternatives considered for v0 are prompt reformulation,
memory enrichment using richer M6.9 retrieval with the same base model,
and multi-turn decomposition. Memory enrichment is explicitly present in
the Phase 0 matrix (`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:412`),
and §1.2 already forbids collapsing failures into "use a smarter model".
Effort-based escalation is still the v0 lane choice because M6.13 is
specifically testing bounded high-effort escalation under budget and
internalization gates, not expanding the default planner.
These are v0 recommendations, not permanent provider choices.

### 5.5 Escalation Preconditions

A blocker can trigger deliberation only when all of these hold:
1. The active todo has a stable id.
2. The active todo has a lane, defaulting to tiny.
3. The blocker has a stable blocker code.
4. The blocker instance has not already exhausted deliberation attempts.
5. The blocker code maps to `eligible` or reviewer-command eligible.
6. The budget reservation succeeds.
7. The cached-window state is not stale or incomplete.
8. The lane binding is configured and available.
9. The request can be represented as read-only deliberation.
If any precondition fails, the decision is recorded and tiny remains
available.

### 5.6 Fallback Rules

Deliberation failure never breaks tiny.
Fallback happens when:
- budget is exceeded
- model binding is missing
- model call times out
- model returns refusal
- model returns non-schema output
- result validation fails
- reviewer rejects the deliberation result
- stale state is detected before escalation
Fallback event shape:

```json
{
  "event": "deliberation_fallback",
  "reason": "budget_exceeded|timeout|non_schema|refusal|validation_failed",
  "fallback_lane": "tiny",
  "todo_id": "todo-17",
  "blocker_code": "review_rejected"
}
```

The fallback does not erase the blocker.
It annotates the blocker with why deliberation did not run or did not
help.

### 5.7 Phase 2 Acceptance

Phase 2 is acceptable when:
- at least one reviewer-command deliberation attempt runs under budget
- at least one automatic eligible blocker produces a deliberate decision
- at least one ineligible blocker is blocked from escalation
- cost events appear in the session trace
- a deliberate failure falls back to tiny
- tiny remains callable after the deliberate failure
- requested/effective model and effort are logged
- no durable reasoning-trace entry is written without Phase 3 review

## 6. Memory Internalization Design (Phase 3)

### 6.1 Phase 3 Goal

Phase 3 proves that deliberation becomes durable coding intelligence.
The phase transforms an accepted deliberation result into a
reasoning-trace candidate.
The candidate enters a reviewer approval path.
Only approved candidates become durable reasoning traces.
Later same-shape tasks retrieve those traces through M6.9 ranked recall.
The tiny lane must then solve at least one later same-shape task using
the recalled trace.
That is the hard close requirement.

### 6.2 Conversion Path

Conversion input:
- `DeliberationResult`
- active `WorkTodo`
- blocker code
- replay bundle reference
- reviewer decision
- task-shape descriptor
Conversion output:

```json
{
  "kind": "reasoning_trace_candidate",
  "situation": "...",
  "reasoning": "...",
  "verdict": "...",
  "abstraction_level": "shallow|deep",
  "source_lane": "deliberation",
  "same_shape_key": "..."
}
```

The candidate uses the M6.9 reasoning-trace content model:
`(situation, reasoning, verdict)` triples
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:242-247`).
It does not store raw transcript.
It may store a short distilled reasoning summary.

### 6.3 Reviewer Approval Path

The reviewer sees:
- source blocker
- deliberation result
- proposed shallow trace
- proposed deep trace
- same-shape key
- proposed retrieval tags
- replay bundle reference
- budget summary
The reviewer can:
- approve
- reject
- request narrower trace
- mark as task-specific only
- mark as unsafe to reuse
Approval writes to durable memory.
Rejection writes only a review event.
This follows M6.9 P2: nothing enters durable memory without a validation
gate, and reuse goes through adaptation rather than raw copy-paste
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:257-266`).

### 6.4 Storage

Approved entries append to:

```text
.mew/durable/memory/reasoning_trace.jsonl
```

Each line has:
- `schema_version`
- `entry_id`
- `memory_kind=reasoning-trace`
- `situation`
- `reasoning`
- `verdict`
- `abstraction_level`
- `source_lane`
- `source_lane_attempt_id`
- `source_blocker_code`
- `source_bundle_ref`
- `same_shape_key`
- `reviewer_decision_ref`
- `created_at`
Existing M6.9 fields remain.
Lane provenance is additive.
If M6.9 Phase 2 ranked recall is unavailable, Phase 3 cannot close.
M6.13 does not implement ranked recall as a substitute.

### 6.5 Reuse Path

The later task must be same-shape, not identical by accident.
The task-shape key should combine:
- blocker family
- target subsystem
- abstract vs mechanical tag
- source/test pairing shape
- reviewer decision family
- symbol or module similarity
The trace is retrieved through M6.9 Phase 2 ranked recall.
M6.9 describes ranked recall as combining recency, importance, and
relevance, including symbol overlap and task-shape similarity
(`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:615-618`).
M6.13 should not bypass that path with a bespoke lookup.
The tiny lane receives the adapted trace as context.
The tiny lane then produces the later successful result.

### 6.6 Internalization Proof Protocol

A valid proof contains:
1. hard task id
2. original blocker code
3. deliberation bundle path
4. reviewer-approved reasoning-trace entry id
5. later same-shape task id
6. ranked-recall event showing the trace was returned
7. prompt injection or adapted memory event showing it was used
8. tiny-lane replay bundle for the later task
9. reviewer decision confirming tiny-lane success used the trace
The proof is blocked if:
- the later task was solved by deliberation again
- the later task did not retrieve the trace
- the trace was retrieved but not injected or adapted
- the trace was not reviewer-approved
- the task shape is not predeclared
- the evidence requires reading raw model transcript

### 6.7 Phase 3 Acceptance

Phase 3 is acceptable only when one full internalization cycle is
recorded.
The cycle must show:
- deliberation helped a hard task
- reviewer approved a reasoning trace
- ranked recall retrieved that trace later
- tiny lane solved the later same-shape task
- reviewer confirmed the trace shortened or avoided deliberation
No partial credit closes M6.13.

## 7. Runtime State Model

### 7.1 WorkTodo State Machine

M6.13 keeps `active_work_todo.status` as the source of truth.
That follows M6.11's invariant that session phase derives from active
todo status once a draft frontier exists
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:327-351`).
The lane is an attribute of that state machine, not a second state
machine.
Current statuses remain valid:
- `queued`
- `drafting`
- `blocked_on_patch`
- `awaiting_review`
- `awaiting_approval`
- `applying`
- `verifying`
- `completed`
M6.13 adds derived lane substate, not necessarily new status strings:
- `lane_candidate`
- `lane_budget_blocked`
- `lane_deliberating`
- `lane_result_ready`
- `lane_internalization_review`
- `lane_fallback`
The implementation may encode those as trace events rather than
`WorkTodo.status` values.
The design requirement is that a reader can reconstruct them.

### 7.2 Lane Transition Events

Transition event shape:

```json
{
  "event": "lane_transition",
  "todo_id": "todo-17",
  "from_lane": "tiny",
  "to_lane": "deliberation",
  "reason": "blocker_code:review_rejected",
  "blocker_code": "review_rejected",
  "authoritative": false,
  "created_at": "..."
}
```

The event is append-only in the session trace.
It does not mutate historical attempts.
It may update `WorkTodo.lane` when a lane becomes authoritative.
In v0, deliberation should usually remain a read-only assist lane, so
the authoritative lane returns to tiny for final patch drafting.

### 7.3 Derived Session Phase

The operator-facing phase can include lane detail:

```text
blocked_on_patch lane=tiny blocker=review_rejected escalation=eligible
deliberating lane=deliberation budget=session-ok task-ok
drafting lane=tiny memory_trace=rt-123
```

This is a display layer.
It must not become a second source of truth.

## 8. Escalation Trigger Mapping

### 8.1 Source Compatibility Note

The M6.11 design lists 12 blocker codes
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:487-498`).
The current source map has 13 keys because `cached_window_incomplete`
has been added
(`src/mew/patch_draft.py:11-24`).
M6.13 v0 maps all 13 executable keys.
The historical 12-code language should not cause an implementation to
drop `cached_window_incomplete`.

### 8.2 Decision Table

| Blocker code | Class | v0 lane decision |
| --- | --- | --- |
| `missing_exact_cached_window_texts` | state-limit | Do not escalate. Refresh exact cached windows first. |
| `cached_window_incomplete` | state-limit | Do not escalate. Refresh or enlarge cached window first. |
| `cached_window_text_truncated` | state-limit | Do not escalate. Refresh non-truncated context first. |
| `stale_cached_window_text` | state-limit | Do not escalate. Refresh live state, then retry tiny once. |
| `old_text_not_found` | state/anchor-limit | Do not escalate before reread or anchor repair. |
| `ambiguous_old_text_match` | contract-limit | Do not escalate. Narrow old text or split hunks. |
| `overlapping_hunks` | contract-limit | Do not escalate by default. Merge or split hunks first. |
| `no_material_change` | possible abstraction-limit | Eligible when task_shape is abstract or repeated. |
| `unpaired_source_edit_blocked` | policy-limit | Do not escalate. Add paired test edit or revise scope. |
| `write_policy_violation` | policy-limit | Do not escalate. Revise write scope. |
| `model_returned_non_schema` | contract/model mixed | Retry wrapper once; escalate only if repeated and semantic context is hard. |
| `model_returned_refusal` | provider/prompt mixed | Reviewer-command eligible; automatic only with refusal classification. |
| `review_rejected` | semantic/model mixed | Eligible when findings are conceptual, cross-file, or design-level. |

This table follows the Phase 0 trigger guidance: state-refresh blockers
refresh first, schema problems do not automatically become intelligence
problems, and `review_rejected` / `no_material_change` are the strongest
semantic candidates
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:343-387`).

### 8.3 Automatic vs Reviewer Command

Automatic escalation is default-on only for:
- eligible blocker code
- abstract or repeated task shape
- budget green
- exact state fresh
- no prior deliberation for the same blocker instance
Reviewer command can request deliberation for:
- `review_rejected`
- `no_material_change`
- `model_returned_refusal`
- repeated `model_returned_non_schema`
Reviewer command cannot request deliberation for:
- stale cached windows
- missing cached windows
- write-policy violations
- exhausted budget
The command may still ask mew to explain why escalation is blocked.

## 9. Cost Budget Model

### 9.1 Budget Shape

M6.13 defines budget structure, not final numbers.
Caps exist at three levels:
- per-session
- per-iteration
- per-task
Each cap may be expressed in:
- attempt count
- wall-clock seconds
- provider token usage when available
- estimated cost units when exact usage is unavailable
The budget object:

```json
{
  "session_cap": {},
  "iteration_cap": {},
  "task_cap": {},
  "reserved": {},
  "spent": {},
  "remaining": {},
  "budget_policy_version": "m6_13.v0"
}
```

No v0 implementation should hard-code final values from this document.
The values belong in config or a later implementation plan.

### 9.2 Budget Events

`deliberation_cost_events` is required in the session trace.
Event kinds:
- `budget_checked`
- `budget_reserved`
- `budget_spent`
- `budget_blocked`
- `budget_exceeded`
- `fallback_to_tiny`
- `usage_missing`
- `usage_estimated`
Event shape:

```json
{
  "event": "budget_reserved",
  "todo_id": "todo-17",
  "lane_attempt_id": "lane-deliberation-todo-17-attempt-1",
  "cap_scope": "task",
  "reserved_units": 1,
  "remaining_units": 2,
  "created_at": "..."
}
```

### 9.3 Budget Failure Behavior

When budget is exceeded:
1. record `budget_blocked`
2. do not call the deliberation model
3. keep tiny available
4. annotate the active blocker
5. surface the reason in follow-status
Budget failure is not a work-loop crash.
It is a lane decision.

### 9.4 Why Budget Is Load-Bearing

The Phase 0 reference says a deliberation lane without budget caps is a
leak, not a lane
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:365-368`).
It also cites literature showing that test-time compute gains are
difficulty-dependent and not monotone across all tasks
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:111-133`,
`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:254-271`).
M6.13 therefore treats budget as a correctness condition.

## 10. Interaction with M6.11 and M6.12

### 10.1 M6.11

M6.13 extends M6.11.
It does not close M6.11.
It does not change the M6.11 blocker vocabulary as a prerequisite.
It consumes the current executable blocker map.
It preserves exact cached-window and paired source/test discipline.
It preserves the patch-draft compiler as the artifact validator.
It preserves replayability.
The tiny lane remains the default route for write-ready drafting.

### 10.2 M6.12

M6.12 is a reading surface.
M6.13 does not implement that surface.
M6.13 adds lane fields that M6.12 can read.
The planned `--m6_12-report` mode should support `--lane <name>`.
M6.12's canonical-vs-derived split remains intact.
Lane metadata is canonical bundle metadata.
Lane summaries and lane recurrence views are derived.

### 10.3 M6.9

M6.9 owns durable coding intelligence.
M6.13 does not execute M6.9 Phase 2 through Phase 4.
M6.13 Phase 3 depends on the M6.9 reasoning-trace write gate and ranked
recall path.
If those surfaces are unavailable, M6.13 Phase 3 cannot close.
M6.13 must not fake ranked recall with a bespoke lane-local lookup.

## 11. CLI Surface Additions

### 11.1 Work Loop Controls

Implementation may add:

```text
mew work ... --lane tiny
mew work ... --lane mirror
mew work ... --deliberate
mew work ... --no-auto-deliberation
```

These are provisional.
The design does not require exact flag names.
Required semantics:
- `--lane tiny` forces normal tiny behavior
- `--lane mirror` enables mirror proof mode without authoritative writes
- `--deliberate` requests reviewer-command escalation
- `--no-auto-deliberation` disables automatic escalation for that run
Any explicit deliberation flag must still obey budget and state-refresh
rules.

### 11.2 Proof Summary Filter

M6.13 requires a future M6.12-compatible filter:

```text
mew proof-summary <artifact_dir> --m6_12-report --lane <name>
```

This is a reader contract.
It is not a requirement that M6.13 implement M6.12.

### 11.3 Follow-Status Fields

Follow-status should show:
- active lane
- supported lanes
- latest lane transition
- latest blocker code
- escalation eligibility
- budget remaining summary
- latest deliberation outcome
- fallback reason
- internalization review state
These fields should be concise.
They should not dump deliberation transcript.

## 12. Representative Examples

### 12.1 State Blocker Does Not Escalate

Tiny lane returns `stale_cached_window_text`.
The trigger table classifies it as a state-limit blocker.
Mew records:

```json
{
  "decision": "do_not_escalate",
  "reason": "state_refresh_required",
  "fallback_lane": "tiny"
}
```

The next action is a targeted reread.
No deliberation budget is spent.

### 12.2 Conceptual Review Rejection Escalates

Tiny lane produces a validated patch.
Reviewer rejects it because the design misses a cross-module invariant.
The blocker is `review_rejected`.
The task shape is `abstract`.
Budget reservation succeeds.
Deliberation produces a structured explanation of the invariant and a
new patch strategy.
Tiny later drafts from that strategy.
The reviewer approves.
The reasoning is proposed as a deep reasoning trace.

### 12.3 Internalization Cycle

The accepted trace is written to `reasoning_trace.jsonl` with
`source_lane=deliberation`.
Later, a same-shape review rejection occurs.
M6.9 ranked recall retrieves the trace.
Tiny receives the adapted trace.
Tiny drafts a correct patch without invoking deliberation.
The reviewer confirms the trace shortened deliberation.
M6.13 can count this as the Phase 3 proof if all artifacts are present.

### 12.4 Budget Exhaustion

A second hard task tries to deliberate after the session cap is spent.
The budget check fails.
Mew records `budget_blocked`.
No high-effort model call is made.
Tiny remains available.
The user sees that deliberation was skipped by budget, not by model
failure.

### 12.5 Mirror Lane

Tiny remains authoritative.
Mirror receives the same patch proposal in shadow mode.
Mirror writes a `lane=mirror` replay bundle.
The final user-visible action is still the tiny action.
A lane-aware report can include or exclude the mirror row.

## 13. Open Questions / Deferred Decisions

1. Exact CLI flag names are deferred.
2. Final numeric budgets are deferred.
3. Final provider and model defaults are deferred.
4. Whether deliberation should use same-family effort increases first is
   deferred.
5. Whether provider usage should be exact tokens or estimated units is
   deferred.
6. Whether mirror lane should stay after Phase 1 is deferred.
7. Whether `WorkTodo.lane` can change after a successful deliberation is
   deferred; v0 should prefer tiny as final authoritative patch lane.
8. Whether `model_returned_non_schema` should ever automatically
   deliberate is deferred beyond the cautious v0 rule.
9. The exact same-shape key algorithm is deferred to implementation, but
   the proof must predeclare it before the reuse run.
10. The exact reviewer UI for internalization approval is deferred.
11. Whether deliberation traces should be shallow-only, deep-only, or
    paired by default is deferred; M6.9 Phase 2 expects shallow + deep
    pairs for reasoning-trace harvesting
    (`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:628-648`).
12. Whether M6.13 should expose lane data through JSON only or also
    text output is deferred.
13. Whether deliberation can use multiple candidate models is deferred.
14. Whether a future write-capable deliberation lane is safe is
    explicitly post-v0.

## 14. Minimal MVP (Phase 1 narrow slice)

The smallest worthwhile MVP is Phase 1 only.
It includes:
1. `WorkTodo.lane` defaulting to `tiny`.
2. Lane registry with `tiny`, `mirror`, and disabled `deliberation`.
3. Additive lane fields in replay metadata.
4. Legacy bundle reader treating missing lane as `tiny`.
5. Lane-scoped writer for mirror bundles.
6. Generalized shadow bridge used by mirror.
7. Planned M6.12 `--lane` filter contract and fixtures.
8. Follow-status display of active lane.
9. Tests proving tiny behavior is unchanged.
The MVP excludes:
- high-effort model binding
- automatic escalation
- cost budget enforcement
- deliberation result schema
- memory internalization
- reasoning-trace writes
- M6.13 close
The MVP is allowed because it de-risks schema and replay compatibility.
The MVP is not allowed to be called the milestone.

## 15. Later Expansion

### 15.1 Better Trigger Metrics

After v0, M6.12 lane-aware reports can measure which blocker families
benefit from deliberation.
That may turn the trigger table from conservative rules into measured
precision and recall.

### 15.2 Provider Matrix

Later versions may compare provider families.
The Phase 0 matrix is qualitative and warns that schema strictness,
latency, and effort controls differ by provider
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:389-437`).
M6.13 v0 should not overfit that matrix into permanent routing.

### 15.3 Multi-Lane Concurrency

Concurrent lane attempts are out of v0 scope.
Future work may run two shadow deliberation candidates under the same
budget envelope.
That needs separate accounting and reviewer UI.

### 15.4 Write-Capable Deliberation

Future deliberation might produce patch drafts directly.
V0 should avoid that.
The safer path is read-only deliberation followed by tiny-lane drafting
or existing compiler validation.

### 15.5 Memory Expansion

Future work may internalize task templates or failure shields from
deliberation.
V0 internalizes only reasoning traces.
That keeps the close proof narrow.

## 16. Success Criteria For v0

`M6.13` v0 is considered good enough to close only when:
1. `WorkTodo.lane` is additive and backward-compatible.
   Old sessions with no lane normalize to `tiny`.
   Existing active-todo fields keep their meanings.
   Tiny remains the default lane.
2. Replay bundle compatibility holds.
   Existing M6.11 legacy bundles parse without migration.
   New lane metadata is additive.
   Missing lane metadata is interpreted as `tiny`.
   New non-tiny lane bundles can use the lane-scoped layout without
   breaking the legacy resolver.
3. Phase 1 proves tiny-lane behavior is unchanged.
   The tiny write-ready prompt, effort override, compiler path, and
   fallback semantics produce the same authoritative behavior as before
   Phase 1.
   Mirror-lane failure cannot fail a tiny-lane run.
4. The generalized shadow bridge works.
   A mirror lane run records a non-authoritative lane bundle.
   The authoritative tiny result remains separate.
   A reader can reconstruct which lane was shadow and which lane was
   authoritative.
5. The deliberation model binding is explicit and observable.
   Every deliberation attempt records requested and effective backend,
   model, effort, timeout, and schema contract.
   Unsupported or remapped effort is visible in telemetry.
   No provider-specific effort label is treated as universally
   equivalent.
6. Escalation obeys the blocker table and preconditions.
   State-limit blockers refresh state instead of escalating.
   Policy-limit blockers do not escalate.
   `review_rejected` and abstract `no_material_change` can escalate
   when budget is green.
   Reviewer-command escalation exists but cannot override budget or
   stale-state blocks.
7. Budget controls are enforced.
   Per-session, per-iteration, and per-task caps are represented.
   `deliberation_cost_events` records checks, reservations, spend or
   estimates, budget blocks, and fallback.
   Budget exhaustion falls back to tiny without crashing the loop.
8. Phase 3 internalization proof is recorded.
   At least one hard task is solved or materially advanced by
   deliberation.
   Its accepted reasoning is written as a reviewer-approved
   reasoning-trace entry with `source_lane=deliberation`.
   A later same-shape task retrieves that trace through M6.9 ranked
   recall.
   The later task is solved by the tiny lane without re-invoking
   deliberation.
   Reviewer evidence confirms the trace shortened or avoided
   deliberation.
   Without this proof, M6.13 v0 is not done.
9. No companion milestone close gate changes.
   M6.9, M6.11, and M6.12 close gates remain unchanged.
   M6.13 may depend on their surfaces, but it does not rewrite their
   success criteria, proof math, or canonical artifacts.
   No `ROADMAP.md` or `ROADMAP_STATUS.md` edits are part of this design.
Not v0 criteria:
- choosing final provider defaults
- shipping multi-provider comparison
- implementing M6.12 reports
- executing M6.9 Phase 2 through Phase 4
- making deliberation write-capable
- proving statistical improvement across many tasks
If any of the nine v0 criteria fail, M6.13 v0 is not done.

## 17. Risks And Tradeoffs

### 17.1 Cost Runaway

High-effort calls can consume time and money quickly.
Budget caps are therefore correctness constraints.
The lane must fail closed to tiny when caps are exceeded.

### 17.2 Internalization Failure

The hardest risk is that deliberation helps once but does not become
durable.
That is why the close gate requires a later tiny-lane reuse proof.
Without that proof, the lane is a wrapper.

### 17.3 Schema Regression

Longer or richer model outputs can violate strict JSON contracts.
The Phase 0 reference names schema adherence drift as a high-effort
failure mode
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:278-285`).
M6.13 must measure non-schema outcomes rather than assume intelligence
solves format discipline.

### 17.4 Tiny Lane Disruption

The tiny lane is already the narrow write-ready route.
Phase 1 must not change it.
The mirror lane exists specifically to prove the lane framework without
changing tiny behavior.

### 17.5 Model Availability Changes

Vendor model menus and effort controls change.
The Phase 0 reference marks vendor model rows as time-sensitive
(`docs/REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md:91-104`).
M6.13 therefore uses model binding abstraction and requested/effective
telemetry instead of hard-coding a permanent model choice.

### 17.6 False Positive Escalation

Automatic escalation may spend budget on tasks that needed state refresh
or policy repair.
The blocker table intentionally blocks those cases.
Reviewer command remains available for exceptional semantic cases.

### 17.7 False Negative Escalation

Conservative triggers may skip a case where deliberation would help.
That is acceptable for v0.
M6.13 should first prove one durable internalization cycle, then widen
trigger recall with measured evidence.

### 17.8 Memory Pollution

Bad reasoning traces can damage later work.
The reviewer approval path and M6.9 write gate are mandatory.
Rejected deliberation outputs do not become durable memory.

### 17.9 Calibration Confusion

Lane-aware bundle metrics can be misread if old bundles lack lane fields.
The rule is simple: missing lane equals `tiny`.
Reports must show how many rows used inferred lane metadata.

### 17.10 Overfitting To One Proof

The close gate requires at least one proof cycle.
That is a minimum, not a claim of broad statistical superiority.
Later M6.12 reporting and M6.9 expected-value observation can decide
whether the benefit generalizes.

### 17.11 Boundary Drift

There is pressure to let deliberation become a second planner.
V0 resists that by keeping deliberation read-only, requiring typed
results, and routing final patch drafting back through tiny and the
existing compiler/approval path.

### 17.12 Companion-Milestone Coupling

Phase 3 depends on M6.9 ranked recall.
That coupling is intentional but must be explicit.
M6.13 may be blocked by missing M6.9 surfaces.
It must not work around that by creating a private memory system.
