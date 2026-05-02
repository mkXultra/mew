# M6.24 Dossier: Long Dependency / Toolchain Build Strategy

Gap class: `long_dependency_toolchain_build_strategy_contract`

Status: active improvement-phase dossier

Primary task evidence: `compile-compcert`

Related task family: `mcmc-sampling-stan`, `protein-assembly`,
`adaptive-rejection-sampler`

Controller: `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`

Decision ledger: `docs/M6_24_DECISION_LEDGER.md`

Gap ledger: `proof-artifacts/m6_24_gap_ledger.jsonl`

Continuation design:
`docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`

Generic managed exec decision:
`docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md`

Reference audits:
`docs/REVIEW_2026-05-02_CODEX_CLI_LONG_BUILD_CONTINUATION_PATTERNS.md`,
`docs/REVIEW_2026-05-02_CLAUDE_CODE_LONG_BUILD_CONTINUATION_PATTERNS.md`

## Current Decision

Current selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> final artifact/default-smoke closeout classification -> repair or written defer
```

Broad measurement remains paused. The build-timeout recovery and long-command
continuation repairs are implemented and reviewed, and the config/source-script
external-hook repair moved the same-shape `compile-compcert` run forward. The
source-authority path-correlation speed rerun, the managed-dispatch speed
rerun, and the nonterminal-handoff speed rerun each moved the blocker forward.
The latest blocker is `compound_long_command_budget_not_attached`: the live
command combined source/configure-looking setup with OPAM install, build, and
final-smoke work, but did not get `long_command_budget`, so it was capped as a
normal shell command. The current repair is generic budget-stage promotion for
planned commands while preserving recorded attempt stage semantics and rejecting
pure source fetch/readback commands. codex-ultra approved the repair after
false-positive hardening. The same-shape speed rerun moved that gap: a managed
long command was created, failed terminally during source acquisition with
`curl` exit `22`, `timed_out=false`, and then recovery blocked the corrected
source-channel retry as `repeat_same_timeout_without_budget_change`. The current
repair separates non-timeout terminal failures from timeout-style resume
recovery. codex-ultra initial review found two integration gaps: the new
`recover_long_command` action was not routed through the managed runner, and
killed managed command status could collapse to `failed`. The follow-up repair
routes `recover_long_command` through managed execution and preserves killed /
interrupted terminal status. codex-ultra re-review approved the repair. The
same-shape speed rerun passed externally (`1/1`, runner errors `0`) and
`mew work` exited cleanly, but internal `resume.long_build_state` still reports
`status=blocked`, `source_authority=unknown`, `default_smoke=unknown`, and a
stale `dependency_generation_required` blocker from earlier evidence. The next
action is to classify that moved closeout gap before any `proof_5` escalation.

Do not broaden this repair into a full shell classifier. Use
`docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md` if future failures
suggest replacing narrow budget routing with all-command generic managed exec.

## Repair Timeline

| Stage | Trigger / result | Repair layer | Outcome |
|---|---|---|---|
| Initial speed rerun | `compile-compcert` reached real CompCert/Coq path but missed `/tmp/CompCert/ccomp` by wall time. | selected long-dependency gap | Repair needed. |
| v0 build-state progress | Preserve package/toolchain/source/build state and final-artifact completion boundary. | detector/resume + THINK guidance | Improved continuity; still missed final artifact. |
| v0 follow-up | Review fixed command-only proof and fresh-session misleading hints. | detector correctness | Approved before rerun. |
| v0.1 compatibility/continuation | Preserve invalidated toolchain/package paths, running build command, dependency-generation order, bounded timeouts. | detector/resume + THINK guidance | Exposed wall-clock/full-build target gap. |
| v0.2 wall-clock/targeted artifact | Cap tool timeout to remaining wall budget; flag untargeted full project builds for specific artifacts. | tool/runtime + detector/profile guidance | Speed `1/1`; parallel proof invalid due contention; resource-normalized proof `1/2`. |
| v0.3 compatibility override ordering | Prefer cheap source override/help probes before heavy alternate toolchain construction. | detector/resume + THINK guidance | Speed `1/1`; proof `2/3`; next failure runtime link. |
| v0.4 runtime link library | Require runtime/library link proof for compiler/toolchain source builds. | detector/resume + THINK guidance | Speed `1/1`; proof `0/1`; next failure prebuilt-vs-source ordering. |
| v0.5 prebuilt dependency override precedence | Prefer prebuilt dependencies plus source override before source-building older dependencies. | detector/resume + THINK guidance | Speed `1/1`; proof `4/5`; next failure default runtime path. |
| v0.6 default runtime link path | Treat custom `-stdlib`/`-L`/env runtime proof as diagnostic until default path proof passes. | detector/resume + THINK guidance | Speed `0/1`; behavior moved to runtime install missing library. |
| v0.7 runtime install target | Build shortest explicit runtime-library target before install/default-link smoke. | detector/resume + THINK guidance | Speed `0/1`; failure moved earlier to source archive identity + empty response. |
| v0.8 source archive identity / empty response recovery | Accept archive/tag/root identity when internal markers are coarse; recover empty assistant response. | detector/resume + recovery + THINK guidance | Speed `1/1`; proof `4/5`; next failure timed-out artifact proof calibration. |
| v0.9 timed-out artifact proof calibration | Do not mark required final artifacts proven from timed-out or nonzero commands. | instrumentation/report | Speed `1/1`; first proof_5 invalidated by auth expiry; rerun pending after OAuth refresh repair. |
| proof infra OAuth refresh | Refresh ChatGPT OAuth tokens from legacy/Codex auth shapes and retry one 401. | proof infrastructure | Auth-expiry failure removed; same-shape proof reached valid completed trials `1/2`; next failure final recovery budget. |
| v1.0 final recovery-budget reserve | Preserve recovery wall budget for long build commands that include final validation smoke. | tool/runtime | Speed `1/1`; proof `2/3`; next failure malformed JSON plan recovery. |
| v1.1 malformed JSON plan recovery | Treat backend `failed to parse JSON plan` as a recoverable one-shot transient model error. | loop recovery | Speed `1/1`; proof `1/2`; next failure timeout-ceiling full-context recovery. |
| v1.2 timeout-ceiling compact recovery | Use compact recovery context when wall-clock pressure reduces model timeout. | model context budgeting | Speed `1/1`; proof `2/3`; next failure compatibility branch budget. |
| v1.3 compatibility branch budget | Commit earlier to coherent prebuilt/external dependency compatibility branches for long source-build tasks and avoid starting the final long build after serial probes consumed the wall budget. | profile/contract | Speed `1/1`; proof_5 pending. |
| source acquisition profile | Surface VCS-generated archive fallback plus compatibility/toolchain surgery without authoritative source-channel evaluation. | source acquisition profile + detector/resume | Speed `1/1`; proof `0/1`; next failure default runtime link. |
| default runtime link failure recovery | Surface failed default compile/link smoke after compiler build as a runtime-link recovery blocker. | runtime link proof + detector/resume | Speed `1/1`; proof `0/1`; next failure vendored dependency proof surgery before supported branch. |
| v1.4 vendored dependency patch surgery | Stop local vendored/third-party dependency or proof-library mutation when source-provided external/prebuilt branch evidence exists and final artifacts are still missing. | profile/contract + detector/resume | Speed `1/1`; proof_5 was superseded by the acceptance-evidence structure repair/rerun. |
| v1.5 acceptance-evidence structure rerun | Generic command-evidence acceptance repair was reviewed, then same-shape speed rerun missed because final artifact was never built. | acceptance substrate evidence | Score `0/1`; new failure shape is narrow configure-help filtering before heavy source-toolchain build. |
| v1.6 external-branch help-probe width | Detect filtered configure/project help probes that omit external/use-external/prebuilt/system/library terms before dependency/API mismatch and version-pinned source-toolchain build. | profile/contract + detector/resume | Speed `0/1`; failure moved later to runtime subdir target recovery after `ccomp` was built. |
| v1.7 runtime subdir target path | Detect parent Makefile `No rule to make target 'runtime/lib*.a'` failures and steer to the runtime subdirectory Makefile's `all/install` continuation. | runtime link proof + detector/resume | Implemented and reviewed; speed_1 pending. |
| v1.8 source-tail clean closeout | Recognize terminal-success runtime repair plus saved archive-member readback after the verifier-passing run. | long-build reducer | Reviewed and committed; same-shape rerun exposed an earlier dependency-strategy miss. |
| v1.9 external branch attempt before source toolchain | Detect starting version-pinned OPAM/source-toolchain work after external/prebuilt branch evidence plus dependency/API mismatch but without an actual external/prebuilt/system configure attempt. | profile/contract + detector/resume | Implemented and reviewed; speed_1 pending. |
| v2.0 temp-fetch source authority | Recognize authoritative archive fetches to temp paths only when the actual fetch URL is authoritative, ordered `fetch -> mv final` occurs, and later saved archive readback proves the final path; reject header-only URL, pre-fetch move, and clipped failed-fetch stale-readback false positives. | long-build reducer | Implemented and reviewed; speed_1 pending. |
| v2.1 build-timeout recovery context | Suppress only same-evidence unreached `make install` blocker after a latest build timeout and hard-cap compact recovery context. | reducer + model context budgeting | Speed rerun moved forward: command reached `make -j"$(nproc)" ccomp` and then wall-timed out while building. This selects the long-command continuation design, not another source/toolchain repair. |
| v2.2 long-command continuation design | Adopt the shared Codex CLI / Claude Code continuation pattern: one active managed long command, durable output owner, running/yielded nonterminal evidence, owner-token poll/finalize lifecycle, and terminal-only acceptance. | tool/runtime design | Adopted durable repair. |
| v2.3 long-command continuation phase 1-3 slice | Implement `LongCommandRun` schema/output/idempotence helpers, terminal-only evidence guard, internal single-active managed runner, and reducer support for live/timed-out long command runs. | tool/runtime substrate + reducer | Implemented and codex-ultra reviewed. Next: production-visible dispatch, continuation rendering, Harbor timeout-shape reporting, transfer fixtures, then same-shape speed_1. |
| v2.4 long-command continuation phase 4-5 slice | Record start/poll/resume budget intent, typed long-command budget blocks, compact recovery continuation actions, latest long-command resume rendering, and Harbor timeout-shape reporting in transcript/summary/report. | work-loop budget + reporting | Implemented and codex-ultra approved after two request-change rounds. |
| v2.5 long-command continuation phase 6 transfer | Verify non-CompCert long-build transfer fixtures plus terminal-only proof rejection before spending the next CompCert proof. | transfer evidence | Closed locally: transfer subset `29 passed`, broader suite `1290 passed`, ruff/diff/JSONL checks passed. Next: one same-shape `compile-compcert` speed_1. |
| v2.6 config/source-script external hook evidence | Treat configure/source-script compatibility-hook variables such as `LIBRARY_* = local # external` as external/prebuilt/system branch evidence before version-pinned source-toolchain work. | profile/contract + detector/resume | Focused validation `10 passed`; broader subset `309 passed`; query-only/xtrace false positives are rejected; assignment-style external attempts clear the blocker. Local replay of the Phase 6 speed rerun now selects `source_toolchain_before_external_branch_attempt`. codex-ultra approved; same-shape speed_1 pending. |
| v2.7 runtime-link compact recovery focus | When runtime-link/default-runtime recovery is already selected, focus compact recovery on the long-build recovery decision and omit broad source/dependency rediscovery sections. | model context budgeting + prompt section routing | Focused validation `4 passed`; broader subset `302 passed`; scoped ruff/diff/JSONL passed; codex-ultra approved. Same-shape speed_1 pending. |
| v2.8 managed long-command dispatch | Wire budget-marked work commands into the managed command runner and persist `LongCommandRun` state so the continuation substrate is exercised in production work sessions. | tool/runtime dispatch + reducer state | Implemented and codex-ultra approved. Focused managed tests `4 passed`; broader long-build/work-session/Harbor/toolbox/acceptance suite `1311 passed` with one warning and `67 subtests`. Same-shape speed_1 pending. |

