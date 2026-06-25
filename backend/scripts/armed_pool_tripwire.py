"""Armed-pool tripwire — alert when a NEW listing lands on a verdicted needle parcel.

The "Rye B-5 tripwire" formalized: every parcel that carries a human permitted/conditional self-storage
verdict AND clears the SN size/wealth gates is "armed." When a current CoStar listing matches such a
parcel and it hasn't been alerted yet, fire a focused tripwire email.

DESIGN NOTES (deliberate, vs the original spec):
- ALIGNED TO THE DIGEST (catch #41): the query mirrors daily_email `_top_parcels_for_filter` eligibility
  exactly so it never raises a signal the digest wouldn't act on. The three gates the digest applies are
  enforced here too: `l.match_confidence >= 0.85` (listing↔parcel trust floor), `pbs.score >= 70`
  (`_MIN_SCORE_LISTED`), and a `notified_listings` 14-day cross-channel dedup (real-time alerts).
- DEDUP via the EXISTING `parcel_buybox_scores.notified_at` PLUS `notified_listings` (catch #41) — NOT a
  new `tripwire_notifications` table. Reason: the daily Storage-Needles digest also reads/stamps
  notified_at and consults notified_listings. Sharing both means the tripwire and the digest never
  DOUBLE-email the same needle. A separate table would let both fire. (No migration.)
- ARMED POOL IS DYNAMIC, not a hardcoded 186-parcel snapshot: any (jurisdiction, muni, zone) with a
  human_reviewed perm/conditional verdict auto-joins the pool as future pastes land. No edit needed to extend.
- OVERLAP: this is functionally a faster-cadence, armed-pool-scoped version of `_top_parcels_for_filter` /
  the daily digest. Run it on a 6h schedule (or post-CoStar-pull) as a supplement; if you'd rather not run a
  second email channel, just rely on the daily digest (same condition, 24h cadence). See PR description.

USAGE:
  python scripts/armed_pool_tripwire.py            # DRY RUN — print armed-pool listings that would fire
  python scripts/armed_pool_tripwire.py --send     # send tripwire email + stamp notified_at (PROD only;
                                                    # needs RESEND_API_KEY + digest recipient in env)
"""
import asyncio
import sys

import asyncpg

SN_FILTER_ID = "72409acf-3712-4761-a156-50c2329ad35b"  # Storage Needles

# Armed + newly-listed + un-fired. Mirrors the SN hard filter; verdict join prefers muni-specific then
# county-default (matches buybox_scoring); notified_at IS NULL = not yet alerted by tripwire or digest.
ARMED_SQL = """
SELECT j.name jurisdiction, p.id parcel_id, p.city, p.zoning_code, p.apn,
       l.id listing_id, l.address, round(p.acres::numeric,2) acres, l.sale_price,
       l.listing_broker_company broker_co, l.listing_broker_contact broker,
       v.self_storage::text verdict, pbs.score,
       r.median_hhi hhi, r.median_home_value hv, r.hnw_households hnw,
       ST_Y(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) lat,
       ST_X(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) lng,
       (SELECT id FROM jobs WHERE jurisdiction_id=j.id AND status='ready'
        ORDER BY finished_at DESC NULLS LAST, created_at DESC LIMIT 1) job_id
FROM parcels p
JOIN jurisdictions j ON j.id = p.jurisdiction_id
JOIN forsale_listings l ON l.matched_parcel_id = p.id AND l.is_current = true
                       AND l.match_confidence >= 0.85   -- catch #41: digest trust floor
JOIN parcel_ring_metrics r ON r.parcel_id = p.id AND r.drive_time_minutes = 10
LEFT JOIN parcel_buybox_scores pbs ON pbs.parcel_id = p.id AND pbs.buybox_filter_id = $1
JOIN LATERAL (
    SELECT m.self_storage FROM zone_use_matrix m
    WHERE m.jurisdiction_id = p.jurisdiction_id AND m.zone_code = p.zoning_code
      AND m.deleted_at IS NULL AND m.human_reviewed = true
      AND (m.municipality = p.city OR m.municipality IS NULL)
    ORDER BY (m.municipality = p.city) DESC NULLS LAST LIMIT 1
) v ON true
WHERE v.self_storage IN ('permitted','conditional')
  AND p.acres BETWEEN 1.5 AND 15
  AND r.median_hhi >= 100000 AND r.hnw_households >= 4400
  AND r.median_home_value >= 475000 AND r.population >= 50000
  AND (l.sale_price IS NULL OR l.sale_price <= 7500000)
  AND (l.sale_price IS NULL OR p.acres = 0 OR l.sale_price / p.acres <= 2000000)
  AND (pbs.notified_at IS NULL)              -- not yet alerted (by tripwire OR digest)
  AND pbs.score >= 70                        -- catch #41: digest _MIN_SCORE_LISTED floor
  AND NOT EXISTS (                           -- catch #41: cross-channel (real-time alert) dedup
        SELECT 1 FROM notified_listings nl
         WHERE nl.filter_id = $1 AND nl.parcel_id = p.id
           AND nl.notified_at > now() - INTERVAL '14 days'
  )
ORDER BY pbs.score DESC NULLS LAST, l.sale_price
"""


