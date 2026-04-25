#!/usr/bin/env bash
# Phase 4 — Amplifier server deploy on Hostinger KVM 1 VPS
# Run on the VPS as ROOT, after Phase 2 (system setup) and Phase 3 (Tailscale auth) are done.
# Usage: paste this entire script into the hPanel browser terminal as root.
#
# What this does (autonomously):
#   1. Generates SSH deploy key for GitHub access
#   2. PAUSES for you to add the deploy key to the GitHub repo
#   3. Clones the Amplifier repo to /home/amplifier/app
#   4. Creates Python venv + installs deps
#   5. Generates fresh secrets (JWT_SECRET_KEY, ADMIN_PASSWORD, ENCRYPTION_KEY) into /home/amplifier/app/server/.env
#   6. Prompts for the Supabase DATABASE_URL + GEMINI_API_KEY (3 interactive inputs)
#   7. Installs and configures Caddy with auto-TLS for api.marketdavinci.com
#   8. Writes amplifier-web.service systemd unit
#   9. Starts the service and runs smoke tests

set -e
SUBDOMAIN="api.marketdavinci.com"
REPO_GIT="git@github.com:Samaara-Das/Amplifier.git"
APP_USER="amplifier"
APP_DIR="/home/${APP_USER}/app"

echo "========================================================"
echo "Phase 4: Amplifier deploy — $(date)"
echo "Target subdomain: $SUBDOMAIN"
echo "========================================================"

# 1. Create amplifier system user (no shell login, dedicated for the service)
echo ""
echo ">>> [1/9] Creating amplifier system user..."
if ! id "$APP_USER" &>/dev/null; then
  adduser --system --group --home "/home/${APP_USER}" --shell /bin/bash "$APP_USER"
fi
mkdir -p "/home/${APP_USER}/.ssh"
chmod 700 "/home/${APP_USER}/.ssh"
chown -R "${APP_USER}:${APP_USER}" "/home/${APP_USER}"

# 2. Generate SSH deploy key for GitHub
echo ""
echo ">>> [2/9] Generating SSH deploy key for GitHub..."
DEPLOY_KEY="/home/${APP_USER}/.ssh/github_deploy"
if [ ! -f "$DEPLOY_KEY" ]; then
  sudo -u "$APP_USER" ssh-keygen -t ed25519 -N "" -f "$DEPLOY_KEY" -C "amplifier-vps-deploy"
fi
sudo -u "$APP_USER" bash -c "cat > /home/${APP_USER}/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
chmod 600 /home/${APP_USER}/.ssh/config"

echo ""
echo "==================== ACTION REQUIRED ===================="
echo ""
echo "Add this PUBLIC key as a deploy key on the GitHub repo:"
echo ""
echo "  https://github.com/Samaara-Das/Amplifier/settings/keys/new"
echo ""
echo "Title: amplifier-vps-deploy"
echo "Allow write access: NO (read-only)"
echo ""
echo "----- COPY EVERYTHING BETWEEN THE LINES -----"
cat "${DEPLOY_KEY}.pub"
echo "----- END KEY -----"
echo ""
echo "Press ENTER when you've added the key to GitHub."
read -r _

# 3. Clone the repo
echo ""
echo ">>> [3/9] Cloning Amplifier repo..."
if [ -d "$APP_DIR" ]; then
  echo "Repo already exists, pulling latest..."
  sudo -u "$APP_USER" git -C "$APP_DIR" pull
else
  sudo -u "$APP_USER" git clone "$REPO_GIT" "$APP_DIR"
fi

# 4. Python venv + deps
echo ""
echo ">>> [4/9] Setting up Python venv + installing deps..."
sudo -u "$APP_USER" python3 -m venv "${APP_DIR}/server/.venv"
sudo -u "$APP_USER" "${APP_DIR}/server/.venv/bin/pip" install --upgrade pip wheel -q
sudo -u "$APP_USER" "${APP_DIR}/server/.venv/bin/pip" install -r "${APP_DIR}/server/requirements.txt" -q

# Quick smoke test of imports
echo ""
echo "Verifying imports..."
sudo -u "$APP_USER" bash -c "cd ${APP_DIR}/server && .venv/bin/python -c 'from app.main import app; print(f\"Import OK: {app.title}\")'"

# 5. Generate fresh secrets + collect runtime secrets
echo ""
echo ">>> [5/9] Generating fresh secrets..."
JWT_SECRET=$(openssl rand -base64 48 | tr -d "=+/" | cut -c1-48)
ADMIN_PW=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-24)
ENC_KEY=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

