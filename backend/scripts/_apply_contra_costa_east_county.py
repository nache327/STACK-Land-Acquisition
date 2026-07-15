"""Contra Costa CA — East County batch (Session D owns these 5 munis in the shared county jid).
Ring done county-wide; grounded per-city from each city's OWN ordinance (all text-verified).

Self-storage is a NAMED use in every one of these codes; named-confinement + explicit status govern:
 OAKLEY (Title 9): "Mini-storage Facility" = CUP in LI (§9.1.602.c) + Warehouse by-right. #38: M-H = MOBILE
   HOME Residential (§9.1.408), NOT manufacturing -> no-op. -> LI conditional; else prohibited.
 PITTSBURG (Title 18): "Warehousing and storage, limited" (incl. ministorage, §18.08.080(32)) = U (CUP) in
   IP/IL/IG (§18.54.010), confined to industrial. #38: T-1 = COUNTY Mobile Home Park (no Pittsburg T-1
   district) -> no-op. -> IP/IL/IG conditional; else prohibited.
 ANTIOCH (Title 9 Ch.5): "Mini-storage" (§9-5.3803) = P in M-2, U in M-1/MCR/WF; blank (prohibited) in
   C-2/C-3/PBC etc. M-1/M-2 verified industrial (NOT multifamily). WSCD = code NOT in Antioch ordinance
   (escalated). -> M-2 permitted, M-1/MCR/WF conditional; else prohibited.
 PINOLE (Title 17): "Storage, Personal Storage Facility" = P in OIMU (by-right, §17.20.030-1), C in CMU/RC,
   N in OPMU. #38: "H-I"/"H-I -X" are LEGACY pre-2010 codes (folded into OIMU by the 2010 rewrite) ->
   grounded conditional-reconcile (land is now OIMU=self-storage permitted; stale code). -> OIMU permitted,
   CMU conditional, H-I(legacy) conditional; OPMU prohibited; else prohibited.
 HERCULES (Title 13): "Mini-Storage Facility" (§13-60 def) = CUP confined to CG + I. -> CG conditional;
   PO/RD self-storage NOT named (li-only, "Storage Facilities" tied to serving Hercules) -> prohibited; else prohibited.

Cross-city stray annexed COUNTY codes: T-1=Mobile Home / M-9/M-12/M-17=Multiple-Family / F-1=Water Rec /
S=R-40 -> residential prohibited; county H-I (Oakley/Antioch/Pittsburg) = Controlled Heavy Industrial ->
li permitted, ss/mw prohibited (manufacturing named, warehouse not by-right). Overlays (" -X/-CE/-SG/-UE"
space-suffix; Pittsburg trailing "-O") classified by BASE code.

Idempotent human-UPSERT, muni-scoped, verbatim cites (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_contra_costa_east_county.py
"""
import asyncio, json, asyncpg

JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"
CITIES = ["Oakley", "Pittsburg", "Antioch", "Pinole", "Hercules"]

ORD = {
    "Oakley": "City of Oakley, CA Muni Code Title 9 Ch.9.1 Zoning (through Ord. 12-25, 2025)",
    "Pittsburg": "City of Pittsburg, CA Muni Code Title 18 Zoning (eCode360 PI4590)",
    "Antioch": "City of Antioch, CA Muni Code Title 9 Ch.5 Zoning (amlegal, through Ord. 2243-C-S 2024)",
    "Pinole": "City of Pinole, CA Muni Code Title 17 Zoning (amlegal 2026 S-28)",
    "Hercules": "City of Hercules, CA Zoning Ordinance Title 13 (Ord. 515, 2018)",
}
QUOTE = {
    "Oakley": "§9.1.602.c: 'In the LI district... conditional use permit: ...5. Mini-storage Facility'; §9.1.602.b.8 'Warehouse' permitted. §9.1.408 MH = Mobile Home Residential. Self-storage confined to LI.",
    "Pittsburg": "§18.54.010: 'Warehousing and storage, limited' (incl. ministorage, §18.08.080(32)) = U (CUP) in IP/IL/IG; confined to industrial. T-1 = county Mobile Home Park (no Pittsburg T-1 district).",
    "Antioch": "§9-5.3803 'Mini-storage': M-2=P (by-right), M-1/MCR/WF=U (CUP), all commercial (C-2/C-3/PBC)=blank (§9-5.3802(B)(4) not allowed). M-1 Light / M-2 Heavy Industrial.",
    "Pinole": "Table 17.20.030-1 'Storage, Personal Storage Facility': OIMU=P, CMU=C, OPMU=N. §17.20.020 'uses not shown... not permitted.' H-I = legacy pre-2010 (folded into OIMU).",
    "Hercules": "§13-60 def 'Mini-Storage Facility... allowed with a conditional use permit in the general commercial and industrial zoning districts' (CG + I only); §13-8.1 CG Mini-Storage=C. PO/RD self-storage not named.",
}


def cite(city):
    return [{"quote": QUOTE[city], "section": "Zoning", "ordinance": ORD[city]}]


def base(zc):
    b = zc.split(" ")[0].strip()          # strip space-suffix overlays (" -X"/" -CE"/" -SG"/" -UE")
    if b.endswith("-O") and b not in ("H-I",):   # Pittsburg trailing "-O" limited overlay
        b = b[:-2]
    return b


