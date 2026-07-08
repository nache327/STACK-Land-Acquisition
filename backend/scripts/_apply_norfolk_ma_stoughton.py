"""Apply human-verified zone_use_matrix verdicts — STOUGHTON (Stoughton MA 200 Att.2 Supp 18 Jun 2026 (ecode360.com/32690363); PR parcellogic/norfolk-ma-stoughton-verdicts. HELD: C,F,T (not in pasted table)).

Generated 2026-07-08 from the applied production rows (paste-session apply;
this file is the committed record of that apply and is idempotently re-runnable).
Discipline: muni-scoped (catch #33), verbatim-quote basis (catch #37),
human-UPSERT via asyncpg (catch #29), verify-and-print after apply (catch #42).
"""
import asyncio, json, asyncpg

JID = "6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5"
MUNI = "STOUGHTON"

VERDICTS = [{'zone_code': 'GB',
  'zone_name': 'Stoughton GB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'E.13 Open storage of raw materials... = BA in GB; warehouse E.22 = N',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.9,
  'notes': 'GB: ss prohibited — 200 Att.2 — raw-materials open storage (BA) distinguished from '
           'self-storage; no storage use otherwise.'},
 {'zone_code': 'HB',
  'zone_name': 'Stoughton HB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'E.22 Warehouse or distribution plant = N in HB; E.12 "Wholesale trade '
                          'and distribution including... accessory storage" = Y; E.8 truck '
                          'terminal w/ freight warehousing = BA',
                 'section': '200 Att.2 E.22/E.12/E.8 + E.4',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2 E.22/E.12/E.8 + E.4',
  'confidence': 0.88,
  'notes': 'HB: ss prohibited — 200 Att.2 E.22/E.12/E.8 + E.4 — wholesale trade =/= storage use '
           '(Concord C-2 precedent); freight-terminal BA is not self-storage. E.4 manufacturing Y '
           '-> light_industrial permitted.'},
 {'zone_code': 'I',
  'zone_name': 'Stoughton I',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'conditional',
  'citations': [{'quote': 'E.22 "Warehouse or distribution plant: N N N N N N N N Y Y" (cols R-M '
                          'R-U R-C R-B R-A GB NB HB I I2)',
                 'section': '200 Att.2 E.22 + E.4',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2 E.22 + E.4',
  'confidence': 0.85,
  'notes': 'I: ss conditional — 200 Att.2 E.22 + E.4 — warehouse/distribution BY RIGHT in I; '
           'self-storage UNNAMED in the entire table -> warehouse=>conditional convention '
           '(Cresskill). E.4 manufacturing Y -> light_industrial permitted. E.13 open storage Y '
           '(screened). garage_condo conditional (0.70 basis: warehouse family + E.13; unnamed).'},
 {'zone_code': 'NB',
  'zone_name': 'Stoughton NB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'warehouse/storage/manufacturing rows all N in NB',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'NB: ss prohibited — 200 Att.2 — closed table silence.'},
 {'zone_code': 'RA',
  'zone_name': 'Stoughton RA',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'all industrial/storage rows N in residential columns (R-M R-U R-C R-B '
                          'R-A; DB codes unhyphenated)',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'RA: residential column, closed table; ss prohibited'},
 {'zone_code': 'RB',
  'zone_name': 'Stoughton RB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'all industrial/storage rows N in residential columns (R-M R-U R-C R-B '
                          'R-A; DB codes unhyphenated)',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'RB: residential column, closed table; ss prohibited'},
 {'zone_code': 'RC',
  'zone_name': 'Stoughton RC',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'all industrial/storage rows N in residential columns (R-M R-U R-C R-B '
                          'R-A; DB codes unhyphenated)',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'RC: residential column, closed table; ss prohibited'},
 {'zone_code': 'RM',
  'zone_name': 'Stoughton RM',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'all industrial/storage rows N in residential columns (R-M R-U R-C R-B '
                          'R-A; DB codes unhyphenated)',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'RM: residential column, closed table; ss prohibited'},
 {'zone_code': 'RU',
  'zone_name': 'Stoughton RU',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'all industrial/storage rows N in residential columns (R-M R-U R-C R-B '
                          'R-A; DB codes unhyphenated)',
                 'section': '200 Att.2',
                 'ordinance': 'Stoughton Zoning Bylaw, Table of Use Regulations 200 Att.2 (Supp 18 '
                              'Jun 2026) https://ecode360.com/32690363'}],
  'cited_subsection': '200 Att.2',
  'confidence': 0.92,
  'notes': 'RU: residential column, closed table; ss prohibited'}]

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
