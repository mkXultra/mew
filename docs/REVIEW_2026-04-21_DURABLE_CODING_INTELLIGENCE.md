# Durable Coding Intelligence — Design for M6.9 (proposed)

Status: proposal, not yet ROADMAP-registered.
Assessed: 2026-04-21.
Position: slots between M6.8 (Task Chaining, also not yet registered) and M7.
M6.7 remains the active milestone and is not paused by this document.

## 1. Why this milestone exists

M6.5 proved mew can reach a reviewable edit quickly. M6.6 proved mew can finish
a coding task with Codex-parity quality and zero rescue edits. M6.7 is proving
that mew can do that under a supervised self-hosting loop.

Everything on that ladder is **parity work**: mew catches up to what Codex CLI
already does inside a single session. None of it uses mew's one unique asset —
durable state across sessions.

A mew agent that has touched its own repo 100 times should be measurably
faster and more accurate than Codex CLI on task 101. Today, it is not. This
milestone closes that gap.

The target is not "more memory." It is: **each coding iteration teaches the
next one, without the human having to teach the same thing twice.**

## 2. Success definition

M6.9 is `done` when all of the following hold on the `mew` repo itself,
measured under the M6.7 supervised loop:

1. **Monotone improvement**: on a predeclared set of 10 repeated task shapes,
   the median wall time per task decreases over the first 5 repetitions,
   with no increase in reviewer rescue edits.
2. **Reviewer-steering reuse**: at least 3 reviewer corrections from past
   iterations fire as durable rules in later iterations (measured via
   session log instrumentation), and at least 1 would have caused a
   rescue edit if not caught.
3. **Failure shield reuse**: at least 2 previously reverted approaches are
   blocked pre-implementation by durable memory in a later iteration.
4. **Structure-aware retrieval**: at least 80% of first-read file lookups
   in a post-Phase-1 iteration are served by the durable symbol/pair
   index rather than fresh search. Measurement protocol:
   - *first-read file lookup* = the first `read` tool call in a work
     session for a given `(module, symbol_name)` pair, excluding reads
     the reviewer explicitly requested.
   - *served by the index* = the target path was returned by an index
     query before the `read` call, logged as `index_hit=true` in the
     session trace.
   - *post-Phase-1 iteration* = any M6.7 supervised iteration that
     starts after Phase 1 Deliverable 4 has landed and before Phase 2
     Deliverable 2 (ranked recall) starts. Measured across 3
     consecutive such iterations; ratio taken over the union of
     first-read lookups.
5. **Drift control holds**: drift canary stays green across 5 consecutive
   iterations while memory accumulates; at least 1 novel-task injection
   forces mew off memory and the agent cleanly falls back to exploration.
6. **Rehearsal proof**: after a deliberate 48h gap (or simulated
   alignment-decay pass), mew recovers prior convention usage within one
   iteration via a rehearsal pass, without reviewer steering.
7. **Reasoning-trace reuse**: at least 2 iterations explicitly recall a
   past reasoning trace (not just a rule) and a reviewer confirms the
   recall shortened the deliberation. At least 1 of those recalls is on
   an abstract task (refactor, design-level) rather than a mechanical
   edit.

All 7 must be reproducible. Credit gates:
- No rescue edits in the proof iterations.
- Proof artifacts recorded per M6.7 shape (`docs/M6_9_*_ITERATION_*.md`).

## 3. Non-goals

- Not a fine-tuning milestone. No model weight updates. All learning is in
  durable artifacts read into the prompt at recall time.
- Not an attempt to make mew autonomous. Reviewer-gated supervision from
  M6.7 stays in place for every M6.9 iteration.
- Not a general memory refactor. Existing typed/scoped memory (§5.12) and
  active memory recall (§5.14) remain. M6.9 layers coding-specific
  durable intelligence on top.
- Not cross-project. M8 (Identity) handles cross-project durability. M6.9
  stays inside a single repo.

## 4. Engineering precedents (verified, repo-local)

All paths under `references/fresh-cli/`.

### 4.0 Existing mew infrastructure that M6.9 layers on top

M6.9 does not rebuild mew's memory stack. It extends it. The
implementation agent must treat the following as already-shipped and
identify the concrete code surfaces during the delta-doc step (§10),
not re-spec them:

- **§5.12 typed/scoped memory** — memory entries already have a type
  discriminator and scope. M6.9 adds five coding-domain values to that
  discriminator. Concrete code surfaces (module paths, schema file,
  recall API) are to be enumerated in the delta doc before Phase 1
  code lands.
