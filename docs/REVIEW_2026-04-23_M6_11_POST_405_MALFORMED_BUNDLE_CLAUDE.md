# M6.11 Post-405 Malformed Bundle Review — Claude

Date: 2026-04-23
HEAD: `739c527341833af38b3c88de2b092073b5ca4f4d`

## 0. Independent verification

Confirmed by direct inspection before answering:

- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  reports `cohort[current_head].malformed_relevant_bundle_count=2` and lists both
  `session-405/todo-todo-405-1/attempt-{1,2}/replay_metadata.json` in
  `summary.errors` as
  `"missing or invalid validator_result JSON for ..."`.
- Both `validator_result.json` files are valid dicts with
  `kind="patch_draft"`, `status="validated"`, `validator_version=1`,
  `id=draft-...`, `files=[...]`, `unified_diff=...`. Neither file has a
  `code` key. The payloads match the shape produced by
  `compile_patch_draft()` at
  [src/mew/patch_draft.py:89-98](../src/mew/patch_draft.py).
- Both `replay_metadata.json` files have
  `bundle="patch_draft_compiler"`,
  `git_head="739c527341833af38b3c88de2b092073b5ca4f4d"` (== current HEAD),
  `blocker_code=""`. They are structurally valid and land in the
  `current_head` cohort.
- `.mew/state.json` line 908111 records
  `"rejection_reason": "This counted calibration sample must stay on the
  paired dogfood src/tests surface. A repeated test-only
  assertion-strengthening diff is low-signal and does not count toward the
  current-head calibration cohort."` Replay paths for attempt-1/attempt-2
  appear at lines 908581 and 908692.

So both Codex claims — (1) valid `patch_draft` artifacts are being classified
malformed, and (2) reviewer countedness lives only in `state.json`, not in
the replay bundle — are verified against the live repo. The current
`cohort[current_head]` is 1 valid compiler bundle plus 2 "malformed" bundles
that are not actually malformed.

## 1. Substrate fix before more counted samples?

**Yes.**

Both bugs are load-bearing for the close-gate math.
`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:118-157` ties the
Phase 2/3 calibration checkpoint and the §3.2 20-slice incidence batch to
cohort[current_head] denominators. With the current substrate:

- Every future validated `patch_draft` (the success case for the
  compiler) will be counted malformed because
  [src/mew/proof_summary.py:286-289](../src/mew/proof_summary.py) treats a
  missing `validator_result.code` as "missing or invalid validator_result
  JSON." This is not a session-405-specific glitch; it will reproduce
  any time the compiler returns a validated draft.
- Reviewer-rejected low-signal attempts still contribute their bundles to
  `cohort[current_head]` because `write_patch_draft_compiler_replay()` at
  [src/mew/work_replay.py:331-354](../src/mew/work_replay.py) records no
  calibration-eligibility field, and there is no post-rejection hook that
  touches the replay. Operator process proved insufficient in this very
  session — the task was reviewer-rejected and still polluted the cohort.

Collecting more counted samples before fixing either bug would mean
collecting data that the substrate cannot honestly interpret. The 20-slice
incidence denominator would be built on classifications we already know are
wrong.

## 2. Minimal correct fix set

Two narrow changes, plus a one-time backfill. I agree with Codex's shape on
both but want to be more specific about the boundaries.

### Fix A — classifier bug in `proof_summary.py`

Rewrite `_read_validator_result_code` and the call site so they distinguish
three cases instead of collapsing them to `None`:

| Validator payload | Current behavior | Correct behavior |
|---|---|---|
| Unreadable JSON | malformed | malformed (unchanged) |
| Not a dict | malformed | malformed (unchanged) |
| Valid dict, `kind="patch_blocker"`, has `code` | classified by code | classified by code (unchanged) |
| Valid dict, `kind="patch_draft"`, `status="validated"`, no `code` | **malformed** | `patch_draft_compiler.other`, off_schema=False, refusal=False |
| Any other dict shape | malformed | malformed |

Concretely: have `_read_validator_result_code` return a small record such
as `(outcome, code)` where `outcome ∈ {"malformed", "blocker", "draft"}`.
Then `_summarize_patch_draft_compiler_bundle` routes:

- `outcome == "malformed"` → append error, return summary (current path)
- `outcome == "draft"` → `calibration_bundle_type = "patch_draft_compiler.other"`, no error
- `outcome == "blocker"` → `_calibration_compiler_type(code)` (current path)

