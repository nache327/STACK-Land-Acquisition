"""Seed ordinance_fingerprints from the per-county zoning directories.

Baseline population for the freshness sentinel (Phase A): one row per muni
ordinance URL from ``backend/data/*_zoning_directory.json`` (the structured
muni-level URL surface — ~92% eCode360), plus, with ``--include-jurisdictions``,
any ``jurisdictions.ordinance_url`` not already covered (zoneomics mirrors are
skipped — a vendor mirror is not a primary source, catch #37; those rows are
being repointed separately).

Rows land with NO baseline fingerprint: the sentinel's first pass fetches each
URL and locks the baseline in (see ordinance_sentinel.py). ``verified_as_of``
prose stamps ("current through Ord X") can be harvested from apply scripts
opportunistically later — informational, not load-bearing.

Idempotent upsert keyed on ordinance_url. Dry-run by default; --apply writes.

  python scripts/backfill_ordinance_fingerprints.py                # dry-run
  python scripts/backfill_ordinance_fingerprints.py --apply
  python scripts/backfill_ordinance_fingerprints.py --apply --include-jurisdictions
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
from app.services.ordinance_freshness import detect_host_kind  # noqa: E402

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Directory file stem -> state. New directories must be added here explicitly
# (an unmapped file is a loud skip, never a guessed state).
_STATE_BY_FILE = {
    "bergen_zoning_directory": "NJ",
    "burlington_zoning_directory": "NJ",
    "essex_zoning_directory": "NJ",
    "middlesex_nj_zoning_directory": "NJ",
    "monmouth_zoning_directory": "NJ",
    "westchester_zoning_directory": "NY",
    "allegheny_pa_zoning_directory": "PA",
    "king_wa_zoning_directory": "WA",
    "kitsap_wa_zoning_directory": "WA",
    "pierce_wa_zoning_directory": "WA",
    "snohomish_wa_zoning_directory": "WA",
    "maricopa_az_zoning_directory": "AZ",
}

# Municode chapter monitoring needs the productId; these were recorded in the
# munis' apply scripts at grounding time. Extend as more Municode munis ground.
_MUNICODE_PRODUCT_IDS = {
    "library.municode.com/az/scottsdale": 10075,
    "library.municode.com/nj/south_brunswick": 13445,
    "library.municode.com/il/libertyville": 12585,
}


def _product_id_for(url: str) -> int | None:
    u = url.lower()
    for fragment, pid in _MUNICODE_PRODUCT_IDS.items():
        if fragment in u:
            return pid
    return None


def _directory_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(_DATA_DIR.glob("*_zoning_directory.json")):
        state = _STATE_BY_FILE.get(path.stem)
        if state is None:
            print(f"SKIP {path.name}: no state mapping in _STATE_BY_FILE", file=sys.stderr)
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")):
            url = (entry.get("ordinance_url") or "").strip()
            if not url:
                continue
            if "zoneomics.com" in url.lower():
                print(f"SKIP vendor mirror URL for {entry.get('muni_name')}: {url}", file=sys.stderr)
                continue
            rows.append(
                {
                    "state": state,
                    "municipality": entry.get("muni_name") or "(unknown)",
                    "ordinance_url": url,
                    "host_kind": detect_host_kind(url),
                    "municode_product_id": _product_id_for(url),
                    "jurisdiction_id": None,
                }
            )
    return rows


async def _jurisdiction_rows(conn: asyncpg.Connection) -> list[dict]:
    records = await conn.fetch(
        """SELECT id, name, state, ordinance_url FROM jurisdictions
            WHERE ordinance_url IS NOT NULL
              AND ordinance_url !~* 'zoneomics'"""
    )
    return [
        {
            "state": (r["state"] or "")[:2] or None,
            "municipality": r["name"],
            "ordinance_url": r["ordinance_url"].strip(),
            "host_kind": detect_host_kind(r["ordinance_url"]),
            "municode_product_id": _product_id_for(r["ordinance_url"]),
            "jurisdiction_id": r["id"],
        }
        for r in records
        if r["ordinance_url"] and r["ordinance_url"].strip()
    ]


async def run(apply: bool, include_jurisdictions: bool) -> int:
    rows = _directory_rows()
    conn = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
    try:
        if include_jurisdictions:
            seen = {r["ordinance_url"] for r in rows}
            rows += [r for r in await _jurisdiction_rows(conn) if r["ordinance_url"] not in seen]

        by_host: dict[str, int] = {}
        for r in rows:
            by_host[r["host_kind"]] = by_host.get(r["host_kind"], 0) + 1
        print(f"candidate rows: {len(rows)} — by host: {by_host}")

        if not apply:
            print("dry-run (no writes). Re-run with --apply.")
            return 0

        before = await conn.fetchval("SELECT count(*) FROM ordinance_fingerprints")
        for r in rows:
            await conn.execute(
                """INSERT INTO ordinance_fingerprints
                       (state, municipality, ordinance_url, host_kind,
                        municode_product_id, jurisdiction_id)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (ordinance_url) DO UPDATE
                       SET municipality = EXCLUDED.municipality,
                           state = COALESCE(EXCLUDED.state, ordinance_fingerprints.state),
                           host_kind = EXCLUDED.host_kind,
                           municode_product_id = COALESCE(
                               EXCLUDED.municode_product_id,
                               ordinance_fingerprints.municode_product_id),
                           jurisdiction_id = COALESCE(
                               EXCLUDED.jurisdiction_id,
                               ordinance_fingerprints.jurisdiction_id),
                           updated_at = now()""",
                r["state"],
                r["municipality"],
                r["ordinance_url"],
                r["host_kind"],
                r["municode_product_id"],
                r["jurisdiction_id"],
            )
        after = await conn.fetchval("SELECT count(*) FROM ordinance_fingerprints")
        print(f"ordinance_fingerprints: {before} -> {after} rows ({len(rows)} upserted)")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument(
        "--include-jurisdictions",
        action="store_true",
        help="also seed from jurisdictions.ordinance_url (zoneomics skipped)",
    )
    args = ap.parse_args()
    return asyncio.run(run(args.apply, args.include_jurisdictions))


if __name__ == "__main__":
    raise SystemExit(main())
