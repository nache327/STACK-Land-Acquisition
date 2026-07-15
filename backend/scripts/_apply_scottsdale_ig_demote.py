"""Scottsdale AZ [8e31ce3a] — DEMOTE self-storage in the I-G district (audit remediation 2026-07-15).

Adversarial verdict spot-audit (backend/outputs/_verdict_audit_2026_07_15.md) found the stored I-G verdict
OVER-PERMITS. Scottsdale's self-storage use is the NAMED use "Internalized community storage" (Appendix B
Zoning Ordinance, Art. XI Land Use Table Table §11.201.A). Verbatim table read (Municode, Playwright):

  "Internalized community storage": C-1=P C-2=P C-3=P C-4=P PNC=P PCC=P I-1=P  I-G = (BLANK / not permitted)
  "Wholesale, warehouse and distribution": C-3=P C-4=P I-1=P I-G=P

I.e. general warehouse/distribution IS permitted in I-G, but the NAMED self-storage use is deliberately
omitted from I-G. Art. III Definitions:
  "Internalized community storage is an establishment that offers storage in an enclosed building, with access
   to storage units only from the interior of the building. The use may include a dwelling unit/office for
   on-site supervision, but may not include outdoor storage."

Named-use exclusion beats the warehouse-by-right convention (#37 verbatim, #58 closed-list, named-beats-
convention). -> self_storage + mini_warehouse PROHIBITED in I-G. luxury_garage_condo -> prohibited (lgc-unnamed;
never outrank a prohibited self_storage sibling / #58 gate). light_industrial stays PERMITTED (general
warehouse/distribution IS permitted in I-G per the "Wholesale, warehouse and distribution" row).

Scope: ONLY the I-G variants (I-G, I-G (C)). Leaves I-1 / C-3 / C-4 untouched (correctly armed; those cells
are P for "Internalized community storage"). Muni-scoped (municipality='SCOTTSDALE'), human_reviewed=true,
idempotent. SELECT-verified before/after.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_scottsdale_ig_demote.py
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402

JID = "8e31ce3a-67cd-4e62-b975-a4e799b59876"  # Scottsdale, AZ
MUNI = "SCOTTSDALE"
ZONES = ["I-G", "I-G (C)"]

_CITE = ('Appendix B Zoning Ordinance, Art. XI Land Use Table §11.201.A: row "Internalized community storage" '
         '(= self-storage/miniwarehouse per Art. III def.: "storage in an enclosed building, with access to '
         'storage units only from the interior of the building ... may not include outdoor storage") is BLANK '
         '(not permitted) in I-G, though "Wholesale, warehouse and distribution" IS P in I-G. Named-use '
         'exclusion beats warehouse convention -> self_storage PROHIBITED in I-G.')

UPDATE = """
UPDATE zone_use_matrix
   SET self_storage='prohibited'::use_permission_enum,
       mini_warehouse='prohibited'::use_permission_enum,
       luxury_garage_condo='prohibited'::use_permission_enum,
       light_industrial='permitted'::use_permission_enum,
       citations=$4::jsonb, cited_subsection=$5, confidence=0.85,
       human_reviewed=true, classification_source='human', notes=$6, updated_at=now()
 WHERE jurisdiction_id=$1::uuid AND municipality=$2 AND zone_code=$3 AND deleted_at IS NULL
"""


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        print("=== BEFORE ===")
        for r in await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, luxury_garage_condo::text lgc, "
            "light_industrial::text li FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND zone_code=ANY($3) AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI, ZONES):
            print(f"  {r['zone_code']:10} ss={r['ss']:11} mw={r['mw']:11} lgc={r['lgc']:11} li={r['li']}")
        for zc in ZONES:
            cites = json.dumps([{
                "ordinance": "City of Scottsdale, Appendix B Zoning Ordinance",
                "section": "Art. XI Land Use Table §11.201.A + Art. III Definitions",
                "basis": f'self_storage=prohibited in {zc}: "Internalized community storage" blank in I-G',
            }])
            note = f'{zc} (I-G Light Employment/Industrial): self_storage prohibited. {_CITE}'
            status = await con.execute(UPDATE, JID, MUNI, zc, cites, _CITE, note)
            print(f"  updated {zc}: {status}")
        print("=== AFTER ===")
        for r in await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, luxury_garage_condo::text lgc, "
            "light_industrial::text li, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1::uuid AND municipality=$2 AND zone_code=ANY($3) AND deleted_at IS NULL "
            "ORDER BY zone_code", JID, MUNI, ZONES):
            print(f"  {r['zone_code']:10} ss={r['ss']:11} mw={r['mw']:11} lgc={r['lgc']:11} li={r['li']:11} "
                  f"conf={r['confidence']} hr={r['hr']}")
        # sanity: confirm I-1/C-3/C-4 untouched
        print("=== untouched (must stay conditional) ===")
        for r in await con.fetch(
            "SELECT zone_code, self_storage::text ss FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND municipality=$2 AND zone_code IN ('I-1','C-3','C-4') AND deleted_at IS NULL ORDER BY zone_code",
            JID, MUNI):
            print(f"  {r['zone_code']:10} ss={r['ss']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
