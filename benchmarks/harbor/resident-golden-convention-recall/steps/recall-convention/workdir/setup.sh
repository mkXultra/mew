#!/usr/bin/env bash
set -euo pipefail

source_root="${FIXTURE_SRC:-/fixture-src}/phase-b-recall"
tmp_dir="$(mktemp -d)"
cp -R "${source_root}/." "${tmp_dir}/"
find . -mindepth 1 ! -name setup.sh -exec rm -rf {} +
cp -R "${tmp_dir}/." .
rm -rf "${tmp_dir}"
