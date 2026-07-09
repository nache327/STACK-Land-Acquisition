"""Sharon MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 14 districts.

Source: Town of Sharon Zoning Bylaw, Ch. 275 (eCode360 SH3206); §3.2 Table of Use
Regulations (Attachment 1 PDF, adopted 5-2-2022, amended thru 5-5-2025 ATM). MAPC-rebind
first (rebind_configs/sharon.json): 6,501 parcels rebound 2026-07-09 — Sharon was ~98.8%
NULL, so the rebind spatially FILLED the districts (code_map SA/SB->SRA/SRB, BD->BD1),
matrix untouched.

§3.2 Table 1 KEY: Y = Yes (by right); N = No (prohibited); BA = Special permit Zoning
Board of Appeals; PB = Special permit Planning Board; SB = Special permit Select Board.

ss/mw AFFIRMATIVELY GROUNDED by NAMED use — Table 1 §J.5 "Mini or self-storage warehouse":
= BA in the Light Industrial (LI) district ONLY, and 'N' in every other district. So
self_storage & mini_warehouse = conditional (LI), prohibited (all 13 others).

li: Table 1 §J.2 'Manufacturing' = Y in LI; §J.4 'Warehouse, storage, distribution
facility; wholesale facility' = Y in LI; both 'N' in every other district. => permitted LI,
prohibited elsewhere.

lgc: no named garage-condominium use; nearest anchor §J.5 Mini/self-storage warehouse
(LI=BA) => conditional in LI, prohibited elsewhere.

Every non-LI district affirmatively marks these uses 'N' (not silence). Needle: LI
(~50 parcels) = self-storage by special permit + light-industrial/warehouse by right.
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
ORD = ("Town of Sharon Zoning Bylaw, Ch. 275 (eCode360 SH3206); §3.2 Table of Use Regulations "
       "(Attachment 1; adopted 5-2-2022, amended thru 5-5-2025 ATM)")

_MINI = {"section": "§3.2 Table 1 §J.5", "ordinance": ORD, "quote":
    "Table 1 §J.5 'Mini or self-storage warehouse' = BA in Light Industrial (LI) ONLY; 'N' in "
    "every other district (BA = Special permit Zoning Board of Appeals; Y=Yes; N=No)."}
_IND = {"section": "§3.2 Table 1 §J.2/§J.4", "ordinance": ORD, "quote":
    "Table 1 §J.2 'Manufacturing' = Y in LI; §J.4 'Warehouse, storage, distribution facility; "
    "wholesale facility' = Y in LI (Y = by right); both 'N' in every other district."}
_LGC = {"section": "§3.2 Table 1 §J.5", "ordinance": ORD, "quote":
    "No named garage-condominium use; nearest anchor §J.5 'Mini or self-storage warehouse' "
    "(LI=BA). Luxury garage-condo -> CONDITIONAL in LI where the storage anchor exists."}
_PROHIB = {"section": "§3.2 Table 1", "ordinance": ORD, "quote":
    "Table 1: §J.5 'Mini or self-storage warehouse', §J.2 'Manufacturing' and §J.4 'Warehouse, "
    "storage, distribution...wholesale facility' are all 'N' (No/prohibited) in this district."}

# code -> (zone_name, is_LI)
DISTRICTS = {
    "R1":   ("Rural District 1", False),
    "R2":   ("Rural District 2", False),
    "SUB1": ("Suburban District 1", False),
    "SUB2": ("Suburban District 2", False),
    "SRA":  ("Single Residence District A", False),
    "SRB":  ("Single Residence District B", False),
    "GR":   ("General Residence District", False),
    "HA":   ("Housing Authority District", False),
    "BA":   ("Business District A", False),
    "BB":   ("Business District B", False),
    "BC":   ("Business District C", False),
    "BD1":  ("Business District D", False),
    "P":    ("Professional District", False),
    "LI":   ("Light Industrial District", True),
}


def _row(code: str) -> dict:
    name, is_li = DISTRICTS[code]
    if is_li:
        return {
            "zone_code": code, "zone_name": name, "municipality": "SHARON",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
            "citations": [_MINI, _IND, _LGC],
        }
    return {
        "zone_code": code, "zone_name": name, "municipality": "SHARON",
        "self_storage": "prohibited", "mini_warehouse": "prohibited",
        "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": [_PROHIB, _MINI],
    }


SHARON_ROWS = [_row(c) for c in DISTRICTS]


def main() -> int:
    rows = SHARON_ROWS
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}\n  rows={len(rows)}  replace_existing=False")
    for r in rows:
        print(f"  {r['zone_code']:5} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} "
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
