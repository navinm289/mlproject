#!/bin/bash
# Install integration artifacts on the Autosys agent host.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/autosys/scripts}"
LOG_DIR="${LOG_DIR:-/var/autosys/log}"
AUTOSYS_USER="${AUTOSYS_USER:-autosys_svc}"

echo "Installing Autosys → Databricks integration..."
echo "  Script dir: ${INSTALL_DIR}"
echo "  Log dir:    ${LOG_DIR}"

sudo mkdir -p "$INSTALL_DIR" "$LOG_DIR"
sudo cp "${SCRIPT_DIR}/trigger_databricks_job.sh" "${INSTALL_DIR}/"
sudo chmod 755 "${INSTALL_DIR}/trigger_databricks_job.sh"
sudo chown "${AUTOSYS_USER}:${AUTOSYS_USER}" "${INSTALL_DIR}/trigger_databricks_job.sh" 2>/dev/null || true
sudo chown "${AUTOSYS_USER}:${AUTOSYS_USER}" "$LOG_DIR" 2>/dev/null || true

echo "Installed: ${INSTALL_DIR}/trigger_databricks_job.sh"
echo
echo "Next:"
echo "  1. Create /etc/autosys/databricks.env with DATABRICKS_TOKEN (chmod 600)"
echo "  2. Load autosys/trigger_databricks_etl.jil"
echo "  3. Run: ${SCRIPT_DIR}/check_network_egress.sh"
