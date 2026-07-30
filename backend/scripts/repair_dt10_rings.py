"""Repair dt=10 parcel_ring_metrics — population AND wealth, together.

WHY A NEW ENTRYPOINT
--------------------
The correct area-weighted logic already lives in
``app/services/ring_metrics_precompute.py`` (including the ``_BBOX_PAD_DEG = 0.3``
buffer fix, without which edge parcels' isochrones reach unloaded tracts and get
systematically UNDER-measured — a bias that runs against the needle). It had no CLI:
its only callers were a worker trigger and an API route.

The existing ``recompute_ring_population.py`` is NOT the tool for this. It writes
``population`` only while stamping ``computed_at = NOW()``. That is the audit's
trust trap: the staleness detectors (ring API 90d filter, drawer 180d banner,
detect_stale_ring_metrics) all go quiet while ``median_home_value`` / ``median_hhi``
stay wrong from the same mis-anchored isochrone. The data looks repaired and the
wealth gate still fails on NULL. This script always recomputes all three together.

computed_at SEMANTICS — the load-bearing part
---------------------------------------------
A fresh ``computed_at`` must mean "every gate-bearing metric on this row is
current", or the detectors lie. Two layers enforce that:

  ROW level      ``_bulk_upsert_metrics`` now advances computed_at only when
                 population, median_home_value AND median_hhi all landed non-NULL
                 (see the CASE in that UPSERT). A row with NULL wealth keeps its
                 OLD stamp and therefore still reads as stale. hnw_households is
                 excluded on purpose: B19001_017E is legitimately missing for some
                 tracts and it feeds a scoring bonus, not the needle gate.

  JURISDICTION   This script treats a jurisdiction as REPAIRED only when the
  level          service reports no ACS shortfall (``acs_incomplete`` absent) AND
                 it wrote rows. A jurisdiction with a partial ACS fetch is recorded
                 as INCOMPLETE and does not count as done, so a resume revisits it.

Neither layer invents data: the service already writes falsy→NULL deliberately
(an ACS outage yields 0 for every aggregate, and persisting that as a measured 0
is the poison this program spent days removing). NULL stays NULL; it simply no
longer gets a fresh timestamp.

GATE — pre-registered, do not self-clear
----------------------------------------
Expected promotions are ~48 board cards (15 storage + 33 LGC currently held by
``soft_wealth_unmeasured``). The other ~684 Verify cards are held by MEASURED
misses — ring home value or income genuinely below the buy box — which no ring
repair can move. So:

  * needle totals should hold at 10,720 / 17,096 (the 2026-07-28 baseline). The
    needle gate reads dt=10 HV/HHI, so a repair CAN legitimately move it — but a
    move of more than a few dozen means the recompute changed wealth broadly, which
    is a STOP-and-surface, not a new baseline.
  * hundreds of promotions is a STOP. It would mean rings that previously read
    "unmeasured" are now measuring wealth that was never there.

``--report-only`` prints the per-jurisdiction before/after needle diff and writes
nothing, which is how to inspect the gate data before trusting it.

USAGE (from backend/):
    python scripts/repair_dt10_rings.py --report-only          # gate data, no writes
    python scripts/repair_dt10_rings.py --dry-run              # plan + ordering
    python scripts/repair_dt10_rings.py --start-index 0        # the repair
    python scripts/repair_dt10_rings.py --jurisdiction <uuid>  # one, for a pilot
    python scripts/repair_dt10_rings.py --start-index 37       # resume

Single worker by design. NullPool so a kill leaks no connections;
``statement_timeout = 0`` because a per-jurisdicton isochrone pass runs long.
Idempotent: re-running a jurisdiction recomputes the same values from the same
tracts and re-stamps only what legitimately landed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

from app.services.ring_metrics_precompute import (  # noqa: E402
    precompute_ring_metrics_for_jurisdiction,
)
# Reuse the REAL needle definition rather than restating it here. Two copies of
# this predicate is precisely the drift that made "Actionable" mean two different
# things on the board (audit A-4.7).
from precompute_needles import (  # noqa: E402
    _LATERAL,
    _LGC_VIABLE,
    _NEEDLES_SQL,
    _STORAGE_VIABLE,
)

# The 2026-07-28 accepted baseline (see memory: the older 10,709/16,816 figure was
# a stale needle_snapshot, not an invariant).
BASELINE_STORAGE = 10_720
BASELINE_LGC = 17_096

# ── The 139 subset gate, re-registered 2026-07-30 ────────────────────────────
# The original gate ("promotions must lie in the pre-registered 33") measured BOARD
# CARDS -- parcels already surfaced and held back by soft_wealth_unmeasured. The
# repair's actual effect is NEEDLE-level, and Union's 29 promotions were all parcels
# that had no dt=10 row at all, so they could not have been in the 33 by construction.
# Zero overlap was the expected result, not an anomaly.
#
# What replaces it is NOT "INSERT-path promotions are automatically fine". That rule
# would have waved Springfield through unexamined, and a brand-new measurement is
# exactly the thing that has not been checked by anything. So:
#
#   1. UPDATE-path promotion outside the 33  -> STOP. Existing wealth was rewritten
#      UPWARD past the gate, which is the signature of a recompute changing values
#      rather than discovering them.
#   2. INSERT-path promotions -> allowed, but wealth-PLAUSIBILITY spot-checked against
#      ACS per jurisdiction. A ring may exceed its own tract (it spans many), but a
#      ring exceeding everything ACS reports for the whole county is inflated.
#   3. CONCENTRATION FLAG -> promotions clustering in a single town or tract is the
#      artifact signature (Springfield was 29/29 in one town). Flag for review; a
#      genuine coverage gap looks like this too, so it is a flag, not a hard stop.
#   4. Needle movement > 100 gross -> exit(2), unchanged.
#   5. Full churn gate: gross promotions AND demotions, every demotion listed with
#      dashboard triage status, any lead_eligible demotion -> STOP for human GO.
_CONCENTRATION_FLAG_RATIO = 0.8   # >=80% of a jurisdiction's promotions in one town
_RECONCILE_EVERY = 25             # full-scan reconciliation cadence for the 139

_TRANSIENT = ("connection", "closed", "getaddrinfo", "timeout",
              "terminating", "server closed")

# NOT transient, even though the text matches _TRANSIENT above. Pool exhaustion is a
# CAPACITY condition: retrying re-runs the whole jurisdiction (including a fresh TIGER
# download and a 15-min needle scan) and competes for the very connections that are
# short. The pooler caps SESSION mode at 15 clients and the LIVE BOARD shares that
# pool, so a retry storm degrades the dashboard while it spins. Fail the jurisdiction
# loudly and let a human decide instead.
_CAPACITY = ("max clients reached", "emaxconnsession", "too many clients",
             "remaining connection slots")

# Leave this many pooler sessions for the live app at all times. The repair holds ONE
# connection (single worker, NullPool, DB access serialised behind db_lock), so this is
# a floor to verify against, not a budget to spend.
_POOL_CAP = 15
_RESERVE_FOR_APP = 8


def _async_session_dsn() -> str:
    """Session-mode host/port (:5432) WITH the asyncpg driver prefix.

    Both halves matter and neither helper gives both:
      * get_dsn()      -> +asyncpg but the TRANSACTION pooler (:6543), where
                          `SET statement_timeout = 0` applies only to the current
                          implicit transaction and silently reverts — the documented
                          cause of this family of scripts "timing out".
      * get_sync_dsn() -> session mode :5432 but NO +asyncpg, so SQLAlchemy loads
                          psycopg2 and create_async_engine raises
                          "The asyncio extension requires an async driver".
    So: take the session-mode URL and add the driver.

    NOTE a latent bug this exposed — scripts/recompute_ring_population.py:138 calls
    create_async_engine(get_sync_dsn(), ...) directly and would fail the same way.
    """
    dsn = get_sync_dsn()
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine():
    """Engine whose EVERY connection has statement_timeout disabled.

    A one-off ``SET statement_timeout = 0`` on the session is not enough:
    ``db.commit()`` releases the connection, and with NullPool the next statement
    opens a brand-new one carrying the server default of 2min. That is exactly what
    killed the post-write needle scan (a ~15min query) on the 2026-07-30 Utah run --
    the write committed, the verification was cancelled, the retry loop re-ran the
    whole jurisdiction 3 more times, and the run reported FAILED for a jurisdiction
    whose data was already in. A run lying about its own outcome is worse than a
    slow one.

    connect_args={"server_settings": ...} does NOT work here and was measured, not
    assumed: Supabase's pooler drops asyncpg startup parameters, so the setting is
    silently ignored (SHOW statement_timeout still reports 2min). The "connect"
    event fires after the connection is established, so the SET actually lands --
    verified 0 both fresh and after a commit.
    """
    engine = create_async_engine(_async_session_dsn(), poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _disable_statement_timeout(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.run_async(
            lambda conn: conn.execute("SET statement_timeout = 0")
        )

    return engine


async def capture_before(db, jid: uuid.UUID) -> dict:
    """Snapshot the exact (parcel_id, dt=10) set this jurisdiction's write will touch.

    PARTITIONED, because the revert differs by shape:
      * PRE-EXISTING rows -> full wealth + computed_at captured; revert = UPDATE back.
      * ABSENT rows       -> key only; revert = DELETE. There is nothing to restore.

    Measured shapes (2026-07-29), which are the INVERSE of the first guess -- the
    earlier "Union delete-heavy / Utah restore-heavy" labels described the promotable
    SUBSET, not this capture set, and must not be reused:
      * Union NJ  pre_existing 102,109 / absent  45,518  -> RESTORE-heavy (69% covered)
      * Utah UT   pre_existing     487 / absent 266,243  -> DELETE-heavy  (0.2% covered)
    Utah's 487 are the NULL-wealth rows that exercise the UPDATE path; its jurisdiction
    is otherwise virgin. Both partitions verified exact and disjoint against independent
    counts, so the capture set == the write set.

    The write scope is every parcel with a centroid in the jurisdiction — that is what
    precompute walks — so the capture is keyed off the same predicate rather than a
    guess about which rows change.
    """
    rows = (await db.execute(text("""
        SELECT p.id AS parcel_id,
               (prm.parcel_id IS NOT NULL) AS existed,
               prm.population, prm.median_hhi, prm.median_home_value,
               prm.hnw_households, prm.computed_at
          FROM parcels p
          LEFT JOIN parcel_ring_metrics prm
                 ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
         WHERE p.jurisdiction_id = :jid AND p.centroid IS NOT NULL
         ORDER BY p.id
    """), {"jid": str(jid)})).mappings().all()
    pre = [dict(r) for r in rows if r["existed"]]
    absent = [int(r["parcel_id"]) for r in rows if not r["existed"]]
    return {"jid": str(jid), "pre_existing": pre, "absent": absent}


async def revert_before(db, cap: dict) -> tuple[int, int]:
    """Undo a jurisdiction's write from a capture. Returns (restored, deleted).

    Deliberately NOT a blanket delete: a row that existed before must be UPDATED back
    to its captured values, and only rows that were ABSENT may be deleted. Getting
    that backwards would either destroy pre-existing data or leave new rows behind.
    """
    restored = 0
    for r in cap["pre_existing"]:
        await db.execute(text("""
            UPDATE parcel_ring_metrics
               SET population = :pop, median_hhi = :hhi,
                   median_home_value = :hv, hnw_households = :hnw,
                   computed_at = :ts
             WHERE parcel_id = :pid AND drive_time_minutes = 10
        """), {"pid": int(r["parcel_id"]), "pop": r["population"],
               "hhi": r["median_hhi"], "hv": r["median_home_value"],
               "hnw": r["hnw_households"], "ts": r["computed_at"]})
        restored += 1
    deleted = 0
    if cap["absent"]:
        res = await db.execute(text("""
            DELETE FROM parcel_ring_metrics
             WHERE drive_time_minutes = 10 AND parcel_id = ANY(:ids)
        """), {"ids": cap["absent"]})
        deleted = res.rowcount or 0
    return restored, deleted


async def fingerprint(db, parcel_ids: list[int]) -> tuple[int, int, str]:
    """(row_count, epoch_count, md5 over ordered values) for a parcel set.

    Counts alone would miss a value that changed without changing cardinality, which
    is exactly what a wrong revert looks like.
    """
    r = (await db.execute(text("""
        SELECT count(*) AS n,
               count(*) FILTER (WHERE computed_at = to_timestamp(0)) AS n_epoch,
               COALESCE(md5(string_agg(
                   parcel_id::text || '|' || COALESCE(population::text,'~') || '|'
                   || COALESCE(median_hhi::text,'~') || '|'
                   || COALESCE(median_home_value::text,'~') || '|'
                   || COALESCE(hnw_households::text,'~') || '|'
                   || computed_at::text, ',' ORDER BY parcel_id)), 'EMPTY') AS h
          FROM parcel_ring_metrics
         WHERE drive_time_minutes = 10 AND parcel_id = ANY(:ids)
    """), {"ids": parcel_ids})).mappings().first()
    return int(r["n"]), int(r["n_epoch"]), r["h"]


def save_capture(cap: dict, out_dir: Path) -> Path:
    """Persist a capture to disk BEFORE the write, so a revert survives the process.

    An in-memory capture is worthless for the case it exists to cover: the run dies
    mid-jurisdiction and the rows are already committed. Decimal/datetime are stored as
    strings and rebuilt on load, because a numeric column will not accept a bare str.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"capture_{cap['jid']}.json"
    def enc(o):
        if isinstance(o, datetime):
            return {"__dt__": o.isoformat()}
        if isinstance(o, Decimal):
            return {"__dec__": str(o)}
        raise TypeError(f"unserialisable {type(o).__name__}")
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(cap, default=enc), encoding="utf-8")
    tmp.replace(path)          # atomic: never leave a half-written capture behind
    return path


