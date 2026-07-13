"""Lexington MA — Stage-4 FULL close (2026-07-09). Zero held cells. 12 base districts.

TAIL / tier-2 (Rt-128 biotech corridor, very wealthy). 0-NEEDLE for self-storage — a CORRECT
no-op: Lexington has real manufacturing/office districts (CM, CRO) but self-storage is NOT a
listed use and the bylaw is closed-list.

No rebind: parcels already carry the bylaw Table-1 district codes (GC/RO/RS/RT/CN/CRS/CS/CB/
CLO/CRO/CM/CSX). NOTE: GC = "Government Civic Use" (NOT commercial) — the large GC parcel count
is civic land, not a needle signal.

Grounding — Code of the Town of Lexington Ch. 135 Zoning (eCode360 LE1818; §135-3.0 + Table 1,
Permitted Uses & Development Standards, 135 Attachment 1, Supp 33 Feb 2025):
  CLOSED-LIST (§135-3.1): "Uses not listed in Table 1 [are prohibited]." Legend: Y=permitted;
    SP=special permit; N=not permitted.
  ss/mw PROHIBITED everywhere: NO self-storage / mini-warehouse row exists in Table 1. The only
    by-right storage uses in CM are specific — "Commercial mover, associated storage facilities"
    (M.1.03) and "Distribution center" (M.1.04) — neither is generic warehouse nor leased personal
    self-storage; distribution/mover-specific mentions do NOT fire the warehouse->self_storage
    convention. Closed-list => self-storage prohibited in every district.
  li PERMITTED in CM (Light manufacturing N.1.01 = Y) and CRO (Research & Development N.1.02 = Y,
    Biotech manufacturing SP); CONDITIONAL in CS / CSX (Industrial services M.1.02 + mover-storage
    M.1.03 = SP). Prohibited elsewhere.
  lgc CONDITIONAL in CS, CSX only: named use "Storage of automobiles or trucks" (L.1.08) = SP in
    CS + CSX; N in all other districts. Prohibited elsewhere (closed-list; no other vehicle-storage
    principal use).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via parsed Table-1 rows.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_lexington.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "LEXINGTON"
CITED_SUBSECTION = "Table 1 (135 Att.1) M/N/L categories + §135-3.1 closed-list"
ORD = ("Code of the Town of Lexington Ch. 135 Zoning (eCode360 LE1818), §135-3.0 Use Regulations + "
       "Table 1 Permitted Uses & Development Standards (135 Attachment 1, Supp 33 Feb 2025)")

Q_CLOSED = ("§135-3.1: 'Uses not listed in Table 1 [are prohibited].' Table 1 legend: Y=permitted as of "
            "right; SP=special permit; N=not permitted. Districts: GC/RO/RS/RT/CN/CRS/CS/CB/CLO/CRO/CM/CSX.")
Q_SS = ("Table 1 has NO self-storage / mini-warehouse use row. Category M storage uses in CM are "
        "specific: M.1.03 'Commercial mover, associated storage facilities' = Y; M.1.04 'Distribution "
        "center, parcel/commercial mail delivery' = Y (CM), Y (CRO). No generic warehouse or leased "
        "self-storage use -> closed-list (§135-3.1) prohibits self-storage in every district.")
Q_LI = ("Table 1 N.1.01 'Light manufacturing' = Y (by-right) in CM only; N.1.02 'Research and "
        "development' = Y in CRO + CM; N.1.04 'Biotech manufacturing' = SP CRO / Y CM; M.1.02 "
        "'Industrial services (machine shop, welding)' + M.1.03 = SP in CS + CSX.")
Q_LGC = ("Table 1 L.1.08 'Storage of automobiles or trucks' = SP in CS and CSX (a commercial/fleet "
         "vehicle-storage use), N elsewhere. No luxury owned/leased garage-condo use is listed -> lgc "
         "PROHIBITED in every district (closed-list §135-3.1; and lgc is not carried above the "
         "prohibited self-storage product, catch #58).")


def cite(*qs):
    return [{"quote": q, "section": "Table 1", "ordinance": ORD} for q in qs]


N_CM = ("li PERMITTED (GROUNDED): Table 1 N.1.01 Light manufacturing = Y (by-right) in CM. ss/mw "
        "PROHIBITED: no self-storage row; only mover-storage (M.1.03) + distribution (M.1.04) by-right "
        "-> closed-list prohibits self-storage. lgc PROHIBITED: L.1.08 auto/truck storage = N in CM.")
N_CRO = ("li PERMITTED (GROUNDED): Table 1 N.1.02 R&D = Y (by-right) in CRO (biotech mfg SP). ss/mw "
         "PROHIBITED (no self-storage row; only distribution by-right; closed-list). lgc PROHIBITED "
         "(L.1.08 = N in CRO).")
N_CSX = ("li CONDITIONAL: Table 1 M.1.02 industrial services + M.1.03 mover-storage = SP here. lgc "
         "PROHIBITED (demoted, catch #58): L.1.08 'Storage of automobiles or trucks' = SP here is a "
         "commercial/fleet vehicle-storage use, NOT a luxury owned/leased garage-condo; and lgc may not "
         "sit permitted/conditional above the prohibited self-storage product. ss/mw PROHIBITED (no "
         "self-storage row; closed-list §135-3.1).")
N_PROHIB = ("All prohibited (closed-list §135-3.1). No self-storage row in Table 1; Light manufacturing "
            "(N.1.01) + auto-storage (L.1.08) = N in this district.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("GC",  "Government Civic Use",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RO",  "One-Family Residence",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RS",  "One-Family Residence (small)","prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RT",  "Two-Family Residence",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("CN",  "Neighborhood Commercial",     "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CRS", "Retail/Service Commercial",   "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CB",  "Central Business",            "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CLO", "Local Office",                "prohibited","prohibited","prohibited","prohibited",0.88,N_PROHIB),
    ("CS",  "Service Commercial",          "prohibited","prohibited","conditional","prohibited",0.78,N_CSX),
    ("CSX", "Service Commercial (CSX)",    "prohibited","prohibited","conditional","prohibited",0.78,N_CSX),
    ("CRO", "Regional Office",             "prohibited","prohibited","permitted","prohibited",0.88,N_CRO),
    ("CM",  "Manufacturing",               "prohibited","prohibited","permitted","prohibited",0.90,N_CM),
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
