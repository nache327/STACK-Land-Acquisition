"""Lake Oswego OR (jid 2c1736ee) — Stage-4 HUMAN grounding (self-storage verdict layer).
municipality='Lake Oswego' (exact parcels.city). Ring-precompute done (15 tracts) → 399 wealth&1.5ac
town-wide (ring maxHV $804k, clears $475k gate). Overrides the machine template rows (human_reviewed=False)
for the industrial/commercial zones.

Ordinance: Lake Oswego Community Development Code (LOC) Table 50.03.002-2 "Commercial, Mixed Use,
Industrial, and Special Purpose Districts Use Table" (eCode360 node 43075916; curl+UA — NOT Municode).
Column order (verified by <td> index; validated against "Light manufacturing C C P C P P"): NC GC HC OC
EC CR&D MC WLG FMU I IP CI PF PNA OC RMU R-2.5.

SELF-STORAGE IS A NAMED USE, CONFINED TO CI: under Industrial/Manufacturing (§50.03.003.7), row
"Storage — Self-storage facility" = P (permitted by-right) in the CI column ONLY — NOT in IP (Industrial
Park), I (Industrial), CR&D, or any commercial district. Corroborating: "General storage" & "Wholesale
distribution" = P in CI/PF only; "Heavy manufacturing" = P in CI (LO's IP is a clean-tech/biotech campus,
not warehousing). → named-confinement: the warehouse convention does NOT extend self-storage to IP/I.

CI = self_storage/mini_warehouse PERMITTED (named, by-right), li PERMITTED, lgc prohibited. NEEDLE = 4
(CI wealth&1.5ac). IP(16 w15)/I(5)/CR&D(16)/PF(21) clear the ring but permit no self-storage → correct
no-op. Also grounds those industrial/commercial zones prohibited (self-storage confined to CI).

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_lake_oswego_or_ci.py
"""
import asyncio, json, asyncpg

JID = "2c1736ee-48ac-4a6e-aefd-77be215a00c2"
MUNI = "Lake Oswego"
ORD = "City of Lake Oswego Community Development Code (LOC) Table 50.03.002-2 (eCode360 43075916)"
SUB = "LOC Table 50.03.002-2; §50.03.003.7 (Industrial Service and Storage / Self-storage facility)"
Q_SS = ("LOC Table 50.03.002-2, Industrial/Manufacturing uses, 'Storage — Self-storage facility' = P "
        "(permitted) in the CI column only (no P in IP, I, CR&D, or any commercial district).")
Q_CONF = ("Self-storage is a NAMED use confined to CI. 'General storage' and 'Wholesale distribution' = P "
          "in CI/PF only; 'Heavy manufacturing' = P in CI. IP/I do not list self-storage → the warehouse "
          "convention does not extend it there. No luxury-garage-condo use → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "LOC 50.03", "ordinance": ORD} for q in (Q_SS, Q_CONF)]

N_CI = ("ss/mw PERMITTED (by-right, named) — LOC Table 50.03.002-2 'Self-storage facility' = P in CI. "
        "li PERMITTED (heavy/light manufacturing P in CI). lgc prohibited.")
N_IND = ("ss/mw PROHIBITED — self-storage is a NAMED use confined to CI (§50.03.003.7); this district does "
         "not list self-storage. li permitted where manufacturing/R&D is listed. lgc prohibited.")
N_COM = ("ss/mw PROHIBITED — self-storage confined to CI; commercial district does not list self-storage. lgc prohibited.")

ROWS = [
    ("CI", "CI Industrial (self-storage-permitted)", "permitted", "permitted", "permitted", "prohibited", 0.85, N_CI),
    ("IP", "IP Industrial Park", "prohibited", "prohibited", "permitted", "prohibited", 0.82, N_IND),
    ("I", "I Industrial", "prohibited", "prohibited", "permitted", "prohibited", 0.80, N_IND),
    ("CR&D", "CR&D Campus Research & Development", "prohibited", "prohibited", "permitted", "prohibited", 0.82, N_IND),
    ("GC", "GC General Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("HC", "HC Highway Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.80, N_COM),
    ("MC", "MC Mixed Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.78, N_COM),
    ("EC", "EC East End Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.78, N_COM),
    ("OC", "OC Office Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.78, N_COM),
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
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, mini_warehouse::text mw,
            light_industrial::text li, human_reviewed hr FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code = ANY($3::text[]) AND deleted_at IS NULL
            ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""", JID, MUNI, [r[0] for r in ROWS])
        print(f"CATCH #42 — {MUNI} ({len(rr)}):")
        for r in rr:
            mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} hr={r['hr']}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
