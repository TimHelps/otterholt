#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import time
from urllib.parse import urljoin

from common import PUBLIC_DATA, ensure_directories, feature_collection, request_text, write_json
from pool_operators import LONDON_BOUNDS

LISTING_URL = "https://www.nuffieldhealth.com/gyms/gyms-in-london"
BASE_URL = "https://www.nuffieldhealth.com"


def text_content(markup: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", markup)
    return " ".join(html.unescape(without_tags).split())


def list_gym_paths() -> list[str]:
    page = request_text(LISTING_URL)
    paths = {
        match
        for match in re.findall(r'href="(/gyms/[a-z0-9-]+)"', page)
        if match not in {"/gyms/gyms-in-london", "/gyms/membership"}
    }
    return sorted(paths)


def has_gym_and_pool(page: str) -> bool:
    lower = page.lower()
    has_gym = "gym" in lower
    has_pool = any(word in lower for word in ("swimming pool", "swim", "pool"))
    return has_gym and has_pool


def parse_gym(path: str) -> dict | None:
    url = urljoin(BASE_URL, path)
    page = request_text(url)
    if not has_gym_and_pool(page):
        return None

    lat_match = re.search(r'"latitude":\s*"([-\d.]+)"', page)
    lon_match = re.search(r'"longitude":\s*"([-\d.]+)"', page)
    if not lat_match or not lon_match:
        return None

    lat = float(lat_match.group(1))
    lon = float(lon_match.group(1))
    if not (
        LONDON_BOUNDS["min_lat"] <= lat <= LONDON_BOUNDS["max_lat"]
        and LONDON_BOUNDS["min_lon"] <= lon <= LONDON_BOUNDS["max_lon"]
    ):
        return None

    title_match = re.search(r"<title>(.*?)</title>", page, flags=re.DOTALL)
    title = text_content(title_match.group(1)) if title_match else path
    name = title.split("|", 1)[0].strip()

    slug = path.rstrip("/").rsplit("/", 1)[-1]
    return {
        "id": slug,
        "name": name,
        "address": "",
        "url": url,
        "latitude": lat,
        "longitude": lon,
    }


def main() -> None:
    ensure_directories()
    features = []
    failures = []

    for index, path in enumerate(list_gym_paths(), start=1):
        try:
            gym = parse_gym(path)
        except Exception as error:  # noqa: BLE001 - collect scrape failures
            failures.append(f"{path}: {error}")
            continue
        if not gym:
            continue

        features.append(
            {
                "type": "Feature",
                "id": gym["id"],
                "properties": {
                    "id": gym["id"],
                    "name": gym["name"],
                    "address": gym["address"],
                    "url": gym["url"],
                    "operator": "nuffield",
                    "operatorLabel": "Nuffield",
                    "hasGym": True,
                    "hasPool": True,
                    "source": LISTING_URL,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [gym["longitude"], gym["latitude"]],
                },
            }
        )
        time.sleep(0.05)
        if index % 20 == 0:
            print(f"Checked {index} gyms…")

    if failures:
        raise RuntimeError(
            "Nuffield scrape failures:\n- " + "\n- ".join(failures[:10])
        )
    if len(features) < 5:
        raise RuntimeError(
            f"Only found {len(features)} Nuffield gyms with pools in London"
        )

    features.sort(key=lambda feature: feature["properties"]["name"])
    output = PUBLIC_DATA / "nuffield-pool-gyms.geojson"
    write_json(output, feature_collection(features))
    print(
        f"Wrote {len(features)} Nuffield gyms with pools to "
        f"{output.relative_to(output.parent.parent)}"
    )


if __name__ == "__main__":
    main()
