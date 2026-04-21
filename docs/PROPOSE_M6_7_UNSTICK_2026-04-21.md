# M6.7 Unstick Proposal — Explorer + Todo Before More Substrate Hardening

Date: 2026-04-21 22:30 JST.
Status: **proposal for reviewer approval**. Not yet in ROADMAP.md.
Target reviewers: user (Kaito Miyagi) + Codex (M6.7 supervisor).

## TL;DR

The 8-hour supervised proof has exercised candidates N-A through N-H
and produced **zero honest iteration closures**. The failure mode is
consistent: mew session stalls in edit planning before a reviewable
paired dry-run diff surfaces. Three substrate hardening passes have
not resolved it.

This proposal: pause the 8-hour proof after the current refreshed
queue, land two bounded enablers from
`docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` —
**Explorer sub-agent (Pattern A)** and **Todo Management Tool
(Pattern D)** — then reopen the proof on a fresh queue. The
hypothesis is that these address the root cause of the stall; if
correct, M6.7 closes faster than by more substrate fixes.

Expected net wall time: **equal to or faster than continuing with
substrate fixes alone**, with the benefit that the two enablers
compound on every M6.9 iteration afterward.

## 1. Evidence that dogfood is stuck

Source: `docs/M6_7_SUPERVISED_8H_PROOF_PLAN_2026-04-21.md` (latest),
commit history between `b220a05` (17:46) and `0e00dd0` (22:01).

- 8 candidates tried: **N-A, N-B, N-C, N-E, N-F, N-H** logged; **N-D,
  N-G, N-I** pending or un-run.
- Outcomes:
  - **N-A, N-B**: soft-stopped; mew did not produce a dry-run diff
    after two fresh attempts each.
  - **N-C**: reviewer no-change; already green.
  - **N-E, N-H**: supervisor landed the product patch directly because
    mew session stalled in edit planning. Counted as product progress,
    **not M6.7 proof credit**.
  - **N-F**: surfaced a real broader-verifier blocker; did not close
    as honest iteration.
- Substrate hardening landed since M6.7 iteration #6:
  - `1f27de3` (16:11): Stabilize M6.7 live verifier loop.
  - `9dad07b` (17:xx): Force compact-live prompt context in work loop.
  - `0e00dd0` (22:01): Harden M6.7 loop timeouts and proof progress
    (762 lines across 16 files, `work_loop.py` +98, `codex_api.py`
    +80).
- **Credit closed in that window: 0 iterations.**

The common failure signal — "stall in edit planning before dry-run
diff surfaces" — is stable across candidates, not an artifact of any
single task shape.

## 2. Diagnosis

Three substrate hardening passes targeted timeouts, verifier
stability, and compact-live context. The stall persists. This points
to a root cause above the substrate, in one or more of:

1. **Context exhaustion during serial exploration** — mew runs
   `search -> read -> search -> read` serially before edit planning;
   by the time planning starts, context is full of exploration output
   and the edit cannot crystallize.
2. **Plan volatility across turns** — mew re-derives its plan every
   turn from context. When the stall happens, next-turn replanning
   rebuilds from scratch rather than resuming.
3. **Exploration pollution of main loop** — failed or speculative
   reads stay in main context, so each turn carries weight from dead
   ends instead of focusing on the edit surface.

Explorer (Pattern A) addresses (1) and (3) directly. Todo (Pattern D)
addresses (2) directly. Both are single-session, non-governance
changes that do not require new M6.7 gate work.

## 3. Proposed intervention

Land two bounded enablers from
`docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`:

### 3.1 Pattern A — Explorer sub-agent (read-only exploration delegation)

Minimum-viable shape for M6.7 unstick:

- a sub-agent role that can call `read_file`, `search_text`, `glob`,
  `git_status`, `git_diff`, `git_log` — **read-only tools only**
- invoked from the main work session via a single tool call
  `explore(question) -> summary` that returns a short natural-language
  summary of findings plus the specific file paths and lines
- sub-agent session is **bounded**: cap at a fixed number of tool
  calls (proposal: 8) and a fixed wall-time (proposal: 60 seconds)
- sub-agent output is a short text report; it does **not** leak raw
  tool results into the main loop's context
- sub-agent write/edit/shell tools are not available; attempt to use
  them is a hard error in Phase 1 of this enabler
- scope-fence compatibility: the Explorer inherits the main session's
  allowed-read paths; cannot read outside the main session's declared
  read surface

Why this specific shape: keeps Explorer strictly additive to M6.7's
scope fence. Read-only + bounded + summary-only means the governance
model remains the same as a single-session write. The Explorer cannot
cause reviewer rescue by its nature.

