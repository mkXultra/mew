# M6.6 Codex CLI Parity Comparator

Use this document to keep M6.6 measurable. Do not count a task as M6.6 evidence
unless the task was chosen before the run and the trace separates mew-authored
work from Codex rescue edits.

## Gate

M6.6 closes only after three predeclared representative coding tasks pass:

| Task | Shape | Status | Mew run | Codex CLI comparator | Rescue edits |
|---|---|---|---|---|---|
| M6.6-A | Behavior-preserving refactor | `not_started` | | | |
| M6.6-B | Bug fix with regression test | `not_started` | | | |
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

Status: `blocked`

Task: #322 `M6.6 bootstrap: durable coding plan state`

Adopted reference patterns:

- Durable plan state: TodoWriteTool-style persistent checklist
- Read-only exploration discipline: exploreAgent-style scoped exploration before edit

Mew run:

- Session #307 started at 2026-04-20 21:30 JST.
- Mew read the reference gate and narrowed implementation surfaces to
  `src/mew/work_loop.py`, `src/mew/snapshot.py`, and
  `tests/test_work_session.py`.
- Mew required reviewer steering after repeated search/read churn.
- Mew then stopped without proposing edits because exact `read_file` old text
  was not retained across model turns under the current context mode.

Verification: not run; no edit was proposed.

Rescue edits: 0

Blocker if failed:

- Native work turns must preserve exact recent file-window content, or provide
  another safe edit mechanism, before mew can self-implement the first M6.6
  slice without guessing old strings.

Verdict: bootstrap failed honestly and produced the next M6.6 blocker.

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

## Current First Slice

Implement durable coding plan state plus path recall in the work session before
attempting the three comparator tasks. This should make the second and third
tasks need less repeated discovery rather than merely adding prompt context.
