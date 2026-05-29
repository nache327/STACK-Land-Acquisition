"""ARCHIVED 2026-05-29 — one-shot cleanup, already applied.
See scripts/_archive/westampton/README.md.

Soft-delete the 16 Westampton matrix rows from the orphan jurisdiction
(fd74c349-1f6d-4941-9ce6-8b2002102303). They were applied here by
apply_westampton_zoning.py (v1) before we realised the real Westampton
parcels live inside Burlington County (d316fb43...). v2 re-applied
them at the Burlington jurisdiction with municipality='Westampton
township'; the v1 rows are now harmless dead weight.

DELETE here is the soft-delete tombstone path (deleted_at = now())
so matrix_bootstrap can't auto-resurrect the rows. Per the v1 script
we have 16 rows: R-1..R-9 + B-1 + C + MCD + OR-1 + OR-2 + OR-3 + I.

The tombstones are durable; this script is not meant to be re-run.
"""
raise SystemExit(
    "Archived — one-shot cleanup already applied. "
    "See scripts/_archive/westampton/README.md."
)

import sys  # noqa: E402
from urllib.parse import quote  # noqa: E402

import requests  # noqa: E402

BASE = "https://capable-serenity-production-0d1a.up.railway.app/api"
ORPHAN_ID = "fd74c349-1f6d-4941-9ce6-8b2002102303"
ZONES = [
    "R-1","R-2","R-3","R-4","R-5","R-6","R-7","R-8","R-9",
    "B-1","C","MCD","OR-1","OR-2","OR-3","I",
]


def main() -> int:
    failures = 0
    for zone in ZONES:
        url = f"{BASE}/jurisdictions/{ORPHAN_ID}/zones/{quote(zone, safe='')}"
        resp = requests.delete(url, timeout=30)
        if resp.status_code in (204, 200):
            print(f"{zone:6s} DELETE {resp.status_code} OK")
        elif resp.status_code == 404:
            print(f"{zone:6s} DELETE 404 (already gone)")
        else:
            print(f"{zone:6s} DELETE {resp.status_code} FAIL -- {resp.text[:200]}")
            failures += 1
    print()
    print(f"Done. {len(ZONES) - failures}/{len(ZONES)} successful.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
