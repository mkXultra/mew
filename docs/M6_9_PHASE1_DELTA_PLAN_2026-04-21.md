# M6.9 Phase 1 Delta Plan

Date: 2026-04-21  
Status: prep only. No M6.9 implementation starts until M6.7 closes and this
delta plan is reviewer-approved.

## Purpose

Turn `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` into an
implementation-ready Phase 1 slice list without changing the active milestone.

Current ordering stays:

1. Finish M6.7 supervised 8-hour proof
2. Approve this delta plan
3. Land M6.9 Phase 1 as bounded M6.7-shaped iterations

This document is deliberately narrower than the design review. It answers:

- what Phase 1 deliverables exist
- which product surfaces likely change first
- what proof artifacts are required
- what is explicitly deferred to later phases

## Inputs

- `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md`
- `ROADMAP.md`
- `ROADMAP_STATUS.md`
- current M6.7 reviewer-gated iteration shape

## Phase 1 Scope

Phase 1 is the baseline that stops the bleeding. The target is not "smart
memory" in the abstract. The target is durable coding memory that is:

- typed
- gated on outcome
- inspectable from outside mew
- cheap enough not to regress the coding loop badly

Phase 1 includes only:

1. coding memory taxonomy
2. per-type write gates
3. deterministic `revise()` on reuse
4. minimum symbol/pair index
5. reviewer-diff capture
6. reviewer veto stub
7. observability surfaces for all durable artifacts

Deferred from Phase 1:

- hindsight harvester
- reasoning-trace population
- ranked recall
- graph rewrite / consolidation
- rehearsal and novelty injection
- preference store

## Deliverable Map

### D1. Coding Memory Taxonomy

Goal:

- add coding-domain `memory_kind` values on top of existing typed memory

Phase 1 populated kinds:

- `reviewer-steering`
- `failure-shield`
- `file-pair`
- `task-template`

Phase 1 schema-only kind:

- `reasoning-trace`

Likely surfaces:

- typed memory schema / validators
- memory write path
- memory list/show/trace output

Proof:

- one iteration writes at least one populated entry of each Phase 1 kind
- schema for `reasoning-trace` exists but stays empty

Non-goals:

- no model-generated reasoning-trace extraction yet

### D2. Write-Gate Matrix

Goal:

- durable writes happen only when type-specific evidence is present

Phase 1 minimum rules:

- `reviewer-steering`: explicit reviewer approval + `why` + `how_to_apply`
- `failure-shield`: explicit reviewer approval + symptom/root-cause/fix/stop-rule
- `file-pair`: focused paired test green + structural evidence
- `task-template`: explicit reviewer approval + rationale
- `reasoning-trace`: schema only, no writes

Likely surfaces:

- write gate evaluator
- durable write trace fields
- rejection reason surfaces

Proof:

- happy-path writes succeed
- missing-field writes reject with logged reason
- drift-canary-red rejects any write
- `file-pair` rejects separately on missing structural evidence and red tests

Non-goals:

- no hidden promotion from raw session logs

### D3. Deterministic `revise()` Reuse Gate

Goal:

- recalled durable memory must be adapted or dropped before injection

Phase 1 behavior:

- no model call
- rewrite symbol/file references from current index
- drop on `symbol_not_found` or `precondition_miss`
- log drop reasons

Likely surfaces:

- active recall path
- reuse trace logging
- session trace fields for dropped/injected entry ids

Proof:

- at least one real recall fires `revise()`
- at least one entry drops with `symbol_not_found`

Non-goals:

- no learned or model-backed revise step yet

### D4. Minimum Symbol/Pair Index

Goal:

- durable coding memory keys off `(module, symbol_kind, symbol_name)` with file
  paths secondary

Phase 1 shape:

- incremental population only
- no full-repo scan
- atomic JSON rewrite at `.mew/durable/symbol_index.json`

Likely surfaces:

- symbol extraction helper
- durable index read/write
- recall lookup path

Proof:

- one known symbol resolves via index on first read
- `index_hit=true` appears in trace

Non-goals:

- no graph scorer yet

### D5. Reviewer-Diff Capture

Goal:

- persist `(ai_draft, reviewer_approved, ai_final)` triples for landed diffs

Phase 1 rule:

- write only when `ai_final` exists

Likely surfaces:

