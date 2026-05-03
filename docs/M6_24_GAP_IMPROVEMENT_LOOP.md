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
- `docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md` for the active
  long-command continuation repair design
- `docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md` for the trigger to
  replace narrow budget routing with all-command generic managed exec
- `docs/REVIEW_2026-05-02_CODEX_CLI_LONG_BUILD_CONTINUATION_PATTERNS.md`
- `docs/REVIEW_2026-05-02_CLAUDE_CODE_LONG_BUILD_CONTINUATION_PATTERNS.md`

Do not resume new broad Terminal-Bench measurement until this controller or the
decision ledger records why measurement is higher value than repairing the
selected gap class.

Current selected gap class:
`structural_tool_runtime_budget`.

Current selected next action:
`M6.24 -> grouped read-only diagnostic repair floor -> UT -> replay -> dogfood -> compile-compcert emulator -> exactly one same-shape speed_1`.

Active authoritative design:
`docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`.

Foundational substrate design:
`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.

This supersedes both the stale 2026-05-01 Long-Build Substrate Phase 0 schema +
safety-parity harness next-action text and proof escalation from the Phase 6
continuation transfer gate. The generic long-command continuation contract
remains implemented and valid, but the latest same-shape speed rerun built far
enough for the compiler artifact to exist and then failed default runtime
linking while `long_command_runs=[]` and `latest_long_command_run_id=null`.
The production-visible managed-dispatch and nonterminal-handoff repairs are now
reviewed and approved. Later same-shape speed reruns moved the blocker through
non-timeout source-acquisition retry repair, managed timeout resume-budget
repair, typed read-only diagnostic budget handling, and now grouped read-only
diagnostic budget handling. The current saved proof artifact
`mew-m6-24-typed-diagnostic-budget-compile-compcert-1attempt-20260503-1653`
is reproduced by exact replay/dogfood and, importantly, by the
`m6_24-compile-compcert-emulator` without spending another Harbor run. The
latest local repair is the grouped diagnostic predicate for shell grouping,
`./configure -help`, pipelines, `/dev/null` redirects, and bounded read-only
shell loop control. Stop rule: if another read-only diagnostic parser false
negative appears, stop adding parser cases and open a diagnostic-contract
redesign slice.

The one-run timeout-shape diagnostic is now recorded as classification evidence.
The previous reruns redirected the controller from `long-build wall-time /
continuation budget` to config/source-script external-hook repair, production
continuation dispatch, nonterminal handoff, compound budget-stage promotion,
non-timeout source-acquisition retry repair, managed timeout resume-budget
repair, typed read-only diagnostic repair-floor handling, and now grouped
diagnostic repair-floor handling. Do not spend another `proof_5` or broad
measurement run until the full
UT/replay/dogfood/emulator pre-speed operation and same-shape speed rerun after
this repair are recorded.

Do not grow the budget classifier into a broad shell classifier. The durable
decision is in `docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md`: keep
budget routing narrow unless repeated false negatives, repeated false positives,
classifier accretion, lifecycle-ledger dominance, or recovery-state inversion
triggers a deliberate all-command generic managed-exec design slice.

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

4. Before spending a live speed same-shape rerun, did the pre-speed operation
   pass on current head?
   required:
     1. focused UT / local validation for the changed gap surface
     2. `mew replay terminal-bench` against the latest relevant saved Harbor
        artifact, or a synthetic same-shape replay fixture if no artifact exists
     3. `mew dogfood --scenario m6_24-terminal-bench-replay`, with
        `--terminal-bench-job-dir` and explicit `--terminal-bench-assert-*`
        flags when validating an existing Harbor artifact
     4. for `compile-compcert` long-build repairs, run
        `mew dogfood --scenario m6_24-compile-compcert-emulator`; pass
        `--terminal-bench-job-dir <latest-saved-job>` after every speed proof
        so the raw model action fixture is refreshed from the latest
        `mew-report.json`
     5. only after 1-4 pass, spend exactly one selected same-shape live
        `speed_1`
   no  -> fix the UT/replay/dogfood/emulator failure before live speed proof
   yes -> spend exactly the selected same-shape speed rerun

5. Did the speed same-shape rerun improve the selected gap class?
   yes -> record delta, then choose the next highest-leverage gap or resume
          broad measurement if the decision ledger says the threshold is met
   no  -> first reproduce the saved Harbor artifact through replay and dogfood
          with assertions for the classified failure; only then record
          unchanged/regressed and revise the repair route or reclassify the gap
```

