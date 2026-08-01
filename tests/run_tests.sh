#!/bin/bash
# Integration test suite — run from Autosys agent or any host with network access.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_DIR}/config/.env" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/config/.env"
fi

DATABRICKS_HOST="${DATABRICKS_HOST:?Set DATABRICKS_HOST in config/.env}"
DATABRICKS_JOB_ID="${DATABRICKS_JOB_ID:?Set DATABRICKS_JOB_ID in config/.env}"
DATABRICKS_TOKEN="${DATABRICKS_TOKEN:?Set DATABRICKS_TOKEN in config/.env}"

PASS=0
FAIL=0

run_test() {
  local name="$1"
  shift
  echo -n "TEST: ${name} ... "
  if "$@" >/dev/null 2>&1; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    FAIL=$((FAIL + 1))
  fi
}

test_network() {
  "${PROJECT_DIR}/scripts/check_network_egress.sh"
}

test_jobs_get() {
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 \
    "${DATABRICKS_HOST}/api/2.1/jobs/get?job_id=${DATABRICKS_JOB_ID}" \
    -H "Authorization: Bearer ${DATABRICKS_TOKEN}")
  [[ "$code" == "200" ]]
}

test_trigger() {
  export DATABRICKS_HOST DATABRICKS_JOB_ID DATABRICKS_TOKEN
  export IDEM_TOKEN="test-$(date +%s)-$$"
  OUTPUT=$("${PROJECT_DIR}/scripts/trigger_databricks_job.sh")
  echo "$OUTPUT" | grep -q "run_id="
}

test_idempotency() {
  export DATABRICKS_HOST DATABRICKS_JOB_ID DATABRICKS_TOKEN
  export IDEM_TOKEN="idempotency-test-fixed-token"
  OUT1=$("${PROJECT_DIR}/scripts/trigger_databricks_job.sh")
  OUT2=$("${PROJECT_DIR}/scripts/trigger_databricks_job.sh")
  RUN1=$(echo "$OUT1" | grep -o 'run_id=[0-9]*' | cut -d= -f2)
  RUN2=$(echo "$OUT2" | grep -o 'run_id=[0-9]*' | cut -d= -f2)
  [[ "$RUN1" == "$RUN2" ]]
}

echo "=== Autosys → Databricks Integration Tests ==="
echo

run_test "Trigger script unit tests" "${PROJECT_DIR}/tests/test_trigger_unit.sh"
run_test "Network + auth" test_network
run_test "Job exists (jobs/get)" test_jobs_get
run_test "Trigger job (run-now)" test_trigger
run_test "Idempotency (same run_id on retry)" test_idempotency

echo
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
