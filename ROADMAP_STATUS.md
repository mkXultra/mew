# Mew Roadmap Status

Last updated: 2026-04-29

This file is the compact operational roadmap dashboard. It is intentionally
short enough to survive context compression and long-session reentry.

Detailed historical evidence through the current compression point is archived
losslessly in:

- `docs/archive/ROADMAP_STATUS_through_M5_2026-04-20.md`
- `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Status vocabulary:

- `not_started`: no meaningful implementation yet
- `foundation`: supporting pieces exist, but the milestone's core user value is
  not usable
- `in_progress`: core implementation exists or is the active focus
- `pending`: meaningful implementation exists, but the milestone is
  intentionally paused by a higher-priority active milestone
- `done`: the recorded close gate passed
- `merged_into_*`: historical milestone folded into another milestone

Important interpretation: `done` means the recorded close gate passed. It does
not mean every idea in every design note has shipped. Deferred post-close work
is tracked below.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| 1. Native Hands | `done` | Native work sessions can inspect, edit, verify, resume, and expose audit trails. |
| 2. Interactive Parity | `done` | Cockpit/live/follow controls, approvals, compact output, interruption handling, and comparator evidence reached the gate. |
| 3. Persistent Advantage | `done` | Reentry/comparator evidence plus long-gap proof shapes closed the gate. |
| 4. True Recovery | `done` | Runtime/work-session effects can be classified and safely retried/requeued or surfaced for review. |
| 5. Self-Improving Mew | `done` | Five consecutive no-rescue self-improvement loops passed with review and verification. |
| 5.1 Trust & Safety Close-Out | `done` | Post-M5 hardening added adversarial review and safety hooks without changing the M5 gate. |
| 6. Body: Daemon & Persistent Presence | `done` | 4-hour daemon proof passed strict summary; retained-artifact false-negative caveat is archived. |
| 6.5 Self-Hosting Speed | `done` | Compact resident rerun produced a verified paired edit proposal with first THINK under 10s. |
| 6.6 Coding Competence: Codex CLI Parity | `done` | Bootstrap, comparator slots, and frozen Codex CLI side-by-side batch passed with recorded caveats. |
| 6.7 Supervised Self-Hosting Loop | `done` | Reviewer-gated supervised iterations, reentry, and detached close-watch satisfied the gate. |
| 6.8 Task Chaining: Supervised Self-Selection | `done` | Close gate passed via `docs/M6_8_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.8.5 Selector Intelligence and Curriculum Integration | `done` | Close gate passed via `docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`. |
| 6.9 Durable Coding Intelligence | `done` | Close gate passed via `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`; Phase 4 moved to M6.8.5. |
| 6.10 Execution Accelerators and Mew-First Reliability | `done` | Latest 10 attempts reached 7/10 clean-or-practical with classified failures. |
| 6.11 Loop Stabilization | `done` | Core and residual hardening are closed; use its surfaces as diagnostics only. |
| 6.12 Failure-Science Instrumentation | `done` | V0 read-only ledger/classifier/report surface is closed. |
| 6.13 High-Effort Deliberation Lane | `done` | Close gate passed via `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`; deterministic and live gpt-5.5 internalization proofs apply and verify the later tiny solve through the normal work path. |
| 6.14 Mew-First Failure Repair Gate | `done` | Follow-on SR-017 side-project write-batch normalizer repair is recorded; M6.24 can resume broad measurement. |
| 6.15 Verified Closeout Redraft Repair | `merged_into_6.14` | Historical episode folded into M6.14. |
| 6.16 Codex-Grade Implementation Lane | `done` | Close gate passed via `docs/M6_16_CLOSE_GATE_AUDIT_2026-04-27.md`; residual first-edit samples feed M6.17/M6.14 rather than keeping M6.16 open. |
| 6.17 Resident Meta Loop / Lane Chooser | `done` | Close gate passed via `docs/M6_17_CLOSE_GATE_AUDIT_2026-04-27.md`; v0 remains reviewer-gated. |
| 6.18 Implementation Failure Diagnosis Gate | `done` | Close gate passed via `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md`; M7+ dogfood now routes failures through diagnosis before M6.14 repair. |
| 6.19 Terminal-Bench Compatibility | `done` | Close gate passed via `docs/M6_19_TERMINAL_BENCH_COMPATIBILITY_AUDIT_2026-04-27.md`; mew and Codex both run the bounded Harbor smoke with comparable artifacts. |
| 6.20 Terminal-Bench Driven Implement-Lane Debugging | `done` | Fixed two-task terminal gate closed on current head: both selected tasks reached 5/5 with Harbor errors 0. |
| 6.21 Terminal-Bench Codex Target Registry | `done` | Codex `0.121.0` / `gpt-5.5@openai` Terminal-Bench 2.0 leaderboard was frozen as JSON for future parity gates. |
| 6.22 Terminal-Bench Curated Subset Parity | `done` | Close gate passed via `docs/M6_22_CLOSE_GATE_AUDIT_2026-04-28.md`; mew reached 17/35 vs Codex target 20/35 with repair rerun evidence. |
| 6.23 Terminal-Bench Failure-Class Coverage | `done` | Close gate passed via `docs/M6_23_CLOSE_GATE_AUDIT_2026-04-28.md`; grounded edit-scope repair improved `overfull-hbox` to 3/5. |
| 6.24 Broad Terminal-Bench Parity Campaign | `in_progress` | Improvement phase active; runtime artifact freshness repair is implemented and awaiting same-shape rerun. |
| 6.25 Codex-Plus Resident Advantage | `not_started` | Preserve parity while proving mew-native memory/reentry/repair makes it preferable to inhabit. |
| 7. Senses: Inbound Signals | `pending` | Paused by user decision on 2026-04-27 while Terminal-Bench compatibility/debugging is added first; existing M7 signal work is preserved. |
| 8. Identity: Cross-Project Self | `not_started` | User-scope identity and cross-project memory remain future work. |
| 9. Legibility: Human-Readable Companion | `not_started` | Human-readable companion state remains future work. |
| 10. Multi-Agent Residence | `not_started` | Multi-model shared residence remains future work. |
| 11. Inner Life | `not_started` | Journal/dream/mood/self-memory continuity remains future work. |

## Active Milestone

Active work: **M6.24 Broad Terminal-Bench Parity Campaign**.

Why M6.24 is active now:

- User decision on 2026-04-27: pause M7 and add Terminal-Bench milestones
  before continuing the senses roadmap.
- User decision on 2026-04-29: M6.24 is a measurement / improvement loop, not
  a pure "measure all tasks first" campaign. If the batch gap to Codex exceeds
  the threshold, pause broad measurement, repair a generic gap class, rerun the
  same failed shape, then continue measuring.
- User decision on 2026-04-28: if M6.24 exposes an accepted structural
  problem, stop broad measurement, set M6.24 to `pending`, and repair the
  substrate through M6.14 before returning to the same failing shape.
- M6.24 Batch 3 `polyglot-rust-c` exposed SR-010:
  exact backticked command examples in the task text were not treated as
  finish-gating acceptance evidence. Trials self-finished after nearby checks
  that changed cwd or used Python wrappers instead of proving the advertised
  command shapes from task cwd. It is now repaired.
- M6.24 Batch 3 `model-extraction-relu-logits` exposed SR-011:
  query-only hidden-model tasks could finish after visible fixture checks such
  as `forward.A1` or local visible-weight cosine checks without synthetic or
  holdout validation. It is now repaired.
- M6.24 Batch 3 `install-windows-3.11` exposed SR-012:
  the local Harbor wrapper imposed an inner 900 second timeout and used
  container-local report paths even though the task timeout is 3600 seconds.
  It is now repaired.
- M6.24 Batch 3 `mcmc-sampling-stan` pre-repair attempt exposed SR-013:
  `run_command` still treated top-level shell operators as argv tokens, so
  `mkdir -p ... && HOME=... Rscript -e ...` failed as `mkdir: invalid option
  -- 'e'`. It is now repaired by shell execution for top-level
  `run_command` operators, non-shell `run_tests` preservation, and
  resident-loop guardrails.
- M6.20 closed the first fixed terminal gate on current head:
  `cancel-async-tasks` 5/5 and `fix-code-vulnerability` 5/5, both with Harbor
  errors 0.
- M6.21 froze the Codex `0.121.0` / `gpt-5.5@openai` Terminal-Bench 2.0 target
  registry as local JSON.
- M6.22 closed the fixed multi-band subset run and showed that mew remains
  below Codex target on two structural failure classes.
- M6.23 closed failure-class coverage and proved one ranked generic repair:
  grounded edit-scope evidence improved `overfull-hbox` from 2/5 to 3/5,
  matching its frozen Codex target.
- M6.24 Batch 2 produced selected structural blockers that made continued
  broad measurement low-value until repaired:
  `domain_ground_truth_verifier_surrogate_false_green` / exact external-tool
  verifier grounding from `dna-assembly`, and timeout / partial observability
  for long domain/document repair loops from `financial-document-processor`
  and `dna-assembly`, plus video/frame artifact observation timeout from
  `extract-moves-from-video`.
- M6.14 repair episode for those selected blockers is now closed:
  SR-001 timeout / partial observability is repaired by atomic partial reports
  plus Harbor `container_repo_root` report mapping; SR-002 exact external-tool
  false green is repaired by the exact-command finish gate plus exact-tool
  unavailable blocker proof; SR-003 artifact observation is repaired by generic
  ordered `read_images`, resume-visible observation transcripts, and large
  chronological chunk guidance.

M6.24 resume condition:

- Controller docs:
  `docs/M6_24_DECISION_LEDGER.md` and
  `docs/M6_24_GAP_BASELINE_2026-04-29.md`. Improvement-phase work must also
  follow `docs/M6_24_GAP_IMPROVEMENT_LOOP.md` and record gap state in
  `proof-artifacts/m6_24_gap_ledger.jsonl`.
- Current controller mode: `improvement_phase`.
- M6.24 measured baseline on 2026-04-29 is **mew 92/210 = 43.8%** vs
  **Codex 156/210 = 74.3%**, absolute gap **-30.5 percentage points**.
  Batch 2, Batch 3, Batch 4, Batch 5, and partial Batch 6 all exceed the
  `> 20 pp` improvement threshold. Do not continue broad measurement just
  because Batch 6 still lists `gpt2-codegolf` as pending.
- If a new accepted structural blocker appears, pause M6.24, append it to
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`, repair it through M6.14, record
  focused validation, and rerun the same failed task shape before resuming
  broad measurement.
- During `improvement_phase`, the next action must be one of: classify a
  measured failure into the gap ledger, add instrumentation for a selected gap,
  repair one selected gap class, rerun the same shape after repair, or update
  the decision ledger to resume measurement with evidence. New broad benchmark
  measurement is drift until the controller says otherwise.
- Current selected gap class:
  `hard_task_implementation_strategy_contract_retention`, recorded in
  `docs/M6_24_GAP_CLASS_PLAN_2026-04-29.md` and
  `proof-artifacts/m6_24_gap_ledger.jsonl`. The v0 reference-backed repair is
  recorded in
  `docs/DESIGN_2026-04-29_M6_24_HARD_TASK_CONTRACT_CAPSULE.md`: hard-task
  `working_memory.implementation_contract` plus a pre-finish source grounding
  blocker. The same-shape rerun is recorded in
  `docs/M6_24_HARD_TASK_CONTRACT_RERUN_2026-04-29.md`: `make-doom-for-mips`
  stayed 0/5, but the behavior improved from surrogate/stub completions to
  source-built ELF and VM-loader/runtime repair attempts with no false complete
  state. codex-ultra review in
  `docs/REVIEW_2026-04-29_M6_24_HARD_CONTRACT_RERUN_NEXT.md` selects the next
  primary blocker as hard-runtime verifier strategy, with package permissions
  and task budget as secondary amplifiers. That v0 repair is recorded in
  `docs/DESIGN_2026-04-29_M6_24_HARD_RUNTIME_VERIFIER_STRATEGY.md`: failed
  VM/emulator/interpreter verifier output now becomes a resume-visible
  `runtime_contract_gap` with PC/opcode/artifact evidence and
  readelf/nm/objdump/addr2line mapping guidance. The same-shape rerun is
  recorded in `docs/M6_24_HARD_RUNTIME_RERUN_2026-04-29.md`: score stayed 0/5,
  but permission waits disappeared, no surrogate/stub completion dominated, one
  trial self-verified exact `node vm.js` plus a valid 640x400 32bpp frame, and
  the external verifier reached 2/3 on the best trial. The next selected blocker
  is generic runtime artifact freshness / external verifier alignment: stale
  `/tmp/frame.bmp` left by self-verification can short-circuit the external
  verifier's fresh-run wait and cause premature stdout capture. The v0 repair
  is recorded in
  `docs/DESIGN_2026-04-29_M6_24_RUNTIME_ARTIFACT_FRESHNESS.md`: finish is now
  blocked when a fresh-runtime task self-verifies a generated `/tmp/...`
  artifact without later cleanup, and resume exposes `stale_runtime_artifact_risk`.
  The same-shape rerun is recorded in
  `docs/M6_24_RUNTIME_FRESHNESS_RERUN_2026-04-29.md`: score stayed 0/5, but
  the stale `/tmp/frame.bmp` short-circuit disappeared. All external verifiers
  now waited for a fresh frame and failed because no final `/tmp/frame.bmp`
  existed. The next selected blocker is
  `hard_runtime_final_verifier_state_transfer`: mew must preserve useful
  VM/build evidence and convert it into a final deliverable state that a fresh
  external verifier can reproduce. Before adding another hard-task repair,
  record `hard_task profile v0` so M6.24 hard-task policies have one
  implementation-profile boundary. That profile is now recorded in
  `docs/DESIGN_2026-04-29_M6_24_HARD_TASK_PROFILE_V0.md`: hard coding tasks
  stay in `implementation/tiny`, with no new authoritative lane in M6.24. Next
  action is to implement the smallest generic final-verifier state-transfer
  repair, then run a 1-trial same-shape speed rerun for `make-doom-for-mips`.
  That v0 repair is recorded in
  `docs/DESIGN_2026-04-29_M6_24_FINAL_VERIFIER_STATE_TRANSFER.md`: finish now
  blocks fresh-runtime command success without required `/tmp/...` artifact
  proof, and resume surfaces `final_verifier_state_transfer`. Do not spend
  `-k 5 -n 5` unless the speed rerun shows material improvement,
  contradictory variance, or the controller is ready for close/resume proof.
  The speed-rerun is recorded in
  `docs/M6_24_FINAL_VERIFIER_TRANSFER_SPEED_RERUN_2026-04-29.md`: score stayed
  0/1, but `final_verifier_state_transfer` surfaced, the agent did not finish
  after command success without artifact proof, and the task advanced to a
  concrete runtime blocker `W_GetNumForName: STCFN33 not found`. Do not
  escalate this to `-k 5 -n 5`; choose the next highest-leverage gap instead.
  Do not resume new broad measurement yet unless the decision ledger explicitly
  changes controller mode.
- Canonical structural blocker queue:
  `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`. Append accepted blockers there so
  context compression and milestone transitions do not lose repair obligations.
- Closed M6.14 episode:
  SR-001 timeout / partial observability is `repaired`; generic code landed in
  `a87754e` and wrapper path mapping in `a3cf090`. Same-shape Harbor rerun
  `mew-m6-14-sr001-financial-document-processor-1attempt-container-report-20260428-1640`
  still timed out after 900s, but preserved host-visible `mew-report.json` with
  the active work-session resume bundle, unresolved failures, recent decisions,
  current working memory, and next action.
- Closed M6.14 follow-on episode:
  SR-002 finish/verifier grounding false green is `repaired`. The first
  generic code slice blocks `finish task_done=true` when the task names an
  exact external ground-truth command/tool and flags but acceptance evidence
  does not cite a completed `run_command` or `run_tests` containing the exact
  command shape. Same-shape `dna-assembly` rerun
  `mew-m6-14-sr002-dna-assembly-1attempt-exact-ground-truth-20260428-1645`
  did not false-green, but timed out after detecting `oligotm NOT_FOUND` and
  drifting into local `primer3-py` surrogate exploration. A smaller exact-tool
  unavailable proof
  `proof-artifacts/m6-14-sr002-exact-tool-unavailable-smoke-20260428-1651/agent/mew-report.json`
  then ran the required exact command, observed executable-not-found, and
  stopped with `task_done=false` plus a blocked acceptance check instead of
  substituting a surrogate.
- Closed M6.14 follow-on episode:
  SR-003 artifact observation substrate is `repaired` for ordered image
  artifact sets. The generic repair added `read_images` with allowed-root,
  MIME, per-image, aggregate-byte, and 16-image caps; work-session resumes now
  preserve recent `read_images` observation transcripts; and the prompt tells
  visual/document/video tasks to transform raw artifacts with bash/Python and
  read the largest chronological image chunks that fit. Same-shape Harbor proof
  `mew-m6-14-sr003-extract-moves-from-video-1attempt-read-images-largechunks-20260428-1843`
  reached 1/1 with errors 0 after extracting 96 frames into eight contact
  sheets and writing `/app/solution.txt`.
- Closed M6.14 follow-on episode:
  SR-004 shell-wrapper literal parse gap is `repaired`. M6.24 Batch 3
  `build-pov-ray` scored 2/5 against Codex target 5/5, with two failed trials
  stopping on `No closing quotation` before practical multiline
  `bash -lc 'python3 - <<"PY" ... PY'` scripts could execute. `split_command_env`
  now falls back for recognized `bash`/`sh`/`zsh` `-c`/`-lc`/`-cl` wrappers when
  normal shlex parsing fails, passing `[shell, flag, script]` under
  `shell=False`. Same-shape proof
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__20-33-30/result.json`
  reached 1/1 with no `No closing quotation` recurrence.
- Closed M6.14 follow-on episode:
  SR-007 coordinated multi-file patch shape failure from GitHub issue #18 is
  `repaired`. Mixed write/wait batches now normalize to an actionable
  top-level blocker, and the executor no longer runs a synthetic `wait`
  pseudo-tool when write-batch normalization fails. Focused regression covered
  `edit_file_hunks` plus `wait` and verified zero tool calls plus
  `batch_blocked=true`.
