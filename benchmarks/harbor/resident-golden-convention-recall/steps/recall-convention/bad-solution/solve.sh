#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

path = Path("generated/expected_delivery.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["delayed:1"] = "Delayed; new estimate is 1 business days"
data["delayed:9"] = "Delayed; new estimate is 9 business days"
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
