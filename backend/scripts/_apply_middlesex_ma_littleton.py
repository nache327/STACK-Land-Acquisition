"""Littleton MA — Stage-4 FULL close (2026-07-09). Zero held cells. 5 base districts.

TIER-1 carry-over (was deferred; eCode360 use schedule now auto-fetched via curl+UA print view).
NEEDLE MUNI: self-storage is a named use permitted by special permit in Industrial A + B.

Grounding — Town of Littleton Zoning Bylaw Ch. 173 (eCode360 LI1092; §173-26 Use Regulations
Schedule, §173-22 districts, §173-25 general):
  CLOSED-LIST (§173-25.A): "No building or structure shall be erected or used, and no land shall
    be used, except as set forth in the Use Regulations Schedule or as exempted by §§173-8..11 or
    by statute." Legend (§173-25): Y=permitted; P/A=special permit (§173-7); N=excluded/prohibited.
  ss/mw CONDITIONAL in I-A, I-B: §173-26 "Self-storage facilities" = P (special permit) in
    Industrial A and Industrial B; N in R (Residence), B (Business), VC (Village Common). Named use.
  li PERMITTED in I-A, I-B: §173-26 "Manufacturing", "Wholesaling, warehousing, distribution
    center", "Research and development" = Y (by-right) in Industrial A + B. CONDITIONAL in VC:
    general Manufacturing = N but "Major industrial use (Article XVIII)" = P (special permit).
    Prohibited in R and B (Manufacturing + Major industrial use both N).
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use ("Self-
    storage facilities" is the personal-storage product, distinct); closed-list -> unnamed garage-
    condo prohibited (Wilmington ledger #58 + Woburn convention).

Districts (MAPC layer 2, strip 158): R, B, VC (Village Common = Mixed Use), I-A, I-B. The bylaw's
"Littleton Station MBTA Communities Multi-family" district is a newer overlay not in MAPC / no
base parcels.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via parsed HTML table cells.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_littleton.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "LITTLETON"
CITED_SUBSECTION = "§173-26 Use Regulations Schedule + §173-25.A"
ORD = ("Town of Littleton Zoning Bylaw Ch. 173 (eCode360 LI1092), §173-22 Establishment of "
       "Districts + §173-25 Use Regulations + §173-26 Use Regulations Schedule")

Q_CLOSED = ("§173-25.A: 'No building or structure shall be erected or used, and no land shall be used, "
            "except as set forth in the Use Regulations Schedule or as exempted by §§173-8 through "
            "173-11 or by statute.' Legend §173-25: Y=a permitted use; P/A=special permit (§173-7); "
            "N=excluded/prohibited.")
Q_SS = ("§173-26 Use Regulations Schedule, INDUSTRIAL USES 'Self-storage facilities': P (special "
        "permit) in Industrial A and Industrial B; N in R (Residence), B (Business), VC (Village Common).")
Q_LI = ("§173-26 'Manufacturing' = Y (by-right) in Industrial A + B (N in R/B/VC); 'Wholesaling, "
        "warehousing, distribution center' = Y in Industrial A + B; 'Research and development' = Y in "
        "Industrial A + B; 'Major industrial use (Article XVIII)' = P in VC / Industrial A / Industrial B.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use exists in the §173-26 schedule "
         "('Self-storage facilities' is the personal-storage product). §173-25.A closed-list -> an "
         "unnamed garage-condo storage use is prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "§173-26", "ordinance": ORD} for q in qs]


N_IND = ("li PERMITTED (GROUNDED): Manufacturing / Warehousing / R&D = Y (by-right) here. ss/mw "
         "CONDITIONAL (GROUNDED): 'Self-storage facilities' = P (special permit) here (named use). lgc "
         "PROHIBITED: no named garage-condo use; closed-list §173-25.A.")
N_VC = ("li CONDITIONAL: general Manufacturing = N but 'Major industrial use (Article XVIII)' = P "
        "(special permit) in VC. ss/mw PROHIBITED: 'Self-storage facilities' = N in VC. lgc PROHIBITED "
        "(closed-list). VC = Village Common (mixed-use).")
N_PROHIB = ("All prohibited (closed-list §173-25.A). 'Self-storage facilities', Manufacturing, "
            "Warehousing and Major industrial use all carry N in this district; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R",   "Residence",       "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("B",   "Business",        "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("VC",  "Village Common",  "prohibited","prohibited","conditional","prohibited",0.80,N_VC),
    ("I-A", "Industrial A",    "conditional","conditional","permitted","prohibited",0.90,N_IND),
    ("I-B", "Industrial B",    "conditional","conditional","permitted","prohibited",0.90,N_IND),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_CLOSED, Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
