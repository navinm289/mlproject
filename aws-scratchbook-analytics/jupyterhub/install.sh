#!/usr/bin/env bash
# Install/upgrade a per-team JupyterHub for a given environment.
#
# Usage:
#   ./install.sh <team> <env>
# Example:
#   ./install.sh retail-cards dev
#   ./install.sh brands prod
#
# Env vars:
#   DRY_RUN=1   Render manifests/values only; do not touch the cluster.
#
# Requires: helm, kubectl, envsubst (gettext). Cluster context must already
# point at the target environment's EKS cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TEAM="${1:-}"
ENV="${2:-}"

if [[ -z "$TEAM" || -z "$ENV" ]]; then
  echo "Usage: $0 <team> <env>" >&2
  echo "  teams:  $(ls "${SCRIPT_DIR}/teams" 2>/dev/null | sed 's/.yaml//' | tr '\n' ' ')" >&2
  echo "  envs:   dev uat prod" >&2
  exit 1
fi

BASE_VALUES="${SCRIPT_DIR}/base-values.yaml"
ENV_TMPL="${SCRIPT_DIR}/envs/${ENV}.yaml"
TEAM_TMPL="${SCRIPT_DIR}/teams/${TEAM}.yaml"
STORAGE_TMPL="${SCRIPT_DIR}/storage/efs-pvc.tmpl.yaml"
RBAC_TMPL="${SCRIPT_DIR}/rbac/singleuser-sa.tmpl.yaml"
CONFIG_FILE="${SCRIPT_DIR}/config/${ENV}.env"

for f in "$BASE_VALUES" "$ENV_TMPL" "$TEAM_TMPL" "$STORAGE_TMPL" "$RBAC_TMPL"; do
  [[ -f "$f" ]] || { echo "ERROR: missing file: $f" >&2; exit 1; }
done
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "ERROR: missing ${CONFIG_FILE}. Copy config/${ENV}.env.example and fill it in." >&2
  exit 1
fi

# envsubst is always required (rendering). helm/kubectl only for a real deploy.
command -v envsubst >/dev/null 2>&1 || { echo "ERROR: 'envsubst' (gettext) not found in PATH" >&2; exit 1; }
if [[ "${DRY_RUN:-0}" != "1" ]]; then
  for tool in helm kubectl; do
    command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' not found in PATH" >&2; exit 1; }
  done
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

# Derived values
export TEAM
export ENVIRONMENT="$ENV"
export NAMESPACE="jhub-${TEAM}"
export RELEASE="jhub-${TEAM}"
export HOST="${TEAM}.${ENV}.${DOMAIN}"
export HMS_THRIFT_URI="thrift://${HMS_SERVICE}.${HMS_NAMESPACE}.svc.cluster.local:9083"

# Re-export config vars so envsubst sees them
export ACCOUNT_ID REGION LAKE_BUCKET EFS_FILE_SYSTEM_ID HMS_NAMESPACE HMS_SERVICE \
  DOMAIN OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET ECR_REPO IMAGE_TAG

# Only substitute known variables (protect KubeSpawner tokens like {username})
SUBST_VARS='${ACCOUNT_ID} ${REGION} ${LAKE_BUCKET} ${EFS_FILE_SYSTEM_ID} ${HMS_NAMESPACE} ${HMS_SERVICE} ${DOMAIN} ${OIDC_ISSUER} ${OIDC_CLIENT_ID} ${OIDC_CLIENT_SECRET} ${ECR_REPO} ${IMAGE_TAG} ${TEAM} ${ENVIRONMENT} ${NAMESPACE} ${RELEASE} ${HOST} ${HMS_THRIFT_URI}'

RENDER_DIR="$(mktemp -d)"
trap 'rm -rf "$RENDER_DIR"' EXIT

envsubst "$SUBST_VARS" < "$ENV_TMPL"     > "${RENDER_DIR}/env-values.yaml"
envsubst "$SUBST_VARS" < "$TEAM_TMPL"    > "${RENDER_DIR}/team-values.yaml"
envsubst "$SUBST_VARS" < "$STORAGE_TMPL" > "${RENDER_DIR}/storage.yaml"
envsubst "$SUBST_VARS" < "$RBAC_TMPL"    > "${RENDER_DIR}/rbac.yaml"

echo "=== Rendering complete ==="
echo "  team:      ${TEAM}"
echo "  env:       ${ENV}"
echo "  namespace: ${NAMESPACE}"
echo "  release:   ${RELEASE}"
echo "  host:      https://${HOST}"
echo "  HMS:       ${HMS_THRIFT_URI}"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo
  echo "DRY_RUN=1 -> rendered files in ${RENDER_DIR} (copying to ./rendered-${TEAM}-${ENV})"
  cp -r "$RENDER_DIR" "${SCRIPT_DIR}/rendered-${TEAM}-${ENV}"
  echo "Wrote ${SCRIPT_DIR}/rendered-${TEAM}-${ENV}"
  exit 0
fi

echo "=== Applying namespace, ServiceAccount (IRSA), NetworkPolicy ==="
kubectl apply -f "${RENDER_DIR}/rbac.yaml"

echo "=== Applying EFS PVCs ==="
kubectl apply -f "${RENDER_DIR}/storage.yaml"

echo "=== Helm upgrade --install ${RELEASE} ==="
helm repo add jupyterhub https://hub.jupyter.org/helm-chart/ >/dev/null 2>&1 || true
helm repo update jupyterhub >/dev/null

helm upgrade --install "$RELEASE" jupyterhub/jupyterhub \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --version 3.3.8 \
  -f "$BASE_VALUES" \
  -f "${RENDER_DIR}/env-values.yaml" \
  -f "${RENDER_DIR}/team-values.yaml" \
  --timeout 15m \
  --wait

echo "Done. ${TEAM}/${ENV} available at https://${HOST}"
