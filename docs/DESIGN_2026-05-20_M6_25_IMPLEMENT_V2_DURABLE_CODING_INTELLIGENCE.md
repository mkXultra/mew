# Design 2026-05-20 - M6.25 Implement V2 Durable Coding Intelligence

Status: design only.

Scope: adapt the older durable-coding-intelligence proposal to the current
`implement_v2` native transcript, `codex_hot_path`, tool registry, internal
finish gate, and sidecar-proof architecture. This document does not authorize
source edits by itself.

## Background And Problem Statement

`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` proposed M6.9 as a
large durable-memory milestone: coding-domain memory types, revise/write gates,
symbol indices, hindsight harvesting, reasoning-trace reuse, rehearsal,
curriculum, habit compilation, and preference conditioning. That proposal was
written before the M6.24 hot-path collapse, native transcript rebuild,
`codex_hot_path` tool registry, and internal finish-gate direction had fully
settled.

The current M6.25 goal is narrower and stricter. `ROADMAP.md` now frames M6.25
as Codex-plus resident advantage: keep Codex-level terminal-agent quality while
proving that resident state, reentry, failure memory, and bounded memory
surfaces make repeated work better than cold work. The M6.25 plan stages memory
into `implement_v2` as:

```text
implement_v2_v0: memory-light, lane-local state and reentry hints
implement_v2_v1: bounded read-only memory summary as a prompt section
implement_v2_v2: read-only MemoryExploreProvider, not a second planner
implement_v2_v3: task/gap repair memory after same-shape evidence exists
```

The problem this design solves is alignment between those two worlds. Durable
coding intelligence is still the right product direction, but it must enter
`implement_v2` through a small, testable, bounded surface. It must not re-expand
the live model loop into a planner, a proof-object editor, a thought-log
retriever, or a memory dump.

The invariant is:

```text
model-visible hot path =
  raw task
  + provider-native transcript window
  + compact factual tool result rendering
  + minimal bounded memory projection, only after retrieve -> revise
```

Everything else is sidecar/internal by default: durable memory stores,
reasoning traces, replay bundles, proof records, failure history, reviewer
history, ranking scores, and finish-gate internals.

## Full Old-Review Feature Mapping

Class labels:

1. `M6.25 v0 implementation candidate`
2. `Freeze schema/interface now, defer implementation`
3. `Future feature outside M6.25`
4. `Reject or reshape because it would pollute implement_v2 hot path`

