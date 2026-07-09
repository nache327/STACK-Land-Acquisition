"""Walpole MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 10 base districts.

Source: Town of Walpole Zoning Bylaws, October 2025 (CURRENT; walpole-ma.gov
zoning_bylaws_october_2025.pdf). §4 Establishment of Districts + §5 Use Regulations,
Table 5-B.1. MAPC-rebind first (rebind_configs/walpole.json): 325 parcels rebound
2026-07-09 (assessor 'HBD' -> ordinance/MAPC 'HB'), matrix untouched.

CLOSED-LIST (§5-A): "No building or structure shall be designed, arranged or constructed
and no building, structure or land shall be used, in whole or in part for any purpose
other than for one or more of the uses hereinafter set forth in Section 5-B as permitted
in the district in which [it is located]." §5 key: A = permitted as of right; SPZ/SPP =
special permit (ZBA / Planning Board) = conditional; X = prohibited.

li GROUNDED permitted in HB/LM/IND — Table 5-B.1 §5.c 'Warehouse for the covered storage
of materials, supplies, equipment, and manufactured products' = A, and the light/general
manufacturing plant rows §5.p-§5.t = A, in those three commercial districts. li prohibited
in R/RA/RB/GR/PSRC (residential-public, all X) and B/CBD (business/central-business:
warehouse & principal manufacturing = X; only accessory light mfg by special permit).

ss/mw/lgc: NO named self-service-storage / mini-warehouse / storage-facility(consumer) /
garage-condominium use anywhere in the bylaw (catch-#58 whole-140-page sweep = 0 use hits;
the only 'storage facility' strings are accessory restroom / hazmat / utility). Warehouse-
by-right convention: where §5.c Warehouse is by-right (HB/LM/IND) => ss/mw/lgc CONDITIONAL;
everywhere warehouse is 'X' (the other 7 districts) => PROHIBITED (closed-list, no anchor).

Needle: HB/LM/IND light-industrial-permitted. POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Town of Walpole Zoning Bylaws, October 2025 (CURRENT); walpole-ma.gov "
       "zoning_bylaws_october_2025.pdf; §5 Use Regulations, Table 5-B.1")

_CLOSED = {"section": "§5-A", "ordinance": ORD, "quote":
    "§5-A: 'no building, structure or land shall be used, in whole or in part for any purpose "
    "other than for one or more of the uses hereinafter set forth in Section 5-B as permitted "
    "in the district'."}
_LEGEND = {"section": "§5 key", "ordinance": ORD, "quote":
    "§5 key: 'A - Use permitted as a matter of right'; 'SPZ'/'SPP' - special permit (ZBA / "
    "Planning Board); 'X - Use prohibited.'"}
_NONAME_COND = {"section": "Table 5-B.1 §5", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage / mini-warehouse / garage-condominium use named "
    "anywhere. §5.c Warehouse is by-right here -> ss/mw/lgc CONDITIONAL (warehouse subset, SP)."}
_NONAME_PROHIB = {"section": "Table 5-B.1 §5", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-storage / mini-warehouse / garage-condominium use named anywhere; "
    "§5.c Warehouse = X here (no by-right anchor) -> closed-list §5-A prohibits ss/mw/lgc."}

# district code -> (zone_name, is_industrial)
DISTRICTS = {
    "R":   ("Rural Resident District", False),
    "RA":  ("Residence A District", False),
    "RB":  ("Residence B District", False),
    "GR":  ("General Residence District", False),
    "PSRC": ("Park, School, Recreation and Conservation District", False),
    "B":   ("Business District", False),
    "CBD": ("Central Business District", False),
    "HB":  ("Highway Business District", True),
    "LM":  ("Limited Manufacturing District", True),
    "IND": ("Industrial District", True),
}


def _ind_table_quote(code: str) -> dict:
    return {"section": "Table 5-B.1 §5.c/§5.p-t", "ordinance": ORD, "quote":
            f"Table 5-B.1 [{code}]: §5.c 'Warehouse for the covered storage of materials, supplies, "
            f"equipment, and manufactured products' = A; §5.p-t manufacturing plants = A (A = by right)."}


def _prohib_table_quote(code: str) -> dict:
    extra = " (only accessory light mfg by special permit)" if code in ("B", "CBD") else ""
    return {"section": "Table 5-B.1 §5.c", "ordinance": ORD, "quote":
            f"Table 5-B.1 [{code}]: §5.c 'Warehouse for the covered storage of materials...' = X "
            f"(prohibited); principal manufacturing rows §5.p-t = X{extra}."}


def _row(code: str) -> dict:
    name, industrial = DISTRICTS[code]
    if industrial:
        return {
            "zone_code": code, "zone_name": name, "municipality": "WALPOLE",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
            "citations": [_ind_table_quote(code), _CLOSED, _LEGEND, _NONAME_COND],
        }
    return {
        "zone_code": code, "zone_name": name, "municipality": "WALPOLE",
        "self_storage": "prohibited", "mini_warehouse": "prohibited",
        "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": [_prohib_table_quote(code), _CLOSED, _NONAME_PROHIB],
    }


WALPOLE_ROWS = [_row(c) for c in DISTRICTS]


def main() -> int:
    rows = WALPOLE_ROWS
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