### 3.2 Pattern D — Todo Management Tool (session-durable plan)

Minimum-viable shape for M6.7 unstick:

- a structured todo list per work session, persisted in the session
  state so it survives turn boundaries, stalls, and crashes within
  the same session
- tool surface on the main session: `todo_write(items)` /
  `todo_update(id, status, notes)` / `todo_list()`
- todo item fields: `id`, `title`, `status ∈ {pending, in_progress,
  done, blocked}`, `notes`, `next_action`
- `in_progress` is limited to one item at a time per session (parity
  with claude-code's TodoWrite convention)
- todo list is visible in `mew focus` / `mew brief` output so a
  reviewer can see the plan without reading the session transcript
- todos are **session-scoped**, not durable across sessions. Cross-
  session durability is Phase 2 and out of scope here; it overlaps
  with M6.9 Phase 1 task-template memory.

Why this specific shape: gives mew a place to park its plan outside
the model context, so stall-then-resume does not require re-deriving
the plan. No M6.9 infrastructure is required.

## 4. Scope and non-goals

In scope:
- minimum Explorer tool with read-only bound
- minimum Todo tool with session persistence
- wiring both into the work session prompt so mew can actually use
  them
- one focused test per tool covering happy path + boundary
  (out-of-scope read attempt for Explorer; double `in_progress` for
  Todo)
- `mew focus` / `mew brief` surfacing of todo list

Out of scope:
- cross-session todo durability (→ M6.9 Phase 1 task-template)
- Explorer writing to any memory or state (→ M6.9 reasoning-trace)
- multi-Explorer concurrency (→ M10 multi-agent residence)
- Explorer with write or shell (→ future milestone, needs governance
  work)
- removing any M6.7 governance or scope-fence behavior
- changing M6.7 Done-when criteria

## 5. Governance

This proposal pauses the 8-hour supervised proof mid-stream. That is a
scope-fence-adjacent decision and requires the same reviewer approval
shape as any M6.7 governance action:

1. Reviewer approves this proposal explicitly before any pause.
2. The pause is recorded in `ROADMAP_STATUS.md` as a dated entry in
   the Active Milestone Decision block, not a silent halt.
3. Explorer and Todo iterations themselves run under M6.7 rules:
   bounded scope, reviewer-gated dry-run, proof-or-revert, drift
   canary before each iteration.
4. Landing Explorer or Todo does **not** count toward M6.7 8-hour
   proof credit; they are enablers, not proof items.
5. Once both enablers land, M6.7 proof resumes with a fresh candidate
   queue. The prior queue is not reused — the stall evidence on
   those candidates is preserved as repair guidance, but honest proof
   credit requires fresh items.

## 6. Entry and exit criteria

### Entry
- reviewer approval of this proposal
- ROADMAP_STATUS entry recording the pause
- current 8h proof attempt explicitly marked soft-stopped in the
  proof plan doc

### Exit (both must hold before M6.7 proof resumes)
- Explorer tool landed with passing tests, used at least once in a
  bounded supervised iteration, and produces a summary that a
  reviewer confirms reduced main-loop context pressure
- Todo tool landed with passing tests, visible in `mew focus` output,
  and used in at least one supervised iteration where a mid-turn
  stall was followed by clean resumption using the persisted plan
- M6.7 proof candidate queue is freshly refreshed with items not
  previously attempted

### Retreat criterion
If after 3 bounded Explorer-involving iterations and 3 bounded
Todo-involving iterations the "stall in edit planning" pattern
persists, this proposal's hypothesis is falsified. At that point the
choice returns to reviewer: continue substrate hardening, or escalate
to a deeper redesign (e.g. §5.1 Streaming Tool Executor, which is a
larger commit than this proposal).

## 7. Implementation order

Six bounded M6.7-shaped iterations under reviewer gating:

1. **Todo D1**: `todo_write/update/list` tool + session-state
   persistence. Single source file + test.
2. **Todo D2**: `mew focus` / `mew brief` surface the todo list. Two
   source files + tests.
3. **Todo D3**: work-session prompt wires todos into context, so mew
   actually uses them. Prompt file + test.
4. **Explorer D1**: read-only tool bundle + sub-agent runner. Two
   source files + test.
5. **Explorer D2**: `explore(question)` main-session tool surface;
   summarization shape; context-isolation guarantee. One source file
   + test.
6. **Explorer D3**: work-session prompt wires Explorer into planning
   guidance. Prompt file + test.

Each iteration reviewer-gated; no bundling; typical M6.7 shape.

Estimated wall time: 3-5 days including reviewer review.

## 8. Alternatives considered

### Alternative A: continue substrate hardening
- What: try a fourth substrate-hardening pass on the work loop.
- Against: three passes already landed with 0 closure credit; signal
  is that the substrate is not the problem.
- For: no new surface to maintain; no governance question.
- Verdict: kept as fallback if this proposal's retreat criterion
  fires.

### Alternative B: loosen M6.7 Done-when
- What: redefine the 8h proof as "3 honest closures across separate
  sessions, no wall-clock constraint".
- Against: breaks the close-gate contract the M6.7 spec makes; future
  reviewers will not be able to audit M6.7 closure on a single proof
  artifact. Sets precedent for softening close gates under pressure.
- For: shortest path to a M6.7 `done` label.
- Verdict: rejected unless all other options fail. Softening close
  gates under pressure is the governance failure mode M6.7 exists to
  prevent.

### Alternative C: jump to M6.9 Phase 1 immediately
- What: start M6.9 Phase 1 without closing M6.7.
- Against: violates the ROADMAP_STATUS ordering the user chose; M6.9
  build under a broken supervised loop will compound the stall
  problem into durable memory.
- For: M6.9 reasoning-trace might indirectly fix the stall.
- Verdict: rejected. M6.9 needs a working loop as substrate.

### Alternative D: full §5.1 Streaming Tool Executor now
- What: implement parallel tool execution as the unstick.
- Against: large commit (~1-2 weeks), async refactor of work loop
  while governance is in flux. High regression risk. The stall may or
  may not be fully fixed by parallel tool exec alone.
- For: biggest long-term compound gain across all future iterations.
- Verdict: correct move after this proposal closes, not during M6.7
  unstick. Listed in this proposal's retreat criterion as the next
  escalation.

## 9. Risks

1. **Explorer misuse**: mew might call Explorer for work that should
   be a direct main-loop read. Mitigation: reviewer steering during
   the 3 Explorer-involving iterations; cap on Explorer invocations
   per turn (proposal: 3).
2. **Todo over-granularity**: mew might write todos at every
   micro-step and spend more time on list maintenance than on work.
   Mitigation: reviewer can see the list in `mew focus` and steer;
   prompt guidance says todos are for multi-step plans, not micro
   tasks.
3. **Scope creep**: temptation to add multi-Explorer concurrency,
   write-capable Explorer, or cross-session todos. Mitigation: this
   proposal is the scope contract. Anything beyond requires a new
   proposal.
4. **Proof-credit confusion**: an iteration that lands an enabler
   might look like M6.7 proof credit. Mitigation: explicit §5 rule
   that enablers do not count toward 8h proof.
5. **Retreat criterion not fired**: the stall might reduce but not
   vanish, leaving ambiguity. Mitigation: retreat criterion is
   explicit (3+3 iterations); reviewer judgment on ambiguity defaults
   to "escalate to §5.1 Streaming".

## 10. Instructions for implementation agent

When reviewer approval of this proposal is recorded:

1. **Do not edit ROADMAP.md**. M6.7 remains `in_progress`; no new
   milestones are registered by this proposal.
2. **Update `ROADMAP_STATUS.md`** Active Milestone Decision block
   with a dated entry recording the pause and the approved scope
   (Explorer + Todo enablers, fresh queue on resume).
3. **Update `docs/M6_7_SUPERVISED_8H_PROOF_PLAN_2026-04-21.md`** with
   a "Paused for unstick" section citing this proposal, listing the
   soft-stopped candidates, and noting that the queue will refresh
   on resume.
4. **Implement in the order listed in §7**. Six reviewer-gated
   iterations under M6.7 rules. Do not bundle.
5. **Do not modify M6.7 governance, scope-fence behavior, or
   Done-when criteria** as part of this work.
6. **After the six iterations land**, write a short
   `docs/M6_7_UNSTICK_OUTCOME_2026-04-21.md` recording whether the
   stall pattern reduced, persisted, or vanished, with evidence per
   iteration. Reviewer decides whether M6.7 proof resumes on a fresh
   queue or the retreat criterion fires.

## 11. Why this is written as a proposal, not as an edit

M6.7 is the active governance milestone. Silently pivoting from
substrate hardening to adopting reference patterns is exactly the
kind of drift M6.7 exists to prevent. Presenting the pivot as a
reviewer-approved proposal keeps the decision durable and auditable,
matches the shape of
`docs/PROPOSE_MILESTONES_2026-04-21_M6_8_M6_9.md`, and makes the
retreat criterion (§6) explicit so future reviewers can re-audit the
choice.