This is roughly 15 lines of production code plus ~4 targeted tests (validated
draft, blocker with code, unreadable JSON, non-dict payload).

### Fix B — calibration-eligibility metadata on compiler bundles

Add two fields to the `metadata` dict written by
`write_patch_draft_compiler_replay()` at
[src/mew/work_replay.py:331-351](../src/mew/work_replay.py):

```json
"calibration_counted": true,
"calibration_exclusion_reason": ""
```

Write-time default: `calibration_counted=true`, reason empty. The reviewer
rejection flow must flip these fields. The cleanest seam is an
update-in-place helper in `work_replay.py` (e.g.
`mark_replay_non_counted(replay_path, reason)`) called from
`reject_work_tool_call()` at
[src/mew/commands.py:5691-5697](../src/mew/commands.py) when the rejected
tool call's model turn carries a `patch_draft_compiler_replay_path`. I
deliberately prefer mutating the existing `replay_metadata.json` over a
sidecar file because:

- The bundle remains self-describing — one file, one artifact boundary,
  which matches Codex's framing of "calibration eligibility must be in
  the artifact that `proof-summary` actually consumes."
- `proof-summary` already opens this file on every pass.
- A sidecar invites drift (e.g. a rejection that writes a sidecar that
  then gets moved/renamed/archived separately).

Update `proof_summary.py` so any bundle with `calibration_counted=false` is
excluded from `relevant_bundles`, `compiler_bundles`, `total_bundles`,
`malformed_*`, cohort math, and threshold gates. Keep it visible via a
new diagnostic bucket (e.g. `non_counted_bundle_counts` per cohort) so
reviewer-rejected samples are still auditable but do not contaminate
denominators.

### Fix C — one-time backfill of the two session-405 replay metadata files

Set `calibration_counted=false`,
`calibration_exclusion_reason="reviewer_rejected_low_signal_test_only_diff"`
on both attempt-1 and attempt-2 `replay_metadata.json`. This is a manual
edit of two JSON files — do not generalize the backfill into a tool.

## 3. Where should the counted/non-counted decision live?

**Primarily in replay metadata, with proof-summary as a pure consumer.**

The decision has to be *written* somewhere the artifact graph already
recognizes, and it has to be *read* by proof-summary without cross-system
coupling. Putting it on the replay bundle gives both properties:

- Write: the reviewer-rejection code path already knows which model turn
  it is rejecting, and `state.json` already records
  `patch_draft_compiler_replay_path` per turn (lines 908581, 908692). The
  hook from `reject_work_tool_call()` → `mark_replay_non_counted()` is
  one direct pointer chase.
- Read: `proof_summary.py` already walks
  `replay_metadata.json` files and would simply check one more field.

Putting the decision in selection rules inside `proof_summary.py` (e.g.
"proof-summary scrapes state.json to see which sessions were rejected") is
worse because:

- `state.json` is ~56MB and has a deeply nested, mutating schema; coupling
  proof-summary to it is a long-lived source of breakage.
- The rejection fact exists on a *tool call*, not on a *replay*; mapping
  between them requires walking `session.model_turns[].plan_item_observations`,
  which is exactly the kind of brittle coupling substrate code should
  avoid.
- It externalizes what the artifact itself should declare — the whole
  point of a replay bundle is that it is self-describing.

Putting the decision in *both* places is over-engineered. The source of
truth is the replay metadata. The operator rejection event *causes* that
metadata to flip, but it does not need to be consulted later.

## 4. Simpler alternative that preserves calibration honesty?

There are two simpler paths worth naming, but neither fully substitutes
for the two-fix set.

### Alt-1: Fix A only, plus manual artifact deletion

Land only the classifier bug fix in `proof_summary.py`, then delete the
two session-405 attempt directories by hand. This is about 15 lines of
code.

Problem: it bets on operator process for countedness, and this incident
already showed that operator process is not sufficient — the rejection was
recorded in `state.json` yet the bundles still contaminated the cohort
until someone noticed. Deletion also destroys evidence useful for
retroactive prompt tuning (why was this low-signal? what did the draft
look like?). So this saves one file touch but re-introduces the structural
problem the incident is exposing.

### Alt-2: Fix A only, plus a rejection sentinel file

Write an empty marker like `.calibration_excluded` into the attempt dir
when a reviewer rejects. Proof-summary checks for its presence and skips
the bundle.

This is smaller than Fix B (no JSON mutation, no field additions), but it
is strictly less informative — you lose the `exclusion_reason` that future
debugging will want. And it still requires hooking the rejection path in
commands.py, which is the bulk of Fix B's work anyway.

