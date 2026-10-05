#!/usr/bin/env python3
from __future__ import annotations

from common import PUBLIC_DATA, ensure_directories, feature_collection, read_json, write_json
from pool_operators import POOL_OPERATORS


def main() -> None:
    ensure_directories()
    features = []

    for operator in POOL_OPERATORS:
        path = PUBLIC_DATA / operator["file"]
        if not path.exists():
            raise RuntimeError(f"Missing {path}; run the operator fetch scripts first")

        for feature in read_json(path).get("features", []):
            properties = dict(feature.get("properties", {}))
            properties["operator"] = operator["id"]
            properties["operatorLabel"] = operator["label"]
            features.append(
                {
                    "type": "Feature",
                    "id": f'{operator["id"]}-{properties.get("id", feature.get("id"))}',
                    "properties": properties,
                    "geometry": feature["geometry"],
                }
            )

    if not features:
        raise RuntimeError("No pool venues to merge")

    output = PUBLIC_DATA / "pool-gyms.geojson"
    features.sort(key=lambda feature: feature["properties"]["name"])
    write_json(output, feature_collection(features))
    print(f"Wrote {len(features)} pool venues to {output.relative_to(output.parent.parent)}")


if __name__ == "__main__":
    main()
