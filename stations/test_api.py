from decimal import Decimal
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from stations.geo import simplify_route, stations_near_route
from stations.models import City, Station
from stations.services import station_table


class GeoTests(SimpleTestCase):
    def test_simplify_and_corridor(self):
        line = [(35.0, -100.0 + i * 0.01) for i in range(1001)]  # ~567 miles due east
        pts, cum = simplify_route(line, spacing_miles=1.0)
        self.assertLess(len(pts), 700)
        self.assertAlmostEqual(cum[-1], 567, delta=8)
        lat = np.array([35.05, 35.5, 36.5])      # ~3.5 mi off, ~35 mi off, ~100 mi off
        lng = np.array([-95.0, -95.0, -95.0])
        idx, miles, off = stations_near_route(pts, cum, lat, lng, corridor_miles=10)
        self.assertEqual(list(idx), [0])
        self.assertAlmostEqual(miles[0], 283, delta=6)


def fake_route(*_args):
    pts = [(35.0, -100.0 + i * 0.01) for i in range(1001)]
    return {"points": pts, "miles": 567.0}


class RouteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.create(key="alpha", name="Alpha", state="TX", latitude=35.0, longitude=-100.0)
        City.objects.create(key="omega", name="Omega", state="TX", latitude=35.0, longitude=-90.0)
        for i, (lng, price) in enumerate([(-98.0, "3.50"), (-95.0, "3.00"), (-92.0, "3.20")]):
            Station.objects.create(opis_id=i + 1, name=f"Stop{i + 1}", address="I-40", city="X",
                                   state="TX", rack_id=1, price=Decimal(price),
                                   latitude=35.0, longitude=lng)

    def setUp(self):
        cache.clear()
        station_table.cache_clear()

    @mock.patch("stations.services.get_route", side_effect=fake_route)
    def test_route_returns_stops_cost_and_map_geometry(self, route):
        resp = self.client.get("/api/route/", {"start": "Alpha, TX", "finish": "Omega, TX"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(route.call_count, 1)                       # exactly one routing call
        self.assertEqual([s["name"] for s in body["fuel_stops"]], ["Stop2"])
        self.assertAlmostEqual(body["total_gallons"], 56.7, places=1)
        self.assertGreater(body["total_fuel_cost"], 0)
        self.assertEqual(body["route"]["geometry"]["type"], "LineString")

    @mock.patch("stations.services.get_route", side_effect=fake_route)
    def test_repeat_request_is_served_from_cache(self, route):
        params = {"start": "Alpha, TX", "finish": "Omega, TX"}
        self.client.get("/api/route/", params)
        self.client.get("/api/route/", params)
        self.assertEqual(route.call_count, 1)

    def test_bad_input_returns_clean_errors(self):
        r = self.client.get("/api/route/", {"start": "Nowhere, TX", "finish": "Omega, TX"})
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/route/", {"start": "Alpha, TX"})
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "Omega, TX"})  # London
        self.assertEqual(r.status_code, 400)

    @mock.patch("stations.services.get_route", side_effect=fake_route)
    def test_coordinates_accepted_and_gap_returns_422(self, _route):
        r = self.client.get("/api/route/", {"start": "35.0,-100.0", "finish": "Omega, TX", "corridor_miles": 1})
        self.assertEqual(r.status_code, 200)
        Station.objects.all().delete()
        station_table.cache_clear()
        cache.clear()
        r = self.client.get("/api/route/", {"start": "Alpha, TX", "finish": "Omega, TX"})
        self.assertEqual(r.status_code, 422)


class MapPageTests(SimpleTestCase):
    def test_root_serves_map_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Fuel Route Planner")
        self.assertContains(resp, "/api/route/")
