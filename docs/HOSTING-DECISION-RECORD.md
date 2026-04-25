# Hosting Decision Record — Task #41

**Date locked:** 2026-04-25
**Task:** #41 (Plan + execute Vercel migration)
**Decision owner:** Sammy + father (consulted) + Claude.ai web (outside advisor)
**Hard deadline:** `/health` returning 200 by **end of week 2026-05-02**

## Decision

Deploy Amplifier server on **Nili + Daniel's existing Hostinger KVM 1 VPS** (Mumbai, Ubuntu 24.04, 1 vCPU / 4 GB RAM / 50 GB disk). Single-tenant for Amplifier after OpenClaw removal. No upgrade. No new VPS.

Execution runbook: [`MIGRATION-FROM-VERCEL.md`](MIGRATION-FROM-VERCEL.md)
Pre-deploy cleanup runbook: [`VPS-RECON-AND-CLEANUP.md`](VPS-RECON-AND-CLEANUP.md)
Outside-advisor brief used: [`CLAUDE-DESKTOP-TASK-41-BRIEF.md`](CLAUDE-DESKTOP-TASK-41-BRIEF.md)

## Options considered

### Chosen: Nili KVM 1 (Hostinger account `nili.thp@gmail.com`)
- **Specs:** 1 vCPU, 4 GB RAM, 50 GB disk, Ubuntu 24.04, Mumbai, IPv4 + IPv6.
- **Current state:** `openclaw-gateway` consumes most CPU; very high CPU steal (host-level contention); daily backups OFF.
- **Action required:** Stop + disable OpenClaw and any other unidentified services (Phase 3-5 in `VPS-RECON-AND-CLEANUP.md`). Preserve binaries on disk for Phase 7.
- **Why chosen:** Free (sunk cost), single-tenant for Amplifier (TTE / Stock Buddy will NOT land here per father), workload sanity check shows ~1 GB resident usage on a 4 GB box, in-place upgrade to KVM 2 is one-click in hPanel when needed.

### Rejected: Option A — New free Vercel account
- **Why rejected:** Vercel Hobby ToS explicitly prohibits commercial use; Amplifier takes 20% cut of real money flow → commercial → automated detection will suspend. Same per-invocation billing trap killed the original deployment ($47/cycle on 3.9M invocations). 1M free invocations/mo would be consumed in ~7-8 days at expected user volume. **Permanently off the table.**

### Rejected: Option C — Nili Business Web Hosting (poolsifi.com)
- **Specs:** Business Web Hosting (LiteSpeed shared, USA/Arizona), 2 CPU cores, 3 GB RAM, no SSH on plan tier.
- **Hosts (separate from VPS):** poolsifi.com, learn.poolsifi.com, myadmin.poolsifi.com, analysis.poolsifi.com, marketdavinci.com, silverpips.com, thebrutalcapitalist.com (all on different physical infrastructure than the VPS).
- **Why rejected:** Cannot run persistent Python ASGI processes (uvicorn). Cannot run local Redis daemon. Cannot run systemd services. Sandboxed for PHP/CMS via hPanel. No SSH = no deploy story.

### Rejected: Option D — KVM 8 on `kingsdxb2025@gmail.com`
- **Specs:** Hostinger's top KVM tier. Bought specifically for Stock Buddy + TTE under employer (Rahul) authority. Also has Starter Business Email (stockbuddy.co, expires 2028-04-07).
- **Why rejected:** Employer has full account access. Privacy / IP risk: do not want employer to see Amplifier source, env vars (Stripe keys, DB creds, JWT secrets), or know that Amplifier exists. Father confirmed off-limits ("not for our use"). **Revisit only if employer-access situation ever changes.**

### Rejected: Upgrade Nili KVM 1 → KVM 2 preemptively
- **Cost:** ~$8-12/mo multi-year, ~$13-16/mo monthly. ~$48-96 unnecessary spend over 6 months.
- **Why rejected:** KVM 2 is sized for sites up to 50,000 monthly visitors — 100x current Amplifier scale (near-zero real users). Pre-buying capacity = comfort spending against the Leila Hormozi framework in `CLAUDE.md` ("ship ugly, don't pre-buy safety"). In-place upgrade is one-click in hPanel (~10 min reboot) when actually needed. Trigger conditions defined below.

