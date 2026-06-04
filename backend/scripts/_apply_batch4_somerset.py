"""Batch 4 — Somerset wealth-tail (Bernardsville, Peapack & Gladstone, Far Hills).
Jurisdiction = Somerset. Reads dry-run verdicts, gates to parcels.zoning_code
(normalize-match), per-zone §-citation in notes. classification_source=human.

MOAT FIND: Bernardsville I + I-2 = self_storage PERMITTED (explicitly named
"Self-storage facilities" §12-15.1(f) / §12-16). Binds I=27 + I-2=4 = 31 parcels.

Reconciliations:
  Bernardsville B-1/C-1/O-B/H-D parcels -> districts REPEALED + replaced by
    Downtown District subdistricts (D-C/D-Cl/D-Co/D-G), all of which prohibit
    warehouses + manufacturing -> self_storage prohibited (grounded).
  Peapack L-I (parcel) <-> LI (parsed) normalize-match; LI = light_industrial
    permitted, self_storage prohibited (§23-39.7, light mfg only).
  Far Hills NO + residentials: VC node grounded prohibited (§"and no other");
    NO=Neighborhood Office + residential districts grounded via the borough's
    exhaustive-list convention (no storage/warehouse/industrial named).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg
import httpx

SOMERSET = "394ef40c-ca0d-4d57-9b11-dc5417430240"
BASE = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{SOMERSET}/zones"
X = "prohibited"
TOWNS = ["Bernardsville borough", "Peapack and Gladstone borough", "Far Hills borough"]

# Per-town note + confidence for parcel codes NOT matched to a parsed zone.
DEFAULT = {
    "Bernardsville borough": (
        "B-1/C-1/O-B/H-D districts repealed & replaced by Downtown District "
        "subdistricts (D-C/D-Cl/D-Co/D-G), all of which prohibit warehouses + "
        "manufacturing; self_storage prohibited.", 0.85),
    "Peapack and Gladstone borough": ("Silence rule — self-storage not named (Art IV zoning).", 0.9),
    "Far Hills borough": (
        "Far Hills uses exhaustive permitted-use lists ('and no other', VC §); "
        "NO=Neighborhood Office (office only) + residential districts name no "
        "storage/warehouse/industrial use.", 0.80),
}


def norm(c): return re.sub(r"[^A-Z0-9]", "", c.upper())
def perm(v): return str(v).split(".")[-1]


def load_verdicts():
    data = json.loads((Path(__file__).parent / "proposed_verdicts_batch4.json").read_text(encoding="utf-8"))
    out = {}
    for rec in data.get("results", []):
        if rec.get("error"):
            continue
        out.setdefault(rec["municipality"], {})
        for z in rec.get("zones", []):
            out[rec["municipality"]][norm(z["zone_code"])] = z
    return out


async def build_rows(conn, verdicts):
    rows = []
    for muni in TOWNS:
        codes = await conn.fetch(
            "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 "
            "AND zoning_code IS NOT NULL", SOMERSET, muni)
        vmap = verdicts.get(muni, {})
        dnote, dconf = DEFAULT[muni]
        for r in codes:
            code = r["zoning_code"]
            z = vmap.get(norm(code))
            if z:
                ss, mw, li, gc = (perm(z["self_storage"]), perm(z["mini_warehouse"]),
                                  perm(z["light_industrial"]), perm(z["luxury_garage_condo"]))
                cites = z.get("citations") or []
                cite = cites[0].get("section") if cites else None
                note = (f"[§{cite}] " if cite else "") + (z.get("notes") or "")
                conf = z.get("confidence") or 0.9
                name = z.get("zone_name")
            else:
                ss = mw = li = gc = X
                note = dnote; conf = dconf; name = None
            rows.append({"zone_code": code, "zone_name": name, "municipality": muni,
                         "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
                         "luxury_garage_condo": gc, "classification_source": "human",
                         "confidence": conf, "notes": note[:2048] or None, "human_reviewed": True})
    return rows


async def main(apply):
    env = Path("c:/Users/nache_rl1pdne/zoning-finder/backend/.env").read_text(encoding="utf-8")
    url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"), statement_cache_size=0)
    rows = await build_rows(conn, load_verdicts())
    await conn.close()
    print(f"[batch4] {len(rows)} rows, apply={apply}", file=sys.stderr)
    print("\n=== reviewer table ===", file=sys.stderr)
    for r in rows:
        nonp = not (r["self_storage"] == X and r["light_industrial"] == X)
        print(f"  {r['municipality']:30} {r['zone_code']:8} ss={r['self_storage']:11} "
              f"li={r['light_industrial']:11} c={r['confidence']} | {(r['notes'] or '')[:55]}"
              f"{'  <<<' if nonp else ''}", file=sys.stderr)
    if not apply:
        print("\n[dry-run] no writes.", file=sys.stderr); return
    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=45.0) as client:
        for r in rows:
            muni, code = r["municipality"], r["zone_code"]
            try:
                resp = await client.post(BASE, json=r)
            except Exception as exc:
                failed += 1; print(f"  ERR {muni}/{code}: {exc}", file=sys.stderr); continue
            if resp.status_code == 201:
                created += 1
            elif resp.status_code == 409:
                purl = f"{BASE}/{quote(code, safe='')}?municipality={quote(muni, safe='')}"
                pr = await client.patch(purl, json={k: r[k] for k in
                    ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo", "notes")})
                if pr.status_code == 200: updated += 1
                else: failed += 1; print(f"  PATCH {pr.status_code} {muni}/{code}", file=sys.stderr)
            else:
                failed += 1; print(f"  {resp.status_code} {muni}/{code}: {resp.text[:120]}", file=sys.stderr)
    print(f"\n[batch4] created={created} updated={updated} failed={failed}", file=sys.stderr)
    if failed: raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