echo ""
echo "==================== ACTION REQUIRED ===================="
echo "Paste the following secrets when prompted (from your password manager / Supabase dashboard):"
echo ""
read -r -p "Supabase DATABASE_URL (postgresql+asyncpg://...): " DB_URL
read -r -p "GEMINI_API_KEY: " GEMINI_KEY
read -r -p "SUPABASE_URL (e.g. https://xyz.supabase.co): " SB_URL
read -r -p "SUPABASE_SERVICE_KEY (eyJ...): " SB_KEY

# 6. Write .env file (mode 600, root:amplifier)
echo ""
echo ">>> [6/9] Writing /home/${APP_USER}/app/server/.env..."
ENV_FILE="${APP_DIR}/server/.env"
cat > "$ENV_FILE" << EOF
# Amplifier server config — generated $(date)
# DO NOT COMMIT TO GIT (it is in .gitignore)

# Database — Supabase transaction pooler
DATABASE_URL=${DB_URL}

# Redis — local on this VPS
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
ADMIN_PASSWORD=${ADMIN_PW}
ENCRYPTION_KEY=${ENC_KEY}

# AI
GEMINI_API_KEY=${GEMINI_KEY}

# Supabase Storage (campaign uploads)
SUPABASE_URL=${SB_URL}
SUPABASE_SERVICE_KEY=${SB_KEY}

# Stripe — leave blank until live payments enabled
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Platform
PLATFORM_CUT_PERCENT=20
MIN_PAYOUT_THRESHOLD=10.00

# Server
HOST=127.0.0.1
PORT=8000
DEBUG=false
EOF
chmod 600 "$ENV_FILE"
chown "root:${APP_USER}" "$ENV_FILE"

# 7. Install Redis (local — for ARQ worker when implemented later)
echo ""
echo ">>> [7/9] Installing Redis..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server
sed -i 's/^# *supervised .*/supervised systemd/' /etc/redis/redis.conf
systemctl enable --now redis-server
redis-cli ping || (echo "Redis ping failed!" && exit 1)

# 8. systemd unit for amplifier-web
echo ""
echo ">>> [8/9] Writing systemd unit + Caddyfile..."
cat > /etc/systemd/system/amplifier-web.service << EOF
[Unit]
Description=Amplifier FastAPI server
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/server
EnvironmentFile=${APP_DIR}/server/.env
ExecStart=${APP_DIR}/server/.venv/bin/uvicorn app.main:app \\
  --host 127.0.0.1 --port 8000 \\
  --workers 1 \\
  --proxy-headers --forwarded-allow-ips=127.0.0.1 \\
  --access-log
Restart=on-failure
RestartSec=5
MemoryMax=2500M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${APP_DIR}/server
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

# Install Caddy if not present
if ! command -v caddy &>/dev/null; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq
  apt-get install -y -qq caddy
fi

# Caddyfile — reverse proxy with auto-TLS
cat > /etc/caddy/Caddyfile << EOF
${SUBDOMAIN} {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-For {remote_host}
    }
    log {
        output stdout
        format console
    }
}
EOF

systemctl daemon-reload
systemctl enable --now amplifier-web
systemctl reload caddy

sleep 3

# 9. Smoke tests
echo ""
echo ">>> [9/9] Smoke tests..."
echo ""
echo "--- amplifier-web service status ---"
systemctl status amplifier-web --no-pager | head -15

echo ""
echo "--- localhost health check ---"
curl -s http://127.0.0.1:8000/health || echo "LOCAL HEALTH FAILED"

echo ""
echo "--- public health check (https://${SUBDOMAIN}/health) ---"
curl -s "https://${SUBDOMAIN}/health" || echo "PUBLIC HEALTH FAILED — DNS may not be propagated yet"

echo ""
echo "========================================================"
echo "Phase 4 COMPLETE: $(date)"
echo "========================================================"
echo ""
echo "Generated secrets (SAVE THESE TO YOUR PASSWORD MANAGER NOW):"
echo "  Admin login URL:  https://${SUBDOMAIN}/admin/login"
echo "  ADMIN_PASSWORD:   ${ADMIN_PW}"
echo ""
echo "If localhost health failed: journalctl -u amplifier-web -n 50"
echo "If public health failed:    DNS propagation: dig ${SUBDOMAIN}; or wait + retry"
echo ""
echo "NEXT (back on laptop):"
echo "  - Update config/.env CAMPAIGN_SERVER_URL=https://${SUBDOMAIN}"
echo "  - Update scripts/utils/server_client.py:22 fallback to https://${SUBDOMAIN}"
echo "  - Commit + push"
echo ""
