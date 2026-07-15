"""Bellevue WA (jid 71a53bba) — Bel-Red (BR-*) + office upside. municipality='Bellevue'.
Follows the main LI/GC grounding (_apply_bellevue_wa.py, 46 needles). Ring already precomputed.

Sources (Cloudflare-JS-gated bellevue.municipal.codes fetched via Playwright headless):
 - Bel-Red use table: LUC Part 20.25D (BelRed), use chart. Column order verified by <td> index and
   validated against a broadly-permitted row ("61 Finance… P 9/P 9 | P/P | P | P | P | P | P"):
   [BR-MO/MO-1] [BR-OR/OR-1/OR-2] [BR-RC-1/2/3] [BR-R] [BR-GC] [BR-CR] [BR-ORT].
 - Office/CB: LUC Chart 20.10.440 (broker-PDF reproduction, x-aligned) — see _apply_bellevue_wa.py.

BEL-RED FINDING: use "637 Warehousing and Storage Services, Excluding Stockyards" = **P in BR-GC** and
**P/ (inside-node) in BR-OR/OR-1/OR-2**; BLANK (not permitted) in BR-MO, BR-RC, BR-R, BR-CR, BR-ORT.
No named self-storage/self-service/mini-storage use anywhere in Bel-Red → self-storage unnamed →
warehouse-permitted-by-right ⇒ self_storage/mini_warehouse CONDITIONAL in BR-GC + BR-OR family; li
PERMITTED. lgc prohibited. (Bel-Red is a TOD corridor replacing its light-industrial past — warehousing
survives by-right only in GC + OR-inside-node; conditional is the appropriate self-storage verdict.)

OFFICE/CB FINDING (part 2 — NO upside): Chart 20.10.440 row 637 is BLANK in O/OLB/OLB2/PO (office does
NOT permit warehousing) and 'S' (special, not by-right) in CB. No named self-storage. → office/CB
self_storage PROHIBITED (not arm-able on a principal by-right basis).

NEEDLES added ≈ 39 (BR-GC 25 + BR-OR 8 + BR-OR-1 1 + BR-OR-2 5 wealth&1.5ac). Other BR-* + office/CB
grounded prohibited (document the no-op / override machine templates).

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_bellevue_belred.py
"""
import asyncio, json, asyncpg

JID = "71a53bba-8697-4b8d-93e9-e3de091b8706"
MUNI = "Bellevue"
ORD = "City of Bellevue LUC Part 20.25D (BelRed use table); Chart 20.10.440 (office/CB)"
SUB = "LUC 20.25D BelRed use table (637 Warehousing); LUC Chart 20.10.440 (637 in O/OLB/OLB2/CB)"
Q_BR = ("LUC Part 20.25D BelRed use table, '637 Warehousing and Storage Services, Excluding Stockyards' = "
         "P in the BR-GC column and P/ (inside-node) in the BR-OR/OR-1/OR-2 column; blank in BR-MO/RC/R/CR/ORT.")
Q_CONV = ("Bel-Red names no self-storage/self-service/mini-storage use → self-storage unnamed; "
          "warehouse-permitted-by-right ⇒ self_storage/mini_warehouse CONDITIONAL (convention). lgc prohibited.")
Q_OFF = ("LUC Chart 20.10.440 '637 Warehousing and Storage' is blank in O/OLB/OLB2/PO (office does not permit "
         "warehousing) and 'S' (special, not by-right) in CB → not arm-able; no named self-storage.")

def cite(*qs):
    return [{"quote": q, "section": "LUC 20.25D / 20.10.440", "ordinance": ORD} for q in qs]

N_BR_YES = ("ss/mw CONDITIONAL via warehouse-by-right convention (LUC 20.25D use 637 Warehousing = P by-right "
            "in this Bel-Red district; self-storage unnamed). li PERMITTED. lgc prohibited.")
N_BR_NO = ("ss/mw PROHIBITED — LUC 20.25D use 637 Warehousing is blank (not permitted) in this Bel-Red "
           "district; no named self-storage use. lgc prohibited.")
N_OFF = ("ss/mw PROHIBITED — Chart 20.10.440 warehousing (637) blank in office (O/OLB/OLB2/PO) or 'S' "
         "special/not-by-right (CB); no named self-storage. lgc prohibited.")

# code, ss, mw, li, note, cites
YES = ["BR-GC", "BR-OR", "BR-OR-1", "BR-OR-2"]
BR_NO = ["BR-MO", "BR-MO-1", "BR-RC-1", "BR-RC-2", "BR-RC-3", "BR-R", "BR-CR", "BR-ORT"]
OFF_NO = ["O", "OLB", "OLB2", "CB", "PO", "DT-O-1"]

ROWS = []
for z in YES:
    ROWS.append((z, f"{z} BelRed (warehousing by-right)", "conditional", "conditional", "permitted", 0.78, N_BR_YES, cite(Q_BR, Q_CONV)))
for z in BR_NO:
    ROWS.append((z, f"{z} BelRed", "prohibited", "prohibited", "prohibited", 0.80, N_BR_NO, cite(Q_BR)))
for z in OFF_NO:
    ROWS.append((z, f"{z} Office/Commercial", "prohibited", "prohibited", "prohibited", 0.80, N_OFF, cite(Q_OFF)))

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,'prohibited',$8::jsonb,$9,$10,true,'human',$11,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
 light_industrial=EXCLUDED.light_industrial, luxury_garage_condo='prohibited', citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, zn, ss, mw, li, conf, note, cites in ROWS:
            await con.execute(SQL, JID, zc, zn, MUNI, ss, mw, li, json.dumps(cites), SUB, conf, note)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[])
            AND deleted_at IS NULL ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""",
            JID, MUNI, [r[0] for r in ROWS])
        print(f"CATCH #42 — {MUNI} Bel-Red/office ({len(rr)}):")
        for r in rr:
            mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:10} ss={r['ss']:11} li={r['li']:11}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
