# Mew Side Project Implementation Status

Last updated: 2026-04-26

This file is the compact operational dashboard for side-project implementation
dogfood. It is intentionally separate from `ROADMAP_STATUS.md`; the main
roadmap consumes side-project evidence through M6.13.2 and M6.16.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| SP0 Dogfood Harness Ready | `done` | Roadmap, status, `side-pj-mew-impl` skill, and M6.13.2 telemetry CLI are ready. |
| SP1 mew-companion-log Scaffold | `done` | Scaffold landed after issue #1 repair; mew-authored source, fixture, README, and tests pass. |
| SP2 Journal and Dream Reports | `done` | Morning, evening, and dream/learning fixture-driven outputs landed with focused tests. |
| SP3 Implementation-Lane Evidence Cohort | `done` | Five side-project attempts are recorded; failures are classified and rescue edits remain zero. |
| SP4 Optional Research Digest Slice | `done` | Static fixture research digest landed with deterministic ranking, README usage, stdout, and output-file tests. |
| SP5 Feed M6.16 | `done` | The side-project cohort is summarized into a measured M6.16 hardening recommendation and now includes the SP4 extension row. |

## Active Focus

Active side-project focus: **current roadmap complete**.

Current target:

- keep the `mew-companion-log` cohort as closed evidence for M6.16
- choose the next side-project roadmap extension before starting another
  implementation slice
- route the already-fixed structural write-scope blocker as closed issue `#1`
  evidence, not an active side-project blocker
- preserve the current operating model for any future side-project cohort:
  current-repo `./mew`, side-project target directory, Codex as
  operator/reviewer/verifier, and rescue edits explicitly tracked

## Evidence

- Core M6.13.2 telemetry CLI exists:
  `mew side-dogfood template`, `mew side-dogfood append`, and
  `mew side-dogfood report`.
- Default ledger:
  `proof-artifacts/side_project_dogfood_ledger.jsonl`.
- `./mew side-dogfood report --json` returned a valid telemetry report with
  six `mew-companion-log` rows on 2026-04-26: `rows_total=6`, one `failed`,
  three `practical`, two `clean`, `success_rate=0.833`,
  `structural_repairs_required=1`, and `rescue_edits_total=0`.
- `side-pj-mew-impl` skill exists at
  `.codex/skills/side-pj-mew-impl/SKILL.md`.
- First side project selected: `mew-companion-log`.
- First side project rationale: medium-sized, local-first, fixture-testable,
  product-relevant, and unlikely to hide implementation-lane failures behind
  GUI/platform friction.
- Task `#1` / session `#1` first attempted the SP1 scaffold with Codex CLI as
  `operator` and mew as first implementer. After inspecting the empty target
  directory, mew twice stopped before writes with
  `write batch is limited to write/edit tools under tests/** and src/mew/**`
  `with at least one of each`, including a second attempt with
  `--model gpt-5.5` and explicit side-project scope steering.
- Failed-attempt local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/1-scaffold-write-scope-guard-blocked.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `1`;
  outcome `failed`, failure class
  `side_project_write_scope_guard_rejected_experiments_paths`.
- Problem issue closed:
  `https://github.com/mkXultra/mew/issues/1`.
- After issue `#1` closed and `origin/main` was pulled, task `#1` retried with
  `--model gpt-5.5`. Mew authored:
  `experiments/mew-companion-log/companion_log.py`,
  `fixtures/sample_session.json`, `tests/test_companion_log.py`, and
  `README.md`.
- Reviewer follow-ups were required only for README command accuracy:
  the stable verifier must include `--no-testmon`, and usage examples must use
  `UV_CACHE_DIR=.uv-cache uv run python` because plain `python` is unavailable
  in this environment. Mew authored both follow-up edits.
- Successful-attempt local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/1-scaffold-practical-after-write-scope-repair.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `2`;
  outcome `practical`, failure class
  `readme_command_polish_after_successful_scaffold`.
- Final verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `4 passed`.
- README usage commands were manually verified with
  `UV_CACHE_DIR=.uv-cache uv run python ...` for stdout and `--output`.