## Pattern Readout

- Most successful repairs are not pure prompt changes. They combine
  detector/resume state with targeted guidance.
- The repeated long-dependency chain is now dominated by ordering and
  proof-boundary contracts.
- v1.3 keeps the repair in the existing implementation profile: resume state
  surfaces `compatibility_branch_budget_contract_missing` from generic evidence
  (prebuilt package-manager dependencies, source-exposed external/prebuilt
  branch, serial probe churn, timed-out external-branch build, missing final
  artifacts) and guidance stays bounded to branch commitment plus wall-budget
  reserve.
- Prompt guidance is accumulating in the same surface. If the next failure is
  another narrow sequencing rule, evaluate a `LongDependencyProfile` or prompt
  section registry before adding another sentence.
- Resource normalization matters. Parallel proof failures can be harness
  artifacts for CPU-heavy dependency builds.
- The v0.8 speed proof patched bundled Flocq locally for Coq 8.18
  compatibility. That is useful task-solving evidence while score passes, but
  a proof miss in the same family should run this dossier preflight before more
  narrow guidance is added.
- The v0.8 proof miss was a report/resume calibration defect, not another
  prompt rule: `long_dependency_build_state` marked `/tmp/CompCert/ccomp` as
  proven after a timed-out build even though the external verifier found it
  missing.
