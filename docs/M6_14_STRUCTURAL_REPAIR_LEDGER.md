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
- `docs/M6_24_BATCH_3_RUNS_2026-04-28.md`

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
| SR-001 | repaired | M6.22 / M6.24 | `agent_wall_timeout_without_report` / timeout partial observability | `gcode-to-text` had timeout without useful report; `financial-document-processor` and `dna-assembly` later hit long domain/document repair timeouts | Add generic partial progress / timeout observability so long work loops emit actionable reports before command or wall timeout | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/ADOPT_FROM_REFERENCES.md` streaming executor notes | rerun `financial-document-processor` or `dna-assembly` same failed shape | Repaired by atomic partial `mew work --oneshot --report` writes plus Harbor `container_repo_root` mapping; same-shape timeout left a host-visible actionable report. |
| SR-002 | repaired | M6.22 / M6.24 | finish/verifier grounding false green | `overfull-hbox` self-reported acceptance despite verifier rejection; `dna-assembly` used surrogate primer Tm checks instead of exact named ground-truth tool | Strengthen finish gate/task contract so named external ground-truth tools or acceptance constraints must be executed exactly, or finish must be blocked | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` patch/review/verify and todo patterns | rerun `dna-assembly`; optionally rerun an acceptance-grounding task | Repaired by exact external-tool finish gate plus exact-tool-unavailable blocker guidance; smaller proof stopped with `task_done=false` after the required command was missing. |
| SR-003 | repaired | M6.22 / M6.24 | artifact observation substrate gap | `gcode-to-text` visual/geometric grounding gap; `code-from-image` fixed by `read_image`; `financial-document-processor` exposed PDF/document observation gap; `extract-moves-from-video` generated contact sheets then timed out across 5/5 trials while sequentially inspecting visual artifacts | Add bounded generic multi-artifact observation: ordered `read_images`, resume-visible observation transcripts, and large chronological chunk guidance | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md` | rerun `extract-moves-from-video` same failed shape | Repaired by generic `read_images` with 16-image / aggregate-byte caps, `recent_read_images_observations`, and large chronological chunk guidance; same-shape proof `mew-m6-14-sr003-extract-moves-from-video-1attempt-read-images-largechunks-20260428-1843` reached 1/1 with errors 0. |
| SR-004 | candidate | M6.22 / M6.24 | `shell_quoting_multiline_command` | `sanitize-git-repo` shell command quote issue; `dna-assembly` multiline `python3 -c` syntax failure | Add safer multiline command guidance or command-shape helper, likely heredoc/script-first policy | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`, `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`, `docs/ADOPT_FROM_REFERENCES.md` tool policy notes | rerun a task that exercises multiline verification | Lower priority than timeout/grounding unless it blocks a selected repair. |
| SR-005 | candidate | M6.24 | `numeric_independent_validation_not_objective_grounded` | `raman-fitting` used table grounding but validated the wrong objective/scale/model family | Add objective-grounding checks for numeric/scientific tasks if another numeric/data task confirms the same shape | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` | rerun `raman-fitting` or another numeric/data task | Do not spend more prompt-polish cycles without selecting this as M6.14 repair. |
| SR-007 | repaired | side-project issue #18 | coordinated multi-file patch shape failure | `[side-pj] mew-wisp SP19 stalls on coordinated HTML removal patch shape`: source-only HTML removal rolled back because tests/README were not updated; follow-up repairs hit stale hunks and unsupported batch shape containing `edit_file_hunks` plus `wait` | Strengthen write-batch normalization/execution so blockers are top-level waits, not pseudo-tools inside a write batch; preserve the exact blocker instead of surfacing `batch write tool is not ... wait` | issue #18, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`, `docs/ADOPT_FROM_REFERENCES.md` patch/review/apply-loop notes | direct regression for mixed `edit_file_hunks` + `wait` batch | Repaired by normalizer and executor guards: mixed write/wait batches now become an actionable top-level blocker, and command execution blocks before any pseudo-tool execution. Focused regression passed. |
| SR-008 | repaired | M6.24 Batch 3 | direct Python pytest-file false green | `break-filter-js-from-html` scored 0/5 while several trials claimed `python /app/test_outputs.py` passed; direct Python execution only defined pytest tests and exited 0, while Harbor pytest verifier failed | Normalize `run_tests` commands that directly execute pytest-style `test_*.py` files through Python into `python -m pytest -q <file>` so no-op verifiers fail loudly | `docs/M6_24_BATCH_3_RUNS_2026-04-28.md`, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` verifier-grounding notes | rerun `break-filter-js-from-html` same failed shape | Repaired by executor normalization plus focused regression; same-shape rerun no longer false-greened and preserved `python -m pytest -q /app/test_outputs.py` failure evidence. |
| SR-009 | repaired | side-project issue #18 reopen | broad rollback loop keeps retrying whole coordinated patch | Reopened issue #18 after SR-007: SP19 still could not land broad HTML removal; coordinated source/test/report attempts rolled back with 9 failed / 19 passed, then 1 failed / 27 passed, then regressed to 8 failed / 20 passed before timeout | Surface `broad_rollback_slice_repair` in work-session resume/prompt/deliberation so repeated verifier rollbacks or broad failed-test output steer the next turn to one smaller complete source/test/docs slice instead of retrying the whole patch | issue #18 reopen, `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`, `docs/ADOPT_FROM_REFERENCES.md` patch/review/apply-loop notes | direct regression for two rolled-back verifier failures spanning source/test/docs | Repaired by resume diagnostic and prompt guidance; focused regression verifies the diagnostic, formatter, and deliberation context. |

## SR-001 Progress

- 2026-04-28: implemented the first generic timeout-observability slice:
  `mew work --oneshot --report` now writes an atomic partial progress report
  before model/tool execution, mirrors batch and single-tool state into the
  report, and mirrors running tool output into the normal work-session state so
  later partial reports can include live command tails. Final report writes are
  atomic as well, so a kill during completion does not corrupt the last valid
  partial report.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py -k 'work_oneshot_writes_partial_report_before_model_turn or work_oneshot_writes_partial_report_during_batch_tool or work_oneshot_partial_report_cannot_overwrite_final_report or work_oneshot_stops_before_model_when_wall_budget_too_small or work_oneshot_reduces_model_timeout_to_fit_wall_budget' -q`.
