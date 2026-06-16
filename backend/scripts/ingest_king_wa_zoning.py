"""Phase 6A.2 — King WA Class A zoning backfill via Washington State Zoning Atlas (WAZA).

Predecessor: PR #259 (Phase 6A.1, 635,186 parcels staged) ·
PR #261 (Contra Costa bbox metadata lesson).

Master authorized Phase 6A.2 after Task A (PR #261) closed. Three
codified updates from the prior dispatch chain are wired into this
adapter:

  1. Skip prod preflight ROLLBACK (PR #253 lesson — in-txn rows aren't
     in GiST → sequential scans, hangs). Use Phase 1 shapely-only
     verdict as substitute; this script's `preflight` is read-only
     pipeline shape validation with NO DB WRITES.

  2. jurisdictions.bbox populated INLINE as part of `fire` (PR #261
     lesson). The fire path computes ST_Extent over King's parcels
     and writes `jurisdictions.bbox` before declaring complete, so the
     audit's `missing_bbox` gate never fires.

  3. Bellevue WAZA-vs-city-layer code mismatch verification (PR #248
     Diagnostic). The directory uses WAZA as primary. After fire,
     this script reports distinct Bellevue `parcels.zoning_code`
     values so an operator can compare against current Bellevue city
     codes (LDR-2 / MU-H post-2017 amendment vs WAZA's frozen
     R-10 / GC).

Source layer:

    Washington State Zoning Atlas (Zones) FeatureServer/0
    https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer/0

Live probes (PR #259):
  - King total : 56,900 features across 39 jurisdictions
  - Bellevue   : 991 features (53 distinct ZoneID×ZoneName)
  - Mercer Island : 48 features
  - Server-side reprojection to WGS84 via outSR=4326 confirmed working

Per-muni backfill scope mirrors Westchester (PR #233 collision-fix):
  - districts filter: raw_attributes->>'muni_name' = entry["muni_name"]
  - parcels filter:   city = entry["prod_city_value"]
  Both supplied as separate params.

Subcommands:

  preflight  Read-only pipeline shape validation. Pulls a sample of
             features from each directory entry's WAZA filter, builds
             rows, reports field distribution. NO DB WRITES.

  fire       Real prod write. Requires --i-know-this-writes-to-prod.
             For each entry: fetch WAZA features → INSERT zoning_districts
             → 2-pass spatial backfill (ST_Within contained →
             ST_DWithin nearest_50m fallback) scoped per-muni. After
             both munis processed: inline UPDATE jurisdictions.bbox.

Hard rules honored:
  - raw_attributes preserved verbatim (Norfolk gate)
  - muni_name vs prod_city_value separated as distinct params (PR #233)
  - jurisdictions.bbox populated inline (PR #261)
  - ONE refresh per task (operator at end)
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

logger = logging.getLogger("king_wa_zoning")

DIRECTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "king_wa_zoning_directory.json"
# Registered in PR #259 (Phase 6A.1).
KING_JID = uuid.UUID("1e65c053-da54-4733-9d77-ca9aa3b27a7b")
ARCGIS_PAGE_SIZE = 1000


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _load_directory_entries() -> list[dict[str, Any]]:
    directory = json.loads(DIRECTORY_PATH.read_text())
    if not directory:
        raise SystemExit(f"{DIRECTORY_PATH.name} is empty")
    return directory


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
            logger.info("fetched %d features (cumulative %d) where=%r offset=%d",
                        len(batch), len(features), where, offset)
            if len(batch) < ARCGIS_PAGE_SIZE:
                break
            offset += ARCGIS_PAGE_SIZE
    return features


def _arcgis_rings_to_wkt(rings: list[list[list[float]]]) -> str:
    """Westchester adapter's winding-detection logic verbatim."""
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
    jurisdiction_id: uuid.UUID,
) -> list[dict[str, Any]]:
    field_map = entry["zoning_district_source"]["field_map"]
    passthrough = entry["zoning_district_source"]["raw_attributes_passthrough"]
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
            "source_url": entry["zoning_district_source"]["url"],
            "source_filter": entry["zoning_district_source"]["filter_query"],
            "source_kind": entry["zoning_district_source"]["kind"],
            "ingested_at": "2026-06-16",
            "muni_name": entry["muni_name"],
            "muni_type": entry["muni_type"],
            "ordinance_url": entry.get("ordinance_url"),
            "vintage": entry.get("vintage"),
        }
        for f_name in passthrough:
            if f_name in attrs:
                raw_attributes[f_name] = attrs[f_name]
        try:
            wkt = _arcgis_rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping feature OBJECTID=%s, ring parse failed: %s",
                           attrs.get("OBJECTID"), exc)
            continue
        out.append({
            "jurisdiction_id": str(jurisdiction_id),
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
    """Pipeline-shape validation only — NO DB WRITES. Per PR #253 lesson:
    skip in-DB ROLLBACK gates for Class A scale work. Phase 1 spec
    primitive verification + this lightweight pipeline check substitutes."""
    print("\n=== PRE-FLIGHT: King WA WAZA zoning ingest (pipeline shape) ===\n")
    entries = _load_directory_entries()
    for entry in entries:
        print(f"--- {entry['muni_name']} ---")
        features = await _fetch_arcgis_features(entry["zoning_district_source"])
        rows = _build_zoning_district_rows(entry, features, KING_JID)
        distinct_codes = sorted({r["zone_code"] for r in rows})
        print(f"  features fetched   : {len(features)}")
        print(f"  rows built         : {len(rows)}")
        print(f"  distinct ZoneIDs   : {len(distinct_codes)}")
        print(f"  top 10 codes       : {distinct_codes[:10]}")
        # Spot-check raw_attributes preservation
        if rows:
            sample_raw = json.loads(rows[0]["raw_attributes"])
            print(f"  sample raw fields  : {len(sample_raw)} fields, including "
                  f"{list(sample_raw.keys())[:6]}")
    print("\n(NO DB WRITES — pipeline shape validated. "
          "Phase 1 spec verdict substitutes for in-DB preflight.)")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Fire
# ────────────────────────────────────────────────────────────────────────────


async def _fire(nearest_within_meters: float = 50.0) -> int:
    """Real prod write. INSERT WAZA features → per-muni spatial backfill →
    inline jurisdictions.bbox UPDATE."""
    print(f"\n=== FIRE: King WA WAZA zoning backfill ===\n")
    entries = _load_directory_entries()

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # Phase 1 — fetch + INSERT districts per muni
        per_muni_inserted: dict[str, int] = {}
        for entry in entries:
            features = await _fetch_arcgis_features(entry["zoning_district_source"])
            rows = _build_zoning_district_rows(entry, features, KING_JID)
            print(f"\n[{entry['muni_name']}] INSERTing {len(rows)} districts…")
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
            per_muni_inserted[entry["muni_name"]] = len(rows)
            print(f"[{entry['muni_name']}] INSERTed {len(rows)} rows")

        # Phase 2 — per-muni spatial backfill scoped via parcels.city.
        # PR #233 collision-fix: muni_name + prod_city_value as separate params.
        for entry in entries:
            muni_name = entry["muni_name"]
            city = entry["prod_city_value"]
            print(f"\n[{muni_name}] Pass 1 contained (ST_Within centroid)…")
            status1 = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class = sub.zone_class,
                    zone_binding_method = 'contained',
                    zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
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
                ) sub
                WHERE target.id = sub.parcel_id
                """,
                str(KING_JID), muni_name, city,
            )
            try:
                n1 = int(status1.split()[-1])
            except (ValueError, IndexError):
                n1 = -1
            print(f"[{muni_name}] contained UPDATEd {n1}")

            binding_label = f"nearest_{int(round(nearest_within_meters))}m"
            print(f"[{muni_name}] Pass 2 {binding_label} (ST_DWithin nearest)…")
            status2 = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class = sub.zone_class,
                    zone_binding_method = $4,
                    zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
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
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id = sub.parcel_id
                """,
                str(KING_JID), muni_name, city, binding_label,
                float(nearest_within_meters),
            )
            try:
                n2 = int(status2.split()[-1])
            except (ValueError, IndexError):
                n2 = -1
            print(f"[{muni_name}] {binding_label} UPDATEd {n2}")

        # Phase 3 — INLINE jurisdictions.bbox UPDATE (PR #261 lesson).
        print("\n--- Inline bbox UPDATE (PR #261 codified) ---")
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
            str(KING_JID),
        )
        if ext and ext["minx"] is not None:
            bbox = [
                float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"]),
            ]
            # Sanity check: King WA is around lon=-122, lat=47-48
            if -125 <= bbox[0] <= -120 and 46 <= bbox[1] <= 48.5:
                await conn.execute(
                    "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
                    str(KING_JID), json.dumps(bbox),
                )
                print(f"jurisdictions.bbox UPDATEd: {bbox}")
            else:
                print(f"HALT: computed bbox doesn't look like King WA: {bbox}",
                      file=sys.stderr)
                return 3
        else:
            print("HALT: no parcel geometry to compute bbox from",
                  file=sys.stderr)
            return 4

        # Phase 4 — Per-muni verification + Bellevue mismatch check.
        print("\n--- Per-muni gate verification ---")
        for entry in entries:
            muni_name = entry["muni_name"]
            city = entry["prod_city_value"]
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE p.geom IS NOT NULL) AS total,
                    COUNT(*) FILTER (WHERE p.zone_binding_method IS NOT NULL) AS bound,
                    COUNT(*) FILTER (WHERE p.zone_binding_method = 'contained') AS contained,
                    COUNT(*) FILTER (WHERE p.zone_binding_method LIKE 'nearest_%') AS nearest
                FROM parcels p
                WHERE p.jurisdiction_id = $1::uuid AND p.city = $2
                """, str(KING_JID), city,
            )
            districts = per_muni_inserted.get(muni_name, 0)
            empty_raw = await conn.fetchval(
                """
                SELECT COUNT(*) FROM zoning_districts
                WHERE jurisdiction_id = $1::uuid
                  AND raw_attributes->>'muni_name' = $2
                  AND (raw_attributes = '{}'::jsonb
                       OR raw_attributes->>'source_url' IS NULL)
                """, str(KING_JID), muni_name,
            )
            cov = (stats["bound"] / stats["total"] * 100) if stats["total"] else 0
            near_share = (stats["nearest"] / stats["bound"] * 100) if stats["bound"] else 0
            print(
                f"[{muni_name}] districts={districts}  parcels={stats['total']}  "
                f"bound={stats['bound']}  cov={cov:.1f}%  "
                f"contained={stats['contained']}  nearest={stats['nearest']}  "
                f"near_share={near_share:.2f}%  empty_raw={empty_raw}"
            )

        # Bellevue WAZA vs city zoning code mismatch check (PR #248).
        print("\n--- Bellevue WAZA vs city-zoning code-mismatch check (PR #248) ---")
        bv_codes = await conn.fetch(
            """
            SELECT zone_code, COUNT(*) AS n
            FROM zoning_districts
            WHERE jurisdiction_id = $1::uuid
              AND raw_attributes->>'muni_name' = 'Bellevue'
            GROUP BY zone_code ORDER BY n DESC LIMIT 20
            """, str(KING_JID),
        )
        print(f"Top 20 Bellevue districts by zone_code (WAZA-source):")
        for r in bv_codes:
            print(f"  {r['zone_code']:12s}  {r['n']:>4} districts")
        # Look for legacy R-10/GC (frozen WAZA vintage) vs modern LDR-2/MU-H
        # (current Bellevue city codes per PR #248 Diagnostic).
        legacy = await conn.fetchval(
            """
            SELECT COUNT(*) FROM zoning_districts
            WHERE jurisdiction_id = $1::uuid
              AND raw_attributes->>'muni_name' = 'Bellevue'
              AND zone_code IN ('R-10', 'GC')
            """, str(KING_JID),
        )
        modern = await conn.fetchval(
            """
            SELECT COUNT(*) FROM zoning_districts
            WHERE jurisdiction_id = $1::uuid
              AND raw_attributes->>'muni_name' = 'Bellevue'
              AND zone_code IN ('LDR-2', 'MU-H')
            """, str(KING_JID),
        )
        print(f"  legacy (R-10 / GC) count : {legacy}")
        print(f"  modern (LDR-2 / MU-H) cnt: {modern}")
        if legacy and not modern:
            print("  → WAZA uses LEGACY codes; current Bellevue city zoning has "
                  "shifted to LDR-2/MU-H. Documented mismatch.")
        elif modern and not legacy:
            print("  → WAZA appears UPDATED to current city codes. No mismatch.")
        elif legacy and modern:
            print("  → WAZA carries BOTH legacy and modern codes (mixed vintage).")
        else:
            print("  → No matching legacy or modern codes found "
                  "(Bellevue likely uses other code namespace).")
    finally:
        await conn.close()

    print(
        "\nNext step (operator): POST /api/admin/coverage/refresh"
        f"?jurisdiction_id={KING_JID}  — fire ONCE per dispatch hard rule."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes "
             "zoning_districts + parcels + jurisdictions rows on prod.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.cmd == "preflight":
        return asyncio.run(_preflight())
    elif args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing to fire without --i-know-this-writes-to-prod",
                  file=sys.stderr)
            return 2
        return asyncio.run(_fire())
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
