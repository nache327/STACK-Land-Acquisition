"""Audit board-score coverage per jurisdiction x board filter — COUNT-based.

WHY THIS EXISTS (the trap it replaces)
--------------------------------------
Every freshness check we had was EXISTENCE-based, e.g.::

    SELECT DISTINCT p.jurisdiction_id ... WHERE pbs.computed_at > cutoff
    SELECT EXISTS (SELECT 1 FROM parcel_buybox_scores ... LIMIT 1)   # --resume

That is unsafe here, because scoring commits in 5,000-row chunks via
``executemany`` with NO enclosing transaction (``buybox_scoring.py`` ~:711-715).
A run killed mid-jurisdiction therefore leaves it PARTIALLY scored — and a single
fresh row is enough for an existence check to report the whole jurisdiction done.
It is then skipped forever, and the needle/board gates run over partial data with
no signal at all. On 2026-07-27 the existence check reported ``MISSING=0`` while
only ~48 of 151 jurisdictions had actually been re-scored in the window.

This compares COUNTS instead: freshly-scored rows vs total parcels, per
jurisdiction, per board filter.

DENOMINATOR — read this before changing it
------------------------------------------
``_select_parcels_sql`` filters on ``WHERE p.jurisdiction_id = $1`` and NOTHING
else — no ``centroid IS NOT NULL``, no acreage floor. So the scorer writes one
row per parcel in the jurisdiction, and the correct denominator is ALL parcels.
Using ``centroid IS NOT NULL`` here would shrink the denominator, push coverage
above 100%, and silently flag nothing — reintroducing the same false-clean.

USAGE (from backend/):
    python scripts/audit_score_coverage.py                    # report only
    python scripts/audit_score_coverage.py --apply            # finish the short ones
    python scripts/audit_score_coverage.py --cutoff '2026-07-26 21:00:00+00'
    python scripts/audit_score_coverage.py --force <uuid>,<uuid>

Runs per-jurisdiction (indexed on parcels.jurisdiction_id) rather than as one
50M-row aggregate, so it streams progress instead of looking hung. It is still
the slowest read we have until the ``pbs(buybox_filter_id, computed_at)`` index
lands (audit item A-9) — expect minutes, and prefer running it when a re-score
is NOT competing for the same table.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

# The two dashboardEnabled board filters — the only ones the board/digest read.
SS_FILTER = uuid.UUID("1c5a257d-b971-4ff7-bdf8-1b9b62083879")   # "Hot deals"
LGC_FILTER = uuid.UUID("3f551716-6bcf-48a1-b2a4-389ade963e9f")  # "LGC Hot deals"

# Default cutoff = after the area-weighted 3-mi population backfill FINISHED and
# before the re-score that consumes it STARTED. Scores older than this read the
# superseded tract-centroid population and must be redone.
#
#   backfill finished   2026-07-26 20:18:51 -0600  =  2026-07-27 02:18:51Z
#   re-score started    2026-07-26 21:20:11 -0600  =  2026-07-27 03:20:11Z
#
# No scores were computed in that one-hour gap, so any value inside it is exact.
#
# TIMEZONE TRAP — the first version of this constant read "2026-07-26 21:00:00+00",
# built from the LOCAL wall-clock times above while labelled +00. This machine is
# UTC-6, so that cutoff was six hours EARLY: it sat before the backfill even
# finished, meaning stale-population scores would have counted as fresh and the
# audit would have reported CLEAN over exactly the rows it exists to catch. Always
# convert to UTC before writing a cutoff; computed_at is timestamptz.
DEFAULT_CUTOFF = "2026-07-27 03:00:00+00"

# Complete means every parcel got a row. Slack absorbs parcels inserted mid-run.
COVERAGE_OK = 0.99

# Jurisdictions known to have been interrupted MID-WRITE, so their counts cannot
# be trusted even if they look complete. Both were holding a scoring advisory
# lock when the duplicate re-score was stopped on 2026-07-27. Safe to empty once
# a clean full pass has confirmed them.
KNOWN_INTERRUPTED: list[uuid.UUID] = [
    uuid.UUID("0cf50881-fdf3-4149-8c9f-6db758c4a08f"),  # Sandy, UT
    uuid.UUID("036dffaf-6f33-40b3-a786-09fb613d7f9f"),  # New York, NY
]

_TRANSIENT = ("connection", "closed", "getaddrinfo", "timeout",
              "terminating", "server closed")


async def _connect() -> asyncpg.Connection:
    conn = await asyncpg.connect(get_sync_dsn())
    await conn.execute("SET statement_timeout = 0")
    return conn


async def _jurisdictions(conn) -> list[tuple[uuid.UUID, str]]:
    """Needle-priority order, same as the re-score, so output lines up."""
    rows = await conn.fetch(
        """
        SELECT j.id, j.name
          FROM jurisdictions j
          LEFT JOIN needle_snapshot ns ON ns.jurisdiction_id = j.id
         ORDER BY COALESCE(ns.storage_needles, 0) + COALESCE(ns.lgc_needles, 0) DESC,
                  j.id
        """
    )
    return [(r["id"], r["name"] or str(r["id"])) for r in rows]


async def _n_parcels(conn, jid: uuid.UUID) -> int:
    # ALL parcels — matches _select_parcels_sql's only predicate. See module docstring.
    return int(await conn.fetchval(
        "SELECT count(*) FROM parcels WHERE jurisdiction_id = $1", jid) or 0)


def parse_cutoff(s: str) -> datetime:
    """Cutoff as a REAL tz-aware datetime, not a string.

    asyncpg binds parameters by type, and a str bound to a ``$n::timestamptz``
    placeholder raises
        DataError: invalid input for query argument $3: '...'
                   (expected a datetime.date or datetime.datetime instance)
    It will not cast text to timestamptz the way a psql literal would. This bit
    this project once already on backfill_radial_population's --redo-after.
    Naive input is treated as UTC — a cutoff without an offset is the same
    ambiguity that made this constant six hours wrong in the first place.
    """
    t = s.strip().replace("Z", "+00:00")
    # fromisoformat wants ±HH:MM; "+00" and "+0000" are common shorthands.
    if len(t) >= 3 and t[-3] in "+-":
        t += ":00"
    elif len(t) >= 5 and t[-5] in "+-" and t[-3] != ":":
        t = t[:-2] + ":" + t[-2:]
    dt = datetime.fromisoformat(t)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _n_fresh(conn, jid: uuid.UUID, fid: uuid.UUID, cutoff: datetime) -> int:
    return int(await conn.fetchval(
        """
        SELECT count(*)
          FROM parcels p
          JOIN parcel_buybox_scores pbs
            ON pbs.parcel_id = p.id
           AND pbs.buybox_filter_id = $2
         WHERE p.jurisdiction_id = $1
           AND pbs.computed_at > $3::timestamptz
        """, jid, fid, cutoff) or 0)


async def _filter_json(conn, fid: uuid.UUID) -> dict:
    fj = await conn.fetchval(
        "SELECT filter_json FROM buybox_filters WHERE id = $1", fid)
    return json.loads(fj) if isinstance(fj, str) else (fj or {})


async def main() -> None:
    ap = argparse.ArgumentParser(
        description="Count-based board-score coverage audit.")
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF,
                    help=f"Scores older than this are stale (default {DEFAULT_CUTOFF}).")
    ap.add_argument("--apply", action="store_true",
                    help="Re-score the jurisdictions reported short.")
    ap.add_argument("--force", default=None,
                    help="Extra jurisdiction UUIDs (comma-separated) to treat as "
                         "untrusted regardless of their counts.")
    ap.add_argument("--retries", type=int, default=4,
                    help="Per-jurisdiction retries on TRANSIENT connection errors.")
    args = ap.parse_args()

    forced = set(KNOWN_INTERRUPTED)
    if args.force:
        forced |= {uuid.UUID(x.strip()) for x in args.force.split(",") if x.strip()}

    cutoff = parse_cutoff(args.cutoff)
    conn = await _connect()
    short: list[tuple[uuid.UUID, str, uuid.UUID, int, int, float, bool]] = []
    try:
        jurisdictions = await _jurisdictions(conn)
        print(f"auditing {len(jurisdictions)} jurisdiction(s) x 2 board filters, "
              f"cutoff {args.cutoff}", flush=True)

        n_ok = n_empty = 0
        # Heartbeat. Without it this loop prints ONLY exceptions, so a long clean
        # stretch is indistinguishable from a hang — 20+ minutes of silence during
        # which the only honest status report was "no idea how far it is". Every
        # PROGRESS_EVERY jurisdictions, say where we are.
        PROGRESS_EVERY = 10
        for i, (jid, name) in enumerate(jurisdictions, 1):
            if i % PROGRESS_EVERY == 1:
                print(f"  ... [{i}/{len(jurisdictions)}] scanning "
                      f"(complete so far: {n_ok} pairs, short: {len(short)})",
                      flush=True)
            n_p = await _n_parcels(conn, jid)
            if n_p == 0:
                n_empty += 1
                continue
            for fid in (SS_FILTER, LGC_FILTER):
                n_f = await _n_fresh(conn, jid, fid, cutoff)
                share = n_f / n_p
                is_forced = jid in forced
                if share < COVERAGE_OK or is_forced:
                    short.append((jid, name, fid, n_p, n_f, share, is_forced))
                    tag = "MID-WRITE" if is_forced else "partial  "
                    lane = "SS " if fid == SS_FILTER else "LGC"
                    print(f"  [{i}/{len(jurisdictions)}] {tag} {lane} "
                          f"{name[:32]:<32} {n_f:>9,}/{n_p:<9,} ({share:6.1%})",
                          flush=True)
                else:
                    n_ok += 1

        print(f"\ncomplete pairs: {n_ok}   SHORT pairs: {len(short)}   "
              f"empty jurisdictions skipped: {n_empty}", flush=True)
        if not short:
            print("=== CLEAN: every jurisdiction fully covered on both board "
                  "filters ===", flush=True)
            return
        if not args.apply:
            print("\nreport only — re-run with --apply to re-score the above",
                  flush=True)
            return
        fjs = {SS_FILTER: await _filter_json(conn, SS_FILTER),
               LGC_FILTER: await _filter_json(conn, LGC_FILTER)}
    finally:
        await conn.close()

    print(f"\napplying: re-scoring {len(short)} short pair(s)", flush=True)
    failures: list[tuple[uuid.UUID, str]] = []
    for jid, name, fid, *_ in short:
        lane = "SS " if fid == SS_FILTER else "LGC"
        for attempt in range(1, max(args.retries, 1) + 1):
            try:
                n = await score_jurisdiction(jid, fid, fjs[fid])
                print(f"  rescored {lane} {name[:32]:<32} scored={n:,}", flush=True)
                break
            except Exception as e:
                msg = str(e).lower()
                if attempt < args.retries and any(t in msg for t in _TRANSIENT):
                    print(f"  {lane} {name[:32]} transient {type(e).__name__}, "
                          f"retry {attempt}/{args.retries}", flush=True)
                    await asyncio.sleep(8)
                    continue
                failures.append((jid, str(e)))
                print(f"  {lane} {name[:32]} FAILED: {e}", flush=True)
                break

    if failures:
        print(f"\n{len(failures)} pair(s) failed:", flush=True)
        for jid, msg in failures:
            print(f"  {jid}: {msg}", flush=True)
        sys.exit(1)
    print("\n=== applied — re-run WITHOUT --apply to confirm CLEAN ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
