#!/usr/bin/env bash
set -euo pipefail

# Un apply reintentado reutiliza el tag inmutable si el push ya había terminado.
if aws ecr describe-images --region "$AGENT_REGION" \
  --repository-name "${AGENT_REPOSITORY#*/}" --image-ids "imageTag=$AGENT_TAG" >/dev/null 2>&1; then
  echo "La imagen del agente ya está publicada."
  exit 0
fi

aws ecr get-login-password --region "$AGENT_REGION" |
  docker login --username AWS --password-stdin "${AGENT_REPOSITORY%%/*}"
docker buildx build --platform linux/arm64 --provenance=false --push \
  -f "$AGENT_CONTEXT/container/Dockerfile" \
  -t "$AGENT_REPOSITORY:$AGENT_TAG" "$AGENT_CONTEXT"