- Closed M6.14 follow-on episode:
  SR-008 direct Python pytest-file false green is `repaired`. M6.24 Batch 3
  `break-filter-js-from-html` exposed trials that ran
  `python /app/test_outputs.py`, got exit 0 because pytest tests were only
  defined, then failed Harbor's external pytest verifier. `run_tests` now
  normalizes pytest-style direct Python file invocations to
  `python -m pytest -q <file>` and preserves the original command. Same-shape
  proof `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__19-55-56/result.json`
  scored 0/1 but no longer false-greened; the report shows the normalized
  pytest command failed before the model continued with verifier feedback.
- Closed M6.14 follow-on episode:
  SR-009 broad rollback slice repair from reopened GitHub issue #18 is
  `repaired`. Repeated verifier rollbacks or broad failed-test output now
  surface `broad_rollback_slice_repair` in the work-session resume, formatted
  resume, main/write-ready prompts, and deliberation context. The next turn is
  steered away from retrying the whole coordinated patch and toward one smaller
  complete source/test/docs slice while carrying remaining scope in
  `working_memory`.
- Closed M6.14 follow-on episode:
  SR-010 exact command example finish gap is `repaired`. The finish gate now
  extracts exact backticked command examples from task text and blocks
  `task_done=true` unless acceptance evidence cites a completed
  `run_command`/`run_tests` whose command text runs the advertised shell shape
  with a concrete placeholder value and without cwd/output-location mutation.
  Same-shape
  `polyglot-rust-c` proof
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__21-23-44/result.json`
  stopped with `ask_user` after observing that the exact Rust command creates
  `/app/main`, not `/app/polyglot/main`, instead of false-finishing.
- Closed M6.14 follow-on episode:
  SR-011 query-only hidden-model visible fixture false green is `repaired`.
  The finish gate now blocks generated source that reads visible hidden-weight
  internals or fixture source for black-box/query-only `forward` oracle tasks,
  and requires synthetic/randomized/holdout/generalization evidence before
  `task_done=true`. Same-shape
  `model-extraction-relu-logits` proof
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__23-29-21/result.json`
  reached 1/1 after first blocking visible-fixture-only finish and then
  requiring randomized synthetic validation.
- Closed M6.14 follow-on episode:
  SR-012 Harbor wrapper inner timeout cap and unmapped partial report is
  `repaired`. `.harbor/mew_terminal_bench_agent.py` now defaults
  `timeout_seconds=None`, captures explicit wrapper timeouts as normal command
  transcripts with `exit_code=124`, and Batch manifests pass
  `container_repo_root=/mew`. The wrapper timeout proof
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-14-sr012-wrapper-timeout-no-error-20260429-0017/result.json`
  recorded `n_errors=0` with a host-visible timeout transcript.
- M6.24 Batch 2 `dna-insert` was measured after SR-003 and before the #18
  repair pivot: 1/5, errors 0, runtime 10m 34s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__19-03-50/result.json`.
  This is broad parity evidence, not yet an accepted structural repair signal.
- M6.24 Batch 2 `caffe-cifar-10` then completed the batch: 0/3 completed
  reward trials, 2 RuntimeError command timeouts, runtime 16m 46s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__19-23-11/result.json`.
  Because the frozen Codex target is 0/5, this is runner-error debt but not a
  selected repair by itself.
- M6.24 Batch 3 has started. `break-filter-js-from-html` baseline scored 0/5
  against Codex target 5/5 and selected SR-008 for immediate repair. After the
  repair proof, the remaining 0/5 is a task-solving gap rather than the direct
  Python pytest-file false-green substrate bug.
- M6.24 Batch 3 `build-pov-ray` scored 2/5 against Codex target 5/5, errors 0,
  runtime 11m 58s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__20-16-05/result.json`.
  It selected and repaired SR-004. One additional failed trial finished despite
  a hidden source/archive completeness miss (`file_id.diz` and related files
  absent), which remains implementation-lane evidence rather than a selected
  core repair.
- M6.24 Batch 3 `polyglot-rust-c` scored 0/5 against Codex target 4/5, errors
  0, runtime 11m 23s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__20-45-24/result.json`.
  It selected and repaired SR-010. Same-shape proof stopped without
  false-finishing when the exact advertised Rust command wrote `/app/main`.
- M6.24 Batch 3 `model-extraction-relu-logits` scored 0/5 against Codex target
  4/5, errors 0, runtime 15m 7s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-28__22-02-51/result.json`.
  It selected and repaired SR-011. Same-shape proof reached 1/1 with hidden
  verifier pass after requiring randomized synthetic validation.
- M6.24 Batch 3 `install-windows-3.11` uses Harbor canonical task name
  `install-windows-3-11`. It scored 0/5 against Codex target 0/5, but all five
  trials were wrapper `RuntimeError: Command timed out after 900 seconds`
  errors. It selected and repaired SR-012. This remains a 0/5 task result but
  should no longer produce wrapper errors on future long-task runs.
- M6.24 Batch 3 `make-doom-for-mips` scored 0/5 against Codex target 1/5,
  errors 0, runtime 12m 52s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__00-29-51/result.json`.
  This is recorded as task-solving / surrogate-build evidence, not an accepted
  structural blocker yet.
- M6.24 Batch 3 `mcmc-sampling-stan` pre-repair attempt
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__00-45-34`
  was interrupted after SR-013 was accepted and is not counted as a score.
  Same-shape substrate proof
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-14-sr013-run-command-shell-chain-20260428T161435Z/result.json`
  passed with `execution_mode=shell`, `exit_code=0`, environment propagation,
  shell redirection, and nested resident-loop rejection.
- M6.24 Batch 3 repaired-head `mcmc-sampling-stan` rerun scored 0/5 against
  Codex target 2/5, with 5 `AgentTimeoutError`s and runtime 32m 32s:
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__01-19-36/result.json`.
  The SR-013 shell-chain failure did not recur; verifier failures centered on
  missing `rstan`, missing output files after timeout, or fallback analysis
  instead of `rstan::sampling`. Treat this as task-solving / long dependency
  strategy evidence, not a new accepted structural blocker.
- M6.24 Batch 3 `video-processing` scored 0/5 against Codex target 3/5,
  errors 0, runtime 11m 16s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__01-56-57/result.json`.
  The work loop analyzed videos and wrote scripts without runner errors, but
  hidden `test_video.mp4` frame ranges failed. Treat this as task-solving /
  hidden-video generalization evidence, not a new accepted M6.14 structural
  blocker.
- M6.24 Batch 3 is now fully measured: latest full task-run total **2/40**
  against frozen Codex target **24/40**.
- M6.24 Batch 4 is selected in
  `docs/M6_24_BATCH_4_MANIFEST_2026-04-29.md` and
  `docs/data/terminal_bench_m6_24_batch_4.json`. It covers remaining
  available unmeasured Codex success bands 0/5, 3/5, 4/5, and 5/5; the 1/5
  and 2/5 unmeasured bands are exhausted. Frozen Codex Batch 4 target:
  **25/40**.
- M6.24 Batch 4 `sam-cell-seg` scored 0/5 against Codex target 0/5, errors
  0, runtime 9m 26s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__02-16-06/result.json`.
  This is a low-target control matching Codex, not a selected structural
  repair signal.
- M6.24 Batch 4 `train-fasttext` partial attempt completed 3/5 requested
  trials before cancellation: 0/3 completed rewards, errors 0 among completed
  trials, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__02-27-54/result.json`.
  Two remaining trials entered Docker/Harbor teardown or verifier hangs with
  `Docker compose down failed` / `tried to kill container, but did not receive
  an exit event`. Because the frozen Codex target is 0/5 and the completed
  trials already matched 0/3, record this as partial runner/benchmark-harness
  debt and do not select a core M6.14 repair from it.
- M6.24 Batch 4 `make-mips-interpreter` scored 0/5 against Codex target 3/5,
  with 1 `AgentTimeoutError`, runtime 32m 17s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__03-53-16/result.json`.
  Several trials created `/tmp/frame.bmp` close enough to pass frame checks but
  missed the exact Doom initialization stdout string. Treat this as
  task-solving / surrogate execution fidelity evidence, not an accepted M6.14
  structural blocker.
- M6.24 Batch 4 `torch-pipeline-parallelism` scored 0/5 against Codex target
  3/5, errors 0, runtime 13m 19s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__04-42-38/result.json`.
  A prior pre-cleanup artifact at
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__04-27-57/result.json`
  is diagnostic only because Docker verifier disk exhaustion contaminated it.
  The counted post-cleanup run still had repeated Torch/CUDA verifier
  `No space left on device` failures, plus one functional gradient-parity
  mismatch. Treat this as verifier-resource debt mixed with task-solving
  evidence, not an accepted M6.14 structural blocker.
- M6.24 Batch 4 `protein-assembly` scored 0/5 against Codex target 4/5,
  errors 3 `AgentTimeoutError`, runtime 31m 56s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__04-59-28/result.json`.
  It selected SR-014: the Harbor wrapper delegated timeout to the outer runner,
  while `mew work --oneshot` received no inner `--max-wall-seconds` budget.
  Three trials therefore reached outer agent timeout with only partial reports
  and running model turns. SR-014 is repaired by Harbor wrapper wall-budget
  placeholders plus explicit M6.24 run-shape timeout propagation. Bounded proof
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-14-sr014-protein-wall-budget/2026-04-29__05-38-06/result.json`
  reran the same task shape with `timeout_seconds=120` and reached
  `n_errors=0`; mew self-stopped with a final `wall_timeout` report before the
  outer Harbor timeout.
- M6.24 Batch 4 `adaptive-rejection-sampler` scored 1/5 against Codex target
  5/5, errors 3 `AgentTimeoutError`, runtime 17m 45s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__05-46-31/result.json`.
  It selected SR-015: the run shape passed wrapper `timeout_seconds=1800` and
  mew `--max-wall-seconds 1740`, but Harbor's own agent execution timeout was
  still 900 seconds. SR-015 is repaired by adding
  `--agent-timeout-multiplier 2` to the Batch 4 manifest. Same-shape proof
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-14-sr015-adaptive-agent-timeout-align/2026-04-29__06-06-11/result.json`
  reran one trial with Harbor agent timeout aligned and reached `n_errors=0`
  with a normal verifier result instead of outer `AgentTimeoutError`.
- M6.24 Batch 4 `cobol-modernization` scored 5/5 against Codex target 5/5,
  errors 0, runtime 4m 25s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__06-18-16/result.json`.
  Treat this as clean parity evidence and continue broad measurement.
- M6.24 Batch 4 `constraints-scheduling` scored 5/5 against Codex target 5/5,
  errors 0, runtime 6m 55s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__06-24-38/result.json`.
  Batch 4 full measured total is **11/35** against frozen Codex target
  **25/35**, excluding the partial `train-fasttext` control run. The clean
  later passes show the SR-015 timeout alignment is good enough to continue
  measurement.
- M6.24 Batch 5 is selected in
  `docs/M6_24_BATCH_5_MANIFEST_2026-04-29.md` and
  `docs/data/terminal_bench_m6_24_batch_5.json`. It covers the next unseen
  frozen Codex 5/5 registry slice: `bn-fit-modify`, `circuit-fibsqrt`,
  `compile-compcert`, `count-dataset-tokens`, `crack-7z-hash`,
  `custom-memory-heap-crash`, `distribution-search`, and
  `feal-differential-cryptanalysis`.
- M6.24 Batch 5 `bn-fit-modify` scored 5/5 against Codex target 5/5, errors
  0, runtime 6m 38s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__06-36-31/result.json`.
  Treat this as clean parity evidence.
- M6.24 Batch 5 `circuit-fibsqrt` scored 5/5 against Codex target 5/5, errors
  0, runtime 11m 38s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__06-44-55/result.json`.
  Treat this as clean parity evidence.
- M6.24 Batch 5 `compile-compcert` scored 0/5 against Codex target 5/5, errors
  0, runtime 4m 2s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__06-58-06/result.json`.
  All trials stopped as `wait` before material work because the task/verifier
  requires `/tmp/CompCert`, while the Batch 5 command shape did not allow
  `/tmp`.
- This selected and repaired SR-016: Batch 5 now treats `/tmp` as generic
  container scratch/build space via `--allow-read /tmp --allow-write /tmp`.
  Same-shape proof
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-14-sr016-compile-compcert-tmp-permission/2026-04-29__07-03-03/result.json`
  reached 10 work steps touching `/tmp/CompCert` and ended as `wall_timeout`,
  not immediate permission wait. The remaining `compile-compcert` gap is
  task-solving / long-build strategy.
- Closed M6.14 follow-on episode:
  SR-017 from side-project issue #20 is `repaired`. `normalize_work_model_action`
  now treats an `edit_file` action carrying an `edits` list and no scalar
  `old`/`new` as `edit_file_hunks` before write-batch classification. The
  focused regression covers the side-project failure shape where a source edit
  plus multi-hunk test edit was incorrectly downgraded into a read/write mixed
  batch. Targeted pytest and ruff passed.
- M6.24 Batch 5 `count-dataset-tokens` scored 4/5 against Codex target 5/5,
  errors 0, runtime 5m 40s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__07-42-06/result.json`.
  The single failed trial wrote `79566` while the verifier expected `79586`;
  treat this as task-solving / numeric-counting precision evidence, not an
  accepted M6.14 structural blocker.
- M6.24 Batch 5 `crack-7z-hash` scored 3/5 against Codex target 5/5, errors
  0, runtime 28m 45s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__07-50-00/result.json`.
  The two failed trials ended without `/app/solution.txt` after candidate
  password extraction attempts failed; treat this as task-solving /
  password-cracking strategy evidence, not an accepted M6.14 structural
  blocker.
- M6.24 Batch 5 `custom-memory-heap-crash` scored 4/5 against Codex target
  5/5, errors 0, runtime 12m 22s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__08-21-18/result.json`.
  The single failed trial left the release build crashing and hit gdb ptrace /
  register observation friction; treat this as low-level debugging /
  task-solving evidence and watch-list signal, not an accepted M6.14 blocker.
- M6.24 Batch 5 `distribution-search` scored 5/5 against Codex target 5/5,
  errors 0, runtime 4m 23s by individual trial timestamps, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__08-35-41/result.json`.
  The top-level result has `finished_at: null` because the interruption/control
  boundary happened after all individual trial result files were written; every
  individual trial has reward 1.0 and `exception_info: null`.
- M6.24 Batch 5 `feal-differential-cryptanalysis` scored 5/5 against Codex
  target 5/5, errors 0, runtime 9m 52s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__08-51-16/result.json`.
  Treat this as clean parity evidence.
- M6.24 Batch 5 is complete: **31/40** against frozen Codex target **40/40**,
  with Harbor errors 0 across all eight counted task runs. It produced one
  accepted structural repair, SR-016 `/tmp` scratch permission; the remaining
  below-target rows are task-solving evidence.
- M6.24 Batch 6 is selected in
  `docs/M6_24_BATCH_6_MANIFEST_2026-04-29.md` and
  `docs/data/terminal_bench_m6_24_batch_6.json`. It covers the next unseen
  frozen Codex 5/5 registry slice: `feal-linear-cryptanalysis`,
  `fix-ocaml-gc`, `git-multibranch`, `gpt2-codegolf`, `headless-terminal`,
  `hf-model-inference`, `largest-eigenval`, and
  `llm-inference-batching-scheduler`.
- M6.24 Batch 6 `feal-linear-cryptanalysis` scored 5/5 against Codex target
  5/5, errors 0, runtime 4m 12s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__09-07-19/result.json`.
  Treat this as clean parity evidence.
- M6.24 Batch 6 `fix-ocaml-gc` scored 4/5 against Codex target 5/5, errors
  0, runtime 51m 57s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__10-05-42/result.json`.
  A prior artifact at
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__09-13-22/result.json`
  was manually interrupted too early during long verifier execution and is not
  counted. Treat the counted 4/5 result as task-solving / runtime repair
  evidence, not an accepted M6.14 structural blocker.
- M6.24 Batch 6 `git-multibranch` produced 1/4 completed reward trials
  against Codex target 5/5, plus 1 setup error, runtime 26m 47s, artifact
  `proof-artifacts/terminal-bench/harbor-smoke/2026-04-29__10-59-27/result.json`.
  Completed trials scored 1 pass / 3 fail; `git-multibranch__o4HqSBy` failed
  before mew work during the agent setup install command with
  `NonZeroAgentExitCodeError` exit 100. Treat this as task-solving plus
  runner/setup debt, not an accepted M6.14 structural blocker unless the same
  install/setup shape repeats.

Next concrete action:

- Do not run the next broad-measurement task yet. First classify the measured
  Batch 1-6 failures into gap classes, choose one generic improvement target,
  name the failed task shape to rerun after repair, and record that selection
  in `docs/M6_24_DECISION_LEDGER.md`. After the repair and same-shape rerun are
  recorded, resume broad measurement with Batch 6.

Closed M6.22 result:

- curated subset manifest:
  `docs/M6_22_CURATED_SUBSET_MANIFEST_2026-04-27.md`
- local subset JSON:
  `docs/data/terminal_bench_m6_22_curated_subset.json`
- run ledger:
  `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`
- close audit:
  `docs/M6_22_CLOSE_GATE_AUDIT_2026-04-28.md`
- selected tasks and Codex targets:
  `filter-js-from-html` 0/5, `sanitize-git-repo` 1/5,
  `gcode-to-text` 2/5, `overfull-hbox` 3/5, `extract-elf` 4/5,
  `cancel-async-tasks` 5/5, and `fix-code-vulnerability` 5/5
