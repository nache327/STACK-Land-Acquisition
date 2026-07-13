"""Plumstead Township (BUCKS County PA) — self-storage verdicts from Ch. 27 Zoning.

Source: Township of Plumstead Code, Ch. 27 Zoning (eCode360 PL2424; current — LI district
Ord. 2025-01, 1/8/2025). PA parcels are spatially name-bound to the Bucks county jid — NO
rebind. Coded per-district use lists (§27-304 use-code definitions; §27-3xx per-district
"Uses Permitted by Right / Conditional Use / Special Exception"). Whole-chapter parsed via
the eCode print endpoint. municipality='Plumstead Township' (== parcels.city, mixed-case).

Use codes: G26 Miniwarehouse (= self-storage/mini-warehouse); H1 Manufacturing, H2 Research,
H3 Warehousing and Distribution, H13 Industrial Park, H16 Flex Space (= light_industrial).

ss/mw GROUNDED by NAMED use — 'G26 Miniwarehouse' appears in exactly ONE district's use list:
LI Light Industrial, as a Use Permitted by Special Exception (=> conditional). Every other
district's use list omits G26 (catch-#58 closed-list sweep: absent => prohibited).

li: LI permits H1/H2/H3/H13/H16 by right (=> permitted). C-2 Highway Commercial permits
H3 Warehousing by special exception (=> conditional). All others omit the H-codes (=> prohibited).

luxury_garage_condo: NO garage-condominium use named anywhere in Ch. 27 (sweep=0) => PROHIBITED
in every district (unnamed; no by-inference in human_reviewed; must not exceed ss).

Needle: LI (80 parcels) self-storage conditional (special exception). POST /_upload-matrix-rows.
"""
from __future__ import annotations

import json, sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Plumstead Township"
ORD = "Township of Plumstead Code, Ch. 27 Zoning (eCode360 PL2424; LI Ord. 2025-01)"

_LI_SS = {"section": "Ch.27 Part 17 (LI)", "ordinance": ORD, "quote":
    "LI Light Industrial District, Uses Permitted by Special Exception: 'G26 Miniwarehouse' "
    "(Ord. 2025-01). Special exception => conditional. G26 = warehouse/storage units for public rent."}
_LI_LI = {"section": "Ch.27 Part 17 (LI)", "ordinance": ORD, "quote":
    "LI Light Industrial District, Uses Permitted by Right: H1 Manufacturing, H2 Research, H3 "
    "Warehousing and Distribution, H13 Industrial Park, H16 Flex Space."}
_LGC = {"section": "Ch.27 (whole-chapter sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere in Ch. 27 (sweep=0); unnamed "
    "=> prohibited (no by-inference in human_reviewed)."}
_C2 = {"section": "Ch.27 (C-2)", "ordinance": ORD, "quote":
    "C-2 Highway Commercial District, Uses Permitted by Special Exception includes H3 Warehousing "
    "and Distribution (=> li conditional); G26 Miniwarehouse not listed => ss/mw prohibited."}
_PROHIB = {"section": "Ch.27 §27-304 use lists", "ordinance": ORD, "quote":
    "This district's use lists (Uses Permitted by Right/Conditional Use/Special Exception) omit "
    "G26 Miniwarehouse and the H1/H3/H13 industrial codes => closed-list prohibits ss/mw/li."}

# code -> (ss, mw, li, cites)
V = {"LI": ("conditional","conditional","permitted",[_LI_SS,_LI_LI,_LGC]),
     "C-2": ("prohibited","prohibited","conditional",[_C2,_LGC])}
for z in ["R-1","R-2","R-3","R-4","R-5","RO","RP","VR","VC","C-1","C-3","Q","MHP"]:
    V[z] = ("prohibited","prohibited","prohibited",[_PROHIB,_LGC])

ROWS = [{"zone_code": z, "zone_name": z, "municipality": MUNI,
         "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
         "luxury_garage_condo": "prohibited", "confidence": 0.93,
         "classification_source": "human", "human_reviewed": True, "citations": c}
        for z,(ss,mw,li,c) in V.items()]


def main() -> int:
    payload = {"rows": ROWS, "replace_existing": False}
    print(f"POST {URL}  rows={len(ROWS)}  muni={MUNI}")
    for r in ROWS:
        if r["self_storage"]!="prohibited" or r["light_industrial"]!="prohibited":
            print(f"  {r['zone_code']:4} ss={r['self_storage']:11} li={r['light_industrial']}")
    resp = httpx.post(URL, json=payload, headers=admin_headers(), timeout=120.0)
    print(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
