"""Data plumbing for the keep-market precompute (scripts/precompute_keep_metrics.py).

Ported from the 2026-10 calibration scripts (outputs/keep_calibration/_scripts:
fetch_census.py, fetch_wealth.py, pools.py, wealth_center.py) so the production
numbers are computed EXACTLY the way the thresholds in ``keep_market`` were calibrated:

  * Tract shapes: Census cartographic boundaries cb_2022_<st>_tract_500k (as pools.py),
    projected to EPSG:5070 (equal-area) for area shares.
  * 20-min pool: tracts intersecting the isochrone, each weighted by
    intersection_area / tract_area (pools.py ``shares``), summing ACS 2022 5-yr counts.
  * Wealth centers: clusters of >= 3 contiguous tracts (1 m buffer touch) each with
    median home value (B25077) >= $1M nationwide; population-weighted centroid.
    Fallback when no cluster lies within 60 km: the nearest single tract >= $750K
    (labelled FALLBACK). Drive time = Mapbox Matrix (driving) to the nearest-by-km
    candidate, as wealth_center.py reported it.
  * County home $/SF: Zillow ZHVI county series, latest FULL calendar year mean ÷ 1,800.

Everything fetched is cached under a caller-supplied cache dir so reruns are cheap and
resumable. Pure helpers (aggregation, batching, ZHVI parsing, clustering) are unit-tested
without network or DB. SECURITY: the Census key and Mapbox token are read from settings
and never logged; error messages are scrubbed of query strings.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

EQUAL_AREA_CRS = 5070

# 50 states + DC (the calibration's national set; PR excluded).
STATE_FIPS: tuple[str, ...] = (
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15", "16", "17",
    "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31",
    "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42", "44", "45", "46",
    "47", "48", "49", "50", "51", "53", "54", "55", "56",
)

ACS_YEAR = 2022
# B01003 population · B25077 median home value · B25075 owner units by value
# (_025 $1.0–1.5M, _026 $1.5–2M, _027 $2M+) · B19001_017 HH income $200k+ ·
# B25004_006 vacant seasonal/recreational units · B25001 housing units ·
# B19037_052 HH 45–64 with $200k+ · B19037_069 HH 65+ with $200k+.
ACS_VARS: tuple[str, ...] = (
    "B01003_001E", "B25077_001E", "B25075_001E", "B25075_025E", "B25075_026E",
    "B25075_027E", "B19001_017E", "B25004_006E", "B25001_001E", "B19037_052E",
    "B19037_069E",
)
OWNER_1M_VARS: tuple[str, ...] = ("B25075_025E", "B25075_026E", "B25075_027E")

WEALTH_TRACT_HV = 1_000_000
WEALTH_FALLBACK_HV = 750_000
WEALTH_CLUSTER_MIN_TRACTS = 3
WEALTH_CLUSTER_RADIUS_KM = 60.0
WEALTH_CANDIDATES = 5          # nearest-by-km candidates sent to the Matrix API

MATRIX_MAX_COORDS = 25         # Mapbox Directions Matrix limit (driving profile)
MATRIX_RPM = 60                # Mapbox Matrix default rate limit (requests/min)
_MATRIX_URL = "https://api.mapbox.com/directions-matrix/v1/mapbox/driving"

_TRACT_SHP_URL = "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_{st}_tract_500k.zip"
_ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"

POOL_MINUTES = 20


def _scrub(e: BaseException) -> str:
    """Exception text without any URL query string (keys/tokens live there)."""
    s = f"{type(e).__name__}: {e}"
    for marker in ("access_token", "key=", "?"):
        s = s.split(marker)[0]
    return s[:300]


# ── Download / cache helpers ─────────────────────────────────────────────────

def _download(url: str, path: Path, timeout: float = 600.0, tries: int = 4) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    last: BaseException | None = None
    for i in range(tries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0 ParcelLogic keep-market"}) as c:
                r = c.get(url)
                r.raise_for_status()
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            return path
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"download failed for {path.name}: {_scrub(last)}")


def ensure_tract_shapes(cache_dir: Path, states: Iterable[str] = STATE_FIPS) -> list[Path]:
    """Download (once) the cb_2022 500k tract shapefile for each state."""
    out = []
    for st in states:
        out.append(_download(_TRACT_SHP_URL.format(st=st),
                             cache_dir / "tracts" / f"cb_2022_{st}_tract_500k.zip"))
    return out


def ensure_acs(cache_dir: Path, census_key: str, states: Iterable[str] = STATE_FIPS):
    """ACS 2022 5-yr tract table for ACS_VARS, nationwide, cached per state.

    Returns a pandas DataFrame indexed by GEOID with float columns; Census jam values
    (any negative) become NaN — every variable here is a count or a dollar median."""
    import pandas as pd

    frames = []
    for st in states:
        path = cache_dir / "acs" / f"acs{ACS_YEAR}_keep_{st}.csv"
        if not (path.exists() and path.stat().st_size > 0):
            path.parent.mkdir(parents=True, exist_ok=True)
            params = {"get": ",".join(ACS_VARS), "for": "tract:*",
                      "in": [f"state:{st}", "county:*"]}
            if census_key:
                params["key"] = census_key
            last: BaseException | None = None
            rows = None
            for i in range(4):
                try:
                    with httpx.Client(timeout=300) as c:
                        r = c.get(_ACS_URL.format(year=ACS_YEAR), params=params)
                        r.raise_for_status()
                        rows = r.json()
                    break
                except Exception as e:  # noqa: BLE001
                    last = e
                    time.sleep(3 * (i + 1))
            if rows is None:
                raise RuntimeError(f"ACS fetch failed for state {st}: {_scrub(last)}")
            df = pd.DataFrame(rows[1:], columns=rows[0])
            df["GEOID"] = df["state"] + df["county"] + df["tract"]
            df[["GEOID", *ACS_VARS]].to_csv(path, index=False)
        frames.append(pd.read_csv(path, dtype={"GEOID": str}))
    a = pd.concat(frames).set_index("GEOID")
    a = a.apply(pd.to_numeric, errors="coerce")
    return a.where(a >= 0)


def load_tracts(cache_dir: Path, states: Iterable[str] = STATE_FIPS):
    """National tract GeoDataFrame in EPSG:5070 with GEOID + tarea (m²)."""
    import geopandas as gpd
    import pandas as pd

    paths = ensure_tract_shapes(cache_dir, states)
    parts = [gpd.read_file(f"zip://{p}")[["GEOID", "geometry"]] for p in paths]
    crs = parts[0].crs
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=crs).to_crs(EQUAL_AREA_CRS)
    g["tarea"] = g.geometry.area
    return g


# ── 20-min pool aggregation (pools.py parity) ────────────────────────────────

@dataclass(frozen=True)
class PoolMetrics:
    hh_200k_20: int | None
    owner_1m_count_20: int | None
    owner_1m_share_20: float | None
    seasonal_share_20: float | None
    young_old_200k_ratio_20: float | None


def _ratio(num: float, den: float, nd: int) -> float | None:
    return round(num / den, nd) if den and den > 0 else None


def aggregate_pool(rows: Iterable[tuple[float, dict[str, float]]]) -> PoolMetrics:
    """Area-share-weighted sums over (share, acs_row) pairs → the five pool metrics.

    NaN/None cells are skipped (pandas ``sum`` semantics in the calibration). An empty
    pool (no ACS rows at all) yields all-None — unmeasured, never zero."""
    sums: dict[str, float] = {}
    n = 0
    for share, acs in rows:
        n += 1
        for k, v in acs.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            sums[k] = sums.get(k, 0.0) + float(v) * share
    if n == 0:
        return PoolMetrics(None, None, None, None, None)

    def S(k: str) -> float:
        return sums.get(k, 0.0)

    own = S("B25075_001E")
    m1 = sum(S(k) for k in OWNER_1M_VARS)
    return PoolMetrics(
        hh_200k_20=int(round(S("B19001_017E"))),
        owner_1m_count_20=int(round(m1)),
        owner_1m_share_20=_ratio(m1, own, 5),
        seasonal_share_20=_ratio(S("B25004_006E"), S("B25001_001E"), 5),
        young_old_200k_ratio_20=_ratio(S("B19037_052E"), S("B19037_069E"), 4),
    )


def pool_for_isochrone(iso_4326, tracts, acs_rows: dict[str, dict]) -> PoolMetrics:
    """Intersect an isochrone (shapely, EPSG:4326) with the national tracts (5070).

    ``acs_rows`` is ``acs.to_dict("index")`` (GEOID → {var: value}), built once."""
    import geopandas as gpd
    import shapely

    ip = gpd.GeoSeries([iso_4326], crs=4326).to_crs(EQUAL_AREA_CRS).iloc[0]
    if not ip.is_valid:
        ip = ip.buffer(0)
    idx = tracts.sindex.query(ip, predicate="intersects")
    cand = tracts.iloc[idx]
    inter = shapely.area(shapely.intersection(cand.geometry.values, ip))
    rows = []
    for geoid, ia, tarea in zip(cand.GEOID.values, inter, cand.tarea.values):
        if tarea <= 0 or geoid not in acs_rows:
            continue
        share = min(max(float(ia) / float(tarea), 0.0), 1.0)
        if share <= 0:
            continue
        rows.append((share, acs_rows[geoid]))
    return aggregate_pool(rows)


# ── Wealth centers (wealth_center.py parity) ─────────────────────────────────

@dataclass(frozen=True)
class WealthCenter:
    center_id: str        # 'C:<min geoid>' cluster | 'S:<geoid>' fallback single
    kind: str             # 'cluster' | 'single'
    n_tracts: int
    lat: float
    lng: float
    pop: int
    hv_ownerwtd: float | None

    @property
    def label(self) -> str:
        hv = f"${self.hv_ownerwtd / 1e6:.2f}M" if self.hv_ownerwtd else "n/a"
        anchor = self.center_id[2:]
        if self.kind == "cluster":
            return f"$1M+ cluster: {self.n_tracts} tracts, owner-wtd HV {hv} (anchor {anchor})"
        return (f"FALLBACK single tract HV {hv} ({anchor}) — no {WEALTH_CLUSTER_MIN_TRACTS}"
                f"-tract $1M cluster within {WEALTH_CLUSTER_RADIUS_KM:.0f} km")


def cluster_labels(n: int, pairs: Iterable[tuple[int, int]]) -> list[int]:
    """Union-find connected components over index pairs → root label per index."""
    par = list(range(n))

    def find(x: int) -> int:
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for u, v in pairs:
        ru, rv = find(int(u)), find(int(v))
        if ru != rv:
            par[ru] = rv
    return [find(k) for k in range(n)]


def _center_rows(df, key: str, kind: str) -> list[WealthCenter]:
    import geopandas as gpd

    out_xy = []
    meta = []
    for _, g in df.groupby(key):
        w = g.B01003_001E.fillna(0)
        if w.sum() <= 0:
            w = w * 0 + 1.0
        x = float((g.px_ * w).sum() / w.sum())
        y = float((g.py_ * w).sum() / w.sum())
        ow = g.B25075_001E.fillna(0)
        hv = float((g.B25077_001E * ow).sum() / ow.sum()) if ow.sum() > 0 else float(g.B25077_001E.mean())
        out_xy.append((x, y))
        meta.append((min(g.GEOID), len(g), int(g.B01003_001E.fillna(0).sum()), hv))
    if not out_xy:
        return []
    ll = gpd.GeoSeries(gpd.points_from_xy([p[0] for p in out_xy], [p[1] for p in out_xy]),
                       crs=EQUAL_AREA_CRS).to_crs(4326)
    res = []
    for (anchor, n, pop, hv), pt in zip(meta, ll.values):
        res.append(WealthCenter(
            center_id=("C:" if kind == "cluster" else "S:") + anchor, kind=kind, n_tracts=n,
            lat=round(pt.y, 6), lng=round(pt.x, 6), pop=pop,
            hv_ownerwtd=None if hv != hv else round(hv)))
    return res


def build_wealth_centers(tracts, acs) -> list[WealthCenter]:
    """Clusters of >= 3 contiguous $1M+ tracts, plus single $750K+ tracts (fallback)."""
    import geopandas as gpd

    t = tracts.join(acs[["B25077_001E", "B01003_001E", "B25075_001E"]], on="GEOID")
    hi = t[t.B25077_001E >= WEALTH_TRACT_HV].reset_index(drop=True)
    buf = gpd.GeoDataFrame(geometry=hi.geometry.buffer(1.0), crs=EQUAL_AREA_CRS)
    pairs = gpd.sjoin(buf, buf, predicate="intersects")
    hi["cl"] = cluster_labels(len(hi), zip(pairs.index.values, pairs.index_right.values))
    hi["px_"], hi["py_"] = hi.geometry.centroid.x, hi.geometry.centroid.y
    sizes = hi.groupby("cl").size()
    clusters = _center_rows(hi[hi.cl.isin(sizes[sizes >= WEALTH_CLUSTER_MIN_TRACTS].index)],
                            "cl", "cluster")
    t75 = t[t.B25077_001E >= WEALTH_FALLBACK_HV].copy()
    t75["px_"], t75["py_"] = t75.geometry.centroid.x, t75.geometry.centroid.y
    singles = _center_rows(t75, "GEOID", "single")
    logger.info("wealth centers: %d tracts >= $1M, %d clusters >= %d tracts, %d single >= $750K",
                len(hi), len(clusters), WEALTH_CLUSTER_MIN_TRACTS, len(singles))
    return clusters + singles


def save_wealth_centers(path: Path, centers: list[WealthCenter]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["center_id", "kind", "n_tracts", "lat", "lng", "pop", "hv_ownerwtd"])
        for c in centers:
            w.writerow([c.center_id, c.kind, c.n_tracts, c.lat, c.lng, c.pop,
                        "" if c.hv_ownerwtd is None else c.hv_ownerwtd])


def load_wealth_centers(path: Path) -> list[WealthCenter]:
    with path.open(encoding="utf-8") as f:
        return [WealthCenter(r["center_id"], r["kind"], int(r["n_tracts"]), float(r["lat"]),
                             float(r["lng"]), int(r["pop"]),
                             float(r["hv_ownerwtd"]) if r["hv_ownerwtd"] else None)
                for r in csv.DictReader(f)]


class WealthCenterIndex:
    """Nearest-center lookup (geodesic km) with the calibration's 60 km fallback rule."""

    def __init__(self, centers: list[WealthCenter]):
        import numpy as np

        self.clusters = [c for c in centers if c.kind == "cluster"]
        self.singles = [c for c in centers if c.kind == "single"]
        self._np = np
        self._c_lat = np.array([c.lat for c in self.clusters])
        self._c_lng = np.array([c.lng for c in self.clusters])
        self._s_lat = np.array([c.lat for c in self.singles])
        self._s_lng = np.array([c.lng for c in self.singles])
        self.by_id = {c.center_id: c for c in centers}

    def _km(self, lat: float, lng: float, lats, lngs):
        from pyproj import Geod

        np = self._np
        if len(lats) == 0:
            return np.array([])
        _, _, d = Geod(ellps="WGS84").inv(np.full(len(lats), lng), np.full(len(lats), lat),
                                          lngs, lats)
        return d / 1000.0

    def candidates(self, lat: float, lng: float, k: int = WEALTH_CANDIDATES
                   ) -> list[tuple[str, float]]:
        """[(center_id, km)] sorted by km — clusters when one is within 60 km, else
        the nearest single $750K+ tracts (fallback)."""
        np = self._np
        ck = self._km(lat, lng, self._c_lat, self._c_lng)
        if len(ck) and float(ck.min()) <= WEALTH_CLUSTER_RADIUS_KM:
            order = np.argsort(ck)[:k]
            return [(self.clusters[i].center_id, float(ck[i])) for i in order]
        sk = self._km(lat, lng, self._s_lat, self._s_lng)
        if not len(sk):
            return []
        order = np.argsort(sk)[:k]
        return [(self.singles[i].center_id, float(sk[i])) for i in order]


