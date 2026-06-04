"""Batch 3 — 5 grounded Monmouth coastal towns (Sea Bright, Spring Lake, Spring
Lake Heights, Allenhurst, Deal). All NO self_storage needle (resort-residential;
storage zoned out). Reads the dry-run verdicts, gates to actual parcels.zoning_code
(normalize-match handles parser C1<->parcel C-1, BR<->B-R, CP<->C-P), applies with
the per-zone §-citation in notes. classification_source=human, human_reviewed=True.

Middletown (M-1/BP/MC) + Tewksbury (Municode PM) are NOT here — handoff follow-up.
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

MONMOUTH = "703d95b4-3229-42f8-8bb1-460d46b3ceb2"
BASE = f"https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions/{MONMOUTH}/zones"
X = "prohibited"
TOWNS = ["Sea Bright borough", "Spring Lake borough", "Spring Lake Heights borough",
         "Allenhurst borough", "Deal borough"]
CATCHALL = {
    "Sea Bright borough": "§130-38(G) catch-all: uses not enumerated are prohibited",
    "Spring Lake borough": "silence rule: uses not listed prohibited",
    "Spring Lake Heights borough": "silence rule: uses not listed prohibited",
    "Allenhurst borough": "§26-4.4(g): all uses not expressly permitted prohibited",
    "Deal borough": "§30-83: uses not expressly permitted prohibited",
}


# Human-review convention bump (overrides the parser's mis-classification).
# Spring Lake GC: §225-13.A(8) permits "wholesale distribution centers and
# warehouses" BY RIGHT -> warehouse permitted + self-storage unnamed = conditional
# per [[feedback_warehouse_conditional_convention]]; light_industrial = permitted.
OVERRIDES = {
    ("Spring Lake borough", "GC"): {
        "self_storage": "conditional", "mini_warehouse": "conditional",
        "light_industrial": "permitted", "luxury_garage_condo": "prohibited",
        "confidence": 0.80, "zone_name": "General Commercial District",
        "notes": "[§225-13.A(8)] Wholesale distribution centers + warehouses permitted "
                 "BY RIGHT in GC District only; self-storage unnamed -> conditional per "
                 "warehouse convention; light_industrial permitted (warehouse/distribution). "
                 "Needle: GC is the ONLY Spring Lake zone permitting warehousing.",
    },
}


def norm(c: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", c.upper())


def load_verdicts() -> dict:
    """municipality -> {normalized_code -> zone dict} from the two dry-run files."""
    out: dict = {}
    for fn in ("proposed_verdicts_batch3.json", "proposed_verdicts_batch3_ad.json"):
        p = Path(__file__).parent / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for rec in data.get("results", []):
            if rec.get("error"):
                continue
            muni = rec["municipality"]
            out.setdefault(muni, {})
            for z in rec.get("zones", []):
                out[muni][norm(z["zone_code"])] = z
    return out


def perm(v):  # normalize "UsePermission.permitted" -> "permitted"
    return str(v).split(".")[-1]


async def build_rows(conn, verdicts) -> list[dict]:
    rows = []
    for muni in TOWNS:
        codes = await conn.fetch(
            "SELECT DISTINCT zoning_code FROM parcels WHERE jurisdiction_id=$1 AND city=$2 "
            "AND zoning_code IS NOT NULL", MONMOUTH, muni)
        vmap = verdicts.get(muni, {})
        for r in codes:
            code = r["zoning_code"]
            ovr = OVERRIDES.get((muni, code))
            if ovr:
                rows.append({"zone_code": code, "zone_name": ovr["zone_name"], "municipality": muni,
                             "self_storage": ovr["self_storage"], "mini_warehouse": ovr["mini_warehouse"],
                             "light_industrial": ovr["light_industrial"], "luxury_garage_condo": ovr["luxury_garage_condo"],
                             "classification_source": "human", "confidence": ovr["confidence"],
                             "notes": ovr["notes"][:2048], "human_reviewed": True})
                continue
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
                note = CATCHALL.get(muni, "silence rule"); conf = 0.9; name = None
            rows.append({"zone_code": code, "zone_name": name, "municipality": muni,
                         "self_storage": ss, "mini_warehouse": mw, "light_industrial": li,
                         "luxury_garage_condo": gc, "classification_source": "human",
                         "confidence": conf, "notes": note[:2048] or None, "human_reviewed": True})
    return rows


async def main(apply: bool) -> None:
    env = Path("c:/Users/nache_rl1pdne/zoning-finder/backend/.env").read_text(encoding="utf-8")
    url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"), statement_cache_size=0)
    verdicts = load_verdicts()
    rows = await build_rows(conn, verdicts)
    await conn.close()

    print(f"[batch3-coastal] {len(rows)} rows, apply={apply}", file=sys.stderr)
    print("\n=== reviewer table (citation per row) ===", file=sys.stderr)
    for r in rows:
        flag = "" if (r["self_storage"] == X and r["light_industrial"] == X) else "  <-- non-prohibited"
        print(f"  {r['municipality']:26} {r['zone_code']:8} ss={r['self_storage']:11} "
              f"li={r['light_industrial']:11} | {(r['notes'] or '')[:70]}{flag}", file=sys.stderr)
    if not apply:
        print("\n[dry-run] no writes.", file=sys.stderr); return

    created = updated = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for r in rows:
            muni, code = r["municipality"], r["zone_code"]
            resp = await client.post(BASE, json=r)
            if resp.status_code == 201:
                created += 1
            elif resp.status_code == 409:
                purl = f"{BASE}/{quote(code, safe='')}?municipality={quote(muni, safe='')}"
                pr = await client.patch(purl, json={k: r[k] for k in
                    ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo", "notes")})
                updated += 1 if pr.status_code == 200 else 0
                if pr.status_code != 200:
                    failed += 1; print(f"  PATCH {pr.status_code} {muni}/{code}", file=sys.stderr)
            else:
                failed += 1; print(f"  {resp.status_code} {muni}/{code}: {resp.text[:120]}", file=sys.stderr)
    print(f"\n[batch3-coastal] created={created} updated={updated} failed={failed}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
