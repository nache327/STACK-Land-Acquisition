"""Fulton GA (Phase-5 South) — ground Sandy Springs + Atlanta-Buckhead per-city jids.
SLCo per-city model (each city jid holds its own zoning). Ring-precompute run per-city.
Self-storage NAMED explicitly in both cities' codes (form-based / Atlanta term-specific):

 SANDY SPRINGS (Development Code Art. 7, Div. 7.2 Allowed Use Table; Ord. 2023-12-23 re-enact,
   amended Ord. 2025-09-22). "Self-service storage, mini-warehouse" (Sec. 7.6.7.C) is a NAMED use:
   P by-right in IX- and CC-; C (conditional use permit) in CX- and NEX-; not permitted elsewhere.
   General warehouse/distribution + light industrial P only in IX-. Closed list Sec. 7.1.1.C / 7.1.3.
 ATLANTA-BUCKHEAD (Land Development Code Part 16; Municode Supp.105, Ord. Z-2026-10). District-specific
   storage terms (§16-29.001): I-1 §16-16.003(20) "self-storage facilities" + warehousing/distribution
   by-right; C-3 §16-13.003(21) "secured-storage facility" by-right; O-I §16-10.003(20)-(21)
   "secured-storage" + "mixed-use storage facility" by-right. C-1/C-2 only vault-storage (NOT self-storage).
   SPI-9/SPI-12 (Buckhead Village/Lenox) permit NO storage (closed lists). SPI-15 (Lindbergh) SA1 Miami
   Circle permits "Warehouse, storage facilities and wholesaling" <=15,000 sf by-right -> warehouse
   convention. 500-ft BeltLine-corridor exclusion is a parcel-level caveat (noted; Buckhead is north of
   the BeltLine and existing facilities are grandfathered).

Idempotent human-UPSERT, muni-scoped, verbatim citations (#37), gated to every parcel code, #42 print.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_fulton_ga_south.py
"""
import asyncio, json, asyncpg

SS_JID = "b49ac34f-6394-47ba-87e3-149b6ae0d706"   # Sandy Springs, GA
BH_JID = "a5d68bcd-ce4b-446a-aefb-23613e6f9013"   # Atlanta-Buckhead, GA
SS_CITY = "Sandy Springs"
BH_CITY = "Buckhead"

SS_ORD = "City of Sandy Springs Development Code Art. 7 Use Provisions (Ord. 2023-12-23; use table amended Ord. 2025-09-22)"
Q_SS_TABLE = ("Div. 7.2 Allowed Use Table, row 'Self-service storage, mini-warehouse' (Sec. 7.6.7.C): "
              "P in IX- and CC-; C (conditional use permit) in CX- and NEX-; '—' elsewhere. Definition "
              "7.6.7.C.1: 'Facilities providing separate storage areas for personal or business use...'")
Q_SS_IX = ("IX- Industrial Mixed Use: 'General warehouse and distribution' (Sec. 7.6.7.A) = P and 'Light "
           "Industrial/Manufacturing' (Sec. 7.6.3) = P (IX only).")
Q_SS_CLOSED = ("Sec. 7.1.1.C: 'No building or lot may be used except for a purpose permitted in the "
               "district'; Sec. 7.1.3: 'A principal use not specifically listed is prohibited.'")

BH_ORD = "City of Atlanta Land Development Code Part 16 Zoning (Municode Supp.105; through Ord. Z-2026-10, 3-16-2026)"
Q_BH_I1 = ("§16-16.003 (I-1 Light Industrial) principal uses: (8) 'Manufacturing, wholesaling... "
           "processing...'; (20) 'Warehousing, self-storage facilities, distribution centers...' "
           "(by-right; 500-ft BeltLine-corridor exclusion, existing facilities may redevelop).")
Q_BH_C3 = ("§16-13.003(21) (C-3 Commercial Residential): 'Secured-storage facility...' by-right. "
           "SECURED-STORAGE FACILITY (§16-29.001(75)) = enclosed climate-controlled self-storage units "
           "<=400 sf leased to the public. (500-ft BeltLine caveat.)")
