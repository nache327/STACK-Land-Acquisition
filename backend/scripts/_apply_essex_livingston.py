"""Livingston Township NJ (Essex Co) — Stage-4 grounding (2026-07-14). NEEDLE = CI + I + R-L + R-L2.

NJ name-bound; parcels bound via NJTPA Atlas 082025. municipality = 'Livingston township' (exact
parcels.city). Source: Township of Livingston NJ Code Ch. 170 Land Use (eCode360 LI1238, full chapter via
print?guid=10295328).

#38 RESOLVED: R-L (§170-115) / R-L2 (§170-116) = "Research Laboratory District" (office/research/lab —
R-L2 §170-116B(4) EXPRESSLY prohibits manufacturing) — industrial-adjacent, NOT residential despite the
R- prefix. CI (§170-118) = Commercial Industrial; I (§170-117) = Limited Industrial.

NJ SELF-STORAGE CATCH: self-storage is a NAMED use. Grounded on the affirmative district-level permitted-
use lists (#57 affirmative-provision):
  - I  §170-117A(6): 'Moving and storage operations and self-storage facilities.' → ss/mw PERMITTED by-right.
  - CI §170-118A(3)(c): 'Warehouses, including self-storage facilities (mini-warehouses).' → ss/mw PERMITTED.
  - R-L/R-L2 §170-94.K: 'Self-storage facilities...shall be permitted only in the R-L and R-L2 Zones as
    conditional uses...' → ss/mw CONDITIONAL in R-L/R-L2 (li prohibited: office/research, no manufacturing).
TENSION FLAGGED (escalated to _exceptions_A.md): §170-94.K says self-storage "only in R-L and R-L2 as
conditional uses," which reads against the explicit I/CI by-right listings. Read here as: §170-94.K scopes
the CONDITIONAL-use pathway (R-L/R-L2), while I/CI grant self-storage by-right in their own permitted-use
sections. Grounded I/CI = permitted (affirmative, explicit) at slightly reduced confidence (0.82); revisit
if Nache reads §170-94.K as an override. li PERMITTED in I/CI (manufacturing/fabrication by-right).
NEEDLE (wealth-ring ≥1.5ac): CI = 27, I = 11 (permitted); R-L = 7, R-L2 = 8 (conditional) ≈ 53 lots.

Executable apply (Boonton template): idempotent human-UPSERT, muni-scoped (#33), verbatim citations (#37),
closed-list sweep (#57/#58), lgc-unnamed→prohibited, verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_essex_livingston.py
"""
import asyncio, json, asyncpg
from scripts._db import get_sync_dsn

JID = "67541a18-c599-423b-bf05-d68153af1e2f"
MUNI = "Livingston township"
CITED = "§ 170-117A(6) (I); § 170-118A(3)(c) (CI); § 170-94.K + §§ 170-115/116 (R-L/R-L2 cond); closed list (per-district 'Any use not specifically permitted herein')"
ORD = "Township of Livingston, NJ Code Ch. 170 Land Use (eCode360 LI1238)"

Q_SS_I = ("§ 170-117A (I Limited Industrial District) 'is designed for:...(6) Moving and storage operations "
          "and self-storage facilities.' → self-storage permitted principal use.")
Q_SS_CI = ("§ 170-118A (CI Commercial Industrial District): 'only the following uses are permitted:...(3) "
           "Manufacturing/industry...(c) Warehouses, including self-storage facilities (mini-warehouses).'")
Q_SS_RL = ("§ 170-94.K: 'Self-storage facilities, as defined in this section, shall be permitted only in the "
           "R-L and R-L2 Zones as conditional uses...' R-L § 170-115 / R-L2 § 170-116 Research Laboratory "
           "Districts.")
Q_LI = ("§ 170-117A(3) (I) 'Limited industrial, manufacturing, assembly and packaging uses'; § 170-118A(3)(a) "
        "(CI) 'Fabrication, assembly, packaging and treatment of products.'")
Q_CLOSED = ("Per-district closed list ('C. Prohibited uses: (1) Any use not specifically permitted herein') "
            "→ self-storage (named in I/CI by-right, R-L/R-L2 conditional) is prohibited in all other "
            "districts; no named vehicle garage-condo use → lgc prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 170", "ordinance": ORD} for q in qs]


