"""Town of Fairfield (Fairfield County, CT — county_gis jid) — Stage-4 verdicts.

HONEST NO-OP for self-storage. Grounds Fairfield's Designed Industrial (DI) +
Designed Business (CDD/DCD/NDD) districts against the Town Zoning Regulations
(Adopted/Effective 09/06/2025, town PDF). Parcels rebound via
rebind_configs/fairfield_ct.json off the MetroCOG layer (17,821 rebound).
STRICT closed-list §2.4.A: "Uses which are not specifically permitted under the
Zoning Regulations are hereby declared to be prohibited uses."

Self-storage / self-service storage / mini-warehouse: the term appears NOWHERE in
the Fairfield code (grep of the full 09/06/2025 regulations = zero hits). Under
§2.4.A closed list -> self-storage is PROHIBITED in every district (catch #57/#58:
silence + no affirmative provision = prohibited; NOT inferred conditional from the
DI "Warehousing" use, which §37 defines as receipt/storage/distribution of goods —
a distribution/logistics model, not customer self-service storage).

Verdicts (municipality='Fairfield'):
  DI (Designed Industrial, §8): self_storage / mini_warehouse = PROHIBITED (0.88,
    absent from §8.2/§8.3 -> closed list). light_industrial = PERMITTED (0.88,
    §8.2.A "The manufacture, processing or assembling of goods"; note §31 special
    permit gates new construction in Designed districts, but the USE is expressly
    permitted). luxury_garage_condo = PROHIBITED (0.85, unnamed).
  CDD / DCD / NDD (Designed Business, §6): self_storage / mini_warehouse = PROHIBITED
    (0.88, absent from §6.3 table). light_industrial = PROHIBITED (0.85, §6.3.R
    manufacturing is ACCESSORY-only / ≤1/3 floor / ≤5 HP — not a principal
    light-industrial use). luxury_garage_condo = PROHIBITED.

Net: ZERO self-storage needles in Fairfield (correct no-op — wealthy + has industrial,
but self-storage is entirely absent from a strict closed-list code). light_industrial is a
real by-right use in DI (recorded), but yields no self-storage needle.

municipality='Fairfield' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_fairfieldct_fairfield.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "66230887-aabe-4d62-aebb-856939ba77bb"
MUNI = "Fairfield"
ORD = ("Town of Fairfield CT Zoning Regulations (Effective 09/06/2025); closed-list §2.4.A "
       "(fairfieldct.org)")
_DI_Q = ('§2.4.A "Uses which are not specifically permitted ... are hereby declared to be '
         'prohibited uses." Self-storage appears nowhere in the code. §8.2.A permits by right '
         '"The manufacture, processing or assembling of goods"; §8.2.C permits "Warehousing" '
         '(defined §37 as receipt/storage/distribution of goods — not customer self-storage).')
_B_Q = ('§2.4.A closed list. Self-storage absent from the §6.3 Designed Business use table. '
        '§6.3.R manufacturing is accessory-only (≤1/3 floor area, ≤5 HP), not a principal use.')
VERDICTS = {
    "DI": ("DI Designed Industrial", "prohibited", "prohibited", "permitted", "prohibited",
           0.88, "§8.2 / §2.4.A", _DI_Q,
           "self_storage/mini_warehouse PROHIBITED (absent; strict closed-list §2.4.A; DI "
           "'Warehousing' is logistics, not self-storage). light_industrial PERMITTED (§8.2.A "
           "manufacture/processing/assembly by right; §31 special permit gates construction). "
           "luxury_garage_condo PROHIBITED (unnamed)."),
    "CDD": ("CDD Center Designed Business", "prohibited", "prohibited", "prohibited",
            "prohibited", 0.88, "§6.3 / §2.4.A", _B_Q,
            "self_storage/mini_warehouse PROHIBITED (absent). light_industrial PROHIBITED "
            "(§6.3.R accessory-only manufacturing, not principal). luxury_garage_condo PROHIBITED."),
    "DCD": ("DCD Designed Commercial", "prohibited", "prohibited", "prohibited", "prohibited",
            0.88, "§6.3 / §2.4.A", _B_Q,
            "self_storage/mini_warehouse PROHIBITED (absent). light_industrial PROHIBITED "
            "(accessory-only mfg). luxury_garage_condo PROHIBITED."),
    "NDD": ("NDD Neighborhood Designed Business", "prohibited", "prohibited", "prohibited",
            "prohibited", 0.88, "§6.3 / §2.4.A", _B_Q,
            "self_storage/mini_warehouse PROHIBITED (absent). light_industrial PROHIBITED "
            "(mfg not permitted in NDD). luxury_garage_condo PROHIBITED."),
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
        assert jn and "Fairfield County" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf,
                              f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Fairfield rows (self-storage no-op):")
        for r in rows:
            print(f"  {r['zone_code']:4} ss={r['ss']:11} li={r['li']:11} conf={r['conf']}")
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
