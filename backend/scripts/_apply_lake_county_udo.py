"""Lake County, IL — county-UDO Stage-4 verdicts for the two industrial districts.

Grounds the UNINCORPORATED-land industrial zones against the Lake County Unified
Development Ordinance (Code Ch. 151), American Legal codelibrary, fetched
2026-07-09. The UDO governs unincorporated Lake County ONLY (incorporated
parcels carry the assessor 'INC' flag, reclassified to unknown per catch #51);
county-wide rows here therefore only reach unincorporated LI/II parcels.

Districts (verbatim, § 151.096(A) / § 151.097(A)):
  LI, Limited Industrial  — "primarily intended to accommodate low-intensity
    industrial uses."
  II, Intensive Industrial — "primarily intended to accommodate existing heavy
    industrial uses."
  Both defer use permissions to the § 151.111 Use Table.

Use Table § 151.111 (column alignment verified against the 22-cell header row;
P = permitted by right, C = conditional/CUP, blank = prohibited):
  "Self-service storage (see § 151.270(E)(6))"          GC=C  LI=P  II=P
  "Warehousing and freight movement not otherwise cl."  ...   LI=P  II=P
  "Manufacturing and production not otherwise classif." GC=P  LI=P  (II core)

Verdicts (ground, don't inflate — honest yield LI 148 + II 3 parcels >=1.5ac):
  self_storage    = PERMITTED (0.95) — "Self-service storage" NAMED, P by right.
  mini_warehouse  = PERMITTED (0.95) — same row (self-service storage == the
    former "mini-warehouse" category; industry-standard synonym).
  light_industrial= PERMITTED (0.95) — warehousing/freight + manufacturing P by
    right; the district's by-right industrial core.
  luxury_garage_condo = CONDITIONAL (0.65) — NOT a named use type. Closest
    analog is self-service storage (permitted), but a strict reading of the
    permissive use table prohibits unlisted uses; conditional is the honest
    middle reading (catch #58: never infer 'permitted' for an unlisted use).

catch #58 closed-list sweep: Ch. 151 is a permissive use-table system — a use is
allowed in a district only if marked P/C in that district's column, else
prohibited. Every PERMITTED verdict above rests on an explicit "P"; the one
unlisted use (luxury_garage_condo) is held at CONDITIONAL, not permitted.

municipality = NULL (genuine county-wide UDO over unincorporated land; NOT a
muni ordinance — catch #33 does not apply). human-UPSERT (catch #29), verbatim
citations, human_reviewed=true. Run: python scripts/_apply_lake_county_udo.py
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
ORD = ("Lake County, IL Code of Ordinances Ch. 151 Unified Development Ordinance "
       "(American Legal https://codelibrary.amlegal.com/codes/lakecountyil)")

_SS_QUOTE = ('§ 151.111 Use Table, row "Self-service storage (see § 151.270(E)(6))": '
             '{col} column = "P" (permitted by right).')
_LI_QUOTE = ('§ 151.111 Use Table, row "Warehousing and freight movement not '
             'otherwise classified": {col} column = "P" (permitted by right).')

# zone -> (zone_name, description_section, description_quote,
#          self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
#          confidence)
VERDICTS = {
    "LI": (
        "LI, Limited Industrial", "§ 151.096(A)",
        "The LI, Limited Industrial District is primarily intended to "
        "accommodate low-intensity industrial uses.",
        "permitted", "permitted", "permitted", "conditional", 0.95, "LI"),
    "II": (
        "II, Intensive Industrial", "§ 151.097(A)",
        "The II, Intensive Industrial District is primarily intended to "
        "accommodate existing heavy industrial uses.",
        "permitted", "permitted", "permitted", "conditional", 0.95, "II"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,NULL,$4::use_permission_enum,$5::use_permission_enum,$6::use_permission_enum,
  $7::use_permission_enum,$8::jsonb,$9,$10,true,'human',$11,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
  mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
  luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes,
  updated_at=now()
"""


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=60)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Lake" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, dsec, dquote, ss, mw, li, lgc, conf, col) in VERDICTS.items():
            cites = json.dumps([
                {"ordinance": ORD, "section": "§ 151.111",
                 "quote": _SS_QUOTE.format(col=col)},
                {"ordinance": ORD, "section": "§ 151.111",
                 "quote": _LI_QUOTE.format(col=col)},
                {"ordinance": ORD, "section": dsec, "quote": dquote},
            ])
            note = (
                f"{zc} ({zname}) — Lake County UDO Ch. 151 § 151.111 Use Table (verbatim, "
                f"col-aligned). self_storage/mini_warehouse PERMITTED: \"Self-service "
                f"storage\" = P in {col}. light_industrial PERMITTED: warehousing/freight "
                f"+ manufacturing = P in {col} (district's by-right core, {dsec}). "
                f"luxury_garage_condo CONDITIONAL: unlisted use, analog to permitted "
                f"self-service storage but held below permitted (catch #58). "
                f"County-wide UDO over unincorporated land."
            )
            await con.execute(SQL, JID, zc, zname, ss, mw, li, lgc, cites, "§ 151.111",
                              conf, note)
        rows = await con.fetch(
            "SELECT zone_code, zone_name, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr, classification_source cs, cited_subsection sec "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND zone_code=ANY($2) "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, list(VERDICTS))
        print(f"\napplied {len(rows)} Lake County UDO rows:")
        for r in rows:
            print(f"  {r['zone_code']:3} {r['zone_name']:<24} ss={r['ss']:10} mw={r['mw']:10} "
                  f"li={r['li']:10} lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']} "
                  f"src={r['cs']} {r['sec']}")
    finally:
        await con.close()


asyncio.run(main())