- Task `#2` / session `#4` added the first SP2 surface with Codex CLI as
  `operator` and mew as first implementer. Mew authored the fixture-driven
  `--mode morning-journal` renderer, updated fixture data, README usage, and
  snapshot-style tests under `experiments/mew-companion-log`.
- Morning journal local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/2-morning-journal-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `3`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- Morning journal verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `6 passed`. The default report CLI, morning journal stdout, and
  morning journal `--output` path were also verified.
- Task `#3` / session `#5` added the second SP2 surface with Codex CLI as
  `operator` and mew as first implementer. Mew authored the fixture-driven
  `--mode evening-journal` renderer, updated fixture data, README usage, and
  snapshot-style tests under `experiments/mew-companion-log`.
- Evening journal local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/3-evening-journal-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `4`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- Evening journal verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `8 passed`. The default report CLI, morning journal stdout, evening
  journal stdout, and evening journal `--output` path were also verified.
- Task `#4` / sessions `#6` and `#7` added the final SP2 dream/learning
  surface with Codex CLI as `operator` and mew as first implementer. Session
  `#6` authored the fixture-driven `--mode dream-learning` renderer, fixture
  data, README fixture description, and snapshot-style test under
  `experiments/mew-companion-log`.
- Reviewer follow-up was required because the first pass lacked a README Usage
  command for `--mode dream-learning` and a focused CLI stdout test for that
  mode. Session `#7` authored both follow-up edits.
- Dream/learning local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/4-dream-learning-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `5`;
  outcome `practical`, failure class
  `readme_cli_test_followup_after_dream_learning`, `rescue_edits=0`.
- Dream/learning verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `10 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, dream/learning `--output`
  path, and `git diff --check` were also verified.
- SP5 summary artifact:
  `docs/M6_16_SIDE_PROJECT_DOGFOOD_SUMMARY_2026-04-26.md`.
- SP5 conclusion: the first M6.16 slice should target implementation closeout
  completeness because practical rows were caused by missing README/CLI/test
  acceptance proof, while first-edit latency was acceptable and structural
  failure already routed through M6.14.
- Task `#5` / session `#8` added the optional SP4 static research digest with
  Codex CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode research-digest` renderer, deterministic ranking over
  static fixture entries, README usage and output-file notes, snapshot test,
  CLI stdout test, output-file test, and fixture shape assertions under
  `experiments/mew-companion-log`.
- A pre-edit operator follow-up was required because the first write batch
  proposed multiple edits to `README.md`; mew collapsed same-file hunks and
  authored the final patch without Codex product-code rescue.
- Research digest local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/5-research-digest-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `6`;
  outcome `practical`, failure class
  `same_file_write_batch_guard_followup_before_research_digest`,
  `rescue_edits=0`.
- Research digest verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `13 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, research digest stdout,
  research digest `--output` path, and `git diff --check` were also verified.

## Missing Proof

- SP1, SP2, SP3, SP4, and SP5 are closed for the current
  `mew-companion-log` roadmap.
- No open milestone remains in `SIDE_PROJECT_ROADMAP.md`; continuing side-pj
  work now needs a roadmap extension or a second isolated side project.

## Next Action

Choose the next side-project extension:

1. either extend `mew-companion-log` with a new SP6 milestone, such as
   multi-fixture digest bundles or a lightweight package/entrypoint polish
2. or start a second isolated side project with the same current-repo `./mew`
   operator model
3. keep recording every bounded attempt in the side-project dogfood ledger
   with rescue edits and failure classes explicit

## Non-Goals

- do not implement the side project before SP0 is done
- do not treat Codex CLI implementation as mew-first autonomy credit
- do treat Codex CLI operating mew as `operator`, not `implementer`
- do not make GitHub issues for normal progress; create one `[side-pj]` issue
  only when mew cannot implement after bounded operator steering or a real
  problem needs main-side action
- do not change core mew unless the side project exposes a classified M6.14
  repair blocker or a later M6.16 measured hardening slice
- do not start GUI, Tauri, screen capture, TTS, or network-heavy side projects
  before the implementation-lane evidence cohort exists
