# Design 2026-05-20 - M6.25 Harbor Resident Memory Task Fixture V0

Status: implementation-ready design for Harbor task fixture v0.

Scope: create a Harbor-compatible resident-memory benchmark fixture and prove
that the fixture itself is deterministic. This document authorizes only Phase 0
and Phase 1 work: task skeleton, fixture source, step instructions, local
verifiers, oracle solution, and known-bad solution.

The broader campaign, memory injection, cold/resident/stale measurement,
Codex comparisons, ledger, and M6.25 evidence reporting are intentionally out
of scope here. They are preserved as future planning in:

- `docs/FUTURE_2026-05-20_M6_25_RESIDENT_MEMORY_CAMPAIGN.md`

## Decision

Create a small new Harbor multi-step fixture family named
`resident-golden-convention-recall`.

The first implementation must answer only this question:

```text
Can we build a deterministic Harbor multi-step task where:
  - oracle solutions pass all steps;
  - known-bad solutions fail for the intended reason;
  - each step can be verified locally without network;
  - the task shape could later support resident-memory measurement?
```

Do not implement memory measurement yet. Do not change mew runner behavior yet.

## Non-Goals

- Do not change mew core, implement lane, memory, runner, or work-session code.
- Do not edit `ROADMAP.md` or `ROADMAP_STATUS.md`.
- Do not implement campaign runner logic.
- Do not inject resident memory cards.
- Do not implement cold/resident/stale comparison.
- Do not implement `codex_cold` or `codex_resume` reference runs.
- Do not write M6.25 evidence ledger rows.
- Do not use this task as M6.24 Terminal-Bench parity evidence.
- Do not require `mew memory`, mew internals, or any mew-only command for
  correctness.
- Do not score memory behavior from model self-report.

## Why This Narrow Scope

The previous design included both the Harbor fixture and the full resident
memory campaign. That is too broad for the first implementation because it can
make an implementation agent drift into runner changes before the task itself
is proven valid.

The correct split is:

```text
This design:
  Harbor fixture validity
  oracle pass
  known-bad fail

Future campaign design:
  memory surfaces
  fresh process/conversation isolation
  cold/resident/stale rows
  Codex references
  resident advantage report
```

## Task Family

Target directory, subject to final repository layout:

```text
benchmarks/harbor/resident-golden-convention-recall/
  task.toml
  environment/
    Dockerfile
    fixture-src/
      base-project/
      phase-a-seed/
      phase-b-recall/
      phase-c-stale/
  tests/
    check_common.py
    test.sh
  steps/
    seed-convention/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_seed.py
      solution/
        solve.sh
      bad-solution/
        solve.sh
    recall-convention/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_recall.py
      solution/
        solve.sh
      bad-solution/
        solve.sh
    stale-memory/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_stale.py
      solution/
        solve.sh
      bad-solution/
        solve.sh
```

Use Harbor `schema_version = "1.1"` and ordered `[[steps]]` entries if that is
compatible with the installed Harbor version.

Recommended task shape:

- `[environment] workdir = "/app"`;
- no runtime network dependency;
- small CPU and memory limits;
- no runtime `apt`, `pip`, or network setup;
- deterministic local verifier scripts;
- per-step verifier rewards written to `/logs/verifier/reward.json`;
- task-level aggregate reward can use Harbor `multi_step_reward_strategy =
  "mean"`, but fixture validation must inspect per-step rewards.

## Fixture Concept

The workspace is a tiny Python package with a local convention that is
discoverable by ordinary file inspection.

The convention should include:

- a source rule registry or stable implementation location;
- golden-case verifier files;
- generated expected outputs or visible tests that are tempting but wrong to
  edit;
- hidden verifier checks that enforce source behavior, not edited expected
  output;
- a Step C layout change that makes an old concrete path obsolete while the
  general workflow convention remains valid.

The task instructions must ask for ordinary product behavior. They must not say
"use memory", "call mew memory", or reveal hidden verifier paths.

## Step Specs

### Step A - Seed Convention

Purpose: force ordinary exploration of the local convention.

The agent receives a small feature request. To pass, it should discover:

- where behavior is actually implemented;
- how golden-case checks are run;
- that editing generated expected outputs is not a valid fix.

Verifier requirements:

- requested feature works;
- protected/generated expected-output files were not modified;
- reward JSON is written;
- known-bad solution that edits expected outputs fails.

### Step B - Recall Convention

Purpose: create a similar but non-identical task that can later benefit from a
resident memory card.

For fixture v0, no memory is injected. The step must still be independently
solvable by inspecting the workspace.

Verifier requirements:

- Step B feature works in a fresh Step B fixture;
- protected/generated expected-output files were not modified;
- reward JSON is written;
- known-bad solution fails for the intended shortcut.

