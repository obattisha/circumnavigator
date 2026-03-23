"""Time-space priority-queue search for the fastest antipodal circumnavigation.

Guinness World Record — "Fastest circumnavigation passing through two
approximate antipodal points by scheduled flights":

  1. Full circumnavigation: 360° longitude coverage, one consistent direction
     (eastbound or westbound), no backtracking.
  2. Minimum distance: 36,787.559 km (Tropic of Cancer circumference).
  3. Must cross the equator.
  4. Must visit two airports forming a near-antipodal pair (independent
     5° tolerance per dimension: lat_off ≤ 5° AND lon_off ≤ 5°).
  5. Must land AND change planes at both antipodal airports.
  6. All flights must appear in published commercial timetables.
  7. Return to the starting airport.

Current record: Andrew Fisher, 52h 34m 00s (Jan 2018)
  PVG → AKL → EZE → AMS → PVG  (eastbound, 360°)
  Antipodal pair: PVG (31.1°N 121.8°E) ↔ EZE (34.8°S 58.5°W)
  lat_off = 3.7°, lon_off = 0.3°  ✓

This search is the standard circumnavigation search (time_space.py) with
one additional state variable: ap_pair_met (bool) — True once the set of
visited airports contains both airports of some near-antipodal pair.
"""

from __future__ import annotations

import heapq
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from config import (
    GUINNESS_MIN_DISTANCE_KM,
    MIN_LONGITUDE_COVERAGE,
    MIN_CONNECTION_MINUTES,
    ANTIPODAL_RECORD_SECONDS,
)
from circumnavigator.data.airports import Airport
from circumnavigator.geometry.distance import haversine
from circumnavigator.geometry.longitude import longitude_delta
from circumnavigator.phase2.airlabs_client import FlightFrequency
from circumnavigator.phase2.static_scheduler import ScheduledLeg, ScheduledRoute
from circumnavigator.phase1.enumerator import CandidateRoute

UTC = timezone.utc
EARTH_MAX_LEG_KM = 20_015.0


# --------------------------------------------------------------------------- #
# Helpers (identical to time_space.py)
# --------------------------------------------------------------------------- #

def _min_conn(airport: Airport) -> int:
    cc = airport.country_code if airport else "XX"
    return MIN_CONNECTION_MINUTES.get(cc, MIN_CONNECTION_MINUTES["default"])


def _all_next_flights(
    flights: list[FlightFrequency],
    earliest: datetime,
    max_wait_hours: int,
) -> list[tuple[FlightFrequency, datetime, datetime]]:
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


