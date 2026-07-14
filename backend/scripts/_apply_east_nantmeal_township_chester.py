"""East Nantmeal Township (CHESTER County PA) — self-storage verdicts from the 2011 Zoning Ordinance.

Source: East Nantmeal Township Zoning Ordinance of 2011 (town PDF, enant.wordpress.com). PA
name-bound to Chester jid — NO rebind. municipality='East Nantmeal Township' (== parcels.city).

Named use "Self-storage facilities": Article V "C Commercial District" §501 lists 'Self-storage
facilities' as a use permitted subject to Board-of-Supervisors conditional-use / special-exception
approval => ss/mw CONDITIONAL in C. Self-storage is a DISTINCT named use — the IA-1/IA-2
Industrial-Agricultural districts list 'Warehouse storage facilities' (a different use) as a
conditional use (Art. VI §601) => li conditional there, but self-storage is NOT listed in IA =>
ss/mw prohibited in IA (named-separately from warehouse; convention does not add it).

CATCH #38: EI = Educational/Institutional District (Art. VIII), NOT industrial => prohibited.
AP (Agricultural Preservation), AR, FRR, R-1, RA = agricultural/residential => prohibited.

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw conditional + wealth gate): C = 24 (IA-1/IA-2 li-only; EI institutional).
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "East Nantmeal Township"
ORD = "East Nantmeal Township Zoning Ordinance of 2011, Art. V (C) / Art. VI (IA) / Art. VIII (EI)"

_C = {"section": "Art. V §501 (C Commercial)", "ordinance": ORD, "quote":
    "C Commercial District §501 lists 'Self-storage facilities' as a use subject to conditional-use / "
    "special-exception approval => ss/mw conditional."}
_IA = {"section": "Art. VI §601 (IA-1/IA-2)", "ordinance": ORD, "quote":
    "IA conditional uses: 'Warehouse storage facilities' => li conditional; 'Self-storage facilities' "
    "(distinct use, listed only in C) not listed here => ss/mw prohibited."}
_EI = {"section": "Art. VIII (EI)", "ordinance": ORD, "quote":
    "EI = Educational/Institutional District (catch #38), not industrial; no self-storage or "
    "industrial use listed => ss/mw/li prohibited."}
_PROHIB = {"section": "2011 Ordinance use lists", "ordinance": ORD, "quote":
    "Agricultural/residential district (AP/AR/FRR/R-1/RA) — no self-storage or industrial use "
    "listed => ss/mw/li prohibited."}
_LGC = {"section": "2011 Ordinance (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {
    "C":    ("conditional", "conditional", "prohibited", [_C, _LGC]),
    "IA-1": ("prohibited", "prohibited", "conditional", [_IA, _LGC]),
    "IA-2": ("prohibited", "prohibited", "conditional", [_IA, _LGC]),
    "EI":   ("prohibited", "prohibited", "prohibited", [_EI, _LGC]),
}
for z in ["AP", "AR", "FRR", "R-1", "RA"]:
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
