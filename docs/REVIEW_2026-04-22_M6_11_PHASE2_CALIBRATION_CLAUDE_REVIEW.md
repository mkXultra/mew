# M6.11 Phase 2/3 Calibration Checkpoint (Claude Review, Revision 3)

Scope: `src/mew/proof_summary.py`, `src/mew/cli.py`, `src/mew/commands.py`, `tests/test_proof_summary.py`, minimal `ROADMAP_STATUS.md`. Revision 3 re-checks the two Codex-raised concerns that the revision-2 addendum conceded to proposal text.

## Verdict

**Green to land as the Phase 2/3 rollout gate.** Both adopted-proposal concerns from the revision-2 addendum are now correctly resolved. Two observability bugs in the formatter's refusal-breakdown rendering are new active findings but are non-blocking for Phase 3 rollout, since gate pass/fail is independent of that rendering.

## Findings

### Codex concern (a) — concentration gate must apply unconditionally — **resolved**

`proof_summary.py:290` now applies the 40% rule without the compiler-only bypass:

```python
dominant_share_ok = total_bundles == 0 or dominant_bundle_share <= 0.4
```

The only exemption is the trivially-empty case (no data to measure). This matches proposal §3.3 literal text ("no single bundle type exceeds 40% of total bundle count") and proposal Risk #3 ("gate always trips is intended behavior"). `test_summarize_m6_11_calibration_compiler_monoculture_fails_concentration_gate` at `tests/test_proof_summary.py:555-567` explicitly pins the compiler-only case as failing: 10 compiler-healthy bundles → `dominant_bundle_share == 1.0` → `failure_mode_concentration_ok == False` → `summary["ok"] == False`.

The gate also gained meaningful discriminative power via the new per-outcome sub-typing at `proof_summary.py:126-140`: compiler bundles are bucketed by validator code (`patch_draft_compiler.off_schema`, `.refusal`, `.other`) and model-failure bundles by failure code (`work-loop-model-failure.model_refused`, `.model_failed_timeout`, etc.). This reads "bundle type" as "bundle outcome / failure mode" — which is what the proposal's parenthetical ("prevents one failure mode dominating") actually wants, not a coarse "which replay format the bundle used." The mixed-distribution test at `tests/test_proof_summary.py:382-424` shows the gate correctly passing a realistic Phase 3 sample (4 healthy compiler + 3 timeouts + 3 rejections → dominant share = 0.4, at the inclusive boundary).

### Codex concern (b) — malformed bundles must block the gate — **resolved**

`proof_summary.py:214, 236, 265` track `malformed_relevant_bundle_count` — bundles whose top-level type matches one of the two known types but which fail to parse or are missing required data. `proof_summary.py:291, 300, 310` adds `malformed_relevant_bundles_ok` to the gate:

```python
malformed_bundle_ok = malformed_relevant_bundle_count == 0
...
thresholds_pass = all((
    thresholds["off_schema_rate_ok"],
    thresholds["refusal_rate_ok"],
    thresholds["failure_mode_concentration_ok"],
    thresholds["malformed_relevant_bundles_ok"],
    thresholds["has_bundles"],
))
```

`test_summarize_m6_11_calibration_malformed_relevant_bundle_fails` at `tests/test_proof_summary.py:519-537` pins the new behavior: one valid compiler bundle + one `{`-truncated metadata → `malformed_relevant_bundle_count == 1` → `malformed_relevant_bundles_ok == False` → `summary["ok"] == False`. The earlier revision's counter-assertion that `ok` stays true is gone.

"Ignored" bundles (right filename, wrong `bundle` field — e.g., `legacy-work-loop-failure`) are distinct from malformed-relevant and are still diagnostic-only, counted under `malformed_bundle_counts[f"ignored_{bundle_type}"]` without failing the gate. That's the right split: ignored bundles aren't part of the measurement sample, so they don't threaten rate trustworthiness, while unreadable relevant bundles do.

### New Finding 1 — formatter's `refusal_breakdown` lookup keys never match any populated key

`proof_summary.py:523-527` renders:

```python
"refusal_breakdown="
f"compiler={refusal_by_type.get('patch_draft_compiler', 0)} "
f"failure={refusal_by_type.get('work-loop-model-failure', 0)}"
```

