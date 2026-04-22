# M6.11 Fresh Evidence Source Pick — Codex

Date: 2026-04-22

## Verdict

Pick a **new M6.11 dogfood-harness task on `src/mew/dogfood.py` + `tests/test_dogfood.py`**, not another `#402` rerun and not a reporting-only `proof_summary` slice.

## Ranked Candidate Slices

1. **Preferred:** harden `m6_11-compiler-replay` by freezing the expected fixture set under `tests/fixtures/work_loop/patch_draft/` and adding one negative malformed-fixture test that must fail cleanly.
   - Old-text anchors are already tight and local: [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:491), [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:683), and [tests/test_dogfood.py](/Users/mk/dev/personal-pj/mew/tests/test_dogfood.py:478).
   - This is active M6.11 evidence-harness work, not frozen M6.9 surface work.

2. `m6_11-phase4-regression` negative-path hardening in the same pair: prove the scenario fails cleanly on missing timing or wrong `(case_id, shape)` mapping.
   - Also good and similarly bounded, but slightly lower value than compiler-replay scope hardening because the compiler-replay scenario is closer to the current live incidence/evidence collector.

3. `src/mew/proof_summary.py` + `tests/test_proof_summary.py`: add additive `blocker_code_counts` for current-head cohorts.
   - Clean and small, with exact anchors at [src/mew/proof_summary.py](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:325) and [tests/test_proof_summary.py](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:504).
   - Not preferred first because the repo’s latest M6.11 memos explicitly defer reporting-only work until after the first fresh non-`#402` live slice exists.

## Exact Preferred Slice

**`src/mew/dogfood.py` + `tests/test_dogfood.py`: bound `m6_11-compiler-replay` to the current three fixture dirs and add one negative malformed-fixture test.**

Recommended shape:

- in `run_m6_11_compiler_replay_scenario(...)`, assert the fixture set is exactly:
  - `paired_src_test_happy`
  - `stale_cached_window_text`
  - `ambiguous_old_text_match`
- add one focused test that temporarily removes a required hash field from a replay fixture payload and asserts the scenario reports `fail` cleanly instead of silently widening scope or producing misleading pass evidence

## Why This Is Better Than `#402`

- `#402` is already recorded in the review trail as a **frozen M6.9** source and has produced a narrow mixed-surface blocker pair (`unpaired_source_edit_blocked`, `insufficient_cached_test_context`) rather than a clean M6.11-owned evidence source.
- This slice stays on **one paired src/test surface** instead of the `#402` mixed memory/CLI surface.
- The exact old text needed to edit it is already concentrated in short, obvious blocks, so mew can cache both sides up front without reopening the `insufficient_cached_test_context` pattern.
- It is directly useful to the active M6.11 close-gate path because it hardens the deterministic evidence harness that the live incidence gate will rely on.

## Exact Bounded Command Shape For The First Live Run

```bash
./mew task add --kind coding --ready \
  "M6.11 current-head evidence: bound compiler-replay dogfood fixture scope" \
  --description "Scope fence: src/mew/dogfood.py + tests/test_dogfood.py only. Tighten m6_11-compiler-replay so it asserts the exact fixture set under tests/fixtures/work_loop/patch_draft and add one negative malformed-fixture test that fails cleanly when a required cached-window/live-file hash is missing. Focused verifier: uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay'." --json

./mew work <NEW_TASK_ID> --ai --live --max-steps 8 --start-session \
  --allow-read src/mew/dogfood.py \
  --allow-read tests/test_dogfood.py \
  --allow-read tests/fixtures/work_loop/patch_draft \
  --allow-write src/mew/dogfood.py \
  --allow-write tests/test_dogfood.py \
  --allow-verify \
  --verify-command "uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay'" \
  --work-guidance "First cache the exact old text for run_m6_11_compiler_replay_scenario and test_run_dogfood_m6_11_compiler_replay_scenario before drafting. Keep the edit inside this paired src/test surface. Do not touch #402 or frozen M6.9 memory surfaces."
```

After that first fresh run, rerun:

```bash
./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```
