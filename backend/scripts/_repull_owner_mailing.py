"""Bucket B — re-pull owner + MAILING address from the source ArcGIS layer.

Audit (2026-07-22) found ~72% of needle parcels stored `raw = '{}'` (attributes
dropped at ingest) or mapped situs only, even though the public assessor layer
we already ingest DOES expose the owner mailing address. This re-hits that same
layer — zero vendor cost — pulling owner name + mailing, and fills the 0053
columns (owner_mailing_address / owner_mailing_csz) + owner_name where NULL.

Scope: NEEDLE parcels only (the direct-mail deliverable) — keeps the external
request count tiny and polite. Join is by APN == the layer's stable key
(verified per source below), so mailing maps to the correct parcel — same
JOIN-INTEGRITY discipline as Bucket A. Idempotent COALESCE-fill.

    python scripts/_repull_owner_mailing.py --source massgis            # dry-run
    python scripts/_repull_owner_mailing.py --source massgis --apply
    python scripts/_repull_owner_mailing.py --source all --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncpg
import httpx

from _db import get_sync_dsn

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# needle LATERAL (matches precompute_needles / use_verdicts)
_LGC = ("(v.ss IN ('permitted','conditional') OR v.mw IN ('permitted','conditional') "
        "OR v.li IN ('permitted','conditional'))")
_LAT = """JOIN LATERAL (SELECT self_storage::text ss, mini_warehouse::text mw,
  light_industrial::text li FROM zone_use_matrix m WHERE m.jurisdiction_id=p.jurisdiction_id
  AND m.zone_code=p.zoning_code AND (m.municipality IS NULL OR m.municipality=p.city)
  AND m.deleted_at IS NULL AND m.human_reviewed ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true"""
_W = "p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"

# A source = one ArcGIS layer + field map, covering one or more jurisdictions.
#   key         : the layer field whose value equals our parcels.apn
#   owner/addr/csz: layer fields to compose (first-non-empty for owner; joined for addr/csz)
#   jids        : jurisdiction id-prefixes fed by this layer
SOURCES: dict[str, dict] = {
    "massgis": {
        "url": "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0",
        "key": "LOC_ID", "owner": ["OWNER1", "OWN_CO"], "addr": ["OWN_ADDR"],
        "csz": ["OWN_CITY", "OWN_STATE", "OWN_ZIP"],
        "jids": [("18a11c2a", "Middlesex County, MA"), ("6cf15e94", "Norfolk County, MA")],
    },
    "lakeil": {
        "url": "https://maps.lakecountyil.gov/arcgis/rest/services/GISMapping/WABParcels/MapServer/12",
        "key": "PIN", "owner": ["taxpayer_name", "taxpayer_org_name"],
        "addr": ["taxpayer_addr_line_1", "taxpayer_addr_line_2"],
        "csz": ["taxpayer_addr_city", "taxpayer_addr_state", "taxpayer_addr_zip"],
        "jids": [("10d01284", "Lake County, IL")],
    },
    "wakenc": {
        "url": "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/MapServer/0",
        "key": "PIN_NUM", "owner": ["OWNER"], "addr": ["ADDR1"], "csz": ["ADDR2", "ADDR3"],
        "jids": [("b05b7317", "Wake County, NC")],
    },
    "maryland": {
        "url": "https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_ParcelBoundaries/MapServer/0",
        "key": "ACCTID", "owner": [], "addr": ["OWNADD1", "OWNADD2"],
        "csz": ["OWNCITY", "OWNSTATE", "OWNERZIP"],
        "jids": [("dc2d9d42", "Howard County, MD"), ("c64d5cd2", "Montgomery County, MD")],
    },
    # NJ statewide MOD-IV composite — mail-only (OWNER_NAME blank, verified). PAMS_PIN == our apn
    # (8/8 exact match on Morris). Covers every NJ Bucket-B county fed by the NJTPA atlas bind.
    "njcomposite": {
        "url": "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0",
        "key": "PAMS_PIN", "owner": ["OWNER_NAME"], "addr": ["ST_ADDRESS"], "csz": ["CITY_STATE", "ZIP_CODE"],
        "jids": [("746b7604", "Morris County, NJ"), ("67541a18", "Essex County, NJ"),
                 ("394ef40c", "Somerset County, NJ"), ("16dc5ad9", "Union County, NJ"),
                 ("7a9ed95d", "Passaic County, NJ"), ("4bf00234", "Bergen County, NJ"),
                 ("e8612f49", "Hunterdon County, NJ")],
    },
}

_SENT = {"", "nan", "null", "none", "n/a", ".", "?"}


def _clean(v) -> str:
    if v is None:
        return ""
    s = " ".join(str(v).split()).strip()
    return "" if s.lower() in _SENT else s


def _compose(attrs: dict, keys: list[str], sep: str) -> str | None:
    parts = [_clean(attrs.get(k)) for k in keys]
    joined = sep.join(p for p in parts if p).strip()
    return joined or None


async def _needle_apns(c, jid) -> list[str]:
    rows = await c.fetch(
        f"SELECT DISTINCT p.apn FROM parcels p "
        f"JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 {_LAT} "
        f"WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC} AND p.apn IS NOT NULL", jid)
    return [r["apn"] for r in rows]


async def _fetch_layer(url: str, key: str, apns: list[str], out_fields: list[str]) -> dict[str, dict]:
    """Query the layer for the given key values in batches; return {key_value: attrs}."""
    q = url.rstrip("/") + "/query"
    out = ",".join([key] + out_fields)
    result: dict[str, dict] = {}
    BATCH = 100  # POST form-encoded: no URL-length limit (GET silently 0-matched at 200)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, headers=_UA) as cl:
        for i in range(0, len(apns), BATCH):
            chunk = apns[i:i + BATCH]
            vals = ",".join("'" + a.replace("'", "''") + "'" for a in chunk)
            for attempt in range(4):
                try:
                    r = await cl.post(q, data={
                        "where": f"{key} IN ({vals})", "outFields": out,
                        "returnGeometry": "false", "f": "json"})
                    r.raise_for_status()
                    feats = r.json().get("features", [])
                    for f in feats:
                        a = f.get("attributes", {})
                        result[str(a.get(key))] = a
                    break
                except Exception as e:
                    if attempt == 3:
                        print(f"    !! batch {i} failed after retries: {e}")
                    else:
                        await asyncio.sleep(1.5 * (attempt + 1))
            print(f"    fetched {min(i+BATCH,len(apns))}/{len(apns)} apns -> {len(result)} matched",
                  end="\r", flush=True)
    print()
    return result


async def run_source(c, name: str, spec: dict, apply: bool) -> None:
    out_fields = spec["owner"] + spec["addr"] + spec["csz"]
    for pref, jname in spec["jids"]:
        jid = await c.fetchval("SELECT id FROM jurisdictions WHERE id::text LIKE $1", pref + "%")
        apns = await _needle_apns(c, jid)
        print(f"\n=== {jname} [{name}] — {len(apns)} needle parcels ===")
        if not apns:
            continue
        matched = await _fetch_layer(spec["url"], spec["key"], apns, out_fields)
        # compose records
        recs = []
        for apn, attrs in matched.items():
            owner = _compose(attrs, spec["owner"], " & ") if spec["owner"] else None
            addr = _compose(attrs, spec["addr"], " ")
            csz = _compose(attrs, spec["csz"], " ")
            if addr or csz or owner:
                recs.append((apn, owner, addr, csz))
        with_mail = sum(1 for _, _, a, _ in recs if a)
        print(f"    layer matched {len(matched)}/{len(apns)}  |  with mailing addr: {with_mail}")
        for apn, owner, addr, csz in recs[:4]:
            print(f"      {apn}: owner={owner!r} MAIL={addr!r} | {csz!r}")
        if not apply:
            continue
        # idempotent COALESCE-fill by apn
        await c.executemany(
            "UPDATE parcels SET "
            "owner_name = COALESCE(owner_name, $2), "
            "owner_mailing_address = COALESCE(owner_mailing_address, $3), "
            "owner_mailing_csz = COALESCE(owner_mailing_csz, $4) "
            "WHERE jurisdiction_id=$5 AND apn=$1",
            [(apn, owner, addr, csz, jid) for apn, owner, addr, csz in recs])
        cov = await c.fetchrow(
            f"SELECT count(*) n, count(*) FILTER (WHERE p.owner_mailing_address IS NOT NULL) m, "
            f"count(*) FILTER (WHERE p.owner_name IS NOT NULL) o "
            f"FROM parcels p JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            f"{_LAT} WHERE p.jurisdiction_id=$1 AND {_W} AND {_LGC}", jid)
        print(f"    APPLIED -> LGC needles {cov['n']}: mailing={cov['m']} ({100.0*cov['m']/max(cov['n'],1):.0f}%) "
              f"owner={cov['o']}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="massgis", help="one of: " + ", ".join(SOURCES) + ", or 'all'")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    await c.execute("SET statement_timeout = 0")
    names = list(SOURCES) if args.source == "all" else [args.source]
    for nm in names:
        if nm not in SOURCES:
            print(f"unknown source {nm}"); continue
        await run_source(c, nm, SOURCES[nm], args.apply)
    if not args.apply:
        print("\ndry-run — inspect composed MAIL lines, then re-run with --apply")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
