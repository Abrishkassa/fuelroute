# Fuel Route API (Django 6.1)

Given a start and finish in the USA, returns the driving route (GeoJSON), the cost-optimal fuel stops
(500-mile range) and the total fuel cost at 10 mpg. Day 3 adds the Leaflet map page.

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

## API
`GET /api/route/?start=Dallas, TX&finish=Atlanta, GA` (also accepts `lat,lng`).
Optional: `start_fuel_miles` (0-500, default 500), `corridor_miles` (default 10).
Response: `distance_miles`, `fuel_stops[]` (mile marker, station, price, gallons, cost),
`total_gallons`, `total_fuel_cost`, `cost_breakdown`, `assumptions`, and `route` (GeoJSON LineString).
Errors: 400 bad input, 422 no station within range, 502 routing service failure.

## How it works
1. Resolve start/finish from our own `City` table (no geocoding call). **One** routing call per request.
2. Thin the ~8k-point route to ~1 point per mile; find stations within `corridor_miles` using numpy.
3. Stations sharing a city centroid are indistinguishable by location, so only the cheapest is kept.
4. `planner.plan_fuel_stops`: greedy gas-station algorithm. At each stop, if a cheaper station is within
   a full tank, buy just enough to reach it; otherwise fill up and hop to the farthest near-cheapest
   station in reach. The destination is a $0 pseudo-station, so the last buy is exactly what's needed.
5. Results cached per start/finish pair (1 hour). Station table is held in memory per process.

## Assumptions (stated up front)
- **Starting tank:** vehicle leaves with a full 500-mile tank. Fuel burned from it is valued at the average
  price of stations in the corridor, so trips under 500 miles still report a cost. Both parts are shown in
  `cost_breakdown`. Total gallons always equals distance / 10.
- **Savings threshold:** a station counts as "cheaper" only if it saves at least 5 cents/gal
  (`MIN_SAVINGS_PER_GALLON`). Strict minimum cost (0.0) produced 17 stops on a 2,790-mile trip, including
  0.1-gallon buys; 5 cents gives 12 stops for 0.2% more fuel cost.
- **Location precision:** stations have city-level coordinates, and no detour for leaving the highway is modelled.
- Stops at the same city centroid are collapsed to the cheapest one.
