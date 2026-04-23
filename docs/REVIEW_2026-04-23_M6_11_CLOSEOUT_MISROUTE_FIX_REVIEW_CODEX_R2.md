STATUS: ISSUES

FINDINGS:
- High | src/mew/work_loop.py:1281 | The new unconditional `repair`/`edit` escape fixes the prior repair overmatch, but it also lets closeout artifact work such as "Edit calibration ledger with the non-counted closeout row" bypass `_work_plan_item_is_verifier_closeout`. With preserved verifier evidence and stale source/test cached windows, that wording can still activate the write-ready tiny-draft path for ledger closeout work, which is the misroute this slice is meant to prevent.
- Medium | tests/test_work_session.py:7387 | Coverage now pins the no-change `Record ... calibration ledger` case and the `Repair ... closeout ... source/test` case, but it does not cover a ledger-closeout item phrased as an edit/write action. That leaves the regression above untested.

RECOMMENDATION: revise before commit; distinguish source/test repair/edit intent from calibration-ledger closeout/edit intent, then add a negative test for an `Edit calibration ledger ... closeout` plan item. The proof-summary/work-replay non-counted model-failure accounting still looks compatible with existing counted metrics.