Q_BH_OI = ("§16-10.003(20)-(21) (O-I Office-Institutional): 'Secured-storage facility' + 'Mixed-use "
           "storage facility' by-right. (500-ft BeltLine caveat.)")
Q_BH_VAULT = ("C-1 §16-11.003(26) / C-2 §16-12.003(30): only 'Vault-storage facility <=7,500 sf' (rental "
              "of small vaults for valuables) — NOT a self-storage use; secured-storage NOT in the C-2 "
              "permitted-principal closed list. Each list opens 'used only for the following...'.")
Q_BH_SPI = ("SPI-9 (Buckhead Village) §16-18I.007(4) & SPI-12 (Buckhead/Lenox) §16-18L.006 closed lists "
            "permit NO storage/warehouse in any subarea. SPI-15 (Lindbergh) SA1 Miami Circle "
            "§16-18O.028(6)(a)(ii): 'Warehouse, storage facilities and wholesaling limited to no more "
            "than 15,000 square feet' by-right; SA9 expressly prohibits storage units.")


def cite(ord_, *qs):
    return [{"quote": q, "section": "Zoning", "ordinance": ord_} for q in qs]


def rows_sandy_springs(codes):
    C_TBL = cite(SS_ORD, Q_SS_TABLE, Q_SS_CLOSED)
    C_IX = cite(SS_ORD, Q_SS_TABLE, Q_SS_IX, Q_SS_CLOSED)
    C_CL = cite(SS_ORD, Q_SS_TABLE, Q_SS_CLOSED)
    N_IX = "ss/mw PERMITTED (GROUNDED): Div. 7.2 self-service storage/mini-warehouse = P by-right in IX-. li PERMITTED (warehouse/distribution + light industrial P in IX- only). lgc PROHIBITED."
    N_CC = "ss/mw PERMITTED (GROUNDED): Div. 7.2 self-service storage/mini-warehouse = P by-right in CC-. li PROHIBITED (warehouse/LI not P in CC-). lgc PROHIBITED."
    N_CX = "ss/mw CONDITIONAL (GROUNDED): Div. 7.2 self-service storage/mini-warehouse = C (conditional use permit) in CX-. li PROHIBITED. lgc PROHIBITED."
    N_NEX = "ss/mw CONDITIONAL (GROUNDED): Div. 7.2 self-service storage/mini-warehouse = C (CUP) in NEX-. li PROHIBITED. lgc PROHIBITED."
    N_P = "Self-service storage = '—' (not permitted) in this transect district (Div. 7.2); Sec. 7.1.3 closed list."
    out = []
    for zc in codes:
        p = zc.split("-")[0]
        if p == "IX":
            out.append((zc, "IX Industrial Mixed Use", "permitted", "permitted", "permitted", "prohibited", 0.92, N_IX, C_IX))
        elif p == "CC":
            out.append((zc, "CC Corridor/Node Commercial", "permitted", "permitted", "prohibited", "prohibited", 0.90, N_CC, C_TBL))
        elif p == "CX":
            out.append((zc, "CX Commercial Mixed Use", "conditional", "conditional", "prohibited", "prohibited", 0.88, N_CX, C_TBL))
        elif p == "NEX":
            out.append((zc, "NEX Neighborhood Mixed Use", "conditional", "conditional", "prohibited", "prohibited", 0.85, N_NEX, C_TBL))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_P, C_CL))
    return SS_CITY, out


