from __future__ import annotations

POOL_OPERATORS = [
    {
        "id": "better",
        "label": "Better",
        "file": "better-pool-gyms.geojson",
        "field": "betterPoolMin",
        "default": True,
    },
    {
        "id": "everyone-active",
        "label": "Everyone Active",
        "file": "everyone-active-pool-gyms.geojson",
        "field": "everyoneActivePoolMin",
        "default": True,
    },
    {
        "id": "virgin-active",
        "label": "Virgin Active",
        "file": "virgin-active-pool-gyms.geojson",
        "field": "virginActivePoolMin",
        "default": True,
    },
    {
        "id": "nuffield",
        "label": "Nuffield",
        "file": "nuffield-pool-gyms.geojson",
        "field": "nuffieldPoolMin",
        "default": True,
    },
    {
        "id": "active-lambeth",
        "label": "Active Lambeth",
        "file": "active-lambeth-pool-gyms.geojson",
        "field": "activeLambethPoolMin",
        "default": True,
    },
]

LONDON_BOUNDS = {
    "min_lat": 51.2,
    "max_lat": 51.8,
    "min_lon": -0.7,
    "max_lon": 0.4,
}


def candidate_fields() -> list[str]:
    return ["postcode", "longitude", "latitude", "stationMin"] + [
        operator["field"] for operator in POOL_OPERATORS
    ]
