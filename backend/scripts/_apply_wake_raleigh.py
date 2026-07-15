"""Wake County NC — Raleigh (North Raleigh wealth center) — Stage-4 verdicts, batch 1.

Atlas... no — Wake muni bind (wake_muni_gis) applied Raleigh's UDO zoning (field ZONING) via
_bind_wake_muni_zoning.py. Ring metrics already complete (435k dt=10). municipality='Raleigh'.

Grounds the Raleigh UDO mixed-use base districts that ALLOW Self-Service Storage. #37 verbatim:
Raleigh UDO Sec. 6.5.5 "Self-Service Storage" (use category incl. "Warehouse, self-service" and
"Mini-warehouse") gives district-specific use standards for the CX-, DX-, and IX- districts; Table
6.1.4 designates Self-Service Storage a LIMITED USE (L) in CX-, DX-, IX- (permitted by-right subject
to the Sec. 6.5.5 use standards — min 2 ac, fully-enclosed building) and a Permitted Use (P) in IH-
(Heavy Industrial). "L" (administrative, no Board-of-Adjustment hearing) -> self_storage/mini_warehouse
= PERMITTED in our schema.

Verdicts (municipality='Raleigh'), applied to every distinct IX-*/CX-*/DX-*/IH-* zoning_code present
(height/frontage/-CU suffixes don't change the base-district use permission):
  IX-* / IH-* (Industrial Mixed / Heavy Industrial): ss/mw PERMITTED, light_industrial PERMITTED.
  CX-* / DX-* (Commercial Mixed / Downtown Mixed): ss/mw PERMITTED, light_industrial PROHIBITED.
  luxury_garage_condo PROHIBITED (unnamed).

In-ring wealth-gated self-storage needles concentrate in CX-3-PL / IX-3-PL / CX-3-PK (North Raleigh).
Cary + Apex (planned-development-dominated wealth rings; discrete commercial/industrial districts need
clean use-table extraction) are escalated to outputs/_exceptions_C.md — NOT ground here.

Run: python scripts/_apply_wake_raleigh.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "b05b7317-b412-492c-a56c-433d447d17bf"
MUNI = "Raleigh"
ORD = ("City of Raleigh Unified Development Ordinance (UDO), Sec. 6.5.5 Self-Service Storage + "
       "Table 6.1.4 Allowed Principal Use Table (udo.raleighnc.gov)")
_IX_Q = ('UDO Sec. 6.5.5 "Self-Service Storage" (incl. "Warehouse, self-service" and "Mini-warehouse") '
         'gives use standards for the IX- (Industrial Mixed-Use) district; Table 6.1.4 designates it a '
         'LIMITED USE (L) in IX- (by-right subject to the 6.5.5 standards: min 2 ac, fully-enclosed '
         'building). IX- is an industrial mixed-use district -> light_industrial permitted.')
_CX_Q = ('UDO Sec. 6.5.5 "Self-Service Storage" gives use standards for the CX- (Commercial Mixed-Use) / '
         'DX- (Downtown Mixed-Use) districts; Table 6.1.4 designates it a LIMITED USE (L) there (min 2 ac, '
         'fully-enclosed single building, internal access). Commercial/downtown mixed-use -> '
         'light_industrial prohibited.')

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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=180)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Wake" in jn, f"unexpected jurisdiction: {jn!r}"
        assert MUNI in {r["city"] for r in await con.fetch(
            "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        codes = [r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 "
            "AND (zoning_code LIKE 'IX%' OR zoning_code LIKE 'IH%' OR zoning_code LIKE 'CX%' "
            "     OR zoning_code LIKE 'DX%') ORDER BY 1", JID, MUNI)]
        await con.execute("SET statement_timeout='180s'")
        n = 0
        for zc in codes:
            is_ind = zc.startswith("IX") or zc.startswith("IH")
            li = "permitted" if is_ind else "prohibited"
            quote = _IX_Q if is_ind else _CX_Q
            fam = "Industrial Mixed-Use" if zc.startswith("IX") else ("Heavy Industrial" if zc.startswith("IH")
                  else ("Commercial Mixed-Use" if zc.startswith("CX") else "Downtown Mixed-Use"))
            cites = json.dumps([{"ordinance": ORD, "section": "Sec. 6.5.5 / Table 6.1.4", "quote": quote}])
            note = (f"Raleigh {zc} ({fam}) — self_storage/mini_warehouse PERMITTED (UDO 6.5.5 Limited Use), "
                    f"light_industrial {li}, lgc prohibited")
            await con.execute(SQL, JID, zc, f"{zc} {fam}", MUNI, "permitted", "permitted", li,
                              "prohibited", cites, "Sec. 6.5.5 / Table 6.1.4", 0.88, note)
            n += 1
        print(f"applied {n} Raleigh IX/CX/DX/IH rows (self_storage permitted)")
        j = await con.fetchrow(
            "SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles, count(*) ss_parcels "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2", JID, MUNI)
        print(f"Raleigh wealth-gated self-storage needles: {j['needles']} (of {j['ss_parcels']} ss parcels)")
    finally:
        await con.close()


asyncio.run(main())
