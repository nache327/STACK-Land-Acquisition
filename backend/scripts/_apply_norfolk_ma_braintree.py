"""Apply human-verified zone_use_matrix verdicts — BRAINTREE (Braintree MA Ch.135 Table of Principal Uses 135 Att.2 Supp 6 Feb 2026 (ecode360.com/14707492); PR parcellogic/norfolk-ma-braintree-verdicts. HELD: legacy assessor codes B/A/IND/GBD/RES/HBD/BUS/CL2/COM/I (not current ordinance districts; needs zoning-layer rebind)).

Generated 2026-07-08 from the applied production rows (paste-session apply;
this file is the committed record of that apply and is idempotently re-runnable).
Discipline: muni-scoped (catch #33), verbatim-quote basis (catch #37),
human-UPSERT via asyncpg (catch #29), verify-and-print after apply (catch #42).
"""
import asyncio, json, asyncpg

JID = "6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5"
MUNI = "BRAINTREE"

VERDICTS = [{'zone_code': 'C',
  'zone_name': 'Braintree C',
  'self_storage': 'conditional',
  'mini_warehouse': 'conditional',
  'light_industrial': 'permitted',
  'luxury_garage_condo': 'conditional',
  'citations': [{'quote': '"Modular Storage: N N N N N SP SP N N" (cols RA RB RC C123 GB HB C OSC '
                          'BWLD); "Warehouse: N N N N N SP Y N N"',
                 'section': '135 Att.2',
                 'ordinance': 'Braintree Ch. 135 Zoning, Table of Principal Uses 135 Att.2 (Supp 6 '
                              "Feb 2026; closed table: 'Any uses not listed herein are deemed not "
                              "allowed') https://ecode360.com/14707492"}],
  'cited_subsection': '135 Att.2',
  'confidence': 0.95,
  'notes': 'C: ss conditional — Modular Storage NAMED SP in C (self-storage family); Warehouse Y; '
           'Light Manufacturing Y -> light_industrial permitted. garage_condo conditional 0.75 '
           "('Garage, Nonresidential' = Y in C; Parking Facility is a separate row)."},
 {'zone_code': 'OSC',
  'zone_name': 'Braintree OSC',
  'self_storage': 'prohibited',
  'mini_warehouse': 'prohibited',
  'light_industrial': 'prohibited',
  'luxury_garage_condo': 'prohibited',
  'citations': [{'quote': '"Modular Storage: N N N N N SP SP N N" (cols RA RB RC C123 GB HB C OSC '
                          'BWLD); "Warehouse: N N N N N SP Y N N"',
                 'section': '135 Att.2',
                 'ordinance': 'Braintree Ch. 135 Zoning, Table of Principal Uses 135 Att.2 (Supp 6 '
                              "Feb 2026; closed table: 'Any uses not listed herein are deemed not "
                              "allowed') https://ecode360.com/14707492"}],
  'cited_subsection': '135 Att.2',
  'confidence': 0.95,
  'notes': 'OSC: ss prohibited — named N / closed table (any use not listed deemed not allowed).'}]

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