- approval/apply path
- final landing hook
- `.mew/durable/reviewer_diffs.jsonl`

Proof:

- one approve + land cycle writes a complete triple
- approve-without-land does not write a triple

Non-goals:

- no preference retrieval yet

### D6. Reviewer Veto Stub

Goal:

- reviewer can mark one durable entry stale/deleted

Phase 1 rule:

- single-entry only
- no edge propagation

Likely surfaces:

- durable memory CLI
- veto log

Proof:

- one bad entry is written, vetoed, and confirmed not to fire again

Non-goals:

- no graph invalidation yet

### D7. Observability Surfaces

Goal:

- external agents can inspect durable coding state without importing mew code

Minimum Phase 1 surfaces:

- stable `.mew/durable/` layout
- `mew memory list/show/trace`
- `mew index query <module> <symbol>`
- session trace fields for recall/write events
- explicit growth budgets and Phase 1 oldest-entry eviction
- separate `veto_log.jsonl` and `eviction_log.jsonl`

Proof:

- one external process reconstructs a recall story from disk + trace only

Non-goals:

- no database or binary storage

## Proposed Bounded Iteration Split

Implement as separate M6.7-shaped iterations after M6.7 closes:

1. D1 taxonomy scaffolding
2. D7 observability surfaces
3. D6 reviewer veto stub
4. D2 write-gate matrix
5. D3 deterministic `revise()`
6. D4 minimum symbol index
7. D5 reviewer-diff capture

Rationale:

- D1 must land first because every later slice needs stable typed objects and
  a durable `memory_kind` vocabulary.
- D6 must exist early so bad durable entries can be cleaned up before they
  accumulate.
- D7 must exist early because later deliverables rely on trace/dump surfaces
  for proof.

Keep them separate. Do not bundle D1-D7 in one pass.

Concrete start rule:

- do not begin D2 until D1, D7, and D6 each have their own bounded proof
  artifact and reviewer sign-off

## Required Proof Artifacts

Before Phase 1 code starts, define and keep stable:

- dogfood scenarios:
  - `m6_9-memory-taxonomy`
  - `m6_9-revise-drop`
  - `m6_9-symbol-index-hit`
  - `m6_9-reviewer-diff`
  - `m6_9-veto-stub`
  - `m6_9-observability-rebuild`
  - `m6_9-phase1-regression`
- comparator baseline source for the 3 M6.6 task shapes
- baseline metrics pinned from 3 consecutive M6.7 iterations:
  - `B0.iter_wall`
  - `B0.first_think`
  - `B0.comparator`
- operator-surface baseline pinned from the late M6.7 wall-clock run:
  - `mew follow-status` shows `latest_model_failure`, selected failure metrics,
    and an exact recovery command
  - `mew focus` / `mew brief` / `mew desk` distinguish interrupted-vs-paused
    active work and do not treat a paused debug target as the default resume
    recommendation
  - current pinned implementation baseline:
    - `a719b5d` surfaces `latest_model_failure` diagnostics in `focus`
    - `234d844` extends `work --follow-status` failure metrics with explicit
      `write_ready_fast_path_reason` output
    - `3360b7c` makes `brief` prefer interrupted-session recovery over
      self-improve/default coding entrypoints
    - `33e7ab0` separates `untracked_only` checkpoint git state from true
      tracked dirtiness
    - `3361f15` prevents `desk` from foregrounding blocked active sessions
    - `090673c` makes `brief` / `focus` / `desk` surface explicitly paused work
      sessions honestly
    - `a8a86d7` aligns `build_work_session_resume()` with paused idle
      stop-request semantics so the resume surface no longer claims an already
      idle paused session will stop "at the next boundary"
    - `7f5a8b8` keeps paused work status consistent across `brief` / `focus`
      task lists instead of mixing a paused session with a `ready` task badge
    - `adb0555` suppresses stale `pending_steer` while a work session is
      explicitly paused, so parked blockers stay quiet until reactivated
  - remaining operator baseline work before M6.9 code starts:
    - keep `#388` paused unless a real invalidation forces resume
    - preserve these paused/interrupted semantics through the rest of M6.7 so
      later M6.9 observability work measures against a stable operator surface
- session trace additions needed for:
  - returned/dropped/injected entry ids
  - memory_kind
  - write_gate_result
  - index hit/miss
- write-path audit fields:
  - `written_by`
  - `approved_by`
  - `approved_at`
  - source iteration id
