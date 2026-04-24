# M6.11 Close-Gate Audit (2026-04-25)

Recommendation: CLOSE_READY.

Auditor task: close-gate audit builder only. This document does not update
`ROADMAP.md`, `ROADMAP_STATUS.md`, source, tests, or existing review docs.

Current HEAD: `fd9b38a` (`Record runtime calibration slice`).

Inputs inspected:

- `ROADMAP.md` M6.11 Done-when criteria.
- `ROADMAP_STATUS.md` M6.11 evidence and the documented fallback baseline
  history.
- `docs/M6_11_CLOSE_GATE_GAP_RATIONALE_2026-04-24.md`.
- `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md`.
- `docs/PROPOSE_M6_7_UNSTICK_2026-04-21.md`.
- `proof-artifacts/m6_11_calibration_ledger.jsonl`.
- Replay calibration output from
  `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --strict --json`.

Recent validation accepted for this audit:

- `./mew dogfood --all --json`: status `pass`.
- `uv run pytest -q tests/test_dogfood.py -k 'm6_11' --no-testmon`:
  `6 passed`.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --strict --json`:
  `ok=true`.

## Done-When Checklist

1. Phase 0-4 of the loop stabilization design are landed and validated;
   deferred phases are non-blocking.

   Status: PASS_WITH_NOTE.

   Evidence: `ROADMAP_STATUS.md` records refusal separation, `WorkTodo`,
   `PatchDraftCompiler`, replay capture, write-ready patch contract routing,
   Phase 4 follow-status parity, and the five M6.11 dogfood scenarios as
   landed. Phase 5 isolated review lane, Phase 6 executor lifecycle tightening,
   and provisional memory-provider protocol work remain explicitly deferred
   inside the milestone and are not close blockers.

   Note: `ROADMAP_STATUS.md` still says M6.11 is `in_progress`; this audit is
   intentionally tracked-ready evidence only and does not perform status
   bookkeeping.

2. `#399` is replayable offline and resolves to either a validated patch-draft
   path or one exact blocker without same-surface reread regression.

   Status: PASS.

   Evidence: `m6_11-compiler-replay` is registered and passing. The fixture set
   includes `tests/fixtures/work_loop/patch_draft/paired_src_test_happy`,
   `ambiguous_old_text_match`, and `stale_cached_window_text`. `ROADMAP_STATUS.md`
   records this as deterministic offline `#399` evidence using the patch-draft
   fixtures.

3. `#401` is replayable offline and recovery preserves the same drafting
   frontier via `resume_draft_from_cached_windows` instead of generic `replan`.

   Status: PASS.

   Evidence: `m6_11-draft-timeout` is registered and passing. The fixture
   `tests/fixtures/work_loop/recovery/401_exact_windows_timeout_before_draft`
   exercises the timeout-before-draft path, and the dogfood assertions check
   `next_recovery_action=resume_draft_from_cached_windows` on both resume and
   follow-status surfaces.

4. Live draft failures emit replay bundles early enough to reproduce the first
   post-rewrite failures locally.

   Status: PASS_WITH_NOTE.

   Evidence: replay bundles under `.mew/replays/work-loop/` are consumed by
   `proof-summary --m6_11-phase2-calibration`; the strict calibration pass
   found `total_bundles=74`, `non_counted_bundle_count=22`, and
   `malformed_relevant_bundle_count=0`. The canonical ledger includes replay
   paths for counted and rejected samples where replay artifacts existed.

   Note: not every positive bounded implementation slice should emit a replay
   bundle. Verifier-backed no-change and paired patch/verifier rows are ledger
   evidence, not replay-bundle calibration evidence.

5. `WorkTodo.status` is the canonical source of truth for drafting state, and
   follow-status/resume expose the same blocker code and next recovery action.

   Status: PASS.

   Evidence: `ROADMAP_STATUS.md` records Phase 4 follow-status parity as
   landed. The passing `m6_11-drafting-recovery`, `m6_11-draft-timeout`, and
   `m6_11-refusal-separation` dogfood scenarios assert phase, blocker code,
   active todo payload, `next_recovery_action`, and suggested recovery parity
   across direct resume and `work --follow-status`.

