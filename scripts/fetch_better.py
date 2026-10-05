#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from urllib.parse import urljoin

from common import PUBLIC_DATA, ensure_directories, feature_collection, request_text, write_json

DIRECTORY_URL = "https://www.better.org.uk/leisure-centre/london"
BASE_URL = "https://www.better.org.uk"


def text_content(markup: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", markup)
    return " ".join(html.unescape(without_tags).split())


def parse_map_pins(page: str) -> dict[str, dict]:
    match = re.search(r'<div id="google-map"[^>]*data-map="([^"]+)', page)
    if not match:
        raise RuntimeError("Could not find Better map data")
    map_data = json.loads(html.unescape(match.group(1)))

    pins = {}
    for pin in map_data.get("pins", []):
        paths = re.findall(r'href="([^"]+)"', pin.get("infowindow", ""))
        path = next(
            (
                value
                for value in paths
                if value.startswith("/leisure-centre/london/")
                and not value.endswith("/facilities")
            ),
            None,
        )
        if path:
            pins[path.rstrip("/")] = pin
    return pins


def parse_cards(page: str) -> list[dict]:
    cards = re.findall(
        r'<article class="venue-card panel">(.*?)</article>',
        page,
        flags=re.DOTALL,
    )
    venues = []

    for card in cards:
        heading = re.search(
            r'<h4[^>]*>\s*<a href="([^"]+)">(.*?)</a>',
            card,
            flags=re.DOTALL,
        )
        if not heading:
            continue

        path = html.unescape(heading.group(1)).rstrip("/")
        name = text_content(heading.group(2))
        facilities = [
            text_content(value)
            for value in re.findall(
                r'<span class="icon-text">(.*?)</span>',
                card,
                flags=re.DOTALL,
            )
        ]
        activity_block = re.search(
            r'<div class="live-facilities">(.*?)</div>',
            card,
            flags=re.DOTALL,
        )
        activities = (
            [
                text_content(value)
                for value in re.findall(
                    r"<a[^>]*>(.*?)</a>",
                    activity_block.group(1),
                    flags=re.DOTALL,
                )
            ]
            if activity_block
            else []
        )
        address_block = re.search(
            r'<div class="address">(.*?)</div>',
            card,
            flags=re.DOTALL,
        )
        address = text_content(address_block.group(1)) if address_block else ""

        advertised = " | ".join([*facilities, *activities]).lower()
        has_pool = any(word in advertised for word in ("pool", "swim", "lido"))
        has_gym = "gym" in advertised
        if has_pool and has_gym:
            venues.append(
                {
                    "name": name,
                    "path": path,
                    "url": urljoin(BASE_URL, path),
                    "address": address,
                    "facilities": facilities,
                    "activities": activities,
                }
            )
    return venues


def main() -> None:
    ensure_directories()
    page = request_text(DIRECTORY_URL)
    pins = parse_map_pins(page)
    venues = parse_cards(page)
    features = []
    unmatched = []

    for venue in venues:
        pin = pins.get(venue["path"])
        if not pin:
            unmatched.append(f'{venue["name"]} ({venue["path"]})')
            continue
        lat = float(pin["lat"])
        lon = float(pin["lng"])
        if not (51.2 <= lat <= 51.8 and -0.7 <= lon <= 0.4):
            raise RuntimeError(f"Venue outside London bounds: {venue['name']}")

        features.append(
            {
                "type": "Feature",
                "id": str(pin["id"]),
                "properties": {
                    "id": str(pin["id"]),
                    "name": venue["name"],
                    "address": venue["address"],
                    "url": venue["url"],
                    "operator": "better",
                    "operatorLabel": "Better",
                    "hasGym": True,
                    "hasPool": True,
                    "facilities": ", ".join(venue["facilities"]),
                    "source": DIRECTORY_URL,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
            }
        )

    if unmatched:
        raise RuntimeError("Better venues missing map coordinates:\n- " + "\n- ".join(unmatched))
    if len(features) < 40:
        raise RuntimeError(
            f"Only found {len(features)} Better gyms with pools; the source format may have changed"
        )

    features.sort(key=lambda feature: feature["properties"]["name"])
    output = PUBLIC_DATA / "better-pool-gyms.geojson"
    write_json(output, feature_collection(features))
    print(f"Wrote {len(features)} Better gyms with pools to {output.relative_to(output.parent.parent)}")


if __name__ == "__main__":
    main()
