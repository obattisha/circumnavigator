"""Unified time-space search for circumnavigation optimization.

Replaces the Phase 1 → Phase 2 pipeline.  Instead of:
  1. Find geometrically valid routes (ignoring real schedules)
  2. Try to fit a timetable to each pre-chosen route

We do a single priority-queue search over (airport, time) states:
  • Priority = elapsed seconds from first departure to current arrival
  • At each state try every available outbound flight departing after
    the required minimum connection time
  • Record any state that closes back to origin with ≥ 360° longitude
    coverage AND ≥ GUINNESS_MIN_DISTANCE_KM total distance

This naturally accounts for real connection waits from the very first leg.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from config import (
    GUINNESS_MIN_DISTANCE_KM,
    MIN_LONGITUDE_COVERAGE,
    MIN_CONNECTION_MINUTES,
    RECORD_TIME_SECONDS,
)
from circumnavigator.data.airports import Airport
from circumnavigator.geometry.distance import haversine
from circumnavigator.geometry.longitude import longitude_delta
from circumnavigator.phase2.airlabs_client import FlightFrequency
from circumnavigator.phase2.static_scheduler import ScheduledLeg, ScheduledRoute
from circumnavigator.phase1.enumerator import CandidateRoute

UTC = timezone.utc
EARTH_MAX_LEG_KM = 20_015.0   # theoretical maximum great-circle distance


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _min_conn(airport: Airport) -> int:
    cc = airport.country_code if airport else "XX"
    return MIN_CONNECTION_MINUTES.get(cc, MIN_CONNECTION_MINUTES["default"])


def _all_next_flights(
    flights: list[FlightFrequency],
    earliest: datetime,
    max_wait_hours: int,
) -> list[tuple[FlightFrequency, datetime, datetime]]:
    """Return ALL (flight, dep_dt, arr_dt) tuples for flights departing at or
    after *earliest* and within *max_wait_hours*."""
    cutoff = earliest + timedelta(hours=max_wait_hours)
    search_date = earliest.date()
    result = []

    for day_offset in range(max_wait_hours // 24 + 2):
        d = search_date + timedelta(days=day_offset)
        weekday = d.weekday()
        for fl in flights:
            if not fl.operates_on(weekday):
                continue
            dep_dt = datetime(d.year, d.month, d.day,
                              fl.dep_utc.hour, fl.dep_utc.minute, tzinfo=UTC)
            if dep_dt < earliest:
                continue
            if dep_dt > cutoff:
                continue
            arr_date = d + timedelta(days=1) if fl.overnight else d
            arr_dt = datetime(arr_date.year, arr_date.month, arr_date.day,
                              fl.arr_utc.hour, fl.arr_utc.minute, tzinfo=UTC)
            result.append((fl, dep_dt, arr_dt))

    return result


def _make_candidate(legs: list[ScheduledLeg], airports: dict[str, Airport],
                    lon_cov: float, direction: str) -> CandidateRoute:
    """Construct a CandidateRoute from a set of scheduled legs."""
    iatas = [legs[0].origin] + [l.destination for l in legs]
    dists = []
    for leg in legs:
        a1 = airports.get(leg.origin)
        a2 = airports.get(leg.destination)
        if a1 and a2:
            dists.append(haversine(a1.lat, a1.lon, a2.lat, a2.lon))
        else:
            dists.append(float(leg.duration_minutes) * 900 / 60)
    return CandidateRoute(
        airports=iatas,
        distances_km=dists,
        total_km=sum(dists),
        lon_coverage=lon_cov,
        direction=direction,
        airports_ref=airports,
    )


# --------------------------------------------------------------------------- #
# Main search
# --------------------------------------------------------------------------- #

def search(
    origins: list[str],
    freq_map: dict[tuple[str, str], list[FlightFrequency]],
    airports: dict[str, Airport],
    start_dates: list[date],
    max_legs: int = 4,
    direction: str = "eastbound",
    require_min_distance: bool = True,
    budget_hours: float = 89.0,    # prune anything over this — default 2× record
    max_wait_hours: int = 24,      # max connection wait at one airport
    top_n: int = 50,
    verbose: bool = True,
) -> list[ScheduledRoute]:
    """Find the fastest valid circumnavigation schedules.

    Args:
        origins:          IATA codes of airports to depart from.
        freq_map:         (dep, arr) → list of FlightFrequency objects.
        airports:         Full airport metadata dict.
        start_dates:      Calendar dates to attempt first departure.
        max_legs:         Maximum number of flight legs.
        direction:        "eastbound" or "westbound".
        require_min_distance: Enforce 36,788 km Guinness minimum.
        budget_hours:     Prune states whose elapsed time exceeds this.
        max_wait_hours:   Give up on a connection if no flight within this window.
        top_n:            Maximum number of results to return.
        verbose:          Print progress to stderr.

    Returns:
        List of ScheduledRoute sorted by total elapsed seconds.
    """
    east = direction == "eastbound"
    budget_s = budget_hours * 3600

    # Pre-index outbound flights by departure airport, filtered by direction.
    # outbound[dep] = [(arr, dist_km, lon_delta, [FlightFrequency])]
    outbound: dict[str, list[tuple[str, float, float, list[FlightFrequency]]]] = {}
    for (dep, arr), flights in freq_map.items():
        if not flights:
            continue
        dep_ap = airports.get(dep)
        arr_ap = airports.get(arr)
        if dep_ap is None or arr_ap is None:
            continue
        delta = longitude_delta(dep_ap.lon, arr_ap.lon)
        # Each individual leg must advance in the chosen direction.
        if east and delta <= 0:
            continue
        if not east and delta >= 0:
            continue
        dist = haversine(dep_ap.lat, dep_ap.lon, arr_ap.lat, arr_ap.lon)
        outbound.setdefault(dep, []).append((arr, dist, delta, flights))

    results: list[ScheduledRoute] = []
    seen: set[tuple] = set()   # (origin, airports_tuple) — deduplicate routes
    ctr = 0

    # State tuple stored in heap (all elements must be comparable):
    # (elapsed_s, ctr, first_dep_ts, arr_ts, cur_ap,
    #  visited_tuple, lon_sum, total_km, legs_tuple, origin)
    # where *_ts are UTC timestamps (floats) for heap comparability.
    pq: list = []

    for origin in origins:
        if origin not in airports:
            continue
        for sd in start_dates:
            # "Available from midnight UTC of start date" — no elapsed yet.
            start_dt = datetime(sd.year, sd.month, sd.day, 0, 0, tzinfo=UTC)
            heapq.heappush(pq, (
                0.0, ctr,
                None,                      # first_dep_ts (not yet departed)
                start_dt.timestamp(),      # arr_ts: available from midnight
                origin,
                (origin,),                 # visited tuple
                0.0,                       # lon_sum
                0.0,                       # total_km
                (),                        # legs tuple
                origin,                    # fixed origin for closing
            ))
            ctr += 1

    states_explored = 0

    while pq:
        (elapsed_s, _, first_dep_ts, arr_ts,
         cur_ap, visited, lon_sum, total_km, legs, origin) = heapq.heappop(pq)

        if elapsed_s > budget_s:
            continue

        states_explored += 1

        cur_airport = airports.get(cur_ap)
        if cur_airport is None:
            continue

        arr_dt = datetime.fromtimestamp(arr_ts, tz=UTC)
        depth = len(legs)

        # Minimum connection from current airport (0 at origin on first leg).
        if first_dep_ts is None:
            # Haven't departed yet — no connection time at origin.
            earliest_dep = arr_dt
        else:
            earliest_dep = arr_dt + timedelta(minutes=_min_conn(cur_airport))

        for dst, leg_km, delta, flights in outbound.get(cur_ap, []):
            # Skip airports already visited, UNLESS it's the origin (closing leg).
            closing = dst == origin
            if dst in visited and not closing:
                continue

            new_lon = lon_sum + delta
            new_km = total_km + leg_km
            new_depth = depth + 1

            # Closing leg: check Guinness validity.
            if closing:
                if new_depth < 3:          # need at least 3 legs (2 stops)
                    continue
                if abs(new_lon) < MIN_LONGITUDE_COVERAGE:
                    continue
                if require_min_distance and new_km < GUINNESS_MIN_DISTANCE_KM:
                    continue
            else:
                # Non-closing leg: prune if we can't possibly finish.
                remaining = max_legs - new_depth   # legs still available after this
                # +1 accounts for the mandatory return leg.
                if abs(new_lon) + (remaining + 1) * 180.0 < MIN_LONGITUDE_COVERAGE:
                    continue
                if require_min_distance:
                    if new_km + (remaining + 1) * EARTH_MAX_LEG_KM < GUINNESS_MIN_DISTANCE_KM:
                        continue
                if new_depth >= max_legs and not closing:
                    # Hit depth limit without closing — dead end.
                    continue

            # Try every available flight on this leg (not just the first).
            for fl, dep_dt, new_arr_dt in _all_next_flights(flights, earliest_dep, max_wait_hours):
                # Determine elapsed time.
                if first_dep_ts is None:
                    new_first_dep_ts = dep_dt.timestamp()
                else:
                    new_first_dep_ts = first_dep_ts

                new_elapsed = new_arr_dt.timestamp() - new_first_dep_ts
                if new_elapsed > budget_s:
                    continue

                # Build scheduled leg.
                conn_min: Optional[int] = None
                if legs:
                    prev_arr = datetime.fromtimestamp(arr_ts, tz=UTC)
                    conn_min = int((dep_dt - prev_arr).total_seconds() / 60)

                new_leg = ScheduledLeg(
                    origin=cur_ap,
                    destination=dst,
                    flight_number=fl.flight_iata,
                    departure_utc=dep_dt,
                    arrival_utc=new_arr_dt,
                    duration_minutes=fl.duration_min,
                    connection_minutes=conn_min,
                )
                new_legs = legs + (new_leg,)

                if closing:
                    # Valid circumnavigation found.
                    route_key = (origin, visited)
                    if route_key in seen:
                        continue
                    seen.add(route_key)

                    legs_list = list(new_legs)
                    candidate = _make_candidate(legs_list, airports,
                                                abs(new_lon), direction)
                    sr = ScheduledRoute(
                        candidate=candidate,
                        legs=legs_list,
                        start_date=str(datetime.fromtimestamp(
                            new_first_dep_ts, tz=UTC).date()),
                    )
                    results.append(sr)

                    if verbose and len(results) % 10 == 0:
                        best = results[-1].elapsed_hms
                        print(f"  Found {len(results)} schedules so far "
                              f"(latest: {best}) ...", flush=True)
                else:
                    new_visited = visited + (dst,)
                    heapq.heappush(pq, (
                        new_elapsed, ctr,
                        new_first_dep_ts,
                        new_arr_dt.timestamp(),
                        dst,
                        new_visited,
                        new_lon,
                        new_km,
                        new_legs,
                        origin,
                    ))
                    ctr += 1

    results.sort(key=lambda r: r.total_elapsed_seconds)
    if verbose:
        print(f"  Search complete: {states_explored:,} states explored, "
              f"{len(results)} valid schedules found.")
    return results[:top_n]
