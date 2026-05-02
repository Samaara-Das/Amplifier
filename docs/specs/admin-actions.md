# Task #80 — Missing Admin Financial Buttons

**Status:** pending  
**Branch:** flask-user-app  

The admin financial dashboard (`/admin/financial`) has two backend routes that have no corresponding UI buttons:

- `POST /admin/financial/run-earning-promotion` — promotes `pending` payouts past the 7-day hold to `available` (`server/app/routers/admin/financial.py:207`)
- `POST /admin/financial/run-payout-processing` — processes `available` payouts via Stripe Connect (`server/app/routers/admin/financial.py:238`)

The existing template (`server/app/templates/admin/financial.html`) has two buttons ("Run Billing Cycle" + "Run Payout Cycle") in the `.action-row` div. This task adds the two missing buttons in the same HTMX form pattern, with `hx-indicator` disabling while submitting to prevent double-submit.

Both routes already work — the fix is purely template + HTMX wiring.

---

## Features to verify end-to-end (Task #80)

1. "Run Earning Promotion" button renders in the action row alongside the existing buttons — AC1
2. Clicking "Run Earning Promotion" POSTs to the route, shows a success toast, and logs an audit row — AC2
3. "Run Payout Processing" button renders and clicking POSTs to the route, shows success toast + audit row — AC3
4. Both buttons are disabled while their form is submitting (htmx-indicator pattern), preventing double-submit — AC4

---

## Verification Procedure — Task #80

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Admin dashboard accessible at `https://api.pointcapitalis.com/admin/login` (password: `admin`).
- Chrome DevTools MCP available.
- At least one `payouts` row exists in `pending` status (for earning-promotion to have something to promote). Seed if needed by running the "Run Billing Cycle" button via the admin dashboard after logging in (step 1 of Test data setup below).

### Test data setup

1. **Log into admin dashboard** and capture `admin_token` cookie:
   ```bash
   TOKEN=$(curl -s -c data/uat/admin_cookies.txt -b data/uat/admin_cookies.txt \
     -X POST https://api.pointcapitalis.com/admin/login \
     -d 'password=admin' -L \
     | python -c "import sys; print('logged in')")
   ```

2. **Seed a payout in pending status** (so run-earning-promotion has a row to promote):
   ```bash
   curl -s -X POST https://api.pointcapitalis.com/admin/financial/run-billing \
     -b data/uat/admin_cookies.txt \
     | python -c "import sys; print('run-billing response received')"
   ```
   If no real payout rows exist, skip — the route still succeeds with `promoted=0` (the success message is still shown).

3. **Capture audit_log row count** before the run:
   ```bash
   curl -s -b data/uat/admin_cookies.txt \
     "https://api.pointcapitalis.com/admin/audit" \
     | python -c "import sys; print('audit page fetched:', len(sys.stdin.read()), 'bytes')"
   ```
   Note the count from the page — exact value captured during AC2/AC3.

### Test-mode flags

None — these routes are purely admin UI actions with no time-sensitive logic.

---

### AC1 — "Run Earning Promotion" button renders on /admin/financial

| Field | Value |
|-------|-------|
| **Setup** | Admin logged in via DevTools MCP. |
| **Action** | `new_page("https://api.pointcapitalis.com/admin/financial")` → `take_snapshot` → `take_screenshot("data/uat/screenshots/80_ac1_financial.png")`. Search snapshot for button text. |
| **Expected** | Page renders. The `.action-row` div contains 4 buttons (or forms): "Run Billing Cycle", "Run Payout Cycle", **"Run Earning Promotion"**, and **"Run Payout Processing"**. All 4 are visible. The two new buttons are NOT disabled on page load. Zero console errors. `list_network_requests` shows no 5xx. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP — assert via regex on snapshot text: `(?i)run earning promotion` and `(?i)run payout processing` |
| **Evidence** | screenshot; snapshot text dump confirming all 4 button labels present |
| **Cleanup** | none |

---

### AC2 — "Run Earning Promotion" click POSTs to route, shows toast, logs audit row

