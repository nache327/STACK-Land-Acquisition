"""New Canaan CT — wave-6 pre-stage matrix substrate apply.

Pattern: backend/scripts/_apply_winnetka_il.py + _apply_westport_ct.py.

Source substrate: backend/data/wave6_pre_stage/fairfield_new_canaan.json
(authored by Orchestrator on origin/adarench/wave6-prestage-extension2,
copied to this branch for the apply).

Context: Agent 9 fired New Canaan via PR #364 fork branch
(adarench/new-canaan-fire) but their PR #364 fire-complete comment
incorrectly stated "Substrate apply — N/A" — `fairfield_new_canaan.json`
DOES exist in `backend/data/wave6_pre_stage/`. This script closes that
gap.

JID: 2580f226-70f4-4c7d-982f-3cbd2b1d7b5b (New Canaan, CT — per-muni
inside Fairfield County umbrella).

Path A — codes match. Substrate has 16 rows; prod live distinct list
has 16 uncovered codes (A-M, O-Q); exact match.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

JID = "2580f226-70f4-4c7d-982f-3cbd2b1d7b5b"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
SUBSTRATE = Path(__file__).resolve().parent.parent / "data" / "wave6_pre_stage" / "fairfield_new_canaan.json"


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
