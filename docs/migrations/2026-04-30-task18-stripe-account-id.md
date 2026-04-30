# Schema migration — `users.stripe_account_id`

**Date**: 2026-04-30 10:42 IST
**Applied to**: production Supabase (`aws-1-us-east-1.pooler.supabase.com:6543/postgres`)
**Sequence**: schema applied via `ALTER TABLE` BEFORE the code referencing the column was deployed (avoids 5xx during the deploy gap).

## What changed

Added a nullable VARCHAR(255) column to the `users` table:

```sql
ALTER TABLE users ADD COLUMN stripe_account_id VARCHAR(255);
```

Verified post-apply:
```
column_name: stripe_account_id, data_type: character varying, is_nullable: YES
```

## Why

`server/app/services/payments.py:238-240` had a TODO `# placeholder until user Stripe onboarding` referring to the missing field. `POST /api/users/me/payout` had no Stripe-Connect-required check — Task #19's spec requires "Connect your bank account first" rejection, but the field needed for that check didn't exist on the User model.

Discovered while implementing Task #18 subtask 18.6 (`test_users_routes.py`). The agent added the column to `server/app/models/user.py` AND the validation in `server/app/routers/users.py`. Tests confirm both the success path (user has `stripe_account_id` set → payout creates row in `processing` status) and the failure path (user has no `stripe_account_id` → 400 with "Connect your bank account").

## Code changes (committed alongside this migration doc)

- `server/app/models/user.py` — added `stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)` after the existing fields.
- `server/app/routers/users.py` `request_payout` — added pre-validation block that raises HTTP 400 if `user.stripe_account_id` is None.

## Compatibility

- Existing rows: column is NULL for all existing users (default for nullable column on Postgres).
- Existing payout route behavior: unchanged for users with `stripe_account_id == None` BEFORE this change (route would have proceeded; now it rejects with 400). No prod users currently have payouts in flight (Task #19 not live), so no behavioral regression.
- Future Stripe Connect onboarding (Task #19) writes to this column when a user completes onboarding.

## Alembic implications

`server/alembic/versions/` is still empty (Task #45 pending — baseline migration). When Task #45 generates the baseline, it will pick up `stripe_account_id` automatically since the column is now in production schema. No back-fill or special handling needed.

## Rollback

If needed:
```sql
ALTER TABLE users DROP COLUMN stripe_account_id;
```

Code rollback: revert commits touching `server/app/models/user.py` and `server/app/routers/users.py`. Tests in `tests/server/test_users_routes.py` would need updating to remove the `stripe_account_id` references.

Not expected to be needed.
