# M6.11 Post-Current-Head=2 Next Step — Codex

Date: 2026-04-22  
HEAD: `f61e657`

## Verdict

The bounded post-Strengthen-Iter-B collection goal is met: live evidence source
`#402` now writes fresh attributable current-HEAD bundles, and the live exit
shape is no longer `request_timed_out`. But M6.11 close-gate evidence is still
blocked because the fresh cohort is too narrow, not because attribution or
follow-status is missing.

Current state from `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`:

- `calibration.cohorts.current_head.total_bundles = 2`
- both fresh bundles are `patch_draft_compiler.other`
- `current_head.thresholds.failure_mode_concentration_ok = false`
- the only failing current-HEAD threshold is concentration
  (`dominant_share = 1.0`)
- `cohorts.unknown` still contains the older mixed 14-bundle history

This supersedes the earlier post-Iter-B memo whose exact goal was only to get
`current_head.total_bundles > 0` via `#402`.

## Evidence Source Decision

Do **not** keep using `#402` as the primary live evidence source. Keep it only
as a regression/canary surface.

Reason:

- the repo’s own session notes say `#402` was to be used only to emit fresh
  attributable bundles after `f61e657`
- that goal is now satisfied
- `#402` is still historical M6.9 frozen work (`M6.9 D7: veto-log read-only
  memory surface`), not an M6.11-owned task-selection authority
- the fresh blocker path is now a mixed target surface
  (`src/mew/commands.py`, `tests/test_memory.py`, `src/mew/cli.py`)
  ending in compiler blockers like `unpaired_source_edit_blocked` and
  `insufficient_cached_test_context`
- more `#402` reruns are therefore likely to deepen the
  `patch_draft_compiler.other` monoculture rather than answer the remaining
  close-gate question

## 20-Slice Incidence Gate

Do **not** start the 20-slice incidence gate yet.

Why:

- the current-HEAD cohort exists, but it is only two bundles and both come from
  the same historical evidence source
- starting the 20-slice batch now would anchor the measurement to a collector
  that the repo already treats as historical M6.9 work
- the immediate gap is not “more count”; it is “first non-`#402` current-HEAD
  evidence from a clean M6.11-era mew-first slice”

## Exact Next Bounded Step

Reviewer-select and run **one fresh bounded mew-first implementation slice on a
new task/session, not `#402`**, then rerun calibration immediately.

Boundaries for that one slice:

1. use a fresh task owned by the active M6.11 evidence chain, since task
   selection remains reviewer-owned in `ROADMAP_STATUS.md`
2. scope it to one clean paired src/test surface with enough cached old text on
   both files to avoid the already-seen `insufficient_cached_test_context`
   blocker up front
3. run one bounded live iteration through the new drafting path
4. rerun:

```bash
./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```

Success condition for this next step:

- `current_head.total_bundles` increases beyond `2`
- at least one fresh bundle comes from a non-`#402` source
- the resulting current-HEAD mix tells us whether present-day M6.11 evidence is
  diversifying beyond `patch_draft_compiler.other` before the full 20-slice
  incidence gate begins
