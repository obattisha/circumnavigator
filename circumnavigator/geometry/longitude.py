"""Longitude arithmetic for circumnavigation tracking (antimeridian-safe)."""

from __future__ import annotations


def longitude_delta(lon_from: float, lon_to: float, direction: str = "") -> float:
    """Return the signed longitude change for a direct nonstop flight leg.

    Always returns a value in (-180, 180] — the actual shortest-path signed
    longitude change.  Positive = eastward, negative = westward.  The
    `direction` parameter is accepted for API compatibility but not used;
    the caller decides whether the sign is acceptable for their direction.

    Examples:
      BNE (+153) → LAX (-118)  →  +89   (east, crossing antimeridian)
      HKG (+114) → YVR (-123)  →  +123  (east, crossing antimeridian)
      LAX (-118) → DOH (+051)  →  +169  (east)
      GUM (+144) → CTS (+141)  →  -3    (west — NOT a valid eastbound leg)
    """
    return (lon_to - lon_from + 180) % 360 - 180


def total_longitude_covered(lons: list[float]) -> float:
    """Absolute sum of signed longitude deltas along a sequence of longitudes."""
    total = 0.0
    for i in range(len(lons) - 1):
        total += longitude_delta(lons[i], lons[i + 1])
    return abs(total)
