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
| SP2 Journal and Dream Reports | `not_started` | Companion report surfaces are next. |
| SP3 Implementation-Lane Evidence Cohort | `not_started` | Needs at least five recorded side-project attempts. |
| SP4 Optional Research Digest Slice | `not_started` | Deferred until SP1-SP3 produce useful evidence. |
| SP5 Feed M6.16 | `not_started` | Waits for enough side-project telemetry to name core implementation-lane bottlenecks. |

## Active Focus

Active side-project focus: **SP2 Journal and Dream Reports**.

Current target:

- keep side-project implementation mew-first
- use side-project Codex CLI as the `operator` that runs current-repo `./mew`
  commands against the side-project target directory and makes local decisions
- use Codex/Codex CLI as reviewer, comparator, or verifier when it is checking
  mew's work
- side-project Codex writes normal completion reports to a local report outbox;
  current-repo Codex polls those reports and records accepted rows with
  `./mew side-dogfood append`
- GitHub issues are only for problems: one real problem per issue, `[side-pj]`
  title prefix, open/closed state only, no label workflow in v0
- treat `proof-artifacts/side_project_dogfood_ledger.jsonl` as the primary
  evidence source for M6.16; reply/chat logs are auxiliary
- continue `mew-companion-log`, not a GUI or OS-permission-heavy project

## Evidence

- Core M6.13.2 telemetry CLI exists:
  `mew side-dogfood template`, `mew side-dogfood append`, and
  `mew side-dogfood report`.
- Default ledger:
  `proof-artifacts/side_project_dogfood_ledger.jsonl`.
- `./mew side-dogfood report --json` returned a valid telemetry report with
  two `mew-companion-log` rows on 2026-04-26: `rows_total=2`, one `failed`,
  one `practical`, `structural_repairs_required=1`, and
  `rescue_edits_total=0`.
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

## Missing Proof

- SP2 journal/dream report surfaces do not exist yet.
- SP3 still needs at least five recorded side-project attempts.

## Next Action

Start SP2:

1. define one bounded journal or dream report task under
   `experiments/mew-companion-log`
2. run current-repo `./mew` mew-first with `--model gpt-5.5`
3. keep Codex CLI as `operator` / `reviewer` / `verifier`, not product-code
   implementer
4. append a new side-dogfood report row after verification

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
