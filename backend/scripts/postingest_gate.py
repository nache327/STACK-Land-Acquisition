"""CLI for the post-ingest anti-poison gate (hardening plan 2.5).

Run after a jurisdiction's munis are applied (the plan's per-county post-batch
step). Exits non-zero on any HARD failure so it can gate a deploy / CI / a
parallel-session merge.

USAGE (from backend/):
  python scripts/postingest_gate.py --jurisdiction <jid>
  python scripts/postingest_gate.py --jurisdiction <jid> --json   # machine-readable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from app.services.postingest_gate import run_postingest_gate  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    conn = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        rep = await run_postingest_gate(conn, args.jurisdiction)
    finally:
        await conn.close()

    if args.json:
        print(json.dumps({
            "jurisdiction_id": rep.jurisdiction_id, "passed": rep.passed,
            "hard_failures": rep.hard_failures, "warnings": rep.warnings, "stats": rep.stats,
        }, indent=2))
    else:
        status = "PASS" if rep.passed else "FAIL"
        print(f"[{status}] post-ingest gate — jurisdiction {rep.jurisdiction_id}")
        print(f"  stats: {rep.stats}")
        for f in rep.hard_failures:
            print(f"  HARD FAIL: {f}")
        for w in rep.warnings:
            print(f"  warn: {w}")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
