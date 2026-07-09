"""Woburn MA — Stage-4 FULL close (2026-07-09). Zero held cells. All 16 base districts.

Woburn is a definitive 0-NEEDLE outcome (like Wilmington/Tewksbury): the city HAS real
light-industrial land (li by-right in I-P/IP-2/I-G — Industrial Park / Industrial Park Two
/ Industrial General), but SELF-STORAGE IS EXPLICITLY PROHIBITED IN EVERY DISTRICT.

Grounding (City of Woburn 1985 Zoning Ordinance, as amended; §5.1 Table of Use Regulations):
  ss/mw PROHIBITED (named-N, strongest): line 42a "Self-storage Warehouse facility" carries a
    "-" (not permitted) in ALL 16 columns. Named use, explicitly barred everywhere — beats any
    warehouse inference (Warehouse/distribution line 42 is only special-permit "P" in I-P/IP-2/I-G,
    never by-right, so no Cresskill-class self-storage upgrade per convention).
  li PERMITTED in I-P/IP-2/I-G: line 40aa "Light Manufacturing <15,000 sf" = X (by-right).
  li CONDITIONAL in S-2/O-P/O-P93 (Mixed Use II / Office Park / Office Park Overlay): line
    40aa/40ab Light Manufacturing = PB (Planning Board special permit), capped 25% GFA (Note 5).
  li PROHIBITED elsewhere (all Business, R-1..R-4, S-1 Mixed Use, O-S Open Space).
  lgc PROHIBITED everywhere: a luxury garage-condo is owned/leased dead storage — it is the
    self-storage product family, which line 42a bars in every district (and 42a explicitly
    excludes "trailers, motor vehicles"). Commercial parking garage (line 71) is transient
    parking, not owned/leased storage, so it is no upgrade path (Wilmington ledger #58 convention).
  No closed-list catch-all in §5.2, so ss/mw/lgc rest on the AFFIRMATIVE prohibition of the named
  self-storage use, not on prohibited-by-silence.

Armed self-storage / garage-condo = 0. Source: woburnma.gov, complete edition through 5/6/2022.
Executable apply (Dedham template): idempotent human-UPSERT via asyncpg, muni-scoped (catch #33),
verbatim-quote basis (catch #37), verify-and-print after apply (catch #42). Greenfield (0 rows before).
Run:  cd backend && PYTHONUTF8=1 python scripts/_apply_middlesex_ma_woburn.py
"""
import asyncio, json, asyncpg

JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"  # Middlesex County, MA
MUNI = "WOBURN"
CITED_SUBSECTION = "§5.1 lines 42a/40aa/42/71 + §4.2"
ORD = ("City of Woburn 1985 Zoning Ordinance, as amended (complete edition through 5/6/2022; "
       "woburnma.gov), §4.2 Establishment of Districts + §5.1 Table of Use Regulations & Notes")

Q_LEGEND = ("§5.1: 'For each of the Zoning Districts, uses permitted by right are designated by an "
            "\"X\"; uses that require a special permit from the City Council are designated by a "
            "\"P\"; uses that require a Special Permit from the Planning Board are designated by "
            "\"PB\"; and those uses not permitted are designated by a \"-\".'")
Q_SS = ("§5.1 line 42a 'Self-storage Warehouse facility - no storage of high hazard materials, "
        "trailers, motor vehicles or any outside storage': not permitted (\"-\") in ALL sixteen "
        "districts (R-1,R-2,R-3,R-4,B-N,B-H,B-D,B-I,I-P,IP-2,I-G,S-1,S-2,O-P,OP-93,O-S).")
Q_WHSE = ("§5.1 line 42 'Wholesale establishment, warehouse and distribution center': P (special "
          "permit) in I-P, IP-2, I-G only; \"-\" in every other district.")
Q_LM = ("§5.1 line 40aa 'Manufacturing: Light Manufacturing: Under 15,000 sf gfa': X (by-right) in "
        "I-P, IP-2, I-G; PB (Planning Board special permit) in S-2, O-P, OP-93; \"-\" in all "
        "Business/Residential/S-1/O-S. Line 40ab (over 15,000 sf): PB in I-P, IP-2, I-G, S-2, O-P, OP-93.")
Q_NOTE5 = ("§5.1 Note 5: 'In office park districts, light manufacturing uses shall not occupy more "
           "than twenty-five (25) percent of the gross floor area of the principal structure.'")
Q_PARK = ("§5.1 line 71 'Commercial parking garage or parking lot': P (special permit) in B-H, B-D, "
          "I-P, IP-2, I-G, S-2, O-P, OP-93 (See Definition, License Required) — transient parking, "
          "not owned/leased garage-condo storage.")


def cite(*quotes):
    return [{"quote": q, "section": "§5.1", "ordinance": ORD} for q in quotes]


