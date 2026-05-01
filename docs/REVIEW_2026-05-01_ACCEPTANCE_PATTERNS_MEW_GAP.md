# Review: Acceptance / Finish Gate / Evidence Handling Gap

Date: 2026-05-01

Scope:

- `src/mew/acceptance.py`
- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `src/mew/commands.py` finish wrapper
- `tests/test_acceptance.py`
- `tests/test_work_session.py`
- `ROADMAP.md`
- `ROADMAP_STATUS.md`
- M6.24 controller, decision ledger, gap ledger, long-dependency dossier, and
  current `compile-compcert` proof docs

## Executive Recommendation

Do not implement another acceptance / finish gate / evidence-handling change
before the pending `compile-compcert` proof_5.

The current active chain is:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> profile_contract ->
prompt_section_registry_v1 recorded ->
long_dependency_compatibility_branch_budget_contract proof_5 -> compile-compcert
```

The v1.3 compatibility-branch budget repair already passed the same-shape
speed gate at `1/1`. The controller and dossier both say the next score action
is resource-normalized sequential proof_5, using `-k 5 -n 1` with refreshable
`~/.codex/auth.json`. Broad measurement remains paused.

The smallest high-leverage structural change, if another repair is needed after
that proof, is not another prompt sentence. It is to unify long-dependency final
artifact proof authority between `acceptance.py` and `work_session.py`, behind
a shared evidence/proof resolver. That would preserve the no-Terminal-Bench-
specific-solver rule because the contract is generic: a final executable or
artifact must be proven by a completed, non-timed-out, zero-exit, non-masked,
non-mutating tool call whose command/output surface actually proves the
artifact.

## Current Architecture

### Acceptance Checks

`acceptance.py` owns the finish-time `task_done=true` blocker layer. It derives
lightweight acceptance constraints from the task text with
`extract_acceptance_constraints()` and normalizes model-authored
`acceptance_checks` through `coerce_acceptance_checks()`.

The check schema is intentionally small:

```text
constraint: string
status: string
evidence: string
```

Evidence grounding is free text. Tool provenance is recovered by parsing
phrases such as `tool #N` or `tool call N`, then looking up completed tool
calls in the session. The finish gate does not currently receive structured
evidence references from the model.

### Work Loop Prompting

`work_loop.py` makes acceptance constraints part of the work model context and
prompt contract. Normal work THINK prompts now render through prompt sections,
including `ImplementationLaneBase`, `LongDependencyProfile`,
`RuntimeLinkProof`, `RecoveryBudget`, `CompactRecovery`,
`DynamicFailureEvidence`, schema, and context JSON.

The prompt tells the model to keep `working_memory.acceptance_constraints` and
`working_memory.acceptance_checks` current, and to finish with verified checks
that cite direct tool output, diffs, or file inspection. Long-dependency
toolchain tasks receive specific guidance about final artifacts, compatibility
branches, runtime link proof, default runtime path proof, wall-budget reserve,
and compact recovery under timeout ceilings.

This is helpful steering, but it is not the authority boundary. The authority
boundary is still the finish wrapper plus `acceptance_finish_blocker()`.

### Finish Execution

`commands.py` routes finish actions through `apply_work_control_action()`.
Before closing a session it checks:

- pending approvals
- source-edit verification confidence
- same-surface audit
- acceptance finish blockers
- side-project dogfood report blockers

For model-inference output tasks, the finish wrapper deliberately applies the
acceptance gate even when the action has `task_done=false`, because handing off
an ungrounded model-equivalence claim is still unsafe.

If blockers exist, the session stays active and the task is not marked done.
Some blocker strings are recognized by `work_finish_blocker_allows_continue()`
as repairable continuation signals.

### Specialized Finish Blockers

`acceptance_finish_blocker()` runs a sequence of specialized gates before the
generic constraint-count fallback:

