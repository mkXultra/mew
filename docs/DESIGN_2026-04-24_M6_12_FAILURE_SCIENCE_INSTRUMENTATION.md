# M6.12 Failure-Science Instrumentation Design (v0)

Date: 2026-04-24
Refreshed: 2026-04-25 (post-M6.11 closeout; ledger grew 68 → 127 rows)
Status: draft, post-M6.11 closeout; canonical input is now the closed
`M6.11` ledger
Owner: M6.12 design surface
Depends on: `M6.11 Loop Stabilization` (closed)

## 1. Purpose And Non-Goals

### 1.1 Purpose

`M6.12 Calibration ergonomics` turns the calibration ledger and replay bundles
that `M6.11` already produces into an operator-facing failure-science surface.
The surface should answer three questions a human operator or reviewer can
ask at any point during a stabilization slice:

- *What is hardest right now on current head?*
- *What changed after the last hardening slice?*
- *Which next slice is most likely to reduce recurrence rather than just move it?*

This design defines what `M6.12` should build. It does not choose final thresholds,
final archetype labels, or a final CLI name, and it does not implement anything
yet. A later `M6.12` plan should be able to turn this document into CLI/code
tasks without rediscovering the evidence plane or reopening the canonical ledger
schema.

### 1.2 Non-Goals

`M6.12` is explicitly **not** supposed to:

- widen the canonical calibration ledger schema. `M6.11` is now closed and
  its ledger is the authoritative input ([ROADMAP.md](../ROADMAP.md)
  `M6.11` close-gate, last bullet); M6.12 reads it, never mutates it.
- adopt `Hermes`, `OpenClaw`, `Codex`, or `Vellum Assistant` loop architecture,
  queue abstractions, product surface, or numeric tuning as mew defaults
  ([REVIEW_2026-04-23_M6_12_CALIBRATION_INPUT_FROM_EXTERNALS.md](REVIEW_2026-04-23_M6_12_CALIBRATION_INPUT_FROM_EXTERNALS.md))
- treat external PR counts, commit counts, release duration, or test counts as
  mew hardness targets
- hide drift behind automatic recovery (auto-compress, auto-retry, auto-resume,
  auto-repair) without recording the before/after boundary
- fold `drift` into generic runtime noise; drift remains a first-class family
- replace reviewer judgement; `reviewer_decision` stays the adjudicating field
- merge external evidence into the canonical ledger or counted bundle math
- ship an unbounded cockpit; the MVP surface should fit on one screen of text
- introduce multi-lane infrastructure (e.g. `WorkTodo.lane` fields, per-lane
  bundle schemas, empty mirror lane, shadow-bridge generalization). Lane
  framework work is consolidated into `M6.13` together with the Deliberation
  Lane itself so that framework and first real backend ship as one coherent
  theme ([REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md](REVIEW_2026-04-23_HIGH_EFFORT_MODEL_TUNING.md))

### 1.3 Shape Of The Product

`M6.12` is a *reading* surface on top of a source-of-truth that `M6.11` already
owns. Every operator claim must trace back to a canonical row in
`proof-artifacts/m6_11_calibration_ledger.jsonl` or a replay bundle that the
row points at. Any derived bucket must be reproducible from those same rows.

## 2. Inputs

### 2.1 Canonical Inputs (mew-native, authoritative)

These are the only sources `M6.12` may treat as counted evidence:

- `proof-artifacts/m6_11_calibration_ledger.jsonl`
  - one JSONL row per calibration sample
  - current shape (unchanged across closeout; verified against the
    post-closeout ledger):
    `recorded_at, head, task_id, session_id, attempt, scope_files, verifier,
    counted, countedness, non_counted_reason, blocker_code, reviewer_decision,
    replay_bundle_path, review_doc, notes`
  - the `countedness` field is already appearing on newer rows and classifies
    *how* a sample counts or fails to count (for example
    `partial_gate_validation_only`,
    `current_head_native_patch_draft_compiler_replay_cached_window_incomplete_duplicate_surface`,
    `fix_first_pre_active_todo_planning_timeout_no_replay`); the `M6.12`
    classifier must treat `countedness` as read-only input, not rewrite it
- replay bundles referenced by `replay_bundle_path`
  - `replay_metadata.json` for `patch_draft_compiler` bundles
  - `report.json` for `work-loop-model-failure` bundles
  - per-bundle fields already consumed by
    [src/mew/proof_summary.py](../src/mew/proof_summary.py) (e.g.
    `calibration_counted`, `calibration_exclusion_reason`, `git_head`,
    `bucket_tag`, `blocker_code`, validator `code`)
  - **Provenance caveat:** `replay_bundle_path` values in the current ledger
    are local paths under `.mew/replays/work-loop/**`. They resolve only on
    the host that produced them and will be absent from a fresh checkout.
    `M6.12` must therefore treat bundle access as a host-dependent surface
    pre-closeout and must separate *ledger-only* aggregates from
    *bundle-derived* rates whenever any referenced bundle is missing
    (see section 8.5).
- the reviewer docs linked by `review_doc`

### 2.2 Secondary Inputs (context, non-canonical)

These inform operator narrative but must not be merged into counted math:

- current-head git state (via `git rev-parse HEAD`) for cohort labeling
- `ROADMAP.md` / `ROADMAP_STATUS.md` for milestone gating prose
- prior design docs that `M6.12` must respect:
  - [docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md](LOOP_STABILIZATION_DESIGN_2026-04-22.md)
  - [docs/REVIEW_2026-04-23_M6_12_CALIBRATION_INPUT_FROM_EXTERNALS.md](REVIEW_2026-04-23_M6_12_CALIBRATION_INPUT_FROM_EXTERNALS.md)

### 2.3 External Prior (informative only)

The `Hermes / OpenClaw / Codex / Vellum Assistant` failure-science memo is an
input to the *derived* classifier layer. It is never counted. It supplies
candidate archetype names and drift axes for `M6.12` to map onto mew-native
evidence. With `M6.11` closed, that mapping runs against the post-closeout
ledger rather than an in-flight target.

## 3. Canonical vs Derived Data Model

This is the central discipline of `M6.12`.

### 3.1 Canonical Layer (frozen at M6.11 closeout)

Only these fields may be used as sources of truth:

| Source | Field(s) |
|---|---|
| ledger row | `head, task_id, session_id, attempt, scope_files, verifier, counted, countedness, non_counted_reason, blocker_code, reviewer_decision, replay_bundle_path, review_doc, notes, recorded_at` |
| replay bundle metadata | `bundle, calibration_counted, calibration_exclusion_reason, git_head, bucket_tag, blocker_code`, validator `code` / `failure.code` |
| cohort | derived from `git_head` vs current HEAD and optional `--measurement-head` (already implemented in [src/mew/proof_summary.py](../src/mew/proof_summary.py) `summarize_m6_11_replay_calibration`) |

`M6.12` **must not** add, rename, or widen canonical fields now that
`M6.11` is closed. The post-closeout ledger shape is the contract `M6.12`
was designed against; any new canonical field is a v1 breaking change
requiring a `classifier_version` bump and a separate reviewer-signed
slice (see §8 for the refresh contract this design still holds M6.12 to,
even though closeout itself is no longer pending).

### 3.2 Derived Layer (read-time only, free to evolve)

Derived fields exist only in the operator surface. They are recomputed from
canonical inputs on every run. A consumer of `M6.12` output should be able to
delete every derived label and rebuild it from the ledger and bundles alone.

Derived labels fall into three families:

1. **archetype** — a coarse failure family label. Archetypes are partitioned
   into Tier 1 (active) and Tier 2 (reserved) per section 4.2. Only Tier 1
   labels are aggregated or ranked; Tier 2 labels are declared but require
   matching canonical evidence before they can be rendered as counted.
2. **drift_axis** — one of five drift buckets (see section 4.3). All five
   axes are reserved (Tier 2) in v0 and always render as `count=0` until
   promoted.
3. **subsystem_tag** — which internal surface is implicated (e.g.
   `patch_draft_compiler`, `work_loop.planning`, `write_ready_fast_path`,
   `dogfood.compiler_replay`).

Rules for the derived layer:

- every derived label carries a pointer back to the canonical evidence that
  produced it (`row_ref` = ledger line number; `bundle_ref` = replay bundle
  path under the chosen `artifact_dir`, or `null` if the row has
  `replay_bundle_path=null`)
- a derived label is never allowed to *shadow* a canonical disagreement; if
  `reviewer_decision` contradicts a derived archetype, the surface shows both
  and prefers the reviewer
- derived labels are versioned by a `classifier_version` string so older
  snapshots remain reproducible
- no derived label is emitted back into canonical files (no round-trip write)
- bundle-derived aggregates are subject to the provenance / missing-bundle
  rules in section 8.5; `canonical.bundle_provenance` in the JSON contract is
  the authoritative separator between ledger-only and bundle-derived math

### 3.3 Why This Split Is Load-Bearing

The external memo warns that `M6.12` will be tempted to import the
`Hermes/OpenClaw/Codex/Vellum` archetype vocabulary directly. If those strings
become canonical, two things break:

- reviewer-rejected samples lose their mew-native reasons because the importer
  rewrote the blocker code
- `M6.11` closure evidence becomes retroactively unstable because its ledger
  schema now depends on a classifier that post-dates it

The split above is what lets `M6.12` import failure *analysis* without
importing failure *schema*.

## 4. Failure Classifier v0

Classifier v0 is intentionally conservative. It emits labels that can be
defended purely from existing ledger rows and bundle fields. It does not
attempt to reproduce the full external archetype set.

### 4.1 Grounding Rule

The first classifier pass must only use fields that already appear in the
current ledger or replay bundles. The ranking of label sources (strongest to
weakest) is:

1. `reviewer_decision` (the human judgement is the tie-breaker)
2. `countedness` (already classifies *how* a row counts)
3. `blocker_code` (from ledger and/or bundle)
4. `calibration_exclusion_reason` + `non_counted_reason` (free-text priors,
   matched by normalized substrings)
5. `bundle_type` + validator `code` / `failure.code`
6. `scope_files` (for subsystem tag)

If none of (1)-(5) yields a confident label, v0 emits
`archetype=unclassified_v0` rather than guessing.

### 4.2 v0 Archetype Set (derived, partitioned)

Archetypes are partitioned into two tiers so the surface cannot imply more
calibration than the current ledger actually supports:

- **Tier 1 — active v0 archetypes.** Each label cites at least one matching
  current ledger row or bundle field via a strong/moderate evidence priority
  (P1 / P2). These are the only labels the cockpit is allowed to aggregate,
  rank, or feed into the comparator.