- Phase 1 NFR ceilings recorded before code lands:
  - iteration wall time `<= B0.iter_wall x 1.15`
  - first-think latency `<= B0.first_think x 1.10`
  - comparator regression bounded by the pinned `B0.comparator`

## Open Questions To Resolve Before Code

1. Which existing typed-memory file/schema should host `memory_kind` without
   forcing a migration rewrite?
2. Which current recall surface should own deterministic `revise()` in Phase 1?
3. What is the minimum symbol extractor that is good enough without a full-repo
   scan?
4. Which current approval/apply hook is the correct source of truth for
   `reviewer_diffs.jsonl` finalization?
5. Which existing CLI family should own `mew index query` and veto operations?
6. What per-type growth budgets and Phase 1 oldest-entry eviction rule should
   be pinned before `.mew/durable/` starts filling?

## Current Repo-Local Candidate Surfaces

These are prep notes only. They narrow the first code-reading pass after M6.7
closes; they do not authorize implementation yet.

- D1 taxonomy / typed-memory extension:
  - `src/mew/typed_memory.py`
  - `src/mew/memory.py`
  - `src/mew/commands.py` (`mew memory --add/--search/--active`)
- D2 write-gate matrix and rejection surfaces:
  - `src/mew/work_session.py` (resume/audit surfaces and durable work context)
  - `src/mew/commands.py` (CLI-facing rejection and audit output)
- D3 deterministic `revise()` on reuse:
  - `src/mew/work_session.py` (`build_work_active_memory`, active recall match/injection)
  - `src/mew/work_loop.py` (prompt compaction/injection path)
- D4 minimum symbol/pair index:
  - likely new durable file under `.mew/durable/`
  - nearest current durable-file precedents:
    - `src/mew/context_checkpoint.py`
    - `src/mew/snapshot.py`
- D5 reviewer-diff capture:
  - `src/mew/commands.py` approval/apply path
  - `src/mew/work_session.py` session-side approval and audit surfaces
- D6 reviewer veto stub:
  - `src/mew/commands.py` is the most likely CLI owner
  - storage shape should follow the existing file-backed typed-memory pattern
- D7 observability surfaces:
  - `src/mew/commands.py` (`memory list/show/active`, future `index query`)
  - `src/mew/work_session.py` and `src/mew/work_loop.py` for session trace fields

The first post-M6.7 implementation pass should confirm or reject this map
before touching any durable schema.

## D1 First Implementation Slice

This is the intended first code slice after M6.7 closes. It exists to keep D1
bounded and to prevent D1 from absorbing D2/D3 behavior.

Target files only:

- `src/mew/typed_memory.py`
- `src/mew/memory.py`
- `src/mew/commands.py`
- `src/mew/cli.py`
- focused tests in `tests/test_memory.py` and `tests/test_work_session.py` only

First-slice rule:

- extend the existing typed-memory infrastructure in place
- do not touch work-loop recall or prompt injection yet
- do not add `.mew/durable/` files yet
- do not add write gates yet
- do not add symbol-index or revise logic yet

Exact intended shape:

1. Keep the current storage layout:
   - `.mew/memory/<scope>/<type>/*.md`
   - no migration rewrite
   - legacy entries without coding metadata continue to load
2. Add an optional `memory_kind` discriminator to typed-memory frontmatter and
   `entry_to_dict()` output.
3. Restrict Phase 1 coding kinds to `--type project` entries only.
4. Accept these populated kinds in the first slice:
   - `reviewer-steering`
   - `failure-shield`
   - `file-pair`
   - `task-template`
5. Reserve `reasoning-trace` in schema, but reject direct writes with an
   explicit `schema-only until Phase 2` error.
6. Add CLI filtering/output only:
   - `mew memory --add ... --type project --kind <memory_kind>`
   - `mew memory --search ... --kind <memory_kind>`
   - JSON and human output show `memory_kind` when present
7. Leave active-memory recall semantics unchanged in D1:
   - same matching
   - same injection order
   - no new recall ranking
   - no automatic promotion from session logs

Proof target for this slice:

- one manual typed-memory round trip for each populated kind
- `reasoning-trace` rejects cleanly as schema-only
- legacy typed-memory reads/searches still pass without `memory_kind`
- active-memory tests stay green without any prompt-shape change

