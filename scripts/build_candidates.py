#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import os
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape

from common import (
    CACHE,
    PUBLIC_DATA,
    USER_AGENT,
    WALK_MINUTES,
    ensure_directories,
    read_json,
    write_json,
)
from generate_contours import build_category, fetch_contours
from pool_operators import POOL_OPERATORS, candidate_fields

CODE_POINT_URL = (
    "https://api.os.uk/downloads/v1/products/CodePointOpen/downloads"
    "?area=GB&format=CSV&redirect"
)


def download_code_point() -> Path:
    destination = CACHE / "sources" / "code-point-open.zip"
    if destination.exists() and destination.stat().st_size:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.part")
    request = urllib.request.Request(CODE_POINT_URL, headers={"User-Agent": USER_AGENT})
    print("Downloading Code-Point Open…")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
        "wb"
    ) as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(destination)
    return destination


def load_postcodes(
    archive_path: Path, relevant_districts: set[str]
) -> tuple[list[str], np.ndarray, np.ndarray]:
    postcodes = []
    eastings = []
    northings = []

    with zipfile.ZipFile(archive_path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("Data/CSV/") and name.endswith(".csv")
        ]
        for name in names:
            with archive.open(name) as binary:
                source = io.TextIOWrapper(binary, encoding="utf-8", newline="")
                for row in csv.reader(source):
                    if len(row) < 4:
                        continue
                    postcode = row[0].strip().upper()
                    district = postcode.split(" ", 1)[0]
                    if district not in relevant_districts:
                        continue
                    try:
                        easting = int(row[2])
                        northing = int(row[3])
                    except ValueError:
                        continue
                    if 480_000 <= easting <= 580_000 and 145_000 <= northing <= 220_000:
                        postcodes.append(postcode)
                        eastings.append(easting)
                        northings.append(northing)

    transformer = Transformer.from_crs(27700, 4326, always_xy=True)
    longitudes, latitudes = transformer.transform(
        np.asarray(eastings), np.asarray(northings)
    )
    return postcodes, np.asarray(longitudes), np.asarray(latitudes)


def zone_shapes(collection: dict) -> dict[int, object]:
    return {
        int(feature["properties"]["minutes"]): shape(feature["geometry"])
        for feature in collection["features"]
    }


def minimum_minutes(
    zones: dict[int, object],
    longitudes: np.ndarray,
    latitudes: np.ndarray,
) -> np.ndarray:
    result = np.full(longitudes.shape, 99, dtype=np.int16)
    for minutes in WALK_MINUTES:
        inside = contains_xy(zones[minutes], longitudes, latitudes)
        result[(result == 99) & inside] = minutes
    return result


def build_postcode_pool_reach(
    provider: str,
    postcodes: np.ndarray,
    longitudes: np.ndarray,
    latitudes: np.ndarray,
    candidate_indexes: np.ndarray,
) -> None:
    cand_lons = longitudes[candidate_indexes]
    cand_lats = latitudes[candidate_indexes]
    cand_postcodes = [postcodes[int(index)] for index in candidate_indexes]

    venue_catalog: list[dict[str, str]] = []
    reach_by_postcode: dict[str, list[list[int]]] = {}

    for operator in POOL_OPERATORS:
        operator_path = PUBLIC_DATA / operator["file"]
        for feature in read_json(operator_path).get("features", []):
            point_id = str(feature.get("id") or feature["properties"]["id"])
            category = f"pool-{operator['id']}"
            contours = fetch_contours(
                category,
                point_id,
                feature["geometry"]["coordinates"],
                provider,
            )
            minutes_at_points = minimum_minutes(contours, cand_lons, cand_lats)

            venue_idx = len(venue_catalog)
            venue_catalog.append(
                {
                    "key": f'{operator["id"]}-{point_id}',
                    "name": feature["properties"]["name"],
                    "operator": operator["id"],
                    "operatorLabel": operator["label"],
                }
            )

            for index, minutes in enumerate(minutes_at_points):
                if minutes > WALK_MINUTES[-1]:
                    continue
                postcode = str(cand_postcodes[index])
                reach_by_postcode.setdefault(postcode, []).append(
                    [venue_idx, int(minutes)]
                )

    output = PUBLIC_DATA / "postcode-pool-reach.json"
    write_json(
        output,
        {"venues": venue_catalog, "byPostcode": reach_by_postcode},
        compact=True,
    )
    print(
        f"Wrote pool reach for {len(reach_by_postcode):,} postcodes "
        f"and {len(venue_catalog)} venues to {output.name}"
    )


