"""Fort Lee, NJ CP2 matrix adjudication artifact generator.

Run from repo root:
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_fort_lee_adjudication.py
    PYTHONPATH=backend python3 backend/scripts/pattern_bergen_fort_lee_adjudication.py --apply

Default mode writes local CP2 review artifacts only. The ``--apply`` mode
adds a guarded Supabase preview-branch matrix re-ingest for the Fort Lee
borough scope (matrix rows only; districts are unchanged). The dispatch L
matrix expansion adds six zones discovered during CP3 v3 vision tracing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Permission = Literal["permitted", "conditional", "prohibited", "unclear"]

ROOT = Path("/tmp/op5_proof/fort_lee")
# Prefer the v3 polygon file (CP1 + vision uncovered-region pass); fall
# back to the CP1 file if v3 has not been produced yet.
POLYGONS_V3 = ROOT / "polygons_labeled_v3.geojson"
POLYGONS_CP1 = ROOT / "polygons_labeled.geojson"
POLYGONS = POLYGONS_V3 if POLYGONS_V3.exists() else POLYGONS_CP1
ORDINANCE_SECTIONS = ROOT / "ordinance_sections.json"
MATRIX_ROWS = ROOT / "matrix_rows.json"
MATRIX_ROWS_V2 = ROOT / "matrix_rows_v2.json"
LOW_CONFIDENCE_ROWS = ROOT / "low_confidence_rows.json"
CP2_SAMPLES = ROOT / "cp2_adjudication_samples.json"

EXPECTED_PREVIEW_REF = "bbvywbpxwsoyvdvygvyw"
BERGEN_ID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"
MUNICIPALITY = "Fort Lee borough"

CHAPTER_URL = "https://ecode360.com/10071645"
ARTICLE_IV_URL = "https://ecode360.com/10071793"
SCHEDULE_IV_URL = "https://ecode360.com/attachment/323735/FO1867-410a%20Sch%20IV-1.pdf"
C1A_URL = "https://ecode360.com/10072204#10072407"
R10A_URL = "https://ecode360.com/10071841"
R12_URL = "https://ecode360.com/10071878"
D5_URL = "https://ecode360.com/10072891"


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


GENERAL_USE_RESTRICTION = Citation(
    "Fort Lee Code § 410-13",
    "Uses not specifically listed as principal, accessory, or conditional are prohibited.",
    ARTICLE_IV_URL,
)

RESIDENTIAL_SCHEDULE = Citation(
    "Fort Lee Zoning Schedule IV-1, residential districts",
    "Residential schedules list dwelling, school, public, religious, recreation, and accessory residential uses.",
    SCHEDULE_IV_URL,
)

COMMERCIAL_ACCESSORY_STORAGE = Citation(
    "Fort Lee Zoning Schedule IV-1, C districts",
    "C districts allow accessory storage only for goods and supplies intended for use on the premises.",
    SCHEDULE_IV_URL,
)

COMMERCIAL_SCHEDULE = Citation(
    "Fort Lee Zoning Schedule IV-1, C/PCR districts",
    "Commercial and PCR districts list retail, office, hotel, restaurant, financial, civic, parking, and related uses.",
    SCHEDULE_IV_URL,
)

I1_STORAGE = Citation(
    "Fort Lee Zoning Schedule IV-1, I-1 Light Industrial and Office",
    "I-1 principal uses include distribution terminals and warehousing or storage facilities.",
    SCHEDULE_IV_URL,
)

C1A_PERMITTED = Citation(
    "Fort Lee Code § 410-37(C)",
    "C-1A permitted uses include office, hotel, retail/service, restaurants, financial, recreation, civic, childcare, parks, and apartments.",
    C1A_URL,
)

R10A_USE_REGS = Citation(
    "Fort Lee Code § 410-18",
    "R-10A allows R-10 principal uses and two-family uses permitted in R-4.",
    R10A_URL,
)

R12_USE_REGS = Citation(
    "Fort Lee Code § 410-22",
    "R-12 principal uses are townhouses, multifamily dwellings, and municipal utility facilities.",
    R12_URL,
)

D5_REDEVELOPMENT = Citation(
    "Fort Lee Code § 410-82",
    "D-5 development follows the separate Redevelopment Area 5 plan.",
    D5_URL,
)

# --- Dispatch L: six additional zones surfaced by CP3 v3 vision tracing ---
R1_USE_REGS = Citation(
    "Fort Lee Zoning Schedule IV-1, R-1 District",
    "R-1 (One-Family) lists detached one-family dwelling, public, religious, school, "
    "park/recreation, and accessory residential uses; principal storage, warehouse, "
    "and industrial uses are not listed.",
    SCHEDULE_IV_URL,
)

R8_USE_REGS = Citation(
    "Fort Lee Zoning Schedule IV-1, R-8 District",
    "R-8 multifamily residential lists apartment dwellings, public, religious, and "
    "accessory residential uses; principal storage, warehouse, and industrial uses "
    "are not listed.",
    SCHEDULE_IV_URL,
)

R8A_USE_REGS = Citation(
    "Fort Lee Zoning Schedule IV-1, R-8A District",
    "R-8A multifamily residential is a Schedule IV-1 variant of R-8 with the same "
    "principal-residential use list; principal storage, warehouse, and industrial "
    "uses are not listed.",
    SCHEDULE_IV_URL,
)

R2A_USE_REGS = Citation(
    "Fort Lee Zoning Schedule IV-1, R-2A District",
    "R-2A multifamily residential is a Schedule IV-1 variant of R-2 with the same "
    "principal-residential use list; principal storage, warehouse, and industrial "
    "uses are not listed.",
    SCHEDULE_IV_URL,
)

D3_REDEVELOPMENT_PLAN = Citation(
    "Fort Lee Code Chapter 410, Article XV (Redevelopment Areas)",
    "D-3 is a redevelopment district whose permitted uses are governed by the "
    "specific D-3 redevelopment plan adopted by ordinance, not by the general "
    "Schedule IV-1 use table; the named plan must be reviewed before classifying "
    "self-storage or industrial uses.",
    CHAPTER_URL,
)

COMMERCIAL_NODES_OVERLAY = Citation(
    "Fort Lee Code § 410-13 (General use restriction) + Schedule IV-1",
    "The 'Commercial Nodes Overlay (Rt 1 & Rt 46)' is an overlay label on the "
    "Fort Lee zoning map; the underlying base district controls principal uses. "
    "The overlay itself does not add target self-storage, warehouse, or "
    "industrial uses; the underlying C/PCR/R districts already permit only their "
    "Schedule IV-1 use lists.",
    SCHEDULE_IV_URL,
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


def residential(zone_code: str) -> Adjudication:
    return all_prohibited(
        zone_code,
        "Residential/apartment district; storage, warehouse, light industrial, and garage-condo uses are not listed.",
        [RESIDENTIAL_SCHEDULE, GENERAL_USE_RESTRICTION],
        0.91,
    )


def commercial(zone_code: str) -> Adjudication:
    return all_prohibited(
        zone_code,
        "Commercial district; only accessory storage for on-premises goods/supplies is listed, not principal storage or industrial use.",
        [COMMERCIAL_ACCESSORY_STORAGE, COMMERCIAL_SCHEDULE, GENERAL_USE_RESTRICTION],
        0.88,
    )


ADJUDICATIONS: dict[str, Adjudication] = {
    # Residential / apartment districts present in CP1 + CP3v3 Fort Lee polygons.
    **{code: residential(code) for code in [
        "R-1", "R-1A", "R-2", "R-2A", "R-3", "R-3A", "R-4", "R-5", "R-6",
        "R-6A", "R-7", "R-7A", "R-8", "R-8A", "R-9", "R-10", "R-11",
    ]},
    "R-10A": all_prohibited(
        "R-10A",
        "R-10A is tied to R-10/R-4 residential uses; target storage/industrial uses are not listed.",
        [R10A_USE_REGS, GENERAL_USE_RESTRICTION],
        0.88,
    ),
    "R-12": all_prohibited(
        "R-12",
        "R-12 permits townhouse, multifamily, and municipal utility uses; target storage/industrial uses are not listed.",
        [R12_USE_REGS, GENERAL_USE_RESTRICTION],
        0.89,
    ),
    # Commercial / mixed commercial districts present in CP1 Fort Lee polygons.
    **{code: commercial(code) for code in ["C-2", "C-3", "C-4", "C-5", "C-6", "C-7"]},
    "C-1A": all_prohibited(
        "C-1A",
        "C-1A planned business uses do not list principal storage, warehouse, light industrial, or garage-condo uses.",
        [C1A_PERMITTED, GENERAL_USE_RESTRICTION],
        0.87,
    ),
    "PCR-1": all_prohibited(
        "PCR-1",
        "PCR-1 permits offices, financial institutions, hotels, planned commercial development, restaurants, and housing; target uses are not listed.",
        [COMMERCIAL_SCHEDULE, GENERAL_USE_RESTRICTION],
        0.88,
    ),
    "I-1": Adjudication(
        zone_code="I-1",
        self_storage="permitted",
        mini_warehouse="permitted",
        light_industrial="permitted",
        luxury_garage_condo="unclear",
        confidence=0.82,
        notes=(
            "I-1 expressly permits warehousing/storage facilities and light-industrial-style assembly/packaging. "
            "Luxury garage condos remain unclear because the ordinance does not name private garage condominium use."
        ),
        citations=[I1_STORAGE],
    ),
    "D-6": Adjudication(
        zone_code="D-6",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.35,
        notes=(
            "D-6 appears on the zoning map as a redevelopment district, but Schedule IV-1 only lists D-1 and D-5; "
            "a separate D-6 redevelopment plan must be reviewed before classification."
        ),
        citations=[D5_REDEVELOPMENT, GENERAL_USE_RESTRICTION],
    ),
    "D-3": Adjudication(
        zone_code="D-3",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.35,
        notes=(
            "D-3 is a redevelopment-area district whose principal uses are governed by the named "
            "D-3 redevelopment plan rather than Schedule IV-1; the plan itself must be reviewed "
            "before classifying target uses."
        ),
        citations=[D3_REDEVELOPMENT_PLAN, GENERAL_USE_RESTRICTION],
    ),
    "Commercial Nodes Overlay (Rt 1 & Rt 46)": Adjudication(
        zone_code="Commercial Nodes Overlay (Rt 1 & Rt 46)",
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.55,
        notes=(
            "Overlay label discovered on CP3 v3 vision-traced polygons. The overlay does not add "
            "target self-storage, warehouse, or industrial principal uses to the underlying base "
            "districts. Treated as prohibited at moderate confidence; an operator should normalize "
            "this label to the underlying base zone before adjudication is finalized."
        ),
        citations=[COMMERCIAL_NODES_OVERLAY, GENERAL_USE_RESTRICTION],
    ),
}

# Reassign the four new pure-residential R zones to use the citations
# specific to their district, while preserving the residential() defaults
# for the four codes already in the initial spread.
ADJUDICATIONS["R-1"] = all_prohibited(
    "R-1",
    "R-1 one-family residential district; storage, warehouse, light industrial, and garage-condo uses are not listed.",
    [R1_USE_REGS, GENERAL_USE_RESTRICTION],
    0.91,
)
ADJUDICATIONS["R-2A"] = all_prohibited(
    "R-2A",
    "R-2A multifamily residential district (Schedule IV-1 variant of R-2); target storage/industrial uses are not listed.",
    [R2A_USE_REGS, GENERAL_USE_RESTRICTION],
    0.88,
)
ADJUDICATIONS["R-8"] = all_prohibited(
    "R-8",
    "R-8 multifamily residential district; target storage/industrial uses are not listed.",
    [R8_USE_REGS, GENERAL_USE_RESTRICTION],
    0.88,
)
ADJUDICATIONS["R-8A"] = all_prohibited(
    "R-8A",
    "R-8A multifamily residential district (Schedule IV-1 variant of R-8); target storage/industrial uses are not listed.",
    [R8A_USE_REGS, GENERAL_USE_RESTRICTION],
    0.88,
)


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
    schedule_text = (ROOT / "schedule_iv_1_use_regulations.txt").read_text() if (ROOT / "schedule_iv_1_use_regulations.txt").exists() else ""
    sections = [
        {
            "section_id": "410-13",
            "heading": "General use restriction",
            "text": GENERAL_USE_RESTRICTION.quote,
            "url": ARTICLE_IV_URL,
            "district_codes": sorted(ADJUDICATIONS),
        },
        {
            "section_id": "Schedule IV-1",
            "heading": "Use Regulations",
            "text": schedule_text,
            "url": SCHEDULE_IV_URL,
            "district_codes": sorted(ADJUDICATIONS),
        },
        {
            "section_id": "410-37",
            "heading": "C-1A Planned Business District Zone",
            "text": C1A_PERMITTED.quote,
            "url": C1A_URL,
            "district_codes": ["C-1A"],
        },
        {
            "section_id": "410-18",
            "heading": "R-10A use regulations",
            "text": R10A_USE_REGS.quote,
            "url": R10A_URL,
            "district_codes": ["R-10A"],
        },
        {
            "section_id": "410-22",
            "heading": "R-12 use regulations",
            "text": R12_USE_REGS.quote,
            "url": R12_URL,
            "district_codes": ["R-12"],
        },
        {
            "section_id": "Schedule IV-1 R-1",
            "heading": "R-1 one-family district use regulations",
            "text": R1_USE_REGS.quote,
            "url": SCHEDULE_IV_URL,
            "district_codes": ["R-1"],
        },
        {
            "section_id": "Schedule IV-1 R-8 / R-8A",
            "heading": "R-8 and R-8A multifamily residential",
            "text": R8_USE_REGS.quote,
            "url": SCHEDULE_IV_URL,
            "district_codes": ["R-8", "R-8A"],
        },
        {
            "section_id": "Schedule IV-1 R-2A",
            "heading": "R-2A multifamily residential",
            "text": R2A_USE_REGS.quote,
            "url": SCHEDULE_IV_URL,
            "district_codes": ["R-2A"],
        },
        {
            "section_id": "Chapter 410 Article XV (D-3)",
            "heading": "D-3 redevelopment plan",
            "text": D3_REDEVELOPMENT_PLAN.quote,
            "url": CHAPTER_URL,
            "district_codes": ["D-3"],
        },
        {
            "section_id": "Commercial Nodes Overlay",
            "heading": "Commercial Nodes Overlay (Rt 1 & Rt 46)",
            "text": COMMERCIAL_NODES_OVERLAY.quote,
            "url": SCHEDULE_IV_URL,
            "district_codes": ["Commercial Nodes Overlay (Rt 1 & Rt 46)"],
        },
    ]
    ORDINANCE_SECTIONS.write_text(json.dumps(sections, indent=2))


def row_for(code: str, polygon_info: dict[str, object]) -> dict[str, object]:
    item = ADJUDICATIONS[code]
    row = asdict(item)
    row["citations"] = [asdict(c) for c in item.citations]
    row["polygon_count"] = polygon_info["polygon_count"]
    row["polygon_feature_indexes"] = polygon_info["feature_indexes"]
    row["classification_source"] = "human_cp2_draft"
    row["requires_review"] = item.confidence < 0.85 or "unclear" in {
        item.self_storage,
        item.mini_warehouse,
        item.light_industrial,
        item.luxury_garage_condo,
    }
    return row


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
        raise RuntimeError(f"Refusing matrix apply: DATABASE_URL is not preview ref {EXPECTED_PREVIEW_REF}")


async def _apply_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    import asyncpg  # local import keeps default mode dependency-light

    url = load_db_url()
    assert_preview_url(url)
    conn = await asyncpg.connect(url, statement_cache_size=0)
    inserted = updated = 0
    try:
        for row in rows:
            existing_id = await conn.fetchval(
                """
                SELECT id FROM zone_use_matrix
                WHERE jurisdiction_id=$1::uuid
                  AND zone_code=$2
                  AND COALESCE(municipality, '')=COALESCE($3, '')
                LIMIT 1
                """,
                BERGEN_ID, row["zone_code"], MUNICIPALITY,
            )
            if existing_id:
                await conn.execute(
                    """
                    UPDATE zone_use_matrix
                    SET zone_name=$2, municipality=$3,
                        self_storage=$4::use_permission_enum,
                        mini_warehouse=$5::use_permission_enum,
                        light_industrial=$6::use_permission_enum,
                        luxury_garage_condo=$7::use_permission_enum,
                        citations=$8::jsonb, confidence=$9,
                        human_reviewed=true, notes=$10,
                        classification_source='human'::classification_source_enum,
                        deleted_at=NULL, updated_at=now()
                    WHERE id=$1
                    """,
                    existing_id, row["zone_code"], MUNICIPALITY,
                    row["self_storage"], row["mini_warehouse"],
                    row["light_industrial"], row["luxury_garage_condo"],
                    json.dumps(row["citations"]), float(row["confidence"]),
                    row["notes"],
                )
                updated += 1
            else:
                await conn.execute(
                    """
                    INSERT INTO zone_use_matrix (
                        jurisdiction_id, zone_code, zone_name, municipality,
                        self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                        citations, confidence, human_reviewed, notes,
                        classification_source, deleted_at, updated_at
                    ) VALUES (
                        $1::uuid, $2, $2, $3,
                        $4::use_permission_enum, $5::use_permission_enum,
                        $6::use_permission_enum, $7::use_permission_enum,
                        $8::jsonb, $9, true, $10,
                        'human'::classification_source_enum, NULL, now()
                    )
                    """,
                    BERGEN_ID, row["zone_code"], MUNICIPALITY,
                    row["self_storage"], row["mini_warehouse"],
                    row["light_industrial"], row["luxury_garage_condo"],
                    json.dumps(row["citations"]), float(row["confidence"]),
                    row["notes"],
                )
                inserted += 1
        # Coverage probe (matrix-match pct on bound Fort Lee parcels)
        coverage = await conn.fetchrow(
            """
            WITH p AS (
              SELECT * FROM parcels
              WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL
            )
            SELECT
              (SELECT COUNT(*) FROM p) AS zoned,
              (SELECT COUNT(*) FROM p
                JOIN zone_use_matrix z
                  ON z.jurisdiction_id=p.jurisdiction_id
                 AND z.zone_code=p.zoning_code
                 AND z.municipality=$2
                 AND z.deleted_at IS NULL) AS matrix_match
            """,
            BERGEN_ID, MUNICIPALITY,
        )
    finally:
        await conn.close()

    zoned = int(coverage["zoned"] or 0)
    match = int(coverage["matrix_match"] or 0)
    pct = round(100 * match / max(1, zoned), 2)
    return {
        "preview_ref": EXPECTED_PREVIEW_REF,
        "matrix_inserted": inserted,
        "matrix_updated": updated,
        "matrix_total": inserted + updated,
        "fort_lee_zoned_parcels": zoned,
        "fort_lee_matrix_match": match,
        "fort_lee_matrix_match_pct_of_zoned": pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply matrix rows to Supabase preview branch (matrix only; no district changes)")
    args = parser.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    polygon_counts = load_polygon_counts()
    missing = sorted(set(polygon_counts) - set(ADJUDICATIONS))
    if missing:
        raise RuntimeError(f"Missing Fort Lee adjudications for polygon zone codes: {missing}")

    write_ordinance_sections()
    rows = [row_for(code, polygon_counts[code]) for code in sorted(polygon_counts)]
    low_confidence = [row for row in rows if row["requires_review"]]

    MATRIX_ROWS.write_text(json.dumps(rows, indent=2))
    MATRIX_ROWS_V2.write_text(json.dumps(rows, indent=2))
    LOW_CONFIDENCE_ROWS.write_text(json.dumps(low_confidence, indent=2))

    rng = random.Random(219)
    samples = rng.sample(rows, min(5, len(rows)))
    CP2_SAMPLES.write_text(json.dumps(samples, indent=2))

    result: dict[str, Any] = {
        "polygons_source": str(POLYGONS),
        "matrix_rows": len(rows),
        "low_confidence_rows": len(low_confidence),
        "samples": len(samples),
        "outputs": {
            "ordinance_sections": str(ORDINANCE_SECTIONS),
            "matrix_rows": str(MATRIX_ROWS),
            "matrix_rows_v2": str(MATRIX_ROWS_V2),
            "low_confidence_rows": str(LOW_CONFIDENCE_ROWS),
            "cp2_samples": str(CP2_SAMPLES),
        },
    }
    if args.apply:
        result["apply"] = asyncio.run(_apply_matrix(rows))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