def pick_center(cands: list[tuple[str, float]], durations: dict[str, float | None]
                ) -> tuple[str | None, float | None, float | None]:
    """(center_id, drive_min, km): the nearest-by-km candidate (as calibrated); if its
    drive time is missing, the fastest candidate that has one."""
    if not cands:
        return None, None, None
    cid, km = cands[0]
    d = durations.get(cid)
    if d is not None:
        return cid, d, km
    timed = [(durations[c], c, k) for c, k in cands if durations.get(c) is not None]
    if timed:
        d, cid, km = min(timed)
        return cid, d, km
    return cid, None, km


# ── Mapbox Matrix batching ───────────────────────────────────────────────────

def plan_matrix_batches(origins: dict[str, list[str]], max_coords: int = MATRIX_MAX_COORDS
                        ) -> list[tuple[list[str], list[str]]]:
    """Group origins into Matrix requests: each request's origins + union of their
    destinations must fit in max_coords. Origins sharing candidate sets pack together
    (neighbouring tracts almost always share their 5 nearest centers)."""
    batches: list[tuple[list[str], list[str]]] = []
    cur_o: list[str] = []
    cur_d: list[str] = []
    for g, cands in sorted(origins.items(), key=lambda kv: (tuple(kv[1]), kv[0])):
        if not cands:
            continue
        new_d = cur_d + [c for c in cands if c not in cur_d]
        if cur_o and len(cur_o) + 1 + len(new_d) > max_coords:
            batches.append((cur_o, cur_d))
            cur_o, cur_d = [], []
            new_d = list(dict.fromkeys(cands))
        cur_o.append(g)
        cur_d = new_d
    if cur_o:
        batches.append((cur_o, cur_d))
    return batches


