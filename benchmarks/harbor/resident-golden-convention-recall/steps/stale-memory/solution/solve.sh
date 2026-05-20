#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path

path = Path("src/golden_convention/current_layout/label_rules.py")
path.write_text(
    '''def delivery_label(channel: str, code: str) -> str:
    normalized = code.strip().upper()
    if channel == "home":
        return f"HOME-{normalized}: doorstep delivery"
    if channel == "store":
        return f"STORE-{normalized}: customer desk"
    if channel == "locker":
        return f"LOCKER-{normalized}: hold for pickup"
    raise ValueError(f"unsupported delivery channel: {channel}")
''',
    encoding="utf-8",
)
PY
