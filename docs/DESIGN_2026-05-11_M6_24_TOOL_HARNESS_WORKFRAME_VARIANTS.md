# Design 2026-05-11 - M6.24 Tool Harness And WorkFrame Variants

Status: design only.

Scope: `implement_v2` M6.24 rearchitecture after the first WorkFrame variant
comparison. This document does not authorize source-code implementation changes,
live benchmark spending, or commits by itself.

## Decision

Rearchitect `implement_v2` around a shared tool/result substrate and make
WorkFrame variants small projection/policy plug-ins.

The common substrate owns:

- tool registry and tool harness;
- natural paired transcript/tool-result flow;
- typed evidence sidecars;
- artifact obligations;
- verifier freshness;
- repair-loop sidecars;
- searchable tool/evidence indexes;
- replay, compression, dogfood, debug, and benchmark artifacts.

WorkFrame variants must not own or fork those boundaries. A variant may only
change the model-visible WorkFrame projection and the policy/navigation fields
inside that WorkFrame. It must not change tool execution, provider transport,
evidence sidecar schema, benchmark harness, replay format, or the ordinary
provider loop.

Introduce a new variant:

```text
transcript_tool_nav
```

`transcript_tool_nav` makes natural tool results the short-horizon action
authority. The model receives the paired transcript result normally, decides the
next action, and uses WorkFrame for safety, navigation, searchable refs,
tool-policy hints, obligations, and forbidden actions.

`transition_contract` remains selectable by variant switch. It is a prescriptive
policy variant, not the unmeasured default policy after this rearchitecture.
If later measurement shows its stronger `required_next` contract wins without
excess bloat or blocked turns, it can be made default by configuration without
rewriting the tool harness.

## Why The Existing Variants Failed

The current `transcript_first` variant did not rebuild the loop around the
transcript. It wraps `reduce_workframe()`, detects a conflict between prompt
projection refs and transcript sidecar refs, reruns the same reducer after
dropping prompt projection events, and copies only short-horizon fields:

```text
current reducer output
  + prompt projection detected
  + transcript sidecar detected
  -> reducer rerun without prompt events
  -> replace current_phase/latest_actionable/required_next/forbidden_next
```

That is useful as a narrow fallback test. It is not a transcript-first tool
architecture because it leaves these deeper surfaces unchanged:

- provider loop shape;
- tool result return shape;
- tool registry and result summarization;
- evidence sidecar conversion;
- prompt renderer responsibilities;
- search/index behavior;
- replay/debug artifacts;
- `required_next` as a hard next-action pressure point.

The speed-proof comparison showed the consequence. `transcript_first` still
blocked with long prompts, many model turns, and late first edit. It was not
too transcript-first. It was not transcript-first enough; the model still had to
work through the same thick WorkFrame machinery.

The current `transition_contract` variant went in the opposite direction. It
made transition provenance more explicit, but it also computed
`required_next`/`required_next_basis` strongly enough that the model-visible loop
became a prescriptive contract. This improved one run shape, but it also made
the prompt/history heavier and made a later bulk patch transport failure more
likely under JSON response pressure. Treat that as evidence that
`transition_contract` is a measurable policy variant, not proof that every
variant should strengthen `required_next`.

This document is therefore not reviving the old `transcript_first` reducer
fallback. It defines the shared harness that `transcript_first` never changed,
then adds `transcript_tool_nav` as a real plug-in over that substrate.

## Architecture

Target ordinary loop:

```text
          static instructions + provider tool spec
                         |
                         v
model response ----> provider/tool loop ----> tool harness
     ^                        |                    |
     |                        |                    v
     |                        |          natural tool_result text
     |                        |                    |
     |                        v                    v
     |              paired transcript <---- tool result sidecars
     |                        |
     |                        v
     |        typed evidence + obligations + indexes
     |                        |
     |                        v
     |             WorkFrame variant plug-in
     |                        |
     |                        v
     +------ prompt renderer: transcript tail + one WorkFrame
```

Variant boundary:

```text
shared reducer inputs
  transcript cursor
  tool result index
  typed evidence sidecars
  artifact obligations
  verifier freshness
  repair-loop sidecars
  registry/policy refs
  replay/debug metadata
        |
        v
WorkFrameVariant.project(inputs)
        |
        +-- current
        +-- minimal
        +-- transcript_tool_nav
        +-- transition_contract
        |
        v
one model-visible WorkFrame projection
```

Search boundary:

```text
hot path:
  latest tool result
    -> tool_result_index / evidence_index
    -> WorkFrame refs and navigation
    -> next model action

debug/recovery only:
  model_turn_index
    -> plateau analysis, context-compression audit, replay review
    -> summarized result may become sidecar evidence
    -> next WorkFrame projection
```

There is no second model-visible frontier, todo, proof, or evidence object
beside WorkFrame.

## Common Substrate Boundaries

### Tool Registry

The registry is the durable source of tool metadata. It contains:

- stable `tool_ref` values;
- tool name, capability class, mutability class, and access policy;
- provider compatibility and input kind, such as JSON arguments or freeform
  input;
- result summarizer policy;
- schema/content hash refs for full implementation details.

