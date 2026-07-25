-- MANUAL dashboard-repo migration — apply to the PORTFOLIO DASHBOARD Supabase
-- (the DB behind PORTFOLIO_DASHBOARD_DATABASE_URL), NOT ParcelLogic's DB.
--
-- Why manual: the dashboard is a separate repo/Supabase and Vercel never runs
-- its alembic (see memory: "Dashboard migrations are manual"). dashboard_push
-- writes these columns as of the 2026-07-25 audit remediation; if they are
-- missing the whole push raises inside its transaction and the board darkens —
-- so APPLY THIS BEFORE deploying the dashboard_push change.
--
-- Idempotent (IF NOT EXISTS) — safe to re-run.
--
-- Apply:
--   psql "$PORTFOLIO_DASHBOARD_DATABASE_URL" -f 002_deal_prospect_triage_context.sql
-- (or paste into the dashboard Supabase SQL editor)
--
-- WHY these columns: the board card carried score, price, acres and contacts —
-- but none of the wealth/demand facts the buy box is DEFINED by. Of the six
-- things the operator triages on (acreage band, 3-mi population >= 30k,
-- saturation as lane-routing, HNW depth, price/basis, internal consistency),
-- three were simply not on the card, and the `factors` JSON could not
-- distinguish "this factor was fine" from "this factor was never measured".
-- With these, a card answers "is this actually in a wealth pocket?" on its own.

ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS ring_median_home_value INTEGER;
ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS ring_median_hhi        INTEGER;
ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS ring_hnw_households    INTEGER;
ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS pop_3mi                INTEGER;
ALTER TABLE deal_prospect ADD COLUMN IF NOT EXISTS sqft_per_capita_3mi    NUMERIC(8,2);

-- Card UI notes (dashboard repo):
--
-- 1. NULL means UNMEASURED, never zero. Render "—" (grey), never "0" and never a
--    red ✗. Presenting unmeasured as failed is its own trust bug — the in-app
--    buy-box panel used to render an unmeasured HNW count as a hard ✗ and that
--    drove the whole panel to "Fail".
--
-- 2. Wealth context (ring_median_home_value / ring_median_hhi are the dt=10
--    drive-time ring — the same numbers the wealth-gated NEEDLE definition uses:
--    HV >= 475,000 AND HHI >= 100,000). Cards below those thresholds now carry
--    the soft_flags `ring home value below buy box` / `ring household income
--    below buy box` and sort into the Verify tier rather than Actionable. They
--    are NOT dropped, deliberately: the dt=10 rings are known-suspect
--    (tract-centroid isochrones, no TTL) so a hard gate could hide a real
--    needle. Treat "below buy box" as "check this one", not "rejected".
--
-- 3. sqft_per_capita_3mi is the storage-market saturation signal
--    (competitor sq ft per person within 3 miles): < 7 underserved, 7-10
--    borderline, >= 10 oversupplied. NULL = that county's competitor sync has
--    never run — do not paint it green/"underserved", which is exactly the bug
--    this remediation fixed on the ParcelLogic side.
--
-- 4. pop_3mi is currently a tract-centric approximation and can disagree with
--    the drawer's area-weighted Saturation panel; a per-parcel area-weighted
--    recompute is queued. Until then treat it as ±, not gospel.
