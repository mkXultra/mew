# Review of LOOP_STABILIZATION_DESIGN_2026-04-22

Reviewing `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` against its
source inputs (Claude Code patterns, Codex patterns, mew structure
review, Claude Ultra synthesis) and the live state of the repo. This is
the third pass of the review, after two rounds of design updates.

## Verdict

**The design is implementation-ready. All three previously-blocking
issues are resolved.** Remaining items are nits or polish, not blockers.

Status of the three prior blockers:

| Blocker | Status | Where it was fixed |
| --- | --- | --- |
| Replay-bundle capture sequenced too late | **Resolved** | Replay-bundle persistence is now inside Phase 2 scope (line 744) and concrete task #4; Phase 2 acceptance explicitly proves "any live draft failure after Phase 2 leaves a replayable local bundle" (line 750) |
| `WorkTodo.status` vs session phase not clear enough | **Resolved** | "Canonical source of truth invariant" added (lines 300-304) plus explicit derivation rules (lines 318-322); `WorkTodo.status` enum harmonized with session phase (line 333); Required Invariant #3 enforces derivation (line 401) |
| `MemoryExploreProvider` gating Phase 5/6 | **Resolved** | Task #12 now gates only on tasks 1-9 (line 859); steps 10-11 explicitly labeled "deferred protocol work" and "not blockers for Phase 5 or Phase 6"; Phase 5 (line 785) and Phase 6 (line 799) scope lines both reiterate independence; §7 has a terminating sentence saying the provider is "explicitly deferred protocol work" (line 180); request/result field lists now marked provisional (lines 204-226) |

Net: implement it.

## What is strong

Carrying forward from prior passes; nothing has regressed:

- Single-sentence diagnosis is still precise and load-bearing.
- `PatchDraftCompiler` sits at the right architectural altitude
  (deterministic, pure, fixture-testable, produces the single artifact
  every downstream surface consumes).
- 12-code blocker taxonomy is concrete, frozen early, and mapped to
  typed recovery actions.
- Freeze list is enforceable and covers the right surfaces
  (`write_tools.py`, paired discipline, approval/apply/verify gates).
- Replay bundle layout is specific and mirrors Codex's portable
  scenario layout.
- Executor lifecycle correctly deferred behind drafting work.
- §8 memory-explore protocol properties (non-goals, terminal states,
  replay bundle shape) are real value and correctly frozen while
  field lists stay provisional.

New in this revision:

- **Canonical source-of-truth invariant (lines 300-304)** is stated
  cleanly: `active_work_todo.status` is canonical, session phase is
  derived, independent phase mutation is forbidden when a todo is
  active. Required Invariant #3 enforces it. This removes a
  meaningful class of drift bugs before they can land.
- **`WorkTodo.status` enum now matches session phase** modulo pre-todo
  (`exploring`) and runtime-overlay (`interrupted`) states. Cleaner
  than the prior duplicative ladder.
