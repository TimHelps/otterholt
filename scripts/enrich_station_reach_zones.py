#!/usr/bin/env python3
from __future__ import annotations

from common import PUBLIC_DATA, parse_tfl_zone_max, read_json, write_json


def main() -> None:
    stations_path = PUBLIC_DATA / "night-stations.geojson"
    reach_path = PUBLIC_DATA / "postcode-station-reach.json"
    stations_geo = read_json(stations_path)
    zone_by_key = {
        str(feature.get("id") or feature["properties"]["id"]): feature["properties"]
        for feature in stations_geo.get("features", [])
    }

    reach = read_json(reach_path)
    updated = 0
    for station in reach.get("stations", []):
        properties = zone_by_key.get(station["key"], {})
        zone = str(properties.get("zone", ""))
        if not zone:
            raise RuntimeError(f"Station {station['key']} is missing a fare zone in {stations_path.name}")
        station["zone"] = zone
        station["zoneMax"] = int(properties.get("zoneMax", parse_tfl_zone_max(zone)))
        updated += 1

    write_json(reach_path, reach, compact=True)
    print(f"Updated fare zones for {updated} stations in {reach_path.name}")


if __name__ == "__main__":
    main()
