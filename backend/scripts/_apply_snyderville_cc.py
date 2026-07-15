"""Snyderville/Promontory UT (Summit County jid 72492dd8) — Stage-4 grounding of CC. municipality=
'Snyderville/Promontory' (exact parcels.city). Ring present. Resort-commercial residual closer.

Ordinance: Summit County Title 10 Snyderville Basin Development Code, Ch. 2 use table (Municode-mirror
mcclibraryweb, Cloudflare/SPA — fetched via Playwright headless). Use-table columns: RR HS MR CC SC NC.
Row "Storage, self-service" = * * * **L L** *  →  Allowed (L) in **CC** (Community Commercial) and **SC**
(Service Commercial); not in RR/HS/MR/NC. "Warehousing and distribution, limited" also = L in CC/SC.
(L = Allowed Use, C = Conditional, * = not permitted.)

→ CC + SC: self_storage/mini_warehouse PERMITTED (named "Storage, self-service" = L), li PERMITTED
(warehousing/distribution L). lgc prohibited. NEEDLE = CC 3 in-ring (SC 0 in-ring — INDUS/LI/SC corridor
is out of the wealth ring). NC self-service=* → prohibited.

TC (Town Center, 21 in-ring) is NOT in this use table — TC uses are set case-by-case via §10-2-12
(Development within a Town Center/Resort Center) master-plan/development-agreement process, with no fixed
by-right/conditional self-storage entitlement → INDETERMINATE, not grounded (no verbatim permission, #37).
Documented in outputs for coordinator; no forced verdict.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_snyderville_cc.py
"""
import asyncio, json, asyncpg

JID = "72492dd8"  # resolved at runtime
MUNI = "Snyderville/Promontory"
ORD = "Summit County Title 10 Snyderville Basin Development Code, Ch. 2 Use Table (Municode-mirror)"
SUB = "Title 10 Ch. 2 Use Table (Storage, self-service = L in CC/SC); §10-2-12 (TC master-plan)"
Q_SS = ("Title 10 Ch. 2 Use Table, row 'Storage, self-service' = L (Allowed) in the CC (Community "
        "Commercial) and SC (Service Commercial) columns; * (not permitted) in RR/HS/MR/NC.")
Q_CONF = ("Self-service storage Allowed (L) only in CC/SC. TC (Town Center) is not in this use table — TC "
          "uses are set via §10-2-12 master-plan process (no fixed self-storage entitlement). No "
          "luxury-garage-condo use → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "Title 10 Ch. 2", "ordinance": ORD} for q in (Q_SS, Q_CONF)]

N_YES = ("ss/mw PERMITTED — Title 10 Ch. 2 Use Table 'Storage, self-service' = L (Allowed) in this district; "
         "'Warehousing and distribution, limited' = L. li PERMITTED. lgc prohibited.")
N_NC = ("ss/mw PROHIBITED — 'Storage, self-service' = * (not permitted) in NC; no self-storage. lgc prohibited.")

ROWS = [
    ("CC", "CC Community Commercial", "permitted", "permitted", "permitted", 0.82, N_YES),
    ("SC", "SC Service Commercial", "permitted", "permitted", "permitted", 0.82, N_YES),
    ("NC", "NC Neighborhood Commercial", "prohibited", "prohibited", "prohibited", 0.82, N_NC),
]

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
        jid = await con.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", JID + "%")
        await con.execute("SET statement_timeout='60s'")
        for zc, zn, ss, mw, li, conf, note in ROWS:
            await con.execute(SQL, jid, zc, zn, MUNI, ss, mw, li, json.dumps(cite()), SUB, conf, note)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, light_industrial::text li
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[])
            AND deleted_at IS NULL ORDER BY zone_code""", jid, MUNI, [r[0] for r in ROWS])
        print(f"CATCH #42 — {MUNI} ({len(rr)}):")
        for r in rr:
            mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:4} ss={r['ss']:11} li={r['li']:11}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
