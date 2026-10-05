#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict

from common import PUBLIC_DATA, ensure_directories, feature_collection, request_json, write_json

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

    features = []
    for station in sorted(stations.values(), key=lambda value: value["name"]):
        if not (51.2 <= station["lat"] <= 51.8 and -0.7 <= station["lon"] <= 0.4):
            raise RuntimeError(f"Station outside London bounds: {station}")
        features.append(
            {
                "type": "Feature",
                "id": station["id"],
                "properties": {
                    "id": station["id"],
                    "name": station["name"],
                    "lines": ", ".join(sorted(station_lines[station["id"]])),
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


if __name__ == "__main__":
    main()
