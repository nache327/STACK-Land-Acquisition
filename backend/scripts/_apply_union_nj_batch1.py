"""Union County NJ — Batch-1 grounding (Session D). 4 wealthy-industrial towns.

Stage-1 note: Union parcels had NO zoning binding (no NJTPA layer). Bound first via
scripts/_bind_union_nj_zoning.py (official UCNJ GIS "County Zoning" centroid spatial join).

NJ self-storage catch order applied per town (#37 verbatim / #57 affirmative / #58 closed-list sweep):
  SUMMIT — LI (§35-13.16.B.1.i) EXPLICITLY names "Self-storage facilities" as a permitted principal
    use -> ss PERMITTED. Warehousing of lightweight materials also named (B.1.e). Global closed list
    §35-9.2.A. Self-storage named in EXACTLY ONE zone (LI) per whole-chapter sweep. RO-60/PROD/PROD-2 =
    research-office, no storage/warehouse principal use -> prohibited.
  BERKELEY HEIGHTS — LI (§6.3.6.A.2) names "Warehouses" (defined to include distribution/cold-storage/
    e-commerce) permitted by-right; self-storage NOT named; closed list §6.4.1.H. warehouse-by-right =>
    ss/mw CONDITIONAL (established convention). OR/OR-B = office/research, no warehouse -> prohibited.
    #38: GIS "OR-A" has no current counterpart (former OR-A1 repealed -> MU); grounded conservative.
  NEW PROVIDENCE — GIS "LI" was RENAMED to TBI-2 (Technology & Business Innovation II) in current
    Ch.310 (adopted 11-14-2022, Ord. 2022-15). TBI-2 permits "Light industrial use" (§310-38.B(16)) and
    "Wholesale business" (B(25)) by-right, but NOT "warehouse"/"distribution" (warehouse appears only in
    definitions; Office-Flex def explicitly excludes warehousing). Self-storage NOT named; hard closed
    list §310-13.A. Wholesale-business != warehouse-by-right -> convention does NOT apply -> ss/mw
    PROHIBITED, li PERMITTED. (Reconciled: matrix zone_code 'LI' = parcels' stale GIS code = current TBI-2.)
  SCOTCH PLAINS — Ch.23; whole-chapter sweep: self-storage/mini-warehouse/warehouse/distribution NAMED
    NOWHERE (only "warehouse" text is inside the INFRASTRUCTURE definition; STORAGE BUILDING is a
    secondary/accessory use). Closed list §23-2.3q. M-1/M-2 permit light manufacturing (li PERMITTED) but
    no warehouse by-right -> ss/mw PROHIBITED. B-1A/B-1 office+residential; B-2/B-3 enumerated retail.

Idempotent human-UPSERT (Boonton template), muni-scoped (#33), verbatim citations (#37), verify-and-print
(#42). Gated: every code the parcels carry is grounded (Bedminster lesson).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_union_nj_batch1.py
"""
import asyncio, json, asyncpg

JID = "16dc5ad9-8211-47c6-bfad-93bf588b15e4"  # Union County, NJ

# ---- citation quote banks (verbatim) ----
SUMMIT_ORD = "City of Summit, NJ Code Ch. 35 Development Regulations (eCode360 SU4097; current to 2025)"
Q_SUM_LI = ("§35-13.16.B.1 (LI Light Industrial Zone) permitted principal uses: '...e. Warehousing of "
            "lightweight materials. ... i. Self-storage facilities.' (conditional uses: 'a. None.')")
Q_SUM_CLOSED = "§35-9.2.A: 'Where a use is not specifically permitted in a zone district, it is prohibited.'"
Q_SUM_RO = ("§35-13.19 (RO-60 Research Office): only permitted principal use 'a. Administrative and "
            "professional offices.' §35-13.17/.18 (PROD/PROD-2): research laboratories, 'specifically "
            "excluding the manufacturing, distribution, packaging or fabricating on the premises... for "
            "sale to the general public.' Self-storage/warehouse not listed -> §35-9.2.A prohibits.")

BH_ORD = ("Township of Berkeley Heights, NJ, Appendix A Land Use Ord. Part 6 Zoning (Municode; use lists "
          "amended 12-19-2024 by Ord. No. 33-2023)")
Q_BH_LI = ("§6.3.6.A (LI Light Industrial) permitted principal uses: '1. Light industry. 2. Warehouses. "
           "...' WAREHOUSE def: 'A facility used for the storage and distribution of goods... such as "
           "wholesale and retail distribution centers, cold storage and e-commerce fulfillment "
           "facilities.' Self-storage not named -> warehouse-by-right => ss/mw conditional (convention).")
