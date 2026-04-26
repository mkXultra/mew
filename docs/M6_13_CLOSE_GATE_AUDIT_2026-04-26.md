# M6.13 Close-Gate Audit (2026-04-26)

Decision: CLOSE.

M6.13 is close-ready because the Phase 3 internalization proof now completes
the full loop rather than stopping at a planned patch:

1. A hard `review_rejected` work-loop task is materially advanced by the
   deliberation lane.
2. A durable reviewer decision artifact approves the distilled reasoning trace.
3. The trace is written to M6.9 reasoning memory with
   `source_lane=deliberation` and `same_shape_key`.
4. A later same-shape task retrieves it through the general
   `m6_9-ranked-recall` active-memory path.
5. The tiny lane drafts a paired source/test batch without re-invoking
   deliberation.
6. The batch previews through `run_work_batch_action`, applies through the
   normal approval batch path, and runs a real unittest verifier.

The replay bundle records:

- `execution_path=run_work_batch_action->_apply_work_approval_batch`
- `approval_count=2`
- `deferred_verification_count=1`
- `final_source_verification_exit_code=0`
- `verification_test_count>=1`
- `files_reflect_patch=true`
- `close_evidence=true`
- `close_blockers=[]`

Codex-ultra reviewer session `019dc96d-a73d-7762-baa4-6af2430c61b9`
approved this shape after rejecting the earlier harness-applied overclaim.

## Validation

Passed on 2026-04-26:

- `uv run pytest -q tests/test_dogfood.py -k 'm6_13' --no-testmon`
- `uv run pytest -q tests/test_dogfood.py tests/test_work_session.py -k 'm6_13 or approve_all or paired' --no-testmon`
- `uv run pytest -q tests/test_dogfood.py --no-testmon`
- `uv run pytest -q tests/test_work_session.py -k 'approve_all or paired' --no-testmon`
- `./mew dogfood --scenario m6_13-deliberation-internalization --workspace /tmp/mew-m6-13-proof-cli-3 --json --report /tmp/mew-m6-13-proof-cli-3-report.json`
- `./mew dogfood --scenario m6_13-deliberation-internalization --ai --auth auth.json --model-backend codex --model gpt-5.5 --model-timeout 120 --workspace /tmp/mew-m6-13-live-gpt55-2 --json --report /tmp/mew-m6-13-live-gpt55-2-report.json`
- `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`
- `git diff --check`

## Deferred Work

M6.13 does not implement statistical lane routing, write-capable
deliberation, memory explorer agentization, concurrent executors, or
provider-specific prompt caching. Those remain post-close work and should be
handled by M6.16/M6.17 or later milestones only when their gates require them.
