"""Monroe Township NJ (Middlesex Co) — Stage-4 grounding (2026-07-14). NEEDLE = L-I only.

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'Monroe township' (exact parcels.city).
Source: Township of Monroe NJ Code Ch. 108 Art. VI Zoning District Regulations (eCode360 MO0544, full
article via print?guid=35513835). No global closed-list clause → per-district enumerated permitted uses.

NJ SELF-STORAGE CATCH: self-storage NAMED NOWHERE (0 mentions). Warehouse/"storage establishments" appears
in exactly two districts:
  - L-I Light Industrial §108-6.19.A(2): "Fully enclosed wholesale, distributive or storage establishments,
    but excluding retail sales" = PERMITTED (by-right) → warehouse-by-right + self-storage unnamed ⇒ ss/mw
    CONDITIONAL (convention; "storage establishments" is a real storage use, Berkeley-Heights). li PERMITTED
    (§108-6.19.A(1) assembly/finishing by-right + D(1) light manufacturing conditional).
  - H-D Highway Development §108-6.18.D(11): "Wholesale, distributive and storage establishments" is only a
    CONDITIONAL use (must have Route 33 frontage) — NOT by-right. Per the convention rule, a conditional-only
    warehouse does NOT trigger the self-storage convention; self-storage unnamed → PROHIBITED. HD's permitted
    uses (A(1)-(11), amended 10-6-2025) are offices/retail/auto/restaurant/hotel — no manufacturing → li
    prohibited too. (The 60 HD wealth-ring lots are a correct no-op, not a needle.)
NEEDLE (wealth-ring ≥1.5ac): L-I = 55 (conditional).

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
per-district sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_mdx_monroe.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "9c039328-c995-41fc-83ce-fb4966fd402b"
MUNI = "Monroe township"
CITED = "§ 108-6.19.A(2) (L-I storage by-right → ss conditional); § 108-6.19.A(1)/D(1) (li); § 108-6.18.D(11) (H-D storage conditional-only → prohibited)"
ORD = "Township of Monroe, NJ Code Ch. 108 Art. VI Zoning District Regulations (eCode360 MO0544)"

Q_SS_LI = ("§ 108-6.19.A (L-I Light Industrial District) Permitted uses: '(2) Fully enclosed wholesale, "
           "distributive or storage establishments, but excluding retail sales, subject to the performance "
           "standards of Article V.' (Warehouse/storage by-right; self-storage unnamed → conditional by convention.)")
Q_LI_LI = ("§ 108-6.19.A(1) 'Assembly and finishing of materials or products'; § 108-6.19.D(1) 'Light "
           "manufacturing, converting, processing, printing or other handling of materials or products' (conditional).")
Q_HD = ("§ 108-6.18 H-D Highway Development District: permitted uses A(1)-(11) are offices/entertainment/"
        "shopping/auto sales/machinery sale-repair/data/restaurants/medical/banks/law/hotels (amended "
        "10-6-2025). 'Wholesale, distributive and storage establishments' is a CONDITIONAL use only "
        "(§ 108-6.18.D(11), Route 33 frontage required) → convention (warehouse-by-right→ss conditional) does "
        "NOT apply to a conditional-only warehouse; self-storage unnamed → prohibited.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 108 Art. VI", "ordinance": ORD} for q in qs]


N_LI = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): § 108-6.19.A(2) 'wholesale, distributive or storage "
        "establishments' permitted by-right; self-storage unnamed → conditional by convention. li PERMITTED: "
        "§ 108-6.19.A(1) assembly/finishing + D(1) light manufacturing. lgc PROHIBITED.")
N_HD = ("All prohibited. H-D Highway Development: 'Wholesale, distributive and storage establishments' is a "
        "CONDITIONAL use only (§ 108-6.18.D(11)) — convention does not apply to conditional-only warehouse; "
        "self-storage unnamed; permitted uses are office/retail/auto/hotel, no manufacturing → li prohibited. "
        "The 60 HD wealth-ring lots are a correct no-op.")
N_OFF = "All prohibited. Office/commercial district (offices/retail/service); no warehouse/storage/self-storage/manufacturing permitted use."
N_PRC = "All prohibited. Planned Retirement Community / planned residential district; no self-storage/warehouse/manufacturing use."
N_FHC = "All prohibited. FHC Flood Hazard/Conservation District: conservation; no self-storage/warehouse/industrial use."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/manufacturing use; no named garage-condo use."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("LI","L-I Light Industrial","conditional","conditional","permitted","prohibited",0.85,N_LI),
    ("HD","H-D Highway Development","prohibited","prohibited","prohibited","prohibited",0.85,N_HD),
    ("NC","N-C Neighborhood Commercial","prohibited","prohibited","prohibited","prohibited",0.86,N_OFF),
    ("OP","OP Office Professional","prohibited","prohibited","prohibited","prohibited",0.86,N_OFF),
    ("PO/CD","PO/CD Planned Office Commercial","prohibited","prohibited","prohibited","prohibited",0.86,N_OFF),
    ("FHC","FHC Flood Hazard/Conservation","prohibited","prohibited","prohibited","prohibited",0.88,N_FHC),
    ("PRC","PRC Planned Retirement Community","prohibited","prohibited","prohibited","prohibited",0.90,N_PRC),
    ("PRC-2","PRC-2 Planned Retirement Community 2","prohibited","prohibited","prohibited","prohibited",0.90,N_PRC),
    ("PRC-3","PRC-3 Planned Retirement Community 3","prohibited","prohibited","prohibited","prohibited",0.90,N_PRC),
    ("PD-SH","PD-SH Planned Development","prohibited","prohibited","prohibited","prohibited",0.85,N_PRC),
    ("PD-AH/NC","PD-AH/NC Planned Development-Affordable","prohibited","prohibited","prohibited","prohibited",0.85,N_PRC),
    ("PRD-AH","PRD-AH Planned Residential-Affordable","prohibited","prohibited","prohibited","prohibited",0.88,N_PRC),
    ("PRGC","PRGC Planned Retirement Golf Community","prohibited","prohibited","prohibited","prohibited",0.88,N_PRC),
    ("MU-HD-R-AH","MU-HD-R-AH Mixed Use-Affordable","prohibited","prohibited","prohibited","prohibited",0.82,N_PRC),
    ("R-3A","R-3A Residential-Agricultural","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5","R-5 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-7.5","R-7.5 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-10","R-10 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-20","R-20 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-30","R-30 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-60","R-60 Residential","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_LI, Q_LI_LI, Q_HD), "cited_subsection": CITED,
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
            print(f"  {r['zone_code']:11} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
