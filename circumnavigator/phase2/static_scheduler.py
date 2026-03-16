"""Static schedule stitcher using AirLabs frequency data.

No per-date API calls.  Given days-of-week + UTC times for every leg,
we search a 14-day departure window and find the combination that
minimises total wheel-up → wheel-down elapsed time.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from config import MIN_CONNECTION_MINUTES, RECORD_TIME_SECONDS
from circumnavigator.data.airports import Airport
from circumnavigator.phase1.enumerator import CandidateRoute
from circumnavigator.phase2.airlabs_client import FlightFrequency

UTC = timezone.utc
_MAX_WAIT_DAYS = 4   # give up looking for next valid flight after this many days


# --------------------------------------------------------------------------- #
# Output types (reused by reporter)
# --------------------------------------------------------------------------- #

@dataclass
class ScheduledLeg:
    origin: str
    destination: str
    flight_number: str
    departure_utc: datetime
    arrival_utc: datetime
    duration_minutes: int
    connection_minutes: Optional[int] = None   # wait at origin before this leg


@dataclass
class ScheduledRoute:
    candidate: CandidateRoute
    legs: list[ScheduledLeg]
    start_date: str           # YYYY-MM-DD of first leg departure
    total_elapsed_seconds: float = field(init=False)
    beats_record: bool = field(init=False)

    def __post_init__(self) -> None:
        first = self.legs[0].departure_utc
        last  = self.legs[-1].arrival_utc
        self.total_elapsed_seconds = (last - first).total_seconds()
        self.beats_record = self.total_elapsed_seconds < RECORD_TIME_SECONDS

    @property
    def elapsed_hms(self) -> str:
        s = int(self.total_elapsed_seconds)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}h {m:02d}m {sec:02d}s"

    @property
    def vs_record(self) -> str:
        diff = int(RECORD_TIME_SECONDS - self.total_elapsed_seconds)
        sign = "-" if diff >= 0 else "+"
        diff = abs(diff)
        h, rem = divmod(diff, 3600)
        m, sec = divmod(rem, 60)
        label = "faster" if sign == "-" else "slower"
        return f"{sign}{h}h {m:02d}m {sec:02d}s {label}"


# --------------------------------------------------------------------------- #
# Core stitcher
# --------------------------------------------------------------------------- #

def _min_connection(ap: Airport) -> int:
    cc = ap.country_code
    return MIN_CONNECTION_MINUTES.get(cc, MIN_CONNECTION_MINUTES["default"])


def _dt_from_time(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=UTC)


def _next_flight(
    flights: list[FlightFrequency],
    earliest: datetime,
) -> Optional[tuple[FlightFrequency, datetime, datetime]]:
    """Find earliest flight departing at or after *earliest*.

    Searches up to _MAX_WAIT_DAYS ahead.  Returns (flight, dep_dt, arr_dt) or None.
    """
    search_date = earliest.date()
    for day_offset in range(_MAX_WAIT_DAYS * 2):
        d = search_date + timedelta(days=day_offset)
        weekday = d.weekday()
        for flight in flights:                    # already sorted by dep_utc
            if not flight.operates_on(weekday):
                continue
            dep_dt = _dt_from_time(d, flight.dep_utc)
            if dep_dt < earliest:
                continue
            arr_date = d + timedelta(days=1) if flight.overnight else d
            arr_dt = _dt_from_time(arr_date, flight.arr_utc)
            return flight, dep_dt, arr_dt
    return None


def _stitch(
    iatas: list[str],
    freq_map: dict[tuple[str, str], list[FlightFrequency]],
    airports: dict[str, Airport],
    first_dep_date: date,
) -> Optional[list[ScheduledLeg]]:
    """Greedily stitch legs into the earliest valid schedule.

    For each leg we pick the earliest flight that satisfies the minimum
    connection constraint coming from the previous leg.
    """
    legs: list[ScheduledLeg] = []
    earliest: Optional[datetime] = None   # earliest valid departure for current leg

    for i in range(len(iatas) - 1):
        src, dst = iatas[i], iatas[i + 1]
        src_ap = airports[src]

        if earliest is None:
            # First leg: start searching from midnight of first_dep_date
            earliest = datetime(
                first_dep_date.year, first_dep_date.month, first_dep_date.day,
                0, 0, tzinfo=UTC
            )

        flights = freq_map.get((src, dst), [])
        if not flights:
            return None   # no service on this pair

        found = _next_flight(flights, earliest)
        if found is None:
            return None

        flight, dep_dt, arr_dt = found
        conn_min = int((dep_dt - legs[-1].arrival_utc).total_seconds() / 60) if legs else None
        legs.append(ScheduledLeg(
            origin=src,
            destination=dst,
            flight_number=flight.flight_iata,
            departure_utc=dep_dt,
            arrival_utc=arr_dt,
            duration_minutes=flight.duration_min,
            connection_minutes=conn_min,
        ))

        # Earliest valid departure for next leg = this arrival + min connection at dst
        min_conn = _min_connection(airports[dst])
        earliest = arr_dt + timedelta(minutes=min_conn)

    return legs


# --------------------------------------------------------------------------- #
# Public interface
# --------------------------------------------------------------------------- #

def schedule_route(
    candidate: CandidateRoute,
    freq_map: dict[tuple[str, str], list[FlightFrequency]],
    airports: dict[str, Airport],
    start_date: str,
    search_days: int = 14,
) -> Optional[ScheduledRoute]:
    """Find the best schedule for *candidate* over a *search_days* window.

    Tries each day as a potential first-leg departure and returns the
    ScheduledRoute with the shortest total elapsed time.
    """
    iatas = candidate.airports
    base = datetime.strptime(start_date, "%Y-%m-%d").date()
    best: Optional[ScheduledRoute] = None

    for offset in range(search_days):
        dep_date = base + timedelta(days=offset)
        legs = _stitch(iatas, freq_map, airports, dep_date)
        if legs is None:
            continue
        sr = ScheduledRoute(candidate=candidate, legs=legs, start_date=str(dep_date))
        if best is None or sr.total_elapsed_seconds < best.total_elapsed_seconds:
            best = sr

    return best


def schedule_all(
    candidates: list[CandidateRoute],
    freq_map: dict[tuple[str, str], list[FlightFrequency]],
    airports: dict[str, Airport],
    start_date: str,
    max_candidates: int = 100,
    search_days: int = 14,
    verbose: bool = True,
) -> list[ScheduledRoute]:
    """Schedule up to *max_candidates* and return sorted ScheduledRoute list."""
    subset = candidates[:max_candidates]
    results: list[ScheduledRoute] = []

    for i, candidate in enumerate(subset, 1):
        if verbose and i % 10 == 0:
            print(f"  Scheduling {i}/{len(subset)} ...", file=sys.stderr)
        sr = schedule_route(candidate, freq_map, airports, start_date, search_days)
        if sr is not None:
            results.append(sr)

    results.sort(key=lambda s: s.total_elapsed_seconds)
    if verbose:
        print(f"  {len(results)}/{len(subset)} candidates have valid schedules.", file=sys.stderr)
    return results


def extract_pairs(candidates: list[CandidateRoute]) -> list[tuple[str, str]]:
    """Return deduplicated (dep, arr) pairs needed to schedule *candidates*."""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for c in candidates:
        for i in range(len(c.airports) - 1):
            p = (c.airports[i], c.airports[i + 1])
            if p not in seen:
                seen.add(p)
                pairs.append(p)
    return pairs
