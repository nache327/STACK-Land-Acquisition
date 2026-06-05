"""Garfield, NJ Op-5 CP2/CP3 artifact and preview-branch ingest runner.

Run from repo root:
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_garfield_adjudication.py
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_garfield_adjudication.py --cp3

The default mode writes local CP2 review artifacts only. The ``--cp3`` mode
adds a guarded Supabase preview-branch ingest for Garfield only and writes the
CP3 audit artifacts under /tmp/op5_proof/garfield.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import asyncpg
from shapely.geometry import shape

Permission = Literal["permitted", "conditional", "prohibited", "unclear"]

ROOT = Path("/tmp/op5_proof/garfield")
POLYGONS = ROOT / "polygons_labeled.geojson"
ORDINANCE_SECTIONS = ROOT / "ordinance_sections.json"
MATRIX_ROWS = ROOT / "matrix_rows.json"
LOW_CONFIDENCE_ROWS = ROOT / "low_confidence_rows.json"
CP2_SAMPLES = ROOT / "cp2_adjudication_samples.json"
PRE_CP3 = ROOT / "pre_cp3_snapshot.json"
POST_CP3 = ROOT / "post_cp3_snapshot.json"
AUDIT_POST = ROOT / "audit_post_op5.json"
SPOT_CHECK = ROOT / "spot_check.json"
CP3_SUMMARY = ROOT / "cp3_summary.md"

EXPECTED_PREVIEW_REF = "bbvywbpxwsoyvdvygvyw"
BERGEN_ID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"
MUNICIPALITY = "Garfield city"

CHAPTER_URL = "https://ecode360.com/10086640"
DISTRICTS_URL = "https://ecode360.com/10086719"
USE_REGS_URL = "https://ecode360.com/10086733"
REDEVELOPMENT_TABLE_URL = "https://ecode360.com/attachment/325186/GA0711-341c%20Table%20of%20Redevelopment%20Zones.pdf"


@dataclass(frozen=True)
class Citation:
    section: str
    quote: str
    url: str


@dataclass(frozen=True)
class Adjudication:
    zone_code: str
    self_storage: Permission
    mini_warehouse: Permission
    light_industrial: Permission
    luxury_garage_condo: Permission
    confidence: float
    notes: str
    citations: list[Citation]


DISTRICTS = Citation(
    "Garfield Code § 341-3",
    "Garfield enumerates R-1A, R-1, R-2, R-TH, R-3, B-1, B-2, B-2D, LM, I, and CA districts.",
    DISTRICTS_URL,
)

ANY_DISTRICT = Citation(
    "Garfield Code § 341-12",
    "Uses permitted in any district are customary accessory uses, public parks/playgrounds, government/school uses, limited excavation, agriculture, religious uses, and fences.",
    USE_REGS_URL,
)

R1A = Citation(
    "Garfield Code § 341-14",
    "In an R-1A District, no building shall be used for any purpose other than one-family dwelling.",
    USE_REGS_URL,
)

R1 = Citation(
    "Garfield Code § 341-15",
    "R-1 permits one-family dwellings, two-family dwellings, home occupations, and resident professional offices/studios.",
    USE_REGS_URL,
)

R2_R3_RTH = Citation(
    "Garfield Code §§ 341-16 through 341-18",
    "R-2, R-TH, and R-3 list residential, multifamily/townhouse, municipal, park, worship, and related accessory/office-townhouse uses.",
    USE_REGS_URL,
)

B1 = Citation(
    "Garfield Code § 341-19",
    "B-1 permits neighborhood retail/service, bakeries, restaurants, offices, financial institutions, certain dwellings, tattoo parlors, and fixed-location food trucks.",
    USE_REGS_URL,
)

B2 = Citation(
    "Garfield Code § 341-20",
    "B-2 permits B-1 uses, incidental retail manufacturing, small printing/newspaper plants, commercial parking, and limited automotive uses.",
    USE_REGS_URL,
)

CA = Citation(
    "Garfield Code § 341-22",
    "In a CA District, permitted uses are commercial antennas.",
    USE_REGS_URL,
)

LM_STORAGE = Citation(
    "Garfield Code § 341-23(A)(4)",
    "LM permits storing, warehousing, shipping, transferring and wholesale distribution of closed-container goods within buildings/loading platforms.",
    USE_REGS_URL,
)

LM_LIGHT_MANUFACTURING = Citation(
    "Garfield Code § 341-23(A)(2)",
    "LM permits manufacture, compounding, processing or treatment of materials/products subject to performance limits.",
    USE_REGS_URL,
)

LM_PROHIBITED = Citation(
    "Garfield Code § 341-23(B)",
    "LM prohibits listed high-impact trades and open-air storage yards, including junk-related storage and open-air building-material/coal/coke storage yards.",
    USE_REGS_URL,
)

PARK_DISTRICT = Citation(
    "Garfield zoning map legend / § 341-12",
    "P is mapped as parkland; public parks and playgrounds are permitted in any district.",
    "https://www.garfieldnj.org/_Content/pdf/zoning.pdf",
)

REDEVELOPMENT = Citation(
    "Garfield Code Ch. 341 Attachment 3",
    "The redevelopment-zone table lists multiple separate redevelopment plans by ordinance, block, and lot rather than one uniform RDVT use schedule.",
    REDEVELOPMENT_TABLE_URL,
)


def all_prohibited(zone_code: str, notes: str, citations: list[Citation], confidence: float = 0.9) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=confidence,
        notes=notes,
        citations=citations,
    )


ADJUDICATIONS: dict[str, Adjudication] = {
    "R-1A": all_prohibited("R-1A", "One-family residential district; target storage/industrial uses are not listed.", [R1A, ANY_DISTRICT], 0.93),
    "R-1": all_prohibited("R-1", "Low-density residential district; target storage/industrial uses are not listed.", [R1, ANY_DISTRICT], 0.92),
    "R-2": all_prohibited("R-2", "Residential/multifamily district; target storage/industrial uses are not listed.", [R2_R3_RTH, ANY_DISTRICT], 0.91),
    "R-3": all_prohibited("R-3", "High-density multifamily residential district; target storage/industrial uses are not listed.", [R2_R3_RTH, ANY_DISTRICT], 0.91),
    "R-TH": all_prohibited("R-TH", "Townhouse/multifamily district; target storage/industrial uses are not listed.", [R2_R3_RTH, ANY_DISTRICT], 0.9),
    "B-1": all_prohibited("B-1", "Neighborhood retail/services district; principal storage, warehouse, industrial, and garage-condo uses are not listed.", [B1, ANY_DISTRICT], 0.89),
    "B-2": all_prohibited("B-2", "General retail district allows retail/service and narrow incidental manufacturing/parking uses, not principal storage or light industrial.", [B2, B1, ANY_DISTRICT], 0.87),
    "CA": all_prohibited("CA", "Commercial antenna district; target storage/industrial uses are not listed.", [CA, ANY_DISTRICT], 0.92),
    "P": all_prohibited("P", "Mapped parkland/open-space district; target storage/industrial uses are not park or public-playground uses.", [PARK_DISTRICT, ANY_DISTRICT], 0.88),
    "LM": Adjudication(
        zone_code="LM",
        self_storage="permitted",
        mini_warehouse="permitted",
        light_industrial="permitted",
        luxury_garage_condo="unclear",
        confidence=0.82,
        notes=(
            "LM expressly permits enclosed storing/warehousing/wholesale distribution and light-manufacturing-style processing. "
            "Self-storage/mini-warehouse are treated as permitted under the broad enclosed storage/warehousing allowance. "
            "Luxury garage condo remains unclear because private garage condominium use is not specifically named."
        ),
        citations=[LM_STORAGE, LM_LIGHT_MANUFACTURING, LM_PROHIBITED],
    ),
    "RDVT": Adjudication(
        zone_code="RDVT",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.35,
        notes=(
            "RDVT map labels correspond to multiple parcel-specific redevelopment plans in Attachment 3. "
            "A plan-by-plan read is required before classifying target uses."
        ),
        citations=[REDEVELOPMENT, DISTRICTS],
    ),
}


def load_db_url() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if not raw:
        raise RuntimeError("DATABASE_URL not found in environment or .env")
    return raw.replace("postgresql+asyncpg://", "postgresql://")


def assert_preview_url(url: str) -> None:
    if EXPECTED_PREVIEW_REF not in url:
        raise RuntimeError(f"Refusing CP3 ingest: DATABASE_URL is not preview ref {EXPECTED_PREVIEW_REF}")


def load_polygon_counts() -> dict[str, dict[str, object]]:
    fc = json.loads(POLYGONS.read_text())
    counts: dict[str, dict[str, object]] = {}
    for feature in fc["features"]:
        props = feature["properties"]
        code = props.get("zone_code")
        if not code:
            continue
        entry = counts.setdefault(code, {"polygon_count": 0, "feature_indexes": []})
        entry["polygon_count"] = int(entry["polygon_count"]) + 1
        entry["feature_indexes"].append(props.get("feature_index"))
    return counts


def write_ordinance_sections() -> None:
    citations = {
        c.section: c
        for item in ADJUDICATIONS.values()
        for c in item.citations
    }
    sections = [
        {
            "section_id": section,
            "heading": section,
            "text": citation.quote,
            "url": citation.url,
            "district_codes": sorted(
                code for code, item in ADJUDICATIONS.items() if any(c.section == section for c in item.citations)
            ),
        }
        for section, citation in sorted(citations.items())
    ]
    ORDINANCE_SECTIONS.write_text(json.dumps(sections, indent=2))


def row_for(code: str, polygon_info: dict[str, object]) -> dict[str, object]:
    item = ADJUDICATIONS[code]
    row = asdict(item)
    row["citations"] = [asdict(c) for c in item.citations]
    row["polygon_count"] = polygon_info["polygon_count"]
    row["polygon_feature_indexes"] = polygon_info["feature_indexes"]
    row["classification_source"] = "human"
    row["requires_review"] = item.confidence < 0.85 or "unclear" in {
        item.self_storage,
        item.mini_warehouse,
        item.light_industrial,
        item.luxury_garage_condo,
    }
    return row


def write_cp2() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    polygon_counts = load_polygon_counts()
    missing = sorted(set(polygon_counts) - set(ADJUDICATIONS))
    if missing:
        raise RuntimeError(f"Missing Garfield adjudications for CP1 zone codes: {missing}")

    write_ordinance_sections()
    rows = [row_for(code, polygon_counts[code]) for code in sorted(polygon_counts)]
    low_confidence = [row for row in rows if row["requires_review"]]

    MATRIX_ROWS.write_text(json.dumps(rows, indent=2))
    LOW_CONFIDENCE_ROWS.write_text(json.dumps(low_confidence, indent=2))

    rng = random.Random(341)
    samples = rng.sample(rows, min(5, len(rows)))
    CP2_SAMPLES.write_text(json.dumps(samples, indent=2))

    return {
        "matrix_rows": len(rows),
        "low_confidence_rows": len(low_confidence),
        "samples": len(samples),
        "outputs": {
            "ordinance_sections": str(ORDINANCE_SECTIONS),
            "matrix_rows": str(MATRIX_ROWS),
            "low_confidence_rows": str(LOW_CONFIDENCE_ROWS),
            "cp2_samples": str(CP2_SAMPLES),
        },
    }


def zone_class(code: str) -> str:
    if code.startswith("R-"):
        return "residential"
    if code in {"B-1", "B-2", "CA"}:
        return "commercial"
    if code == "LM":
        return "industrial"
    if code == "P":
        return "open_space"
    if code == "RDVT":
        return "special"
    return "unknown"


async def snapshot(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        WITH garfield AS (
            SELECT * FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2
        )
        SELECT
            COUNT(*)::int AS parcels,
            COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '')::int AS zoned,
            COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zone_use_matrix z
                    WHERE z.jurisdiction_id = garfield.jurisdiction_id
                      AND z.zone_code = garfield.zoning_code
                      AND z.municipality = $2
                      AND z.deleted_at IS NULL
                )
            )::int AS matrix_matches,
            COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM zone_use_matrix z
                    WHERE z.jurisdiction_id = garfield.jurisdiction_id
                      AND z.zone_code = garfield.zoning_code
                      AND z.municipality = $2
                      AND z.deleted_at IS NULL
                      AND z.self_storage::text <> 'unclear'
                )
            )::int AS self_storage_classified
        FROM garfield
        """,
        BERGEN_ID,
        MUNICIPALITY,
    )
    districts = await conn.fetchval(
        """
        SELECT COUNT(*)::int
        FROM zoning_districts
        WHERE jurisdiction_id=$1::uuid
          AND raw_attributes->>'op5_town' = 'garfield'
        """,
        BERGEN_ID,
    )
    matrix = await conn.fetchval(
        """
        SELECT COUNT(*)::int
        FROM zone_use_matrix
        WHERE jurisdiction_id=$1::uuid
          AND municipality=$2
          AND deleted_at IS NULL
        """,
        BERGEN_ID,
        MUNICIPALITY,
    )
    out = dict(row)
    out["op5_garfield_zoning_districts"] = districts
    out["garfield_matrix_rows"] = matrix
    return out


