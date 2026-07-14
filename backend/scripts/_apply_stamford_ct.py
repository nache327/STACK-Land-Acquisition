"""City of Stamford (Stamford, CT — single-town jid) — Stage-4 verdicts.

Real industrial city. Grounds the industrial + relevant commercial districts against the
Stamford Zoning Regulations (full text, web version dated 08/31/2021, hosted by the Stamford
Board of Representatives). Stamford NAMES a self-storage use ("Self-Storage Facility", def.
§Definitions; use 164.1 in Appendix A - Table II Land Use Schedule) and expressly classes it as
"a low intensity industrial use" (§4.B.8 M-G text). #37 verbatim basis: grounded on the literal
Land Use Schedule cell, read by x-coordinate off the landscape Table II page (columns
C-N C-B C-L C-G CC C-I | M-L M-G).

Appendix A - Table II, use 164.1 Self-Storage Facility (verbatim row cells):
  C-N=-  C-B=-  C-L=-  C-G=B  CC=-  C-I=-  |  M-L=x  M-G=x
Legend (Appendix A NOTE): "X" = permitted (as-of-right; §7.5 large-scale review may add a
special permit for big developments); "B" = subject to Zoning Board Special Permit approval
(§9/§19); "-" = not permitted.

Verdicts (municipality='Stamford'):
  M-G General Industrial District (§4.B.8): self_storage / mini_warehouse = PERMITTED
    (Table II 164.1 = 'x' as-of-right; §4.B.9.c special-permit list does NOT include it).
    light_industrial = PERMITTED (M-G "allows the most intense industrial uses"). lgc PROHIBITED.
  M-L Light Industrial District (§4.B.9): self_storage / mini_warehouse = PERMITTED (Table II
    164.1 = 'x'; §4.B.9.b as-of-right = Appendix A Tables I & II). light_industrial = PERMITTED. lgc PROHIBITED.
  HT-D Designed High-Technology District (§9.J.3.a): self_storage / mini_warehouse = PERMITTED
    ("Industrial Uses are all uses currently permitted ... in the M-G and M-L Districts except"
    an enumerated nuisance list that does NOT include self-storage — #57 affirmative inheritance).
    light_industrial = PERMITTED. lgc PROHIBITED.
  C-G General Commercial District: self_storage / mini_warehouse = CONDITIONAL (Table II 164.1 =
    'B' = Zoning Board Special Permit). light_industrial = PROHIBITED. lgc PROHIBITED.
  IP-D Designed Industrial Park District (§9.I.3): self_storage / mini_warehouse = PROHIBITED
    (9.I.3 is a CLOSED enumerated list — labs/offices/light-product fabrication/schools; self-storage
    NOT named — #58 closed-list). light_industrial = PERMITTED (9.I.3.c fabrication/assembly of light
    products). lgc PROHIBITED.

M-D Designed Industrial District is NOT grounded here — genuine #57/#58 tension (9.H.2 permitted-use
list = labs/offices only, self-storage unnamed; but 9.H.3.d bulk standards affirmatively set FAR for
"a self-storage facility" in a 9.H.1.f M-D). Escalated to outputs/_exceptions_C.md; left as the
existing prohibited stub (5 parcels, immaterial to the needle).

Needle districts: M-G (386), M-L (118), HT-D (10) by-right; C-G (56) conditional.
municipality='Stamford' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_stamford_ct.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "9bbffb2b-2460-47be-a486-0687d795b1fb"
MUNI = "Stamford"
ORD = ("City of Stamford CT Zoning Regulations (full text, web version 08/31/2021, "
       "boardofreps.org); Appendix A - Table II Land Use Schedule, use 164.1 Self-Storage Facility")
_IND_Q = ('Appendix A - Table II, use "164.1 Self-Storage Facility" cell = "x" (permitted as-of-'
          'right) in both M-L and M-G. Appendix A NOTE: uses marked "X" are permitted. §4.B.8: "The '
          'M-G district allows the most intense industrial uses"; Self-Storage Facility def. classes '
          'it "a low intensity industrial use". §4.B.9.b: M-L as-of-right uses = Appendix A Tables I '
          '& II; the §4.B.9.c special-permit list does NOT include self-storage.')
_HT_Q = ('§9.J.3.a: "Industrial Uses. Industrial Uses are all uses currently permitted, in the same '
         'manner permitted, either as-of-right or by Special Permit in the M-G and M-L Districts '
         'except" an enumerated nuisance list (sand/gravel, auto wrecking, foundry, meat processing) '
         'that does NOT include self-storage -> self-storage is inherited by-right.')
_CG_Q = ('Appendix A - Table II, use 164.1 Self-Storage Facility cell = "B" in C-G. Appendix A NOTE: '
         '"Where such use is marked with a \'B\', it is subject to approval by the Zoning Board" '
         '(§9/§19 Special Permit).')
_IPD_Q = ('§9.I.3 permitted-use list for IP-D is closed and enumerated (research/labs; §9.I.3.b '
          'offices; §9.I.3.c non-retail sale/fabrication/assembly of cosmetic, pharmaceutical, '
          'electronic, light-plastic, optical products; schools; colleges; accessory). Self-Storage '
          'Facility is NOT among them -> prohibited by closed list. Light fabrication/assembly (9.I.3.c) '
          'is a permitted light-industrial use.')

VERDICTS = {
    "M-G": ("M-G General Industrial District", "permitted", "permitted", "permitted", "prohibited",
            0.93, "Appendix A Table II u.164.1 / §4.B.8", _IND_Q,
            "self_storage/mini_warehouse PERMITTED by-right (Table II 164.1='x'; §4.B.8 most-intense "
            "industrial). light_industrial PERMITTED. luxury_garage_condo PROHIBITED (unnamed)."),
    "M-L": ("M-L Light Industrial District", "permitted", "permitted", "permitted", "prohibited",
            0.93, "Appendix A Table II u.164.1 / §4.B.9", _IND_Q,
            "self_storage/mini_warehouse PERMITTED by-right (Table II 164.1='x'; §4.B.9.b Tables I&II; "
            "not in §4.B.9.c special-permit list). light_industrial PERMITTED. luxury_garage_condo PROHIBITED."),
    "HT-D": ("HT-D Designed High-Technology District", "permitted", "permitted", "permitted", "prohibited",
             0.85, "§9.J.3.a", _HT_Q,
             "self_storage/mini_warehouse PERMITTED (§9.J.3.a inherits all M-G/M-L industrial uses; "
             "self-storage not in the excepted nuisance list). light_industrial PERMITTED. lgc PROHIBITED."),
    "C-G": ("C-G General Commercial District", "conditional", "conditional", "prohibited", "prohibited",
            0.90, "Appendix A Table II u.164.1 = 'B'", _CG_Q,
            "self_storage/mini_warehouse CONDITIONAL (Table II 164.1='B' = Zoning Board Special Permit, "
            "§9/§19). light_industrial PROHIBITED. luxury_garage_condo PROHIBITED."),
    "IP-D": ("IP-D Designed Industrial Park District", "prohibited", "prohibited", "permitted", "prohibited",
             0.85, "§9.I.3", _IPD_Q,
             "self_storage/mini_warehouse PROHIBITED (§9.I.3 closed enumerated list; self-storage unnamed). "
             "light_industrial PERMITTED (§9.I.3.c light-product fabrication/assembly). lgc PROHIBITED."),
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
        assert jn and "Stamford" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf,
                              f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND human_reviewed AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} human-reviewed Stamford rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} conf={r['conf']}")
        j = await con.fetchrow(
            "SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles, count(*) total "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2", JID, MUNI)
        print(f"catch #42 wealth-gated self-storage needles: {j['needles']} "
              f"(of {j['total']} ss permitted/conditional parcels)")
    finally:
        await con.close()


asyncio.run(main())
