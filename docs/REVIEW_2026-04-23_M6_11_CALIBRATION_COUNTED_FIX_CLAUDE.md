# M6.11 Calibration-Counted Compiler Replay Fix — Review (Claude)

Date: 2026-04-23
Reviewed working tree on top of `739c527`.

## 0. Bottom line

**Ships. The slice does solve the session-405 malformed-bundle pollution.**
A handful of minor issues remain (dead code, one design-vs-implementation
deviation on non-counted malformed accounting, silent failure in the helper),
but none block the fix. End-to-end verification on the live repo shows
`cohort[current_head]` is clean.

## 1. What was reviewed

Working-tree diff touching:
- `src/mew/commands.py` — reject hook that marks the compiler replay
  non-counted.
- `src/mew/proof_summary.py` — (a) accept validated `patch_draft` without
  `code`, (b) consume `calibration_counted` field.
- `src/mew/work_replay.py` — (a) add `calibration_counted` /
  `calibration_exclusion_reason` to metadata on write, (b) helper
  `mark_patch_draft_compiler_replay_non_counted`.
- `src/mew/work_session.py` — helper `find_model_turn_for_tool_call`.
- Corresponding tests in `tests/test_proof_summary.py`,
  `tests/test_work_replay.py`, `tests/test_work_session.py`.
- The two session-405 replay metadata files already on disk
  (`.mew/replays/work-loop/2026-04-22/session-405/todo-todo-405-1/attempt-{1,2}/replay_metadata.json`)
  which contain the backfill (`calibration_counted=false`,
  `calibration_exclusion_reason="reviewer rejected"`).

## 2. End-to-end verification

Ran `PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop
--m6_11-phase2-calibration --json` against the live repo. Result:

