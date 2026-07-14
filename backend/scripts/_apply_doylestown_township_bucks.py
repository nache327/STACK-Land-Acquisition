"""Doylestown Township (BUCKS County PA) — self-storage verdicts from Ch. 175 Zoning.

Source: Township of Doylestown Code, Ch. 175 Zoning (eCode360 DO1312; current, LI amended
Ord. 413 12/19/2023). Whole-chapter parsed via eCode print endpoint. PA name-bound to Bucks
jid — NO rebind. municipality='Doylestown Township' (== parcels.city, mixed-case). Distinct
from the already-grounded Doylestown BOROUGH.

Per-district "§175-XX. Permitted uses. A. Uses by right / B. Uses by special exception /
D. Uses permitted by conditional use." Closed-list (Art. IV): "no building, structure or land
shall be used or occupied except for the purposes permitted in the zoning districts as
indicated herein." Use codes: G-3 Mini warehouse/mini storage (= self-storage); G-1
Manufacturing, G-15 Warehouse (= light_industrial).

CATCH #38: in Doylestown Twp 'I' and 'I-2' = INSTITUTIONAL districts (per §175-10), NOT
industrial. LI Limited Industrial is the industrial needle.

ss/mw GROUNDED by NAMED use 'G-3 Mini warehouse/mini storage' — appears as a Use BY RIGHT in
LI (§175-84.A verbatim) and Q (Quarry). No other district's use list permits G-3 (the C-2/VC
G-3 mentions in batch-1 recon were the OFF-STREET-PARKING ratio table, not a use permission —
corrected here). => ss/mw PERMITTED in LI and Q; prohibited everywhere else (closed-list #58).

li: LI + Q permit G-1 Manufacturing / G-15 Warehouse by right => permitted. C-1 permits G-15
Warehouse by special exception => conditional. All others prohibited.

luxury_garage_condo: no garage-condominium use named in Ch. 175 (sweep=0) => PROHIBITED
everywhere (unnamed; no by-inference; must not exceed ss).

Needle: LI (27 parcels; 16 wealth-lots). POST /_upload-matrix-rows.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Doylestown Township"
ORD = "Township of Doylestown Code, Ch. 175 Zoning (eCode360 DO1312; LI Ord. 413, 2023)"

_LI = {"section": "§175-84.A (LI)", "ordinance": ORD, "quote":
    "LI Limited Industrial, §175-84.A Uses by right: 'G-3 Mini warehouse/mini storage', 'G-1 "
    "Manufacturing', 'G-15 Warehouse' — 'shall be permitted' (by right)."}
_Q = {"section": "§175 (Q)", "ordinance": ORD, "quote":
    "Q Quarry District, Uses by right: 'G-3 Mini warehouse/mini storage' + G-1 Manufacturing / "
    "G-15 Warehouse (by right)."}
_C1 = {"section": "§175 (C-1)", "ordinance": ORD, "quote":
    "C-1 District: G-15 Warehouse permitted by special exception (=> li conditional); G-3 Mini "
    "warehouse NOT in the use list (the C-1/C-2/VC G-3 mentions are the parking-ratio table) => ss/mw prohibited."}
_LGC = {"section": "Ch.175 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere in Ch. 175 (sweep=0); unnamed "
    "=> prohibited (no by-inference)."}
_INST = {"section": "§175-10 (I/I-2)", "ordinance": ORD, "quote":
    "'I' and 'I-2' are INSTITUTIONAL Districts (§175-10 establishment), not industrial; G-3 Mini "
    "warehouse and G-1/G-15 industrial uses are not permitted => prohibited."}
_PROHIB = {"section": "Ch.175 use lists", "ordinance": ORD, "quote":
    "This district's use lists (Uses by right / special exception / conditional use) omit G-3 Mini "
    "warehouse and G-1/G-15 industrial uses => closed-list (Art. IV) prohibits ss/mw/li."}

V = {"LI": ("permitted","permitted","permitted",[_LI,_LGC]),
     "Q":  ("permitted","permitted","permitted",[_Q,_LGC]),
     "C-1": ("prohibited","prohibited","conditional",[_C1,_LGC]),
     "I":  ("prohibited","prohibited","prohibited",[_INST,_LGC]),
     "I-2": ("prohibited","prohibited","prohibited",[_INST,_LGC])}
for z in ["R-1","R-1A","R-2","R2","R2A","R2B","R-4","CR","C-2","C-3","C-4","VC"]:
    V[z] = ("prohibited","prohibited","prohibited",[_PROHIB,_LGC])

ROWS = [{"zone_code": z, "zone_name": z, "municipality": MUNI, "self_storage": ss,
         "mini_warehouse": mw, "light_industrial": li, "luxury_garage_condo": "prohibited",
         "confidence": 0.95, "classification_source": "human", "human_reviewed": True, "citations": c}
        for z,(ss,mw,li,c) in V.items()]


def main() -> int:
    print(f"POST rows={len(ROWS)} muni={MUNI}")
    for r in ROWS:
        if r["self_storage"]!="prohibited" or r["light_industrial"]!="prohibited":
            print(f"  {r['zone_code']:4} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} li={r['light_industrial']}")
    resp = httpx.post(URL, json={"rows": ROWS, "replace_existing": False}, headers=admin_headers(), timeout=120.0)
    print(f"HTTP {resp.status_code}: {resp.text[:260]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