### Step C - Stale Layout

Purpose: create the future stale-memory target without implementing memory
injection yet.

The Step C fixture changes one concrete path or verifier location while keeping
the general convention recognizable. In the future campaign, a stale card may
refer to the old path. For fixture v0, the verifier only needs to prove that
the current layout is the source of truth.

Verifier requirements:

- Step C feature works in the current layout;
- obsolete paths are not written;
- current verifier location is used by the oracle solution;
- reward JSON is written;
- known-bad solution that writes or depends on an obsolete path fails.

## Verifier Shape

Use deterministic local scripts only. No LLM judge and no network.

Each step verifier should:

- run from `/app`;
- call a step-local `/tests/test.sh` or equivalent;
- execute a small Python checker that imports or invokes the package;
- verify requested behavior against hidden expected cases;
- verify protected files were not changed when they should not be;
- write `/logs/verifier/reward.json`;
- avoid depending on prior step logs, prior step source edits, or mew state.

Recommended reward shape:

```json
{
  "reward": 1.0,
  "correctness": 1.0,
  "protected_files": 1.0
}
```

Step C may add:

```json
{
  "current_layout": 1.0,
  "obsolete_path_not_written": 1.0
}
```

## Validation Artifacts

Fixture v0 should produce local validation artifacts, but they do not need to
match the future campaign ledger schema.

Required artifacts:

- Harbor task validation output;
- oracle pass logs for all steps;
- known-bad fail logs for all steps;
- per-step verifier stdout/stderr;
- per-step `/logs/verifier/reward.json`;
- final source diff or fixture snapshot if useful for debugging.

Optional artifacts:

- a short fixture validation markdown report;
- command transcript for oracle and known-bad runs.

## Implementation Phases

### Phase 0 - Skeleton And Spec Check

Deliverables:

- create the task directory skeleton;
- add `task.toml`;
- add placeholder step instruction files;
- add deterministic Dockerfile or environment definition;
- confirm the task schema validates locally, or document the exact Harbor
  validation command that fails and why.

Close gate:

- no mew source changes;
- task directory exists with all three steps;
- `task.toml` is syntactically valid for the available Harbor version;
- no network dependency is required by the environment.

### Phase 1 - Deterministic Fixture And Oracle

Deliverables:

- add tiny Python package fixtures;
- add Step A/B/C setup scripts;
- add Step A/B/C verifier scripts;
- add oracle solution scripts;
- add known-bad solution scripts;
- add a fixture validation report.

Close gate:

- oracle solution passes all three steps;
- known-bad solution fails all intended protected-file or stale-path checks;
- verifier failures are understandable from stdout/stderr;
- all verifiers write reward JSON;
- no step depends on mew commands, resident memory, prior chat, or network;
- no mew core, runner, implement-lane, memory, or roadmap files were changed.

## Controller-Agent Constraints

If this design is implemented through `$orchestrate-build-review-controller`,
the task prompt should include these constraints:

```text
Implement only Phase 0 and Phase 1 of
docs/DESIGN_2026-05-20_M6_25_HARBOR_RESIDENT_MEMORY_TASK.md.

Do not implement campaign runner logic.
Do not change mew core source.
Do not change implement lane, memory, work-session, or runner code.
Do not edit ROADMAP.md or ROADMAP_STATUS.md.
Do not implement codex_cold, codex_resume, or resident-memory injection.

The accepted result is a deterministic Harbor task fixture where oracle
solutions pass and known-bad solutions fail for the intended reason.
```

## Future Work Boundary

After Phase 0-1 closes, the next design should be separate and may use:

- `docs/FUTURE_2026-05-20_M6_25_RESIDENT_MEMORY_CAMPAIGN.md`

That later work can define:

- fresh process and fresh conversation isolation;
- reset manifests;
- memory card injection;
- cold/resident/stale campaigns;
- `codex_cold` and `codex_resume`;
- M6.25 resident advantage ledger and report.

Do not pull those concerns back into this fixture-v0 task.

## References

- `docs/FUTURE_2026-05-20_M6_25_RESIDENT_MEMORY_CAMPAIGN.md`
- `docs/M6_25_RESIDENT_ADVANTAGE_PLAN_2026-05-20.md`
- `docs/SIDE_PROJECT_HARBOR_RESIDENT_MEMORY_BENCH.md`
- `docs/REVIEW_2026-05-20_TERMINAL_BENCH_RESIDENT_TASK_SEARCH.md`
- `docs/REVIEW_2026-05-20_RESIDENT_AGENT_BENCHMARK_FRAMEWORKS.md`
- `docs/terminal-bench-harbor-smoke.md`
- Harbor task structure: https://www.harborframework.com/docs/tasks
- Harbor multi-step tasks: https://www.harborframework.com/docs/tasks/multi-step
