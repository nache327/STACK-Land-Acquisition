"""White Plains NY (in Westchester jid 3e706886) — Stage-4 grounding. municipality='White Plains'
(exact parcels.city). The deferred Westchester item. Ring present (2,372 wealth&1.5ac town-wide).

Ordinance: City of White Plains Zoning Ordinance (amended through 2-5-2024; city PDF DocumentCenter/8865
— the Municode "Code of Ordinances" Ch. 9-2 explicitly excludes the zoning ordinance). Use table is the
per-district schedule (Section 5). Column alignment done by pdfplumber x-position (page 81 industrial
block); validated: Manufacturing / Printing / Wholesale-storage-warehousing / "Mini-storage facility"
all = PP (permitted principal) in the Light Industrial column (x≈912.6, header IL / DB code "LI").

SELF-STORAGE NAMED + CONFINED TO LI: the use table row "'Mini-storage facility'" = PP in the LI/IL
column ONLY (single cell); §4.4.28 defines "Mini-storage facility" = "A self-storage facility ...
self-service storage units." It is NOT permitted in CB-* (Central Business), B-*, RM-* (multifamily),
or any other district (mini-storage appears in no other column; the wholesale-only business columns get
"Wholesale businesses, storage or warehousing" but NOT mini-storage). → self_storage permitted only in LI.

LI = self_storage/mini_warehouse PERMITTED (named, by-right; §4.4.28 dimensional standards apply),
li PERMITTED (manufacturing/printing/wholesale by-right), lgc prohibited. NEEDLE = 5 (LI wealth&1.5ac).
CB-4 (335 w15) / RM-* / BR-2 clear the ring but permit no self-storage → correct no-op.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_white_plains_ny.py
"""
import asyncio, json, asyncpg

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"
MUNI = "White Plains"
ORD = "City of White Plains Zoning Ordinance, amended through 2-5-2024 (city PDF DocumentCenter/8865)"
SUB = "WP Zoning Ord. Use Table (Section 5, LI/Industrial column); §4.4.28 Mini-storage facility"
Q_SS = ("WP Zoning Ordinance use table: row \"'Mini-storage facility'\" = PP (permitted) in the Light "
        "Industrial (LI) column only. §4.4.28: 'Mini-storage facility — A self-storage facility ... "
        "self-service storage units ...'.")
Q_CONF = ("Mini-storage appears in no district column except LI (x-aligned). CB-*, B-*, RM-* and other "
          "districts do not permit mini-storage → self-storage confined to LI. No luxury-garage-condo use "
          "→ lgc prohibited.")

def cite():
    return [{"quote": q, "section": "WP Zoning Ord.", "ordinance": ORD} for q in (Q_SS, Q_CONF)]

N_LI = ("ss/mw PERMITTED (named, by-right) — use table \"'Mini-storage facility'\" = PP in LI; §4.4.28 "
        "defines it as a self-storage facility. li PERMITTED (manufacturing/printing/wholesale PP). lgc prohibited.")
N_COM = ("ss/mw PROHIBITED — mini-storage/self-storage is named & confined to LI; this district permits no "
         "mini-storage. lgc prohibited.")
N_RES = "ss/mw PROHIBITED — residential (multifamily) district; no self-storage use. lgc prohibited."

# code, name, ss, mw, li, lgc, conf, note
ROWS = [
    ("LI", "LI Light Industrial", "permitted", "permitted", "permitted", "prohibited", 0.85, N_LI),
    ("CB-4", "CB-4 Central Business", "prohibited", "prohibited", "prohibited", "prohibited", 0.82, N_COM),
    ("CB-3", "CB-3 Central Business", "prohibited", "prohibited", "prohibited", "prohibited", 0.82, N_COM),
    ("CB-2", "CB-2 Central Business", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("CB-1", "CB-1 Central Business", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("B-6", "B-6 Business", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("C-O", "C-O Commercial Office", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("BR-2", "BR-2 Business/Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.78, N_COM),
    ("RM-2", "RM-2 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES),
    ("RM-1.5", "RM-1.5 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES),
    ("RM-0.4", "RM-0.4 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES),
    ("RM-0.35", "RM-0.35 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES),
]

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
        for zc, zn, ss, mw, li, lgc, conf, note in ROWS:
            await con.execute(SQL, JID, zc, zn, MUNI, ss, mw, li, lgc, json.dumps(cite()), SUB, conf, note)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[])
            AND deleted_at IS NULL ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""",
            JID, MUNI, [r[0] for r in ROWS])
        print(f"CATCH #42 — {MUNI} ({len(rr)}):")
        for r in rr:
            mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:8} ss={r['ss']:11} li={r['li']:11}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