6. Refusal-shaped model output is classified distinctly from generic parse or
   transport failure at the work-loop boundary.

   Status: PASS.

   Evidence: refusal separation is represented as `model_returned_refusal` with
   recovery `inspect_refusal` in the patch-draft taxonomy. The passing
   `m6_11-refusal-separation` dogfood scenario checks that resume and
   follow-status surface `model_returned_refusal` through the blocked-on-patch
   contract rather than generic parse/backend failure.

7. At least one bounded mew-first implementation slice completes through the
   new drafting path with reviewer-visible dry-run preview,
   approval/apply/verify, and no rescue edits attributable to old drafting
   failure buckets.

   Status: PASS.

   Evidence: `ROADMAP_STATUS.md` records task `#521` / session `#502` as a
   positive current-head paired dry-run/apply/verify slice after the cached-ref
   hydration fix. The canonical ledger also contains multiple later counted
   paired patch/verifier rows in the 20-slice batch, including `#526`, `#527`,
   `#531`, `#534`, `#535`, `#536`, `#545`, `#546`, `#549`, and `#555`.

8. `m6_11-*` dogfood scenarios for compiler replay, draft timeout, refusal
   separation, drafting recovery, and phase-4 regression are registered and
   pass under strict M6.11 validation.

   Status: PASS.

   Evidence: `src/mew/dogfood.py` registers all five scenarios. The accepted
   validation commands show `./mew dogfood --all --json` passed, the M6.11
   dogfood pytest subset passed with `6 passed`, and strict proof-summary
   calibration returned `ok=true`.

9. A 20-slice bounded iteration batch shows at least a 50% combined reduction
   in `#399` + `#401` incidence versus the documented pre-M6.11 baseline, or a
   reviewer-signed documented reason explains a smaller reduction.

   Status: PASS_WITH_NOTE.

   Ledger computation:

   - Canonical ledger length: 127 rows.
   - Counted rows: 65.
   - Non-counted rows: 62.
   - Documented 20-slice batch starts at task `#524`.
   - Rows from `#524` through `#570`: 53 rows, 47 unique task ids, 42 counted,
     11 non-counted.
   - First 20 counted rows from `#524` through `#543`: 18 positive rows, 2
     counted fix-first blockers, 0 timeout-like counted rows.
   - Full counted continuation from `#524` through `#570`: 38 positive rows, 4
     counted fix-first blockers, 0 timeout-like counted rows.

   Conservative post-M6.11 incidence:

   - First 20 counted slices: 2 / 20 = 10.0% combined `#399/#401`-shaped
     incidence if `cached_window_incomplete` and
     `missing_exact_cached_window_texts_after_targeted_nontruncated_windows`
     are treated as `#399`-shaped exact-window drafting blockers.
   - Full counted batch continuation: 4 / 42 = 9.5% combined
     `#399/#401`-shaped incidence by the same mapping.
   - `#401` timeout-like counted incidence in both windows: 0 / 20 and 0 / 42.

Baseline comparison:

- The documented fallback baseline is the soft-stopped M6.7 candidate queue in
  `docs/PROPOSE_M6_7_UNSTICK_2026-04-21.md`. That proposal names six tried
  candidates: N-A, N-B, N-C, N-E, N-F, and N-H.
- Reviewer-audited baseline mapping:
  - N-A and N-B: `#399`-shaped. They soft-stopped after repeated attempts
    without a reviewable dry-run diff.
  - N-C: excluded from `#399/#401` incidence. It was reviewer no-change and
    already green.
  - N-E and N-H: `#399`-shaped. The supervisor landed the product patches
    directly because the mew sessions stalled in edit planning before a
    reviewable dry-run diff.
  - N-F: excluded from `#399/#401` incidence. It surfaced a real broader
    verifier blocker, which is useful task evidence but not the exact-window
    no-draft or timeout-before-draft failure bucket.
