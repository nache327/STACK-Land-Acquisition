"""Princeton, NJ (Mercer County) — bank the zoning verdicts, muni-scoped.

OUTCOME: PROHIBITED EVERYWHERE — Princeton has NO industrial, warehouse or storage
zoning at all. This is a Winnetka-class correct no-op on the storage/LGC lanes, NOT
a gap: 8,390/8,391 parcels are bound (100.0%) from the municipality's own adopted
GIS layer, and every one of the 54 district codes resolves to a residential,
educational, business/mixed-use or conservation district whose closed use list
names no storage, warehouse, mini-warehouse or industrial use.

SOURCES (both pulled whole via the eCode360 print endpoint, client PR4086,
fetched 2026-08-12; B17A carries amendments through Ord. No. 2026-18, 5-11-2026):
  * Township legacy code  — Chapter T10B Land Use, ARTICLE XI Zoning
      https://ecode360.com/print/PR4086?guid=36739376&children=true
  * Borough legacy code   — Chapter B17A Land Use and Zoning
      https://ecode360.com/print/PR4086?guid=36813655&children=true
Princeton consolidated Borough+Township in 2013 but kept BOTH legacy zoning codes;
the GIS layer suffixes each zone with its code of origin (" T" / " B").

Parcel bind: municipal layer `Zoning_Districts_with_Links` (FeatureServer/0,
services5.arcgis.com/YDej7f2G8aXR0FNl), the ADOPTED layer — the separate
`2026_Zoning_Update_Draft_For_Review` layer was deliberately NOT used (Hudson trap).

THE DECISIVE CLAUSES (#37 verbatim basis):

TOWNSHIP (" T" zones + the unsuffixed T10B districts) — one article-wide closed
list, § T10B-254 "Uses prohibited in all districts":
  "All uses not expressly permitted in this article are prohibited, including, but
  not by way of limitation, the following: ... (g) Trucking terminals. (h)
  Manufacturing, other than the manufacture, assembly or treatment of products in
  connection with permitted research or product development in the OR district, or
  clearly incidental to and solely used in the conduct of a permitted retail
  business on premises in business districts, SC districts or S districts."
So beyond mere silence, trucking terminals and manufacturing are AFFIRMATIVELY
prohibited township-wide (#57). The OR districts' own list (§ T10B-268) is
offices/research/accessory only — 'research' is labs and product development, NOT
an industrial/flex family (catch #38, the Essex R-L lesson).

BOROUGH (" B" zones + E-5) — every district subdivision opens with its own closed
clause, pattern verbatim (R1 form): "In R1 districts, land and buildings may be
used only for the purposes set forth in section B17A-227 through B17A-230." The
per-district clause section is cited on each row below. R2 has no separate list:
§ B17A-239 "The use, bulk and parking and loading regulations in R2 districts are
the same as in R1 districts."

AH-6 / "AH B" — Borough-established AH districts whose borough use sections were
REPEALED: § B17A-202.1–202.6 Editor's Note (Ord. No. 2020-15): "See Township Code,
Chapter T10B, Land Use." The AH regulations live in T10B (§ T10B-272.8x et seq.),
so the T10B-254 closed list governs them.

THE #58 CLOSED-LIST SWEEP (both chapters, full text, 1.61M chars):
  * self-storage / mini-warehouse / miniwarehouse: ZERO occurrences as a use.
  * "warehouse": only inside the T10B *definition* of public utility infrastructure
    and a B17A wireless-facility definition ("storage sheds, storage buildings" as
    tower-accessory equipment) — definitions, not permitted uses.
  * "industrial": only in stormwater regulations, master-plan boilerplate and the
    T10B-254 manufacturing PROHIBITION itself.
  * "storage" collocated with a permitted/conditional-use context: one hit, an
    accessory "maintenance and storage" room within a principal residential use.
  * "garage" collocated with a use context: only accessory/required parking
    garages (e.g. MX § B17A-268.33(c)(4) "Parking garages of no more than three
    stories" as an ACCESSORY use). No garage-for-compensation use is NAMED
    anywhere => lgc-unnamed -> prohibited.
No district permits warehousing by right, so the warehouse-by-right => ss/mw
conditional convention never fires.

LGC LANE CONSEQUENCE: use_verdicts.py derives LGC from the sibling columns; with
human_reviewed AND self_storage='prohibited' AND light_industrial != 'permitted'
the QC veto yields LGC 'prohibited' for every Princeton row — consistent, and it
keeps the postingest gate's sibling-leak check green.

CASING: parcels.city is 'Princeton' (NJ mixed-case convention, no suffix — it is
the one consolidated municipality). Verified via SELECT DISTINCT before this was
written; the scope preflight below re-verifies at run time.

Uses SELECT-then-INSERT/UPDATE rather than ON CONFLICT: uq_zone_matrix is a unique
EXPRESSION index, and ON CONFLICT against it has bitten this repo before.

USAGE (from backend/):
    python scripts/_apply_princeton.py            # report what it would do
    python scripts/_apply_princeton.py --apply
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
MUNI = "Princeton"                                  # EXACT parcels.city value

_SWEEP = (
    "FULL-CHAPTER SWEEP (#58): the complete printed text of both legacy zoning "
    "codes (T10B Art. XI and B17A, eCode360 print endpoint, fetched 2026-08-12) "
    "contains NO self-storage, mini-warehouse, warehouse, or industrial use in any "
    "permitted or conditional use list. 'Warehouse'/'storage' appear only inside "
    "definitions (public-utility, wireless-facility equipment) and accessory "
    "provisions; 'industrial' only in stormwater/master-plan text and in the "
    "T10B-254 manufacturing prohibition itself. No garage-for-compensation use is "
    "named anywhere => luxury_garage_condo prohibited (lgc-unnamed rule). No "
    "district permits warehousing by right, so the warehouse-by-right => ss/mw "
    "conditional convention does not fire."
)

_T_CLOSED = (
    "CLOSED LIST + AFFIRMATIVE PROHIBITION, township-wide — § T10B-254 'Uses "
    "prohibited in all districts' (Ord. No. 2014-37; Ord. No. 856 § 2; Ord. No. "
    "94-2 § 1), verbatim: 'All uses not expressly permitted in this article are "
    "prohibited, including, but not by way of limitation, the following: ... (g) "
    "Trucking terminals. (h) Manufacturing, other than the manufacture, assembly "
    "or treatment of products in connection with permitted research or product "
    "development in the OR district, or clearly incidental to and solely used in "
    "the conduct of a permitted retail business on premises in business districts, "
    "SC districts or S districts.' Storage/warehouse uses are not expressly "
    "permitted anywhere in the article, and manufacturing/trucking are prohibited "
    "affirmatively (#57). "
)

_T_BASIS = _T_CLOSED + _SWEEP

_OR_EXTRA = (
    "District list § T10B-268 'Permitted uses; OR-1 and OR-2' (Ord. No. 2019-6 "
    "line), verbatim heads: '(a) General, professional or other office uses. (b) "
    "Any uses of a research nature involving scientific investigation, research or "
    "engineering study or related instruction, product development and similar "
    "related uses. (c) Accessory uses...' — offices and research labs, NOT an "
    "industrial/flex family (catch #38). "
)

_AH_B_NOTE = (
    "Borough-established AH district whose borough use sections were REPEALED — "
    "§ B17A-202.1 through § B17A-202.6 Editor's Note (Ord. No. 2020-15): 'See "
    "Township Code, Chapter T10B, Land Use.' The governing AH regulations sit in "
    "T10B, so the § T10B-254 closed list applies. "
)

def _b_basis(district: str, clause_sec: str, first: str, last: str,
             extra: str = "") -> str:
    return (
        f"CLOSED USE CLAUSE, district-scoped — § {clause_sec} 'Use regulations — "
        f"Generally', verbatim pattern: 'In {district} districts, land and "
        f"buildings may be used only for the purposes set forth in sections "
        f"{first} through {last}.' Those sections' permitted and conditional "
        f"lists name no storage, warehouse or industrial use. {extra}" + _SWEEP
    )

# ---------------------------------------------------------------------------
# Township zones (T10B Art. XI) — the " T"-suffixed codes plus the unsuffixed
# districts codified in T10B (AH family, R-*/AH, R-H/12, R-HF-W, R-M, RH-8, RSC-3).
_TOWNSHIP = [
    "B-1 T", "B-2 T", "E-1 T", "E-2 T", "E-4 T", "OR-1 T", "OR-2 T", "POR T",
    "R-1 T", "R-2 T", "R-3 T", "R-4 T", "R-5 T", "R-6 T", "R-7 T", "R-8 T",
    "R-9 T", "R-A T", "R-B T", "R-T T", "RO T", "S-1 T", "S-2 T", "SC T",
    "AH-3", "AH-4", "AH-5", "AH-7", "R-1/AH", "R-2/AH", "R-H/12", "R-HF-W",
    "R-M", "RH-8", "RSC-3",
]

# Borough zones (B17A) — zone code -> (district label, clause section, use-range).
_BOROUGH = {
    "R-1 B":  ("R1",   "B17A-227",    ("B17A-227", "B17A-230"), ""),
    "R-2 B":  ("R2",   "B17A-239",    ("B17A-227", "B17A-230"),
               "§ B17A-239 verbatim: 'The use, bulk and parking and loading "
               "regulations in R2 districts are the same as in R1 districts'. "),
    "R-3 B":  ("R3",   "B17A-241",    ("B17A-241", "B17A-244"), ""),
    "R-4 B":  ("R4",   "B17A-253",    ("B17A-253", "B17A-256"), ""),
    "R-4A B": ("R4A",  "B17A-268.2",  ("B17A-268.2", "B17A-268.31"), ""),
    "RO B":   ("RO",   "B17A-269",    ("B17A-269", "B17A-272"), ""),
    "RB B":   ("RB",   "B17A-283",    ("B17A-283", "B17A-286"), ""),
    "NB B":   ("NB",   "B17A-290",    ("B17A-290", "B17A-294"), ""),
    "CB B":   ("CB",   "B17A-304",    ("B17A-304", "B17A-308"), ""),
    "SB B":   ("SB",   "B17A-320",    ("B17A-320", "B17A-324"),
               "§ B17A-321 permits offices (limited), parks, churches, banks; no "
               "storage or warehouse entry. "),
    "E-1 B":  ("E1",   "B17A-331",    ("B17A-331", "B17A-334"), ""),
    "E-2 B":  ("E2",   "B17A-345",    ("B17A-345", "B17A-348"), ""),
    "E-3 B":  ("E3",   "B17A-354.1",  ("B17A-354.1", "B17A-354.4"), ""),
    "E-4 B":  ("E4",   "B17A-354.11", ("B17A-354.11", "B17A-354.14"), ""),
    "E-5":    ("E5",   "B17A-354.20", ("B17A-354.20", "B17A-354.23"), ""),
    "MX B":   ("MX",   "B17A-268.32", ("B17A-268.32", "B17A-268.47"),
               "§ B17A-268.33 permits residential, parks, public buildings; "
               "accessory 'Parking garages of no more than three stories' are "
               "accessory parking, not a garage-for-compensation use. "),
    "MRRO B": ("MRRO", "B17A-355",    ("B17A-355", "B17A-356.2"),
               "§ B17A-356 permits hospital and medical office uses. "),
}

# Borough-listed AH districts governed by T10B after Ord. No. 2020-15's repeal.
_AH_BOROUGH = ["AH-6", "AH B"]


def _rows():
    rows = []
    for z in _TOWNSHIP:
        extra = _OR_EXTRA if z.startswith("OR-") else ""
        rows.append((z, "T10B-254" + ("; T10B-268" if extra else ""),
                     _T_CLOSED + extra + _SWEEP))
    for z, (label, sec, (first, last), extra) in _BOROUGH.items():
        rows.append((z, sec, _b_basis(label, sec, first, last, extra)))
    for z in _AH_BOROUGH:
        rows.append((z, "B17A-202.1-202.6 (repealed); T10B-254",
                     _AH_B_NOTE + _T_CLOSED + _SWEEP))
    return rows


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
VALUES ($1::uuid, $2, $3, 'prohibited'::use_permission_enum,
        'prohibited'::use_permission_enum, 'prohibited'::use_permission_enum,
        'prohibited'::use_permission_enum, true,
        'human'::classification_source_enum, $4, $5, $6::jsonb, 1.0, now(), now())
"""