- The v0.9 speed rerun passed external verification, but the internal final
  finish remained conservatively blocked with stale `missing_or_unproven`
  long-dependency state. Treat this as finish-ergonomics evidence, not a reason
  to skip the resource-normalized proof.
- The first v0.9 resource-normalized proof_5 is not clean score evidence:
  `auth.plus.json` expired mid-run and four trials hit `HTTP 401 token_expired`.
  Treat this as proof-infrastructure evidence. Rerun the same shape after Codex
  OAuth refresh is validated before selecting another mew-core repair.
- The OAuth-refresh proof rerun is clean auth evidence: no `token_expired`
  recurrence. The failed valid trial repeated the runtime-link class, but the
  differentiator was exhausted recovery budget, not missing runtime-link policy:
  a passing contrast trial used the already-known runtime-library build/install
  recovery route successfully.
- The v1.0 recovery-budget same-shape speed proof passed `1/1`: `mew work`
  finished cleanly, built `/tmp/CompCert/ccomp`, installed default runtime
  support, ran a default-path smoke, and the external verifier passed. Escalate
  to resource-normalized proof_5 before any next repair or broad measurement.
- The v1.0 resource-normalized proof miss is not another long-dependency
  sequencing rule. The failed valid trial stopped before task work because a
  structured model response was malformed and one-shot treated the parser error
  as terminal. Keep the fix in loop recovery, not long-dependency prompt
  guidance.