- **Tier 2 — reserved/provisional archetypes.** These labels reflect
  failure modes the external memo (and the loop-stabilization design) warns
  about, but the current ledger has zero or only weak (P3) grounding for
  them. v0 keeps the labels declared so future rows can adopt them without
  vocabulary churn, but v0 must *not* render them unless a row actually
  carries matching canonical evidence.

**Evidence priorities used below:**

- **P1 (strong):** direct match to `blocker_code` (in ledger or bundle) or to
  validator `code` / `failure.code`.
- **P2 (moderate):** direct match to `reviewer_decision` or `countedness`
  (stable structured fields), without a canonical `blocker_code`.
- **P3 (weak):** evidence only appears in free-text `non_counted_reason`,
  `calibration_exclusion_reason`, or `notes`. P3-only labels stay reserved in
  v0 and are rendered only under `--expand`, always with a warning.

Row counts below reflect the post-M6.11-closeout
`proof-artifacts/m6_11_calibration_ledger.jsonl` (127 rows total, of
which 65 are counted, 62 non-counted, 30 have a `replay_bundle_path`,
and 97 do not; the ledger spans 99 unique git heads).

The enumerations in the two tables below list the named `blocker_code` /
`reviewer_decision` / `countedness` values that were present at the
2026-04-24 snapshot plus any close-gate additions observed in the
127-row post-closeout state. Classifier implementation must enumerate
the names it recognizes exactly; any *new* ledger value that a future
slice introduces without being on these lists falls through to a
`*_other` fallback with a warning (see §4.2.D for the post-closeout
tail).

**Raw match vs post-priority emit.** Each grounding row now carries two
counts:

- *Raw match* — the number of ledger rows whose fields satisfy this
  archetype's enumeration in isolation. This is the count an
  implementer will read straight out of the ledger when writing unit
  tests against a single rule.
- *Post-priority emit* — the number of ledger rows that actually reach
  this archetype after the §4.2.A.2 priority list runs, i.e. what the
  classifier prints in the cockpit and JSON. Differences between the
  two columns are caused entirely by earlier-slot interception and
  are spelled out in the `Priority interception` column.

The distinction matters because several Tier 1 archetypes share raw
matches with `preflight_gap` at slot 1 or with the `fix_first_*`
fallback family; a raw-only count over-states the cohort the
classifier actually emits. Post-priority counts below are what the
cockpit "counted" tallies will equal when the classifier runs against
the closeout ledger and report them under §6.3
`derived.archetypes_active[].counted`.

#### 4.2.A Tier 1 — Active v0 Archetypes

**Compiler / drafting family** (derived from `patch_draft_compiler` bundles
and `blocker_code`):

| Archetype | Evidence | Enumerated match values (post-closeout ledger, 127 rows) | Raw | Post-priority emit | Priority interception |
|---|---|---|---|---|---|
| `cached_window_integrity` | P1 | `blocker_code ∈ {insufficient_cached_window_context (13), cached_window_incomplete (4), insufficient_cached_context (2), missing_exact_cached_window_texts_after_targeted_nontruncated_windows (2), cached_window_incomplete_after_mid_block_test_window (2), missing_exact_cached_window_texts (1), cached_window_refs_not_hydrated_to_exact_window_texts (1)}` | 25 | 17 | 8 rows have `countedness` or `reviewer_decision` containing `preflight`, so they are captured by `preflight_gap` at slot 1 first |
| `drafting_timeout` | P1 | `blocker_code ∈ {timeout (8), drafting_timeout_after_complete_cached_refs_no_artifact (2), model_auth_timed_out_object (1), medium_small_impl_predraft_timeout_after_full_pair_read_no_artifact (1)}`; plus `work-loop-model-failure` reports with `failure.code=request_timed_out` | 12 | 12 | none |
| `drafting_no_change` | P1 | `blocker_code ∈ {no_material_change (4), verifier_green_no_change_overridden_by_overlapping_hunks (2), no_concrete_draftable_change (1)}` | 7 | 6 | 1 row is a preflight-tagged `fix_first_*` row that is captured by `preflight_gap` at slot 1 first |
| `write_policy_block` | P1 (weak N) | `blocker_code ∈ {old_text_not_found (2), write_policy_violation (1), unpaired_source_edit_blocked (1)}` | 4 | 4 | none |
| `drafting_other` | P1 (fallback) | strict fallback: rows with a `replay_bundle_path` that points at a compiler bundle **and** a non-null `blocker_code` that is not in the enumerations above. No row in the post-closeout 127-row ledger satisfies this combined predicate: the five unrecognised blocker codes observed at closeout — `work_already_running` (row 36), `session_accounting_gap_external_patch` (row 119), `write_ready_structural_tokenize_indentation_crash` (row 122), `write_ready_preflight_adjacent_tail_read_wait_loop` (row 125), `recent_read_file_windows_missing_next_line_for_tail_refresh` (row 126) — all appear on non-bundle rows. `drafting_other` remains declared so a future row that genuinely is compiler-bundle + unrecognised blocker has a Tier 1 home without a `classifier_version` bump. Emits a `drafting_other_warning` naming the unrecognised code whenever N > 0. | — | 0 | no interception needed, because no ledger row is a `drafting_other` candidate. For the routing of the five unrecognised-blocker non-bundle rows listed in the Enumerated match values cell: rows 122, 125, 126 have `countedness=fix_first_remediation` and land in `fix_first_evidence` at slot 12; rows 36 and 119 have non-`fix_first_*` countedness and fall through to `unclassified_v0` at slot 15. Neither path involves `drafting_other`. |

**Non-bundle family** (derived from `reviewer_decision` / `countedness` when
`replay_bundle_path=null`):

| Archetype | Evidence | Enumerated match values (post-closeout ledger, 127 rows) | Raw | Post-priority emit | Priority interception |
|---|---|---|---|---|---|
| `no_change_non_calibration` | P2 | `reviewer_decision=accepted_as_no_change_non_calibration` | 4 | 4 | none |
| `measurement_process_gap` | P2 | `reviewer_decision ∈ {accepted_as_no_bundle_measurement_process_gap_evidence (2), accepted_as_no_bundle_measurement_path_evidence (2), accepted_as_non_counted_measurement_artifact_evidence (2)}` | 6 | 6 | none |
| `verifier_config_evidence` | P2 | `reviewer_decision=accepted_as_no_bundle_verifier_config_evidence` | 2 | 2 | none |
| `timeout_family_no_bundle` | P2 | `reviewer_decision ∈ {accepted_as_no_bundle_timeout_family_evidence (3), accepted_as_no_bundle_timeout_family_fix_first_evidence (2)}`; distinct from `drafting_timeout` because no bundle was emitted | 5 | 5 | none |
| `preflight_gap` | P2 | match rule per §4.2.A.1 (structured preflight evidence in `countedness` or `reviewer_decision`, plus explicit handling of `non_counted_no_artifact_live_preflight_validation`) | 9 | 9 | none — `preflight_gap` is at slot 1, so it intercepts other rows rather than being intercepted |
| `fix_first_evidence` | P2 (fallback) | rows whose `countedness` starts with `fix_first_` **or** equals `counted_fix_first_blocker` and that do not match any more specific Tier 1 archetype. See the priority rule in §4.2.A.2 and the `fix_first_*` exclusion from `positive_outcome_v0` in §4.2.D. Raw = 18 `fix_first_*` starts-with rows + 4 `counted_fix_first_blocker` rows = 22. | 22 | 3 | 15 of the 18 `fix_first_*` rows land in earlier slots (6 in `preflight_gap`, 6 in `cached_window_integrity`, 2 in `drafting_timeout`, 1 in `drafting_no_change`, 0 in `write_policy_block`); all 4 `counted_fix_first_blocker` rows land in `cached_window_integrity` at slot 2. The 3 rows that actually emit at slot 12 are the `fix_first_remediation` rows whose `blocker_code` is unrecognised (rows 122, 125, 126 in the post-closeout ledger). |
| `live_finish_gate_validation` | P2 | `reviewer_decision=accepted_as_live_finish_gate_validation_not_replay_incidence` | 3 | 3 | none |
| `positive_outcome_v0` | P2 | match rule per §4.2.D (explicit enumerations plus the `fix_first_*` exclusion guard) | 42 | 42 | none — the §4.2.D exclusion is applied inside the match itself, not by an earlier priority slot |

**v0 classifier-output summary (post-priority emits against the 127-row
closeout ledger, from the fixed §4.2.A.2 + §4.2.D rules):**

- `preflight_gap`: 9
- `cached_window_integrity`: 17
- `drafting_timeout`: 12
- `drafting_no_change`: 6
- `write_policy_block`: 4
- `timeout_family_no_bundle`: 5
- `verifier_config_evidence`: 2
- `measurement_process_gap`: 6
- `live_finish_gate_validation`: 3
- `no_change_non_calibration`: 4
- `positive_outcome_v0`: 42
- `fix_first_evidence`: 3
- `drafting_other`: 0 (see table row above; no current ledger row is a `drafting_other` candidate)
- `model_failure_other`: 0. The closeout ledger contains no `work-loop-model-failure` report row whose `failure.code` falls outside the `drafting_timeout` enumeration: every bundle with a non-null `blocker_code` already matches one of `cached_window_integrity`, `drafting_timeout`, `drafting_no_change`, or `write_policy_block`, and no current bundle carries a non-timeout model-failure `failure.code`. The slot-14 label stays declared so a future non-timeout model-failure report row has a Tier 1 home without a `classifier_version` bump.
- `unclassified_v0`: 14. Three residual shapes, confirmed by simulation against the 127-row ledger:
  - *No `blocker_code`, no `replay_bundle_path`, no Tier 1 reviewer/countedness match* — 7 rows (rows 6, 10, 24, 28, 30, 31, 35). Reviewer decisions such as `accepted_as_no_bundle_prompt_risk_evidence`, `accepted_as_no_bundle_verifier_only_evidence`, `accepted_as_no_bundle_closeout_recognition_evidence`, `rejected_as_no_bundle_verifier_only_false_finish`, `rejected_as_fixture_only_verifier_finish`, `accepted_as_live_finish_gate_blocker_validation_not_replay_sample`, and `rejected_as_no_artifact_timeout_read_loop` are not in any v0 Tier 1 enumeration.
  - *Compiler bundle with `blocker_code=null` or empty, and no Tier 1 reviewer/countedness match* — 5 rows (rows 3, 25, 26, 38, 43). Under the strict `drafting_other` definition these cannot land in slot 13 (they lack an unrecognised non-null blocker), and they are not `work-loop-model-failure` reports so they cannot land in slot 14 either. They therefore fall through to slot 15.
  - *Non-bundle row with an unrecognised `blocker_code` whose `countedness` does not start with `fix_first_`* — 2 rows: row 36 (`blocker_code=work_already_running`, `countedness=rejected_recursive_same_session_work_invocation`) and row 119 (`blocker_code=session_accounting_gap_external_patch`, `countedness=non_counted_external_patch_due_session_accounting_gap`). Neither reaches `fix_first_evidence` (countedness does not start with `fix_first_`) nor `drafting_other` (no bundle), so they fall through to slot 15.

  All 14 rows trigger the §4.1 `unclassified_v0` warning with
  `row_ref` and a field dump so operators can see exactly which
  fields did not match any Tier 1 enumeration.

