# Resident Lane Architecture

Date: 2026-04-26
Status: reviewed draft; architecture reference, not a replacement milestone
Owner: resident architecture / M6.13 framing surface
Related:
- `ROADMAP.md`
- `ROADMAP_STATUS.md`
- `docs/DESIGN_2026-04-25_M6_13_DELIBERATION_LANE.md`
- `docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md`

## 1. Purpose

This document describes the ideal resident architecture for mew before M6.13
continues further.

It is a framing reference, not a replacement for
`docs/DESIGN_2026-04-25_M6_13_DELIBERATION_LANE.md`. M6.13 should keep its
current high-effort deliberation close gate. This document explains the broader
resident architecture that M6.13 should grow toward and the invariants it must
not violate while doing so.

The question is not only whether mew should add a `deliberation` lane. The
product question is:

> What kind of body would an AI model want to inhabit for long-running task and
> coding work?

The current answer is:

> mew should adopt a lane architecture with one authoritative work lane per
> task, multiple non-authoritative helper lanes, calibration economics recorded
> from day one, and a future resident meta loop that dispatches bounded work.

This is not a proposal to add many autonomous agents that all mutate state. It
is a proposal to separate authority, evidence, reasoning, memory, and
supervision so mew can become more reliable than a single reactive coding CLI.

## 2. Architecture Sketch

```text
                         +------------------------------+
                         |        Resident Context       |
                         | roadmap / tasks / memory      |
                         | metrics / user constraints    |
                         +---------------+--------------+
                                         |
                                         | later
                                         v
                         +------------------------------+
                         |       Resident Meta Loop      |
                         | observe / select / dispatch   |
                         | evaluate / update memory      |
                         +---------------+--------------+
                                         |
                                         | bounded work order
                                         v
+--------------------------------------------------------------------+
|                            Work Session                            |
|                                                                    |
|  one task / one active WorkTodo / one authoritative owner           |
|                                                                    |
|  +--------------------------------------------------------------+  |
|  | Lane Chooser                                                  |  |
|  | calibration economics                                         |  |
|  | cost / latency / rejection / rescue / verifier / reuse value |  |
|  +---------------+----------------------------------------------+  |
|                  |                                                 |
|                  v                                                 |
|  +--------------------------------------------------------------+  |
|  | Authoritative Lane                                           |  |
|  |                                                              |  |
|  | implementation lane                                          |  |
|  | - normal task/coding execution                               |  |
|  | - inspect / edit / test / recover for coding                 |  |
|  | - final output authority                                     |  |
|  | - preserves current tiny write path in v0                    |  |
|  +---------------+----------------------------------------------+  |
|                  |                                                 |
|                  | may call helper lanes                           |
|                  |                                                 |
|    +-------------+-------------+----------------+--------------+  |
|    v             v             v                v              |  |
| +---------+  +----------+  +--------------+  +--------------+ |  |
| | mirror  |  | memory   |  | deliberation |  | verifier     | |  |
| | lane    |  | lane     |  | lane         |  | lane         | |  |
| |         |  |          |  |              |  |              | |  |
| | replay  |  | recall   |  | hard blocker |  | test/proof   | |  |
| | bundle  |  | traces   |  | reasoning    |  | diagnostics  | |  |
| | shadow  |  | history  |  | plan/risk    |  |              | |  |
| +----+----+  +----+-----+  +------+-------+  +------+-------+ |  |
|      |            |               |                 |         |  |
|      +------------+---------------+-----------------+---------+  |
|                         evidence / advice only                  |  |
|                         no final write authority                 |  |
|                                                                    |
|                  v                                                 |
|  +--------------------------------------------------------------+  |
|  | Policy Gate                                                   |  |
|  | mechanical scope / permission / governance checks             |  |
|  +---------------+----------------------------------------------+  |
|                  |                                                 |
|                  v                                                 |
|  +--------------------------------------------------------------+  |
|  | Reviewer Gate                                                 |  |
|  | semantic approve / reject / request changes                   |  |
|  +---------------+----------------------------------------------+  |
|                  |                                                 |
|                  v                                                 |
|  +--------------------------------------------------------------+  |
|  | Apply / Verify / Record                                      |  |
|  | patch / report / tests / replay bundle / metrics / trace     |  |
|  +---------------+----------------------------------------------+  |
+------------------+-------------------------------------------------+
                   |
                   v
        +------------------------------+
        | Calibration Economics         |
        | lane cost                    |
        | first output latency         |
        | approval rejection rate      |
        | rescue edit rate             |
        | verifier failure rate        |
        | deliberation reuse value     |
        | memory trace reuse value     |
        +---------------+--------------+
                        |
                        | feeds future lane choice
                        v
                 +-------------+
                 | Lane Chooser|
                 +-------------+
```

