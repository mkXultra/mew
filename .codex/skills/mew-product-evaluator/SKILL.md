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
- The remaining frontier is a durable runtime effect journal: planned -> applied -> verified -> recovered/resolved, visible in doctor/brief and resumable after interruption.
- The next maintainability frontier is extracting action application from the large agent/command modules so mew can reason about and improve its own execution layer.

If confidence is low, say what is uncertain. Use `acm run` with another model only when the user explicitly asks for that model, then compare its answer with your own before responding.
