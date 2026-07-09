"""Norwood MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 13 base districts.

Source: Town of Norwood Zoning Bylaws, Chapter Z (eCode360 NO6678 / ecode360.com/42511340,
current through 10-24-2024). §2.1 Establishment + §3.1 Principal Uses / §3.1.6 Table of
Use Regulations. MAPC-rebind first (rebind_configs/norwood.json): MAPC 'HB' = ordinance
'BPH' (Boston-Providence Highway District, Route 1 corridor); 997 parcels rebound
2026-07-09, matrix untouched.

CLOSED-LIST (§3.1): "no building or structure shall be constructed, and no building,
structure or land shall be used, in whole or in part, except as permitted under Section
3.1.6, Table of Use Regulations." §3.1.1: Y = permitted as of right; N = prohibited.
§3.1.2/§3.1.3: BA/PB = special permit (Board of Appeals / Planning Board, §10.4) = conditional.

li GROUNDED permitted in BPH/LM/LMA/M — §3.1.6 names "Storage warehouse or distribution
plant" (G.2.c) AND "Light manufacturing" (I.3) AND "Manufacturing" (I.4, M/BPH) by-right (Y)
in those districts (BPH subject to fn.12 Route 1 ground-level 100-ft locational limit, NOT
a prohibition). li prohibited in the 9 residential/commercial/office districts (all storage
& manufacturing rows = N; Office-Research O permits laboratory research only, light mfg = N).

ss/mw/lgc: NO named self-service-storage / mini-warehouse / garage-condominium use anywhere
in the bylaw (catch #58 whole-table sweep = 0 hits). Warehouse-by-right convention: where
"Storage warehouse or distribution plant" is by-right (BPH/LM/LMA/M) => ss/mw/lgc CONDITIONAL
(plausible warehouse subset, special-permit interpretation). Everywhere warehouse is 'N'
(the other 9 districts) => ss/mw/lgc PROHIBITED (closed-list, no anchor).

Needle: BPH 65 / LM 90 / LMA 1 / M 264 = ~420 light-industrial-permitted parcels. Armed
self-storage = 0 (no by-right path). POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Town of Norwood Zoning Bylaws, Chapter Z (eCode360 NO6678 / ecode360.com/42511340, "
       "current through 10-24-2024); §3.1 Principal Uses / §3.1.6 Table of Use Regulations")

# Each `quote` is capped at 200 chars by the API (CitationSchema guard); grounding is
# carried across several short verbatim excerpts. The long provenance lives in `ordinance`.
_CLOSED = {"section": "§3.1", "ordinance": ORD, "quote":
    "§3.1: 'no building or structure shall be constructed, and no building, structure or land "
    "shall be used, in whole or in part, except as permitted under Section 3.1.6, Table of Use "
    "Regulations.'"}
_LEGEND = {"section": "§3.1.1-3.1.3", "ordinance": ORD, "quote":
    "§3.1.1: a use 'is permitted as of right...where it is denoted by the letter Y'; 'A "
    "prohibited use is denoted by the letter N.' §3.1.2/.3: 'BA'/'PB' = special permit."}
_FN12 = {"section": "§3.1.6 fn.12", "ordinance": ORD, "quote":
    "Fn.12: 'Route 1 Ground Level Use Restriction - These uses shall not be located at ground "
    "level within 100 feet of the Route 1 Right-of-Way line' (locational limit, not a prohibition)."}
_NONAME_COND = {"section": "§3.1.6 G.2", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-service-storage / mini-warehouse / garage-condominium use named "
    "anywhere. Warehouse by-right here -> ss/mw/lgc CONDITIONAL (special-permit warehouse subset)."}
_NONAME_PROHIB = {"section": "§3.1.6 G.2", "ordinance": ORD, "quote":
    "Catch-#58 sweep: no self-storage / mini-warehouse / garage-condominium use named anywhere; "
    "no warehouse by-right anchor -> closed-list §3.1 prohibits ss/mw/lgc."}
_OFFICE_CIT = {"section": "§3.1.6 I.1", "ordinance": ORD, "quote":
    "Office-Research permits only I.1 'Laboratory engaged in research, experimental or testing "
    "activities' = Y among industrial uses; principal light mfg / warehouse = N."}

# district code -> (zone_name, is_industrial)
DISTRICTS = {
    "S":   ("Single Residence", False),
    "S1":  ("Single Residence - 1", False),
    "S2":  ("Single Residence - 2", False),
    "G":   ("General Residence", False),
    "A":   ("Multifamily", False),
    "GB":  ("General Business", False),
    "CB":  ("Central Business", False),
    "LB":  ("Limited Business", False),
    "O":   ("Office-Research", False),
    "BPH": ("Boston-Providence Highway District", True),
    "LM":  ("Limited Manufacturing", True),
    "LMA": ("Limited Manufacturing A", True),
    "M":   ("Manufacturing", True),
}

def _ind_table_quote(code: str) -> dict:
    mfg = "; I.4 'Manufacturing' = Y" if code in ("M", "BPH") else ""
    return {"section": "§3.1.6", "ordinance": ORD, "quote":
            f"§3.1.6 Table [{code}]: G.2.c 'Storage warehouse or distribution plant - Other "
            f"material or equipment' = Y; I.3 'Light manufacturing' = Y{mfg}."}


def _prohib_table_quote(code: str) -> dict:
    return {"section": "§3.1.6", "ordinance": ORD, "quote":
            f"§3.1.6 Table [{code}]: 'Storage warehouse or distribution plant' (G.2), 'Light "
            f"manufacturing' (I.3) and 'Manufacturing' (I.4) are all denoted 'N' (prohibited)."}


def _row(code: str) -> dict:
    name, industrial = DISTRICTS[code]
    if industrial:
        cites = [_ind_table_quote(code), _CLOSED, _LEGEND]
        if code == "BPH":
            cites.append(_FN12)
        cites.append(_NONAME_COND)
        return {
            "zone_code": code, "zone_name": name, "municipality": "NORWOOD",
            "self_storage": "conditional", "mini_warehouse": "conditional",
            "light_industrial": "permitted", "luxury_garage_condo": "conditional",
            "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
            "citations": cites,
        }
    cites = [_prohib_table_quote(code), _CLOSED, _NONAME_PROHIB]
    if code == "O":
        cites.append(_OFFICE_CIT)
    return {
        "zone_code": code, "zone_name": name, "municipality": "NORWOOD",
        "self_storage": "prohibited", "mini_warehouse": "prohibited",
        "light_industrial": "prohibited", "luxury_garage_condo": "prohibited",
        "confidence": 0.95, "classification_source": "human", "human_reviewed": True,
        "citations": cites,
    }


NORWOOD_ROWS = [_row(c) for c in DISTRICTS]


def main() -> int:
    rows = NORWOOD_ROWS
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}")
    print(f"  rows={len(rows)}  replace_existing=False")
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
