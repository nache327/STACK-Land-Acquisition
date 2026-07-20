"""Data-driven zoning-verdict applier — replaces the ~180 hand-written
``_apply_<muni>.py`` scripts with ONE tool that reads a verdicts JSON and writes
``zone_use_matrix`` rows (``human_reviewed=true``, ``classification_source='human'``,
verbatim citations). Every per-muni apply script was the same shape (a zone→verdict
map + the same INSERT/ON CONFLICT + a present-zone filter + a needle tally); this
generalizes it so a session only produces the JSON, not bespoke Python.

VERDICTS JSON schema
--------------------
{
  "jurisdiction_id": "b05b7317-...",
  "jurisdiction_name_contains": "Wake",        # optional guard assertion
  "municipality": "Apex",                       # exact parcels.city, or null = county default
  "ordinance": "Town of Apex NC UDO Table 4.2.2 ...",   # citation source
  "cited_subsection": "UDO Table 4.2.2",        # optional default section for all zones
  "zones": {
    "LI": {
      "zone_name": "LI Light Industrial",
      "self_storage": "permitted", "mini_warehouse": "permitted",
      "light_industrial": "permitted", "luxury_garage_condo": "prohibited",
      "confidence": 0.88,
      "quote": "Table 4.2.2 'Self-service storage' row = P in the LI column ...",
      "section": "UDO Table 4.2.2"              # optional; falls back to cited_subsection
    }
  }
}

Guards (the discipline the gate can't see):
  * ``municipality`` MUST equal a ``parcels.city`` EXACTLY (case-sensitive) or the
    buybox join silently scores 0 — hard error, never a silent write.
  * By default only zone_codes PRESENT in the (muni-scoped) parcels are written;
    ``--all`` overrides. Absent zones are reported, never silently dropped.
  * Every verdict value is validated against the use_permission enum.

USAGE (from backend/):
  python scripts/apply_verdicts.py verdicts.json                 # apply present zones
  python scripts/apply_verdicts.py verdicts.json --dry-run       # plan only, no writes
  python scripts/apply_verdicts.py verdicts.json --all           # apply every zone in the file
  python scripts/apply_verdicts.py verdicts.json --gate          # run postingest_gate after
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

VALID_VERDICTS = {"permitted", "conditional", "prohibited", "unclear"}
USE_COLS = ("self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo")

_SQL = """
INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality,
 self_storage, mini_warehouse, light_industrial, luxury_garage_condo, citations,
 cited_subsection, confidence, human_reviewed, classification_source, notes,
 created_at, updated_at)
VALUES ($1, $2, $3, $4, $5::use_permission_enum, $6::use_permission_enum,
 $7::use_permission_enum, $8::use_permission_enum, $9::jsonb, $10, $11, true,
 'human', $12, now(), now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
 mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
 luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
 human_reviewed=true, classification_source='human', notes=EXCLUDED.notes,
 updated_at=now()
"""


class SpecError(ValueError):
    """Raised when the verdicts JSON is malformed — surfaced before any DB write."""


def validate_spec(spec: dict) -> None:
    """Validate the verdicts-JSON shape + every enum value. Pure; raises SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("top-level JSON must be an object")
    if not spec.get("jurisdiction_id"):
        raise SpecError("missing 'jurisdiction_id'")
    if not spec.get("ordinance"):
        raise SpecError("missing 'ordinance' (citation source string)")
    zones = spec.get("zones")
    if not isinstance(zones, dict) or not zones:
        raise SpecError("'zones' must be a non-empty object keyed by zone_code")
    for zc, v in zones.items():
        if not isinstance(v, dict):
            raise SpecError(f"zone {zc!r}: verdict must be an object")
        for col in USE_COLS:
            val = v.get(col)
            if val not in VALID_VERDICTS:
                raise SpecError(
                    f"zone {zc!r}: {col}={val!r} is not one of {sorted(VALID_VERDICTS)}"
                )
        conf = v.get("confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            raise SpecError(f"zone {zc!r}: confidence {conf} out of [0,1]")
        if not v.get("quote"):
            raise SpecError(f"zone {zc!r}: missing 'quote' (verbatim citation basis)")


def plan_rows(
    spec: dict, present_zones: set[str] | None, apply_all: bool = False
) -> tuple[list[dict], list[str]]:
    """Pure planner: turn a validated spec into the rows to write, given the set of
    zone_codes actually present on the (muni-scoped) parcels.

    Returns (rows, skipped_absent). A zone in the file but NOT present in parcels is
    skipped (and reported) unless apply_all — writing a verdict for a zone no parcel
    has is dead data. present_zones=None means "don't filter" (same as apply_all)."""
    muni = spec.get("municipality")
    default_section = spec.get("cited_subsection")
    ordinance = spec["ordinance"]
    rows: list[dict] = []
    skipped: list[str] = []
    for zc, v in spec["zones"].items():
        if not apply_all and present_zones is not None and zc not in present_zones:
            skipped.append(zc)
            continue
        section = v.get("section") or default_section
        citations = json.dumps([{
            "ordinance": ordinance,
            "section": section,
            "quote": v["quote"],
        }])
        note = (f"{muni or 'county-default'} {zc} ({v.get('zone_name') or zc}) "
                f"ss={v['self_storage']} mw={v['mini_warehouse']} "
                f"li={v['light_industrial']} lgc={v['luxury_garage_condo']}")
        rows.append({
            "zone_code": zc,
            "zone_name": v.get("zone_name") or zc,
            "municipality": muni,
            "self_storage": v["self_storage"],
            "mini_warehouse": v["mini_warehouse"],
            "light_industrial": v["light_industrial"],
            "luxury_garage_condo": v["luxury_garage_condo"],
            "citations": citations,
            "cited_subsection": section,
            "confidence": v.get("confidence"),
            "notes": note,
        })
    return rows, skipped


async def _present_zones(conn, jid: str, muni: str | None) -> set[str]:
    if muni is not None:
        rows = await conn.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels "
            "WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL",
            jid, muni,
        )
    else:
        rows = await conn.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels "
            "WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",
            jid,
        )
    return {r["z"] for r in rows}


