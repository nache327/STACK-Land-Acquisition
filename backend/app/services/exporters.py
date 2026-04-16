"""
Export utilities: CSV and GeoJSON parcel exports.

Used by the shortlist CSV endpoint and the frontend "Export all" button.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.models.parcel import Parcel


CSV_COLUMNS = [
    "apn",
    "address",
    "owner_name",
    "acres",
    "zoning_code",
    "land_use_code",
    "improvement_value",
    "has_structure",
    "in_flood_zone",
    "avg_slope_pct",
    "in_wetland",
    "county_link",
]


def parcels_to_csv(parcels: list[Parcel]) -> str:
    """Serialize a list of Parcel ORM objects to a CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for p in parcels:
        writer.writerow({col: getattr(p, col, "") or "" for col in CSV_COLUMNS})
    return output.getvalue()


def parcels_to_geojson(parcels: list[Parcel], geometries: list[dict]) -> dict[str, Any]:
    """
    Build a GeoJSON FeatureCollection from parcels + pre-serialized geometries.

    Args:
        parcels: ORM Parcel objects (in the same order as geometries)
        geometries: List of GeoJSON geometry dicts (one per parcel)
    """
    features = []
    for parcel, geom in zip(parcels, geometries):
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {col: getattr(parcel, col, None) for col in CSV_COLUMNS},
        })
    return {"type": "FeatureCollection", "features": features}
