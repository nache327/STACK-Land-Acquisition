"""Quincy MA (Norfolk County) — Stage-4 FULL close. Zero held cells. 12 districts.

Source: City of Quincy, Ch. 375 Zoning (eCode360 QU3125; §2.1 Establishment, §3.1 Use
Regulations, Appendix A Table of Use Regulations dated 2011-06-16 — the operative table
referenced by current §3.1.4; §8 special districts). MAPC-rebind first
(rebind_configs/quincy.json): ~20,912 parcels rebound 2026-07-09 (assessor RESA/BUSB/
QCZD.. + split-zone combos -> canonical RA/RB/RC/BA/BB/BC/IA/IB/OS/PUD/QCD-10/QCD-15),
matrix untouched.

CLOSED-LIST (§3.1): "No land shall be used and no structure shall be erected or used except
as set forth in the following Table of Use Regulations... Any building or use of premises
not herein expressly permitted is hereby prohibited." Symbols: Y=by right; N=prohibited;
PB/BA/CC = special permit (Planning Board / Board of Appeals / City Council) = conditional.

ss/mw AFFIRMATIVELY GROUNDED by NAMED+DEFINED use — Appendix A §H "Mini-storage warehouse"
(defined: "A facility at which individual self-service storage spaces are made available to
the public for rent"): RA=N RB=N RC=N BA=N BB=BA BC=BA IA=Y IB=Y. => permitted IA/IB,
conditional BB/BC, prohibited RA/RB/RC/BA.

li: Appendix A §I "Light manufacturing" IA/IB=Y; §H "Storage warehouse/building" IA/IB=Y;
"Distribution center/warehouse" BB=Y. => permitted IA/IB, conditional BB, prohibited
RA/RB/RC/BA/BC.

Special districts: OS (§8.2 open space/recreation only) -> all prohibited. QCD-10/QCD-15
(§8.3.2: all Appendix A uses allowed only by Planning Board special permit, minus a
prohibited list that does NOT include Mini-storage warehouse) -> all conditional. PUD
(§8.4.1: "All uses permitted by right or by special permit shall be allowed" via City
Council special permit) -> all conditional.

lgc: no named garage-condominium use; nearest anchor §H Mini-storage warehouse -> CONDITIONAL
where a storage anchor exists (BB/BC/IA/IB + QCD/PUD), prohibited RA/RB/RC/BA/OS.

Needle: IA/IB self-storage BY RIGHT. POST /_upload-matrix-rows (replace_existing=false).
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
ORD = ("City of Quincy, Ch. 375 Zoning (eCode360 QU3125); §3.1 Use Regulations + Appendix A "
       "Table of Use Regulations (2011-06-16); §8 special districts")

_MINI = {"section": "Appendix A §H", "ordinance": ORD, "quote":
    "Appendix A §H 'Mini-storage warehouse': RA=N RB=N RC=N BA=N BB=BA BC=BA IA=Y IB=Y "
    "(Y=by right; BA=special permit Board of Appeals; N=prohibited)."}
_MINI_DEF = {"section": "§ Definitions", "ordinance": ORD, "quote":
    "Defined: 'Mini-storage warehouse: A facility at which individual self-service storage "
    "spaces are made available to the public for rent.'"}
_LI = {"section": "Appendix A §H/§I", "ordinance": ORD, "quote":
    "Appendix A §I 'Light manufacturing' IA=Y IB=Y; §H 'Storage warehouse/building' IA=Y IB=Y; "
    "'Distribution center...delivery warehouse' BB=Y IA=Y IB=Y."}
_CLOSED = {"section": "§3.1", "ordinance": ORD, "quote":
    "§3.1: 'No land shall be used and no structure shall be erected or used except as set forth "
    "in the...Table of Use Regulations... Any use not herein expressly permitted is hereby "
    "prohibited.'"}
_OS = {"section": "§8.2.2", "ordinance": ORD, "quote":
    "§8.2.2: within an Open Space District 'no building or premises shall be used...for other "
    "than' parks/recreation/cemetery/open-space purposes -> ss/mw/li/lgc prohibited."}
_QCD = {"section": "§8.3.2", "ordinance": ORD, "quote":
    "§8.3.2: in Quincy Center Districts all Appendix A uses require a Planning Board special "
    "permit, minus a prohibited list; 'Mini-storage warehouse' is NOT on that list -> conditional."}
_PUD = {"section": "§8.4.1", "ordinance": ORD, "quote":
    "§8.4.1: within PUD districts 'All uses permitted by right or by special permit shall be "
    "allowed' by City Council special permit -> conditional."}
_LGC = {"section": "Appendix A §H", "ordinance": ORD, "quote":
    "No named garage-condominium use; nearest anchor §H 'Mini-storage warehouse' (individual "
    "self-service storage). Luxury garage-condo hybrid -> CONDITIONAL where a storage anchor exists."}

# code -> (zone_name, ss, mw, li, lgc, profile)
VERDICTS = {
    "RA": ("Residence A District", "prohibited", "prohibited", "prohibited", "prohibited", "res"),
    "RB": ("Residence B District", "prohibited", "prohibited", "prohibited", "prohibited", "res"),
    "RC": ("Residence C District", "prohibited", "prohibited", "prohibited", "prohibited", "res"),
    "BA": ("Business A District", "prohibited", "prohibited", "prohibited", "prohibited", "res"),
    "BB": ("Business B District", "conditional", "conditional", "conditional", "conditional", "bb"),
    "BC": ("Business C District", "conditional", "conditional", "prohibited", "conditional", "bc"),
    "IA": ("Industrial A District", "permitted", "permitted", "permitted", "conditional", "ind"),
    "IB": ("Industrial B District", "permitted", "permitted", "permitted", "conditional", "ind"),
    "OS": ("Open Space District", "prohibited", "prohibited", "prohibited", "prohibited", "os"),
    "PUD": ("Planned Unit Development District", "conditional", "conditional", "conditional", "conditional", "pud"),
    "QCD-10": ("Quincy Center District 10", "conditional", "conditional", "conditional", "conditional", "qcd"),
    "QCD-15": ("Quincy Center District 15", "conditional", "conditional", "conditional", "conditional", "qcd"),
}

_CITES = {
    "res": [_MINI, _CLOSED],
    "bb":  [_MINI, _LI, _CLOSED, _LGC],
    "bc":  [_MINI, _CLOSED, _LGC],
    "ind": [_MINI, _MINI_DEF, _LI, _CLOSED, _LGC],
    "os":  [_OS, _CLOSED],
    "pud": [_PUD, _MINI, _CLOSED],
    "qcd": [_QCD, _MINI, _CLOSED],
}


def _row(code: str) -> dict:
    name, ss, mw, li, lgc, prof = VERDICTS[code]
    return {
        "zone_code": code, "zone_name": name, "municipality": "QUINCY",
        "self_storage": ss, "mini_warehouse": mw,
        "light_industrial": li, "luxury_garage_condo": lgc,
        "confidence": 0.9, "classification_source": "human", "human_reviewed": True,
        "citations": _CITES[prof],
    }


QUINCY_ROWS = [_row(c) for c in VERDICTS]


def main() -> int:
    rows = QUINCY_ROWS
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}\n  rows={len(rows)}  replace_existing=False")
    for r in rows:
        print(f"  {r['zone_code']:7} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} "
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
