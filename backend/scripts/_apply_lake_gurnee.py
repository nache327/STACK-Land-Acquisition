"""Village of Gurnee (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds the Gurnee municipal industrial/commercial districts against the Village
of Gurnee Zoning Ordinance, Article 8, **Table 8-1 Use Matrix** (town PDF,
zoningdistrictusematrix_zotable-8-1.pdf; Use Standard Sec. 8.2.6), fetched
2026-07-09. Column alignment verified against the 18-district header
(R-1..R-6, C-1..C-6, O-1, O-2, I-1, I-2, I-3, P). Parcels rebound to real codes
first via rebind_configs/gurnee.json (INC -> district; 11,581 rebound).

Table 8-1 storage/industrial rows (verbatim, P=permitted / S=special use / blank=prohibited):
  "Self-Storage Facility"                              C-3 P   I-1 P      (Sec. 8.2.6)
  "Self-Storage Facility - Principal Use is Outdoor    C-3 S   I-1 S
     Storage"                                          I-2 P   I-3 P      (Sec. 8.2.6)
  "Industrial - Light"                                 I-1 P   I-2 P  I-3 P (Sec. 8.2.6)
  "Warehouse"                                          C-3 S  O-1 S O-2 S  I-1 P I-2 P I-3 P

Verdicts (municipality='GURNEE'; ground, don't inflate):
  C-3 Heavy Commercial:
    self_storage / mini_warehouse = PERMITTED (0.92) — "Self-Storage Facility" P in C-3.
    light_industrial = PROHIBITED (0.85) — "Industrial - Light" is blank (not allowed) in C-3.
    luxury_garage_condo = CONDITIONAL (0.65) — unlisted; analog to permitted self-storage.
  I-1 Restricted Industrial:
    self_storage / mini_warehouse = PERMITTED (0.92) — "Self-Storage Facility" P in I-1.
    light_industrial = PERMITTED (0.92) — "Industrial - Light" P in I-1.
    luxury_garage_condo = CONDITIONAL (0.65) — unlisted.
  I-2 General / I-3 Intensive Industrial:
    self_storage / mini_warehouse = CONDITIONAL (0.75) — the standard/indoor
      "Self-Storage Facility" is NOT listed for I-2/I-3 (blank); ONLY the
      "Principal Use is Outdoor Storage" variant is P there. So a standard indoor
      self-storage building has no by-right path in I-2/I-3 (outdoor-principal or
      special/PUD only). Conditional is the honest reading (catch #58: don't infer
      by-right permitted from an unlisted indoor use).
    light_industrial = PERMITTED (0.92) — "Industrial - Light" P in I-2 and I-3.
    luxury_garage_condo = CONDITIONAL (0.65) — unlisted.

catch #58 closed-list sweep: Table 8-1 is a permissive use matrix; a use is allowed in a
district only where marked P/S. Every PERMITTED verdict rests on an explicit "P"; the two
unlisted/indoor-unlisted uses (luxury_garage_condo everywhere; self-storage in I-2/I-3) are
held at CONDITIONAL, never inferred to by-right permitted.

municipality='GURNEE' (catch #33 — muni-scoped, never county-wide). human-UPSERT (catch #29),
verbatim citations, human_reviewed=true. Run: python scripts/_apply_lake_gurnee.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "10d01284-829b-4b03-b416-54bc452b8e70"  # Lake County, IL
MUNI = "GURNEE"
ORD = ("Village of Gurnee Zoning Ordinance, Article 8, Table 8-1 Use Matrix "
       "(https://www.gurnee.il.us/docs/default-source/planning/"
       "zoningdistrictusematrix_zotable-8-1.pdf)")

# zone -> (zone_name, self_storage, mini_warehouse, light_industrial,
#          luxury_garage_condo, confidence, quote, note)
VERDICTS = {
    "C-3": (
        "C-3 Heavy Commercial", "permitted", "permitted", "prohibited", "conditional", 0.92,
        'Table 8-1 Use Matrix: "Self-Storage Facility" = "P" (permitted) in the C-3 column '
        "(Use Standard Sec. 8.2.6).",
        "self_storage/mini_warehouse permitted by right (Self-Storage Facility P in C-3). "
        "light_industrial PROHIBITED: 'Industrial - Light' is blank (not allowed) in C-3. "
        "luxury_garage_condo CONDITIONAL: unlisted, analog to permitted self-storage."),
    "I-1": (
        "I-1 Restricted Industrial", "permitted", "permitted", "permitted", "conditional", 0.92,
        'Table 8-1 Use Matrix: "Self-Storage Facility" = "P" and "Industrial - Light" = "P" '
        "in the I-1 column (Use Standard Sec. 8.2.6).",
        "self_storage/mini_warehouse + light_industrial permitted by right in I-1. "
        "luxury_garage_condo CONDITIONAL: unlisted, analog to permitted self-storage."),
    "I-2": (
        "I-2 General Industrial", "conditional", "conditional", "permitted", "conditional", 0.75,
        'Table 8-1 Use Matrix: "Industrial - Light" = "P" in I-2; the standard "Self-Storage '
        'Facility" row is blank for I-2 (only "Self-Storage Facility - Principal Use is Outdoor '
        'Storage" = "P" in I-2).',
        "light_industrial permitted by right (Industrial - Light P in I-2). self_storage/"
        "mini_warehouse CONDITIONAL: standard/indoor self-storage NOT listed for I-2 (only the "
        "outdoor-principal variant is P) -> no by-right indoor path (catch #58). "
        "luxury_garage_condo CONDITIONAL: unlisted."),
    "I-3": (
        "I-3 Intensive Industrial", "conditional", "conditional", "permitted", "conditional", 0.75,
        'Table 8-1 Use Matrix: "Industrial - Light" = "P" in I-3; the standard "Self-Storage '
        'Facility" row is blank for I-3 (only "Self-Storage Facility - Principal Use is Outdoor '
        'Storage" = "P" in I-3).',
        "light_industrial permitted by right (Industrial - Light P in I-3). self_storage/"
        "mini_warehouse CONDITIONAL: standard/indoor self-storage NOT listed for I-3 (only the "
        "outdoor-principal variant is P) -> no by-right indoor path (catch #58). "
        "luxury_garage_condo CONDITIONAL: unlisted."),
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
        assert jn and "Lake" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, ss, mw, li, lgc, conf, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": "Table 8-1 / Sec. 8.2.6",
                                 "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites,
                              "Art. 8 Table 8-1", conf, f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr, classification_source cs "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"\napplied {len(rows)} GURNEE rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']} src={r['cs']}")
        # catch #42: confirm rebound parcels join these rows
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15 "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 "
            "GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("\ncatch #42 — rebound parcels joining a human GURNEE verdict:")
        for r in j:
            print(f"  {r['zoning_code']:5} parcels={r['n']:>5}  >=1.5ac={r['ge15']:>4}")
    finally:
        await con.close()


asyncio.run(main())
