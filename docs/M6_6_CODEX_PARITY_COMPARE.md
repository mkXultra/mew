# M6.6 Codex CLI Parity Comparator

Use this document to keep M6.6 measurable. Do not count a task as M6.6 evidence
unless the task was chosen before the run and the trace separates mew-authored
work from Codex rescue edits.

## Gate

M6.6 closes only after three predeclared representative coding tasks pass:

| Task | Shape | Status | Mew run | Codex CLI comparator | Rescue edits |
|---|---|---|---|---|---|
| M6.6-A | Behavior-preserving refactor | `not_started` | | | |
| M6.6-B | Bug fix with regression test | `side_by_side_recorded` | #324 / session #310 | `/tmp/mew-m66b-codex-20260420-2218` | 0 |
| M6.6-C | Small feature with paired source/test changes | `not_started` | | | |

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

## Current Comparator State

Bootstrap is complete. M6.6-B has side-by-side mew/Codex CLI evidence.
M6.6-A and M6.6-C have not started.
