#!/bin/bash
# Trigger a Databricks job via Jobs API 2.1 run-now (fire-and-forget).
# Deploy to: /opt/autosys/scripts/trigger_databricks_job.sh
set -euo pipefail

if [[ -f /etc/autosys/databricks.env ]]; then
  # shellcheck disable=SC1091
  source /etc/autosys/databricks.env
fi

WORKSPACE_URL="${DATABRICKS_HOST:?DATABRICKS_HOST is required}"
JOB_ID="${DATABRICKS_JOB_ID:?DATABRICKS_JOB_ID is required}"
TOKEN="${DATABRICKS_TOKEN:?DATABRICKS_TOKEN is required}"

# Autosys injects AUTO_JOB_NAME and AUTO_RUN_ID when available
IDEM_TOKEN="${IDEM_TOKEN:-${AUTO_JOB_NAME:-autosys}-${AUTO_RUN_ID:-$$}-$(date +%Y%m%d)}"

CURL_OPTS=(-sS --max-time 60 -X POST)
if [[ -n "${HTTP_PROXY:-}" || -n "${HTTPS_PROXY:-}" ]]; then
  echo "Using proxy: HTTP_PROXY=${HTTP_PROXY:-} HTTPS_PROXY=${HTTPS_PROXY:-}"
fi

REQUEST_BODY=$(cat <<EOF
{"job_id": ${JOB_ID}, "idempotency_token": "${IDEM_TOKEN}"}
EOF
)

RESPONSE=$(curl "${CURL_OPTS[@]}" \
  "${WORKSPACE_URL}/api/2.1/jobs/run-now" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${REQUEST_BODY}" \
  -w "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "Databricks API failed: HTTP ${HTTP_CODE}" >&2
  echo "${BODY}" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  RUN_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || true)
else
  RUN_ID=$(echo "$BODY" | grep -o '"run_id":[0-9]*' | head -1 | cut -d: -f2)
fi

if [[ -z "$RUN_ID" ]]; then
  echo "Databricks API returned 200 but no run_id in response: ${BODY}" >&2
  exit 1
fi

echo "Triggered Databricks job_id=${JOB_ID} run_id=${RUN_ID} idempotency_token=${IDEM_TOKEN}"
exit 0
