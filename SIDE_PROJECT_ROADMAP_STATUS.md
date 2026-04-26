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
| SP6 Mew State Companion Export | `done` | State-brief mode landed clean: static mew-state-like fixture, README usage, stdout/output-file behavior, and focused tests are in place without live `.mew` access. |
| SP7 Multi-Fixture Companion Bundles | `done` | Bundle mode landed practical: static manifest, deterministic grouping/order, missing-fixture behavior, README usage, stdout/output-file proof, and focused tests are in place. |
| SP8 Multi-Day Companion Archive | `done` | Archive-index mode landed practical: static multi-day fixture, day/surface/next-action grouping, empty-day behavior, README usage, stdout/output-file proof, and focused tests are in place. |
| SP9 Issue and Dogfood Ledger Digest | `done` | Dogfood-digest mode landed practical: static dogfood rows, `[side-pj]` issue summaries, outcome/failure-class/rescue-edits grouping, README usage, stdout/output-file proof, and focused tests are in place. |
| SP10 Companion Export Contract | `done` | Export contract landed practical: local schema examples, documented markdown surfaces for every mode, README pointer, and all-mode output-file compatibility tests are in place. |
| SP11 Second Side-Project Gate | `done` | Gate landed practical: the recommendation is to pause new side-project work and feed SP6-SP10 evidence into core M6.16/M9/M11 before starting a second isolated side project. |
| SP12 mew-ghost macOS Shell Scaffold | `done` | Scaffold landed practical: isolated `experiments/mew-ghost` shell, permission-safe macOS probe contract, deterministic HTML/state rendering, dry-run `mew chat`/`mew code` intents, README usage, local report, and focused tests are in place. |
| SP13 mew-ghost Live macOS Probe Integration | `done` | Live probe integration landed practical: explicit `--live-active-window` opt-in, injectable `osascript` runner/provider, structured fallbacks, README usage, output proof, and hermetic tests are in place. |
| SP14 mew-ghost Presence Loop | `done` | Presence loop landed practical: deterministic idle/attentive/coding/waiting/blocked classification, bounded refresh snapshots, README refresh contract, output proof, and focused tests are in place. |
| SP15 mew-ghost Launcher Contract | `done` | Launcher contract landed practical: explicit `mew chat`/`mew code` commands, dry-run default state, `--execute-launchers` opt-in execution gate, injected-runner tests, README usage, local report, and focused proof are in place. |
| SP16 mew-ghost Watch Mode | `planned` | Next slice: add bounded CLI/HTML watch mode so `idle`/`attentive`/`coding`/`waiting`/`blocked` presence can update continuously without background monitoring or implicit launcher execution. |

## Active Focus

Active side-project focus: **SP16 mew-ghost Watch Mode**.

Current target:

- keep `mew-ghost` isolated under `experiments/mew-ghost`
- `mew chat` and `mew code` are represented as explicit command arrays
- launcher state remains dry-run by default with `side_effects: "none"` and
  `execution.status: "dry_run"`
- direct launcher execution is gated behind explicit `--execute-launchers`;
  automated tests use an injected runner and do not spawn real `mew`
- add `--watch` style behavior for CLI and HTML so presence can update
  continuously until interrupted
- include a bounded watch path such as `--watch-count` so tests do not rely on
  infinite loops
- keep HTML watch output safe for browser display, either by atomic rewrite
  plus page refresh metadata or an equivalent local refresh contract
- live macOS probing remains explicit through `--live-active-window`
- preserve the bounded deterministic presence loop without background
  monitoring or hidden capture
- preserve structured fallback for missing `osascript`, non-macOS platforms,
  permission denial, empty probe results, malformed output, and timeouts
- focused verifier remains:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
- keep `mew-companion-log` stable as the local fixture-tested companion surface
  set for future product planning and contract checks
- route the already-fixed structural write-scope blocker as closed issue `#1`
  evidence, not an active side-project blocker
- route the repeated stale failed-approval cleanup pattern as open issue `#10`
  evidence for M6.16 implementation-lane hardening
- route the SP15 report-schema closeout gap as open issue `#11` evidence for
  M6.16 implementation-lane hardening
- preserve the current operating model for any future side-project cohort:
  current-repo `./mew`, side-project target directory, Codex as
  operator/reviewer/verifier, and rescue edits explicitly tracked

## Evidence

