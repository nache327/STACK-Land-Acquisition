"""Darien CT (jid 9b27e214) — Stage-4 grounding. DEFINITIVE NO-OP (0 self-storage needles).

Bound 99.6% via town parcel-GIS ZONING attribute (scripts/_bind_darien_ct.py, provenance
darien_ct_parcels_gis). municipality = 'Darien' (exact parcels.city, CT mixed-case).

Darien Zoning Law 2021 (town PDF, current through Amendment 104 / 2026):
- CLOSED LIST (§ "M. A prohibited use includes any use not specifically permitted in a zoning
  district established by this Zoning Law").
- SELF-STORAGE is a DEFINED use ("A self-storage facility ... A warehouse operated for a specific
  commercial or industrial establishment shall NOT be considered a self-storage facility") but is
  listed as a permitted use in NO district. History confirms it: self-storage at 131 Hollow Tree
  Ridge Rd required a site-specific Affordable-Housing amendment (Amdt 51/2016, 77/2020), not a
  base-district permission.
- ⇒ self_storage / mini_warehouse PROHIBITED town-wide (#58 closed-list sweep). The
  warehouse-by-right convention is OVERRIDDEN here: the town expressly defines self-storage as
  DISTINCT from warehouse and does not permit it in the warehouse districts.
- No named luxury-garage-condo use ⇒ lgc prohibited.

#38 CODE-MISMATCH FLAG (see outputs/_exceptions_B.md): the town parcel-GIS ZONING field uses granular
legacy codes (CBD/DB/SB/NB/DO/DC/DMR/RNBD/MU) that do NOT appear as district names in the 2021 Zoning
Law (which consolidated to C / MU-CC / MU-NC / I / MDR / REC). The GIS codes are the operative parcel
designations and the matrix keys on them; the self-storage=prohibited verdict holds under the current
law regardless of mapping. light_industrial set conservatively PROHIBITED (no parcel is GIS-coded to the
ordinance's C/I warehouse-permitting districts; li does not affect the self-storage needle).

Run: cd backend && PYTHONUTF8=1 python scripts/_apply_darien_ct.py
"""
import asyncio, json, asyncpg

JID = "9b27e214-367c-4652-8385-99b09fe38cd6"
MUNI = "Darien"
ORD = "Town of Darien, CT Zoning Law (2021 ed., current through Amdt 104)"
SUB = "§ Definitions (Self-Storage Facility); § 'M. A prohibited use includes any use not specifically permitted'"
Q_CLOSED = ("'M. A prohibited use includes any use not specifically permitted in a zoning district "
            "established by this Zoning Law.'")
Q_DEF = ("Self-Storage Facility defined as 'a building or group of buildings divided into separate units "
         "... used to meet the temporary storage needs of businesses and residential users. A warehouse "
         "operated for a specific commercial or industrial establishment shall not be considered a "
         "self-storage facility.' Self-storage is listed as a permitted use in no district.")

def cite():
    return [{"quote": q, "section": "Darien Zoning Law", "ordinance": ORD} for q in (Q_CLOSED, Q_DEF)]

N_BUS = ("All prohibited. Business/commercial/mixed-use district — self-storage is a DEFINED use listed as "
         "permitted in NO Darien district; closed-list clause prohibits any use not specifically permitted "
         "(warehouse-convention overridden by the ordinance's explicit self-storage≠warehouse definition). "
         "li prohibited (GIS legacy code; not mapped to the ordinance C/I warehouse districts). lgc prohibited.")
N_RES = "All prohibited. Residential district — no self-storage/warehouse use; closed-list."
N_PR = "All prohibited. Park/Recreation — no self-storage use."

# code, name, note  (all four uses prohibited)
ROWS = [
    ("CBD", "CBD Central Business (GIS legacy)", N_BUS),
    ("DB", "DB Business (GIS legacy)", N_BUS),
    ("DB1", "DB1 Business (GIS legacy)", N_BUS),
    ("DB2", "DB2 Business (GIS legacy)", N_BUS),
    ("SB", "SB Business (GIS legacy)", N_BUS),
    ("NB", "NB Neighborhood Business (GIS legacy)", N_BUS),
    ("RNBD", "RNBD Business (GIS legacy)", N_BUS),
    ("DO", "DO Office (GIS legacy)", N_BUS),
    ("DC", "DC Commercial (GIS legacy)", N_BUS),
    ("MU", "MU Mixed Use", N_BUS),
    ("DMR", "DMR Mixed Residential (GIS legacy)", N_BUS),
    ("PR", "PR Park/Recreation", N_PR),
    ("R-1", "R-1 Single-Family Residence", N_RES),
    ("R1", "R1 Single-Family Residence", N_RES),
    ("R-1/5", "R-1/5 Residence", N_RES),
    ("R2", "R2 Single-Family Residence", N_RES),
    ("R12", "R12 Single-Family Residence", N_RES),
    ("R13", "R13 Single-Family Residence", N_RES),
    ("R15", "R15 Single-Family Residence", N_RES),
]

SQL = """INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
 light_industrial, luxury_garage_condo, citations, cited_subsection, confidence, human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,'prohibited','prohibited','prohibited','prohibited',$5::jsonb,$6,$7,true,'human',$8,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage='prohibited', mini_warehouse='prohibited',
 light_industrial='prohibited', luxury_garage_condo='prohibited', citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, zn, note in ROWS:
            conf = 0.88 if zc not in ("DB1", "DB2", "RNBD", "DMR") else 0.80
            await con.execute(SQL, JID, zc, zn, MUNI, json.dumps(cite()), SUB, conf, note)
        rr = await con.fetch("""SELECT zone_code, self_storage::text ss, human_reviewed hr, confidence
            FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI}: {len(rr)} rows (all self_storage=prohibited → 0 needles)")
        for r in rr:
            print(f"  {r['zone_code']:8} ss={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
