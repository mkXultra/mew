---
name: mew-product-evaluator
description: Evaluate mew as a passive AI product and as a shell/body that an AI model might want to inhabit. Use when asked whether mew is good enough, whether it feels usable as the next execution form, or what should improve next.
---

# Mew Product Evaluator

When evaluating mew, do not only review code quality. Ask the product question:

> Would I want to be inside mew?

Answer candidly.

Use these checks:

- Does mew help a resident AI remember itself after time passes or context is compressed?
- Does it let the AI notice tasks, ask questions, and act without constant user prompting?
- Does it have enough feedback to read, decide, act, verify, and recover?
- Is the human interface calm enough for daily use?
- Is it safe enough to run passively without surprising the user?

Current guiding judgment:

- A task/coding passive AI is the first target.
- Broader general passive AI can come later.
- "Works" is not enough; "I would want to be inside it" is the higher bar.
- Reflex observation exists: with bounded opt-in rounds, mew can read/inspect/search, rethink with the observation, and then act.
- Gated write/verify/rollback exists, and write runs link to verification runs; this is now a real feedback loop.
- Runtime effect journaling has started: cycles now persist planning/commit/apply/verify status and surface it in doctor/brief/dogfood.
- Repair can explicitly mark unfinished runtime effects as interrupted after process death and attach a recovery hint; runtime startup now performs the safe subset automatically for incomplete runtime effects.
- True interruption recovery has started: passive native work can auto-retry the selected interrupted verifier or safe read/git tool when explicit gates match, while side-effecting write/shell recovery stays on the visible review path.
- The remaining recovery frontier is side-effecting command/write recovery and broader runtime-effect recovery: use the journal to automatically choose safe next actions without hiding risk from the user.
- The next maintainability frontier is extracting action application from the large agent/command modules so mew can reason about and improve its own execution layer.
- Native work sessions are now the main evidence for "inside mew": THINK/ACT is journaled before model calls, live work has stop boundaries, resume bundles include world state/recovery plans, older context is digested, and oversized model context is compacted.
- Persistent advantage should be judged as continuity, not only multi-day use: after context compression, runtime stop, terminal close, pending approval, failed verifier, external review, or user pivot, mew should preserve memory, risks, runnable next action, approvals, recovery path, verifier confidence, context budget, prior decisions, and pending user-pivot cues.
- Continuity should be actionable, not merely graded: if the bundle is weak, mew should tell the resident the next repair action before it acts.
- Passive native work advance is now part of the bar: with explicit gates, mew can start a runtime-owned coding work session and later passive ticks can advance it by one bounded native step while preserving auditability.
- The current product frontier is a polished REPL-style coding cockpit: calm streaming, clear live output, and daily-use ergonomics that make mew feel preferable to starting a fresh coding CLI.
- External observer operation is now a serious product surface: task lifecycle commands have JSON output, follow snapshots expose pending approvals and supported reply actions, `--follow-status` reports producer health, and stale/dead/absent snapshots return `suggested_recovery` commands.
- The remaining observer frontier is not basic legibility; it is making the recommended recovery path feel obvious and trustworthy during real interrupted work, especially side-effecting command/write recovery.
- Reference-adoption decision from 2026-04-19: when optimizing for "Would I want to be inside mew?", prefer 5.12 Memory Scope × Type as the next persistence slice before 5.11 AgentMemorySnapshot or 5.1 Streaming Tool Executor. Typed/scoped memory makes past resident knowledge findable; snapshots should wait until the state/resume shape is calmer; streaming is the right M2 choice only when cockpit latency is the active pain.
- 5.12 has a file-backed typed/scoped memory MVP, native work resume injects an `active_memory` bundle into the resident THINK prompt, and `mew memory --active --task-id ...` exposes that injected bundle for humans/observers. A real Codex Web API dogfood turn chose `read_file README.md` because active project memory steered that route. The next product question is recall quality and daily usefulness, not whether more storage surfaces exist.

If confidence is low, say what is uncertain. Use `acm run` with another model only when the user explicitly asks for that model, then compare its answer with your own before responding.
