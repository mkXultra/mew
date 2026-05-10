# Design 2026-05-11 - M6.24 Transition Contract Runtime Repair Redesign

Status: implementation in progress.

Implementation note 2026-05-11:

- Phase 0 was committed in `f90c779`.
- Phase 1-3 are implemented in the reducer path:
  - saved runtime-artifact repeat fixture:
    `tests/fixtures/implement_v2/transition_contract_runtime_artifact_missing.json`;
  - typed `runtime_artifact_missing` normalization;
  - same-key repeat budget and required-next transitions;
  - post-failure inspection collapse from "diagnose" to patch/block decision.
- Phase 4 has an initial implementation for prompt-visible WorkFrame slimming:
  full reducer output stays in sidecar/debug artifacts, while the normal prompt
  gets only the compact current phase, latest actionable, required-next,
  forbidden-next, verifier, and finish-readiness card.
- Phase 5/6 are not closed yet. Before live spend, run focused tests, saved
  replay/micro checks, and a 10 minute step-shape diagnostic.

Scope: `implement_v2` `transition_contract` runtime repair loop only,
specifically the conversion from runtime failure evidence to WorkFrame
`required_next`. This design keeps `transition_contract` as the default
WorkFrame variant. It does not authorize a new WorkFrame variant or any
task-specific benchmark solver.

## Problem

The latest same-shape speed proof after the `apply_patch` transport repair
shows that the transport blocker is gone but the runtime repair loop is still
too loose.

Evidence:

- `proof-artifacts/terminal-bench/workframe-variant-speed-proof-make-mips-interpreter-transition-contract-after-apply-patch-20260511.json`
- Harbor job
  `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-speed-proof-wf-transition-contract-20260511-004240/.../make-mips-interpreter__h9ZmspQ`
- `parse_error_count=0`, so the line-array `apply_patch` transport repair held.
- Reward remained `0.0`.
- The job took about 23 minutes, with `model_turns=38`,
  `prompt_chars=1508797`, `verifier_count=11`, and
  `stop_reason=implement_v2_blocked`.
- The final WorkFrame was `variant=transition_contract`,
  `current_phase=repair_after_verifier_failure`, invariant status `pass`.
- The latest failure family is `runtime_artifact_missing`: the verifier expected
  `/app/first_frame.ppm`, the artifact was missing before and after the run, the
  command was killed/interrupted after no observable artifact progress, and the
  structured finish gate blocked on `verifier_fail` plus
  `runtime_artifact_missing`.

The failure is not that the model cannot call the patch tool. It is that the
loop repeatedly turns the same missing runtime artifact evidence into another
patch-plus-verifier attempt instead of deterministically requiring inspection of
the exact producer, artifact path, and prior mutation state, or stopping when
the same evidence has repeated too many times.

## Goal

Keep `transition_contract` as the default WorkFrame variant and make its repair
transition from runtime failure evidence to the next patch action shorter, more
deterministic, and observable.

The target loop is:

```text
runtime tool result
  -> typed runtime failure family
  -> transition_contract state transition
  -> one reducer-owned required_next
  -> patch, inspect, verifier, or blocked state
```

The model should see a compact transition summary and an unambiguous
`required_next`. Raw command output, tool history, artifact checks, and full
execution records should remain in sidecars with stable evidence refs.

## Non-Goals

- No new WorkFrame variant.
- No adoption of `minimal` or `transcript_first` as the repair direction.
- No task-specific frame-hook, MIPS, Doom, VM, or `make-mips-interpreter` prompt
  hacks.
- No provider-native tool redesign in this document.
- No weakening of finish safety or verifier freshness.
- No broad hot-path redesign outside `transition_contract` runtime failure
  evidence to `required_next` conversion.

## Proposed Scoped Redesign

### 1. Typed Runtime Failure Normalization

Add a `transition_contract`-owned normalized runtime failure family layer for
the two current shapes:

- `runtime_artifact_missing`: a verifier/runtime command completed, failed,
  timed out, or was interrupted, and one or more required artifacts failed
  checks such as exists, non-empty, or header/content.
- `runtime_artifact_missing.silent_verifier_repeat`: the same verifier/artifact
  key repeats with no stdout/stderr progress and no artifact freshness progress.

The normalized record should include only decision-grade fields:

- family and optional subfamily;
- artifact id/path and failed checks;
- command run id, tool run record id, verifier id, and artifact evidence id;
- producer substep or producer path if known;
- latest source mutation ref and whether it occurred before the failing
  verifier;
- whether there was observable runtime progress;
- stable repeat key, for example
  `family + verifier_contract_id + artifact_path + failed_checks`;