# Notes by verdict group
N_PROHIB = ("ss/mw PROHIBITED GROUNDED (line 42a Self-storage Warehouse facility explicitly "
            "not-permitted \"-\" in this district; named-N, strongest grounding). li PROHIBITED: no "
            "light-industrial use permitted here — Light Manufacturing (40aa/40ab), "
            "Warehouse/distribution (42) and Research/testing lab (41) all \"-\". lgc PROHIBITED: "
            "the self-storage product family (42a) is barred in every Woburn district; commercial "
            "parking garage (71) is transient parking not owned/leased storage and is not permitted "
            "here anyway; no garage-condo use is named.")
N_BUSINESS = ("ss/mw PROHIBITED GROUNDED (42a named-N). li PROHIBITED: Light/Heavy Manufacturing, "
              "Warehouse/distribution and R&D lab all \"-\" in Business districts. lgc PROHIBITED: "
              "self-storage product family barred citywide (42a); commercial parking garage (71, "
              "special-permit in B-H/B-D) is transient parking, not owned/leased garage-condo storage.")
N_INDUSTRIAL = ("li PERMITTED GROUNDED: line 40aa Light Manufacturing (<15,000 sf) = X by-right (also "
                "R&D/testing lab 41 and printing/publishing 39b by-right). ss/mw PROHIBITED GROUNDED: "
                "line 42a Self-storage Warehouse facility explicitly \"-\" in every district incl. "
                "this one — named-N beats warehouse inference (Warehouse/distribution 42 here is only "
                "special-permit \"P\", not by-right → no self-storage upgrade per convention). lgc "
                "PROHIBITED: garage-condo = owned/leased dead storage; named self-storage use (42a) is "
                "barred and explicitly excludes 'trailers, motor vehicles'; commercial parking garage "
                "(71, special-permit here) is transient parking not owned storage — fits no permitted "
                "use (Wilmington ledger #58 convention).")
N_OFFICEPARK = ("li CONDITIONAL GROUNDED: line 40aa/40ab Light Manufacturing = PB (Planning Board "
                "special permit) here, capped at 25% GFA per Note 5 (office-park/mixed-use); R&D lab "
                "(41) by-right in O-P/OP-93. ss/mw PROHIBITED GROUNDED (42a named-N). lgc PROHIBITED: "
                "self-storage product family barred citywide (42a); commercial parking garage (71, "
                "special-permit) is transient parking, not owned/leased garage-condo storage.")

# zone_code, zone_name, group, li verdict, confidence
_ROWS = [
    ("R-1", "Single Family Residential", "prohib", "prohibited", 0.95),
    ("R-2", "Single Two Family Residential", "prohib", "prohibited", 0.95),
    ("R-3", "Townhouse and Garden Apartment Residential", "prohib", "prohibited", 0.95),
    ("R-4", "Apartment, other Residential", "prohib", "prohibited", 0.95),
    ("B-N", "Neighborhood Business", "business", "prohibited", 0.95),
    ("B-H", "Highway Business", "business", "prohibited", 0.95),
    ("B-D", "Downtown Business", "business", "prohibited", 0.95),
    ("B-I", "Interstate Business", "business", "prohibited", 0.95),
    ("I-P", "Industrial Park", "industrial", "permitted", 0.95),
    ("IP-2", "Industrial Park Two", "industrial", "permitted", 0.95),
    ("I-G", "Industrial General", "industrial", "permitted", 0.95),
    ("S-1", "Mixed Use", "prohib", "prohibited", 0.95),
    ("S-2", "Mixed Use II", "officepark", "conditional", 0.90),
    ("O-P", "Office Park", "officepark", "conditional", 0.90),
    ("O-P93", "Office Park Overlay", "officepark", "conditional", 0.90),
    ("O-S", "Open Space", "prohib", "prohibited", 0.95),
]

_NOTES = {"prohib": N_PROHIB, "business": N_BUSINESS, "industrial": N_INDUSTRIAL,
          "officepark": N_OFFICEPARK}
# Citation sets per group (only the quotes relevant to the group's basis)
_CITES = {
    "prohib": cite(Q_LEGEND, Q_SS, Q_LM),
    "business": cite(Q_LEGEND, Q_SS, Q_LM, Q_PARK),
    "industrial": cite(Q_LEGEND, Q_SS, Q_WHSE, Q_LM, Q_PARK),
    "officepark": cite(Q_LEGEND, Q_SS, Q_LM, Q_NOTE5, Q_PARK),
}

VERDICTS = [{
    "zone_code": zc, "zone_name": zn,
    "self_storage": "prohibited", "mini_warehouse": "prohibited",
    "light_industrial": li, "luxury_garage_condo": "prohibited",
    "citations": _CITES[grp], "cited_subsection": CITED_SUBSECTION,
    "confidence": conf, "notes": _NOTES[grp],
} for zc, zn, grp, li, conf in _ROWS]

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
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} lgc={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
