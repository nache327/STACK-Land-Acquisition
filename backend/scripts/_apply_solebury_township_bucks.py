"""Solebury Township (BUCKS County PA) — self-storage verdicts from Ch. 27 Zoning.

Source: Township of Solebury Code, Ch. 27 Zoning (eCode360 SO1688; through 11/6/2025). PA
name-bound to Bucks jid — NO rebind. municipality='Solebury Township' (== parcels.city).

LI Light Industrial District: closed list ("A building may be erected ... for any of the
following uses and no other"): A. Permitted Principal Uses (1) Manufacturing, fabricating and
assembly ... (5) "Warehouse; truck terminal; mini-warehouse". The NAMED self-storage use
(mini-warehouse) is a Permitted Principal Use (by right) => ss/mw PERMITTED; manufacturing +
warehouse by right => li PERMITTED. Mini-warehouse appears only in LI's use list (+ its §W
supplemental standards + the definition) — no other district grants it => prohibited elsewhere.

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw permitted, >=1.5ac + dt10 HV>=475k + HHI>=100k): LI = 8.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Solebury Township"
ORD = "Township of Solebury Code, Ch. 27 Zoning (eCode360 SO1688)"

_LI = {"section": "Ch.27 LI (Permitted Principal Uses)", "ordinance": ORD, "quote":
    "LI Light Industrial closed list ('for any of the following uses and no other'): Permitted "
    "Principal Uses (5) 'Warehouse; truck terminal; mini-warehouse' + (1) Manufacturing => ss/mw + li permitted."}
_PROHIB = {"section": "Ch.27 use lists", "ordinance": ORD, "quote":
    "This district's use list omits 'mini-warehouse' and manufacturing/warehouse uses (granted only "
    "in LI); closed list => ss/mw/li prohibited."}
_LGC = {"section": "Ch.27 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {"LI": ("permitted", "permitted", "permitted", [_LI, _LGC])}
for z in ["RB", "RA", "RDC", "TNC", "RD", "VR", "OR", "R-1", "VR-C", "VC-1", "VC", "RC", "VC-C", "QA"]:
    V[z] = ("prohibited", "prohibited", "prohibited", [_PROHIB, _LGC])

ROWS = [{"zone_code": z, "zone_name": z, "municipality": MUNI, "self_storage": ss,
         "mini_warehouse": mw, "light_industrial": li, "luxury_garage_condo": "prohibited",
         "confidence": 0.95, "classification_source": "human", "human_reviewed": True, "citations": c}
        for z, (ss, mw, li, c) in V.items()]


def main() -> int:
    print(f"POST rows={len(ROWS)} muni={MUNI}")
    for r in ROWS:
        if r["self_storage"] != "prohibited" or r["light_industrial"] != "prohibited":
            print(f"  {r['zone_code']:5} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} li={r['light_industrial']}")
    resp = httpx.post(URL, json={"rows": ROWS, "replace_existing": False}, headers=admin_headers(), timeout=120.0)
    print(f"HTTP {resp.status_code}: {resp.text[:260]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