- Core M6.13.2 telemetry CLI exists:
  `mew side-dogfood template`, `mew side-dogfood append`, and
  `mew side-dogfood report`.
- Default ledger:
  `proof-artifacts/side_project_dogfood_ledger.jsonl`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP15 on 2026-04-26: `rows_total=16`, one `failed`, twelve `practical`,
  three `clean`, `success_rate=0.938`, `structural_repairs_required=1`, and
  `rescue_edits_total=0`.
- `./mew side-dogfood report --json` returned a valid telemetry report with
  twelve `mew-companion-log` rows on 2026-04-26: `rows_total=12`, one `failed`,
  eight `practical`, three `clean`, `success_rate=0.917`,
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
- Task `#6` / session `#9` added the SP6 mew state companion export with Codex
  CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode state-brief` renderer, static mew-state-like fixture,
  README usage/output-file examples, snapshot test, CLI stdout test,
  output-file test, and fixture shape assertions under
  `experiments/mew-companion-log`.
- Bundle local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/6-state-brief-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `7`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- State brief verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `17 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, research digest stdout, state
  brief stdout, state brief `--output` path, `git diff --check`, and a scoped
  search for `src/mew` / live `.mew` coupling were also verified.
- Task `#7` / session `#10` added the SP7 multi-fixture companion bundle with
  Codex CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode bundle` renderer, static bundle manifest, README
  usage/output-file examples, snapshot test, CLI stdout test, output-file test,
  ordering/grouping assertions, missing-fixture behavior coverage, and fixture
  shape assertions under `experiments/mew-companion-log`.
- State brief local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/7-bundle-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `8`;
  outcome `practical`, failure class
  `same_file_write_batch_retry_timeout_after_bundle_verifier_failure`,
  `rescue_edits=0`.
- Bundle verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `22 passed`. Bundle stdout, bundle `--output`, default report
  stdout, state brief stdout, `git diff --check`, and a scoped no-core/no-live
  coupling search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/4`.
- Task `#8` / sessions `#11` and `#12` added the SP8 multi-day companion
  archive index with Codex CLI as `operator` and mew as first implementer.
  Session `#11` reached the right archive-index implementation shape but the
  first verifier failed because a new stdout ordering assertion compared
  headings across different day sections. Mew chose a remember/checkpoint under
  high pressure, so Codex restarted a fresh mew session with the repair plan.
  Session `#12` authored the final `--mode archive-index` renderer, static
  archive fixture, README usage/output-file examples, snapshot test, CLI stdout
  test, output-file test, empty-day behavior coverage, and fixture shape
  assertions under `experiments/mew-companion-log`.
- Archive index local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/8-archive-index-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `9`;
  outcome `practical`, failure class
  `archive_index_cross_day_ordering_retry_after_verifier_failure`,
  `rescue_edits=0`.
- Archive index verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `26 passed`. Archive-index stdout, archive-index `--output`, bundle
  stdout, `git diff --check`, and a scoped no-core/no-live/no-crawl coupling
  search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/5`.
- Task `#9` / sessions `#13` through `#17` added the SP9 issue and dogfood
  ledger digest with Codex CLI as `operator` and mew as first implementer.
  Session `#13` stopped before product edits after a duplicated-context edit
  failure and same-file write-batch wait, so Codex restarted fresh. Session
  `#14` authored the final `--mode dogfood-digest` renderer, static dogfood
  digest fixture, README usage/output-file examples, failure-class grouping
  tests, issue-link rendering tests, stdout/output-file tests, and fixture
  shape assertions under `experiments/mew-companion-log`. Reviewer follow-up in
  sessions `#15` through `#17` was required to preserve canonical
  `rescue_edits` semantics and align static issue summaries with real side-pj
  issue `#4` and `#5`.
- Dogfood digest local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/9-dogfood-digest-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `10`;
  outcome `practical`, failure class
  `dogfood_digest_ledger_semantics_repair_after_write_batch_retries`,
  `rescue_edits=0`.
- Dogfood digest verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `30 passed`. Dogfood-digest stdout, dogfood-digest `--output`,
  `git diff --check`, and a scoped no-core/no-live/no-network/no-crawl coupling
  search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/6`.
- Task `#10` / sessions `#18` and `#19` added the SP10 companion export
  contract with Codex CLI as `operator` and mew as first implementer. Session
  `#18` authored `experiments/mew-companion-log/CONTRACT.md`, a README pointer,
  and an all-mode output-file compatibility test proving every documented mode
  renders and writes a markdown output file from a local fixture. Reviewer
  follow-up in session `#19` was required because the first contract documented
  the `dogfood-digest` heading as `# Companion Dogfood Digest:` while the
  renderer emits `# Dogfood Digest:`.
