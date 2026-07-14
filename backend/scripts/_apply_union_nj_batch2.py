"""Union County NJ — Batch-2 grounding (Session D). 4 newly-bound wealthy-industrial towns.

All parcels bound via UCNJ GIS County Zoning layer (scripts/_bind_union_nj_zoning.py, county-wide
replace=false). NJ self-storage catch order per town (#37 verbatim / #57 affirmative / #58 sweep;
Berkeley-Heights-vs-New-Providence rule: "warehouse(ing)" named permitted-by-right => convention;
"wholesale business" != warehouse => no convention):

  CLARK — self-storage EXPLICITLY named permitted principal use in BOTH industrial districts:
    CI §195-136.1B(21) "Self-storage facility." + limited manufacturing (18) -> ss/mw/li PERMITTED.
    LCI §195-136.2B(19) "Self-storage facility." (no manufacturing) -> ss/mw PERMITTED, li prohibited.
    Global closed list §195-116A. Warehouse NOT named (self-storage named outright, no convention needed).
  MOUNTAINSIDE — L-I: self-storage EXPLICITLY named CONDITIONAL: §1004 "Public warehousing and
    self-storage facilities are permitted as a conditional use in the L-I Zone" (proximity/height/lot
    standards). "warehousing"+industry/manufacturing are named primary uses §1013(a). -> ss/mw
    CONDITIONAL, li PERMITTED. O-B offices only (§1014 re-prohibits warehouses+mfg) -> prohibited.
    Global closed list §1003. LI/AH = L-I base + AH overlay (same base uses). GIS "I-40" (2 lots) is not
    a Mountainside ordinance district -> conservative.
  SPRINGFIELD (Union Co, 07081) — I-20/I-40 General Industrial share one use column; principal use #8
    "Non-nuisance industry including processing, fabricating, assembly, manufacturing, packaging and
    WAREHOUSING" -> warehousing by-right => ss/mw CONDITIONAL, li PERMITTED. Self-storage NOT named;
    closed list §35-4.4a. H-C names only "Wholesale business" (#6) != warehouse -> prohibited. G-C/O/N-C
    no warehouse -> prohibited.
  CRANFORD — Ch.255 research-office-industrial districts C-1/C-2/C-3. C-1 & C-2: "Warehouses" = PPU
    (§255-36D) -> warehouse by-right => ss/mw CONDITIONAL, li PERMITTED. GIS "ORD-1" (Office Research,
    Distribution) has no current code letter; best-maps to ordinance C-3 "Office distribution centers"=PPU
    (warehousing/distribution) -> ss/mw CONDITIONAL (inferential mapping, conf 0.72). Self-storage NOT
    named (parking-ratio only). Closed list §255-32B. O-1/O-2/ORC = offices, no warehouse -> prohibited.

Idempotent human-UPSERT (Boonton template), muni-scoped (#33), verbatim citations (#37), gated to every
parcel code (Bedminster lesson), verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_union_nj_batch2.py
"""
import asyncio, json, asyncpg

JID = "16dc5ad9-8211-47c6-bfad-93bf588b15e4"  # Union County, NJ

CLARK_ORD = "Township of Clark, NJ Code Ch. 195 Land Use & Development (eCode360 CL2905; zoning amended 12-16-2024)"
Q_CL_CI = ("§195-136.1B (CI Commercial Industrial): 'only the following uses shall be permitted: ... (18) "
           "Limited manufacturing as defined herein. ... (21) Self-storage facility.' LIMITED MFG = "
           "'fabrication, processing or assembly of goods and materials, or the storage of bulk goods...'")
Q_CL_LCI = ("§195-136.2B (LCI Limited Commercial Industrial): 'only the following uses shall be permitted: "
            "... (19) Self-storage facility,' (no manufacturing/warehouse use listed).")
Q_CL_CLOSED = ("§195-116A: 'No structure shall be... used... other than those included among the uses "
               "hereafter listed as permitted in the district'; SELF-STORAGE FACILITY defined §Art.XX.")

MTN_ORD = "Borough of Mountainside, NJ Municipal Code Art. 10 Zoning (mountainside.municipalcodeonline.com; amended Ord. 1340-2025, 4-22-2025)"
Q_MTN_LI = ("§1004: 'Public warehousing and self-storage facilities are permitted as a conditional use in "
            "the L-I Zone' (height/lot/half-mile-proximity standards). §1013(a) primary uses incl. "
            "'warehousing and limited industrial and manufacturing, fabrication and assembly uses'.")
