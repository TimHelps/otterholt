#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from shapely import make_valid, union_all
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape

from common import (
    CACHE,
    WALK_MINUTES,
    feature_collection,
    read_json,
    request_json,
    write_json,
)

VALHALLA_URL = "https://valhalla1.openstreetmap.de/isochrone"
ORS_URL = "https://api.openrouteservice.org/v2/isochrones/foot-walking"
VALHALLA_GROUPS = [
    WALK_MINUTES[index : index + 4] for index in range(0, len(WALK_MINUTES), 4)
]


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")


def polygonal(geometry):
    geometry = make_valid(geometry)
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = [
            part
            for part in geometry.geoms
            if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
        ]
        return union_all(polygons) if polygons else MultiPolygon()
    return MultiPolygon()


def parse_valhalla(data: dict[str, Any]) -> dict[int, Any]:
    contours = {}
    for feature in data.get("features", []):
        minutes = int(round(float(feature.get("properties", {}).get("contour", 0))))
        if minutes in WALK_MINUTES:
            contours[minutes] = shape(feature["geometry"])
    return contours


def parse_ors(data: dict[str, Any]) -> dict[int, Any]:
    contours = {}
    for feature in data.get("features", []):
        seconds = float(feature.get("properties", {}).get("value", 0))
        minutes = int(round(seconds / 60))
        if minutes in WALK_MINUTES:
            contours[minutes] = shape(feature["geometry"])
    return contours


def fetch_contours(
    category: str,
    point_id: str,
    coordinates: list[float],
    provider: str,
) -> dict[int, Any]:
    lon, lat = coordinates
    cache_directory = CACHE / "isochrones" / provider / category
    cache_directory.mkdir(parents=True, exist_ok=True)
    contours = {}

    if provider == "ors":
        groups = [WALK_MINUTES]
    else:
        groups = VALHALLA_GROUPS

    for index, minutes_group in enumerate(groups):
        cache_path = cache_directory / f"{safe_id(point_id)}-{index}.json"
        if cache_path.exists():
            data = read_json(cache_path)
        elif provider == "ors":
            api_key = os.environ.get("ORS_API_KEY")
            if not api_key:
                raise RuntimeError("ORS_API_KEY is required when ISOCHRONE_PROVIDER=ors")
            data = request_json(
                ORS_URL,
                payload={
                    "locations": [[lon, lat]],
                    "range": [minutes * 60 for minutes in minutes_group],
                    "range_type": "time",
                    "smoothing": 40,
                },
                headers={"Authorization": api_key},
            )
            write_json(cache_path, data, compact=True)
            time.sleep(0.2)
        else:
            data = request_json(
                VALHALLA_URL,
                payload={
                    "locations": [{"lat": lat, "lon": lon}],
                    "costing": "pedestrian",
                    "contours": [{"time": minutes} for minutes in minutes_group],
                    "polygons": True,
                    "denoise": 0.5,
                    "generalize": 25,
                },
                headers={"X-Client-Id": "otterholt-local-development"},
            )
            write_json(cache_path, data, compact=True)
            time.sleep(0.25)

        parsed = parse_ors(data) if provider == "ors" else parse_valhalla(data)
        contours.update(parsed)

    missing = set(WALK_MINUTES) - set(contours)
    if missing:
        raise RuntimeError(f"{category}/{point_id} is missing contours: {sorted(missing)}")
    return contours


def build_category(
    source_path: Path,
    category: str,
    provider: str,
) -> dict[str, Any]:
    points = read_json(source_path).get("features", [])
    if not points:
        raise RuntimeError(f"No points found in {source_path}")

    shapes_by_minutes: defaultdict[int, list[Any]] = defaultdict(list)
    print(f"Generating {category} contours for {len(points)} locations via {provider}…")

    for index, feature in enumerate(points, start=1):
        point_id = str(feature.get("id") or feature["properties"]["id"])
        contours = fetch_contours(
            category,
            point_id,
            feature["geometry"]["coordinates"],
            provider,
        )
        for minutes, geometry in contours.items():
            shapes_by_minutes[minutes].append(geometry)
        if index % 10 == 0 or index == len(points):
            print(f"  {category}: {index}/{len(points)}")

    features = []
    for minutes in WALK_MINUTES:
        merged = polygonal(union_all(shapes_by_minutes[minutes]))
        if merged.is_empty:
            raise RuntimeError(f"Empty {category} geometry for {minutes} minutes")
        simplified = polygonal(merged.simplify(0.00008, preserve_topology=True))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "minutes": minutes,
                    "category": category,
                    "provider": provider,
                },
                "geometry": mapping(simplified),
            }
        )
    return feature_collection(features)