- refs to sidecar evidence, not expanded evidence bodies.

This is a normalization of existing evidence. It is not a new model-visible
planning object and not a replacement for WorkFrame.

### 2. Transition Rule Table

`transition_contract` should own a small rule table that maps:

```text
failure_family + prior mutation/verifier state + repeat state -> required_next
```

Initial table:

| Condition | Required next |
|---|---|
| `runtime_artifact_missing`, latest source mutation exists, verifier is fresh after that mutation, repeat count below budget, producer path known | `patch_or_edit` the producer path, then run the configured verifier |
| `runtime_artifact_missing`, producer path or producer substep unknown | `inspect_latest_failure` using artifact evidence refs and exact producer/artifact paths before another patch |
| `runtime_artifact_missing`, no source mutation since last identical miss | `inspect_latest_failure`; do not rerun the same verifier unchanged |
| `runtime_artifact_missing.silent_verifier_repeat`, repeat count below hard block threshold | `inspect_latest_failure` for command lifecycle, producer hook, artifact write path, and output refs |
| Same verifier/artifact failure repeated beyond budget after at least one patch and verifier | `blocked` with reason `repeated_runtime_artifact_missing_without_new_evidence` |
| Fresh passing verifier after latest mutation | `finish` if all finish obligations are satisfied |

Every rule emits:

- `rule_id`;
- concise reason;
- required next kind;
- target paths or inspection target paths;
- evidence refs;
- forbidden alternatives, especially unchanged verifier rerun and finish.

### 3. Repetition Budget

Track repeated failures by normalized repeat key. The initial default should use
`N=3`, matching the existing runtime repeat threshold shape unless fixture
evidence argues for a smaller value.

Budget behavior:

- First occurrence: permit a targeted patch when producer evidence is known.
- Second occurrence: require inspection unless the latest inspection already
  resolved a new producer fact.
- Third occurrence: require exact producer inspection or a different verifier
  observation with cited new evidence.
- Above budget: block or stop with a structured reason instead of spending more
  patch/verifier turns on the same artifact miss.

The budget is not a turn counter. It is keyed to the repeated verifier/artifact
failure so unrelated failures do not poison the current repair.

### 4. Prompt Projection

The normal prompt should expose only:

- current WorkFrame;
- latest transition summary;
- normalized failure family and repeat count;
- `required_next` and `forbidden_next`;
- evidence refs needed to fetch raw detail.

Raw tool history, command output, artifact evidence bodies, execution contracts,
and per-turn trace details stay in sidecars. If the model needs raw detail, the
`required_next` should be an inspection/read action naming the exact refs or
paths, not another broad patch.

Close target: the projected dynamic repair state should grow by transition
summary size, not by repeated command/tool history. Prompt byte impact must be
measured before live proof.

### 5. Observability

Each transition should write a trace record containing:

- transition id, WorkFrame input hash, output hash, and rule id;
- normalized failure family/subfamily;
- prior phase, next phase, and selected `required_next`;
- evidence refs and sidecar refs;
- repeat key and repeat counter;
- prompt byte impact for WorkFrame and transition projection;
- first-write metrics and verifier metrics for the attempt;
- whether the rule allowed patch, required inspection, or blocked.

Reviewers should be able to answer, from artifacts alone, why a repeated
missing-artifact verifier led to patch, inspect, verifier, or block.

### 6. Fast Validation Before Live Spend

Validation must start with saved evidence and micro next-action checks:

- fixture from the latest Harbor artifact;
- replay of the final and repeated missing-artifact transitions;
- focused reducer tests for the rule table;
- prompt projection byte checks;
- micro next-action check that proves the repeated first-frame artifact miss
  maps to inspect or block at the configured repeat count.

Only after those pass should one same-shape 10 minute step-shape diagnostic run.
Speed proof is reserved for after fast checks and the 10 minute step-shape gate
show the intended loop shape.

## Phases And Close Gates

### Phase 0: Default Switch And Tests

Close criteria:

- `DEFAULT_WORKFRAME_VARIANT == "transition_contract"`.
- Omitted and blank `workframe_variant` resolve to `transition_contract`.
- Explicit `workframe_variant=current` still resolves to the current reducer.
- Registry/default tests and directly touched tests pass.

### Phase 1: Design-Only Fixtures And Diagnostic From Latest Artifact

Close criteria:

- A saved-artifact fixture or fixture spec identifies the final repeated
  `runtime_artifact_missing` evidence from the latest speed proof.
- The fixture records repeat key, artifact path, verifier refs, mutation refs,
  and expected required-next result.
- No runtime behavior changes in this phase.

### Phase 2: Reducer Rule Table And Typed Failure Normalization

