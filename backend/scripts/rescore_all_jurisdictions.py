"""Re-score every jurisdiction's parcels under the buy-box filters.

Run this after ANY change to the composite scoring formula in
``app/services/buybox_scoring.py`` — existing ``parcel_buybox_scores`` rows
were computed with the old weights and are stale until re-scored. The daily
digest ranks off these rows, so a mixed-formula table ranks incoherently.

Enumerates jurisdictions (needle-priority) and, per jurisdiction, either:
  - calls ``auto_score_jurisdiction`` (default: scores the is_default seed
    filters AND the dashboardEnabled board filters), or
  - with ``--filter``, scores only the given buybox_filter UUIDs directly via
    ``score_jurisdiction`` (e.g. to refresh just the board's "Hot deals" /
    "LGC Hot deals" filters).

Resumable: ``--start-index N`` skips the first N jurisdictions in the
deterministic order (instant, no per-row lookups) — use it to continue a
paused/interrupted run. ``--resume`` is the slower content-based fallback.

USAGE (from backend/):
    python scripts/rescore_all_jurisdictions.py                       # all
    python scripts/rescore_all_jurisdictions.py --jurisdiction <uuid>  # one
    python scripts/rescore_all_jurisdictions.py --filter <uuid>[,<uuid>]
    python scripts/rescore_all_jurisdictions.py --start-index 28       # resume
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

from app.services.buybox_scoring import (  # noqa: E402
    auto_score_jurisdiction, score_jurisdiction,
)


async def _load_filters(filter_ids: list[uuid.UUID]) -> list[tuple[uuid.UUID, dict]]:
    """Fetch (id, filter_json) for explicit --filter targets (e.g. the
    dashboardEnabled board filters), so we can score them directly via
    score_jurisdiction rather than auto_score_jurisdiction's default set."""
    conn = await asyncpg.connect(get_sync_dsn())
    try:
        rows = await conn.fetch(
            "SELECT id, filter_json FROM buybox_filters WHERE id = ANY($1::uuid[])",
            filter_ids,
        )
    finally:
        await conn.close()
    out = []
    for r in rows:
        fj = r["filter_json"]
        fj = json.loads(fj) if isinstance(fj, str) else (fj or {})
        out.append((r["id"], fj))
    return out


async def _jurisdiction_ids(only: uuid.UUID | None) -> list[uuid.UUID]:
    if only is not None:
        return [only]
    # Enumerate from the small jurisdictions table (instant), needle-priority
    # first — NOT a GROUP BY over all ~millions of parcels (which blows the
    # statement timeout). Empty jurisdictions score 0 rows, harmless.
    conn = await asyncpg.connect(get_sync_dsn())
    try:
        await conn.execute("SET statement_timeout = 0")
        rows = await conn.fetch(
            """
            SELECT j.id
              FROM jurisdictions j
              LEFT JOIN needle_snapshot ns ON ns.jurisdiction_id = j.id
             ORDER BY COALESCE(ns.storage_needles, 0) + COALESCE(ns.lgc_needles, 0) DESC,
                      j.id
            """
        )
    finally:
        await conn.close()
    return [r["id"] for r in rows]


async def _recently_scored(conn, jid: uuid.UUID, hours: int = 12) -> bool:
    """True if this jurisdiction already has buybox scores computed within the
    last `hours` (already done this session). Content-based resume fallback;
    prefer --start-index (this join can be slow without a computed_at index).

    CAUTION — this is EXISTENCE-based, and scoring commits in 5,000-row chunks
    with no enclosing transaction (see _UPSERT_SQL usage in buybox_scoring), so a
    jurisdiction interrupted mid-write has SOME fresh rows and will be treated
    here as fully done. --resume can therefore permanently skip a partially
    scored jurisdiction. To confirm real coverage use the count-based
    scripts/audit_score_coverage.py, which compares scored rows against total
    parcels instead of asking whether any row exists.
    """
    return bool(await conn.fetchval(
        f"""
        SELECT EXISTS (
            SELECT 1 FROM parcel_buybox_scores pbs
              JOIN parcels p ON p.id = pbs.parcel_id
             WHERE p.jurisdiction_id = $1
               AND pbs.computed_at > now() - interval '{hours} hours'
             LIMIT 1
        )
        """, jid))