- all-valid answer completeness
- external ground-truth tool command/flag evidence
- exact command examples from task text
- implementation-contract source grounding
- runtime final verifier artifact state
- runtime visual artifact quality
- runtime artifact freshness and cleanup
- long-dependency final artifact proof
- stateful output semantic contrast
- query-only hidden-model validation
- model inference output/oracle provenance
- numeric artifact quality
- generic extracted acceptance constraints plus edit-scope grounding

This covers many M6.24 failure classes and is well tested. The design is
incremental: each newly observed false finish has added a narrow detector and
blocker.

### Work Session Evidence State

`work_session.py` builds the resume state that the model uses after tool calls,
timeouts, or continuation. For M6.24 long-dependency work, it surfaces
`long_dependency_build_state`, including:

- expected final artifacts
- missing or unproven artifacts
- latest build status
- incomplete reason
- strategy blockers
- suggested next action

The long-dependency proof logic in `work_session.py` is stricter than the
acceptance proof logic. It requires completed command evidence, no timeout,
`exit_code == 0`, acceptable command surface, no negative output markers, and
strict artifact proof. It also rejects masked probes and artifact-mutating
command surfaces.

This strictness directly reflects the prior v0.9 repair, where a timed-out
build was incorrectly allowed to mark `/tmp/CompCert/ccomp` as proven even
though the external verifier found it missing.

### Tests

The tests pin the major safety surfaces:

- `tests/test_acceptance.py` covers acceptance constraints, stateful output,
  stale runtime artifacts, final verifier artifacts, runtime visual quality,
  implementation source grounding, edit-scope proof, numeric cross-checks,
  long-dependency final artifacts, model inference, hidden-model extraction,
  exact command examples, and external ground-truth commands.
- `tests/test_work_session.py` covers finish blocking, repairable finish
  continuation, long-dependency resume state, artifact proof calibration,
  runtime/default-path blockers, compatibility-branch budget blockers, compact
  recovery prompt mode, and many loop-level regressions.

The test suite is broad, but it currently tests acceptance and resume evidence
mostly as parallel surfaces, not as one shared proof authority.

## Observed Gaps

### 1. Long-Dependency Final Artifact Proof Is Split

This is the highest-leverage structural gap.

`acceptance.py` proves a long-dependency final artifact by checking whether the
model-authored evidence text has proof markers for the artifact, then checking
cited tool output text for similar markers. It does not reuse the stricter
`work_session.py` artifact proof surface.

`work_session.py` now has a stronger contract:

- only command tools count
- status must be completed
- timed-out calls do not prove final artifacts
- `exit_code` must be zero
- command surface must not be masked or ambiguous
- artifact-mutating surfaces cannot prove the artifact
- command-only proof is allowed only for strict executable probes such as
  `test -x artifact` or invoking the artifact with version/help-style smoke

Because these are separate implementations, finish acceptance and resume state
can disagree. That is especially relevant to `compile-compcert`, where the
current task family has already exposed artifact-proof calibration bugs.

Risk shape:

- resume can say an artifact is missing or unproven
- acceptance can still accept a free-text check that cites a tool output with
  artifact/proof markers
- the model can finish from weaker evidence than the resume detector would
  consider sufficient

This does not prove the pending proof will fail. The latest v1.3 speed run
passed externally. It does mean the current architecture has two authorities
for the same final-artifact question.

### 2. Evidence References Are Free-Text Rather Than Structured

All finish blockers parse tool ids out of model-authored text. That keeps the
model schema simple, but it spreads evidence resolution across many helpers.

Current free-text evidence can answer "did this string cite tool #N?" It does
not give each blocker a typed object like:

```text
tool_call_id
tool
status
exit_code
timed_out
command
cwd
result_text
full_call_text
```

As a result, each blocker decides for itself which fields matter. The same
session evidence can be interpreted differently by different gates.

### 3. Generic Constraint Coverage Is Count-Based

After specialized gates, the fallback accepts finish when the number of
verified checks is at least the number of extracted constraints. It does not
semantically map each extracted constraint to a unique check.

This is mitigated by the specialized blockers for high-risk classes, but the
generic fallback can still accept duplicated or loosely related verified checks
when a task has several simple textual constraints.

