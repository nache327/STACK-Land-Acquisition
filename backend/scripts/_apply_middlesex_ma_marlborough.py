"""Apply human-verified zone_use_matrix verdicts — MARLBOROUGH (Marlborough MA Ch.650 Table 650 Att.1 / 650-17 (ecode360.com/9216860); PR parcellogic/middlesex-ma-marlborough-verdicts).

Generated 2026-07-08 from the applied production rows (paste-session apply;
this file is the committed record of that apply and is idempotently re-runnable).
Discipline: muni-scoped (catch #33), verbatim-quote basis (catch #37),
human-UPSERT via asyncpg (catch #29), verify-and-print after apply (catch #42).
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"
MUNI = "MARLBOROUGH"

VERDICTS = [{'zone_code': 'A1',
  'zone_name': 'Marlborough A1',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'A1: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'A2',
  'zone_name': 'Marlborough A2',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'A2: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'A3',
  'zone_name': 'Marlborough A3',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'A3: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'B',
  'zone_name': 'Marlborough B',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17',
  'confidence': 0.95,
  'notes': 'B: ss conditional — §650-17 — self-service storage facility = SP (special permit, City '
           'Council) in B; industrial uses N; closed table §650-16B.'},
 {'zone_code': 'CA',
  'zone_name': 'Marlborough CA',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17',
  'confidence': 0.95,
  'notes': 'CA: ss conditional — §650-17 — SP in CA; industrial uses N; closed table.'},
 {'zone_code': 'I',
  'zone_name': 'Marlborough I',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'permitted',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-18A(36),(37)',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-18A(36),(37)',
  'confidence': 0.95,
  'notes': 'I: ss prohibited — §650-17 + §650-18A(36),(37) — self-storage NAMED N in I (explicit N '
           'beats Cresskill inference). light mfg Y; (37) general warehousing Y in I. garage_condo '
           "PERMITTED via 'hobby vehicle storage' named in (36), Y in I — (36) screening condition "
           'applies.'},
 {'zone_code': 'LI',
  'zone_name': 'Marlborough LI',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'permitted',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-18A(36)',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-18A(36)',
  'confidence': 0.95,
  'notes': 'LI: ss prohibited — §650-17 + §650-18A(36) — self-storage NAMED N in LI. light mfg Y; '
           "warehousing limited to the (36) product list. garage_condo PERMITTED via 'hobby "
           'vehicle storage\' in (36), Y in LI — screening condition. §650-18A(36): "Manufacturing '
           'and/or warehousing of footwear, precision instruments, tool and die, dental, medical '
           'and optical equipment, electrical or electronic instruments, hobby vehicle storage, '
           'biomedical or biotechnology products... provided truck loading and parking areas are '
           'effectively screened..."'},
 {'zone_code': 'MV',
  'zone_name': 'Marlborough MV',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'MV: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'NB',
  'zone_name': 'Marlborough NB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'NB: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'RB',
  'zone_name': 'Marlborough RB',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'RB: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'RC',
  'zone_name': 'Marlborough RC',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'RC: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'},
 {'zone_code': 'RR',
  'zone_name': 'Marlborough RR',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': 'Self-service storage facility: N N N N N N N N SP SP N N N N N (cols RR '
                          'A-1 A-2 A-3 RB RC RCR NB B CA LI I MV Wayside DLB)',
                 'section': '§650-17 + §650-16B',
                 'ordinance': 'Marlborough Code Ch. 650 Zoning, Table of Uses 650 Att.1/§650-17 '
                              '(Supp 15 Sep 2025; legend §650-16, closed table §650-16B) '
                              'https://ecode360.com/9216860'}],
  'cited_subsection': '§650-17 + §650-16B',
  'confidence': 0.95,
  'notes': 'RR: ss prohibited — §650-17 + §650-16B — named N across residential/village columns; '
           '§650-16B: all uses not noted are deemed prohibited. MV = Marlborough Village '
           '§650-18A(31)(a)[6].'}]

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
