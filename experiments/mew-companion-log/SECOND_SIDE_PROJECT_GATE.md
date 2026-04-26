# SP11 Second Side-Project Gate

Date: 2026-04-26

## Recommendation

**Pause new side-project implementation and use the `mew-companion-log` evidence for core M6.16/M9/M11 work before starting a second isolated side project.**

The first side project has produced enough dogfood evidence for the current roadmap gate. SP6-SP10 show that mew can keep landing bounded, fixture-driven work under `experiments/mew-companion-log` without Codex product-code rescue, but they also show repeated implementation-lane friction that is more valuable as core hardening input than as another side-project cohort right now.

This recommendation does **not** begin a second side-project implementation.

## Evidence Window

This gate uses the static local SP6-SP10 evidence from `proof-artifacts/side_project_dogfood_ledger.jsonl` rows `7` through `11` and the local status notes in `SIDE_PROJECT_ROADMAP_STATUS.md`.

| Ledger row | Task | Outcome | Failure class | First-edit latency | Rescue edits | Issue outcome |
|---|---:|---|---|---:|---:|---|
| 7 | SP6 state brief | `clean` | `none_observed` | 51.0 | 0 | No new issue needed. |
| 8 | SP7 bundle | `practical` | `same_file_write_batch_retry_timeout_after_bundle_verifier_failure` | 70.0 | 0 | Reusable polish issue #4 opened. |
| 9 | SP8 archive index | `practical` | `archive_index_cross_day_ordering_retry_after_verifier_failure` | 75.0 | 0 | Reusable polish issue #5 opened. |
| 10 | SP9 dogfood digest | `practical` | `dogfood_digest_ledger_semantics_repair_after_write_batch_retries` | 75.0 | 0 | Reusable polish issue #6 opened. |
| 11 | SP10 export contract | `practical` | `contract_heading_mismatch_reviewer_followup` | 100.0 | 0 | Reusable polish issue #7 opened. |

## Comparison

### Repeated failure classes

SP6 was clean, but SP7-SP10 repeatedly needed verifier, reviewer, or session-management follow-up:

- SP7 exposed same-file write-batch ergonomics and timeout/session-pressure friction after a verifier failure.
- SP8 exposed verifier assertion quality: an ordering assertion compared headings across different day sections.
- SP9 exposed ledger-semantics and issue-summary precision problems after write-batch retries.
- SP10 exposed a contract/reality mismatch for the documented `dogfood-digest` heading.

These are not signs that the side project is blocked. They are signs that the first side-project cohort has reached the point where the marginal value is in core workflow hardening and reviewer-contract polish.

### Rescue edits

All five rows report `rescue_edits=0`. Codex acted as operator, reviewer, and verifier rather than product-code implementer. That preserves the central dogfood signal: mew remained the first implementer across the SP6-SP10 continuation arc.

### First-edit latency

First-edit latency increased across the arc: `51.0`, `70.0`, `75.0`, `75.0`, and `100.0`. Some of this reflects increasing task complexity, but the trend also matches the recurring need for more inspection, schema alignment, and contract verification before safe edits.

The gate conclusion is therefore not that mew cannot continue. It is that starting a second isolated project now would likely reproduce the same operator/reviewer/retry friction before M6.16/M9/M11 have absorbed the current evidence.

### Issue queue outcomes

The issue queue already contains reusable side-project polish findings from this arc:

- Issue #4 follows SP7 same-file write-batch retry/session-pressure polish.
- Issue #5 follows SP8 archive-index retry/verification polish.
- Issue #6 follows SP9 dogfood-digest ledger/issue semantics polish.
- Issue #7 follows SP10 export-contract reviewer-contract polish.

SP11 does not add a new live issue because this task is intentionally static/local, with no live GitHub query or network use. The reusable findings visible at this gate are already represented by the local status evidence for issues #4, #5, #6, and #7.

## Gate Decision

Choose: **pause side-project work for core M6.16/M9/M11 use**.

Rationale:

1. The first side project has enough successful breadth: state brief, bundles, archive index, dogfood digest, and export contract all exist with local focused tests.
2. The important remaining evidence is no longer another product surface; it is the repeated workflow friction around write batching, verifier repair, semantic ledgers, and reviewer-visible contracts.
3. `rescue_edits=0` across SP6-SP10 is a strong positive result and should be preserved as dogfood evidence rather than diluted by immediately opening a second project.
4. The issue queue already has the reusable polish items needed for core prioritization.

## What Should Happen Next

- Feed SP6-SP10 into core M6.16 hardening decisions.
- Revisit M9/M11 planning with the `mew-companion-log` contract surfaces as stable local fixtures.
- Start a second isolated side project only after core work has addressed the repeated write-batch/session-pressure and reviewer-contract polish classes, or after a new roadmap gate explicitly asks for a second cohort.

## Validation

Focused validation for this gate is static/local:

- The artifact is under `experiments/mew-companion-log`.
- The recommendation is explicit.
- The evidence is grounded in ledger rows `7`-`11` and local `[side-pj]` issue references.
- No second side-project implementation is started.
- No live `.mew` state, `src/mew` import, network query, or filesystem crawl is required.

The next verifier remains the local focused pytest command:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py
```
