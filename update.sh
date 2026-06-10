#!/usr/bin/env bash
#
# Update the deploy host to the latest origin/dev and redeploy.
#
# Run from the repo root on the deploy host:
#   ./update.sh
#
# It pulls the latest dev, sanity-checks .env, then hands off to deploy.sh
# (which applies the prod overlay, runs migrations, and brings services up).
# .env is git-ignored, so your POSTGRES_PASSWORD / BIND_IP are never touched.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Fetching latest origin/dev"
git fetch origin
git checkout dev
git pull --ff-only origin dev

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env  then set POSTGRES_PASSWORD + BIND_IP." >&2
  exit 1
fi

if ! grep -q '^BIND_IP=' .env; then
  echo "ERROR: BIND_IP is not set in .env." >&2
  echo "       Add this host's Tailscale IP, e.g.:  echo 'BIND_IP=100.x.x.x' >> .env" >&2
  exit 1
fi

echo "==> Redeploying"
exec ./deploy.sh
