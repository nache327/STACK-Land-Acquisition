"""Avon MA (Norfolk County) — Stage-4 close. Modest industrial (IND); verdict-only.

Source: Town of Avon Zoning By-Law, Ch. 255 (eCode360 AV1285; §255 Establishment of
Districts + Table of Use Regulations — Principal Uses; code date 2026-05-05, CURRENT).
NO rebind: Avon is SRPEDD region — MAPC returns 0 polygons — but parcels ARE coded, so
verdicts are keyed to the existing assessor codes -> current bylaw districts.
municipality='AVON' (== parcels.city, UPPERCASE).

Table of Use columns: RES R-25 | RES R-40 | GEN BUS | IND | COM | MU Low D | RES HD | BOD
| VOD. Symbols: Y = by right; SP = special permit; N = prohibited.

li PERMITTED in IND (assessor IND) — NAMED by-right uses: 'Place for manufacturing,
assembling or packaging' = Y (IND only); 'Wholesale business and storage in a roofed
structure' = Y (IND only); 'Printing, binding, publishing' = Y; 'Laboratory or research
facility' = Y. li CONDITIONAL in GEN BUS / COM / MU-LowD (only 'Space for manufacturing,
assembly, or packaging' / labs by-right or SP; full manufacturing + warehouse = N/SP).

ss/mw: NO named self-service-storage / mini-warehouse use (sweep=0). Warehouse-by-right
convention: 'Wholesale business and storage in a roofed structure' = Y in IND -> ss/mw
CONDITIONAL in IND; prohibited everywhere else (warehouse N). lgc: no named garage-condo;
IND warehouse-storage anchor -> conditional in IND, else prohibited.

Residential (RDA/RDB/RDV/RHD) -> all prohibited. Needle: IND (assessor IND, 134 parcels)
ss/mw conditional. POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("Town of Avon Zoning By-Law, Ch. 255 (eCode360 AV1285; code date 2026-05-05); "
       "Table of Use Regulations — Principal Uses")

_IND = {"section": "§255 Table of Use Regs", "ordinance": ORD, "quote":
    "§255 Table: 'Wholesale business and storage in a roofed structure' = Y (by right) in IND only; "
    "'Place for manufacturing, assembling or packaging' = Y in IND."}
_SS = {"section": "§255 Table (sweep)", "ordinance": ORD, "quote":
    "No named self-service-storage/mini-warehouse use (sweep=0). 'Wholesale business and storage in a "
    "roofed structure' by-right in IND -> ss/mw CONDITIONAL; N elsewhere."}
_LGC = {"section": "§255 Table", "ordinance": ORD, "quote":
    "No named garage-condo use; IND 'Wholesale business and storage in a roofed structure' by-right -> "
    "luxury garage-condo CONDITIONAL in IND, prohibited elsewhere."}
_BUS = {"section": "§255 Table of Use Regs", "ordinance": ORD, "quote":
    "§255 Table: 'Space for manufacturing, assembly, or packaging'=Y / 'Laboratory or research facility'"
    "=Y/SP in GEN BUS/COM/MU-LowD; 'Wholesale business and storage'=N -> li conditional, ss/mw prohibited."}
_PROHIB = {"section": "§255 Table of Use Regs", "ordinance": ORD, "quote":
    "Table of Use Regs: 'Wholesale business and storage', 'Place for manufacturing...' and industrial uses "
    "are all 'N' (prohibited) in this residential district."}

# assessor code -> (zone_name, ss, mw, li, lgc, [cites])
V = {}
for c,n in [("RDA","Residence District A"),("RDB","Residence District B"),
            ("RDV","Residence District V"),("RHD","Residential - High Density")]:
    V[c]=(n,"prohibited","prohibited","prohibited","prohibited",[_PROHIB])
V["IND"]=("Industrial","conditional","conditional","permitted","conditional",[_IND,_SS,_LGC])
V["BUS"]=("General Business (GEN BUS)","prohibited","prohibited","conditional","prohibited",[_BUS,_SS])
V["COM"]=("Commercial","prohibited","prohibited","conditional","prohibited",[_BUS,_SS])
V["MUL"]=("Mixed Use - Low Density","prohibited","prohibited","conditional","prohibited",[_BUS,_SS])
V["MUR"]=("Mixed Use (residential-oriented)","prohibited","prohibited","conditional","prohibited",[_BUS,_SS])


def _row(code):
    name,ss,mw,li,lgc,cites=V[code]
    return {"zone_code": code, "zone_name": name, "municipality": "AVON",
            "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
            "luxury_garage_condo": lgc, "confidence": 0.9,
            "classification_source": "human", "human_reviewed": True, "citations": cites}


AVON_ROWS = [_row(c) for c in V]


def main() -> int:
    rows = AVON_ROWS
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
