"""Fuel stop planner: the core algorithm. Pure Python, no Django, easy to test.

Problem: drive `total_miles` along a line. A tank holds `range_miles` of fuel. Fuel can be
bought at stations (position = miles from start, price = $/gal). Minimise money spent.

Greedy rule (classic "gas station" problem), applied at each station we stop at:
  1. If a CHEAPER station is within a full tank's reach, buy only enough fuel to get there.
     (Fuel here is dearer than fuel there, so never buy more than needed.)
  2. Otherwise nothing ahead is cheaper, so fill the tank here, then drive to the farthest
     station whose price is (nearly) the cheapest within reach.
The destination is a pseudo-station priced $0, so rule 1 also means "buy only what's needed
to arrive". We don't pay a detour for leaving the highway; stations are within a small
corridor of the route (see geo.py).
"""
from bisect import bisect_right


class NoFeasibleRoute(Exception):
    """No station is reachable within the vehicle's range at some point on the route."""


def plan_fuel_stops(stations, total_miles, *, range_miles=500.0, mpg=10.0,
                    start_fuel_miles=500.0, start_price=0.0, min_savings=0.0):
    """
    stations: list of dicts with at least 'position' (miles) and 'price' ($/gal),
              sorted by position. Extra keys are passed through untouched.
    Returns a dict:
      stops           [{'station': <dict>, 'miles_bought', 'gallons', 'cost'}, ...]
      gallons_total   gallons needed for the whole trip (total_miles / mpg)
      purchased_cost  money spent at the stops
      start_tank_gallons / start_tank_cost
                      fuel burned from the tank we left home with, valued at `start_price`
      total_cost      purchased_cost + start_tank_cost
    min_savings: a station only counts as "cheaper" if it saves at least this many $/gal.
                 0 gives the strict minimum cost; a few cents avoids chasing negligible
                 savings with tiny stop-and-go purchases.
    """
    fuel = float(min(start_fuel_miles, range_miles))  # fuel on board, in miles of range
    gallons_total = total_miles / mpg

    destination = {"position": float(total_miles), "price": 0.0, "is_destination": True}
    nodes = [s for s in stations if 0 < s["position"] < total_miles] + [destination]
    positions = [n["position"] for n in nodes]

    purchases = []
    current = None  # index into nodes; None means "still at the start"

    if total_miles > fuel:
        # No station at the origin, so the first hop is just to the nearest station we can reach.
        if nodes[0]["position"] > fuel:
            raise NoFeasibleRoute("No fuel station within reach of the starting tank.")
        fuel -= nodes[0]["position"]
        current = 0
    else:
        current = len(nodes) - 1  # destination reachable on the starting tank alone

    while not nodes[current].get("is_destination"):
        here = nodes[current]
        window_end = bisect_right(positions, here["position"] + range_miles)
        window = range(current + 1, window_end)
        if not window:
            raise NoFeasibleRoute(
                f"No station within {range_miles:.0f} miles after mile {here['position']:.0f}."
            )

        cheaper = next((i for i in window if nodes[i]["price"] < here["price"] - min_savings), None)
        if cheaper is not None:
            target = cheaper
            miles_bought = max(0.0, nodes[target]["position"] - here["position"] - fuel)
        else:
            # Hop to the FARTHEST station whose price is within min_savings of the cheapest in
            # reach: same money, fewer stops (avoids 1-mile hops to a fraction-of-a-cent saving).
            floor = min(nodes[i]["price"] for i in window)
            target = max(i for i in window if nodes[i]["price"] <= floor + min_savings)
            miles_bought = range_miles - fuel  # fill the tank

        if miles_bought > 1e-9:
            gallons = miles_bought / mpg
            purchases.append({
                "station": here,
                "miles_bought": miles_bought,
                "gallons": gallons,
                "cost": gallons * here["price"],
            })
        fuel = max(0.0, fuel + miles_bought - (nodes[target]["position"] - here["position"]))
        current = target

    purchased_gallons = sum(p["gallons"] for p in purchases)
    purchased_cost = sum(p["cost"] for p in purchases)
    start_tank_gallons = max(0.0, gallons_total - purchased_gallons)
    start_tank_cost = start_tank_gallons * start_price
    return {
        "stops": purchases,
        "gallons_total": gallons_total,
        "purchased_cost": purchased_cost,
        "start_tank_gallons": start_tank_gallons,
        "start_tank_cost": start_tank_cost,
        "total_cost": purchased_cost + start_tank_cost,
    }
