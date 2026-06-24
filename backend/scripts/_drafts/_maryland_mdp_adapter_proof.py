"""Maryland MDP statewide zoning adapter proof for nache hand-off.

HAND-OFF ARTIFACT ONLY. DO NOT FIRE.

This script turns PR #347's Maryland MDP probe into a reusable, read-only
adapter skeleton following the King WA WAZA statewide-carry pattern:

  - One statewide polygon source.
  - Per-county filters by source jurisdiction code (`JURSCODE`).
  - Source attributes preserved in `raw_attributes`.
  - Local code (`ZONING`) kept separate from generalized QA class (`GENZONE`).
  - Per-county payloads that can later feed `zoning_districts` ingest and
    county-scoped spatial backfill.

It intentionally does not connect to the database and does not provide a
production `fire` command. Nache should integrate the proof into his Maryland
domain branch, wire the write path, and run local ordinance-backed matrix work.

Truthfulness caveat from the MDP item description:
MDP generalized zoning is not a substitute for local zoning information and
should not be used to determine permissible uses for a specific property.
Use it as Class A zoning polygon infrastructure, not as ordinance evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkb import dumps as wkb_dumps


MDP_LAYER_URL = (
    "https://mdpgis.mdp.state.md.us/arcgis/rest/services/PlanningCadastre/"
    "Generalized_Zoning_2025/MapServer/0"
)
MDP_ITEM_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    "4f97daeeaab341b18eeccc068121497c?f=json"
)
ARCGIS_PAGE_SIZE = 2000
REQUEST_TIMEOUT = httpx.Timeout(90.0)

# The user request scopes this proof to Maryland's 23 counties:
# Howard + Montgomery + Baltimore County + Anne Arundel + 19 other counties.
# Baltimore City (`BACI`) is listed separately as an optional city authority
# because it is not one of the 23 counties.
PRIMARY_HANDOFF_CODES = ("BACO", "ANNE", "MONT", "HOWA")


@dataclass(frozen=True)
class MarylandCounty:
    jurscode: str
    jurisdiction_name: str
    expected_feature_count: int
    probe_acres: int
    priority: str
    note: str

    @property
    def where(self) -> str:
        return f"JURSCODE = '{self.jurscode}'"


MARYLAND_COUNTIES: tuple[MarylandCounty, ...] = (
    MarylandCounty("ALLE", "Allegany County, MD", 61, 270285, "hold", "statewide carry member"),
    MarylandCounty(
        "ANNE",
        "Anne Arundel County, MD",
        67,
        264769,
        "expansion",
        "Severna Park candidate",
    ),
    MarylandCounty(
        "BACO",
        "Baltimore County, MD",
        82,
        389421,
        "expansion",
        "Roland Park / Ruxton candidate",
    ),
    MarylandCounty("CALV", "Calvert County, MD", 30, 137617, "hold", "statewide carry member"),
    MarylandCounty("CARO", "Caroline County, MD", 82, 198789, "hold", "statewide carry member"),
    MarylandCounty("CARR", "Carroll County, MD", 111, 289562, "hold", "statewide carry member"),
    MarylandCounty("CECI", "Cecil County, MD", 138, 224841, "hold", "statewide carry member"),
    MarylandCounty("CHAR", "Charles County, MD", 64, 294228, "hold", "statewide carry member"),
    MarylandCounty("DORC", "Dorchester County, MD", 60, 359316, "hold", "statewide carry member"),
    MarylandCounty(
        "FRED",
        "Frederick County, MD",
        145,
        428772,
        "watch",
        "populated source; customer signal needed",
    ),
    MarylandCounty("GARR", "Garrett County, MD", 49, 420483, "hold", "statewide carry member"),
    MarylandCounty(
        "HARF",
        "Harford County, MD",
        54,
        281027,
        "watch",
        "populated source; customer signal needed",
    ),
    MarylandCounty(
        "HOWA",
        "Howard County, MD",
        56,
        162110,
        "calibration",
        "already operational; code-family check",
    ),
    MarylandCounty("KENT", "Kent County, MD", 66, 178114, "hold", "statewide carry member"),
    MarylandCounty(
        "MONT",
        "Montgomery County, MD",
        424,
        298632,
        "calibration",
        "already operational; regression only",
    ),
    MarylandCounty(
        "PRIN",
        "Prince George's County, MD",
        52,
        280859,
        "watch",
        "populated source; customer signal needed",
    ),
    MarylandCounty(
        "QUEE",
        "Queen Anne's County, MD",
        102,
        229984,
        "hold",
        "statewide carry member",
    ),
    MarylandCounty("SOME", "Somerset County, MD", 31, 202597, "hold", "statewide carry member"),
    MarylandCounty("STMA", "St. Mary's County, MD", 33, 215958, "hold", "statewide carry member"),
    MarylandCounty("TALB", "Talbot County, MD", 105, 170189, "hold", "statewide carry member"),
    MarylandCounty("WASH", "Washington County, MD", 148, 299456, "hold", "statewide carry member"),
    MarylandCounty("WICO", "Wicomico County, MD", 106, 232791, "hold", "statewide carry member"),
    MarylandCounty("WORC", "Worcester County, MD", 94, 297926, "hold", "statewide carry member"),
)

OPTIONAL_CITY_AUTHORITIES: tuple[MarylandCounty, ...] = (
    MarylandCounty(
        "BACI",
        "Baltimore City, MD",
        66,
        54726,
        "optional-city",
        "not one of 23 counties",
    ),
)

COUNTY_BY_CODE = {county.jurscode: county for county in MARYLAND_COUNTIES}
OPTIONAL_BY_CODE = {city.jurscode: city for city in OPTIONAL_CITY_AUTHORITIES}
ALL_BY_CODE = {**COUNTY_BY_CODE, **OPTIONAL_BY_CODE}

RAW_ATTRIBUTE_FIELDS = (
    "OBJECTID",
    "GENZONE",
    "GENZONE_CAT",
    "OVERLAY",
    "JURSCODE",
    "ZONING",
    "MUNICIPALITY_NAME",
    "ABBREVIATION",
    "UPDATEYR",
    "ACRES",
    "Source",
)


def _trim(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _zone_class_from_genzone(genzone: str | None) -> str:
    value = (genzone or "").upper()
    if "RESIDENTIAL" in value:
        return "residential"
    if "COMMERCIAL" in value:
        return "commercial"
    if "INDUSTRIAL" in value:
        return "industrial"
    if "MIXED" in value:
        return "mixed_use"
    if "AGRICULT" in value:
        return "agricultural"
    if "OPEN" in value or "PARK" in value or "CONSERVATION" in value:
        return "open_space"
    return "unknown"


def _signed_area(coords: list[tuple[float, float]]) -> float:
    area = 0.0
    for idx in range(len(coords) - 1):
        x1, y1 = coords[idx]
        x2, y2 = coords[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _ring_to_coords(ring: list[list[float]]) -> list[tuple[float, float]]:
    coords = [(float(point[0]), float(point[1])) for point in ring if len(point) >= 2]
    if len(coords) < 3:
        return []
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _arcgis_rings_to_geom(rings: list[list[list[float]]]) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    holes_by_outer: list[list[list[tuple[float, float]]]] = []

    for ring in rings:
        coords = _ring_to_coords(ring)
        if not coords:
            continue
        if _signed_area(coords) < 0:
            outers.append(coords)
            holes_by_outer.append([])
        elif outers:
            holes_by_outer[-1].append(coords)
        else:
            outers.append(coords)
            holes_by_outer.append([])

    polygons: list[Polygon] = []
    for outer, holes in zip(outers, holes_by_outer):
        try:
            polygon = Polygon(outer, holes)
        except ValueError:
            continue
        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None
    geom: BaseGeometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    geom = make_valid(geom)
    return None if geom.is_empty else geom


def _geom_hash(geom: BaseGeometry) -> str:
    return hashlib.sha256(wkb_dumps(geom, hex=False, srid=4326)).hexdigest()


async def _request_json(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    response = await client.get(f"{MDP_LAYER_URL}/query", params=params)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    return data


async def _fetch_count(client: httpx.AsyncClient, county: MarylandCounty) -> int:
    data = await _request_json(
        client,
        {
            "f": "json",
            "where": county.where,
            "returnCountOnly": "true",
        },
    )
    return int(data.get("count") or 0)


async def _fetch_features(
    client: httpx.AsyncClient,
    county: MarylandCounty,
    *,
    sample_size: int | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        page_size = ARCGIS_PAGE_SIZE
        if sample_size is not None:
            remaining = sample_size - len(features)
            if remaining <= 0:
                break
            page_size = min(page_size, remaining)

        data = await _request_json(
            client,
            {
                "f": "json",
                "where": county.where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": "OBJECTID",
            },
        )
        batch = list(data.get("features") or [])
        if not batch:
            break
        features.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return features


def build_zoning_district_payload(
    county: MarylandCounty,
    feature: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a future zoning_districts payload without touching the DB."""
    attrs = feature.get("attributes") or {}
    geom_json = feature.get("geometry") or {}
    geom = _arcgis_rings_to_geom(geom_json.get("rings") or [])
    if geom is None:
        return None

    zone_code = _trim(attrs.get("ZONING"))
    if not zone_code:
        return None

    genzone = _trim(attrs.get("GENZONE"))
    raw_attributes = {
        "source_url": MDP_LAYER_URL,
        "source_item_url": MDP_ITEM_URL,
        "source_kind": "maryland_mdp_generalized_zoning_2025",
        "source_filter": county.where,
        "handoff_owner": "nache",
        "handoff_status": "proof_not_fire_ready",
        "jurisdiction_name": county.jurisdiction_name,
        "jurscode": county.jurscode,
        "mdp_truthfulness_caveat": (
            "MDP generalized zoning is infrastructure for district geometry/code "
            "population, not local ordinance evidence for permitted-use verdicts."
        ),
    }
    for field in RAW_ATTRIBUTE_FIELDS:
        value = attrs.get(field)
        if value not in (None, ""):
            raw_attributes[field] = value

    return {
        "jurisdiction_name": county.jurisdiction_name,
        "jurscode": county.jurscode,
        "zone_code": zone_code,
        "zone_name": genzone,
        "zone_class": _zone_class_from_genzone(genzone),
        "geom_wkt": geom.wkt,
        "geom_hash": _geom_hash(geom),
        "raw_attributes": raw_attributes,
        "source": "arcgis",
    }


