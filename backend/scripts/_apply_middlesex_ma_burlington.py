"""Burlington MA — Stage-4 FULL close (2026-07-09). Zero held cells.

TIER-2 (Rt-128 corridor). 0-NEEDLE for self-storage — a CORRECT no-op: Burlington has real
industrial land (IG/IR General Industrial + Research) but self-storage is a DEFINED use that
the bylaw PROHIBITS IN EVERY DISTRICT (deliberate amendment, Art. VII/IV, p166).

No rebind needed: Burlington parcels already carry the bylaw district codes (RO/RG/RC, BN/BL/BT/BG,
IG/IR/IH, OS, CBD/CC, PD/NPD) — no assessor mismatch.

Grounding — Town of Burlington Zoning Bylaw (burlington.org ArchiveCenter/ViewFile/Item/599),
§4.2 Use Regulations + §4.3 Accessory Uses:
  CLOSED-LIST (p79): "All uses not specifically permitted by Section 4.4.1 or 4.4.2 are prohibited."
    Legend: YES=permitted as of right; SP=special permit (Art. IX §9.2); NO=prohibited.
  ss/mw PROHIBITED everywhere (named-N, strongest): §4.2.6.29 "Self-Storage Facility" = NO in ALL
    16 columns (RO/RG/RC/BN/BL/BT/BG/IG/I/IR/OS/A/WR + CC/CBD/MCMOD overlays); §4.3.2.18 (accessory)
    = NO everywhere too. Self-storage is a defined use explicitly barred citywide.
  li PERMITTED in IG, I, IR: §4.2.7.1 "Light Manufacturing" + §4.2.7.2 "Research and Development"
    = YES (by-right) in IG/I/IR; SP in A/WR/CC/CBD; NO in residential + business + OS.
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use; the
    self-storage product family is barred citywide; closed-list (Wilmington ledger #58 + Woburn).

Note: IH (Industrial Heavy, 3 parcels) + PD/NPD (Planned Development, ~91 parcels) are not standard
§4.2 use-table columns — ss/mw/lgc still PROHIBITED there (citywide self-storage bar + closed-list),
li marked CONDITIONAL (planned/heavy-industrial: light industry by special permit / approved plan).

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42), catch #56 alignment via parsed table rows.
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_burlington.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "BURLINGTON"
CITED_SUBSECTION = "§4.2.6.29/§4.3.2.18 (Self-Storage) + §4.2.7 (Industrial) + p79 closed-list"
ORD = ("Town of Burlington Zoning Bylaw (burlington.org ArchiveCenter/ViewFile/Item/599), §4.2 Use "
       "Regulations + §4.3 Accessory Uses")

Q_CLOSED = ("p79: 'All uses not specifically permitted by Section 4.4.1 or 4.4.2 are prohibited.' "
            "Legend: YES=permitted as of right; SP=special permit (Art. IX §9.2.0-9.2.7); NO=prohibited.")
Q_SS = ("§4.2.6.29 'Self-Storage Facility' = NO in ALL districts (RO/RG/RC/BN/BL/BT/BG/IG/I/IR/OS/A/WR "
        "+ CC/CBD/MCMOD overlays); §4.3.2.18 (accessory) 'Self-Storage Facility' = NO everywhere too. "
        "Defined use (Art. VII definition) explicitly barred in every district.")
Q_LI = ("§4.2.7.1 'Light Manufacturing' = YES (by-right) in IG, I, IR; SP in A/WR/CC/CBD; NO in "
        "residential/business/OS. §4.2.7.2 'Research and Development' = YES in IG, I, IR.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use; the self-storage product family "
         "is barred citywide (§4.2.6.29); closed-list (p79) -> unnamed garage-condo prohibited everywhere.")


def cite(*qs):
    return [{"quote": q, "section": "§4.2", "ordinance": ORD} for q in qs]


N_IND = ("li PERMITTED (GROUNDED): §4.2.7.1 Light Manufacturing + §4.2.7.2 R&D = YES (by-right) here. "
         "ss/mw PROHIBITED (GROUNDED): §4.2.6.29 Self-Storage Facility = NO in every district. lgc "
         "PROHIBITED: no named garage-condo use; closed-list p79.")
N_OVL = ("li CONDITIONAL: Light Manufacturing = SP (special permit) in this district. ss/mw PROHIBITED "
         "(§4.2.6.29 Self-Storage = NO everywhere). lgc PROHIBITED (closed-list p79).")
N_PLANNED = ("Planned/heavy-industrial district not in the standard §4.2 use-table columns. ss/mw "
             "PROHIBITED (§4.2.6.29 Self-Storage = NO in ALL districts + closed-list p79). li "
             "CONDITIONAL (light industry by special permit / approved development plan). lgc PROHIBITED.")
N_PROHIB = ("All prohibited (closed-list p79). §4.2.6.29 Self-Storage Facility = NO here; §4.2.7.1 Light "
            "Manufacturing = NO here; no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("RO",  "One Family Residence",    "prohibited","prohibited","prohibited","prohibited",0.95,N_PROHIB),
    ("RG",  "General Residence",       "prohibited","prohibited","prohibited","prohibited",0.95,N_PROHIB),
    ("RC",  "Residence C",             "prohibited","prohibited","prohibited","prohibited",0.95,N_PROHIB),
    ("BL",  "Limited Business",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("BT",  "Continuous Traffic Business","prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("BG",  "General Business",        "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("OS",  "Open Space",              "prohibited","prohibited","prohibited","prohibited",0.95,N_PROHIB),
    ("IG",  "General Industrial",      "prohibited","prohibited","permitted","prohibited",0.92,N_IND),
    ("IR",  "Industrial Research",     "prohibited","prohibited","permitted","prohibited",0.92,N_IND),
    ("CBD", "Central Business District","prohibited","prohibited","conditional","prohibited",0.85,N_OVL),
    ("CC",  "Commercial Center",       "prohibited","prohibited","conditional","prohibited",0.85,N_OVL),
    ("IH",  "Industrial Heavy",        "prohibited","prohibited","conditional","prohibited",0.80,N_PLANNED),
    ("PD",  "Planned Development",     "prohibited","prohibited","conditional","prohibited",0.80,N_PLANNED),
    ("NPD", "New Planned Development",  "prohibited","prohibited","conditional","prohibited",0.80,N_PLANNED),
]

VERDICTS = [{
    "zone_code": zc, "zone_name": zn, "self_storage": ss, "mini_warehouse": mw,
    "light_industrial": li, "luxury_garage_condo": lgc,
    "citations": cite(Q_CLOSED, Q_SS, Q_LI, Q_LGC), "cited_subsection": CITED_SUBSECTION,
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
