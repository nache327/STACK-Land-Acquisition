"""Bucket C — Bucks County PA owner + mailing.

Two public sources joined by APN (= PARCEL_NUM = BOA pin, dashed):
  * owner name  <- Bucks County GIS parcel layer (OWNER1/OWNER2/CARE_OF)
  * MAILING     <- Bucks County Board of Assessment Vision datalet
                   (buckscountyboa.org/Datalets/Datalet.aspx?UseSearch=no&pin=<apn>),
                   'Parcel Mailing Details' table — same Tyler/Vision system as Fairfax iCare.

The GIS layer carries only the situs address (no mailing); the BOA datalet carries
the mailing but not owner name on its default tab — so we take each from where it lives
and join on the shared APN. Needle-scoped, idempotent COALESCE-fill.

    python scripts/_repull_bucks_boa.py --limit 15     # dry-run
    python scripts/_repull_bucks_boa.py --apply
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
_BUCKS = "b5fb97a5"
_GIS = "https://services3.arcgis.com/SP47Tddf7RK32lBU/arcgis/rest/services/Bucks_County_Parcels/FeatureServer/0"
_BOA = "https://www.buckscountyboa.org/Datalets/Datalet.aspx?UseSearch=no&pin={pin}"
_CONCURRENCY = 4

_LGC = ("(v.ss IN ('permitted','conditional') OR v.mw IN ('permitted','conditional') "
        "OR v.li IN ('permitted','conditional'))")
_LAT = """JOIN LATERAL (SELECT self_storage::text ss, mini_warehouse::text mw,
  light_industrial::text li FROM zone_use_matrix m WHERE m.jurisdiction_id=p.jurisdiction_id
  AND m.zone_code=p.zoning_code AND (m.municipality IS NULL OR m.municipality=p.city)
  AND m.deleted_at IS NULL AND m.human_reviewed ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true"""
_W = "p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"
_SENT = {"", "nan", "null", "none", "n/a", ".", "&nbsp;"}


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = " ".join(s.replace("&nbsp;", " ").split()).strip().strip(",").strip()
    return None if s.lower() in _SENT else (s or None)


def _table_cells(html: str, table_id: str) -> list[str]:
    m = re.search(r"id='" + re.escape(table_id) + r"'(.*?)</table>", html, re.S | re.I)
    if not m:
        return []
    return [_clean(re.sub("<[^>]+>", " ", t)) or ""
            for t in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S | re.I)]


def parse_boa_mailing(html: str) -> tuple[str | None, str | None]:
    """(mailing_address_line, city_state_zip) from the BOA 'Parcel Mailing Details' table."""
    cells = _table_cells(html, "Parcel Mailing Details")
    if not cells:
        return None, None
    street = co = csz = None
    for i, c in enumerate(cells):
        if c == "Mailing Address" and i + 1 < len(cells):
            street = cells[i + 1] or None
        if c == "In Care Of" and i + 1 < len(cells):
            co = cells[i + 1] or None
    # csz = last cell matching "<CITY> <ST> <ZIP>"
    for c in reversed(cells):
        if c and re.search(r"[A-Z]{2}\s+\d{5}", c):
            csz = c
            break
    # address line = street, with c/o appended when present (normalized to a single C/O prefix)
    addr = street
    if co:
        co_txt = co if co.upper().startswith("C/O") else f"C/O {co}"
        addr = f"{street} {co_txt}" if street else co_txt
    return addr, csz


async def _fetch_mail(cl, apn, sem):
    async with sem:
        for attempt in range(4):
            try:
                r = await cl.get(_BOA.format(pin=apn), timeout=40.0)
                r.raise_for_status()
                return apn, parse_boa_mailing(r.text)
            except Exception:
                if attempt == 3:
                    return apn, (None, None)
                await asyncio.sleep(1.5 * (attempt + 1))
    return apn, (None, None)


async def _gis_owners(cl, apns: list[str]) -> dict[str, str | None]:
    """{apn: owner_name} from Bucks GIS via PARCEL_NUM batches."""
    out: dict[str, str | None] = {}
    for i in range(0, len(apns), 100):
        chunk = apns[i:i + 100]
        vals = ",".join("'" + a.replace("'", "''") + "'" for a in chunk)
        try:
            r = await cl.post(_GIS + "/query", data={
                "where": f"PARCEL_NUM IN ({vals})", "outFields": "PARCEL_NUM,OWNER1,OWNER2",
                "returnGeometry": "false", "f": "json"})
            for f in r.json().get("features", []):
                a = f["attributes"]
                o = " & ".join(x for x in (_clean(a.get("OWNER1")), _clean(a.get("OWNER2"))) if x) or None
                out[str(a.get("PARCEL_NUM"))] = o
        except Exception as e:
            print(f"  !! GIS batch {i}: {e}")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    c = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    await c.execute("SET statement_timeout = 0")
    jid = await c.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", _BUCKS + "%")
    rows = await c.fetch(
        f"SELECT DISTINCT p.apn FROM parcels p "
        f"JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 {_LAT} "
        f"WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC} AND p.apn IS NOT NULL", jid)
    apns = [r["apn"] for r in rows]
    if args.limit:
        apns = apns[:args.limit]
    print(f"Bucks needle parcels: {len(apns)}", flush=True)

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(headers=_UA, follow_redirects=True) as cl:
        owners = await _gis_owners(cl, apns)
        print(f"GIS owners matched: {sum(1 for v in owners.values() if v)}/{len(apns)}", flush=True)
        recs = []
        done = 0
        tasks = [asyncio.ensure_future(_fetch_mail(cl, a, sem)) for a in apns]
        for fut in asyncio.as_completed(tasks):
            apn, (addr, csz) = await fut
            done += 1
            owner = owners.get(apn)
            if addr or csz or owner:
                recs.append((apn, owner, addr, csz))
            if done % 100 == 0 or done == len(apns):
                print(f"  BOA mailing {done}/{len(apns)}", end="\r", flush=True)
    print()
    with_mail = sum(1 for _, _, a, _ in recs if a)
    with_own = sum(1 for _, o, _, _ in recs if o)
    print(f"records: {len(recs)}  owner={with_own}  mailing={with_mail}")
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
    print(f"APPLIED -> Bucks LGC needles {cov['n']}: mailing={cov['m']} "
          f"({100.0*cov['m']/max(cov['n'],1):.0f}%) owner={cov['o']}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
