"""One-off acreage repairs behind the garage-condo (keep) land ranking — 2026-10-19.

Two defects made non-sites look like 5+ acre land deals on the LGC board:

1. ALLENTOWN PA (jurisdiction 'Allentown, PA'). scripts/setup_allentown.py stored
   ``acres = Shape__Area / 4046.856`` — it treated the City_Landuse layer's Shape__Area
   as square METRES, but that service is in PA State Plane South (US survey FEET), so
   every acreage is square feet ÷ 4046.856 = true acres × 10.764 (43,560 / 4,046.86).
   Repair: the rows whose stored acres ≈ 10.76 × the geodetic geometry area get the
   geodetic area, exactly as scripts/_backfill_acres_from_geom.py writes it
   (``ST_Area(geom::geography) / 4046.8564224``, rounded to 3 dp). Rows whose stored
   acres already agree with the geometry are untouched.

2. NJ CONDO UNITS. MOD-IV publishes one record per condo unit, each carrying the WHOLE
   lot's acreage (e.g. 0219_3652_1_C1433 … one Fort Lee complex, every unit 5.219 ac).
   A unit is identified as either
     (a) a 'C…' condo QUALIFIER on the PAMS PIN (MUN_BLOCK_LOT_Cxxxx), grouped by the
         PIN without the qualifier, or
     (b) two or more distinct APNs in one jurisdiction sharing an IDENTICAL geometry
         (e.g. Denville 1408_50001_3.01 … 3.40, 38 units on one 9.5-ac polygon).
   Only groups whose members all carry the same acreage (within 1%) are touched — that
   is the signature of the lot acreage copied onto every unit. Repair (least invasive
   that removes them from the land ranking without deleting any parcel): each unit's
   acres = lot acres ÷ unit count (its undivided share of the land, floored at 0.001;
   a share still >= 1.5 ac is capped by the drawn geometry's share), then its
   parcel_keep_metrics row is deleted (the keep precompute only measures parcels
   >= 1.5 ac, so it won't recreate them). The mother lot (the PIN with no qualifier,
   when present) is left as is.

A backup CSV of EVERY changed row (old + new acres; full parcel_keep_metrics row JSON
for deletions) is written BEFORE any write. Dry run by default.

USAGE (from backend/):
  python scripts/_repair_keep_acreage_2026_10_19.py                 # dry run, both
  python scripts/_repair_keep_acreage_2026_10_19.py --only allentown
  python scripts/_repair_keep_acreage_2026_10_19.py --apply --backup <csv>
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

_SQM_PER_ACRE = 4046.8564224  # matches _backfill_acres_from_geom.py / ingestion
# Square feet ÷ square metres-per-acre ⇒ true acres × 43560/4046.8564224 = 10.7639.
SQFT_AS_SQM_RATIO = 43_560.0 / _SQM_PER_ACRE
_RATIO_LO, _RATIO_HI = 10.0, 11.5

ALLENTOWN_JURISDICTION = "Allentown, PA"

_ALLENTOWN_SQL = f"""
SELECT p.id, p.apn, p.jurisdiction_id::text AS jid, p.city,
       p.acres::float8 AS old_acres,
       round((ST_Area(p.geom::geography) / {_SQM_PER_ACRE})::numeric, 3)::float8 AS new_acres
  FROM parcels p
  JOIN jurisdictions j ON j.id = p.jurisdiction_id
 WHERE j.name = $1
   AND p.city ILIKE 'Allentown%'
   AND p.geom IS NOT NULL
   AND p.acres > 0
   AND ST_Area(p.geom::geography) > 0
   AND p.acres / (ST_Area(p.geom::geography) / {_SQM_PER_ACRE})
       BETWEEN {_RATIO_LO} AND {_RATIO_HI}
"""

# NJ candidates: parcels >= 1.5 ac (only those can masquerade as sites).
_NJ_SQL = """
SELECT p.id, p.apn, p.jurisdiction_id::text AS jid, p.city, p.acres::float8 AS acres,
       md5(ST_AsBinary(p.geom)) AS geom_hash,
       (ST_Area(p.geom::geography) / 4046.8564224)::float8 AS geo_acres,
       (k.parcel_id IS NOT NULL) AS has_keep
  FROM parcels p
  JOIN jurisdictions j ON j.id = p.jurisdiction_id
  LEFT JOIN parcel_keep_metrics k ON k.parcel_id = p.id
 WHERE coalesce(p.state, j.state) = 'NJ'
   AND p.acres >= 1.5
   AND p.geom IS NOT NULL
