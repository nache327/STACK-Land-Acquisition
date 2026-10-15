"""Haverford Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 182 Zoning, Articles III (O-1/O-2), IV (C-1..C-5), V (OL/LIN) pasted 2026-07-07
(LIN accessory subsection truncated — the B(1)(a-q) principal-use list is complete).

LIN (§ 182-503B(1)(e)) — "Indoor storage buildings, warehouses and distribution
  centers and packaging and crating." PERMITTED BY RIGHT. Storage-buildings-by-right
  is stronger than plain warehouse, but Haverford does NOT name mini-warehouse/
  self-storage the way Middletown (§ 275-76A(9)) / Marple (§ 300-45) do when meant —
  so per the warehouse=>conditional convention: self_storage/mini_warehouse
  CONDITIONAL (0.85), reinforced by the (q) same-general-character SE catch-all.
  Upgrade to permitted on a Board/solicitor confirmation that 'indoor storage
  buildings' includes public self-storage. light_industrial PERMITTED (0.95).
  luxury_garage_condo conditional (0.70, same basis). 6 pool parcels >=1.5ac.

O-1 (§ 182-302) / O-2 (§ 182-303, O-1+residential by reference) — offices only ->
  PROHIBITED (0.92).
C-1 (§ 182-402) / C-2 (§ 182-403) / C-3 (§ 182-404) / C-5 (§ 182-406) — closed
  commercial lists; storage language is ACCESSORY-only (C-2 B(2)(a)[1]; C-5 D(2)
  outdoor merchandise storage as special reg) -> PROHIBITED (0.92). Kills C-3 (2) pool.
C-4 (§ 182-405) — adds auto uses + "wholesale business establishments" by right and
  SE "express, trucking or hauling stations"; neither is a warehouse/storage USE
  (consistent w/ Concord C-2 wholesale ruling) -> PROHIBITED (0.90).
OL (§ 182-502) — labs/offices; accessory enclosed storage only -> PROHIBITED (0.92).

HELD (not pasted): INS, ROS, SRD, R-1..R-9.

Muni-specific municipality='Haverford Township' (catch #33 family); human-UPSERT
(catch #29). Run: python scripts/_apply_delaware_pa_haverford.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Haverford Township"
ORD = "Haverford Township Code Ch. 182 Zoning (eCode360 https://ecode360.com/12186966)"

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "LIN": ("conditional", "conditional", "permitted", "conditional", 0.85,
            "§ 182-503B(1)(e)",
            "Indoor storage buildings, warehouses and distribution centers and "
            "packaging and crating.",
            "storage buildings + warehouses BY RIGHT; self-storage/mini-warehouse not "
            "named (unlike Middletown/Marple when meant) -> warehouse=>conditional "
            "convention; (q) same-general-character SE reinforces. Upgrade to "
            "permitted on Board/solicitor confirmation."),
}
for z, sec, quote, extra, conf in (
    ("O-1", "§ 182-302B(1)", "land, buildings or premises may be used or occupied by "
     "only one of the following", "offices/banks/studios only", 0.92),
    ("O-2", "§ 182-303B(1)", "Any use permitted in an O-1 Office District ... Any "
     "residential use permitted in R-4 Districts", "O-1 + residential by reference", 0.92),
    ("C-1", "§ 182-402B(1)", "may be used or occupied by only one of the following",
     "O-1 uses + restaurants + hotel; no storage use", 0.92),
    ("C-2", "§ 182-403B(1)", "may be used or occupied by only one of the following",
     "neighborhood retail; storage is ACCESSORY-only (B(2)(a)[1] 'Storage within a "
     "completely enclosed building in conjunction with a permitted use')", 0.92),
    ("C-3", "§ 182-404B(1)", "land, buildings or premises shall be used by right for "
     "one or more of the following", "general retail closed list; no storage use", 0.92),
    ("C-4", "§ 182-405B(1)", "Any use permitted by right in a C-3 General Commercial "
     "District ... Wholesale business establishments",
     "wholesale business establishment is not a warehouse/storage USE (consistent "
     "with Concord C-2 ruling); SE trucking stations likewise", 0.90),
    ("C-5", "§ 182-406B(1)", "used by right only for a planned community shopping center",
     "shopping-center district; D(2) outdoor merchandise storage is a special "
     "regulation for accessory storage, not a storage use", 0.92),
    ("OL", "§ 182-502B(1)", "shall be used by right for one or more of the following",
     "labs + offices; accessory enclosed storage only (B(2)(c))", 0.92),
):
    VERDICTS[z] = ("prohibited", "prohibited", "prohibited", "prohibited", conf, sec, quote, extra)

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn == "Delaware County, PA", jn
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, mw, li, lgc, conf, section, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": section, "quote": quote}])
            await con.execute(
                SQL, JID, zc, f"Haverford Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Haverford Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec'][:30]}")
    finally:
        await con.close()


asyncio.run(main())
