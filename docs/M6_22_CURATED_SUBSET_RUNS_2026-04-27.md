# M6.22 Curated Subset Runs

Date: 2026-04-27 JST

Status: all selected task runs recorded; acceptance-check repair in progress.

## Scope

M6.22 uses the fixed curated subset in
`docs/data/terminal_bench_m6_22_curated_subset.json`.

Codex registry target for the full curated subset: **20/35 successes**.

This document records mew results as they are run through the same generic
`mew work --oneshot` Harbor command shape used by M6.20. It must not become a
Terminal-Bench-specific solver log.

## Results

| Task | Codex target | Mew result | Harbor errors | Runtime | Artifact |
|---|---:|---:|---:|---:|---|
| `filter-js-from-html` | 0/5 | 0/5 | 5 | 32m 24s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json` |
| `sanitize-git-repo` | 1/5 | 1/5 | 0 | 4m 41s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-sanitize-git-repo-5attempts-20260427-2245/result.json` |
| `gcode-to-text` | 2/5 | 0/5 | 1 | 15m 41s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json` |
| `overfull-hbox` | 3/5 | 1/5 | 0 | 14m 33s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-python-bootstrap-20260427-2315/result.json` |
| `extract-elf` | 4/5 | 5/5 | 0 | 4m 46s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-extract-elf-5attempts-python-bootstrap-20260427-2334/result.json` |

Current non-control subset total: **7/25**, below the 10/25 Codex target.

Full M6.22 curated subset total, including the M6.20 positive controls:
**17/35**, below the 20/35 Codex target.

Positive controls from M6.20:

- `cancel-async-tasks`: mew 5/5, Codex target 5/5
- `fix-code-vulnerability`: mew 5/5, Codex target 5/5

## `filter-js-from-html`

Command shape:

```sh
mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json
```

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 0
- `n_errors`: 5
- `exception_stats`: `VerifierTimeoutError` for all 5 trials
- `mean`: 0.0
- `pass@5`: 0.0
- started: `2026-04-27T22:07:22.268417`
- finished: `2026-04-27T22:39:46.498522`

Trial notes:

- Each trial produced a `mew-report.json`.
- All five work reports reached `stop_reason = finish`.
- The work reports show zero accepted writes for this task, so this run is best
  classified as a no-edit / verifier-timeout result, not a failed patch.
- The cached verifier runs Selenium/Chrome tests and timed out after 900s.
- Harbor's Docker cleanup failed afterward because the five task containers did
  not emit exit events when stopped. A manual `docker rm -f` attempt against the
  five Harbor container IDs returned the same daemon exit-event failure.

Classification:

- Against the frozen Codex target: no parity gap for this task, because Codex
  target is 0/5.
- Against implementation-lane usefulness: keep as cost/no-op evidence. It does
  not justify a core repair by itself because the reference target is also 0/5.
- Harness note: the stuck Docker containers are environmental cleanup debt, not
  mew core evidence unless it recurs on non-Selenium tasks.

## `sanitize-git-repo`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-sanitize-git-repo-5attempts-20260427-2245/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 5
- `n_errors`: 0
- `mean`: 0.2
- `pass@5`: 1.0
- reward `1.0`: `sanitize-git-repo__HdGFU9Y`
- reward `0.0`: `sanitize-git-repo__899ZFZb`,
  `sanitize-git-repo__C9TSKAr`, `sanitize-git-repo__gHAc6b3`,
  `sanitize-git-repo__MSD6ApM`
- started: `2026-04-27T22:45:20.586488`
- finished: `2026-04-27T22:50:02.510378`

Trial notes:

- All five trials produced `mew-report.json`.
- The successful trial reached `stop_reason = finish` after 17 steps and
  verifier passed all 3 hidden tests.
- Four failed trials reached `stop_reason = tool_failed` in 4-6 steps. One
  inspected failed report shows a generated multiline Python heredoc command
  failed with `No closing quotation`; its verifier still ran and found raw AWS
  credentials remained.

Classification:

- Against the frozen Codex target: no parity gap for this task, because mew
  matched the 1/5 Codex target.
- Keep the failed-trial shape as M6.23 evidence. If the same heredoc/shell
  quoting failure recurs on below-target tasks, classify through M6.18 as a
  candidate generic work-session shell-command repair.

## `gcode-to-text`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 5
- `n_errors`: 1
- `mean`: 0.0
- `pass@5`: 0.0
- reward `0.0`: all 5 trials
- exception: `AgentTimeoutError` for `gcode-to-text__TBsGjTk`
- started: `2026-04-27T22:52:31.104091`
- finished: `2026-04-27T23:08:12.821137`

Trial notes:

- Four trials produced `mew-report.json`.
- Stop reasons among reported trials:
  - `max_steps`: `gcode-to-text__BsmYCDb`, `gcode-to-text__wwcCb2v`
  - `finish`: `gcode-to-text__bvsCe3p`, `gcode-to-text__ks74VUm`
- The timeout trial did not produce a `mew-report.json` before Harbor's
  900-second agent timeout.
- Hidden verifier expected exact output `flag{gc0d3_iz_ch4LLenGiNg}`.
  Observed wrong outputs included `Embossed text`, `The quick brown fox jumps
  over the lazy dog`, and lowercase `the quick brown fox jumps over the lazy
  dog`.
- Inspected reports show extensive ad hoc G-code rendering and ASCII/OCR-style
  analysis, but no robust exact-answer confidence gate before writing
  `/app/out.txt`.

M6.18 classification:

- `failure_scope`: `structural`
- `confidence`: medium
- `diagnosis_signals`:
  - below frozen Codex target by 2 successes
  - repeated wrong finished answers despite verifier-compatible output file
  - two `max_steps` reports and one Harbor `AgentTimeoutError`
  - visual/geometric decoding task with no reliable artifact-grounded
    acceptance check
- `structural_reason`: `missing_visual_decode_artifact_grounding`
- secondary structural signal: `agent_wall_timeout_without_report`
- `recommended_route`: continue remaining M6.22 runs to see whether this is an
  isolated visual-task gap or part of a broader benchmark failure class; then
  choose a bounded generic repair. Candidate repair surfaces are visual artifact
  readback/OCR support, exact-answer confidence gates for "what does this file
  show" tasks, and wall-budget use in Harbor command templates so timed-out
  trials still leave reports.

No task-specific solver should be added for this task. The repair must improve
generic work-session behavior.

## `extract-elf`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-extract-elf-5attempts-python-bootstrap-20260427-2334/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 5
- `n_errors`: 0
- `mean`: 1.0
- `pass@5`: 1.0
- reward `1.0`: all 5 trials
- started: `2026-04-27T23:33:50.827285`
- finished: `2026-04-27T23:38:37.827171`

Trial notes:

- All five trials produced `mew-report.json`.
- All five work sessions exited `0` with `stop_reason = finish`.
- Step counts were 5, 5, 5, 6, and 10.

Classification:

- Against the frozen Codex target: no parity gap; mew exceeded the 4/5 Codex
  target with 5/5.
- Keep as positive evidence that the generic work-session path can solve
  arbitrary binary/file-inspection benchmark workspaces without a
  Terminal-Bench-specific solver.

## Gap Table

| Task | Gap vs Codex | M6.18 class | Selected route |
|---|---:|---|---|
| `gcode-to-text` | -2 | structural: `missing_visual_decode_artifact_grounding` | Defer task-specific visual/OCR work until M6.23; include in cohort ranking. |
| `overfull-hbox` | -2 | structural: `insufficient_acceptance_constraint_model` | Use as the first M6.22 repair candidate: add a generic acceptance-constraint ledger / final self-check before finish, then rerun `overfull-hbox`. |

M6.22 should not close yet: its Done-when requires at least one below-target
task to be repaired and rerun against the same subset evidence.

## Repair Attempt 1: Acceptance Checks

Commit: `29335c9` (`Add work acceptance checks`)

Change:

- Surface `task.acceptance_constraints` in the work prompt context.
- Ask the model to preserve `working_memory.acceptance_constraints` and
  `working_memory.acceptance_checks`.
- Require `action.acceptance_checks` before a `finish` with `task_done=true`.
- Block task-done finish when extracted stated constraints are unchecked.

Rerun artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-acceptance-checks-20260427-2349/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 5
- `n_errors`: 1
- exception: `AgentTimeoutError` for `overfull-hbox__S2pETMP`
- `mean`: 0.0
- `pass@5`: 0.0
- reward `0.0`: all 5 trials
- started: `2026-04-27T23:48:52.588140`
- finished: `2026-04-28T00:04:10.564154`

Delta:

- Baseline `overfull-hbox`: 1/5
- After first acceptance-check repair: 0/5
- Result: regressed.

M6.18 classification of the repair regression:

- `failure_scope`: structural
- `confidence`: high
- `structural_reason`: `repairable_constraint_blocker_terminal_wait`
- evidence:
  - four reported trials stopped with `stop_reason = wait`
  - repeated last-action reasons show unsafe or unsupported synonym-edit
    candidates were detected, but the work loop stopped instead of continuing
    to repair the candidate
  - the remaining trial hit `AgentTimeoutError`
- follow-up repair: convert repairable constraint/unsafe/unsupported `wait`
  actions into `remember` when `continue_after_remember` is enabled and the
  current run still has remaining steps; continue after acceptance-finish blocks
  caused by unchecked constraints.

## `overfull-hbox`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-python-bootstrap-20260427-2315/result.json`

