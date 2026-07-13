"""Ayer MA — Stage-4 FULL close (2026-07-09). Zero held cells. 8 base districts (parcel codes).

TAIL. NEEDLE MUNI: self-storage is a named use permitted by special permit in the Light
Industrial (LI) and Mixed-Use Transitional (MUT) districts.

No rebind: Ayer parcels carry the bylaw district codes (assessor abbreviations DB=DPSFBC,
MT=MUT confirmed vs §320-4). Ayer is MRPC region (no MAPC/NMCOG layer), codes already clean.

Grounding — Town of Ayer Zoning Bylaw Ch. 320 (eCode360 AY3858; Table of Use Regulations = 320
Attachment 1; §320-4 districts):
  Legend: P=permitted; SPB=special permit (BoA); SPZ=special permit (ZBA); N=not permitted.
    Comprehensive per-cell table (every use has an explicit value per district) — closed by
    construction; self-storage is a NAMED use (§5.16), so grounded directly (not silence).
  ss/mw CONDITIONAL in LI + MUT: Table §5.16 "Self-storage facilities" = SPB in MUT and LI; N in
    all other districts (incl. Industrial I = N). (Named use -> grounded.)
  li PERMITTED in LI, I: §6.2 "Enclosed manufacturing" + §6.3 "Warehousing and interior storage" +
    §6.1 R&D = P (by-right) in LI and I; CONDITIONAL in GB (§6.2 manufacturing = SPB) and MUT
    (§5.15 wholesaling/distribution = SPB); prohibited in residential + DPSFBC + HCS.
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use; the
    named storage product (self-storage §5.16) is SPB only in LI/MUT and does not cover a vehicle
    garage-condo; closed table (Wilmington ledger #58 + Woburn convention).

Parcel-code map (assessor -> §320-4 district): A1/A2 = Residence, GR = General Residence,
GB = General Business, DB = Downtown Ayer/Park St Form-Based (DPSFBC), LI = Light Industrial,
I = Industrial, MT = Mixed-Use Transitional (MUT).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via parsed table rows.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_ayer.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "AYER"
CITED_SUBSECTION = "Table of Use Regs §5.16 (self-storage) + §6.1-6.3 (industrial) + §320-4"
ORD = ("Town of Ayer Zoning Bylaw Ch. 320 (eCode360 AY3858), Table of Use Regulations (320 "
       "Attachment 1) + §320-4 Zoning Districts")

Q_SS = ("Table of Use Regulations §5.16 'Self-storage facilities' = SPB (special permit) in MUT and LI; "
        "N (not permitted) in A1/A2/GR/DPSFBC/WAVFBC/GB/I/HCS. Legend: P=permitted; SPB/SPZ=special "
        "permit; N=not permitted.")
Q_LI = ("Table §6.2 'Enclosed manufacturing' = P in LI + I, SPB in GB, N elsewhere; §6.3 'Warehousing "
        "and interior storage' = P in LI + I, SPB in GB; §6.1 R&D = P in LI + I; §5.15 'Wholesaling and "
        "distribution' = P in LI/I, SPB in MUT/GB.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use in the Table of Use Regulations; "
         "the named storage product (§5.16 self-storage, SPB in LI/MUT) does not cover a vehicle "
         "garage-condo -> prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 320", "ordinance": ORD} for q in qs]


N_LI = ("ss/mw CONDITIONAL (GROUNDED): §5.16 Self-storage facilities = SPB in LI (named use). li "
        "PERMITTED (GROUNDED): §6.2 manufacturing + §6.3 warehousing = P (by-right) in LI. lgc "
        "PROHIBITED: no named garage-condo use.")
N_MUT = ("ss/mw CONDITIONAL (GROUNDED): §5.16 Self-storage facilities = SPB in MUT (=parcel code MT). li "
         "CONDITIONAL: §5.15 wholesaling/distribution = SPB; §6.2 manufacturing = N in MUT. lgc "
         "PROHIBITED.")
N_I = ("li PERMITTED (GROUNDED): §6.2 manufacturing + §6.3 warehousing = P (by-right) in Industrial (I). "
       "ss/mw PROHIBITED: §5.16 Self-storage facilities = N in I (self-storage confined to LI/MUT). lgc "
       "PROHIBITED.")
N_GB = ("li CONDITIONAL: §6.2 manufacturing + §6.3 warehousing = SPB in General Business. ss/mw "
        "PROHIBITED: §5.16 = N in GB. lgc PROHIBITED.")
N_PROHIB = ("All prohibited. §5.16 Self-storage = N here; §6.2 manufacturing / §6.3 warehousing = N here; "
            "no named garage-condo use.")

# zone_code (parcel), zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("A1", "Residence A1",                "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("A2", "Residence A2",                "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("GR", "General Residence",           "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("DB", "Downtown/Park St (DPSFBC)",   "prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("GB", "General Business",            "prohibited","prohibited","conditional","prohibited",0.85,N_GB),
    ("MT", "Mixed-Use Transitional (MUT)","conditional","conditional","conditional","prohibited",0.82,N_MUT),
    ("LI", "Light Industrial",            "conditional","conditional","permitted","prohibited",0.90,N_LI),
    ("I",  "Industrial",                  "prohibited","prohibited","permitted","prohibited",0.90,N_I),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
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
            ORDER BY zone_code""", JID, MUNI)
        print(f"CATCH #42 — {MUNI} rows post-apply ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:4} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
