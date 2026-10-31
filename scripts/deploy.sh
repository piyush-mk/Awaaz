#!/usr/bin/env bash
# Redeploy Awaaz to a server: build the frontend here, sync code, restart the API.
# Never copies .env, databases or tests. Secrets live only in /opt/awaaz/backend/.env on the server.
#
#   AWAAZ_HOST=root@<server> AWAAZ_URL=https://<domain> scripts/deploy.sh
#
# Non-root login with an isolated service user (recommended when sharing a server):
#   AWAAZ_HOST=deploy@<server> AWAAZ_RUN_AS=awaaz AWAAZ_URL=https://<domain> scripts/deploy.sh
# Files are then written as that user via sudo, and the service is restarted with sudo.
#
# Assumes the server layout described in RUNBOOK.md (systemd unit `awaaz`, venv at /opt/awaaz/venv, uv installed).
set -euo pipefail

: "${AWAAZ_HOST:?set AWAAZ_HOST, for example root@your-server}"
: "${AWAAZ_URL:?set AWAAZ_URL, for example https://your-domain}"
RUN_AS="${AWAAZ_RUN_AS:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -n "$RUN_AS" ]; then
  RSYNC_PATH="sudo -u $RUN_AS rsync"
  AS="sudo -u $RUN_AS -H"
  SUDO="sudo"
else
  RSYNC_PATH="rsync"
  AS=""
  SUDO=""
fi

echo "==> building frontend"
(cd "$ROOT/frontend" && npm run build >/dev/null)

echo "==> syncing backend and frontend to $AWAAZ_HOST"
rsync -az --delete --rsync-path="$RSYNC_PATH" \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
  --exclude='*.sqlite' --exclude='*.legacy' --exclude='.cache' --exclude='.pytest_cache' --exclude='tests' \
  "$ROOT/backend/" "$AWAAZ_HOST:/opt/awaaz/backend/"
rsync -az --delete --rsync-path="$RSYNC_PATH" "$ROOT/frontend/dist/" "$AWAAZ_HOST:/opt/awaaz/frontend/dist/"

echo "==> installing deps and restarting"
ssh "$AWAAZ_HOST" "cd /opt/awaaz && $AS env HOME=/opt/awaaz PATH=/opt/awaaz/.local/bin:\$HOME/.local/bin:\$PATH \
    uv pip install --python /opt/awaaz/venv/bin/python -q -r /opt/awaaz/backend/requirements.txt \
  && $SUDO systemctl restart awaaz && sleep 5 && systemctl is-active awaaz"

echo "==> health"
curl -fsS "$AWAAZ_URL/health" && echo
