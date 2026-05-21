"""One-shot: apply Westampton Township NJ zoning rules to its
zone_use_matrix.

Source: Ord. No. 3-2026 (adopted 4/7/2026) + Chapter 250, Articles II
and VI (§§ 250-10 through 250-21.1). Verified against the user's
correction report on 2026-05-21.

Why: Westampton (Burlington County, NJ) just had its first deal-pad in
the B-1 zone. The zone_use_matrix had every zone null. Ord. 3-2026
adds Self-Storage as a permitted use in B-1 only — all other zones
are silent on self-storage / mini-warehouse / garage condos under
Westampton's closed-list permitted-uses convention.

Westampton is its own jurisdiction (fd74c349-1f6d-4941-9ce6-8b2002102303),
not a municipality scope of a county-row, so all rows are written with
municipality=None.

Idempotent: POST first, fall through to PATCH on 409. Re-run safe.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
WESTAMPTON_ID = "fd74c349-1f6d-4941-9ce6-8b2002102303"

CITATION = (
    "Westampton Township NJ. Source: Ord. No. 3-2026 (adopted "
    "4/7/2026) + Ch. 250 §§ 250-10..250-21.1. Verified 2026-05-21. "
    "Closed-list permitted-uses: any use not expressly listed is "
    "prohibited. Ord. 3-2026 WHEREAS confirms self-storage is "
    "B-1-only."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
#
# Residential zones (R-1 through R-9) — all closed-list residential
# zones with no storage / warehouse / industrial / garage-condo uses
# permitted. R-7/R-8/R-9 explicitly state "Conditional uses permitted:
# none." R-6 includes the Ord. 3-2026 rezone of B-106 lots 22-23 from
# B-1 to R-6 to remove commercial uses.
UPDATES = [
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-10 R-1 — one-family dwellings + farms only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-11 R-2 — one-family dwellings only. No storage uses listed."),
    ("R-3", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-12 R-3 — detached/multifamily dwellings only. No storage uses listed."),
    ("R-4", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-12 R-4 — detached/multifamily dwellings only. No storage uses listed."),
    ("R-5", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-13 R-5 — dwellings, schools, parks, gov't offices, golf courses, cemeteries. No storage/industrial uses."),
    ("R-6", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14 R-6 — one-family dwellings only. Ord. 3-2026 rezones B-106 Lots 22-23 from B-1 to R-6 to remove commercial uses."),
    ("R-7", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.1.D R-7 — 'Conditional uses permitted: none.' Age-restricted/attached residential only."),
    ("R-8", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.2.D R-8 — 'Conditional uses permitted: none.' Non-age-restricted attached affordable dwellings only."),
    ("R-9", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-14.3.D R-9 — 'Conditional uses permitted: none.' Townhouses + multifamily rental apartments only."),

    # B-1 — the only zone where self-storage is permitted, per Ord. 3-2026.
    # Light industry is already permitted under § 250-15.A(7). Mini-warehouse
    # falls under the § 250-4.B self-storage definition (separately secured
    # compartments for personal/household/commercial goods).
    ("B-1", "permitted", "permitted", "permitted", "prohibited",
     "Ord. 3-2026 adds § 250-15.A(19) 'Self-storage facilities' as permitted in B-1 (parking std § 250-15.F(8)). § 250-15.A(7) 'Light industry' permitted. Mini-warehouse covered by § 250-4.B self-storage definition. Garage condominiums not listed."),

    # C (Commercial) — retail/service uses only; no storage or industrial.
    ("C", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-16 C — retail/service uses only. No storage/warehouse/industrial/garage-condo uses listed."),

    # MCD — Medical/healthcare overlay; tightly scoped.
    ("MCD", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-16.1 MCD — medical/healthcare uses only. No storage/industrial/garage-condo uses."),

    # OR-1 / OR-2 — Office/Research; offices + labs + child-care + ag +
    # public buildings. No storage, no warehouse, no industrial.
    ("OR-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-17 OR-1 — offices/labs/data centers/banks/conference/medical-dental/child-care/ag/public uses only. No storage/warehouse/industrial/garage-condo uses listed."),
    ("OR-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "§ 250-18 OR-2 — offices/labs/data centers/banks/medical-dental/child-care/ag/public uses only. No storage/warehouse/industrial/garage-condo uses listed."),

    # OR-3 — Flex space: § 250-19.A(1) allows light industry as part of
    # flex space (with ≤40K sf warehouse) and inherits all OR-2 uses.
    # Warehouse uses are conditional only and explicitly distribution /
    # fulfillment / parcel hub — not mini-warehouse / self-storage.
    ("OR-3", "prohibited", "prohibited", "permitted", "prohibited",
     "§ 250-19 OR-3 — flex space (≤40K sf warehouse) + light industry permitted (A(1)). Warehouse uses (dist/fulfillment/parcel hub) are conditional, not self-storage or mini-warehouse. Self-storage per Ord. 3-2026 is B-1-only."),

    # I (Industrial) — § 250-20.A(4) explicitly permits Light industry.
    # Self-storage / mini-warehouse not listed and Ord. 3-2026 confirms
    # B-1 only. Warehouse distribution/fulfillment/parcel hub are
    # conditional (§ 250-20.C) but those are distinct uses from
    # self-storage / mini-warehouse.
    ("I", "prohibited", "prohibited", "permitted", "prohibited",
     "§ 250-20 I — light industry permitted (A(4)). Warehouse uses (dist/fulfillment/parcel hub) conditional only, not self-storage/mini-warehouse. Ord. 3-2026 confirms self-storage is B-1-only. Garage condominiums not listed."),
]


def main() -> int:
    failures = 0
    for zone, ss, mw, li, lgc, detail in UPDATES:
        create_payload = {
            "zone_code": zone,
            "self_storage": ss,
            "mini_warehouse": mw,
            "light_industrial": li,
            "luxury_garage_condo": lgc,
            "classification_source": "human",
            "confidence": 0.95,
        }
        create_url = f"{BASE}/jurisdictions/{WESTAMPTON_ID}/zones"
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
        # quote() with safe="" so any '/' in codes is encoded.
        patch_url = (
            f"{BASE}/jurisdictions/{WESTAMPTON_ID}/zones/{quote(zone, safe='')}"
        )
        resp = requests.patch(patch_url, json=patch_payload, timeout=30)
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
