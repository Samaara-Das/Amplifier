# UAT Infrastructure — Specs & Verification

These tasks are UAT helper infrastructure bugs. They fix scripts under `scripts/uat/` and the background agent's UAT override path. They live outside the 4 product batches (Money Loop, AI Brain, Product Features, Business Launch) and outside the server infra tasks (infra.md). They are not user-facing features — they unblock UAT execution for other tasks.

**Tasks:** #63 (seed_campaign.py wrong invitation-accept endpoint), #64 (seed_campaign.py wrong image-upload endpoint), #65 (AMPLIFIER_UAT_FORCE_DAY doesn't propagate to agent_draft.iteration)

---

## Task #63 — seed_campaign.py wrong invitation-accept endpoint

### What It Does

Fixes the HTTP path used by `scripts/uat/seed_campaign.py` when accepting a campaign invitation.

**Before:** `POST /api/invitations/{assignment_id}/accept` → 404 (wrong prefix)

**After:** `POST /api/campaigns/invitations/{assignment_id}/accept` → matches the router mount at `prefix="/api/campaigns"` in `server/app/main.py`

### Files Changed

- `scripts/uat/seed_campaign.py` — one-line URL fix in step 7 of `main()`

---

## Verification Procedure — Task #63

**Preconditions**:
- Server running (local or prod)
- `UAT_TEST_USER_EMAIL`, `UAT_TEST_USER_PASSWORD`, `UAT_TEST_COMPANY_EMAIL`, `UAT_TEST_COMPANY_PASSWORD` set in `config/.env`

**Test data setup**: None — verified by code inspection.

**Test-mode flags**: none

---

### AC1: seed_campaign.py accept step calls the correct API path

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | Read `scripts/uat/seed_campaign.py` step 7. Confirm the URL matches the router mount. |
| **Expected** | URL is `f"{server_url}/api/campaigns/invitations/{assignment_id}/accept"`. Not `/api/invitations/...`. |
| **Automated** | partial |
| **Automation** | `grep -n "invitations.*accept" scripts/uat/seed_campaign.py` — expect path to contain `/api/campaigns/invitations/` |
| **Evidence** | grep output showing correct path |
| **Cleanup** | none |

### AC2: seed_campaign.py runs end-to-end without 404 on accept step

| Field | Value |
|-------|-------|
| **Setup** | Server live. UAT creds configured. |
| **Action** | `python scripts/uat/seed_campaign.py --title "UAT Test 9999" --goal brand_awareness --tone casual --brief "$(python -c "print('x'*310)")" --guidance "Test guidance at least 50 chars long for rubric." --company-urls "https://example.com" --output-id-to data/uat/last_campaign_id.txt` |
| **Expected** | Script prints `Invitation accepted: accepted`. Exit code 0. `data/uat/last_campaign_id.txt` contains an integer. |
| **Automated** | partial — automated exit code check; manual read of stdout |
| **Automation** | manual + stdout inspection |
| **Evidence** | Terminal output showing `Invitation accepted: accepted` and zero `404` lines |
| **Cleanup** | `python scripts/uat/cleanup_campaign.py --id $(cat data/uat/last_campaign_id.txt)` |

---

### Aggregated PASS rule for Task #63

- AC1 PASS (grep confirms correct path in source)
- AC2 PASS (script exits 0, invitation accepted without 404)

---

## Task #64 — seed_campaign.py wrong image-upload endpoint

### What It Does

Fixes the image upload step in `scripts/uat/seed_campaign.py` and adds a matching API endpoint server-side.

**Before:** `POST /api/storage/upload` → 404 (endpoint did not exist)

**After:** `POST /api/company/campaigns/assets` → Bearer-auth upload endpoint added to `server/app/routers/campaigns.py`. Returns `{"url": "...", "filename": "...", "content_type": "..."}`.

### Files Changed

- `server/app/routers/campaigns.py` — new `upload_campaign_asset_api()` route (~40 LOC)
- `scripts/uat/seed_campaign.py` — URL updated in `_upload_product_images()`

### Schema Migration

No model changes. No Alembic migration required.

---

## Verification Procedure — Task #64