- aggregate Codex target: 20/35 successes, 57.14%
- selected task runs:
  `filter-js-from-html` completed 0/5 with 5 `VerifierTimeoutError`
  exceptions in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json`;
  `sanitize-git-repo` completed 1/5 with Harbor errors 0 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-sanitize-git-repo-5attempts-20260427-2245/result.json`.
  `gcode-to-text` completed 0/5 with 1 `AgentTimeoutError` in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json`.
  `overfull-hbox` completed 1/5 with Harbor errors 0 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-overfull-hbox-5attempts-python-bootstrap-20260427-2315/result.json`.
  `extract-elf` completed 5/5 with Harbor errors 0 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-extract-elf-5attempts-python-bootstrap-20260427-2334/result.json`.
  Current full M6.22 total is 17/35, below the frozen Codex 20/35 target.
- below-target classification:
  `gcode-to-text` is classified as M6.18 `structural`, confidence medium,
  `structural_reason = missing_visual_decode_artifact_grounding`, with
  secondary `agent_wall_timeout_without_report`. `overfull-hbox` is classified
  as M6.18 `structural`,
  confidence medium-high,
  `structural_reason = insufficient_acceptance_constraint_model`, with a
  secondary `repeat_action_after_partial_repair` signal.
- M6.22 repair rerun:
  commit `29335c9` added acceptance checks and regressed `overfull-hbox` to
  0/5 because repairable constraint blockers terminated as `wait`; commit
  `2d0b5c4` converted those waits into continuity notes while budget remains
  and reran `overfull-hbox` at 2/5. Remaining gap moves to M6.23.
- M6.20 positive-control artifacts remain available for the two 100% tasks.

Closed M6.23 result:

- `docs/M6_23_FAILURE_CLASS_COVERAGE_2026-04-28.md` ranks the observed
  curated-subset failure classes and selects the first repair.
- close audit:
  `docs/M6_23_CLOSE_GATE_AUDIT_2026-04-28.md`
- selected first repair:
  `self_reported_acceptance_evidence_not_grounded_in_diff_validator` ->
  grounded edit-scope acceptance validator, implemented by commit `47a3393`.
- rerun artifact:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-23-overfull-hbox-5attempts-edit-scope-grounding-20260428-0032/result.json`
- rerun result: `overfull-hbox` 3/5, mean 0.600, pass@5 1.000,
  1 `AgentTimeoutError`; verdict improved vs M6.22's 2/5 repair rerun.
- Deferred ranked classes:
  `missing_visual_decode_artifact_grounding`,
  `agent_wall_timeout_without_report`, `shell_quoting_multiline_command`, and
  `verifier_timeout_no_edit`.
- Already repaired class:
  `repairable_constraint_blocker_terminal_wait` by commit `2d0b5c4`.

Current M6.24/M6.14 chain:

`M6.24 broad parity evidence -> M6.18 classification -> accepted structural blocker -> M6.24 pending -> M6.14 bounded generic repair -> rerun same failed task shape -> resume M6.24`

M6.24 Batch 1:

- manifest: `docs/M6_24_BATCH_1_MANIFEST_2026-04-28.md`
- local batch JSON: `docs/data/terminal_bench_m6_24_batch_1.json`
- run ledger: `docs/M6_24_BATCH_1_RUNS_2026-04-28.md`
- Batch 2 manifest: `docs/M6_24_BATCH_2_MANIFEST_2026-04-28.md`
- Batch 2 local JSON: `docs/data/terminal_bench_m6_24_batch_2.json`
- Batch 2 run ledger: `docs/M6_24_BATCH_2_RUNS_2026-04-28.md`
- selected tasks: `configure-git-webserver`, `db-wal-recovery`,
  `raman-fitting`, `chess-best-move`, `kv-store-grpc`,
  `build-cython-ext`, `code-from-image`, and `fix-git`
- frozen Codex target: 25/40 successes, 62.5%
- measured so far:
  - `build-cython-ext`: latest 0/5 after the same-file batch-blocker
    continuation repair, best observed 1/5, Codex target 5/5.
  - `chess-best-move`: latest 5/5 after all-valid answer gating plus
    acceptance-finish continuation, above Codex target 3/5; previous baseline
    and answer-artifact prompt repair were both 0/5, and post-`read_image`
    validation was 1/5.
  - `code-from-image`: latest 5/5 after the generic `read_image` repair,
    matched Codex target 5/5; previous baseline was 0/5.
  - `configure-git-webserver`: 0/5, matched Codex target 0/5, no Harbor
    errors.
  - `db-wal-recovery`: 2/5, above Codex target 1/5, no Harbor errors.
  - `fix-git`: 5/5, matched Codex target 5/5, no Harbor errors.
  - `kv-store-grpc`: latest 5/5 after generic exact-schema repair, above Codex
    target 4/5; previous baseline was 2/5.
  - `raman-fitting`: latest 0/5 after generic `analyze_table` and numeric
    artifact-quality finish gating, below Codex target 2/5; previous baseline
    and numeric-plausibility repair were both 0/5.
  - measured latest task total: 22/40 against frozen Codex target 25/40.
  - best observed measured total: 23/40 if `build-cython-ext` uses its best
    observed 1/5 rerun.
- completed first repair:
  `batch_missing_read_path_terminal_tool_failed`; commit `d519a3e` made
  read-only batches continue after missing paths under allowed write roots.
  Score stayed 0/5 but progressed trials moved further.
- completed second repair:
  `repeat_command_after_source_edit_blocked_by_total_repeat_guard`; commit
  `26a2647` reset repeat counts at the latest completed workspace-changing
  write. Score stayed 0/5 but the progressed trial reached 9/11 verifier tests
  before timing out.
- completed third repair:
  `stale_exact_text_edit_terminal_tool_failed`; commit `404f36c` made stale
  exact-text edit misses recoverable under allowed write roots while budget
  remains. Score stayed 0/5 but stale edit misses no longer terminated the
  loop.
- completed fourth repair:
  `git_status_not_repo_terminal_tool_failed`; commits `1ed31c7` and `fa82204`
  made unavailable git status recoverable both as a top-level tool and inside
  read-only batches. Commit `184ee1f` recorded the repair path. Score stayed
  0/5, but the terminal git-status boundary did not recur in the rerun.
- completed fifth repair:
  `run_tests_failure_terminal_tool_failed`; direct `run_tests` failures should
  become recoverable verifier observations while budget remains. The latest
  rerun improved `build-cython-ext` from 0/5 to 1/5. Commit `f91209e`
  implements the generic repair.
- completed sixth repair:
  `git_diff_not_repo_terminal_tool_failed`; read-only git inspection in
  filesystem-only workspaces should be recoverable generally, not only for
  `git_status`. Commit `dae6000` generalized the recovery for read-only
  git-inspection tools. The targeted boundary did not recur in the next
  non-timeout trials, but score regressed to 0/5.
- completed seventh repair:
  `run_tests_cd_prefix_shell_operator_terminal_tool_failed`; commit `3930af5`
  normalizes only the safe `cd DIR && <verifier>` shape into `cwd=DIR` plus a
  single verifier command, while preserving `run_tests` shell-chain rejection.
  The next rerun produced 5/5 `AgentTimeoutError`, so this repair could not be
  validated against `build-cython-ext`.
- current route:
  stop spending more `build-cython-ext`-only repair cycles until either
  timeout partial-report observability is improved or another Batch 1 task
  confirms the same shape. Run the next Batch 1 task to keep M6.24 broad.
- completed Batch 1 control:
  `fix-git` matched Codex at 5/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-fix-git-5attempts-20260428-0353/result.json`.
  This suggests the `build-cython-ext` timeout wall is task-shape-specific, not
  a universal Harbor/mew execution failure.
- completed eighth repair:
  `kv-store-grpc` scored 2/5 against Codex target 4/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-kv-store-grpc-5attempts-20260428-0359/result.json`.
  The dominant failure is `schema_field_name_substitution_false_green`: failed
  trials implemented `SetValRequest.val` even though the task specified request
  field `value`, while response fields used `val`. The generic repair is exact
  contract-name preservation in implementation prompts and self-verifiers.
  Commit `098d1e9` implemented that prompt repair and reran the task at 5/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-kv-store-grpc-5attempts-schema-contract-20260428-0410/result.json`.
- current route:
  continue broad Batch 1 measurement with the next unmeasured manifest task.
  Do not revisit `build-cython-ext` until timeout partial-report observability
  is selected as the active repair or another task confirms the same
  timeout-dominated shape.
- completed low-target measurement:
  `configure-git-webserver` matched Codex target 0/5 with no Harbor errors in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-configure-git-webserver-5attempts-20260428-0415/result.json`.
  This is measurement coverage only, not a repair candidate.
- completed low-band measurement:
  `db-wal-recovery` exceeded Codex target 1/5 by scoring 2/5 with no Harbor
  errors in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-db-wal-recovery-5attempts-20260428-0421/result.json`.
  This is measurement coverage only, not a repair candidate.
- completed ninth repair:
  `raman-fitting` scored 0/5 against Codex target 2/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-raman-fitting-5attempts-20260428-0426/result.json`.
  The dominant failure is `numeric_artifact_schema_only_false_green`: all
  trials produced `/app/results.json`, but internal checks only proved JSON
  shape or finite values while hidden tests rejected the fitted peak
  parameters. The generic repair is numeric plausibility verification for
  fitting/optimization/scientific scripting tasks before finish. Commit
  `defd1c3` implemented that prompt repair and reran the task at 0/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-raman-fitting-5attempts-numeric-plausibility-20260428-0438/result.json`.
  The repair changed behavior but did not improve score, so do not spend a
  third consecutive `raman-fitting` prompt-polish cycle. Continue broad Batch 1
  measurement; if another numeric/data task shows the same shape, prefer a
  reusable artifact-quality verifier scaffold over another prompt sentence.
- completed tenth repair:
  `chess-best-move` scored 0/5 against Codex target 3/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-chess-best-move-5attempts-20260428-0452/result.json`.
  The dominant failure is `answer_artifact_readback_false_green`: all trials
  wrote `/app/move.txt` and read it back, but hidden verification expected both
  `e2e4` and `g2g4` while observed outputs were incomplete or wrong. The
  generic repair is semantic answer-from-artifact verification for images,
  boards, puzzles, diagrams, screenshots, and data files, including
  completeness proof when all winning/valid answers are requested. Commit
  `db91b79` implemented that prompt repair and reran the task at 0/5 with one
  `AgentTimeoutError` in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-chess-best-move-5attempts-answer-artifact-20260428-0508/result.json`.
  The repair did not improve score, so do not spend a third consecutive
  `chess-best-move` prompt-polish cycle. Continue to `code-from-image` to get
  broader visual/artifact evidence before choosing a heavier generic repair.
- completed eleventh measurement:
  `code-from-image` scored 0/5 against Codex target 5/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-code-from-image-5attempts-20260428-0526/result.json`.
  There were no Harbor errors, but every trial failed because `/app/output.txt`
  was missing. The dominant failure is structural
  `visual_artifact_observation_missing`: mew tried to render and manually
  inspect `/app/code.png`, but without a native visual-artifact observation
  tool it stopped by max-step, remember, wait, or ask-user instead of computing
  the requested output. The next repair should be a generic image/visual
  artifact observation tool in the normal work path, not a benchmark-specific
  solver or another prompt-only polish cycle.
- completed twelfth repair:
  commit `5e963d3` added a generic `read_image` work tool backed by the Codex
  Responses API image input format. It keeps auth/model details in the
  execution context rather than persisted tool parameters and enforces normal
  allowed read roots and sensitive-path checks. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-code-from-image-5attempts-read-image-20260428-0558/result.json`
  improved `code-from-image` from 0/5 to 5/5 with Harbor errors 0 and runtime
  2m 51s. This repairs `visual_artifact_observation_missing` for this task and
  gives a reusable visual-artifact observation surface for screenshots,
  diagrams, boards, plots, and code screenshots.
- completed thirteenth cross-task validation:
  rerunning `chess-best-move` after the generic `read_image` repair scored
  1/5 with Harbor errors 0 and runtime 4m 28s in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-chess-best-move-5attempts-read-image-20260428-0603/result.json`.
  The pass case read the board image, derived the FEN, enumerated both
  mate-in-one moves, wrote `e2e4` and `g2g4`, and read the file back. The four
  failures still wrote only `e2e4`, so the remaining structural reason is
  `all_valid_answers_completeness_not_enforced`, not missing image access.
  The next repair should improve generic answer-space completeness proof for
  all-valid/all-winning answer tasks rather than adding a chess-specific
  solver.
- completed fourteenth repair:
  commit `6db7116` added a generic all-valid answer completion gate. It
  improved `chess-best-move` to 2/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-chess-best-move-5attempts-all-valid-gate-20260428-0613/result.json`,
  but blocked finishes could still become terminal stops with incomplete
  answer artifacts.
- completed fifteenth repair:
  commit `ce44a95` made acceptance finish blockers continue the work loop
  while budget remains. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-chess-best-move-5attempts-finish-block-continue-20260428-0620/result.json`
  improved `chess-best-move` to 5/5 with Harbor errors 0 and runtime 14m 9s,
  exceeding the frozen Codex target 3/5. This repairs
  `all_valid_answers_completeness_not_enforced` and
  `acceptance_finish_block_terminal_stop` generically. Track the increased
  runtime as a later implementation-lane ergonomics issue, not as a reason to
  revert the correctness repair.
- completed sixteenth measurement:
  rerunning `build-cython-ext` with the existing generic
  `mew work --oneshot --max-wall-seconds 780` path scored 0/5 with Harbor
  errors 0 and runtime 10m 4s in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-max-wall-780-20260428-0637/result.json`.
  This repaired the previous `AgentTimeoutError` opacity: every trial emitted
  `mew-report.json`, `command-transcript.json`, `summary.json`, and verifier
  output before stopping with `stop_reason = wall_timeout`. The remaining
  primary structural reason is now
  `multi_error_verifier_repair_not_closed_before_wall_timeout`, with secondary
  `scattered_legacy_compatibility_sweep_incomplete` and
  `dry_run_patch_not_converted_to_applied_patch_before_deadline`. Treat the
  next repair as generic verifier-failure repair planning, not a
  Cython-specific solver.
- completed seventeenth repair:
  commit `d1069ba` promoted verifier traceback/error output into
  `work_session.resume.verifier_failure_repair_agenda`. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-verifier-agenda-20260428-0710/result.json`
  scored 0/5 with Harbor errors 0 and runtime 9m 34s. The score stayed
  unchanged, but the failures are now more diagnosable: four trials hit
  `wall_timeout` with visible verifier targets, and one trial stopped because
  read-only batch observation treated a missing generated metadata directory
  as terminal.
- current route:
  repair generic missing generated-directory observations in read-only batches,
  then rerun `build-cython-ext`. If the missing-directory stop disappears and
  score is still below target, move to same-family verifier sibling-set repair
  rather than a benchmark-specific Cython solver.
- completed eighteenth repair:
  commit `85eade0` made missing generated-directory observations recoverable
  for `inspect_dir` and `read_file`, top-level and inside read-only batches,
  while budget remains. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-missing-dir-observation-20260428-0731/result.json`
  scored 0/5 with Harbor errors 0 and runtime 10m 4s. The previous
  missing-directory terminal stop did not recur; all attempts reached
  `wall_timeout`.
- current route:
  repair generic max-wall scheduling. The latest runs show mew stops before
  another model turn as soon as remaining wall time is less than the configured
  300s model timeout, leaving usable wall time idle. Reduce the per-turn model
  timeout to fit the remaining wall budget instead of stopping early, then
  rerun `build-cython-ext`.
- completed nineteenth repair:
  commit `84528a1` made max-wall scheduling reduce per-turn model timeout to
  fit the remaining wall budget, while preserving normal write-ready and
  deliberation timeout floors when the wall budget has room. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-wall-timeout-reduced-20260428-0755/result.json`
  scored 0/5 with Harbor errors 0 and runtime 14m 27s. The score stayed
  unchanged, but attempts used more wall time and hidden verifier tails
  improved to 8/11 or 9/11 pass patterns in most trials.
- current route:
  rerun `build-cython-ext` after committing the generic duplicate same-path
  write-batch wait repair, then pivot unless the result exposes a small generic
  repair. The sibling-search rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-sibling-search-20260428-0818/result.json`
  improved from 0/5 to 1/5 with Harbor errors 0 and pass@5 1.000. Remaining
  failures show mew often reaches README-smoke or near-repository-test-tail
  success, but one run stopped on a repairable "collapse same-file hunks"
  write-batch wait instead of continuing to a corrected batch.
- completed twentieth repair:
  commit `11f521f` converted the specific duplicate same-path write-batch
  normalization wait into recoverable continuity, without converting broad
  write-root blockers. The rerun
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-same-file-batch-wait-20260428-0841/result.json`
  scored 0/5 with Harbor errors 0 and runtime 13m 53s. The targeted same-file
  wait did not recur, but all trials stopped through `wall_timeout` with only
  a few seconds available for the last model call and hidden verifier tails
  still concentrated around repository tests and NumPy alias compatibility.
- current route:
  do not continue broad M6.24 measurement while an accepted structural blocker
  is selected for repair. M6.24 is pending behind the active M6.14 repair
  episode; resume only after a bounded generic repair is validated and rerun
  against the same failed task shape.
- latest source/test validation:
  `uv run pytest --no-testmon tests/test_work_session.py -k verifier_failure_repair_agenda -q`,
  `uv run pytest --no-testmon tests/test_work_session.py -q`, and
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
  passed for the verifier-agenda sibling-search repair. Codex-ultra review
  session `019dd139-62f4-7872-9ad2-00d5c018d3e9` reported `STATUS: pass`
  with no blocking issues.
- latest source/test validation:
  `uv run pytest --no-testmon tests/test_work_session.py -k "repairable_wait or work_model_batch_refuses_same_path" -q`,
  `uv run pytest --no-testmon tests/test_work_session.py -q`, and
  `uv run ruff check src/mew/commands.py tests/test_work_session.py` passed
  for the duplicate same-path write-batch wait repair. Codex-ultra review
  session `019dd14c-c236-7d63-9705-44595068365a` reported `STATUS: pass`
  after narrowing the marker to the specific `collapse same-file` reason and
  adding a negative write-root wait test.
- latest proof validation:
  the post-`11f521f` Harbor rerun completed with errors 0 but scored 0/5, so
  the repair removed its targeted blocker without closing the Batch 1 deficit.
