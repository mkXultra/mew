# M6.12 Close-Gate Audit (2026-04-25)

Recommendation: CLOSE_READY.

Auditor task: close-gate audit and roadmap-status input only. This document
does not update source, tests, proof artifacts, or the canonical M6.11
calibration ledger.

Current HEAD: `c7b6dcd`
(`Add M6.12 proof-summary report surface`).

Inputs inspected:

- `ROADMAP.md` M6.12 Done-when criteria.
- `ROADMAP_STATUS.md` M6.12 active-focus entry.
- `docs/DESIGN_2026-04-24_M6_12_FAILURE_SCIENCE_INSTRUMENTATION.md`.
- `docs/REVIEW_2026-04-23_M6_12_CALIBRATION_INPUT_FROM_EXTERNALS.md`.
- `proof-artifacts/m6_11_calibration_ledger.jsonl`.
- Replay bundles under `.mew/replays/work-loop`.
- Commits `ec0e0d4` and `c7b6dcd`.

Recent validation accepted for this audit:

- `uv run pytest -q tests/test_proof_summary_m6_12.py tests/test_proof_summary.py tests/test_calibration_report.py --no-testmon`:
  `64 passed`.
- `uv run ruff check src/mew/proof_summary.py src/mew/commands.py tests/test_proof_summary_m6_12.py`:
  all checks passed.
- `uv run python -m unittest tests.test_commands`: `182` tests passed. The
  run emitted the existing `mew: no active runtime found` messages and Python
  `ResourceWarning`s, but no test failure.
- `./mew proof-summary .mew/replays/work-loop --m6_12-report --ledger proof-artifacts/m6_11_calibration_ledger.jsonl --json --strict`:
  `ok=true`, `canonical.mode=pre_closeout`, `ledger_rows=127`,
  `counted_rows=65`, `non_counted_rows=62`, `referenced=30`,
  `resolved=30`, and `missing=0`.
- `./mew proof-summary .mew/replays/work-loop --m6_12-report --ledger proof-artifacts/m6_11_calibration_ledger.jsonl --strict`:
  exits `0` and renders the operator cockpit.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --strict --json`:
  `ok=true`, preserving the existing M6.11 strict proof-summary behavior.
- Codex-ultra reviewer session
  `019dc104-51be-7ce2-99a0-f3b5735853cb` approved the corrected Phase 2
  implementation after strict provenance, JSON-contract, text-cockpit, and
  legacy proof-summary checks were added.

## Done-When Checklist

1. Every row in the closed 127-row M6.11 calibration ledger is classified into
   exactly one v0 archetype or `unclassified_v0` with a row-ref warning, and
   the emitted counts match the design's post-priority totals.

   Status: PASS.

   Evidence: the strict live M6.12 report emitted all 127 rows across the
   design totals:
   `preflight_gap=9`, `cached_window_integrity=17`,
   `drafting_timeout=12`, `drafting_no_change=6`,
   `write_policy_block=4`, `timeout_family_no_bundle=5`,
   `verifier_config_evidence=2`, `measurement_process_gap=6`,
   `live_finish_gate_validation=3`, `no_change_non_calibration=4`,
   `positive_outcome_v0=42`, `fix_first_evidence=3`,
   `drafting_other=0`, `model_failure_other=0`, and
   `unclassified_v0=14`.

2. Every derived label traces back to a ledger row and, where applicable, a
   replay bundle reference.

   Status: PASS.

   Evidence: `derived.archetypes_active` entries carry `row_refs` and
   `bundle_refs`. Missing bundle accounting includes row references, and the
   post-closeout resolver tests cover all missing reason codes.

3. Text output fits the single-screen cockpit discipline while still showing
   reserved drift axes.

   Status: PASS_WITH_NOTE.

   Evidence: the live strict text output exits `0`, is sectioned as an
   operator cockpit, includes the reserved drift axes even at `count=0`, and
   currently renders in `78` lines against the 127-row ledger. The 14
   `unclassified_v0` warnings are intentionally explicit because they are part
   of the v0 Done-when contract. Future row-capping or folding can be a later
   ergonomics slice, but it is not a v0 blocker.

4. `--json` separates `canonical` from `derived`, includes
   `bundle_provenance`, and exposes `derived.classifier_priority`.

   Status: PASS.

   Evidence: `tests/test_proof_summary_m6_12.py` asserts the contract layers,
   classifier priority, default ledger path, measurement-head cohort handling,
   and CLI strict/non-strict behavior. The live JSON report includes the
   pre-closeout `bundle_provenance` object with `mode`, `root`,
   `closeout_index`, `referenced`, `resolved`, `missing`, and
   `missing_row_refs`.

5. Pre-closeout and post-closeout resolver modes are both tested, including
   strict-mode failures for missing bundles and closeout-index errors.

   Status: PASS.

   Evidence: focused tests cover pre-closeout missing bundles, post-closeout
   index miss, export-file miss, sha mismatch, malformed index hard-fail,
   `--closeout-index` flag gating, and strict missing-bundle non-zero exit.

6. Existing `proof-summary` default and `--m6_11-phase2-calibration` strict
   behavior remains unchanged.

   Status: PASS.

   Evidence: the focused proof-summary regression tests pass, and the live
   `--m6_11-phase2-calibration --strict --json` command still returns
   `ok=true`.

7. No canonical ledger field is renamed, widened, or retroactively rewritten.

   Status: PASS.

   Evidence: the implementation reads the canonical JSONL ledger and computes
   derived labels at report time. It does not write back to
   `proof-artifacts/m6_11_calibration_ledger.jsonl`.

8. Reviewer adjudication still wins when a derived label would disagree with
   `reviewer_decision`.

   Status: PASS.

   Evidence: the classifier tests exercise positive-outcome and
   fix-first/reviewer-decision priority cases so rows do not fall through to
   misleading success labels.

9. Mew-first implementation boundary is recorded honestly.

   Status: PASS_WITH_NOTE.

   Evidence: task `#572` started as a mew-first implementation loop, but the
   final Phase 2 patch required direct supervisor rescue after reviewer
   rejections. Count the landed report as product progress and M6.12 closure
   evidence, not clean autonomy credit. This should feed the next durable
   coding/autonomy hardening slice.

## Closure Decision

M6.12 v0 satisfies the bounded read-only failure-science instrumentation gate.
The closeout bundle export tree and governance wiring remain explicitly
deferred by the design and are not v0 blockers.

After M6.12 closes, resume M6.9 Durable Coding Intelligence from its landed
Phase 1 substrate. The M6.12 report should be used as an operator input for
choosing the next hardening slice, especially recurrence and failure-family
evidence from the closed M6.11 ledger.
