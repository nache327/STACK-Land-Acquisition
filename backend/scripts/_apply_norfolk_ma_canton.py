"""Canton MA (Norfolk County) — Stage-4 close. Self-storage NO-OP; light-industrial yield.

Source: Town of Canton Zoning By-Laws; §3.1 Use Regulations + Table of Use Regulations
(Attachment A = current 'TABLE OF USE REGULATIONS 2026', town.canton.ma.us
DocumentCenter/View/13244). MAPC-rebind first (rebind_configs/canton.json): 7,058 parcels
rebound 2026-07-09 — decoded the town's NUMERIC assessor codes (11/12/9/10/3/6/5/1/7)
spatially to SRA/SRAA/SRB/SRC/GR/B/I/LI/POS, matrix untouched.

SCHEME NOTE: MAPC reflects the pre-2026 district scheme (SRA/SRAA/SRB/SRC single-residence
variants; single LI). The 2026 recodification consolidated single-residence to 'SR' and split
LI into LI/LI(B)/LI(C) + added CB. For the 4 storage/industrial uses this is immaterial: the
2026 table's LI/LI(B)/LI(C) columns are IDENTICAL (light mfg = Y, warehouse = BA), and every
residential (SR*/GR), business (B/CB) and open-space (POS) district prohibits them — so MAPC's
codes map to robust verdicts (NOT a Hudson-class hold; codes correspond to real current districts).

CLOSED-LIST (§3.1.1): "No building, structure or land shall be used, in whole or in part, for
any purpose other than for one or more of the uses hereinafter set forth as permitted in the
district." Symbols: Y=by right; N=prohibited; BA/PB/SB=special permit (ZBA/Planning/Selectboard).

li GROUNDED permitted in LI (+family) and I — 2026 Table §I 'Light manufacturing' = Y in
LI/LI(B)/LI(C)/I; 'Manufacturing' = Y in LI and I. Prohibited in SR*/GR/B/POS (all 'N').

ss/mw/lgc: NO named self-service-storage / mini-warehouse use (catch-#58 sweep = 0). The only
storage use, 'Warehouse or distribution plant' (defined as storage "for distribution"), is BA
(special permit) — NOT by-right — in the LI-family/I. Per the warehouse-by-right convention a
conditional-warehouse does NOT bump ss/mw to conditional, and self-storage (dead consumer storage)
is not a distribution plant -> closed-list PROHIBITS ss/mw/lgc in every district.

Needle: self-storage 0 (warehouse only special-permit + not a distribution plant); li permitted
in LI+I (~340 parcels). POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Town of Canton Zoning By-Laws; §3.1 + Table of Use Regulations (Attachment A = "
       "TABLE OF USE REGULATIONS 2026, town.canton.ma.us DocumentCenter/View/13244)")

_CLOSED = {"section": "§3.1.1", "ordinance": ORD, "quote":
    "§3.1.1: 'No building, structure or land shall be used, in whole or in part, for any purpose "
    "other than for one or more of the uses hereinafter set forth as permitted in the district.'"}
_LI = {"section": "2026 Table §I", "ordinance": ORD, "quote":
    "2026 Table §I: 'Light manufacturing' = Y in LI/LI(B)/LI(C)/I; 'Manufacturing' = Y in LI and I "
    "(Y = by right)."}
_NONAME = {"section": "2026 Table §I", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage/mini-warehouse use named. Only storage use 'Warehouse "
    "or distribution plant' = BA (special permit, for distribution) -> closed-list prohibits ss/mw/lgc."}
_PROHIB = {"section": "2026 Table §I", "ordinance": ORD, "quote":
    "2026 Table §I: 'Light manufacturing', 'Manufacturing' and 'Warehouse or distribution plant' are "
    "all 'N' (prohibited) in this district."}

# code -> (zone_name, is_industrial)
DISTRICTS = {
    "SRA":  ("Single Residence A District", False),
    "SRAA": ("Single Residence AA District", False),
    "SRB":  ("Single Residence B District", False),
    "SRC":  ("Single Residence C District", False),
    "GR":   ("General Residence District", False),
    "B":    ("Business District", False),
    "POS":  ("Parkland/Open Space District", False),
    "I":    ("Industrial District", True),
    "LI":   ("Limited Industrial District", True),
}


def _row(code: str) -> dict:
    name, industrial = DISTRICTS[code]
    base = {"zone_code": code, "zone_name": name, "municipality": "CANTON",
            "self_storage": "prohibited", "mini_warehouse": "prohibited",
            "luxury_garage_condo": "prohibited",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True}
    if industrial:
        base.update(light_industrial="permitted", citations=[_LI, _NONAME, _CLOSED])
    else:
        base.update(light_industrial="prohibited", citations=[_PROHIB, _NONAME, _CLOSED])
    return base


CANTON_ROWS = [_row(c) for c in DISTRICTS]


def main() -> int:
    rows = CANTON_ROWS
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
