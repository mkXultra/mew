# Harbor Resident Golden Convention Recall Fixture Validation

Date: 2026-05-20

Scope validated: Phase 0 and Phase 1 fixture-v0 only. No mew source, runner,
implement-lane, memory, work-session, campaign, roadmap, or resident-memory
injection code is part of this proof.

## Harbor Schema And Structure Check

Command:

```sh
/Users/mk/.local/share/uv/tools/harbor/bin/python - <<'PY'
from pathlib import Path
from harbor.models.task.task import Task
path = Path('benchmarks/harbor/resident-golden-convention-recall')
task = Task(path)
print(task.name)
print(task.config.schema_version)
print([step.name for step in task.config.steps or []])
print(task.config.environment.workdir)
print(task.config.environment.allow_internet)
PY
```

Outcome:

```text
mew/resident-golden-convention-recall
1.1
['seed-convention', 'recall-convention', 'stale-memory']
/app
False
```

The installed Harbor CLI has no local `harbor task check` schema validator:

```sh
harbor task check benchmarks/harbor/resident-golden-convention-recall
```

Outcome:

```text
Error: 'harbor tasks check' has been removed. Use 'harbor check <task-dir>' instead.
```

`harbor check <task-dir>` is the LLM quality checker in Harbor 0.5.0, not a
deterministic local schema validation command, so the fixture proof uses the
local Harbor `Task(...)` loader above.

## Host Fixture Validation

Command:

```sh
benchmarks/harbor/resident-golden-convention-recall/proof/run_fixture_validation.sh
```

Outcome:

```text
fixture validation passed; logs in /Users/mk/dev/personal-pj/mew/benchmarks/harbor/resident-golden-convention-recall/proof/validation-output
```

Validated cases:

| Step | Solution | Expected | Actual |
| --- | --- | --- | --- |
| seed-convention | oracle | pass | pass |
| seed-convention | known-bad | fail protected generated output | fail protected generated output |
| recall-convention | oracle | pass | pass |
| recall-convention | known-bad | fail protected generated output | fail protected generated output |
| stale-memory | oracle | pass | pass |
| stale-memory | known-bad | fail obsolete path | fail obsolete source path |

All six verifier runs wrote Harbor-facing `logs/verifier/reward.json` with
exactly one key, `reward`, under their validation case directory. Detailed
diagnostic metrics are written separately to
`logs/verifier/resident-memory-metrics.json`.

Known-bad failure excerpts:

```text
seed-convention: VERIFIER_FAILURE: protected generated expected-output file changed: generated/expected_totals.json ...
recall-convention: VERIFIER_FAILURE: protected generated expected-output file changed: generated/expected_delivery.json ...
stale-memory: VERIFIER_FAILURE: obsolete source path was written: src/golden_convention/legacy_layout
```

Oracle reward JSON summaries:

```text
seed-convention: {"reward": 1.0}
recall-convention: {"reward": 1.0}
stale-memory: {"reward": 1.0}
```

Oracle resident-memory metrics summaries:

```text
seed-convention: {"correctness": 1.0, "protected_files": 1.0}
recall-convention: {"correctness": 1.0, "protected_files": 1.0}
stale-memory: {"correctness": 1.0, "protected_files": 1.0, "current_layout": 1.0, "obsolete_path_not_written": 1.0}
```

## Direct Harbor Oracle Smoke

Command:

```sh
harbor run --path benchmarks/harbor/resident-golden-convention-recall --agent oracle -k 1 -n 1 --jobs-dir tmp/harbor-resident-oracle-smoke-fix --no-force-build --delete -y
```

Outcome:

```text
Trials: 1
Exceptions: 0
Mean: 1.000
Reward: 1.0 count 1
Results written to tmp/harbor-resident-oracle-smoke-fix/2026-05-20__16-51-50/result.json
```