- The v1.1 malformed-JSON recovery speed proof passed `1/1`, so return to
  proof_5 before another repair or broad measurement.
- The v1.1 resource-normalized proof miss is not another runtime-link or
  runtime-install prompt rule. The blocker was already visible as
  `runtime_install_before_runtime_library_build`; the failure was that a
  low-wall recovery turn used a ~193k char full prompt and timed out repeatedly.
  Keep the v1.2 repair in model-context budgeting.
- The v1.2 timeout-ceiling compact-recovery speed proof passed `1/1`: `mew
  work` finished cleanly after 9 steps, installed default runtime support, ran
  a default-path smoke, and the external verifier passed. Escalate to
  resource-normalized proof_5 before another repair or broad measurement.
- The v1.2 resource-normalized proof miss is not another compact-recovery or
  runtime-link regression. Two valid trials passed; the failed trial found the
  right `-use-external-Flocq` branch but only after serially spending most of
  the wall budget on weaker compatibility probes. This should be repaired as a
  long-dependency profile/contract budget issue, not by appending another
  task-local prompt sentence.
- The source-acquisition profile speed proof passed `1/1`, but its proof_5
  miss repeated the known runtime-link failure after building `ccomp`; that was
  repaired by `default_runtime_link_path_failed` and validated by another
  speed proof.