def _selected_counties(args: argparse.Namespace) -> list[MarylandCounty]:
    if args.all_counties:
        return list(MARYLAND_COUNTIES)
    if args.include_baltimore_city:
        selected_codes = list(PRIMARY_HANDOFF_CODES) + ["BACI"]
    else:
        selected_codes = list(PRIMARY_HANDOFF_CODES)
    if args.codes:
        selected_codes = args.codes

    counties: list[MarylandCounty] = []
    for raw_code in selected_codes:
        code = raw_code.upper()
        if code not in ALL_BY_CODE:
            valid = ", ".join(sorted(ALL_BY_CODE))
            raise SystemExit(f"Unknown JURSCODE {code!r}. Valid codes: {valid}")
        counties.append(ALL_BY_CODE[code])
    return counties


async def _catalog(args: argparse.Namespace) -> None:
    counties = _selected_counties(args)
    print("Maryland MDP statewide adapter proof catalog")
    print(f"source={MDP_LAYER_URL}")
    print("default carry scope: Maryland 23 counties; Baltimore City is optional")
    for county in counties:
        print(
            f"{county.jurscode:4s} | {county.jurisdiction_name:28s} | "
            f"probe_features={county.expected_feature_count:>3} | "
            f"priority={county.priority:11s} | {county.note}"
        )


