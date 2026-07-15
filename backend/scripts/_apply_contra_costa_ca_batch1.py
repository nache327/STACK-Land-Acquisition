"""Contra Costa County CA — Batch-1 grounding (Phase-5). County jid; SLCo-style per-city verdicts
(muni-scoped via parcels.city, mixed-case EXACT). County-scale ring-precompute complete (100%).

Cities grounded this batch (cleanly researched): Walnut Creek, Pleasant Hill, Danville, Concord, and the
UNINCORPORATED county areas (county Zoning Ordinance Title 8/Div 84). Other incorporated cities
(Martinez, Oakley, Richmond, Antioch, Pittsburg, Hercules, Pinole, San Pablo, El Cerrito, Moraga,
Lafayette, Orinda, San Ramon, Brentwood-CA, Clayton) are HANDED BACK for per-city research (see _exceptions_D).

#38 disambiguations (all confirmed from ordinance text):
 - CA "M-##" codes = MULTIPLE-FAMILY RESIDENTIAL (density du/acre), NOT Manufacturing — Walnut Creek
   (M1/M3/M15/M25 = M-1/M-3/M-1.5/M-2.5), Danville (M-8/13/20/30), county (M-6/9/12/17/29). -> prohibited.
 - County T-1 = Mobile Home Park (residential), F-1 = Water Recreational, S = R-40 (residential),
   W-3 = Controlled HEAVY Industrial (not water). -> T-1/F-1/S residential/rec = prohibited.

Self-storage findings (named-confinement respected; warehouse-by-right convention only where self-storage
is NOT separately named):
 - WALNUT CREEK: self-storage = "Mini-Storage", named P in SC (by-right) + CUP in B-P-100/B-P-200. Confined
   there -> SC permitted, BP100/BP200 conditional; all else (incl. M multifamily, OC/CR/CF) prohibited.
 - PLEASANT HILL: self-storage NOT named; "Warehousing and storage"+"Wholesaling, distribution" by-right
   (P) in LI + C -> warehouse convention -> LI/C ss/mw conditional. Else prohibited.
 - DANVILLE: self-storage NOT named; C names "warehouses" by-right (conditional) but ~0 in-ring; L-I permits
   warehouse only via CUP (conditional-warehouse -> NO convention) -> L-I ss/mw prohibited, li permitted;
   M-## multifamily prohibited; DBD prohibited. Near-no-op.
 - CONCORD: self-storage = "Self-Storage Facility, Mini-Storage" named UP (conditional) in OBP/IBP/IMX/HI/SC
   (and the county-style L-I/H-I on Concord parcels = Concord light/heavy industrial -> conditional);
   explicit "-" (prohibited) in WMX/CMX/CO/NC/RC/DMX/DP. C-M/C (county-style) warehouse-by-right ->
   conditional. [Ch.18.50 OBP/IBP/IMX/HI cells from a 2016 snapshot -> conf 0.78; SC current 0.85.]
 - UNINCORPORATED COUNTY: self-storage named nowhere; C-M ("Storage warehouses" 84-56.402(J)) + C
   ("warehouses" 84-54.402) + L-I (general industrial) warehouse by-right -> ss/mw conditional, li permitted;
   H-I/W-3 name manufacturing only (warehouse not clearly by-right) -> ss/mw prohibited, li permitted.

Idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37), gated to every parcel code, #42 print.
Combining-district suffixes (" -CE/-X/-BS/-SG/-FH/-UE/-T/-TOV -K/-S-2") are overlays -> classified by BASE code.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_contra_costa_ca_batch1.py
"""
import asyncio, json, asyncpg

JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"  # Contra Costa County, CA

WC_ORD = "City of Walnut Creek, CA Municipal Code Title 10 Ch.10-2 Zoning (current 2025)"
PH_ORD = "City of Pleasant Hill, CA Title 18 Zoning (Ord. 978, adopted 11-17-2025; Table 18.25-A)"
DV_ORD = "Town of Danville, CA Municipal Code Ch. XXXII Zoning (current 2026 S-18)"
CO_ORD = "City of Concord, CA Development Code Title 18 (Ch.18.40 Ord.25-6 2025; Ch.18.50 through Ord.15-5 2015)"
CC_ORD = "Contra Costa County, CA Ordinance Code Title 8 Div.84 Zoning (Municode Supp.103, Ord.2026-04)"

