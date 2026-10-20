"""Backfill usable acres + existing building on parcel_keep_metrics (migration 0060).

USABLE ACRES (owner decision 2026-10-19). A garage-condo card's land $/SF is spread over
the acreage that can actually be built on:

    usable_acres = gross_acres − area under (NWI wetlands ∪ FEMA SFHA)

The overlap is a UNION, so ground that is both wetland and flood zone is subtracted once.
Gross acres = parcels.acres (what the card shows; the geodetic geometry area when that is
NULL/0). The constrained area is measured as a FRACTION of the parcel's own geometry and
applied to gross, so a parcel whose assessor acreage differs from its drawn polygon keeps
a consistent split (identical to plain subtraction whenever acres came from the geometry):

    wetland_acres = gross × area(P ∩ W) / area(P)
    sfha_acres    = gross × area(P ∩ F) / area(P)
    usable_acres  = gross × (1 − area(P ∩ (W ∪ F)) / area(P))

GEOMETRY SOURCE. The DB has no usable overlay polygons for the keep candidates
(parcels.in_wetland / in_flood_zone are ~never set on them, and the overlays table holds
wetlands for 4 jurisdictions and SFHA for 24), so polygons are fetched from the public
services the overlay pipeline already uses (app.config):

    USFWS NWI wetlands  — settings.usfws_nwi_url layer 0 (every NWI type: marsh, swamp,
                          pond, lake, riverine — none of it is buildable)
    FEMA NFHL SFHA      — settings.fema_nfhl_url layer 28, FLD_ZONE in A/AE/AH/AO/V/VE

per TILE (a TILE_DEG × TILE_DEG grid cell, 0.02° ≈ 2 km by default) that some candidate
parcel touches, cached on disk (scripts/_keep_cache/overlays/, git-ignored) so a rerun or
resume never re-downloads. Areas are computed in shapely in CONUS Albers equal-area
(EPSG:5070). A tile that fails to download leaves its parcels UNMEASURED (usable NULL →
the card falls back to gross) — never a silent "no wetland".

EXISTING BUILDING. improvement_share = assessor improvement (building) value ÷ total
assessed value (keep_market.improvement_share); existing_building = share >= 25%
(keep_market.EXISTING_BUILDING_SHARE); NULL when the roll doesn't carry the values.
Sources: the source roll fields kept in parcels.raw are tried FIRST as one-roll families (VALUE_FAMILIES
below; land + improvement when no total, total − land when no improvement), then the
parcels.improvement_value / parcels.assessed_value columns.

RESUMABLE. A row is done when usable_computed_at is set; reruns pick up the rest
(--recompute redoes everything). Writes are batched, one transaction per batch.
--dry-run is read-only and works before 0060 is applied (it measures and reports).

USAGE (from backend/):
  python scripts/backfill_keep_usable.py --dry-run --jurisdiction "Chester County, PA"
  python scripts/backfill_keep_usable.py                    # all jurisdictions, apply
  python scripts/backfill_keep_usable.py --state NJ --recompute
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger("backfill_keep_usable")

TILE_DEG = 0.02
SFHA_ZONES = ("A", "AE", "AH", "AO", "V", "VE")
_SQM_PER_ACRE = 4046.8564224
_NFHL_LAYER = 28
_NWI_LAYER = 0
DEFAULT_CACHE = Path(__file__).parent / "_keep_cache" / "overlays"
_PAGE = 1000
_MAX_PAGES = 200

LAYER_WETLAND = "nwi"
LAYER_SFHA = "sfha"

# Source-roll value fields kept in parcels.raw, as (improvement, land, total) key
# FAMILIES from one roll each — never mixing a building value from one basis with a
# total from another (CT assessed is 70% of appraised; TN publishes both assessed and
# market). Verified against a 5% sample of the keep candidates' raw rows 2026-10-19.
# A family is usable when its improvement is present or derivable as total − land, and
# its total is present or derivable as land + improvement.
VALUE_FAMILIES: tuple[tuple[str | None, str | None, str | None], ...] = (
    ("IMPRVT_VAL", "LAND_VAL", "NET_VALUE"),                  # NJ MOD-IV
    ("BUILDING_VALUE", "LAND_VALUE", "TOTAL_VALUE"),          # Bucks PA
    ("PROP_ASSESS", "LOT_ASSESS", "TOT_ASSESS"),              # Chester PA (LOT + PROP = TOT)
    ("Assessed_Building", "Assessed_Land", "Assessed_Total"), # CT CAMA
    ("BLDG_VAL", "LAND_VAL", "TOTAL_VAL"),                    # MassGIS L3 (Hingham)
    ("BLDG_MV1", "LAND_MV1", "TOTAL_MV1"),                    # Hennepin MN
    ("ImprovementFullCashValue", "LandFullCashValue", "FullCashValue"),  # Maricopa AZ
    ("Imp_Value", "Land_Value", "Appr_Value"),                # Arapahoe CO
    ("IMP_VAL", "LAND_VALUE", None),                          # Contra Costa CA
    ("VALUE_BLDG", "VALUE_LAND", None),                       # King WA
    ("CurrBldg40", "CurrLand40", None),                       # Gwinnett GA (40% basis)
    (None, "LAND_AV", "TOTAL_AV"),                            # NY RPS (Westchester)
    (None, "LAND_MARKE", "TOTAL_MARK"),                       # Williamson TN (market)
    (None, "LAND_MKT_VALUE", "TOTAL_MKT_VALUE"),              # UT county rolls
)


# ── pure helpers (unit-tested) ────────────────────────────────────────────────

def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _family_values(raw: dict, fam) -> tuple[float | None, float | None, float | None] | None:
    ik, lk, tk = fam
    impr = _num(raw.get(ik)) if ik else None
    land = _num(raw.get(lk)) if lk else None
    total = _num(raw.get(tk)) if tk else None
    if impr is None and total is not None and land is not None and total >= land:
        impr = total - land
    if (total is None or total <= 0) and impr is not None and land is not None:
        total = impr + land
    if impr is None or total is None or total <= 0:
        return None
    return impr, total, land


def resolve_values(improvement_value, assessed_value, raw: dict | None):
    """(improvement, total, land) for the improvement share.

    The first raw VALUE_FAMILY that yields a consistent triple wins (one roll, one
    basis); else the parcel columns improvement_value / assessed_value (written from
    the same source row at ingest). (None, None, None) when neither has both parts."""
    for fam in VALUE_FAMILIES if raw else ():
        got = _family_values(raw, fam)
        if got is not None:
            return got
    impr = _num(improvement_value)
    total = _num(assessed_value)
    if impr is None or total is None or total <= 0:
        return None, None, None
    return impr, total, None


def tiles_for_bounds(minx: float, miny: float, maxx: float, maxy: float,
                     deg: float = TILE_DEG) -> list[tuple[int, int]]:
    """Grid cells (ix, iy) a bbox touches."""
    x0, x1 = math.floor(minx / deg), math.floor(maxx / deg)
    y0, y1 = math.floor(miny / deg), math.floor(maxy / deg)
    return [(ix, iy) for ix in range(x0, x1 + 1) for iy in range(y0, y1 + 1)]


def tile_envelope(ix: int, iy: int, deg: float = TILE_DEG) -> tuple[float, float, float, float]:
    return (round(ix * deg, 6), round(iy * deg, 6),
            round((ix + 1) * deg, 6), round((iy + 1) * deg, 6))


def split_envelope(env) -> list[tuple[float, float, float, float]]:
    """2×2 quarters of an envelope (the retry for a tile the service times out on)."""
    x0, y0, x1, y1 = env
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    return [(x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)]


def usable_split(gross: float | None, frac_wet: float, frac_sfha: float,
                 frac_any: float) -> dict:
    """Gross acres + constrained fractions of the geometry → the persisted acre fields."""
    if gross is None:
        return {"gross_acres": None, "usable_acres": None,
                "wetland_acres": None, "sfha_acres": None}
    clamp = lambda f: max(0.0, min(1.0, f))  # noqa: E731
    return {
        "gross_acres": round(gross, 4),
        "usable_acres": round(gross * (1.0 - clamp(frac_any)), 4),
        "wetland_acres": round(gross * clamp(frac_wet), 4),
        "sfha_acres": round(gross * clamp(frac_sfha), 4),
    }


def _feature_id(feat: dict, geom_json) -> str:
    fid = feat.get("id")
    props = feat.get("properties") or {}
    if fid is None:
        fid = props.get("OBJECTID", props.get("objectid", props.get("FID")))
    if fid is None:
        fid = hash(json.dumps(geom_json, sort_keys=True))
    return str(fid)


def parse_features(fc: dict, layer: str) -> list[tuple[str, dict]]:
    """GeoJSON FeatureCollection → [(feature_id, geometry_json)] (SFHA zones only for
    the flood layer, polygons only)."""
    out = []
    for f in fc.get("features") or []:
        g = f.get("geometry")
        if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        if layer == LAYER_SFHA:
            zone = str((f.get("properties") or {}).get("FLD_ZONE") or "").strip().upper()
            if zone not in SFHA_ZONES:
                continue
        out.append((_feature_id(f, g), g))
    return out


# ── geometry ─────────────────────────────────────────────────────────────────

_TRANSFORMER = None


def to_equal_area(geom):
    """WGS84 lon/lat shapely geometry → EPSG:5070 (CONUS Albers equal-area), valid."""
    global _TRANSFORMER
    import shapely
    from pyproj import Transformer

    if _TRANSFORMER is None:
        _TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)

    def _xy(coords):
        import numpy as np

        x, y = _TRANSFORMER.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    g = shapely.transform(geom, _xy)
    if not g.is_valid:
        g = shapely.make_valid(g)
    return g


def _polys(g):
    """Polygonal part of a (possibly GeometryCollection) geometry."""
    import shapely
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

    if g is None or g.is_empty:
        return None
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return shapely.union_all(parts) if parts else None
    return None


@dataclass
class OverlayIndex:
    """Equal-area overlay polygons for one layer, deduped by feature id, STRtree-indexed."""
    geoms: list = field(default_factory=list)
    _ids: set = field(default_factory=set)
    _tree: object = None

    def add(self, fid: str, geom_json: dict) -> None:
        from shapely.geometry import shape

        if fid in self._ids:
            return
        self._ids.add(fid)
        try:
            g = _polys(to_equal_area(shape(geom_json)))
        except Exception:  # noqa: BLE001 — a malformed source polygon is skipped
            return
        if g is not None and not g.is_empty:
            self.geoms.append(g)
            self._tree = None

    def clip(self, parcel):
        """Union of this layer's polygons intersected with the parcel (or None)."""
        import shapely
        from shapely.strtree import STRtree

        if not self.geoms:
            return None
        if self._tree is None:
            self._tree = STRtree(self.geoms)
        hits = [self.geoms[i] for i in self._tree.query(parcel, predicate="intersects")]
        if not hits:
            return None
        parts = []
        for h in hits:
            try:
                parts.append(_polys(parcel.intersection(h)))
            except Exception:  # noqa: BLE001 — topology error on one polygon
                parts.append(_polys(parcel.intersection(shapely.make_valid(h))))
        parts = [p for p in parts if p is not None and not p.is_empty]
        return shapely.union_all(parts) if parts else None