async def _preflight(args: argparse.Namespace) -> None:
    counties = _selected_counties(args)
    print("Maryland MDP adapter proof preflight")
    print("READ-ONLY: no DB connection, no writes, no fire path")
    print(f"source={MDP_LAYER_URL}")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for county in counties:
            features = await _fetch_features(
                client,
                county,
                sample_size=args.sample_size,
            )
            rows = [
                row
                for feature in features
                if (row := build_zoning_district_payload(county, feature)) is not None
            ]
            live_count = None
            if args.with_counts:
                live_count = await _fetch_count(client, county)

            zone_codes = sorted({row["zone_code"] for row in rows})
            genzones = sorted(
                {
                    str(row["raw_attributes"].get("GENZONE"))
                    for row in rows
                    if row["raw_attributes"].get("GENZONE")
                }
            )
            null_zone = len(features) - len(rows)
            print()
            print(f"[{county.jurscode}] {county.jurisdiction_name}")
            print(f"  query              : {county.where}")
            print(f"  probe count        : {county.expected_feature_count}")
            print(f"  live count         : {live_count if live_count is not None else 'skipped'}")
            print(f"  sample features    : {len(features)}")
            print(f"  payload rows       : {len(rows)}")
            print(f"  skipped null ZONING: {null_zone}")
            print(f"  zone_code sample   : {zone_codes[:12]}")
            print(f"  GENZONE sample     : {genzones[:8]}")
            if rows:
                sample = rows[0].copy()
                sample["geom_wkt"] = sample["geom_wkt"][:96] + "..."
                print(f"  payload sample     : {json.dumps(sample, sort_keys=True)[:1200]}")


