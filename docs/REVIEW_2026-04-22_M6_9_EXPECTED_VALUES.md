# M6.9 Expected Values — Scientific Reference

Date: 2026-04-22.
Status: **reference document** (not a formal gate, not a proposal).
Paired with: `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`.

## 1. Purpose

M6.9 is the most research-heavy milestone in mew's ROADMAP. Each
deliverable rests on a specific published finding about memory-augmented
LLM agents. This document records the **quantitative expectation** each
deliverable inherits from the literature, the **adaptation rule** used
to translate that finding into a mew telemetry field, the **expected
value** after adaptation, and the **tolerance** acceptable before the
hypothesis is considered falsified for mew's coding workflow.

This is not a close gate. It is a scientific record. Its job is:
- ground engineering decisions in published evidence,
- give implementers a target number during polish,
- give close artifacts (`docs/M6_9_CLOSE_GATE_*.md`) a concrete
  "observed vs expected" table to populate,
- document adaptation uncertainty honestly, so "observed ≠ expected"
  becomes a data point about the literature's transferability to
  coding workflows, not a governance crisis.

M6.11 uses a formal close-gate strengthening proposal
(`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md`) because its
failure mode (drafting stall) is reactive and operational. M6.9 uses
this scientific reference instead because its failure mode is
literature-adaptation uncertainty, which is predictive and research-
shaped. Both patterns coexist deliberately.

## 2. Scope

### In scope
- Per-deliverable expected values derived from cited papers
- Adaptation rules from paper metrics to mew telemetry fields
- Tolerance justified by adaptation distance
- Falsification criteria (what "the hypothesis does not apply to mew"
  would look like in the data)
- Observation log template for Phase 2-4 implementations to populate
- Amendment policy (dated updates, no formal approval cycle)

### Out of scope
- Close gate enforcement (M6.9 close gate stays as defined in
  `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` §2)
- M6.11, M6.7, M6.8, M6.10 expectations (those milestones have their
  own shape)
- Rewriting the M6.9 design spec (§2 of the design doc is authoritative;
  this document supplements, it does not replace)

### Relationship to existing docs
- **Design spec**: `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`
  defines the 4 Phases, 18 deliverables, and 7 success criteria.
  Expected values below are bound to specific deliverables in that doc.
- **Research grounding**: design spec §5 cites the papers this
  doc quantifies. Citations here match §5 for all primary sources,
  with two exceptions explicitly flagged at their use sites
  (Phase 1 D5 and Phase 4 D2/D3): the historical-edits-alignment
  literature is treated as conceptual background only, and the
  "habit compilation" concept is treated as background without a
  canonical §5 citation. Neither is used as a binding hypothesis.
- **Close artifact**: future `docs/M6_9_CLOSE_GATE_*.md` must include
  an "Observed vs Expected" section populated from §5 of this doc.
- **ROADMAP_STATUS**: M6.9 entry may cite this doc as the
  expectations reference; no edit required now.

## 3. Adaptation philosophy

Published findings measure performance on benchmark datasets (Gaia2,
HumanEval, Minecraft, ALFWorld). mew's workload is bounded roadmap
iterations on its own codebase. The adaptation is non-trivial.

Three adaptation classes are used in §5 below:

1. **Direct class**: paper metric maps to a near-identical mew field
   (e.g. recall precision → ranked recall top-N precision). Tolerance
   ±30%. Classify as Direct when both surface (what is measured) and
   domain (what is being measured on) match the paper closely.