- **§5.14 active memory recall** — the recall-at-prompt-time pipeline
  already exists. M6.9 adds the ranked recall scorer (Phase 2) and the
  `revise()` pass (Phase 1 D3) as hooks on that pipeline; it does not
  replace the pipeline.
- **M3 context checkpoint** — session re-entry already restores prior
  state. M6.9 reasoning-trace (Phase 2) is additional, not a
  replacement.
- **Snapshot (§5.11)** — evolution-safe schema already exists for
  durable state files. M6.9 writes to `.mew/durable/` follow the same
  schema discipline.

If any of these surfaces has diverged from the M6.9 assumptions at
delta-doc time, that divergence must be flagged back before Phase 1
coding begins.

### 4.1 claude-code — live in-session memory + typed taxonomy

| Handhold | Path | What mew can borrow |
| --- | --- | --- |
| Typed memory taxonomy (user/feedback/project/reference) | `claude-code/src/memdir/memoryTypes.ts:14-105` | Coding-domain taxonomy: reviewer-steering / failure-shield / file-pair / task-template |
| CLAUDE.md depth-ordered loader | `claude-code/src/utils/claudemd.ts:1-100` | Project-local durable rules override global ones |
| Daily log → nightly distillation | `claude-code/src/memdir/paths.ts:236-251` + `claude-code/src/skills/bundled/remember.ts:9-82` | Session raw → distilled skills; mew can tie this to iteration boundaries instead of calendar days |
| Memory freshness warnings | `claude-code/src/memdir/memoryAge.ts:1-54` | Recall-time staleness caveats |
| File-history snapshot (edit locality) | `claude-code/src/utils/fileHistory.ts:30-80` | Recent-touch prioritization |
| Symbol context extraction | `claude-code/src/tools/LSPTool/symbolContext.ts:20-90` | Starting point for structure-aware indexing |
| Skill schema for durable workflow | `claude-code/src/skills/bundled/{remember,verify,stuck}.ts` | Task-template persistence format |

### 4.2 codex — consolidation discipline + failure shields

| Handhold | Path | What mew can borrow |
| --- | --- | --- |
| Phase 1 rollout triage | `codex/codex-rs/core/templates/memories/stage_one_system.md:1-150` | Per-iteration extraction gate: "Will a future agent act better?" |
| Failure shields as first-class type | same file, lines 40-100 | Revert history and Codex corrections ranked above procedural notes |
| Phase 2 consolidation | `codex/codex-rs/core/templates/memories/consolidation.md:1-150` | Raw → `MEMORY.md` + `skills/` + rollout summaries, INIT vs INCREMENTAL |
| Drift triage (verify vs annotate) | `codex/codex-rs/core/templates/memories/read_path.md:1-50` | Decision table for when to trust vs re-verify durable facts |
| Compact prompt template | `codex/codex-rs/core/templates/compact/prompt.md:1-10` | Minimum-viable handoff structure |

### 4.3 openclaw — skill schema in the wild

| Handhold | Path | What mew can borrow |
| --- | --- | --- |
| Skill schema | `openclaw/.agents/skills/openclaw-pr-maintainer/SKILL.md:1-76` | YAML frontmatter + step-by-step workflow + evidence bar |
| Skill directory layout | `openclaw/.agents/skills/` (verified: root `AGENTS.md` only; no scoped AGENTS.md) | Per-task-shape skill folders |

## 5. Research grounding (verified arXiv IDs)

All IDs confirmed via arxiv.org on 2026-04-21.

### 5.1 Memory architecture
- Sumers et al., *Cognitive Architectures for Language Agents* (CoALA),
  arXiv:2309.02427. Canonical split: working / episodic / semantic /
  procedural memory; internal vs external actions.
- Packer et al., *MemGPT: Towards LLMs as Operating Systems*,
  arXiv:2310.08560. OS-like paging between main context and external store.
- Park et al., *Generative Agents*, arXiv:2304.03442. Memory stream +
  reflection tree; retrieval = recency × importance × relevance.
- Xu et al., *A-MEM: Agentic Memory for LLM Agents*, arXiv:2502.12110.
  Zettelkasten-style structured attributes; new memories *rewrite* old
  links.
- Feng et al., *Thought-Retriever: Don't Just Retrieve Raw Data, Retrieve
  Thoughts for Memory-Augmented Agentic Systems*, arXiv:2604.12231.
  Retrieve *past intermediate reasoning* instead of raw chunks;
  self-evolving long-term memory; deeper thoughts retrieved for more
  abstract questions. +7.6% F1 / +16% win rate.

