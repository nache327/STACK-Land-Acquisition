"""Preview-branch validation for the audit matrix_stats deleted_at fix.

Runs the audit twice — once with the old matrix_stats CTE (no WHERE
filter) and once with the new one (`WHERE deleted_at IS NULL`) — and
diffs the per-jurisdiction state. Reports:

  - jurisdictions whose `operational_readiness` flips (esp. regressions
    from `operational` → `partial`)
  - jurisdictions whose `matrix_zone_count` changes (size of the
    tombstone delta)
  - jurisdictions whose `matrix_zone_match_pct` changes
  - whether the regression count exceeds the >2 halt threshold the
    dispatch sets

Point DATABASE_URL at the Supabase preview branch (bbvywbpxwsoyvdvygvyw)
before running:

    DATABASE_URL=postgresql+asyncpg://...preview... \
      python backend/scripts/validate_audit_matrix_deleted_filter.py \
      --json > /tmp/audit_matrix_filter_delta.json

The script is read-only — it executes SELECTs only. Safe to run against
any environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from scripts.audit_zoning_coverage import (
    _build_audit,
    _build_audit_sql,
    _load_schema_profile,
)


def _strip_deleted_at_filter(sql: str) -> str:
    """Reproduce the pre-fix audit SQL so we can A/B the audit.

    Three places in `_build_audit_sql` now filter `zum.deleted_at IS NULL`:

    1. `matrix_stats` CTE — `WHERE zum.deleted_at IS NULL` (PR #191).
    2. `parcel_zone_matrix` CTE LEFT JOIN — `AND zum.deleted_at IS NULL`
       in the ON clause (this PR).
    3. `unmatched_zone_samples` CTE LEFT JOIN — same shape (this PR).

    To reconstruct the true pre-PR-#191 baseline (and thus give Master
    the total before/after delta this whole effort produces), the
    harness strips all three. We use narrow string anchors so this
    can't drift if a future CTE adds a similar filter.
    """
    patches = (
        # matrix_stats CTE (PR #191)
        (
            "            FROM zone_use_matrix zum\n"
            "            WHERE zum.deleted_at IS NULL\n"
            "            GROUP BY zum.jurisdiction_id\n",
            "            FROM zone_use_matrix zum\n"
            "            GROUP BY zum.jurisdiction_id\n",
        ),
        # parcel_zone_matrix CTE LEFT JOIN (this PR)
        (
            "            LEFT JOIN zone_use_matrix zum\n"
            "              ON zum.jurisdiction_id = p.jurisdiction_id\n"
            "             AND zum.zone_code = p.zoning_code\n"
            "             AND zum.deleted_at IS NULL\n"
            "            GROUP BY p.jurisdiction_id\n",
            "            LEFT JOIN zone_use_matrix zum\n"
            "              ON zum.jurisdiction_id = p.jurisdiction_id\n"
            "             AND zum.zone_code = p.zoning_code\n"
            "            GROUP BY p.jurisdiction_id\n",
        ),
        # unmatched_zone_samples CTE LEFT JOIN (this PR) — note the
        # extra indentation level vs parcel_zone_matrix's join.
        (
            "                LEFT JOIN zone_use_matrix zum\n"
            "                  ON zum.jurisdiction_id = p.jurisdiction_id\n"
            "                 AND zum.zone_code = p.zoning_code\n"
            "                 AND zum.deleted_at IS NULL\n",
            "                LEFT JOIN zone_use_matrix zum\n"
            "                  ON zum.jurisdiction_id = p.jurisdiction_id\n"
            "                 AND zum.zone_code = p.zoning_code\n",
        ),
    )
    out = sql
    missing: list[int] = []
    for i, (needle, replacement) in enumerate(patches):
        if needle not in out:
            missing.append(i)
            continue
        out = out.replace(needle, replacement)
    if missing:
        raise RuntimeError(
            "Could not locate filter clause(s) to strip at index(es) "
            f"{missing}. The audit SQL was rewritten in a way this "
            "harness doesn't understand. Fix the harness before "
            "trusting its output."
        )
    return out


async def _run_audit(conn, schema, *, old_behavior: bool) -> list[Any]:
    sql_obj = _build_audit_sql(schema)
    sql_str = str(sql_obj)
    if old_behavior:
        sql_str = _strip_deleted_at_filter(sql_str)
    rows = await conn.execute(
        text(sql_str),
        {"jurisdiction_id": None, "jurisdiction_name": None},
    )
    return [_build_audit(r, schema) for r in rows]


def _index_by_id(audits) -> dict[str, Any]:
    return {a.id: a for a in audits}


def _diff(old, new) -> dict[str, Any]:
    old_by_id = _index_by_id(old)
    new_by_id = _index_by_id(new)
    flipped: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    promotions: list[dict[str, Any]] = []
    count_deltas: list[dict[str, Any]] = []
    pct_deltas: list[dict[str, Any]] = []
    for jid, new_audit in new_by_id.items():
        old_audit = old_by_id.get(jid)
        if old_audit is None:
            continue
        if old_audit.matrix_zone_count != new_audit.matrix_zone_count:
            count_deltas.append({
                "id": jid,
                "name": old_audit.name,
                "state": old_audit.state,
                "matrix_zone_count_before": old_audit.matrix_zone_count,
                "matrix_zone_count_after": new_audit.matrix_zone_count,
                "delta": new_audit.matrix_zone_count - old_audit.matrix_zone_count,
            })
        if abs(old_audit.matrix_zone_match_pct - new_audit.matrix_zone_match_pct) >= 0.05:
            pct_deltas.append({
                "id": jid,
                "name": old_audit.name,
                "state": old_audit.state,
                "matrix_zone_match_pct_before": old_audit.matrix_zone_match_pct,
                "matrix_zone_match_pct_after": new_audit.matrix_zone_match_pct,
            })
        if old_audit.operational_readiness != new_audit.operational_readiness:
            entry = {
                "id": jid,
                "name": old_audit.name,
                "state": old_audit.state,
                "operational_readiness_before": old_audit.operational_readiness,
                "operational_readiness_after": new_audit.operational_readiness,
                "matrix_zone_count_before": old_audit.matrix_zone_count,
                "matrix_zone_count_after": new_audit.matrix_zone_count,
                "matrix_zone_match_pct_before": old_audit.matrix_zone_match_pct,
                "matrix_zone_match_pct_after": new_audit.matrix_zone_match_pct,
                "blocking_gaps_before": old_audit.blocking_gaps,
                "blocking_gaps_after": new_audit.blocking_gaps,
            }
            flipped.append(entry)
            if (
                old_audit.operational_readiness == "operational"
                and new_audit.operational_readiness != "operational"
            ):
                regressions.append(entry)
            elif (
                old_audit.operational_readiness != "operational"
                and new_audit.operational_readiness == "operational"
            ):
                promotions.append(entry)
    return {
        "jurisdictions_compared": len(new_by_id),
        "matrix_zone_count_delta_jurisdictions": len(count_deltas),
        "matrix_zone_count_deltas": sorted(
            count_deltas, key=lambda e: e["delta"]
        ),
        "matrix_match_pct_delta_jurisdictions": len(pct_deltas),
        "matrix_match_pct_deltas": pct_deltas,
        "operational_readiness_flips": len(flipped),
        "operational_regressions": regressions,
        "operational_promotions": promotions,
        "halt_threshold_exceeded": len(regressions) > 2,
        "halt_threshold": "regressions > 2 — see Dispatch hard rule",
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    settings = Settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )
    async with engine.connect() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        schema = await _load_schema_profile(conn)
        old = await _run_audit(conn, schema, old_behavior=True)
        new = await _run_audit(conn, schema, old_behavior=False)
    await engine.dispose()

    payload = _diff(old, new)
    payload["database_url_sanitized"] = settings.database_url_sanitized

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"Compared {payload['jurisdictions_compared']} jurisdictions")
    print(
        f"matrix_zone_count changed for "
        f"{payload['matrix_zone_count_delta_jurisdictions']} "
        f"jurisdictions"
    )
    print(
        f"operational_readiness flipped for "
        f"{payload['operational_readiness_flips']} jurisdictions"
    )
    print(f"  REGRESSIONS  (operational → other): {len(payload['operational_regressions'])}")
    for e in payload["operational_regressions"]:
        print(
            f"    - {e['name']} ({e['state']}): "
            f"matrix_zone_count {e['matrix_zone_count_before']} → "
            f"{e['matrix_zone_count_after']}, "
            f"match_pct {e['matrix_zone_match_pct_before']} → "
            f"{e['matrix_zone_match_pct_after']}"
        )
    print(f"  PROMOTIONS  (other → operational): {len(payload['operational_promotions'])}")
    for e in payload["operational_promotions"]:
        print(f"    + {e['name']} ({e['state']})")
    if payload["halt_threshold_exceeded"]:
        print(
            "\n⚠ HALT — regressions > 2; per Dispatch hard rule, do not "
            "deploy without Master decision on bundled audit + adjudication fix."
        )


if __name__ == "__main__":
    asyncio.run(main())
