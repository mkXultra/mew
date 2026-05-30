# Design 2026-05-08 - M6.24 Typed Evidence Acceptance / Oracle Bundle V0

Status: design only.

Scope: convert `docs/REVIEW_2026-05-08_ACCEPTANCE_GATE_ARCHITECTURE.md`
into an implementable M6.24 `implement_v2` plan. This document names the
target code surfaces, migration phases, verification gates, and stop criteria.
It does not authorize live benchmark spending by itself.

## Decision

Stop growing `src/mew/acceptance.py` as the semantic judge for
`implement_v2` completion. Keep the current acceptance checks as temporary
safety asserts for known false-completion families, especially the runtime
visual artifact guard, but move the main finish path to typed evidence:

```text
task contract / verifier facts
  -> OracleBundle obligations
  -> tool results and artifact checks
  -> EvidenceEvent index
  -> compact model-visible evidence digest
  -> FinishClaim with cited evidence ids
  -> typed resolver
  -> allow_complete | block_continue
```

This project is not released, so the implementation does not need external
backward compatibility. The migration still needs to be incremental: each
phase must have focused unit coverage and replay/dogfood confidence before
the next phase changes model-visible finish behavior.

## Current Surfaces

The design is intentionally specific to the current `implement_v2` pieces:

- `src/mew/acceptance.py`
  - Current temporary safety gate:
    `acceptance_done_gate_decision()`, `acceptance_finish_blocker()`,
    `_runtime_visual_artifact_quality_blocker()`,
    `_runtime_artifact_final_state_blocker()`,
    `_runtime_artifact_freshness_blocker()`, evidence-ref validation, and
    `finish_continuation_prompt()`.
  - New role: call the typed resolver first when typed session data exists;
    keep legacy string checks only as fallback or explicit safety asserts.
  - Boundary: `acceptance.py` must not import, own, or reimplement
    `OracleBundle` extraction. It consumes typed session data that
    `implement_v2` built from `execution_evidence.build_oracle_bundle(...)`.

- `src/mew/implement_lane/v2_runtime.py`
  - Current finish path:
    `_live_acceptance_done_gate()`, `_finish_acceptance_action()`,
    `_acceptance_session_from_tool_results()`,
    `_structured_finish_acceptance_checks()`, finish-gate history projection,
    and `finish_gate_block_count` metrics.
  - Current observability substrate from
    `docs/DESIGN_2026-05-07_M6_24_INTEGRATION_OBSERVABILITY.md`:
    `ModelTurnInput`, `ModelTurnOutput`, `_call_model_turn()`,
    `_render_prompt_history_json()`, and `integration_observation`.
  - New role: build typed evidence/oracle state from tool results, project a
    compact evidence digest into provider history, and pass typed session data
    into `acceptance_done_gate_decision()`.

- `src/mew/implement_lane/execution_evidence.py`
  - Current structured evidence:
    `ExecutionContract`, `ExpectedArtifact`, `ArtifactEvidence`,
    `VerifierEvidence`, `FailureClassification`, `FinishGateResult`,
    `derive_verifier_evidence()`, `classify_execution_failure()`, and
    `apply_finish_gate()`.
  - New role: define the typed acceptance data model, the
    `build_oracle_bundle(...)` extraction site, and resolver primitives.

- `src/mew/implement_lane/artifact_checks.py`
  - Current deterministic artifact facts:
    existence, non-empty, size, mtime freshness, kind, JSON schema, text, and
    regex checks.
  - New role: add only structured deterministic checks that produce typed
    observations, starting with image dimensions/freshness. Do not add visual
    quality prose parsing here.

- `src/mew/dogfood.py`
  - Current replay/emulator gate:
    `m6_24-terminal-bench-replay` and
    `run_m6_24_runtime_finish_gate_emulator_scenario()`.
  - New role: add a typed-evidence branch to the runtime finish-gate emulator
    while preserving the legacy safety-assert cases.