Explicit non-goals for D1 first slice:

- no `mew memory list/show/trace` expansion beyond exposing `memory_kind`
- no write-gate enforcement
- no reviewer-diff capture
- no veto command
- no deterministic `revise()`
- no symbol-index persistence

If D1 needs any of those to land, stop and split the slice again instead of
bundling later Phase 1 deliverables into taxonomy scaffolding.

## D7 First Implementation Slice

D7 is second, not concurrent with D1. The first D7 slice should expose D1
state read-only before it tries to explain recall/write events from later
deliverables.

Target files only:

- `src/mew/typed_memory.py`
- `src/mew/commands.py`
- `src/mew/cli.py`
- focused tests in `tests/test_memory.py`

First-slice rule:

- read-only surfaces only
- reuse the existing typed-memory store under `.mew/memory/`
- do not create `.mew/durable/` yet
- do not add `trace`, `index query`, or veto behavior yet
- do not depend on work-session or work-loop changes

Exact intended shape:

1. Add a read-only listing surface for typed memory:
   - `mew memory --list`
   - optional filters: `--type`, `--scope`, `--kind`, `--limit`
2. Add a read-only single-entry surface:
   - `mew memory --show <id>`
   - supports typed-memory ids already emitted in JSON/search output
3. Keep output stable and external-agent friendly:
   - human format shows `scope.type.kind name`
   - JSON includes `id`, `scope`, `memory_type`, `memory_kind`, `name`,
     `description`, `created_at`, and `path`
4. Preserve legacy compatibility:
   - entries without `memory_kind` still list/show normally
   - `--kind` filters only typed-memory entries that actually carry the field

Proof target for this slice:

- `mew memory --list --json` reconstructs typed-memory inventory without
  importing mew modules
- `mew memory --show <id> --json` round-trips a D1 entry by id
- legacy typed-memory entries still list/show cleanly

Explicit non-goals for D7 first slice:

- no `.mew/durable/` directory yet
- no `mew memory trace`
- no `mew index query`
- no recall/write-event trace fields
- no reviewer veto surfaces

If D7 needs any of those to land, stop and split the slice again instead of
pulling later observability work into the first read-only surface.

## D6 First Implementation Slice

D6 is third, after D1 and D7. The first D6 slice should only let a reviewer
disable one bad durable entry and observe that it no longer participates in
read-only surfaces.

Target files only:

- `src/mew/typed_memory.py`
- `src/mew/commands.py`
- `src/mew/cli.py`
- focused tests in `tests/test_memory.py`

First-slice rule:

- single-entry veto only
- no edge propagation
- no ranking or decay interaction
- no work-session/work-loop integration yet
- no hidden deletion; keep the original entry on disk

Exact intended shape:

1. Add a reviewer-owned command surface:
   - `mew memory --veto <id> --reason <text>`
2. Persist vetoes separately from typed-memory entries:
   - append-only log file under the future durable layout
   - first slice may use a minimal standalone JSONL veto log without requiring
     the rest of `.mew/durable/` to exist yet
3. Treat veto as logical suppression, not physical deletion:
   - `mew memory --show <id>` reports veto status
   - `mew memory --list` hides vetoed entries by default
   - optional future `--include-vetoed` stays deferred unless needed
4. Keep the first veto decision reviewer-authored:
   - no automatic veto from failed recall or stale symbol detection

Proof target for this slice:

- write one D1 entry, veto it, confirm default list output no longer shows it
- `mew memory --show <id>` explains that the entry is vetoed and includes the
  veto reason
- the original typed-memory file remains unchanged on disk

Explicit non-goals for D6 first slice:

- no transitive invalidation
- no supersedes/refined_by graph walk
- no recall-time veto metrics
- no bulk veto or query-language selection

If D6 needs any of those to land, stop and split the slice again instead of
pulling Phase 2 invalidation behavior into the Phase 1 veto stub.

## Stop Rules

Do not start M6.9 code if any of these is still true:

- M6.7 is not closed
- this delta plan is not reviewer-approved
- Phase 1 deliverables are being bundled
- the comparator baseline for `m6_9-phase1-regression` is not pinned

## First Action After Approval

After M6.7 closes and this plan is approved:

1. pin comparator baseline fixtures
2. choose D1 only
3. land D1 as one bounded supervised iteration
4. record proof artifact before touching D2
