# M6.22 Curated Subset Runs

Date: 2026-04-27 JST

Status: first three selected task runs recorded.

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

Current counted subset total: **1/15**, below the 3/15 Codex target for the
three counted M6.22 task runs so far.

Positive controls from M6.20 remain available but are not re-counted in this
document until the five not-yet-run M6.22 tasks finish:

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

## Next Tasks

Run the remaining non-control M6.22 tasks:

1. `overfull-hbox` (Codex target 3/5)
2. `extract-elf` (Codex target 4/5)

If any task lands below the Codex target, classify it through M6.18 before
choosing a repair.
