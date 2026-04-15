---
description: Quick smoke test of server, dashboards, and user app
argument-hint: [area to test: server | admin | company | user-app | all]
allowed-tools: Bash, Read, Grep, mcp__chrome-devtools__navigate_page, mcp__chrome-devtools__take_screenshot, mcp__chrome-devtools__list_console_messages, mcp__chrome-devtools__list_network_requests, mcp__chrome-devtools__new_page, mcp__chrome-devtools__select_page, mcp__chrome-devtools__list_pages, mcp__chrome-devtools__evaluate_script, mcp__chrome-devtools__click
---

Run a quick smoke test to catch broken pages, 500 errors, and JS console errors.

Area to test: $ARGUMENTS (default: all)

## Step 1: Ensure server is running

Check if something is listening on port 8000:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "DOWN"
```
If DOWN, start it:
```bash
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
```
Wait 3 seconds, then re-check.

## Step 2: API smoke test

Hit these endpoints and report status codes:
- `GET /health`
- `GET /api/campaigns` (with auth token if needed)
- `GET /admin/login`
- `GET /company/login`

Any non-2xx response = FAIL. Report the status code and response body snippet.

## Step 3: Dashboard smoke test (ChromeDevTools)

Navigate to each dashboard page, wait for load, check for:
- **JS console errors**: `list_console_messages` — any `error` level = FAIL
- **Network failures**: `list_network_requests` — any 4xx/5xx on page resources = FAIL  
- **Visual check**: `take_screenshot` of any page that has errors

### Pages to test by area:

**admin**: `/admin/login`, `/admin/` (overview), `/admin/users`, `/admin/campaigns`, `/admin/financial`
**company**: `/company/login`, `/company/dashboard`, `/company/campaigns`
**user-app**: `http://localhost:5222/` (only if user app is running on port 5222)
**server**: API endpoints only (step 2)
**all**: everything above

## Step 4: Report

Output a clear pass/fail table:
```
Page                    | Status | Issues
/admin/login            | PASS   | -
/admin/                 | FAIL   | JS error: "Cannot read property..."
/company/dashboard      | PASS   | -
```

If all pass: "All clear." If any fail: list the issues with enough detail to debug.

## Rules

- Do NOT fix issues — just report them
- Keep it fast — don't wait more than 5 seconds per page
- If ChromeDevTools MCP is not connected, fall back to API-only testing (step 2) and note that dashboard testing requires ChromeDevTools
- Auth for admin pages: navigate to `/admin/login`, type password "admin", submit
- Auth for company pages: use test credentials from CLAUDE.md
