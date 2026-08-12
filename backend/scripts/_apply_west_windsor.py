"""West Windsor Township, NJ (Mercer County) — bank the zoning verdicts, muni-scoped.

THIS IS A LIVE STORAGE MUNI: self-storage is AFFIRMATIVELY NAMED as a permitted
principal use in TWO districts (RO-1 and ROM-3, both by 2020/2021 ordinances), and
the PCD district permits warehousing/distribution by right (=> ss/mw conditional
under the established warehouse-by-right convention).

SOURCE: Code of the Township of West Windsor, Chapter 200 Land Use, Part 4 Zoning
(eCode360 client WE1666, legislation through 2026-03-30), pulled whole via the
print endpoint: https://ecode360.com/print/WE1666?guid=8064661&children=true
(fetched 2026-08-12).

Parcel bind: township GIS `Zoning_Web_Map_WFL1/FeatureServer/12` "Zoning
Districts" (ADOPTED layer; the "Proposed Zones"/"Proposed Zoning" layers 34/49
deliberately NOT used). Bind rate 9,319/9,324 = 99.9%. Layer codes are stored
VERBATIM on parcels — including the layer's quirks: `R0-1` (zero, not the letter
O, for the ordinance's RO-1) and `R & D` (spaces). Matrix rows below match the
PARCEL spelling; `RO-1` is also banked for future re-binds that fix the typo.

DISTRICT VERDICTS (#37 verbatim bases carried on each row):

  ss/mw PERMITTED:  R0-1 / RO-1 (§ 200-219.5A(9) 'Self-storage facilities',
                    A(10) 'Warehousing and distribution facilities'), ROM-3
                    (§ 200-213A(5)/(3), latent — no parcels currently bound).
  ss/mw CONDITIONAL: PCD (warehouse-by-right => ss/mw conditional; § 200-207.3B(5)
                    permits 'Warehousing and distribution facilities' by right and
                    the district intent says 'Warehouse and distribution uses are
                    encouraged'; self-storage itself is NOT named).
  li PERMITTED:     R0-1/RO-1, ROM-3, PCD, ROM-1, ROM-2, ROM-4 (limited
                    manufacturing and/or warehousing by right).
  li CONDITIONAL:   R & D (manufacturing reachable ONLY through a mixed-use
                    planned development per ROM-1 § 200-209A(8), with the 30%
                    low-traffic-use condition of § 200-219.2G(3)).
  everything else:  PROHIBITED. Every WW district section opens with its own
                    closed clause ('no building or premises shall be used ...
                    except for one or more of the following uses'); the full-part
                    sweep found no storage/warehouse/manufacturing use named in
                    any residential, B-*, P-*, E/EH, PRN/PRRC/PMN list. B-1 goes
                    further and EXCLUDES 'outdoor storage facilities' verbatim.

luxury_garage_condo: PROHIBITED on every row — no garage-for-compensation use is
named anywhere in Part 4 (swept); lgc-unnamed -> prohibited. The LGC lane derives
from the sibling columns at query time, so RO-1/ROM-3/PCD/ROM-* will still light
up for LGC via their li/ss standings — as intended.

NOT COVERED HERE — RP-1..RP-11 (~83 parcels): districts of the PRINCETON JUNCTION
REDEVELOPMENT PLAN, a separately adopted plan document that chapter 200 only
references. Escalated to outputs/_exceptions_mercer.md rather than guessed (#37).
Parcels in RP zones simply stay unscored until that plan text is grounded.

CASING: parcels.city = 'West Windsor township' (NJ convention). Preflight verifies.

Uses SELECT-then-INSERT/UPDATE (uq_zone_matrix is an expression index; no ON
CONFLICT).

USAGE (from backend/):
    python scripts/_apply_west_windsor.py            # report only
    python scripts/_apply_west_windsor.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

JID = "e6274124-e04c-4212-a35f-ff1b8a803fe0"       # Mercer County, NJ
MUNI = "West Windsor township"                      # EXACT parcels.city value

_SWEEP = (
    "FULL-PART SWEEP (#58): the complete printed text of Ch. 200 Part 4 Zoning "
    "(eCode360 print endpoint, WE1666, fetched 2026-08-12, legislation through "
    "2026-03-30) was swept for storage/warehouse/manufacturing/garage uses. "
    "Outside the districts called out above, every hit is boilerplate (snow "
    "storage, 'furnishings manufactured from recycled materials', accessory "
    "sheds, bulk tables) — no storage, warehouse, manufacturing or "
    "garage-for-compensation use is named in any other district's permitted, "
    "accessory or conditional list. lgc-unnamed -> prohibited."
)

_CLOSED = (
    "Each West Windsor district section opens with its own closed clause, "
    "pattern verbatim (ROM-1 form, § 200-209A): 'In a ROM-1 District, no "
    "building or premises shall be used and no building shall be erected or "
    "altered which is arranged, intended or designed to be used except for one "
    "or more of the following uses'. An unnamed use is therefore prohibited, "
    "not unclear. "
)

_RO1_BASIS = (
    "SELF-STORAGE IS NAMED AS A PERMITTED PRINCIPAL USE. § 200-219.5 'RO-1 "
    "District (research, office) use regulations' A. Permitted uses, verbatim "
    "entries: '(9) Self-storage facilities. [Added 5-24-2021 by Ord. No. "
    "2021-09]' and '(10) Warehousing and distribution facilities. [Added "
    "5-24-2021 by Ord. No. 2021-09]' => self_storage and mini_warehouse "
    "PERMITTED; warehousing/distribution by right => light_industrial PERMITTED. "
    "Bulk (§ 200-219.6): minimum lot area for warehouse and distribution "
    "facilities 12 acres; side/rear yards increased to 300 feet for warehouse "
    "and distribution facilities. NOTE the GIS layer spells this zone 'R0-1' "
    "(digit zero); the matrix row matches the parcel spelling verbatim. "
    + _CLOSED + _SWEEP
)

_ROM3_BASIS = (
    "SELF-STORAGE IS NAMED AS A PERMITTED PRINCIPAL USE (LATENT — no parcels "
    "currently bind to ROM-3; banked so it bites on any future rebind). "
    "§ 200-213 'ROM-3 Industrial District' A. Permitted uses, verbatim: '(3) "
    "Warehousing and distribution facilities. [Added 12-14-2020 by Ord. No. "
    "2020-24] (4) Finishing and assembly of products. (5) Self-storage "
    "facilities. [Added 12-14-2020 by Ord. No. 2020-24]' plus '(1) All those "
    "permitted uses as listed for an ROM-2 District' (which includes limited "
    "manufacturing) => ss/mw/li PERMITTED. Bulk (§ 200-214): minimum lot area "
    "for warehouse and distribution facilities 25 acres. " + _CLOSED + _SWEEP
)

_PCD_BASIS = (
    "WAREHOUSE-BY-RIGHT => ss/mw CONDITIONAL (established convention; "
    "self-storage itself is NOT named). § 200-207.3 'PCD Planned Commercial "
    "District use regulations' [Added 12-14-2020 by Ord. No. 2020-25] B. "
    "Permitted uses, verbatim entries: '(5) Warehousing and distribution "
    "facilities. (6) Finishing and assembly of products. (7) Limited "
    "manufacturing.' — and the district intent (A) says verbatim: 'Warehouse "
    "and distribution uses are encouraged within the remainder of the "
    "district.' => light_industrial PERMITTED; self_storage/mini_warehouse "
    "CONDITIONAL via the warehouse-by-right convention. " + _CLOSED + _SWEEP
)

_ROM1_BASIS = (
    "LIMITED MANUFACTURING BY RIGHT; WAREHOUSE ACCESSORY-ONLY. § 200-209 "
    "'ROM-1 Industrial District' A. Permitted uses: '(4) Limited manufacturing "
    "associated with such specialty industry groupings as agriculture, "
    "aerospace, computers, telecommunications, instrumentation, biomedical, "
    "medical, pharmaceutical and electronics.' => light_industrial PERMITTED. "
    "Storage appears only as an ACCESSORY: A(6)(i) 'Warehouse facilities and "
    "wholesale storage within a completely enclosed building, the latter being "
    "incidental and accessory to a permitted or conditional use' — accessory to "
    "another principal use, not a standalone storage business; and A(1) "
    "affirmatively excludes labs 'involving the manufacturing, sale, "
    "processing, warehousing, distribution or fabrication of material ... "
    "except as incidental'. No self-storage use is named => ss/mw PROHIBITED "
    "(warehouse-by-right does not apply to an accessory-only entry). "
    + _CLOSED + _SWEEP
)

_ROM2_BASIS = (
    "LIMITED MANUFACTURING BY RIGHT; NO STORAGE USE NAMED. § 200-211 'ROM-2 "
    "Industrial District' A. Permitted uses, verbatim entries: '(1) Research, "
    "testing, analytical and product development laboratories not involving "
    "the manufacturing, sale, processing, warehousing, distribution or "
    "fabrication of material, products or goods, except as incidental to the "
    "principal permitted uses. ... (4) Limited manufacturing. (5) Publishing "
    "houses and commercial printing plants. (6) Commercial recreation "
    "facilities within an existing or former warehouse building.' => "
    "light_industrial PERMITTED. No self-storage/warehouse principal use is "
    "named (A(6) refers to reuse of a former warehouse BUILDING for recreation, "
    "not to warehousing as a use); accessory storage only via A(9)(f) "
    "'Maintenance, utility and storage facilities incidental to the principal "
    "use' => ss/mw PROHIBITED. " + _CLOSED + _SWEEP
)

_ROM4_BASIS = (
    "LIMITED MANUFACTURING BY RIGHT; NO STORAGE USE NAMED. § 200-215 'ROM-4 "
    "Industrial District' A. Permitted uses: labs (with the same 'not involving "
    "... warehousing' exclusion), offices, computer centers, commercial "
    "recreation in a former warehouse building, farm uses, accessory uses "
    "('(f) Maintenance, utility and storage facilities incidental to the "
    "principal use, provided that they are in fully enclosed buildings'), "
    "township buildings, and verbatim '(8) Limited manufacturing.' => "
    "light_industrial PERMITTED; ss/mw PROHIBITED (no storage principal use "
    "named). " + _CLOSED + _SWEEP
)

_RD_BASIS = (
    "MANUFACTURING ONLY VIA PLANNED DEVELOPMENT => li CONDITIONAL. § 200-219.1 "
    "'R&D Research and Development (research, office) use regulations' A. "
    "Permitted uses, verbatim: '(1) Mixed used planned developments as set "
    "forth in the ROM-1 District, provided that no less than 30% of the floor "
    "area be low traffic-generating uses as set forth in § 200-219.2G(3).' — "
    "ROM-1's mixed-use menu (§ 200-209A(8)) includes limited-manufacturing "
    "incubator facilities, so light industrial is reachable but only inside a "
    "planned development meeting those conditions => light_industrial "
    "CONDITIONAL. No storage/warehouse principal use is named in the R&D list "
    "or restored by it => ss/mw PROHIBITED. GIS spells the zone 'R & D'; the "
    "row matches the parcel spelling verbatim. " + _CLOSED + _SWEEP
)

_ROR_BASIS = (
    "ROM-1 USES MINUS MANUFACTURING => all prohibited. § 200-219.3 'ROR "
    "Industrial District (research, office, recreation)' A. Permitted uses, "
    "verbatim: '(1) All the permitted and accessory uses permitted in the "
    "ROM-1 District by § 200-209A, except that the limited manufacturing uses "
    "set forth in § 200-209A(4) shall not be permitted. Additionally, the "
    "limited manufacturing uses set forth in portions of § 200-209A(8)(a)[1] "
    "and [2] shall not be permitted.' — an AFFIRMATIVE carve-out of the "
    "industrial family (#57). ROM-1's storage entries are accessory-only, so "
    "nothing storage-like carries in => ss/mw/li PROHIBITED. "
    + _CLOSED + _SWEEP
)

_RO_BASIS = (
    "OFFICES AND LABS ONLY. § 200-218 'RO Industrial District (research, "
    "office)' A. Permitted uses (the whole list): '(1) Research, testing and "
    "analytical laboratories. (2) General, corporate, administrative and "
    "professional offices. (3) Municipal center activities ... (4) All farm "
    "and agricultural uses ... (5) Accessory uses and accessory buildings "
    "incidental to the above uses.' B. Conditional uses: antennas and utility "
    "substations only. No storage, warehouse or manufacturing use is named "
    "=> ss/mw/li PROHIBITED. " + _CLOSED + _SWEEP
)

_B1_BASIS = (
    "AFFIRMATIVE EXCLUSION (#57): § 200-199 'B-1 Business District (limited "
    "convenience center)' permits neighborhood retail/services verbatim "
    "'excluding drive-in establishments and outdoor storage facilities', plus "
    "professional offices capped at 20% of GFA. No storage, warehouse or "
    "manufacturing use is named => ss/mw/li PROHIBITED. " + _CLOSED + _SWEEP
)

_GENERIC_PROHIBITED = (
    "No storage, warehouse, mini-warehouse, manufacturing or "
    "garage-for-compensation use is named in this district's permitted, "
    "accessory or conditional lists (verified against the full district "
    "section in the printed chapter). " + _CLOSED + _SWEEP
)

# (zone_code_as_bound, ss, mw, li, cited_subsection, basis)
ROWS = [
    # -- live storage districts ------------------------------------------------
    ("R0-1",  "permitted",   "permitted",   "permitted",
     "200-219.5A(9),(10); 200-219.6", _RO1_BASIS),
    ("RO-1",  "permitted",   "permitted",   "permitted",
     "200-219.5A(9),(10); 200-219.6", _RO1_BASIS),      # ordinance spelling, latent
    ("ROM-3", "permitted",   "permitted",   "permitted",
     "200-213A(3),(4),(5); 200-214", _ROM3_BASIS),      # latent
    ("PCD",   "conditional", "conditional", "permitted",
     "200-207.3A,B(5),(6),(7)", _PCD_BASIS),
    # -- industrial family, li only --------------------------------------------
    ("ROM-1", "prohibited", "prohibited", "permitted",
     "200-209A(4),(6)(i)", _ROM1_BASIS),
    ("ROM-2", "prohibited", "prohibited", "permitted",
     "200-211A(1),(4)", _ROM2_BASIS),
    ("ROM-4", "prohibited", "prohibited", "permitted",
     "200-215A(1),(8)", _ROM4_BASIS),
    ("R & D", "prohibited", "prohibited", "conditional",
     "200-219.1A(1); 200-219.2G(3)", _RD_BASIS),
    ("ROR",   "prohibited", "prohibited", "prohibited",
     "200-219.3A(1)", _ROR_BASIS),
    ("RO",    "prohibited", "prohibited", "prohibited",
     "200-218A,B", _RO_BASIS),
    ("B-1",   "prohibited", "prohibited", "prohibited",
     "200-199", _B1_BASIS),
]

# All-prohibited districts sharing the generic closed-list basis.
_PROHIBITED_ZONES = {
    # business / office / village
    "B-2": "200-201", "B-2A": "200-202.1", "B-3": "200-203", "B-4": "200-203.1",
    "P": "200-204", "P-1": "200-206", "P-3": "200-207.1",
    # education / elderly
    "E": "200-221", "EH": "200-192",
    # residential + conservation + planned residential/mixed
    "RR/C": "200-156", "R-1/C": "200-158", "R-1A": "200-159.1", "R-2": "200-160",
    "R-30": "200-162", "R-30A": "200-164", "R-30B": "200-166", "R-30C": "200-168",
    "R-30D": "200-170", "R-24": "200-172", "R-20": "200-173.1",
    "R-20A": "200-173.3", "R-20B": "200-173.5", "R-3": "200-175",
    "R-3A": "200-176", "R-3.5": "200-178.1", "R-4": "200-179", "R-4A": "200-180",
    "R-4B": "200-183", "R-5": "200-185", "R-5A": "200-187", "R-5B": "200-189",
    "R-5C": "200-189.1", "R-5D": "200-189.3", "R-5E": "200-189.4",
    "R-5F": "200-189.5", "R-5G": "200-189.6", "R-5H": "200-189.7",
    "R-5I": "200-189.8", "R-5J": "200-189.9",
    "PRN-1": "200-190", "PRRC": "200-194", "PRRC-1": "200-194",
    "PMN": "200-194.4", "PMN-1": "200-194.4", "R-1/O": "200-195",
}
for z, sec in sorted(_PROHIBITED_ZONES.items()):
    ROWS.append((z, "prohibited", "prohibited", "prohibited", sec,
                 _GENERIC_PROHIBITED))

# RP-1..RP-11 deliberately ABSENT: Princeton Junction Redevelopment Plan
# districts, governed by a separately adopted plan document (escalated to
# outputs/_exceptions_mercer.md). Unscored beats guessed.

_SELECT = """
SELECT id FROM zone_use_matrix
 WHERE jurisdiction_id = $1::uuid AND zone_code = $2 AND municipality = $3
   AND deleted_at IS NULL
