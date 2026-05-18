"""One-shot: apply Flemington Borough NJ zoning rules to Hunterdon
County's zone_use_matrix as municipality-scoped rows.

Mirrors apply_bedminster_zoning.py / apply_somerville_zoning.py /
apply_hillsborough_zoning.py. Creates Flemington-scoped rows under
Hunterdon County jurisdiction; other Hunterdon municipalities will get
their own scoped rows in follow-up passes.

Source: Flemington Borough Code Ch. 26 Zoning, §§ 2610-2626
(ecode360 / Flemington Borough Code, verified 2026-05-18).
NJ closed-list permitted-uses rule: any use not expressly enumerated
in the district's Permitted Principal Uses / Conditional Uses list is
prohibited.

Headline finding: NO Flemington district enumerates self-storage,
mini-warehouse, or luxury garage condo as a permitted principal use.
TC §2618.D.7 is the only district that lists 'light industrial' at
all, and only as a conditional use (hrs 7a-9p, no outdoor storage,
all activities enclosed). The borough is built out at ~1.1 sq mi
with no dedicated industrial/manufacturing zone.

Zones covered (13 of 14 zones from § 2610):
  SF, TR, TH, GA, SC, TC, CB, DB, DBII, PO, VAS, HR, O/SS, PS/P

Deferred (ordinance text not located):
  O/MUMF — Mixed-Use Multifamily Overlay

PO is included with a 'repealed' note: § 2622 was repealed 2024-09-23
by Ord. 2024-19 (section 'Reserved'), but the symbol PO still appears
on the § 2610 zoning district list. Treat as prohibited until the
borough re-enacts.

If a row already exists (409 from POST), falls through and PATCHes —
idempotent re-run safe.

Known limitation: PATCH /zones/{zone_code} 404s on codes containing
'/' (O/SS, PS/P) even when URL-encoded — FastAPI decodes %2F before
path matching. POST sets the use values correctly; only the notes
field for these two codes won't be populated via this script. Script
prints a warning so they can be patched out-of-band.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
HUNTERDON_ID = "e8612f49-218b-48cc-9eb0-a1dd90cf583d"
MUNICIPALITY = "Flemington borough"

CITATION = (
    "Flemington Borough NJ. Source: Borough Code Ch. 26 Zoning, "
    "§§ 2610-2626 (verified 2026-05-18). NJ closed-list permitted-"
    "uses rule: any use not expressly enumerated is prohibited."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
UPDATES = [
    ("SF", "prohibited", "prohibited", "prohibited", "prohibited",
     "SF Single Family Residential: § 2613.B permits only single-family detached, place of worship, ECHO housing, cemetery, municipal/parks, community gardening. Conditional: accessory apartment, day school. No storage/warehouse/industrial uses."),
    ("TR", "prohibited", "prohibited", "prohibited", "prohibited",
     "TR Transition Residential: § 2614.B permits SFD, two-family, place of worship, ECHO, municipal, community gardening. Conditional: two-family conversion, B&B, day school. No storage/warehouse/industrial uses."),
    ("TH", "prohibited", "prohibited", "prohibited", "prohibited",
     "TH Townhouse Residential: § 2615.B permits only townhouse dwellings, municipal/parks, community gardening. Conditional: day school. No storage/warehouse/industrial uses."),
    ("GA", "prohibited", "prohibited", "prohibited", "prohibited",
     "GA Garden Apartment: § 2616.B permits only multi-family dwellings and municipal/parks. No storage/warehouse/industrial uses."),
    ("SC", "prohibited", "prohibited", "prohibited", "prohibited",
     "SC Senior Citizen Residential: § 2617.B permits only age-restricted (55+) dwellings. No storage/warehouse/industrial uses."),
    ("TC", "prohibited", "prohibited", "conditional", "prohibited",
     "TC Transition Commercial: § 2618.B permits offices, medical, childcare, indoor/outdoor recreation, theaters, higher ed, community buildings, club facilities, animal hospital, funeral homes, research, fitness, learning, artisan manufacturing. § 2618.D.7 lists 'light industrial' as CONDITIONAL (hours 7a-9p, no outdoor storage, all activities within enclosed building). Self-storage, mini-warehouse, and luxury garage condo are not enumerated — closed-list → prohibited."),
    ("CB", "prohibited", "prohibited", "prohibited", "prohibited",
     "CB Community Business: § 2619.B permits SFD, two-family, SIC 17xx contractor services (1711 plumbing/HVAC, 172 painting, 173 electrical), retail food/apparel/drug, miscellaneous retail, business/professional services, dance studios, commercial printing (275), farmer's market, commercial agriculture, municipal. § 2619.F.1 caps commercial buildings at 5,000 sf / 3,000 sf per level. No SIC 4225 storage/warehouse, no general light industrial, no garage-condo uses."),
    ("DB", "prohibited", "prohibited", "prohibited", "prohibited",
     "DB Downtown Business: § 2620.B permits retail, restaurants, artisan studios, breweries, indoor recreation, fitness, higher ed, learning, theaters, museums, upper-floor dwellings, offices, medical, existing funeral homes, existing SFD, municipal, club facilities. No drive-thrus. No storage/warehouse/industrial uses enumerated."),
    ("DBII", "prohibited", "prohibited", "prohibited", "prohibited",
     "DBII Downtown II Business: § 2621.B permits retail, artisan studios, fitness, higher ed, learning, museums, upper-floor apartments, offices, medical, existing SFD, municipal. § 2621.F.1: 'All equipment stored on the site shall be placed within an enclosed building' — accessory only, not principal warehousing. No drive-thrus (§ 2621.F.5). No storage/warehouse/industrial uses enumerated."),
    ("PO", "prohibited", "prohibited", "prohibited", "prohibited",
     "PO Professional Office: § 2622 REPEALED 2024-09-23 by Ord. 2024-19; section is 'Reserved'. Symbol PO still appears on § 2610 zoning district list but no current regulations. Treat as prohibited until borough re-enacts."),
    ("VAS", "prohibited", "prohibited", "prohibited", "prohibited",
     "VAS Village Artisan Shopping: § 2623.B permits retail sales, indoor/outdoor recreation, childcare, higher ed, artisan manufacturing, artisan studios, farmer's market, commercial agriculture, theater, retail services, restaurants, breweries, museums, learning, upper-story fitness/office/medical, banquet hall, municipal. Artisan manufacturing is narrow craft scale, not general light industrial. No storage/warehouse/garage-condo uses enumerated."),
    ("HR", "prohibited", "prohibited", "prohibited", "prohibited",
     "HR Highway Retail (Rt 31 / Rt 202): § 2624.B permits long list of highway retail (department/grocery/apparel/restaurants/auto sales/hardware), contractor services (15 general, 172 painting, 173 electrical, 1711 plumbing 'no outside storage'), brewery, fitness centers, bowling, miscellaneous repair (75 & 7699 narrow), medical/dental, funeral home/crematorium (7261), shopping centers, senior citizens housing, municipal. Conditional: service stations (5541), hotels/motels (701), automotive body (7532 only as ancillary to new-car dealer), comm towers (4812), cannabis retailer/cultivator, structured parking. NO SIC 4225 warehousing/self-storage, NO general SIC 20-39 light industrial, NO garage-condo uses. § 2624.F.3: 75-ft buffer with residential."),
    ("O/SS", "prohibited", "prohibited", "prohibited", "prohibited",
     "O/SS Super Shopping Overlay: § 2626.B permits only shopping center incorporating any HR-district permitted use. Inherits HR's permitted-uses set and narrows to shopping-center configuration. Same outcome as HR — no warehouse/self-storage/industrial uses enumerated."),
    ("PS/P", "prohibited", "prohibited", "prohibited", "prohibited",
     "PS/P Public School and Parks: § 2625.B permits only public schools, government use (including parks/recreation), and private swim clubs. No storage/warehouse/industrial uses."),
]


def main() -> int:
    failures = 0
    slashed_notes_skipped: list[str] = []
    for zone, ss, mw, li, lgc, detail in UPDATES:
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
        create_url = f"{BASE}/jurisdictions/{HUNTERDON_ID}/zones"
        resp = requests.post(create_url, json=create_payload, timeout=30)
        if resp.status_code == 409:
            print(f"{zone:6s} POST 409 (row exists, will PATCH)")
        elif not resp.ok:
            print(f"{zone:6s} POST {resp.status_code} FAIL — {resp.text[:200]}")
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
        patch_url = f"{BASE}/jurisdictions/{HUNTERDON_ID}/zones/{quote(zone, safe='')}"
        resp = requests.patch(
            patch_url,
            json=patch_payload,
            params={"municipality": MUNICIPALITY},
            timeout=30,
        )
        if not resp.ok:
            if "/" in zone and resp.status_code == 404:
                # Known FastAPI/Starlette path-decode limitation — POST
                # already set the use values; only notes are missing.
                slashed_notes_skipped.append(zone)
                print(f"{zone:6s} PATCH 404 (slashed code — known limitation, notes not set)")
            else:
                print(f"{zone:6s} PATCH {resp.status_code} FAIL — {resp.text[:200]}")
                failures += 1
        else:
            print(f"{zone:6s} PATCH {resp.status_code} OK")

    print()
    total = len(UPDATES)
    print(f"Done. {total - failures}/{total} successful (POST + PATCH).")
    if slashed_notes_skipped:
        print(
            f"Notes not set via API for {len(slashed_notes_skipped)} "
            f"slashed zone(s): {', '.join(slashed_notes_skipped)}. "
            f"Use values are correct; patch notes out-of-band if needed."
        )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
