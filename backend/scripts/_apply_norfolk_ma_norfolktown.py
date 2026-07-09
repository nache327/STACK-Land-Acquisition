"""Norfolk (town, Norfolk County MA) — Stage-4 FULL close. REAL self-storage needle.

Source: Town of Norfolk, Ch. 310 Zoning (eCode360 NO3198); Art. 4 Use Regulations +
Schedule of Use Regulations = Attachment 310a PDF (Supp 6, Nov 2025). MAPC-rebind first
(rebind_configs/norfolktown.json): 3,971 parcels rebound 2026-07-09 (normalized R1/R2/R3 +
decoded COM/IND umbrella assessor codes to C-1/C-1A/B-1; 'B-1 OUT'->B-1), matrix untouched.

Schedule columns: R | B-1 | B-3 | B-4 | C-1 | C-1a | C-1b | C-1c | C-1d | C-3 | C-4 | C-5 |
C-6 (C-1a..C-1d = the Rte-1A/115 Highway commercial subdistricts). Symbols: Yes = by right;
No = prohibited; SPZ/SPZB/SPPB = special permit. (MAPC carries C-1A but not C-1b/c/d — no
mapped parcels; verdict identical across the C-1a-family anyway.)

ss/mw AFFIRMATIVELY GROUNDED by NAMED use — Schedule 'Self-storage facilities' = Yes in
C-1a(..C-1d) and C-6; No everywhere else. => self_storage & mini_warehouse PERMITTED in
C-1A and C-6, prohibited in R-1/R-2/R-3/B-1/B-3/B-4/C-1/C-3/C-4/C-5.

li: Schedule 'Manufacturing' = Yes in C-1/C-1a/C-3/C-5/C-6; 'Warehouses' = Yes in C-1a/C-6.
=> li permitted in C-1/C-1A/C-3/C-5/C-6; prohibited in R*/B*/C-4.

lgc: no named garage-condominium use; nearest anchor 'Self-storage facilities' (Yes in
C-1A/C-6) => conditional in C-1A/C-6, prohibited elsewhere.

Needle: self-storage BY-RIGHT in C-1A + C-6 (the Rte-1A/115 highway commercial pool).
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
ORD = ("Town of Norfolk, Ch. 310 Zoning (eCode360 NO3198); Art. 4 + Schedule of Use Regulations "
       "(Attachment 310a, Supp 6 Nov 2025)")

_SS = {"section": "Schedule of Use Regs", "ordinance": ORD, "quote":
    "Schedule of Use Regulations: 'Self-storage facilities' = Yes (by right) in C-1a(..C-1d) and "
    "C-6; No in all other districts (Yes=by right; No=prohibited; SPZ/SPZB=special permit)."}
_LI = {"section": "Schedule of Use Regs", "ordinance": ORD, "quote":
    "Schedule: 'Manufacturing' = Yes in C-1/C-1a/C-3/C-5/C-6; 'Warehouses' = Yes in C-1a and C-6 "
    "(Yes = by right)."}
_LGC = {"section": "Schedule of Use Regs", "ordinance": ORD, "quote":
    "No named garage-condominium use; nearest anchor 'Self-storage facilities' (Yes in C-1a/C-6) "
    "-> luxury garage-condo CONDITIONAL where the storage anchor exists."}
_PROHIB = {"section": "Schedule of Use Regs", "ordinance": ORD, "quote":
    "Schedule: 'Self-storage facilities', 'Warehouses' and 'Manufacturing' are all 'No' "
    "(prohibited) in this district."}
_LI_NOSS = {"section": "Schedule of Use Regs", "ordinance": ORD, "quote":
    "Schedule: 'Manufacturing' = Yes (by right) in this district; 'Self-storage facilities' and "
    "'Warehouses' = No -> li permitted, ss/mw prohibited."}

# code -> (zone_name, ss, mw, li, lgc, profile)
VERDICTS = {
    "R-1": ("Residential District R-1", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "R-2": ("Residential District R-2", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "R-3": ("Residential District R-3", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "B-1": ("B-1 District (Town Center)", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "B-3": ("B-3 District", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "B-4": ("B-4 District", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "C-4": ("C-4 Mixed-Use District", "prohibited", "prohibited", "prohibited", "prohibited", "p"),
    "C-1": ("C-1 District (Rtes 1A/115)", "prohibited", "prohibited", "permitted", "prohibited", "li"),
    "C-3": ("C-3 District", "prohibited", "prohibited", "permitted", "prohibited", "li"),
    "C-5": ("C-5 District", "prohibited", "prohibited", "permitted", "prohibited", "li"),
    "C-1A": ("C-1a Highway Commercial District", "permitted", "permitted", "permitted", "conditional", "ss"),
    "C-6": ("C-6 Commercial Use District (Rte 1A, Dedham St)", "permitted", "permitted", "permitted", "conditional", "ss"),
}


def _row(code: str) -> dict:
    name, ss, mw, li, lgc, prof = VERDICTS[code]
    cites = {"p": [_PROHIB], "li": [_LI_NOSS, _LI], "ss": [_SS, _LI, _LGC]}[prof]
    return {
        "zone_code": code, "zone_name": name, "municipality": "NORFOLK",
        "self_storage": ss, "mini_warehouse": mw,
        "light_industrial": li, "luxury_garage_condo": lgc,
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": cites,
    }


NORFOLKTOWN_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = NORFOLKTOWN_ROWS
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