def load_capture(path: Path) -> dict:
    def dec(d):
        if "__dt__" in d:
            return datetime.fromisoformat(d["__dt__"])
        if "__dec__" in d:
            return Decimal(d["__dec__"])
        return d
    return json.loads(path.read_text(encoding="utf-8"), object_hook=dec)


async def _needles_by_jid(db) -> dict[uuid.UUID, tuple[int, int]]:
    """{jid: (storage_needles, lgc_needles)} using precompute_needles' own SQL."""
    rows = (await db.execute(text(_NEEDLES_SQL))).mappings().all()
    return {r["jid"]: (int(r["storage_needles"]), int(r["lgc_needles"])) for r in rows}


async def _needles_for_jid(db, jid) -> tuple[int, int]:
    """(storage, lgc) needles for ONE jurisdiction. ~2s, versus ~15min for the
    cross-jurisdiction _NEEDLES_SQL.

    _NEEDLES_SQL has no jurisdiction bindparam and groups over the whole table, so
    using it per jurisdiction made the 139 roughly 35 HOURS of pure scanning. This
    reuses the SAME predicate CONSTANTS (_STORAGE_VIABLE / _LGC_VIABLE / _LATERAL /
    the wealth floors) rather than restating the predicate, so the two cannot drift;
    only the scope differs. The full scan is still run periodically to reconcile the
    incrementally-maintained global total -- see _RECONCILE_EVERY.
    """
    r = (await db.execute(text(f"""
        SELECT count(*) FILTER (WHERE {_STORAGE_VIABLE}) AS storage,
               count(*) FILTER (WHERE {_LGC_VIABLE})     AS lgc
          FROM parcels p
          JOIN parcel_ring_metrics prm
            ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
          {_LATERAL}
         WHERE p.jurisdiction_id = :j
           AND p.acres >= 1.5
           AND prm.median_home_value >= 475000
           AND prm.median_hhi >= 100000
    """), {"j": str(jid)})).mappings().first()
    return int(r["storage"]), int(r["lgc"])


