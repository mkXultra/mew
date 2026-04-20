# M3 Proof Isolation Docker Foundation

Generated: 2026-04-20 10:10 JST

Source:

- `docs/REVIEW_2026-04-20_M3_PROOF_ISOLATION.md`

Decision:

Adopt the separate-environment strategy, starting with local Docker. VPS
provisioning remains a human decision because it creates external cost and
security responsibilities.

Implemented:

- `Dockerfile.proof`: builds a minimal Python 3.11 proof image and defaults to
  `mew dogfood --scenario resident-loop`
- `.dockerignore`: excludes local state, caches, auth, references, and proof
  output directories from the build context
- `scripts/run_proof_docker.sh`: builds the image and starts a detached
  resident-loop proof container with mounted workspace/artifact directories
- runtime commands use `uv run --no-sync` so proof execution does not mutate the
  environment by syncing development dependencies

Usage:

```bash
# one-hour real cadence proof
scripts/run_proof_docker.sh

# one-hour real run with one-week logical time
MEW_PROOF_DURATION=3600 \
MEW_PROOF_INTERVAL=60 \
MEW_PROOF_TIME_DILATION=168 \
MEW_PROOF_NAME=mew-proof-dilated-week \
scripts/run_proof_docker.sh

# follow output
docker logs -f mew-proof-dilated-week
```

Boundary:

Docker isolates filesystem and process state from the development checkout, but
it still depends on the host Mac staying awake. For real 24-hour or 1-week
uptime proof, the recommended next step is a pinned tag on a small VPS or other
always-on machine.

Validation:

```bash
docker build -f Dockerfile.proof -t mew-proof:validation .
MEW_PROOF_NAME=mew-proof-validation-nosync \
MEW_PROOF_DURATION=7 \
MEW_PROOF_INTERVAL=2 \
MEW_PROOF_TIME_DILATION=3600 \
MEW_PROOF_WORKSPACE=/tmp/mew-proof-nosync-workspace \
MEW_PROOF_ARTIFACTS=/tmp/mew-proof-nosync-artifacts \
MEW_PROOF_IMAGE=mew-proof:validation-nosync \
scripts/run_proof_docker.sh
docker wait mew-proof-validation-nosync
docker logs mew-proof-validation-nosync
```

Result: `pass`

The validation container ran `resident-loop` with `time_dilation=3600.0`,
processed 4 events including 3 passive ticks, and passed all resident-loop
checks. The container logs showed no runtime dependency sync after switching to
`uv run --no-sync`.
