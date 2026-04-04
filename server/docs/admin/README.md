# Amplifier Admin Dashboard — Documentation

## Documents

| Document | Description |
|----------|-------------|
| [Concept Document](CONCEPT.md) | What the admin dashboard is, why it exists, its principles, feature scope, security model, and success criteria |
| [Architecture](ARCHITECTURE.md) | System architecture, file structure, auth flow, data flow, pagination, template structure, database models, and design decisions |
| [User Guide](USER_GUIDE.md) | Step-by-step guide to every page and workflow — how to manage users, companies, campaigns, finances, fraud, reviews, and read the audit log |
| [API Reference](API_REFERENCE.md) | Complete reference of all 34 routes — GET pages with query parameters, POST actions with parameters and effects, and the full audit action catalog |
| [Design System](DESIGN_SYSTEM.md) | Color palette, typography, component library (badges, buttons, cards, tables, forms, alerts), layout structure, icon set, and status color mapping |
| [Deployment Guide](DEPLOYMENT.md) | Local development setup, production deployment (Vercel + Supabase), SQL migration scripts, configuration reference, security checklist, and troubleshooting |
| [Changelog](CHANGELOG.md) | Version history — what changed, what was added, what was fixed, what was removed |

## Quick Start

```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000/admin/login (password: admin)
```

## System at a Glance

- **10 pages**: Overview, Users, Companies, Campaigns, Financial, Fraud & Trust, Analytics, Review Queue, Settings, Audit Log
- **34 routes**: 14 GET pages + 20 POST actions
- **3 detail pages**: User, Company, Campaign — each with tabbed drill-down views
- **2 new models**: AuditLog, ContentScreeningLog
- **Full audit trail**: Every admin action logged with timestamp, IP, and context
- **Server-side pagination**: All list pages paginate at 25-30 items
- **Search & filter**: Every list page supports text search and status filters
