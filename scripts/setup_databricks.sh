#!/bin/bash
# Databricks setup helper — run from a machine with Databricks CLI configured.
# Requires: databricks CLI v0.200+ authenticated as workspace admin.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../config/.env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/../config/.env"
fi

SP_NAME="${DATABRICKS_SP_NAME:-autosys-trigger}"
JOB_ID="${DATABRICKS_JOB_ID:-}"
AUTOSYS_EGRESS_IP="${AUTOSYS_EGRESS_IP:-}"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  create-sp          Create service principal '${SP_NAME}'
  grant-job-access   Grant Can Manage Run on job \${DATABRICKS_JOB_ID}
  add-ip-allowlist   Add \${AUTOSYS_EGRESS_IP} to IP access list
  verify             Verify job exists and permissions

Set variables in config/.env before running.
EOF
}

require_cli() {
  if ! command -v databricks >/dev/null 2>&1; then
    echo "ERROR: Databricks CLI not installed. See https://docs.databricks.com/aws/en/dev-tools/cli/"
    exit 1
  fi
}

cmd="${1:-}"

case "$cmd" in
  create-sp)
    require_cli
    echo "Creating service principal: ${SP_NAME}"
    databricks service-principals create --display-name "$SP_NAME"
    echo
    echo "Next steps:"
    echo "  1. Generate OAuth secret or PAT for this service principal"
    echo "  2. Store token in Autosys secure credential store"
    echo "  3. Run: $0 grant-job-access"
    ;;

  grant-job-access)
    require_cli
    [[ -n "$JOB_ID" ]] || { echo "Set DATABRICKS_JOB_ID in config/.env"; exit 1; }
    SP_ID=$(databricks service-principals list --filter "displayName eq '${SP_NAME}'" --output json \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Resources'][0]['id'] if d.get('Resources') else '')" 2>/dev/null || true)
    [[ -n "$SP_ID" ]] || { echo "Service principal '${SP_NAME}' not found. Run: $0 create-sp"; exit 1; }
    echo "Granting CAN_MANAGE_RUN on job ${JOB_ID} to ${SP_NAME} (${SP_ID})"
    databricks permissions update jobs "$JOB_ID" --json "{
      \"access_control_list\": [{
        \"service_principal_name\": \"${SP_ID}\",
        \"permission_level\": \"CAN_MANAGE_RUN\"
      }]
    }"
    echo "Done."
    ;;

  add-ip-allowlist)
    require_cli
    [[ -n "$AUTOSYS_EGRESS_IP" ]] || { echo "Set AUTOSYS_EGRESS_IP in config/.env"; exit 1; }
    echo "Adding IP ${AUTOSYS_EGRESS_IP} to access list..."
    databricks ip-access-lists create --json "{
      \"label\": \"autosys-prod\",
      \"list_type\": \"ALLOW\",
      \"ip_addresses\": [\"${AUTOSYS_EGRESS_IP}/32\"],
      \"enabled\": true
    }" 2>/dev/null || {
      echo "Note: If list exists, update via Admin Console → Settings → IP Access Lists"
    }
    ;;

  verify)
    require_cli
    [[ -n "$JOB_ID" ]] || { echo "Set DATABRICKS_JOB_ID in config/.env"; exit 1; }
    echo "Verifying job ${JOB_ID}..."
    databricks jobs get "$JOB_ID" --output json | python3 -m json.tool 2>/dev/null || databricks jobs get "$JOB_ID"
    ;;

  *)
    usage
    exit 1
    ;;
esac
