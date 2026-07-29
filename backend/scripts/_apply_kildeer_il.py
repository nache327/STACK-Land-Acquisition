"""Kildeer, IL (Lake County) — bank the village zoning ordinance, muni-scoped.

STATUS: LATENT BY DESIGN — same shape as Deer Park (see _apply_deer_park_il.py).
All 1,917 Kildeer parcels carry zoning_code='INC', the Lake County sentinel meaning
"incorporated municipality — county zoning does not apply, see the village"
(catch #51). So the nine district verdicts below match ZERO parcels today. They are
written now so they bite the moment a village GIS layer lands and the parcels rebind
off INC.

UNLIKE Deer Park, Kildeer is NOT a storage no-op on the merits: self-storage is
AFFIRMATIVELY NAMED as a special use in TWO districts (B and LC). Once the rebind
lands, any B/LC parcel >= 1.5 acres inside the wealth ring is a live needle.

Source: Village Code of Kildeer, IL, TITLE 5 ZONING REGULATIONS, current through
Ord. 26-O-003, passed 2026-01-20 (amlegal codelibrary, client `kildeeril`).
Full text pulled via the amlegal JSON render endpoint:
  api/render-doc/kildeeril/latest/kildeer_il/<doc-id>/   (section ids from
  api/section-toc/<numeric-id>/, chapter list from api/toc-chain/<code-uuid>/...)

DISTRICTS — §5-3-1 establishes exactly nine: R-1, R-2, PD-1, PD-2, PD-3, PD-4, B,
LC, O&R. There is NO industrial district in Kildeer at all.

CLOSED LIST — §5-2-13 "USES NOT SPECIFICALLY PERMITTED IN DISTRICT": "When a use is
not specifically listed in the sections devoted to permitted uses, it shall be
assumed that such uses are hereby expressly prohibited unless by a written decision
of the plan commission/board of appeals it is determined that said use is similar to
and not more objectionable than uses listed." Each of the three commercial chapters
restates the closure in its own use sections ("The following uses, AND NO OTHERS,
shall be permitted as of right" / "...may be permitted by special use permit"). So an
unnamed use is prohibited, not unclear (catch #58).

SELF-STORAGE, by district:
  * B  (ch. 10)  — CONDITIONAL. §5-10-3(C) names it as a special use with conditions.
  * LC (ch. 10A) — CONDITIONAL. §5-10A-3 names it as a special use with conditions.
  * O&R (ch. 10B) — PROHIBITED by AFFIRMATIVE EXCLUSION (catch #57), not silence:
    §5-10B-2(C) permits "Lessors of real estate (5311), EXCEPT miniwarehouses and
    self-storage units (53113)." The special-use cross-reference in §5-10B-3(A)
    reaches only "Retail trade uses as allowed in the B zoning district"; in B,
    self-storage sits under "C. Real Estate, Rental And Leasing", NOT under
    "A. Retail Trade" — so the cross-reference does not carry it in.
  * R-1, R-2, PD-1..PD-4 — PROHIBITED. Residential closed lists; no storage,
    warehouse or industrial use named anywhere in them.

light_industrial is prohibited in ALL nine districts. No district permits warehousing
by right, so the "warehouse-by-right => ss/mw conditional" convention never fires
here; self-storage's conditional standing in B/LC rests on its own NAMED entry.
Kildeer has no industrial district, and even the planned-development route forbids it:
§5-14-... planned-development standards state "There shall be no warehousing,
manufacturing, processing, or treatment of products other than that which is clearly
incidental and essential to the use conducted on the same premises." B and O&R repeat
the same bar in their CONDITIONS OF USE sections (§5-10-4(A), §5-10B-4(A)).

luxury_garage_condo is prohibited on every row: no garage-for-compensation use is
NAMED anywhere in Title 5. "GARAGE, PRIVATE" and "CARPORT" appear only in the §5-1
definitions as accessory residential storage of the occupants' own vehicles, and a
definition is not a permitted use. So `lgc-unnamed -> prohibited` applies. This also
keeps the post-ingest gate's sibling-leak check happy — lgc must never outrank a
prohibited self_storage.

The INC row stays UNCLEAR on purpose. Stamping it prohibited would assert a muni-wide
verdict the ordinance contradicts (B and LC are conditional), and INC spans ~133k
parcels across 51 Lake County villages. Scoped to municipality='KILDEER' regardless.

CASING: parcels.city is 'KILDEER' (uppercase) for all 1,917 rows. municipality =
'Kildeer' would match 0 of them — the silent zero from CLAUDE.md.

Uses SELECT-then-INSERT/UPDATE rather than ON CONFLICT: uq_zone_matrix is a unique
EXPRESSION index over (jurisdiction_id, zone_code, COALESCE(municipality, ...)),
not a plain constraint, and ON CONFLICT against it has bitten this repo before.

USAGE (from backend/):
    python scripts/_apply_kildeer_il.py            # report what it would do
    python scripts/_apply_kildeer_il.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

JID = "10d01284-829b-4b03-b416-54bc452b8e70"      # Lake County, IL
MUNI = "KILDEER"                                   # EXACT parcels.city value

_CLOSED_LIST = (
    "CLOSED LIST — §5-2-13: 'When a use is not specifically listed in the sections "
    "devoted to permitted uses, it shall be assumed that such uses are hereby "
    "expressly prohibited unless by a written decision of the plan commission/board "
    "of appeals it is determined that said use is similar to and not more "
    "objectionable than uses listed.' => unnamed use is prohibited, not unclear."
)

# ---------------------------------------------------------------- residential
_R1_BASIS = (
    "§5-4-2 Permitted Uses (the whole list): accessory uses, including off street "
    "parking facilities per ch. 13; agricultural (equine animals per §5-2-14); parks, "
    "when publicly owned and operated; signs (§5-20-19A); single-family detached "
    "dwellings and permitted accessory uses. §5-4-3 Special Uses (the whole list): "
    "church; municipal building; planned development per ch. 14; swimming and tennis "
    "clubs, private (nonprofit). No storage, warehouse, mini-warehouse, industrial or "
    "garage-for-compensation use is named. §5-4-4 mentions storage only to PROHIBIT "
    "off-street parking/storage of commercial motor vehicles outside a garage. "
    + _CLOSED_LIST
)

_R2_BASIS = (
    "§5-5-2 Permitted Uses (the whole list): accessory uses, including off street "
    "parking facilities per ch. 13; agriculture (equine animals per §5-2-14); parks, "
    "when publicly owned and operated; signs (§5-20-19A); single-family detached "
    "dwellings and permitted accessory uses. §5-5-3 Special Uses (the whole list): "
    "church; home occupations; municipal building; planned developments per ch. 14; "
    "swimming club, private (nonprofit). Identical use profile to R-1; only lot area "
    "and bulk differ. No storage/warehouse/industrial/garage use named. §5-5-4 "
    "mentions storage only to PROHIBIT commercial motor vehicles outside a garage. "
    + _CLOSED_LIST
)

# ---------------------------------------------------------------- PD-1 .. PD-4
_PD_TAIL = (
    "The planned-development route does not open storage either. §5-14-3(D)(1)(a) "
    "(Standards For Planned Business Developments): 'Uses within a business or office "
    "portion of a planned development shall be limited to those identified in the "
    "underlying zoning district unless the plan commission/board of appeals "
    "recommends, and the village board approves, similar or compatible uses.' The "
    "underlying district here is the PD district itself, whose permitted and special "
    "use lists name no storage, warehouse or mini-warehouse use — so a business PD "
    "inherits nothing that reaches self-storage. Where a PD is an office park, "
    "§5-14-3(E)(1)(a) limits development to 'business and professional offices, "
    "financial institutions, and research facilities' and (E)(1)(b) adds 'There shall "
    "be no warehousing, manufacturing, processing, or treatment of products other than "
    "that which is clearly incidental and essential to the use conducted on the same "
    "premises.' §5-14-3(D)(1)(d) permits outdoor storage only as an accessory to an "
    "approved business PD, under the §5-10-3G / §5-10A-3G screening standards. "
    + _CLOSED_LIST
)

_PD1_BASIS = (
    "§5-6-1 Permitted Uses (the whole list): 'Single-family detached dwellings, which "
    "conform to the standards of the R-1 District.' §5-6-2 Special Uses (the whole "
    "list): 'Planned large-lot residential, business, or office park developments "
    "complying with the provisions of Title 5, Chapter 14'; church; municipal "
    "building. " + _PD_TAIL
)

_PD2_BASIS = (
    "§5-7-1 Permitted Uses (the whole list): 'Single-family detached dwellings, which "
    "conform to the standards of the R-1 District.' §5-7-2 Special Uses (the whole "
    "list): 'Planned large-lot residential, or cluster and townhome developments, "
    "complying with the provisions of Title 5, Chapter 14'; church; municipal "
    "building. PD-2's PD menu is residential only — it does not even reach business "
    "or office park. " + _PD_TAIL
)

_PD3_BASIS = (
    "§5-8-1 Permitted Uses (the whole list): 'Single-family detached dwellings, which "
    "conform to the standards of the R-1 District.' §5-8-2 Special Uses (the whole "
    "list): 'Planned large-lot residential, cluster and townhome, or office park "
    "developments complying with the provisions of Title 5, Chapter 14'; church; "
    "municipal building. " + _PD_TAIL
)

_PD4_BASIS = (
    "§5-9-1 Permitted Uses: 'None.' (verbatim — the district has no by-right use). "
    "§5-9-2 Special Uses (the whole list): 'Planned large-lot residential, cluster "
    "and townhome, business, office park, or mixed use developments complying with "
    "the provisions of Title 5, Chapter 14'; church; municipal building. " + _PD_TAIL
)

# ---------------------------------------------------------------- B (ch. 10)
_B_BASIS = (
    "SELF-STORAGE IS NAMED AS A SPECIAL USE. §5-10-3 opens: 'The following uses, and "
    "no others, may be permitted by special use permit in accordance with the "
    "provisions of this chapter.' Under 'C. Real Estate, Rental And Leasing': "
    "'Lessors of miniwarehouses and self-storage units (531130), subject to the "
    "following conditions: 1. Minimum lot size shall be one acre (43,560 square "
    "feet). 2. Minimum yard area shall be provided in accordance with section 5-10-10 "
    "of this chapter. 3. If the site adjoins an R-1, R-2 or residential portion of a "
    "PD-1, PD-2 or PD-3 District, transitional yards as required by section 5-10-9 of "
    "this chapter shall be provided. 4. Landscaping within required yards shall be "
    "provided in accordance with a plan reviewed by the Plan Commission/Board of "
    "Appeals and approved by the Village Board. 5. Hours of operation shall be "
    "subject to review and approval. 6. All sales and displays and storage of goods "
    "shall be confined within a permanent structure. 7. The operations of the business "
    "shall conform with the performance standards for noise, odors, toxic and noxious "
    "material, storage and handling of flammable materials and all other standards "
    "established in chapter 12 of this title...' => self_storage and mini_warehouse "
    "CONDITIONAL. Note the 1-acre floor is below the product's 1.5-acre needle floor, "
    "so it never binds first. "
    "light_industrial PROHIBITED: §5-10-2 ('The following uses, and no others, shall "
    "be permitted as of right in the B business district') is retail/finance/personal "
    "service only — no warehousing, wholesaling or manufacturing entry, so the "
    "warehouse-by-right convention does not apply here. §5-10-4(A) Conditions Of Use: "
    "'There shall be no manufacture, processing or treatment of products other than "
    "those which are clearly incidental and essential to the retail business conducted "
    "on the same premises.' §5-10-3(G) allows 'Outdoor storage for principal use "
    "listed elsewhere' — accessory to another use, screened, not a standalone "
    "industrial use. luxury_garage_condo PROHIBITED: no garage-for-compensation use is "
    "named in §5-10-2 or §5-10-3. " + _CLOSED_LIST
)

# ---------------------------------------------------------------- LC (ch. 10A)
_LC_BASIS = (
    "SELF-STORAGE IS NAMED AS A SPECIAL USE. §5-10A-3 opens: 'The following uses, and "
    "no others, may be permitted by special use permit in accordance with the "
    "provisions of chapter 17 of this title.' Its list contains, verbatim, both "
    "'Lessors of miniwarehouses and self-storage units (531130).' and 'Lessors of "
    "miniwarehouses and self-storage units, subject to the following conditions: 1. "
    "Minimum lot size shall be one acre (43,560 square feet). 2. Minimum yard area "
    "shall be provided in accordance with section 5-10-10 of this title. 3. If the "
    "site adjoins an R-1, R-2 or residential portion of a PD-1, PD-2 or PD-3 "
    "district, transitional yards as required by section 5-10-9 of this title shall "
    "be provided. 4. Landscaping within required yards... 5. Hours of operation shall "
    "be subject to review and approval. 6. All sales and displays and storage of goods "
    "shall be confined within a permanent structure. 7. The operations of the business "
    "shall conform with the performance standards... established in chapter 12 of this "
    "title...' (the bare entry and the conditioned entry are a codification "
    "duplicate; both sit inside SPECIAL USES, so the verdict is the same either way) "
    "=> self_storage and mini_warehouse CONDITIONAL. It is NOT in §5-10A-2 PERMITTED "
    "USES ('The following uses, and no others, shall be permitted as of right'), so "
    "conditional and not permitted. "
    "light_industrial PROHIBITED: §5-10A-2 is retail/service only; no warehousing or "
    "manufacturing entry. §5-10A-24 OUTDOOR STORAGE RESTRICTED: 'All outdoor storage "
    "of materials shall be prohibited in the LC Limited Commercial District, except "
    "only that live plant materials may be visible from outside of the structure in "
    "which they are located.' luxury_garage_condo PROHIBITED: no "
    "garage-for-compensation use named. " + _CLOSED_LIST
)

# ---------------------------------------------------------------- O&R (ch. 10B)
_OR_BASIS = (
    "AFFIRMATIVE EXCLUSION, NOT SILENCE (catch #57). §5-10B-2 ('The following uses, "
    "and no others, shall be permitted as of right in the O&R office and research "
    "district'), subsection 'C. Real Estate, Rental And Leasing', reads verbatim: "
    "'Lessors of real estate (5311), EXCEPT miniwarehouses and self-storage units "
    "(53113).' The ordinance grants the parent NAICS class and carves this exact use "
    "back out. §5-10B-3 SPECIAL USES ('The following uses, and no others, may be "
    "permitted by special use permit') does not restore it: its only cross-reference "
    "is 'A. Retail Trade: Retail trade uses as allowed in the B zoning district', and "
    "in B self-storage sits under 'C. Real Estate, Rental And Leasing', not under "
    "'A. Retail Trade' — so the cross-reference does not carry self-storage into O&R. "
    "=> self_storage and mini_warehouse PROHIBITED. "
    "light_industrial PROHIBITED: §5-10B-2 is offices/finance/professional/education/ "
    "healthcare plus accessory retail; §5-10B-4(A) Conditions Of Use: 'There shall be "
    "no manufacture, processing or treatment of products other than those which are "
    "clearly incidental and essential to the business conducted on the same premises.' "
    "Note the district name is Office AND RESEARCH — 'research' here means "
    "'Scientific research and development services (5417)' and 'Medical and diagnostic "
    "laboratories (6215)', i.e. offices and labs, NOT an industrial/flex family "
    "(catch #38). luxury_garage_condo PROHIBITED: no garage-for-compensation use "
    "named. " + _CLOSED_LIST
)

# ---------------------------------------------------------------- INC sentinel
_INC_NOTE = (
    "ordinance_analyzed; verdict pending village GIS rebind to R-1/R-2/PD-1/PD-2/PD-3/"
    "PD-4/B/LC/O&R. Kildeer's Title 5 (current through Ord. 26-O-003, 2026-01-20) has "
    "been read in full and the nine district verdicts are banked muni-scoped to "
    "'KILDEER'. They match 0 parcels today because every Kildeer parcel carries "
    "zoning_code='INC', the Lake County sentinel for 'incorporated — see the village' "
    "(catch #51). This row is left UNCLEAR deliberately: a muni-wide prohibited stamp "
    "would contradict B and LC, whose self_storage is CONDITIONAL. Kildeer is "
    "DONE-BUT-UNBINDABLE, not unexplored — and unlike Deer Park it is NOT a no-op on "
    "the merits: §5-10-3(C) and §5-10A-3 both NAME 'Lessors of miniwarehouses and "
    "self-storage units (531130)' as a special use, so B and LC parcels >= 1.5 acres "
    "inside the wealth ring become live needles the moment the rebind lands."
    "\n\n"
    "REBIND GATE — run this BEFORE trusting any Kildeer needle count:\n"
    "  1. Verify all nine zone_code strings (R-1, R-2, PD-1, PD-2, PD-3, PD-4, B, LC, "
    "O&R) match VERBATIM what the village GIS layer emits — same casing/format trap as "
    "'KILDEER' vs 'Kildeer', just deferred. In particular 'O&R' may arrive as 'OR', "
    "'O-R' or 'O&R'; a mismatch binds nothing.\n"
    "  2. Confirm each district bound a NON-ZERO parcel count and the nine sum to "
    "~1,917.\n"
    "  3. ONLY THEN read the storage needle count. Unlike Deer Park, the expected "
    "yield here is NON-ZERO if any B or LC parcel clears 1.5 acres inside the wealth "
    "ring. A 0 after a successful bind means no qualifying B/LC acreage, which is a "
    "different (and checkable) claim than 'unbindable'.\n"
    "  '0 needles' is trustworthy ONLY after non-zero binding is confirmed — a string "
    "mismatch that bound nothing looks identical to a clean pass. If binding is 0 or "
    "partial the rebind failed silently: STOP, do not accept the yield. If storage "
    "needles appear in R-1/R-2/PD-*/O&R, that is a mismapped district: STOP."
)

ROWS = [
    # (zone_code, ss, mw, li, lgc, human_reviewed, source, cited_subsection, basis)
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-4-2, §5-4-3, §5-2-13", _R1_BASIS),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-5-2, §5-5-3, §5-2-13", _R2_BASIS),
    ("PD-1", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-6-1, §5-6-2, §5-2-13", _PD1_BASIS),
    ("PD-2", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-7-1, §5-7-2, §5-2-13", _PD2_BASIS),
    ("PD-3", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-8-1, §5-8-2, §5-2-13", _PD3_BASIS),
    ("PD-4", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-9-1, §5-9-2, §5-2-13", _PD4_BASIS),
    ("B", "conditional", "conditional", "prohibited", "prohibited", True, "human",
     "§5-10-3(C), §5-10-2, §5-10-4(A)", _B_BASIS),
    ("LC", "conditional", "conditional", "prohibited", "prohibited", True, "human",
     "§5-10A-3, §5-10A-2, §5-10A-24", _LC_BASIS),
    ("O&R", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§5-10B-2(C), §5-10B-3(A), §5-10B-4(A)", _OR_BASIS),
    ("INC", "unclear", "unclear", "unclear", "unclear", False, "unclear",
     "§5-2-13 (closed list); Lake County INC sentinel", _INC_NOTE),
]

# zone_use_matrix.notes is varchar(2048). The two conditional districts carry the
# longest bases (B 2462, LC 2147), so they get a trimmed `notes` while `citations`
# keeps the full verbatim text above. Everything else uses one string for both.
_CLOSED_LIST_SHORT = (
    "CLOSED LIST — §5-2-13: a use 'not specifically listed in the sections devoted to "
    "permitted uses ... shall be assumed [to be] hereby expressly prohibited' absent a "
    "written plan commission/board of appeals finding that it is 'similar to and not "
    "more objectionable than uses listed'."
)

_B_NOTES = (
    "SELF-STORAGE IS NAMED AS A SPECIAL USE. §5-10-3 opens: 'The following uses, and "
    "no others, may be permitted by special use permit in accordance with the "
    "provisions of this chapter.' Under 'C. Real Estate, Rental And Leasing': "
    "'Lessors of miniwarehouses and self-storage units (531130), subject to the "
    "following conditions: 1. Minimum lot size shall be one acre (43,560 square "
    "feet). ... 6. All sales and displays and storage of goods shall be confined "
    "within a permanent structure.' (conditions 2-5: yards per §5-10-10; transitional "
    "yards per §5-10-9 where the site adjoins R-1/R-2/residential PD-1/PD-2/PD-3; "
    "landscaping plan approved by the Village Board; hours of operation subject to "
    "review. Condition 7 defers to the ch. 12 performance standards.) => self_storage "
    "and mini_warehouse CONDITIONAL. The 1-acre floor sits below the product's "
    "1.5-acre needle floor, so it never binds first. "
    "light_industrial PROHIBITED: §5-10-2 ('...and no others, shall be permitted as of "
    "right in the B business district') is retail/finance/personal service only — no "
    "warehousing, wholesaling or manufacturing entry, so the warehouse-by-right "
    "convention does not apply. §5-10-4(A): 'There shall be no manufacture, processing "
    "or treatment of products other than those which are clearly incidental and "
    "essential to the retail business conducted on the same premises.' §5-10-3(G) "
    "allows 'Outdoor storage for principal use listed elsewhere' — accessory and "
    "screened, not a standalone industrial use. luxury_garage_condo PROHIBITED: no "
    "garage-for-compensation use is named in §5-10-2 or §5-10-3. "
    + _CLOSED_LIST_SHORT
)

_LC_NOTES = (
    "SELF-STORAGE IS NAMED AS A SPECIAL USE. §5-10A-3 opens: 'The following uses, and "
    "no others, may be permitted by special use permit in accordance with the "
    "provisions of chapter 17 of this title.' Its list contains, verbatim, both "
    "'Lessors of miniwarehouses and self-storage units (531130).' and 'Lessors of "
    "miniwarehouses and self-storage units, subject to the following conditions: 1. "
    "Minimum lot size shall be one acre (43,560 square feet). ... 6. All sales and "
    "displays and storage of goods shall be confined within a permanent structure.' "
    "(the bare entry and the conditioned entry are a codification duplicate; both sit "
    "inside SPECIAL USES, so the verdict is the same either way) => self_storage and "
    "mini_warehouse CONDITIONAL. It is NOT in §5-10A-2 PERMITTED USES ('The following "
    "uses, and no others, shall be permitted as of right'), so conditional, not "
    "permitted. light_industrial PROHIBITED: §5-10A-2 is retail/service only, with no "
    "warehousing or manufacturing entry; §5-10A-24 OUTDOOR STORAGE RESTRICTED: 'All "
    "outdoor storage of materials shall be prohibited in the LC Limited Commercial "
    "District, except only that live plant materials may be visible from outside of "
    "the structure in which they are located.' luxury_garage_condo PROHIBITED: no "
    "garage-for-compensation use named. " + _CLOSED_LIST_SHORT
)

NOTES_OVERRIDE = {"B": _B_NOTES, "LC": _LC_NOTES}

_SELECT = """
SELECT id, self_storage::text ss, mini_warehouse::text mw,
       light_industrial::text li, luxury_garage_condo::text lgc, human_reviewed
  FROM zone_use_matrix
 WHERE jurisdiction_id = $1::uuid AND zone_code = $2 AND municipality = $3
   AND deleted_at IS NULL
