"""Hackensack, NJ CP2/CP3 adjudication and preview-branch ingest.

Run from repo root:
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_hackensack_adjudication.py
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_hackensack_adjudication.py --apply-cp3

This Op-5 proof script is deliberately scoped to Hackensack. It writes CP2/CP3
artifacts under /tmp/op5_proof/hackensack and, in --apply-cp3 mode, touches only
the configured Supabase preview branch plus Bergen County rows for
municipality/city "Hackensack city".
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings

Permission = Literal["permitted", "conditional", "prohibited", "unclear"]

ROOT = Path("/tmp/op5_proof/hackensack")
POLYGONS = ROOT / "polygons_labeled.geojson"
ORDINANCE_SECTIONS = ROOT / "ordinance_sections.json"
MATRIX_ROWS = ROOT / "matrix_rows.json"
LOW_CONFIDENCE_ROWS = ROOT / "low_confidence_rows.json"
CP2_SAMPLES = ROOT / "cp2_adjudication_samples.json"
AUDIT_POST_OP5 = ROOT / "audit_post_op5.json"
SPOT_CHECK = ROOT / "spot_check.json"
CP3_SUMMARY = ROOT / "cp3_summary.md"

EXPECTED_PREVIEW_REF = "bbvywbpxwsoyvdvygvyw"
JURISDICTION_NAME = "Bergen County, NJ"
MUNICIPALITY = "Hackensack city"
SOURCE_TAG = "op5_hackensack_cp3"

CHAPTER_URL = "https://ecode360.com/13166949"
DISTRICTS_URL = "https://ecode360.com/38524535"
ARTICLE_VII_URL = "https://www.zoneomics.com/code/hackensack-NJ/chapter_7"
RESIDENTIAL_INSERT_URL = "https://ecode360.com/attachment/323733/HA0454-175a%20Insert%201.pdf"
NONRESIDENTIAL_INSERT_URL = "https://ecode360.com/attachment/323733/HA0454-175b%20Insert%202.pdf"


@dataclass(frozen=True)
class Citation:
    section: str
    quote: str
    url: str


@dataclass(frozen=True)
class Adjudication:
    zone_code: str
    zone_name: str
    zone_class: str
    self_storage: Permission
    mini_warehouse: Permission
    light_industrial: Permission
    luxury_garage_condo: Permission
    confidence: float
    notes: str
    cited_subsection: str
    citations: list[Citation]


GENERAL_USE_RESTRICTION = Citation(
    "Hackensack Code § 175-7.2(A)(3)",
    "Any use not specifically identified in Insert 1 or Insert 2 as permitted or conditional is prohibited.",
    ARTICLE_VII_URL,
)

RESIDENTIAL_INSERT = Citation(
    "Hackensack Code 175 Attachment 1, Insert 1",
    "Residential zones list residential, civic, utility, assisted-living, office-limited, and accessory residential uses; blank means prohibited.",
    RESIDENTIAL_INSERT_URL,
)

NONRESIDENTIAL_INSERT = Citation(
    "Hackensack Code 175 Attachment 2, Insert 2",
    "Nonresidential zones list business, office, retail, service, civic, and M-1 industrial uses; blank means prohibited.",
    NONRESIDENTIAL_INSERT_URL,
)

M1_WAREHOUSE = Citation(
    "Hackensack Code 175 Attachment 2, M-1 uses",
    "M-1 permits light manufacturing, warehouse, wholesale business, truck and bus terminals and yards, and related industrial uses.",
    NONRESIDENTIAL_INSERT_URL,
)

DISTRICT_DESIGNATIONS = Citation(
    "Hackensack Code § 175-5.1",
    "Districts include R residential zones, B business zones, HRO High-Rise Office, and M-1 Manufacturing.",
    DISTRICTS_URL,
)


ZONE_NAMES = {
    "R100": "R-100 Single-Family",
    "R60": "R-60 Single-Family Residential",
    "R50": "R-50 Single-Family Residential",
    "R2": "R-2 Single- and Two-Family Residential",
    "R2B": "R-2B Single-, Two-Family and Townhouse",
    "R3": "R-3 High-Density Multifamily Residential",
    "R3A": "R-3A Medium-Density Multifamily Residential",
    "R3B": "R-3B Medium-Density Multifamily and Offices",
    "B1": "B-1 Neighborhood Business",
    "B2": "B-2 Central Business District",
    "B3": "B-3 General Business",
    "B4": "B-4 Shopping Center District",
    "HRO": "HRO High-Rise Office",
    "M1": "M-1 Manufacturing",
}


def prohibited(
    zone_code: str,
    zone_class: str,
    notes: str,
    citations: list[Citation],
    confidence: float = 0.9,
) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        zone_name=ZONE_NAMES[zone_code],
        zone_class=zone_class,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=confidence,
        notes=notes,
        cited_subsection="§ 175-7.2(A)(3)",
        citations=citations,
    )


def residential(zone_code: str) -> Adjudication:
    return prohibited(
        zone_code,
        "residential",
        "Residential district; principal self-storage, mini-warehouse, light industrial, and garage-condo uses are not listed.",
        [DISTRICT_DESIGNATIONS, RESIDENTIAL_INSERT, GENERAL_USE_RESTRICTION],
        0.91,
    )


def business(zone_code: str) -> Adjudication:
    return prohibited(
        zone_code,
        "commercial",
        "Business/office district; principal storage, warehouse, light industrial, and garage-condo uses are not listed for this zone.",
        [DISTRICT_DESIGNATIONS, NONRESIDENTIAL_INSERT, GENERAL_USE_RESTRICTION],
        0.89,
    )


ADJUDICATIONS: dict[str, Adjudication] = {
    **{code: residential(code) for code in ["R100", "R60", "R50", "R2", "R2B", "R3", "R3A", "R3B"]},
    **{code: business(code) for code in ["B1", "B2", "B3", "B4", "HRO"]},
    "M1": Adjudication(
        zone_code="M1",
        zone_name=ZONE_NAMES["M1"],
        zone_class="industrial",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="permitted",
        luxury_garage_condo="prohibited",
        confidence=0.76,
        notes=(
            "M-1 permits warehouse and light manufacturing. Self-storage and mini-warehouse are left unclear because "
            "the matrix does not specifically identify consumer self-storage/mini-warehouse use. Garage-condo use is "
            "not listed as a principal or conditional use."
        ),
        cited_subsection="175 Attachment 2",
        citations=[DISTRICT_DESIGNATIONS, M1_WAREHOUSE, GENERAL_USE_RESTRICTION],
    ),
}


def normalized_code(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip().replace("-", "").upper() or None


def load_polygon_counts() -> dict[str, dict[str, object]]:
    fc = json.loads(POLYGONS.read_text())
    counts: dict[str, dict[str, object]] = {}
    for feature in fc["features"]:
        props = feature["properties"]
        code = normalized_code(props.get("zone_code"))
        if not code:
            continue
        entry = counts.setdefault(code, {"polygon_count": 0, "feature_indexes": []})
        entry["polygon_count"] = int(entry["polygon_count"]) + 1
        entry["feature_indexes"].append(props.get("feature_index"))
    return counts


def write_ordinance_sections() -> None:
    sections = [
        {
            "section_id": "175-5.1",
            "heading": "Districts designated",
            "text": DISTRICT_DESIGNATIONS.quote,
            "url": DISTRICTS_URL,
            "district_codes": sorted(ADJUDICATIONS),
        },
        {
            "section_id": "175-7.2",
            "heading": "Uses permitted in each zoning district",
            "text": GENERAL_USE_RESTRICTION.quote,
            "url": ARTICLE_VII_URL,
            "district_codes": sorted(ADJUDICATIONS),
        },
        {
            "section_id": "175 Attachment 1",
            "heading": "Residential Zone Districts - Insert 1",
            "text": RESIDENTIAL_INSERT.quote,
            "url": RESIDENTIAL_INSERT_URL,
            "district_codes": ["R100", "R60", "R50", "R2", "R2B", "R3", "R3A", "R3B"],
        },
        {
            "section_id": "175 Attachment 2",
            "heading": "Nonresidential Zone Districts - Insert 2",
            "text": NONRESIDENTIAL_INSERT.quote,
            "url": NONRESIDENTIAL_INSERT_URL,
            "district_codes": ["B1", "B2", "B3", "B4", "HRO", "M1"],
        },
    ]
    ORDINANCE_SECTIONS.write_text(json.dumps(sections, indent=2))


def row_for(code: str, polygon_info: dict[str, object]) -> dict[str, object]:
    item = ADJUDICATIONS[code]
    row = asdict(item)
    row["citations"] = [asdict(c) for c in item.citations]
    row["polygon_count"] = polygon_info["polygon_count"]
    row["polygon_feature_indexes"] = polygon_info["feature_indexes"]
    row["classification_source"] = "human"
    row["municipality"] = MUNICIPALITY
    row["requires_review"] = item.confidence < 0.85 or "unclear" in {
        item.self_storage,
        item.mini_warehouse,
        item.light_industrial,
        item.luxury_garage_condo,
    }
    return row


def write_cp2_artifacts() -> list[dict[str, object]]:
    ROOT.mkdir(parents=True, exist_ok=True)
    polygon_counts = load_polygon_counts()
    missing = sorted(set(polygon_counts) - set(ADJUDICATIONS))
    if missing:
        raise RuntimeError(f"Missing Hackensack adjudications for CP1 zone codes: {missing}")

    write_ordinance_sections()
    rows = [row_for(code, polygon_counts[code]) for code in sorted(polygon_counts)]
    low_confidence = [row for row in rows if row["requires_review"]]

    MATRIX_ROWS.write_text(json.dumps(rows, indent=2))
    LOW_CONFIDENCE_ROWS.write_text(json.dumps(low_confidence, indent=2))

    rng = random.Random(305)
    samples = rng.sample(rows, min(5, len(rows)))
    CP2_SAMPLES.write_text(json.dumps(samples, indent=2))
    return rows


def database_url() -> str:
    url = Settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    if EXPECTED_PREVIEW_REF not in url:
        raise RuntimeError(
            f"Refusing to run: DATABASE_URL does not contain preview ref {EXPECTED_PREVIEW_REF}"
        )
    return url


async def fetch_jurisdiction_id(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT id::text AS id FROM jurisdictions WHERE name = $1",
        JURISDICTION_NAME,
    )
    if not row:
        raise RuntimeError(f"Jurisdiction not found: {JURISDICTION_NAME}")
    return row["id"]


def load_polygon_features() -> list[dict[str, object]]:
    fc = json.loads(POLYGONS.read_text())
    features: list[dict[str, object]] = []
    for feature in fc["features"]:
        props = feature["properties"]
        code = normalized_code(props.get("zone_code"))
        if not code:
            continue
        item = ADJUDICATIONS[code]
        features.append(
            {
                "zone_code": code,
                "zone_name": item.zone_name,
                "zone_class": item.zone_class,
                "confidence": float(props.get("confidence") or item.confidence),
                "feature_index": props.get("feature_index"),
                "properties": props,
                "geometry": feature["geometry"],
            }
        )
    return features


async def ingest_polygons(conn: asyncpg.Connection, jurisdiction_id: str) -> int:
    await conn.execute(
        """
        DELETE FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
          AND raw_attributes->>'op5_source' = $2
          AND raw_attributes->>'municipality' = $3
        """,
        jurisdiction_id,
        SOURCE_TAG,
        MUNICIPALITY,
    )

    inserted = 0
    for feature in load_polygon_features():
        raw = {
            "op5_source": SOURCE_TAG,
            "municipality": MUNICIPALITY,
            "feature_index": feature["feature_index"],
            "cp1_properties": feature["properties"],
        }
        result = await conn.execute(
            """
            WITH g AS (
                SELECT ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($6), 4326))) AS geom
            )
            INSERT INTO zoning_districts (
                jurisdiction_id,
                zone_code,
                zone_name,
                zone_class,
                raw_attributes,
                geom,
                centroid,
                source,
                confidence,
                human_reviewed,
                geom_hash,
                updated_at
            )
            SELECT
                $1::uuid,
                $2,
                $3,
                $4::zone_class_enum,
                $5::jsonb,
                g.geom,
                ST_Centroid(g.geom),
                'manual'::zone_source_enum,
                $7::numeric,
                TRUE,
                md5(encode(ST_AsEWKB(g.geom), 'hex')),
                now()
            FROM g
            ON CONFLICT ON CONSTRAINT uq_zoning_districts_jur_code_hash DO NOTHING
            """,
            jurisdiction_id,
            feature["zone_code"],
            feature["zone_name"],
            feature["zone_class"],
            json.dumps(raw),
            json.dumps(feature["geometry"]),
            feature["confidence"],
        )
        inserted += int(result.split()[-1])
    return inserted


async def upsert_matrix_rows(
    conn: asyncpg.Connection,
    jurisdiction_id: str,
    rows: list[dict[str, object]],
) -> int:
    upserted = 0
    for row in rows:
        update_result = await conn.execute(
            """
            UPDATE zone_use_matrix
            SET
                zone_name = $3,
                self_storage = $5::use_permission_enum,
                mini_warehouse = $6::use_permission_enum,
                light_industrial = $7::use_permission_enum,
                luxury_garage_condo = $8::use_permission_enum,
                citations = $9::jsonb,
                confidence = $10::numeric,
                human_reviewed = TRUE,
                notes = $11,
                classification_source = 'human'::classification_source_enum,
                cited_subsection = $12,
                conditions_json = NULL,
                overlay_codes = NULL,
                deleted_at = NULL,
                updated_at = now()
            WHERE jurisdiction_id = $1::uuid
              AND zone_code = $2
              AND municipality = $4
            """,
            jurisdiction_id,
            row["zone_code"],
            row["zone_name"],
            MUNICIPALITY,
            row["self_storage"],
            row["mini_warehouse"],
            row["light_industrial"],
            row["luxury_garage_condo"],
            json.dumps(row["citations"]),
            row["confidence"],
            row["notes"],
            row["cited_subsection"],
        )
        count = int(update_result.split()[-1])
        if count == 0:
            insert_result = await conn.execute(
                """
                INSERT INTO zone_use_matrix (
                    jurisdiction_id,
                    zone_code,
                    zone_name,
                    municipality,
                    self_storage,
                    mini_warehouse,
                    light_industrial,
                    luxury_garage_condo,
                    citations,
                    confidence,
                    human_reviewed,
                    notes,
                    classification_source,
                    cited_subsection,
                    conditions_json,
                    overlay_codes,
                    deleted_at,
                    updated_at
                )
                VALUES (
                    $1::uuid,
                    $2,
                    $3,
                    $4,
                    $5::use_permission_enum,
                    $6::use_permission_enum,
                    $7::use_permission_enum,
                    $8::use_permission_enum,
                    $9::jsonb,
                    $10::numeric,
                    TRUE,
                    $11,
                    'human'::classification_source_enum,
                    $12,
                    NULL,
                    NULL,
                    NULL,
                    now()
                )
                """,
                jurisdiction_id,
                row["zone_code"],
                row["zone_name"],
                MUNICIPALITY,
                row["self_storage"],
                row["mini_warehouse"],
                row["light_industrial"],
                row["luxury_garage_condo"],
                json.dumps(row["citations"]),
                row["confidence"],
                row["notes"],
                row["cited_subsection"],
            )
            count = int(insert_result.split()[-1])
        upserted += count
    return upserted


async def spatial_join_hackensack(conn: asyncpg.Connection, jurisdiction_id: str) -> int:
    result = await conn.execute(
        """
        UPDATE parcels target
        SET
            zoning_code = sub.zone_code,
            zone_class = sub.zone_class::zone_class_enum,
            updated_at = now()
        FROM (
            SELECT p.id AS parcel_id, zd.zone_code, zd.zone_class::text AS zone_class
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_code, zd.zone_class
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = $1::uuid
                  AND zd.raw_attributes->>'op5_source' = $2
                  AND zd.raw_attributes->>'municipality' = $3
                  AND zd.geom IS NOT NULL
                  AND ST_Within(COALESCE(p.centroid, ST_Centroid(p.geom)), zd.geom)
                ORDER BY zd.id
                LIMIT 1
            ) zd
            WHERE p.jurisdiction_id = $1::uuid
              AND p.city = $3
              AND p.geom IS NOT NULL
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        jurisdiction_id,
        SOURCE_TAG,
        MUNICIPALITY,
    )
    return int(result.split()[-1])


