"""Framingham MA — Stage-4 FULL close (2026-07-09). Zero held cells. 19 base districts.

TIER-1 (Rt-9 corridor). Real light-industrial land (M-1 Light Mfg / M General Mfg / TP
Technology Park / CMU) but self-storage is NOT a named use and the bylaw is CLOSED-LIST.

Grounding — City of Framingham Zoning By-Law (Published Aug 2019, amendments through
7/23/2019; framinghamma.gov), §II.A Classes of Districts + §II.B Table of Uses + §II.C:
  CLOSED-LIST (§II.B): "No building, structure, or land shall be used ... for any purpose or
    in any manner other than as permitted as set forth in the Table of Uses or unless
    otherwise authorized by this Zoning By-law." Legend: Y=by-right, N=prohibited,
    SP/SPP/SPZ=special permit (PB / ZBA / either).
  lgc PROHIBITED everywhere (§II.C, named-N, no variance): "Automobile Storage as a principal
    use" and "Vehicle Storage Yard" are "expressly prohibited in all zoning districts." A luxury
    garage-condo = vehicle storage as a principal use -> prohibited citywide.
  li PERMITTED in M-1/M/TP/CMU: 6.A Research, Development & Laboratories = Y (by-right) in all
    four; 6.C Processing, assembly and manufacturing = Y in M/TP/CMU, SPP in M-1.
  li CONDITIONAL in B-2/B-3/B-4/CB/B: 6.A R&D = SP/SPP (special permit); no by-right industrial.
  li PROHIBITED in R-1..R-4/G/B-1/P/PRD/OSR/G-E.
  ss/mw: NO named self-storage/mini-warehouse use anywhere (whole-bylaw scan; the 2018 proposed
    Mini-Warehouse amendment was NOT adopted). Nearest use = 6.M "Storage and distribution
    facility" (parking-code 24 = "warehouse or other storage facility"): Y (by-right) only in TP;
    SPP in M; N elsewhere. Per the warehouse->self_storage convention, by-right warehouse/storage
    -> ss/mw CONDITIONAL (TP only); conditional-warehouse (M = SPP) and distribution-only
    (Wholesale Business by-right in M) do NOT fire the upgrade -> closed-list PROHIBITS ss/mw in
    every other district incl. M/M-1/CMU. (M flagged as the tension district, conf lowered.)

Armed self-storage = TP-conditional only; garage-condo = 0. Executable apply (Dedham template):
idempotent human-UPSERT via asyncpg, muni-scoped (catch #33), verbatim citations (catch #37),
verify-and-print (catch #42). Rebind: MAPC, gates a/b/d PASS after G-E added + HC (overlay) set
nonbinding (the Hudson vocab-vs-bylaw check caught both), 4.9% changed, 3 orphans.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_framingham.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "FRAMINGHAM"
CITED_SUBSECTION = "§II.B Table of Uses 6.A/6.C/6.M + §II.C"
ORD = ("City of Framingham Zoning By-Law (Published August 2019, amendments through July 23, 2019; "
       "framinghamma.gov), §II.A Classes of Districts + §II.B Table of Uses + §II.C Prohibited Uses")

Q_CLOSED = ("§II.B: 'No building, structure, or land shall be used and no building or part thereof or "
            "other structure shall be erected...for any purpose or in any manner other than as permitted "
            "as set forth in the Table of Uses or unless otherwise authorized by this Zoning By-law.' "
            "Legend: Y=permitted as of right; N=prohibited; SP/SPP/SPZ=special permit (PB/ZBA/either).")
Q_LGC = ("§II.C Prohibited Uses: 'the following uses are expressly prohibited in all zoning districts: "
         "...q. Automobile Storage as a principal use; r. Vehicle Storage Yard; s. Truck Terminal... "
         "No use variance shall be granted for any prohibited use set forth in this subsection, within "
         "any zoning district in the Town of Framingham.'")
Q_LI = ("§II.B 6.A 'Research, Development & Laboratories' = Y (by-right) in M-1, M, TP, CMU; SP/SPP in "
        "B-2/B-3/B-4/CB/B; N elsewhere. 6.C 'Processing, assembly and manufacturing' = Y in M, TP, CMU; "
        "SPP in M-1; N elsewhere.")
Q_SS = ("§II.B 6.M 'Storage and distribution facility' (parking code 24 = 'warehouse or other storage "
        "facility') = Y (by-right) in TP; SPP in M; N in all other districts. 6.B 'Wholesale Business' = "
        "Y in M, SPP in M-1/CMU. No self-storage / mini-warehouse is a named use anywhere in the By-Law.")


def cite(*qs):
    return [{"quote": q, "section": "§II", "ordinance": ORD} for q in qs]


N_RES = ("All prohibited. Closed-list (§II.B): only the residential/named uses permitted in this "
         "district; no industrial, warehouse, storage, or manufacturing use is listed. ss/mw: no named "
         "self-storage use + closed-list. li: 6.A/6.C = N. lgc: 'Automobile Storage as a principal use' "
         "expressly prohibited in all districts (§II.C, no variance).")
N_GE = ("Geriatric Care/Elderly Housing District (§II.A.7): permitted uses are elderly housing, geriatric "
        "health-care/nursing-care, and accessory uses only. No storage/warehouse/industrial use -> "
        "ss/mw/li prohibited (closed-list). lgc prohibited (§II.C Automobile Storage as a principal use, "
        "all districts).")
N_BUS_NOLI = ("B-1 Neighborhood Business: closed-list; 6.A R&D = N and no industrial/warehouse use listed "
              "-> li prohibited. ss/mw prohibited (no named self-storage + closed-list). lgc prohibited "
              "(§II.C, all districts).")
N_BUS_LI = ("Business district: li CONDITIONAL — 6.A Research, Development & Laboratories = SP/SPP "
            "(special permit); no by-right industrial. ss/mw prohibited (no named self-storage; 6.M "
            "Storage-and-distribution = N here; closed-list). lgc prohibited (§II.C, all districts).")
N_IND_NOSS = ("Industrial/tech district: li PERMITTED (6.A R&D by-right Y{mfg}). ss/mw PROHIBITED — 6.M "
              "Storage-and-distribution = {sd} here and no named self-storage use exists; the "
              "warehouse->self_storage convention does not fire (by-right warehouse only in TP). Closed-"
              "list prohibits the unnamed self-storage use. lgc prohibited (§II.C Automobile Storage as a "
              "principal use, all districts, no variance).")
N_TP = ("TP Technology Park: li PERMITTED (6.A R&D + 6.C manufacturing by-right Y). ss/mw CONDITIONAL — "
        "6.M 'Storage and distribution facility' = Y (by-right) here (parking code 24 = 'warehouse or "
        "other storage facility'); per the warehouse->self_storage convention a by-right warehouse/"
        "storage use makes self-storage conditional (self-storage is the more specific use). lgc "
        "prohibited (§II.C Automobile Storage as a principal use, all districts, no variance).")

# zone_code, zone_name, ss, mw, li, lgc, confidence, note
_R = [
    ("R-1", "Single Family Residential",              "prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("R-2", "Single Two Family Residential",           "prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("R-3", "Townhouse and Garden Apartment Residential","prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("R-4", "Apartment, other Residential",            "prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("G",   "General Residence",                        "prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("B-1", "Neighborhood Business",                    "prohibited","prohibited","prohibited","prohibited",0.90,N_BUS_NOLI),
    ("B-2", "Community Business",                        "prohibited","prohibited","conditional","prohibited",0.85,N_BUS_LI),
    ("B-3", "General Business",                          "prohibited","prohibited","conditional","prohibited",0.85,N_BUS_LI),
    ("B-4", "Nobscot Village Business",                 "prohibited","prohibited","conditional","prohibited",0.85,N_BUS_LI),
    ("CB",  "Central Business",                          "prohibited","prohibited","conditional","prohibited",0.85,N_BUS_LI),
    ("B",   "Business",                                  "prohibited","prohibited","conditional","prohibited",0.85,N_BUS_LI),
    ("P",   "Office and Professional",                  "prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("PRD", "Planned Reuse District",                   "prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("OSR", "Open Space and Recreation",                "prohibited","prohibited","prohibited","prohibited",0.92,N_RES),
    ("G-E", "Geriatric Care/Elderly Housing",           "prohibited","prohibited","prohibited","prohibited",0.92,N_GE),
    ("M-1", "Light Manufacturing",                      "prohibited","prohibited","permitted","prohibited",0.90,N_IND_NOSS.format(mfg="; 6.C manufacturing SPP",sd="N")),
    ("M",   "General Manufacturing",                    "prohibited","prohibited","permitted","prohibited",0.82,N_IND_NOSS.format(mfg=" + 6.C manufacturing by-right",sd="SPP (conditional-warehouse -> convention does not fire); Wholesale Business by-right is distribution, not self-storage")),
    ("CMU", "Commercial Mixed Use",                     "prohibited","prohibited","permitted","prohibited",0.88,N_IND_NOSS.format(mfg=" + 6.C manufacturing by-right",sd="N")),
    ("TP",  "Technology Park",                           "conditional","conditional","permitted","prohibited",0.75,N_TP),
]

_CITES = {
    N_RES: cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC),
    N_GE: cite(Q_CLOSED, Q_SS, Q_LGC),
    N_BUS_NOLI: cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC),
    N_BUS_LI: cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC),
    N_TP: cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC),
}

VERDICTS = []
for zc, zn, ss, mw, li, lgc, conf, note in _R:
    cites = _CITES.get(note) or cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC)
    VERDICTS.append({"zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
                     "light_industrial": li, "luxury_garage_condo": lgc, "citations": cites,
                     "cited_subsection": CITED_SUBSECTION, "confidence": conf, "notes": note})

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
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