"""

_INSERT = """
INSERT INTO zone_use_matrix
  (jurisdiction_id, zone_code, municipality, self_storage, mini_warehouse,
   light_industrial, luxury_garage_condo, human_reviewed, classification_source,
   notes, cited_subsection, citations, confidence, created_at, updated_at)
VALUES ($1::uuid, $2, $3, $4::use_permission_enum, $5::use_permission_enum,
        $6::use_permission_enum, $7::use_permission_enum, $8,
        $9::classification_source_enum, $10, $11, $12::jsonb, $13, now(), now())
"""

# NOTE: numbered independently of _INSERT. An UPDATE that carried unreferenced
# $1/$2/$3 placeholders (jurisdiction/zone/municipality are not in the SET or WHERE)
# fails asyncpg prepare with "could not determine data type of parameter $1".
_UPDATE = """
UPDATE zone_use_matrix
   SET self_storage = $1::use_permission_enum,
       mini_warehouse = $2::use_permission_enum,
       light_industrial = $3::use_permission_enum,
       luxury_garage_condo = $4::use_permission_enum,
       human_reviewed = $5,
       classification_source = $6::classification_source_enum,
       notes = $7, cited_subsection = $8, citations = $9::jsonb,
       confidence = $10, updated_at = now()
 WHERE id = $11
