# M6.11 Phase4-Regression Slice Review — Claude

Scope: uncommitted working-tree diff for
`src/mew/dogfood.py`, `tests/test_dogfood.py`, and the new fixture
`tests/fixtures/work_loop/phase4_regression/m6_6_comparator_budget/scenario.json`.
Design intent cross-checked against
`docs/REVIEW_2026-04-22_M6_11_NEXT_AFTER_REFUSAL_CODEX.md` and
`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md`.
HEAD at review time: `60832b9` (refusal-separation slice landed).

This is a re-review after follow-up fixes. The original review pass is
preserved verbatim under "Pass 1" below; the re-review verdict is in
"Pass 2".

---

## Pass 2 — Re-review after follow-up fixes

### Verdict: approve

Both medium-severity findings from Pass 1 are now closed. The slice
honestly delivers the intended close-gate move from
`4 pass + 1 not_implemented` to `5 pass`, the `(case_id, shape)`
mapping is now strictly pinned, and the per-case `source_reference`
provenance round-trips from the fixture into the emitted artifact and
is asserted in the test. Full `tests/test_dogfood.py` run is now
**81 passed / 0 failed** under `uv run pytest`.

### Pass 1 finding 1 — `(case_id, shape)` integrity — RESOLVED

The fix tightens the integrity check on three coordinated edges:

1. `M6_11_PHASE4_COMPARATOR_CASES` is upgraded from a tuple of strings to
   an explicit dict mapping at `src/mew/dogfood.py:107-111`:
   `{"M6.6-A": "M6.6-A", "M6.6-B": "M6.6-B", "M6.6-C": "M6.6-C"}`.
   This now declares the frozen `case_id → shape` invariant in code.
2. `_phase4_comparator_case_id` at `src/mew/dogfood.py:415-418` no longer
   falls back to `shape` or `name` — it returns only
   `str(case.get("case_id") or "").strip()`. Missing `case_id` therefore
   collapses to `""`, which fails the equality check.
3. A new `_phase4_comparator_case_shape` at `src/mew/dogfood.py:421-424`
   reads `shape` strictly, with no fallback chain.
4. The check at `src/mew/dogfood.py:1537-1546` now compares
   `sorted((case_id, shape))` pairs against
   `sorted(M6_11_PHASE4_COMPARATOR_CASES.items())` — exact pair-set
   equality, no aliasing.
5. The test at `tests/test_dogfood.py:651-654` enforces the dict
   `{case_id: shape}` from the artifact equals the expected mapping, so
   regressions in either direction would be caught at test time.

I confirmed the new behavior by reasoning through three adversarial
fixture variants:
- `case_id="M6.6-A"` + `shape="M6.6-OTHER"` → `case_pairs` contains
  `("M6.6-A","M6.6-OTHER")`, which is not in `expected_case_pairs` →
  **fails**.
- `shape="M6.6-A"` with no `case_id` → `case_id=""`, pair
  `("","M6.6-A")` not in expected → **fails**.
- Missing `shape` entirely → pair `("M6.6-A","")` not in expected →
  **fails**.

The integrity check now matches the design-doc claim.

### Pass 1 finding 2 — `source_reference` audit trail — RESOLVED

The provenance is now preserved end-to-end:

1. The artifact projection at `src/mew/dogfood.py:1499-1509` now copies
   `source_reference` per case alongside the existing `source`/`trace_id`
   fields.
2. The test at `tests/test_dogfood.py:635-637, 655-658` builds an
   `expected_provenance` dict from the fixture's
   `source_reference` values and asserts the artifact preserves the
   same `{case_id: source_reference}` mapping. So if a future change
   either drops the field from the artifact or mutates a fixture
   reference string, the test fails loudly.

I verified by reading the fixture (still
`source_reference: "M6.6-A comparator evidence"` etc. at
`tests/fixtures/.../scenario.json:11,17,23`) and the artifact code
path. The audit trail back to M6.6 evidence now survives into
the report.

Note: the artifact still also includes `source` and `trace_id`, both
of which remain `None` for this fixture because the fixture does not
populate them. That is harmless (the test does not assert their value)
but is mildly redundant against the now-canonical `source_reference`.
Not a blocker.

### Pass 1 findings 3 and 4 — unchanged, still optional polish

- `_phase4_case_wall_seconds` at `src/mew/dogfood.py:427-438` still
  accepts the four-name fallback chain. Same low/nit assessment as
  before.