class MatrixClient:
    """Minimal async Mapbox Directions Matrix client (driving), rate-limited."""

    def __init__(self, token: str, rpm: int = MATRIX_RPM, client: httpx.AsyncClient | None = None):
        from app.services.mapbox_isochrone import MapboxConfigError, _SlidingWindowRateLimiter

        if not token:
            raise MapboxConfigError("MAPBOX_TOKEN is empty — Matrix API disabled.")
        self._token = token
        self._limiter = _SlidingWindowRateLimiter(rpm)
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._sem = asyncio.Semaphore(4)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def durations(self, origins: list[tuple[float, float]],
                        dests: list[tuple[float, float]]) -> list[list[float | None]]:
        """Minutes, [origin][dest]; None where Mapbox found no route."""
        coords = ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in [*origins, *dests])
        n_o = len(origins)
        params = {
            "sources": ";".join(str(i) for i in range(n_o)),
            "destinations": ";".join(str(n_o + j) for j in range(len(dests))),
            "annotations": "duration",
            "access_token": self._token,
        }
        last = ""
        async with self._sem:
            for attempt in range(5):
                await self._limiter.acquire()
                try:
                    r = await self._client.get(f"{_MATRIX_URL}/{coords}", params=params)
                except httpx.HTTPError as e:
                    last = _scrub(e)
                    await asyncio.sleep(1.0 * 2 ** attempt)
                    continue
                if r.status_code == 200:
                    j = r.json()
                    if j.get("code") != "Ok":
                        raise RuntimeError(f"Matrix code {j.get('code')}")
                    return [[None if v is None else v / 60.0 for v in row]
                            for row in j["durations"]]
                last = f"HTTP {r.status_code}"
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("Retry-After")
                    await asyncio.sleep(float(ra) if ra and ra.isdigit() else 2.0 * 2 ** attempt)
                    continue
                break
        raise RuntimeError(f"Matrix request failed: {last}")


