"""Chester Heights Borough PA (Delaware Co) — Stage-4 close (2026-07-14). NEEDLE = MHP only.

KEY CATCH: self-storage IS a named use, but § 185-110.1.A permits it BY CONDITIONAL USE ONLY in the
Mobile Home Park (MHP) District. Because self-storage is named AND explicitly confined to MHP, the
warehouse-by-right convention does NOT override that exclusion in B / LI (coordinator rule:
"named-separately ⇒ convention doesn't override an explicit exclusion"). So the wealthy Business (B)
and Limited Industrial (LI) land yields NO self-storage needle; the only self-storage needle is the
MHP district (2 parcels >=1.5ac in the wealth ring).

PA spatially bound -> NO rebind. Verdicts keyed on parcel zoning_code (municipality = 'Chester Heights Borough').

Grounding — Borough of Chester Heights, PA Code Ch. 185 Zoning (eCode360 CH2012, full chapter via
print?guid=12777187). Permissive per-district use lists ("... for any of the following purposes, and no
other" = closed list).
  ss/mw CONDITIONAL in MHP only: § 185-110.1.A "Self-storage facilities shall be permitted by
    conditional use in a Mobile Home Park Zoning District" (added 9-13-2004 Ord. 174). Not listed in
    any other district -> prohibited elsewhere.
  li PERMITTED in LI: § 185-81 "A building may be erected, altered or used ... for any of the following
    purposes, and no other: A. office; B. Industrial research laboratories; C. Manufacture, compounding,
    processing, assembly, treatment and packaging of [cosmetics/electronics/pharma/plastics/textiles/
    toys/etc.]" -> light manufacturing by-right. NO warehouse and NO self-storage in the LI closed list.
  B Business § 185-72 (current, amended 4-21-2025): retail(<=10k sf)/restaurant/personal-service/office/
    bank + accessory 'Storage within a completely enclosed building in conjunction with a permitted use'
    only -> no self-storage, no standalone warehouse, no manufacturing -> ss/mw + li prohibited.
  lgc PROHIBITED everywhere: no named vehicle garage-condo use; closed lists.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim
citations (#37), named-use-confinement over convention, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_delaware_pa_chester_heights.py
"""
import asyncio, json, asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Chester Heights Borough"
CITED_SUBSECTION = "§ 185-110.1.A (self-storage); § 185-81 (LI); § 185-72 (B)"
ORD = ("Borough of Chester Heights, PA Code Ch. 185 Zoning (eCode360 CH2012), permissive per-district "
       "use regulations")

Q_SS = ("§ 185-110.1.A: 'Self-storage facilities shall be permitted by conditional use in a Mobile Home "
        "Park Zoning District, provided that the self-storage facility complies with the following...' "
        "(added 9-13-2004 Ord. 174). Self-storage is not listed in any other district.")
Q_LI = ("§ 185-81 (LI Limited Industrial): 'A building may be erected, altered or used ... for any of the "
        "following purposes, and no other: A. office; B. Industrial research laboratories; C. Manufacture, "
        "compounding, processing, assembly, treatment and packaging of such products as cosmetics ... "
        "textiles, and toys.' No warehouse and no self-storage in the closed list.")
Q_B = ("§ 185-72 (B Business, amended 4-21-2025): retail (<=10,000 sf), restaurant, personal service, "
       "office, bank + accessory 'Storage within a completely enclosed building in conjunction with a "
       "permitted use' only. No self-storage, no standalone warehouse, no manufacturing.")
Q_LGC = ("No named vehicle garage-condo principal use in Ch. 185; per-district use lists are closed "
         "('and no other') -> lgc prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 185", "ordinance": ORD} for q in qs]


N_MHP = ("ss/mw CONDITIONAL (GROUNDED): § 185-110.1.A 'Self-storage facilities shall be permitted by "
         "conditional use in a Mobile Home Park Zoning District' — the ONLY district permitting "
         "self-storage. li prohibited (residential MHP). lgc PROHIBITED.")
N_LI = ("ss/mw PROHIBITED: self-storage is named and confined to MHP (§ 185-110.1.A); LI closed list "
        "(§ 185-81 'and no other') has no warehouse/self-storage -> convention does not override the "
        "explicit exclusion. li PERMITTED (GROUNDED): § 185-81.C light manufacturing by-right. lgc PROHIBITED.")
N_B = ("ss/mw PROHIBITED: self-storage confined to MHP; § 185-72 B Business permits only retail/office/"
       "service + accessory conjunctive storage. li PROHIBITED (no manufacturing/warehouse). lgc PROHIBITED.")
N_PROHIB = ("All prohibited. Self-storage confined to MHP (§ 185-110.1.A); no warehouse/manufacturing/"
            "self-storage in this district's closed use list; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-1","R-1 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("R1-1/2","R-1 1/2 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("R-1A","R-1A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("RA","RA Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("PRD","Planned Residential Development","prohibited","prohibited","prohibited","prohibited",0.88,N_PROHIB),
    ("PLO","PLO Planned Laboratory-Office","prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("B","B Business","prohibited","prohibited","prohibited","prohibited",0.88,N_B),
    ("LI","LI Limited Industrial","prohibited","prohibited","permitted","prohibited",0.88,N_LI),
    ("MHP","Mobile Home Park","conditional","conditional","prohibited","prohibited",0.86,N_MHP),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_B, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