- The test's median formula at `tests/test_dogfood.py:640` still uses
  `sorted(case_walls)[len(case_walls) // 2]`. Still correct for the
  pinned 3-case fixture; still a fragility if the fixture ever grows.

Neither blocks landing.

### Verification

- Focused: `uv run pytest tests/test_dogfood.py::DogfoodTests::test_run_dogfood_m6_11_phase4_regression_scenario tests/test_dogfood.py::DogfoodTests::test_run_dogfood_m6_11_all_subset_aggregate_reflects_full_coverage` — **2 passed**.
- Full file: `uv run pytest tests/test_dogfood.py` — **81 passed**.

### Recommendation

**approve**

The two medium findings raised in Pass 1 are addressed at the layer
they should be (helper strictness, expected-value declaration,
artifact projection, and matching test assertions). The remaining
nits are explicitly optional and do not affect proof integrity. Safe
to land and flip the aggregate `m6_11-*` subset to `5 pass`.

---

## Pass 1 — original review (preserved for context)

### Verdict summary

The slice honestly delivers the intended close-gate move from
`4 pass + 1 not_implemented` to `5 pass`. Median/budget math is correct
for the current fixture, the scenario dispatch and aggregate test are
rewired consistently, and all 75 `tests/test_dogfood.py` cases pass
under `uv run pytest`. Two integrity-chain findings weaken the
strength-of-proof in ways worth tightening, but neither makes the
current proof false — they reduce its resistance to future fixture
drift and strip per-case provenance from the emitted artifact.

### Findings

#### 1. Fixture "frozen shape" integrity is weaker than the design-doc claim (medium)

The design spec (and `PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN` §3.1) says the
scenario must prove "comparator names/shapes are the frozen M6.6 A/B/C
set." The implementation only checks the set of *derived ids*, not the
`(case_id, shape)` pair.

- `_phase4_comparator_case_id` at `src/mew/dogfood.py:411-416` falls back
  `case_id → shape → name`, so the "id" is whichever of those three
  resolves first.
- The integrity assertion at `src/mew/dogfood.py:1526-1535` compares only
  `case_names = {case.get("case_id") for case in comparator_cases}`
  against `M6_11_PHASE4_COMPARATOR_CASES`.
- `shape` is captured into the emitted artifact at
  `src/mew/dogfood.py:1493` but never asserted.

Consequences:
- A future fixture with `case_id: "M6.6-A"` + `shape: "something-else"`
  still passes every check and still reports "proof passed against the
  M6.6 shapes." The scenario would claim something it has not verified.
- A fixture with `shape: "M6.6-A"` and no `case_id` also passes (via the
  fallback), which is the more benign path but still means the frozen
  label is not pinned to a single field.

Neither case is the current fixture (which pins `case_id == shape == "M6.6-A/B/C"`
at `tests/fixtures/.../scenario.json:8-21`), so the slice is honest
today. The integrity check is looser than the invariant the design
document relies on.

Minimal fix: compare the `{(case_id, shape)}` pair set to the expected
`{("M6.6-A","M6.6-A"), ("M6.6-B","M6.6-B"), ("M6.6-C","M6.6-C")}` set, or
add a separate `_scenario_check` enforcing `case_id == shape` for each
case. Either locks the frozen-label invariant to the fixture schema.

#### 2. Per-case audit trail (`source_reference`) is dropped from the artifact (medium)

The fixture pins per-case provenance — `"source_reference": "M6.6-A comparator evidence"`
and siblings at `tests/fixtures/.../scenario.json:11,17,23`. That is the
only hook tying the pinned numbers (4.0 / 3.7 / 3.8 / 3.9) back to any
M6.6 evidence chain, since I could not find independent corroboration
of those specific numbers in
`docs/M6_6_CODEX_PARITY_COMPARE.md` or surrounding M6.6/M6.9 docs
(which is fine under the "pinned deterministic fixture" scope, but makes
the audit field load-bearing for inspectability).

The scenario code at `src/mew/dogfood.py:1496-1498` instead reads
`case.get("source")` and `case.get("trace_id")`, neither of which exists
in this fixture. Result: every comparator case in
`report["artifacts"]["comparator_cases"]` has `"source": null`,
`"trace_id": null`, and **no `source_reference` at all**. The audit
trail is silently lost.

The test at `tests/test_dogfood.py:648-652` only asserts
`case_id` set membership and total count, so it does not catch the drop.