async def main() -> None:
    ap = argparse.ArgumentParser(description="Re-score all jurisdictions.")
    ap.add_argument("--jurisdiction", type=str, default=None,
                    help="Only re-score this jurisdiction UUID.")
    ap.add_argument("--resume", action="store_true",
                    help="Skip jurisdictions already scored in the last 12h "
                         "(slower content-based resume of an interrupted run).")
    ap.add_argument("--start-index", type=int, default=0,
                    help="Skip the first N jurisdictions in the (deterministic) "
                         "needle-priority order — instant resume with no per-row "
                         "DB lookups. Prefer this over --resume for a clean pause.")
    ap.add_argument("--end-index", type=int, default=None,
                    help="Stop before this index (exclusive) in the ordered list. "
                         "With --start-index, bounds a worker to a disjoint slice "
                         "for safe 2-worker parallelism (no overlap/redo).")
    ap.add_argument("--retries", type=int, default=4,
                    help="Per-jurisdiction retries on TRANSIENT connection errors. "
                         "An overnight run lost 2 of its first 9 counties to "
                         "mid-query connection drops without this.")
    ap.add_argument("--filter", type=str, default=None,
                    help="Comma-separated buybox_filter UUIDs to score directly "
                         "(e.g. the dashboardEnabled board filters). When omitted, "
                         "scores auto_score_jurisdiction's default+board set.")
    args = ap.parse_args()
    only = uuid.UUID(args.jurisdiction) if args.jurisdiction else None

    target_filters = None
    if args.filter:
        fids = [uuid.UUID(x.strip()) for x in args.filter.split(",") if x.strip()]
        target_filters = await _load_filters(fids)
        got = {str(f[0]) for f in target_filters}
        missing = [str(f) for f in fids if str(f) not in got]
        if missing:
            print(f"ERROR: filter(s) not found: {missing}", flush=True)
            sys.exit(2)
        print(f"Scoring {len(target_filters)} explicit filter(s): "
              f"{[str(f[0])[:8] for f in target_filters]}", flush=True)

    jids_all = await _jurisdiction_ids(only)
    start = max(args.start_index, 0)
    end = args.end_index if args.end_index is not None else len(jids_all)
    jids = jids_all[start:end]
    n_all = len(jids_all)
    print(f"Re-scoring {len(jids)} of {n_all} jurisdiction(s) "
          f"(index {start}..{end})…", flush=True)

    skip_conn = await asyncpg.connect(get_sync_dsn()) if args.resume else None
    if skip_conn is not None:
        await skip_conn.execute("SET statement_timeout = 0")

    total = 0
    failures: list[tuple[uuid.UUID, str]] = []
    for offset, jid in enumerate(jids):
        i = start + offset + 1  # absolute position in the full ordered list
        t0 = time.monotonic()
        if skip_conn is not None and await _recently_scored(skip_conn, jid):
            print(f"  [{i}/{n_all}] {jid}  already scored — skip", flush=True)
            continue
        # Retry TRANSIENT connection failures. Without this an overnight run lost
        # 2 of its first 9 counties to "connection was closed in the middle of
        # operation" — the network drops mid-query and a multi-hour scoring pass
        # has many chances to be hit. Mirrors the same guard in
        # backfill_radial_population. A genuine error still records and moves on.
        for attempt in range(1, max(args.retries, 1) + 1):
            try:
                if target_filters is not None:
                    n = 0
                    for fid, fjson in target_filters:
                        n += await score_jurisdiction(jid, fid, fjson)
                else:
                    n = await auto_score_jurisdiction(jid)
                total += n
                print(f"  [{i}/{n_all}] {jid}  scored={n:,}  "
                      f"({time.monotonic() - t0:.1f}s)", flush=True)
                break
            except Exception as e:  # keep going; report at the end
                msg = str(e).lower()
                transient = any(t in msg for t in (
                    "connection", "closed", "getaddrinfo", "timeout",
                    "terminating", "server closed"))
                if attempt < args.retries and transient:
                    print(f"  [{i}/{n_all}] {jid}  transient {type(e).__name__}, "
                          f"retry {attempt}/{args.retries}", flush=True)
                    await asyncio.sleep(8)
                    continue
                failures.append((jid, str(e)))
                print(f"  [{i}/{n_all}] {jid}  FAILED: {e}", flush=True)
                break

    if skip_conn is not None:
        await skip_conn.close()

    print(f"\nDone. {total:,} parcel-scores upserted across {len(jids)} of "
          f"{n_all} jurisdiction(s).", flush=True)
    if failures:
        print(f"{len(failures)} jurisdiction(s) failed:", flush=True)
        for jid, msg in failures:
            print(f"  {jid}: {msg}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
