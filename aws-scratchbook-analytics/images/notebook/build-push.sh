#!/usr/bin/env bash
# Build and push scratchbook notebook image to ECR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACCOUNT_ID="${ACCOUNT_ID:?Set ACCOUNT_ID}"
REGION="${REGION:-us-east-1}"
REPO="${REPO:-scratchbook-notebook}"
TAG="${TAG:-1.0.0}"
IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker build -t "$IMAGE" "$SCRIPT_DIR"
docker push "$IMAGE"
echo "Pushed ${IMAGE}"
echo "Set jupyterhub/values.yaml singleuser.image.name/tag accordingly."
