# M6.24 Gap Improvement Loop

Purpose: keep M6.24 from drifting between broad measurement, local fixes, and
reference-derived architecture work. This file is the controller for closing
the measured Codex gap, not a general idea backlog.

## Current Controller

M6.24 is in `improvement_phase`.

Authoritative inputs:

- `docs/M6_24_DECISION_LEDGER.md`
- latest `docs/M6_24_GAP_CLASS_PLAN_*`
- `docs/M6_24_GAP_BASELINE_2026-04-29.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`
- `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md` for accepted structural repairs
- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md` for lane,
  authority, helper-lane, and calibration-fit decisions

Do not resume new broad Terminal-Bench measurement until this controller or the
decision ledger records why measurement is higher value than repairing the
selected gap class.

## Loop

For every candidate gap, run this decision chain:

```text
1. Is there enough evidence to classify the target gap?
   no  -> add instrumentation/logging and speed-rerun the same shape
   yes -> continue

2. Is the gap local/polish, structural, measurement-missing, or ambiguous?
   local/polish        -> bounded fix, then same-shape rerun
   structural          -> reference-backed rearchitecture, then same-shape rerun
   measurement-missing -> add the missing measurement, then speed-rerun
   ambiguous           -> add classifier/logging, then same-shape rerun

3. If the fix changes task policy, lane behavior, helper lanes, verifier
   authority, or repair loop shape, did it pass the Architecture Fit Gate?
   no  -> stop and write the lane/profile/helper decision first
   yes -> continue

4. Did the speed same-shape rerun improve the selected gap class?
   yes -> record delta, then choose the next highest-leverage gap or resume
          broad measurement if the decision ledger says the threshold is met
   no  -> record unchanged/regressed, then either revise the repair route or
          reclassify the gap
```

The selected gap class must be written before implementation starts. If the
current resident cannot write this chain in one line, do not implement:

```text
M6.24 -> selected gap class -> architecture fit -> required next action -> same-shape rerun condition
```

## Gap-Class Repair History Rule

Before designing another repair for a gap class or task shape that has already
had two or more repair/rerun cycles, build or refresh a compact gap-class
dossier.

The dossier is required before code changes when the next action affects the
same gap class, task family, task shape, or a profile/prompt section that was
created from that evidence. Task-specific histories are evidence sections
inside the dossier, not the primary unit of memory. It must summarize:

- chronological attempts and reruns;
- observed failure shape for each attempt;
- repair hypothesis and implemented layer;
- whether the repair was detector/state, profile/contract, tool/runtime,
  verifier/proof, or prompt-only guidance;
- before/after score or failure-shape movement;
- recurring patterns and explicitly rejected duplicate fixes;
- current next action and the same-shape rerun condition.

Use the dossier to answer this preflight before any next repair:

```text
1. Is this failure new, a repeat, or a narrower version of an older failure?
2. Which previous repair already tried to address this gap or task shape?
3. Why is the proposed fix not duplicating an earlier detector/prompt patch?
4. What is the lowest durable layer for the fix?
   instrumentation/report -> detector/resume state -> profile/contract ->
   tool/runtime -> prompt section registry