def measure(parcel_ea, wet: OverlayIndex, sfha: OverlayIndex) -> tuple[float, float, float]:
    """(wetland, sfha, wetland ∪ sfha) as fractions of the parcel's area."""
    area = parcel_ea.area
    if area <= 0:
        return 0.0, 0.0, 0.0
    w = wet.clip(parcel_ea)
    f = sfha.clip(parcel_ea)
    aw = w.area if w is not None else 0.0
    af = f.area if f is not None else 0.0
    if w is not None and f is not None:
        au = w.union(f).area
    else:
        au = aw + af
    return aw / area, af / area, au / area


# ── overlay fetch with disk cache ────────────────────────────────────────────

class TileFetcher:
    def __init__(self, cache_dir: Path, deg: float, concurrency: int, offline: bool = False):
        from app.config import settings

        self.cache_dir = Path(cache_dir)
        self.deg = deg
        self.sem = asyncio.Semaphore(concurrency)
        self.offline = offline
        self.urls = {
            LAYER_WETLAND: settings.usfws_nwi_url.rstrip("/") + f"/{_NWI_LAYER}/query",
            LAYER_SFHA: settings.fema_nfhl_url.rstrip("/") + f"/{_NFHL_LAYER}/query",
        }
        self.stats = Counter()

    def _path(self, layer: str, tile: tuple[int, int]) -> Path:
        return self.cache_dir / layer / f"{self.deg:g}" / f"{tile[0]}_{tile[1]}.json"

    def cached(self, layer: str, tile) -> list | None:
        p = self._path(layer, tile)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — a torn cache file is re-fetched
                return None
        return None

    async def _query(self, client, layer: str, env, offset: int) -> dict:
        params = {
            "geometry": ",".join(str(v) for v in env),
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326", "outSR": "4326",
            "returnGeometry": "true", "geometryPrecision": "7",
            "f": "geojson",
            "resultOffset": offset, "resultRecordCount": _PAGE,
        }
        if layer == LAYER_SFHA:
            params["where"] = "FLD_ZONE IN (" + ",".join(f"'{z}'" for z in SFHA_ZONES) + ")"
            params["outFields"] = "OBJECTID,FLD_ZONE"
        else:
            params["where"] = "1=1"
            params["outFields"] = "OBJECTID"
        last = None
        for attempt in range(4):
            try:
                r = await client.get(self.urls[layer], params=params)
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    raise RuntimeError(str(data["error"])[:200])
                return data
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last = exc
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{layer} tile query failed: {last!r}")

    async def _fetch_env(self, client, layer: str, env) -> list:
        """All features in one envelope (paginated); raises on failure."""
        feats: list = []
        seen: set = set()
        for page in range(_MAX_PAGES):
            data = await self._query(client, layer, env, page * _PAGE)
            batch = parse_features(data, layer)
            raw_n = len(data.get("features") or [])
            new = [(fid, g) for fid, g in batch if fid not in seen]
            seen.update(fid for fid, _ in new)
            feats.extend(new)
            more = (data.get("exceededTransferLimit")
                    or (data.get("properties") or {}).get("exceededTransferLimit")
                    or raw_n >= _PAGE)
            if not more or (raw_n and not new):
                break
        return feats

    async def fetch(self, client, layer: str, tile) -> list | None:
        """[(fid, geometry_json)] for a tile, from cache or the service; None on failure."""
        hit = self.cached(layer, tile)
        if hit is not None:
            self.stats[f"{layer}_cache"] += 1
            return hit
        if self.offline:
            self.stats[f"{layer}_missing"] += 1
            return None
        env = tile_envelope(*tile, self.deg)
        async with self.sem:
            try:
                feats = await self._fetch_env(client, layer, env)
            except Exception as exc:  # noqa: BLE001 — retry as 2×2 sub-envelopes
                # FEMA times out on dense tiles; quarter the envelope once and merge
                # (deduped by feature id) before giving the tile up as unmeasured.
                logger.info("tile %s %s failed (%s); retrying as quarters", layer, tile, exc)
                try:
                    feats, seen = [], set()
                    for sub in split_envelope(env):
                        for fid, g in await self._fetch_env(client, layer, sub):
                            if fid not in seen:
                                seen.add(fid)
                                feats.append((fid, g))
                    self.stats[f"{layer}_split"] += 1
                except Exception as exc2:  # noqa: BLE001 — tile left unmeasured
                    logger.warning("tile %s %s failed: %s", layer, tile, exc2)
                    self.stats[f"{layer}_failed"] += 1
                    return None
        p = self._path(layer, tile)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(feats), encoding="utf-8")
        tmp.replace(p)
        self.stats[f"{layer}_fetched"] += 1
        return feats

    async def fetch_all(self, tiles) -> dict[tuple[str, tuple], list | None]:
        import httpx

        tiles = sorted(set(tiles))
        out: dict = {}
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True,
                                     headers={"User-Agent": "ParcelLogic keep-usable"}) as c:
            jobs = [(layer, t) for t in tiles for layer in (LAYER_WETLAND, LAYER_SFHA)]
            res = await asyncio.gather(*(self.fetch(c, layer, t) for layer, t in jobs))
        for (layer, t), feats in zip(jobs, res):
            out[(layer, t)] = feats
        return out