C_WC_SC = [{"quote": "Mini-Storage = P (permitted by right) in S-C Service Commercial (§10-2.2.1102); 'Land uses not listed are not permitted.'", "section": "Ch.10-2", "ordinance": WC_ORD}]
C_WC_BP = [{"quote": "Mini-Storage = L(8) = Conditional Use Permit in B-P Business Park (§10-2.2.1202, 6 findings incl. 300/500 ft setbacks).", "section": "Ch.10-2", "ordinance": WC_ORD}]
C_WC_P = [{"quote": "Self-storage ('Mini-Storage') is named ONLY in S-C (P) and B-P (CUP); 'Land uses not listed are not permitted.' M-1..M-3 = Multiple-Family Residential (not manufacturing).", "section": "Ch.10-2", "ordinance": WC_ORD}]
C_PH = [{"quote": "'Warehousing and storage, limited' = P and 'Wholesaling, distribution and storage' = P in C and LI (Table 18.25-A); self-storage not named -> warehouse-by-right convention. Closed list §18.210.010.", "section": "Title 18", "ordinance": PH_ORD}]
C_PH_P = [{"quote": "No self-storage/warehouse use permitted; §18.210.010 'Use classifications not listed are prohibited.' MR* = Multiple Residential (residential).", "section": "Title 18", "ordinance": PH_ORD}]
C_DV_LI = [{"quote": "L-I §32-62: general industrial uses by-right; 'warehouses' (C-district use) allowed only via land use permit §32-62.2.b (conditional-warehouse -> no self-storage convention). Self-storage not named.", "section": "Ch.XXXII", "ordinance": DV_ORD}]
C_DV_C = [{"quote": "§32-61.2.a.1: 'All types of wholesale businesses, warehouses...' by-right in C -> warehouse convention. Self-storage not named.", "section": "Ch.XXXII", "ordinance": DV_ORD}]
C_DV_P = [{"quote": "No self-storage/warehouse by-right; §32-1.3 permissive/closed-list. M-8/13/20/30 = Multiple Family Residential (§32-27); DBD downtown no storage.", "section": "Ch.XXXII", "ordinance": DV_ORD}]
C_CO_IND = [{"quote": "'Self-Storage Facility, Mini-Storage' = UP (Use Permit/conditional) in OBP/IBP/IMX/HI (Table 18.50.020) and SC (Table 18.40); Warehouse+Wholesaling/Distribution = ZC by-right. [18.50 cells per 2016 snapshot, Ord.15-5.]", "section": "Title 18", "ordinance": CO_ORD}]
C_CO_WMX = [{"quote": "WMX West Concord Mixed-Use: self-storage = '-' Not Allowed (explicit) despite Warehouse/Wholesaling = ZC by-right; §18.20.010 closed list -> self-storage prohibited, warehouse li permitted.", "section": "Title 18", "ordinance": CO_ORD}]
C_CO_P = [{"quote": "Self-storage = '-' (Not Allowed) in CO/CMX/NC/RC/DMX/DP; §18.20.010 'Any use that cannot be determined to fit... is not permitted.' M-29 = Multiple Family Residential.", "section": "Title 18", "ordinance": CO_ORD}]
C_CC_LI = [{"quote": "L-I Light Industrial (Ch.84-58) general industrial by-right; C-M (84-56.402(J)) 'Storage warehouses' by-right; C (84-54.402) 'warehouses' by-right -> warehouse-by-right convention. Self-storage named nowhere in Title 8.", "section": "Div.84", "ordinance": CC_ORD}]
C_CC_HI = [{"quote": "H-I Heavy Industrial (84-62) / W-3 Controlled Heavy Industrial (84-60): manufacturing by-right; warehouse/self-storage not named by-right (W-3 routes non-mfg via land use permit) -> ss/mw conservative-prohibited, li permitted.", "section": "Div.84", "ordinance": CC_ORD}]
C_CC_P = [{"quote": "No self-storage/warehouse by-right. M-6/9/12/17/29 = Multiple Family Residential; T-1 = Mobile Home Park; F-1 = Water Recreational; S = R-40; A-* = Agricultural (all residential/ag). Permissive closed-list zoning.", "section": "Div.84", "ordinance": CC_ORD}]