Short form:

```text
implementation lane = hands
helper lanes        = eyes / memory / deep thought / tests
calibration         = measured evidence now, value function later
meta loop           = future resident supervisor
```

## 3. Core Principles

1. **Exactly one authoritative lane owns final output for a work item.**
   Multiple lanes may observe or advise, but only one lane can apply patches,
   mark task progress, or produce the final accepted report.

2. **Helper lanes are non-authoritative by default.**
   Mirror, deliberation, memory, verifier, and source-check lanes may write
   evidence artifacts, but they cannot silently replace authoritative output.

3. **The normal implementation lane must remain reliable before broad
   deliberation or meta-loop autonomy.**
   A resident supervisor over unreliable hands only amplifies failure. If the
   implementation lane regresses, use the existing M6.6/M6.10 reopen rules or
   M6.14 repair episodes instead of expanding M6.13 indefinitely.

4. **Calibration economics starts as instrumentation and later chooses lanes.**
   M6.13 v0 should record the evidence needed for expected-value routing. Lane
   dispatch can become EV-based only after comparable lane outcomes exist.

5. **Deliberation is justified only by durable reuse.**
   A high-effort lane that does not internalize useful reasoning into later
   cheaper work is only a wrapper around a stronger model.

6. **Memory is evidence, not prompt stuffing.**
   Lanes should retrieve lane-specific summaries and traces, not load all
   historical memory into every turn.

7. **The meta loop is future work.**
   M6.13 should leave clean dispatch/result contracts that a future resident
   supervisor can use, but should not add an autonomous second planner now.

8. **One task maps to one work session and one authoritative owner.**
   Helper lanes may be invoked through recorded lane decision events, but they
   do not become independent task owners.

## 4. Task Kinds And Authoritative Lanes

Lane architecture is not only for coding. Different task kinds can have
different default authoritative lanes.

The non-coding lanes below are architectural direction, not M6.13 scope. Do
not add them to ROADMAP as active implementation targets until the coding lane
substrate has proven itself.

```text
task.kind=coding
  authoritative lane = implementation
  output authority   = patch / verifier / reviewer-approved code change

task.kind=research
  authoritative lane = research
  output authority   = sourced report / citations / uncertainty

task.kind=routine
  authoritative lane = routine
  output authority   = task update / question / summary / lightweight action

task.kind=planning
  authoritative lane = planning
  output authority   = roadmap/status proposal, normally reviewer-approved
```

Helper lanes are shared across task kinds:

```text
memory lane        retrieves relevant prior evidence
mirror lane        records non-authoritative replay/diagnostics
deliberation lane  analyzes hard blockers or high-ambiguity decisions
verifier lane      checks proof/test/source confidence
source lane        checks freshness and credibility for research
```

The immediate coding focus remains the implementation lane because coding is
where mew must first become credible as a resident body.

For M6.13 v0, `memory lane` and `verifier lane` are adapter concepts over
existing recall and verifier surfaces, not new autonomous lane backends. They
become true lanes only if a later milestone gives them explicit dispatch,
result, and calibration contracts.

## 5. Implementation Lane

The existing `tiny` path is the canonical persisted v0 lane id. It must remain
canonical in source, `WorkTodo.lane`, replay metadata, and legacy bundle
resolution during M6.13.

`implementation` is a conceptual and user-facing display name for that lane,
not a v0 storage migration.

Target terminology:

```text
tiny           = canonical persisted lane id in M6.13 v0
implementation = display/conceptual name for the same authoritative lane
```

The implementation lane should be optimized for ordinary bounded coding tasks:

- inspect current files and local state
- choose exact edit surface
- produce paired source/test patches
- run focused verification
- recover from rejection or verifier failure
- classify failures without hidden supervisor rescue
- hand useful evidence back to memory and calibration

The implementation lane is successful when it is normally usable the way an AI
coding CLI is usable: it can complete small-to-medium scoped coding tasks with
bounded review and without frequent supervisor-authored rescue edits.

That quality bar should be measured through existing M6.6/M6.10/M6.14 gates,
not turned into an unbounded Phase 1 requirement. M6.13 Phase 1 should preserve
the current tiny write path, the M6.11 patch-draft compiler discipline, and the
exact cached-window contract while adding lane observability.

## 6. Mirror Lane

The mirror lane is a proof and observability lane.

It should:

- write lane-scoped replay metadata
- reconstruct what the authoritative lane did
- prove that non-authoritative lane artifacts do not change authoritative
  output
- make calibration and debugging easier

It should not:

- apply patches
- mark a task done
- override implementation lane results
- turn into a second planner

Mirror comes before deliberation because it proves lane identity, bundle
layout, filtering, and reconstruction without increasing model authority.

## 7. Deliberation Lane

The deliberation lane is a bounded high-effort reasoning lane for hard blockers.

It should:

- run only when reviewer-commanded or when a blocker is eligible
- bind backend, model, effort, timeout, schema, and budget explicitly
- return structured reasoning, plan, risk, or blocker analysis
- fall back to implementation on timeout, refusal, budget block, schema
  failure, validation failure, or reviewer rejection
- produce distilled reasoning traces only after reviewer approval

It should not:

- become write-capable in v0
- store raw transcript as durable memory
- be the default route for normal coding
- be used to hide implementation-lane weakness

The close proof for deliberation is not "a stronger model solved a task". The
close proof is:

```text
hard task -> deliberation advances it -> reviewer-approved trace
later same-shape task -> tiny/implementation solves it using the trace
```

## 8. Calibration Economics

Calibration economics is first an instrumentation contract, then a value
function for lane choice.

Each lane attempt should emit comparable evidence:

```text
task_kind
lane
task_shape
blocker_code
model/backend/effort
timeout
budget_reserved
budget_spent_or_estimated
first_output_latency
first_edit_latency
approval_rejected
verifier_failed
fallback_taken
rescue_edit_used
reviewer_decision
outcome
later_reuse_value
```

Minimum v0 event shape:

```json
{
  "event": "lane_attempt",
  "task_id": 649,
  "session_id": 636,
  "task_kind": "coding",
  "lane": "tiny",
  "lane_display_name": "implementation",
  "task_shape": "bounded_source_test_patch",
  "blocker_code": "",
  "model_backend": "codex",
  "model": "gpt-5.5",
  "effort": "high",
  "timeout_seconds": 60,
  "budget_reserved": null,
  "budget_spent_or_estimated": null,
  "first_output_latency_seconds": 12.4,
  "first_edit_latency_seconds": 183.0,
  "approval_rejected": false,
  "verifier_failed": false,
  "fallback_taken": false,
  "rescue_edit_used": false,
  "reviewer_decision": "approved",
  "outcome": "success_mew_first",
  "later_reuse_value": "unknown"
}
```

`later_reuse_value` starts as `unknown`. It becomes meaningful only after a
later same-shape task demonstrates that a trace or lane artifact changed the
outcome.

The lane chooser should eventually use a simple expected-value shape:

```text
EV(lane | task_shape, blocker)
  = expected_success_or_reuse_value
    - cost
    - latency
    - rejection_penalty
    - rescue_penalty
    - verifier_failure_penalty
    - policy_risk_penalty
```

M6.12 remains the read-side failure-science surface. M6.13 should make lane
events and lane outcomes compatible with that surface so the chooser can use
real evidence later.

In v0, the chooser should be rule-based. The important requirement is that it
records the features that a future EV chooser would need. It should not claim
EV-based routing until there are enough comparable outcomes to defend the
decision.

The simplest v0 decision table is:

```text
fresh state or local missing context    -> refresh implementation state
ordinary scoped coding                  -> tiny / implementation
observability or replay proof           -> mirror
eligible semantic hard blocker          -> deliberation candidate
policy, budget, permission, governance  -> block or ask reviewer
```

## 9. Memory Implications

Lane architecture changes memory from a shared prompt blob into typed evidence.

Recommended memory surfaces:

```text
task memory
  objective, constraints, status, result

lane memory
  lane-specific attempts, failures, costs, fallbacks

reasoning traces
  distilled situation / reasoning / verdict / reuse conditions

calibration ledger
  measurable lane outcomes and reviewer decisions

user/project memory
  durable preferences, project rules, long-lived context
```

Read policy should be lane-specific:

```text
implementation reads:
  task scope, code anchors, similar patch failures, verifier history

deliberation reads:
  blocker summary, failed attempts, relevant traces, budget/model constraints

research reads:
  user constraints, prior research, source credibility and freshness rules

lane chooser reads:
  compact calibration summaries, not raw transcripts
```

Write policy should be approval-aware:

- implementation may write task results and verifier evidence
- mirror may write non-authoritative replay artifacts
- deliberation may write candidate reasoning artifacts
- only reviewer-approved distilled traces enter durable reasoning memory
- raw deliberation transcripts are not durable memory

## 10. Resident Meta Loop

