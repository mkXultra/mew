#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

path = Path("generated/expected_totals.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["compact"] = {
    "100000": "$1k",
    "125000": "$1.2k",
    "2500000": "$25k",
}
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
