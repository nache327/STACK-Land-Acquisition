-- MANUAL dashboard-repo migration — apply to the PORTFOLIO DASHBOARD Supabase
-- (the DB behind PORTFOLIO_DASHBOARD_DATABASE_URL), NOT ParcelLogic's DB.
--
-- Why manual: the dashboard is a separate repo/Supabase and Vercel never runs
-- its alembic (see memory: "Dashboard migrations are manual"). dashboard_push
-- writes situs_address/situs_city as of this sweep; if the columns are missing
-- the push crashes and the board darkens — so APPLY THIS BEFORE deploying the
-- dashboard_push change.
--
-- Idempotent (IF NOT EXISTS) — safe to re-run.
--
-- Apply:
--   psql "$PORTFOLIO_DASHBOARD_DATABASE_URL" -f 001_deal_prospect_situs.sql
-- (or paste into the dashboard Supabase SQL editor)

ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS situs_address TEXT;
ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS situs_city    TEXT;

-- Card UI note (dashboard repo): render situs_address as a secondary line
-- ("Site: 91 Cottontail Ln") whenever it differs (normalized, case-insensitive)
-- from the primary `address`. The primary line keeps the listing address —
-- it's the outreach address.