N_PERM = "ss/mw PERMITTED (GROUNDED, named)."
N_COND = "ss/mw CONDITIONAL (GROUNDED)."
N_PROH = "prohibited."


def base(code):
    return (code or "").split(" ")[0].strip()


def classify(city, code):
    """Return (ss, mw, li, lgc, conf, note, cites) for a (city, zoning_code)."""
    b = base(code)
    WC = {"SC": ("permitted", "permitted", "conditional", "prohibited", 0.88, "ss/mw PERMITTED: Mini-Storage = P by-right in S-C. li conditional (Limited Industry CUP).", C_WC_SC),
          "BP100": ("conditional", "conditional", "conditional", "prohibited", 0.85, "ss/mw CONDITIONAL: Mini-Storage = CUP in B-P-100 (L(8)).", C_WC_BP),
          "BP200": ("conditional", "conditional", "conditional", "prohibited", 0.85, "ss/mw CONDITIONAL: Mini-Storage = CUP in B-P-200 (L(8)).", C_WC_BP)}
    PH = {"LI": ("conditional", "conditional", "permitted", "prohibited", 0.85, "ss/mw CONDITIONAL: warehouse/distribution by-right in LI -> convention. li permitted.", C_PH),
          "C": ("conditional", "conditional", "permitted", "prohibited", 0.82, "ss/mw CONDITIONAL: warehouse/distribution by-right in C -> convention. li permitted.", C_PH)}
    DV = {"L-1": ("prohibited", "prohibited", "permitted", "prohibited", 0.80, "ss/mw PROHIBITED: L-I warehouse only via CUP (no convention); self-storage not named. li permitted.", C_DV_LI),
          "L-I": ("prohibited", "prohibited", "permitted", "prohibited", 0.80, "ss/mw PROHIBITED: L-I warehouse only via CUP; self-storage not named. li permitted.", C_DV_LI),
          "C-M": ("conditional", "conditional", "permitted", "prohibited", 0.70, "ss/mw CONDITIONAL: controlled-manufacturing, warehouse by-right -> convention. li permitted.", C_DV_C)}
    CO_IND = ("conditional", "conditional", "permitted", "prohibited", 0.78, "ss/mw CONDITIONAL: 'Self-Storage Facility, Mini-Storage' = UP (Use Permit). li permitted. [Ch.18.50 2016 snapshot.]", C_CO_IND)
    CO = {"OBP": CO_IND, "IBP": CO_IND, "IMX": CO_IND, "HI": CO_IND, "H-I": CO_IND, "L-I": CO_IND,
          "SC": ("conditional", "conditional", "permitted", "prohibited", 0.85, "ss/mw CONDITIONAL: Self-Storage = UP in SC (current 2025 table). li permitted.", C_CO_IND),
          "C-M": ("conditional", "conditional", "permitted", "prohibited", 0.72, "ss/mw CONDITIONAL: county-style C-M storage warehouses by-right -> convention. li permitted.", C_CO_IND),
          "C": ("conditional", "conditional", "permitted", "prohibited", 0.72, "ss/mw CONDITIONAL: county-style C warehouses by-right -> convention. li permitted.", C_CO_IND),
          "WMX": ("prohibited", "prohibited", "permitted", "prohibited", 0.82, "ss/mw PROHIBITED: WMX self-storage explicit '-' (not allowed) despite warehouse by-right. li permitted.", C_CO_WMX)}
    CC = {"L-I": ("conditional", "conditional", "permitted", "prohibited", 0.82, "ss/mw CONDITIONAL: L-I general industrial + warehouse by-right (convention). li permitted.", C_CC_LI),
          "C-M": ("conditional", "conditional", "permitted", "prohibited", 0.82, "ss/mw CONDITIONAL: C-M 'Storage warehouses' by-right (§84-56.402(J)). li permitted.", C_CC_LI),
          "C": ("conditional", "conditional", "permitted", "prohibited", 0.80, "ss/mw CONDITIONAL: C 'warehouses' by-right (§84-54.402). li permitted.", C_CC_LI),
          "H-I": ("prohibited", "prohibited", "permitted", "prohibited", 0.75, "ss/mw PROHIBITED: H-I heavy manufacturing by-right; warehouse/self-storage not clearly by-right (conservative). li permitted.", C_CC_HI),
          "W-3": ("prohibited", "prohibited", "permitted", "prohibited", 0.75, "ss/mw PROHIBITED: W-3 Controlled Heavy Industrial; warehouse via land use permit only. li permitted.", C_CC_HI)}

    if city == "Walnut Creek":
        return WC.get(b, ("prohibited", "prohibited", "prohibited", "prohibited", 0.65 if b in ("P-1", "PD", "PUD", "MUPD", "HPD", "SFHPD", "MHD") else 0.85, "prohibited (self-storage confined to S-C/B-P; M=multifamily).", C_WC_P))
    if city == "Pleasant Hill":
        return PH.get(b, ("prohibited", "prohibited", "prohibited", "prohibited", 0.65 if b.startswith(("PUD", "HPUD", "PPD")) else 0.85, "prohibited (no self-storage/warehouse; MR*=residential).", C_PH_P))
    if city == "Danville":
        if b in DV:
            return DV[b]
        return ("prohibited", "prohibited", "prohibited", "prohibited", 0.65 if b.startswith(("P-1", "ZM", "DBD")) else 0.85, "prohibited (M-##=multifamily; DBD/other no storage).", C_DV_P)
    if city == "Concord":
        if b in CO:
            return CO[b]
        return ("prohibited", "prohibited", "prohibited", "prohibited", 0.60 if b in ("U", "PD", "NTS") else 0.85, "prohibited (self-storage '-'; M-29 multifamily; residential/office/public).", C_CO_P)
    # unincorporated county
    if b in CC:
        return CC[b]
    return ("prohibited", "prohibited", "prohibited", "prohibited", 0.65 if b.startswith(("P-1", "SP", "NA", "CMU")) else 0.85, "prohibited (M-##/T-1/F-1/S/A-*/R-* residential-ag-rec; no self-storage/warehouse).", C_CC_P)


