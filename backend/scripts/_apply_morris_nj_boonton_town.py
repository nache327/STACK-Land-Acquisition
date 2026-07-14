"""Boonton TOWN NJ (Morris Co) — Stage-4 close (2026-07-14). NEEDLE = C-1 only.

DISTINCT from 'Boonton township' (D's rank-3 target) — this is 'Boonton town' (#38). NJ name-bound ->
NO rebind. municipality = 'Boonton town' (exact parcels.city).

NJ CATCH (scenario b, verbatim-verified): the zoning was amended 9-16-2024 (Ord. 19-24) to add a
defined "SELF STORAGE FACILITY" use and to list "Self-storage facilities" as a permitted principal use
in the C-1 (Hybrid Commercial/Industrial) Zone ONLY (§ 300-110 A(18)(d)). The SAME ordinance amended
§ 300-111 I-1 Industrial but did NOT add self-storage there (I-1 lists "Warehouses" by-right but not
self-storage). Combined with the global closed-list § 300-83 ("Where a use is not specifically
permitted in a zone district, it is prohibited"), self-storage is a NAMED use CONFINED to C-1 -> the
warehouse-by-right convention does NOT override the deliberate I-1 exclusion. So the 27 wealth-ring I-1
lots are li-armed only (NOT self-storage needles); the self-storage needle is C-1 (9 wealth-ring lots).

Grounding — Town of Boonton, NJ Code Ch. 300 Zoning & Land Use (eCode360 BO1912, full chapter via
print?guid=7162402):
  ss/mw PERMITTED (by-right) in C-1: § 300-110 A(18) "The following uses shall only be permitted in the
    C-1 Zone: ... (d) Self-storage facilities" (Hybrid Commercial/Industrial; amended 9-16-2024 Ord.
    19-24). "SELF STORAGE FACILITY: A facility solely used for the storage of goods and materials..."
  li PERMITTED in C-1 and I-1: C-1 § 300-110 A(18)(c) "Processes of manufacturing, fabrication,
    packaging, treatment, or conversion of products"; I-1 § 300-111 A(1) manufacturing + A(4)
    "Warehouses, trucking, terminals and wholesale distribution centers" (by-right).
  ss/mw PROHIBITED in I-1, C-2, B-*, residential: self-storage named & confined to C-1; § 300-83 closed
    list. C-2 (Gateway Commercial) gets only the shared (1)-(17) commercial uses, not the C-1-only (18).
  lgc PROHIBITED everywhere: no named vehicle garage-condo use; § 300-83 closed list.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), Boonton-town-vs-township disambiguation (#38), named-confinement over convention +
closed-list sweep (#57/#58), verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_morris_nj_boonton_town.py
"""
import asyncio, json, asyncpg

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Boonton town"
CITED_SUBSECTION = "§ 300-110 A(18)(d) (C-1); § 300-111 (I-1); § 300-83 (closed list)"
ORD = ("Town of Boonton, NJ Code Ch. 300 Zoning & Land Use (eCode360 BO1912), amended 9-16-2024 by "
       "Ord. No. 19-24")

Q_SS = ("§ 300-110 A(18): 'The following uses shall only be permitted in the C-1 Zone: ... (d) "
        "Self-storage facilities.' 'SELF STORAGE FACILITY: A facility solely used for the storage of "
        "goods and materials...' (added 9-16-2024 Ord. 19-24). Not listed in I-1, C-2 or any other zone.")
Q_LI = ("C-1 § 300-110 A(18)(c) 'Processes of manufacturing, fabrication, packaging, treatment, or "
        "conversion of products'; I-1 § 300-111 A(1) manufacturing + A(4) 'Warehouses, trucking, "
        "terminals and wholesale distribution centers' (permitted principal uses).")
Q_CLOSED = ("§ 300-83 Permitted uses: 'Where a use is not specifically permitted in a zone district, it "
            "is prohibited.' -> self-storage (named, C-1 only) is prohibited in I-1/C-2/B/residential "
            "notwithstanding the by-right warehouse use in I-1; no named vehicle garage-condo use -> lgc "
            "prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 300", "ordinance": ORD} for q in qs]


N_C1 = ("ss/mw PERMITTED (GROUNDED): § 300-110 A(18)(d) 'Self-storage facilities' by-right in C-1 (Hybrid "
        "Commercial/Industrial). li PERMITTED: (18)(c) manufacturing/fabrication. lgc PROHIBITED.")
N_I1 = ("ss/mw PROHIBITED: self-storage is a NAMED use confined to C-1 (§ 300-110 A(18)(d)); the same "
        "9-16-2024 amendment did NOT add it to I-1, and § 300-83 closes the list -> warehouse-by-right "
        "does NOT ground self-storage here. li PERMITTED (GROUNDED): § 300-111 A(1) manufacturing + A(4) "
        "warehouses/distribution by-right. lgc PROHIBITED.")
N_C2 = ("ss/mw PROHIBITED: C-2 (Gateway Commercial) receives only the shared § 300-110 A(1)-(17) "
        "commercial uses; the (18) uses incl. self-storage are C-1 ONLY (§ 300-83 closed). li PROHIBITED "
        "(no manufacturing/warehouse). lgc PROHIBITED.")
N_B = ("All prohibited. Business district: retail/office/service only; self-storage confined to C-1 and "
       "§ 300-83 closes the list; no manufacturing/warehouse or garage-condo use.")
N_I2 = ("ss/mw PROHIBITED: self-storage confined to C-1; § 300-83 closed. li conservative-prohibited: "
        "no I-2 district use list in the current Ch. 300 (legacy code) -> not cited. lgc PROHIBITED.")
N_RES = ("All prohibited. Residential district: no self-storage/warehouse/manufacturing use (§ 300-83 "
         "closed list); no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-1A","R-1A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1B","R-1B Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1C","R-1C Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1D","R-1D Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1E","R-1E Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2A","R-2A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2B","R-2B Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3A","R-3A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3B","R-3B Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("RH","RH Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("C-1","C-1 Hybrid Commercial/Industrial","permitted","permitted","permitted","prohibited",0.90,N_C1),
    ("C-2","C-2 Gateway Commercial","prohibited","prohibited","prohibited","prohibited",0.88,N_C2),
    ("I-1","I-1 Industrial","prohibited","prohibited","permitted","prohibited",0.90,N_I1),
    ("I-2","I-2 (legacy code)","prohibited","prohibited","prohibited","prohibited",0.75,N_I2),
    ("B-1","B-1 Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-2","B-2 Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-3","B-3 Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-4","B-4 Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
    ("B-5","B-5 Business","prohibited","prohibited","prohibited","prohibited",0.86,N_B),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_CLOSED), "cited_subsection": CITED_SUBSECTION,
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
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