def rows_buckhead(codes):
    C_I1 = cite(BH_ORD, Q_BH_I1)
    C_C3 = cite(BH_ORD, Q_BH_C3)
    C_OI = cite(BH_ORD, Q_BH_OI)
    C_V = cite(BH_ORD, Q_BH_VAULT)
    C_SPI = cite(BH_ORD, Q_BH_SPI)
    N_I1 = "ss/mw PERMITTED (GROUNDED): §16-16.003(20) 'self-storage facilities' by-right; warehousing/distribution by-right. li PERMITTED. lgc PROHIBITED. (500-ft BeltLine-corridor parcels excluded; existing may redevelop.)"
    N_C3 = "ss/mw PERMITTED (GROUNDED): §16-13.003(21) 'secured-storage facility' (climate-controlled self-storage) by-right. li PROHIBITED (no warehouse/mfg named). lgc PROHIBITED. (500-ft BeltLine caveat.)"
    N_OI = "ss/mw PERMITTED (GROUNDED): §16-10.003(20)-(21) 'secured-storage' + 'mixed-use storage facility' by-right. li PROHIBITED. lgc PROHIBITED. (500-ft BeltLine caveat.)"
    N_SA1 = "ss/mw CONDITIONAL (GROUNDED): SPI-15 SA1 Miami Circle §16-18O.028(6) 'Warehouse, storage facilities and wholesaling <=15,000 sf' by-right (>15k = SUP) -> warehouse convention. li PERMITTED. lgc PROHIBITED."
    N_VAULT = "ss/mw PROHIBITED: C-1/C-2 permit only 'vault-storage facility <=7,500 sf' (valuables vault, not self-storage); secured-storage not in the permitted-principal closed list. li PROHIBITED. lgc PROHIBITED."
    N_SPI_P = "ss/mw PROHIBITED: SPI-9/SPI-12 (Buckhead Village/Lenox) closed-list tables permit no storage/warehouse in any subarea; SPI-15 SA2-8 permit only vault-storage / SA9 prohibits storage. lgc PROHIBITED."
    N_RES = "All prohibited: residential/mixed-residential district; no storage/warehouse use (closed list)."
    out = []
    for zc in codes:
        base = zc.split("-C")[0] if zc.endswith("-C") else zc
        if zc in ("I-1", "I-2"):
            out.append((zc, "I-1 Light Industrial", "permitted", "permitted", "permitted", "prohibited", 0.90, N_I1, C_I1))
        elif zc in ("C-3", "C-3-C"):
            out.append((zc, "C-3 Commercial Residential", "permitted", "permitted", "prohibited", "prohibited", 0.88, N_C3, C_C3))
        elif zc in ("O-I", "O-I-C"):
            out.append((zc, "O-I Office-Institutional", "permitted", "permitted", "prohibited", "prohibited", 0.90, N_OI, C_OI))
        elif zc == "SPI-15 SA1":
            out.append((zc, "SPI-15 SA1 Lindbergh Miami Circle Commercial", "conditional", "conditional", "permitted", "prohibited", 0.80, N_SA1, C_SPI))
        elif zc in ("C-1", "C-1-C", "C-2", "C-2-C"):
            out.append((zc, "C-1/C-2 Commercial (vault-storage only)", "prohibited", "prohibited", "prohibited", "prohibited", 0.82, N_VAULT, C_V))
        elif zc.startswith("SPI-"):
            out.append((zc, f"{zc} (Buckhead/Lindbergh Special Public Interest)", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_SPI_P, C_SPI))
        else:
            out.append((zc, zc, "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES, C_SPI))
    return BH_CITY, out


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
        for jid, (city, builder) in [(SS_JID, (SS_CITY, rows_sandy_springs)), (BH_JID, (BH_CITY, rows_buckhead))]:
            codes = [r["zoning_code"] for r in await con.fetch(
                "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND zoning_code IS NOT NULL ORDER BY zoning_code", jid)]
            muni, rows = builder(codes)
            for zc, zn, ss, mw, li, lgc, conf, note, cits in rows:
                await con.execute(SQL, jid, zc, zn, muni, ss, mw, li, lgc, json.dumps(cits), "Zoning", conf, note)
            got = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
                light_industrial::text li, luxury_garage_condo::text lgc, confidence
                FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
                ORDER BY zone_code""", jid, muni)
            openz = [r['zone_code'] for r in got if r['ss'] in ('permitted', 'conditional')]
            print(f"\n#42 {muni} [{jid}]: {len(got)} rows; ss-open = {openz or '(none)'}")
            for r in got:
                if r['ss'] in ('permitted', 'conditional'):
                    print(f"  {r['zone_code']:12} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} c={r['confidence']} <==")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