### 5.2 Skill libraries and lifelong learning
- Wang et al., *Voyager*, arXiv:2305.16291. Automatic curriculum, skill
  library of verified executable code, iterative prompting with errors
  and self-verification.
- Zhao et al., *ExpeL*, arXiv:2308.10144. Recall of successful trajectories
  + abstracted insights from success/failure pairs.
- Qi et al., *WebRL*, arXiv:2411.02337. Self-evolving online curriculum
  generated from past failed attempts.

### 5.3 Self-reflection and failure memory
- Shinn et al., *Reflexion*, arXiv:2303.11366. Verbal reflection in an
  episodic buffer, no weight updates.
- Madaan et al., *Self-Refine*, arXiv:2303.17651. Generator / critic /
  refiner roles inside a single LLM.
- Allard et al., *Experiential Reflective Learning*, arXiv:2603.24639
  (ICLR 2026 MemAgents Workshop). Cross-task consolidation of reflections
  into transferable heuristics; selective retrieval beats few-shot.

### 5.4 Retrieval-augmented coding
- Zhang et al., *RepoCoder*, arXiv:2303.12570. Iterative retrieve-generate
  loop; draft as re-retrieval query.
- Bairi et al., *CodePlan*, FSE 2024. Repo edit as a plan over a
  dependency graph.
- Zhang et al., *AutoCodeRover*, arXiv:2404.05427. AST/method-level search
  APIs; structure-aware localization.
- Zhang et al., *CodeRAG*, arXiv:2509.16112. Log-prob-guided query
  construction, multi-path retrieval, preference-aligned reranking.

### 5.5 SWE-agent family
- Yang et al., *SWE-agent*, arXiv:2405.15793. ACI design dominates gains.
- Xia et al., *Live-SWE-agent*, arXiv:2511.13646. Inference-time
  self-evolution study.

### 5.6 Continual learning
- Huang et al., *Self-Synthesized Rehearsal* (ACL 2024). LLM generates its
  own rehearsal instances.
- *Spurious Forgetting in Continual Learning of Language Models*, ICLR
  2025. Most "forgetting" is alignment decay, cheap to re-anchor.

### 5.7 Case-based reasoning
- Wiratunga et al., *Review of CBR for LLM Agents*, arXiv:2504.06943.
- Classical Aamodt-Plaza Retrieve-Reuse-Revise-Retain cycle.

### 5.8 Hindsight replay
- Hu et al., *Sample-Efficient Online Learning in LM Agents via Hindsight
  Trajectory Rewriting*, arXiv:2510.10304.
- Ding, *AgentHER: Hindsight Experience Replay for LLM Agent Trajectory
  Relabeling*, arXiv:2603.21357 (ICLR 2026 MemAgents Workshop).

### 5.9 Human correction alignment
- Kaufmann et al., *A Survey of RLHF*, arXiv:2312.14925.
- RLTHF (2024): reward-model-driven targeted human-review routing.

## 6. Design principles

Seven principles. Each Phase in §7 must reference which principles it
applies and which it defers.

### P1. Typed durable memory for coding
Not a single memory bag. Five coding-domain types, each with its own
retention and recall rules:
- **reviewer-steering**: Codex / human corrections as rules with
  `why` + `how-to-apply`. Source: claude-code feedback type + CoALA
  semantic memory.
- **failure-shield**: revert history and failed approaches with
  symptom → root-cause → fix → stop-rule. Source: codex
  `stage_one_system.md`.
- **file-pair / symbol-edge**: verified structural relationships
  (source ↔ test, import edges, paired modules). Source: AutoCodeRover
  + CodePlan.
- **task-template**: supervised iteration shapes as reusable workflow
  artifacts. Source: openclaw SKILL.md + claude-code /remember /verify.
- **reasoning-trace**: distilled chain-of-thought from past iterations
  stored as `(situation, reasoning, verdict)` triples. Not the raw
  transcript — a thought-distilled form the next iteration can actually
  graft onto its own deliberation. Abstract tasks (refactor planning,
  design choices) benefit most. Source: Thought-Retriever
  (arXiv:2604.12231); CoALA procedural memory; ExpeL insights.

