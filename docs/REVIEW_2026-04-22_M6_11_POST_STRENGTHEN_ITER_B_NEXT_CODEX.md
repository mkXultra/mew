# M6.11 Post-Strengthen-Iter-B Next Step — Codex

## 1. Verdict

The exact next bounded step is: **collect the first fresh current-HEAD live replay cohort, starting with a bounded rerun on task `#402`, then rerun calibration summary.**

Current `HEAD` (`f61e657`) already landed Strengthen-Iter-B. The blocking fact in the fresh summary is not missing instrumentation; it is that `calibration.cohorts.current_head.total_bundles == 0` while all `14` relevant bundles still sit in `cohorts.unknown`. Until at least one new live bundle is written on current `HEAD`, the close gate cannot say whether `#399/#401` incidence is actually dropping.

`#399` and `#401` remain open historical blocker tasks, but they are not the next bounded action. `#402` is the existing live collection surface with a known command shape and replay root, so it is the right first evidence source.

## 2. Why This Is Now The Highest-Value Step

- `ROADMAP_STATUS.md` already says the post-Iter-B gap is "collecting fresh current-HEAD bundles first, then rerun `proof-summary`."
- The fresh `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` output is still red only because the replay root is old/unknown-cohort data:
  - `current_head.total_bundles = 0`
  - `unknown.total_bundles = 14`
  - `unknown.dominant_bundle_type = work-loop-model-failure.request_timed_out`
  - `unknown.dominant_bundle_share = 0.5714285714285714`
- That means another implementation slice now would be blind. Strengthen-Iter-B already solved attribution; the next missing truth is fresh evidence from current `HEAD`.

## 3. Commands To Run

Start with one bounded live rerun on the existing `#402` surface:

```bash
./mew work 402 --live --auth auth.json --model-backend codex --allow-read . --allow-write src/mew --allow-write tests --allow-verify --verify-command 'uv run pytest -q tests/test_memory.py -k veto --no-testmon' --act-mode model --max-steps 1
```

If one step does not emit a useful fresh replay bundle, use the already-recorded short burst once:

```bash
./mew work 402 --live --auth auth.json --model-backend codex --allow-read . --allow-write src/mew --allow-write tests --allow-verify --verify-command 'uv run pytest -q tests/test_memory.py -k veto --no-testmon' --act-mode model --max-steps 3
```

Then re-measure immediately:

```bash
./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```

Success for this bounded step is modest but exact: `cohorts.current_head.total_bundles` becomes non-zero and the summary can finally distinguish fresh current-head behavior from stale unknown history.

## 4. What Not To Do Next

- Do **not** cut another Phase 0-4 implementation slice before a fresh current-HEAD cohort exists.
- Do **not** treat the all-`unknown` calibration result as evidence that current `HEAD` is still timeout-dominated.
- Do **not** start the full 20-slice incidence gate yet; first prove the replay root is receiving current-head bundles.
- Do **not** reopen `#399` or `#401` as the immediate coding task; use them as incidence labels, not as the next action.
- Do **not** change thresholds, discard old bundles, or resume unrelated M6.9/M6.10 product work.
