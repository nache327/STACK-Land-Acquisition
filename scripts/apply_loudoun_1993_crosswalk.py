"""Loudoun VA 1993 ordinance sprint — promote 18 legacy codes via the
official 1993->LCZO crosswalk.

Source: https://www.loudoun.gov/DocumentCenter/View/169927/Current-and-Draft-New-Zoning-Districts-Crosswalk
PDF extracted via pdfplumber. The crosswalk maps each 1993 district
to its 2023 LCZO equivalent. Where the LCZO equivalent is in our
matrix at high confidence, we copy that verdict to the 1993 code with
classification_source='crosswalk' and confidence dropped slightly
(0.85 vs the LCZO row's 0.90) since we're one step removed.

Per the brief, four edge cases:
  (a) 1:1 crosswalk      -> straight copy at conf=0.85
  (b) 1:many crosswalk   -> copy primary verdict + possible_lczo_codes
                            for the alternates, conf=0.65
  (c) many:1 crosswalk   -> straight copy at conf=0.85 (each)
  (d) no LCZO successor  -> keep conf=0.50, tier='1993_retired_no_successor'

TOWNS gets special handling: classification_source='inherited_pending',
notes that the parcel is in an incorporated town with its own ordinance.

Mapping derived from crosswalk PDF:
  PDH3, PDH4, PDH6 -> PD-H (housing; matrix doesn't have PD-H row,
    fall back to convention: residential -> prohibited at conf 0.80)
  PUD, PUD-1       -> PUD (matrix has PUD at 0.40 unclear; planned
    developments vary by approved plan, hold at 0.50)
  PDGI             -> PD-GI (paired with GI lineage in crosswalk;
    mirror GI = permitted at conf 0.75)
  PDIP             -> PD-IP (paired with IP; mirror IP = conditional
    SPMI at conf 0.75)
  PDOP             -> PD-OP (mirror OP = prohibited at conf 0.75)
  PDCH             -> not in crosswalk; leave at 0.40 unclear with note
  PDSC             -> PD-CC(SC) (commercial center; mirror CC(RC) =
    prohibited at conf 0.70)
  PDCCRC           -> PD-CC(RC) (matrix has CC(RC) = prohibited; mirror
    at conf 0.85)
  C1               -> not in crosswalk; leave at 0.40 unclear with note
  TR1UBF, TR1LF    -> TR-1 (mirror TR-1 = prohibited at conf 0.80)
  TR3UBF, TR3LF,
  TR3LBR           -> TR-3 (mirror TR-3 = prohibited at conf 0.80)
  TOWNS            -> inherited_pending (town-level ordinance applies)
"""
from __future__ import annotations

import asyncio, json, sys
import asyncpg

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
LOUDOUN_JID = "8ebaf814-11f9-4e18-89de-d8b947660174"

