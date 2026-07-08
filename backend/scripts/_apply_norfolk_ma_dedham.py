"""Apply human-verified zone_use_matrix verdicts — DEDHAM (Dedham MA Ch.280 Table 1, 280 Att.1 Supp 4 Nov 2023 (via dedham-ma.gov zoning bylaw); PR parcellogic/norfolk-ma-dedham-verdicts. LM->LMA alias per 280-2.1A; spot-check: 180 Rustcraft Rd / 300 Providence Hwy / 110 Elm St (Rustcraft industrial corridor = LMA). HELD: legacy codes B/G/A/R/000/L/R1).

Regenerated 2026-07-08 post-rebind (LM re-keyed to LMA; RDO row added w/ fn24 condition; eyeball-verified) (paste-session apply;
this file is the committed record of that apply and is idempotently re-runnable).
Discipline: muni-scoped (catch #33), verbatim-quote basis (catch #37),
human-UPSERT via asyncpg (catch #29), verify-and-print after apply (catch #42).
"""
import asyncio, json, asyncpg

JID = "6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5"
MUNI = "DEDHAM"

VERDICTS = [{'zone_code': 'CB',
  'zone_name': 'Central Business',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.2',
  'confidence': 0.92,
  'notes': 'Commercial storage NO, Warehouse NO, Limited manufacturing NO in CB; closed list '
           '280-3.1A.'},
 {'zone_code': 'GB',
  'zone_name': 'General Business',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.2',
  'confidence': 0.92,
  'notes': 'Commercial storage NO, Warehouse NO, Limited manufacturing NO in GB; closed list '
           '280-3.1A.'},
 {'zone_code': 'HB',
  'zone_name': 'Highway Business',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'conditional',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.2',
  'confidence': 0.92,
  'notes': "ss prohibited: 'Commercial storage' explicit NO in HB (named-N beats inference); "
           'Warehouse only SP -> no Cresskill upgrade (convention: by-right only) + no upgrade '
           'over specific NO per 280-3.1D. li conditional: Limited manufacturing SP (Board of '
           'Appeals).'},
 {'zone_code': 'LB',
  'zone_name': 'Local Business',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.2',
  'confidence': 0.92,
  'notes': 'Commercial storage NO, Warehouse NO, Limited manufacturing NO in LB; closed list '
           '280-3.1A.'},
 {'zone_code': 'LM',
  'zone_name': 'Limited Manufacturing (LMA alias)',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'conditional',
  'luxury_garage_condo': 'conditional',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.2',
  'confidence': 0.85,
  'notes': 'ALIAS LM->LMA per 280-2.1A (no bare LM district; official abbrev = LMA Limited '
           "Manufacturing); zoning-map spot-check logged. ss/mw conditional 0.85: 'Commercial "
           "storage' YES by right (most specific designation per 280-3.1D; generic storage not "
           'named self-storage -> Cresskill-class); Warehouse NO except fn27 existing >=150k sf '
           'bldg. li conditional 0.95-class: Limited manufacturing SP — AUTHORITY: Board of '
           'Appeals (280-3.1C). lgc conditional 0.70 via Commercial-storage-YES.'},
 {'zone_code': 'LMB',
  'zone_name': 'Limited Manufacturing Type B',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'conditional',
  'citations': [{'quote': 'F.2 "Commercial storage": YES in LMA, YES in LMB; F.3 "Warehouse": '
                          'NO(fn27, existing >=150k sf bldg only) in LMA, YES in LMB, SP in HB; '
                          'H.2 "Limited manufacturing": SP in LMA, YES in LMB, SP in HB. Column '
                          'alignment footnote-anchored (fn18/fn24 fix RDO col; fn27 fixes LMA).',
                 'section': '280 Att.1 F.2/F.3/H.1/H.2',
                 'ordinance': 'Dedham Zoning Bylaw Ch. 280, Table 1 Principal Use Regulations (280 '
                              "Att.1, Supp 4 Nov 2023; closed-list per 280-3.1A: 'no land shall be "
                              'used...other than for one or more of the uses specifically '
                              "permitted herein'; legend 280-3.1C: YES=right, SP=Special Permit "
                              'BoA, PB=Special Permit PB)'}],
  'cited_subsection': '280 Att.1 F.2/F.3/H.1/H.2',
  'confidence': 0.85,
  'notes': "ss/mw conditional 0.85: 'Commercial storage' YES + 'Warehouse' YES by right (generic "
           'storage named, self-storage unnamed -> Cresskill-class). li PERMITTED 0.95: Limited '
           'manufacturing YES + Manufacturing YES by right. lgc conditional 0.70 via '
           'Commercial-storage/Warehouse YES.'}]

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,$8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
 light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
 citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
 human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for v in VERDICTS:
            await con.execute(SQL, JID, v["zone_code"], v["zone_name"], MUNI,
                              v["self_storage"], v["mini_warehouse"], v["light_industrial"],
                              v["luxury_garage_condo"], json.dumps(v["citations"]),
                              v["cited_subsection"], v["confidence"], v["notes"])
        rows = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
            light_industrial::text li, luxury_garage_condo::text lgc, confidence, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply:")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