The meta loop is the future resident supervisor.

It should eventually:

- observe roadmap, tasks, sessions, metrics, memory, and user constraints
- select the next task or ask a question when authority is missing
- dispatch a bounded work order to an authoritative lane
- choose helper lanes through calibration economics
- evaluate outcome against roadmap gates
- update memory, status, and next action

It should not be implemented before the implementation lane and lane evidence
contracts are stable.

The future meta loop should subsume the existing M6.8.5 selector pattern, not
compete with it. The M6.14 repair ledger is the feedback channel for substrate
failures that the meta loop must respect: when mew-first implementation fails
structurally, the product milestone pauses and repair evidence goes through
M6.14 rather than hidden supervisor rescue.

The safe dependency order is:

```text
1. stable implementation lane instrumentation
2. lane-aware replay and calibration evidence
3. mirror lane proof
4. bounded deliberation lane
5. internalization proof
6. resident meta loop
```

The meta loop is not a new source of write authority. It dispatches work to
lanes that already have explicit contracts.

## 11. M6.13 Recommendation

The current M6.13 title emphasizes deliberation. Keep that milestone and its
close gate. Do not replace it with this broader architecture document.

Use this document as a framing reference that sharpens M6.13 terminology,
instrumentation, and future compatibility.

Recommended M6.13 interpretation:

```text
Phase 1: Lane Foundation
  - preserve tiny compatibility
  - keep tiny as the canonical persisted lane id
  - use implementation only as display/conceptual terminology
  - prove ordinary tiny behavior is unchanged
  - emit lane-aware calibration fields for future EV routing

Phase 2: Mirror / Replay Lane
  - lane-scoped non-authoritative bundles
  - legacy bundle resolver treats missing lane as tiny
  - lane-aware report/filter can include/exclude mirror artifacts

Phase 3: Bounded Deliberation Lane
  - reviewer-commanded and eligible automatic attempts only
  - explicit model/effort/timeout/schema/budget
  - reasoning-only output
  - fallback to implementation

Phase 4: Internalization Proof
  - reviewer-approved reasoning trace
  - later same-shape task solved by tiny/implementation using the trace
  - reviewer confirms the trace was used
  - lane economics records whether deliberation paid for itself
```

The existing M6.13 close requirement remains load-bearing:

```text
hard task -> deliberation advances it -> reviewer-approved trace
later same-shape task -> tiny/implementation solves it using that trace
```

This keeps the important M6.13 idea and prevents the milestone from becoming
"call a stronger model".

## 12. Not M6.13

This document intentionally looks beyond M6.13. These parts are not M6.13
implementation scope:

- autonomous resident meta loop
- non-coding authoritative lanes (`research`, `routine`, `planning`)
- true autonomous memory/verifier lane backends
- EV-based automatic routing from sparse data
- write-capable deliberation
- broad multi-agent residence
- user-scope identity or inner-life product work

## 13. Non-Goals For The Next Slice

Do not implement these immediately:

- autonomous meta loop
- write-capable deliberation
- multiple authoritative lanes for one task
- concurrent lane races
- permanent provider/model routing
- raw transcript memory
- cross-project resident identity
- general passive AI behavior outside task/coding work

## 14. Open Decisions

Resolved for v0:

1. `tiny` remains the canonical persisted lane id. `implementation` is a
   display/conceptual name only.
2. M6.13 keeps its current milestone title and close gate.
3. Calibration fields are mandatory instrumentation in Phase 1/2. EV routing
   is future work after comparable lane outcomes exist.
4. Non-coding authoritative lanes stay in this architecture document only and
   should not enter ROADMAP until the coding lane substrate is proven.

Still open:

1. Which exact metrics are mandatory for lane-choice EV v0 beyond the minimum
   event shape in section 8?
2. Where should lane-attempt events be stored: existing session trace, M6.12
   ledger-adjacent JSONL, or both?
3. What is the first mirror-lane proof fixture that is small enough for
   mew-first implementation but strong enough to validate reconstruction?

## 15. Adoption Criteria

Adopt this architecture if reviewers agree that:

- lane composition is the right substrate
- implementation lane reliability comes before broad deliberation
- calibration economics belongs in the lane chooser
- meta loop should be deferred but designed for
- memory must become lane-scoped evidence rather than raw context stuffing

Reject or revise it if reviewers find that:

- lane architecture adds complexity without improving implementation success
- meta loop should be the first-class architecture now
- calibration economics cannot be made reliable enough for dispatch
- `implementation` terminology breaks too much existing M6.13 compatibility
- non-coding lanes should be separated into a later product architecture doc