# ── DB ───────────────────────────────────────────────────────────────────────

_RAW_KEYS = sorted({k for fam in VALUE_FAMILIES for k in fam if k})
_RAW_SQL = "jsonb_strip_nulls(jsonb_build_object(" + ", ".join(
    f"'{k}', p.raw->'{k}'" for k in _RAW_KEYS) + "))"

_JURIS_SQL = """
SELECT j.id::text AS jid, j.name, coalesce(j.state, '') AS state, count(*) AS n
  FROM parcel_keep_metrics k
  JOIN parcels p ON p.id = k.parcel_id
  JOIN jurisdictions j ON j.id = p.jurisdiction_id
 WHERE TRUE {where}
 GROUP BY 1, 2, 3
 ORDER BY 4 DESC
"""

_ROWS_SQL = f"""
SELECT k.parcel_id, p.acres::float8 AS acres, ST_AsBinary(p.geom) AS wkb,
       p.improvement_value::float8 AS improvement_value,
       p.assessed_value::float8 AS assessed_value,
       CASE WHEN jsonb_typeof(p.raw) = 'object' THEN {_RAW_SQL} END AS raw_vals
  FROM parcel_keep_metrics k
  JOIN parcels p ON p.id = k.parcel_id
 WHERE p.jurisdiction_id = $1::uuid AND k.parcel_id > $2 {{todo}}
 ORDER BY k.parcel_id
 LIMIT $3
"""

