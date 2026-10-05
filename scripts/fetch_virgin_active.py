#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET

from common import (
    PUBLIC_DATA,
    ensure_directories,
    feature_collection,
    geocode_postcode,
    request_text,
    write_json,
)
from pool_operators import LONDON_BOUNDS

SITEMAP_URL = "https://www.virginactive.co.uk/sitemap.xml"
BASE_URL = "https://www.virginactive.co.uk"


def text_content(markup: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", markup)
    return " ".join(html.unescape(without_tags).split())


def list_club_slugs() -> list[str]:
    root = ET.fromstring(request_text(SITEMAP_URL))
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    slugs = set()
    for location in root.findall("sm:url/sm:loc", namespace):
        match = re.match(r"https://www\.virginactive\.co\.uk/clubs/([a-z0-9-]+)$", location.text or "")
        if match:
            slugs.add(match.group(1))
    return sorted(slugs)


def has_gym_and_pool(page: str) -> bool:
    lower = page.lower()
    has_gym = "gym" in lower
    has_pool = any(word in lower for word in ("swimming pool", "swim", "pool"))
    return has_gym and has_pool


def parse_club(slug: str) -> dict | None:
    url = f"{BASE_URL}/clubs/{slug}"
    page = request_text(url)
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

    title_match = re.search(r"<title>(.*?)</title>", page, flags=re.DOTALL)
    title = text_content(title_match.group(1)) if title_match else slug
    name = title.split("|", 1)[0].strip()

    return {
        "id": slug,
        "name": name,
        "address": f"London, {postcode_match.group(1)}",
        "url": url,
        "latitude": lat,
        "longitude": lon,
    }


def main() -> None:
    ensure_directories()
    features = []
    failures = []

    for index, slug in enumerate(list_club_slugs(), start=1):
        try:
            club = parse_club(slug)
        except Exception as error:  # noqa: BLE001 - collect scrape failures
            failures.append(f"{slug}: {error}")
            continue
        if not club:
            continue

        features.append(
            {
                "type": "Feature",
                "id": club["id"],
                "properties": {
                    "id": club["id"],
                    "name": club["name"],
                    "address": club["address"],
                    "url": club["url"],
                    "operator": "virgin-active",
                    "operatorLabel": "Virgin Active",
                    "hasGym": True,
                    "hasPool": True,
                    "source": SITEMAP_URL,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [club["longitude"], club["latitude"]],
                },
            }
        )
        time.sleep(0.08)
        if index % 10 == 0:
            print(f"Checked {index} clubs…")

    if failures:
        raise RuntimeError(
            "Virgin Active scrape failures:\n- " + "\n- ".join(failures[:10])
        )
    if len(features) < 5:
        raise RuntimeError(
            f"Only found {len(features)} Virgin Active clubs with pools in London"
        )

    features.sort(key=lambda feature: feature["properties"]["name"])
    output = PUBLIC_DATA / "virgin-active-pool-gyms.geojson"
    write_json(output, feature_collection(features))
    print(
        f"Wrote {len(features)} Virgin Active clubs with pools to "
        f"{output.relative_to(output.parent.parent)}"
    )


if __name__ == "__main__":
    main()
