"""Summit UT Snyderville/Promontory — wave-6 pre-stage substrate apply.

Source pre-stage doc: backend/data/wave6_pre_stage/summit_park_city_corridor.json
on origin/adarench/wave6-prestage-extension2 (16 codes, all
Bergen-catchall-x4 prohibited per substrate-first halt rule).

JID: 72492dd8-eb36-4b69-b5ac-a2acdb671830 (Snyderville/Promontory, UT)

Live source codes (from FIRE) match substrate codes 1:1:
  AG-10, AG-20, AG-40, AG-5, AG-80, C, CC, HS, INDUS, LI, MR, NC, RC, RR, SC, TC

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

JID = "72492dd8-eb36-4b69-b5ac-a2acdb671830"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
SUBSTRATE_PATH = Path(__file__).resolve().parent.parent / "data" / "wave6_pre_stage" / "summit_park_city_corridor.json"


def main() -> int:
    if not SUBSTRATE_PATH.exists():
        sub = Path("/tmp/summit_substrate.json")
        if not sub.exists():
            print(f"substrate not found at {SUBSTRATE_PATH} or {sub}", file=sys.stderr)
            return 2
        rows = json.loads(sub.read_text())
    else:
        rows = json.loads(SUBSTRATE_PATH.read_text())

    for row in rows:
        row["municipality"] = "Snyderville/Promontory"

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
