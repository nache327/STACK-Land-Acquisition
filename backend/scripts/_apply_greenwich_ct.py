"""Town of Greenwich (Greenwich, CT — single-town jid) — Stage-4 verdicts.

HONEST NO-OP for self-storage. Wealthy residential town; grounds the business/commercial
districts against the Town of Greenwich Building Zone Regulations (Division 9 Use Regulations +
Business Zones Schedule of Uses, greenwichct.gov; full version April 2018 w/ later revisions).

CLOSED LIST — §6-100: "Any use not specifically listed in the following Use Groups shall be
prohibited, unless allowed under" a specific provision. #37 verbatim basis.

Self-storage / self-service storage / mini-warehouse: the term appears NOWHERE in the Greenwich
regulations (grep of Division 9 + the Business Schedule = zero hits). The only storage/warehouse
use is "Warehousing and storage" (Use Group 5 — a SPECIAL EXCEPTION use, Board of Appeals, §6-19
to §6-21), permitted only in the GB and GBO zones (Schedule cell = "E"), and "Wholesale
establishment" (E, GB/GBO). Greenwich's own Planning & Zoning FAQ states self-storage is not
permitted in Town. Under §6-100 closed list, self-storage is therefore PROHIBITED in every zone
(catch #57/#58: silence + no affirmative self-storage provision = prohibited; the by-right
warehouse->ss/mw convention does NOT fire — warehousing here is a special-exception use, not
by-right, and self-storage is a distinct customer self-service use the Town does not list).

Verdicts (municipality='Greenwich'):
  GB / GBO (General Business / General Business Office): self_storage / mini_warehouse = PROHIBITED
    (not listed; "Warehousing and storage" = Use Group 5 special-exception, a distinct logistics use).
    light_industrial = CONDITIONAL (Use Group 5 "Any business or industry not otherwise covered by
    these Use Groups" + "Warehousing and storage" — special-exception only). lgc PROHIBITED.
  CGB / CGBR / LB / LBR-1 / LBR-2 / WB / BEX-50-R (+ -HO overlay variants): self_storage /
    mini_warehouse = PROHIBITED (not listed; §6-100 closed list). light_industrial = PROHIBITED
    (only accessory ≤750 sq ft assembling/processing, footnote 1 — not a principal use). lgc PROHIBITED.

Net: ZERO self-storage needles in Greenwich (correct no-op — wealthy, strict closed-list code, no
self-storage use anywhere; Town P&Z confirms).
municipality='Greenwich' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_greenwich_ct.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "e5406ad0-4e9d-4cea-b20f-800a94d6be8a"
MUNI = "Greenwich"
ORD = ("Town of Greenwich CT Building Zone Regulations (Division 9 Use Regulations + Business Zones "
       "Schedule of Uses, greenwichct.gov, April 2018 full version w/ revisions); closed list §6-100")
_GB_Q = ('§6-100: "Any use not specifically listed in the following Use Groups shall be prohibited." '
         'Self-storage / self-service storage / mini-warehouse is listed NOWHERE. The only warehouse '
         'use is "Warehousing and storage" (Use Group 5 — Special Exception, Board of Appeals §6-19 to '
         '6-21; Schedule cell "E" in GB & GBO only), a distinct logistics use, not customer self-storage. '
         '"Any business or industry not otherwise covered by these Use Groups" is also Use Group 5 '
         '(special exception).')
_OTHER_Q = ('§6-100 closed list: self-storage / mini-warehouse not specifically listed -> prohibited. '
            'No warehousing or general-industry use is available in this zone; assembling/processing is '
            'permitted only as an accessory use <=750 sq ft (Schedule footnote 1).')

# self_storage, mini_warehouse, light_industrial, luxury_garage_condo, conf, section, quote
GB_V  = ("prohibited", "prohibited", "conditional", "prohibited", 0.88, "§6-100 / Use Group 5", _GB_Q)
OTH_V = ("prohibited", "prohibited", "prohibited", "prohibited", 0.88, "§6-100 closed list", _OTHER_Q)
NAMES = {
    "GB": "GB General Business", "GBO": "GBO General Business Office",
    "GB-HO": "GB General Business (Housing Opportunity overlay)",
    "GBO-HO": "GBO General Business Office (Housing Opportunity overlay)",
    "CGB": "CGB Central Greenwich Business", "CGB-HO": "CGB Central Greenwich Business (HO overlay)",
    "CGBR": "CGBR Central Greenwich Business Retail", "CGBR-HO": "CGBR Central Greenwich Business Retail (HO overlay)",
    "LB": "LB Local Business", "LB-HO": "LB Local Business (HO overlay)",
    "LBR-1": "LBR-1 Local Business Retail 1", "LBR-1-HO": "LBR-1 Local Business Retail 1 (HO overlay)",
    "LBR-2": "LBR-2 Local Business Retail 2", "LBR-2-HO": "LBR-2 Local Business Retail 2 (HO overlay)",
    "WB": "WB Waterfront Business", "BEX-50-R": "BEX-50-R Business Executive Office",
}
GB_ZONES = {"GB", "GBO", "GB-HO", "GBO-HO"}
VERDICTS = {}
for zc, zname in NAMES.items():
    ss, mw, li, lgc, conf, sec, quote = GB_V if zc in GB_ZONES else OTH_V
    note = (f"{zc} ({zname}) — self_storage/mini_warehouse PROHIBITED (not listed; §6-100 closed list). "
            + ("light_industrial CONDITIONAL (Use Group 5 special exception). " if zc in GB_ZONES
               else "light_industrial PROHIBITED (only accessory <=750 sq ft). ")
            + "luxury_garage_condo PROHIBITED (unnamed).")
    VERDICTS[zc] = (zname, ss, mw, li, lgc, conf, sec, quote, note)

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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=60)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Greenwich" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        # only ground zone_codes that actually appear in parcels (avoid phantom rows)
        present = {r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout = '60s'")
        applied = 0
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote, note) in VERDICTS.items():
            if zc not in present:
                continue
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf, note)
            applied += 1
        print(f"applied {applied} business-zone rows (self-storage no-op).")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND human_reviewed AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        for r in rows:
            print(f"  {r['zone_code']:10} ss={r['ss']:11} li={r['li']:11} conf={r['conf']}")
        j = await con.fetchrow(
            "SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2", JID, MUNI)
        print(f"catch #42 wealth-gated self-storage needles: {j['needles']} (expected 0 — no-op)")
    finally:
        await con.close()


asyncio.run(main())