- The default-runtime-link recovery proof miss did not repeat runtime-link
  failure. It fell back to a VCS-generated source archive, then edited bundled
  Flocq proof-library files under unsupported Coq while the final compiler
  artifact was missing. The transferable issue is local vendored dependency
  patch surgery after source-provided external/prebuilt branch evidence exists.
- v1.4 keeps the repair in the existing implementation profile. It should not
  fire from package-manager evidence alone, configure override attempts alone,
  read-only inspection, or normal project source patches.
- The v1.4 vendored patch surgery speed proof passed `1/1`: `mew work` built
  `/tmp/CompCert/ccomp`, verified source/config/runtime evidence, ran the
  default compile/link/run smoke, and the external verifier passed. Escalate to
  resource-normalized proof_5 before another repair or broad measurement.
- The acceptance-evidence-structure speed rerun did not fail because of the
  acceptance substrate. It failed before final artifact creation. The
  differentiator is that a filtered configure-help probe omitted
  external/prebuilt branch terms, so mew never surfaced the cheap
  source-provided compatibility branch before switching to a heavy
  version-pinned source-toolchain build.
- The v1.6 repair covers both same-command help filters and split
  `configure --help > file` followed by a narrow filter of that file. Its
  speed rerun moved the failure later, proving the repair direction was useful.
- The latest miss is not another external-branch discovery issue. The run built
  `ccomp` and failed default runtime link. The narrower blocker is an invalid
  parent Makefile target path for a runtime library that is actually declared
  inside the runtime subdirectory Makefile.
- The 2026-05-02 temp-fetch source-authority same-shape rerun is not another
  source-authority or target-selection repair. Source authority, configure, and
  dependency generation were satisfied; the reached failure was a timeout inside
  explicit `make -j"$(nproc)" ccomp`. Treat unreached later `make install` text
  as stale for current-failure selection when the same command evidence timed
  out first, and keep low-wall compact recovery small enough to render the
  recovery decision instead of the full implementation prompt.
- The 2026-05-02 build-timeout recovery rerun confirms that the prior masking
  and oversized-recovery blocker moved: the command reached the final `ccomp`
  build and was killed by wall time. Do not add another narrow
  toolchain-strategy or closeout reducer rule from this evidence. The durable
  product work is now generic long-build continuation/budget support before
  proof_5.
- The current blocker is above source/toolchain policy. Repair it as generic
  command continuation and wall-budget handling, not as another prompt/profile
  clause and not as a compile-compcert solver.
- The config/source-script external-hook same-shape rerun moved the blocker
  past source/config/dependency generation into default runtime linking.
  `/tmp/CompCert/ccomp` existed at verifier time, but the functional smoke
  failed with `cannot find -lcompcert`. The next repair is not another source
  or dependency strategy clause. It is a low-wall compact-recovery routing
  repair: when `runtime_link_failed` is already the selected long-build
  recovery class, prompt context should focus on the runtime-link recovery
  contract instead of reloading broad source/dependency sections and large
  unrelated resume payloads.
- The runtime-link compact-recovery speed rerun externally passed `1/1`, but
  internal mew closeout remained blocked on `source_authority_unverified`.
  The runtime repair direction was useful; the next blocker is reducer
  correlation, not another runtime command recipe. The source archive was
  acquired at an absolute path and later read back by basename after `cd` into
  the archive parent directory. The reviewed repair accepts that shape only
  when both hash and archive-list readbacks execute from the authoritative
  archive parent directory, rejects basename spoofing through cwd mutation
  (`pushd`, `popd`, wrapped/control-flow/variable `cd`, parent escape paths,
  and absolute mismatches), and treats validated `tar -x ... -C <absolute
  source dir> --strip-components=1` as source-root placement for
  archive-acquisition completion.
- The source-authority path-correlation speed rerun moved that blocker:
  `source_authority=satisfied` and `/tmp/CompCert/ccomp` existed, but the
  verifier failed default runtime linking. The current differentiator is that
  the continuation substrate still was not production-visible:
  `long_command_runs=[]`, `latest_long_command_run_id=null`, and a compound
  `configure -> make depend -> make ccomp -> smoke` command was classified as
  `dependency_generation` without managed-command budget dispatch. The next
  repair was generic managed long-command dispatch and reserve preservation,
  not proof_5, broad measurement, or a CompCert runtime recipe.
