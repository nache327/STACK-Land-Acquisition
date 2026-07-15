"""Bellevue WA (jid 71a53bba) — Stage-4 grounding of LI + GC via warehouse-by-right convention.
municipality='Bellevue' (exact parcels.city, WA mixed-case). Ring-precompute done (40 tracts) →
978 wealth&1.5ac town-wide.

Ordinance: Bellevue Land Use Code (LUC) Chart 20.10.440 "Uses in land use districts". The city site
(bellevue.municipal.codes) is Cloudflare-JS-gated; chart obtained from a static reproduction (broker PDF
of Chart 20.10.440) and cross-checked to LUC 20.10.300 (LI district purpose). Non-residential column
order verified: PO O OLB OLB2 **LI GC** NB NMU CB F1 F2 F3.

Use row "637 Warehousing and Storage Services, Excluding Stockyards" — cell x-positions aligned to the
district header (consistent −6.4pt offset): **LI = P, GC = P** (permitted by-right); CB / F1 = S (special,
NOT clean by-right). Bellevue names NO distinct self-storage / mini-storage / mini-warehouse use → self-
storage is unnamed → warehouse-permitted-by-right ⇒ self_storage / mini_warehouse = CONDITIONAL,
light_industrial = PERMITTED, lgc prohibited. (LUC 20.10.300: LI = "manufacturing, wholesale trade and
distribution activities" — corroborates warehousing by-right.)

NEEDLES = 46 (LI 28 + GC 18 wealth&1.5ac). NOT armed (need column-verified Bel-Red chart 20.10.375 /
office-district confirmation, JS-blocked): O(54)/OLB(42)/OLB2(26)/CB(25 'S') office/commercial and the
BR-* Bel-Red corridor zones (BR-GC 25, BR-CR 19, …) — flagged for coordinator.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_bellevue_wa.py
"""
import asyncio, json, asyncpg

JID = "71a53bba-8697-4b8d-93e9-e3de091b8706"
MUNI = "Bellevue"
ORD = "City of Bellevue Land Use Code (LUC) Chart 20.10.440; LI district LUC 20.10.300"
SUB = "LUC Chart 20.10.440 (use 637 Warehousing and Storage); LUC 20.10.300 (LI)"
Q_WHSE = ("LUC Chart 20.10.440, use '637 Warehousing and Storage Services, Excluding Stockyards' = P "
          "(permitted) in the LI and GC districts (cell x-positions aligned to the district header).")
Q_LI = ("LUC 20.10.300: the Light Industrial (LI) District provides for 'manufacturing, wholesale trade "
        "and distribution activities.'")
Q_CONV = ("Bellevue LUC names no distinct self-storage / mini-storage / mini-warehouse use → self-storage "
          "unnamed; warehouse-permitted-by-right ⇒ self_storage/mini_warehouse CONDITIONAL (convention). "
          "No luxury-garage-condo use → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "LUC 20.10", "ordinance": ORD} for q in (Q_WHSE, Q_LI, Q_CONV)]

NOTE = ("ss/mw CONDITIONAL via warehouse-by-right convention (Chart 20.10.440 use 637 = P in this district; "
        "self-storage unnamed). li PERMITTED (warehousing/distribution/manufacturing by-right). lgc prohibited.")

ROWS = [
    ("LI", "LI Light Industrial"),
    ("GC", "GC General Commercial"),
]

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,'conditional','conditional','permitted','prohibited',$5::jsonb,$6,$7,true,'human',$8,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage='conditional', mini_warehouse='conditional',
 light_industrial='permitted', luxury_garage_condo='prohibited', citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, zn in ROWS:
            await con.execute(SQL, JID, zc, zn, MUNI, json.dumps(cite()), SUB, 0.80, NOTE)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[])
            AND deleted_at IS NULL ORDER BY zone_code""", JID, MUNI, [r[0] for r in ROWS])
        print(f"CATCH #42 — {MUNI} grounded ({len(rr)}):")
        for r in rr:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} li={r['li']:11} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