- Export contract local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/10-export-contract-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `11`;
  outcome `practical`, failure class
  `contract_heading_mismatch_reviewer_followup`, `rescue_edits=0`.
- Export contract verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `31 passed`. `git diff --check` and a scoped no-core/no-live/no-network/no-crawl
  coupling search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/7`.
- Task `#11` / sessions `#20` through `#22` added the SP11 second side-project
  gate recommendation with Codex CLI as `operator` and mew as first implementer.
  Mew authored `experiments/mew-companion-log/SECOND_SIDE_PROJECT_GATE.md` and
  a local SP11 report. The gate compares SP6-SP10 ledger rows `7` through `11`,
  repeated failure classes, `rescue_edits=0`, first-edit latency, and issue
  queue outcomes. Reviewer follow-up was required to include SP7 issue `#4` in
  the issue queue comparison and to correct local report proof paths before
  ledger append.
- Second side-project gate local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/11-second-side-project-gate-recommendation.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `12`;
  outcome `practical`, failure class
  `second_side_project_gate_recommends_core_hardening_before_new_cohort`,
  `rescue_edits=0`.
- Gate recommendation:
  pause new side-project implementation and feed the first side-project cohort
  into core M6.16/M9/M11 before starting a second isolated side project.
- Gate verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `31 passed`. `git diff --check` was also verified.
- Task `#12` / sessions `#23` through `#25` opened the second side-project arc
  and added the SP12 mew-ghost macOS shell scaffold with Codex CLI as
  `operator` and mew as first implementer. Operator bookkeeping first opened
  SP12-SP15 in `SIDE_PROJECT_ROADMAP.md` and this status file. Session `#23`
  exposed setup friction because `experiments/mew-ghost` did not exist, then a
  model timeout; operator created the empty target directory and restarted with
  narrower guidance. Session `#24` authored the four-file scaffold under
  `experiments/mew-ghost`: README, `ghost.py`, static fixture, and focused
  tests. Mew repaired one focused verifier failure caused by a source-string
  assertion and reached `7 passed`. Session `#25` completed reviewer follow-up
  by changing README examples to
  `UV_CACHE_DIR=.uv-cache uv run python ...` and adding README usage coverage.
- mew-ghost SP12 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/12-macos-shell-scaffold-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `13`;
  outcome `practical`, failure class
  `mew_ghost_scaffold_verifier_repair_and_readme_command_followup`,
  `rescue_edits=0`.
- mew-ghost SP12 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `8 passed`. The state CLI, HTML `--output` path, rendered HTML
  content check, and `git diff --check` were also verified.
- Task `#13` / session `#26` added the SP13 explicit live macOS probe
  integration with Codex CLI as `operator` and mew as first implementer. The
  first resume attempt hit `HTTP 401 token_expired` with the default local
  auth before product edits; retrying with `--auth /Users/mk/.codex/auth.json`
  allowed the same session to continue. Mew authored the opt-in
  `--live-active-window` path, injectable `osascript` runner/provider,
  structured fallback reasons, README usage, and hermetic tests under
  `experiments/mew-ghost`.
- The first SP13 write batch failed the focused verifier because one stale test
  assertion still expected `mew-ghost.sp12.v1`; mew repaired in the same
  session and the corrected batch passed. Operator rejected three stale
  approvals from the failed batch after the corrected batch had already applied.
- mew-ghost SP13 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/13-live-macos-probe-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `14`;
  outcome `practical`, failure class
  `stale_failed_approval_cleanup_after_live_probe_verifier_repair`,
  `rescue_edits=0`.
- mew-ghost SP13 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `13 passed`. Default state CLI, explicit live opt-in state CLI,
  HTML `--output`, state `--output`, rendered HTML content checks,
  `git diff --check`, and scoped no-core/no-live-state coupling searches were
  also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/10`.
- Task `#14` / session `#27` added the SP14 bounded presence loop with Codex
  CLI as `operator` and mew as first implementer. Mew authored deterministic
  presence classification for `idle`, `attentive`, `coding`, `waiting`, and
  `blocked`; bounded refresh snapshots; the rendered HTML presence section;
  README refresh-contract documentation; CLI `--refresh-count`; and hermetic
  tests under `experiments/mew-ghost`.
