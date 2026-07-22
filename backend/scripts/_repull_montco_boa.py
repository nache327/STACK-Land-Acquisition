"""Bucket C — Montgomery County PA owner + mailing.

Single public source: the county Board of Assessment property-records Vision
datalet (propertyrecords.montcopa.org/pt/Datalets/Datalet.aspx?UseSearch=no&pin=<apn>,
same Tyler system as Fairfax iCare / Bucks BOA). Owner-name *search* is disabled
for privacy, but a direct parcel-ID deep link returns the 'Owner' table with
owner Name(s) + Mailing Address — and our apn is the parcel id (e.g. 010000001007).

Needle-scoped, idempotent COALESCE-fill; concurrency-capped + retried.

    python scripts/_repull_montco_boa.py --limit 15    # dry-run
    python scripts/_repull_montco_boa.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncpg
import httpx

from _db import get_sync_dsn

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}
_MONTCO = "a59d956d"
_BASE = "https://propertyrecords.montcopa.org/pt/Datalets/Datalet.aspx?UseSearch=no&pin={pin}"
_CONCURRENCY = 4

_LGC = ("(v.ss IN ('permitted','conditional') OR v.mw IN ('permitted','conditional') "
        "OR v.li IN ('permitted','conditional'))")
_LAT = """JOIN LATERAL (SELECT self_storage::text ss, mini_warehouse::text mw,
  light_industrial::text li FROM zone_use_matrix m WHERE m.jurisdiction_id=p.jurisdiction_id
  AND m.zone_code=p.zoning_code AND (m.municipality IS NULL OR m.municipality=p.city)
  AND m.deleted_at IS NULL AND m.human_reviewed ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true"""
_W = "p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"
_SENT = {"", "nan", "null", "none", "n/a", "."}


def _clean(s: str) -> str:
    return " ".join(s.replace("&nbsp;", " ").split()).strip()


def _owner_cells(html: str) -> list[str]:
    m = re.search(r"id='Owner'(.*?)</table>", html, re.S | re.I)
    if not m:
        return []
    return [_clean(re.sub("<[^>]+>", " ", t)) for t in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S | re.I)]


def parse(html: str) -> tuple[str | None, str | None, str | None]:
    """(owner_name, mailing_street[+c/o], city_state_zip)."""
    cells = _owner_cells(html)
    names: list[str] = []
    street = co = csz = None
    for i, c in enumerate(cells):
        nxt = cells[i + 1] if i + 1 < len(cells) else ""
        if c == "Name(s)" and nxt and nxt.lower() not in _SENT:
            names.append(nxt)
        elif c == "Mailing Address" and street is None and nxt and nxt.lower() not in _SENT:
            street = nxt
        elif c == "Care Of" and nxt and nxt.lower() not in _SENT:
            co = nxt
    for c in reversed(cells):
        if c and re.search(r"[A-Z]{2}\s+\d{5}", c):
            csz = c
            break
    owner = " & ".join(dict.fromkeys(names)) or None
    addr = street
    if co:
        addr = f"{street} C/O {co}" if street else f"C/O {co}"
    return owner, addr, csz


async def _fetch(cl, apn, sem):
    async with sem:
        for attempt in range(4):
            try:
                r = await cl.get(_BASE.format(pin=apn), timeout=40.0)
                r.raise_for_status()
                return apn, parse(r.text)
            except Exception:
                if attempt == 3:
                    return apn, (None, None, None)
                await asyncio.sleep(1.5 * (attempt + 1))
    return apn, (None, None, None)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    c = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    await c.execute("SET statement_timeout = 0")
    jid = await c.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", _MONTCO + "%")
    rows = await c.fetch(
        f"SELECT DISTINCT p.apn FROM parcels p "
        f"JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 {_LAT} "
        f"WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC} AND p.apn IS NOT NULL", jid)
    apns = [r["apn"] for r in rows]
    if args.limit:
        apns = apns[:args.limit]
    print(f"Montgomery PA needle parcels: {len(apns)}", flush=True)

    sem = asyncio.Semaphore(_CONCURRENCY)
    recs = []
    done = 0
    async with httpx.AsyncClient(headers=_UA, follow_redirects=True) as cl:
        tasks = [asyncio.ensure_future(_fetch(cl, a, sem)) for a in apns]
        for fut in asyncio.as_completed(tasks):
            apn, (owner, addr, csz) = await fut
            done += 1
            if owner or addr or csz:
                recs.append((apn, owner, addr, csz))
            if done % 100 == 0 or done == len(apns):
                print(f"  fetched {done}/{len(apns)} -> {len(recs)} with data", end="\r", flush=True)
    print()
    print(f"records: {len(recs)}  owner={sum(1 for _,o,_,_ in recs if o)}  mailing={sum(1 for _,_,a,_ in recs if a)}")
    for apn, owner, addr, csz in recs[:6]:
        print(f"  {apn}: owner={owner!r} MAIL={addr!r} | {csz!r}")
    if not args.apply:
        print("\ndry-run — re-run with --apply")
        await c.close()
        return
    await c.executemany(
        "UPDATE parcels SET owner_name=COALESCE(owner_name,$2), "
        "owner_mailing_address=COALESCE(owner_mailing_address,$3), "
        "owner_mailing_csz=COALESCE(owner_mailing_csz,$4) WHERE jurisdiction_id=$5 AND apn=$1",
        [(apn, owner, addr, csz, jid) for apn, owner, addr, csz in recs])
    cov = await c.fetchrow(
        f"SELECT count(*) n, count(*) FILTER (WHERE p.owner_mailing_address IS NOT NULL) m, "
        f"count(*) FILTER (WHERE p.owner_name IS NOT NULL) o "
        f"FROM parcels p JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
        f"{_LAT} WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC}", jid)
    print(f"APPLIED -> Montgomery PA LGC needles {cov['n']}: mailing={cov['m']} "
          f"({100.0*cov['m']/max(cov['n'],1):.0f}%) owner={cov['o']}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