# per-city needle/special code -> (ss, mw, li, lgc, conf, tag)
SPECIAL = {
    "Oakley": {
        "LI": ("conditional", "conditional", "permitted", "prohibited", 0.88, "Mini-storage Facility = CUP (§9.1.602.c) + Warehouse by-right. li permitted."),
        "M-H": ("prohibited", "prohibited", "prohibited", "prohibited", 0.88, "#38 MH = Mobile Home Residential (§9.1.408), not industrial. no-op."),
        "H-I": ("prohibited", "prohibited", "permitted", "prohibited", 0.72, "county Controlled Heavy Industrial (annexed); manufacturing by-right, warehouse/self-storage not by-right. li permitted."),
    },
    "Pittsburg": {
        "IP": ("conditional", "conditional", "permitted", "prohibited", 0.88, "Warehousing-and-storage-limited (ministorage) = U/CUP in IP (§18.54.010). li permitted."),
        "IL": ("conditional", "conditional", "permitted", "prohibited", 0.88, "ministorage = U/CUP in IL. li permitted."),
        "IG": ("conditional", "conditional", "permitted", "prohibited", 0.88, "ministorage = U/CUP in IG; warehousing/mfg by-right. li permitted."),
        "T-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.85, "#38 county Mobile Home/Manufactured Home Park (no Pittsburg T-1 district). no-op."),
        "H-I": ("prohibited", "prohibited", "permitted", "prohibited", 0.72, "county Controlled Heavy Industrial (annexed). li permitted; ss/mw not by-right."),
    },
    "Antioch": {
        "M-2": ("permitted", "permitted", "permitted", "prohibited", 0.88, "Mini-storage = P by-right in M-2 Heavy Industrial (§9-5.3803); Warehousing&wholesaling P. li permitted."),
        "M-1": ("conditional", "conditional", "permitted", "prohibited", 0.88, "Mini-storage = U/CUP in M-1 Light Industrial (§9-5.3803). li permitted."),
        "MCR": ("conditional", "conditional", "prohibited", "prohibited", 0.82, "Mini-storage = U/CUP in MCR Mixed Commercial/Residential. li prohibited."),
        "WF": ("conditional", "conditional", "prohibited", "prohibited", 0.80, "Mini-storage = U/CUP in WF Urban Waterfront. li prohibited."),
        "LI": ("prohibited", "prohibited", "permitted", "prohibited", 0.70, "stray county-style Light Industrial (annexed); Antioch's own industrial is M-1/M-2. li permitted, ss/mw conservative-prohibited."),
        "IG": ("prohibited", "prohibited", "permitted", "prohibited", 0.65, "stray industrial code; conservative li permitted, ss/mw prohibited."),
        "H-I": ("prohibited", "prohibited", "permitted", "prohibited", 0.70, "county Controlled Heavy Industrial (annexed). li permitted."),
        "WSCD": ("prohibited", "prohibited", "prohibited", "prohibited", 0.55, "#38 WSCD NOT a codified Antioch district (not in Title 9 Ch.5) — ESCALATED; conservative prohibited pending base-zoning verification."),
    },
    "Pinole": {
        "OIMU": ("permitted", "permitted", "permitted", "prohibited", 0.90, "Personal Storage Facility = P (by-right) in OIMU (Table 17.20.030-1); Warehouse P. li permitted."),
        "CMU": ("conditional", "conditional", "prohibited", "prohibited", 0.85, "Personal Storage Facility = C (CUP) in CMU. li prohibited (warehouse N)."),
        "OPMU": ("prohibited", "prohibited", "conditional", "prohibited", 0.82, "Personal Storage Facility = N (not allowed) in OPMU; warehouse C. ss/mw prohibited, li conditional."),
        "H-I": ("conditional", "conditional", "permitted", "prohibited", 0.68, "#38 LEGACY pre-2010 code folded into OIMU by 2010 rewrite (self-storage P as OIMU); grounded conditional-reconcile pending rebind to OIMU."),
    },
    "Hercules": {
        "CG": ("conditional", "conditional", "prohibited", "prohibited", 0.85, "Mini-Storage = C (CUP) in CG General Commercial (§13-8.1; def §13-60 confines to CG+I). li prohibited (warehouse accessory-only)."),
        "PO/RD": ("prohibited", "prohibited", "conditional", "prohibited", 0.80, "self-storage NOT named (§13-60 confines to CG/I; PO/RD 'Storage Facilities' must serve Hercules businesses). li conditional (light mfg A). ss/mw prohibited."),
    },
}
# residential/ag/open county-stray codes -> prohibited
CTY_RES = {"T-1", "M-9", "M-12", "M-17", "M-6", "M-29", "F-1", "S"}
PROH_NOTE = "PROHIBITED: no self-storage/warehouse named for this district (closed list / not listed); residential/ag/open/office/commercial or county-stray residential."


def classify(city, zc):
    b = base(zc)
    sp = SPECIAL.get(city, {})
    if b in sp:
        ss, mw, li, lgc, conf, tag = sp[b]
        return ss, mw, li, lgc, conf, tag
    if b in CTY_RES:
        return "prohibited", "prohibited", "prohibited", "prohibited", 0.85, "county-stray residential code (Mobile Home/Multifamily/Water-Rec/R-40). no-op."
    conf = 0.65 if b.startswith(("SP", "S-P", "P-D", "PD", "DTSP", "P-1", "DR", "0", "NA", "HTC")) else 0.85
    return "prohibited", "prohibited", "prohibited", "prohibited", conf, PROH_NOTE


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
        for city in CITIES:
            cits = json.dumps(cite(city))
            codes = [r["zoning_code"] for r in await con.fetch(
                "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NOT NULL ORDER BY zoning_code", JID, city)]
            openz = []
            for zc in codes:
                ss, mw, li, lgc, conf, tag = classify(city, zc)
                await con.execute(SQL, JID, zc, zc, city, ss, mw, li, lgc, cits, "Zoning", conf, tag)
                if ss in ("permitted", "conditional"):
                    openz.append(f"{zc}({ss[:4]})")
            print(f"#42 {city}: {len(codes)} rows; ss-open = {openz or '(none)'}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
