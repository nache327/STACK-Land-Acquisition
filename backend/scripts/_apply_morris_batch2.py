"""Morris Batch 2 apply — 7 wealth-pocket municipalities. Reviewer-confirmed:
NO self_storage needle in any town (all affluent historic/low-density boroughs
that zone storage out). Self-sources gated to actual parcels.zoning_code per
municipality (queried at apply time), defaults every code to all-prohibited,
then applies the handful of grounded exceptions below.

Exceptions (grounded in the dry-run parse + NJTPA zone labels):
  Florham Park  C-1 / POD-S / POD-N  light_industrial=PERMITTED (storage unlisted)
                M-2                  all UNCLEAR (NJTPA 'M-2 Industrial' but no
                                     such zone in Ch250; 1 stale parcel) -> verify
  Madison       OR / PCD-O           light_industrial=CONDITIONAL (R&D/lab)
                G-I / G-II           prohibited (= 'Gateway I/II' redevelopment,
                                     NOT industrial despite the code)
  Chester boro  I / M-H              all UNCLEAR (industrial §163-74 repealed 2004;
                                     stale labels) -> verify, do NOT assert
  Mendham boro  LB                   all UNCLEAR (use list not fully captured) -> verify

Everything else -> all 4 uses prohibited, classification_source=human,
human_reviewed=True, confidence 0.90 (silence rule, grounded per town ordinance).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg
import httpx

MORRIS_JID = "746b7604-f362-470f-aa42-70dc8973b4ee"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
BASE = f"{API_BASE}/api/jurisdictions/{MORRIS_JID}/zones"

P, C_, X, U = "permitted", "conditional", "prohibited", "unclear"

TOWNS = ["Mendham borough", "Mendham township", "Chester borough", "Chester township",
         "Harding township", "Madison borough", "Florham Park borough"]

# The 4 UNCLEAR rows — held out of the grounded-92 commit, applied separately
# after a verification pass (per Nache 2026-06-04).
EXCLUDE = {("Mendham borough", "LB"), ("Chester borough", "I"),
           ("Chester borough", "M-H"), ("Florham Park borough", "M-2")}

# zone_code -> (ss, mw, li, gc, conf, source, name, note)
OVERRIDES = {
    "Florham Park borough": {
        "C-1":   (X, X, P, X, 0.85, "human", "C-1 Commercial (light mfg)",
                  "Light manufacturing permitted [§250-55D]; storage uses unlisted -> prohibited."),
        "POD-S": (X, X, P, X, 0.85, "human", "Planned Office District South",
                  "Light manufacturing permitted [§250-118A(3)]; storage unlisted."),
        "POD-N": (X, X, P, X, 0.85, "human", "Planned Office District North",
                  "Light manufacturing permitted [§250-117A(3)]; storage unlisted."),
        "M-2":   (U, U, U, U, 0.50, "human", "M-2 (stale/legacy NJTPA label)",
                  "NJTPA labels 'M-2 Industrial District' but Chapter 250 has no M-2 "
                  "(1 stale parcel); manufacturing lives in C-1, storage unlisted. VERIFY."),
    },
    "Madison borough": {
        "OR":    (X, X, C_, X, 0.70, "human", "Office Research",
                  "R&D/laboratory permitted [§195-32.7B] (partial light-industrial analog); storage unlisted."),
        "PCD-O": (X, X, C_, X, 0.70, "human", "Planned Commercial Development - Office",
                  "R&D/lab permitted [§195-32.8B]; storage unlisted."),
        "G-I":   (X, X, X, X, 0.90, "human", "G-I Gateway I Zone",
                  "NJTPA 'G-I Gateway I Zone' = mixed-use redevelopment, NOT industrial; no storage."),
        "G-II":  (X, X, X, X, 0.90, "human", "G-II Gateway II Zone",
                  "NJTPA 'G-II Gateway II Zone' = mixed-use redevelopment, NOT industrial; no storage."),
    },
    "Chester borough": {
        "I":   (U, U, U, U, 0.50, "human", "I (repealed industrial — verify)",
                "Prior Industrial zone §163-74 repealed 2004 per parsed ordinance; 4 parcels "
                "carry stale 'I' label. No current Chester Borough zone permits storage. VERIFY repeal."),
        "M-H": (U, U, U, U, 0.50, "human", "M-H (legacy — verify)",
                "Designation absent from current Chester Borough code (1 parcel). VERIFY."),
    },
    "Mendham borough": {
        "LB": (U, U, U, U, 0.40, "human", "LB Limited Business (verify)",
               "Limited Business use list not fully captured; Borough description = office/"
               "banking/public uses, no storage. VERIFY."),
    },
}

PROHIBITED_NOTE = {
    "Mendham borough":   "Silence rule — self-storage not named (Ch215; HB=Historic Business grounded).",
    "Mendham township":  "Silence rule — self-storage not named (Ch500; CR-1/CR-2=Combination Residential).",
    "Chester borough":   "Silence rule — self-storage not named (Art IX; industrial §163-74 repealed 2004).",
    "Chester township":  "Silence rule — self-storage not named (B/LB/PO-R = office/retail/residential).",
    "Harding township":  "Silence rule — self-storage not named (B-1/B-2/OB = office/retail/residential).",
    "Madison borough":   "Silence rule — self-storage not named (no Madison zone permits storage/mfg).",
    "Florham Park borough": "Silence rule — self-storage not named (Ch250).",
}


def payload(muni, code, ss, mw, li, gc, conf, src, name, note):
    return {"zone_code": code, "zone_name": name, "municipality": muni,
            "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
            "luxury_garage_condo": gc, "classification_source": src,
            "confidence": conf, "notes": note[:2048] or None, "human_reviewed": True}


async def build_rows(conn) -> list[dict]:
    rows = []
    for muni in TOWNS:
        codes = await conn.fetch(
            "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 "
            "AND zoning_code IS NOT NULL", MORRIS_JID, muni)
        ov = OVERRIDES.get(muni, {})
        pnote = PROHIBITED_NOTE.get(muni, "Silence rule — self-storage not named.")
        for r in codes:
            code = r["zoning_code"]
            if (muni, code) in EXCLUDE:
                continue
            if code in ov:
                ss, mw, li, gc, conf, src, name, note = ov[code]
                rows.append(payload(muni, code, ss, mw, li, gc, conf, src, name, note))
            else:
                rows.append(payload(muni, code, X, X, X, X, 0.90, "human", None, pnote))
    return rows


async def main(apply: bool) -> None:
    env = Path(".env").read_text(encoding="utf-8")
    url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    rows = await build_rows(conn)
    await conn.close()

    print(f"[morris-batch2] {len(rows)} rows across {len(TOWNS)} towns, apply={apply}", file=sys.stderr)
    # reviewer table: show every non-(all-prohibited) row
    print("\n=== non-prohibited / verify rows ===", file=sys.stderr)
    for r in rows:
        if not (r["self_storage"] == X and r["mini_warehouse"] == X
                and r["light_industrial"] == X and r["luxury_garage_condo"] == X):
            print(f"  {r['municipality']:20} {r['zone_code']:8} ss={r['self_storage']:10} "
                  f"li={r['light_industrial']:11} conf={r['confidence']}", file=sys.stderr)
    if not apply:
        print("\n[dry-run] no writes. re-run with --apply", file=sys.stderr)
        return

    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for r in rows:
            muni, code = r["municipality"], r["zone_code"]
            try:
                resp = await client.post(BASE, json=r)
            except Exception as exc:  # noqa: BLE001
                failed += 1; print(f"  FAIL {muni}/{code}: {exc}", file=sys.stderr); continue
            if resp.status_code == 201:
                created += 1
            elif resp.status_code == 409:
                purl = f"{BASE}/{quote(code, safe='')}?municipality={quote(muni, safe='')}"
                pr = await client.patch(purl, json={
                    "self_storage": r["self_storage"], "mini_warehouse": r["mini_warehouse"],
                    "light_industrial": r["light_industrial"], "luxury_garage_condo": r["luxury_garage_condo"],
                    "notes": r["notes"]})
                if pr.status_code == 200: updated += 1
                else: failed += 1; print(f"  PATCH {pr.status_code} {muni}/{code}: {pr.text[:140]}", file=sys.stderr)
            else:
                failed += 1; print(f"  {resp.status_code} {muni}/{code}: {resp.text[:140]}", file=sys.stderr)
    print(f"\n[morris-batch2] created={created} updated={updated} failed={failed}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
