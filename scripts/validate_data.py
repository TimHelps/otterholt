#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from common import PUBLIC_DATA, WALK_MINUTES, read_json
from pool_operators import candidate_fields

EXPECTED_FILES = [
    "manifest.json",
    "night-stations.geojson",
    "better-pool-gyms.geojson",
    "everyone-active-pool-gyms.geojson",
    "virgin-active-pool-gyms.geojson",
    "nuffield-pool-gyms.geojson",
    "active-lambeth-pool-gyms.geojson",
    "pool-gyms.geojson",
    "district-sales.json",
    "postcode-candidates.json",
    "postcode-pool-reach.json",
    "postcode-station-reach.json",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_points(path: Path, minimum: int, kind: str) -> None:
    data = read_json(path)
    features = data.get("features", [])
    require(len(features) >= minimum, f"Too few {kind}: {len(features)}")
    ids = [
        str(feature.get("id") or feature["properties"]["id"]) for feature in features
    ]
    require(len(ids) == len(set(ids)), f"Duplicate {kind} IDs")

    for feature in features:
        require(feature["geometry"]["type"] == "Point", f"Non-point {kind} feature")
        lon, lat = feature["geometry"]["coordinates"]
        require(
            51.2 <= lat <= 51.8 and -0.7 <= lon <= 0.4,
            f"{kind} outside London bounds: {feature['properties']['name']}",
        )


def validate_candidates(path: Path, districts: dict, fields: list[str]) -> None:
    data = read_json(path)
    points = data.get("points", [])
    require(data.get("fields") == fields, "Candidate fields do not match manifest")
    require(len(points) >= 10_000, f"Too few postcode candidates: {len(points)}")
    postcodes = [point[0] for point in points]
    require(len(postcodes) == len(set(postcodes)), "Duplicate candidate postcodes")
    station_index = fields.index("stationMin")
    pool_fields = [field for field in fields if field.endswith("PoolMin")]
    for point in points:
        postcode = point[0]
        lon = point[1]
        lat = point[2]
        station_minutes = point[station_index]
        district = postcode.split(" ", 1)[0]
        require(district in districts, "Candidate has no price district")
        require(station_minutes in WALK_MINUTES, "Invalid station time")
        for pool_field in pool_fields:
            pool_minutes = point[fields.index(pool_field)]
            require(pool_minutes in WALK_MINUTES or pool_minutes == 99, "Invalid pool time")
        require(51.2 <= lat <= 51.8 and -0.7 <= lon <= 0.4, "Candidate outside London")


def main() -> None:
    for filename in EXPECTED_FILES:
        require((PUBLIC_DATA / filename).exists(), f"Missing data/{filename}")

    manifest = read_json(PUBLIC_DATA / "manifest.json")
    require(manifest.get("options") == WALK_MINUTES, "Manifest options are incorrect")
    validate_points(PUBLIC_DATA / "night-stations.geojson", 100, "stations")
    validate_points(PUBLIC_DATA / "better-pool-gyms.geojson", 40, "better venues")
    validate_points(PUBLIC_DATA / "everyone-active-pool-gyms.geojson", 5, "everyone active venues")
    validate_points(PUBLIC_DATA / "virgin-active-pool-gyms.geojson", 5, "virgin active venues")
    validate_points(PUBLIC_DATA / "nuffield-pool-gyms.geojson", 5, "nuffield venues")
    validate_points(PUBLIC_DATA / "active-lambeth-pool-gyms.geojson", 3, "active lambeth venues")
    validate_points(PUBLIC_DATA / "pool-gyms.geojson", 45, "pool venues")
    sales = read_json(PUBLIC_DATA / "district-sales.json")
    districts = sales.get("districts", {})
    require(len(districts) >= 100, f"Too few sale-price districts: {len(districts)}")
    require(
        sum(bool(value.get("flatSaleMedian")) for value in districts.values()) >= 100,
        "Too few sale-price districts",
    )
    require(
        all(value.get("saleSamples", 0) >= 10 for value in districts.values()),
        "Sale-price district has too few samples",
    )
    require(manifest.get("poolOperators"), "Manifest is missing pool operators")
    fields = read_json(PUBLIC_DATA / "postcode-candidates.json").get("fields", [])
    require(fields == candidate_fields(), "Candidate fields are incorrect")
    validate_candidates(PUBLIC_DATA / "postcode-candidates.json", districts, fields)
    pool_reach = read_json(PUBLIC_DATA / "postcode-pool-reach.json")
    require(pool_reach.get("venues"), "Pool reach is missing venue catalog")
    require(pool_reach.get("byPostcode"), "Pool reach is missing postcode index")
    station_reach = read_json(PUBLIC_DATA / "postcode-station-reach.json")
    require(station_reach.get("stations"), "Station reach is missing station catalog")
    require(station_reach.get("byPostcode"), "Station reach is missing postcode index")
    require(
        (PUBLIC_DATA / "postcode-candidates.json").stat().st_size < 4_000_000,
        "Candidate file exceeds 4 MB",
    )

    for filename in EXPECTED_FILES:
        path = PUBLIC_DATA / filename
        print(f"{filename}: {path.stat().st_size / 1024:.1f} KiB")
    print("All data checks passed")


if __name__ == "__main__":
    main()
