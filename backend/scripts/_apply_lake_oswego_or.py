"""Lake Oswego OR — wave-6 pre-stage substrate apply.

Source pre-stage doc: backend/data/wave6_pre_stage/clackamas_lake_oswego.json
on origin/adarench/wave6-prestage-extension2 (29 codes, Bergen-catchall-x4
prohibited per substrate-first halt rule).

JID: 2c1736ee-48ac-4a6e-aefd-77be215a00c2 (Lake Oswego, OR)

Substrate 29 codes match live 29 codes 1:1.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

JID = "2c1736ee-48ac-4a6e-aefd-77be215a00c2"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"
SUBSTRATE_PATH = Path(__file__).resolve().parent.parent / "data" / "wave6_pre_stage" / "clackamas_lake_oswego.json"
SUBSTRATE_BRANCH = "origin/adarench/wave6-prestage-extension2"


def _load_substrate() -> list[dict]:
    if SUBSTRATE_PATH.exists():
        return json.loads(SUBSTRATE_PATH.read_text())
    rel = "backend/data/wave6_pre_stage/clackamas_lake_oswego.json"
    out = subprocess.check_output(["git", "show", f"{SUBSTRATE_BRANCH}:{rel}"], text=True)
    return json.loads(out)


def main() -> int:
    rows = _load_substrate()
    for row in rows:
        row["municipality"] = "Lake Oswego"

    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}")
    print(f"  rows={len(rows)}  replace_existing=False")
    print(f"  zone_codes={[r['zone_code'] for r in rows]}")
    r = httpx.post(URL, json=payload, timeout=180.0)
    print(f"\nHTTP {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2))
    except Exception:
        print(r.text)
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
