"""Wilmington MA — Stage-4 FULL close (2026-07-08). Zero held cells. GI/HI/LI(=LI/O).

li=permitted GROUNDED (Table 1 §3.6.4 named by-right). ss/mw=prohibited GROUNDED
(§3.1 closed-list + Warehouse §3.6.1 reshipment-def + no SS use/overlay anywhere).
lgc=prohibited GROUNDED (ledger #58 reconcile: garage-condo=leased dead storage,
fits neither Light Industrial §3.6.4 nor Parking Facility §3.5.17 -> §3.1 prohibits).
Armed self-storage/garage-condo = 0. 269 parcels light-industrial-permitted (GI 198/
HI 67/LI 4). 2023 bylaw.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped
(catch #33), verbatim-quote basis (catch #37), verify-and-print after apply (catch #42).
The DB already matches these rows (applied in PR #458); re-running proves idempotency.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_wilmington.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "WILMINGTON"

ZONE_NAMES = {'GI': 'General Industrial', 'HI': 'Highway Industrial',
              'LI': 'Light Industrial (LI/O)'}
CITED_SUBSECTION = "Table 1 §3.6"
NOTES = ("[TIER-1 human-verified 2026-07-08 Wilmington Stage-4 CLOSED] li=permitted GROUNDED "
         "(Table 1 §3.6.4 Light Industrial, named by-right use). ss/mw=PROHIBITED GROUNDED — three "
         "converging: (1) §3.1 closed-list ('prohibit any use not specifically permitted herein'); "
         "(2) Warehouse §3.6.1 = sorting-for-reshipment distribution, excludes leased dead storage; "
         "(3) no self-storage use/definition/overlay anywhere (full-bylaw+§6.7 scan; §6.7=Adult Use). "
         "lgc=PROHIBITED GROUNDED (reconciled from inferred-conditional, ledger #58): "
         "garage-condo/hobby-vehicle = leased dead storage; fits NO named use — not Light Industrial "
         "§3.6.4 (warehouse/distribution/assembly/high-tech/printing 'and other like uses' = active "
         "industry) nor Parking Facility §3.5.17 ('commercial parking lot or parking garage' = "
         "transient commercial parking) → prohibited on identical §3.1 basis as ss. Arming loss: "
         "GI 198/HI 67/LI 4 lgc conditional->prohibited.")

WILMINGTON_ROWS = [{'zone_code': 'GI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]},
 {'zone_code': 'HI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]},
 {'zone_code': 'LI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]}]

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,$8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
 light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
 citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
 human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for v in WILMINGTON_ROWS:
            await con.execute(SQL, JID, v["zone_code"], ZONE_NAMES[v["zone_code"]], MUNI,
                              v["ss"], v["mw"], v["li"], v["lgc"], json.dumps(v["citations"]),
                              CITED_SUBSECTION, v["confidence"], NOTES)
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
