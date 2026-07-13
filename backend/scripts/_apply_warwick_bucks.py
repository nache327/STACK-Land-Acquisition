"""Warwick Township (BUCKS County PA) — self-storage verdicts from Ch. 195 Zoning.

Source: Township of Warwick Code, Ch. 195 Zoning (eCode360 WA1313; adopted Ord. 2010-8,
12/20/2010, w/ amendments). Whole-chapter parsed via eCode print endpoint. PA name-bound to
Bucks jid — NO rebind. municipality='Warwick Township' (== parcels.city, mixed-case).
(catch #38 verified: WA1313 = Warwick Twp BUCKS, warwick-bucks.com; district codes RA/LI/
C-1/C-2/C-3/O/MF/RR/RG match parcels.)

Coded per-district lists: "A. Uses permitted by right / B. conditional use / C. special
exception". Use codes: G28 Miniwarehouse (= self-storage/mini-warehouse); H3 Wholesale
Business/Wholesale Storage/Warehousing + light-manufacturing/flex (= light_industrial).

ss/mw GROUNDED by NAMED use 'G28 Miniwarehouse':
  C-2, C-3 (Commercial): permitted BY RIGHT (verbatim "A. Uses permitted by right: ... G28
    Miniwarehouse") -> PERMITTED.
  C-1: conditional use -> conditional.  LI (Limited Industrial): special exception -> conditional.
  Every other district omits G28 -> prohibited (catch-#58 closed-list sweep).
li: permitted in LI/C-1/C-2/C-3/O (H3 warehousing/wholesale + flex by-right); prohibited elsewhere.
luxury_garage_condo: no garage-condo use named in Ch. 195 (sweep=0) -> PROHIBITED everywhere
  (unnamed; no by-inference; must not exceed ss).

Needle: LI (72 wealth-lots) + C-3 (14) + C-1 (14) + C-2 (8) + O(li). POST /_upload-matrix-rows.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Warwick Township"
ORD = "Township of Warwick Code, Ch. 195 Zoning (eCode360 WA1313; Ord. 2010-8)"

_BYRIGHT = {"section": "Ch.195 (C-2/C-3)", "ordinance": ORD, "quote":
    "C-2/C-3 Commercial, 'A. Uses permitted by right: ... G28 Miniwarehouse ...' -> self-storage "
    "permitted by right. (G28 = warehouse/storage units rented to the public.)"}
_COND = {"section": "Ch.195 (C-1)", "ordinance": ORD, "quote":
    "C-1 Commercial, 'B. Uses permitted by conditional use: ... G28 Miniwarehouse' -> self-storage conditional."}
_LI_SE = {"section": "Ch.195 (LI)", "ordinance": ORD, "quote":
    "LI Limited Industrial, 'C. Uses permitted by special exception: ... G28 Miniwarehouse' -> conditional; "
    "'A. Uses permitted by right' includes H3 Wholesale Business/Storage/Warehousing -> li permitted."}
_LI_R = {"section": "Ch.195", "ordinance": ORD, "quote":
    "'A. Uses permitted by right' in this district includes H3 Wholesale Storage/Warehousing and/or "
    "light-manufacturing/flex-space -> light_industrial permitted."}
_LGC = {"section": "Ch.195 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere in Ch. 195 (sweep=0); unnamed -> "
    "prohibited (no by-inference)."}
_PROHIB = {"section": "Ch.195 use lists", "ordinance": ORD, "quote":
    "This district's use lists (permitted by right / conditional use / special exception) omit G28 "
    "Miniwarehouse and warehouse/manufacturing uses -> closed-list prohibits ss/mw/li."}

V = {
    "C-2": ("permitted","permitted","permitted",[_BYRIGHT,_LI_R,_LGC]),
    "C-3": ("permitted","permitted","permitted",[_BYRIGHT,_LI_R,_LGC]),
    "C-1": ("conditional","conditional","permitted",[_COND,_LI_R,_LGC]),
    "LI":  ("conditional","conditional","permitted",[_LI_SE,_LGC]),
    "O":   ("prohibited","prohibited","permitted",[_LI_R,_PROHIB,_LGC]),
}
for z in ["RR","RA","R-1","R-1A","R-2","MF-1","MF-2","RG","MHP","VC","VC-2","AG-1"]:
    V[z] = ("prohibited","prohibited","prohibited",[_PROHIB,_LGC])

ROWS = [{"zone_code": z, "zone_name": z, "municipality": MUNI, "self_storage": ss,
         "mini_warehouse": mw, "light_industrial": li, "luxury_garage_condo": "prohibited",
         "confidence": 0.93, "classification_source": "human", "human_reviewed": True, "citations": c}
        for z,(ss,mw,li,c) in V.items()]


def main() -> int:
    print(f"POST rows={len(ROWS)} muni={MUNI}")
    for r in ROWS:
        if r["self_storage"]!="prohibited" or r["light_industrial"]!="prohibited":
            print(f"  {r['zone_code']:4} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} li={r['light_industrial']}")
    resp = httpx.post(URL, json={"rows": ROWS, "replace_existing": False}, headers=admin_headers(), timeout=120.0)
    print(f"HTTP {resp.status_code}: {resp.text[:280]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
