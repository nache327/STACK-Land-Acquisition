"""One-shot: apply Hillsborough Township NJ zoning rules to Somerset
County's zone_use_matrix as municipality-scoped rows.

Mirrors apply_somerville_zoning.py but uses POST (new rows scoped to
``municipality='Hillsborough township'``) instead of PATCH-in-place.
Each zone:
  1. POST /api/jurisdictions/{somerset_id}/zones — creates the row
     with municipality + permission values + classification_source=human.
  2. PATCH /zones/{zone_code}?municipality=... — adds the citation
     notes (also auto-stamps human_reviewed=True).

If a row already exists (409 from POST), falls through and just PATCHes
to refresh the values + notes — idempotent re-run safe.
"""
import json
import sys

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
SOMERSET_ID = "394ef40c-ca0d-4d57-9b11-dc5417430240"
MUNICIPALITY = "Hillsborough township"

CITATION = (
    "Hillsborough Township NJ. Source: Land Development Ordinance "
    "Chapter 188, §§ 188-97 through 188-110. Verified 2025-01-22. "
    "§ 188-97A closed-list: any use not expressly permitted is prohibited."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
UPDATES = [
    ("I-1", "permitted", "permitted", "permitted", "prohibited",
     "I-1: § 188-106B(13) small scale storage and distribution permitted; § 188-106B(3),(14) manufacturing/assembly permitted; garage condos not listed."),
    ("I-2", "permitted", "permitted", "permitted", "prohibited",
     "I-2: § 188-106B(13) small scale storage and distribution permitted; § 188-106B(3),(14) manufacturing/assembly permitted; garage condos not listed."),
    ("LI", "conditional", "conditional", "permitted", "prohibited",
     "LI: § 188-107.1D(6) self-service storage facilities = conditional; § 188-107.1B(8) manufacturing/processing/assembly permitted; garage condos not listed."),
    ("GI", "prohibited", "prohibited", "permitted", "prohibited",
     "GI: § 188-107B no storage use (warehousing repealed by Ord. 2023-08); § 188-107B(4) manufacturing/finishing/assembly permitted; mini-warehouse and garage condos not listed."),
    ("TECD", "prohibited", "prohibited", "permitted", "prohibited",
     "TECD: § 188-107.2B no storage use (warehousing repealed by Ord. 2023-04); § 188-107.2B(6) manufacturing/processing/assembly permitted; mini-warehouse and garage condos not listed."),
    ("MZ", "prohibited", "prohibited", "prohibited", "prohibited",
     "MZ: § 188-99.4B permits only single-family homes, parks, fire stations, municipal facilities. All storage/industrial uses prohibited by closed-list rule."),
    ("MVH", "prohibited", "prohibited", "prohibited", "prohibited",
     "MVH: § 188-99.5B permits only parks, open space, conservation, public schools, municipal/historic district uses. All storage/industrial uses prohibited."),
    ("M", "prohibited", "prohibited", "permitted", "prohibited",
     "M: § 188-108B mining/processing + GI District uses (manufacturing permitted via GI § 188-107B(4)); GI does not permit storage so M doesn't either."),
    ("Q", "prohibited", "prohibited", "permitted", "prohibited",
     "Q: § 188-108B quarrying/processing + GI District uses (manufacturing permitted via GI § 188-107B(4)); GI does not permit storage so Q doesn't either. NOTE: Q zone may not be current per the township's active ordinance — verify before relying."),
]


def main() -> int:
    failures = 0
    for zone, ss, mw, li, lgc, detail in UPDATES:
        # 1. Try to create the municipality-scoped row.
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
            # Row already exists — fall through to PATCH for value refresh.
            print(f"{zone:5s} POST 409 (row exists, will PATCH)")
        elif not resp.ok:
            print(f"{zone:5s} POST {resp.status_code} FAIL — {resp.text[:200]}")
            failures += 1
            continue
        else:
            print(f"{zone:5s} POST {resp.status_code} OK")

        # 2. PATCH to update values (idempotent) + add notes.
        patch_payload = {
            "self_storage": ss,
            "mini_warehouse": mw,
            "light_industrial": li,
            "luxury_garage_condo": lgc,
            "notes": f"{CITATION} {detail}",
        }
        patch_url = f"{BASE}/jurisdictions/{SOMERSET_ID}/zones/{zone}"
        resp = requests.patch(
            patch_url,
            json=patch_payload,
            params={"municipality": MUNICIPALITY},
            timeout=30,
        )
        if not resp.ok:
            print(f"{zone:5s} PATCH {resp.status_code} FAIL — {resp.text[:200]}")
            failures += 1
        else:
            print(f"{zone:5s} PATCH {resp.status_code} OK")

    print()
    total = len(UPDATES)
    print(f"Done. {total - failures}/{total} successful.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
