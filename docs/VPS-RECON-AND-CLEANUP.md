# VPS Recon and Cleanup Runbook

**Target VPS:** Nili + Daniel's Hostinger KVM 1 (Mumbai, Ubuntu 24.04, 1 vCPU / 4 GB / 50 GB)
**Purpose:** Identify everything running on the VPS, get explicit go-ahead from Nili / Daniel before stopping anything, then cleanly stop unneeded services to free the box for Amplifier deploy per `docs/MIGRATION-FROM-VERCEL.md`.

> **Pre-recon update from Hostinger Kodee 2026-04-25:** Kodee reports the only running non-OpenClaw processes are stock Ubuntu daemons: `systemd-journald`, `tailscaled`, `fwupd`, `snapd`, `systemd-resolved`, `rsyslogd`, `multipathd`. All using "very little CPU and small RAM" per Kodee. **OpenClaw is the only real cleanup target.** Tailscale is the one Nili-specific item — ask her if she's actively using it for remote access before disabling.

> **Why this runbook exists.** Last attempt at OpenClaw removal left it still running (likely systemd auto-restart) AND we noticed other unidentified processes on the box. The single most common way migrations like this fail is: "I cleaned up stuff I shouldn't have." 1-2 days for a proper inventory + handoff conversation is cheap insurance vs. discovering 3 days post-deploy that you broke a TTE-related service.

---

## Phase 1 — Get SSH access (blocks everything)

Message to send Nili (today):

> Hey Nili, I'm deploying Amplifier to the Mumbai KVM VPS this week. Can you add my SSH public key to the box, ideally under a dedicated `amplifier` user with sudo? I'll send you my public key. Will also need to do a recon pass on what's currently running and check with you and Daniel before stopping any unknown services.

If you don't have an SSH keypair, generate one on Windows:
```powershell
ssh-keygen -t ed25519 -C "amplifier-deploy"
# Default path: C:\Users\dassa\.ssh\id_ed25519 (private) + id_ed25519.pub (public)
# Send the .pub file contents to Nili
```

---

## Phase 2 — Recon (run as root, save output BEFORE changing anything)

SSH into the VPS, then run all of this in a single session and capture to a timestamped file:

```bash
RECON_FILE=/tmp/recon-$(date +%F-%H%M).txt
{
  echo "=== systemd running services ==="
  systemctl list-units --type=service --state=running --no-pager

  echo -e "\n=== process tree (top 50) ==="
  ps auxf | head -50

  echo -e "\n=== top by CPU ==="
  ps aux --sort=-%cpu | head -20

  echo -e "\n=== top by RAM ==="
  ps aux --sort=-%mem | head -20

  echo -e "\n=== network listeners ==="
  ss -tlnp

  echo -e "\n=== docker containers (if any) ==="
  docker ps -a 2>/dev/null || echo "(docker not installed)"

  echo -e "\n=== cron — root ==="
  crontab -l 2>/dev/null

  echo -e "\n=== cron — all users ==="
  for u in $(cut -d: -f1 /etc/passwd); do
    OUT=$(crontab -u $u -l 2>/dev/null)
    if [ -n "$OUT" ]; then echo "--- user: $u ---"; echo "$OUT"; fi
  done

  echo -e "\n=== systemd unit files in custom locations ==="
  ls -la /etc/systemd/system/ /etc/systemd/system/multi-user.target.wants/ 2>/dev/null

  echo -e "\n=== recent journal (last 24h, last 100 lines) ==="
  journalctl --since "24 hours ago" --no-pager | tail -100

  echo -e "\n=== resource summary ==="
  df -h
  free -h
  uptime

  echo -e "\n=== user accounts with shell access ==="
  grep -E "/bin/(bash|sh|zsh)$" /etc/passwd

  echo -e "\n=== disk usage by common dirs ==="
  sudo du -sh /home/* /opt/* /srv/* /var/www/* 2>/dev/null
} | tee "$RECON_FILE"

echo "Recon saved to: $RECON_FILE"
```

`scp` the recon file to your laptop:
```powershell
# On Windows
scp amplifier@<VPS_IP>:/tmp/recon-*.txt C:\Users\dassa\Work\Auto-Posting-System\docs\recon\
```

---

## Phase 3 — Identify each unknown service

> **Likely-empty phase.** Per Kodee 2026-04-25, the only non-OS process is OpenClaw. If recon confirms this, skip directly to Phase 4 with a single ask for Nili: "Are you actively using Tailscale on this box for remote access?" If recon turns up surprises (anything not in the known list), work through them here.

For every systemd unit you don't recognize, run:

```bash
sudo systemctl cat <service-name>      # full unit definition + ExecStart
sudo systemctl status <service-name>   # current state, recent logs
sudo systemctl list-dependencies --reverse <service-name>   # what depends on this?
which <process-name>                   # where the binary lives
```

