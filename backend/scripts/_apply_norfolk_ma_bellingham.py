"""Bellingham MA (Norfolk County) — Stage-4 close. Self-storage NO-OP; light-industrial yield.

Source: Town of Bellingham Zoning Bylaw, Ch. 240 (eCode360 BE3069); §240-30/31 General Use
Regulations + Use Regulations Schedule (Art. V inline table). MAPC-rebind first
(rebind_configs/bellingham.json): 6,191 parcels rebound 2026-07-09 (filled ~55% null,
normalized RES/SUBN/AGR/BUS1/IND -> bylaw codes), matrix untouched.

CLOSED-LIST (§240-30.A): "No building or structure shall be erected or used and no premises
shall be used except as set forth in the Use Regulations Schedule." Schedule symbols:
Yes = permitted; No = prohibited; BA/PB/BS = special permit (Board of Appeals / Planning
Board / Board of Selectmen). Use-table columns group districts A | S,R | M | B-1,B-2 | I.

HONEST SELF-STORAGE NO-OP: 'Warehouse' (Use Regulations Schedule) = No in EVERY district
including Industrial (I); no self-service-storage / mini-warehouse use is named anywhere
(catch-#58 sweep = 0); 'Wholesaling without storage' is explicitly without storage. With
no warehouse by-right anchor in any district, ss/mw/lgc = PROHIBITED in all 7 districts.

li: 'Other manufacturing, research' = Yes in I; 'Manufacturing for on-site sales' = Yes in
B-1/B-2 and I; "Contractor's yard" = Yes in I. => li permitted in I; conditional in B-1/B-2
(only on-site-sales manufacturing by-right; general manufacturing/warehouse = No); prohibited
in A/S/R/M.

Needle: self-storage 0 (warehouse prohibited town-wide). li permitted in I (~175 parcels).
POST /_upload-matrix-rows (replace_existing=false).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
ORD = ("Town of Bellingham Zoning Bylaw, Ch. 240 (eCode360 BE3069); §240-30/31 Use Regulations "
       "Schedule (Art. V)")

_CLOSED = {"section": "§240-30.A", "ordinance": ORD, "quote":
    "§240-30.A: 'No building or structure shall be erected or used and no premises shall be used "
    "except as set forth in the Use Regulations Schedule.' (Yes=permitted; No=prohibited)"}
_WAREHOUSE = {"section": "§240-31 Schedule", "ordinance": ORD, "quote":
    "Use Regulations Schedule: 'Warehouse' = No in A, S/R, M, B-1/B-2 and I (all districts); "
    "'Wholesaling without storage' is explicitly without storage; no self-storage use named."}
_NONAME = {"section": "§240-31 Schedule", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage / mini-warehouse / garage-condominium use named. "
    "'Warehouse'=No in every district (no by-right anchor) -> closed-list prohibits ss/mw/lgc."}
_LI_I = {"section": "§240-31 Schedule", "ordinance": ORD, "quote":
    "Use Regulations Schedule: 'Other manufacturing, research' = Yes in I; 'Manufacturing for "
    "on-site sales' = Yes in B-1/B-2 and I; \"Contractor's yard\" = Yes in I."}
_LI_B = {"section": "§240-31 Schedule", "ordinance": ORD, "quote":
    "Use Regulations Schedule: 'Manufacturing for on-site sales' = Yes in B-1/B-2 (limited); "
    "'Other manufacturing, research' and 'Warehouse' = No in B-1/B-2."}
_PROHIB_RES = {"section": "§240-31 Schedule", "ordinance": ORD, "quote":
    "Use Regulations Schedule: 'Manufacturing for on-site sales', 'Other manufacturing, research', "
    "'Warehouse' and 'Wholesaling' are all 'No' in A/S/R/M (residential/agricultural)."}

# code -> (zone_name, profile)  profile in {res, b, i}
VERDICTS = {
    "A":   ("Agricultural District", "res"),
    "S":   ("Suburban District", "res"),
    "R":   ("Residential District", "res"),
    "M":   ("Multifamily Dwelling District", "res"),
    "B-1": ("Business District B-1", "b"),
    "B-2": ("Business District B-2", "b"),
    "I":   ("Industrial District", "i"),
}


def _row(code: str) -> dict:
    name, prof = VERDICTS[code]
    base = {"zone_code": code, "zone_name": name, "municipality": "BELLINGHAM",
            "self_storage": "prohibited", "mini_warehouse": "prohibited",
            "luxury_garage_condo": "prohibited",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True}
    if prof == "i":
        base.update(light_industrial="permitted", citations=[_LI_I, _WAREHOUSE, _NONAME, _CLOSED])
    elif prof == "b":
        base.update(light_industrial="conditional", confidence=0.9,
                    citations=[_LI_B, _WAREHOUSE, _NONAME, _CLOSED])
    else:
        base.update(light_industrial="prohibited", citations=[_PROHIB_RES, _NONAME, _CLOSED])
    return base


BELLINGHAM_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = BELLINGHAM_ROWS
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}\n  rows={len(rows)}  replace_existing=False")
    for r in rows:
        print(f"  {r['zone_code']:4} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} "
              f"li={r['light_industrial']:11} lgc={r['luxury_garage_condo']}")
    r = httpx.post(URL, json=payload, headers=admin_headers(), timeout=120.0)
    print(f"\nHTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
