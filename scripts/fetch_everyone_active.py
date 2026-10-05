#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import time
from urllib.parse import urljoin

from common import PUBLIC_DATA, ensure_directories, feature_collection, request_text, write_json
from pool_operators import LONDON_BOUNDS

LISTING_URL = "https://www.everyoneactive.com/centre/"
BASE_URL = "https://www.everyoneactive.com"


def text_content(markup: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", markup)
    return " ".join(html.unescape(without_tags).split())


def list_centre_urls() -> list[str]:
    page_html = request_text(LISTING_URL)
    urls = {
        match
        for match in re.findall(
            r"https://www\.everyoneactive\.com/centre/[a-z0-9-]+/",
            page_html,
        )
        if "/page/" not in match
    }
    return sorted(urls)


def has_gym_and_pool(page: str) -> bool:
    lower = page.lower()
    has_gym = "gym" in lower
    has_pool = any(word in lower for word in ("swimming pool", "swim", "lido"))
    return has_gym and has_pool


def parse_centre(url: str) -> dict | None:
    page = request_text(url)
    if not has_gym_and_pool(page):
        return None

    maps_match = re.search(
        r"google\.co\.uk/maps/place/([-\d.]+),([-\d.]+)",
        page,
    )
    if not maps_match:
        return None

    lat = float(maps_match.group(1))
    lon = float(maps_match.group(2))
    if not (
        LONDON_BOUNDS["min_lat"] <= lat <= LONDON_BOUNDS["max_lat"]
        and LONDON_BOUNDS["min_lon"] <= lon <= LONDON_BOUNDS["max_lon"]
    ):
        return None

    title_match = re.search(r"<title>(.*?)</title>", page, flags=re.DOTALL)
    title = text_content(title_match.group(1)) if title_match else url
    name = title.split("|", 1)[0].strip()

    address_match = re.search(
        r'itemprop="address"[^>]*>(.*?)</[^>]+>',
        page,
        flags=re.DOTALL,
    )
    address = text_content(address_match.group(1)) if address_match else ""

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return {
        "id": slug,
        "name": name,
        "address": address,
        "url": url,
        "latitude": lat,
        "longitude": lon,
    }


def main() -> None:
    ensure_directories()
    features = []
    failures = []

    for index, url in enumerate(list_centre_urls(), start=1):
        try:
            centre = parse_centre(url)
        except Exception as error:  # noqa: BLE001 - collect scrape failures
            failures.append(f"{url}: {error}")
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
                    "operator": "everyone-active",
                    "operatorLabel": "Everyone Active",
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
        if index % 25 == 0:
            print(f"Checked {index} centres…")

    if failures:
        raise RuntimeError(
            "Everyone Active scrape failures:\n- " + "\n- ".join(failures[:10])
        )
    if len(features) < 5:
        raise RuntimeError(
            f"Only found {len(features)} Everyone Active gyms with pools in London"
        )

    features.sort(key=lambda feature: feature["properties"]["name"])
    output = PUBLIC_DATA / "everyone-active-pool-gyms.geojson"
    write_json(output, feature_collection(features))
    print(
        f"Wrote {len(features)} Everyone Active gyms with pools to "
        f"{output.relative_to(output.parent.parent)}"
    )


if __name__ == "__main__":
    main()