- **Phase 2 acceptance explicitly proves live capture** ("any live
  draft failure after Phase 2 leaves a replayable local bundle").
  That closes the debuggability gap the design's own thesis
  requires.
- **Recovery rule 1 no longer says "smaller prompt."** Now reads
  "same tiny draft contract after re-verifying hashes" (line 511) —
  concrete and implementable.
- **Task #12 and Phase 5/6 scope lines explicitly decouple** the
  review lane and executor work from memory-provider protocol
  freeze.

## What is still weak (all non-blocking)

All of these are polish or small omissions. None should block Phase 0.

1. **Refusal separation in `src/mew/codex_api.py` is still not
   scheduled.** The blocker taxonomy includes `model_returned_refusal`,
   but today refusal deltas flow through `codex_api.py` lines 86-109 /
   125-131 and fail at JSON parsing. Without a small, isolated
   separation step (probably Phase 3 or a sub-phase), the
   `model_returned_refusal` code is unreachable — refusals will keep
   landing as `model_returned_non_schema` or transport errors. This is
   the one remaining issue that is worth pulling forward; it is small
   but the taxonomy depends on it.

2. **Session JSON migration still unspecified.** Pre-change sessions
   in `.mew/sessions/` will not have `WorkTodo`, `active_work_todo`,
   or window hashes. Resume semantics on an old session are
   undefined. One sentence of policy (fail-closed with a
   `session_requires_observe_refresh` recovery action is the safe
   default) would close this. Could be handled during Phase 1
   implementation.

3. **Calibration gate before Phase 3 rollout not named.** If the
   real model emits off-schema output >X% of the time, the single
   bounded retry is insufficient and every draft costs 2x. Naming a
   threshold and adding a calibration checkpoint at the end of
   Phase 2 would de-risk Phase 3.

4. **Testing polish missing:**
   - No `WorkTodo` serialization round-trip test named in Phase 1.
   - No follow-status JSON snapshot test in Phase 0.
   - Prompt-budget regression test not in the test matrix (synthesis
     doc asked for `tiny draft contract ≤ 3000 chars`).
   - No test that asserts tool-call-shaped responses are classified
     as `model_returned_non_schema` rather than silently accepted —
     this is the biggest behavioral change in Phase 3.

5. **Observability / interaction gaps:**
   - `reasoning_policy.py` keyword promotion (`policy`/`recovery`)
     not acknowledged; drafting/recovery prompts will silently run
     at `high` effort.
   - `self_improve_audit.py` interaction still not mentioned —
     unclear whether self-improve drafts route through the
     compiler.
   - Replay-bundle retention and scrubbing policy still
     hand-waved across both `.mew/replays/work-loop/` and
     `.mew/replays/memory-explore/`.

6. **Draft supersession rule missing.** When a validator blocker
   arrives after a draft has been shown, the design does not say
   whether the draft is `superseded` or the todo branches.
   Edge-case, but exactly the kind of omission that surfaces as an
   integration bug later.

7. **Streaming-mode recovery semantics** across
   `guarded|streaming|fallback_unguarded` are observable but not
   normatively specified. The test matrix includes a "#401 streaming
   timeout" row; recovery wording should confirm it reuses the
   guarded-mode path.

## Sequencing review

Phase order is correct and the edges are now clean:

- Phase 0 (freeze/instrument) — right
- Phase 1 (`WorkTodo`) — right
- Phase 2 (compiler + fixtures + replay capture) — right, and now
  complete
- Phase 3 (rewire prompt) — right; only gap is scheduling refusal
  separation inside or alongside it
- Phase 4 (drafting recovery + follow-status) — right
- Phase 5 (review lane) — right; scope line explicitly keeps it
  independent of memory-provider work
- Phase 6 (executor) — right; same independence guarantee

Concrete task list is now ordered so replay-bundle capture (task #4)
lands between compiler and fixtures — which is the right spot.

## Testability review

Strong parts unchanged from the prior review (fixture layout,
explicit `#399`/`#401` fixtures, four required harnesses, test
matrix covering the main negative cases).

Still missing, all non-blocking:

- `WorkTodo` serialization round-trip test.
- Phase 0 follow-status JSON snapshot test.
- Prompt-budget regression test.
- Test that the tiny contract rejects tool-call JSON.
- Fixture-update policy for when validator logic changes.
- No-op memory-explore conformance test (if tasks #10/#11 stay in
  the design, even a stub implementation would prove the protocol is
  implementable).

Net: testability is about 80% complete. The offline compiler story
is strong; observability-shape and runtime-integration tests are
still under-specified.

## Risk review

Risks the design names correctly are unchanged.

Risks still missed or understated:

- **Refusal pipeline gap** (§1 above).
- **Session JSON migration** (§2 above).
- **Model compliance rate** / calibration gate missing.
- **Replay-bundle privacy** across both bundle locations.
- **`reasoning_policy.py` interaction** not acknowledged.
- **`self_improve_audit.py` interaction** not mentioned.
- **Status-ladder drift risk: reduced to near-zero.** The new
  canonical invariant plus Required Invariant #3 closes this, but
  Phase 1 should still include one contract test that exercises
  derivation.

Risks that are now effectively eliminated (relative to prior
reviews):

- Task-ordering coupling between drafting stabilization and
  memory-explore protocol freeze.
- Late replay-bundle capture undermining debuggability thesis.
- Two overlapping status ladders drifting silently.

## Recommended changes before implementation

All three top-level blockers are resolved. Only two items are worth
addressing before Phase 0 lands:

1. **Schedule refusal separation in `codex_api.py`** either inside
   Phase 3 or as an explicit Phase 3.5. Without it,
   `model_returned_refusal` is unreachable and the taxonomy is
   incomplete. Small and isolated.

2. **Add a one-sentence session JSON migration policy.** Probably
   fail-closed with a `session_requires_observe_refresh` recovery
   action. Prevents a first-dogfood regression on old sessions.

Everything else (calibration gate, test polish,
`reasoning_policy.py`/`self_improve_audit.py` notes, replay-bundle
retention, draft supersession rule, streaming-mode recovery wording,
memory-explore conformance stub) can land during implementation
without blocking Phase 0.

## Final recommendation

**Start Phase 0.** The three previously-blocking issues — replay
sequencing, status-ladder source-of-truth, memory-provider coupling —
are all cleanly resolved in this revision. The design picks the
right architectural line, preserves mew's existing strengths, freezes
the right surfaces, and defers the right things. The remaining gaps
are small enough that they should not hold back implementation; the
only one worth pulling forward is refusal separation in
`codex_api.py`, because the blocker taxonomy depends on it.

This revision is good enough to build against.
