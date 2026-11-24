from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase

from stations.ingest import clean_stations, normalize_city
from stations.models import Station
from stations.routing import RoutingError, decode_polyline, get_route

CSV = (
    "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\r\n"
    '1,PILOT #1,"I-8, EXIT 1",Gila Bend,AZ,930,3.899\r\n'
    '1,PILOT TRAVEL CENTER #1,"I-8, EXIT 1",Gila Bend,AZ,930,3.799\r\n'
    "2,CANADIAN STOP,HWY 1,Calgary,AB,1,4.5\r\n"
    "3,ST LOUIS STOP,I-70,St. Louis,MO,2,3.2\r\n"
)
CITY_INDEX = {("gilabend", "AZ"): (32.95, -112.72), ("saintlouis", "MO"): (38.63, -90.2)}


class CleaningTests(SimpleTestCase):
    def setUp(self):
        import tempfile

        self.tmp = Path(tempfile.mkstemp(suffix=".csv")[1])
        self.tmp.write_text(CSV, encoding="utf-8")

    def test_drops_non_us_and_dedupes_to_cheapest(self):
        rows, stats = clean_stations(self.tmp, CITY_INDEX)
        by_id = {r["opis_id"]: r for r in rows}
        self.assertEqual(set(by_id), {1, 3})
        self.assertEqual(by_id[1]["price"], Decimal("3.79900"))
        self.assertEqual(stats["non_us"], 1)
        self.assertEqual(stats["duplicates_dropped"], 1)

    def test_city_normalization(self):
        self.assertEqual(normalize_city("St. Louis"), "saintlouis")
        self.assertEqual(normalize_city("Port Wentworth"), "portwentworth")


class PolylineTests(SimpleTestCase):
    def test_decodes_google_reference_example(self):
        pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(pts, [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])


class RoutingTests(SimpleTestCase):
    @mock.patch("stations.routing.requests.get")
    def test_single_call_and_parse(self, get):
        get.return_value.json.return_value = {
            "code": "Ok",
            "routes": [{"geometry": "_p~iF~ps|U_ulLnnqC", "distance": 1609.344 * 100}],
        }
        route = get_route((38.5, -120.2), (40.7, -120.95))
        self.assertEqual(get.call_count, 1)
        self.assertAlmostEqual(route["miles"], 100.0)
        self.assertEqual(len(route["points"]), 2)

    @mock.patch("stations.routing.requests.get")
    def test_no_route_raises(self, get):
        get.return_value.json.return_value = {"code": "NoRoute", "routes": []}
        with self.assertRaises(RoutingError):
            get_route((0, 0), (1, 1))


class ModelSmokeTest(TestCase):
    def test_create(self):
        s = Station.objects.create(
            opis_id=9, name="X", address="Y", city="Z", state="TX", rack_id=1,
            price=Decimal("3.5"), latitude=30.0, longitude=-97.0,
        )
        self.assertEqual(Station.objects.count(), 1)
        self.assertIn("TX", str(s))