Sub-principle — **content favors thought-distilled form over raw
snippet**. Every type except file-pair carries a short reasoning
field explaining the `why`. file-pair stays structural. This is
applied to all writes, not only reasoning-trace entries: a reviewer-
steering rule without `why` is rejected at write gate; a failure-
shield without root-cause is rejected; a task-template without
rationale for ordering is rejected.

### P2. Outcome-gated retention, with an explicit Revise step
Nothing enters durable memory without a validation gate. Retrieval
always goes through an adapt-to-this-iteration step before reuse, not
raw copy-paste.
- Write gate (universal requirement): drift canary green at the close
  of the iteration that produced the write. Per-type additional
  requirements are defined in the Phase 1 write-gate matrix (§7.1).
- Reuse gate: `revise(memory, current_context) → adapted`. See
  `revise()` spec in §7.1 Deliverable 3.
- Grounded in: Voyager self-verification; CBR Revise + Retain.

### P3. Structure-aware index as the primary key
Durable coding knowledge is keyed to symbol / call-graph edges, with file
paths as secondary keys. Refactors that rename files do not invalidate
memory.
- Canonical Phase 1 schema (single source of truth; supersedes any
  earlier informal mention in this doc):
  ```
  key:   (module, symbol_kind, symbol_name)
  value: {
    defined_in:  list[path]           # paths where the symbol is defined
    tested_in:   list[path]           # paired test files that exercise it
    edited_with: list[(module, symbol_name)]   # co-edit neighbours
    last_seen:   iso8601_utc          # last iteration touching this entry
    confidence:  float ∈ [0,1]        # default 1.0; decayed per Phase 3
  }
  ```
  - `module` = the Python import path relative to `src/`, e.g.
    `mew.work_session`. Not the file path.
  - `symbol_kind` ∈ `{function, method, class, const}`.
  - `symbol_name` uses the dotted form for nested scopes
    (`ClassName.method_name`).
  - All list values are deduplicated and lexicographically sorted for
    stable diffs.
- Grounded in: AutoCodeRover AST-level search; CodePlan dependency
  graph; claude-code `symbolContext.ts` as seed regex.

### P4. Memory as a mutable graph
New memories can **rewrite** old ones. Writing a reviewer-steering rule
checks for conflicts with existing rules and either refines, supersedes,
or links them. Memory is not append-only.
- Grounded in: A-MEM link evolution; Generative Agents reflection tree.
- Implementation: each memory entry has `supersedes`, `refined_by`,
  `related` edges; consolidation pass walks and rewrites.

### P5. Recall scored by recency × importance × relevance
Pure embedding similarity is a weak baseline for code. Retrieval also
weights recent touch on the symbol, and reviewer-assigned importance
(how often the rule has fired; whether it caught a would-be rescue).
- Grounded in: Generative Agents; CodeRAG's "retrieval quality, not
  context size, is the bottleneck."

### P6. Hindsight harvest from failed iterations
Every iteration produces a trace. Sessions that end in revert or blocked
finish are run through a relabeling pass: what could this trajectory
have been a successful demonstration of? Candidate cases land in a
hindsight queue that reviewer approves before they become durable.
- Grounded in: AgentHER; Hu et al. hindsight rewriting.
- Constraint: hindsight cases enter reviewer approval queue, not
  durable memory directly, to prevent polluting with imagined skills.

### P7. Scheduled rehearsal + novel-task injection
Memory suffers alignment decay even without storage loss. Two
counter-measures:
- **Rehearsal**: scheduled passes re-expose mew to canonical project
  conventions and "why we do X this way" notes.
- **Novel-task injection**: periodic tasks that falsify reliance on
  memory. mew must complete them with exploration; memory-only
  shortcuts should fail. Measures real coverage.
- Grounded in: Self-Synthesized Rehearsal; Spurious Forgetting.

## 7. Phases

Four phases, ordered by value × implementation cost. Each phase lands in
the M6.7 supervised loop — meaning each feature is built by mew itself
under reviewer gating, or by an external agent on a paused M6.7 if we
choose to accelerate. That choice is a governance call, not a design
call; the design below does not depend on it.

### Phase 1 (Tier S) — baseline that stops the bleeding

Principles applied: P1 (5 types; reasoning-trace is schema-only in
Phase 1, populated in Phase 2), P2 (write+reuse gates), P3 (minimum
symbol index, canonical schema above).

Deliverables:

