# M6.24 Hot-Path Hypothesis Ledger

Date: 2026-05-15 JST

Purpose: keep M6.24 hot-path work from drifting into prompt/gate/frontier
patches that cannot be evaluated. This ledger tracks behavior-change
hypotheses separately from the observability substrate.

This document is not the observability design. The observability contract lives
in `docs/DESIGN_2026-05-15_M6_24_HOT_PATH_OBSERVABILITY.md`. Use that design
and the resulting analyzer before making or judging any hot-path behavior
change.

## Operating Rule

Do not combine multiple behavior hypotheses in one experiment.

Each experiment must have:

- one hypothesis;
- one minimal behavior change;
- one expected step-shape signal;
- one comparison against saved Codex and, where useful, Claude Code reference
  traces;
- one decision: keep, revert, revise, or escalate to redesign.

Codex is the primary target trace for `make-mips-interpreter`. Claude Code is a
useful negative/control trace for exploration-heavy behavior that does not
reach mutation.

## Required Evidence Before Behavior Changes

Before changing live loop behavior, produce or update:

- normalized Codex vs mew step-diff report;
- first tool / first mutation / first verifier metrics;
- probe count before first mutation;
- repeated probe-family diagnostics;
- first-patch readiness timestamp and basis;
- time from first-patch readiness to first mutation;
- direct vs delegated/externalized exploration shape;
- long reasoning/design-pass stalls after readiness;
- provider-visible prompt/transcript shape snapshot;
- tool-result rendering comparison when the hypothesis touches output salience;
- artifact paths for all compared runs.

If those artifacts are missing, add observability first.

## Current Reference Inputs

- Codex reference:
  `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq`
- Claude Code reference:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__WuLGVMp`
- mew A/B diagnostic:
  `proof-artifacts/tool-surface-ab-diagnostic/make-mips-interpreter-step-check-10min-20260514T193304Z`
- Current divergence report:
  `docs/REVIEW_2026-05-15_CODEX_HOT_PATH_DIVERGENCE_BEYOND_TOOL_IF.md`
- Codex vs Claude Code exploration-to-patch report:
  `docs/REVIEW_2026-05-15_CODEX_VS_CLAUDE_EXPLORATION_TO_PATCH.md`

## H0 Measurement Result

Measured on 2026-05-15 from saved artifacts only, using:

```bash
uv run python scripts/analyze_hot_path_step_diff.py \
  --codex-reference-root proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq \
  --claude-code-reference-root proof-artifacts/terminal-bench/reference-trace/claude-code-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__WuLGVMp \
  --mew-artifact-root proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-20260514-092606/2026-05-14__09-26-07/make-mips-interpreter__prSv5Ny/agent/terminal-bench-harbor-smoke/unknown-task \
  --out-json tmp/m6_24_hot_path_observability.json \
  --out-md tmp/m6_24_hot_path_observability.md