async def audit(conn: asyncpg.Connection, jurisdiction_id: str, rows: list[dict[str, object]]) -> dict[str, object]:
    zone_codes = [str(row["zone_code"]) for row in rows]
    summary = await conn.fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_parcels,
            COUNT(*) FILTER (WHERE p.geom IS NOT NULL)::int AS parcels_with_geom,
            COUNT(*) FILTER (WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> '')::int AS parcels_with_zoning_code,
            COUNT(*) FILTER (WHERE z.zone_code IS NOT NULL)::int AS parcels_with_matrix_match,
            COUNT(DISTINCT p.zoning_code) FILTER (WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> '')::int AS distinct_parcel_zones,
            COUNT(DISTINCT z.zone_code) FILTER (WHERE z.zone_code IS NOT NULL)::int AS distinct_matrix_matched_zones
        FROM parcels p
        LEFT JOIN zone_use_matrix z
          ON z.jurisdiction_id = p.jurisdiction_id
         AND z.zone_code = p.zoning_code
         AND z.municipality = p.city
         AND z.deleted_at IS NULL
        WHERE p.jurisdiction_id = $1::uuid
          AND p.city = $2
        """,
        jurisdiction_id,
        MUNICIPALITY,
    )
    district_rows = await conn.fetchval(
        """
        SELECT COUNT(*)::int
        FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
          AND raw_attributes->>'op5_source' = $2
          AND raw_attributes->>'municipality' = $3
        """,
        jurisdiction_id,
        SOURCE_TAG,
        MUNICIPALITY,
    )
    matrix_rows = await conn.fetchval(
        """
        SELECT COUNT(*)::int
        FROM zone_use_matrix
        WHERE jurisdiction_id = $1::uuid
          AND municipality = $2
          AND zone_code = ANY($3::text[])
          AND deleted_at IS NULL
        """,
        jurisdiction_id,
        MUNICIPALITY,
        zone_codes,
    )
    unmatched = await conn.fetch(
        """
        SELECT p.zoning_code, COUNT(*)::int AS parcel_count
        FROM parcels p
        LEFT JOIN zone_use_matrix z
          ON z.jurisdiction_id = p.jurisdiction_id
         AND z.zone_code = p.zoning_code
         AND z.municipality = p.city
         AND z.deleted_at IS NULL
        WHERE p.jurisdiction_id = $1::uuid
          AND p.city = $2
          AND p.zoning_code IS NOT NULL
          AND btrim(p.zoning_code) <> ''
          AND z.zone_code IS NULL
        GROUP BY p.zoning_code
        ORDER BY parcel_count DESC, p.zoning_code
        LIMIT 20
        """,
        jurisdiction_id,
        MUNICIPALITY,
    )
    s = dict(summary)
    total = s["total_parcels"] or 0
    with_geom = s["parcels_with_geom"] or 0
    with_code = s["parcels_with_zoning_code"] or 0
    matched = s["parcels_with_matrix_match"] or 0
    payload = {
        "database_ref": EXPECTED_PREVIEW_REF,
        "jurisdiction_id": jurisdiction_id,
        "jurisdiction_name": JURISDICTION_NAME,
        "municipality": MUNICIPALITY,
        "cp1_polygon_count": sum(int(row["polygon_count"]) for row in rows),
        "cp2_matrix_rows": len(rows),
        "cp2_low_confidence_rows": sum(1 for row in rows if row["requires_review"]),
        "zoning_district_rows_tagged": district_rows,
        "matrix_rows_scoped_to_hackensack": matrix_rows,
        **s,
        "zoning_code_coverage_pct_of_total": round(100.0 * with_code / total, 2) if total else 0.0,
        "zoning_code_coverage_pct_of_geom": round(100.0 * with_code / with_geom, 2) if with_geom else 0.0,
        "matrix_match_pct_of_total": round(100.0 * matched / total, 2) if total else 0.0,
        "matrix_match_pct_of_zoned": round(100.0 * matched / with_code, 2) if with_code else 0.0,
        "unmatched_zoning_codes": [dict(row) for row in unmatched],
    }
    AUDIT_POST_OP5.write_text(json.dumps(payload, indent=2, default=str))
    return payload


async def spot_check(conn: asyncpg.Connection, jurisdiction_id: str) -> dict[str, object]:
    samples = await conn.fetch(
        """
        WITH sample AS (
            SELECT p.id
            FROM parcels p
            WHERE p.jurisdiction_id = $1::uuid
              AND p.city = $2
              AND p.geom IS NOT NULL
            ORDER BY random()
            LIMIT 10
        )
        SELECT
            p.id,
            p.apn,
            p.address,
            p.city,
            p.zoning_code,
            p.zone_class::text AS zone_class,
            z.self_storage::text AS self_storage,
            z.mini_warehouse::text AS mini_warehouse,
            z.light_industrial::text AS light_industrial,
            z.luxury_garage_condo::text AS luxury_garage_condo,
            z.municipality AS matrix_municipality,
            (z.zone_code IS NOT NULL) AS matrix_matched,
            ST_AsGeoJSON(COALESCE(p.centroid, ST_Centroid(p.geom))) AS centroid_geojson
        FROM sample s
        JOIN parcels p ON p.id = s.id
        LEFT JOIN zone_use_matrix z
          ON z.jurisdiction_id = p.jurisdiction_id
         AND z.zone_code = p.zoning_code
         AND z.municipality = p.city
         AND z.deleted_at IS NULL
        ORDER BY p.id
        """,
        jurisdiction_id,
        MUNICIPALITY,
    )
    rows = [dict(row) for row in samples]
    checked = len(rows)
    matched = sum(1 for row in rows if row["matrix_matched"])
    payload = {
        "database_ref": EXPECTED_PREVIEW_REF,
        "jurisdiction_id": jurisdiction_id,
        "municipality": MUNICIPALITY,
        "sample_size": checked,
        "matched_count": matched,
        "spot_check_match_rate_pct": round(100.0 * matched / checked, 2) if checked else 0.0,
        "samples": rows,
    }
    SPOT_CHECK.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def write_summary(audit_payload: dict[str, object], spot_payload: dict[str, object], inserted: int, updated: int, upserted: int) -> None:
    text = f"""# Hackensack CP3 Summary

