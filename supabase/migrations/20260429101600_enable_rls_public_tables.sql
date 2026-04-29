-- Enable Row-Level Security on all public tables.
--
-- Context: Supabase auto-exposes every public-schema table via PostgREST.
-- With RLS disabled, anyone holding the public anon key can read/write the table.
-- The Amplifier server connects as the `postgres` role (rolbypassrls=true) via the
-- transaction pooler and SQLAlchemy, so it bypasses RLS entirely. We don't use
-- PostgREST or the anon key anywhere (only Supabase Storage with the service role
-- key, which also bypasses RLS).
--
-- Effect: enabling RLS without policies = deny-all for anon/authenticated PostgREST.
-- Server (postgres role) and Storage (service_role) continue to work unchanged.

ALTER TABLE public.audit_log                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_assignments     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_invitation_log  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_posts           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaigns                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companies                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_transactions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.content_screening_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.content_screening_logs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metrics                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payouts                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.penalties                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.posts                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users                    ENABLE ROW LEVEL SECURITY;

-- Belt-and-suspenders: also FORCE RLS so even the table owner is subject to it
-- when not bypassing. (postgres role still bypasses via rolbypassrls.)
ALTER TABLE public.audit_log                FORCE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_assignments     FORCE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_invitation_log  FORCE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_posts           FORCE ROW LEVEL SECURITY;
ALTER TABLE public.campaigns                FORCE ROW LEVEL SECURITY;
ALTER TABLE public.companies                FORCE ROW LEVEL SECURITY;
ALTER TABLE public.company_transactions     FORCE ROW LEVEL SECURITY;
ALTER TABLE public.content_screening_log    FORCE ROW LEVEL SECURITY;
ALTER TABLE public.content_screening_logs   FORCE ROW LEVEL SECURITY;
ALTER TABLE public.metrics                  FORCE ROW LEVEL SECURITY;
ALTER TABLE public.payouts                  FORCE ROW LEVEL SECURITY;
ALTER TABLE public.penalties                FORCE ROW LEVEL SECURITY;
ALTER TABLE public.posts                    FORCE ROW LEVEL SECURITY;
ALTER TABLE public.users                    FORCE ROW LEVEL SECURITY;
