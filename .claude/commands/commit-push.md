---
description: Commit, push, and auto-deploy to Hostinger VPS (api.pointcapitalis.com)
allowed-tools: Bash, Read, Grep, Glob
---

1. Git add the unstaged changes
2. Remove unnecessary debug logs and temporary files
3. Understand the changes and make a commit for it with a one-liner commit msg. If the changes are huge and need more explanation, write a description in the commit message
4. Push changes which are relevant to the commit (push to BOTH `flask-user-app` AND `main` so the deploy reflects latest)
5. **Auto-deploy** (only if server-affecting files changed — files in `server/`, `requirements.txt`, or alembic migrations):

   ```bash
   ssh -i ~/.ssh/amplifier_vps -o IdentitiesOnly=yes -o BatchMode=yes sammy@31.97.207.162 \
     "sudo -u amplifier git -C /home/amplifier/app pull && \
      sudo systemctl restart amplifier-web && \
      sleep 8 && \
      curl -s -o /dev/null -w 'health: HTTP %{http_code}\n' https://api.pointcapitalis.com/health"
   ```

   - Do NOT ask for confirmation — just deploy
   - Report the health check result when done (should be HTTP 200)
   - If health is not 200, run `sudo journalctl -u amplifier-web -n 30 --no-pager` to capture errors and report them, but don't block the push
   - Skip auto-deploy entirely for docs-only or test-only changes (nothing to deploy)

6. **Schema-changing commits** (anything that modifies `server/app/models/*.py`): also remind the user that an Alembic migration should be generated + applied to the Supabase production DB before relying on the deploy. Cross-reference Task #11 (Alembic baseline + enforcement). Do NOT auto-apply schema changes.

## Notes

- The previous version of this skill auto-deployed to Vercel — that infrastructure is dead as of 2026-04-25. Server now runs on Hostinger KVM 1 VPS at `https://api.pointcapitalis.com`.
- The systemd unit `amplifier-web.service` runs uvicorn (1 worker, 127.0.0.1:8000). Caddy reverse-proxies with auto-TLS.
- Restart causes ~13-second downtime (uvicorn application startup time). 502 from Caddy briefly during this window is expected.
- See `docs/HOSTING-DECISION-RECORD.md` and `docs/MIGRATION-FROM-VERCEL.md` for full deploy context.
