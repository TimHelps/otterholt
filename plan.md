# Otterholt

## Product

A static London map for comparing postcode districts that contain locations
within selected walking times of both:

- Friday/Saturday night service on the Central, Jubilee, Northern, Piccadilly,
  Victoria or Windrush line; and
- a selected gym operator with both a gym and swimming pool.

The two walking-time dropdowns offer 5, 10, 15 and 20 minutes. Pool operators
can be toggled independently; a postcode qualifies when it is within the
selected pool walk of at least one enabled operator and within the selected
Night Tube walk. District markers are coloured by recent median flat or
maisonette sale price.

## Data

Pedestrian isochrones are generated at build time. OS Code-Point Open postcode
centroids inside both 20-minute coverages store their smallest station and pool
walking-time bands. The browser filters those locations and groups them into
one marker per postcode district.

HM Land Registry Price Paid Data is filtered to standard flat or maisonette
sales from 2025 onward and aggregated by postcode district. Districts with
fewer than ten sales are omitted.

## Architecture

- Static HTML, CSS and JavaScript with MapLibre GL JS and OpenFreeMap
- Generated browser data under `data/`
- Python data pipeline under `scripts/`
- No backend, database or browser API keys
