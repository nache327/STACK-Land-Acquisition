"""Richmond CA (Contra Costa) — ground per-city (batch-2). Codes normalized first
(_normalize_contra_costa_codes.py: "IB Industrial Business"->IB etc.).

Richmond Municipal Code Art. 15.04 (Municode, through Ord.02-26 N.S. 3-3-2026). Self-storage is the
NAMED use "Mini-Storage" (§15.04.104.020: "individual separate spaces... accessible by customers for
storing... personal effects and household goods"). Explicit status per district (Tables 15.04.204.020 /
.203.020 / .202.020); closed list §15.04.*.020 ("classifications not listed... are prohibited"):
  Mini-Storage = C (conditional/CUP) in IB, IL, IG (industrial) + CG (commercial).
  Mini-Storage = x (NOT permitted) in IW, ILL, CR, CC.
  Mini-Storage NOT listed (prohibited) in all CM mixed-use (CM-1..CM-5) incl. CM-5 (its 21 in-ring lots
    are NOT needles) and CR (28 in-ring lots NOT needles) — named-confinement respected.
Indoor Warehousing/Storage = P by-right in IL/IG/IW/ILL, but Mini-Storage is separately named so the
warehouse convention is not needed. li (Limited Industrial) = P in IB/IL/IG.

Idempotent human-UPSERT, muni-scoped, verbatim cites (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_richmond_ca.py
"""
import asyncio, json, asyncpg

JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"
CITY = "Richmond"
ORD = "City of Richmond, CA Municipal Code Art. 15.04 Zoning (Municode; through Ord. 02-26 N.S., 3-3-2026)"


def cite(*qs):
    return [{"quote": q, "section": "Art. 15.04", "ordinance": ORD} for q in qs]


Q_MS = ("MINI-STORAGE (§15.04.104.020) = 'individual separate spaces... accessible by customers for the "
        "storing and retrieval of personal effects and household goods'. Table 15.04.204.020: Mini-Storage "
        "= C in IB/IL/IG; Table 15.04.203.020: = C in CG; = x in IW/CR/CC; not listed in CM (prohibited).")
Q_LI = ("'Limited Industrial' = P by-right in IB/IL/IG; 'Indoor Warehousing and Storage' = P in IL/IG/IW/ILL.")
Q_CL = ("§15.04.204.020/.203.020/.202.020: 'Use classifications... not listed in the table or not found to "
        "be substantially similar... are prohibited.' Mini-Storage confined to IB/IL/IG/CG.")

# code -> (ss, mw, li, lgc, conf, note)
R = {
    "IB": ("conditional", "conditional", "permitted", "prohibited", 0.88, "ss/mw CONDITIONAL (GROUNDED): Mini-Storage = C (CUP) in IB. li PERMITTED (Limited Industrial P). lgc PROHIBITED."),
    "IL": ("conditional", "conditional", "permitted", "prohibited", 0.90, "ss/mw CONDITIONAL (GROUNDED): Mini-Storage = C; purpose §15.04.204.010 names 'warehouses, mini-storage'. li PERMITTED. lgc PROHIBITED."),
    "IG": ("conditional", "conditional", "permitted", "prohibited", 0.85, "ss/mw CONDITIONAL (GROUNDED): Mini-Storage = C (CUP) in IG. li PERMITTED. lgc PROHIBITED."),
    "IW": ("prohibited", "prohibited", "permitted", "prohibited", 0.85, "ss/mw PROHIBITED: Mini-Storage = x in IW. li PERMITTED (Indoor Warehousing P; Limited Industrial L6). lgc PROHIBITED."),
    "ILL": ("prohibited", "prohibited", "permitted", "prohibited", 0.82, "ss/mw PROHIBITED: Mini-Storage = x in ILL. li PERMITTED. lgc PROHIBITED."),
    "IA": ("prohibited", "prohibited", "prohibited", "prohibited", 0.65, "Industrial-Agriculture; Mini-Storage not listed -> prohibited (conservative). lgc PROHIBITED."),
    "CG": ("conditional", "conditional", "prohibited", "prohibited", 0.85, "ss/mw CONDITIONAL (GROUNDED): Mini-Storage = C (CUP) in CG. li PROHIBITED (Limited Industrial x; Artisan L1). lgc PROHIBITED."),
    "CR": ("prohibited", "prohibited", "prohibited", "prohibited", 0.88, "PROHIBITED: Mini-Storage = x in CR (Regional Commercial); all industrial/storage x. (28 in-ring lots = NOT needles.)"),
    "CC": ("prohibited", "prohibited", "prohibited", "prohibited", 0.80, "PROHIBITED: Mini-Storage = L5 (water-related accessory only) in CC Coastal Commercial -> not a standalone self-storage home."),
}
CM_NOTE = "PROHIBITED: CM mixed-use table has no Warehousing/Mini-Storage category -> not listed -> §15.04.202.020 closed list prohibits (CM-5's in-ring lots are NOT needles)."
RES_NOTE = "PROHIBITED: residential/open-space/public/agri/specific-plan; no self-storage or warehouse use (closed list)."


def classify(zc):
    if zc in R:
        return R[zc]
    if zc.startswith("CM-") or zc in ("LW",):
        return ("prohibited", "prohibited", "prohibited", "prohibited", 0.85, CM_NOTE)
    conf = 0.65 if zc.startswith(("SP-", "PA", "P-1")) or zc in ("NA", "__", "TOHIMU", "TOMIMU", "CMU", "IMU") else 0.85
    return ("prohibited", "prohibited", "prohibited", "prohibited", conf, RES_NOTE)


CITS = cite(Q_MS, Q_LI, Q_CL)

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
        codes = [r["zoning_code"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NOT NULL ORDER BY zoning_code", JID, CITY)]
        openz = []
        for zc in codes:
            ss, mw, li, lgc, conf, note = classify(zc)
            await con.execute(SQL, JID, zc, zc, CITY, ss, mw, li, lgc, json.dumps(CITS), "Art. 15.04", conf, note)
            if ss in ("permitted", "conditional"):
                openz.append(f"{zc}({ss[:4]})")
        print(f"#42 {CITY}: {len(codes)} rows; ss-open = {openz}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