Q_MTN_OB = ("§1014 (O-B Office Building): primary uses = 'business, executive, professional or research "
            "offices or laboratories'; §1014(b) prohibits Section 1011(b)(7) warehouses & (9) mfg. No "
            "storage/warehouse/self-storage use.")
Q_MTN_CLOSED = "§1003: 'Any use which is not expressly permitted shall be considered a prohibited use.'"

SPR_ORD = "Township of Springfield (Union Co, 07081), NJ Code Ch. 35 Land Use (eCode360 SP1128; Appendix A Supp 7, Jan 2026)"
Q_SPR_I = ("Appendix A §35-14 (I-20 & I-40 General Industrial, shared column) principal uses: '(4) "
           "Wholesale business ... (8) Non-nuisance industry including processing, fabricating, assembly, "
           "manufacturing, packaging and warehousing ...' -> warehousing by-right.")
Q_SPR_CLOSED = ("§35-4.4a: 'Any use not expressly permitted in this chapter is prohibited.' Self-storage/"
                "mini-warehouse named nowhere; warehousing named permitted-by-right in I-20/I-40 only.")
Q_SPR_COMM = ("G-C/O/N-C: retail/office, no warehouse. H-C (§35-14) names '(6) Wholesale business' but NOT "
              "warehouse -> wholesale != warehouse-by-right, convention does not attach; §35-4.4a prohibits.")

CRA_ORD = "Township of Cranford, NJ Code Ch. 255 Land Development (eCode360 CR1142; use tbl amended Ord. 2023-08)"
Q_CRA_C = ("§255-36D (Research-office-industrial C-1/C-2/C-3): 'Warehouses PPU PPU' (permitted principal "
           "use in C-1 & C-2); 'Industrial and manufacturing uses PPU PPU'; 'Office distribution centers "
           "... PPU' (C-3). -> warehouse/distribution by-right.")
Q_CRA_ORD1 = ("GIS 'ORD-1' (Office Research, Distribution) has no current Ch.255 code letter; best maps to "
              "ordinance C-3 'Office distribution centers'=PPU (def: 'warehousing and distribution of "
              "goods'). Inferential #38 mapping; all C-1/C-2/C-3 permit warehouse/distribution by-right.")
Q_CRA_CLOSED = ("§255-32B: 'no use... shall be permitted... which is not listed as a permitted, accessory "
                "or conditional use.' Self-storage appears only as a parking ratio (§255-44), not a use.")
Q_CRA_OFF = ("§255-36C (Office districts O-1/O-2/ORC/NC): offices, data processing, research laboratories; "
             "NO warehouse/distribution/industrial/self-storage use -> §255-32B prohibits.")


def cite(ord_, *qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ord_} for q in qs]


def rows_clark():
    C_CI = cite(CLARK_ORD, Q_CL_CI, Q_CL_CLOSED)
    C_LCI = cite(CLARK_ORD, Q_CL_LCI, Q_CL_CLOSED)
    C_CL = cite(CLARK_ORD, Q_CL_CLOSED)
    N_CI = "ss/mw PERMITTED (GROUNDED): §195-136.1B(21) 'Self-storage facility' named permitted principal use. li PERMITTED: (18) limited manufacturing. lgc PROHIBITED."
    N_LCI = "ss/mw PERMITTED (GROUNDED): §195-136.2B(19) 'Self-storage facility' named permitted. li PROHIBITED (no manufacturing/warehouse listed). lgc PROHIBITED."
    N_P = "No self-storage/warehouse/manufacturing named; §195-116A closed list (self-storage named only in CI/LCI)."
    N_COR = "(COR) Corporate Office Research Overlay: office/research; no self-storage/warehouse named -> prohibited (§195-116A)."
    R = [("CI", "CI Commercial Industrial District", "permitted", "permitted", "permitted", "prohibited", 0.90, N_CI, C_CI),
         ("LCI", "LCI Limited Commercial Industrial District", "permitted", "permitted", "prohibited", "prohibited", 0.88, N_LCI, C_LCI),
         ("(COR)", "Corporate Office Research Overlay District", "prohibited", "prohibited", "prohibited", "prohibited", 0.65, N_COR, C_CL)]
    for zc, zn in [("(R-SH)", "Age Restricted/Senior Housing Overlay"), ("CG", "General Commercial"),
                   ("CN", "Neighborhood Service Commercial"), ("CO", "Commercial Office"),
                   ("COH", "Commercial Office Multistory"), ("DTV", "Downtown Village"), ("GC", "Golf Course"),
                   ("O", "Conservation District"), ("P", "Public District"), ("R-100", "One-Family Residential"),
                   ("R-150", "One-Family Residential"), ("R-60", "One-Family Residential"),
                   ("R-75", "One-Family Residential"), ("R-A", "Multiple-Family Apartment Residential"),
                   ("R-B", "Multiple-Family Residential"), ("R-TH", "Residential Townhouse")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_CL))
    return "Clark township", R


