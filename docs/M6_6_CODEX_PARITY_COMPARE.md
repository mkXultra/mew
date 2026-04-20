# M6.6 Codex CLI Parity Comparator

Use this document to keep M6.6 measurable. Do not count a task as M6.6 evidence
unless the task was chosen before the run and the trace separates mew-authored
work from Codex rescue edits.

## Gate

M6.6 closes only after three predeclared representative coding tasks pass:

| Task | Shape | Status | Mew run | Codex CLI comparator | Rescue edits |
|---|---|---|---|---|---|
| M6.6-A | Behavior-preserving refactor | `side_by_side_recorded` | #325 / session #311 | `/tmp/mew-m66a-codex-20260420-2316` | 0 |
| M6.6-B | Bug fix with regression test | `side_by_side_recorded` | #324 / session #310 | `/tmp/mew-m66b-codex-20260420-2218` | 0 |
| M6.6-C | Small feature with paired source/test changes | `mew_run_recorded_comparator_deferred` | #327 / session #314 | deferred until M6.6 freeze | 0 |

Comparator note:

- Codex CLI comparator runs are gate evidence, not per-slice critical-path work.
- Once the mew-side M6.6 implementation set is stable, run the remaining
  comparator tasks from that frozen commit in parallel detached worktrees.

Required pass conditions for each task:

- `rescue_edits=0`
- no obvious path hallucination
- no repeated identical broad search/read loop
- focused verifier command chosen by mew
- approval surface shows a reviewable edit before write
- if verification fails, mew performs or proposes a repair loop before asking
  Codex to rescue the implementation

## Reference-Grounded Gate

Do not count M6.6 implementation evidence unless the slice states which
reference pattern it adopts or deliberately rejects.

| Pattern | Reference | M6.6 expectation |
|---|---|---|
| Durable plan state | `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts` and `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` Pattern D | Work sessions keep a durable coding checklist instead of re-deriving intent every turn. |
| Read-only exploration discipline | `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts` and Missing Patterns Pattern A | Implementation starts from scoped exploration and records known paths before editing. |
| Verification agent behavior | `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts` and `docs/REVIEW_2026-04-20_M2_BLOCKERS_FROM_REFERENCES.md` B5 | Mew discovers focused verifier commands and repairs failures before asking for rescue. |
| Streaming/multi-tool execution | `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts` and ADOPT §5.1 | Later M6.6 speed-parity slices should support concurrent safe reads or justify deferral. |
| Snapshot/reentry | `references/fresh-cli/claude-code/src/tools/AgentTool/agentMemorySnapshot.ts` and ADOPT §5.11 | Coding plans survive context compression and resume without rebuilding from chat. |
| Codex patch/review loop | `references/fresh-cli/codex/codex-rs/core/prompt_with_apply_patch_instructions.md`, `references/fresh-cli/codex/codex-rs/core/review_prompt.md`, and Codex core tests | Comparator evidence records patch quality, reviewability, approval behavior, and verifier choice. |

## Bootstrap Integration Gate

Before the three comparator tasks count, mew must implement one small M6.6
infrastructure slice itself. This is the integration test for the gate:

1. Codex creates or approves a small task whose prompt points at this document,
   `ROADMAP.md`, `ROADMAP_STATUS.md`, and the relevant reference docs.
2. Mew runs the work session as implementer and proposes the code/doc edit
   through the normal approval surface.
3. Codex may approve, reject, or steer. Any Codex rescue edit fails the
   bootstrap gate and must be recorded as a blocker instead of being retried or
   counted silently.
4. Focused verification passes.
5. The run is recorded below with the adopted reference pattern, metrics, and
   `rescue_edits=0`.

## Bootstrap Run Record

Status: `success`

Task: #323 `M6.6 bootstrap retry: coding plan state`

Adopted reference patterns:

- Durable plan state: TodoWriteTool-style persistent checklist
- Read-only exploration discipline: exploreAgent-style scoped exploration before edit

Mew run:

- Retry followed the blocked #322 bootstrap after commit `ca9ba94`.
- Mew produced dry-run edits for `src/mew/work_loop.py` (#2182) and
  `tests/test_work_session.py` (#2183).
- Codex reviewed and approved/applied those mew-authored writes (#2184 and
  #2185).
- The resulting patch changed `src/mew/work_loop.py` and
  `tests/test_work_session.py`.
- Reviewer steering was still needed during the run, and one read-root
  permission repair was needed before completion.

Verification: focused pytest passed with 2 tests.

Rescue edits: 0

Caveats:

- This is bootstrap evidence for one small reference-grounded coding-loop slice,
  not full M6.6 closure.
- The retry succeeded without rescue edits, but broader native coding-loop
  robustness still needs follow-up work.

Verdict: bootstrap retry succeeded for the durable coding plan state slice.

## Run Template

Copy this section for each mew and Codex CLI comparator run.

```md
### M6.6-<letter> <tool> run

Task:

Predeclared success criteria:

Start time:
End time:

Metrics:

- first_edit_latency_seconds:
- model_turns:
- search_calls_before_first_edit:
- read_calls_before_first_edit:
- changed_files:
- verifier_commands:
- repair_cycles:
- prompt_context_chars:
- rescue_edits:
- adopted_reference_patterns:

Review:

- correctness:
- minimality:
- reviewability:
- resident_state_reuse:
- notes:

Verdict:
```

### M6.6-A mew run

Task: #325 `M6.6-A comparator: behavior-preserving prompt guidance refactor`

Predeclared success criteria:

- Refactor one dense `build_work_think_prompt` guidance literal into clearer
  adjacent string fragments without changing prompt semantics.
- Keep the diff small and paired across `src/mew/work_loop.py` and
  `tests/test_work_session.py`.
- Codex may steer/review/approve only; no rescue edits.

Start time: 2026-04-20 22:23 JST
End time: 2026-04-20 23:07 JST

Metrics:

- first_edit_latency_seconds: about 2491
- model_turns: 8 before first edit proposal; 10 total
- search_calls_before_first_edit: 2
- read_calls_before_first_edit: 8
- changed_files: `src/mew/work_loop.py`,
  `tests/test_work_session.py`
- verifier_commands:
  `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch --no-testmon`;
  reviewer broader verify:
  `uv run python -m unittest tests.test_work_session`
- repair_cycles: 0
- prompt_context_chars: first edit proposal turn `context_chars=29531`,
  `think.prompt_chars=43427`
- rescue_edits: 0
- adopted_reference_patterns: read-only exploration discipline, Codex
  patch/review loop, paired source/test approval surface

Review:

- correctness: focused verifier passed on apply, then reviewer broader verify
  passed with `395 tests`
- minimality: split one prompt literal into three adjacent strings and added two
  prompt assertions
- reviewability: mew produced a readable paired dry-run batch (#2221/#2222)
  before apply; Codex only approved/applied (#2223/#2224)
- resident_state_reuse: reused prior session #311 context, then benefitted from
  a Codex-authored unblocker that preserved `recent_read_file_windows` during
  full-mode compaction and exposed recent-window metrics
- notes: mew initially looped on narrow source reads (#2217-#2219); reviewer
  steer redirected the next step toward the paired test read (#2220), after
  which mew proposed the edit batch and finished cleanly

Verdict: mew run passed.

### M6.6-A Codex CLI run

Task: same as M6.6-A mew run, executed in a detached worktree at commit
`3ea02ea`.

Predeclared success criteria: same as mew run.

Start time: 2026-04-20 23:16 JST
End time: 2026-04-20 23:17 JST

Metrics:

- first_edit_latency_seconds: about 44
- model_turns: one Codex CLI session
- search_calls_before_first_edit: 1
- read_calls_before_first_edit: 4
- changed_files: `src/mew/work_loop.py`,
  `tests/test_work_session.py`
- verifier_commands:
  `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch --no-testmon`
- repair_cycles: 0
- prompt_context_chars: not recorded; Codex CLI reported
  `input_tokens=160796`, `cached_input_tokens=142592`
- rescue_edits: 0
- adopted_reference_patterns: Codex patch/review loop, read-only exploration
  discipline, focused regression verifier

Review:

- correctness: preferred focused verifier passed with `1 passed in 0.47s`
- minimality: the source change matches the intended readability refactor, and
  the test delta is a single added assertion for the second clause
- reviewability: Codex showed the exact patch before write, then confirmed the
  final two-file diff stat and full diff
- resident_state_reuse: none; this was a fresh detached worktree comparator
- notes: the Codex CLI run converged on the same source refactor as the mew
  run, but with a slightly smaller test delta; `uv` ran successfully without a
  sandbox/cache blocker by creating a local `.venv` in the detached worktree

Verdict: Codex CLI comparator passed with no environment caveat.

### M6.6-B mew run

Task: #324 `M6.6-B comparator: docs-only prompt safety bugfix`

Predeclared success criteria:

- Fix the prompt-safety ambiguity observed in #323 where docs-only single
  `edit_file` work was blocked by code-write batch guidance.
- Add a focused regression test in `tests/test_work_session.py`.
- Codex may review, steer, and approve only; no rescue edits.

Start time: 2026-04-20 22:08 JST
End time: 2026-04-20 22:15 JST

Metrics:

- first_edit_latency_seconds: about 296
- model_turns: 5 before first edit proposal
- search_calls_before_first_edit: 7
- read_calls_before_first_edit: 3
- changed_files: `src/mew/work_loop.py`,
  `tests/test_work_session.py`
- verifier_commands:
  `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch --no-testmon`
- repair_cycles: 0
- prompt_context_chars: not recorded
- rescue_edits: 0
- adopted_reference_patterns: Codex patch/review loop, focused regression test,
  approval-gated paired source/test edits

Review:

- correctness: passed focused regression plus ruff, py_compile, and diff check
- minimality: one prompt sentence expanded and one existing prompt test extended
- reviewability: dry-run diffs #2207/#2208 were reviewable and approved as
  #2209/#2210
- resident_state_reuse: reused #323 friction as the next M6.6 comparator target
- notes: Codex CLI comparator was run afterward in
  `/tmp/mew-m66b-codex-20260420-2218`

Verdict: mew run passed.

### M6.6-B Codex CLI run

Task: same as M6.6-B mew run, executed in a detached worktree at commit
`ac8b7d6`.

Predeclared success criteria: same as mew run.

Start time: 2026-04-20 22:17 JST
End time: 2026-04-20 22:29 JST

Metrics:

- first_edit_latency_seconds: about 120
- model_turns: one Codex CLI session
- search_calls_before_first_edit: several broad shell searches plus large file
  reads; exact count not captured
- read_calls_before_first_edit: included a broad
  `sed -n '1,260p' tests/test_work_session.py` and multiple targeted windows
- changed_files: `src/mew/work_loop.py`,
  `tests/test_work_session.py`
- verifier_commands:
  `PYTHONPATH=src /Users/mk/dev/x-cli/.venv/bin/python -m pytest -q -o addopts= tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_allows_docs_only_single_writes_outside_code_batch_rule`
- repair_cycles: 0 implementation repairs; multiple verification environment
  retries
- prompt_context_chars: not recorded
- rescue_edits: 0
- adopted_reference_patterns: Codex patch/review loop, focused regression test

Review:

- correctness: focused regression passed with `1 passed in 0.67s`
- minimality: one prompt sentence and one focused new regression test
- reviewability: patch was readable, but the test was larger than the mew-side
  assertion-only update
- resident_state_reuse: none; this was a fresh CLI worktree comparator
- notes: normal `uv run pytest ...` could not complete in the Codex CLI
  sandbox because uncached `coverage`/`hatchling` dependencies were unavailable;
  Codex recovered by using an existing pytest environment with `PYTHONPATH=src`

Verdict: Codex CLI comparator passed with environment caveat.

### M6.6-C mew run

Task: #327 `M6.6-C comparator: recent window reuse guidance`

Predeclared success criteria:

- Add one small prompt behavior feature in `src/mew/work_loop.py`: when
  `work_session.recent_read_file_windows` already contains the exact recent
  path/span or old text needed for edit preparation, explicitly tell the model
  to reuse that recent window instead of issuing another same-span `read_file`.
- Add one focused regression assertion in
  `tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch`.
- Codex may steer/review/approve only; no rescue edits.

Start time: 2026-04-20 23:50 JST
End time: 2026-04-20 23:55 JST

Metrics:

- first_edit_latency_seconds: about 242
- model_turns: 4 before first edit proposal; 6 total
- search_calls_before_first_edit: 5
- read_calls_before_first_edit: 4
- changed_files: `src/mew/work_loop.py`,
  `tests/test_work_session.py`
- verifier_commands:
  `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch --no-testmon`;
  reviewer broader verify:
  `uv run python -m unittest tests.test_work_session`
- repair_cycles: 0
- prompt_context_chars: not recorded
- rescue_edits: 0
- adopted_reference_patterns: read-only exploration discipline, Codex
  patch/review loop, paired source/test approval surface

Review:

- correctness: focused verifier passed on apply, then reviewer broader verify
  passed with `396 tests`
- minimality: one prompt sentence expanded and one focused assertion added
- reviewability: mew proposed a paired dry-run edit batch (#2270/#2271) before
  apply; Codex only approved/applied it as #2272/#2273
- resident_state_reuse: session #314 reused task guidance, touched-file state,
  and recent read windows; the final patch directly reduced same-span reread
  churn during edit preparation
- notes: the first fresh attempt still repeated narrow `search_text` on the
  same src symbol, so reviewer steer redirected the run toward one exact src
  window read (#2269) and then a paired dry-run batch; this run counts as
  mew-side evidence with steering but no rescue edits

Verdict: mew run passed. Matching Codex CLI comparator is deferred until the
M6.6 implementation set is frozen.

## Historical M6.6-C Blocker Note

Task: #326 `M6.6-C comparator: suggested verifier fallback`

Predeclared success criteria:

- Add one small feature with paired source/test changes: when the work model
  chooses `run_tests`, no explicit command is present, and no configured
  `verify_command` exists, prefer
  `work_session.resume.suggested_verify_command.command`.
- Keep the diff focused in `src/mew/work_loop.py` and
  `tests/test_work_session.py`.
- Codex may steer/review/approve only; no rescue edits.

Blocked mew run summary:

- Session #312 started from the predeclared task but fell into repeated
  targeted `search_text` and `read_file` loops while trying to recover exact
  old strings for the edit surface.
- Session #313 retried with stronger `--work-guidance`, but again stayed in
  repeated targeted reads and one live planning turn hung before any dry-run
  edit was proposed.
- The supervisor stopped tracking #313 as comparator evidence, killed the hung
  producer, recorded the blocker in mew session notes, and closed the session.

Not-counted direct fix:

- A direct supervisor implementation then landed the fallback feature in
  `src/mew/work_loop.py` and `tests/test_work_session.py`.
- Focused and broader validation passed, including:
  `uv run pytest -q tests/test_work_session.py -k 'suggested_verify or verification_command or resident_loop or guides_independent_reads_to_batch' --no-testmon`
  and `uv run python -m unittest tests.test_work_session`.
- This direct patch is product progress, but it does not count as M6.6-C mew
  comparator evidence because sessions #312/#313 never reached a reviewable
  dry-run edit.

Verdict: historical blocker only. Task #326 does not count as M6.6-C evidence;
task #327 is the replacement mew-side run.

## Current Comparator State

Bootstrap is complete. M6.6-A and M6.6-B have side-by-side mew/Codex CLI
evidence. M6.6-B still carries an environment caveat from its comparator run.
M6.6-C now has mew-side evidence from task #327 / session #314. By project
decision on 2026-04-21, the remaining/final Codex CLI comparator runs are
deferred until the M6.6 mew-side implementation set is frozen, then they should
run in parallel detached worktrees as gate evidence rather than per-slice
critical-path work.

After the direct `working_memory.target_paths` patch from task #331, task #332
/ session #319 added fresh mew-side implementation evidence for that path-
recall surface: mew proposed paired dry-run edits (#2345/#2346), Codex only
approved/applied them as #2347/#2348, mew chose
`uv run python -m unittest tests.test_work_session`, passed it with `396
tests`, performed one same-surface audit read, and finished with
`rescue_edits=0`. This is implementation evidence for the frozen M6.6 set, not
an extra comparator slot.
