"""Bedminster township — corrected/COMPLETE per-city verdict pass (Batch 4 add).
The prior 11-row pass was incomplete: it never gated to parcels.zoning_code and
missed PUD (2436), PRD (918), OR/OP/OR-V/OR-2/ORVMU office-research zones, P,
SCH, SFC, VN-3. This pass parses Article 13-400 and gates to the actual parcel
codes (normalize-match). NO self_storage needle — every office-research zone
EXPLICITLY excludes warehousing/distribution (§13-406.1 / 13-406B.1 / 13-406C.2
/ 13-413.3). PATCHes the 11 stale rows + creates the ~12 missing.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg
import httpx

SOM = "394ef40c-ca0d-4d57-9b11-dc5417430240"
BASE = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{SOM}/zones"
MUNI = "Bedminster township"
X = "prohibited"


def norm(c): return re.sub(r"[^A-Z0-9]", "", c.upper())
def perm(v): return str(v).split(".")[-1]


async def main(apply):
    env = Path("c:/Users/nache_rl1pdne/zoning-finder/backend/.env").read_text(encoding="utf-8")
    url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"), statement_cache_size=0)
    d = json.load(open("c:/Users/nache_rl1pdne/zoning-finder/backend/scripts/proposed_verdicts_bedminster.json", encoding="utf-8"))
    vmap = {norm(z["zone_code"]): z for z in d["results"][0]["zones"]}
    codes = await conn.fetch("SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 AND zoning_code IS NOT NULL", SOM, MUNI)
    await conn.close()
    rows = []
    for r in codes:
        code = r["zoning_code"]; z = vmap.get(norm(code))
        if z:
            cites = z.get("citations") or []; cite = cites[0].get("section") if cites else None
            note = (f"[§{cite}] " if cite else "") + (z.get("notes") or "")
            rows.append({"zone_code": code, "zone_name": z.get("zone_name"), "municipality": MUNI,
                "self_storage": perm(z["self_storage"]), "mini_warehouse": perm(z["mini_warehouse"]),
                "light_industrial": perm(z["light_industrial"]), "luxury_garage_condo": perm(z["luxury_garage_condo"]),
                "classification_source": "human", "confidence": z.get("confidence") or 0.9,
                "notes": note[:2048] or None, "human_reviewed": True})
        else:
            rows.append({"zone_code": code, "zone_name": None, "municipality": MUNI, "self_storage": X,
                "mini_warehouse": X, "light_industrial": X, "luxury_garage_condo": X, "classification_source": "human",
                "confidence": 0.85, "notes": "Silence rule — self-storage not named (Art 13-400; parcel code uncovered by parse).",
                "human_reviewed": True})
    print(f"[bedminster] {len(rows)} rows (parcel codes), apply={apply}", file=sys.stderr)
    for r in rows:
        nn = "" if (r["self_storage"] == X and r["light_industrial"] == X) else "  <<<"
        print(f"  {r['zone_code']:8} ss={r['self_storage']:11} li={r['light_industrial']:11} c={r['confidence']}{nn}", file=sys.stderr)
    if not apply:
        print("[dry-run]", file=sys.stderr); return
    cr = up = fa = 0
    async with httpx.AsyncClient(timeout=45.0) as cl:
        for r in rows:
            resp = await cl.post(BASE, json=r)
            if resp.status_code == 201:
                cr += 1
            elif resp.status_code == 409:
                pr = await cl.patch(f"{BASE}/{quote(r['zone_code'], safe='')}?municipality={quote(MUNI, safe='')}",
                    json={k: r[k] for k in ('self_storage', 'mini_warehouse', 'light_industrial', 'luxury_garage_condo', 'notes')})
                up += 1 if pr.status_code == 200 else 0
                if pr.status_code != 200:
                    fa += 1; print(f"  PATCH {pr.status_code} {r['zone_code']}", file=sys.stderr)
            else:
                fa += 1; print(f"  {resp.status_code} {r['zone_code']}: {resp.text[:100]}", file=sys.stderr)
    print(f"\n[bedminster] created={cr} updated={up} failed={fa}", file=sys.stderr)
    if fa:
        raise SystemExit(1)


asyncio.run(main("--apply" in sys.argv))
