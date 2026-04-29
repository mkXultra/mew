# DESIGN 2026-04-29 - M6.24 Hard-Task Contract Capsule

Active chain:

```text
M6.24 -> hard_task_implementation_strategy_contract_retention -> reference-backed implementation-lane repair -> rerun make-doom-for-mips or make-mips-interpreter same shape
```

## Problem

M6.24 measurement shows a large Codex gap on hard implementation tasks after
lower-level timeout, permission, artifact, and verifier-grounding repairs.
Several failures now look like the work loop can run tools and edit files, but
does not reliably preserve the task contract across turns:

- provided source or binary is ignored
- a nearby stub or surrogate is treated as enough
- a smoke command is confused with external behavior proof
- final `task_done=true` lacks source/provenance evidence

The clearest shapes are `make-doom-for-mips` and `make-mips-interpreter`.

## Reference Import

Codex patterns used:

- persistent goal/objective state
- explicit plan/todo state
- source/instruction grounding
- patch/diff provenance as evidence
- pre-finish review against concrete proof

Mew-compatible translation:

- do not import Codex's full planner, patch engine, or subagent review loop yet
- add a compact `working_memory.implementation_contract`
- seed it from hard-task descriptions with provided source/binary/artifact refs
- preserve it through resume formatting and model working memory
- block `task_done=true` when cited source grounding is missing

## v0 Implementation

`src/mew/acceptance.py` now extracts source requirements from sentences that
mention provided/corresponding source, existing/given source, or source
directories. It tracks path-like source refs such as `/app/doomgeneric_mips`
and `doomgeneric/`.

`acceptance_finish_blocker()` now checks hard implementation tasks before
allowing `task_done=true`:

- each provided source/binary/artifact must be grounded by cited completed
  `read_file`, `search_text`, `glob`, or `run_command` evidence
- `run_tests` / smoke execution alone is not source grounding
- exact command evidence remains separately enforced by the existing exact
  command blocker

`src/mew/work_session.py` seeds and preserves:

- `objective`
- `source_inventory`
- `prohibited_surrogates`
- `open_contract_gaps`

`src/mew/work_loop.py` asks the model to keep that contract current and cite
source/verifier/artifact/behavior proof separately.

## Validation

Focused checks:

```text
uv run pytest tests/test_acceptance.py -k 'implementation_contract or hard_task'
uv run pytest tests/test_work_session.py -k 'startup_working_memory_seeds_hard_task_implementation_contract or work_think_prompt_guides_independent_reads_to_batch'
uv run pytest tests/test_acceptance.py
uv run pytest tests/test_work_session.py
```

Observed:

- `tests/test_acceptance.py`: 46 passed, 3 deselected
- `tests/test_work_session.py`: 766 passed, 2 deselected

## Same-Shape Rerun Gate

Next proof should rerun one selected hard task, preferably:

1. `make-doom-for-mips`
2. `make-mips-interpreter`

Expected improvement signal:

- no false `task_done=true` if provided source/binary evidence is absent
- source inventory appears in resume/report context
- acceptance evidence cites source grounding separately from `node vm.js`
- fewer stub/surrogate completions, or a more actionable blocked/failure report

If the rerun does not improve the selected gap, keep M6.24 in improvement mode
and either strengthen the contract capsule or reclassify the gap.

## Rerun Result

Recorded in:

`docs/M6_24_HARD_TASK_CONTRACT_RERUN_2026-04-29.md`

The same-shape `make-doom-for-mips` rerun remained 0/5, but the selected gap
class improved qualitatively: reports preserved the contract capsule, no trial
finished with a false complete state, and several trials reached real
source-built ELF / VM-loader repair work instead of surrogate stubs.

Remaining follow-up is still inside M6.24 improvement phase:

- primary: hard-runtime verifier strategy for VM/emulator/interpreter failure
  signatures
- secondary: hard-task budget/reasoning is too small for this shape
- secondary: ephemeral container package/toolchain permissions are not explicit
  enough
- rerun `make-doom-for-mips` after the hard-runtime strategy repair