- completed twenty-first repair:
  generic numeric/data artifact support was added for the remaining Batch 1
  deficit shape. The normal work path now has a read-only `analyze_table` tool
  for deterministic full-file numeric profiling of CSV/TSV/whitespace tables,
  including delimiter/header clues, column ranges, monotonicity, and local
  extrema for x/y pairs. Finish gating for fitting, optimization, ranking,
  scientific, and metric tasks now blocks schema-only, finite-number, and
  single-fit residual evidence unless the acceptance check cites an independent
  cross-check or alternative validation from a completed grounding tool.
- current route:
  the post-`8cec348` rerun of `raman-fitting` used `analyze_table` in the
  completed trials and changed finish behavior, but still scored 0/5 with one
  `AgentTimeoutError` in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-raman-fitting-5attempts-analyze-table-20260428-0926/result.json`.
  Classify the new blocker as
  `numeric_independent_validation_not_objective_grounded`: the loop now
  grounds in the source table and cites independent checks, but still
  validates the wrong objective/scale/model family. Stop `raman-fitting`-only
  repair cycles unless it becomes the selected M6.14 structural blocker with a
  generic objective-grounding repair plan.
- completed Batch 2 selection:
  Batch 2 covers unseen tasks `caffe-cifar-10`,
  `extract-moves-from-video`, `dna-assembly`, `dna-insert`,
  `financial-document-processor`, `build-pmars`, `git-leak-recovery`, and
  `large-scale-text-editing`, with frozen Codex target 27/40. The next chain
  is `M6.24 broad parity -> all 89 frozen registry tasks measured -> run Batch
  2 task-by-task through normal mew work --oneshot`.
- completed Batch 2 control:
  `git-leak-recovery` matched Codex target 5/5 with no Harbor errors in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-git-leak-recovery-5attempts-20260428-0953/result.json`.
  The first `build-pmars` run scored 3/5 against Codex target 5/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-build-pmars-5attempts-20260428-0959/result.json`.
  The blocker was harness permission, not core loop logic:
  `container_system_install_path_not_explicitly_allowed`. Adding the generic
  container-system write root `/usr/local/bin` improved `build-pmars` to 4/5,
  and adding package-source read root `/etc/apt` plus `/usr/local/bin` produced
  5/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-build-pmars-5attempts-system-perms-20260428-1015/result.json`.
  Future Batch 2 runs should use the explicit normal work path roots
  `--allow-read . --allow-read /etc/apt --allow-write . --allow-write /usr/local/bin`.
  `large-scale-text-editing` matched Codex target 5/5 with no Harbor errors in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-large-scale-text-editing-5attempts-20260428-1026/result.json`.
  `financial-document-processor` scored 0/5 against Codex target 4/5 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-financial-document-processor-5attempts-20260428-1044/result.json`.
  The first blocker was structural:
  `unsupported_document_observation_type_terminal_stop`, where read-only
  batches treated `read_image` on PDFs as terminal instead of recoverable.
  The generic repair records
  `recoverable_unsupported_observation_type` and continues while budget
  remains; focused and full `tests/test_work_session.py` validation passed, and
  Codex-ultra review session `019dd1d0-02ea-7ec3-acad-08c57ad59976` reported
  `STATUS: pass` after the stale-state regression test was added. The repair
  rerun remained 0/5 with 2 Harbor `RuntimeError` timeouts in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-financial-document-processor-5attempts-unsupported-image-recover-20260428-1058/result.json`,
  exposing the deeper generic blocker
  `document_pdf_observation_missing`; a future repair should add a generic
  PDF/document observation substrate, not a task-specific solver.
  Later generic repeat-guard, apt-root, and patch-shape repairs showed mixed
  evidence: a single-trial probe passed 1/1 in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-financial-document-processor-1attempt-repeat-guard-apt-20260428-1245/result.json`,
  but a post-issue #3/#14/#15 parallel 5-trial rerun had 0 completed reward
  trials and 5 `RuntimeError` command timeouts in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-financial-document-processor-5attempts-post-issue3-20260428-1328/result.json`.
  The sequential probe was stopped after one 900s timeout and one cancelled
  trial. The current blocker is timeout/partial-observability dominated, not a
  simple PDF absolute blocker. Do not spend more wall-clock on repeated
  `financial-document-processor` 5-trial reruns until a generic timeout /
  partial-report repair is selected or another document/artifact task confirms
  the same shape.
  `dna-assembly` then scored 0/2 completed reward trials with 3 Harbor errors
  in
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch2-dna-assembly-5attempts-20260428-1440/result.json`,
  against Codex target 3/5. The completed trials false-greened local primer
  verification but failed hidden checks on melting-temperature constraints; the
  dominant reusable class is
  `domain_ground_truth_verifier_surrogate_false_green`, with secondary
  `agent_command_timeout_after_domain_repair_loop`,
  `agent_setup_timeout_under_parallel_install`, and
  `shell_quoting_multiline_command`. Batch 2 measured latest total is 15/25
  against frozen Codex target 22/25 for measured tasks, with runner-error debt
  still requiring cleanup before M6.24 can close.
- latest source/test validation:
  `uv run pytest --no-testmon tests/test_data_tools.py tests/test_acceptance.py tests/test_work_session.py -q`
  passed with 743 tests and 30 subtests; `uv run ruff check` on changed files
  passed; `git diff --check` passed. Codex-ultra review session
  `019dd16d-eae2-7253-b1fe-6dffab2cdf63` reported `STATUS: pass` after three
  blocker rounds.

Drift guard:

- Do not create a Terminal-Bench-specific solver in mew core.
- Repairs must improve generic `work_session` / implementation-lane behavior
  for arbitrary workspace roots such as a benchmark task `/app`.
- Harbor glue may adapt input/output capture, but benchmark execution should
  call the normal work path with explicit cwd, read/write roots, verifier, and
  bounded permissions.
- Below-target M6.22 tasks must be classified through M6.18 before repair.

M7 pending evidence preserved:

- M6.18 close audit `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md` adds the
  required diagnosis route for future M7 dogfood failures:
  polish -> same-task retry, structural -> M6.14 repair, invalid spec -> task
  correction, transient -> retry, ambiguous -> replay/proof collection.

- Existing signal gates, journaling, and RSS/feed surfaces provide foundation,
  but the M7 close proof is not yet present.
- Next work should define the smallest enabled inbound source and proof window,
  then produce or simulate one auditable passive observation.
- Selector proposal `#26` chose task `#682` as the first M7 bounded task with
  lane dispatch, calibration refs, failure cluster, and preference refs. This
  proves the closed M6.17 lane chooser can hand off into M7 without falling
  back to stale paused M6 work.
- Task `#682` completed the first M7 bounded slice. Mew session `#672`
  selected the existing signal source registry as the smallest deterministic
  proof-source surface and added `select_signal_proof_source(state,
  current_time=...)` in `src/mew/signals.py`. The helper is read-only: it
  inspects configured RSS/Atom sources, returns candidate blockers, proof
  metadata, reason-for-use, URL, and remaining budget, and does not fetch,
  record, queue, or save state. Reviewer follow-up fixed zero-budget and
  stale day-window edge cases, preserving source state while refreshing the
  returned budget view. Validation passed: `uv run python -m unittest
  tests.test_signals`, `uv run ruff check src/mew/signals.py
  tests/test_signals.py`, and `git diff --check`. Codex-ultra review
  `019dcc07-6515-71d0-afe0-d280a002c6a9` returned `STATUS: pass`.
- Task `#683` added the first explicit gated non-file signal fetch surface as
  product-progress supervisor rescue after mew session `#673` drifted into
  help/proof-source-only edits. `mew signals fetch <source> [--json]` now uses
  existing `fetch_signal_source` gates and budgets, saves state only after a
  recorded observation, and reports blocked sources without queueing or saving.
  `mew signals proof-source [--json]` exposes the read-only selector from task
  `#682`. Reviewer correction moved budget checking before network access and
  added proof that exhausted budgets do not call the opener. Validation passed:
  `uv run python -m unittest tests.test_signals tests.test_signal_fetch
  tests.test_commands`, `uv run ruff check src/mew/signals.py src/mew/cli.py
  src/mew/commands.py tests/test_signals.py tests/test_signal_fetch.py`, and
  `git diff --check`. Codex-ultra review
  `019dcc19-8fa5-72c3-b88c-7030398e3cc1` initially failed the pre-network
  budget gate, then passed after the fix.
- Task `#684` added the first deterministic passive surface for queued inbound
  signal evidence. A `signal_observed` event now produces one unread
  reviewer-visible `send_message` that says mew noticed but did not act,
  includes source, summary, `reason_for_use`, and an explicit
  `./mew signals disable <source>` command, and does not mutate tasks or
  roadmap state. Mew session `#674` first drifted into reflex-observation
  metadata, then produced the core signal path after reviewer steer; supervisor
  cleanup removed residual wrong-target reflex changes. Count as mixed/product
  progress after steer, not clean autonomy credit. Validation passed:
  `uv run python -m unittest tests.test_commands tests.test_autonomy
  tests.test_signals tests.test_signal_fetch`, `uv run ruff check
  src/mew/agent.py tests/test_autonomy.py`, and `git diff --check`.
  Codex-ultra review `019dcc36-658f-72b0-8371-f24eae6a863e` returned
  `STATUS: pass`.
- Runtime proof `2026-04-27 09:00 JST`: enabled gated non-file RSS source
  `hn` with daily budget `1`, selected it through `mew signals proof-source`,
  fetched one HN RSS item through `mew signals fetch hn --json`, and processed
  the queued event with `mew run --once --echo-outbox`. The runtime produced
  outbox `#156`: `signal-observed noticed, not acted`, with source `hn`,
  fetched summary, `reason_for_use`, and disable command
  `./mew signals disable hn`. This proves the immediate end-to-end M7 path, but
  the real-day useful-observation gate remains open until the observation
  survives an intended passive proof window without spam.
- Task `#685` added the first M7 no-spam guard. `record_signal_observation`
  now suppresses duplicates in the current budget window before budget
  consumption and before queueing `signal_observed`: same source/kind/summary
  duplicates and same payload URL duplicates are blocked with
  `duplicate_suppressed`, with payload URL suppression working across sources.
  Mew session `#675` hit `task_goal_term_missing` once, then produced the core
  source/test patch after explicit reviewer steer. Supervisor fixed a
  codex-ultra finding that URL suppression was accidentally source-scoped.
  Validation passed: `uv run python -m unittest tests.test_signals
  tests.test_signal_fetch tests.test_commands`, `uv run ruff check
  src/mew/signals.py tests/test_signals.py`, and `git diff --check`.
  Codex-ultra review `019dcc4b-c380-77e3-acf5-26cd146e7935` failed initially;
  re-review `019dcc4f-1032-7f22-9a6f-d4610bd92e9a` returned `STATUS: pass`.

M6.17 close evidence:

- Task `#679` landed the first reviewer-visible lane-dispatch proposal slice as
  mixed mew-first plus supervisor review-fix evidence. Mew sessions `#668` and
  `#669` produced the initial `lane_dispatch` schema, human formatter exposure,
  and paired tests, but codex-ultra review
  `019dcbbe-33bb-7313-80bd-9ef159edd697` found two acceptance gaps:
  missing `repair_route` and missing `lane_dispatch` on no-candidate selector
  responses. The supervisor applied only those review fixes after the mew work
  session exhausted its failure budget, so this is product progress but not
  clean mew-first autonomy credit. Validation passed:
  `uv run python -m unittest tests.test_tasks tests.test_commands`,
  `uv run ruff check src/mew/tasks.py src/mew/commands.py tests/test_tasks.py tests/test_commands.py`,
  and `git diff --check`. Codex-ultra re-review
  `019dcbc5-974b-7fc3-955b-b2bc869c74c3` returned `STATUS: pass`.
- Task `#680` fixed a reentry drift path where `mew next --kind coding` could
  prefer a stale paused older milestone work session over the active M6.17
  roadmap gate. Mew session `#670` attempted the task first, but produced three
  failing or too-broad drafts, so the final patch is supervisor rescue with no
  mew autonomy credit. The fix parses `Active work: **M6.17 ...**.` from
  `ROADMAP_STATUS.md`, keeps current/non-milestone paused sessions paused, and
  routes older `M6.x` paused sessions to the active native self-improve focus.
  Validation passed: `uv run python -m unittest tests.test_brief`,
  `uv run ruff check src/mew/brief.py tests/test_brief.py`, and
  `git diff --check`. Codex-ultra review
  `019dcbd8-e9bb-7880-9009-7efb152bc3eb` returned `STATUS: pass` after the
  punctuation/current-milestone test gaps were fixed.
- Task `#681` added `next_action` to no-candidate selector proposals so a
  reviewer still sees the active native self-improve path when no safe bounded
  task candidate exists. Mew session `#671` authored the source/test patch and
  verification passed; the supervisor applied a tiny formatter follow-up so
  normal candidate proposals do not show `next_action: null`. After M7 became
  active, `./mew task propose-next 681 --json` returns a blocked no-candidate
  proposal with `lane_dispatch` plus `next_action: ./mew self-improve
  --start-session --focus 'Advance M7 Senses: Inbound Signals'`. Validation
  passed: `uv run python -m unittest
  tests.test_commands`, `uv run ruff check src/mew/commands.py
  tests/test_commands.py`, and `git diff --check`. Codex-ultra review
  `019dcbe9-aae6-75d1-a17d-fb613f1ef4c3` returned `STATUS: pass`.

M6.16 close evidence:

- Task `#656` produced the first M6.16 baseline slice as supervisor-owned
  rescue after failed mew-first attempts. Sessions `#642` and `#643` did not
  land product code: the first draft was label-only, the second helper-only
  draft missed the real metrics shape and CLI surface, the fresh retry hit
  `task_goal_term_missing`, and the final retry drifted into a wrong-target
  calibration parser patch. Count this as `product_progress_supervisor_rescue`
  with no autonomy credit, and as implementation-lane evidence for
  task-goal/substitution fragility after rejection feedback.
- The supervisor-owned baseline surface adds `mew metrics --implementation-lane`
  plus `src/mew/implementation_lane_baseline.py`. It combines
  `summarize_mew_first_calibration`, `build_observation_metrics(kind="coding")`,
  and `summarize_side_project_dogfood`. Current output reports
  `attempts_total=12`, `clean_or_practical_successes=3`,
  `rescue_partial_count=9`, `approval.rejected=13/18`,
  `verifier.failed=0/75`, `first_edit_latency.p95=890.0`, empty
  side-project dogfood rows, and failure classes including
  `task_goal_substitution` and `synthetic_schema_substitution`; after task
  `#659`, the current output reports `attempts_total=15`,
  `clean_or_practical_successes=3`, `rescue_partial_count=12`,
  `approval.rejected=17/22`, `verifier.failed=0/74`, and still recommends
  `mew_first_rescue_partial` as the first bottleneck. Validation passed:
  `uv run pytest -q tests/test_implementation_lane_baseline.py tests/test_mew_first_calibration.py tests/test_metrics.py tests/test_side_project_dogfood.py --no-testmon`,
  `uv run ruff check src/mew/implementation_lane_baseline.py src/mew/commands.py src/mew/cli.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
- Task `#657` landed the first M6.16 bottleneck-reduction slice against
  closeout correctness: `same_surface_audit.status=noted` should not keep a
  work session blocked at finish after the required sibling-surface audit has
  been recorded. This is a supervisor-owned substrate fix, not mew-first
  autonomy credit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'finish_block or same_surface_audit' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_commands.py -k 'finish or same_surface_audit or work_finish' --no-testmon`,
  `uv run ruff check src/mew/commands.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#658` attempted the side-project issue `#2` closeout-completeness
  prompt slice mew-first. Session `#644` produced two rejected paired dry-run
  attempts: the first edited the write-ready tiny draft prompt with
  side-project-specific wording, and the retry still substituted
  side-pj/internal-plumbing anti-schema wording instead of finish/closeout
  evidence. Count this as `product_progress_supervisor_rescue` with no
  autonomy credit. The supervisor-owned bounded patch adds normal
  `build_work_think_prompt` guidance requiring user-facing implementation
  tasks to account for acceptance criteria, README/usage docs, CLI
  stdout/output-file behavior, tests run, and unverified modes before finish.
  Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_commands.py -k 'work_think_prompt or finish or same_surface_audit or work_finish' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#659` is a supervisor-owned M6.16/M6.14 repair slice from the `#658`
  failure evidence. Rejection-frontier classification now preserves explicit
  `task_goal_substitution` before it can be downgraded to
  `missing_focused_verifier` or pairing recovery, and write-ready
  `task_goal.required_terms` filters evidence-source/scope labels such as
  `side-pj`, `side-project`, `implementation-lane`, `prompt-only`, and
  `test-only` while retaining real task anchors such as `user-facing` and
  `output-file`. This is loop-substrate/product progress, not mew-first
  autonomy credit. Focused proof:
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'rejection_frontier or write_ready or work_think_prompt' --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py tests/test_metrics.py -k 'task_goal or implementation_lane or metrics' --no-testmon`,
  `uv run ruff check src/mew/commands.py src/mew/work_loop.py tests/test_work_session.py tests/test_work_rejection_frontier.py`,
  and `git diff --check`.
- Task `#661` is a follow-on supervisor-owned M6.16/M6.14 repair from task
  `#660` / session `#645`: after switching `mew work` to
  `~/.codex/auth.json`, the model got past the expired `auth.pro.json` token
  but write-ready tiny draft blocked on `task_goal_term_missing` for
  `ROADMAP_STATUS`. The repair adds `roadmap_status` to the evidence-source
  required-term stopwords and extends the focused evidence-source test so
  document names do not become mandatory patch anchors. This is substrate
  progress only; retry `#660` mew-first after commit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k evidence_source_scope_terms --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#662` is the next same-family supervisor-owned M6.16/M6.14 repair:
  the retry after `#661` then blocked on verifier command flag `no-testmon`
  as a required task-goal term. The repair adds `no-testmon` to the
  evidence/command stopwords and extends the same focused test. Retry `#660`
  mew-first after commit. Focused proof:
  `uv run pytest -q tests/test_work_session.py -k evidence_source_scope_terms --no-testmon`,
  `uv run pytest -q tests/test_work_session.py tests/test_work_rejection_frontier.py -k 'evidence_source_scope_terms or task_goal_substitution or required_terms' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#660` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#661` and `#662` blocker fixes and
  switching live work to `~/.codex/auth.json`. It deduplicates
  `mew_first.gate_blocking_task_ids` in `mew metrics --implementation-lane`
  while preserving first-seen order, with paired coverage in
  `tests/test_implementation_lane_baseline.py`. Count this as
  `success_after_substrate_fix`: the fresh mew-first session drafted the
  paired source/test patch and the supervisor approved without product rescue
  edits; a reviewer steer was needed only to replace an invalid task verifier
  (`-k "gate_blocking"` selected no tests and exited 5). Valid proof passed:
  `uv run pytest -q tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run pytest -q tests/test_implementation_lane_baseline.py tests/test_metrics.py -k 'implementation_lane or gate_blocking or metrics' --no-testmon`,
  `uv run ruff check src/mew/implementation_lane_baseline.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --mew-first --limit 100 --json`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
  Codex-ultra re-review reported no findings after confirming `#660` is in
  the mew-first attempt window and counted as a practical success.
