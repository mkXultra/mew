# M6.11 Strengthen-Iter-B — Claude Review (final, after stale-head cache removal)

Scope reviewed (working-tree diff, uncommitted):

- `src/mew/work_replay.py`
- `src/mew/proof_summary.py`
- `tests/test_work_replay.py`
- `tests/test_proof_summary.py`

Task: replay-cohort tagging (`git_head`, `bucket_tag`, `blocker_code`) on
both bundle writers, plus a per-cohort `cohorts: {current_head, legacy,
unknown}` breakout under `summarize_m6_11_replay_calibration(...)`.

Verdict: **approve**.

## Change from prior re-review

The previous iteration added a cwd-keyed `_GIT_HEAD_CACHE` to amortize
the `git rev-parse HEAD` subprocess. That cache has now been removed
from both `src/mew/work_replay.py` and `src/mew/proof_summary.py`.
`_current_git_head()` is again a plain best-effort subprocess wrapper
on every call. The non-git-dir tests were updated to stop patching the
cache (they now just make `subprocess.run` raise `OSError`).

This is a deliberate correctness-over-perf trade: a process-lifetime
cache would return a stale HEAD whenever the repo advanced mid-session
(a real scenario for long-running work-loop processes that span
commits). Stale-cache bundles would be tagged with the wrong
`git_head`, which silently mis-buckets them in the summarizer — the
exact pathology this slice exists to cure. Paying the subprocess cost
per write keeps the stamp honest. I agree with the call.

Measured cost of removing the cache:

- 17.5 ms per `_current_git_head()` call (50 calls in 877 ms on this
  box).
- Called once per `write_patch_draft_compiler_replay(...)` (per
  compile attempt) and once per `write_work_model_failure_replay(...)`
  (per failure). The existing session-392 root has 14 attempt
  directories total, so the full slice's worst-observed subprocess
  cost to date is ~0.25 s aggregate over the session. Even a
  pathological 1000-attempt session aggregates to ~17 s over the whole
  session, not per second. Within budget for a work-loop process.

If this ever becomes a real perf problem, the correct mitigation is a
HEAD-move-aware invalidation (watch `.git/HEAD`) or capturing HEAD
once at session start and passing it to writers — not a naive
process-lifetime cache.

## Re-verification

- `uv run pytest -q tests/test_work_replay.py tests/test_proof_summary.py --no-testmon` → 31 passed.
- `uv run pytest -q tests/test_dogfood.py -k m6_11 --no-testmon` → 6 passed.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration` →
  top-level `total=14`, `dominant_share=0.5714`,
  `failure_mode_concentration_ok=False` unchanged; existing
  session-392 bundles all routed to `cohort[unknown]` as designed.
- Production compiler bundle shape:
  `_derive_compiler_bucket_tag({"kind":"patch_blocker","code":"write_policy_violation"}, {"id":"todo-...","source":{...}})`
  → `"code=write_policy_violation"` (empty contract/tiny parts filtered,
  no misleading `n/a` spam).

## Resolution of prior findings

### Resolved

- **(was Medium) Compiler-bundle `bucket_tag` misleading `n/a` spam.**
  `_build_bucket_tag` (`src/mew/work_replay.py:66-72`) filters empty
  values, so production compiler bundles get `"code=<validator_code>"`
  instead of `"code=X/contract=n/a/tiny=n/a"`. Pinned by
  `test_write_patch_draft_compiler_replay_bucket_tag_without_contracts_is_code_only`.
  The original secondary goal (actually carrying contract versions on
  compiler bundles) is still out of scope for this slice — the writer
  reads from the `todo` dict, which never carries contract versions
  in production. Cohort split via `git_head` is unaffected by this.

- **(was Low / Codex Medium) Non-git-dir summarizer mislabels tagged bundles as `legacy`.**
  `_cohort_label(...)` at `src/mew/proof_summary.py:129-137` returns
  `"unknown"` when `current_head` is empty/unset, so a summary process
  that cannot resolve its own HEAD no longer fabricates legacy
  incidence. Pinned by
  `test_summarize_m6_11_calibration_unknown_when_summary_head_lookup_fails`.

- **(was Low) Missing non-git-dir subprocess fallback tests.**
  Three new tests exercise the `subprocess.run`-raises path directly:
  - `test_write_work_model_failure_replay_non_git_head_fallback`
  - `test_write_patch_draft_compiler_replay_non_git_head_fallback`
  - `test_summarize_m6_11_calibration_non_git_head_lookup_fallback_is_non_raising`

### Consciously re-opened

- **(was Medium) Hot-path subprocess on every compile attempt.**
  `write_patch_draft_compiler_replay` now runs `git rev-parse HEAD`
  every call (no cache). Measured: ~17.5 ms per call. Session-392's
  14 attempts aggregate to ~0.25 s. Trade-off is intentional:
  a process-lifetime cache would let a mid-session HEAD move corrupt
  cohort tagging, which is the exact failure the slice is meant to
  prevent. Accepting the per-write cost to keep stamps honest is the
  right call. Not a blocker for landing.

### Still outstanding (non-blocking nits, unchanged)

- **Duplicated `_current_git_head` helper** across
  `src/mew/work_replay.py:50-63`,
  `src/mew/proof_summary.py:113-126`, plus a `--short HEAD` variant in
  `src/mew/context_checkpoint.py`. Three near-copies. Invites drift if
  someone tweaks one (e.g., timeout tuning). Tidy follow-up.

- **Dead-allowlist entries `patch_valid`/`patch_adapted`** in
  `_derive_compiler_blocker_code` at `src/mew/work_replay.py:111`.
  Neither name is emitted by the production write path; `"patch_valid"`
  appears only in test fixtures. Harmless.

- **Redundant `defaultdict(int, existing_defaultdict)` wraps** in
  `_finalize_m6_11_cohort_summary` at
  `src/mew/proof_summary.py:177, 199, 204-206`. No-op copies.

- **`refusal_by_type` / `refusal_breakdown` rebound inside the cohort
  loop** in `format_proof_summary`
  (`src/mew/proof_summary.py:720-724`). Reads correctly; readability
  nit.

- **`schema_version` not bumped** on `replay_metadata.json` /
  `report.json` despite the three new top-level keys. Strictly
  additive; old readers using `.get(...)` remain correct.

## Contract-safety summary

- Top-level `calibration` shape is unchanged — the cohort block is
  added under `calibration.cohorts`; all existing keys and threshold
  math are preserved (pinned by
  `test_summarize_m6_11_calibration_current_head_matches_top_level_threshold_math`).
- Replay bundle payloads are additive: `git_head`, `bucket_tag`,
  `blocker_code` are new top-level keys on
  `replay_metadata.json` / `report.json`; older readers using
  `.get(...)` remain correct.
- `format_proof_summary` cohort lines are appended **after** the
  existing `malformed_bundle_types:` line, so parsers reading the
  first N lines still see the prior contract.
- Scope stayed inside the four declared files; no touches to
  `work_loop.py`, `work_session.py`, `dogfood.py`, `commands.py`, or
  `patch_draft.py`. Landed dogfood scenarios unaffected.

## Final recommendation

`approve`.

All prior landing-relevant findings are resolved. The one deliberate
regression (per-write subprocess) is a correctness-for-perf trade that
matches the slice's stated purpose — keeping `git_head` stamps honest
across mid-session HEAD moves is more valuable than shaving 17 ms per
compile attempt. The remaining items are nits that belong in a
separate tidy-pass, not in this slice.
