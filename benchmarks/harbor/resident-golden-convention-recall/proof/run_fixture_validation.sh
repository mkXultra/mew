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
}

run_case seed-convention phase-a-seed solution pass
run_case seed-convention phase-a-seed bad-solution fail
run_case recall-convention phase-b-recall solution pass
run_case recall-convention phase-b-recall bad-solution fail
run_case stale-memory phase-c-stale solution pass
run_case stale-memory phase-c-stale bad-solution fail

echo "fixture validation passed; logs in ${out_dir}"
