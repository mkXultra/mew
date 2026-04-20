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