WorkFrame may cite registry refs. It must not embed implementation bodies, full
schemas, or long provider-specific tool descriptions. Adding, removing, or
changing a tool updates registry artifacts and provider tool specs, not
WorkFrame schema.

### Tool Harness

The harness owns:

- provider tool-call normalization;
- tool execution;
- exactly one model-visible result per tool call;
- synthetic error results when execution, validation, permission, parsing,
  interruption, or timeout fails;
- natural result text shaped for the next model decision;
- bounded previews and output refs for large results;
- write/source mutation provenance;
- command run ids, terminal status, and output refs;
- tool-result indexing.

The harness does not know which WorkFrame variant is selected. It emits the same
tool sidecars and transcript items for every variant.

### Natural Transcript

The model sees paired tool results as ordinary transcript evidence. A tool
failure is returned as a concrete result, not hidden in controller-only state.
The transcript pair invariant is hard:

```text
one model tool_call with call_id X
one model-visible tool_result with call_id X
one sidecar observation event for X
one tool-result index entry for X
```

Missing outputs are synthesized, orphan outputs are rejected or quarantined, and
truncation must not separate the latest actionable result from its call.

### Evidence Sidecars

Typed evidence is sidecar state. It includes generic events such as:

- `tool_result`;
- `command_result`;
- `write_result`;
- `source_mutation`;
- `strict_verifier_result`;
- `probe_observation`;
- `artifact_obligation`;
- `artifact_evidence`;
- `repair_attempt`;
- `finish_gate`.

Evidence sidecars are shared by all variants. A variant can choose how much of
their current summary appears in WorkFrame, but it cannot introduce a private
evidence schema or a private conversion path.

### Artifact Obligations

Artifact obligations are generic finish/verifier contracts. They are produced
from task/verifier/test evidence and represented by refs plus compact status in
WorkFrame:

```text
obligation_ref
  kind: path | stream | glob | semantic
  status: missing | satisfied | stale | surrogate_only | unchecked
  required_for_finish: true | false
  checkability: internal_check | shell_assertion | external_verifier_only
```

Surrogate evidence can guide repair, but it cannot satisfy finish unless a
generic task/verifier rule accepts it.

### Verifier Freshness

Verifier freshness is a shared sidecar fact:

```text
latest source/config mutation
latest strict verifier result
fresh_after_latest_mutation
finish closeout requirement
```

No variant may weaken the invariant that finish requires fresh accepted proof
after the latest mutation and after active obligations are satisfied.

### Repair-Loop Sidecars

Repair-loop tracking is sidecar-only history. WorkFrame may expose the current
compact state:

```text
none | warn | plateau | blocked
```

The full repeat sequence, hypotheses, search episodes, and debug history stay
outside the ordinary prompt. A variant may recommend or disable action families
based on that state, but it must not render a second plan.

### Searchable Indexes

Two indexes are intentionally separate.

Tool/evidence search is hot-path primary:

- lookup by `call_id`, `tool_ref`, command run id, output ref, path, evidence
  kind, obligation ref, verifier id, failure family, and mutation ref;
- used by WorkFrame projection and by model-visible fetch tools when the
  current result says more output is needed;
- persisted and hash-checked per turn.

Model-turn search is debug/plateau/recovery only:

- lookup by model turn, assistant message, old plan text, historical rationale,
  or response parse errors;
- used for replay explanation, context-compression audit, plateau recovery, and
  reviewer diagnosis;
- not an ordinary next-action authority.

If hot-path progress needs model-turn search, the active WorkFrame/tool-result
summary is under-specified. The fix is to improve the tool/evidence sidecar or
the WorkFrame summary, not to load old model turns into the ordinary prompt.

## Variant Plug-In Contract

A WorkFrame variant is a deterministic projection/policy function:

```text
WorkFrameVariant.project(CommonWorkFrameInputs) -> WorkFrameProjection
```

### `CommonWorkFrameInputs`

`CommonWorkFrameInputs` is the stable typed input contract for all variants. It
subsumes the current `WorkFrameInputs` dataclass by wrapping the existing fields
with shared harness, index, registry, and migration metadata. Phase 3 may
implement it as an adapter around current `WorkFrameInputs`; the important
contract is that every variant receives the same normalized object.

Conceptual type:

```text
CommonWorkFrameInputs
  schema_version: 1
  attempt:
    attempt_id
    turn_id
    task_id
    objective
    success_contract_ref
    constraints
    budget_class
  transcript:
    natural_transcript_tail_ref
    transcript_tail_hash
    latest_tool_call_ref
    latest_tool_result_ref
    paired_call_result_index_ref
  tool_registry:
    registry_ref
    registry_hash
    active_tool_refs
    provider_tool_spec_hash
    tool_policy_index_ref
  sidecars:
    observation_event_log_ref
    typed_evidence_delta_ref
    evidence_ref_index_ref
    artifact_obligation_index_ref
    verifier_freshness_ref
    repair_loop_state_ref
    source_mutation_index_ref
  indexes:
    tool_result_index_ref
    evidence_search_index_ref
    model_turn_index_ref
    model_turn_index_usage = debug_plateau_recovery_only
  replay:
    workframe_cursor_ref
    previous_workframe_hash
    replay_manifest_ref
    compression_cursor_ref
  migration:
    source_workframe_schema_version
    fixture_conversion_version
    canonicalizer_version
  current_workframe_inputs:
    current WorkFrameInputs-compatible payload
```