- The managed-dispatch speed rerun moved the dispatch blocker:
  `latest_long_command_run_id=work_session:1:long_command:1` and
  `latest_long_command_status=running`. The remaining gap is now
  `nonterminal_managed_command_handoff`: oneshot accepted model `wait` as a
  successful external verifier handoff while terminal command evidence was
  still absent. The current repair is generic one-shot handoff semantics:
  convert `wait` to a managed poll when `poll_long_command` is the allowed next
  action, and return a typed nonzero incomplete stop rather than verifier
  handoff if the command remains nonterminal at max steps. Review this repair
  before exactly one same-shape speed_1.
- The nonterminal-handoff speed rerun moved that blocker: it no longer returned
  `wait` as success and instead failed nonzero after `30m37s`. The next gap is
  `compound_long_command_budget_not_attached`: a compound OPAM / configure /
  build / final-smoke command was capped as a normal shell command with only the
  generic 2s reserve and no `long_command_budget`. The current repair adds a
  budget-specific planned-stage promotion so such compound long-build
  continuations are eligible for the managed long-command runner without
  changing recorded attempt stage semantics.
- The non-timeout source retry speed rerun externally passed and `mew work`
  finished, but internal closeout stayed stale:
  `source_authority=unknown`, `default_smoke=unknown`, and a previous
  `dependency_generation_required` blocker remained active. codex-ultra
  classified this as reducer/closeout projection, not a solver gap. The local
  generic repair accepts safe `|| exit 1` failure guards for default-smoke
  commands, recognizes strict selected authoritative source archive acquisition
  after failed candidate probes, and resolves simple shell assignments in
  archive hash/list readbacks. codex-ultra requested hardening against
  selected-URL spoofing, selected-alias mutation including `VAR+=...`,
  `readonly`, `read`, and `printf -v`, literal-URL / other-variable /
  non-print marker spoofing, redirected marker output, multiple selected
  markers, dynamic marker output, stale direct fetch URL bindings after `read`
  / `builtin read` / `command printf -v`, unmodeled shell-state mutators such
  as `eval` / `source` / `.`, non-stdout `printf -v` marker commands, and
  split selected stdout vs non-authoritative marker stdout, loop-body alias
  / loop-variable reassignment before fetch, stale while-read candidate-file
  variable bindings, candidate-file overwrite/first-candidate ordering, plus
  authoritative-first for-loop/selected-alias ordering, mixed direct-fetch URL
  rejection, and premature blocker clearing; all follow-ups are implemented and
  locally validated. Next action is re-review, then exactly one same-shape
  speed_1.

## Preflight Before Next Repair

Before any next repair in this gap class:

1. Identify whether the failure repeats one of: final artifact missing,
   untargeted build, compatibility override ordering, runtime link/install
   default path, source identity, or transient backend recovery.
2. Cite the previous stage that tried to handle it.
3. Explain why the next fix is not a duplicate detector/prompt patch.
4. Choose the layer:
   `instrumentation/report -> detector/resume -> profile/contract ->
   tool/runtime -> prompt section registry`.
5. If the fix touches prompt wording, state whether it belongs in a profile or
   prompt section instead of inline THINK guidance.

## Current Open Risk

`prompt_profile_accretion_risk`: the long-dependency policy now has many
detector plus guidance clauses. v1 consolidation introduced prompt section
registry support for normal work THINK prompts, with named sections for
`ImplementationLaneBase`, `LongDependencyProfile`, `RuntimeLinkProof`,
`RecoveryBudget`, `CompactRecovery`, `DynamicFailureEvidence`, schema, and
context. Another narrow prompt guidance repair should update the relevant
section or structural profile, not append inline THINK text, unless the failure
is clearly new and low-risk.

## Non-Goals

- No Terminal-Bench-specific solver.
- No full Codex CLI or Claude Code clone.
- No compile-compcert-specific solver.
- No new authoritative lane for M6.24 coding tasks.
- No broad prompt rewrite without typed continuation state and controller
  approval.