**Preconditions**:
- Server running (local or prod)
- Company JWT available (via `seed_campaign.py` login step or direct login)
- A test image file exists at `data/uat/fixtures/product1.jpg` (create one if missing: `python -c "from PIL import Image; Image.new('RGB',(100,100)).save('data/uat/fixtures/product1.jpg')"`)

**Test data setup**: None beyond the preconditions.

**Test-mode flags**: none

---

### AC1: New API endpoint rejects unauthenticated upload

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `pytest tests/server/test_campaigns.py::TestCampaignAssetUpload::test_upload_asset_rejects_unauthenticated -v` |
| **Expected** | Test PASSES. Endpoint returns 401 or 403. |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_campaigns.py::TestCampaignAssetUpload::test_upload_asset_rejects_unauthenticated` |
| **Evidence** | pytest stdout PASSED |
| **Cleanup** | none |

### AC2: New API endpoint rejects unsupported file type

| Field | Value |
|-------|-------|
| **Setup** | Company JWT available. |
| **Action** | `pytest tests/server/test_campaigns.py::TestCampaignAssetUpload::test_upload_asset_rejects_unsupported_type -v` |
| **Expected** | Test PASSES. Uploading `application/octet-stream` returns 400 with "Unsupported file type". |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_campaigns.py::TestCampaignAssetUpload::test_upload_asset_rejects_unsupported_type` |
| **Evidence** | pytest stdout PASSED |
| **Cleanup** | none |

### AC3: seed_campaign.py image upload step calls correct endpoint

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `grep -n "api/company/campaigns/assets" scripts/uat/seed_campaign.py` |
| **Expected** | At least one match showing the updated URL. |
| **Automated** | partial |
| **Automation** | grep command above |
| **Evidence** | grep output with matching line |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #64

- AC1 and AC2 PASS (pytest)
- AC3 PASS (grep confirms correct path in seed_campaign.py)

---

## Task #65 — AMPLIFIER_UAT_FORCE_DAY doesn't propagate to agent_draft.iteration

### What It Does

Fixes `scripts/background_agent.py` so that `AMPLIFIER_UAT_FORCE_DAY` is read early in the campaign loop and applied to both the `posting_plan` call and the `add_draft(iteration=...)` call. Previously, `posting_plan` was called with hardcoded `day_number=1` before the override was applied.

### Files Changed

- `scripts/background_agent.py` — reads env var early, uses `_early_day_override` for `posting_plan` and `day_number` assignment

---

## Verification Procedure — Task #65

**Preconditions**:
- Local user app environment set up
- At least one active campaign in local DB (or use seed + accept)

**Test data setup**:
```bash
export AMPLIFIER_UAT_FORCE_DAY=3
```

**Test-mode flags**:
- `AMPLIFIER_UAT_FORCE_DAY=3` — forces `day_number=3` for all campaign draft generation in the current run

---

### AC1: With AMPLIFIER_UAT_FORCE_DAY=3, agent_draft.iteration equals 3

| Field | Value |
|-------|-------|
| **Setup** | Active campaign in local DB. `AMPLIFIER_UAT_FORCE_DAY=3` exported. |
| **Action** | Run one content generation cycle: `AMPLIFIER_UAT_FORCE_DAY=3 python scripts/background_agent.py --once` (or equivalent). Then query: `python -c "import sqlite3; c=sqlite3.connect('data/local.sqlite'); rows=c.execute('SELECT iteration FROM agent_draft ORDER BY id DESC LIMIT 3').fetchall(); print(rows)"` |
| **Expected** | All returned rows show `iteration=3`. Log line `UAT override: day_number=3` appears in output. |
| **Automated** | partial |
| **Automation** | manual + log grep + SQL query |
| **Evidence** | SQL output showing `(3,)` rows. Log line matching `UAT override: day_number=3`. |
| **Cleanup** | `DELETE FROM agent_draft WHERE iteration=3 AND created_at > datetime('now', '-1 hour')` (or use cleanup_campaign.py) |

---

### Aggregated PASS rule for Task #65

- AC1 PASS (iteration column contains the forced day number)
- Log contains `UAT override: day_number=3`
- No `exception` or `traceback` in agent output during the run