Close criteria:

- `runtime_artifact_missing` and repeated silent runtime artifact verifier
  evidence normalize deterministically from sidecar inputs.
- Rule-table tests cover patch, inspect, verifier, finish, and block outcomes.
- WorkFrame invariant tests pass with transition records attached.

### Phase 3: Repetition Budget And Required-Next Transition Behavior

Close criteria:

- Same verifier/artifact repeat keys increment across replayed sidecar events.
- Repeated same-family failures change `required_next` from patch/verifier to
  inspect exact producer, then to block after budget.
- Unrelated verifier failures do not consume the artifact-missing budget.

### Phase 4: Prompt Projection Slimming And Sidecar Evidence Refs

Close criteria:

- Normal prompt includes transition summary and `required_next`, not raw
  repeated evidence bodies.
- Raw artifact/tool/command detail remains available by sidecar ref.
- Prompt byte metrics show bounded repeated-failure growth:
  - each additional same-key runtime-artifact transition adds at most 2,000
    prompt chars to the normal WorkFrame projection;
  - the replay fixture's total prompt chars stay below the 2026-05-11 baseline
    prompt chars for the same trace (`1,508,797`);
  - raw command/tool bodies are absent from the normal prompt and present only
    through cited sidecar refs.

### Phase 5: Fast Checks And 10 Minute Step-Shape Gate

Close criteria:

- Focused tests, saved-artifact replay, prompt byte checks, and micro
  next-action checks pass.
- Saved replay/micro checks show deterministic transition thresholds:
  - first repeated same-key runtime-artifact miss keeps repair available;
  - second same-key miss requires an explicit inspect of the exact producer
    command/output path before another verifier run, unless the latest
    inspection resolved a new producer fact;
  - fourth same-key miss blocks with a structured reason.
- One same-shape 10 minute diagnostic satisfies either success or controlled
  stop:
  - verifier count is at most 5, or the run blocks before a 6th same-key
    verifier attempt;
  - model turns are at most 19, or the run blocks before turn 20 with
    `repeat_key`, `evidence_refs`, and `rule_id`;
  - no more than 2 unchanged verifier reruns occur for the same artifact miss.
- No terminal-bench speed proof is run before these fast checks pass.

### Phase 6: Speed Proof Acceptance Gate

Close criteria:

- One same-shape speed proof runs with `transition_contract` defaulted rather
  than explicitly selected.
- Parse errors remain zero or explainably unrelated.
- The loop either completes with reward or blocks earlier with a structured
  repeated-failure reason:
  - completion path: reward is non-zero, verifier count is at most 5, model
    turns are at most 19, and prompt chars are at most 900,000;
  - controlled-block path: the block happens before a 6th same-key verifier
    attempt and before turn 20, includes `repeat_key`, `evidence_refs`, and
    `rule_id`, and prompt chars are at most 900,000.
- Any failure to meet these numbers is treated as another runtime-repair
  design failure, not as normal polish.
- Artifacts include transition trace, repeat counters, prompt byte impact, and
  first-write/verifier metrics sufficient for review.

## Risks And Rollback

Risks:

- Over-normalization could hide a genuinely new runtime failure under an old
  repeat key.
- A too-small repetition budget could block before a valid second repair.
- Prompt slimming could remove detail the model needs unless `inspect` actions
  name exact refs and paths.
- Rule-table bugs could make `required_next` stale even when fresh evidence
  arrives.
- Artifact-specific validation could accidentally encode the latest
  first-frame task instead of the generic missing-runtime-artifact family.

Rollback:

- Keep `current`, `minimal`, and `transcript_first` as explicit valid overrides.
- If the default switch causes unrelated regressions, set
  `DEFAULT_WORKFRAME_VARIANT` back to `current` while keeping
  `transition_contract` selectable.
- If a rule-table phase regresses repair behavior, disable only the new
  runtime-artifact rule path and keep the existing transition contract wrapper.
- Preserve all raw sidecar evidence so replay can compare old and new reducer
  decisions without rerunning terminal-bench.

## Why This Is Scoped Redesign, Not Polish

Polish would tune another prompt sentence or add another local detector around
the latest frame artifact. That would repeat the current failure mode: evidence
is present, but the WorkFrame transition from evidence to action stays
underspecified.

This redesign is scoped because it changes one generic boundary:

```text
runtime failure evidence -> transition_contract rule -> required_next
```

It does not introduce a new variant, a new planning surface, provider-native
tools, or task-specific MIPS/frame-hook behavior. The only intended product
change is that `transition_contract` becomes stricter and more observable when
runtime artifact evidence repeats, especially for silent or missing-artifact
verifier loops.
