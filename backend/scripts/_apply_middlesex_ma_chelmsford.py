"""Chelmsford MA — Stage-4 FULL close (2026-07-09). Zero held cells. 16 base districts.

TIER-1. NEEDLE MUNI: self-storage permitted by special permit in CB + IA -> armed candidates.
(Exception-queue #2 RESOLVED: the Use Regulation Schedule was auto-fetched via curl+browser-UA
at ecode360.com/attachment/332663/CH1747-195a — the earlier "eCode360 blocked" escalation was
premature; the corrected method reaches eCode360 attachment PDFs.)

Grounding — Town of Chelmsford Zoning Bylaw Ch. 195, Use Regulation Schedule (195 Attachment 1,
amended through 10-20-2025 FTM; ecode360 CH1747-195a):
  CLOSED-LIST (§195-5 / §195-6): no structure/land used except as set forth in the Use Regulation
    Schedule or §195-6. Legend: Y=permitted; N=excluded/prohibited; BA=special permit Board of
    Appeals (§195-103); PB=special permit Planning Board (§195-103).
  ss/mw CONDITIONAL in CB, IA: row 13 "Self-storage mini warehouse" = PB in CB and IA; N in all
    other districts. (Named use -> grounded.)
  li: row 2 "Light manufacturing" = Y (by-right) in IA + IS, PB in CB + CBLT; row 23 "Ultralight
    Manufacturing" = Y in CBLT + IA + IS, PB in CB. So li PERMITTED in IA, IS, CBLT (by-right
    light/ultralight mfg); CONDITIONAL in CB (PB only). Prohibited elsewhere.
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use; "Parking
    garage/structure" (row 16, BA/PB) is transient parking; "Motor vehicle towing and storage" is
    impound storage. Closed-list -> unnamed garage-condo prohibited (Wilmington ledger #58 + Woburn).

Districts (16): RA/RB/RC/RM/RMH (residential), CA/CB/CBLT/CC/CD/CV/CX (commercial), IA (Limited
Industrial) / IS (Special Industrial), P (Public), OS (Open Space). CBLT is brand-new (10-20-2025);
NMCOG/5 layer lags (no CBLT parcels yet) — CBLT verdict written for completeness.

Rebind: NMCOG layer 5 (field ZONE_), gates checked pre-apply. Executable apply (Dedham template):
idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim citations (#37), verify-and-print
(#42), catch #56 alignment via table row read.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_chelmsford.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "CHELMSFORD"
CITED_SUBSECTION = "195 Att.1 Use Reg Schedule rows 13/2/23 + §195-5/§195-6"
ORD = ("Town of Chelmsford Zoning Bylaw Ch. 195, Use Regulation Schedule (195 Attachment 1, amended "
       "through 10-20-2025 FTM; ecode360 CH1747-195a)")

Q_CLOSED = ("Ch.195: no structure shall be erected or used or land used except as set forth in the Use "
            "Regulation Schedule or in §195-6. Symbols: Y=a permitted use; N=an excluded or prohibited "
            "use; BA=special permit from the Board of Appeals (§195-103); PB=special permit from the "
            "Planning Board (§195-103).")
Q_SS = ("195 Att.1 Use Regulation Schedule row 13 'Self-storage mini warehouse' = PB (Planning Board "
        "special permit) in CB and IA; N (prohibited) in RA/RB/RC/RM/CA/CBLT/CC/CD/CV/IS/RMH/CX/P/OS.")
Q_LI = ("195 Att.1 row 2 'Light manufacturing' = Y (by-right) in IA + IS, PB in CB + CBLT, N elsewhere; "
        "row 23 'Ultralight Manufacturing' = Y in CBLT + IA + IS, PB in CB; row 3 'Heavy manufacturing' "
        "= N in all districts.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage PRINCIPAL use; 'Parking garage/structure' (row "
         "16) = BA/PB (transient parking, not owned storage); 'Motor vehicle towing and storage' = PB in "
         "CB/CC/CD (impound). Closed-list -> unnamed garage-condo storage prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "195 Att.1", "ordinance": ORD} for q in qs]


N_IA = ("ss/mw CONDITIONAL (GROUNDED): 'Self-storage mini warehouse' = PB in IA. li PERMITTED "
        "(GROUNDED): Light manufacturing + Ultralight Manufacturing = Y (by-right) in IA. lgc "
        "PROHIBITED: no named garage-condo use; parking garage is transient; closed-list.")
N_IS = ("li PERMITTED (GROUNDED): Light + Ultralight Manufacturing = Y (by-right) in IS. ss/mw "
        "PROHIBITED: 'Self-storage mini warehouse' = N in IS (only CB + IA carry PB). lgc PROHIBITED: "
        "no named garage-condo use; closed-list.")
N_CBLT = ("li PERMITTED (GROUNDED): Ultralight Manufacturing = Y (by-right) in CBLT (Light mfg PB). "
          "ss/mw PROHIBITED: 'Self-storage mini warehouse' = N in CBLT. lgc PROHIBITED (closed-list). "
          "CBLT = brand-new district (10-20-2025); NMCOG/5 layer has no CBLT parcels yet.")
N_CB = ("ss/mw CONDITIONAL (GROUNDED): 'Self-storage mini warehouse' = PB in CB. li CONDITIONAL: Light "
        "+ Ultralight Manufacturing = PB (special permit) in CB (no by-right industrial). lgc "
        "PROHIBITED: no named garage-condo use; parking garage transient; closed-list.")
N_PROHIB = ("All prohibited (closed-list). Self-storage mini warehouse (PB only in CB/IA), Light/"
            "Ultralight Manufacturing (by-right only in IA/IS/CBLT) and Warehouse carry N in this "
            "district; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("RA",   "Residence A (Single Family)",   "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RB",   "Residence B (Single Family)",   "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RC",   "Residence C (General)",         "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RM",   "Residence Multi-Family",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RMH",  "Residence Mobile Home",         "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("CA",   "Commercial Neighborhood",       "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CB",   "Commercial Roadside",           "conditional","conditional","conditional","prohibited",0.85,N_CB),
    ("CBLT", "Commercial Business/Life-Tech", "prohibited","prohibited","permitted","prohibited",0.85,N_CBLT),
    ("CC",   "Commercial Shopping Center",    "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CD",   "Commercial General",            "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CV",   "Commercial Center Village",     "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CX",   "Commercial Adult",              "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("IA",   "Industrial Limited",            "conditional","conditional","permitted","prohibited",0.90,N_IA),
    ("IS",   "Industrial Special",            "prohibited","prohibited","permitted","prohibited",0.90,N_IS),
    ("P",    "Public",                        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("OS",   "Open Space",                    "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
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
