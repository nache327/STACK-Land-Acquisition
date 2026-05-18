"""One-shot: apply Bedminster Township NJ zoning rules to Somerset
County's zone_use_matrix as municipality-scoped rows.

Mirrors apply_hillsborough_zoning.py exactly. Creates Bedminster-scoped
rows that override the (NULL-municipality) county-default for Bedminster
parcels only — other Somerset townships keep the existing default.

Source: Bedminster Township Code Ch 13 Land Management, Article 13-400
District Regulations, ecode360.com/35861743 (2025-09-02 revision).
The code uses a closed-list permitted-uses rule: any use not expressly
listed in § 13-X01.1 ("Principal Permitted Uses on the Land and in
Buildings") is prohibited.

Zones covered in this pass (11 of 23 Bedminster zones):
  R-10, R-3, R-2, R-1, R-1/2, VR-100, VR-80, SFC-RD, MF, VN, VN-2

Deferred — ordinance text not yet provided / verified:
  VN-3, OR, OP, OR-1, ORVMU, OR-V, P, SFC, PRD, PUD, SCH, RDOL

If a row already exists (409 from POST), falls through and PATCHes —
idempotent re-run safe.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
SOMERSET_ID = "394ef40c-ca0d-4d57-9b11-dc5417430240"
MUNICIPALITY = "Bedminster township"

CITATION = (
    "Bedminster Township NJ. Source: Township Code Ch 13, Article "
    "13-400 District Regulations (ecode360.com/35861743, "
    "2025-09-02 revision). Verified 2026-05-18. § 13-X01.1 "
    "closed-list rule: any use not expressly permitted is prohibited."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
#
# All residential / village zones below permit only farms, dwellings,
# parks, houses of worship, schools, and a handful of conditional uses
# (boarding schools, airports, golf clubs in R-10). No storage,
# warehouse, industrial, or garage-condo uses appear in any permitted-
# uses list, so under the closed-list rule all four target uses are
# prohibited.
UPDATES = [
    ("R-10", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-10: § 13-401A.1 lists farms, dwellings, parks, houses of worship, schools, open air clubs, airports (cond.), boarding schools, golf courses (cond.), agricultural support (cond.). No storage/warehouse/industrial/garage-condo uses."),
    ("R-3", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-3: § 13-402.1 lists farms, dwellings, parks, houses of worship, schools, open air clubs, private boarding schools, PRDs, PUDs. No storage uses."),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-2: § 13-403.1 lists farms, dwellings, parks, houses of worship, schools. No storage uses."),
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-1: § 13-403.1 (shared) lists farms, dwellings, parks, houses of worship, schools. No storage uses."),
    ("R-1/2", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-1/2: § 13-403.1 (shared) lists farms, dwellings, parks, houses of worship, schools. No storage uses."),
    ("VR-100", "prohibited", "prohibited", "prohibited", "prohibited",
     "VR-100: § 13-403.1 (shared with R-2/R-1/R-1/2/VR-80) lists farms, dwellings, parks, houses of worship, schools. No storage uses listed. Was 'unclear' in DB — downgrade to prohibited."),
    ("VR-80", "prohibited", "prohibited", "prohibited", "prohibited",
     "VR-80: § 13-403.1 (shared) lists farms, dwellings, parks, houses of worship, schools. No storage uses listed. Was 'unclear' in DB — downgrade to prohibited."),
    ("SFC-RD", "prohibited", "prohibited", "prohibited", "prohibited",
     "SFC-RD: § 13-403A.1 lists ONLY detached dwelling units (Single Family Cluster - Restricted Development). No storage uses."),
    # The material correction: DB had MF as 'permitted' for all four target uses;
    # the ordinance lists only townhouses/apartments, parks, and public utility
    # (conditional). 121 condo/apartment parcels (TIMBERBROOKE DR etc.) flip
    # from candidate to excluded.
    ("MF", "prohibited", "prohibited", "prohibited", "prohibited",
     "MF: § 13-404.1 lists ONLY townhouses/apartments, public playgrounds/parks/conservation, public utility (cond.). High-density multifamily zone — no storage/warehouse/industrial/garage-condo uses. DB had 'permitted' — INCORRECT, corrected."),
    ("VN", "prohibited", "prohibited", "prohibited", "prohibited",
     "VN: § 13-405.1 lists dwellings, small grocery/markets ≤1,200 sf, local retail, local services, banks (drive-thru cond.), professional offices, restaurants, houses of worship, parks, agricultural support (cond.). § 13-405.3A caps any building at 5,000 sf. No storage/warehouse/industrial/garage-condo uses; the 5,000 sf cap alone precludes self-storage."),
    ("VN-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "VN-2: § 13-405A.1 permits dwellings, parks, houses of worship, schools; § 13-405A.3 conditional non-residential limited to boutique retail (antique shops, beauty shops, book stores, day care, fabric stores, etc.). No storage/warehouse/industrial uses."),
]


def main() -> int:
    failures = 0
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
        create_url = f"{BASE}/jurisdictions/{SOMERSET_ID}/zones"
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
        # quote() with safe="" so '/' in codes like "R-1/2" is encoded too,
        # otherwise FastAPI parses /zones/R-1/2 as /zones/R-1 + stray path.
        patch_url = f"{BASE}/jurisdictions/{SOMERSET_ID}/zones/{quote(zone, safe='')}"
        resp = requests.patch(
            patch_url,
            json=patch_payload,
            params={"municipality": MUNICIPALITY},
            timeout=30,
        )
        if not resp.ok:
            print(f"{zone:6s} PATCH {resp.status_code} FAIL — {resp.text[:200]}")
            failures += 1
        else:
            print(f"{zone:6s} PATCH {resp.status_code} OK")

    print()
    total = len(UPDATES)
    print(f"Done. {total - failures}/{total} successful.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