async def _jurisdictions(db, only: uuid.UUID | None) -> list[tuple[uuid.UUID, str]]:
    """Needle-priority order, matching the re-score, so indices line up across
    tools and a --start-index means the same thing everywhere."""
    if only is not None:
        r = (await db.execute(text(
            "SELECT id, name FROM jurisdictions WHERE id = :j"), {"j": only})).first()
        return [(r[0], r[1] or str(r[0]))] if r else []
    rows = (await db.execute(text(
        """
        SELECT j.id, j.name
          FROM jurisdictions j
          LEFT JOIN needle_snapshot ns ON ns.jurisdiction_id = j.id
         WHERE EXISTS (SELECT 1 FROM parcels p
                        WHERE p.jurisdiction_id = j.id AND p.centroid IS NOT NULL)
         ORDER BY COALESCE(ns.storage_needles, 0) + COALESCE(ns.lgc_needles, 0) DESC,
                  j.id
        """))).all()
    return [(r[0], r[1] or str(r[0])) for r in rows]


def _verdict(before: tuple[int, int], after: tuple[int, int]) -> str:
    ds, dl = after[0] - before[0], after[1] - before[1]
    if ds == 0 and dl == 0:
        return "unchanged"
    return f"storage {ds:+d} / lgc {dl:+d}"


