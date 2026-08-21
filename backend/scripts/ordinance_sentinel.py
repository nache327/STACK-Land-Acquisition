"""Monthly primary-source ordinance drift sentinel (freshness plan, Phase A).

Refreshes the CURRENT fingerprint for the stalest monitored munis (see
``app/models/ordinance_fingerprint.py``), compares against the BASELINE
captured when the muni was grounded, and stamps ``drift_detected_at`` /
``drift_reason`` on mismatch. Drift is sticky until a human re-grounds the
muni from the primary source and clears it with ``--rebaseline``.

Runs from the watchdog tick in capped batches (Railway cron container — httpx
only, no Playwright: headless Chromium OOMs that container), or by hand:

  python scripts/ordinance_sentinel.py                    # stalest 25
  python scripts/ordinance_sentinel.py --limit 5 --dry-run
  python scripts/ordinance_sentinel.py --report           # open drift queue
  python scripts/ordinance_sentinel.py --report --write-queue-file
  python scripts/ordinance_sentinel.py --rebaseline "https://ecode360.com/..."

Exit codes: 0 = ran clean (drift is DATA — recorded in the DB and printed
loud, never an error exit); 1 = operational fetch/DB errors.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402
import httpx  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from app.services.ordinance_freshness import (  # noqa: E402
    _FETCH_TIMEOUT,
    decide_drift,
    fingerprint_url,
)

_BATCH_LIMIT = 25
_MIN_AGE_DAYS = 30
_POLITENESS_SLEEP_S = 2.0
_QUEUE_FILE = Path(__file__).resolve().parents[2] / "outputs" / "_reverify_queue.md"


async def _connect() -> asyncpg.Connection:
    conn = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
    await conn.execute("SET statement_timeout = 0")
    return conn


async def run_batch(limit: int, min_age_days: int, dry_run: bool) -> int:
    conn = await _connect()
    try:
        if not await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended('ordinance_sentinel', 42))"
        ):
            print("sentinel: another run holds the lock; skipping", file=sys.stderr)
            return 0
        rows = await conn.fetch(
            """SELECT id, municipality, state, ordinance_url, municode_product_id,
                      baseline_hash, baseline_new_laws, baseline_job_id,
                      drift_detected_at
                 FROM ordinance_fingerprints
                WHERE fetched_at IS NULL
                   OR fetched_at < now() - ($1 || ' days')::interval
                ORDER BY fetched_at ASC NULLS FIRST
                LIMIT $2""",
            str(min_age_days),
            limit,
        )
        if not rows:
            print("sentinel: nothing stale — all fingerprints current")
            return 0

        errors = 0
        drifts = 0
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            for i, row in enumerate(rows):
                if i:
                    await asyncio.sleep(_POLITENESS_SLEEP_S)
                fp = await fingerprint_url(
                    row["ordinance_url"],
                    municode_product_id=row["municode_product_id"],
                    client=client,
                )
                label = f"{row['municipality']}, {row['state'] or '??'}"

                if fp.chapter_hash is None and fp.new_laws_count is None and fp.municode_job_id is None:
                    errors += 1
                    print(f"sentinel ERROR  {label}: {fp.error}", file=sys.stderr)
                    if not dry_run:
                        await conn.execute(
                            """UPDATE ordinance_fingerprints
                                  SET fetched_at=now(), fetch_error=$2, updated_at=now()
                                WHERE id=$1""",
                            row["id"],
                            (fp.error or "no signals extracted")[:1000],
                        )
                    continue

                # First sight of a signal becomes its baseline (per-signal:
                # municode rows never grow a hash; ecode rows never a job id).
                baseline_hash = row["baseline_hash"] or fp.chapter_hash
                baseline_new_laws = (
                    row["baseline_new_laws"]
                    if row["baseline_new_laws"] is not None
                    else fp.new_laws_count
                )
                baseline_job_id = row["baseline_job_id"] or fp.municode_job_id

                drifted, reason = decide_drift(
                    baseline_hash=row["baseline_hash"],
                    baseline_new_laws=row["baseline_new_laws"],
                    baseline_job_id=row["baseline_job_id"],
                    current=fp,
                )
                if drifted:
                    drifts += 1
                    already = " (already flagged)" if row["drift_detected_at"] else ""
                    print(f"sentinel DRIFT  {label}: {reason}{already}")
                else:
                    print(f"sentinel ok     {label}"
                          + (f" [fetch degraded: {fp.error}]" if fp.error else ""))

                if dry_run:
                    continue
                await conn.execute(
                    """UPDATE ordinance_fingerprints
                          SET host_kind=$2,
                              baseline_hash=$3, baseline_new_laws=$4, baseline_job_id=$5,
                              baseline_set_at=COALESCE(baseline_set_at, now()),
                              current_hash=COALESCE($6, current_hash),
                              current_new_laws=COALESCE($7, current_new_laws),
                              current_job_id=COALESCE($8, current_job_id),
                              codified_through=COALESCE($9, codified_through),
                              fetched_at=now(), fetch_error=$10,
                              drift_detected_at=CASE WHEN $11 THEN COALESCE(drift_detected_at, now())
                                                     ELSE drift_detected_at END,
                              drift_reason=CASE WHEN $11 THEN $12 ELSE drift_reason END,
                              updated_at=now()
                        WHERE id=$1""",
                    row["id"],
                    fp.host_kind,
                    baseline_hash,
                    baseline_new_laws,
                    baseline_job_id,
                    fp.chapter_hash,
                    fp.new_laws_count,
                    fp.municode_job_id,
                    fp.codified_through,
                    (fp.error or None) and fp.error[:1000],
                    drifted,
                    reason,
                )

        print(
            f"sentinel: batch done — {len(rows)} checked, {drifts} drifted, {errors} errors"
            + (" (dry-run, no writes)" if dry_run else "")
        )
        return 1 if errors else 0
    finally:
        await conn.close()  # releases the advisory lock


async def report(write_queue_file: bool) -> int:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """SELECT municipality, state, ordinance_url, drift_detected_at, drift_reason,
                      codified_through
                 FROM ordinance_fingerprints
                WHERE drift_detected_at IS NOT NULL
                ORDER BY drift_detected_at ASC"""
        )
    finally:
        await conn.close()
    if not rows:
        print("re-verify queue: EMPTY — no drift detected")
        return 0
    lines = [
        "# Ordinance re-verify queue (primary-source drift)",
        "",
        "Munis whose PRIMARY ordinance host changed after grounding. Re-ground each",
        "via the normal 7-step loop scoped to the delta, then clear with",
        '`python scripts/ordinance_sentinel.py --rebaseline "<ordinance_url>"`.',
        "",
    ]
    for r in rows:
        lines.append(
            f"- **{r['municipality']}, {r['state'] or '??'}** — {r['drift_reason']}"
            f" (detected {r['drift_detected_at']:%Y-%m-%d}; {r['ordinance_url']})"
        )
    text = "\n".join(lines) + "\n"
    print(text)
    if write_queue_file:
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE_FILE.write_text(text, encoding="utf-8")
        print(f"wrote {_QUEUE_FILE}")
    return 0


async def rebaseline(needle: str) -> int:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """SELECT id, municipality, state, ordinance_url FROM ordinance_fingerprints
                WHERE ordinance_url = $1 OR lower(municipality) = lower($1)""",
            needle,
        )
        if len(rows) != 1:
            print(
                f"rebaseline: expected exactly 1 match for {needle!r}, got {len(rows)} — "
                "pass the exact ordinance_url",
                file=sys.stderr,
            )
            return 1
        row = rows[0]
        await conn.execute(
            """UPDATE ordinance_fingerprints
                  SET baseline_hash=current_hash, baseline_new_laws=current_new_laws,
                      baseline_job_id=current_job_id, baseline_set_at=now(),
                      drift_detected_at=NULL, drift_reason=NULL, updated_at=now()
                WHERE id=$1""",
            row["id"],
        )
        print(f"rebaselined {row['municipality']}, {row['state'] or '??'} ({row['ordinance_url']})")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=_BATCH_LIMIT)
    ap.add_argument("--min-age-days", type=int, default=_MIN_AGE_DAYS)
    ap.add_argument("--dry-run", action="store_true", help="fetch + compare, no writes")
    ap.add_argument("--report", action="store_true", help="print the open drift queue")
    ap.add_argument("--write-queue-file", action="store_true",
                    help="with --report: also write outputs/_reverify_queue.md")
    ap.add_argument("--rebaseline", metavar="URL_OR_MUNI",
                    help="after human re-verification: current becomes the new baseline")
    args = ap.parse_args()

    if args.rebaseline:
        return asyncio.run(rebaseline(args.rebaseline))
    if args.report:
        return asyncio.run(report(args.write_queue_file))
    return asyncio.run(run_batch(args.limit, args.min_age_days, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
