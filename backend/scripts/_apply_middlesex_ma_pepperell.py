"""Pepperell MA — Stage-4 FULL close (2026-07-13). 7 districts. MRPC region (not MAPC/NMCOG).

TAIL. NEEDLE MUNI: "Self-storage facility" is permitted BY-RIGHT in both Commercial (C) and
Industrial (I). No rebind: Pepperell parcels carry meaningful district codes (RUR/TNR/SUR/RCR/URR/
COM/IND) that map one-to-one BY NAME to the bylaw's §2200 abbreviations (RR/TR/RCR/SR/UR/C/I) —
verified against the district-establishment list. Verdicts are keyed on the PARCEL codes so they join
parcels.zoning_code directly (COM->C Commercial, IND->I Industrial).

Grounding — Town of Pepperell Zoning Bylaw (adopted 9/17/2001, consolidated rev. 7/28/2014,
town.pepperell.ma.us/DocumentCenter/View/2442), Appendix A Table of Principal Uses, columns
RR TR RCR SR UR C I:
  Legend (§3100 header): Y=permitted as of right; BA=Special Permit/Board of Appeals; PB=Special
    Permit/Planning Board; BOS=Special Permit/Board of Selectmen. CLOSED LIST — §3100 "Any building
    or use of premises not herein expressly permitted is hereby prohibited."
  ss/mw PERMITTED (by-right) in C, I: "Self-storage facility" = Y in C + I, N in all residence
    districts; "Warehouse, wholesale or indoor storage facility" = Y in C + I.
  li PERMITTED in C, I: "Light manufacturing; research laboratory" = Y in C + I; "Manufacturing,
    assembly or processing" = PB in C, Y in I. Prohibited in RR/TR/RCR/SR/UR (contractor's-yard BA is
    a narrow outdoor-storage special permit, not by-right light industry).
  lgc PROHIBITED everywhere: no named vehicle garage-condo principal use; "Self-storage facility" is
    goods storage and "Parking Garage" is an accessory customer/employee vehicle-parking structure,
    neither a luxury owned/leased garage-condo; closed list (§3100) + Wilmington ledger #58 / Woburn
    convention.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), name-mapping disambiguation (#38), verify-and-print (#42), closed-list
sweep (#58), catch #56 alignment via pdfplumber table extraction.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_pepperell.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "PEPPERELL"
CITED_SUBSECTION = "Appendix A Table of Principal Uses (F. Industrial; G. Other)"
ORD = ("Town of Pepperell Zoning Bylaw (adopted 9/17/2001, consolidated rev. 7/28/2014, "
       "town.pepperell.ma.us/DocumentCenter/View/2442), Appendix A Table of Principal Uses")

Q_SS = ("Appendix A 'Self-storage facility': Y (permitted as of right) in C and I; N in RR/TR/RCR/SR/UR. "
        "'Warehouse, wholesale or indoor storage facility': Y in C + I. Legend: Y=as of right; "
        "BA/PB/BOS=special permit; §3100 closed list.")
Q_LI = ("Appendix A 'Light manufacturing; research laboratory' = Y in C + I; 'Manufacturing, assembly "
        "or processing' = PB in C, Y in I; 'Contractor's yard or outdoor storage facility' = BA in the "
        "residence districts, Y in C + I.")
Q_LGC = ("§3100 'Any building or use of premises not herein expressly permitted is hereby prohibited.' "
         "No named vehicle garage-condo use; 'Self-storage facility' is goods storage and 'Parking "
         "Garage' is an accessory vehicle-parking structure -> lgc prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Appendix A / §3100", "ordinance": ORD} for q in qs]


N_CI = ("ss/mw PERMITTED (GROUNDED): 'Self-storage facility' = Y (as of right) + 'Warehouse, wholesale "
        "or indoor storage facility' = Y here. li PERMITTED: 'Light manufacturing; research laboratory' "
        "= Y (as of right). lgc PROHIBITED: no named garage-condo use (closed list §3100).")
N_PROHIB = ("All prohibited. 'Self-storage facility', 'Warehouse/indoor storage', 'Light manufacturing' "
            "= N in this residence district; §3100 closed list; no named garage-condo use. (Contractor's "
            "yard = BA only, a narrow outdoor-storage special permit.)")

# parcel_code, bylaw_col, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("RUR", "RR", "Rural Residence",        "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("TNR", "TR", "Town Residence",         "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("SUR", "SR", "Suburban Residence",     "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("RCR", "RCR","Recreational Residence", "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("URR", "UR", "Urban Residence",        "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("COM", "C",  "Commercial",             "permitted","permitted","permitted","prohibited",0.90,N_CI),
    ("IND", "I",  "Industrial",             "permitted","permitted","permitted","prohibited",0.90,N_CI),
]

VERDICTS = [{
    "zone_code": pc, "zone_name": f"{zn} ({col})", "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
    "confidence": conf, "notes": note,
} for pc, col, zn, ss, mw, li, lgc, conf, note in _R]

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