- Broader validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py -q`.
- Lint passed:
  `uv run ruff check src/mew/commands.py tests/test_work_session.py`.
- Missing proof before marking `repaired`: rerun the same failed task shape
  (`financial-document-processor` or `dna-assembly`) and confirm timeout
  failures leave actionable `mew-report.json` / resume artifacts.
- Same-shape proof note:
  `mew-m6-14-sr001-financial-document-processor-1attempt-20260428-1600`
  reproduced the 900s command timeout but did not preserve `mew-report.json`
  because the Harbor wrapper passed a container-local artifact path. The wrapper
  now supports `container_repo_root=/mew`, mapping `{report_path}` and
  `{artifact_dir}` into the mounted repo so partial reports can survive outer
  command timeout. A container-visible rerun is in progress.
- Same-shape proof result:
  `mew-m6-14-sr001-financial-document-processor-1attempt-container-report-20260428-1640`
  reproduced the 900s `RuntimeError: Command timed out after 900 seconds`, but
  preserved host-visible
  `financial-document-processor__9ecQBGT/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`.
  The report is an atomic partial report with `partial_report=true`,
  `phase=running`, a fresh heartbeat, the active work-session resume bundle,
  unresolved repeat-action failures, recent decisions, current working memory,
  and next action. This satisfies SR-001: timeouts no longer erase the
  actionable state needed to resume or diagnose the long document loop.

## SR-002 Progress

- 2026-04-28: implemented the first generic false-green grounding slice:
  task descriptions that name an exact external ground-truth command/tool and
  required flags now block `finish task_done=true` unless acceptance evidence
  cites a completed `run_command` or `run_tests` whose command/output contains
  the named command and flags. The work prompt now tells the model not to
  substitute surrogate libraries, approximations, or nearby tools for exact
  ground-truth command constraints.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py -k 'external_ground_truth or work_think_prompt_guides_independent_reads_to_batch' -q`.
- Broader validation passed:
  `uv run pytest --no-testmon tests/test_acceptance.py tests/test_work_session.py -q`.
- Lint passed:
  `uv run ruff check src/mew/acceptance.py src/mew/work_loop.py tests/test_work_session.py`.
- Combined validation including the Harbor wrapper passed:
  `uv run pytest --no-testmon tests/test_acceptance.py tests/test_work_session.py tests/test_harbor_terminal_bench_agent.py -q`.
- Same-shape proof result:
  `mew-m6-14-sr002-dna-assembly-1attempt-exact-ground-truth-20260428-1645`
  timed out after 900s before a final answer. It did not produce the previous
  false-green finish: the partial report preserved `oligotm NOT_FOUND`, a
  blocked acceptance check for "Tm must be computed by primer3 oligotm with
  required flags", and later local `primer3-py` surrogate exploration. This is
  useful but insufficient to mark SR-002 repaired because the proof ended in
  timeout rather than an explicit finish block or exact `oligotm` validation.
