"""West Chester Borough (CHESTER County PA) — self-storage verdicts from Ch. 112 Zoning.

Source: Borough of West Chester Code, Ch. 112 Zoning (eCode360 WE0442; amended in full 2021). PA
name-bound to Chester jid — NO rebind. municipality='West Chester Borough' (== parcels.city).

Named use "Mini storage". Two use tables (columns NC-1/NC-2/NC-3/MU/TC/CS/ID/IS/PUC):
- Principal uses (permitted by right): '27. Mini storage' = X in ID only => ss/mw PERMITTED in ID.
- Special Exception Uses: '9. Mini storage; wholesale storage' = X in CS only => ss/mw
  CONDITIONAL in CS.
Mini storage is a distinct named use; where a district's tables omit it, it is prohibited
(named-separately from warehousing => convention does not add it). ID / IS are the industrial
districts (light industrial by right) => li permitted there.

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw permitted|conditional + wealth gate): ID 4 + CS 6 = 10.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "West Chester Borough"
ORD = "Borough of West Chester Code, Ch. 112 Zoning (eCode360 WE0442, 2021)"

_ID = {"section": "Ch.112 principal-use table (ID)", "ordinance": ORD, "quote":
    "Principal uses permitted by right, '27. Mini storage' = X in the ID column => ss/mw permitted; "
    "ID is an industrial district (light industrial by right) => li permitted."}
_CS = {"section": "Ch.112 Special Exception Uses (CS)", "ordinance": ORD, "quote":
    "Special Exception Uses table, '9. Mini storage; wholesale storage' = X in the CS column "
    "(permitted by special exception) => ss/mw conditional."}
_IS = {"section": "Ch.112 (IS)", "ordinance": ORD, "quote":
    "IS Industrial: 'Mini storage' not marked in either use table (named separately from "
    "warehousing) => ss/mw prohibited; industrial uses by right => li permitted."}
_PROHIB = {"section": "Ch.112 use tables", "ordinance": ORD, "quote":
    "'Mini storage' not marked in this district's column in either the principal-use or "
    "special-exception table => ss/mw prohibited; no industrial use by right => li prohibited."}
_LGC = {"section": "Ch.112 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {
    "ID": ("permitted", "permitted", "permitted", [_ID, _LGC]),
    "CS": ("conditional", "conditional", "prohibited", [_CS, _LGC]),
    "IS": ("prohibited", "prohibited", "permitted", [_IS, _LGC]),
}
for z in ["NC-1", "NC-2", "NC-3", "MU", "TC", "PUC"]:
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
