"""Holbrook MA (Norfolk County) — Stage-4 FULL close. Named self-storage (special permit).

Source: Holbrook Zoning By-Law (Sept 2019; holbrookma.gov/372 DocumentCenter PDF); Table of
Use Regulations (Appendix A). MAPC-rebind first (rebind_configs/holbrook.json): 564 parcels
rebound 2026-07-09 (normalized + decoded assessor 'TC' town-center -> B business), matrix
untouched. Use-table columns: Res I-V | Bus I | Bus II | BV | BC | I. 'Y' = permitted;
'N' = prohibited; 'PB' = special permit (Planning Board). MAPC: R1-R5=Res I-V, B1=Bus I,
B2=Bus II, BC, I; 'W' (Water) is not a use-table district -> nonbinding.

ss/mw GROUNDED by NAMED use — Appendix A row 20 'Self Service Storage Warehouse providing
warehouse storage services directly to the general public...within buildings' = PB in Bus I,
Bus II, BV, BC and I; N in Res I-V. => self_storage & mini_warehouse CONDITIONAL (special
permit) in B1/B2/BC/I; prohibited in R1-R5.

li: 'Light manufacturing' = BC:PB, I:Y; 'Place for manufacturing...' = I:Y; 'Wholesale
business and storage (roofed)' and 'Trucking/Freight terminals' = BC:Y, I:Y; all industrial
rows = N in Bus I/Bus II. => li permitted in BC and I; prohibited in R1-R5, B1, B2.

lgc: no named garage-condominium use; nearest anchor row-20 Self Service Storage Warehouse
(PB in B1/B2/BC/I) -> conditional there, prohibited in R1-R5.

Needle: self-storage conditional (special permit) in B1/B2/BC/I. POST /_upload-matrix-rows.
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
ORD = ("Holbrook Zoning By-Law (Sept 2019; holbrookma.gov/372 DocumentCenter PDF); Appendix A "
       "Table of Use Regulations")

_SS = {"section": "App. A row 20", "ordinance": ORD, "quote":
    "App. A row 20 'Self Service Storage Warehouse providing warehouse storage services directly "
    "to the general public...within buildings' = PB in Bus I/II/BV/BC/I; N in Res I-V (PB=SP Planning Board)."}
_LI = {"section": "App. A §G/§D", "ordinance": ORD, "quote":
    "App. A 'Light manufacturing'=I:Y (BC:PB); 'Place for manufacturing...'=I:Y; 'Wholesale business "
    "and storage'/'Trucking/Freight terminals'=BC:Y,I:Y (Y=by right)."}
_LGC = {"section": "App. A row 20", "ordinance": ORD, "quote":
    "No named garage-condominium use; nearest anchor row-20 Self Service Storage Warehouse (PB in "
    "B1/B2/BC/I) -> luxury garage-condo CONDITIONAL where the storage anchor exists."}
_PROHIB = {"section": "App. A", "ordinance": ORD, "quote":
    "App. A: 'Self Service Storage Warehouse' (row 20) and the §G Industrial/Manufacturing uses are "
    "all 'N' (prohibited) in this district."}
_B_LI_N = {"section": "App. A §G", "ordinance": ORD, "quote":
    "App. A §G: 'Light manufacturing', 'Place for manufacturing', 'Wholesale business and storage', "
    "'Trucking/Freight terminals' are all 'N' in Bus I/Bus II -> li prohibited."}

# code -> (zone_name, profile) profile: res / bus (ss cond, li prohib) / ind (ss cond, li permitted)
VERDICTS = {
    "R1": ("Residence I District", "res"), "R2": ("Residence II District", "res"),
    "R3": ("Residence III District", "res"), "R4": ("Residence IV District", "res"),
    "R5": ("Residence V District", "res"),
    "B1": ("Business I District", "bus"), "B2": ("Business II District", "bus"),
    "BC": ("Business/Commercial (BC) District", "ind"),
    "I":  ("Industrial District", "ind"),
}


def _row(code: str) -> dict:
    name, prof = VERDICTS[code]
    if prof == "res":
        return {"zone_code": code, "zone_name": name, "municipality": "HOLBROOK",
                "self_storage": "prohibited", "mini_warehouse": "prohibited",
                "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
                "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
                "citations": [_PROHIB]}
    if prof == "bus":
        return {"zone_code": code, "zone_name": name, "municipality": "HOLBROOK",
                "self_storage": "conditional", "mini_warehouse": "conditional",
                "light_industrial": "prohibited", "luxury_garage_condo": "conditional",
                "confidence": 0.9, "classification_source": "human", "human_reviewed": True,
                "citations": [_SS, _B_LI_N, _LGC]}
    return {"zone_code": code, "zone_name": name, "municipality": "HOLBROOK",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
            "citations": [_SS, _LI, _LGC]}


HOLBROOK_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = HOLBROOK_ROWS
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