- Tests:
  - `tests/test_acceptance.py`: typed resolver and safety-assert coverage.
  - `tests/test_implement_lane.py`: event indexing, prompt projection,
    integration observation, and live JSON finish behavior.
  - `tests/test_dogfood.py`: replay/emulator gate assertions.

## Temporary Asserts Versus Typed Path

Temporary safety asserts are the existing deterministic blockers in
`acceptance.py`. Their job is to prevent known unsafe completions while the
typed path is being built. They may inspect current `acceptance_checks` prose
and tool text because they are guarding already-known hazards. They should be
frozen except for critical correctness fixes.

The typed evidence path is the replacement. Its job is to decide normal
`implement_v2` completion from structured facts:

- obligations come from `OracleBundle`, not from a completed finish summary;
- facts come from `EvidenceEvent`, `ArtifactEvidence`, `VerifierEvidence`,
  `ToolRunRecord`, and trusted source-grounding records;
- finish must cite ids;
- deterministic code resolves ids, status, freshness, provenance, and
  obligation coverage.

The migration must not disguise old heuristics as typed evidence. A new
`EvidenceEvent` whose `observed` field is only "the model wrote a convincing
sentence" is not typed evidence.

## Data Model Sketch

Add these shapes in `src/mew/implement_lane/execution_evidence.py`. They may be
dataclasses with `as_dict()` helpers, matching the existing evidence style.

```python
OracleObligationKind = Literal[
    "artifact_exists",
    "artifact_fresh",
    "visual_dimension",
    "visual_similarity",
    "verifier_pass",
    "source_grounding",
]

EvidenceEventKind = Literal[
    "tool_result",
    "artifact_check",
    "oracle_check",
    "verifier_result",
    "source_grounding",
    "failure_classification",
    "cleanup",
]

@dataclass(frozen=True)
class OracleObligation:
    id: str
    kind: OracleObligationKind
    subject: dict[str, Any]
    expected: dict[str, Any]
    source: str  # task_contract | verifier_evidence | repo_test | runtime_inferred
    provenance_refs: tuple[dict[str, Any], ...]
    candidate_derived_allowed: bool = False
    required: bool = True

@dataclass(frozen=True)
class OracleBundle:
    id: str
    source: str
    obligations: tuple[OracleObligation, ...]
    provenance_refs: tuple[dict[str, Any], ...]
    schema_version: int = 1

@dataclass(frozen=True)
class EvidenceEvent:
    id: str
    kind: EvidenceEventKind
    status: Literal["passed", "failed", "partial", "unknown"]
    observed: dict[str, Any]
    refs: tuple[dict[str, Any], ...]
    contract_id: str = ""
    oracle_id: str = ""
    obligation_id: str = ""
    tool_call_id: str = ""
    provider_call_id: str = ""
    command_run_id: str = ""
    tool_run_record_id: str = ""
    freshness: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    supersedes: tuple[str, ...] = ()
    schema_version: int = 1

@dataclass(frozen=True)
class FinishClaim:
    outcome: str
    summary: str
    evidence_refs: tuple[dict[str, Any], ...]
    oracle_refs: tuple[str, ...] = ()
    legacy_acceptance_checks: tuple[dict[str, Any], ...] = ()

@dataclass(frozen=True)
class DoneDecision:
    decision: Literal["allow_complete", "block_continue", "no_typed_decision"]
    gate_source: Literal["typed_evidence", "legacy_string_safety", "none"]
    missing_obligations: tuple[dict[str, Any], ...] = ()
    failed_evidence_refs: tuple[dict[str, Any], ...] = ()
    stale_evidence_refs: tuple[dict[str, Any], ...] = ()
    invalid_evidence_refs: tuple[dict[str, Any], ...] = ()
    blockers: tuple[dict[str, Any], ...] = ()
    continuation_prompt: str = ""
```

`decision="no_typed_decision"` is the explicit neutral typed resolver result.
It means the typed resolver did not have enough typed scope to decide. It does
not grant typed completion credit. The caller must still run legacy safety
asserts and normal legacy evidence-ref validation during migration.

