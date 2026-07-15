"""Phase-5 Denver (South) — ground Greenwood Village + Highlands Ranch per-city jids (SLCo model).
Ring-precompute run per-city.

 GREENWOOD VILLAGE (Muni Code Ch.16 Land Development Code; Municode, through Ord.3 3-2-2026). Closed
   list §16-1-10(b)(2): "If a use of property is not expressly permitted... it is prohibited." Self-storage
   is EXPLICITLY named in EXACTLY ONE district — B-3 Community Business, as a SPECIAL USE (§16-16-30(2)
   "Warehouses and self-storage facilities"). Per named-confinement + closed list (Boonton precedent), the
   warehouse-by-right in T.C. does NOT bump self-storage elsewhere — the town deliberately placed
   self-storage in B-3 only. So B-3 = ss/mw CONDITIONAL (SUP); T.C./L-I = li-permitted no-op for storage;
   M-C = li-conditional (light-assembly SUP). #38: O-1/O-2 = OPEN SPACE (not Office); M-C = Mixed
   Commercial (not Metro Center).
   - T.C. §16-19-20(1): "warehousing and storage of any commodity when enclosed within a building" by-right
     -> li PERMITTED (warehousing is a by-right USE), but self-storage confined to B-3 -> ss/mw prohibited.
   - L-I §16-20-20: "Light industrial facilities" + "Wholesale businesses" by-right; "Distribution
     facilities" is SUP; warehouse only in intent/definitions -> li PERMITTED, ss/mw prohibited.
 HIGHLANDS RANCH (Douglas County Zoning Resolution + HR Planned Development Guide). GI (§1402.01->LI
   §1302.16 "Mini warehouse" + §1302.30 "Warehouse") + C (§1202.03 "Mini warehouse") = self-storage
   by-right -> ss/mw PERMITTED. PD (30,689 parcels) = INDETERMINATE: self-storage/warehousing permitted
   by-right ONLY in HR Industrial Park Planning Areas (PA 75-78,80,81,84-88; "Service Industry" def #101
   folds in warehousing+self-storage) but the bare "PD" code does NOT encode the Planning Area -> grounded
   PROHIBITED (conservative; grounding PD=permitted would falsely arm ~30k mostly-residential parcels).
   ESCALATED: the HR Industrial Park PAs are a real self-storage home that needs PA-level parcel mapping.

Idempotent human-UPSERT, muni-scoped, verbatim citations (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_denver_co_south.py
"""
import asyncio, json, asyncpg

GV_JID = "9fd6996b-a4c3-4433-a737-9c705bff92ed"   # Greenwood Village, CO
HR_JID = "524b1948-f806-4007-b7e3-6ef7219c2b2c"   # Highlands Ranch, CO
GV_CITY = "Greenwood Village"
HR_CITY = "Highlands Ranch"

GV_ORD = "City of Greenwood Village, CO Municipal Code Ch.16 Land Development Code (Municode; through Ord.3, 3-2-2026)"
Q_GV_B3 = ("§16-16-30(2) (B-3 Community Business, Special Uses): 'Warehouses and self-storage facilities' "
           "— self-storage EXPLICITLY named, Special Use Permit (conditional track). SELF-STORAGE FACILITY "
           "def §16-1-100: 'separate, individual and private storage spaces... individually leased.'")
Q_GV_CLOSED = ("§16-1-10(b)(2): 'If a use of property is not expressly permitted pursuant to this Chapter, "
               "it is prohibited.' Self-storage is named ONLY in B-3 -> confined there (Boonton rule): "
               "warehouse-by-right in T.C./L-I does NOT bump self-storage elsewhere.")
Q_GV_TC = ("T.C. §16-19-20(1): 'Offices, including... warehousing and storage of any commodity when "
           "enclosed within a building...' by-right -> warehousing is a by-right USE (li permitted). "
           "Self-storage not named in T.C. -> confined to B-3 -> ss/mw prohibited.")
Q_GV_LI = ("L-I §16-20-20 by-right: 'Light industrial facilities'; 'Wholesale businesses'. 'Distribution "
           "facilities' = Special Use §16-20-30(3). Warehouse appears only in intent/definitions. Self-"
           "storage not named -> ss/mw prohibited; li permitted.")
Q_GV_MC = ("M-C Mixed Commercial §16-18-20/30: office/retail/hotel by-right; 'Light assembly and "
           "manufacturing' + 'Wholesale businesses' = Special Uses. No warehouse/self-storage named.")

HR_ORD = "Douglas County, CO Zoning Resolution + Highlands Ranch Planned Development Guide"
Q_HR_GI = ("GI §1402.01 adopts all LI principal uses; LI §1302.16 'Mini warehouse' + §1302.30 'Warehouse' "
           "+ §1302.21 'Product distribution/storage' by-right (Site Improvement Plan). Mini-warehouse is "
           "the self-storage term of art.")
Q_HR_C = ("C (Commercial) §1202.03: 'Mini warehouse' permitted by-right (Site Improvement Plan). §1201 "
          "intent lists 'mini warehouses'.")
Q_HR_PD = ("PD (DCZR §15) is procedural — uses defined by the approved Development Plan. The Highlands Ranch "
           "PD Guide permits self-storage/warehousing by-right ('Service Industry' def #101; Industrial "
           "Park Sections X-A/X-B) ONLY in Industrial Park Planning Areas 75-78/80/81/84-88. The bare 'PD' "
           "code does NOT encode the Planning Area -> self-storage indeterminate at parcel level; §206 "
           "closed list. Grounded prohibited pending PA-level mapping (escalated).")


