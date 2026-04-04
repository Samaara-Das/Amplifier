# Amplifier Company Dashboard — Deployment Guide

## 1. Local Development

### Prerequisites
- Python 3.11+
- pip packages: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite`, `jinja2`, `pydantic-settings`, `python-multipart`, `passlib[bcrypt]`, `python-jose[cryptography]`, `httpx`, `beautifulsoup4`

### Start the Server
```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Access
- **Company Dashboard:** `http://localhost:8000/company/login`
- **Admin Dashboard:** `http://localhost:8000/admin/login`
- **API Docs:** `http://localhost:8000/docs`

### Test Mode
Without Stripe configured, the billing page uses **test mode** — entering an amount instantly credits the balance without real payment processing.

---

## 2. Production Deployment (Vercel + Supabase)

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | Random 32+ character secret for JWT tokens |
| `ADMIN_PASSWORD` | Yes | Admin dashboard password |
| `STRIPE_SECRET_KEY` | No | Stripe API key. Without it, billing uses test mode (instant credit) |
| `SUPABASE_URL` | No | Supabase project URL for file uploads. Without it, campaign asset upload fails |
| `SUPABASE_SERVICE_KEY` | No | Supabase service key for storage access |
| `GEMINI_API_KEY` | No | Google Gemini API key for AI campaign brief generation. Set via campaign_wizard.py |

### Deploy
```bash
vercel deploy --yes --prod --cwd server
```

### Post-Deployment Checklist
- [ ] Set all required environment variables
- [ ] Verify company login page loads: `https://<domain>/company/login`
- [ ] Register a test company account
- [ ] Test billing top-up (test mode or Stripe)
- [ ] Test campaign creation wizard
- [ ] Verify AI generation works (requires Gemini API key)

---

## 3. Service Dependencies

### Stripe (Optional)
- **Purpose:** Real payment processing for company balance top-ups
- **Without it:** Test mode — amounts are credited instantly
- **Setup:** Set `STRIPE_SECRET_KEY` environment variable
- **Flow:** Company → Stripe Checkout → Success callback → Balance credited

### Supabase Storage (Optional)
- **Purpose:** Campaign asset uploads (product images, documents)
- **Without it:** File uploads return 500 error
- **Setup:** Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- **Bucket:** `campaign-assets` (must be created in Supabase dashboard)
- **Folder structure:** `company-{id}/images/` and `company-{id}/files/`

### Gemini API (Optional)
- **Purpose:** AI-powered campaign brief generation
- **Without it:** AI generation fails, fallback returns default brief template
- **Setup:** Set `GEMINI_API_KEY` in environment or in `campaign_wizard.py`
- **Models used:** gemini-2.5-flash → gemini-2.0-flash → gemini-2.5-flash-lite (fallback chain)

---

## 4. Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./amplifier.db` | Database connection |
| `JWT_SECRET_KEY` | `change-me-to-a-random-secret` | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | Token lifetime |
| `PLATFORM_CUT_PERCENT` | `20.0` | Platform's cut from payouts (%) |
| `MIN_PAYOUT_THRESHOLD` | `10.0` | Minimum user balance for payout ($) |
| `STRIPE_SECRET_KEY` | (empty) | Stripe API key |
| `SUPABASE_URL` | (empty) | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | (empty) | Supabase service key |
| `SERVER_URL` | `http://localhost:8000` | Public server URL (for Stripe redirects) |

---

## 5. Security Checklist

### Before Going Live
- [ ] Change `JWT_SECRET_KEY` to a strong random secret
- [ ] Use HTTPS in production (Vercel provides this)
- [ ] Set `STRIPE_SECRET_KEY` for real payment processing
- [ ] Restrict CORS origins in `main.py` (currently `*`)
- [ ] Set `DEBUG=false` to disable SQL query logging
- [ ] Test all pages return 200 after deployment

### Ongoing
- Monitor company balances and campaign budgets
- Review flagged campaigns in the admin dashboard
- Process pending payouts regularly

---

## 6. Troubleshooting

### "You need at least $50 to create a campaign"
The company's balance is below $50. Go to Billing → Add Funds.

### Campaign wizard shows "AI generation failed"
- Check that `GEMINI_API_KEY` is set
- The AI generates a fallback brief — edit it manually
- Check server logs for specific Gemini API error

### File upload returns "Upload failed"
Supabase Storage is not configured. Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

### "Payment verification failed"
The Stripe session expired or the company_id in the session metadata doesn't match. The user should try the payment again.

### Campaign stuck in "draft"
The company doesn't have enough balance to activate. Add funds via Billing, then go to Campaign Detail → Activate.

### Balance not updating after Stripe payment
Check that the Stripe success callback URL is correct (`/company/billing/success?session_id=...`). Verify the session_id matches a completed payment.