Event ids must be deterministic under saved-artifact replay. The source of
truth is the persisted replay/proof artifact, not a fresh model execution. Use
persisted ids from `tool_run_record`, `command_run`, `artifact_evidence`,
`verifier_evidence`, and `failure_classification` when possible:

- `ev:tool:{command_run_id}:{tool_run_record_id}`
- `ev:artifact:{artifact_evidence.evidence_id}`
- `ev:verifier:{verifier_evidence.verifier_id}`
- `ev:oracle:{oracle_id}:{obligation_id}:{source_event_id}`

`provider_call_id` is a cross-reference only. It may appear in `refs` or
`provenance`, but it must not be the sole determinism key for event identity.
Tool index may be used only as a local disambiguator inside one persisted
artifact when no better persisted id exists.

Do not assert event-id stability across fresh model re-execution unless the
fresh run is normalized through a replay fixture that maps command/tool/artifact
ids to the saved-artifact namespace. Do not include timestamps, random ids,
absolute artifact roots that differ between replay workspaces, provider output
clipping, or prose snippets in event ids. Freshness belongs in the event body,
not the id.

## Typed Resolver Rules

Implement:

```python
resolve_typed_finish(
    finish_claim: FinishClaim,
    oracle_bundle: OracleBundle | None,
    evidence_events: tuple[EvidenceEvent, ...],
) -> DoneDecision
```

Rules:

1. If no `OracleBundle` exists, return
   `DoneDecision(decision="no_typed_decision", gate_source="none")` so legacy
   safety asserts can continue to run during migration. This grants no typed
   completion credit.
2. For completed outcomes, require `finish_claim.evidence_refs`.
3. Every cited id must exist and refer to a terminal/trusted event.
4. An obligation is covered only when a cited passing event maps to that
   obligation and satisfies status, freshness, provenance, and comparator
   rules.
5. `visual_dimension` can satisfy only a dimension obligation. It cannot
   satisfy visual correctness unless the bundle explicitly says dimensions are
   the complete contract.
6. `visual_similarity` requires a task/verifier/repo-grounded reference or
   oracle. Candidate-derived references are rejected unless the obligation
   explicitly sets `candidate_derived_allowed=True`, which should be rare and
   never inferred from model finish prose.
7. Later failed or stale evidence for the same obligation supersedes earlier
   passing evidence.
8. A failed `VerifierEvidence` or failed `oracle_check` blocks completion even
   if an older passing artifact event is cited.

The continuation prompt should name missing typed obligations, not missing
phrases. Example:

```text
Finish was blocked by the typed evidence gate.
- oracle:task:frame_similarity is missing a passed visual_similarity event
  against task-provided reference /tmp/target.png.
Artifact existence already passed as ev:artifact:frame:call-017.
Next action: run one verifier-shaped command that compares the produced frame
with the task reference, then finish with evidence_refs pointing to that event.
```

## Phase Plan

### Phase 0: Freeze Legacy Gate And Repair The Red Pre-Speed State

Target files:

- `src/mew/acceptance.py`
- `tests/test_acceptance.py`
- `tests/test_implement_lane.py`
- `tests/test_dogfood.py`

Rules:

- Do not add more string/regex acceptance families to
  `_runtime_visual_artifact_quality_blocker()` or nearby semantic classifiers.
- Keep the current visual-oracle grounding guard as a safety assert.
- Historical context from the 2026-05-08 decision ledger: the red focused test
  was
  `tests/test_implement_lane.py::test_implement_v2_live_json_finish_gate_can_continue_then_complete`.
  The local supervisor may have repaired this before typed-evidence
  implementation starts. If it is still red on the implementation branch,
  repair that existing behavior first. If it is green, do not churn behavior
  just to match the historical note.
- Separate behavior repair from behavior-preserving metrics. The first typed
  migration commit should add counters/observability without changing
  allow/block semantics unless it is explicitly repairing an already-red
  focused test.
- Add or preserve metrics:
  `finish_gate_block_count`, `legacy_string_gate_block_count`,
  `typed_evidence_gate_block_count`, `missing_typed_evidence_count`,
  `model_claim_without_refs_count`, and `typed_coverage_gap_count`.