N_CI = ("ss/mw PERMITTED (GROUNDED NEEDLE): § 170-118A(3)(c) 'Warehouses, including self-storage facilities "
        "(mini-warehouses)' by-right in CI. li PERMITTED: § 170-118A(3)(a) fabrication/assembly/packaging. "
        "lgc PROHIBITED. NOTE: § 170-94.K 'only R-L/R-L2 conditional' tension flagged (see header/exceptions); "
        "grounded by-right on the explicit CI listing, conf 0.82.")
N_I = ("ss/mw PERMITTED (GROUNDED NEEDLE): § 170-117A(6) 'Moving and storage operations and self-storage "
       "facilities' by-right in I. li PERMITTED: § 170-117A(3) limited industrial/manufacturing/assembly/"
       "packaging. lgc PROHIBITED. NOTE: § 170-94.K tension flagged; grounded by-right on explicit I listing, conf 0.82.")
N_RL = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): § 170-94.K self-storage conditional use in R-L/R-L2 only. li "
        "PROHIBITED: R-L § 170-115A = executive/admin offices + scientific/research labs (≤25% accessory "
        "pilot plant), no general manufacturing. lgc PROHIBITED.")
N_RL2 = ("ss/mw CONDITIONAL (GROUNDED NEEDLE): § 170-94.K self-storage conditional use in R-L/R-L2 only. li "
         "PROHIBITED: R-L2 § 170-116A = same as R-L; § 170-116B(4) EXPRESSLY prohibits manufacturing / any I-"
         "district use. lgc PROHIBITED.")
N_BUS = "All prohibited. Business/commercial district (retail/office/service); no self-storage/warehouse/manufacturing named (per-district closed list)."
N_DS = "All prohibited. D-S Designed Shopping Center: retail center; no self-storage/warehouse/industrial use."
N_HH = "All prohibited. H-H Hospital Health Care District: medical/hospital uses; no self-storage/industrial use."
N_PB = "All prohibited. P-B Professional Building/Office District: professional offices; no self-storage/warehouse."
N_AH = "All prohibited. AH Adult Housing District: age-restricted residential; no self-storage/industrial use."
N_WRC = "All prohibited. WRC Water Resource Conservation District: conservation; no self-storage/industrial use."
N_RES = "All prohibited. Residential district: no self-storage/warehouse/manufacturing use (per-district closed list); no named garage-condo use."

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("CI","CI Commercial Industrial","permitted","permitted","permitted","prohibited",0.82,N_CI),
    ("I","I Limited Industrial","permitted","permitted","permitted","prohibited",0.82,N_I),
    ("R-L","R-L Research Laboratory","conditional","conditional","prohibited","prohibited",0.85,N_RL),
    ("R-L2","R-L2 Research Laboratory","conditional","conditional","prohibited","prohibited",0.85,N_RL2),
    ("B","B Central Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("B-1","B-1 General Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("B-2","B-2 Highway Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("BN","BN Neighborhood Business","prohibited","prohibited","prohibited","prohibited",0.86,N_BUS),
    ("D-S","D-S Designed Shopping Center","prohibited","prohibited","prohibited","prohibited",0.86,N_DS),
    ("D-S2","D-S2 Designed Shopping Center","prohibited","prohibited","prohibited","prohibited",0.86,N_DS),
    ("H-H","H-H Hospital Health Care","prohibited","prohibited","prohibited","prohibited",0.86,N_HH),
    ("P-B","P-B Professional Building","prohibited","prohibited","prohibited","prohibited",0.86,N_PB),
    ("P-B1","P-B1 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,N_PB),
    ("P-B2","P-B2 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,N_PB),
    ("P-B3","P-B3 Professional Office","prohibited","prohibited","prohibited","prohibited",0.86,N_PB),
    ("AH","AH Adult Housing","prohibited","prohibited","prohibited","prohibited",0.88,N_AH),
    ("WRC","WRC Water Resource Conservation","prohibited","prohibited","prohibited","prohibited",0.88,N_WRC),
    ("R-G","R-G Residence Garden","prohibited","prohibited","prohibited","prohibited",0.88,N_RES),
    ("R-1","R-1 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-2","R-2 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-3","R-3 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-4","R-4 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5","R-5 Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5A","R-5A Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5B","R-5B Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5C","R-5C Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5E","R-5E Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5F","R-5F Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5I","R-5I Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-5J","R-5J Residence","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
    ("R-6","R-6 Senior Citizen Housing","prohibited","prohibited","prohibited","prohibited",0.90,N_RES),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS_I, Q_SS_CI, Q_SS_RL, Q_LI, Q_CLOSED), "cited_subsection": CITED,
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
    con = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
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
            ORDER BY (self_storage::text IN ('permitted','conditional')) DESC, zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