2. **Translated class**: paper metric needs re-scaling (e.g. "items
   per hour" → "bounded iterations per supervised hour"). Tolerance
   ±50%. Classify as Translated when surface matches but domain
   differs (benchmark vs coding), or surface is re-shaped but
   conceptually isomorphic.
3. **Directional class**: the paper establishes a direction but
   specific magnitudes are domain-specific. The primary claim is
   direction, not magnitude. Tolerance is specified as a bounded
   window for the mew-specific field; the window's purpose is to
   detect drift or degradation, not to match paper magnitude.

### Decision rubric

Use the following rubric to classify a new deliverable:

- Paper reports a headline number in a coding / software-engineering
  domain → **Direct**, tolerance ±30%.
- Paper reports a headline number in a non-coding domain (Gaia2,
  Minecraft, ALFWorld, web agents) → **Translated**, tolerance ±50%.
- Paper reports a qualitative improvement or the reported metric
  does not have a clean mew equivalent → **Directional**, bounded
  window chosen to detect drift (not paper match).

### Directional rows with numeric windows (not a contradiction)

Directional classification does **not** mean "no numeric target."
It means the numeric target is chosen to detect degenerate behavior
in the mew-specific field, not to mirror a paper's reported
magnitude. For example, a Directional row may specify
`write_gate_rejection_rate in [0.10, 0.40]` as a drift-detection
window, while still classified Directional because no paper
reports the expected rejection-rate magnitude.

When a Directional row has a numeric window, the window must state
the drift-detection meaning explicitly (what the lower and upper
bounds signal), not a paper-derived expectation.

When in doubt, widen the adaptation class (Directional over
Translated, Translated over Direct). Under-committing is preferred
over over-committing.

## 4. Measurement mapping

Observation surfaces fall into three categories:
- **Telemetry**: raw fields from design spec §12.3 session-trace
  contract. These must exist in `session_trace` output before the
  deliverable's observation can be recorded.
- **Durable-file derived**: values computed from
  `.mew/durable/*.jsonl` or `.mew/replays/work-loop/`. These do not
  appear in session traces but are reconstructible offline per P8
  observability.
- **Reviewer-annotated**: values that require reviewer judgment
  during or after an iteration (e.g. "was this recall useful?").
  These are not telemetry; they are structured review outcomes.

| Surface | Category | Source | Landed? |
| --- | --- | --- | --- |
| Iteration wall time | Telemetry | `wall_time_ms` (§12.3) | ✅ |
| First-read index hit rate | Telemetry | `index_hit_count` / total first-reads (§12.3) | ✅ |
| Memory recall injection | Telemetry | `returned_entry_ids`, `injected_entry_ids` (§12.3) | ✅ |
| Revise drop rate | Telemetry | `dropped_entry_ids_with_reason` count / recall total (§12.3) | ✅ |
| Write gate events | Telemetry | `write_events` (includes `write_gate_result` per event, §12.3) | ✅ |
| Reviewer veto events | Telemetry | `veto_events` (§12.3) | ✅ |
| Reviewer steering reuse | Derived | per-entry `fire_count` from `reviewer_steering.jsonl` durable file, aggregated across session | ✅ (Phase 1 D1+D7) |
| Failure-shield reuse | Derived | per-entry `fire_count` from `failure_shield.jsonl`, aggregated | ✅ (Phase 1 D1+D7) |
| Honest-close rate | Derived | ratio of iterations finishing with reviewer-approved apply ∧ verify green, computed from `docs/M6_9_*_ITERATION_*.md` | ✅ (from existing iteration proof shape) |
| Ranked recall precision | Reviewer-annotated | per-recall `useful=true` flag added by reviewer during or after turn; aggregated over 20+ recalls | (Phase 2 new — needs §12.3 addition of `reviewer_recall_useful` field) |
| Hindsight acceptance rate | Derived | ratio of hindsight_queue items that land in durable memory via `hindsight_queue.jsonl` (Phase 2 spec) | (Phase 2 new) |
| Reasoning-trace recall fires | Derived | per-entry `fire_count` on `reasoning_trace.jsonl` entries, split by `abstraction_level=shallow/deep` | (Phase 2 new) |
| First-try success (abstract tasks) | Derived | ratio of iterations with `task_shape=abstract` that complete without reviewer rework, from iteration docs | (Phase 2 new — needs task-shape tag in iteration docs) |
| Rehearsal recovery rate | Telemetry | `rehearsal_outcome=reacked` / total rehearsal passes (§12.3 Phase 3+) | (Phase 3 new) |
| Novel-task shortcut rate | Telemetry | `memory_shortcut_attempted ∧ shortcut_succeeded` / novel-task injections (§12.3 Phase 3+) | (Phase 3 new) |
| Decay ordering effect | Derived | comparison of recall ranking output before/after decay factor applied, computed from session trace snapshots | (Phase 3 new) |
| Invalidation propagation | Derived | per-veto event, count of entries reached via `supersedes`/`refined_by`/`related` edges that were invalidated in same cycle, from `veto_log.jsonl` + durable graph | (Phase 2 new) |
| Curriculum completion | Derived | bounded tasks completed per chained session, compared against M6.8 non-curriculum baseline sessions | (Phase 4 new — depends on M6.8) |
| Compiled-path speed | Telemetry | `compiled_path_hits` wall_time_ms vs pre-compilation `wall_time_ms` on same task shape (§12.3 Phase 4+) | (Phase 4 new) |
| Reviewer edit-rate reduction | Derived | reviewer patch-edit events per approved iteration, pre vs post preference-store activation | (Phase 4 new) |

### Telemetry gaps to schedule before Phase 2 starts

The following Phase-2+ observation surfaces require telemetry fields
that are **not yet in design spec §12.3** and must be added before
the relevant deliverable can be measured:

- `reviewer_recall_useful` — per-recall reviewer annotation flag
  (prerequisite for ranked recall precision)
- `task_shape` tag on iteration docs — distinguishes abstract vs
  mechanical tasks (prerequisite for first-try success on abstract
  tasks)

These gaps should be closed as part of the Phase 2 Strengthen
iteration plan (see design spec §10 handoff notes; adding a
telemetry delta doc addendum is the lightest route).

Phase 2-4 deliverables that depend on these surfaces cannot be
scored until the surfaces exist. The observation log (§6) for those
rows stays "not measured" until the telemetry addition lands.

## 5. Per-deliverable expected values

Organized by Phase. Each row includes citation (with arXiv ID for
verification), reported metric, adaptation class, expected value,
tolerance, and falsification criterion.

### 5.1 Phase 1 — Baseline substrate (landed 2026-04-22)

Phase 1 deliverables are primarily framework adoption with fewer
quantitative targets. D4 symbol index and D5 reviewer-diff have
direct quantitative paper grounding; the rest are directional.

#### D1 — Typed memory taxonomy
- Source: CoALA (Sumers et al., arXiv:2309.02427)
- Reported: CoALA is a design taxonomy paper, no quantitative gain
  reported for a "typed vs untyped" comparison.
- Adaptation: **Directional only**. Hypothesis: typed memory
  retrieval produces fewer irrelevant recalls than a single-bag
  untyped store.
- Expected: ≥ 15% reduction in irrelevant-recall rate over a naive
  untyped baseline (if one were measured). Not a required
  measurement.
- Tolerance: N/A — directional hypothesis, direction matters.
- Falsification: if Phase 2 ranked recall on typed memory performs
  worse than naive cosine over untyped pool in a controlled
  comparison, the taxonomy is adding overhead without value.

#### D2 — Write-gate matrix
- Source: Voyager (Wang et al., arXiv:2305.16291) self-verification
  gate + CBR Retain step (Aamodt & Plaza 1994).
- Reported: Voyager rejects unverified skills from the library; CBR
  retains only successfully-validated cases.
- Adaptation: **Directional**. Hypothesis: outcome-gated writes keep
  the memory signal-to-noise ratio higher than permissive writes.
- Expected: `write_gate_rejection_rate` in `[0.10, 0.40]`. Below 10%
  means gates are too permissive; above 40% means gates reject
  legitimate candidates or the writer is producing noise.
- Tolerance: the window itself is the tolerance.
- Falsification: reviewer-veto rate on durable entries exceeding
  15% would imply gates passed entries the reviewer had to remove,
  signalling permissive gates.

#### D3 — `revise()` reuse gate
- Source: CBR (Aamodt & Plaza 1994; Wiratunga et al. arXiv:2504.06943)
  Revise step.
- Reported: CBR Revise is a qualitative step; no magnitude given.
- Adaptation: **Directional**. Hypothesis: without Revise, stale-
  entry reuse causes incorrect actions.
- Expected: `revise_drop_rate` in `[0.10, 0.35]`. Lower means Revise
  is over-cautious and dropping useful adapted entries; higher means
  memory staleness is higher than expected and write gates need
  tightening.
- Tolerance: window-based.
- Falsification: if `revise_drop_rate > 0.50` sustained across 5
  iterations, either write gates are failing or the store is
  polluted faster than adaptation can fix.

#### D4 — Minimum symbol/pair index
- Source: CodeRAG (Zhang et al., arXiv:2509.16112), AutoCodeRover
  (Zhang et al., arXiv:2404.05427).
- Reported: CodeRAG shows **>10% gain** over single-shot RAG on
  repository-level completion when retrieval is structure-aware.
- Adaptation: **Direct class**. mew first-read-via-index rate maps
  to "retrieved correct file on first attempt" in CodeRAG terms.
- Expected: `index_hit_rate` ≥ 0.80 on post-Phase-1 iterations
  (matches M6.9 §2 success criterion #4).
- Tolerance: ±10% (0.72 – 0.88), tight because this is the most
  directly mapped expectation.
- Falsification: if `index_hit_rate < 0.60` after 3 consecutive
  post-Phase-1 iterations with a warm index, structural retrieval
  is not delivering the CodeRAG-class benefit for mew's repo shape.

#### D5 — Reviewer-diff triples
- Source: RLTHF (2024; cited in design spec §5.9).
  (Historical-edits-alignment literature is conceptual background
  for Phase 4 preference-store use; not cited as primary source
  here because it is not in design spec §5.9.)
- Reported: RLTHF shows targeted human feedback reduces annotation
  cost by "targeting only uncertain cases" (fraction-gated).
- Adaptation: **Directional only for Phase 1** — reviewer-diff
  triples are raw material for Phase 4 preference store, not a
  direct live metric.
- Expected: triple completion rate (iterations where reviewer
  approved ∧ `ai_final` landed) ≥ 0.95. Remaining 5% are approve-
  then-revert cases which are expected and intentional.
- Tolerance: ±5% (0.90 – 1.00).
- Falsification: if completion rate < 0.80 sustained, either the
  landing path has a bug or the approval surface is emitting
  approvals that do not reach `ai_final`.

#### D6 — Reviewer veto stub
- Source: No direct paper; extension of CBR Retain/Revise.
- Reported: N/A.
- Adaptation: **Directional**. Hypothesis: reviewer veto, even as
  a stub, prevents bad-write accumulation.
- Expected: veto events during Phase 1 operation ≥ 1 per 100
  durable writes (non-zero usage implies the surface is discoverable;
  zero usage implies vetos cannot be issued in practice).
- Tolerance: directional — any non-zero usage satisfies.
- Falsification: if the first reviewer-detected bad entry cannot
  be vetoed due to surface bugs, the stub has failed its minimum.

#### D7 — Observability surfaces
- Source: No direct paper; P8 design principle, grounded in M9
  Legibility forward-looking work.
- Reported: N/A.
- Adaptation: **Directional**. Hypothesis: external inspectability
  without source-reading enables reviewer diagnosis.
- Expected: `m6_9-observability-rebuild` dogfood scenario
  reconstructs recall decisions from `.mew/durable/` + session
  trace alone, matching internal recall state exactly.
- Tolerance: exact reconstruction expected (no tolerance; any
  mismatch is a bug).
- Falsification: any recall decision that requires reading `src/mew`
  to reconstruct signals the observability contract is broken.

### 5.2 Phase 2 — Graph rewrite and hindsight (pending)

Phase 2 deliverables have the strongest paper grounding.

#### D1 — Link-evolving consolidation
- Source: A-MEM (Xu et al., arXiv:2502.12110).
- Reported: A-MEM shows Gaia2 benchmark improvement via link-
  evolving memory updates; paper reports **~8% Gaia2 gain** vs
  non-evolving baseline in the reported configuration.
- Adaptation: **Translated class**. Gaia2 maps weakly to coding
  iteration. Adaptation: "agent task completion rate" → "iteration
  honest-close rate".
- Expected: ≥ 5% improvement in honest-close rate over Phase 1
  baseline, measured over 20+ iterations.
- Tolerance: ±50% (i.e. observed improvement ≥ 2.5% is directionally
  consistent).
- Falsification: if honest-close rate declines or stays flat after
  consolidation lands across 20+ iterations, A-MEM's link evolution
  is not transferring to coding workflows.
- Observation ready when: ≥ 20 post-consolidation iterations
  recorded. Baseline = honest-close rate over the 20 iterations
  immediately preceding Phase 2 D1 landing, computed from the same
  iteration-doc shape. Denominator = iterations reaching
  reviewer-approval attempt (not all started iterations).

#### D2 — Ranked recall
- Source: Generative Agents (Park et al., arXiv:2304.03442) +
  CodeRAG reranking (arXiv:2509.16112).
- Reported: Generative Agents' three-factor scoring (recency ×
  importance × relevance) + CodeRAG shows >10% retrieval quality
  improvement over cosine-only.
- Adaptation: **Direct class**. mew's top-1 recall precision (as
  judged by reviewer annotation) maps directly to retrieval
  quality in paper terms.
