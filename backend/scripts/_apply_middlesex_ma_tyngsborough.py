"""Tyngsborough MA — Stage-4 FULL close (2026-07-09). Zero held cells. 8 base districts.

TIER-1. NEEDLE MUNI: self-storage / mini-warehouse is a named use permitted by special
permit in I-1 (Light Industrial) + B-4 -> real armed candidates.

Grounding — Town of Tyngsborough Zoning Bylaw, May 6 2025 (tyngsboroughma.gov
DocumentCenter/View/2000), §4 Use Regulations Table of Uses:
  CLOSED-LIST (§4.1): "No land shall be used, and no structure shall be erected or used, except
    as in conformity with the Table of Uses... Any building or use of premises not explicitly
    permitted is prohibited." Legend (§4.3): P=permitted; O=prohibited; PB=Special Permit-Planning
    Board; SB=Special Permit-Board of Selectmen; SPR=Site Plan Review.
  ss/mw CONDITIONAL in B-4, I-1: "Mini-Warehouse" (= mini-warehouse/self-storage, §3.10.24) = PB
    in B-4 and I-1; O (prohibited) in R-1/R-2/R-3/B-1/B-2/B-3. "Warehouse" = PB in B-4/I-1 too.
  li PERMITTED in I-1: "Light Manufacturing" = P (by-right) in I-1; PB in B-4; O elsewhere.
    ("Heavy Manufacturing" = PB in I-1.)
  lgc PROHIBITED everywhere: generic "Storage" (principal use) = O in every district; no named
    garage-condo / automotive-storage principal use; "Private garage...for not more than four
    motor vehicles" is accessory-only (§4.4). Closed-list (§4.1) -> unnamed garage-condo prohibited
    (consistent w/ Wilmington ledger #58 + Woburn).

Rebind: NMCOG layer 18 (field CODE); vocab matches the CURRENT May-2025 bylaw §3.1 exactly
(Hudson check PASS), gates a/b/d PASS, 0 orphans, 100% changed = hyphen normalization
(R1->R-1, I1->I-1, B3->B-3) + minor spatial corrections. Executable apply (Dedham template):
idempotent human-UPSERT via asyncpg, muni-scoped (#33), verbatim citations (#37), verify-and-
print (#42), catch #56 alignment via matrix row read.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_tyngsborough.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "TYNGSBOROUGH"
CITED_SUBSECTION = "§4.3 Table of Uses (Warehouse/Mini-Warehouse/Manufacturing) + §4.1"
ORD = ("Town of Tyngsborough Zoning Bylaw, May 6 2025 (tyngsboroughma.gov DocumentCenter/View/2000), "
       "§4 Use Regulations Table of Uses")

Q_CLOSED = ("§4.1: 'No land shall be used, and no structure shall be erected or used, except as in "
            "conformity with the Table of Uses... Any building or use of premises not explicitly "
            "permitted is prohibited.' Legend §4.3: P=permitted; O=prohibited; PB=Special "
            "Permit-Planning Board; SB=Special Permit-Board of Selectmen; SPR=Site Plan Review.")
Q_SS = ("§4.3 Table of Uses 'Mini-Warehouse' (mini-warehouse/self-storage, def. §3.10.24) = PB in B-4 "
        "and I-1; O in R-1/R-2/R-3/B-1/B-2/B-3. 'Warehouse' = PB in B-4/I-1; O elsewhere.")
Q_LI = ("§4.3 Table of Uses 'Light Manufacturing' = P (by-right) in I-1; PB in B-4; O in all other "
        "districts. 'Heavy Manufacturing' = PB in I-1. 'Storage' (principal use) = O in every district.")
Q_LGC = ("No named garage-condo / automotive-storage PRINCIPAL use; generic 'Storage' = O everywhere; "
         "'Private garage...for not more than four motor vehicles' is accessory-only (§4.4). Closed-list "
         "(§4.1) -> unnamed garage-condo storage prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "§4", "ordinance": ORD} for q in qs]


N_I1 = ("li PERMITTED (GROUNDED): Light Manufacturing = P (by-right) in I-1. ss/mw CONDITIONAL "
        "(GROUNDED): Mini-Warehouse = PB (special permit) in I-1 (named use). lgc PROHIBITED: generic "
        "'Storage' principal use = O everywhere + no named garage-condo use; closed-list §4.1.")
N_B4 = ("ss/mw CONDITIONAL (GROUNDED): Mini-Warehouse = PB in B-4. li CONDITIONAL: Light Manufacturing "
        "= PB in B-4. lgc PROHIBITED: 'Storage' = O + no named garage-condo use; closed-list §4.1.")
N_PROHIB = ("All prohibited (closed-list §4.1). Mini-Warehouse/Warehouse (PB only in B-4/I-1) and Light "
            "Manufacturing (P only in I-1, PB in B-4) carry O in this district; generic 'Storage' = O; "
            "no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("R-1", "Residential 1 (Low Density)",     "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-2", "Residential 2 (Moderate Density)","prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R-3", "Residential 3 (Multi-Family)",    "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("B-1", "Business 1 (Neighborhood)",       "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("B-2", "Business 2 (Office/Professional)","prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("B-3", "Business 3 (General Shopping)",   "prohibited","prohibited","prohibited","prohibited",0.90,N_PROHIB),
    ("B-4", "Business 4 (Adult Zone)",         "conditional","conditional","conditional","prohibited",0.85,N_B4),
    ("I-1", "Industrial 1 (Light)",            "conditional","conditional","permitted","prohibited",0.92,N_I1),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_CLOSED, Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
