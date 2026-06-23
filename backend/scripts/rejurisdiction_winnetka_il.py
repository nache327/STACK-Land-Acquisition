"""Phase 7G.x — Move Winnetka parcels from Cook IL umbrella → own jurisdiction.

Per Master's WINNETKA FIRE SEQUENCE dispatch 2026-06-23 (Wave-6, post
Cook IL 1.87M headless ingest completion verified at 21:55 UTC).

Pattern: King WA Phase 6B-PIVOT (rejurisdiction_bellevue_mercer.py)
+ raw->>'CITYNAME' selector (Cook IL parcel ingest left
parcels.city NULL but preserved raw 'CITYNAME' field — finding from
Probe PR #335).

This script:
  1. Registers "Village of Winnetka, IL" as its own jurisdiction
     (idempotent find-or-create)
  2. UPDATES parcels.jurisdiction_id Cook → Winnetka WHERE
     raw->>'CITYNAME' = 'WINNETKA' (expected ~5,194 rows; probe
     baseline)
  3. Inline jurisdictions.bbox UPDATE from ST_Extent over moved
     parcels (PR #261 codified)
  4. Per-muni atomic transaction

Pre-move probe (PR #335): 5,194 candidates by raw CITYNAME.
Post-move: Winnetka adapter (PR #334) is fire-gated on the new
JID + >=100 parcels under it.

Hard rules:
  - raw preserved verbatim (UPDATE on jurisdiction_id only)
  - Inline bbox per new jurisdiction
  - Per-muni transaction for atomicity
"""
from __future__ import annotations
import argparse, asyncio, json, logging, os, sys, uuid
from pathlib import Path
import asyncpg, dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set")

logger = logging.getLogger("rejurisdiction_winnetka")

COOK_JID = "1726fc6f-9927-413e-b20e-936ab438de10"
WINNETKA_NAME = "Village of Winnetka, IL"
WINNETKA_STATE = "IL"
WINNETKA_COUNTY = "Cook"
RAW_CITYNAME_VALUE = "WINNETKA"
# Winnetka village extent sanity envelope. Actual extent observed via
# dry-run: [-87.78986, 42.08486, -87.71090, 42.12839]. Envelope is for
# gross-mismatch sanity (wrong city / wrong county ingest), not
# tight-fit verification.
BBOX_LON = (-87.80, -87.69)
BBOX_LAT = (42.07, 42.14)


def _db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _fire(dry_run: bool = False) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Winnetka PATH 1 re-jurisdictioning ===\n")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, command_timeout=600)
    try:
        # Pre-move probe (cheap).
        candidates = await conn.fetchval(
            """SELECT COUNT(*) FROM parcels
               WHERE jurisdiction_id=$1::uuid
                 AND raw->>'CITYNAME'=$2""", COOK_JID, RAW_CITYNAME_VALUE,
        )
        print(f"  candidates in Cook (CITYNAME={RAW_CITYNAME_VALUE!r}): {candidates:,}")
        if candidates < 100:
            raise SystemExit(
                f"REFUSE — only {candidates} Winnetka candidates; expected ~5,194"
            )

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            # Idempotent jurisdiction find/create.
            existing = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
                WINNETKA_NAME, WINNETKA_STATE,
            )
            if existing:
                new_jid = str(existing["id"])
                print(f"  Found existing JID: {new_jid}")
            else:
                new_jid = str(uuid.uuid4())
                await conn.execute(
                    """INSERT INTO jurisdictions (id, name, state, county)
                       VALUES ($1::uuid, $2, $3, $4)""",
                    new_jid, WINNETKA_NAME, WINNETKA_STATE, WINNETKA_COUNTY,
                )
                print(f"  Registered new JID: {new_jid}")

            # Move parcels Cook → Winnetka.
            status = await conn.execute(
                """UPDATE parcels
                      SET jurisdiction_id=$2::uuid, updated_at=NOW()
                    WHERE jurisdiction_id=$1::uuid
                      AND raw->>'CITYNAME'=$3""",
                COOK_JID, new_jid, RAW_CITYNAME_VALUE,
            )
            try:
                n_moved = int(status.split()[-1])
            except (ValueError, IndexError):
                n_moved = -1
            print(f"  Moved parcels: {n_moved:,}")
            if n_moved < 100:
                raise RuntimeError(
                    f"only {n_moved} parcels moved; aborting tx (expected ~5,194)"
                )

            # Inline bbox UPDATE from moved parcels.
            ext = await conn.fetchrow(
                """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                          ST_YMin(ST_Extent(geom)) AS miny,
                          ST_XMax(ST_Extent(geom)) AS maxx,
                          ST_YMax(ST_Extent(geom)) AS maxy
                   FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""",
                new_jid,
            )
            if ext is None or ext["minx"] is None:
                raise RuntimeError("no Winnetka parcel geometry post-move; aborting")
            bbox = [float(ext["minx"]), float(ext["miny"]),
                    float(ext["maxx"]), float(ext["maxy"])]
            if not (BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
                    and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]):
                raise RuntimeError(
                    f"bbox {bbox} outside Winnetka envelope "
                    f"(lon {BBOX_LON}, lat {BBOX_LAT})"
                )
            await conn.execute(
                "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
                new_jid, json.dumps(bbox),
            )
            print(f"  Inline bbox UPDATEd: {bbox}")

            if dry_run:
                raise _RollbackSentinel()

        # Post-move verify.
        p_after = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid", new_jid,
        )
        p_cook_after = await conn.fetchval(
            """SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid
               AND raw->>'CITYNAME'=$2""", COOK_JID, RAW_CITYNAME_VALUE,
        )
        bb = await conn.fetchval(
            "SELECT bbox FROM jurisdictions WHERE id=$1::uuid", new_jid,
        )
        print(f"\n=== POST-MOVE ===")
        print(f"  Winnetka JID:         {new_jid}")
        print(f"  Winnetka parcels:     {p_after:,}")
        print(f"  Cook residual CITYNAME=WINNETKA: {p_cook_after}")
        print(f"  Winnetka bbox:        {bb}")

    except _RollbackSentinel:
        print("\n(DRY-RUN — transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
    return 0


class _RollbackSentinel(Exception):
    pass


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="Run full tx then ROLLBACK; verifies pipeline without writes.")
    a = p.parse_args()
    if not a.dry_run and not a.i_know_this_writes_to_prod:
        print("Refusing — pass --dry-run or --i-know-this-writes-to-prod",
              file=sys.stderr)
        sys.exit(2)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_fire(dry_run=a.dry_run)))
