# Milestone Addition Proposal — M6.8 and M6.9

Date: 2026-04-21.
Status: **proposal for reviewer approval**. Not yet in ROADMAP.md or
ROADMAP_STATUS.md.
Target reviewers: user (Kaito Miyagi) + Codex (M6.7 supervisor reviewer).

## Why this proposal exists

M6.7 is active. Its ROADMAP definition ends at "supervised self-hosting
loop" with no named successor milestones. In practice, several follow-on
concepts have already been discussed in design reviews:

- **M6.8 Task Chaining**: the operational step that removes human
  latency between M6.7 iterations by letting mew pick the next roadmap
  task itself, still under reviewer gating.
- **M6.9 Durable Coding Intelligence**: the substrate step that turns
  mew's persistent state into a coding advantage, ending the current
  "Codex parity" ceiling. Design already exists at
  `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` (Round 2
  reviewer-verified as implementation-ready for Phase 1).

Neither is in ROADMAP.md or ROADMAP_STATUS.md. That absence is
problematic for three reasons:

1. **Governance**: M6.7 forbids mew from self-authoring roadmap-status
   or milestone-close edits. Without named successors, reviewer
   decisions about "what to credit next" are implicit, which is the
   exact condition M6.7 tries to prevent.
2. **Ordering clarity**: the user has decided — M6.7 → M6.8 → M6.9
   Phase 1-3 (with Phase 4 after M6.8). This decision is currently
   only in session context, not in the durable roadmap.
3. **Agent motivation**: M6.9 is the first coding-track milestone
   whose value is not parity with Codex CLI. Delaying its registration
   as a dream-goal changes what both mew and human implementers
   prioritize during M6.7 remaining work.

This proposal requests reviewer approval to add both milestones to
ROADMAP.md and ROADMAP_STATUS.md, *without* changing M6.7's active
status or its remaining scope-fence-hardening and 8h-supervised-proof
work.

## Governance note

This document is a proposal, not a self-edit. Per M6.7's governance
rule, milestone registration requires explicit human sign-off. The
implementation agent receiving this doc must:

- **not** edit ROADMAP.md or ROADMAP_STATUS.md directly without
  confirming reviewer approval of this proposal text;
- treat any reviewer push-back on wording, ordering, or done-when gates
  as authoritative;
- record the approval (reviewer id, timestamp, any diff from this
  proposal) in the same commit that lands the ROADMAP edits.

## Proposed M6.8 — ROADMAP.md entry

Insert between current Milestone 6.7 (line 386) and current Milestone 7
(line 427).

```markdown
## Milestone 6.8: Task Chaining - Supervised Self-Selection

Remove the per-iteration human-dispatch latency from the M6.7 loop by letting
mew select its next roadmap task itself while reviewer gating stays in place.

Target:

- task-selection mode for the supervised loop: mew reads the roadmap and
  proposes the next bounded task at iteration close, under the same scope
  fence and drift canary used in M6.7
- reviewer approves, edits, or rejects the proposed task before the next
  iteration begins; rejection returns control to the human
- chained iteration identity: each iteration records `previous_task_id` and
  `selector_reason` so drift across chains is auditable
- scope fence extended to the selector: selector output cannot touch
  roadmap-status, milestone-close, or governance files
- cap on consecutive automatic selections before a hard human checkpoint
  (initial cap: 3 per supervised run)
- proof-or-revert applies to each iteration in the chain, not to the chain
  as a whole; a single failed iteration does not cascade

Done when:

- mew completes three consecutive bounded iterations in a single supervised
  session where mew chose each next task, with reviewer approval recorded
  per iteration and zero rescue edits
- at least one reviewer task-rejection is recorded, showing the selector
  can be steered without breaking the chain
- scope fence holds: no selector output touches roadmap-status,
  milestone-close, or governance files across the proof run
- drift canary stays green across the full chained run
- an attempt to run chained iterations without reviewer approval is rejected
  and logged as a governance violation

Why it matters:

- M6.7 proves mew can implement one roadmap task safely. M6.8 proves mew
  can implement several in a row without requiring the human to pick each
  one. This is the operational bridge from reviewer-gated single-shot
  execution to reviewer-gated supervised operation. Unattended autonomy
  remains explicitly out of scope.
```

