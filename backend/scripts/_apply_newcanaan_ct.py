"""Town of New Canaan (New Canaan, CT — single-town jid) — Stage-4 verdicts.

HONEST NO-OP for self-storage. Estate-residential + small "Village District" business town
(Greenwich/Westport pattern). Grounds every zone against the New Canaan Zoning Regulations
(eCode360 NE0075, Amended Effective December 17, 2021). #37 verbatim basis.

Zone structure: Article 3 Residence Zones, Article 4 Business Zones (all "Village District":
Retail A/B, Business A/B/C/D), Article 5 Special Zones (Apartment, Multi-Family, Open Space,
Waveny). THERE IS NO INDUSTRIAL ZONE.

Letter codes A–Q are the Town GIS zoning-layer's `Code` field (hostingdata3.tighebond.com
NewCanaanDynamic/MapServer layer 89), decoded to the ordinance `ZONING` name (below). #38 layer
check: the codes+geometry were verified against that authoritative Code->ZONING legend — note
'I' here = Business A ("Business & Retail: BA"), NOT Institutional.

Self-storage / self-service storage / mini-warehouse: appears NOWHERE in the code as a permitted
use (whole-text: 0 hits for self-storage/mini-warehouse; "warehous" appears exactly ONCE, in a
Business-B PARKING computation — §6.x "any use (other than warehousing) which has more than 25%
of its gross floor area in ... storage facilities" — a dimensional/parking standard, NOT a use
grant; dimensional-mention rule). The Business-B use list (§4.5) and the Retail A/B, Business A/C
lists (§4.2/4.4/4.6) grant retail/office/service/restaurant/auto/inn/supermarket/theater uses only
— no warehouse or self-storage use. "storage facilities" in §5.8 is an accessory use serving
multi-family residents, not a self-storage facility. Under New Canaan's enumerated Village-District
use lists, self-storage is PROHIBITED in every zone (catch #57/#58: no affirmative provision;
the by-right-warehouse convention does NOT fire — there is no by-right warehouse use anywhere).

Verdicts (municipality='New Canaan'), ALL zones: self_storage / mini_warehouse = PROHIBITED;
light_industrial = PROHIBITED (no industrial zone; only accessory craftsperson/artisan work);
luxury_garage_condo = PROHIBITED (unnamed).

Net: ZERO self-storage needles (correct no-op — purest wealth zone, no self-storage-permitting district).
municipality='New Canaan' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_newcanaan_ct.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "2580f226-70f4-4c7d-982f-3cbd2b1d7b5b"
MUNI = "New Canaan"
ORD = ("Town of New Canaan CT Zoning Regulations (eCode360 NE0075, Amended Effective Dec 17, 2021); "
       "Article 4 Business Zones use lists; GIS Code->ZONING legend (Tighe & Bond NewCanaanDynamic L89)")
# letter Code -> ordinance ZONING name
ZONES = {
    "A": "1 Acre Residence Zone", "B": "1/2 Acre Residence Zone", "C": "1/3 Acre Residence Zone",
    "D": "2 Acre Residence Zone", "E": "4 Acre Residence Zone", "F": "A Residence Zone",
    "G": "Apartment Zone", "H": "B Residence Zone",
    "I": "Business A Zone (Village District)", "J": "Business B Zone (Village District)",
    "K": "Business C Zone (Village District)", "L": "Retail A Zone (Village District)",
    "M": "Retail B Zone (Village District)", "O": "Multi-Family Zone",
    "P": "Open Space Zone", "Q": "Waveny Zone",
}
BUSINESS = {"I", "J", "K", "L", "M"}
_RES_Q = ('Residential/open-space zone (Article 3 / Article 5). Self-storage / warehousing is not a '
          'permitted use; the code names no self-storage use anywhere. Prohibited (no affirmative provision).')
_BUS_Q = ('Village-District business/retail zone (Article 4). The use lists (§4.2-§4.7) grant '
          'retail/office/service/restaurant/auto/inn/supermarket/theater uses only. Self-storage / '
          'self-service storage / mini-warehouse is named NOWHERE; "warehous" appears once, in the '
          'Business-B parking computation ("any use (other than warehousing) ... storage facilities") '
          '— a dimensional/parking standard, not a use grant. Prohibited (#57/#58).')

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
        assert jn and "New Canaan" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        present = {r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout = '60s'")
        applied = 0
        for zc, zname in ZONES.items():
            if zc not in present:
                continue
            is_bus = zc in BUSINESS
            quote = _BUS_Q if is_bus else _RES_Q
            sec = "§4.2-§4.7 use lists" if is_bus else "Art.3/Art.5 (no self-storage use)"
            note = (f"{zc}={zname} — self_storage/mini_warehouse PROHIBITED (no self-storage use in code; "
                    + ("Village-District retail use list, warehousing only a parking-formula mention). "
                       if is_bus else "residential/open-space zone). ")
                    + "light_industrial PROHIBITED (no industrial zone). luxury_garage_condo PROHIBITED.")
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, "prohibited", "prohibited", "prohibited",
                              "prohibited", cites, sec, 0.90, note)
            applied += 1
        print(f"applied {applied} zone rows (self-storage no-op).")
        rows = await con.fetch(
            "SELECT zone_code, zone_name, self_storage::text ss, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND human_reviewed AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        for r in rows:
            print(f"  {r['zone_code']:2} {r['zone_name']:34} ss={r['ss']:11} conf={r['conf']}")
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