| Old-review feature family | Class | implement_v2-compatible form | Why this class |
| --- | --- | --- | --- |
| Coding memory taxonomy with five types | 2 | Freeze type names and sidecar schema vocabulary for reviewer-steering, failure-shield, file-pair/symbol-edge, task-template, and reasoning-trace, but do not inject all types live. | The taxonomy is useful for future resident advantage, but M6.25 v0 should not implement the full old M6.9 memory stack. |
| Reviewer-steering memory | 1 | Store or project only approved, short rules with `why`, `how_to_apply`, applicability tags, source refs, and expiry/staleness fields. Projection is capped and only after retrieve -> revise. | This is the smallest durable-resident advantage likely to prevent repeated reviewer corrections without widening the tool loop. |
| Failure-shield memory | 1 | Store prior failed approach families as stop-rules: symptom, root cause, forbidden shortcut, safe verification cue, source refs. Projection is capped to relevant failures and never names a next action. | M6.25 specifically wants repeated failures avoided. Failure shields can improve reentry while preserving hot-path cleanliness. |
| File-pair memory | 2 | Freeze schema for structural source/test or source/generated-output pair facts with evidence refs, but use it as sidecar lookup first. Hot-path projection is limited to a bounded path hint only when revise confirms current relevance. | Useful for first-read speed, but a broad pair index can become a hidden navigation planner if rushed. |
| Symbol-edge memory | 2 | Freeze `(module, symbol_kind, symbol_name)` identity and current path resolution contract. Keep the index internal until bounded projection tests exist. | Current M6.24 relies on shell/Codex-like exploration. Symbol edges should accelerate later work without replacing transcript-driven action choice. |
| Task-template memory | 2 | Freeze task-template schema and retrieval metadata. In M6.25 v0, task templates are sidecar-only and never provider-visible, including as workflow reminders. A later design may add a bounded task-template projection kind only with its own limits, metrics, revise rules, and leak gate. | Templates are valuable, but live workflow templates can become a second planner. This removes v0 ambiguity. |
| Reasoning-trace search | 4 | Do not search or inject raw reasoning traces in the main loop. Store only distilled derived facts, decisions, invariants, failure families, and source edges, with raw reasoning unavailable to the model. | Raw reasoning-trace retrieval directly violates the current hot-path and risks thought-log injection. |
| Thought retriever / reasoning-trace harvester | 2 | Freeze a replacement distillation interface: transcript/proof input -> distilled facts/decisions/invariants/failure families/source edges. M6.25 v0 explicitly does not freeze the old `abstraction_level in {shallow, deep}` or `shallow_of` vocabulary as active schema. | The old goal is still useful for abstract tasks, but M6.25 must first define the non-leaking artifact contract and avoid thought-log injection. |
| Write gate matrix | 1 | Add or define a uniform gate contract for durable writes: source refs, verifier/result status, reviewer approval where required, drift/leak checks, and schema validation. | A write gate is required before any resident memory is trustworthy. It is sidecar/internal and does not bloat the live prompt. |
| Revise gate | 1 | Every recalled item must pass `retrieve -> revise -> bounded projection`. Revise adapts paths, checks preconditions, rejects stale facts, and records drop reasons. No raw recalled entry is projected. | This is the central M6.25 safety boundary for memory entering the hot path. |
| Reviewer-diff capture | 2 | Freeze sidecar JSONL for `(ai_draft, reviewer_approved, ai_final)` with refs/hashes. Do not recall diffs directly in M6.25 v0. | Reviewer history is useful raw material, but direct diff injection would be too large and too style-heavy. |
| Reviewer steering from review history | 1 | Only distilled reviewer-approved rules can become hot-path memory candidates. Reviewer comments and diffs stay sidecar. | This keeps reviewer value while avoiding noisy historical context. |
| Reviewer veto | 1 | Provide the contract that any memory entry can be marked stale/deleted with reason and that revised recall must respect the veto. | Essential rollback/safety mechanism for any v0 memory surface. |
| Observability surfaces / external reconstruction | 1 | Required metrics and artifacts: returned ids, rejected ids/reasons, revise result, injected ids, projection bytes/tokens, source refs, and write-gate decisions. | M6.25 must be measurable and reviewable; observability is not optional. |
| CLI memory dump commands | 2 | Freeze command semantics for later: list/show/trace/query as read-only views over durable sidecars. | Useful, but implementation is not necessary before the first bounded projection proof. |
| Mutable graph over append-only store | 2 | Freeze `supersedes`, `refined_by`, and `related` edge vocabulary, with append-only sidecar expectation. Do not implement graph consolidation in v0. | The graph is important for long-lived residence but too broad for the first memory insertion. |
| Link-evolving consolidation | 3 | Future async sidecar job. It may refine entries and graph edges but cannot block ordinary coding turns or inject consolidated dumps. | Valuable after memory volume exists; not needed for first resident advantage evidence. |
| Ranked recall using recency, importance, relevance | 2 | Freeze score component names and trace fields. M6.25 v0 can use deterministic filtering and ordering; full ranker is deferred. | Ranking is needed later, but the first gate is proving projection bounds and rejection behavior. |
| Hindsight harvesting | 2 | Freeze a queue schema for failed/blocked trajectories mapped to existing memory types. Do not auto-promote candidates. | High pollution risk; schema now, implementation later behind reviewer queue. |
| Memory invalidation propagation | 2 | Freeze propagation semantics over `supersedes`/`related` edges. v0 only requires direct veto to suppress recall. | Propagation matters only after graph consolidation exists. |
| Scheduled rehearsal | 3 | Future resident-maintenance lane that records re-anchoring sidecars and never writes prompt content directly. | Rehearsal is outside short coding-task flow and should not block M6.25 v0. |
| Novel-task injection | 3 | Future campaign/selector mechanism. It should measure over-reliance on memory, not alter live coding turns. | Needs task-selection infrastructure and campaign metrics. |
| Confidence decay | 2 | Freeze fields: `confidence`, `last_verified_at`, `decay_reason`, `requires_reverify`. v0 revise may reject manually stale entries; automatic decay is deferred. | The schema should not be painted into a corner, but automatic decay needs more volume and tests. |
| Failure-clustered curriculum / task selection | 3 | Future M6.8.5/M6.25 report feature that influences selector proposals, with reviewer-visible evidence. | Task selection is not part of `codex_hot_path` coding turns and must not steer ordinary actions. |
| Habit compilation | 3 | Future deterministic runner candidate derived from stable task templates, with fallback-on-mismatch. | Powerful but far beyond M6.25 v0 and easy to overfit. |
| Preference store | 3 | Future bounded draft-time preference projection from reviewer-diff triples, max-token capped and provenance logged. | Preference conditioning needs enough reviewed examples and a separate injection budget. |
| Drift canary extension | 2 | Freeze memory-integrity checks and leak checks as close-gate concepts. Implement only the leak/projection metrics needed for v0. | Full drift canary belongs with a broader memory system. |
| Write-path audit | 1 | Every durable memory write records writer, approving actor or policy, source artifact refs, schema version, and gate result. | Required to trust resident memory and to roll it back. |
| Growth budget / eviction | 2 | Freeze per-kind caps and eviction-log semantics. v0 can enforce projection caps even if durable-store caps are deferred. | Store growth is later; projection growth is immediate. |
| Comparative baseline / repeated-task proof | 1 | M6.25 v0 must compare cold vs resident on at least one bounded repeated/reentry task using quality, resident advantage, and cost/latency axes. | This is the resident-advantage proof shape in the current roadmap. |
| Dogfood scenario registration from old M6.9 | 3 | Convert into future campaign fixtures or replay tests as features land; do not register the whole M6.9 scenario suite now. | The old suite assumes the large milestone, not the current v0 scope. |
| B0 baseline capture | 1 | Capture a cold baseline before any resident-memory projection experiment: task id, prompt/instruction hash, model/config, memory-off flag, quality result, first-write latency, first-verifier latency, read/search/tool counts, wall time, and verifier/finish result. | Without a frozen baseline, resident advantage can be claimed post hoc. This is required for Phase 2 evidence. |
| Latency and wall-time regression ceilings | 1 | For v0, require resident runs to stay within a predeclared ceiling against the paired cold baseline: no quality regression and no >10% median wall-time regression unless the primary resident-reuse axis is a predeclared correctness/failure-avoidance win. | The old NFR family remains relevant, but the old M6.9 `B0.iter_wall` ladder is reshaped to paired M6.25 experiments. |
| Memory injection token/item caps | 1 | Enforce projection caps as close-gate requirements: <= 3 projected items and <= 1200 UTF-8 chars. Item count, chars, and hash must be recorded per provider request. | Prompt growth is the most immediate v0 regression risk. This is a live hot-path budget, not merely future schema. |
| Recall/revise/projection latency budgets | 2 | Freeze metric names and require capture now; exact per-call ceilings are deferred to implementation design after current harness timing is known. Projection must fail closed if budget measurement is unavailable in accepted evidence rows. | The old review's 50-200ms numbers may not map cleanly to current native harness surfaces without measurement. |
| Durable storage caps and eviction policy | 2 | Freeze durable-store cap, eviction-log, and per-kind cap vocabulary, but implement only provider-visible projection caps in v0. Durable storage growth controls land with broader memory writes/consolidation. | v0 has little durable volume; the important immediate cap is what reaches the model. |
| NFR breach policy | 1 | A Phase 2 proof row with missing metrics, over-budget projection, forbidden-field leakage, quality regression, or unapproved wall-time regression does not count. Two consecutive breaches on the same axis pause the experiment until rollback, budget revision, or proof-blocker decision is recorded. | The old breach policy is needed to keep memory experiments from normalizing regressions. |
| M6.6 comparator regression tests | 4 | Replace the old M6.6 comparator requirement with current M6.24 baseline protection plus paired M6.25 cold/resident rows. Do not rerun or cite the old M6.6 comparator unless a separate design says it is still the correct baseline. | M6.25 must protect the current `implement_v2` / `codex_hot_path` baseline, not revive an older milestone comparator by default. |