- The first `#663` retry exposed a new M6.16/M6.14 substrate blocker before
  product editing: after a same-path positive `search_text` on
  `src/mew/mew_first_calibration.py`, a later same-path zero-match
  `search_text` caused the broad-read guard to hard-fail a top-of-file
  `read_file` instead of reusing the positive search anchor. Task `#664`
  repairs that path: broad-read-after-search-miss now produces a narrow
  `read_file` replacement from the latest positive same-path search anchor
  when no cached read window exists. This is supervisor-owned loop-substrate
  progress, not mew-first autonomy credit; retry `#663` after commit.
  Focused proof:
  `uv run pytest -q tests/test_work_session.py -k 'broad_read_after_search_miss' --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings.
- Task `#663` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#664` blocker fix. It ignores narrative
  metric/status bullets that merely mention a task id, while preserving real
  attempt-entry prefixes such as `- Task #...`, `- follow-up #...`, and
  `- #639 mew-first note`. Count this as `success_after_substrate_fix`: the
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without product rescue edits after rejecting two
  wrong-target drafts. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py -k "narrative or attempt_window or substrate or success_after" --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_metrics.py -k 'narrative or attempt_window or substrate or success_after or mew_first or metrics' --no-testmon`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `./mew metrics --mew-first --limit 100 --json`,
  `./mew metrics --implementation-lane --json`, and `git diff --check`.
  The failed `uv run python -m unittest tests.test_mew_first_calibration`
  command was an invalid inferred verifier because this module contains pytest
  tests, not a product regression. Codex-ultra re-review reported no findings
  after adding explicit `follow-up #...` prefix coverage.
- Task `#665` is a supervisor-owned M6.16/M6.14 repair from the invalid
  inferred verifier observed during `#663`: `suggested_verify_command_for_call_path`
  now prefers `uv run pytest -q <test_path> --no-testmon` for pytest-style
  test files while preserving `uv run python -m unittest <module>` for
  `unittest.TestCase` modules. Count this as loop-substrate/product progress,
  not mew-first autonomy credit: mew hit repeated `task_goal_term_missing`
  before drafting the patch. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k "suggested_verify_command or pytest_style or paired_source_verifier" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "verify_command or verifier" --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings after adding
  explicit pytest import/class-style coverage.
- Task `#666` is a supervisor-owned M6.16/M6.14 repair from GitHub issue `#10`:
  stale pending dry-run approvals are now suppressed once a later completed,
  non-rolled-back same-path write is followed by a passing verifier. Rolled
  back failed writes do not suppress the original pending approval. Count this
  as loop-substrate/product progress, not mew-first autonomy credit: mew spent
  the attempt budget reading anchors and then timed out before drafting. Valid
  proof passed:
  `uv run pytest -q tests/test_work_session.py -k "superseded or pending_approval or finish_blocked or rolled_back" --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. Codex-ultra re-review reported no findings after the
  rolled-back-write regression was added.
- Task `#667` landed the GitHub issue `#3` same-file write-batch ergonomics
  slice as practical mew-first evidence. The work loop now collapses duplicate
  same-path `edit_file` actions into one `edit_file_hunks` action before
  enforcing the five-tool write-batch cap, while preserving rejection for
  unsafe `write_file` duplicates and `replace_all=True` edit semantics. Count
  this as practical mew-first without rescue edits: mew authored the source
  and test patch, Codex-ultra first found two correctness issues, and reviewer
  steer was needed for mew to repair both in the same session with no
  supervisor product-code rescue. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k "same_path_write_edits or edit_file_hunks or paired_write_batch" --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The broad `uv run python -m unittest tests.test_work_session`
  attempts are not counted as product regressions: inside the mew run they
  inherited `MEW_CODEX_REASONING_EFFORT=high` and failed existing reasoning
  expectation tests, and the manual env-cleared rerun hit an unrelated 0.21s
  timing flake. Codex-ultra re-review session
  `019dca8b-7797-7760-b628-100e80455aa5` reported no findings after the
  reviewer fixes.
- Task `#668` landed the GitHub issue `#9` behavior-verifier prompt slice as
  practical mew-first evidence. The work think prompt now tells tests and
  verifier commands to prefer behavior, contract, output, state, or
  docs-visible assertions over exact source text phrase assertions unless the
  task explicitly requires a literal public string or security-sensitive marker.
  Count this as practical mew-first without rescue edits: mew authored the
  paired source/test patch, codex-ultra review session
  `019dcab7-b73d-7bf2-b4a5-994e8c940a62` found the missing write-ready and
  tiny-draft prompt surfaces, and mew session `#651` repaired them without
  supervisor product-code rescue. The supervisor only corrected an invalid
  pytest `-k` verifier expression in the task invocation. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or behavior' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The invalid original verifier
  `work_think_prompt or source_literal or behavior verifier` was a task-spec
  operator error, not a product regression. Codex-ultra re-review reported no
  findings after the write-ready and tiny-draft repair.
- Task `#669` landed the GitHub issue `#5` scoped-verifier-repair slice as
  supervisor-owned M6.16/M6.14 repair evidence after a partial mew-first
  attempt. The normal, write-ready, and tiny-draft work prompts now tell the
  implementation lane to keep one compact in-session repair when a rollback
  verifier failure has one small clear localized cause and a clean worktree,
  centering that repair on the failed assertion/output and target path before
  switching to remember, checkpoint, or stop due pressure. Count this as
  loop-substrate/product progress, not mew-first autonomy credit: mew session
  `#652` authored the first normal-prompt patch, codex-ultra review session
  `019dcace-ebe2-7422-98d9-553dc259e1b2` found missing write-ready/tiny
  coverage, mew session `#653` added model-specific wording and then hit
  `old_text_not_found`, and the supervisor repaired the final generic
  three-surface prompt/test shape. Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'verifier_failure or failed_patch_repair or work_think_prompt or write_ready_tiny_draft or write_ready' --no-testmon`,
  `env -u MEW_CODEX_REASONING_EFFORT uv run python -m unittest tests.test_work_session.WorkSessionTests.test_work_ai_compact_live_forces_compact_prompt_context_on_high_risk_task tests.test_work_session.WorkSessionTests.test_work_session_steer_is_consumed_by_next_model_step`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`. The broader `uv run python -m unittest tests.test_work_session`
  failure inside the mew run inherited `MEW_CODEX_REASONING_EFFORT=high` and is
  not counted as a product regression. Codex-ultra re-review reported no
  findings after the generic three-surface repair.
- Task `#670` landed the GitHub issue `#4` rejected/rolled-back retry-context
  compaction slice as supervisor-owned M6.16/M6.14 repair evidence after a
  mew-first attempt failed to produce a patch. Session `#654` spent ten steps
  on targeted inspection and write-ready cached-window refresh, then reached
  `max_steps` without drafting. The supervisor-owned repair adds
  `resume.retry_context` for rejected and rolled-back writes, omits raw
  `old`/`new`/`content`/`edits` and `diff` bodies from resolved rejected or
  rolled-back write tool calls in model prompts, propagates the compact
  retry context into write-ready and deliberation focused contexts, and drops
  stale retry context after a newer changed write supersedes it. Count this as
  loop-substrate/product progress, not mew-first autonomy credit. Valid proof
  passed:
  `uv run pytest -q tests/test_work_session.py -k 'rejected or rolled_back or retry_context or patch_body or pending_approval or work_session_resume' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'write_ready or failed_patch_repair or rejection_frontier or retry_context' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcaf1-2534-7a12-8812-e6927b62d586` first found stale supersession and
  empty-diff-key issues, then re-review reported no findings after both
  regressions were covered.
- Task `#671` landed the GitHub issue `#11` side-dogfood append-validation
  slice as practical mew-first evidence. `mew side-dogfood validate --input
  ... [--json]` now validates one local side-project dogfood report against the
  canonical append schema without mutating the ledger, so side-project
  closeout can catch descriptive/non-appendable reports before finish. Count
  this as practical mew-first without rescue edits: session `#655` authored
  the source/CLI/test patch, codex-ultra review session
  `019dcb09-266b-7a22-8db7-9eead609e51b` found a missing-input `OSError`
  path, and mew session `#656` repaired it with a focused regression. Valid
  proof passed:
  `uv run pytest -q tests/test_side_project_dogfood.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run python -m unittest tests.test_commands tests.test_work_deliberation_cli`,
  `uv run ruff check src/mew/cli.py src/mew/commands.py tests/test_side_project_dogfood.py`,
  and `git diff --check`. Codex-ultra re-review reported no findings after
  the missing-input regression.
- Task `#672` landed the GitHub issue `#12` watch/continuous-mode verifier
  guidance slice as practical mew-first evidence. The normal, write-ready,
  and tiny-draft work prompts now tell the implementation lane that tasks
  involving watch, continuous, polling, listen, or other repeated modes must
  include bounded-loop or repeated-observation proof of external behavior, plus
  interval/interrupt handling or output-rewrite evidence where relevant, and
  must not accept internal mode flags alone. Count this as practical
  mew-first without rescue edits: session `#657` authored the paired
  source/test patch, hit one stale `old_text_not_found` draft, then repaired
  the same proposal after reviewer steer to retry exact anchors. Valid proof
  passed:
  `uv run pytest -q tests/test_work_session.py -k 'watch or continuous or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or write_ready or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcb20-3fec-7043-b508-a3ec5e8ceac4` reported no findings.
- Task `#673` landed the GitHub issue `#7` contract/docs-heading proof
  guidance slice as practical mew-first evidence. The normal, write-ready,
  and tiny-draft work prompts now tell the implementation lane that
  contract/docs-heavy slices must compare documented headings/surfaces against
  actual renderer or CLI output instead of treating file creation as proof.
  Count this as practical mew-first without rescue edits: session `#658`
  authored the paired source/test patch. The mew-run broad unittest verifier
  initially failed two unrelated reasoning-effort tests, but the same full
  module passed immediately when re-run outside the failed follow snapshot.
  Valid proof passed:
  `uv run pytest -q tests/test_work_session.py -k 'contract or heading or behavior or verifier' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or write_ready_tiny_draft or write_ready or contract or heading or behavior or verifier' --no-testmon`,
  `uv run python -m unittest tests.test_work_session`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check`. Codex-ultra review session
  `019dcb2f-dcd3-79e1-b069-4919e7e21c6d` reported no findings.
- Task `#674` landed the GitHub issue `#6` side-dogfood ledger-semantics
  slice as practical mew-first evidence. `mew side-dogfood report` now states
  that `rescue_edits` is a numeric Codex product-code rescue count and excludes
  operator steering, reviewer rejection, verifier follow-up, and generic
  repair. The implementation-lane baseline text labels the side-project
  aggregate as `codex_product_code_rescue_edits`, while JSON keeps the
  backward-compatible `rescue_edits_total` key and adds the same semantic alias.
  Count this as practical mew-first without supervisor product-code rescue:
  session `#659` authored the initial paired source/test patch and sibling
  digest label; codex-ultra review session
  `019dcb3e-a3f6-7423-ac91-981e1396c86c` found a non-integral float truncation
  bug and missing machine-readable alias; session `#660` repaired both. Valid
  proof passed:
  `uv run pytest -q tests/test_side_project_dogfood.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/side_project_dogfood.py src/mew/implementation_lane_baseline.py tests/test_side_project_dogfood.py tests/test_implementation_lane_baseline.py`,
  and `git diff --check`. Codex-ultra re-review reported no findings.
- Task `#675` landed an M6.16 measurement-quality slice as practical
  mew-first evidence. The mew-first calibration now treats reviewer-mediated
  mew-first repairs with no supervisor product-code rescue as
  `practical_mew_first`, while preserving clean credit for no-review
  `without rescue edits` entries. Sessions `#661`, `#662`, and `#663`
  authored the paired source/test patch and repaired two codex-ultra review
  findings plus the live `#671` wording gap. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `git diff --check`,
  `./mew metrics --mew-first --limit 100 --json`,
  and `./mew metrics --implementation-lane --json`. Metrics now classify
  tasks `#671` and `#674` as practical, keep clean/practical successes at
  `11`, and reduce the measured rescue/partial count from `29` to `28`.
  Codex-ultra review session `019dcb59-5c67-7e12-9169-500867c5e80c` ended with
  `NO FINDINGS`.
- Task `#676` landed an M6.16 measurement-window slice as practical
  mew-first evidence. `extract_mew_first_attempts(limit=N)` now sorts attempt
  records by descending task id before applying the limit, so recent cohort
  metrics select the newest task ids instead of the oldest tail of
  `ROADMAP_STATUS.md`; M6.16 headings are also recognized by the default
  attempt-section list for fixture/doc compatibility. Session `#664` authored
  the paired source/test patch. It hit one expected shell-permission stop while
  trying to run `./mew metrics` from inside the work session, but no
  supervisor product-code rescue was needed. Valid proof passed:
  `uv run pytest -q tests/test_mew_first_calibration.py --no-testmon`,
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/mew_first_calibration.py tests/test_mew_first_calibration.py`,
  `git diff --check`,
  `./mew metrics --mew-first --limit 10 --json`,
  and `./mew metrics --implementation-lane --limit 20 --json`. Current
  `--limit 10` now reports task window `#676 #675 #674 #673 #672 #671 #670
  #669 #668 #667` and passes the gate at `8/10`; `--limit 20` reduces the
  measured rescue/partial rate to `0.5`. Codex-ultra review session
  `019dcb76-a4a1-7803-b29c-d9a888edae14` reported `NO FINDINGS`.
- Task `#677` landed an M6.16 first-edit-latency instrumentation slice as
  practical mew-first evidence. Metrics diagnostics now expose
  `slow_first_edit_proposals` samples with session/task fields, first-edit
  seconds, first write tool id/tool/path, start time, and first model-turn
  summary; the implementation-lane baseline carries those samples under
  `first_edit_latency.samples` and prints them in the text report. Session
  `#665` authored the read-only telemetry/reporting patch, and session `#666`
  repaired the codex-ultra threshold finding so exactly-at-threshold `30.0s`
  samples are not treated as slow. Valid proof passed:
  `uv run pytest -q tests/test_metrics.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/metrics.py src/mew/implementation_lane_baseline.py tests/test_metrics.py tests/test_implementation_lane_baseline.py`,
  `git diff --check`,
  `./mew metrics --implementation-lane --limit 20 --json`,
  and `./mew metrics --implementation-lane --limit 20`. Current samples name
  concrete first-edit latency targets including sessions `#665`, `#652`, and
  `#649`. Codex-ultra review session
  `019dcb8a-8e66-71b3-b488-203fb4f5eb4f` ended with `NO FINDINGS`. No
  supervisor product-code rescue occurred.
- Task `#678` landed an M6.16 first-edit-latency reduction slice as clean
  mew-first evidence. The normal THINK prompt now treats first-edit latency as
  an operational budget: when scoped source/test cached windows already contain
  first-edit old text, mew should avoid another same-surface rediscovery turn
  and prefer the bounded paired edit path while preserving exact-old-text,
  pairing, scope, and verifier gates. Session `#667` authored the patch,
  produced a patch-draft replay on the write-ready surface, and passed both
  the focused prompt verifier and the full work-session unittest module:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or first_edit_latency' --no-testmon`
  and `uv run python -m unittest tests.test_work_session`. Additional local
  checks passed: `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`
  and `git diff --check`. Codex-ultra review session
  `019dcb9d-ddf7-7f30-8605-7b603f048ba8` reported `STATUS: pass` with
  `NO FINDINGS`; this was mew-first without rescue edits. After the `#677`
  and `#678` evidence-classification notes, `./mew metrics --mew-first --limit 10 --json`
  passes at `8/10`; `./mew metrics --implementation-lane --limit 20 --json`
  reports `clean_or_practical_successes=12/20`, `rescue_partial_rate=0.4`,
  `approval.rejection_rate=0.143`, `verifier.failure_rate=0.0`, and
  first-edit latency `median=285.5s`, `p95=536.55s`, `max=704.0s`.
- M6.13 close gate passed via
  `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`. The proof records
  reviewer-approved deliberation internalization, M6.9 ranked recall, normal
  tiny batch preview, normal approval apply, and a real unittest verifier with
  `close_evidence=true` and no close blockers.
- M6.13.2 decision memory saved at
  `.mew/memory/private/project/20260426T081045Z-decision-m6-13-2-side-project-dogfood-telemetry.md`.
  It records the side-project dogfood reporting flow: side-project task ->
  mew-first implementer -> Codex CLI/Codex reviewer/comparator/verifier ->
  tests/proof -> JSONL ledger append -> commit on success or M6.14 repair on
  structural failure. It also records the non-goals: no side-project
  implementation, EV routing, automatic Codex CLI integration, implementation
  lane refactor, or M6.13 close in this slice.
- M6.13.2 implementation landed a side-project dogfood ledger/report surface:
  `src/mew/side_project_dogfood.py`, `mew side-dogfood template`,
  `mew side-dogfood append`, and `mew side-dogfood report`. The default
  ledger path is `proof-artifacts/side_project_dogfood_ledger.jsonl`. This is
  ready for the first side-project dogfood task; side-project Codex CLI should
  normally be recorded as `operator` when it drives mew from the side-project
  directory. Direct Codex CLI implementation must be recorded via
  `codex_cli_used_as` as `implementer` or `fallback` and does not count as
  mew-first autonomy credit.

