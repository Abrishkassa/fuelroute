"""Routing client: exactly ONE external call per route request.

Uses an OSRM-compatible endpoint (public demo server by default, configurable via
ROUTING_URL). Returns the route geometry as [(lat, lng), ...] plus total miles.
"""
import requests
from django.conf import settings

METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


def decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode a Google/OSRM encoded polyline into [(lat, lng), ...]."""
    coords, index, lat, lng = [], 0, 0, 0
    factor = 10 ** precision
    while index < len(encoded):
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lat:
                lat += delta
            else:
                lng += delta
        coords.append((lat / factor, lng / factor))
    return coords


def get_route(start: tuple[float, float], finish: tuple[float, float]) -> dict:
    """start/finish are (lat, lng). Returns {'points': [...], 'miles': float}."""
    url = (
        f"{settings.ROUTING_URL}/{start[1]},{start[0]};{finish[1]},{finish[0]}"
        "?overview=full&geometries=polyline&steps=false"
    )
    try:
        resp = requests.get(url, timeout=settings.ROUTING_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service failed: {exc}") from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No route found: {data.get('code')}")
    route = data["routes"][0]
    return {
        "points": decode_polyline(route["geometry"]),
        "miles": route["distance"] / METERS_PER_MILE,
    }