## implement_v2 Architecture

The architecture has four layers:

```text
durable sidecars
  -> retrieval candidates with source refs
  -> revise gate
  -> bounded memory projection
  -> provider-native implement_v2 request
```

### Hot Path

Production `implement_v2` remains Codex-like:

- raw task text and stable coding instructions;
- provider-native transcript window;
- `codex_hot_path` tool surface from the `ToolRegistry`;
- compact factual tool-result rendering;
- optional bounded memory projection, only after retrieve -> revise.

The memory projection is not a planner. It must not include `next_action`,
`required_next`, first-write pressure, full WorkFrame state, proof JSON, finish
gate schema, reviewer diffs, raw memory files, raw transcripts, or raw reasoning
traces.

### Sidecar Surfaces

The resident sidecar owns:

- durable memory candidate files and indices;
- reviewer history and failure history;
- reasoning-trace distillation inputs and outputs;
- write-gate and revise-gate logs;
- memory hit/rejection metrics;
- replay/proof artifacts;
- finish-gate, verifier-planner, and completion sidecars;
- cold/resident campaign ledgers.

Sidecars may compute summaries, rankings, stale decisions, and proof reports.
They do not become provider-visible unless a specific bounded projection schema
allows a distilled item through revise.

### Retrieval Flow

```text
current task + transcript facts + changed paths
  -> retrieve candidate ids from sidecar memory
  -> revise each candidate against current workspace facts
  -> reject stale, irrelevant, vetoed, over-budget, or unsafe entries
  -> project at most the bounded distilled form
  -> record projection hash/size and source refs
```

