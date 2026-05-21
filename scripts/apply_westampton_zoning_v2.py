"""Apply Westampton Township zoning matrix at the CORRECT scope.

v2 vs v1: v1 applied the matrix at jurisdiction fd74c349... — an
orphan Westampton jurisdiction with 16 stub parcels and 0 zoning
districts. Real Westampton parcels live inside Burlington County's
jurisdiction (d316fb43...) — so the v1 rows could never match any
actual parcel.

This script writes municipality-scoped rows on the Burlington
jurisdiction, mirroring the Bedminster-on-Somerset pattern. The
municipality value matches TIGER MCD NAME ('Westampton township',
lowercase 't') so it joins parcels.city populated by the
admin/_backfill-nj-parcel-city job.

Idempotent: POST first, fall through to PATCH on 409.

Companion: scripts/delete_westampton_orphan_matrix.py should be run
after this to soft-delete the 16 orphan rows under fd74c349.

Once Westampton zoning polygons are ingested (PDF -> shapefile ->
_upload-zoning) and the spatial-join populates parcels.zoning_code,
these matrix rows will resolve real per-parcel storage_permission
values for Westampton parcels.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
BURLINGTON_ID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"
MUNICIPALITY = "Westampton township"  # matches TIGER MCD NAME

CITATION = (
    "Westampton Township NJ (Burlington Co.). Source: Ord. No. 3-2026 "
    "(adopted 4/7/2026) + Ch. 250 §§ 250-10..250-21.1 (ecode360.com/"
    "8751721). Verified 2026-05-21. Closed-list permitted-uses: any "
    "use not expressly listed is prohibited. Ord. 3-2026 WHEREAS "
    "confirms self-storage is B-1-only."
)

# Same 16 zones as v1, same evidence. Only the (jurisdiction_id,
# municipality) scope is different.
UPDATES = [
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-10 R-1 -- one-family dwellings + farms only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-11 R-2 -- one-family dwellings only. No storage uses listed."),
    ("R-3", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-12 R-3 -- detached/multifamily dwellings only. No storage uses listed."),
    ("R-4", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-12 R-4 -- detached/multifamily dwellings only. No storage uses listed."),
    ("R-5", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-13 R-5 -- dwellings, schools, parks, gov't offices, golf courses, cemeteries. No storage/industrial uses."),
    ("R-6", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14 R-6 -- one-family dwellings only. Ord. 3-2026 rezones B-106 Lots 22-23 from B-1 to R-6 to remove commercial uses."),
    ("R-7", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.1.D R-7 -- 'Conditional uses permitted: none.' Age-restricted/attached residential only."),
    ("R-8", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.2.D R-8 -- 'Conditional uses permitted: none.' Non-age-restricted attached affordable dwellings only."),
    ("R-9", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.3.D R-9 -- 'Conditional uses permitted: none.' Townhouses + multifamily rental apartments only."),
    ("B-1", "permitted", "permitted", "permitted", "prohibited",
     "Ord. 3-2026 adds § 250-15.A(19) 'Self-storage facilities' as permitted in B-1 (parking std § 250-15.F(8)). § 250-15.A(7) 'Light industry' permitted. Mini-warehouse covered by § 250-4.B self-storage definition. Garage condominiums not listed."),
    ("C", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-16 C -- retail/service uses only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("MCD", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-16.1 MCD -- medical/healthcare uses only. No storage/industrial/garage-condo uses."),
    ("OR-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-17 OR-1 -- offices/labs/data centers/banks/conference/medical-dental/child-care/ag/public uses only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("OR-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-18 OR-2 -- offices/labs/data centers/banks/medical-dental/child-care/ag/public uses only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("OR-3", "prohibited", "prohibited", "permitted", "prohibited",
     "§ 250-19 OR-3 -- flex space (<=40K sf warehouse) + light industry permitted (A(1)). Warehouse uses (dist/fulfillment/parcel hub) are conditional, not self-storage or mini-warehouse. Self-storage per Ord. 3-2026 is B-1-only."),
    ("I", "prohibited", "prohibited", "permitted", "prohibited",
     "§ 250-20 I -- light industry permitted (A(4)). Warehouse uses (dist/fulfillment/parcel hub) conditional only, not self-storage/mini-warehouse. Ord. 3-2026 confirms self-storage is B-1-only. Garage condominiums not listed."),
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
        create_url = f"{BASE}/jurisdictions/{BURLINGTON_ID}/zones"
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
        patch_url = (
            f"{BASE}/jurisdictions/{BURLINGTON_ID}/zones/{quote(zone, safe='')}"
        )
        resp = requests.patch(
            patch_url,
            json=patch_payload,
            params={"municipality": MUNICIPALITY},
            timeout=30,
        )
        if not resp.ok:
            print(f"{zone:6s} PATCH {resp.status_code} FAIL -- {resp.text[:200]}")
            failures += 1
        else:
            print(f"{zone:6s} PATCH {resp.status_code} OK")
    print()
    print(f"Done. {len(UPDATES) - failures}/{len(UPDATES)} successful.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
