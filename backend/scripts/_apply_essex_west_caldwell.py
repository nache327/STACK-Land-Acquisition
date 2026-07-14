"""West Caldwell Township NJ (Essex Co) — Stage-4 grounding (2026-07-14). NEEDLE = M-1 (conditional).

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'West Caldwell township' (exact
parcels.city). Source: Township of West Caldwell NJ Code Ch. 20 Zoning (eCode360 WE0897, full chapter
via print?guid=35367190).

#38 RESOLVED (Tarrytown trap avoided): M-1 = "LIMITED MANUFACTURING DISTRICT" (§20-13), M-2 = "LIMITED
INDUSTRY AND RESEARCH LABORATORY DISTRICT" (§20-14) — both INDUSTRIAL, NOT Multifamily. (B-1 is the
"Special Business AND Multi-Family Residence District" — a business zone, 0 wealth-ring industrial.)

NJ SELF-STORAGE CATCH: (a) GLOBAL CLOSED LIST §20-20 "Any use not specifically permitted in a zone
district established by this chapter is specifically prohibited for that district"; (b) self-storage is a
NAMED use CONFINED to M-1 — §20-13.3.c lists "Self-Storage Facilities" as a CONDITIONAL use, and §20-17.27
(Ord. 1802-2017) states "Self-Storage facilities shall be permitted as a conditional use in the M-1
Limited Manufacturing District ONLY." So M-1 ss/mw = CONDITIONAL; M-2 (and all others) ss = prohibited
despite M-2's limited-industry uses. Warehousing in M-1/M-2 is ACCESSORY-only (own products, §20-13.2/
20-14.2) — not a principal warehouse-by-right, so the convention is moot; self-storage is explicitly
conditional anyway. NEEDLE (wealth-ring ≥1.5ac): M-1 = 57. M-2 = 21 li-armed (NOT ss).

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_essex_west_caldwell.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "67541a18-c599-423b-bf05-d68153af1e2f"
MUNI = "West Caldwell township"
CITED = "§ 20-13.3.c + § 20-17.27 (M-1 ss conditional, M-1-only); § 20-13.1 / § 20-14.1 (li); § 20-20 (closed list)"
ORD = "Township of West Caldwell, NJ Code Ch. 20 Zoning (eCode360 WE0897)"

Q_SS_M1 = ("§ 20-13.3 Conditional Uses (M-1 Limited Manufacturing): 'c. Self-Storage Facilities, subject "
           "to the applicable standards of § 20-17.' § 20-17.27 (Ord. 1802-2017): 'Self-Storage facilities "
           "shall be permitted as a conditional use in the M-1 Limited Manufacturing District only...'")
Q_LI_M1 = ("§ 20-13.1 Permitted Principal Uses (M-1): 'a. Light manufacturing, fabrication, processing and "
           "handling of products and/or materials; research, scientific and medical institutions and "
           "laboratories.'")
Q_LI_M2 = ("§ 20-14.1 Permitted Principal Uses (M-2 Limited Industry and Research Laboratory): 'a. Offices "
           "for executive, professional, scientific, engineering or administrative purposes; and b. "
           "Scientific, engineering or research laboratories devoted to research, design or processing and "
           "fabricating incidental thereto; and limited industry.'")
Q_CLOSED = ("§ 20-20 Prohibited Uses: 'Any use not specifically permitted in a zone district established by "
            "this chapter is specifically prohibited for that district.' → self-storage (conditional, M-1 "
            "ONLY per § 20-17.27) is prohibited in M-2/B/OP/OS/residential; no named vehicle garage-condo "
            "use → lgc prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 20", "ordinance": ORD} for q in qs]


N_M1 = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): § 20-13.3.c + § 20-17.27 self-storage is a conditional use in "
        "the M-1 Limited Manufacturing District ONLY. li PERMITTED: § 20-13.1a light manufacturing/"
        "fabrication/processing by-right. lgc PROHIBITED (no named garage-condo use).")
N_M2 = ("ss/mw PROHIBITED: § 20-17.27 confines self-storage to M-1 ONLY; § 20-20 closes the list — M-2's "
        "limited-industry uses + accessory-only storage (§20-14.2, own products) do NOT ground self-storage. "
        "li PERMITTED (GROUNDED): § 20-14.1b research/design/processing + limited industry. lgc PROHIBITED.")
N_B1 = ("All prohibited. B-1 Special Business and Multi-Family Residence District (§ 20-10): retail/office/"
        "multi-family residence; no self-storage/warehouse/manufacturing principal use (§ 20-20 closed list).")
N_B2 = "All prohibited. B-2 Planned Shopping Center District (§ 20-11): retail center; no industrial/self-storage use."
N_B3 = ("All prohibited. B-3 General Business District (§ 20-12.1): retail sale/display/rental, office and "
        "professional buildings, restaurants only; no self-storage/warehouse/manufacturing (§ 20-20 closed list).")
N_OP = ("All prohibited. OP Office and Professional Building District (§ 20-15.1): offices 'which do not "
        "involve the storage, handling or distribution of products, goods or merchandise on the premises'; "
        "banks; professional offices. No self-storage/warehouse.")
N_OS = "All prohibited. OS Open Space District (§ 20-16): open space/recreation; no self-storage/industrial use."
N_RES = "All prohibited. Single-Family Residence District: no self-storage/warehouse/manufacturing use (§ 20-20 closed list); no named garage-condo use."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("M-1","M-1 Limited Manufacturing","conditional","conditional","permitted","prohibited",0.92,N_M1),
    ("M-2","M-2 Limited Industry and Research Laboratory","prohibited","prohibited","permitted","prohibited",0.90,N_M2),
    ("B-1","B-1 Special Business and Multi-Family Residence","prohibited","prohibited","prohibited","prohibited",0.86,N_B1),
    ("B-2","B-2 Planned Shopping Center","prohibited","prohibited","prohibited","prohibited",0.86,N_B2),
    ("B-3","B-3 General Business","prohibited","prohibited","prohibited","prohibited",0.88,N_B3),
    ("OP","OP Office and Professional Building","prohibited","prohibited","prohibited","prohibited",0.88,N_OP),
    ("OS","OS Open Space","prohibited","prohibited","prohibited","prohibited",0.88,N_OS),
    ("R-2","R-2 Single-Family Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3","R-3 Single-Family Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3A","R-3A Single-Family Residence and Cluster","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-4","R-4 Single-Family Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RA","RA Residence","prohibited","prohibited","prohibited","prohibited",0.85,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_M1, Q_LI_M1, Q_LI_M2, Q_CLOSED), "cited_subsection": CITED,
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
    con = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
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