The selected gap class must be written before implementation starts. If the
current resident cannot write this chain in one line, do not implement:

```text
M6.24 -> selected gap class -> architecture fit -> required next action -> pre-speed operation -> same-shape rerun condition
```

## Failed-Proof Reproduction Rule

When a live `speed_1` or `proof_5` misses, do not repair directly from the live
Harbor output. Reproduce the exact saved artifact first:

1. `mew replay terminal-bench --job-dir <saved-job> --task <task> ...` with
   assertions matching the classified current failure.
2. `mew dogfood --scenario m6_24-terminal-bench-replay
   --terminal-bench-job-dir <saved-job> ...` with the same assertion shape.
3. Only after both pass may code repair start.

If dogfood cannot express the current failure shape, fix dogfood
instrumentation before repairing the product gap.

For `compile-compcert`, also refresh the emulator fixture from the saved
artifact:

```text
mew dogfood --scenario m6_24-compile-compcert-emulator \
  --terminal-bench-job-dir <saved-job>
```

This does not rebuild CompCert. It extracts the model-turn action JSON that mew
parsed from the speed proof, writes a local JSONL fixture, recomputes the
long-build state, and re-runs the raw action through budget/continuation
policy. If this emulator fails, repair the emulator-detected substrate gap
before spending another live speed proof.

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

## Current Controller Note - 2026-05-03

The latest same-shape `compile-compcert` speed_1 after compound budget repair
scored `0/1`, but it moved the selected gap again: `latest_long_command_run_id`
is now present and the managed long command reached terminal `failed` state.
The run lasted `9m58s`; `work_report.stop_reason` is
`long_command_budget_blocked`. The new gap is
`non_timeout_source_acquisition_retry_blocked_as_same_timeout`: terminal
source acquisition failed with `curl` exit `22`, `timed_out=false`, but recovery
used timeout-style same-command resume policy and blocked the corrected source
channel retry as `repeat_same_timeout_without_budget_change`.

Selected chain:

`M6.24 -> long_dependency/toolchain gap -> execution-contract Phase 0-6 pre-speed gate -> same-shape speed_1`

The current repair is generic detector/resume-state policy: only timed-out or
killed long commands require same-idempotence resume with larger budget.
Terminal non-timeout failures produce `repair_failed_long_command`; exact
repeats remain blocked, but changed corrective commands are allowed. The
same-shape rerun recorded a newer narrower gap: external pass with stale
internal long-build closeout. codex-ultra classified it as reducer/closeout
`REPAIR_NOW`; the generic local repair plus codex-requested hardening is
implemented and locally validated in
`docs/M6_24_FINAL_CLOSEOUT_PROJECTION_REPAIR_2026-05-03.md`. The follow-on
flag-day execution-contract repair in
`docs/DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md` is implemented through
Phase 6 and committed as `4dbd099`. It shifts acceptance/reducer/recovery proof
from task-semantic shell labels toward typed `ExecutionContract` and
`CommandRun` evidence, while keeping safety/display parsers and negative
fallback fixtures as guardrails. The pre-speed operation has passed on current
head, and codex-ultra approved the phase gate as
`safe_to_commit_pre_speed`. Do not run broad measurement or `proof_5` next.
Spend exactly one same-shape `compile-compcert` speed_1, then classify the
result as clean closeout, moved narrower gap, or regression.

