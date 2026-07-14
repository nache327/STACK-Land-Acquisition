"""Yardley Borough (BUCKS County PA) — self-storage verdicts from Ch. 27 Zoning.

Source: Borough of Yardley Code, Ch. 27 Zoning (eCode360 YA0910). PA name-bound to Bucks jid —
NO rebind. municipality='Yardley Borough' (== parcels.city).

I-1 Industrial District §27-412 ("the following uses are permitted by right ... and no other"):
C. 'Ministorage. Such use shall include the storage of items ... within a warehouse structure as
miniwarehouse structures ...' => the NAMED self-storage use, permitted BY RIGHT => ss/mw
PERMITTED. D. 'Wholesale/Warehousing' + B. manufacturing/printing by right => li PERMITTED.
Ministorage appears only in I-1's use list => granted only there (C-1/C-2 are retail/auto
commercial with no storage use).

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw permitted + wealth gate): I-1 = 3.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Yardley Borough"
ORD = "Borough of Yardley Code, Ch. 27 Zoning (eCode360 YA0910)"

_I1 = {"section": "§27-412 (I-1)", "ordinance": ORD, "quote":
    "I-1 Industrial §27-412 'permitted by right ... and no other': C. Ministorage (miniwarehouse "
    "structures) => ss/mw permitted; D. Wholesale/Warehousing + B. manufacturing => li permitted."}
_PROHIB = {"section": "Ch.27 use lists", "ordinance": ORD, "quote":
    "This district's 'permitted by right ... and no other' list omits Ministorage and "
    "warehousing/manufacturing uses => ss/mw prohibited; li prohibited."}
_LGC = {"section": "Ch.27 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {"I-1": ("permitted", "permitted", "permitted", [_I1, _LGC])}
for z in ["C-1", "C-2", "R-1", "R-1A", "R-2", "R-2A", "R-3", "R-R", "TND"]:
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
