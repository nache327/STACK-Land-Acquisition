"""Bucket C — Fairfax County VA owner + mailing from iCare (DTA per-parcel lookup).

Fairfax's public ArcGIS org exposes NO owner-bearing parcel layer (Parcels is
geometry-only; the DTA feature servers are CAMA building characteristics only),
and there is no bulk owner/mailing download. The Dept of Tax Administration's
iCare datalet DOES expose owner name + mailing address per PIN, so we scrape it
for the needle parcels only (~3.6k) — the direct-mail deliverable.

Join: our parcels.apn (e.g. '0022 01  0003A') -> iCare pin (spaces stripped,
'0022010003A'). Verified against real records (owner + mailing returned 6/6,
incl. alpha PINs). Same JOIN-INTEGRITY discipline: pin derives from the parcel's
own apn, and we UPDATE that exact apn. Idempotent COALESCE-fill.

iCare returns mailing as one line (street + city/state/zip); stored whole in
owner_mailing_address (deliverable as-is), owner_mailing_csz left NULL.

    python scripts/_repull_fairfax_icare.py --limit 20          # dry-run sample
    python scripts/_repull_fairfax_icare.py --apply
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
_BASE = "https://icare.fairfaxcounty.gov/ffxcare/Datalets/Datalet.aspx?UseSearch=no&pin={pin}"
_FAIRFAX = "6421e666"
_CONCURRENCY = 4

_LGC = ("(v.ss IN ('permitted','conditional') OR v.mw IN ('permitted','conditional') "
        "OR v.li IN ('permitted','conditional'))")
_LAT = """JOIN LATERAL (SELECT self_storage::text ss, mini_warehouse::text mw,
  light_industrial::text li FROM zone_use_matrix m WHERE m.jurisdiction_id=p.jurisdiction_id
  AND m.zone_code=p.zoning_code AND (m.municipality IS NULL OR m.municipality=p.city)
  AND m.deleted_at IS NULL AND m.human_reviewed ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true"""
_W = "p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"

_SENT = {"", "nan", "null", "none", "n/a", "."}


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = " ".join(s.split()).strip().strip(",").strip()
    return None if s.lower() in _SENT else (s or None)


def _grab(html: str, label: str) -> str | None:
    """Pull the value cell following a datalet label."""
    m = re.search(re.escape(label) + r"\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.S | re.I)
    if not m:
        m = re.search(re.escape(label) + r"(.*?)<", html, re.S | re.I)
    if not m:
        return None
    return _clean(re.sub("<[^>]+>", " ", m.group(1)))


def parse(html: str) -> tuple[str | None, str | None]:
    """(owner_name, mailing_address) from an iCare datalet page."""
    owner = _grab(html, "Name")
    mail = _grab(html, "Mailing Address")
    return owner, mail


async def _fetch_one(cl: httpx.AsyncClient, apn: str, sem: asyncio.Semaphore) -> tuple[str, str | None, str | None]:
    pin = apn.replace(" ", "")
    async with sem:
        for attempt in range(4):
            try:
                r = await cl.get(_BASE.format(pin=pin), timeout=40.0)
                r.raise_for_status()
                owner, mail = parse(r.text)
                return apn, owner, mail
            except Exception:
                if attempt == 3:
                    return apn, None, None
                await asyncio.sleep(1.5 * (attempt + 1))
    return apn, None, None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap parcels (dry-run sampling)")
    args = ap.parse_args()

    c = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    await c.execute("SET statement_timeout = 0")
    jid = await c.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", _FAIRFAX + "%")
    rows = await c.fetch(
        f"SELECT DISTINCT p.apn FROM parcels p "
        f"JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 {_LAT} "
        f"WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC} AND p.apn IS NOT NULL", jid)
    apns = [r["apn"] for r in rows]
    if args.limit:
        apns = apns[:args.limit]
    print(f"Fairfax needle parcels to enrich via iCare: {len(apns)}", flush=True)

    sem = asyncio.Semaphore(_CONCURRENCY)
    recs: list[tuple] = []
    done = 0
    async with httpx.AsyncClient(headers=_UA, follow_redirects=True) as cl:
        tasks = [asyncio.ensure_future(_fetch_one(cl, a, sem)) for a in apns]
        for fut in asyncio.as_completed(tasks):
            apn, owner, mail = await fut
            done += 1
            if owner or mail:
                recs.append((apn, owner, mail))
            if done % 100 == 0 or done == len(apns):
                print(f"  fetched {done}/{len(apns)} -> {len(recs)} with data", end="\r", flush=True)
    print()
    with_mail = sum(1 for _, _, m in recs if m)
    print(f"parsed: {len(recs)}/{len(apns)} rows; with mailing addr: {with_mail}")
    for apn, owner, mail in recs[:6]:
        print(f"  {apn!r}: owner={owner!r} MAIL={mail!r}")

    if not args.apply:
        print("\ndry-run — re-run with --apply")
        await c.close()
        return

    await c.executemany(
        "UPDATE parcels SET owner_name = COALESCE(owner_name, $2), "
        "owner_mailing_address = COALESCE(owner_mailing_address, $3) "
        "WHERE jurisdiction_id=$4 AND apn=$1",
        [(apn, owner, mail, jid) for apn, owner, mail in recs])
    cov = await c.fetchrow(
        f"SELECT count(*) n, count(*) FILTER (WHERE p.owner_mailing_address IS NOT NULL) m, "
        f"count(*) FILTER (WHERE p.owner_name IS NOT NULL) o "
        f"FROM parcels p JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
        f"{_LAT} WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC}", jid)
    print(f"APPLIED -> Fairfax LGC needles {cov['n']}: mailing={cov['m']} "
          f"({100.0*cov['m']/max(cov['n'],1):.0f}%) owner={cov['o']}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
