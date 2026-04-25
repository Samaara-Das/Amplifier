# Migration Plan — Amplifier Server Off Vercel

> **STATUS: DECISION LOCKED 2026-04-25.** Execution runbook below. Hard deadline: `/health` returning 200 by **end of week 2026-05-02**.

**Trigger:** Vercel Hobby (`araamas-projects`) billed ~$47 in one cycle for the Amplifier FastAPI server. Root causes: 3.9M function invocations (721% over free tier), 904% Fluid Active CPU, 350 build minutes. Vercel is serverless — every HTTP request spawns a function. Amplifier makes *lots* of requests (campaign polling from every user app instance every 10 min + metric scraping + background agent health checks). Serverless pricing scales linearly with traffic and has no hard cap; one noisy user could bankrupt you.

**Current state:** Project deleted from Vercel, billing disputed, server offline. Clients now default to `http://localhost:8000` after `759e3c2` (`server_client.py:22` + `config/.env:7`); will be updated to the new VPS subdomain at cutover.

---

## 0. Decision summary (2026-04-25)

After consultation with Claude.ai web (full transcript and brief at `docs/CLAUDE-DESKTOP-TASK-41-BRIEF.md`), the following is locked:

**PICK:** Deploy Amplifier on Nili + Daniel's existing Hostinger **KVM 1 VPS** (Mumbai, Ubuntu 24.04, 1 vCPU / 4 GB / 50 GB). Single-tenant after OpenClaw removal. No upgrade. No new VPS.

**Rejected options (do not revisit unless stated condition changes):**

| Option | Why rejected |
|---|---|
| **A — New free Vercel account** | Vercel Hobby ToS prohibits commercial use; auto-detection will suspend. Same per-invocation billing trap (1M free invocations/mo consumed in ~7-8 days at expected user volume). Same architectural failure mode. **Permanently off the table.** |
| **C — Nili Business Web Hosting (poolsifi)** | Shared LiteSpeed in USA/Arizona, no SSH on plan tier, can't run uvicorn / Redis / systemd. Sandboxed for PHP/CMS via hPanel. Hosts 7 sites (poolsifi + subdomains, marketdavinci, silverpips, thebrutalcapitalist) but is a separate physical server from the VPS — killing things on the VPS does NOT affect any website. |
| **D — KVM 8 on `kingsdxb2025@gmail.com`** | Bought specifically for Stock Buddy + TTE under employer (Rahul) authority. Employer has full account access. Privacy / IP risk: do not want employer to see Amplifier source, env vars, Stripe keys. Father confirmed off-limits. **Revisit only if employer-access situation changes.** |
| **Upgrade Nili KVM 1 → KVM 2** | Premature — KVM 2 is sized for 50k MAU (100x current scale). Pre-buying capacity = comfort spending. In-place upgrade is one-click in hPanel (~10 min reboot) when actually needed. Trigger conditions in §10. |
| **New small VPS under own account** | Solves imaginary isolation problem. Nili KVM is already single-tenant for Amplifier (TTE / Stock Buddy not landing there). $60-96/yr duplicate of free capacity already available. |