Continue when the focused finish-gate tests are green. Stop if the next repair
requires another broad `acceptance.py` regex family; select a typed obligation
or evidence event instead.

### Phase 1: Shadow Evidence Event Index

Target files:

- `src/mew/implement_lane/execution_evidence.py`
- `src/mew/implement_lane/v2_runtime.py`
- `tests/test_implement_lane.py`

Implementation:

1. Add the dataclasses and normalization helpers in `execution_evidence.py`.
2. Add reducer helpers that accept existing payload dictionaries rather than
   importing `ToolResultEnvelope` into `execution_evidence.py`, for example:

   ```python
   evidence_events_from_tool_payload(
       *,
       tool_index: int,
       tool_name: str,
       tool_status: str,
       provider_call_id: str,
       payload: Mapping[str, Any],
   ) -> tuple[EvidenceEvent, ...]
   ```

3. In `v2_runtime.py`, build a shadow event index from each
   `ToolResultEnvelope` after command closeout/projection has stabilized.
4. Include only counts and hashes in normal metrics; write full detail only
   when existing integration-observation detail is explicitly enabled.
5. Do not change allow/block behavior in this phase.
6. Treat current `apply_finish_gate()` / `structured_finish_gate` output as an
   evidence source. The reducer may emit events from
   `structured_finish_gate.blocked`, `structured_finish_gate.reasons`, and
   `structured_finish_gate.evidence_refs`, but this result must not remain a
   separate independent completion gate once the typed resolver owns finish
   decisions.

Events to emit first:

- terminal `tool_result` from `tool_run_record`;
- `artifact_check` from `artifact_evidence`;
- `verifier_result` from `verifier_evidence`;
- `failure_classification`;
- `structured_finish_gate` as a legacy structured source from
  `apply_finish_gate()`;
- `source_grounding` from the existing source sidecar;
- `cleanup` from cleanup tool results or closeout payloads.

Continue when exact replay yields stable event ids and statuses. Stop if the
event layer depends on arbitrary finish prose.

### Phase 2: Oracle Bundle V0

Target files:

- `src/mew/implement_lane/execution_evidence.py`
- `src/mew/implement_lane/artifact_checks.py`
- `src/mew/implement_lane/v2_runtime.py`
- `tests/test_acceptance.py`
- `tests/test_implement_lane.py`

Implementation:

1. Implement the single extraction entry point in
   `execution_evidence.py`:

   ```python
   build_oracle_bundle(
       *,
       task_contract: Mapping[str, Any],
       execution_contracts: Sequence[Mapping[str, Any] | ExecutionContract] = (),
       verifier_evidence: Sequence[Mapping[str, Any] | VerifierEvidence] = (),
       artifact_evidence: Sequence[Mapping[str, Any] | ArtifactEvidence] = (),
       source_grounding_refs: Sequence[Mapping[str, Any]] = (),
   ) -> OracleBundle | None
   ```

   `v2_runtime.py` calls this function and passes the resulting bundle in the
   typed acceptance session. `acceptance.py` must not import or reimplement
   OracleBundle extraction.
2. Build `OracleBundle` for runtime artifact and visual tasks from structured
   sources only. Priority order for reference paths, thresholds, comparators,
   and expected dimensions:
   - explicit structured `task_contract` oracle/expected-artifact fields, if
     present;
   - normalized `ExecutionContract.expected_artifacts[*].checks`,
     `declared_target_refs`, and `source_authority_requirement`;
   - structured `VerifierEvidence.checks[*].expected` /
     `VerifierEvidence.checks[*].observed`;
   - repo/test metadata or saved replay artifacts that already encode
     reference/threshold facts as fields;
   - source-grounding records for provided source/artifact references.
3. Do not move raw prose regex parsing to another file. Raw task
   `title`/`description`/`guidance` may be stored as provenance context, but v0
   must not mine them for visual references or thresholds with a new prose
   parser. If an upstream normalizer later adds structured fields, consume
   those fields here.