Field sources:

| Field group | Source of truth | Notes |
|---|---|---|
| `attempt` | lane config, task contract, budget sidecars | Equivalent to current `WorkFrameInputs` goal/identity fields plus budget class. |
| `transcript` | provider transcript and tool harness | Natural paired call/result order is authoritative for short-horizon observation. |
| `tool_registry` | registry and provider tool-spec artifacts | Variants receive refs/hashes, not full implementation bodies. |
| `sidecars` | evidence, artifact, verifier, mutation, and repair-loop sidecars | Shared by every variant. |
| `indexes` | tool/evidence/model-turn indexes | Tool/evidence search is hot path; model-turn search is debug/recovery only. |
| `replay` | replay/debug bundle | Used for deterministic reconstruction and context compression. |
| `migration` | fixture converter and canonicalizer | Prevents v1/v2/v3 hash comparisons from being silently mixed. |
| `current_workframe_inputs` | current `WorkFrameInputs` adapter | Allows incremental porting of existing reducer tests. |

Rules:

- Every field that affects a projection hash must be canonicalized before the
  variant runs.
- The current `WorkFrameInputs` payload remains valid as a compatibility
  subobject during migration, but variants must not read old prompt projection
  fallbacks from it unless those fallbacks have been converted into shared
  sidecar events.
- If a variant needs data outside `CommonWorkFrameInputs`, the common substrate
  is missing a field; the fix is not a variant-local side channel.

It may:

- choose which WorkFrame fields are model-visible;
- decide whether `required_next` is absent, broad, advisory, or strict;
- add navigation fields inside WorkFrame;
- recommend tools by `tool_ref`;
- disable tools/actions by policy refs and evidence refs;
- summarize obligations and verifier freshness;
- cite evidence refs and searchable index refs;
- choose compact wording and caps;
- emit variant metadata to debug artifacts.

It must not:

- execute tools;
- change provider request/response parsing;
- alter the tool registry, harness, or result schemas;
- mutate evidence sidecars;
- create variant-specific benchmark harness behavior;
- change replay, dogfood, or compression semantics;
- hide paired tool results from the transcript;
- add a second ordinary model-visible state object;
- embed full tool implementation bodies or full schemas in WorkFrame.

Required variant artifacts:

```text
implement_v2/workframes/turn-XXXX/
  workframe_variant.json
  reducer_inputs.json
  prompt_visible_workframe.json
  reducer_output.workframe.json
  invariant_report.json
  prompt_render_inventory.json
```

`workframe_variant.json` records the variant name, version, projection hash, and
the shared substrate hashes it used. Switching variants must change only the
projection/policy artifacts and prompt-visible WorkFrame, not tool execution or
sidecar evidence.

## Schema Version Migration

WorkFrame `schema_version=3` is the target schema for this rearchitecture.

Relationship to prior schemas:

- v1: current compact WorkFrame fields such as `goal`, `latest_actionable`,
  `required_next`, `forbidden_next`, `changed_sources`, `verifier_state`,
  `finish_readiness`, and `evidence_refs`.
- v2: transition-contract design fields for transition provenance, artifact
  obligations, and repair-loop state.
- v3: shared-harness variant projection fields, including `variant`,
  `tool_context`, normalized `obligations`, normalized `repair_loop`,
  explicit search refs, and an explicit policy that `required_next` may be
  absent for ordinary repair.

Added or restructured v3 fields:

| Field | Source | Backfill for v1/v2 fixtures |
|---|---|---|
| `variant` | `workframe_variant.json` or variant selector | `{name: "current_legacy", schema_version: 0}` when absent. |
| `tool_context` | tool registry, policy index, tool/evidence indexes | Empty refs plus registry hash when available; otherwise `null` with conversion warning. |
| `obligations` | artifact obligation sidecar and finish readiness | Convert `finish_readiness.missing_obligations` to `missing_or_stale_refs`. |
| `repair_loop` | repair-loop sidecar | `null` when no repair-loop sidecar exists. |
| `search_refs` inside `tool_context` | tool/evidence/model-turn indexes | Backfill only refs to existing indexes; never synthesize model-turn authority. |
| `required_next.policy_strength` | variant projection | `strict` for v2 `transition_contract`, `advisory_or_absent` for `transcript_tool_nav`, `legacy` for v1. |

Fixture conversion:

- v1/v2 fixtures are converted into v3 fixture inputs before hash comparison.
- Converted fixtures record:

  ```text
  source_workframe_schema_version
  fixture_conversion_version
  canonicalizer_version
  pre_conversion_input_hash
  converted_input_hash
  converted_workframe_hash
  ```

- A live v3 WorkFrame must not rely on fixture conversion defaults.
- A v2 output hash and a v3 output hash are not directly comparable. Tests must
  compare either pre-conversion v2 hashes against v2 expectations or converted
  v3 hashes against v3 expectations.
- Same-shape comparison artifacts include `schema_version`,
  `fixture_conversion_version`, and variant selector hashes so reviewers can
  separate schema migration effects from behavior changes.

Phase linkage:

- Phase 0 closes only after the v3 migration/backfill rules and affected
  fixture inventory are written.