Harness setup note:

- Two earlier attempts failed before mew ran because the task image did not
  include `python` or `python3`.
- The counted run bootstrapped Python generically in the Harbor install command:
  `apt-get install ... python3 python3-pip python3-venv` followed by
  `python3 -m pip install --break-system-packages -e /mew`.
- This is harness compatibility glue, not a Terminal-Bench-specific solver.

Observed result:

- `n_total_trials`: 5
- `n_trials`: 5
- `n_errors`: 0
- `mean`: 0.2
- `pass@5`: 1.0
- reward `1.0`: `overfull-hbox__E8y5Cdd`
- reward `0.0`: `overfull-hbox__Cq6XyMs`,
  `overfull-hbox__YUpmmJm`, `overfull-hbox__7WjQ3DR`,
  `overfull-hbox__mgoxXJo`
- started: `2026-04-27T23:15:37.013629`
- finished: `2026-04-27T23:30:10.847560`

Trial notes:

- All five trials produced `mew-report.json`.
- Stop reasons:
  - `finish`: `overfull-hbox__E8y5Cdd`,
    `overfull-hbox__YUpmmJm`, `overfull-hbox__mgoxXJo`
  - `tool_failed`: `overfull-hbox__Cq6XyMs`
  - `wait`: `overfull-hbox__7WjQ3DR`