- Database ref: `{EXPECTED_PREVIEW_REF}`
- Jurisdiction: `{JURISDICTION_NAME}`
- Municipality scope: `{MUNICIPALITY}`
- CP1 polygons ingested/tagged: {audit_payload['zoning_district_rows_tagged']} rows ({inserted} inserted this run)
- CP2 matrix rows: {audit_payload['cp2_matrix_rows']} total; {audit_payload['cp2_low_confidence_rows']} low-confidence/review rows
- Matrix rows applied/upserted: {upserted}
- Hackensack parcel zoning updates from spatial join: {updated}
- Parcel zoning-code coverage: {audit_payload['zoning_code_coverage_pct_of_total']}% of total; {audit_payload['zoning_code_coverage_pct_of_geom']}% of parcels with geometry
- Matrix match coverage: {audit_payload['matrix_match_pct_of_total']}% of total; {audit_payload['matrix_match_pct_of_zoned']}% of zoned parcels
- Spot-check match rate: {spot_payload['spot_check_match_rate_pct']}% ({spot_payload['matched_count']}/{spot_payload['sample_size']})

Artifacts:
- `{MATRIX_ROWS}`
- `{LOW_CONFIDENCE_ROWS}`
- `{CP2_SAMPLES}`
- `{AUDIT_POST_OP5}`
- `{SPOT_CHECK}`

