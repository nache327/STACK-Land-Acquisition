"""Phase 7F.x - Fox Chapel PA Borough zoning Class B per-muni ingest.

Per Diagnostic PR #342 (merged 2026-06-23), Fox Chapel's stale ZoningHub
configuration still points to a dead services8 ArcGIS URL, but the Borough's
own ArcGIS account (`FoxChapelAC`) exposes a live public zoning FeatureServer:

Source: services6.arcgis.com/JjJzcTHADvUflwt9/.../Zoning_District/FeatureServer/0
  - 72 polygons
  - ZONECLASS field, 100% queryable
  - 5 distinct codes: A, B, C, D, I-O
  - Spatial reference: PA StatePlane South (wkid 102729 / latest 2272);
    we request outSR=4326 to normalize server-side.

Pattern: PR #334 Winnetka prep adapter + Allegheny Phase 7F PATH 1
per-muni registration. Fox Chapel is already expected to exist as its own
jurisdiction from Phase 7F.2 (`Fox Chapel, PA`), with parcels moved out of
the Allegheny County umbrella by exact city label `Fox Chapel Borough`.

GATE: this script REFUSES TO FIRE unless:
  - `Fox Chapel, PA` jurisdiction exists
  - enough parcels are already under that JID (Phase 7F.2 PATH 1 landed)

IDEMPOTENCY: wraps the full pipeline (DELETE existing rows + reset parcel
bindings + INSERT + spatial backfill + bbox update) in a single transaction.
Re-firing is safe and does not touch Beverly Hills, Aspinwall, Sewickley, or
zone_use_matrix.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg
import dotenv
import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
logger = logging.getLogger("fox_chapel_pa")

MUNI = "Fox Chapel"
MUNI_LABEL = "Fox Chapel Borough"
JURISDICTION_NAME = "Fox Chapel, PA"
LAYER = "https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer/0"
ZCODE = "ZONECLASS"
RAW_KEYS = (
    "OBJECTID",
    "ZONECLASS",
    "ZONEDESC",
    "BASEELEV",
    "HEIGHT",
    "LASTUPDATE",
    "LASTEDITOR",
    "COMMENT",
    "SOURCE",
    "GlobalID",
    "CreationDate",
    "Creator",
    "EditDate",
    "Editor",
    "Shape__Area",
    "Shape__Length",
)

# Fox Chapel parcel bbox from accepted Allegheny acquisition spec/probe.
BBOX_LON = (-79.93, -79.84)
BBOX_LAT = (40.48, 40.56)

# Phase 7F.1/7F.2 expected roughly 2,179 Fox Chapel parcels; keep this low
# enough to tolerate parcel-count drift, high enough to catch missing PATH 1.
MIN_PARCELS_FOR_FIRE = 1000


def _db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not set in environment")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _rings_to_wkt(rings) -> str:
    polys = []
    for ring in rings:
        if len(ring) < 4:
            continue
        polys.append("((" + ", ".join(f"{p[0]} {p[1]}" for p in ring) + "))")
    if not polys:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(polys) + ")"


async def _resolve_jid(conn: asyncpg.Connection) -> str:
    """Look up the Fox Chapel per-muni JID. Refuse if PATH 1 is absent."""
    jid = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE name = $1 AND state = 'PA'",
        JURISDICTION_NAME,
    )
    if not jid:
        raise SystemExit(
            f"REFUSE FIRE - jurisdiction '{JURISDICTION_NAME}' not registered. "
            "Run/confirm Allegheny Phase 7F.2 PATH 1 per-muni registration first."
        )
    return str(jid)


async def _gate_check(conn: asyncpg.Connection, jid: str) -> None:
    """Refuse if Fox Chapel parcels have not been moved under the per-muni JID."""
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    if n < MIN_PARCELS_FOR_FIRE:
        raise SystemExit(
            f"REFUSE FIRE - only {n} parcels under Fox Chapel JID. "
            f"Expected about 2,179 after Allegheny PATH 1; "
            f"gate threshold {MIN_PARCELS_FOR_FIRE}."
        )

    label_mismatch = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
           WHERE jurisdiction_id=$1::uuid
             AND COALESCE(city, '') <> $2""",
        jid,
        MUNI_LABEL,
    )
    if label_mismatch:
        raise SystemExit(
            f"REFUSE FIRE - {label_mismatch} Fox Chapel JID parcels do not carry "
            f"city='{MUNI_LABEL}'. Preserve Allegheny LABEL discipline before fire."
        )
    print(f"[gate] {n:,} parcels under Fox Chapel JID with city='{MUNI_LABEL}' - proceeding")


