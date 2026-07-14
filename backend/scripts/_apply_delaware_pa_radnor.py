"""Radnor Township PA (Delaware Co) — Stage-4 close (2026-07-14). 0-NEEDLE CORRECT NO-OP.

Radnor is a wealthy Main Line office/institutional/residential township with NO self-storage-eligible
land in the wealth ring. Self-storage is NOT a named use anywhere in Ch. 280. The ONLY district with a
standalone by-right warehouse use is C-3 Service Commercial (§ 280-55.E "Indoor storage building or
warehouse") -> ss/mw grounded CONDITIONAL by the warehouse-by-right convention (self-storage UNNAMED —
FLAGGED). But C-3 has ZERO parcels >=1.5 ac inside the wealth ring, so it produces no wealth-gated
needles. Correct no-op per the thesis (wealth without self-storage-eligible industrial != gap).

PA spatially bound -> NO rebind. Verdicts keyed on parcel zoning_code (municipality = 'Radnor Township').

Grounding — Township of Radnor, PA Code Ch. 280 Zoning (eCode360 RA0484, full chapter via
print?guid=11078356), permissive per-district use lists ("A building may be erected or used ... for any
of the following purposes" = closed list by construction). Districts per Article II § 280-9:
  C-3 Service Commercial § 280-55: A "may be erected or used ... for any of the following": ...D.
    Wholesale business establishment. E. Indoor storage building or warehouse. F. Laundry... -> warehouse
    BY-RIGHT (standalone). Self-storage not named -> ss/mw CONDITIONAL (convention; FLAGGED unnamed). li
    permitted (contractor's shop + wholesale + warehouse by-right).
  CO Commercial-Office § 280-42: office/bank "to include a security-vault storage building" (a bank
    vault, NOT self-storage) -> no storage use. C-2 § warehouse permitted only "in conjunction with a
    retail store" (accessory conjunctive, not standalone) -> ss prohibited. C-1/PB/PLO/PA name no storage.
  #38 verified: PI = Planned INSTITUTIONAL (not Industrial); PLU = Public Land Use; AC =
    Agricultural-Conservation. Radnor has NO industrial district.
  lgc PROHIBITED everywhere: no named vehicle garage-condo use; closed list.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), wrong-family disambiguation (#38), unnamed->convention flag, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_delaware_pa_radnor.py
"""
import asyncio, json, asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Radnor Township"
CITED_SUBSECTION = "Ch. 280 Art. II-XVIII per-district use lists (§ 280-42/55)"
ORD = ("Township of Radnor, PA Code Ch. 280 Zoning (eCode360 RA0484), permissive per-district use "
       "regulations")

Q_C3 = ("§ 280-55 C-3 Service Commercial: 'A detached nonresidential building may be erected or used ... "
        "for any one of the following nonresidential purposes: ... D. Wholesale business establishment. "
        "E. Indoor storage building or warehouse. F. Laundry...' -> warehouse by-right; self-storage not "
        "a named use (grounded conditional via warehouse-by-right convention).")
Q_NOSTORE = ("Self-storage/mini-warehouse is NOT a named use in Ch. 280. § 280-42 CO permits only a bank "
             "'security-vault storage building' (not self-storage); C-2 permits 'Indoor storage building "
             "or warehouse in conjunction with a retail store' (accessory only). Per-district lists are "
             "closed ('may be erected or used ... for any of the following purposes').")
Q_LGC = ("No named vehicle garage-condo principal use anywhere in Ch. 280; per-district permissive use "
         "lists are closed -> lgc prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 280", "ordinance": ORD} for q in qs]


N_C3 = ("ss/mw CONDITIONAL (GROUNDED, self-storage UNNAMED -> via convention): § 280-55.E 'Indoor storage "
        "building or warehouse' by-right in C-3. li PERMITTED: wholesale + contractor's shop + warehouse "
        "by-right. lgc PROHIBITED. NOTE: C-3 has 0 parcels >=1.5ac in the wealth ring -> 0 needles.")
N_COMPROHIB = ("All prohibited. No self-storage/warehouse standalone use in this commercial/business/lab "
               "district (CO = office/bank-vault only; C-2 warehouse is accessory-to-retail); closed "
               "per-district use list; no named garage-condo use.")
N_RES = ("All prohibited. Residence / Agricultural-Conservation district: no commercial storage or "
         "warehouse use; closed per-district use list; no named garage-condo use.")
N_INST = ("All prohibited. #38: PI = Planned INSTITUTIONAL, PLU = Public Land Use (NOT industrial) — no "
          "self-storage/warehouse use; closed list.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-1","R-1 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1A","R-1A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2","R-2 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3","R-3 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-4","R-4 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5","R-5 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-6","R-6 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("PA","PA Planned Apartment","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("AC","AC Agricultural-Conservation","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-1/D-M","R-1 w/ Density-Mod overlay","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("AC/D-M","AC w/ Density-Mod overlay","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("R-3/D-M","R-3 w/ Density-Mod overlay","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("R-4/D-M","R-4 w/ Density-Mod overlay","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("CO","CO Commercial-Office","prohibited","prohibited","prohibited","prohibited",0.85,N_COMPROHIB),
    ("C-1","C-1 Local Commercial","prohibited","prohibited","prohibited","prohibited",0.85,N_COMPROHIB),
    ("C-2","C-2 General Commercial","prohibited","prohibited","prohibited","prohibited",0.83,N_COMPROHIB),
    ("C-3","C-3 Service Commercial","conditional","conditional","permitted","prohibited",0.80,N_C3),
    ("PB","PB Planned Business","prohibited","prohibited","prohibited","prohibited",0.85,N_COMPROHIB),
    ("PLO","PLO Planned Laboratory-Office","prohibited","prohibited","prohibited","prohibited",0.85,N_COMPROHIB),
    ("PI","PI Planned Institutional","prohibited","prohibited","prohibited","prohibited",0.88,N_INST),
    ("PLU","PLU Public Land Use","prohibited","prohibited","prohibited","prohibited",0.88,N_INST),
    ("WBOD","Wayne Business Overlay","prohibited","prohibited","prohibited","prohibited",0.80,N_COMPROHIB),
    ("GH-BC","Garrett Hill Business Center","prohibited","prohibited","prohibited","prohibited",0.82,N_COMPROHIB),
    ("GH-N","Garrett Hill Neighborhood","prohibited","prohibited","prohibited","prohibited",0.82,N_RES),
    ("GH-CR","Garrett Hill Conestoga Rd","prohibited","prohibited","prohibited","prohibited",0.82,N_COMPROHIB),
    ("GH-GA","Garrett Hill Garrett Ave","prohibited","prohibited","prohibited","prohibited",0.82,N_COMPROHIB),
    ("GH-OS","Garrett Hill Open Space","prohibited","prohibited","prohibited","prohibited",0.82,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_C3, Q_NOSTORE, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
            print(f"  {r['zone_code']:9} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