### 4. Finish Blocker Identity Is Mostly Free-Text

Finish blockers are returned as strings and concatenated into one
`finish blocked:` note. Some continuation behavior is keyed by substring
matching in `work_finish_blocker_allows_continue()`.

This makes the finish gate legible to a human, but weak as a machine contract.
There is no stable internal `code`, `layer`, `evidence_refs`, or
`suggested_next` for most acceptance blockers. `work_session.py` strategy
blockers are closer to this shape than acceptance blockers are.

### 5. First-Blocker Return Can Hide the Next Repair

`acceptance_finish_blocker()` returns the first specialized blocker. That is
useful for concise feedback, but it can hide coexisting gaps.

For long dependency/toolchain work, a finish attempt may simultaneously need
artifact proof, runtime link/default path proof, and acceptance-check cleanup.
The current gate reports whichever blocker appears first in the ordering.

### 6. Prompt Section Registry Does Not Yet Unify Evidence Authority

The prompt section registry is a good response to prompt accretion risk. It
names and hashes long-dependency prompt sections, which should prevent future
inline guidance sprawl.

It does not solve the evidence authority split. A prompt section can tell the
model what proof to cite, but only shared structured proof logic can make finish
and resume agree on what proof counts.

### 7. Minor Runtime-Artifact Message Drift

`_runtime_artifact_freshness_blocker()` returns a stateful-output semantic
contrast message when runtime artifacts exist but no verified checks exist.
That looks like copy/paste drift. It is not the active `compile-compcert`
blocker, but it is another sign that the blocker layer has grown by accretion.

## Risk Of Changing Before The Pending Measurement

Risk is high enough to recommend no-go.

The active controller state is already proof_5-pending. The selected v1.3
compatibility-branch budget repair passed its speed proof, and the next
decision point should be the resource-normalized close proof. A code change now
would mean the proof is no longer measuring the same implementation that passed
the speed gate.

Specific risks:

- A stricter acceptance gate could delay or block finish after a successful
  external-verifier path, increasing wall-clock pressure on the exact task
  shape currently being measured.
- A shared proof resolver could change `compile-compcert` stop/continue
  behavior even if the external verifier would have passed.
- A finish-blocker registry or structured evidence change would be a process
  or policy-shape change and would need explicit M6.24 trial-boundary evidence.
- The current speed doc already records a residual internal calibration signal:
  top-level `resume.long_dependency_build_state` was absent in the successful
  finish path. That is worth tracking, but the score gate passed and the
  controller says to escalate.

Documenting this review is safe. Changing the code before proof_5 would reduce
comparability and make the result harder to interpret.

## Go / No-Go

### Before `compile-compcert` proof_5

No-go for implementation.

Run the pending proof_5 first:

```text
compile-compcert, sequential -k 5 -n 1, refreshable ~/.codex/auth.json
```

Do not add Terminal-Bench-specific solvers. Do not add another task-local prompt
clause. Do not change acceptance or finish behavior before this proof unless a
new explicit operator decision records a fresh trial boundary and rollback
condition.

### If proof_5 reaches the frozen target

Keep this review as structural debt. Defer the shared evidence/proof resolver
until after the selected M6.24 repair is closed and the controller chooses the
next gap class or resumes broader measurement.

### If proof_5 misses

Read the long-dependency dossier before any repair, then classify the miss.

Go only if the miss involves one of these shapes:

- final artifact marked proven internally while the verifier finds it missing
- finish accepted weaker artifact evidence than resume state would accept
- task_done or session close happened from a timed-out, nonzero, masked, or
  mutating artifact proof
- repeated evidence/proof disagreement between acceptance checks, work report,
  and resume state

If the miss is instead a new ordering, wall-budget, backend recovery, or
toolchain strategy failure, do not use this patch plan as a shortcut. Keep the
repair in the selected generic gap class and layer.

## Concrete Patch Plan If Go

### Controller Record