The scanner never stores anything under the bare keys `'patch_draft_compiler'` or `'work-loop-model-failure'`. It stores:
- `'patch_draft_compiler.refusal'` (from `calibration_bundle_type` at `proof_summary.py:248`)
- `'model_returned_refusal'` (from `refusal_code` at `proof_summary.py:250`)
- `'work-loop-model-failure.model_refused'` (from `calibration_bundle_type` at `proof_summary.py:274`)
- `'model_refused'` (from the `or` fallback at `proof_summary.py:275`)

Net effect: `refusal_breakdown=compiler=0 failure=0` is emitted regardless of the actual refusal mix. Operators reading the textual output to diagnose a failing refusal gate will see misinformation. None of the existing tests exercise this path with refusals present — `test_format_m6_11_calibration_output` uses a no-refusal fixture — so the defect is untested as well.

Not blocker-level: the gate's `ok` boolean and `thresholds.refusal_rate_ok` are independently correct, and the JSON output's raw `refusal_by_type` still contains the real per-key counts. But the headline text line is wrong, and a diagnostician using only the rendered summary would be misled. Fix is one-line: either key the formatter lookup on the actual stored keys (`.refusal`, `.model_refused`) or add a dedicated two-key aggregate during summarization.

### New Finding 2 — `refusal_by_type` pollution with non-refusal codes

`proof_summary.py:249-250` populates `refusal_by_type` for *any* non-empty compiler validator code, not just refusal codes:

```python
if bundle_summary.get("refusal"):
    refusal_count += 1
    refusal_by_type[calibration_bundle_type] += 1
if bundle_summary.get("refusal_code"):
    refusal_by_type[bundle_summary.get("refusal_code")] += 1
```

`_summarize_patch_draft_compiler_bundle` sets `refusal_code = code` unconditionally (`proof_summary.py:173`), so a healthy compiler bundle with `code == "patch_valid"` still hits the truthy branch and writes `refusal_by_type["patch_valid"] += 1`. The dict name and the data no longer match. Observable in any JSON `calibration.refusal_by_type` field in the wild, but — because of Finding 1 — not surfaced by the formatter. Not a gate-correctness issue; `refusal_count` is only incremented under the strict `refusal` flag. Suggested fix: rename to `validator_code_breakdown` (or similar) if that population shape is actually desired, or gate the line on `bundle_summary.get("refusal")` if it isn't.

## Residual risks

- **Sub-typing is an interpretation.** The proposal literally says "no single bundle type exceeds 40% of total bundle count," and the implementation reads "bundle type" at sub-type granularity (`patch_draft_compiler.off_schema` etc.) rather than at top-level filename granularity. Reading the parenthetical "(prevents one failure mode dominating)" as the operative intent, this is defensible and makes the gate actually discriminate between failure modes rather than between file formats. Worth a one-line comment near `_calibration_compiler_type` documenting the choice, but not a land-blocker.
- **Concentration boundary is inclusive.** `dominant_bundle_share <= 0.4` (`proof_summary.py:290`) passes exactly-40% samples (as the mixed-distribution test demonstrates). Matches proposal's "exceeds 40%" phrasing; confirming this is intended rather than drift would be a one-line comment.
- **Dead loop at `proof_summary.py:276-277`.** Same as prior reviews — after the failure-bundle error branch `continue`s, the subsequent `for error in bundle_summary.get("errors") or []:` can only fire when the list is empty. Harmless no-op; clean up on next touch.
- **Bundle name matching is still literal** (`proof_summary.py:228, 257`). A future `patch_draft_compiler_v2` rename would route silently to `ignored_*`. Observable via `malformed_bundle_counts`; acceptable for now.
- **CLI flag underscore/hyphen mix** (`cli.py:949-953`). Cosmetic.
- **No `schema_version` enforcement** in the scanner. Low priority until v2 lands.
- **Backwards compatibility of the existing `proof-summary` path is intact.** Unchanged since revision 2.

## Recommended next step

Land the slice. Address the two formatter findings as a small follow-up before any operator actually uses the textual summary for refusal-gate diagnosis; do not block Phase 3 rollout on them, since the gate itself is correct and the JSON output carries the real data.
