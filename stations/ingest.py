"""Pure functions for turning the raw fuel CSV into clean, geocoded station rows.

Kept free of Django imports so the logic is trivial to unit test.
Decisions (also documented in the README):
  * Non-US rows (Canadian provinces) are dropped.
  * Duplicate OPIS IDs: keep the cheapest row (no timestamp exists to prefer a newer one).
  * Coordinates are city-level, joined from a free US cities dataset. Addresses are
    highway exits ("I-44, EXIT 283 & US-69") which street geocoders cannot resolve.
"""
import csv
import re
from decimal import Decimal

US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
    "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)

# Approximate centroids for the few station cities missing from the cities dataset.
MANUAL_COORDS = {
    ("brookpark", "OH"): (41.40, -81.80),
    ("elizabethport", "NJ"): (40.66, -74.19),
    ("evergreen", "AL"): (31.43, -86.96),
    ("henrico", "VA"): (37.55, -77.40),
    ("portwentworth", "GA"): (32.15, -81.16),  # key has no space: see normalize_city
    ("universitypark", "IL"): (41.44, -87.68),
}


def normalize_city(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\bst\.? ", "saint ", s)
    s = re.sub(r"\bmt\.? ", "mount ", s)
    s = re.sub(r"\bft\.? ", "fort ", s)
    return re.sub(r"[^a-z0-9]", "", s)  # drop spaces/punctuation entirely


def load_city_index(path) -> dict:
    """{(normalized_city, STATE): (lat, lng)} from the US cities CSV."""
    index = dict(MANUAL_COORDS)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (normalize_city(row["CITY"]), row["STATE_CODE"])
            index.setdefault(key, (float(row["LATITUDE"]), float(row["LONGITUDE"])))
    return index


def clean_stations(csv_path, city_index) -> tuple[list[dict], dict]:
    """Return (clean_rows, stats). Each row is ready for Station(**row)."""
    stats = {"rows": 0, "non_us": 0, "no_coords": 0, "duplicates_dropped": 0}
    best: dict[int, dict] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            stats["rows"] += 1
            state = raw["State"].strip().upper()
            if state not in US_STATES:
                stats["non_us"] += 1
                continue
            coords = city_index.get((normalize_city(raw["City"]), state))
            if coords is None:
                stats["no_coords"] += 1
                continue
            row = {
                "opis_id": int(raw["OPIS Truckstop ID"]),
                "name": raw["Truckstop Name"].strip(),
                "address": raw["Address"].strip(),
                "city": raw["City"].strip(),
                "state": state,
                "rack_id": int(raw["Rack ID"]),
                "price": Decimal(raw["Retail Price"]).quantize(Decimal("0.00001")),
                "latitude": coords[0],
                "longitude": coords[1],
            }
            current = best.get(row["opis_id"])
            if current is None:
                best[row["opis_id"]] = row
            else:
                stats["duplicates_dropped"] += 1
                if row["price"] < current["price"]:
                    best[row["opis_id"]] = row
    stats["kept"] = len(best)
    return list(best.values()), stats