Record the chain before implementation:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract ->
evidence_authority_unification -> no_lane_change/profile_contract ->
compile-compcert speed_1 same-shape rerun
```

In the decision ledger or gap ledger, record:

- current pain
- expected benefit
- one-run trial boundary
- rollback condition
- no-Terminal-Bench-specific-solver statement

### Patch 1: Add A Shared Evidence Reference Resolver

Add an internal resolver that takes `acceptance_checks` plus `session` and
returns typed evidence references for each cited tool id. Do not change the
model-facing acceptance schema yet.

The resolver should expose at least:

```text
tool_call_id
tool
status
exit_code
timed_out
command
cwd
result_text
call_text
```

Keep the public `acceptance_checks` format unchanged so this is a substrate
repair, not a prompt/schema migration.

### Patch 2: Share Long-Dependency Artifact Proof Logic

Move the strict long-dependency artifact proof helpers to a shared module, for
example `src/mew/evidence.py` or `src/mew/proof_evidence.py`, then use them
from both `acceptance.py` and `work_session.py`.

The shared final-artifact proof must reject:

- timed-out calls
- nonzero exits
- missing command/result text
- masked probes such as `|| true`, pipes, shell conditionals, redirects to
  `/dev/null`, or ambiguous shell control flow
- commands that mutate or delete the artifact after checking it
- output containing negative markers such as missing/not found/no such file

It must accept generic strict proof such as:

```text
test -x /tmp/CompCert/ccomp
/tmp/CompCert/ccomp -version
```

when the cited call is completed, zero-exit, and unmasked.

### Patch 3: Make Acceptance Use The Shared Proof

Update `_has_long_dependency_artifact_evidence()` so an acceptance check passes
only when a cited evidence ref satisfies the same strict proof contract that
`long_dependency_build_state` uses.

Keep the external blocker wording stable unless tests need a clearer message.
The purpose is to unify authority, not redesign user-facing output.

### Patch 4: Add Agreement Tests

Add focused tests proving acceptance and resume agree on the same fixtures:

- timed-out build output mentioning `/tmp/CompCert/ccomp` does not prove the
  artifact
- nonzero command output mentioning the artifact does not prove it
- masked soft probes such as `test -x artifact || true` do not prove it
- artifact-mutating command surfaces do not prove it
- strict executable/version probes do prove it
- the same session fixture yields no acceptance blocker and no
  `missing_or_unproven` resume state when proof is valid

### Patch 5: Optional Stable Blocker Codes

If the proof miss shows repeated repair-routing ambiguity, add internal blocker
objects:

```text
code
layer
message
evidence_refs
suggested_next
```

Keep string output unchanged for CLI compatibility. This is optional for the
first go patch; do not expand scope unless the proof miss specifically shows
free-text blocker routing caused the failure.

### Validation

Run focused validation first:

```text
uv run pytest --no-testmon tests/test_acceptance.py -q
uv run pytest --no-testmon tests/test_work_session.py -k 'long_dependency or work_finish' -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py tests/test_acceptance.py tests/test_work_session.py
git diff --check
```

Then run the same-shape score sequence:

```text
compile-compcert speed_1
compile-compcert proof_5 only if speed_1 passes or moves the failure in the intended way
```

For CPU-heavy long dependency/toolchain proof, preserve the current resource
normalization rule: sequential five-trial proof is `-k 5 -n 1`, not `-k 1 -n 5`
and not parallel `-k 5 -n 5`.

### Rollback

Rollback if the shared resolver creates a false block on strict successful
artifact evidence, worsens the speed_1 path without exposing a real proof gap,
or changes behavior outside the selected generic contract. Record the rollback
as M6.24 process evidence rather than burying it in local code churn.

## Bottom Line

The architecture already has many valuable gates, and recent M6.24 repairs are
moving failures from false finish toward real task execution. The main
remaining structural weakness in this area is not missing prompt guidance; it
is duplicated evidence authority.

The right next action is still the pending `compile-compcert` proof_5. If that
proof misses on artifact-proof disagreement, the smallest durable repair is a
shared, typed evidence/proof resolver with long-dependency final artifact proof
unified across acceptance and resume state.