M6.25 v0 should prefer deterministic filters over model-backed retrieval. Later
rankers may be added only if their score components are logged and they do not
increase projection caps.

## Memory Surface Contract

The only allowed model-visible memory surface in M6.25 v0 is a bounded prompt
section, tentatively:

```text
section_id: implement_v2_durable_memory_projection_v0
visibility: provider_visible
cache_policy: dynamic_uncached
max_items: 3 total
max_chars: 1200 UTF-8 chars after whitespace normalization
allowed_kinds: reviewer_steering, failure_shield, narrow file_pair hint
forbidden_kinds: task_template, raw reasoning_trace, reviewer_diff,
                 raw transcript, proof JSON
```

The v0 `cache_policy` is strictly `dynamic_uncached`. Provider cache transport
and cache-equivalence proof are separate M6.25 work and cannot be used to pass
or explain resident-memory scoring in this design.

Each projected item must have:

- `kind`;
- one-sentence distilled content;
- applicability summary;
- source edge refs or artifact refs;
- revise result id;
- staleness/confidence state;
- no hidden verifier answer, hidden expected output, or future-step answer.

The projection is dropped entirely if:

- revise returns no applicable item;
- the projection exceeds budget;
- any item lacks source refs;
- any item contains forbidden schema keys or raw thought text;
- the current task is a short benchmark-like task where the memory would reveal
  an answer rather than a reusable convention, unless the experiment is
  explicitly a resident-memory campaign row.

For the Harbor resident-memory fixture family, this contract is compatible with
the existing `resident-memory-card-v0` idea: one small workflow/gotcha card,
not prior transcript, not prior source diff, and not the answer.

Task-template memory is explicitly sidecar-only in M6.25 v0. It may be written,
retrieved, revised, counted, or shown in reviewer/debug artifacts, but it must
not be included in `implement_v2_durable_memory_projection_v0`. If a later
phase wants provider-visible task-template projection, it needs a new projection
kind, a separate budget from reviewer-steering/failure-shield/file-pair hints,
forbidden-field tests, and a close gate proving it is not a live planner.

## Reasoning Trace Handling Policy

Reasoning traces never enter the hot path verbatim.

Allowed:

- store sidecar references to trace source artifacts;
- distill traces into facts, decisions, failure families, invariants, source
  edges, or reusable reviewer-approved rules;
- record abstraction level as metadata for future retrieval;
- expose source refs so reviewers can audit distillation.

Forbidden:

- returning chain-of-thought, scratchpads, hidden rationale, or model internal
  reasoning text to the main model;
- injecting raw transcript windows as "memory";
- using thought retrieval to steer the next action;
- asking the main model to continue or imitate a prior reasoning trace.

The compatible substitute for "thought retriever" is a sidecar distiller:

```text
trace/proof/review input
  -> distilled decision/fact/invariant/failure-family/source-edge candidate
  -> write gate and reviewer approval where required
  -> future retrieval candidate
  -> revise
  -> bounded projection, if allowed
```

### Reasoning Trace Schema Vocabulary Decision

The old review reserved `abstraction_level in {shallow, deep}` plus a
`shallow_of` back-edge for reasoning-trace entries. M6.25 v0 does not adopt
that vocabulary as an active schema because it suggests recalling prior
thoughts at different depths. That framing is too close to thought-log
retrieval for the current hot-path contract.

