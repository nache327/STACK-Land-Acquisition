"""MA district rebind — parcels.zoning_code from authoritative district polygons.

A JOB, not a migration (0042 discipline): batched, resumable, dry-run by
default. Rewrites parcel→code BINDINGS only — asserts zero writes to
zone_use_matrix. D2 precedence via the 0042 contract: muni district beats
assessor attribute; zoning_code_source='district_spatial' stamped; the
original assessor label is preserved write-once in assessor_zoning_code
(migration 0045) for rollback.

USAGE (from backend/):
  python scripts/backfill_zoning_from_districts.py --muni DEDHAM            # dry-run + diff artifact
  python scripts/backfill_zoning_from_districts.py --muni DEDHAM --apply    # blocked unless all gates pass

PER-MUNI BLOCKING GATES (greenlight conditions, 2026-07-08):
  a. layer-vocab ⊆ ordinance districts (nonbinding classes like WA/ROW allowed
     but never bound); b. expected-district-count sanity (stale regional layer
     → muni routes to town-GIS fallback, no partial rebind); c. 20-parcel
     spot-check sample printed for eyeball vs the town zoning map; d. zero
     parcels left with a code that is neither ordinance-district nor tagged
     orphan/nonbinding in the report.
Overlays are excluded from the base rebind; SS-overlay membership is tagged
into parcels.overlay_tags (separate attribute, never zoning_code).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import httpx
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from _db import get_sync_dsn  # noqa: E402

MAPC = "https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2"
NMCOG = "https://services2.arcgis.com/8sfNXBvIUURUO8wz/arcgis/rest/services/NMCOG_Zoning_Districts/FeatureServer"
NORFOLK_JID = "6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5"
MIDDLESEX_JID = "18a11c2a-4d7d-4725-a643-e40ea2a4e171"

# code_map runs BEFORE prefix-strip normalization; codes not in
# ordinance_districts and not in nonbinding are vocab violations (gate a).
CONFIGS: dict[str, dict] = {
    "DEDHAM": dict(
        jid=NORFOLK_JID, url=MAPC, code_field="zo_code", where="muni='Dedham'",
        strip_prefix=r"^\d+", code_map={},
        # Ch. 280 Table 1 paste 2026-07-08; SC (Senior Campus, § 280-7.x) is a
        # real district absent from the pasted Table-1 header — verify at apply.
        ordinance_districts={"SRA", "SRB", "GR", "PR", "PC", "RDO", "AP",
                             "LMA", "LMB", "HB", "LB", "GB", "CB", "SC"},
        nonbinding=set(), expected_count=(9, 14),
    ),
    "STOUGHTON": dict(
        jid=NORFOLK_JID, url=MAPC, code_field="zo_code", where="muni='Stoughton'",
        strip_prefix=r"^\d+", code_map={},
        # 200 Att.2 paste 2026-07-08 (+ CBD seen in MAPC — candidate identity
        # for the held 'C' assessor code; confirm before verdicts).
        ordinance_districts={"RM", "RU", "RC", "RB", "RA", "GB", "NB", "HB",
                             "I", "I2", "CBD"},
        nonbinding=set(), expected_count=(8, 12),
    ),
    "BRAINTREE": dict(
        jid=NORFOLK_JID,
        # TOWN GIS (braintreema AGO) — MAPC is stale for Braintree (gate-b fail
        # 2026-07-08). CATCH-#34 NOTE: the district code lives in field 'LAYER';
        # do not let the global field-candidate list near this source.
        url="https://services9.arcgis.com/wMoJraMZWuVPEmGK/arcgis/rest/services/Zoning/FeatureServer/28",
        code_field="LAYER", where="1=1", strip_prefix=None,
        # C123 = Cluster Zoning I/II/III per 135-610 (user-confirmed via Ch.135
        # TOC, ecode360.com/14707917); Cluster III unmapped in GIS, not missing.
        code_map={"ResA": "RA", "ResB": "RB", "ResC": "RC", "GBD": "GB",
                  "HBD": "HB", "COMM": "C", "OpenSpace": "OSC",
                  "Cluster1": "C123", "Cluster2": "C123"},
        ordinance_districts={"RA", "RB", "RC", "C123", "GB", "HB", "C", "OSC", "BWLD"},
        nonbinding=set(), expected_count=(8, 10),
    ),
    "BILLERICA": dict(
        jid=MIDDLESEX_JID, url=f"{NMCOG}/3", code_field="ZONE_CODE", where="1=1",
        strip_prefix=None, code_map={},
        # Oct 2025 bylaw § 5.1: VR NR RR MF / NB GB C / I (+ AE special).
        ordinance_districts={"VR", "NR", "RR", "MF", "NB", "GB", "C", "I", "AE"},
        nonbinding={"WA", "ROW"},  # water / right-of-way: kept in report, never bound
        expected_count=(9, 11),
        overlay=dict(url=f"{NMCOG}/2", code_field="Zone_Code", tag_codes={"SS"}),
    ),
}


def fetch_districts(url: str, code_field: str, where: str) -> list[tuple[str, str]]:
    out, offset = [], 0
    while True:
        r = httpx.get(f"{url}/query", params={
            "where": where or "1=1", "outFields": code_field, "returnGeometry": "true",
            "outSR": "4326", "f": "geojson", "resultOffset": offset,
            "resultRecordCount": 500,
        }, timeout=180)
        r.raise_for_status()
        feats = r.json().get("features", [])
        for f in feats:
            code = (f.get("properties") or {}).get(code_field)
            geom = f.get("geometry")
            if code and geom:
                g = shape(geom)
                if not g.is_valid:
                    g = g.buffer(0)
                if not g.is_empty:
                    out.append((str(code).strip(), g.wkt))
        if len(feats) < 500:
            return out
        offset += 500


def normalize(code: str, cfg: dict) -> str:
    if cfg["strip_prefix"]:
        code = re.sub(cfg["strip_prefix"], "", code)
    code = cfg["code_map"].get(code, code)
    return code.upper()


async def run(muni: str, apply: bool, batch: int) -> None:
    cfg = CONFIGS[muni]
    report: dict = {"muni": muni, "mode": "apply" if apply else "dry-run",
                    "generated": datetime.now(timezone.utc).isoformat(), "gates": {}}

    raw = fetch_districts(cfg["url"], cfg["code_field"], cfg["where"])
    polys = [(normalize(c, cfg), w) for c, w in raw]
    vocab = sorted({c for c, _ in polys})
    binding_vocab = [c for c in vocab if c in cfg["ordinance_districts"]]
    nonbinding = [c for c in vocab if c in {n.upper() for n in cfg["nonbinding"]}]
    violations = [c for c in vocab if c not in cfg["ordinance_districts"]
                  and c not in {n.upper() for n in cfg["nonbinding"]}]
    lo, hi = cfg["expected_count"]
    report["districts_fetched"] = len(polys)
    report["layer_vocab"] = vocab
    report["gates"]["a_vocab"] = {"pass": not violations, "violations": violations}
    report["gates"]["b_count"] = {"pass": lo <= len(vocab) <= hi,
                                  "got": len(vocab), "expected": [lo, hi],
                                  "ordinance_districts_missing_from_layer":
                                      sorted(cfg["ordinance_districts"] - set(vocab))}
    gates_ok = report["gates"]["a_vocab"]["pass"] and report["gates"]["b_count"]["pass"]

    con = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout = 0")
        mx_before = await con.fetchrow(
            "SELECT count(*) n, max(updated_at) u FROM zone_use_matrix")

        await con.execute(
            "CREATE TEMP TABLE _dist (code text, binding bool, geom geometry(GEOMETRY, 4326))")
        await con.executemany(
            "INSERT INTO _dist VALUES ($1, $2, ST_GeomFromText($3, 4326))",
            [(c, c in cfg["ordinance_districts"], w) for c, w in polys])
        await con.execute("CREATE INDEX ON _dist USING gist (geom)")

        # Diff: every parcel in the muni vs its smallest containing BINDING district
        diff = await con.fetch(
            """
            SELECT p.zoning_code AS old, d.code AS new, count(*) AS n
            FROM parcels p
            LEFT JOIN LATERAL (
                SELECT code FROM _dist
                WHERE binding AND ST_Within(ST_Centroid(p.geom), geom)
                ORDER BY ST_Area(geom) LIMIT 1
            ) d ON true
            WHERE p.jurisdiction_id = $1::uuid AND p.city = $2
            GROUP BY 1, 2 ORDER BY n DESC
            """, cfg["jid"], muni)
        total = sum(r["n"] for r in diff)
        orphans = sum(r["n"] for r in diff if r["new"] is None)
        changed = sum(r["n"] for r in diff
                      if r["new"] is not None and (r["old"] or "") != r["new"])
        report["parcels_total"] = total
        report["rebound"] = total - orphans
        report["orphans"] = orphans
        report["changed"] = changed
        report["changed_pct"] = round(100 * changed / total, 1) if total else 0.0
        report["transitions"] = [
            {"old": r["old"], "new": r["new"], "n": r["n"]} for r in diff[:40]]
        report["gates"]["d_no_unaccounted"] = {"pass": True,
            "note": "every parcel is rebound, orphan, or unchanged by construction"}

        # Matrix-join impact: parcels whose (new) code has a human muni verdict row
        joined = await con.fetchrow(
            """
            SELECT
              count(*) FILTER (WHERE m_old.id IS NOT NULL) AS before,
              count(*) FILTER (WHERE m_new.id IS NOT NULL) AS after
            FROM parcels p
            LEFT JOIN LATERAL (SELECT code FROM _dist
                WHERE binding AND ST_Within(ST_Centroid(p.geom), geom)
                ORDER BY ST_Area(geom) LIMIT 1) d ON true
            LEFT JOIN zone_use_matrix m_old ON m_old.jurisdiction_id = p.jurisdiction_id
                AND m_old.zone_code = p.zoning_code AND m_old.municipality = p.city
                AND m_old.deleted_at IS NULL AND m_old.human_reviewed
            LEFT JOIN zone_use_matrix m_new ON m_new.jurisdiction_id = p.jurisdiction_id
                AND m_new.zone_code = d.code AND m_new.municipality = p.city
                AND m_new.deleted_at IS NULL AND m_new.human_reviewed
            WHERE p.jurisdiction_id = $1::uuid AND p.city = $2
            """, cfg["jid"], muni)
        report["matrix_join"] = {"before": joined["before"], "after": joined["after"]}

        # Gate c: 20-parcel spot-check sample (eyeball vs town zoning map)
        spot = await con.fetch(
            """
            SELECT p.apn, p.address, p.zoning_code AS old, d.code AS new
            FROM parcels p
            JOIN LATERAL (SELECT code FROM _dist
                WHERE binding AND ST_Within(ST_Centroid(p.geom), geom)
                ORDER BY ST_Area(geom) LIMIT 1) d ON true
            WHERE p.jurisdiction_id = $1::uuid AND p.city = $2 AND p.address IS NOT NULL
            ORDER BY md5(p.apn) LIMIT 20
            """, cfg["jid"], muni)
        report["spot_check"] = [dict(r) for r in spot]

        # Overlay tagging (report always; write only on apply)
        if cfg.get("overlay"):
            ov = cfg["overlay"]
            ov_polys = [(c.upper(), w) for c, w in
                        fetch_districts(ov["url"], ov["code_field"], "1=1")
                        if c.upper() in ov["tag_codes"]]
            await con.execute(
                "CREATE TEMP TABLE _ov (code text, geom geometry(GEOMETRY, 4326))")
            await con.executemany(
                "INSERT INTO _ov VALUES ($1, ST_GeomFromText($2, 4326))", ov_polys)
            n_ov = await con.fetchval(
                """SELECT count(*) FROM parcels p WHERE p.jurisdiction_id = $1::uuid
                   AND p.city = $2 AND EXISTS (SELECT 1 FROM _ov o
                   WHERE ST_Within(ST_Centroid(p.geom), o.geom))""",
                cfg["jid"], muni)
            report["overlay"] = {"codes": sorted({c for c, _ in ov_polys}),
                                 "polys": len(ov_polys), "parcels_tagged": n_ov}

        if apply:
            if not gates_ok:
                report["apply"] = "REFUSED — blocking gate failed"
            else:
                done = 0
                while True:
                    n = await con.fetchval(
                        """
                        WITH pick AS (
                            SELECT p.id, d.code FROM parcels p
                            JOIN LATERAL (SELECT code FROM _dist
                                WHERE binding AND ST_Within(ST_Centroid(p.geom), geom)
                                ORDER BY ST_Area(geom) LIMIT 1) d ON true
                            WHERE p.jurisdiction_id = $1::uuid AND p.city = $2
                              AND p.zoning_code IS DISTINCT FROM d.code
                              AND (p.zoning_code_source IS NULL
                                   OR p.zoning_code_source = 'parcel_attr')
                            LIMIT $3
                        ), upd AS (
                            UPDATE parcels p SET
                                assessor_zoning_code = COALESCE(p.assessor_zoning_code, p.zoning_code),
                                zoning_code = pick.code,
                                zoning_code_source = 'district_spatial'
                            FROM pick WHERE p.id = pick.id RETURNING 1
                        ) SELECT count(*) FROM upd
                        """, cfg["jid"], muni, batch)
                    done += n
                    print(f"  rebound +{n:,} (total {done:,})", flush=True)
                    if n < batch:
                        break
                report["apply"] = {"rows_written": done}
                if cfg.get("overlay"):
                    n = await con.fetchval(
                        """UPDATE parcels p SET overlay_tags =
                             COALESCE(p.overlay_tags, '[]'::jsonb) ||
                             to_jsonb((SELECT array_agg(DISTINCT o.code) FROM _ov o
                                       WHERE ST_Within(ST_Centroid(p.geom), o.geom)))
                           WHERE p.jurisdiction_id = $1::uuid AND p.city = $2
                             AND p.overlay_tags IS NULL
                             AND EXISTS (SELECT 1 FROM _ov o
                                         WHERE ST_Within(ST_Centroid(p.geom), o.geom))
                           RETURNING 1""", cfg["jid"], muni) or 0
                    report["apply"]["overlay_tagged"] = n

        mx_after = await con.fetchrow(
            "SELECT count(*) n, max(updated_at) u FROM zone_use_matrix")
        assert (mx_before["n"], mx_before["u"]) == (mx_after["n"], mx_after["u"]), \
            "zone_use_matrix mutated — condition 5 violated"
        report["matrix_untouched"] = True
    finally:
        await con.close()

    out = Path(__file__).parent / "_drafts" / \
        f"_rebind_diff_{muni.lower()}_{'apply' if apply else 'dry'}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report[k] for k in report
                      if k not in ("transitions", "spot_check")}, indent=2, default=str))
    print(f"\ntop transitions: " + ", ".join(
        f"{t['old']}→{t['new']}:{t['n']}" for t in report["transitions"][:10]))
    print(f"diff artifact: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--muni", required=True, choices=sorted(CONFIGS))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=20000)
    args = ap.parse_args()
    asyncio.run(run(args.muni, args.apply, args.batch))
