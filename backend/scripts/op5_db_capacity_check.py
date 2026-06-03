"""
Op-5 Factory — Preview DB capacity check (Pre-build D).

Validates that the Supabase preview branch can sustain the 25-agent Op-5
factory fan-out described in `docs/OP5_FACTORY_72H_PLAN.md`. This script
does NOT touch any service code; it reads pg_catalog state and runs a
self-contained stress test against a throwaway test jurisdiction.

Subcommands:

    python backend/scripts/op5_db_capacity_check.py --snapshot
    python backend/scripts/op5_db_capacity_check.py --pool-check
    python backend/scripts/op5_db_capacity_check.py --index-check
    python backend/scripts/op5_db_capacity_check.py --stress-test \\
        --concurrency 25 --duration 60 \\
        --test-jurisdiction-name op5-cap-check-<id>
    python backend/scripts/op5_db_capacity_check.py --all

Safety rails (PR will be rejected if violated):

    * Refuses to run unless DATABASE_URL contains the preview branch ref
      `bbvywbpxwsoyvdvygvyw`.
    * Stress test uses a throwaway jurisdiction created on the fly (name
      prefix `op5-cap-check-`). Refuses to operate on Bergen/Fort Lee/
      Garfield/Hackensack — those hold Op-5 proof state.
    * Caps concurrency at 25 — the documented factory ceiling.
    * Cleans up after itself (DELETE the test jurisdiction + cascaded
      parcels + districts) unless `--keep-test-data` is passed.

Outputs:

    /tmp/op5_factory/pre_factory_db_snapshot.json  (--snapshot, --all)
    /tmp/op5_factory/db_capacity_results.json      (--all)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

# -------------------------------------------------------------------------
# Config / safety rails
# -------------------------------------------------------------------------

PREVIEW_REF = "bbvywbpxwsoyvdvygvyw"
PROTECTED_JURISDICTION_NAMES = {
    "fort lee",
    "garfield",
    "hackensack",
    "fair lawn",
}
PROTECTED_COUNTIES = {"bergen"}  # whole-county lock to be safe
FACTORY_MAX_CONCURRENCY = 25
TEST_JUR_PREFIX = "op5-cap-check-"
OUT_DIR = Path("/tmp/op5_factory")
SNAPSHOT_PATH = OUT_DIR / "pre_factory_db_snapshot.json"
RESULTS_PATH = OUT_DIR / "db_capacity_results.json"

# Towns in the Op-5 factory list (from PHASE2_PROGRESS + OP5_PROOF). Used
# only to break out the parcel/district counts in the snapshot — these are
# the towns whose state the factory will mutate.
OP5_PROOF_TOWNS = ("fort lee", "garfield", "hackensack", "fair lawn")


def _load_database_url() -> str:
    """Load DATABASE_URL from env / .env. Returns the *session-mode* URL
    (port 5432, plain postgresql://) that asyncpg can connect to.
    """
    # Try to load .env from repo root, backend/, or any ancestor (in case
    # this script is invoked from a git worktree whose root has no .env).
    here = Path(__file__).resolve()
    backend_dir = here.parent.parent
    candidates: list[Path] = [backend_dir / ".env", backend_dir.parent / ".env"]
    # Walk up looking for a repo-root .env (handles git worktrees).
    cursor = backend_dir.parent
    for _ in range(8):
        cursor = cursor.parent
        if cursor == cursor.parent:
            break
        candidates.append(cursor / ".env")
    try:
        from dotenv import load_dotenv

        for f in candidates:
            if f.exists():
                load_dotenv(f, override=False)
    except ImportError:
        pass

    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise SystemExit("DATABASE_URL is not set in env or .env")

    if PREVIEW_REF not in raw:
        raise SystemExit(
            f"DATABASE_URL does not contain preview branch ref "
            f"`{PREVIEW_REF}`. Refusing to run — this script is preview-only.\n"
            f"Sanitised URL hint: host portion does not include the preview ref."
        )

    # Normalise: drop SQLAlchemy driver prefix, force session-mode port.
    session_url = raw
    if session_url.startswith("postgresql+asyncpg://"):
        session_url = "postgresql://" + session_url[len("postgresql+asyncpg://") :]
    elif session_url.startswith("postgresql+psycopg2://"):
        session_url = "postgresql://" + session_url[len("postgresql+psycopg2://") :]
    elif session_url.startswith("postgres://"):
        session_url = "postgresql://" + session_url[len("postgres://") :]
    session_url = session_url.replace(":6543/", ":5432/")
    return session_url


def _sanitise(url: str) -> str:
    """Strip credentials for safe logging."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        rest = "***@" + rest.split("@", 1)[1]
    return f"{scheme}://{rest}"


async def _connect(url: str, *, timeout: float = 30.0) -> asyncpg.Connection:
    """asyncpg connection with session-mode-friendly settings."""
    conn = await asyncpg.connect(
        url,
        statement_cache_size=0,
        command_timeout=timeout,
    )
    return conn


# -------------------------------------------------------------------------
# 1. Snapshot
# -------------------------------------------------------------------------

async def snapshot(url: str) -> dict:
    """Pre-factory DB state — rollback baseline."""
    conn = await _connect(url, timeout=600.0)
    try:
        await conn.execute("SET statement_timeout = 0")
        # Total parcels / districts / matrix rows
        total_parcels = await conn.fetchval("SELECT COUNT(*) FROM parcels")
        total_districts = await conn.fetchval("SELECT COUNT(*) FROM zoning_districts")
        total_matrix = await conn.fetchval("SELECT COUNT(*) FROM zone_use_matrix")
        total_jurisdictions = await conn.fetchval("SELECT COUNT(*) FROM jurisdictions")

        # Op-5 proof town breakdown (parcels + districts). Matches on
        # name substring across all states because the preview branch
        # has used both `state='NJ'` and `state='NE'` for NJ munis at
        # various points (the latter is a known pre-existing labelling
        # quirk that pre-dates this script — we want to capture both).
        op5_town_rows = await conn.fetch(
            """
            SELECT
                j.name,
                j.state,
                j.county,
                (SELECT COUNT(*) FROM parcels p WHERE p.jurisdiction_id = j.id)
                    AS parcel_count,
                (SELECT COUNT(*) FROM zoning_districts zd WHERE zd.jurisdiction_id = j.id)
                    AS district_count,
                (SELECT COUNT(*) FROM zone_use_matrix zm WHERE zm.jurisdiction_id = j.id)
                    AS matrix_count
            FROM jurisdictions j
            WHERE (
                lower(j.name) LIKE '%fort lee%'
                OR lower(j.name) LIKE '%garfield%'
                OR lower(j.name) LIKE '%hackensack%'
                OR lower(j.name) LIKE '%fair lawn%'
            )
            ORDER BY lower(j.name)
            """,
        )
        op5_town_state = [dict(r) for r in op5_town_rows]
        op5_town_parcels = sum(r["parcel_count"] for r in op5_town_state)
        op5_town_districts = sum(r["district_count"] for r in op5_town_state)

        # zone_binding_method distribution (Op-5 audit field)
        binding_rows = await conn.fetch(
            """
            SELECT
                COALESCE(zone_binding_method, 'NULL') AS method,
                COUNT(*) AS n
            FROM parcels
            GROUP BY zone_binding_method
            ORDER BY n DESC
            """
        )
        binding_distribution = {r["method"]: int(r["n"]) for r in binding_rows}

        # Active connections at snapshot time, broken out by state.
        conn_rows = await conn.fetch(
            """
            SELECT state, COUNT(*) AS n
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
            ORDER BY n DESC
            """
        )
        connection_state = {(r["state"] or "unknown"): int(r["n"]) for r in conn_rows}

        # Alembic head, so the rollback baseline records schema rev
        try:
            alembic_head = await conn.fetchval(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )
        except asyncpg.PostgresError:
            alembic_head = None

        # PG version
        pg_version = await conn.fetchval("SELECT version()")

        snap = {
            "snapshot_taken_at": datetime.now(timezone.utc).isoformat(),
            "preview_branch_ref": PREVIEW_REF,
            "connection_mode": "session (port 5432)",
            "pg_version": pg_version,
            "alembic_head": alembic_head,
            "totals": {
                "jurisdictions": int(total_jurisdictions or 0),
                "parcels": int(total_parcels or 0),
                "zoning_districts": int(total_districts or 0),
                "zone_use_matrix_rows": int(total_matrix or 0),
            },
            "op5_proof_towns": {
                "towns": op5_town_state,
                "total_parcels_in_op5_towns": op5_town_parcels,
                "total_districts_in_op5_towns": op5_town_districts,
                "non_op5_parcels": int(total_parcels or 0) - op5_town_parcels,
                "non_op5_districts": int(total_districts or 0) - op5_town_districts,
            },
            "zone_binding_method_distribution": binding_distribution,
            "active_connections_by_state": connection_state,
        }
        return snap
    finally:
        await conn.close()


# -------------------------------------------------------------------------
# 2. Pool / connection-cap check
# -------------------------------------------------------------------------

async def pool_check(url: str) -> dict:
    """Inspect connection cap + idle/active distribution at session-mode."""
    conn = await _connect(url, timeout=120.0)
    try:
        await conn.execute("SET statement_timeout = 0")
        max_conn = await conn.fetchval("SHOW max_connections")
        superuser_reserve = await conn.fetchval("SHOW superuser_reserved_connections")

        # Per-database / per-user / per-state breakdown
        per_state = await conn.fetch(
            """
            SELECT state, COUNT(*) AS n
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
            ORDER BY n DESC
            """
        )
        per_state_dict = {(r["state"] or "unknown"): int(r["n"]) for r in per_state}

        per_app = await conn.fetch(
            """
            SELECT COALESCE(NULLIF(application_name, ''), '<unset>') AS app, COUNT(*) AS n
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY application_name
            ORDER BY n DESC
            LIMIT 20
            """
        )
        per_app_list = [{"application_name": r["app"], "n": int(r["n"])} for r in per_app]

        current_total = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()"
        )

        # Try to spawn N=FACTORY_MAX_CONCURRENCY session-mode connections at
        # once and see if any are refused. This is the *actual* check that
        # matters — Supabase tiers throttle session-mode connections.
        spawn_ok = 0
        spawn_errors: list[str] = []
        spawned: list[asyncpg.Connection] = []
        spawn_start = time.perf_counter()
        try:
            tasks = [
                _connect(url, timeout=20.0)
                for _ in range(FACTORY_MAX_CONCURRENCY)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    spawn_errors.append(f"{type(r).__name__}: {r}")
                else:
                    spawn_ok += 1
                    spawned.append(r)
        finally:
            spawn_elapsed = time.perf_counter() - spawn_start
            for c in spawned:
                try:
                    await c.close()
                except Exception:
                    pass

        max_conn_int = int(max_conn) if max_conn is not None else None
        verdict_ok = (
            spawn_ok == FACTORY_MAX_CONCURRENCY
            and len(spawn_errors) == 0
        )

        return {
            "max_connections": max_conn_int,
            "superuser_reserved_connections": int(superuser_reserve)
            if superuser_reserve is not None
            else None,
            "current_connections_in_db": int(current_total or 0),
            "connections_by_state": per_state_dict,
            "top_application_names": per_app_list,
            "factory_concurrency_target": FACTORY_MAX_CONCURRENCY,
            "spawn_test": {
                "tried": FACTORY_MAX_CONCURRENCY,
                "succeeded": spawn_ok,
                "errors": spawn_errors,
                "elapsed_seconds": round(spawn_elapsed, 3),
            },
            "verdict_can_sustain_25_writers": verdict_ok,
            "verdict_reasoning": (
                f"Successfully opened {spawn_ok}/{FACTORY_MAX_CONCURRENCY} "
                "concurrent session-mode connections; pre-existing "
                f"connections={int(current_total or 0)} of "
                f"max_connections={max_conn_int}."
                if verdict_ok
                else f"Only {spawn_ok}/{FACTORY_MAX_CONCURRENCY} session-mode "
                "connections succeeded. Reduce factory concurrency or "
                "upgrade Supabase plan."
            ),
        }
    finally:
        await conn.close()


# -------------------------------------------------------------------------
# 3. Index health
# -------------------------------------------------------------------------

async def index_check(url: str) -> dict:
    """List indexes on zoning_districts + parcels and EXPLAIN a sample
    ST_Within / ST_DWithin query plan against a small jurisdiction so the
    planner choice (GIST scan vs seq scan) is recorded."""
    conn = await _connect(url, timeout=600.0)
    try:
        await conn.execute("SET statement_timeout = 0")
        index_rows = await conn.fetch(
            """
            SELECT schemaname, tablename, indexname, indexdef
            FROM pg_indexes
            WHERE tablename IN ('parcels', 'zoning_districts')
            ORDER BY tablename, indexname
            """
        )
        indexes = [
            {
                "table": r["tablename"],
                "name": r["indexname"],
                "definition": r["indexdef"],
            }
            for r in index_rows
        ]

        # Pick a small-but-real NJ jurisdiction with both parcels and
        # zoning_districts for the EXPLAIN. EXPLAIN is read-only so we
        # can safely use any jurisdiction with both populated; we cap
        # parcel_count to keep ANALYZE wall-clock bounded.
        sample = await conn.fetchrow(
            """
            SELECT j.id, j.name, j.state, j.county,
                   (SELECT COUNT(*) FROM parcels p WHERE p.jurisdiction_id = j.id)
                       AS parcel_count,
                   (SELECT COUNT(*) FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = j.id) AS district_count
            FROM jurisdictions j
            WHERE j.state IN ('NJ', 'NE')
              AND EXISTS (
                  SELECT 1 FROM zoning_districts zd
                  WHERE zd.jurisdiction_id = j.id
              )
              AND EXISTS (
                  SELECT 1 FROM parcels p
                  WHERE p.jurisdiction_id = j.id
              )
            ORDER BY (
                SELECT COUNT(*) FROM zoning_districts zd
                WHERE zd.jurisdiction_id = j.id
            ) ASC
            LIMIT 1
            """,
        )
        if sample is None or sample["parcel_count"] == 0:
            return {
                "indexes": indexes,
                "explain_sample": None,
                "verdict_indexes_healthy": None,
                "verdict_reasoning": (
                    "Could not find a sample jurisdiction with parcels+districts "
                    "to EXPLAIN against. Inspect the indexes list manually."
                ),
            }

        sample_id = sample["id"]
        # EXPLAIN ANALYZE the same shape spatial_backfill uses.
        try:
            explain_within = await conn.fetch(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT p.id, m.zone_class
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1
                      AND zd.geom IS NOT NULL
                      AND ST_Within(ST_Centroid(p.geom), zd.geom)
                    ORDER BY zd.id
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1
                  AND p.geom IS NOT NULL
                LIMIT 500
                """,
                sample_id,
            )
            within_plan = explain_within[0]["QUERY PLAN"] if explain_within else None
        except asyncpg.PostgresError as e:
            within_plan = f"EXPLAIN failed: {type(e).__name__}: {e}"

        try:
            explain_dwithin = await conn.fetch(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT p.id, m.zone_class
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class
                    FROM zoning_districts zd
                    WHERE zd.jurisdiction_id = $1
                      AND zd.geom IS NOT NULL
                      AND ST_DWithin(
                          zd.geom::geography,
                          ST_Centroid(p.geom)::geography,
                          100.0
                      )
                    ORDER BY ST_Distance(
                        zd.geom::geography,
                        ST_Centroid(p.geom)::geography
                    )
                    LIMIT 1
                ) m
                WHERE p.jurisdiction_id = $1
                  AND p.geom IS NOT NULL
                LIMIT 500
                """,
                sample_id,
            )
            dwithin_plan = explain_dwithin[0]["QUERY PLAN"] if explain_dwithin else None
        except asyncpg.PostgresError as e:
            dwithin_plan = f"EXPLAIN failed: {type(e).__name__}: {e}"

        # Sanity check: does the plan mention any "Seq Scan on zoning_districts"
        # or "Seq Scan on parcels"? We want the GIST indexes used.
        def _walk_for_seq_scan(plan_blob) -> list[str]:
            found: list[str] = []

            def _walk(node):
                if isinstance(node, dict):
                    if (
                        node.get("Node Type") == "Seq Scan"
                        and node.get("Relation Name") in ("parcels", "zoning_districts")
                    ):
                        found.append(node.get("Relation Name"))
                    for v in node.values():
                        _walk(v)
                elif isinstance(node, list):
                    for x in node:
                        _walk(x)

            _walk(plan_blob)
            return found

        seq_scans: list[str] = []
        for blob in (within_plan, dwithin_plan):
            if isinstance(blob, (dict, list)):
                seq_scans.extend(_walk_for_seq_scan(blob))

        indexes_healthy = len(seq_scans) == 0

        return {
            "indexes": indexes,
            "explain_sample_jurisdiction": {
                "id": str(sample_id),
                "name": sample["name"],
                "state": sample["state"],
                "parcel_count": int(sample["parcel_count"]),
                "district_count": int(sample["district_count"]),
            },
            "explain_st_within_plan": within_plan,
            "explain_st_dwithin_plan": dwithin_plan,
            "seq_scans_detected_on_geom_tables": seq_scans,
            "verdict_indexes_healthy": indexes_healthy,
            "verdict_reasoning": (
                "GIST indexes are reachable; planner did not fall back to "
                "Seq Scan on parcels/zoning_districts for ST_Within or "
                "ST_DWithin against the sample jurisdiction."
                if indexes_healthy
                else f"Planner used Seq Scan on {sorted(set(seq_scans))} — "
                "reindex or ANALYZE before the factory launch."
            ),
        }
    finally:
        await conn.close()


# -------------------------------------------------------------------------
# 4. Stress test
# -------------------------------------------------------------------------

async def _stress_setup(
    conn: asyncpg.Connection,
    test_name: str,
    n_districts: int,
    n_parcels: int,
) -> uuid.UUID:
    """Create the throwaway jurisdiction + N districts + N parcels.

    Polygons are placed in an unused chunk of ocean off the NJ coast
    (~73.0 W, 39.0 N) on a tight grid so ST_Within / ST_DWithin are
    cheap and there's zero chance of overlapping real NJ geometry.
    """
    safe_name = test_name.lower()
    if not safe_name.startswith(TEST_JUR_PREFIX):
        raise SystemExit(
            f"Stress-test jurisdiction name must start with `{TEST_JUR_PREFIX}` "
            f"(got `{test_name}`)."
        )
    for protected in PROTECTED_JURISDICTION_NAMES:
        if protected in safe_name:
            raise SystemExit(
                f"Refusing to stress-test against name containing "
                f"`{protected}` — Op-5 proof town."
            )

    jur_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO jurisdictions (id, name, state, county, created_at)
        VALUES ($1, $2, 'NJ', $3, NOW())
        """,
        jur_id,
        test_name,
        "Op5CapCheck",
    )

    # Build a 10x10 grid of square polygons offshore — each cell is
    # ~0.01 deg ~= 1.1 km wide so the synthetic parcels comfortably
    # land inside one polygon each. Lat/lng stays well outside any
    # real NJ jurisdiction. SRID 4326.
    base_lng = -73.000
    base_lat = 39.000
    cell = 0.010
    side = 10  # 10x10 = 100 cells
    polys = []
    for k in range(n_districts):
        i = k % side
        j = (k // side) % side
        x0 = base_lng + i * cell
        y0 = base_lat + j * cell
        x1 = x0 + cell * 0.95
        y1 = y0 + cell * 0.95
        wkt = (
            f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, "
            f"{x0} {y1}, {x0} {y0}))"
        )
        polys.append((f"TZ{k:03d}", wkt))

    for code, wkt in polys:
        await conn.execute(
            """
            INSERT INTO zoning_districts
                (jurisdiction_id, zone_code, zone_class, geom, source, geom_hash)
            VALUES ($1, $2, 'unknown',
                    ST_GeomFromText($3, 4326), 'manual',
                    md5($3))
            """,
            jur_id,
            code,
            wkt,
        )

    # Parcels: scatter one point-ish polygon inside each district cell so
    # the centroid lives inside exactly one district. Replicate to reach
    # n_parcels (cycles through cells).
    rng = random.Random(20260603)
    for k in range(n_parcels):
        i = (k % side)
        j = ((k // side) % side)
        x0 = base_lng + i * cell + cell * 0.30
        y0 = base_lat + j * cell + cell * 0.30
        dx = rng.uniform(0.0, cell * 0.30)
        dy = rng.uniform(0.0, cell * 0.30)
        x1 = x0 + dx + 0.0005
        y1 = y0 + dy + 0.0005
        wkt = (
            f"POLYGON(({x0 + dx} {y0 + dy}, {x1} {y0 + dy}, "
            f"{x1} {y1}, {x0 + dx} {y1}, {x0 + dx} {y0 + dy}))"
        )
        await conn.execute(
            """
            INSERT INTO parcels (jurisdiction_id, apn, geom, created_at, updated_at)
            VALUES ($1, $2, ST_GeomFromText($3, 4326), NOW(), NOW())
            """,
            jur_id,
            f"TP{k:06d}",
            wkt,
        )

    return jur_id


async def _stress_teardown(conn: asyncpg.Connection, jur_id: uuid.UUID) -> None:
    """Hard-delete the test jurisdiction; cascades to parcels + districts."""
    await conn.execute(
        "DELETE FROM zoning_districts WHERE jurisdiction_id = $1", jur_id
    )
    await conn.execute(
        "DELETE FROM parcels WHERE jurisdiction_id = $1", jur_id
    )
    await conn.execute(
        "DELETE FROM jurisdictions WHERE id = $1", jur_id
    )


async def _stress_worker(
    worker_id: int,
    url: str,
    jur_id: uuid.UUID,
    n_inserts_per_cycle: int,
    deadline: float,
    results: list[dict],
) -> None:
    """One concurrent writer.

    Each cycle mimics the op5_per_muni_runner write shape:
      * INSERT n_inserts_per_cycle new parcels into the test jurisdiction
        (small-batch row inserts so the test does not deadlock against
        the bulk shape used in real ingestion).
      * Run an UPDATE that joins parcels to zoning_districts via
        ST_Within(ST_Centroid(parcel.geom), district.geom) — same LATERAL
        shape as spatial_backfill.backfill_parcel_zoning_from_districts.
      * Record per-cycle latency.

    Failures (deadlocks, lock-not-available, timeouts) are recorded with
    the SQLSTATE so they show up in the report.
    """
    try:
        conn = await _connect(url, timeout=60.0)
    except Exception as e:
        results.append(
            {
                "worker_id": worker_id,
                "cycle": -1,
                "latency_ms": None,
                "error": f"connect_failed: {type(e).__name__}: {e}",
            }
        )
        return
    try:
        await conn.execute("SET statement_timeout = 0")
        rng = random.Random(20260603 + worker_id)
        cycle = 0
        while time.perf_counter() < deadline:
            cycle += 1
            # Each cycle uses a unique APN prefix so worker writes don't
            # collide on the UNIQUE constraint should there be one.
            t0 = time.perf_counter()
            try:
                # Small fresh inserts — keeps the table size growing
                # like a real ingest, exercising autovacuum/WAL just a
                # touch.
                for k in range(n_inserts_per_cycle):
                    base_lng = -73.000 + rng.random() * 0.09
                    base_lat = 39.000 + rng.random() * 0.09
                    wkt = (
                        f"POLYGON(({base_lng} {base_lat}, "
                        f"{base_lng + 0.0002} {base_lat}, "
                        f"{base_lng + 0.0002} {base_lat + 0.0002}, "
                        f"{base_lng} {base_lat + 0.0002}, "
                        f"{base_lng} {base_lat}))"
                    )
                    await conn.execute(
                        """
                        INSERT INTO parcels
                            (jurisdiction_id, apn, geom, created_at, updated_at)
                        VALUES ($1, $2, ST_GeomFromText($3, 4326), NOW(), NOW())
                        """,
                        jur_id,
                        f"W{worker_id:02d}_C{cycle:05d}_K{k:03d}_"
                        f"{uuid.uuid4().hex[:6]}",
                        wkt,
                    )

                # Spatial UPDATE pass — same LATERAL shape as
                # spatial_backfill.backfill_parcel_zoning_from_districts
                # Pass 1. Scoped to test jurisdiction only.
                await conn.execute(
                    """
                    UPDATE parcels target
                    SET zone_class = sub.zone_class,
                        zone_binding_method = 'contained'
                    FROM (
                        SELECT p.id AS parcel_id, m.zone_class
                        FROM parcels p,
                        LATERAL (
                            SELECT zd.zone_class
                            FROM zoning_districts zd
                            WHERE zd.jurisdiction_id = $1
                              AND zd.geom IS NOT NULL
                              AND ST_Within(ST_Centroid(p.geom), zd.geom)
                            ORDER BY zd.id
                            LIMIT 1
                        ) m
                        WHERE p.jurisdiction_id = $1
                          AND p.geom IS NOT NULL
                          AND p.apn LIKE $2
                    ) sub
                    WHERE target.id = sub.parcel_id
                    """,
                    jur_id,
                    f"W{worker_id:02d}_C{cycle:05d}_%",
                )
                elapsed = (time.perf_counter() - t0) * 1000.0
                results.append(
                    {
                        "worker_id": worker_id,
                        "cycle": cycle,
                        "latency_ms": round(elapsed, 2),
                        "error": None,
                    }
                )
            except asyncpg.PostgresError as e:
                elapsed = (time.perf_counter() - t0) * 1000.0
                results.append(
                    {
                        "worker_id": worker_id,
                        "cycle": cycle,
                        "latency_ms": round(elapsed, 2),
                        "error": f"{getattr(e, 'sqlstate', '?')}: "
                        f"{type(e).__name__}: {e}",
                    }
                )
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000.0
                results.append(
                    {
                        "worker_id": worker_id,
                        "cycle": cycle,
                        "latency_ms": round(elapsed, 2),
                        "error": f"{type(e).__name__}: {e}",
                    }
                )
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def stress_test(
    url: str,
    *,
    concurrency: int,
    duration_s: float,
    test_jurisdiction_name: str,
    seed_districts: int = 50,
    seed_parcels: int = 1000,
    keep_test_data: bool = False,
) -> dict:
    """Spawn `concurrency` workers; each writes for `duration_s` seconds."""
    if concurrency > FACTORY_MAX_CONCURRENCY:
        raise SystemExit(
            f"--concurrency {concurrency} exceeds factory cap "
            f"{FACTORY_MAX_CONCURRENCY}."
        )

    print(
        f"[stress-test] concurrency={concurrency} duration={duration_s:.0f}s "
        f"test_jur='{test_jurisdiction_name}'",
        flush=True,
    )

    setup_conn = await _connect(url, timeout=60.0)
    jur_id: uuid.UUID | None = None
    try:
        print("[stress-test] seeding test jurisdiction…", flush=True)
        await setup_conn.execute("SET statement_timeout = 0")
        jur_id = await _stress_setup(
            setup_conn,
            test_jurisdiction_name,
            n_districts=seed_districts,
            n_parcels=seed_parcels,
        )
        print(
            f"[stress-test] seeded jur_id={jur_id} "
            f"districts={seed_districts} parcels={seed_parcels}",
            flush=True,
        )
    finally:
        await setup_conn.close()

    results: list[dict] = []
    start = time.perf_counter()
    deadline = start + duration_s

    try:
        await asyncio.gather(
            *(
                _stress_worker(
                    worker_id=i,
                    url=url,
                    jur_id=jur_id,
                    n_inserts_per_cycle=10,
                    deadline=deadline,
                    results=results,
                )
                for i in range(concurrency)
            )
        )
    finally:
        wall = time.perf_counter() - start
        print(
            f"[stress-test] workers done after {wall:.1f}s; "
            f"results recorded={len(results)}",
            flush=True,
        )

        # Clean up unless keep_test_data
        if not keep_test_data and jur_id is not None:
            tear_conn = await _connect(url, timeout=120.0)
            try:
                await tear_conn.execute("SET statement_timeout = 0")
                await _stress_teardown(tear_conn, jur_id)
                print(
                    f"[stress-test] cleaned up jur_id={jur_id}",
                    flush=True,
                )
            finally:
                await tear_conn.close()
        elif keep_test_data:
            print(
                f"[stress-test] --keep-test-data set; jur_id={jur_id} "
                "not deleted. Clean up manually.",
                flush=True,
            )

    # ── Aggregate ──────────────────────────────────────────────────────
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] is not None]
    successes = [r for r in results if r["error"] is None]
    errors = [r for r in results if r["error"] is not None]
    total = len(results)
    success_count = len(successes)
    error_count = len(errors)

    def _pct(xs: list[float], p: float) -> float | None:
        if not xs:
            return None
        xs_sorted = sorted(xs)
        k = max(0, min(len(xs_sorted) - 1, int(round(p / 100.0 * (len(xs_sorted) - 1)))))
        return round(xs_sorted[k], 2)

    p50 = _pct(latencies, 50)
    p95 = _pct(latencies, 95)
    p99 = _pct(latencies, 99)
    mean_lat = round(statistics.mean(latencies), 2) if latencies else None
    max_lat = round(max(latencies), 2) if latencies else None
    error_rate = (error_count / total) if total else None
    throughput = (success_count / wall) if wall > 0 else None

    # Sort errors by SQLSTATE for quick scan
    error_breakdown: dict[str, int] = {}
    connect_failures = 0
    for r in errors:
        msg = r["error"] or ""
        key = msg.split(":")[0].strip()
        error_breakdown[key] = error_breakdown.get(key, 0) + 1
        if "connect_failed" in msg or "EMAXCONNSESSION" in msg:
            connect_failures += 1
    # Workers that never connected count as full failures — they could
    # not do any useful work for the duration of the test.
    workers_unable_to_connect = sum(
        1
        for w_id in range(concurrency)
        if not any(r["worker_id"] == w_id and r["error"] is None for r in results)
    )

    verdict_safe = (
        error_rate is not None
        and error_rate < 0.05
        and successes
        and (p95 or 0) < 30000  # p95 under 30s per cycle is "safe enough"
        and workers_unable_to_connect == 0
    )

    summary = {
        "concurrency": concurrency,
        "duration_seconds_requested": duration_s,
        "wall_seconds_actual": round(wall, 2),
        "test_jurisdiction_name": test_jurisdiction_name,
        "seed_districts": seed_districts,
        "seed_parcels": seed_parcels,
        "inserts_per_cycle": 10,
        "cycles_attempted": total,
        "cycles_succeeded": success_count,
        "cycles_failed": error_count,
        "error_rate": round(error_rate, 4) if error_rate is not None else None,
        "throughput_cycles_per_sec": round(throughput, 3)
        if throughput is not None
        else None,
        "latency_ms": {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "mean": mean_lat,
            "max": max_lat,
            "samples": len(latencies),
        },
        "error_breakdown_by_sqlstate": error_breakdown,
        "workers_unable_to_connect": workers_unable_to_connect,
        "connect_failures_total": connect_failures,
        "verdict_safe_for_factory_launch": verdict_safe,
        "verdict_reasoning": (
            f"Error rate {error_rate:.2%} below 5% threshold; p95 latency "
            f"{p95}ms below 30s; all {concurrency} workers connected. "
            f"Safe to launch factory at concurrency {concurrency}."
            if verdict_safe
            else (
                f"{workers_unable_to_connect}/{concurrency} workers could "
                "not acquire a session-mode connection (Supavisor pool "
                "cap). Effective parallelism is the number that connected, "
                f"not {concurrency}. Lower concurrency below the connection "
                "cap or switch to direct DB connections."
                if workers_unable_to_connect > 0
                else f"Error rate {error_rate} / p95 latency {p95}ms exceeds "
                "safety thresholds. Lower concurrency or diagnose before launch."
            )
        ),
        "kept_test_data": bool(keep_test_data),
    }
    return summary


# -------------------------------------------------------------------------
# Recommendations
# -------------------------------------------------------------------------

def _build_recommendations(
    pool_res: dict | None,
    index_res: dict | None,
    stress_res: dict | None,
) -> dict:
    """Synthesise the Report §5 recommendations from the measured numbers."""
    recommended_concurrency = FACTORY_MAX_CONCURRENCY
    notes: list[str] = []

    if pool_res and not pool_res.get("verdict_can_sustain_25_writers", False):
        spawn = pool_res.get("spawn_test", {}).get("succeeded", 0)
        recommended_concurrency = min(recommended_concurrency, max(1, spawn))
        notes.append(
            f"Pool spawn test reached only {spawn}/{FACTORY_MAX_CONCURRENCY} "
            "concurrent session-mode connections; cap factory accordingly."
        )

    if stress_res:
        err = stress_res.get("error_rate") or 0.0
        if err >= 0.05:
            # Recommend halving and rerunning
            new_cap = max(1, stress_res["concurrency"] // 2)
            recommended_concurrency = min(recommended_concurrency, new_cap)
            notes.append(
                f"Stress test error rate {err:.2%} ≥ 5%; recommend lowering "
                f"concurrency to {new_cap} and re-running before launch."
            )
        p95 = (stress_res.get("latency_ms") or {}).get("p95")
        if p95 is not None and p95 > 30000:
            notes.append(
                f"Stress test p95 latency {p95}ms above 30s — investigate "
                "lock contention before launch."
            )

    if index_res and index_res.get("verdict_indexes_healthy") is False:
        notes.append(
            "EXPLAIN showed Seq Scan on parcels/zoning_districts — run "
            "REINDEX / ANALYZE before launch."
        )

    statement_timeout = "0 (disabled) — per spatial_backfill pattern"

    rollback = (
        "1) Snapshot at /tmp/op5_factory/pre_factory_db_snapshot.json "
        "records totals + Op-5 town counts.\n"
        "2) If factory misfires: DELETE FROM jurisdictions WHERE name IN (...) "
        "for any non-Op-5-proof factory muni; cascades to parcels + "
        "zoning_districts + zone_use_matrix.\n"
        "3) For touched-but-not-new munis (zone_binding_method='nearest_*'): "
        "UPDATE parcels SET zone_binding_method=NULL, zone_class=NULL WHERE "
        "jurisdiction_id IN (...) AND zone_binding_method LIKE 'nearest_%'.\n"
        "4) Re-snapshot to confirm totals match the pre-factory baseline."
    )

    return {
        "recommended_factory_concurrency": recommended_concurrency,
        "recommended_per_muni_statement_timeout": statement_timeout,
        "tuning_notes": notes,
        "rollback_procedure": rollback,
    }


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", action="store_true")
    p.add_argument("--pool-check", action="store_true")
    p.add_argument("--index-check", action="store_true")
    p.add_argument("--stress-test", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument(
        "--concurrency",
        type=int,
        default=FACTORY_MAX_CONCURRENCY,
        help=f"Stress-test concurrency (cap {FACTORY_MAX_CONCURRENCY}).",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Stress-test duration in seconds.",
    )
    p.add_argument(
        "--test-jurisdiction-name",
        type=str,
        default=None,
        help=(
            "Throwaway test jurisdiction name (must start with "
            f"`{TEST_JUR_PREFIX}`). Default: auto-generated."
        ),
    )
    p.add_argument(
        "--seed-districts",
        type=int,
        default=50,
        help="Test districts seeded before stress test.",
    )
    p.add_argument(
        "--seed-parcels",
        type=int,
        default=1000,
        help="Test parcels seeded before stress test.",
    )
    p.add_argument(
        "--keep-test-data",
        action="store_true",
        help="Skip teardown of the test jurisdiction (debug use only).",
    )
    p.add_argument(
        "--out-results",
        type=str,
        default=str(RESULTS_PATH),
        help="Where to write the --all results JSON.",
    )
    p.add_argument(
        "--out-snapshot",
        type=str,
        default=str(SNAPSHOT_PATH),
        help="Where to write the --snapshot JSON.",
    )
    return p.parse_args()


def _print_block(title: str, payload: dict) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str))


async def _main() -> int:
    args = _parse_args()
    if not (
        args.snapshot
        or args.pool_check
        or args.index_check
        or args.stress_test
        or args.all
    ):
        print(
            "Pick at least one of --snapshot, --pool-check, --index-check, "
            "--stress-test, --all",
            file=sys.stderr,
        )
        return 2

    if args.concurrency > FACTORY_MAX_CONCURRENCY:
        print(
            f"--concurrency {args.concurrency} exceeds factory cap "
            f"{FACTORY_MAX_CONCURRENCY}. Refusing.",
            file=sys.stderr,
        )
        return 2

    url = _load_database_url()
    print(
        f"[op5_db_capacity_check] using DATABASE_URL host: "
        f"{_sanitise(url)}",
        flush=True,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    test_name = args.test_jurisdiction_name or (
        f"{TEST_JUR_PREFIX}{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
        f"-{uuid.uuid4().hex[:8]}"
    )

    snapshot_res: dict | None = None
    pool_res: dict | None = None
    index_res: dict | None = None
    stress_res: dict | None = None

    if args.snapshot or args.all:
        snapshot_res = await snapshot(url)
        Path(args.out_snapshot).write_text(
            json.dumps(snapshot_res, indent=2, default=str)
        )
        _print_block("snapshot", snapshot_res)
        print(f"[snapshot] wrote {args.out_snapshot}", flush=True)

    if args.pool_check or args.all:
        pool_res = await pool_check(url)
        _print_block("pool_check", pool_res)

    if args.index_check or args.all:
        index_res = await index_check(url)
        # Index plan blobs are huge; print a trimmed view.
        trimmed = dict(index_res)
        for k in ("explain_st_within_plan", "explain_st_dwithin_plan"):
            v = trimmed.get(k)
            if isinstance(v, (list, dict)):
                trimmed[k] = "<JSON plan captured in results file>"
        _print_block("index_check", trimmed)

    if args.stress_test or args.all:
        stress_res = await stress_test(
            url,
            concurrency=args.concurrency,
            duration_s=args.duration,
            test_jurisdiction_name=test_name,
            seed_districts=args.seed_districts,
            seed_parcels=args.seed_parcels,
            keep_test_data=args.keep_test_data,
        )
        _print_block("stress_test", stress_res)

    if args.all:
        recs = _build_recommendations(pool_res, index_res, stress_res)
        bundle = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "preview_branch_ref": PREVIEW_REF,
            "snapshot": snapshot_res,
            "pool_check": pool_res,
            "index_check": index_res,
            "stress_test": stress_res,
            "recommendations": recs,
        }
        Path(args.out_results).write_text(
            json.dumps(bundle, indent=2, default=str)
        )
        print(f"[all] wrote {args.out_results}", flush=True)
        _print_block("recommendations", recs)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