"""


def ratio_is_sqft_as_sqm(stored: float, geodetic: float) -> bool:
    """True when stored acres ≈ 10.76 × the geometry's acres (sq ft read as sq m)."""
    if not stored or not geodetic or geodetic <= 0:
        return False
    return _RATIO_LO <= stored / geodetic <= _RATIO_HI


def condo_base(apn: str | None) -> str | None:
    """PAMS PIN without a 'C…' condo qualifier: '0219_3652_1_C1433' → '0219_3652_1'.

    None when the PIN carries no condo qualifier (4th '_' part starting with C)."""
    if not apn:
        return None
    parts = str(apn).split("_")
    if len(parts) >= 4 and parts[3][:1].upper() == "C":
        return "_".join(parts[:3])
    return None


def condo_groups(rows: list[dict]) -> tuple[dict[str, list[dict]], Counter]:
    """Group NJ unit rows into condo groups → {group_key: [rows]} plus skip reasons.

    A row joins its qualifier group (jid|base) when its PIN has a C-qualifier, else its
    identical-geometry group (jid|hash) when >= 2 distinct APNs share the geometry.
    Groups need >= 2 distinct APNs and a uniform acreage (max − min <= 1% of max)."""
    by_geom: dict[str, set[str]] = {}
    for r in rows:
        by_geom.setdefault(f"{r['jid']}|{r['geom_hash']}", set()).add(r["apn"])
    groups: dict[str, list[dict]] = {}
    for r in rows:
        base = condo_base(r["apn"])
        if base:
            key = f"Q|{r['jid']}|{base}"
        elif len(by_geom[f"{r['jid']}|{r['geom_hash']}"]) >= 2:
            key = f"G|{r['jid']}|{r['geom_hash']}"
        else:
            continue
        groups.setdefault(key, []).append(r)
    skipped: Counter = Counter()
    out: dict[str, list[dict]] = {}
    for key, members in groups.items():
        if len({m["apn"] for m in members}) < 2:
            skipped["single_unit"] += 1
            continue
        acres = [m["acres"] for m in members]
        if max(acres) - min(acres) > 0.01 * max(acres):
            skipped["non_uniform_acres"] += 1
            continue
        out[key] = members
    return out, skipped


def lot_acres(members: list[dict]) -> float:
    """The lot's acreage = the acreage copied onto every unit."""
    return max(m["acres"] for m in members)


def group_geo_acres(members: list[dict]) -> float | None:
    geo = [m.get("geo_acres") for m in members if m.get("geo_acres")]
    return max(geo) if geo else None


UNIT_ACRES_FLOOR = 0.001  # never 0: acres = 0 means "never measured" to _backfill_acres_from_geom


def unit_acres(lot: float, n_units: int, geo: float | None = None) -> float:
    """A unit's undivided share of the lot: lot ÷ units, floored at 0.001 ac.

    When the share is STILL >= 1.5 ac (the copied acreage itself is inflated, e.g. 52,700
    'acres' on a Montclair unit) it is capped by the drawn geometry's share (geo ÷ units),
    so the unit can't stay on the land ranking on a bad number. The cap is not applied
    to ordinary shares: many unit geometries are just the unit's footprint."""
    u = lot / n_units
    if u >= 1.5 and geo:
        u = min(u, geo / n_units)
    return max(round(u, 3), UNIT_ACRES_FLOOR)


