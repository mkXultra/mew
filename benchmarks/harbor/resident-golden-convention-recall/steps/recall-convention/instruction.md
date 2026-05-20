Add a delayed delivery status to the ETA rules.

`delivery_summary("delayed", business_days)` should return
`Delayed; new estimate is N business days`.

Keep the existing queued and shipped statuses working. Generated
expected-output snapshots are protected and should not be edited by hand.
