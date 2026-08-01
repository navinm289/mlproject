#!/bin/bash
# Unit tests for trigger script logic (no live Databricks required).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIGGER="${SCRIPT_DIR}/../scripts/trigger_databricks_job.sh"
MOCK_BIN=$(mktemp -d)

cleanup() { rm -rf "$MOCK_BIN"; }
trap cleanup EXIT

cat > "${MOCK_BIN}/curl" <<'MOCK'
#!/bin/bash
if [[ "$*" == *"run-now"* ]]; then
  printf '{"run_id":9876543210,"number_in_job":9876543210}\n200'
  exit 0
fi
printf '403\n'
exit 0
MOCK
chmod +x "${MOCK_BIN}/curl"

export PATH="${MOCK_BIN}:${PATH}"
export DATABRICKS_HOST="https://test.cloud.databricks.com"
export DATABRICKS_JOB_ID="123456789012345"
export DATABRICKS_TOKEN="test-token"
export IDEM_TOKEN="unit-test-token"

OUTPUT=$("$TRIGGER")
echo "$OUTPUT" | grep -q "run_id=9876543210" || { echo "FAIL: expected run_id in output"; exit 1; }
echo "PASS: trigger script returns run_id on mocked 200 response"

# Failure path
cat > "${MOCK_BIN}/curl" <<'MOCK'
#!/bin/bash
printf '{"error_code":"INVALID_PARAMETER_VALUE"}\n400'
MOCK
chmod +x "${MOCK_BIN}/curl"

if "$TRIGGER" 2>/dev/null; then
  echo "FAIL: expected exit 1 on HTTP 400"
  exit 1
fi
echo "PASS: trigger script exits 1 on HTTP 400"

echo "All unit tests passed."
