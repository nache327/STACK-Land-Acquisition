"""Medfield MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 8 districts.

Source: Town of Medfield Zoning Bylaw, Ch. 300 (eCode360 ME3164); Table of Use Regulations
= 300 Attachment 1 PDF (amended thru 5-5-2025 ATM). MAPC-rebind first
(rebind_configs/medfield.json): 149 parcels rebound 2026-07-09 (MAPC codes match assessor
1:1), matrix untouched.

CLOSED-LIST (§Use Regulations): "No building, structure, or land shall be used or occupied
except for the purposes permitted in its district." Table symbols: YES = permitted by right;
PB = permitted by right but requires Planning Board site plan approval; SP = special permit
(Board of Appeals); SPPB = special permit (Planning Board); NO = not permitted. Columns:
A RE RT RS RU B BI IE.

li GROUNDED — Table §5.5 'Trucking service and warehousing' = PB (by-right w/ site plan) in
BI/IE; §5.7 'Wholesale trade' = PB in BI/IE; §5.6 'Printing and publishing' = PB in B/BI/IE;
§5.3 'Manufacturing/Fabrication' = SP in BI/IE. => permitted BI/IE (multiple by-right
light-industrial uses), conditional B (printing/publishing PB only; general mfg/warehousing
NO), prohibited A/RE/RT/RS/RU (all NO).

ss/mw: NO named self-service-storage / mini-warehouse use (catch-#58 sweep = 0). Warehouse-
by-right convention anchored on §5.5 'Trucking service and warehousing' = PB (by-right) in
BI/IE => ss/mw CONDITIONAL in BI/IE; PROHIBITED elsewhere (warehousing = NO; closed-list).

lgc: no named garage-condominium use; nearest anchor §5.5 warehousing (BI/IE=PB) =>
CONDITIONAL in BI/IE, prohibited elsewhere.

Needle: BI/IE (~60 parcels) light-industrial + warehousing by right. POST /_upload-matrix-rows.
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
ORD = ("Town of Medfield Zoning Bylaw, Ch. 300 (eCode360 ME3164); Table of Use Regulations "
       "(300 Attachment 1; amended thru 5-5-2025 ATM)")

_CLOSED = {"section": "§ Use Regulations", "ordinance": ORD, "quote":
    "Use Regulations: 'No building, structure, or land shall be used or occupied except for the "
    "purposes permitted in its district.' (YES=by right; PB=by right w/ site plan; NO=not permitted)"}
_IND = {"section": "Table §5.5/§5.7/§5.3", "ordinance": ORD, "quote":
    "Table §5.5 'Trucking service and warehousing'=PB in BI/IE; §5.7 'Wholesale trade'=PB in "
    "BI/IE; §5.3 'Manufacturing/Fabrication'=SP in BI/IE (PB=by right w/ site plan)."}
_IND_CONV = {"section": "Table §5.5", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage / mini-warehouse use named. §5.5 warehousing is "
    "by-right (PB) here -> ss/mw/lgc CONDITIONAL (warehouse subset)."}
_B_LI = {"section": "Table §5.6", "ordinance": ORD, "quote":
    "Table §5.6 'Printing and publishing'=PB (by right) in B; general §5.3 Manufacturing, §5.5 "
    "Trucking/warehousing, §5.7 Wholesale trade = NO in B -> limited light-industrial."}
_PROHIB = {"section": "Table §5", "ordinance": ORD, "quote":
    "Table §5: 'Trucking service and warehousing' (§5.5), 'Manufacturing/Fabrication' (§5.3) and "
    "'Wholesale trade' (§5.7) are all 'NO' (not permitted) in this district."}
_PROHIB_CONV = {"section": "Table §5.5", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-storage / mini-warehouse use named; §5.5 warehousing = NO here "
    "(no by-right anchor) -> closed-list prohibits ss/mw/lgc."}

# code -> (zone_name, profile)  profile in {res, b, ind}
VERDICTS = {
    "A":  ("Agricultural District", "res"),
    "RE": ("Residential Estate District", "res"),
    "RT": ("Residential Town District", "res"),
    "RS": ("Residential Suburban District", "res"),
    "RU": ("Residential Urban District", "res"),
    "B":  ("Business District", "b"),
    "BI": ("Business-Industrial District", "ind"),
    "IE": ("Industrial-Extensive District", "ind"),
}


def _row(code: str) -> dict:
    name, prof = VERDICTS[code]
    if prof == "ind":
        return {
            "zone_code": code, "zone_name": name, "municipality": "MEDFIELD",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
            "citations": [_IND, _IND_CONV, _CLOSED],
        }
    if prof == "b":
        return {
            "zone_code": code, "zone_name": name, "municipality": "MEDFIELD",
            "self_storage": "prohibited", "mini_warehouse": "prohibited",
            "light_industrial": "conditional", "luxury_garage_condo": "prohibited",
            "confidence": 0.9, "classification_source": "human", "human_reviewed": True,
            "citations": [_B_LI, _PROHIB, _CLOSED],
        }
    return {
        "zone_code": code, "zone_name": name, "municipality": "MEDFIELD",
        "self_storage": "prohibited", "mini_warehouse": "prohibited",
        "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": [_PROHIB, _PROHIB_CONV, _CLOSED],
    }


MEDFIELD_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = MEDFIELD_ROWS
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