1. **Coding memory taxonomy** with 5 types (reviewer-steering,
   failure-shield, file-pair/symbol-edge, task-template,
   reasoning-trace). Stored under existing typed-memory infrastructure
   (§5.12) with `memory_kind` discriminator. Phase 1 defines the schema
   for all 5 and populates the first 4 from iteration evidence; the
   reasoning-trace harvester lands in Phase 2, but the slot — including
   the `abstraction_level ∈ {shallow, deep}` field and `shallow_of`
   back-edge reserved for the deep form — exists from day one so
   downstream code does not need to be rewritten.

2. **Write-gate matrix** (per-type, canonical). No automatic promotion
   from raw session logs. The universal requirement from P2 (drift
   canary green at iteration close) applies in addition to the per-type
   requirements below.

   | Type | Phase 1 write gate |
   | --- | --- |
   | `reviewer-steering` | reviewer explicit approval of the extracted rule + `why` present + `how-to-apply` present; rules missing `why` or `how-to-apply` are rejected |
   | `failure-shield` | reviewer explicit approval + full symptom → root-cause → fix → stop-rule fields populated; entries missing root-cause are rejected |
   | `file-pair / symbol-edge` | focused-test green for the paired module + structural evidence (at least one observed co-edit or same-session read of both targets); no reviewer approval required because the evidence is structural, but reviewer can veto via §7.1 Deliverable 6 |
   | `task-template` | reviewer explicit approval of the template shape + rationale field for ordering present; entries without rationale are rejected |
   | `reasoning-trace` | *not populated in Phase 1*; schema present only. Phase 2 Deliverable 4 specifies the write gate. |

3. **Reuse gate — `revise()` pass**. Phase 1 uses a deterministic
   structured-rewrite implementation (no model call). A model-backed
   variant is deferred to Phase 2/3 (§11 open question 1). Spec:

   ```
   revise(memory_entry, current_context) -> adapted_entry | dropped
   
   inputs:
     memory_entry    - a durable entry returned by the current recall
                       pipeline. In Phase 1 this is the existing §5.14
                       active memory recall result. In Phase 2+ this is
                       the output of the ranked recall scorer.
     current_context - {target_symbols, target_modules, active_task_id,
                        active_write_roots}
   steps:
     1. Resolve each symbol reference in memory_entry against the
        current symbol index. If any referenced symbol is no longer
        present, mark the entry as dropped with reason
        "symbol_not_found" and return.
     2. Rewrite file-path references in memory_entry to the current
        paths returned by step 1 (paths may have moved under refactor;
        symbol identity is primary).
     3. If memory_entry declares preconditions (failure-shield
        stop-rules, reviewer-steering applicability tags) and none of
        the preconditions match current_context, mark as dropped with
        reason "precondition_miss" and return.
     4. Return adapted_entry with the rewritten references.
   
   behaviour:
     - deterministic, no model call
     - on failure, drops the entry rather than raising
     - all drop reasons are logged to the session trace
   ```
   A drop is not an error: it means the memory was recalled but is not
   applicable right now. Dropped entries stay in durable memory.

4. **Minimum symbol/pair index** — populated incrementally from
   successful iterations (no Phase 1 full-repo scan required). Uses the
   canonical P3 schema (§6 P3). Seed the symbol-extraction step from
   `references/fresh-cli/claude-code/src/tools/LSPTool/symbolContext.ts`.
   Persistence: single JSON file at `.mew/durable/symbol_index.json`,
   rewritten atomically per write.

5. **Reviewer-diff capture**. Every reviewer approval of a dry-run diff
   records a triple.
   - Storage: sidecar JSONL at `.mew/durable/reviewer_diffs.jsonl`.
     *Not* a typed memory entry in Phase 1 (these are raw material for
     the Phase 4 preference store, not recalled directly in Phases 1-3).
   - Triple shape:
     ```
     {
       iteration_id: str,
       approval_id: str,
       ai_draft:           unified_diff,   # the diff mew proposed
       reviewer_approved:  unified_diff,   # the diff the reviewer accepted,
                                           # including any reviewer edits
       ai_final:           unified_diff,   # the diff actually landed
       approved_at:        iso8601_utc,
       reviewer:           str,            # reviewer agent/user id
       steering_extracted: bool,           # was a reviewer-steering entry
                                           # derived from this triple?
     }
     ```
   - Completion rule: a triple is complete only when `ai_final` exists
     (i.e. the landing commit is recorded). The triple is written at
     `ai_final` time, not at approval time, to avoid half-records.
     Approved-but-never-landed diffs (reviewer approves a dry-run but
     the iteration later reverts or blocks finish before landing) are
     **not** recorded as triples. They may still produce a
     reviewer-steering candidate via the separate extraction path.
   - Approval definition: a triple is "approved" iff the reviewer
     emitted an explicit approve action on the dry-run surface and
     `reviewer_approved` is the exact patch after any reviewer edits.
     Instructional comments without a corresponding approve action are
     captured separately as reviewer-steering candidates, not as
     diff triples.

