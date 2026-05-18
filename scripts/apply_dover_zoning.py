"""One-shot: apply Dover Town NJ zoning rules to Morris County's
zone_use_matrix as municipality-scoped rows.

Mirrors apply_mine_hill_zoning.py / apply_bedminster_zoning.py /
apply_flemington_zoning.py pattern. Pure ADD pass — no DELETEs
this time; no existing Morris county-default rows collide with
Dover's zone codes.

Source: Dover Town Code Ch. 236 Zoning (ecode360.com/10031294,
verified 2025). § 236-15(B) closed-list rule: "All uses not
expressly permitted in this chapter are prohibited uses."

Zones covered (14 of 20 on the Dover zoning map):
  R-1, R-1S, R-2, R-3, R-4   — residential
  C-1, C-2, C-3              — commercial / light-industrial-commercial
  D1, D2, D3, D4             — downtown form-based districts
  IND, IND/OP                — industrial

Headline: IND district (§ 236-20) is the only Dover zone that
permits self-storage and mini-warehouse by right — A(3) principal
uses include "warehouses, wholesale distribution centers… and other
warehouses". C-3 and IND/OP permit light_industrial but lock
self-storage out (warehousing is accessory-only with a 40% cap).
C-2 differs from C-3 in that it omits "Light manufacturing" from
its principal-uses list, so C-2 prohibits even light_industrial.
Every residential and downtown district prohibits all four target
uses under the § 236-15(B) closed-list rule.

D4 mini_warehouse/light_industrial/luxury_garage_condo recorded as
prohibited per user confirmation — D4 § 236-17.1D(4)(h) permitted
building types are liner, courtyard, multifamily, corner,
townhouse, civic, commercial block (no warehouse / industrial /
garage-condo building types).

Deferred (ordinance text not yet provided):
  R-3A (Double Family / Rooming House),
  RAD, BHRPA, SSRA, GMRA, P-1 RA (5 redevelopment-area overlays).

Idempotent: POST returns 409 on existing rows; PATCH then updates.
"""
import sys
from urllib.parse import quote

import requests

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
MORRIS_ID = "746b7604-f362-470f-aa42-70dc8973b4ee"
MUNICIPALITY = "Dover town"

CITATION = (
    "Dover Town NJ. Source: Town Code Ch. 236 Zoning "
    "(ecode360.com/10031294, verified 2025). § 236-15(B) closed-"
    "list rule: 'All uses not expressly permitted in this chapter "
    "are prohibited uses.'"
)