### Rejected: New small VPS under own Hostinger account
- **Cost:** ~$5-8/mo introductory, ~$11/mo at renewal (~$60-96/yr).
- **Why rejected:** Optimizes for isolation that has zero current value. Nili KVM is already single-tenant for Amplifier. Duplicate of free capacity already available. Only scenario isolation matters: future disagreement with Nili on server admin → at that point migrate, don't run two boxes in parallel.

## Workload sanity check (why KVM 1 is enough)

| Component | Resident memory |
|---|---|
| FastAPI + asyncpg (1 uvicorn worker) | ~250-350 MB |
| ARQ worker (idle, polling Redis) | ~80-120 MB |
| Local Redis | ~20-60 MB |
| Caddy reverse proxy | ~30-50 MB |
| Ubuntu 24.04 baseline + journald + sshd | ~400-600 MB |
| **Total** | **~0.8-1.2 GB on 4 GB** |
| **Headroom** | **~2.8-3.2 GB** |

CPU is even less of a worry: workload is I/O-bound (waits on Supabase, Gemini, Stripe). 1 vCPU async event loop handles hundreds of concurrent waiters. 500 active users × 1 poll / 10 min = ~50 polls/minute → trivial.

## Upgrade triggers (when KVM 1 → KVM 2 in-place)

Switch when **any one** of these is true and sustained for ≥7 days:

- Memory utilization >80% (`free -h` showing <800 MB available consistently)
- 1-min load average >1.5 sustained (1 vCPU = >1.5 means request queuing)
- Caddy 5xx rate >0.5% (`journalctl -u caddy | grep " 5[0-9][0-9] "`)
- ~300+ active user-app instances polling, OR Stripe live + paying users
- OpenClaw Phase 7 brought back as co-tenant — most likely real trigger, 2-4 months out

In-place upgrade is one-click in hPanel: same IP, same SSH keys, same disk, ~10 min reboot.

## Risks accepted

1. **Sudden viral spike** (5,000 users / week) would undersize KVM 1. Monitoring will catch this within hours via the trigger conditions above. No catastrophic failure mode at current scale.
2. **OpenClaw incomplete cleanup** — last attempt left it running. `VPS-RECON-AND-CLEANUP.md` Phase 5 step 4 mandates `ps aux | grep` after every `systemctl stop` to catch orphan workers.
3. **Unknown services on the VPS** — Phase 3-4 of the cleanup runbook mandates explicit Nili / Daniel sign-off on every service before stopping. Adds 1-2 days but prevents breaking their work.
4. **No isolation from Nili / Daniel admin actions** — they could in theory `sudo` and disrupt Amplifier. Accepted: trust relationship, daily Hostinger backups (need to enable — currently OFF), and Supabase holds the actual data.
5. **ARQ worker entrypoint may not exist** — `MIGRATION-FROM-VERCEL.md` §4.6 flags this. Web server ships first; worker becomes a follow-up task if `WorkerSettings` class isn't yet implemented.
6. **`ENCRYPTION_KEY` rotation could brick prod data** — `MIGRATION-FROM-VERCEL.md` §6 mandates an audit (`grep -rn "crypto.encrypt\|crypto.decrypt" server/`) before rotating.

## Process notes (for future hosting decisions)

This decision was made with an outside advisor (Claude.ai web) acting as an independent reviewer. The brief at `CLAUDE-DESKTOP-TASK-41-BRIEF.md` is reusable for future big technical decisions — the format (tier-1/2/3 reading list + explicit no-assumptions rule + ask-questions allowance + web-search allowance) worked well and should be reused.

Key insight from the consultation: the binding constraint on hosting choice was **willingness to ship today**, not Amplifier's actual load. Don't pre-buy capacity that isn't needed; ship on what's free, monitor, upgrade when triggers hit.