def rows_mtn():
    C_LI = cite(MTN_ORD, Q_MTN_LI, Q_MTN_CLOSED)
    C_OB = cite(MTN_ORD, Q_MTN_OB, Q_MTN_CLOSED)
    C_CL = cite(MTN_ORD, Q_MTN_CLOSED)
    N_LI = "ss/mw CONDITIONAL (GROUNDED): §1004 'Public warehousing and self-storage facilities... permitted as a conditional use in the L-I Zone'. li PERMITTED: §1013(a) warehousing + limited industrial/manufacturing. lgc PROHIBITED."
    N_LIAH = "L-I base district + AH affordable-housing overlay (base L-I uses apply): ss/mw CONDITIONAL (§1004), li PERMITTED. lgc PROHIBITED."
    N_OB = "O-B Office Building: offices/laboratories only; §1014(b) expressly prohibits warehouses (1011(b)(7)) & manufacturing (1011(b)(9)). All prohibited."
    N_P = "No warehouse/self-storage use; §1003 closed list (self-storage conditional only in L-I §1004)."
    N_I40 = "#38: GIS 'I-40' is NOT a Mountainside ordinance district (7-district schedule §1001 has no I-40); conservative-prohibited pending map reconcile. 2 lots, 0 wealth+acre."
    R = [("LI", "L-I Limited Industrial District", "conditional", "conditional", "permitted", "prohibited", 0.90, N_LI, C_LI),
         ("LI/AH", "L-I Limited Industrial + Affordable Housing overlay", "conditional", "conditional", "permitted", "prohibited", 0.85, N_LIAH, C_LI),
         ("O-B", "O-B Office Building District", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_OB, C_OB),
         ("O-B/AH", "O-B Office Building + Affordable Housing overlay", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OB, C_OB),
         ("I-40", "GIS I-40 (not a Mountainside ordinance district)", "prohibited", "prohibited", "prohibited", "prohibited", 0.60, N_I40, C_CL)]
    for zc, zn in [("B", "B Business District"), ("H", "H Hospital Zone"), ("R-1", "R-1 Single-Family Residence"),
                   ("R-2", "R-2 Single-Family Residence"), ("R-2/AH", "R-2 + Affordable Housing overlay"),
                   ("R-3", "R-3 Single-Family Residence"), ("RS-16", "RS-16 Residential"), ("RS-40", "RS-40 Residential")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_CL))
    return "Mountainside borough", R