Build a table like this for the handoff conversation:

| Service | Owner (guess) | What it does | Stop OK? |
|---|---|---|---|
| openclaw-gateway | Daniel | OpenClaw multi-agent gateway | YES — confirmed by father, preserve binaries |
| ssh.service | system | SSH | NO |
| ... | ... | ... | ASK |

---

## Phase 4 — Handoff conversation with Nili + Daniel

Take the recon file + the table to Nili and Daniel. Get explicit go-ahead on each service marked "ASK". Quote each line — "What is `xyz.service`? Can I stop it?" beats "Can I clean up the server?" every time.

Document Nili / Daniel's answers in writing (Discord, WhatsApp, anywhere with a timestamp). If a service is theirs and they want it kept running, mark it KEEP and accept the resource cost.

---

## Phase 5 — Cleanup (only after Phase 4 explicit OK)

For each service marked "Stop OK":

```bash
# 1. Inspect dependencies one more time before stopping
sudo systemctl list-dependencies --reverse <unit>

# 2. Stop the service
sudo systemctl stop <unit>

# 3. Disable so it doesn't auto-start on reboot
sudo systemctl disable <unit>

# 4. CRITICAL — verify orphans (worker processes) didn't survive
ps aux | grep -i <unit-name>
# Should return only the grep line itself.
# If orphans found:
sudo pkill -f <process-pattern>
# Re-run ps to confirm.

# 5. (Optional) Mask the unit so a `systemctl start` won't accidentally bring it back
sudo systemctl mask <unit>
```

For Docker containers (if any are unwanted):
```bash
sudo docker stop <container>
sudo docker rm <container>
sudo docker ps -a   # confirm gone
```

For cron jobs flagged for removal — edit the relevant user's crontab:
```bash
sudo crontab -u <user> -e
# Comment out the line; do NOT delete (preserves provenance)
```

**Do NOT delete binaries on disk.** OpenClaw in particular needs to come back for Phase 7 of the Amplifier PRD. Stop + disable + mask is enough; the files stay where they are.

---

## Phase 6 — Verify the box is genuinely idle

Before starting `MIGRATION-FROM-VERCEL.md` §4.2, all of these must pass:

```bash
free -h
# "available" column should show ≥ 3.0 GB

htop            # press q to quit
# Watch CPU% line for 60 seconds. Average <10%. No process consistently >5%.

uptime
# Load average (1-min) should be <0.3

ps auxf | head -30
# Verify no openclaw, no unknown agent processes
```

If any of these fail, go back to Phase 3 — there's a service still running that you missed.

---

## Phase 7 — Snapshot post-cleanup state

Once idle, take a clean snapshot for the deploy baseline:

```bash
SNAP_FILE=/tmp/snapshot-pre-amplifier-$(date +%F-%H%M).txt
{
  systemctl list-units --type=service --state=running --no-pager
  echo -e "\n---"
  ps auxf
  echo -e "\n---"
  free -h
  uptime
} | tee "$SNAP_FILE"
```

`scp` to laptop. This is your "known-good idle" baseline. Any future weirdness can be diffed against this.

---

## Phase 8 — Proceed to MIGRATION-FROM-VERCEL.md §4.2

Now and only now: install Python, Caddy, Redis (if not already there), create the `amplifier` system user, deploy the code, write the systemd unit, point Caddy at it, smoke-test.

Apply the three §0 tweaks from `MIGRATION-FROM-VERCEL.md`:
- §4.5 systemd: drop `CPUQuota=80%`, set `MemoryMax=2500M`, `--workers 1`
- §4.2 baseline: OpenClaw is already gone (you did Phase 5)
- §4.6 ARQ worker: `grep` for `WorkerSettings` first; defer if missing

---

## Rollback if cleanup goes wrong

If you stop something and Nili / Daniel report it broke their work:

```bash
# Re-enable + start
sudo systemctl unmask <unit>     # if you masked it
sudo systemctl enable <unit>
sudo systemctl start <unit>
sudo systemctl status <unit>     # verify it came up
```

Because you preserved binaries on disk and only stopped+disabled (not deleted), recovery is one command per service. This is why we never `rm -rf` during cleanup.

---

## Reference: original recon command set (from Claude.ai consultation 2026-04-25)

```bash
systemctl list-units --type=service --state=running --no-pager
ps auxf | head -50
ss -tlnp
docker ps -a 2>/dev/null
crontab -l; for u in $(cut -d: -f1 /etc/passwd); do crontab -u $u -l 2>/dev/null && echo "^^ $u"; done
ls /etc/systemd/system/ /etc/systemd/system/multi-user.target.wants/
journalctl --since "24 hours ago" --no-pager | tail -100
df -h; free -h; uptime
```