UNINC = ["Alamo", "Diablo", "Byron", "Knightsen", "Bethel Island", "Pacheco", "Bay Point",
         "El Sobrante", "Crocket", "Rodeo", "Discovery Bay", "Kensington", "Canyon", "Briones",
         "Port Costa", "Clyde"]
CITIES = ["Walnut Creek", "Pleasant Hill", "Danville", "Concord"] + UNINC
ZNAME = {"SC": "Service Commercial", "BP100": "B-P-100 Business Park", "BP200": "B-P-200 Business Park",
         "LI": "Light/Limited Industrial", "C": "General Commercial", "C-M": "Controlled Manufacturing",
         "L-I": "Light Industrial", "L-1": "L-I Light Industrial", "H-I": "Heavy Industrial",
         "OBP": "Office Business Park", "IBP": "Industrial Business Park", "IMX": "Industrial Mixed-Use",
         "HI": "Heavy Industrial", "WMX": "West Concord Mixed-Use", "W-3": "Controlled Heavy Industrial"}

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
    con = await asyncpg.connect(url, timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        grand_open = 0
        for city in CITIES:
            codes = [r["zoning_code"] for r in await con.fetch(
                "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NOT NULL ORDER BY zoning_code", JID, city)]
            openz = []
            for zc in codes:
                ss, mw, li, lgc, conf, note, cites = classify(city, zc)
                zn = ZNAME.get(base(zc), zc)
                await con.execute(SQL, JID, zc, zn, city, ss, mw, li, lgc, json.dumps(cites), "Zoning", conf, note)
                if ss in ("permitted", "conditional"):
                    openz.append(f"{zc}({ss[:4]})")
            if openz:
                grand_open += len(openz)
                print(f"  {city}: {len(codes)} rows; ss-open = {openz}")
            else:
                print(f"  {city}: {len(codes)} rows; ss-open = (none)")
        print(f"\nTotal ss-open (city,zone) rows: {grand_open}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
