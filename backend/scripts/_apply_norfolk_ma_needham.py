"""Needham MA (Norfolk County) — Stage-4 close. Route-128 industrial needle; verdict-only.

Source: Town of Needham Zoning By-Law (needhamma.gov DocumentCenter/View/16644, printed
Nov 2025 — CURRENT). §2 Classes of Districts; §3.2 Schedule of Use Regulations
(§3.2.1 RRC/SRA/SRB/GR/A/I(Institutional)/IND/IND-1 grid; §3.2.2 B/CSB/CB/ASB/HAB grid;
§3.2.3 NB; §3.2.4 NEBC; §3.2.5 HC-128; §3.2.6 MU-128; §3.2.7 HC-1 "Permitted Uses" lists).

NO REBIND (Hudson lesson): MAPC's Needham layer is STALE — it lacks the current Route-128
corridor districts (HC-128, MU-128, NEBC, HC-1) + A-3/AHD/ES; a MAPC rebind would misplace
the corridor parcels. The town assessor codes ALREADY carry the current scheme (IND1, M128,
H128, NEBC, etc.), and no public current town-GIS layer was found — so verdicts are keyed
to the existing parcel codes, mapped to the current-bylaw district each represents.
municipality='NEEDHAM' (== parcels.city, UPPERCASE, 9,783 parcels).

NAMED grounding (#37/#58): li=permitted rests on NAMED by-right uses — §3.2.1 'Wholesale
distribution facilities or storage in an enclosed structure' = Y in IND/IND-1; §3.2.4.1(e)/
§3.2.6.1(i) 'Wholesale distribution facilities in an enclosed structure' + 'Light non-nuisance
manufacturing' by-right in NEBC/MU-128. NO named self-service-storage / mini-warehouse use
anywhere (whole-doc sweep = 0) -> ss/mw are the unnamed enclosed-storage cohort: CONDITIONAL
where enclosed-storage/wholesale-distribution is by-right (IND-1/MU-128/NEBC), else prohibited.

Needle districts (assessor->bylaw): IND1->IND-1, M128->MU-128, NEBC->NEBC (ss/mw conditional,
li permitted, lgc conditional). H128->HC-128 (labs/incidental-mfg only, no warehouse -> li
conditional, ss/mw prohibited). Business B/HAB/ASB: warehouse/mfg only by SP -> li conditional,
ss/mw prohibited. I=Institutional, NB/CSB/CB, all residential (SRA/SRB/GR/A/A1/A2/R1) -> all
prohibited. ESCALATED to outputs/_exceptions_B.md: assessor 'C' (20 parcels, undecodable);
'FP' Flood-Plain overlay skipped (overlay, no base verdict). POST /_upload-matrix-rows.
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
ORD = ("Town of Needham Zoning By-Law (needhamma.gov DocumentCenter/View/16644, printed Nov 2025); "
       "§3.2 Schedule of Use Regulations")

# ---- citation fragments (verbatim, <=200 chars) ----
_IND = {"section": "§3.2.1 Schedule", "ordinance": ORD, "quote":
    "§3.2.1 Schedule: 'Wholesale distribution facilities or storage in an enclosed structure' = Y "
    "(by right) in IND and IND-1; 'Light non-nuisance manufacturing' = Y. (N=prohibited)"}
_MU128 = {"section": "§3.2.6.1", "ordinance": ORD, "quote":
    "§3.2.6.1 Mixed Use-128 Permitted Uses: (i) 'Wholesale distribution facilities in an enclosed "
    "structure' + (l) 'Light non-nuisance manufacturing' — by right."}
_NEBC = {"section": "§3.2.4.1", "ordinance": ORD, "quote":
    "§3.2.4.1 New England Business Center Permitted Uses: (e) 'Wholesale distribution facilities in an "
    "enclosed structure' + (h) 'Light non-nuisance manufacturing' — by right."}
_HC128 = {"section": "§3.2.5.1", "ordinance": ORD, "quote":
    "§3.2.5.1 Highland Commercial-128 Permitted Uses: medical/R&D laboratory + manufacturing incidental "
    "to retail (by right); NO warehouse / general light-manufacturing use listed."}
_SSCONV = {"section": "§3.2 (whole-doc sweep)", "ordinance": ORD, "quote":
    "No named self-service-storage / mini-warehouse use (catch-#58 sweep=0). Enclosed-storage / wholesale-"
    "distribution is by-right here -> ss/mw CONDITIONAL (enclosed-storage cohort), not permitted."}
_SSPROHIB = {"section": "§3.2 (whole-doc sweep)", "ordinance": ORD, "quote":
    "No named self-service-storage / mini-warehouse use (catch-#58 sweep=0); no by-right warehouse/enclosed-"
    "storage use in this district -> closed-list prohibits ss/mw."}
_LGC = {"section": "§3.2.1", "ordinance": ORD, "quote":
    "No named garage-condominium use; §3.2.1 'Commercial garage for the storage or repair of vehicles' = SP "
    "(IND) + enclosed-storage by-right anchor -> luxury garage-condo CONDITIONAL."}
_BUS = {"section": "§3.2.2 Schedule", "ordinance": ORD, "quote":
    "§3.2.2 Schedule: 'Wholesale distribution facilities or storage' + 'Light non-nuisance manufacturing' "
    "= SP (special permit), not by-right, in B/HAB (ASB warehouse=N); commercial garage = SP in B."}
_PROHIB = {"section": "§3.2 Schedule", "ordinance": ORD, "quote":
    "§3.2 Schedule: warehouse/storage, manufacturing and wholesale-distribution uses are all 'N' (not "
    "permitted) in this district."}

# code -> (zone_name, ss, mw, li, lgc, [citations])
V = {}
def res(code, name): V[code]=(name,"prohibited","prohibited","prohibited","prohibited",[_PROHIB])
for c,n in [("SRA","Single Residence A"),("SRB","Single Residence B"),("GR","General Residence"),
            ("A","Apartment A-1"),("A1","Apartment A-1"),("A2","Apartment A-2"),
            ("R1","Residential (single-residence)"),("I","Institutional"),
            ("NB","Neighborhood Business"),("CS","Chestnut Street Business (CSB)"),
            ("CB","Center Business")]:
    res(c,n)
# business with SP light-industrial (li conditional; ss/mw prohibited)
# lgc prohibited (not conditional): ss+mw prohibited here (warehouse only SP), so the
# garage-condo inference sibling must not exceed them (catch-#58 sibling-consistency).
V["B"]   = ("Business","prohibited","prohibited","conditional","prohibited",[_BUS,_SSPROHIB])
V["BUS"] = ("Business","prohibited","prohibited","conditional","prohibited",[_BUS,_SSPROHIB])
V["AS"]  = ("Avery Square Business (ASB)","prohibited","prohibited","conditional","prohibited",[_BUS,_SSPROHIB])
V["HA"]  = ("Hillside Avenue Business (HAB)","prohibited","prohibited","conditional","prohibited",[_BUS,_SSPROHIB])
# needle districts
V["IND1"] = ("Industrial-1 (IND-1)","conditional","conditional","permitted","conditional",[_IND,_SSCONV,_LGC])
V["M128"] = ("Mixed Use-128 (MU-128)","conditional","conditional","permitted","conditional",[_MU128,_SSCONV,_LGC])
V["NEBC"] = ("New England Business Center (NEBC)","conditional","conditional","permitted","conditional",[_NEBC,_SSCONV,_LGC])
V["H128"] = ("Highland Commercial-128 (HC-128)","prohibited","prohibited","conditional","prohibited",[_HC128,_SSPROHIB])


def _row(code):
    name,ss,mw,li,lgc,cites = V[code]
    return {"zone_code": code, "zone_name": name, "municipality": "NEEDHAM",
            "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
            "luxury_garage_condo": lgc, "confidence": 0.9,
            "classification_source": "human", "human_reviewed": True, "citations": cites}


NEEDHAM_ROWS = [_row(c) for c in V]


def main() -> int:
    rows = NEEDHAM_ROWS
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
