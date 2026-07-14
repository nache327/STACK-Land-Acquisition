"""Chester County PA (jid 7f5293ff…) — Batch-1 Stage-4 verdicts for 4 towns.

PA parcels are spatially bound (zoning_code already present) → NO rebind; straight
muni-scoped use-table grounding. All use tables fetched via the eCode360 print
endpoint (curl+browser-UA; whole chapter one fetch). Self-storage detected BY NAME
(catch #37 verbatim basis). municipality = exact parcels.city (PA mixed-case,
"Township" suffix). human_reviewed=true. catch #38 confirmed I-codes = Industrial
(not Institutional) in each town.

WEST GOSHEN TWP (Ch.84, eCode360 WE0457; closed-list "...for any of the following
purposes and for no other"): self-storage NAMED, PERMITTED BY RIGHT in all industrial
+ multipurpose districts.
NEW GARDEN TWP (Ch.200, NE2032; closed-list "...and for no other"): self-storage NAMED,
PERMITTED BY RIGHT in C/I only.
EAST GOSHEN TWP (Ch.240, EA1698): self-storage NAMED CONDITIONAL in I-1; EXPRESSLY
PROHIBITED in BP (§240-21C(2)(b)).
UWCHLAN TWP (Ch.265, UW2708; NOT closed-list — open catch-all conditional): self-storage
UNNAMED; warehousing+light-mfg by-right in PI/PIC/PCID → warehouse⇒conditional convention.

luxury_garage_condo PROHIBITED everywhere (unnamed; closed-list sweep #58 / not a
warehouse use). Verify rows via SELECT (catch #42, run at end).
Run: python scripts/_apply_chester_pa_batch1.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"  # Chester County, PA

# municipality -> ordinance-string -> {zone_code: (zone_name, ss, mw, li, lgc, conf, section, quote)}
P, C, X = "permitted", "conditional", "prohibited"
TOWNS = {
    "West Goshen Township": ("West Goshen Twp Code Ch. 84 Zoning (eCode360 WE0457)", {
        "I-1": ("Campus Light Industrial", P, P, P, X, 0.95, "§ 84-37A(2.1)",
                '"Miniwarehouse or self-storage facility." (permitted by right; closed-list district)'),
        "I-2": ("Light Industrial", P, P, P, X, 0.95, "§ 84-38A(2.1)",
                '"Miniwarehouse or self-storage facility." (permitted by right)'),
        "I-3": ("General Industrial", P, P, P, X, 0.95, "§ 84-39A(2.1)",
                '"Miniwarehouse or self-storage facility." (permitted by right)'),
        "I-2-R": ("Light Industrial — Restricted", P, P, P, X, 0.95, "§ 84-40A(2.1)",
                  '"Miniwarehouse." (permitted by right)'),
        "I-C": ("Industrial-Commercial", P, P, P, X, 0.95, "§ 84-41A(3)",
                '"Miniwarehouse or self-storage facility." (permitted by right)'),
        "MPD": ("Multipurpose", P, P, P, X, 0.90, "§ 84-96A/B",
                '"All uses permitted in the I-2 Light Industrial District" / "...I-3 General '
                'Industrial District" — incorporates the by-right miniwarehouse/self-storage use.'),
        "C-4": ("Special Limited Business & Apartment", X, X, X, X, 0.88, "§ 84-28",
                "self-storage NOT listed among the C-4 permitted uses (closed-list '...and for no "
                "other'); wholesale storage is a distinct named use — self-storage prohibited."),
        "C-5": ("General Highway Commercial", X, X, X, X, 0.88, "§ 84-32",
                "self-storage NOT listed (closed-list); prohibited."),
    }),
    "New Garden Township": ("New Garden Twp Code Ch. 200 Zoning (eCode360 NE2032)", {
        "C/I": ("Commercial/Industrial", P, P, C, X, 0.95, "§ 200-45.A(17)",
                '"Self-storage facility." — permitted by right (named); light manufacturing is '
                "conditional (§ 200-45.C(3)); closed-list '...and for no other'."),
        "H/C": ("Highway Commercial", X, X, X, X, 0.88, "§ 200-35",
                "self-storage absent from the H/C closed list — prohibited."),
        "BP": ("Business Park", X, X, C, X, 0.88, "§ 200-50",
               "self-storage absent (prohibited); light industrial only via Business-Park "
               "conditional use (§ 200-50.B)."),
        "ADZ": ("Airport Development Zone", X, X, X, X, 0.88, "§ 200-53.3",
                "self-storage absent from the ADZ closed list — prohibited."),
    }),
    "East Goshen Township": ("East Goshen Twp Code Ch. 240 Zoning (eCode360 EA1698)", {
        "I-1": ("Light Industrial", C, C, C, X, 0.90, "§ 240-19C(2)",
                '"Wholesaling, warehousing and distribution, including self-storage and '
                'mini-warehouse developments ..." — permitted CONDITIONAL use (named).'),
        "BP": ("Business Park", X, X, C, X, 0.92, "§ 240-21C(2)(b)",
               'EXPRESSLY PROHIBITED: "(b) Self-storage developments and/or mini-warehousing." '
               "(warehousing/distribution otherwise a conditional use)."),
        "I-2": ("Planned Business, Research & Limited Industrial", X, X, C, X, 0.85, "§ 240-20",
                "self-storage/mini-warehouse and general warehousing ABSENT; only product-specific "
                "manufacturing is conditional (§ 240-20D(1)) — self-storage prohibited (catch #57)."),
        "C-1": ("Community Commercial", X, X, X, X, 0.85, "§ 240-14", "self-storage absent — prohibited."),
        "C-2": ("Local Convenience Commercial", X, X, X, X, 0.85, "§ 240-15", "self-storage absent — prohibited."),
        "C-4": ("Planned Highway Commercial", X, X, X, X, 0.85, "§ 240-16", "self-storage absent — prohibited."),
        "C-5": ("Government, Finance and Office", X, X, X, X, 0.85, "§ 240-17", "self-storage absent — prohibited."),
    }),
    "Uwchlan Township": ("Uwchlan Twp Code Ch. 265 Zoning (eCode360 UW2708)", {
        "PI": ("Planned Industrial", C, C, P, X, 0.65, "§ 509.3.a",
               '"Manufacturing, wholesaling, processing, warehousing, and distributing ..." '
               "permitted by right → warehouse⇒self_storage CONDITIONAL convention (self-storage "
               "unnamed; NOT a closed list — open conditional catch-all § 509.5.f)."),
        "PIC": ("Planned Industrial-Commercial", C, C, P, X, 0.65, "§ 507.3.a",
                '"Manufacturing, wholesaling, processing, warehousing and distributing ..." by '
                "right → warehouse⇒self_storage CONDITIONAL convention (unnamed; open list)."),
        "PCID": ("Planned Commercial Industrial Development", C, C, P, X, 0.65, "§ 508.4.k",
                 '"Wholesaling, warehousing and distributing, provided that there shall be no '
                 'exterior evidence ..." (indoor) → warehouse⇒self_storage CONDITIONAL convention.'),
        "PC": ("Planned Commercial", X, X, X, X, 0.85, "§ 505.3.d",
               '"...no merchandise shall be warehoused on the premises ..." — warehousing/'
               "self-storage excluded; prohibited."),
        "PC-2": ("Planned Commercial (interchange)", X, X, X, X, 0.85, "§ 506.3.d",
                 "warehousing on-premises excluded (§ 506.3.d); self-storage prohibited."),
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
                note = f"{zc} ({zname}) — self_storage {ss}; {sec}: {quote[:150]}"
                await con.execute(SQL, JID, zc, zname, muni, ss, mw, li, lgc, cites, sec, conf, note)
        # catch #42 — verify rows + wealth-gated needles per town
        for muni in TOWNS:
            rows = await con.fetch(
                "SELECT zone_code, self_storage::text ss, light_industrial::text li, human_reviewed hr "
                "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
                "AND deleted_at IS NULL ORDER BY zone_code", JID, muni)
            print(f"\n{muni}: {len(rows)} rows")
            for r in rows:
                print(f"   {r['zone_code']:6} ss={r['ss']:11} li={r['li']:11} hr={r['hr']}")
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
            print(f"   wealth-gated needles = {tot}: " + ", ".join(f"{r['zoning_code']}:{r['needles']}" for r in j))
    finally:
        await con.close()


asyncio.run(main())
