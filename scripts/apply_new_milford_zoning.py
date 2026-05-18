"""One-shot: apply New Milford Borough NJ zoning rules to Bergen County
NJ's zone_use_matrix as municipality-scoped rows.

Mirrors apply_bedminster_zoning.py / apply_hillsborough_zoning.py.
Creates Bergen-jurisdiction rows scoped to municipality='New Milford
borough' so they override the (NULL-municipality) county default for
NM parcels only — other Bergen towns are unaffected.

Source: Borough of New Milford NJ, Code Chapter 30 (Zoning), Article IV
Zoning Regulations. Sourced from local PDF
zoning_sources/new_milford/Zoning Regulations.pdf (ecode360.com/NE0287).
Verified 2026-05-18.

Closed-list rule: § 30-20.6 — "Any use not specifically permitted in a
zoning district established by the Zoning Chapter is hereby expressly
prohibited from that district."

Note: NM parcels in our DB currently have zoning_code = NULL across all
4,468 rows (no per-parcel zoning ingested). These matrix entries are
inert until NM zoning data lands at the parcel level. They are still
worth applying for audit trail, consistency with sister apply-scripts,
and zero rework on future NM zoning ingest.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
BERGEN_ID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"
MUNICIPALITY = "New Milford borough"

CITATION = (
    "Borough of New Milford NJ. Source: Code Ch 30, Article IV "
    "Zoning Regulations (ecode360.com/NE0287). Verified 2026-05-18. "
    "§ 30-20.6 closed-list rule: any use not expressly permitted "
    "in a zone's permitted-uses list is prohibited."
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
#
# Closed-list rule applies. Self-storage, mini-warehouse, and garage-
# condo uses are not named in ANY New Milford zone's permitted-uses
# list, so they are prohibited everywhere. Light-industrial uses
# (manufacture/fabrication/assembling/handling of products with
# performance-standard constraints) ARE listed in the LIP zone's
# §30-26.2.a.5, so light_industrial = permitted in LIP only.
UPDATES = [
    ("RA", "prohibited", "prohibited", "prohibited", "prohibited",
     "RA: §30-21.1 permitted uses are one-family dwellings, public parks, public recreation grounds. No storage/warehouse/industrial uses."),
    ("RB", "prohibited", "prohibited", "prohibited", "prohibited",
     "RB: §30-22.1 permits RA uses plus two-family dwellings, membership clubs, libraries, museums, art galleries. No storage uses."),
    ("RC", "prohibited", "prohibited", "prohibited", "prohibited",
     "RC: §30-23.1 permits low-rise and mid-rise multifamily dwellings (plus parks/schools/houses-of-worship as conditional). No storage uses."),
    ("RD", "prohibited", "prohibited", "prohibited", "prohibited",
     "RD: §30-24.2 permits only townhouses and accessory buildings. No storage uses."),
    ("RE/MFTH", "prohibited", "prohibited", "prohibited", "prohibited",
     "RE/MFTH: §30-24A.2 permits only townhomes and accessory buildings (multi-family townhome district). No storage uses."),
    ("Business", "prohibited", "prohibited", "prohibited", "prohibited",
     "Business: §30-25.1 permits retail, personal services, offices (incl. medical), banks, health clubs, restaurants (excl. drive-thru), laundry/dry cleaning, shopping centers, commercial schools, dwellings above first floor, governmental buildings. No storage/warehouse/industrial uses."),
    ("Office/Service", "prohibited", "prohibited", "prohibited", "prohibited",
     "Office/Service: §30-27.1 permits personal services, business/professional services, offices, medical offices, banks, commercial schools, governmental buildings. No storage/industrial uses."),
    ("LIP", "prohibited", "prohibited", "permitted", "prohibited",
     "LIP: §30-26.2.a permits offices, research labs, public utility offices/facilities, commercial recreation, and §30-26.2.a.5 manufacture/fabrication/assembling/'other handling of products' subject to performance standards. Light industrial = permitted; self-storage and mini-warehouse and garage-condo uses not named. §30-26.3 also explicitly prohibits all Office/Service §30-27.1 uses plus most Business §30-25 uses within LIP."),
    ("MUPUD", "prohibited", "prohibited", "prohibited", "prohibited",
     "MUPUD: §30-31.3 permits area-A public recreation/concession/restrooms/storage-sheds-for-playing-fields, area-B bank/supermarket/parking, area-C up to 135 multifamily housing units plus 12,500 sf commerce. No storage/warehouse/industrial principal uses."),
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
        create_url = f"{BASE}/jurisdictions/{BERGEN_ID}/zones"
        resp = requests.post(create_url, json=create_payload, timeout=30)
        if resp.status_code == 409:
            print(f"{zone:18s} POST 409 (row exists, will PATCH)")
        elif not resp.ok:
            print(f"{zone:18s} POST {resp.status_code} FAIL — {resp.text[:200]}")
            failures += 1
            continue
        else:
            print(f"{zone:18s} POST {resp.status_code} OK")

        patch_payload = {
            "self_storage": ss,
            "mini_warehouse": mw,
            "light_industrial": li,
            "luxury_garage_condo": lgc,
            "notes": f"{CITATION} {detail}",
        }
        # quote() with safe="" so '/' in codes like "RE/MFTH" / "Office/Service"
        # is encoded too. (Known backend limitation — FastAPI/Starlette decodes
        # %2F before path matching, so this PATCH may still 404 for slash codes.
        # If it does, the POST already created the row with correct values; the
        # notes/human_reviewed fields just won't land via API.)
        patch_url = f"{BASE}/jurisdictions/{BERGEN_ID}/zones/{quote(zone, safe='')}"
        resp = requests.patch(
            patch_url,
            json=patch_payload,
            params={"municipality": MUNICIPALITY},
            timeout=30,
        )
        if not resp.ok:
            print(f"{zone:18s} PATCH {resp.status_code} FAIL — {resp.text[:200]}")
            failures += 1
        else:
            print(f"{zone:18s} PATCH {resp.status_code} OK")

    print()
    total = len(UPDATES)
    print(f"Done. {total - failures}/{total} successful.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
