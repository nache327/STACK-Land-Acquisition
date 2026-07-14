"""Warrington Township (BUCKS County PA) — self-storage verdicts from Ch. 370 Zoning.

Source: Township of Warrington Code, Ch. 370 Zoning (eCode360 WA0807; 2021-O-04). PA name-bound
to Bucks jid — NO rebind. municipality='Warrington Township' (== parcels.city).

Distinct named uses: E19 Mini warehouses + E20 Limited-access self-storage facility. Per the
per-district "the following uses are permitted by right" lists, E19 AND E20 are BY RIGHT in:
CR Commercial Residential, PI-1, PI-1A, PI-2 Planned Industrial. The use-matrix row confirms
'E19 P P P P' / 'E20 P P P P' (exactly those 4 districts; no other district lists them, incl.
BZ / CBD / OI / Q / IST / IU) => ss/mw PERMITTED only in those 4; prohibited elsewhere.

Parcel zoning_code renders the Planned Industrial districts as Pl-1 / Pl-1A / Pl-2 (capital-I
shown as lowercase-l) plus PI-2 => all map to PI-1/PI-1A/PI-2 (ss/mw permitted, li permitted).
CR permits E19/E20 by right (ss/mw permitted) but is Commercial-Residential (no general
industrial use => li prohibited).

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw permitted + wealth gate): Pl-1 17 + Pl-1A 5 + Pl-2 2 + PI-2 1 = 25 (CR 0).
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Warrington Township"
ORD = "Township of Warrington Code, Ch. 370 Zoning (eCode360 WA0807, 2021)"

_PI = {"section": "Ch.370 PI-1/PI-1A/PI-2 (by right)", "ordinance": ORD, "quote":
    "Planned Industrial 'the following uses are permitted by right: ... E19 Mini warehouses; E20 "
    "Limited-access self-storage facility' => ss/mw permitted; industrial uses by right => li permitted."}
_CR = {"section": "Ch.370 CR (by right)", "ordinance": ORD, "quote":
    "CR Commercial Residential permits by right 'E19 Mini warehouses' + 'E20 Limited-access "
    "self-storage facility' => ss/mw permitted; no general industrial use => li prohibited."}
_PROHIB = {"section": "Ch.370 use matrix", "ordinance": ORD, "quote":
    "Use matrix: E19/E20 marked 'P' only in CR/PI-1/PI-1A/PI-2 (this district blank) => ss/mw "
    "prohibited; no mini-warehouse/self-storage use permitted here."}
_LGC = {"section": "Ch.370 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {
    "Pl-1":  ("permitted", "permitted", "permitted", [_PI, _LGC]),
    "Pl-1A": ("permitted", "permitted", "permitted", [_PI, _LGC]),
    "Pl-2":  ("permitted", "permitted", "permitted", [_PI, _LGC]),
    "PI-2":  ("permitted", "permitted", "permitted", [_PI, _LGC]),
    "CR":    ("permitted", "permitted", "prohibited", [_CR, _LGC]),
}
for z in ["BZ", "CBD", "CE", "EV", "IST", "IU", "J", "MR", "OI", "OS/P", "Q",
          "R-1C", "R1", "R2", "R2-I", "R3", "RA", "RA-2", "WV"]:
    V[z] = ("prohibited", "prohibited", "prohibited", [_PROHIB, _LGC])

ROWS = [{"zone_code": z, "zone_name": z, "municipality": MUNI, "self_storage": ss,
         "mini_warehouse": mw, "light_industrial": li, "luxury_garage_condo": "prohibited",
         "confidence": 0.95, "classification_source": "human", "human_reviewed": True, "citations": c}
        for z, (ss, mw, li, c) in V.items()]


def main() -> int:
    print(f"POST rows={len(ROWS)} muni={MUNI}")
    for r in ROWS:
        if r["self_storage"] != "prohibited" or r["light_industrial"] != "prohibited":
            print(f"  {r['zone_code']:6} ss={r['self_storage']:11} mw={r['mini_warehouse']:11} li={r['light_industrial']}")
    resp = httpx.post(URL, json={"rows": ROWS, "replace_existing": False}, headers=admin_headers(), timeout=120.0)
    print(f"HTTP {resp.status_code}: {resp.text[:260]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