- `summary.errors` is **empty** (was 2 spurious "missing or invalid
  validator_result JSON" messages before the fix).
- `cohort[current_head].total_bundles = 1`,
  `compiler_bundles = 1`, `relevant_bundles = 1`,
  `malformed_bundle_count = 0`, `malformed_relevant_bundle_count = 0`,
  `non_counted_bundle_count = 2`, `non_counted_bundle_reasons =
  {"reviewer rejected": 2}`.
- `thresholds.malformed_relevant_bundles_ok = true`.

The overall `ok` is still `false` only because
`failure_mode_concentration_ok=false` (dominant share 0.71 with a sample
of 1 counted bundle); that is the expected sparse-sample behavior and is
unrelated to this fix.

All existing and new tests pass:
- `tests.test_work_session` — 491 tests pass.
- `tests.test_work_replay` — 12 tests pass.
- `tests.test_proof_summary` — 24 tests pass.

## 3. Correctness of the fixes

### 3.1 Classifier fix (proof_summary.py:316-326)

Works as intended. When `validator_result.code` is absent, the code
now falls through if and only if `kind=="patch_draft" && status=="validated"`,
classifies the bundle as `patch_draft_compiler.other`, and leaves
`off_schema`/`refusal` false. All other shapes (unreadable JSON, non-dict,
unrecognized payload) continue to be malformed. This matches the matrix
Codex and I agreed on in
`REVIEW_2026-04-23_M6_11_POST_405_MALFORMED_BUNDLE_{CLAUDE,NEXT_CODEX}.md`.

### 3.2 Calibration-eligibility metadata (work_replay.py)

- Write-time defaults `calibration_counted=True`,
  `calibration_exclusion_reason=""` (line 340-341). ✓
- `mark_patch_draft_compiler_replay_non_counted(metadata_path, reason)`
  (lines 365-390) reads/mutates/rewrites the file with the same
  `json.dumps(..., indent=2, sort_keys=True)` shape. ✓
- Error handling is safe-but-silent: missing path, non-existent file,
  non-UTF8, non-JSON, non-dict payload, and unwritable target all return
  False. See §4.3 for the trade-off.

### 3.3 Reject hook (commands.py:5723-5734)

Flow is correct:
1. `reject_work_tool_call` runs as before (unchanged semantics on
   `source_call`).
2. `find_model_turn_for_tool_call(session, source_call.get("id"))` looks
   up the owning turn.
3. `replay_path` is read from `model_turn["model_metrics"]
   ["patch_draft_compiler_replay_path"]` (already populated by the
   work-loop shadow compile at `work_loop.py:2962` and the tiny-draft
   path at `work_loop.py:1727`; absolute path per `work_loop.py:1547`).
4. Helper flips the metadata.

The helper is called with the stripped `reason`, so
`calibration_exclusion_reason` is whitespace-free.

### 3.4 `find_model_turn_for_tool_call` (work_session.py:1512-1519)

Reuses `_turn_tool_call_ids(turn)` (work_session.py:2888), so both the
singular `tool_call_id` (set in `finish_work_model_turn`) and the plural
`tool_call_ids` (set in batched flows at `commands.py:2928,3079`) are
checked. `reversed()` returns the most recent match, which is the
right turn for pending dry-runs. Stringifies both sides — robust to
int-vs-str id drift.

Test coverage (`test_work_session_reject_pending_write_marks_patch_draft_replay_non_counted`)
asserts the full chain: dry-run edit_file → synthesized model_turn with
`tool_call_id` + `model_metrics.patch_draft_compiler_replay_path` →
`--reject-tool` → `calibration_counted=false` on disk. The existing
reject test (`test_work_session_can_approve_and_reject_dry_run_write_tool`)
still passes, confirming no regression for the no-model-turn path.

## 4. Issues

### 4.1 Low — dead code in `work_replay.py`

`_coerce_bool(value, default=False)` at `src/mew/work_replay.py:14-17`
is defined but never referenced in `src/mew`. Likely a drafting
remnant — proof_summary.py has its own `_coerce_calibration_counted`
and the helper mutates `calibration_counted` directly. Delete.

### 4.2 Low — deviation from design: non-counted bundles still count in `malformed_bundle_count`

The Codex/Claude reviews specified that `calibration_counted=false`
bundles should be excluded from **all** `malformed_*` buckets. The
implementation excludes them from `malformed_relevant_bundle_count`
(the gating metric) but *not* from `malformed_bundle_count`.

Reproduced directly:

```
PYTHONPATH=src python3 -c "
import tempfile, json, sys
from pathlib import Path
sys.path.insert(0, 'src')
from mew.proof_summary import summarize_m6_11_replay_calibration

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); bundle = root / 'b' / 'attempt-1'; bundle.mkdir(parents=True)
    (bundle / 'replay_metadata.json').write_text(json.dumps({
        'bundle': 'patch_draft_compiler',
        'files': {'validator_result': 'validator_result.json'},
        'calibration_counted': False,
        'calibration_exclusion_reason': 'test',
    }))
    (bundle / 'validator_result.json').write_text('{')
    s = summarize_m6_11_replay_calibration(root)
    print(s['calibration']['malformed_bundle_count'],
          s['calibration']['malformed_relevant_bundle_count'],
          s['calibration']['non_counted_bundle_count'],
          len(s['errors']))
"
# → 1 0 1 1
```

A non-counted bundle with a malformed validator_result is simultaneously
counted as malformed **and** non-counted, and its error message leaks
into `summary.errors`. Two consequences:

- Cosmetic inconsistency: one bundle appears in two buckets.
- No gate is affected: only `malformed_relevant_bundles_ok` gates, and
  that metric stays clean.

In the realistic path this rarely triggers — rejection happens after the
validator has produced a well-formed artifact. But it is a real
deviation from the stated spec. Either:

- drop the malformed-bookkeeping for non-counted bundles (simpler; matches
  Codex's spec), or
- keep double-counting and document that `malformed_bundle_count` is
  "all bundles with any error regardless of counted status."

No action required to ship, but worth picking a direction before the
20-slice incidence batch.

### 4.3 Low — test for 4.2 hides the deviation

`test_summarize_m6_11_calibration_non_counted_compiler_bundle_excluded`
(tests/test_proof_summary.py:485-513) uses a deliberately malformed
`validator_result.json` (`"{"`) for its non-counted bundle. It asserts
`malformed_relevant_bundle_count=0` but does **not** assert on
`malformed_bundle_count` or on `len(summary["errors"])`. If the design
goal is Codex's spec, the test should additionally check
`malformed_bundle_count == 0` and `summary["errors"] == []`. If the
intent is the current behavior, switch to a well-formed validator
payload (`{"kind":"patch_draft","status":"validated"}`) so the test
reflects the production case instead of an accidental edge.

### 4.4 Low — silent failures in `mark_patch_draft_compiler_replay_non_counted`

The helper returns `False` on missing path, missing file, read error,
JSON error, non-dict payload, or write error. `cmd_work_reject_tool`
discards the return value — the operator sees nothing if the calibration
metadata was not actually flipped. Two forgivable scenarios (no
compiler replay attached; fail-fast already returned False) and several
genuinely diagnostic ones (file gone, permissions) end up looking
identical. Consider logging a one-line warning when the helper fails
*and* `replay_path` was non-empty.

### 4.5 Cosmetic — rejection_reason stripping asymmetry

`commands.py:5722` passes the unstripped reason to
`reject_work_tool_call` (stored in `source_call.rejection_reason`).
`commands.py:5731` passes the stripped reason to the helper (stored in
`calibration_exclusion_reason`). These two fields can disagree on
leading/trailing whitespace. Either strip once near the top of the
function or accept it as harmless.

### 4.6 Cosmetic — missing blank line in `tests/test_proof_summary.py`

Between the new `test_summarize_m6_11_calibration_non_counted_compiler_bundle_excluded`
and the existing `test_summarize_m6_11_calibration_legacy_bundles_are_ignored`
(around line 513-514), there is no blank line. Matches nothing around
it stylistically. Trivial.

## 5. Residual risk

- `find_model_turn_for_tool_call` returns only the most recent match. No
  current flow produces multiple turns that share a `tool_call_id`, so
  this is fine. If a future retry flow re-links the same tool_call id to
  multiple turns, the helper silently flips only the last turn's replay.
- The classifier fix accepts any `kind=="patch_draft" && status=="validated"`
  payload as `patch_draft_compiler.other`, without checking structural
  completeness (e.g., `unified_diff`, `files`). That is a conscious
  simplification — the validator upstream is the source of truth for
  "validated." If the validator schema ever loosens, proof-summary will
  uncritically trust it.
- Backfill durability: the two session-405 `replay_metadata.json` files
  live under `.mew/replays/` which is `.gitignore`'d. If a fresh clone
  replays the same work, those files will not exist and there is nothing
  to re-flip. This is consistent with how other replay artifacts are
  treated. But the backfill is not reproducible from git state alone;
  it depends on whoever ran the hand-edit (or the live reject flow)
  having done so in each operator's local `.mew/`.

## 6. Recommendations

Ship the slice. Follow-ups (not blocking):

1. Delete `_coerce_bool` from `work_replay.py`.
2. Decide on §4.2's malformed-accounting rule and make the test in §4.3
   assert it explicitly.
3. Add a one-line warning from the reject path when
   `mark_patch_draft_compiler_replay_non_counted` returns False despite
   a non-empty `replay_path`.
4. Optionally strip `reject_reason` once at the top of
   `cmd_work_reject_tool` so all downstream writes see the same value.