```

Key result:

| Agent | Readiness step | First mutation | Readiness -> mutation | Duplicate-after-readiness families |
|---|---:|---:|---:|---:|
| Codex | 3 | 25 | 22 steps | 3 |
| Claude Code | 3 | none | none | 3 |
| mew | 2 | none | none | 6 |

Interpretation:

- mew does not primarily lack early evidence. It reaches first-patch readiness
  at step 2.
- mew fails to compress early probe facts into a runnable patch. It continues
  source listing, text search, file reads, disassembly, and even build attempts
  without producing a first mutation.
- Codex also probes substantially, but turns probe facts into an `apply_patch`
  at step 25 and immediately runs a verifier at step 26.
- Claude Code is the control anti-pattern here: useful facts exist, but the
  loop does not mutate and spends long design/re-exploration effort.

Decision: H0 is complete. The next behavior experiment is H10: improve
exploration-to-patch compression. Do not switch to broad prompt/tool/render
tuning before a minimal H10 change is designed and measured.

## Hypothesis Queue

| ID | Hypothesis | Minimal change | Expected signal | Status | Decision |
|---|---|---|---|---|---|
| H0 | Hot-path behavior cannot be judged until first-patch readiness and exploration compression are measured. | Observability only: compute first-patch readiness timestamp/basis, readiness-to-mutation latency, accepted implementation constraints, and duplicate exploration after readiness. | We can say whether mew lacks evidence, fails to compress evidence into constraints, or stalls after enough evidence exists. | measured | mew has early evidence but does not compress it into a patch; use H10 next |
| H1 | Provider-visible task shape is wrong: mew leads with sidecar/task JSON rather than a plain task. | Make the hot-path first visible content environment context plus plain user task; move sidecar/task facts out of the leading position. | Earlier target-path mutation; fewer prewrite probes; no native rebuild branch before `vm.js`. | observable measured | Current H10 artifact starts every provider request with a JSON envelope; due sorted keys, `compact_sidecar_digest` is the first top-level section |
| H2 | Base instructions differ too much from Codex. | Use Codex-like base coding instructions for `codex_hot_path`, with only minimal mew safety/finish suffix. | More direct `apply_patch`; fewer evidence/protocol-oriented probes. | pending observability | TBD |
| H3 | `previous_response_id` continuity is present but not equivalent enough. | Add continuity audit first; behavior change only if audit proves missing response items or broken prefix continuity. | Audit explains whether model sees prior tool/reasoning state as expected. | observability first | TBD |
| H4 | Tool-result rendering adds salience noise. | Render command outputs closer to Codex: `Exit code`, `Wall time`, `Output`; remove runtime/evidence/token-count prose from model-visible output. | Same probe facts, but faster transition to mutation and fewer repeated probe families. | pending observability | TBD |
| H5 | Output compaction hides synthesis-critical source/binary detail. | Add visible/omitted content metrics first; expand only the specific result families that lost critical facts. | Fewer rereads of same files; more coherent first patch. | observability first | TBD |
| H6 | `apply_patch` affordance is still weak despite visible tool parity. | Run a synthetic artifact-only apply_patch affordance check before changing tool descriptions again. | Model chooses `apply_patch` for a trivial source mutation without extra steering. | measured pass | Not proximate cause; do not tune apply_patch wording before testing prompt/transcript shape |
| H7 | Visible sidecar scaffolding competes with task facts. | Hide or compress `compact_sidecar_digest` in provider-visible hot path while keeping sidecar artifacts internal. | Less process/proof language in first request; earlier task-directed mutation. | observable measured | Current H10 artifact exposes `compact_sidecar_digest` on all 50 provider requests; defer behavior change until H1 task-first shape is isolated |
| H8 | Environment affordances nudge mew into native rebuild. | Only after H1/H2/H4 checks, compare branch metrics for native rebuild attempts before target-path mutation. | `gcc`/build attempts disappear without hiding environment tools. | deferred | TBD |
| H9 | mew lacks a first-patch readiness threshold: it keeps exploring after enough evidence exists to write a runnable skeleton. | Add observability first: compute first-patch readiness candidates and readiness-to-mutation latency. Behavior change only after a measured miss. | Readiness-to-mutation latency shrinks; first mutation happens after enough evidence but before broad re-exploration/design stalls. | observability first | TBD |
| H10 | Exploration is not compressed into patch constraints. | Minimal behavior change: make accepted implementation constraints from probe facts visible as task facts, not as `next_action` steering. Keep the diagnostic sidecar as the source of truth and avoid adding a new frontier. | More direct transition from probes to one coherent patch; fewer repeated same-family probes; first mutation appears before repeated build/disassembly loops. | measured failed, reverted | compact task facts alone do not create probe-to-patch compression |
| H11 | Read-only exploration handoff can become an anti-pattern if the parent re-explores instead of patching. | For any future memory/explore provider, require a patch-readiness packet and measure duplicate post-handoff probes. Do not add another autonomous planner for this. | Duplicate exploration after a handoff decreases; mutation follows accepted facts faster. | deferred | TBD |
| H12 | Long private design passes after readiness are a hidden stall class. | Add metric: model turns or completion tokens after readiness with no tool call/mutation/verifier. Behavior change later may shorten visible instructions or force a small runnable skeleton. | Fewer high-token no-action turns after readiness; earlier verifier feedback. | observability first | TBD |

## Codex vs Claude Code Addendum

`docs/REVIEW_2026-05-15_CODEX_VS_CLAUDE_EXPLORATION_TO_PATCH.md`
adds an important distinction: Codex did not win by exploring less. It explored
on the implementation critical path and converted probes into patch
constraints. Claude Code gathered useful facts but used a blocking read-only
Explore handoff, re-read many facts in the parent, and spent long private
design passes without writing.

Use that report as a control when judging mew:

- Moving closer to Codex means probe facts become a runnable patch earlier.
- Moving closer to Claude Code means useful facts exist but the model keeps
  re-exploring or mentally completing the implementation before mutation.
- A future memory/explore provider must return a patch-readiness packet, not a
  general background report, or it risks reproducing the Claude Code failure
  shape.

## Experiment Record Template

Use one block per experiment.

```text
### EXP-YYYYMMDD-N: <short name>