def build_postcode_station_reach(
    provider: str,
    stations_path: Path,
    postcodes: np.ndarray,
    longitudes: np.ndarray,
    latitudes: np.ndarray,
    candidate_indexes: np.ndarray,
) -> None:
    cand_lons = longitudes[candidate_indexes]
    cand_lats = latitudes[candidate_indexes]
    cand_postcodes = [postcodes[int(index)] for index in candidate_indexes]

    station_catalog: list[dict[str, str]] = []
    reach_by_postcode: dict[str, list[list[int]]] = {}

    for feature in read_json(stations_path).get("features", []):
        point_id = str(feature.get("id") or feature["properties"]["id"])
        contours = fetch_contours(
            "station",
            point_id,
            feature["geometry"]["coordinates"],
            provider,
        )
        minutes_at_points = minimum_minutes(contours, cand_lons, cand_lats)

        station_idx = len(station_catalog)
        properties = feature["properties"]
        station_catalog.append(
            {
                "key": point_id,
                "name": properties["name"],
                "lines": properties.get("lines", ""),
            }
        )

        for index, minutes in enumerate(minutes_at_points):
            if minutes > WALK_MINUTES[-1]:
                continue
            postcode = str(cand_postcodes[index])
            reach_by_postcode.setdefault(postcode, []).append(
                [station_idx, int(minutes)]
            )

    output = PUBLIC_DATA / "postcode-station-reach.json"
    write_json(
        output,
        {"stations": station_catalog, "byPostcode": reach_by_postcode},
        compact=True,
    )
    print(
        f"Wrote station reach for {len(reach_by_postcode):,} postcodes "
        f"and {len(station_catalog)} stations to {output.name}"
    )


def main() -> None:
    ensure_directories()
    sales_path = PUBLIC_DATA / "district-sales.json"
    stations_path = PUBLIC_DATA / "night-stations.geojson"
    pool_paths = [PUBLIC_DATA / operator["file"] for operator in POOL_OPERATORS]
    venues_path = PUBLIC_DATA / "pool-gyms.geojson"
    for path in (sales_path, stations_path, *pool_paths, venues_path):
        if not path.exists():
            raise RuntimeError(f"Missing {path}; run the source importers first")

    sales = read_json(sales_path)
    relevant_districts = set(sales["districts"])
    postcodes, longitudes, latitudes = load_postcodes(
        download_code_point(), relevant_districts
    )
    print(f"Loaded {len(postcodes):,} London postcode points")

    provider = os.environ.get("ISOCHRONE_PROVIDER")
    if not provider:
        provider = "ors" if os.environ.get("ORS_API_KEY") else "valhalla"
    station_zones = zone_shapes(build_category(stations_path, "station", provider))
    pool_minutes_by_operator = {}
    for operator in POOL_OPERATORS:
        operator_path = PUBLIC_DATA / operator["file"]
        operator_features = read_json(operator_path).get("features", [])
        if not operator_features:
            print(f"Skipping {operator['label']}: no venues in {operator_path.name}")
            pool_minutes_by_operator[operator["id"]] = np.full(
                longitudes.shape,
                99,
                dtype=np.int8,
            )
            continue
        pool_zones = zone_shapes(
            build_category(operator_path, f"pool-{operator['id']}", provider)
        )
        pool_minutes_by_operator[operator["id"]] = minimum_minutes(
            pool_zones, longitudes, latitudes
        )

    station_minutes = minimum_minutes(station_zones, longitudes, latitudes)
    within_any_pool = np.zeros(longitudes.shape, dtype=bool)
    for operator_minutes in pool_minutes_by_operator.values():
        within_any_pool |= operator_minutes <= WALK_MINUTES[-1]
    eligible = (station_minutes <= WALK_MINUTES[-1]) & within_any_pool
    indexes = np.flatnonzero(eligible)

    fields = candidate_fields()
    points = []
    for index in indexes:
        postcode = postcodes[index]
        row = [
            postcode,
            round(float(longitudes[index]), 6),
            round(float(latitudes[index]), 6),
            int(station_minutes[index]),
        ]
        for operator in POOL_OPERATORS:
            row.append(int(pool_minutes_by_operator[operator["id"]][index]))
        points.append(row)

    candidates_path = PUBLIC_DATA / "postcode-candidates.json"
    write_json(
        candidates_path,
        {
            "fields": fields,
            "points": points,
        },
        compact=True,
    )
    build_postcode_pool_reach(provider, postcodes, longitudes, latitudes, indexes)
    build_postcode_station_reach(
        provider, stations_path, postcodes, longitudes, latitudes, indexes
    )
    reach_path = PUBLIC_DATA / "postcode-pool-reach.json"
    station_reach_path = PUBLIC_DATA / "postcode-station-reach.json"
    manifest = {
        "generated": datetime.now(UTC).isoformat(),
        "options": WALK_MINUTES,
        "defaults": {"station": 10, "pool": 15},
        "provider": provider,
        "poolOperators": POOL_OPERATORS,
        "counts": {"postcodes": len(points)},
        "files": {
            "candidates": candidates_path.name,
            "poolReach": reach_path.name,
            "stationReach": station_reach_path.name,
            "sales": sales_path.name,
            "stations": stations_path.name,
            "venues": venues_path.name,
        },
    }
    write_json(PUBLIC_DATA / "manifest.json", manifest)
    print(
        f"Wrote {len(points):,} eligible postcode points "
        f"({candidates_path.stat().st_size / 1024 / 1024:.1f} MiB)"
    )


if __name__ == "__main__":
    main()