4. Keep extraction narrow and provenance-backed:
   expected artifact paths, explicit dimensions/resolution,
   explicit reference/golden/oracle image paths, source paths, verifier pass
   requirements, and structured external verifier failures.
5. If a visual-similarity obligation is required but no trusted structured
   reference/threshold can be extracted, create a blocking missing obligation
   with code `missing_reference`. Do not fall back to candidate-created
   references or model-authored "reference" text.
6. Mark anything proposed only by the model as `model_declared` or leave it out
   of the bundle. Do not let a model-authored reference, generated oracle, or
   self-proxy quality flag become trusted oracle provenance.
7. Extend `artifact_checks.py` only for deterministic structured observations,
   starting with an `image_dimensions` check for supported file headers and
   freshness checks using existing pre/post stat data. Leave SSIM/reference
   similarity to external verifier commands or structured verifier evidence
   until there is a small, deterministic implementation plan.
8. Emit `oracle_check` events when structured evidence satisfies or fails an
   obligation. Example observed payloads:

   ```json
   {
     "kind": "visual_dimension",
     "path": "/tmp/frame.bmp",
     "width": 640,
     "height": 400,
     "expected_width": 640,
     "expected_height": 400
   }
   ```

   ```json
   {
     "kind": "visual_similarity",
     "candidate_path": "/tmp/frame.bmp",
     "reference_path": "/tmp/target.png",
     "metric": "ssim",
     "score": 0.8065,
     "threshold": 0.95,
     "comparator": ">="
   }
   ```

Continue when all current visual-oracle acceptance examples can either be
represented as structured obligations/events or block deterministically as
`missing_reference`. Stop if obligations are being populated from model-authored
quality phrases or raw prose regex parsing.

### Phase 3: Typed Done Resolver Before Legacy String Fallback

Target files:

- `src/mew/acceptance.py`
- `src/mew/implement_lane/execution_evidence.py`
- `src/mew/implement_lane/v2_runtime.py`
- `tests/test_acceptance.py`
- `tests/test_implement_lane.py`

Implementation:

1. Add a typed session shape passed by `v2_runtime.py`:

   ```json
   {
     "typed_acceptance": {
       "oracle_bundle": {"id": "oracle:task:runtime-visual-v0", "...": "..."},
       "evidence_events": [{"id": "ev:artifact:...", "...": "..."}],
       "digest": {"missing_obligations": ["oracle:..."]}
     },
     "tool_calls": ["legacy session projection for temporary asserts"]
   }
   ```

2. In `acceptance_done_gate_decision()`, call the typed resolver first when
   `session["typed_acceptance"]` exists. If that typed session has no
   `oracle_bundle`, the resolver returns `no_typed_decision`.
3. Use this migration routing table:

   | Typed resolver result | Legacy safety result | Routed decision | Metrics |
   |---|---|---|---|
   | `no_typed_decision` | allow | legacy allow/block result only; no typed completion credit | `typed_neutral_count += 1` |
   | `no_typed_decision` | block | block on legacy safety assert | `typed_neutral_count += 1`, `legacy_string_gate_block_count += 1` |
   | `block_continue` | any | block on typed decision; append critical legacy blockers only as supporting context | `typed_evidence_gate_block_count += 1` |
   | `allow_complete` | allow | allow completion for typed-covered family | `typed_evidence_allow_count += 1` |
   | `allow_complete` | block, family not retired | block; this is a typed coverage gap | `typed_coverage_gap_count += 1`, `legacy_string_gate_block_count += 1` |
   | `allow_complete` | block, family retired | allow only after replay/dogfood proof retired that family; record legacy warning | `legacy_string_gate_warning_count += 1` |

   Retirement is per false-finish family, not global. A family can move from
   "legacy blocks" to "legacy warns" only after replay and dogfood prove typed
   obligations/events cover the same historical false completes.
4. Normalize current finish JSON into `FinishClaim`. Prefer
   `finish.evidence_refs`; read `acceptance_checks` only as transitional
   scaffolding for old in-repo tests and current model outputs.
   `acceptance_checks -> FinishClaim` normalization should be deleted or made
   irrelevant once Phase 4 native `finish.evidence_refs` is established.