Hypothesis:
Change:
Reference artifacts:
Mew artifact:
Expected signal:
Observed signal:
Decision: keep | revert | revise | redesign
Notes:
```

### EXP-20260515-1: H10 Probe Constraints As Task Facts

Hypothesis:
mew already reaches first-patch readiness, but native transcript probe facts are
not compacted into model-visible patch constraints.

Change:
Commit `5cc6af7` exposes compact `implementation_constraints` inside
provider-visible `task_facts` on later native requests. The payload is factual:
observed probe families, observed paths, source/artifact context, and latest
probe facts. It explicitly avoids `next_action`, `required_next`,
`first_write`, thresholds, a new frontier, or WorkFrame steering.

Reference artifacts:
Use the Codex, Claude Code, and mew H0 artifacts listed above.

Mew artifact:
`proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-ts-codex-hot-path-20260515-070200/2026-05-15__07-02-01/make-mips-interpreter__WD3uvwZ`

Expected signal:
First mutation appears earlier than H0, duplicate-after-readiness probe families
decrease, and the model moves toward Codex's probe-to-patch shape rather than
Claude Code's read/design/re-explore shape.

Observed signal:
Failed. The diagnostic reached reward 0, 50 tool calls, no detected source
mutation, and no external verifier pass. The analyzer reported:

- first mutation: Codex step 25, mew none;
- probe count before first mutation: Codex 24, mew 50;
- first-patch readiness: mew step 7 with no later mutation;
- repeated pre-mutation families: binary metadata, disassembly, symbol lookup,
  build, file read, and runtime verifier;
- provider request inspection confirmed `implementation_constraints` were
  present from turn 2 onward and reached `source_plus_artifact_probe` by turn 8.

Compared with H0, this did not improve the target signal. It increased probe
count and still failed to create a first mutation.

Decision:
Reverted by `f9b0059`. Do not keep this behavior in the live loop. The result
shows that compact factual `task_facts` are too weak or too unspecific to
change the model's probe-to-patch transition. The next experiment should not be
another small task-facts append unless it explains why the model still used
50 `exec_command` probes despite visible `implementation_constraints`.

Notes:
Focused validation before the diagnostic:

- `uv run pytest --no-testmon tests/test_native_tool_harness.py tests/test_hot_path_fastcheck.py tests/test_hot_path_step_diff.py -q`
  passed with 191 tests.
- `uv run ruff check src/mew/implement_lane/native_tool_harness.py tests/test_native_tool_harness.py`
  passed.
- `git diff --check` passed before commit.
- codex-ultra scoped review initially found provider alias and source-mutating
  exec gaps; both were fixed and re-review reported no blocking findings.
- bounded diagnostic command:
  `uv run python scripts/run_harbor_mew_diagnostic.py make-mips-interpreter --mode step-check-10min --tool-surface-profile-id codex_hot_path`.
- analysis output:
  `tmp/m6_24_h10_step_diff.json` and `tmp/m6_24_h10_step_diff.md`.

### EXP-20260515-2: H6 Synthetic Apply Patch Affordance

Hypothesis:
The model may still avoid `apply_patch` under `codex_hot_path` even when the
required source mutation is trivial and the target path/content are already
known.

Change:
Added an observability-only provider-native check:
`scripts/check_apply_patch_affordance.py`. It builds a one-turn
`codex_hot_path` tool-surface request with tools
`apply_patch`, `exec_command`, `write_stdin`, and `finish`, then records the
first tool call without executing it. No live loop behavior changes.

Reference artifacts:
No Harbor reference needed; this is a synthetic affordance check.

Mew artifact:
`proof-artifacts/m6_24_apply_patch_affordance/20260514T222246Z.json`

Expected signal:
The first provider-native tool call is `apply_patch`.

Observed signal:
Passed. The first tool call was a custom `apply_patch` call. Transcript item
count was 1. This proves the current `codex_hot_path` surface can make the model
choose `apply_patch` for a trivial known-path source mutation.

Decision:
Keep the check and do not change live behavior. H6 is not the proximate blocker
for `make-mips-interpreter`: the problem is not that the model cannot see or
choose `apply_patch` in principle. Continue with hypotheses about prompt /
transcript / task-shape salience and evidence-to-patch synthesis. Do not tune
`apply_patch` wording until a later measured artifact contradicts this result.

Notes:
Focused validation before the live check:

- `uv run pytest --no-testmon tests/test_apply_patch_affordance.py -q`
  passed with 3 tests.
- `uv run ruff check src/mew/implement_lane/apply_patch_affordance.py scripts/check_apply_patch_affordance.py tests/test_apply_patch_affordance.py`
  passed.
- descriptor-only smoke:
  `uv run python scripts/check_apply_patch_affordance.py --descriptor-only --out tmp/h6_apply_patch_affordance_descriptor.json`.
- live check:
  `uv run python scripts/check_apply_patch_affordance.py --timeout 90`.

### EXP-20260515-3: H1/H7 Provider Visible Salience Snapshot

Hypothesis:
After H6, the model can choose `apply_patch` in isolation, but the live
task-shaped provider input may still make resident sidecar scaffolding more
salient than the task itself.

Change:
Added an observability-only saved-artifact analyzer:
`scripts/analyze_provider_visible_salience.py`. It reads
`native-provider-requests.json` and `provider-request-inventory.json`, then
reports first-input shape, top-level section order, compact sidecar visibility,
section sizes, task-anchor counts, and resident scaffolding term counts. It
does not call a model and does not affect live behavior.

Reference artifacts:
No live reference run. This analyzer uses the existing H10 mew artifact and
the Codex/Claude Code step references remain the comparison context.

Mew artifact:
`proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-ts-codex-hot-path-20260515-070200/2026-05-15__07-02-01/make-mips-interpreter__WD3uvwZ/agent/terminal-bench-harbor-smoke/unknown-task`

Generated reports:

- `tmp/m6_24_h10_provider_visible_salience.json`
- `tmp/m6_24_h10_provider_visible_salience.md`

Expected signal:
The report can say whether H1/H7 are measurable without changing behavior:
plain-task-first versus JSON envelope, and whether compact sidecar scaffolding
is visible enough to compete with task facts.

Observed signal:

- 50/50 provider requests had `json_envelope` as the first user item shape.
- 50/50 provider requests had visible `compact_sidecar_digest`.
- First request section order was
  `compact_sidecar_digest, lane, task_contract, task_facts, workspace`.
- Max first input text was 9,120 chars.
- Max compact sidecar JSON was 5,981 chars.
- Scaffolding terms occurred 2,474 times, including resident refs such as
  `implement-v2-exec://`, `implement-v2-evidence://`, `tool-result:`,
  `provider_input_authority`, `sidecar_hashes`, and `runtime_id`.

