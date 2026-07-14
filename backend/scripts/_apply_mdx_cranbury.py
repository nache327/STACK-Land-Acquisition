"""Cranbury Township NJ (Middlesex Co) — Stage-4 grounding (2026-07-14). NEEDLE = HC + GC.

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'Cranbury township' (exact
parcels.city). Source: Township of Cranbury NJ Code Ch. 150 Art. III Zoning (eCode360 CR0758, full
article via print?guid=6664894).

#38 CATCH: R-LI = "Residential - Light Impact" Zone (§150-15), NOT industrial — its 27 wealth-ring lots
are residential. The industrial zones are I-LI "Industrial-Light Impact" (§150-23) and RO/LI "Research
Office and Light Industrial" (§150-24).

NJ SELF-STORAGE CATCH (both triggers): (a) GLOBAL CLOSED LIST §150-10 "Uses prohibited in all districts.
All uses not expressly permitted in this article are prohibited"; (b) self-storage NAMED & CONFINED —
§150-20B(47) "Self-storage warehouses" is a permitted use in the HC Highway Commercial District, and GC
§150-21B(1) inherits "All uses which are permitted in the HC Highway Commercial District." Self-storage
appears NOWHERE else (single mention in the whole article). So:
  - HC + GC → ss/mw PERMITTED (named).
  - I-LI (§150-23) + RO/LI (§150-24) → ss/mw PROHIBITED: their "(5) Wholesaling of goods...including
    warehousing or storage of goods" / "(c) Wholesale and warehouse storage facilities" is wholesale-
    accessory warehousing (Berkeley-Heights rule: wholesale ≠ a named self-storage use) and §150-10 +
    named-confinement to HC/GC override the warehouse convention. li PERMITTED (§150-23/24 "Light industry").
NEEDLE (wealth-ring ≥1.5ac): HC = 14, GC = 10 → 24 ss lots. I-LI = 88, RO/LI = 23 = li-armed only
(the Exit-8A industrial base is real but self-storage is confined to the HC/GC commercial strips).

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_mdx_cranbury.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "9c039328-c995-41fc-83ce-fb4966fd402b"
MUNI = "Cranbury township"
CITED = "§ 150-20B(47) (HC ss); § 150-21B(1) (GC inherits HC); § 150-23/150-24 (I-LI/RO-LI li); § 150-10 (closed list)"
ORD = "Township of Cranbury, NJ Code Ch. 150 Art. III Zoning (eCode360 CR0758)"

Q_SS_HC = ("§ 150-20B (HC Highway Commercial District) Permitted uses: '...(46) Hotels and inns. (47) "
           "Self-storage warehouses. (48) Health clubs...'")
Q_SS_GC = ("§ 150-21B(1) (GC General Commercial District): '(1) All uses which are permitted in the HC "
           "Highway Commercial District (§ 150-20B).' → inherits (47) Self-storage warehouses.")
Q_LI_ILI = ("§ 150-23B (I-LI Industrial-Light Impact Zone): '(1) Light industry, provided that any "
            "manufacturing or fabricating activities shall be contained within enclosed structures... (5) "
            "Wholesaling of goods and services, including warehousing or storage of goods, provided that "
            "all activities and inventories are conducted entirely within an enclosed structure.'")
Q_LI_ROLI = ("§ 150-24B (RO/LI Research Office and Light Industrial Zone): '(1) Light industry... (3) "
             "Planned industrial parks... (c) Wholesale and warehouse storage facilities.'")
Q_CLOSED = ("§ 150-10 Uses prohibited in all districts: 'All uses not expressly permitted in this article "
            "are prohibited.' → self-storage (named only in HC/GC) is prohibited in I-LI/RO/LI/all others "
            "notwithstanding by-right wholesale-warehousing; no named vehicle garage-condo use → lgc "
            "prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 150 Art. III", "ordinance": ORD} for q in qs]


N_HC = ("ss/mw PERMITTED (GROUNDED NEEDLE): §150-20B(47) 'Self-storage warehouses' permitted in HC. li "
        "PROHIBITED (retail-commercial district, no manufacturing). lgc PROHIBITED.")
N_GC = ("ss/mw PERMITTED (GROUNDED NEEDLE): §150-21B(1) GC inherits all HC permitted uses incl. §150-20B(47) "
        "'Self-storage warehouses'. li PROHIBITED (commercial). lgc PROHIBITED.")
N_ILI = ("ss/mw PROHIBITED: self-storage named/confined to HC/GC (§150-20B(47)); §150-10 closes the list — "
         "the §150-23B(5) 'Wholesaling...including warehousing or storage of goods' is wholesale-accessory "
         "(Berkeley-Heights: wholesale ≠ named self-storage) → does NOT ground self-storage. li PERMITTED "
         "(GROUNDED): §150-23B(1) light industry. lgc PROHIBITED.")
N_ROLI = ("ss/mw PROHIBITED: self-storage confined to HC/GC (§150-10 closed list); §150-24B(3)(c) 'Wholesale "
          "and warehouse storage facilities' in planned industrial parks is not a named self-storage use. li "
          "PERMITTED (GROUNDED): §150-24B(1) light industry. lgc PROHIBITED.")
N_CM = "All prohibited. C-M Community Mixed-Use (§150-22): attached dwellings/apartments/offices/retail; no self-storage/warehouse/manufacturing (§150-10 closed list)."
N_VC = "All prohibited. VC Village Commercial (§150-19): village retail/service; no self-storage/warehouse (§150-10 closed list)."
N_HM = "All prohibited (conservative; 0 wealth-ring lots). HM Highway Mixed Use — self-storage inheritance not verified; no needle impact (no in-ring parcels)."
N_AG = "All prohibited. A-100 Agricultural Preservation (§150-14): agriculture/farm; no self-storage/warehouse/industrial use."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/manufacturing use (§150-10 closed list); no named garage-condo use."
N_RLI = "All prohibited. #38: R-LI = Residential - Light Impact Zone (§150-15), NOT industrial — residential, no self-storage/warehouse/manufacturing."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("HC","HC Highway Commercial","permitted","permitted","prohibited","prohibited",0.90,N_HC),
    ("GC","GC General Commercial","permitted","permitted","prohibited","prohibited",0.88,N_GC),
    ("I-LI","I-LI Industrial-Light Impact","prohibited","prohibited","permitted","prohibited",0.90,N_ILI),
    ("RO/LI","RO/LI Research Office and Light Industrial","prohibited","prohibited","permitted","prohibited",0.90,N_ROLI),
    ("CM","C-M Community Mixed-Use","prohibited","prohibited","prohibited","prohibited",0.86,N_CM),
    ("VC","VC Village Commercial","prohibited","prohibited","prohibited","prohibited",0.86,N_VC),
    ("HM","HM Highway Mixed Use","prohibited","prohibited","prohibited","prohibited",0.60,N_HM),
    ("A-100","A-100 Agricultural Preservation","prohibited","prohibited","prohibited","prohibited",0.88,N_AG),
    ("RLD-1","RLD-1 Residential-Low Density 1","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RLD-3","RLD-3 Residential-Low Density 3","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-LI","R-LI Residential-Light Impact","prohibited","prohibited","prohibited","prohibited",0.90,N_RLI),
    ("V/HR","V/HR Village/Hamlet Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-AH","R-AH Residential-Affordable Housing","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-AR","R-AR Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-ML","R-ML Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-ML III","R-ML III Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_HC, Q_SS_GC, Q_LI_ILI, Q_LI_ROLI, Q_CLOSED), "cited_subsection": CITED,
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
            print(f"  {r['zone_code']:9} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
