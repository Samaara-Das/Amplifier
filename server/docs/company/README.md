# Amplifier Company Dashboard — Documentation

## Documents

| Document | Description |
|----------|-------------|
| [Concept Document](CONCEPT.md) | What the company dashboard is, why it exists, target users, feature scope, user flows, security, and success criteria |
| [Architecture](ARCHITECTURE.md) | System architecture, file structure, auth flow, campaign creation flow, budget flow, data model relationships, AI integration, payment integration, and design decisions |
| [User Guide](USER_GUIDE.md) | Step-by-step guide to every page — dashboard, campaigns, wizard, detail, influencers, billing, analytics, settings — with common workflows |
| [API Reference](API_REFERENCE.md) | Complete reference of all 21 routes — GET pages with parameters, POST actions with form fields and effects, AI generation JSON schema, file upload specs |
| [Deployment Guide](DEPLOYMENT.md) | Local setup, production deployment (Vercel + Supabase), service dependencies (Stripe, Supabase Storage, Gemini), configuration reference, security checklist, troubleshooting |
| [Changelog](CHANGELOG.md) | Version history — v1.0 (initial) and v2.0 (modular rebuild with new pages) |

## Quick Start

```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000/company/login
# Register with any email/password
# Add funds via Billing (test mode credits instantly)
# Create your first campaign with the AI wizard
```

## System at a Glance

- **8 pages**: Dashboard, Campaigns, Create Campaign, Campaign Detail, Influencers, Billing, Analytics, Settings
- **21 routes**: 10 GET pages + 11 POST actions
- **AI-powered**: 4-step campaign wizard with Gemini API (URL crawling + brief generation)
- **Stripe integration**: Real payments in production, instant credit in test mode
- **File uploads**: Images and documents to Supabase Storage
- **Server-side pagination**: Campaigns list paginates at 15 per page
- **Search & filter**: Campaign search by title, filter by status, sort by date/budget/title
- **Cross-campaign analytics**: Influencer performance, platform ROI, monthly spend trends
