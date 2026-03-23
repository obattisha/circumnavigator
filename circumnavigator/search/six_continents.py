"""Time-space priority-queue search for the fastest six-continent world trip.

Rules differ from the circumnavigation search:
  • Must visit all six inhabited continents (AF, AS, EU, NA, OC, SA).
  • No longitude coverage requirement — direction is unconstrained.
  • No minimum distance requirement.
  • Must return to the starting airport.

The search state tracks which continents have been visited so far.
Pruning: if the remaining available legs cannot cover the unvisited
continents plus the mandatory closing leg, the branch is dropped.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from config import (
    COUNTRY_TO_CONTINENT,
    MIN_CONNECTION_MINUTES,
    SIX_CONTINENT_RECORD_SECONDS,
)
from circumnavigator.data.airports import Airport
from circumnavigator.geometry.distance import haversine
from circumnavigator.phase2.airlabs_client import FlightFrequency
from circumnavigator.phase2.static_scheduler import ScheduledLeg, ScheduledRoute
from circumnavigator.phase1.enumerator import CandidateRoute

UTC = timezone.utc
ALL_SIX = frozenset(["AF", "AS", "EU", "NA", "OC", "SA"])


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
    """Return ALL (flight, dep_dt, arr_dt) tuples departing at or after
    *earliest* and within *max_wait_hours*."""
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
) -> CandidateRoute:
    iatas = [legs[0].origin] + [leg.destination for leg in legs]
    dists: list[float] = []
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
        lon_coverage=0.0,   # not tracked for 6-continent search
        direction="mixed",
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
    max_legs: int = 7,
    budget_hours: float = 80.0,
    max_wait_hours: int = 24,
    top_n: int = 50,
    verbose: bool = True,
) -> list[ScheduledRoute]:
    """Find the fastest schedules that visit all six inhabited continents.

    Args:
        origins:         IATA codes to depart from (one per search thread).
        freq_map:        (dep, arr) → list of FlightFrequency objects.
        airports:        Full airport metadata dict.
        start_dates:     Calendar dates to attempt first departure.
        max_legs:        Maximum number of flight legs (default 7).
        budget_hours:    Prune states exceeding this elapsed time.
        max_wait_hours:  Give up on a connection if no flight within this window.
        top_n:           Maximum results to return.
        verbose:         Print progress to stderr.

    Returns:
        List of ScheduledRoute sorted by total elapsed seconds.
    """
    budget_s = budget_hours * 3600

    # Build continent map for all airports in the freq_map.
    continent_of: dict[str, str] = {}
    for iata, ap in airports.items():
        cont = COUNTRY_TO_CONTINENT.get(ap.country_code)
        if cont:
            continent_of[iata] = cont

    # Build outbound index — no direction filter, but only inter-continental
    # legs are useful for intermediate hops (intra-continental legs waste a
    # leg slot without gaining a new continent; they are allowed only for the
    # closing leg back to origin).
    #
    # outbound[dep] = [(arr, dist_km, arr_continent, [FlightFrequency])]
    outbound: dict[str, list[tuple[str, float, str, list[FlightFrequency]]]] = {}
    for (dep, arr), flights in freq_map.items():
        if not flights:
            continue
        dep_ap = airports.get(dep)
        arr_ap = airports.get(arr)
        if dep_ap is None or arr_ap is None:
            continue
        dep_cont = continent_of.get(dep)
        arr_cont = continent_of.get(arr)
        if dep_cont is None or arr_cont is None:
            continue
        # Only index inter-continental legs; closing legs (same continent back
        # to origin) are handled by checking dst == origin during expansion.
        if dep_cont == arr_cont:
            continue
        dist = haversine(dep_ap.lat, dep_ap.lon, arr_ap.lat, arr_ap.lon)
        outbound.setdefault(dep, []).append((arr, dist, arr_cont, flights))

    # Also build a separate same-continent index so we can evaluate closing
    # legs that happen to cross back within the same continent.
    # (The closing leg just needs dst == origin, handled inline below.)

    results: list[ScheduledRoute] = []
    seen: set[tuple] = set()
    ctr = 0

    # Heap state:
    # (elapsed_s, ctr, first_dep_ts, arr_ts, cur_ap,
    #  visited_tuple, continents_tuple, legs_tuple, origin)
    # All elements after 'ctr' are never compared by the heap (ctr is unique).
    pq: list = []

    for origin in origins:
        ap = airports.get(origin)
        if ap is None:
            continue
        origin_cont = continent_of.get(origin)
        if origin_cont is None:
            continue
        for sd in start_dates:
            start_dt = datetime(sd.year, sd.month, sd.day, 0, 0, tzinfo=UTC)
            heapq.heappush(pq, (
                0.0, ctr,
                None,                       # first_dep_ts
                start_dt.timestamp(),       # arr_ts: available from midnight
                origin,
                (origin,),                  # visited airports
                (origin_cont,),             # visited continents (sorted tuple)
                (),                         # legs
                origin,
            ))
            ctr += 1

    states_explored = 0

    while pq:
        (elapsed_s, _, first_dep_ts, arr_ts,
         cur_ap, visited, conts_t, legs, origin) = heapq.heappop(pq)

        if elapsed_s > budget_s:
            continue

        states_explored += 1
        conts = frozenset(conts_t)
        depth = len(legs)

        cur_airport = airports.get(cur_ap)
        if cur_airport is None:
            continue

        arr_dt = datetime.fromtimestamp(arr_ts, tz=UTC)

        if first_dep_ts is None:
            earliest_dep = arr_dt
        else:
            earliest_dep = arr_dt + timedelta(minutes=_min_conn(cur_airport))

        # Evaluate inter-continental outbound legs.
        for dst, leg_km, arr_cont, flights in outbound.get(cur_ap, []):
            closing = dst == origin
            if dst in visited and not closing:
                continue

            new_conts = conts | {arr_cont}
            new_depth = depth + 1

            if closing:
                # Valid only if all 6 continents are covered.
                if new_conts < ALL_SIX:
                    continue
                if new_depth < 6:
                    continue
            else:
                remaining = max_legs - new_depth
                unvisited = len(ALL_SIX - new_conts)
                # Need 'unvisited' more legs for remaining continents + 1 closing leg.
                if remaining < unvisited + 1:
                    continue
                if new_depth >= max_legs:
                    continue

            if first_dep_ts is None:
                same_day_end = earliest_dep + timedelta(hours=18)
                all_opts = _all_next_flights(flights, earliest_dep, max_wait_hours)
                candidates = [t for t in all_opts if t[1] <= same_day_end]
                if not candidates:
                    candidates = all_opts[:1]
            else:
                candidates = _all_next_flights(flights, earliest_dep, max_wait_hours)[:1]
            for fl, dep_dt, new_arr_dt in candidates:
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
                    candidate = _make_candidate(legs_list, airports)
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
                    new_conts_t = tuple(sorted(new_conts))
                    heapq.heappush(pq, (
                        new_elapsed, ctr,
                        new_first_dep_ts,
                        new_arr_dt.timestamp(),
                        dst,
                        new_visited,
                        new_conts_t,
                        new_legs,
                        origin,
                    ))
                    ctr += 1

    results.sort(key=lambda r: r.total_elapsed_seconds)
    if verbose:
        print(f"  Search complete: {states_explored:,} states explored, "
              f"{len(results)} valid schedules found.")
    return results[:top_n]