Decision:
Keep the analyzer and use it to select the next behavior experiment. H1 and H7
are both measurable, but do not change both at once. The next behavior
experiment should isolate H1 first: make the provider-visible hot-path task
payload task-first while keeping compact sidecar visibility unchanged. If that
does not improve step shape, use this same analyzer to justify an H7
sidecar-visibility experiment.

Notes:
Focused validation:

- `uv run pytest --no-testmon tests/test_provider_visible_salience.py -q`
  passed with 2 tests.
- `uv run ruff check src/mew/implement_lane/provider_visible_salience.py scripts/analyze_provider_visible_salience.py tests/test_provider_visible_salience.py`
  passed.

## Stop Conditions

Stop polishing a hypothesis and escalate when:

- two consecutive measured variants do not improve the expected signal;
- the change requires another model-visible frontier/todo/evidence object;
- the change improves one task by adding task-specific behavior;
- the result moves closer to the Claude Code exploration-heavy anti-pattern;
- observability cannot explain why the step shape changed.

## Current Next Step

Follow this execution order. Do not reorder it after context compression:

1. Treat H0 as measured. Do not rerun live Harbor / Terminal-Bench just to
   re-answer H0.
2. Treat H10 as measured failed/reverted and H6 as measured pass.
3. Treat EXP-20260515-3 as the current provider-visible shape measurement:
   H1/H7 are measurable, with `compact_sidecar_digest` leading the first user
   payload and visible on every request.
4. Run the next single behavior experiment as H1 only: make live
   provider-visible task input task-first while keeping H7 sidecar visibility
   unchanged.
5. Run focused tests, fastcheck/replay where applicable, the provider-visible
   salience analyzer, then one bounded 10 minute step-shape diagnostic.
6. Keep, revise, or revert based on whether first mutation appears earlier and
   duplicate-after-readiness probe families decrease.
