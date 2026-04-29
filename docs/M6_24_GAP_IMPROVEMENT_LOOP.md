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

3. Did the same-shape rerun improve the selected gap class?
   yes -> record delta, then choose the next highest-leverage gap or resume
          broad measurement if the decision ledger says the threshold is met
   no  -> record unchanged/regressed, then either revise the repair route or
          reclassify the gap
```

The selected gap class must be written before implementation starts. If the
current resident cannot write this chain in one line, do not implement:

```text
M6.24 -> selected gap class -> required next action -> same-shape rerun condition
```

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

Use `ambiguous` when a failure might be structural but the evidence is too thin.
Add logs or a classifier first; do not start rearchitecture from weak evidence.

## Reference-Backed Rearchitecture Procedure

Only enter this procedure after a gap is classified as structural.

1. Start from the mew failure class and task evidence. Do not start by importing
   an attractive Codex or Claude Code feature.
2. Inspect why Codex can pass the same shape and mew cannot. The local Codex
   source reference is `references/fresh-cli/codex`.
3. Inspect existing reference summaries, especially:
   - `docs/ADOPT_FROM_REFERENCES.md`
   - `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
   - relevant `docs/REVIEW_*` or `docs/DESIGN_*` files for the gap class
4. If needed, ask `acm run` with `codex-ultra` to audit the reference source
   for the specific gap class. Use `claude-ultra` for difficult architecture
   review, not for open-ended brainstorming.
5. Translate the concept into mew's resident work-session architecture.
6. Implement the smallest generic substrate change.
7. Rerun the same failed shape and record before/after evidence.

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
  "same_shape_key": "stable rerun shape",
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
- add missing instrumentation for a selected gap
- repair exactly one selected gap class
- rerun the same shape after repair
- update the decision ledger to resume measurement with evidence

Anything else is drift unless the user explicitly changes direction.
