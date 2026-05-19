"""validate_pdf_zoning_ingest — post-ingest spot-check + sanity report.

Called by the operator AFTER `_upload-zoning` lands a PDF-digitized GeoJSON.
Surfaces the issues the operator can plausibly check from CLI:

  1. Distinct-code diff: does the set of `zone_code` values in zoning_districts
     match what the operator extracted from the PDF legend?
  2. Distribution check: any single zone_code dominating >70% of overlay area
     is suspicious (operator likely over-traced one district).
  3. Spot-check pull: emit 5 random parcels that received a new zone_code so
     the operator can hand-verify against the town's published map.
  4. Per-municipality rollup: how many parcels in the target town are now
     zoned vs. still NULL.

Usage:
    python -m scripts.validate_pdf_zoning_ingest \\
      --jurisdiction-id 4bf00234-... \\
      --municipality "Garfield City" \\
      --expected-codes R-1,R-1A,R-2,R-3,B-1,B-2,LM,CA,RDVT,P
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _resolve_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


async def main(args: argparse.Namespace) -> dict:
    engine = create_async_engine(_resolve_db_url())
    expected = {c.strip().upper() for c in (args.expected_codes or "").split(",") if c.strip()}
    out: dict = {
        "jurisdiction_id": str(args.jurisdiction_id),
        "municipality": args.municipality,
        "expected_codes": sorted(expected),
        "checks": {},
    }

    async with engine.connect() as conn:
        # 1) Distinct codes in zoning_districts for this jurisdiction (filtered by city if given).
        where = "jurisdiction_id = :jid"
        params: dict = {"jid": str(args.jurisdiction_id)}
        if args.municipality:
            where += " AND lower(city) = lower(:city)"
            params["city"] = args.municipality
        rows = await conn.execute(
            text(f"SELECT DISTINCT zone_code FROM zoning_districts WHERE {where} AND zone_code IS NOT NULL ORDER BY 1"),
            params,
        )
        actual = {r[0].upper() for r in rows.fetchall() if r[0]}
        missing = sorted(expected - actual) if expected else []
        unexpected = sorted(actual - expected) if expected else []
        out["checks"]["distinct_codes"] = {
            "in_db": sorted(actual),
            "missing": missing,
            "unexpected": unexpected,
            "status": "PASS" if (expected and not missing and not unexpected) else
                      ("MISSING_REFERENCE" if not expected else "FAIL"),
        }

        # 2) Distribution: any single zone_code covering >70% of overlay area?
        rows = await conn.execute(
            text(f"""
                SELECT zone_code, COUNT(*) AS n,
                       ROUND(100.0 * SUM(ST_Area(geom::geography)) /
                                     NULLIF(SUM(SUM(ST_Area(geom::geography))) OVER (), 0), 2) AS area_pct
                FROM zoning_districts
                WHERE {where} AND zone_code IS NOT NULL
                GROUP BY zone_code
                ORDER BY area_pct DESC NULLS LAST
            """),
            params,
        )
        dist = [{"code": r[0], "n": r[1], "area_pct": float(r[2] or 0)} for r in rows.fetchall()]
        max_share = max((d["area_pct"] for d in dist), default=0)
        out["checks"]["distribution"] = {
            "rows": dist,
            "max_share_pct": max_share,
            "status": "PASS" if max_share <= 70 else "WARN_DOMINANT_CODE",
        }

        # 3) Spot-check: 5 random parcels with a non-null zone_code in this town.
        params_p = {"jid": str(args.jurisdiction_id)}
        muni_filter = ""
        if args.municipality:
            muni_filter = " AND lower(city) = lower(:city)"
            params_p["city"] = args.municipality
        rows = await conn.execute(
            text(f"""
                SELECT id, address, city, zone_code,
                       ST_Y(ST_Centroid(geom))::float AS lat,
                       ST_X(ST_Centroid(geom))::float AS lng
                FROM parcels
                WHERE jurisdiction_id = :jid AND zone_code IS NOT NULL {muni_filter}
                ORDER BY random() LIMIT 5
            """),
            params_p,
        )
        out["checks"]["spot_check_parcels"] = [
            {"id": str(r[0]), "address": r[1], "city": r[2], "zone_code": r[3],
             "lat": r[4], "lng": r[5]}
            for r in rows.fetchall()
        ]

        # 4) Per-municipality rollup.
        rows = await conn.execute(
            text(f"""
                SELECT COUNT(*) AS total,
                       COUNT(zone_code) AS with_zone
                FROM parcels
                WHERE jurisdiction_id = :jid {muni_filter}
            """),
            params_p,
        )
        rec = rows.fetchone()
        total = rec[0] if rec else 0
        with_zone = rec[1] if rec else 0
        out["checks"]["coverage"] = {
            "total_parcels": total,
            "parcels_with_zone_code": with_zone,
            "pct": round(100 * with_zone / total, 2) if total else 0,
        }

    await engine.dispose()

    # Overall status
    statuses = [c.get("status") for c in out["checks"].values() if isinstance(c, dict) and "status" in c]
    out["overall_status"] = "PASS" if all(s == "PASS" for s in statuses) else \
                            "WARN" if any(s and s.startswith("WARN") for s in statuses) else \
                            "FAIL"
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--jurisdiction-id", required=True, type=uuid.UUID)
    p.add_argument("--municipality", help="parcels.city filter; omit for jurisdiction-wide")
    p.add_argument("--expected-codes", help="comma-separated zone codes from the PDF legend")
    args = p.parse_args()
    result = asyncio.run(main(args))
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.exit(0 if result.get("overall_status") in ("PASS", "WARN") else 2)