- Task `#647` / session `#634` landed the first additive WorkTodo lane field
  on `_normalize_active_work_todo`: missing or empty lane normalizes to
  `tiny`, while explicit strings such as `mirror` and unknown future lane names
  are preserved. Existing active-todo id/status/source/attempts/error behavior
  remains unchanged.
- Validation passed for the #647 source/test slice:
  `uv run pytest -q tests/test_work_session.py -k 'active_work_todo or lane' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py --no-testmon`,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`.
- The current mirror-lane replay slice keeps tiny on the legacy replay path
  while writing non-tiny lane bundles under
  `.mew/replays/work-loop/<date>/session-<id>/lane-<name>/todo-<id>/...`.
  Replay metadata now records additive lane reconstruction fields including
  `lane_decision`, `lane_authoritative`, `lane_layout`,
  `lane_write_capable`, and `lane_fallback_lane`.
- The write-ready shadow bridge now carries `active_work_todo.lane` into the
  patch-draft compiler replay environment, so a mirror-lane work todo can
  record a non-authoritative lane-scoped bundle while leaving the outer
  model-selected action unchanged. A replay-writer exception in the mirror
  path is captured as compiler observation data and does not replace or fail
  the outer action.
- The current deliberation preflight slice added `src/mew/deliberation.py` as
  pure M6.13 Phase 2 substrate: it normalizes requested/effective model
  bindings, classifies blocker-code escalation eligibility, reserves per-task
  attempt budget, builds cost/fallback events, appends deliberation attempts
  and cost events to session trace state, exposes those fields through
  `build_work_session_resume`, and validates the v1 `deliberation_result`
  contract before any raw model output can influence the tiny lane.
- The current work-loop call-boundary slice wires those deliberation primitives
  into `plan_work_model_turn` as a read-only lane attempt. Eligible blockers
  can make one explicitly bound high-effort call; validated results stop as
  reviewer-visible `result_ready` waits, while timeout, non-schema, validation,
  budget, or state-limit cases record fallback trace data and leave tiny
  available. `cmd_work_ai` now persists the returned session trace patch
  through `apply_work_session_trace_patch`.
- The current deliberation control slice adds explicit work-loop controls for
  the live proof: `--deliberate` requests a reviewer-commanded deliberation
  attempt, and `--no-auto-deliberation` disables automatic escalation for the
  run without blocking explicit reviewer commands. This makes the next proof
  commands observable instead of relying only on free-text guidance markers.
  Command-boundary tests now prove that `cmd_work_ai` persists reviewer
  commanded traces, automatic eligible traces, and no-auto fallback traces
  while still calling the tiny lane after the fallback.
- The current Phase 3 internalization slice extends approved
  `reasoning-trace` memory with additive lane provenance
  (`source_lane`, lane attempt id, blocker code, bundle ref, same-shape key,
  and reviewer decision ref). Existing M6.9 reasoning traces remain valid, but
  `source_lane=deliberation` now requires the provenance needed to reconstruct
  the internalization proof. Approved reasoning traces also append to
  `.mew/durable/memory/reasoning_trace.jsonl`, preserving the M6.9/M6.13
  durable ledger slot. A deterministic dogfood scenario records a hard
  deliberation-assisted task, writes the reviewed trace, proves a later
  same-shape task recalls it through provenance-aware active memory, and
  runs the tiny write-ready planning path with a deterministic fake model that
  receives the trace provenance in prompt context and emits a validated paired
  patch draft with `deliberation_invoked=false`. The same scenario now supports
  `--ai --auth <path>` live tiny-provider mode: it loads the configured model
  auth and replaces both the deliberation result call and the tiny draft call
  with a live provider. Validation passed with
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model gpt-5.5 --model-timeout 180 --json`,
  producing `evidence_class=live_provider_internalization_contract`,
  `deliberation_provider_mode=live_provider`, `tiny_provider_mode=live_provider`,
  and a validated paired patch draft. A later close slice replaced the
  previous not-close readiness state with normal work-path apply/verify proof.
- The M6.13 close slice records the full Phase 3 proof: active memory emits
  M6.9 ranked recall metadata with recency, importance, relevance,
  symbol-overlap, and task-shape components; the dogfood trace records
  `contract_cycle_proven=true`; deterministic and live `gpt-5.5` proofs pass;
  the later tiny task previews through `run_work_batch_action`, applies via
  `_apply_work_approval_batch`, and runs a real unittest verifier with
  `verification_test_count>=1`; and `close_evidence=true` has no close
  blockers. The close audit is
  `docs/M6_13_CLOSE_GATE_AUDIT_2026-04-26.md`.
- GitHub issue `#1` from side-project dogfood exposed a bounded M6.14 repair
  class: write-batch normalization/execution assumed every code batch must be
  a mew-core `src/mew/**` plus root `tests/**` pair, which blocked declared
  non-core product roots such as `experiments/mew-companion-log`. The repair
  keeps the strict mew-core paired-test rule for `src/mew/**` writes, but lets
  non-core write batches proceed when every write is inside
  `allowed_write_roots`; prompts now describe the same distinction. This is
  substrate repair from side-project evidence, not side-project implementation
  progress.
- Mirror-lane validation passed:
  `uv run pytest -q tests/test_work_replay.py -k "lane or path_shape" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "lane_metadata" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "m6_11_replay_lane_metadata_defaults_and_counts or m6_11_calibration" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "shadow_bridge_mirror_lane or shadow_bridge_records_validated_replay" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "patch_draft_compiler_shadow_bridge" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py tests/test_proof_summary.py --no-testmon`,
  and
  `uv run ruff check src/mew/work_loop.py src/mew/work_replay.py tests/test_work_session.py tests/test_work_replay.py tests/test_proof_summary.py`.
- Mew-first accounting: `product_progress_supervisor_rescue`, not autonomy
  credit. Mew reached the correct lane-normalization direction after reviewer
  steer, but stalled in partial-apply/rollback plus cached-window recovery
  before the final source repair. Treat another repeat as an M6.14 repair
  signal.
- Task `#648` / session `#635` landed the first data-only lane registry v0.
  `src/mew/work_lanes.py` now lists supported lanes `tiny`, `mirror`, and
  `deliberation`; `tiny` is authoritative/write-capable with legacy layout,
  `mirror` is non-authoritative lane-scoped mirror evidence, and
  `deliberation` is non-authoritative lane-scoped shadow evidence requiring
  explicit model binding. Missing or empty lane lookups fall back to `tiny`;
  unknown lane strings return an unsupported view while preserving the original
  WorkTodo lane value.
- #648 validation passed: work-session focused verifier
  `uv run pytest -q tests/test_work_lanes.py tests/test_work_session.py -k 'work_lane or active_work_todo_lane' --no-testmon`,
  `uv run python -m unittest tests.test_work_lanes`,
  `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py`, and
  `git diff --check`.
- #648 mew-first accounting: `success_mew_first_after_reviewer_rejection`.
  The reviewer rejected the first role-enum draft and steered the exact
  authoritative/mirror/shadow contract, but mew authored and verified the final
  source/test patch. No supervisor product rescue was used.
- Task `#649` / session `#636` landed the first data-only lane-attempt
  telemetry v0 helper. `build_lane_attempt_event()` emits the minimum
  `lane_attempt` event shape from the resident architecture design doc, maps
  the persisted `tiny` lane to display name `implementation`, keeps unknown
  lanes unsupported while preserving their string, and leaves routing,
  mirror execution, EV selection, and broad refactoring untouched. This was a
  mew-first implementation: after one transient model timeout and restarted
  live run, mew produced the paired source/test patch and the supervisor
  approved without rescue edits. Validation covered focused tests.
- #649 validation passed: work-session focused verifier
  `uv run pytest -q tests/test_work_lanes.py --no-testmon`,
  `uv run python -m unittest tests.test_work_lanes`,
  `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py`, and
  `git diff --check`.
- #649 same-surface audit found only `src/mew/work_lanes.py`,
  `tests/test_work_lanes.py`, and the architecture design doc referencing the
  new lane-attempt surface, so no production call sites need migration yet.
- Task `#650` / session `#637` exposed an M6.14 repair-class blocker before
  replay metadata could proceed: after `missing_required_terms`, mew produced
  rejected dry-run tools `#5890`/`#5891` that treated `required_terms` as
  product replay metadata and invented schema. Task `#651` records the bounded
  M6.14 repair episode for this `synthetic_schema_substitution` failure.
- Task `#651` landed the substrate repair: write-ready prompts now define
  `task_goal.required_terms` as semantic anchors, not fields or metadata keys
  to persist, and instruct the draft lane to return `task_goal_term_missing`
  rather than inventing schema when anchors cannot fit naturally. This is loop
  substrate surgery, not mew-first product autonomy credit. Retry target remains
  task `#650`.
- #651 validation passed:
  `uv run pytest -q tests/test_work_session.py -k "required_terms or tiny_write_ready_draft_prompt" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "write_ready" --no-testmon`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- While retrying `#650`, verifier baseline exposed one more M6.14 substrate
  repair: generic `fast-path` wording in the replay-harness task description
  was extracted as a required term and made the clean replay compiler fixture
  return `patch_blocker`. Task `#652` added `fast-path` to the generic
  required-term stopword set and covered this with a focused work-session test.
  This was direct Codex substrate repair, not mew-first autonomy credit.
- Task `#650` / session `#638` then completed the replay metadata slice
  mew-first after repair. Replay bundle metadata now derives lane provenance
  via `get_work_todo_lane_view()` and records `lane`, `lane_role`,
  `lane_schema_version=1`, and `lane_attempt_id`; missing/empty lanes resolve
  to `tiny` with authoritative role, while explicit lanes use registry roles.
  The reviewer steer was needed: the reviewer rejected the first lane-only
  draft, repaired the verifier substrate, then approved the mew-authored
  source/test patch without rescue edits. Validation covered focused tests.
- #650/#652 validation passed:
  `uv run pytest -q tests/test_work_replay.py --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "write_ready or required_terms" --no-testmon`,
  `uv run ruff check src/mew/work_replay.py src/mew/work_loop.py tests/test_work_replay.py tests/test_work_session.py`, and
  `git diff --check`.
- Task `#653` / session `#639` exposed another bounded M6.14 repair-class
  blocker while attempting the proof-summary read/report lane slice: after
  complete cached windows existed, the model requested a broad `read_file` on a
  path whose latest same-path `search_text` had zero matches, and the
  broad-read guard failed the step instead of coercing to the known cached
  line-window. Task `#654` repaired that loop substrate by attaching safe
  replacement parameters to the broad-read guard and executing the narrowed
  cached-window read when available. This is direct Codex substrate repair, not
  mew-first autonomy credit; retry target remains task `#653`.
- #654 validation passed:
  `uv run pytest -q tests/test_work_session.py -k "broad_read_after_search_miss_guard or write_ready" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "broad_read_after_search_miss_guard_reuses_latest_same_path_window or work_session_runs_read_only_tools_and_journals_results" --no-testmon`,
  `uv run ruff check src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`, and
  `git diff --check`.
- While retrying `#653`, required-term validation exposed one more bounded
  M6.14 repair: natural-language task wording used `proof-summary`, while the
  scoped Python source and tests naturally use `proof_summary`. Task `#655`
  repaired required-term validation to accept hyphen/underscore spelling
  variants without weakening genuinely missing anchors. This is direct Codex
  substrate repair, not mew-first autonomy credit; retry target remains
  task `#653`.
- #655 validation passed:
  `uv run pytest -q tests/test_patch_draft.py -k "required_term or task_goal_terms" --no-testmon`,
  `uv run pytest -q tests/test_patch_draft.py --no-testmon`,
  `uv run ruff check src/mew/patch_draft.py tests/test_patch_draft.py`, and
  `git diff --check`.
- Task `#653` / session `#641` then completed the proof-summary read/report
  lane slice mew-first after the bounded M6.14 fixes. Replay bundle summaries
  now expose lane metadata via `get_work_lane_view()`; legacy missing/empty
  lanes default to `tiny` with authoritative role; explicit `mirror` lanes
  report mirror metadata; and M6.11 replay calibration top-level/cohort
  summaries now include additive `lane_counts` without changing bundle type
  counts, thresholds, or classification. The reviewer steer was needed after
  the restart, but the final source/test patch landed without rescue edits:
  mew authored the source/test patch and Codex only hydrated
  cached windows, approved the dry-run patch, and verified it. Verification
  passed for the work-session pytest and ruff commands below.
- #653 validation passed:
  work-session verifier `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run ruff check src/mew/proof_summary.py tests/test_proof_summary.py`, and
  `git diff --check`.
- Resident architecture framing was recorded in
  `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`. Claude Ultra and
  Codex Ultra both reviewed the direction as `approve_with_changes`; the
  accepted constraints are that M6.13 keeps its current close gate, `tiny`
  remains the persisted canonical lane id, `implementation` is display
  terminology only, calibration economics starts as telemetry, EV routing is
  future work, and the meta loop is deferred.

Current M6.8.5 close evidence:

- Task `#639` / session `#627` landed the first read-only selector
  intelligence signal after bounded M6.14 substrate repair. Non-blocked
  `mew task propose-next` proposals now attach `failure_cluster_reason` from
  `summarize_calibration_ledger("proof-artifacts/m6_11_calibration_ledger.jsonl")`
  when the existing M6.12 calibration ledger has non-positive archetype counts.
  Missing-ledger and blocked proposal paths leave the existing field empty; the
  M6.8 approval/no-dispatch/governance contract is unchanged.
- #639 mew-first note: sessions `#625`/`#626` first failed with rejected
  synthetic-schema/hard-coded metadata patches. M6.14 repair task `#640`
  landed `synthetic_schema_substitution` rejection-frontier classification in
  commit `9c2c1d1`, then #627 retried #639 and produced the accepted source/test
  patch. Count this as `success_after_substrate_fix`; Codex reviewer correction
  was limited to rejecting bad drafts and steering the `CalibrationSummary.counts`
  API, not authoring the product patch.
- #639 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py
  tests/test_work_session.py`, and `git diff --check`.
- #639 dogfood evidence: `mew task propose-next 639 --candidate-task-id 641
  --record --json` produced `failure_cluster_reason:
  preflight_gap:9 from proof-artifacts/m6_11_calibration_ledger.jsonl` while
  keeping `approval_required=true`, `blocked=false`, and no auto-dispatch.
- Task `#641` / session `#629` added the second read-only selector
  intelligence signal. Non-blocked `mew task propose-next` proposals now attach
  bounded `preference_signal_refs` from existing selector reviewer history
  (`reviewer_decision` + `reviewer_reason`) so the next reviewer sees compact
  preference evidence without opening raw state.
- #641 mew-first note: session `#628` first drifted toward the previous
  `failure_cluster_reason` target, and #629 needed reviewer steering for a
  stale `src/mew/task_selector.py` path plus one rejected non-ASCII truncation
  draft. The final paired source/test patch was authored by mew and applied
  after reviewer approval; count this as `success_mew_first_with_reviewer_revisions`.
- #641 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- #641 dogfood evidence: `mew task propose-next 641 --candidate-task-id 642
  --record --json` produced both `failure_cluster_reason` and three
  `preference_signal_refs`; proposal `#18` was approved and executed to
  supervised handoff `#9` for task `#642`. A first candidate title containing a
  forbidden governance surface word was correctly blocked before retitling.
- Task `#642` / session `#630` added the third read-only selector intelligence
  signal. Non-blocked `mew task propose-next` proposals now attach bounded
  calibration/evaluator evidence rows as `memory_signal_refs` from the real
  `summarize_calibration_ledger("proof-artifacts/m6_11_calibration_ledger.jsonl")`
  output. Missing evidence leaves `memory_signal_refs` empty; blocked proposals
  still skip signal attachment.
- #642 mew-first note: #630 initially spent too many read turns and needed a
  reviewer steer to draft from cached anchors, but the final paired source/test
  patch was authored by mew and applied after approval. Count this as
  `success_mew_first_with_reviewer_steer`; no supervisor product edit.
- #642 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- #642 dogfood evidence: `mew task propose-next 642 --candidate-task-id 643
  --record --json` produced `memory_signal_refs`, `failure_cluster_reason`, and
  `preference_signal_refs`; proposal `#19` was approved and executed to
  supervised handoff `#10` for task `#643`.
- Task `#643` / session `#631` added the fourth read-only selector intelligence
  signal. Non-blocked `mew task propose-next` proposals now attach bounded
  `selector_habit_template` entries into existing `memory_signal_refs` from
  real `selector_proposals`, `selector_execution_attempts`, and tasks, for both
  non-record and `--record` output. Missing repeated evidence leaves
  `memory_signal_refs` empty; no new top-level proposal field was added.
- #643 mew-first note: #631 first drifted into a rejected
  `selector_governance_tags` synthetic schema, then produced a close but
  record-only habit patch. M6.14 repair task `#644` landed write-ready recovery
  cues in commit `161180b`, so explicit `read_file` / `first read` /
  `exact source text` recovery guidance triggered the needed exact read instead
  of another wait. The retried paired source/test patch was authored by mew and
  applied after reviewer approval. Count this as `success_after_substrate_fix`;
  no supervisor product patch.
- #643 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#645` / session `#632` implemented the M6.8.5 habit compilation v0
  proof slice. Selector habit evidence now emits a reviewer-visible
  `compiled_habit_runner_candidate` entry in existing `memory_signal_refs` only
  when a repeated task template has approved handoff evidence and the historical
  `next_command` matches the deterministic runner command shape for that source
  task. Command mismatches fall back to the normal selector proposal with no
  compiled candidate ref; approval-required/no-dispatch behavior is unchanged.
- #645 mew-first note: #632 was mew-authored and needed no supervisor product
  rescue. The reviewer approved one paired source/test dry-run patch and then
  asked mew to finish after verification. Count this as `success_mew_first`.
