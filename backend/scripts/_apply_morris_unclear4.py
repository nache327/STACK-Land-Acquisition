"""Morris Batch 2 — the 4 held-back UNCLEAR rows, resolved by verification pass
(Nache 2026-06-04) and applied as a SEPARATE commit from the grounded 92 so they
can be revisited cleanly later.

Resolution (all -> prohibited; none actionable for storage):
  Mendham boro LB   conf 0.65 — node lands on dev standards; storage only
                    accessory (§215-31.1 rear+screened); Borough description =
                    office/banking/public uses. Conservative call.
  Chester boro I    conf 0.70 — Industrial §163-74 repealed 2004 WITHOUT
                    replacement (no industrial zone in current code); orphaned.
  Chester boro M-H  conf 0.70 — absent from current Chester Borough code; orphaned.
  Florham Park M-2  conf 0.70 — NJTPA 'M-2 Industrial' but no M-2 in current
                    Chapter 250 (1 parcel); orphaned.
"""
from __future__ import annotations

import asyncio
import sys
from urllib.parse import quote

import httpx

MORRIS_JID = "746b7604-f362-470f-aa42-70dc8973b4ee"
BASE = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{MORRIS_JID}/zones"
X = "prohibited"

ROWS = [
    {"municipality": "Mendham borough", "zone_code": "LB",
     "zone_name": "LB Limited Business", "confidence": 0.65,
     "notes": "LB principal-use list not fully captured (node lands on development "
              "standards); storage is accessory-only (§215-31.1, rear + screened); "
              "Borough description = office/banking/public uses. Conservative prohibited; "
              "revisit if a deal lands."},
    {"municipality": "Chester borough", "zone_code": "I",
     "zone_name": "I (repealed industrial)", "confidence": 0.70,
     "notes": "I zone (§163-74) repealed 2004 without replacement (no industrial zone in "
              "current Chester Borough code); parcels orphaned."},
    {"municipality": "Chester borough", "zone_code": "M-H",
     "zone_name": "M-H (legacy)", "confidence": 0.70,
     "notes": "M-H designation absent from current Chester Borough code; parcels orphaned."},
    {"municipality": "Florham Park borough", "zone_code": "M-2",
     "zone_name": "M-2 (stale NJTPA label)", "confidence": 0.70,
     "notes": "NJTPA labels 'M-2 Industrial District' but no M-2 zone in current Chapter 250 "
              "(1 parcel); parcels orphaned."},
]


async def main(apply: bool) -> None:
    print(f"[unclear4] {len(ROWS)} rows, apply={apply}", file=sys.stderr)
    for r in ROWS:
        print(f"  {r['municipality']:20} {r['zone_code']:6} -> prohibited conf={r['confidence']}", file=sys.stderr)
    if not apply:
        print("[dry-run] no writes.", file=sys.stderr); return
    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for r in ROWS:
            body = {"zone_code": r["zone_code"], "zone_name": r["zone_name"],
                    "municipality": r["municipality"], "self_storage": X, "mini_warehouse": X,
                    "light_industrial": X, "luxury_garage_condo": X,
                    "classification_source": "human", "confidence": r["confidence"],
                    "notes": r["notes"][:2048], "human_reviewed": True}
            resp = await client.post(BASE, json=body)
            if resp.status_code == 201:
                created += 1; print(f"  201 {r['municipality']}/{r['zone_code']}", file=sys.stderr)
            elif resp.status_code == 409:
                purl = f"{BASE}/{quote(r['zone_code'], safe='')}?municipality={quote(r['municipality'], safe='')}"
                pr = await client.patch(purl, json={"self_storage": X, "mini_warehouse": X,
                    "light_industrial": X, "luxury_garage_condo": X, "notes": r["notes"][:2048]})
                if pr.status_code == 200: updated += 1; print(f"  409->PATCH {r['municipality']}/{r['zone_code']}", file=sys.stderr)
                else: failed += 1; print(f"  PATCH {pr.status_code} {r['zone_code']}: {pr.text[:140]}", file=sys.stderr)
            else:
                failed += 1; print(f"  {resp.status_code} {r['zone_code']}: {resp.text[:140]}", file=sys.stderr)
    print(f"\n[unclear4] created={created} updated={updated} failed={failed}", file=sys.stderr)
    if failed: raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
