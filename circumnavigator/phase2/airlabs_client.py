"""AirLabs Routes API client with permanent disk cache.

One API call per (dep_iata, arr_iata) pair — cached forever since airline
schedules are semi-static.  The cache is the source of truth for the static
scheduler; no further network calls are made at schedule-compute time.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import time
from typing import Optional

import httpx

from config import AIRLABS_API_KEY, AIRLABS_ROUTES_URL, API_CACHE_DIR

# AirLabs day-name → Python weekday (Mon=0 … Sun=6)
_DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class FlightFrequency:
    """One scheduled nonstop service between two airports."""
    flight_iata: str          # e.g. "AC837"
    airline_iata: str         # e.g. "AC"
    dep_iata: str
    arr_iata: str
    dep_utc: time             # scheduled UTC departure (HH:MM)
    arr_utc: time             # scheduled UTC arrival  (HH:MM)
    duration_min: int         # block time in minutes
    days: frozenset[int]      # Python weekdays this flight operates (Mon=0)
    overnight: bool           # arrival is next calendar day after departure

    def operates_on(self, weekday: int) -> bool:
        return weekday in self.days


def _cache_path(dep: str, arr: str) -> str:
    return os.path.join(API_CACHE_DIR, f"airlabs_{dep}_{arr}.json")


def _load_cache(dep: str, arr: str) -> Optional[list[dict]]:
    p = _cache_path(dep, arr)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(dep: str, arr: str, data: list[dict]) -> None:
    os.makedirs(API_CACHE_DIR, exist_ok=True)
    with open(_cache_path(dep, arr), "w", encoding="utf-8") as f:
        json.dump(data, f)


def fetch_routes(dep: str, arr: str) -> list[dict]:
    """Fetch raw route records from AirLabs (or disk cache)."""
    cached = _load_cache(dep, arr)
    if cached is not None:
        return cached

    if not AIRLABS_API_KEY:
        raise RuntimeError(
            "AIRLABS_API_KEY environment variable not set.\n"
            "Sign up free at https://airlabs.co and export your key."
        )

    resp = httpx.get(
        AIRLABS_ROUTES_URL,
        params={"dep_iata": dep, "arr_iata": arr, "api_key": AIRLABS_API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("response", [])
    _save_cache(dep, arr, data)
    return data


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' string to datetime.time."""
    h, m = s.split(":")
    return time(int(h), int(m))


def parse_frequencies(raw: list[dict]) -> list[FlightFrequency]:
    """Convert raw AirLabs route records into FlightFrequency objects."""
    result: list[FlightFrequency] = []
    for r in raw:
        try:
            dep_utc = _parse_time(r["dep_time_utc"])
            arr_utc = _parse_time(r["arr_time_utc"])
            duration = int(r.get("duration") or 0)
            if duration <= 0:
                continue   # skip placeholder/bad records with no block time
            raw_days = r.get("days") or []
            days = frozenset(_DAY_MAP[d] for d in raw_days if d in _DAY_MAP)
            if not days:
                # No day info — assume daily
                days = frozenset(range(7))
            # Overnight: arrival clock-time is earlier than departure
            overnight = arr_utc < dep_utc
            result.append(FlightFrequency(
                flight_iata=r.get("flight_iata") or "",
                airline_iata=r.get("airline_iata", ""),
                dep_iata=r["dep_iata"],
                arr_iata=r["arr_iata"],
                dep_utc=dep_utc,
                arr_utc=arr_utc,
                duration_min=duration,
                days=days,
                overnight=overnight,
            ))
        except (KeyError, ValueError, AttributeError, TypeError):
            continue
    # Sort by departure time for deterministic processing
    result.sort(key=lambda f: f.dep_utc)
    return result


def prefetch_all_pairs(
    pairs: list[tuple[str, str]],
    verbose: bool = True,
) -> dict[tuple[str, str], list[FlightFrequency]]:
    """Fetch (and cache) routes for every (dep, arr) pair.

    Returns dict mapping (dep, arr) → list of FlightFrequency.
    Pairs already on disk are loaded without hitting the network.
    """
    result: dict[tuple[str, str], list[FlightFrequency]] = {}
    need_fetch = [(d, a) for d, a in pairs if _load_cache(d, a) is None]
    cached_count = len(pairs) - len(need_fetch)

    if verbose:
        print(
            f"Route pairs: {len(pairs)} total, "
            f"{cached_count} cached, {len(need_fetch)} to fetch",
            file=sys.stderr,
        )

    for i, (dep, arr) in enumerate(need_fetch, 1):
        if verbose:
            print(f"  [{i}/{len(need_fetch)}] Fetching {dep}→{arr} ...", file=sys.stderr)
        try:
            raw = fetch_routes(dep, arr)
            result[(dep, arr)] = parse_frequencies(raw)
        except Exception as e:
            print(f"  WARNING: {dep}→{arr} failed: {e}", file=sys.stderr)
            result[(dep, arr)] = []

    # Load all cached pairs
    for dep, arr in pairs:
        if (dep, arr) not in result:
            raw = _load_cache(dep, arr) or []
            result[(dep, arr)] = parse_frequencies(raw)

    return result
