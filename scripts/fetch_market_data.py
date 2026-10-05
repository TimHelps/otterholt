#!/usr/bin/env python3
from __future__ import annotations

import csv
import statistics
import urllib.request
from collections import defaultdict
from pathlib import Path

from common import CACHE, PUBLIC_DATA, USER_AGENT, ensure_directories, write_json

LAND_REGISTRY_URL = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/"
    "pp-{year}.csv"
)
SALE_YEARS = [2025, 2026]
MINIMUM_SALES = 10
LONDON_POSTCODE_AREAS = {
    "BR",
    "CR",
    "DA",
    "E",
    "EC",
    "EN",
    "HA",
    "IG",
    "KT",
    "N",
    "NW",
    "RM",
    "SE",
    "SM",
    "SW",
    "TW",
    "UB",
    "W",
    "WC",
    "WD",
}


def download(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    print(f"Downloading {destination.name}…")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
        "wb"
    ) as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(destination)
    return destination


def postcode_area(district: str) -> str:
    for index, character in enumerate(district):
        if not character.isalpha():
            return district[:index]
    return district


def read_sales(paths: list[Path]) -> tuple[dict, str, str]:
    transactions = {}
    minimum_date = None
    maximum_date = None

    for path in paths:
        print(f"Reading {path.name}…")
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.reader(source):
                if len(row) < 16:
                    continue
                transaction_id = row[0]
                postcode = row[3].strip().upper()
                district = postcode.split(" ", 1)[0] if postcode else ""
                if (
                    postcode_area(district) not in LONDON_POSTCODE_AREAS
                    or row[4] != "F"
                    or row[14] != "A"
                ):
                    continue

                if row[15] == "D":
                    transactions.pop(transaction_id, None)
                    continue

                date = row[2][:10]
                transactions[transaction_id] = {
                    "district": district,
                    "price": int(row[1]),
                    "date": date,
                }
                minimum_date = date if minimum_date is None else min(minimum_date, date)
                maximum_date = date if maximum_date is None else max(maximum_date, date)

    prices: defaultdict[str, list[int]] = defaultdict(list)
    for transaction in transactions.values():
        prices[transaction["district"]].append(transaction["price"])

    summaries = {}
    for district, values in prices.items():
        if len(values) < MINIMUM_SALES:
            continue
        values.sort()
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        summaries[district] = {
            "flatSaleMedian": round(statistics.median(values)),
            "flatSaleLower": round(quartiles[0]),
            "flatSaleUpper": round(quartiles[2]),
            "saleSamples": len(values),
        }
    return summaries, minimum_date or "", maximum_date or ""


def main() -> None:
    ensure_directories()
    source_directory = CACHE / "sources"
    sale_paths = [
        download(
            LAND_REGISTRY_URL.format(year=year),
            source_directory / f"land-registry-{year}.csv",
        )
        for year in SALE_YEARS
    ]

    districts, sale_start, sale_end = read_sales(sale_paths)
    output = {
        "meta": {
            "salePeriod": f"{sale_start} to {sale_end}",
            "salePropertyType": "Flat/maisonette",
            "saleCategory": "Standard Price Paid Data category A",
            "saleSource": "HM Land Registry Price Paid Data",
        },
        "districts": districts,
    }
    write_json(PUBLIC_DATA / "district-sales.json", output, compact=True)
    print(f"Wrote {len(districts)} postcode districts with recent flat sales")


if __name__ == "__main__":
    main()
