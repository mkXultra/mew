STATUS: ISSUES

FINDINGS:
- High | src/mew/work_loop.py:1290 | `_work_plan_item_is_verifier_closeout` returns true for any `ledger`, `closeout`, `non-counted`, `preserved verifier`, or `verifier evidence` marker before checking for `repair`, `edit`, or `patch`. With a passed preserved verifier, a legitimate repair plan item such as "Repair closeout misroute on the source/test pair" would deactivate the write-ready/tiny-draft path as `verifier_closeout_plan_item`, so normal verifier-closeout repair paths are not protected.
- Medium | tests/test_work_session.py:7387 | The new test covers the intended no-change ledger closeout suppression, but it does not cover a repair/edit plan item containing closeout or ledger wording. Existing repair-path coverage uses wording without those markers, so it would not catch the overmatch above.

RECOMMENDATION: revise before commit; narrow closeout classification to no-change/record/finish ledger closeouts and add a repair/edit counterexample test. The proof-summary/work-replay countedness path otherwise preserves default counted model-failure metrics and covers explicit non-counted exclusion.