My judgement: **Alt-1 is acceptable as a hot-fix if shipping is urgent**
(it unblocks cohort readout for the one sample that *isn't* rejected),
but it should be followed by Fix B within the next bounded slice. It is
not a replacement for Fix B.

## 5. Recommended next bounded implementation step

Land one slice, in this order, before collecting any more counted samples.
Everything below is scoped to ~120 LoC plus tests.

1. **Classifier fix** — modify
   [src/mew/proof_summary.py:226-293](../src/mew/proof_summary.py) per
   Fix A. Add tests:
   - validated `patch_draft` with no `code` → bucketed as
     `patch_draft_compiler.other`, `malformed_*=0`
   - unreadable JSON → still malformed
   - non-dict JSON → still malformed
   - `patch_blocker` with `code="unpaired_source_edit_blocked"` → still
     classified correctly
2. **Metadata field + reviewer hook** —
   - extend the metadata dict in
     `write_patch_draft_compiler_replay()` at
     [src/mew/work_replay.py:331-351](../src/mew/work_replay.py) with
     `calibration_counted=True`, `calibration_exclusion_reason=""`
   - add `mark_replay_non_counted(replay_path, reason)` in
     `work_replay.py` that reads, flips, and rewrites the file with the
     same `json.dumps(..., indent=2, sort_keys=True)` shape
   - call it from `reject_work_tool_call()` at
     [src/mew/commands.py:5691-5697](../src/mew/commands.py) when the
     rejected tool call's owning model turn has a
     `patch_draft_compiler_replay_path`
3. **Proof-summary consumer** — in
   [src/mew/proof_summary.py:355-399](../src/mew/proof_summary.py),
   treat `calibration_counted=false` bundles as non-counted: skip all
   cohort math, but surface them in a new `non_counted_bundle_counts`
   per cohort for auditability. Mirror the same check in the
   `report.json` loop at lines 400-440.
4. **Backfill** — hand-edit the two
   `.mew/replays/work-loop/2026-04-22/session-405/todo-todo-405-1/attempt-{1,2}/replay_metadata.json`
   to set `calibration_counted=false`,
   `calibration_exclusion_reason="reviewer_rejected_low_signal_test_only_diff"`.
5. **Rerun**
   `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
   and confirm `cohort[current_head]` shows
   `relevant_bundles=1, compiler_bundles=1, malformed_relevant_bundle_count=0,
   non_counted_bundles >= 2`.
6. **Then and only then** restart counted sample collection on a fresh
   paired src/tests surface.

### Testability notes

- Fix A's four tests are pure-unit and take milliseconds — they are the
  regression gate.
- Fix B's reviewer-hook test should drive `reject_work_tool_call()` end-to-end
  and assert the linked `replay_metadata.json` on disk now has
  `calibration_counted=false`. This is the test that will catch future
  drift if anyone changes the rejection flow.
- Add an explicit proof-summary test that builds a mixed replay tree
  where one compiler bundle is counted and one is non-counted, and
  asserts the non-counted bundle appears in `non_counted_bundle_counts`
  but not in `compiler_bundles`, `off_schema_count`, `refusal_count`, or
  `malformed_*`.

### Debuggability notes

- The new `non_counted_bundle_counts` output is cheap to add to
  `format_proof_summary()` and makes future incidents self-diagnosing —
  a reviewer looking at a close-gate readout can see at a glance how
  many bundles were excluded and why.
- Keep the `calibration_exclusion_reason` free-form but encourage a
  small vocabulary (`reviewer_rejected_low_signal`,
  `reviewer_rejected_out_of_scope`, etc.) by documenting it next to the
  field in `write_patch_draft_compiler_replay()`.

## 6. Short answer summary

1. Substrate fix first: **yes**.
2. Minimal fix set: classifier bug in `proof_summary.py` +
   `calibration_counted` field in compiler replay metadata with a
   `reject_work_tool_call` hook + one-time backfill of the two
   session-405 files.
3. Decision lives in **replay metadata**; `proof-summary` is a pure
   consumer.
4. Simpler alternative: classifier-only plus artifact deletion works as
   a hot-fix, but operator-process countedness has already failed once
   this session, so it should not be the endpoint.
5. Next bounded step: one slice across `proof_summary.py` +
   `work_replay.py` + `commands.py` + tests + backfill, then rerun
   `proof-summary`, then restart counted samples.