def cite(ord_, *qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ord_} for q in qs]


def rows_greenwood(codes):
    C_B3 = cite(GV_ORD, Q_GV_B3, Q_GV_CLOSED)
    C_TC = cite(GV_ORD, Q_GV_TC, Q_GV_CLOSED)
    C_LI = cite(GV_ORD, Q_GV_LI, Q_GV_CLOSED)
    C_MC = cite(GV_ORD, Q_GV_MC, Q_GV_CLOSED)
    C_CL = cite(GV_ORD, Q_GV_CLOSED)
    N_B3 = "ss/mw CONDITIONAL (GROUNDED): §16-16-30(2) 'Warehouses and self-storage facilities' = Special Use (SUP). self-storage EXPLICITLY named. li PROHIBITED (business district; no mfg by-right). lgc PROHIBITED."
    N_TC = "ss/mw PROHIBITED: self-storage named only in B-3 (§16-1-10(b)(2) closed list; Boonton named-confinement). li PERMITTED: §16-19-20(1) 'warehousing and storage of any commodity when enclosed within a building' by-right. lgc PROHIBITED."
    N_LI = "ss/mw PROHIBITED: self-storage confined to B-3 (closed list); distribution is SUP, warehouse only definitional. li PERMITTED: 'Light industrial facilities' by-right §16-20-20. lgc PROHIBITED."
    N_MC = "ss/mw PROHIBITED: no warehouse/self-storage named (self-storage confined to B-3). li CONDITIONAL: 'Light assembly and manufacturing' = Special Use §16-18-30(5). lgc PROHIBITED."
    N_OS = "#38: O-1/O-2 = OPEN SPACE district (not Office). No storage/warehouse use. All prohibited."
    N_P = "No self-storage/warehouse named; §16-1-10(b)(2) closed list (self-storage confined to B-3). All prohibited."
    out = []
    for zc in codes:
        base = zc.replace(" PUD", "")
        if base == "B-3":
            out.append((zc, "B-3 Community Business" + (" (PUD)" if "PUD" in zc else ""), "conditional", "conditional", "prohibited", "prohibited", 0.85, N_B3, C_B3))
        elif base == "T.C.":
            out.append((zc, "Town Center", "prohibited", "prohibited", "permitted", "prohibited", 0.85, N_TC, C_TC))
        elif base == "L-I":
            out.append((zc, "Light Industrial", "prohibited", "prohibited", "permitted", "prohibited", 0.85, N_LI, C_LI))
        elif base == "M-C":
            out.append((zc, "Mixed Commercial", "prohibited", "prohibited", "conditional", "prohibited", 0.82, N_MC, C_MC))
        elif base in ("O-1", "O-2"):
            out.append((zc, f"{base} Open Space (#38 not Office)", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OS, C_CL))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85 if zc != "Unknown" else 0.60, N_P, C_CL))
    return GV_CITY, out


def rows_highlands(codes):
    C_GI = cite(HR_ORD, Q_HR_GI)
    C_C = cite(HR_ORD, Q_HR_C)
    C_PD = cite(HR_ORD, Q_HR_PD)
    C_CL = cite(HR_ORD, Q_HR_PD)
    N_GI = "ss/mw PERMITTED (GROUNDED): GI adopts LI uses (§1402.01); §1302.16 'Mini warehouse' + §1302.30 'Warehouse' by-right. li PERMITTED. lgc PROHIBITED."
    N_C = "ss/mw PERMITTED (GROUNDED): §1202.03 'Mini warehouse' by-right. li PROHIBITED (commercial; no mfg). lgc PROHIBITED."
    N_PD = "ss/mw PROHIBITED (INDETERMINATE, escalated): self-storage permitted by-right ONLY in HR Industrial Park PAs 75-78/80/81/84-88; bare 'PD' code cannot identify the Planning Area -> conservative prohibited pending PA-level parcel mapping (grounding PD=permitted would falsely arm ~30k mostly-residential parcels). lgc PROHIBITED."
    N_P = "Residential/agricultural/other; no storage/warehouse use (§206 closed list). All prohibited."
    out = []
    for zc in codes:
        if zc == "GI":
            out.append((zc, "GI General Industrial", "permitted", "permitted", "permitted", "prohibited", 0.88, N_GI, C_GI))
        elif zc == "C":
            out.append((zc, "C Commercial", "permitted", "permitted", "prohibited", "prohibited", 0.85, N_C, C_C))
        elif zc == "PD":
            out.append((zc, "PD Planned Development (HR PD Guide; indeterminate)", "prohibited", "prohibited", "prohibited", "prohibited", 0.60, N_PD, C_PD))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_CL))
    return HR_CITY, out


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
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for jid, builder in [(GV_JID, rows_greenwood), (HR_JID, rows_highlands)]:
            codes = [r["zoning_code"] for r in await con.fetch(
                "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL ORDER BY zoning_code", jid)]
            muni, rows = builder(codes)
            for zc, zn, ss, mw, li, lgc, conf, note, cits in rows:
                await con.execute(SQL, jid, zc, zn, muni, ss, mw, li, lgc, json.dumps(cits), "Zoning", conf, note)
            got = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, confidence FROM zone_use_matrix
                WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code""", jid, muni)
            openz = [r['zone_code'] for r in got if r['ss'] in ('permitted', 'conditional')]
            print(f"\n#42 {muni} [{jid}]: {len(got)} rows; ss-open = {openz or '(none)'}")
            for r in got:
                if r['ss'] in ('permitted', 'conditional') or r['li'] != 'prohibited':
                    print(f"  {r['zone_code']:10} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} c={r['confidence']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
