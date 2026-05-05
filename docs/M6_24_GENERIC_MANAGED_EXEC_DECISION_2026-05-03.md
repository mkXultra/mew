# M6.24 Generic Managed Exec Decision - 2026-05-03

## Decision

Keep the current command classifier narrow for M6.24.

The classifier should decide only whether a planned command should receive
managed long-command budget. It must not grow into a general shell semantics
engine.

The current accepted shape is:

- source acquisition/readback stays outside managed long-command budget unless
  a non-fetch segment actually invokes build/install/smoke work;
- compound source/configure-looking commands may receive managed budget when
  they contain real long build/install/final-proof work;
- approval/safety policy stays separate from budget routing;
- terminal `CommandEvidence` remains the only acceptance proof.

This is a routing policy for mew's current `work --oneshot` / external verifier
handoff architecture, not a permanent product ideal.

## Why Not All-Command Managed Exec Now

Codex CLI and Claude Code both have generic long-running command lifecycle
machinery: process identity, streaming or persisted output, timeout/yield,
background/poll, and terminal finalization.

They do not appear to use a mew-like build/fetch classifier to decide whether a
command is a long build. Their command classification is mostly for safety,
read-only permission, UI summary, sandbox/approval, and exit-code interpretation.

Mew still needs a narrow budget classifier because:

- `mew work --oneshot --defer-verify` must decide when to preserve wall budget
  before handing a workspace to an external verifier;
- sending every small fetch/readback/probe through long-command continuation
  would add noisy `poll`/`wait` state and pollute proof handoff;
- failing to route real long builds into managed continuation causes wall
  timeout before terminal evidence.

## Trigger To Reconsider

Switch from "narrow budget classifier" to "all shell commands use generic
managed exec lifecycle" when one or more of these signals appears.

Strong triggers:

1. Repeated false negatives:
   - real long commands are killed by wall timeout because no managed budget was
     attached;
   - threshold: same `budget_not_attached` shape repeats on a different task or
     a different build ecosystem, or repeats twice after this repair.

2. Repeated false positives:
   - fetch/readback/probe commands receive managed budget and create noisy
     nonterminal/poll state;
   - threshold: two distinct false-positive repairs in the budget classifier.

3. Classifier accretion:
   - adding ecosystems such as `nix build`, `bazel build`, `cmake --build`,
     `meson compile`, `gradle build`, `mvn package`, or long test runners
     becomes the active repair pattern;
   - threshold: three or more ecosystem-specific additions in two weeks, or
     five classifier repairs in the same gap family.

4. Lifecycle gaps dominate the benchmark ledger:
   - recent failures are mostly `budget_not_attached`, `handoff_race`,
     `poll_missing`, `output_lost`, or `nonterminal_proof`;
   - threshold: three or more of the latest ten selected M6.24 gap records are
     lifecycle-routing gaps.

5. Recovery state inverts ownership:
   - `LongBuildState` starts encoding shell-command budget details instead of
     task/recovery state;
   - when this happens, split responsibilities: state/recovery decides what
     needs to happen, generic managed exec owns command lifecycle.

## Non-Triggers

Do not switch just because:

- `compile-compcert` alone needs another bounded budget-routing guard;
- reference CLIs have generic exec lifecycle;
- a single benchmark run times out without showing a routing/lifecycle cause;
- the next failure is dependency strategy, source authority, runtime linking,
  or closeout reducer logic rather than command lifecycle.

## If Triggered

Open a deliberate design/implementation slice before more local classifier
patches.

Required design output:

- define how every shell command receives a process identity, output owner,
  timeout/yield policy, and terminal finalization;
- keep short command UX efficient, with no unnecessary model-visible poll noise;
- preserve approval/safety classification separately from lifecycle routing;
- preserve acceptance proof boundaries: running/yielded commands never prove
  task success;
- define how `work --oneshot --defer-verify` waits, polls, or blocks before
  external verifier handoff;
- include transfer tests for short readback, pure fetch, long build, long test,
  timeout, killed/interrupted, and terminal proof cases.

Until that trigger is met, continue the current M6.24 chain:

```text
M6.24 -> long_dependency/toolchain gap -> compound long-command budget repair reviewed -> same-shape speed_1
```