**Workload sanity check on KVM 1 (why it's sufficient):**
- FastAPI + asyncpg (1 worker): ~250-350 MB
- ARQ worker (idle, polling Redis): ~80-120 MB
- Local Redis: ~20-60 MB
- Caddy: ~30-50 MB
- Ubuntu 24.04 baseline + journald + sshd: ~400-600 MB
- **Total: ~0.8-1.2 GB on 4 GB box → 2.8-3.2 GB headroom**
- Workload is I/O-bound (waiting on Supabase, Gemini, Stripe). 1 vCPU async event loop handles hundreds of concurrent waiting requests easily.
- 500 active users × 1 poll / 10 min = 50 polls/min → trivial.

**Three execution-time tweaks vs. the original plan below** (all reflect single-tenant, no neighbor):

1. §4.5 systemd web unit: drop `CPUQuota=80%` (no neighbor to protect), raise `MemoryMax=` to `2500M`, use `--workers 1` (one worker fits I/O-bound load shape, saves ~150 MB RAM).
2. §4.2 baseline: kill OpenClaw cleanly (`systemctl stop openclaw-gateway && systemctl disable openclaw-gateway`) BEFORE installing anything. Verify `htop` <10% CPU and `free -h` ≥3 GB available before proceeding. **Do NOT delete OpenClaw binaries** — preserve on disk for Phase 7.
3. §4.6 ARQ worker: before writing the systemd unit, run `grep -rn "WorkerSettings\|class Worker" server/app/` to confirm entrypoint exists. If not, defer worker as a follow-up task and ship the web server first.

**Pre-cleanup recon is mandatory.** The Nili VPS has unidentified processes besides OpenClaw. Do NOT stop services blindly. Full recon-first procedure is documented in `docs/VPS-RECON-AND-CLEANUP.md`.

---

## 1. Recommendation: Hostinger KVM VPS (shared box, systemd + Caddy)

**Pick one:** run the FastAPI app as a systemd service behind Caddy (reverse proxy with auto-TLS) on the Hostinger KVM VPS already owned by Nili and Daniel. Run Redis locally on the same box. Keep Supabase PostgreSQL as-is.

**VPS context (confirmed 2026-04-19):**
- Purchased recently by **Nili** (colleague) and **Daniel** (Sammy's father).
- Originally bought to host **TTE** (`tradingview_to_everywhere` — Python + Selenium TradingView signal bridge) and **Stock Buddy** (Next.js trading app currently on Vercel Pro, may also deploy here).
- Amplifier is approved to co-host on the same VPS.
- Need to confirm plan tier (KVM 1, 2, 4, or 8) with Nili before §4 — it dictates how tightly we pack uvicorn workers and Redis.

**Co-tenancy implications:**
- TTE runs persistent Selenium browser instances — those are RAM-hungry (~200-400 MB per Chrome). Don't grab all available RAM for Amplifier.
- Rough budget on a KVM 2 (2 vCPU / 8 GB): TTE 2-3 GB, Stock Buddy (if deployed here) 1-2 GB, Amplifier 1 GB, Redis 200 MB, OS 500 MB. Comfortable, with headroom for OpenClaw (PRD Phase 7) later.
- If it's KVM 1 (1 vCPU / 4 GB), drop uvicorn to 1 worker and monitor RAM.

**Coordination needed before §4:**
- Get SSH access from Nili or Daniel (key-based auth preferred).
- If Caddy is already installed for TTE/Stock Buddy, extend its Caddyfile with the Amplifier block instead of re-installing.
- If a Redis is already running for TTE/Stock Buddy, share it (with a dedicated DB number, e.g. `redis://localhost:6379/2`) rather than launching a second.
- Agree on systemd unit naming convention (`amplifier-web.service`, `amplifier-worker.service`) so services don't collide with TTE's.
- Verify the VPS's outbound firewall allows Stripe, Supabase, and Google Generative AI endpoints.
- Pick a subdomain — `api.amplifier.app` or a sub of an existing owned domain.

### Why VPS, not Railway / Render / Fly

| Criterion | Hostinger VPS | Railway | Render | Fly.io |
|-----------|---------------|---------|--------|--------|
| Billing model | **Flat monthly** (already paid) | Usage-based (CPU+RAM+egress) | Flat service + flat Redis | Usage-based (CPU+RAM) |
| Billing surprise risk | **Zero** (hard ceiling = your plan) | Moderate — scales with traffic | Low — flat fees | Moderate — scales with traffic |
| Persistent Python process | ✅ native | ✅ | ✅ | ✅ |
| Redis | Self-host (free) | $5–10/mo add-on | $10/mo managed | Self-host or Upstash |
| Sysadmin burden | **Highest** (you run OS + updates) | Lowest | Low | Medium |
| Room for OpenClaw | **Yes — co-host** | Extra service fee | Extra service fee | Extra app fee |
| Outbound IP control | **Fixed IP** (useful for Stripe webhook allowlists, scraping) | Pooled, changes | Pooled, changes | Pooled |
| Scales to users > ~500 | Manual (upgrade plan) | Auto | Manual | Auto |

**Why VPS wins here:**
1. **Predictable cost.** The thing that burned you was unpredictable per-request billing. A VPS has a flat ceiling. You cannot get a surprise $47 invoice from it.
2. **Sunk cost is already paid.** Nili and Daniel already bought this KVM plan for TTE and Stock Buddy. Every dollar spent on Railway/Render is duplicative spend on top of a resource you already own.
3. **Consolidation.** TTE and (eventually) Stock Buddy already live here. Phase 7 OpenClaw agents will need a VPS anyway. One box, one SSH key, one systemd unit set to manage — not four different dashboards.
4. **Fixed outbound IP.** When you later do Stripe webhook verification or scraper reliability work, having a stable IP matters.
5. **The server is small.** FastAPI + ARQ worker comfortably fits in 1 vCPU / 2 GB RAM. Amplifier isn't CPU-bound — requests are I/O-bound (DB + external APIs). Supabase does the heavy DB lifting. You don't need auto-scaling yet.

**When to revisit this choice:** >500 active user installs OR >100 concurrent campaign polls. At that point, vertical-scale the VPS plan first, then migrate to Railway/Fly for autoscaling.

## 2. Fallback if VPS unavailable (unlikely — VPS is confirmed)

Kept for reference only. The Hostinger KVM is confirmed available, so skip to §3 unless resource constraints force a change.

- **Render Web Service** — $7/mo flat (Starter instance, always-on). Deploys from GitHub. Native Python support, env vars, zero cold starts on paid plans.
- **Render Key Value (Redis)** — $10/mo flat. Managed. No self-hosting.
- **Total: $17/mo flat**, hard-capped, no per-request billing. Deploy command is `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Everything else in this plan (env vars, client switchover, Vercel cleanup) applies identically. Only §4 (server setup) changes — Render handles most of it via `render.yaml` or dashboard.

---

## 3. What the server needs from its host

Scraped from `server/app/main.py`, `server/requirements.txt`, `server/app/core/database.py`, `server/app/core/config.py`, `docs/deployment-guide.md`:

| Requirement | Detail |
|-------------|--------|
| Runtime | Python 3.11+ (project uses `google-genai`, `asyncpg`, modern FastAPI) |
| Process model | **Persistent ASGI** via `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Not serverless. FastAPI `lifespan` handler runs `init_tables()` on startup |
| Memory | ~300–500 MB working set (FastAPI + asyncpg + Gemini SDK + supabase SDK) |
| Disk | <100 MB for code + deps. No persistent app data on disk — DB is external |
| Outbound network | HTTPS to: Supabase (PostgreSQL:6543 + Storage), Stripe API, Google Generative AI, arbitrary URLs (campaign wizard scrapes product pages) |
| Inbound network | HTTPS on 443. Behind reverse proxy with auto-TLS. No websockets currently |
| Redis | Required by `arq>=0.26.1` (ARQ worker — billing every 6h, trust checks 2×/day per `server/requirements.txt` + `docs/deployment-guide.md`). Localhost Redis is fine |
| Database | External: Supabase PostgreSQL via transaction pooler (`aws-1-us-east-1.pooler.supabase.com:6543`). Already production |
| Env vars | See §6. `DATABASE_URL`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `GEMINI_API_KEY`, `ENCRYPTION_KEY` required. `REDIS_URL`, `STRIPE_*`, `SUPABASE_*` optional-but-recommended |
| TLS | Must serve HTTPS — user apps assume it. Caddy auto-provisions Let's Encrypt certs |
| Two processes | Eventually: (1) uvicorn web server, (2) `arq` worker for background jobs. Both as separate systemd units |

---

## 4. Step-by-step migration — Hostinger VPS

Assumes Ubuntu 22.04/24.04 LTS. Adjust package names if using AlmaLinux/Debian.

### 4.1 Prep (on your laptop)

1. **Pick a subdomain.** E.g. `api.amplifier.app` or `server.yourdomain.com`. The deployment URL needs to be stable; clients will point to it indefinitely.
2. **Point DNS.** Add an `A` record: `api.yourdomain.com → <VPS-public-IP>`. TTL 300s for the initial cut. Wait for propagation (check with `dig api.yourdomain.com`).
3. **Generate new secrets.** Don't reuse the Vercel ones — a dispute process may have exposed them to support.
   ```bash
   # On laptop
   python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(32))"   # ENCRYPTION_KEY
   python -c "import secrets; print(secrets.token_urlsafe(24))"   # ADMIN_PASSWORD
   ```
   Save these in your password manager. Confirm they DO NOT contain trailing newlines.

### 4.2 VPS baseline

**Before touching anything:** ask Nili/Daniel what's already installed. TTE likely has Python + Chrome + some reverse proxy already. Don't reinstall duplicates.

SSH into the VPS (key-based auth from Nili/Daniel) and check existing state:

```bash
# Recon first — do NOT assume a blank box
whoami
cat /etc/os-release
systemctl list-units --type=service --state=running | grep -Ei 'caddy|nginx|redis|python|tte'
ss -tlnp                                         # who's listening on what port
ls /home                                         # what service users exist
sudo ufw status                                  # firewall state
which python3.11 python3.12 caddy redis-server   # what's already installed
```

Then — only install what's missing:

```bash
# System update — coordinate with Nili before running, could interrupt TTE
sudo apt update && sudo apt upgrade -y

# Create a dedicated service user for Amplifier (separate from TTE/Stock Buddy)
sudo adduser --disabled-password --gecos '' amplifier

# Firewall — if UFW isn't already configured for TTE/Stock Buddy, set it up.
# If it IS configured, DON'T `ufw --force enable` blind — you could lock out TTE.
sudo ufw status
# If inactive and safe to enable:
#   sudo apt install -y ufw
#   sudo ufw default deny incoming
#   sudo ufw default allow outgoing
#   sudo ufw allow OpenSSH
#   sudo ufw allow 80/tcp
#   sudo ufw allow 443/tcp
#   sudo ufw --force enable

# Python — only install if not present
sudo apt install -y python3.11 python3.11-venv python3-pip git curl

# Redis — if TTE/Stock Buddy already run Redis, SHARE IT:
#   - Use a different DB number: REDIS_URL=redis://localhost:6379/2
#   - Confirm DB 0/1 aren't used by checking `redis-cli INFO keyspace`
# If Redis is not installed:
sudo apt install -y redis-server
sudo sed -i 's/^# *supervised .*/supervised systemd/' /etc/redis/redis.conf
sudo systemctl enable --now redis-server
# Verify: redis-cli ping  → PONG
```

### 4.3 Deploy the code

```bash
# As amplifier user
su - amplifier

# Clone (use HTTPS + read-only deploy key, or SSH key)
cd ~
git clone https://github.com/<your-handle>/Auto-Posting-System.git app
cd app/server

# Python venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install gunicorn   # optional — can run bare uvicorn, but gunicorn supervises better

# Smoke test (no env vars yet — expects 500s, but proves the import chain works)
python -c "from app.main import app; print(app.title)"
# Expected: "Amplifier API"
```

### 4.4 Environment file

Create `/home/amplifier/app/server/.env` (mode 600, owned by `amplifier`):

```bash
chmod 600 .env
```

Contents (paste values from your password manager):

```ini
# Database — Supabase transaction pooler (port 6543), asyncpg format
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-1-us-east-1.pooler.supabase.com:6543/postgres

# Redis — local on this VPS
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET_KEY=<48-char-secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
ADMIN_PASSWORD=<admin-password>
ENCRYPTION_KEY=<32-char-key>

# AI
GEMINI_API_KEY=<your-key>

# Stripe (live — only when ready)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Supabase Storage (campaign uploads)
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-key>

# Platform
PLATFORM_CUT_PERCENT=20
MIN_PAYOUT_THRESHOLD=10.00

# Server
HOST=127.0.0.1       # bind to loopback — Caddy proxies to us
PORT=8000
DEBUG=false          # silence SQLAlchemy echo in prod
```

**Critical:** bind `HOST=127.0.0.1`, not `0.0.0.0`. UFW already blocks 8000 externally, but belt-and-suspenders: uvicorn should only listen on localhost and Caddy should own 443.

### 4.5 systemd — web service

Create `/etc/systemd/system/amplifier-web.service` (as root). Note the `CPUQuota=` and `MemoryMax=` limits — they prevent Amplifier from starving TTE if traffic spikes:

```ini
[Unit]
Description=Amplifier FastAPI server
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=amplifier
Group=amplifier
WorkingDirectory=/home/amplifier/app/server
EnvironmentFile=/home/amplifier/app/server/.env
ExecStart=/home/amplifier/app/server/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 \
  --workers 2 \
  --proxy-headers --forwarded-allow-ips=127.0.0.1 \
  --access-log
Restart=on-failure
RestartSec=5
# Co-tenancy limits (tune to VPS plan — these are KVM 2 defaults)
CPUQuota=80%
MemoryMax=1200M
# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/amplifier/app/server
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
```

**Workers=2 rationale:** the app is I/O-bound (DB + external APIs). 2 uvicorn workers on 1 vCPU handles early-stage load fine. Bump to 4 when you have >100 concurrent users. Don't over-provision — each worker duplicates memory.

Enable + start:
```bash
systemctl daemon-reload
systemctl enable --now amplifier-web
systemctl status amplifier-web        # should be "active (running)"
journalctl -u amplifier-web -f        # tail logs during smoke test
curl http://127.0.0.1:8000/health     # → {"status":"ok"}
```

### 4.6 systemd — ARQ worker

Background jobs (billing every 6h, trust checks) run via ARQ. The codebase imports `arq` but the worker entrypoint isn't currently wired into deployment (per `docs/deployment-guide.md` it's documented but not auto-started on Vercel either). Verify the ARQ `WorkerSettings` class location before enabling this unit — it should be in `server/app/worker.py` or similar. If it's not yet implemented, skip this unit and file a follow-up task.

If it exists: create `/etc/systemd/system/amplifier-worker.service`:

```ini
[Unit]
Description=Amplifier ARQ worker
After=network.target redis-server.service amplifier-web.service
Wants=redis-server.service

[Service]
Type=simple
User=amplifier
Group=amplifier
WorkingDirectory=/home/amplifier/app/server
EnvironmentFile=/home/amplifier/app/server/.env
ExecStart=/home/amplifier/app/server/.venv/bin/arq app.worker.WorkerSettings
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 4.7 Caddy — reverse proxy + auto-TLS

Caddy beats nginx here: single binary, auto-renews Let's Encrypt certs, config is 5 lines, no Certbot cron.

**Check first:** if TTE or Stock Buddy already run Caddy/nginx on this box, DON'T install a second reverse proxy. Extend the existing one instead — add your `api.yourdomain.com` block to the existing Caddyfile or nginx sites-available. Ask Nili.

If no reverse proxy exists yet:

```bash
# As root
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo tee /usr/share/keyrings/caddy-stable-archive-keyring.asc
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Create or extend `/etc/caddy/Caddyfile`:

```
api.yourdomain.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-For {remote_host}
    }
    # basic rate limiting on auth endpoints — app also has slowapi but belt-and-braces
    @auth path /api/auth/*
    # (optional) log to journald
    log {
        output stdout
        format console
    }
}
```

```bash
systemctl reload caddy
journalctl -u caddy -f   # watch cert provisioning (~5 seconds)
curl https://api.yourdomain.com/health   # → {"status":"ok"}
```

### 4.8 Supabase allowlist

Supabase PostgreSQL has no IP allowlist by default for the pooler, but double-check:
- Supabase Dashboard → Project Settings → Database → Network Restrictions.
- If IP restrictions were added during the Vercel era, add the VPS public IP.
- Supabase Storage — no allowlist needed; auth is via service key.

### 4.9 Stripe (when enabling live payments)

- Update Stripe webhook endpoint from the deleted Vercel URL to `https://api.yourdomain.com/api/webhooks/stripe` (verify the actual webhook path in `server/app/routers/` — there's no current webhook route, so implement first or skip).
- Rotate `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` if they were ever in the Vercel dashboard.

---

## 5. Switch the clients

Two places point at Vercel. Change both:

1. **`config/.env` line 7:**
   ```diff
   - CAMPAIGN_SERVER_URL=https://server-five-omega-23.vercel.app
   + CAMPAIGN_SERVER_URL=https://api.yourdomain.com
   ```
2. **`scripts/utils/server_client.py:22`** (hardcoded fallback default):
   ```diff
   - return os.getenv("CAMPAIGN_SERVER_URL", "https://server-five-omega-23.vercel.app")
   + return os.getenv("CAMPAIGN_SERVER_URL", "https://api.yourdomain.com")
   ```

Both changes are durable — commit and push. Any user app already running locally picks up `config/.env` on next restart. Agent instances running on your machine: restart `campaign_dashboard.py` + `background_agent.py`.

**Do not** leave the old Vercel URL as a fallback — it's a dead domain now, and silent 5xx retries will burn CPU on user machines.

---

## 6. Environment variable map

Required for server to boot cleanly:

| Variable | Source | Change on migration? |
|----------|--------|----------------------|
| `DATABASE_URL` | Supabase transaction pooler string | No — same Supabase project |
| `JWT_SECRET_KEY` | Generate new (see §4.1) | **Yes — rotate** |
| `ADMIN_PASSWORD` | Generate new | **Yes — rotate** |
| `ENCRYPTION_KEY` | Generate new | **Yes — rotate, but see ⚠ below** |
| `GEMINI_API_KEY` | Your Google AI Studio key | No |
| `REDIS_URL` | `redis://localhost:6379/0` (local on VPS) | **Yes — was external before** |
| `SUPABASE_URL` | Supabase dashboard | No |
| `SUPABASE_SERVICE_KEY` | Supabase dashboard | No |
| `STRIPE_SECRET_KEY` | Stripe dashboard (live when ready) | Conditional — rotate if exposed |
| `HOST` | `127.0.0.1` | **Yes — was `0.0.0.0` on Vercel** |
| `DEBUG` | `false` in prod | **Yes — was `true`** |

⚠ **`ENCRYPTION_KEY` rotation caveat:** `server/app/utils/crypto.py` uses AES-256-GCM for server-side data encryption. If existing production data in Supabase was encrypted with the old key, rotating mid-migration will make that data unreadable. Before rotating:
- Audit what columns use encryption (grep for `crypto.encrypt` / `crypto.decrypt` in `server/`).
- If any encrypted data exists, either keep the old key or write a one-time re-encryption migration.
- If encryption was only theoretically enabled but never used in practice (likely — Vercel deploy was recent), rotation is safe.

Confirm this before cutting over.

---

## 7. Vercel-specific bits to remove / refactor

Grep confirmed these Vercel-touchpoints. None break on removal — FastAPI is framework-neutral.

| Path | Action | Why |
|------|--------|-----|
| `/vercel.json` (repo root) | **Delete** | Stray Vercel config pointing at nonexistent `api/index.py` at root. Dead |
| `/server/vercel.json` | **Delete** | Serverless build config — no longer needed |
| `/server/api/index.py` | **Delete** | Vercel serverless entry. On a VPS, uvicorn imports `app.main:app` directly |
| `/server/.vercel/` (directory) | **Delete** | Local CLI state (`project.json`, README) — already stale after project deletion |
| `server/app/main.py:22-26` (`if not os.environ.get("VERCEL")`) | **Remove the guard** | Always run `init_tables()` on startup now. VPS has no ephemeral filesystem issue |
| `server/app/core/database.py:13-15` (`/tmp/amplifier.db` fallback) | **Remove** | Vercel-only hack; VPS lets SQLite write anywhere. (Server will use PostgreSQL in prod regardless — this is just dead code) |
| `server/.env.example` line 2-5 (Vercel comments) | **Reword** | Remove "set on Vercel" language; mention VPS deploy |
| `docs/deployment-guide.md` | **Rewrite** | Entire "Production Deployment (Vercel + Supabase)" section stale. Rewrite against VPS setup — this migration doc can be the source |
| `CLAUDE.md` → "Deployed Server" + "Vercel environment variables" + "Vercel deploy command" + "vercel.json" sections | **Rewrite** | Replace with VPS deploy details, env file path, systemd commands |
| `README.md` | **Update** | Any mention of Vercel URL or deploy command |
| `config/.env:7` | **Change URL** (see §5) | Points user app to dead Vercel domain |
| `scripts/utils/server_client.py:22` | **Change URL** (see §5) | Hardcoded Vercel fallback |
| `docs/env-vars.md`, `docs/technical-architecture.md`, `docs/config-reference.md`, etc. | **Search & replace** `server-five-omega-23.vercel.app` → new domain | 62 files contain the URL per grep |
| `.claude/commands/commit-push.md` | **Check** for `vercel deploy` invocations | If it auto-deploys, rewire to `ssh vps 'cd ~/app && git pull && sudo systemctl restart amplifier-web'` or similar |

**Grep to execute before migration day:**
```bash
grep -rln "server-five-omega-23.vercel.app\|araamas\|@vercel/python" .
```

Expect ~62 hits. Batch-replace in a single commit.

---

## 8. Cutover sequence (migration day, estimated 2–3 hours)

Do this in order:

1. **Pre-flight** (day before)
   - DNS record for `api.yourdomain.com` in place, propagated.
   - VPS provisioned, SSH key tested.
   - Supabase IP allowlist updated if restricted.
   - New secrets generated + saved.
   - ARQ worker entrypoint audited (§4.6).
   - `ENCRYPTION_KEY` rotation decision made (§6).

2. **Stop user-side activity** (~5 min)
   - Kill any running `background_agent.py` + `campaign_dashboard.py` on your dev machine.
   - Post a brief in any user-facing channel if users exist.

3. **Deploy to VPS** (~60 min) — steps §4.2 → §4.7.

4. **Smoke test the new server** (~20 min)
   - `curl https://api.yourdomain.com/health` → `{"status":"ok"}`.
   - `curl https://api.yourdomain.com/api/version` → version JSON.
   - Browse `https://api.yourdomain.com/docs` — Swagger loads.
   - Log into `/admin/login` with new password.
   - Log into `/company/login` — company accounts still exist (DB unchanged).
   - Create a test campaign end-to-end.
   - Check `journalctl -u amplifier-web -n 200` for errors.

5. **Switch clients** (~5 min) — §5. Commit + push.

6. **Verify user flow** (~15 min)
   - Start user app, confirm campaigns poll, draft generation works, post cycle runs.

7. **Document + snapshot**
   - Take a Supabase DB backup.
   - `vercel logout` and remove the stale CLI config from your dev machine.
   - Update this doc's "Status" section (below).

8. **Monitor** (24h)
   - `journalctl -u amplifier-web --since "1 hour ago"` periodically.
   - Check VPS resource usage: `htop`, `df -h`.

## 9. Rollback

If the VPS deployment fails smoke tests:
- DNS is still pointing to VPS — either leave it or flip back (keep 300s TTL during cutover).
- The Vercel project is deleted and will not come back. If you need emergency rollback: redeploy from the current `main` to Vercel (`vercel deploy --prod --cwd server`) — but understand you're restarting the billing bleed.
- Preferred rollback: fix the VPS issue. Most likely failure modes:
  - Supabase connection refused → IP allowlist.
  - 502 from Caddy → uvicorn not listening on 8000 → check `journalctl -u amplifier-web`.
  - Cert not provisioned → DNS hasn't propagated → wait or switch Caddy to HTTP for the first hour.

## 10. Cost comparison

| Item | Vercel (actual) | Hostinger VPS | Render fallback |
|------|-----------------|---------------|-----------------|
| Compute | $47/cycle (unpredictable) | ~$4–10/mo (already paid) | $7/mo Starter |
| Redis | n/a | $0 (self-hosted on VPS) | $10/mo |
| Bandwidth | metered | 1–8 TB included | metered-ish |
| Build minutes | $44.10 (350 min) | $0 | Included |
| **Total** | **$47+/cycle, no cap** | **~$0 marginal** | **$17/mo flat** |

## 11. Follow-ups (out of scope for this migration)

- Wire ARQ worker as a real systemd service (§4.6) — billing/trust jobs currently don't auto-run.
- Set up automated DB backups: `pg_dump` Supabase → S3 bucket or VPS disk, daily cron.
- Add `/metrics` endpoint (Prometheus format) + basic dashboard — you've been flying blind on traffic.
- Configure `fail2ban` for SSH + Caddy auth-endpoint rate limits.
- When OpenClaw lands (Phase 7 per `docs/PRD.md:1117`), co-host on the same VPS. Plan for it now: don't use all vCPU/RAM for the web server.
- Switch `allow_origins=["*"]` in `server/app/main.py:45` to an explicit allowlist once stable.
- CSRF middleware (`server/app/core/csrf.py`) is enabled globally — verify it plays nicely with non-browser clients (the user app's `server_client.py` requests).

---

## 12. Open questions

Answer before starting:

1. ~~Does the Hostinger VPS actually exist?~~ **Confirmed 2026-04-19** — KVM plan bought by Nili and Daniel for TTE + Stock Buddy, Amplifier approved to co-host.
2. **VPS plan tier + current load.** KVM 1 / 2 / 4 / 8? What's TTE using in RAM/CPU today? Dictates uvicorn worker count and `MemoryMax=` in §4.5.
3. **SSH access handoff from Nili or Daniel.** Need a key added to the `amplifier` service user (or whatever naming convention they prefer).
4. **Existing infra on the VPS.** Is Caddy / nginx / Redis already installed for TTE or Stock Buddy? Extend, don't duplicate (§4.2, §4.7).
5. **Domain strategy.** Do you own a domain to put `api.` on, or will this be a subdomain of something already purchased? TTE/Stock Buddy may already have a domain configured — reuse if so.
6. **User base size right now.** If zero real users, you can cut over whenever. If non-zero, schedule a low-traffic window.
7. **Is `ENCRYPTION_KEY` currently protecting any live data?** (§6) Audit before rotating.
8. **ARQ worker — is the entrypoint class implemented?** (§4.6) Grep for `WorkerSettings` in `server/app/`.

---

## Status

| Field | Value |
|-------|-------|
| Plan written | 2026-04-19 |
| Plan updated | 2026-04-19 — Hostinger VPS confirmed (shared with TTE + Stock Buddy, owned by Nili + Daniel) |
| Migration executed | Not yet |
| Old host | Vercel (project deleted, billing disputed) |
| New host | Hostinger KVM VPS (shared — coordinate with Nili + Daniel) |
| Clients on old URL | Yes — `config/.env` + `scripts/utils/server_client.py:22` |