- Phase 3 closes only after `CommonWorkFrameInputs` canonicalization and
  v1/v2-to-v3 hash comparison rules are enforced by fastcheck.

## `transcript_tool_nav`

`transcript_tool_nav` is the baseline candidate for the next architecture pass,
not an immediate runtime default flip. It is intentionally less prescriptive
than `transition_contract`.

Model-visible behavior:

- tool results are returned naturally in the transcript;
- the model decides the next inspect/patch/verify action from the latest result;
- WorkFrame supplies safety, navigation, refs, and obligations;
- `required_next` is absent for ordinary repair when several actions are safe;
- `required_next` is used only for controller-required safety states, such as
  blocked, deterministic closeout, or finish-ready;
- `forbidden_next` remains strict for unsafe finish, stale verifier, repeated
  same-family action without new evidence, and unavailable tools.

Projection sketch:

```json
{
  "schema_version": 3,
  "variant": {
    "name": "transcript_tool_nav",
    "schema_version": 1,
    "projection_hash": "sha256:..."
  },
  "goal": {
    "task_id": "task-ref",
    "objective": "Repair the workspace to satisfy the configured verifier.",
    "success_contract_ref": "task-contract:..."
  },
  "latest_actionable": {
    "source_ref": "tool-result:turn-8:call-2",
    "tool_ref": "tool:run_command",
    "status": "failed",
    "summary": "bounded natural result summary",
    "evidence_refs": ["ev:strict-verifier:run-12"]
  },
  "tool_context": {
    "schema_version": 1,
    "registry_ref": "tool-registry:sha256:...",
    "active_tool_refs": ["tool:read_file", "tool:search_text", "tool:apply_patch", "tool:run_command"],
    "recommended_tool_refs": [
      {
        "tool_ref": "tool:read_file",
        "reason": "latest result cites a source path that has not been inspected after the failure",
        "evidence_refs": ["tool-result:turn-8:call-2"]
      }
    ],
    "disabled_tool_refs": [
      {
        "tool_ref": "tool:finish",
        "reason": "finish requires fresh verifier evidence after latest mutation",
        "until_evidence_refs": ["ev:strict-verifier:fresh-pass"]
      }
    ],
    "policy_refs": ["tool-policy:mutation-boundary:v1", "tool-policy:finish-safety:v1"],
    "fetchable_refs": ["out:run-12:stderr-full"],
    "tool_result_search": {
      "index_ref": "tool-result-index:turn-8",
      "primary": true,
      "query_hints": ["call_id", "tool_ref", "target_path", "output_ref"]
    },
    "model_turn_search": {
      "index_ref": "model-turn-index:attempt",
      "usage": "debug_plateau_recovery_only"
    }
  },
  "obligations": {
    "artifact_obligation_refs": ["artifact-obligation:final-output"],
    "missing_or_stale_refs": ["artifact-obligation:final-output"]
  },
  "verifier_state": {
    "configured_verifier_ref": "task-contract:verify",
    "last_strict_verifier_ref": "cmd:run-12",
    "status": "failed",
    "fresh_after_latest_source_mutation": true
  },
  "repair_loop": {
    "state": "warn",
    "signature_ref": "repair-signature:...",
    "disabled_action_families": ["repeat_identical_verifier_without_mutation"]
  },
  "required_next": null,
  "forbidden_next": [
    {
      "kind": "finish",
      "reason": "finish requires fresh accepted verifier and satisfied obligations",
      "evidence_refs": ["ev:strict-verifier:run-12"]
    }
  ],
  "evidence_refs": {
    "typed": ["ev:strict-verifier:run-12"],
    "sidecar": ["sidecar:tool-result:turn-8:call-2"],
    "replay": ["replay:event:turn-8:workframe"]
  }
}
```

`tool_context` rules:

- `active_tool_refs` lists refs, not schemas.
- `recommended_tool_refs` are advisory and must cite current evidence.
- `disabled_tool_refs` are policy constraints and must name what evidence would
  clear them.
- `fetchable_refs` are bounded refs the model may request through existing
  tools.
- full registry data, provider-native schemas, and implementation details live
  in `tool_registry.json` and provider tool-spec artifacts.

### Projection Logic

`transcript_tool_nav` recommendations and disables are deterministic. The model
still chooses the next action; the projection only changes tool navigation and
safety policy.

Input ordering:

1. Canonicalize `CommonWorkFrameInputs`.
2. Select the latest paired tool result by semantic event sequence, then
   provider turn, then tool-call index, then `call_id`.
3. Resolve all evidence refs through `evidence_ref_index.json`.
4. Resolve tool availability through `tool_registry.json` and
   `tool_policy_index.json`.
5. Apply the rule table below in fixed order.
6. Deduplicate recommendations/disables by `tool_ref`, keeping the first
   rule and appending later evidence refs only when they are current.
7. Cap model-visible recommendations at four entries and disables at six
   entries. Overflow is recorded in sidecar debug artifacts, not prompt text.
8. Tie-break remaining entries by registry priority, then tool ref
   lexicographic order.

Recommended tool rules:

| Condition from shared substrate | Recommended refs | Policy |
|---|---|---|
| Latest result has a fetchable output gap | output fetch/read ref for that output | Advisory; do not require fetch if visible preview is enough. |
| Latest write/edit/apply_patch failed before mutation | read/fetch exact target, retry same mutating tool only after changed input | Advisory repair; disable stale verifier and finish. |
| Source/config mutation is newer than strict verifier | configured verifier tool ref | Controller-required only when budget closeout requires it; otherwise advisory. |
| Fresh verifier failed with concrete diagnostic and target path | read/search cited target and mutating tool refs available for that target | Advisory alternatives; model chooses inspect or patch. |
| Fresh verifier failed with no useful output but fetchable refs exist | output fetch/read ref | Advisory; do not synthesize patch target. |
| Exact obligation is missing, stale, unchecked, or surrogate-only | exact artifact check, producer inspection, or configured verifier ref | Advisory unless finish is attempted; finish remains disabled. |
| Repair-loop state is `warn` or `plateau` | tool/evidence search ref, bounded diagnostic refs, or smaller-slice read/search refs | Advisory; identical action family is disabled. |
| Tool registry marks a safer specialized tool available for the current family | specialized tool ref | Advisory and must cite registry/policy ref plus evidence ref. |

Disabled tool/action rules:

| Condition from shared substrate | Disabled ref or action | Clear condition |
|---|---|---|
| Finish lacks fresh passing verifier evidence | `tool:finish` / `finish` | Fresh accepted verifier after latest mutation. |
| Required artifact obligation is missing/stale/surrogate-only/unchecked | `tool:finish` / `finish` | Obligation status becomes satisfied or external verifier accepts it. |
| Source changed after verifier | `tool:finish` / `finish` | Strict verifier passes after mutation. |
| Write failed before mutation | stale verifier action family | Successful mutation or corrected write-result evidence. |
| Repair-loop signature repeated without new evidence | identical tool/action family for that signature | New evidence signature, different target, mutation, or blocked state. |
| Tool registry marks tool unavailable, denied, deprecated, or incompatible | that `tool_ref` | Registry/policy changes in a later turn. |
| Model-turn search would be needed for ordinary action | model-turn search as hot-path action | Tool/evidence summary or sidecar evidence is repaired. |

`required_next` policy:

- ordinary inspect/patch/verify repair keeps `required_next=null` when at least
  two safe actions are plausible;
- `required_next.kind=run_verifier` is allowed only when source freshness or
  closeout policy makes verifier execution the only safe next class;
- `required_next.kind=blocked` is allowed only when no safe tool/action remains
  under current evidence and budget;
- `required_next.kind=finish` is allowed only when finish readiness is already
  satisfied;
- recommendations must never be worded as mandatory unless they are mirrored in
  `required_next` for one of the controller-required states above.

## `transition_contract` As A Switchable Policy

`transition_contract` remains available as:

```text
workframe_variant=transition_contract
```

It consumes the same common substrate:

```text
same paired transcript
same tool_result_index
same typed evidence sidecars
same artifact obligations
same verifier freshness
same repair-loop sidecars
same benchmark harness
same replay artifacts
```

The variant changes only projection and policy:

- it can render `transition_contract` provenance inside WorkFrame;
- it can compute stricter `required_next`;
- it can classify prescriptive rule ids;
- it can disable broader action families earlier.

It must not require a different tool harness or evidence schema. Restoring it
after `transcript_tool_nav` means changing the variant selector and comparing
the same-shape artifacts, not rewriting runtime plumbing.

Adoption rule:

- Do not flip `DEFAULT_WORKFRAME_VARIANT` in Phase 4. Phase 4 introduces
  `transcript_tool_nav` and runs it only through explicit
  `workframe_variant=transcript_tool_nav` selectors.
- Keep the current runtime default unchanged through Phase 6 so existing proof
  gates are not silently rebaselined.
- In Phase 7, compare explicit variants on the same shared substrate. Only
  Phase 7 may select a new default.
- If Phase 7 selects `transcript_tool_nav`, flip the runtime default in a
  separate implementation change after reviewers accept the measured comparison.
- If Phase 7 selects `transition_contract`, keep or restore it as default only
  because measurement shows its prescriptive policy improves step shape without
  unacceptable bloat, stale `required_next`, over-blocking, or bulk-patch
  transport failures.

## Responsibilities

| Component | Owns | Must not own |
|---|---|---|
| Tool registry | tool refs, capability classes, input kinds, provider compatibility, policy refs, full schema hashes | WorkFrame next-action decisions |
| Tool harness | execute tools, pair calls/results, natural result text, previews/output refs, mutation provenance | variant-specific behavior |
| Provider loop | sampling, response parsing, follow-up after tool calls, transcript adjacency | evidence semantics or WorkFrame policy |
| Evidence sidecar | typed events, artifact obligations, verifier freshness, repair signatures, indexes | model-visible planner text |
| WorkFrame | one compact model-visible state projection, safety, navigation, refs, forbidden actions | tool execution, full evidence, full schemas, alternate frontier |
| Prompt renderer | static instructions, transcript tail, exactly one WorkFrame section, prompt inventory | hidden fallback projection authority |
| Benchmark harness | variant selection, same-shape metrics, artifact collection | variant-specific tool runtime |
| Replay/debug | deterministic reconstruction, hashes, diffs, invariant reports | live-only diagnosis |