| Field | Value |
|-------|-------|
| **Setup** | Financial page loaded (AC1 state). Record `audit_log` count before: `curl -s -b data/uat/admin_cookies.txt "https://api.pointcapitalis.com/admin/audit?per_page=1" | python -c "import sys; print('audit page status: ok')"` (count captured from page during AC execution). |
| **Action** | `take_snapshot` → find UID of "Run Earning Promotion" button → `click(uid)` → wait 3s → `take_snapshot`. Check `list_network_requests` for the POST. |
| **Expected** | POST request to `/admin/financial/run-earning-promotion` returns HTTP 200. Page re-renders (HTMX swap) with a success alert/toast containing text matching `(?i)(earning promotion|promoted|payouts promoted)` with a number (e.g., "Earning promotion: 0 payouts promoted from pending to available" is valid). New `audit_log` row with `event='earning_promotion_run'` exists (verify: `curl -s https://api.pointcapitalis.com/admin/audit -b data/uat/admin_cookies.txt | grep -i earning_promotion`). Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP + curl |
| **Evidence** | screenshot showing toast; network log showing 200 POST; audit log grep output |
| **Cleanup** | none |

---

### AC3 — "Run Payout Processing" click POSTs to route, shows toast, logs audit row

| Field | Value |
|-------|-------|
| **Setup** | Financial page loaded. |
| **Action** | `take_snapshot` → find UID of "Run Payout Processing" button → `click(uid)` → wait 3s → `take_snapshot`. Check `list_network_requests`. |
| **Expected** | POST request to `/admin/financial/run-payout-processing` returns HTTP 200. Page re-renders with success alert containing text matching `(?i)(payout processing|processed|paid|failed)` and numbers (e.g., "Payout processing: 0 processed, 0 paid, 0 failed" is valid). New `audit_log` row with `event='payout_processing_run'`. Zero console errors. No 5xx. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP + curl |
| **Evidence** | screenshot showing toast; network log 200 POST; audit grep for `payout_processing_run` |
| **Cleanup** | none |

---

### AC4 — Both new buttons disabled while submitting (no double-submit)

| Field | Value |
|-------|-------|
| **Setup** | Financial page loaded. DevTools Network throttling set to "Slow 3G" to make the server response take > 500ms (simulates submit latency). |
| **Action** | For each of the two new buttons in turn: `take_snapshot` → click the button → immediately (within 200ms) take another snapshot → `list_network_requests`. Alternatively: click the button twice in rapid succession and count the number of POST requests to the route. |
| **Expected** | During submission: the clicked button's DOM shows a loading/disabled state (`disabled` attribute OR `htmx-request` class on the form). Only ONE POST request to the route per click sequence (no duplicate requests). After response: button re-enables. Verify the htmx-indicator pattern: `evaluate_script("document.querySelector('form[action*=\"run-earning-promotion\"] button').disabled")` returns `true` during the in-flight request. |
| **Automated** | partial — automated for request count; manual for disabled-state visual |
| **Automation** | Chrome DevTools MCP (double-click sequence + request count check) |
| **Evidence** | network log showing exactly 1 POST per button click sequence; screenshot of button in loading state; manual y/n: "Does the button appear disabled/loading while the request is in flight? (y/n)" |
| **Cleanup** | Reset Network throttling to "No throttling". |

---

### Aggregated PASS rule for Task #80

Task #80 is marked done in task-master ONLY when:
1. AC1–AC3 all PASS (automated)
2. AC4 PASS — request count = 1 per submit AND user says `y` on disabled-state visual
3. No `error|exception|traceback` in server logs during the UAT window: `ssh sammy@31.97.207.162 "sudo journalctl -u amplifier-web --since '-5min' | grep -i 'error\|exception\|traceback' | wc -l"` → 0
4. No new `audit_log` rows with `severity='error'` during the window
5. Server `/health` returns 200 at end of run
6. UAT report `docs/uat/reports/task-80-<yyyy-mm-dd>.md` written with all screenshots and network logs embedded
