#!/usr/bin/env bash
# Seed /shared/examples on EFS (run from a node/pod that can write the shared PVC).
# No Git — copies local bootstrap notebooks onto the shared EFS path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:-/shared/examples}"

mkdir -p "$TARGET"
cp -f "${SCRIPT_DIR}/read_iceberg_via_hms.ipynb" "${TARGET}/"
chmod -R a+rX "$TARGET"
echo "Seeded notebooks into ${TARGET}"
ls -la "$TARGET"
