"""Westport CT — wave-6 pre-stage matrix substrate apply.

Pattern: backend/scripts/_apply_winnetka_il.py (PR #356 + tracker flip
PR #367).

Source substrate: backend/data/wave6_pre_stage/fairfield_westport.json
(authored by Orchestrator on origin/adarench/wave6-prestage-extension2,
copied to this branch for the apply).

JID: 0a142989-e2ea-4cbf-9c07-ba72d06d5ca4 (Westport, CT — per-muni inside
Fairfield County umbrella).

Path A — codes match. Substrate has 35 rows; prod live distinct list
has 33 uncovered codes; 2 substrate rows (IHZ, SV) accept-and-no-op
against parcels.zoning_code at apply time.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

JID = "0a142989-e2ea-4cbf-9c07-ba72d06d5ca4"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
SUBSTRATE = Path(__file__).resolve().parent.parent / "data" / "wave6_pre_stage" / "fairfield_westport.json"


def main() -> int:
    rows = json.loads(SUBSTRATE.read_text(encoding="utf-8"))
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}")
    print(f"  substrate={SUBSTRATE}")
    print(f"  rows={len(rows)}  replace_existing=False")
    print(f"  zone_codes={sorted({r['zone_code'] for r in rows})}")
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