async def main() -> None:
    ap = argparse.ArgumentParser(
        description="Repair dt=10 ring metrics (population + wealth together).")
    ap.add_argument("--jurisdiction", default=None, help="Repair one jurisdiction UUID.")
    ap.add_argument("--start-index", type=int, default=0,
                    help="Skip the first N in the deterministic order (resume).")
    ap.add_argument("--end-index", type=int, default=None,
                    help="Stop before this index (bound a pilot slice).")
    ap.add_argument("--report-only", action="store_true",
                    help="Print current per-jurisdiction needles and exit. No writes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan and ordering. No writes.")
    ap.add_argument("--retries", type=int, default=4,
                    help="Per-jurisdiction retries on TRANSIENT connection errors.")
    ap.add_argument("--capture-dir", default="outputs/ring_captures",
                    help="Where per-jurisdiction before-state captures are written "
                         "(taken BEFORE each write; required for a revert).")
    ap.add_argument("--no-capture", action="store_true",
                    help="Skip before-state capture. Refuses to run unless "
                         "--i-accept-no-revert is also given.")
    ap.add_argument("--i-accept-no-revert", action="store_true",
                    help=argparse.SUPPRESS)
    ap.add_argument("--revert-from", default=None,
                    help="Path to a capture JSON. Reverts that jurisdiction's write "
                         "and exits. Performs no repair.")
    args = ap.parse_args()
    only = uuid.UUID(args.jurisdiction) if args.jurisdiction else None
    capture_dir = Path(args.capture_dir)
    if args.no_capture and not args.i_accept_no_revert:
        print("REFUSING: --no-capture removes the only way to undo this write.",
              flush=True)
        sys.exit(3)

    # PREFLIGHT. Without a Mapbox token there are no isochrones, so there are no
    # rings -- but the failure surfaces as one warning per tract, AFTER a capture, a
    # TIGER download and a 15-min needle scan, and the retry loop then repeats the
    # whole thing because a connection error looks transient. That cost 40 minutes to
    # learn one env var was missing. Fail in one second instead: refuse loudly before
    # touching anything. Reads settings.mapbox_enabled -- the SAME source the client
    # checks, so this cannot pass while the client refuses.
    if not args.report_only and not args.dry_run and not args.revert_from:
        from app.config import settings  # local import: keeps --help cheap
        if not settings.mapbox_enabled:
            print("REFUSING: MAPBOX_TOKEN is empty, so no isochrone can be fetched and "
                  "every tract would fail.\n"
                  "  Ring metrics cannot be computed without it -- Mapbox is the only "
                  "isochrone provider (fetch_isochrone wraps the same client).\n"
                  "  Set MAPBOX_TOKEN in backend/.env (copy it from the Railway service "
                  "env) and re-run.\n"
                  "  Nothing was captured or written.", flush=True)
            sys.exit(3)

    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if args.revert_from:
            cap = load_capture(Path(args.revert_from))
            ids = [int(r["parcel_id"]) for r in cap["pre_existing"]] + \
                  [int(x) for x in cap["absent"]]
            async with Session() as db:
                await db.execute(text("SET statement_timeout = 0"))
                fp_pre = await fingerprint(db, ids)
                restored, deleted = await revert_before(db, cap)
                await db.commit()
                fp_post = await fingerprint(db, ids)
            print(f"revert {cap['jid']}: restored={restored:,} deleted={deleted:,}",
                  flush=True)
            print(f"  fingerprint {fp_pre[0]:,} rows/{fp_pre[1]:,} epoch -> "
                  f"{fp_post[0]:,} rows/{fp_post[1]:,} epoch", flush=True)
            return

        async with Session() as db:
            await db.execute(text("SET statement_timeout = 0"))
            # POOL WATCH. The live board shares this session-mode pool, so check the
            # headroom BEFORE a long run rather than discovering it at jurisdiction 40.
            # The repair itself needs exactly one connection; this refuses when the app
            # is already close to the cap, so the repair is never the thing that tips it.
            live = int((await db.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname IS NOT NULL"
            ))).scalar() or 0)
            spare = _POOL_CAP - live
            print(f"pool: {live} session(s) in use of ~{_POOL_CAP}; spare {spare}; "
                  f"repair needs 1 (single worker, NullPool, DB serialised)", flush=True)
            if spare < 2:
                print(f"REFUSING: only {spare} pooler session(s) spare. The live board "
                      f"shares this pool — starting now would degrade it. Wait for the "
                      f"app to settle, then resume.", flush=True)
                sys.exit(3)
            if live > (_POOL_CAP - _RESERVE_FOR_APP):
                print(f"  WARNING: fewer than {_RESERVE_FOR_APP} sessions held back for "
                      f"the app. Proceeding (the repair takes only 1), but a second "
                      f"concurrent job would tip the pool.", flush=True)
            todo = await _jurisdictions(db, only)
            before_all = await _needles_by_jid(db)

        total = len(todo)
        end = args.end_index if args.end_index is not None else total
        slice_ = todo[args.start_index:end]
        b_ss = sum(v[0] for v in before_all.values())
        b_lgc = sum(v[1] for v in before_all.values())
        print(f"jurisdictions: {total}  slice: {len(slice_)} "
              f"(index {args.start_index}..{end})", flush=True)
        print(f"needles BEFORE: storage {b_ss:,} / lgc {b_lgc:,}   "
              f"(accepted baseline {BASELINE_STORAGE:,} / {BASELINE_LGC:,})", flush=True)

        if args.report_only:
            print("\nper-jurisdiction needles (report only, nothing written):", flush=True)
            for jid, name in slice_:
                ss, lgc = before_all.get(jid, (0, 0))
                if ss or lgc:
                    print(f"   {name[:38]:<40} storage {ss:>6,}  lgc {lgc:>6,}", flush=True)
            return
        if args.dry_run:
            print("\nplan (dry run — nothing written):", flush=True)
            for i, (jid, name) in enumerate(slice_, args.start_index):
                print(f"   [{i}] {name[:44]:<46} {jid}", flush=True)
            return

        repaired: list[str] = []
        incomplete: list[tuple[str, str]] = []
        failed: list[tuple[str, str]] = []
        # Incrementally-maintained global needle totals, seeded from the one true
        # full scan at start. Reconciled against another full scan every
        # _RECONCILE_EVERY jurisdictions and at the end.
        g_ss, g_lgc = b_ss, b_lgc

        for offset, (jid, name) in enumerate(slice_):
            i = args.start_index + offset
            t0 = time.monotonic()
            # Capture BEFORE the write, persisted to disk, in its own session that is
            # closed before the repair opens one. If this fails, the jurisdiction is
            # skipped -- a write with no revert net is the thing we are avoiding.
            if not args.no_capture:
                try:
                    async with Session() as db:
                        await db.execute(text("SET statement_timeout = 0"))
                        cap = await capture_before(db, jid)
                    cpath = save_capture(cap, capture_dir)
                    print(f"  [{i}/{total}] captured   {name[:32]:<34} "
                          f"pre_existing={len(cap['pre_existing']):,} "
                          f"absent={len(cap['absent']):,} -> {cpath.name}", flush=True)
                except Exception as e:
                    failed.append((name, f"capture failed, write SKIPPED: {e}"[:160]))
                    print(f"  [{i}/{total}] NO-CAPTURE {name[:32]}: {e} — SKIPPED",
                          flush=True)
                    continue

            for attempt in range(1, max(args.retries, 1) + 1):
                try:
                    async with Session() as db:
                        await db.execute(text("SET statement_timeout = 0"))
                        # NO pre-write scan. _NEEDLES_SQL has no jurisdiction
                        # bindparam -- it is a full cross-jurisdiction GROUP BY, ~15
                        # min per call -- and the pre-write numbers are already in
                        # `running_all`. Re-scanning for them bought nothing and
                        # doubled the cost of every jurisdiction.
                        # SCOPED needle counts (~2s each) instead of two ~15min
                        # cross-jurisdiction scans. Pre-write is affordable again, so
                        # `before` is measured rather than chained -- no assumption
                        # that nothing else moved needles between jurisdictions.
                        before = await _needles_for_jid(db, jid)
                        summary = await precompute_ring_metrics_for_jurisdiction(jid, db)
                        await db.commit()
                        after = await _needles_for_jid(db, jid)
                    # Global total maintained incrementally from per-jurisdiction
                    # deltas, then RECONCILED against a true full scan periodically --
                    # an incremental figure nobody checks is how drift hides.
                    g_ss += after[0] - before[0]
                    g_lgc += after[1] - before[1]

                    if (offset + 1) % _RECONCILE_EVERY == 0:
                        async with Session() as db2:
                            true_all = await _needles_by_jid(db2)
                        t_ss = sum(v[0] for v in true_all.values())
                        t_lgc = sum(v[1] for v in true_all.values())
                        drift = abs(t_ss - g_ss) + abs(t_lgc - g_lgc)
                        print(f"  [{i}/{total}] RECONCILE  incremental "
                              f"{g_ss:,}/{g_lgc:,} vs true {t_ss:,}/{t_lgc:,} "
                              f"-> drift {drift}", flush=True)
                        if drift:
                            # HARD STOP. Re-syncing to the true scan and carrying on
                            # would paper over the real problem: a drift means the
                            # incremental accounting is BUGGY, so every
                            # per-jurisdiction gate decision taken since the last
                            # reconciliation rested on a number now known to be wrong.
                            # Silently adopting the true total discards exactly the
                            # evidence needed to find out which ones.
                            print(
                                f"\n*** GATE: reconciliation MISMATCH at index {i}. "
                                f"incremental {g_ss:,}/{g_lgc:,} vs true "
                                f"{t_ss:,}/{t_lgc:,} (drift {drift}).\n"
                                f"    The incremental accounting is wrong, so every "
                                f"gate decision since the last checkpoint was made on "
                                f"a bad number. HALTING — do NOT re-sync and continue, "
                                f"do NOT re-baseline. Captures for completed "
                                f"jurisdictions are in {capture_dir}. ***",
                                flush=True)
                            sys.exit(2)

                    wrote = int(summary.get("parcels_written") or 0)
                    acs_bad = bool(summary.get("acs_incomplete"))
                    tag = "REPAIRED"
                    if acs_bad or wrote == 0:
                        # Not counted as done: the row-level CASE already withheld
                        # fresh stamps from the NULL rows, and a resume must revisit
                        # this jurisdiction rather than assume it is current.
                        tag = "INCOMPLETE"
                        incomplete.append((name, "acs_incomplete" if acs_bad else "wrote 0 rows"))
                    else:
                        repaired.append(name)
                    print(f"  [{i}/{total}] {tag:<10} {name[:32]:<34} "
                          f"rows={wrote:,} tracts={summary.get('tracts_computed')} "
                          f"needles {_verdict(before, after)} "
                          f"({time.monotonic() - t0:.1f}s)", flush=True)
                    break
                except Exception as e:
                    msg = str(e).lower()
                    if any(t in msg for t in _CAPACITY):
                        # Capacity, not transience -- see _CAPACITY. Do not retry.
                        failed.append((name, f"POOL EXHAUSTED (not retried): {e}"[:160]))
                        print(f"  [{i}/{total}] POOL-FULL  {name[:32]}: the pooler is out "
                              f"of session-mode clients. NOT retrying — a retry would "
                              f"compete with the live board for the connections that are "
                              f"short. Reduce concurrency or wait, then resume with "
                              f"--start-index {i}.", flush=True)
                        break
                    if attempt < args.retries and any(t in msg for t in _TRANSIENT):
                        print(f"  [{i}/{total}] transient {type(e).__name__}, "
                              f"retry {attempt}/{args.retries}", flush=True)
                        await asyncio.sleep(8)
                        continue
                    failed.append((name, str(e)[:160]))
                    print(f"  [{i}/{total}] FAILED     {name[:32]}: {e}", flush=True)
                    break

        async with Session() as db:
            await db.execute(text("SET statement_timeout = 0"))
            after_all = await _needles_by_jid(db)
        a_ss = sum(v[0] for v in after_all.values())
        a_lgc = sum(v[1] for v in after_all.values())

        print(f"\nrepaired {len(repaired)} · incomplete {len(incomplete)} · "
              f"failed {len(failed)}", flush=True)
        for nm, why in incomplete:
            print(f"   INCOMPLETE {nm[:38]:<40} {why}", flush=True)
        for nm, why in failed:
            print(f"   FAILED     {nm[:38]:<40} {why}", flush=True)
        # Final reconciliation: the AUTHORITATIVE numbers below come from the true
        # full scan (after_all). The incrementally-maintained totals are compared to
        # it here so a divergence is reported rather than silently carried.
        final_drift = abs(a_ss - g_ss) + abs(a_lgc - g_lgc)
        print(f"\nreconcile     : incremental {g_ss:,}/{g_lgc:,} vs true scan "
              f"{a_ss:,}/{a_lgc:,} -> drift {final_drift}"
              f"{'  (gate uses the TRUE scan)' if final_drift else ''}", flush=True)
        print(f"\nneedles AFTER : storage {a_ss:,} / lgc {a_lgc:,}", flush=True)
        print(f"needle delta  : storage {a_ss - b_ss:+d} / lgc {a_lgc - b_lgc:+d}", flush=True)
        moved = abs(a_ss - b_ss) + abs(a_lgc - b_lgc)
        if moved > 100:
            print("\n*** GATE: needle movement exceeds 100 — STOP. The repair changed "
                  "wealth broadly, not just the unmeasured rings. Surface this; do NOT "
                  "re-baseline. ***", flush=True)
            sys.exit(2)
        print("\nnext: re-score, then audit_score_coverage.py, then the board push. "
              "Ceiling is 33 promotions (Actionable 290 -> at most 323, measured -- the "
              "earlier ~48 was a guess); hundreds is a STOP.", flush=True)
        if not args.no_capture:
            print(f"revert net: {capture_dir}/capture_<jid>.json  "
                  f"(replay with --revert-from <path>)", flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