"""

_INSERT = """
INSERT INTO zone_use_matrix
  (jurisdiction_id, zone_code, municipality, self_storage, mini_warehouse,
   light_industrial, luxury_garage_condo, human_reviewed, classification_source,
   notes, cited_subsection, citations, confidence, created_at, updated_at)
VALUES ($1::uuid, $2, $3, $4::use_permission_enum, $5::use_permission_enum,
        $6::use_permission_enum, 'prohibited'::use_permission_enum, true,
        'human'::classification_source_enum, $7, $8, $9::jsonb, 1.0, now(), now())
"""

_UPDATE = """
UPDATE zone_use_matrix
   SET self_storage = $1::use_permission_enum,
       mini_warehouse = $2::use_permission_enum,
       light_industrial = $3::use_permission_enum,
       luxury_garage_condo = 'prohibited'::use_permission_enum,
       human_reviewed = true,
       classification_source = 'human'::classification_source_enum,
       notes = $4, cited_subsection = $5, citations = $6::jsonb,
       confidence = 1.0, updated_at = now()
 WHERE id = $7
"""


async def main() -> None:
    ap = argparse.ArgumentParser(description="Apply West Windsor NJ zoning verdicts.")
    ap.add_argument("--apply", action="store_true", help="Write. Otherwise report only.")
    args = ap.parse_args()

    c = await asyncpg.connect(get_sync_dsn(), timeout=60)
    await c.execute("SET statement_timeout = 120000")
    try:
        n_muni = await c.fetchval(
            "SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2",
            JID, MUNI)
        print(f"scope municipality={MUNI!r} -> {n_muni:,} parcels in Mercer NJ",
              flush=True)
        if n_muni == 0:
            print("REFUSING: scope matches 0 parcels — casing is wrong.", flush=True)
            sys.exit(2)

        db_zones = {r["zoning_code"] for r in await c.fetch(
            "SELECT DISTINCT zoning_code FROM parcels "
            "WHERE jurisdiction_id=$1::uuid AND city=$2 "
            "AND zoning_code IS NOT NULL", JID, MUNI)}
        script_zones = {z for z, *_ in ROWS}
        missing = {z for z in db_zones - script_zones
                   if not z.startswith("RP-")}          # RP-* escalated, not missed
        if missing:
            print(f"REFUSING: bound zones with no verdict row: {sorted(missing)}",
                  flush=True)
            sys.exit(3)
        rp = sorted(z for z in db_zones if z.startswith("RP-"))
        if rp:
            print(f"note: RP zones left unscored pending the Princeton Junction "
                  f"Redevelopment Plan: {rp}", flush=True)

        for zone, ss, mw, li, cite, basis in ROWS:
            if len(basis) > 2048:
                print(f"REFUSING: notes for {zone} is {len(basis)} chars > 2048",
                      flush=True)
                sys.exit(4)
            existing = await c.fetchrow(_SELECT, JID, zone, MUNI)
            citations = json.dumps([{"section": cite, "text": basis}])
            action = "UPDATE" if existing else "INSERT"
            print(f"  {action} {zone:<8} ss={ss:<11} mw={mw:<11} li={li:<11} "
                  f"notes={len(basis)}c", flush=True)
            if not args.apply:
                continue
            if existing:
                await c.execute(_UPDATE, ss, mw, li, basis, cite, citations,
                                existing["id"])
            else:
                await c.execute(_INSERT, JID, zone, MUNI, ss, mw, li, basis,
                                cite, citations)

        if not args.apply:
            print("\nreport only — re-run with --apply", flush=True)
            return
        print(f"\napplied {len(ROWS)} rows scoped to municipality={MUNI!r}",
              flush=True)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