- Expected: ranked recall `top-1 precision` ≥ 0.70 (reviewer-
  annotated "this recall was useful"), vs Phase-1 keyword-filter
  baseline expected at ~0.55.
- Tolerance: ±10% (i.e. 0.63 – 0.77 acceptable).
- Falsification: if top-1 precision ≤ 0.55 (matching or below
  naive baseline), the scorer is adding overhead without signal.
- Observation ready when: ≥ 20 ranked-recall events have a
  `reviewer_recall_useful` annotation (requires telemetry-gap
  closure listed in §4). Baseline = same annotation fraction on
  Phase 1 keyword-filter recalls over the same 20-event window
  immediately prior to ranked-recall activation.

#### D3 — Hindsight harvester
- Source: AgentHER (Ding, arXiv:2603.21357).
- Reported: AgentHER shows **+7.1 to +11.7 pp** improvement across
  1.5B–72B model sizes on trajectory relabeling tasks.
- Adaptation: **Translated class**. "Relabeled trajectory success"
  → "reviewer-accepted hindsight case converted to durable memory".
- Expected: `hindsight_queue_acceptance_rate` ≥ 0.50 (of proposed
  relabeled cases, at least half become durable memory on reviewer
  review). Paper midpoint gain +9pp → relative acceptance ~0.50.
