"""Foxborough MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 8 base districts.

Source: Code of the Town of Foxborough, Chapter 275 Zoning (eCode360 FO3116; Districts
26808603, §3.0 Use Regulations 26808617; current through 10-27-2025 STM). Table 3-1 Table
of Uses. MAPC-rebind first (rebind_configs/foxborough.json): 5513 parcels rebound 2026-07-09
(normalized the malformed assessor vocab "R 40"/"R40"/".R 40"/OSRD/WRPD), matrix untouched.

CLOSED-LIST (§3.1): uses "are only allowed as noted below. Any use not noted herein is
prohibited." §3.1.1 'Y' = permitted as of right; §3.1.2 'N' = prohibited; BA/PB/SB =
special permit (Board of Appeals / Planning Board / Select Board) = conditional.

ss/mw AFFIRMATIVELY GROUNDED by NAMED use — Table 3-1 §D.7 "Self storage mini-warehouse":
R-15=N R-40=N GB=N NB=N HB=BA GI=Y LI=Y S-1=Y. So self_storage & mini_warehouse =
permitted (GI/LI/S-1), conditional (HB), prohibited (R-15/R-40/GB/NB). No convention needed.

li: §B.1 Low-Hazard (assembly/fabrication/manufacture/processing/storage of noncombustible
materials) = HB:BA GI:Y LI:Y S-1:PB; §D.8 Warehouse = HB/GI/LI/S-1:PB. => permitted GI/LI,
conditional HB/S-1, prohibited R-15/R-40/GB/NB.

lgc: no named garage-condominium use; nearest anchors §D.7 self-storage + §C.5 Commercial
storage garages (GI/LI=Y, HB=BA, S-1=PB). Luxury garage-condo is a hybrid (dead storage +
recreational) => CONDITIONAL where a storage anchor exists (HB/GI/LI/S-1), prohibited elsewhere.

Needle: GI/LI = self-storage BY RIGHT (strong). POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Code of the Town of Foxborough, Ch. 275 Zoning (eCode360 FO3116; §3.0 Use Regulations, "
       "Table 3-1; current through 10-27-2025 STM)")

_CLOSED = {"section": "§3.1", "ordinance": ORD, "quote":
    "§3.1: uses 'are only allowed as noted below. Any use not noted herein is prohibited.' "
    "§3.1.1 'Y' = permitted as of right; §3.1.2 'N' = prohibited; BA/PB/SB = special permit."}
_D7 = {"section": "Table 3-1 §D.7", "ordinance": ORD, "quote":
    "Table 3-1 §D.7 'Self storage mini-warehouse': R-15=N R-40=N GB=N NB=N HB=BA GI=Y LI=Y "
    "S-1=Y (Y=by right; BA=special permit Board of Appeals; N=prohibited)."}
_LI = {"section": "Table 3-1 §B.1/§D.8", "ordinance": ORD, "quote":
    "§B.1 Low-Hazard (assembly/fabrication/manufacture/processing/storage of noncombustible "
    "materials): HB=BA GI=Y LI=Y S-1=PB; §D.8 Warehouse: HB/GI/LI/S-1=PB."}
_LGC = {"section": "Table 3-1 §D.7/§C.5", "ordinance": ORD, "quote":
    "No named garage-condominium use; anchors §D.7 self-storage + §C.5 'Commercial storage "
    "garages' (GI/LI=Y, HB=BA). Luxury garage-condo hybrid -> CONDITIONAL where anchored."}
_NB_GB = {"section": "Table 3-1", "ordinance": ORD, "quote":
    "In GB/NB (business districts): §D.7 self-storage, §B.1 Low-Hazard, §D.8 Warehouse and §C.5 "
    "storage garages are all 'N' (prohibited)."}

# code -> (zone_name, ss, mw, li, lgc)
VERDICTS = {
    "R-15": ("Residential District", "prohibited", "prohibited", "prohibited", "prohibited"),
    "R-40": ("Residential and Agricultural District", "prohibited", "prohibited", "prohibited", "prohibited"),
    "GB":   ("General Business District", "prohibited", "prohibited", "prohibited", "prohibited"),
    "NB":   ("Neighborhood Business District", "prohibited", "prohibited", "prohibited", "prohibited"),
    "HB":   ("Highway Business District", "conditional", "conditional", "conditional", "conditional"),
    "GI":   ("General Industrial District", "permitted", "permitted", "permitted", "conditional"),
    "LI":   ("Limited Industrial District", "permitted", "permitted", "permitted", "conditional"),
    "S-1":  ("Special Use District", "permitted", "permitted", "conditional", "conditional"),
}


def _row(code: str) -> dict:
    name, ss, mw, li, lgc = VERDICTS[code]
    cites = [_D7, _LI, _CLOSED]
    if code in ("GI", "LI", "S-1", "HB"):
        cites.append(_LGC)
    else:
        cites.append(_NB_GB) if code in ("GB", "NB") else None
    cites = [c for c in cites if c]
    return {
        "zone_code": code, "zone_name": name, "municipality": "FOXBOROUGH",
        "self_storage": ss, "mini_warehouse": mw,
        "light_industrial": li, "luxury_garage_condo": lgc,
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": cites,
    }


FOXBOROUGH_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = FOXBOROUGH_ROWS
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
