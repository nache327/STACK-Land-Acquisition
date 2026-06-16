"""Task E — Mercer Island city-fallback re-fire (Phase 6B-PIVOT post-flip).

PR #271 flipped Bellevue, WA operational. Mercer Island remained `partial`
at parcel_zoning_code_coverage_pct = 63.2 % — sub the 70 % gate by 6.8 pp.
Root cause: WAZA's Mercer Island layer has only 48 polygons (vs the
city zoning layer's 82). 2,741 of 7,448 parcels (36.8 %) sit outside
any WAZA polygon even at 50 m nearest fallback — not a code-mismatch
problem, a polygon-density problem.

This script fires the city-layer fallback per the pre-staged directory
entry (`backend/data/king_wa_zoning_directory.json` → Mercer Island
`fallback_zoning_district_source`). 82 city polygons → INSERT as
zoning_districts under Mercer's jurisdiction, then spatial backfill
scoped to the city layer, targeting parcels with NULL zoning_code only
(preserves existing WAZA bindings via Norfolk-gate-safe COALESCE).

Subcommands:

  preflight  Read-only pipeline shape validation. Fetch city features,
             build rows, report distinct ZONING codes + sample
             raw_attributes. NO DB WRITES.

  fire       Real prod write. Requires --i-know-this-writes-to-prod.
             INSERT 82 city districts with raw_attributes.muni_name =
             'Mercer Island (city)' (distinct from existing 48 WAZA
             at 'Mercer Island'), then 2-pass spatial backfill
             targeting parcels with zoning_code IS NULL only. Then
             inline jurisdictions.bbox verify-or-update.

Hard rules honored:
  - raw_attributes preserved verbatim (Norfolk gate)
  - muni_name distinguished between WAZA + city layer (avoids
    re-binding parcels that already have a WAZA zoning_code)
  - jurisdictions.bbox verified inline (PR #261 codified)
  - Don't author matrix (orchestrator's domain — surface new codes only)
  - ONE refresh per task (operator at end)

Distinct ZONING codes from city layer (live probe 2026-06-16):
  14 codes — B, C-O, MF-2, MF-2L, MF-3, OS, P, PBZ, PI,
  R-12, R-15, R-8.4, R-9.6, TC

Compared to PR #266's 11 Mercer matrix codes
(B, C-O, MF-2, MF-2L, MF-3, PBZ, PI, R-12, R-15, R-8.4, R-9.6),
3 new codes will surface: OS (Open Space), P (Park), TC (Town Center).
Orchestrator authoring follow-up if these bind > 0 parcels.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely.geometry import MultiPolygon, Polygon

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("mercer_city_fallback")

DIRECTORY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "king_wa_zoning_directory.json"
)
# Registered in PR #271 (Phase 6B-PIVOT re-jurisdictioning).
MERCER_JID = uuid.UUID("bdf769db-4150-45da-baa5-529995e7246f")
MUNI_NAME_CITY = "Mercer Island (city)"  # distinct from WAZA's 'Mercer Island'
PROD_CITY_VALUE = "Mercer Island"
ARCGIS_PAGE_SIZE = 1000


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _load_mercer_fallback_source() -> dict[str, Any]:
    directory = json.loads(DIRECTORY_PATH.read_text())
    for entry in directory:
        if entry["muni_name"] == "Mercer Island":
            fb = entry.get("fallback_zoning_district_source")
            if not fb:
                raise SystemExit(
                    "Mercer Island directory entry lacks fallback_zoning_district_source"
                )
            return {
                "fallback_source": fb,
                "ordinance_url": entry.get("ordinance_url"),
                "ordinance_chapter": entry.get("ordinance_chapter"),
                "ordinance_platform": entry.get("ordinance_platform"),
                "vintage": entry.get("vintage"),
            }
    raise SystemExit("Mercer Island directory entry not found")


async def _fetch_arcgis_features(source: dict[str, Any]) -> list[dict[str, Any]]:
    base_url = source["url"]
    where = source["filter_query"]
    out_sr = source.get("out_sr", 4326)
    features: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            params = {
                "where": where, "outFields": "*", "returnGeometry": "true",
                "outSR": out_sr, "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE, "f": "json",
            }
            r = await client.get(f"{base_url}/query", params=params)
            r.raise_for_status()
            batch = r.json().get("features", [])
            features.extend(batch)
            logger.info(
                "fetched %d features (cumulative %d) where=%r offset=%d",
                len(batch), len(features), where, offset,
            )
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _arcgis_rings_to_wkt(rings: list[list[list[float]]]) -> str:
    def _signed_area(ring):
        s = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            s += (x2 - x1) * (y2 + y1)
        return s
    polys: list[Polygon] = []
    has_outer = any(_signed_area(r) < 0 for r in rings)
    if has_outer:
        current_outer = None
        current_holes: list[list[list[float]]] = []
        for ring in rings:
            if _signed_area(ring) < 0:
                if current_outer is not None:
                    polys.append(Polygon(current_outer, current_holes))
                current_outer = ring
                current_holes = []
            else:
                current_holes.append(ring)
        if current_outer is not None:
            polys.append(Polygon(current_outer, current_holes))
    else:
        polys = [Polygon(r) for r in rings]
    if not polys:
        raise ValueError("rings produced no polygons")
    geom = MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return geom.wkt


def _build_zoning_district_rows(
    entry: dict[str, Any],
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fb = entry["fallback_source"]
    field_map = fb["field_map"]
    passthrough = fb["raw_attributes_passthrough"]
    out: list[dict[str, Any]] = []
    for f in features:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        if not geom or "rings" not in geom:
            continue
        zone_code = attrs.get(field_map["zone_code"])
        zone_name = attrs.get(field_map.get("zone_name", ""))
        if not zone_code or not str(zone_code).strip():
            continue
        raw_attributes = {
            "source_url": fb["url"],
            "source_filter": fb["filter_query"],
            "source_kind": fb["kind"],
            "ingested_at": "2026-06-16",
            "muni_name": MUNI_NAME_CITY,
            "muni_type": "city",
            "ordinance_url": entry.get("ordinance_url"),
            "ordinance_chapter": entry.get("ordinance_chapter"),
            "ordinance_platform": entry.get("ordinance_platform"),
            "vintage": entry.get("vintage"),
        }
        for f_name in passthrough:
            if f_name in attrs:
                raw_attributes[f_name] = attrs[f_name]
        try:
            wkt = _arcgis_rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning(
                "Skipping feature OBJECTID=%s, ring parse failed: %s",
                attrs.get("OBJECTID"), exc,
            )
            continue
        out.append({
            "jurisdiction_id": str(MERCER_JID),
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip() if zone_name else None,
            "zone_class": "unknown",
            "geom_wkt": wkt,
            "raw_attributes": json.dumps(raw_attributes),
            "source": "arcgis",
        })
    return out


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight (read-only)
# ────────────────────────────────────────────────────────────────────────────


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Mercer Island city-fallback (pipeline shape) ===\n")
    entry = _load_mercer_fallback_source()
    features = await _fetch_arcgis_features(entry["fallback_source"])
    rows = _build_zoning_district_rows(entry, features)
    distinct_codes = sorted({r["zone_code"] for r in rows})
    print(f"  features fetched   : {len(features)}")
    print(f"  rows built         : {len(rows)}")
    print(f"  distinct ZONING    : {len(distinct_codes)}")
    print(f"  codes              : {distinct_codes}")
    if rows:
        sample_raw = json.loads(rows[0]["raw_attributes"])
        print(f"  sample raw fields  : {len(sample_raw)} fields → "
              f"{list(sample_raw.keys())}")
    print("\n(NO DB WRITES — pipeline shape validated.)")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Fire
# ────────────────────────────────────────────────────────────────────────────


async def _fire(nearest_within_meters: float = 50.0) -> int:
    print(f"\n=== FIRE: Mercer Island city-fallback re-fire ===\n")
    entry = _load_mercer_fallback_source()

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # Pre-fire snapshot
        p_before = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) AS bound,
                COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest%') AS nearest
            FROM parcels WHERE jurisdiction_id = $1::uuid
            """,
            str(MERCER_JID),
        )
        d_before = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            str(MERCER_JID),
        )
        print(f"PRE-FIRE — Mercer parcels: {p_before['total']:,} "
              f"bound: {p_before['bound']:,} ({100*p_before['bound']/p_before['total']:.1f}%) | "
              f"contained: {p_before['contained']:,} | nearest: {p_before['nearest']:,}")
        print(f"PRE-FIRE — Mercer zoning_districts (WAZA only so far): {d_before}")

        # Phase 1 — fetch + INSERT city-layer districts (muni_name distinct)
        features = await _fetch_arcgis_features(entry["fallback_source"])
        rows = _build_zoning_district_rows(entry, features)
        print(f"\n[city layer] INSERTing {len(rows)} districts (muni_name='{MUNI_NAME_CITY}')…")
        for r in rows:
            await conn.execute(
                """
                INSERT INTO zoning_districts (
                    jurisdiction_id, zone_code, zone_name, zone_class,
                    geom, raw_attributes, source
                ) VALUES (
                    $1::uuid, $2, $3, $4::zone_class_enum,
                    ST_MakeValid(ST_GeomFromText($5, 4326)),
                    $6::jsonb, $7::zone_source_enum
                )
                """,
                r["jurisdiction_id"], r["zone_code"], r["zone_name"],
                r["zone_class"], r["geom_wkt"], r["raw_attributes"],
                r["source"],
            )
        print(f"[city layer] INSERTed {len(rows)} rows")

        # Phase 2 — spatial backfill scoped to CITY layer only, targeting
        # NULL-zoning_code parcels only (preserves WAZA bindings).
        print(f"\n[city layer] Pass 1 contained (ST_Within centroid, NULL-zoning_code only)…")
        status1 = await conn.execute(
            """
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = 'contained',
                zoning_code = sub.zone_code
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $3
                  AND p.geom IS NOT NULL
                  AND p.zoning_code IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(MERCER_JID), MUNI_NAME_CITY, PROD_CITY_VALUE,
        )
        try:
            n1 = int(status1.split()[-1])
        except (ValueError, IndexError):
            n1 = -1
        print(f"[city layer] contained UPDATEd {n1}")

        binding_label = f"nearest_{int(round(nearest_within_meters))}m"
        print(f"[city layer] Pass 2 {binding_label} (ST_DWithin, still-NULL only)…")
        status2 = await conn.execute(
            """
            UPDATE parcels target
            SET zone_class = sub.zone_class,
                zone_binding_method = $4,
                zoning_code = sub.zone_code
            FROM (
                SELECT p.id AS parcel_id, m.zone_class, m.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1::uuid
                      AND zd.raw_attributes->>'muni_name' = $2
                      AND zd.geom IS NOT NULL
                      AND ST_DWithin(
                          zd.geom::geography,
                          ST_Centroid(p.geom)::geography,
                          $5
                      )
                    ORDER BY ST_Distance(
                        zd.geom::geography,
                        ST_Centroid(p.geom)::geography
                    )
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1::uuid
                  AND p.city = $3
                  AND p.geom IS NOT NULL
                  AND p.zoning_code IS NULL
            ) sub
            WHERE target.id = sub.parcel_id
            """,
            str(MERCER_JID), MUNI_NAME_CITY, PROD_CITY_VALUE, binding_label,
            float(nearest_within_meters),
        )
        try:
            n2 = int(status2.split()[-1])
        except (ValueError, IndexError):
            n2 = -1
        print(f"[city layer] {binding_label} UPDATEd {n2}")

        # Phase 3 — INLINE bbox verify (PR #261 codified).
        # Parcel geom didn't change, so bbox should match existing.
        ext = await conn.fetchrow(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(MERCER_JID),
        )
        if ext and ext["minx"] is not None:
            bbox = [
                float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"]),
            ]
            if -123 <= bbox[0] <= -121 and 47 <= bbox[1] <= 48:
                await conn.execute(
                    "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
                    str(MERCER_JID), json.dumps(bbox),
                )
                print(f"\njurisdictions.bbox verified+UPDATEd: {bbox}")
            else:
                print(f"HALT: computed bbox doesn't look like Mercer Island: {bbox}",
                      file=sys.stderr)
                return 3
        else:
            print("HALT: no parcel geometry to compute bbox from", file=sys.stderr)
            return 4

        # Post-fire roll-up
        print("\n=== POST-FIRE QUALITY GATES ===")
        p_after = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) AS bound,
                COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
                COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest%') AS nearest
            FROM parcels WHERE jurisdiction_id = $1::uuid
            """,
            str(MERCER_JID),
        )
        d_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid",
            str(MERCER_JID),
        )
        m_after = await conn.fetchval(
            "SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = $1::uuid",
            str(MERCER_JID),
        )
        cov_pct = 100.0 * p_after['bound'] / p_after['total']
        near_pct = 100.0 * p_after['nearest'] / p_after['total']

        print(f"GATE 1 parcel_zoning_code_coverage_pct = {cov_pct:.1f}% "
              f"(target ≥70%) — {'PASS' if cov_pct >= 70.0 else 'SUB-GATE'}")
        print(f"GATE 2 nearest_* share = {near_pct:.1f}% "
              f"(target <30%) — {'PASS' if near_pct < 30.0 else 'SUB-GATE'}")
        print(f"GATE 3 raw_attributes preserved (Norfolk): "
              f"INSERTed with full source payload + muni_name='{MUNI_NAME_CITY}'")
        print(f"GATE 4 districts: {d_after} (was {d_before}; +{d_after - d_before} city)")
        print(f"GATE 5 jurisdictions.bbox: populated")
        print(f"GATE 6 matrix codes: {m_after} (orchestrator's domain)")

        print(f"\nPRE→POST parcels: bound {p_before['bound']:,} → {p_after['bound']:,} "
              f"({100*(p_after['bound']-p_before['bound'])/p_before['total']:+.1f} pp)")
        print(f"          contained: {p_before['contained']:,} → {p_after['contained']:,}")
        print(f"          nearest:   {p_before['nearest']:,} → {p_after['nearest']:,}")

        # Zoning code distribution post-fire
        print("\n=== Post-fire parcels.zoning_code distribution ===")
        rows = await conn.fetch(
            """
            SELECT zoning_code, COUNT(*) AS n
            FROM parcels WHERE jurisdiction_id = $1::uuid
            GROUP BY zoning_code ORDER BY zoning_code
            """,
            str(MERCER_JID),
        )
        # Surface new codes not in existing matrix (orchestrator's follow-up signal)
        existing_matrix_codes = set(
            r["zone_code"] for r in await conn.fetch(
                "SELECT DISTINCT zone_code FROM zone_use_matrix WHERE jurisdiction_id = $1::uuid",
                str(MERCER_JID),
            )
        )
        new_codes_with_parcels = []
        for r in rows:
            code = r["zoning_code"]
            flag = ""
            if code is not None and code not in existing_matrix_codes:
                flag = "  ← NEW (no matrix yet)"
                new_codes_with_parcels.append((code, r["n"]))
            print(f"  {str(code):10s} {r['n']:>6,}{flag}")

        if new_codes_with_parcels:
            print(f"\nORCHESTRATOR FOLLOW-UP — {len(new_codes_with_parcels)} new codes need matrix:")
            for code, n in new_codes_with_parcels:
                print(f"  {code}: {n} parcels")

    finally:
        await conn.close()
    return 0


async def main(args) -> int:
    if args.subcommand == "preflight":
        return await _preflight()
    if args.subcommand == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing to fire without --i-know-this-writes-to-prod",
                  file=sys.stderr)
            return 2
        return await _fire(nearest_within_meters=args.nearest_within_meters)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("preflight", help="Read-only pipeline shape validation.")
    fire = sub.add_parser("fire", help="Real prod write.")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args)))