Sum check: 9 + 17 + 12 + 6 + 4 + 5 + 2 + 6 + 3 + 4 + 42 + 3 + 0 + 0 + 14 = **127** ✓

These are the numbers the MVP classifier implementation should reproduce
against the closeout ledger, not the raw enumeration totals. They will
also be emitted under §6.3 `derived.archetypes_active[].counted`.

#### 4.2.A.1 `preflight_gap` Match Rule

A row matches `preflight_gap` when **any** of the following holds:

- `countedness` contains the literal substring `preflight` (case-insensitive)
  — this covers current values such as
  `fix_first_unnumbered_preflight_refresh_gap`,
  `fix_first_preflight_refresh_gap`,
  `fix_first_preflight_search_result_read_gap`,
  `fix_first_preflight_search_result_path_and_anchor_gap`,
  `fix_first_preflight_compact_refresh_search_history_gap`,
  `fix_first_repeated_preflight_wait_after_paired_cached_windows`, and
  `non_counted_no_artifact_live_preflight_validation`
  (8 post-closeout rows from `countedness`; plus 1 match via
  `reviewer_decision`);
- `reviewer_decision` contains the literal substring `preflight`
  (case-insensitive);
- `countedness` is exactly `non_counted_no_artifact_live_preflight_validation`
  (explicitly listed so the row is never silently dropped into
  `unclassified_v0` if substring matching is later tightened).

Evidence priority for `preflight_gap` is **P2** on the above grounds; no
row requires free-text `notes` matching to classify. The reserved
`preflight_gap` entry has therefore been moved out of §4.2.B and promoted
into Tier 1 above.

#### 4.2.A.2 Tier 1 Classification Priority (de-duplication)

Each ledger row is classified into **exactly one** Tier 1 archetype. The
classifier walks the priority list below top-to-bottom and emits the first
match. Later entries are considered only if all earlier ones failed.

1. `preflight_gap` — match rule per §4.2.A.1. This is intentionally above
   generic blocker-code families because current preflight rows may also carry
   blocker codes such as `insufficient_cached_window_context`, `timeout`, or
   `no_material_change`. A row whose `countedness` reads
   `fix_first_preflight_refresh_gap` or
   `non_counted_no_artifact_live_preflight_validation` lands in
   `preflight_gap` exactly once and is **not** additionally counted in
   `cached_window_integrity`, `drafting_timeout`, `drafting_no_change`, or
   `fix_first_evidence`.
2. `cached_window_integrity` — `blocker_code` match per §4.2.A.
3. `drafting_timeout` — `blocker_code` match per §4.2.A, or bundle-side
   `failure.code=request_timed_out`.
4. `drafting_no_change` — `blocker_code` match per §4.2.A.
5. `write_policy_block` — `blocker_code` match per §4.2.A.
6. `timeout_family_no_bundle` — `reviewer_decision` match per §4.2.A.
7. `verifier_config_evidence` — `reviewer_decision` match per §4.2.A.
8. `measurement_process_gap` — `reviewer_decision` match per §4.2.A.
9. `live_finish_gate_validation` — `reviewer_decision` match per §4.2.A.
10. `no_change_non_calibration` — `reviewer_decision` match per §4.2.A.
11. `positive_outcome_v0` — two-step match rule per §4.2.D: Step 1
    excludes any row whose `countedness` starts with `fix_first_` or
    equals `counted_fix_first_blocker`; Step 2 matches the remaining
    rows against the positive `countedness` / `reviewer_decision`
    enumerations. A row that passes Step 1 but does not match Step 2
    falls through to later slots. Intentionally placed **before**
    `fix_first_evidence` so the `positive_*` countedness values never
    collide with the fix-first fallback, and Step 1 keeps the inverse
    collision (fix-first `countedness` + positive-looking
    `reviewer_decision` such as `approve_commit`) impossible.
12. `fix_first_evidence` — fallback: `countedness` starts with
    `fix_first_` (or equals `counted_fix_first_blocker`) and none of
    slots 1-11 matched. This label is therefore the *non-preflight,
    non-timeout, non-positive, non-blocker-family* remainder of the
    fix-first cohort.
13. `drafting_other` — strict compiler-bundle fallback: matches only
    rows that have a `replay_bundle_path` pointing at a compiler bundle
    **and** a non-null `blocker_code` that is not in the Tier 1
    enumerations at slots 2–5. No row in the current 127-row closeout
    ledger satisfies this predicate, so slot 13 emits 0 against
    closeout. The five unrecognised `blocker_code` values that do
    appear post-closeout (`work_already_running`,
    `session_accounting_gap_external_patch`,
    `write_ready_structural_tokenize_indentation_crash`,
    `write_ready_preflight_adjacent_tail_read_wait_loop`,
    `recent_read_file_windows_missing_next_line_for_tail_refresh`) all
    live on non-bundle rows and are therefore **not** slot-13
    examples: rows 122, 125, and 126 route to `fix_first_evidence` at
    slot 12 (via `countedness=fix_first_remediation`); rows 36 and 119
    route to `unclassified_v0` at slot 15 (non-`fix_first_*`
    countedness). See the `drafting_other` row in §4.2.A for the full
    grounding. Slot 13 stays declared so a future genuine
    compiler-bundle + unrecognised-blocker row has a Tier 1 home
    without a `classifier_version` bump; when it does emit, the
    cockpit renders a `drafting_other_warning` naming the unrecognised
    code.
14. `model_failure_other` — `work-loop-model-failure` bundle fallback.
15. `unclassified_v0` — no rule matched. Always emits a warning with the
    row-ref and the fields that failed to match.

The classifier must expose this priority list explicitly in the `--json`
output (see §6.3: `derived.classifier_priority`) so operators can audit
the order without re-reading this document.

#### 4.2.B Tier 2 — Reserved / Provisional Archetypes

These labels are *declared but not active* in v0. They will activate only
when a matching canonical field appears in the ledger or bundles. Reviewers
and operators must not treat them as evidence of coverage.

| Archetype | Why reserved | Trigger that would activate it |
|---|---|---|
| `drafting_refusal` | no current ledger row has `blocker_code=model_returned_refusal` and no bundle has validator `code=model_returned_refusal` | any such row appears |
| `drafting_off_schema` | no current ledger row has `blocker_code=model_returned_non_schema` | any such row appears |
| `model_refused` | no current `work-loop-model-failure` report has `failure.code=model_refused` | any such report appears |
| `task_frontier_drift` | current ledger has no P1/P2 evidence | `reviewer_decision` or `countedness` explicitly names drift |
| `context_session_drift` | current ledger has no P1/P2 evidence | as above |
| `replay_tool_drift` | current ledger has no P1/P2 evidence | as above |
| `approval_review_drift` | current ledger has no P1/P2 evidence | as above |
| `ui_channel_drift` | current ledger has no P1/P2 evidence | as above |

All five drift axes from section 4.3 are reserved archetypes in v0 and are
listed above for consistency with the cockpit drift view. Section 5.1.5
still renders `count=0` lines for them so silence is impossible.

#### 4.2.C Boundary For Tier Promotion

A reserved archetype promotes to active only during a bounded refresh
slice (historically the M6.11 closeout refresh; post-closeout, an
explicit reviewer-signed expansion slice). A classifier bump from
`m6_12.v0` to `m6_12.v1` is required whenever the Tier 1 list changes.

#### 4.2.D Post-Closeout Positive-Outcome Cohort (out-of-scope for failure archetypes)

The post-closeout refresh revealed a significant cohort of **successful
calibration rows** that the failure-science v0 taxonomy is not designed
to classify. These rows are canonical evidence and must not be dropped,
but they are **not** failures and therefore cannot be pressed into any
Tier 1 failure archetype.

v0 recognises this cohort by explicit enumerations on both sides of
the row plus a hard exclusion rule, so it cannot accidentally absorb
ambiguous `fix_first_*` rows:

**Step 1 — Exclusion guard (always runs first).** A row is excluded
from `positive_outcome_v0` regardless of any other match if either:

- `countedness` starts with `fix_first_` (e.g. `fix_first_remediation`,
  `fix_first_preflight_refresh_gap`, `fix_first_remediation`'s
  approve-commit siblings rows 122/125/126 in the closeout ledger), or
- `countedness` is exactly `counted_fix_first_blocker`.

These rows record that a fix-first gate fired, which is a calibration
signal about an upstream failure, not a positive outcome. They continue
down the §4.2.A.2 priority list and land in an earlier
blocker-code / preflight archetype or in `fix_first_evidence` at slot
12. The guard closes the earlier "either side matches" loophole where
`reviewer_decision=approve_commit` paired with `fix_first_remediation`
was being absorbed into `positive_outcome_v0`.

**Step 2 — Inclusion match (only after Step 1 passes).** A non-excluded
row matches `positive_outcome_v0` if either:

- `countedness` is in the positive-countedness set:
  - `positive_verifier_backed_no_change` (26 rows),
  - `positive_paired_patch_verifier` (10 rows),
  - `current_head_positive_verifier_backed_no_change` (2 rows),
  - `positive_test_only_patch_verifier` (2 rows),
  - `positive_current_head_paired_dry_run_applied_verified_after_reasoning_policy_fixes` (1 row, row 69 in the closeout ledger),
  - `positive_current_head_paired_dry_run_applied_verified_after_cached_ref_hydration_fix` (1 row, row 72 in the closeout ledger);
- **or** `reviewer_decision` is in the positive-reviewer set:
  - `approved_positive_paired_patch_verifier` (3 rows),
  - `approved_current_head_positive_verifier_backed_no_change` (2 rows),
  - `approved_positive_current_head_fix_evidence_apply_and_verify` (1 row, row 69),
  - `approved_positive_current_head_cached_ref_hydration_write_ready_path` (1 row, row 72),
  - `approve_counted_paired_patch` (1 row),
  - `approve_counted_test_only_patch` (1 row).

The two explicit additions
(`positive_current_head_paired_dry_run_applied_verified_after_*` and
`approved_positive_current_head_*`) are the fix for the under-capture
the closeout-refresh reviews flagged: rows 69 and 72 now land in
`positive_outcome_v0` instead of falling through to `unclassified_v0`.

