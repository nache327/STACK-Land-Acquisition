"""Westford MA — Stage-4 FULL close (2026-07-09). Zero held cells. 10 base districts.

TIER-1. 0-NEEDLE for self-storage (like Woburn/Wilmington): real light-industrial land
(IA/IB/IC/ID/IH + CH) but self-storage is affirmatively excluded from the one warehouse use
and is not a named use anywhere -> prohibited citywide under the closed-list.

Grounding — Town of Westford Zoning Bylaw, certified Oct 27 2025 (westfordma.gov
DocumentCenter/View/18102), Appendix A Table of Principal Use Regulations + §3 Use Regulations:
  CLOSED-LIST (§3): "Any use not allowed in the district as a principal use is also prohibited";
    comprehensive Y/N table. Legend: Y=permitted, N=not permitted, SPB=special permit Planning
    Board, SPA=special permit Zoning Board of Appeals.
  ss/mw PROHIBITED everywhere (affirmative exclusion + closed-list): the "Warehouse" use is
    DEFINED as "A building used primarily for the storage of goods and materials, for
    distribution, but not for sale on the premises, and EXCLUDING mini or self-storage warehouse."
    No self-storage / mini-warehouse use row exists anywhere in the Table of Principal Use
    Regulations -> self-storage is not a permitted use in any district.
  li PERMITTED in CH/IH/IA/IB/IC/ID: "Light manufacturing" (E.7) = Y (by-right) in IH/IA/IB/IC/ID,
    SPA in CH; "Research/office park" (E.1) + "Light manufacturing <=4 employees" (E.8) = Y by-right
    in CH -> by-right light-industrial path in CH too. Prohibited in RA/RB/B/BL.
  lgc PROHIBITED everywhere: no principal-use garage-condo / automotive-storage use; "Commercial
    parking lot" (D.C.19, Y in CH/IH) is transient parking; garage / "storage of vehicles and
    trailers" / "private parking garage" are ACCESSORY uses only (§3.2). Closed-list -> unnamed
    principal garage-condo prohibited (consistent w/ Wilmington ledger #58 + Woburn).

Rebind: NMCOG layer 20 (field DISTRICT_C); vocab matches the CURRENT Oct-2025 certified bylaw
Appendix A district columns exactly (Hudson check PASS), gates a/b/d PASS, 3.5% changed, 8 orphans.
NOTE: the rebind script's condition-5 global matrix-untouched assertion trips under parallel-session
matrix writes (it counts ALL zone_use_matrix rows, unscoped) -> apply exited 1 AFTER the parcel
UPDATEs committed; Westford parcels verified rebound (RA/RB/CH/B/IA/IB/IC/ID/IH/BL). Spurious guard
trip, not a data issue -- flagged for a tooling fix (scope the assert to the muni jid).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via table row read.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_westford.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "WESTFORD"
CITED_SUBSECTION = "Appendix A Table of Principal Use Regs (Warehouse def + E.1/E.7) + §3"
ORD = ("Town of Westford Zoning Bylaw, certified October 27 2025 (westfordma.gov "
       "DocumentCenter/View/18102), Appendix A Table of Principal Use Regulations + §3 Use Regulations")

Q_CLOSED = ("§3: 'Any use not allowed in the district as a principal use is also prohibited.' "
            "Appendix A is a comprehensive Y/N table. Legend: Y=permitted, N=not permitted, "
            "SPB=special permit Planning Board, SPA=special permit Zoning Board of Appeals.")
Q_SS = ("Appendix A definition of 'Warehouse': 'A building used primarily for the storage of goods and "
        "materials, for distribution, but not for sale on the premises, and EXCLUDING mini or "
        "self-storage warehouse.' No self-storage / mini-warehouse USE ROW exists anywhere in the "
        "Table of Principal Use Regulations -> self-storage is not a permitted use in any district.")
Q_LI = ("Appendix A Industrial Uses E.7 'Light manufacturing' = Y (by-right) in IH/IA/IB/IC/ID, SPA in "
        "CH; E.1 'Research/office park' = Y in CH/IH/IA/IB/IC/ID; E.8 'Light manufacturing with not "
        "more than four employees' = Y in CH/IH; E.2 'Warehouse' = SPB in IH/IA/IB/IC/ID.")
Q_LGC = ("No principal-use garage-condo / automotive-storage use exists; 'Commercial parking lot' "
         "(D.C.19, Y in CH/IH) is transient parking; garage, 'storage of vehicles and trailers', and "
         "'private parking garage' are ACCESSORY uses only (§3.2). Closed-list -> unnamed principal "
         "garage-condo storage prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Appendix A / §3", "ordinance": ORD} for q in qs]


N_IND = ("li PERMITTED (GROUNDED): Light manufacturing / Research-office-park by-right (Appendix A "
         "E.7/E.1). ss/mw PROHIBITED (GROUNDED): 'Warehouse' use is DEFINED to EXCLUDE mini/"
         "self-storage warehouse and no self-storage use row exists -> not permitted (closed-list). "
         "lgc PROHIBITED: no principal garage-condo use; commercial parking lot is transient; "
         "closed-list.")
N_CH = ("li PERMITTED (GROUNDED): Research/office park + Light manufacturing <=4 employees by-right in "
        "CH (general light mfg = SPA). ss/mw PROHIBITED: 'Warehouse' excludes self-storage + no "
        "self-storage row (closed-list). lgc PROHIBITED: no principal garage-condo use; closed-list.")
N_PROHIB = ("All prohibited (closed-list). No light-industrial use permitted (Light manufacturing / "
            "Research-office-park / Warehouse all N here). ss/mw: 'Warehouse' excludes self-storage + no "
            "self-storage use row anywhere. lgc: no principal garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("RA", "Residence A",         "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RB", "Residence B",         "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("B",  "Business",            "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("BL", "Business, Limited",   "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("CH", "Commercial Highway",  "prohibited","prohibited","permitted","prohibited",0.82,N_CH),
    ("IH", "Industrial Highway",  "prohibited","prohibited","permitted","prohibited",0.90,N_IND),
    ("IA", "Industrial A",        "prohibited","prohibited","permitted","prohibited",0.90,N_IND),
    ("IB", "Industrial B",        "prohibited","prohibited","permitted","prohibited",0.90,N_IND),
    ("IC", "Industrial C",        "prohibited","prohibited","permitted","prohibited",0.90,N_IND),
    ("ID", "Industrial D",        "prohibited","prohibited","permitted","prohibited",0.90,N_IND),
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