async def _fetch_features(client: httpx.AsyncClient) -> list:
    """Page through the source layer, requesting WGS84 geometry from ArcGIS."""
    features = []
    offset = 0
    while True:
        r = await client.get(
            f"{LAYER}/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "f": "json",
                "orderByFields": "OBJECTID",
            },
        )
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(f"ArcGIS query error: {payload['error']}")
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info("fetched %d (cum %d)", len(batch), len(features))
        if len(batch) < 1000:
            break
        offset += 1000
    return features


async def _fire(near: float = 50.0, dry_run: bool = False) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: {MUNI} PA zoning (Class B per-muni) ===\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        feats = await _fetch_features(client)

    rows = []
    for f in feats:
        attrs = f.get("attributes", {})
        geom = f.get("geometry")
        zone_code = attrs.get(ZCODE)
        if not geom or "rings" not in geom:
            continue
        if not zone_code or not str(zone_code).strip():
            continue
        try:
            wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("skip OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue

        raw = {
            "source_url": LAYER,
            "source_kind": "arcgis_feature_server",
            "source_item_id": "bc38d9d6d63b497382dd8da18a692024",
            "ingested_at": "2026-06-23",
            "muni_name": MUNI_LABEL,
            "muni_type": "borough",
            "publisher": "Borough of Fox Chapel PA GIS (FoxChapelAC, Diagnostic PR #342)",
            "source_srid_native": 102729,
        }
        for key in RAW_KEYS:
            if key in attrs and attrs[key] is not None:
                raw[key] = attrs[key]

        zone_name = str(attrs.get("ZONEDESC") or "").strip() or str(zone_code).strip()
        rows.append({
            "zone_code": str(zone_code).strip(),
            "zone_name": zone_name,
            "wkt": wkt,
            "raw": json.dumps(raw),
        })

    distinct = sorted({row["zone_code"] for row in rows})
    print(f"features={len(feats)} rows={len(rows)} distinct={len(distinct)}: {distinct}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, command_timeout=3600)
    try:
        jid = await _resolve_jid(conn)
        await _gate_check(conn, jid)

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            cleared_districts = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(f"[idempotency] cleared {cleared_districts.split()[-1]} prior zoning_districts rows")

            cleared_parcels = await conn.execute(
                """UPDATE parcels
                      SET zoning_code = NULL,
                          zone_class = NULL,
                          zone_binding_method = NULL
                    WHERE jurisdiction_id=$1::uuid""",
                jid,
            )
            print(f"[idempotency] reset bindings on {cleared_parcels.split()[-1]} parcels")

            print(f"\n[INSERT] {len(rows)} zoning_districts...")
            for row in rows:
                await conn.execute(
                    """INSERT INTO zoning_districts (
                           jurisdiction_id, zone_code, zone_name, zone_class,
                           geom, raw_attributes, source
                       )
                       VALUES (
                           $1::uuid, $2, $3, 'unknown'::zone_class_enum,
                           ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                           $5::jsonb, 'arcgis'::zone_source_enum
                       )""",
                    jid,
                    row["zone_code"],
                    row["zone_name"],
                    row["wkt"],
                    row["raw"],
                )
            print(f"[INSERT] {len(rows)} committed")

            contained = await conn.execute(
                """
                UPDATE parcels target
                   SET zone_class = sub.zone_class,
                       zone_binding_method = 'contained',
                       zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                  FROM (
                    SELECT p.id AS parcel_id, match.zone_class, match.zone_code
                      FROM parcels p,
                           LATERAL (
                             SELECT zd.zone_class, zd.zone_code
                               FROM zoning_districts zd
                              WHERE zd.jurisdiction_id=$1::uuid
                                AND zd.geom IS NOT NULL
                                AND ST_Within(ST_Centroid(p.geom), zd.geom)
                              ORDER BY zd.id
                              LIMIT 1
                           ) match
                     WHERE p.jurisdiction_id=$1::uuid
                       AND p.geom IS NOT NULL
                  ) sub
                 WHERE target.id = sub.parcel_id
                """,
                jid,
            )
            print(f"[spatial] contained UPDATEd {int(contained.split()[-1])}")

            nearest_label = f"nearest_{int(round(near))}m"
            nearest = await conn.execute(
                """
                UPDATE parcels target
                   SET zone_class = sub.zone_class,
                       zone_binding_method = $2,
                       zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                  FROM (
                    SELECT p.id AS parcel_id, match.zone_class, match.zone_code
                      FROM parcels p,
                           LATERAL (
                             SELECT zd.zone_class, zd.zone_code
                               FROM zoning_districts zd
                              WHERE zd.jurisdiction_id=$1::uuid
                                AND zd.geom IS NOT NULL
                                AND ST_DWithin(
                                  zd.geom::geography,
                                  ST_Centroid(p.geom)::geography,
                                  $3
                                )
                              ORDER BY ST_Distance(
                                zd.geom::geography,
                                ST_Centroid(p.geom)::geography
                              )
                              LIMIT 1
                           ) match
                     WHERE p.jurisdiction_id=$1::uuid
                       AND p.geom IS NOT NULL
                       AND p.zone_binding_method IS NULL
                  ) sub
                 WHERE target.id = sub.parcel_id
                """,
                jid,
                nearest_label,
                float(near),
            )
            print(f"[spatial] {nearest_label} UPDATEd {int(nearest.split()[-1])}")

            ext = await conn.fetchrow(
                """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                          ST_YMin(ST_Extent(geom)) AS miny,
                          ST_XMax(ST_Extent(geom)) AS maxx,
                          ST_YMax(ST_Extent(geom)) AS maxy
                     FROM parcels
                    WHERE jurisdiction_id=$1::uuid
                      AND geom IS NOT NULL""",
                jid,
            )
            if ext is None or ext["minx"] is None:
                raise RuntimeError("Fox Chapel parcels have no geometry")
            bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
            if not (BBOX_LON[0] <= bbox[0] <= BBOX_LON[1] and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]):
                raise RuntimeError(
                    f"bbox {bbox} outside Fox Chapel envelope "
                    f"(lon {BBOX_LON}, lat {BBOX_LAT}) - abort"
                )
            await conn.execute(
                "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
                jid,
                json.dumps(bbox),
            )
            print(f"\nbbox {bbox}")

            if dry_run:
                raise _RollbackForDryRun()

        p = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (
                        WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                      ) AS bound,
                      COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                      COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
                 FROM parcels
                WHERE jurisdiction_id=$1::uuid""",
            jid,
        )
        district_count = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
            jid,
        )
        empty_raw = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts
                WHERE jurisdiction_id=$1::uuid
                  AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)""",
            jid,
        )
        coverage = 100.0 * p["bound"] / p["total"] if p["total"] else 0.0
        nearest_pct = 100.0 * p["nearest"] / p["total"] if p["total"] else 0.0

        print("\n=== 5-GATE ===")
        print(f"GATE 1 cov {coverage:.1f}% (>=70%) - {'PASS' if coverage >= 70 else 'SUB'}")
        print(f"GATE 2 near {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty_raw} - {'PASS' if empty_raw == 0 else 'FAIL'}")
        print(f"GATE 4 districts {district_count} - {'PASS' if district_count > 0 else 'FAIL'}")
        print("GATE 5 bbox populated")
        print(
            f"  parcels {p['total']:,} bound {p['bound']:,} "
            f"contained {p['contained']:,} nearest {p['nearest']:,}"
        )

        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n
                 FROM parcels
                WHERE jurisdiction_id=$1::uuid
                  AND zoning_code IS NOT NULL
                GROUP BY 1
                ORDER BY 2 DESC""",
            jid,
        )
        print(f"\nDistribution ({len(codes)}):")
        for row in codes:
            print(f"  {row['zoning_code']:15s} {row['n']:>5,}")

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the tx context manager to trigger rollback."""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run the full pipeline inside a transaction, then ROLLBACK. "
            "Useful for fire-readiness verification once Master/Lane A greenlights."
        ),
    )
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()
    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass --dry-run for transactional rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_fire(near=args.nearest_within_meters, dry_run=args.dry_run)))