- Follow-on repair slice:
  exact ground-truth tool unavailability must become an explicit blocker
  instead of a long surrogate loop. The work prompt now says that if prior
  command output reports the exact command as `NOT_FOUND`, command not found,
  executable not found, or otherwise unavailable, the model must not install or
  use a surrogate package/library/API; it must run/install the exact command
  within current capabilities or return `wait`/`remember` with that exact
  blocker.
- Smaller exact-ground-truth proof result:
  `proof-artifacts/m6-14-sr002-exact-tool-unavailable-smoke-20260428-1651/agent/mew-report.json`
  created `output.txt`, ran the required exact command
  `missing-validator --threshold 50 --format json output.txt`, observed
  `executable not found: missing-validator`, and then finished with
  `task_done=false`. Its final acceptance checks marked the file creation as
  verified and the exact ground-truth command as blocked, citing the completed
  `run_command` evidence. It did not install or use a surrogate validator and
  did not claim task completion. This satisfies the SR-002 repair proof for the
  false-green/unavailable-tool shape.

## SR-003 Progress

- 2026-04-28: implemented a bounded generic multi-image observation slice:
  `read_images` lets a work session send an ordered set of related images to
  the model in one read-only tool call. It is not video-specific: bash/Python
  remain responsible for extracting frames, contact sheets, PDFs, or other
  artifacts into image files, then `read_images` observes the ordered artifact
  set.
- Safety and ergonomics:
  `read_images` enforces allowed read roots, sensitive-path checks, image MIME
  validation, per-image size caps, a 16-image count cap, and an aggregate byte
  cap. The error for over-large image sets tells the model to split the set
  into ordered chunks.
- Resume repair:
  work-session resumes now preserve recent `read_images` observations with
  ordered paths and clipped transcript text. The prompt tells the model to
  reuse those transcripts instead of rereading the same visual artifacts, and
  to carry compact transcripts forward in working memory for long artifact
  tasks.
- Prompt policy:
  visual/document/video artifact tasks should use bash/Python to transform the
  raw file into a small ordered image set, then use the largest chronological
  `read_images` chunks that fit. This avoids the previous one-contact-sheet-at-
  a-time loop that consumed wall-clock and context budget.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_image_tools.py tests/test_work_session.py -k 'read_images or work_think_prompt_includes_work_guidance or write_ready or resume_preserves_recent_read_images' -q`.
- Lint passed:
  `uv run ruff check src/mew/image_tools.py src/mew/read_tools.py src/mew/work_session.py src/mew/commands.py src/mew/cli.py src/mew/plan_schema.py src/mew/acceptance.py src/mew/work_loop.py tests/test_image_tools.py tests/test_work_session.py`.
- Same-shape proof sequence:
  the first `read_images` proof avoided command errors but failed because the
  8-image cap was too small for the contact-sheet set; the second proof with a
  16-image cap successfully transcribed chunks but lost earlier transcript
  context; the third proof preserved `recent_read_images_observations` but
  still used chunks that were too small for the step budget.
- Final same-shape proof result:
  `mew-m6-14-sr003-extract-moves-from-video-1attempt-read-images-largechunks-20260428-1843`
  reached reward 1/1 with exceptions 0. The session extracted 96 frames into
  eight chronological contact sheets, read them with one ordered `read_images`
  call, performed an independent visual audit, and wrote the required
  `/app/solution.txt` before the 30-step budget expired.

## SR-007 Progress

- 2026-04-28: issue #18 showed that a side-project coordinated patch could
  reach a repair frontier but then emit a write batch containing
  `edit_file_hunks` plus `wait`. The command executor treated that synthetic
  `wait` as a batch sub-tool and stopped with the misleading error
  `batch write tool is not a paired write/edit: wait`.
- Generic repair:
  `normalize_work_model_action` now rejects write batches that contain
  non-write tools such as `wait` with an actionable top-level blocker. The work
  prompt also says not to mix reads, wait, remember, finish, or blockers into
  write batches.
- Executor repair:
  `run_work_batch_action` no longer inserts a synthetic `wait` sub-tool when a
  write batch cannot be normalized. It finishes the model turn with
  `batch_blocked=true`, zero tool calls, and the original actionable blocker.
  This makes the next turn repair the patch shape instead of debugging a fake
  wait-tool execution failure.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py -k 'mixed_write_wait or refuses_wait_inside_write_batch or work_session_resume_surfaces_working_memory or batch_refuses_partial_truncated_write_batches' -q`.
- Lint/diff validation passed:
  `uv run ruff check src/mew/commands.py src/mew/work_loop.py tests/test_work_session.py`
  and `git diff --check`.

