"""Scottsdale AZ (jid 8e31ce3a) — Stage-4 grounding of the industrial districts. municipality='SCOTTSDALE'
(exact parcels.city, AZ UPPERCASE). Ring-precompute done (84 tracts) → 7,885 wealth&1.5ac town-wide.

Ordinance: City of Scottsdale Zoning Ordinance (Appendix B), Article XI Land Use Table 11.201.A
(Municode client 4271 / product 10075 / job 425135; fetched via api.municode.com/CodesContent, curl+UA).
District column order verified: S-R C-S C-1 C-2 C-3 C-4 S-S C-O PNC PCC PCoC **I-1 I-G** P-1 P-2.

WAREHOUSE-BY-RIGHT CONVENTION (coordinator-directed, [[feedback_warehouse_conditional_convention]]):
Table 11.201.A lists "Wholesale, warehouse and distribution" = **P** (permitted by-right) in I-1 and I-G
(also C-3/C-4), and "Light manufacturing" = P in I-1/I-G. Scottsdale has NO separate "self-storage" /
"mini-storage" / "mini-warehouse" use row → self-storage is UNNAMED, so warehouse-by-right ⇒
self_storage / mini_warehouse = **CONDITIONAL**; light_industrial = **PERMITTED**. lgc-unnamed → prohibited.
("Internalized community storage" (P in C-1..C-4/PNC/PCC/I-1) is ambiguous — likely accessory community
storage, NOT commercial self-storage — so NOT relied on to arm commercial; see C-3/C-4 flag below.)

Grounds the 7 I-1/I-G zoning_code variants present (base district governs use; PCD/ESL/HD/(C) overlays
don't change self-storage permission). Overrides the pre-existing human_reviewed=False template rows
(which had ss=prohibited). Needle = 196 wealth&1.5ac (I-1 98 + I-1 PCD 80 + I-G 10 + variants 8).

C-3/C-4 FLAG (not grounded): C-3/C-4 also permit "Wholesale, warehouse and distribution" by-right
(106 wealth&1.5ac) → the convention would extend self-storage=conditional there too. Held for coordinator
(commercial, outside the "I-1/I-G industrial" scope) — arm on greenlight.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_scottsdale_az.py
"""
import asyncio, json, asyncpg

JID = "8e31ce3a-67cd-4e62-b975-a4e799b59876"
MUNI = "SCOTTSDALE"
ORD = "City of Scottsdale Zoning Ordinance (Appendix B), Art. XI Table 11.201.A (Municode; job 425135)"
SUB = "Table 11.201.A Land Use Table (I-1 Industrial Park; I-G Light Employment/Industrial)"
Q_WHSE = ("Table 11.201.A: 'Wholesale, warehouse and distribution' = P (permitted) in the I-1 and I-G "
          "columns (also C-3, C-4).")
Q_LI = "Table 11.201.A: 'Light manufacturing' = P in I-1 and I-G (also C-4); 'Equipment storage' P in I-1."
Q_CONV = ("No 'self-storage' / 'mini-storage' / 'mini-warehouse' use row exists in Table 11.201.A → "
          "self-storage is unnamed; warehouse-permitted-by-right ⇒ self_storage/mini_warehouse CONDITIONAL "
          "(established convention). No luxury-garage-condo use listed → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "Table 11.201.A", "ordinance": ORD} for q in (Q_WHSE, Q_LI, Q_CONV)]

NOTE = ("ss/mw CONDITIONAL via warehouse-by-right convention (Table 11.201.A 'Wholesale, warehouse and "
        "distribution' = P in I-1/I-G; self-storage unnamed). li PERMITTED ('Light manufacturing' P). "
        "lgc prohibited. Overlay suffix (PCD/ESL/HD/(C)) does not change base-district self-storage permission.")

VARIANTS = ["I-1", "I-1 PCD", "I-G", "I-1 (C)", "I-1 PCD ESL (HD)", "I-1 ESL (HD)", "I-G (C)"]

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,'conditional','conditional','permitted','prohibited',$5::jsonb,$6,$7,true,'human',$8,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage='conditional', mini_warehouse='conditional',
 light_industrial='permitted', luxury_garage_condo='prohibited', citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc in VARIANTS:
            zn = ("I-1 Industrial Park" if zc.startswith("I-1") else "I-G Light Employment/Industrial") + \
                 ("" if zc in ("I-1", "I-G") else f" [{zc}]")
            await con.execute(SQL, JID, zc, zn, MUNI, json.dumps(cite()), SUB, 0.80, NOTE)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
            light_industrial::text li, human_reviewed hr FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[]) AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI, VARIANTS)
        print(f"CATCH #42 — {MUNI} I-1/I-G grounded ({len(rr)}):")
        for r in rr:
            print(f"  {r['zone_code']:20} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
