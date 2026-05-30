#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="${fixture_dir}/proof/validation-output"
rm -rf "${out_dir}"
mkdir -p "${out_dir}"

run_case() {
  local step="$1"
  local phase="$2"
  local solution_kind="$3"
  local expect="$4"
  local case_dir="${out_dir}/${step}-${solution_kind}"
  local app_dir="${case_dir}/app"
  local tests_dir="${case_dir}/tests"
  local logs_dir="${case_dir}/logs/verifier"

  mkdir -p "${app_dir}" "${tests_dir}" "${logs_dir}"
  cp -R "${fixture_dir}/environment/fixture-src/${phase}/." "${app_dir}/"
  cp -R "${fixture_dir}/tests/." "${tests_dir}/"
  cp -R "${fixture_dir}/steps/${step}/tests/." "${tests_dir}/"

  (
    cd "${app_dir}"
    bash "${fixture_dir}/steps/${step}/${solution_kind}/solve.sh"
  ) >"${case_dir}/solution.stdout" 2>"${case_dir}/solution.stderr"

  set +e
  (
    cd "${app_dir}"
    APP_DIR="${app_dir}" TEST_DIR="${tests_dir}" VERIFIER_LOG_DIR="${logs_dir}" \
      bash "${tests_dir}/test.sh"
  ) >"${case_dir}/verifier.stdout" 2>"${case_dir}/verifier.stderr"
  local status=$?
  set -e

  printf '%s\n' "${status}" >"${case_dir}/verifier.exit"
  if [[ "${expect}" == "pass" && "${status}" -ne 0 ]]; then
    echo "expected ${step}/${solution_kind} to pass, got exit ${status}" >&2
    return 1
  fi
  if [[ "${expect}" == "fail" && "${status}" -eq 0 ]]; then
    echo "expected ${step}/${solution_kind} to fail, got exit 0" >&2
    return 1
  fi

  python3 - "${logs_dir}/reward.json" "${logs_dir}/resident-memory-metrics.json" "${expect}" <<'PY'
import json
import sys
from pathlib import Path

reward_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])
expect = sys.argv[3]

if not reward_path.exists():
    raise SystemExit(f"missing reward.json: {reward_path}")
reward = json.loads(reward_path.read_text())
if list(reward.keys()) != ["reward"]:
    raise SystemExit(f"reward.json must contain exactly one reward key, got {reward!r}")
expected_reward = 1.0 if expect == "pass" else 0.0
if reward["reward"] != expected_reward:
    raise SystemExit(
        f"reward.json reward mismatch: expected {expected_reward}, got {reward['reward']!r}"
    )

if not metrics_path.exists():
    raise SystemExit(f"missing resident-memory-metrics.json: {metrics_path}")
metrics = json.loads(metrics_path.read_text())
if not isinstance(metrics, dict) or not metrics:
    raise SystemExit(f"metrics file must contain a non-empty object, got {metrics!r}")
if expect == "pass" and "failure" in metrics:
    raise SystemExit(f"passing case should not record failure metrics, got {metrics!r}")
if expect == "fail" and "failure" not in metrics:
    raise SystemExit(f"failing case should record failure reason, got {metrics!r}")
PY
}

run_case seed-convention phase-a-seed solution pass
run_case seed-convention phase-a-seed bad-solution fail
run_case recall-convention phase-b-recall solution pass
run_case recall-convention phase-b-recall bad-solution fail
run_case stale-memory phase-c-stale solution pass
run_case stale-memory phase-c-stale bad-solution fail

echo "fixture validation passed; logs in ${out_dir}"
