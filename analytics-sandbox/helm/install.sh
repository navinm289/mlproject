#!/usr/bin/env bash
# Render templated manifests/values from config.env and install JupyterHub.
#
# Usage:
#   ./helm/install.sh            # render + apply + helm upgrade --install
#   DRY_RUN=1 ./helm/install.sh  # render to stdout only (no cluster access)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-${ROOT_DIR}/config.env}"

NAMESPACE="analytics-sandbox"
RELEASE="jupyterhub"
CHART="jupyterhub/jupyterhub"
CHART_VERSION="${CHART_VERSION:-3.3.8}"

DRY_RUN="${DRY_RUN:-0}"

command -v envsubst >/dev/null 2>&1 || { echo "ERROR: envsubst not found (install gettext)"; exit 1; }
if [[ "${DRY_RUN}" != "1" ]]; then
  command -v kubectl >/dev/null 2>&1 || { echo "ERROR: kubectl not found"; exit 1; }
  command -v helm >/dev/null 2>&1 || { echo "ERROR: helm not found"; exit 1; }
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "ERROR: ${CONFIG_FILE} not found. Copy config.env.example to config.env and fill it in."
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "${CONFIG_FILE}"; set +a

# Only substitute known vars so KubeSpawner tokens like {username} survive.
SUBST_VARS='${ACCOUNT_ID} ${REGION} ${EFS_FILE_SYSTEM_ID} ${HOST} ${ACM_CERT_ARN} ${OIDC_ISSUER} ${OIDC_CLIENT_ID} ${OIDC_CLIENT_SECRET} ${SINGLEUSER_IMAGE} ${SINGLEUSER_IMAGE_TAG}'

RENDER_DIR="$(mktemp -d)"
trap 'rm -rf "${RENDER_DIR}"' EXIT

envsubst "${SUBST_VARS}" < "${SCRIPT_DIR}/namespace-sa.yaml" > "${RENDER_DIR}/namespace-sa.yaml"
envsubst "${SUBST_VARS}" < "${SCRIPT_DIR}/efs-pvc.yaml"      > "${RENDER_DIR}/efs-pvc.yaml"
envsubst "${SUBST_VARS}" < "${SCRIPT_DIR}/values.yaml"       > "${RENDER_DIR}/values.yaml"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "===== namespace-sa.yaml ====="; cat "${RENDER_DIR}/namespace-sa.yaml"
  echo "===== efs-pvc.yaml =====";      cat "${RENDER_DIR}/efs-pvc.yaml"
  echo "===== values.yaml =====";       cat "${RENDER_DIR}/values.yaml"
  echo "===== (dry run) would run ====="
  echo "kubectl apply -f namespace-sa.yaml"
  echo "kubectl apply -f efs-pvc.yaml"
  echo "helm upgrade --install ${RELEASE} ${CHART} --version ${CHART_VERSION} -n ${NAMESPACE} -f values.yaml"
  exit 0
fi

kubectl apply -f "${RENDER_DIR}/namespace-sa.yaml"
kubectl apply -f "${RENDER_DIR}/efs-pvc.yaml"

helm repo add jupyterhub https://hub.jupyter.org/helm-chart/ >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install "${RELEASE}" "${CHART}" \
  --version "${CHART_VERSION}" \
  --namespace "${NAMESPACE}" \
  --values "${RENDER_DIR}/values.yaml" \
  --timeout 15m

echo "Done. Hub will be reachable at https://${HOST} once the ALB is provisioned."
