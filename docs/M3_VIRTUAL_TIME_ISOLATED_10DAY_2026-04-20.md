# M3 Virtual-Time Isolated 10-Day Proof

Generated: 2026-04-20 10:27 JST

Purpose:

Before attempting longer real-time M3 cadence proof, use virtual time to expose
date, passive tick, question, memory, and repeated-wait behavior across many
logical days in a short isolated run.

Command:

```bash
MEW_PROOF_NAME=mew-proof-virtual-10day-backoff-20260420-1024 \
MEW_PROOF_DURATION=90 \
MEW_PROOF_INTERVAL=5 \
MEW_PROOF_TIME_DILATION=10080 \
MEW_PROOF_IMAGE=mew-proof:virtual-10day-backoff \
scripts/run_proof_docker.sh
docker wait mew-proof-virtual-10day-backoff-20260420-1024
scripts/collect_proof_docker.sh mew-proof-virtual-10day-backoff-20260420-1024
```

Result: `pass`

Evidence:

- Real run duration: about 90 seconds
- Logical passive span: `814680.0` seconds, about 9.4 days between the first
  and last passive tick
- Processed events: `18`
- Passive events: `17`
- Time dilation: `10080.0`
- Resident-loop checks passed:
  - starts and stops cleanly
  - processes multiple events
  - records passive effects
  - compacts repeated wait thoughts
  - echoes passive output
- Collected artifacts:
  - `proof-artifacts/mew-proof-virtual-10day-backoff-20260420-1024/stdout.log`
  - `proof-artifacts/mew-proof-virtual-10day-backoff-20260420-1024/stderr.log`
  - `proof-artifacts/mew-proof-virtual-10day-backoff-20260420-1024/inspect.json`
  - `proof-artifacts/mew-proof-virtual-10day-backoff-20260420-1024/summary.txt`

Bug Found First:

The first isolated 10-day virtual run failed. It exposed that passive task
questions could refresh every logical day or so when the user stayed silent.
The runtime did not crash, but it accumulated duplicate task questions and
prevented the repeated-wait compaction check from passing.

Fix:

Passive task-question refresh now backs off by prior same-question refresh
count:

- first refresh after `24h`
- second after `48h`
- third after `96h`
- later refreshes cap at `168h`

The passing run ended with only four task questions across the virtual span:
three deferred questions with 24h/48h/96h backoff and one currently open
question. Repeated wait thoughts compacted into repeat counts `3`, `6`, and
`4`.

Boundary:

This is not a real uptime proof. It proves that accelerated logical time can
exercise passive resident behavior and catch long-horizon state bugs before
spending hours or days on real-time cadence.
