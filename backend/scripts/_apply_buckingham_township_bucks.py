"""Buckingham Township (BUCKS County PA) — self-storage verdicts from the Zoning Ordinance.

Source: Buckingham Township Zoning Ordinance (as amended to 09/22/21), Art. 4 §400/§405 Use
Regulations + per-district Articles. PA name-bound to Bucks jid — NO rebind.
municipality='Buckingham Township' (== parcels.city, mixed-case).

Closed list — Art. 4 §400: "in each district no building, structure or land shall be used or
occupied except for the purposes permitted in Section 405 and for the zoning districts so
indicated"; each district article repeats "used or occupied for any of the following uses and no
other." => unnamed uses PROHIBITED (#58 sweep).

NO named self-storage / mini-warehouse use anywhere in the ordinance (sweep=0). The only
industrial-use codes are G1 Manufacturing, G2 Research, **G3 Wholesale, Storage, Warehousing**,
G4-G15 (Art. 4 §405 §G "Industrial Uses"). ss/mw is UNNAMED — grounded by the established
**warehouse-permitted-by-right => ss/mw conditional** convention wherever G3 (a genuine
warehousing use) is by-right.

By-district (verified verbatim):
- **PI** Planned Industrial (Art. 29 §2901.A Uses Permitted By Right): G1 Manufacturing + **G3
  Wholesale, Storage, Warehousing** by right => li PERMITTED; ss/mw CONDITIONAL (warehouse conv.).
- **PI-2** Planned Industrial-2 (Art. 29-A §2901-A.A Uses Permitted By Right): G1 + **G3** by right
  => li PERMITTED; ss/mw CONDITIONAL.
- **AG-2** Agricultural-2: names G1 Manufacturing (tier not by-right-confirmed; ag district) — no
  G3 warehouse => li CONDITIONAL (named, conservative); ss/mw PROHIBITED (no warehouse by-right).
- **I** = INSTITUTIONAL District (CATCH #38 — NOT industrial; §noise-table classifies I under
  Commercial/Institutional), no G-codes => prohibited. **PC-1** (only G7 Crafts, no warehouse),
  **PC-2**, **LC**, **NVO** (office) => prohibited. All AG-1 / R-* / VR-* / VC-* / PBR / MHP /
  RA / RB residential/agricultural/village => prohibited.

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw conditional, >=1.5ac + dt10 HV>=475k + HHI>=100k): PI-2 25 + PI 17 = 42.
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "Buckingham Township"
ORD = "Buckingham Township Zoning Ordinance (amended to 09/22/2021), Art. 4 §405 + per-district Articles"

_PI = {"section": "Art. 29 §2901.A (PI)", "ordinance": ORD, "quote":
    "PI, §2901 Uses Permitted By Right: 'G1 Manufacturing' + 'G3 Wholesale, Storage, Warehousing' "
    "by right => li permitted; warehouse by-right => ss/mw conditional."}
_PI2 = {"section": "Art. 29-A §2901-A.A (PI-2)", "ordinance": ORD, "quote":
    "PI-2, §2901-A Uses Permitted By Right: 'G1 Manufacturing' + 'G3 Wholesale, Storage, "
    "Warehousing' by right => li permitted; warehouse by-right => ss/mw conditional."}
_AG2 = {"section": "AG-2 (Art. 4 §405 §G)", "ordinance": ORD, "quote":
    "AG-2 names 'G1 Manufacturing'; no G3 warehousing use => li conditional (named); ss/mw unnamed "
    "+ no warehouse by-right => prohibited."}
_INST = {"section": "I-Institutional", "ordinance": ORD, "quote":
    "'I' is the INSTITUTIONAL District (not Industrial; CATCH #38); use list names no G-series "
    "industrial use => ss/mw/li prohibited."}
_PC1 = {"section": "PC-1 (Art)", "ordinance": ORD, "quote":
    "PC-1 Planned Commercial permits only 'G7 Crafts' of the G-series — no warehousing/manufacturing "
    "=> li prohibited; ss/mw unnamed => prohibited."}
_PROHIB = {"section": "Art. 4 §400 (closed list)", "ordinance": ORD, "quote":
    "§400 closed list: land used only for purposes permitted in §405 for the district indicated; "
    "this district names no G1/G3 industrial or storage use => ss/mw/li prohibited."}
_LGC = {"section": "§405 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

# (ss, mw, li, citations)
V = {
    "PI":  ("conditional", "conditional", "permitted", [_PI, _LGC]),
    "PI-2": ("conditional", "conditional", "permitted", [_PI2, _LGC]),
    "AG-2": ("prohibited", "prohibited", "conditional", [_AG2, _LGC]),
    "I":   ("prohibited", "prohibited", "prohibited", [_INST, _LGC]),
    "PC-1": ("prohibited", "prohibited", "prohibited", [_PC1, _LGC]),
}
for z in ["AG-1", "PC-2", "LC", "NVO", "VR-1", "VR-3", "VC-1", "VC-2", "VC-3", "PBR", "MHP",
          "RA", "RB", "R-1", "R-2", "R-3", "R-4", "R-5", "R-6", "R-7", "R-8", "R-9"]:
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