async def ingest_districts(conn: asyncpg.Connection) -> int:
    fc = json.loads(POLYGONS.read_text())
    await conn.execute(
        """
        DELETE FROM zoning_districts
        WHERE jurisdiction_id=$1::uuid
          AND raw_attributes->>'op5_town' = 'garfield'
        """,
        BERGEN_ID,
    )
    inserted = 0
    for feature in fc["features"]:
        props = feature["properties"]
        code = props.get("zone_code")
        if not code:
            continue
        geom_json = json.dumps(feature["geometry"])
        geom_hash = hashlib.sha256(shape(feature["geometry"]).wkb).hexdigest()
        raw = {
            **props,
            "op5_town": "garfield",
            "op5_stage": "cp3",
            "op5_source": str(POLYGONS),
        }
        await conn.execute(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class, raw_attributes,
                geom, centroid, source, confidence, human_reviewed, geom_hash, updated_at
            )
            VALUES (
                $1::uuid, $2, $3, $4::zone_class_enum, $5::jsonb,
                ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON($6)), 4326),
                ST_PointOnSurface(ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON($6)), 4326)),
                'ordinance'::zone_source_enum, $7, false, $8, now()
            )
            ON CONFLICT ON CONSTRAINT uq_zoning_districts_jur_code_hash DO NOTHING
            """,
            BERGEN_ID,
            code,
            code,
            zone_class(code),
            json.dumps(raw),
            geom_json,
            float(props.get("confidence") or 0.0),
            geom_hash,
        )
        inserted += 1
    return inserted


async def ingest_matrix(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    inserted = 0
    updated = 0
    for row in rows:
        existing_id = await conn.fetchval(
            """
            SELECT id
            FROM zone_use_matrix
            WHERE jurisdiction_id=$1::uuid
              AND zone_code=$2
              AND COALESCE(municipality, '')=COALESCE($3, '')
            LIMIT 1
            """,
            BERGEN_ID,
            row["zone_code"],
            MUNICIPALITY,
        )
        if existing_id:
            await conn.execute(
                """
                UPDATE zone_use_matrix
                SET
                    zone_name = $2,
                    municipality = $3,
                    self_storage = $4::use_permission_enum,
                    mini_warehouse = $5::use_permission_enum,
                    light_industrial = $6::use_permission_enum,
                    luxury_garage_condo = $7::use_permission_enum,
                    citations = $8::jsonb,
                    confidence = $9,
                    human_reviewed = true,
                    notes = $10,
                    classification_source = 'human'::classification_source_enum,
                    deleted_at = NULL,
                    updated_at = now()
                WHERE id = $1
                """,
                existing_id,
                row["zone_code"],
                MUNICIPALITY,
                row["self_storage"],
                row["mini_warehouse"],
                row["light_industrial"],
                row["luxury_garage_condo"],
                json.dumps(row["citations"]),
                float(row["confidence"]),
                row["notes"],
            )
            updated += 1
        else:
            await conn.execute(
                """
                INSERT INTO zone_use_matrix (
                    jurisdiction_id, zone_code, zone_name, municipality,
                    self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                    citations, confidence, human_reviewed, notes, classification_source,
                    deleted_at, updated_at
                )
                VALUES (
                    $1::uuid, $2, $2, $3,
                    $4::use_permission_enum, $5::use_permission_enum,
                    $6::use_permission_enum, $7::use_permission_enum,
                    $8::jsonb, $9, true, $10, 'human'::classification_source_enum,
                    NULL, now()
                )
                """,
                BERGEN_ID,
                row["zone_code"],
                MUNICIPALITY,
                row["self_storage"],
                row["mini_warehouse"],
                row["light_industrial"],
                row["luxury_garage_condo"],
                json.dumps(row["citations"]),
                float(row["confidence"]),
                row["notes"],
            )
            inserted += 1
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


async def spatial_join_parcels(conn: asyncpg.Connection) -> int:
    status = await conn.execute(
        """
        WITH matches AS (
            SELECT p.id, zd.zone_code
            FROM parcels p
            JOIN LATERAL (
                SELECT zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = p.jurisdiction_id
                  AND zd.raw_attributes->>'op5_town' = 'garfield'
                  AND p.centroid IS NOT NULL
                  AND ST_Covers(zd.geom, p.centroid)
                ORDER BY ST_Area(zd.geom::geography) ASC, zd.id ASC
                LIMIT 1
            ) zd ON true
            WHERE p.jurisdiction_id=$1::uuid
              AND p.city=$2
        )
        UPDATE parcels p
        SET zoning_code = matches.zone_code
        FROM matches
        WHERE p.id = matches.id
        """,
        BERGEN_ID,
        MUNICIPALITY,
    )
    return int(status.split()[-1])


async def audit(conn: asyncpg.Connection) -> dict[str, Any]:
    snap = await snapshot(conn)
    parcels = max(1, int(snap["parcels"]))
    zoned = int(snap["zoned"])
    matrix_matches = int(snap["matrix_matches"])
    classified = int(snap["self_storage_classified"])
    zone_counts = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*)::int AS parcels
        FROM parcels
        WHERE jurisdiction_id=$1::uuid
          AND city=$2
          AND zoning_code IS NOT NULL
        GROUP BY zoning_code
        ORDER BY parcels DESC, zoning_code
        """,
        BERGEN_ID,
        MUNICIPALITY,
    )
    return {
        **snap,
        "parcel_zoning_code_coverage_pct": round(100 * zoned / parcels, 1),
        "matrix_match_pct_of_zoned": round(100 * matrix_matches / max(1, zoned), 1),
        "self_storage_classified_pct_of_zoned": round(100 * classified / max(1, zoned), 1),
        "zone_counts": [dict(r) for r in zone_counts],
    }


