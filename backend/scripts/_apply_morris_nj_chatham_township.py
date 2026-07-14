"""Chatham TOWNSHIP NJ (Morris Co) — Stage-4 close (2026-07-14). 0-NEEDLE correct no-op.

DISTINCT from 'Chatham borough' (already grounded). NJ name-bound -> NO rebind.
municipality = 'Chatham township' (exact parcels.city).

#38 WRONG-FAMILY CLUSTER (verified against Article II district classification): every
industrial-looking parcel code is actually non-industrial —
  PI-1 / PI-2 = "Professional Institutional District" (office/institutional, NOT Planned Industrial)
  CP          = "County Park District" (park land, NOT Corporate/Commercial Park)
  B-1 / B-2   = "Residence District" (NOT Business)
  WA          = "Wilderness Area District" (conservation)
  PCD         = "Planned Commercial District" (retail commercial — the only commercial district)
Self-storage / mini-warehouse / warehouse / light-manufacturing / distribution / wholesale appear
NOWHERE in the 251k-char zoning regulations. So Chatham township has NO self-storage-eligible use in
any district -> 0 wealth-gated needles. Correct no-op per the thesis (wealth without self-storage-
eligible industrial != gap).

Grounding — Township of Chatham, NJ Code Ch. 30 Land Development, Article VII Zoning Regulations
(eCode360 CH4056, full print?guid=35304966). NJ permissive per-district use lists (closed).
  ss/mw PROHIBITED everywhere: "Self-storage" and "warehouse" are not named uses in any district.
  li PROHIBITED everywhere: no light-manufacturing / industrial / distribution / wholesale use appears
    in any district (PI = Professional Institutional office use only; PCD = retail commercial).
  lgc PROHIBITED everywhere: no named vehicle garage-condo use.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), wrong-family disambiguation (#38), closed-list sweep (#58), verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_morris_nj_chatham_township.py
"""
import asyncio, json, asyncpg

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Chatham township"
CITED_SUBSECTION = "Art. VII Zoning Regulations; Art. II district classification"
ORD = ("Township of Chatham, NJ Code Ch. 30 Land Development, Article VII Zoning Regulations "
       "(eCode360 CH4056)")

Q_DIST = ("District classification (Art. II): 'PI-1/PI-2 Professional Institutional District; CP County "
          "Park District; B-1/B-2 Residence District; WA Wilderness Area District; PCD Planned Commercial "
          "District.' None is an industrial district.")
Q_NOSTORE = ("Self-storage, mini-warehouse, warehouse, light-manufacturing, distribution and wholesale "
             "are NOT named as permitted uses in any district of Article VII (per-district permissive use "
             "lists are closed).")
Q_LGC = ("No named vehicle garage-condo principal use anywhere in Ch. 30; per-district use lists are "
         "closed -> lgc prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 30 Art. VII", "ordinance": ORD} for q in qs]


N_PI = ("All prohibited. #38: PI-1/PI-2 = Professional INSTITUTIONAL District (office/institutional, not "
        "industrial); no self-storage/warehouse/light-industrial use named; no garage-condo use.")
N_CP = ("All prohibited. #38: CP = County Park District (park land); no commercial/storage/industrial use.")
N_WA = ("All prohibited. WA = Wilderness Area District (conservation); no commercial/storage use.")
N_PCD = ("All prohibited. PCD = Planned Commercial District (retail commercial); self-storage/warehouse/"
         "light-industrial NOT named in Article VII; no garage-condo use.")
N_B = ("All prohibited. #38: B-1/B-2 = RESIDENCE District (not Business); no self-storage/industrial use.")
N_RES = ("All prohibited. Residence district: no self-storage/warehouse/industrial use named; no "
         "garage-condo use.")

# zone_code, zone_name, note
_R = [
    ("R-1","R-1 Residence",N_RES), ("R-1A","R-1A Residence",N_RES), ("R-2","R-2 Residence",N_RES),
    ("R-2A","R-2A Residence",N_RES), ("R-2B-1","R-2B-1 Residence",N_RES), ("R-2B-2","R-2B-2 Residence",N_RES),
    ("R-3","R-3 Residence",N_RES), ("R-4","R-4 Residence",N_RES), ("R-5","R-5 Residence",N_RES),
    ("R-5A","R-5A Residence",N_RES), ("R-6A","R-6A Residence",N_RES), ("R-6B","R-6B Residence",N_RES),
    ("R-7","R-7 Residence",N_RES), ("AH","AH Affordable Housing Residence",N_RES),
    ("B-1","B-1 Residence District",N_B), ("B-2","B-2 Residence District",N_B),
    ("PI-1","PI-1 Professional Institutional",N_PI), ("PI-2","PI-2 Professional Institutional",N_PI),
    ("CP","CP County Park District",N_CP), ("WA","WA Wilderness Area District",N_WA),
    ("PCD","PCD Planned Commercial District",N_PCD),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": "prohibited", "mini_warehouse": "prohibited",
    "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
    "citations": cite(Q_DIST, Q_NOSTORE, Q_LGC), "cited_subsection": CITED_SUBSECTION,
    "confidence": 0.88, "notes": note,
} for zc, zn, note in _R]

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
        rows = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li,
            luxury_garage_condo::text lgc, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:8} ss={r['ss']:11} li={r['li']:11} lgc={r['lgc']:11} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
