#!/usr/bin/env python3
'''Product-named Python entrypoint for the local mew-wisp CLI.

Keeps ghost.py as the historical implementation module while exposing a named
operator path.
'''

from __future__ import annotations

from ghost import main


if __name__ == '__main__':
    raise SystemExit(main())
