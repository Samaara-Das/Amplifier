---
description: Commit, push, and auto-deploy to Vercel when on main
allowed-tools: Bash, Read, Grep, Glob
---

1. Git add the unstaged changes
2. Remove unnecessary debug logs and temporary files
3. Understand the changes and make a commit for it with a one-liner commit msg. If the changes are huge and need more explanation, write a description in the commit message
4. Push changes which are relevant to the commit
5. **Auto-deploy**: After pushing, automatically deploy to Vercel:
   ```bash
   vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
   ```
   - Do NOT ask for confirmation — just deploy
   - Report the deployment URL when done
   - If the deploy fails, report the error but don't block the push