async def _allentown(conn) -> list[dict]:
    rows = [dict(r) for r in await conn.fetch(_ALLENTOWN_SQL, ALLENTOWN_JURISDICTION)]
    tot = await conn.fetchrow(
        f"""SELECT count(*) n, sum(p.acres)::float8 stored,
                   sum(ST_Area(p.geom::geography) / {_SQM_PER_ACRE})::float8 geo
              FROM parcels p JOIN jurisdictions j ON j.id = p.jurisdiction_id
             WHERE j.name = $1 AND p.city ILIKE 'Allentown%' AND p.geom IS NOT NULL""",
        ALLENTOWN_JURISDICTION,
    )
    keep_ids = {r["parcel_id"] for r in await conn.fetch(
        "SELECT parcel_id FROM parcel_keep_metrics WHERE parcel_id = ANY($1::bigint[])",
        [r["id"] for r in rows])}
    print(f"[allentown] city parcels {tot['n']:,}: stored {tot['stored']:,.0f} ac vs "
          f"geodetic {tot['geo']:,.0f} ac")
    print(f"[allentown] {len(rows):,} rows at ~{SQFT_AS_SQM_RATIO:.3f}x geometry: "
          f"{sum(r['old_acres'] for r in rows):,.0f} ac -> "
          f"{sum(r['new_acres'] for r in rows):,.0f} ac")
    kr = [r for r in rows if r["id"] in keep_ids]
    print(f"[allentown] of which keep candidates: {len(kr):,} "
          f"({sum(r['old_acres'] for r in kr):,.0f} ac -> "
          f"{sum(r['new_acres'] for r in kr):,.0f} ac); "
          f">=5 ac before {sum(1 for r in kr if r['old_acres'] >= 5):,}, "
          f"after {sum(1 for r in kr if r['new_acres'] >= 5):,}; "
          f">=1.5 ac after {sum(1 for r in kr if r['new_acres'] >= 1.5):,}")
    for r in rows:
        r["repair"] = "allentown_sqft_as_sqm"
        r["has_keep"] = r["id"] in keep_ids
    return rows


_NJ_RESTORE_SQL = """
SELECT p.id, p.apn, p.jurisdiction_id::text AS jid, p.city,
       p.acres::float8 AS current_acres,
       md5(ST_AsBinary(p.geom)) AS geom_hash,
       (ST_Area(p.geom::geography) / 4046.8564224)::float8 AS geo_acres,
       (k.parcel_id IS NOT NULL) AS has_keep
  FROM parcels p
  LEFT JOIN parcel_keep_metrics k ON k.parcel_id = p.id
 WHERE p.id = ANY($1::bigint[])
"""


def read_backup_acres(path) -> dict[int, float]:
    """parcel_id → ORIGINAL acres of the nj_condo_unit rows in a backup CSV."""
    out: dict[int, float] = {}
    with Path(path).open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["table"] == "parcels" and r["repair"].startswith("nj_condo_unit"):
                out[int(r["parcel_id"])] = float(r["old_acres"])
    return out


async def _nj_condos(conn, restore: dict[int, float] | None = None) -> list[dict]:
    """Detect + split condo units. With ``restore`` (parcel_id → original acres from an
    earlier backup) the same rows are regrouped on their ORIGINAL acreage — used to
    redo a split after a rule change, since a split unit no longer passes acres >= 1.5."""
    if restore:
        rows = [dict(r) for r in await conn.fetch(_NJ_RESTORE_SQL, list(restore))]
        for r in rows:
            r["acres"] = restore[r["id"]]
    else:
        rows = [dict(r) for r in await conn.fetch(_NJ_SQL)]
    groups, skipped = condo_groups(rows)
    out = []
    sizes = Counter()
    for key, members in groups.items():
        n = len(members)
        sizes["2" if n == 2 else "3-9" if n < 10 else "10-49" if n < 50 else "50+"] += 1
        lot = lot_acres(members)
        geo = group_geo_acres(members)
        for m in members:
            out.append({
                "repair": "nj_condo_unit_" + ("qualifier" if key.startswith("Q|") else "shared_geom"),
                "id": m["id"], "apn": m["apn"], "jid": m["jid"], "city": m["city"],
                "old_acres": m.get("current_acres", m["acres"]),
                "new_acres": unit_acres(lot, n, geo),
                "has_keep": m["has_keep"], "group": key, "units": n,
            })
    print(f"[nj-condo] NJ parcels >= 1.5 ac scanned: {len(rows):,}")
    print(f"[nj-condo] {len(groups):,} condo group(s), {len(out):,} unit row(s); "
          f"group sizes {dict(sizes)}; skipped {dict(skipped)}")
    q = sum(1 for r in out if r["repair"].endswith("qualifier"))
    print(f"[nj-condo]   by C-qualifier {q:,}, by shared geometry {len(out) - q:,}")
    print(f"[nj-condo]   with a keep row: {sum(1 for r in out if r['has_keep']):,}; "
          f"still >= 1.5 ac after the split: {sum(1 for r in out if r['new_acres'] >= 1.5):,}")
    by_city = Counter(r["city"] for r in out)
    print("[nj-condo]   top towns: " + ", ".join(f"{c}={n}" for c, n in by_city.most_common(10)))
    return out


