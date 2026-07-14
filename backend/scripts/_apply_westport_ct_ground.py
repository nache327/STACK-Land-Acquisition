"""Town of Westport (Westport, CT — single-town jid) — Stage-4 human verdicts.

(Distinct from the old wave-6 substrate seeder _apply_westport_ct.py — this is the grounding.)

HONEST NO-OP for self-storage. Wealthy residential/coastal town; grounds the business, office
and commercial districts against the Town of Westport Zoning Regulations (Effective April 1, 2022,
portal.ct.gov full text; districts §21-§30). #37 verbatim basis.

Each district lists its permitted PRINCIPAL uses by enumeration; a use not enumerated as a
principal use is not permitted.

Self-storage / self-service storage / mini-warehouse: the term appears NOWHERE in the Westport
regulations (grep of the full 2022 text = zero hits). The only warehousing/storage provisions are:
  - "Wholesaling and warehousing" as an ACCESSORY use (§24-2.3.4 GBD; §28-2.3 BPD; §29B-2.2 BCRR;
    §30-2.4 HDD) — accessory to a permitted principal use, not a standalone facility; and
  - §26-2.2 DDD "Warehouses in conjunction with commercial and research uses, and motels"
    (a Special-Permit, in-conjunction use — not a standalone self-storage facility).
No district permits warehousing as a stand-alone principal use, and none by-right. Under the
enumerated-use structure, self-storage is therefore PROHIBITED in every district (catch #57/#58:
no affirmative self-storage provision; the by-right-warehouse -> ss/mw-conditional convention does
NOT fire — warehousing here is accessory / special-permit-in-conjunction, never by-right principal).

Verdicts (municipality='Westport'), business/office/commercial districts:
  self_storage / mini_warehouse = PROHIBITED; light_industrial = PROHIBITED (mfg permitted only as
  accessory incidental to a retail business, §24-2.3.1); luxury_garage_condo = PROHIBITED (unnamed).

Net: ZERO self-storage needles in Westport (correct no-op).
municipality='Westport' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_westport_ct_ground.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "0a142989-e2ea-4cbf-9c07-ba72d06d5ca4"
MUNI = "Westport"
ORD = ("Town of Westport CT Zoning Regulations (Effective April 1, 2022, portal.ct.gov full text); "
       "districts §21-§30, enumerated permitted-use lists")
_Q = ('Self-storage / self-service storage / mini-warehouse appears NOWHERE in the Westport '
      'regulations. Warehousing is only an ACCESSORY use (§24-2.3.4 GBD "Wholesaling and '
      'warehousing"; likewise §28-2.3 BPD, §29B-2.2 BCRR, §30-2.4 HDD) or a Special-Permit '
      'in-conjunction use (§26-2.2 DDD "Warehouses in conjunction with commercial and research '
      'uses"). No standalone / by-right warehouse or self-storage principal use exists -> under the '
      'enumerated-use structure self-storage is prohibited (no affirmative provision).')
NAMES = {
    "GBD": "GBD General Business District", "GBD/S": "GBD/S General Business District (Saugatuck)",
    "GBD/SM": "GBD/SM General Business District (Saugatuck/Mixed)",
    "BCD": "BCD Business Center District", "BCD/H": "BCD/H Business Center District (Historic)",
    "BCRR": "BCRR Business Center Retail Residential District",
    "BPD": "BPD Business Preservation District", "RBD": "RBD Restricted Business District",
    "RORD1": "RORD #1 Restricted Office-Retail District", "RORD2": "RORD #2 Restricted Office-Retail District",
    "RORD3": "RORD #3 Restricted Office-Retail District", "RPOD": "RPOD Restricted Professional Office District",
    "HDD": "HDD Historic Design District", "DDD4": "DDD Design Development District (4)",
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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=60)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Westport" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        present = {r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout = '60s'")
        applied = 0
        for zc, zname in NAMES.items():
            if zc not in present:
                continue
            note = (f"{zc} ({zname}) — self_storage/mini_warehouse PROHIBITED (not listed; warehousing "
                    "only accessory/in-conjunction). light_industrial PROHIBITED (accessory mfg only). "
                    "luxury_garage_condo PROHIBITED (unnamed).")
            cites = json.dumps([{"ordinance": ORD, "section": "§21-§30 / §24-2.3.4 / §26-2.2", "quote": _Q}])
            await con.execute(SQL, JID, zc, zname, MUNI, "prohibited", "prohibited", "prohibited",
                              "prohibited", cites, "§21-§30 enumerated use lists", 0.87, note)
            applied += 1
        print(f"applied {applied} business/office-district rows (self-storage no-op).")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND human_reviewed AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        for r in rows:
            print(f"  {r['zone_code']:8} ss={r['ss']:11} conf={r['conf']}")
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