async def run(path: str, dry_run: bool, apply_all: bool, gate: bool) -> int:
    spec = json.loads(Path(path).read_text())
    validate_spec(spec)
    jid = spec["jurisdiction_id"]
    muni = spec.get("municipality")

    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=180)
    try:
        await conn.execute("SET statement_timeout='180s'")
        jname = await conn.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", jid)
        if jname is None:
            print(f"ERROR: jurisdiction {jid} not found", file=sys.stderr)
            return 1
        want = spec.get("jurisdiction_name_contains")
        if want and want.lower() not in jname.lower():
            print(f"ERROR: jurisdiction guard failed — {jname!r} does not contain {want!r}",
                  file=sys.stderr)
            return 1

        # CRITICAL: municipality must equal a parcels.city EXACTLY (case-sensitive),
        # or the buybox join silently scores 0. Hard-fail rather than write dead rows.
        if muni is not None:
            cities = {r["city"] for r in await conn.fetch(
                "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city IS NOT NULL",
                jid)}
            if muni not in cities:
                near = [c for c in cities if c.lower() == muni.lower()]
                hint = f" — did you mean {near[0]!r}? (case-sensitive)" if near else ""
                print(f"ERROR: municipality {muni!r} matches no parcels.city in {jname}{hint}",
                      file=sys.stderr)
                return 1

        present = await _present_zones(conn, jid, muni)
        rows, skipped = plan_rows(spec, present, apply_all=apply_all)

        print(f"=== apply_verdicts — {jname} · municipality={muni or '(county default)'} ===")
        print(f"  zones in file: {len(spec['zones'])}  present in parcels: {len(present)}  "
              f"to write: {len(rows)}  skipped-absent: {len(skipped)}")
        if skipped:
            print(f"  skipped (no parcels carry these zone codes; use --all to force): "
                  f"{', '.join(sorted(skipped))}")
        for r in rows:
            print(f"    {r['zone_code']}: ss={r['self_storage']} mw={r['mini_warehouse']} "
                  f"li={r['light_industrial']} lgc={r['luxury_garage_condo']} "
                  f"conf={r['confidence']}")

        if dry_run:
            print("  DRY RUN — no rows written.")
            return 0
        if not rows:
            print("  nothing to write.")
            return 0

        for r in rows:
            await conn.execute(
                _SQL, jid, r["zone_code"], r["zone_name"], r["municipality"],
                r["self_storage"], r["mini_warehouse"], r["light_industrial"],
                r["luxury_garage_condo"], r["citations"], r["cited_subsection"],
                r["confidence"], r["notes"],
            )
        print(f"  applied {len(rows)} row(s).")

        # Verify-before-declare: read the rows back + tally wealth-gated needles.
        muni_pred = "AND m.municipality=$2" if muni is not None else "AND m.municipality IS NULL"
        params = [jid, muni] if muni is not None else [jid]
        written = await conn.fetchval(
            f"SELECT count(*) FROM zone_use_matrix m WHERE m.jurisdiction_id=$1::uuid "
            f"{muni_pred} AND m.deleted_at IS NULL AND m.human_reviewed", *params)
        print(f"  verified human-reviewed rows for scope: {written}")

        needle_muni = "AND p.city=$2" if muni is not None else ""
        needles = await conn.fetchval(
            f"""SELECT count(*) FROM parcels p
                  JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id
                       AND m.zone_code=p.zoning_code
                       AND (m.municipality IS NULL OR m.municipality=p.city)
                       AND m.deleted_at IS NULL AND m.human_reviewed
                       AND m.self_storage IN ('permitted','conditional')
                  JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
                 WHERE p.jurisdiction_id=$1::uuid {needle_muni}
                   AND p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000""",
            *params)
        print(f"  wealth-gated self-storage needles (scope): {needles}")

        if gate:
            from app.services.postingest_gate import run_postingest_gate
            rep = await run_postingest_gate(conn, jid)
            status = "PASS" if rep.passed else "FAIL"
            print(f"  POST-INGEST GATE: [{status}] {rep.stats}")
            for f in rep.hard_failures:
                print(f"    HARD FAIL: {f}")
            if not rep.passed:
                return 1
    finally:
        await conn.close()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply zoning verdicts from a JSON file.")
    ap.add_argument("verdicts_json", help="path to the verdicts JSON")
    ap.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    ap.add_argument("--all", action="store_true",
                    help="apply every zone in the file, even ones no parcel carries")
    ap.add_argument("--gate", action="store_true",
                    help="run postingest_gate after applying; nonzero exit on FAIL")
    args = ap.parse_args()
    try:
        code = asyncio.run(run(args.verdicts_json, args.dry_run, args.all, args.gate))
    except SpecError as exc:
        print(f"ERROR: invalid verdicts JSON — {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