Q_BH_CLOSED = ("§6.4.1.H: 'in all zones of the Township any uses not specifically permitted in Article 6.3 "
               "herein are prohibited.'")
Q_BH_OR = ("§6.3.5.A (OR/OR-B Office and Research): principal uses = offices, research laboratories "
           "(no materials/finished products manufactured for sale), gov/worship/school/fitness. No "
           "warehouse or self-storage principal use; accessory only 'Storage buildings appropriately "
           "screened from public view.' -> §6.4.1.H prohibits warehouse/self-storage.")

NP_ORD = "Borough of New Providence, NJ Code Ch. 310 Zoning (adopted 11-14-2022 by Ord. No. 2022-15; eCode360 NE1158)"
Q_NP_TBI2 = ("§310-38.B (TBI-2 Technology & Business Innovation Zone II; = the parcels' stale GIS 'LI') "
             "permitted principal uses incl. '(16) Light industrial use' and '(25) Wholesale business'; "
             "only conditional use is wireless telecom. 'Warehouse'/'distribution' NOT a permitted use "
             "(appears only in definitions; OFFICE, FLEX def excludes 'warehousing, distribution, "
             "manufacturing'). LIGHT INDUSTRIAL def = manufacturing/fabricating/assembling in enclosed "
             "buildings.")
Q_NP_CLOSED = ("§310-13.A: 'Any use not designated as a permitted principal use, accessory use or "
               "conditional use is specifically prohibited from any district in the Borough.' "
               "Self-storage/mini-warehouse named nowhere; wholesale-business != warehouse-by-right, so "
               "the warehouse convention does not attach -> ss/mw prohibited.")

SP_ORD = "Township of Scotch Plains, NJ Code Ch. 23 Zoning (eCode360 SC0174; amended through Ord. 2024-11)"
Q_SP_M = ("§23-3.14 (M-1) / §23-3.15 (M-2) Industrial Zones permitted primary uses: office buildings; "
          "research laboratories; '(3) Any light manufacturing, processing, packaging or assembly use...'. "
          "No warehouse/self-storage/distribution use named. M-1 also permits '(4) Contractors' storage "
          "buildings and storage yards' (contractor outdoor storage, not self-storage).")
Q_SP_CLOSED = ("§23-2.3q: 'Any use not specifically permitted in the zoning district... is hereby "
               "specifically prohibited from that district.' Whole-chapter sweep: self-storage/"
               "mini-warehouse/warehouse/distribution named in NO district (only 'warehouse' text is "
               "inside the INFRASTRUCTURE definition). STORAGE BUILDING is defined as a secondary use.")
Q_SP_B = ("§23-3.10 (B-1A Office/Research/Multifamily) & §23-3.9 (B-1): offices, research labs (no mfg "
          "for sale), townhouses/garden apts. §23-3.11 (B-2) enumerated retail/service; §23-3.12 (B-3) = "
          "B-2 uses + cannabis. No warehouse/self-storage/light-manufacturing principal use.")


def cite(ord_, *qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ord_} for q in qs]


