"""Phase 7G.x — Winnetka IL Village zoning Class B per-muni ingest.

Per Diagnostic 2026-06-23 (commit 6a07d03 on
adarench/cook-il-winnetka-source-probe): Winnetka publishes a clean
GIS Consortium FeatureServer-equivalent MapServer zoning layer —
64/64 polygons with non-null ZONED, 10 distinct codes.

Pattern: Westchester Class B proof primitive (PR #214,
ingest_westchester_class_b_proof.py) + King WA per-muni
jurisdictioning (PR #285). Winnetka gets its OWN jurisdiction_id,
NOT a Cook County umbrella sub-filter — Cook umbrella stays HALT
(unincorporated-only zoning), Winnetka flips as a per-muni.

Source: ags.gisconsortium.org/.../VWN/AGOL_VWN_Project/MapServer/0
  - 64 polygons (small, queryable)
  - ZONED field, 100% non-null
  - 10 distinct codes: B1, B2, C1, C2, D, R1, R2, R3, R4, R5
  - Spatial reference: IL StatePlane East (wkid 102671);
    we request outSR=4326 to reproject server-side.

GATE: this script REFUSES TO FIRE unless:
  - 'Village of Winnetka, IL' jurisdiction exists
  - Parcels exist under that JID (Cook IL headless ingest + per-muni
    PATH 1 transparent re-jurisdictioning must have landed first)

IDEMPOTENCY: wraps the full pipeline (DELETE existing rows + reset
parcel bindings + INSERT + spatial backfill + bbox update) in a
single transaction. Re-firing is safe — no double-INSERT footgun
(lesson from Fountain Hills 7B.3).
"""
from __future__ import annotations
import argparse, asyncio, json, logging, os, sys
from pathlib import Path
import asyncpg, dotenv, httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
logger = logging.getLogger("winnetka_il")

MUNI = "Winnetka"
JURISDICTION_NAME = "Village of Winnetka, IL"
LAYER = "https://ags.gisconsortium.org/arcgis/rest/services/VWN/AGOL_VWN_Project/MapServer/0"
ZCODE = "ZONED"
RAW_KEYS = ("OBJECTID", "ZONED", "ZONINGDESCRIPTION", "ZONINGDOCUMENT", "DATEMODIFIED",
            "Shape__Area", "Shape__Length")
# Winnetka village bbox sanity envelope. Actual extent observed via
# PATH 1 re-jurisdictioning dry-run on 2026-06-23:
# [-87.78986, 42.08486, -87.71090, 42.12839]. Envelope catches
# gross errors (wrong-county ingest), not tight-fit.
BBOX_LON = (-87.80, -87.69)
BBOX_LAT = (42.07, 42.14)
# Refuse to fire if parcel count is below this — guard against
# firing before headless Cook IL ingest + per-muni registration landed.
MIN_PARCELS_FOR_FIRE = 100


def _db_url(): return DATABASE_URL.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")


def _rings_to_wkt(rings):
    ws = []
    for r in rings:
        if len(r) < 4: continue
        ws.append("((" + ", ".join(f"{p[0]} {p[1]}" for p in r) + "))")
    if not ws: raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ws) + ")"


async def _resolve_jid(conn) -> str:
    """Look up Winnetka JID by jurisdiction name. Refuse if missing."""
    jid = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE name = $1", JURISDICTION_NAME,
    )
    if not jid:
        raise SystemExit(
            f"REFUSE FIRE — jurisdiction '{JURISDICTION_NAME}' not registered. "
            f"Per-muni registration must complete first (PATH 1 transparent UPDATE "
            f"from Cook IL umbrella to a fresh Winnetka JID)."
        )
    return str(jid)


async def _gate_check(conn, jid: str) -> None:
    """Refuse to fire if parcels haven't been re-jurisdictioned yet."""
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid", jid,
    )
    if n < MIN_PARCELS_FOR_FIRE:
        raise SystemExit(
            f"REFUSE FIRE — only {n} parcels under Winnetka JID. "
            f"Cook IL headless ingest + per-muni re-jurisdictioning must complete first. "
            f"Probe showed ~4,813 Winnetka parcels expected; gate threshold {MIN_PARCELS_FOR_FIRE}."
        )
    print(f"[gate] {n:,} parcels under Winnetka JID — proceeding")


