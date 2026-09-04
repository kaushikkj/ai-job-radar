#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/ai-job-radar}"
IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
PUBLIC_API_URL="${PUBLIC_API_URL:-http://localhost:8000}"
STATE_FILE="$DEPLOY_PATH/.last-successful-tag"

cd "$DEPLOY_PATH"

previous_tag=""
if [[ -f "$STATE_FILE" ]]; then
  previous_tag="$(cat "$STATE_FILE" || true)"
fi

echo "Deploying AI Job Radar image tag: $IMAGE_TAG"
if [[ -n "$previous_tag" ]]; then
  echo "Previous successful tag: $previous_tag"
fi

export IMAGE_TAG PUBLIC_API_URL
podman compose -f compose.prod.yaml pull
podman compose -f compose.prod.yaml up -d --remove-orphans

check_health() {
  local i
  for i in {1..30}; do
    if curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

if check_health; then
  echo "$IMAGE_TAG" > "$STATE_FILE"
  echo "Deployment healthy: $IMAGE_TAG"
  podman compose -f compose.prod.yaml ps
  exit 0
fi

echo "Deployment health check failed."

if [[ -n "$previous_tag" && "$previous_tag" != "$IMAGE_TAG" ]]; then
  echo "Rolling back to $previous_tag"
  export IMAGE_TAG="$previous_tag"
  podman compose -f compose.prod.yaml pull
  podman compose -f compose.prod.yaml up -d --remove-orphans

  if check_health; then
    echo "Rollback successful: $previous_tag"
    podman compose -f compose.prod.yaml ps
    exit 1
  fi
fi

echo "Rollback unavailable or rollback health check failed."
podman compose -f compose.prod.yaml ps
exit 1
