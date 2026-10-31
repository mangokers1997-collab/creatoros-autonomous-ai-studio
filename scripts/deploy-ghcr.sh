#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${CREATOROS_COMPOSE_FILE:-compose.ghcr.yaml}"
SERVICE="${CREATOROS_SERVICE:-creatoros}"
URL="${CREATOROS_HEALTH_URL:-http://127.0.0.1:8000/health}"
TIMEOUT="${CREATOROS_HEALTH_TIMEOUT:-120}"

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.docker.example to .env and configure secrets first." >&2
  exit 1
fi

echo "Pulling the latest CreatorOS image..."
docker compose -f "$COMPOSE_FILE" pull "$SERVICE"

echo "Starting/updating CreatorOS..."
docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"

echo "Waiting for health endpoint..."
elapsed=0
until docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" python -c "import urllib.request; urllib.request.urlopen('$URL', timeout=3)" >/dev/null 2>&1; do
  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    echo "Health check timed out. Recent logs:" >&2
    docker compose -f "$COMPOSE_FILE" logs --tail=80 "$SERVICE" >&2
    exit 1
  fi
  sleep 5
  elapsed=$((elapsed + 5))
done

echo "CreatorOS is healthy."
docker compose -f "$COMPOSE_FILE" ps
