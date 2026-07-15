"""South Brunswick township NJ (Middlesex jid 9c039328) — Stage-4 grounding, muni-scoped.

Parcels Atlas-bound (100%). municipality='South Brunswick township' (exact parcels.city).
Ordinance: Township of South Brunswick Code Ch. 62 Land Use, Art. IV Zoning, Div. 3 Districts
(Municode client 7740 / product 13445 / job 489397; fetched via api.municode.com/CodesContent, curl+UA).

NJ SELF-STORAGE CATCH (b) — NAMED DISTRICTS beat the warehouse convention:
Miniwarehouse/self-storage facilities are named as a CONDITIONAL USE ONLY in:
  • I-3 General Industrial (§ Subdiv. XXXII) — "(4) Miniwarehouse/self-storage facilities, subject to
    the following conditions: a. The site shall be east of Route 130 and south of Route [522]..."
  • LI-4 Light Industrial (§ Subdiv. XXXVI) — "The following uses shall be permitted in the LI-4 light
    industrial district as conditional uses ...: (1) Miniwarehouse/self-storage facilities ... south of
    Davidson's Mill Road."
South Brunswick has a SEPARATE I-2 General Industrial district (and LI-1/LI-2/LI-4-C) that permit
warehouse/distribution BY-RIGHT but do NOT name self-storage → the warehouse-by-right convention is
OVERRIDDEN (deliberate confinement, Boonton pattern). self_storage is therefore CONDITIONAL in I-3 & LI-4
and PROHIBITED in every other district. lgc-unnamed → prohibited.

NEEDLES: I-3 conditional (14 wealth&1.5ac), LI-4 conditional (0 w15). Office (OR 48 / OP 22 w15) and
commercial (C-2 14 / C-1 7 / C-3 5) clear the ring but do NOT permit self-storage → correct no-op.

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_south_brunswick_nj.py
"""
import asyncio, json, asyncpg

JID = "9c039328-c995-41fc-83ce-fb4966fd402b"
MUNI = "South Brunswick township"
ORD = "Township of South Brunswick, NJ Code Ch. 62 Land Use, Art. IV Zoning (Municode; job 489397)"
SUB = "Ch. 62 Art. IV Div. 3 — I-3 (Subdiv. XXXII); LI-4 (Subdiv. XXXVI); I-2 (Subdiv. XXXI)"

Q_I3 = ("I-3 General Industrial District: '(4) Miniwarehouse/self-storage facilities, subject to the "
        "following conditions: a. The site shall be east of Route 130 and south of Route [522] ...' "
        "(listed as a conditional use).")
Q_LI4 = ("LI-4 Light Industrial District: 'The following uses shall be permitted in the LI-4 light "
         "industrial district as conditional uses ...: (1) Miniwarehouse/self-storage facilities, subject "
         "to ... south of Davidson's Mill Road.'")
Q_CONF = ("Self-storage is named as a conditional use ONLY in I-3 and LI-4. The separate I-2 General "
          "Industrial district and LI-1/LI-2/LI-4-C permit warehouse/distribution by-right but do NOT "
          "name self-storage → confined to I-3/LI-4; warehouse convention overridden. No named "
          "luxury-garage-condo use anywhere → lgc prohibited.")

def cite():
    return [{"quote": q, "section": "Ch. 62 Art. IV Div. 3", "ordinance": ORD} for q in (Q_I3, Q_LI4, Q_CONF)]

N_NEEDLE = ("ss/mw CONDITIONAL — Miniwarehouse/self-storage named as a conditional use in this district "
            "(geographic sub-conditions apply within the zone). li PERMITTED (industrial/warehouse). lgc prohibited.")
N_IND = ("ss/mw PROHIBITED — warehouse/distribution permitted by-right but self-storage is a NAMED use "
         "confined to I-3/LI-4 (convention overridden). li PERMITTED (industrial/warehouse). lgc prohibited.")
N_COM = ("All prohibited. Commercial/retail district — self-storage not permitted (confined to I-3/LI-4); "
         "no by-right industrial use. ")
N_OFF = ("All prohibited. Office/research district — no self-storage or warehouse by-right use "
         "(self-storage confined to I-3/LI-4).")
N_RES = "All prohibited. Residential / planned-residential / affordable-housing district — no self-storage use."
N_OTH = "All prohibited. Public land / park / redevelopment district — self-storage not a permitted use here."

# code, name, ss, mw, li, lgc, conf, note
ROWS = [
    ("I-3", "I-3 General Industrial", "conditional", "conditional", "permitted", "prohibited", 0.85, N_NEEDLE),
    ("LI-4", "LI-4 Light Industrial", "conditional", "conditional", "permitted", "prohibited", 0.85, N_NEEDLE),
    ("I-2", "I-2 General Industrial", "prohibited", "prohibited", "permitted", "prohibited", 0.85, N_IND),
    ("LI-1", "LI-1 Light Industrial", "prohibited", "prohibited", "permitted", "prohibited", 0.85, N_IND),
    ("LI-2", "LI-2 Light Industrial/Office/Research", "prohibited", "prohibited", "permitted", "prohibited", 0.85, N_IND),
    ("LI-4/C", "LI-4/C Light Industrial/Commercial", "prohibited", "prohibited", "permitted", "prohibited", 0.83, N_IND),
    ("R-3/I", "R-3/I Single-Family/Industrial", "prohibited", "prohibited", "permitted", "prohibited", 0.78, N_IND),
    ("C-1", "C-1 Neighborhood Commercial/Prof Office/Local Service", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COM),
    ("C-2", "C-2 General Retail Commercial Center", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COM),
    ("C-3", "C-3 Highway Commercial", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_COM),
    ("OR", "OR Office/Research/Conference", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OFF),
    ("OP", "OP Office Park", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_OFF),
    ("OC", "OC Office/Corporate", "prohibited", "prohibited", "prohibited", "prohibited", 0.83, N_OFF),
    ("R-1", "R-1 Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.90, N_RES),
    ("R-2", "R-2 Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.90, N_RES),
    ("R-2.1", "R-2.1 Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.90, N_RES),
    ("R-3", "R-3 Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.90, N_RES),
    ("R-4", "R-4 Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.90, N_RES),
    ("R-C3", "R-C3 Residential Cluster", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("RR", "RR Rural Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("RM-1.1", "RM-1.1 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("RM-4", "RM-4 Multifamily Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("MF", "MF Multiple-Dwelling/Garden Apartment", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("MHP", "MHP Mobile Home Park", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("AH", "AH Affordable Housing", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("ARRC", "ARRC Age-Restricted Residential", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, N_RES),
    ("PRD I", "PRD I Planned Residential Development", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("PRD II", "PRD II Planned Residential Development", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("PRD III", "PRD III Planned Residential Development", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("PRD IV/AH", "PRD IV/AH Planned Residential Development/Affordable Housing", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_RES),
    ("PL", "PL Public Land", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_OTH),
    ("PARC", "PARC Park", "prohibited", "prohibited", "prohibited", "prohibited", 0.88, N_OTH),
    # NOTE: 'Wilson Farm Redevelopment Zone' was an over-length Atlas phrase-artifact on 3 parcels
    # (not a valid district code). Those parcels' zoning_code was NULLed and no matrix row is kept
    # (an over-length zone_code trips the post-ingest gate). The hardened Atlas bind now skips such
    # >20-char phrases (scripts/bind_nj_atlas082025.py _bad_code).
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
            light_industrial::text li, confidence conf FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI}: {len(rr)} rows")
        for r in rr:
            mark = " <== NEEDLE" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:32} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} conf={r['conf']}{mark}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