def rows_spr():
    C_I = cite(SPR_ORD, Q_SPR_I, Q_SPR_CLOSED)
    C_COMM = cite(SPR_ORD, Q_SPR_COMM, Q_SPR_CLOSED)
    C_CL = cite(SPR_ORD, Q_SPR_CLOSED)
    N_I = "ss/mw CONDITIONAL (GROUNDED): Appendix A §35-14 I-20/I-40 principal use #8 'Non-nuisance industry including... warehousing' by-right => warehouse convention. li PERMITTED (manufacturing/industry). lgc PROHIBITED."
    N_COMM = "Commercial/office: no warehouse by-right (H-C names 'Wholesale business' only, != warehouse). All prohibited (§35-4.4a)."
    N_P = "No warehouse/self-storage/industrial use; §35-4.4a closed list."
    R = [("I-20", "I-20 General Industrial", "conditional", "conditional", "permitted", "prohibited", 0.85, N_I, C_I),
         ("I-40", "I-40 General Industrial", "conditional", "conditional", "permitted", "prohibited", 0.85, N_I, C_I),
         ("G-C", "General Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COMM, C_COMM),
         ("H-C", "Highway Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COMM, C_COMM),
         ("N-C", "Neighborhood Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COMM, C_COMM),
         ("O", "Offices", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COMM, C_COMM)]
    for zc, zn in [("AH-17", "Affordable Housing"), ("AH-18", "Affordable Housing"), ("AH-24.2", "Affordable Housing"),
                   ("AH-7/RCA", "Affordable Housing/RCA"), ("AH-SC", "Affordable Housing"), ("M-R", "Multi-Family Residential"),
                   ("OS-GU", "Open Space-Government Use"), ("PUD", "Planned Unit Development"), ("R-10", "Residential"),
                   ("S-120", "Single-Family Residential"), ("S-60", "Single-Family Residential"), ("S-75", "Single-Family Residential")]:
        conf = 0.70 if zc == "PUD" else 0.85
        note = "PUD Planned Unit Development: conservative-prohibited pending §35-15.3 plan text; §35-4.4a." if zc == "PUD" else N_P
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", conf, note, C_CL))
    return "Springfield township", R


def rows_cra():
    C_C = cite(CRA_ORD, Q_CRA_C, Q_CRA_CLOSED)
    C_ORD1 = cite(CRA_ORD, Q_CRA_ORD1, Q_CRA_C, Q_CRA_CLOSED)
    C_OFF = cite(CRA_ORD, Q_CRA_OFF, Q_CRA_CLOSED)
    C_CL = cite(CRA_ORD, Q_CRA_CLOSED)
    N_C = "ss/mw CONDITIONAL (GROUNDED): §255-36D 'Warehouses'=PPU (permitted principal use) in C-1/C-2 => warehouse convention. li PERMITTED ('Industrial and manufacturing uses'=PPU). lgc PROHIBITED."
    N_ORD1 = "ss/mw CONDITIONAL (GROUNDED, inferential #38): GIS 'ORD-1'=ordinance C-3 'Office distribution centers'=PPU (warehousing/distribution) => warehouse convention. li PERMITTED (limited assembly). lgc PROHIBITED. Confirm ORD-1->C-3 vs adopted map legend."
    N_OFF = "Office district (O-1/O-2/ORC): offices/data-processing/research labs; no warehouse/distribution/self-storage -> prohibited (§255-32B)."
    N_P = "No warehouse/distribution/self-storage use; §255-32B closed list."
    R = [("C-1", "Commercial-1 (Research-office-industrial)", "conditional", "conditional", "permitted", "prohibited", 0.85, N_C, C_C),
         ("C-2", "Commercial-2 (Research-office-industrial)", "conditional", "conditional", "permitted", "prohibited", 0.85, N_C, C_C),
         ("ORD-1", "Office Research, Distribution (GIS) = ordinance C-3", "conditional", "conditional", "permitted", "prohibited", 0.72, N_ORD1, C_ORD1),
         ("O-1", "O-1 Low-Density Office Building", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OFF, C_OFF),
         ("O-2", "O-2 Medium-Density Office Building", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OFF, C_OFF),
         ("ORC", "Office Residential Character", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OFF, C_OFF)]
    for zc, zn in [("D-B", "Downtown Business"), ("D-C", "Downtown Core"), ("D-T", "Downtown Transition"),
                   ("E-1", "Education District"), ("IMR", "Inclusionary Multifamily Residence"),
                   ("NC", "Neighborhood Commercial"), ("P-1", "Public Use District"), ("PF", "Public Facility"),
                   ("R-1", "R-1 Residence"), ("R-2", "R-2 Residence"), ("R-3", "R-3 Residence"), ("R-4", "R-4 Residence"),
                   ("R-5", "R-5 Residence"), ("R-6", "R-6 Townhouse Residence"), ("R-7", "R-7 Garden Apartment"),
                   ("R-8", "R-8 Apartment Residence"), ("R-A", "R-A Residence"), ("R-ARR", "Age-Restricted Redevelopment"),
                   ("R-B", "R-B Residence"), ("R-CC", "Cranford Crossing Redevelopment"), ("R-R", "Riverfront Redevelopment"),
                   ("R-SC-1", "Senior Citizens Apartment Residence"), ("R-WG", "Western Gateway Rehabilitation"),
                   ("VC", "Village Commercial")]:
        R.append((zc, zn, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_CL))
    return "Cranford township", R


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
        for muni, rows in [rows_clark(), rows_mtn(), rows_spr(), rows_cra()]:
            for zc, zn, ss, mw, li, lgc, conf, note, cits in rows:
                await con.execute(SQL, JID, zc, zn, muni, ss, mw, li, lgc,
                                  json.dumps(cits), "Zoning", conf, note)
            got = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, luxury_garage_condo::text lgc, confidence
                FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
                ORDER BY zone_code""", JID, muni)
            openz = [r['zone_code'] for r in got if r['ss'] in ('permitted', 'conditional')]
            print(f"\n#42 {muni}: {len(got)} rows; ss-open = {openz or '(none)'}")
            for r in got:
                flag = " <== ss-open" if r['ss'] in ('permitted', 'conditional') else ""
                print(f"  {r['zone_code']:9} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} c={r['confidence']}{flag}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
