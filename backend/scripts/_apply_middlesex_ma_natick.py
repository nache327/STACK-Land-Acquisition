"""Natick MA — Stage-4 FULL close (2026-07-13). Large multi-district town; CURRENT June-2025 bylaw.

TAIL. MODEST NEEDLE: self-storage is NOT a named use in Natick's bylaw (verified: only occurrence of
"self-*" is "self-service laundry"). Under the closed list (§III-A.1.a "no building or structure shall
be erected or used ... except as set forth in the Table of Use Regulations"), self-storage grounds to
its nearest NAMED use — K6 "Warehouses (excluding retail warehouses), for storage of any personal
property with no sales taking place on the premises" (a self-storage facility is warehousing of
personal property). ss/mw therefore inherit K6's permission (#58 demote-unnamed-to-named).

No rebind: verdicts are keyed on the PARCEL codes so they join parcels.zoning_code directly. Parcel
codes map to the Table of Use columns (RG RM RS PCD AP DM CII INI INII H CG HMIa HMIb LC) by name;
RS* / RES* / RG variants are all residential.

Grounding — Zoning Bylaws Town of Natick, MA, June 2025 (natickma.gov DocumentCenter/View/19928),
Section III-A.1 Table of Use Regulations + district-specific §III-B/C/D/E/G. Legend: Y=permitted;
SP=Special Permit (§VI-DD.1); N=excluded.
  ss/mw (=K6 Warehouse): SP (conditional) in INII (K6=SP*) and HMIa (K6=SP); DM = warehouse <1,000 sf
    Y / >1,000 sf SP (K6a/K6b) -> a self-storage facility (>1,000 sf) = conditional. N (prohibited)
    everywhere else INCLUDING INI (K6 INI=N), CII, CG, LC, PCD, AP. The HM-II/HM-III/HPU district
    sections (§III-C/G.1/G.2) name office / R&D / retail / showroom-with-inside-storage but NO
    warehouse or self-storage use -> prohibited there (closed list).
  li (=K4 Light manufacturing / K5 General industrial): permitted (by-right) in INI (K4=Y), INII
    (K4=Y, K5=Y), HMIa (K4=Y, K5=Y); conditional in CG (K4=SP) and HM-II/HM-III/HPU (R&D/craft by site
    plan). Prohibited in residential / CII / LC / DM / PCD / AP / HMIb.
  lgc PROHIBITED everywhere: no named vehicle garage-condo use; the HPU "surface or indoor storage and
    parking of motor vehicles" is accessory parking, not a leased/owned garage-condo; closed list
    (Wilmington ledger #58 + Woburn convention).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), unnamed->named demotion (#58), verify-and-print (#42), catch #56 alignment
via pdfplumber table extraction of the 14-column Table of Use.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_natick.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "NATICK"
CITED_SUBSECTION = "Section III-A.1 Table of Use Regs (K4/K5/K6) + §III-B..G"
ORD = ("Zoning Bylaws Town of Natick, MA, June 2025 (natickma.gov DocumentCenter/View/19928), "
       "Section III-A.1 Table of Use Regulations + district-specific §III-B/C/D/E/G")

Q_SS = ("Self-storage is not a named use (only 'self-service laundry' appears); under §III-A.1.a closed "
        "list it grounds to K6 'Warehouses (excluding retail warehouses), for storage of any personal "
        "property with no sales taking place on the premises' = SP in INII and HMIa; DM warehouse "
        "<1,000 sf Y / >1,000 sf SP (K6a/K6b); N elsewhere incl. INI. Legend Y=permitted, SP=Special "
        "Permit, N=excluded.")
Q_LI = ("K4 'Light manufacturing uses' = Y in INI, INII, HMIa; SP in CG; N elsewhere. K5 'General "
        "industrial uses including manufacturing' = Y in INII, HMIa; N elsewhere. §III-C/G.1/G.2 "
        "(HM-II/HM-III/HPU) allow research-and-development / craft by site plan.")
Q_LGC = ("No named vehicle garage-condo principal use; §III-G.2 HPU 'surface or indoor storage and "
         "parking of motor vehicles' is accessory parking, not a leased/owned garage-condo -> lgc "
         "prohibited in every district (§III-A.1.a closed list).")


def cite(*qs):
    return [{"quote": q, "section": "III-A.1 / III-B..G", "ordinance": ORD} for q in qs]


N_INII = ("ss/mw CONDITIONAL (GROUNDED): self-storage -> K6 Warehouse = SP (Special Permit) here. li "
          "PERMITTED: K4 Light manufacturing + K5 General industrial = Y (by-right). lgc PROHIBITED: no "
          "named garage-condo use.")
N_HMIa = ("ss/mw CONDITIONAL (GROUNDED): self-storage -> K6 Warehouse = SP here. li PERMITTED: K4/K5 = Y "
          "(by-right). lgc PROHIBITED.")
N_DM = ("ss/mw CONDITIONAL (GROUNDED): self-storage -> K6 Warehouse; DM allows <1,000 sf Y / >1,000 sf "
        "SP (a self-storage facility is >1,000 sf -> Special Permit). li PROHIBITED (K4/K5 = N in DM). "
        "lgc PROHIBITED.")
N_INI = ("ss/mw PROHIBITED: K6 Warehouse = N in INI (closed list; self-storage is warehousing). li "
         "PERMITTED (GROUNDED): K4 Light manufacturing = Y (by-right). lgc PROHIBITED.")
N_CG = ("ss/mw PROHIBITED: K6 Warehouse = N in CG. li CONDITIONAL: K4 Light manufacturing = SP (Special "
        "Permit). lgc PROHIBITED.")
N_HMX = ("ss/mw PROHIBITED: §III-C/G HM-II/HM-III/HPU name office/R&D/retail but NO warehouse or "
         "self-storage use (closed list). li CONDITIONAL: research-and-development / craft allowed by "
         "site plan. lgc PROHIBITED.")
N_COMPROHIB = ("All prohibited. K6 Warehouse = N and K4/K5 industrial = N in this commercial/PCD/AP "
               "district; self-storage unnamed -> prohibited (closed list); no named garage-condo use.")
N_RES = ("All prohibited. Residential district: K6 Warehouse, K4/K5 industrial = N; self-storage "
         "unnamed -> prohibited (closed list); no named garage-condo use.")

# parcel_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("RSA","Residential Single A","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RSB","Residential Single B","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RSC","Residential Single C","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RSG","Residential Single G","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RG","Residential General","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RM","Residential Multi","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RESGEN","Residence General","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("RESG","Residence General","prohibited","prohibited","prohibited","prohibited",0.86,N_RES),
    ("RESGE","Residence General","prohibited","prohibited","prohibited","prohibited",0.84,N_RES),
    ("RESM","Residence Multi","prohibited","prohibited","prohibited","prohibited",0.84,N_RES),
    ("CII","Commercial II","prohibited","prohibited","prohibited","prohibited",0.86,N_COMPROHIB),
    ("COM II","Commercial II","prohibited","prohibited","prohibited","prohibited",0.82,N_COMPROHIB),
    ("CG","Commercial General","prohibited","prohibited","conditional","prohibited",0.82,N_CG),
    ("COMM","Commercial General","prohibited","prohibited","conditional","prohibited",0.78,N_CG),
    ("COM","Commercial General","prohibited","prohibited","conditional","prohibited",0.76,N_CG),
    ("C","Commercial General","prohibited","prohibited","conditional","prohibited",0.74,N_CG),
    ("DM","Downtown Mixed Use","conditional","conditional","prohibited","prohibited",0.80,N_DM),
    ("DMU","Downtown Mixed Use","conditional","conditional","prohibited","prohibited",0.78,N_DM),
    ("INI","Industrial I","prohibited","prohibited","permitted","prohibited",0.86,N_INI),
    ("IND 1","Industrial I","prohibited","prohibited","permitted","prohibited",0.80,N_INI),
    ("INII","Industrial II","conditional","conditional","permitted","prohibited",0.86,N_INII),
    ("LC","Local Commercial","prohibited","prohibited","prohibited","prohibited",0.84,N_COMPROHIB),
    ("PCD","Planned Commercial Development","prohibited","prohibited","prohibited","prohibited",0.82,N_COMPROHIB),
    ("AP","AP District","prohibited","prohibited","prohibited","prohibited",0.80,N_COMPROHIB),
    ("HM-I","Highway Mixed Use-I","conditional","conditional","permitted","prohibited",0.80,N_HMIa),
    ("HM-II","Highway Mixed Use-II","prohibited","prohibited","conditional","prohibited",0.80,N_HMX),
    ("HM-III","Highway Mixed Use-III","prohibited","prohibited","conditional","prohibited",0.80,N_HMX),
    ("HPU","Highway Planned Use","prohibited","prohibited","conditional","prohibited",0.80,N_HMX),
]

VERDICTS = [{
    "zone_code": pc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
    "confidence": conf, "notes": note,
} for pc, zn, ss, mw, li, lgc, conf, note in _R]

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
            print(f"  {r['zone_code']:8} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
