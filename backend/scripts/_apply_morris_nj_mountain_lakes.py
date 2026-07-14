"""Mountain Lakes Borough NJ (Morris Co) — Stage-4 close (2026-07-14). NEEDLE = B (Business Zone B).

CATCH #38: parcel codes "C-1"/"C-2" are CONSERVATION Zones (recreational uses only), NOT commercial —
the 26+8 wealth-ring "C" lots are a false commercial signal and ground PROHIBITED. Parcel "A"/"B" =
Business Zone A / Business Zone B; "OL-1"/"OL-2" = Office and Light Industrial Zones; "RC-*" =
Residential Clustering (not commercial).

NJ CATCH (scenario b, verbatim): self-storage IS a named/defined use (§ 245-112) assigned as a
CONDITIONAL use to Business Zone B ONLY (§ 245-78 C(4)). It is NOT listed in the OL Office/Light
Industrial zones, whose § 245-79 A(2) permits "Light manufacturing ... storing, assembly or fabrication
of goods and materials" by-right — but because self-storage is separately named and assigned to Zone B,
that by-right storage/fabrication grounds li (NOT self-storage) in OL. So OL-2's 9 wealth-ring lots are
li-armed only; the self-storage needle is Business Zone B (6 wealth-ring lots, conditional).

NJ name-bound -> NO rebind. municipality = 'Mountain Lakes borough' (exact parcels.city).

Grounding — Borough of Mountain Lakes, NJ Code Ch. 245 Land Use & Zoning (eCode360 MO1514, full chapter
via print?guid=8632797):
  ss/mw CONDITIONAL in B (Business Zone B): § 245-78 C. Conditional uses (4) "Self-storage facilities in
    accordance with § 245-112." "SELF-STORAGE FACILITY: A building or group of buildings containing
    individual ... storage." Business Zone A (§ 245-77) has "Conditional uses: none" -> ss prohibited.
  li PERMITTED in OL-1/OL-2 (and OL overlays): § 245-79 A(2) "Light manufacturing; processing of data
    and materials; storing, assembly or fabrication of goods and materials; printing and publishing;
    research" (by-right). Self-storage NOT listed in OL -> ss/mw prohibited there.
  C-1/C-2 = Conservation Zones (§ 245-81): recreational uses only -> all prohibited.
  lgc PROHIBITED everywhere: no named vehicle garage-condo use.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), conservation-vs-commercial disambiguation (#38), named-assignment over convention,
verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_morris_nj_mountain_lakes.py
"""
import asyncio, json, asyncpg

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Mountain Lakes borough"
CITED_SUBSECTION = "§ 245-78 C(4) (Business B); § 245-79 A(2) (OL); § 245-81 (Conservation)"
ORD = "Borough of Mountain Lakes, NJ Code Ch. 245 Land Use & Zoning (eCode360 MO1514)"

Q_SS = ("§ 245-78 Business Zone B, C. Conditional uses (4): 'Self-storage facilities in accordance with "
        "§ 245-112.' 'SELF-STORAGE FACILITY: A building or group of buildings containing individual ... "
        "storage.' Business Zone A (§ 245-77) 'Conditional uses: none.' Self-storage not listed in any "
        "OL/Conservation/residential zone.")
Q_LI = ("§ 245-79 Office and Light Industrial Zones OL-1 and OL-2, A(2): 'Light manufacturing; processing "
        "of data and materials; storing, assembly or fabrication of goods and materials; printing and "
        "publishing; research' (permitted principal use).")
Q_CONS = ("§ 245-81 Conservation Zone C: permitted principal uses are recreational (walking, jogging, "
          "biking, bird-watching, fishing) with limited disturbance to the natural environment; no "
          "commercial/storage use. C-1/C-2 are Conservation Zones. No named vehicle garage-condo use -> "
          "lgc prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 245", "ordinance": ORD} for q in qs]


N_B = ("ss/mw CONDITIONAL (GROUNDED): § 245-78 C(4) 'Self-storage facilities in accordance with § 245-112' "
       "is a conditional use in Business Zone B. li prohibited (retail/commercial, no manufacturing). lgc "
       "PROHIBITED.")
N_A = ("All prohibited. Business Zone A (§ 245-77) 'Conditional uses: none' — no self-storage; retail/"
       "office only; no manufacturing/garage-condo.")
N_OL = ("ss/mw PROHIBITED: self-storage is named and assigned to Business Zone B only (§ 245-78 C(4)); not "
        "listed in OL. li PERMITTED (GROUNDED): § 245-79 A(2) light manufacturing / storing / assembly / "
        "fabrication by-right. lgc PROHIBITED.")
N_CONS = ("All prohibited. C-1/C-2 = Conservation Zone (§ 245-81): recreational uses only (walking, biking, "
          "bird-watching); no commercial/storage/industrial use; no garage-condo use.")
N_RES = ("All prohibited. Residential district: no self-storage/warehouse/manufacturing use; no named "
         "garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-A","R-A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-AA","R-AA Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1","R-1 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2","R-2 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-AH","R-AH Residence-Affordable Housing","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("RC-1","RC-1 Residential Clustering","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("RC-2","RC-2 Residential Clustering","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("RC-3","RC-3 Residential Clustering","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("A","A Business Zone","prohibited","prohibited","prohibited","prohibited",0.86,N_A),
    ("B","B Business Zone","conditional","conditional","prohibited","prohibited",0.90,N_B),
    ("OL-1","OL-1 Office & Light Industrial","prohibited","prohibited","permitted","prohibited",0.88,N_OL),
    ("OL-2","OL-2 Office & Light Industrial","prohibited","prohibited","permitted","prohibited",0.88,N_OL),
    ("OL-2/R-1","OL-2 Office/Light Industrial + R-1 overlay","prohibited","prohibited","permitted","prohibited",0.85,N_OL),
    ("C-1","C-1 Conservation Zone","prohibited","prohibited","prohibited","prohibited",0.92,N_CONS),
    ("C-2","C-2 Conservation Zone","prohibited","prohibited","prohibited","prohibited",0.92,N_CONS),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_CONS), "cited_subsection": CITED_SUBSECTION,
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
            print(f"  {r['zone_code']:10} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