- `overfull-hbox__E8y5Cdd` passed the hidden verifier: 4 tests passed.
- `overfull-hbox__7WjQ3DR` rejected its own candidate edit because it violated
  the synonym-only constraint, then stopped without a valid patch; the external
  verifier still saw the original overfull hboxes.
- `overfull-hbox__Cq6XyMs` reduced but did not eliminate all overfull hboxes and
  then hit the repeat-action guard after repeated identical compile attempts.
- `overfull-hbox__YUpmmJm` and `overfull-hbox__mgoxXJo` locally verified the
  LaTeX no-overfull condition, but the external verifier rejected the final
  file because edits were not limited to allowed `synonyms.txt` substitutions.

M6.18 classification:

- `failure_scope`: `structural`
- `confidence`: medium-high
- `diagnosis_signals`:
  - below frozen Codex target by 2 successes
  - two failures passed local task-specific checks but failed the external
    verifier's edit-constraint check
  - one failure recognized an invalid candidate but had no repair path before
    stopping
  - one failure looped on the same compile command until the repeat-action guard
    stopped it
- `structural_reason`: `insufficient_acceptance_constraint_model`
- secondary structural signal: `repeat_action_after_partial_repair`
- `recommended_route`: continue the final M6.22 selected task first, then choose
  a bounded generic repair across the gcode/overfull cohort. Candidate surfaces
  are stronger task-contract extraction, explicit acceptance-constraint ledgers,
  and a self-check that distinguishes "local compile condition passed" from
  "all stated edit constraints are satisfied".

No task-specific solver should be added for this task. The repair must improve
generic work-session behavior.

## Next Tasks

Commit and rerun the follow-up repair for
`repairable_constraint_blocker_terminal_wait`; M6.22 can close only after a
below-target task is repaired and rerun with recorded outcome.