6. **Reviewer veto surface (Phase 1 minimum stub)**. A reviewer command
   that marks a single durable entry stale or deleted. Scope in
   Phase 1 is minimum: single-entry targeting, no edge propagation.
   Edge propagation is added in Phase 2 Deliverable 5 (memory
   invalidation surface). This stub exists in Phase 1 so that early
   bad writes can be cleaned up before they accumulate.

Proof:
- 3 supervised M6.7 iterations after Phase 1 lands. Each iteration
  must exercise at least one Phase 1 deliverable as follows:
  - at least one recall that fires `revise()` on a real memory entry
    (exercises D3), with the revise trace logged;
  - at least one `read` tool call resolved via the symbol index, logged
    as `index_hit=true` (exercises D4);
  - at least one reviewer approval producing a complete triple written
    to the JSONL sidecar (exercises D5);
  - at least one reviewer-steering rule reused (not re-derived) across
    the 3 iterations (exercises D1+D2).
- At least 1 reviewer-steering rule fires as a rule rather than as a
  prose recall.
- At least 1 test of the reviewer veto stub (D6): write a bad entry,
  veto it, confirm it no longer fires in a subsequent recall.

### Phase 2 (Tier S/A) — graph rewrite and hindsight

Principles applied: P4 (mutable graph), P5 (scored recall), P6 (hindsight
harvest).

Deliverables:

1. **Link-evolving consolidation**: a consolidation pass that, on write,
   walks related entries and rewrites `supersedes` / `refined_by` /
   `related` edges. Runs at iteration boundary plus on explicit
   `/consolidate`.
2. **Ranked recall**: recall scorer combining recency, importance
   (firing count, rescue-prevention count), and relevance (symbol
   overlap, task-shape similarity). Replaces the current raw-relevance
   recall.