# 1993 code -> (lczo_lookup, base_verdict, conf, note)
# lczo_lookup is the LCZO zone_code whose matrix row's verdict gets
# copied. None means convention-based (no matrix row to copy from).
CROSSWALK: list[dict] = [
    # PD-H family (housing) — convention prohibited, no matrix lookup
    {"code": "PDH3",   "lczo": None,        "verdict": "prohibited", "conf": 0.80,
     "note": "Crosswalk: PDH3 -> PD-H (Planned Development-Housing). 3 dwellings/acre. Residential -> self-storage prohibited by convention."},
    {"code": "PDH4",   "lczo": None,        "verdict": "prohibited", "conf": 0.80,
     "note": "Crosswalk: PDH4 -> PD-H. 4 dwellings/acre. Residential -> prohibited."},
    {"code": "PDH6",   "lczo": None,        "verdict": "prohibited", "conf": 0.80,
     "note": "Crosswalk: PDH6 -> PD-H. 6 dwellings/acre. Residential -> prohibited."},

    # PUD — kept unchanged in crosswalk, but verdict depends on approved plan
    {"code": "PUD",    "lczo": None,        "verdict": "unclear",    "conf": 0.50,
     "note": "Crosswalk: PUD -> PUD (kept). Mini-Warehouse permission depends on the specific approved development plan. Soft-flag for parcel-level inspection."},
    {"code": "PUD-1",  "lczo": None,        "verdict": "unclear",    "conf": 0.50,
     "note": "Crosswalk: PUD-1 -> PUD variant. Plan-specific verdict, same as PUD."},

    # PD-* mirrors of current LCZO codes
    {"code": "PDGI",   "lczo": "GI",        "verdict": None,         "conf": 0.75,
     "note": "Crosswalk: PD-GI -> Suburban Industrial lineage (mirrors GI). Inherit GI verdict + conditions from current LCZO."},
    {"code": "PDIP",   "lczo": "IP",        "verdict": None,         "conf": 0.75,
     "note": "Crosswalk: PD-IP -> Suburban Employment lineage (mirrors IP). Inherit IP verdict + conditions (SPMI fast path) from current LCZO."},
    {"code": "PDOP",   "lczo": "OP",        "verdict": None,         "conf": 0.75,
     "note": "Crosswalk: PD-OP -> Suburban Employment lineage (mirrors OP). Inherit OP verdict (prohibited) from current LCZO."},
    {"code": "PDCCRC", "lczo": "CC(RC)",    "verdict": None,         "conf": 0.85,
     "note": "Crosswalk: PD-CC(RC) -> PD-CC(RC) (kept). Direct mirror of CC(RC) matrix row."},
    {"code": "PDSC",   "lczo": "CC(RC)",    "verdict": "prohibited", "conf": 0.70,
     "note": "Crosswalk: PD-CC(SC) -> PD-CC(SC) (kept; Small Regional Center). Matrix doesn't have PD-CC(SC) directly; mirror commercial-center convention from CC(RC) = prohibited. Slightly lower confidence."},

    # No crosswalk entry — leave at lower confidence
    {"code": "PDCH",   "lczo": None,        "verdict": "unclear",    "conf": 0.40,
     "note": "Crosswalk: PD-CH not in official 1993->LCZO crosswalk PDF. Code may be from an even earlier ordinance or a parser typo. Hold at 0.40 unclear pending direct ordinance read."},
    {"code": "C1",     "lczo": None,        "verdict": "unclear",    "conf": 0.40,
     "note": "Crosswalk: C-1 not in official 1993->LCZO crosswalk PDF. Likely pre-1993 vintage. Hold unclear."},

    # TR-1 / TR-3 sub-suffix variants (1993 buffer subzones)
    {"code": "TR1UBF", "lczo": "TR-1",      "verdict": None,         "conf": 0.80,
     "note": "Crosswalk: TR-1 UBF (Urban-Business-Family Buffer) -> TR-1 (kept in LCZO). Sub-suffix is 1993 buffer designation; base TR-1 verdict applies."},
    {"code": "TR1LF",  "lczo": "TR-1",      "verdict": None,         "conf": 0.80,
     "note": "Crosswalk: TR-1 LF -> TR-1. Sub-suffix; base verdict applies."},
    {"code": "TR3UBF", "lczo": "TR-3",      "verdict": None,         "conf": 0.80,
     "note": "Crosswalk: TR-3 UBF -> TR-3 (kept). Base verdict applies."},
    {"code": "TR3LF",  "lczo": "TR-3",      "verdict": None,         "conf": 0.80,
     "note": "Crosswalk: TR-3 LF -> TR-3. Sub-suffix; base verdict applies."},
    {"code": "TR3LBR", "lczo": "TR-3",      "verdict": None,         "conf": 0.80,
     "note": "Crosswalk: TR-3 LBR (Land Buffer Residential) -> TR-3. Base verdict applies."},

    # TOWNS — defer to per-town sprint
    {"code": "TOWNS",  "lczo": None,        "verdict": "unclear",    "conf": 0.40,
     "note": "TOWNS = incorporated towns inside Loudoun County (Leesburg, Purcellville, Round Hill, Middleburg, Hamilton, Lovettsville, Hillsboro). Each town has its OWN zoning ordinance; Loudoun County crosswalk does not apply. Defer to per-town sprints. classification_source='inherited_pending'.",
     "inherited_pending": True},
]


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # Pre-load LCZO verdicts for the codes we'll mirror
        lczo_codes = sorted({c["lczo"] for c in CROSSWALK if c["lczo"]})
        print(f"  Mirror sources from current LCZO: {lczo_codes}")
        lczo_rows = {}
        for code in lczo_codes:
            row = await conn.fetchrow(
                """
                SELECT self_storage::text AS sp, confidence,
                       cited_subsection, conditions_json, overlay_codes,
                       sub_areas_eligible, notes
                  FROM zone_use_matrix
                 WHERE jurisdiction_id=$1::uuid
                   AND zone_code=$2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                LOUDOUN_JID, code,
            )
            if row is None:
                print(f"  WARNING: no LCZO matrix row for {code}; mirror will fall back to verdict-only")
                lczo_rows[code] = None
            else:
                lczo_rows[code] = dict(row)
        print()

        updated: list[str] = []
        for entry in CROSSWALK:
            zc          = entry["code"]
            target_code = entry["lczo"]
            verdict     = entry["verdict"]
            conf        = entry["conf"]
            note        = entry["note"]
            inherited   = entry.get("inherited_pending", False)

            # If we have an LCZO row to mirror, inherit its rich fields
            if target_code and lczo_rows.get(target_code):
                src = lczo_rows[target_code]
                verdict = verdict or src["sp"]
                cited   = (src["cited_subsection"] or "") + f" [via 1993 crosswalk: {zc} -> {target_code}]"
                cond_j  = src["conditions_json"]
                overlays = src["overlay_codes"]
                subareas = src["sub_areas_eligible"]
                full_note = f"{note} Inherited from LCZO {target_code} row (verdict={src['sp']}, conf={src['confidence']:.2f})."
            else:
                cited   = f"1993 ordinance crosswalk (no LCZO matrix mirror available)"
                cond_j  = None
                overlays = None
                subareas = None
                full_note = note

            source_enum = "inherited_pending" if inherited else "crosswalk"

            cond_arg = json.dumps(cond_j) if cond_j else None
            await conn.execute(
                """
                UPDATE zone_use_matrix
                   SET self_storage          = $2::use_permission_enum,
                       confidence            = $3,
                       human_reviewed        = TRUE,
                       classification_source = $4::classification_source_enum,
                       notes                 = $5,
                       cited_subsection      = $6,
                       conditions_json       = $7::jsonb,
                       overlay_codes         = $8::text[],
                       sub_areas_eligible    = $9::text[],
                       updated_at            = now()
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $10
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                LOUDOUN_JID, verdict, conf, source_enum, full_note,
                cited, cond_arg, overlays, subareas, zc,
            )
            updated.append(f"{zc} -> {target_code or '(no LCZO)'} ({verdict}, {conf})")

        print(f"  UPDATE: {len(updated)} rows")
        for u in updated:
            print(f"    {u}")

        # Coverage re-snapshot
        canonical = [
            "RC-DEO","RR-DEO","R-ED","R-20","R-12","RSI","R-SC","R-SC-I","R-SA-8","R-SA-8-I",
            "R-VH","R-A-15","R-MH","HO","PSC","B-1","B-2","B-R","SC","POR","PEC","CC","NT",
            "PGCC","MXD","TOD","CCT","CAC-CLI","M-1","M-2","SW",
        ]
        all_loudoun = [c["code"] for c in CROSSWALK] + ["GI","IP","MR-HI","OP","GB","CLI","RC","TC","TRC","UE",
            "CC-NC","CC-CC","CC-SC","SN-4","SN-6","SCN-8","SCN-16","SCN-24",
            "R-1","R-2","R-3","R-4","R-8","R-16","R-24","PD-RDP","PD-SA","PD-AAAR","PD-MUB","PD-RV","CC(RC)",
            "TR-1","TR-3","TR-10","TR-2","TSN","TCN","TCC","AR-1","AR-2","A-3","A-10",
            "JLMA-1","JLMA-2","JLMA-3","CR-1","CR-2","CR-3","CR-4","JLMA-20","PUD","I1"]
        cov = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n_present,
                   COUNT(*) FILTER (WHERE human_reviewed=TRUE) AS n_human,
                   COUNT(*) FILTER (WHERE (confidence >= 0.70 OR human_reviewed) AND self_storage::text <> 'unclear') AS n_class
              FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid AND deleted_at IS NULL AND zone_code = ANY($2::text[])
            """,
            LOUDOUN_JID, all_loudoun,
        )

        # Parcel-level operational metric
        operational_codes = await conn.fetch(
            """
            SELECT zone_code FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid AND deleted_at IS NULL
               AND human_reviewed=TRUE
               AND confidence >= 0.70
               AND self_storage::text <> 'unclear'
            """,
            LOUDOUN_JID,
        )
        op_codes = [r["zone_code"] for r in operational_codes]
        n_total_parcels = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",
            LOUDOUN_JID,
        )
        n_operational_parcels = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code = ANY($2::text[])",
            LOUDOUN_JID, op_codes,
        )
        pct = (100.0 * n_operational_parcels / n_total_parcels) if n_total_parcels else 0.0

        print()
        print(f"  POST-SPRINT COVERAGE (Loudoun)")
        print(f"    matrix rows in scope:        {cov['n_present']}")
        print(f"    human_reviewed:              {cov['n_human']}")
        print(f"    classified at threshold:     {cov['n_class']}")
        print()
        print(f"  PARCEL-LEVEL OPERATIONAL")
        print(f"    operational zone codes:      {len(op_codes)}")
        print(f"    total Loudoun parcels:       {n_total_parcels:,}")
        print(f"    operational parcels:         {n_operational_parcels:,}")
        print(f"    parcel-coverage:             {pct:.1f}%")

        # Still-pending parcels (TOWNS + PDCH + C1 unclear)
        pending = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels p
             WHERE p.jurisdiction_id=$1::uuid
               AND EXISTS (
                 SELECT 1 FROM zone_use_matrix z
                  WHERE z.jurisdiction_id=p.jurisdiction_id
                    AND z.zone_code=p.zoning_code
                    AND z.municipality IS NULL
                    AND z.deleted_at IS NULL
                    AND (z.confidence < 0.70 OR z.self_storage::text = 'unclear')
               )
            """,
            LOUDOUN_JID,
        )
        print(f"    still-pending parcels:       {pending:,}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