async def _fetch_features(client) -> list:
    """Page through the source layer (defensive — source has only 64 features today)."""
    features = []
    offset = 0
    while True:
        r = await client.get(f"{LAYER}/query", params={
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": 4326, "resultOffset": offset, "resultRecordCount": 1000,
            "f": "json", "orderByFields": "OBJECTID",
        })
        r.raise_for_status()
        batch = r.json().get("features", [])
        features.extend(batch)
        logger.info("fetched %d (cum %d)", len(batch), len(features))
        if len(batch) < 1000: break
        offset += 1000
    return features


async def _fire(near: float = 50.0, dry_run: bool = False) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: {MUNI} IL zoning (Class B per-muni) ===\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        feats = await _fetch_features(client)

    rows = []
    for f in feats:
        a = f.get("attributes", {})
        g = f.get("geometry")
        zc = a.get(ZCODE)
        if not g or "rings" not in g: continue
        if not zc or not str(zc).strip(): continue
        try: wkt = _rings_to_wkt(g["rings"])
        except Exception as e:
            logger.warning("skip OBJECTID=%s: %s", a.get("OBJECTID"), e); continue
        raw = {
            "source_url": LAYER, "source_kind": "arcgis_map_server",
            "ingested_at": "2026-06-23", "muni_name": MUNI, "muni_type": "village",
            "publisher": "Village of Winnetka IL (GIS Consortium hosted, Diagnostic 6a07d03)",
            "source_srid_native": 102671,
        }
        for k in RAW_KEYS:
            if k in a and a[k] is not None: raw[k] = a[k]
        rows.append({
            "zone_code": str(zc).strip(),
            "zone_name": str(a.get("ZONINGDESCRIPTION") or "").strip() or str(zc).strip(),
            "wkt": wkt,
            "raw": json.dumps(raw),
        })

    distinct = sorted({r["zone_code"] for r in rows})
    print(f"features={len(feats)} rows={len(rows)} distinct={len(distinct)}: {distinct}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, command_timeout=3600)
    try:
        jid = await _resolve_jid(conn)
        await _gate_check(conn, jid)

        # Single transaction wraps the whole pipeline — idempotency guard.
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            # Idempotency: clear prior ingest for this JID before re-insert.
            d_cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid", jid,
            )
            print(f"[idempotency] cleared {d_cleared.split()[-1]} prior zoning_districts rows")

            # Idempotency: reset bindings on this JID's parcels so the
            # backfill UPDATE re-runs cleanly. COALESCE NULLIF logic in
            # backfill would otherwise preserve stale codes from a prior fire.
            p_cleared = await conn.execute(
                """UPDATE parcels SET zoning_code = NULL, zone_class = NULL,
                          zone_binding_method = NULL
                   WHERE jurisdiction_id=$1::uuid""", jid,
            )
            print(f"[idempotency] reset bindings on {p_cleared.split()[-1]} parcels")

            print(f"\n[INSERT] {len(rows)} zoning_districts…")
            for r in rows:
                await conn.execute(
                    """INSERT INTO zoning_districts (jurisdiction_id, zone_code, zone_name,
                           zone_class, geom, raw_attributes, source)
                       VALUES ($1::uuid, $2, $3, 'unknown'::zone_class_enum,
                           ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                           $5::jsonb, 'arcgis'::zone_source_enum)""",
                    jid, r["zone_code"], r["zone_name"], r["wkt"], r["raw"],
                )
            print(f"[INSERT] {len(rows)} committed")

            # Pass 1: ST_Within (centroid contained in district).
            s1 = await conn.execute("""
                UPDATE parcels target SET zone_class=sub.zone_class,
                    zone_binding_method='contained',
                    zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
                FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                      LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                               WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                                 AND ST_Within(ST_Centroid(p.geom), zd.geom)
                               ORDER BY zd.id LIMIT 1) m
                      WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL) sub
                WHERE target.id = sub.parcel_id""", jid)
            print(f"[spatial] contained UPDATEd {int(s1.split()[-1])}")

            # Pass 2: ST_DWithin nearest fallback for the remainder.
            bl = f"nearest_{int(round(near))}m"
            s2 = await conn.execute("""
                UPDATE parcels target SET zone_class=sub.zone_class,
                    zone_binding_method=$2,
                    zoning_code = COALESCE(NULLIF(target.zoning_code,''), sub.zone_code)
                FROM (SELECT p.id AS parcel_id, m.zone_class, m.zone_code FROM parcels p,
                      LATERAL (SELECT zd.zone_class, zd.zone_code FROM zoning_districts zd
                               WHERE zd.jurisdiction_id=$1::uuid AND zd.geom IS NOT NULL
                                 AND ST_DWithin(zd.geom::geography, ST_Centroid(p.geom)::geography, $3)
                               ORDER BY ST_Distance(zd.geom::geography, ST_Centroid(p.geom)::geography) LIMIT 1) m
                      WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL
                        AND p.zone_binding_method IS NULL) sub
                WHERE target.id = sub.parcel_id""", jid, bl, float(near))
            print(f"[spatial] {bl} UPDATEd {int(s2.split()[-1])}")

            # Inline bbox update (per-muni jurisdictions.bbox, PR #261).
            ext = await conn.fetchrow(
                """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                          ST_YMin(ST_Extent(geom)) AS miny,
                          ST_XMax(ST_Extent(geom)) AS maxx,
                          ST_YMax(ST_Extent(geom)) AS maxy
                   FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""", jid,
            )
            bbox = [float(ext["minx"]), float(ext["miny"]),
                    float(ext["maxx"]), float(ext["maxy"])]
            if not (BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
                    and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]):
                raise RuntimeError(
                    f"bbox {bbox} outside Winnetka envelope "
                    f"(lon {BBOX_LON}, lat {BBOX_LAT}) — abort"
                )
            await conn.execute(
                "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
                jid, json.dumps(bbox),
            )
            print(f"\nbbox {bbox}")

            if dry_run:
                raise _RollbackForDryRun()

        # 5-GATE verdict (post-commit read).
        p = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
                      COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                      COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
               FROM parcels WHERE jurisdiction_id=$1::uuid""", jid,
        )
        d = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid", jid,
        )
        empty = await conn.fetchval(
            """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid
               AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)""", jid,
        )
        cov = 100.0 * p["bound"] / p["total"] if p["total"] else 0
        near_pct = 100.0 * p["nearest"] / p["total"] if p["total"] else 0
        print(f"\n=== 5-GATE ===")
        print(f"GATE 1 cov {cov:.1f}% (≥70%) — {'PASS' if cov>=70 else 'SUB'}")
        print(f"GATE 2 near {near_pct:.1f}% (<30%) — {'PASS' if near_pct<30 else 'OVER'}")
        print(f"GATE 3 raw empty {empty} — {'PASS' if empty==0 else 'FAIL'}")
        print(f"GATE 4 districts {d} — {'PASS' if d>0 else 'FAIL'}")
        print(f"GATE 5 bbox populated")
        print(f"  parcels {p['total']:,} bound {p['bound']:,} "
              f"contained {p['contained']:,} nearest {p['nearest']:,}")

        codes = await conn.fetch(
            """SELECT zoning_code, COUNT(*) AS n FROM parcels
               WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC""", jid,
        )
        print(f"\nDistribution ({len(codes)}):")
        for r in codes:
            print(f"  {r['zoning_code']:15s} {r['n']:>5,}")

    except _RollbackForDryRun:
        print("\n(DRY-RUN — transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the tx context manager to trigger rollback."""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="Run the full pipeline inside a transaction, then ROLLBACK. "
                        "Useful for fire-readiness verification once Cook IL parcels land.")
    p.add_argument("--nearest-within-meters", type=float, default=50.0)
    a = p.parse_args()
    if not a.dry_run and not a.i_know_this_writes_to_prod:
        print("Refusing — pass --dry-run for transactional rehearsal "
              "or --i-know-this-writes-to-prod to actually fire.",
              file=sys.stderr)
        sys.exit(2)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_fire(near=a.nearest_within_meters, dry_run=a.dry_run)))
