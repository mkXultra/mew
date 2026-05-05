# Review: M6.24 Post-Loop Source Signal Repair

Reviewer: codex-ultra

Session: `019de5fe-2059-7bd2-8853-4184e3e1f472`

Final status: `APPROVE`

## Final Finding

The ordered nonterminal source proof is acceptable for this repair.

Closed false-positive classes:

- pre-fetch static hash output
- pre-fetch dynamic hash output
- pre-fetch heredoc hash output
- pre-fetch Python-generated hash output
- same-line stdout before fetch
- post-fetch fake hash before real hash/proof commands
- failable setup between hash and validation
- command-substitution assignment after hash
- nounset assignment after hash
- failable builtin after hash

The positive post-loop later-build-failure case remains valid and still
satisfies `source_authority`.

## Residual Risk

The post-hash allowlist is conservative, so some real scripts with harmless
`mkdir` or `cd` after hashing may remain false negatives. This is non-blocking:
the repair favors avoiding unsafe source-authority approvals.

