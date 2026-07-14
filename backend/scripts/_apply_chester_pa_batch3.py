"""Chester County PA (jid 7f5293ff…) — Batch-3 Stage-4 verdicts (Session C partition).

SHARED county with Session B (B takes ranks 5-8; C takes ranks 1-4). Muni-scoped →
parallel-safe. PA spatially bound → NO rebind; use tables via eCode360 print-endpoint
(East Nantmeal not on eCode360 → town PDF). Self-storage detected BY NAME (catch #37).
zone_code strings match parcels.zoning_code exactly. human_reviewed.

catch #38 institutional saves (NOT grounded as needles): West Chester "IS" = Institutional
(§112-312); East Nantmeal "EI" = Educational/Institutional (§801); West Vincent "M" =
Municipal (Art.XV); Westtown "T" = Township parkland (§170-1401).
NB-Twp J25: East Nantmeal self-storage NAMED only in C (special exception) → NOT
convention-conditional in IA-1/IA-2.
warehouse⇒conditional convention (UNNAMED self-storage) applied + FLAGGED: West Vincent
PC/LI (open catch-all), Westtown C-1/C-2/M-U (CF-WV / CF-WT). luxury_garage_condo prohibited
everywhere (#58).

SKIP re-score (shared county — coordinator runs ONE reconciling Chester re-score after B+C
merge). verify_batch reads the matrix directly, so needle counts are accurate without it.

Run: python scripts/_apply_chester_pa_batch3.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"
P, C, X = "permitted", "conditional", "prohibited"

TOWNS = {
    "West Chester Borough": ("West Chester Borough Zoning Ch. 112, use table § 112-304 (eCode360 WE0442)", {
        "ID": ("Industrial District", P, P, P, X, 0.93, "§ 112-304.A(27)",
               '"Mini storage" marked in the ID column of the § 112-304.A by-right use table '
               "(also Warehousing/Manufacturing/Light industrial by right). PERMITTED by right."),
        "CS": ("Commercial Service District", C, C, X, X, 0.90, "§ 112-304.D(9)",
               '"Mini storage; wholesale storage" in the § 112-304.D SPECIAL EXCEPTION table '
               "(CS column). CONDITIONAL (special exception); light manufacturing not in CS."),
        "IS": ("Institutional District", X, X, X, X, 0.90, "§ 112-312",
               "catch #38: IS = INSTITUTIONAL (health care/nursing/educational/religious), NOT "
               "industrial; mini storage absent from the IS column → prohibited."),
        "MU": ("Mixed-Use District", X, X, P, X, 0.88, "§ 112-304",
               "mini storage NOT designated in MU (named use omitted → prohibited); light "
               "industrial IS by right in MU (§ 112-304.A(23)) but warehouse is not, so no "
               "convention trigger for self_storage."),
    }),
    "East Nantmeal Township": ("East Nantmeal Twp Zoning Ordinance of 2011 (town PDF; NOT eCode360)", {
        "C": ("Commercial", C, C, X, X, 0.82, "§ 501.C.6",
              '"Self-storage facilities." — listed as a Zoning-Hearing-Board SPECIAL EXCEPTION '
              "(§ 501.C), NAMED → CONDITIONAL. Light manufacturing absent (retail/office district). "
              "CURRENCY CAVEAT: 2011 ordinance (town's own hosted copy); live site Cloudflare-gated, "
              "post-2011 recodification not ruled out — flagged."),
        "IA-1": ("Industrial/Agricultural 1", X, X, C, X, 0.80, "§ 601",
                 "self-storage NAMED only in the C district → absent in IA-1 (closed-list § 601.A "
                 "'and no other') → prohibited (NB-J25; warehouse here is conditional not by-right, "
                 "so no convention). light_industrial conditional (industrial parks/labs § 601.B)."),
        "IA-2": ("Industrial/Agricultural 2", X, X, C, X, 0.75, "§ 701",
                 "self-storage 'otherwise provided for' (named in C) → not affirmatively grounded "
                 "by the § 701.C open catch-all → prohibited (conservative). light_industrial "
                 "conditional (wholesale storage by right + IA-1 uses incorporated)."),
        "EI": ("Educational/Institutional", X, X, X, X, 0.85, "§ 801",
               "catch #38: EI = Educational/Institutional, NOT industrial; self-storage/warehouse/"
               "mfg all absent → prohibited."),
    }),
    "West Vincent Township": ("West Vincent Twp Zoning Ch. 390 (eCode360)", {
        "PC/LI": ("Planned Commercial/Limited Industrial", C, C, C, X, 0.62, "§ 390-53B(13)",
                  "self-storage UNNAMED; grounded CONDITIONAL via the affirmative open catch-all "
                  '§ 390-53B(13) "Uses not specifically provided for herein" (conditional; § 390-156 '
                  "standards) — NOT a closed list. light manufacturing conditional (§ 390-53B(8)). "
                  "FLAG CF-WV: convention/catch-all, not a named self-storage use."),
        "LVCC": ("Ludwigs Village Center Commercial", X, X, X, X, 0.85, "§ 390-58",
                 "self-storage absent; only a narrow 'substantially similar' clause (self-storage "
                 "not similar to listed retail/office) → prohibited."),
        "M": ("Municipal", X, X, X, X, 0.90, "§ 390 Art. XV",
              "catch #38: M = Municipal (government/institutional land), NOT Manufacturing → "
              "prohibited no-op."),
    }),
    "Westtown Township": ("Westtown Twp Zoning Ch. 170 (eCode360 WE1870)", {
        "C-1": ("Neighborhood and Highway Commercial", C, C, X, X, 0.65, "§ 170-1101A(8)",
                'self-storage UNNAMED; "Wholesale sales, storage, or distribution facilities" '
                "PERMITTED by right → warehouse⇒self_storage CONDITIONAL convention (FLAG CF-WT). "
                "light manufacturing absent in C-1."),
        "C-2": ("Highway Commercial", C, C, X, X, 0.65, "§ 170-11A01A(8)",
                'self-storage UNNAMED; "Storage or distribution facilities" by right → '
                "warehouse⇒self_storage CONDITIONAL convention (FLAG CF-WT)."),
        "M-U": ("Multi-Use", C, C, C, X, 0.65, "§ 170-1001A(1)",
                "incorporates C-1 by-right storage/distribution (§ 170-1101A(8)) → warehouse⇒"
                "self_storage CONDITIONAL convention (FLAG CF-WT); light industrial special "
                "exception (§ 170-1001B)."),
        "POC": ("Planned Office Campus", X, X, X, X, 0.85, "§ 170-1201",
                "office-only closed list; storage only accessory; no warehouse/self-storage → "
                "prohibited."),
        "T": ("Township", X, X, X, X, 0.90, "§ 170-1401",
              "catch #38: T = Township (municipal parkland/public, NOT Town Center); self-storage "
              "absent → prohibited no-op."),
    }),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
  mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
  luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=90)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Chester" in jn, f"unexpected jurisdiction: {jn!r}"
        # SELECT-check: don't collide with B's grounded towns
        already = {r['municipality'] for r in await con.fetch(
            "SELECT DISTINCT municipality FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND human_reviewed AND municipality IS NOT NULL", JID)}
        collide = already & set(TOWNS)
        if collide:
            print(f"WARNING: these towns already grounded (collision w/ B?): {collide} — proceeding "
                  "(muni-scoped upsert is idempotent, but verify partition).")
        print(f"jurisdiction: {jn}")
        await con.execute("SET statement_timeout = '90s'")
        for muni, (ordstr, zones) in TOWNS.items():
            for zc, (zname, ss, mw, li, lgc, conf, sec, quote) in zones.items():
                cites = json.dumps([{"ordinance": ordstr, "section": sec, "quote": quote}])
                note = f"{zc} ({zname}) — self_storage {ss}; {sec}: {quote[:160]}"
                await con.execute(SQL, JID, zc, zname, muni, ss, mw, li, lgc, cites, sec, conf, note)
        for muni in TOWNS:
            n = await con.fetchval("SELECT count(*) FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
                                   "AND municipality=$2 AND deleted_at IS NULL AND human_reviewed", JID, muni)
            j = await con.fetch(
                "SELECT p.zoning_code, count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
                "  AND prm.median_hhi>=100000) needles "
                "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
                "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
                "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
                "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
                "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 GROUP BY 1 HAVING count(*) FILTER "
                "(WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000)>0 "
                "ORDER BY 2 DESC", JID, muni)
            tot = sum(r['needles'] for r in j)
            print(f"  {muni}: {n} rows, needles={tot}: " + ", ".join(f"{r['zoning_code']}:{r['needles']}" for r in j))
    finally:
        await con.close()


asyncio.run(main())
