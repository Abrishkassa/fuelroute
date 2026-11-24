from django.test import SimpleTestCase

from stations.planner import NoFeasibleRoute, plan_fuel_stops


def st(position, price, name=None):
    return {"position": position, "price": price, "name": name or f"S{position}"}


class PlannerTests(SimpleTestCase):
    def test_short_trip_needs_no_stops(self):
        plan = plan_fuel_stops([st(100, 3.0)], 300, start_price=3.5)
        self.assertEqual(plan["stops"], [])
        self.assertAlmostEqual(plan["total_cost"], 30 * 3.5)  # 300 mi / 10 mpg at start price

    def test_buys_only_what_is_needed_when_cheaper_ahead(self):
        # A($4)@100, B($3)@400, dest@700. Reach B from A on the starting tank, buy only at B.
        plan = plan_fuel_stops([st(100, 4.0), st(400, 3.0)], 700, start_price=3.5)
        self.assertEqual([s["station"]["name"] for s in plan["stops"]], ["S400"])
        self.assertAlmostEqual(plan["stops"][0]["gallons"], 20.0)  # 200 miles
        self.assertAlmostEqual(plan["purchased_cost"], 60.0)
        self.assertAlmostEqual(plan["start_tank_gallons"], 50.0)
        self.assertAlmostEqual(plan["total_cost"], 60.0 + 50 * 3.5)

    def test_fills_tank_when_nothing_cheaper_in_range(self):
        stations = [st(100, 3.0), st(500, 5.0), st(900, 4.0)]
        plan = plan_fuel_stops(stations, 1200, start_price=0)
        got = [(s["station"]["name"], round(s["gallons"], 1)) for s in plan["stops"]]
        # fill at A (10 gal), bring just enough from B to reach C (30), enough at C to finish (30)
        self.assertEqual(got, [("S100", 10.0), ("S500", 30.0), ("S900", 30.0)])
        self.assertAlmostEqual(plan["purchased_cost"], 10 * 3 + 30 * 5 + 30 * 4)

    def test_total_gallons_always_distance_over_mpg(self):
        plan = plan_fuel_stops([st(200, 3.0), st(650, 3.3)], 900, start_price=3.0)
        bought = sum(s["gallons"] for s in plan["stops"])
        self.assertAlmostEqual(bought + plan["start_tank_gallons"], 90.0)

    def test_gap_longer_than_range_raises(self):
        with self.assertRaises(NoFeasibleRoute):
            plan_fuel_stops([st(100, 3.0)], 1200)

    def test_first_station_beyond_starting_tank_raises(self):
        with self.assertRaises(NoFeasibleRoute):
            plan_fuel_stops([st(450, 3.0)], 900, start_fuel_miles=300)

    def test_never_exceeds_tank_capacity(self):
        stations = [st(p, 3.0 + (p % 7) * 0.1) for p in range(80, 2000, 90)]
        plan = plan_fuel_stops(stations, 2000, start_price=3.2)
        for s in plan["stops"]:
            self.assertLessEqual(s["miles_bought"], 500 + 1e-6)


class NearTieTests(SimpleTestCase):
    STATIONS = [st(100, 3.00), st(101, 2.995), st(450, 3.02), st(900, 3.05)]

    def test_skips_one_mile_hop_for_negligible_saving(self):
        plan = plan_fuel_stops(self.STATIONS, 1200, start_price=3.0, min_savings=0.05)
        names = [s["station"]["name"] for s in plan["stops"]]
        self.assertNotIn("S101", names)
        self.assertIn("S450", names)

    def test_zero_threshold_is_strict_minimum_cost(self):
        strict = plan_fuel_stops(self.STATIONS, 1200, start_price=3.0, min_savings=0.0)
        loose = plan_fuel_stops(self.STATIONS, 1200, start_price=3.0, min_savings=0.05)
        self.assertLessEqual(strict["purchased_cost"], loose["purchased_cost"] + 1e-9)
        self.assertGreaterEqual(len(strict["stops"]), len(loose["stops"]))
