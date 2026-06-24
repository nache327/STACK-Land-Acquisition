"""Winnetka IL — Bergen catchall × 4 substrate matrix apply.

Source pre-stage doc: docs/AUDIT_NOTES/winnetka_il_matrix_prestaged.md
(commit ca43e9b). 10 base zoning codes from Winnetka Village Code Title
17 (Zoneomics + amlegal corroboration).

CRITICAL deviation from pre-stage doc: the live source
(ags.gisconsortium.org/.../VWN/.../MapServer/0) returns codes WITHOUT
hyphens (R1/R2/R3/R4/R5, B1/B2, C1/C2, D), so the prod parcels.zoning_code
values are NON-hyphenated. The pre-stage doc enumerated hyphenated
codes (R-1/R-2/...). This apply uses the DB-actual codes to ensure
matrix-match against parcels.zoning_code.

JID: d1c50553-1ec0-49b8-9e52-46186c200221 (Village of Winnetka, IL)
Codes (10): R1 R2 R3 R4 R5 B1 B2 C1 C2 D

Bergen catchall × 4 prohibited per substrate-first halt rule.
D Light Industrial flagged for verdict-truth queue addition post-apply.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations
import json, sys
import httpx

JID = "d1c50553-1ec0-49b8-9e52-46186c200221"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"

# (zone_code, chapter, district_name, hyphenated_for_citation)
ZONES = [
    ("R1", "17.28", "Single-Family Residential", "R-1"),
    ("R2", "17.24", "Single-Family Residential", "R-2"),
    ("R3", "17.20", "Single-Family Residential", "R-3"),
    ("R4", "17.16", "Single-Family Residential", "R-4"),
    ("R5", "17.12", "Single-Family Residential", "R-5"),
    ("B1", "17.32", "Multifamily Residential", "B-1"),
    ("B2", "17.36", "Multifamily Residential", "B-2"),
    ("C1", "17.40", "Neighborhood Commercial", "C-1"),
    ("C2", "17.44", "General Retail Commercial", "C-2"),
    ("D",  "17.48", "Light Industrial", "D"),
]

ORDINANCE_URL = "https://codelibrary.amlegal.com/codes/winnetka/latest/winnetka_il/0-0-0-25873"


def hardcap(s: str, cap: int = 200) -> str:
    if not s or len(s) <= cap:
        return s
    return s[:cap - 1] + "…"


def build_row(zone_code: str, chapter: str, district_name: str, ord_code: str) -> dict:
    return {
        "zone_code": zone_code,
        "zone_name": f"Winnetka {ord_code} ({district_name})",
        "municipality": "Winnetka",
        "self_storage": "prohibited",
        "mini_warehouse": "prohibited",
        "light_industrial": "prohibited",
        "luxury_garage_condo": "prohibited",
        "confidence": 0.86,
        "classification_source": "human",
        "human_reviewed": False,
        "notes": hardcap(
            f"Bergen catchall x4 prohibited per substrate-first halt rule. "
            f"Source code {zone_code} (ordinance {ord_code}) maps to Winnetka "
            f"Village Code Title 17 Chapter {chapter} ({district_name})."
        ),
        "citations": [
            {
                "section": hardcap(
                    "Winnetka IL Village Code Title 17 Zoning - Chapter 17.08 "
                    "Districts; Chapter 17.40 sec 17.40.020 default-prohibition"
                ),
                "quote": hardcap(
                    "Uses not specifically listed as permitted in a district's chapter "
                    "are prohibited per Winnetka Village Code (default-prohibition "
                    "pattern; uniform across districts)."
                ),
                "url": ORDINANCE_URL,
            },
            {
                "section": hardcap(
                    f"Winnetka Village Code Title 17 Chapter {chapter} - "
                    f"{ord_code} District ({district_name})"
                ),
                "quote": hardcap(
                    f"Self-storage facility, mini-warehouse, light industrial, and "
                    f"luxury garage condominium uses are not enumerated in the "
                    f"{ord_code} district permitted-use chapter."
                ),
                "url": ORDINANCE_URL,
            },
        ],
    }


def main() -> int:
    rows = [build_row(zc, ch, name, ord_code) for zc, ch, name, ord_code in ZONES]
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}")
    print(f"  rows={len(rows)}  replace_existing=False")
    print(f"  zone_codes={[r['zone_code'] for r in rows]}")
    r = httpx.post(URL, json=payload, timeout=120.0)
    print(f"\nHTTP {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2))
    except Exception:
        print(r.text)
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
