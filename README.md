# Otterholt

An interactive map of London postcode districts within walking distance of a
Night Tube station and a gym with a pool (all pool operators are on by
default), coloured by recent median flat sale price.

## Run locally

The web app is static and has no JavaScript build step:

```bash
python3 -m http.server 4173
```

Open [http://localhost:4173](http://localhost:4173).

## Regenerate the map data

Create the Python environment once:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then fetch current locations and sale statistics, classify postcode points,
and validate the output:

```bash
.venv/bin/python scripts/fetch_tfl.py
.venv/bin/python scripts/fetch_better.py
.venv/bin/python scripts/fetch_everyone_active.py
.venv/bin/python scripts/fetch_virgin_active.py
.venv/bin/python scripts/fetch_nuffield.py
.venv/bin/python scripts/fetch_active_lambeth.py
.venv/bin/python scripts/merge_pool_venues.py
.venv/bin/python scripts/fetch_market_data.py
.venv/bin/python scripts/build_candidates.py
.venv/bin/python scripts/validate_data.py
```

Downloads and contour responses are cached under `.cache/`, so interrupted or
repeated runs only request missing data. HM Land Registry downloads are subject
to its published Price Paid Data conditions.

## Data sources

- [TfL Unified API](https://tfl.gov.uk/info-for/open-data-users/api-documentation)
- [Better London venue directory](https://www.better.org.uk/leisure-centre/london)
- [Everyone Active centre directory](https://www.everyoneactive.com/centre/)
- [Virgin Active club finder](https://www.virginactive.co.uk/clubs)
- [Nuffield Health gyms in London](https://www.nuffieldhealth.com/gyms/gyms-in-london)
- [Active Lambeth](https://active.lambeth.gov.uk/)
- [HM Land Registry Price Paid Data](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads)
- [OS Code-Point Open](https://www.ordnancesurvey.co.uk/products/code-point-open)
- [Valhalla](https://valhalla.github.io/valhalla/) routing over OpenStreetMap

Walking contours are approximations. They can be affected by incomplete path data, access restrictions, temporary closures, and routing-provider updates.
Contains OS data © Crown copyright and database right 2026.