async def _emit_directory(args: argparse.Namespace) -> None:
    """Emit a future directory skeleton for nache's integration branch."""
    entries = []
    for county in _selected_counties(args):
        entries.append(
            {
                "jurisdiction_name": county.jurisdiction_name,
                "state": "MD",
                "jurscode": county.jurscode,
                "status": "handoff_proof_not_fire_ready",
                "priority": county.priority,
                "source": {
                    "kind": "maryland_mdp_generalized_zoning_2025",
                    "url": MDP_LAYER_URL,
                    "item_url": MDP_ITEM_URL,
                    "filter_query": county.where,
                    "out_sr": 4326,
                    "field_map": {
                        "zone_code": "ZONING",
                        "zone_name": "GENZONE",
                        "zone_class_hint": "GENZONE",
                        "municipality": "MUNICIPALITY_NAME",
                        "update_year": "UPDATEYR",
                    },
                    "raw_attributes_passthrough": list(RAW_ATTRIBUTE_FIELDS),
                    "truthfulness_caveat": (
                        "Use MDP polygons for zoning_district geometry/code "
                        "population. Do not use GENZONE as ordinance verdict evidence."
                    ),
                },
                "probe": {
                    "feature_count": county.expected_feature_count,
                    "acres": county.probe_acres,
                    "note": county.note,
                },
                "handoff_next_steps": [
                    "Verify parcel substrate exists for this jurisdiction.",
                    "Run bbox coverage and 1,000-parcel ST_Within dry-run gates.",
                    "Ingest zoning_districts with raw_attributes preserved.",
                    "Backfill parcels with contained pass plus capped nearest fallback.",
                    "Author matrix rows from local county ordinances, not from GENZONE.",
                ],
            }
        )
    print(json.dumps(entries, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_scope_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--codes",
            nargs="+",
            help="Specific JURSCODE values to include, e.g. BACO ANNE HOWA.",
        )
        subparser.add_argument(
            "--all-counties",
            action="store_true",
            help="Use all 23 Maryland counties. Excludes Baltimore City.",
        )
        subparser.add_argument(
            "--include-baltimore-city",
            action="store_true",
            help="Include optional Baltimore City code BACI in the default scope.",
        )

    catalog = subparsers.add_parser("catalog", help="Print configured carry scope.")
    add_scope_flags(catalog)
    catalog.set_defaults(func=_catalog)

    preflight = subparsers.add_parser(
        "preflight",
        help="Fetch source samples and build proof payloads. Read-only.",
    )
    add_scope_flags(preflight)
    preflight.add_argument("--sample-size", type=int, default=5)
    preflight.add_argument("--with-counts", action="store_true")
    preflight.set_defaults(func=_preflight)

    directory = subparsers.add_parser(
        "emit-directory",
        help="Emit a future integration directory skeleton as JSON.",
    )
    add_scope_flags(directory)
    directory.set_defaults(func=_emit_directory)

    return parser


async def _main_async() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    await args.func(args)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