## SR-008 Progress

- 2026-04-28: M6.24 Batch 3 `break-filter-js-from-html` baseline scored 0/5
  with Harbor errors 0. Several trials finished `task_done=true` after running
  `python /app/test_outputs.py` and seeing exit 0, but the command only defined
  pytest tests and did not execute them. Harbor's external verifier executed
  pytest and failed all five trials.
- Generic repair:
  `run_tests` now detects direct Python invocation of pytest-style files such
  as `python test_outputs.py` or `python /app/test_outputs.py` when the file
  contains pytest test functions/classes and no direct `__main__` runner. It
  normalizes the command to `python -m pytest -q <file>` before execution and
  records the original command plus normalization reason in the result.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py -k 'direct_pytest_file_invocation or normalizes_leading_cd_and_then_operator or allows_quoted_shell_operator_literals or zero_test_pytest' -q`.
- Broader nearby validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py -k 'run_tests' -q`.
- Lint/diff validation passed:
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
  and `git diff --check`.

## SR-009 Progress

- 2026-04-28: issue #18 reopened after SR-007. The side-project retry no
  longer hit the mixed write/wait pseudo-tool bug, but broad SP19 HTML removal
  still failed because coordinated source/test/report edits repeatedly rolled
  back under verifier output: first `9 failed, 19 passed`, then
  `1 failed, 27 passed`, then `8 failed, 20 passed` before timeout.
- Generic repair:
  work-session resumes now build `broad_rollback_slice_repair` when repeated
  rolled-back writes, multiple involved paths, or multi-failure verifier output
  indicate that the next turn should not retry the whole broad patch. The
  formatter, main think prompt, write-ready prompts, and deliberation context
  all surface the same instruction: choose one smaller complete
  source/test/docs slice, verify it, and carry remaining scope in
  `working_memory`.
- Focused validation passed:
  `uv run pytest --no-testmon tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch tests/test_work_session.py::WorkSessionTests::test_work_resume_surfaces_broad_rollback_slice_repair -q`.
- Lint/diff validation passed:
  `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`
  and `git diff --check`.
- Same-shape proof result:
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__19-55-56/result.json`
  scored 0/1 with Harbor errors 0, but the prior false green was removed. The
  preserved `mew-report.json` has `work_exit_code=1`, `stop_reason=model_error`,
  and command history showing `python -m pytest -q /app/test_outputs.py` failed
  before the model continued with explicit verifier feedback. This satisfies
  SR-008: the executor no longer treats direct Python execution of pytest-style
  test files as a passing verifier.

## Repaired / Superseded Rows

| ID | Status | First seen | Blocker | Evidence | Generic repair route | Reference inputs | Retry target | Notes |
|---|---|---|---|---|---|---|---|---|
| SR-101 | repaired | M6.22 | `repairable_constraint_blocker_terminal_wait` | `overfull-hbox` acceptance-check rerun regressed because repairable blockers stopped as `wait` | Convert repairable waits to continuity notes while budget remains | `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md` | `overfull-hbox` rerun | Repaired by commit `2d0b5c4`; later M6.23 rerun improved to 3/5 after edit-scope grounding. |
| SR-102 | repaired | M6.23 | `self_reported_acceptance_evidence_not_grounded_in_diff_validator` | `overfull-hbox` claimed acceptance without grounded edit-scope evidence | Ground acceptance evidence in diff/edit-scope validation | `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md` | `overfull-hbox` rerun | Repaired by commit `47a3393`; improved to 3/5 but timeout/false-green families remain relevant. |
| SR-103 | superseded | M6.24 | `visual_artifact_observation_missing` for images | `code-from-image` could not read image artifact and scored 0/5 | Add generic `read_image` work tool | `docs/M6_24_BATCH_1_RUNS_2026-04-28.md` | `code-from-image` and `chess-best-move` reruns | Image substrate repaired by commit `5e963d3`; broader document/PDF remains SR-003. |
| SR-006 | repaired | side-project issue #17 | side-project closeout git status/diff blocked by narrow allow-read root | `[side-pj] work-session git status closeout fails under side-project allow-read roots` reported `git_status` / `git_diff` failures when only `experiments/mew-ghost` was allowed | Scope default-cwd git inspection to the first allowed read root and pass a pathspec so final audits can inspect side-project diffs without reading repo root | issue #17, work-session git tool tests | side-project closeout git audit under `--allow-read experiments/mew-ghost` | Repaired by adding pathspec support to git tools plus a regression test proving `git_status` and `git_diff` include the side-project file and exclude repo-root changes. |
