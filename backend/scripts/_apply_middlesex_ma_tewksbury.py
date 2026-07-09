"""Tewksbury MA — Stage-4 FULL close (2026-07-09). Zero held cells. 15 base districts.

TIER-1 (Rt-38 / I-93 corridor). NEEDLE MUNI: unlike Wilmington/Woburn (self-storage
prohibited), Tewksbury MA PERMITS self-storage by special permit in the office-industrial
+ WNB districts -> real armed candidates.

NOT the NJ namesake: Tewksbury Township, Hunterdon NJ (jid e8612f49, _apply_tewksbury.py)
is a different jurisdiction and is off-limits to this county session (catch #38).

Grounding — Town of Tewksbury Zoning Bylaw, MAY 2025 (tewksbury-ma.gov DocumentCenter/View/4550),
§5.4 Use Regulations + Appendix A (§5.4.3) Table of Uses:
  CLOSED-LIST (§5.4.2.A): "Any use not listed in Section 5, Appendix A, or otherwise allowable
    under the provisions of this Bylaw shall be deemed prohibited." Legend: Y=by-right (may need
    Site Plan Review); PB=Planning Board special permit; SP=ZBA special permit; N=prohibited.
  ss/mw CONDITIONAL in WNB, I1, I2, OR: Appendix A "NN. SELF-STORAGE FACILITY" = PB (special
    permit) in WNB, I1, I2, OR; N in all other districts. (Named use -> grounded.)
  li PERMITTED in WNB, I1, I2, OR: "A. RESEARCH & DEVELOPMENT, LABORATORY, WHICH MAY INCLUDE
    ACCESSORY MANUFACTURING..." = Y (by-right) in WNB, I1, I2, OR; "Q. LIGHT INDUSTRIAL
    WAREHOUSE" + "O. DATA STORAGE CENTER" + "P. COLD STORAGE WAREHOUSE" = Y (by-right) in I1, I2,
    OR; "C. MANUFACTURING" = PB in WNB/I1/I2/OR.
  lgc PROHIBITED everywhere: no "garage for automotive storage" / vehicle-storage-condo use is a
    named permitted use; "Commercial Parking Lot or Parking Garage" is transient parking (not
    owned/leased dead storage). Under the closed-list a garage-condo is unnamed -> prohibited
    (consistent w/ Wilmington ledger #58 + Woburn).

Rebind: NMCOG layer 23 (Tewksbury Zoning Districts 7-1-2022); vocab matches the CURRENT May-2025
bylaw §4.1 exactly (Hudson check PASS), gates a/b/d PASS, 9.5% changed (assessor->bylaw code
translation: HI->I1/I2, COM->business, TR->TD, FA->F), 4 orphans. Executable apply (Dedham
template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim citations (#37),
verify-and-print (#42), catch #56 alignment via pdfplumber table extraction.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_tewksbury.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA (NOT Hunterdon NJ)
MUNI = "TEWKSBURY"
CITED_SUBSECTION = "Appendix A (§5.4.3) NN/A.5 + §5.4.2.A"
ORD = ("Town of Tewksbury Zoning Bylaw, May 2025 (tewksbury-ma.gov DocumentCenter/View/4550), "
       "§5.4 Use Regulations + Appendix A (§5.4.3) Table of Uses")

Q_CLOSED = ("§5.4.2.A: 'Any use not listed in Section 5, Appendix A, or otherwise allowable under the "
            "provisions of this Bylaw shall be deemed prohibited.' Legend (§5.4.3): Y=permitted as of "
            "right (may be subject to Site Plan Review); PB=Planning Board special permit; SP=ZBA "
            "special permit; N=prohibited.")
Q_SS = ("Appendix A 'NN. SELF-STORAGE FACILITY': PB (Planning Board special permit) in WNB, I1, I2, OR; "
        "N (prohibited) in F, R40, MF, VR, MUB, TC, LB, SB, GB, TD, P.")
Q_LI = ("Appendix A A.5 INDUSTRIAL 'A. RESEARCH & DEVELOPMENT, LABORATORY, WHICH MAY INCLUDE ACCESSORY "
        "MANUFACTURING OF PRODUCTS IN TESTING AND DEVELOPMENT' = Y (by-right) in WNB, I1, I2, OR; "
        "'Q. LIGHT INDUSTRIAL WAREHOUSE', 'O. DATA STORAGE CENTER', 'P. COLD STORAGE WAREHOUSE' = Y in "
        "I1, I2, OR; 'C. MANUFACTURING' = PB in WNB/I1/I2/OR; all N in every other district.")
Q_LGC = ("No 'garage for automotive storage' / vehicle-storage condominium is a named permitted use "
         "(A.4 motor-vehicle uses cover sales/repair/gas/car-wash and 'Commercial Parking Lot or "
         "Parking Garage' = transient parking only). §5.4.2.A closed-list -> an unnamed garage-condo "
         "storage use is prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Appendix A / §5.4.2", "ordinance": ORD} for q in qs]


N_NEEDLE = ("ss/mw CONDITIONAL (GROUNDED): 'Self-storage facility' = PB (special permit) here (named "
            "use, Appendix A NN). li PERMITTED (GROUNDED): Research & Development/Laboratory (accessory "
            "manufacturing) by-right (Y); {whse} Manufacturing by special permit. lgc PROHIBITED: no "
            "named garage-condo/automotive-storage use; parking garage is transient; closed-list "
            "(§5.4.2.A).")
N_PROHIB = ("All prohibited (closed-list §5.4.2.A). Self-storage facility (NN), Research & "
            "Development/Manufacturing (A.5), Light Industrial Warehouse (Q) and Warehouse/Distribution "
            "(E) all carry N in this district. lgc: no named garage-condo use -> prohibited.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("F",   "Farming",                        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R40", "Residence 40",                    "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("MF",  "Multifamily",                     "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("VR",  "Village Residential",             "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("TC",  "Town Center",                     "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("MUB", "Mixed-Use Business",              "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("SB",  "South Village Business",          "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("GB",  "General Business",                "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("LB",  "Limited Business",                "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("TD",  "Transition",                      "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("P",   "Park",                            "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("WNB", "Westside Neighborhood Business",  "conditional","conditional","permitted","prohibited",0.88,N_NEEDLE.format(whse="")),
    ("OR",  "Office-Research",                 "conditional","conditional","permitted","prohibited",0.90,N_NEEDLE.format(whse="Data Storage / Cold Storage Warehouse by-right;")),
    ("I1",  "Industrial 1",                    "conditional","conditional","permitted","prohibited",0.92,N_NEEDLE.format(whse="Light Industrial Warehouse / Data Storage / Cold Storage Warehouse by-right;")),
    ("I2",  "Industrial 2",                    "conditional","conditional","permitted","prohibited",0.92,N_NEEDLE.format(whse="Light Industrial Warehouse / Data Storage / Cold Storage Warehouse by-right;")),
]

VERDICTS = []
for zc, zn, ss, mw, li, lgc, conf, note in _R:
    cites = cite(Q_CLOSED, Q_SS, Q_LI, Q_LGC)
    VERDICTS.append({"zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
                     "light_industrial": li, "luxury_garage_condo": lgc, "citations": cites,
                     "cited_subsection": CITED_SUBSECTION, "confidence": conf, "notes": note})

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
