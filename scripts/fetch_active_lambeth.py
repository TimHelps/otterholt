#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import time

from common import (
    PUBLIC_DATA,
    ensure_directories,
    feature_collection,
    geocode_postcode,
    request_json,
    request_text,
    write_json,
)
from pool_operators import LONDON_BOUNDS

LISTING_URL = "https://active.lambeth.gov.uk/"
API_URL = "https://active.lambeth.gov.uk/wp-json/wp/v2/locations?per_page=50"


def text_content(markup: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", markup)
    return " ".join(html.unescape(without_tags).split())


def has_gym_and_pool(page: str) -> bool:
    lower = page.lower()
    has_gym = "gym" in lower
    has_pool = any(
        phrase in lower
        for phrase in ("swimming pool", "swim", "pool")
    )
    return has_gym and has_pool


def parse_location(link: str, slug: str, title: str) -> dict | None:
    page = request_text(link)
    if not has_gym_and_pool(page):
        return None

    postcode_match = re.search(
        r"London,?\s*([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})",
        page,
    )
    if not postcode_match:
        return None

    lat, lon = geocode_postcode(postcode_match.group(1))
    if not (
        LONDON_BOUNDS["min_lat"] <= lat <= LONDON_BOUNDS["max_lat"]
        and LONDON_BOUNDS["min_lon"] <= lon <= LONDON_BOUNDS["max_lon"]
    ):
        return None

    return {
        "id": slug,
        "name": text_content(title),
        "address": f"London, {postcode_match.group(1)}",
        "url": link,
        "latitude": lat,
        "longitude": lon,
    }


def main() -> None:
    ensure_directories()
    features = []
    failures = []

    locations = request_json(API_URL)
    for index, location in enumerate(locations, start=1):
        slug = location.get("slug", "")
        link = location.get("link", "").rstrip("/") + "/"
        title = location.get("title", {}).get("rendered", slug)
        try:
            centre = parse_location(link, slug, title)
        except Exception as error:  # noqa: BLE001 - collect scrape failures
            failures.append(f"{slug}: {error}")
            continue
        if not centre:
            continue

        features.append(
            {
                "type": "Feature",
                "id": centre["id"],
                "properties": {
                    "id": centre["id"],
                    "name": centre["name"],
                    "address": centre["address"],
                    "url": centre["url"],
                    "operator": "active-lambeth",
                    "operatorLabel": "Active Lambeth",
                    "hasGym": True,
                    "hasPool": True,
                    "source": LISTING_URL,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [centre["longitude"], centre["latitude"]],
                },
            }
        )
        time.sleep(0.05)

    if failures:
        raise RuntimeError(
            "Active Lambeth scrape failures:\n- " + "\n- ".join(failures[:10])
        )
    if len(features) < 3:
        raise RuntimeError(
            f"Only found {len(features)} Active Lambeth centres with gym and pool"
        )

    features.sort(key=lambda feature: feature["properties"]["name"])
    output = PUBLIC_DATA / "active-lambeth-pool-gyms.geojson"
    write_json(output, feature_collection(features))
    print(
        f"Wrote {len(features)} Active Lambeth centres to "
        f"{output.relative_to(output.parent.parent)}"
    )


if __name__ == "__main__":
    main()
