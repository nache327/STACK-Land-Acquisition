"""One-shot: apply Mine Hill Township NJ zoning rules to Morris County's
zone_use_matrix.

Two passes:

  1. SQL DELETE on 13 NULL-municipality (county-default) rows under
     Morris County that hold zone codes verified absent from every
     Morris municipality's ordinance (parser-generated noise from an
     earlier bootstrap):
       B-1, B-2, B-2ENV, B-3, B-4, I-1, I-2, LVC, OS/GU, R/PO,
       SS/VO, VCC, VMU
     Per user audit, none of these codes exist in any Morris
     township's ordinance — the rows are pure noise. Hard-delete is
     surgical to Morris jurisdiction only.

  2. POST + PATCH municipality-scoped ADD pass for Mine Hill
     Township's 11 real zones from Article XXIII of Mine Hill
     Code Ch. 310 (ecode360.com/28591199, verified 2025):
       SF, TH, TH-1, RAH, RAH-2, O/I, ED, C, PMARC, MLO, AOZ

Headline finding: ED (Economic Development) is the ONLY Mine Hill
zone that permits self-storage and mini-warehouse by right.
§ 310-171 A(4) explicitly lists "mini warehouses/self-storage
facilities" as principal permitted uses. O/I permits light
industrial / light warehousing but NOT self-storage. Every other
Mine Hill zone is residential, commercial-retail, or overlay and
prohibits the target uses.

AOZ is an OVERLAY zone — § 310-175 says permitted/conditional uses
inherit from the underlying zone. Recorded as 'unclear' for all
four targets with a citation note explaining the overlay
dependency, so parcels tagged only AOZ don't misclassify.

If a row already exists (409 from POST), falls through and
PATCHes — idempotent re-run safe.
"""
import sys
from urllib.parse import quote

import asyncpg
import asyncio
import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
MORRIS_ID = "746b7604-f362-470f-aa42-70dc8973b4ee"
MUNICIPALITY = "Mine Hill township"

# Direct-SQL DSN for the DELETE pass (no API endpoint exposes row delete).
DSN = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

DELETE_ZONES = [
    "B-1", "B-2", "B-2ENV", "B-3", "B-4",
    "I-1", "I-2",
    "LVC", "OS/GU", "R/PO", "SS/VO", "VCC", "VMU",
]

