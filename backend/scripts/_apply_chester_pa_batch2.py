"""Chester County PA (jid 7f5293ff…) — Batch-2 Stage-4 verdicts for 4 towns.

PA spatially bound → NO rebind; muni-scoped use-table grounding. Use tables via
eCode360 print-endpoint (curl+UA). Self-storage detected BY NAME (catch #37).
zone_code strings match parcels.zoning_code exactly (from discovery). human_reviewed.

Discipline applied:
- catch #38 (I = Industrial vs Institutional): Charlestown "I" = INSTITUTIONAL (§27-802,
  not industrial) → prohibited; East Marlborough "ESI" = Educational/Scientific/
  Institutional (not industrial) → prohibited.
- NB-Twp J25 rule: where self-storage is NAMED and placed only in a specific district
  under a closed list, the warehouse⇒conditional convention does NOT override its absence
  elsewhere → Upper Uwchlan PI = PROHIBITED (self-storage named only in LI), not conditional.
- warehouse⇒conditional convention applied ONLY where self-storage is UNNAMED townwide and
  not excluded → West Whiteland I-1 (flagged CF-WW, like CF-UW).
- luxury_garage_condo prohibited everywhere (unnamed → closed-list #58).

Run: python scripts/_apply_chester_pa_batch2.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"
P, C, X = "permitted", "conditional", "prohibited"

TOWNS = {
    "Upper Uwchlan Township": ("Upper Uwchlan Twp Zoning Ch. 200 (eCode360 UP2148)", {
        "LI": ("Limited Industrial", P, P, P, X, 0.95, "§ 200-44.A(10)",
               '"Mini-warehouse/self storage facility." — permitted BY RIGHT (NAMED); '
               "light mfg by right § 200-44.A(1); closed-list '...and no other'."),
        "PI": ("Planned Industrial/Office", X, X, P, X, 0.85, "§ 200-49",
               "self-storage NOT named in PI (named ONLY in LI § 200-44.A(10)); closed-list "
               "'...and no other' → prohibited (NB-Twp J25: named-use placement overrides the "
               "warehouse-by-right convention). light_industrial permitted (electronic mfg § "
               "200-49.A + warehousing § 200-49.K by right)."),
        "C1": ("Village", X, X, X, X, 0.85, "§ 200-33",
               "self-storage absent from the C-1 Village closed list → prohibited."),
        "C3": ("Highway Commercial", X, X, X, X, 0.85, "§ 200-39",
               "self-storage absent from the C-3 closed list → prohibited."),
    }),
    "East Marlborough Township": ("East Marlborough Twp Zoning Ch. 450 (eCode360 EA6734)", {
        "LI": ("Limited Industrial", C, C, C, X, 0.90, "§ 450-1002.B(12)",
               '"Warehouse, mini-warehouse, or distribution center ..." — CONDITIONAL use '
               "(NAMED); base industrial + mfg also conditional (by-right only office ≤8,000 sf "
               "+ forestry)."),
        "ESI": ("Educational, Scientific & Institutional", X, X, X, X, 0.90, "§ 450-1102",
                "catch #38: ESI is INSTITUTIONAL, not industrial; self-storage absent + mfg "
                "explicitly excluded ('no ... manufacturing activities') → prohibited."),
        "MU": ("Multiple Use", X, X, X, X, 0.85, "§ 450-902",
               "self-storage absent from the MU closed list → prohibited."),
        "WMU": ("Willowdale Multiple Use", X, X, X, X, 0.85, "§ 450-752",
                "self-storage absent (residential-led closed list) → prohibited."),
        "LMU": ("Limited Multiple Use", X, X, X, X, 0.85, "§ 450-952",
                "self-storage absent from the LMU closed list → prohibited."),
        "C-2": ("Highway Commercial", X, X, X, X, 0.85, "§ 450-802",
                "self-storage absent from the C-2 retail closed list → prohibited."),
    }),
    "Charlestown Township": ("Charlestown Twp Zoning Ch. 27 (eCode360 CH3694)", {
        "I/O": ("Industrial/Office", C, C, C, X, 0.90, "§ 27-1002.1.A(3)(h)",
                '"Self-storage facility." — CONDITIONAL use (NAMED; standards § 27-1009, 3-acre '
                "min); warehouse + manufacturing also conditional; by-right = light assembly only."),
        "I": ("Institutional", X, X, X, X, 0.90, "§ 27-802",
              "catch #38: the 'I' map code is INSTITUTIONAL (public/semipublic: schools, "
              "churches, parks), NOT industrial; self-storage absent → prohibited."),
        "LI/B": ("Limited Industrial/Business", X, X, X, X, 0.85, "§ 27-1002.1.C",
                 "despite the name, self-storage/warehouse/mfg ABSENT (by-right ag/office/light "
                 "assembly; conditional only extraction + landfill) → prohibited."),
        "B-1": ("Business-1", X, X, X, X, 0.85, "§ 27-1002.1.B",
                "self-storage/warehouse absent (office/light-assembly + R&D CU) → prohibited."),
        "H": ("Historic (Charlestown Village)", X, X, X, X, 0.85, "§ 27-701",
              "architectural/historic-preservation district, not a use district; self-storage "
              "absent → prohibited."),
        "NC-1": ("Neighborhood Commercial-1", X, X, X, X, 0.85, "§ 27-902",
                 "self-storage absent (residential/retail/office) → prohibited."),
        "NC-2": ("Neighborhood Commercial-2", X, X, X, X, 0.85, "§ 27-9A02",
                 "self-storage absent (flex space ≠ self-storage) → prohibited."),
    }),
    "West Whiteland Township": ("West Whiteland Twp Zoning Ch. 325 (eCode360 WE2141)", {
        "I-1": ("Limited Industrial", C, C, P, X, 0.65, "§ 325-18B(3)",
                "self-storage UNNAMED townwide; warehouse PERMITTED by right § 325-18B(3) "
                "('Warehouses for wholesale sales, distribution or storage') + light mfg by "
                "right § 325-18B(4) → warehouse⇒self_storage CONDITIONAL convention (not "
                "excluded; flagged CF-WW)."),
        "TC": ("Town Center Mixed Use", X, X, X, X, 0.85, "§ 325-13",
               "office/retail/residential closed list, no warehouse/storage → prohibited."),
        "NC": ("Neighborhood Commercial", X, X, X, X, 0.85, "§ 325-14",
               "retail/office closed list, no warehouse → prohibited."),
        "O/L": ("Office/Laboratory", X, X, X, X, 0.85, "§ 325-15",
                "office/lab/R&D; conditional uses exclude warehouse/mfg → prohibited."),
        "O/R": ("Office/Residential", X, X, X, X, 0.85, "§ 325-15.1",
                "office/residential/limited-retail closed list, no warehouse → prohibited."),
        "O/C": ("Office/Commercial", X, X, X, X, 0.85, "§ 325-15.2",
                "office/retail closed list, no warehouse → prohibited."),
    }),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
  mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
  luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=90)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Chester" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}")
        await con.execute("SET statement_timeout = '90s'")
        for muni, (ordstr, zones) in TOWNS.items():
            for zc, (zname, ss, mw, li, lgc, conf, sec, quote) in zones.items():
                cites = json.dumps([{"ordinance": ordstr, "section": sec, "quote": quote}])
                note = f"{zc} ({zname}) — self_storage {ss}; {sec}: {quote[:160]}"
                await con.execute(SQL, JID, zc, zname, muni, ss, mw, li, lgc, cites, sec, conf, note)
        for muni in TOWNS:
            n = await con.fetchval("SELECT count(*) FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
                                   "AND municipality=$2 AND deleted_at IS NULL AND human_reviewed", JID, muni)
            j = await con.fetch(
                "SELECT p.zoning_code, count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
                "  AND prm.median_hhi>=100000) needles "
                "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
                "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
                "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
                "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
                "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 GROUP BY 1 HAVING count(*) FILTER "
                "(WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000)>0 "
                "ORDER BY 2 DESC", JID, muni)
            tot = sum(r['needles'] for r in j)
            print(f"  {muni}: {n} rows, needles={tot}: " + ", ".join(f"{r['zoning_code']}:{r['needles']}" for r in j))
    finally:
        await con.close()


asyncio.run(main())
