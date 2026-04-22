# M6.11 Post-5-Pass Next Slice — Codex

## 1. Verdict

Implement **Strengthen-Iter-B now**: add replay-cohort tagging plus current-head batch/incidence summary for M6.11 replays.

Exact slice:

- stamp both `work-loop-model-failure` and `patch_draft_compiler` bundles with cohort fields that let us separate current-HEAD runs from superseded attempts: at minimum `git_head`, a stable `bucket_tag`, and `blocker_code` when a blocker exists
- extend `mew proof-summary --m6_11-phase2-calibration` so the output can summarize current-head/cohort counts separately from legacy mixed-root counts, without changing any thresholds

## 2. Why This Is The Highest-Value Bounded Slice Now

- Current `HEAD` already has the close-gate dogfood matrix green: `ROADMAP_STATUS.md` and `tests/test_dogfood.py` both reflect all five `m6_11-*` scenarios as `pass`. Earlier next-slice docs that recommended `m6_11-drafting-recovery`, `m6_11-draft-timeout`, refusal separation, or Phase 4 parity are now stale as next-step guidance because those slices landed.
- The live calibration result is still honestly red right now: `14` relevant bundles, `8` `work-loop-model-failure.request_timed_out`, dominant share `0.5714285714285714` (> `0.4`).
- But the current replay root is a mixed single-session history, not a clean current-HEAD cohort. Session `392` contains older `v1`/`v2` timeout bundles (`turn-1819` to `turn-1821`) and newer compiler-blocker bundles (`attempt-1` to `attempt-6`), with the latest observed turn (`1826`) already on tiny contract `v3` and exiting via compiler fallback in `11.58s`, not timeout.
- Today the replay bundles do **not** carry the cohort keys needed to tell "current HEAD still failing" apart from "historical failures still dominating the shared root". Another prompt/runtime tweak now would be blind.
- This slice is the smallest honest move that turns the red gate into an actionable decision: after it lands, a fresh bounded rerun can tell us whether a real Phase 2.5 timeout-reduction fix is still needed.

## 3. Files To Touch If Code Is Recommended

- `src/mew/work_replay.py`
- `src/mew/proof_summary.py`
- `tests/test_work_replay.py`
- `tests/test_proof_summary.py`
- optional only if integration coverage is cleaner there: `tests/test_work_session.py`

## 4. Focused Validation

- Add replay-writer tests proving both bundle families persist the new cohort fields.
- Add proof-summary tests proving:
  - mixed historical roots report current-head/cohort counts separately
  - unknown/legacy bundles stay visible as legacy, not silently merged into current-head counts
  - threshold math stays unchanged for the selected cohort
- Run:
  - `uv run pytest -q tests/test_work_replay.py tests/test_proof_summary.py`
  - `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
- Success condition for this slice: the existing session-392 root becomes attributable by cohort, and the next rerun can measure current-HEAD timeout concentration honestly.

## 5. What Not To Do Next

- Do **not** treat dogfood `5/5` as a proxy for calibration green.
- Do **not** change calibration thresholds or implicitly discard old bundles.
- Do **not** spend the next slice on more follow-status/operator-surface polish; that work is already landed.
- Do **not** jump straight into another timeout/prompt tweak before the replay root can distinguish obsolete `v1`/`v2` failures from current-HEAD behavior.
- Do **not** resume M6.9 or M6.10 work until this measurement gap is closed.
