"""New Britain Township (BUCKS County PA) — self-storage verdicts from Ch. 27 Zoning.

Source: Township of New Britain Code, Ch. 27 Zoning (eCode360 NE0937; through 2025). PA
name-bound to Bucks jid — NO rebind. municipality='New Britain Township' (== parcels.city).

The ordinance has a DISTINCT named self-storage use — J25 Self-Storage ("Warehouse/storage
units ... under month-to-month lease ... Mini-warehouses and warehouse buildings ...") — assigned
per-district in the Part-4/5 Use Regulations (a./b./c. = by right / special exception /
conditional use). Because J25 is named separately from K3 Wholesale Storage/Warehousing, the
warehouse-by-right convention does NOT override an explicit J25 exclusion (#37/#58): ss/mw follows
J25's placement.

By district (verified):
- C-1 (§27-1201), C-2 (§27-1301), OP (§27-1501): J25 = Uses Permitted by Conditional Use => ss/mw
  CONDITIONAL. (OP also lists warehousing by right => li permitted; C-1/C-2 do not => li prohibited.)
- I Industrial (§27-1701) + IO Industrial/Office (§27-1801): J25 = Uses Permitted by Right => ss/mw
  PERMITTED; li permitted.
- C-3 (§27-1401): J25 ABSENT from the use list (closed list §27-1401.D "not listed = not permitted")
  => ss/mw PROHIBITED; but K3 'Wholesale Business, Wholesale Storage, and Warehousing' is by right
  => li PERMITTED.
- IN (§27-1601) = Institutional (catch #38, J25 absent) => prohibited. All residential
  (RR/SR-1/SR-2/MHP/WS/VR/CR/CC) => prohibited.

luxury_garage_condo: no garage-condominium use named (sweep=0) => PROHIBITED everywhere.

Needle (ss/mw permitted|conditional + wealth gate): C-1 2 + C-2 1 + OP 2 = 5 (I/IO by right but
0 wealth-lots; C-3's 29 wealth-lots are li-only, J25 not permitted there).
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import admin_headers  # noqa: E402

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"
URL = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{JID}/_upload-matrix-rows"
MUNI = "New Britain Township"
ORD = "Township of New Britain Code, Ch. 27 Zoning (eCode360 NE0937)"

_COND = {"section": "§27-1201/1301/1501 (C-1/C-2/OP)", "ordinance": ORD, "quote":
    "'J25 Self-Storage' listed under 'c. Uses Permitted by Conditional Use' => ss/mw conditional."}
_OP_LI = {"section": "§27-1501 (OP)", "ordinance": ORD, "quote":
    "OP: J25 Self-Storage = Conditional Use (ss/mw conditional); warehousing use listed by right => li permitted."}
_IND = {"section": "§27-1701/1801 (I / IO)", "ordinance": ORD, "quote":
    "I Industrial / IO Industrial-Office: 'J25 Self-Storage' under 'a. Uses Permitted by Right' => ss/mw permitted; li permitted."}
_C3 = {"section": "§27-1401 (C-3)", "ordinance": ORD, "quote":
    "C-3 by-right lists 'K3 Wholesale Business, Wholesale Storage, and Warehousing' (=> li permitted) but "
    "NOT J25 Self-Storage; §27-1401.D 'not listed = not permitted' => ss/mw prohibited."}
_INST = {"section": "§27-1601 (IN)", "ordinance": ORD, "quote":
    "IN = Institutional District (catch #38); J25 Self-Storage not listed => ss/mw/li prohibited."}
_PROHIB = {"section": "Ch.27 use lists", "ordinance": ORD, "quote":
    "Residential/other district — J25 Self-Storage and warehousing/manufacturing uses not listed; "
    "closed list ('not listed = not permitted') => ss/mw/li prohibited."}
_LGC = {"section": "Ch.27 (sweep)", "ordinance": ORD, "quote":
    "No luxury-garage-condominium / garage-condo use named anywhere (sweep=0); unnamed => prohibited."}

V = {
    "C-1": ("conditional", "conditional", "prohibited", [_COND, _LGC]),
    "C-2": ("conditional", "conditional", "prohibited", [_COND, _LGC]),
    "OP":  ("conditional", "conditional", "permitted", [_OP_LI, _LGC]),
    "I":   ("permitted", "permitted", "permitted", [_IND, _LGC]),
    "IO":  ("permitted", "permitted", "permitted", [_IND, _LGC]),
    "C-3": ("prohibited", "prohibited", "permitted", [_C3, _LGC]),
    "IN":  ("prohibited", "prohibited", "prohibited", [_INST, _LGC]),
}
for z in ["RR", "SR-1", "SR-2", "MHP", "WS", "VR", "CR", "CC"]:
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
