"""Hingham MA - Bergen catchall x 4 substrate matrix apply.

Source substrate (this PR): backend/data/wave6_pre_stage/plymouth_hingham.json
Authored fresh (no pre-stage existed) from PR #335 Plymouth MA acquisition
spec + PR #378 Hingham per-muni probe v2.

15 zone codes from MAPC Zoning Atlas v0.2 zoning_full layer 2, filter
muni='Hingham' (Hingham MA TOWN_ID=131, prefixed `131*`):

  Residential:  131RA  131RB  131RC  131RD  131RE
  Business:     131BA  131BB  131BR  131WB
  Office:       131OP
  Industrial:   131I   131IP  131LIP
  Open:         131OO  131WR

DB-actual codes from perm_muni_hingham_ma_zoning.py fire match the
substrate codes exactly (zone_code = zo_code verbatim from MAPC).

JID: 4208af9b-5a97-4ca8-9b77-43aac5b58fb2 (Hingham, MA)

Bergen catchall x 4 prohibited per substrate-first halt rule.
Industrial codes (131I, 131IP, 131LIP) flagged for verdict-truth queue
follow-up — MAPC zo_usede shows manufacturing / light industrial /
freight terminal allowed at source level, so `light_industrial=prohibited`
is conservative and should be re-litigated.

POST /api/jurisdictions/{JID}/_upload-matrix-rows  (replace_existing=false)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

JID = "4208af9b-5a97-4ca8-9b77-43aac5b58fb2"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
URL = f"{API_BASE}/api/jurisdictions/{JID}/_upload-matrix-rows"

SUBSTRATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "wave6_pre_stage"
    / "plymouth_hingham.json"
)


def main() -> int:
    if not SUBSTRATE_PATH.exists():
        print(f"Substrate missing at {SUBSTRATE_PATH}", file=sys.stderr)
        return 2

    rows = json.loads(SUBSTRATE_PATH.read_text())
    payload = {"rows": rows, "replace_existing": False}
    print(f"POST {URL}")
    print(f"  rows={len(rows)}  replace_existing=False")
    print(f"  zone_codes={[r['zone_code'] for r in rows]}")
    r = httpx.post(URL, json=payload, timeout=120.0)
    print(f"\nHTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