- Tolerance: ±30% (0.35 – 0.65).
- Falsification: if acceptance rate < 0.35 sustained, the harvester
  is producing cases that reviewers systematically reject, meaning
  the relabeling heuristic does not translate.
- Observation ready when: ≥ 10 hindsight candidates have passed
  through the reviewer queue (accepted or rejected). Smaller
  sample sizes are too noisy for an acceptance-rate judgment.

#### D4 — Reasoning-trace harvester
- Source: Thought-Retriever (Feng et al., arXiv:2604.12231).
- Reported: **+7.6% F1, +16% win rate** on Gaia2 with retrieved-
  thoughts over retrieved-raw-data.
- Adaptation: **Translated class**. F1 → first-try success rate on
  abstract tasks (refactor, design-level). Win rate → reviewer
  preference between pre- and post-reasoning-trace output.
- Expected: ≥ +5% first-try success on abstract-task shapes after
  reasoning-trace becomes available, measured against Phase-1-only
  baseline on the same task shapes.
- Tolerance: ±50% (i.e. +2.5% improvement is directionally
  consistent).
- Falsification: if first-try success rate is unchanged or lower
  after 20 abstract-task iterations with reasoning-trace active,
  thought-based retrieval is not providing the claimed gain for
  coding work.
- Observation ready when: ≥ 20 iterations tagged
  `task_shape=abstract` have completed since reasoning-trace
  harvester landed (requires telemetry-gap closure listed in §4).
  Baseline = first-try success rate on the 20 most recent
  abstract-task iterations prior to reasoning-trace activation.
  Abstract-task tag criterion must be pre-declared (candidates:
  "refactor touching ≥ 3 files", "design decision recorded in
  task note", "plan-item list ≥ 4").

#### D5 — Memory invalidation surface
- Source: A-MEM (arXiv:2502.12110) update model + CBR Retain.
- Reported: No quantitative invalidation-specific metric.
- Adaptation: **Directional**.
- Expected: propagated veto reaches all entries sharing an edge
  with the vetoed entry within one recall cycle (correctness, not
  magnitude).
- Tolerance: exact propagation expected.
- Falsification: any case where a veto fails to propagate to
  linked entries indicates a bug in the edge traversal.
- Observation ready when: first veto with ≥ 1 linked entry is
  exercised. Correctness is tested, not sampled over iterations.

### 5.3 Phase 3 — Rehearsal and novelty (pending)

#### D1 — Scheduled rehearsal pass
- Source: Self-Synthesized Rehearsal (Huang et al., ACL 2024);
  Spurious Forgetting (ICLR 2025).
- Reported: rehearsal reduces alignment decay; "spurious forgetting"
  is largely re-anchorable.
- Adaptation: **Directional**. Hypothesis: rehearsal recovers
  convention usage after a gap.
- Expected: `rehearsal_convention_recovery_rate` ≥ 0.80 after a
  simulated 48h gap (matches M6.9 §2 success criterion #6).
- Tolerance: ±10% (0.72 – 0.88).
- Falsification: if recovery rate < 0.60 after rehearsal, either
  the gap simulation is harsher than real decay or rehearsal is
  not re-anchoring convention memory correctly.
- Observation ready when: ≥ 5 rehearsal passes completed (5 is
  the minimum to distinguish consistent recovery from one-shot
  luck). Denominator = convention entries re-acked / total
  convention entries in the canonical set.

#### D2 — Novel-task injector
- Source: WebRL (Qi et al., arXiv:2411.02337) failure-seeded
  curriculum; Voyager (arXiv:2305.16291) automatic curriculum.
- Reported: WebRL uses past failures to generate novel tasks;
  Voyager notes self-verification prevents memory shortcut abuse.
- Adaptation: **Direct class**. `memory_shortcut_attempted ∧
  ¬shortcut_succeeded` is the exact metric described.
- Expected: on novel-task injections, `shortcut_succeeded` rate ≤
  0.20 (matches design spec §7.3 Phase 3 proof criterion).
- Tolerance: ±10% (0.10 – 0.30).
- Falsification: if > 0.40 of novel-task shortcuts succeed, the
  injector is not producing truly novel tasks (the novelty
  spec is too lax).
- Observation ready when: ≥ 10 novel-task injections executed.
  Smaller sample sizes cannot reliably bound the success rate.

#### D3 — Confidence decay
- Source: Generative Agents recency weighting (arXiv:2304.03442).
- Reported: no directly comparable quantitative metric.
- Adaptation: **Directional**.
- Expected: decay-factor weighted recall produces different top-N
  ordering for entries older than 7 iterations vs newer entries
  (observable, not magnitude-gated).
- Tolerance: directional — decay must have measurable effect on
  recall ordering.
- Falsification: if decay factor has no observable effect on
  recall ordering after 20 iterations, decay is not wired into
  the scorer correctly.
- Observation ready when: ≥ 20 iterations include recall events
  where at least one candidate entry has age > 7 iterations.
  Comparison is per-event before vs after decay weighting.

### 5.4 Phase 4 — Curriculum and habit compilation (post-M6.8)

#### D1 — Failure-clustered curriculum
- Source: Voyager (arXiv:2305.16291) automatic curriculum; WebRL
  (arXiv:2411.02337).
- Reported: Voyager shows **3.3× item acquisition, 15.3× tech-tree
  milestone unlocking** over non-curriculum baseline.
- Adaptation: **Translated class**. Items → bounded roadmap tasks
  completed per supervised session. Milestones → roadmap milestone
  closures per chain.
- Expected: ≥ 2× bounded-task completion rate with curriculum
  active vs M6.8 chaining without curriculum (conservative —
  Voyager's Minecraft domain is much more structured than coding).
- Tolerance: ±40% (1.2× – 2.8× acceptable).
- Falsification: if curriculum chain completes no more tasks than
  random task-pick chain, failure-seeded curriculum is not
  transferring.
- Observation ready when: ≥ 5 chained supervised sessions with
  curriculum active AND ≥ 5 baseline chained sessions with
  random task-pick (M6.8-only, no curriculum) are recorded.
  Baseline sessions should be from M6.8 post-close era, not
  pre-M6.8 era.

#### D2 — Habit compilation
- Source: no canonical paper in design spec §5. Concept appears
  across 2024-2025 agent workshop literature ("habit compilation,"
  "trace compilation," "compiled plans") without a single
  authoritative reference. Treated here as **background
  expectation**, not formally cited source.
- Reported: workshop reports indicate compiled traces execute
  N× faster than model-backed traces; N varies widely.
- Adaptation: **Translated class** (workshop → coding). N varies
  widely (5× to 50× in workshop reports). mew's compiled-path vs
  model-backed fallback gives concrete `wall_time_ms` comparison.
- Expected: compiled-path tasks ≥ 3× faster than pre-compilation
  baseline on compiled-eligible tasks (matches design spec §12.2
  Phase 4 NFR).
- Tolerance: ±50% (1.5× – 4.5× acceptable).
- Falsification: if compiled paths are not measurably faster, the
  compilation step is adding overhead without dispatch benefit.
- Observation ready when: ≥ 3 compiled-path invocations and
  ≥ 3 pre-compilation baseline invocations on the same task
  shape are recorded. Baseline = identical task executed by
  model-backed path before the template was compiled.

#### D3 — Preference store
- Source: RLTHF (2024; design spec §5.9).
  (Historical-edits-alignment literature is conceptual background;
  not cited as primary source here because it is not in design
  spec §5.9.)
- Reported: preference-pair conditioning shows improvement in
  reviewer-preference-driven tasks (magnitudes vary).
- Adaptation: **Directional**. Prompt-time conditioning effect on
  output style.
- Expected: ≥ 10% reduction in reviewer edit rate on preference-
  eligible tasks once preference injection is active.
- Tolerance: ±50% (≥ 5% directionally consistent).
- Falsification: if reviewer edit rate is unchanged or higher with
  preference injection active, the retrieval/injection is not
  surfacing the right pairs.
- Observation ready when: ≥ 15 iterations after preference
  injection activation AND ≥ 15 pre-activation baseline iterations
  on similar task shapes are recorded. Edit-rate denominator =
  reviewer patch-edit events / total reviewer-approved iterations.

## 6. Observation log

Populated during Phase 1 proof (retroactively from landed evidence)
and Phase 2-4 implementation. The log is a table of observations per
deliverable, not per iteration.

### Observation log template

```
| Phase | Deliverable | Metric surface | Baseline | Sample window | Expected | Tolerance | Observed | Sample size | Date | Artifact link | Reason (if out of range or not measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
```

Column definitions:
- **Metric surface**: the §4 row that this observation measures,
  expressed as either a raw §12.3 telemetry field or a §4-derived
  measure.
- **Baseline**: the pre-deliverable or pre-phase reference value
  used to compute the expected change. If expected is an absolute
  ratio (e.g. `index_hit_rate ≥ 0.80`), baseline may be "N/A".
- **Sample window**: number of iterations or events backing this
  observation, per the deliverable's readiness rule in §5.
- **Observed**: the measured value. If not measured, write "not
  measured" and complete the Reason column.
- **Artifact link**: path to the proof artifact, close artifact
  section, or session-trace bundle that supports the observation.

### Readiness rules (when an observation is mature enough to record)

Each Phase 2-4 deliverable in §5 states its own readiness rule at
the end of its row, under a "Observation ready when..." line.
When that condition is first met, an observation row is added to
this log. Subsequent iterations may amend the same row with newer
data, preserving the original row via §7 amendment policy.

For Phase 1 deliverables (D1-D7) that have quantitative expectations,
observations are populated retroactively from landed proof artifacts
(`docs/M6_7_*_ITERATION_*.md`, `docs/M6_9_PHASE1_*.md` when it lands,
session traces already captured). Directional Phase 1 rows may record
"directional only" in the Observed column instead of a numeric value.

### Recording rule
- Each observation specifies sample size, date of last iteration,
  and artifact link.
- When an observation is outside `expected ± tolerance`, the Reason
  column must identify whether (a) the adaptation was wrong,
  (b) the implementation is incomplete, or (c) the literature's
  finding does not transfer to mew. The answer informs future
  Phase decisions.
- When a metric is impossible to measure (e.g. no pre-M6.9 baseline
  captured in time), record "not measured" with the specific cause.

### Aggregation rule for close artifact

The M6.9 close artifact (`docs/M6_9_CLOSE_GATE_*.md`) must include
an "Observed vs Expected" section using the following table schema:

```
| Phase.D | Metric surface | Expected | Tolerance | Observed | Status | Reason |
| --- | --- | --- | --- | --- | --- | --- |
```

- **Status** is one of: `in range` | `out of range` | `not measured`.
- One row per §5 deliverable. Missing measurements are recorded
  explicitly, not silently omitted (see §8 for the enforcement
  boundary).
- For Phase 1 rows already observed (landed behavior), the Observed
  column is populated from the referenced proof artifact.
- For Phase 2-4 rows, the Observed column is populated from the
  observation log in this document at close time.

The close artifact aggregation duplicates data intentionally: this
reference doc is the live working record; the close artifact is the
frozen-at-close snapshot.

## 7. Amendment policy

This is a reference document. Numeric values in §5 are hypotheses
derived from cited literature. If Phase 2-4 evidence shows a
specific expected value is miscalibrated for mew's domain:

1. **Revise in place** with a dated amendment block at the end of
   the affected §5 subsection, e.g.:
   ```
   Amended 2026-05-15: Phase 2 D3 acceptance rate target reduced
   from 0.50 to 0.40 after 30 iterations showed consistent 0.38
   acceptance with reviewer satisfaction. Reason: hindsight
   harvester generates higher-quality candidates than AgentHER's
   benchmark shape, so reviewer applies stricter filter.
   ```
2. **No formal proposal required** for amendments — this is a
   scientific reference, not a governance contract.
3. **Reviewer sign-off on the specific amendment** is preferred but
   not blocking; the amendment author's name + date is sufficient
   for non-controversial changes (e.g. tolerance widening based on
   real measurements).
4. **Substantive structural changes** (adding a new deliverable,
   changing paper citation) should go through reviewer-approved
   commit review at minimum.
5. **Never silently delete** an expected value or observation.
   Supersede with an amendment; keep the record of what was
   previously expected.

## 8. Relationship to close gate (formal)

M6.9 close gate remains as specified in
`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` §2:
the 7 success criteria plus NFR budgets per phase (§12). This
reference doc does not alter the formal close gate.

What it adds is:
- **Polish direction**: implementers target expected values during
  iteration, not just functional presence.
- **Close artifact evidence**: observed vs expected becomes a
  required section, giving the close artifact a scientific shape
  in addition to the functional shape.
- **Adaptation record**: if mew's observed values differ
  systematically from literature, that is documented domain
  adaptability data, useful for future research-heavy milestones
  (M8, M11).

The close gate does **not** require observed to match expected
within tolerance; it requires the table to be populated.

### Scope of the "missing measurement" rule

"Missing measurement = missing evidence, not automatic failure"
applies **only to reference-only expectations** in this document —
i.e. expected values that exist purely to quantify literature
adaptation. This rule does **not** weaken:

- **Design spec §2 success criteria** (the 7 formal close criteria
  in `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`), which
  require measurement-backed evidence as stated there.
- **Design spec §7 proof blocks** per Phase, which specify
  mandatory dogfood-scenario outputs and iteration-level observations.
- **Design spec §12 NFR budgets**, which have breach-policy
  consequences independent of this document.

If a §5 expected value happens to overlap a formal success criterion
(e.g. D4 `index_hit_rate ≥ 0.80` restates §2 criterion #4), the
formal success criterion is the governing requirement. This document
adds the literature grounding and tolerance; it does not displace
the close-gate obligation.

When in doubt, the design spec wins. This document is a
complementary scientific record.

## 9. Why this document exists (rationale preserved)

During the 2026-04-22 design conversation, three alternatives
were considered for strengthening M6.9 close verification:

1. Formal close-gate strengthening proposal matching M6.11 shape
   (A)/(B)/(C) — registered dogfood, statistical incidence gate,
   phase-transition calibration.
2. Scientific reference document with expected values from
   literature (this document).
3. Hybrid: reference doc + lightweight close-artifact requirement.

Option 2 was selected because:
- M6.9 is the most research-heavy milestone, so scientific
  framing matches the work.
- Numeric values locked in a formal gate become governance
  contracts that block Phase progress when literature
  adaptation is wrong; reference-doc values can evolve via
  amendment.
- Close artifact discipline already exists; reference doc
  integrates without new enforcement mechanism.
- Establishes a second close-gate strengthening pattern
  (scientific reference) alongside M6.11's engineering gate,
  giving future research-heavy milestones a precedent.

If Phase 2-4 evidence shows this document is insufficient
(e.g. implementers ignore the reference, close artifacts omit
the observation table), a more enforcing variant can be
proposed later. The reference-only shape is the minimum that
gives mew the scientific signal it needs.

### Pattern selection rubric for future milestones

Future milestones deciding between the two close-gate strengthening
patterns — **engineering gate** (M6.11 shape, formal proposal with
threshold-blocking CLI) vs **scientific reference** (M6.9 shape,
reference doc with observation log) — should choose as follows:

| Milestone trait | Preferred pattern |
| --- | --- |
| Failure mode is **operational** (stall, crash, latency regression) observable in production | **Engineering gate** |
| Failure mode is **hypothetical** (does adoption of pattern X produce benefit Y?) and only confirmable via measurement | **Scientific reference** |
| Close condition is **deterministic** (scenario passes OR fails on reproducible fixture) | **Engineering gate** |
| Close condition is **adaptation-heavy** (paper says X%, mew may differ; judgment on whether direction is consistent) | **Scientific reference** |
| Milestone rests primarily on **engineering practice** (governance, recovery, drafting reliability) | **Engineering gate** |
| Milestone rests primarily on **published research findings** (memory architectures, curriculum learning, continual learning) | **Scientific reference** |
| Risk is **regression below current baseline** | **Engineering gate** |
| Risk is **failure to achieve novel capability** that literature predicts | **Scientific reference** |

When the traits are split across the two columns, pick the pattern
matching the majority of traits. Hybrids are allowed (a milestone
may have both an engineering-gate proposal and a scientific-reference
doc), but hybrids require explicit justification for the scope
boundary between them.

Future candidate applications:
- **M8 Identity (cross-project self)**: research-heavy (identity
  persistence literature) + adaptation-uncertain → **scientific
  reference**.
- **M11 Inner Life**: research-heavy + directional metrics
  ("self-description coherence over time") → **scientific
  reference**.
- **M10 Multi-Agent Residence**: primarily engineering (governance,
  permission boundaries) with operational failure modes
  (disagreement artifact integrity) → **engineering gate**.
- **M7 Senses (when deeper wiring resumes)**: mixed, leaning
  engineering (signal correctness, suppression) → **engineering
  gate**.

These are suggestions, not commitments. The pattern choice belongs
to each milestone's own reviewer decision at activation time.

## 10. Related documents

- `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` —
  authoritative M6.9 design spec. §2 success criteria, §5
  research grounding, §7 phase deliverables, §12 NFR budgets are
  the canonical references this document quantifies.
- `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` —
  sister document for M6.11, using the engineering-gate pattern
  instead. Cross-reference for how the two patterns differ.
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` — feeds
  some Phase 4 deliverables (curriculum, preference store).
- `docs/ADOPT_FROM_REFERENCES.md` — broader adoption catalog;
  M6.9 is the §5.11 / §5.12 / §5.14 cluster plus the research
  additions above.
- `ROADMAP.md` M6.9 block — summary-level definition.
- `ROADMAP_STATUS.md` M6.9 entry — current status (`frozen` as of
  2026-04-22, Phase 1 substrate landed).
- `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` and
  `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` —
  active M6.11 work; M6.9 is frozen until M6.11 closes.

## 11. Amendment log

```
2026-04-22: initial document.
(future amendments land here with dated entries)
```
