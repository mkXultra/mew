#!/usr/bin/env bash
set -euo pipefail

mkdir -p src/golden_convention/legacy_layout generated/legacy
python3 - <<'PY'
import json
from pathlib import Path

Path("src/golden_convention/legacy_layout/__init__.py").write_text("", encoding="utf-8")
Path("src/golden_convention/legacy_layout/label_rules.py").write_text(
    '''def delivery_label(channel: str, code: str) -> str:
    normalized = code.strip().upper()
    if channel == "locker":
        return f"LOCKER-{normalized}: hold for pickup"
    raise ValueError(f"unsupported delivery channel: {channel}")
''',
    encoding="utf-8",
)
Path("generated/legacy/expected_labels.json").write_text(
    json.dumps({"locker:q7": "LOCKER-Q7: hold for pickup"}, indent=2) + "\n",
    encoding="utf-8",
)
PY
