# Issue Repair Policy

Purpose: keep issue-driven repairs useful beyond the triggering bug and keep
long sessions from drifting into narrow product-specific patches.

This policy applies to GitHub issues, side-project problem issues, and local
ledger rows that interrupt active milestone work.

## Repair Controller

Before code changes, write this chain in notes, a commit message, or the
decision ledger:

```text
issue -> generic failure class -> reference/policy basis -> bounded repair -> proof -> return path
```

If the chain cannot be written, do not implement yet. Classify or gather
evidence first.

## Classification

Classify the issue as one of:

- `product_specific`: the side project or current product code is simply wrong.
- `generic_loop_gap`: mew's implementation lane can repeat the failure.
- `verifier_contract_gap`: verifier green does not prove the requested behavior.
- `task_spec_gap`: the task lacks acceptance, scope, or proof criteria.
- `measurement_gap`: the evidence cannot distinguish product failure from loop
  failure.
- `ambiguous`: more data is needed.

Only `generic_loop_gap`, `verifier_contract_gap`, `task_spec_gap`, and
`measurement_gap` should change core mew behavior. `product_specific` belongs
in the product or side-project branch unless the user explicitly asks for a
core mew change.

## Generalization Rule

Do not implement a fix by naming the triggering side project, task id, file
name, UI label, benchmark, or product-specific noun unless the issue itself is
classified as `product_specific`.

For core mew repairs, translate the issue into a reusable contract:

- failing shape, not failing app
- acceptance semantics, not literal label text
- verifier proof class, not one test name
- task contract, not benchmark-specific solver
- lane/profile decision, not ad hoc special case

If no reusable contract exists, record that and route the issue away from core
mew.

## Reference Basis

For structural or verifier-contract repairs, inspect at least one relevant
reference before editing:

- `docs/ADOPT_FROM_REFERENCES.md`
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`
- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`
- `references/fresh-cli/codex`
- `references/fresh-cli/claude-code`

Use the references as patterns, not as copy targets. The preferred import shape
is a small mew-native invariant, blocker, typed contract, replay fixture, or
testable proof rule.

## Proof Rule

A repair is not complete until it has:

- a positive test proving the intended behavior
- a negative test proving the previous superficial or wrong behavior is blocked
- tool-grounded evidence when the repair concerns verification or finish
  eligibility
- a false-positive guard for the closest ordinary task that should still pass
- focused validation and `git diff --check`

For verifier-contract gaps, free-form acceptance prose is not enough. The proof
must be grounded in cited tool output, source inspection, diff, or replayable
fixture data.

## Drift Control

Issue repair must not silently replace the active milestone controller.

During long sessions:

1. Fix open side-project problem issues only when they are core blockers,
   implementation-lane hardening inputs, or explicitly requested by the user.
2. After each issue fix, close the issue or record why it remains open.
3. Re-read the active milestone controller before selecting the next task.
4. If the issue repair reveals a structural blocker, pause the product
   milestone and route through the structural repair ledger.
5. If the repair only closes the issue, return to the prior active milestone.

For M6.24 specifically, issue repair does not permit broad measurement to
resume. After issue close, return to `improvement_phase` and select the next
gap class unless `docs/M6_24_DECISION_LEDGER.md` explicitly changes mode.

## Stop Conditions

Stop and reclassify when:

- the patch mentions the triggering app/product more than the generic failure
  class
- the only evidence is the model's own summary
- the fix expands prompts without a runtime blocker, invariant, or test
- the nearest false-positive example fails
- a reference suggests a larger architecture change than the issue needs
- the issue would take the session away from the active milestone without a
  written return path
