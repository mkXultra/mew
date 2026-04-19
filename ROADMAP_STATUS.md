# Mew Roadmap Status

Last updated: 2026-04-20

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | `mew work --ai` can inspect, edit, verify, resume, and expose an audit trail without delegating to an external coding agent. |
| 2. Interactive Parity | `in_progress` | `mew work --ai` now has deterministic live steps, command/model streaming with readable compact model deltas, persisted work-session gates, phase/elapsed progress anchors, grouped action/result panes, focused multi-pane views, compact/quiet chat controls, work-mode/follow cockpit controls, one-time steer, interrupt/max-step reentry notes, approval/live controls, chat transcript logging, work-session/global ledgers, repeated-action guardrails, effort budget signals, prioritized desk actions, paired-test source-edit steering, paired-test approval auto-defer, paired verifier promotion, stale reentry labeling, same-surface source-edit audit checkpoints, verification-confidence checkpoints, external-cwd/default-preserving observer recovery hints, and proved mew-side interruption/process-stop comparative gates; the remaining gap is a polished continuous REPL-style coding cockpit. |
| 3. Persistent Advantage | `in_progress` | Task-local resume, working memory, compressed prior think, durable work notes, typed/scoped active memory, user preferences, unresolved-risk reentry, continuity scoring, live world-state context, task-kind scoped reentry views, short passive native-work advancement, deterministic continuity dogfood, a day-scale reentry proof, and a scoped M3 reentry gate now exist; long-running resident cadence is still unproven. |
| 4. True Recovery | `in_progress` | `doctor`, `repair`, runtime effect journal, `recovery_hint`, recovery plans, safe read/git and verifier retries, passive auto-recovery, direct Ctrl-C capture, and batched CLI/chat/runtime safe auto-recovery exist; broader automatic side-effect recovery is not implemented. |
| 5. Self-Improving Mew | `foundation` | Native self-improvement dogfood can produce useful implementation targets, expose active-memory/cell reentry controls, and preserve recent completed work, but closed-loop self-improvement is not yet reliable. |

## Active Milestone Decision

Last assessed: 2026-04-20 01:39 JST.

Active milestone: Milestone 2, Interactive Parity.

Rationale: Milestone 1 is closed. Milestones 3-5 have useful foundations, but
they should not pull fresh implementation away from the earliest unfinished
roadmap gate unless the user explicitly redirects the session or a concrete
M2-blocking metric requires a supporting slice.

Milestone 2 Done-when checklist:

- Using mew for one focused coding task feels close to Claude Code / Codex CLI:
  partial. The cockpit has live/follow cells, scoped chat, approvals, ledgers,
  and real dogfood evidence. The first `mew dogfood --scenario m2-comparative`
  paired run is recorded in `docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md`; it
  preferred a fresh CLI for the small local task because mew hit a paired
  source/test approval loop. A first mitigation now exposes explicit
  single-approval `--defer-verify` controls for test-first or paired-change
  flows, and a follow-up mew-led implementation task used that control to avoid
  the rollback loop and finish. A second mitigation now tags tests/** dry-runs
  created from `paired_test_steer` as approval-time auto-defer candidates: their
  resume/cell primary approve hint uses `--defer-verify`, approval records a
  system note, and a failing verifier is not run until the matching source edit
  arrives; the same dogfood now retries the source edit and records a passing
  approval verifier after the deferred test approval. `./mew dogfood --scenario
  work-session --workspace /tmp/mew-m2-auto-defer-full-dogfood --json` passed
  with `work_ai_paired_test_approval_auto_defers_verification`, proving this
  exact flow. The mew-side M2 comparative artifact at
  `/tmp/mew-m2-auto-defer-full-comparative/.mew/dogfood/m2-comparative-protocol.json`
  prefills this run with two applied approvals and a passing verifier. The
  merged fresh `codex-ultra` comparison at
  `/tmp/mew-m2-auto-defer-full-combined/.mew/dogfood/m2-comparative-protocol.json`
  still marks `fresh_cli_preferred` for this no-edit artifact verification task;
  the outcome is documented in
  `docs/M2_AUTO_DEFER_COMPARATIVE_DOGFOOD_2026-04-20.md`. The compact follow stop surface now preserves the
  `apply tool #... and defer verification` control, matching the resume/cell
  surfaces. The M2 comparative dogfood can now prefill mew-side evidence from a
  real work session via `--mew-session-id`, so future parity checks carry actual
  wall/active time, approval, verification, resume, and continuity evidence
  instead of only a protocol template. It can also merge a paired fresh-CLI JSON
  report via `--m2-comparison-report`, making the comparison executable without
  hand-editing the protocol markdown. A real paired high-idle metrics refactor
  then flowed through this evidence pipeline with mew session `#246` and a
  fresh `codex-ultra` worktree report; the combined artifact passed and marked
  `fresh_cli_preferred`. Parity is still not claimed: for small localized
  changes, mew's persistent context is useful but the observer/supervision
  overhead remains higher than a fresh CLI. A small permission-mode slice now
  adds explicit `--approval-mode accept-edits` for `mew do`, `mew work --live`,
  and `mew code` defaults: dry-run write/edit previews are applied
  automatically only when this mode is requested, while write roots,
  paired-test source-edit guards, and approval-time verification still apply.
  The deterministic work-session dogfood now includes
  `work_ai_accept_edits_auto_applies_preview`, and
  `docs/M2_ACCEPT_EDITS_DOGFOOD_2026-04-20.md` records the focused validation
  and passing `/tmp/mew-accept-edits-work-session-dogfood` run. M2 comparative
  artifacts now also serialize the mew-side `approval_mode` and default
  permission posture, so future fresh-CLI comparisons can tell whether
  `accept-edits` was actually used. Real dogfood of task `#259` exposed a
  test-first failure mode where `accept-edits` auto-applied a normal paired-test
  preview and verified before the source edit landed; paired-test-steer previews
  are now marked with `defer_verify_on_approval`, and
  `/tmp/mew-accept-edits-paired-defer-dogfood` proves
  `work_ai_accept_edits_defers_paired_test_first_verification`. A follow-up
  M2 ceremony slice keeps `batch` read-only by default but allows exactly one
  `tests/**` write/edit plus one `src/mew/**` write/edit as a guarded paired
  write batch. Both writes are forced to dry-run previews, ordered
  test-before-source, and still flow through approval / approve-all. Under
  `--approval-mode accept-edits`, the new pending previews are auto-approved as
  one group: the test approval defers verification and the source approval runs
  the final verifier. `/tmp/mew-paired-write-batch-dogfood` proves
  `work_ai_accept_edits_auto_approves_paired_write_batch`. Real dogfood task
  `#260` then used this path in session `#251`: the resident emitted one paired
  write batch for `tests/test_dogfood.py` plus `src/mew/dogfood.py`,
  `accept-edits` auto-approved both previews, full pytest and the focused M2
  comparative test passed, and `/tmp/mew-m2-paired-batch-evidence` records
  `paired_write_batch.status=proved` in the comparative protocol. The merged
  fresh `codex-ultra` comparison at `/tmp/mew-m2-paired-batch-combined` still
  records `resident_preference.choice=fresh_cli` for this narrow write-heavy
  edit/test loop: paired batch reduces mew ceremony, but direct fresh CLI is
  still lower overhead when no pause, handoff, or resident memory advantage is
  exercised.
- The model does not lose momentum while waiting for tool feedback: partial.
  `./mew metrics --kind coding --limit 20` at this assessment showed
  `first_tool_start_seconds p95=30.15s`, `model_resume_wait_seconds p95=25.25s`,
  and `perceived_idle_ratio p95=0.905`, while approval and verification
  friction remain high. Recent-session metrics now ignore later cleanup
  `updated_at` churn when selecting and measuring session wall time, so stale
  session cleanup no longer contaminates the current M2 momentum view.
  `mew metrics` now also surfaces `slow_first_tools` diagnostics, including the
  session, first tool call, first turn id, path, and first model summary behind
  slow first-tool-start latency. The same diagnostic now reaches
  `mew focus --kind coding` as `first_tool_start_p95` plus concrete first-tool
  samples, so reentry can choose a latency slice without opening the metrics
  report first. The latency now starts at the first model turn when present,
  avoiding false slow-first-tool signals from a native session that was created
  and then left dormant before the first follow run.
  Native self-improve sessions started inside the mew project now also seed
  `src/mew` and `tests` as write roots plus `uv run pytest -q` verification,
  preventing the resident from dead-ending in read-only mode when the chosen M2
  improvement needs a code change. When coding focus is otherwise idle, the
  next native self-improve command now uses recent metrics signals to target the
  focus string, avoiding a generic "pick anything" self-improvement loop.
  Historical approval and verification friction is now retired from active
  metrics when later successful verification covers the same command, test
  path, or source/test surface. After recording fresh mew-native verification
  for the old `tests/test_dogfood.py` and `tests/test_work_session.py` failures,
  `./mew metrics --kind coding --limit 20` reports
  `approval_rejection=None`, `verification_failure=0.0`, and
  `verification_rollback=0.0`; the remaining active signal is idle time rather
  than stale approval/verification history.
  Covered historical dry-run approvals are also excluded from approval-bound
  wait metrics, so rejected stale proposals no longer reappear as
  `approval_bound_p95` after later verification proves the same surface healthy.
  `mew focus --kind coding` now uses the same 20-session observation window as
  the metrics-targeted self-improve next move, and renders
  `perceived_idle_ratio`, `high_idle_sessions`, and concrete high-idle session
  samples when idle-time friction drives the next M2 task. This keeps the
  suggested next self-improve loop grounded in visible evidence instead of a
  hidden metrics signal. The idle ratio is now measured over the actual
  model/tool loop window instead of the whole session span, so human pause time,
  session creation delay, and later notes no longer look like model momentum
  loss. With that definition, `./mew metrics --kind coding --limit 20` reports
  `first_tool_start_seconds p95=14.3s`, `model_resume_wait_seconds p95=21.5s`,
  and `perceived_idle_ratio p95=0.551`, with no high-idle signal; remaining
  samples are slow individual model resumes rather than a broad active blocker.
  The paired-test approval auto-defer slice also reduces approval/verification
  ceremony for the B1 rollback-loop blocker without claiming that the broader
  continuous cockpit is solved.
- During a focused coding task, an interrupted resident can resume inside mew
  without user re-briefing and would not prefer to restart in a fresh coding
  CLI: partial. M1-level resume and M3 continuity foundations exist. A scoped
  `mew dogfood --scenario m3-reentry-gate` proof now exercises the narrow
  interruption/context-compression gate that M2 needs: an interrupted coding
  task resumes with the pending change, failed verifier risk, live world state,
  and next action visible, then advances by applying the known edit and running
  verification successfully. This is supporting evidence, not full parity: the
  next comparative run still needed an interruption-shaped mew task paired
  against a fresh Claude Code or Codex CLI session, with the resident-preference
  result recorded. The follow-up comparative run in
  `docs/M2_INTERRUPT_COMPARATIVE_DOGFOOD_2026-04-20.md` proved the mew-side
  interruption-resume gate on a controlled failed-tool recovery task: changed
  work, preserved recovery risk, runnable next action, strong continuity, and
  post-reentry verification were all present. A stricter Ctrl-C process-stop
  run is recorded in `docs/M2_PROCESS_STOP_COMPARATIVE_DOGFOOD_2026-04-20.md`;
  its actual interruption and final verification landed in separate work
  sessions, so M2 comparative dogfood now supports `--mew-session-id task:<id>`
  task-chain evidence. That task-chain gate is also `proved`. The combined
  resident preference remains `inconclusive` because the matching fresh CLI leg
  was not interrupted.

Current decision rule: the next implementation task must close one unmet
Milestone 2 Done-when criterion or reduce a measured blocker to that criterion.
Useful next choices are running a true interruption-shaped paired source/test
M2 comparative task and a matching interrupted fresh-CLI comparison, or a
targeted latency/friction slice chosen from `mew metrics --kind coding`.
Polish, side projects, and later-milestone architecture are deferred unless
they directly unblock this active criterion.
The 2026-04-19 scoped M3 Reentry Gate is a supporting slice for this rule, not
a milestone switch: after it is green, return to M2 by running or preparing a
paired interruption-shaped comparative dogfood task.
`docs/ADOPT_FROM_REFERENCES.md` remains advisory implementation evidence:
§0.1 and §0.2 are durable adoption decisions, while §1-§5 cards are candidate
levers chosen only when a measured active-milestone signal justifies them.

## Current Focus Notes (Historical)

Canonical current focus is the `Active Milestone Decision` above. The notes
below are retained as recent evidence and should not override the active
milestone gate.

The active Persistent Advantage framing is now continuity, not calendar time.
`mew work` resume bundles compute a `continuity` score across working memory,
risk preservation, runnable next action, approval visibility, recovery path,
verifier confidence, context budget, and prior decisions. The same score is
visible in text resume output, `mew focus`, follow snapshots, and
`follow-status`, and `dogfood --scenario continuity` deterministically proves
that memory, failed verification, pending approval, focus reentry, and observer
status survive an interruption-style pivot. `compressed_prior_think` also keeps
older model turns visible after the recent decision window would otherwise drop
them. Keep one day-scale scenario for time-decay failures, but choose next work
from continuity friction first.
Codex-ultra review then tightened that contract: continuity scoring now requires
concrete risk/recovery controls instead of counting any non-empty next-action
text, includes a `user_pivot_preserved` axis for pending steer / queued
follow-up state, and `mew focus` surfaces that pivot cue. The local fresh-CLI
reference symlinks are also guarded by pytest `testpaths = ["tests"]`, so
default `uv run pytest` no longer recurses into external reference checkouts.
Codex-ultra re-review of those three findings passed in session
`019da3df-9b5c-7932-8452-d14fd83f77e9`, with local verification of
`uv run pytest tests/test_work_session.py tests/test_dogfood.py` and
default `uv run pytest`.
Continuity is now actionable when it is not strong: the score carries a
`recommendation` with ordered repair actions, and text resume, focus,
`status`, and `follow-status` surface a `continuity_next:` line for weak or
usable bundles instead of leaving the resident to infer the recovery step.
Claude-ultra review then found one false-strong risk in that contract:
human-readable waiting text and hint-only recovery items could look more
runnable than they were. The continuity score now uses word-boundary runnable
action checks, rejects waiting/pending next-action prose outside active waiting
phases, and requires recovery hints to contain a real mew/chat control or an
explicit command/review step.
The same repair signal now reaches `mew next`: when an active work session has
weak or broken continuity, the top-level next move points at a live continuity
repair action instead of blindly entering the coding cockpit, while usable
sessions still route to the normal cockpit.
Codex-ultra re-review of that fix passed in session
`019da3ff-e521-7351-a5de-3943ae3d81b8`: focused probes confirmed usable
continuity routes to `mew code`, broken continuity routes to
`mew work ... --live --max-steps 1`, and `mew next --json` returns the live
repair command.
Self-memory continuity cues now build from the same work-session resume bundle,
so generated self-memory preserves the active session's continuity score and
repair recommendation alongside phase and next action.
Dream active-session lines now use the same resume-derived continuity signal,
so overnight-style reflection preserves the active work score and repair cue
instead of only raw phase/next-action text.
Journal active-session lines use that resume-derived signal too, making daily
reports preserve the same continuity score, repair recommendation, and next
action that `focus`/`next` use.
The 2026-04-19 reference-adoption decision is now recorded in
`docs/ADOPT_FROM_REFERENCES.md`: if optimizing for "would I want to be inside
mew?", the next persistence slice is 5.12 Memory Scope × Type, not streaming.
Streaming remains the right M2 choice when cockpit latency becomes the live
pain, while AgentMemorySnapshot should wait until the state/resume shape is
less volatile.
The 5.12 MVP now exists: file-backed typed/scoped memories can be written under
`.mew/memory/{private,team}/{user,feedback,project,reference,unknown}/`,
searched through `mew memory --search ... --type ... --scope ...`, and listed
from `mew memory --deep`, while existing state memory remains legacy
`unknown` instead of being migrated. Native work resume now also exposes a
bounded `active_memory` bundle from that store, and the same bundle flows into
the resident THINK prompt so user/project/reference memory can influence the
next step without a manual search.
Follow-up dogfood proved the active recall route with the real Codex Web API,
added `mew memory --active --task-id ...` as the debug surface, exposed that
command from native self-improve controls, tightened term extraction so
self-improve boilerplate and recent commit hashes do not dominate recall, and
now prints score plus matched terms in text output.
Native self-improve entry output now also exposes the task-scoped
`mew work <task-id> --cells` command, giving a context-compressed resident a
stable cell cockpit reentry surface without remembering the flag.

Milestone 2 is the active focus. The latest Claude Code / Codex CLI reference
investigation is preserved in `docs/COCKPIT_REFERENCE_NOTES.md`; it does not
change the roadmap goal, but it narrowed the cockpit target to stable
`mew work --follow` cells plus explicit mid-loop control lanes. The useful cell
slice, one-time steer lane, FIFO queued follow-up lane, and boundary-safe
interrupt-submit lane now exist, so the next cockpit work should dogfood a real
coding change before adding more ad hoc log output.

Already shipped: readable diff panes,
command/test output panes, chat work-mode, bounded follow loops, compact live
result panes, readable compact model-delta previews, phase/elapsed progress
anchors, chat transcript logging, interrupt/max-step reentry notes, and scoped
reentry controls. Remaining gap: a calmer continuous coding cockpit with a more
stable reasoning/status pane, less repeated reentry material during long
sessions, and more real dogfood on repository work. Fresh `mew code` dogfood
fixed partial `/follow --max-steps ...` commands dropping cached session gates;
made runtime activity opt-in for `mew code`; added search match counts to
summaries; made inline approval rejection stop live/follow loops; and removed
duplicated cached `--max-steps` controls. External dogfood then fixed
non-positive `--max-steps` running a model step and stopped newer memory from
reattaching stale old tool state. Keep using real cockpit friction, not imagined
polish, to choose the next fix.
Real dogfood with `mew code` task #48 produced an isolated
`experiments/mew-dream` prototype, then fixed two cockpit blockers it exposed:
brand-new write roots can now be created during gated writes, and `--no-verify`
now prevents approval from resurrecting stale verification commands.
Fresh human-role dogfood with `codex-ultra` then tightened the direct CLI
cockpit: session start gates now persist into later manual tools, closed/done
sessions allow read-only review probes, focused pane flags compose without
`--session`, and `mew chat --quiet` can start without a banner.
Latest native self-improvement dogfood then polished the self-improve entry
help, aligned historical diff JSON with the text `recorded_at` label, and made
batch action summaries show read-window fields so compact cockpit output better
matches the model's actual tool plan.
`codex-ultra` human-role dogfood on current HEAD then found three concrete
cockpit papercuts that are now fixed: unclipped diff stats for huge single-line
edits, explicit cleanup-skipped reporting for user-provided dogfood workspaces,
and visible `work cwd` output for native self-improvement sessions started
outside the repository.
The remaining scoped-resume ambiguity from that dogfood is also reduced:
implicit `/work-session resume` now names the selected active task when more
than one scoped session matches.
Retesting then found and fixed the last diff-stat edge case: huge single-line
edits without a trailing newline now count as `+1 -1` instead of `+0 -1`.
Fresh Codex review of the follow/interrupt lanes found and fixed three smaller
human-loop issues: queued follow-ups are now shown in FIFO order even when the
resume view is truncated, idle `interrupt_submit` sessions now point directly
at the continue command that will submit the pending interrupt, and reply-file
help no longer under-documents supported observer actions.
Native self-improve dogfood then picked a small discoverability fix: `mew code
--help` now documents both external resume (`mew work <task-id> --session
--resume --allow-read .`) and scoped chat reentry (`mew chat --kind coding
--work-mode`).
Cell cockpit pacing has one more concrete control: `mew work --cells
--cell-tail-lines N` now caps command/test stdout/stderr tails for calmer
inspection while leaving failure expansion as the default when no cap is set.
Claude review then identified the highest-leverage external-observer gap:
`--reply-file` could reject or steer pending writes but could not approve them.
That gap is now closed with `approve` and `approve_all` reply actions, plus
schema/docs/dogfood coverage, so another model watching `.mew/follow/latest.json`
can drive a dry-run write through approval without a separate human CLI command.
The same follow snapshot now also exposes top-level `pending_approvals`, so an
observer does not have to dig through the nested resume bundle just to find the
approval tool ids.
Native self-improve entry output now prints a direct resume command alongside
continue/follow, making long-running self-improvement sessions easier to reenter
after context compression or a terminal restart.
External observer dogfood on that approval loop confirmed another model could
approve a dry-run write from `.mew/follow/latest.json`; the follow snapshot now
also carries `supported_actions`, emits an approval-shaped `reply_template` when
approvals are pending, supports `--live/--follow --max-steps 0` as a no-model
snapshot refresh, and suppresses stale approval-waiting working-memory hints after a
reply-file approval has already resolved them.
Follow snapshots now also expose CLI-native approval/rejection hints beside the
chat cockpit hints, so external observer agents do not have to translate
`/work-session ...` controls back into `mew work ...` commands.
`mew work --follow-status` now gives observers a read-only freshness/producer
liveness check over `.mew/follow/latest.json` or the session snapshot, closing
the read-side loop around the reply-file observer contract.
Observer automation is now less text-dependent: task add/list/show/update/done
have JSON surfaces with top-level aliases, `mew observe` aliases the passive
workspace perception view, zero-step follow refresh supports `--json`, and
`follow-status` returns `producer_health` plus `suggested_recovery` commands
for absent, stale, dead, or recovery-plan-bearing snapshots.
The latest True Recovery pass proves the passive native failure loop can close:
a failed runtime-owned native advance asks a classified recovery question,
`recover-session` reruns the interrupted verifier, marks the old call
superseded, and the next passive tick resumes native advance. Recovery
suggestions now use the recovery plan's action priority, so side-effect review
is not hidden by a later verifier retry hint.
The newest recovery slice goes one step further: when a runtime-owned native
advance leaves only an interrupted verifier and the runtime was started with
matching read/verify gates, the next passive tick can rerun that verifier
itself and then resume native advance on the following tick. If a higher-risk
interrupted write/command is still selected by the recovery plan, mew falls back
to the visible recovery question instead of auto-running the verifier.
The same selected-item pattern now covers interrupted safe read/git tools:
`read_file`, `search_text`, `glob`, `inspect_dir`, and `git_*` can be replayed
by the next passive tick when they are the recovery plan's selected item and
the runtime read gate covers the recorded path/cwd.
Runtime startup now performs the safest part of the repair path that previously
required an explicit `mew repair`: incomplete runtime effects are marked
`interrupted` before the new runtime cycle begins. Running work-session
tools/model turns remain reserved for explicit repair because a startup process
cannot prove a human-owned or orphaned subprocess is dead.
The latest Persistent Advantage pass adds a deterministic `day-reentry`
dogfood scenario and `focus` age display, proving that an active work session
aged by more than a day still surfaces last-active time, working memory,
resume/follow commands, notes, live file world state, and old activity events.
Claude's follow-up evaluation judged mew inhabitable for small supervised
coding slices, but called out paired implementation+test discipline as a top
remaining blocker versus Claude Code/Codex CLI. The latest cockpit pass adds
an advisory pairing status for `src/mew/**` write approvals and tells the
resident to carry the intended paired test in `working_memory` when the write
approval boundary stops the loop.
Fresh mew-as-buddy dogfood on task #122 tightened that approval path: unpaired
`src/mew/**` source edits no longer present plain approve as the primary action
in cells, resume text, chat cockpit controls, follow `reply_template`, or
follow/control JSON; they steer toward adding paired tests or require an
explicit unpaired override. The same dogfood pass found that narrow pytest
  selector runs polluted future continue commands, so successful `pytest -k`,
  node-id, marker, last-failed, deselect, or broad-to-file verification runs no
  longer replace an existing broader default verify command.
Follow `reply_template` also scans the whole visible pending-approval set for
unpaired source edits before suggesting any normal approval, avoiding mixed
approval batches where an early safe write hides a later source edit that still
needs tests.
If the unpaired source edit is outside the visible pending-approval window but
still blocks approve-all, the reply template now steers to resume inspection
instead of approving the first visible normal write.
If the first successful verification is a narrow pytest node-id run, mew marks
it as a narrow verification result and keeps it out of default verify fallback,
so the next resident step does not inherit a one-test command as its long-lived
gate.
The paired-test loop now gives the resident a concrete first test-file
candidate: `pairing_status.missing_test_edit` includes an inferred
`suggested_test_path` such as `src/mew/work_session.py` ->
`tests/test_work_session.py`, visible in resume text, approval cells, follow
snapshots, and reply-file steer text.
Compact task workbench reentry now also surfaces the latest unresolved
work-session failure as a `risk:` line, while hiding only superseded recovered
failures. This keeps failed verifier recovery or failed work tools visible from
the top-level `mew work <task-id>` front door instead of requiring a full
session resume.
The newest dogfood friction fix makes `mew dogfood --all` an exact shortcut for
`--scenario all`, so the command a resident/human naturally tries no longer
collides with the `--allow-*` gate flags.
The same unresolved-risk signal now reaches `mew focus`: active work sessions
carry a compact `risk:` line from the shared work-session failure formatter,
and the day-reentry dogfood seeds a failed verifier to prove the quiet daily
entrypoint preserves that risk.
State persistence is also less noisy under live output mirroring: `state_lock`
now serializes same-process threads as well as external processes, and
`save_state` uses per-thread/per-call temp names for both state and backup
writes.
Search navigation is more forgiving for resident models: `search_text`
normalizes space-separated include globs such as `src/** tests/** docs/**` and
adds absolute-path-friendly `**/` variants before invoking `rg`.
Native self-improvement startup now has a structured surface:
`mew self-improve --start-session --json` returns the task, work session, and
copy-paste controls without scraping text.
Reused native self-improve sessions now refresh their work-session title/goal
from the latest task description, so changing `--focus` does not leave an old
resident objective inside the active session.
The native self-improve help now advertises the structured
`--start-session --json` entrypoint directly in the work-session flow.
The bake-off ledger `WHY_MEW.md` now records real mew-vs-fresh evidence; the
first task proved mew's resume advantage after a failed model call, while a
fresh `codex-ultra` review found broader same-surface JSON gaps that were then
fixed.
The latest long dogfood session connected several active-buddy surfaces:
resident work loops now block repeated identical tool calls before execution,
failed repeat-guard tool calls carry concrete recovery actions, work sessions
surface effort/budget pressure in resume/model context/desk, and `mew desk`
now exposes prioritized actions with rationale and stale age while keeping the
old `primary_action` field for compatibility.
The current 2026-04-19 long dogfood pass extended that thread with commits
`4073282`, `d500105`, and `6229213`: native self-improve start sessions now
persist read/compact-live defaults, chat `/self start` matches the CLI path and
marks the task ready, and approved paired `src/mew/**` source edits can promote
the session verifier to the inferred matching test while `approve-all` applies
the pending paired test edit first when promotion depends on it.
The same long session then added commits `c7a6a7c`, `c0901c3`, and `718cc41`:
compact workbench reentry now labels stale next steps explicitly,
native-only self-improve start hints carry the read/compact-live defaults they
need to preserve handoff quality, and `follow-status` recovery commands reuse
the selected work session's saved read roots and compact-live preference instead
of falling back to `--allow-read .` for absent/dead observer snapshots.
External human-role dogfood then found two arbitrary-cwd handoff footguns that
are fixed in `c8f3109`: generated commands now preserve a path-style `mew`
launcher when the observer invoked `/path/to/mew`, and session-scoped git/run
tools default to the task cwd when no meaningful `--cwd` was provided.
The evaluator-requested same-surface checkpoint is now visible in the resident
resume/workbench path: changed `src/mew/**` work-session writes surface a
`same_surface_audit` prompt until a newer session note records that sibling
code paths on the same surface were checked, while no-op dry-runs and stale
pre-edit notes do not satisfy it. The deterministic work-session dogfood now
covers this alongside the existing paired-test advisory.
Follow-up self-improve dogfood then used the new native session path to choose
a tiny reentry-doc fix: `01e9f2a` aligns `mew self-improve --help` with the
actual generated resume control by documenting `mew work <task-id> --session
--resume --allow-read .`.
One more small dogfood pass fixed the empty coding-queue recommendation:
`d437460` now suggests `mew self-improve --start-session --ready ...`, so the
created native self-improvement task enters the ready coding queue instead of
being left as a todo task.
The same empty-queue action now reaches the desk/pet surface in `81f0412`:
`mew desk --kind coding` exposes a `start_self_improve` primary action with the
same ready native self-improve command instead of going actionless while focus
has a next move.
Task #175 adds a verification-confidence checkpoint to the resident work
surface: pending source approvals, stale verifiers, partial coverage, selector
or node-id verifier runs, and broad verified runs now produce structured
confidence state in resume/live/follow/follow-status before a resident calls
work finished or applies approval.

## Milestone 1: Native Hands

Status: `done`

Evidence:

- Native read/write/verify helper modules exist.
- Runtime action application can perform bounded actions.
- `src/mew/action_application.py` started extracting action application helpers.
- Roadmap first slice is defined.
- `work_session` state now tracks active native work sessions and their tool calls.
- `mew work <task-id> --start-session` starts or reuses a native work session.
- `mew work --tool read_file|search_text|glob|inspect_dir --allow-read ...` runs read-only native tools and journals outcomes.
- `mew work --tool run_tests --allow-verify ...` runs verification commands and journals command results.
- `mew work --tool run_command --allow-shell ...` runs explicitly gated shell commands and journals command results.
- `mew work --tool write_file|edit_file --allow-write ...` previews writes by default.
- Applied `write_file`/`edit_file` requires `--allow-verify` and `--verify-command`; failed verification rolls the write back and records the failed tool result.
- `mew work <task-id> --ai` calls the resident model in THINK/ACT phases, records `model_turns`, executes one selected work-session tool per step, and feeds prior tool results into the next model prompt.
- Unit coverage proves a model-selected `read_file` is journaled and that the second model turn can see the first tool result.
- Unit coverage proves `mew work --ai` reuses an existing active session across separate invocations and can resume with prior tool output.
- Live Codex Web API dogfood in a temporary workspace fixed `calc.add`: read `calc.py`, applied an `edit_file` changing subtraction to addition, ran the configured verification command with exit code 0, then finished.
- `/work-session` in chat can start, show, and close native work sessions.
- `dogfood --scenario work-session` exercises session creation, `read_file`, `glob`, `run_tests`, dry-run `edit_file`, verified `write_file`, and workbench journal visibility.

Missing proof:

- Larger real-world coding tasks may still expose UX and context limits, but the Milestone 1 done criteria are satisfied.

Next action:

- Historical handoff complete. Keep current implementation work under Milestone 2's active focus rather than reopening Milestone 1.

## Milestone 2: Interactive Parity

Status: `in_progress`

Evidence:

- `mew chat` exists.
- Chat can inspect focus, status, workbench, agents, verification, writes, thoughts, runtime effects, doctor, and repair.
- `mew work --session --details` and `/work-session details` expose touched files, model turns, and tool-call summaries for the active work session.
- `mew work --session --diffs` and `/work-session diffs` expose a focused cockpit diff pane for recent write/edit previews and applied writes.
- `mew work --session --tests` and `/work-session tests` expose a focused cockpit test/verification pane for recent run output.
- `mew work --session --commands` and `/work-session commands` expose a focused cockpit command-output pane for recent command stdout/stderr.
- Compact resume bundles now include clipped stdout/stderr previews for recent commands, so live/reentry output can show key test or shell output without switching panes.
- Truncated command output previews now start on a line boundary, avoiding confusing partial-line fragments in the cockpit.
- `mew work --session --timeline` and `/work-session timeline` show a compact chronological model/tool event timeline for cockpit reorientation.
- `mew work --ai` streams progress events to stderr in normal mode, and with `--progress` when JSON output is requested.
- Work-session details now include a `Recent diffs` section for write/edit tool calls, including verification exit code and rollback state.
- Pending write approvals in resume output and inline `--prompt-approval` now include clipped diff previews with added/removed line counts, so the cockpit can support approve/reject decisions without opening a separate details view.
- Pending write approvals for changed `src/mew/**` files now carry advisory
  `pairing_status`. If the work session has no changed `tests/**` write/edit,
  approval cells and resume output show `missing_test_edit`; if a paired test
  write exists in the session, they show the paired test tool id.
- Changed `src/mew/**` work-session writes now add a `same_surface_audit`
  checkpoint to structured resume JSON, text resume output, and top-level task
  workbench reentry. The checkpoint prompts the resident to inspect sibling
  command/JSON/control peers on the same surface and remains `needed` until the
  latest post-edit relevant session note records the audit as checked, covered,
  reviewed, or out of scope.
- Work-session resumes now also emit `verification_confidence` for inferred
  paired tests on `src/mew/**` edits. The checkpoint distinguishes pending
  approval, stale verifier, failed/missing verifier, partial coverage, selector
  or node-id verifier, and broad verified states; live result panes, workbench
  reentry, and follow-status surface non-verified states for residents and
  observer agents.
- Dry-run `write_file`/`edit_file` tool calls can be explicitly applied with `mew work --approve-tool ...` or rejected with `mew work --reject-tool ...`.
- `mew work --approve-all` and `/work-session approve all ...` can apply multiple pending dry-run write/edit calls with the same explicit write and verification gates, reducing scaffold dogfood approval churn.
- `/work-session approve <tool-call-id> --allow-write ... --verify-command ...` and `/work-session reject <tool-call-id> ...` expose the same approval flow inside chat.
- `run_tests` tool calls now fail the work-session step when the verifier exits nonzero, and `/work-session details` includes a compact `Verification failures` section with command, cwd, exit code, stderr, and stdout context.
- `--progress` streams `run_tests`, `run_command`, and write-verification stdout/stderr lines to stderr for both manual work tools and `mew work --ai`.
- `/work-session ai ...` lets the user run a resident model work step from inside `mew chat`, using the same gates as `mew work --ai`.
- `dogfood --scenario work-session` now exercises chat `/work-session details` and `/work-session resume --allow-read .`, so cockpit visibility and live world-state resume are part of the recurring dogfood path.
- Native work reads now default to 50,000 characters, while model work-session context clips recent `read_file` text to a smaller page with `visible_chars`, `source_text_chars`, and a resume `next_offset`, reducing long-session prompt growth without losing the path to request more file content.
- Work sessions now expose read-only `git_status`, `git_diff`, and `git_log` tools behind the read gate, avoiding unnecessary `--allow-shell` for common coding context.
- `mew work --ai --act-mode deterministic` can skip the second model ACT call and normalize THINK output locally; the default remains model ACT to preserve the original THINK/ACT architecture.
- `mew work --session --resume` and `/work-session resume` produce a compact reentry bundle with touched files, commands, failures, pending approvals, recent decisions, and next action.
- The same resume bundle is included in work-mode model context so the resident model sees reentry state without reconstructing it from raw tool history.
- Work-session resume bundles now include compact `working_memory` when available, giving humans and future model turns a short hypothesis, next step, open questions, and latest verification state.
- Work-session working memory now also surfaces the latest tool observation and marks itself stale when a tool result landed after the memory was written; human-facing resumes label old plans as `stale_next_step`, preventing pre-tool `next_step` text from looking current after a live step.
- `mew work --session --resume --allow-read ...` and `/work-session resume --allow-read ...` add live git status and touched-file stats to the resume, and before any file is touched they show a shallow allowed-root snapshot for non-git workspaces. The same bounded world-state summary is injected into future work-model context when read access is allowed.
- Resume world-state git status now probes allowed read roots before falling back to the current directory, so reentry from a disposable cwd can still report the actual project repo state.
- `mew work --live` runs the resident work loop with progress and prints a resume bundle after each completed tool step.
- `mew archive` now archives closed work sessions, which gives large work-session histories a retention path after read/context limits increased.
- `read_file` supports `offset` and returns `next_offset`, letting the resident model page through files larger than one read window.
- Codex Web API SSE text deltas are forwarded even when the response omits a `content-type` header; `--follow` enables batched live `model_delta` thinking-pane output by default when the backend supports it.
- Malformed model JSON plans are treated as retryable model errors, so a single broken THINK/ACT response does not immediately kill a live/follow work session.
- Compact follow mode suppresses duplicate stderr delta progress while still preserving the model stream in the thinking pane and final preview, reducing token-by-token noise during real Codex Web API dogfood.
- Compact follow mode now suppresses the duplicate raw `stream_preview` when live model deltas were already shown, keeping the planning summary to model-stream metrics, summary, action, and reason.
- Compact follow mode now renders plan-shaped JSON streams as readable `summary_delta`, `reason_delta`, and `action_delta` lines instead of raw JSON tokens.
- `mew work --live` now prints a compact `thinking` pane before each action, showing the model summary and planned action before any tool runs.
- Live thinking panes now include a stable progress anchor (`step/max`, session id, task id, phase, and elapsed time), improving orientation during multi-step resident work.
- `mew work --live --compact-live` and `/work-session live --compact-live` skip full per-step resume blocks, leaving a lighter thinking/action/result stream for longer supervised runs.
- Compact live mode also keeps the final step report to command/cwd/exit summaries, avoiding stdout/stderr replay after the result pane.
- `mew work --live` now prints a compact `result` pane after each step, combining tool outcome, command output, phase, context pressure, pending approvals, and next action before the full resume block.
- Live result panes now surface compact work-session memory (`memory_hypothesis`, `memory_next`/`stale_memory_next`, and verification state), so compact follow keeps the resident model's current belief and next intended step visible without opening a full resume.
- Live result, resume, and workbench reentry panes now include a recurring-failure ribbon when the same tool/target/error repeats, making loops visible before the resident blindly retries the same broken action again.
- Live result panes now group `outcome`, `tools`, and `session`, include per-tool duration when timestamps are available, indent multiline command metadata consistently, and place command cwd/stdout/stderr directly under the tool result instead of a duplicate `summary: command` line.
- Live result panes suppress duplicate step/tool summaries, keeping command and tool outcomes easier to scan during dogfood.
- Live result panes now use compact read/search/glob summaries instead of dumping file text into the main cockpit stream.
- Live result panes now show bounded `search_text` context snippets around matches, so compact runs reveal what the resident model found without opening full session details or forcing conclusions from a single matched line.
- Final `mew work --ai` step reports now reuse compact tool summaries, so live runs do not reprint read-file bodies after the resume.
- `mew work --live` now prints the selected action, reason, key parameters, and tool-call id before execution, so the user can see what the resident model is about to do before the resume bundle appears.
- `/work-session live ...` provides a chat shortcut for the same live resident work loop, and pending write approvals in resume output include concrete `/work-session approve ...` and `/work-session reject ...` hints.
- Interactive `mew work --live` and `mew do` prompt inline by default for dry-run writes, with clipped diff preview, the approval verification command, `--prompt-approval` for non-TTY forcing, and `--no-prompt-approval` for explicit opt-out.
- `/work-session live` inherits the same interactive inline approval behavior from chat, and focused work help now documents the default plus `--no-prompt-approval`.
- Work-session resume output now reports context pressure (`tool_calls`, `model_turns`, recent chars, total chars, pressure), making large active-session growth visible to both humans and the model.
- A real Codex Web API dogfood run on task #21 used `mew work --live --act-mode deterministic` for two read-only steps; it selected `inspect_dir` then `read_file`, printed action/reason/resume/context pressure for each step, and made no repository writes.
- Work-mode control actions now have side effects: `send_message` writes to outbox, `ask_user` creates a normal question, and `finish` closes the work session while appending a final note to the task.
- Work-mode `finish` can now explicitly set `task_done: true` with a completion summary, separating "close this work session" from "mark the task done".
- Closed work sessions can still be inspected with `mew work <task-id> --session --resume`, so a finished resident work loop leaves a durable reentry/final-state artifact.
- `mew chat` now has `/continue ...` as a short one-step live command for the active work session, reducing the repeated `/work-session live ...` command burden.
- Work mode now supports a read-only `batch` action with up to five inspection tools in one model turn, journaling each tool call separately while keeping writes and shell commands outside batch mode.
- `glob` now skips common generated/cache directories such as `.git`, `.pytest_cache`, `.venv`, `__pycache__`, and `node_modules`, reducing noisy read-only navigation for resident models.
- Codex Web API dogfood for batch exposed a missing `read_file.path` failure, after which batch normalization was hardened to skip invalid read subtools; retrying the same dogfood task completed `inspect_dir` and `read_file README.md` in one model turn without writes.
- Work-session resume next-action selection now keys off the latest tool result, so an old failure no longer dominates the suggested next action after a successful retry.
- Chat live work now prints compact `Next controls` after live steps, keeping primary continue/follow plus resume/help visible while leaving full controls to startup and `/work-session`.
- `/continue` now remembers the previous live-step options for the current chat session and treats plain text as `--work-guidance`, so a user can steer the next resident step without retyping gates.
- `mew chat --work-mode`, `/work-mode on`, and `/c` reduce cockpit typing: text becomes `/continue` guidance, blank lines repeat only after a work step has run, and `/c` is a short continue alias.
- `mew work --follow` and chat `/follow` provide a compact continuous live loop that defaults to 10 steps, streams model progress, shows a separated model-stream preview in the thinking pane, and stops at existing resident boundaries such as finish, failures, stop requests, pending approvals, or user interrupt.
- Ctrl+C during `--follow` marks the current running model turn/tool as interrupted, records a durable resume note, and preserves chat continue options instead of leaving the next `/c` blocked by a stop request.
- When `--follow` or a multi-step live run reaches `--max-steps`, mew records a system work-session note with the final action/result and reentry hint, so bounded loops leave a durable explanation even if the model spent the final step observing.
- Pending write approval hints now reuse the latest session verification command when available, reducing the chance that an approval prompt shows only a placeholder.
- Write approval execution can now reuse the latest session verification command when `--verify-command` is omitted, while still requiring explicit write roots.
- Successful `run_tests` and write verification results now refresh the session default verification command, preventing reentry controls from preserving a known-stale verifier after a better command succeeds.
- Work-session resume next-action text now points at `/continue` and `mew work --live`, matching the current cockpit path instead of older `/work-session ai` guidance.
- `mew chat --help` now includes the slash-command reference, and `/help work` prints focused work-session reentry/continue commands.
- `mew chat` appends local input transcript entries to `.mew/chat.jsonl`, and `mew chat-log` plus `/transcript` expose recent chat inputs without mixing them into runtime activity output.
- `mew effects 10` and `mew runtime-effects 10` now accept positional limits like the chat command forms, reducing CLI/chat grammar mismatch.
- `mew do <task-id>` now provides a compact supervised resident coding entrypoint over `mew work --live`, defaulting to deterministic ACT, read/write roots at `.`, and an auto-detected verification command when available.
- Model-selected `run_tests` now refuses resident mew loops such as `mew do`, `mew chat`, `mew run`, and `mew work --live`, preventing a supervised session from treating another resident loop as its verifier.
- `mew work --session`, `mew work --session --resume`, and `/work-session` now fall back to recent work sessions when no session is active, including exact CLI and chat resume hints.
- `mew work --session --json` and `mew work --session --resume --json` expose the same recent-session summaries for model-facing or scripted reentry.
- Active `mew work --session --json` and `--resume --json` now include structured `next_cli_controls`, preserving continue/stop/resume/chat commands for machine readers.
- Active `mew work --session`, active `/work-session`, and normal `mew chat` startup now surface next controls for continuing, stopping, resuming, or entering chat.
- Text resume surfaces (`mew work --session --resume` and `/work-session resume`) now print controls after the compact resume bundle.
- Quiet `mew chat --no-brief` startup still surfaces active work-session controls, so suppressing the brief does not remove the reentry affordance.
- `mew focus` / `mew daily` now surface active work sessions with phase, next action, resume command, and one-step continue command, making task reentry visible from the quiet daily view.
- `mew focus` now includes active work-session working memory when present, so the quiet daily view can show the resident model's current hypothesis and memory next step before opening a full resume.
- `mew focus` now marks stale work-session memory and suppresses stale `memory_next` text when later tool or model activity means the resident should refresh before relying on it.
- `mew focus` now reuses the active work session's saved model/gate/verify/approval defaults in its continue/follow commands, so daily reentry stays copy-paste runnable.
- `mew digest` exposes the chat digest as a top-level command, making recent autonomous activity review available without entering the chat REPL.
- `mew activity --kind ...` now scopes activity to task kind and includes native work-session turns, notes, and tool calls, so the coding cockpit has an observable activity stream without unrelated passive history.
- `mew session` JSONL requests for `status`, `brief`, and `activity` now accept the same `kind` scopes as the CLI/chat surfaces, keeping future frontends aligned with the cockpit.
- Active sessions remember start/live read/write/verify/model/approval options and reuse them in later CLI/chat controls, reducing repeated gate flag entry after reentry.
- Chat work-session Inspect and Advanced controls now reuse the active session's saved/default read roots instead of falling back to `--allow-read .`, keeping scoped cockpits from suggesting broader or invalid read gates.
- Chat `/work-session resume <task> --allow-read <root>` now carries that explicit read root into the printed Next controls and cached `/c` options, so scoped resume does not immediately suggest broader `--allow-read .` follow-ups.
- Scripted non-interactive `mew chat` defers startup controls when the first input is a work-session/continue command, so scoped command results are not preceded by generic active-session controls.
- Manual `run_tests` / `run_command` calls no longer store the parser's default `--path .` as a touched file, so non-file actions do not create noisy `.` world-state warnings.
- Missing-executable verification failures now keep JSON `exit_code: null` but render human-facing resume/commands/tests output as `exit=unavailable` with `executable not found: ...` context.
- Missing-executable command records now normalize stderr to `executable not found: ...`, so focused command/test panes no longer leak raw Python `[Errno 2]` text.
- Live work progress now flushes stdout before stderr progress lines, reducing apparent reordering where model delta prose could appear after `ACT ok` progress in mixed streams.
- Follow/live max-step boundary notes are shorter and replace older system max-step boundary notes in the same session, reducing repeated reentry material while keeping model/tool history for audit.
- Partial reentry-option updates now preserve existing read/write/verify/model defaults and add new explicit roots, so a later read-only command does not erase previously useful write or verification gates.
- CLI live controls now prefer the current command's explicit tool gates over saved broader defaults, so read-only reentry does not suggest stale write, shell, or verification permissions.
- Starting a new work session for a task with only closed sessions now clones the latest closed session defaults, preserving cockpit gates across closed-session restart.
- CLI/chat controls now show both one-step continue and bounded `--max-steps 3` continue paths, making short autonomous runs discoverable without removing the safer single-step path.
- Multi-step work loops stop at pending dry-run write approvals, preserving the human review boundary while allowing bounded autonomous read/verify progress.
- Fresh `mew chat` `/continue <guidance>` now falls back to the active work session's stored defaults when the current chat state has no cached options, preserving read/auth/model gates after reentry.
- Default `mew work --session` and `/work-session` tool-call views compact read/search/glob results, keeping reentry quiet even when prior `read_file` calls captured large text.
- Work-session world-state formatting no longer labels nonzero `git_status` as `(clean)`; it surfaces stderr/stdout so non-git workspaces are not misrepresented.
- Work-session world-state git summaries filter `.mew/` internal state noise, so reentry does not make mew's own persistence look like project dirt.
- `mew next` and passive next-move messages now route unplanned coding tasks to `mew work <task-id> --start-session`, matching native hands as the first execution path.
- Chat work-session parsing accepts task-first resume order such as `/work-session 26 resume --allow-read .`, reducing command-order friction during reentry.
- Work-session resume bundles now expose a compact `phase` such as `idle`, `awaiting_approval`, `running_tool`, `planning`, `interrupted`, or `closed`, giving the cockpit and resident prompt a clearer state label.
- The same phase is visible in normal workbench/work-session views, so the user does not need to open the full resume just to know the current state.
- `mew work --live` now prints a resume bundle after control actions such as `finish`, so live sessions end with the closed-session state visible instead of only an action line.
- `mew work --live` now preflights missing tool gates and prints concrete reentry controls before calling the model, avoiding a wasted model turn that can only fail on permissions.
- Native work sessions now support a stop request (`mew work --stop-session` and `/work-session stop`) that is consumed at the next model/tool boundary before another model call starts.
- Stop requests leave their reason in the work report and resume bundle after they are consumed, preserving why a live loop paused.
- Work model turns are now journaled as `running` before THINK/ACT starts, so resume can show `phase=planning` during an in-flight model call and repair has real state to interrupt if the process dies.
- Stop requests are checked again after THINK/ACT, immediately before a selected tool starts, and between batch subtools, so a pause request prevents the next tool call at real execution boundaries.
- CLI `mew work --live` runs now end with `Next CLI controls`, showing continue, stop, resume, and chat commands for the current session.
- `dogfood --scenario work-session` now covers stop request recording and `phase=stop_requested` resume output.
- Stop-requested sessions now suppress live/follow continue commands in `Next CLI controls`, so the controls no longer contradict a resume whose next action is to stay paused.
- `dogfood --scenario work-session` now also covers user session notes appearing in resume output.
- Model-selected `read_file` now defaults to a smaller 12,000-character page, and model-selected `git_diff` defaults to diffstat unless full diff is explicitly requested, reducing the chance that a broad read-only batch bloats a resident session.
- Work-mode prompts now tell the resident model that current capability gates are authoritative, reducing stale permission-failure loops where it asks for a flag already present.
- Work-mode prompts now tell the resident model that `run_command` is shlex-parsed without a shell, reducing failed probes that use `&&`, pipes, or redirection.
- Work-mode prompts now steer code navigation toward `search_text` before broad `read_file`, then line-window reads from search hits, reducing wasted context in compact live dogfood.
- Work-mode prompts now require exact `edit_file` old/new strings, and deterministic action normalization turns incomplete `edit_file` attempts with a path into a safe `read_file` re-observation instead of a failed write tool call.
- Work-session resumes now include structured `suggested_safe_reobserve` metadata for the latest failed tool, turning edit/read/search/git/command failures into explicit safe re-observation or output-review suggestions for the next model turn and human resume.
- Nonzero `run_command` exits now surface in work-session failure summaries and `phase=failed` without treating the command launch itself as a tool crash.
- Work-mode prompts now treat one-shot `--work-guidance` / `/continue <guidance>` as the current instruction for that turn, reducing early `finish` decisions based only on older session notes.
- Work-session model turns now retain a clipped `guidance_snapshot` copy of that one-shot guidance, and resume, timeline, details, and model context expose it for reentry and audit without making it current guidance again.
- Work-session guidance previews now clip on a one-line word boundary, keeping recent decision/reentry guidance readable instead of corrupting intent with mid-word truncation.
- `mew next --kind coding`, `mew focus --kind coding`, and chat `/next coding` / `/focus coding` expose the next coding-shell move without being blocked by unrelated open research or personal questions.
- `mew self-improve --native`, `mew self-improve --start-session`, and chat `/self native ...` / `/self start ...` create/reuse a self-improvement coding task without forcing the older programmer-plan path, then print or start the native work-session path.
- When the coding queue is empty, `mew next --kind coding` / `mew focus --kind coding` now suggest starting a native self-improvement session rather than going silent.
- `mew work --approve-tool` now accepts exact new-file write roots and missing directory roots for `create=True` writes, so independent experiments can start from an empty path without broadening the write gate to `.`.
- `mew code --no-verify` now records verification as explicitly disabled, so approval no longer reuses stale successful verification commands after the user cleared verify defaults.
- `mew work <task-id>` now surfaces the latest work-session write and verification ledgers, including closed sessions, so the task workbench no longer says `Verification (none)` / `Writes (none)` after verified native work.
- `mew work <task-id>` now surfaces a compact `Reentry` block with work-session working memory, recent user/model notes, latest decision guidance, task notes, and resume/chat hints, making the top-level task workbench a usable front door for resident continuation.
- `mew verification` and `mew writes` now include work-session tool calls with stable `source`, `id`, `ledger_id`, and session-qualified labels such as `work25#113.verify`, making native work audit trails visible outside the full session view.
- `mew status --kind ...` and `mew brief --kind ...` now scope counts, unread task-linked messages, questions, attention, task queues, next moves, and brief ledgers by task kind; kind-scoped briefs suppress unrelated global activity/thought/step history.
- Human-role E2E round 3 verified that `brief --kind coding`, `status --kind coding`, missing-parent write-root errors, and global work-session ledgers all behave as intended without tracked file edits.
- `mew chat --kind ...` now scopes the startup brief, unread outbox, and slash-command views; `/scope` can switch or clear the active chat kind, and `mew listen --kind ...` scopes passive outbox observation.
- Chat `/work` now respects the active kind scope when selecting a default task, so a `mew chat --kind coding` cockpit no longer silently opens unrelated research work.
- Chat startup, `/work-session`, `/work-session live`, `/work-session resume`, `/work-session timeline`, approvals, rejections, stop, and notes now respect the active chat kind scope when no explicit task id is supplied.
- Chat `/continue` now accepts stored options followed by plain guidance, preserving reusable gates like `--auth` / `--allow-read` while treating the trailing text as one-shot work guidance.
- `mew work --live` now defaults to deterministic ACT, so the common live path uses one model call per step; model JSON/text deltas are quiet by default and remain available with explicit `--stream-model`.
- `read_file` now supports `line_start` / `line_count` through both CLI tools and resident model actions, letting the model jump from `search_text` line numbers to the relevant source region instead of rereading file offset 0.
- Invalid line-based `read_file` requests now fail clearly (`line_start must be >= 1`), while out-of-range line reads return structured EOF metadata and summaries like `lines=99-EOF`.
- Line-window reads now distinguish `has_more_lines` from `truncated`, so a fully returned requested window can expose `next_line` without falsely saying the returned text was truncated.
- Compact work-session timelines now preserve failed/interrupted tool errors instead of formatting failed `read_file` calls as empty offset reads.
- Failed/interrupted timeline summaries now avoid duplicate labels such as `read_file failed: read_file failed: ...`.
- Generated cockpit commands now prefer `./mew ...` when the current checkout has an executable local wrapper, making next controls copy-paste runnable in source worktrees where `mew` is not installed on `PATH`.
- Text outbox/listen/chat history views now clip very large message bodies and point to `outbox --json` for the full payload, reducing the chance that historical agent payloads swamp the cockpit.
- `edit_file` now permits small exact replacements in large files by limiting replacement/delta size instead of rejecting based on total edited file size.
- `mew work --live` dogfood task #44 used Codex Web API as a resident buddy: it exposed the missing line-based read path, exposed the large-file small-edit blocker, retried after those fixes, produced dry-run edit #133, and approved it with `uv run pytest -q`.
- `dogfood --scenario work-session` now covers line-based `read_file`, large-file dry-run `edit_file`, no-trailing-newline diff stats, focused diff previews, and focused test output.
- `dogfood --scenario chat-cockpit` now exercises a scripted `mew chat --kind coding` session with `/scope`, `/tasks`, `/work`, scoped startup controls, scoped `/work-session`, and chat transcript logging, making the scoped cockpit path part of deterministic recurring dogfood.
- Focused work-session panes now compose cleanly, avoid duplicated `run_tests` entries when `--tests --commands` are combined, and expose historical diff timestamps as both `finished_at` and `recorded_at` in JSON.
- Batch action rendering now includes read-window fields such as `line_start`, `line_count`, and `max_chars`, keeping compact text summaries aligned with the underlying model/tool JSON during dogfood.
- `mew self-improve --help` now documents the native work-session flow directly, reducing the chance that a resident or human reentry chooses the older programmer-plan path by accident.
- Compact follow/live model stream labels are now shorter (`summary_delta`, `reason_delta`, `action_delta`), reducing mechanical cockpit noise while keeping streamed THINK progress visible.
- Diff previews now use full, unclipped diff stats even when the stored diff body is clipped, so huge single-line edits no longer appear as false `+0 -0` changes.
- `mew dogfood --cleanup --workspace ...` now reports `cleanup_skipped_reason=explicit_workspace` instead of silently keeping the user-provided path, and native self-improvement output now prints the resolved `work cwd`.
- When scoped chat has multiple active matching work sessions, implicit `/work-session resume` now names the selected task and points to `/work-session resume <task-id>` for explicit selection.
- Write/edit diff stats now count line replacements from the before/after text rather than parsing unified diff text, covering no-trailing-newline replacements that `difflib` renders on one physical line.
- `dogfood --scenario chat-cockpit` now covers `mew code --quiet`, preserving the silent scripted cockpit startup path.
- `mew code --help` now describes the coding-cockpit create/reuse flow and common quiet/read-only entry commands.
- Read-only `codex-ultra` investigations of Claude Code and Codex CLI, followed by a `claude-ultra` product decision pass, identified stable transcript cells as the next enabling cockpit primitive; the findings are captured in `docs/COCKPIT_REFERENCE_NOTES.md`.
- `src/mew/work_cells.py` builds stable cockpit cells from existing work-session state, including `model_turn`, `tool_call`, `command`, `test`, `diff`, and `approval` cells with durable ids, statuses, previews, details, and command/test tails.
- `mew work --cells --json`, text `mew work --cells`, and chat `/work-session cells` expose the same cell model for reentry and future UIs.
- `mew work --follow` now prints newly added cells after each live step, so follow-mode output has stable model/tool anchors instead of only transient stream text.
- Real read-only `mew work 86 --follow --auth auth.json --allow-read . --act-mode deterministic --max-steps 2` dogfood used the new cells, found that leading raw ids/timestamps made rows noisy, and the formatter was then adjusted to put stable ids and timing in metadata lines.
- `dogfood --scenario work-session` now checks both CLI and chat cell panes, including model, test, diff, and pending approval rows.
- Command/test cells now include command, cwd, exit status, elapsed time, stdout/stderr line and character counts, output tails, explicit no-output rows, timeout/error metadata, and a `full_output` hint back to `mew work <task-id> --tests` or `--commands`.
- Approval cells now carry structured `operation`, `target`, and `actions`; pending write/edit approvals expose approve-once, reject, and reject-with-feedback commands, and missing shell/verification gates can surface as required approval cells.
- Direct `mew work 86 --cells` dogfood verified both approval anchor paths in a real ignored state session: a failed shell-gated command produced a required `shell_command` approval cell, and a dry-run write produced a pending `file_write` approval cell with reject-with-feedback guidance.
- Diff cells now carry structured `operation`, `target`, `diff_stats`, `dry_run`, `applied`, and `approval_status` metadata plus a `full_diff` hint back to `mew work <task-id> --diffs`, so write previews are no longer just raw clipped patches.
- `mew work --follow` now treats cells as the primary per-step result display: follow still shows thinking/progress, but it suppresses the older action/result panes whenever new cells are available.
- `codex-ultra` human-role cells dogfood then found and drove fixes for pending-approval CLI controls, concrete verifier hints in approval cells, resolved shell/verify gate cells, failed verify-gate visibility in `--tests`, and unavailable approval actions on closed sessions.
- Follow mode now prints a `Work active cell` for the running model turn and running tool call before completion, then prints the durable completed cells after the step finishes.
- Real Codex Web API dogfood tasks #87 and #88 exercised the cell stream itself: #87 identified noisy completed-cell dumps after batch actions, then #88 verified compact completed cells with a `--cells` detail hint after that fix.
- Follow planning output now uses a compact `plan: <action>` line plus model-stream stats instead of repeating the full live planning summary/reason block.
- `mew work --follow --quiet` now suppresses default `mew work ai:` progress lines unless `--progress` is explicitly passed, leaving a cleaner stdout-only cell stream for humans and scripted captures.
- A fresh `codex-ultra` human-role compact follow test verified active cells, compact completed cells, pending approval controls, approval apply/reject, and closed-session unavailable approvals; its remaining findings are now addressed by concrete resume verifier hints, retryable failed-approval cells, and raw-diff-free compact final reports.
- Chat `/follow --quiet` now accepts the same quiet flag as the CLI and preserves it in cached continue options, making attach-style chat probes less noisy.
- Failed command/test cells now expand their stderr/stdout tails instead of using the success-path 8-line clip, reducing the need to open `--tests` just to see the actual failure.
- `mew work --steer "..."` and `/work-session steer ...` queue one-time guidance for the next live/follow step; pending steer is exposed in session/resume/live output, then injected into model guidance, recorded as a work-session note, and cleared only after model planning succeeds. Stop requests and model/API errors preserve pending steer for the next actual step.
- `mew work --steer` now refuses ambiguous taskless routing when multiple work sessions are active and prints task-qualified steer commands instead, preventing a queued instruction from landing in the wrong resident session.
- `Next CLI controls` now include the `mew work <task-id> --steer <guidance>` lane, making the mid-loop control discoverable from live/follow output instead of only from chat help.
- Queued follow-ups are surfaced in consumption order, with total/truncation metadata, so a long queue does not mislead the next-step preview.
- Idle `interrupt_submit` sessions now render "submit pending interrupt" controls instead of generic pause controls, while still waiting at a boundary when a model/tool step is actually running.
- `mew code --help` now includes direct reentry examples for reviewing a work-session resume and reopening coding-scoped work-mode chat.
- `mew work --cells --cell-tail-lines N` provides configurable command/test tail output, reducing noisy cell panes without changing the full `--commands`/`--tests` detail views.
- `mew work --reply-file` now supports `approve` and `approve_all` observer actions for pending dry-run writes, reusing existing write/verify gates and rewriting the follow snapshot after completion.
- `.mew/follow/latest.json` now includes top-level `pending_approvals`, `supported_actions`, and a context-aware `reply_template` for external observer UIs and models.
- `mew work --live/--follow --max-steps 0` refreshes `.mew/follow/latest.json` without spending a model turn, so observers can publish pending approval state on demand.
- Pending approval snapshots now include `cli_approve_hint` and `cli_reject_hint` alongside chat-style hints for external observer agents.
- `mew work --follow-status --json` reports snapshot freshness, heartbeat age, producer PID liveness, and pending approval count without requiring observers to parse raw snapshot files.
- `mew work --follow-status --json` now includes `producer_health` and `suggested_recovery`, pointing observers at task selection, zero-step snapshot refresh, resume inspection, safe read auto-recovery, human review, or replanning as appropriate.
- `mew work --live/--follow --max-steps 0 --json` can refresh a snapshot and print a structured refresh report without spending a model turn.
- `mew task add/list/show/update/done --json` provide task lifecycle data without text parsing, and `mew observe --json` aliases passive workspace perception for observer-oriented naming.
- `mew self-improve --start-session` now prints `resume: mew work <task-id> --session --resume --allow-read .` next to its continue/follow commands.
- `mew metrics --kind coding` now reports observation-first reliability and
  latency signals with diagnostic samples for approval friction, verification
  failures, slow model resumes, approval-bound waits, and high-idle sessions.
  Approval-bound dry-run wait is split from true model-resume latency, so
  human review time no longer masquerades as runtime slowness.
- `mew focus --kind coding` now surfaces a concise `Recent friction` section
  from the same metrics diagnostics, making approval rejection reasons,
  verifier failures, approval-bound waits, and slow model-resume samples part
  of the default reentry surface instead of a separate command the resident has
  to remember.
- High-idle metrics samples now include tool/model-turn/note counts plus the
  latest work-session note preview, so long wall-clock gaps can be interpreted
  as manual/out-of-band work when that is what happened.
- `mew dogfood --scenario m2-comparative` now writes JSON and Markdown
  protocol artifacts under `.mew/dogfood/`, requiring both a `mew code` run and
  a fresh Claude Code / Codex CLI run, friction counts, resume behavior,
  resident preference, and explicit mapping to all three M2 Done-when criteria.
- The first recorded M2 paired dogfood is preserved in
  `docs/M2_COMPARATIVE_DOGFOOD_2026-04-19.md`. For a small local protocol
  edit, fresh `codex-ultra` in a detached worktree completed the change more
  smoothly than mew. The mew leg found the right context but hit a paired-test
  steer plus approval-verification rollback loop: the guard asked for a test
  edit first, while approval verification required that test-only edit to pass
  before the matching source edit existed.
- Paired-test steering now discovers existing tests before falling back to a
  convention path. This addresses the follow-up blocker from that dogfood where
  `src/mew/cli.py` steered the resident toward nonexistent `tests/test_cli.py`
  instead of the existing dogfood parser coverage in `tests/test_dogfood.py`.
- The B5 follow-up comparative dogfood is recorded in
  `docs/M2_B5_COMPARATIVE_DOGFOOD_2026-04-20.md`. In a disposable worktree,
  mew completed a `test_discovery` task-shape change with continuity `9/9`,
  one deferred paired-test approval, and passing broad verification. The paired
  steer correctly suggested `tests/test_dogfood.py`. A fresh `codex-ultra` run
  completed the same non-interrupted task with less ceremony and judged
  `fresh_cli_preferred`.
- The interruption-shaped follow-up comparative dogfood is recorded in
  `docs/M2_INTERRUPT_COMPARATIVE_DOGFOOD_2026-04-20.md`. In a disposable
  worktree, mew completed an `approval_pairing` task-shape change after an
  intentionally failed stale file read was preserved in the work session. The
  resulting mew-side interruption gate was `proved` with continuity `9/9`,
  preserved recovery risk, a runnable next action, one deferred paired-test
  approval, and passing broad verification. The matching fresh `codex-ultra`
  run completed the same narrow task, but its interruption gate remained
  `unknown`, so the combined resident preference is `inconclusive`.
- `mew dogfood --scenario m2-comparative --m2-comparison-report` now accepts a
  natural flat fresh-CLI report shape with `task_summary`, `verification`,
  `friction_summary`, `preference_signal`, and a top-level
  `interruption_resume_gate`, in addition to the nested `fresh_cli` shape.
- The process-stop follow-up comparative dogfood is recorded in
  `docs/M2_PROCESS_STOP_COMPARATIVE_DOGFOOD_2026-04-20.md`. In a disposable
  worktree, `mew work --follow` was interrupted with Ctrl-C and recorded
  `stop=user_interrupt`; the task then completed in a second work session with
  passing focused and broad verification. Because interruption evidence and
  verification evidence were split across sessions, the M2 protocol now accepts
  `--mew-session-id task:<id>` and evaluates task-chain evidence. The resulting
  mew-side gate is `proved` with `risk_session_ids=[1]` and
  `verification_session_ids=[2]`. The matching fresh `codex-ultra` run
  completed the narrow task, but was not interrupted, so the combined resident
  preference remains `inconclusive`.

Missing proof:

- Model delta streaming and a separated thinking-pane preview now exist and work against the live Codex Web API, but the reasoning/status pane still needs longer dogfood and polish before it is comparable to Claude Code / Codex CLI.
- `mew chat --work-mode`, `/c`, and bounded `/follow` now reduce cockpit friction, but the broader resident coding loop still needs more long-session dogfood before it can replace a mature coding CLI.
- Batch support removes the strict one-tool limit for read-only inspection, but applied writes, shell commands, and verification still run one tool at a time.
- Large active-session growth is now visible and recent file reads are clipped in model context, but there is no global prompt budget enforcement or semantic compaction of noisy work-session history.
- Live coding work session UX now has focused help, one-step `/continue` and `/c`, reusable options, chat work-mode with guarded blank repeats, bounded follow loops, inline guidance capture, boundary stop requests, interrupt and max-step reentry notes, recent-session reentry, compact chat controls, focused diff/test panes, scoped status/brief views, and global work-session ledgers, but it is still not a full REPL-style coding cockpit with polished reasoning/status flow.
- `mew work --follow` now has stable cell anchors, running model/tool cells, and duplicate action/result suppression, but it still needs longer real task dogfood before treating the cell stream as the default cockpit contract.
- The first process-stop comparative run proved the mew-side task-chain gate,
  but it did not yet prove a resident preference over a matching interrupted
  fresh CLI run. It also exposed remaining approval/deferred-verification
  ceremony in multi-edit test-first flows.
- TTY redraw, cell-level collapse/expand, and hard mid-stream cancellation are not implemented.

Next action:

- Reduce the paired approval / deferred-verification ceremony found during the
  process-stop run, or run a matching interrupted fresh-CLI comparison. The
  broader cockpit latency slice remains the other active M2 option.

## Milestone 3: Persistent Advantage

Status: `in_progress`

Evidence:

- Durable state tracks tasks, questions, inbox/outbox, agent runs, step runs, thoughts, and runtime effects.
- Context builder includes recent runtime effects and clipped summaries.
- Project snapshot and memory systems exist.
- Native work sessions now have task-local resume bundles with files touched, commands, failures, pending approvals, working memory, recent decisions, next action, and context pressure.
- Top-level task workbench reentry now includes the latest unresolved
  work-session failure as an explicit `risk:` line, including `retry_failed`
  recovery records, while hiding superseded recovered failures. This preserves
  open risk across compact reentry without forcing the user or resident model
  to reopen the full session resume first.
- `mew focus` active-session entries now use the same unresolved failure risk
  formatter, so the daily quiet reentry surface shows failed verification/work
  risk alongside age, working memory, and continue/follow controls.
- State saving now uses an in-process `RLock` around the existing file lock and
  unique pid/thread/monotonic temp names for both state and backup writes,
  reducing live-output mirror races during concurrent save paths.
- `search_text` now accepts resident-style space-separated include glob strings
  and expands relative directory globs to `**/...` variants, so a model can
  search `src/** tests/** docs/**` from an absolute workspace path instead of
  getting a silent zero-match result.
- `mew self-improve --json` now returns structured task/plan/run/session data;
  in native start-session mode it includes work-session controls for continue,
  follow, status, and resume.
- The resident work model receives the resume bundle in its prompt, so separate invocations can continue from task-local work history.
- Recent work model turns now feed bounded prior THINK/reasoning fields back into the next prompt, so the resident model can carry observations and hypotheses between steps instead of relying only on raw tool output.
- THINK prompts now ask the resident model to persist a compact `working_memory` object for future reentry; old sessions fall back to latest turn summary/action reason plus verification state.
- Working memory treats observed verification results as authoritative over model-written verification claims and marks the digest stale when later model turns did not refresh it.
- Work mode now has a `remember` control action that records durable session notes surfaced in resume bundles and future model context.
- Humans can add the same durable work-session notes with `mew work --session-note` or `/work-session note`, and task-qualified `mew work <task-id> --session-note ...` can annotate the latest closed task session after review, making persistent guidance distinct from one-shot `/continue` guidance.
- Work model context now carries a bounded `session_knowledge` digest for older tool calls that have fallen out of the full recent tool-call window, preserving what was inspected without raw file contents.
- Work model context now includes a bounded live `world_state` summary when read access is allowed, so resumed work can compare durable history with current git/file metadata.
- Work-session resume bundles now include bounded `memory.deep.preferences`
  items as `user_preferences`; the same resume flows into the native work THINK
  prompt and `.mew/follow/latest.json`, making durable human preferences
  visible to both the resident model and external observer agents after
  reentry. The deterministic work-session dogfood scenario now also checks that
  resume and zero-step follow snapshots preserve those preferences.
- Typed/scoped memory has a file-backed MVP for the 5.12 reference-adoption
  slice. `mew memory --add --type ... --scope ...` writes frontmatter-backed
  entries, `mew memory --search` can filter by memory type/scope, legacy
  shallow/deep state memory is still searchable as `unknown`, and
  `dogfood --scenario memory-search` verifies private user memory can be
  recalled separately from legacy state memory.
- Active typed recall now enters resident startup context. Work-session resume
  includes an `active_memory` bundle from `.mew/memory`, user memories are
  carried as always-relevant recall, project/reference/feedback memories are
  selected by current task/session terms, and the THINK prompt explicitly tells
  the resident to use that typed recall while still verifying project facts
  before code changes. `dogfood --scenario work-session` verifies typed user
  and project memories appear in resume.
- Real Codex Web API dogfood in a temporary workspace proved the active recall
  can affect a resident turn. A typed project memory told the resident to
  inspect `README.md` first for the "Active Memory API Proof" task; the model
  selected `read_file README.md` and its decision summary explicitly cited the
  active project memory as the route.
- `mew memory --active --task-id ...` now exposes the exact typed-memory bundle
  that would be injected for a task/session, giving humans and observer agents
  a debug surface for active recall without opening raw state files.
- Native self-improve controls now include that same active-memory command, so
  the standard continue/follow/status/resume/chat handoff also exposes the
  resident recall bundle before work starts.
- Active recall debug output now surfaces `score=` and `matched=` in text mode,
  and task-term extraction filters self-improve boilerplate, constraints, and
  recent commit hashes before matching typed memories.
- Recent read-file results are clipped for model context with a resume offset, so long-running sessions keep enough local detail to continue without repeatedly embedding large source files.
- Work model context now enforces a budget by shrinking recent tool/turn windows and adding a `context_compaction` note when the work-session JSON grows too large.
- Work model context now clips task notes by recent lines and tail length, so recent recommendations and corrections survive when old self-improvement notes have accumulated.
- Work-session `finish` notes now prefer explicit action summaries over boundary reasons, keeping task notes useful for future reentry.
- `mew task show` and chat `/show` now clip long task notes to recent lines, so human reentry views do not drown in old self-improvement session endings.
- Work-session write and verification records now appear in global `mew writes` / `mew verification` ledgers with stable identifiers, so task-local work history is discoverable without reopening raw session JSON.
- Kind-scoped `mew status --kind coding` and `mew brief --kind coding` provide a calmer task/coding reentry view that is not dominated by unrelated research questions or unread outbox.
- A controlled no-input `--passive-now --autonomy-level propose --echo-outbox`
  run in `/tmp/mew-passive-outbox-proof.tgg0Oo` created a user-visible outbox
  question for a ready coding task, proving passive proposal output can happen
  when stale unanswered questions are not already blocking the loop.
- Real-repo passive proof after the stale-question cadence fix emitted one
  user-visible outbox question instead of staying silent: old task question #3
  was deferred with a reason, new task question #5 was opened, and the same
  cycle kept other task questions as `wait_for_user`.
- Question reentry views now expose old open prompts as `waiting=...`; all-question
  listings such as `mew questions --all` expose deferred stale prompts with
  `defer_reason=...`, so humans can see why passive work is waiting or why an
  older prompt was superseded.
- Active work sessions in `mew focus` now include `last_active` age and
  `focus --json` exposes `updated_at`, `inactive_hours`, and `inactive_for`,
  so day-scale reentry makes the age of resident work explicit instead of
  silently looking fresh.
- `mew dogfood --scenario resident-loop` now starts a real resident runtime,
  lets it process startup plus passive ticks, stops it cleanly, and checks that
  passive effects and stdout summaries were recorded.
- Repeated passive waits on the same unresolved question now compact into a
  single thought journal entry with `repeat_count`, preserving cadence evidence
  without flooding long-running memory.
- Ready coding task questions now point to the native coding cockpit with
  `mew code <task-id>` instead of the older agent/command/backend workflow,
  and interrupted-focus dogfood checks that routing.
- Autonomous act-level runtime can now start a native work session for a ready
  coding task when `--allow-native-work` is explicitly enabled. The
  `native-work` dogfood scenario proves this starts a `mew code` reentry path
  without launching an external agent run or leaving a redundant ready-task
  question open; the start message remains visible to attach/outbox listeners,
  and the created session inherits current runtime read/verify/model defaults
  plus a runtime provenance note without stale write/verify authority from
  older sessions. `mew focus` reuses those same saved defaults for active
  session next/resume/continue/follow commands, and direct `mew work <task>
  --live` reentry applies saved session defaults to planning/tool execution.
- Autonomous act-level runtime can now advance runtime-owned native work
  sessions on later passive ticks when `--allow-native-advance` is explicitly
  enabled. Each advance runs one bounded `mew work --live --max-steps 1`
  subprocess, preserves the runtime auth/model/read/write/verify defaults,
  disables inline approval prompts, skips human-started/running/approval-waiting
  sessions, records outcome notes, and is summarized in dogfood metrics. Real
  Codex Web API dogfood in temporary workspaces completed two passive native
  work advances after startup, including read-only model/tool turns and runtime
  verification.
- The passive native-work advance path is now covered by a deterministic
  `native-advance` dogfood scenario inside `dogfood --scenario all`. The
  scenario uses a fake `MEW_EXECUTABLE` to prove passive ticks invoke one quiet
  `mew work --live --max-steps 1` step without spending model tokens, and
  runtime status now preserves a bounded skip-reason history for later dogfood
  diagnosis.
- `dogfood --scenario day-reentry` now proves an active work session aged by
  more than a day can be reentered through `mew focus`, `mew work --session
  --resume --allow-read .`, and `mew activity --kind coding` while preserving
  working memory, durable notes, touched-file world state, and old work events.
- Failed passive native-work advances no longer cause blind retries. If the
  last native advance failed for the same runtime-owned session and no newer
  session activity has occurred, the next passive tick records
  `previous_native_work_step_failed` and leaves recovery to the visible
  runtime/model path or a human/manual session update.

Missing proof:

- Task-local resume and scoped reentry views are proven across a deterministic
  day-scale interruption/resume cycle, but not yet across real multi-day
  resident runtime operation.
- There is no semantic compaction strategy for noisy long-running work-session history beyond archive retention, explicit `remember` notes, automatic working-memory digests, older-tool digests, read-result clipping, and budgeted recent-window compaction.
- Watcher-driven passive output now has controlled, real-repo one-shot,
  short resident-loop, native-work-start, and real API native-work-advance
  proofs, but not yet a long-running cadence proof across several hours or days.

Next action:

- Move back to the broader cockpit/recovery roadmap, while continuing to watch
  active recall quality during real dogfood and only expanding memory scoring
  when the selected memories are visibly wrong or opaque.
- After typed memory exists and the state/resume schema is less volatile,
  revisit 5.11 AgentMemorySnapshot. Use the day-scale reentry proof as the
  basis for longer resident cadence testing, but do not let that defer the
  memory-scope foundation indefinitely.

## Milestone 4: True Recovery

Status: `in_progress`

Evidence:

- Runtime effects persist lifecycle status.
- `mew doctor` detects incomplete runtime cycles/effects.
- `mew repair` can mark unfinished effects as `interrupted`.
- Interrupted effects receive `recovery_hint`.
- Runtime effects now record user-visible `outcome`.
- `mew repair` now marks stale `running` work-session tool calls and model turns as `interrupted` with a recovery hint, so native work resumes do not keep ambiguous in-flight state forever.
- Interrupted work-session items surface as `phase=interrupted` in the resume bundle with a conservative next action.
- `mew work --recover-session --allow-read ...` can retry interrupted read-only work tools and mark the original interrupted call as superseded; `mew work --session --resume --allow-read ... --auto-recover-safe` and `/work-session resume --allow-read ... --auto-recover-safe` can opt into the same safe read/git retry while showing the refreshed resume. Safe retries record `world_state_before`; write/shell/verification recovery remains gated by human review.
- Interrupted work-session resumes now include a recovery plan that classifies retryable read/git tools, replannable model turns, and side-effecting work that needs human review.
- Retryable read/git recovery plan items now include manual, automatic CLI, and chat auto-recovery hints.
- Side-effecting interrupted command/write recovery items now include the original command or path, a review hint, and short review steps; `mew work --recover-session --json` reports the same review context instead of only refusing automatic retry.
- Interrupted command summaries now fall back to stored parameters when no result exists, non-JSON recovery output prints command/path review context, and pending stop requests appear directly in resume JSON/text.
- Work-session recovery plan items now carry the interrupted source record's summary, error, and `recovery_hint`, so text and JSON resumes preserve why a retry/replan/review item exists instead of showing only a generic action classification.
- Work-session resumes that include live world state now refine recovery-driven `next_action` text: missing touched paths are called out first, clean git plus existing touched paths are distinguished from dirty/uncertain world state, and no side-effecting recovery is attempted automatically.
- Recovered interrupted tools remain in the failure history for audit, but resume JSON/text now labels them with `recovery_status` and the recovering tool call id.
- `save_state` now rotates the previous `state.json` to `state.json.bak` before replacing it, giving the resident shell a simple recovery point if the current state file is damaged.
- `mew work --session --resume --allow-read ...` now adds a live world-state section with current git status and touched-file stats, reducing reliance on cached session history alone.
- The same world-state check is available from chat resume and in model context, making it easier for both user and resident model to revalidate state before continuing.
- Follow-status recovery hints now expose the read-side next command for absent/stale/dead snapshots and prefer the session recovery plan when it contains a retryable read, side-effect review, or replannable model turn.
- Failed passive native-work advances now route the next tick to an explicit
  recovery question with concrete inspect/retry commands instead of silent wait
  or blind retry. Runtime-created recovery notes are ignored by the retry gate,
  so mew does not mistake its own bookkeeping for user/model/tool progress.
- Interrupted `run_tests` is now classified as `retry_verification` rather than
  generic side-effect review. `mew work <task> --recover-session` can rerun the
  exact interrupted verifier when the user provides explicit read roots,
  `--allow-verify`, and the matching `--verify-command`; arbitrary
  `run_command`, write, and edit recovery still stay on the manual-review path.
- Passive native-work failure questions now include the current work-session
  recovery plan's suggested command when one exists, so the user/model sees a
  classified path such as `retry_verification` or side-effect review instead of
  only a generic inspect/retry prompt.
- Review follow-up tightened interrupted verifier recovery: `--allow-read` must
  cover the verifier's recorded `cwd`, missing-gate reports include that cwd,
  and only the latest interrupted verifier receives a runnable recovery hint.
- Verifier recovery now accepts quote-only command differences when
  `shlex.split` produces the same argv, reducing false `needs_matching_verifier`
  rejections while preserving exact interrupted-command recovery semantics.
- `dogfood --scenario passive-recovery-loop` now proves the end-to-end passive
  recovery path: failed native advance, classified recovery question,
  explicit verifier recovery, superseded interrupted call, and a following
  passive tick that advances the runtime-owned session instead of staying
  blocked on `previous_native_work_step_failed`.
- Recovery suggestions now select the highest-priority recovery action
  (`needs_user_review`, safe retry, verifier retry, then replan) rather than
  blindly using the last item in the recovery plan, keeping side-effect review
  visible when multiple interrupted items exist.
- Passive native-work auto-recovery now handles the safest runtime-owned failure
  slice: if the previous native advance left an interrupted `run_tests`, the
  recovery plan selects that verifier as the safe next item, `--allow-read`
  covers the recorded verifier cwd, and `--allow-verify --verify-command`
  exactly matches the interrupted command, the next passive tick reruns the
  verifier and marks the interrupted call superseded.
- The same auto-recovery path refuses to bypass higher-priority side-effect
  review. A regression test seeds an interrupted write plus a later interrupted
  verifier and proves mew asks a recovery question instead of starting an
  automatic verifier retry.
- `dogfood --scenario passive-auto-recovery` proves the automatic path end to
  end: seed failed runtime-owned native advance with interrupted verifier, run
  one passive tick to auto-rerun the verifier, then run another passive tick to
  advance the runtime-owned work session.
- Passive native-work auto-recovery now also supports selected interrupted
  safe read/git tools. It uses the same recovery-plan priority gate, requires
  explicit `--allow-read` to cover the interrupted tool's path/cwd, marks the
  old tool call superseded on success, and falls back to the visible recovery
  question when read gates are missing.
- `dogfood --scenario passive-auto-recovery-read` proves the safe-read path end
  to end with an interrupted `read_file`, a passive auto-retry, and a following
  passive native advance.
- `mew run` startup now repairs incomplete prior runtime effects before
  processing the next event. It deliberately leaves running work-session items
  to explicit `mew repair`, avoiding accidental interruption of human-owned or
  still-live work.

Missing proof:

- Automatic `ask_user` recovery exists for failed passive native-work advances,
  and passive auto-retry now exists for selected interrupted verifier plus
  safe read/git work-session tools, but not yet for all interrupted runtime
  effects or side-effecting write/shell work items.
- World-state revalidation before retry exists for safe read/git and
  interrupted verifier work-session recovery, but not yet for runtime effects or
  write/shell work.
- Safe work-session auto-recovery is still opt-in and limited to one interrupted read/git tool per resume.

Next action:

- Extend safe next-action selection from work-session tool recovery into
  broader interrupted runtime effects, while keeping side-effecting write/shell
  recovery on explicit review until world-state validation is strong enough.

## Milestone 5: Self-Improving Mew

Status: `foundation`

Evidence:

- `mew-product-evaluator` skill exists.
- Dogfood scenarios exist and are used.
- Self-improvement task creation/planning paths exist.
- External model review through ACM has been used for roadmap and extraction decisions.
- `mew-roadmap-status` skill and this status file exist to preserve roadmap progress across context compression.
- Native self-improvement dogfood tasks #36-#39 produced and validated small mew fixes: low-intent research wait suppression, stale done-task work-session filtering/closing, and recent-commit/coding-focus context for future self-improvement sessions.
- Native self-improvement dogfood task #44 used `mew work --live` with Codex Web API to discover and drive line-based reads, large-file edit support, and a cockpit `/continue` display improvement.
- Native self-improvement dogfood session #69 used `mew self-improve --start-session` and `mew work --follow` with Codex Web API to implement a small True Recovery slice, then verified it with focused and full tests.
- Native self-improvement dogfood session #70 used `mew work --follow` with Codex Web API to continue True Recovery work; it exposed malformed JSON and incomplete edit friction, then landed world-aware recovery `next_action` guidance after those cockpit fixes.
- Native self-improvement dogfood session #71 used `mew work --follow` with Codex Web API to attempt the first post-error re-observer slice; it stalled on a stale edit after a partial patch, which directly shaped the manual structured `suggested_safe_reobserve` implementation.
- Native self-improvement dogfood session #81 used `mew self-improve --start-session` and `mew work --live` with Codex Web API to identify redundant `--start-session` output; the follow-up implementation now keeps plain `--native` start guidance while showing only the actionable continue hint after a session is already started.
- Native self-improvement dogfood session #82 used `mew work --follow` with Codex Web API plus write/verify gates to apply a real edit: chat `/self ... start` now matches CLI behavior by suppressing the redundant native-work start hint after the session already exists.
- Native self-improvement dogfood session #83 used `mew work --follow` with Codex Web API plus write/verify gates to apply a cockpit cleanup: non-compact work controls now show only the scoped `/work-session resume --allow-read ...` hint instead of also showing a generic duplicate resume line.
- Native self-improvement dogfood session #84 targeted a real friction from this session (`mew task list --status pending`); mew found the parser but needed manual assist to locate the imported handler, after which task list gained `--status` with `pending`/`open` aliases and Claude review follow-up coverage for `todo`, `running`, `blocked`, `open`, `--kind`, and `--all --status`.
- Native self-improvement dogfood session #85 followed up on #84's handler-location friction; `mew work` THINK guidance now tells the resident model to search the broader project tree or allowed read root when a symbol is imported but not defined in the current file, rather than repeating same-file searches.
- Native self-improvement dogfood session #88 exposed a work-tool bug while looking for `--limit`: `search_text` treated a query beginning with `--status` as an `rg` flag. The read tool now inserts `--` before the query so dash-prefixed literal searches work.
- `codex-ultra` human-role dogfood reported noisy quick chat startup; `mew chat --quiet` now starts without the brief, unread backlog, runtime activity, or startup controls while preserving existing `--no-brief`/`--no-unread` behavior.
- Native self-improvement dogfood session #90 returned to the long task-list friction; `mew task list` now accepts `--limit N`, preserving existing default output while allowing bounded done/status listings.
- Native self-improvement task #89/session #114 used `mew work --follow` with Codex Web API after the one-time steer slice; it recommended making the native self-improve entrypoint show a bounded follow command, and the CLI/help output now does.
- Native self-improvement task #116/session #138 used `mew work --follow` with
  Codex Web API after the day-reentry proof. The resident inspected
  self-improve native/start-session code and tests, decided not to make an
  ungrounded code edit, and recommended a narrow assertion-only hardening; the
  resulting tests now prove plain `--native` advertises continue/follow/resume
  controls without creating a work session.
- Native self-improvement task #106/session #133 used `mew work --follow` with Codex Web API to choose and attempt a real cockpit/recovery improvement. It selected recovery controls correctly and verification rollback caught the first implementation-only edit, but the resident then failed to produce a paired implementation+test edit without supervisor help. The landed change now surfaces concrete recovery commands from the recovery plan in cockpit controls, including side-effect review commands, and the friction is recorded on the work session.
- Follow-up dogfood task #107 clarified the rollback friction without changing the retryable-approval model: failed approvals remain available for retry, but CLI controls now label them as `retry failed approval #<id>` instead of the misleading plain `approve tool #<id>`.
- Native self-improvement task #108/session #134 targeted the deeper rollback-context gap from #106. The resident found the right context slice but again produced an implementation-only dry-run; the supervisor landed the paired test. Resident context now places verification stdout/stderr tails beside write-run records when `verification_run_id` is available, so failed write/rollback recovery can see the failing test output near the write that caused it.
- Claude's current HEAD review identified the #106/#108 implementation-only
  edit pattern as the top one-hour blocker. Source edit approvals now surface
  paired-test advisory state, and the resident prompt explicitly says to pair
  `src/mew` edits with `tests/` changes or preserve the intended test in
  `working_memory.next_step` when the approval boundary stops the loop.
- `codex-ultra` human-role dogfood reported that `mew work <task> --tests/--commands/--diffs` looked like inert flags unless `--session` was also passed; these flags now route directly to their focused work-session panes.
- `codex-ultra` human-role dogfood on HEAD `600bb1a` verified persisted read, shell, write, and verify gates; read-only review probes on closed/done sessions; and combined `--tests --commands --diffs` panes using temporary tasks #66/#67, then closed the sessions and left tracked git status clean.
- Direct work tools now reuse session default gates while merging explicit per-call roots, and sensitive write roots such as `.mew/...` are filtered from persisted session defaults and generated controls so copy-paste follow-ups do not advertise roots the write tool will refuse.
- `mew work <task-id> --tool read_file|search_text|glob|git_*` can now run as a read-only review probe against the latest closed session for done or still-open tasks, while write-class tools explain how to resume/reopen instead of emitting a generic no-active-session error.
- `mew work <task-id> --tests --commands --diffs` now prints all requested focused panes in one command and prints a single start/resume hint when no session exists for the task.
- `mew chat --quiet` now suppresses the REPL banner as well as startup brief, unread messages, activity, and controls, making scripted attach/chat checks truly quiet.

Missing proof:

- mew does not yet run repeated self-improvement loops with native tools.
- Human approval/checkpoint flow is still manual.
- Self-improvement is not yet primarily driven by mew's own resident loop.
- Roadmap/status files are governance support, not proof of autonomous self-improvement.

Next action:

- Once Native Hands exists, dogfood a small self-improvement task end-to-end inside mew.

## Latest Validation

- 2026-04-19 observation/reentry sprint: commits `b70f6d5`, `d83cd87`,
  `2030c7a`, `0a5a31f`, `57e2fd7`, and `a67aeb6` made metrics actionable for
  resident dogfood. `mew metrics --kind coding` now exposes friction samples,
  splits approval-bound dry-run waiting from model-resume latency, ignores
  empty sessions in idle ratios, and adds high-idle session context. `mew
  focus --kind coding` now brings those friction samples into the default
  reentry view. Validation included focused metrics/brief tests, ruff on
  changed files, `git diff --check`, metrics text/JSON smoke checks, repeated
  `./mew dogfood --all --cleanup --json` runs (pass), and full
  `uv run pytest -q` runs up to `1052 passed, 30 subtests passed`.
- 2026-04-19 active memory sprint: commits `874eccd`, `8647117`,
  `6c6f2df`, `a4310dd`, `b57edb8`, `16ad503`, and `155630d` delivered the
  5.12 typed/scoped memory MVP, injected active typed recall into native work
  resume and resident THINK context, proved with the real Codex Web API that a
  project memory can steer the first resident action, exposed
  `mew memory --active --task-id ...` from both CLI and native self-improve
  controls, filtered noisy self-improve boilerplate from active recall terms,
  and made text output show recall score and matched terms. Validation included
  focused memory/work-session tests, ruff on changed files, full
  `uv run pytest -q` (`1036 passed, 30 subtests passed`), repeated
  `./mew dogfood --all --cleanup --json` runs (pass), `git diff --check`, and
  a real API dogfood where active project memory led the resident to
  `read_file README.md`.
- 2026-04-19 continuation dogfood kept Milestone 2 as the active focus and
  landed several small cockpit/reentry fixes from real mew use: `64a5381`
  and `7f6bcc8` make no-active work-session read tools point at one-shot
  `mew tool ...` alternatives, `7b0b5c8` removes redundant `--ready` from
  empty coding-queue self-improve start suggestions, `d9723ba` scopes
  agent-status projections in `status`/`brief`/session/chat kind-filtered
  views, and `fec0bfe` fixes running search/glob cockpit summaries so live
  cells show the requested query/pattern instead of `None` before results
  land; `2eaacea` preserves path-style `mew` launchers in `mew next --json`
  command fields for external observers using `MEW_EXECUTABLE`; and `3fb8005`
  makes injected dogfood messages use the same runtime environment as the
  runtime process, so `PYTHONPATH`/`MEW_EXECUTABLE` do not diverge. Validation
  included repeated `uv run --with ruff ruff check` on changed files, focused
  command/brief/desk/work-session/dogfood tests, `tests.test_work_session`
  (`339 tests`, pass), repeated full `uv run python -m unittest` runs (latest:
  `1003 tests`, pass), direct `MEW_EXECUTABLE=/tmp/.../mew ./mew next --json`
  checks, short Codex Web API dogfood with `injected_messages processed=1/1`,
  and repeated `./mew dogfood --all --cleanup --json` runs (pass).
- The same 2026-04-19 session then dogfooded native self-improve task #198 /
  work session #204 with Codex Web API. The resident found a small contract gap
  in chat `/self start`: `a59a1a8` now asserts that the created native work
  session is `active`, matching the existing CLI behavior. Verification included
  ruff on `tests/test_commands.py`, the focused chat self-improve unittest,
  `tests.test_commands` (`170 tests`, pass), full `uv run python -m unittest`
  (`1003 tests`, pass), and `./mew dogfood --all --cleanup --json` (pass).
- Native self-improve task #199 / work session #205 then targeted the resident
  over-search friction seen during dogfood. `d03040e` dedupes repeated
  pipe-split `search_text` queries while preserving first occurrence order and
  the existing five unique-query cap, with coverage beside the existing
  split/flatten/truncation tests. Validation included ruff on changed files,
  focused search-split tests, `tests.test_work_session` (`340 tests`, pass),
  full `uv run python -m unittest` (`1004 tests`, pass), and
  `./mew dogfood --all --cleanup --json` (pass). This dogfood also exposed an
  approval-order papercut: `approve-all` tried the pending failing test before
  the source fix, so future paired test+source batches should keep improving
  verifier sequencing.
- Follow-up task #200 fixed the concrete pairing bug behind that papercut:
  `c3aa584` no longer lets failed or rolled-back test writes satisfy `src/mew`
  source-edit paired-test checks when the failed tool lacks an explicit
  `approval_status`. Validation included ruff on changed files, the focused
  pairing regression test, `tests.test_work_session` (`340 tests`, pass), full
  `uv run python -m unittest` (`1004 tests`, pass), and
  `./mew dogfood --all --cleanup --json` (pass).
- Read-only `codex-ultra` human-role dogfood then judged mew usable as a
  supervised coding buddy but not yet as a primary shell/body, with the top
  blocker that `mew status` could say the runtime was stopped while a native
  `mew work --live` producer was still running. Task #202 / `ff63f60` adds
  active native work visibility to `mew status`: JSON now includes
  `active_work_sessions` with phase, pending approvals, follow-status command,
  and follow snapshot producer health, while text status prints compact
  `active_work_session` lines. Validation included ruff on changed files, the
  focused status test, `tests.test_commands` (`171 tests`, pass), full
  `uv run python -m unittest` (`1005 tests`, pass), and
  `./mew dogfood --all --cleanup --json` (pass).
- The same dogfood thread then fixed two front-door reentry papercuts:
  `e0d0317` makes natural `mew help` print the top-level help instead of an
  argparse invalid-choice error, and `407fd1a` keeps a `Coding:` reentry line
  visible in global `mew focus` / `mew next` even when old non-coding questions
  remain the primary next move. Validation included ruff on changed files,
  focused help/focus tests, `tests.test_brief` (`42 tests`, pass),
  `tests.test_commands` (`172 tests`, pass), full `uv run python -m unittest`
  (`1007 tests`, pass), direct `./mew help`, `./mew focus`, and `./mew next`
  checks, and `./mew dogfood --all --cleanup --json` (pass).
- Native self-improve task #205 / work session #207 then used mew itself as a
  read-only buddy to pick the next small Milestone 2 friction. The resident
  selected self-improve help clarity, and `c046dff` now states that
  `--start-session` prints concrete continue/follow/status/resume controls
  while `--json` returns the same controls as structured fields. Validation
  included ruff on changed files, the focused self-improve help test,
  `tests.test_self_improve` (`26 tests`, pass), `tests.test_commands`
  (`172 tests`, pass), full `uv run python -m unittest` (`1007 tests`, pass),
  direct `./mew self-improve --help`, and
  `./mew dogfood --all --cleanup --json` (pass).
- Task #206 / `dd5f175` finishes the natural help front door: `mew help
  <command...>` now forwards to the corresponding argparse help, so
  `mew help self-improve` and nested paths like `mew help task add` work
  without remembering `--help` placement. Validation included ruff on changed
  files, direct help-topic checks, focused help tests, `tests.test_commands`
  (`174 tests`, pass), full `uv run python -m unittest` (`1009 tests`, pass),
  and `./mew dogfood --all --cleanup --json` (pass).
- `claude-ultra` review session `8d167357-cc40-4dae-ab2c-e79d6c5fcdea`
  identified `approve-all` verification sequencing as the next high-leverage
  Milestone 2 cockpit fix. Task #207 / `ac5d3cb` implements it for CLI and
  reply-file approve-all by deferring verification for every batch item except
  the last, so multi-file batches verify against final state instead of partial
  state. `f556a67` then preserves that behavior in the recurring work-session
  dogfood scenario. `codex-ultra` review session
  `019da3ad-34c5-7810-8a0e-9f94f6a735d1` found the important failure path:
  if final verification failed, earlier deferred writes could remain applied.
  Task #210 / `3698f94` closes that by capturing rollback snapshots for
  deferred approvals and rolling them back when the batch verifier fails, for
  both CLI and reply-file approve-all. Validation included ruff on changed
  files, focused approve-all tests, `tests.test_work_session` (`343 tests`, pass),
  `tests.test_commands` (`174 tests`, pass), full `uv run python -m unittest`
  (`1013 tests`, pass), `./mew dogfood --scenario work-session --cleanup --json`
  (pass), and `./mew dogfood --all --cleanup --json` (pass after the rollback
  fix). `codex-ultra` re-review session
  `019da3b6-e2d9-7763-a2a1-e3523d859fd6` then returned PASS on the exact
  failure path and ran a targeted rollback test selection (`2 passed`).
- Task #209 / `4e72011` adds a safer recovery front door: `mew repair
  --dry-run` now computes predicted repairs and validation without saving state,
  includes `dry_run` in JSON output, and the chat cockpit accepts
  `/repair --dry-run`. Validation included ruff on changed files, direct
  `repair --dry-run` checks, focused repair/chat slash tests,
  `tests.test_commands` (`175 tests`, pass), full `uv run python -m unittest`
  (`1011 tests`, pass), and `./mew dogfood --all --cleanup --json` (pass).
- Task #175 verification-confidence pass: this slice adds structured
  `verification_confidence` to work-session resume/live/follow/follow-status
  and dogfood coverage for `src/mew/**` source-edit confidence. Validation:
  focused confidence/resume/follow-status tests (`10 passed`), ruff on changed
  files (pass), `./mew dogfood --scenario work-session --json` (pass), full
  `uv run python -m unittest` (`991 tests`, pass), and three `codex-ultra`
  reviews. The first two reviews found and drove fixes for rejected/applied
  dry-run false pending states, `python -m pytest` selector false positives,
  over-trusting `narrow_verify_command`, and `uv run --with pytest ...`
  dependency-token parsing. The final review returned PASS.
- Task #176 follow-mode dogfood used two `mew work --follow` runs with Codex
  Web API to investigate a small native self-improve improvement. The resident
  repeatedly searched only `tests/test_work_session.py` for self-improve
  control assertions and missed the actual `tests/test_self_improve.py` surface,
  so the THINK prompt now tells residents to broaden from a missed targeted
  test-file search to `tests/` or the likely test module before concluding no
  paired test surface exists. Validation: focused prompt test (pass), ruff on
  changed files (pass), `tests.test_work_session` (`332 tests`, pass),
  `./mew dogfood --scenario work-session --json` (pass), and full
  `uv run python -m unittest` (`991 tests`, pass).
- Interactive/Self-improve current: the 2026-04-19 long dogfood session added
  seven reentry, verifier-safety, and observer-handoff commits: `4073282` seeds
  native self-improve work-session defaults, `d500105` aligns CLI and chat
  self-improve start-session state, `6229213` promotes paired source-edit
  verifiers while preserving explicit verifier precedence and `verify_disabled`
  behavior, `c7a6a7c` labels stale workbench next steps, `c0901c3` makes
  native-only self-improve start hints carry read/compact-live defaults, and
  `718cc41` makes `follow-status` suggested recovery reuse selected-session
  defaults for absent/dead observer snapshots; `c8f3109` preserves path-style
  `mew` launchers in generated commands and defaults session-scoped git/run
  tools to the task cwd for external observers. Validation included focused
  self-improve/chat/work-session/cli-command tests, `uv run --with ruff ruff
  check` on the changed files, repeated full `uv run python -m unittest` runs
  (latest: `979 tests`, pass), repeated `./mew dogfood --all` runs (pass),
  `codex-ultra` reviews with an initial approve-all ordering finding, a
  no-task-arg follow-status recovery finding, and a test-environment
  `MEW_EXECUTABLE` finding, plus final `codex-ultra` re-review PASS after each
  regression test was added. A manual external-cwd e2e smoke also passed:
  `mew self-improve --native --cwd <external-root>` printed a
  default-preserving start hint, `mew work 1 --start-session --allow-read
  <external-root> --compact-live --json` persisted those defaults, taskless
  `mew work --follow-status --json` suggested a matching `refresh_snapshot`
  command, and the suggested zero-step follow refresh wrote a fresh session
  snapshot. A separate `codex-ultra` human-role dogfood from `/tmp` then
  confirmed the core flow worked and exposed the fixed path-launcher/task-cwd
  handoff issues.
- Post-session evaluator check on clean HEAD `4b5b21a`: `codex-ultra` scored
  mew `7.2/10`, judging it worth inhabiting for bounded supervised coding where
  persistence/reentry matters, while still behind Claude Code/Codex CLI for a
  dense uninterrupted coding burst. `claude-ultra` scored mew `6/10`, agreeing
  it is now genuinely inhabitable for task-scoped resident coding but not yet
  trustworthy for unattended multi-hour autonomy. Both evaluations keep the
  next highest-leverage work inside Milestone 2: codex points at a calmer
  continuous live/follow cockpit, while Claude points at a built-in same-surface
  audit before a resident task is called done.
- `098df7d` adds the first lightweight same-surface audit nudge to native
  self-improvement task descriptions: before calling work done, the resident is
  asked to inspect sibling code paths on the same surface and note why they are
  covered or out of scope. This is not yet a hard checkpoint, but it turns the
  evaluator finding into default resident guidance.
- The same-surface audit is now a visible work-session checkpoint rather than
  only prompt guidance: `build_work_session_resume` emits structured
  `same_surface_audit`, `format_work_session_resume` and `mew work <task-id>`
  render it, and `dogfood --scenario work-session` asserts the checkpoint on a
  `src/mew/**` dry-run edit. Validation included focused workbench/resume tests
  (`2 passed`), ruff on changed files (pass), `./mew dogfood --scenario
  work-session --json` (pass), related `tests.test_dogfood tests.test_work_session
  tests.test_commands` (`536 tests`, pass), full `uv run python -m unittest`
  (`980 tests`, pass), and `codex-ultra` review with two rounds of findings
  fixed followed by re-review PASS.
- Follow-up native self-improve dogfood task #172 used read-only `mew work
  --live` steps to inspect the self-improve controls surface, then aligned
  `mew self-improve --help` with the actual resume control in `01e9f2a`.
  Validation: focused self-improve help test (pass), ruff on changed files
  (pass), direct `./mew self-improve --help` output check, and full
  `uv run python -m unittest` (`980 tests`, pass).
- Follow-up native self-improve dogfood task #173 used read-only `mew work
  --live` steps to inspect the focus/brief next-move surface, then changed the
  empty coding-queue recommendation to include `--ready` in `d437460`.
  Validation: focused brief tests (pass), `tests.test_brief` (pass), ruff on
  changed files (pass), direct `./mew focus --kind coding` output check, and
  full `uv run python -m unittest` (`980 tests`, pass).
- Task #174 aligned the desk/pet empty coding-queue action with focus in
  `81f0412`, adding a `start_self_improve` primary action for
  `mew desk --kind coding` inside the mew project and keeping non-mew
  workspaces quiet. Validation: focused desk tests (pass), `tests.test_desk
  tests.test_brief` (`56 tests`, pass), ruff on changed files (pass), direct
  `./mew desk --kind coding --json` output check, and full `uv run python -m
  unittest` (`982 tests`, pass).
- Post-`e32f633` evaluator check: `claude-ultra` scored mew `6.5/10`, calling
  it a real task-scoped resident shell but not yet a proven long-lived body;
  `codex-ultra` scored mew `7.2/10`, preferring it over a fresh CLI for
  interrupted scoped work while still preferring Claude Code/Codex CLI for
  fast one-off edits. Both point at the same next blockers: cockpit fluency,
  durable multi-day cadence, and stronger verification confidence before
  finish/approval.
- Interactive Parity current: the 2026-04-19 long dogfood session added five
  bounded cockpit/body improvements across commits `803ce79`, `cf165f9`,
  `e64a2eb`, `99a9734`, and `ea7368d`: repeated resident work tools are blocked
  before execution; blocked repeat guards suggest review/steer/desk recovery
  actions; work-session effort budgets are visible in resume/model context/desk;
  `mew desk` exposes multiple prioritized actions instead of hiding everything
  behind a stale primary action; and those actions now explain their rationale
  and stale age. Validation for the final state in this session included
  focused desk/work-session/browser tests, ruff checks, full `uv run python -m
  unittest` (`964 tests`, pass), `./mew dogfood --all` (pass), and
  `codex-ultra` review PASS for each slice after fixes.
- Persistent Advantage current: native self-improve task #131 used two
  read-only `mew work --follow` steps to identify that compact task workbench
  reentry under-surfaced open risk from failed verification/work tools. The
  workbench now prints the latest unresolved failure as `risk: ...`, keeps
  `retry_failed` recovery records visible even when they reference a retry
  tool call, and hides only `recovery_status=superseded` failures. An initial
  `codex-ultra` review found that `recovered_by_tool_call_id` must not hide
  failed retries; that blocker was fixed, and the re-review returned no
  blockers with a superseded-path test suggestion that was added. Validated
  with focused reentry/recovery tests (`3 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py`
  (`444 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`964 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/commands.py tests/test_work_session.py`
  (pass), and `./mew dogfood --scenario all` (pass).
- Interactive Parity current: dogfood task #132 captured a real CLI papercut
  from this long session: `./mew dogfood --all` was rejected as ambiguous with
  `--allow-*` flags. The parser now has an exact `--all` shortcut normalized to
  `--scenario all`, rejects conflicting specific scenarios, and README lists
  the shortcut. Validated with focused shortcut tests (`3 passed`), real
  `./mew dogfood --all` (pass), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_commands.py tests/test_dogfood.py`
  (`209 passed, 4 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`967 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/cli.py src/mew/commands.py tests/test_dogfood.py tests/test_commands.py`
  (pass), and `git diff --check` (pass).
- Persistent Advantage current: task #133 extended unresolved work-session
  risk from the task workbench into `mew focus` by sharing the risk formatter
  through `work_session`. Focus JSON/text now expose the latest non-superseded
  failed tool, including failed verifier recovery, while day-reentry dogfood
  seeds a failed verifier and asserts the quiet reentry surface preserves it.
  `codex-ultra` found that the first focus implementation looked only at the
  truncated resume failure window; the fix adds `unresolved_failure` before
  truncation and re-review returned no blockers. Validated with focused
  focus/workbench/day-reentry tests (`3 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_brief.py tests/test_commands.py tests/test_work_session.py tests/test_dogfood.py`
  (`531 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`968 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/brief.py src/mew/commands.py src/mew/work_session.py src/mew/dogfood.py tests/test_brief.py tests/test_work_session.py tests/test_dogfood.py`
  (pass), and `./mew dogfood --all` (pass, including day-reentry risk checks).
- Persistent/Recovery foundation current: task #134 investigated a transient
  `output mirror failed` warning from related tests and found that
  `fcntl.flock` did not serialize same-process timer/main threads, while
  `save_state` reused pid-only temp names for backup writes. `state_lock` now
  uses a genuinely reentrant in-process `RLock`, and `save_state` temp names
  include pid, thread id, and monotonic time. `codex-ultra` reviewed the first
  pass and noted the nested-lock deadlock and weak test coverage; the fix skips
  repeat `flock` calls for nested same-thread entry and mocks `flock` in the
  thread serialization test. Validated with focused state/mirror tests (`4
  passed`), the warning-producing related suite plus validation
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_brief.py tests/test_commands.py tests/test_work_session.py tests/test_dogfood.py tests/test_validation.py`
  (`553 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`970 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/state.py tests/test_validation.py`
  (pass), and `./mew dogfood --all` (pass).
- Interactive/Persistent current: self-improve task #135 exposed that the
  resident naturally emitted `search_text` with a space-separated include glob
  pattern (`src/** tests/** docs/**`), which previously returned zero matches
  because it was sent to `rg` as one glob. `search_text` now splits
  shell-style whitespace, de-dupes patterns, and adds `**/` variants for
  relative path globs. The exact failed work-session command now returns
  repository matches. Validated with focused search tests (`2 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py`
  (`282 passed, 5 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`971 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/read_tools.py tests/test_work_session.py`
  (pass), and `./mew dogfood --all` (pass).
