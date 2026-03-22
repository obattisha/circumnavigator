"""Antipodal geometry utilities.

Two airports are *near-antipodal* when they are approximately at opposite ends
of Earth.  Guinness uses **independent** 5° tolerances per dimension:

  lat_off = ||lat1| − |lat2||           ≤ 5°   (magnitudes should match)
  lon_off = circular distance from 180°  ≤ 5°   (longitudes should sum to 180°)

In terms of signed coordinates (N positive, E positive):
  lat_off = |lat1 + lat2|               (0 when lat2 = −lat1, i.e. opposite)
  antipode_lon of lon1 = lon1 ± 180
  lon_off = circular gap between lon2 and antipode_lon(lon1)

Both conditions must hold independently (NOT combined budget).

Example: PVG (31.14°N, 121.81°E) ↔ EZE (34.82°S, 58.54°W)
  lat_off = |31.14 + (−34.82)| = 3.68°  ≤ 5° ✓
  antipode_lon(121.81°E) = −58.19°E ; EZE lon = −58.54°
  lon_off = 0.35°                         ≤ 5° ✓

Example: AKL (36.99°S, 174.79°E) ↔ MAD (40.47°N, −3.56°E)
  lat_off = |−36.99 + 40.47| = 3.48°   ≤ 5° ✓
  antipode_lon(174.79°E) = −5.21°E ; MAD lon = −3.56°
  lon_off = 1.65°                        ≤ 5° ✓
"""

from __future__ import annotations

from circumnavigator.data.airports import Airport


def antipodal_components(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float]:
    """Return (lat_off, lon_off) from exact antipodal (degrees, each ≥ 0)."""
    lat_off = abs(lat1 + lat2)
    antipode_lon = lon1 + 180.0 if lon1 <= 0.0 else lon1 - 180.0
    d = abs(lon2 - antipode_lon)
    lon_off = min(d, 360.0 - d)
    return lat_off, lon_off


def is_near_antipodal(
    ap1: Airport, ap2: Airport, tolerance: float = 5.0
) -> bool:
    """Return True if both lat_off ≤ tolerance AND lon_off ≤ tolerance."""
    lat_off, lon_off = antipodal_components(ap1.lat, ap1.lon, ap2.lat, ap2.lon)
    return lat_off <= tolerance and lon_off <= tolerance


def build_antipodal_partners(
    airports: dict[str, Airport],
    candidate_iatas: set[str],
    tolerance: float = 5.0,
) -> dict[str, frozenset[str]]:
    """For each airport in *candidate_iatas*, find all near-antipodal partners.

    Returns dict: iata -> frozenset of near-antipodal iata codes.
    Only airports with at least one partner are included.

    O(n²) — fine for the long-haul graph (~500–1 000 airports).
    """
    candidates = [(iata, airports[iata]) for iata in candidate_iatas if iata in airports]
    partners: dict[str, set[str]] = {}

    for i, (iata_a, ap_a) in enumerate(candidates):
        for iata_b, ap_b in candidates[i + 1:]:
            if is_near_antipodal(ap_a, ap_b, tolerance):
                partners.setdefault(iata_a, set()).add(iata_b)
                partners.setdefault(iata_b, set()).add(iata_a)

    return {k: frozenset(v) for k, v in partners.items()}
