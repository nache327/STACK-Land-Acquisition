"""Hopkinton MA — Stage-4 FULL close (2026-07-13). Zero held cells. 11 base districts.

TAIL (Rt-495 biotech, wealthy). NEEDLE MUNI: Industrial A/B permit "Warehousing for distribution"
by-right -> self-storage conditional there per the warehouse->self_storage convention.

Grounding — Town of Hopkinton Zoning Bylaws Ch. 210 (2023 ed., ehop.org; eCode360 Ch.210),
Article VIII Industrial A (§210-34) + Article VIIIA Industrial B (§210-37):
  CLOSED-LIST (per-article, §210-34.B / §210-37): "Any use not so permitted is excluded unless
    otherwise permitted by law or the terms of this article."
  li PERMITTED in IA, IB: §210-34.A "Manufacturing, assembly or processing plants" (Subsection
    A(3)(a)-(k), incl. "any other light manufacturing enterprise") + "(1) Research and development" +
    "(4) Warehousing for distribution" = by-right in IA; §210-37 IB permits the same set by-right.
  ss/mw CONDITIONAL in IA, IB: no NAMED self-storage use, but "Warehousing for distribution" is a
    WAREHOUSE use permitted BY-RIGHT in IA + IB -> self-storage is the more-specific storage product
    => conditional there per the CLAUDE.md warehouse->self_storage convention (closed-list + unnamed
    => conditional, not by-right). Prohibited in all non-industrial districts.
  lgc PROHIBITED everywhere: no named garage-condo / owned-vehicle-storage principal use ("Automobile
    and truck rental and repair" is a SP rental/repair use, and fuel storage is accessory only);
    closed-list (Wilmington ledger #58 + Woburn convention).
  Business (B/BD/BR) + Office (OP/P) + Residence/Agriculture (A/RA/RB/RLF): no warehouse/manufacturing/
    self-storage use in their permitted lists -> all prohibited under the town-wide closed-list.

Rebind: MAPC layer 2 (strip ^139) — parcels carried assessor sub-codes (A2/RA1/RB2/OSLP), rebound
to bylaw districts A/B/BD/BR/IA/IB/OP/P/RA/RB/RLF. Gates a/b/d PASS.

Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (#33),
verbatim citations (#37), verify-and-print (#42).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_hopkinton.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "HOPKINTON"
CITED_SUBSECTION = "§210-34 (IA) / §210-37 (IB) permitted uses + closed-list §210-34.B"
ORD = ("Town of Hopkinton Zoning Bylaws Ch. 210 (2023 ed., ehop.org; eCode360 Ch.210), Article VIII "
       "Industrial A (§210-34) + Article VIIIA Industrial B (§210-37)")

Q_CLOSED = ("§210-34.B (IA) / §210-37 (IB): 'Any use not so permitted is excluded unless otherwise "
            "permitted by law or the terms of this article.' (per-article closed list)")
Q_LI = ("§210-34.A IA permitted by-right: '(3) Manufacturing, assembly or processing plants...any other "
        "light manufacturing enterprise'; '(1) Research and development'; '(4) Warehousing for "
        "distribution'. §210-37 IB permits the same industrial set by-right.")
Q_SS = ("No named self-storage/mini-warehouse use. '(4) Warehousing for distribution' is a warehouse use "
        "permitted BY-RIGHT in IA + IB -> self-storage conditional there per the warehouse->self_storage "
        "convention; §210-34.B/§210-37 closed-list prohibits self-storage in every other district.")
Q_LGC = ("No named garage-condo / owned-vehicle-storage principal use ('Automobile and truck rental and "
         "repair' is a §210-35 special-permit rental/repair use; fuel storage is accessory only). "
         "Closed-list -> unnamed garage-condo prohibited in every district.")


def cite(*qs):
    return [{"quote": q, "section": "Ch. 210", "ordinance": ORD} for q in qs]


N_IND = ("li PERMITTED (GROUNDED): §210-34.A/§210-37 Manufacturing/assembly/processing + R&D = by-right "
         "here. ss/mw CONDITIONAL: '(4) Warehousing for distribution' by-right -> self-storage "
         "conditional (convention; unnamed + closed-list => conditional). lgc PROHIBITED: no named "
         "garage-condo use; closed-list §210-34.B.")
N_PROHIB = ("All prohibited (town-wide closed-list). Warehouse/manufacturing/self-storage are IA/IB uses "
            "(§210-34/§210-37), not permitted in this business/office/residential/agricultural district; "
            "no named garage-condo use.")

# zone_code, zone_name, ss, mw, li, lgc, conf, note
_R = [
    ("A",   "Agriculture",            "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RA",  "Residence A",            "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RB",  "Residence B",            "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("RLF", "Residence Lake Front",   "prohibited","prohibited","prohibited","prohibited",0.92,N_PROHIB),
    ("B",   "Business",               "prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("BD",  "Downtown Business",      "prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("BR",  "Rural Business",         "prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("OP",  "Office Park",            "prohibited","prohibited","prohibited","prohibited",0.82,N_PROHIB),
    ("P",   "Professional Office",    "prohibited","prohibited","prohibited","prohibited",0.85,N_PROHIB),
    ("IA",  "Industrial A",           "conditional","conditional","permitted","prohibited",0.88,N_IND),
    ("IB",  "Industrial B",           "conditional","conditional","permitted","prohibited",0.88,N_IND),
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
