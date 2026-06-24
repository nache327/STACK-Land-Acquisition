"""Wilton CT - Bergen catchall x 4 substrate matrix apply.

Source pre-stage file: backend/data/wave6_pre_stage/fairfield_wilton.json
(on origin/adarench/wave6-prestage-extension2; not merged to main per
Wave-6 _APPLY_CLAIMS.md convention - apply happens via runtime POST).

12 zone codes from Wilton CT QDSGIS CT_Wilton_Adv_Viewer_Layers/
FeatureServer/13 (47 polygons, Description field, effective 10/29/2018).

Codes match DB-actual exactly (no hyphen-mismatch like Winnetka): codes
load via Description column verbatim into parcels.zoning_code + zoning_
districts.zone_code by perm_muni_wilton_ct_zoning.py fire.

JID: 05f76256-51a5-4785-9a3f-bc01f41b21f9 (Wilton, CT)
Codes (12): CRA-10 DE-10 DE-5 DRB DRD GB HOD R-1A R-2A SFAAHD THRD WC

Bergen catchall x 4 prohibited per substrate-first halt rule.
"Bias-against-unclear" default; no verdict-truth lift.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

JID = "05f76256-51a5-4785-9a3f-bc01f41b21f9"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"

SUBSTRATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "wave6_pre_stage"
    / "fairfield_wilton.json"
)


def main() -> int:
    if SUBSTRATE_PATH.exists():
        rows = json.loads(SUBSTRATE_PATH.read_text())
    else:
        # Substrate file lives on origin/adarench/wave6-prestage-extension2,
        # not on main. For local re-run, fetch via:
        #   git show origin/adarench/wave6-prestage-extension2:\
        #     backend/data/wave6_pre_stage/fairfield_wilton.json > /tmp/wilton.json
        path = Path("/tmp/fairfield_wilton.json")
        if not path.exists():
            print(
                "Substrate missing - fetch from origin/adarench/wave6-prestage-"
                "extension2:backend/data/wave6_pre_stage/fairfield_wilton.json",
                file=sys.stderr,
            )
            return 2
        rows = json.loads(path.read_text())

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
