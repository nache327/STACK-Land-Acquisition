"""Bergen wealth-tail Batch 1 FINALIZATION — Tenafly, Cresskill, Demarest,
Closter District 4. Verdicts hand-delivered by the reviewer (Nache), already
eyeballed against the ordinances. Applied in one batch via the prod /zones
endpoints (201 create / 409 -> PATCH). Saddle River §210-5 is DEFERRED to a
separate commit (paste pending).

Reconciliation (ordinance code -> parcel/NJTPA code, from _codes_per_town.py):
  Tenafly  M-I   -> M-1 (35 parcels)   [SR/B has 0 parcels — applied future-proof]
  Cresskill P&L  -> "P and L" (29)
  Demarest BUS   == BUS (9)            [alias of ordinance CB-I]
  Closter  D4    == "District No. 4" (28)

Every "other zone" is gated to codes parcels actually carry (per-town distinct
zoning_code), so no phantom rows. classification_source='human',
human_reviewed=True. Closter D4 uses confidence 0.60 (enum has no
'human_inferred'; the <0.70 value keeps it out of digest surfacing while
preserving honest provenance in notes).
"""
from __future__ import annotations

import asyncio
import sys
from urllib.parse import quote

import httpx

BERGEN_JID = "4bf00234-4455-4987-a067-b22ee6b6aa1f"
API_BASE = "https://capable-serenity-production-0d1a.up.railway.app"
BASE = f"{API_BASE}/api/jurisdictions/{BERGEN_JID}/zones"

P, C_, X, U = "permitted", "conditional", "prohibited", "unclear"

# §35-802.22 self-storage conditions (developer requirements, not blockers)
TEN_COND = ("Conditions §35-802.22: 10ft landscape buffer; 25ft parking setback "
            "from residential; no unit doors open to street; shielded lighting; "
            "facade compatibility; trash screening (developer reqs, not blockers).")


def row(muni, code, ss, mw, li, gc, conf, note, name=None):
    return {
        "zone_code": code, "zone_name": name, "municipality": muni,
        "self_storage": ss, "mini_warehouse": mw,
        "light_industrial": li, "luxury_garage_condo": gc,
        "classification_source": "human", "confidence": conf,
        "notes": note[:2048] or None, "human_reviewed": True,
    }


def prohibited_set(muni, codes, note):
    return [row(muni, c, X, X, X, X, 0.95, note) for c in codes]


ROWS: list[dict] = []

# ---- TENAFLY ---------------------------------------------------------------
TEN = "Tenafly borough"
ROWS.append(row(TEN, "M-1", P, P, P, X, 0.90,
    "[Schedule A (Ch35 Att10) Permitted Use #1 — M-I inherits SR/B principal "
    f"uses incl. self-storage; manufacturing also permitted] {TEN_COND}",
    name="M-I Industrial"))
ROWS.append(row(TEN, "SR/B", P, P, P, X, 0.95,
    "[Schedule A (Ch35 Att10) Permitted Use #3 self-storage named + Use #4 "
    f"warehousing] {TEN_COND} NOTE: no Tenafly parcels carry SR/B in current "
    "NJTPA layer (pool=0); M-1 carries the bound inheritance pool.",
    name="SR/B Self-Storage / Business"))
ROWS += prohibited_set(TEN,
    ["R-9", "R-10", "R-20", "R-40", "R-7.5", "B-2", "C", "B-1", "R-RMF", "O",
     "R-MF", "R-6"],
    "Schedule A silence rule — self-storage not named in this district.")

# ---- CRESSKILL -------------------------------------------------------------
CRE = "Cresskill borough"
ROWS.append(row(CRE, "P and L", C_, C_, P, X, 0.75,
    "[§275-24.D(1) — receipt/storage/distribution within enclosed building "
    "permitted by right; self-storage unnamed -> conditional per convention] "
    "lab-centric zone; storage framed as lab-product flow (conf 0.75).",
    name="Professional Office + R&D Labs"))
ROWS.append(row(CRE, "C", X, X, X, X, 0.95,
    "[§275-21 silence rule + §275-19.C explicitly excludes motor-vehicle "
    "storage; §275-20 requires accessory storage fully enclosed].",
    name="Commercial"))
ROWS += prohibited_set(CRE,
    ["R-10", "R-40", "TR", "PURD", "MU", "R-15", "DU", "P", "CMU", "AHSZ",
     "R-SC", "RA", "D", "R-9"],
    "§275-21 silence rule — self-storage not named.")

# ---- DEMAREST --------------------------------------------------------------
DEM = "Demarest borough"
ROWS.append(row(DEM, "BUS", X, X, X, X, 0.95,
    "[§175-14 silence rule] NJTPA 'BUS' = ordinance 'CB-I' (Community Business "
    "I); permits residential + contained retail + personal service + office "
    "only; §175-15 conditional uses repealed 1996; no warehouse/storage/industrial.",
    name="CB-I Community Business I (NJTPA alias 'BUS')"))
ROWS += prohibited_set(DEM, ["D", "C", "B", "A", "BB"],
    "§175-14 silence rule — self-storage not named.")

# ---- CLOSTER (District 4 + stray R-40 sweep) -------------------------------
CLO = "Closter borough"
ROWS.append(row(CLO, "District No. 4", X, X, X, X, 0.60,
    "Inferred from Closter sibling-district pattern; Districts 3/4A/4B all "
    "prohibit storage per their parsed articles. District 4 article not "
    "directly parsed (Schedule A is dimensional only); revisit if a deal lands "
    "on a District 4 parcel. confidence 0.60 — below 0.70 digest filter.",
    name="District No. 4, Commercial Area"))
ROWS.append(row(CLO, "R-40", X, X, X, X, 0.95,
    "Residential anomaly (2 parcels mis-coded R-40 in Closter); silence rule.",
    name="R-40 Residential (anomaly)"))


async def main(apply: bool) -> None:
    print(f"[batch1-final] {len(ROWS)} rows, apply={apply}", file=sys.stderr)
    if not apply:
        for r in ROWS:
            print(f"  {r['municipality']:18} {r['zone_code']:16} "
                  f"ss={r['self_storage']:11} conf={r['confidence']}", file=sys.stderr)
        print("\n[dry-run] no writes. re-run with --apply", file=sys.stderr)
        return

    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for r in ROWS:
            muni, code = r["municipality"], r["zone_code"]
            try:
                resp = await client.post(BASE, json=r)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAIL  {muni}/{code}: {exc}", file=sys.stderr)
                continue
            if resp.status_code == 201:
                created += 1
                print(f"  201   {muni}/{code} ss={r['self_storage']}", file=sys.stderr)
            elif resp.status_code == 409:
                purl = f"{BASE}/{quote(code, safe='')}?municipality={quote(muni, safe='')}"
                pr = await client.patch(purl, json={
                    "self_storage": r["self_storage"],
                    "mini_warehouse": r["mini_warehouse"],
                    "light_industrial": r["light_industrial"],
                    "luxury_garage_condo": r["luxury_garage_condo"],
                    "notes": r["notes"],
                })
                if pr.status_code == 200:
                    updated += 1
                    print(f"  409->PATCH 200  {muni}/{code}", file=sys.stderr)
                else:
                    failed += 1
                    print(f"  409->PATCH {pr.status_code}  {muni}/{code}: "
                          f"{pr.text[:160]}", file=sys.stderr)
            else:
                failed += 1
                print(f"  {resp.status_code}  {muni}/{code}: {resp.text[:160]}",
                      file=sys.stderr)
    print(f"\n[batch1-final] created={created} updated={updated} failed={failed}",
          file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