Update 2026-05-03 12:17 JST: that execution-contract speed_1 was run and
classified. The prior execution-contract gate moved; the current selected gap
is `failed_long_command_repair_timeout_floor_overconstrained` in
`tool_runtime_budget`. The exact Harbor artifact was reproduced through both
`mew replay terminal-bench` and `mew dogfood --scenario
m6_24-terminal-bench-replay` with explicit assertions. The local repair keeps
the 600s floor for true build repairs while allowing bounded changed
source/diagnostic probes.
Review update: codex-ultra session `019debd8-a8c8-7d91-8fcf-27f147c89eb4`
approved after a request-change round that added post-wall-ceiling enforcement
for recover actions. The next action is the pre-speed operation on current head,
then exactly one same-shape `compile-compcert` speed_1.

Update 2026-05-03 12:56 JST: that same-shape speed_1 was run and classified.
The prior failed-long-command repair-budget gate moved; the current selected
gap is `dependency_generation_diagnostic_budget_floor_overconstrained` in
`tool_runtime_budget`. The exact Harbor artifact was reproduced through both
`mew replay terminal-bench` and `mew dogfood --scenario
m6_24-terminal-bench-replay` with explicit assertions. The local repair keeps
the `600s` floor for side-effecting dependency/build repairs, but routes
read-only diagnostics such as `find`, `sed`, and `make -n` to the diagnostic
floor only after segment/token validation. codex-ultra review session
`019debfe-47ae-71c0-b778-744d4aa70d99` approved after two request-change
rounds. The next action is the pre-speed operation on current head, then
exactly one same-shape `compile-compcert` speed_1.

Update 2026-05-03 13:56 JST: that same-shape speed_1 was run and classified.
The prior dependency-generation diagnostic budget gate moved; the current
selected gap is `managed_long_command_poll_blocked_by_final_proof_reserve` in
`tool_runtime_budget`. The exact Harbor artifact was reproduced through both
`mew replay terminal-bench` and `mew dogfood --scenario
m6_24-terminal-bench-replay` with explicit assertions. codex-ultra session
`019dec30-429e-77d2-a75d-a233bdeb3af7` classified this as structural and
recommended repair now. The next action is a narrow generic repair: allow only
`poll_long_command` for an already running/yielded managed command to spend the
final-proof reserve, while preserving reserve for start/resume/recover/new
commands and preserving terminal-only artifact proof. The local repair is
implemented and codex-ultra review session
`019dec39-7f1d-7901-af16-e2d1950b0a3e` approved after one request-change
round. The next action is the pre-speed operation on current head, then exactly
one same-shape `compile-compcert` speed_1.

Update 2026-05-03 14:55 JST: that same-shape speed_1 was run and classified.
The prior managed-poll reserve gate moved; the current selected gap is
`timed_out_managed_long_command_resume_budget_not_preserved` in
`structural_tool_runtime_budget`. The run reached real managed
`make -j10 ccomp` progress, then timed out in `runtime_build` before
`/tmp/CompCert/ccomp` existed. The exact Harbor artifact was reproduced through
both `mew replay terminal-bench` and `mew dogfood --scenario
m6_24-terminal-bench-replay` with explicit assertions for `blocked`,
`build_timeout`, `resume_idempotent_long_command`, and external reward `0`.
codex-ultra session `019dec63-b7ff-7a31-9d54-661b13a6062c` classified this as
structural and recommended repair now. This is still narrow long-build
substrate evidence, not an all-command generic managed-exec trigger. The next
action is the generic timeout/resume-budget repair in
`docs/M6_24_MANAGED_TIMEOUT_RESUME_BUDGET_REPAIR_2026-05-03.md`.

Repair update 2026-05-03 15:06 JST: the local repair now caps terminal timed-out
managed long-command remaining budget by the prior work-session wall slice, and
the reducer emits `resume_budget_exhausted` instead of advertising
`resume_idempotent_long_command` when remaining budget is below
`minimum_resume_seconds + reserve_seconds`. Exact artifact replay and dogfood
now pass with the repaired assertion. Focused and broader long-build/work-session
tests, terminal-bench replay/dogfood tests, scoped ruff, JSONL parse, and diff
check pass. codex-ultra review session
`019dec74-191f-75b1-97f0-da6e0ed306fe` approved; the requested direct
`resume_budget_exhausted` policy test was added and passed. The next action is
the pre-speed operation on current head, then exactly one same-shape
`compile-compcert` speed_1.