Stopped at CP3 for review. No production promotion or non-Hackensack audit was run.
"""
    CP3_SUMMARY.write_text(text)


async def apply_cp3(rows: list[dict[str, object]]) -> dict[str, object]:
    conn = await asyncpg.connect(
        database_url(),
        statement_cache_size=0,
        command_timeout=120,
    )
    try:
        await conn.execute("SET statement_timeout = 120000")
        async with conn.transaction():
            jurisdiction_id = await fetch_jurisdiction_id(conn)
            inserted = await ingest_polygons(conn, jurisdiction_id)
            upserted = await upsert_matrix_rows(conn, jurisdiction_id, rows)
            updated = await spatial_join_hackensack(conn, jurisdiction_id)
        audit_payload = await audit(conn, jurisdiction_id, rows)
        spot_payload = await spot_check(conn, jurisdiction_id)
        write_summary(audit_payload, spot_payload, inserted, updated, upserted)
        return {
            "jurisdiction_id": jurisdiction_id,
            "inserted_zoning_districts": inserted,
            "upserted_matrix_rows": upserted,
            "updated_parcels": updated,
            "audit": audit_payload,
            "spot_check": {
                "sample_size": spot_payload["sample_size"],
                "matched_count": spot_payload["matched_count"],
                "spot_check_match_rate_pct": spot_payload["spot_check_match_rate_pct"],
            },
        }
    finally:
        await conn.close()


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Hackensack Op-5 CP2/CP3 proof")
    parser.add_argument("--apply-cp3", action="store_true", help="ingest/apply on the configured preview branch")
    args = parser.parse_args()

    rows = write_cp2_artifacts()
    output: dict[str, object] = {
        "cp2": {
            "matrix_rows": len(rows),
            "low_confidence_rows": sum(1 for row in rows if row["requires_review"]),
            "samples": min(5, len(rows)),
            "outputs": {
                "ordinance_sections": str(ORDINANCE_SECTIONS),
                "matrix_rows": str(MATRIX_ROWS),
                "low_confidence_rows": str(LOW_CONFIDENCE_ROWS),
                "cp2_samples": str(CP2_SAMPLES),
            },
        }
    }
    if args.apply_cp3:
        output["cp3"] = await apply_cp3(rows)
        output["cp3_outputs"] = {
            "audit_post_op5": str(AUDIT_POST_OP5),
            "spot_check": str(SPOT_CHECK),
            "cp3_summary": str(CP3_SUMMARY),
        }

    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
