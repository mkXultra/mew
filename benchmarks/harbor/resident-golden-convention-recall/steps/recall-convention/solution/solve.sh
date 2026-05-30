#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path

path = Path("src/golden_convention/eta_rules.py")
path.write_text(
    '''def delivery_summary(status: str, business_days: int) -> str:
    if status == "queued":
        return f"Leaves warehouse in {business_days} business days"
    if status == "shipped":
        return f"Arrives in {business_days} business days"
    if status == "delayed":
        return f"Delayed; new estimate is {business_days} business days"
    raise ValueError(f"unsupported delivery status: {status}")
''',
    encoding="utf-8",
)
PY
