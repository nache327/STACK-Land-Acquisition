"""Fairfield Township NJ (Essex Co) — Stage-4 grounding (2026-07-14). NEEDLE = C-3 + H-R.

NJ name-bound (no rebind); parcels bound to zoning_code via NJTPA Atlas 082025. municipality =
'Fairfield township' (exact parcels.city). Source: Township of Fairfield NJ Code Ch. 45 Zoning
(eCode360 FA0184, full chapter via print?guid=35314662).

NJ SELF-STORAGE CATCH (both triggers present — applied BEFORE the warehouse convention):
  (a) GLOBAL CLOSED LIST §45-7 (Definitions): "Any use not specifically permitted as a principal
      permitted use, accessory use or conditional use is prohibited."
  (b) self-storage is a NAMED use CONFINED to two districts:
      - C-3 Commercial-Industrial Mixed-Use §45-32.1h "Interior self-storage facilities" (permitted
        principal use; also §45-32.1a fabrication/assembly + d warehousing/distribution → li).
      - H-R Highway Redevelopment §45-34.1 "Permitted uses shall be limited to self-service storage
        facilities permitted only within multistory structures..." (self-storage-ONLY zone; §45-34.1a(2)
        expressly bars manufacturing/fabrication/processing in units → li prohibited).
So the warehouse-by-right zones (L-1 §45-39.1b, L-2 =L-1, L-3 =L-1+aviation, H-D §45-35.1l) do NOT
ground self-storage (named-confinement + closed list beats the convention — the Boonton rule). Those are
li-armed only. NEEDLE (wealth-ring ≥1.5ac): C-3 = 8, H-R = 1 → 9 self-storage lots. L-1(150)/H-D(90)/
L-2(40)/L-3(15) = li-armed, NOT ss needles.

Executable apply (Boonton template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_essex_fairfield.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "67541a18-c599-423b-bf05-d68153af1e2f"  # Essex County, NJ
MUNI = "Fairfield township"
CITED = "§ 45-32.1 (C-3); § 45-34.1 (H-R); § 45-35.1 (H-D); § 45-39.1 (L-1); § 45-7 (closed list)"
ORD = "Township of Fairfield, NJ Code Ch. 45 Zoning (eCode360 FA0184)"

Q_SS_C3 = ("§ 45-32.1 Permitted Uses (C-3 Commercial-Industrial Mixed-Use): 'No structure, building or "
           "premises shall be used...except for the following uses: a. Fabrication and assembly of "
           "products... d. Packaging, warehousing and distribution of products... h. Interior "
           "self-storage facilities. ... r. Indoor storage/warehousing of vehicles.'")
Q_SS_HR = ("§ 45-34.1 Permitted Principal Uses (H-R Highway Redevelopment): 'Permitted uses shall be "
           "limited to self-service storage facilities permitted only within multistory structures "
           "designed to emulate attractive office buildings...' (individual units: no manufacturing, "
           "fabrication, processing, service/repair, or retail — dead storage only).")
Q_LI_L1 = ("§ 45-39.1 Permitted Uses (L-1 Light Industrial): 'a. The fabrication, assembly and production "
           "of products... b. The packaging, warehousing and distribution of products...' L-2 §45-40.1 "
           "'same as specified for the L-1 Zone'; L-3 §45-41.1 'In addition to those uses permitted in the "
           "L-1 Zone... helistops, heliports and airports.'")
Q_LI_HD = ("§ 45-35.1 Permitted Uses (H-D U.S. Route 46 Special Highway Development): retail/personal "
           "service/office/restaurant uses + 'l. Warehousing and wholesale supply establishments.' "
           "Self-storage is NOT among the enumerated uses.")
Q_CLOSED = ("§ 45-7 (Definitions): 'Any use not specifically permitted as a principal permitted use, "
            "accessory use or conditional use is prohibited.' → self-storage (named & confined to C-3 and "
            "H-R) is prohibited in L-1/L-2/L-3/H-D notwithstanding by-right warehousing; no named "
            "vehicle garage-condo use → lgc prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 45", "ordinance": ORD} for q in qs]


N_C3 = ("ss/mw PERMITTED (GROUNDED): §45-32.1h 'Interior self-storage facilities' by-right in C-3. li "
        "PERMITTED: §45-32.1a fabrication/assembly + d packaging/warehousing/distribution. lgc PROHIBITED "
        "(§45-32.1r indoor vehicle storage/warehousing ≠ luxury garage-condo; unnamed).")
N_HR = ("ss/mw PERMITTED (GROUNDED): §45-34.1 permitted uses 'limited to self-service storage facilities' "
        "(self-storage-only zone). li PROHIBITED: §45-34.1a(2) expressly bars manufacturing/fabrication/"
        "processing in units. lgc PROHIBITED.")
N_HD = ("ss/mw PROHIBITED: §45-35.1 enumerates retail/service/office + 'l. Warehousing and wholesale "
        "supply' but NOT self-storage; §45-7 closed list + self-storage named-confined to C-3/H-R ⇒ "
        "warehouse-by-right does NOT ground self-storage here. li PERMITTED (GROUNDED): §45-35.1l "
        "warehousing/wholesale. lgc PROHIBITED.")
N_L1 = ("ss/mw PROHIBITED: self-storage not named (§45-7 closed list; named-confined to C-3/H-R) — "
        "warehouse-by-right does NOT ground it. li PERMITTED (GROUNDED): §45-39.1a fabrication/assembly/"
        "production + b packaging/warehousing/distribution. lgc PROHIBITED.")
N_L2 = ("ss/mw PROHIBITED (same as L-1). li PERMITTED (GROUNDED): §45-40.1 'same as specified for the L-1 "
        "Zone'. lgc PROHIBITED.")
N_L3 = ("ss/mw PROHIBITED (same as L-1). li PERMITTED (GROUNDED): §45-41.1 L-1 uses + helistops/heliports/"
        "airports. lgc PROHIBITED.")
N_OP = "All prohibited. O-P Office Professional §45-36.1: offices/business schools/services/churches/public only."
N_C1 = "All prohibited. C-1 Commercial-Neighborhood §45-30.1: offices/retail/personal-service/restaurants only."
N_C2 = "All prohibited. C-2 Commercial-Bloomfield Ave §45-31.1: = C-1 + restaurants/car dealerships/indoor rec."
N_AC = "All prohibited. A-C Agricultural-Conservatory §45-46 (flood hazard area): agriculture/conservation; no industrial use (§45-7 closed list)."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/industrial use (§45-7 closed list); no named garage-condo use."
N_OS = "All prohibited. OS/REC Public, Open Space and Recreation: public/open-space/recreation only (§45-7 closed list)."
N_NDLR = ("CONSERVATIVE prohibited (conf 0.60, 1 wealth-ring lot). NDLR New Dutch Lane Redevelopment Zone "
          "(§45 Ord. 2016-11) — use schedule not cleanly captured in the Ch.45 print export; redevelopment "
          "zone, presumed residential/mixed. Escalated to _exceptions_A.md; revisit if a deal lands.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("C-3","C-3 Commercial-Industrial Mixed-Use","permitted","permitted","permitted","prohibited",0.92,N_C3),
    ("H-R","H-R Highway Redevelopment","permitted","permitted","prohibited","prohibited",0.90,N_HR),
    ("H-D","H-D U.S. Route 46 Special Highway Development","prohibited","prohibited","permitted","prohibited",0.90,N_HD),
    ("L-1","L-1 Light Industrial","prohibited","prohibited","permitted","prohibited",0.90,N_L1),
    ("L-2","L-2 Light Industrial","prohibited","prohibited","permitted","prohibited",0.88,N_L2),
    ("L-3","L-3 Light Industrial","prohibited","prohibited","permitted","prohibited",0.88,N_L3),
    ("O-P","O-P Office Professional","prohibited","prohibited","prohibited","prohibited",0.88,N_OP),
    ("C-1","C-1 Commercial-Neighborhood","prohibited","prohibited","prohibited","prohibited",0.88,N_C1),
    ("C-2","C-2 Commercial-Bloomfield Avenue","prohibited","prohibited","prohibited","prohibited",0.86,N_C2),
    ("A-C","A-C Agricultural-Conservatory","prohibited","prohibited","prohibited","prohibited",0.85,N_AC),
    ("R-1","R-1 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2","R-2 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3","R-3 Residential Mixed/Townhouse","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-4","R-4 Age Restricted Housing","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5","R-5 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-6","R-6 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("OS/REC","OS/REC Public, Open Space and Recreation","prohibited","prohibited","prohibited","prohibited",0.88,N_OS),
    ("NDLR","NDLR New Dutch Lane Redevelopment","prohibited","prohibited","prohibited","prohibited",0.60,N_NDLR),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_C3, Q_SS_HR, Q_LI_L1, Q_LI_HD, Q_CLOSED), "cited_subsection": CITED,
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
            print(f"  {r['zone_code']:8} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
