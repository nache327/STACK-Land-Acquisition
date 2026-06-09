-- Storage Needles dedicated digest track — filter-config rows.
-- APPLY AT DEPLOY, AFTER the daily_email.py storageVerdictMode change merges.
-- NOT run by the dry-run/design work. Review against prod buybox_filters first.
--
-- Pairs with: app/workers/daily_email.py (storageVerdictMode gate) +
-- scripts/_drafts/_storage_needles_track_design.md.

-- 1. Clean dedup: the general "Hot deals" track stops listing needles
--    (they move to their own track). NULL-safe gate handles no-verdict rows.
UPDATE buybox_filters
   SET filter_json = filter_json || '{"storageVerdictMode": "exclude"}'::jsonb,
       updated_at  = now()
 WHERE name = 'Hot deals';

-- 2. New "Storage Needles" filter: same listed/score criteria as Hot deals,
--    but gated to human-reviewed self_storage permitted/conditional parcels,
--    with its own (generous) top-N so scarce needles are never throttled.
--    Clones Hot deals' filter_json so the score/acre/price criteria match,
--    then sets the gate + top_n. requireListed stays true.
INSERT INTO buybox_filters (id, name, filter_json, daily_email_enabled, daily_email_top_n, created_at, updated_at)
SELECT gen_random_uuid(),
       'Storage Needles',
       (filter_json - 'storageVerdictMode') || '{"storageVerdictMode": "only"}'::jsonb,
       true,
       20,
       now(), now()
  FROM buybox_filters
 WHERE name = 'Hot deals';

-- NOTE: verify buybox_filters has no other NOT NULL columns (e.g. owner/tenant
-- FK) before applying; if so add them to the INSERT. Confirm 'Hot deals'
-- filter_json carries the intended maxTotalPrice/maxAcres for the storage
-- thesis (consider allowing up to ~$10M for a wealth-pocket industrial parcel).