Continue when finish blocks are about missing typed obligations or invalid ids,
not missing acceptance phrases. Stop if typed allow disagrees with a known
correct legacy safety block; add the missing obligation/event coverage.

### Phase 4: Cited Finish And Compact Evidence Digest

Target files:

- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/implement_lane/execution_evidence.py`
- `tests/test_implement_lane.py`

Implementation:

1. Update `_live_json_prompt()` response contract to prefer:

   ```json
   {
     "finish": {
       "outcome": "completed | blocked | failed | continue",
       "summary": "short stop reason",
       "evidence_refs": [
         {"kind": "evidence_event", "id": "ev:artifact:frame:call-017"},
         {"kind": "evidence_event", "id": "ev:oracle:frame_similarity:call-019"}
       ],
       "oracle_refs": ["oracle:task:frame_similarity"]
     }
   }
   ```

2. Make native `finish.evidence_refs` the normal finish contract. Keep
   `acceptance_checks` and `acceptance_evidence` only as transitional input
   fields until focused tests and fake-provider fixtures have moved to native
   refs. Do not require external backward compatibility.
3. Add a compact typed digest to provider-visible history through the existing
   `_provider_visible_tool_result_for_history()` /
   `_structured_execution_summary_for_provider_history()` path:

   ```json
   {
     "typed_evidence": [
       {
         "id": "ev:artifact:frame:call-017",
         "kind": "artifact_check",
         "status": "passed",
         "observed": {"path": "/tmp/frame.bmp", "exists": true}
       },
       {
         "id": "ev:oracle:frame_similarity:call-019",
         "kind": "oracle_check",
         "status": "failed",
         "observed": {"score": 0.8065, "threshold": 0.95}
       }
     ],
     "typed_next_blocker": "visual_similarity_below_threshold"
   }
   ```

4. Use the 2026-05-07 integration-observation boundary to measure prompt
   impact. Add counts/hashes such as `typed_evidence_event_count`,
   `oracle_obligation_count`, `typed_digest_chars`, and
   `typed_gate_decision` to the observation summary or sidecar. Do not put raw
   prompts, raw stdout/stderr, secrets, or full evidence bodies in normal lane
   state.
5. Keep `ModelTurnInput`, `_call_model_turn()`, and
   `integration_observation` as instrumentation boundaries. Typed evidence
   changes model-visible projection, but it should not change provider-call
   mechanics.
6. Migrate `_structured_finish_acceptance_checks()` and
   `structured_finish_gate` users toward typed evidence production. After the
   typed resolver lands, `structured_finish_gate` should explain what evidence
   was produced or missing; it should not independently allow a completion
   after `resolve_typed_finish()` has decided the finish.

Continue when the model cites valid ids in focused fake-provider tests. Stop
and repair the digest if the model repeatedly cites nonexistent ids.

### Phase 5: Replay, Dogfood, Emulator Gate

Target files:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`
- `tests/test_acceptance.py`
- `tests/test_implement_lane.py`

Gate order before any live 10 minute diagnostic, `speed_1`, `proof_5`, or
broad measurement:

1. Focused unit tests for the changed surface must be green. The current
   pre-speed rule is strict: do not run live 10 minute diagnostics, `speed_1`,
   `proof_5`, or broad measurement while focused UT is red.
2. Exact replay of the latest relevant saved Harbor artifact.
3. `mew dogfood --scenario m6_24-terminal-bench-replay` with the same job dir
   and explicit terminal-bench assertions when validating a Harbor artifact.
4. `mew dogfood --scenario m6_24-runtime-finish-gate-emulator`.
5. The selected gap emulator. For the current runtime visual finish shape,
   that is the runtime finish-gate emulator unless a narrower typed-evidence
   emulator is added.
6. Only after steps 1-5 pass, run one selected same-shape 10 minute
   step-shape diagnostic. Classify it before any `speed_1`, `proof_5`, or
   broad measurement.

Dogfood changes:

- Extend `run_m6_24_runtime_finish_gate_emulator_scenario()` with typed
  acceptance artifacts:
  format-only visual evidence blocks on missing `visual_similarity` or
  explicit `visual_dimension` obligation;
  task/reference-grounded visual similarity passes;
  self-proxy quality evidence remains blocked because provenance is
  candidate-derived.
- Preserve the existing legacy emulator checks until typed gates have covered
  the same false-finish classes in replay.

### Phase 6: Retire Regex Families By Coverage

Target files:

- `src/mew/acceptance.py`
- `tests/test_acceptance.py`
- `tests/test_implement_lane.py`
- `tests/test_dogfood.py`

Retire only after typed replay/dogfood covers the same family:

1. Convert the legacy block into a warning/report artifact.
2. Keep hard safety asserts for invalid evidence refs, failed verifier
   verdicts, stale artifacts, candidate-derived oracles, and impossible
   provenance.
3. Remove the legacy allow/block dependency only when typed evidence blocks all
   historical false completes for that family.

Do not delete tests blindly. Rewrite legacy tests into typed tests first, then
leave a smaller safety-assert test for the frozen guard.

## Migration Strategy

The project does not need compatibility with old clients. Still, implement in
thin vertical slices:

1. Shadow event index with no behavior change.
2. `execution_evidence.build_oracle_bundle(...)` for runtime visual/artifact
   tasks only, using structured-source-only extraction.
3. Typed resolver behind current `acceptance_done_gate_decision()` with the
   explicit migration routing table.
4. Cited finish prompt and compact digest.
5. Dogfood/replay/emulator validation.
6. Retirement of covered legacy regex blockers.

Fields such as `acceptance_checks` may stay during staging so current tests can
be migrated safely. They are transitional scaffolding for `FinishClaim`
normalization and should be replaced by native `finish.evidence_refs` in
Phase 4. They should not be treated as a public compatibility contract.

## Test Plan

`tests/test_acceptance.py`:

- `resolve_typed_finish()` returns `no_typed_decision` when no typed bundle is
  available, and that result grants no typed completion credit.
- `resolve_typed_finish()` allows a completed finish only when every required
  obligation is covered by cited passing events.
- Completed finish with no refs blocks with `missing_typed_evidence`.
- Nonexistent, nonterminal, failed, stale, or superseded refs block.
- Artifact existence and freshness obligations pass/fail from structured
  `ArtifactEvidence`.
- Visual dimension pass cannot satisfy visual similarity.
- Visual similarity pass requires score/threshold comparator and trusted
  task/verifier/repo reference provenance.
- Visual similarity with no structured trusted reference/threshold blocks with
  `missing_reference`.
- Candidate-derived references and model-authored quality flags block.
- Typed allow plus non-retired legacy block still blocks and records
  `typed_coverage_gap_count`.
- Existing temporary visual safety tests remain until typed coverage replaces
  them.

`tests/test_implement_lane.py`:

- Tool-result payloads reduce to stable `EvidenceEvent` ids under saved-artifact
  replay using persisted `command_run`, `tool_run_record`, and
  `artifact_evidence` ids. `provider_call_id` is asserted only as a
  cross-reference.
- Provider-visible history includes compact typed digest ids and omits raw
  large outputs/secrets.
- `build_oracle_bundle(...)` is called from `v2_runtime.py`; `acceptance.py`
  receives the result through typed session data and does not own extraction.
- `_live_acceptance_done_gate()` passes typed session data into acceptance.
- Finish with typed `evidence_refs` can complete when obligations are covered.
- Finish without refs blocks for typed runtime visual/artifact tasks.
- `structured_finish_gate` / `apply_finish_gate()` output is converted into
  evidence events or structured source facts, not used as a parallel final
  completion gate.
- `finish_gate_block_count`, `typed_evidence_gate_block_count`,
  `missing_typed_evidence_count`, `typed_coverage_gap_count`, and
  integration-observation metrics are updated.
- Current integration-observation tests still prove state safety by default.

`tests/test_dogfood.py`:

- Runtime finish-gate emulator covers both legacy safety asserts and typed
  acceptance artifacts.
