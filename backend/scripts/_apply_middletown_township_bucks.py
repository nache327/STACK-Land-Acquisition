"""Middletown Township (BUCKS County PA) — self-storage verdicts from Ch. 500 Zoning.

Source: Township of Middletown Code, Ch. 500 Zoning (eCode360 MI2390; whole chapter via print
endpoint). PA name-bound to Bucks jid — NO rebind. municipality='Middletown Township'
(== parcels.city, mixed-case).

M-1 (Art. XIX §500-1902) is the MANUFACTURING district (catch #38: its use list is manufacturing/
warehousing/fuel-storage/trucking — Manufacturing, NOT Multifamily). Closed list — §500-1902.A:
"A building may be erected or used ... for any of the following purposes AND NO OTHER".

M-1 §500-1902 uses BY RIGHT include (7) Manufacturing and (8) "Wholesale storage, warehousing ..."
=> light_industrial PERMITTED. (18) "Mini warehouse when authorized by the Zoning Hearing Board as
a special exception" => the NAMED self-storage use, special exception => ss/mw CONDITIONAL.
"Mini warehouse" appears ONCE in Ch. 500 — M-1 only. No other district permits it => prohibited
elsewhere (closed-list #58).

luxury_garage_condo: no garage-condominium use named anywhere (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw conditional, >=1.5ac + dt10 HV>=475k + HHI>=100k): M-1 = 35.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Middletown Township"
ORD = "Township of Middletown Code, Ch. 500 Zoning (eCode360 MI2390)"

_M1 = {"section": "§500-1902.A (M-1)", "ordinance": ORD, "quote":
    "M-1 §500-1902.A (closed list 'and no other'): (7) Manufacturing + (8) Wholesale storage, "
    "warehousing by right => li permitted; (18) 'Mini warehouse ... special exception' => ss/mw conditional."}
_PROHIB = {"section": "Ch.500 use lists", "ordinance": ORD, "quote":
    "This district's use list omits 'Mini warehouse' and manufacturing/warehousing uses; closed-list "
    "(§...A 'and no other') => ss/mw/li prohibited."}
_LGC = {"section": "Ch.500 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {"M-1": ("conditional", "conditional", "permitted", [_M1, _LGC])}
for z in ["RA-1", "RA-2", "RA-3", "R-1", "R-2", "MHP", "AQC", "OR", "OC", "MR", "AO",
          "C", "P", "GB", "CS", "RC"]:
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
