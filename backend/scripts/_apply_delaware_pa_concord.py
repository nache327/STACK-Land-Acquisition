"""Concord Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 210 Zoning, Articles XIII (C-1) / XIV (C-2) / XV (M/I) / XVII (LI), pasted 2026-07-07.

C-2 (§ 210-127) — CLOSED LIST: "may be erected or used and a lot may be used or occupied
  for any of the following uses and no other". No self-storage / mini-warehouse / warehouse
  in uses-by-right (A), special exception (C), or conditional (D). Only storage language is
  ACCESSORY: § 210-127B(2)(a) "Storage within a completely enclosed building in conjunction
  with a permitted use" — accessory-only, does NOT trigger the warehouse=>conditional
  convention. -> self_storage PROHIBITED (0.92). Kills both listed C-2 armed parcels
  (5.5ac/$3.3M, 1.7ac/$5.995M) — correct outcome.

C-1 (§ 210-119) — closed list ("...and no other"), no storage/warehouse -> PROHIBITED (0.92).
M/I (§ 210-135) — "for any of the purposes set forth in this section and for no other",
  municipal/institutional only -> PROHIBITED (0.92).

LI (§ 210-152) — § 210-152A(15) uses by right: "Warehouse: wholesale, storage or
  distribution." Warehouse-storage PERMITTED BY RIGHT; self-storage unnamed -> the
  warehouse=>conditional convention (Cresskill) -> self_storage/mini_warehouse CONDITIONAL
  (0.85). light_industrial PERMITTED (0.95, the district's by-right core, § 210-151A).
  luxury_garage_condo CONDITIONAL (0.75, same warehouse-storage-by-right basis; unnamed).
  NOTE: paste truncated mid-§ 210-152B(7); if the LI tail names self-storage explicitly,
  upgrade conditional->permitted on a follow-up paste. Conditional is the safe reading.

HELD (not in paste): PBP, PIP (bound districts, no >=1.5ac pool parcels), R-* residential
(silence rule applies but not pasted — bootstrap heuristic prohibited stands un-humaned).

Muni-specific municipality='Concord Township' (catch #33 family — never county-wide);
human-UPSERT (catch #29). Run: python scripts/_apply_delaware_pa_concord.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Concord Township"
ORD = "Concord Township Code Ch. 210 Zoning (eCode360 https://ecode360.com/10947599)"

_CLOSED = (
    "closed-list use regulations; no self-storage/mini-warehouse/warehouse in uses by "
    "right, special exception, or conditional; accessory-only storage does not create a use"
)

# zone -> (self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
#          confidence, section, verbatim_quote, note)
VERDICTS = {
    "C-2": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 210-127",
            "A building or unified group of buildings may be erected or used and a lot may "
            "be used or occupied for any of the following uses and no other",
            f"{_CLOSED}. Accessory storage only: § 210-127B(2)(a) 'Storage within a "
            "completely enclosed building in conjunction with a permitted use'."),
    "C-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 210-119",
            "A building may be erected or used, and a lot may be used or occupied for any "
            "one or combination of the following uses and no other",
            _CLOSED),
    "M/I": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 210-135",
            "A building may be erected, altered or used, and a lot or premises may be "
            "used, for any of the purposes set forth in this section and for no other",
            "municipal/institutional uses only"),
    "LI": ("conditional", "conditional", "permitted", "conditional", 0.85,
           "§ 210-152A(15)",
           "Warehouse: wholesale, storage or distribution.",
           "warehouse-storage permitted by right; self-storage unnamed -> "
           "warehouse=>conditional convention (Cresskill). light_industrial = the "
           "district's by-right core (§ 210-151A). Paste truncated mid-§ 210-152B(7): "
           "upgrade conditional->permitted if the LI tail names self-storage."),
}

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
                SQL, JID, zc, f"Concord Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec, left(notes, 90) note "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Concord Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec']}")
    finally:
        await con.close()


asyncio.run(main())