# ---- per-town verdicts: (zone_code, zone_name, ss, mw, li, lgc, conf, note, citations) ----
def rows_summit():
    C_LI = cite(SUMMIT_ORD, Q_SUM_LI, Q_SUM_CLOSED)
    C_RO = cite(SUMMIT_ORD, Q_SUM_RO, Q_SUM_CLOSED)
    C_PR = cite(SUMMIT_ORD, Q_SUM_CLOSED)
    N_LI = ("ss/mw PERMITTED (GROUNDED): §35-13.16.B.1.i 'Self-storage facilities' is a named permitted "
            "principal use; B.1.e 'Warehousing of lightweight materials'. li PERMITTED (light "
            "manufacturing). lgc PROHIBITED (no named garage-condo use; §35-9.2.A).")
    N_RO = "RO-60 Research Office: only 'Administrative and professional offices' permitted. All prohibited (§35-9.2.A)."
    N_PR = "PROD/PROD-2 Research Office Dev: research labs; mfg/distribution for public sale excluded. All prohibited."
    N_PROH = "Not permitting self-storage/warehouse (named only in LI per whole-chapter sweep); §35-9.2.A closed list."
    R = [("LI", "LI Light Industrial Zone", "permitted", "permitted", "permitted", "prohibited", 0.90, N_LI, C_LI),
         ("RO60", "RO-60 Research Office Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RO, C_RO),
         ("PROD", "PROD Planned Research Office Dev Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_PR, C_PR),
         ("PROD-2", "PROD-2 Planned Research Office Dev Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_PR, C_PR)]
    for zc, zn in [("B", "B Business"), ("B-1", "B-1 Business"), ("CRBD", "Central Retail Business District"),
                   ("G", "Golf"), ("GW-1", "Gateway-1"), ("GW-2", "Gateway-2"), ("MF", "Multi-Family Residential"),
                   ("MF/TOD", "Multi-Family/Transit Oriented Dev"), ("MFT", "Multi-Family Tower Residential"),
                   ("NB", "Neighborhood Business"), ("ORC", "Office Residential Character"),
                   ("ORC-1", "Office Residential Character-1"), ("PI", "Professional-Institutional"),
                   ("PL", "Public Land"), ("R-5", "R-5 Single & Two-Family Residential"),
                   ("R-6", "R-6 Single-Family Residential"), ("R-10", "R-10 Single-Family Residential"),
                   ("R-15", "R-15 Single-Family Residential"), ("R-25", "R-25 Single-Family Residential"),
                   ("R-43", "R-43 Single-Family Residential"), ("RAH-1", "Affordable Housing"),
                   ("TH-1", "Town House-1"), ("TH-2", "Town House-2")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_PR))
    return "Summit city", R


def rows_bh():
    C_LI = cite(BH_ORD, Q_BH_LI, Q_BH_CLOSED)
    C_OR = cite(BH_ORD, Q_BH_OR, Q_BH_CLOSED)
    C_CL = cite(BH_ORD, Q_BH_CLOSED)
    N_LI = ("ss/mw CONDITIONAL (GROUNDED): §6.3.6.A.2 'Warehouses' permitted by-right (WAREHOUSE def "
            "includes distribution/cold-storage/e-commerce); self-storage unnamed -> warehouse-by-right "
            "convention => ss/mw conditional. li PERMITTED ('1. Light industry'). lgc PROHIBITED.")
    N_OR = "OR/OR-B Office & Research: offices/labs only; no warehouse or self-storage. All prohibited (§6.4.1.H)."
    N_ORA = ("#38: GIS 'OR-A' has no current ordinance district (former OR-A1 repealed -> MU Mixed Use per "
             "Ord. 2-2021). Grounded conservative-prohibited; mixed-use permits no warehouse/self-storage.")
    N_PROH = "Not permitting warehouse/self-storage (named only in LI); §6.4.1.H closed list."
    R = [("LI", "LI Light Industrial Zone", "conditional", "conditional", "permitted", "prohibited", 0.88, N_LI, C_LI),
         ("OR", "OR Office and Research Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_OR, C_OR),
         ("OR-B", "OR-B Office and Research Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_OR, C_OR),
         ("OR-A", "OR-A (repealed -> MU Mixed Use)", "prohibited", "prohibited", "prohibited", "prohibited", 0.65, N_ORA, C_CL)]
    for zc, zn in [("AH-1", "Attached Housing 1"), ("AH-3", "Attached Housing 3"), ("AH-4", "Attached Housing 4"),
                   ("AH-5", "Attached Housing 5"), ("AH-6", "Attached Housing 6"), ("AH-7", "Attached Housing 7"),
                   ("DD", "Downtown Development"), ("DH-12", "Downtown Housing 12"), ("DH-18", "Downtown Housing 18"),
                   ("DH-24", "Downtown Housing 24"), ("DMX", "Downtown Mixed Use"), ("HB-2", "Housing Business 2"),
                   ("HB-3", "Housing Business 3"), ("OL", "Open Land Zone"), ("R-1", "R-1 Residential"),
                   ("R-10", "R-10 Residential"), ("R-15", "R-15 Residential"), ("R-15A", "R-15A Residential"),
                   ("R-20", "R-20 Residential")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_CL))
    return "Berkeley Heights township", R


def rows_np():
    C_TBI = cite(NP_ORD, Q_NP_TBI2, Q_NP_CLOSED)
    C_CL = cite(NP_ORD, Q_NP_CLOSED)
    N_LI = ("ss/mw PROHIBITED: parcels' GIS 'LI' = current TBI-2; §310-38 permits 'Light industrial use' "
            "and 'Wholesale business' by-right but NOT warehouse/distribution -> warehouse convention does "
            "NOT attach; self-storage named nowhere; §310-13.A closed list. li PERMITTED (§310-38.B(16) "
            "Light industrial use). lgc PROHIBITED.")
    N_RL = ("RL 'Research Laboratory' (stale GIS code, not in current Ch.310): research-lab character, no "
            "storage/warehouse use. ss/mw/li prohibited (conservative); §310-13.A. lgc PROHIBITED.")
    N_PROH = "No warehouse/self-storage permitted; §310-13.A closed list (self-storage named nowhere in Ch.310)."
    R = [("LI", "LI (=current TBI-2 Tech & Business Innovation II)", "prohibited", "prohibited", "permitted", "prohibited", 0.88, N_LI, C_TBI),
         ("RL", "RL Research Laboratory (stale GIS code)", "prohibited", "prohibited", "prohibited", "prohibited", 0.70, N_RL, C_CL)]
    for zc, zn in [("A-1", "Affordable Housing 6 u/ac"), ("A-2", "Affordable Housing 10 u/ac"),
                   ("A-3", "Affordable Housing 14 u/ac"), ("C", "Central Commercial"), ("C-1", "Specialty Commercial"),
                   ("C-2", "Neighborhood Commercial"), ("OR", "Office & Residential"), ("R-1", "R-1 Single Family"),
                   ("R-2", "R-2 Single Family"), ("R-3", "R-3 Two Family"), ("R-4", "R-4 Multi Family"),
                   ("R-15", "R-15 Residential"), ("R-S", "Residential Senior"), ("R2A", "Single Family District"),
                   ("R3A", "Single & Two Family District"), ("Rail", "Railroad")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_CL))
    return "New Providence borough", R


def rows_sp():
    C_M = cite(SP_ORD, Q_SP_M, Q_SP_CLOSED)
    C_B = cite(SP_ORD, Q_SP_B, Q_SP_CLOSED)
    C_CL = cite(SP_ORD, Q_SP_CLOSED)
    N_M = ("ss/mw PROHIBITED: no warehouse/self-storage/distribution named in any Scotch Plains district "
           "(whole-chapter sweep); §23-2.3q closed list. li PERMITTED: §23-3.14a(3)/§23-3.15a 'light "
           "manufacturing, processing, packaging or assembly'. lgc PROHIBITED (no garage-condo use).")
    N_B1A = ("B-1A Office/Research/Multifamily: offices + research labs (no mfg for sale) + townhouses/"
             "garden apts. No warehouse/self-storage/light-manufacturing principal use -> all prohibited.")
    N_PROH = "No warehouse/self-storage/light-manufacturing use; §23-2.3q closed list."
    N_RDV = "SCRPD redevelopment plan district; conservative-prohibited pending plan text; §23-2.3q."
    R = [("M-1", "M-1 Industrial Zone", "prohibited", "prohibited", "permitted", "prohibited", 0.90, N_M, C_M),
         ("M-2", "M-2 Industrial Zone", "prohibited", "prohibited", "permitted", "prohibited", 0.90, N_M, C_M),
         ("B-1A", "B-1A Office/Research/Multifamily Residence", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_B1A, C_B),
         ("B-1", "B-1 Office and Multifamily Residence", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_B1A, C_B),
         ("B-2", "B-2 Business Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_B),
         ("B-3", "B-3 Highway Business Zone", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_B),
         ("SCRPD", "Sub-Area C Redevelopment Plan District", "prohibited", "prohibited", "prohibited", "prohibited", 0.70, N_RDV, C_CL)]
    for zc, zn in [("C", "Conservation"), ("ML-2", "Multi-Family Zone"), ("P", "Public"),
                   ("R-1", "R-1 Single Family"), ("R-2", "R-2 Single Family"), ("R-2A", "R-2A Residential"),
                   ("R-2B", "R-2B Residential"), ("R-2C", "R-2C Residential"), ("R-2D", "R-2D Mixed Residence"),
                   ("R-3", "R-3 Single Family"), ("R-3A", "R-3A Single Family"), ("R-3B", "R-3B Broadway/Redevelopment"),
                   ("R-75", "R-75 Residential"), ("SC-1", "Senior Citizen Zone")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_PROH, C_CL))
    return "Scotch Plains township", R


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
        await con.execute("SET statement_timeout='90s'")
        for muni, rows in [rows_summit(), rows_bh(), rows_np(), rows_sp()]:
            for zc, zn, ss, mw, li, lgc, conf, note, cits in rows:
                await con.execute(SQL, JID, zc, zn, muni, ss, mw, li, lgc,
                                  json.dumps(cits), "Zoning", conf, note)
            got = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, luxury_garage_condo::text lgc, confidence
                FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
                ORDER BY zone_code""", JID, muni)
            needles = [r['zone_code'] for r in got if r['ss'] in ('permitted', 'conditional')]
            print(f"\n#42 {muni}: {len(got)} rows applied; ss-open zones = {needles or '(none)'}")
            for r in got:
                flag = " <== ss-open" if r['ss'] in ('permitted', 'conditional') else ""
                print(f"  {r['zone_code']:8} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} c={r['confidence']}{flag}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
