"""Passaic County NJ (jid 7a9ed95d…) — Stage-4 verdicts, batch 1.

Three in-ring industrial/CI towns (wealth-ring discovery-rank): Wayne, Hawthorne, Wanaque.
Atlas-bound (njtpa_atlas_082025). municipality = EXACT parcels.city (mixed-case NJ suffix).
#37 verbatim basis; #38 codes verified vs each town's ordinance; #57/#58; named beats convention.

WAYNE township — Zoning Ch. 134 (eCode360 WA0473).
  I (Industrial) §134-48.1 permitted principal uses (closed list "no land shall be used …
    except the following"): "D. Warehousing" + "E. Self-storage facilities" + "C. Industrial
    operations or uses" -> self_storage/mini_warehouse PERMITTED by-right (NAMED use), light_industrial
    PERMITTED. lgc PROHIBITED (unnamed).
  B (Business) §134-43.2 Prohibited uses names "F. Self-storage facilities" -> PROHIBITED.
  HC (Highway Commercial) §134-44.2 Prohibited uses names "F. Self-storage facilities" -> PROHIBITED.
  OR (Office & Research) §134-47.1 + OB-L (Office Building Ltd) §134-46.1: closed lists of
    offices/labs/banks/dwellings only — no warehouse/storage -> self_storage PROHIBITED, li PROHIBITED.
  MLR3D-4 (Mount Laurel Round-3 Dist 4) §134-54.8: self-storage is a permitted principal use ONLY on
    Block 3101 Lots 12/13 (AvalonBay settlement); the rest is affordable-housing residential. Cannot
    confirm the 3 bound parcels are that block -> conservative PROHIBITED + escalated (see _exceptions_C.md).

HAWTHORNE borough — Zoning Ch. 540 (eCode360 HA0182, adopted 2023).
  I-1 §540-167A(1) permitted use: "research and development, manufacturing, processing, fabricating,
    indoor warehousing and storage" by-right. Self-storage is not a NAMED use anywhere in Ch. 540, but
    "indoor warehousing and storage" is permitted by-right -> warehouse-by-right convention =>
    self_storage/mini_warehouse CONDITIONAL. light_industrial PERMITTED. lgc PROHIBITED. (I-1 prohibited
    list §540-167B = heavy-nuisance manufacturing only; does not bar storage.)
  B-1/B-2/B-3/B-3A (business/retail) + P (public): self-storage not named/permitted -> PROHIBITED.

WANAQUE borough — Zoning Ch. 114 (eCode360 WA0388).
  IR-1 §114-14A: "(1) Research and development laboratories. (2) Wholesaling, warehousing and
    distribution activities. (3) [manufacturing…]". The warehousing here is a WHOLESALE/DISTRIBUTION
    logistics activity (Berkeley-Heights warehouse-vs-wholesale rule) — NOT customer self-storage, which
    is named nowhere in Ch. 114 -> self_storage/mini_warehouse PROHIBITED (#58 closed list; convention
    does NOT fire on a wholesale/distribution use). light_industrial PERMITTED (mfg by-right). lgc PROHIBITED.
  B (Business): self-storage not permitted -> PROHIBITED.

Run: python scripts/_apply_passaic_batch1.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "7a9ed95d-df89-4864-a203-f831a987b562"
ORD_WAYNE = "Township of Wayne NJ Zoning, Ch. 134 (eCode360 WA0473, amended through 2025)"
ORD_HAW = "Borough of Hawthorne NJ Zoning, Ch. 540 (eCode360 HA0182, adopted 2023 Ord. 2313-23)"
ORD_WAN = "Borough of Wanaque NJ Zoning, Ch. 114 (eCode360 WA0388)"

# (municipality, zone_code, zone_name, ss, mw, li, lgc, conf, section, quote, ordinance)
VERDICTS = [
    # --- WAYNE township ---
    ("Wayne township", "I", "I Industrial", "permitted", "permitted", "permitted", "prohibited",
     0.93, "§134-48.1", '§134-48.1 permitted principal uses (closed list): "D. Warehousing"; '
     '"E. Self-storage facilities"; "C. Industrial operations or uses". Self-storage is a NAMED '
     'by-right use.', ORD_WAYNE),
    ("Wayne township", "B", "B Business", "prohibited", "prohibited", "prohibited", "prohibited",
     0.92, "§134-43.2", '§134-43.2 Prohibited uses: "F. Self-storage facilities" (expressly prohibited).',
     ORD_WAYNE),
    ("Wayne township", "HC", "HC Highway Commercial", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.92, "§134-44.2",
     '§134-44.2 Prohibited uses: "F. Self-storage facilities" (expressly prohibited).', ORD_WAYNE),
    ("Wayne township", "OR", "OR Office & Research", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.87, "§134-47.1", '§134-47.1 closed list ("no land shall be used … except the '
     'following"): offices, research laboratories, banks, private schools, adult day care, municipal, '
     'commercial recreation. No warehouse/storage/self-storage use.', ORD_WAYNE),
    ("Wayne township", "OB-L", "OB-L Office Building — Limited", "prohibited", "prohibited",
     "prohibited", "prohibited", 0.87, "§134-46.1", '§134-46.1 closed list: dwellings, professional '
     'offices, banks, funeral homes, adult day care, municipal. No warehouse/storage/self-storage use.',
     ORD_WAYNE),
    ("Wayne township", "MLR3D-4", "MLR3D-4 Mount Laurel Round-3 District 4", "prohibited",
     "prohibited", "prohibited", "prohibited", 0.65, "§134-54.8",
     '§134-54.8: self-storage is a permitted principal use ONLY on Block 3101 Lots 12/13 (AvalonBay '
     'settlement); remainder is affordable-housing residential. Bound parcels not confirmed as that '
     'block -> conservative prohibited (escalated).', ORD_WAYNE),
    # --- HAWTHORNE borough ---
    ("Hawthorne borough", "I-1", "I-1 Industrial", "conditional", "conditional", "permitted",
     "prohibited", 0.85, "§540-167A", '§540-167A(1) permitted use: "research and development, '
     'manufacturing, processing, fabricating, indoor warehousing and storage" by-right. Self-storage '
     'not separately named; warehouse/storage permitted by-right -> self_storage/mini_warehouse '
     'conditional (warehouse-by-right convention). §540-167B prohibited list = heavy-nuisance mfg only.',
     ORD_HAW),
    ("Hawthorne borough", "B-1", "B-1 Business", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.85, "§540 B-1", "B-1 retail/business use list; self-storage not permitted/named.",
     ORD_HAW),
    ("Hawthorne borough", "B-2", "B-2 Business", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.85, "§540 B-2", "B-2 business use list; self-storage not permitted/named.", ORD_HAW),
    ("Hawthorne borough", "B-3", "B-3 Retail Business", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.85, "§540 B-3", "B-3 retail business; self-storage not permitted/named.", ORD_HAW),
    ("Hawthorne borough", "B-3A", "B-3A Retail Business", "prohibited", "prohibited", "prohibited",
     "prohibited", 0.85, "§540 B-3A", "B-3A retail business; self-storage not permitted/named.", ORD_HAW),
    ("Hawthorne borough", "P", "P Public", "prohibited", "prohibited", "prohibited", "prohibited",
     0.85, "§540 P", "Public/institutional zone; self-storage not permitted/named.", ORD_HAW),
    # --- WANAQUE borough ---
    ("Wanaque borough", "IR-1", "IR-1 Industrial/Research", "prohibited", "prohibited", "permitted",
     "prohibited", 0.82, "§114-14A", '§114-14A permitted primary uses: "(1) Research and development '
     'laboratories. (2) Wholesaling, warehousing and distribution activities. (3) [manufacturing…]". '
     'The warehousing is a wholesale/distribution logistics use (Berkeley-Heights warehouse-vs-wholesale '
     'rule) — not customer self-storage, which is named nowhere in Ch. 114. self_storage prohibited; '
     'light_industrial permitted (mfg by-right).', ORD_WAN),
    ("Wanaque borough", "B", "B Business", "prohibited", "prohibited", "prohibited", "prohibited",
     0.85, "§114-12", "§114-12 B District permitted uses = retail/service/business; self-storage not "
     "permitted/named.", ORD_WAN),
]

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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=240)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Passaic" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}")
        # casing guard: every municipality must exist verbatim in parcels.city
        munis = sorted({v[0] for v in VERDICTS})
        cities = {r["city"] for r in await con.fetch(
            "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city = ANY($2::text[])",
            JID, munis)}
        for v in VERDICTS:
            assert v[0] in cities, f"municipality {v[0]!r} not in parcels.city"
        await con.execute("SET statement_timeout = '60s'")
        for (muni, zc, zname, ss, mw, li, lgc, conf, sec, quote, ordn) in VERDICTS:
            cites = json.dumps([{"ordinance": ordn, "section": sec, "quote": quote}])
            note = f"{muni} {zc} ({zname}) — ss={ss} mw={mw} li={li} lgc={lgc}"
            await con.execute(SQL, JID, zc, zname, muni, ss, mw, li, lgc, cites, sec, conf, note)
        print(f"applied {len(VERDICTS)} human-reviewed rows across Wayne/Hawthorne/Wanaque")
        # needle tally per town
        rows = await con.fetch(
            """SELECT p.city, m.zone_code, m.self_storage::text ss,
                   count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
                        AND prm.median_hhi>=100000) needles
               FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id
                 AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL
                 AND m.human_reviewed AND m.self_storage IN ('permitted','conditional')
               LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
               WHERE p.jurisdiction_id=$1::uuid
               GROUP BY 1,2,3 ORDER BY needles DESC""", JID)
        print("\nself-storage needle districts (wealth-gated):")
        tot = 0
        for r in rows:
            print(f"  {r['city']:<18} {r['zone_code']:<8} ss={r['ss']:<11} needles={r['needles']}")
            tot += r["needles"]
        print(f"TOTAL wealth-gated self-storage needles: {tot}")
    finally:
        await con.close()


asyncio.run(main())
