# Fuel Route API (Django 6.1 + DRF + PostgreSQL)

Given a start and finish inside the USA, the API returns the driving route (GeoJSON), the
**cost-optimal fuel stops** for a 500-mile-range vehicle, and the **total fuel cost** at 10 mpg.
A small Leaflet page at `/` draws the route and stops on a map.

## Quick start
```bash
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
# Optional PostgreSQL (SQLite is the zero-setup default). Verified on PostgreSQL 16;
# the docker-compose file is provided for convenience:
#   docker compose up -d
#   export POSTGRES_DB=fuelroute POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres
python manage.py migrate
python manage.py load_stations     # cleans the CSV, downloads a free US cities file, loads stations
python manage.py test              # 21 tests
python manage.py runserver         # open http://127.0.0.1:8000/
```

## API
`GET /api/route/?start=Dallas, TX&finish=Atlanta, GA` (either end may also be `lat,lng`)

Optional: `start_fuel_miles` (0-500, default 500), `corridor_miles` (1-50, default 10).

Returns `distance_miles`, `fuel_stops[]` (mile marker, station, address, price, gallons, cost),
`total_gallons`, `total_fuel_cost`, `cost_breakdown`, `assumptions`, and `route` (GeoJSON LineString).
Errors: `400` bad or non-US input, `422` no station within range, `502` routing service failed.

A Postman collection with tests is in `postman/`.

## How it works
1. **Locations** resolve from our own `City` table (about 30k US cities), so there is no geocoding call.
2. **One routing call** per request to an OSRM-compatible API (`ROUTING_URL`, public demo server by default).
3. The ~8k-point route is thinned to about one point per mile; numpy finds every station within
   `corridor_miles` and its mile position along the route. Stations at the same city centroid collapse
   to the cheapest.
4. `stations/planner.py` runs a greedy gas-station algorithm. At each stop: if a cheaper station is within a
   full tank, buy only enough to reach it; otherwise fill up and hop to the farthest near-cheapest station
   in reach. The destination is a $0 pseudo-station, so the final purchase is exactly what's needed.
5. Responses are cached per start/finish pair for an hour, and the station table is held in memory.

Measured on the full dataset (routing call mocked): about 20-150 ms uncached, 1-2 ms cached.

## Data decisions
- Canadian provinces (620 rows) dropped. Duplicate OPIS IDs (905) keep the cheapest row; 6,626 stations remain.
- The CSV has no coordinates, and its addresses are highway exits, so stations get **city-level**
  coordinates by joining city + state to a free US cities dataset (99.8% match; 6 cities hand-patched).

## Assumptions
- **Starting tank:** the vehicle leaves with a full 500-mile tank. Fuel burned from it is valued at the average
  price of stations in the corridor, so short trips still report a cost. `cost_breakdown` splits
  `purchased_at_stops` from `starting_tank`. Total gallons always equals distance / 10.
- **Savings threshold:** a station is "cheaper" only if it saves at least 5 cents/gal
  (`MIN_SAVINGS_PER_GALLON`). A strict minimum gave 17 stops on a 2,790-mile trip (including 0.1-gallon
  buys); 5 cents gives 12 stops for about 0.2% more fuel cost.
- No detour cost is modelled for leaving the highway; the corridor is 10 miles because station coordinates are city-level.

## Known limitations
- City-level station coordinates mean a stop's map pin can be a few miles from the real exit.
- The public OSRM demo server has no SLA; set `ROUTING_URL` to a self-hosted or keyed instance for production.
- The cache is per-process (Django local memory); use Redis for multi-worker deployments.
- No live prices: the CSV is a snapshot, and the code treats it as static.
- Very small purchases (under 1 gallon) can still occur when a stop is needed only to top up slightly.

## Layout
`stations/planner.py` (algorithm) · `geo.py` (corridor search) · `services.py` (orchestration) ·
`routing.py` (the single external call) · `ingest.py` + `management/commands/load_stations.py` (data pipeline) ·
`views.py` + `templates/stations/map.html` (API and map).