CITATION = (
    "Mine Hill Township NJ. Source: Township Code Ch. 310 Zoning, "
    "Article XXIII §§ 310-166 to 310-175 (ecode360.com/28591199, "
    "verified 2025). NJ closed-list permitted-uses rule: any use "
    "not expressly enumerated is prohibited."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
ADD_UPDATES = [
    ("SF", "prohibited", "prohibited", "prohibited", "prohibited",
     "SF Single-Family District (§ 310-166): permitted principal use is single-family dwellings only. None of the four target uses are listed."),
    ("TH", "prohibited", "prohibited", "prohibited", "prohibited",
     "TH Residential Townhouse District (§ 310-167): permitted principal uses are single-family dwellings and townhouses only. None of the four target uses are listed."),
    ("TH-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "TH-1 Residential Townhouse District (§ 310-168): permitted principal uses are single-family dwellings and townhouses only. None of the four target uses are listed."),
    ("RAH", "prohibited", "prohibited", "prohibited", "prohibited",
     "RAH Residential Affordable Housing Zone (§ 310-169): permitted uses are senior citizen housing and townhouses for low/moderate income families only. None of the four target uses are listed."),
    ("RAH-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "RAH-2 District (§ 310-169.1): permitted principal use is apartment units only. None of the four target uses are listed."),
    ("O/I", "prohibited", "prohibited", "permitted", "prohibited",
     "O/I Office/Industrial Zone (§ 310-170): permitted principal uses include manufacturing (enclosed buildings, A(1)) and light warehousing (A(3)) — light_industrial PERMITTED. Self-storage, mini-warehouse, and luxury garage condo are NOT enumerated."),
    ("ED", "permitted", "permitted", "permitted", "prohibited",
     "ED Economic Development District (§ 310-171): A(4) explicitly lists 'mini warehouses/self-storage facilities' as principal permitted uses. Same subsection permits warehousing, distribution, manufacturing (enclosed), assembly, light industrial. Luxury garage condo NOT enumerated. ED is the only Mine Hill zone that permits self_storage / mini_warehouse by right."),
    ("C", "prohibited", "prohibited", "prohibited", "prohibited",
     "C Commercial Zone (§ 310-172): permitted principal uses are retail goods/services, furniture/appliances, professional offices, banks, funeral homes, indoor theaters, laundromats, dry-cleaning, printing/publishing shops, general office, schools. Printing/publishing is narrow and does not extend to general light industrial. None of the four target uses are listed."),
    ("PMARC", "prohibited", "prohibited", "prohibited", "prohibited",
     "PMARC Planned Multifamily Age-Restricted Community District (§ 310-173): permitted uses are age-restricted residential dwellings, public parks/recreation, and government buildings/schools only. None of the four target uses are listed."),
    ("MLO", "prohibited", "prohibited", "prohibited", "prohibited",
     "MLO Previously Mined Land Overlay District (§ 310-174): permitted uses are temporary nonprofit fund-raising events on specifically listed Block/Lot properties. None of the four target uses are listed."),
    ("AOZ", "unclear", "unclear", "unclear", "unclear",
     "AOZ Agricultural Overlay Zone (§ 310-175): an OVERLAY zone that permits commercial farms PLUS any principal permitted use in the underlying zone. Stance on the four target uses depends entirely on the underlying zone (O/I, ED, etc.) — recorded as 'unclear' to signal the inheritance, parcels should be classified by their underlying zone code, not by AOZ alone."),
]


async def run_deletes() -> int:
    """Delete the 13 NULL-municipality bogus rows. Idempotent."""
    c = await asyncpg.connect(DSN)
    try:
        preview = await c.fetch(
            """SELECT zone_code FROM zone_use_matrix
               WHERE jurisdiction_id = $1::uuid
                 AND municipality IS NULL
                 AND zone_code = ANY($2::text[])
               ORDER BY zone_code""",
            MORRIS_ID, DELETE_ZONES,
        )
        existing = [r["zone_code"] for r in preview]
        print(f"DELETE pass — {len(existing)} of {len(DELETE_ZONES)} bogus rows currently present: {existing}")
        if not existing:
            print("  (nothing to delete; script already applied?)")
            return 0
        res = await c.execute(
            """DELETE FROM zone_use_matrix
               WHERE jurisdiction_id = $1::uuid
                 AND municipality IS NULL
                 AND zone_code = ANY($2::text[])""",
            MORRIS_ID, DELETE_ZONES,
        )
        print(f"  {res}")
        return len(existing)
    finally:
        await c.close()


def run_adds() -> int:
    """POST + PATCH municipality-scoped rows for Mine Hill's real zones."""
    failures = 0
    slashed_notes_skipped: list[str] = []
    for zone, ss, mw, li, lgc, detail in ADD_UPDATES:
        create_payload = {
            "zone_code": zone,
            "municipality": MUNICIPALITY,
            "self_storage": ss,
            "mini_warehouse": mw,
            "light_industrial": li,
            "luxury_garage_condo": lgc,
            "classification_source": "human",
            "confidence": 0.95,
        }
        create_url = f"{BASE}/jurisdictions/{MORRIS_ID}/zones"
        resp = requests.post(create_url, json=create_payload, timeout=30)
        if resp.status_code == 409:
            print(f"{zone:6s} POST 409 (row exists, will PATCH)")
        elif not resp.ok:
            print(f"{zone:6s} POST {resp.status_code} FAIL -- {resp.text[:200]}")
            failures += 1
            continue
        else:
            print(f"{zone:6s} POST {resp.status_code} OK")

        patch_payload = {
            "self_storage": ss,
            "mini_warehouse": mw,
            "light_industrial": li,
            "luxury_garage_condo": lgc,
            "notes": f"{CITATION} {detail}",
        }
        patch_url = f"{BASE}/jurisdictions/{MORRIS_ID}/zones/{quote(zone, safe='')}"
        resp = requests.patch(
            patch_url, json=patch_payload,
            params={"municipality": MUNICIPALITY}, timeout=30,
        )
        if not resp.ok:
            if "/" in zone and resp.status_code == 404:
                slashed_notes_skipped.append(zone)
                print(f"{zone:6s} PATCH 404 (slashed code -- known limitation, notes not set)")
            else:
                print(f"{zone:6s} PATCH {resp.status_code} FAIL -- {resp.text[:200]}")
                failures += 1
        else:
            print(f"{zone:6s} PATCH {resp.status_code} OK")

    total = len(ADD_UPDATES)
    print(f"\nADD pass: {total - failures}/{total} successful.")
    if slashed_notes_skipped:
        print(
            f"Notes not set via API for {len(slashed_notes_skipped)} slashed "
            f"zone(s): {', '.join(slashed_notes_skipped)}. "
            f"Patch notes out-of-band if needed."
        )
    return failures


async def main_async() -> int:
    deleted = await run_deletes()
    print(f"\n--- DELETE pass complete ({deleted} rows removed) ---\n")
    fails = run_adds()
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
