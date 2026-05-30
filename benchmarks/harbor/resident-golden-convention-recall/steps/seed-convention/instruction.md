Add a compact total rendering mode to the price rules.

`render_total(cents, mode="compact")` should keep normal dollar formatting
below $1000. At $1000 and above, it should use a lowercase `k` suffix, with one
decimal place only when needed.

Keep the existing standard mode working. Generated expected-output snapshots are
not the source of truth for this change.
