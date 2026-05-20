#!/usr/bin/env bash
set -euo pipefail

cd "${APP_DIR:-/app}"
export PYTHONPATH="${PWD}/src:/tests:${PYTHONPATH:-}"
python3 "${TEST_DIR:-/tests}/check_seed.py"
