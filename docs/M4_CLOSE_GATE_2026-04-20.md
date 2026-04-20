# M4 Close Gate 2026-04-20

Status: close-gate dogfood passed.

This document closes Milestone 4, True Recovery. It does not claim that every
possible side effect can be retried automatically. It proves the M4 product
bar: after interrupted, crashed, or failed work, mew can restart from durable
state, classify the situation, choose a safe next move, or ask the user through
visible recovery surfaces without manual reconstruction.

## Behavior Proved

The close gate combines the M4 recovery slices that had previously been proved
separately:

- runtime-effect recovery decisions and follow-ups:
  `docs/M4_RUNTIME_EFFECT_RECOVERY_DECISION_2026-04-20.md`;
- hash-based work-session file write recovery:
  `docs/M4_FILE_WRITE_RECOVERY_2026-04-20.md`;
- failed shell-command review recovery:
  `docs/M4_COMMAND_REVIEW_RECOVERY_2026-04-20.md`;
- durable approval elicitation:
  `docs/M4_DURABLE_APPROVAL_ELICITATION_2026-04-20.md`.

The new `m4-close-gate` dogfood scenario exercises the M4 end state through a
single artifact:

- an unchanged runtime write intent is classified as
  `runtime_write_not_started` and the original event is requeued;
- an interrupted runtime-owned verifier is auto-retried and the interrupted
  tool call is marked superseded;
- an interrupted live approval prompt remains visible in `focus`, `brief`,
  `questions`, outbox, attention, and the work-session resume;
- a completed runtime write intent stays on review rather than being blindly
  reapplied;
- recovery evidence is read back through CLI surfaces after seeding the
  interrupted/crashed state.

## Validation

Focused test:

```bash
uv run pytest --testmon -q tests/test_dogfood.py -k m4_close_gate
uv run --with ruff ruff check src/mew/dogfood.py tests/test_dogfood.py
```

Direct dogfood proof:

```bash
./mew dogfood --scenario m4-close-gate --workspace proof-workspace/mew-proof-m4-close-gate-local-20260420 --json
```

Result:

- status: `pass`
- checks:
  - `m4_close_gate_runtime_write_intent_auto_requeued`
  - `m4_close_gate_verifier_auto_retried_and_superseded`
  - `m4_close_gate_durable_approval_visible_in_focus_and_brief`
  - `m4_close_gate_completed_external_write_stays_on_review`
  - `m4_close_gate_no_manual_reconstruction_required`

## Interpretation

M4 is done because `recovery_hint` and the surrounding recovery metadata are no
longer only notes. They feed real recovery paths: event requeue, safe verifier
retry, safe read/git retry, hash-based write recovery, durable approval
elicitation, and explicit user review for opaque or risky side effects.

Opaque shell/action retry remains a deliberate non-goal for M4. Shell side
effects stay on review until mew has a deterministic world-state validator for
that class.