## Validation And Observability

Every turn must be diagnosable offline from artifacts.

Required shared artifacts:

```text
implement_v2/
  tool_registry.json
  tool_policy_index.json
  natural_transcript.jsonl
  tool_results.jsonl
  tool_result_index.json
  model_turn_index.json
  evidence_ref_index.json
  typed_evidence_delta.jsonl
  artifact_obligation_index.json
  verifier_freshness.json
  repair_loop_state.json
  prompt_render_inventory.json
  replay_manifest.json
  provider_request_inventory.json
  provider_response_inventory.json
  workframes/
    turn-XXXX/
      workframe_variant.json
      reducer_inputs.json
      prompt_visible_workframe.json
      reducer_output.workframe.json
      invariant_report.json
      workframe_diff.json
      workframe_cursor.json
```

Required hashes:

- tool registry hash;
- provider tool-spec hash;
- natural transcript tail hash;
- tool result index hash;
- model turn index hash;
- evidence ref index hash;
- typed evidence delta hash;
- artifact obligation index hash;
- verifier freshness hash;
- repair-loop state hash;
- WorkFrame input hash;
- WorkFrame projection hash;
- prompt render hash;
- provider request/response inventory hash;
- benchmark config and variant selector hash.

Hard invariants:

- ordinary prompt has exactly one dynamic WorkFrame state object;
- no `frontier_state_update`, `active_work_todo`,
  `lane_hard_runtime_frontier`, full proof manifest, full oracle bundle, or
  full typed evidence object appears as ordinary prompt state;
- every provider-visible tool call has one provider-visible result;
- every model-visible tool result has one sidecar observation event;
- every semantic tool result has either typed evidence refs or an explicit
  `no_semantic_evidence` classification;
- every WorkFrame evidence ref resolves through `evidence_ref_index.json`;
- a variant cannot alter tool execution, tool schemas, evidence sidecar schema,
  or benchmark harness behavior;
- switching variants on identical sidecars changes only WorkFrame projection,
  prompt render, and variant artifacts;
- finish is forbidden when verifier evidence is stale or required obligations
  are missing, stale, surrogate-only, or unchecked;
- WorkFrame does not embed full tool implementation bodies or full schemas;
- tool/evidence search is hot-path primary;
- model-turn search is not used as ordinary next-action authority;
- WorkFrame byte target remains `<= 4096` and red cap remains `<= 6144`
  unless a reviewed gate accepts a measured tradeoff.

### Byte Cap Policy

The `4096` byte target and `6144` byte red cap are retained from the existing
WorkFrame design and code constants. They are policy caps, not proof that those
exact numbers are optimal.

Rationale:

- `4096` bytes is large enough for one compact current-state object with refs,
  safety blockers, and a few navigation hints, while keeping most ordinary
  prompt budget available for static instructions, task contract, and the
  natural transcript/tool-result tail.
- `6144` bytes is a hard warning band at 1.5x the target. It catches projection
  bloat before the WorkFrame starts competing with transcript evidence or
  increasing JSON/tool-response failure pressure.
- The variant speed proof showed that large prompt/history pressure can
  coincide with blocked runs; the caps are meant to force that pressure into
  measured artifacts instead of hidden prompt growth.

Measurement policy:

- Phase 0 records current WorkFrame byte distribution by variant where fixtures
  exist.
- Phase 4 records `transcript_tool_nav` p50/p95/max WorkFrame bytes and
  tool-context entry counts.
- Phase 7 compares WorkFrame bytes, full prompt chars, provider-visible
  tool-result bytes, model turns, and first-edit/first-verifier timing across
  variants.
- Raising or lowering caps requires a reviewed design note with artifact
  evidence. A cap change must update invariants, fixture expectations, and
  same-shape comparison rules in the same phase.

Tool-result search fixtures:

- lookup by `call_id` returns natural result, sidecar observation, typed
  evidence refs, output refs, and mutation refs;
- lookup by command run id returns terminal status, bounded stdout/stderr
  previews, and full output refs;
- lookup by path returns relevant reads, writes, diagnostics, artifacts, and
  verifier refs;
- lookup by artifact obligation returns exact evidence, surrogate evidence,
  freshness state, and finish blockers;
- lookup by failure family returns latest failure and repair-loop signature;
- lookup by output ref returns fetch policy and max fetch bytes;
- model-turn search fixtures prove the same failure can be debugged, but the
  ordinary hot-path projection must not depend on them.

Micro next-action checks:

- failed write result is naturally visible and WorkFrame disables stale
  verifier/finish rather than requiring old prompt fallback;
- source mutation with no later verifier disables finish and recommends or
  requires verifier closeout depending on budget state;
- fresh verifier failure exposes the failure result and evidence refs while
  allowing the model to choose bounded inspect or patch when both are safe;
- missing exact obligation blocks finish and recommends exact proof/producer
  inspection without hard-coding a solver path;
- repeated same-family repair disables identical retries and points to
  tool/evidence search or blocked state;
- output truncation recommends bounded output fetch through fetchable refs;
- context compression with no new semantic event preserves tool/evidence refs,
  verifier freshness, obligations, and forbidden actions.

Same-shape comparison:

- compare variants with identical tool registry, harness, evidence sidecars,
  benchmark config, and provider loop;
- record first tool, first edit, first verifier, command count, edit count,
  verifier count, model turns, prompt chars, tool-result bytes, WorkFrame
  bytes, result-search hits, repair-loop repeats, artifact obligation
  visibility, and finish-blocker correctness;
- compare against saved reference traces by generic step shape:

```text
cheap/current evidence -> coherent mutation -> verifier/exact artifact check
  -> latest failure repair or finish/blocked with cited refs
```

The comparison must not encode task-specific solver commands or artifact paths.

## Phases And Close Gates

Each phase is independently implementable and reviewable.

### Phase 0: Design Freeze And Inventory

Implementation scope:

- no runtime behavior change;
- inventory current tool registry, prompt tool specs, WorkFrame variants,
  sidecar artifacts, and variant proof artifacts;
- write the shared substrate schemas and migration notes;
- record which current artifacts are missing for offline diagnosis.

Validation:

- docs reviewed;
- artifact inventory script or manual fixture enumerates current coverage;
- no source implementation or live benchmark required.

Close gate:

- reviewers agree on substrate boundaries and variant plug-in contract;
- `CommonWorkFrameInputs` field groups, sources, and current
  `WorkFrameInputs` compatibility wrapper are specified;
- v3 schema migration/backfill and fixture conversion rules are specified;
- `transcript_first` failure is explicitly classified as a narrow fallback, not
  the target architecture;
- `transition_contract` is classified as a prescriptive selectable policy.

### Phase 1: Common Tool Harness Contract

Implementation scope:

- make paired tool call/result contract explicit for all tools;
- return synthetic model-visible error results for parse/validation/tool
  failures;
- write natural result text plus output refs;
- record tool registry refs and provider tool-spec hashes.

Validation:

- fixture tests for success, failure, timeout, denied, interrupted, parse error,
  empty output, large output, and mutation result;
- invariant check: no tool call without result and no result without call;
- replay proves transcript adjacency survives truncation/compression.

Close gate:

- every semantic tool result has an observation event and index entry;
- variants can be switched without changing tool outputs.

### Phase 2: Evidence Sidecar And Hot-Path Indexes

Implementation scope:

- convert observations to typed evidence sidecars;
- create artifact obligation, verifier freshness, and repair-loop sidecars;
- create `tool_result_index.json` and `evidence_ref_index.json`;
- create `model_turn_index.json` but mark it debug/recovery only.

Validation:

- fixtures for command, write, source mutation, verifier, probe, artifact,
  repair-loop, output-gap, and finish-gate evidence;
- search fixtures for call id, path, evidence kind, obligation, output ref, and
  failure family;
- invariant check rejects unresolved refs and hot-path model-turn search use.

Close gate:

- WorkFrame projection can be recomputed from sidecars and indexes only;
- finish safety is at least as strict as the prior WorkFrame path.

### Phase 3: Variant API And Projection Renderer

Implementation scope:

- implement the plug-in API over shared inputs;
- port `current`, `minimal`, and `transition_contract` onto the API;
- ensure prompt renderer always emits the same static shape:

```text
static instructions
task contract/digest
natural transcript tail
one WorkFrame projection
```

Validation:

- same inputs across variants produce identical substrate hashes;
- variant switch changes only WorkFrame/prompt projection artifacts;
- prompt inventory detects old frontier/todo/proof/evidence leakage.

Close gate:

- `CommonWorkFrameInputs` is canonicalized before every variant projection;
- v1/v2 fixtures either compare within their original schema or pass through
  explicit v3 fixture conversion before hash comparison;
- benchmark harness records variant name and shared substrate hashes;
- replay can rerun the same sidecars under multiple variants offline.

### Phase 4: `transcript_tool_nav`

Implementation scope:

- add `transcript_tool_nav` projection;
- add `tool_context` refs and navigation fields;
- reserve hard `required_next` for finish-ready, closeout, blocked, or other
  controller-required safety states;
- use advisory recommended/disabled tool refs for ordinary repair.

Validation:

- micro next-action checks listed above;
- WorkFrame byte cap checks;
- tool-context fixtures prove no full schemas or implementation bodies are
  embedded;
- replay proves natural transcript remains the short-horizon authority.

Close gate:

- ordinary repair does not require a prescriptive `required_next`;
- deterministic recommendation/disable rules are covered by fixtures and cite
  current evidence refs;
- finish safety, obligations, verifier freshness, and no-repeat policy remain
  strict;
- reviewers can debug a bad next action from local artifacts;
- runtime default is not flipped in this phase. All `transcript_tool_nav`
  validation uses explicit variant selectors.

### Phase 5: Prescriptive `transition_contract` Compatibility

Implementation scope:

- keep `transition_contract` selectable through the same variant API;
- move any remaining transition-specific runtime assumptions into projection
  policy or sidecar-neutral rule tables;
- ensure its strict `required_next` basis cites the shared evidence refs.

Validation:

- same sidecar fixture runs under `transcript_tool_nav` and
  `transition_contract`;
- diffs show only projection/policy changes;
- strict required-next fixtures include rule ids, evidence refs, and byte caps.

Close gate:

- restoring `transition_contract` needs only a variant selector change;
- no tool harness, evidence sidecar, provider loop, or benchmark harness rewrite
  is needed.

### Phase 6: Replay, Compression, Dogfood, And Observability

Implementation scope:

- complete per-turn debug bundle;
- add hash reproduction checks;
- preserve WorkFrame refs and safety state across context compression;
- wire dogfood assertions for substrate and variant invariants.

Validation:

- replay recomputes WorkFrame projections from sidecars;
- compression with no semantic event preserves verifier freshness,
  obligations, forbidden actions, and index refs;
- dogfood checks one representative repair, one blocked finish, and one plateau
  recovery path;
- debug artifact completeness fastcheck passes.

Close gate:

- a bad next action can be diagnosed offline without a live benchmark rerun;
- context compression does not reintroduce a second recovery card.

### Phase 7: Controlled Same-Shape Comparison

Implementation scope:

- run fastcheck/micro/replay first;
- then run one same-shape diagnostic per reviewed comparison plan;
- compare `transcript_tool_nav`, `transition_contract`, and any retained
  baseline using the same substrate and metrics.

Validation:

- step-shape metrics recorded;
- prompt/tool/result byte metrics recorded;
- artifact obligations and finish blockers verified;
- no task-specific solver rule added.

Close gate:

- green: chosen default improves or preserves safety and moves the loop toward
  current-evidence -> coherent mutation -> verifier/exact proof -> latest
  repair;
- yellow: safety is intact and any regression has a written accepted tradeoff;
- red: stale evidence, surrogate finish, missing paired result, variant runtime
  fork, unresolved evidence refs, repeated same-family loop, or WorkFrame bloat.
- default flip decision is written explicitly: keep current default, switch to
  `transcript_tool_nav`, or keep/restore `transition_contract`, with measured
  evidence and a follow-up implementation task if code needs to change.

## Non-Goals

- No source-code implementation in this design pass.
- No task-specific solver rules, benchmark-specific command recipes, or
  hard-coded artifact paths.
- No new model-visible frontier, todo, proof, or evidence object beside
  WorkFrame.
- No weakening of finish safety, verifier freshness, artifact obligations, or
  replay requirements.
- No use of model-turn search as the ordinary next-action mechanism.
- No embedding of full tool schemas, implementation bodies, or large sidecar
  payloads inside WorkFrame.
- No provider-native transport redesign beyond the contracts needed for the
  shared harness to expose refs and natural results consistently.
- No broad measurement campaign until the phased validation gates are green or
  explicitly accepted yellow.

## Failure And Escalation Criteria

Escalate to tool-harness repair if:

- a model-visible tool call lacks a model-visible result;
- parse/validation/tool failures do not become paired natural results;
- bulk mutation transport fails before producing a tool result;
- tool results are not searchable by call id or output ref.

Escalate to evidence-sidecar repair if:

- WorkFrame needs hidden replay-only detail for ordinary action;
- evidence refs are missing, stale, unresolved, or variant-specific;
- artifact obligations cannot be represented generically;
- verifier freshness cannot be recomputed from sidecars.

Escalate to WorkFrame projection repair if:

- `transcript_tool_nav` over-constrains ordinary repair;
- `transition_contract` emits stale or oscillating `required_next`;
- WorkFrame exceeds byte caps for ordinary turns;
- forbidden actions are missing for unsafe finish or repeated identical repair.

Escalate to repair/debug search if:

- tool/evidence search cannot localize a plateau;
- repeated same-family repair persists after disabled identical actions;
- model-turn search is needed to explain historical drift. The search output
  must return as sidecar evidence and a compact WorkFrame update, not a second
  prompt object.

Escalate beyond WorkFrame variants only if:

- shared substrate invariants are green;
- multiple variants have been compared on the same sidecars and benchmark
  harness;
- the remaining gap is not explained by tool transport, evidence conversion,
  projection policy, or debug/search observability.

## Resident-Agent Requirements

This architecture preserves mew's resident-agent requirements:

- replay: every WorkFrame projection is recomputed from sidecar events and
  hashes;
- context compression: reentry renders the same single WorkFrame from durable
  cursors when no semantic event changed;
- dogfood: substrate and variant invariants are testable locally before live
  benchmark spending;
- durable evidence: tool results, typed evidence, obligations, verifier
  freshness, and repair-loop state persist outside prompt tokens;
- provenance: every recommendation, disabled tool/action, obligation, finish
  decision, and replay state cites refs to tool results or sidecar evidence.

## Reviewer Acceptance Criteria

Accept this design if reviewers agree that:

- the shared tool harness, evidence sidecars, indexes, replay, and benchmark
  artifacts are outside the variant boundary;
- `transcript_tool_nav` is materially different from the current
  `transcript_first` reducer fallback;
- `transition_contract` remains restorable by variant switch without a harness
  rewrite;
- WorkFrame can guide tools through refs and policy without embedding full tool
  bodies or schemas;
- tool/evidence search and model-turn search have separate authority levels;
- validation includes artifacts, hashes, invariants, search fixtures, micro
  next-action checks, and same-shape comparison;
- phases can be implemented and reviewed independently;
- the design avoids task-specific solver rules and avoids adding a second
  ordinary model-visible state object.
