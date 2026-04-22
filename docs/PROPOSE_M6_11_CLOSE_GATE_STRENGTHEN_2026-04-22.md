# M6.11 Close-Gate Strengthening Proposal — Dogfood + Statistical + Calibration

Date: 2026-04-22.
Status: **proposal for reviewer approval**. Not yet applied to ROADMAP.md
or `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`.
Target reviewers: user (Kaito Miyagi) + Codex (M6.11 reviewer).

## TL;DR

The current M6.11 close gate proves that `#399` and `#401` become
**replayable and recoverable**, but does not prove they become
**rarer**. This proposal adds three reviewer-gated additions to the
M6.11 close gate:

- **(A) Dogfood scenario registration** — `m6_11-*` scenarios in the
  dogfood enum, matching M6.9 Phase 1 discipline
- **(B) Statistical incidence gate** — measure `#399` + `#401` bucket
  incidence across 20 bounded iterations; require ≥50% reduction vs
  pre-M6.11 baseline or a documented reason
- **(C) Phase 2/3 calibration checkpoint** — if off-schema rate > 5%
  across Phase 2 replay bundles, pause Phase 3 rollout and schedule
  Phase 2.5 model-behavior calibration

**Crucial non-goal: no wall-clock condition.** All three criteria are
event-driven (iteration count, off-schema rate, bucket incidence),
not time-based. The M6.7 `≥4h wall-clock` condition caused the
`gate_pending` + split-execution complexity; M6.11 should not repeat
that failure mode.

Expected cost: 2-4 extra iterations over the current close path.
Expected benefit: M6.11 close artifact actually proves the stall
pattern is rarer, not just replayable.

## 1. Why this exists

