"""Millburn Township NJ (Essex Co) — Stage-4 grounding (2026-07-14). NEEDLE = CMO (conditional, convention).

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'Millburn township' (exact
parcels.city). Source: Township of Millburn NJ Code Art. 6 Zoning Provisions (eCode360 MI4080, full
article via print?guid=35143140).

#38 CATCH: parcel code 'C' = "Conservation-Recreation" (§ DRZ-606.1 — public/water-supply/park land, NOT
commercial) → the 30 wealth-ring 'C' lots are conservation, NOT a needle (Mountain-Lakes pattern). CE =
Conservation-Educational-Cultural; CD = Cultural District; P = Public; OR-1/2/3 = Office Research.

NJ SELF-STORAGE CATCH: self-storage is NAMED NOWHERE in Art. 6 (0 hits). Closed list §DRZ ("All uses not
expressly permitted in this ordinance are prohibited"). ONE district permits warehousing by-right:
  - CMO Commercial/Medical Office §DRZ-606.9 b.2: "Wholesale business, light assembly and manufacturing,
    scientific and other research facilities, warehouses, and offices operated in connection with the
    foregoing uses." → warehouse-by-right + self-storage UNNAMED ⇒ ss/mw CONDITIONAL (convention
    [[feedback_warehouse_conditional_convention]]); li PERMITTED (light assembly/manufacturing).
OR-1/2/3 (office/retail/hotel/multifamily), B-1..B-4 (business/retail), C/CE (conservation), CD (cultural),
P (public), R-* (residential) — none permit warehouse/self-storage/manufacturing → prohibited.
NEEDLE (wealth-ring ≥1.5ac): CMO = 9 (conditional).

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_essex_millburn.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "67541a18-c599-423b-bf05-d68153af1e2f"
MUNI = "Millburn township"
CITED = "§ DRZ-606.9 b.2 (CMO warehouse by-right); closed list ('All uses not expressly permitted...prohibited'); § DRZ-606.1 (C Conservation)"
ORD = "Township of Millburn, NJ Code Art. 6 Zoning Provisions (eCode360 MI4080)"

Q_SS_CMO = ("§ DRZ-606.9 (Commercial/Medical Office CMO) b. Permitted Principal Uses: '2. Wholesale "
            "business, light assembly and manufacturing, scientific and other research facilities, "
            "warehouses, and offices operated in connection with the foregoing uses.' (Self-storage is not "
            "separately named → conditional by the warehouse-by-right convention.)")
Q_CLOSED = ("Closed list: 'All uses not expressly permitted in this ordinance are prohibited.' → self-"
            "storage (named nowhere; warehousing by-right only in CMO) is prohibited in all other districts; "
            "no named vehicle garage-condo use → lgc prohibited everywhere.")
Q_C = ("§ DRZ-606.1 (Conservation-Recreation C): 'restrict development on public lands, lands which are "
       "environmentally sensitive...' permitted uses = water-supply utility facilities + park/recreation "
       "open-space only.")


def cite(*qs):
    return [{"quote": q, "section": "Art. 6", "ordinance": ORD} for q in qs]


N_CMO = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): §DRZ-606.9 b.2 warehouses permitted by-right; self-storage "
         "UNNAMED → conditional by convention. li PERMITTED: light assembly/manufacturing by-right. lgc "
         "PROHIBITED (no named garage-condo use).")
N_C = ("All prohibited. #38: 'C' = Conservation-Recreation (§DRZ-606.1), NOT commercial — public/water-"
       "supply/park land only. The wealth-ring 'C' lots are conservation, not a self-storage opportunity.")
N_CE = "All prohibited. CE Conservation-Educational-Cultural: conservation/institutional; no self-storage/warehouse/industrial use."
N_CD = "All prohibited. CD Cultural District: cultural/institutional; no self-storage/warehouse/industrial use."
N_OR = ("All prohibited. OR-1/2/3 Office Research (§DRZ-606.8): offices/retail services/office-hotel/"
        "multifamily; NO warehouse/self-storage/manufacturing (closed list).")
N_B = "All prohibited. Business district (Regional/Highway/Neighborhood/Central Business): retail/office/service; no warehouse/self-storage/manufacturing (closed list)."
N_P = "All prohibited. P Public District: public/governmental uses; no self-storage/warehouse/industrial use."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/manufacturing use (closed list); no named garage-condo use."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("CMO","CMO Commercial/Medical Office","conditional","conditional","permitted","prohibited",0.85,N_CMO),
    ("C","C Conservation-Recreation","prohibited","prohibited","prohibited","prohibited",0.90,N_C),
    ("CE","CE Conservation-Educational-Cultural","prohibited","prohibited","prohibited","prohibited",0.88,N_CE),
    ("CD","CD Cultural District","prohibited","prohibited","prohibited","prohibited",0.86,N_CD),
    ("OR-1","OR-1 Office Research","prohibited","prohibited","prohibited","prohibited",0.86,N_OR),
    ("OR-2","OR-2 Office Research","prohibited","prohibited","prohibited","prohibited",0.86,N_OR),
    ("OR-3","OR-3 Office Research","prohibited","prohibited","prohibited","prohibited",0.86,N_OR),
    ("B-1","B-1 Regional Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-2","B-2 Highway Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-3","B-3 Neighborhood Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-4","B-4 Central Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("P","P Public","prohibited","prohibited","prohibited","prohibited",0.88,N_P),
    ("R-O","R-O Residential Office","prohibited","prohibited","prohibited","prohibited",0.86,N_RES),
    ("R-3","R-3 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-4","R-4 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5","R-5 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-6","R-6 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-7","R-7 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-8","R-8 Residential Multi-Family","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1-5","R-1-5 Residential","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_CMO, Q_CLOSED, Q_C), "cited_subsection": CITED,
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
            ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