# ── ZHVI county home $/SF ────────────────────────────────────────────────────

def load_zhvi_county_ppsf(path: Path | str) -> tuple[int | None, dict[str, float]]:
    """(year, {county_fips5: home_ppsf}) from a Zillow ZHVI county CSV.

    Uses the latest calendar year with all 12 monthly columns present in the header;
    each county's value is the mean of that year's non-empty months ÷ 1,800 SF."""
    from app.services.keep_market import county_home_ppsf

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        months: dict[int, list[int]] = {}
        for i, h in enumerate(header):
            if len(h) == 10 and h[4] == "-" and h[:4].isdigit():
                months.setdefault(int(h[:4]), []).append(i)
        full = [y for y, cols in months.items() if len(cols) == 12]
        if not full:
            return None, {}
        year = max(full)
        cols = months[year]
        i_st = header.index("StateCodeFIPS")
        i_co = header.index("MunicipalCodeFIPS")
        out: dict[str, float] = {}
        for row in reader:
            try:
                fips = row[i_st].strip().zfill(2) + row[i_co].strip().zfill(3)
            except IndexError:
                continue
            vals = []
            for c in cols:
                v = row[c].strip() if c < len(row) else ""
                if v:
                    try:
                        vals.append(float(v))
                    except ValueError:
                        pass
            if vals:
                ppsf = county_home_ppsf(sum(vals) / len(vals))
                if ppsf is not None:
                    out[fips] = round(ppsf, 2)
    return year, out