"""


async def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Kildeer IL zoning verdicts.")
    ap.add_argument("--apply", action="store_true", help="Write. Otherwise report only.")
    args = ap.parse_args()

    c = await asyncpg.connect(get_sync_dsn(), timeout=60)
    await c.execute("SET statement_timeout = 120000")
    try:
        n_muni = await c.fetchval(
            "SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2",
            JID, MUNI)
        print(f"scope municipality={MUNI!r} -> {n_muni:,} parcels in Lake County IL",
              flush=True)
        if n_muni == 0:
            print("REFUSING: scope matches 0 parcels — casing is wrong.", flush=True)
            sys.exit(2)

        for (code, ss, mw, li, lgc, human, src, cite, basis) in ROWS:
            existing = await c.fetchrow(_SELECT, JID, code, MUNI)
            citations = json.dumps([{"section": cite, "text": basis}])
            notes = NOTES_OVERRIDE.get(code, basis)
            if len(notes) > 2048:                     # notes is varchar(2048)
                print(f"REFUSING: notes for {code} is {len(notes)} chars > 2048",
                      flush=True)
                sys.exit(3)
            conf = 1.0 if human else None
            action = "UPDATE" if existing else "INSERT"
            print(f"  {action} {code:<14} ss={ss:<11} mw={mw:<11} li={li:<12} "
                  f"lgc={lgc:<11} human={human}  notes={len(notes)}c", flush=True)
            if not args.apply:
                continue
            if existing:
                await c.execute(_UPDATE, ss, mw, li, lgc, human,
                                src, notes, cite, citations, conf, existing["id"])
            else:
                await c.execute(_INSERT, JID, code, MUNI, ss, mw, li, lgc, human,
                                src, notes, cite, citations, conf)

        if not args.apply:
            print("\nreport only — re-run with --apply", flush=True)
            return
        print(f"\napplied {len(ROWS)} rows scoped to municipality={MUNI!r}", flush=True)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
