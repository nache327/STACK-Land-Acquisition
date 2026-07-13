"""Holliston MA — Stage-4 FULL close (2026-07-09). Zero held cells. 7 base districts.

TIER-2. NEEDLE MUNI: no NAMED self-storage use, but the Industrial District permits general
industrial uses (incl. storage) + warehouse by-right -> self-storage is conditional there per the
warehouse->self_storage convention.

Grounding — Town of Holliston Zoning By-Laws (Oct-2017 ed., hollistonedc.com), §II-A Classes of
Districts + Schedule of Use Regulations (§III):
  CLOSED-LIST (p3): "...permitted within the district in which such building, structure or land is
    located. Any use not specifically enumerated in a district herein shall be [prohibited]." p16:
    "In any district, no building or structure shall be erected or used for any purpose other than
    those set forth in the Schedule of Use Regulations." Legend: Y=permitted; SP=special permit; N=no.
  li PERMITTED in I: Schedule G.2 "General industrial uses including manufacturing, storage,
    processing, fabrication, packaging and assembly (<=15,000 sf)" = Y in I (N in AR1/AR2/R1/VR/C1/VC);
    G.1 "Wholesale office or showroom, including warehouse facilities" = Y in I (SP in C1/VC);
    F.3 Alternative-Energy Manufacturing/R&D = Y in I. li CONDITIONAL in C1, VC (G.1 warehouse/
    wholesale = SP). Prohibited in AR1/AR2/R1/VR.
  ss/mw CONDITIONAL in I: no named self-storage use, but warehouse + general-industrial-storage are
    BY-RIGHT in I (G.1/G.2) -> self-storage conditional per the warehouse->self_storage convention
    (self-storage is the more specific product; closed-list + not explicitly named => conditional,
    not by-right). Prohibited elsewhere (C1/VC warehouse is only SP -> convention does not fire).
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage use (E.1 auto-salesroom-
    with-storage and E.4 repair-garage are distinct); closed-list (Wilmington ledger #58 + Woburn).

Rebind: MAPC layer 2 (strip ^136) — parcels carried messy assessor codes (40/30/80/CL4/etc.),
rebound to bylaw districts AR1/AR2/C1/I/R1/VC/VR (vocab matches bylaw §II-A; gates a/b/d PASS,
0 orphans, ~96% changed = assessor->bylaw translation).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via raw row read.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_holliston.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "HOLLISTON"
CITED_SUBSECTION = "Schedule of Use Regs G.1/G.2/F.3 + §II closed-list (p3/p16)"
ORD = ("Town of Holliston Zoning By-Laws (Oct-2017 ed., hollistonedc.com), §II-A Classes of "
       "Districts + Schedule of Use Regulations")

Q_CLOSED = ("p3: 'Any use not specifically enumerated in a district herein shall be [prohibited].' p16: "
            "'In any district, no building or structure shall be erected or used for any purpose other "
            "than those set forth in the Schedule of Use Regulations.' Legend: Y=permitted; SP=special "
            "permit; N=not permitted.")
Q_LI = ("Schedule G.2 'General industrial uses including manufacturing, storage, processing, "
        "fabrication, packaging and assembly (<=15,000 sf)' = Y in I; N in AR1/AR2/R1/VR/C1/VC. G.1 "
        "'Wholesale office or showroom, including warehouse facilities' = Y in I, SP in C1/VC. F.3 "
        "Alternative-Energy Manufacturing / R&D = Y in I.")
Q_SS = ("No named self-storage use in the Schedule; the Industrial (I) district permits warehouse (G.1) "
        "and general-industrial storage (G.2) BY-RIGHT -> self-storage is the more-specific storage "
        "product, conditional in I per the warehouse->self_storage convention; C1/VC warehouse is only "
        "SP (does not fire the convention) so self-storage prohibited there.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use (E.1 motor-vehicle salesroom with "
         "accessory storage and E.4 repair garage are distinct). Closed-list (p3/p16) -> unnamed "
         "garage-condo storage prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Schedule of Use Regs", "ordinance": ORD} for q in qs]


N_I = ("li PERMITTED (GROUNDED): Schedule G.2 general industrial (incl. storage) + G.1 warehouse = Y "
       "(by-right) in I. ss/mw CONDITIONAL: warehouse/storage by-right -> self-storage conditional "
       "(convention; not explicitly named + closed-list => conditional). lgc PROHIBITED: no named "
       "garage-condo use; closed-list.")
N_COM = ("li CONDITIONAL: Schedule G.1 'Wholesale office or showroom, including warehouse facilities' = "
         "SP (special permit) here; general industrial = N. ss/mw PROHIBITED (warehouse only SP -> "
         "convention does not fire; no named self-storage; closed-list). lgc PROHIBITED.")
N_PROHIB = ("All prohibited (closed-list p3/p16). No industrial/warehouse/storage use permitted here "
            "(Schedule G.1/G.2 = N); no named self-storage or garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("AR1", "Agricultural-Residential A", "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("AR2", "Agricultural-Residential B", "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("R1",  "Residential",                "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("VR",  "Village Residential",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("C1",  "Commercial",                 "prohibited","prohibited","conditional","prohibited",0.82,N_COM),
    ("VC",  "Village Center Commercial",  "prohibited","prohibited","conditional","prohibited",0.82,N_COM),
    ("I",   "Industrial",                 "conditional","conditional","permitted","prohibited",0.85,N_I),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_CLOSED, Q_LI, Q_SS, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