- #645 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#646` / session `#633` closed the preference draft-preparation proof
  slice. Work-session resume and THINK prompt context now surface bounded
  `preference_signal_refs` from the approved selector proposal that selected the
  current task, with `approved_selector_proposal` provenance and selector
  proposal/task ids. Missing preference refs, unapproved selector records, or
  wrong-task records produce an empty field; `memory_signal_refs` are not used
  as a fallback.
- #646 mew-first note: #633 first produced a close source/test dry-run that
  incorrectly fell back to `memory_signal_refs`. The reviewer rejected it, and
  mew retried with a paired source/test patch that removed the fallback and
  added a THINK-prompt assertion. Count this as
  `success_mew_first_with_reviewer_revision`; no supervisor product patch.
- #646 validation passed: focused
  `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt' --no-testmon`,
  exact-timeout rerun
  `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt or hard_timeout_without_retries' --no-testmon`,
  full `uv run pytest -q tests/test_work_session.py --no-testmon` on rerun,
  `uv run ruff check src/mew/work_session.py tests/test_work_session.py`, and
  `git diff --check`. The first full work-session run had one transient
  hard-timeout assertion failure; the exact failing test and full suite passed
  immediately on rerun.

Closed M6.8 evidence:

- Task `#628` / session `#612` landed the first mew-first selector-contract
  slice: `build_task_selector_proposal()` in `src/mew/tasks.py` produces a
  reviewer-gated proposal with `previous_task_id`, proposed task identity,
  `selector_reason`, `approval_required=true`, optional M6.8.5 signal refs, and
  governance/status blocking fields.
- The first #628 patch was correctly rejected as a shallow
  `task_kind_report` passthrough. After reviewer steering, mew retried the same
  task and produced the accepted helper/test patch without supervisor product
  rescue.
- Validation passed: `uv run pytest -q tests/test_tasks.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/tasks.py tests/test_tasks.py`, and
  `git diff --check`.
- Task `#629` / session `#614` exposed the proposal helper as the read-only
  `mew task propose-next` CLI. It supports JSON and human output, keeps
  `approval_required=true`, reports governance-blocked candidates, and does not
  dispatch or mutate agent runs.
- #629 mew-first note: the first implementation verifier failed on a test
  expectation case mismatch (`roadmap` vs `ROADMAP_STATUS.md`). Reviewer steered
  mew to preserve product behavior and repair the test; mew re-applied the CLI
  parser and the paired test repair with no supervisor product edit.
- #629 validation passed: `uv run pytest -q tests/test_commands.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/commands.py src/mew/cli.py tests/test_commands.py`,
  and `git diff --check`.
- Task `#630` / session `#615` repaired a selector scope-fence
  false-positive found by dogfooding: M6.8 implementation tasks that merely
  describe governance/status guardrails were being blocked as if they targeted
  those surfaces. Selector target checks now inspect task title and explicit
  `scope.target_paths`, not description/notes. Explicit forbidden titles and
  target paths still block.
- #630 validation passed: `uv run pytest -q tests/test_tasks.py --no-testmon`,
  `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`,
  `uv run ruff check src/mew/tasks.py tests/test_tasks.py`, and
  `git diff --check`.
- Starting task `#631` exposed a loop-substrate false negative rather than a
  product-code failure: sessions `#616`/`#617` repeatedly stopped with
  `cached_window_incomplete` because write-ready structural preflight could not
  narrow a complete indented `build_parser()` parser-registration fragment in
  `src/mew/cli.py`. This was repaired as M6.14 substrate work, not counted as
  #631 autonomy credit. The structural gate now accepts complete indented
  simple-statement sequences such as argparse registration blocks while still
  rejecting one-line orphaned body fragments; the observed `cli.py:1707-1995`
  window narrows to `1707-1960`.
- #631 substrate repair validation passed: `uv run pytest -q
  tests/test_work_session.py -k 'write_ready' --no-testmon`, `uv run pytest -q
  tests/test_work_session.py tests/test_commands.py --no-testmon`, `uv run
  ruff check src/mew/work_loop.py tests/test_work_session.py`, and `git diff
  --check`.
- Task `#631` / session `#617` then landed the durable selector-proposal
  ledger slice mew-first after one reviewer rejection. `mew task propose-next
  --record` now persists `selector_proposals` records without dispatching:
  `id`, `previous_task_id`, `proposed_task_id`, original `proposal`, `status`
  (`proposed` or `blocked`), `created_at`, and `updated_at`. The slice
  intentionally does not add approve/reject commands or chained execution.
- #631 mew-first note: the first proposed patch only added a cosmetic
  `selector-proposal` output label and was rejected. After reviewer steer and
  one model-timeout retry, mew produced the accepted source/CLI/test batch; no
  supervisor product edit was used.
- #631 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_commands.py tests/test_tasks.py
  tests/test_work_session.py -k 'task_propose_next or write_ready'
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py src/mew/work_loop.py tests/test_work_session.py`, and
  `git diff --check`.
- Dogfooding `mew task propose-next 631 --record --json` immediately after
  #631 recorded a blocked proposal for stale governance task `#388`, proving
  the scope fence but also exposing that automatic selection could get stuck on
  the first blocked ready candidate.
- Task `#632` / session `#618` repaired that selector behavior mew-first.
  Automatic `task propose-next` now scans ready/todo coding tasks, builds each
  proposal, skips governance-blocked proposals, and returns the first unblocked
  candidate; explicit `--candidate-task-id` still returns and records blocked
  proposals for reviewer visibility.
- #632 mew-first note: the first patch only added comments/assertions around
  existing explicit-candidate behavior and was rejected. After reviewer steer,
  mew produced the accepted source/test patch with no supervisor product edit.
- #632 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_commands.py
  tests/test_work_session.py -k 'task_propose_next or write_ready'
  --no-testmon`, `uv run ruff check src/mew/commands.py
  tests/test_commands.py`, and `git diff --check`.
- Post-#632 dogfood `mew task propose-next 632 --record --json` skipped stale
  governance task `#388` and returned `no safe selector candidate found`
  instead of proposing the blocked task.
- Task `#633` / session `#619` landed reviewer-visible selector approval and
  rejection recording mew-first. `mew task approve-proposal <id>` and `mew task
  reject-proposal <id>` update existing `selector_proposals` records with
  `reviewer_decision`, `reviewer_reason`, `reviewed_at`, `updated_at`, and a
  terminal `status` without dispatching the proposed task or mutating tasks.
- #633 mew-first note: two proposed patches were rejected before approval. The
  first bypassed the CLI by calling command helpers directly from tests. The
  second added CLI wiring but allowed approving blocked governance proposals,
  which would weaken the M6.8 scope fence. After reviewer steer, mew produced
  the accepted CLI/source/test patch with no supervisor product edit.
- #633 scope-fence dogfood: `mew task approve-proposal 4 --reason ... --json`
  recorded reviewer approval for the safe `#632 -> #633` proposal, `mew task
  approve-proposal 1 --reason ... --json` rejected approval of the blocked
  governance proposal, and `mew task reject-proposal 1 --reason ... --json`
  recorded the reviewer rejection for the blocked candidate.
- #633 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#634` / session `#620` landed the first guarded execution attempt
  slice mew-first. `mew task execute-proposal <id>` now rejects missing,
  unapproved, and blocked selector proposals, persists
  `selector_execution_attempts` audit records with `proposal_id`,
  `proposed_task_id`, `status=rejected`, `blocked_reason`,
  `governance_violation=true`, and `timestamp`, and does not mutate tasks or
  dispatch agent runs.
- #634 dogfood: `mew task execute-proposal 5 --json` rejected/logged blocked
  proposal execution, `mew task propose-next 634 --candidate-task-id 635
  --record --json` created proposal `#7`, `mew task execute-proposal 7 --json`
  rejected/logged the unapproved execution attempt, and after reviewer approval
  `mew task execute-proposal 7 --json` returned the safe v0 message that
  approved execution handoff is not implemented and no task was dispatched.
- #634 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#635` / session `#621` landed the approved selector handoff slice
  mew-first. Approved `mew task execute-proposal <id>` now persists a
  `selector_execution_attempts` record with `status=handoff_ready`,
  `proposal_id`, `proposed_task_id`, reviewer approval metadata,
  `next_command`, and `auto_run=false`; it prints the reviewer-visible
  `./mew work <task-id> --start-session` handoff command and still does not
  dispatch model work or mutate tasks.
- #635 mew-first note: one patch was rejected for omitting the required
  `next_command` handoff evidence, and a later edit attempt hit the known
  duplicated-adjacent-context guard. After reviewer steer, mew produced the
  accepted source/test pair with no supervisor product edit.
- #635 dogfood: `mew task execute-proposal 7 --json` recorded
  `status=handoff_ready`, `proposed_task_id=635`, the original reviewer
  approval metadata, `next_command="./mew work 635 --start-session"`, and
  `auto_run=false`.
- #635 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#636` / session `#622` continued the approved handoff chain from
  proposal `#9`. The reviewer approved `#635 -> #636`, `execute-proposal`
  recorded `handoff_ready`, and mew implemented the read-only
  `mew task selector-status` CLI as the next bounded task.
- #636 adds a selector proof status summary for close-gate review without
  dispatching work or mutating state: counts for `selector_proposals`,
  `selector_execution_attempts`, `approved_handoffs`, `rejected_attempts`, and
  `blocked_proposals`, plus the latest proposal and execution attempt.
- #636 dogfood: `mew task selector-status --json` reported the live M6.8 chain
  state, including `approved_handoffs=2`, `rejected_attempts=2`, and latest
  handoff attempt `#4` for proposal `#9 -> task #636`.
- #636 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#637` / session `#623` continued the auto-selected handoff chain from
  proposal `#11`. The reviewer approved `#636 -> #637`, `execute-proposal`
  recorded `handoff_ready`, and mew extended `mew task selector-status` with a
  joined `recent_handoffs` list for close-gate auditing.
- #637 exposes each recent approved handoff with `proposal_id`,
  `previous_task_id`, `proposed_task_id`, `selector_reason`, reviewer metadata,
  `next_command`, and timestamp. This keeps proof evidence read-only and avoids
  M6.8.5 selector intelligence or dispatch behavior.
- #637 dogfood: `mew task selector-status --json` reported
  `approved_handoffs=3`, `rejected_attempts=2`, and recent handoffs for
  proposal `#11` (`#636 -> #637`), proposal `#9` (`#635 -> #636`), and
  proposal `#7` (`#634 -> #635`).
- #637 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.
- Task `#638` / session `#624` added the close-gate proof summary after the
  reviewer-approved `#637 -> #638` auto-selected handoff. `mew task
  selector-status --json` now derives `proof_summary` from `recent_handoffs`:
  total recent handoffs, contiguous chain length, latest task id, oldest task
  id, and `has_three_consecutive_handoffs`.
- #638 dogfood: live `selector-status --json` reported
  `approved_handoffs=4`, `rejected_attempts=2`, `blocked_proposals=6`,
  `proof_summary.contiguous_chain_length=4`, and
  `has_three_consecutive_handoffs=true`. The latest three auto-selected links
  are `#635 -> #636`, `#636 -> #637`, and `#637 -> #638`.
- #638 validation passed: `uv run pytest -q tests/test_commands.py
  --no-testmon`, `uv run pytest -q tests/test_tasks.py tests/test_commands.py
  --no-testmon`, `uv run ruff check src/mew/commands.py src/mew/cli.py
  tests/test_commands.py`, and `git diff --check`.

M6.8 is done when:

- mew completes three consecutive bounded iterations in one supervised session
  where mew chose each next task, reviewer approval was recorded per iteration,
  and rescue edits stayed at zero
- at least one reviewer rejection happens during the chained proof run, and the
  next approved task continues the chain without manual reset
- selector scope fence holds across the proof run
- drift canary stays green across the full chained run
- attempting chained execution without reviewer approval is rejected and logged
  as a governance violation

M6.8 close result: **done**. The recorded audit is
`docs/M6_8_CLOSE_GATE_AUDIT_2026-04-26.md`.

M6.8.5 close result: **done**. The recorded audit is
`docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`.

## Next Milestone

Current scheduled milestone: **M6.22 Terminal-Bench Curated Subset Parity**.

M6.20 starts after M6.19 proves that Harbor / Terminal-Bench can execute mew
and at least one reference agent on the same smoke subset. M6.20 should not
begin from model opinion alone; it needs benchmark artifacts from M6.19.

First M6.20 slice:

- baseline report completed:
  `docs/M6_20_TERMINAL_BENCH_BASELINE_2026-04-27.md`
- instruction-consuming `mew-smoke` entrypoint and host-side report capture are
  implemented and validated; the previous `make-mips-interpreter` candidate is
  retained as stretch evidence, not the close gate
- next: run real implementation-lane attempts on the two active M6.20 gate
  tasks, `terminal-bench/fix-code-vulnerability` and
  `terminal-bench/cancel-async-tasks`
- classify any failed mew task through M6.18
- route only cited structural failures into M6.14 repair episodes
- rerun the same subset and record whether the repair improved, regressed, or
  did not affect the score
- closed on 2026-04-27 JST by
  `docs/M6_20_MEW_TERMINAL_GATE_RUNS_2026-04-27.md`: both fixed gate tasks
  reached 5/5 successes with Harbor errors 0 on current head

Planned future milestones:

- **M6.21 Terminal-Bench Codex Target Registry**: done. The frozen target data
  is `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`.
- **M6.22 Terminal-Bench Curated Subset Parity**: active. The curated subset
  manifest is now selected in `docs/M6_22_CURATED_SUBSET_MANIFEST_2026-04-27.md`
  and `docs/data/terminal_bench_m6_22_curated_subset.json`: 7 tasks, 35 trials,
  Codex target 20 successes. Next: run the five not-yet-run selected tasks
  through the same generic `mew work --oneshot` Harbor command shape, then
  combine them with the M6.20 positive-control artifacts.
- **M6.23 Terminal-Bench Failure-Class Coverage**: classify below-target
  benchmark failures into repair classes and rerun at least one ranked repair.
- **M6.24 Broad Terminal-Bench Parity Campaign**: run measurement /
  improvement loops over the 89 registry tasks and close the gap to Codex's
  366/445 successes, 82.2% aggregate target.
- **M6.25 Codex-Plus Resident Advantage**: preserve Terminal-Bench parity while
  proving mew's persistence, memory, and repair loops make it preferable to
  inhabit over a reactive terminal-agent CLI.
- **M7 Senses: Inbound Signals**: resume after M6.19/M6.20 give the
  implementation lane an external benchmark and failure-debug loop.
- **M8 Identity: Cross-Project Self**: user-scope identity and cross-project
  memory remain future work after M7.

## Post-Close Deferred Ledger

| Origin | Deferred Item | Trigger / Timing | Recommended Home | Blocks Current? |
|---|---|---|---|---|
| M6.9 Phase 4 | Failure-clustered curriculum | Closed by M6.8.5 task `#639` | M6.8.5 done | No |
| M6.9 Phase 4 | Preference-store retrieval from reviewer diffs | Closed by M6.8.5 tasks `#641` and `#646` | M6.8.5 done | No |
| M6.9 Phase 4 | Habit compilation v0 | Closed by M6.8.5 tasks `#643` and `#645` | M6.8.5 done | No |
| M6.10 | Explorer D1 / read-only exploration reducer | Only if M6.8 or M6.8.5 evidence shows read-only exploration churn is a measured blocker again | M6.10 follow-up or M6.8.5 helper slice | No |
| M6.11 | Full concurrent / streaming executor | After selector/curriculum proof shows measured idle or concurrency pain while loop attribution is stable | Later execution milestone | No |
| M6.11 | MemoryExplore protocol full freeze/replay and agentization | Keep read-only provider for now; full agentization waits until a second planner will not obscure loop failures | M10 or later memory/explorer milestone | No |
| M6.11 | Provider-specific prompt caching | Only when provider telemetry shows cache/latency as a direct blocker | M6.13 or later acceleration slice | No |
| M6.12 | Governance/evaluator/adversarial wiring | First use M6.12 as read-only selector input in M6.8.5; automatic governance wiring needs a later explicit safety milestone | M6.8.5 read-only, later governance milestone | No |
| Resident architecture | Codex-grade implementation lane hardening | After M6.13 emits enough lane-attempt telemetry to identify implementation-lane bottlenecks | M6.16 | No |
| Resident architecture | Resident meta loop / lane chooser | After M6.13 lane boundaries and M6.16 implementation-lane reliability are proven | M6.17 | No |
| Refactor policy | Broad work-loop/work-session refactoring | Defer until M6.16 unless the same reproducible failure class blocks M6.13 mew-first work twice and fits M6.14 repair | M6.16 or M6.14 repair | No |

## Mew-First Operating Rule

From M6.9 onward, bounded roadmap/coding implementation belongs to mew first.
Codex acts as reviewer/supervisor.

Allowed direct Codex work:

- roadmap/status/audit bookkeeping
- governance, permission, safety, and skill-policy changes
- loop-substrate repairs after a classified mew-first failure

Not allowed as autonomy credit:

- supervisor-authored product rescue disguised as mew-owned implementation
- milestone-close or roadmap-status changes authored by selector output
- unattended auto-merge

If a mew-owned task fails structurally:

1. classify the failure
2. pause the active product milestone
3. append or activate a bounded M6.14 repair episode
4. fix the substrate or task spec
5. retry the same task

## Closed Baseline Caveats

These caveats are preserved; they do not reopen the milestones by default.

- M6 daemon: original retained-artifact report had a false-negative shape, but
  strict summary proof passed and the caveat is archived.
- M6.6: comparator proof contains environment/caveat notes, but the gate is
  closed.
- M6.9: some wall-time and comparator evidence is deterministic fixture
  evidence rather than fresh external CLI reruns; the close audit records this.
- M6.10: Explorer D1 is deferred because the reliability gate passed without
  it.
- M6.11: residual hardening includes mixed autonomy outcomes; acceptable
  because the residual gate was loop-substrate hardening.
- M6.12: closeout export tree and governance wiring are deferred by design.

## Reopen Rules

- Reopen M6.6 only if a future native coding loop regresses on rescue edits,
  first-edit efficiency, or comparator parity.
- Reopen M6.8 only if chained task selection violates approval, scope fence, or
  drift-canary discipline after close.