def _row_html(r, base):
    seg = r["job_id"] or r["jurisdiction"]
    link = f"{base.rstrip('/')}/dashboard/{seg}?parcel_id={r['parcel_id']}"
    if r["lat"] is not None and r["lng"] is not None:
        link += f"&lat={r['lat']:.6f}&lng={r['lng']:.6f}"
    price = f"${int(r['sale_price']):,}" if r["sale_price"] else "(unpriced)"
    broker = " / ".join(x for x in (r["broker_co"], r["broker"]) if x) or "—"
    return (f"<div style='border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin:8px 0'>"
            f"<div style='font-size:15px;font-weight:700'>{r['address']}</div>"
            f"<div style='color:#475569'>{r['city']} · zone {r['zoning_code']} · {r['verdict']}</div>"
            f"<div style='margin-top:4px'>🏷️ {price} · {r['acres']} ac · score {r['score']}</div>"
            f"<div style='font-size:13px'>Broker: <strong>{broker}</strong></div>"
            f"<div style='font-size:12px;color:#334155'>ring HHI ${int(r['hhi']):,} · HV ${int(r['hv']):,} · HNW {r['hnw']}</div>"
            f"<a href='{link}' style='color:#0369a1;font-size:13px'>Open in dashboard →</a></div>")


async def main(send: bool):
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        rows = await con.fetch(ARMED_SQL, SN_FILTER_ID)
        print(f"armed-pool tripwire: {len(rows)} new un-fired listing(s) on armed parcels")
        for r in rows:
            print(f"  {str(r['jurisdiction'] or '')[:20]:20} {str(r['city'] or '?')[:22]:22} "
                  f"{str(r['zoning_code'] or '')[:5]:5} {str(r['address'] or '')[:30]:30} "
                  f"${r['sale_price']} score={r['score']} [{r['verdict']}]")
        if not rows:
            return
        if not send:
            print("\n(dry run — pass --send on prod to email + stamp notified_at)")
            return
        # PROD send path: reuse the digest/alert Resend infra + stamp notified_at (shared dedup).
        from app.services.email_resend import send_email
        from app.config import settings
        base = settings.digest_dashboard_base_url
        body = "".join(_row_html(r, base) for r in rows)
        html = f"<h2>🎯 Armed-Pool Tripwire — {len(rows)} new listing(s)</h2>{body}"
        text = "\n".join(f"{r['address']} — {r['city']} {r['zoning_code']} ${r['sale_price']}" for r in rows)
        subj = (f"🎯 ARMED POOL TRIPWIRE — {rows[0]['address']} just listed in {rows[0]['city']}"
                if len(rows) == 1 else f"🎯 ARMED POOL TRIPWIRE — {len(rows)} new armed-pool listings")
        msg_id = await send_email(to=settings.digest_default_recipient, subject=subj, text=text, html=html)
        await con.execute(
            "UPDATE parcel_buybox_scores SET notified_at=now() WHERE buybox_filter_id=$1 AND parcel_id=ANY($2::int[]) AND notified_at IS NULL",
            SN_FILTER_ID, [r["parcel_id"] for r in rows])
        print(f"\nsent tripwire (resend_id={msg_id}); stamped notified_at on {len(rows)} parcels")
    finally:
        await con.close()


asyncio.run(main("--send" in sys.argv))