_UPDATE_SQL = """
UPDATE parcel_keep_metrics k
   SET gross_acres       = CASE WHEN v.measured THEN v.gross ELSE coalesce(k.gross_acres, v.gross) END,
       usable_acres      = CASE WHEN v.measured THEN v.usable ELSE k.usable_acres END,
       wetland_acres     = CASE WHEN v.measured THEN v.wet ELSE k.wetland_acres END,
       sfha_acres        = CASE WHEN v.measured THEN v.sfha ELSE k.sfha_acres END,
       improvement_share = v.share,
       existing_building = v.building,
       usable_computed_at = CASE WHEN v.measured THEN now() ELSE k.usable_computed_at END
  FROM unnest($1::bigint[], $2::float8[], $3::float8[], $4::float8[], $5::float8[],
              $6::float8[], $7::bool[], $8::bool[])
       AS v(parcel_id, gross, usable, wet, sfha, share, building, measured)
 WHERE k.parcel_id = v.parcel_id
"""


def compute_rows(rows: list[dict], tile_feats: dict, deg: float) -> list[dict]:
    """Measure each DB row against the fetched overlay tiles + resolve its values."""
    from shapely import wkb as _wkb

    from app.services import keep_market

    wet, sfha = OverlayIndex(), OverlayIndex()
    for (layer, _t), feats in tile_feats.items():
        if feats:
            idx = wet if layer == LAYER_WETLAND else sfha
            for fid, g in feats:
                idx.add(fid, g)
    out = []
    for r in rows:
        raw = r.get("raw_vals")
        if isinstance(raw, str):
            raw = json.loads(raw)
        impr, total, land = resolve_values(r.get("improvement_value"),
                                           r.get("assessed_value"), raw)
        share = keep_market.improvement_share(impr, total, land)
        res = {"parcel_id": r["parcel_id"], "improvement_share": share,
               "existing_building": keep_market.existing_building(share),
               "measured": False}
        gross = r.get("acres")
        geom = None
        if r.get("wkb") is not None:
            try:
                geom = _wkb.loads(bytes(r["wkb"]))
            except Exception:  # noqa: BLE001
                geom = None
        if geom is not None and not geom.is_empty:
            ea = to_equal_area(geom)
            if not gross or gross <= 0:
                gross = ea.area / _SQM_PER_ACRE  # Albers is equal-area
            b = geom.bounds
            tiles = tiles_for_bounds(*b, deg)
            if all(tile_feats.get((layer, t)) is not None
                   for t in tiles for layer in (LAYER_WETLAND, LAYER_SFHA)):
                fw, ff, fu = measure(ea, wet, sfha)
                res.update(usable_split(gross, fw, ff, fu))
                res["measured"] = True
        if not res["measured"]:
            res.update({"gross_acres": None if not gross else round(gross, 4),
                        "usable_acres": None, "wetland_acres": None, "sfha_acres": None})
        out.append(res)
    return out