5. Does this indicate prompt/profile accretion rather than a new task blocker?
```

If a gap class has accumulated multiple detector plus THINK-guidance repairs
without stable close-gate success, treat that as a process signal. Pause the
next local repair long enough to decide whether the correct next action is
profile/contract consolidation or a prompt section registry, not another
one-off guidance line.

## Repair Close Rule

A same-shape proof reaching the frozen Codex target closes only that selected
repair. It does **not** automatically reopen broad measurement.

For CPU-heavy long dependency/toolchain builds, proof escalation must be
resource-normalized. A high-parallelism `-k N -n N` proof can create host-level
CPU/memory contention that is not part of the per-trial task contract. When a
speed proof passes but a parallel proof fails only by wall timeout across all
trials, record the parallel run as harness evidence and rerun with sequential or
low-concurrency scheduling before starting a mew-core repair.

For Harbor proof commands used in this project, `-k` is the trial count and
`-n` is the worker concurrency. A sequential five-trial proof is therefore
`-k 5 -n 1`, not `-k 1 -n 5`.

Before broad measurement resumes, re-evaluate the controller thresholds against
the latest aggregate and batch evidence:

```text
aggregate/current gap <= 20 pp -> measurement may resume if the decision ledger records why
aggregate/current gap > 20 pp  -> stay in improvement_phase and select the next gap class
accepted structural blocker    -> pause measurement and repair the blocker first
```

If a resident just wrote "resume measurement" because a single selected repair
passed, but the aggregate gap is still above threshold, treat that as process
drift. Correct the decision ledger, record the process correction, and select
the next highest-leverage gap instead of launching another broad benchmark.

## Classification Rules

Use `measurement_missing` when the current artifacts cannot answer why mew lost
against the Codex target. The only allowed work is instrumentation plus a
minimal rerun that preserves speed.

Use `local/polish` when the failure is task-specific, the generic loop remains
sound, and a bounded fix can be validated on the same task shape.

Use `structural` when the failure repeats across tasks or indicates that mew's
work-session body cannot reliably preserve one of these contracts:

- task contract / acceptance criteria
- relevant context window
- patch lifecycle
- verifier and artifact proof
- tool policy / permission boundary
- approval and rejection semantics
- resume / recovery state
- lane authority, helper-lane routing, or calibration boundary

Use `ambiguous` when a failure might be structural but the evidence is too thin.
Add logs or a classifier first; do not start rearchitecture from weak evidence.

## Architecture Fit Gate

Run this gate before implementing any structural repair that changes task
policy, lane behavior, helper-lane behavior, verifier authority, or repair loop
shape. This is mandatory for hard-task fixes because "hard" is a difficulty
signal, not automatically a new lane.

Read `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md` and write the
architecture fit decision in the design note, decision ledger, or gap ledger
before code changes start.

Answer these questions:

```text
1. Is this still the same authoritative output?
   coding patch / verifier / reviewer-approved code -> implementation/tiny

2. Are the artifact, authority, loop, success metric, and calibration unit
   different enough to justify a new lane?
   no -> keep the existing lane and implement a policy/profile/guard
   yes -> propose a new lane with explicit authority, non-goals, and proof

3. Is a helper lane enough?
   deliberation / memory / verifier may advise or provide evidence, but may not
   become the write-capable authoritative lane in M6.24.

4. Does the repair hide implementation-lane weakness?
   yes -> reject or convert it into implementation-lane hardening

5. Does the proposal violate current non-goals?
   no multiple authoritative lanes for one task, no write-capable deliberation,
   no concurrent lane races.
```

Default rule for M6.24 coding gaps:

```text
ordinary coding gap       -> implementation/tiny lane
hard coding gap           -> implementation/tiny lane with a hard-task profile
hard semantic blocker     -> optional deliberation helper, then return to tiny
different task kind       -> later lane milestone, not an M6.24 repair shortcut
```

If the gate chooses "new lane", do not implement it as an M6.24 gap repair
unless `ROADMAP.md` and `ROADMAP_STATUS.md` explicitly name that lane work as
the active repair. Otherwise record it as a future resident-architecture task
and continue with the smallest implementation-lane repair.

## Reference-Backed Rearchitecture Procedure

Only enter this procedure after a gap is classified as structural.

1. Start from the mew failure class and task evidence. Do not start by importing
   an attractive Codex or Claude Code feature.
2. Inspect why Codex can pass the same shape and mew cannot. The local Codex
   source reference is `references/fresh-cli/codex`.
3. Inspect existing reference summaries, especially:
   - `docs/ADOPT_FROM_REFERENCES.md`
   - `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
   - `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`
   - relevant `docs/REVIEW_*` or `docs/DESIGN_*` files for the gap class
4. Run the Architecture Fit Gate. For coding tasks, the default repair shape is
   an implementation/tiny profile or guard, not a new authoritative lane.
5. If needed, ask `acm run` with `codex-ultra` to audit the reference source
   for the specific gap class. Use `claude-ultra` for difficult architecture
   review, not for open-ended brainstorming.
