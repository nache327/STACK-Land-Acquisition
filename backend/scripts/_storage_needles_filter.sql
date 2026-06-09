-- Storage Needles dedicated digest track — filter-config rows.
-- APPLY AT DEPLOY, AFTER the daily_email.py storageVerdictMode change merges.
-- Pairs with: app/workers/daily_email.py (storageVerdictMode gate) +
-- scripts/_drafts/_storage_needles_track_design.md.
--
-- buybox_filters has NOT-NULL organization_id + use_case_id (no defaults) — the
-- INSERT clones both from the existing "Hot deals" row. Idempotent via NOT EXISTS.

-- 1. Clean dedup: the general "Hot deals" track stops listing needles
--    (they move to their own track). NULL-safe gate handles no-verdict rows.
UPDATE buybox_filters
   SET filter_json = filter_json || '{"storageVerdictMode": "exclude"}'::jsonb,
       updated_at  = now()
 WHERE name = 'Hot deals';

-- 2. New "Storage Needles" filter: same listed/score criteria as Hot deals
--    (cloned filter_json + org/use_case), gated to human-reviewed self_storage
--    permitted/conditional parcels, with a generous top-N so scarce needles
--    are never throttled.
INSERT INTO buybox_filters
  (id, organization_id, use_case_id, name, filter_json, is_default,
   daily_email_enabled, daily_email_top_n, created_at, updated_at)
SELECT gen_random_uuid(), organization_id, use_case_id, 'Storage Needles',
       (filter_json - 'storageVerdictMode') || '{"storageVerdictMode": "only"}'::jsonb,
       false, true, 20, now(), now()
  FROM buybox_filters
 WHERE name = 'Hot deals'
   AND NOT EXISTS (SELECT 1 FROM buybox_filters WHERE name = 'Storage Needles');

-- Verify:
--   SELECT name, daily_email_enabled, daily_email_top_n,
--          filter_json->>'storageVerdictMode' AS mode
--   FROM buybox_filters WHERE name IN ('Hot deals','Storage Needles');
-- Rollback:
--   DELETE FROM buybox_filters WHERE name='Storage Needles';
--   UPDATE buybox_filters SET filter_json = filter_json - 'storageVerdictMode' WHERE name='Hot deals';
