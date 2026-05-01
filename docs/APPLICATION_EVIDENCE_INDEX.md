# Application Evidence Index

Updated: 2026-05-01.

This page is a short map for reviewers evaluating `mew` as an early
evidence-heavy OSS project, especially for OpenAI Codex Open Source Fund and
Codex for Open Source applications.

## Summary

`mew` is an MIT-licensed durable-state runtime for long-running AI coding
agents. It preserves task memory, typed/scoped recall, recovery state,
approval history, verifier evidence, runtime effects, and audit trails so an
interrupted agent can resume with less human rebriefing than a fresh CLI
restart.

Current application framing:

- Repository: https://github.com/mkXultra/mew
- Maintainer: Kaito Miyagi / https://github.com/mkXultra
- Commit count at packet preparation: `1,962`
- Status: M1-M5 closed; M6 implementation-lane and Terminal-Bench evidence
  active through M6.24
- Current benchmark baseline: mew `92/210 = 43.8%` vs frozen Codex target
  `156/210 = 74.3%`
- Side-project dogfood: `67` attempts, `51` clean or practical, `0`
  product-code rescue edits

## Roadmap Evidence

- [ROADMAP_STATUS.md](../ROADMAP_STATUS.md): compact current status and active
  milestone.
- [M3 close gate](M3_CLOSE_GATE_2026-04-20.md): persistent-advantage close
  evidence.
- [M4 close gate](M4_CLOSE_GATE_2026-04-20.md): true-recovery close evidence.
- [M5 close review](M5_CLOSE_REVIEW_2026-04-20.md): self-improvement close
  review after no-rescue loop work.
- [M6 close gate](M6_CLOSE_GATE_2026-04-21.md): resident body close evidence.
- [M6.16 close gate](M6_16_CLOSE_GATE_AUDIT_2026-04-27.md): implementation
  lane close evidence.
- [M6.19 Terminal-Bench compatibility](M6_19_TERMINAL_BENCH_COMPATIBILITY_AUDIT_2026-04-27.md):
  Harbor/Terminal-Bench compatibility audit.
- [M6.22 curated subset parity](M6_22_CLOSE_GATE_AUDIT_2026-04-28.md):
  curated multi-band subset close audit.
- [M6.23 failure-class coverage](M6_23_CLOSE_GATE_AUDIT_2026-04-28.md):
  selected failure-class repair proof.

## Active Terminal-Bench Evidence

M6.24 is the active public benchmark and debugging loop. It is not framed as
already solved parity. The useful evidence is the measured gap, selected
failure classes, bounded repair loop, and same-shape rerun discipline.

- [M6.24 gap baseline](M6_24_GAP_BASELINE_2026-04-29.md): mew `92/210` vs
  Codex `156/210` baseline.
- [M6.24 gap improvement loop](M6_24_GAP_IMPROVEMENT_LOOP.md): controller
  rules for measurement, repair, and rerun.
- [M6.24 decision ledger](M6_24_DECISION_LEDGER.md): selected gap decisions
  and controller state.
- [M6.14 structural repair ledger](M6_14_STRUCTURAL_REPAIR_LEDGER.md):
  accepted structural repair episodes that feed back into M6.24.
- `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`: frozen
  Codex target registry.
- `proof-artifacts/m6_24_gap_ledger.jsonl`: machine-readable gap ledger.

## Side-Project Dogfood

Side projects exercise the implementation lane without hiding failures behind
supervisor-authored product patches.

- [SIDE_PROJECT_ROADMAP.md](../SIDE_PROJECT_ROADMAP.md): side-project roadmap.
- [SIDE_PROJECT_ROADMAP_STATUS.md](../SIDE_PROJECT_ROADMAP_STATUS.md):
  current side-project status.
- `proof-artifacts/side_project_dogfood_ledger.jsonl`: canonical dogfood
  ledger.
- `experiments/mew-companion-log/`: fixture-driven companion-log project.
- `experiments/mew-ghost/`: historical path for the current `mew-wisp`
  terminal resident side project.

Current dogfood summary from `./mew side-dogfood report --json`:

- rows: `67`
- clean or practical: `51`
- failed: `16`
- product-code rescue edits: `0`
- main projects: `mew-companion-log`, `mew-ghost`, `mew-wisp`

## Security-Relevant Surfaces

See [Security and Privacy Notes](SECURITY_AND_PRIVACY.md). The main review
targets are:

- `.mew/` persisted state and memory
- work-session snapshots, runtime traces, effects, and approvals
- auth file handling and prompt/context construction
- write, shell, verification, launcher, and webhook gates
- side-effect recovery after interrupted or failed work

## Current Limitations

- `mew` is early and should not be represented as widely adopted.
- Terminal-Bench parity is not closed; M6.24 is actively measuring and reducing
  a substantial gap against Codex.
- M6.25 Codex-plus resident advantage is not started. The current benchmark
  loop must remain honest about where Codex is still stronger.
- Persisted memory and runtime traces are security-sensitive and require careful
  handling before wider use.
- Side-project dogfood records failures openly; recent blocked slices remain
  useful implementation-lane evidence rather than completed product progress.

## OpenAI Application Packet

The companion draft packet lives in `../mew_inspect/docs/`:

- `APPLICATION_DRAFTS.md`
- `CREDITS_PLAN.md`
- `README_PITCH.md`

Those files are application copy. This repository page is the public evidence
map that reviewers can follow after opening the repo.
