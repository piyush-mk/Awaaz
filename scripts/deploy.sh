#!/usr/bin/env bash
# Redeploy Awaaz to a server: build the frontend here, sync code, restart the API.
# Never copies .env, databases or tests. Secrets live only in /opt/awaaz/backend/.env on the server.
#
#   AWAAZ_HOST=root@<server> AWAAZ_URL=https://<domain> scripts/deploy.sh
#
# Assumes the server layout described in RUNBOOK.md (systemd unit `awaaz`, venv at /opt/awaaz/venv, uv installed).
set -euo pipefail

: "${AWAAZ_HOST:?set AWAAZ_HOST, for example root@your-server}"
: "${AWAAZ_URL:?set AWAAZ_URL, for example https://your-domain}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> building frontend"
(cd "$ROOT/frontend" && npm run build >/dev/null)

echo "==> syncing backend and frontend to $AWAAZ_HOST"
rsync -az --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
  --exclude='*.sqlite' --exclude='*.legacy' --exclude='.cache' --exclude='.pytest_cache' --exclude='tests' \
  "$ROOT/backend/" "$AWAAZ_HOST:/opt/awaaz/backend/"
rsync -az --delete "$ROOT/frontend/dist/" "$AWAAZ_HOST:/opt/awaaz/frontend/dist/"

echo "==> installing deps and restarting"
ssh "$AWAAZ_HOST" 'export PATH=$HOME/.local/bin:$PATH
  uv pip install --python /opt/awaaz/venv/bin/python -q -r /opt/awaaz/backend/requirements.txt
  systemctl restart awaaz && sleep 4 && systemctl is-active awaaz'

echo "==> health"
curl -fsS "$AWAAZ_URL/health" && echo