The M6.11 design (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`)
and its review (`docs/REVIEW_2026-04-22_LOOP_STABILIZATION_DESIGN_REVIEW.md`)
define a close gate that is **structurally sound but measurably
incomplete**. Specifically:

- The current gate (ROADMAP M6.11 Done-when) requires "at least one
  bounded mew-first implementation slice completes... no rescue edits
  attributable to the old drafting failure buckets."
- "At least one" and "attributable" are both undefined.
- Replay bundles prove failures are **recoverable**, not that they
  are **less frequent**.
- M6.9 Phase 1 established dogfood registration discipline
  (`m6_9-*` scenarios per deliverable). M6.11 currently drops that
  discipline, repeating the M6.5-M6.7 gap pattern identified in
  `docs/ADOPTION_STATUS_*`-style audits.
- The design review itself flags a missing "calibration gate before
  Phase 3 rollout" (line 88-89), noting that if model off-schema
  output rate is high, a single bounded retry is insufficient. The
  review calls this non-blocking for shipping, but it is a real
  verification gap.

This proposal adds the three missing verification surfaces so M6.11
close means "the stall pattern is demonstrably rarer and the
discipline stays intact," not "we wrote code that can catch stalls."

## 2. Explicitly non-goals (what this proposal does not do)

- **No wall-clock condition.** Nothing in (A), (B), or (C) is
  time-gated. The M6.7 experience demonstrated that wall-clock gates
  force `gate_pending` branches and split-execution workarounds. M6.11
  should close on event criteria only.
- **No replacement of the existing close gate.** This proposal is
  additive. The current seven Done-when items stay; three more are
  added.
- **No re-opening of M6.7 or M6.9.** Both remain in their current
  states. This proposal only touches M6.11.
- **No new milestones.** M6.10 stays as registered. M6.11 scope is
  strengthened, not split.
- **No design re-review for Phases 0-4.** The design review already
  found Phases 0-4 implementation-ready; this proposal does not
  revisit that.
- **No new infrastructure.** All three additions reuse existing dogfood,
  session telemetry, and replay bundle infrastructure.

## 3. Proposed strengthening

### 3.1 (A) Dogfood scenario registration

Register five `m6_11-*` scenarios in the dogfood scenario enum
(same discipline as `m6_9-*`) before M6.11 close:

- **`m6_11-compiler-replay`** — runs the `#399` fixture through
  `PatchDraftCompiler` and asserts the compiler emits a blocker code
  (not a generic parse failure), with no same-surface reread
- **`m6_11-draft-timeout`** — runs the `#401` fixture (timeout
  before draft), asserts `WorkTodo` survives, and asserts the
  recovery action offered is `resume_draft_from_cached_windows`
  (not generic `replan`)
- **`m6_11-refusal-separation`** — synthesises a refusal-shaped
  model response and asserts it is classified as
  `model_returned_refusal`, not `model_returned_non_schema`; covers
  both streaming and non-streaming paths per the Phase 0 refusal
  review gap
- **`m6_11-drafting-recovery`** — scripted resume/follow-status
  flow; asserts the same blocker code and next recovery action are
  emitted in both surfaces for the same `WorkTodo`
- **`m6_11-phase4-regression`** — runs the three M6.6 comparator task
  shapes with the new drafting path active; fails if median wall time
  exceeds `B0.iter_wall × 1.10`, matching M6.9 Phase 1 regression
  discipline

All scenarios must be:
- **deterministic** — no live model call beyond what fixtures provide
- **≤ 5 min wall time each** on the existing dogfood harness
- **JSON-reportable** via the existing `proof-summary --strict` path

The regression scenario `m6_11-phase4-regression` is tied to the
phase gate (§7.2 NFR discipline), not to a specific deliverable,
matching the carve-out already in M6.9 §10.

### 3.2 (B) Statistical incidence gate

During Phase 4 validation, measure `#399` + `#401` bucket incidence
across a controlled iteration batch:

- **Batch size**: 20 bounded mew-first implementation slices
- **Baseline**: pre-M6.11 incidence rate computed from the same
  iteration shapes pre-Phase-0, taken from the existing M6.7 / M6.9
  Phase 1 session traces. If no pre-M6.11 baseline is available for
  a given slice shape, use the incidence rate from the soft-stopped
  M6.7 candidate queue (N-A through N-H) as the fallback baseline.
- **Metric**: per-bucket incidence rate (fraction of iterations
  that produce a `#399`-shaped or `#401`-shaped failure)
- **Gate**: ≥50% reduction in combined `#399 + #401` incidence
  versus baseline. A reduction short of 50% requires a documented
  reason (e.g. model-side off-schema rate unchanged) and a reviewer
  sign-off; it does not auto-close the milestone.
- **Recording**: results land in `docs/M6_11_CLOSE_GATE_*.md`
  alongside the existing close artifact.

This is iteration-count based (20), not wall-clock based. The
20-iteration batch can execute over any duration.

### 3.3 (C) Phase 2/3 calibration checkpoint

Insert a single checkpoint between Phase 2 close and Phase 3 start:

- **Measurement surface**: Phase 2 live-failure replay bundles
  collected during normal operation
- **Checkpoint criteria**:
  - off-schema response rate ≤ 5% across collected bundles
  - refusal response rate ≤ 3% across collected bundles
  - no single bundle type exceeds 40% of total bundle count
    (prevents one failure mode dominating)
- **If any criterion fails**: Phase 3 rollout pauses. A Phase 2.5
  calibration slice is inserted (model-behavior adjustment, prompt
  tightening, or contract revision). Phase 3 resumes only after
  Phase 2.5 produces a re-measured bundle set meeting the criteria.
- **If all criteria pass**: Phase 3 proceeds as currently scoped in
  the design doc.

Checkpoint is iteration-count / ratio based, not time-based.

## 4. Close gate after strengthening

The ROADMAP M6.11 Done-when block gains three items:

```markdown
[existing 7 items stay]

- `m6_11-*` dogfood scenarios listed in §3.1 of the close-gate
  strengthening proposal are registered in the dogfood enum and pass
  under `proof-summary --strict` during Phase 4 validation
- a 20-slice bounded-iteration batch shows ≥50% combined reduction
  in `#399` + `#401` incidence versus the pre-M6.11 baseline, or a
  reviewer-signed-off documented reason for a smaller reduction
- the Phase 2/3 calibration checkpoint passed or a Phase 2.5
  calibration slice landed before Phase 3 started, recorded in the
  design doc or the close artifact
```

No wall-clock condition. No minimum duration. Close eligibility is
determined by iteration count + ratio thresholds + scenario pass.

## 5. Why no wall-clock condition

The M6.7 close required `≥4h wall-clock`. This had three bad effects
that should not recur in M6.11:

1. `gate_pending` as a separate status — a milestone could not be
   `done` or `in_progress` but sat in a third state waiting for
   clock to advance
2. Frozen close-watch copy at `/private/tmp/mew-m67-close-watch-*`
   to accumulate clock independently of mainline work — governance
   complexity for a simple time delay
3. Mainline work continued on M6.9 D1 while M6.7 clock ticked in
   the frozen copy — the clock was real but operationally irrelevant

A wall-clock gate is appropriate when the *thing being proved* is
continuity (daemon, passive residence). M6.11 proves *structural*
behavior (drafting path works, failure buckets recoverable), which
is deterministic per-iteration. Iteration-count gates are a better
fit: you close when N iterations demonstrate the behavior, not
when N hours pass.

## 6. Entry / exit criteria

### Entry
- reviewer approval of this proposal
- current M6.11 Phases 0-4 scope unchanged; this proposal adds to
  close gate, not to implementation scope
- ROADMAP.md M6.11 Done-when block updated to include the three new
  items

### Exit (M6.11 close)
All existing 7 Done-when items, plus:
- (A) five `m6_11-*` dogfood scenarios registered and passing
- (B) 20-slice statistical gate passed or documented reason
- (C) Phase 2/3 calibration checkpoint crossed

### Retreat
If after 2 rounds of bounded iteration batches the statistical gate
(B) cannot show ≥50% reduction and no structural cause can be
identified:
- M6.11 close is blocked
- Reviewer decides: extend scope to include a new Phase 7 targeting
  the residual stall source, or accept the documented reason and
  close with caveat
- The retreat branch must be recorded in the close artifact

## 7. Implementation order

Three reviewer-gated iterations, bounded to their respective
surfaces. None of these block Phase 0-4 implementation; they are
parallel-gate work. Minimum order:

1. **Strengthen-Iter-A**: register five `m6_11-*` dogfood scenarios
   in the dogfood enum. One source file + tests. Fixtures already
   exist per Phase 2 design, so this is mostly wiring.
2. **Strengthen-Iter-B**: add incidence-measurement instrumentation
   to session traces (`blocker_code` + `bucket_tag` fields already
   planned in Phase 0; extend with per-iteration summary for batch
   analysis). One source file + tests.
3. **Strengthen-Iter-C**: add the Phase 2/3 checkpoint evaluator as
   a `mew proof-summary --m6_11-phase2-calibration` invocation.
   One source file + tests.

Strengthen-Iter-A may be landed during Phase 2. Iter-B may be
landed during Phase 3. Iter-C must land before Phase 2/3 transition
but its evaluation runs at the transition, not at land time.

Estimated total: 2-4 extra iterations beyond the current Phase 0-4
scope, no more than 1-2 days of wall time.

## 8. Alternatives considered

### Alt 1: accept current close gate as-is
- What: close M6.11 on the existing 7 items.
- Against: close artifact proves recoverability, not rarity; the
  user's own concern remains unanswered.
- For: fastest close.
- Verdict: rejected; the milestone's stated purpose is to fix
  "ちょこちょこ失敗," so close must show the stall pattern actually
  reduced.

### Alt 2: only add (A) dogfood registration
- What: add dogfood scenarios but not (B) and (C).
- Against: dogfood alone does not measure incidence; fixtures always
  pass by construction, so dogfood does not catch the "model still
  off-schema 20% of the time" failure.
- For: lowest overhead.
- Verdict: rejected; (A) alone is necessary but not sufficient.

### Alt 3: split (A)(B)(C) into a separate new milestone
- What: M6.11.1 "Close-gate verification."
- Against: close gate verification is not a milestone in its own
  right; it is how M6.11 closes honestly. Splitting introduces
  registration overhead without new scope.
- For: clean scope separation.
- Verdict: rejected.

### Alt 4: add a wall-clock condition (e.g. "≥4h observed uptime")
- What: require M6.11 to sit in production for N hours before close.
- Against: wall-clock conditions caused the M6.7 `gate_pending`
  problem. M6.11 proves structural behavior, which does not need
  clock.
- For: mirrors some M3 / M6 proof shapes.
- Verdict: rejected; see §5.

### Alt 5: run all 20 iterations serially after Phase 4
- What: Phase 5 "validation batch" runs 20 iterations end-to-end.
- Against: wastes supervised-reviewer time; the 20 iterations can
  happen during normal Phase 3 / Phase 4 work if iterations are
  logged with bucket tags.
- For: cleaner measurement window.
- Verdict: partially adopted — (B) batch can be "20 iterations
  observed during Phase 4" rather than a dedicated window, reducing
  overhead.

## 9. Risks

1. **Baseline unavailable**: pre-M6.11 baseline incidence for
   `#399 + #401` may not exist in clean form. Mitigation: use the
   soft-stopped M6.7 candidate queue (N-A through N-H) as the
   documented baseline; this was the exact failure pattern that
   motivated M6.11 and is already in the plan doc.
2. **False statistical floor**: 20 iterations is a small sample; a
   50% reduction might still be noise. Mitigation: the gate allows
   "documented reason for smaller reduction" with reviewer sign-off,
   so statistically marginal cases escalate to reviewer judgment
   rather than fail silently.
3. **Phase 2/3 calibration always trips**: if the model is
   consistently off-schema at >5%, every Phase 2 run triggers
   Phase 2.5. Mitigation: this is the intended behavior; if
   baseline is high, the milestone should notice.
4. **Dogfood registration fatigue**: adding `m6_11-*` scenarios
   feels like bureaucracy. Mitigation: Phase 2 fixtures already
   exist; scenarios are thin wrappers.
5. **Scope creep toward model tuning**: Phase 2.5 might drift into
   fine-tuning the model prompt. Mitigation: Phase 2.5 is explicitly
   scoped to contract/prompt adjustments, not to model training or
   API backend changes.

## 10. Instructions for implementation agent

When reviewer approval of this proposal is recorded:

1. **Update ROADMAP.md** M6.11 Done-when block to add the three new
   close items from §4. Leave the existing 7 items unchanged.
2. **Update `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`** with a
   new appendix section "Close-Gate Strengthening" citing this
   proposal and summarising (A)(B)(C). Do not modify Phases 0-6
   implementation scope.
3. **Update `ROADMAP_STATUS.md`** M6.11 entry to reflect the added
   close conditions. Active milestone decision block gains a note
   that the strengthen additions are reviewer-approved and parallel
   to the Phase 0-4 implementation path.
4. **Implement in §7 order**: Iter-A during or after Phase 2,
   Iter-B during or after Phase 3, Iter-C before Phase 2/3
   transition.
5. **Land as bounded reviewer-gated iterations** matching existing
   M6.11 iteration shape. Do not bundle.
6. **Record close artifact** at M6.11 close in
   `docs/M6_11_CLOSE_GATE_2026-04-22.md` including:
   - dogfood scenario JSON reports
   - 20-iteration batch incidence data with baseline
   - calibration checkpoint outcome (pass / Phase 2.5 ran / both)
7. **Do not change M6.7, M6.9, or M6.10** as part of this work.

## 11. Why this is written as a proposal

M6.11 is the active milestone. Modifying its close gate mid-stream
is governance-adjacent and requires the same reviewer approval
pattern as any M6.x gate change. This proposal matches the shape of
`docs/PROPOSE_MILESTONES_2026-04-21_M6_8_M6_9.md` and
`docs/PROPOSE_M6_7_UNSTICK_2026-04-21.md` so the approval decision is
durable and auditable.

Rejecting the proposal is also a valid outcome; in that case the
existing 7-item close gate stands and the user's concern about
"stall pattern actually rare, not just recoverable" remains
accepted-with-documented-caveat.
