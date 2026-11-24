from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from stations.ingest import clean_stations, load_city_index
from stations.models import City, Station


class Command(BaseCommand):
    help = "Clean the fuel CSV, attach city-level coordinates, and load stations (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(settings.BASE_DIR / "data" / "fuel-prices-for-be-assessment.csv"))
        parser.add_argument("--cities", default=str(settings.BASE_DIR / "data" / "us_cities.csv"))

    def handle(self, *args, **opts):
        cities_path = Path(opts["cities"])
        if not cities_path.exists():
            self.stdout.write(f"Downloading US cities dataset -> {cities_path}")
            resp = requests.get(settings.CITIES_CSV_URL, timeout=60)
            resp.raise_for_status()
            cities_path.write_bytes(resp.content)

        city_index = load_city_index(cities_path)
        City.objects.bulk_create(
            [City(key=k, name=name, state=st, latitude=lat, longitude=lng) for (k, st), (lat, lng, name) in city_index.items()],
            batch_size=2000, update_conflicts=True, unique_fields=["key", "state"],
            update_fields=["name", "latitude", "longitude"],
        )
        rows, stats = clean_stations(opts["csv"], city_index)
        Station.objects.bulk_create(
            [Station(**r) for r in rows],
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["opis_id"],
            update_fields=["name", "address", "city", "state", "rack_id", "price", "latitude", "longitude"],
        )
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} stations. Stats: {stats}"))
