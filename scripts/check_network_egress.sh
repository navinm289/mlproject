#!/bin/bash
# Run on the Autosys agent host to validate outbound connectivity to Databricks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/../config/.env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/../config/.env"
fi

DATABRICKS_HOST="${DATABRICKS_HOST:?Set DATABRICKS_HOST in config/.env}"
DATABRICKS_TOKEN="${DATABRICKS_TOKEN:-}"

echo "=== Autosys → Databricks Network Validation ==="
echo "Host: ${DATABRICKS_HOST}"
echo

echo "[1/4] Detecting egress IP..."
if command -v curl >/dev/null 2>&1; then
  EGRESS_IP=$(curl -sS --max-time 10 https://ifconfig.me/ip || curl -sS --max-time 10 https://api.ipify.org || echo "unknown")
  echo "  Egress IP: ${EGRESS_IP}"
  echo "  Add this IP to Databricks IP Access List (label: autosys-prod)"
else
  echo "  ERROR: curl not found"
  exit 1
fi
echo

echo "[2/4] DNS resolution..."
if host "${DATABRICKS_HOST#https://}" >/dev/null 2>&1; then
  host "${DATABRICKS_HOST#https://}" | head -3
else
  getent hosts "${DATABRICKS_HOST#https://}" 2>/dev/null || nslookup "${DATABRICKS_HOST#https://}" 2>/dev/null || true
fi
echo

echo "[3/4] TCP/HTTPS reachability (no auth)..."
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "${DATABRICKS_HOST}/" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "000" || -z "$HTTP_CODE" ]]; then
  echo "  FAIL: Cannot reach ${DATABRICKS_HOST} (timeout, DNS failure, or firewall blocked)"
  echo "  Action: Request firewall rule for outbound HTTPS to *.cloud.databricks.com:443"
  exit 1
fi
echo "  OK: Received HTTP ${HTTP_CODE} from workspace"
echo

echo "[4/4] Jobs API auth test..."
if [[ -z "$DATABRICKS_TOKEN" ]]; then
  echo "  SKIP: DATABRICKS_TOKEN not set — set in config/.env to test authentication"
  exit 0
fi

AUTH_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 \
  "${DATABRICKS_HOST}/api/2.1/jobs/list" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}")

case "$AUTH_CODE" in
  200)
    echo "  OK: Authentication successful (HTTP 200)"
    ;;
  401)
    echo "  FAIL: HTTP 401 Unauthorized — check token"
    exit 1
    ;;
  403)
    echo "  FAIL: HTTP 403 Forbidden — likely IP not allowlisted (egress: ${EGRESS_IP})"
    exit 1
    ;;
  *)
    echo "  WARN: Unexpected HTTP ${AUTH_CODE}"
    exit 1
    ;;
esac

echo
echo "Network validation passed."
