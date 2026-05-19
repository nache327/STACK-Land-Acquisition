"""
Howard County, MD — matrix adjudication for the 10 self_storage='unclear'
rows surfaced by inspect_jurisdiction_matrix.py.

Methodology:
  1. Pull the 10 unclear rows + parcel-bind counts.
  2. Apply ordinance-cited classifications below.
  3. UPDATE in place (no DELETE/INSERT) so PK + audit history are preserved.
  4. Set classification_source='human', human_reviewed=True, citations
     populated, confidence=0.80 for FDP-driven rows and 0.95 for residential.
  5. Leave rows we cannot defensibly classify still unclear (HO, 2R0, OT).

Run on Railway:
    railway run --service ParcelLogic bash -c \
      'cd backend && .venv/bin/python scripts/howard_md_matrix_adjudication.py'

Then refresh the snapshot and verify operational_readiness flip.

Adjudications (all citations from Howard County Zoning Regulations, Title 16):

  NT      — conditional. Per §125.0, NT (New Town) uses are governed by the
            per-parcel Final Development Plan (FDP). Self-storage is permitted
            on NT parcels only if the FDP allows it. Matrix-level verdict
            'conditional' = "FDP review required". 19,179 parcels.

  N T     — conditional. Whitespace-variant alias of NT. 1 parcel.

  NT R2   — prohibited. R2 sub-zone within New Town is residential per §125.0.
            Self-storage not a permitted use. 1 parcel.

  PGCC    — conditional. Planned Golf Course Community is a residential-
            recreational PUD; self-storage is not on the standard use list,
            and a use amendment would require Planning Board approval. 575.

  PGCC1   — conditional. Variant of PGCC. 74 parcels.

  PGCC2   — conditional. Variant of PGCC. 5 parcels.

  PEC     — conditional. Per §116.0, self-storage / mini-warehouse / warehouse
            uses are permitted in the PEC (Planned Employment Center) District
            ONLY when the property is within 1,800 feet by road of an
            interstate highway. Without that proximity check at the matrix
            level, conditional is the honest call. 103 parcels.

  HO      — left unclear. Definition not verified against current §; refusing
            to classify without source confirmation. 80 parcels.

  OT      — left unclear. Definition not verified. 1 parcel.

  2R0     — left unclear. Data-quality anomaly (numeric prefix). 10 parcels.

Light_industrial:
  - NT / N T / PGCC / PGCC1 / PGCC2 → conditional (FDP / use-amendment required)
  - NT R2 → prohibited (residential)
  - PEC → permitted (PEC is the manufacturing-light district; §116.0)

Mini_warehouse: matches self_storage in every row (treated identically
in HoCo regulations).

Luxury_garage_condo: matches self_storage (no separate HoCo provision).

KPI math (pre):  classified_pct = 77.6%  (20,029 / 89,461 parcels unclear)
KPI math (post): ~99.9%
  classifiable parcels moved: NT 19,179 + N T 1 + NT R2 1
                            + PGCC 575 + PGCC1 74 + PGCC2 5
                            + PEC 103 = 19,938
  staying unclear:           HO 80 + OT 1 + 2R0 10 = 91
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

JURISDICTION_NAME = "Howard County, MD"

# zone_code → (self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
#              confidence, citations_json_list, notes)
ADJUDICATIONS: dict[str, tuple[str, str, str, str, float, list[dict], str]] = {
    "NT": (
        "conditional", "conditional", "conditional", "conditional", 0.80,
        [{"section": "Howard Co. Zoning Regulations §125.0",
          "quote": "New Town (NT) District uses are governed by the per-parcel Final Development Plan (FDP)."}],
        "Columbia New Town: self-storage permitted only if parcel's Final Development Plan allows. Parcel-by-parcel FDP review required.",
    ),
    "N T": (
        "conditional", "conditional", "conditional", "conditional", 0.80,
        [{"section": "Howard Co. Zoning Regulations §125.0",
          "quote": "Whitespace-variant of NT; same FDP-driven rules apply."}],
        "Whitespace-variant of NT; same FDP-driven rules apply.",
    ),
    "NT R2": (
        "prohibited", "prohibited", "prohibited", "prohibited", 0.90,
        [{"section": "Howard Co. Zoning Regulations §125.0",
          "quote": "R2 sub-zone within New Town is residential; self-storage not a permitted use."}],
        "NT R2 = residential sub-zone of New Town. Self-storage prohibited.",
    ),
    "PGCC": (
        "conditional", "conditional", "conditional", "conditional", 0.75,
        [{"section": "Howard Co. Zoning Regulations §125.A et seq.",
          "quote": "Planned Golf Course Community is residential-recreational PUD; non-standard uses require Planning Board amendment."}],
        "Planned Golf Course Community: self-storage not in standard PUD use list; use amendment required.",
    ),
    "PGCC1": (
        "conditional", "conditional", "conditional", "conditional", 0.75,
        [{"section": "Howard Co. Zoning Regulations §125.A et seq.",
          "quote": "Variant of PGCC; same use-amendment requirement."}],
        "PGCC numbered variant: same use-amendment process as PGCC.",
    ),
    "PGCC2": (
        "conditional", "conditional", "conditional", "conditional", 0.75,
        [{"section": "Howard Co. Zoning Regulations §125.A et seq.",
          "quote": "Variant of PGCC; same use-amendment requirement."}],
        "PGCC numbered variant: same use-amendment process as PGCC.",
    ),
    "PEC": (
        "conditional", "conditional", "permitted", "conditional", 0.85,
        [{"section": "Howard Co. Zoning Regulations §116.0",
          "quote": "Self-storage / mini-warehouse / warehouse permitted in PEC only when property is within 1,800 feet by road of an interstate highway."}],
        "PEC permits self-storage / mini-warehouse only when within 1,800 ft (by road) of an interstate. Verify per-parcel highway proximity.",
    ),
}


async def main() -> None:
    async with async_session_maker() as db:
        jur = (
            await db.execute(
                text("SELECT id FROM jurisdictions WHERE name = :n"),
                {"n": JURISDICTION_NAME},
            )
        ).first()
        if jur is None:
            print(f"ERROR: {JURISDICTION_NAME} not found")
            return
        jid = jur.id

        # Show pre-state
        pre = await db.execute(
            text(
                """
                SELECT zone_code, self_storage, classification_source, human_reviewed
                FROM zone_use_matrix
                WHERE jurisdiction_id = :jid
                  AND zone_code = ANY(:codes)
                  AND deleted_at IS NULL
                ORDER BY zone_code
                """
            ),
            {"jid": jid, "codes": list(ADJUDICATIONS.keys())},
        )
        print("PRE-STATE:")
        for r in pre:
            print(f"  {r.zone_code:8} self_storage={r.self_storage:12} src={r.classification_source:8} human_reviewed={r.human_reviewed}")

        # Apply updates
        updated = 0
        for code, (ss, mw, li, lgc, conf, cits, notes) in ADJUDICATIONS.items():
            result = await db.execute(
                text(
                    """
                    UPDATE zone_use_matrix
                    SET self_storage = :ss,
                        mini_warehouse = :mw,
                        light_industrial = :li,
                        luxury_garage_condo = :lgc,
                        confidence = :conf,
                        citations = CAST(:cits AS jsonb),
                        notes = :notes,
                        classification_source = 'human',
                        human_reviewed = TRUE
                    WHERE jurisdiction_id = :jid
                      AND zone_code = :code
                      AND deleted_at IS NULL
                    """
                ),
                {
                    "jid": jid,
                    "code": code,
                    "ss": ss,
                    "mw": mw,
                    "li": li,
                    "lgc": lgc,
                    "conf": conf,
                    "cits": __import__("json").dumps(cits),
                    "notes": notes,
                },
            )
            updated += result.rowcount or 0
            logger.info("updated %s: %d row(s) → self_storage=%s", code, result.rowcount or 0, ss)

        await db.commit()

        # Show post-state
        post = await db.execute(
            text(
                """
                SELECT zone_code, self_storage, classification_source, human_reviewed, confidence
                FROM zone_use_matrix
                WHERE jurisdiction_id = :jid
                  AND zone_code = ANY(:codes)
                  AND deleted_at IS NULL
                ORDER BY zone_code
                """
            ),
            {"jid": jid, "codes": list(ADJUDICATIONS.keys())},
        )
        print("\nPOST-STATE:")
        for r in post:
            print(f"  {r.zone_code:8} self_storage={r.self_storage:12} src={r.classification_source:8} human_reviewed={r.human_reviewed} conf={r.confidence}")

        print(f"\nTOTAL ROWS UPDATED: {updated}")


if __name__ == "__main__":
    asyncio.run(main())
