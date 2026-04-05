#!/usr/bin/env bash
# Run this ON THE SERVER (e.g. 18.208.59.254) when you see 502 Bad Gateway.
# It checks why the API isn't responding and suggests fixes.

set -e
echo "=== 502 fix: checking API container ==="
echo ""

if ! command -v docker &>/dev/null; then
  echo "Docker not found. Install Docker or run this on the host where the stack runs."
  exit 1
fi

# Find API container (name may vary)
CONTAINER=$(docker ps -a --filter "name=truckerp-api" --format "{{.Names}}" | head -n1)
if [[ -z "$CONTAINER" ]]; then
  CONTAINER=$(docker ps -a --filter "name=api" --format "{{.Names}}" | head -n1)
fi

if [[ -z "$CONTAINER" ]]; then
  echo "No truckerp-api container found. List all: docker ps -a"
  exit 1
fi

echo "Container: $CONTAINER"
echo ""

if ! docker ps --filter "name=$CONTAINER" --format "{{.Status}}" | grep -q "Up"; then
  echo "Container is NOT running. Last 30 lines of logs:"
  echo "---"
  docker logs "$CONTAINER" 2>&1 | tail -30
  echo "---"
  echo ""
  echo "Fix: start the stack from repo root, e.g.:"
  echo "  docker compose -f docker-compose.yml up -d"
  echo ""
  echo "If the API exits because of missing secrets, either:"
  echo "  1) Configure AWS SSM, or"
  echo "  2) Add a .env file in the repo root with DATABASE_URL, JWT_SECRET, etc., and mount it or use the dev override."
  exit 1
fi

echo "Container is running. Last 20 lines of logs:"
echo "---"
docker logs "$CONTAINER" 2>&1 | tail -20
echo "---"
echo ""

# Quick health check from inside the network
if docker exec "$CONTAINER" curl -sf http://127.0.0.1:8000/api/v1/health 2>/dev/null; then
  echo ""
  echo "API responds inside the container. 502 might be nginx or network."
else
  echo "API did not respond on 127.0.0.1:8000 inside the container."
  echo "Process might have crashed after start. Check full logs: docker logs $CONTAINER"
fi
