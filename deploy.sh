#!/usr/bin/env bash
#
# GhostMeter deploy helper.
#
# Always applies docker-compose.prod.yml so published ports stay bound to
# BIND_IP (never the public network interface), and always runs database
# migrations before bringing the app up — the app only seeds data on startup,
# it does NOT create tables, so skipping migrations breaks a fresh deploy.
#
# Usage (from the repo root, on the deploy host):
#   ./deploy.sh
#
# Prerequisites:
#   - .env exists (cp .env.example .env, then set POSTGRES_PASSWORD + BIND_IP)
#   - Docker + Docker Compose v2.24.0+ installed
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env  then edit it." >&2
  exit 1
fi

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

# Enable the Cloudflare Tunnel sidecar only when a token is configured in
# .env (see docs/deployment.md section 5 — an Access policy must be set up
# in Cloudflare Zero Trust BEFORE exposing a Public Hostname).
if grep -q '^CLOUDFLARE_TUNNEL_TOKEN=..*' .env; then
  export COMPOSE_PROFILES=tunnel
  echo "==> Cloudflare Tunnel enabled (CLOUDFLARE_TUNNEL_TOKEN is set)"
fi

echo "==> Building backend and frontend images"
"${COMPOSE[@]}" build backend frontend

echo "==> Starting postgres"
"${COMPOSE[@]}" up -d postgres

echo "==> Waiting for postgres to become healthy"
until [ "$(docker inspect -f '{{.State.Health.Status}}' ghostmeter-postgres 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "==> Running database migrations (alembic upgrade head)"
"${COMPOSE[@]}" run --rm backend alembic upgrade head

echo "==> Starting all services"
"${COMPOSE[@]}" up -d

echo "==> Current status"
"${COMPOSE[@]}" ps
