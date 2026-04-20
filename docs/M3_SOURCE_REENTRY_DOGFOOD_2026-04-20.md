# M3 Source Reentry Dogfood

Generated: 2026-04-20 10:58 JST

Purpose:

Move M3 reentry proof beyond README-only tasks. This dogfood scenario uses a
Python source file plus a unittest failure so the preserved reentry state must
carry a pending source edit, a failed verifier, touched source/test world state,
and an approve-then-verify next action.

Scenario:

```bash
./mew dogfood --scenario m3-source-reentry \
  --workspace proof-workspace/mew-proof-m3-source-reentry-local-20260420-1058 \
  --json
```

Result: `pass`

Checks:

- `m3_source_reentry_resume_has_source_edit_test_risk_next_action`: pass
- `m3_source_reentry_world_state_and_follow_snapshot_preserve_resume`: pass
- `m3_source_reentry_can_advance_to_passing_unittest`: pass

Evidence:

- source file: `mew_status.py`
- test file: `test_mew_status.py`
- continuity: `strong`
- continuity score: `9/9`
- pending approval count: `1`
- unresolved failure: `run_tests`
- unresolved failure exit code: `1`
- final verifier: pass after approving the pending source edit

Docker Isolation:

```bash
MEW_PROOF_NAME=mew-proof-m3-source-reentry-20260420-1058 \
MEW_PROOF_SCENARIO=m3-source-reentry \
MEW_PROOF_IMAGE=mew-proof:m3-source-reentry \
scripts/run_proof_docker.sh
docker wait mew-proof-m3-source-reentry-20260420-1058
scripts/collect_proof_docker.sh mew-proof-m3-source-reentry-20260420-1058
```

Docker result: `pass`

Collected artifacts:

- `proof-artifacts/mew-proof-m3-source-reentry-20260420-1058/stdout.log`
- `proof-artifacts/mew-proof-m3-source-reentry-20260420-1058/stderr.log`
- `proof-artifacts/mew-proof-m3-source-reentry-20260420-1058/inspect.json`
- `proof-artifacts/mew-proof-m3-source-reentry-20260420-1058/summary.txt`

Interpretation:

This is still synthetic, but it is a stronger task shape than README-only
proofs. It shows mew can preserve and resume a source/test coding interruption:
the model can return to a pending source diff, prior unittest failure, world
state for both source and test files, and a runnable approve-then-verify path.

Boundary:

This does not replace a real multi-hour resident cadence proof or a fresh CLI
comparator on the same source/test shape. It closes part of the "tiny README
task" gap by proving the mew-side source/test reentry path.

Strict Fresh Comparator:

The source/test shape was also compared against a strict fresh restart in a
non-git `/tmp` workspace:

```text
/tmp/mew-m3-source-fresh-strict-20260420-1100
```

Durable comparator inputs and output:

- template: `docs/M3_SOURCE_FRESH_TEMPLATE_2026-04-20.json`
- report: `docs/M3_SOURCE_FRESH_STRICT_COMPARATOR_2026-04-20.json`

Result:

- `status=passed`
- `manual_rebrief_needed=false`
- `repository_only_compliance=true`
- `verification_exit_code=0`
- `comparison_result.choice=mew_preferred`
- `repository_only_steps_before_first_correct_action=3`
- `needed_to_read_test_before_action=true`
- `needed_to_run_tests_before_action=false`
- `mew_saved_reconstruction=true`
- `mew_saved_test_rerun=false`
- `mew_prevented_wrong_first_action=false`

Interpretation:

The fresh CLI correctly recovered the source/test mismatch after reading the
test and source. mew is still preferred for this reentry shape because it
already retained the pending source diff, the prior failed unittest result, and
the queued approve-then-verify next action. The advantage here is
reconstruction efficiency, not preventing a wrong edit.