Minimal fix: either rename the fixture key to `source` (simpler), or
extend the artifact projection to include `source_reference`. Adding one
test assertion that the artifact preserves each case's evidence string
would prevent future regressions of the same shape.

#### 3. Loose wall-time field alias chain (low / nit)

`_phase4_case_wall_seconds` at `src/mew/dogfood.py:419-430` accepts four
candidate field names (`iter_wall_seconds` → `iter_wall` → `wall_seconds`
→ `wall_time_seconds`). The design doc is silent on field naming, so
this is style, not correctness — but the more aliases the helper
tolerates, the less the fixture schema is a real contract, and the more
likely a future contributor introduces a fourth fixture that mixes
names silently. The B0 block also uses `iter_wall` while cases use
`iter_wall_seconds`, so the helper is already papering over inconsistent
naming between sibling fields in the same fixture. Consider pinning a
single canonical name and tightening the helper to only that name.

#### 4. Test median formula only agrees for odd case counts (low / nit)

The production helper `_median_wall_seconds` at `src/mew/dogfood.py:400-408`
correctly averages two middle values for even-length inputs. The test at
`tests/test_dogfood.py:637` computes
`sorted(case_walls)[len(case_walls) // 2]`, which only agrees with the
production helper for odd lengths. With the current three-case fixture
(enforced by `case_count == 3`) they match at 3.8, so there is no bug
today. It is just a subtle fragility: if the fixture is ever extended to
four cases and the `case_count` expectation updated, the test's own
median computation will silently diverge from the code under test. A
clearer test would either reuse `_median_wall_seconds` or duplicate the
even-length branch.

### Things that are right

- Median computation for the pinned fixture (3.7, 3.8, 3.9) yields 3.8,
  exactly matching the production helper.
- Budget computation: `B0.iter_wall × 1.10 = 4.0 × 1.10 = 4.4`, and
  3.8 ≤ 4.4 — check passes honestly.
- `run_m6_11_phase4_regression_scenario` emits exactly the four
  `_scenario_check` assertions listed in the design doc
  (`case_count == 3`, `expected_comparator_cases`,
  `case_wall_time_present`, `median_vs_budget`).
- Report artifacts include `b0_iter_wall_seconds`, `budget_wall_seconds`,
  `median_wall_seconds`, and the full `comparator_cases` list per the
  design-doc requirement.
- Scenario is dispatched from the runner at
  `src/mew/dogfood.py:11454-11455`, consistent with the other four
  m6_11 scenarios.
- Aggregate test `test_run_dogfood_m6_11_all_subset_aggregate_reflects_full_coverage`
  at `tests/test_dogfood.py:654-695` is updated from the old
  `_reflects_not_implemented` shape: status flipped from `fail` to
  `pass`, all five `m6_11-*` subscenarios asserted `pass`, and the
  formatted text includes `m6_11-phase4-regression: pass`.
- The stale `test_run_dogfood_m6_11_not_implemented_scenarios` test is
  removed cleanly with no dangling one-element subtest shell.
- No changes to `work_loop`, `work_session`, or `commands` — slice scope
  matches the design doc's "harness/proof slice, not product-behavior
  slice" mandate.
- Full `tests/test_dogfood.py` run: 75 passed / 0 failed under
  `uv run pytest`.

### Integrity-of-proof assessment

The scenario is honest within the scope the design document chose
(pinned deterministic fixture, not live benchmark). It does **not**
measure the real loop; it asserts "a pinned fixture claims median 3.8s
vs budget 4.4s, therefore budget met." That is the agreed contract and
is appropriate for a close-gate proof.

The weakening from findings 1 and 2 is that the fixture contract is
softer than the design-doc language suggests, and the artifact trail
that would let a reviewer audit the pinned numbers is partially
severed. Tightening either — ideally both — would bring the proof up to
the strength the design doc describes. Neither is a blocker for landing
this slice and flipping the aggregate `m6_11-*` subset to `pass`, but
they should be follow-ups before anyone quotes this scenario as
unconditional Phase 4 NFR evidence.

### Recommendation

**approve_with_nits**

Land the slice to close the gate, and file a follow-up to:

1. tighten the comparator-integrity check to enforce `case_id == shape`
   (or compare `(case_id, shape)` pairs to the frozen expected set), and
2. preserve `source_reference` into the emitted artifact (renaming the
   fixture key to `source` is the smallest change) plus add one
   assertion that each case's provenance string survives into the
   report.

Findings 3 and 4 are optional polish.