## Proposed M6.9 — ROADMAP.md entry

Insert after M6.8 (before current Milestone 7). The design document at
`docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` is the
authoritative spec; this ROADMAP entry is the summary gate.

```markdown
## Milestone 6.9: Durable Coding Intelligence

Turn mew's persistent state into a coding advantage so that the Nth iteration
on the same repository is measurably smarter than the 1st. This is the first
coding-track milestone whose goal is not parity with Codex CLI but a
capability Codex CLI cannot structurally have.

Target:

- five coding-domain memory types layered on existing typed memory:
  reviewer-steering, failure-shield, file-pair/symbol-edge, task-template,
  reasoning-trace
- outcome-gated write gates per type, and a Revise step on the reuse path
- symbol/call-graph-aware durable index keyed to `(module, symbol_kind,
  symbol_name)`, with file paths as secondary keys, so refactors do not
  invalidate memory
- reviewer-diff capture of approved `(ai_draft, reviewer_approved, ai_final)`
  triples as raw material for a later preference store
- hindsight harvester that relabels failed trajectories into candidate
  cases, routed through reviewer approval before entering durable memory
- reasoning-trace harvester that distills (situation, reasoning, verdict)
  triples at shallow and deep abstraction levels
- scheduled rehearsal passes and novel-task injection as a memory-coverage
  metric, to prevent alignment decay and over-reliance on memory
- drift controls: reviewer veto with edge-propagating invalidation, confidence
  decay, growth budgets per type, and comparator rerun against M6.6 slots
- design spec: see `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`
  for the canonical schema, phase split, and proof protocol

Done when:

- on a predeclared set of 10 repeated task shapes, median wall time per task
  decreases over the first five repetitions with no increase in reviewer
  rescue edits
- at least three reviewer corrections from past iterations fire as durable
  rules in later iterations, and at least one would have caused a rescue
  edit if not caught
- at least two previously reverted approaches are blocked pre-implementation
  by durable failure-shield memory in a later iteration
- at least 80% of first-read file lookups in a post-Phase-1 iteration are
  served by the durable symbol/pair index rather than fresh search
- drift canary stays green across five consecutive iterations while memory
  accumulates, and at least one novel-task injection forces exploration
  without silent memory reliance
- after a deliberate 48-hour gap or a simulated alignment-decay pass, mew
  recovers prior convention usage within one iteration via a rehearsal pass,
  without reviewer steering
- at least two iterations explicitly recall a past reasoning trace and a
  reviewer confirms the recall shortened deliberation; at least one of
  those recalls lands on an abstract task, not a mechanical edit
- the M6.6 comparator is rerun with durable recall active and shows
  measurable gain over the M6.6 baseline attributable to the new memory

Why it matters:

- M6.5 through M6.8 track parity and operational autonomy. None of them use
  the one thing mew has that reactive CLI agents cannot have: durable state
  across sessions. Without M6.9, mew is a slower, safer Codex CLI with a
  daemon. With M6.9, mew's Nth visit to the same repo is structurally better
  than the 1st, which is the only long-term basis for a resident that a
  frontier model would prefer to inhabit over Claude Code or Codex CLI.
```

## Proposed ROADMAP_STATUS.md changes

### Summary table — insert two new rows

After the existing `6.7. Supervised Self-Hosting Loop` row and before
`7. Senses: Inbound Signals`, add:

```markdown
| 6.8. Task Chaining: Supervised Self-Selection | `not_started` | Remove per-iteration human-dispatch latency from the M6.7 loop by letting mew pick the next roadmap task itself under reviewer gating. |
| 6.9. Durable Coding Intelligence | `not_started` | Turn persistent state into a coding advantage so the Nth iteration on the same repo is measurably smarter than the 1st. Spec: `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`. |
```

### Active Milestone Decision block — append ordering note

Append a paragraph near the existing reasoning block that explains:

```markdown
- M6.8 (Task Chaining) and M6.9 (Durable Coding Intelligence) are now
  registered as proposed successors. Neither is active. Ordering: M6.7
  closes first, including the supervised 8-hour proof. Then M6.9 Phase 1-3
  may begin under M6.7's supervised loop shape. M6.8 may begin in parallel
  with M6.9 Phase 1-3 or before M6.9 Phase 4, which depends on M6.8.
- This ordering was chosen over "M6.9 first" after weighing the risk of
  building durable memory on top of an unstable loop versus the compound
  cost of running more iterations without durable memory. The judgement
  was that a stable supervised loop is a better substrate on which to
  develop durable coding intelligence, and that Phase 4 curriculum work
  benefits from chaining being already proven.
```

## Entry gates

### M6.8 entry gate
- M6.7 Done-when all items recorded (scope-fence enforcement beyond the
  current visible fence, 8-hour supervised proof recorded).
- Reviewer approval logged before the first chained run begins.

### M6.9 entry gate
- M6.7 closed.
- Delta doc (§10 of the design doc) written and reviewer-approved before
  any `src/mew` code edits for M6.9 land.
- Phase 1 Deliverables D1-D6 land as six separate bounded M6.7-shaped
  iterations; do not bundle.

## Dependencies (summary)

```
M6.7 Supervised Self-Hosting Loop (active)
    closes -> enables M6.8 and M6.9 Phase 1-3

M6.8 Task Chaining
    closes -> enables M6.9 Phase 4

M6.9 Durable Coding Intelligence
    Phase 1-3 depend only on M6.7
    Phase 4 depends on M6.8
```

M7 (Senses), M8 (Identity), M9 (Legibility), M10 (Multi-Agent
Residence), M11 (Inner Life) remain gated behind M6.7 close and are
unaffected by this proposal in ordering.

## Instructions for implementation agent

When reviewer approval of this proposal is recorded:

1. **Apply ROADMAP.md edits first**, inserting the two milestone blocks
   verbatim in the positions specified (between current 6.7 and 7).
   Do not reflow surrounding content.
2. **Apply ROADMAP_STATUS.md edits second**: insert the two table rows
   in order, then append the ordering paragraph in the Active Milestone
   Decision block. Do not alter any existing rows, including M6.7's
   `in_progress` status.
3. **Land as a single commit** scoped to ROADMAP.md and
   ROADMAP_STATUS.md only. Message should name both milestones and cite
   this proposal path.
4. **Do not start M6.8 or M6.9 implementation work in the same commit
   or session**. Implementation begins only after M6.7 closes (see
   entry gates above).
5. **Reviewer-approval record**: include, in the commit body, the
   reviewer's approval id and any diff this commit takes from the
   wording in this proposal. If the reviewer asked for changes, apply
   them and record the change, do not silently adopt them.
6. **If ROADMAP.md structure has changed** between the time this
   proposal was written and the time of the edit (e.g., milestones
   re-numbered), stop and flag the divergence to the reviewer before
   proceeding. Do not attempt to auto-reconcile.

## Why this is written as a proposal, not as an edit

M6.7 is the active milestone. Self-authored milestone additions are
exactly the failure mode M6.7's scope fence protects against. Presenting
these additions as a reviewer-approved proposal keeps the M6.7 loop
honest and makes the ordering decision durable in the roadmap rather
than implicit in chat history.

If this proposal is rejected or amended, the counter-proposal should
take the same shape: document the ROADMAP/STATUS edits as text,
describe the reasoning, and route through the same reviewer gate.
