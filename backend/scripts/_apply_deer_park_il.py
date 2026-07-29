"""Deer Park, IL (Lake County) — bank the village zoning ordinance, muni-scoped.

STATUS: LATENT BY DESIGN. All 1,338 Deer Park parcels carry zoning_code='INC', the
Lake County sentinel meaning "incorporated municipality — county zoning does not
apply, see the village" (catch #51). So the five district verdicts below match ZERO
parcels today. They are written now so they bite the moment a village GIS layer
lands and the parcels rebind off INC.

Source: Village of Deer Park Zoning Code, Chapter 158 (Rev. 11/25).

CLOSED LIST — §158.09: "No building or tract of land shall be devoted to any use
other than one (1) which is specified as a permitted or special use in the zoning
district in which such land or building is located." So an unnamed use is
prohibited, not unclear (catch #58).

Self-storage / mini-warehouse is named in NO district. Every district is therefore
prohibited for storage. light_industrial is prohibited everywhere EXCEPT PD, where
business-park warehousing is a special use — see the PD note.

luxury_garage_condo is set prohibited on every row: no garage-for-compensation use
is NAMED anywhere in the code (GARAGE, PUBLIC appears only in §158.03 DEFINITIONS,
and a definition is not a permitted use), so the `lgc-unnamed -> prohibited` rule
applies. This also keeps the post-ingest gate's sibling-leak check happy — lgc must
never outrank a prohibited self_storage.

The INC row stays UNCLEAR on purpose. Stamping it prohibited would assert a
muni-wide verdict the ordinance does not support (PD's light_industrial is
conditional), and INC spans 133,844 parcels across 51 Lake County villages — 132,506
of them outside Deer Park. Scoped to municipality='DEER PARK' regardless.

CASING: parcels.city is 'DEER PARK' (uppercase). municipality='Deer Park' matches 0
of the 1,338 rows — the silent zero from CLAUDE.md.

Uses SELECT-then-INSERT/UPDATE rather than ON CONFLICT: uq_zone_matrix is a unique
EXPRESSION index over (jurisdiction_id, zone_code, COALESCE(municipality, ...)),
not a plain constraint, and ON CONFLICT against it has bitten this repo before.

USAGE (from backend/):
    python scripts/_apply_deer_park_il.py            # report what it would do
    python scripts/_apply_deer_park_il.py --apply
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
MUNI = "DEER PARK"                                 # EXACT parcels.city value

_R1_USES = (
    "§158.27(A) Permitted Uses: single-family detached dwellings; home occupations; "
    "signs; temporary construction signs/structures; accessory uses; public parks; "
    "wildlife preserves; community residences. (B) Special Uses: utility and public "
    "uses under franchise; parks/recreation/forest/wildlife preserves owned by the "
    "Village; church/places of worship; antennas and towers; country clubs; golf "
    "courses. No storage, warehouse, industrial or garage-for-compensation use is "
    "named. Closed list per §158.09 => prohibited."
)

# The PD basis carries BOTH the express carve-out and the special use, verbatim.
_PD_BASIS = (
    "§158.30 PD Planned Development District — purpose: 'professional office, retail, "
    "and service establishments'. STORAGE IS EXPRESSLY CARVED OUT: §158.30(A)(50) "
    "permits 'Wholesale establishments excluding any building for which the principal "
    "use is storage warehousing.' That is an affirmative exclusion of exactly this "
    "use, not silence (catch #57) — a self-storage facility IS a building whose "
    "principal use is storage warehousing. Self-storage/mini-warehouse are named "
    "nowhere else in the district, so prohibited under the §158.09 closed list. "
    "WAREHOUSING EXISTS ONLY AS ANCILLARY: §158.30(B)(15) makes 'Business parks, "
    "comprised of offices, laboratories, showrooms or warehousing and related uses "
    "for wholesale and service businesses' a SPECIAL use, conditioned by "
    "§158.30(B)(22)(f) on (i) all activities conducted within an enclosed building, "
    "(ii) no noise, smells or vibrations beyond the property lines, (iii) NO OUTSIDE "
    "STORAGE OF MATERIALS, (iv) loading docks at the rear and screened from all roads "
    "and adjoining properties, (v) low-glare exterior lighting. Warehousing is thus "
    "ancillary to a wholesale/service business park, NEVER a standalone storage "
    "operation => light_industrial conditional, self_storage prohibited."
)

_INC_NOTE = (
    "ordinance_analyzed; verdict pending village GIS rebind to R-1/R-1a/R-2/PD/"
    "PUBLIC LANDS. Deer Park's Chapter 158 (Rev. 11/25) has been read in full and the "
    "five district verdicts are banked muni-scoped to 'DEER PARK'. They match 0 "
    "parcels today because every Deer Park parcel carries zoning_code='INC', the Lake "
    "County sentinel for 'incorporated — see the village' (catch #51). This row is "
    "left UNCLEAR deliberately: a muni-wide prohibited stamp would overstate PD, whose "
    "light_industrial is conditional. Deer Park is DONE-BUT-UNBINDABLE, not unexplored."
    "\n\n"
    "REBIND GATE — run this BEFORE trusting any Deer Park needle count:\n"
    "  1. Verify all five zone_code strings (R-1, R-1a, R-2, PUBLIC LANDS, PD) match "
    "VERBATIM what the village GIS layer emits — same casing/format trap as "
    "'DEER PARK' vs 'Deer Park', just deferred. A mismatch binds nothing.\n"
    "  2. Confirm each district bound a NON-ZERO parcel count and the five sum to "
    "~1,338.\n"
    "  3. ONLY THEN read the storage needle count. Expected 0 across all districts "
    "including PD, via the §158.30(A)(50) carve-out.\n"
    "  '0 needles' is trustworthy ONLY after non-zero binding is confirmed — a string "
    "mismatch that bound nothing looks identical to a clean pass. If binding is 0 or "
    "partial the rebind failed silently: STOP, do not accept the yield. If binding is "
    "full but storage needles appear, that is a mismapped district or the carve-out "
    "failing to travel: STOP."
)

ROWS = [
    # (zone_code, ss, mw, li, lgc, human_reviewed, source, cited_subsection, basis)
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§158.27", _R1_USES),
    ("R-1a", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§158.28(C)",
     "§158.28(C) Uses: 'Uses permitted in the Hillcrest District shall be the same "
     "use as permitted in the R-1 District.' R-1a is an overlay on R-1 and adds no "
     "use; it varies only lot area, dwelling size, FAR and yards. Inherits R-1's "
     "verdicts. " + _R1_USES),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited", True, "human",
     "§158.29",
     "§158.29(A)/(B) permitted and special use lists are IDENTICAL to R-1 §158.27 "
     "(single-family district on 80,000 sf lots); only lot area, frontage and setbacks "
     "differ. No storage/warehouse/industrial/garage use named. " + _R1_USES),
    ("PUBLIC LANDS", "prohibited", "prohibited", "prohibited", "prohibited", True,
     "human", "§158.35",
     "§158.35(B)(1)(a) Permitted: emergency service facilities (fire, rescue, police); "
     "public administrative facilities (Village Hall, Public Works); public educational "
     "and cultural facilities (schools, libraries, museums, cultural centers); public "
     "recreational facilities (parks, playfields, open space, community/recreation "
     "centers). (b) Special: government buildings and public uses; utility substations "
     "(electric, water treatment, sewage treatment, pumping stations). The similar-use "
     "clause — 'Other uses similar to those listed below may be permitted as determined "
     "appropriate by the Village Board' — is confined to PUBLIC uses; commercial "
     "self-storage is not a public facility and cannot enter through it. Closed list "
     "per §158.09 => prohibited."),
    ("PD", "prohibited", "prohibited", "conditional", "prohibited", True, "human",
     "§158.30(A)(50), §158.30(B)(15), §158.30(B)(22)(f)", _PD_BASIS),
    ("INC", "unclear", "unclear", "unclear", "unclear", False, "unclear",
     "§158.09 (closed list); Lake County INC sentinel", _INC_NOTE),
]

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

_UPDATE = """
UPDATE zone_use_matrix
   SET self_storage = $4::use_permission_enum,
       mini_warehouse = $5::use_permission_enum,
       light_industrial = $6::use_permission_enum,
       luxury_garage_condo = $7::use_permission_enum,
       human_reviewed = $8,
       classification_source = $9::classification_source_enum,
       notes = $10, cited_subsection = $11, citations = $12::jsonb,
       confidence = $13, updated_at = now()
 WHERE id = $14
"""


async def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Deer Park IL zoning verdicts.")
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
            conf = 1.0 if human else None
            action = "UPDATE" if existing else "INSERT"
            print(f"  {action} {code:<14} ss={ss:<11} mw={mw:<11} li={li:<12} "
                  f"lgc={lgc:<11} human={human}", flush=True)
            if not args.apply:
                continue
            if existing:
                await c.execute(_UPDATE, JID, code, MUNI, ss, mw, li, lgc, human,
                                src, basis, cite, citations, conf, existing["id"])
            else:
                await c.execute(_INSERT, JID, code, MUNI, ss, mw, li, lgc, human,
                                src, basis, cite, citations, conf)

        if not args.apply:
            print("\nreport only — re-run with --apply", flush=True)
            return
        print(f"\napplied {len(ROWS)} rows scoped to municipality={MUNI!r}", flush=True)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