async def spot_check(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        """
        SELECT
            p.id,
            p.apn,
            p.address,
            p.zoning_code AS parcel_zoning_code,
            zd.zone_code AS containing_zone_code,
            z.self_storage::text AS self_storage,
            z.mini_warehouse::text AS mini_warehouse,
            z.light_industrial::text AS light_industrial,
            z.luxury_garage_condo::text AS luxury_garage_condo
        FROM parcels p
        JOIN LATERAL (
            SELECT zone_code
            FROM zoning_districts zd
            WHERE zd.jurisdiction_id = p.jurisdiction_id
              AND zd.raw_attributes->>'op5_town' = 'garfield'
              AND p.centroid IS NOT NULL
              AND ST_Covers(zd.geom, p.centroid)
            ORDER BY ST_Area(zd.geom::geography) ASC, zd.id ASC
            LIMIT 1
        ) zd ON true
        LEFT JOIN zone_use_matrix z
          ON z.jurisdiction_id = p.jurisdiction_id
         AND z.zone_code = p.zoning_code
         AND z.municipality = $2
         AND z.deleted_at IS NULL
        WHERE p.jurisdiction_id=$1::uuid
          AND p.city=$2
          AND p.zoning_code IS NOT NULL
        ORDER BY random()
        LIMIT 10
        """,
        BERGEN_ID,
        MUNICIPALITY,
    )
    checks = []
    passed = 0
    for r in rows:
        d = dict(r)
        d["pass"] = bool(d["parcel_zoning_code"] == d["containing_zone_code"] and d["self_storage"])
        passed += int(d["pass"])
        checks.append(d)
    return {
        "sample_method": "fresh_random_order_by_random_zoned_garfield_parcels",
        "sample_size": len(checks),
        "passed": passed,
        "pass_pct": round(100 * passed / max(1, len(checks)), 1),
        "checks": checks,
    }