def _write_backup(path: Path, changes: list[dict], keep_rows: dict[int, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repair", "table", "action", "parcel_id", "apn", "jurisdiction_id",
                    "city", "old_acres", "new_acres", "row_json"])
        for r in changes:
            w.writerow([r["repair"], "parcels", "update_acres", r["id"], r["apn"], r["jid"],
                        r["city"], r["old_acres"], r["new_acres"], ""])
        for pid, kr in keep_rows.items():
            w.writerow(["nj_condo_unit", "parcel_keep_metrics", "delete", pid, "", "", "",
                        "", "", json.dumps(kr, default=str)])


async def run(args) -> int:
    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, timeout=120)
    try:
        await conn.execute(f"SET statement_timeout = '{int(args.statement_timeout_min)}min'")
        if not args.apply:
            await conn.execute("SET default_transaction_read_only = on")
        changes: list[dict] = []
        if args.only in (None, "allentown"):
            changes += await _allentown(conn)
        nj: list[dict] = []
        if args.only in (None, "nj-condo"):
            restore = read_backup_acres(args.restore_from) if args.restore_from else None
            nj = await _nj_condos(conn, restore)
            changes += nj
        nj_keep_ids = [r["id"] for r in nj if r["has_keep"]]
        if not args.apply:
            print(f"DRY RUN — would update {len(changes):,} parcels.acres and delete "
                  f"{len(nj_keep_ids):,} parcel_keep_metrics row(s)")
            return 0
        if not args.backup:
            raise SystemExit("--apply needs --backup <csv>")
        keep_rows = {r["parcel_id"]: dict(r) for r in await conn.fetch(
            "SELECT * FROM parcel_keep_metrics WHERE parcel_id = ANY($1::bigint[])",
            nj_keep_ids)}
        _write_backup(Path(args.backup), changes, keep_rows)
        print(f"backup written: {args.backup} ({len(changes):,} parcel + "
              f"{len(keep_rows):,} keep row(s))")
        for i in range(0, len(changes), args.batch_size):
            chunk = changes[i:i + args.batch_size]
            async with conn.transaction():
                await conn.execute(
                    """UPDATE parcels p SET acres = v.acres, updated_at = now()
                         FROM unnest($1::bigint[], $2::numeric[]) AS v(id, acres)
                        WHERE p.id = v.id AND p.acres IS DISTINCT FROM v.acres""",
                    [r["id"] for r in chunk], [r["new_acres"] for r in chunk],
                )
        if nj_keep_ids:
            async with conn.transaction():
                res = await conn.execute(
                    "DELETE FROM parcel_keep_metrics WHERE parcel_id = ANY($1::bigint[])",
                    nj_keep_ids)
            print(f"parcel_keep_metrics: {res}")
        ids = [r["id"] for r in changes]
        check = await conn.fetchrow(
            "SELECT count(*) n, sum(acres)::float8 ac FROM parcels WHERE id = ANY($1::bigint[])",
            ids)
        left = await conn.fetchval(
            "SELECT count(*) FROM parcel_keep_metrics WHERE parcel_id = ANY($1::bigint[])",
            nj_keep_ids)
        print(f"verify: {check['n']:,} repaired parcel(s) now sum {check['ac']:,.0f} ac "
              f"(expected {sum(r['new_acres'] for r in changes):,.0f}); "
              f"{left} condo keep row(s) left")
    finally:
        await conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--only", choices=("allentown", "nj-condo"))
    ap.add_argument("--backup", help="backup CSV path (required with --apply)")
    ap.add_argument("--restore-from", help="nj-condo: regroup the units of an earlier "
                    "backup CSV on their ORIGINAL acres (redo a split)")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--statement-timeout-min", type=int, default=20)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:  # pragma: no cover
            pass
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