def _make_candidate(
    legs: list[ScheduledLeg],
    airports: dict[str, Airport],
    lon_cov: float,
    direction: str,
) -> CandidateRoute:
    iatas = [legs[0].origin] + [leg.destination for leg in legs]
    dists: list[float] = []
    for leg in legs:
        a1, a2 = airports.get(leg.origin), airports.get(leg.destination)
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
    antipodal_partners: dict[str, frozenset[str]],
    max_legs: int = 5,
    direction: str = "eastbound",
    require_min_distance: bool = True,
    budget_hours: float = 75.0,
    max_wait_hours: int = 24,
    top_n: int = 50,
    verbose: bool = True,
) -> list[ScheduledRoute]:
    """Find the fastest full circumnavigation routes that also pass through
    a near-antipodal airport pair.

    Identical to the standard circumnavigation search (time_space.py) except:
      - State carries ap_pair_met (bool).
      - Closing leg is only valid when ap_pair_met is True.

    Args:
        origins:             IATA codes to depart from.
        freq_map:            (dep, arr) -> list[FlightFrequency].
        airports:            Full airport metadata dict.
        start_dates:         Calendar dates for first departure.
        antipodal_partners:  Precomputed map: iata -> frozenset of near-antipodal iatas.
        max_legs:            Maximum flight legs (default 5).
        direction:           "eastbound" or "westbound".
        require_min_distance: Enforce 36,788 km Guinness minimum.
        budget_hours:        Prune states exceeding this elapsed time.
        max_wait_hours:      Give up on a connection if no flight in this window.
        top_n:               Maximum results to return.
        verbose:             Print progress to stderr.

    Returns:
        List of ScheduledRoute sorted by total elapsed seconds.
    """
    east = direction == "eastbound"
    budget_s = budget_hours * 3600

    # Direction-filtered outbound index (same as time_space.py).
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
        if east and delta <= 0:
            continue
        if not east and delta >= 0:
            continue
        dist = haversine(dep_ap.lat, dep_ap.lon, arr_ap.lat, arr_ap.lon)
        outbound.setdefault(dep, []).append((arr, dist, delta, flights))

    results: list[ScheduledRoute] = []
    seen: set[tuple] = set()
    ctr = 0
    states_explored = 0

    # State tuple:
    # (elapsed_s, ctr, first_dep_ts, arr_ts, cur_ap,
    #  visited_tuple, lon_sum, total_km, ap_pair_met, legs_tuple, origin)
    pq: list = []

    for origin in origins:
        if origin not in airports:
            continue
        # Origin may itself be one half of a near-antipodal pair.
        # ap_pair_met starts False; it becomes True once we visit the partner.
        for sd in start_dates:
            start_dt = datetime(sd.year, sd.month, sd.day, 0, 0, tzinfo=UTC)
            heapq.heappush(pq, (
                0.0, ctr,
                None,                   # first_dep_ts
                start_dt.timestamp(),   # arr_ts: available from midnight
                origin,
                (origin,),              # visited airports
                0.0,                    # lon_sum
                0.0,                    # total_km
                False,                  # ap_pair_met
                (),                     # legs
                origin,
            ))
            ctr += 1

    while pq:
        (elapsed_s, _, first_dep_ts, arr_ts,
         cur_ap, visited, lon_sum, total_km,
         ap_pair_met, legs, origin) = heapq.heappop(pq)

        if elapsed_s > budget_s:
            continue

        states_explored += 1
        depth = len(legs)

        cur_airport = airports.get(cur_ap)
        if cur_airport is None:
            continue

        arr_dt = datetime.fromtimestamp(arr_ts, tz=UTC)
        earliest_dep = arr_dt if first_dep_ts is None else (
            arr_dt + timedelta(minutes=_min_conn(cur_airport))
        )

        visited_set = set(visited)

        for dst, leg_km, delta, flights in outbound.get(cur_ap, []):
            closing = dst == origin
            if dst in visited_set and not closing:
                continue

            new_lon = lon_sum + delta
            new_km  = total_km + leg_km
            new_depth = depth + 1

            # Update antipodal pair status: did we just visit the partner
            # of any already-visited airport?
            if not ap_pair_met:
                new_ap_met = any(
                    p in visited_set for p in antipodal_partners.get(dst, frozenset())
                )
            else:
                new_ap_met = True

            if closing:
                if new_depth < 3:
                    continue
                if abs(new_lon) < MIN_LONGITUDE_COVERAGE:
                    continue
                if require_min_distance and new_km < GUINNESS_MIN_DISTANCE_KM:
                    continue
                # Antipodal pair must have been satisfied somewhere in the route.
                if not new_ap_met:
                    continue
            else:
                remaining = max_legs - new_depth
                if abs(new_lon) + (remaining + 1) * 180.0 < MIN_LONGITUDE_COVERAGE:
                    continue
                if require_min_distance:
                    if new_km + (remaining + 1) * EARTH_MAX_LEG_KM < GUINNESS_MIN_DISTANCE_KM:
                        continue
                if new_depth >= max_legs:
                    continue

            for fl, dep_dt, new_arr_dt in _all_next_flights(flights, earliest_dep, max_wait_hours):
                new_first_dep_ts = dep_dt.timestamp() if first_dep_ts is None else first_dep_ts
                new_elapsed = new_arr_dt.timestamp() - new_first_dep_ts
                if new_elapsed > budget_s:
                    continue

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
                        print(f"  Found {len(results)} schedules so far "
                              f"(latest: {sr.elapsed_hms}) ...", flush=True)
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
                        new_ap_met,
                        new_legs,
                        origin,
                    ))
                    ctr += 1

    results.sort(key=lambda r: r.total_elapsed_seconds)
    if verbose:
        print(f"  Search complete: {states_explored:,} states explored, "
              f"{len(results)} valid schedules found.")
    return results[:top_n]