- Conservative baseline incidence is therefore 4 / 6 = 66.7% if all tried
  candidates are included, or 4 / 5 = 80.0% if the already-green N-C no-change
  item is excluded from the denominator.
- Post-M6.11 first-20 counted incidence is 2 / 20 = 10.0%, which is an 85.0%
  relative reduction against the 66.7% denominator and an 87.5% relative
  reduction against the 80.0% denominator.
- Post-M6.11 full counted continuation incidence is 4 / 42 = 9.5%, which is an
  85.7% relative reduction against the 66.7% denominator and an 88.1% relative
  reduction against the 80.0% denominator.
- Both windows clear the required 50% combined `#399/#401` incidence reduction.

Note: the ledger does not have a first-class `failure_bucket="#399|#401"`
field and does not store the pre-M6.11 baseline rows. This audit therefore
uses a reviewer-audited mapping from canonical ledger `countedness`,
`blocker_code`, and reviewer decisions, plus the documented fallback baseline.
No smaller-reduction waiver is used or needed.

10. A Phase 2/3 calibration checkpoint passes before Phase 3 starts, or an
    explicit Phase 2.5 calibration slice lands first; the checkpoint uses
    replay bundles to measure off-schema/refusal rates and prevent unstable
    rollout.

    Status: PASS_WITH_NOTE.

    Evidence: strict replay calibration returned `ok=true` with
    `off_schema_rate=0.0`, `refusal_rate=0.0`,
    `dominant_bundle_share=0.3108108108`, `malformed_relevant_bundle_count=0`,
    and all top-level thresholds passing. This is replay-bundle calibration,
    not 20-slice ledger evidence.

    Note: at HEAD `fd9b38a`, `cohort[current_head].total_bundles=0`. This is an
    expected artifact of evidence-recording commits: the latest runtime ledger
    slice `#570` is recorded on head `d7e9986`, and commit `fd9b38a` only
    records the runtime calibration slice, so those replay bundles now classify
    as `legacy` rather than literal `current_head`.

11. While M6.11 is open, measured and reviewer-rejected calibration samples are
    appended to the canonical ledger with head, scope, verifier,
    counted/non-counted status, blocker code, replay bundle path, and reviewer
    decision.

    Status: PASS.

    Evidence: `proof-artifacts/m6_11_calibration_ledger.jsonl` has 127 rows:
    65 counted and 62 non-counted. The latest row is task `#570` / session
    `#552`, counted as `positive_verifier_backed_no_change`, with head
    `d7e9986`, scoped runtime source/test files, verifier
    `uv run pytest -q tests/test_runtime.py --no-testmon`, reviewer decision
    `accept_no_change`, and notes explaining why the earlier cached-window wait
    was recovered by adjacent tail reads and is not a counting blocker.

## Replay Calibration Versus Ledger Evidence

Replay calibration and ledger evidence answer different questions.

Replay calibration reads `.mew/replays/work-loop/` and measures bundle quality:
off-schema rate, refusal rate, dominant bundle concentration, malformed
relevant bundles, and cohort distribution. The latest strict calibration passed
top-level thresholds with `total_bundles=74`. The literal current-head cohort is
empty only because the evidence-recording commit `fd9b38a` moved the latest
runtime replay bundles to the `legacy` cohort.

Ledger evidence is the canonical accounting source for measured and
reviewer-rejected calibration samples. It includes replay-backed incidents,
positive paired patches, verifier-backed no-change slices, fix-first blockers,
and non-counted remediation rows. The 20-slice bounded iteration gate is
computed from this ledger, not from the replay cohort alone.

## Final Recommendation

CLOSE_READY.

No close-blocking follow-up tasks are identified by this audit. Post-audit
roadmap/status bookkeeping should happen separately if the close recommendation
is accepted.
