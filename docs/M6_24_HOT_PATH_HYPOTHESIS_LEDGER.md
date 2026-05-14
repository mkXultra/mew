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
| H1 | Provider-visible task shape is wrong: mew leads with sidecar/task JSON rather than a plain task. | Make the hot-path first visible content environment context plus plain user task; move sidecar/task facts out of the leading position. | Earlier target-path mutation; fewer prewrite probes; no native rebuild branch before `vm.js`. | blocked by H0 | TBD |
| H2 | Base instructions differ too much from Codex. | Use Codex-like base coding instructions for `codex_hot_path`, with only minimal mew safety/finish suffix. | More direct `apply_patch`; fewer evidence/protocol-oriented probes. | pending observability | TBD |
| H3 | `previous_response_id` continuity is present but not equivalent enough. | Add continuity audit first; behavior change only if audit proves missing response items or broken prefix continuity. | Audit explains whether model sees prior tool/reasoning state as expected. | observability first | TBD |
| H4 | Tool-result rendering adds salience noise. | Render command outputs closer to Codex: `Exit code`, `Wall time`, `Output`; remove runtime/evidence/token-count prose from model-visible output. | Same probe facts, but faster transition to mutation and fewer repeated probe families. | pending observability | TBD |
| H5 | Output compaction hides synthesis-critical source/binary detail. | Add visible/omitted content metrics first; expand only the specific result families that lost critical facts. | Fewer rereads of same files; more coherent first patch. | observability first | TBD |
| H6 | `apply_patch` affordance is still weak despite visible tool parity. | Run a synthetic artifact-only apply_patch affordance check before changing tool descriptions again. | Model chooses `apply_patch` for a trivial source mutation without extra steering. | observability first | TBD |
| H7 | Visible sidecar scaffolding competes with task facts. | Hide or compress `compact_sidecar_digest` in provider-visible hot path while keeping sidecar artifacts internal. | Less process/proof language in first request; earlier task-directed mutation. | pending observability | TBD |
| H8 | Environment affordances nudge mew into native rebuild. | Only after H1/H2/H4 checks, compare branch metrics for native rebuild attempts before target-path mutation. | `gcc`/build attempts disappear without hiding environment tools. | deferred | TBD |
| H9 | mew lacks a first-patch readiness threshold: it keeps exploring after enough evidence exists to write a runnable skeleton. | Add observability first: compute first-patch readiness candidates and readiness-to-mutation latency. Behavior change only after a measured miss. | Readiness-to-mutation latency shrinks; first mutation happens after enough evidence but before broad re-exploration/design stalls. | observability first | TBD |
| H10 | Exploration is not compressed into patch constraints. | Minimal behavior change: make accepted implementation constraints from probe facts visible as task facts, not as `next_action` steering. Keep the diagnostic sidecar as the source of truth and avoid adding a new frontier. | More direct transition from probes to one coherent patch; fewer repeated same-family probes; first mutation appears before repeated build/disassembly loops. | selected next | design and run one bounded experiment |
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
2. Design the first H10 behavior experiment: expose compact implementation
   constraints derived from probe facts as task facts, while keeping diagnostics
   sidecar-only and avoiding `next_action`, `required_next`, probe thresholds,
   or new frontier objects.
3. Add the smallest implementation that can change the step shape.
4. Run focused tests, fastcheck/replay where applicable, then the artifact-only
   analyzer. Only after that, run one bounded 10 minute step-shape diagnostic.
5. Keep, revise, or revert based on whether first mutation appears earlier and
   duplicate-after-readiness probe families decrease.
