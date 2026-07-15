"""SLCo human-review — West Valley City M zone (county jid d79e9029, city-filtered).
municipality='West Valley City' (exact parcels.city). Brings the machine-era M-zone needles (99) to
human_reviewed standard. Ring lives on the county jid (per-city WVC jid is ring=0).

Ordinance: West Valley City Municipal Code §7-7-122 Self-Storage Facilities (westvalleycity.municipal.codes,
Cloudflare-JS → Playwright headless). Verbatim: "Self-Storage Facilities are only allowed in the
Manufacturing (M) Zone ..." (§7-7-122(1)). Per §7-6-301 / FAQ: permitted in M when NOT adjacent to a
residential/ag use or zone; conditional when adjacent; prohibited in the Decker Lake Station / Jordan
River / Bangerter Highway / 5600 West overlay zones. → self-storage is a NAMED use CONFINED to M.

M = self_storage PERMITTED (named, by-right primary case), mini_warehouse PERMITTED, li PERMITTED
(Manufacturing), lgc prohibited. Confirms the machine verdict (M permitted) → 99 needles to human standard.
Self-storage is confined to M, so all other WVC zones remain prohibited (no needle leak).

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_slco_westvalley.py
"""
import asyncio, json, asyncpg

JID = "d79e9029-0f0c-4ac5-9337-64ed581df883"  # Salt Lake County jid (county-model, city-filtered)
MUNI = "West Valley City"
ORD = "West Valley City Municipal Code §7-7-122 (westvalleycity.municipal.codes)"
SUB = "WVC MC §7-7-122 Self-Storage Facilities; §7-6-301 (M zone uses)"
Q_SS = ("WVC MC §7-7-122(1): 'Self-Storage Facilities are only allowed in the Manufacturing (M) Zone ...'. "
        "Permitted in M when not adjacent to a residential/agricultural use or zone; conditional when "
        "adjacent; prohibited in the Decker Lake Station / Jordan River / Bangerter Highway / 5600 West overlays.")

def cite():
    return [{"quote": Q_SS, "section": "§7-7-122", "ordinance": ORD}]

NOTE = ("ss/mw PERMITTED (named, by-right) — §7-7-122 'Self-Storage Facilities are only allowed in the "
        "Manufacturing (M) Zone'. Conditional if residential/ag-adjacent; prohibited in 4 named overlays "
        "(parcel-level nuance). li PERMITTED (Manufacturing). lgc prohibited. Confirms machine M verdict.")

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,'permitted','permitted','permitted','prohibited',$5::jsonb,$6,$7,true,'human',$8,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage='permitted', mini_warehouse='permitted',
 light_industrial='permitted', luxury_garage_condo='prohibited', citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        await con.execute(SQL, JID, "M", "M Manufacturing", MUNI, json.dumps(cite()), SUB, 0.85, NOTE)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, human_reviewed hr, confidence
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code='M' AND deleted_at IS NULL""",
            JID, MUNI)
        for r in rr:
            print(f"CATCH #42 — {MUNI} M: ss={r['ss']} hr={r['hr']} conf={r['confidence']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
