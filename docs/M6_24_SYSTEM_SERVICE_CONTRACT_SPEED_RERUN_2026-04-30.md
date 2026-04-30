# M6.24 System Service Contract Speed Rerun - 2026-04-30

Task: `git-multibranch`

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-system-service-contract-git-multibranch-1attempt-20260430-0247/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `0/1`
- runtime: `2m 7s`

## Observed Behavior

The v0 THINK prompt-policy repair was insufficient.

The THINK phase selected the right shape: a bounded `run_command` that would
configure the exact SSH Git server, `/git/project`, Nginx HTTPS endpoint, and
post-receive hook, then verify with real pushes.

The ACT phase converted that command to `wait`:

```text
Cannot execute the proposed setup because it would write to /git, /etc/ssh,
/etc/nginx, /etc/ssl, and /var/www, which are outside the allowed write roots:
., /usr/local/bin, /tmp.
```

External verifier then failed with `ssh: connect to host localhost port 22:
Connection refused`.

## Decision

The gap remains selected:

`system_service_state_permission_contract`

Next repair:

`system_service_state_act_capability_boundary`

The prompt-policy boundary must be applied to ACT, not only THINK:

- if THINK chose a shell-authorized `run_command` for explicit system-service
  state, ACT must not convert it to `wait` solely because native write roots do
  not cover `/git`, `/srv`, `/var`, `/run`, or `/etc`;
- ACT should still reject resident mew loops, sensitive host-secret access, and
  unsupported actions.

Same-shape rerun after v0.1:

Run another one-trial `git-multibranch` speed proof. Success means the run no
longer stops at the ACT write-root wait and either improves reward or moves to
a concrete service/verifier failure.
