# M6.24 Staged Close Report - Software/Coding Terminal-Bench Parity Campaign

Date: 2026-05-20 JST

## Verdict

M6.24 is staged-closed.

This is not a claim that mew has completed full trial-aligned 5-run parity
against Codex across all 25 scoped tasks. It is a controller close decision:
the M6.24 measurement/improvement loop has enough evidence to stop spending
live proof budget here and move the active roadmap to M6.25.

The user explicitly deferred additional proof_5 spending because it is too
time-expensive for the current decision. The next work should prove Codex-plus
resident advantage, not continue reflexive Terminal-Bench proof collection.

## Evidence Snapshot

| Measure | Result |
|---|---:|
| Scoped tasks with `implement_v2` evidence | 25/25 |
| Clean `speed_1` passes | 22/25 |
| Existing proof_5 close row | `make-mips-interpreter` 4/5 |
| Frozen Codex target for that row | `make-mips-interpreter` 3/5 |
| Below-target rows | 2 |
| Unexplained Harbor runner errors in final selected rows | 0 |
| Accepted active structural blockers | 0 |

Primary evidence:

- `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-proof-5-ts-codex-hot-path-20260515-141331`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-write-compressor-speed-proof-ts-codex-hot-path-20260520-002334/2026-05-20__00-23-35/write-compressor__CDB9pWH`

## Deferred Gaps

| Task | Current mew evidence | Codex target | Decision |
|---|---:|---:|---|
| `make-doom-for-mips` | 0/1 speed proof | 1/5 | Deferred. Do not add Doom/MIPS-specific repair. Reopen only if a generic bounded verifier closeout or long-running observable-output verifier class repeats. |
| `raman-fitting` | 0/1 speed proof | 2/5 | Deferred. Codex single reference also failed 0/1. Reopen only if a generic numeric objective-grounding substrate is selected from repeated evidence. |

These deferrals are written decisions, not hidden failures. They should not
pull M6.24 back into task-specific repair without repeated generic evidence.

## Done-When Mapping

| M6.24 Done-when item | Status | Evidence |
|---|---|---|
| All 25 scoped tasks have mew results with complete artifacts and no unexplained Harbor runner errors | Met | Rebaseline table and aggregate snapshot record 25/25 evidence, final selected runner errors 0. |
| Aggregate successes match/exceed Codex, or explicit staged close gate is written | Staged met | This report is the explicit staged close gate. It does not claim full trial-aligned aggregate parity. |
| Below-Codex tasks have classification and selected repair route or deferral | Met | `make-doom-for-mips` and `raman-fitting` are classified/deferred with trigger conditions. |
| Improvement-phase changes are recorded with decision context | Met | Gap ledger records measurement, repair, rerun, and adoption decisions. |
| No accepted structural blocker remains unaddressed | Met | Current aggregate snapshot records none. |
| Final parity report includes aggregate score, deltas, errors, top gaps | Staged met | This report plus the rebaseline table provide the staged aggregate, per-task deltas, runner errors, and top remaining gaps. Cost/token data is not available in the current artifacts. |

## Caveats

- Full 5-trial proof across all 25 scoped tasks is intentionally not complete.
- `speed_1` rows are useful scoped evidence but are not statistically equivalent
  to full proof_5 runs.
- `schemelike-metacircular-eval` passed but remains high-turn/high-edit evidence
  for future speed tuning if the shape repeats.
- `make-doom-for-mips` and `raman-fitting` remain known deferred gaps.

## Next

Move active focus to M6.25: Codex-Plus Resident Advantage.

M6.25 should preserve the M6.24 evidence baseline while proving mew-native
persistence, reentry, memory, diagnosis, and repair reuse. It should not restart
M6.24 proof_5 collection unless a named M6.25 experiment requires a specific
regression check.
