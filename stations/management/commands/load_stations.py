from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from stations.ingest import clean_stations, load_city_index
from stations.models import Station


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

        rows, stats = clean_stations(opts["csv"], load_city_index(cities_path))
        Station.objects.bulk_create(
            [Station(**r) for r in rows],
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["opis_id"],
            update_fields=["name", "address", "city", "state", "rack_id", "price", "latitude", "longitude"],
        )
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} stations. Stats: {stats}"))