6. Translate the concept into mew's resident work-session architecture.
7. Implement the smallest generic substrate change.
8. Rerun the same failed shape and record before/after evidence.

Do not add Terminal-Bench-specific solvers. The repair must improve the generic
arbitrary-workspace `mew work` path.

## Process-Change Rule

The loop itself may be optimized, but only with an explicit trial boundary.

Process changes are allowed only when all of these are recorded in
`docs/M6_24_DECISION_LEDGER.md`:

- current pain
- expected benefit
- one-run trial boundary
- rollback condition
- adopted / rejected decision after the trial

Do not change the loop because a new process feels cleaner. Change it only when
the current loop blocks classification, repair, or rerun evidence.

## Rerun Budget Rule

Do not spend `-k 5 -n 5` on every repair cycle. A five-trial rerun is the close
or escalation proof, not the default diagnostic loop.

Use the smallest rerun that can answer the current question:

```text
classification / missing instrumentation -> 1 trial
small generic repair smoke               -> 1 trial
noisy or partially stochastic repair      -> 2 trials
close-gate / resume-measurement proof     -> 5 trials
benchmark parity comparison               -> documented batch size
```

Speed-reruns must keep the same task, model, permissions, timeout shape, and
agent wrapper unless the selected gap is the run shape itself. The smaller
trial count is allowed because it answers a narrower question: "did the failure
mode move?" rather than "what is the stable pass rate?"

Escalate from a speed-rerun to `-k 5 -n 5` only when one of these is true:

- a speed-rerun shows a material improvement and the repair is a close
  candidate
- the result is contradictory or variance-sensitive enough that one trial is
  misleading
- the decision ledger is about to resume broad measurement
- the user explicitly asks for a five-trial proof

Record both the rerun tier and the reason in the decision ledger or gap ledger.

## Gap Ledger Contract

Append one JSON object per classified gap or repair attempt to:

`proof-artifacts/m6_24_gap_ledger.jsonl`

Recommended fields:

```json
{
  "schema_version": 1,
  "recorded_at": "2026-04-29T00:00:00Z",
  "record_type": "gap|repair|rerun|process_change",
  "task": "terminal-bench-task-name",
  "batch": "M6.24 Batch N",
  "mew_result": "pass|fail|partial|runner_error|unknown",
  "codex_target": "pass|fail|partial|unknown",
  "gap_class": "measurement_missing|local_polish|structural|ambiguous",
  "gap_reason": "short stable reason",
  "evidence": ["path/to/result.json", "path/to/job.log", "path/to/doc.md"],
  "repair_route": "instrument_then_rerun|local_fix|m6_14_repair|reference_backed_rearchitecture|defer",
  "architecture_decision": "no_lane_change|implementation_profile|helper_lane|new_lane|unknown",
  "authoritative_lane": "tiny|implementation|research|routine|planning|unknown",
  "helper_lanes": ["deliberation"],
  "same_shape_key": "stable rerun shape",
  "history_ref": "docs/M6_24_DOSSIER_<GAP_CLASS>.md",
  "prior_repairs_considered": ["long_dependency_build_state_progress_contract", "long_dependency_wall_clock_and_targeted_artifact_build_contract"],
  "rerun_tier": "speed_1|speed_2|proof_5|batch",
  "rerun_reason": "why this trial count is enough",
  "same_shape_rerun_required": true,
  "status": "open|repairing|rerun_pending|improved|unchanged|regressed|deferred",
  "score_before": "0/5",
  "score_after": null,
  "decision_ref": "docs/M6_24_DECISION_LEDGER.md#...",
  "notes": "short note"
}
```

The ledger is operational evidence. If a field is unknown, write `unknown` or
`null` rather than omitting the gap entirely.

## Resume Rule

On context compression or long-session reentry, read this file before selecting
work. The next task must be one of:

- classify a measured failure into the gap ledger
- create or refresh the gap-class repair dossier before another repair cycle
- add missing instrumentation for a selected gap
- run the Architecture Fit Gate for a selected structural repair
- repair exactly one selected gap class
- rerun the same shape after repair
- update the decision ledger to resume measurement with evidence

Anything else is drift unless the user explicitly changes direction.
