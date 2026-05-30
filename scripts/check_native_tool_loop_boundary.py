#!/usr/bin/env python3
"""Run the M6.24 native tool-loop responsibility boundary audit."""

from __future__ import annotations

import sys
from pathlib import Path


def _repo_src() -> Path:
    return Path(__file__).resolve().parents[1] / "src"


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(_repo_src()))
    from mew.implement_lane.native_boundary_audit import main as audit_main

    return audit_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