_UPDATE = """
UPDATE zone_use_matrix
   SET self_storage = 'prohibited'::use_permission_enum,
       mini_warehouse = 'prohibited'::use_permission_enum,
       light_industrial = 'prohibited'::use_permission_enum,
       luxury_garage_condo = 'prohibited'::use_permission_enum,
       human_reviewed = true,
       classification_source = 'human'::classification_source_enum,
       notes = $1, cited_subsection = $2, citations = $3::jsonb,
       confidence = 1.0, updated_at = now()
 WHERE id = $4
"""


async def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Princeton NJ zoning verdicts.")
    ap.add_argument("--apply", action="store_true", help="Write. Otherwise report only.")
    args = ap.parse_args()

    rows = _rows()

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

        # coverage preflight: every bound zoning_code must have a row here
        db_zones = {r["zoning_code"] for r in await c.fetch(
            "SELECT DISTINCT zoning_code FROM parcels "
            "WHERE jurisdiction_id=$1::uuid AND city=$2 "
            "AND zoning_code IS NOT NULL", JID, MUNI)}
        script_zones = {z for z, _, _ in rows}
        missing = db_zones - script_zones
        if missing:
            print(f"REFUSING: bound zones with no verdict row: {sorted(missing)}",
                  flush=True)
            sys.exit(3)
        extra = script_zones - db_zones
        if extra:
            print(f"note: verdict rows for currently-unbound zones (kept): "
                  f"{sorted(extra)}", flush=True)

        for zone, cite, basis in rows:
            if len(basis) > 2048:                     # notes is varchar(2048)
                print(f"REFUSING: notes for {zone} is {len(basis)} chars > 2048",
                      flush=True)
                sys.exit(4)
            existing = await c.fetchrow(_SELECT, JID, zone, MUNI)
            citations = json.dumps([{"section": cite, "text": basis}])
            action = "UPDATE" if existing else "INSERT"
            print(f"  {action} {zone:<10} ss/mw/li/lgc=prohibited  "
                  f"notes={len(basis)}c", flush=True)
            if not args.apply:
                continue
            if existing:
                await c.execute(_UPDATE, basis, cite, citations, existing["id"])
            else:
                await c.execute(_INSERT, JID, zone, MUNI, basis, cite, citations)

        if not args.apply:
            print("\nreport only — re-run with --apply", flush=True)
            return
        print(f"\napplied {len(rows)} rows scoped to municipality={MUNI!r}",
              flush=True)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
