#!/usr/bin/env python3
from __future__ import annotations

import math
import re
from typing import Any

from common import request_json

LINE_STOP_URL = "https://api.tfl.gov.uk/Line/{line}/StopPoints"


def normalise_tfl_station_name(name: str) -> str:
    cleaned = name.lower()
    cleaned = cleaned.replace("underground station", "")
    cleaned = cleaned.replace(" rail station", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned


def tfl_stop_zone(stop: dict[str, Any]) -> str | None:
    for prop in stop.get("additionalProperties", []):
        if prop.get("category") == "Geo" and prop.get("key") == "Zone":
            return str(prop["value"])
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_zone_lookup(line_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    zones_by_id: dict[str, str] = {}
    zones_by_name: dict[str, str] = {}

    for line_id in line_ids:
        stops = request_json(LINE_STOP_URL.format(line=line_id))
        if not isinstance(stops, list):
            raise RuntimeError(f"TfL returned unexpected StopPoints payload for line {line_id}")

        for stop in stops:
            zone = tfl_stop_zone(stop)
            if not zone:
                continue
            stop_id = str(stop.get("id") or stop.get("naptanId") or "")
            if stop_id:
                zones_by_id.setdefault(stop_id, zone)
            name = normalise_tfl_station_name(str(stop.get("commonName") or stop.get("name") or ""))
            if name:
                zones_by_name.setdefault(name, zone)

    return zones_by_id, zones_by_name


def resolve_station_zone(
    station: dict[str, Any],
    zones_by_id: dict[str, str],
    zones_by_name: dict[str, str],
    night_stations: dict[str, dict[str, Any]],
) -> str:
    station_id = station["id"]
    if station_id in zones_by_id:
        return zones_by_id[station_id]

    normalised = normalise_tfl_station_name(station["name"])
    if normalised in zones_by_name:
        return zones_by_name[normalised]

    best_zone = None
    best_km = float("inf")
    for zoned_id, zone in zones_by_id.items():
        other = night_stations.get(zoned_id)
        if not other:
            continue
        km = haversine_km(station["lat"], station["lon"], other["lat"], other["lon"])
        if km < best_km:
            best_km = km
            best_zone = zone

    if best_zone is not None and best_km <= 2.5:
        return best_zone

    raise RuntimeError(
        f"Could not resolve fare zone for {station_id} ({station['name']}); "
        f"nearest zoned stop was {best_km:.2f} km away"
    )
