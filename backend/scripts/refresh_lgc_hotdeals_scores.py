"""Fresh-score the currently-listed parcels for the LGC email lane.

The LGC Hot deals digest is ``requireListed`` — it only surfaces parcels with a
current CoStar listing. Those parcels' scores must reflect CURRENT data (a newly
listed parcel needs its listing boost; re-grounding changes the verdict), but the
per-ingest auto-scorer only scores DEFAULT filters, so a non-default email filter
would drift. This re-scores every currently-listed parcel for the LGC
email-enabled requireListed filter(s) through the canonical scorer path
(score_for_parcel + the real upsert) — never a stale copy. Idempotent; cheap
(only listed parcels). Run nightly before the digest.

USAGE (from backend/):  python scripts/refresh_lgc_hotdeals_scores.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import (  # noqa: E402
    ParcelInputs, _UPSERT_SQL, _has_ss_overlay, score_for_parcel,
)
from app.services.use_verdicts import LGC_SLUG, verdict_expr  # noqa: E402

_INPUTS_SQL = f"""
SELECT p.id AS parcel_id, {verdict_expr(LGC_SLUG)} AS storage_permission,
       zum.classification_source AS classification_source, zum.confidence AS verdict_confidence,
       zum.human_reviewed AS human_reviewed, p.acres, p.aadt, p.in_flood_zone, p.in_wetland,
       p.has_structure, p.overlay_tags AS overlay_tags,
       prm.homes_over_1m, prm.homes_over_2m, prm.homes_over_5m,
       lst.source AS listing_source, lst.sale_price AS listing_sale_price, lst.days_on_market AS listing_dom
FROM parcels p
LEFT JOIN LATERAL (SELECT self_storage, mini_warehouse, light_industrial,
       classification_source::text AS classification_source, confidence, human_reviewed
   FROM zone_use_matrix WHERE jurisdiction_id=p.jurisdiction_id AND zone_code=p.zoning_code
     AND (municipality IS NULL OR municipality=p.city) AND deleted_at IS NULL
   ORDER BY (municipality IS NULL) ASC LIMIT 1) zum ON true
LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=$2::int
LEFT JOIN LATERAL (SELECT source, sale_price, days_on_market FROM forsale_listings
   WHERE matched_parcel_id=p.id AND is_current=true AND match_confidence>=0.85
   ORDER BY last_seen_at DESC LIMIT 1) lst ON true
WHERE p.id = ANY($1::bigint[])
"""


def _inputs(r) -> ParcelInputs:
    return ParcelInputs(
        parcel_id=r["parcel_id"], storage_permission=r["storage_permission"],
        acres=float(r["acres"]) if r["acres"] is not None else None, aadt=r["aadt"],
        in_flood_zone=bool(r["in_flood_zone"]), in_wetland=bool(r["in_wetland"]),
        has_structure=r["has_structure"], homes_over_1m=r["homes_over_1m"],
        homes_over_2m=r["homes_over_2m"], homes_over_5m=r["homes_over_5m"],
        listing_source=r["listing_source"],
        listing_sale_price=(float(r["listing_sale_price"]) if r["listing_sale_price"] is not None else None),
        listing_dom=r["listing_dom"], classification_source=r["classification_source"],
        confidence=(float(r["verdict_confidence"]) if r["verdict_confidence"] is not None else None),
        human_reviewed=bool(r["human_reviewed"]), verdict_matched=r["storage_permission"] is not None,
        overlay_ss=_has_ss_overlay(r["overlay_tags"]),
    )


async def main() -> int:
    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=300)
    try:
        await conn.execute("SET statement_timeout = 0")
        # LGC email-enabled, requireListed filter(s) — the lane that needs fresh
        # listed-parcel scores. Resolved (not hardcoded) so it tracks config.
        filters = await conn.fetch(
            """
            SELECT bf.id, bf.name, bf.filter_json
              FROM buybox_filters bf JOIN use_cases uc ON uc.id = bf.use_case_id
             WHERE uc.slug = $1 AND bf.daily_email_enabled
               AND COALESCE((bf.filter_json->>'requireListed')::bool, false)
            """,
            LGC_SLUG,
        )
        if not filters:
            print("refresh_lgc_hotdeals: no LGC email-enabled requireListed filter — nothing to do")
            return 0

        listed = [r["pid"] for r in await conn.fetch(
            "SELECT DISTINCT matched_parcel_id pid FROM forsale_listings "
            "WHERE is_current=true AND match_confidence>=0.85 AND matched_parcel_id IS NOT NULL")]
        rows = await conn.fetch(_INPUTS_SQL, listed, 10)
        print(f"refresh_lgc_hotdeals: {len(listed)} listed parcel(s), {len(filters)} filter(s)")

        for f in filters:
            fj = json.loads(f["filter_json"]) if isinstance(f["filter_json"], str) else (f["filter_json"] or {})
            drive = int(fj.get("driveTimeMinutes") or 10)
            src = rows if drive == 10 else await conn.fetch(_INPUTS_SQL, listed, drive)
            scored = []
            for r in src:
                s = score_for_parcel(_inputs(r), fj)
                scored.append((s.parcel_id, f["id"], s.score, s.tier, json.dumps(s.factors),
                               s.lead_eligible, s.gate_reason, s.verdict_basis))
            for i in range(0, len(scored), 5000):
                await conn.executemany(_UPSERT_SQL, scored[i:i + 5000])
            print(f"  {f['name']!r}: fresh-scored {len(scored)} listed parcel(s)")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