# ── Isochrone cache ──────────────────────────────────────────────────────────

def iso_cache_path(cache_dir: Path, geoid: str) -> Path:
    return cache_dir / f"iso{POOL_MINUTES}" / f"{geoid}.json"


def read_iso(cache_dir: Path, geoid: str):
    from shapely.geometry import shape

    p = iso_cache_path(cache_dir, geoid)
    if not p.exists():
        return None
    try:
        return shape(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a corrupt cache entry is refetched
        return None


def write_iso(cache_dir: Path, geoid: str, geom) -> None:
    from shapely.geometry import mapping

    p = iso_cache_path(cache_dir, geoid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_text(json.dumps(mapping(geom)), encoding="utf-8")
    tmp.replace(p)


def matrix_cache_path(cache_dir: Path, geoid: str) -> Path:
    return cache_dir / "wc_drive" / f"{geoid}.json"


def read_matrix(cache_dir: Path, geoid: str, cands: list[str]) -> dict[str, Any] | None:
    p = matrix_cache_path(cache_dir, geoid)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return d if set(d.get("dur", {})) >= set(cands) else None


def write_matrix(cache_dir: Path, geoid: str, dur: dict[str, float | None]) -> None:
    p = matrix_cache_path(cache_dir, geoid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"dur": dur}), encoding="utf-8")