- Terminal-bench replay dogfood preserves typed gate decisions and blocker
  classes when replaying saved artifacts.

Cheap checks after implementation phases:

```bash
python -m pytest tests/test_acceptance.py -k 'typed or runtime_visual or evidence_ref'
python -m pytest tests/test_implement_lane.py -k 'typed or finish_gate or integration_observation or artifact_evidence'
python -m pytest tests/test_dogfood.py -k 'runtime_finish_gate_emulator or terminal_bench_replay'
python -m ruff check src/mew/acceptance.py src/mew/implement_lane/execution_evidence.py src/mew/implement_lane/artifact_checks.py src/mew/implement_lane/v2_runtime.py src/mew/dogfood.py tests/test_acceptance.py tests/test_implement_lane.py tests/test_dogfood.py
git diff --check
```

Do not run long benchmark tasks as part of these phases.

## Integration With M6.24 Observability

`docs/DESIGN_2026-05-07_M6_24_INTEGRATION_OBSERVABILITY.md` remains the
instrumentation foundation. Typed evidence should use that work as follows:

- Keep the `ModelTurnInput -> _call_model_turn() -> ModelTurnOutput` boundary
  intact.
- Treat typed evidence digest generation as model-visible projection work
  outside the provider-call mechanics.
- Record digest size, event counts, obligation counts, finish-ref counts, and
  typed gate outcomes, including `typed_coverage_gap_count`, in
  `integration_observation` summary/detail without serializing raw prompts or
  raw tool output into normal lane state.
- Use projection metrics to catch hot-path regressions. If typed evidence
  makes prompt weight climb materially, stop and compact the digest before more
  acceptance semantics are added.

## Integration With The Decision Ledger

`docs/M6_24_DECISION_LEDGER.md` is the control source for when measurement may
resume. The 2026-05-08 row records a red current-head pre-speed state and
typed-evidence migration pending. A local supervisor may repair that focused
test before implementation begins, but this design preserves the control rule:

- no live 10 minute diagnostics, `speed_1`, `proof_5`, or broad measurement
  while focused UT is red;
- after a typed-evidence implementation phase, run focused UT, exact replay,
  terminal-bench replay dogfood, and the runtime finish-gate emulator before
  any live diagnostic;
- classify the next 10 minute step-shape diagnostic before speed/proof or
  broader measurement;
- update the decision ledger only after implementation evidence exists.

## Stop Criteria

Stop the typed evidence migration and revise the design if any of these occur:

- evidence events are just regex/string acceptance results in a new wrapper;
- oracle bundles are filled from model-authored finish claims;
- reference paths, thresholds, or comparators are extracted from raw prose by
  new regexes instead of structured sources;
- completed finish still depends on prose phrases rather than cited ids;
- the model-visible digest is too large and worsens the hot path;
- replay does not produce stable event ids and decisions;
- typed allow lets through a finish that current safety asserts correctly
  block;
- the same runtime visual family requires another broad `acceptance.py` regex
  patch;
- focused UT is red when someone wants to run live 10 minute, speed, proof, or
  broad measurement.

## What Not To Do

- Do not add another visual/model/numeric heuristic family to
  `src/mew/acceptance.py` as the normal repair.
- Do not move arbitrary prose regexes from `acceptance.py` into
  `execution_evidence.py` and call them typed evidence.
- Do not mine raw task prose for visual references, thresholds, or comparators
  in `build_oracle_bundle(...)`; consume structured task/verifier/repo fields
  or block with `missing_reference`.
- Do not let model-authored references, generated oracle sources, copied
  candidate outputs, or self-proxy quality markers satisfy oracle provenance.
- Do not use `integration_observation` as proof; it is observability.
- Do not dump full proof objects, full history, or full stdout/stderr into the
  prompt to make ids available.
- Do not require old finish schemas for compatibility. Keep legacy fields only
  while they help incremental verification.
- Do not make a monitor model the final authority. Advisory model output must
  become typed findings and still pass the deterministic resolver.
- Do not run live benchmark diagnostics or speed/proof/broad measurement from
  a red focused-test state.