# (zone, self_storage, mini_warehouse, light_industrial, luxury_garage_condo, detail)
UPDATES = [
    ("R-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-1 (§ 236-15 et seq.): principal uses are single-family dwellings, parish houses/rectories, senior rooming units, community residences. Private garages and household-effects storage permitted only as accessory to a dwelling. No storage, warehouse, or industrial uses listed."),
    ("R-1S", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-1S Steep Slope Single-Family (§ 236-21.1): principal uses are single-family dwelling, boarding/rooming houses for not more than two roomers, and community residences for ≤6 persons. Accessory only: home occupations, private garages, swimming pools. Density capped at 1.5 units/acre to protect steep slopes. No storage, warehouse, or industrial uses listed."),
    ("R-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-2 (§ 236-15 et seq.): shares R-1's principal-uses list — single-family residential only. No storage, warehouse, or industrial uses listed."),
    ("R-3", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-3 (§ 236-17): principal uses are single-family, two-family, duplex, and funeral homes. No storage, warehouse, or industrial uses listed."),
    ("R-4", "prohibited", "prohibited", "prohibited", "prohibited",
     "R-4: principal uses are two-family/duplex dwellings, garden apartments, funeral homes, public/private parking lots and garages, community residences. Parking garages permit vehicle parking only — not garage condominium ownership/storage units. No mini-warehouse / self-storage / general light-industrial uses listed."),
    ("C-1", "prohibited", "prohibited", "prohibited", "prohibited",
     "C-1 Central Commercial: principal uses are retail, offices, banks, restaurants, hotels, high-rise apartments, automobile parking lots and parking garages. No self-storage, mini-storage, warehousing, storage facilities, or general industrial uses listed. Parking garages are for vehicle parking, not garage condominium use type."),
    ("C-2", "prohibited", "prohibited", "prohibited", "prohibited",
     "C-2 General Commercial (§ 236-18): principal uses are motor vehicle repair garages, tire/auto parts sales, hardware stores, retail lumberyards (storage/sale/minor milling of materials sold), motor vehicle service stations, bars/restaurants, electronic stores, funeral homes, hotels/motels, offices. UNLIKE C-3, light manufacturing is NOT in the C-2 principal-uses list — light_industrial prohibited. No self-storage, mini-warehouse, or garage-condo uses listed."),
    ("C-3", "prohibited", "prohibited", "permitted", "prohibited",
     "C-3 Light Industrial-Commercial (§ 236-19): A(12) explicitly lists 'Light manufacturing' as a principal use — light_industrial PERMITTED. Warehousing is accessory-only with floor-area caps: basement + 25% of 1st/2nd floor, or 40% of 1st/2nd alone (B(3)). Self-storage and mini-warehouse are principal-use warehousing, not accessory — prohibited. Garages permitted only to house delivery trucks/commercial vehicles accessory to a permitted use; not garage condominium ownership units."),
    ("D1", "prohibited", "prohibited", "prohibited", "prohibited",
     "D1 Station Area District (§ 236-17.1D(1)): form-based code. Permitted building types per (h): commercial block, liner, townhouse, civic, multifamily. No warehouse, industrial, storage, or garage-condo building types. Transit-oriented mixed-use district."),
    ("D2", "prohibited", "prohibited", "prohibited", "prohibited",
     "D2 Blackwell Street Historic District (§ 236-17.1D(2)): historic mixed-use retail/office/residential character. Existing buildings retained per Permitted Uses by Building Type table; new construction uses D3 regulations. No storage, warehouse, or industrial uses permitted."),
    ("D3", "prohibited", "prohibited", "prohibited", "prohibited",
     "D3 East Blackwell Business District (§ 236-17.1D(3)(h)): permitted building types are commercial block, corner buildings, civic. Mixed-use retail/office/residential extension of historic district. No warehouse, industrial, storage, or garage-condo building types listed."),
    ("D4", "prohibited", "prohibited", "prohibited", "prohibited",
     "D4 South Downtown District (§ 236-17.1D(4)(h)): permitted building types are liner, courtyard, multifamily, corner, townhouse, civic, commercial block. Mixed-use transit-oriented district. No warehouse, industrial, storage, or garage-condo building types listed."),
    ("IND", "permitted", "permitted", "permitted", "prohibited",
     "IND Industrial (§ 236-20): A(3) principal uses include 'warehouses, wholesale distribution centers, machine repair shops and public utility storage yards, garages and other warehouses and workshops' — self_storage and mini_warehouse PERMITTED as principal warehousing. A(1) covers manufacture/compounding/assembly/treatment in enclosed buildings — light_industrial PERMITTED. luxury_garage_condo is a specific use type not enumerated in the closed list (garages here refers to commercial/industrial garages, not condominium ownership units) — prohibited under § 236-15(B). Conditional: licensed cannabis (non-retail), public utility, satellite antennas."),
    ("IND/OP", "prohibited", "prohibited", "permitted", "prohibited",
     "IND/OP Industrial-Office Park (§ 236-21): principal uses are office complexes, light manufacturing (A(2)), scientific/research labs, hotel/motel complexes. Warehousing is accessory only, capped at 40% of building floor area (B). light_industrial PERMITTED via 'Light manufacturing' principal use. Self-storage and mini-warehouse are principal-use warehousing, not accessory — prohibited. luxury_garage_condo not enumerated — prohibited. 2-acre minimum lot, 200ft width, 65ft residential setback."),
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

    total = len(UPDATES)
    print(f"\nDone. {total - failures}/{total} successful.")
    if slashed_notes_skipped:
        print(
            f"Notes not set via API for {len(slashed_notes_skipped)} slashed "
            f"zone(s): {', '.join(slashed_notes_skipped)}. "
            f"Patch notes out-of-band if needed."
        )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
