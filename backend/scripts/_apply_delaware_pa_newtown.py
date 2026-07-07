"""Newtown Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 172 Zoning, Articles XV (O), XVI (C-1), XVII (C-2), XVIII (I), XIX (SU-1),
XX (SU-2) pasted 2026-07-07 (current through Ord. 2026-01).

I (§ 172-82) — closed list; no plain warehouse, BUT (E) "Distribution plants,
  parcel delivery, cold storage plants and bottling plants" BY RIGHT (the
  warehousing/distribution family) + (J) "Uses approved by the Board of Supervisors
  of the same general character as any of the above, subject to conditional use
  approval" — self-storage is of the same general character as distribution/cold-
  storage -> self_storage/mini_warehouse CONDITIONAL (0.85). light_industrial
  PERMITTED (0.95, manufacturing by right at (B)). garage_condo conditional (0.70,
  same J basis). 3 pool parcels >=1.5ac.

C-2 (§ 172-74) — closed list; the 2024 LOGISTICS CENTER amendment lists "storage"
  only as a flex-logistics component, conditional, and only "as part of a lifestyle
  village" (§ 172-74L + § 172-72 definition) — NOT public self-storage; accessory
  (N) enclosed storage in conjunction with a permitted use only -> PROHIBITED
  (0.88, discounted for the logistics-center adjacency). Kills the 2 C-2 pool parcels.

SU-1 (§ 172-88) — the county's most storage-hostile text: labs conditional only
  with "no storage of any commodity or substance whatsoever"; offices only
  "provided that no commercial storage, exchange, sales or delivery of merchandise
  is conducted"; § 172-89C(6)/(7) conditional criteria ban outdoor storage and
  visible indoor storage -> PROHIBITED (0.95). SU-2 (§ 172-99/100): SU-1 by
  reference + nurseries/car-sales/golf/convalescent/service-office/schools ->
  PROHIBITED (0.92).

O (§ 172-65) — service office building only -> PROHIBITED (0.95).
C-1 (§ 172-70) — retail/service closed list -> PROHIBITED (0.92).

HELD (not pasted): A, AO, CCRC, R-*.

Muni-specific municipality='Newtown Township' (catch #33 family; catch #38: this is
Newtown TOWNSHIP Delaware County — not Newtown Borough/Township Bucks County).
human-UPSERT (catch #29). Run: python scripts/_apply_delaware_pa_newtown.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Newtown Township"
ORD = "Newtown Township Code Ch. 172 Zoning (eCode360 https://ecode360.com/15082757)"

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "I": ("conditional", "conditional", "permitted", "conditional", 0.85,
          "§ 172-82E + § 172-82J",
          "Distribution plants, parcel delivery, cold storage plants and bottling "
          "plants. / Uses approved by the Board of Supervisors of the same general "
          "character as any of the above, subject to conditional use approval.",
          "distribution/cold-storage family by right; self-storage unnamed -> "
          "conditional via the (J) same-general-character conditional-use catch-all. "
          "Manufacturing by right at (B) -> light_industrial permitted."),
    "C-2": ("prohibited", "prohibited", "prohibited", "prohibited", 0.88,
            "§ 172-74 + § 172-72",
            "An integrated building system and supporting facilities may be created, "
            "occupied or used for the following purposes and no other purpose ... "
            "LOGISTICS CENTER: Flex space for any combination of three or more of the "
            "following uses: office, receiving, storage, assembly, packaging, delivery, "
            "automation and other logistics services.",
            "closed list; 'storage' appears only as a logistics-center flex component, "
            "conditional, and only as part of a lifestyle village — NOT public "
            "self-storage; accessory (N) enclosed storage only."),
    "SU-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.95,
             "§ 172-88B(1)-(2)",
             "provided that there is no commercial production and no storage of any "
             "commodity or substance whatsoever ... provided that no commercial "
             "storage, exchange, sales or delivery of merchandise is conducted",
             "buffer district, expressly storage-hostile; § 172-89C(6)/(7) conditional "
             "criteria also ban outdoor storage and visible indoor storage."),
    "SU-2": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
             "§ 172-99B(1) + § 172-100",
             "Any use permitted in SU-1 Special Use Districts.",
             "SU-1 by reference (storage-hostile) + nurseries/car-sales/golf/"
             "convalescent/service-office/schools/restaurant; no storage use."),
    "O": ("prohibited", "prohibited", "prohibited", "prohibited", 0.95,
          "§ 172-65",
          "A building may be erected or used and a lot may be used or occupied for "
          "the following purposes and no other: A. Service office building.",
          "single-use district (service office building only)."),
    "C-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 172-70",
            "A building may be erected or used and a lot may be used or occupied for "
            "any of the following purposes and no other",
            "retail/personal-service/office closed list; no storage use."),
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
                SQL, JID, zc, f"Newtown Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote[:180]}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Newtown Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec'][:32]}")
    finally:
        await con.close()


asyncio.run(main())