**Deliberately omitted reviewer_decision values:** `accept_no_change`,
`accept_recovered_no_change`, and `approve_commit`. These values appear
on both positive rows (where `countedness` already starts with
`positive_*` and therefore matches the inclusion set) and on fix-first
rows (where they must not trigger a positive match). v0 does not use
them as inclusion signals; rows where one of these is the only positive
evidence are classified by their `countedness` or fall through the
priority list and land in `fix_first_evidence` or earlier failure
archetypes as appropriate. In the closeout ledger, every row where one
of these three values *would* have matched under the old "either side"
rule also matches the `countedness` inclusion set, so no positive row
is lost.

**Post-priority emit.** Under the fixed rule the closeout ledger
classifies **42 rows** as `positive_outcome_v0` (zero `fix_first_*`
leaks, rows 69 and 72 both captured). The raw inclusion-match set also
has 42 rows; the guard catches the 3 previous fix-first leaks before
Step 2 ever evaluates. See §4.2.A for the full raw-vs-post-priority
summary.

v0 rule for the positive cohort:

- route matches to a dedicated non-failure label `positive_outcome_v0`;
- place `positive_outcome_v0` at §4.2.A.2 priority slot 11
  (immediately *before* `fix_first_evidence` at slot 12) so the
  `positive_*` countedness values never collide with any `fix_first_*`
  fallback; the guard in Step 1 above keeps the inverse collision
  (fix-first `countedness` + positive-looking `reviewer_decision`)
  impossible as well;
- render the counted total in the text cockpit as a one-line
  `positive_outcome_v0: counted=<N>` entry under the Summary line,
  **not** in the subsystem heatmap or recurrence view (both of which
  remain failure-focused);
- the actual enumeration of positive countedness / reviewer-decision
  values is frozen from the post-closeout ledger for v0. Any *new*
  positive-outcome value in a future slice falls through to
  `positive_outcome_v0_other` with a warning, and its promotion into
  the main list is a reviewer-signed slice.

A richer positive-outcome taxonomy (e.g. separating verifier-green
no-change from approved-commit delta) is explicitly **deferred to v1**
alongside the threshold work in §11.2. v0's job is to avoid
mis-classifying these rows as failures or silently dropping them.

### 4.3 v0 Drift Axes (derived, reserved)

Per the external memo, `drift` is a first-class calibration family. `M6.12`
v0 declares the five drift axes so the cockpit's drift view has a fixed
vocabulary, but all five axes are **reserved** in v0 per section 4.2.B:

- `task_frontier_drift`
- `context_session_drift`
- `replay_tool_drift`
- `approval_review_drift`
- `ui_channel_drift`

The reason they are reserved in v0: the current ledger does not carry
P1/P2 evidence for drift. Matching signals appear only in free-text
`notes` / `non_counted_reason` (P3), and the external memo explicitly
warns against inferring drift from prose.

v0 therefore renders every drift axis with `count=0 (reserved)` in the
cockpit (section 5.1.5) so silence is impossible, and promotes an axis to
active only when a `reviewer_decision` or `countedness` value
unambiguously names one (classifier bump to `m6_12.v1`). Coverage of
drift is a post-closeout expansion task (section 11.2).

### 4.4 Subsystem Tags

`subsystem_tag` maps each row to a mew-native surface using `scope_files`:

- `scope_files` contains `src/mew/patch_draft.py` or
  `tests/test_patch_draft.py` → `patch_draft_compiler`
- `scope_files` contains `src/mew/work_loop.py` or
  `tests/test_work_session.py` → `work_loop`
- `scope_files` contains `src/mew/dogfood.py` or `tests/test_dogfood.py`
  → `dogfood_compiler_replay`
- otherwise → `other_<first-matching-file-stem>`

The label `work_loop` may sub-label further from `countedness` (e.g.
`work_loop.pre_active_todo_planning`) but sub-labels are v0-optional.

### 4.5 Boundary Rules

Classifier v0 must respect:

- **countedness-aware counts**: every aggregate (e.g. "current-head incidence")
  must restrict to `counted=true` rows unless the operator explicitly asks
  for non-counted views
- **cohort fences**: do not mix `current_head`, `legacy`, and `unknown`
  cohorts in the same operator claim (reuse
  [src/mew/proof_summary.py](../src/mew/proof_summary.py) `_cohort_label`)
- **minimum-N discipline**: claims like "dominant failure family on
  current_head" must declare the counted-N behind them; v0 refuses to name a
  dominant family if counted-N is below a small floor (the floor value is
  deferred to the M6.12 plan — do not pick one before M6.11 closes)

## 5. Operator Report / Cockpit Design

The cockpit is a single-screen textual report. It is not a TUI. It is meant to
be readable in the same place as `mew proof-summary` output today.

### 5.1 Sections (v0)

In order:

1. **Header** — artifact dir, ledger path, classifier version, active
   `mode` (`pre_closeout` or `post_closeout`, per §8.5.1), current-head
   short sha, measurement head if set, ledger row count. When mode is
   `post_closeout`, the header must also print the `closeout_index` path.
2. **Summary line** — one-liner with counted/non-counted totals per cohort.
3. **Subsystem heatmap** — counted-row breakdown per `subsystem_tag` with
   archetype mix.
4. **Recurrence view** — for each `subsystem_tag`, the number of distinct
   heads on which it shows up as counted, and the top two archetypes by
   counted incidence.
5. **Drift view** — per drift axis, counted row count and sample
   `task_id`/`review_doc`. If a drift axis has zero rows, it still prints as
   `count=0` — silence is not allowed.
6. **Calibration rates** — off-schema rate, refusal rate, malformed-relevant
   counts, and dominant-share, reusing the existing math from
   [src/mew/proof_summary.py](../src/mew/proof_summary.py).
