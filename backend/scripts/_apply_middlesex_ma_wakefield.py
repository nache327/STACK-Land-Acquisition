"""Wakefield MA — Stage-4 FULL close (2026-07-13). Zero held cells. 8 base districts.

TAIL. NEEDLE MUNI: "Self-storage facility" is a named use permitted BY-RIGHT in Light Industrial
(LI) and Industrial (I) (and by special permit in Business).

No rebind: Wakefield parcels carry the bylaw district codes (SSR/SR/GR/NB/LB/B/LI/I).

Grounding — Town of Wakefield Zoning Bylaw Ch. 190 (eCode360 WA1512), Appendix A Table of Use
Regulations (190 Attachment 1):
  Legend: Y=permitted; BA=special permit (Board of Appeals); N=prohibited. Comprehensive per-cell
    table (closed by construction); self-storage is a NAMED use -> grounded directly.
  ss/mw PERMITTED (by-right) in LI, I: Appendix A row 7 "Self-storage facility (also see § 190-53,
    SSFOD)" = Y in LI + I; BA (special permit) in B (Business); N in SSR/SR/GR/NB/LB.
  li PERMITTED in LI, I: row 1 "Light manufacturing" = Y (by-right) in LI + I; row 6 "Wholesale or
    warehouse establishment" = Y in LI + I. CONDITIONAL in B (row 2 light-mfg-with-onsite-sales = Y
    but general light mfg N; wholesale/warehouse = BA) and NB/LB (light-mfg-with-sales / research =
    BA). Prohibited in SSR/SR/GR.
  lgc PROHIBITED everywhere: "Self-storage facility" is defined as rented space for temporary storage
    of business/personal ITEMS (goods self-storage), not a luxury vehicle garage-condo; no named
    vehicle-storage/garage-condo use; closed table (Wilmington ledger #58 + Woburn convention).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via pdfplumber table extraction.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_wakefield.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "WAKEFIELD"
CITED_SUBSECTION = "Appendix A Table of Use Regs rows 7/1/6 (190 Att.1)"
ORD = ("Town of Wakefield Zoning Bylaw Ch. 190 (eCode360 WA1512), Appendix A Table of Use "
       "Regulations (190 Attachment 1)")

Q_SS = ("Appendix A row 7 'Self-storage facility (also see § 190-53, SSFOD)': Y (by-right) in LI and I; "
        "BA (special permit, Board of Appeals) in B; N in SSR/SR/GR/NB/LB. Legend: Y=permitted; "
        "BA=special permit; N=prohibited.")
Q_LI = ("Appendix A row 1 'Light manufacturing' = Y (by-right) in LI + I; row 2 'Light manufacturing, "
        "with onsite sales' = Y in B, BA in NB; row 6 'Wholesale or warehouse establishment' = Y in "
        "LI + I, BA in B; row 9 'Research or testing laboratory' = BA in LB/B/LI, Y in I.")
Q_LGC = ("'Self-storage facility' is defined as rented space for temporary storage of business/personal "
         "ITEMS (goods), not a vehicle garage-condo; no named vehicle-storage / garage-condo principal "
         "use -> lgc prohibited in every district (closed table).")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 190 App. A", "ordinance": ORD} for q in qs]


N_IND = ("ss/mw PERMITTED (GROUNDED): Appendix A row 7 'Self-storage facility' = Y (by-right) here. li "
         "PERMITTED (GROUNDED): row 1 Light manufacturing + row 6 Wholesale/warehouse = Y (by-right). "
         "lgc PROHIBITED: self-storage is goods storage, not a vehicle garage-condo; no named "
         "garage-condo use.")
N_B = ("ss/mw CONDITIONAL (GROUNDED): row 7 'Self-storage facility' = BA (special permit) in Business. "
       "li CONDITIONAL: light-mfg-with-onsite-sales = Y but general light mfg N; wholesale/warehouse = "
       "BA. lgc PROHIBITED.")
N_NBLB = ("ss/mw PROHIBITED: row 7 Self-storage = N here. li CONDITIONAL: light-mfg-with-sales / "
          "research-lab = BA (special permit); no by-right industrial. lgc PROHIBITED.")
N_PROHIB = ("All prohibited. Row 7 Self-storage, row 1 Light manufacturing, row 6 Wholesale/warehouse = "
            "N in this residential district; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("SSR", "Single-Family Suburban Residence", "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("SR",  "Single Residence",                 "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("GR",  "General Residence",                 "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("NB",  "Neighborhood Business",             "prohibited","prohibited","conditional","prohibited",0.82,N_NBLB),
    ("LB",  "Limited Business",                  "prohibited","prohibited","conditional","prohibited",0.82,N_NBLB),
    ("B",   "Business",                          "conditional","conditional","conditional","prohibited",0.85,N_B),
    ("LI",  "Light Industrial",                  "permitted","permitted","permitted","prohibited",0.90,N_IND),
    ("I",   "Industrial",                        "permitted","permitted","permitted","prohibited",0.90,N_IND),
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
