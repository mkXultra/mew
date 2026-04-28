# M6.14 Structural Repair Ledger

Date started: 2026-04-28 JST

Purpose: keep one compact, append-friendly ledger of structural implementation
lane blockers so context compression, milestone closeout, and broad benchmark
campaigns do not lose repair obligations.

This file is the canonical queue for accepted structural blockers. Detailed
evidence remains in milestone run ledgers and proof artifacts; append rows here
when a blocker is accepted, selected for repair, repaired, deferred, or
superseded.

## Operating Rule

- Structural signal detected: record in the producing milestone ledger.
- Accepted structural blocker: append or update a row here.
- Repair selected: set the active product/parity milestone to `pending`, set
  M6.14 active, and name a bounded generic repair.
- Repair complete: record validation and rerun the same failed task shape.
- Resume the paused milestone only after the rerun result is recorded.

Do not add task-specific benchmark solvers here. Repairs must improve the
generic mew work path.

## Reference Pack

Before starting an M6.14 repair episode, read only the references relevant to
the selected blocker. Use them as design evidence, not as automatic permission
for broad refactors.

Core policy:

- `ROADMAP.md`: M6.14, M6.18, and the paused product/parity milestone gate.
- `ROADMAP_STATUS.md`: current active/pending status and latest accepted
  blocker.
- This ledger: selected blocker, retry target, and repair status.

Failure evidence:

- `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`
- `docs/M6_22_CLOSE_GATE_AUDIT_2026-04-28.md`
- `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`
- `docs/M6_23_CLOSE_GATE_AUDIT_2026-04-28.md`
- `docs/M6_24_BATCH_1_RUNS_2026-04-28.md`
- `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`

Architecture references:

- `docs/ADOPT_FROM_REFERENCES.md`: reference CLI patterns such as streaming
  executor, tool policy, task contract, and fail-closed tool factory.
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`: explorer/todo,
  structured approval, task decomposition, and patch/review/verify patterns.
- `docs/REVIEW_2026-04-20_CONTEXT_WINDOW_MANAGER.md`: task-contract and
  context-window ideas when the blocker involves missing or unstable task
  context.
- `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`: loop-state, replay,
  lifecycle, and debugging contracts when the repair touches the work loop.

Reference source trees, only when the docs are insufficient:

- `references/fresh-cli/claude-code`
- `references/fresh-cli/codex`

Selection rule:

- Timeout / partial observability: start with M6.23/M6.24 evidence plus
  `ADOPT_FROM_REFERENCES.md` streaming/executor notes.
- False green / verifier grounding: start with M6.22/M6.23/M6.24 evidence plus
  `MISSING_PATTERNS_SURVEY.md` patch/review/verify and todo patterns.
- Artifact observation gaps: start with M6.22/M6.24 evidence, then inspect
  existing work tools before adding a new observation tool.
- Shell command ergonomics: start with M6.22/M6.24 evidence plus tool policy
  notes; prefer safe command-shape repair over prompt-only advice.

## Append Schema

Use this schema when appending a new row:

```text
| ID | Status | First seen | Blocker | Evidence | Generic repair route | Reference inputs | Retry target | Notes |
```

Status vocabulary:

- `candidate`: structural-looking signal, not yet selected.
- `selected`: accepted structural blocker; M6.14 should own active repair.
- `in_repair`: implementation underway.
- `repaired`: generic repair landed and same-shape rerun recorded.
- `deferred`: consciously not repaired yet, with reason.
- `superseded`: covered by a broader repair row.

## Active / Open Rows

| ID | Status | First seen | Blocker | Evidence | Generic repair route | Reference inputs | Retry target | Notes |
|---|---|---|---|---|---|---|---|---|
| SR-001 | selected | M6.22 / M6.24 | `agent_wall_timeout_without_report` / timeout partial observability | `gcode-to-text` had timeout without useful report; `financial-document-processor` and `dna-assembly` later hit long domain/document repair timeouts | Add generic partial progress / timeout observability so long work loops emit actionable reports before command or wall timeout | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/ADOPT_FROM_REFERENCES.md` streaming executor notes | rerun `financial-document-processor` or `dna-assembly` same failed shape | Current top repair candidate because it repeats across milestones and makes broad measurement low-value. |
| SR-002 | selected | M6.22 / M6.24 | finish/verifier grounding false green | `overfull-hbox` self-reported acceptance despite verifier rejection; `dna-assembly` used surrogate primer Tm checks instead of exact named ground-truth tool | Strengthen finish gate/task contract so named external ground-truth tools or acceptance constraints must be executed exactly, or finish must be blocked | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` patch/review/verify and todo patterns | rerun `dna-assembly`; optionally rerun an acceptance-grounding task | High trust impact; false green is more dangerous than honest failure. |
| SR-003 | candidate | M6.22 / M6.24 | artifact observation substrate gap | `gcode-to-text` visual/geometric grounding gap; `code-from-image` fixed by `read_image`; `financial-document-processor` exposed PDF/document observation gap | Add generic document/PDF or broader artifact observation only if selected as bounded repair slice | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md` | rerun `financial-document-processor` or a visual/document task | Partly repaired for images; PDF/document remains open. |
| SR-004 | candidate | M6.22 / M6.24 | `shell_quoting_multiline_command` | `sanitize-git-repo` shell command quote issue; `dna-assembly` multiline `python3 -c` syntax failure | Add safer multiline command guidance or command-shape helper, likely heredoc/script-first policy | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/ADOPT_FROM_REFERENCES.md` tool policy notes | rerun a task that exercises multiline verification | Lower priority than timeout/grounding unless it blocks a selected repair. |
| SR-005 | candidate | M6.24 | `numeric_independent_validation_not_objective_grounded` | `raman-fitting` used table grounding but validated the wrong objective/scale/model family | Add objective-grounding checks for numeric/scientific tasks if another numeric/data task confirms the same shape | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` | rerun `raman-fitting` or another numeric/data task | Do not spend more prompt-polish cycles without selecting this as M6.14 repair. |

## Repaired / Superseded Rows

| ID | Status | First seen | Blocker | Evidence | Generic repair route | Reference inputs | Retry target | Notes |
|---|---|---|---|---|---|---|---|---|
| SR-101 | repaired | M6.22 | `repairable_constraint_blocker_terminal_wait` | `overfull-hbox` acceptance-check rerun regressed because repairable blockers stopped as `wait` | Convert repairable waits to continuity notes while budget remains | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md` | `overfull-hbox` rerun | Repaired by commit `2d0b5c4`; later M6.23 rerun improved to 3/5 after edit-scope grounding. |
| SR-102 | repaired | M6.23 | `self_reported_acceptance_evidence_not_grounded_in_diff_validator` | `overfull-hbox` claimed acceptance without grounded edit-scope evidence | Ground acceptance evidence in diff/edit-scope validation | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md` | `overfull-hbox` rerun | Repaired by commit `47a3393`; improved to 3/5 but timeout/false-green families remain relevant. |
| SR-103 | superseded | M6.24 | `visual_artifact_observation_missing` for images | `code-from-image` could not read image artifact and scored 0/5 | Add generic `read_image` work tool | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` | `code-from-image` and `chess-best-move` reruns | Image substrate repaired by commit `5e963d3`; broader document/PDF remains SR-003. |
