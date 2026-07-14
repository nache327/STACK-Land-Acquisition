"""Edison Township NJ (Middlesex Co) — Stage-4 grounding (2026-07-14). NEEDLE = R-I-1 (conditional).

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'Edison township' (exact parcels.city).
Source: Township of Edison NJ Code Ch. 37 Zoning (eCode360 ED0440, full chapter via print?guid=34716725).
Global closed list § 37-4.14 "Prohibited Uses in All Zones: a. All uses not specifically permitted... are
prohibited." Self-storage NAMED NOWHERE (0 mentions); "WAREHOUSE" is a defined use.

HUDSON LESSON (Edison is the textbook case): Edison's massive warehouse corridor is the L-I Light Industrial
District (§ 37-33, warehousing-distribution by-right) — but L-I sits OUTSIDE the wealth ring (0 wealth-ring
≥1.5ac lots in the distribution). The IN-RING industrial is R-I / R-I-1 Restricted Industrial:
  - R-I-1 §37-32.2(d): "Warehousing facilities for products or materials, excluding hazardous..." = PERMITTED
    by-right → warehouse-by-right + self-storage unnamed ⇒ ss/mw CONDITIONAL (convention). li PERMITTED
    (§37-32.2(b)(c) finishing/mechanical assembly). NEEDLE = 14 wealth-ring lots.
  - R-I §37-31.1: offices/labs/fabrication/assembly/processing — NO warehousing → ss/mw PROHIBITED
    (closed list); li PERMITTED (fabrication/assembly). li-armed only (18 lots).
  - L-I §37-33.1(d): warehousing-distribution by-right → ss/mw CONDITIONAL, li permitted — grounded for
    correctness but 0 wealth-ring lots (out-of-ring corridor = correct no-op today).
#38: G-C = "Golf Course District" (§37-21 area), NOT General Commercial — the 7 in-ring G-C lots are a golf
course no-op. ROL = Research/Office/Laboratory (office/retail/labs, no warehouse/manufacturing) → prohibited.

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_mdx_edison.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "9c039328-c995-41fc-83ce-fb4966fd402b"
MUNI = "Edison township"
CITED = "§ 37-32.2(d) (R-I-1 warehousing by-right → ss conditional); § 37-31.1 (R-I li); § 37-33.1(d) (L-I); § 37-4.14 (closed list)"
ORD = "Township of Edison, NJ Code Ch. 37 Zoning (eCode360 ED0440)"

Q_SS_RI1 = ("§ 37-32.2 (R-I-1 Restricted Industrial District) Permitted Uses: '(d) Warehousing facilities "
            "for products or materials, excluding hazardous, toxic, flammable and corrosive substances.' "
            "(Warehouse by-right; self-storage unnamed → conditional by convention.)")
Q_SS_LI = ("§ 37-33.1 (L-I Light Industrial District) Permitted Uses: '(d) Warehousing-distribution "
           "facilities for products or materials but not including truck terminals.' (Out-of-ring corridor.)")
Q_LI = ("§ 37-31.1 (R-I) '(c) Fabrication and assembly of products'; § 37-32.2 (R-I-1) '(b) Finishing and "
        "assembly of products... (c) Mechanical assembly of high technology and electronic equipment.'")
Q_CLOSED = ("§ 37-4.14 Prohibited Uses in All Zones: 'a. All uses not specifically permitted by zone... are "
            "prohibited.' → self-storage (unnamed) prohibited except where warehousing is a permitted "
            "principal use (R-I-1/L-I, conditional by convention); no named garage-condo use → lgc prohibited.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 37", "ordinance": ORD} for q in qs]


N_RI1 = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): § 37-32.2(d) warehousing facilities permitted by-right; self-"
         "storage unnamed → conditional by convention. li PERMITTED: § 37-32.2(b)(c) finishing/mechanical "
         "assembly. lgc PROHIBITED.")
N_RI = ("ss/mw PROHIBITED: R-I § 37-31.1 permits offices/labs/fabrication/assembly/processing but NOT "
        "warehousing; § 37-4.14 closed list + self-storage unnamed. li PERMITTED (GROUNDED): § 37-31.1(c) "
        "fabrication and assembly of products. lgc PROHIBITED.")
N_LI = ("ss/mw CONDITIONAL: § 37-33.1(d) warehousing-distribution by-right → conditional by convention; li "
        "PERMITTED (§37-33.1(c) manufacturing). HUDSON LESSON: L-I is the out-of-ring Turnpike corridor — "
        "0 wealth-ring ≥1.5ac lots today (correct no-op); grounded for correctness/future-proofing. lgc PROHIBITED.")
N_GC = "All prohibited. #38: G-C = Golf Course District (NOT General Commercial) — the 7 in-ring lots are a golf course, no self-storage/industrial use."
N_ROL = "All prohibited. ROL Research/Office/Laboratory (§37-34.1): offices/schools/retail/labs/hotels; no warehousing or manufacturing (§37-4.14 closed list)."
N_BUS = "All prohibited. Business/office-service district: retail/office/service; no warehousing/self-storage/manufacturing permitted use (§37-4.14 closed list)."
N_OTH = "All prohibited. Open-space/educational/township-center/urban-renewal/revitalization district: no self-storage/warehouse/manufacturing permitted principal use (§37-4.14 closed list)."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/manufacturing use (§37-4.14 closed list); no named garage-condo use."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-I-1","R-I-1 Restricted Industrial","conditional","conditional","permitted","prohibited",0.85,N_RI1),
    ("R-I","R-I Restricted Industrial","prohibited","prohibited","permitted","prohibited",0.90,N_RI),
    ("L-I","L-I Light Industrial","conditional","conditional","permitted","prohibited",0.82,N_LI),
    ("ROL","ROL Research, Office and Laboratory","prohibited","prohibited","prohibited","prohibited",0.85,N_ROL),
    ("G-C","G-C Golf Course","prohibited","prohibited","prohibited","prohibited",0.90,N_GC),
    ("G-BH","G-BH General Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("L-B","L-B Local Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("P-B","P-B Planned Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("O-S","O-S Office-Service","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("O-S-1","O-S-1 Office-Service","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("O-S-2","O-S-2 Office-Service","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("OSR-C","OSR-C Open Space/Recreation Conservation","prohibited","prohibited","prohibited","prohibited",0.88,N_OTH),
    ("E-1","E-1 Educational","prohibited","prohibited","prohibited","prohibited",0.88,N_OTH),
    ("T-C","T-C Township Center","prohibited","prohibited","prohibited","prohibited",0.82,N_OTH),
    ("U-R","U-R Urban Renewal","prohibited","prohibited","prohibited","prohibited",0.78,N_OTH),
    ("RRRD","RRRD Raritan River Revitalization","prohibited","prohibited","prohibited","prohibited",0.80,N_OTH),
    ("AAR","AAR Residential","prohibited","prohibited","prohibited","prohibited",0.85,N_RES),
    ("AHOZ","AHOZ Affordable Housing Overlay","prohibited","prohibited","prohibited","prohibited",0.85,N_RES),
    ("AHOZ-2","AHOZ-2 Affordable Housing Overlay","prohibited","prohibited","prohibited","prohibited",0.85,N_RES),
    ("L-R","L-R Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1","R-1 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-7","R-7 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-A","R-A Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-A (PRD)","R-A (PRD) Residential","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("R-A-th","R-A-th Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-AA","R-AA Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-B","R-B Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-B (PUD)","R-B (PUD) Residential","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("R-B-th","R-B-th Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-BB","R-BB Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-BB-th","R-BB-th Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_RI1, Q_SS_LI, Q_LI, Q_CLOSED), "cited_subsection": CITED,
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
            ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, (light_industrial::text='permitted') DESC, zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:11} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
