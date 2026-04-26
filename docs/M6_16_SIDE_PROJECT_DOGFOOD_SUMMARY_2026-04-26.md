# M6.16 Side-Project Dogfood Summary

Date: 2026-04-26

Source:

- `SIDE_PROJECT_ROADMAP.md`
- `SIDE_PROJECT_ROADMAP_STATUS.md`
- `./mew side-dogfood report --json`
- `experiments/mew-companion-log/.mew-dogfood/reports/*.json`

## Cohort

The first `mew-companion-log` side-project cohort reached the SP3 evidence
gate with five recorded attempts:

| Row | Task | Outcome | Failure Class | Rescue Edits |
|---:|---:|---|---|---:|
| 1 | 1 | `failed` | `side_project_write_scope_guard_rejected_experiments_paths` | 0 |
| 2 | 1 | `practical` | `readme_command_polish_after_successful_scaffold` | 0 |
| 3 | 2 | `clean` | `none_observed` | 0 |
| 4 | 3 | `clean` | `none_observed` | 0 |
| 5 | 4 | `practical` | `readme_cli_test_followup_after_dream_learning` | 0 |

Report metrics after row 5:

- `rows_total=5`
- `clean_or_practical=4`
- `success_rate=0.8`
- `failed=1`
- `structural_repairs_required=1`
- `rescue_edits_total=0`
- `first_edit_latency_avg=30.5`
- `read_turns_before_edit_avg=1.6`

## Observed Bottlenecks

1. Non-core write-root guard was too narrow.
   - Evidence: row 1, GitHub issue `#1`.
   - Resolution: handled as an M6.14 repair, then retried successfully.
   - M6.16 implication: preserve the core `src/mew/**` paired-test rule, but
     keep non-core allowed-write-root handling covered by regression tests.

2. Acceptance completeness lagged behind implementation.
   - Evidence: rows 2 and 5 were practical rather than clean because README
     usage and CLI proof/test coverage needed reviewer follow-up.
   - M6.16 implication: ordinary implementation tasks need a stronger closeout
     checklist that links task acceptance criteria to docs, CLI examples,
     output-file behavior, and focused tests before `finish`.

3. Verifier commands were necessary but not sufficient.
   - Evidence: the first dream/learning pass passed focused pytest with
     renderer snapshot coverage, but missed CLI stdout coverage and README
     Usage.
   - M6.16 implication: verifier discipline should include reviewer-visible
     proof coverage for user-facing modes, not only the configured pytest
     command.

4. Reviewer rejection recovery was healthy.
   - Evidence: both practical rows were repaired by mew follow-up sessions
     without Codex product rescue edits.
   - M6.16 implication: approval rejection is acceptable when retries are fast,
     scoped, and classified.

5. First-edit latency was acceptable for this cohort.
   - Evidence: average first-edit latency was `30.5s`, with average
     read-turns-before-edit `1.6`.
   - M6.16 implication: the next measured improvement should target acceptance
     completeness before latency.

## Recommended M6.16 First Slice

Start M6.16 with a bounded implementation closeout hardening slice:

- baseline symptom: mew can pass focused tests while missing user-facing
  acceptance artifacts such as README commands or CLI stdout proof
- expected improvement: fewer practical rows caused by reviewer follow-up for
  docs/CLI/test completeness
- narrow mechanism: add or strengthen reviewer-visible finish/closeout
  evidence that enumerates task acceptance criteria, touched user-facing
  surfaces, tests run, and any unverified mode
- focused proof: a fixture test or work-session replay showing that a task with
  a new CLI mode cannot close as clean unless the finish evidence accounts for
  the mode's README usage and CLI stdout/output proof
- non-goal: broad `work_loop.py` / `work_session.py` refactor

Structural failures should continue to route through M6.14. The write-root
guard blocker from row 1 is closed evidence, not an active SP5 blocker.
