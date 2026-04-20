#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/collect_proof_docker.sh <container-name> [artifact-dir]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="$1"
ARTIFACTS="${2:-$ROOT/proof-artifacts/$NAME}"

mkdir -p "$ARTIFACTS"

docker inspect "$NAME" > "$ARTIFACTS/inspect.json"
docker logs "$NAME" > "$ARTIFACTS/stdout.log" 2> "$ARTIFACTS/stderr.log"

status="$(docker inspect "$NAME" --format '{{.State.Status}}')"
exit_code="$(docker inspect "$NAME" --format '{{.State.ExitCode}}')"
started_at="$(docker inspect "$NAME" --format '{{.State.StartedAt}}')"
finished_at="$(docker inspect "$NAME" --format '{{.State.FinishedAt}}')"
image="$(docker inspect "$NAME" --format '{{.Config.Image}}')"

cat > "$ARTIFACTS/summary.txt" <<EOF
container: $NAME
image: $image
status: $status
exit_code: $exit_code
started_at: $started_at
finished_at: $finished_at
stdout: $ARTIFACTS/stdout.log
stderr: $ARTIFACTS/stderr.log
inspect: $ARTIFACTS/inspect.json
EOF

cat "$ARTIFACTS/summary.txt"
