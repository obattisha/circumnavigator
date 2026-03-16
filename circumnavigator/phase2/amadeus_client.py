"""Amadeus API client with OAuth2 token management and disk caching."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from config import (
    AMADEUS_CLIENT_ID,
    AMADEUS_CLIENT_SECRET,
    AMADEUS_TOKEN_URL,
    AMADEUS_FLIGHTS_URL,
)
from circumnavigator.phase2.cache import cache_get, cache_set


class AmadeusClient:
    """Thread-safe(ish) Amadeus sandbox API client with auto token refresh."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expires: float = 0.0
        self._client = httpx.Client(timeout=30)

    def _ensure_token(self) -> None:
        if self._token and time.time() < self._token_expires - 30:
            return
        if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
            raise RuntimeError(
                "AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET environment variables required."
            )
        resp = self._client.post(
            AMADEUS_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": AMADEUS_CLIENT_ID,
                "client_secret": AMADEUS_CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 1800)

    def get_nonstop_flights(
        self, origin: str, destination: str, date: str
    ) -> list[dict[str, Any]]:
        """Return list of nonstop flight offers for (origin, destination, date).

        Date format: "YYYY-MM-DD".
        Uses disk cache — each (origin, dest, date) triple fetched at most once.
        """
        cached = cache_get(origin, destination, date)
        if cached is not None:
            return cached

        self._ensure_token()
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": date,
            "adults": 1,
            "nonStop": "true",
            "max": 50,
            "currencyCode": "USD",
        }
        resp = self._client.get(
            AMADEUS_FLIGHTS_URL,
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
        )
        if resp.status_code == 404:
            result: list[dict] = []
        else:
            resp.raise_for_status()
            result = resp.json().get("data", [])

        cache_set(origin, destination, date, result)
        return result

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AmadeusClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def parse_offer(offer: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Extract departure/arrival UTC datetimes and duration from an offer dict."""
    try:
        itinerary = offer["itineraries"][0]
        segments = itinerary["segments"]
        if len(segments) != 1:
            return None   # not nonstop (should not happen with nonStop=true)
        seg = segments[0]
        dep = seg["departure"]["at"]   # "YYYY-MM-DDTHH:MM:SS" local
        arr = seg["arrival"]["at"]
        duration_str = itinerary.get("duration", "PT0H0M")  # ISO 8601 e.g. PT14H30M
        return {
            "flight_number": seg["carrierCode"] + seg["number"],
            "departure_local": dep,
            "arrival_local": arr,
            "duration_iso": duration_str,
        }
    except (KeyError, IndexError):
        return None


def iso_duration_to_minutes(duration: str) -> int:
    """Convert ISO 8601 duration like 'PT14H30M' to minutes."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes
