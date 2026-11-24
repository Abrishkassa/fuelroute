"""Geometry helpers: shrink the route, find stations near it, and locate them along it.

Distances use an equirectangular approximation, which is accurate to well under 1% over the
few-mile corridor distances we care about, and is fully vectorised with numpy.
"""
import numpy as np

MILES_PER_DEG_LAT = 69.0
EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(lng2) - np.radians(lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def simplify_route(points, spacing_miles=1.0):
    """Thin an N-point polyline to roughly one point per `spacing_miles`.

    Returns (points Nx2 array of lat,lng; cumulative miles per point, same length).
    The 8k-point route from the routing service becomes ~1 point per mile, which keeps both
    the station search and the API response small.
    """
    pts = np.asarray(points, dtype=float)
    seg = haversine_miles(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.arange(0.0, cum[-1], spacing_miles)
    keep = np.unique(np.concatenate([np.searchsorted(cum, targets), [len(pts) - 1]]))
    return pts[keep], cum[keep]


def stations_near_route(route_pts, route_cum, st_lat, st_lng, corridor_miles):
    """For every station within `corridor_miles` of the route, find where along it it sits.

    Returns (station_indices, mile_positions, distance_from_route), each a 1-D array.
    """
    margin = corridor_miles / MILES_PER_DEG_LAT + 0.05
    box = (
        (st_lat >= route_pts[:, 0].min() - margin) & (st_lat <= route_pts[:, 0].max() + margin)
        & (st_lng >= route_pts[:, 1].min() - 2 * margin) & (st_lng <= route_pts[:, 1].max() + 2 * margin)
    )
    idx = np.flatnonzero(box)
    if idx.size == 0:
        return idx, np.array([]), np.array([])

    lat, lng = st_lat[idx], st_lng[idx]
    dy = (lat[:, None] - route_pts[None, :, 0]) * MILES_PER_DEG_LAT
    dx = (lng[:, None] - route_pts[None, :, 1]) * MILES_PER_DEG_LAT * np.cos(np.radians(lat))[:, None]
    dist = np.sqrt(dx * dx + dy * dy)
    nearest = dist.argmin(axis=1)
    best = dist[np.arange(idx.size), nearest]
    ok = best <= corridor_miles
    return idx[ok], route_cum[nearest[ok]], best[ok]