- Session `#27` first hit an invalid JSON model response before edits, then a
  source-only batch whose verifier failed because tests and README were not
  updated. After operator rejection, mew produced a complete source/tests/README
  batch; the first complete batch failed one expectation for Safari notes
  classification, then mew repaired it in the same session.
- Stale failed approvals remained after the corrected batch passed, repeating
  issue `#10`; the issue was updated with SP14 evidence.
- mew-ghost SP14 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/14-presence-loop-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `15`;
  outcome `practical`, failure class
  `presence_loop_json_parse_source_only_and_stale_approval_repair`,
  `rescue_edits=0`.
- mew-ghost SP14 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `15 passed`. Default state CLI with refresh count, explicit live
  opt-in state CLI, HTML `--output`, state `--output`, rendered HTML content
  checks, `git diff --check`, and scoped no-core/no-live-state coupling
  searches were also verified.
- Task `#15` / sessions `#28` through `#30` added the SP15 launcher contract
  with Codex CLI as `operator` and mew as first implementer. Mew authored
  explicit `mew chat` and `mew code` command intents, default dry-run execution
  metadata, the `--execute-launchers` opt-in gate, injected-runner tests that do
  not spawn real `mew`, README usage, and the SP15 local report under
  `experiments/mew-ghost`.
- Session `#28` produced the first launcher-contract batch, but verifier
  failure left stale pending approvals after SP14 schema expectations were not
  fully updated. Operator rejected the stale failed approvals and updated issue
  `#10` with SP15 recurrence evidence. Session `#29` completed the product
  implementation and verifier pass. Session `#30` rewrote only the local
  report into canonical side-dogfood schema after operator review found the
  first report was not appendable.
- mew-ghost SP15 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/15-launcher-contract-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `16`;
  outcome `practical`, failure class
  `launcher_contract_retry_and_report_schema_followup`, `rescue_edits=0`.
- mew-ghost SP15 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `16 passed`. `git diff --check`, dry-run state output, HTML output,
  rendered HTML content checks, explicit live-probe fallback output, and
  temporary side-dogfood ledger append validation were also verified. Real
  `--execute-launchers` execution remains intentionally outside automated
  verification and requires local operator opt-in.

## Missing Proof

- SP1 through SP11 are closed for the first `mew-companion-log` cohort.
- SP12 is closed for the second `mew-ghost` cohort.
- SP13 is closed for the second `mew-ghost` cohort.
- SP14 is closed for the second `mew-ghost` cohort.
- SP15 is closed for the second `mew-ghost` cohort.
- SP16 has not started; continuous CLI/HTML watch behavior is not yet defined.
- Real local execution of `--execute-launchers` is intentionally unverified by
  automation because it would spawn `mew chat` and `mew code`; the opt-in gate
  is covered by injected-runner tests and dry-run output proof.
- Open `[side-pj]` implementation-lane polish issues remain M6.16 input and do
  not block the isolated `mew-ghost` scaffold unless the same failure repeats.

## Next Action

Start SP16 with mew as first implementer:

1. create a coding task for `mew-ghost` SP16
2. run repo-root `./mew work` from `/Users/mk/dev/personal-pj/mew_side_pj`
   with `--model gpt-5.5`
3. allow writes only under `experiments/mew-ghost`
4. add bounded CLI and HTML watch mode while preserving live probe opt-in and
   dry-run launcher safety
5. verify with
   `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
6. write a canonical local side-dogfood report and append it to the ledger

## Non-Goals

- do not implement outside `experiments/mew-ghost` for the `mew-ghost` arc
- do not treat Codex CLI implementation as mew-first autonomy credit
- do treat Codex CLI operating mew as `operator`, not `implementer`
- do not make GitHub issues for normal progress; create one `[side-pj]` issue
  only when mew cannot implement after bounded operator steering or a real
  problem needs main-side action, or when a reusable M6.16 polish finding is
  visible in the ledger
- do not change core mew unless the side project exposes a classified M6.14
  repair blocker or a later M6.16 measured hardening slice
- do not read live `.mew` state, import `src/mew/**`, use screen capture,
  keystroke monitoring, TTS, network-heavy services, background monitoring, or
  native packaging in the `mew-ghost` arc
