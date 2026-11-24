"""Orchestration: resolve locations -> ONE routing call -> corridor -> fuel plan -> response."""
import hashlib
import re
from functools import lru_cache

import numpy as np
from django.conf import settings
from django.core.cache import cache

from .geo import simplify_route, stations_near_route
from .ingest import normalize_city
from .models import City, Station
from .planner import NoFeasibleRoute, plan_fuel_stops  # noqa: F401  (re-exported for views)
from .routing import get_route

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
# Rough bounding box around the USA (lower 48 + Alaska + Hawaii) as a sanity check.
USA_BOX = (18.0, 72.0, -171.0, -65.0)


class LocationError(ValueError):
    pass


def resolve_location(text: str) -> dict:
    """Accepts 'lat,lng' or 'City, ST'. Text is resolved from our own DB: zero API calls."""
    m = COORD_RE.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        label = text.strip()
    else:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 2 or len(parts[1]) != 2:
            raise LocationError(f"Could not understand '{text}'. Use 'City, ST' or 'lat,lng'.")
        city = City.objects.filter(key=normalize_city(parts[0]), state=parts[1].upper()).first()
        if city is None:
            raise LocationError(f"Unknown US city '{text}'.")
        lat, lng, label = city.latitude, city.longitude, f"{city.name}, {city.state}"
    if not (USA_BOX[0] <= lat <= USA_BOX[1] and USA_BOX[2] <= lng <= USA_BOX[3]):
        raise LocationError(f"'{text}' is outside the USA.")
    return {"input": text.strip(), "label": label, "lat": lat, "lng": lng}


@lru_cache(maxsize=1)
def station_table():
    """All stations as numpy arrays + row dicts, loaded once per process (6.6k rows)."""
    rows = list(Station.objects.values(
        "opis_id", "name", "address", "city", "state", "price", "latitude", "longitude"))
    return {
        "rows": rows,
        "lat": np.array([r["latitude"] for r in rows]),
        "lng": np.array([r["longitude"] for r in rows]),
    }


def _collapse_same_spot(candidates):
    """Stations sharing a city centroid can't be told apart by location: keep the cheapest."""
    best = {}
    for c in candidates:
        key = (round(c["latitude"], 4), round(c["longitude"], 4))
        if key not in best or (c["price"], c["opis_id"]) < (best[key]["price"], best[key]["opis_id"]):
            best[key] = c
    return sorted(best.values(), key=lambda c: c["position"])


def plan_trip(start_text, finish_text, start_fuel_miles=None, corridor_miles=None):
    cfg = settings
    start_fuel_miles = cfg.VEHICLE_RANGE_MILES if start_fuel_miles is None else start_fuel_miles
    corridor_miles = cfg.CORRIDOR_MILES if corridor_miles is None else corridor_miles

    start, finish = resolve_location(start_text), resolve_location(finish_text)
    cache_key = "trip:" + hashlib.sha1(
        f"{start['lat']:.4f},{start['lng']:.4f}|{finish['lat']:.4f},{finish['lng']:.4f}|"
        f"{start_fuel_miles}|{corridor_miles}".encode()).hexdigest()
    if (hit := cache.get(cache_key)) is not None:
        return hit

    route = get_route((start["lat"], start["lng"]), (finish["lat"], finish["lng"]))  # the ONE API call
    pts, cum = simplify_route(route["points"])
    scale = route["miles"] / cum[-1] if cum[-1] else 1.0
    positions_scale = scale  # make mile markers agree with the routing service's distance

    table = station_table()
    near, miles, off_route = stations_near_route(pts, cum, table["lat"], table["lng"], corridor_miles)
    candidates = [
        {**table["rows"][i], "price": float(table["rows"][i]["price"]),
         "position": float(m * positions_scale), "off_route_miles": float(d)}
        for i, m, d in zip(near, miles, off_route)
    ]
    candidates = _collapse_same_spot(candidates)

    pool = [c["price"] for c in candidates] or [float(r["price"]) for r in table["rows"]]
    avg_price = float(np.mean(pool)) if pool else 0.0
    plan = plan_fuel_stops(
        candidates, route["miles"], range_miles=cfg.VEHICLE_RANGE_MILES, mpg=cfg.VEHICLE_MPG,
        start_fuel_miles=start_fuel_miles, start_price=avg_price,
        min_savings=cfg.MIN_SAVINGS_PER_GALLON)

    result = {
        "start": start,
        "finish": finish,
        "distance_miles": round(route["miles"], 1),
        "fuel_stops": [
            {
                "mile_marker": round(p["station"]["position"], 1),
                "name": p["station"]["name"],
                "address": p["station"]["address"],
                "city": p["station"]["city"],
                "state": p["station"]["state"],
                "latitude": p["station"]["latitude"],
                "longitude": p["station"]["longitude"],
                "price_per_gallon": round(p["station"]["price"], 3),
                "gallons_purchased": round(p["gallons"], 2),
                "cost": round(p["cost"], 2),
            }
            for p in plan["stops"]
        ],
        "total_gallons": round(plan["gallons_total"], 2),
        "total_fuel_cost": round(plan["total_cost"], 2),
        "cost_breakdown": {
            "purchased_at_stops": round(plan["purchased_cost"], 2),
            "starting_tank": round(plan["start_tank_cost"], 2),
        },
        "assumptions": {
            "vehicle_range_miles": cfg.VEHICLE_RANGE_MILES,
            "miles_per_gallon": cfg.VEHICLE_MPG,
            "start_fuel_miles": start_fuel_miles,
            "starting_tank_priced_at": round(avg_price, 3),
            "corridor_miles": corridor_miles,
            "min_savings_per_gallon": cfg.MIN_SAVINGS_PER_GALLON,
            "stations_considered": len(candidates),
        },
        "route": {
            "type": "Feature",
            "properties": {"distance_miles": round(route["miles"], 1)},
            "geometry": {"type": "LineString", "coordinates": [[round(p[1], 5), round(p[0], 5)] for p in pts]},
        },
    }
    cache.set(cache_key, result, cfg.TRIP_CACHE_SECONDS)
    return result