async def run_cp3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    url = load_db_url()
    assert_preview_url(url)
    started = time.time()
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        pre = await snapshot(conn)
        PRE_CP3.write_text(json.dumps(pre, indent=2))
        async with conn.transaction():
            inserted_districts = await ingest_districts(conn)
            matrix_result = await ingest_matrix(conn, rows)
            updated_parcels = await spatial_join_parcels(conn)
        post = await snapshot(conn)
        POST_CP3.write_text(json.dumps(post, indent=2))
        audit_result = await audit(conn)
        AUDIT_POST.write_text(json.dumps(audit_result, indent=2))
        spot_result = await spot_check(conn)
        SPOT_CHECK.write_text(json.dumps(spot_result, indent=2))
    finally:
        await conn.close()

    wall = time.time() - started
    coverage = audit_result["parcel_zoning_code_coverage_pct"]
    spot_pct = spot_result["pass_pct"]
    summary = f"""# Garfield CP3 Summary

Status: STOPPED at CP3 for review.

Target:
- Jurisdiction: `Bergen County, NJ` / `{BERGEN_ID}`
- Municipality scope: `{MUNICIPALITY}`
- Database ref used: `{EXPECTED_PREVIEW_REF}`

Execution:
- Upload-equivalent ingest source: `{POLYGONS}`
- Inserted zoning districts: `{inserted_districts}` of `{len(json.loads(POLYGONS.read_text())['features'])}` features
- Spatial join result: `UPDATE {updated_parcels}`
- Matrix rows applied with municipality scope: inserted `{matrix_result['inserted']}`, updated `{matrix_result['updated']}`, total `{matrix_result['total']}`
- Wall clock seconds: `{wall:.2f}`

Garfield audit:
- Parcels: `{audit_result['parcels']}`
- Parcels with zoning code: `{audit_result['zoned']}` (`{coverage}%`)
- Parcels with matrix match: `{audit_result['matrix_matches']}` (`{audit_result['matrix_match_pct_of_zoned']}%` of zoned)
- Self-storage classified pct: `{audit_result['self_storage_classified_pct_of_zoned']}%`

Spot-check:
- Method: fresh random sample of zoned Garfield parcels
- Sample size: `{spot_result['sample_size']}`
- Passed: `{spot_result['passed']}` / `{spot_result['sample_size']}` (`{spot_pct}%`)

Artifacts:
- `{AUDIT_POST}`
- `{SPOT_CHECK}`
- `{PRE_CP3}`
- `{POST_CP3}`

Notes:
- Direct SQL/PostGIS ingest was used against the configured Supabase preview branch only.
- Writes were scoped to OP5-marked Garfield zoning districts, Garfield matrix rows, and `{MUNICIPALITY}` parcels.
- No prod promotion, PR, merge, coordination edit, or other-town ingest was run.
"""
    CP3_SUMMARY.write_text(summary)
    return {
        "inserted_districts": inserted_districts,
        "spatial_join_updated": updated_parcels,
        "matrix": matrix_result,
        "audit": audit_result,
        "spot_check": spot_result,
        "wall_clock_seconds": round(wall, 2),
        "cp3_summary": str(CP3_SUMMARY),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cp3", action="store_true", help="Run guarded preview-branch CP3 ingest/audit after CP2 artifacts")
    args = parser.parse_args()

    cp2 = write_cp2()
    result: dict[str, Any] = {"cp2": cp2}
    if args.cp3:
        rows = json.loads(MATRIX_ROWS.read_text())
        result["cp3"] = asyncio.run(run_cp3(rows))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
