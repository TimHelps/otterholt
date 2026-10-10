#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict

from common import (
    PUBLIC_DATA,
    ensure_directories,
    feature_collection,
    parse_tfl_zone_max,
    request_json,
    write_json,
)
from enrich_station_reach_zones import main as enrich_station_reach_zones
from tfl_zones import build_zone_lookup, resolve_station_zone

LINES = {
    "central": "Central",
    "jubilee": "Jubilee",
    "northern": "Northern",
    "piccadilly": "Piccadilly",
    "victoria": "Victoria",
    "windrush": "Windrush",
}
SEQUENCE_URL = (
    "https://api.tfl.gov.uk/Line/{line}/Route/Sequence/outbound?serviceTypes=Night"
)


def main() -> None:
    ensure_directories()
    stations: dict[str, dict] = {}
    station_lines: defaultdict[str, set[str]] = defaultdict(set)

    for line_id, line_name in LINES.items():
        data = request_json(SEQUENCE_URL.format(line=line_id))
        sequences = [
            sequence
            for sequence in data.get("stopPointSequences", [])
            if sequence.get("serviceType") == "Night"
        ]
        if not sequences:
            raise RuntimeError(f"TfL returned no night sequences for {line_name}")

        for sequence in sequences:
            for stop in sequence.get("stopPoint", []):
                station_id = stop["id"]
                station_lines[station_id].add(line_name)
                stations[station_id] = {
                    "id": station_id,
                    "name": stop["name"],
                    "lat": float(stop["lat"]),
                    "lon": float(stop["lon"]),
                }

    zones_by_id, zones_by_name = build_zone_lookup(list(LINES))
    print(
        f"Loaded fare zones for {len(zones_by_id)} TfL stops "
        f"from {len(LINES)} line StopPoint feeds"
    )

    features = []
    for station in sorted(stations.values(), key=lambda value: value["name"]):
        if not (51.2 <= station["lat"] <= 51.8 and -0.7 <= station["lon"] <= 0.4):
            raise RuntimeError(f"Station outside London bounds: {station}")
        zone = resolve_station_zone(station, zones_by_id, zones_by_name, stations)
        features.append(
            {
                "type": "Feature",
                "id": station["id"],
                "properties": {
                    "id": station["id"],
                    "name": station["name"],
                    "lines": ", ".join(sorted(station_lines[station["id"]])),
                    "zone": zone,
                    "zoneMax": parse_tfl_zone_max(zone),
                    "source": "TfL Unified API",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [station["lon"], station["lat"]],
                },
            }
        )

    output = PUBLIC_DATA / "night-stations.geojson"
    write_json(output, feature_collection(features))
    print(f"Wrote {len(features)} night-service stations to {output.relative_to(output.parent.parent)}")

    reach_path = PUBLIC_DATA / "postcode-station-reach.json"
    if reach_path.exists():
        enrich_station_reach_zones()


if __name__ == "__main__":
    main()
