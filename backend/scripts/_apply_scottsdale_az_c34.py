"""Scottsdale AZ (jid 8e31ce3a) — PART 2: arm C-3/C-4 via warehouse-by-right convention (coordinator greenlight).

Confirmed from Table 11.201.A (Municode client 4271/product 10075/job 425135): "Wholesale, warehouse and
distribution" = P (PRINCIPAL permitted use, by-right, no footnote) in C-3, C-4 — the SAME row-basis used
for I-1/I-G. Self-storage/mini-warehouse is unnamed in the table → warehouse-by-right convention ⇒
ss/mw CONDITIONAL, li PERMITTED, lgc prohibited. (NOT armed off the accessory "Internalized community
storage" entry, per instruction.)

Grounds the 8 C-3/C-4 zoning_code variants that carry wealth&1.5ac parcels (base district governs;
PCD/ESL/(C) overlays don't change the by-right warehouse use). Downtown-Overlay / P-3 variants
(C-3 DO, C-3/P-3, C-3 DO HP — all 0 wealth&1.5ac) are intentionally EXCLUDED: the Downtown/Old Town Area
carries use restrictions and those rows are 0-needle regardless (left prohibited).

municipality='SCOTTSDALE' (AZ UPPERCASE). Adds ~106 wealth&1.5ac needles on top of the I-1/I-G 196.
Run: cd backend && PYTHONUTF8=1 python scripts/_apply_scottsdale_az_c34.py
"""
import asyncio, json, asyncpg

JID = "8e31ce3a-67cd-4e62-b975-a4e799b59876"
MUNI = "SCOTTSDALE"
ORD = "City of Scottsdale Zoning Ordinance (Appendix B), Art. XI Table 11.201.A (Municode; job 425135)"
SUB = "Table 11.201.A Land Use Table (C-3, C-4 commercial districts)"
Q_WHSE = ("Table 11.201.A: 'Wholesale, warehouse and distribution' = P (principal permitted use, by-right) "
          "in the C-3 and C-4 columns (same row that grounds I-1/I-G).")
Q_CONV = ("No 'self-storage' / 'mini-storage' / 'mini-warehouse' use row exists in Table 11.201.A → "
          "self-storage is unnamed; warehouse-permitted-by-right ⇒ self_storage/mini_warehouse CONDITIONAL "
          "(established convention). Not armed off the accessory 'Internalized community storage' entry. "
          "No luxury-garage-condo use listed → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "Table 11.201.A", "ordinance": ORD} for q in (Q_WHSE, Q_CONV)]

NOTE = ("ss/mw CONDITIONAL via warehouse-by-right convention (Table 11.201.A 'Wholesale, warehouse and "
        "distribution' = P principal in C-3/C-4; self-storage unnamed). li PERMITTED (warehouse/distribution "
        "by-right). lgc prohibited. Overlay suffix (PCD/ESL/(C)) does not change base-district permission; "
        "Downtown-Overlay (DO) / P-3 variants excluded.")

VARIANTS = ["C-3", "C-3 PCD", "C-3 PCD (C)", "C-3 (C)", "C-3 PCD ESL",
            "C-4", "C-4 (C)", "C-4 PCD"]

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
        for zc in VARIANTS:
            base = "C-3 Highway Commercial" if zc.startswith("C-3") else "C-4 Central Commercial"
            zn = base + ("" if zc in ("C-3", "C-4") else f" [{zc}]")
            await con.execute(SQL, JID, zc, zn, MUNI, json.dumps(cite()), SUB, 0.78, NOTE)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li, human_reviewed hr
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[])
            AND deleted_at IS NULL ORDER BY zone_code""", JID, MUNI, VARIANTS)
        print(f"CATCH #42 — {MUNI} C-3/C-4 grounded ({len(rr)}):")
        for r in rr:
            print(f"  {r['zone_code']:16} ss={r['ss']:11} li={r['li']:11} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