- Reopen M6.9 only if M6.8/M6.8.5 selector proof exposes a real
  durable-memory regression against `docs/M6_9_CLOSE_GATE_AUDIT_2026-04-26.md`.
- Reopen M6.11 only if a fresh loop regression cannot be classified or repaired
  using the closed residual surfaces.
- Reopen M6.12 only if the read-only report stops parsing the canonical ledger
  or gives incorrect missing-bundle/citation results.
- Reopen M6.16 only if a fresh bounded implementation-lane cohort regresses
  below the recorded close gate, or if first-edit latency remains high on
  current-head samples after M6.17 has used it as lane-choice evidence.
- Reopen M6.18 only if mew-first failure diagnosis stops emitting routeable
  failure scopes or sends structural repairs to M6.14 without cited signals.
- M6.14 remains the default home for future mew-first substrate repair
  episodes.

## Current Roadmap Focus

The next implementation task should map to this chain:

`M6.20 closed -> M6.21 registry done -> M6.22 curated subset parity`

Acceptable near-term work:

- define the M6.22 curated subset directly from
  `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`
  (done in `docs/data/terminal_bench_m6_22_curated_subset.json`)
- keep `mew work --oneshot` as the implementation path and preserve the
  no-Terminal-Bench-specific-solver constraint
- run `filter-js-from-html`, `sanitize-git-repo`, `gcode-to-text`,
  `overfull-hbox`, and `extract-elf`; reuse the M6.20 current-head artifacts
  for `cancel-async-tasks` and `fix-code-vulnerability` as positive controls
- classify below-target tasks through M6.18, then choose the next generic
  implementation-lane repair from cited benchmark evidence

Non-goals for the next session:

- adding a Terminal-Bench-specific solver path or benchmark-only core command
- treating Terminal-Bench as a separate architecture instead of a measurement
  harness for generic `mew work`
- broad prompt tuning before instruction ingestion and failure classification
  are proven
- resuming M7 inbound signal work before M6.22 is addressed or explicitly
  reprioritized
- full concurrent executor
- memory explore agentization
- provider-specific prompt caching
- broad work-loop or work-session refactors without a recorded structural
  signal
- treating diagnosis output as automatic permission to perform structural
  repair without reviewer-visible evidence

## Latest Validation

Latest roadmap/status validation:

- M6.20 fixed terminal gate is closed. Current-head mew runs matched the
  frozen Codex target on both fixed tasks with Harbor errors 0:
  `terminal-bench/cancel-async-tasks` 5/5
  (`proof-artifacts/terminal-bench/harbor-smoke/mew-work-oneshot-cancel-async-tasks-5attempts-boundary-verifier-20260427-2201/result.json`)
  and `terminal-bench/fix-code-vulnerability` 5/5
  (`proof-artifacts/terminal-bench/harbor-smoke/mew-work-oneshot-fix-code-vulnerability-5attempts-current-head-20260427-2207/result.json`).
  Evidence and failure classification:
  `docs/M6_20_MEW_TERMINAL_GATE_RUNS_2026-04-27.md`.
- M6.22 curated subset manifest exists:
  `docs/M6_22_CURATED_SUBSET_MANIFEST_2026-04-27.md` and
  `docs/data/terminal_bench_m6_22_curated_subset.json`. Selected tasks:
  `filter-js-from-html`, `sanitize-git-repo`, `gcode-to-text`,
  `overfull-hbox`, `extract-elf`, `cancel-async-tasks`, and
  `fix-code-vulnerability`. Aggregate Codex target: 20/35 successes.
- First M6.22 runs are recorded in
  `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`:
  `filter-js-from-html` scored 0/5 with 5 `VerifierTimeoutError` exceptions
  in 32m 24s
  (`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json`).
  `sanitize-git-repo` scored 1/5 with Harbor errors 0 in 4m 41s
  (`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-sanitize-git-repo-5attempts-20260427-2245/result.json`).
  `gcode-to-text` scored 0/5 with 1 `AgentTimeoutError` in 15m 41s
  (`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-gcode-to-text-5attempts-20260427-2252/result.json`).
  The combined counted result is 1/15, below the frozen Codex 3/15 target for
  those three tasks. `gcode-to-text` is classified through M6.18 as structural
  visual/geometric artifact-grounding failure; repair selection waits for the
  remaining M6.22 tasks so the repair can target a cohort.
- M6.21 target registry is complete. The source leaderboard is
  `https://www.tbench.ai/leaderboard/terminal-bench/2.0/codex/0.121.0/gpt-5.5%40openai`.
  Local JSON:
  `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`.
  Extracted aggregate: 89 tasks, 445 trials, 366 successes, 82.2% overall
  resolution rate. M6.20 fixed-task gate targets:
  `fix-code-vulnerability`, checksum
  `13c4e35adbd7e55707f273aabd8f4108672f0fb790c96af543fbcbdcc977b119`,
  5 trials, 5 successes, 100.0%; and `cancel-async-tasks`, checksum
  `283c70ca90688dc09a969d24e3ed137ba0f00d23018df68771bdf86526b82047`,
  5 trials, 5 successes, 100.0%.
- M6.20 task `#694` repaired Harbor report capture after task `#693` proved
  instruction ingestion but exposed missing host-side report metadata. Direct
  supervisor implementation was used by user decision because this is
  Terminal-Bench harness substrate, not the mew-first autonomy proof target.
  New report:
  `docs/M6_20_INSTRUCTION_RERUN_2026-04-27.md`. Validation passed:
  `uv run pytest -q tests/test_terminal_bench_smoke.py tests/test_harbor_terminal_bench_agent.py --no-testmon`
  (`9 passed`),
  `uv run ruff check src/mew/terminal_bench_smoke.py tests/test_terminal_bench_smoke.py .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py`,
  `uv run mew-smoke --instruction 'diagnostic instruction' --report /tmp/mew-smoke-report.json --artifacts /tmp/mew-smoke-artifacts`,
  `git diff --check`, and a bounded Harbor rerun:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-stdout-report-fallback/result.json`.
  The rerun has `n_errors=0`, mean score `0.0`, and host-side
  `mew-report.json` / `summary.json` with recovered report fields. The score
  remains expectedly zero because `mew-smoke` is capture-only; next M6.20 value
  is a real implementation-lane attempt or task-spec repair, not more smoke
  wrapper plumbing.
- M6.20 task `#693` ran the first instruction-consuming Harbor rerun:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-instruction-entrypoint/result.json`.
  It had one trial, no Harbor exceptions, mean score `0.0`, and a command
  transcript proving the full `make-mips-interpreter` instruction reached
  `mew-smoke`. It also exposed that `mew-report.json` was not visible to the
  host artifact directory, which task `#694` repaired.
- M6.20 task `#692` added the installed `mew-smoke` entrypoint for
  instruction-consuming Terminal-Bench smoke runs. It accepts `--instruction`,
  `--report`, and `--artifacts`, records instruction/report JSON, registers the
  console script in `pyproject.toml`, and updates
  `docs/terminal-bench-harbor-smoke.md`. Focused validation passed:
  `uv run pytest -q tests/test_terminal_bench_smoke.py tests/test_harbor_terminal_bench_agent.py --no-testmon`,
  `uv run ruff check src/mew/terminal_bench_smoke.py tests/test_terminal_bench_smoke.py .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py`,
  `uv run mew-smoke --instruction 'diagnostic instruction' --report /tmp/mew-smoke-report.json --artifacts /tmp/mew-smoke-artifacts`,
  and `git diff --check`.
- M6.20 task `#691` created
  `docs/M6_20_TERMINAL_BENCH_BASELINE_2026-04-27.md` from the M6.19 mew and
  Codex Harbor smoke artifacts. Verifier passed:
  `test -f docs/M6_20_TERMINAL_BENCH_BASELINE_2026-04-27.md`, and manual
  `git diff --check` passed.
- M6.20 baseline facts: mew and Codex each ran one
  `terminal-bench/make-mips-interpreter` smoke trial with `n_errors=0`, empty
  `exception_stats`, and mean score `0.0`. The baseline route is not M6.14
  repair yet; next step is an instruction-consuming mew rerun, then M6.18
  failure classification if score remains zero.
- M6.19 task `#687` added `.harbor/mew_terminal_bench_agent.py`,
  `docs/terminal-bench-harbor-smoke.md`, and
  `tests/test_harbor_terminal_bench_agent.py`.
- Focused validation for `#687` passed:
  `uv run pytest -q tests/test_harbor_terminal_bench_agent.py --no-testmon`,
  `uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py`,
  and `git diff --check`.
- Autonomy accounting: mew produced the wrapper/docs/tests and repaired the
  await-time timeout fallback test; Codex applied a one-line supervisor lint
  cleanup after mew marked the task done without running ruff. Count the slice
  as product progress with a small reviewer cleanup, not a fully clean
  mew-first close.
- Historical M6.19 gap after `#687`: live Harbor execution and reference-agent
  comparison were still missing at that point.
- M6.19 task `#688` repaired Harbor factory/install compatibility. Focused
  validation passed:
  `uv run pytest -q tests/test_harbor_terminal_bench_agent.py --no-testmon`,
  `uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py`,
  `git diff --check`, and a real Harbor tool-env
  `AgentFactory.create_agent_from_import_path(...)` smoke.
- M6.19 close audit:
  `docs/M6_19_TERMINAL_BENCH_COMPATIBILITY_AUDIT_2026-04-27.md`.
  The mew smoke result is
  `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-help-fixed-return-code/result.json`
  with `Exceptions=0`, transcript `exit_code=0`, and score `0.0`.
  The Codex reference result is
  `proof-artifacts/terminal-bench/harbor-smoke/codex-smoke-make-mips/result.json`
  with `Exceptions=0`, score `0.0`, and Codex token metadata in Harbor
  `agent_result`.
- M7 task `#686` pending dry-run tools `#6644/#6645` were rejected without
  applying because M7 is now pending behind Terminal-Bench milestones.
- Earlier roadmap-only M6.19/M6.20 setup remains historical; current M6.19
  validation includes the focused wrapper tests and ruff checks listed above.

Latest M6.18 source/test validation:

- Close audit: `docs/M6_18_CLOSE_GATE_AUDIT_2026-04-27.md`.
- Failure diagnosis slice:
  `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`,
  `uv run ruff check src/mew/mew_first_calibration.py src/mew/implementation_lane_baseline.py tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py`,
  `./mew metrics --mew-first --limit 10 --json`, and
  `./mew metrics --implementation-lane --limit 10` passed.

Latest M6.17 source/test validation:

- Task `#679` lane-dispatch proposal slice:
  `uv run python -m unittest tests.test_tasks tests.test_commands`,
  `uv run ruff check src/mew/tasks.py src/mew/commands.py tests/test_tasks.py tests/test_commands.py`,
  and `git diff --check` passed.
- Task `#680` active roadmap gate slice:
  `uv run python -m unittest tests.test_brief`,
  `uv run ruff check src/mew/brief.py tests/test_brief.py`, and
  `git diff --check` passed.
- Task `#681` no-candidate next-action fallback slice:
  `uv run python -m unittest tests.test_commands`,
  `uv run ruff check src/mew/commands.py tests/test_commands.py`, and
  `git diff --check` passed.

Earlier M6.16 source/test validation:

- Task `#678` first-edit latency budget slice:
  `uv run pytest -q tests/test_work_session.py -k 'work_think_prompt or first_edit_latency' --no-testmon`,
  `uv run python -m unittest tests.test_work_session`,
  `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`,
  and `git diff --check` passed. Codex-ultra review session
  `019dcb9d-ddf7-7f30-8605-7b603f048ba8` reported `STATUS: pass` with
  `NO FINDINGS`.
- M6.13 deliberation work-loop call-boundary slice:
  `uv run pytest -q tests/test_work_deliberation_loop.py --no-testmon`,
  `uv run pytest -q tests/test_deliberation.py tests/test_work_deliberation_loop.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'deliberation or active_work_todo or lane' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'plan_work_model_turn' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_deliberation_loop.py`,
  and `git diff --check` passed.
- M6.13 deliberation live-control slice:
  `uv run pytest -q tests/test_deliberation.py tests/test_work_deliberation_loop.py tests/test_work_deliberation_cli.py --no-testmon`,
  `uv run ruff check src/mew/deliberation.py src/mew/work_loop.py src/mew/commands.py src/mew/cli.py tests/test_deliberation.py tests/test_work_deliberation_loop.py tests/test_work_deliberation_cli.py`,
  and `git diff --check` passed.
- M6.13 Phase 3 internalization proof slice:
  `uv run pytest -q tests/test_dogfood.py -k 'm6_13' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py tests/test_work_session.py -k 'm6_13 or approve_all or paired' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'approve_all or paired' --no-testmon`,
  `./mew dogfood --scenario m6_13-deliberation-internalization --workspace /tmp/mew-m6-13-proof-cli-3 --json --report /tmp/mew-m6-13-proof-cli-3-report.json`,
  `./mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model-backend codex --model gpt-5.5 --model-timeout 120 --workspace /tmp/mew-m6-13-live-gpt55-2 --json --report /tmp/mew-m6-13-live-gpt55-2-report.json`,
  `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`,
  and `git diff --check` passed for the final normal work-path close proof.
  Earlier supporting validation:
  `uv run pytest -q tests/test_memory.py -k 'reasoning_trace' --no-testmon`,
  `uv run pytest -q tests/test_dogfood.py -k 'm6_13_deliberation_internalization or m6_13_live_provider or scenario_choices' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'compact_active_memory_preserves_reasoning_trace_provenance' --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'write_ready_tiny or write_ready_fast_path or compact_active_memory_preserves_reasoning_trace_provenance' --no-testmon`,
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --json`,
  `uv run python -m mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model gpt-5.5 --model-timeout 180 --json`,
  `uv run ruff check src/mew/typed_memory.py src/mew/work_session.py src/mew/work_loop.py src/mew/commands.py src/mew/cli.py src/mew/dogfood.py tests/test_memory.py tests/test_dogfood.py tests/test_work_session.py`,
  and `git diff --check` passed.
- M6.14 side-project write-scope repair from GitHub issue `#1`:
  `uv run pytest -q tests/test_work_write_scope.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k 'plan_work_model_turn or paired or write_batch' --no-testmon`,
  `uv run ruff check src/mew/work_loop.py src/mew/commands.py tests/test_work_write_scope.py`,
  and `git diff --check` passed.
- M6.13 mirror lane-scoped replay bundle slice:
  `uv run pytest -q tests/test_work_replay.py -k "lane or path_shape" --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py -k "lane_metadata" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`,
  `uv run pytest -q tests/test_proof_summary.py --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "shadow_bridge_mirror_lane or shadow_bridge_records_validated_replay" --no-testmon`,
  `uv run pytest -q tests/test_work_session.py -k "patch_draft_compiler_shadow_bridge" --no-testmon`,
  `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py tests/test_proof_summary.py --no-testmon`,
  and
  `uv run ruff check src/mew/work_loop.py src/mew/work_replay.py tests/test_work_session.py tests/test_work_replay.py tests/test_proof_summary.py`
  passed.
- M6.13.2 side-project dogfood telemetry v0:
  `uv run pytest -q tests/test_side_project_dogfood.py --no-testmon` passed,
  `uv run ruff check src/mew/side_project_dogfood.py src/mew/commands.py src/mew/cli.py tests/test_side_project_dogfood.py`
  passed, `./mew side-dogfood template` printed the appendable schema, and
  `./mew side-dogfood report --json` returned an empty valid report for the
  default ledger.
- task `#650` / session `#638`: replay metadata lane provenance/defaulting
- task `#652`: M6.14 fast-path required-term stopword repair
- `uv run pytest -q tests/test_work_replay.py --no-testmon` passed
- `uv run pytest -q tests/test_work_replay.py tests/test_work_lanes.py --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py -k "write_ready or required_terms" --no-testmon`
  passed
- `uv run ruff check src/mew/work_replay.py src/mew/work_loop.py tests/test_work_replay.py tests/test_work_session.py`
  passed
- `git diff --check` passed
- task `#651`: M6.14 repair for #650 required-terms synthetic schema
- `uv run pytest -q tests/test_work_session.py -k "required_terms or tiny_write_ready_draft_prompt" --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py -k "write_ready" --no-testmon`
  passed
- `uv run ruff check src/mew/work_loop.py tests/test_work_session.py` passed
- `git diff --check` passed
- task `#649` / session `#636`: data-only lane-attempt telemetry v0
- `uv run pytest -q tests/test_work_lanes.py --no-testmon` passed
- `uv run python -m unittest tests.test_work_lanes` passed
- `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py` passed
- `git diff --check` passed
- task `#648` / session `#635`: data-only lane registry v0
- `uv run pytest -q tests/test_work_lanes.py tests/test_work_session.py -k 'work_lane or active_work_todo_lane' --no-testmon`
  passed
- `uv run python -m unittest tests.test_work_lanes` passed
- `uv run ruff check src/mew/work_lanes.py tests/test_work_lanes.py` passed
- `git diff --check` passed
- task `#647` / session `#634`: additive WorkTodo lane normalization
- `uv run pytest -q tests/test_work_session.py -k 'active_work_todo or lane' --no-testmon`
  passed
- `uv run pytest -q tests/test_work_session.py --no-testmon` passed
- `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
  passed
- `git diff --check` passed

Latest milestone-close validation:

- M6.8.5 close audit passed via `docs/M6_8_5_CLOSE_GATE_AUDIT_2026-04-26.md`
- detailed pre-compression `ROADMAP_STATUS.md` was archived to
  `docs/archive/ROADMAP_STATUS_detailed_2026-04-26.md`

Behavioral validation for the latest source/test changes is listed above under
tasks `#639` through `#646`; this closeout edit is documentation/status only.

## Maintenance Rule

Keep this file as a dashboard, not a changelog.

- Move detailed milestone history to `docs/archive/`.
- Keep only active decision, sequencing, reopen rules, and current next action
  here.
- When a milestone closes, add or update a close-gate audit in `docs/` and
  summarize only the result here.
- Do not let `mew focus`, stale paused tasks, or historical active sessions
  override the active milestone decision in this file.
