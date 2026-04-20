#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${MEW_PROOF_IMAGE:-mew-proof:latest}"
NAME="${MEW_PROOF_NAME:-mew-proof-$(date +%Y%m%d-%H%M%S)}"
WORKSPACE="${MEW_PROOF_WORKSPACE:-$ROOT/proof-workspace/$NAME}"
ARTIFACTS="${MEW_PROOF_ARTIFACTS:-$ROOT/proof-artifacts/$NAME}"
DURATION="${MEW_PROOF_DURATION:-3600}"
INTERVAL="${MEW_PROOF_INTERVAL:-60}"
POLL_INTERVAL="${MEW_PROOF_POLL_INTERVAL:-0.2}"
TIME_DILATION="${MEW_PROOF_TIME_DILATION:-}"

mkdir -p "$WORKSPACE" "$ARTIFACTS"

docker build -f "$ROOT/Dockerfile.proof" -t "$IMAGE" "$ROOT"

command=(
  uv run --no-sync mew dogfood
  --scenario resident-loop
  --duration "$DURATION"
  --interval "$INTERVAL"
  --poll-interval "$POLL_INTERVAL"
  --workspace /proof/workspace
  --json
)

if [[ -n "$TIME_DILATION" ]]; then
  command+=(--time-dilation "$TIME_DILATION")
fi

docker run \
  --detach \
  --name "$NAME" \
  --restart no \
  -v "$WORKSPACE:/proof/workspace" \
  -v "$ARTIFACTS:/proof/artifacts" \
  -e MEW_PROOF_MODE=1 \
  "$IMAGE" \
  "${command[@]}"

cat <<EOF
started $NAME
workspace: $WORKSPACE
artifacts: $ARTIFACTS
logs: docker logs -f $NAME
inspect: docker inspect $NAME
EOF
