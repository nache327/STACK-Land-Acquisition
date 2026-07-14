"""Boxborough MA — Stage-4 FULL close (2026-07-13). 7 bylaw districts (Article 3).

TAIL. NEEDLE MUNI: "Self-storage facility" is permitted BY-RIGHT in the Industrial-Commercial (IC)
district only. Rebind (MAPC layer 2) confirmed assessor code "C" -> IC spatially (C->IC:62, gates
a/b/d PASS, layer vocab = AR/B/B1/IC/OP/R1/TC exactly matching bylaw Article 3).

Grounding — Boxborough Zoning Bylaw (boxborough-ma.gov DocumentCenter/View/1918, 2025), Article 3
(Establishment of Districts) + Table 4.1.3.d (Business/Industrial Uses). Column order AR R1 B B1 OP TC IC.
  Legend: Y=permitted; ZBA=special permit (Zoning Board of Appeals); N=prohibited.
  ss/mw PERMITTED (by-right) in IC only: Table 4.1.3.d "Self-storage facility" = Y in IC, N in every
    other district; "Warehouse" = Y9 in IC only.
  li PERMITTED in B, B1, OP, IC: "Light Manufacturing" = Y3,11 (by-right) in B/B1, Y3 in OP/IC;
    "Manufacturing" = Y3,11 in B1, Y3 in IC; "Wholesale operations" = Y9 in B/B1/IC, ZBA9 in OP.
    CONDITIONAL in R1: "Light Manufacturing" = ZBA. Prohibited in AR, TC.
  lgc PROHIBITED everywhere: no named vehicle garage-condo use; "Self-storage facility" is goods
    storage and "Repair garage/auto detailing garage" is an auto-service use, neither a luxury owned/
    leased garage-condo; comprehensive table (Wilmington ledger #58 + Woburn convention).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), wrong-family disambiguation via spatial rebind (#38), verify-and-print (#42),
catch #56 alignment via pdfplumber table extraction.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_boxborough.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "BOXBOROUGH"
CITED_SUBSECTION = "Table 4.1.3.d Business/Industrial Uses; Article 3"
ORD = ("Boxborough Zoning Bylaw (boxborough-ma.gov DocumentCenter/View/1918, 2025), Article 3 + "
       "Table 4.1.3.d Business/Industrial Uses")

Q_SS = ("Table 4.1.3.d 'Self-storage facility': Y (permitted) in IC; N in AR/R1/B/B1/OP/TC. 'Warehouse': "
        "Y9 in IC; N elsewhere. Legend: Y=permitted; ZBA=special permit; N=prohibited.")
Q_LI = ("Table 4.1.3.d 'Light Manufacturing' = Y3,11 in B/B1, Y3 in OP/IC, ZBA3,10 in R1; 'Manufacturing' "
        "= Y3,11 in B1, Y3 in IC; 'Wholesale operations' = Y9 in B/B1/IC, ZBA9 in OP.")
Q_LGC = ("No named vehicle garage-condo principal use; 'Self-storage facility' is goods storage and "
         "'Repair garage/auto detailing garage' is an auto-service use -> lgc prohibited in every "
         "district (comprehensive Table 4.1.3.d).")


def cite(*qs):
    return [{"quote": q, "section": "Table 4.1.3.d", "ordinance": ORD} for q in qs]


N_IC = ("ss/mw PERMITTED (GROUNDED): Table 4.1.3.d 'Self-storage facility' = Y (by-right) + 'Warehouse' = "
        "Y9, only in IC. li PERMITTED: Light/Manufacturing + Wholesale = Y (by-right). lgc PROHIBITED: no "
        "named garage-condo use.")
N_LIPERM = ("ss/mw PROHIBITED: 'Self-storage facility' = N here (by-right only in IC). li PERMITTED "
            "(GROUNDED): 'Light Manufacturing' / 'Wholesale operations' = Y (by-right). lgc PROHIBITED.")
N_OP = ("ss/mw PROHIBITED: 'Self-storage facility' = N in Office Park. li PERMITTED (GROUNDED): 'Light "
        "Manufacturing' = Y3 (by-right); 'Wholesale operations' = ZBA. lgc PROHIBITED.")
N_R1 = ("ss/mw PROHIBITED: 'Self-storage facility' = N. li CONDITIONAL: 'Light Manufacturing' = ZBA "
        "(special permit). lgc PROHIBITED.")
N_PROHIB = ("All prohibited. Self-storage, Warehouse, Light Manufacturing, Wholesale = N in this "
            "district; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("AR", "Agricultural-Residential", "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R1", "Residential R1",           "prohibited","prohibited","conditional","prohibited",0.82,N_R1),
    ("B",  "Business",                 "prohibited","prohibited","permitted","prohibited",0.86,N_LIPERM),
    ("B1", "Business B1",              "prohibited","prohibited","permitted","prohibited",0.86,N_LIPERM),
    ("OP", "Office Park",              "prohibited","prohibited","permitted","prohibited",0.84,N_OP),
    ("TC", "Town Center",              "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("IC", "Industrial-Commercial",    "permitted","permitted","permitted","prohibited",0.90,N_IC),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
    "confidence": conf, "notes": note,
} for zc, zn, ss, mw, li, lgc, conf, note in _R]

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
        for v in VERDICTS:
            await con.execute(SQL, JID, v["zone_code"], v["zone_name"], MUNI,
                              v["self_storage"], v["mini_warehouse"], v["light_industrial"],
                              v["luxury_garage_condo"], json.dumps(v["citations"]),
                              v["cited_subsection"], v["confidence"], v["notes"])
        rows = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
            light_industrial::text li, luxury_garage_condo::text lgc, confidence, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