3. **Hindsight harvester**: on blocked-finish or revert iterations, a
   relabeling pass generates candidate cases ("this trajectory was a
   successful exploration of X-not-Y"). Lands in a reviewer queue.
   Approved cases enter durable memory **by mapping into existing
   types**, not as a new 6th type: a relabeled success maps to either
   `failure-shield` (if it warns against a wrong approach) or
   `task-template` (if it generalizes to a reusable workflow). The
   harvester must emit a `target_type` proposal with each candidate so
   the reviewer's approval also selects the destination type.
4. **Reasoning-trace harvester**: at iteration close, a distillation
   pass extracts `(situation, reasoning, verdict)` triples from the
   work-session transcript. Raw transcript is not stored; only the
   distilled thought is. Two abstraction levels produced per trace —
   **shallow** (this specific task) and **deep** (generalizable
   pattern) — so later recall can target the right level for the next
   question. Reviewer approves before entries enter durable memory.
   Co-located with hindsight harvester because both distill from
   trace: hindsight extracts *what was achieved*, reasoning-trace
   extracts *how it was thought through*.
5. **Memory invalidation surface**: reviewer command that marks an
   entry stale or deleted, propagating to related edges.

Proof:
- 1 iteration shows a reviewer-steering rule being refined (not
  duplicated) by a new session.
- 1 iteration closes with at least 1 hindsight case entering the
  reviewer queue.
- 1 iteration closes with at least 1 reasoning-trace entry (shallow +
  deep pair) entering the reviewer queue, and a later iteration
  recalls the deep form on a structurally different task.
- Ranked recall surfaces at least 1 non-obvious memory (not the
  top-cosine hit) that a reviewer confirms was the right one.

### Phase 3 (Tier A) — rehearsal and novelty

Principles applied: P7 (rehearsal + novel-task injection).

Deliverables:

1. **Scheduled rehearsal pass**: on a cadence (every N iterations or T
   hours), mew runs a short no-op iteration that reads canonical
   convention memories and records an ack. No code changes.
2. **Novel-task injector**: a task-selector mode that deliberately
   chooses a task for which memory cannot short-circuit the work.
   mew must complete it by exploration. Tracked as a memory-coverage
   metric: fraction of tasks where memory reuse would have been
   incorrect.
3. **Confidence decay**: entries gain a decay factor over wall-time
   and edits to the referenced symbol. Decay does not delete; it
   lowers recall priority and triggers re-verification at use.

Proof:
- 1 rehearsal pass recovers prior convention usage after a simulated
  48h gap.
- 3 novel-task injections; mew completes them with exploration; memory
  is not falsely invoked.
- 1 entry is decayed-then-re-verified across an iteration boundary.

### Phase 4 (Tier B) — curriculum and habit compilation

Principles applied: extension of P7 + P1 task-template.

Deliverables:

1. **Failure-clustered curriculum**: when M6.8 task chaining is live,
   the chooser weights tasks whose shape clusters near recent failures.
   Grounded in: Voyager automatic curriculum, WebRL failure-seeded
   curriculum.
2. **Habit compilation**: task-template entries whose recall scores
   and success rates cross a threshold are compiled into deterministic
   task-runner scripts. These run without model inference for the
   compiled portion, with a model-backed fallback on mismatch.
3. **Preference store**: reviewer-diff triples from Phase 1 are
   indexed as `(context, dispreferred, preferred)` pairs, retrievable
   at draft time. No fine-tuning — prompt-time conditioning only.

Proof and positioning: Phase 4 is only meaningful after M6.8 task
chaining. Registering here for completeness; actual work lands after
M6.8 closes.

## 8. Drift and evolutionary-pressure controls

Durable memory expands the attack surface for drift. The controls below
are part of the milestone, not optional extras.

1. **Drift canary extended**: current M6.7 drift canary grows to include
   a memory-integrity check — durable entries resolve against current
   code, stale ones are flagged.
2. **Novel-task injection** (P7) measured as a coverage metric. If a
   scheduled iteration could have been passed purely by memory reuse,
   that counts against memory coverage, not for it.
3. **Reviewer veto**: reviewer can mark any durable entry as invalid
   with a reason. In Phase 1, veto is single-entry only (§7.1 D6). In
   Phase 2, veto extends to propagate along `supersedes` / `refined_by`
   / `related` edges (§7.2 D5).
4. **Rehearsal pass** (P7) as a positive-pressure signal: if rehearsal
   finds convention recall already correct, it confirms no alignment
   decay.
5. **Write-path audit**: every durable write records `written_by`,
   `approved_by`, `approved_at`, source iteration id. No anonymous
   writes.
6. **Growth budget**: each memory type has a soft cap. Exceeding the
   cap forces a consolidation pass rather than accepting more entries.
   reasoning-trace has the tightest cap of the 5 types: traces are the
   easiest to over-generate and the hardest to sanity-check later, so
   the cap forces consolidation into deep-form abstractions before
   shallow-form volume explodes.
7. **Comparative baseline retained**: M6.6 comparator tasks should be
   rerun after each Phase with and without durable recall. Gains
   attributable to durable memory must be measurable at that comparator
   level.

## 9. Dependencies

```
M6.7 Supervised Self-Hosting Loop  (active, not paused by M6.9 proposal)
  │
  ├── remainder of M6.7:
  │     - scope-fence hardening
  │     - 8h supervised proof
  │
  ├── M6.8 Task Chaining  (proposed, not registered)
  │     supervisor-gated task self-selection
  │
  └── M6.9 Durable Coding Intelligence  (this doc)
        Phase 1 → Phase 2 → Phase 3 → [Phase 4 requires M6.8]
```

Ordering decision: **M6.7 completes first** (including 8h supervised
proof). Then Phase 1-3 of M6.9 can begin under M6.7 supervision. M6.8
can proceed in parallel or precede Phase 4, but Phase 4 depends on M6.8.

This ordering was user-selected after weighing "build Durable on top of
a working loop" vs "build Durable first so all remaining iterations
benefit." The user judged that (a) Durable is long tail and risky to
build without a stable loop, and (b) supervisor gating contains the
drift risk of chaining without Durable.

## 10. Implementation handoff notes

For the implementation agent:

1. **Do not start by writing code.** Start by reading the engineering
   precedents (§4) and the 3 canonical research papers: CoALA
   (arXiv:2309.02427), Voyager (arXiv:2305.16291), AutoCodeRover
   (arXiv:2404.05427). Write a short delta doc before touching
   `src/mew`. The delta doc must contain, at minimum:
   - **Existing-infrastructure map**: concrete code surfaces for §5.12
     typed memory, §5.14 active recall, §5.11 snapshot, and M3 context
     checkpoint — module paths, public APIs, schema files. Flag any
     divergence from §4.0 assumptions.
   - **Per-deliverable mapping for Phase 1 D1-D6**: which new files or
     existing files each deliverable touches; the public API surface
     each introduces.
   - **Schema decisions**: the `memory_kind` discriminator values, the
     reasoning-trace schema shape (including shallow/deep fields
     reserved for Phase 2), and the reviewer-diff JSONL layout, all
     reconciled with the existing typed-memory schema.
   - **Telemetry plan**: which fields in the session trace are added
     to measure the §2 success criteria, in particular criterion #4
     (`index_hit` logging) and criterion #7 (reasoning-trace recall
     attribution).
   - **Adopt/reject list**: from §4 engineering precedents and §5
     research grounding, name each pattern and state adopted / adapted
     / rejected, with reason.
   - **Open questions touched**: which §11 open questions Phase 1
     answers (if any) and which remain deferred.
