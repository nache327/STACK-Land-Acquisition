"""Middletown Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 275 Zoning, Articles XI/XII/XIV/XV/XVI/XVII/XVIII, pasted 2026-07-07.

M (§ 275-76A(9)) — "Mini-warehouse/self-storage facility, subject to § 275-156."
  SELF-STORAGE PERMITTED BY RIGHT, EXPLICITLY NAMED (plus A(8) warehouse <=200k sf by
  right; A(11) light manufacturing by right). -> self_storage/mini_warehouse PERMITTED
  (0.95). 20 pool parcels >=1.5ac — the strongest verdict class. luxury_garage_condo
  unnamed -> conditional (0.70) via the C(12) catch-all conditional ("Any lawful use not
  otherwise listed in any zoning district").

SU-1-A (§ 275-98C(26)) — "Mini-warehouse/self-storage facility, subject to § 275-156."
  ALSO by-right named -> PERMITTED (0.90; noted: 100-acre minimum tract + required mix of
  >=3 uses per § 275-98A/§ 275-99 make standalone development impractical — verdict is
  correct but development-constrained). light_industrial not named in the closed list ->
  prohibited.

C-1 (§ 275-81) / C-2 (§ 275-86) / C-3 (§ 275-92) / I-1 (§ 275-62) / I-2 (§ 275-67) —
  closed lists ("...and for no other"); no storage/warehouse use named (C-3's only storage
  language is ACCESSORY maintenance-storage § 275-92C(1); C-1/C-2 accessory outdoor
  storage § 275-134) -> PROHIBITED (0.92). Kills the C-2 (8) + C-3 (3) pool parcels.

HELD (not in paste): MS "Municipal Service District" (17 pool parcels — follow-up paste
  worth it), OR, PRD, SU-1, SU-2, R-*.

Muni-specific municipality='Middletown Township' (catch #33 family); human-UPSERT
(catch #29). Run: python scripts/_apply_delaware_pa_middletown.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Middletown Township"
ORD = "Middletown Township Code Ch. 275 Zoning (eCode360 https://ecode360.com/13267796)"

_CLOSED = (
    "closed-list use regulations; no self-storage/mini-warehouse/warehouse use named in "
    "permitted, accessory, or conditional uses"
)

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "M": ("permitted", "permitted", "permitted", "conditional", 0.95,
          "§ 275-76A(9)",
          "Mini-warehouse/self-storage facility, subject to § 275-156.",
          "EXPLICITLY NAMED by right; also § 275-76A(8) 'Warehouse, not exceed 200,00 "
          "square feet in gross floor area' and A(11) light manufacturing by right. "
          "garage_condo unnamed -> conditional via § 275-76C(12) catch-all."),
    "SU-1-A": ("permitted", "permitted", "prohibited", "prohibited", 0.90,
               "§ 275-98C(26)",
               "Mini-warehouse/self-storage facility, subject to § 275-156.",
               "by-right named, BUT § 275-98A minimum tract 100 acres + § 275-99 required "
               "mix of >=3 uses — development-constrained. light industrial/garage condo "
               "not in the closed list."),
    "C-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 275-81A",
            "A building may be erected, altered or used, and land may be used or occupied "
            "... for any of the following uses and for no other",
            _CLOSED),
    "C-2": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 275-86A",
            "A building may be erected, altered or used, and land may be used or occupied "
            "... for any of the following purposes and for no other",
            _CLOSED + "; accessory outdoor storage (§ 275-134) only"),
    "C-3": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 275-92A",
            "A building may be erected, altered or used, and land may be used or occupied "
            "... for any of the following uses and for no other",
            _CLOSED + "; only accessory maintenance-storage structures § 275-92C(1)"),
    "I-1": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 275-62A",
            "A building may be erected or used, and land may be used or occupied ... for "
            "any of the following uses and for no other",
            "institutional closed list (hospitals/schools/cultural/governmental)"),
    "I-2": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
            "§ 275-67A",
            "A building may be erected or used, and land may be used or occupied ... for "
            "any of the following uses and for no other",
            "institutional closed list (human services/schools)"),
    "SU-1": ("prohibited", "prohibited", "permitted", "prohibited", 0.90,
             "§ 275-108A",
             "for any of the following uses and for no other ... (2) Light manufacturing. "
             "(3) A dairy, together with warehouse facilities operating on the same lot, "
             "serving the dairy operation or warehouse facilities serving off-site retail "
             "operations.",
             "closed list; the only warehouse language is the A(3) dairy/retail-service "
             "carve-out — purpose-restricted, NOT general warehousing, so the "
             "warehouse=>conditional convention does not apply. Expressio unius: this "
             "township names 'Mini-warehouse/self-storage facility' explicitly where "
             "intended (M § 275-76A(9), SU-1-A § 275-98C(26)); absent here. Light "
             "manufacturing by right."),
    "SU-2": ("prohibited", "prohibited", "permitted", "prohibited", 0.90,
             "§ 275-113A(1)",
             "Any use permitted in the SU-1 District, pursuant to the provisions stated "
             "in or referred to in Article XIX.",
             "uses defined by reference to SU-1 (self-storage prohibited there); SU-2 "
             "adds only mobile home parks / billboards / single-family attached as "
             "conditional — no storage use."),
    "MS": ("prohibited", "prohibited", "prohibited", "prohibited", 0.92,
           "§ 275-59A",
           "A building may be erected, altered or used, and land may be used or occupied "
           "... for any of the following uses and for no other: (1) Agriculture ... "
           "(3) Municipal service use ... (6) Utilities.",
           "Municipal Services District closed list — agriculture/recreation/municipal/"
           "open-space/utilities only; no storage, warehouse, or manufacturing use. "
           "Kills the 17-parcel MS pool (township facilities land)."),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn == "Delaware County, PA", jn
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, mw, li, lgc, conf, section, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": section, "quote": quote}])
            await con.execute(
                SQL, JID, zc, f"Middletown Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Middletown Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:7} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec']}")
    finally:
        await con.close()


asyncio.run(main())