7. **Before/after comparator** — optional; requires two
   `--measurement-head`-style anchors. Shows the delta in each archetype's
   counted count between the two anchors, flagged as `moved`, `reduced`,
   `converted` (class changed, subsystem didn't), or `hidden`
   (counted count dropped but `non_counted` under an evasive reason rose).
8. **Non-counted concentration** — top `non_counted_reason` strings and top
   `countedness` values, with row-ref pointers.
9. **Warnings** — every derived label whose evidence is weaker than rule
   4.1(3) is listed here, with `row_ref` and `bundle_ref`. This is how the
   operator knows when to distrust v0.

### 5.2 Single-Screen Discipline

Each section gets a maximum row cap (v0 suggestion: 8 rows per section). Any
overflow is indicated with a trailing `+ N more (see --expand)` line. The full
expanded output is available via a flag, not default.

### 5.3 Interaction With `proof-summary --strict`

`M6.12` output must not change the pass/fail semantics of
`proof-summary --strict`. The cockpit is advisory. If a `M6.12` aggregate
violates a proposed threshold, it renders a `review` tag, but it does not fail
the existing strict gate. Thresholds that would fail `--strict` are deferred
to post-closeout (section 11.2).

## 6. Proposed CLI Surface

`M6.12` ships exactly one new CLI surface for v0: a mode flag on the
existing `mew proof-summary` subcommand. No new entry point, no new
subcommand, no alternative shape.

Existing `mew proof-summary` CLI (verified in
[src/mew/cli.py](../src/mew/cli.py) and
[src/mew/commands.py](../src/mew/commands.py)):

- positional `artifact_dir`
- top-level flags: `--json`, `--strict`
- mode flag: `--m6_11-phase2-calibration` (reinterprets `artifact_dir` as a
  replay-root and dispatches to
  `summarize_m6_11_replay_calibration()`)
- contextual flag: `--measurement-head <sha>` (additive cohort for M6.11 mode)

### 6.1 MVP Surface (v0)

```
mew proof-summary <artifact_dir> --m6_12-report [--ledger <path>]
                                                [--closeout-index <path>]
                                                [--measurement-head <sha>]
                                                [--cohort <name>]
                                                [--since <date|head>]
                                                [--diff <head-a>..<head-b>]
                                                [--expand]
                                                [--json] [--strict]
```

- `artifact_dir` (positional, reused) — bundle root. Interpreted per the
  active mode (§8.5.1):
  - **pre-closeout mode (default):** local replay root, typically
    `.mew/replays/work-loop`;
  - **post-closeout mode (when `--closeout-index` is set):** the closeout
    export root, recommended `proof-artifacts/m6_11_closeout_replay_bundles/`.
- `--m6_12-report` — new mode flag on top of the existing subcommand.
  Switches dispatch to the M6.12 reader.
- `--ledger <path>` — ledger JSONL path. Defaults to
  `proof-artifacts/m6_11_calibration_ledger.jsonl`. Only meaningful under
  `--m6_12-report`.
- `--closeout-index <path>` — **controls mode detection (§8.5.1.1).**
  - absent → pre-closeout mode, pre-closeout resolver (§8.5.1.2);
  - present → post-closeout mode, post-closeout resolver (§8.5.1.3). The
    file must exist, parse as JSON, and conform to the schema in §8.5.2.
    Any failure fails closed immediately; the reader never silently falls
    back to pre-closeout.
- `--measurement-head <sha>` — reused verbatim from the M6.11 mode.
- `--cohort <current_head|legacy|unknown|measurement_head>` — single-cohort
  view filter. Optional; default prints all cohorts.
- `--since <date|head>` — ledger row filter. Optional.
- `--diff <head-a>..<head-b>` — renders only section 5.1.7 (comparator).
  Post-MVP optional.
- `--expand` — drops the per-section row cap. Post-MVP optional.
- `--json`, `--strict` — reused verbatim from the existing top-level flags.
  `--strict` semantics are unified across modes per §8.5.6.

Rationale for reusing `proof-summary`:

- The positional `artifact_dir` already means "replay-root" under
  `--m6_11-phase2-calibration`; reusing that contract for the new mode keeps
  one mental model.
- `summarize_m6_11_replay_calibration()` already owns cohort labeling and
  bundle math. The M6.12 reader composes over it instead of forking it.
- No alternate subcommand naming has to be locked in before closeout.

### 6.2 Mode Coexistence And Dispatch Rules

- Exactly one top-level mode flag may be set. Passing both
  `--m6_11-phase2-calibration` and `--m6_12-report` is a CLI argument error
  (fail fast, exit non-zero).
- `--closeout-index` is an **M6.12-only** flag. It is ignored by the default
  dogfood summarizer and by `--m6_11-phase2-calibration` mode. Passing
  `--closeout-index` without `--m6_12-report` is a CLI argument error.
- Default mode (neither flag) keeps its current behavior: treat
  `artifact_dir` as a dogfood artifact directory and dispatch
  `summarize_proof_artifacts`.
- `--m6_11-phase2-calibration` mode is unchanged. The M6.11 close gate
  continues to use it as the authoritative green check. M6.12 does not
  modify its math, its output, or its exit code.
- `--m6_12-report` mode reads the ledger via `--ledger` and the bundle root
  via `artifact_dir`. The presence of `--closeout-index` selects which of
  the two resolvers (§8.5.1.2 vs §8.5.1.3) is invoked per row. The
  resolver selection is atomic per invocation; cross-mode fallback is
  forbidden (§8.5.1.4).
- `--measurement-head` is respected by both top-level modes with identical
  semantics.
- `--strict` in `--m6_12-report` returns non-zero whenever (a)
  `canonical.bundle_provenance.missing > 0`, or (b) in post-closeout mode,
  the closeout index cannot be loaded or validated, or (c) a derived
  aggregate violates a threshold that v1 may add post-closeout. v0 ships
  no such threshold, so (a) and (b) are the only v0 triggers. See §8.5.6
  for the unified strict-mode rule.

### 6.3 JSON Contract

The `--json` output under `--m6_12-report` separates canonical from derived
explicitly:

```json
{
  "classifier_version": "m6_12.v0",
  "generated_at": "...",
  "subcommand_mode": "m6_12_report",
  "canonical": {
    "mode": "pre_closeout | post_closeout",
    "ledger_path": "...",
    "ledger_rows": N,
    "cohorts": {...},
    "bundles": {...},
    "bundle_provenance": {
      "mode": "pre_closeout | post_closeout",
      "root": "...",
      "closeout_index": null | "...",
      "referenced": N,
      "resolved": N,
      "missing": N,
      "missing_row_refs": [
        {"row_ref": "ledger:#NN", "reason": "precloseout_missing | closeout_index_miss | closeout_export_missing | closeout_export_sha_mismatch"}
      ]
    }
  },
  "derived": {
    "classifier_priority": [
      "preflight_gap", "cached_window_integrity", "drafting_timeout",
      "drafting_no_change", "write_policy_block", "timeout_family_no_bundle",
      "verifier_config_evidence", "measurement_process_gap",
      "live_finish_gate_validation", "no_change_non_calibration",
      "positive_outcome_v0", "fix_first_evidence", "drafting_other",
      "model_failure_other", "unclassified_v0"
    ],
    "archetypes_active": [...],
    "archetypes_reserved_seen": [...],
    "drift_axes": [...],
    "subsystems": [...],
    "comparator": {...}
  },
  "warnings": [...]
}
```

- `canonical.mode` and `canonical.bundle_provenance.mode` are both
  required and must match; operators and CI consumers read whichever is
  closer at hand.
- `canonical.bundle_provenance.closeout_index` is `null` in pre-closeout
  mode and must be the path passed via `--closeout-index` in
  post-closeout mode.
- `canonical.bundle_provenance.missing_row_refs[].reason` carries the
  mode-specific sub-code from §8.5.4 so callers can audit what kind of
  miss occurred (pre-closeout absence vs closeout index miss vs export
  file missing vs sha mismatch).
- `canonical.bundle_provenance` is required (see section 8.5) and is how a
  caller tells ledger-only aggregates from bundle-derived rates.
- `derived.classifier_priority` is the literal ordered list from
  §4.2.A.2; the reader always emits it so operators do not need to
  cross-reference this document to audit archetype selection.
- `derived.archetypes_active` lists only Tier 1 archetypes (section 4.2.A).
  Each archetype entry carries `label`, `cohort`, `counted`,
  `evidence_priority`, `row_refs`, and `bundle_refs`.
- `derived.archetypes_reserved_seen` is empty unless a reserved archetype
  actually matched a row (in which case promotion discussion belongs in a
  review doc, not an in-place ledger edit).
- Every derived row carries `row_refs` and `bundle_refs` pointing back to
  canonical evidence.

### 6.4 Post-MVP Surface Promotion (deferred)

A dedicated top-level command (`mew calibration report` or similar) is a
post-closeout candidate only. It is tracked in section 11.2 as a naming
decision to defer. The MVP does not add it.

## 7. Representative Output Examples

The examples below are illustrative. Row counts reflect the post-M6.11
closeout ledger shape (127 rows total, 65 counted, 62 non-counted, 99
unique heads, 30 rows with a `replay_bundle_path`, 97 without). The
per-section aggregates shown (e.g. "counted=3 non_counted=6" on a
cohort line) are *shape* examples and will be recomputed by the
classifier implementation; they are not a commitment to final numbers.
The pre-closeout example in §7.1 is retained because pre-closeout mode
remains a valid invocation for hosts that still have local
`.mew/replays/**` bundles from the in-flight M6.11 slice; the
post-closeout example in §7.4 is now the canonical operator citation
mode.

### 7.1 Default text output (pre-closeout, current-head cohort, all bundles resolved)

Invocation:

```
mew proof-summary .mew/replays/work-loop --m6_12-report \
    --ledger proof-artifacts/m6_11_calibration_ledger.jsonl
```

Output:

```
Proof summary (M6.12): artifact_dir=.mew/replays/work-loop
ledger: proof-artifacts/m6_11_calibration_ledger.jsonl
classifier_version: m6_12.v0
mode: pre_closeout
cohort: current_head   head: <current-sha>   ledger_rows: 127

bundle_provenance: mode=pre_closeout root=.mew/replays/work-loop referenced=30 resolved=30 missing=0

# Per-cohort counted/non_counted breakdown is a classifier-implementation
# output; the line below is a shape placeholder. Totals across cohorts
# must sum to ledger_rows (127) under the discipline in §4.5.
summary: current_head counted=<n> non_counted=<n> | legacy counted=<n> non_counted=<n> | unknown counted=<n> non_counted=<n>

subsystem_heatmap:
  patch_draft_compiler        counted=2  top=cached_window_integrity(2), drafting_no_change(0)
  work_loop                   counted=3  top=drafting_timeout(3), preflight_gap(0)
  dogfood_compiler_replay     counted=0  top=- (no current-head rows)

recurrence:
  patch_draft_compiler        heads_seen=4  top_archetypes=cached_window_integrity, drafting_timeout
  work_loop                   heads_seen=2  top_archetypes=drafting_timeout, preflight_gap

drift:
  task_frontier_drift         count=0    (reserved)
  context_session_drift       count=0    (reserved)
  replay_tool_drift           count=0    (reserved)
  approval_review_drift       count=0    (reserved)
  ui_channel_drift            count=0    (reserved)

calibration_rates (bundle-derived):
  off_schema=0.0000 (0/2)
  refusal=0.0000 (0/3)
  dominant_share=1.0000 (drafting_timeout)
  malformed_relevant=0

comparator (06167a9b..54b657a):
  drafting_timeout            counted moved +2
  preflight_gap               counted moved +1
  cached_window_integrity     counted unchanged
  measurement_process_gap     non_counted reduced -1

non_counted_concentration:
  no replay bundle emitted                                       x3
  model planning failed with Codex Web API error: cannot read... x2

warnings:
  reserved archetype declared but not activated in v0: drafting_refusal, drafting_off_schema, model_refused,
                                                       <5 drift axes>
```

Strict-exit note: the invocation above with `--strict` appended would
also exit zero because `bundle_provenance.missing=0`. The unified rule
in §8.5.6 only fails closed when at least one bundle is missing.

### 7.2 JSON excerpt (`--json`, pre-closeout, abbreviated)

```json
{
  "classifier_version": "m6_12.v0",
  "subcommand_mode": "m6_12_report",
  "canonical": {
    "mode": "pre_closeout",
    "ledger_path": "proof-artifacts/m6_11_calibration_ledger.jsonl",
    "ledger_rows": 127,
    "cohorts": {
      "current_head": {"total_bundles": "<n>", "relevant_bundles": "<n>", "off_schema_rate": "<rate>"}
    },
    "bundles": {"patch_draft_compiler": "<n>", "work-loop-model-failure": "<n>"},
    "bundle_provenance": {
      "mode": "pre_closeout",
      "root": ".mew/replays/work-loop",
      "closeout_index": null,
      "referenced": 30,
      "resolved": 30,
      "missing": 0,
      "missing_row_refs": []
    }
  },
  "derived": {
    "classifier_priority": [
      "preflight_gap", "cached_window_integrity", "drafting_timeout",
      "drafting_no_change", "write_policy_block", "timeout_family_no_bundle",
      "verifier_config_evidence", "measurement_process_gap",
      "live_finish_gate_validation", "no_change_non_calibration",
      "positive_outcome_v0", "fix_first_evidence", "drafting_other",
      "model_failure_other", "unclassified_v0"
    ],
    "archetypes_active": [
      {"label": "drafting_timeout", "cohort": "current_head", "counted": 3,
       "evidence_priority": "P1",
       "subsystem_tags": ["work_loop"],
       "row_refs": ["ledger:#63", "ledger:#64", "ledger:#65"],
       "bundle_refs": ["<artifact_dir>/.../report.json"]}
    ],
    "archetypes_reserved_seen": [],
    "drift_axes": [
      {"axis": "task_frontier_drift", "count": 0, "status": "reserved"},
      {"axis": "context_session_drift", "count": 0, "status": "reserved"},
      {"axis": "replay_tool_drift", "count": 0, "status": "reserved"},
      {"axis": "approval_review_drift", "count": 0, "status": "reserved"},
      {"axis": "ui_channel_drift", "count": 0, "status": "reserved"}
    ],
    "comparator": {
      "anchors": ["06167a9b", "54b657a"],
      "moves": [{"archetype": "drafting_timeout", "delta": 2, "kind": "moved"}]
    }
  },
  "warnings": [
    {"kind": "reserved_archetype_inactive", "label": "drafting_refusal",
     "reason": "no current ledger row carries matching canonical evidence"}
  ]
}
```

### 7.3 Missing-bundle example (pre-closeout fresh checkout)

Invocation on a fresh checkout whose ledger rows reference
`.mew/replays/…` paths that do not exist locally. `--closeout-index` is
*not* passed, so the reader runs in pre-closeout mode per §8.5.1.1.

```
mew proof-summary .mew/replays/work-loop --m6_12-report
```

Output excerpt (see §8.5 for the full rule set):

```
mode: pre_closeout
bundle_provenance: mode=pre_closeout root=.mew/replays/work-loop referenced=30 resolved=0 missing=30
calibration_rates (bundle-derived): SUPPRESSED (bundle_provenance.missing > 0)
warnings:
  bundle_provenance_missing: 30 rows reference bundles under .mew/replays/work-loop
  that did not resolve via the pre-closeout resolver (reason=precloseout_missing);
  ledger-only archetype counts remain valid; bundle-derived rates are suppressed
```

Exit codes (unified rule, §8.5.6):

- without `--strict`: **exit 0**. The suppression rule in §8.5.5 still
  fires, missing-bundle warnings are still emitted, and the operator is
  told the mode plainly.
- with `--strict`: **exit non-zero** because
  `canonical.bundle_provenance.missing > 0`. This is identical to the
  post-closeout strict failure and does not depend on mode.

### 7.4 Post-closeout example (authoritative citation — canonical v0 mode)

M6.11 is closed. The canonical M6.12 citation invocation runs against
the closeout export tree and the closeout replay index. This example
shows the shape the reader should produce against the current 127-row
post-closeout ledger. Concrete counts under `referenced` / `resolved`
depend on the export step (§8.2) populating the tree; the 30
bundle-carrying rows in the current ledger are the upper bound.

```
mew proof-summary proof-artifacts/m6_11_closeout_replay_bundles \
    --m6_12-report \
    --closeout-index proof-artifacts/m6_11_closeout_replay_index.json \
    --ledger proof-artifacts/m6_11_calibration_ledger_closeout.jsonl \
    --strict
```

Text header:

```
Proof summary (M6.12): artifact_dir=proof-artifacts/m6_11_closeout_replay_bundles
ledger: proof-artifacts/m6_11_calibration_ledger_closeout.jsonl
closeout_index: proof-artifacts/m6_11_closeout_replay_index.json
classifier_version: m6_12.v0
mode: post_closeout
cohort: current_head   head: <closeout-sha>   ledger_rows: 127

bundle_provenance: mode=post_closeout root=proof-artifacts/m6_11_closeout_replay_bundles
                   closeout_index=proof-artifacts/m6_11_closeout_replay_index.json
                   referenced=30 resolved=30 missing=0
```

JSON fragment (abbreviated) showing the additional post-closeout fields:

```json
{
  "canonical": {
    "mode": "post_closeout",
    "ledger_rows": 127,
    "bundle_provenance": {
      "mode": "post_closeout",
      "root": "proof-artifacts/m6_11_closeout_replay_bundles",
      "closeout_index": "proof-artifacts/m6_11_closeout_replay_index.json",
      "referenced": 30, "resolved": 30, "missing": 0,
      "missing_row_refs": []
    }
  }
}
```

Failure cases in post-closeout mode:

- If `--closeout-index` points at a missing, unreadable, or malformed
  file, the reader exits non-zero **before** classification begins (even
  without `--strict`), per §8.5.1.1.
- If a ledger row's `replay_bundle_path` is not in the index, the row is
  recorded with `reason=closeout_index_miss` in `missing_row_refs`.
- If the index entry's `export_path` points at a file that is absent,
  the reason is `closeout_export_missing`.
- If sha verification fails, the reason is `closeout_export_sha_mismatch`.
- In all three of the above cases, `--strict` fails closed per §8.5.6.

## 8. M6.11 Closeout Refresh Contract

`M6.11` is now closed. This section defines the single-step refresh the
M6.12 reader relies on. It is retained as a normative contract (not
just a historical note) for two reasons:

- the closeout *export* step that produces the post-closeout replay
  tree and index is still a concrete deliverable the M6.12 plan
  depends on (see §8.2 and §9.11);
- if M6.11 ever has to be reopened for a follow-up correction, the
  same contract applies to a second closeout cycle.

The ledger snapshot already exists at
`proof-artifacts/m6_11_calibration_ledger.jsonl` (127 rows at the
closeout boundary). The remaining closeout deliverables are the
bundle export tree and index described in §8.2.

### 8.1 Trigger

The refresh runs exactly once per closure, on the commit that flips
`M6.11` to `done`. If the ledger is later reopened for a follow-up
correction, the contract is re-run against that new closure commit;
it is never run twice against the same closure.

### 8.2 Refresh Actions (in order)

1. Snapshot `proof-artifacts/m6_11_calibration_ledger.jsonl` into
   `proof-artifacts/m6_11_calibration_ledger_closeout.jsonl` (byte-identical).
2. Export every referenced replay bundle under
   `proof-artifacts/m6_11_closeout_replay_bundles/` per the bundle
   provenance rules in section 8.5. No bundle content is rewritten; the
   export copies `replay_metadata.json` / `report.json` and any sibling
   files the existing reader consumes (see
   [src/mew/proof_summary.py](../src/mew/proof_summary.py)
   `_read_validator_result` for the `validator_result.json` case).
3. Write the closeout index
   `proof-artifacts/m6_11_closeout_replay_index.json`, keyed by
   `replay_bundle_path` (the original local path), with at minimum:
   `original_path`, `export_path`, `sha256`, `size_bytes`,
   `exported_at`.
4. Freeze `classifier_version` = `m6_12.v0` against this snapshot; any future
   classifier change bumps to `m6_12.v1` and reproduces v0 output side-by-side
   for one release so regressions are visible.
5. Re-run the archetype mapping end-to-end against the closeout snapshot and
   record per-archetype counted-N in
   `docs/M6_12_CLASSIFIER_V0_CALIBRATION.md` (a new reference doc, not a
   ledger file).
6. Diff the closeout archetype distribution against the final in-flight
   distribution. Any archetype whose counted-N changes by more than one
   during closeout must be inspected manually before release.
7. Re-evaluate the v0 drift tags. Any drift tag that was inferred from
   `notes` prose becomes `warnings` until a reviewer upgrades it.
8. Only after steps 1-7 pass, propose threshold floors (see section 11.2).
   Do not commit thresholds into the code path before this step.

### 8.3 Closeout Non-Goals

- Do not rewrite ledger rows.
- Do not renumber `countedness` values.
- Do not merge external archetype names into any ledger or bundle field.
- Do not retroactively re-adjudicate `reviewer_decision` during closeout.
- Do not mutate original replay bundles under `.mew/replays/**` during the
  export step; the export is a copy, and the original tree may be pruned
  safely afterward without invalidating the frozen index.

### 8.4 Evidence Required For Closeout Refresh

- byte-identical ledger snapshot exists
- replay-bundle export tree resolves every `replay_bundle_path` to a file
  under `proof-artifacts/m6_11_closeout_replay_bundles/` and the closeout
  index records a matching sha
- `classifier_version=m6_12.v0` reproduces archetype counts from the snapshot
  deterministically twice, sourcing bundles only from the export tree
- `mew proof-summary --m6_11-phase2-calibration` remains green on the
  frozen cohort, with `artifact_dir` pointed at the export tree

### 8.5 Bundle Provenance, Retention, And Missing-Bundle Rules

This subsection is load-bearing. Without it the M6.12 reader can silently
produce different rates on different hosts because `replay_bundle_path`
values in the ledger are local to the machine that produced them.

#### 8.5.1 Mode Detection And Resolver Selection

The M6.12 reader operates in exactly one of two modes per invocation, and
the mode is part of the MVP contract. Mode is decided **deterministically**
from CLI flags; there is no implicit mode inference.

##### 8.5.1.1 Mode-Detection Rule (MVP contract)

- **Post-closeout mode** is entered **iff** the caller passes
  `--closeout-index <path>` on the CLI. In that case the reader:
  1. Opens the path. If the file is missing, unreadable, or fails JSON
     parsing, the reader **fails closed**: exits non-zero (or raises, for
     library callers) with an explicit error naming the path and reason.
     It does **not** fall back to pre-closeout resolution.
  2. Validates that every entry carries the index schema required by
     §8.5.2 (`original_path`, `export_path`, `sha256`, `size_bytes`,
     `exported_at`). Any malformed entry fails closed.
  3. Selects the **post-closeout resolver** (§8.5.1.3) for every ledger
     row with a non-null `replay_bundle_path`.
- **Pre-closeout mode** is the default. It applies whenever
  `--closeout-index` is not set. The reader:
  1. Never opens, scans for, or honors any closeout index file even if
     one happens to exist in the working tree.
  2. Selects the **pre-closeout resolver** (§8.5.1.2) for every ledger
     row with a non-null `replay_bundle_path`.

The detected mode is printed in both surfaces:

- text cockpit header: `mode: pre_closeout` or `mode: post_closeout`;
- JSON: `canonical.mode` (identical values).

##### 8.5.1.2 Pre-Closeout Resolver

Purpose: resolve local bundle paths that were written by the host that
produced the ledger row.

Inputs: `artifact_dir` (positional, required), `replay_bundle_path` from
the ledger row.

Rule, applied per row:

1. If `replay_bundle_path` is an absolute path, the resolver uses it
   verbatim.
2. Else the resolver strips, in order, the first matching prefix from
   `replay_bundle_path`:
   - the literal value of `artifact_dir` followed by `/`;
   - `.mew/replays/work-loop/` (the canonical local replay root);
   - no prefix stripped.
   The remainder (possibly equal to the original path) is joined as a
   relative path under `artifact_dir` to form the candidate file path.
3. The bundle is considered **resolved** iff the candidate file exists
   and is a regular readable file. Otherwise the row is **missing**.

Pre-closeout runs:

- set `canonical.mode = pre_closeout`;
- set `canonical.bundle_provenance.root = artifact_dir`;
- never freeze `classifier_version`; the output always includes the
  `mode` label so downstream readers can tell pre-closeout evidence from
  post-closeout evidence.

##### 8.5.1.3 Post-Closeout Resolver

Purpose: resolve bundles that live in the host-independent closeout
export tree named by §8.5.2.

Inputs: `artifact_dir` (the closeout export root), the loaded closeout
index (from `--closeout-index`), and `replay_bundle_path` from the ledger
row (the `original_path` key).

Rule, applied per row:

1. Look up the row's `replay_bundle_path` in the index as an
   `original_path` key.
   - If the key is not present in the index, the row is **missing**. The
     resolver does **not** fall back to directory scanning, filename
     matching, or the pre-closeout rule. No cross-mode fallback is
     permitted.
2. If present, take the corresponding `export_path` and resolve it
   relative to `artifact_dir` (i.e. `<artifact_dir>/<export_path>`).
   - If the resulting file does not exist, the row is **missing** and
     the reader emits a `closeout_export_missing` warning naming the
     index entry and expected path.
3. If the index entry carries a `sha256`, the resolver reads the file
   and verifies the sha. Mismatch → `missing` with a
   `closeout_export_sha_mismatch` warning. (SHA verification can be
   deferred behind `--skip-sha-check` in later versions, but is on by
   default in v0.)

Post-closeout runs:

- set `canonical.mode = post_closeout`;
- set `canonical.bundle_provenance.root` to the export root
  (`artifact_dir`);
- set `canonical.bundle_provenance.closeout_index` to the path passed
  via `--closeout-index`;
- are the only mode whose output may be cited outside the author's host
  as authoritative `M6.12` math.

##### 8.5.1.4 Cross-Mode Fallback Is Forbidden

The reader must never mix the two resolvers within a single invocation:

- Pre-closeout mode must not consult the closeout index even if one
  exists on disk.
- Post-closeout mode must not degrade to directory scanning of
  `.mew/replays/**` or to joining `replay_bundle_path` under
  `artifact_dir` if the index is absent, malformed, incomplete, or
  contains stale references.
- Both modes treat `row.replay_bundle_path is null` as "bundle-less
  evidence" (not missing); the resolver is never invoked for those rows.
- Any rule added in a future version that relaxes this separation is a
  breaking change requiring a `classifier_version` bump and a fresh
  reviewer-signed design decision.

#### 8.5.2 Export Layout

The closeout export uses a stable, host-independent layout:

```
proof-artifacts/m6_11_closeout_replay_bundles/
    <row-id>/<basename-of-replay_bundle_path>
    <row-id>/<sibling-files>
```

`<row-id>` is `ledger-<zero-padded-line-number>` so the mapping back to a
ledger row is obvious. The original relative structure under
`.mew/replays/…` is not preserved; the index file is the authoritative
reverse lookup.

#### 8.5.3 Retention Policy

- The export tree and the closeout index are both checked in under
  `proof-artifacts/` once M6.11 closes, and are never rewritten.
- `.mew/replays/**` is not checked in and may be pruned after the export
  step. The M6.12 reader must never depend on its continued existence
  post-closeout.
- Future bundles produced after closeout belong to whichever milestone
  owns them (M6.12, M6.13, …). They are not retrofitted into the M6.11
  closeout tree.

#### 8.5.4 Missing-Bundle Behavior In The Reader

The reader first selects the resolver per §8.5.1, then classifies bundle
access into three states per ledger row:

| Row class | Meaning | Reader action |
|---|---|---|
| `row.replay_bundle_path is null` | row was always bundle-less (many non-counted rows are in this state) | ledger-only aggregation applies; no `missing` warning; the resolver is not invoked |
| resolver (§8.5.1.2 or §8.5.1.3) returns **resolved** | bundle present under the mode's authoritative root | full aggregation (ledger + bundle-derived rates) |
| resolver returns **missing** | bundle not present by the rules of the active mode (pre-closeout: not under `artifact_dir`; post-closeout: not in index, export file missing, or sha mismatch) | `missing_bundle` warning with the mode-specific sub-code (`precloseout_missing`, `closeout_index_miss`, `closeout_export_missing`, `closeout_export_sha_mismatch`); bundle-derived rates suppressed for this row; ledger-only archetype count still applies |

The top-level JSON carries a required `canonical.bundle_provenance` object
(section 6.3) with `mode`, `root`, `closeout_index` (post-closeout only),
`referenced`, `resolved`, `missing`, and `missing_row_refs`.

#### 8.5.5 Rate Separation Rule

When `bundle_provenance.missing > 0`:

- `derived.archetypes_active` may still be populated from ledger-only
  evidence; those counts remain valid.
- `calibration_rates` (off-schema, refusal, malformed-relevant,
  dominant-share) are suppressed in the text output and emitted as
  `null` in JSON; the comparator section is also suppressed unless both
  anchors have `missing == 0`.
- The operator is told explicitly in the text cockpit which aggregates are
  ledger-only vs bundle-derived (see section 7.3).

#### 8.5.6 Strict-Mode Failure (unified rule)

v0 commits to one strict-mode rule that applies identically in both modes:

- `--strict --m6_12-report` exits non-zero whenever
  `canonical.bundle_provenance.missing > 0`, regardless of whether the
  active mode is `pre_closeout` or `post_closeout`.
- `--strict --m6_12-report` also exits non-zero whenever the mode is
  `post_closeout` and the reader cannot even load or validate the
  closeout index per §8.5.1.1 (index missing, unreadable, malformed, or
  schema-violating). The exit happens *before* resolver evaluation;
  `bundle_provenance.missing` may be undefined in that case, but the
  non-zero exit is still correct.
- Non-strict `--m6_12-report` runs (no `--strict`) **always exit zero**
  on missing bundles. They still emit the suppression rules from §8.5.5
  and the explicit `missing_bundle` warnings, and the operator can tell
  from `canonical.mode` and `canonical.bundle_provenance.missing` that
  bundle-derived math was suppressed.
- The unified rule reflects the meaning of `--strict`: the operator is
  asserting that the M6.12 claim is complete and authoritative. A
  missing bundle breaks that assertion identically in either mode. The
  difference between modes lives in `canonical.mode`, not in the
  strict-exit code.

Rationale for choosing "strict always fails on missing bundles" over the
earlier wording in §7.3/§8.5.6 that was ambiguous:

1. Ambiguity about `--strict` is a silent correctness bug. Operators in
   CI need one predictable rule.
2. Pre-closeout runs that want to tolerate missing bundles simply do not
   pass `--strict`; the non-strict pre-closeout invocation is the
   intended path for hosts that retain only local `.mew/replays/**`
   bundles (e.g. authors running against the pre-export state).
3. The authoritativeness of pre-closeout output is still separately
   conveyed by `canonical.mode=pre_closeout`, so no consumer will
   accidentally treat pre-closeout non-strict output as authoritative.
4. The rule composes cleanly with future v1 threshold additions: those
   can also fail `--strict` without touching mode detection.

#### 8.5.7 Forbidden Compensations

The reader must not:

- re-derive missing `blocker_code` values from bundle text on the fly;
- copy bundle content outside the closeout export path;
- silently use a different host-local replay root than the one the operator
  named;
- treat `null` `replay_bundle_path` rows as missing (they are explicit
  bundle-less evidence, not failed lookups).

## 9. Open Questions / Deferred Decisions

These are known and intentionally deferred. They must not block v0.

1. **Post-closeout command promotion.** The MVP surface is committed:
   `mew proof-summary <artifact_dir> --m6_12-report` (section 6.1). The
   open question is whether to promote it to a dedicated top-level command
   (e.g. `mew calibration report`) once there is live operator feedback
   on the post-closeout report. Still a naming and UX decision, not an
   MVP decision; no longer gated on closeout *itself* now that M6.11 is
   closed.
2. **Tier 2 archetype activation order.** When reserved labels
   (section 4.2.B) actually start matching new ledger rows, which activate
   first, and with what reviewer sign-off. This decision intentionally
   waits until the trigger fires. The post-closeout refresh did not
   trigger any reserved label promotion.
3. **Threshold floors.** Off-schema, refusal, dominant-share, counted-N,
   drift-coverage — none of these are picked here. All of them still
   depend on counts recomputed against the post-closeout 127-row
   ledger; the MVP classifier implementation produces those counts, at
   which point v1 can propose floors (section 11.2).
4. **Drift detection without prose.** v0 tags drift conservatively. A later
   pass may harvest drift from replay-bundle diffs, but that is additive.
5. **Calibration-estimate view.** The Vellum-inspired
   `calibration_feedback_drift` bucket (raw vs corrected estimate vs provider
   ground truth) requires fields the canonical ledger does not carry.
   Deferred to a v1 expansion slice now that closeout froze the
   canonical shape; see section 11.2.
6. **Context-pressure view.** Preflight/mid-loop/reducer/media-bloat
   pressure also needs new evidence channels that do not exist in the
   current ledger; treat as an `M6.12+` expansion.
7. **Queue/lifecycle visibility.** Codex-style queue-pressure / lifecycle
   transition surfaces likely need daemon-side instrumentation. `M6.12` v0
   does not promise them.
8. **Governance for downstream wiring.** Whether the `M6.12` `--json`
   contract should ever be consumed by `mew-product-evaluator`,
   `mew-adversarial-verifier`, `mew chat`, roadmap-governance surfaces, or
   any other decision-influencing consumer is an open governance question.
   v0 does not wire any such consumer; the only v0 consumer is a unit-test
   fixture (section 12.6). Resolve this question before moving to
   section 11.3.
9. **Persistence of derived labels.** v0 recomputes on every run. If a
   later version wants to cache derived labels, the cache must live outside
   `proof-artifacts/` so it cannot contaminate canonical evidence.
10. **Reviewer UX.** Whether the report should highlight rows that currently
    have weak derived labels to a reviewer, so reviewers can upgrade them via
    review docs instead of ledger edits, is deferred but recommended for v1.
11. **Closeout export execution owner.** M6.11 has closed; the ledger
    snapshot is the 127-row
    `proof-artifacts/m6_11_calibration_ledger.jsonl`. The closeout
    export tree (`proof-artifacts/m6_11_closeout_replay_bundles/`) and
    index (`proof-artifacts/m6_11_closeout_replay_index.json`) are still
    pending deliverables — the concrete export step from §8.2 has not
    yet been executed. Owner of that export is the open question.
    Until it lands, post-closeout mode (§8.5.1.3) cannot be exercised
    and operators must use pre-closeout mode against local
    `.mew/replays/**` bundles.
12. **Positive-outcome taxonomy richness.** v0 treats every row matching
    §4.2.D as a single `positive_outcome_v0` bucket. A richer v1
    taxonomy (e.g. separating verifier-green no-change from
    approved-commit delta, or separating "accept_no_change" reviewer
    approvals from fresh positive verifications) is deferred. The
    discovery of this cohort during closeout is why v0 now names the
    bucket explicitly rather than letting these rows fall into
    `unclassified_v0`.

## 10. Minimal MVP

The smallest `M6.12` that is worth shipping:

1. Add a new ledger reader
   (e.g. `src/mew/calibration_ledger.py`) that parses
   `proof-artifacts/m6_11_calibration_ledger.jsonl` into a typed row view.
   **No ledger mutation.**
2. Add a derived classifier module (e.g. `src/mew/calibration_report.py`)
   implementing section 4 rules (Tier 1 archetypes only; Tier 2 labels
   declared but inactive per section 4.2.B).
3. Wire the classifier into the single MVP CLI surface
   (`mew proof-summary <artifact_dir> --m6_12-report …`, section 6.1) and
   enforce the mutual-exclusion rule against `--m6_11-phase2-calibration`
   (section 6.2).
4. Implement the bundle provenance rules (section 8.5): every MVP run
   produces a `bundle_provenance` object with `mode`, `root`,
   `closeout_index`, `referenced`, `resolved`, `missing`, and
   `missing_row_refs[].reason`; separates ledger-only aggregates from
   bundle-derived rates; selects the pre-closeout or post-closeout
   resolver per §8.5.1 without cross-mode fallback; and applies the
   unified strict rule in §8.5.6 (non-zero exit on any
   `bundle_provenance.missing > 0` under `--strict`, regardless of mode;
   also non-zero under `--closeout-index` failures even without
   `--strict`).
5. Emit text output per section 5.1 (1, 2, 3, 5, 6, 8) — sections
   4 (recurrence), 7 (comparator), 9 (warnings) can land incrementally,
   but *drift* (section 5.1.5) must ship in the MVP even if every axis is
   `count=0 (reserved)`, because making drift visible is the whole point.
6. Tests in `tests/test_calibration_report.py` cover, at minimum:
   - canonical row parsing from `m6_11_calibration_ledger.jsonl`
   - derived archetype mapping on a checked-in fixture ledger with rows
     matching each Tier 1 archetype in section 4.2.A, including at least
     one `preflight_gap` row sourced from a `countedness` value
     containing `preflight` and one `non_counted_no_artifact_live_preflight_validation`
     row; asserts that `fix_first_evidence` does not double-count either
   - the §4.2.A.2 priority list behavior on a fixture row whose
     `countedness` would match multiple archetypes (e.g.
     `fix_first_preflight_refresh_gap` must land in `preflight_gap`, not
     `cached_window_integrity`, `drafting_timeout`, `drafting_no_change`, or
     `fix_first_evidence`)
   - the §4.2.D Step-1 exclusion guard: a fixture row with
     `countedness=fix_first_remediation` and
     `reviewer_decision=approve_commit` (and a `blocker_code` outside
     the cached-window / drafting-timeout / drafting-no-change /
     write-policy enumerations — e.g.
     `write_ready_structural_tokenize_indentation_crash`) must **not**
     land in `positive_outcome_v0`; it lands in `fix_first_evidence`
     at slot 12. Add the symmetric fixture row with
     `countedness=counted_fix_first_blocker` and assert the same
     guard behavior.
   - the §4.2.D Step-2 inclusion match on the two
     `positive_current_head_paired_dry_run_applied_verified_after_*`
     values (rows 69 and 72 in the closeout ledger) and their
     corresponding `approved_positive_current_head_*` reviewer
     decisions — both variants must land in `positive_outcome_v0` at
     slot 11 rather than falling through to `unclassified_v0`.
   - raw-match vs post-priority emit: a fixture ledger with a full
     mix of the Tier 1 match values must reproduce the post-priority
     emit totals listed in the §4.2.A "v0 classifier-output summary"
     block (e.g. `cached_window_integrity: 17`,
     `drafting_no_change: 6`, `fix_first_evidence: 3`), not the raw
     enumeration totals.
   - cohort-fenced aggregates
   - `--json` contract separation between `canonical` and `derived`,
     including `canonical.mode`, `canonical.bundle_provenance` with
     `mode`, `root`, `closeout_index`, `referenced`, `resolved`,
     `missing`, and `missing_row_refs[].reason`
   - mode detection: `--closeout-index` absent → `mode=pre_closeout`;
     `--closeout-index` present and valid → `mode=post_closeout`;
     `--closeout-index` pointing at a missing / unreadable / malformed
     file → non-zero exit before classification (covered even without
     `--strict`)
   - pre-closeout resolver (§8.5.1.2) on a fixture with one row whose
     `replay_bundle_path` starts with `artifact_dir` and one that does
     not; both must resolve correctly when the bundle exists and report
     `reason=precloseout_missing` otherwise
   - post-closeout resolver (§8.5.1.3) on a fixture with all four miss
     reasons: `closeout_index_miss`, `closeout_export_missing`,
     `closeout_export_sha_mismatch`, and the success path;
     asserts no cross-mode fallback to pre-closeout scanning
   - unified strict-mode rule (§8.5.6): with `--strict`, any
     `bundle_provenance.missing > 0` exits non-zero in both modes;
     without `--strict`, both modes exit zero
   - mutual-exclusion error when both `--m6_11-phase2-calibration` and
     `--m6_12-report` are passed, and when `--closeout-index` is passed
     without `--m6_12-report`
   - single-screen row cap and `+ N more` behavior
   - at least one Tier 2 archetype declared in output (as `reserved`)
     without being counted — i.e., the reserved/active partition is visible
     and testable
7. The MVP reuses `summarize_m6_11_replay_calibration()` for replay-bundle
   math; it does not fork or rewrite that code path.

The MVP is *not* allowed to:

- write new fields into `m6_11_calibration_ledger.jsonl`
- change pass/fail semantics of `proof-summary --strict` for the existing
  default mode or the existing `--m6_11-phase2-calibration` mode
- introduce new archetype-aware terms into any canonical file
- wire the `--json` output into `mew-product-evaluator`,
  `mew-adversarial-verifier`, `mew chat`, roadmap governance surfaces, or
  any other consumer that could cause M6.12 output to influence milestone
  decisions; those wirings are post-MVP and remain blocked on the
  governance question in section 9.8
- depend on the closeout bundle export tree (§8.2) having been
  produced. The MVP must still render honestly in pre-closeout mode
  against local `.mew/replays/**` bundles (with `missing_bundle`
  warnings where applicable); post-closeout mode becomes the
  authoritative operator citation as soon as the export step lands.

## 11. Later Expansion

### 11.1 MVP follow-ups (pre-v1)

- flesh out section 5.1.4 (recurrence across heads) and 5.1.7 (before/after
  comparator) if they did not land in the MVP slice
- add `--diff` flag rendering only the comparator section
- promote additional fixture tests if the reserved-archetype triggers in
  section 4.2.B start firing on new ledger rows (classify, do not
  retroactively canonicalize)
- no new downstream consumers of the `--json` contract are added in this
  window; external wiring stays blocked on the governance decision in
  section 9.8

### 11.2 v1 (requires recomputed post-closeout counts)

- commit initial threshold floors (dominant-share, drift-coverage,
  non-counted concentration) based on the recomputed post-closeout
  counts from the MVP classifier run; never before the classifier has
  actually been run against the 127-row ledger
- activate previously reserved archetypes (section 4.2.B) whose trigger
  conditions are met on the post-closeout ledger, under a `m6_12.v1`
  classifier bump
- promote `positive_outcome_v0` (section 4.2.D) into a richer
  positive-outcome sub-taxonomy if v0 operator feedback warrants it
- upgrade drift tags from `reserved` to evidence-backed once a
  drift harvester exists
- introduce `calibration-estimate` and `context-pressure` views if the
  evidence channels are added (section 9.5, 9.6)
- decide whether a dedicated top-level command (e.g.
  `mew calibration report`) is worth promoting over the
  `proof-summary --m6_12-report` subflag

### 11.3 Longer term (governance-gated)

- treat the `M6.12` report as a first-class input to `mew-product-evaluator`
  so roadmap decisions can cite recurrence directly; requires the
  governance decision in section 9.8 to land first
- treat the `--json` output as an `mew-adversarial-verifier` input;
  same governance gate
- explore whether `M6.12` output should be journaled per-session as passive
  telemetry (only after `M7 Senses` work re-opens inbound signal budgets)

## 12. Success Criteria For v0

`M6.12` v0 is considered good enough to close the bounded design slice when:

1. Every counted row in `proof-artifacts/m6_11_calibration_ledger.jsonl`
   receives an archetype label via rule 4.1 and the priority list in
   §4.2.A.2 (Tier 1 only), or is explicitly tagged `unclassified_v0` with
   a warning. No ledger row drops between archetypes ambiguously; the
   v0 taxonomy in particular must:
   - classify `non_counted_no_artifact_live_preflight_validation` as
     `preflight_gap` and must not double-count any `fix_first_preflight_*`
     row in both `preflight_gap` and `fix_first_evidence`;
   - classify the two
     `positive_current_head_paired_dry_run_applied_verified_after_*`
     rows (rows 69 and 72 in the closeout ledger) as
     `positive_outcome_v0`, not `unclassified_v0`;
   - never classify a `fix_first_remediation` or
     `counted_fix_first_blocker` row as `positive_outcome_v0`, even
     when its `reviewer_decision` is `approve_commit` — the §4.2.D
     Step-1 exclusion guard must fire first;
   - emit the archetype cohort counts from the §4.2.A "v0
     classifier-output summary" (the post-priority totals), not the
     raw enumeration totals.
2. Every derived label trace-backs to a `row_ref` and, where applicable, a
   `bundle_ref`.
3. The cockpit renders on one screen for the current ledger without
   silencing drift axes that have zero rows.
4. `mew proof-summary --strict` continues to pass unchanged on the current
   artifact set, in both the default mode and the existing
   `--m6_11-phase2-calibration` mode.
5. No canonical field was renamed, widened, or retroactively rewritten.
6. The `--json` contract separates `canonical` from `derived`, includes
   the required `bundle_provenance` object (with `mode`, `root`,
   `closeout_index`, `referenced`, `resolved`, `missing`, and
   `missing_row_refs[].reason`), exposes the full
   `derived.classifier_priority` list, and is consumed by at least one
   **in-tree, non-governance** reader: a unit test in
   `tests/test_calibration_report.py` that parses the JSON, asserts the
   canonical/derived partition, asserts the bundle-provenance separation
   rules from §8.5, and asserts the §4.2.A.2 priority semantics on a
   fixture row whose `countedness` could match multiple archetypes.
   **No evaluator, adversarial verifier, or other governance-facing
   consumer is wired in v0.**
7. Mode-detection and resolver rules (§8.5.1) hold:
   - `--closeout-index` absent → `canonical.mode = pre_closeout` and the
     pre-closeout resolver is used;
   - `--closeout-index` present and valid → `canonical.mode = post_closeout`
     and the post-closeout resolver is used;
   - `--closeout-index` present but missing/unreadable/malformed → hard
     fail before classification (non-zero exit), regardless of `--strict`;
   - no cross-mode fallback, and no pre-closeout resolver is ever invoked
     when `canonical.mode = post_closeout`.
8. Unified strict-mode rule (§8.5.6) holds: `--strict --m6_12-report`
   exits non-zero whenever `canonical.bundle_provenance.missing > 0` in
   either mode, and exits zero otherwise (subject to future v1
   threshold additions that do not ship in v0). Non-strict runs exit
   zero on missing bundles in both modes while still surfacing the
   suppression rule in §8.5.5.
9. Reviewer adjudication still wins when a derived label would disagree
   with `reviewer_decision`.

Not v0 criteria (explicitly deferred):

- The closeout bundle export step from §8.2 actually having been run.
  M6.11 is closed and the 127-row ledger is the canonical input, but
  `proof-artifacts/m6_11_closeout_replay_bundles/` and
  `proof-artifacts/m6_11_closeout_replay_index.json` are still pending
  deliverables (see §9.11). v0 MVP must run in pre-closeout mode today
  and must be ready to switch to post-closeout mode as soon as the
  export step lands, without changing classifier_version.
- Any downstream wiring of the `--json` contract into
  `mew-product-evaluator`, `mew-adversarial-verifier`, roadmap-governance,
  or other surfaces. Those remain post-MVP and governance-gated
  (sections 9.8, 11.3).

If any v0 criterion fails, `M6.12` v0 is not done.