M6.25 v0 replaces it with a distilled-output vocabulary:

```text
distillation_kind: fact | decision | invariant | failure_family | source_edge
source_trace_ref: sidecar artifact ref
specificity: task_local | project_general
related_entry_refs: list[entry_id]
```

`shallow`, `deep`, and `shallow_of` may appear only in legacy review discussion
or migration notes. They must not be implemented as provider-visible fields or
as required durable-memory schema without a later design that proves they do
not reintroduce reasoning-trace retrieval.

## Revise Gate, Write Gate, And Reviewer Steering

### Revise Gate

`revise(candidate, current_context)` is mandatory before projection.

Required outputs:

- `status`: `adapted`, `dropped`, or `needs_reverify`;
- `drop_reason` when dropped;
- rewritten current paths, if any;
- applicability match summary;
- source refs used;
- byte/char contribution if projected.

Required drop reasons include:

- `vetoed`;
- `schema_invalid`;
- `source_ref_missing`;
- `symbol_or_path_not_found`;
- `precondition_miss`;
- `stale_current_workspace_conflict`;
- `hidden_answer_risk`;
- `projection_budget_exceeded`;
- `forbidden_content`.

### Write Gate

Durable memory writes must be sidecar-gated before they can become retrieval
candidates.

Minimum write-gate fields:

- `memory_kind`;
- `entry_id`;
- `schema_version`;
- `source_artifact_refs`;
- `created_from`: reviewer, verifier, trajectory, or explicit resident note;
- `write_gate_result`;
- `approval_ref` when approval is required;
- `hidden_answer_scan`;
- `hot_path_projection_allowed`: boolean;
- `projection_kind`, if allowed.

Reviewer-steering and failure-shield writes require either explicit reviewer
approval or a later policy that is separately reviewed. File-pair/symbol-edge
writes may be structural, but their first hot-path projection still requires
revise success.

### Reviewer Steering

Reviewer steering is not a general "previous reviewer said" text block. A
projected steering rule must be:

- distilled;
- approved or policy-gated;
- scoped to an applicability condition;
- source-referenced;
- small enough to fit the projection budget;
- phrased as an invariant or caution, not an action command.

Reviewer diffs and reviewer-history bodies remain sidecar material for future
preference store work.

## Phase Plan And Close Gates

### Mapping To ROADMAP `implement_v2_v0..v3`

This document's phases are not a one-to-one replacement for the ROADMAP ladder.
They are the design and proof slices that keep that ladder safe:

| Design phase | ROADMAP stage | Relationship |
| --- | --- | --- |
| Phase 0 - Contract Freeze And Leak Gate | `implement_v2_v0` | Defines the memory-light contract and leak gate before any live memory projection. |
| Phase 1 - Sidecar Candidate And Projection Dry Run | `implement_v2_v0` | Exercises lane-local/sidecar memory selection without changing provider input. |
| Phase 2 - Bounded Prompt Projection Experiment | `implement_v2_v1` | First explicit bounded read-only memory prompt section experiment. |
| Phase 3 - Resident Campaign Bridge | `implement_v2_v2` precondition | Produces the campaign metrics and isolation rules needed before a read-only MemoryExploreProvider can be trusted; it does not implement the provider/tool itself. |
| Phase 4 - Deferred Durable Intelligence Expansion | `implement_v2_v2` and `implement_v2_v3` future work | Later designs may add read-only MemoryExploreProvider and task/gap repair memory after bounded projection evidence is green. |

Provider cache transport is outside this phase ladder for scoring purposes. It
remains default-off and cannot be part of v0/v1 resident-memory evidence.

### Phase 0 - Contract Freeze And Leak Gate

Purpose: define the memory surface without changing live behavior.

Deliverables:

- schema/interface notes for candidate kinds, write gate, revise gate, and
  projection section;
- forbidden-content list for memory projection;
- artifact field inventory for memory hit/rejection/projection metrics;
- v0 cold/resident experiment shape selected.

Close gate:

- no implementation/source/test/config files changed by this design step;
- provider-visible allowed/forbidden memory fields are named;
- reviewers can tell which old M6.9 features are v0, deferred, future, or
  rejected/reshaped;
- M6.25 v0 scope excludes graph consolidation, raw reasoning retrieval,
  curriculum, habit compilation, and preference store.