- Observer/self-improve current: task #136 fixed the long-session failure where
  `mew self-improve --start-session --json` was rejected. The command now has a
  JSON surface with task, plan, run, work-session, and native controls fields,
  while preserving existing text output. Validated with focused start-session
  JSON/text tests (`2 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_self_improve.py tests/test_commands.py`
  (`188 passed, 10 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`972 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/cli.py src/mew/commands.py tests/test_self_improve.py`
  (pass), and `./mew dogfood --all` (pass).
- Observer/self-improve current: task #137 dogfooded the new JSON surface and
  exposed that reusing an existing `self-improve --start-session` task updated
  the task description but left the active work-session goal on the previous
  focus. `create_work_session` now refreshes the existing session's task
  snapshot on reuse, and the real task #137 JSON output shows the session goal
  aligned with the latest focus. Validated with focused reuse tests (`2
  passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_self_improve tests.test_work_session`
  (`307 passed`), full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`974
  passed, 15 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/work_session.py tests/test_self_improve.py tests/test_work_session.py`
  (pass), `git diff --check` (pass), and `./mew dogfood --all` (pass).
- Observer/self-improve current: task #138 used `mew work --follow` to inspect
  the self-improve/start-session surface and picked a tiny discoverability
  cleanup. `mew self-improve --help` now lists the structured
  `--start-session --json` entrypoint beside the text start-session flow.
  Validated with focused help output test (`1 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_self_improve`
  (`24 passed`), full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`974
  passed, 15 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/cli.py tests/test_self_improve.py`
  (pass), `git diff --check` (pass), and `./mew dogfood --all` (pass).
- Bake-off current: task #139 created `WHY_MEW.md` and ran the first
  mew-vs-fresh product proof. Mew preserved a failed model call in resume
  memory, retried the session, searched/read the relevant code, and diagnosed
  the `--close-session --json` no-active plaintext path. A fresh `codex-ultra`
  review then caught wider same-surface misses, so the fix now covers
  `--close-session`, `--stop-session`, `--session-note`, `--steer`,
  `--queue-followup`, `--interrupt-submit`, `--approve-tool`, `--approve-all`,
  `--reject-tool`, and no-session `--tool` action paths with structured
  no-active JSON. Fresh re-review returned PASS. Validated with focused
  no-active JSON tests (`2 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_work_session`
  (`285 tests OK`), full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`976
  passed, 25 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/commands.py tests/test_work_session.py`
  (pass), `git diff --check` (pass), and `./mew dogfood --all` (pass).
- Bake-off current: task #140 turned the first bake-off weakness into a second
  real improvement. With write/verify gates present, mew inspected the
  workbench reentry path and applied a source edit itself, then stopped with a
  durable note for the missing paired test. The final fix now shows
  `resume_next_action` in the workbench Reentry block and makes the workbench's
  canonical bottom `Next action` reuse active work-session defaults when they
  include gates. For sessions with only non-gate defaults, it preserves those
  options while injecting `--allow-read .`, avoiding the `missing_gates`
  regression found by fresh `codex-ultra`. Fresh re-review returned PASS.
  Validated with focused workbench tests (`4 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_commands tests.test_work_session`
  (`452 tests OK`), full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`978
  passed, 25 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/commands.py tests/test_commands.py tests/test_work_session.py`
  (pass), `git diff --check` (pass), and `./mew dogfood --all` (pass).
- Follow-up current: `claude-ultra` recommended closing the recurring
  implementation-only source-edit loop by adding a concrete paired-test
  candidate to `pairing_status`. Missing `src/mew/**` paired-test approvals now
  carry an inferred `suggested_test_path`; resume text, approval cells,
  reply-file steer text, follow schema docs, and the THINK prompt surface it.
  `codex-ultra` reviewed the diff and returned `NO_BLOCKERS`. Validated with
  focused pairing/prompt tests (`3 passed, 278 deselected`),
  `./mew dogfood --scenario work-session --cleanup --json` (pass with
  suggested test path in `work_source_edit_pairing_advisory`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py tests/test_dogfood.py`
  (`487 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`964 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), and `./mew dogfood --scenario all --cleanup --json` (pass).
- Persistent Advantage current: `claude-ultra` recommended wiring
  `memory.deep.preferences` into native work as the smallest M3 slice that
  turns resident memory into observable model behavior. Work-session resumes now
  expose `user_preferences`; native work THINK prompts receive the same resume;
  follow snapshots carry it; and `mew code --help` / `/help work` point users
  at `mew memory --add ... --category preferences`. `codex-ultra` reviewed the
  diff and returned `NO_BLOCKERS`; its blank-entry metadata suggestion was
  folded in. Validated with focused preference/help/follow snapshot tests
  (`4 passed`), related
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py tests/test_brief.py tests/test_runtime.py`
  (`522 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`964 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), `git diff --check` (pass), and
  `./mew dogfood --scenario all --cleanup --json` (pass). Follow-up dogfood
  coverage added `work_resume_surfaces_user_preferences`, validated with
  `./mew dogfood --scenario work-session --cleanup --json` (pass) and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_dogfood.py -k work_session`
  (`1 passed, 42 deselected`).
- Native self-improve dogfood task #127 current: mew used a read-only
  `--follow` pass to choose the next small Milestone 2 improvement, then landed
  `follow-status` discoverability in native self-improve output/help. Validated
  with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_self_improve.py tests/test_commands.py -k self_improve`
  (`28 passed, 157 deselected, 6 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/commands.py src/mew/cli.py tests/test_self_improve.py tests/test_commands.py`
  (pass), and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_self_improve.py tests/test_commands.py`
  (`185 passed, 10 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`963 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), and `./mew dogfood --scenario all --cleanup --json` (pass across
  all scenarios, including the running-output follow snapshot check).
- Native self-improve dogfood task #128 current: mew identified that native
  self-improve still advertised a three-step follow loop while work/code
  cockpit controls use ten-step follow. The entry output, help, README example,
  and assertions now use `--follow --quiet --compact-live --max-steps 10`.
  Validated with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_self_improve.py tests/test_commands.py -k self_improve`
  (`28 passed, 157 deselected, 6 subtests passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/commands.py src/mew/cli.py tests/test_self_improve.py tests/test_commands.py`
  (pass), and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_self_improve.py tests/test_commands.py`
  (`185 passed, 10 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`963 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), and `./mew dogfood --scenario all --cleanup --json` (pass).
- Follow-up current: running `run_command`/`run_tests` output is mirrored as a
  bounded tail into work-session state and follow snapshots without changing
  the stale-reply `session_updated_at` token; quiet follow still writes a
  timer-flushed snapshot, and completed tools clear the running tail in favor
  of the final result. `codex-ultra` twice found blockers in the first draft
  (temp-file races, unthrottled churn, stale reply tokens, and silent buffered
  chunks); the final re-review returned `NO_BLOCKERS`. Validated with targeted
  running-output/follow tests (`3 passed`), combined
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py`
  (`442 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`962 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_dogfood.py`
  (`43 passed`), and `./mew dogfood --scenario all` (pass with
  `work_follow_snapshot_surfaces_running_output` across 77 work-session
  commands).
- Follow-up current: zero-step snapshot refresh is now read-only for existing
  active work sessions; validated with targeted zero-step/running-output tests
  (`7 passed`), combined
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py tests/test_dogfood.py`
  (`486 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`963 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), and `./mew dogfood --scenario all` (pass).
- Follow-up current: pending write approvals in resume/follow JSON now include
  a capped machine-review `diff` plus `diff_truncated` and `diff_max_chars`,
  so observer agents can review the exact dry-run change from
  `.mew/follow/latest.json` without scraping terminal preview text. Validated
  with targeted approval/follow snapshot tests (`3 passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_work_session.py tests/test_commands.py`
  (`438 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`958 passed, 15 subtests
  passed`), `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check .`
  (pass), `./mew dogfood --scenario all` (pass), and `codex-ultra` review
  (`NO_BLOCKERS`).
- Follow-up current: real dogfood task #122 used `mew code`/`mew work` as the
  buddy surface to probe paired-test approval UX, found misleading approve
  paths and narrow-test default pollution, and the tree now fixes both. Reviewed
  by `codex-ultra` and `claude-ultra`; codex found a runtime recovery regression
  after raw blocked approve hints were cleared, which was fixed and re-reviewed
  with no blockers. Validated with focused approval/default-memory tests
  (`8 passed, 257 deselected, 5 subtests passed`), related runtime/dogfood
  regressions (`3 passed`), the combined work/runtime/dogfood/commands/brief
  suite (`552 passed, 9 subtests passed`), full
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`951 passed, 15 subtests
  passed`), full ruff over `src tests` (pass), and
  `./mew dogfood --scenario all --json` (pass).
- Follow-up current: passive native-work auto-recovery can now rerun a
  runtime-owned interrupted verifier on the next passive tick when explicit
  read/verify gates match, while preserving recovery-plan priority so unsafe
  interrupted write/command work still asks the user. `codex-ultra` reviewed
  the first diff, found the recovery-priority and stale-finish risks, then
  re-reviewed the fix and found no blockers. Validated with
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/runtime.py src/mew/dogfood.py tests/test_runtime.py tests/test_dogfood.py`
  (pass), focused runtime/dogfood recovery tests (`4 passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_runtime.py tests/test_work_session.py tests/test_dogfood.py`
  (`336 passed`), full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
  (`937 passed, 10 subtests passed`), and
  `./mew dogfood --scenario all --json` (pass, including
  `passive-auto-recovery`).
- Follow-up current: passive native-work auto-recovery now also reruns selected
  interrupted safe read/git tools under explicit read gates. `claude-ultra`
  recommended this as the next safest recovery slice, and `codex-ultra`
  reviewed the implementation with no blockers. Validated with
  focused runtime recovery tests (`4 passed`),
  `./mew dogfood --scenario passive-auto-recovery-read --json` (pass),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/runtime.py src/mew/dogfood.py tests/test_runtime.py tests/test_dogfood.py`
  (pass),
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_runtime.py tests/test_work_session.py tests/test_dogfood.py`
  (`339 passed`), and `./mew dogfood --scenario all --json` (pass, including
  `passive-auto-recovery-read`).
- Follow-up current: runtime startup now performs conservative repair for
  incomplete runtime effects before processing a new event, while deliberately
  leaving running work-session items for explicit `mew repair`. `codex-ultra`
  caught and the implementation fixed the unsafe first version that interrupted
  all running work sessions. Validated with focused startup repair coverage,
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_runtime.py tests/test_validation.py`
  (`58 passed`),
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check src/mew/runtime.py tests/test_runtime.py`
  (pass),
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_runtime.py tests/test_work_session.py tests/test_dogfood.py tests/test_validation.py`
  (`360 passed`), and `./mew dogfood --scenario all --json` (pass).
- Claude current-HEAD evaluation (`claude-ultra`, session
  `e8ffa27e-5e27-45c9-b37f-68cca4897a95`) verdict: qualified yes for small,
  supervised bounded coding work; the highest-leverage next slice was paired
  test discipline for model-authored writes. Implemented advisory
  `pairing_status` on `src/mew/**` pending approvals and prompt guidance to
  carry the paired test plan across approval boundaries. Validated with
  `uv run pytest -q tests/test_work_session.py` (`244 passed`),
  `./mew dogfood --scenario work-session --cleanup --json` (pass),
  `./mew dogfood --scenario all --cleanup --json` (pass), and full
  `uv run pytest -q` (`908 passed, 6 subtests passed`).
- Follow-up current: `mew focus` now shows active work-session age, and
  `dogfood --scenario day-reentry` proves day-scale reentry across focus,
  resume, world-state, notes, and activity history. Validated with
  `uv run pytest -q tests/test_brief.py` (`39 passed`),
  `uv run pytest -q tests/test_dogfood.py` (`41 passed`),
  `uv run pytest -q tests/test_brief.py tests/test_commands.py tests/test_self_improve.py`
  (`217 passed, 6 subtests passed`), day-reentry dogfood (pass),
  all-scenario dogfood (pass), and full `uv run pytest -q` (`906 passed,
  6 subtests passed`).
- Native self-improve dogfood task #116 current: mew selected assertion-only
  hardening instead of an ungrounded code edit; CLI/chat `--native` tests now
  assert continue/follow/resume controls are printed while no work session is
  created. Validated with targeted native self-improve tests and
  `uv run pytest -q tests/test_self_improve.py tests/test_commands.py -k self_improve`
  (`24 passed, 154 deselected, 2 subtests passed`).
- Follow-up current: passive native-work recovery now has a deterministic
  `passive-recovery-loop` dogfood scenario, and recovery suggestions now follow
  recovery-plan action priority. Recovery plan items and observer
  `suggested_recovery` now surface `effect_classification` (`no_action`,
  `verify_pending`, `action_committed`, `write_started`, `rollback_needed`) so
  side-effect recovery risk is visible. Validated with
  `uv run pytest -q tests/test_dogfood.py` (`40 passed`),
  `./mew dogfood --scenario passive-recovery-loop --cleanup --json` (pass),
  `uv run pytest -q tests/test_work_session.py tests/test_runtime.py`
  (`270 passed`), `uv run pytest -q tests/test_work_session.py tests/test_runtime.py tests/test_dogfood.py`
  (`311 passed`), `./mew dogfood --scenario all --cleanup --json` (pass), and
  full `uv run pytest -q` (`903 passed, 6 subtests passed`).
- `uv run pytest -q` current: `897 passed, 6 subtests passed`.
- `./mew dogfood --scenario native-advance --cleanup --json` current: pass; validates passive runtime selection of a runtime-owned work session, the configured `MEW_EXECUTABLE` handoff, quiet one-step live flags, completed runtime status, and dogfood advance metrics.
- Focused native-work runtime tests current: `11 passed`; covers failed passive-native-advance classification, no blind retry on the next tick, and retry allowance after newer session activity.
- Native self-improve dogfood task #105 used mew to choose the next small improvement, then extracted shared native self-improve work-control printing so CLI and chat paths keep `continue`/`follow`/`resume` guidance consistent without changing output.
- Native self-improve dogfood task #106 current: mew selected a recovery-cockpit target and drove the first dry-run; supervisor completed the paired test update after rollback friction. Validated with `uv run pytest -q tests/test_work_session.py -k recovery` (`8 passed`), `uv run pytest -q tests/test_work_session.py` (`238 passed`), full `uv run pytest -q` (`897 passed, 6 subtests passed`), and `./mew dogfood --scenario all --cleanup --json` (pass).
- Follow-up task #107 current: failed approval retry labels validated with focused approval-control tests, `uv run pytest -q tests/test_work_session.py` (`238 passed`), full `uv run pytest -q` (`897 passed, 6 subtests passed`), and `./mew dogfood --scenario all --cleanup --json` (pass).
- Native self-improve task #108 current: write-run context now includes linked verification stdout/stderr tails; validated with `uv run pytest -q tests/test_autonomy.py` (`100 passed`), full `uv run pytest -q` (`897 passed, 6 subtests passed`), and `./mew dogfood --scenario all --cleanup --json` (pass).
- Follow-up task #109 current: failed passive native-work advance recovery now
  ignores runtime-created recovery notes when deciding whether a failure was
  resolved. `dogfood --scenario native-advance` simulates a failing
  `MEW_EXECUTABLE` and verifies that mew asks a seeded recovery question with
  inspect/retry commands and does not blindly call `mew work <task>` again.
  Validated with full `uv run pytest -q` (`897 passed, 6 subtests passed`) and
  `./mew dogfood --scenario all --cleanup --json` (pass).
- Self-improve task #110 current: after claude-ultra and codex-ultra both
  identified True Recovery as the next trust blocker, interrupted `run_tests`
  recovery gained a `retry_verification` plan, explicit verifier gates, and
  work-session dogfood coverage. Validated with
  `uv run pytest -q tests/test_work_session.py` (`239 passed`),
  `./mew dogfood --scenario all --cleanup --json` (pass), and full
  `uv run pytest -q` (`898 passed, 6 subtests passed`).
- Follow-up task #111 current: passive native-work failure prompts now include
  classified recovery-plan commands, preserving the `retry_verification` or
  side-effect review path in the seeded runtime question. Validated with
  `uv run pytest -q tests/test_runtime.py` (`29 passed`), native-advance
  dogfood (pass), all dogfood (pass), and full `uv run pytest -q` (`898 passed,
  6 subtests passed`).
- Follow-up task #112 current: claude-ultra/codex-ultra review of
  `e5d2fb1..HEAD` found no regression but identified verifier cwd/read-root and
  stale hint risks. Both are fixed: verifier recovery now requires read roots to
  cover the recorded cwd and only the latest interrupted verifier has a runnable
  hint. Validated with focused work-session recovery tests,
  `uv run pytest -q tests/test_work_session.py` (`239 passed`), work-session
  dogfood (pass), all dogfood (pass), and full `uv run pytest -q` (`898 passed,
  6 subtests passed`).
- Self-improve task #113 current: native self-improve controls are now
  cwd-aware, so `--cwd <other-dir>` prints continue/follow/resume commands
  gated with that resolved directory instead of `--allow-read .`. Validated with
  `uv run pytest -q tests/test_self_improve.py -k start_session` (`3 passed`),
  self-improve command tests (`23 passed`), work-session dogfood (pass), all
  dogfood (pass), and full `uv run pytest -q` (`899 passed, 6 subtests passed`).
- Follow-up task #114 current: verifier recovery now treats argv-equivalent
  commands as matching, so quoting-only differences in `--verify-command` do
  not falsely block recovery. Validated with the focused recovery test,
  `uv run pytest -q tests/test_work_session.py` (`239 passed`), work-session
  dogfood (pass), all dogfood (pass), and full `uv run pytest -q` (`899 passed,
  6 subtests passed`).
- Real Codex Web API dogfood after the verification-recovery work current:
  `./mew dogfood --duration 80 ... --ai --auth auth.json --allow-native-work
  --allow-native-advance` completed startup plus two passive ticks; it started
  native work session #1, advanced one quiet resident step through Codex Web
  API, completed the seeded task on the next tick, and ended with
  `native_work_advance.by_outcome.completed=1`.
- `./mew dogfood --scenario native-work --allow-native-work --allow-native-advance` current: pass; validates native work session start, runtime defaults, visible reentry commands, no redundant ready-task question, and no external agent run.
- Real Codex Web API dogfood current: `./mew dogfood --duration 80 --interval 20 --poll-interval 0.2 --ai --auth auth.json --autonomy-level act --allow-native-work --allow-native-advance --seed-ready-coding-task --allow-verify --verify-command '/usr/bin/python3 -V' --report .mew/dogfood-native-advance-ai-20260418-seed-note.json --json` completed startup plus two passive ticks; `native_work_advance.attempts=2`, `by_outcome.completed=2`, `last_native_work_step.outcome=completed`, and the earlier refused-complete warning is gone because the dogfood seed task is now marked as self-proposed.
- `uv run pytest -q` previous native-work rollout: `881 passed, 6 subtests passed`.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, resident-loop, native-work, native-advance, chat-cockpit, and work-session; interrupted-focus checks ready coding questions route to `mew code`, runtime-focus includes stale passive question refresh, resident-loop proves startup/passive tick cadence and repeated-wait thought compaction, native-work proves explicit `--allow-native-work` act-level runtime starts a native work session for a ready coding task with current runtime read/verify/model defaults, provenance, visible live/follow commands, no external agent runs, no stale write/verify authority, and no redundant ready-task questions, native-advance proves a later passive tick can invoke one quiet native work step through `MEW_EXECUTABLE`, `observe --json`, and work-session includes task lifecycle JSON, done-task resume reopen controls, follow-status producer health, suggested recovery, reply-file checks, and stable cockpit cells.
- `uv run pytest -q experiments/mew-desk` current: `11 passed`, including the isolated terminal-pet renderer over `mew desk --json`.
- `uv run pytest -q` older cockpit rollout: `813 passed, 6 subtests passed`.
- `uv run pytest -q tests/test_dogfood.py` current: `36 passed`.
- `uv run pytest -q tests/test_commands.py` current: `158 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_commands.py -k "chat_self_improve_start_opens_native_work_session or chat_self_improve_native_skips_programmer_plan"` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `203 passed`.
- `uv run pytest -q tests/test_work_session.py -k "reply_file_can_queue_safe_follow_actions or reply_file_rejects_stale_session_snapshot or reply_file_reject_action_is_single_use or chat_work_session_can_approve_and_reject_tool_changes"` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py -k "follow_writes_round_trip_snapshot or reply_file_can_queue_safe_follow_actions or reply_file_without_active_session_fails or reply_file_rejects_stale_session_snapshot"` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py -k "reply_file_can_queue_safe_follow_actions or follow_writes_round_trip_snapshot or work_session_steer_requires_task_id_when_multiple_sessions_active"` current: `3 passed`.
- `uv run pytest -q tests/test_work_session.py -k "work_live_prints_resume_after_step or work_follow_honors_explicit_one_step_bound or work_follow_writes_round_trip_snapshot or work_follow_runs_compact_multi_step_live_loop"` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_steer_is_consumed_by_next_model_step tests/test_work_session.py::WorkSessionTests::test_work_session_model_error_preserves_pending_steer tests/test_work_session.py::WorkSessionTests::test_work_session_stop_preserves_pending_steer` current: `3 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_steer_requires_task_id_when_multiple_sessions_active tests/test_work_session.py::WorkSessionTests::test_work_session_steer_is_consumed_by_next_model_step` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_cli_controls_include_steer_command tests/test_work_session.py::WorkSessionTests::test_work_session_start_can_seed_reentry_options` current: `2 passed`.
- `uv run pytest -q tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_help_describes_native_work_flow tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_start_session_uses_native_work` current: `2 passed`.
- `./mew self-improve --start-session --focus 'Dogfood native follow output' --force --ready` current: printed both `continue:` and `follow:` native work commands.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, chat-cockpit, and work-session; work-session includes 44 commands and the structured reply-file snapshot check.
- `./mew dogfood --scenario work-session --cleanup --json` current: pass across 44 commands, including CLI/chat one-time steer queuing, exact new-file approval, approve-all for multiple pending writes, structured reply-file snapshot acknowledgement, pending diff preview in resume, command-output previews in resume, working-memory resume surfacing, focused chat diff/test/command previews, line-based read, large-file dry-run edit, workbench/global work-session ledgers, chat resume world state, timeline surfacing, side-effect recovery review context, and safe read auto-recovery.
- `uv run pytest -q` current: `823 passed, 6 subtests passed`.
- `uv run pytest -q tests/test_work_session.py` current: `213 passed`.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, chat-cockpit, and work-session; work-session includes 51 commands and the session-specific reply-schema, FIFO follow-up, and interrupt-submit checks.
- `./mew dogfood --scenario work-session --cleanup --json` current: pass across 51 commands, including the session-specific reply-schema check, CLI/chat one-time steer queuing, CLI/chat FIFO follow-up queuing, boundary-safe interrupt-submit, exact new-file approval, approve-all for multiple pending writes, structured reply-file snapshot acknowledgement, pending diff preview in resume, command-output previews in resume, working-memory resume surfacing, focused chat diff/test/command previews, line-based read, large-file dry-run edit, workbench/global work-session ledgers, chat resume world state, timeline surfacing, side-effect recovery review context, and safe read auto-recovery.
- `uv run python -m py_compile src/mew/commands.py src/mew/cli.py src/mew/work_session.py src/mew/dogfood.py` current: pass.
- `uv run pytest -q` last observed before the steer lane: `802 passed, 6 subtests passed`.
- `uv run pytest -q tests/test_work_session.py` last observed before the steer lane: `192 passed`.
- `./mew dogfood --scenario work-session --cleanup --json` last observed before the steer lane: pass across 39 commands, including CLI/chat cell pane checks.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, chat-cockpit, and work-session; work-session includes 39 commands and cell pane checks.
- `codex-ultra` human-role cells dogfood current: verified stable CLI/chat cell rendering and exposed five approval/control issues; the current code fixes four directly and narrows the remaining active in-flight cell work.
- `mew work 88 --follow --auth auth.json --allow-read . --max-steps 2` current: real Codex Web API dogfood verified active cells plus compact completed cells and finished with a less-noisy cockpit assessment.
- `mew work 86 --follow --auth auth.json --allow-read . --act-mode deterministic --max-steps 2` current: real Codex Web API dogfood inspected the new cell implementation, produced stable cells after each step, and identified the row-noise polish that was fixed in this session.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, chat-cockpit, and work-session after the latest cockpit help/resume next-action changes.
- `uv run pytest -q tests/test_work_session.py` current: `179 passed`, including task-specific idle resume `next_action`.
- `./mew dogfood --scenario work-session --cleanup --json` current: pass across 37 commands after task-specific live resume next-action changes.
- `mew work 74 --live --auth auth.json --allow-read . --compact-live` current: resident self-improvement buddy session #100 traced the taskless live next-action wording to `build_work_session_resume`.
- `uv run pytest -q tests/test_commands.py` current: `149 passed, 4 subtests passed`, including task-first live help coverage.
- `mew work 73 --live --auth auth.json --allow-read . --compact-live` current: resident self-improvement buddy session #99 identified the task-first live help gap and finished with a concrete edit recommendation.
- `uv run pytest -q` current: `703 passed, 6 subtests passed`.
- `./mew dogfood --scenario work-session --cleanup --json` current: pass across 37 commands, including no-trailing-newline large edit diff stats.
- `./mew dogfood --scenario chat-cockpit --cleanup --json` current: pass across 11 commands, including `code_quiet_startup_is_silent`.
- `claude-ultra` final review of `348677e..HEAD` current: no blockers; verified `702 passed`, no-newline diff stats, updated dogfood command counts, quiet code dogfood, and roadmap claims.
- `codex-ultra` retest of prior human-role frictions current: scoped resume naming, self-improve work cwd, explicit dogfood cleanup reason, and code quiet passed; remaining no-trailing-newline diff-stat edge was reproduced and fixed in `85e2d07`.
- `claude-ultra` review of `b18880d..5a6f3fd` current: no blockers for compact labels, unclipped diff stats, explicit dogfood cleanup skip reasons, and self-improve cwd output; minor notes were schema/memory/test-coupling caveats.
- `./mew dogfood --scenario all --cleanup --json` current: pass across interrupted-focus, trace-smoke, memory-search, runtime-focus, chat-cockpit, and work-session; temporary workspace removed.
- `codex-ultra` human-role dogfood on current HEAD current: deterministic dogfood `all` and `trace-smoke`, temp self-improve/work-session/chat probes, and targeted `tests/test_self_improve.py tests/test_work_session.py tests/test_dogfood.py` passed; reported diff-stat, cleanup, cwd, and scoped resume frictions.
- `uv run pytest -q tests/test_work_session.py` current: `177 passed`.
- `uv run pytest -q tests/test_self_improve.py` current: `18 passed, 2 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-work-session-after-batch-fields --json` current: pass across 36 commands.
- `claude-ultra` review of `d42a9b4..7735215` current: no blockers; minor JSON/text timestamp mismatch and commands-pane scope notes were triaged, with the timestamp mismatch resolved in `0523395`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `323 passed, 4 subtests passed`.
- `codex-ultra` human-role dogfood on HEAD `600bb1a` current: persisted gate reuse, closed/done read-only probes, combined focused panes, and final `git status --short` clean.
- `claude-ultra` review of `d6caf93..a7ace9c` current: follow-up materially addressed persisted gates, review probes, and multi-pane composition; remaining cosmetic fallback and double-computation notes were resolved in `600bb1a`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_run_tests_missing_executable_reports_not_found tests/test_work_session.py::WorkSessionTests::test_work_session_write_tools_default_to_dry_run_and_can_apply_with_verification` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `164 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-work-view-flags --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_commands.py::CommandTests::test_task_list_can_filter_by_status` current: `1 passed`.
- `uv run pytest -q tests/test_commands.py` current: `147 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-task-list-limit --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_commands.py::CommandTests::test_chat_quiet_suppresses_startup_noise tests/test_commands.py::CommandTests::test_chat_kind_filter_scopes_startup_brief_and_unread` current: `2 passed`.
- `uv run pytest -q tests/test_commands.py` current: `147 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-chat-quiet --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_search_text_accepts_query_that_starts_with_dash tests/test_work_session.py::WorkSessionTests::test_search_text_marks_truncated_when_more_matches_exist` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `164 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-dash-query-search --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_commands.py::CommandTests::test_task_list_can_filter_by_status` current: `1 passed`.
- `uv run pytest -q tests/test_commands.py` current: `146 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch` current: `1 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `163 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-imported-symbol-prompt --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_commands.py::CommandTests::test_task_list_can_filter_by_kind tests/test_commands.py::CommandTests::test_task_list_can_filter_by_status` current: `2 passed`.
- `uv run pytest -q tests/test_commands.py` current: `146 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-task-list-status --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_scripted_chat_defers_startup_controls_to_scoped_work_command` current: `1 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `163 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-cockpit-resume-controls --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_commands.py::CommandTests::test_chat_self_improve_native_skips_programmer_plan tests/test_commands.py::CommandTests::test_chat_self_improve_start_opens_native_work_session` current: `2 passed`.
- `uv run pytest -q tests/test_commands.py tests/test_self_improve.py` current: `162 passed, 6 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-chat-self-improve-output --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_native_skips_programmer_plan tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_start_session_uses_native_work tests/test_commands.py::CommandTests::test_chat_self_improve_native_skips_programmer_plan tests/test_commands.py::CommandTests::test_chat_self_improve_start_opens_native_work_session` current: `4 passed`.
- `uv run pytest -q tests/test_self_improve.py tests/test_commands.py` current: `162 passed, 6 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-self-improve-output --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_model_batch_reports_truncated_pipe_search_text_queries tests/test_work_session.py::WorkSessionTests::test_work_model_batch_flattens_pipe_search_text_queries tests/test_work_session.py::WorkSessionTests::test_work_session_stop_request_is_consumed_before_model_step tests/test_work_session.py::WorkSessionTests::test_work_recovery_plan_includes_side_effect_review_context tests/test_work_session.py::WorkSessionTests::test_work_recover_session_reports_review_context_for_side_effects` current: `5 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `308 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-claude-review-fixes --json` current: pass across 36 commands.
- `claude-ultra` review of `bb5ec1a`, `68cb9ee`, and `d729264` current: no critical issues; follow-up addressed silent batch truncation, stop-request label clarity, and remaining concrete review hints.
- `uv run pytest -q tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_start_session_rejects_dispatch_and_cycle tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_native_rejects_dispatch tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_native_rejects_cycle tests/test_self_improve.py::SelfImproveTests::test_cli_self_improve_start_session_uses_native_work` current: `4 passed, 2 subtests passed`.
- `uv run pytest -q tests/test_self_improve.py tests/test_brief.py tests/test_commands.py` current: `199 passed, 6 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-self-improve-alias-tests --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Pick the next smallest improvement to make mew's dogfood..."` created task #56/session #80; read-only `./mew work 56 --live ...` identified missing `--start-session` invalid-combination parity coverage.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool` current: `1 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `307 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-specific-recovery-hints --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Pick the next smallest non-UI mew improvement..."` created task #55/session #78; after rejecting an already-covered fallback-memory idea, session #79 identified generic `<path>` interrupted recovery hints as the concrete non-UI recovery slice.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_workbench_surfaces_work_session_reentry_guidance tests/test_work_session.py::WorkSessionTests::test_work_live_result_pane_shows_search_matches tests/test_work_session.py::WorkSessionTests::test_work_session_stop_request_is_consumed_before_model_step tests/test_work_session.py::WorkSessionTests::test_work_live_result_pane_falls_back_to_search_snippets_without_matches` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `307 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-claude-ux-followups --json` current: pass across 36 commands.
- `claude-ultra` review of `68bc997`, `94e9a99`, and `713474d` current: no critical or JSON-breaking issues; follow-up addressed chat reentry discoverability, live search context loss, and stop-branch label coverage.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch tests/test_work_session.py::WorkSessionTests::test_work_model_splits_pipe_search_text_queries tests/test_work_session.py::WorkSessionTests::test_work_model_batch_flattens_pipe_search_text_queries` current: `3 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `307 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-pipe-search-normalize --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Pick the next smallest mew improvement that is not about..."` created task #53/session #76; read-only `./mew work 53 --live ...` exposed model misuse of pipe-separated `search_text` queries against fixed-string search.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_show_active_includes_next_cli_controls tests/test_work_session.py::WorkSessionTests::test_work_session_controls_prefer_local_mew_executable tests/test_work_session.py::WorkSessionTests::test_work_session_stop_request_is_consumed_before_model_step` current: `3 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `305 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-labeled-cli-controls --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Pick the next smallest Milestone 2 improvement..."` created task #52/session #75; read-only `./mew work 52 --live ...` identified unlabeled active `Next CLI controls` as the next small live/follow UX slice.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_live_result_pane_shows_search_matches tests/test_work_session.py::WorkSessionTests::test_work_live_result_pane_falls_back_to_search_snippets_without_matches` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `305 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-compact-live-search --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Stabilize the live/follow reasoning and status pane..."` created task #51/session #74; read-only `./mew work 51 --live ...` identified noisy live `search_text` snippet rendering as the smallest next slice.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_chat_work_session_can_request_stop tests/test_work_session.py::WorkSessionTests::test_chat_work_session_stop_keeps_pending_approval_controls tests/test_work_session.py::WorkSessionTests::test_workbench_surfaces_work_session_reentry_guidance` current: `3 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_parent_path_for_observation_handles_common_paths tests/test_work_session.py::WorkSessionTests::test_retry_failed_source_does_not_hide_retry_call_reobserve tests/test_work_session.py::WorkSessionTests::test_work_resume_suggests_parent_inspection_after_failed_read_file tests/test_work_session.py::WorkSessionTests::test_chat_work_session_stop_keeps_pending_approval_controls` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `304 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-calm-reentry --json` current: pass across 36 commands.
- `./mew self-improve --native --start-session --force --ready --focus "Reduce repeated reentry material..."` created task #50/session #73; `./mew work 50 --live --auth auth.json --allow-read . --max-steps 2 --compact-live ...` identified the workbench reentry command duplication slice.
- `./mew work 50` current: Reentry now shows one `resume:` line and no repeated `chat: /work-session resume ...` line.
- `claude-ultra` review of `5398723` and `c99e5ba` current: no critical issues; low-risk findings around stop-requested pending approvals, retry_failed coverage, and parent path edge cases were addressed in the follow-up slice.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_resume_suggests_safe_reobserve_after_failed_edit tests/test_work_session.py::WorkSessionTests::test_work_resume_suggests_parent_inspection_after_failed_read_file tests/test_work_session.py::WorkSessionTests::test_work_resume_retries_interrupted_read_file tests/test_work_session.py::WorkSessionTests::test_work_resume_uses_recorded_output_review_after_failed_command tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool` current: `5 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `301 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-safe-reobserve-tight --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool tests/test_work_session.py::WorkSessionTests::test_chat_work_session_can_request_stop tests/test_work_session.py::WorkSessionTests::test_work_session_stop_takes_precedence_over_session_flag tests/test_brief.py::BriefTests::test_next_move_coding_filter_in_empty_project_suggests_task_creation` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_brief.py tests/test_commands.py` current: `335 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-review-fixes --json` current: pass across 36 commands.
- `/Users/mk/dev/personal-pj/mew/mew focus` and `/Users/mk/dev/personal-pj/mew/mew next` in `/tmp/mew-empty-check` current: default next remains wait, with a `Coding:` task-creation suggestion.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_resume_suggests_safe_reobserve_after_failed_edit tests/test_work_session.py::WorkSessionTests::test_work_session_resume_next_action_uses_latest_tool_status` current: `2 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-safe-reobserve --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_brief.py::BriefTests::test_next_move_coding_filter_suggests_native_self_improve_when_no_tasks tests/test_brief.py::BriefTests::test_next_move_coding_filter_in_empty_project_suggests_task_creation` current: `2 passed`.
- `/Users/mk/dev/personal-pj/mew/mew focus --kind coding` and `/Users/mk/dev/personal-pj/mew/mew next --kind coding` in `/tmp/mew-empty-check` current: both suggest `mew task add ... --kind coding --ready`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_stop_request_is_consumed_before_model_step tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool` current: `2 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-reentry-controls --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_note_records_user_note` current: `1 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_model_incomplete_edit_reads_target_before_retrying tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool tests/test_work_session.py::WorkSessionTests::test_work_recovery_next_action_prioritizes_missing_touched_paths tests/test_work_session.py::WorkSessionTests::test_work_model_incomplete_edit_reads_target_before_retrying` current: `3 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-world-aware-recovery --json` current: pass across 36 commands.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_model_incomplete_edit_reads_target_before_retrying tests/test_work_session.py::WorkSessionTests::test_work_think_prompt_guides_independent_reads_to_batch` current: `2 passed`.
- `uv run pytest -q tests/test_runtime.py::RuntimeTests::test_think_phase_retries_malformed_model_json_once tests/test_runtime.py::RuntimeTests::test_think_phase_retries_transient_model_errors` current: `2 passed`.
- `uv run pytest -q tests/test_work_session.py::WorkSessionTests::test_work_session_recovers_interrupted_read_tool` current: `1 passed`.
- `./mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-recovery-source-context --json` current: pass, including safe read auto-recovery and side-effect recovery review context across 36 commands.
- `uv run pytest -q tests/test_brief.py tests/test_commands.py tests/test_work_session.py` current: `310 passed, 4 subtests passed`.
- Focused regression tests for default `next` coding surfacing, workbench generated-focus elision, and closed-session restart guidance current: `3 passed`.
- Focused regression tests for `mew code` quiet unread defaults, session startup, coding work-mode entry, and read-only default clearing current: `3 passed`.
- `uv run pytest -q tests/test_codex_api.py tests/test_work_session.py::WorkSessionTests::test_work_ai_can_stream_model_deltas_to_progress tests/test_work_session.py::WorkSessionTests::test_work_follow_streams_model_deltas_by_default` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `148 passed`.
- `uv run pytest -q tests/test_dogfood.py tests/test_work_session.py` current: `134 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_write_tools.py` current: `98 passed` (last observed before the latest approval-continuity tests).
- `uv run pytest -q tests/test_commands.py` current: `135 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_commands.py tests/test_brief.py` current: `162 passed, 4 subtests passed` (last combined run before the latest focus-coding-line test).
- `uv run pytest -q tests/test_brief.py` current: `36 passed`.
- `uv run pytest -q tests/test_dogfood.py` current: `32 passed`.
- `uv run pytest -q tests/test_self_improve.py` current: `16 passed` (last observed in this long-session cycle before the latest cockpit edits).
- `uv run pytest -q tests/test_dogfood.py::DogfoodTests::test_run_dogfood_chat_cockpit_scenario tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario` current: `2 passed`.
- `uv run python -m compileall -q src/mew` current: pass.
- `uv run mew dogfood --scenario chat-cockpit --cleanup` current: pass, including scoped chat startup, scoped `/tasks`, scoped `/work`, scoped active-session controls, scoped `/work-session`, `/follow` discoverability, `/work-mode` toggles, chat transcript logging, `mew code` entry, short startup controls, and read-only default clearing.
- `uv run mew dogfood --scenario work-session --workspace /tmp/mew-dogfood-approve-all-status --json` current: pass, including exact new-file approval, approve-all for multiple pending writes, pending diff preview in resume, command-output previews in resume, working-memory resume surfacing, focused chat diff/test/command previews, line-based read, large-file dry-run edit, workbench/global work-session ledgers, chat resume world state, timeline surfacing, side-effect recovery review context, safe read auto-recovery, and 36 commands.
- `uv run mew dogfood --scenario all --cleanup` current: pass, including `chat-cockpit` with transcript logging and `mew code` entry checks, plus `work-session`.
- `uv run mew doctor` current: state/runtime/auth ok.
- `codex-ultra` focused reviews of the low-intent wait guard, stale work-session filtering/closing, and self-improvement context changes found no concrete issues after fixes.
- `mew work --live` dogfood as a self-improvement buddy exposed repeated stale-topic selection; self-improvement descriptions now put recent completed commits before a coding-only focus view.
- `mew code` real dogfood task #48 used Codex Web API as a resident buddy to create `experiments/mew-dream`, approve gated writes, fix a pytest import failure, run the generated CLI, and commit the result; it exposed the missing-write-root and stale-verify approval issues fixed in commits `f9f8ddf` and `b341ec9`.
- `codex-ultra` focused re-review of stop/context/recovery fixes: no concrete remaining issues found.
- `codex-ultra` read-only external-use test: usable for short bounded resident coding sessions; main remaining gap is the REPL-style cockpit and reentry discovery.
- `codex-ultra` reentry retest after cockpit changes: strict chat resume order and missing chat resume hints are mostly fixed; remaining UX gaps are broader cockpit polish and quiet-chat affordances.
- `codex-ultra` human-role E2E round 2 verified exact `/tmp` new-file approval, sibling write rejection, work-session/global ledgers, and `uv run pytest tests/test_work_session.py -q` with `88 passed`.
- `codex-ultra` human-role E2E round 3 verified that `brief --kind coding`, `status --kind coding`, missing-parent write-root errors, and global work-session ledgers pass without tracked file edits.
- `codex-ultra` approval-UX human-role E2E after inline defaults verified pending diff previews, explicit and TTY-default inline prompts, verifier display, opt-out behavior, verification/writes ledgers, and clean repo state. It found two continuity bugs: generated controls dropped `--no-prompt-approval`, and `approve-tool` ignored session default verification commands; both now have regression tests and fixes.
- `codex-ultra` approval-UX retest after continuity fixes verified that `--no-prompt-approval` stays in next controls without reintroducing `--prompt-approval`, CLI and chat approvals reuse default verification commands, and focused `--diffs`/`--tests` plus `/work-session diffs`/`tests` show useful cockpit panes. No remaining bug was found in that scope.
- `claude-ultra` review of the working-memory reentry slice found two correctness concerns: model-written verification claims could outlive later failed tests, and old memory could shadow newer turns. Both are fixed with observed verification override, stale markers, and regression tests; Claude re-review reported no blockers.
- Work-session unit coverage now includes a deterministic resident THINK path proving model-returned `working_memory` is journaled and surfaced in the resume, not only manually synthesized state.
- `claude-ultra` review during the 2026-04-17 long session judged mew materially closer to a usable AI shell/body and identified live cockpit fluency, recovery breadth, and day-scale persistence as the top blockers.
- `claude-ultra` recheck after the 2026-04-17 cockpit work started successfully and identified `/work` scope leakage and mixed `/continue` options+guidance as the highest-leverage cockpit bugs; both were fixed in commit `1f97120`.
- `claude-ultra` Milestone 2 review after pending diff previews judged the cockpit direction coherent and recommended consolidating inline approval as the next small slice; interactive live/do approval prompts now have explicit default/force/opt-out semantics.
- Isolated `codex-ultra` agent-as-human E2E in `/tmp/mew-agent-human-role-20260417-013828` ran `chat-cockpit`, `work-session`, `all`, manual `chat --kind coding`, work-session reentry, line reads, and a live read-only resident model step. It judged mew usable for narrow task-coding shell work and found three papercuts: source-checkout command prefixes, timeline failure summaries, and line-window truncation wording; all three were fixed in commit `4e8ecf1`.
- Isolated `codex-ultra` retest in `/tmp/mew-agent-human-role-retest-20260417-015606` verified the three papercut fixes: `./mew` next controls, timeline failure text, and line-window `has_more_lines` without `(truncated)`; `chat-cockpit` dogfood also passed.
- `mew chat --kind coding`, `mew next --kind coding`, and `mew status --kind coding` were dogfooded locally after the scoped-chat changes; startup and slash-view scoping stayed quiet and task/coding-focused.
- `mew work --live` task #44 dogfood verified the quieter deterministic live path, then used line-based reads and large-file edit support to reach and approve a real cockpit improvement.
- `claude-ultra` reviews found no ship-blockers after fixes for work-session global ledgers and status/brief kind scoping.
- Mew dogfood task #27 used `mew work --live` with Codex Web API in this repository; it found high context pressure from broad batch reads, which led to smaller model read defaults and diffstat-first model `git_diff`.
- Mew dogfood task #28 used `mew work --live` with Codex Web API as a read-only self-improvement buddy; it reentered docs, chose `finish`, and exposed the need to distinguish session finish from task completion.
- `codex-ultra` distracted-user dogfood found that generated live/continue controls failed when only `~/.codex/auth.json` existed; work/do/chat defaults now preserve normal auth fallback instead of baking in `--auth auth.json`.
- `claude-ultra` product evaluation at HEAD before inline approval judged mew `NOT_YET` versus Claude Code/Codex CLI, with the top one-hour recommendation to add an inline live write approval loop; `--prompt-approval` is now the first implementation slice of that recommendation.
- `codex-ultra` focused retest after live-gate preflight, inline approval, interrupted recovery context, active-focus surfacing, and state backup found no concrete regressions in that scope.
- `claude-ultra` review of the 2026-04-17 recovery/cockpit commits found no crash-level issues; follow-up fixes made empty `edit_file.old` re-observe instead of failing and changed world-state recovery wording from touched paths to observed paths.
- `codex-ultra` human-role recovery dogfood verified focus/next/code routing, terse `mew code` cockpit controls, conservative side-effect recovery review after repair, safe read/git auto-recovery, recent-session listing, and work-session dogfood pass; it found empty-project self-improve routing, stop-request control conflict, and recovered-failure presentation issues, all now fixed.
- `codex-ultra` human-role retest after the follow/work-mode slice verified four targeted fixes: explicit `--follow --max-steps 1` is honored, chat `/follow` controls include `--max-steps 10`, world-state git status uses allowed repo roots from disposable cwd, and `glob` skips cache/venv directories. Repo status stayed clean.
- `claude-ultra` review after the follow interrupt/streaming/max-step work judged mew coherent but not yet preferred over Claude Code/Codex CLI; top blockers were thin streaming UX, shallow interrupt cancellation, and max-step note scope.
- `codex-ultra` human-role cockpit dogfood verified `/c`, `/follow`, max-step notes, and Ctrl+C reentry in a temporary workspace. It judged mew usable for short bounded read-only coding sessions and found three papercuts: sharp initial work-mode blank lines, repeated full controls, and verbose max-step notes; all three now have focused fixes and regression tests.
- Mew dogfood task #46 used `mew work --follow` with Codex Web API as a resident buddy after the 2026-04-17 cockpit changes; it verified grouped result panes with duration output and recorded that the remaining live-output gap was dense tool-result rendering, which led to multiline section indentation and direct command cwd/stdout/stderr rendering.
- `codex-ultra` human-role retest after the 2026-04-17 cockpit transcript work found three issues: non-git initial world-state resume showed `(no files)`, stale working memory rendered an old `next_step` too strongly, and `effects 10` / `runtime-effects 10` failed despite analogous chat grammar. Follow-up retest verified all three fixed with no repo edits.
- Live Codex Web API dogfood on task #46 exposed that SSE responses can omit `content-type`, causing final text to work while live deltas were dropped; after the fix, session #40 showed batched `model_delta` lines in the thinking pane with no stderr token spam.
- Mew buddy dogfood on task #46 exposed that one-line `search_text` hits could make the resident model misread ROADMAP_STATUS; after adding bounded context snippets and clarifying the status wording, session #44 correctly distinguished shipped cockpit panes from the remaining live reasoning/status-pane gap.
- Live Codex Web API dogfood on task #46 session #45 verified compact follow no longer repeats the same raw JSON in both `model_delta` and `stream_preview`; the planning summary kept `model_stream` metrics plus summary/reason.
- `claude-ultra` evaluation after the live-delta/search-snippet work said mew is conditionally worth inhabiting for short bounded coding tasks, but still behind Claude Code/Codex CLI for sustained interactive coding; its top 1-2 hour recommendation was readable compact rendering of plan-shaped model deltas.
- Live Codex Web API dogfood on task #46 session #46 verified compact follow now emits readable `summary_delta`, `action_delta`, and `reason_delta` lines instead of raw JSON `model_delta` text.
- Focused local validation verified that chat `/work-session` Inspect and Advanced controls now preserve a scoped `--allow-read sample` default and no longer suggest `--allow-read .` for that session.
- `codex-ultra` isolated human-role E2E after search-snippet/live-delta work judged mew usable for bounded supervised coding/task work and found six papercuts: model-delta ordering, mid-word guidance clipping, chat read-gate broadening, `.` touched-file noise, missing top-level workbench reentry notes, and missing-executable `exit=None` wording. This session fixed the read-gate broadening, guidance clipping, touched-file noise, top-level reentry block, and missing-executable wording.
- `claude-ultra` priority review ranked `mew work <task>` missing reentry guidance as the highest-leverage front-door issue and mid-word guidance clipping second; both are fixed in this session.
- `codex-ultra` retest after those fixes found that CLI scoped resume preserved read roots, but chat `/work-session resume <task> --allow-read <root>` still printed broadened Next controls and command/test panes still showed `exit=None`; both follow-up issues are now fixed with regression tests.
- `codex-ultra` focused retest of chat scoped resume controls and missing-executable panes passed against the current implementation: scoped slash-command resume printed `sample` controls, no `.` controls appeared in that command block, and resume/commands/tests panes used `exit=unavailable` plus normalized `executable not found` text. The agent noted its final clean-tree check saw concurrent local edits from this session, not test-created changes.
- Mew dogfood session #48 used Codex Web API as a read-only buddy after the front-door workbench change; it reentered task #46, inspected `ROADMAP_STATUS.md`, and recorded the next non-duplicative Milestone 2 slice as stabilizing the continuous reasoning/status pane and reducing repeated reentry material during long sessions.
- Mew dogfood session #48 later verified the live working-memory pane with real Codex Web API output: the closed live result printed `memory_hypothesis`, `memory_next`, and `memory_verified` in the compact `session` section.
- `codex-ultra` cockpit evaluation recommended the smallest next slice as surfacing active work-session `working_memory` inside the live result cockpit; this is now implemented in `format_work_live_step_result` with stale-memory labeling.
- `claude-ultra` cockpit evaluation recommended a recurring-failure ribbon for repeated tool failures; this is now implemented by deriving repeated tool/target/error groups from existing work-session history and surfacing them in resume/live result views.
- Focused dogfood of `mew work <task-id>` after the recurring-failure slice exposed old system max-step boundary notes crowding the front-door reentry block; workbench reentry now prefers user/model notes and hides those boundary notes while full resumes keep the audit trail.
- Follow-up dogfood of `mew work 46` exposed repeated `Work session finished:` task notes crowding the same front-door reentry block; workbench reentry now collapses older finish notes and keeps the latest one visible.
- Full `mew work --session --resume` dogfood exposed repeated identical one-shot guidance under every recent decision; resume text now prints the first guidance and references later duplicates as `same as #...`, preserving context without replaying the same paragraph.
- `codex-ultra` human-role retest after the reentry-noise work found the front-door behavior passing, then flagged `dogfood --json` as too large for practical terminal use; scenario JSON now stores compact command tails and clipped observed values instead of full command stdout/stderr and large diffs.
- Scenario `dogfood --json` now prints a summary JSON shape by default and leaves full command/observed details to `--report`; the work-session scenario stdout dropped from roughly 98KB after compaction to about 3.3KB while keeping pass/fail check names.
- Mew buddy dogfood session #50 exposed that a model-selected `search_text` action with `pattern=*.md` still searched Python files; `search_text` now honors optional glob filters from resident actions and the CLI, reducing noisy false-scope search results in cockpit output.
- The same session showed that three broad model-selected searches could push resume context to medium pressure; model-selected `search_text` now defaults to 20 matches and caps explicit requests at 50, while manual CLI searches keep their broader defaults.
- `claude-ultra` cockpit review after the reentry-noise work recommended deduping the front-door workbench against the full resume; `mew work <task-id>` now leaves guidance snapshots and finish-only task-note history to `--session --resume` instead of replaying them in the compact Reentry block.
- Mew buddy dogfood session #51 found a suspected `search_text.truncated` edge case during read-only retest; focused regression coverage now proves overflow beyond `max_matches` reports `truncated=True`, turning the dogfood concern into a preserved contract.
- The same retest exposed that a workbench whose only recent note was a system max-step boundary note could still show that note because of a fallback path; boundary-only system notes now stay hidden in the front-door Reentry block.
- Empty work-session front-door summaries no longer render `last_tool=#`; the field appears only when a real latest tool call exists.
- Default `mew focus` now surfaces a `Coding:` next-move line when coding work exists, so stale non-coding questions no longer completely hide the native coding cockpit entrypoint; `--kind coding` remains the scoped quiet view.
- Default `mew next` now also prints a secondary `Coding:` move when coding work exists but the global next action is blocked by unrelated non-coding work, preserving the single primary next action while keeping the coding cockpit discoverable.
- `mew work <task-id>` now elides embedded generated `Current coding focus` blocks from long self-improvement task descriptions, leaving the real focus and constraints without replaying a nested `Mew focus` view.
- Closed task-specific work-session resumes now suggest the task-specific restart command, such as `./mew work 46 --start-session`, instead of a generic `mew work --ai` path.
- `mew code [task-id]` now provides a single coding-cockpit entrypoint that starts or reuses a task work session, scopes chat to coding, enables work-mode, hides unread outbox/runtime activity by default, and caches safe `/continue` defaults. Its startup controls collapse to `/c`, `/follow`, and `/continue <guidance>` while detailed flag-heavy commands stay behind `/help work`; `--read-only --no-verify` clears cloned write/shell/verify defaults, so a read-only cockpit cannot inherit stale side-effect gates from an older session.
- `mew code` now keeps compact `/c` and `/follow` primary controls after a live `/continue` step, instead of expanding cached auth/read/write/verify flags back into the main cockpit surface.
- `mew code --read-only --no-verify` now updates an existing active coding session even when no task id is supplied, so attaching read-only cannot silently keep stale write/verify gates.
- `mew code <text>` now explains that an existing task id is required and prints the exact `mew task add ... --kind coding` command to create the task.
- In non-mew empty projects, `mew focus --kind coding` and `mew next --kind coding` now suggest creating a coding task instead of routing to mew self-improvement; mew source checkouts still keep the self-improvement shortcut.
- `mew code` now uses a compact startup brief (`runtime`, task count, unread count, next move, and active session when present) instead of dumping the full general chat brief, keeping coding entry calmer while `/brief` remains available inside chat.
- `mew next` and `mew focus` now point fresh or active coding work at `mew code <task-id>` as the quiet cockpit entry instead of surfacing `mew work --start-session` or the full flag-heavy `mew work --live ...` command in the primary next-action line.
- Done-task work sessions no longer capture the default active cockpit, and attempts to start or run a new resident work session on a done task now ask for the task to be reopened first.
- Mew buddy dogfood session #99 chose the smallest visible cockpit polish: `/help work` now documents task-first live usage (`/work-session <task-id> live --allow-read .`) alongside task-first resume, preserving the accepted command order in the focused chat help.
- Mew buddy dogfood session #100 then inspected README/help/test command wording and exposed that idle resume `next_action` still pointed at a taskless `mew work --live`; resume now points at `mew work <task-id> --live` when the task id is known.
- Mid-loop steer now has an explicit CLI/chat lane via `mew work --steer` and `/work-session steer`, with regression coverage for next-step model guidance injection and stop-request precedence.
- Live/follow work runs now write `.mew/follow/latest.json` and `.mew/follow/session-<id>.json` with the latest step, resume bundle, cells, and next controls, creating the first structured follow cockpit artifact for another model or UI to observe.
- `mew work --reply-file reply.json` now applies safe structured observer replies back into an active work session, covering `steer`, `followup`, `interrupt_submit`, `note`, `stop`, and dry-run write `reject` actions while leaving approval gates explicit.
- The follow snapshot contract now includes `schema_version`, heartbeat/process metadata, `session_updated_at`, `reply_command`, and `reply_template`; applying a reply file rewrites the snapshot with `mode=reply_file`, and no-active reply files fail nonzero instead of silently succeeding.
- `docs/FOLLOW_REPLY_SCHEMA.md` documents the local snapshot/reply contract for another model or UI.
- `mew work <task-id> --reply-schema --json` prints the current session's structured observer reply contract and ready-to-write template, so an external UI or model does not have to scrape `.mew/follow/latest.json` first.
- `mew work --queue-followup "..."`, chat `/work-session queue ...`, and reply-file `followup` queue FIFO user input for later live/follow steps; pending steer still wins the next step, and queued follow-ups are consumed one at a time only after steer is clear.
- `mew work --interrupt-submit "..."`, chat `/work-session interrupt ...`, and reply-file `interrupt_submit` request a boundary stop and preserve the submitted text as pending steer; if the current live/follow loop still has another step, it skips the interrupted tool action and immediately replans with that text.
- Reply files can now include `observed_session_updated_at`; stale observer replies are rejected before mutation when the active session has moved on.
- Reply-file `reject` now shares the pending dry-run write/edit guard, rejects replayed reject actions, and bumps the work-session `updated_at` like the other reply actions.
- Reply files now require `schema_version: 1` and `observed_session_updated_at`, making the observer contract strict rather than best-effort.
- `dogfood --scenario work-session` now covers a deterministic structured reply-file loop, session-specific reply schema, FIFO queued follow-up path, and boundary-safe interrupt-submit path, so the observer interface is part of recurring dogfood.
- Chat `/self start ...` now prints the same native `follow:` command as CLI `mew self-improve --start-session`, so the self-improvement entrypoint points at the compact continuous cockpit from both interfaces.
- Real `mew code` dogfood task #94/session #120 used saved coding-cockpit gates, followed the resident model through a 4-step loop, applied a tiny help-text polish, and verified it with `uv run pytest -q tests/test_work_session.py -k interrupt_submit`.
- Native self-improve buddy task #95/session #121 then identified that compact `Next controls` lost saved read gates on `/work-session resume`; compact controls now preserve the same read flags as the full cockpit view.
- Native self-improve dogfood tasks #102/#103 exercised the resident loop on
  current HEAD: #102 correctly chose not to make an unjustified weak edit, while
  #103 identified a concrete CLI/chat self-improve dry-run output inconsistency.
  CLI dry-run self-improve output now includes the originating plan id, matching
  chat. The same dogfood pass exposed invalid closed-session resume controls
  for done tasks; done-task resumes now point to
  `mew task update <id> --status ready` instead of an impossible
  `mew work <id> --start-session`, and `work-session` dogfood preserves that
  contract.
- Native self-improve task #113/session #136 identified a cwd/gate mismatch in
  native self-improve controls: the output printed `work cwd: <task cwd>` but
  still suggested `--allow-read .`. Controls now keep `.` only when the task cwd
  is the current directory and otherwise use the resolved task cwd.
- `claude-ultra` evaluation after passive native-work advance answered
  `CONDITIONAL`: mew is worth inhabiting for bounded, observable,
  gate-limited passive coding, but not yet for dense interactive or unattended
  multi-hour autonomy. Its highest-leverage next 1-2 hour recommendation is a
  deterministic failed passive-native-advance recovery slice: classify failed
  advance outcomes and route the next tick toward a safe recovery/ask-user path
  instead of blind retry. That first deterministic recovery slice is now
  implemented; the next gap is richer recovery action selection after the skip.
- Source edits under `src/mew/**` now surface an advisory paired-test status in
  pending approvals and approval cells. `work-session` dogfood now exercises a
  real dry-run source edit and verifies `missing_test_edit`, while the follow
  schema documents the optional observer field.
- That paired-test status now includes an inferred `suggested_test_path` for
  source-only dry-run approvals, and the resident THINK prompt tells the model
  to use it as the first test-file candidate when the write boundary stops
  before a paired test edit.
- Passive native-work skips now keep a structured
  `last_native_work_skip_recovery`, including concrete approval/reject/resume
  commands for `pending_write_approval` instead of only a skip reason. Recovery
  plan selection also ranks `needs_user_review` items by effect severity, so
  `rollback_needed` and `verify_pending` are surfaced before lower-risk
  `action_committed` or `no_action` reviews. Validated with recovery-focused
  tests, `passive-recovery-loop` dogfood, all dogfood scenarios, and full
  pytest (`913 passed, 6 subtests passed`).
- Mew buddy dogfood task #117/session #139 selected a recovery-cockpit
  hardening target after inspecting `commands.py`. The landed change preserves
  the selected recovery item's `source_index` and makes cockpit recovery
  commands use that exact item for chat auto-recovery hints instead of
  action-only matching. Validated with `tests/test_work_session.py`, all dogfood
  scenarios, and full pytest (`915 passed, 6 subtests passed`).
- `mew status` and `mew brief` now surface the latest passive native-work skip
  plus the structured recovery command, so a paused passive coding loop is
  visible without requiring raw `runtime_status` JSON inspection.
- `native-advance` dogfood now includes a runtime-owned session blocked by a
  pending dry-run write approval. It verifies passive advance does not call
  `mew work --live` through the fake executable and records concrete
  approve/reject recovery commands under `last_native_work_skip_recovery`.
- The paired-test guard for `src/mew/**` edits is now default-deny on approval:
  unpaired source edits require a same-session `tests/**` write/edit or an
  explicit `--allow-unpaired-source-edit` / reply-file
  `allow_unpaired_source_edit` override. `work-session` dogfood proves the
  block and audited override path.
- Codex-ultra review found and the tree now fixes three approval-gate edge
  cases: reply-file overrides require a real JSON boolean `true`, rejected or
  failed `tests/**` edits no longer satisfy source pairing, and passive
  native-work recovery for unpaired source approvals is resume-first while
  exposing the blocked approve command plus explicit override command.
- Native self-improve dogfood task #118/session #140 used mew as the coding
  buddy for a small self-improve control copy change. The resident first
  produced an unpaired source dry-run and was correctly stopped by
  `pairing_status: missing_test_edit`; after paired test dry-runs were added,
  the source edit was approved with focused pytest.
- The same post-dogfood reentry exposed stale shallow memory after completing a
  task with `mew task update --status done`; that path now shares the
  `task done` completion sync, so related questions, active work sessions,
  shallow memory, agent status, and user-reported verification are updated on
  done transitions.
- `claude-ultra` review then identified a stale-state race in work approval
  finalization: if an apply tool call disappears while a long approval is
  running, `_apply_work_approval` no longer crashes on `None`; it marks the
  source approval failed and returns a clean error.
- The same stale-finish guard is now shared by regular work tools, batch/live
  tools, and recovery retries: missing finished tool calls are surfaced as
  failed synthetic tool results instead of crashing the cockpit.
- Native dogfood task #124/session #146 tightened long-session reentry output:
  `mew work --follow` and `--compact-live` now print compact CLI controls by
  default, and code-mode `/work-session resume` keeps terse cockpit controls
  instead of expanding back into the full command list.
- Native self-improve task #125/session #147 exposed a real resident-tool
  failure: the model naturally asked `glob` for a brace list containing
  `docs/**`, `src/mew/**`, and `tests/**`. `glob` now expands brace lists,
  includes `/**/*` for recursive-directory patterns across Python versions, and
  keeps candidate results inside allowed read roots even through symlinks or
  rejected parent traversal.
- Native self-improve task #126/session #148 then chose a small UX follow-up:
  the native self-improve help and printed next commands now show
  `--compact-live`, matching the calmer long-session defaults used elsewhere.
- External observer review then identified a small but important approval
  visibility gap: top-level `pending_approvals` still only carried a short
  preview. Resume/follow JSON now includes a capped machine-review `diff` with
  `diff_truncated` and `diff_max_chars`, while terminal resume output stays on
  the concise preview.
- Follow snapshots now also carry bounded running stdout/stderr tails for
  active `run_command` and `run_tests` cells, mirrored into `resume.commands[]`
  without advancing `session_updated_at`. The mirror is timer-flushed and
  rate-capped so observer replies do not go stale just because command output
  arrived. The deterministic work-session dogfood scenario now also checks
  zero-step follow snapshots for running command/test output tails.
- Zero-step live/follow snapshot refresh now reuses an existing active work
  session without touching `updated_at` or cached default gates, so observer
  refreshes do not invalidate reply-file stale tokens or silently widen a
  cockpit's remembered authority.
- Native self-improve dogfood task #127/session #149 then selected a small
  observer discoverability follow-up: native self-improve output and help now
  show the task-scoped `mew work <task-id> --follow-status --json` command
  beside continue, follow, and resume.
- Native self-improve dogfood task #128/session #150 then selected another
  small cockpit consistency fix: native self-improve follow commands now use
  the same 10-step compact follow loop as the normal work/code cockpit, and the
  README self-improvement example shows the matching follow-status check.
- WHY_MEW bake-off task #141/session #160 proved the interrupted-verifier
  recovery path with a real Ctrl-C. The initial run exposed a gap where manual
  `mew work --tool` interruption printed a Python traceback and left the tool
  call `running` until `mew repair`; that path now catches `KeyboardInterrupt`,
  records the tool call as `interrupted`, returns structured JSON under
  `--json`, exits 130, and can be recovered with the normal
  `recover-session` verifier retry flow.
- Native self-improve task #142/session #161 then dogfooded that recovery
  surface. Mew selected a small follow-up in text-mode interrupted tool output,
  made the source edit, failed and rolled back the paired test edit, and still
  left enough durable work-session context for a supervised handoff. The landed
  follow-up always prints a task-scoped fallback `recovery_hint` if the stored
  interrupted tool call is unavailable.
- Approval recovery now handles Ctrl-C during write/edit application: the apply
  tool call is marked `interrupted`, the source dry-run approval becomes
  `indeterminate`, and pending approval controls disappear until the user/model
  reviews the resume. This avoids blind re-approval when write side effects may
  be unknown.
- `recover-session` itself is also Ctrl-C durable for retried safe tools and
  verifiers: the retry tool call is marked `interrupted`, returns code 130, and
  the original interrupted source remains unresolved rather than being falsely
  superseded.
- Work-session resume now suggests a concrete verifier for touched
  `src/mew/*.py` files when the matching `tests/test_*.py` module exists,
  reducing the B3 failure mode where a resident trusts a too-broad or wrong
  verification gate.
- Real `mew code` dogfood on task #143/session #162 exposed a front-door
  wording loop: after entering `mew code <task-id>`, the compact startup brief
  still said "Next: enter coding cockpit". Active coding cockpits now say the
  cockpit is already open and point to `/c`, `/follow`, or `/continue`.
- Follow-up task #144 captured another concrete friction from that same
  dogfood: once a resident has already read the exact line window needed for an
  edit, the THINK prompt now tells it not to reread the whole file solely to
  prepare `edit_file`.
- After Claude identified verifier trust as the highest-leverage next gap,
  task #145 added a resume-level verification coverage warning: if a mew source
  edit has an inferred matching test and the latest verifier is a different
  narrow test command, the cockpit now surfaces the expected verifier instead
  of presenting the green result without caveat.
- The smaller target remembered by task #145 also landed: when an
  `interrupt_submit` request is idle and ready to continue, chat cockpit
  controls now show `/follow` alongside `/c`, preserving the normal multi-step
  cockpit path through that recovery branch.
- Smart reentry now preserves bounded edit context: if `edit_file` fails after
  a successful line-window `read_file` on the same target, the safe reobserve
  hint keeps that `line_start`/`line_count` instead of falling back to a broad
  full-file reread.
- A follow-up self-improve pass tightened compact cockpit scanability:
  compact controls now expose `/work-session details` directly before the
  shorter `/help work` fallback, while keeping the primary `/c`/`/follow`
  section short.
- Workbench reentry now explains stale working memory with the specific
  later tool call or model turn that made it stale, so a returning resident can
  decide what to refresh without opening the full session detail view first.
- Verifier coverage warnings are no longer trapped in the full resume view:
  compact live session output and `work --follow-status` now surface the short
  warning when the latest green verifier appears to miss the edited mew source.
- Compact live/follow session output now shares the same stale working-memory
  source hints as workbench reentry, including the later tool call or model turn
  that made the recorded `next_step` unsafe to trust blindly.
- Passive runtime recovery now has a narrow write-shaped safe path: interrupted
  dry-run `write_file`/`edit_file` previews can be retried under a fresh
  `--allow-write` gate, while real apply/approval and indeterminate side effects
  remain on the human-review path.
- The dogfood suite now includes `passive-auto-recovery-write`, which exercises
  that dry-run preview recovery path and confirms the target file is unchanged.
- `mew mood` now treats weak or broken active work-session continuity as worry
  and signal output, so the passive emotional/status surface reflects when a
  resident would struggle to resume after compression.
- `mew desk` active work-session details now carry the same continuity score
  and repair hint, making the pet/status surface a viable quick reentry view
  instead of only a task/session counter.
- `mew morning-paper` now includes a `continuity_risks` field and markdown
  section when active work sessions are weak or broken, so the first-look
  morning surface no longer hides unsafe reentry state.
- Passive bundles now promote a Morning Paper `Continuity risks` item into
  the top-level Reentry hints, preventing the composed daily report from
  burying unsafe active-work state beneath ordinary article picks.
- The `continuity` dogfood scenario now plants a weak active work session and
  verifies that both `morning-paper --json` and the composed passive bundle
  surface the unsafe reentry hint.
- CLI/chat `--auto-recover-safe` now drains multiple safe read/git recovery
  items in one call when they are selected by the recovery plan. The batch
  path still stops at side-effect review barriers, follows the recovery plan's
  selected item instead of the newest interrupted safe call, and keeps the
  outer JSON `retry_tool` scalar contract while adding batch metadata and
  per-item `recoveries`.
- Passive runtime recovery now applies the same idea to runtime-owned native
  work sessions for safe read/git tools. It batches adjacent safe recoveries,
  uses a runtime-specific selector that does not cross verifier or other
  non-read barriers, tags runtime-created recovery calls, and stops to ask the
  user after a failed runtime recovery instead of continuing past it.
- Failed runtime-owned automatic recovery now becomes explicit user-facing
  context: the recovery question names the failed recovery tool/result and
  suppresses misleading lower-priority safe-read suggestions until that failure
  is inspected.
- Latest validation for the 2026-04-19 recovery/control slice:
  `uv run pytest -q` passed with 1044 tests and 30 subtests,
  `./mew dogfood --all --cleanup --json` passed all scenarios,
  `UV_CACHE_DIR=/tmp/uv-cache uv run --with ruff ruff check` passed on
  changed files, `git diff --check` passed, and codex-ultra re-review of the
  runtime recovery batch reported no findings in session
  `019da47e-e8b1-7a91-9d7c-d20f33557ffb`.

## Current Roadmap Focus

Milestone 2: Interactive Parity.

The canonical active decision is the top-level `Active Milestone Decision`.
Fresh implementation should continue dogfooding real coding changes through
`mew code <task-id>` or choose a targeted friction slice from
`mew metrics --kind coding`; either path must map to a Milestone 2 Done-when
criterion. The front-door route and core mid-loop control lanes are coherent,
and global `focus` / `next` keep the coding reentry visible even when stale
non-coding questions still need a user answer. The remaining Milestone 2 work
is making the active coding loop feel as fast and calm as Claude Code or Codex
CLI while preserving mew's persistent memory and audit trail. Same-surface
audit and verification confidence are visible cockpit/checkpoint artifacts
rather than only prompt guidance. Do not spend new long-session work on polish
or later-milestone architecture unless it directly closes a current Milestone 2
gap or reduces a measured M2 blocker.
