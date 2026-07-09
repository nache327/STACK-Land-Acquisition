"""Randolph MA (Norfolk County) — Stage-4 close. 14 grounded districts; 3 codes escalated.

Source: Code of the Town of Randolph, Chapter 200 Zoning (eCode360 RA1509; §3.1 Establishment,
§4.6 Town of Randolph Table of Uses). NO MAPC rebind: the MAPC Randolph layer is
consolidated to only 6 coarse districts (SF/BP/BD/RSFHD/I/RMFD) vs the ordinance's 13
base districts — a MAPC rebind would REGRESS granularity (Braintree-class gate-b fail with
no clean town-GIS substitute at hand). Verdicts are therefore keyed to the existing parcel
(assessor) codes, mapped to the §4.6 Table district each represents.

§4.6 KEY: P = Permitted by right; — = Not permitted; SPTC/SPPB = special permit
(Town Council / Planning Board) = conditional. Columns: CSBD NRBD WCBD BD BP OSBD BRHD
GBHD ID SFD RHDD RMDD RMFD.

li GROUNDED permitted in the industrial/highway districts — §4.6 'Warehousing and storage'
= P in ID; 'Manufacturing, light' = P in BRHD/GBHD/ID; 'Wholesaling, warehousing,
distributing...' = P in BRHD/GBHD/ID. Prohibited in every residential (RHDD/RMDD/RMFD) and
business (CSBD/NRBD/WCBD/BD/BP) district (all '—') and SFD.

ss/mw/lgc: NO named self-service-storage / mini-warehouse use anywhere (catch-#58 sweep = 0).
Warehouse-by-right convention: where 'Warehousing and storage' / 'Wholesaling, warehousing'
is by-right (I=ID, BHRD=BRHD, GBHD) => ss/mw/lgc CONDITIONAL; everywhere warehousing is '—'
=> PROHIBITED.

ESCALATED to _exception_queue.md (tag B): GPOD (16 parcels; Great Pond Commerce Center
Overlay code obscures base zoning), HA (3), C (1) — unknown/overlay assessor codes.

Assessor->ordinance map: RH=RHDD, RM=RMDD, A=RMFD, R/A55=residential, B=BD, BP=BPD,
BHRD=BRHD (transposition). POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Code of the Town of Randolph, Ch. 200 Zoning (eCode360 RA1509); §4.6 Town of Randolph "
       "Table of Uses")

_IND_TABLE = {"section": "§4.6", "ordinance": ORD, "quote":
    "§4.6 Table of Uses: 'Warehousing and storage' = P in ID; 'Manufacturing, light' = P in "
    "BRHD/GBHD/ID; 'Wholesaling, warehousing, distributing...' = P in BRHD/GBHD/ID (P=by right)."}
_IND_CONV = {"section": "§4.6", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage / mini-warehouse use named anywhere. Warehousing "
    "is by-right here -> ss/mw/lgc CONDITIONAL (warehouse subset, special permit)."}
_PROHIB_TABLE = {"section": "§4.6", "ordinance": ORD, "quote":
    "§4.6 Table of Uses: 'Warehousing and storage', 'Manufacturing, light' and 'Wholesaling, "
    "warehousing, distributing...' are all '—' (Not permitted) in this district."}
_PROHIB_CONV = {"section": "§4.6", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-storage / mini-warehouse use named; warehousing is '—' (not "
    "permitted) here -> closed-list prohibits ss/mw/lgc."}

# assessor code -> (zone_name, is_industrial)
DISTRICTS = {
    "RH":   ("Residential High Density District (RHDD)", False),
    "RM":   ("Residential Medium Density District (RMDD)", False),
    "A":    ("Residential Multi Family District (RMFD)", False),
    "A55":  ("Age-restricted residential (RMFD-class)", False),
    "R":    ("Residential", False),
    "CSBD": ("Crawford Square Business District", False),
    "NRBD": ("North Randolph Business District", False),
    "WCBD": ("West Corners Business District", False),
    "B":    ("Business District (BD)", False),
    "BP":   ("Business Professional District (BPD)", False),
    "SFD":  ("Sanitary Facility District", False),
    "I":    ("Industrial District (ID)", True),
    "BHRD": ("Blue Hill River Highway District (BRHD)", True),
    "GBHD": ("Great Bear Swamp Highway District (GBHD)", True),
}


def _row(code: str) -> dict:
    name, industrial = DISTRICTS[code]
    if industrial:
        return {
            "zone_code": code, "zone_name": name, "municipality": "RANDOLPH",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.9, "classification_source": "human", "human_reviewed": True,
            "citations": [_IND_TABLE, _IND_CONV],
        }
    return {
        "zone_code": code, "zone_name": name, "municipality": "RANDOLPH",
        "self_storage": "prohibited", "mini_warehouse": "prohibited",
        "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
        "confidence": 0.9, "classification_source": "human", "human_reviewed": True,
        "citations": [_PROHIB_TABLE, _PROHIB_CONV],
    }


RANDOLPH_ROWS = [_row(c) for c in DISTRICTS]


def main() -> int:
    rows = RANDOLPH_ROWS
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