### Phase 1 - Sidecar Candidate And Projection Dry Run

Purpose: prove bounded memory can be selected and rejected without entering the
live provider request.

Deliverables:

- sidecar-only dry-run projection over one saved or synthetic attempt;
- revise results for applicable and rejected entries;
- projection size report;
- leak report proving no raw memory/reasoning/proof enters the rendered card.

Close gate:

- `returned_entry_ids`, `dropped_entry_ids_with_reason`,
  `revise_gate_result`, `candidate_projection_chars`, and
  `projection_allowed=false` are recorded;
- at least one stale/inapplicable candidate is rejected with a concrete reason;
- generated projection would be <= 1200 chars and <= 3 items;
- no live `implement_v2` request behavior changes.

### Phase 2 - Bounded Prompt Projection Experiment

Purpose: allow the v0 projection into one explicitly selected experiment.

Deliverables:

- provider request inventory records section id, hash, chars, and selected refs;
- cold vs resident comparison on a predeclared bounded repeated/reentry task;
- experiment registration before the resident attempt starts, including the
  primary improvement axis, paired cold baseline rows, model/config, prompt or
  instruction hash, verifier command/result expectation, and memory projection
  hash policy;
- memory projection visible only through the named prompt section;
- sidecar replay can reconstruct why each item was included or dropped.

Close gate:

- the primary improvement axis is predeclared as one of:
  repeated-failure avoidance, first-write latency, first-verifier latency,
  read/search count, or turn count;
- at least 3 paired cold/resident attempts run against the same task shape and
  instruction hash before any tuning based on resident results;
- for numeric axes, resident median improves by at least 10% against the paired
  cold median, or by at least 1 whole turn/read/search when the cold median is
  below 10 units;
- for repeated-failure avoidance, the predeclared failure family appears in at
  least 2 of 3 cold attempts and is avoided in at least 2 of 3 resident
  attempts without reviewer rescue;
- task quality does not regress against cold baseline: resident pass rate must
  be >= cold pass rate and every counted resident success must have the same
  verifier/finish standard as cold;
- median resident wall time is not more than 10% slower than cold unless the
  predeclared primary axis is repeated-failure avoidance and the resident path
  wins that axis under the rule above;
- prompt projection remains <= 1200 chars and <= 3 items;
- memory hit/rejection and revise metrics are present;
- no forbidden hot-path fields appear in provider-visible input.

### Phase 3 - Resident Campaign Bridge

Purpose: connect the contract to Harbor resident-memory evidence without
changing ordinary coding tasks.

Deliverables:

- campaign rows record `memory_surface`, memory card hash/chars, memory items
  returned/injected, fresh process/conversation flags, and prior-artifact
  visibility;
- stale-memory rows prove current workspace verification beats blind memory;
- reference conditions separate `mew_resident`, `codex_cold`, and
  `codex_resume`.

Close gate:

- at least three paired cold/resident/stale attempts exist before tuning;
- stale rows use deterministic predicates, not model prose;
- resident advantage and conversation continuation are reported separately;
- no campaign result is claimed if reset manifests or isolation fields are
  missing.

### Phase 4 - Deferred Durable Intelligence Expansion

Purpose: decide whether to implement broader old-review features.

Eligible only after Phase 2 or 3 evidence shows useful bounded memory without
hot-path pollution.

Candidate expansions:

- read-only MemoryExploreProvider;
- ranked recall;
- graph consolidation;
- reasoning-trace distillation;
- preference store;
- habit compilation;
- curriculum/task selection.

Close gate:

- each expansion has its own design and leak gate;
- no expansion increases the default prompt projection budget without a written
  ratchet decision;
- short Terminal-Bench/Harbor coding flows remain runnable with memory off and
  with no semantic prompt change.

## Observability, Metrics, And Artifacts

M6.25 durable memory is accepted only if reviewers can reconstruct its influence
from artifacts.

Required per attempt:

- `cold_baseline_id`;
- `paired_attempt_id`;
- `resident_improvement_primary_axis`;
- `resident_improvement_threshold`;
- `memory_recall_attempt_count`;
- `memory_returned_entry_ids`;
- `memory_dropped_entry_ids_with_reason`;
- `revise_gate_results`;
- `memory_projected_entry_ids`;
- `memory_projection_chars`;
- `memory_projection_hash`;
- `memory_projection_section_id`;
- `memory_write_gate_results`, when writes occur;
- `memory_veto_events`;
- `first_write_latency_ms`;
- `first_verifier_latency_ms`;
- `patch_success`;
- `finish_verifier_result`;
- `done_candidate_status` and internal finish-gate outcome when applicable;
- `provider_visible_memory_forbidden_fields` pass/fail;
- `memory_projection_cache_policy`, always `dynamic_uncached` for v0/v1;
- `resident_advantage_axis`: quality, resident reuse, or cost/latency.

Suggested artifact names, subject to implementation design:

```text
memory_recall_trace.jsonl
memory_revise_results.jsonl
memory_projection.json
memory_projection_leak_scan.json
memory_write_gate_results.jsonl
resident_advantage_metrics.jsonl
```

The proof manifest or equivalent attempt summary should hash these artifacts
when they affect an accepted result.

## Anti-Drift Rules

- Raw memory dumps are forbidden in provider-visible input.
- Memory enters the hot path only through retrieve -> revise -> bounded
  projection.
- Reasoning traces are never returned to the model verbatim.
- The projection cannot contain `next_action`, `required_next`,
  `first_write_due`, `prewrite_probe_plateau`, WorkFrame action fields, finish
  gate schema, proof JSON, or reviewer-diff bodies.
- Memory projection is default-off except in named M6.25 experiments until the
  close gate passes.
- The default non-cache scoring path remains semantically equivalent when memory
  is off.
- The v0 memory projection cache policy is always `dynamic_uncached`; cache
  transport experiments cannot be mixed into resident-memory scoring.
- Task-template memory is sidecar-only in v0 and cannot be projected as a
  workflow reminder, checklist, plan, or hidden action policy.
- Memory must not reveal hidden verifier answers, hidden expected outputs, or
  future-step fixture answers.
- Sidecar observability can grow; provider-visible projection cannot grow
  without an explicit budget ratchet and review.
- A stale or vetoed memory entry must fail closed by being dropped, not by being
  rendered with a warning.
- If memory changes task semantics instead of reducing repeated work, the row
  is invalid as resident-advantage evidence.

## Non-Goals

- No code implementation in this task.
- No broad implementation of the old M6.9 milestone.
- No raw thought retrieval or chain-of-thought memory injection.
- No full durable-memory CLI, graph database, or consolidation worker in v0.
- No provider-visible planner, WorkFrame replacement, next-action card, or
  memory-authored tool instruction.
- No change to `codex_hot_path` tool descriptors for memory.
- No provider cache transport as part of memory scoring.
- No Terminal-Bench proof rerun unless a named M6.25 experiment requires a
  narrow regression check.
- No claim that Codex resume/session continuation is equivalent to mew
  resident memory.

## Risks And Rollback Plan

| Risk | Mitigation | Rollback |
| --- | --- | --- |
| Memory projection bloats the prompt and slows short tasks. | Hard caps, section metrics, memory-off baseline. | Disable the memory projection section; keep sidecars for analysis. |
| Memory steers the model through hidden next actions. | Forbidden-field scan and reviewer focus on wording. | Drop all projection items and keep only sidecar metrics. |
| Stale memory causes wrong edits. | Revise gate, veto, current-workspace conflict checks, stale campaign rows. | Mark entry vetoed/stale and rerun with memory off. |
| Reasoning trace handling leaks hidden rationale. | Store only distilled facts/decisions/invariants/source edges. | Disable reasoning-trace candidate kind until a separate leak audit passes. |
| Reviewer history becomes preference overfitting. | Keep diffs sidecar-only in v0. | Reject preference projection until enough reviewed examples exist. |
| Resident-memory proof is confused with conversation continuation. | Metrics require fresh process/conversation and prior-transcript visibility flags. | Invalidate rows missing isolation evidence. |
| Memory improvements mask regressions in `codex_hot_path`. | Always keep memory-off baseline and provider-native transcript artifacts. | Revert default to memory-off and treat memory as experiment-only. |
| Store growth becomes unreviewable. | Projection caps now; freeze future growth/eviction fields. | Pause durable writes; preserve existing sidecars read-only. |

The primary rollback rule is: if a memory feature contaminates the provider
visible hot path, remove only the provider-visible projection. Do not delete
sidecar artifacts, transcript artifacts, proof artifacts, or reviewer history;
they remain useful for diagnosis and future designs.
