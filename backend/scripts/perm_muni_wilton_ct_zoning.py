"""Phase 7.x - Wilton CT Class B per-muni zoning adapter.

Per Diagnostic PR #361 (merged 2026-06-23), Wilton CT has an anonymous
QDSGIS zoning polygon source:

  https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/
      CT_Wilton_Adv_Viewer_Layers/FeatureServer/13

Diagnostic result:
  - 47 zoning polygons
  - polygon geometry
  - zone code field: Description
  - auxiliary fields: Zoning, ZoneNum
  - parcel/MAT source also carries embedded zoning, but the municipal
    OpenGov layer has a different record grain than the existing Fairfield
    parcel substrate. Treat embedded zoning as a validation aid until Lane A
    explicitly authorizes a parcel-alignment path.

Pattern: Winnetka PR #334 for idempotent per-muni Class B zoning ingest,
plus Fairfield/Allegheny PATH 1 per-muni jurisdiction registration.

This script:
  1. Registers/finds the Wilton, CT jurisdiction inside the Fairfield CT
     umbrella.
  2. Moves only existing Fairfield County parcels with city='Wilton' into
     the Wilton JID.
  3. Ingests QDSGIS zoning polygons into zoning_districts.
  4. Resets and spatially backfills only Wilton parcels.

Hard rules:
  - PREP-only PR. Do not fire until Master/Lane A greenlights.
  - No zone_use_matrix changes.
  - No Beverly Hills / Aspinwall / Sewickley / Fox Chapel state touched.
  - raw_attributes preserved on zoning_districts.
  - Idempotent: clear Wilton zoning_districts and Wilton parcel bindings
    inside the same transaction before re-insert/backfill.
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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("wilton_ct_zoning")

FAIRFIELD_CT_JID = "66230887-aabe-4d62-aebb-856939ba77bb"
JURISDICTION_NAME = "Wilton, CT"
JURISDICTION_STATE = "CT"
JURISDICTION_COUNTY = "Fairfield"
PROD_CITY_VALUE = "Wilton"
MUNI_NAME = "Wilton"
MUNI_TYPE = "town"

ZONING_LAYER_URL = (
    "https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/"
    "CT_Wilton_Adv_Viewer_Layers/FeatureServer/13"
)
PARCEL_MAT_LAYER_URL = (
    "https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/"
    "CT_Wilton_OpenGov_FS/FeatureServer/0"
)
ZONE_CODE_FIELD = "Description"
ZONE_NAME_FIELD = "Description"
RAW_PASSTHROUGH = (
    "OBJECTID",
    "Zoning",
    "ZoneNum",
    "Description",
    "Shape__Area",
    "Shape__Length",
)

ARCGIS_PAGE_SIZE = 1000
EXPECTED_ZONING_COUNT = 47
MIN_ZONING_ROWS_FOR_FIRE = 40
MIN_PARCELS_FOR_FIRE = 1000

# Broad Wilton/Fairfield sanity envelope. This is for wrong-target catches,
# not a tight municipal boundary.
BBOX_LON_RANGE = (-73.65, -73.30)
BBOX_LAT_RANGE = (41.05, 41.35)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    ring_wkts = []
    for ring in rings:
        if len(ring) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


async def _arcgis_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS error from {url}: {payload['error']}")
    return payload


async def _source_freshness_check(client: httpx.AsyncClient) -> None:
    metadata = await _arcgis_json(client, ZONING_LAYER_URL, {"f": "json"})
    field_names = {field.get("name") for field in metadata.get("fields", [])}
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError(
            f"Wilton zoning source drift: geometryType={metadata.get('geometryType')}"
        )
    if ZONE_CODE_FIELD not in field_names:
        raise RuntimeError(
            f"Wilton zoning source drift: missing {ZONE_CODE_FIELD!r}; "
            f"fields={sorted(field_names)}"
        )

    count_payload = await _arcgis_json(
        client,
        f"{ZONING_LAYER_URL}/query",
        {"where": "1=1", "returnCountOnly": "true", "f": "json"},
    )
    count = int(count_payload.get("count") or 0)

    sample_payload = await _arcgis_json(
        client,
        f"{ZONING_LAYER_URL}/query",
        {
            "where": "1=1",
            "outFields": "OBJECTID,Zoning,ZoneNum,Description",
            "returnGeometry": "false",
            "resultRecordCount": 10,
            "f": "json",
            "orderByFields": "OBJECTID",
        },
    )
    sample = [f.get("attributes", {}) for f in sample_payload.get("features", [])]
    non_null = sum(
        1 for attrs in sample if str(attrs.get(ZONE_CODE_FIELD) or "").strip()
    )
    if count < MIN_ZONING_ROWS_FOR_FIRE or non_null != len(sample):
        raise RuntimeError(
            "Wilton zoning source drift: "
            f"count={count}, sample_non_null_{ZONE_CODE_FIELD}={non_null}/{len(sample)}"
        )

    mat_total = await _arcgis_json(
        client,
        f"{PARCEL_MAT_LAYER_URL}/query",
        {"where": "1=1", "returnCountOnly": "true", "f": "json"},
    )
    mat_zoned = await _arcgis_json(
        client,
        f"{PARCEL_MAT_LAYER_URL}/query",
        {
            "where": "zoning IS NOT NULL AND zoning <> ''",
            "returnCountOnly": "true",
            "f": "json",
        },
    )
    print("[source] Wilton QDSGIS zoning layer live")
    print(f"  name          : {metadata.get('name')}")
    print(f"  geometry      : {metadata.get('geometryType')}")
    print(f"  count         : {count} (diagnostic expected {EXPECTED_ZONING_COUNT})")
    print(f"  code field    : {ZONE_CODE_FIELD}")
    print(f"  sample nonnull: {non_null}/{len(sample)}")
    print(
        "  OpenGov parcel/MAT embedded zoning: "
        f"{mat_zoned.get('count')}/{mat_total.get('count')} records"
    )


async def _fetch_zoning_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = await _arcgis_json(
            client,
            f"{ZONING_LAYER_URL}/query",
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": ARCGIS_PAGE_SIZE,
                "f": "json",
                "orderByFields": "OBJECTID",
            },
        )
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info(
            "fetched %d zoning features (cumulative %d) offset=%d",
            len(batch),
            len(features),
            offset,
        )
        if len(batch) < ARCGIS_PAGE_SIZE:
            break
        offset += ARCGIS_PAGE_SIZE
    return features


def _build_district_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        zone_code = str(attrs.get(ZONE_CODE_FIELD) or "").strip()
        if not geom or "rings" not in geom or not zone_code:
            continue
        try:
            geom_wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue

        raw_attributes = {
            "source_url": ZONING_LAYER_URL,
            "source_kind": "arcgis_feature_server",
            "source_filter": "1=1",
            "ingested_at": "2026-06-24",
            "muni_name": MUNI_NAME,
            "muni_type": MUNI_TYPE,
            "publisher": "Town of Wilton CT / QDSGIS",
            "diagnostic_pr": 361,
            "parcel_mat_validation_url": PARCEL_MAT_LAYER_URL,
        }
        for key in RAW_PASSTHROUGH:
            if key in attrs and attrs[key] is not None:
                raw_attributes[key] = attrs[key]

        zone_name = str(attrs.get(ZONE_NAME_FIELD) or zone_code).strip()
        rows.append(
            {
                "zone_code": zone_code,
                "zone_name": zone_name,
                "geom_wkt": geom_wkt,
                "raw_attributes": json.dumps(raw_attributes),
            }
        )
    return rows


async def _resolve_or_register_wilton(conn: asyncpg.Connection) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if existing:
        jid = str(existing["id"])
        print(f"[jurisdiction] found existing {JURISDICTION_NAME}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO jurisdictions (id, name, state, county)
           VALUES ($1::uuid, $2, $3, $4)""",
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _move_wilton_parcels(conn: asyncpg.Connection, jid: str) -> None:
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    candidates = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
           WHERE jurisdiction_id=$1::uuid AND city=$2""",
        FAIRFIELD_CT_JID,
        PROD_CITY_VALUE,
    )
    print(f"[jurisdiction] existing Wilton parcels: {existing:,}")
    print(f"[jurisdiction] Fairfield candidates city={PROD_CITY_VALUE!r}: {candidates:,}")

    if candidates:
        status = await conn.execute(
            """UPDATE parcels
                  SET jurisdiction_id=$2::uuid,
                      city=$3,
                      updated_at=NOW()
                WHERE jurisdiction_id=$1::uuid AND city=$3""",
            FAIRFIELD_CT_JID,
            jid,
            PROD_CITY_VALUE,
        )
        moved = int(status.split()[-1])
        print(f"[jurisdiction] moved Fairfield -> Wilton parcels: {moved:,}")

    total = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid",
        jid,
    )
    if total < MIN_PARCELS_FOR_FIRE:
        raise RuntimeError(
            f"REFUSE FIRE - only {total:,} parcels under {JURISDICTION_NAME}; "
            f"expected ~2,561 from PR #228 city derivation"
        )
    print(f"[gate] {total:,} parcels under Wilton JID - proceeding")


async def _update_wilton_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    ext = await conn.fetchrow(
        """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                  ST_YMin(ST_Extent(geom)) AS miny,
                  ST_XMax(ST_Extent(geom)) AS maxx,
                  ST_YMax(ST_Extent(geom)) AS maxy
           FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""",
        jid,
    )
    if ext is None or ext["minx"] is None:
        raise RuntimeError("no Wilton parcel geometry post-move")

    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    lon_lo, lon_hi = BBOX_LON_RANGE
    lat_lo, lat_hi = BBOX_LAT_RANGE
    if not (
        lon_lo <= bbox[0] <= lon_hi
        and lon_lo <= bbox[2] <= lon_hi
        and lat_lo <= bbox[1] <= lat_hi
        and lat_lo <= bbox[3] <= lat_hi
    ):
        raise RuntimeError(
            f"Wilton bbox {bbox} outside expected range "
            f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
        )

    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    print(f"[bbox] verified+updated: {bbox}")
    return bbox


async def _run(nearest_within_meters: float, dry_run: bool) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Wilton CT Class B per-muni zoning ===\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        await _source_freshness_check(client)
        features = await _fetch_zoning_features(client)
    rows = _build_district_rows(features)
    distinct = sorted({row["zone_code"] for row in rows})
    print(f"[source] features={len(features)} rows={len(rows)} distinct={len(distinct)}")
    print(f"[source] codes={distinct}")
    if len(rows) < MIN_ZONING_ROWS_FOR_FIRE:
        raise RuntimeError(
            f"REFUSE FIRE - only {len(rows)} usable Wilton zoning rows; "
            f"expected around {EXPECTED_ZONING_COUNT}"
        )

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _resolve_or_register_wilton(conn)
            await _move_wilton_parcels(conn, jid)

            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(
                f"[idempotency] cleared {int(cleared.split()[-1])} "
                "prior zoning_districts rows"
            )

            reset = await conn.execute(
                """UPDATE parcels
                      SET zoning_code=NULL,
                          zone_class=NULL,
                          zone_binding_method=NULL
                    WHERE jurisdiction_id=$1::uuid""",
                jid,
            )
            print(f"[idempotency] reset bindings on {int(reset.split()[-1])} parcels")

            print(f"[insert] {len(rows)} zoning_districts")
            for row in rows:
                await conn.execute(
                    """INSERT INTO zoning_districts (
                           jurisdiction_id, zone_code, zone_name, zone_class,
                           geom, raw_attributes, source
                       ) VALUES (
                           $1::uuid, $2, $3, 'unknown'::zone_class_enum,
                           ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                           $5::jsonb, 'arcgis'::zone_source_enum
                       )""",
                    jid,
                    row["zone_code"],
                    row["zone_name"],
                    row["geom_wkt"],
                    row["raw_attributes"],
                )

            contained = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class=sub.zone_class,
                    zone_binding_method='contained',
                    zoning_code=COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT d.zone_class, d.zone_code
                        FROM zoning_districts d
                        WHERE d.jurisdiction_id=$1::uuid
                          AND d.geom IS NOT NULL
                          AND ST_Within(ST_Centroid(p.geom), d.geom)
                        ORDER BY d.id
                        LIMIT 1
                    ) zd
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid,
            )
            print(f"[spatial] contained updated {int(contained.split()[-1])}")

            binding_label = f"nearest_{int(round(nearest_within_meters))}m"
            nearest = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class=sub.zone_class,
                    zone_binding_method=$2,
                    zoning_code=COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT d.zone_class, d.zone_code
                        FROM zoning_districts d
                        WHERE d.jurisdiction_id=$1::uuid
                          AND d.geom IS NOT NULL
                          AND ST_DWithin(
                              d.geom::geography,
                              ST_Centroid(p.geom)::geography,
                              $3
                          )
                        ORDER BY ST_Distance(
                            d.geom::geography,
                            ST_Centroid(p.geom)::geography
                        )
                        LIMIT 1
                    ) zd
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid,
                binding_label,
                float(nearest_within_meters),
            )
            print(f"[spatial] {binding_label} updated {int(nearest.split()[-1])}")

            await _update_wilton_bbox(conn, jid)

            parcel_stats = await conn.fetchrow(
                """SELECT COUNT(*) AS total,
                          COUNT(*) FILTER (
                              WHERE zoning_code IS NOT NULL
                                AND btrim(zoning_code) <> ''
                          ) AS bound,
                          COUNT(*) FILTER (
                              WHERE zone_binding_method='contained'
                          ) AS contained,
                          COUNT(*) FILTER (
                              WHERE zone_binding_method LIKE 'nearest_%'
                          ) AS nearest
                   FROM parcels WHERE jurisdiction_id=$1::uuid""",
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
            coverage = (
                100.0 * parcel_stats["bound"] / parcel_stats["total"]
                if parcel_stats["total"]
                else 0.0
            )
            nearest_pct = (
                100.0 * parcel_stats["nearest"] / parcel_stats["total"]
                if parcel_stats["total"]
                else 0.0
            )
            print("\n=== 5-GATE ===")
            print(
                f"GATE 1 cov {coverage:.1f}% (>=70%) - "
                f"{'PASS' if coverage >= 70 else 'SUB'}"
            )
            print(
                f"GATE 2 near {nearest_pct:.1f}% (<30%) - "
                f"{'PASS' if nearest_pct < 30 else 'OVER'}"
            )
            print(f"GATE 3 raw empty {empty_raw} - {'PASS' if empty_raw == 0 else 'FAIL'}")
            print(
                f"GATE 4 districts {district_count} - "
                f"{'PASS' if district_count > 0 else 'FAIL'}"
            )
            print("GATE 5 bbox populated")
            print(
                f"  parcels {parcel_stats['total']:,} bound {parcel_stats['bound']:,} "
                f"contained {parcel_stats['contained']:,} "
                f"nearest {parcel_stats['nearest']:,}"
            )

            codes = await conn.fetch(
                """SELECT zoning_code, COUNT(*) AS n
                   FROM parcels
                   WHERE jurisdiction_id=$1::uuid
                     AND zoning_code IS NOT NULL
                     AND btrim(zoning_code) <> ''
                   GROUP BY 1
                   ORDER BY 2 DESC, 1""",
                jid,
            )
            print(f"\nDistribution ({len(codes)}):")
            for code in codes:
                print(f"  {code['zoning_code']:15s} {code['n']:>5,}")

            if dry_run:
                raise _RollbackForDryRun()

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    return 0


async def _source_check_only() -> int:
    async with httpx.AsyncClient(timeout=120.0) as client:
        await _source_freshness_check(client)
        features = await _fetch_zoning_features(client)
    rows = _build_district_rows(features)
    distinct = sorted({row["zone_code"] for row in rows})
    print(f"[source] full fetch features={len(features)} rows={len(rows)}")
    print(f"[source] distinct codes ({len(distinct)}): {distinct}")
    if len(rows) < MIN_ZONING_ROWS_FOR_FIRE:
        raise RuntimeError(
            f"source check failed - only {len(rows)} usable zoning rows"
        )
    print("\n(NO DB WRITES - source freshness only.)")
    return 0


class _RollbackForDryRun(Exception):
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()

    if args.source_check_only:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        raise SystemExit(asyncio.run(_source_check_only()))

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
    raise SystemExit(
        asyncio.run(_run(args.nearest_within_meters, dry_run=args.dry_run))
    )
