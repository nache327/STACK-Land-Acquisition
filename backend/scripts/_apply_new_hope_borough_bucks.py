"""New Hope Borough (BUCKS County PA) — self-storage verdicts from Ch. 275 Zoning.

Source: Borough of New Hope Code, Ch. 275 Zoning (eCode360 NE2409). PA name-bound to Bucks jid
— NO rebind. municipality='New Hope Borough' (== parcels.city).

NO named self-storage/mini-warehouse use in Ch. 275 (only "warehousing and distribution",
§275-21A). LI Light Industrial District (§275-36, closed list "any one of the following uses and
no other"): (1) Uses by right (d) '§275-21A warehousing and distribution' by right => li
PERMITTED; warehouse by-right => ss/mw CONDITIONAL (established convention). §275-21A warehousing
is by-right ONLY in LI (other districts list it by special exception at most => no convention).

LI = "Light Industrial" (catch #38 cleared — genuine industrial, not multifamily).

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw conditional + wealth gate): LI = 8.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "New Hope Borough"
ORD = "Borough of New Hope Code, Ch. 275 Zoning (eCode360 NE2409)"

_LI = {"section": "§275-36 (LI)", "ordinance": ORD, "quote":
    "LI Light Industrial §275-36 closed list, (1) Uses by right (d) '§275-21A warehousing and "
    "distribution' by right => li permitted; warehouse by-right => ss/mw conditional (convention)."}
_PROHIB = {"section": "Ch.275 use lists", "ordinance": ORD, "quote":
    "No named self-storage anywhere; this district does not permit warehousing by right (SE at most) "
    "=> ss/mw prohibited; no manufacturing/warehousing by right => li prohibited."}
_LGC = {"section": "Ch.275 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {"LI": ("conditional", "conditional", "permitted", [_LI, _LGC])}
for z in ["CC", "HC", "LC", "MU", "PRD", "R-1", "R-2", "RA", "RB", "RC", "SC"]:
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