2. **Land Phase 1 as one bounded M6.7 iteration per deliverable.**
   Six iterations (D1 through D6), each reviewer-gated. Do not bundle.
3. **Do not replace existing typed-memory scaffolding.** §5.12 and §5.14
   stay. Add the coding-domain taxonomy as a `memory_kind` layer on
   top.
4. **Instrument from day one.** Every durable memory read, write,
   fire-count, rescue-prevention count, and revise invocation is
   logged. The proof gates in §2 depend on this telemetry existing
   before the proof iteration runs.
5. **Reviewer tooling first.** Phase 1 must surface the reviewer veto
   command before writing many durable entries, or early bad entries
   are hard to clean up.
6. **Hindsight harvester (Phase 2) is the highest risk component.**
   It can pollute durable memory with plausible-but-wrong cases.
   Gate it behind reviewer queue from the first commit, not as a
   retrofit.

## 11. Open questions

These are unresolved research-adjacent choices that the implementing
agent should flag if it has a preference, not silently decide:

1. **Revise step specification**: does `revise(memory, context)` use a
   model call, a structured rewrite, or both? Model calls cost
   latency; structured rewrites may be too rigid. CBR literature
   (§5.7) describes the space but does not specify for coding.
2. **Hindsight relabeling grounding**: what prevents hindsight from
   generating imagined goals? Candidates: require the relabeled goal
   to be achievable from repo state at trace start, require reviewer
   approval for the first N per iteration, bound by a similarity
   threshold to existing tasks.
3. **Structure index refresh cadence**: full reindex vs incremental
   updates on diff. Incremental is cheaper but risks drift. AutoCode-
   Rover uses full parse; for mew's repo size this should be tractable.
4. **Rehearsal frequency**: every N iterations or on time cadence?
   Time cadence survives iteration-rate changes. N-cadence ties to
   real work density. No clear literature answer.
5. **Novel-task injection source**: does mew generate novel tasks, or
   does reviewer supply them? Voyager generates them; RLTHF supplies
   them. mew's supervised mode leans toward reviewer supply; Phase 4
   may flip to generation once task chaining is live.
6. **Preference store (Phase 4) retrieval format**: inject `(dispre-
   ferred, preferred)` pairs as in-context examples, or as delta
   rules? Fine-tuning is out of scope (§3).
7. **Reasoning-trace raw vs distilled**: the design stores distilled
   thoughts, not raw transcripts. Thought-Retriever argues this is
   correct for abstraction and cost. Open question: should a small
   window of raw transcript be retained for reviewer audit of the
   distillation step, or is reviewer approval at distill time
   sufficient?
8. **Reasoning-trace abstraction levels**: Phase 2 defines two levels
   (shallow / deep). Should there be a third, meta level ("what kind
   of task is this at all") recalled for unfamiliar task types? No
   clear literature answer; adding later is cheaper than removing.

## 12. Expected impact

If M6.9 lands fully:

- Iteration wall time decreases monotonically on repeated task shapes.
- Reviewer rescue rate stays at zero, with reviewer time per iteration
  dropping as steering reuse grows.
- `mew` becomes the first coding agent in `references/fresh-cli/` whose
  competitive edge is durable state, not session-local capability.
- The 8h supervised M6.7 proof (scheduled after M6.7 scope-fence
  hardening) is rerun with Phase 1-3 active. That proof becomes
  evidence for durable-memory advantage, not just Codex parity.
- M10 (Multi-Agent Residence) and M11 (Inner Life) become well-
  founded: a durable agent with a coding-competent memory has the
  substrate those milestones assume.

This is the first milestone where mew stops copying reference CLIs and
starts using what they structurally cannot have.
