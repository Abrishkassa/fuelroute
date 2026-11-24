# Fuel Route API (Django 6.1)

Day 1 status: data pipeline, models, routing client, tests. API endpoint + fuel algorithm come next.

## Quick start
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# optional Postgres: docker compose up -d, then
# export POSTGRES_DB=fuelroute POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres
python manage.py migrate
python manage.py load_stations      # cleans CSV, downloads cities dataset, loads stations
python manage.py test
```

## Data decisions
- Non-US rows (Canadian provinces) dropped: 620 rows.
- Duplicate OPIS IDs: keep the cheapest row (the CSV has no timestamp): 905 dropped, 6,626 stations kept.
- The CSV has no coordinates and its addresses are highway exits, so stations get city-level
  coordinates from a free US cities dataset (matched on city + state, no per-request geocoding).
  Six unmatched cities use hand-set approximate centroids.

## Routing
One call per request to an OSRM-compatible endpoint (`ROUTING_URL`, public demo server by default).
