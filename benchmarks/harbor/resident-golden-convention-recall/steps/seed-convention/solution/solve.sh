#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path

path = Path("src/golden_convention/price_rules.py")
path.write_text(
    '''def render_total(cents: int, mode: str = "standard") -> str:
    dollars, remainder = divmod(cents, 100)
    if mode == "standard":
        return f"${dollars}.{remainder:02d}"
    if mode == "compact":
        if cents < 100000:
            return f"${dollars}.{remainder:02d}"
        thousands = cents / 100000
        text = f"{thousands:.1f}".rstrip("0").rstrip(".")
        return f"${text}k"
    raise ValueError(f"unsupported total render mode: {mode}")
''',
    encoding="utf-8",
)
PY