class Tally:
    def __init__(self):
        self.c = Counter()
        self.gross = 0.0
        self.usable = 0.0
        self.wet = 0.0
        self.sfha = 0.0
        self.share_buckets = Counter()

    def add(self, res: dict) -> None:
        self.c["rows"] += 1
        if res["measured"]:
            self.c["measured"] += 1
            g, u = res["gross_acres"] or 0.0, res["usable_acres"] or 0.0
            self.gross += g
            self.usable += u
            self.wet += res["wetland_acres"] or 0.0
            self.sfha += res["sfha_acres"] or 0.0
            if (res["wetland_acres"] or 0) > 0:
                self.c["any_wetland"] += 1
            if (res["sfha_acres"] or 0) > 0:
                self.c["any_sfha"] += 1
            if g > 0:
                lost = 1 - u / g
                self.share_buckets["0%" if lost <= 0 else "<10%" if lost < 0.1
                                   else "10-50%" if lost < 0.5 else "50-99%" if lost < 0.99
                                   else "~100%"] += 1
            if g >= 1.5 > u:
                self.c["usable_below_1_5"] += 1
            if g >= 5 > u:
                self.c["usable_below_5_from_5plus"] += 1
        if res["improvement_share"] is not None:
            self.c["valued"] += 1
            if res["existing_building"]:
                self.c["existing_building"] += 1

    def report(self, label: str) -> str:
        c = self.c
        pct = (lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a")  # noqa: E731
        return (
            f"{label}: rows {c['rows']:,}; overlay-measured {c['measured']:,}; "
            f"gross {self.gross:,.0f} ac -> usable {self.usable:,.0f} ac "
            f"({pct(self.gross - self.usable, self.gross)} removed; wetland {self.wet:,.0f} ac, "
            f"SFHA {self.sfha:,.0f} ac, union-adjusted); parcels touching wetland "
            f"{c['any_wetland']:,}, SFHA {c['any_sfha']:,}; acreage lost "
            f"{dict(self.share_buckets)}; >=1.5ac gross but usable <1.5: "
            f"{c['usable_below_1_5']:,}; >=5ac gross but usable <5: "
            f"{c['usable_below_5_from_5plus']:,}; improvement value known "
            f"{c['valued']:,} ({pct(c['valued'], c['rows'])}), existing_building "
            f"{c['existing_building']:,}"
        )


async def run(args) -> int:
    import asyncpg

    from _db import get_sync_dsn

    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, timeout=120)
    fetcher = TileFetcher(Path(args.cache_dir), args.tile_deg, args.concurrency,
                          offline=args.offline)
    try:
        await conn.execute(f"SET statement_timeout = '{int(args.statement_timeout_min)}min'")
        has_cols = await conn.fetchval(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = "
            "'parcel_keep_metrics' AND column_name IN ('usable_acres', 'usable_computed_at')")
        if args.dry_run:
            await conn.execute("SET default_transaction_read_only = on")
        elif has_cols < 2:
            raise SystemExit("parcel_keep_metrics.usable_acres missing — apply migration 0060 first")
        where, params = "", []
        if args.jurisdiction:
            params.append(args.jurisdiction)
            where += (" AND (j.id::text = $1 OR j.name = $1)")
        if args.state:
            params.append(args.state.upper())
            where += f" AND coalesce(p.state, j.state) = ${len(params)}"
        juris = await conn.fetch(_JURIS_SQL.format(where=where), *params)
        todo = ("" if (args.recompute or has_cols < 2)
                else "AND k.usable_computed_at IS NULL")
        rows_sql = _ROWS_SQL.format(todo=todo)
        total = Tally()
        for j in juris:
            t0 = time.monotonic()
            jt = Tally()
            last = 0
            while True:
                rows = [dict(r) for r in await conn.fetch(rows_sql, j["jid"], last, args.batch_size)]
                if not rows:
                    break
                last = rows[-1]["parcel_id"]
                from shapely import wkb as _wkb

                tiles = set()
                for r in rows:
                    if r["wkb"] is not None:
                        try:
                            tiles.update(tiles_for_bounds(*_wkb.loads(bytes(r["wkb"])).bounds,
                                                          args.tile_deg))
                        except Exception:  # noqa: BLE001
                            pass
                feats = await fetcher.fetch_all(tiles)
                results = compute_rows(rows, feats, args.tile_deg)
                for res in results:
                    jt.add(res)
                    total.add(res)
                if not args.dry_run:
                    async with conn.transaction():
                        await conn.execute(
                            _UPDATE_SQL,
                            [r["parcel_id"] for r in results],
                            [r["gross_acres"] for r in results],
                            [r["usable_acres"] for r in results],
                            [r["wetland_acres"] for r in results],
                            [r["sfha_acres"] for r in results],
                            [r["improvement_share"] for r in results],
                            [r["existing_building"] for r in results],
                            [r["measured"] for r in results],
                        )
                logger.info("%s: %d rows done (last id %d); tiles %s", j["name"],
                            jt.c["rows"], last, dict(fetcher.stats))
            print(jt.report(f"[{j['state']}] {j['name']} ({time.monotonic() - t0:.0f}s)"),
                  flush=True)
        print(total.report("TOTAL"))
        print(f"tiles: {dict(fetcher.stats)}")
        if args.dry_run:
            print("DRY RUN — no writes")
    finally:
        await conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="measure + report; no writes")
    ap.add_argument("--jurisdiction", help="one jurisdiction (id or exact name)")
    ap.add_argument("--state", help="one state (2-letter)")
    ap.add_argument("--recompute", action="store_true",
                    help="redo rows already measured (default: only usable_computed_at NULL)")
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument("--tile-deg", type=float, default=TILE_DEG)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--offline", action="store_true",
                    help="cache only; tiles not cached leave parcels unmeasured")
    ap.add_argument("--statement-timeout-min", type=int, default=10)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:  # pragma: no cover
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
