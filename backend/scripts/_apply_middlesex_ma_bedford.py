"""Bedford MA — Stage-4 FULL close (2026-07-09). Zero held cells. 11 base districts.

TAIL (Rt-3 / Hanscom biotech, wealthy). NEEDLE MUNI: no NAMED self-storage use, but Warehouse
is BY-RIGHT in the Commercial + Industrial A/B/C districts -> self-storage conditional there per
the warehouse->self_storage convention.

Grounding — Town of Bedford Zoning Bylaw (adopted Town Meeting March 25 2025; bedfordma.gov
View/2818), §2.3 + Table 4.3-1 Table of Principal Uses (Appendix A):
  CLOSED-LIST (§2.3): "Any building or use of premises not specifically permitted is prohibited."
    Legend: Yes=permitted; SP=special permit; No=prohibited.
  li PERMITTED in C, IP, I, IC: Table 4.3-1 "Light Manufacturing" = Yes (by-right) in the
    Commercial district + Industrial A/B/C (= MAPC IP/I/IC); No in residential.
  ss/mw CONDITIONAL in C, IP, I, IC: no named self-storage use, but Table 4.3-1 "Warehouse"
    (defined: "Warehouse or other building for the storage or wholesale marketing of materials")
    = Yes (by-right) in Commercial + Industrial A/B/C -> self-storage is the more-specific storage
    product => conditional there per the warehouse->self_storage convention (closed-list + unnamed
    => conditional, not by-right). Prohibited in all other districts.
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use; §2.3
    closed-list (Wilmington ledger #58 + Woburn convention).

Districts (MAPC layer 2, strip ^23): R/R-A/R-B/R-C/R-D=Residence, C=Commercial, IP=Industrial Park
A (bylaw 'Industrial A'), I=Industrial (B), IC=Industrial (C). GB/LB = Great Road District
(Table 4.3-2, form-based mixed-use corridor) — warehouse/self-storage are NOT among its uses
(Table 4.3-1 industrial grants do not extend to Great Road); recorded prohibited (conservative,
Table 4.3-2 not machine-parsed — lower confidence).

Rebind: MAPC (strip ^23) — parcels carried generic assessor codes (IND/COM/A/B/C), rebound to
IP/I/IC/C/GB/LB/R*. Gates a/b/d PASS, 5 orphans, ~93% changed (assessor->bylaw split IND->IP/I/IC).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via parsed Table 4.3-1 rows.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_bedford.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "BEDFORD"
CITED_SUBSECTION = "Table 4.3-1 (Warehouse / Light Manufacturing) + §2.3 closed-list"
ORD = ("Town of Bedford Zoning Bylaw (adopted March 25 2025; bedfordma.gov View/2818), §2.3 + "
       "Table 4.3-1 Table of Principal Uses (Appendix A)")

Q_CLOSED = ("§2.3: 'Any building or use of premises not specifically permitted is prohibited.' Table "
            "4.3-1 legend: Yes=permitted; SP=special permit; No=prohibited.")
Q_LI = ("Table 4.3-1 'Light Manufacturing' = Yes (by-right) in the Commercial district + Industrial A, "
        "Industrial B, Industrial C; No in Residence R/A/B/C/D.")
Q_SS = ("No named self-storage/mini-warehouse use. Table 4.3-1 'Warehouse' (defined: 'Warehouse or "
        "other building for the storage or wholesale marketing of materials, merchandise...') = Yes "
        "(by-right) in Commercial + Industrial A/B/C -> self-storage conditional there per the "
        "warehouse->self_storage convention; §2.3 closed-list prohibits it elsewhere.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use in Table 4.3-1; §2.3 closed-list "
         "-> unnamed garage-condo storage prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Table 4.3-1", "ordinance": ORD} for q in qs]


N_IND = ("li PERMITTED (GROUNDED): Table 4.3-1 Light Manufacturing = Yes (by-right) here. ss/mw "
         "CONDITIONAL: Warehouse = Yes (by-right) -> self-storage conditional (convention; unnamed + "
         "closed-list => conditional). lgc PROHIBITED: no named garage-condo use; §2.3 closed-list.")
N_GR = ("Great Road District (Table 4.3-2, form-based mixed-use corridor). Warehouse / self-storage / "
        "light manufacturing are NOT among its by-right uses (Table 4.3-1 industrial grants do not "
        "extend to Great Road) -> all prohibited (conservative; Table 4.3-2 not machine-parsed).")
N_PROHIB = ("All prohibited (§2.3 closed-list). Table 4.3-1 Warehouse + Light Manufacturing = No in "
            "this district; no named self-storage or garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R",   "Residence R",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-A", "Residence A",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-B", "Residence B",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-C", "Residence C",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-D", "Residence D",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("GB",  "Great Road Business","prohibited","prohibited","prohibited","prohibited",0.75,N_GR),
    ("LB",  "Great Road Limited Business","prohibited","prohibited","prohibited","prohibited",0.75,N_GR),
    ("C",   "Commercial",         "conditional","conditional","permitted","prohibited",0.82,N_IND),
    ("IP",  "Industrial Park A",  "conditional","conditional","permitted","prohibited",0.85,N_IND),
    ("I",   "Industrial (B)",     "conditional","conditional","permitted","prohibited",0.85,N_IND),
    ("IC",  "Industrial (C)",     "conditional","conditional","permitted","prohibited",0.85,N_IND),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
