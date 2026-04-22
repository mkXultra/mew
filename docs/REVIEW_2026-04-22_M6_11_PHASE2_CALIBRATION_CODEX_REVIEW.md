# Findings

No active blocker-level findings.

The remaining prior concentration issue is resolved. The calibration checker now evaluates concentration unconditionally across counted calibration bundle types at [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:290), and the new tests pin both sides of the adopted proposal semantics: a mixed distribution can pass exactly at 40% in [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:382), while a compiler-monoculture replay root now fails in [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:587). The prior denominator / legacy-bundle dilution issue also remains fixed: ignored legacy bundles no longer enter `total_bundles`, as covered by [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:426). The latest refusal-breakdown adjustment is observability-only: it changes `refusal_by_type` reporting at [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:245) and [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:269) without changing `refusal_count`, `refusal_rate`, or any threshold predicate, and that reporting fix is pinned by [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:555).

# Verdict

Green for this bounded slice. The adopted proposal semantics that were previously in dispute are now met closely enough for Phase 3 rollout gating:

1. Off-schema rate is still measured against compiler bundles only at [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:287), with the denominator behavior pinned in [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:468).
2. Refusal rate is measured across counted replay bundles at [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:288), and the latest refusal-breakdown fix only changes observability keys rather than gate math. [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:245) [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:269)
3. The adopted 40% concentration rule is now enforced for compiler-only roots instead of being bypassed. [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:290) [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:598)
4. The `proof-summary` CLI remains backward-compatible: calibration mode is opt-in via [`src/mew/cli.py`](/Users/mk/dev/personal-pj/mew/src/mew/cli.py:941) and dispatches cleanly in [`src/mew/commands.py`](/Users/mk/dev/personal-pj/mew/src/mew/commands.py:10434).

# Residual risks

- The adopted proposal text does not spell out malformed-bundle handling. The new `malformed_relevant_bundles_ok` gate at [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:291) is coherent and tested at [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:519), but it is stricter than what the proposal text states explicitly.
- [`ROADMAP_STATUS.md`](/Users/mk/dev/personal-pj/mew/ROADMAP_STATUS.md:1997) still summarizes the checkpoint mostly in terms of off-schema/refusal ratios, so the finer concentration and malformed-bundle behavior still mostly lives in code/tests plus the adopted proposal wording rather than this short status note.

# Recommended next step

Land this slice if the team accepts the stricter malformed-relevant-bundle policy as the implementation choice for the checkpoint, then keep any further semantic changes in a separate follow-up so Phase 3 gating does not drift again.
